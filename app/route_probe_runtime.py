"""One bounded diagnostic job, called under the existing probe scheduler.

It never applies keys or routes. HTTPS response time is measured from the
router to one fixed destination IP; it is not device/game/UDP latency.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import sys
import time
from urllib.parse import urlsplit

from pool_probe_runner import start_pool_probe_xray, stop_pool_probe_xray
from proxy_apply_coordinator import process_identity
from proxy_config_builder import socks_inbound, xray_base_config
from proxy_protocols import proxy_outbound_from_key
from route_egress import PacketEgressCapture, attest_process_egress, process_socket_inodes
from route_profiles import normalize_profile
from route_quality import RouteIdentity, ProbeReply, MeasurementWindow, window_metrics, recommend
from xray_live_apply import qualify_outbound


class DiagnosticCancelled(RuntimeError):
    pass


def _resolve_dns_worker(host, *, lookup=socket.getaddrinfo, connection=None):
    """OS DNS first; encrypted fallback only when OS resolution fails.

    Runs inside the six-second child deadline. The fallback changes no router
    settings and is not used as WAN or latency evidence.
    """
    try:
        addresses = sorted({r[4][0] for r in lookup(host, 443, socket.AF_INET, socket.SOCK_STREAM)})
    except socket.gaierror:
        addresses = []
    if addresses:
        return addresses
    import http.client
    from urllib.parse import urlencode
    factory = connection or http.client.HTTPSConnection
    client = factory('1.1.1.1', timeout=2, context=ssl.create_default_context())
    try:
        client.request('GET', '/dns-query?' + urlencode({'name': host, 'type': 'A'}),
                       headers={'Accept': 'application/dns-json'})
        response = client.getresponse()
        body = response.read(16385)
        if response.status != 200 or len(body) > 16384:
            raise ValueError('dns_unavailable')
        data = json.loads(body)
        if not isinstance(data, dict) or data.get('Status') != 0:
            raise ValueError('dns_unavailable')
        answer = data.get('Answer', [])
        if not isinstance(answer, list) or len(answer) > 64:
            raise ValueError('dns_unavailable')
        # Keep all returned A records for the parent's mixed-private check.
        return sorted({item['data'] for item in answer if isinstance(item, dict) and item.get('type') == 1})
    finally:
        client.close()


def resolve_public_ipv4(host, *, runner=subprocess.run):
    """Bound OS resolver lifetime without an abandoned resolver thread."""
    code='import json,sys; from route_probe_runtime import _resolve_dns_worker; print(json.dumps(_resolve_dns_worker(json.load(sys.stdin))))'
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent) + os.pathsep + os.environ.get('PYTHONPATH', ''))
    result=runner([sys.executable,'-B','-c',code],input=json.dumps(host),text=True,
                  stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=6,check=False,env=environment)
    if result.returncode or len(result.stdout)>4096:raise ValueError('dns_unavailable')
    addresses=json.loads(result.stdout)
    if not addresses or not isinstance(addresses,list) or len(addresses)>16:raise ValueError('dns_unavailable')
    # Reject the whole answer on mixed public/private DNS, and pin the selected
    # address in both direct and proxied requests (no second DNS resolution).
    if any(ipaddress.ip_address(value).version!=4 or not ipaddress.ip_address(value).is_global for value in addresses):
        raise ValueError('non_public_destination')
    return addresses[0]


def pinned_outbound(protocol,key,interface_name,*,resolver=resolve_public_ipv4):
    outbound=deepcopy(proxy_outbound_from_key(protocol,key,'proxy-route-probe'))
    if not qualify_outbound(outbound):raise ValueError('unsupported_transport')
    settings=outbound.get('settings',{})
    peers=settings.get('vnext',settings.get('servers',[]))
    if len(peers)!=1:raise ValueError('unsupported_transport')
    host=peers[0]['address'];address=resolver(host);port=int(peers[0]['port'])
    peers[0]['address']=address
    stream=outbound.setdefault('streamSettings',{})
    if stream.get('security') in ('tls','reality'):
        tls=stream.setdefault(stream['security']+'Settings',{})
        if not tls.get('serverName'):tls['serverName']=host
    stream.setdefault('sockopt',{})['interface']=interface_name
    return outbound,address,port


def _receive(sock,count,deadline):
    result=b''
    while len(result)<count:
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('sample_deadline')
        sock.settimeout(remaining)
        part=sock.recv(count-len(result))
        if not part:raise OSError('closed')
        result+=part
    return result


def https_sample(host,path,target_ip,*,socks_port=None,interface_name='',context=None,on_live=None):
    """Fixed IPv4 target, verified TLS, HEAD without redirects, 16 KiB headers."""
    start=time.monotonic();deadline=start+5
    raw=socket.socket();stream=None
    def remaining():
        value=deadline-time.monotonic()
        if value<=0:raise TimeoutError('sample_deadline')
        return value
    try:
        raw.settimeout(remaining())
        if socks_port is None:
            raw.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,interface_name.encode()+b'\0')
            raw.connect((target_ip,443))
        else:
            raw.connect(('127.0.0.1',socks_port));raw.sendall(b'\x05\x01\x00')
            if _receive(raw,2,deadline)!=b'\x05\x00':raise OSError('socks_rejected')
            raw.sendall(b'\x05\x01\x00\x01'+socket.inet_aton(target_ip)+struct.pack('!H',443))
            header=_receive(raw,4,deadline)
            if header[0]!=5 or header[1]!=0:raise OSError('socks_rejected')
            if header[3]==1:_receive(raw,6,deadline)
            elif header[3]==4:_receive(raw,18,deadline)
            elif header[3]==3:_receive(raw,_receive(raw,1,deadline)[0]+2,deadline)
            else:raise OSError('socks_rejected')
        raw.settimeout(remaining())
        stream=(context or ssl.create_default_context()).wrap_socket(raw,server_hostname=host)
        stream.settimeout(remaining())
        stream.sendall(('HEAD '+path+' HTTP/1.1\r\nHost: '+host+'\r\nConnection: keep-alive\r\nUser-Agent: Bypass-Route-Check/1\r\n\r\n').encode('ascii'))
        response=b''
        while b'\r\n\r\n' not in response:
            stream.settimeout(remaining());part=stream.recv(min(1024,16384-len(response)))
            if not part or len(response)+len(part)>=16384:raise OSError('invalid_headers')
            response+=part
        first=response.split(b'\r\n',1)[0].split()
        if len(first)<2 or not first[0].startswith(b'HTTP/1.') or not first[1].isdigit():raise OSError('invalid_headers')
        status=int(first[1]);elapsed=(time.monotonic()-start)*1000
        if not 200<=status<400:raise OSError('http_unavailable')
        evidence=False
        if socks_port is None:
            evidence=stream.getsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,64).rstrip(b'\0').decode()==interface_name
        elif on_live is not None:evidence=on_live()
        return elapsed,bool(evidence)
    finally:
        if stream is not None:stream.close()
        raw.close()


def _owns_listener(process,port):
    owned=process_socket_inodes(process.pid)
    with Path('/proc',str(process.pid),'net','tcp').open() as file:
        for index,line in enumerate(file):
            if index>8192:return False
            fields=line.split()
            if len(fields)>9 and fields[3]=='0A' and int(fields[1].split(':')[1],16)==port and int(fields[9]) in owned:return True
    return False


def _candidate_window(profile,protocol,key,generation,target,*,deadline,still_current,resource_guard,
                       resolver=resolve_public_ipv4,sample=https_sample,count=20):
    process=None;config_path=None;port=None;capture=None;wan_ok=False;replies=[];sent=0
    started=time.time();peer=None;identity=None
    interface_index=socket.if_nametoindex(profile['wan'])
    context=ssl.create_default_context();parsed=urlsplit(profile['url'])
    try:
        if protocol!='direct':
            outbound,peer,peer_port=pinned_outbound(protocol,key,profile['wan'],resolver=resolver)
            with socket.socket() as reserve:
                reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
            config=xray_base_config(error_log_path='/dev/null')
            config['inbounds']=[socks_inbound(port,'in-route-probe')]
            config['outbounds']=[outbound,{'tag':'blocked','protocol':'blackhole'}]
            config['routing']['rules']=[{'type':'field','inboundTag':['in-route-probe'],'outboundTag':'proxy-route-probe'}]
            process,config_path=start_pool_probe_xray(config)
            until=min(deadline,time.monotonic()+4)
            while time.monotonic()<until and process.poll() is None:
                if _owns_listener(process,port):break
                time.sleep(.05)
            else:raise OSError('probe_start_failed')
            identity=process_identity(process.pid)
        for sequence in range(count):
            if not still_current():raise DiagnosticCancelled('generation_changed')
            if not resource_guard():raise DiagnosticCancelled('resource_guard')
            if socket.if_nametoindex(profile['wan'])!=interface_index:raise DiagnosticCancelled('wan_changed')
            if process and (process.poll() is not None or process_identity(process.pid)!=identity):raise DiagnosticCancelled('process_changed')
            if deadline-time.monotonic()<6:break
            capture=None
            try:
                if process and not wan_ok:
                    capture=PacketEgressCapture(profile['wan'],peer,peer_port).__enter__()
                def attest():
                    evidence=attest_process_egress(process.pid,process_identity=identity,identity_getter=process_identity,
                        remote_ip=peer,remote_port=peer_port,interface_name=profile['wan'])
                    if evidence['verified']:return True
                    return bool(capture and capture.attest(process.pid,process_identity=identity,identity_getter=process_identity)['verified'])
                sent+=1
                elapsed,verified=sample(parsed.hostname,parsed.path or '/',target,socks_port=port,
                    interface_name=profile['wan'],context=context,on_live=attest if process else None)
                if elapsed<=5000:replies.append(ProbeReply(sequence,elapsed))
                wan_ok=wan_ok or verified
            except (OSError,ValueError,TimeoutError):pass
            finally:
                if capture:capture.__exit__()
            time.sleep(.15)
        if not still_current():raise DiagnosticCancelled('generation_changed')
        if not sent:raise DiagnosticCancelled('job_deadline')
        scope=RouteIdentity(profile['id']+'-router-origin',profile['destination'],profile['wan'],protocol,
            hashlib.sha256(key.encode()).hexdigest()[:16] if key else 'none','tcp',
            hashlib.sha256((profile['url']+'|'+target+'|HEAD').encode()).hexdigest()[:24],'https',generation)
        return MeasurementWindow(scope,started,time.time(),sent,5000,tuple(replies),wan_ok,False,True)
    finally:
        if process or config_path:stop_pool_probe_xray(process,config_path)


def measure_profile(profile,keys,*,generation,still_current,resource_guard,resolver=resolve_public_ipv4):
    profile=normalize_profile(profile)
    if not still_current() or not resource_guard():raise DiagnosticCancelled('busy')
    deadline=time.monotonic()+150
    target=resolver(urlsplit(profile['url']).hostname)
    windows=[];unavailable=[]
    candidates=(['direct'] if profile['direct_allowed'] else [])+profile['protocols']
    # Interleave windows on subsequent user runs by storing no permanent winner.
    for protocol in candidates:
        if not still_current():raise DiagnosticCancelled('generation_changed')
        if protocol!='direct' and not keys.get(protocol):
            unavailable.append({'protocol':protocol,'reason':'no_active_key'});continue
        try:
            windows.append(_candidate_window(profile,protocol,keys.get(protocol,''),generation,target,
                deadline=deadline,still_current=still_current,resource_guard=resource_guard,resolver=resolver))
        except DiagnosticCancelled:raise
        except (OSError,ValueError,KeyError,TypeError):
            unavailable.append({'protocol':protocol,'reason':'candidate_unavailable'})
    now=time.time()
    decision=recommend(windows,now=now,direct_allowed=profile['direct_allowed'],required_kind='https',
        expected_generations={(w.identity.protocol,w.identity.key_id,w.identity.wan):generation for w in windows})
    winner=decision['recommended']
    return {'schema':1,'profile_id':profile['id'],'checked_at':now,'generation':generation,
            'origin':'router','measurement':'https_head_same_ipv4','automatic_apply':False,
            'recommended_protocol':winner.protocol if winner else '',
            'reason':decision['reason'],'windows':[{'identity':asdict(w.identity),'metrics':window_metrics(w,now=now)} for w in windows],
            'unavailable':unavailable,'udp_latency_ms':None,'udp_loss':None}
