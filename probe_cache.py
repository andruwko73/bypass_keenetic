import hashlib
import json
import os
import threading
import time


KEY_PROBE_CACHE_PATH = '/opt/etc/bot/key_probe_cache.json'
KEY_PROBE_CACHE_TTL = 3600

_cache_lock = threading.Lock()


def hash_key(value):
    return hashlib.sha1((value or '').encode('utf-8', errors='ignore')).hexdigest()


def load_key_probe_cache():
    try:
        with open(KEY_PROBE_CACHE_PATH, 'r', encoding='utf-8') as file:
            value = json.load(file)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def save_key_probe_cache(cache):
    os.makedirs(os.path.dirname(KEY_PROBE_CACHE_PATH), exist_ok=True)
    tmp_path = f'{KEY_PROBE_CACHE_PATH}.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as file:
        json.dump(cache, file, ensure_ascii=False, indent=2)
        file.flush()
        try:
            os.fsync(file.fileno())
        except Exception:
            pass
    os.replace(tmp_path, KEY_PROBE_CACHE_PATH)


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


def record_key_probe(proto, key_value, tg_ok=None, yt_ok=None, custom=None):
    with _cache_lock:
        cache = load_key_probe_cache()
        key_id = hash_key(key_value)
        entry = cache.get(key_id, {})
        if not isinstance(entry, dict):
            entry = {}
        entry['proto'] = proto
        entry['ts'] = time.time()
        if tg_ok is not None:
            entry['tg_ok'] = None if tg_ok == 'unknown' else bool(tg_ok)
        if yt_ok is not None:
            entry['yt_ok'] = None if yt_ok == 'unknown' else bool(yt_ok)
        if custom is not None:
            existing_custom = entry.get('custom', {})
            if not isinstance(existing_custom, dict):
                existing_custom = {}
            for check_id, ok in (custom or {}).items():
                existing_custom[str(check_id)] = bool(ok)
            entry['custom'] = existing_custom
        cache[key_id] = entry
        save_key_probe_cache(cache)


def key_probe_is_fresh(entry, now=None, custom_checks=None):
    if not isinstance(entry, dict):
        return False
    try:
        ts = float(entry.get('ts', 0))
    except (TypeError, ValueError):
        return False
    if (now or time.time()) - ts >= KEY_PROBE_CACHE_TTL:
        return False
    custom_checks = custom_checks or []
    if custom_checks:
        custom = entry.get('custom', {})
        if not isinstance(custom, dict):
            return False
        return all(check.get('id') in custom for check in custom_checks)
    return True


def key_probe_has_required_results(entry, custom_checks=None):
    if not isinstance(entry, dict):
        return False
    if 'tg_ok' not in entry or 'yt_ok' not in entry:
        return False
    custom_checks = custom_checks or []
    if custom_checks:
        custom = entry.get('custom', {})
        if not isinstance(custom, dict):
            return False
        return all(check.get('id') in custom for check in custom_checks)
    return True
