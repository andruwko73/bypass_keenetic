import concurrent.futures
import gc
import json
import os
import shutil
import signal
import subprocess
import threading
import time
from collections import deque

YOUTUBE_HEALTHCHECK_URL = 'https://www.youtube.com/generate_204'
YOUTUBE_HEALTHCHECK_URLS = (
    YOUTUBE_HEALTHCHECK_URL,
    'https://redirector.googlevideo.com/generate_204',
    'https://i.ytimg.com/generate_204',
    'https://www.youtube.com',
)
YOUTUBE_HEALTHCHECK_MIN_OK = 2
TELEGRAM_HEALTHCHECK_URLS = (
    'https://web.telegram.org/',
    'https://t.me/',
)
TELEGRAM_HEALTHCHECK_MIN_OK = 1


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


def check_youtube_through_proxy(check_http, proxy_url, *, http_timeouts, urls=YOUTUBE_HEALTHCHECK_URLS, min_ok=YOUTUBE_HEALTHCHECK_MIN_OK):
    ok_count = 0
    last_message = ''
    connect_timeout, read_timeout = http_timeouts
    for url in urls:
        ok, message = check_http(
            proxy_url,
            url=url,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )
        if ok:
            ok_count += 1
            if ok_count >= max(1, int(min_ok or 1)):
                return True, 'YouTube endpoints confirmed'
        else:
            last_message = message
    return False, last_message or 'YouTube endpoints did not respond through this key.'


def check_telegram_service_through_proxy(
    check_telegram_api,
    check_http,
    proxy_url,
    *,
    telegram_timeouts,
    http_timeouts,
    urls=TELEGRAM_HEALTHCHECK_URLS,
    min_ok=TELEGRAM_HEALTHCHECK_MIN_OK,
):
    tg_connect, tg_read = telegram_timeouts
    api_ok, api_message = check_telegram_api(
        proxy_url,
        connect_timeout=tg_connect,
        read_timeout=tg_read,
    )
    if not api_ok:
        return False, api_message

    connect_timeout, read_timeout = http_timeouts
    ok_hosts = []
    failed = []
    for url in urls or TELEGRAM_HEALTHCHECK_URLS:
        host = url.split('/')[2] if '://' in url else url
        ok, message = check_http(
            proxy_url,
            url=url,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )
        if ok:
            ok_hosts.append(host)
            if len(ok_hosts) >= max(1, int(min_ok or 1)):
                return True, 'Telegram endpoints confirmed: ' + ', '.join(ok_hosts)
        else:
            failed.append(f'{host}: {message}')
    return False, '; '.join(failed[-2:]) or 'Telegram web endpoints did not respond through this key.'


def build_pool_probe_core_config_batch(probe_tasks, test_port, proxy_outbound_from_key):
    config_json = {
        'log': {
            'access': '/dev/null',
            'error': '/dev/null',
            'loglevel': 'warning',
        },
        'dns': {
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
    probe_tasks = deque(
        (proto, (key_value or '').strip())
        for proto, key_value in candidates
        if (key_value or '').strip()
    )
    batch_size = max(1, int(batch_size or 1))
    tg_connect, tg_read = telegram_timeouts
    http_connect, http_read = http_timeouts
    while probe_tasks:
        raw_batch = [probe_tasks.popleft() for _ in range(min(batch_size, len(probe_tasks)))]
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
                    primary_ok, _ = check_youtube_through_proxy(
                        check_http,
                        proxy_url,
                        http_timeouts=(http_connect, http_read),
                    )
                    tg_ok = None
                    yt_ok = primary_ok
                else:
                    primary_ok, _ = check_telegram_service_through_proxy(
                        check_telegram_api,
                        check_http,
                        proxy_url,
                        telegram_timeouts=(tg_connect, tg_read),
                        http_timeouts=(http_connect, http_read),
                    )
                    tg_ok = primary_ok
                    yt_ok = None
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
    cpu_busy_percent=None,
    max_cpu_percent=0,
    high_cpu_delay_seconds=5.0,
    max_high_cpu_wait_seconds=45.0,
    low_memory_delay_seconds=15.0,
    max_low_memory_wait_seconds=180.0,
    sleep=time.sleep,
    time_provider=time.time,
):
    pending_tasks = deque(probe_tasks or [])
    total = len(pending_tasks)
    checked = 0
    marked_tasks = set()
    ignored_result_tasks = set()
    result_deadlines = {}
    ignored_result_lock = threading.Lock()

    def task_id(proto, key_value):
        return (proto, hash_key(key_value))

    def cancel_requested():
        return bool(cancel_event is not None and cancel_event.is_set())

    def mark_checked(proto, key_value):
        nonlocal checked
        checked_task_id = task_id(proto, key_value)
        if checked_task_id in marked_tasks:
            return
        marked_tasks.add(checked_task_id)
        checked += 1
        set_checked(checked)

    def ignore_late_result(proto, key_value):
        with ignored_result_lock:
            ignored_task_id = task_id(proto, key_value)
            ignored_result_tasks.add(ignored_task_id)
            result_deadlines.pop(ignored_task_id, None)

    def set_result_deadline(proto, key_value, deadline):
        with ignored_result_lock:
            result_deadlines[task_id(proto, key_value)] = deadline

    def clear_result_deadline(proto, key_value):
        with ignored_result_lock:
            result_deadlines.pop(task_id(proto, key_value), None)

    def result_is_ignored(proto, key_value):
        with ignored_result_lock:
            current_task_id = task_id(proto, key_value)
            if current_task_id in ignored_result_tasks:
                return True
            deadline = result_deadlines.get(current_task_id)
        return bool(deadline is not None and time.monotonic() > deadline)

    def record_key_probe_if_current(proto, key_value, **kwargs):
        if result_is_ignored(proto, key_value):
            return
        record_key_probe(proto, key_value, **kwargs)

    def run_check_pool_key(proto, key_value, checks, proxy_url):
        try:
            return check_pool_key(
                proto,
                key_value,
                checks,
                proxy_url,
                record_key_probe=record_key_probe_if_current,
            )
        except TypeError as exc:
            if 'record_key_probe' not in str(exc) and 'unexpected keyword' not in str(exc):
                raise
            return check_pool_key(proto, key_value, checks, proxy_url)

    low_memory_since = None
    high_cpu_since = None
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

    def cpu_above_limit():
        if not cpu_busy_percent or not max_cpu_percent or max_cpu_percent <= 0:
            return None
        try:
            busy = cpu_busy_percent()
        except Exception:
            return None
        if busy is not None and busy >= max_cpu_percent:
            return busy
        return None

    try:
        while pending_tasks:
            if cancel_requested():
                log('Проверка пула приостановлена для применения выбранного ключа.')
                break
            high_cpu_percent = cpu_above_limit()
            if high_cpu_percent is not None:
                if high_cpu_since is None:
                    high_cpu_since = time_provider()
                note = (
                    f'Проверка ждёт снижения нагрузки CPU: сейчас {int(round(high_cpu_percent))}%, '
                    f'порог {int(round(max_cpu_percent))}%.'
                )
                update_note(note)
                if (
                    not max_high_cpu_wait_seconds or
                    time_provider() - high_cpu_since < max_high_cpu_wait_seconds
                ):
                    sleep(max(1.0, float(high_cpu_delay_seconds or 1.0)))
                    continue
                log(note + ' Продолжаю один ключ с низким приоритетом.')
            high_cpu_since = None
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

            raw_batch = [pending_tasks.popleft() for _ in range(min(batch_size, len(pending_tasks)))]
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
                    pending_tasks.extendleft(reversed(valid_batch))
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
                    batch_timeout = timeout_budget(
                        checks,
                        task_count=len(ready_batch),
                        workers=max_workers,
                    )
                    batch_deadline = time.monotonic() + float(batch_timeout or 0)
                    for offset, proto, key_value in ready_batch:
                        port = str(int(test_port) + offset)
                        proxy_url = f'socks5h://127.0.0.1:{port}'
                        set_result_deadline(proto, key_value, batch_deadline)
                        future = executor.submit(run_check_pool_key, proto, key_value, checks, proxy_url)
                        future_map[future] = (proto, key_value)

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
                            clear_result_deadline(proto, key_value)
                            mark_checked(proto, key_value)
                            invalidate_caches()
                            gc.collect()

                    for future in pending:
                        proto, key_value = future_map[future]
                        future.cancel()
                        log(
                            f'Проверка ключа из пула {proto_label(proto)} превысила лимит '
                            f'{batch_timeout:g} сек.; результат не сохранён и ключ будет перепроверен позже.'
                        )
                        ignore_late_result(proto, key_value)
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

            if checked < total and pending_tasks:
                sleep(delay_seconds)
    except Exception as exc:
        log(f'Ошибка фоновой проверки пула ключей: {exc}')
    finally:
        if (cancel_requested() or paused_remaining) and pending_tasks and on_cancelled_remaining:
            try:
                on_cancelled_remaining(list(pending_tasks))
            except Exception as exc:
                log(f'Не удалось сохранить очередь продолжения проверки пула: {exc}')
        invalidate_caches()
        gc.collect()

    return checked, total
