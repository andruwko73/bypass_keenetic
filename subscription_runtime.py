import re
from urllib.parse import parse_qsl, urlencode, urlparse

import key_pool_store


DEFAULT_HWID_HEADER_NAMES = ('X-HWID', 'X-Router-HWID', 'X-Device-ID')
PROTOCOL_SUBSCRIPTION_SOURCE = {
    'vless2': 'vless',
}


def subscription_source_protocol(proto):
    proto = str(proto or '').strip()
    return PROTOCOL_SUBSCRIPTION_SOURCE.get(proto, proto)


def subscription_keys_for_protocol(proto, fetched_keys):
    source_proto = subscription_source_protocol(proto)
    if not isinstance(fetched_keys, dict):
        return []
    return key_pool_store.dedupe_key_list(fetched_keys.get(source_proto, []) or [])


def sync_subscription_keys_to_pool(pools, proto, fetched_keys, previous_managed_keys=None):
    pools = key_pool_store.normalize_key_pools(pools)
    if proto not in pools:
        pools[proto] = []
    managed_keys = subscription_keys_for_protocol(proto, fetched_keys)
    managed_set = set(managed_keys)
    previous_set = set(key_pool_store.dedupe_key_list(previous_managed_keys or []))
    current_keys = key_pool_store.dedupe_key_list(pools.get(proto, []) or [])
    removed_keys = [
        key_value
        for key_value in current_keys
        if key_value in previous_set and key_value not in managed_set
    ]
    kept_keys = [
        key_value
        for key_value in current_keys
        if key_value not in previous_set or key_value in managed_set
    ]
    existing = set(kept_keys)
    added_keys = []
    for key_value in managed_keys:
        if key_value in existing:
            continue
        kept_keys.append(key_value)
        existing.add(key_value)
        added_keys.append(key_value)
    pools[proto] = kept_keys
    return pools, added_keys, removed_keys, managed_keys


def normalize_subscription_state(payload):
    if not isinstance(payload, dict):
        payload = {}
    entries = payload.get('subscriptions') if isinstance(payload.get('subscriptions'), dict) else payload
    state = {}
    for proto in key_pool_store.PROTOCOLS:
        item = entries.get(proto, {}) if isinstance(entries, dict) else {}
        if not isinstance(item, dict):
            item = {}
        state[proto] = {
            'url': str(item.get('url') or '').strip(),
            'hwid_enabled': bool(item.get('hwid_enabled')),
            'last_attempt_at': float(item.get('last_attempt_at') or 0),
            'last_success_at': float(item.get('last_success_at') or 0),
            'last_error': str(item.get('last_error') or '').strip(),
            'managed_keys': key_pool_store.dedupe_key_list(item.get('managed_keys') or []),
        }
    return state


def serialize_subscription_state(state):
    state = normalize_subscription_state(state)
    return {'subscriptions': state}


def subscription_public_settings(state):
    state = normalize_subscription_state(state)
    return {
        proto: {
            'hwid_enabled': bool(item.get('hwid_enabled')),
            'last_success_at': float(item.get('last_success_at') or 0),
            'last_error': str(item.get('last_error') or ''),
        }
        for proto, item in state.items()
    }


def apply_hwid_to_subscription_request(
    url,
    hwid,
    *,
    query_param='hwid',
    header_names=DEFAULT_HWID_HEADER_NAMES,
):
    hwid = str(hwid or '').strip()
    if not hwid:
        return str(url or ''), {}
    request_url = str(url or '').strip()
    parsed = urlparse(request_url)
    query_param = str(query_param or '').strip()
    if query_param:
        query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key != query_param
        ]
        query.append((query_param, hwid))
        request_url = parsed._replace(query=urlencode(query)).geturl()
    headers = {
        str(name).strip(): hwid
        for name in (header_names or ())
        if str(name or '').strip()
    }
    return request_url, headers


_HWID_PATTERNS = (
    re.compile(r'\b(?:hwid|hardware\s+id|device\s+id|serial(?:\s+number)?)\b\s*[:=]\s*([A-Za-z0-9_.:-]{4,128})', re.I),
    re.compile(r'\b(?:серийн(?:ый|ого)?\s+номер|идентификатор)\b\s*[:=]\s*([A-Za-z0-9_.:-]{4,128})', re.I),
)


def extract_router_hwid(text):
    text = str(text or '')
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for pattern in _HWID_PATTERNS:
            match = pattern.search(line)
            if match:
                return match.group(1).strip()
    return ''
