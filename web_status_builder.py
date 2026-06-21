from probe_cache import youtube_probe_state


def empty_protocol_status():
    return {
        'tone': 'empty',
        'label': 'Не сохранён',
        'details': 'Ключ ещё не сохранён на роутере',
    }


def _strip_status_period(text):
    return str(text or '').strip().rstrip('.')


def _youtube_state_text(yt_ok, yt_state=''):
    yt_state = str(yt_state or '').strip().lower()
    if yt_state == 'warn':
        return 'нестабильно, перепроверяется'
    return 'работает' if yt_ok else 'не работает'


def service_status_parts(api_ok, yt_ok, custom_states, custom_checks, *, api_transient=False, api_required=True, yt_state=''):
    parts = [
        f'YouTube: {_youtube_state_text(yt_ok, yt_state)}',
    ]
    if api_required:
        telegram_state = 'работает' if api_ok else ('перепроверяется' if api_transient else 'не работает')
    else:
        telegram_state = 'работает' if api_ok else 'не требуется для текущего режима'
    parts.insert(0, f'Telegram: {telegram_state}')
    for check in custom_checks or []:
        check_id = check.get('id')
        state = custom_states.get(check_id)
        if state in ('ok', 'fail'):
            parts.append(f'{check.get("label", "Сервис")}: {"работает" if state == "ok" else "не работает"}')
    return parts


def tone_label(api_ok, yt_ok, custom_states, *, api_required=True):
    any_ok = api_ok or yt_ok or any(state == 'ok' for state in custom_states.values())
    if not api_required and any_ok:
        return 'ok', 'Работает'
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
    api_required=True,
    yt_state='',
):
    if endpoint_ok and api_transient:
        return {
            'tone': 'warn',
            'label': 'Проверяется',
            'details': (f'{endpoint_message} Telegram API не ответил вовремя, идёт повторная проверка. '
                        'Статус обновится без перезагрузки страницы').strip(),
            'endpoint_ok': endpoint_ok,
            'endpoint_message': endpoint_message,
            'api_ok': False,
            'api_message': api_message,
            'api_pending': True,
            'yt_ok': yt_ok,
            'yt_state': yt_state or ('ok' if yt_ok else 'fail'),
            'yt_message': yt_message,
            'custom': custom_states,
        }
    service_parts = service_status_parts(
        api_ok,
        yt_ok,
        custom_states,
        custom_checks,
        api_transient=api_transient,
        api_required=api_required,
        yt_state=yt_state,
    )
    tone, label = tone_label(api_ok, yt_ok, custom_states, api_required=api_required)
    if yt_state == 'warn' and tone == 'ok':
        tone = 'warn'
        label = 'Частично работает'
    endpoint_text = _strip_status_period(endpoint_message)
    details = 'Показан результат проверки активного ключа'
    if endpoint_text:
        details += f'; {endpoint_text}'
    if service_parts:
        details += '; ' + ', '.join(service_parts)
    return {
        'tone': tone,
        'label': label,
        'details': details,
        'endpoint_ok': endpoint_ok,
        'endpoint_message': endpoint_message,
        'api_ok': api_ok,
        'api_message': api_message,
        'yt_ok': yt_ok,
        'yt_state': yt_state or ('ok' if yt_ok else 'fail'),
        'yt_message': yt_message,
        'custom': custom_states,
    }


def cached_protocol_status(key_value, probe, custom_checks, custom_states, *, api_required=True):
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
            'details': 'Ключ ждёт фоновой проверки. Чтобы не перегружать роутер, ключи проверяются по одному',
            'endpoint_ok': None,
            'endpoint_message': '',
            'api_ok': False,
            'api_message': '',
            'yt_ok': False,
            'yt_message': '',
            'custom': custom_states,
        }
    api_ok = bool(probe.get('tg_ok')) if 'tg_ok' in probe else False
    yt_state = youtube_probe_state(probe)
    yt_ok = yt_state in ('ok', 'warn') if 'yt_ok' in probe or probe.get('yt_stability') else False
    service_parts = []
    if 'tg_ok' in probe:
        telegram_state = 'работает' if api_ok else ('не работает' if api_required else 'не требуется для текущего режима')
        service_parts.append(f'Telegram: {telegram_state}')
    if 'yt_ok' in probe:
        service_parts.append(f'YouTube: {_youtube_state_text(yt_ok, yt_state)}')
    for check in custom_checks or []:
        check_id = check.get('id')
        state = custom_states.get(check_id)
        if state in ('ok', 'fail'):
            service_parts.append(f'{check.get("label", "Сервис")}: {"работает" if state == "ok" else "не работает"}')
    details = 'Показан последний результат проверки пула'
    if service_parts:
        details += '; ' + ', '.join(service_parts)
    tone, label = tone_label(api_ok, yt_ok, custom_states, api_required=api_required)
    if yt_state == 'warn' and tone == 'ok':
        tone = 'warn'
        label = 'Частично работает'
    return {
        'tone': tone,
        'label': label,
        'details': details,
        'endpoint_ok': None,
        'endpoint_message': '',
        'api_ok': api_ok,
        'api_message': '',
        'yt_ok': yt_ok,
        'yt_state': yt_state,
        'yt_message': '',
        'custom': custom_states,
    }
