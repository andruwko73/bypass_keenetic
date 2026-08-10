import time


def task_id(proto, key_or_id, *, protocols, hash_key):
    proto = str(proto or '').strip()
    key_or_id = str(key_or_id or '').strip()
    if proto not in protocols or not key_or_id:
        return None
    if len(key_or_id) == 40 and all(char in '0123456789abcdefABCDEF' for char in key_or_id):
        return proto, key_or_id.lower()
    return proto, hash_key(key_or_id)


def normalize_payload(payload, *, protocols, hash_key, now=None):
    if not isinstance(payload, dict):
        return None
    tasks = []
    for item in payload.get('tasks') or []:
        if isinstance(item, dict):
            normalized = task_id(
                item.get('proto') or item.get('protocol'),
                item.get('key_id') or item.get('hash') or item.get('key'),
                protocols=protocols,
                hash_key=hash_key,
            )
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            normalized = task_id(item[0], item[1], protocols=protocols, hash_key=hash_key)
        else:
            normalized = None
        if normalized:
            tasks.append(normalized)
    if not tasks:
        return None

    checked = _nonnegative_int(payload.get('checked'))
    total = max(_nonnegative_int(payload.get('total')), checked + len(tasks), len(tasks))
    checked = min(checked, total)
    try:
        started_at = float(payload.get('started_at') or 0)
    except (TypeError, ValueError):
        started_at = 0.0
    if started_at <= 0:
        started_at = time.time() if now is None else float(now)
    checks = [dict(check) for check in payload.get('checks') or [] if isinstance(check, dict)]
    return {
        'tasks': tasks,
        'checks': checks,
        'scope': str(payload.get('scope') or 'manual'),
        'checked': checked,
        'total': total,
        'started_at': started_at,
        'skipped_missing': _nonnegative_int(payload.get('skipped_missing')),
    }


def resolve_payload(payload, pools, *, protocols, hash_key, now=None):
    payload = normalize_payload(
        payload,
        protocols=protocols,
        hash_key=hash_key,
        now=now,
    )
    if not payload:
        return None
    lookup = {
        (proto, hash_key(key_value)): key_value
        for proto in protocols
        for key in (pools.get(proto) or [])
        for key_value in (str(key or '').strip(),)
        if key_value
    }
    resolved = [
        (proto, lookup[(proto, key_id)])
        for proto, key_id in payload['tasks']
        if (proto, key_id) in lookup
    ]
    missing_count = max(0, len(payload['tasks']) - len(resolved))
    result = dict(payload)
    result['tasks'] = resolved
    result['total'] = result['checked'] + len(resolved)
    result['skipped_missing'] += missing_count
    return result


def serializable_payload(payload):
    payload = dict(payload or {})
    payload.pop('_durable', None)
    payload['task_ref'] = 'key_hash'
    payload['tasks'] = [
        {'proto': proto, 'key_id': key_id}
        for proto, key_id in payload.get('tasks') or []
    ]
    return payload


def _nonnegative_int(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
