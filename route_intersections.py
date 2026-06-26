import ipaddress
import os
import subprocess

from service_catalog import normalize_route_entry, shared_service_route_entries
from unblock_lists import DEFAULT_ORDER, UNBLOCK_DIR, UNBLOCK_UPDATE_SCRIPT, read_unblock_list_entries, write_unblock_list_entries


MAX_ISSUES = 120
IPSET_STATUS_FILE = '/opt/tmp/bypass_ipset_status.json'
ROUTE_FILES = [name[:-4] for name in DEFAULT_ORDER]
ROUTE_IPSET_SETS = {
    'shadowsocks': (('unblocksh', 'tcp'), ('unblockshudp', 'udp'), ('unblocksh6', 'ipv6')),
    'vmess': (('unblockvmess', 'tcp'), ('unblockvmessudp', 'udp'), ('unblockvmess6', 'ipv6')),
    'vless': (('unblockvless', 'tcp'), ('unblockvlessudp', 'udp'), ('unblockvless6', 'ipv6')),
    'vless-2': (('unblockvless2', 'tcp'), ('unblockvless2udp', 'udp'), ('unblockvless2v6', 'ipv6')),
    'trojan': (('unblocktroj', 'tcp'), ('unblocktrojudp', 'udp'), ('unblocktroj6', 'ipv6')),
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


def route_files_signature(unblock_dir=UNBLOCK_DIR):
    signature = []
    for route in ROUTE_FILES:
        path = os.path.join(unblock_dir, f'{route}.txt')
        try:
            stat = os.stat(path)
            signature.append((route, int(stat.st_mtime), int(stat.st_size)))
        except FileNotFoundError:
            signature.append((route, 0, 0))
        except Exception:
            signature.append((route, -1, -1))
    return tuple(signature)


def runtime_ipset_signature(status_path=IPSET_STATUS_FILE):
    try:
        stat = os.stat(status_path)
        return (status_path, int(getattr(stat, 'st_mtime_ns', int(stat.st_mtime * 1000000000))), int(stat.st_size))
    except FileNotFoundError:
        return (status_path, 0, 0)
    except Exception:
        return (status_path, -1, -1)


def _read_all(unblock_dir):
    result = {}
    for route in ROUTE_FILES:
        try:
            result[route] = set(read_unblock_list_entries(route, unblock_dir=unblock_dir))
        except FileNotFoundError:
            result[route] = set()
    return result


def _entry_value(entry):
    value = str(entry or '').strip()
    if not value or value.startswith('#'):
        return ''
    return value.split('#', 1)[0].strip()


def _entry_key(entry):
    value = _entry_value(entry)
    if not value:
        return ''
    return normalize_route_entry(value)


def _domain_key(entry):
    value = _entry_value(entry).lower()
    if not value or '/' in value or ':' in value:
        return ''
    value = value.lstrip('*.')
    allowed = set('abcdefghijklmnopqrstuvwxyz0123456789.-_')
    if not value or any(char not in allowed for char in value):
        return ''
    if '.' not in value:
        return ''
    if _ip_network(value):
        return ''
    return value.rstrip('.')


def _ip_network(entry):
    value = _entry_value(entry)
    try:
        return ipaddress.ip_network(value, strict=False)
    except Exception:
        return None


def _owners(entries_by_route, entry):
    return [route for route, entries in entries_by_route.items() if entry in entries]


def _command_text(args, *, run_command=subprocess.run, timeout=3):
    try:
        result = run_command(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return ''
    return result.stdout or ''


def _read_ipset_members(set_name, *, run_command=subprocess.run):
    text = _command_text(['ipset', 'list', set_name], run_command=run_command)
    members = set()
    in_members = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == 'Members:':
            in_members = True
            continue
        if in_members:
            members.add(line.split()[0])
    return members


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
    members_by_set = {}
    for sets in ROUTE_IPSET_SETS.values():
        for set_name, _kind in sets:
            members_by_set[set_name] = _read_ipset_members(set_name, run_command=run_command)
    priority_members = {}
    for route, sets_by_kind in ROUTE_PRIORITY_IPSET_SETS.items():
        for kind, set_name in sets_by_kind.items():
            priority_members[(route, kind)] = _read_ipset_members(set_name, run_command=run_command)

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
                sample = samples
                shared = [None] * match_count
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
                        f'{set_name} и {other_set}: {len(shared)} общих IP '
                        f'в реальных ipset ({", ".join(sample)})'
                    ),
                })
                if len(issues) >= max_issues:
                    return issues
    return issues


def analyze_route_intersections(
    *,
    unblock_dir=UNBLOCK_DIR,
    max_issues=MAX_ISSUES,
    include_runtime=True,
    run_command=subprocess.run,
):
    entries_by_route = _read_all(unblock_dir)
    issues = []
    shared_entries = {
        normalize_route_entry(entry)
        for entry in shared_service_route_entries()
        if str(entry or '').strip()
    }
    exact_seen = {}
    for route, entries in entries_by_route.items():
        for entry in entries:
            key = _entry_key(entry)
            if not key:
                continue
            bucket = exact_seen.setdefault(key, {'routes': set(), 'entries': set(), 'display': _entry_value(entry)})
            bucket['routes'].add(route)
            bucket['entries'].add(entry)
    for key, bucket in exact_seen.items():
        routes = sorted(bucket['routes'])
        if len(routes) > 1 and key not in shared_entries:
            display = bucket.get('display') or key
            issues.append({
                'kind': 'exact',
                'entry': display,
                'entries': sorted(bucket['entries']),
                'routes': routes,
                'message': f'{display}: точное совпадение в {", ".join(routes)}',
            })

    domains = []
    for route, entries in entries_by_route.items():
        for entry in entries:
            domain = _domain_key(entry)
            if domain:
                domains.append((domain, entry, route))
    domains.sort()
    suffix_pairs = set()
    for index, (domain, entry, route) in enumerate(domains):
        for other_domain, other_entry, other_route in domains[index + 1:]:
            if route == other_route:
                continue
            if (
                other_domain.endswith('.' + domain)
                or domain.endswith('.' + other_domain)
            ):
                if (
                    _entry_key(entry) in shared_entries
                    and _entry_key(other_entry) in shared_entries
                ):
                    continue
                pair = tuple(sorted((entry, other_entry))) + tuple(sorted((route, other_route)))
                if pair not in suffix_pairs:
                    suffix_pairs.add(pair)
                    issues.append({
                        'kind': 'domain_suffix',
                        'entry': entry,
                        'entries': sorted({entry, other_entry}),
                        'routes': sorted({route, other_route}),
                        'message': f'{other_entry} пересекается с {entry}',
                    })
            if len(issues) >= max_issues:
                break
        if len(issues) >= max_issues:
            break

    networks = []
    for route, entries in entries_by_route.items():
        for entry in entries:
            network = _ip_network(entry)
            if network:
                networks.append((network, entry, route))
    for index, (network, entry, route) in enumerate(networks):
        for other_network, other_entry, other_route in networks[index + 1:]:
            if route == other_route:
                continue
            if network == other_network:
                continue
            if network.version == other_network.version and network.overlaps(other_network):
                issues.append({
                    'kind': 'ip_overlap',
                    'entry': entry,
                    'entries': sorted({entry, other_entry}),
                    'routes': sorted({route, other_route}),
                    'message': f'{entry} пересекается с {other_entry}',
                })
            if len(issues) >= max_issues:
                break
        if len(issues) >= max_issues:
            break

    file_issues = list(issues)
    runtime_issues = []
    if include_runtime and len(issues) < max_issues:
        runtime_issues = _runtime_ipset_intersections(
            max_issues=max_issues - len(issues),
            run_command=run_command,
        )
        issues.extend(runtime_issues)

    return {
        'issues': issues[:max_issues],
        'count': len(issues),
        'file_count': len(file_issues),
        'runtime_count': len(runtime_issues),
        'runtime_match_count': sum(int(item.get('match_count') or 0) for item in runtime_issues),
        'truncated': len(issues) > max_issues,
        'routes': {route: len(entries) for route, entries in entries_by_route.items()},
    }


def resolve_route_intersections(
    target_route,
    *,
    unblock_dir=UNBLOCK_DIR,
    update_script=UNBLOCK_UPDATE_SCRIPT,
    before_update=None,
):
    target_route = str(target_route or '').strip()
    if target_route.endswith('.txt'):
        target_route = target_route[:-4]
    if target_route not in ROUTE_FILES:
        raise ValueError('Неизвестный список обхода')
    report = analyze_route_intersections(unblock_dir=unblock_dir, include_runtime=False)
    entries_by_route = _read_all(unblock_dir)
    affected = set()
    for issue in report.get('issues') or []:
        affected.update(issue.get('entries') or [])
    for route, entries in entries_by_route.items():
        entries.difference_update(affected)
    entries_by_route[target_route].update(affected)
    os.makedirs(unblock_dir, exist_ok=True)
    for route, entries in entries_by_route.items():
        write_unblock_list_entries(route, entries, unblock_dir=unblock_dir)
    if callable(before_update):
        before_update()
    if update_script:
        subprocess.run([update_script], check=False)
    return {
        'target_route': target_route,
        'moved': len(affected),
        'issues': report.get('count', 0),
    }
