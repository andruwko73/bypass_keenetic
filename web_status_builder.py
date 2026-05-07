def empty_protocol_status():
    return {
        'tone': 'empty',
        'label': 'Не сохранён',
        'details': 'Ключ ещё не сохранён на роутере.',
    }


def service_status_parts(api_ok, yt_ok, custom_states, custom_checks, *, api_transient=False):
    parts = [
        f'Telegram: {"работает" if api_ok else ("перепроверяется" if api_transient else "не работает")}',
        f'YouTube: {"работает" if yt_ok else "не работает"}',
    ]
    for check in custom_checks or []:
        check_id = check.get('id')
        state = custom_states.get(check_id)
        if state in ('ok', 'fail'):
            parts.append(f'{check.get("label", "Сервис")}: {"работает" if state == "ok" else "не работает"}')
    return parts


def tone_label(api_ok, yt_ok, custom_states):
    any_ok = api_ok or yt_ok or any(state == 'ok' for state in custom_states.values())
    return (
        'ok' if api_ok else ('warn' if any_ok else 'fail'),
        'Работает' if api_ok else ('Частично работает' if any_ok else 'Не работает'),
    )


def active_protocol_status(
    *,
    endpoint_ok,
    endpoint_message,
    api_ok,
    api_message,
    api_transient,
    yt_ok,
    yt_message,
    custom_states,
    custom_checks,
):
    if endpoint_ok and api_transient:
        return {
            'tone': 'warn',
            'label': 'Проверяется',
            'details': (f'{endpoint_message} Telegram API не ответил вовремя, идёт повторная проверка. '
                        'Статус обновится без перезагрузки страницы.').strip(),
            'endpoint_ok': endpoint_ok,
            'endpoint_message': endpoint_message,
            'api_ok': False,
            'api_message': api_message,
            'api_pending': True,
            'yt_ok': yt_ok,
            'yt_message': yt_message,
            'custom': custom_states,
        }
    service_parts = service_status_parts(
        api_ok,
        yt_ok,
        custom_states,
        custom_checks,
        api_transient=api_transient,
    )
    tone, label = tone_label(api_ok, yt_ok, custom_states)
    return {
        'tone': tone,
        'label': label,
        'details': (f'Показан результат проверки активного ключа. {endpoint_message} ' + ', '.join(service_parts) + '.').strip(),
        'endpoint_ok': endpoint_ok,
        'endpoint_message': endpoint_message,
        'api_ok': api_ok,
        'api_message': api_message,
        'yt_ok': yt_ok,
        'yt_message': yt_message,
        'custom': custom_states,
    }


def cached_protocol_status(key_value, probe, custom_checks, custom_states):
    if not str(key_value or '').strip():
        return empty_protocol_status()
    has_probe_result = (
        'tg_ok' in probe or
        'yt_ok' in probe or
        any(state in ('ok', 'fail') for state in custom_states.values())
    )
    if not has_probe_result:
        return {
            'tone': 'warn',
            'label': 'Не проверялся',
            'details': 'Ключ ждёт фоновой проверки. Чтобы не перегружать роутер, ключи проверяются по одному.',
            'endpoint_ok': None,
            'endpoint_message': '',
            'api_ok': False,
            'api_message': '',
            'yt_ok': False,
            'yt_message': '',
            'custom': custom_states,
        }
    api_ok = bool(probe.get('tg_ok')) if 'tg_ok' in probe else False
    yt_ok = bool(probe.get('yt_ok')) if 'yt_ok' in probe else False
    service_parts = []
    if 'tg_ok' in probe:
        service_parts.append(f'Telegram: {"работает" if api_ok else "не работает"}')
    if 'yt_ok' in probe:
        service_parts.append(f'YouTube: {"работает" if yt_ok else "не работает"}')
    for check in custom_checks or []:
        check_id = check.get('id')
        state = custom_states.get(check_id)
        if state in ('ok', 'fail'):
            service_parts.append(f'{check.get("label", "Сервис")}: {"работает" if state == "ok" else "не работает"}')
    details = 'Показан последний результат проверки пула.'
    if service_parts:
        details += ' ' + ', '.join(service_parts) + '.'
    tone, label = tone_label(api_ok, yt_ok, custom_states)
    return {
        'tone': tone,
        'label': label,
        'details': details,
        'endpoint_ok': None,
        'endpoint_message': '',
        'api_ok': api_ok,
        'api_message': '',
        'yt_ok': yt_ok,
        'yt_message': '',
        'custom': custom_states,
    }
