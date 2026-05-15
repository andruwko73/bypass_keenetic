import concurrent.futures
import gc
import json
import os
import shutil
import signal
import subprocess
import threading
import time

YOUTUBE_HEALTHCHECK_URL = 'https://www.youtube.com/generate_204'


def pool_probe_socks_inbound(port, tag):
    return {
        'port': int(port),
        'listen': '127.0.0.1',
        'protocol': 'socks',
        'settings': {'auth': 'noauth', 'udp': True, 'ip': '127.0.0.1'},
        'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
        'tag': tag,
    }


def pool_probe_outbound(proto, key_value, tag, proxy_outbound_from_key, email='pool-probe@local'):
    return proxy_outbound_from_key(proto, key_value, tag, email=email)


def build_pool_probe_core_config_batch(probe_tasks, test_port, proxy_outbound_from_key):
    config_json = {
        'log': {
            'access': '/dev/null',
            'error': '/dev/null',
            'loglevel': 'warning',
        },
        'dns': {
            'hosts': {
                'api.telegram.org': '149.154.167.220',
            },
            'servers': ['8.8.8.8', '1.1.1.1', 'localhost'],
            'queryStrategy': 'UseIPv4',
        },
        'inbounds': [],
        'outbounds': [],
        'routing': {
            'domainStrategy': 'IPIfNonMatch',
            'rules': [],
        },
    }
    test_routes = []
    for offset, (proto, key_value) in enumerate(probe_tasks):
        port = str(int(test_port) + offset)
        inbound_tag = f'in-pool-probe-{offset}'
        outbound_tag = f'proxy-pool-probe-{offset}'
        config_json['inbounds'].append(pool_probe_socks_inbound(port, inbound_tag))
        config_json['outbounds'].append(pool_probe_outbound(proto, key_value, outbound_tag, proxy_outbound_from_key))
        test_routes.append({
            'type': 'field',
            'inboundTag': [inbound_tag],
            'outboundTag': outbound_tag,
            'enabled': True,
        })
    config_json['outbounds'].append({'protocol': 'freedom', 'tag': 'direct'})
    config_json['routing']['rules'] = test_routes
    return config_json


def start_pool_probe_xray(config_json):
    xray_binary = shutil.which('xray') or '/opt/sbin/xray'
    config_path = f'/tmp/bypass_pool_probe_{os.getpid()}_{threading.get_ident()}.json'
    with open(config_path, 'w', encoding='utf-8') as file:
        json.dump(config_json, file, ensure_ascii=False, separators=(',', ':'))
    preexec_fn = None
    if os.name == 'posix':
        def prepare_child_process():
            try:
                if hasattr(os, 'setsid'):
                    os.setsid()
            except Exception:
                pass
            try:
                if hasattr(os, 'nice'):
                    os.nice(10)
            except Exception:
                pass
        preexec_fn = prepare_child_process
    process = subprocess.Popen(
        [xray_binary, 'run', '-c', config_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        preexec_fn=preexec_fn,
    )
    return process, config_path


def stop_pool_probe_xray(process, config_path):
    pid = None
    try:
        pid = process.pid if process else None
        if process and process.poll() is None:
            try:
                if os.name == 'posix' and hasattr(os, 'getpgid') and hasattr(os, 'killpg'):
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                else:
                    process.terminate()
            except Exception:
                process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:
                try:
                    try:
                        if os.name == 'posix' and hasattr(os, 'getpgid') and hasattr(os, 'killpg'):
                            os.killpg(os.getpgid(pid), signal.SIGKILL)
                        else:
                            process.kill()
                    except Exception:
                        process.kill()
                    process.wait(timeout=2)
                except Exception:
                    if pid:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except Exception:
                            pass
    except Exception:
        pass
    if pid:
        try:
            os.waitpid(pid, os.WNOHANG)
        except Exception:
            pass
    try:
        if config_path and os.path.exists(config_path):
            os.remove(config_path)
    except Exception:
        pass


def _pool_probe_process_ids():
    pids = set()
    try:
        output = subprocess.check_output(
            ['pgrep', '-f', '/tmp/bypass_pool_probe_'],
            stderr=subprocess.DEVNULL,
        ).decode('utf-8', errors='ignore')
        for raw_pid in output.split():
            try:
                pids.add(int(raw_pid))
            except ValueError:
                continue
    except Exception:
        pass
    try:
        for name in os.listdir('/proc'):
            if not name.isdigit():
                continue
            pid = int(name)
            if pid == os.getpid():
                continue
            try:
                with open(os.path.join('/proc', name, 'cmdline'), 'rb') as file:
                    cmdline = file.read().decode('utf-8', errors='ignore')
                if '/tmp/bypass_pool_probe_' in cmdline:
                    pids.add(pid)
            except Exception:
                pass
    except Exception:
        pass
    pids.discard(os.getpid())
    return pids


def cleanup_pool_probe_runtime(kill_processes=False):
    if kill_processes:
        for pid in _pool_probe_process_ids():
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
        time.sleep(0.2)
        for pid in _pool_probe_process_ids():
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass

    try:
        for name in os.listdir('/tmp'):
            if name.startswith('bypass_pool_probe_') and name.endswith('.json'):
                try:
                    os.remove(os.path.join('/tmp', name))
                except Exception:
                    pass
    except Exception:
        pass


def find_pool_failover_candidate(
    candidates,
    *,
    service,
    batch_size,
    test_port,
    proxy_outbound_from_key,
    wait_for_socks5,
    check_telegram_api,
    check_http,
    record_key_probe,
    proto_label,
    log,
    telegram_timeouts,
    http_timeouts,
    validate_outbound=pool_probe_outbound,
    build_config_batch=build_pool_probe_core_config_batch,
    start_xray=start_pool_probe_xray,
    stop_xray=stop_pool_probe_xray,
    cleanup_runtime=cleanup_pool_probe_runtime,
    collect_garbage=gc.collect,
):
    probe_tasks = [(proto, (key_value or '').strip()) for proto, key_value in candidates if (key_value or '').strip()]
    batch_size = max(1, int(batch_size or 1))
    tg_connect, tg_read = telegram_timeouts
    http_connect, http_read = http_timeouts
    while probe_tasks:
        raw_batch = probe_tasks[:batch_size]
        del probe_tasks[:batch_size]
        valid_batch = []
        for proto, key_value in raw_batch:
            try:
                validate_outbound(proto, key_value, 'proxy-failover-validate', proxy_outbound_from_key)
                valid_batch.append((proto, key_value))
            except Exception as exc:
                log(f'Auto-failover: ключ {proto} не подготовлен для проверки: {exc}')
        if not valid_batch:
            continue

        process = None
        config_path = None
        try:
            process, config_path = start_xray(build_config_batch(valid_batch, test_port, proxy_outbound_from_key))
            for offset, (proto, key_value) in enumerate(valid_batch):
                port = str(int(test_port) + offset)
                if not wait_for_socks5(port, timeout=6):
                    log(
                        f'Auto-failover: тестовый SOCKS-порт {port} не поднялся для {proto_label(proto)}; '
                        'прежний статус ключа оставлен без изменений.'
                    )
                    continue
                proxy_url = f'socks5h://127.0.0.1:{port}'
                if service == 'youtube':
                    primary_ok, _ = check_http(
                        proxy_url,
                        url=YOUTUBE_HEALTHCHECK_URL,
                        connect_timeout=http_connect,
                        read_timeout=http_read,
                    )
                    tg_ok, _ = check_telegram_api(
                        proxy_url,
                        connect_timeout=tg_connect,
                        read_timeout=tg_read,
                    )
                    yt_ok = primary_ok
                else:
                    primary_ok, _ = check_telegram_api(
                        proxy_url,
                        connect_timeout=tg_connect,
                        read_timeout=tg_read,
                    )
                    tg_ok = primary_ok
                    yt_ok, _ = check_http(
                        proxy_url,
                        url=YOUTUBE_HEALTHCHECK_URL,
                        connect_timeout=http_connect,
                        read_timeout=http_read,
                    )
                record_key_probe(proto, key_value, tg_ok=tg_ok, yt_ok=yt_ok)
                if primary_ok:
                    return proto, key_value, tg_ok, yt_ok
        except Exception as exc:
            log(f'Auto-failover: ошибка проверки кандидатов через временный xray: {exc}')
        finally:
            stop_xray(process, config_path)
            cleanup_runtime(kill_processes=True)
            collect_garbage()
    return None


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
    cancel_event=None,
    on_cancelled_remaining=None,
    set_note=None,
    low_memory_delay_seconds=15.0,
    max_low_memory_wait_seconds=180.0,
    sleep=time.sleep,
    time_provider=time.time,
):
    total = len(probe_tasks)
    checked = 0
    marked_tasks = set()

    def cancel_requested():
        return bool(cancel_event is not None and cancel_event.is_set())

    def mark_checked(proto, key_value):
        nonlocal checked
        task_key = (proto, hash_key(key_value))
        if task_key in marked_tasks:
            return
        marked_tasks.add(task_key)
        checked += 1
        set_checked(checked)

    low_memory_since = None
    paused_remaining = False

    def update_note(text):
        if set_note:
            try:
                set_note(text)
            except Exception:
                pass

    def memory_below_limit():
        available_kb = available_memory_kb()
        if available_kb is not None and available_kb < min_available_kb:
            return available_kb
        return None

    try:
        while probe_tasks:
            if cancel_requested():
                log('Проверка пула приостановлена для применения выбранного ключа.')
                break
            low_memory_kb = memory_below_limit()
            if low_memory_kb is not None:
                if low_memory_since is None:
                    low_memory_since = time_provider()
                note = (
                    f'Проверка ждёт свободную память: доступно {low_memory_kb} KB, '
                    f'порог {min_available_kb} KB.'
                )
                update_note(note)
                if max_low_memory_wait_seconds and time_provider() - low_memory_since >= max_low_memory_wait_seconds:
                    log(note)
                    paused_remaining = True
                    break
                sleep(max(1.0, float(low_memory_delay_seconds or 1.0)))
                continue
            low_memory_since = None
            update_note('')

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
                low_memory_kb = memory_below_limit()
                if low_memory_kb is not None:
                    note = (
                        f'Проверка остановила временный xray: доступно {low_memory_kb} KB, '
                        f'порог {min_available_kb} KB.'
                    )
                    log(note)
                    update_note(note)
                    probe_tasks[:0] = valid_batch
                    continue
                ready_batch = []
                for offset, (proto, key_value) in enumerate(valid_batch):
                    port = str(int(test_port) + offset)
                    if not wait_for_socks5(port, timeout=6):
                        log(f'Тестовый SOCKS-порт {port} не поднялся для {proto_label(proto)}.')
                        record_key_probe(
                            proto,
                            key_value,
                            tg_ok=False,
                            yt_ok=False,
                            custom=failed_custom_results(checks),
                        )
                        mark_checked(proto, key_value)
                        continue
                    ready_batch.append((offset, proto, key_value))

                if not ready_batch:
                    continue

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
                            f'{batch_timeout:g} сек.; ключ отмечен как не прошедший проверку.'
                        )
                        record_key_probe(
                            proto,
                            key_value,
                            tg_ok=False,
                            yt_ok=False,
                            custom=failed_custom_results(checks),
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
                    record_key_probe(
                        proto,
                        key_value,
                        tg_ok=False,
                        yt_ok=False,
                        custom=failed_custom_results(checks),
                    )
                    mark_checked(proto, key_value)
            finally:
                stop_xray(process, config_path)
                cleanup_runtime(kill_processes=True)
                invalidate_caches()
                del raw_batch
                del valid_batch
                gc.collect()

            if checked < total and probe_tasks:
                sleep(delay_seconds)
    except Exception as exc:
        log(f'Ошибка фоновой проверки пула ключей: {exc}')
    finally:
        if (cancel_requested() or paused_remaining) and probe_tasks and on_cancelled_remaining:
            try:
                on_cancelled_remaining(list(probe_tasks))
            except Exception as exc:
                log(f'Не удалось сохранить очередь продолжения проверки пула: {exc}')
        invalidate_caches()
        gc.collect()

    return checked, total
