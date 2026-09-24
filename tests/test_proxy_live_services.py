import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from proxy_live_services import encode_key, restart_service, service_listener, SERVICE_PATHS


@pytest.mark.parametrize('protocol', ['trojan', 'shadowsocks'])
def test_only_selected_protocol_service_is_restarted(protocol):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        assert kwargs['stdout'] == kwargs['stderr'] == subprocess.DEVNULL
        assert kwargs['timeout'] == 20
        return SimpleNamespace(returncode=0)
    assert restart_service(protocol, 12345, run=run, listening=lambda p, port: p == protocol and port == 12345)
    assert calls == [[SERVICE_PATHS[protocol][0], 'restart']]


def test_failed_service_does_not_restart_core_or_retry():
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1)
    assert not restart_service('trojan', 12345, run=run)
    assert calls == [['/opt/etc/init.d/S22trojan', 'restart']]


def test_port_without_matching_service_cannot_attest_health(tmp_path):
    net = tmp_path / 'net'
    net.mkdir()
    (net / 'tcp').write_text('header\n0: 00000000:3039 00000000:0000 0A 0 0 0 0 0 1234\n')
    process = tmp_path / '42'
    process.mkdir()
    (process / 'cmdline').write_bytes(b'/opt/sbin/xray\0-c\0/opt/etc/trojan/config.json\0')
    assert not service_listener('trojan', 12345, proc_root=tmp_path)


@pytest.mark.skipif(os.name == 'nt', reason='Requires POSIX proc symlink semantics')
def test_listener_requires_matching_configuration_and_socket_owner(tmp_path):
    (tmp_path / 'net').mkdir()
    (tmp_path / 'net' / 'tcp6').write_text('header\n0: 00000000:3039 00000000:0000 0A 0 0 0 0 0 1234\n')
    process = tmp_path / '42'
    (process / 'fd').mkdir(parents=True)
    (process / 'fd' / '7').symlink_to('socket:[1234]')
    (process / 'cmdline').write_bytes(b'/opt/bin/trojan\0-c\0/opt/etc/trojan/config.json\0')
    assert service_listener('trojan', 12345, proc_root=tmp_path)
    (process / 'cmdline').write_bytes(b'/opt/bin/trojan\0-c\0/tmp/another-config.json\0')
    assert not service_listener('trojan', 12345, proc_root=tmp_path)


def test_key_files_keep_legacy_reader_compatible_format():
    ports = {'trojan': 12345, 'shadowsocks': 12346}
    key = 'trojan://synthetic-password@example.invalid:443?sni=example.invalid'
    value = json.loads(encode_key('trojan', key, ports=ports))
    assert value['raw_uri'] == key and value['local_port'] == 12345
    assert value['password'] == ['synthetic-password']
    key = 'ss://YWVzLTEyOC1nY206c3ludGhldGlj@example.invalid:443'
    value = json.loads(encode_key('shadowsocks', key, ports=ports))
    assert value['raw_uri'] == key and value['local_port'] == 12346
    assert encode_key('vless', 'synthetic-key', ports=ports) == b'synthetic-key\n'
