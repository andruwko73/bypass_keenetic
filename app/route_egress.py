"""Read-only Linux socket evidence for a *specific* proxy process and WAN.

Xray 26.2.6 logs some socket-option errors and continues dialing. Configuration
alone therefore cannot attest SO_BINDTODEVICE. inet_diag exposes idiag_if; an
unsupported kernel or an unbound/mismatched socket gives unknown, not success.
"""
from dataclasses import dataclass
import ipaddress
import os
from pathlib import Path
import socket
import struct
import threading
import time


@dataclass(frozen=True)
class SocketEvidence:
    family: int
    state: int
    source_ip: str
    source_port: int
    destination_ip: str
    destination_port: int
    interface_index: int
    inode: int


def parse_diag_messages(data, sequence):
    """Parse bounded kernel messages, rejecting incomplete/error responses."""
    records=[];done=False;offset=0
    if not isinstance(data, bytes) or len(data)>65536:
        raise ValueError('Invalid socket diagnostic response')
    while offset<len(data):
        if len(data)-offset<16:raise ValueError('Truncated netlink header')
        size,kind,flags,seq,pid=struct.unpack_from('=IHHII',data,offset)
        if size<16 or offset+size>len(data):raise ValueError('Truncated netlink message')
        payload=data[offset+16:offset+size]
        offset+=(size+3)&~3
        if seq!=sequence:continue
        if flags & 0x10:raise OSError('Interrupted socket diagnostic dump')
        if kind==3:
            if payload and (len(payload)<4 or struct.unpack_from('=i',payload)[0]):
                raise OSError('Socket diagnostic dump failed')
            done=True;continue
        if kind==2:
            if len(payload)<4 or struct.unpack_from('=i',payload)[0]:
                raise OSError('Socket diagnostic request failed')
            continue
        if kind!=20:continue
        if len(payload)<72:raise ValueError('Truncated inet_diag message')
        family,state=payload[:2]
        if family not in (socket.AF_INET,socket.AF_INET6):continue
        count=4 if family==socket.AF_INET else 16
        records.append(SocketEvidence(family,state,
            str(ipaddress.ip_address(payload[8:8+count])),struct.unpack_from('!H',payload,4)[0],
            str(ipaddress.ip_address(payload[24:24+count])),struct.unpack_from('!H',payload,6)[0],
            struct.unpack_from('=I',payload,40)[0],struct.unpack_from('=I',payload,68)[0]))
    return records,done


def tcp_socket_snapshot(*, family=socket.AF_INET, timeout=1.0, socket_factory=socket.socket):
    if os.name!='posix' or not hasattr(socket,'AF_NETLINK'):
        raise OSError('Kernel socket diagnostics unavailable')
    if family not in (socket.AF_INET,socket.AF_INET6) or not .1<=timeout<=3:
        raise ValueError('Invalid socket diagnostic request')
    sequence=time.monotonic_ns() & 0xffffffff
    # inet_diag_req_v2: established TCP sockets; all addresses/ports.
    request=struct.pack('=BBBBI',family,socket.IPPROTO_TCP,0,0,1<<1)+bytes(40)+b'\xff'*8
    header=struct.pack('=IHHII',16+len(request),20,0x301,sequence,0)
    deadline=time.monotonic()+timeout;records=[]
    with socket_factory(socket.AF_NETLINK,socket.SOCK_RAW,4) as client:
        client.bind((0,0));client.sendto(header+request,(0,0))
        for _ in range(128):
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Socket diagnostic deadline')
            client.settimeout(remaining)
            data,ancillary,flags,address=client.recvmsg(65536)
            if address[0]!=0 or flags & socket.MSG_TRUNC:
                raise OSError('Untrusted or truncated socket diagnostic response')
            batch,done=parse_diag_messages(data,sequence);records.extend(batch)
            if len(records)>8192:raise OSError('Socket diagnostic budget exceeded')
            if done:return records
    raise OSError('Socket diagnostic message budget exceeded')


def process_socket_inodes(pid, *, proc_root='/proc'):
    if type(pid) is not int or pid<=0:raise ValueError('Invalid process')
    inodes=set()
    for index,path in enumerate((Path(proc_root)/str(pid)/'fd').iterdir()):
        if index>=4096:raise OSError('Process descriptor budget exceeded')
        try:target=os.readlink(path)
        except FileNotFoundError:continue
        if target.startswith('socket:[') and target.endswith(']'):
            try:inodes.add(int(target[8:-1]))
            except ValueError:continue
    return inodes


def verify_bound_egress(records, *, owned_inodes, remote_ip, remote_port, interface_index):
    remote=str(ipaddress.ip_address(remote_ip))
    if type(remote_port) is not int or not 1<=remote_port<=65535 or type(interface_index) is not int or interface_index<=0:
        raise ValueError('Invalid expected egress')
    matched=[record for record in records if record.state==1 and record.inode in owned_inodes
             and record.destination_ip==remote and record.destination_port==remote_port]
    if not matched:return {'verified':False,'reason':'socket_not_observed'}
    if any(record.interface_index!=interface_index for record in matched):
        return {'verified':False,'reason':'wan_binding_mismatch'}
    return {'verified':True,'reason':'kernel_socket_binding'}


def attest_process_egress(pid, *, process_identity, identity_getter, remote_ip, remote_port,
                          interface_name, snapshot=tcp_socket_snapshot, inodes=process_socket_inodes):
    """Call while probe traffic is flowing; do not infer evidence after exit."""
    try:
        if not process_identity or identity_getter(pid)!=process_identity:
            return {'verified':False,'reason':'process_changed'}
        index=socket.if_nametoindex(interface_name)
        address=ipaddress.ip_address(remote_ip)
        records=snapshot(family=socket.AF_INET if address.version==4 else socket.AF_INET6)
        result=verify_bound_egress(records,owned_inodes=inodes(pid),remote_ip=remote_ip,
                                   remote_port=remote_port,interface_index=index)
        if identity_getter(pid)!=process_identity:return {'verified':False,'reason':'process_changed'}
        return result
    except (OSError,ValueError,TimeoutError):
        return {'verified':False,'reason':'egress_unavailable'}


def ipv4_tcp_tuple(header):
    """Extract only a 4-tuple; never retain packet contents."""
    if len(header)<24 or header[0]>>4!=4 or header[9]!=6:return None
    offset=(header[0]&15)*4
    if offset<20 or len(header)<offset+4 or struct.unpack_from('!H',header,6)[0]&0x1fff:return None
    source=socket.inet_ntoa(header[12:16]);destination=socket.inet_ntoa(header[16:20])
    sport,dport=struct.unpack_from('!HH',header,offset)
    return source,sport,destination,dport


def process_tcp_flows(pid, *, proc_root='/proc'):
    owned=process_socket_inodes(pid,proc_root=proc_root);flows=set()
    with (Path(proc_root)/str(pid)/'net'/'tcp').open() as stream:
        for index,line in enumerate(stream):
            if index>8192:raise OSError('Socket table budget exceeded')
            fields=line.split()
            if len(fields)<10 or fields[3]!='01':continue
            if int(fields[9]) not in owned:continue
            def address(value):
                ip,port=value.split(':')
                return socket.inet_ntoa(struct.pack('=I',int(ip,16))),int(port,16)
            source,sport=address(fields[1]);target,dport=address(fields[2])
            flows.add((source,sport,target,dport))
    return flows


class PacketEgressCapture:
    """Fallback for kernels without inet_diag, bounded to 3 s / 2048 headers.

    No promiscuous mode, payload storage, pcap file, network rules or new daemon.
    Match an outgoing interface observation to a still-owned established socket.
    Only IPv4 TCP is admitted here; other transports remain unverified.
    """
    def __init__(self, interface_name, remote_ip, remote_port, *, duration=3.0):
        address=ipaddress.ip_address(remote_ip)
        if address.version!=4 or type(remote_port) is not int or not 1<=remote_port<=65535:
            raise ValueError('Unsupported packet evidence target')
        if not .1<=duration<=3:raise ValueError('Invalid capture budget')
        self.interface_name,self.remote_ip,self.remote_port=interface_name,str(address),remote_port
        self.duration=duration;self.flows=set();self.error=False
        self.headers_seen=0;self.outgoing_headers=0
        self._stop=threading.Event();self._thread=None;self._socket=None

    def __enter__(self):
        client=None
        try:
            socket.if_nametoindex(self.interface_name)
            # Linux's outgoing packet tap is on ETH_P_ALL, not the protocol-
            # specific receive hook. Parse/reject non-IPv4 headers ourselves.
            client=socket.socket(socket.AF_PACKET,socket.SOCK_DGRAM,socket.htons(0x0003))
            client.bind((self.interface_name,0));client.settimeout(.1)
            client.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,65536)
            self._socket=client
            self._thread=threading.Thread(target=self._collect,name='route-egress-headers',daemon=True)
            self._thread.start()
        except (OSError,ValueError,AttributeError):
            self.error=True
            if client:client.close()
        return self

    def _collect(self):
        until=time.monotonic()+self.duration
        try:
            for _ in range(2048):
                if self._stop.is_set() or time.monotonic()>=until:return
                try:header,address=self._socket.recvfrom(96)
                except socket.timeout:continue
                self.headers_seen+=1
                if address[0]!=self.interface_name or address[1]!=0x0800 or address[2]!=4:continue
                self.outgoing_headers+=1
                flow=ipv4_tcp_tuple(header)
                if flow and flow[2:]==(self.remote_ip,self.remote_port):
                    self.flows.add(flow)
                    if len(self.flows)>32:self.error=True;return
            self.error=True
        except OSError:self.error=True

    def __exit__(self,*args):
        self._stop.set()
        if self._thread:self._thread.join(timeout=1)
        if self._thread and self._thread.is_alive():self.error=True
        if self._socket:self._socket.close()

    def attest(self,pid,*,process_identity,identity_getter,flows_getter=process_tcp_flows):
        if self.error:return {'verified':False,'reason':'egress_unavailable'}
        try:
            if not process_identity or identity_getter(pid)!=process_identity:
                return {'verified':False,'reason':'process_changed'}
            owned=flows_getter(pid)
            # Snapshot after joining the collector so set iteration cannot race.
            self.__exit__()
            observed=bool(owned.intersection(self.flows))
            if identity_getter(pid)!=process_identity:return {'verified':False,'reason':'process_changed'}
            return {'verified':observed and not self.error,'reason':'interface_packet_and_owned_socket' if observed and not self.error else 'socket_not_observed'}
        except (OSError,ValueError):return {'verified':False,'reason':'egress_unavailable'}
