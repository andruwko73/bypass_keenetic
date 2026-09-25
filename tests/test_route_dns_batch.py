import json
from pathlib import Path
import subprocess
import socket
import struct
import threading
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import route_dns_batch as dns
from route_ipset_batch import NetIndex, members, remove_overlaps


def packet(flags=0x8180, answer=True):
    question = b'\x01x\x07example\0' + struct.pack('!HH', 1, 1)
    header = struct.pack('!6H', 123, flags, 1, int(answer), 0, 0)
    rr = b'\xc0\x0c' + struct.pack('!HHIH', 1, 1, 50, 4) + bytes([203, 0, 113, 7]) if answer else b''
    return header + question + rr


@pytest.mark.parametrize('mutation', ('id', 'name', 'length', 'cycle'))
def test_wire_rejects_malformed_or_unrelated_reply(mutation):
    data = bytearray(packet())
    if mutation == 'id': data[1] ^= 1
    if mutation == 'name': data[13] = ord('y')
    if mutation == 'length': data = data[:-1]
    if mutation == 'cycle': data[12:14] = b'\xc0\x0c'
    with pytest.raises(ValueError):
        dns.parse_response(bytes(data), 123, 'x.example', 'A')


def test_wire_positive_truncated_and_failure():
    assert dns.parse_response(packet(), 123, 'x.example', 'A') == (['203.0.113.7'], 50, True)
    assert dns.parse_response(packet(flags=0x8380, answer=False), 123, 'x.example', 'A') is None
    assert dns.parse_response(packet(flags=0x8182, answer=False), 123, 'x.example', 'A') == ([], 0, False)


def test_wire_negative_cache_uses_soa_minimum():
    raw = bytearray(packet(flags=0x8183, answer=False)); raw[8:10] = struct.pack('!H', 1)
    soa = b'\0\0' + struct.pack('!5I', 1, 2, 3, 4, 7)
    raw += b'\xc0\x0c' + struct.pack('!HHIH', 6, 1, 60, len(soa)) + soa
    assert dns.parse_response(bytes(raw), 123, 'x.example', 'A') == ([], 7, True)


@pytest.mark.parametrize('family,kind,ip', [('A', 1, '203.0.113.7'), ('AAAA', 28, '2001:db8::7')])
def test_wire_cname_chain_ttl_ignores_unrelated_answers(family, kind, ip):
    import ipaddress
    def name(value):
        return b''.join(bytes([len(v)]) + v.encode() for v in value.split('.')) + b'\0'
    def rr(owner, rtype, ttl, data):
        return name(owner) + struct.pack('!HHIH', rtype, 1, ttl, len(data)) + data
    question = name('x.example') + struct.pack('!HH', kind, 1)
    raw = struct.pack('!6H', 123, 0x8180, 1, 3, 0, 0) + question
    raw += rr('x.example', 5, 17, name('alias.example'))
    raw += rr('alias.example', kind, 90, ipaddress.ip_address(ip).packed)
    raw += rr('unrelated.example', kind, 1, ipaddress.ip_address(ip).packed)
    assert dns.parse_response(raw, 123, 'x.example', family) == ([ip], 17, True)


def test_wire_rejects_cname_crossing_record_boundary():
    raw = packet(answer=False)
    raw = raw[:6] + struct.pack('!H', 1) + raw[8:]
    raw += b'\xc0\x0c' + struct.pack('!HHIH', 5, 1, 30, 1) + b'\xc0\x0c'
    with pytest.raises(ValueError, match='CNAME'):
        dns.parse_response(raw, 123, 'x.example', 'A')


@pytest.mark.parametrize('tcp_fallback', [False, True])
def test_real_loopback_dns_transport_and_tcp_fallback(tcp_fallback):
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(('127.0.0.1', 0)); port = udp.getsockname()[1]; udp.settimeout(3)
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.bind(('127.0.0.1', port)); tcp.listen(1); tcp.settimeout(3)
    errors = []
    def serve():
        try:
            request, peer = udp.recvfrom(1024)
            data = packet(flags=0x8380, answer=False) if tcp_fallback else packet()
            udp.sendto(request[:2] + data[2:], peer)
            if tcp_fallback:
                client, _ = tcp.accept()
                with client:
                    client.settimeout(3)
                    req = client.recv(1024)
                    response = request[:2] + packet()[2:]
                    client.sendall(struct.pack('!H', len(response)) + response)
        except Exception as exc:
            errors.append(type(exc).__name__)
        finally:
            udp.close(); tcp.close()
    worker = threading.Thread(target=serve); worker.start()
    result = dns.query_dns(('x.example', 'A', '127.0.0.1', port))
    worker.join(5)
    assert not worker.is_alive() and not errors
    assert result == (['203.0.113.7'], 50, True)


def test_dns_ttl_includes_cname_and_filters_wrong_family_local_addresses():
    text = ''';; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1
example.org. 20 IN CNAME alias.example.org.
alias.example.org. 300 IN A 203.0.113.7
alias.example.org. 100 IN A 127.0.0.1
alias.example.org. 100 IN AAAA 2001:db8::1
'''
    def run(args, **kw):
        assert args[-4:] == ['example.org', '@127.0.0.1', '-p', '53']
        assert kw['timeout'] == 3.5
        return SimpleNamespace(returncode=0, stdout=text)
    assert dns.query_dns_dig(('example.org', 'A', '127.0.0.1', 53), run=run) == (['203.0.113.7'], 20, True)


@pytest.mark.parametrize('status,code,healthy', [('NXDOMAIN', 0, True), ('SERVFAIL', 0, False), ('NOERROR', 9, False)])
def test_dns_errors_are_not_cached_as_success(status, code, healthy):
    response = SimpleNamespace(returncode=code, stdout=';; status: ' + status + ', id: 1\n')
    assert dns.query_dns_dig(('x.example', 'A', '127.0.0.1', 53), run=lambda *a, **k: response) == ([], 0, healthy)


def test_shared_queue_ttl_expiry_and_bounded_stale_on_timeout(tmp_path):
    cache = tmp_path / 'cache.json'
    a = ('x.example', 'A', '127.0.0.1', 53)
    b = ('x.example', 'AAAA', '127.0.0.1', 53)
    calls = []
    def query(item):
        calls.append(item)
        return (['203.0.113.7'] if item == a else ['2001:db8::7']), 30, True
    result, stats = dns.resolve_queue([a, a, b], cache, now=100, query=query)
    assert len(calls) == 2 and stats['requested'] == 2
    result, stats = dns.resolve_queue([a, a, b], cache, now=120, query=query)
    assert len(calls) == 2 and stats['cached'] == 2
    failed = lambda _: ([], 0, False)
    result, stats = dns.resolve_queue([a, b], cache, now=135, query=failed)
    assert stats['stale'] == 2 and result[a] == ['203.0.113.7']
    result, stats = dns.resolve_queue([a, b], cache, now=701, query=failed)
    assert stats['stale'] == 0 and result[a] == []
    assert json.loads(cache.read_text())['entries'] == {}


def test_negative_answer_removes_old_positive_without_caching_negative(tmp_path):
    cache = tmp_path / 'cache.json'
    q = ('x.example', 'A', '127.0.0.1', 53)
    dns.resolve_queue([q], cache, now=1, query=lambda _: (['203.0.113.7'], 1, True))
    result, stats = dns.resolve_queue([q], cache, now=3, query=lambda _: ([], 0, True))
    assert result[q] == [] and json.loads(cache.read_text())['entries'] == {}


def test_batch_outputs_udp_ipv6_and_priority_from_one_queue(tmp_path, monkeypatch):
    (tmp_path / 'unblockvless.domains').write_text('youtube.com\nx.example\n')
    (tmp_path / 'unblockvlessudp.domains').write_text('youtube.com\n')
    (tmp_path / 'unblockvless2.domains').write_text('x.example\n')
    (tmp_path / 'excluded').write_text('203.0.113.8\n')
    captured = []
    def queue(queries, path, **kwargs):
        captured.extend(queries)
        return {q: (['203.0.113.7', '203.0.113.8'] if q[1] == 'A' else ['2001:db8:1:2::3']) for q in queries}, {}
    monkeypatch.setattr(dns, 'resolve_queue', queue)
    dns.batch(tmp_path, '123', dict(DNS_HOST='127.0.0.1', DNS_PORT='53',
        YOUTUBE_DNS_SAMPLE_SERVERS='1.1.1.1', VLESS_PRIORITY_DOMAINS='youtube.com',
        UDP_QUIC_EXCLUDE_SOURCE=str(tmp_path / 'excluded')))
    commands = (tmp_path / 'dns.restore').read_text().splitlines()
    assert 'add tmp_unblockvlessudp_123 203.0.113.7' in commands
    assert 'add tmp_unblockvlessudp_123 203.0.113.8' not in commands
    assert 'add tmp_unblockvless6_123 2001:db8:1:2::/64' in commands
    assert not any('unblockvless2v6' in c for c in commands)
    assert captured.count(('youtube.com', 'A', '127.0.0.1', 53)) == 1
    assert captured.count(('x.example', 'A', '127.0.0.1', 53)) == 1
    assert 'youtube.com A 203.0.113.7' in (tmp_path / 'priority.answers').read_text()


def test_hash_net_host_membership_differs_from_explicit_network_membership():
    index = NetIndex(['203.0.113.0/24', '2001:db8:1::/48'])
    assert index.contains('203.0.113.7') and index.contains('203.0.113.7/32')
    assert index.contains('203.0.113.0/24')
    assert not index.contains('203.0.113.0/25')
    assert not index.contains('203.0.112.0/23')
    assert index.contains('2001:db8:1::7')
    assert not index.contains('2001:db8:1::/64')
    assert not index.contains('2001:db8:2::7')


def test_extended_ipset_entries_use_kernel_fallback():
    with pytest.raises(ValueError):
        members('create test hash:net\nadd test 203.0.113.7 nomatch\n', 'test')
    with pytest.raises(ValueError):
        members('create test hash:net timeout 60\n', 'test')


def test_bulk_removal_matches_ordered_pairs_without_per_member_processes():
    calls = []
    data = {'a': ['203.0.113.7', '203.0.113.0/25'], 'b': ['203.0.113.0/24'], 'c': ['203.0.113.7']}
    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[1] == 'save':
            name = args[2]
            return SimpleNamespace(returncode=0, stdout='create ' + name + ' hash:net\n' +
                ''.join('add ' + name + ' ' + v + '\n' for v in data[name]))
        return SimpleNamespace(returncode=0)
    assert remove_overlaps([('a', 'b'), ('c', 'a')], run=run) == 2
    assert len(calls) == 4
    assert calls[-1][1]['input'] == 'del a 203.0.113.7\ndel c 203.0.113.7\n'
