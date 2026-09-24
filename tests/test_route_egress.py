import ipaddress
import os
import platform
import socket
import struct
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from route_egress import (SocketEvidence,parse_diag_messages,tcp_socket_snapshot,
                          process_socket_inodes,verify_bound_egress,attest_process_egress,
                          ipv4_tcp_tuple,PacketEgressCapture)
from proxy_apply_coordinator import process_identity
from test_xray_live_apply import lab,base_config,wait_api,exchange


def message(*, seq=42, family=socket.AF_INET, bound=7, inode=123, kind=20, payload=None):
    if payload is None:
        raw=bytearray(72);raw[0]=family;raw[1]=1
        struct.pack_into('!HH',raw,4,32100,443)
        source=ipaddress.ip_address('10.0.0.2' if family==socket.AF_INET else '2001:db8::1').packed
        target=ipaddress.ip_address('203.0.113.7' if family==socket.AF_INET else '2001:db8::2').packed
        raw[8:8+len(source)]=source;raw[24:24+len(target)]=target
        struct.pack_into('=I',raw,40,bound);struct.pack_into('=I',raw,68,inode)
        payload=bytes(raw)
    return struct.pack('=IHHII',len(payload)+16,kind,0,seq,0)+payload


@pytest.mark.parametrize('family',[socket.AF_INET,socket.AF_INET6])
def test_kernel_message_layout(family):
    rows,done=parse_diag_messages(message(family=family)+message(kind=3,payload=b''),42)
    assert done and len(rows)==1
    row=rows[0]
    assert row.interface_index==7 and row.inode==123
    assert row.destination_port==443 and row.source_port==32100
    assert ipaddress.ip_address(row.destination_ip).version==(4 if family==socket.AF_INET else 6)


@pytest.mark.parametrize('data',[b'\x00',message()[:-1],message(kind=20,payload=b'\x00'*71)])
def test_truncation_is_not_positive_evidence(data):
    with pytest.raises(ValueError):parse_diag_messages(data,42)


def test_wrong_sequence_and_kernel_errors():
    assert parse_diag_messages(message(seq=43),42)==([],False)
    with pytest.raises(OSError):parse_diag_messages(message(kind=2,payload=struct.pack('=i',-1)),42)
    with pytest.raises(OSError):parse_diag_messages(message(kind=3,payload=struct.pack('=i',-4)),42)


def test_ownership_destination_and_binding_are_all_required():
    row=parse_diag_messages(message(),42)[0][0]
    def check(rows=(row,),**overrides):
        params=dict(owned_inodes={123},remote_ip='203.0.113.7',remote_port=443,interface_index=7)
        return verify_bound_egress(rows,**(params|overrides))
    assert check()['verified']
    assert not check(owned_inodes={124})['verified']
    assert not check(remote_port=444)['verified']
    assert not check(remote_ip='203.0.113.8')['verified']
    assert check((replace(row,interface_index=0),))['reason']=='wan_binding_mismatch'
    assert not check((row,replace(row,interface_index=8)))['verified']


def test_process_change_during_snapshot_rejects_result(monkeypatch):
    monkeypatch.setattr(socket,'if_nametoindex',lambda name:7)
    values=iter(('before','after'))
    result=attest_process_egress(1,process_identity='before',identity_getter=lambda pid:next(values),
        remote_ip='203.0.113.7',remote_port=443,interface_name='wan0',
        snapshot=lambda **kw:parse_diag_messages(message(),42)[0],inodes=lambda pid:{123})
    assert result=={'verified':False,'reason':'process_changed'}


def test_unsupported_kernel_means_unknown(monkeypatch):
    monkeypatch.setattr(socket,'if_nametoindex',lambda name:7)
    def unavailable(**kw):raise OSError('unsupported')
    result=attest_process_egress(1,process_identity='before',identity_getter=lambda pid:'before',
        remote_ip='203.0.113.7',remote_port=443,interface_name='wan0',snapshot=unavailable)
    assert result=={'verified':False,'reason':'egress_unavailable'}


@pytest.mark.skipif(os.name!='posix' or not os.environ.get('XRAY_TEST_BINARY'),reason='Linux and exact Xray required')
@pytest.mark.parametrize('interface,verified',[('lo',True),('bypass-missing0',False)])
def test_real_xray_socket_binding_and_silent_failure(lab,interface,verified):
    if verified and 'microsoft' in platform.release().lower():
        pytest.skip('This WSL host also times out on native SO_BINDTODEVICE lo; positive case requires native Linux')
    port,echo,start,api,connect=lab
    destination=echo(b'A');control=port();incoming=port()
    config=base_config(control,{'managed':incoming},destination)
    config['outbounds'][0]['streamSettings']={'sockopt':{'interface':interface}}
    process=start(config);wait_api(process,api,control)
    client=connect(incoming);exchange(client,b'probe-1',b'A')
    result=attest_process_egress(process.pid,process_identity=process_identity(process.pid),
        identity_getter=process_identity,remote_ip='127.0.0.1',remote_port=destination,interface_name='lo')
    assert result['verified'] is verified
    if not verified:assert result['reason']=='wan_binding_mismatch'
    exchange(client,b'probe-2',b'A')


def test_packet_parser_keeps_only_ipv4_tcp_tuple():
    raw=bytearray(60);raw[0]=0x45;raw[9]=6
    raw[12:16]=socket.inet_aton('192.0.2.1');raw[16:20]=socket.inet_aton('203.0.113.1')
    struct.pack_into('!HH',raw,20,30000,443)
    assert ipv4_tcp_tuple(raw)==('192.0.2.1',30000,'203.0.113.1',443)
    raw[6]=0x20  # First fragment still contains TCP ports.
    assert ipv4_tcp_tuple(raw)
    raw[7]=1
    assert ipv4_tcp_tuple(raw) is None
    raw[7]=0;raw[9]=17
    assert ipv4_tcp_tuple(raw) is None
    assert ipv4_tcp_tuple(b'') is None


def test_interface_packet_must_belong_to_same_process_socket():
    capture=PacketEgressCapture('wan0','203.0.113.1',443)
    flow=('192.0.2.1',30000,'203.0.113.1',443)
    capture.flows.add(flow)
    args=dict(process_identity='identity',identity_getter=lambda pid:'identity')
    assert capture.attest(12,flows_getter=lambda pid:{flow},**args)['verified']
    assert not capture.attest(12,flows_getter=lambda pid:set(),**args)['verified']
    capture.error=True
    assert not capture.attest(12,flows_getter=lambda pid:{flow},**args)['verified']
