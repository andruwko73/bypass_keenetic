"""Official Xray/Hysteria only; all servers, keys and traffic are local fixtures."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

from test_xray_live_apply import lab, base_config, wait_api, exchange

pytestmark = pytest.mark.skipif(
    not os.environ.get('XRAY_TEST_BINARY') or not os.environ.get('HYSTERIA_TEST_BINARY'),
    reason='Official XRAY_TEST_BINARY and HYSTERIA_TEST_BINARY required')


@pytest.fixture
def hy_servers(lab, tmp_path):
    port, echo, start, api, connect = lab
    processes = []
    cert = json.loads(subprocess.run([os.environ['XRAY_TEST_BINARY'], 'tls', 'cert',
                      '-domain=localhost', '-json'], capture_output=True, timeout=10, check=True).stdout)
    cert_path, key_path = tmp_path / 'cert.pem', tmp_path / 'cert.key'
    cert_path.write_text('\n'.join(cert['certificate']) + '\n')
    key_path.write_text('\n'.join(cert['key']) + '\n')

    def server(target, *, auth='synthetic-auth', server_port=None, mask=False):
        server_port, socks = server_port or port(), port()
        start({'log': {'loglevel': 'none'}, 'inbounds': [{
            'port': socks, 'listen': '127.0.0.1', 'protocol': 'socks',
            'settings': {'auth': 'noauth', 'udp': True},
        }], 'outbounds': [{'protocol': 'freedom', 'settings': {'redirect': f'127.0.0.1:{target}'}}]})
        config = {'listen': f'127.0.0.1:{server_port}',
                  'tls': {'cert': str(cert_path), 'key': str(key_path)},
                  'auth': {'type': 'password', 'password': auth},
                  'outbounds': [{'name': 'local', 'type': 'socks5', 'socks5': {'addr': f'127.0.0.1:{socks}'}}]}
        if mask:
            config['obfs'] = {'type': 'salamander', 'salamander': {'password': 'synthetic-mask'}}
        path = tmp_path / f'hy-{len(processes)}.json'
        path.write_text(json.dumps(config))
        process = subprocess.Popen([os.environ['HYSTERIA_TEST_BINARY'], 'server', '-c', str(path)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(process)
        time.sleep(.3)
        assert process.poll() is None, 'local Hysteria server did not start'
        outbound = {'protocol': 'hysteria', 'settings': {'version': 2, 'address': '127.0.0.1', 'port': server_port},
                    'streamSettings': {'network': 'hysteria', 'security': 'tls',
                       'hysteriaSettings': {'version': 2, 'auth': auth},
                       'tlsSettings': {'serverName': 'localhost', 'alpn': ['h3'], 'disableSystemRoot': True,
                                       'certificates': [{'certificate': cert['certificate'], 'usage': 'verify'}]}}}
        if mask:
            outbound['streamSettings']['finalmask'] = {'udp': [{
                'type': 'salamander', 'settings': {'password': 'synthetic-mask'}}]}
        return outbound

    yield server
    for process in processes:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=4)


@pytest.mark.parametrize('mask', [False, True])
def test_hysteria_switch_and_return_preserves_tcp_udp(lab, hy_servers, mask):
    port, echo, start, api, connect = lab
    a, b = echo(b'A'), echo(b'B')
    first, second = hy_servers(a, mask=mask), hy_servers(b, auth='other-synthetic-auth', mask=mask)
    api_port, managed, control = port(), port(), port()
    config = base_config(api_port, {'managed': managed, 'control-in': control}, a)
    config['outbounds'][0] = dict(first, tag='generation-a')
    proc = start(config)
    wait_api(proc, api, api_port)
    old = [connect(managed), connect(managed, True), connect(control), connect(control, True)]
    for client in old:
        exchange(client, b'before', b'A')
    assert api(api_port, 'ado', config={'outbounds': [dict(second, tag='generation-b')]}).returncode == 0
    assert api(api_port, 'bo', '-b', 'choice', 'generation-b').returncode == 0
    assert api(api_port, 'rmo', 'generation-a').returncode == 0
    for number in range(30):
        for client in old:
            exchange(client, f'old-{number}'.encode(), b'A')
    new = [connect(managed), connect(managed, True)]
    for client in new:
        exchange(client, b'new', b'B')
    assert api(api_port, 'ado', config={'outbounds': [dict(first, tag='generation-c')]}).returncode == 0
    assert api(api_port, 'bo', '-b', 'choice', 'generation-c').returncode == 0
    assert api(api_port, 'rmo', 'generation-b').returncode == 0
    for client in new:
        exchange(client, b'second-still-open', b'B')
    for udp in (False, True):
        exchange(connect(managed, udp), b'returned', b'A')
    assert proc.poll() is None


def test_official_core_reuses_old_auth_for_same_destination(lab, hy_servers):
    port, echo, start, api, connect = lab
    a, api_port, managed = echo(b'A'), port(), port()
    first = hy_servers(a)
    config = base_config(api_port, {'managed': managed}, a)
    config['outbounds'][0] = dict(first, tag='generation-a')
    proc = start(config)
    wait_api(proc, api, api_port)
    exchange(connect(managed), b'first-auth', b'A')
    wrong = deepcopy(first)
    wrong['tag'] = 'wrong-auth'
    wrong['streamSettings']['hysteriaSettings']['auth'] = 'deliberately-incorrect-synthetic-auth'
    assert api(api_port, 'ado', config={'outbounds': [wrong]}).returncode == 0
    assert api(api_port, 'bo', '-b', 'choice', 'wrong-auth').returncode == 0
    # A false positive: data still flows with an invalid NEW password. The app
    # MUST detect this collision before mutating the live core or claiming success.
    exchange(connect(managed), b'wrong-auth-was-ignored', b'A')


@pytest.mark.parametrize('failed_health', [False, True])
def test_hysteria_runtime_persists_or_rolls_back_without_touching_control(lab, hy_servers, tmp_path, failed_health):
    from proxy_apply_coordinator import ApplyCoordinator
    from proxy_live_runtime import ProxyLiveRuntime
    from xray_live_apply import XrayApi, LiveApplyError, managed_config, balancer_tag
    port, echo, start, api, connect = lab
    a, b, api_port, managed, control = echo(b'A'), echo(b'B'), port(), port(), port()
    first, second = hy_servers(a), hy_servers(b, auth='synthetic-second')
    logical = base_config(api_port, {'managed': managed, 'control-in': control}, a)
    logical.pop('api')
    logical['inbounds'] = logical['inbounds'][1:]
    logical['outbounds'][0] = dict(first, tag='proxy-hysteria2')
    logical['routing'].pop('balancers')
    logical['routing']['rules'] = [
        {'type': 'field', 'inboundTag': ['managed'], 'outboundTag': 'proxy-hysteria2'},
        {'type': 'field', 'inboundTag': ['control-in'], 'outboundTag': 'control'}]
    private, ram = tmp_path / 'private', tmp_path / 'ram'
    private.mkdir(); ram.mkdir()
    path, key = tmp_path / 'installed.json', tmp_path / 'installed.key'
    path.write_text(json.dumps(managed_config(logical, api_port=api_port)))
    key.write_text('synthetic-old\n')
    process = start(managed_config(logical, api_port=api_port))
    wait_api(process, api, api_port, balancer_tag('proxy-hysteria2'))
    coordinator = ApplyCoordinator(ram)
    runtime = ProxyLiveRuntime(coordinator=coordinator, directory=private, ram_directory=ram,
        config_path=path, key_paths={'hysteria2': key}, binary=os.environ['XRAY_TEST_BINARY'],
        api_port=api_port, identity=lambda: str(process.pid) if process.poll() is None else None,
        allowed_protocols=('hysteria2',), detach_qualified=True,
        api=XrayApi(os.environ['XRAY_TEST_BINARY'], port=api_port, directory=ram))
    with coordinator.lock:
        runtime.register_controlled_load(logical, previous_identity=None, generation=0)
    old = [connect(managed), connect(managed, True), connect(control), connect(control, True)]
    for client in old:
        exchange(client, b'before', b'A')
    desired = deepcopy(logical)
    desired['outbounds'][0] = dict(second, tag='proxy-hysteria2')
    def verify():
        for udp in (False, True):
            exchange(connect(managed, udp), b'verify', b'B')
        return not failed_health
    ticket = coordinator.request_manual()
    with coordinator.transaction(ticket, manual=True):
        if failed_health:
            with pytest.raises(LiveApplyError):
                runtime.try_apply('hysteria2', 'synthetic-new', current=logical, desired=desired,
                                  ticket=ticket, verify=verify, precheck=lambda: True)
        else:
            assert runtime.try_apply('hysteria2', 'synthetic-new', current=logical, desired=desired,
                ticket=ticket, verify=verify, precheck=lambda: True) == 'hot'
    for client in old:
        exchange(client, b'after', b'A')
    for udp in (False, True):
        exchange(connect(managed, udp), b'new-flow', b'A' if failed_health else b'B')
    assert key.read_text() == ('synthetic-old\n' if failed_health else 'synthetic-new\n')
    assert runtime.hysteria_guard.check(second, runtime.identity())
    incompatible = deepcopy(second)
    incompatible['streamSettings']['hysteriaSettings']['auth'] = 'third-synthetic-auth'
    assert not runtime.hysteria_guard.check(incompatible, runtime.identity())
    assert process.poll() is None
