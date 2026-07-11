"""Small curl-based HTTP checks used only by the disposable pool worker."""

import json
import os
import subprocess
import tempfile
import time
from urllib.parse import urlparse

from custom_check_policy import CUSTOM_TARGET_DENY_MARKERS


CURL_BINARY = '/opt/bin/curl'
_CODE_MARKER = b'\n__BK_HTTP_CODE__'
_URL_MARKER = b'\n__BK_URL__'


def _proxy_url(value):
    parsed = urlparse(str(value or '').strip())
    if not parsed.hostname:
        raise ValueError('SOCKS proxy is not configured')
    return f'socks5h://{parsed.hostname}:{int(parsed.port or 1080)}'


def _run_curl(proxy_url, url, connect_timeout, read_timeout, *, body_limit=4096, user_agent='', command_runner=subprocess.run):
    timeout = max(1.0, float(connect_timeout or 0) + float(read_timeout or 0))
    body_limit = max(0, int(body_limit or 0))
    body_path = ''
    body = b''
    args = [
        CURL_BINARY,
        '--silent', '--show-error', '--location', '--max-redirs', '3',
        '--proxy', _proxy_url(proxy_url),
        '--noproxy', '',
        '--connect-timeout', str(max(1.0, float(connect_timeout or 0))),
        '--max-time', str(timeout),
        '--range', f'0-{max(0, body_limit - 1)}',
        '--write-out', '\n__BK_HTTP_CODE__%{http_code}\n__BK_URL__%{url_effective}',
    ]
    if user_agent:
        args.extend(('--user-agent', str(user_agent)))
    # Keep even authenticated URLs out of the process argument list.
    args.extend(('--config', '-'))
    curl_config = ('url = ' + json.dumps(str(url or ''), ensure_ascii=True) + '\n').encode('utf-8')
    try:
        temp_dir = '/tmp' if os.path.isdir('/tmp') else None
        body_fd, body_path = tempfile.mkstemp(prefix='bypass_pool_curl_', dir=temp_dir)
        os.close(body_fd)
        args.extend(('--output', body_path))
        completed = command_runner(
            args,
            input=curl_config,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except Exception:
        if body_path:
            try:
                os.remove(body_path)
            except OSError:
                pass
        return 0, '', b'', 'curl could not start'
    try:
        output = completed.stdout if isinstance(completed.stdout, bytes) else str(completed.stdout or '').encode('utf-8')
        if _CODE_MARKER not in output:
            if int(getattr(completed, 'returncode', 1) or 0) == 28:
                return 0, '', b'', 'request timed out'
            return 0, '', b'', f'curl exited with code {int(getattr(completed, "returncode", 1) or 1)}'
        if int(getattr(completed, 'returncode', 1) or 0) != 0:
            return 0, '', b'', f'curl exited with code {int(getattr(completed, "returncode", 1) or 1)}'
        try:
            with open(body_path, 'rb') as body_file:
                body = body_file.read(body_limit)
        except OSError:
            return 0, '', b'', 'curl response body could not be read'
        trailer = output.rsplit(_CODE_MARKER, 1)[1]
        code_raw, separator, final_url = trailer.partition(_URL_MARKER)
        try:
            status_code = int(code_raw.decode('ascii', errors='ignore').strip() or '0')
        except ValueError:
            status_code = 0
        if not separator:
            return 0, '', body, 'curl response metadata is incomplete'
        return status_code, final_url.decode('utf-8', errors='ignore').strip(), body, ''
    finally:
        if body_path:
            try:
                os.remove(body_path)
            except OSError:
                pass


def check_http_through_proxy(proxy_url, url, connect_timeout=2, read_timeout=3):
    status_code, _final_url, _body, error = _run_curl(proxy_url, url, connect_timeout, read_timeout)
    if error:
        return False, 'Web check through the key failed: ' + error
    if 0 < status_code < 500:
        return True, f'Web access through the key confirmed (HTTP {status_code}).'
    return False, f'Web check through the key returned HTTP {status_code}.'


def check_custom_target_through_proxy(normalize_url, proxy_url, url, connect_timeout=2, read_timeout=3):
    try:
        target_url = normalize_url(url)
    except ValueError as exc:
        return False, str(exc)
    status_code, final_url, body, error = _run_curl(
        proxy_url,
        target_url,
        connect_timeout,
        read_timeout,
        user_agent='bypass_keenetic health check',
    )
    target_name = urlparse(target_url).netloc
    if error:
        return False, 'Service check failed: ' + error
    response_text = body.decode('utf-8', errors='ignore').lower()
    denied = any(marker in final_url.lower() or marker in response_text for marker in CUSTOM_TARGET_DENY_MARKERS)
    if denied:
        return False, f'{target_name} returned a regional restriction (HTTP {status_code}).'
    if status_code <= 0 or status_code in (403, 451) or status_code >= 500:
        return False, f'{target_name} returned HTTP {status_code}.'
    return True, f'Access to {target_name} confirmed (HTTP {status_code}).'


def check_telegram_api(authenticated, proxy_url, connect_timeout=6, read_timeout=10):
    token = ''
    if authenticated:
        try:
            import bot_config as config

            token = str(getattr(config, 'token', '') or '').strip()
        except Exception:
            token = ''
        if not token:
            return False, 'Telegram API authentication is not configured.'
    url = f'https://api.telegram.org/bot{token}/getMe' if authenticated else 'https://api.telegram.org/'
    status_code, _final_url, body, error = _run_curl(proxy_url, url, connect_timeout, read_timeout)
    if error:
        return False, 'Telegram API check failed: ' + error
    if not authenticated:
        return (0 < status_code < 500), f'Telegram API returned HTTP {status_code}.'
    try:
        payload = json.loads(body.decode('utf-8', errors='replace'))
    except (TypeError, ValueError):
        payload = {}
    if status_code < 400 and payload.get('ok'):
        return True, 'Telegram API is reachable.'
    return False, f'Telegram API returned HTTP {status_code}.'


def measure_download(proxy_url, settings):
    bytes_limit = int(settings.get('quality_bytes') or 0)
    if bytes_limit <= 0:
        return None, 'quality download sample is disabled'
    url = str(settings.get('quality_url') or '').replace('{bytes}', str(bytes_limit))
    started_at = time.monotonic()
    status_code, _final_url, body, error = _run_curl(
        proxy_url,
        url,
        settings.get('quality_connect'),
        settings.get('quality_read'),
        body_limit=bytes_limit,
        user_agent='bypass_keenetic quality check',
    )
    if error:
        return None, error
    if status_code <= 0 or status_code >= 500:
        return None, f'quality download returned HTTP {status_code}'
    received = len(body)
    if received < min(bytes_limit, 32768):
        return None, f'quality download sample too short: {received} bytes'
    return round((received * 8.0) / max(0.001, time.monotonic() - started_at) / 1000000.0, 2), ''
