import hashlib
import json
import re
import time
from urllib.parse import parse_qsl, urlencode, urlparse

import key_pool_store


DEFAULT_HWID_HEADER_NAMES = ('X-HWID', 'X-Router-HWID', 'X-Device-ID')
DEFAULT_SUBSCRIPTION_USER_AGENT = 'v2rayN/6.45'
PROTOCOL_SUBSCRIPTION_SOURCE = {
    'vless2': 'vless',
}
AUTO_SYNC_MIN_PREVIOUS_KEYS = 20
AUTO_SYNC_MIN_RETAINED_KEYS = 5
AUTO_SYNC_MIN_RETAINED_RATIO = 0.25
AUTO_SYNC_SHRINK_CONFIRM_MIN_AGE_SECONDS = 300


def subscription_sync_shrink_is_suspicious(
    previous_managed_keys,
    fetched_keys,
    *,
    min_previous_keys=AUTO_SYNC_MIN_PREVIOUS_KEYS,
    min_retained_keys=AUTO_SYNC_MIN_RETAINED_KEYS,
    min_retained_ratio=AUTO_SYNC_MIN_RETAINED_RATIO,
):
    """Reject an implausibly small automatic subscription snapshot."""
    previous_count = len(key_pool_store.dedupe_key_list(previous_managed_keys or []))
    fetched_count = len(key_pool_store.dedupe_key_list(fetched_keys or []))
    if previous_count < max(1, int(min_previous_keys or 1)):
        return False
    retained_floor = max(
        max(1, int(min_retained_keys or 1)),
        int(previous_count * max(0.0, float(min_retained_ratio or 0.0))),
    )
    return fetched_count < retained_floor


def subscription_keys_signature(keys):
    normalized = sorted(key_pool_store.dedupe_key_list(keys or []))
    payload = json.dumps(normalized, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8', errors='ignore')).hexdigest()


def subscription_shrink_confirmation(record, fetched_keys, now, *, min_age_seconds=AUTO_SYNC_SHRINK_CONFIRM_MIN_AGE_SECONDS):
    """Return whether an identical suspicious snapshot was observed twice."""
    record = record if isinstance(record, dict) else {}
    signature = subscription_keys_signature(fetched_keys)
    try:
        first_seen_at = float(record.get('pending_shrink_at') or 0)
        now = float(now)
    except (TypeError, ValueError):
        first_seen_at = 0.0
        now = 0.0
    confirmed = bool(
        signature and
        signature == str(record.get('pending_shrink_signature') or '') and
        first_seen_at > 0 and
        now >= first_seen_at and
        now - first_seen_at >= max(0.0, float(min_age_seconds or 0))
    )
    return confirmed, {
        'pending_shrink_signature': signature,
        'pending_shrink_count': len(key_pool_store.dedupe_key_list(fetched_keys or [])),
        'pending_shrink_at': first_seen_at if confirmed else now,
    }


def subscription_refresh_is_due(record, now, *, interval_seconds, retry_seconds):
    """Use the retry delay after a failed attempt that followed an older success."""
    record = record if isinstance(record, dict) else {}
    try:
        now = float(now)
        last_success = float(record.get('last_success_at') or 0)
        last_attempt = float(record.get('last_attempt_at') or 0)
        interval_seconds = max(0.0, float(interval_seconds or 0))
        retry_seconds = max(0.0, float(retry_seconds or 0))
    except (TypeError, ValueError):
        return False
    if last_attempt > last_success:
        return now - last_attempt >= retry_seconds
    if last_success:
        return now - last_success >= interval_seconds
    if last_attempt:
        return now - last_attempt >= retry_seconds
    return True


def subscription_source_protocol(proto):
    proto = str(proto or '').strip()
    return PROTOCOL_SUBSCRIPTION_SOURCE.get(proto, proto)


def subscription_keys_for_protocol(proto, fetched_keys):
    source_proto = subscription_source_protocol(proto)
    if not isinstance(fetched_keys, dict):
        return []
    return key_pool_store.dedupe_key_list(fetched_keys.get(source_proto, []) or [])


def sync_subscription_keys_to_pool(pools, proto, fetched_keys, previous_managed_keys=None, preserve_keys=None):
    pools = key_pool_store.normalize_key_pools(pools)
    if proto not in pools:
        pools[proto] = []
    managed_keys = subscription_keys_for_protocol(proto, fetched_keys)
    managed_set = set(managed_keys)
    previous_set = set(key_pool_store.dedupe_key_list(previous_managed_keys or []))
    preserve_set = set(key_pool_store.dedupe_key_list(preserve_keys or []))
    retained_keys = [
        key_value
        for key_value in key_pool_store.dedupe_key_list(preserve_keys or [])
        if key_value in previous_set and key_value not in managed_set
    ]
    current_keys = key_pool_store.dedupe_key_list(pools.get(proto, []) or [])
    removed_keys = [
        key_value
        for key_value in current_keys
        if key_value in previous_set and key_value not in managed_set and key_value not in preserve_set
    ]
    kept_keys = [
        key_value
        for key_value in current_keys
        if key_value not in previous_set or key_value in managed_set or key_value in preserve_set
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
    state_managed_keys = key_pool_store.dedupe_key_list(list(managed_keys) + retained_keys)
    return pools, added_keys, removed_keys, state_managed_keys


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
            'pending_shrink_signature': str(item.get('pending_shrink_signature') or '').strip(),
            'pending_shrink_count': max(0, int(item.get('pending_shrink_count') or 0)),
            'pending_shrink_at': float(item.get('pending_shrink_at') or 0),
        }
    return state


def serialize_subscription_state(state):
    state = normalize_subscription_state(state)
    return {'subscriptions': state}


def nightly_pool_probe_window_date(timestamp, *, start_hour=3, end_hour=6, localtime=time.localtime):
    """Return the local calendar day for a configured nightly window, or ``''``.

    The caller persists the returned day after dispatching the full probe, which
    prevents duplicate launches when the maintenance scheduler wakes every few
    minutes or the bot restarts during the same window.
    """
    try:
        start_hour = max(0, min(23, int(start_hour)))
        end_hour = max(start_hour + 1, min(24, int(end_hour)))
        local = localtime(float(timestamp))
    except Exception:
        return ''
    if not start_hour <= int(local.tm_hour) < end_hour:
        return ''
    return time.strftime('%Y-%m-%d', local)


def nightly_pool_probe_due_date(timestamp, *, start_hour=3, end_hour=6, localtime=time.localtime):
    """Return the local day whose nightly probe is already due.

    Unlike :func:`nightly_pool_probe_window_date`, this remains valid after the
    nominal window closes.  A scheduler can therefore persist a pending run and
    safely retry it after a busy router, a subscription failure, or a restart.
    """
    try:
        start_hour = max(0, min(23, int(start_hour)))
        end_hour = max(start_hour + 1, min(24, int(end_hour)))
        local = localtime(float(timestamp))
    except Exception:
        return ''
    if int(local.tm_hour) < start_hour:
        return ''
    return time.strftime('%Y-%m-%d', local)


def latest_recent_subscription_success_at(state, now, *, max_age_seconds):
    """Return the newest eligible subscription refresh in a bounded age window."""
    try:
        now = float(now)
        max_age_seconds = max(0.0, float(max_age_seconds))
    except (TypeError, ValueError):
        return 0.0
    latest = 0.0
    for record in normalize_subscription_state(state).values():
        if not record.get('url') or not record.get('hwid_enabled'):
            continue
        try:
            success_at = float(record.get('last_success_at') or 0.0)
        except (TypeError, ValueError):
            continue
        if success_at <= 0.0 or success_at > now or now - success_at > max_age_seconds:
            continue
        latest = max(latest, success_at)
    return latest


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
    re.compile(r'\bhw[_\-\s]?id\b\s*[:=]\s*([A-Za-z0-9_.:-]{4,128})', re.I),
    re.compile(r'\b(?:hwid|hardware\s+id|device\s+id|serial(?:\s+number)?)\b\s*[:=]\s*([A-Za-z0-9_.:-]{4,128})', re.I),
    re.compile(r'\b(?:service\s+tag|serial)\b\s*[:=]\s*([A-Za-z0-9_.:-]{4,128})', re.I),
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
