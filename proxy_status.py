import time


TRANSIENT_STATUS_MARKERS = (
    'network is unreachable',
    'timed out',
    'timeout',
    'таймаут',
    'не ответил вовремя',
    'за отведённое время',
    'за отведенное время',
    'max retries exceeded',
    'failed to establish a new connection',
    'connection reset',
)


def is_transient_status_text(status_text):
    text = str(status_text or '').casefold()
    return any(marker in text for marker in TRANSIENT_STATUS_MARKERS)


def custom_checks_signature(custom_checks, *, include_urls=False):
    if include_urls:
        return tuple((item.get('id'), tuple(item.get('urls') or [item.get('url')])) for item in custom_checks or [])
    return tuple((item.get('id'), item.get('url')) for item in custom_checks or [])


def status_snapshot_signature(current_keys, custom_checks=None, *, include_custom_urls=False):
    key_signature = tuple((name, current_keys.get(name, '')) for name in sorted(current_keys))
    if custom_checks is None:
        return key_signature
    return (key_signature, custom_checks_signature(custom_checks, include_urls=include_custom_urls))


def active_mode_status_signature(proxy_mode, current_keys, custom_checks=None):
    return (
        proxy_mode,
        current_keys.get(proxy_mode, ''),
        custom_checks_signature(custom_checks, include_urls=True),
    )


def cached_snapshot(cache, signature, ttl, *, now=None):
    now = time.time() if now is None else now
    if (
        cache.get('data') is not None and
        cache.get('signature') == signature and
        now - cache.get('timestamp', 0) < ttl
    ):
        return cache.get('data')
    return None


def store_snapshot(cache, signature, snapshot, *, now=None):
    cache['timestamp'] = time.time() if now is None else now
    cache['data'] = snapshot
    cache['signature'] = signature
    return snapshot


def cached_active_status(cache, signature, ttl, lock, *, now=None):
    now = time.time() if now is None else now
    with lock:
        if (
            cache.get('status') is not None and
            cache.get('signature') == signature and
            now - cache.get('timestamp', 0) < ttl
        ):
            return dict(cache.get('status'))
    return None


def store_active_status(cache, signature, status, lock, *, now=None):
    if not isinstance(status, dict):
        return
    with lock:
        cache['timestamp'] = time.time() if now is None else now
        cache['signature'] = signature
        cache['status'] = dict(status)


def placeholder_protocol_statuses(current_keys, *, pending_details=None):
    pending_details = pending_details or 'Фоновая проверка ключа выполняется. Обновите страницу через несколько секунд.'
    result = {}
    for key_name, key_value in current_keys.items():
        if str(key_value or '').strip():
            result[key_name] = {
                'tone': 'warn',
                'label': 'Проверяется',
                'details': pending_details,
            }
        else:
            result[key_name] = {
                'tone': 'empty',
                'label': 'Не сохранён',
                'details': 'Ключ ещё не сохранён на роутере.',
            }
    return result


def protocol_error_status(exc):
    return {
        'tone': 'warn',
        'label': 'Ошибка проверки',
        'details': f'Не удалось завершить проверку ключа: {exc}',
    }
