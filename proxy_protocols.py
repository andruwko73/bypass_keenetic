import base64
import json
from urllib.parse import parse_qs, unquote, urlparse


def parse_vmess_key(key):
    if not key.startswith('vmess://'):
        raise ValueError('Неверный протокол, ожидается vmess://')
    encoded_key = key[8:]
    try:
        decoded = base64.b64decode(encoded_key + '=' * (-len(encoded_key) % 4)).decode('utf-8')
    except Exception as exc:
        raise ValueError(f'Не удалось декодировать vmess-ключ: {exc}')
    try:
        data = json.loads(decoded.replace("'", '"'))
    except Exception as exc:
        raise ValueError(f'Неверный JSON в vmess-ключе: {exc}')
    if not data.get('add') or not data.get('port') or not data.get('id'):
        raise ValueError('В vmess-ключе нет server/port/id')
    if data.get('net') == 'grpc':
        service_name = data.get('serviceName') or data.get('grpcSettings', {}).get('serviceName')
        if not service_name:
            data['serviceName'] = data.get('add')
    return data


def parse_vless_key(key):
    parsed = urlparse(key)
    if parsed.scheme != 'vless':
        raise ValueError('Неверный протокол, ожидается vless://')
    if not parsed.hostname:
        raise ValueError('В vless-ключе отсутствует адрес сервера')
    if not parsed.username:
        raise ValueError('В vless-ключе отсутствует UUID')
    params = parse_qs(parsed.query)
    address = parsed.hostname
    port = parsed.port or 443
    user_id = parsed.username
    security = params.get('security', ['none'])[0]
    encryption = params.get('encryption', ['none'])[0]
    flow = params.get('flow', [''])[0]
    host = params.get('host', [''])[0]
    if not address and host:
        address = host
    network = params.get('type', params.get('network', ['tcp']))[0]
    path = params.get('path', ['/'])[0]
    if path == '':
        path = '/'
    sni = params.get('sni', [''])[0] or host or address
    service_name = params.get('serviceName', [''])[0]
    public_key = params.get('pbk', params.get('publicKey', ['']))[0]
    short_id = params.get('sid', params.get('shortId', ['']))[0]
    fingerprint = params.get('fp', params.get('fingerprint', ['']))[0]
    spider_x = params.get('spx', params.get('spiderX', ['']))[0]
    alpn = params.get('alpn', [''])[0]
    if not service_name and (network == 'grpc' or security == 'reality'):
        service_name = address
    return {
        'address': address,
        'port': port,
        'id': user_id,
        'security': security,
        'encryption': encryption,
        'flow': flow,
        'host': host,
        'path': path,
        'sni': sni,
        'type': network,
        'serviceName': service_name,
        'publicKey': public_key,
        'shortId': short_id,
        'fingerprint': fingerprint,
        'spiderX': spider_x,
        'alpn': alpn,
    }


def parse_trojan_key(key):
    parsed = urlparse(key)
    if parsed.scheme != 'trojan':
        raise ValueError('Неверный протокол, ожидается trojan://')
    if not parsed.hostname:
        raise ValueError('В trojan-ключе отсутствует адрес сервера')
    if not parsed.username:
        raise ValueError('В trojan-ключе отсутствует пароль')
    params = parse_qs(parsed.query)
    return {
        'address': parsed.hostname,
        'port': parsed.port or 443,
        'password': parsed.username,
        'sni': params.get('sni', [''])[0],
        'security': params.get('security', ['tls'])[0],
        'type': params.get('type', ['tcp'])[0],
        'host': params.get('host', [''])[0],
        'path': params.get('path', ['/'])[0] or '/',
        'serviceName': params.get('serviceName', [''])[0],
        'fingerprint': params.get('fp', params.get('fingerprint', ['chrome']))[0],
        'alpn': params.get('alpn', [''])[0],
        'fragment': unquote(parsed.fragment or ''),
    }


def decode_shadowsocks_uri(key):
    if not key.startswith('ss://'):
        raise ValueError('Неверный протокол, ожидается ss://')
    payload = key[5:]
    payload, _, _ = payload.partition('#')
    payload, _, _ = payload.partition('?')
    if '@' in payload:
        left, right = payload.rsplit('@', 1)
        host_part = right
        if ':' not in host_part:
            raise ValueError('Не удалось определить host:port в Shadowsocks-ключе')
        server, port = host_part.split(':', 1)
        try:
            decoded = base64.urlsafe_b64decode(left + '=' * (-len(left) % 4)).decode('utf-8')
            if ':' not in decoded:
                raise ValueError('Неверный формат декодированного payload Shadowsocks')
            method, password = decoded.split(':', 1)
        except Exception:
            decoded = unquote(left)
            if ':' not in decoded:
                raise ValueError('Неверный формат Shadowsocks credentials')
            method, password = decoded.split(':', 1)
    else:
        decoded = base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)).decode('utf-8')
        if '@' not in decoded:
            raise ValueError('Не удалось разобрать Shadowsocks-ключ')
        creds, host_part = decoded.rsplit('@', 1)
        if ':' not in host_part or ':' not in creds:
            raise ValueError('Неверный формат раскодированного Shadowsocks-URI')
        server, port = host_part.split(':', 1)
        method, password = creds.split(':', 1)
    return server, port, method, password


def proxy_outbound_from_key(proto, key_value, tag, email='t@t.tt'):
    if proto == 'shadowsocks':
        server, port, method, password = decode_shadowsocks_uri(key_value)
        return {
            'tag': tag,
            'protocol': 'shadowsocks',
            'settings': {
                'servers': [{
                    'address': server,
                    'port': int(port),
                    'method': method,
                    'password': password,
                    'level': 0,
                }]
            },
        }
    if proto == 'vmess':
        data = parse_vmess_key(key_value)
        stream_settings = {'network': data.get('net', 'tcp')}
        tls_mode = data.get('tls', 'tls')
        if tls_mode in ['tls', 'xtls']:
            stream_settings['security'] = tls_mode
            stream_settings[f'{tls_mode}Settings'] = {
                'allowInsecure': True,
                'serverName': data.get('add', ''),
            }
        else:
            stream_settings['security'] = 'none'
        if stream_settings['network'] == 'ws':
            stream_settings['wsSettings'] = {
                'path': data.get('path', '/'),
                'headers': {'Host': data.get('host', '')},
            }
        elif stream_settings['network'] == 'grpc':
            grpc_service = data.get('serviceName', '') or data.get('grpcSettings', {}).get('serviceName', '')
            stream_settings['grpcSettings'] = {'serviceName': grpc_service, 'multiMode': False}
        return {
            'tag': tag,
            'domainStrategy': 'UseIPv4',
            'protocol': 'vmess',
            'settings': {
                'vnext': [{
                    'address': data['add'],
                    'port': int(data['port']),
                    'users': [{
                        'id': data['id'],
                        'alterId': int(data.get('aid', 0)),
                        'email': email,
                        'security': 'auto',
                    }],
                }]
            },
            'streamSettings': stream_settings,
            'mux': {'enabled': True, 'concurrency': -1, 'xudpConcurrency': 16, 'xudpProxyUDP443': 'reject'},
        }
    if proto in ('vless', 'vless2'):
        data = parse_vless_key(key_value)
        network = data.get('type', 'tcp') or 'tcp'
        security = data.get('security', 'none')
        stream_settings = {'network': network}
        if security in ['tls', 'xtls']:
            stream_settings['security'] = security
            stream_settings[f'{security}Settings'] = {
                'allowInsecure': True,
                'serverName': data.get('sni', ''),
            }
        elif security == 'reality':
            stream_settings['security'] = 'reality'
            stream_settings['realitySettings'] = {
                'serverName': data.get('sni', '') or data.get('host', '') or data.get('address', ''),
                'publicKey': data.get('publicKey', ''),
                'shortId': data.get('shortId', ''),
                'fingerprint': data.get('fingerprint', 'chrome'),
                'spiderX': data.get('spiderX', '/'),
            }
            if data.get('alpn'):
                stream_settings['realitySettings']['alpn'] = [item.strip() for item in data['alpn'].split(',') if item.strip()]
        else:
            stream_settings['security'] = 'none'
        if network == 'ws':
            stream_settings['wsSettings'] = {
                'path': data.get('path', '/'),
                'headers': {'Host': data.get('host', '')},
            }
        elif network == 'grpc':
            stream_settings['grpcSettings'] = {'serviceName': data.get('serviceName', ''), 'multiMode': False}
        return {
            'tag': tag,
            'domainStrategy': 'UseIPv4',
            'protocol': 'vless',
            'settings': {
                'vnext': [{
                    'address': data.get('address', data.get('host', '')),
                    'port': int(data['port']),
                    'users': [{
                        'id': data['id'],
                        'encryption': data.get('encryption', 'none'),
                        'flow': data.get('flow', ''),
                        'level': 0,
                    }],
                }]
            },
            'streamSettings': stream_settings,
        }
    if proto == 'trojan':
        data = parse_trojan_key(key_value)
        stream_settings = {'network': data.get('type', 'tcp') or 'tcp', 'security': 'none'}
        if data.get('security', 'tls') == 'tls':
            stream_settings['security'] = 'tls'
            stream_settings['tlsSettings'] = {
                'allowInsecure': True,
                'serverName': data.get('sni') or data.get('host') or data.get('address', ''),
                'fingerprint': data.get('fingerprint', 'chrome'),
            }
            if data.get('alpn'):
                stream_settings['tlsSettings']['alpn'] = [item.strip() for item in data['alpn'].split(',') if item.strip()]
        if stream_settings['network'] == 'ws':
            stream_settings['wsSettings'] = {
                'path': data.get('path', '/'),
                'headers': {'Host': data.get('host') or data.get('sni') or data.get('address', '')},
            }
        elif stream_settings['network'] == 'grpc':
            stream_settings['grpcSettings'] = {'serviceName': data.get('serviceName', ''), 'multiMode': False}
        return {
            'tag': tag,
            'protocol': 'trojan',
            'settings': {
                'servers': [{
                    'address': data['address'],
                    'port': int(data['port']),
                    'password': data['password'],
                    'level': 0,
                }]
            },
            'streamSettings': stream_settings,
        }
    raise ValueError(f'Unsupported protocol: {proto}')
