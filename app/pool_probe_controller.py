import gc
import threading
import time

from youtube_healthcheck import (
    YOUTUBE_HEALTHCHECK_MIN_OK,
    YOUTUBE_HEALTHCHECK_REQUIRED_URLS,
    YOUTUBE_HEALTHCHECK_URLS,
    check_youtube_through_proxy,
    youtube_healthcheck_profile,
)
from telegram_healthcheck import (
    TELEGRAM_HEALTHCHECK_MIN_OK,
    TELEGRAM_HEALTHCHECK_URLS,
    check_telegram_service_through_proxy,
)

__all__ = (
    'YOUTUBE_HEALTHCHECK_MIN_OK',
    'YOUTUBE_HEALTHCHECK_REQUIRED_URLS',
    'YOUTUBE_HEALTHCHECK_URLS',
    'TELEGRAM_HEALTHCHECK_MIN_OK',
    'TELEGRAM_HEALTHCHECK_URLS',
    'initial_pool_probe_progress',
    'start_pool_probe_worker',
)


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


def pool_probe_timeout_budget(custom_checks, task_count, workers, timeouts, youtube_profile='quick'):
    tg_connect, tg_read, http_connect, http_read, custom_connect, custom_read, single_timeout, batch_timeout = timeouts[:8]
    has_http_retry_timeouts = len(timeouts) > 9
    retry_http_connect = timeouts[8] if has_http_retry_timeouts else 0
    retry_http_read = timeouts[9] if has_http_retry_timeouts else 0
    custom_retry_budget = retry_http_connect + retry_http_read if has_http_retry_timeouts else 0
    custom_target_count = 0
    for check in custom_checks or []:
        targets = check.get('urls') if isinstance(check.get('urls'), list) else [check.get('url', '')]
        custom_target_count += len([target for target in targets[:2] if target])
    youtube_urls, _youtube_min_ok, _youtube_max_failures = youtube_healthcheck_profile(youtube_profile)
    base_per_key = (
        tg_connect + tg_read +
        len(TELEGRAM_HEALTHCHECK_URLS) * (http_connect + http_read) +
        len(youtube_urls) * (http_connect + http_read) +
        custom_target_count * (custom_connect + custom_read + custom_retry_budget)
    )
    retry_per_key = tg_connect + tg_read + retry_http_connect + retry_http_read
    per_key = max(single_timeout, base_per_key + retry_per_key + 5.0)
    workers = max(1, int(workers or 1))
    task_count = max(1, int(task_count or 1))
    waves = (task_count + workers - 1) // workers
    return max(batch_timeout, per_key * waves + 5.0)


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
    youtube_profile='quick',
    measure_download=None,
    quality_settings=None,
    sleep=time.sleep,
):
    tg_connect, tg_read = telegram_timeouts
    http_connect, http_read = http_timeouts
    retry_http_connect, retry_http_read = http_retry_timeouts or http_timeouts
    quick_youtube_profile = str(youtube_profile or '').strip().lower() == 'quick'
    youtube_retry_timeouts = http_timeouts if quick_youtube_profile else (retry_http_connect, retry_http_read)
    tg_check_timeouts = (tg_connect, tg_read)
    tg_http_timeouts = (http_connect, http_read)
    tg_urls = TELEGRAM_HEALTHCHECK_URLS
    if quick_youtube_profile and not telegram_required:
        tg_check_timeouts = (min(tg_connect, 1.0), min(tg_read, 1.5))
        tg_http_timeouts = (min(http_connect, 1.0), min(http_read, 1.5))
        tg_urls = TELEGRAM_HEALTHCHECK_URLS[:1]
    quality_settings = quality_settings or {}
    collect_quality = bool(quality_settings.get('enabled') or measure_download)
    tg_metrics = {}
    yt_metrics = {}
    tg_ok, tg_message = check_telegram_service_through_proxy(
        check_telegram_api,
        check_http,
        proxy_url,
        telegram_timeouts=tg_check_timeouts,
        http_timeouts=tg_http_timeouts,
        urls=tg_urls,
        metrics=tg_metrics if collect_quality else None,
        allow_app_endpoints_without_api=False,
    )
    yt_ok, _ = check_youtube_through_proxy(
        check_http,
        proxy_url,
        http_timeouts=(http_connect, http_read),
        http_retry_timeouts=youtube_retry_timeouts,
        retry_delay_seconds=retry_delay_seconds,
        profile=youtube_profile,
        metrics=yt_metrics,
        sleep=sleep,
    )
    if not tg_ok and not yt_ok:
        sleep(retry_delay_seconds)
        if telegram_required:
            tg_ok, tg_message = check_telegram_service_through_proxy(
                check_telegram_api,
                check_http,
                proxy_url,
                telegram_timeouts=(tg_connect, tg_read),
                http_timeouts=(retry_http_connect, retry_http_read),
                metrics=tg_metrics if collect_quality else None,
                allow_app_endpoints_without_api=False,
            )
        if telegram_required or not quick_youtube_profile:
            yt_ok, _ = check_youtube_through_proxy(
                check_http,
                proxy_url,
                http_timeouts=youtube_retry_timeouts,
                http_retry_timeouts=youtube_retry_timeouts,
                retry_delay_seconds=retry_delay_seconds,
                profile=youtube_profile,
                metrics=yt_metrics,
                sleep=sleep,
            )
    elif not tg_ok and telegram_required:
        sleep(retry_delay_seconds)
        tg_ok, tg_message = check_telegram_service_through_proxy(
            check_telegram_api,
            check_http,
            proxy_url,
            telegram_timeouts=(tg_connect, tg_read),
            http_timeouts=(retry_http_connect, retry_http_read),
            metrics=tg_metrics if collect_quality else None,
            allow_app_endpoints_without_api=False,
        )
    elif not yt_ok and not quick_youtube_profile:
        sleep(retry_delay_seconds)
        yt_ok, _ = check_youtube_through_proxy(
            check_http,
            proxy_url,
            http_timeouts=youtube_retry_timeouts,
            http_retry_timeouts=youtube_retry_timeouts,
            retry_delay_seconds=retry_delay_seconds,
            profile=youtube_profile,
            metrics=yt_metrics,
            sleep=sleep,
        )

    quality_kwargs = {}
    if collect_quality:
        quality_kwargs.update(tg_metrics)
    quality_kwargs.update(yt_metrics)
    if yt_ok and measure_download and quality_settings.get('enabled', True):
        try:
            throughput_mbps, quality_error = measure_download(
                proxy_url,
                url=quality_settings.get('download_url', ''),
                bytes_limit=int(quality_settings.get('download_bytes') or 0),
                connect_timeout=float(quality_settings.get('download_connect_timeout') or retry_http_connect),
                read_timeout=float(quality_settings.get('download_read_timeout') or retry_http_read),
            )
            if throughput_mbps is not None:
                quality_kwargs['yt_throughput_mbps'] = throughput_mbps
            elif quality_error:
                quality_kwargs['quality_error'] = str(quality_error)
        except Exception as exc:
            quality_kwargs['quality_error'] = str(exc).splitlines()[0][:180]
    for key in ('stable_latency_ms', 'fast_latency_ms', 'min_1600p_mbps', 'min_4k_mbps'):
        if key in quality_settings:
            quality_kwargs[key] = quality_settings[key]
    record_key_probe(
        proto,
        key_value,
        tg_ok=tg_ok,
        yt_ok=yt_ok,
        allow_recent_success_downgrade=True,
        **quality_kwargs,
    )
    if custom_checks and not tg_ok and not yt_ok:
        record_key_probe(
            proto,
            key_value,
            custom=failed_custom_probe_results(custom_checks),
            custom_checks=custom_checks,
            allow_recent_success_downgrade=True,
        )
        return
    if custom_checks:
        record_key_probe(
            proto,
            key_value,
            custom=probe_custom_targets(proxy_url, custom_checks=custom_checks),
            custom_checks=custom_checks,
            allow_recent_success_downgrade=True,
        )


def select_pool_probe_tasks(tasks, *, protocol_order, custom_checks, cache, hash_key, is_fresh, max_keys=None, stale_only=False, now=None):
    now = time.time() if now is None else now
    selected = []
    seen_keys = set()
    for proto, key_value in tasks:
        key_value = (key_value or '').strip()
        if proto not in protocol_order or not key_value:
            continue
        key_id = hash_key(key_value)
        if key_id in seen_keys:
            continue
        seen_keys.add(key_id)
        if stale_only and is_fresh(cache.get(key_id), now=now, custom_checks=custom_checks):
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
    initial_checked=0,
    total_count=None,
    started_at=None,
):
    probe_tasks = list(probe_tasks or [])
    if not probe_tasks:
        return False, 0
    queued_count = len(probe_tasks)
    if not lock.acquire(blocking=False):
        return False, queued_count
    if cancel_event is not None:
        cancel_event.clear()

    initial_checked = max(0, int(initial_checked or 0))
    total_count = len(probe_tasks) if total_count is None else max(initial_checked, int(total_count or 0))
    started_at = time_provider() if started_at is None else started_at
    set_progress(
        running=True,
        checked=initial_checked,
        total=total_count,
        scope=scope,
        note='',
        started_at=started_at,
        finished_at=0,
    )

    def worker():
        checked = 0
        total = len(probe_tasks)
        try:
            worker_kwargs = {
                'set_checked': lambda value: set_progress(checked=initial_checked + value),
                'invalidate_caches': invalidate_caches,
            }
            if cancel_event is not None:
                worker_kwargs['cancel_event'] = cancel_event
            checked, total = run_worker(probe_tasks, checks, **worker_kwargs)
        finally:
            invalidate_caches()
            set_progress(
                running=False,
                checked=initial_checked + checked,
                total=total_count,
                scope=scope,
                note='',
                finished_at=time_provider(),
            )
            try:
                probe_tasks.clear()
            except Exception:
                pass
            lock.release()
            collect_garbage()

    try:
        thread_factory(target=worker, daemon=True).start()
    except Exception:
        invalidate_caches()
        set_progress(
            running=False,
            checked=initial_checked,
            total=total_count,
            scope=scope,
            note='Не удалось запустить проверку пула.',
            finished_at=time_provider(),
        )
        try:
            probe_tasks.clear()
        except Exception:
            pass
        lock.release()
        collect_garbage()
        return False, queued_count
    return True, queued_count
