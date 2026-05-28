import hashlib
import json
import os
import threading
import time


KEY_PROBE_CACHE_PATH = '/opt/etc/bot/key_probe_cache.json'
KEY_PROBE_CACHE_TTL = 3600
KEY_PROBE_FAILURE_TTL = 300
KEY_PROBE_MIN_WRITE_INTERVAL = 30
KEY_PROBE_CACHE_SCHEMA_VERSION = 6
KEY_PROBE_SUCCESS_DOWNGRADE_GRACE = 300

_cache_lock = threading.Lock()


def hash_key(value):
    return hashlib.sha1((value or '').encode('utf-8', errors='ignore')).hexdigest()


def load_key_probe_cache():
    try:
        with open(KEY_PROBE_CACHE_PATH, 'r', encoding='utf-8') as file:
            value = json.load(file)
        if not isinstance(value, dict):
            return {}
        return {
            key: entry
            for key, entry in value.items()
            if isinstance(entry, dict) and entry.get('schema') == KEY_PROBE_CACHE_SCHEMA_VERSION
        }
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
    return None if value == 'unknown' else bool(value)


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
    if tg_ok is not None:
        value = _stored_probe_value(tg_ok)
        if _skip_recent_success_downgrade(entry, 'tg_ok', value, now, previous_ts):
            skipped_downgrade = True
        elif entry.get('tg_ok') is not value:
            entry['tg_ok'] = value
            changed = True
    if yt_ok is not None:
        value = _stored_probe_value(yt_ok)
        if _skip_recent_success_downgrade(entry, 'yt_ok', value, now, previous_ts):
            skipped_downgrade = True
        elif entry.get('yt_ok') is not value:
            entry['yt_ok'] = value
            changed = True
    if custom is not None:
        existing_custom = entry.get('custom', {})
        if not isinstance(existing_custom, dict):
            existing_custom = {}
        else:
            existing_custom = dict(existing_custom)
        for check_id, ok in (custom or {}).items():
            check_key = str(check_id)
            value = bool(ok)
            if (
                value is False and
                previous_ts and
                now - previous_ts < KEY_PROBE_SUCCESS_DOWNGRADE_GRACE and
                existing_custom.get(check_key) is True
            ):
                skipped_downgrade = True
                continue
            if existing_custom.get(check_key) is not value:
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

    def record(self, proto, key_value, tg_ok=None, yt_ok=None, custom=None, custom_checks=None):
        should_flush = False
        with self._lock:
            self._pending.append((proto, key_value, tg_ok, yt_ok, custom, custom_checks, time.time()))
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
            for proto, key_value, tg_ok, yt_ok, custom, custom_checks, ts in pending:
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
    if (
        age >= KEY_PROBE_FAILURE_TTL and
        (
            entry.get('tg_ok') is False or
            entry.get('yt_ok') is False or
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
    if 'tg_ok' not in entry or 'yt_ok' not in entry:
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
