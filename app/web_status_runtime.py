PROXY_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')


def telegram_api_success_message():
    return '✅ Доступ к api.telegram.org подтверждён'


def telegram_api_pending_message():
    return (
        '⏳ Telegram API не ответил вовремя через текущий режим. '
        'Программа подбирает рабочий ключ из пула текущего режима; '
        'если подходящих кандидатов нет, повторит проверку позже. '
        'Статус обновится без перезагрузки страницы'
    )


def telegram_api_refresh_message():
    return '⏳ Статус обновляется. Проверяется актуальное состояние. Статус обновится без перезагрузки страницы'


def telegram_api_recovery_message(proxy_mode):
    mode = str(proxy_mode or '').strip() or 'текущий'
    return (
        f'❌ Доступ к Telegram API через режим {mode} не проходит. '
        'Программа подбирает рабочий ключ из пула текущего режима; '
        'если подходящих кандидатов нет, повторит проверку позже. '
        'Техническая ошибка записана в лог.'
    )


def telegram_api_direct_recovery_message():
    return (
        '❌ Прямой доступ к api.telegram.org не проходит. '
        'Если Telegram должен работать через ключ, включите режим с пулом. '
        'Программа подбирает рабочий ключ из пула текущего режима; '
        'если включён прямой режим, повторит проверку позже. '
        'Техническая ошибка записана в лог.'
    )


def api_status_from_runtime_check(proxy_mode, api_status, socks_ok, is_transient):
    status_text = str(api_status or '').strip()
    if status_text.startswith('✅'):
        return status_text
    if proxy_mode != 'none' and socks_ok and is_transient(status_text):
        return telegram_api_pending_message()
    if proxy_mode == 'none':
        return telegram_api_direct_recovery_message()
    return telegram_api_recovery_message(proxy_mode)


def protocol_status_is_pending(protocol_status):
    status = protocol_status or {}
    if status.get('api_ok') is True:
        return False
    if status.get('api_pending'):
        return True
    if (
        status.get('tone') == 'warn' and
        status.get('api_ok') is not True and
        not str(status.get('api_message') or '').strip()
    ):
        return True
    label = str(status.get('label') or '').casefold()
    details = str(status.get('details') or '').casefold()
    pending_markers = (
        'проверяется',
        'фоновая проверка',
        'статус обновится',
    )
    return any(marker in label or marker in details for marker in pending_markers)


def protocol_preflight_status(key_value, endpoint_ok, endpoint_message, *, proxy_user_label='Бот', xray_required=False):
    if not str(key_value or '').strip():
        return {
            'tone': 'empty',
            'label': 'Не сохранён',
            'details': 'Ключ ещё не сохранён на роутере',
        }
    if not endpoint_ok:
        return {
            'tone': 'fail',
            'label': 'Не работает',
            'details': f'{endpoint_message} {proxy_user_label} не может использовать этот ключ',
        }
    if xray_required:
        return {
            'tone': 'warn',
            'label': 'Требует Xray',
            'details': (f'{endpoint_message} Этот ключ использует VLESS Reality/XTLS и должен работать через Xray, '
                        'а сейчас активен V2Ray. Локальный SOCKS поднят, но внешний трафик через ключ может не пройти.'),
        }
    return None


def api_status_from_protocol(proxy_mode, protocol_status, socks_ok, is_transient):
    status = protocol_status or {}
    has_api_result = 'api_ok' in status or 'api_message' in status
    api_ok = bool(status.get('api_ok'))
    api_message = str(status.get('api_message', '') or '')
    if api_ok:
        return telegram_api_success_message()
    if protocol_status_is_pending(status):
        return telegram_api_refresh_message()
    if socks_ok and is_transient(api_message):
        return telegram_api_pending_message()
    if not has_api_result:
        api_message = str((protocol_status or {}).get('details') or '').strip() or 'нет результата проверки'
    if proxy_mode == 'none':
        return telegram_api_direct_recovery_message()
    return telegram_api_recovery_message(proxy_mode)


def build_web_status_snapshot(
    *,
    state_label,
    proxy_mode,
    protocols,
    ports,
    check_socks5,
    check_telegram_api,
    is_transient,
    fallback_reason,
):
    socks_details = ''
    socks_ok = False
    protocols = protocols if isinstance(protocols, dict) else {}
    current_protocol = protocols.get(proxy_mode)
    if current_protocol and proxy_mode in PROXY_PROTOCOLS:
        socks_ok = bool(current_protocol.get('endpoint_ok'))
        socks_details = current_protocol.get('endpoint_message', '')
        api_status = api_status_from_protocol(proxy_mode, current_protocol, socks_ok, is_transient)
    elif proxy_mode in PROXY_PROTOCOLS:
        port = ports.get(proxy_mode)
        if port:
            socks_ok = check_socks5(port)
            socks_state = 'доступен' if socks_ok else 'не отвечает как SOCKS5'
            socks_details = f'Локальный SOCKS {proxy_mode} 127.0.0.1:{port}: {socks_state}'
        api_status = api_status_from_runtime_check(
            proxy_mode,
            check_telegram_api(retries=0, retry_delay=0, connect_timeout=5, read_timeout=8),
            socks_ok,
            is_transient,
        )
    else:
        api_status = api_status_from_runtime_check(
            'none',
            check_telegram_api(retries=0, retry_delay=0, connect_timeout=5, read_timeout=8),
            False,
            is_transient,
        )
    return {
        'state_label': state_label,
        'proxy_mode': proxy_mode,
        'api_status': api_status,
        'socks_details': socks_details,
        'fallback_reason': fallback_reason,
    }
