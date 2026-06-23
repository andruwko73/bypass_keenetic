import hashlib
import json
import os
import threading
import time


KEY_PROBE_CACHE_PATH = '/opt/etc/bot/key_probe_cache.json'
KEY_PROBE_CACHE_TTL = 3600
KEY_PROBE_FAILURE_TTL = 300
KEY_PROBE_MIN_WRITE_INTERVAL = 30
KEY_PROBE_CACHE_SCHEMA_VERSION = 8
KEY_PROBE_COMPAT_SCHEMA_VERSIONS = (6, 7, 8)
KEY_PROBE_SUCCESS_DOWNGRADE_GRACE = 300
KEY_PROBE_ERROR_TEXT_MAX_CHARS = 120
YOUTUBE_QUALITY_STABLE = 'stable'
YOUTUBE_QUALITY_FAST = 'fast'
YOUTUBE_QUALITY_DEFAULT_STABLE_LATENCY_MS = 2500
YOUTUBE_QUALITY_DEFAULT_FAST_LATENCY_MS = 1500
YOUTUBE_QUALITY_DEFAULT_1600P_MBPS = 25.0
YOUTUBE_QUALITY_DEFAULT_4K_MBPS = 45.0

_cache_lock = threading.Lock()


def hash_key(value):
    return hashlib.sha1((value or '').encode('utf-8', errors='ignore')).hexdigest()


def load_key_probe_cache():
    try:
        with open(KEY_PROBE_CACHE_PATH, 'r', encoding='utf-8') as file:
            value = json.load(file)
        if not isinstance(value, dict):
            return {}
        result = {}
        for key, entry in value.items():
            if not isinstance(entry, dict) or entry.get('schema') not in KEY_PROBE_COMPAT_SCHEMA_VERSIONS:
                continue
            normalized = dict(entry)
            normalized['schema'] = KEY_PROBE_CACHE_SCHEMA_VERSION
            result[key] = normalized
        return result
    except Exception:
        return {}


def save_key_probe_cache(cache):
    os.makedirs(os.path.dirname(KEY_PROBE_CACHE_PATH), exist_ok=True)
    tmp_path = f'{KEY_PROBE_CACHE_PATH}.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as file:
        json.dump(cache, file, ensure_ascii=False, separators=(',', ':'))
        file.flush()
        try:
            os.fsync(file.fileno())
        except Exception:
            pass
    os.replace(tmp_path, KEY_PROBE_CACHE_PATH)


def _stored_probe_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    text = str(value).strip().casefold()
    if text in ('', 'unknown', 'none', 'null'):
        return None
    if text in ('1', 'true', 'yes', 'y', 'ok', 'success', 'passed', 'stable'):
        return True
    if text in ('0', 'false', 'no', 'n', 'fail', 'failed', 'error', 'unstable'):
        return False
    return None


def _stored_float(value, digits=2):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0:
        return None
    return round(numeric, int(digits))


def _stored_int(value):
    numeric = _stored_float(value, digits=0)
    if numeric is None:
        return None
    return int(round(numeric))


def _stored_error_text(value, fallback='', max_chars=KEY_PROBE_ERROR_TEXT_MAX_CHARS):
    text = str(value or '').strip() or str(fallback or '').strip()
    if not text:
        return ''
    text = ' '.join(text.split())
    return text[:max(1, int(max_chars or KEY_PROBE_ERROR_TEXT_MAX_CHARS))]


def youtube_quality_score(
    *,
    yt_ok=None,
    yt_latency_ms=None,
    googlevideo_latency_ms=None,
    googlevideo_ok=None,
    yt_error_rate=None,
    yt_stability='',
    yt_throughput_mbps=None,
    stable_latency_ms=YOUTUBE_QUALITY_DEFAULT_STABLE_LATENCY_MS,
    fast_latency_ms=YOUTUBE_QUALITY_DEFAULT_FAST_LATENCY_MS,
    min_1600p_mbps=YOUTUBE_QUALITY_DEFAULT_1600P_MBPS,
    min_4k_mbps=YOUTUBE_QUALITY_DEFAULT_4K_MBPS,
):
    if yt_ok is not True:
        return {'yt_score': 0 if yt_ok is False else 20, 'yt_quality': '', 'yt_stream_tier': ''}
    stability = str(yt_stability or '').strip().lower()
    if stability == 'fail' or (googlevideo_ok is False and stability != 'unstable'):
        return {'yt_score': 0, 'yt_quality': '', 'yt_stream_tier': ''}

    stable_latency_ms = max(1, _stored_int(stable_latency_ms) or YOUTUBE_QUALITY_DEFAULT_STABLE_LATENCY_MS)
    fast_latency_ms = max(1, _stored_int(fast_latency_ms) or YOUTUBE_QUALITY_DEFAULT_FAST_LATENCY_MS)
    min_1600p_mbps = max(0.1, _stored_float(min_1600p_mbps) or YOUTUBE_QUALITY_DEFAULT_1600P_MBPS)
    min_4k_mbps = max(min_1600p_mbps, _stored_float(min_4k_mbps) or YOUTUBE_QUALITY_DEFAULT_4K_MBPS)
    error_rate = _stored_float(yt_error_rate, digits=3) or 0.0

    latencies = [
        value for value in (
            _stored_int(yt_latency_ms),
            _stored_int(googlevideo_latency_ms),
        )
        if value is not None
    ]
    max_latency = max(latencies) if latencies else None
    throughput = _stored_float(yt_throughput_mbps)

    score = 45
    if max_latency is None:
        score += 5
    elif max_latency <= fast_latency_ms:
        score += 25
    elif max_latency <= stable_latency_ms:
        score += 17
    else:
        score += max(0, 12 - int((max_latency - stable_latency_ms) / 500.0))

    stream_tier = ''
    if throughput is None:
        score += 5
    elif throughput >= min_4k_mbps:
        score += 30
        stream_tier = '4k'
    elif throughput >= min_1600p_mbps:
        score += 22
        stream_tier = '1600p'
    else:
        score += max(0, int((throughput / min_1600p_mbps) * 16))

    score = max(0, min(100, int(round(score))))
    quality = ''
    latency_is_fast = max_latency is None or max_latency <= fast_latency_ms
    latency_is_stable = max_latency is None or max_latency <= stable_latency_ms
    if throughput is not None:
        if throughput >= min_4k_mbps and latency_is_fast:
            quality = YOUTUBE_QUALITY_FAST
        elif throughput >= min_1600p_mbps and latency_is_stable:
            quality = YOUTUBE_QUALITY_STABLE
    if stability == 'unstable':
        score = max(0, min(55, score - max(18, int(round(error_rate * 100)))))
        quality = ''
    elif error_rate > 0:
        score = max(0, score - min(10, int(round(error_rate * 40))))
    return {'yt_score': score, 'yt_quality': quality, 'yt_stream_tier': stream_tier}


def youtube_probe_state(entry):
    if not isinstance(entry, dict):
        return 'unknown'
    stability = str(entry.get('yt_stability') or '').strip().lower()
    if entry.get('yt_ok') is True:
        return 'warn' if stability == 'unstable' else 'ok'
    if stability == 'unstable':
        return 'warn'
    if entry.get('yt_ok') is False:
        return 'fail'
    return 'unknown'


def youtube_probe_effective_ok(entry):
    return youtube_probe_state(entry) in ('ok', 'warn')


def _set_entry_metric(entry, key, value, *, digits=2):
    stored = _stored_int(value) if digits == 0 else _stored_float(value, digits=digits)
    if stored is None:
        return False
    if entry.get(key) != stored:
        entry[key] = stored
        return True
    return False


def custom_checks_signature(custom_checks):
    normalized = []
    for check in custom_checks or []:
        if not isinstance(check, dict):
            continue
        check_id = str(check.get('id') or '').strip()
        if not check_id:
            continue
        raw_urls = check.get('urls') if isinstance(check.get('urls'), list) else [check.get('url', '')]
        urls = [str(url or '').strip() for url in raw_urls if str(url or '').strip()]
        normalized.append((check_id, tuple(urls)))
    payload = json.dumps(normalized, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha1(payload.encode('utf-8', errors='ignore')).hexdigest()


def _entry_timestamp(entry):
    try:
        return float((entry or {}).get('ts', 0))
    except (TypeError, ValueError):
        return 0


def _skip_recent_success_downgrade(entry, field, value, now, previous_ts):
    return (
        value is False and
        previous_ts and
        now - previous_ts < KEY_PROBE_SUCCESS_DOWNGRADE_GRACE and
        entry.get(field) is True
    )


def update_key_probe_cache_entry(
    cache,
    proto,
    key_value,
    tg_ok=None,
    yt_ok=None,
    custom=None,
    *,
    now=None,
    min_write_interval=0,
    custom_checks=None,
    timeout=False,
    timeout_reason='',
    tg_latency_ms=None,
    yt_latency_ms=None,
    googlevideo_latency_ms=None,
    yt_home_ok=None,
    yt_watch_ok=None,
    yt_short_ok=None,
    yt_bootstrap_ok=None,
    googlevideo_ok=None,
    yt_error_rate=None,
    yt_last_error='',
    yt_stability=None,
    yt_first_load_ms=None,
    yt_throughput_mbps=None,
    yt_score=None,
    yt_quality=None,
    yt_stream_tier=None,
    quality_error='',
    stable_latency_ms=YOUTUBE_QUALITY_DEFAULT_STABLE_LATENCY_MS,
    fast_latency_ms=YOUTUBE_QUALITY_DEFAULT_FAST_LATENCY_MS,
    min_1600p_mbps=YOUTUBE_QUALITY_DEFAULT_1600P_MBPS,
    min_4k_mbps=YOUTUBE_QUALITY_DEFAULT_4K_MBPS,
    allow_recent_success_downgrade=False,
):
    cache = cache if isinstance(cache, dict) else {}
    key_id = hash_key(key_value)
    entry = cache.get(key_id, {})
    if not isinstance(entry, dict):
        entry = {}
    else:
        entry = dict(entry)

    now = time.time() if now is None else now
    previous_ts = _entry_timestamp(entry)
    if previous_ts and now < previous_ts:
        return False
    changed = False
    skipped_downgrade = False
    if entry.get('schema') != KEY_PROBE_CACHE_SCHEMA_VERSION:
        entry['schema'] = KEY_PROBE_CACHE_SCHEMA_VERSION
        changed = True
    if entry.get('proto') != proto:
        entry['proto'] = proto
        changed = True
    has_probe_value = (
        tg_ok is not None or yt_ok is not None or custom is not None or
        tg_latency_ms is not None or yt_latency_ms is not None or
        googlevideo_latency_ms is not None or yt_throughput_mbps is not None or
        yt_home_ok is not None or yt_watch_ok is not None or yt_short_ok is not None or
        yt_bootstrap_ok is not None or googlevideo_ok is not None or
        yt_error_rate is not None or bool(yt_last_error) or yt_stability is not None or
        yt_first_load_ms is not None or
        yt_score is not None or yt_quality is not None or yt_stream_tier is not None or
        bool(quality_error)
    )
    timeout = bool(timeout)
    if timeout:
        reason = _stored_error_text(timeout_reason, fallback='timeout')
        if entry.get('timeout') is not True:
            entry['timeout'] = True
            changed = True
        if entry.get('timeout_reason') != reason:
            entry['timeout_reason'] = reason
            changed = True
    elif has_probe_value:
        for marker in ('timeout', 'timeout_reason'):
            if marker in entry:
                entry.pop(marker, None)
                changed = True

    if tg_ok is not None:
        value = _stored_probe_value(tg_ok)
        if (
            not allow_recent_success_downgrade and
            _skip_recent_success_downgrade(entry, 'tg_ok', value, now, previous_ts)
        ):
            skipped_downgrade = True
        elif 'tg_ok' not in entry or entry.get('tg_ok') is not value:
            entry['tg_ok'] = value
            changed = True
        if value is not True and tg_latency_ms is None and 'tg_latency_ms' in entry:
            entry.pop('tg_latency_ms', None)
            changed = True
    if yt_ok is not None:
        value = _stored_probe_value(yt_ok)
        if (
            not allow_recent_success_downgrade and
            _skip_recent_success_downgrade(entry, 'yt_ok', value, now, previous_ts)
        ):
            skipped_downgrade = True
        elif 'yt_ok' not in entry or entry.get('yt_ok') is not value:
            entry['yt_ok'] = value
            changed = True
    allow_quality_update = not (skipped_downgrade and yt_ok is False)
    if allow_quality_update:
        changed = _set_entry_metric(entry, 'tg_latency_ms', tg_latency_ms, digits=0) or changed
        changed = _set_entry_metric(entry, 'yt_latency_ms', yt_latency_ms, digits=0) or changed
        changed = _set_entry_metric(entry, 'googlevideo_latency_ms', googlevideo_latency_ms, digits=0) or changed
        changed = _set_entry_metric(entry, 'yt_first_load_ms', yt_first_load_ms, digits=0) or changed
        changed = _set_entry_metric(entry, 'yt_error_rate', yt_error_rate, digits=3) or changed
        for field_name, field_value in (
            ('yt_home_ok', yt_home_ok),
            ('yt_watch_ok', yt_watch_ok),
            ('yt_short_ok', yt_short_ok),
            ('yt_bootstrap_ok', yt_bootstrap_ok),
            ('googlevideo_ok', googlevideo_ok),
        ):
            if field_value is not None:
                value = _stored_probe_value(field_value)
                if entry.get(field_name) is not value:
                    entry[field_name] = value
                    changed = True
        if yt_stability is not None:
            stability_value = str(yt_stability or '').strip().lower()
            if stability_value not in ('stable', 'unstable', 'fail'):
                stability_value = ''
            if entry.get('yt_stability', '') != stability_value:
                if stability_value:
                    entry['yt_stability'] = stability_value
                else:
                    entry.pop('yt_stability', None)
                changed = True
        if yt_last_error:
            error_value = _stored_error_text(yt_last_error)
            if entry.get('yt_last_error') != error_value:
                entry['yt_last_error'] = error_value
                changed = True
        elif has_probe_value and entry.get('yt_last_error') and yt_ok is True:
            entry.pop('yt_last_error', None)
            changed = True
        throughput_measured = yt_throughput_mbps is not None
        changed = _set_entry_metric(entry, 'yt_throughput_mbps', yt_throughput_mbps, digits=2) or changed
        if throughput_measured and entry.get('yt_throughput_ts') != now:
            entry['yt_throughput_ts'] = now
            changed = True
        if (
            not throughput_measured and
            (yt_ok is not None or yt_latency_ms is not None or googlevideo_latency_ms is not None or quality_error) and
            yt_score is None and yt_quality is None and yt_stream_tier is None
        ):
            for marker in ('yt_throughput_mbps', 'yt_throughput_ts', 'yt_quality', 'yt_stream_tier'):
                if marker in entry:
                    entry.pop(marker, None)
                    changed = True
        if (
            yt_score is None and yt_quality is None and yt_stream_tier is None and
            (
                yt_ok is not None or yt_latency_ms is not None or googlevideo_latency_ms is not None or
                yt_throughput_mbps is not None or yt_error_rate is not None or yt_stability is not None or
                googlevideo_ok is not None
            )
        ):
            inferred = youtube_quality_score(
                yt_ok=entry.get('yt_ok') if yt_ok is None else _stored_probe_value(yt_ok),
                yt_latency_ms=entry.get('yt_latency_ms'),
                googlevideo_latency_ms=entry.get('googlevideo_latency_ms'),
                googlevideo_ok=entry.get('googlevideo_ok'),
                yt_error_rate=entry.get('yt_error_rate'),
                yt_stability=entry.get('yt_stability'),
                yt_throughput_mbps=entry.get('yt_throughput_mbps'),
                stable_latency_ms=stable_latency_ms,
                fast_latency_ms=fast_latency_ms,
                min_1600p_mbps=min_1600p_mbps,
                min_4k_mbps=min_4k_mbps,
            )
            yt_score = inferred.get('yt_score')
            yt_quality = inferred.get('yt_quality')
            yt_stream_tier = inferred.get('yt_stream_tier')
        score_value = _stored_int(yt_score)
        if score_value is not None:
            score_value = max(0, min(100, score_value))
            if entry.get('yt_score') != score_value:
                entry['yt_score'] = score_value
                changed = True
        if yt_quality is not None:
            quality_value = str(yt_quality or '').strip().lower()
            if quality_value not in (YOUTUBE_QUALITY_STABLE, YOUTUBE_QUALITY_FAST):
                quality_value = ''
            if entry.get('yt_quality', '') != quality_value:
                if quality_value:
                    entry['yt_quality'] = quality_value
                else:
                    entry.pop('yt_quality', None)
                changed = True
        if yt_stream_tier is not None:
            tier_value = str(yt_stream_tier or '').strip().lower()
            if tier_value not in ('1600p', '4k'):
                tier_value = ''
            if entry.get('yt_stream_tier', '') != tier_value:
                if tier_value:
                    entry['yt_stream_tier'] = tier_value
                else:
                    entry.pop('yt_stream_tier', None)
                changed = True
        if quality_error:
            error_value = _stored_error_text(quality_error)
            if entry.get('quality_error') != error_value:
                entry['quality_error'] = error_value
                changed = True
        elif has_probe_value and entry.get('quality_error'):
            entry.pop('quality_error', None)
            changed = True
    if custom is not None:
        existing_custom = entry.get('custom', {})
        if not isinstance(existing_custom, dict):
            existing_custom = {}
        else:
            existing_custom = dict(existing_custom)
        for check_id, ok in (custom or {}).items():
            check_key = str(check_id)
            value = _stored_probe_value(ok)
            if (
                not allow_recent_success_downgrade and
                value is False and
                previous_ts and
                now - previous_ts < KEY_PROBE_SUCCESS_DOWNGRADE_GRACE and
                existing_custom.get(check_key) is True
            ):
                skipped_downgrade = True
                continue
            if check_key not in existing_custom or existing_custom.get(check_key) is not value:
                existing_custom[check_key] = value
                changed = True
        if entry.get('custom') != existing_custom:
            entry['custom'] = existing_custom
            changed = True
        if custom_checks is not None:
            signature = custom_checks_signature(custom_checks)
            if entry.get('custom_sig') != signature:
                entry['custom_sig'] = signature
                changed = True

    if (not skipped_downgrade or changed) and (
        changed or not previous_ts or now - previous_ts >= float(min_write_interval or 0)
    ):
        entry['ts'] = now
        changed = True

    if changed:
        cache[key_id] = entry
    return changed


class KeyProbeBatchRecorder:
    def __init__(self, *, flush_every=5, flush_interval=2.0):
        self.flush_every = max(1, int(flush_every or 1))
        self.flush_interval = max(0.1, float(flush_interval or 0.1))
        self._pending = []
        self._last_flush = time.time()
        self._lock = threading.Lock()

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
        should_flush = False
        with self._lock:
            self._pending.append((
                proto,
                key_value,
                tg_ok,
                yt_ok,
                custom,
                custom_checks,
                bool(timeout),
                timeout_reason,
                dict(quality_kwargs),
                time.time(),
            ))
            if len(self._pending) >= self.flush_every or time.time() - self._last_flush >= self.flush_interval:
                should_flush = True
        if should_flush:
            self.flush()

    def flush(self):
        with self._lock:
            pending = self._pending
            self._pending = []
            self._last_flush = time.time()
        if not pending:
            return False
        with _cache_lock:
            cache = load_key_probe_cache()
            changed = False
            for proto, key_value, tg_ok, yt_ok, custom, custom_checks, timeout, timeout_reason, quality_kwargs, ts in pending:
                changed = update_key_probe_cache_entry(
                    cache,
                    proto,
                    key_value,
                    tg_ok=tg_ok,
                    yt_ok=yt_ok,
                    custom=custom,
                    now=ts,
                    min_write_interval=0,
                    custom_checks=custom_checks,
                    timeout=timeout,
                    timeout_reason=timeout_reason,
                    **(quality_kwargs or {}),
                ) or changed
            if changed:
                save_key_probe_cache(cache)
        return True


def forget_key_probes(key_values):
    removed = 0
    with _cache_lock:
        cache = load_key_probe_cache()
        for key_value in key_values or []:
            key_id = hash_key(key_value)
            if key_id in cache:
                removed += 1
                cache.pop(key_id, None)
        if removed:
            save_key_probe_cache(cache)
    return removed


def record_key_probe(
    proto,
    key_value,
    tg_ok=None,
    yt_ok=None,
    custom=None,
    *,
    min_write_interval=KEY_PROBE_MIN_WRITE_INTERVAL,
    custom_checks=None,
    timeout=False,
    timeout_reason='',
    allow_recent_success_downgrade=False,
    **quality_kwargs,
):
    with _cache_lock:
        cache = load_key_probe_cache()
        if update_key_probe_cache_entry(
            cache,
            proto,
            key_value,
            tg_ok=tg_ok,
            yt_ok=yt_ok,
            custom=custom,
            min_write_interval=min_write_interval,
            custom_checks=custom_checks,
            timeout=timeout,
            timeout_reason=timeout_reason,
            allow_recent_success_downgrade=allow_recent_success_downgrade,
            **quality_kwargs,
        ):
            save_key_probe_cache(cache)


def key_probe_is_fresh(entry, now=None, custom_checks=None):
    if not isinstance(entry, dict):
        return False
    if entry.get('schema') != KEY_PROBE_CACHE_SCHEMA_VERSION:
        return False
    try:
        ts = float(entry.get('ts', 0))
    except (TypeError, ValueError):
        return False
    age = (now or time.time()) - ts
    if age >= KEY_PROBE_CACHE_TTL:
        return False
    if entry.get('timeout'):
        return False
    if (
        age >= KEY_PROBE_FAILURE_TTL and
        (
            entry.get('tg_ok') is False or
            youtube_probe_state(entry) == 'fail' or
            any(value is False for value in (entry.get('custom') or {}).values())
        )
    ):
        return False
    custom_checks = custom_checks or []
    if custom_checks:
        custom = entry.get('custom', {})
        if not isinstance(custom, dict):
            return False
        if entry.get('custom_sig') != custom_checks_signature(custom_checks):
            return False
        return all(check.get('id') in custom for check in custom_checks)
    return True


def key_probe_has_required_results(entry, custom_checks=None):
    if not isinstance(entry, dict):
        return False
    if entry.get('schema') != KEY_PROBE_CACHE_SCHEMA_VERSION:
        return False
    if entry.get('timeout'):
        return False
    if not isinstance(entry.get('tg_ok'), bool) or not isinstance(entry.get('yt_ok'), bool):
        return False
    custom_checks = custom_checks or []
    if custom_checks:
        custom = entry.get('custom', {})
        if not isinstance(custom, dict):
            return False
        if entry.get('custom_sig') != custom_checks_signature(custom_checks):
            return False
        return all(isinstance(custom.get(check.get('id')), bool) for check in custom_checks)
    return True
