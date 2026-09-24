import json
import os
from pathlib import Path
import stat
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import route_probe_runtime as runtime
import pool_probe_runner
from route_quality import RouteIdentity,MeasurementWindow,ProbeReply
from route_profiles import normalize_profile


def profile(direct=False):
    return normalize_profile({'id':'abcdef123456','label':'Проверка','device':'router','destination':'example.com',
        'url':'https://example.com/check','wan':'eth1','protocols':['vless','vless2'],'direct_allowed':direct})


def result(output,code=0):return SimpleNamespace(returncode=code,stdout=output)


def test_resolver_is_bounded_uses_stdin_and_pins_one_public_address():
    called=[]
    def run(args,**kwargs):called.append((args,kwargs));return result('["8.8.8.8","1.1.1.1"]')
    assert runtime.resolve_public_ipv4('example.com',runner=run)=='8.8.8.8'
    args,kwargs=called[0]
    assert 'example.com' not in args and json.loads(kwargs['input'])=='example.com'
    assert kwargs['timeout']==6


def test_system_dns_answer_does_not_contact_fallback_or_hide_private_tail():
    addresses = [f'1.1.1.{i}' for i in range(1, 18)] + ['192.168.1.1']
    result = runtime._resolve_dns_worker('example.com',
        lookup=lambda *args: [(None, None, None, None, (a, 443)) for a in addresses],
        connection=lambda *args, **kwargs: pytest.fail('must keep system DNS authoritative'))
    assert set(result) == set(addresses)


@pytest.mark.parametrize('body,status,valid', [
    ({'Status': 0, 'Answer': [{'type': 1, 'data': '1.1.1.1'}]}, 200, True),
    ({'Status': 3}, 200, False), ({'Status': 0}, 302, False),
    ('x' * 16385, 200, False),
])
def test_encrypted_dns_fallback_is_bounded_verified_and_closed(body,status,valid):
    import socket
    closed = []
    raw = body.encode() if isinstance(body, str) else json.dumps(body).encode()
    def read(size):
        assert size == 16385
        return raw[:size]
    def request(method, path, headers):
        assert method == 'GET' and path == '/dns-query?name=example.com&type=A'
        assert headers['Accept'] == 'application/dns-json'
    def connect(host, *, timeout, context):
        assert host == '1.1.1.1' and timeout == 2 and context.check_hostname
        assert context.verify_mode == runtime.ssl.CERT_REQUIRED
        return SimpleNamespace(request=request, getresponse=lambda: SimpleNamespace(status=status, read=read),
                               close=lambda: closed.append(True))
    def failed(*args):raise socket.gaierror(-2, 'fixture')
    if valid:
        assert runtime._resolve_dns_worker('example.com', lookup=failed, connection=connect) == ['1.1.1.1']
    else:
        with pytest.raises(ValueError):runtime._resolve_dns_worker('example.com', lookup=failed, connection=connect)
    assert closed == [True]


@pytest.mark.parametrize('output',['[]','["127.0.0.1"]','["1.1.1.1","192.168.1.1"]','["::1"]','{}','not json'])
def test_dns_rebinding_and_invalid_answers_fail_closed(output):
    with pytest.raises((ValueError,TypeError)):runtime.resolve_public_ipv4('example.com',runner=lambda *a,**kw:result(output))


def test_pin_preserves_implicit_tls_name_and_does_not_modify_builder(monkeypatch):
    original={'protocol':'vless','tag':'proxy-route-probe','settings':{'vnext':[{'address':'example.com','port':443,'users':[{'id':'test'}]}]},'streamSettings':{'security':'tls','network':'tcp','tlsSettings':{'serverName':''}}}
    monkeypatch.setattr(runtime,'proxy_outbound_from_key',lambda *args:original)
    outbound,address,port=runtime.pinned_outbound('vless','unused','eth1',resolver=lambda host:'1.1.1.1')
    assert address=='1.1.1.1' and port==443
    assert outbound['streamSettings']['tlsSettings']['serverName']=='example.com'
    assert outbound['streamSettings']['sockopt']['interface']=='eth1'
    assert original['settings']['vnext'][0]['address']=='example.com'
    assert 'sockopt' not in original['streamSettings']


def test_unqualified_transport_not_measured(monkeypatch):
    monkeypatch.setattr(runtime,'proxy_outbound_from_key',lambda *args:{'protocol':'vless','streamSettings':{'network':'ws'}})
    with pytest.raises(ValueError,match='unsupported_transport'):runtime.pinned_outbound('vless','unused','eth1')


def test_direct_window_does_not_start_xray_and_requires_egress_evidence(monkeypatch):
    monkeypatch.setattr(runtime.socket,'if_nametoindex',lambda name:2)
    monkeypatch.setattr(runtime.time,'sleep',lambda value:None)
    monkeypatch.setattr(runtime,'start_pool_probe_xray',lambda config:pytest.fail('direct must not start Xray'))
    for verified in (True,False):
        w=runtime._candidate_window(profile(True),'direct','',3,'1.1.1.1',deadline=time.monotonic()+100,
            still_current=lambda:True,resource_guard=lambda:True,sample=lambda *args,**kw:(12,verified))
        assert w.sent==20 and len(w.replies)==20 and w.wan_verified is verified
        assert w.identity.device.endswith('-router-origin')


def test_manual_change_cancels_window(monkeypatch):
    monkeypatch.setattr(runtime.socket,'if_nametoindex',lambda name:2)
    with pytest.raises(runtime.DiagnosticCancelled,match='generation_changed'):
        runtime._candidate_window(profile(True),'direct','',3,'1.1.1.1',deadline=time.monotonic()+100,
            still_current=lambda:False,resource_guard=lambda:True,sample=lambda *a,**kw:pytest.fail('stale probe'))


def test_resource_budget_cancels_before_network(monkeypatch):
    with pytest.raises(runtime.DiagnosticCancelled,match='busy'):
        runtime.measure_profile(profile(),{},generation=1,still_current=lambda:True,resource_guard=lambda:False,
            resolver=lambda host:pytest.fail('must not resolve under pressure'))


def test_proxy_required_never_tests_direct(monkeypatch):
    called=[]
    def candidate(p,protocol,key,generation,target,**kwargs):
        called.append(protocol)
        identity=RouteIdentity('router','example.com','eth1',protocol,'key','tcp','endpoint','https',generation)
        now=time.time()
        return MeasurementWindow(identity,now-1,now,20,5000,tuple(ProbeReply(i,20) for i in range(20)),True,False,True)
    monkeypatch.setattr(runtime,'_candidate_window',candidate)
    result=runtime.measure_profile(profile(),{'vless':'one','vless2':'two'},generation=3,
        still_current=lambda:True,resource_guard=lambda:True,resolver=lambda host:'1.1.1.1')
    assert called==['vless','vless2']
    assert result['origin']=='router' and result['automatic_apply'] is False
    assert result['udp_latency_ms'] is None and result['udp_loss'] is None


def test_probe_config_private_and_removed_on_spawn_failure(monkeypatch,tmp_path):
    original=pool_probe_runner.tempfile.mkstemp
    seen=[]
    def temp(**kwargs):
        kwargs['dir']=tmp_path
        fd,path=original(**kwargs);seen.append(Path(path));return fd,path
    def fail(*args,**kwargs):
        assert seen[0].exists()
        if os.name=='posix':assert stat.S_IMODE(seen[0].stat().st_mode)==0o600
        raise OSError('spawn failed')
    monkeypatch.setattr(pool_probe_runner.tempfile,'mkstemp',temp)
    monkeypatch.setattr(pool_probe_runner.subprocess,'Popen',fail)
    with pytest.raises(OSError):pool_probe_runner.start_pool_probe_xray({'test':'no secrets'})
    assert not seen[0].exists()
