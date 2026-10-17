# Immutable comparison oracle from 2e13a006 (1.1087); synthetic inputs only.
import ipaddress
import subprocess

MAX_ISSUES = 120

ROUTE_IPSET_SETS = {
    'shadowsocks': (('unblocksh', 'tcp'), ('unblockshudp', 'udp'), ('unblocksh6', 'ipv6')),
    'vmess': (('unblockvmess', 'tcp'), ('unblockvmessudp', 'udp'), ('unblockvmess6', 'ipv6')),
    'vless': (('unblockvless', 'tcp'), ('unblockvlessudp', 'udp'), ('unblockvless6', 'ipv6')),
    'vless-2': (('unblockvless2', 'tcp'), ('unblockvless2udp', 'udp'), ('unblockvless2v6', 'ipv6')),
    'trojan': (('unblocktroj', 'tcp'), ('unblocktrojudp', 'udp'), ('unblocktroj6', 'ipv6')),
    'hysteria2': (('unblockhy2', 'tcp'), ('unblockhy2udp', 'udp'), ('unblockhy26', 'ipv6')),
}

ROUTE_PRIORITY_IPSET_SETS = {
    'vless': {
        'tcp': 'unblockvlesspriority',
        'udp': 'unblockvlesspriority',
        'ipv6': 'unblockvlesspriority6',
    },
    'vless-2': {
        'tcp': 'unblockvless2priority',
        'udp': 'unblockvless2priority',
        'ipv6': 'unblockvless2priority6',
    },
}

def read_runtime_ipset_members_map(*args, **kwargs):
    raise AssertionError("test must supply synthetic snapshot")

def _entry_value(entry):
    value = str(entry or '').strip()
    if not value or value.startswith('#'):
        return ''
    return value.split('#', 1)[0].strip()

def _ip_network(entry):
    value = _entry_value(entry)
    try:
        return ipaddress.ip_network(value, strict=False)
    except Exception:
        return None

def _priority_networks(members):
    networks = {4: [], 6: []}
    for value in members or []:
        network = _ip_network(value)
        if network:
            networks[network.version].append(network)
    return networks

def _network_is_host(network):
    return bool(network and network.prefixlen == network.max_prefixlen)

def _network_in_priority(network, priority_networks):
    if not network:
        return False
    for priority_network in priority_networks.get(network.version, []):
        if network.subnet_of(priority_network):
            return True
    return False

def _priority_overlap_is_protected(left_network, right_network, left_priority, right_priority):
    left_priority_hit = _network_in_priority(left_network, left_priority)
    right_priority_hit = _network_in_priority(right_network, right_priority)
    if left_priority_hit and right_priority_hit:
        return False
    if left_priority_hit and _network_is_host(left_network):
        return True
    if right_priority_hit and _network_is_host(right_network):
        return True
    return False

def _network_overlap_samples(
    left_members,
    right_members,
    *,
    max_samples=8,
    left_priority_members=None,
    right_priority_members=None,
):
    left_networks = {4: [], 6: []}
    right_networks = {4: [], 6: []}
    left_priority = _priority_networks(left_priority_members)
    right_priority = _priority_networks(right_priority_members)
    for value in left_members or []:
        network = _ip_network(value)
        if network:
            left_networks[network.version].append((
                int(network.network_address),
                int(network.broadcast_address),
                value,
                network,
            ))
    for value in right_members or []:
        network = _ip_network(value)
        if network:
            right_networks[network.version].append((
                int(network.network_address),
                int(network.broadcast_address),
                value,
                network,
            ))
    samples = []
    seen = set()
    match_count = 0
    for version in (4, 6):
        left_items = sorted(left_networks[version], key=lambda item: (item[0], item[1], item[2]))
        right_items = sorted(right_networks[version], key=lambda item: (item[0], item[1], item[2]))
        right_index = 0
        for left_start, left_end, left_value, left_network in left_items:
            while right_index < len(right_items) and right_items[right_index][1] < left_start:
                right_index += 1
            scan_index = right_index
            while scan_index < len(right_items) and right_items[scan_index][0] <= left_end:
                right_start, right_end, right_value, right_network = right_items[scan_index]
                if right_end >= left_start:
                    if _priority_overlap_is_protected(
                        left_network,
                        right_network,
                        left_priority,
                        right_priority,
                    ):
                        scan_index += 1
                        continue
                    key = (left_value, right_value)
                    if key not in seen:
                        seen.add(key)
                        match_count += 1
                        if len(samples) < max_samples:
                            samples.append(left_value if left_value == right_value else f'{left_value} / {right_value}')
                scan_index += 1
    return samples, match_count

def _runtime_ipset_intersections(*, max_issues=MAX_ISSUES, run_command=subprocess.run):
    set_names = {
        set_name
        for sets in ROUTE_IPSET_SETS.values()
        for set_name, _kind in sets
    }
    set_names.update(
        set_name
        for sets_by_kind in ROUTE_PRIORITY_IPSET_SETS.values()
        for set_name in sets_by_kind.values()
    )
    members_by_set = read_runtime_ipset_members_map(set_names, run_command=run_command)
    priority_members = {}
    for route, sets_by_kind in ROUTE_PRIORITY_IPSET_SETS.items():
        for kind, set_name in sets_by_kind.items():
            priority_members[(route, kind)] = members_by_set.get(set_name, set())

    issues = []
    routes = list(ROUTE_IPSET_SETS)
    for index, route in enumerate(routes):
        for other_route in routes[index + 1:]:
            for (set_name, kind), (other_set, other_kind) in zip(
                ROUTE_IPSET_SETS[route],
                ROUTE_IPSET_SETS[other_route],
            ):
                if kind != other_kind:
                    continue
                samples, match_count = _network_overlap_samples(
                    members_by_set.get(set_name, set()),
                    members_by_set.get(other_set, set()),
                    left_priority_members=priority_members.get((route, kind), set()),
                    right_priority_members=priority_members.get((other_route, kind), set()),
                )
                if not match_count:
                    continue
                issues.append({
                    'kind': 'runtime_ipset_overlap',
                    'runtime': True,
                    'entry': f'{set_name} / {other_set}',
                    'entries': [],
                    'routes': sorted({route, other_route}),
                    'set_names': [set_name, other_set],
                    'match_count': match_count,
                    'samples': samples,
                    'message': (
                        f'{set_name} и {other_set}: {match_count} общих IP '
                        f'в реальных ipset ({", ".join(samples)})'
                    ),
                })
                if len(issues) >= max_issues:
                    return issues
    return issues
