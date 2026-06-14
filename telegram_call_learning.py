import ipaddress
import re
import subprocess
import time


TELEGRAM_CALL_PORTS = {
    '3478',
    '3479',
    '3480',
    '3481',
    '3482',
    '3483',
    '3484',
    '3485',
    '3486',
    '3487',
    '3488',
    '3489',
    '3490',
    '3491',
    '3492',
    '3493',
    '3494',
    '3495',
    '3496',
    '3497',
}
TELEGRAM_SIGNAL_PORTS = TELEGRAM_CALL_PORTS | {'80', '88', '443', '5222'}
TELEGRAM_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        '91.108.0.0/16',
        '149.154.160.0/20',
        '95.161.64.0/20',
    )
)

PROTOCOL_IPSETS = {
    'shadowsocks': ('unblocksh', 'unblockshudp'),
    'vmess': ('unblockvmess', 'unblockvmessudp'),
    'vless': ('unblockvless', 'unblockvlessudp'),
    'vless2': ('unblockvless2', 'unblockvless2udp'),
    'trojan': ('unblocktroj', 'unblocktrojudp'),
}

CALL_LEARNED_IPSETS = {
    'shadowsocks': 'bypass_tg_call_sh',
    'vmess': 'bypass_tg_call_vmess',
    'vless': 'bypass_tg_call_vless',
    'vless2': 'bypass_tg_call_vless2',
    'trojan': 'bypass_tg_call_troj',
}

NOISE_UDP_PORTS = {
    '53',
    '67',
    '68',
    '123',
    '137',
    '138',
    '1900',
    '5353',
}
UDP_CLUSTER_EXCLUDED_PORTS = NOISE_UDP_PORTS | {'80', '88', '443', '5222'}
UDP_CALL_CLUSTER_MIN_FLOWS = 2
UDP_CALL_CLUSTER_MAX_FLOWS = 8
UDP_CALL_CLUSTER_MIN_PACKETS = 8
UDP_CALL_CLUSTER_MIN_BYTES = 1600
ACTIVE_UDP_MEDIA_MIN_PACKETS = 40
ACTIVE_UDP_MEDIA_MIN_BYTES = 8000


def protocol_ipsets(protocol):
    return PROTOCOL_IPSETS.get(str(protocol or '').strip().lower(), ())


def protocol_call_ipset(protocol):
    return CALL_LEARNED_IPSETS.get(str(protocol or '').strip().lower(), '')


def is_public_ipv4(value):
    try:
        address = ipaddress.ip_address(str(value or '').strip())
    except ValueError:
        return False
    if address.version != 4:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def is_lan_ipv4(value):
    try:
        address = ipaddress.ip_address(str(value or '').strip())
    except ValueError:
        return False
    return (
        address.version == 4
        and (address.is_private or address.is_link_local)
        and not address.is_loopback
        and not address.is_multicast
        and not address.is_unspecified
    )


def address_in_networks(value, networks=TELEGRAM_NETWORKS):
    try:
        address = ipaddress.ip_address(str(value or '').strip())
    except ValueError:
        return False
    return any(address in network for network in networks)


def _first_value(fields, name):
    for field_name, value in fields:
        if field_name == name:
            return value
    return ''


def _conntrack_tuples(fields):
    tuples = []
    field_count = len(fields or [])
    for index in range(0, max(0, field_count - 3)):
        group = fields[index:index + 4]
        if [name for name, _value in group] != ['src', 'dst', 'sport', 'dport']:
            continue
        tuples.append({name: value for name, value in group})
    return tuples


def _packets_bytes(line):
    packets = 0
    byte_count = 0
    try:
        for value in re.findall(r'\bpackets=(\d+)', line or ''):
            packets += int(value)
        for value in re.findall(r'\bbytes=(\d+)', line or ''):
            byte_count += int(value)
    except Exception:
        return 0, 0
    return packets, byte_count


def _select_lan_udp_tuple(fields, device_ip=''):
    selected = None
    for item in _conntrack_tuples(fields):
        src = item.get('src') or ''
        dst = item.get('dst') or ''
        sport = item.get('sport') or ''
        dport = item.get('dport') or ''
        if device_ip and src != str(device_ip):
            continue
        if sport in NOISE_UDP_PORTS or dport in NOISE_UDP_PORTS:
            continue
        if not is_public_ipv4(dst):
            continue
        if selected is None:
            selected = item
        if is_lan_ipv4(src):
            return item
    return selected


def parse_udp_flow(line, device_ip=''):
    text = str(line or '')
    if ' udp ' not in text and not text.startswith('udp '):
        return None
    if 'TIME_WAIT' in text or 'CLOSE' in text:
        return None
    fields = re.findall(r'\b(src|dst|sport|dport)=([^ ]+)', text)
    if len(fields) < 4:
        return None
    selected = _select_lan_udp_tuple(fields, device_ip=device_ip)
    if not selected:
        return None
    src = selected.get('src') or ''
    dst = selected.get('dst') or ''
    sport = selected.get('sport') or ''
    dport = selected.get('dport') or ''
    if not src or not dst or not sport or not dport:
        return None
    packets, byte_count = _packets_bytes(text)
    identity = '|'.join((src, dst, sport, dport, 'udp'))
    return {
        'identity': identity,
        'protocol': 'udp',
        'src': src,
        'dst': dst,
        'sport': sport,
        'dport': dport,
        'packets': packets,
        'bytes': byte_count,
        'assured': 'ASSURED' in text,
        'raw': text.strip(),
    }


def flow_matches_telegram_call(flow):
    if not flow:
        return False
    dport = str(flow.get('dport') or '')
    dst = str(flow.get('dst') or '')
    return dport in TELEGRAM_SIGNAL_PORTS and address_in_networks(dst)


def telegram_signal_clients_from_lines(lines, router_ip='', allowed_sources=None):
    allowed_sources = {str(item or '').strip() for item in (allowed_sources or []) if str(item or '').strip()}
    allowed_source_tokens = tuple(f'src={item}' for item in allowed_sources)
    excluded_sources = {str(router_ip or '').strip()} if str(router_ip or '').strip() else set()
    clients = set()
    for line in lines or []:
        text = str(line or '')
        if allowed_source_tokens and not any(token in text for token in allowed_source_tokens):
            continue
        if ' tcp ' not in text and ' udp ' not in text and not text.startswith(('tcp ', 'udp ')):
            continue
        fields = re.findall(r'\b(src|dst|sport|dport)=([^ ]+)', text)
        for item in _conntrack_tuples(fields):
            src = item.get('src') or ''
            dst = item.get('dst') or ''
            dport = item.get('dport') or ''
            if not is_lan_ipv4(src):
                continue
            if src in excluded_sources:
                continue
            if allowed_sources and src not in allowed_sources:
                continue
            if dport not in TELEGRAM_SIGNAL_PORTS:
                continue
            if address_in_networks(dst):
                clients.add(src)
    return clients


def _udp_cluster_key(flow):
    return (str(flow.get('src') or ''), str(flow.get('sport') or ''))


def _udp_cluster_member(flow):
    if not flow:
        return False
    if not flow.get('assured'):
        return False
    dport = str(flow.get('dport') or '')
    if dport in UDP_CLUSTER_EXCLUDED_PORTS:
        return False
    try:
        sport = int(str(flow.get('sport') or '0'))
        remote_port = int(dport or '0')
    except ValueError:
        return False
    return sport >= 1024 and remote_port >= 1024


def _udp_call_cluster_stats(flows):
    clusters = {}
    for flow in flows or []:
        if not _udp_cluster_member(flow):
            continue
        key = _udp_cluster_key(flow)
        stats = clusters.setdefault(key, {
            'flow_count': 0,
            'telegram_flow_count': 0,
            'addresses': set(),
            'telegram_addresses': set(),
            'packets': 0,
            'bytes': 0,
        })
        stats['flow_count'] += 1
        stats['addresses'].add(str(flow.get('dst') or ''))
        if address_in_networks(flow.get('dst')):
            stats['telegram_flow_count'] += 1
            stats['telegram_addresses'].add(str(flow.get('dst') or ''))
        try:
            stats['packets'] += int(flow.get('packets') or 0)
            stats['bytes'] += int(flow.get('bytes') or 0)
        except Exception:
            pass
    return clusters


def flow_matches_udp_call_cluster(flow, cluster_stats, telegram_clients):
    if not _udp_cluster_member(flow):
        return False
    src = str(flow.get('src') or '')
    if src not in set(telegram_clients or ()):
        return False
    stats = cluster_stats.get(_udp_cluster_key(flow), {}) if cluster_stats else {}
    flow_count = int(stats.get('flow_count') or 0)
    address_count = len(stats.get('addresses') or ())
    telegram_flow_count = int(stats.get('telegram_flow_count') or 0)
    if flow_count < UDP_CALL_CLUSTER_MIN_FLOWS or flow_count > UDP_CALL_CLUSTER_MAX_FLOWS:
        return False
    if address_count < UDP_CALL_CLUSTER_MIN_FLOWS or address_count > UDP_CALL_CLUSTER_MAX_FLOWS:
        return False
    if telegram_flow_count < 1:
        return False
    packets = int(stats.get('packets') or 0)
    byte_count = int(stats.get('bytes') or 0)
    return packets >= UDP_CALL_CLUSTER_MIN_PACKETS or byte_count >= UDP_CALL_CLUSTER_MIN_BYTES


def flow_matches_active_udp_media(flow, telegram_clients):
    if not _udp_cluster_member(flow):
        return False
    src = str(flow.get('src') or '')
    if src not in set(telegram_clients or ()):
        return False
    try:
        packets = int(flow.get('packets') or 0)
        byte_count = int(flow.get('bytes') or 0)
    except Exception:
        return False
    return packets >= ACTIVE_UDP_MEDIA_MIN_PACKETS or byte_count >= ACTIVE_UDP_MEDIA_MIN_BYTES


def read_conntrack_flows(device_ip, conntrack_path='/proc/net/nf_conntrack', now=None):
    timestamp = time.time() if now is None else float(now)
    flows = {}
    try:
        with open(conntrack_path, 'r', encoding='utf-8', errors='ignore') as file:
            lines = file.readlines()
    except Exception:
        return flows
    for line in lines:
        flow = parse_udp_flow(line, device_ip=device_ip)
        if not flow:
            continue
        flow['seen_at'] = timestamp
        flows[flow['identity']] = flow
    return flows


def read_lan_conntrack_flows(
    router_ip='',
    conntrack_path='/proc/net/nf_conntrack',
    now=None,
    allowed_sources=None,
):
    timestamp = time.time() if now is None else float(now)
    allowed_sources = {str(item or '').strip() for item in (allowed_sources or []) if str(item or '').strip()}
    excluded_sources = {str(router_ip or '').strip()} if str(router_ip or '').strip() else set()
    flows = {}
    try:
        with open(conntrack_path, 'r', encoding='utf-8', errors='ignore') as file:
            lines = file.readlines()
    except Exception:
        return flows
    all_flows = []
    allowed_source_tokens = tuple(f'src={item}' for item in allowed_sources)
    for line in lines:
        if allowed_source_tokens and not any(token in line for token in allowed_source_tokens):
            continue
        flow = parse_udp_flow(line)
        if not flow:
            continue
        src = str(flow.get('src') or '')
        if not is_lan_ipv4(src):
            continue
        if src in excluded_sources:
            continue
        if allowed_sources and src not in allowed_sources:
            continue
        all_flows.append(flow)

    telegram_clients = telegram_signal_clients_from_lines(
        lines,
        router_ip=router_ip,
        allowed_sources=allowed_sources,
    )
    telegram_clients.update(allowed_sources)
    cluster_stats = _udp_call_cluster_stats(all_flows)
    for flow in all_flows:
        strict_match = flow_matches_telegram_call(flow)
        cluster_match = flow_matches_udp_call_cluster(flow, cluster_stats, telegram_clients)
        active_media_match = flow_matches_active_udp_media(flow, telegram_clients)
        if not strict_match and not cluster_match and not active_media_match:
            continue
        if cluster_match or active_media_match:
            flow = dict(flow)
            stats = cluster_stats.get(_udp_cluster_key(flow), {})
            flow.update({
                'telegram_signal_client': True,
                'udp_call_cluster': bool(cluster_match),
                'udp_call_active_media': bool(active_media_match),
                'cluster_flow_count': int(stats.get('flow_count') or 0),
                'cluster_address_count': len(stats.get('addresses') or ()),
                'cluster_telegram_flow_count': int(stats.get('telegram_flow_count') or 0),
            })
        flow['seen_at'] = timestamp
        flows[flow['identity']] = flow
    return flows


def candidate_score(flow, previous=None, min_packets=2, min_bytes=240):
    previous = previous or {}
    try:
        packet_delta = int(flow.get('packets') or 0) - int(previous.get('packets') or 0)
    except Exception:
        packet_delta = int(flow.get('packets') or 0)
    try:
        byte_delta = int(flow.get('bytes') or 0) - int(previous.get('bytes') or 0)
    except Exception:
        byte_delta = int(flow.get('bytes') or 0)
    score = 0
    reasons = []
    if not previous:
        score += 2
        reasons.append('new')
    if packet_delta >= int(min_packets):
        score += 3
        reasons.append('packets')
    if byte_delta >= int(min_bytes):
        score += 3
        reasons.append('bytes')
    if flow.get('assured'):
        score += 1
        reasons.append('assured')
    if str(flow.get('dport') or '') in TELEGRAM_SIGNAL_PORTS:
        score += 1
        reasons.append('media-port')
    if address_in_networks(flow.get('dst')):
        score += 1
        reasons.append('telegram-net')
    if flow.get('telegram_signal_client'):
        score += 1
        reasons.append('telegram-client')
    if flow.get('udp_call_cluster'):
        score += 2
        reasons.append('udp-cluster')
    if flow.get('udp_call_active_media'):
        score += 2
        reasons.append('active-media')
    return score, reasons, packet_delta, byte_delta


def learn_candidates(
    baseline,
    current,
    seen_addresses=None,
    min_score=5,
    min_packets=2,
    min_bytes=240,
    max_candidates=20,
):
    seen_addresses = set(seen_addresses or ())
    candidates = []
    for identity, flow in (current or {}).items():
        address = flow.get('dst')
        if not address or address in seen_addresses:
            continue
        score, reasons, packet_delta, byte_delta = candidate_score(
            flow,
            previous=(baseline or {}).get(identity),
            min_packets=min_packets,
            min_bytes=min_bytes,
        )
        if score < int(min_score):
            continue
        candidate = dict(flow)
        candidate.update({
            'address': address,
            'score': score,
            'reasons': reasons,
            'packet_delta': packet_delta,
            'byte_delta': byte_delta,
        })
        candidates.append(candidate)
    candidates.sort(key=lambda item: (int(item.get('score') or 0), int(item.get('byte_delta') or 0)), reverse=True)
    return candidates[:max(1, int(max_candidates))]


def _run_quiet(args, timeout=3):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)


def add_candidate_to_ipsets(candidate, protocol, apply=False, run_command=None):
    address = str((candidate or {}).get('address') or (candidate or {}).get('dst') or '').strip()
    sets = protocol_ipsets(protocol)
    result = {
        'address': address,
        'protocol': protocol,
        'sets': list(sets),
        'applied_sets': [],
        'apply': bool(apply),
        'errors': [],
    }
    if not is_public_ipv4(address):
        result['errors'].append('not_public_ipv4')
        return result
    if not sets:
        result['errors'].append('unknown_protocol')
        return result
    if not apply:
        return result
    runner = run_command or _run_quiet
    for set_name in sets:
        try:
            completed = runner(['ipset', 'add', set_name, address, '-exist'], timeout=3)
            returncode = getattr(completed, 'returncode', 0)
            if returncode == 0:
                result['applied_sets'].append(set_name)
            else:
                stderr = getattr(completed, 'stderr', b'')
                if isinstance(stderr, bytes):
                    stderr = stderr.decode('utf-8', errors='replace')
                result['errors'].append(f'{set_name}: {stderr or returncode}')
        except Exception as exc:
            result['errors'].append(f'{set_name}: {exc}')
    return result


def add_candidate_to_call_ipset(candidate, protocol, timeout=14400, apply=False, run_command=None):
    address = str((candidate or {}).get('address') or (candidate or {}).get('dst') or '').strip()
    set_name = protocol_call_ipset(protocol)
    result = {
        'address': address,
        'protocol': protocol,
        'sets': [set_name] if set_name else [],
        'applied_sets': [],
        'apply': bool(apply),
        'errors': [],
    }
    if not is_public_ipv4(address):
        result['errors'].append('not_public_ipv4')
        return result
    if not set_name:
        result['errors'].append('unknown_protocol')
        return result
    if not apply:
        return result
    try:
        timeout_value = max(120, int(timeout or 14400))
    except Exception:
        timeout_value = 14400
    runner = run_command or _run_quiet
    try:
        completed = runner(
            ['ipset', 'add', set_name, address, 'timeout', str(timeout_value), '-exist'],
            timeout=3,
        )
        returncode = getattr(completed, 'returncode', 0)
        if returncode == 0:
            result['applied_sets'].append(set_name)
        else:
            stderr = getattr(completed, 'stderr', b'')
            if isinstance(stderr, bytes):
                stderr = stderr.decode('utf-8', errors='replace')
            result['errors'].append(f'{set_name}: {stderr or returncode}')
    except Exception as exc:
        result['errors'].append(f'{set_name}: {exc}')
    return result


def delete_conntrack_candidate(candidate, run_command=None):
    src = str((candidate or {}).get('src') or '').strip()
    dst = str((candidate or {}).get('dst') or (candidate or {}).get('address') or '').strip()
    if not src or not dst:
        return False
    runner = run_command or _run_quiet
    try:
        completed = runner(['conntrack', '-D', '-p', 'udp', '--orig-src', src, '--orig-dst', dst], timeout=3)
        return getattr(completed, 'returncode', 1) == 0
    except Exception:
        return False
