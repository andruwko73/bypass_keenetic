import socket
import time
from urllib.parse import urlparse


TELEGRAM_HEALTHCHECK_URLS = (
    'https://web.telegram.org/',
    'https://t.me/',
)
TELEGRAM_APP_TCP_ENDPOINTS = (
    ('149.154.167.50', 443),
    ('149.154.175.50', 443),
    ('91.108.56.170', 443),
)
TELEGRAM_HEALTHCHECK_MIN_OK = 1
TELEGRAM_TRANSIENT_FAILURE_MARKERS = (
    'timeout',
    'timed out',
    'max retries',
    'temporarily',
    'temporary failure',
    'connection reset',
    'remote disconnected',
    'unexpected eof',
    'не ответил',
    'вовремя',
    'таймаут',
    'врем',
    'разорвал',
)


def _elapsed_ms(started_at):
    return max(0, int(round((time.monotonic() - started_at) * 1000)))


def telegram_failure_is_transient(message):
    text = str(message or '').strip().lower()
    return bool(text and any(marker in text for marker in TELEGRAM_TRANSIENT_FAILURE_MARKERS))


def _recv_exact(sock, length):
    data = b''
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise OSError('SOCKS proxy closed connection')
        data += chunk
    return data


def _socks5_connect(proxy_host, proxy_port, target_host, target_port, timeout):
    with socket.create_connection((proxy_host, int(proxy_port)), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(b'\x05\x01\x00')
        reply = _recv_exact(sock, 2)
        if reply != b'\x05\x00':
            raise OSError('SOCKS proxy does not allow no-auth connect')

        try:
            address = socket.inet_aton(target_host)
            request = b'\x05\x01\x00\x01' + address
        except OSError:
            encoded = str(target_host).encode('idna')
            if len(encoded) > 255:
                raise OSError('target host is too long')
            request = b'\x05\x01\x00\x03' + bytes([len(encoded)]) + encoded
        request += int(target_port).to_bytes(2, 'big')
        sock.sendall(request)

        header = _recv_exact(sock, 4)
        if len(header) != 4 or header[0] != 5:
            raise OSError('invalid SOCKS reply')
        if header[1] != 0:
            raise OSError(f'SOCKS connect failed with code {header[1]}')
        atyp = header[3]
        if atyp == 1:
            _recv_exact(sock, 4)
        elif atyp == 3:
            size = _recv_exact(sock, 1)[0]
            _recv_exact(sock, size)
        elif atyp == 4:
            _recv_exact(sock, 16)
        else:
            raise OSError('invalid SOCKS address type')
        _recv_exact(sock, 2)


def check_telegram_app_tcp_through_proxy(
    proxy_url,
    *,
    endpoints=TELEGRAM_APP_TCP_ENDPOINTS,
    connect_timeout=1.2,
):
    parsed = urlparse(str(proxy_url or ''))
    if parsed.scheme not in ('socks5', 'socks5h') or not parsed.hostname or not parsed.port:
        return False, 'Telegram app TCP probe requires a SOCKS5 proxy.'

    failures = []
    timeout = max(0.2, float(connect_timeout or 1.2))
    for host, port in endpoints or TELEGRAM_APP_TCP_ENDPOINTS:
        try:
            _socks5_connect(parsed.hostname, parsed.port, host, int(port), timeout)
            return True, f'Telegram app TCP endpoint confirmed: {host}:{int(port)}'
        except Exception as exc:
            failures.append(f'{host}:{int(port)} {str(exc).splitlines()[0][:80]}')
    return False, '; '.join(failures[-2:]) or 'Telegram app TCP endpoints did not respond through this key.'


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
    check_app_tcp=check_telegram_app_tcp_through_proxy,
    app_tcp_endpoints=TELEGRAM_APP_TCP_ENDPOINTS,
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
    if allow_app_endpoints_without_api and callable(check_app_tcp):
        app_ok, app_message = check_app_tcp(
            proxy_url,
            endpoints=app_tcp_endpoints,
            connect_timeout=min(connect_timeout, read_timeout),
        )
        if app_ok:
            if metrics is not None:
                metrics['tg_latency_ms'] = _elapsed_ms(started_at)
            return True, app_message
        failed.append(app_message)
    if not api_ok:
        return False, api_message
    return False, '; '.join(failed[-2:]) or 'Telegram web endpoints did not respond through this key.'
