import os
import requests
import socket
import subprocess
import time
from urllib.parse import urlparse


TRANSIENT_STATUS_MARKERS = (
    'network is unreachable',
    'timed out',
    'timeout',
    'таймаут',
    'не ответил вовремя',
    'за отведённое время',
    'за отведенное время',
    'max retries exceeded',
    'failed to establish a new connection',
    'connection reset',
)


def wait_for_port(hosts, port, timeout=15, *, sleep=time.sleep):
    if hosts is None:
        hosts = ['127.0.0.1', '::1', 'localhost']
    elif isinstance(hosts, str):
        hosts = [hosts]
    deadline = time.time() + timeout
    while time.time() < deadline:
        for host in hosts:
            try:
                addrs = socket.getaddrinfo(host, int(port), type=socket.SOCK_STREAM)
            except OSError:
                continue
            for family, socktype, proto, canonname, sockaddr in addrs:
                try:
                    with socket.socket(family, socktype, proto) as sock:
                        sock.settimeout(2)
                        sock.connect(sockaddr)
                        return True
                except OSError:
                    continue
        sleep(1)
    return False


def port_is_listening(port, *, command_runner=subprocess.check_output):
    for command in (['netstat', '-ltn'], ['ss', '-ltn']):
        try:
            output = command_runner(command, stderr=subprocess.DEVNULL, text=True)
            if any(f':{port} ' in line or line.endswith(f':{port}') for line in output.splitlines()):
                return True
        except Exception:
            pass
    return False


def check_socks5_handshake(port, timeout=3):
    try:
        with socket.create_connection(('127.0.0.1', int(port)), timeout=timeout) as sock:
            sock.sendall(b'\x05\x01\x00')
            return sock.recv(2) == b'\x05\x00'
    except Exception:
        return False


def wait_for_socks5_handshake(port, timeout=20, *, sleep=time.sleep):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check_socks5_handshake(port):
            return True
        sleep(1)
    return False


def ensure_service_port(port, restart_cmd=None, retries=2, sleep_after_restart=5, timeout=20, *, system_runner=os.system):
    if wait_for_port(None, port, timeout=timeout) or port_is_listening(port):
        return True
    if restart_cmd:
        for _ in range(retries):
            system_runner(restart_cmd)
            time.sleep(sleep_after_restart)
            if wait_for_port(None, port, timeout=timeout) or port_is_listening(port):
                return True
    return False


def read_tail(file_path, lines=12):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.readlines()
        return ''.join(content[-lines:]).strip() if content else ''
    except Exception as exc:
        return f'Не удалось прочитать {file_path}: {exc}'


def is_transient_status_text(status_text):
    text = str(status_text or '').casefold()
    return any(marker in text for marker in TRANSIENT_STATUS_MARKERS)


def custom_checks_signature(custom_checks, *, include_urls=False):
    if include_urls:
        return tuple((item.get('id'), tuple(item.get('urls') or [item.get('url')])) for item in custom_checks or [])
    return tuple((item.get('id'), item.get('url')) for item in custom_checks or [])


def status_snapshot_signature(current_keys, custom_checks=None, *, include_custom_urls=False):
    key_signature = tuple((name, current_keys.get(name, '')) for name in sorted(current_keys))
    if custom_checks is None:
        return key_signature
    return (key_signature, custom_checks_signature(custom_checks, include_urls=include_custom_urls))


def active_mode_status_signature(proxy_mode, current_keys, custom_checks=None):
    return (
        proxy_mode,
        current_keys.get(proxy_mode, ''),
        custom_checks_signature(custom_checks, include_urls=True),
    )


def cached_snapshot(cache, signature, ttl, *, now=None):
    now = time.time() if now is None else now
    if (
        cache.get('data') is not None and
        cache.get('signature') == signature and
        now - cache.get('timestamp', 0) < ttl
    ):
        return cache.get('data')
    return None


def store_snapshot(cache, signature, snapshot, *, now=None):
    cache['timestamp'] = time.time() if now is None else now
    cache['data'] = snapshot
    cache['signature'] = signature
    return snapshot


def cached_active_status(cache, signature, ttl, lock, *, now=None):
    now = time.time() if now is None else now
    with lock:
        if (
            cache.get('status') is not None and
            cache.get('signature') == signature and
            now - cache.get('timestamp', 0) < ttl
        ):
            return dict(cache.get('status'))
    return None


def store_active_status(cache, signature, status, lock, *, now=None):
    if not isinstance(status, dict):
        return
    with lock:
        cache['timestamp'] = time.time() if now is None else now
        cache['signature'] = signature
        cache['status'] = dict(status)


def placeholder_protocol_statuses(current_keys, *, pending_details=None):
    pending_details = pending_details or 'Фоновая проверка ключа выполняется. Обновите страницу через несколько секунд.'
    result = {}
    for key_name, key_value in current_keys.items():
        if str(key_value or '').strip():
            result[key_name] = {
                'tone': 'warn',
                'label': 'Проверяется',
                'details': pending_details,
            }
        else:
            result[key_name] = {
                'tone': 'empty',
                'label': 'Не сохранён',
                'details': 'Ключ ещё не сохранён на роутере.',
            }
    return result


def protocol_error_status(exc):
    return {
        'tone': 'warn',
        'label': 'Ошибка проверки',
        'details': f'Не удалось завершить проверку ключа: {exc}',
    }


def check_http_through_proxy(proxy_url, url='https://www.youtube.com', connect_timeout=2, read_timeout=3):
    try:
        response = requests.get(
            url,
            timeout=(connect_timeout, read_timeout),
            proxies={'https': proxy_url, 'http': proxy_url},
            stream=True,
        )
        status_code = response.status_code
        response.close()
        if status_code < 500:
            return True, f'Веб-доступ через ключ подтверждён (HTTP {status_code}).'
        return False, f'Веб-проверка через ключ вернула HTTP {status_code}.'
    except requests.exceptions.ConnectTimeout:
        return False, 'Прокси не установил соединение за отведённое время.'
    except requests.exceptions.ReadTimeout:
        return False, 'Удалённый сервер не ответил вовремя через этот ключ.'
    except requests.exceptions.RequestException as exc:
        return False, f'Веб-проверка через ключ завершилась ошибкой: {exc}'


def check_custom_target_through_proxy(normalize_url, proxy_url, url, connect_timeout=2, read_timeout=3):
    try:
        target_url = normalize_url(url)
        response = requests.get(
            target_url,
            timeout=(connect_timeout, read_timeout),
            proxies={'https': proxy_url, 'http': proxy_url},
            headers={'User-Agent': 'bypass_keenetic health check'},
            stream=True,
        )
        status_code = response.status_code
        response.close()
        if status_code < 500:
            return True, f'Доступ к {urlparse(target_url).netloc} подтверждён (HTTP {status_code}).'
        return False, f'{urlparse(target_url).netloc} вернул HTTP {status_code}.'
    except ValueError as exc:
        return False, str(exc)
    except requests.exceptions.ConnectTimeout:
        return False, 'Прокси не установил соединение за отведённое время.'
    except requests.exceptions.ReadTimeout:
        return False, 'Сервис не ответил вовремя через этот ключ.'
    except requests.exceptions.RequestException as exc:
        return False, f'Проверка сервиса завершилась ошибкой: {str(exc).splitlines()[0][:180]}'


def probe_custom_targets(proxy_url, custom_checks, target_checker, *, connect_timeout, read_timeout, max_targets=None):
    results = {}
    for check in custom_checks or []:
        check_id = check.get('id')
        if not check_id:
            continue
        targets = check.get('urls') if isinstance(check.get('urls'), list) else [check.get('url', '')]
        if max_targets is not None:
            targets = targets[:max_targets]
        target_results = []
        for target in targets:
            ok, _ = target_checker(
                proxy_url,
                target,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
            )
            target_results.append(ok)
            if ok:
                break
        results[check_id] = any(target_results)
    return results
