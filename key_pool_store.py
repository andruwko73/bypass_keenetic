import base64
import json
import os
import tempfile
import time


PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')


def dedupe_key_list(keys):
    result = []
    seen = set()
    for key_value in keys or []:
        key_value = str(key_value or '').strip()
        if not key_value or key_value in seen:
            continue
        seen.add(key_value)
        result.append(key_value)
    return result


def normalize_key_pools(pools):
    return {
        proto: dedupe_key_list((pools or {}).get(proto, []))
        for proto in PROTOCOLS
    }


def load_key_pools(path):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            value = json.load(file)
        if isinstance(value, dict):
            return normalize_key_pools(value)
    except Exception:
        pass
    return {proto: [] for proto in PROTOCOLS}


def save_key_pools(path, pools):
    pools = normalize_key_pools(pools)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix='.key_pools_', suffix='.json', dir=directory or None)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(pools, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
    return pools


def ensure_current_keys_in_pools(pools, current_keys):
    pools = normalize_key_pools(pools)
    changed = False
    for proto in PROTOCOLS:
        key_value = str((current_keys or {}).get(proto) or '').strip()
        keys = dedupe_key_list(pools.get(proto, []) or [])
        original_keys = list(keys)
        if key_value and key_value not in keys:
            keys.append(key_value)
        pools[proto] = keys
        if keys != original_keys:
            changed = True
    return pools, changed


def set_active_key(pools, proto, key):
    pools = normalize_key_pools(pools)
    key = str(key or '').strip()
    if proto not in pools or not key:
        return pools
    keys = dedupe_key_list(pools.get(proto, []) or [])
    if key not in keys:
        keys.append(key)
    pools[proto] = keys
    return pools


def add_keys_to_pool(pools, proto, keys_text):
    pools = normalize_key_pools(pools)
    if proto not in pools:
        pools[proto] = []
    new_keys = [line.strip() for line in (keys_text or '').splitlines() if line.strip()]
    added_keys = []
    existing = set(pools.get(proto, []) or [])
    for key_value in new_keys:
        if key_value in existing:
            continue
        pools[proto].append(key_value)
        existing.add(key_value)
        added_keys.append(key_value)
    return pools, added_keys


def classify_subscription_keys(raw_text):
    try:
        decoded = base64.b64decode(raw_text + '=' * (-len(raw_text) % 4)).decode('utf-8')
    except Exception:
        decoded = raw_text
    result = {proto: [] for proto in PROTOCOLS}
    for key_value in decoded.splitlines():
        key_value = key_value.strip()
        if not key_value:
            continue
        if key_value.startswith('ss://'):
            result['shadowsocks'].append(key_value)
        elif key_value.startswith('vmess://'):
            result['vmess'].append(key_value)
        elif key_value.startswith('vless://'):
            result['vless'].append(key_value)
        elif key_value.startswith('trojan://'):
            result['trojan'].append(key_value)
    return result


def add_subscription_keys_to_pool(pools, proto, fetched_keys):
    pools = normalize_key_pools(pools)
    if proto not in pools:
        pools[proto] = []
    source_proto = 'vless' if proto == 'vless2' else proto
    added_keys = []
    existing = set(pools.get(proto, []) or [])
    for key_value in (fetched_keys or {}).get(source_proto, []) or []:
        if key_value in existing:
            continue
        pools[proto].append(key_value)
        existing.add(key_value)
        added_keys.append(key_value)
    return pools, added_keys


def delete_pool_key(pools, proto, key_value):
    pools = normalize_key_pools(pools)
    if proto not in pools:
        return pools, False
    key_value = str(key_value or '').strip()
    keys = dedupe_key_list(pools.get(proto, []) or [])
    if key_value not in keys:
        pools[proto] = keys
        return pools, False
    pools[proto] = [candidate for candidate in keys if candidate != key_value]
    return pools, True


def clear_pool(pools, proto):
    pools = normalize_key_pools(pools)
    if proto not in pools:
        return pools, []
    removed_keys = dedupe_key_list(pools.get(proto, []) or [])
    pools[proto] = []
    return pools, removed_keys


def failover_candidates(
    pools,
    current_proto,
    current_key,
    protocols=PROTOCOLS,
    key_probe_cache=None,
    hash_key=None,
    service='telegram',
    exclude_keys=None,
    recent_failure_backoff_seconds=0,
    skip_failed=False,
    now=None,
):
    pools = normalize_key_pools(pools)
    current_proto = str(current_proto or '').strip()
    current_key = str(current_key or '').strip()
    exclude_keys = {str(key or '').strip() for key in (exclude_keys or ()) if str(key or '').strip()}
    key_probe_cache = key_probe_cache or {}
    service_field = 'yt_ok' if service == 'youtube' else 'tg_ok'
    try:
        now_ts = int(time.time() if now is None else now)
    except Exception:
        now_ts = 0
    try:
        failure_backoff = max(0, int(recent_failure_backoff_seconds or 0))
    except Exception:
        failure_backoff = 0

    def probe_score(key_value):
        probe = {}
        if not key_probe_cache or not hash_key:
            pass
        else:
            probe = key_probe_cache.get(hash_key(key_value), {})
            if not isinstance(probe, dict):
                probe = {}
        try:
            checked_ts = int(probe.get('ts') or 0)
        except Exception:
            checked_ts = 0
        if service == 'youtube':
            try:
                score = int(probe.get('yt_score'))
            except Exception:
                score = None
            if score is None:
                if probe.get(service_field) is True:
                    score = 60
                elif service_field in probe and probe.get(service_field) is False:
                    score = 0
                else:
                    score = 30
            stability = str(probe.get('yt_stability') or '').strip().lower()
            if stability == 'unstable':
                score = min(score, 65)
            elif stability == 'fail':
                score = 0
            try:
                error_rate = float(probe.get('yt_error_rate') or 0)
            except Exception:
                error_rate = 0.0
            if error_rate > 0 and stability == 'unstable':
                score = max(0, score - int(round(error_rate * 100)))
            elif error_rate > 0:
                score = max(0, score - min(10, int(round(error_rate * 40))))
        elif probe.get(service_field) is True:
            score = 3
        elif service_field in probe and probe.get(service_field) is False:
            score = 1
        else:
            score = 2
        recently_failed = bool(
            service != 'youtube' and
            probe.get(service_field) is False and
            failure_backoff > 0 and
            checked_ts > 0 and
            now_ts > 0 and
            now_ts - checked_ts < failure_backoff
        )
        return (score, checked_ts, recently_failed)

    protocol_order = [proto for proto in (protocols or PROTOCOLS) if proto in pools]
    priority = []
    if current_proto in protocol_order:
        priority.append(current_proto)
    if current_proto == 'vless' and 'vless2' in protocol_order:
        priority.append('vless2')
    elif current_proto == 'vless2' and 'vless' in protocol_order:
        priority.append('vless')
    for proto in protocol_order:
        if proto not in priority:
            priority.append(proto)
    candidates = []
    for proto in priority:
        for index, key_value in enumerate(pools.get(proto, []) or []):
            key_value = str(key_value or '').strip()
            if not key_value:
                continue
            if proto == current_proto and key_value == current_key:
                continue
            if key_value in exclude_keys:
                continue
            score, checked_ts, recently_failed = probe_score(key_value)
            if recently_failed:
                continue
            proto_rank = priority.index(proto)
            if service != 'youtube' and skip_failed and score <= 1:
                continue
            candidates.append((proto, key_value, score, checked_ts, proto_rank, index))
    if service == 'youtube':
        candidates.sort(key=lambda item: (item[4], -item[2], -item[3], item[5]))
    else:
        candidates.sort(
            key=lambda item: (
                -item[2],
                item[3] if item[2] <= 1 else -item[3],
                item[4],
                item[5],
            )
        )
    candidates = [(proto, key_value) for proto, key_value, _score, _checked_ts, _proto_rank, _index in candidates]
    return candidates
