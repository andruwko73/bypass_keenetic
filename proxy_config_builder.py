from proxy_protocols import (
    decode_shadowsocks_uri,
    parse_trojan_key,
    proxy_outbound_from_key,
)


def socks_inbound(port, tag, listen='127.0.0.1'):
    return {
        'port': int(port),
        'listen': listen,
        'protocol': 'socks',
        'settings': {
            'auth': 'noauth',
            'udp': True,
            'ip': '127.0.0.1',
        },
        'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
        'tag': tag,
    }


def transparent_inbound(port, tag):
    return {
        'port': int(port),
        'listen': '0.0.0.0',
        'protocol': 'dokodemo-door',
        'settings': {
            'network': 'tcp',
            'followRedirect': True,
        },
        'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
        'tag': tag,
    }


def _add_proxy_route(config_data, inbound_tags, outbound_tag):
    config_data['routing']['rules'].append({
        'type': 'field',
        'inboundTag': list(inbound_tags),
        'outboundTag': outbound_tag,
        'enabled': True,
    })


def _add_socks_proxy(config_data, proto, key_value, socks_port, socks_tag, outbound_tag):
    if not key_value:
        return
    config_data['inbounds'].append(socks_inbound(socks_port, socks_tag))
    config_data['outbounds'].append(proxy_outbound_from_key(proto, key_value, outbound_tag))
    _add_proxy_route(config_data, [socks_tag], outbound_tag)


def _add_transparent_proxy(config_data, proto, key_value, socks_port, transparent_port, socks_tag, transparent_tag, outbound_tag):
    if not key_value:
        return
    config_data['inbounds'].append(socks_inbound(socks_port, socks_tag))
    config_data['inbounds'].append(transparent_inbound(transparent_port, transparent_tag))
    config_data['outbounds'].append(proxy_outbound_from_key(proto, key_value, outbound_tag))
    _add_proxy_route(config_data, [socks_tag, transparent_tag], outbound_tag)


def build_proxy_core_config(
    *,
    vmess_key=None,
    vless_key=None,
    vless2_key=None,
    shadowsocks_key=None,
    trojan_key=None,
    ports,
    error_log_path,
    access_log_path='/dev/null',
    loglevel='warning',
    connectivity_check_domains=None,
    include_vmess_transparent=False,
):
    config_data = {
        'log': {
            'access': access_log_path,
            'error': error_log_path,
            'loglevel': loglevel,
        },
        'dns': {
            'hosts': {
                'api.telegram.org': '149.154.167.220',
            },
            'servers': ['8.8.8.8', '1.1.1.1', 'localhost'],
            'queryStrategy': 'UseIPv4',
        },
        'inbounds': [],
        'outbounds': [],
        'routing': {
            'domainStrategy': 'IPIfNonMatch',
            'rules': [],
        },
    }

    if include_vmess_transparent:
        _add_transparent_proxy(
            config_data,
            'vmess',
            vmess_key,
            ports['vmess'],
            ports['vmess_transparent'],
            'in-vmess',
            'in-vmess-transparent',
            'proxy-vmess',
        )
    else:
        _add_socks_proxy(config_data, 'vmess', vmess_key, ports['vmess'], 'in-vmess', 'proxy-vmess')

    _add_socks_proxy(
        config_data,
        'shadowsocks',
        shadowsocks_key,
        ports['shadowsocks_bot'],
        'in-shadowsocks',
        'proxy-shadowsocks',
    )
    _add_transparent_proxy(
        config_data,
        'vless',
        vless_key,
        ports['vless'],
        ports['vless_transparent'],
        'in-vless',
        'in-vless-transparent',
        'proxy-vless',
    )
    _add_transparent_proxy(
        config_data,
        'vless',
        vless2_key,
        ports['vless2'],
        ports['vless2_transparent'],
        'in-vless2',
        'in-vless2-transparent',
        'proxy-vless2',
    )
    _add_socks_proxy(config_data, 'trojan', trojan_key, ports['trojan_bot'], 'in-trojan', 'proxy-trojan')

    if config_data['outbounds']:
        config_data['outbounds'].append({'protocol': 'freedom', 'tag': 'direct'})
        if connectivity_check_domains:
            config_data['routing']['rules'].insert(0, {
                'type': 'field',
                'domain': list(connectivity_check_domains),
                'outboundTag': 'direct',
                'enabled': True,
            })
        config_data['routing']['rules'].append({
            'type': 'field',
            'port': '0-65535',
            'outboundTag': 'direct',
            'enabled': True,
        })

    return config_data


def build_trojan_config(raw_key, local_port):
    raw_key = raw_key.strip()
    trojan_data = parse_trojan_key(raw_key)
    return {
        'run_type': 'nat',
        'local_addr': '::',
        'local_port': int(local_port),
        'remote_addr': trojan_data['address'],
        'remote_port': int(trojan_data['port']),
        'password': [trojan_data['password']],
        'raw_uri': raw_key,
        'type': trojan_data['type'],
        'security': trojan_data['security'],
        'sni': trojan_data['sni'],
        'host': trojan_data['host'],
        'path': trojan_data['path'],
        'serviceName': trojan_data['serviceName'],
        'fingerprint': trojan_data['fingerprint'],
        'alpn': trojan_data['alpn'],
        'fragment': trojan_data['fragment'],
        'ssl': {
            'verify': False,
            'verify_hostname': False,
        },
    }


def build_shadowsocks_config(raw_key, local_port):
    raw_key = raw_key.strip()
    server, port, method, password = decode_shadowsocks_uri(raw_key)
    return {
        'server': [server],
        'mode': 'tcp_and_udp',
        'server_port': int(port),
        'password': password,
        'timeout': 86400,
        'method': method,
        'local_address': '::',
        'local_port': int(local_port),
        'fast_open': False,
        'ipv6_first': True,
        'raw_uri': raw_key,
    }
