import os
import time

YOUTUBE_HEALTHCHECK_URLS = (
    'https://www.youtube.com/generate_204',
    'https://redirector.googlevideo.com/generate_204',
    'https://i.ytimg.com/generate_204',
    'https://www.youtube.com',
)
YOUTUBE_HEALTHCHECK_MIN_OK = 2
YOUTUBE_HEALTHCHECK_REQUIRED_URLS = (YOUTUBE_HEALTHCHECK_URLS[0],)


def check_youtube_health(check_http, proxy_url, *, timeouts, urls=YOUTUBE_HEALTHCHECK_URLS, min_ok=YOUTUBE_HEALTHCHECK_MIN_OK):
    ok_count = 0
    ok_urls = set()
    last_message = ''
    connect_timeout, read_timeout = timeouts
    required_urls = set(YOUTUBE_HEALTHCHECK_REQUIRED_URLS)
    for url in urls:
        ok, message = check_http(
            proxy_url,
            url=url,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )
        if ok:
            ok_count += 1
            ok_urls.add(url)
            if required_urls <= ok_urls and ok_count >= max(1, int(min_ok or 1)):
                return True, 'YouTube endpoints confirmed'
        else:
            last_message = message
    missing_required = required_urls - ok_urls
    if missing_required:
        return False, 'Primary YouTube connectivity endpoint did not respond through this key.'
    return False, last_message or 'YouTube endpoints did not respond through this key.'


def proxy_apply_settings(core_service_script, ports):
    core_restart = core_service_script + ' restart'
    return {
        'shadowsocks': {
            'label': 'Shadowsocks',
            'port': ports['shadowsocks'],
            'restart_cmds': ['/opt/etc/init.d/S22shadowsocks restart', core_restart],
            'startup_wait': 8,
        },
        'vmess': {
            'label': 'Vmess',
            'port': ports['vmess'],
            'restart_cmds': [core_restart],
            'startup_wait': 18,
        },
        'vless': {
            'label': 'Vless 1',
            'port': ports['vless'],
            'restart_cmds': [core_restart],
            'startup_wait': 18,
        },
        'vless2': {
            'label': 'Vless 2',
            'port': ports['vless2'],
            'restart_cmds': [core_restart],
            'startup_wait': 18,
        },
        'trojan': {
            'label': 'Trojan',
            'port': ports['trojan'],
            'restart_cmds': ['/opt/etc/init.d/S22trojan restart', core_restart],
            'startup_wait': 8,
        },
    }


def apply_installed_proxy_runtime(
    key_type,
    key_value,
    *,
    settings,
    app_mode_noun,
    load_proxy_mode,
    proxy_mode_label,
    proxy_url_getter,
    build_diagnostics,
    ensure_service_port,
    check_local_endpoint,
    check_telegram_api,
    check_http=None,
    record_key_probe=None,
    youtube_route_protocol_getter=None,
    verify=True,
    run_command=os.system,
    sleep=time.sleep,
    telegram_timeouts=(10, 15),
    youtube_timeouts=(3, 5),
):
    current = settings[key_type]
    active_mode = load_proxy_mode()
    active_label = proxy_mode_label(active_mode)
    for command in current['restart_cmds']:
        run_command(command)

    diagnostics = build_diagnostics(key_type, key_value)
    restart_cmd = current['restart_cmds'][-1]
    if not ensure_service_port(
        current['port'],
        restart_cmd,
        retries=2,
        sleep_after_restart=3,
        timeout=current['startup_wait'],
    ):
        return (f'⚠️ {current["label"]} ключ сохранён, но локальный порт 127.0.0.1:{current["port"]} '
                f'не поднялся. Текущий {app_mode_noun} {active_label} сохранён. {diagnostics}').strip()

    endpoint_ok, endpoint_message = check_local_endpoint(key_type, current['port'])
    if not endpoint_ok:
        return (f'⚠️ {current["label"]} ключ сохранён, но {endpoint_message} '
                f'Текущий {app_mode_noun} {active_label} сохранён. {diagnostics}').strip()

    if not verify:
        return (f'✅ {current["label"]} ключ сохранён. {endpoint_message} '
                'Проверка Telegram API и YouTube выполняется в фоне; '
                f'статус обновится без перезагрузки страницы. Текущий {app_mode_noun} {active_label} сохранён.').strip()

    proxy_url = proxy_url_getter(key_type)
    youtube_route_proto = youtube_route_protocol_getter() if callable(youtube_route_protocol_getter) else 'vless2'
    if key_type == youtube_route_proto and active_mode != key_type and check_http is not None:
        yt_ok, yt_probe_message = check_youtube_health(
            check_http,
            proxy_url,
            timeouts=youtube_timeouts,
        )
        if record_key_probe is not None:
            record_key_probe(key_type, key_value, tg_ok=None, yt_ok=yt_ok)
        if yt_ok:
            return (f'✅ {current["label"]} ключ сохранён. {endpoint_message} '
                    f'YouTube через этот ключ подтверждён. Telegram не проверялся, потому что текущий {app_mode_noun} {active_label}.').strip()
        return (f'⚠️ {current["label"]} ключ сохранён. {endpoint_message} '
                f'Но YouTube не проходит через этот ключ: {yt_probe_message} '
                f'Текущий {app_mode_noun} {active_label} сохранён. {diagnostics}').strip()

    api_ok, api_probe_message = check_telegram_api(
        proxy_url,
        connect_timeout=telegram_timeouts[0],
        read_timeout=telegram_timeouts[1],
    )
    if check_http is not None and record_key_probe is not None:
        yt_ok, _ = check_youtube_health(
            check_http,
            proxy_url,
            timeouts=youtube_timeouts,
        )
        record_key_probe(key_type, key_value, tg_ok=api_ok, yt_ok=yt_ok)
    elif record_key_probe is not None:
        record_key_probe(key_type, key_value, tg_ok=api_ok)

    if api_ok:
        return (f'✅ {current["label"]} ключ сохранён. {endpoint_message} '
                f'Доступ к Telegram API через этот ключ подтверждён. '
                f'Текущий {app_mode_noun} {active_label} сохранён.').strip()
    return (f'⚠️ {current["label"]} ключ сохранён. {endpoint_message} '
            f'Но Telegram API не проходит через этот ключ. '
            f'Текущий {app_mode_noun} {active_label} сохранён. '
            f'❌ Не удалось подключиться к Telegram API: {api_probe_message} {diagnostics}').strip()
