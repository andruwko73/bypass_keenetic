import ipaddress
import os
import subprocess

from unblock_lists import DEFAULT_ORDER, UNBLOCK_DIR, UNBLOCK_UPDATE_SCRIPT, read_unblock_list_entries, write_unblock_list_entries


MAX_ISSUES = 120
ROUTE_FILES = [name[:-4] for name in DEFAULT_ORDER]


def _read_all(unblock_dir):
    result = {}
    for route in ROUTE_FILES:
        try:
            result[route] = set(read_unblock_list_entries(route, unblock_dir=unblock_dir))
        except FileNotFoundError:
            result[route] = set()
    return result


def _domain_key(entry):
    value = str(entry or '').strip().lower()
    if not value or '/' in value or ':' in value or value.startswith('#'):
        return ''
    value = value.lstrip('*.')
    allowed = set('abcdefghijklmnopqrstuvwxyz0123456789.-_')
    if not value or any(char not in allowed for char in value):
        return ''
    if '.' not in value:
        return ''
    return value.rstrip('.')


def _ip_network(entry):
    value = str(entry or '').strip()
    try:
        return ipaddress.ip_network(value, strict=False)
    except Exception:
        return None


def _owners(entries_by_route, entry):
    return [route for route, entries in entries_by_route.items() if entry in entries]


def analyze_route_intersections(*, unblock_dir=UNBLOCK_DIR, max_issues=MAX_ISSUES):
    entries_by_route = _read_all(unblock_dir)
    issues = []
    exact_seen = {}
    for route, entries in entries_by_route.items():
        for entry in entries:
            exact_seen.setdefault(entry, []).append(route)
    for entry, routes in exact_seen.items():
        if len(routes) > 1:
            issues.append({
                'kind': 'exact',
                'entry': entry,
                'entries': [entry],
                'routes': sorted(routes),
                'message': f'{entry}: точное совпадение в {", ".join(sorted(routes))}',
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
                other_domain == domain
                or other_domain.endswith('.' + domain)
                or domain.endswith('.' + other_domain)
            ):
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

    return {
        'issues': issues[:max_issues],
        'count': len(issues),
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
    report = analyze_route_intersections(unblock_dir=unblock_dir)
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
