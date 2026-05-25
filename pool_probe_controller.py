import gc
import threading
import time

YOUTUBE_HEALTHCHECK_URLS = (
    'https://www.youtube.com/generate_204',
    'https://redirector.googlevideo.com/generate_204',
    'https://i.ytimg.com/generate_204',
    'https://www.youtube.com',
)
YOUTUBE_HEALTHCHECK_MIN_OK = 1
TELEGRAM_HEALTHCHECK_URLS = (
    'https://web.telegram.org/',
    'https://t.me/',
)
TELEGRAM_HEALTHCHECK_MIN_OK = 1


def initial_pool_probe_progress():
    return {
        'running': False,
        'checked': 0,
        'total': 0,
        'scope': '',
        'note': '',
        'started_at': 0,
        'finished_at': 0,
    }


class PoolProbeProgress:
    def __init__(self):
        self._lock = threading.Lock()
        self._progress = initial_pool_probe_progress()

    def update(self, **updates):
        with self._lock:
            self._progress.update(updates)

    def snapshot(self):
        with self._lock:
            return dict(self._progress)


def pool_probe_progress_label(progress):
    scope = (progress or {}).get('scope')
    if scope == 'manual_all':
        return 'Полная проверка всех ключей'
    if scope == 'protocol':
        return 'Проверка выбранного пула'
    return 'Фоновая проверка пула ключей'


def failed_custom_probe_results(custom_checks):
    return {check.get('id'): False for check in (custom_checks or []) if check.get('id')}


def available_memory_kb(meminfo_path='/proc/meminfo'):
    try:
        with open(meminfo_path, 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                if line.startswith('MemAvailable:'):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
    except Exception:
        pass
    return None


def pool_probe_timeout_budget(custom_checks, task_count, workers, timeouts):
    tg_connect, tg_read, http_connect, http_read, custom_connect, custom_read, single_timeout, batch_timeout = timeouts[:8]
    has_http_retry_timeouts = len(timeouts) > 9
    retry_http_connect = timeouts[8] if has_http_retry_timeouts else 0
    retry_http_read = timeouts[9] if has_http_retry_timeouts else 0
    custom_retry_budget = retry_http_connect + retry_http_read if has_http_retry_timeouts else 0
    custom_target_count = 0
    for check in custom_checks or []:
        targets = check.get('urls') if isinstance(check.get('urls'), list) else [check.get('url', '')]
        custom_target_count += len([target for target in targets[:2] if target])
    base_per_key = (
        tg_connect + tg_read +
        len(TELEGRAM_HEALTHCHECK_URLS) * (http_connect + http_read) +
        http_connect + http_read +
        retry_http_connect + retry_http_read +
        custom_target_count * (custom_connect + custom_read + custom_retry_budget)
    )
    retry_per_key = tg_connect + tg_read + retry_http_connect + retry_http_read
    per_key = max(single_timeout, base_per_key + retry_per_key + 5.0)
    workers = max(1, int(workers or 1))
    task_count = max(1, int(task_count or 1))
    waves = (task_count + workers - 1) // workers
    return max(batch_timeout, per_key * waves + 5.0)


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
                if not api_ok:
                    return True, 'Telegram app endpoints confirmed: ' + ', '.join(ok_hosts)
                return True, 'Telegram endpoints confirmed: ' + ', '.join(ok_hosts)
        else:
            failed.append(f'{host}: {message}')
    if not api_ok:
        return False, api_message
    return False, '; '.join(failed[-2:]) or 'Telegram web endpoints did not respond through this key.'


def check_youtube_through_proxy(
    check_http,
    proxy_url,
    *,
    urls=YOUTUBE_HEALTHCHECK_URLS,
    min_ok=YOUTUBE_HEALTHCHECK_MIN_OK,
    http_timeouts,
    http_retry_timeouts=None,
    retry_delay_seconds=0,
    sleep=time.sleep,
):
    retry_http_connect, retry_http_read = http_retry_timeouts or http_timeouts
    ok_hosts = []
    failed = []
    for index, url in enumerate(urls or YOUTUBE_HEALTHCHECK_URLS):
        connect_timeout, read_timeout = http_timeouts if index == 0 else (retry_http_connect, retry_http_read)
        ok, message = check_http(
            proxy_url,
            url=url,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )
        host = url.split('/')[2] if '://' in url else url
        if ok:
            ok_hosts.append(host)
            if len(ok_hosts) >= max(1, int(min_ok or 1)):
                return True, 'YouTube endpoints confirmed: ' + ', '.join(ok_hosts)
        else:
            failed.append(f'{host}: {message}')
            if retry_delay_seconds and index == 0:
                sleep(retry_delay_seconds)
    if ok_hosts and min_ok <= 1:
        return True, 'YouTube endpoint confirmed: ' + ', '.join(ok_hosts)
    return False, '; '.join(failed[-2:]) or 'YouTube endpoints did not respond through this key.'


def check_pool_key_through_proxy(
    proto,
    key_value,
    custom_checks,
    proxy_url,
    *,
    check_telegram_api,
    check_http,
    record_key_probe,
    probe_custom_targets,
    retry_delay_seconds,
    telegram_timeouts,
    http_timeouts,
    http_retry_timeouts=None,
    telegram_required=False,
    sleep=time.sleep,
):
    tg_connect, tg_read = telegram_timeouts
    http_connect, http_read = http_timeouts
    retry_http_connect, retry_http_read = http_retry_timeouts or http_timeouts
    tg_ok, _ = check_telegram_service_through_proxy(
        check_telegram_api,
        check_http,
        proxy_url,
        telegram_timeouts=(tg_connect, tg_read),
        http_timeouts=(http_connect, http_read),
    )
    yt_ok, _ = check_youtube_through_proxy(
        check_http,
        proxy_url,
        http_timeouts=(http_connect, http_read),
        http_retry_timeouts=(retry_http_connect, retry_http_read),
        retry_delay_seconds=retry_delay_seconds,
        sleep=sleep,
    )
    if not tg_ok and not yt_ok:
        sleep(retry_delay_seconds)
        tg_ok, _ = check_telegram_service_through_proxy(
            check_telegram_api,
            check_http,
            proxy_url,
            telegram_timeouts=(tg_connect, tg_read),
            http_timeouts=(retry_http_connect, retry_http_read),
        )
        yt_ok, _ = check_youtube_through_proxy(
            check_http,
            proxy_url,
            http_timeouts=(retry_http_connect, retry_http_read),
            http_retry_timeouts=(retry_http_connect, retry_http_read),
            retry_delay_seconds=retry_delay_seconds,
            sleep=sleep,
        )
    elif not tg_ok and telegram_required:
        sleep(retry_delay_seconds)
        tg_ok, _ = check_telegram_service_through_proxy(
            check_telegram_api,
            check_http,
            proxy_url,
            telegram_timeouts=(tg_connect, tg_read),
            http_timeouts=(retry_http_connect, retry_http_read),
        )
    elif not yt_ok:
        sleep(retry_delay_seconds)
        yt_ok, _ = check_youtube_through_proxy(
            check_http,
            proxy_url,
            http_timeouts=(retry_http_connect, retry_http_read),
            http_retry_timeouts=(retry_http_connect, retry_http_read),
            retry_delay_seconds=retry_delay_seconds,
            sleep=sleep,
        )

    record_tg_ok = tg_ok if (telegram_required or tg_ok or not yt_ok) else 'unknown'
    record_key_probe(proto, key_value, tg_ok=record_tg_ok, yt_ok=yt_ok)
    if custom_checks and not tg_ok and not yt_ok:
        record_key_probe(
            proto,
            key_value,
            custom=failed_custom_probe_results(custom_checks),
            custom_checks=custom_checks,
        )
        return
    if custom_checks:
        record_key_probe(
            proto,
            key_value,
            custom=probe_custom_targets(proxy_url, custom_checks=custom_checks),
            custom_checks=custom_checks,
        )


def select_pool_probe_tasks(tasks, *, protocol_order, custom_checks, cache, hash_key, is_fresh, max_keys=None, stale_only=False, now=None):
    now = time.time() if now is None else now
    selected = []
    seen = set()
    for proto, key_value in tasks:
        key_value = (key_value or '').strip()
        if proto not in protocol_order or not key_value:
            continue
        task_id = (proto, hash_key(key_value))
        if task_id in seen:
            continue
        seen.add(task_id)
        if stale_only and is_fresh(cache.get(hash_key(key_value)), now=now, custom_checks=custom_checks):
            continue
        selected.append((proto, key_value))
        if max_keys is not None and len(selected) >= max_keys:
            break
    return selected, custom_checks


def filter_active_probe_tasks(tasks, current_keys):
    return [
        (proto, key_value)
        for proto, key_value in (tasks or [])
        if key_value == (current_keys.get(proto) or '').strip()
    ]


def start_pool_probe_worker(
    probe_tasks,
    checks,
    *,
    scope,
    lock,
    set_progress,
    run_worker,
    invalidate_caches,
    cancel_event=None,
    time_provider=time.time,
    collect_garbage=gc.collect,
    thread_factory=threading.Thread,
):
    probe_tasks = list(probe_tasks or [])
    if not probe_tasks:
        return False, 0
    if not lock.acquire(blocking=False):
        return False, len(probe_tasks)
    if cancel_event is not None:
        cancel_event.clear()

    set_progress(
        running=True,
        checked=0,
        total=len(probe_tasks),
        scope=scope,
        note='',
        started_at=time_provider(),
        finished_at=0,
    )

    def worker():
        checked = 0
        total = len(probe_tasks)
        try:
            worker_kwargs = {
                'set_checked': lambda value: set_progress(checked=value),
                'invalidate_caches': invalidate_caches,
            }
            if cancel_event is not None:
                worker_kwargs['cancel_event'] = cancel_event
            checked, total = run_worker(probe_tasks, checks, **worker_kwargs)
        finally:
            invalidate_caches()
            set_progress(
                running=False,
                checked=checked,
                total=total,
                scope=scope,
                note='',
                finished_at=time_provider(),
            )
            lock.release()
            collect_garbage()

    thread_factory(target=worker, daemon=True).start()
    return True, len(probe_tasks)
