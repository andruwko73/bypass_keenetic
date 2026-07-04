import base64
import json
import os
from urllib.parse import quote, urlencode


SHADOWSOCKS_CONFIG_PATH = '/opt/etc/shadowsocks.json'
TROJAN_CONFIG_PATH = '/opt/etc/trojan/config.json'


def read_v2ray_key(file_path, xray_config_dir, v2ray_config_dir):
    candidate_paths = [file_path]
    file_name = os.path.basename(file_path)
    current_dir = os.path.dirname(file_path)
    alternate_dirs = []
    if current_dir == xray_config_dir:
        alternate_dirs.append(v2ray_config_dir)
    elif current_dir == v2ray_config_dir:
        alternate_dirs.append(xray_config_dir)
    for directory in alternate_dirs:
        candidate_paths.append(os.path.join(directory, file_name))

    for candidate_path in candidate_paths:
        try:
            with open(candidate_path, 'r', encoding='utf-8') as file:
                value = file.read().strip()
            if value:
                return value
        except Exception:
            continue
    return None


def save_v2ray_key(file_path, key):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write((key or '').strip())


def load_shadowsocks_key(config_path=SHADOWSOCKS_CONFIG_PATH):
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        raw_uri = str(data.get('raw_uri', '') or '').strip()
        if raw_uri.startswith('ss://'):
            return raw_uri
        server = (data.get('server') or [''])[0]
        port = data.get('server_port', '')
        method = data.get('method', '')
        password = data.get('password', '')
        if not server or not port or not method:
            return ''
        encoded = base64.urlsafe_b64encode(f'{method}:{password}'.encode('utf-8')).decode('utf-8').rstrip('=')
        return f'ss://{encoded}@{server}:{port}'
    except Exception:
        return ''


def load_trojan_key(config_path=TROJAN_CONFIG_PATH):
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        raw_uri = str(data.get('raw_uri', '') or '').strip()
        if raw_uri.startswith('trojan://'):
            return raw_uri
        password = (data.get('password') or [''])[0]
        address = data.get('remote_addr', '')
        port = data.get('remote_port', '')
        if (
            str(address).strip().lower() == 'ownade' and
            str(port).strip() == '65432' and
            str(password).strip() == 'pw'
        ):
            return ''
        if not password or not address or not port:
            return ''
        query_params = []
        trojan_type = str(data.get('type', '') or '').strip()
        if trojan_type and trojan_type != 'tcp':
            query_params.append(('type', trojan_type))

        security = str(data.get('security', '') or '').strip()
        if security and security != 'tls':
            query_params.append(('security', security))

        sni = str(data.get('sni', '') or '').strip()
        if sni:
            query_params.append(('sni', sni))

        host = str(data.get('host', '') or '').strip()
        if host:
            query_params.append(('host', host))

        path = str(data.get('path', '') or '').strip()
        if path and path != '/':
            query_params.append(('path', path))

        service_name = str(data.get('serviceName', '') or '').strip()
        if service_name:
            query_params.append(('serviceName', service_name))

        fingerprint = str(data.get('fingerprint', '') or '').strip()
        if fingerprint and fingerprint != 'chrome':
            query_params.append(('fp', fingerprint))

        alpn = str(data.get('alpn', '') or '').strip()
        if alpn:
            query_params.append(('alpn', alpn))

        query_suffix = ''
        if query_params:
            query_suffix = '?' + urlencode(query_params)

        fragment = str(data.get('fragment', '') or '').strip()
        fragment_suffix = f'#{quote(fragment)}' if fragment else ''

        return f'trojan://{password}@{address}:{port}{query_suffix}{fragment_suffix}'
    except Exception:
        return ''


def load_current_keys(vmess_key_path, vless_key_path, vless2_key_path, xray_config_dir, v2ray_config_dir):
    return {
        'shadowsocks': load_shadowsocks_key(),
        'vmess': read_v2ray_key(vmess_key_path, xray_config_dir, v2ray_config_dir) or '',
        'vless': read_v2ray_key(vless_key_path, xray_config_dir, v2ray_config_dir) or '',
        'vless2': read_v2ray_key(vless2_key_path, xray_config_dir, v2ray_config_dir) or '',
        'trojan': load_trojan_key(),
    }


def v2ray_key_file_candidates(file_path, xray_config_dir, v2ray_config_dir):
    paths = [file_path]
    file_name = os.path.basename(file_path)
    for directory in (xray_config_dir, v2ray_config_dir):
        candidate = os.path.join(directory, file_name)
        if candidate not in paths:
            paths.append(candidate)
    return paths


def remove_file_if_exists(file_path, logger=None):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as exc:
        if logger:
            logger(f'Не удалось удалить {file_path}: {exc}')


def proxy_config_snapshot_paths(core_config_path, vmess_key_path, vless_key_path, vless2_key_path):
    return [
        core_config_path,
        vmess_key_path,
        vless_key_path,
        vless2_key_path,
        SHADOWSOCKS_CONFIG_PATH,
        TROJAN_CONFIG_PATH,
    ]


def snapshot_proxy_config_files(paths, logger=None):
    snapshot = {}
    for file_path in paths or []:
        try:
            with open(file_path, 'rb') as file:
                snapshot[file_path] = file.read()
        except FileNotFoundError:
            snapshot[file_path] = None
        except Exception as exc:
            if logger:
                logger(f'Не удалось сохранить snapshot {file_path}: {exc}')
            snapshot[file_path] = None
    return snapshot


def restore_proxy_config_files(snapshot, logger=None):
    for file_path, content in (snapshot or {}).items():
        try:
            if content is None:
                if os.path.exists(file_path):
                    os.remove(file_path)
                continue
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'wb') as file:
                file.write(content)
        except Exception as exc:
            if logger:
                logger(f'Не удалось восстановить snapshot {file_path}: {exc}')
