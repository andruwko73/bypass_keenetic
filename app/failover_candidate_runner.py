#!/usr/bin/python3
"""Short-lived candidate selector that never imports the long-running bot."""

import json
import os
import sys
import time

from health_check_runner import _check_telegram, _redact, _status_value
from pool_probe_runner import cleanup_pool_probe_runtime, find_pool_failover_candidate
from probe_cache import record_key_probe
from proxy_protocols import proxy_outbound_from_key
from proxy_status import check_http_through_proxy, wait_for_socks5_handshake, check_custom_target_through_proxy
from custom_checks_store import normalize_check_url
from failover_services import check_required, record_required, service_label


def _check_custom(proxy_url, url, **kwargs):
    return check_custom_target_through_proxy(normalize_check_url, proxy_url, url, **kwargs)


def _read_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file)
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
        except OSError:
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


def _as_candidates(payload):
    return [
        (str(item[0] or ''), str(item[1] or ''))
        for item in (payload.get('candidates') or [])
        if isinstance(item, (list, tuple)) and len(item) >= 2 and str(item[0] or '').strip() and str(item[1] or '').strip()
    ]


def _telegram_check(authenticated):
    def check(proxy_url, *, connect_timeout, read_timeout):
        return _check_telegram({
            'authenticated': bool(authenticated),
            'proxy_url': str(proxy_url or ''),
            'connect_timeout': float(connect_timeout or 0),
            'read_timeout': float(read_timeout or 0),
        })

    return check


def run_failover_candidate_worker(input_path, result_path):
    payload = _read_json(input_path, {})
    _remove(input_path)
    if not isinstance(payload, dict):
        payload = {}
    service = str(payload.get('service') or 'telegram').strip().lower()
    if service not in ('telegram', 'youtube'):
        service = 'telegram'
    result = {
        'ok': False,
        'candidate': None,
        'error': '',
        'rss_before_kb': _status_value('VmRSS'),
        'rss_after_kb': 0,
        'hwm_kb': 0,
        'events': [],
    }
    exit_code = 1
    try:
        telegram_timeouts = tuple(payload.get('telegram_timeouts') or (2, 3))
        http_timeouts = tuple(payload.get('http_timeouts') or (2, 3))
        deadline = time.monotonic() + max(1, min(120, float(payload.get('budget_seconds') or 60)))
        contracts = payload.get('service_contracts')
        if not isinstance(contracts, dict):
            raise ValueError('Missing failover service contracts')
        def log(message):
            if len(result['events']) < 12:
                result['events'].append(_redact(message)[:200])
        if payload.get('confirmation_proxy'):
            proto, key_value = _as_candidates(payload)[0]
            verdict, rejected, values = check_required(
                payload['confirmation_proxy'], contracts[proto], primary=service,
                check_telegram=_telegram_check(payload.get('telegram_authenticated')),
                check_http=check_http_through_proxy, check_custom=_check_custom,
                timeouts=http_timeouts, deadline=deadline,
            )
            record_required(record_key_probe, proto, key_value, contracts[proto], values, kind='runtime')
            if verdict is not True:
                log(f'Auto-failover: постоянная проверка сервиса {service_label(rejected)}: '
                    + ('недоступна.' if verdict is None else 'неуспешна.'))
            candidate = (proto, key_value, None, None) if verdict is True else None
        else:
            candidate = find_pool_failover_candidate(
                _as_candidates(payload),
                service=service,
                batch_size=max(1, int(payload.get('batch_size') or 1)),
                test_port=str(payload.get('test_port') or 10900),
                proxy_outbound_from_key=proxy_outbound_from_key,
                wait_for_socks5=wait_for_socks5_handshake,
                check_telegram_api=_telegram_check(payload.get('telegram_authenticated')),
                check_http=check_http_through_proxy,
                record_key_probe=record_key_probe,
                proto_label=lambda proto: str(proto or ''),
                log=log,
                telegram_timeouts=(float(telegram_timeouts[0]), float(telegram_timeouts[1])),
                http_timeouts=(float(http_timeouts[0]), float(http_timeouts[1])),
                youtube_profile=str(payload.get('youtube_profile') or 'confirm'),
                youtube_retry_unstable=bool(payload.get('youtube_retry_unstable', True)),
                youtube_quality_settings=(
                    dict(payload.get('youtube_quality_settings') or {})
                    if isinstance(payload.get('youtube_quality_settings'), dict)
                    else None
                ),
                collect_garbage=lambda: 0,
                service_contracts=contracts,
                check_custom=_check_custom,
                deadline=deadline,
            )
        if candidate:
            proto, key_value, tg_ok, yt_ok = candidate
            result.update({'ok': True, 'candidate': [proto, key_value, tg_ok, yt_ok]})
            exit_code = 0
        else:
            exit_code = 2
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {_redact(exc)}'
    finally:
        if not payload.get('confirmation_proxy'):
            cleanup_pool_probe_runtime(kill_processes=True)
        result['rss_after_kb'] = _status_value('VmRSS')
        result['hwm_kb'] = _status_value('VmHWM')
        try:
            _write_json(result_path, result)
        except Exception:
            pass
    return exit_code


if __name__ == '__main__':
    sys.exit(run_failover_candidate_worker(sys.argv[1], sys.argv[2]))
