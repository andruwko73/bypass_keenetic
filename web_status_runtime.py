PROXY_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')


def telegram_api_success_message():
    return '✅ Доступ к api.telegram.org подтверждён.'


def telegram_api_pending_message():
    return (
        '⏳ Telegram API не ответил вовремя через текущий режим. '
        'Локальный SOCKS работает, идёт повторная проверка. '
        'Статус обновится без перезагрузки страницы.'
    )


def api_status_from_protocol(proxy_mode, protocol_status, socks_ok, is_transient):
    api_ok = bool((protocol_status or {}).get('api_ok'))
    api_message = str((protocol_status or {}).get('api_message', '') or '')
    if api_ok:
        return telegram_api_success_message()
    if socks_ok and is_transient(api_message):
        return telegram_api_pending_message()
    if proxy_mode == 'none':
        return f'❌ Прямой доступ к api.telegram.org не проходит: {api_message}'
    return f'❌ Доступ к Telegram API через режим {proxy_mode} не проходит: {api_message}'


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
        api_status = check_telegram_api(retries=0, retry_delay=0, connect_timeout=5, read_timeout=8)
        if proxy_mode != 'none' and socks_ok and not api_status.startswith('✅') and is_transient(api_status):
            api_status = telegram_api_pending_message()
    else:
        api_status = check_telegram_api(retries=0, retry_delay=0, connect_timeout=5, read_timeout=8)
    return {
        'state_label': state_label,
        'proxy_mode': proxy_mode,
        'api_status': api_status,
        'socks_details': socks_details,
        'fallback_reason': fallback_reason,
    }
