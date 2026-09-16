"""Shared addresses must not override an unambiguous hostname assignment."""
import ast
import copy
import random
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(APP))
import proxy_config_builder as builder
import transparent_route_policy as policy

PORTS = {
    'vmess': 10810, 'vmess_transparent': 10815, 'vless': 10811,
    'vless_transparent': 10812, 'vless2': 10813, 'vless2_transparent': 10814,
    'shadowsocks_bot': 10820, 'trojan_bot': 10830,
    'hysteria2': 10840, 'hysteria2_transparent': 10841,
    'shadowsocks_tproxy': 11802, 'vmess_tproxy': 11815,
    'vless_tproxy': 11812, 'vless2_tproxy': 11814,
    'trojan_tproxy': 11829, 'hysteria2_tproxy': 11840,
}


def test_arbitrary_domains_without_a_service_catalog():
    entries = {
        'vless': ['api.example.org', 'https://Cloud.Example.net/path',
                  'full:Exact.Example.org.', '*.suffix.example.org', 'api.example.org',
                  '192.0.2.1', '2001:db8::1', 'bad value'],
        'vless2': ['video.example.net'],
    }
    assert policy.compile_cross_route_domain_overrides(entries) == {
        'vless': {'domains': ('domain:api.example.org', 'domain:cloud.example.net',
                             'domain:suffix.example.org', 'full:exact.example.org')},
        'vless2': {'domains': ('domain:video.example.net',)},
    }


@pytest.mark.parametrize('left,right,expected', [
    ('example.org', 'example.org', {}),
    ('example.org', 'child.example.org', {}),
    ('example.org', 'full:child.example.org', {}),
    ('full:example.org', 'example.org', {}),
    ('full:example.org', 'child.example.org',
     {'vless': {'domains': ('full:example.org',)},
      'vless2': {'domains': ('domain:child.example.org',)}}),
    ('full:child.example.org', 'other.example.org',
     {'vless': {'domains': ('full:child.example.org',)},
      'vless2': {'domains': ('domain:other.example.org',)}}),
    ('example.org', 'notexample.org',
     {'vless': {'domains': ('domain:example.org',)},
      'vless2': {'domains': ('domain:notexample.org',)}}),
])
def test_conflicts_respect_full_suffix_and_label_boundaries(left, right, expected):
    assert policy.compile_cross_route_domain_overrides({'vless': [left], 'vless2': [right]}) == expected


def test_conflict_does_not_disable_independent_routes_or_fallback():
    entries = {'vless': ['example.org', 'safe.example.net'],
               'vless2': ['child.example.org', 'video.example.net']}
    original = copy.deepcopy(entries)
    assert policy.compile_cross_route_domain_overrides(entries) == {
        'vless': {'domains': ('domain:safe.example.net',)},
        'vless2': {'domains': ('domain:video.example.net',)},
    }
    assert entries == original


def test_same_owner_overlap_is_allowed_and_output_is_deterministic():
    entries = {'vless': ['example.org', 'full:example.org', 'child.example.org']}
    result = policy.compile_cross_route_domain_overrides(entries)
    assert len(result['vless']['domains']) == 3
    assert result == policy.compile_cross_route_domain_overrides({'vless': list(reversed(entries['vless']))})
    assert policy.compile_cross_route_domain_overrides(None) == {}


def reference_overrides(entries):
    tokens = [(proto, token) for proto in policy.SUPPORTED_PROTOCOLS
              for token in policy.compile_route_entries(entries.get(proto, ()))['domains']]

    def overlaps(left, right):
        lk, lh = left.split(':', 1)
        rk, rh = right.split(':', 1)
        return (lh == rh or
                lk == 'domain' and rh.endswith('.' + lh) or
                rk == 'domain' and lh.endswith('.' + rh))

    result = {}
    for proto, token in tokens:
        if not any(other != proto and overlaps(token, candidate) for other, candidate in tokens):
            result.setdefault(proto, {'domains': []})['domains'].append(token)
    return {proto: {'domains': tuple(sorted(row['domains']))} for proto, row in result.items()}


def test_trie_matches_independent_pairwise_reference():
    rng = random.Random(1056)
    hosts = ['example.org', 'a.example.org', 'b.example.org', 'deep.a.example.org',
             'example.net', 'a.example.net', 'notexample.org']
    for _ in range(250):
        entries = {proto: [rng.choice(('', 'full:', 'domain:')) + rng.choice(hosts)
                           for _ in range(rng.randrange(9))]
                   for proto in policy.SUPPORTED_PROTOCOLS}
        assert policy.compile_cross_route_domain_overrides(entries) == reference_overrides(entries)


def core_config(monkeypatch, entries, absent=()):
    monkeypatch.setattr(builder, 'proxy_outbound_from_key',
                        lambda _proto, _key, tag: {'tag': tag, 'protocol': 'blackhole'})
    keys = {proto + '_key': None if proto in absent else 'synthetic'
            for proto in policy.SUPPORTED_PROTOCOLS}
    return builder.build_proxy_core_config(
        **keys, ports=PORTS, error_log_path='/tmp/test.log',
        include_vmess_transparent=True,
        strict_transparent_protocols=('vless', 'vless2', 'vmess', 'hysteria2'),
        transparent_route_policies=policy.compile_protocol_policies(
            entries, ('vless', 'vless2', 'vmess', 'hysteria2')),
        cross_route_domain_overrides=policy.compile_cross_route_domain_overrides(entries),
        connectivity_check_domains=['full:connectivity.example.org'],
        bittorrent_direct_enabled=True,
    )


@pytest.mark.parametrize('protocol', policy.SUPPORTED_PROTOCOLS)
def test_every_available_outbound_and_only_transparent_tcp_inputs(monkeypatch, protocol):
    config = core_config(monkeypatch, {protocol: ['service.example.org']})
    rules = config['routing']['rules']
    rule = next(r for r in rules if r.get('ruleTag') == 'cross-route-domains-' + protocol)
    assert rule['outboundTag'] == 'proxy-' + protocol
    assert set(rule['inboundTag']) == {
        'in-vless-transparent', 'in-vless2-transparent', 'in-vmess-transparent',
        'in-hysteria2-transparent',
    }
    assert rule['network'] == 'tcp'
    assert rules[0]['outboundTag'] == 'direct'
    assert rules[1]['ruleTag'] == 'bittorrent-direct'
    assert rules.index(rule) < next(i for i, r in enumerate(rules)
                                   if r.get('inboundTag') == ['in-vless2-transparent'])
    for tag in ('in-vless', 'in-vless2', 'in-vmess', 'in-trojan', 'in-shadowsocks', 'in-hysteria2'):
        assert next(r for r in rules if r.get('inboundTag') == [tag])['outboundTag'] == tag.replace('in-', 'proxy-')
    for r in rules:
        if len(r.get('inboundTag', [])) == 1 and r['inboundTag'][0].endswith('-tproxy'):
            assert r['outboundTag'] == r['inboundTag'][0].replace('in-', 'proxy-').removesuffix('-tproxy')


def test_absent_outbound_and_existing_ip_fallback_unchanged(monkeypatch):
    entries = {'vless': ['api.example.org', '192.0.2.0/24'], 'vless2': ['video.example.net']}
    config = core_config(monkeypatch, entries, absent=('vless',))
    assert not any(r.get('ruleTag') == 'cross-route-domains-vless' for r in config['routing']['rules'])
    config = core_config(monkeypatch, entries)
    rules = config['routing']['rules']
    assert next(r for r in rules if r.get('ip') == ['192.0.2.0/24'])['port'] == '80,443,5222'
    assert next(r for r in rules if r.get('inboundTag') == ['in-vless-transparent']
                and 'domain' not in r and 'ip' not in r)['outboundTag'] == 'direct'


def test_runtime_uses_one_snapshot_for_general_policy():
    tree = ast.parse((APP / 'bot.py').read_text('utf-8'))
    names = {'_transparent_route_policies', '_transparent_cross_route_domain_overrides', '_build_v2ray_config'}
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    calls = []
    entries = {'vless': ['new-domain.example.org'], 'vless2': ['video.example.net']}
    namespace = {
        'XRAY_STRICT_TRANSPARENT_PROTOCOLS': ('vless', 'vless2'),
        'XRAY_ROUTE_ONLY_TRANSPARENT_PROTOCOLS': (),
        'XRAY_ROUTE_ONLY_TPROXY_PROTOCOLS': (),
        'XRAY_BITTORRENT_DIRECT_ENABLED': True,
        'CORE_PROXY_ERROR_LOG': '/tmp/test.log',
        '_transparent_route_entries_by_protocol': lambda: calls.append('read') or entries,
        '_compile_transparent_route_policies': policy.compile_protocol_policies,
        '_compile_transparent_domain_overrides': policy.compile_cross_route_domain_overrides,
        '_apply_reality_endpoint_override': lambda value: value,
        '_service_catalog': lambda: type('Catalog', (), {'CONNECTIVITY_CHECK_DOMAINS': ()}),
        '_builder_build_proxy_core_config': lambda **kwargs: kwargs,
    }
    for node in ast.walk(next(n for n in definitions if n.name == '_build_v2ray_config')):
        if isinstance(node, ast.Name) and node.id.startswith('localport'):
            namespace[node.id] = 1
    exec(compile(ast.Module(body=definitions, type_ignores=[]), '<runtime>', 'exec'), namespace)
    result = namespace['_build_v2ray_config']()
    assert calls == ['read']
    assert result['cross_route_domain_overrides']['vless']['domains'] == ('domain:new-domain.example.org',)
    namespace['XRAY_STRICT_TRANSPARENT_PROTOCOLS'] = ()
    calls.clear()
    assert namespace['_build_v2ray_config']()['cross_route_domain_overrides'] == {}
    assert calls == []


@pytest.mark.skipif(not __import__('os').environ.get('XRAY_TEST_BINARY'),
                    reason='Set XRAY_TEST_BINARY to run the real-engine loopback test')
def test_real_xray_sniffed_hosts_use_distinct_egresses(monkeypatch, tmp_path):
    """Actual HTTP sniffing/rule selection; kernel REDIRECT is tested on the router."""
    import contextlib
    import http.client
    import http.server
    import json
    import os
    import socket
    import subprocess
    import threading
    import time

    servers, threads, processes = [], [], []
    entries = {proto: [proto + '.example.org'] for proto in policy.SUPPORTED_PROTOCOLS}
    entries['vless'] += ['conflict.example.org', 'full:exact.example.net']
    entries['vless2'] += ['child.conflict.example.org']
    config = core_config(monkeypatch, entries)
    config['log'] = {'loglevel': 'error'}
    config['dns'] = {'hosts': {}, 'servers': []}

    def handler(tag):
        class Reply(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'
            def do_GET(self):
                data = tag.encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def log_message(self, *_args):
                pass
        return Reply

    allocated_ports = set()

    def free_port():
        while True:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            if port not in allocated_ports:
                allocated_ports.add(port)
                return port

    def request(port, host, socks=False):
        with socket.create_connection(('127.0.0.1', port), timeout=4) as client:
            client.settimeout(4)
            if socks:
                client.sendall(b'\x05\x01\x00')
                assert client.recv(2) == b'\x05\x00'
                client.sendall(b'\x05\x01\x00\x01\x7f\x00\x00\x01\x00\x50')
                response = bytearray()
                while len(response) < 10:
                    part = client.recv(10 - len(response))
                    assert part
                    response.extend(part)
                assert response[1] == 0
            header = ('Host: ' + host + '\r\n') if host else ''
            client.sendall(('GET / HTTP/1.0\r\n' + header + '\r\n').encode())
            response = http.client.HTTPResponse(client)
            response.begin()
            assert response.status == 200
            return response.read().decode()

    try:
        targets = {}
        for tag in ['direct'] + ['proxy-' + proto for proto in policy.SUPPORTED_PROTOCOLS]:
            server = http.server.HTTPServer(('127.0.0.1', 0), handler(tag))
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05})
            thread.start()
            servers.append(server)
            threads.append(thread)
            targets[tag] = server.server_port
        for outbound in config['outbounds']:
            outbound.update(protocol='freedom', settings={'redirect': '127.0.0.1:' + str(targets[outbound['tag']])})
        inbounds = []
        ports = {}
        for inbound in config['inbounds']:
            if inbound['tag'].endswith('-tproxy'):
                continue
            inbound['listen'] = '127.0.0.1'
            inbound['port'] = free_port()
            ports[inbound['tag']] = inbound['port']
            if inbound['tag'].endswith('-transparent'):
                inbound['settings'] = {'network': 'tcp', 'address': '127.0.0.1',
                                       'port': targets['direct'], 'followRedirect': False}
                inbound.pop('streamSettings', None)
            inbounds.append(inbound)
        config['inbounds'] = inbounds

        def start(data, filename):
            path = tmp_path / filename
            path.write_text(json.dumps(data), encoding='utf-8')
            subprocess.run([os.environ['XRAY_TEST_BINARY'], 'run', '-test', '-c', str(path)],
                           capture_output=True, timeout=15, check=True)
            proc = subprocess.Popen([os.environ['XRAY_TEST_BINARY'], 'run', '-c', str(path)],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            processes.append(proc)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                assert proc.poll() is None, 'Xray fixture exited'
                try:
                    # Wait for every listener, using a complete HTTP exchange.
                    # Bare connect/close can strand the HTTP fixture on Linux.
                    for tag, port in ports.items():
                        transparent = tag.endswith('-transparent')
                        expected = 'direct' if transparent else tag.replace('in-', 'proxy-')
                        assert request(port, 'ready.example.net', socks=not transparent) == expected
                    return proc
                except OSError:
                    time.sleep(0.02)
            pytest.fail('Xray did not start')

        # Same rules as A for non-catalog domains: demonstrate the regression.
        old = copy.deepcopy(config)
        old['routing']['rules'] = [r for r in old['routing']['rules']
                                   if not r.get('ruleTag', '').startswith('cross-route-domains-')]
        proc = start(old, 'before.json')
        assert request(ports['in-vless2-transparent'], 'vless.example.org') == 'direct'
        proc.terminate()
        proc.wait(timeout=5)
        # Use fresh ports: Linux may still retain the previous connections.
        for inbound in config['inbounds']:
            inbound['port'] = free_port()
            ports[inbound['tag']] = inbound['port']
        start(config, 'after.json')
        for inbound in ('vless', 'vless2', 'vmess', 'hysteria2'):
            for target in policy.SUPPORTED_PROTOCOLS:
                assert request(ports['in-' + inbound + '-transparent'], target + '.example.org') == 'proxy-' + target
        assert request(ports['in-vless2-transparent'], 'exact.example.net') == 'proxy-vless'
        assert request(ports['in-vless2-transparent'], 'child.exact.example.net') == 'direct'
        assert request(ports['in-vless2-transparent'], 'unknown.example.net') == 'direct'
        assert request(ports['in-vless2-transparent'], 'connectivity.example.org') == 'direct'
        assert request(ports['in-vless2-transparent'], '') == 'direct'
        # Ambiguity retains each inbound's existing policy.
        assert request(ports['in-vless2-transparent'], 'child.conflict.example.org') == 'proxy-vless2'
        assert request(ports['in-vless-transparent'], 'child.conflict.example.org') == 'proxy-vless'
        for proto in policy.SUPPORTED_PROTOCOLS:
            assert request(ports['in-' + proto], 'vless.example.org', socks=True) == 'proxy-' + proto
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=5)
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
            output = proc.communicate(timeout=5)[0]
            if sys.exc_info()[0] is not None and output:
                print(output[-2000:].decode('utf-8', errors='replace'))
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
            assert not thread.is_alive()
