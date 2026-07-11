#!/usr/bin/python3
"""Disposable full-pool worker; deliberately independent from ``bot.py``."""

import json
import os
import sys
import threading
import time

try:
    import bot_config as config
except ImportError:
    class _DefaultConfig:
        pass

    config = _DefaultConfig()

try:
    # The worker keeps one timeout executor even for serial probing.  Match
    # the parent process instead of reserving the platform-default thread stack.
    threading.stack_size(128 * 1024)
except (ValueError, RuntimeError):
    pass

from custom_checks_store import normalize_check_url
from health_check_runner import _redact, _status_value
from pool_probe_curl import (
    check_custom_target_through_proxy as curl_check_custom_target,
    check_http_through_proxy as curl_check_http,
    check_telegram_api as curl_check_telegram,
    measure_download as curl_measure_download,
)
from pool_probe_controller import available_memory_kb, check_pool_key_through_proxy, failed_custom_probe_results, pool_probe_timeout_budget
from pool_probe_runner import (
    build_pool_probe_core_config_batch,
    cleanup_pool_probe_runtime,
    run_pool_probe_worker,
    start_pool_probe_xray,
    stop_pool_probe_xray,
)
from proxy_protocols import proxy_outbound_from_key
from proxy_status import (
    probe_custom_targets,
    wait_for_socks5_handshake,
)


def _read_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception:
        return default


def _write_json(path, value):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temporary = f'{path}.tmp.{os.getpid()}'
    try:
        with open(temporary, 'w', encoding='utf-8') as file:
            json.dump(value, file, ensure_ascii=False, separators=(',', ':'))
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass
        except Exception:
            pass


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except Exception:
        pass


class _FileCancelEvent:
    def __init__(self, path):
        self.path = path

    def is_set(self):
        return bool(self.path and os.path.exists(self.path))


class _WorkerProbeRecorder:
    """Append non-secret probe results for one parent-side cache write."""

    def __init__(self, task_key_ids, records_path):
        self._task_key_ids = dict(task_key_ids or {})
        self._records_path = str(records_path or '')
        self._file = None
        self._count = 0
        self._lock = threading.Lock()

    def _open(self):
        if self._file is not None:
            return self._file
        if not self._records_path:
            return None
        directory = os.path.dirname(self._records_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._file = open(self._records_path, 'a', encoding='utf-8')
        try:
            os.chmod(self._records_path, 0o600)
        except OSError:
            pass
        return self._file

    def record(
        self,
        proto,
        key_value,
        tg_ok=None,
        yt_ok=None,
        custom=None,
        custom_checks=None,
        timeout=False,
        timeout_reason='',
        **quality_kwargs,
    ):
        key_id = self._task_key_ids.get((str(proto or ''), str(key_value or '')))
        if not key_id:
            return
        values = {}
        if tg_ok is not None:
            values['tg_ok'] = tg_ok
        if yt_ok is not None:
            values['yt_ok'] = yt_ok
        if custom is not None:
            values['custom'] = custom
        if custom_checks is not None:
            values['custom_checks'] = custom_checks
        if timeout:
            values['timeout'] = True
            values['timeout_reason'] = str(timeout_reason or '')
        for name, value in quality_kwargs.items():
            if value is not None and value != '':
                values[name] = value
        if not values:
            return
        with self._lock:
            file = self._open()
            if file is None:
                return
            json.dump(
                {'key_id': str(key_id), 'proto': str(proto or ''), 'values': values},
                file,
                ensure_ascii=False,
                separators=(',', ':'),
            )
            file.write('\n')
            file.flush()
            self._count += 1

    def close(self):
        with self._lock:
            if self._file is not None:
                try:
                    self._file.close()
                finally:
                    self._file = None
            return self._records_path if self._count and os.path.exists(self._records_path) else ''


def _cancel_allows_resume(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as file:
            return 'no-resume' not in file.read(128)
    except Exception:
        return True


def _settings():
    minimum_available_kb = max(0, int(getattr(config, 'pool_probe_min_available_kb', 160000)))
    pause_available_kb = max(
        0,
        int(getattr(config, 'pool_probe_pause_available_kb', min(125000, minimum_available_kb))),
    )
    retry_connect = float(getattr(config, 'pool_probe_retry_connect_timeout', 6))
    retry_read = float(getattr(config, 'pool_probe_retry_read_timeout', 10))
    quality_bytes = max(0, int(getattr(config, 'pool_probe_quality_download_bytes', 524288)))
    quality_enabled = bool(getattr(config, 'pool_probe_quality_enabled', True)) and quality_bytes > 0
    return {
        'configured_batch_size': hasattr(config, 'pool_probe_batch_size'),
        'batch_size': max(1, int(getattr(config, 'pool_probe_batch_size', 1))),
        'concurrency': max(1, int(getattr(config, 'pool_probe_concurrency', 1))),
        'delay_seconds': max(0.0, float(getattr(config, 'pool_probe_delay_seconds', 3.0))),
        'min_available_kb': pause_available_kb,
        'slow_available_kb': max(
            minimum_available_kb,
            int(getattr(config, 'pool_probe_slow_available_kb', minimum_available_kb)),
        ),
        'slow_memory_delay_seconds': max(0.0, float(getattr(config, 'pool_probe_slow_memory_delay_seconds', 3.0))),
        'low_memory_delay_seconds': max(1.0, float(getattr(config, 'pool_probe_low_memory_delay_seconds', 12.0))),
        'max_low_memory_wait_seconds': max(0.0, float(getattr(config, 'pool_probe_low_memory_max_wait_seconds', 180.0))),
        'test_port': str(getattr(config, 'pool_probe_test_port', 10991)),
        'cpu_guard': bool(getattr(config, 'pool_probe_cpu_guard_enabled', True)),
        'max_cpu_percent': max(0.0, float(getattr(config, 'pool_probe_max_cpu_percent', 45.0))),
        'max_load1': max(0.0, float(getattr(config, 'pool_probe_max_load1', 2.0))),
        'high_cpu_delay_seconds': max(1.0, float(getattr(config, 'pool_probe_high_cpu_delay_seconds', 8.0))),
        'max_high_cpu_wait_seconds': max(0.0, float(getattr(config, 'pool_probe_high_cpu_max_wait_seconds', 120.0))),
        'high_load_delay_seconds': max(1.0, float(getattr(config, 'pool_probe_high_load_delay_seconds', 10.0))),
        'max_high_load_wait_seconds': max(0.0, float(getattr(config, 'pool_probe_high_load_max_wait_seconds', 120.0))),
        'tg_connect': float(getattr(config, 'pool_probe_tg_connect_timeout', 2)),
        'tg_read': float(getattr(config, 'pool_probe_tg_read_timeout', 3)),
        'http_connect': float(getattr(config, 'pool_probe_http_connect_timeout', 2)),
        'http_read': float(getattr(config, 'pool_probe_http_read_timeout', 3)),
        'custom_connect': float(getattr(config, 'pool_probe_custom_connect_timeout', 1.5)),
        'custom_read': float(getattr(config, 'pool_probe_custom_read_timeout', 2.5)),
        'retry_connect': retry_connect,
        'retry_read': retry_read,
        'retry_delay_seconds': max(0.0, float(getattr(config, 'pool_probe_retry_delay_seconds', 0.2))),
        'youtube_profile': str(getattr(config, 'pool_probe_youtube_profile', 'quick') or 'quick'),
        'quality_enabled': quality_enabled,
        'quality_url': str(getattr(config, 'pool_probe_quality_download_url', 'https://speed.cloudflare.com/__down?bytes={bytes}') or ''),
        'quality_bytes': quality_bytes,
        'quality_min_available_kb': max(0, int(getattr(config, 'pool_probe_quality_min_available_kb', minimum_available_kb))),
        'quality_max_samples': max(0, int(getattr(config, 'pool_probe_quality_max_samples_per_run', 6))),
        'quality_connect': float(getattr(config, 'pool_probe_quality_download_connect_timeout', retry_connect)),
        'quality_read': float(getattr(config, 'pool_probe_quality_download_read_timeout', min(12.0, max(4.0, retry_read)))),
        'quality_stable_latency_ms': max(1, int(getattr(config, 'pool_probe_quality_stable_latency_ms', 2500))),
        'quality_fast_latency_ms': max(1, int(getattr(config, 'pool_probe_quality_fast_latency_ms', 1500))),
        'quality_1600p_mbps': max(0.1, float(getattr(config, 'pool_probe_quality_1600p_min_mbps', 25.0))),
        'quality_4k_mbps': max(0.1, float(getattr(config, 'pool_probe_quality_4k_min_mbps', 45.0))),
    }


def _load_average():
    try:
        with open('/proc/loadavg', 'r', encoding='utf-8', errors='ignore') as file:
            return float(file.read().split()[0])
    except Exception:
        return None


def _cpu_busy_percent():
    try:
        with open('/proc/stat', 'r', encoding='utf-8', errors='ignore') as file:
            parts = file.readline().split()[1:]
        values = [int(value) for value in parts]
        total = sum(values)
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        time.sleep(0.35)
        with open('/proc/stat', 'r', encoding='utf-8', errors='ignore') as file:
            current = [int(value) for value in file.readline().split()[1:]]
        current_total = sum(current)
        current_idle = current[3] + (current[4] if len(current) > 4 else 0)
        delta_total = current_total - total
        return 0.0 if delta_total <= 0 else max(0.0, min(100.0, 100.0 * (1.0 - ((current_idle - idle) / delta_total))))
    except Exception:
        return None


def run_pool_probe_process_worker(input_path, progress_path, result_path, cancel_path):
    payload = _read_json(input_path, {})
    _remove(input_path)
    if not isinstance(payload, dict):
        payload = {}
    settings = _settings()
    tasks = []
    task_key_ids = {}
    task_hashes = {}
    raw_key_ids = list(payload.get('task_key_ids') or [])
    for index, item in enumerate(payload.get('tasks') or []):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        proto, key_value = str(item[0] or ''), str(item[1] or '')
        key_id = str(raw_key_ids[index] or '') if index < len(raw_key_ids) else ''
        tasks.append((proto, key_value))
        if key_id:
            task_key_ids[(proto, key_value)] = key_id
            task_hashes.setdefault(key_value, key_id)
    checks = [dict(item) for item in (payload.get('checks') or []) if isinstance(item, dict)]
    scope = str(payload.get('scope') or 'manual')
    initial_checked = max(0, int(payload.get('initial_checked') or 0))
    total = max(initial_checked + len(tasks), int(payload.get('total_count') or 0), len(tasks))
    started_at = float(payload.get('started_at') or time.time())
    progress = {'running': True, 'checked': initial_checked, 'total': total, 'scope': scope, 'note': '', 'started_at': started_at, 'finished_at': 0}
    _write_json(progress_path, progress)
    records_path = f'{result_path}.records'
    _remove(records_path)
    result = {'ok': False, 'checked': 0, 'absolute_checked': initial_checked, 'total': total, 'scope': scope, 'started_at': started_at, 'finished_at': 0, 'rss_before_kb': _status_value('VmRSS'), 'rss_after_kb': 0, 'hwm_kb': 0, 'cancelled': False, 'resume_allowed': True, 'remaining': [], 'probe_records_path': '', 'error': ''}
    recorder = _WorkerProbeRecorder(task_key_ids, records_path)
    quality_samples = {'count': 0}

    def write_progress(**updates):
        progress.update(updates)
        _write_json(progress_path, progress)

    def telegram_check(proxy_url, *, connect_timeout, read_timeout):
        return curl_check_telegram(bool(payload.get('telegram_authenticated')), proxy_url, connect_timeout, read_timeout)

    def custom_target(proxy_url, url, connect_timeout=2, read_timeout=3):
        return curl_check_custom_target(normalize_check_url, proxy_url, url, connect_timeout, read_timeout)

    def custom_probe(proxy_url, custom_checks=None):
        return probe_custom_targets(proxy_url, custom_checks or [], custom_target, connect_timeout=settings['custom_connect'], read_timeout=settings['custom_read'], retries=1, retry_connect_timeout=settings['retry_connect'], retry_read_timeout=settings['retry_read'], retry_delay_seconds=settings['retry_delay_seconds'])

    def measure_quality(proxy_url, **_kwargs):
        if not settings['quality_enabled'] or (settings['quality_min_available_kb'] and (available_memory_kb() or 0) < settings['quality_min_available_kb']):
            return None, ''
        if settings['quality_max_samples'] and quality_samples['count'] >= settings['quality_max_samples']:
            return None, ''
        quality_samples['count'] += 1
        return curl_measure_download(proxy_url, settings)

    def check_pool_key(proto, key_value, custom_checks, proxy_url, record_key_probe=None):
        quality_settings = {
            'enabled': settings['quality_enabled'], 'download_url': settings['quality_url'], 'download_bytes': settings['quality_bytes'],
            'download_connect_timeout': settings['quality_connect'], 'download_read_timeout': settings['quality_read'],
            'stable_latency_ms': settings['quality_stable_latency_ms'], 'fast_latency_ms': settings['quality_fast_latency_ms'],
            'min_1600p_mbps': settings['quality_1600p_mbps'], 'min_4k_mbps': settings['quality_4k_mbps'],
        }
        return check_pool_key_through_proxy(
            proto, key_value, custom_checks, proxy_url,
            check_telegram_api=telegram_check, check_http=curl_check_http, record_key_probe=record_key_probe or recorder.record,
            probe_custom_targets=custom_probe, retry_delay_seconds=settings['retry_delay_seconds'],
            telegram_timeouts=(settings['tg_connect'], settings['tg_read']), http_timeouts=(settings['http_connect'], settings['http_read']),
            http_retry_timeouts=(settings['retry_connect'], settings['retry_read']),
            telegram_required=str(proto or '') == str(payload.get('telegram_required_protocol') or ''),
            youtube_profile=settings['youtube_profile'], measure_download=measure_quality if settings['quality_enabled'] else None, quality_settings=quality_settings,
        )

    def timeout_budget(custom_checks, task_count=1, workers=1):
        single_timeout = max(8.0, settings['tg_connect'] + settings['tg_read'] + settings['http_connect'] + settings['http_read'] + settings['retry_connect'] + settings['retry_read'] + 3.0)
        return pool_probe_timeout_budget(custom_checks, task_count, workers, (settings['tg_connect'], settings['tg_read'], settings['http_connect'], settings['http_read'], settings['custom_connect'], settings['custom_read'], single_timeout, single_timeout + 5.0, settings['retry_connect'], settings['retry_read']), youtube_profile=settings['youtube_profile'])

    def task_hash(key_value):
        return task_hashes.get(str(key_value or ''), '')

    exit_code = 1
    try:
        batch_size = settings['batch_size']
        if not settings['configured_batch_size'] and (available_memory_kb() or 0) >= 200000:
            batch_size = min(2, max(1, len(tasks)))
        concurrency = max(1, min(settings['concurrency'], batch_size))
        checked, reported_total = run_pool_probe_worker(
            tasks, checks, batch_size=batch_size, concurrency=concurrency, delay_seconds=settings['delay_seconds'], min_available_kb=settings['min_available_kb'], test_port=settings['test_port'], available_memory_kb=available_memory_kb,
            log=lambda _message: None, proto_label=lambda proto: str(proto or ''), hash_key=task_hash, set_checked=lambda value: write_progress(checked=initial_checked + int(value or 0)), validate_outbound=lambda proto, key_value: proxy_outbound_from_key(proto, key_value, 'proxy-pool-probe-validate'), failed_custom_results=failed_custom_probe_results, record_key_probe=recorder.record,
            start_xray_for_batch=lambda valid_batch: start_pool_probe_xray(build_pool_probe_core_config_batch(valid_batch, settings['test_port'], proxy_outbound_from_key)), wait_for_socks5=wait_for_socks5_handshake, check_pool_key=check_pool_key, timeout_budget=timeout_budget, stop_xray=stop_pool_probe_xray, cleanup_runtime=cleanup_pool_probe_runtime, invalidate_caches=lambda: None, cancel_event=_FileCancelEvent(cancel_path), on_cancelled_remaining=lambda remaining: result.update(remaining=list(remaining or [])), set_note=lambda note: write_progress(note=str(note or '')), cpu_busy_percent=_cpu_busy_percent if settings['cpu_guard'] else None, max_cpu_percent=settings['max_cpu_percent'], high_cpu_delay_seconds=settings['high_cpu_delay_seconds'], max_high_cpu_wait_seconds=settings['max_high_cpu_wait_seconds'], load_average=_load_average, max_load1=settings['max_load1'], high_load_delay_seconds=settings['high_load_delay_seconds'], max_high_load_wait_seconds=settings['max_high_load_wait_seconds'], low_memory_delay_seconds=settings['low_memory_delay_seconds'], max_low_memory_wait_seconds=settings['max_low_memory_wait_seconds'], slow_available_kb=settings['slow_available_kb'], slow_memory_delay_seconds=settings['slow_memory_delay_seconds'], process_rss_kb=None, max_process_rss_kb=0, memory_cleanup=None,
        )
        result.update({'ok': True, 'checked': int(checked or 0), 'absolute_checked': initial_checked + int(checked or 0), 'total': max(total, int(reported_total or 0)), 'cancelled': _FileCancelEvent(cancel_path).is_set(), 'resume_allowed': _cancel_allows_resume(cancel_path)})
        exit_code = 0
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {_redact(exc)}'
    finally:
        cleanup_pool_probe_runtime(kill_processes=True)
        result['finished_at'] = time.time()
        result['rss_after_kb'] = _status_value('VmRSS')
        result['hwm_kb'] = _status_value('VmHWM')
        result['probe_records_path'] = recorder.close()
        write_progress(running=False, checked=int(result.get('absolute_checked') or initial_checked), total=int(result.get('total') or total), note=str(result.get('error') or progress.get('note') or ''), finished_at=result['finished_at'])
        try:
            _write_json(result_path, result)
        except Exception:
            pass
        _remove(cancel_path)
    return exit_code


_PROBE_RECORD_ALLOWED_FIELDS = frozenset((
    'tg_ok', 'yt_ok', 'custom', 'custom_checks', 'timeout', 'timeout_reason',
    'tg_latency_ms', 'yt_latency_ms', 'googlevideo_latency_ms', 'yt_home_ok',
    'yt_watch_ok', 'yt_short_ok', 'yt_bootstrap_ok', 'googlevideo_ok',
    'yt_error_rate', 'yt_last_error', 'yt_stability', 'yt_first_load_ms',
    'yt_throughput_mbps', 'yt_score', 'yt_quality', 'yt_stream_tier',
    'quality_error', 'stable_latency_ms', 'fast_latency_ms', 'min_1600p_mbps',
    'min_4k_mbps', 'allow_recent_success_downgrade',
))


def apply_pool_probe_records_file(path):
    """Apply streamed probe records outside the long-lived bot process."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return 0
    if size <= 0 or size > 4 * 1024 * 1024:
        return 0

    from probe_cache import load_key_probe_cache, save_key_probe_cache, update_key_probe_cache_entry

    cache = load_key_probe_cache()
    changed = False
    applied = 0
    now = time.time()
    try:
        with open(path, 'r', encoding='utf-8') as file:
            for index, line in enumerate(file):
                if index >= 4096:
                    break
                try:
                    record = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if not isinstance(record, dict):
                    continue
                key_id = str(record.get('key_id') or '')
                proto = str(record.get('proto') or '')
                values = record.get('values')
                if not key_id or not proto or not isinstance(values, dict):
                    continue
                updates = {
                    name: values[name]
                    for name in _PROBE_RECORD_ALLOWED_FIELDS
                    if name in values
                }
                if not updates:
                    continue
                changed = update_key_probe_cache_entry(
                    cache,
                    proto,
                    '',
                    key_id=key_id,
                    now=now,
                    min_write_interval=0,
                    **updates,
                ) or changed
                applied += 1
    except OSError:
        return 0
    if changed:
        save_key_probe_cache(cache)
    return applied


def run_pool_probe_records_apply_worker(records_path, result_path):
    result = {'ok': False, 'applied': 0, 'error': ''}
    exit_code = 1
    try:
        result['applied'] = apply_pool_probe_records_file(records_path)
        result['ok'] = True
        exit_code = 0
    except Exception as exc:
        result['error'] = type(exc).__name__
    finally:
        try:
            _write_json(result_path, result)
        except Exception:
            pass
    return exit_code


if __name__ == '__main__':
    sys.exit(run_pool_probe_process_worker(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]))
