#!/usr/bin/python3
"""Small one-shot worker for Telegram and YouTube health checks."""

import json
import os
import re
import sys
import time


_TOKEN_PATH_RE = re.compile(r'/bot[^/\s]+/', re.I)
_PROXY_KEY_RE = re.compile(r'\b(?:vless|vmess|trojan|ss)://[^\s]+', re.I)


def _read_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            value = json.load(file)
        return value
    except Exception:
        return default


def _write_json(path, value):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temporary = f'{path}.tmp.{os.getpid()}'
    try:
        with open(temporary, 'w', encoding='utf-8') as file:
            json.dump(value, file, ensure_ascii=False, separators=(',', ':'))
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
    finally:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass
        except Exception:
            pass


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except Exception:
        pass


def _status_value(name):
    try:
        with open('/proc/self/status', 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                if line.startswith(name + ':'):
                    fields = line.split()
                    return int(fields[1]) if len(fields) > 1 else 0
    except Exception:
        pass
    return 0


def _redact(value):
    text = str(value or '')
    text = _TOKEN_PATH_RE.sub('/bot<redacted-token>/', text)
    text = _PROXY_KEY_RE.sub('<redacted-key>', text)
    return text.splitlines()[0][:240]


def _requests():
    import requests

    return requests


def _session():
    requests = _requests()
    session = requests.Session()
    session.trust_env = False
    return requests, session


def _check_telegram(payload):
    requests, session = _session()
    try:
        authenticated = bool(payload.get('authenticated'))
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
        proxy_url = str(payload.get('proxy_url') or '').strip()
        proxies = {'https': proxy_url, 'http': proxy_url} if proxy_url else None
        response = session.get(
            url,
            timeout=(
                float(payload.get('connect_timeout') or 6),
                float(payload.get('read_timeout') or 10),
            ),
            proxies=proxies,
        )
        if not authenticated:
            if response.status_code < 500:
                return True, 'Telegram API is reachable.'
            response.raise_for_status()
        response.raise_for_status()
        data = response.json()
        if data.get('ok'):
            return True, 'Telegram API is reachable.'
        return False, f'Telegram API replied: {data.get("description", "unknown error")}.'
    except requests.exceptions.ConnectTimeout:
        return False, 'Proxy did not connect to api.telegram.org in time.'
    except requests.exceptions.ReadTimeout:
        return False, 'Telegram API did not respond in time through this key.'
    except requests.exceptions.RequestException as exc:
        error_text = _redact(exc)
        if 'Missing dependencies for SOCKS support' in error_text:
            return False, 'SOCKS support is unavailable for the Telegram API check.'
        return False, f'Telegram API check failed: {error_text}'
    finally:
        session.close()


def _youtube_http_check(proxy_url, *, session, requests):
    proxies = {'https': proxy_url, 'http': proxy_url} if proxy_url else None

    def check(_unused_proxy_url, *, url, connect_timeout, read_timeout):
        try:
            response = session.get(
                url,
                timeout=(float(connect_timeout), float(read_timeout)),
                proxies=proxies,
            )
            return True, f'HTTP {response.status_code}'
        except requests.exceptions.RequestException as exc:
            return False, _redact(exc)

    return check


def _check_youtube(payload):
    from youtube_healthcheck import check_youtube_through_proxy

    requests, session = _session()
    try:
        connect_timeout = float(payload.get('connect_timeout') or 6)
        read_timeout = float(payload.get('read_timeout') or 10)
        metrics = {}
        ok, message = check_youtube_through_proxy(
            _youtube_http_check(str(payload.get('proxy_url') or '').strip(), session=session, requests=requests),
            str(payload.get('proxy_url') or '').strip() or None,
            urls=tuple(payload.get('urls') or ()),
            min_ok=int(payload.get('min_ok') or 1),
            http_timeouts=(connect_timeout, read_timeout),
            http_retry_timeouts=(connect_timeout, read_timeout),
            retry_delay_seconds=float(payload.get('retry_delay_seconds') or 0),
            metrics=metrics,
            sleep=time.sleep,
        )
        return bool(ok), _redact(message), {
            str(key): value
            for key, value in metrics.items()
            if isinstance(value, (bool, int, float, str)) or value is None
        }
    finally:
        session.close()


def run_health_check_worker(input_path, result_path):
    payload = _read_json(input_path, {})
    _remove(input_path)
    if not isinstance(payload, dict):
        payload = {}
    result = {
        'ok': False,
        'message': '',
        'metrics': {},
        'error': '',
        'rss_before_kb': _status_value('VmRSS'),
        'rss_after_kb': 0,
        'hwm_kb': 0,
    }
    exit_code = 0
    try:
        kind = str(payload.get('kind') or '').strip().lower()
        if kind == 'telegram':
            result['ok'], result['message'] = _check_telegram(payload)
        elif kind == 'youtube':
            result['ok'], result['message'], result['metrics'] = _check_youtube(payload)
        else:
            result['error'] = f'unsupported health check kind: {kind}'
            exit_code = 1
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {_redact(exc)}'
        exit_code = 1
    finally:
        result['rss_after_kb'] = _status_value('VmRSS')
        result['hwm_kb'] = _status_value('VmHWM')
        try:
            _write_json(result_path, result)
        except Exception:
            pass
    return exit_code


if __name__ == '__main__':
    sys.exit(run_health_check_worker(sys.argv[1], sys.argv[2]))
