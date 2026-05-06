import base64
import json
import os


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
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(pools, file, ensure_ascii=False, indent=2)
    return pools


def ensure_current_keys_in_pools(pools, current_keys):
    pools = normalize_key_pools(pools)
    changed = False
    for proto in PROTOCOLS:
        key_value = str((current_keys or {}).get(proto) or '').strip()
        keys = dedupe_key_list(pools.get(proto, []) or [])
        original_keys = list(keys)
        if key_value:
            keys = [candidate for candidate in keys if candidate != key_value]
            keys.insert(0, key_value)
        pools[proto] = keys
        if keys != original_keys:
            changed = True
    return pools, changed


def set_active_key(pools, proto, key):
    pools = normalize_key_pools(pools)
    key = str(key or '').strip()
    if proto not in pools or not key:
        return pools
    keys = [candidate for candidate in dedupe_key_list(pools.get(proto, []) or []) if candidate != key]
    keys.insert(0, key)
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
