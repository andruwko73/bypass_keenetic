import concurrent.futures
import gc
import time


def run_pool_probe_worker(
    probe_tasks,
    checks,
    *,
    batch_size,
    concurrency,
    delay_seconds,
    min_available_kb,
    test_port,
    available_memory_kb,
    log,
    proto_label,
    hash_key,
    set_checked,
    validate_outbound,
    failed_custom_results,
    record_key_probe,
    start_xray_for_batch,
    wait_for_socks5,
    check_pool_key,
    timeout_budget,
    stop_xray,
    cleanup_runtime,
    invalidate_caches,
):
    total = len(probe_tasks)
    checked = 0
    marked_tasks = set()

    def mark_checked(proto, key_value):
        nonlocal checked
        task_key = (proto, hash_key(key_value))
        if task_key in marked_tasks:
            return
        marked_tasks.add(task_key)
        checked += 1
        set_checked(checked)

    try:
        while probe_tasks:
            available_kb = available_memory_kb()
            if available_kb is not None and available_kb < min_available_kb:
                log(
                    f'Проверка пула остановлена: свободной памяти {available_kb} KB, '
                    f'порог {min_available_kb} KB.'
                )
                break

            raw_batch = probe_tasks[:batch_size]
            del probe_tasks[:batch_size]
            valid_batch = []

            for proto, key_value in raw_batch:
                try:
                    validate_outbound(proto, key_value)
                    valid_batch.append((proto, key_value))
                except Exception as exc:
                    log(f'Ошибка подготовки ключа из пула {proto_label(proto)}: {exc}')
                    record_key_probe(
                        proto,
                        key_value,
                        tg_ok=False,
                        yt_ok=False,
                        custom=failed_custom_results(checks),
                    )
                    mark_checked(proto, key_value)

            if not valid_batch:
                continue

            process = None
            config_path = None
            try:
                process, config_path = start_xray_for_batch(valid_batch)
                ready_batch = []
                for offset, (proto, key_value) in enumerate(valid_batch):
                    port = str(int(test_port) + offset)
                    if not wait_for_socks5(port, timeout=6):
                        log(f'Тестовый SOCKS-порт {port} не поднялся для {proto_label(proto)}.')
                        mark_checked(proto, key_value)
                        continue
                    ready_batch.append((offset, proto, key_value))

                if not ready_batch:
                    raise RuntimeError('Тестовые SOCKS-порты не поднялись.')

                max_workers = min(concurrency, len(ready_batch))
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
                future_map = {}
                try:
                    for offset, proto, key_value in ready_batch:
                        port = str(int(test_port) + offset)
                        proxy_url = f'socks5h://127.0.0.1:{port}'
                        future = executor.submit(check_pool_key, proto, key_value, checks, proxy_url)
                        future_map[future] = (proto, key_value)

                    batch_timeout = timeout_budget(
                        checks,
                        task_count=len(ready_batch),
                        workers=max_workers,
                    )
                    done, pending = concurrent.futures.wait(future_map, timeout=batch_timeout)

                    for future in done:
                        proto, key_value = future_map[future]
                        try:
                            future.result()
                        except Exception as exc:
                            log(f'Ошибка проверки ключа из пула {proto_label(proto)}: {exc}')
                            record_key_probe(
                                proto,
                                key_value,
                                tg_ok=False,
                                yt_ok=False,
                                custom=failed_custom_results(checks),
                            )
                        finally:
                            mark_checked(proto, key_value)
                            invalidate_caches()
                            gc.collect()

                    for future in pending:
                        proto, key_value = future_map[future]
                        future.cancel()
                        log(
                            f'Проверка ключа из пула {proto_label(proto)} превысила лимит '
                            f'{batch_timeout:g} сек.; прежний статус оставлен без изменений.'
                        )
                        mark_checked(proto, key_value)
                        invalidate_caches()
                        gc.collect()
                finally:
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except TypeError:
                        executor.shutdown(wait=False)
            except Exception as exc:
                log(f'Ошибка проверки пачки ключей из пула: {exc}')
                for proto, key_value in valid_batch:
                    mark_checked(proto, key_value)
            finally:
                stop_xray(process, config_path)
                cleanup_runtime(kill_processes=True)
                invalidate_caches()
                del raw_batch
                del valid_batch
                gc.collect()

            if checked < total and probe_tasks:
                time.sleep(delay_seconds)
    except Exception as exc:
        log(f'Ошибка фоновой проверки пула ключей: {exc}')
    finally:
        invalidate_caches()
        gc.collect()

    return checked, total
