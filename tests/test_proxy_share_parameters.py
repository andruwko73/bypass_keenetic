"""Synthetic share links and compatibility with unchanged v1.1050 outbounds."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import pool_probe_runner
import proxy_protocols
import xray_compat_runtime


VLESS = 'vless://00000000-0000-0000-0000-000000000000@example.com:443'
HY2 = 'hy2://fixture@example.com:443'


def legacy_cases():
    cases = {
        'vless-tcp': ('vless', VLESS + '?type=tcp'),
        'vless-tls': ('vless', VLESS + '?type=tcp&security=tls&sni=tls.example.com'),
        'vless-ws': ('vless', VLESS + '?type=ws&security=tls&host=ws.example.com&path=%2Fsample'),
        'vless-reality': ('vless', VLESS + '?security=reality&pbk=fixture&sid=ab&fp=firefox&flow=xtls-rprx-vision'),
        'vless-grpc': ('vless', VLESS + '?type=grpc&security=reality&pbk=fixture&serviceName=sample'),
        'vless2-reality': ('vless2', VLESS + '?security=reality&pbk=fixture&sid=ab&fp=chrome'),
        'hy2-plain': ('hysteria2', HY2 + '?sni=tls.example.com'),
        'hy2-pin': ('hysteria2', HY2 + '?insecure=1&pinSHA256=' + 'ab' * 32),
        'hy2-salamander': ('hysteria2', HY2 + '?obfs=salamander&obfs-password=fixture'),
        'shadowsocks': ('shadowsocks', 'ss://' + base64.b64encode(b'aes-128-gcm:fixture').decode() + '@example.com:8388'),
    }
    for network in ('tcp', 'ws', 'grpc'):
        cases['trojan-' + network] = ('trojan', 'trojan://fixture@example.com:443?' + urlencode({
            'type': network, 'sni': 'tls.example.com', 'path': '/sample', 'serviceName': 'sample',
        }))
        data = {
            'v': '2', 'add': 'example.com', 'port': '443',
            'id': '00000000-0000-0000-0000-000000000000', 'aid': '0',
            'net': network, 'tls': 'tls', 'sni': 'tls.example.com',
            'host': 'host.example.com', 'path': '/sample', 'serviceName': 'sample',
        }
        cases['vmess-' + network] = ('vmess', 'vmess://' + base64.b64encode(json.dumps(data).encode()).decode())
    return cases


@pytest.mark.parametrize('name', list(legacy_cases()))
def test_existing_outbound_matches_v1_1050(name):
    expected = json.loads((Path(__file__).parent / 'fixtures' / 'proxy_outbounds_v1_1050.json').read_text())
    proto, key = legacy_cases()[name]
    outbound = proxy_protocols.proxy_outbound_from_key(proto, key, 'fixture')
    serialized = json.dumps(outbound, sort_keys=True, separators=(',', ':')).encode()
    assert hashlib.sha256(serialized).hexdigest() == expected[name]


@pytest.mark.parametrize('proto', ['vless', 'vless2'])
def test_vless_tls_pin_and_client_parameters_reach_live_and_probe(proto):
    pin = 'ab' * 32 + ',' + 'cd' * 32
    key = VLESS + '?' + urlencode({
        'security': 'tls', 'type': 'tcp', 'flow': 'xtls-rprx-vision',
        'sni': 'tls.example.com', 'pcs': pin, 'vcn': 'tls.example.com,alt.example.com',
        'fp': 'firefox', 'alpn': 'h2,http/1.1',
    })
    outbound = proxy_protocols.proxy_outbound_from_key(proto, key, 'fixture')
    probe = pool_probe_runner.pool_probe_outbound(proto, key, 'fixture', proxy_protocols.proxy_outbound_from_key)
    expected_tls = {
        'serverName': 'tls.example.com', 'fingerprint': 'firefox', 'alpn': ['h2', 'http/1.1'],
        'pinnedPeerCertSha256': pin, 'verifyPeerCertByName': 'tls.example.com,alt.example.com',
    }
    assert outbound['streamSettings']['tlsSettings'] == expected_tls
    assert probe['streamSettings']['tlsSettings'] == expected_tls
    assert outbound['settings']['vnext'][0]['users'][0]['flow'] == 'xtls-rprx-vision'
    assert 'allowInsecure' not in json.dumps(outbound)


@pytest.mark.parametrize('network', ['xhttp', 'splithttp'])
@pytest.mark.parametrize('security', ['tls', 'reality'])
def test_vless_xhttp_preserves_transport_settings(network, security):
    extra = {'noSSEHeader': True, 'xPaddingBytes': '100-200', 'headers': {'X-Sample': 'fixture'}}
    key = VLESS + '?' + urlencode({
        'security': security, 'type': network, 'path': '/stream?sample=one&two=three',
        'host': 'edge.example.com', 'mode': 'packet-up', 'extra': json.dumps(extra),
        'pbk': 'fixture',
    })
    stream = proxy_protocols.proxy_outbound_from_key('vless', key, 'fixture')['streamSettings']
    assert stream['network'] == 'xhttp'
    assert stream['security'] == security
    assert stream['xhttpSettings'] == {
        'path': '/stream?sample=one&two=three', 'host': 'edge.example.com',
        'mode': 'packet-up', 'extra': extra,
    }


def hy2_with_mask(mask, suffix=''):
    return HY2 + '?' + urlencode({'fm': json.dumps(mask)}) + suffix


@pytest.mark.parametrize('version', [(26, 2, 6), (26, 3, 27), (26, 7, 28)])
def test_hysteria2_finalmask_uses_matching_core_schema(monkeypatch, version):
    monkeypatch.setattr(xray_compat_runtime, 'xray_version', lambda: version)
    mask = {'quicParams': {'debug': False, 'congestion': 'bbr'}}
    key = hy2_with_mask(mask)
    before = proxy_protocols.parse_hysteria2_key(key)
    stream = proxy_protocols.proxy_outbound_from_key('hysteria2', key, 'fixture')['streamSettings']
    probe = pool_probe_runner.pool_probe_outbound('hysteria2', key, 'fixture', proxy_protocols.proxy_outbound_from_key)
    assert stream == probe['streamSettings']
    assert proxy_protocols.parse_hysteria2_key(key) == before
    if version < (26, 3, 27):
        assert stream['hysteriaSettings']['congestion'] == 'bbr'
        assert 'finalmask' not in stream
    else:
        assert stream['finalmask'] == mask
        assert 'congestion' not in stream['hysteriaSettings']


def test_hysteria2_legacy_quic_bandwidth_hopping_and_obfs(monkeypatch):
    monkeypatch.setattr(xray_compat_runtime, 'xray_version', lambda: (26, 2, 6))
    mask = {'quicParams': {
        'congestion': 'brutal', 'brutalUp': '10 mbps', 'brutalDown': 0,
        'udpHop': {'ports': '10000-10010', 'interval': '5-10'},
    }}
    key = hy2_with_mask(mask, '&obfs=salamander&obfs-password=fixture')
    stream = proxy_protocols.proxy_outbound_from_key('hysteria2', key, 'fixture')['streamSettings']
    assert stream['hysteriaSettings'] == {
        'version': 2, 'auth': 'fixture', 'congestion': 'brutal',
        'up': '10 mbps', 'down': '0', 'udphop': {'port': '10000-10010', 'interval': '5-10'},
    }
    assert stream['finalmask']['udp'] == [{'type': 'salamander', 'settings': {'password': 'fixture'}}]


def test_hysteria2_finalmask_layers_preserved_without_version_probe(monkeypatch):
    def unexpected_version_read():
        pytest.fail('No version subprocess needed for unchanged finalmask layers')
    monkeypatch.setattr(xray_compat_runtime, 'xray_version', unexpected_version_read)
    mask = {'udp': [{'type': 'salamander', 'settings': {'password': 'fixture'}}]}
    stream = proxy_protocols.proxy_outbound_from_key('hysteria2', hy2_with_mask(mask), 'fixture')['streamSettings']
    assert stream['finalmask'] == mask
    with pytest.raises(ValueError, match='одновременно'):
        proxy_protocols.parse_hysteria2_key(hy2_with_mask(mask, '&obfs=salamander&obfs-password=other'))


@pytest.mark.parametrize('mask', [[], {'unknown': 'private-value'}, {'udp': {}}, {'udp': [None]},
                                       {'udp': [{'type': 'salamander', 'settings': []}]}, {'quicParams': []}])
def test_hysteria2_malformed_finalmask_rejected_without_secret(mask):
    with pytest.raises(ValueError) as error:
        proxy_protocols.parse_hysteria2_key(hy2_with_mask(mask))
    assert 'private-value' not in str(error.value)


def test_unsupported_or_unknown_core_does_not_silently_drop_quic(monkeypatch):
    monkeypatch.setattr(xray_compat_runtime, 'xray_version', lambda: (26, 2, 6))
    for quic in ({'bbrProfile': 'conservative'}, {'debug': True}, {'udpHop': {'unknown': 'private-value'}}):
        with pytest.raises(ValueError) as error:
            proxy_protocols.proxy_outbound_from_key('hysteria2', hy2_with_mask({'quicParams': quic}), 'fixture')
        assert 'private-value' not in str(error.value)
    monkeypatch.setattr(xray_compat_runtime, 'xray_version', lambda: None)
    with pytest.raises(ValueError, match='версию Xray'):
        proxy_protocols.proxy_outbound_from_key('hysteria2', hy2_with_mask({'quicParams': {'congestion': 'bbr'}}), 'fixture')


@pytest.mark.parametrize('parameter,value', [('extra', '{private-value'), ('extra', '[]'), ('mode', 'private-value')])
def test_invalid_xhttp_parameters_do_not_expose_values(parameter, value):
    key = VLESS + '?' + urlencode({'type': 'xhttp', parameter: value})
    with pytest.raises(ValueError) as error:
        proxy_protocols.proxy_outbound_from_key('vless', key, 'fixture')
    assert 'private-value' not in str(error.value)


def test_irrelevant_extra_does_not_change_existing_tcp_key():
    plain = VLESS + '?type=tcp&security=tls'
    with_irrelevant_extra = plain + '&extra=legacy-unused-text'
    assert proxy_protocols.proxy_outbound_from_key('vless', plain, 'fixture') == proxy_protocols.proxy_outbound_from_key('vless', with_irrelevant_extra, 'fixture')


def test_version_cache_tracks_binary_changes_and_retries_failures(monkeypatch, tmp_path):
    binary = tmp_path / 'xray-fixture'
    binary.write_bytes(b'fixture')
    monkeypatch.setattr(xray_compat_runtime, '_resolve_binary', lambda *args: str(binary))
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(args, 3)
        return SimpleNamespace(returncode=0, stdout='Xray 26.2.6 (Xray, Penetrates Everything.)')
    monkeypatch.setattr(xray_compat_runtime.subprocess, 'run', run)
    xray_compat_runtime._read_xray_version.cache_clear()
    try:
        assert xray_compat_runtime.xray_version() is None
        assert xray_compat_runtime.xray_version() == (26, 2, 6)
        assert xray_compat_runtime.xray_version() == (26, 2, 6)
        assert len(calls) == 2
        binary.write_bytes(b'updated-fixture')
        assert xray_compat_runtime.xray_version() == (26, 2, 6)
        assert len(calls) == 3
    finally:
        xray_compat_runtime._read_xray_version.cache_clear()
