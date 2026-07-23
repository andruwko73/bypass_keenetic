from proxy_protocols import (
    decode_shadowsocks_uri,
    parse_trojan_key,
    proxy_outbound_from_key,
)
from transparent_route_policy import normalize_protocol_set


def xray_base_config(*, error_log_path, access_log_path='/dev/null', loglevel='warning'):
    """Return the shared router-local Xray foundation used by runtime and probes."""
    return {
        'log': {
            'access': access_log_path,
            'error': error_log_path,
            'loglevel': loglevel,
        },
        'dns': {
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
        'sniffing': {'enabled': False},
        'tag': tag,
    }


def transparent_sniffing(route_only=False):
    return {
        'enabled': True,
        'destOverride': ['http', 'tls', 'quic'],
        'routeOnly': bool(route_only),
    }


def transparent_inbound(port, tag, route_only=False):
    return {
        'port': int(port),
        'listen': '0.0.0.0',
        'protocol': 'dokodemo-door',
        'settings': {
            'network': 'tcp,udp',
            'followRedirect': True,
        },
        'streamSettings': {
            'sockopt': {'tproxy': 'redirect'},
        },
        'sniffing': transparent_sniffing(route_only=route_only),
        'tag': tag,
    }


def tproxy_inbound(port, tag, route_only=False):
    return {
        'port': int(port),
        'listen': '0.0.0.0',
        'protocol': 'dokodemo-door',
        'settings': {
            'network': 'udp',
            'followRedirect': True,
        },
        'streamSettings': {
            'sockopt': {'tproxy': 'tproxy'},
        },
        'sniffing': transparent_sniffing(route_only=route_only),
        'tag': tag,
    }


def _add_proxy_route(config_data, inbound_tags, outbound_tag):
    config_data['routing']['rules'].append({
        'type': 'field',
        'inboundTag': list(inbound_tags),
        'outboundTag': outbound_tag,
        'enabled': True,
    })


def _add_confirmed_transparent_routes(config_data, inbound_tag, outbound_tag, route_policy):
    """Proxy only entries that the transparent inbound can prove belong to its list."""
    policy = route_policy or {}
    domains = list(policy.get('domains') or ())
    addresses = list(policy.get('ips') or ())
    ip_ports = str(policy.get('ip_ports') or '').strip()
    if domains:
        config_data['routing']['rules'].append({
            'type': 'field',
            'inboundTag': [inbound_tag],
            'domain': domains,
            'outboundTag': outbound_tag,
            'enabled': True,
        })
    if addresses:
        ip_rule = {
            'type': 'field',
            'inboundTag': [inbound_tag],
            'ip': addresses,
            'outboundTag': outbound_tag,
            'enabled': True,
        }
        if ip_ports:
            ip_rule['port'] = ip_ports
        config_data['routing']['rules'].append(ip_rule)
    config_data['routing']['rules'].append({
        'type': 'field',
        'inboundTag': [inbound_tag],
        'outboundTag': 'direct',
        'enabled': True,
    })


def _add_bittorrent_direct_route(config_data, inbound_tags):
    tags = [tag for tag in inbound_tags if tag]
    if not tags:
        return
    config_data['routing']['rules'].insert(0, {
        'type': 'field',
        'inboundTag': tags,
        'protocol': ['bittorrent'],
        'outboundTag': 'direct',
        'ruleTag': 'bittorrent-direct',
        'enabled': True,
    })


def _add_socks_proxy(config_data, proto, key_value, socks_port, socks_tag, outbound_tag):
    if not key_value:
        return
    config_data['inbounds'].append(socks_inbound(socks_port, socks_tag))
    config_data['outbounds'].append(proxy_outbound_from_key(proto, key_value, outbound_tag))
    _add_proxy_route(config_data, [socks_tag], outbound_tag)


def _add_transparent_proxy(
    config_data,
    proto,
    key_value,
    socks_port,
    transparent_port,
    socks_tag,
    transparent_tag,
    outbound_tag,
    *,
    route_only=False,
    strict_policy=None,
):
    if not key_value:
        return None
    config_data['inbounds'].append(socks_inbound(socks_port, socks_tag))
    config_data['inbounds'].append(transparent_inbound(transparent_port, transparent_tag, route_only=route_only))
    config_data['outbounds'].append(proxy_outbound_from_key(proto, key_value, outbound_tag))
    _add_proxy_route(config_data, [socks_tag], outbound_tag)
    if strict_policy is None:
        _add_proxy_route(config_data, [transparent_tag], outbound_tag)
    else:
        _add_confirmed_transparent_routes(config_data, transparent_tag, outbound_tag, strict_policy)
    return transparent_tag


def _add_tproxy_route(config_data, key_value, tproxy_port, tproxy_tag, outbound_tag, *, route_only=False):
    if not key_value or not tproxy_port:
        return None
    config_data['inbounds'].append(tproxy_inbound(tproxy_port, tproxy_tag, route_only=route_only))
    _add_proxy_route(config_data, [tproxy_tag], outbound_tag)
    return tproxy_tag


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
    include_tproxy_inbounds=True,
    route_only_transparent_protocols=(),
    route_only_tproxy_protocols=(),
    strict_transparent_protocols=(),
    transparent_route_policies=None,
    bittorrent_direct_enabled=False,
):
    config_data = xray_base_config(
        error_log_path=error_log_path,
        access_log_path=access_log_path,
        loglevel=loglevel,
    )

    route_only_transparent = normalize_protocol_set(route_only_transparent_protocols)
    route_only_tproxy = normalize_protocol_set(route_only_tproxy_protocols)
    strict_transparent = normalize_protocol_set(strict_transparent_protocols)
    route_policies = transparent_route_policies or {}
    transparent_tags = []
    tproxy_tags = []

    if include_vmess_transparent:
        transparent_tag = _add_transparent_proxy(
            config_data,
            'vmess',
            vmess_key,
            ports['vmess'],
            ports['vmess_transparent'],
            'in-vmess',
            'in-vmess-transparent',
            'proxy-vmess',
            route_only='vmess' in route_only_transparent,
            strict_policy=route_policies.get('vmess') if 'vmess' in strict_transparent else None,
        )
        if transparent_tag:
            transparent_tags.append(transparent_tag)
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
    transparent_tag = _add_transparent_proxy(
        config_data,
        'vless',
        vless_key,
        ports['vless'],
        ports['vless_transparent'],
        'in-vless',
        'in-vless-transparent',
        'proxy-vless',
        route_only='vless' in route_only_transparent,
        strict_policy=route_policies.get('vless') if 'vless' in strict_transparent else None,
    )
    if transparent_tag:
        transparent_tags.append(transparent_tag)
    transparent_tag = _add_transparent_proxy(
        config_data,
        'vless',
        vless2_key,
        ports['vless2'],
        ports['vless2_transparent'],
        'in-vless2',
        'in-vless2-transparent',
        'proxy-vless2',
        route_only='vless2' in route_only_transparent,
        strict_policy=route_policies.get('vless2') if 'vless2' in strict_transparent else None,
    )
    if transparent_tag:
        transparent_tags.append(transparent_tag)
    _add_socks_proxy(config_data, 'trojan', trojan_key, ports['trojan_bot'], 'in-trojan', 'proxy-trojan')

    if include_tproxy_inbounds:
        tproxy_tag = _add_tproxy_route(
            config_data,
            shadowsocks_key,
            ports.get('shadowsocks_tproxy'),
            'in-shadowsocks-tproxy',
            'proxy-shadowsocks',
            route_only='shadowsocks' in route_only_tproxy,
        )
        if tproxy_tag:
            tproxy_tags.append(tproxy_tag)
        tproxy_tag = _add_tproxy_route(
            config_data,
            vmess_key,
            ports.get('vmess_tproxy'),
            'in-vmess-tproxy',
            'proxy-vmess',
            route_only='vmess' in route_only_tproxy,
        )
        if tproxy_tag:
            tproxy_tags.append(tproxy_tag)
        tproxy_tag = _add_tproxy_route(
            config_data,
            vless_key,
            ports.get('vless_tproxy'),
            'in-vless-tproxy',
            'proxy-vless',
            route_only='vless' in route_only_tproxy,
        )
        if tproxy_tag:
            tproxy_tags.append(tproxy_tag)
        tproxy_tag = _add_tproxy_route(
            config_data,
            vless2_key,
            ports.get('vless2_tproxy'),
            'in-vless2-tproxy',
            'proxy-vless2',
            route_only='vless2' in route_only_tproxy,
        )
        if tproxy_tag:
            tproxy_tags.append(tproxy_tag)
        tproxy_tag = _add_tproxy_route(
            config_data,
            trojan_key,
            ports.get('trojan_tproxy'),
            'in-trojan-tproxy',
            'proxy-trojan',
            route_only='trojan' in route_only_tproxy,
        )
        if tproxy_tag:
            tproxy_tags.append(tproxy_tag)

    if bittorrent_direct_enabled:
        _add_bittorrent_direct_route(config_data, [*transparent_tags, *tproxy_tags])

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
