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


def _last_result_state(state):
    """Normalize legacy age-qualified states to their last completed result."""
    return {
        'stale_ok': 'ok',
        'stale_fail': 'fail',
        'stale': 'unknown',
    }.get(str(state or '').strip().lower(), str(state or '').strip().lower())


def _last_custom_states(custom_states):
    return {
        check_id: _last_result_state(state)
        for check_id, state in (custom_states or {}).items()
    }


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


def pool_status_summary(
    current_keys,
    key_pools,
    key_probe_cache,
    custom_checks,
    hash_key,
    *,
    protocol_order=('vless', 'vless2', 'vmess', 'trojan', 'shadowsocks'),
    active_keys_text='протоколов с выбранным ключом',
    pool_total_text='Записей в пулах',
    checked_text='С сохранённым результатом',
):
    """Build one consistent pool summary for light and full web snapshots."""
    current_keys = current_keys or {}
    key_pools = key_pools or {}
    key_probe_cache = key_probe_cache or {}
    protocol_order = tuple(protocol_order or ())
    services = [
        {'label': 'Telegram', 'field': 'tg_ok', 'id': None, 'count': 0},
        {'label': 'YouTube', 'field': 'yt_ok', 'id': None, 'count': 0},
    ]
    for check in custom_checks or ():
        if not isinstance(check, dict):
            continue
        check_id = str(check.get('id') or '').strip()
        if not check_id:
            continue
        label = str(check.get('label') or check_id).strip() or check_id
        services.append({'label': label, 'field': None, 'id': check_id, 'count': 0})

    total_count = 0
    checked_count = 0
    all_services_count = 0
    any_service_count = 0
    for proto in protocol_order:
        for pool_key in key_pools.get(proto, ()) or ():
            total_count += 1
            probe = key_probe_cache.get(hash_key(pool_key), {})
            if not isinstance(probe, dict):
                probe = {}
            custom = probe.get('custom', {})
            if not isinstance(custom, dict):
                custom = {}
            results = []
            for service in services:
                field = service['field']
                if field == 'yt_ok':
                    state = youtube_probe_state(probe)
                    if state == 'unknown':
                        continue
                    ok = state in ('ok', 'warn')
                elif field:
                    if field not in probe or not isinstance(probe.get(field), bool):
                        continue
                    ok = probe.get(field)
                else:
                    service_id = service['id']
                    if service_id not in custom or not isinstance(custom.get(service_id), bool):
                        continue
                    ok = custom.get(service_id)
                results.append(ok)
                if ok:
                    service['count'] += 1
            if results:
                checked_count += 1
                if any(results):
                    any_service_count += 1
                if all(results):
                    all_services_count += 1

    active_key_count = sum(1 for proto in protocol_order if (current_keys.get(proto) or '').strip())
    service_text = '; '.join(f"{service['label']}: {service['count']}" for service in services)
    note_parts = [f'{pool_total_text}: {total_count}', f'{checked_text}: {checked_count}']
    if service_text:
        note_parts.append(service_text)
    return {
        'active_key_count': active_key_count,
        'protocol_count': len(protocol_order),
        'active_text': f'{active_key_count} из {len(protocol_order)} {active_keys_text}',
        'note': '; '.join(note_parts),
        'pool_total_count': total_count,
        'checked_pool_count': checked_count,
        'all_services_count': all_services_count,
        'any_service_count': any_service_count,
        'services': [{'label': service['label'], 'count': service['count']} for service in services],
    }


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
    custom_states = _last_custom_states(custom_states)
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
        state_text = {
            'ok': 'работает',
            'fail': 'не работает',
            'unknown': 'не проверено',
        }.get(state)
        if state_text:
            parts.append(f'{check.get("label", "Сервис")}: {state_text}')
    return parts


def _normalize_required_services(required_services):
    if required_services is None:
        return None
    selected = set(required_services or [])
    return tuple(service for service in ('telegram', 'youtube') if service in selected)


def _probe_age_text(age_seconds):
    if age_seconds is None:
        return ''
    try:
        age_seconds = max(0, int(age_seconds))
    except (TypeError, ValueError):
        return ''
    if age_seconds < 10:
        return 'только что'
    if age_seconds < 60:
        return f'{age_seconds} сек. назад'
    if age_seconds < 3600:
        return f'{age_seconds // 60} мин назад'
    return f'{age_seconds // 3600} ч назад'


def tone_label(
    api_ok,
    yt_ok,
    custom_states,
    *,
    api_required=True,
    required_services=None,
    pending=False,
    verification_pending=False,
):
    if pending:
        return 'warn', 'Статус обновляется'
    required_services = _normalize_required_services(required_services)
    custom_states = _last_custom_states(custom_states)
    custom_fail = any(state == 'fail' for state in custom_states.values())
    if verification_pending and not custom_fail:
        return 'warn', 'Требуется повторная проверка'
    if required_services:
        states = []
        if 'telegram' in required_services:
            states.append(bool(api_ok))
        if 'youtube' in required_services:
            states.append(bool(yt_ok))
        custom_ok = any(state == 'ok' for state in custom_states.values())
        if states and all(states) and not custom_fail:
            return 'ok', 'Работает'
        if any(states) or custom_ok:
            return 'warn', 'Частично работает'
        return 'fail', 'Не работает'
    any_ok = api_ok or yt_ok or any(state == 'ok' for state in custom_states.values())
    if not api_required and any_ok and not custom_fail:
        return 'ok', 'Работает'
    return (
        'ok' if api_ok and not custom_fail else ('warn' if any_ok else 'fail'),
        'Работает' if api_ok and not custom_fail else ('Частично работает' if any_ok else 'Не работает'),
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
            'api_state': 'pending' if api_pending else ('ok' if api_ok else 'fail'),
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
        'api_state': 'pending' if api_pending else ('ok' if api_ok else 'fail'),
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


def confirmed_telegram_status(
    status,
    custom_checks,
    *,
    required_services=None,
    confirmation_message='Telegram-бот работает через активный ключ.',
):
    """Overlay stronger live polling evidence onto a cached protocol status."""
    current = dict(status or {})
    required_services = _normalize_required_services(required_services)
    if required_services is not None and 'telegram' not in required_services:
        return current

    custom_states = current.get('custom')
    if not isinstance(custom_states, dict):
        custom_states = {}
    endpoint_message = str(current.get('endpoint_message') or '').strip() or confirmation_message
    return active_protocol_status(
        endpoint_ok=True,
        endpoint_message=endpoint_message,
        api_ok=True,
        api_message=confirmation_message,
        api_transient=False,
        api_pending=False,
        yt_ok=bool(current.get('yt_ok')),
        yt_message=str(current.get('yt_message') or ''),
        yt_pending=bool(current.get('yt_pending')),
        yt_state=str(current.get('yt_state') or ''),
        custom_states=dict(custom_states),
        custom_checks=custom_checks or (),
        api_required=True,
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
    api_state=None,
    probe_yt_state=None,
    checked_age_seconds=None,
):
    if not str(key_value or '').strip():
        return empty_protocol_status()
    required_services = _normalize_required_services(required_services)
    if required_services == () and not custom_checks:
        return unused_protocol_status()
    api_state = api_state or ('ok' if probe.get('tg_ok') is True else 'fail' if probe.get('tg_ok') is False else 'unknown')
    probe_yt_state = probe_yt_state or youtube_probe_state(probe)
    if api_state == 'stale':
        api_state = 'ok' if probe.get('tg_ok') is True else 'fail' if probe.get('tg_ok') is False else 'unknown'
    if probe_yt_state == 'stale':
        probe_yt_state = youtube_probe_state(probe)
    custom_states = _last_custom_states(custom_states)
    has_probe_result = any(
        state in ('ok', 'warn', 'fail')
        for state in (api_state, probe_yt_state, *custom_states.values())
    )
    if not has_probe_result:
        return {
            'tone': 'warn',
            'label': 'Не проверялся',
            'details': 'Ключ ждёт фоновой проверки. Чтобы не перегружать роутер, ключи проверяются по одному',
            'endpoint_ok': None,
            'endpoint_message': '',
            'api_ok': False,
            'api_state': 'unknown',
            'api_message': '',
            'yt_ok': False,
            'yt_state': 'unknown',
            'yt_message': '',
            'custom': custom_states,
        }
    api_ok = api_state == 'ok'
    yt_ok = probe_yt_state in ('ok', 'warn')
    service_parts = []
    if api_state != 'unknown':
        telegram_state = 'работает' if api_ok else ('не работает' if api_required else 'не требуется для текущего режима')
        service_parts.append(f'Telegram: {telegram_state}')
    if probe_yt_state != 'unknown':
        youtube_state_text = _youtube_state_text(yt_ok, probe_yt_state)
        service_parts.append(f'YouTube: {youtube_state_text}')
    for check in custom_checks or []:
        check_id = check.get('id')
        state = custom_states.get(check_id)
        state_text = {
            'ok': 'работает',
            'fail': 'не работает',
            'unknown': 'не проверено',
        }.get(state)
        if state_text:
            service_parts.append(f'{check.get("label", "Сервис")}: {state_text}')
    verification_pending = (
        ((required_services is None or 'telegram' in required_services) and api_state == 'unknown') or
        ((required_services is None or 'youtube' in required_services) and probe_yt_state == 'unknown')
    )
    tone, label = tone_label(
        api_ok,
        yt_ok,
        custom_states,
        api_required=api_required,
        required_services=required_services,
        verification_pending=verification_pending,
    )
    if probe_yt_state == 'warn' and tone == 'ok' and required_services is None:
        tone = 'warn'
        label = 'Частично работает'
    if label == 'Требуется повторная проверка':
        details = 'Проверка пула ещё не содержит результаты для всех назначенных сервисов'
    else:
        details = 'Показан последний результат проверки пула'
    age_text = _probe_age_text(checked_age_seconds)
    if age_text:
        details += f' ({age_text})'
    if service_parts:
        details += '; ' + ', '.join(service_parts)
    return {
        'tone': tone,
        'label': label,
        'details': details,
        'endpoint_ok': None,
        'endpoint_message': '',
        'api_ok': api_ok,
        'api_state': api_state,
        'api_message': '',
        'yt_ok': yt_ok,
        'yt_state': probe_yt_state,
        'yt_message': '',
        'custom': custom_states,
        'checked_age_seconds': checked_age_seconds,
    }
