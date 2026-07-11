def empty_protocol_status():
    return {
        'tone': 'empty',
        'label': 'Не сохранён',
        'details': 'Ключ ещё не сохранён на роутере',
    }


def unused_protocol_status():
    return {
        'tone': 'empty',
        'label': 'Не используется',
        'details': 'Сервисы не назначены на этот протокол; проверка не требуется',
        'endpoint_ok': None,
        'endpoint_message': '',
        'api_ok': False,
        'api_message': '',
        'yt_ok': False,
        'yt_state': 'unused',
        'yt_message': '',
        'custom': {},
    }


def _strip_status_period(text):
    return str(text or '').strip().rstrip('.')


def _youtube_state_text(yt_ok, yt_state=''):
    yt_state = str(yt_state or '').strip().lower()
    if yt_state == 'pending':
        return 'статус обновляется'
    if yt_state == 'warn':
        return 'нестабильно, перепроверяется'
    return 'работает' if yt_ok else 'не работает'


def youtube_probe_state(entry):
    if not isinstance(entry, dict):
        return 'unknown'
    stability = str(entry.get('yt_stability') or '').strip().lower()
    if entry.get('yt_ok') is True:
        return 'ok'
    if stability == 'unstable':
        return 'warn'
    if entry.get('yt_ok') is False:
        return 'fail'
    return 'unknown'


def service_status_parts(
    api_ok,
    yt_ok,
    custom_states,
    custom_checks,
    *,
    api_transient=False,
    api_pending=False,
    yt_pending=False,
    api_required=True,
    yt_state='',
    required_services=None,
):
    required_services = _normalize_required_services(required_services)
    parts = []
    if api_pending:
        telegram_state = 'статус обновляется'
    elif api_required:
        telegram_state = 'работает' if api_ok else ('перепроверяется' if api_transient else 'не работает')
    else:
        telegram_state = 'работает' if api_ok else 'не требуется для текущего режима'
    if required_services is None or 'telegram' in required_services:
        parts.append(f'Telegram: {telegram_state}')
    if required_services is None or 'youtube' in required_services:
        parts.append(f'YouTube: {_youtube_state_text(yt_ok, "pending" if yt_pending else yt_state)}')
    for check in custom_checks or []:
        check_id = check.get('id')
        state = custom_states.get(check_id)
        if state in ('ok', 'fail'):
            parts.append(f'{check.get("label", "Сервис")}: {"работает" if state == "ok" else "не работает"}')
    return parts


def _normalize_required_services(required_services):
    if required_services is None:
        return None
    selected = set(required_services or [])
    return tuple(service for service in ('telegram', 'youtube') if service in selected)


def tone_label(
    api_ok,
    yt_ok,
    custom_states,
    *,
    api_required=True,
    required_services=None,
    pending=False,
):
    if pending:
        return 'warn', 'Статус обновляется'
    required_services = _normalize_required_services(required_services)
    if required_services:
        states = []
        if 'telegram' in required_services:
            states.append(bool(api_ok))
        if 'youtube' in required_services:
            states.append(bool(yt_ok))
        custom_ok = any(state == 'ok' for state in custom_states.values())
        custom_fail = any(state == 'fail' for state in custom_states.values())
        if states and all(states) and not custom_fail:
            return 'ok', 'Работает'
        if any(states) or custom_ok:
            return 'warn', 'Частично работает'
        return 'fail', 'Не работает'
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
    api_pending=False,
    yt_pending=False,
    api_required=True,
    yt_state='',
    required_services=None,
):
    required_services = _normalize_required_services(required_services)
    if required_services == () and not custom_checks:
        return unused_protocol_status()
    telegram_required = (
        'telegram' in required_services
        if required_services is not None else
        bool(api_required)
    )
    pending = bool(api_pending or yt_pending or (api_transient and telegram_required))
    if endpoint_ok and pending:
        service_parts = service_status_parts(
            api_ok,
            yt_ok,
            custom_states,
            custom_checks,
            api_transient=api_transient,
            api_pending=api_pending,
            yt_pending=yt_pending,
            api_required=api_required,
            yt_state=yt_state,
            required_services=required_services,
        )
        endpoint_text = _strip_status_period(endpoint_message)
        details = 'Последний подтверждённый результат сохранён; статус обновится без перезагрузки страницы'
        if endpoint_text:
            details = f'{endpoint_text}. {details}'
        if service_parts:
            details += '; ' + ', '.join(service_parts)
        return {
            'tone': 'warn',
            'label': 'Статус обновляется',
            'details': details,
            'endpoint_ok': endpoint_ok,
            'endpoint_message': endpoint_message,
            'api_ok': api_ok,
            'api_message': api_message,
            'api_pending': True,
            'yt_ok': yt_ok,
            'yt_pending': bool(yt_pending),
            'yt_state': ('pending' if yt_pending else (yt_state or ('ok' if yt_ok else 'fail'))),
            'yt_message': yt_message,
            'custom': custom_states,
        }
    service_parts = service_status_parts(
        api_ok,
        yt_ok,
        custom_states,
        custom_checks,
        api_transient=api_transient,
        api_pending=api_pending,
        yt_pending=yt_pending,
        api_required=api_required,
        yt_state=yt_state,
        required_services=required_services,
    )
    tone, label = tone_label(
        api_ok,
        yt_ok,
        custom_states,
        api_required=api_required,
        required_services=required_services,
        pending=pending,
    )
    if yt_state == 'warn' and tone == 'ok' and required_services is None:
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
        'api_pending': bool(api_pending),
        'yt_ok': yt_ok,
        'yt_pending': bool(yt_pending),
        'yt_state': ('pending' if yt_pending else (yt_state or ('ok' if yt_ok else 'fail'))),
        'yt_message': yt_message,
        'custom': custom_states,
    }


def merge_light_status_with_cached_services(
    light_status,
    previous_status,
    custom_checks,
    *,
    required_services=(),
):
    """Keep confirmed custom checks when a lightweight refresh omits them."""
    light = dict(light_status or {})
    previous = previous_status if isinstance(previous_status, dict) else {}
    custom_states = previous.get('custom')
    if not isinstance(custom_states, dict) or not custom_states:
        return light

    checks = [
        check for check in (custom_checks or [])
        if isinstance(check, dict) and check.get('id') in custom_states
    ]
    if not checks or 'endpoint_ok' not in light:
        light['custom'] = dict(custom_states)
        return light

    required_services = _normalize_required_services(required_services)
    preserve_youtube = required_services is None or 'youtube' in required_services
    yt_state = str(light.get('yt_state') or '').strip().lower()
    if preserve_youtube and yt_state in ('', 'unused'):
        yt_ok = bool(previous.get('yt_ok'))
        yt_message = str(previous.get('yt_message') or '')
        yt_pending = bool(previous.get('yt_pending'))
        yt_state = str(previous.get('yt_state') or '').strip().lower()
    else:
        yt_ok = bool(light.get('yt_ok'))
        yt_message = str(light.get('yt_message') or '')
        yt_pending = bool(light.get('yt_pending'))

    return active_protocol_status(
        endpoint_ok=bool(light.get('endpoint_ok')),
        endpoint_message=str(light.get('endpoint_message') or ''),
        api_ok=bool(light.get('api_ok')),
        api_message=str(light.get('api_message') or ''),
        api_transient=False,
        api_pending=bool(light.get('api_pending')),
        yt_ok=yt_ok,
        yt_message=yt_message,
        yt_pending=yt_pending,
        yt_state=yt_state,
        custom_states=dict(custom_states),
        custom_checks=checks,
        api_required='telegram' in (required_services or ()),
        required_services=required_services,
    )


def cached_protocol_status(
    key_value,
    probe,
    custom_checks,
    custom_states,
    *,
    api_required=True,
    required_services=None,
):
    if not str(key_value or '').strip():
        return empty_protocol_status()
    required_services = _normalize_required_services(required_services)
    if required_services == () and not custom_checks:
        return unused_protocol_status()
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
    tone, label = tone_label(
        api_ok,
        yt_ok,
        custom_states,
        api_required=api_required,
        required_services=required_services,
    )
    if yt_state == 'warn' and tone == 'ok' and required_services is None:
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
