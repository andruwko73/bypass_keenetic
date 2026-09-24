"""Real-core API experiments. All traffic and configuration are synthetic/local.

These tests establish routing semantics, NOT production transport eligibility.
"""
import contextlib
import json
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import sys
import threading
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from xray_live_apply import XrayApi, LiveApplyError, balancer_tag, managed_config, switch_prepared_outbound


pytestmark = pytest.mark.skipif(not os.environ.get('XRAY_TEST_BINARY'), reason='XRAY_TEST_BINARY required')


class TcpEcho(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(4)
        try:
            while data := self.request.recv(4096):
                self.request.sendall(self.server.label + data)
        except (OSError, TimeoutError):
            pass


class UdpEcho(socketserver.BaseRequestHandler):
    def handle(self):
        data, sock = self.request
        sock.sendto(self.server.label + data, self.client_address)


class TcpServer(socketserver.ThreadingTCPServer):
    daemon_threads = True


@pytest.fixture
def lab(tmp_path):
    binary = os.environ['XRAY_TEST_BINARY']
    servers, threads, processes, clients = [], [], [], []
    ports = set()

    def port():
        while True:
            with socket.socket() as s:
                s.bind(('127.0.0.1', 0))
                value = s.getsockname()[1]
            if value not in ports:
                ports.add(value)
                return value

    def echo(label):
        tcp = TcpServer(('127.0.0.1', 0), TcpEcho)
        udp = socketserver.UDPServer(('127.0.0.1', tcp.server_address[1]), UdpEcho)
        for server in (tcp, udp):
            server.label = label
            servers.append(server)
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .03})
            threads.append(thread)
            thread.start()
        return tcp.server_address[1]

    def start(config):
        path = tmp_path / ('core-' + str(len(processes)) + '.json')
        path.write_text(json.dumps(config), encoding='utf-8')
        result = subprocess.run([binary, 'run', '-test', '-c', str(path)], capture_output=True, timeout=15)
        assert result.returncode == 0, result.stderr.decode(errors='replace')[-1500:]
        process = subprocess.Popen([binary, 'run', '-c', str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(process)
        return process

    def api(api_port, command, *args, config=None):
        argv = [binary, 'api', command, '--server=127.0.0.1:' + str(api_port), '-timeout=3']
        if config is not None:
            path = tmp_path / 'api-candidate.json'
            path.write_text(json.dumps(config), encoding='utf-8')
            args = (*args, str(path))
        return subprocess.run([*argv, *args], capture_output=True, timeout=6)

    def connect(value, udp=False):
        client = socket.socket(type=socket.SOCK_DGRAM if udp else socket.SOCK_STREAM)
        clients.append(client)
        client.settimeout(3)
        client.connect(('127.0.0.1', value))
        return client

    yield port, echo, start, api, connect
    for client in clients:
        client.close()
    for process in processes:
        if process.poll() is None:
            process.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=4)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=4)
    for server in servers:
        server.shutdown()
        server.server_close()
    for thread in threads:
        thread.join(timeout=4)
        assert not thread.is_alive()


def exchange(client, payload, expected):
    client.sendall(payload)
    received = bytearray()
    while len(received) < len(payload) + 1:
        part = client.recv(4096)
        assert part, 'stream closed'
        received.extend(part)
    assert received == expected + payload


def base_config(api_port, input_ports, target):
    return {
        'log': {'loglevel': 'none'},
        'api': {'tag': 'api', 'services': ['HandlerService', 'RoutingService']},
        'inbounds': [
            {'tag': 'api-in', 'listen': '127.0.0.1', 'port': api_port, 'protocol': 'dokodemo-door',
             'settings': {'address': '127.0.0.1'}},
            *[{'tag': tag, 'listen': '127.0.0.1', 'port': p, 'protocol': 'dokodemo-door',
               'settings': {'network': 'tcp,udp', 'address': '127.0.0.1', 'port': target}}
              for tag, p in input_ports.items()],
        ],
        'outbounds': [
            {'tag': 'generation-a', 'protocol': 'freedom', 'settings': {'redirect': f'127.0.0.1:{target}'}},
            {'tag': 'control', 'protocol': 'freedom', 'settings': {'redirect': f'127.0.0.1:{target}'}},
        ],
        'routing': {'domainStrategy': 'AsIs', 'balancers': [
            {'tag': 'choice', 'selector': ['generation-a'], 'strategy': {'type': 'random'}},
        ], 'rules': [
            {'type': 'field', 'inboundTag': ['api-in'], 'outboundTag': 'api'},
            {'type': 'field', 'inboundTag': ['managed'], 'balancerTag': 'choice'},
            {'type': 'field', 'inboundTag': ['control-in'], 'outboundTag': 'control'},
        ]},
    }


def wait_api(process, api, api_port, balancer='choice'):
    until = time.monotonic() + 8
    while time.monotonic() < until:
        assert process.poll() is None, 'core exited during startup'
        result = api(api_port, 'bi', balancer)
        if result.returncode == 0:
            return
        time.sleep(.03)
    pytest.fail('core API did not start: ' + result.stderr.decode(errors='replace')[-500:])


def test_balancer_override_preserves_established_tcp_udp_and_control(lab):
    port, echo, start, api, connect = lab
    a, b = echo(b'A'), echo(b'B')
    api_port, managed, control = port(), port(), port()
    proc = start(base_config(api_port, {'managed': managed, 'control-in': control}, a))
    wait_api(proc, api, api_port)
    old = [connect(managed), connect(managed, True), connect(control), connect(control, True)]
    for client in old:
        exchange(client, b'before', b'A')
    result = api(api_port, 'ado', config={'outbounds': [
        {'tag': 'generation-b', 'protocol': 'freedom', 'settings': {'redirect': f'127.0.0.1:{b}'}}
    ]})
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert api(api_port, 'bo', '-b', 'choice', 'generation-b').returncode == 0
    for number in range(20):
        for client in old:
            exchange(client, f'old-{number}'.encode(), b'A')
        time.sleep(.01)
    for udp in (False, True):
        exchange(connect(managed, udp), b'new', b'B')
        exchange(connect(control, udp), b'independent', b'A')
    assert api(api_port, 'bo', '-b', 'choice', 'generation-a').returncode == 0
    exchange(connect(managed), b'rollback', b'A')
    for client in old:
        exchange(client, b'after-rollback', b'A')
    assert proc.poll() is None


def test_routing_replace_failure_is_not_atomic(lab):
    port, echo, start, api, connect = lab
    target = echo(b'A')
    api_port, managed = port(), port()
    proc = start(base_config(api_port, {'managed': managed}, target))
    wait_api(proc, api, api_port)
    # Keep the API rule, then fail while resolving a nonexistent balancer.
    result = api(api_port, 'adrules', config={'routing': {'rules': [
        {'type': 'field', 'inboundTag': ['api-in'], 'outboundTag': 'api', 'ruleTag': 'partial'},
        {'type': 'field', 'inboundTag': ['managed'], 'balancerTag': 'missing', 'ruleTag': 'bad'},
    ]}})
    assert result.returncode != 0
    listed = api(api_port, 'lsrules')
    assert listed.returncode == 0
    assert b'partial' in listed.stdout
    assert b'control' not in listed.stdout
    assert proc.poll() is None


def test_runtime_api_observation_schema(lab):
    port, echo, start, api, connect = lab
    target, api_port = echo(b'A'), port()
    proc = start(base_config(api_port, {'managed': port()}, target))
    wait_api(proc, api, api_port)
    for command, args in [('lso', ()), ('bi', ('-json', 'choice'))]:
        result = api(api_port, command, *args)
        assert result.returncode == 0
        value = json.loads(result.stdout)
        if command == 'lso':
            assert {item['tag'] for item in value['outbounds']} == {'generation-a', 'control'}
        else:
            assert value['balancer']['override'].get('target', '') == ''


def test_runtime_observation_detects_external_api_change(lab, tmp_path):
    port, echo, start, api, connect = lab
    target, api_port = echo(b'A'), port()
    proc = start(base_config(api_port, {'managed': port()}, target))
    wait_api(proc, api, api_port)
    adapter = XrayApi(os.environ['XRAY_TEST_BINARY'], port=api_port, directory=tmp_path)
    before = adapter.observation(['choice'])
    assert before == adapter.observation(['choice'])
    adapter.add({'tag': 'new-handler', 'protocol': 'freedom'})
    added = adapter.observation(['choice'])
    assert added != before
    adapter.select('choice', 'new-handler')
    assert adapter.observation(['choice']) != added
    assert proc.poll() is None


def proxy_pair(protocol, server_port, credential):
    if protocol in ('vless', 'vmess'):
        client = {'id': credential}
        settings = {'clients': [client]}
        user = dict(client)
        if protocol == 'vless':
            settings['decryption'] = 'none'
            user['encryption'] = 'none'
        outbound_settings = {'vnext': [{'address': '127.0.0.1', 'port': server_port, 'users': [user]}]}
    elif protocol == 'trojan':
        settings = {'clients': [{'password': credential}]}
        outbound_settings = {'servers': [{'address': '127.0.0.1', 'port': server_port, 'password': credential}]}
    else:
        settings = {'method': 'aes-128-gcm', 'password': credential, 'network': 'tcp,udp'}
        outbound_settings = {'servers': [dict(settings, address='127.0.0.1', port=server_port)]}
    inbound = {'tag': 'synthetic-server', 'listen': '127.0.0.1', 'port': server_port,
               'protocol': protocol, 'settings': settings}
    outbound = {'protocol': protocol, 'settings': outbound_settings,
                'streamSettings': {'network': 'tcp', 'security': 'none'}}
    return inbound, outbound


QUALIFIED_CASES = [
    ('vless', False, 'none'), ('vmess', False, 'none'), ('trojan', False, 'none'),
    ('shadowsocks', False, 'none'), ('vless', True, 'none'), ('vmess', True, 'none'),
    ('vless', False, 'tls'), ('vmess', False, 'tls'), ('trojan', False, 'tls'),
    ('vless', True, 'tls'), ('vmess', True, 'tls'), ('vless', False, 'reality'),
    ('vless', True, 'reality'),
    ('vless', False, 'tls-vision'), ('vless', False, 'reality-vision'),
]


def secure_candidates(lab, protocol, mux, security, targets, policy=None):
    port, echo, start, api, connect = lab
    vision = security.endswith('-vision')
    security = security.removesuffix('-vision')
    if security != 'none':
        cert = json.loads(subprocess.run(
            [os.environ['XRAY_TEST_BINARY'], 'tls', 'cert', '-domain=localhost', '-json'],
            capture_output=True, timeout=10, check=True,
        ).stdout)
    if security == 'reality':
        decoy = port()
        start({'log': {'loglevel': 'none'}, 'inbounds': [{
            'port': decoy, 'listen': '127.0.0.1', 'protocol': 'dokodemo-door',
            'settings': {'address': '127.0.0.1', 'port': targets[0], 'network': 'tcp'},
            'streamSettings': {'network': 'tcp', 'security': 'tls',
                               'tlsSettings': {'certificates': [cert]}},
        }], 'outbounds': [{'protocol': 'freedom'}]})
        key_lines = subprocess.run([os.environ['XRAY_TEST_BINARY'], 'x25519'],
                                   capture_output=True, timeout=10, check=True).stdout.decode().splitlines()
        keys = dict(line.split(': ', 1) for line in key_lines if ': ' in line)
    credentials = ['00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002']
    candidates = []
    for target, credential in zip(targets, credentials):
        inbound, outbound = proxy_pair(protocol, port(), credential)
        if vision:
            inbound['settings']['clients'][0]['flow'] = 'xtls-rprx-vision'
            outbound['settings']['vnext'][0]['users'][0]['flow'] = 'xtls-rprx-vision'
        if security == 'tls':
            inbound['streamSettings'] = {'network': 'tcp', 'security': 'tls',
                                         'tlsSettings': {'certificates': [cert]}}
            outbound['streamSettings'] = {'network': 'tcp', 'security': 'tls',
                                          'tlsSettings': {'serverName': 'localhost', 'disableSystemRoot': True,
                                                          'certificates': [{'certificate': cert['certificate'],
                                                                            'usage': 'verify'}]}}
        elif security == 'reality':
            inbound['streamSettings'] = {'network': 'tcp', 'security': 'reality', 'realitySettings': {
                'target': f'127.0.0.1:{decoy}', 'serverNames': ['localhost'],
                'privateKey': keys['PrivateKey'], 'shortIds': ['aabb'],
            }}
            outbound['streamSettings'] = {'network': 'tcp', 'security': 'reality', 'realitySettings': {
                'serverName': 'localhost', 'fingerprint': 'chrome',
                'password': keys['Password'], 'shortId': 'aabb',
            }}
        start({'log': {'loglevel': 'none'}, 'policy': policy or {}, 'inbounds': [inbound], 'outbounds': [
            {'protocol': 'freedom', 'settings': {'redirect': f'127.0.0.1:{target}'}}
        ]})
        if mux:
            outbound['mux'] = {'enabled': True, 'concurrency': 8, 'xudpConcurrency': 8}
        candidates.append(outbound)
    return candidates


@pytest.mark.parametrize('protocol,mux,security', QUALIFIED_CASES)
def test_protocol_remove_preserves_existing_tcp_udp(lab, protocol, mux, security):
    port, echo, start, api, connect = lab
    a, b = echo(b'A'), echo(b'B')
    candidates = secure_candidates(lab, protocol, mux, security, (a, b))
    api_port, managed, control = port(), port(), port()
    config = base_config(api_port, {'managed': managed, 'control-in': control}, a)
    config['outbounds'][0] = dict(candidates[0], tag='generation-a')
    proc = start(config)
    wait_api(proc, api, api_port)
    old = [connect(managed), connect(managed, True), connect(control), connect(control, True)]
    for client in old:
        exchange(client, b'before', b'A')
    assert api(api_port, 'ado', config={'outbounds': [dict(candidates[1], tag='generation-b')]}).returncode == 0
    assert api(api_port, 'bo', '-b', 'choice', 'generation-b').returncode == 0
    assert api(api_port, 'rmo', 'generation-a').returncode == 0
    for number in range(30):
        for client in old:
            exchange(client, f'old-{number}'.encode(), b'A')
    for udp in (False, True):
        exchange(connect(managed, udp), b'new', b'B')
        exchange(connect(control, udp), b'independent', b'A')
    assert proc.poll() is None


@pytest.mark.parametrize('protocol,mux,security', QUALIFIED_CASES)
def test_removed_generations_release_idle_goroutines(lab, protocol, mux, security):
    port, echo, start, api, connect = lab
    target, api_port, managed = echo(b'A'), port(), port()
    policy = {'levels': {'0': {'connIdle': 1, 'uplinkOnly': 1, 'downlinkOnly': 1}}}
    outbound = secure_candidates(lab, protocol, mux, security, (target,), policy)[0]
    config = base_config(api_port, {'managed': managed}, target)
    config['api']['services'].append('StatsService')
    config['stats'] = {}
    config['policy'] = policy
    proc = start(config)
    wait_api(proc, api, api_port)

    def snapshot():
        result = api(api_port, 'statssys')
        assert result.returncode == 0
        value = {key.lower(): item for key, item in json.loads(result.stdout).items()}
        assert 'numgoroutine' in value and 'alloc' in value, sorted(value)
        sample = {k: int(value[k.lower()]) for k in ('numGoroutine', 'alloc')}
        for key in ('numGC', 'liveObjects', 'sys'):
            sample[key] = int(value[key.lower()]) if key.lower() in value else None
        if sys.platform.startswith('linux'):
            status = Path(f'/proc/{proc.pid}/status').read_text()
            sample['rss_bytes'] = next(int(line.split()[1]) * 1024 for line in status.splitlines()
                                       if line.startswith('VmRSS:'))
        return sample

    samples = [snapshot()]
    for cycle in range(4):
        for index in range(8):
            tag = f'candidate-{cycle}-{index}'
            assert api(api_port, 'ado', config={'outbounds': [dict(outbound, tag=tag)]}).returncode == 0
            assert api(api_port, 'bo', '-b', 'choice', tag).returncode == 0
            client = connect(managed)
            exchange(client, b'candidate', b'A')
            client.close()
            assert api(api_port, 'bo', '-b', 'choice', 'generation-a').returncode == 0
            assert api(api_port, 'rmo', tag).returncode == 0
        # The synthetic core uses a one-second inactivity policy. This is NOT
        # an inference of drain for the production defaults or remote servers.
        time.sleep(3)
        samples.append(snapshot())
    assert all(s['numGoroutine'] > 0 for s in samples), samples
    if os.environ.get('XRAY_RESOURCE_REPORT'):
        with Path(os.environ['XRAY_RESOURCE_REPORT']).open('a', encoding='utf-8') as report:
            report.write(json.dumps({'protocol': protocol, 'mux': mux, 'security': security, 'samples': samples}) + '\n')
    assert samples[-1]['numGoroutine'] <= samples[0]['numGoroutine'] + 12, samples
    # Compare warmed windows. Alloc includes garbage awaiting collection; RSS
    # can retain Go heap pages, so these are bounded regression gates, not a
    # claim that every byte was returned to the OS or no long-term leak exists.
    assert samples[-1]['alloc'] <= samples[1]['alloc'] + 4 * 1024 * 1024, samples
    if 'rss_bytes' in samples[-1]:
        assert samples[-1]['rss_bytes'] <= samples[1]['rss_bytes'] + 8 * 1024 * 1024, samples


@pytest.mark.parametrize('protocol', ['vless', 'vmess', 'trojan', 'shadowsocks'])
@pytest.mark.parametrize('failure', [None, 'health', 'disk', 'lost_response'])
@pytest.mark.parametrize('executor', ['api', 'runtime', 'runtime_detach'])
def test_real_executor_preserves_control_and_recovers(lab, tmp_path, failure, executor, protocol):
    port, echo, start, api, connect = lab
    a, b, managed, control, api_port = echo(b'A'), echo(b'B'), port(), port(), port()
    candidates = []
    for target, credential in [(a, '00000000-0000-4000-8000-000000000004'),
                               (b, '00000000-0000-4000-8000-000000000005')]:
        inbound, outbound = proxy_pair(protocol, port(), credential)
        start({'log': {'loglevel': 'none'}, 'inbounds': [inbound], 'outbounds': [
            {'protocol': 'freedom', 'settings': {'redirect': f'127.0.0.1:{target}'}}
        ]})
        candidates.append(outbound)
    original = {
        'log': {'loglevel': 'none'},
        'inbounds': [
            {'tag': tag, 'protocol': 'dokodemo-door', 'listen': '127.0.0.1', 'port': p,
             'settings': {'address': '127.0.0.1', 'port': a, 'network': 'tcp,udp'}}
            for tag, p in [('managed', managed), ('control', control)]
        ],
        'outbounds': [dict(candidates[0], tag='proxy-' + protocol), {'tag': 'control', 'protocol': 'freedom'}],
        'routing': {'domainStrategy': 'AsIs', 'rules': [
            {'type': 'field', 'inboundTag': ['managed'], 'outboundTag': 'proxy-' + protocol},
            {'type': 'field', 'inboundTag': ['control'], 'outboundTag': 'control'},
        ]},
    }
    core = start(managed_config(original, api_port=api_port))
    wait_api(core, api, api_port, balancer_tag('proxy-' + protocol))
    adapter = XrayApi(os.environ['XRAY_TEST_BINARY'], port=api_port, directory=tmp_path)
    if executor != 'api':
        from proxy_apply_coordinator import ApplyCoordinator
        from proxy_live_runtime import ProxyLiveRuntime
        private, ram = tmp_path / 'private', tmp_path / 'ram'
        private.mkdir()
        ram.mkdir()
        coordinator = ApplyCoordinator(ram)
        config_path, key_path = tmp_path / 'installed.json', tmp_path / 'installed-key'
        config_path.write_text(json.dumps(managed_config(original, api_port=api_port)))
        key_path.write_text('synthetic-old\n')
        runtime = ProxyLiveRuntime(
            coordinator=coordinator, directory=private, ram_directory=ram,
            config_path=config_path, key_paths={protocol: key_path}, binary=os.environ['XRAY_TEST_BINARY'],
            api_port=api_port, identity=lambda: str(core.pid) if core.poll() is None else None,
            allowed_protocols=(protocol,), api=adapter, detach_qualified=executor == 'runtime_detach',
        )
        with coordinator.lock:
            runtime.register_controlled_load(original, previous_identity=None, generation=0)
        if failure == 'disk':
            def fail_commit():
                raise OSError('synthetic disk failure before commit')
            runtime.bundle.commit = fail_commit
    old = [connect(managed), connect(managed, True), connect(control), connect(control, True)]
    for client in old:
        exchange(client, b'before', b'A')
    phases, saved = [], []
    select = adapter.select
    lost = [failure == 'lost_response']
    def select_with_failure(*args):
        select(*args)
        if lost[0]:
            lost[0] = False
            raise LiveApplyError('synthetic lost reply after real API success')
    adapter.select = select_with_failure
    def verify():
        for udp in (False, True):
            exchange(connect(managed, udp), b'verify', b'B')
        return failure != 'health'
    def persist(target):
        if failure == 'disk':
            raise OSError('synthetic disk failure before commit')
        saved.append(target)
    def run():
        if executor != 'api':
            from copy import deepcopy
            desired = deepcopy(original)
            desired['outbounds'][0] = dict(candidates[1], tag='proxy-' + protocol)
            ticket = coordinator.request_manual()
            with coordinator.transaction(ticket, manual=True):
                return runtime.try_apply(protocol, 'synthetic-new', current=original, desired=desired,
                                         ticket=ticket, verify=verify, precheck=lambda: True)
        return switch_prepared_outbound(
            adapter, logical_tag='proxy-' + protocol, old_target='proxy-' + protocol + '@initial.',
            candidate=candidates[1], generation=1, checkpoint=lambda *v: phases.append(v[0]),
            require_current=lambda: None, verify=verify, persist=persist,
            current_identity=lambda: core.pid if core.poll() is None else None, expected_identity=core.pid,
        )
    if failure:
        with pytest.raises(LiveApplyError, match='previous route restored'):
            run()
        assert not saved
        if executor == 'api':
            assert phases[-1] == 'rolled_back'
        else:
            assert key_path.read_text() == 'synthetic-old\n'
            assert not runtime.pending_path.exists()
            assert runtime._observe(runtime._receipt()['targets']) == runtime._receipt()['observed']
        for udp in (False, True):
            exchange(connect(managed, udp), b'restored', b'A')
    else:
        assert run() == ('proxy-' + protocol + '@g1.' if executor == 'api' else 'hot')
        if executor == 'api':
            assert saved == ['proxy-' + protocol + '@g1.']
        else:
            assert key_path.read_text() == 'synthetic-new\n'
            assert not runtime.pending_path.exists()
    for client in old:
        exchange(client, b'continuous', b'A')
    assert core.poll() is None
