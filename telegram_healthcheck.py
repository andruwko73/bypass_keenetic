import time


TELEGRAM_HEALTHCHECK_URLS = (
    'https://web.telegram.org/',
    'https://t.me/',
)
TELEGRAM_HEALTHCHECK_MIN_OK = 1


def _elapsed_ms(started_at):
    return max(0, int(round((time.monotonic() - started_at) * 1000)))


def check_telegram_service_through_proxy(
    check_telegram_api,
    check_http,
    proxy_url,
    *,
    telegram_timeouts,
    http_timeouts,
    urls=TELEGRAM_HEALTHCHECK_URLS,
    min_ok=TELEGRAM_HEALTHCHECK_MIN_OK,
    metrics=None,
    allow_app_endpoints_without_api=True,
):
    started_at = time.monotonic()
    tg_connect, tg_read = telegram_timeouts
    api_ok, api_message = check_telegram_api(
        proxy_url,
        connect_timeout=tg_connect,
        read_timeout=tg_read,
    )

    connect_timeout, read_timeout = http_timeouts
    ok_hosts = []
    failed = []
    for url in urls or TELEGRAM_HEALTHCHECK_URLS:
        host = url.split('/')[2] if '://' in url else url
        ok, message = check_http(
            proxy_url,
            url=url,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )
        if ok:
            ok_hosts.append(host)
            if len(ok_hosts) >= max(1, int(min_ok or 1)):
                if metrics is not None:
                    metrics['tg_latency_ms'] = _elapsed_ms(started_at)
                if api_ok:
                    return True, 'Telegram endpoints confirmed: ' + ', '.join(ok_hosts)
                if allow_app_endpoints_without_api:
                    return True, 'Telegram app endpoints confirmed: ' + ', '.join(ok_hosts)
                return False, api_message
        else:
            failed.append(f'{host}: {message}')
    if not api_ok:
        return False, api_message
    return False, '; '.join(failed[-2:]) or 'Telegram web endpoints did not respond through this key.'
