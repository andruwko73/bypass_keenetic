import json
import os
import re
import shutil
import subprocess


XRAY_CONFIG_PATH = '/opt/etc/xray/config.json'
V2RAY_CONFIG_PATH = '/opt/etc/v2ray/config.json'
PROXY_PROTOCOLS_PATH = '/opt/etc/bot/proxy_protocols.py'
XRAY_SERVICE_PATH = '/opt/etc/init.d/S24xray'
V2RAY_SERVICE_PATH = '/opt/etc/init.d/S24v2ray'
XRAY_REQUIRED_PORTS = (10811, 10812, 10813, 10814)
XRAY_REMOVED_OPTIONS = {'allowInsecure'}
PORTS_LABEL = '\u043f\u043e\u0440\u0442\u044b'


def _last_lines(text, limit=8):
    lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
    return '\n'.join(lines[-limit:])


def _resolve_binary(binary_name, fallback):
    if binary_name and os.path.isabs(binary_name):
        return binary_name
    resolved = shutil.which(binary_name or os.path.basename(fallback))
    return resolved or fallback


def drop_xray_removed_options(value):
    if isinstance(value, dict):
        changed = False
        for option in XRAY_REMOVED_OPTIONS:
            if option in value:
                value.pop(option, None)
                changed = True
        for child in value.values():
            changed = drop_xray_removed_options(child) or changed
        return changed
    if isinstance(value, list):
        changed = False
        for child in value:
            changed = drop_xray_removed_options(child) or changed
        return changed
    return False


def sanitize_xray_config_file(config_path=XRAY_CONFIG_PATH):
    if not os.path.isfile(config_path):
        return False
    with open(config_path, 'r', encoding='utf-8') as file:
        config_data = json.load(file)
    if not drop_xray_removed_options(config_data):
        return False
    with open(config_path, 'w', encoding='utf-8') as file:
        json.dump(config_data, file, ensure_ascii=False, indent=2)
    return True


def sanitize_proxy_protocols_file(protocols_path=PROXY_PROTOCOLS_PATH):
    if not os.path.isfile(protocols_path):
        return False
    with open(protocols_path, 'r', encoding='utf-8', errors='ignore') as file:
        text = file.read()
    if not any(option in text for option in XRAY_REMOVED_OPTIONS):
        return False
    filtered = ''.join(
        line for line in text.splitlines(True)
        if not any(option in line for option in XRAY_REMOVED_OPTIONS)
    )
    with open(protocols_path, 'w', encoding='utf-8') as file:
        file.write(filtered)
    return True


def sanitize_xray26_compat_files(
    *,
    config_paths=(XRAY_CONFIG_PATH, V2RAY_CONFIG_PATH),
    protocols_path=PROXY_PROTOCOLS_PATH,
    logger=None,
):
    changed = []
    for config_path in config_paths:
        try:
            if sanitize_xray_config_file(config_path):
                changed.append(os.path.basename(config_path))
        except Exception as exc:
            if logger:
                logger(f'Xray migration failed for {config_path}: {exc}')
    try:
        if sanitize_proxy_protocols_file(protocols_path):
            changed.append(os.path.basename(protocols_path))
    except Exception as exc:
        if logger:
            logger(f'Xray migration failed for {protocols_path}: {exc}')
    return changed


def validate_xray_config(config_path=XRAY_CONFIG_PATH, xray_binary=None, timeout=10):
    if not os.path.isfile(config_path):
        return {
            'ok': False,
            'message': f'config not found: {config_path}',
            'returncode': None,
        }
    binary = _resolve_binary(xray_binary or 'xray', '/opt/sbin/xray')
    if not os.path.exists(binary) and shutil.which(binary) is None:
        return {
            'ok': False,
            'message': f'xray binary not found: {binary}',
            'returncode': None,
        }
    try:
        result = subprocess.run(
            [binary, 'run', '-test', '-c', config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return {'ok': False, 'message': str(exc), 'returncode': None}
    output = _last_lines(result.stdout or '')
    return {
        'ok': result.returncode == 0,
        'message': output,
        'returncode': result.returncode,
    }


def service_status(service_path):
    if not os.path.exists(service_path):
        return {'state': 'missing', 'message': 'service script not found'}
    try:
        result = subprocess.run(
            [service_path, 'status'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return {'state': 'error', 'message': str(exc)}
    text = result.stdout or ''
    lowered = text.lower()
    if 'alive' in lowered or 'running' in lowered:
        state = 'alive'
    elif 'dead' in lowered or 'stopped' in lowered or 'not running' in lowered:
        state = 'dead'
    else:
        state = 'unknown'
    return {'state': state, 'message': _last_lines(text, limit=3)}


def restart_service(service_path, timeout=20):
    if not os.path.exists(service_path):
        return {'ok': False, 'message': 'service script not found', 'returncode': None}
    try:
        result = subprocess.run(
            [service_path, 'restart'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return {'ok': False, 'message': str(exc), 'returncode': None}
    return {
        'ok': result.returncode == 0,
        'message': _last_lines(result.stdout or '', limit=5),
        'returncode': result.returncode,
    }


def _netstat_text(timeout=3):
    try:
        result = subprocess.run(
            ['netstat', '-lnpt'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return ''
    return result.stdout or ''


def listening_ports(ports=XRAY_REQUIRED_PORTS, netstat_text=None):
    text = _netstat_text() if netstat_text is None else (netstat_text or '')
    result = {}
    for port in ports:
        pattern = re.compile(r'[:.]' + re.escape(str(int(port))) + r'(?:\s|$)')
        result[int(port)] = any(pattern.search(line) for line in text.splitlines())
    return result


def core_proxy_health(
    *,
    xray_config_path=XRAY_CONFIG_PATH,
    xray_service_path=XRAY_SERVICE_PATH,
    v2ray_service_path=V2RAY_SERVICE_PATH,
    ports=XRAY_REQUIRED_PORTS,
):
    xray_status = service_status(xray_service_path)
    v2ray_status = service_status(v2ray_service_path)
    validation = validate_xray_config(xray_config_path)
    port_states = listening_ports(ports)
    ports_ok = all(port_states.values()) if port_states else False
    ok = xray_status.get('state') == 'alive' and validation.get('ok') and ports_ok
    return {
        'ok': bool(ok),
        'xray_state': xray_status.get('state'),
        'xray_status': xray_status.get('message', ''),
        'v2ray_state': v2ray_status.get('state'),
        'xray_config_ok': bool(validation.get('ok')),
        'xray_config_message': validation.get('message', ''),
        'ports': port_states,
    }


def core_proxy_note(health):
    health = health or {}
    port_states = health.get('ports') or {}
    ports_text = ', '.join(
        f'{port}:{"ok" if ok else "down"}'
        for port, ok in sorted(port_states.items())
    )
    if health.get('ok'):
        return f'Xray: alive, config OK, {PORTS_LABEL}: {ports_text}.'
    parts = [
        f"Xray: {health.get('xray_state') or 'unknown'}",
        f"config: {'OK' if health.get('xray_config_ok') else 'error'}",
    ]
    if ports_text:
        parts.append(f'{PORTS_LABEL}: {ports_text}')
    message = str(health.get('xray_config_message') or '').strip().splitlines()
    if message:
        parts.append(message[-1][:180])
    return '. '.join(parts) + '.'
