import concurrent.futures
import gc
import json
import os
import shutil
import signal
import subprocess
import threading
import time


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
    if os.name == 'posix' and hasattr(os, 'nice'):
        def lower_priority():
            try:
                os.nice(10)
            except Exception:
                pass
        preexec_fn = lower_priority
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
            process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:
                try:
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


def cleanup_pool_probe_runtime(kill_processes=False):
    if kill_processes:
        try:
            output = subprocess.check_output(
                ['pgrep', '-f', '/tmp/bypass_pool_probe_'],
                stderr=subprocess.DEVNULL,
            ).decode('utf-8', errors='ignore')
            for raw_pid in output.split():
                try:
                    pid = int(raw_pid)
                except ValueError:
                    continue
                if pid != os.getpid():
                    os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        time.sleep(0.2)
        try:
            output = subprocess.check_output(
                ['pgrep', '-f', '/tmp/bypass_pool_probe_'],
                stderr=subprocess.DEVNULL,
            ).decode('utf-8', errors='ignore')
            for raw_pid in output.split():
                try:
                    pid = int(raw_pid)
                except ValueError:
                    continue
                if pid != os.getpid():
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
