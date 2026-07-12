import ipaddress
import math
import os
import subprocess

from service_catalog import (
    CUSTOM_CHECK_PRESETS,
    SERVICE_LIST_SOURCES,
    global_route_exclude_entries,
    normalize_route_entry,
    service_route_entries,
    shared_service_route_entries,
)
from unblock_lists import (
    BASE_LABELS,
    UNBLOCK_DIR,
    UNBLOCK_UPDATE_SCRIPT,
    read_unblock_list_entries,
    write_unblock_list_entries,
)


PROTOCOL_ROUTES = {
    'vless': 'vless',
    'vless2': 'vless-2',
    'vmess': 'vmess',
    'trojan': 'trojan',
    'shadowsocks': 'shadowsocks',
}

ROUTE_PROTOCOLS = {route: proto for proto, route in PROTOCOL_ROUTES.items()}
ROUTE_ORDER = ['vless', 'vless2', 'vmess', 'trojan', 'shadowsocks']

ROUTE_PROFILES = [
    {
        'id': 'youtube_vless2_rest_vless',
        'label': 'YouTube -> Vless 2, остальное -> Vless 1',
        'description': 'Сценарий для раздельных ключей: видео отдельно, Telegram и сервисы отдельно.',
        'youtube_protocol': 'vless2',
        'default_protocol': 'vless',
    },
    {
        'id': 'all_vless',
        'label': 'Все сервисы -> Vless 1',
        'description': 'Один рабочий ключ Vless 1 обслуживает все готовые маршруты.',
        'default_protocol': 'vless',
    },
    {
        'id': 'all_vless2',
        'label': 'Все сервисы -> Vless 2',
        'description': 'Один рабочий ключ Vless 2 обслуживает все готовые маршруты.',
        'default_protocol': 'vless2',
    },
]


def protocol_label(proto):
    route = PROTOCOL_ROUTES.get(proto, proto)
    return BASE_LABELS.get(route, proto)


def protocol_options():
    return [{'value': proto, 'label': protocol_label(proto)} for proto in ROUTE_ORDER]


def route_service_items(*, include_core=True, presets=None):
    items = []
    seen = set()
    preset_items = list(presets or CUSTOM_CHECK_PRESETS)
    presets_by_id = {
        str(item.get('id') or ''): item
        for item in preset_items
        if isinstance(item, dict) and item.get('id')
    }

    def add(service_key, source=None):
        if service_key in seen:
            return
        source = source or SERVICE_LIST_SOURCES.get(service_key) or {}
        if not source.get('entries'):
            return
        seen.add(service_key)
        preset = presets_by_id.get(service_key, {})
        item = {
            'id': service_key,
            'label': source.get('label') or preset.get('label') or service_key,
            'icon': preset.get('icon') or source.get('icon') or '',
            'badge': preset.get('badge') or '',
            'url': preset.get('url') or source.get('url') or '',
            'routes': service_route_entries(service_key),
            'is_custom_check': bool(preset),
        }
        if service_key == 'telegram':
            item['badge'] = item.get('badge') or 'TG'
        if service_key == 'youtube':
            item['badge'] = item.get('badge') or 'YT'
        items.append(item)

    if include_core:
        add('telegram')
        add('youtube')
    for preset in preset_items:
        add(preset.get('id'))
    return items


def _service_entries(service_key):
    entries = []
    seen = set()
    for value in service_route_entries(service_key):
        item = str(value or '').strip()
        if item and item not in seen:
            seen.add(item)
            entries.append(item)
    if not entries:
        raise ValueError(f'У сервиса {service_key} нет готового списка адресов')
    return entries


def _service_profile_enabled(service_key):
    source = SERVICE_LIST_SOURCES.get(service_key) or {}
    return bool(source.get('route_profile_enabled', True))


def _service_state_entries(service_key):
    return set(_service_entries(service_key))


def _read_route(route, unblock_dir):
    try:
        return set(read_unblock_list_entries(route, unblock_dir=unblock_dir))
    except FileNotFoundError:
        return set()


def _read_all_routes(unblock_dir):
    return {
        route: _read_route(route, unblock_dir)
        for route in PROTOCOL_ROUTES.values()
    }


def _write_routes(route_entries, unblock_dir):
    os.makedirs(unblock_dir, exist_ok=True)
    for route, entries in route_entries.items():
        write_unblock_list_entries(route, entries, unblock_dir=unblock_dir)


def _remove_global_route_excludes(route_entries):
    excluded = {
        normalize_route_entry(value)
        for value in global_route_exclude_entries()
        if str(value or '').strip()
    }
    removed = 0
    for values in route_entries.values():
        stale = {entry for entry in values if normalize_route_entry(entry) in excluded}
        if stale:
            values.difference_update(stale)
            removed += len(stale)
    return removed


def _shared_service_entry_set():
    return {
        normalize_route_entry(value)
        for value in shared_service_route_entries()
        if str(value or '').strip()
    }


def _removable_service_entries(entries, shared_entries):
    return {
        entry for entry in entries
        if normalize_route_entry(entry) not in shared_entries
    }


def _run_update(update_script):
    if update_script:
        subprocess.run([update_script], check=False)


def service_route_state(service_key, *, unblock_dir=UNBLOCK_DIR, route_entries=None, service_entries=None):
    try:
        entries = set(service_entries) if service_entries is not None else set(_service_state_entries(service_key))
    except ValueError:
        entries = set()
    total = len(entries)
    routes = {}
    complete = []
    partial = []
    route_entries = route_entries if route_entries is not None else _read_all_routes(unblock_dir)
    for proto in ROUTE_ORDER:
        route = PROTOCOL_ROUTES[proto]
        matched = len(entries & (route_entries.get(route) or set()))
        routes[proto] = {'matched': matched, 'total': total}
        if total and matched == total:
            complete.append(proto)
        elif matched:
            partial.append(proto)
    return {
        'service_key': service_key,
        'total': total,
        'routes': routes,
        'complete_protocols': complete,
        'partial_protocols': partial,
        'label': route_state_label(complete, partial),
    }


def route_state_label(complete, partial):
    if complete:
        return ' / '.join(protocol_label(proto) for proto in complete)
    if partial:
        return 'частично: ' + ' / '.join(protocol_label(proto) for proto in partial)
    return 'не добавлен'


def service_route_summary(service_items, *, unblock_dir=UNBLOCK_DIR, route_entries=None):
    route_entries = route_entries if route_entries is not None else _read_all_routes(unblock_dir)
    summary = {}
    service_entries_cache = {}
    for item in service_items or []:
        service_key = item.get('id') if isinstance(item, dict) else str(item or '')
        if not service_key:
            continue
        try:
            service_entries_cache[service_key] = set(_service_state_entries(service_key))
        except ValueError:
            service_entries_cache[service_key] = set()
        summary[service_key] = service_route_state(
            service_key,
            unblock_dir=unblock_dir,
            route_entries=route_entries,
            service_entries=service_entries_cache[service_key],
        )
    return summary


def apply_service_route(
    service_key,
    target_protocol,
    *,
    remove_from_others=True,
    unblock_dir=UNBLOCK_DIR,
    update_script=UNBLOCK_UPDATE_SCRIPT,
    before_update=None,
):
    if target_protocol not in PROTOCOL_ROUTES:
        raise ValueError('Неизвестный протокол')
    entries = set(_service_entries(service_key))
    target_route = PROTOCOL_ROUTES[target_protocol]
    route_entries = _read_all_routes(unblock_dir)
    shared_entries = _shared_service_entry_set()
    removable_entries = _removable_service_entries(entries, shared_entries)
    removed = _remove_global_route_excludes(route_entries)
    before_target = set(route_entries[target_route])
    if remove_from_others:
        for route, values in route_entries.items():
            if route == target_route:
                continue
            size_before = len(values)
            values.difference_update(removable_entries)
            removed += size_before - len(values)
    route_entries[target_route].update(entries)
    added = len(route_entries[target_route] - before_target)
    _write_routes(route_entries, unblock_dir)
    if callable(before_update):
        before_update()
    _run_update(update_script)
    source = SERVICE_LIST_SOURCES.get(service_key) or {}
    return {
        'service_key': service_key,
        'service_label': source.get('label') or service_key,
        'target_protocol': target_protocol,
        'target_label': protocol_label(target_protocol),
        'entries': len(entries),
        'added': added,
        'removed': removed,
    }


def repair_service_route_catalog_drift(
    *,
    service_items=None,
    min_coverage=0.5,
    remove_from_others=True,
    unblock_dir=UNBLOCK_DIR,
    update_script=UNBLOCK_UPDATE_SCRIPT,
    before_update=None,
):
    service_items = service_items or route_service_items()
    route_entries = _read_all_routes(unblock_dir)
    repaired = []
    global_removed = _remove_global_route_excludes(route_entries)
    shared_entries = _shared_service_entry_set()
    threshold_ratio = max(0.0, min(1.0, float(min_coverage)))

    for item in service_items:
        service_key = item.get('id') if isinstance(item, dict) else str(item or '')
        if not service_key:
            continue
        if not _service_profile_enabled(service_key):
            continue
        try:
            entries = set(_service_entries(service_key))
        except ValueError:
            continue
        if not entries:
            continue

        matches = {
            proto: entries & route_entries[PROTOCOL_ROUTES[proto]]
            for proto in ROUTE_ORDER
        }
        matched_protocols = [proto for proto in ROUTE_ORDER if matches[proto]]
        if not matched_protocols:
            continue

        complete_protocols = [
            proto for proto in ROUTE_ORDER
            if len(matches[proto]) == len(entries)
        ]
        if complete_protocols:
            target_protocol = complete_protocols[0]
            reason = 'duplicate_cleanup'
        else:
            target_protocol = max(
                matched_protocols,
                key=lambda proto: (len(matches[proto]), -ROUTE_ORDER.index(proto)),
            )
            required = max(1, int(math.ceil(len(entries) * threshold_ratio)))
            if len(matches[target_protocol]) < required:
                continue
            reason = 'catalog_drift'

        target_route = PROTOCOL_ROUTES[target_protocol]
        before_target = set(route_entries[target_route])
        removed = 0
        if remove_from_others:
            removable_entries = _removable_service_entries(entries, shared_entries)
            for route, values in route_entries.items():
                if route == target_route:
                    continue
                size_before = len(values)
                values.difference_update(removable_entries)
                removed += size_before - len(values)

        route_entries[target_route].update(entries)
        added = len(route_entries[target_route] - before_target)
        if added or removed:
            source = SERVICE_LIST_SOURCES.get(service_key) or {}
            repaired.append({
                'service_key': service_key,
                'service_label': source.get('label') or service_key,
                'target_protocol': target_protocol,
                'target_label': protocol_label(target_protocol),
                'entries': len(entries),
                'matched': len(matches[target_protocol]),
                'added': added,
                'removed': removed,
                'reason': reason,
            })

    if repaired or global_removed:
        _write_routes(route_entries, unblock_dir)
        if callable(before_update):
            before_update()
        _run_update(update_script)

    return {
        'services': len(repaired),
        'entries_added': sum(item.get('added', 0) for item in repaired),
        'entries_removed': global_removed + sum(item.get('removed', 0) for item in repaired),
        'global_entries_removed': global_removed,
        'repaired': repaired,
    }


def _unique_complete_protocol_for_service(service_key, *, unblock_dir=UNBLOCK_DIR, route_entries=None):
    state = service_route_state(service_key, unblock_dir=unblock_dir, route_entries=route_entries)
    complete = [
        proto for proto in (state.get('complete_protocols') or [])
        if proto in PROTOCOL_ROUTES
    ]
    if len(complete) == 1:
        return complete[0], state
    return '', state


def _intersection_target_for_service(service_key, *, unblock_dir=UNBLOCK_DIR, route_entries=None):
    complete_protocol, state = _unique_complete_protocol_for_service(
        service_key,
        unblock_dir=unblock_dir,
        route_entries=route_entries,
    )
    if complete_protocol:
        return complete_protocol, state
    scores = []
    for proto in ROUTE_ORDER:
        route_state = (state.get('routes') or {}).get(proto) or {}
        try:
            matched = int(route_state.get('matched') or 0)
        except Exception:
            matched = 0
        if matched > 0:
            scores.append((matched, -ROUTE_ORDER.index(proto), proto))
    if not scores:
        return '', state
    scores.sort(reverse=True)
    if len(scores) == 1:
        return scores[0][2], state
    if scores[0][0] > scores[1][0]:
        return scores[0][2], state
    return '', state


def _service_item_id_set(service_items):
    if service_items is None:
        return None
    service_item_ids = {
        str(item.get('id') if isinstance(item, dict) else item or '').strip()
        for item in service_items
    }
    service_item_ids.discard('')
    return service_item_ids


def _issue_service_keys(issue, service_item_ids=None):
    service_keys = []
    for service_key in issue.get('service_keys') or []:
        service_key = str(service_key or '').strip()
        if not service_key or service_key in service_keys:
            continue
        if service_item_ids is not None and service_key not in service_item_ids:
            continue
        if not _service_profile_enabled(service_key):
            continue
        service_keys.append(service_key)
    return service_keys


def _service_targets(service_keys, *, unblock_dir=UNBLOCK_DIR, route_entries=None):
    targets = {}
    missing_targets = []
    for service_key in service_keys:
        target_protocol, _state = _intersection_target_for_service(
            service_key,
            unblock_dir=unblock_dir,
            route_entries=route_entries,
        )
        if not target_protocol:
            missing_targets.append(service_key)
            continue
        targets[service_key] = target_protocol
    unique_targets = set(targets.values())
    return targets, missing_targets, unique_targets


def _service_runtime_networks(service_key):
    networks = []
    for entry in _service_entries(service_key):
        network = _runtime_ip_network(entry)
        if network:
            networks.append(network)
    return tuple(networks)


def _runtime_network_overlaps_any(network, networks):
    if not network:
        return False
    for service_network in networks or ():
        if network.version == service_network.version and network.overlaps(service_network):
            return True
    return False


def _runtime_command(args, *, run_command=subprocess.run, stdout=subprocess.PIPE, timeout=3):
    try:
        return run_command(
            args,
            stdout=stdout,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            check=False,
        )
    except TypeError:
        try:
            return run_command(args)
        except Exception:
            return None
    except Exception:
        return None


def _runtime_command_stdout(args, *, run_command=subprocess.run, timeout=3):
    result = _runtime_command(args, run_command=run_command, stdout=subprocess.PIPE, timeout=timeout)
    if result is None:
        return ''
    if isinstance(result, str):
        return result
    stdout = getattr(result, 'stdout', '') or ''
    if isinstance(stdout, bytes):
        return stdout.decode('utf-8', errors='ignore')
    return str(stdout or '')


def _runtime_command_ok(args, *, run_command=subprocess.run, timeout=3):
    result = _runtime_command(args, run_command=run_command, stdout=subprocess.DEVNULL, timeout=timeout)
    if isinstance(result, bool):
        return result
    if result is None:
        return False
    try:
        return int(getattr(result, 'returncode', 1) or 0) == 0
    except Exception:
        return False


def _read_runtime_ipset_members(set_name, *, run_command=subprocess.run):
    if not set_name:
        return set()
    text = _runtime_command_stdout(['ipset', 'list', set_name], run_command=run_command)
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


def _runtime_ip_network(value):
    value = str(value or '').strip().split()[0] if str(value or '').strip() else ''
    try:
        return ipaddress.ip_network(value, strict=False)
    except Exception:
        return None


def _runtime_network_items(members):
    items = {4: [], 6: []}
    for value in members or []:
        network = _runtime_ip_network(value)
        if not network:
            continue
        items[network.version].append((
            int(network.network_address),
            int(network.broadcast_address),
            value,
            network,
        ))
    for version in items:
        items[version].sort(key=lambda item: (item[0], item[1], item[2]))
    return items


def _runtime_priority_networks(members):
    networks = {4: [], 6: []}
    for value in members or []:
        network = _runtime_ip_network(value)
        if network:
            networks[network.version].append(network)
    return networks


def _runtime_network_is_host(network):
    return bool(network and network.prefixlen == network.max_prefixlen)


def _runtime_network_in_priority(network, priority_networks):
    if not network:
        return False
    for priority_network in priority_networks.get(network.version, []):
        if network.subnet_of(priority_network):
            return True
    return False


def _runtime_priority_overlap_is_protected(left_network, right_network, left_priority, right_priority):
    left_priority_hit = _runtime_network_in_priority(left_network, left_priority)
    right_priority_hit = _runtime_network_in_priority(right_network, right_priority)
    if left_priority_hit and right_priority_hit:
        return False
    if left_priority_hit and _runtime_network_is_host(left_network):
        return True
    if right_priority_hit and _runtime_network_is_host(right_network):
        return True
    return False


def _runtime_overlapping_loser_members(
    loser_members,
    winner_members,
    *,
    loser_priority_members=None,
    winner_priority_members=None,
):
    loser_items = _runtime_network_items(loser_members)
    winner_items = _runtime_network_items(winner_members)
    loser_priority = _runtime_priority_networks(loser_priority_members)
    winner_priority = _runtime_priority_networks(winner_priority_members)
    delete_members = []
    seen = set()
    for version in (4, 6):
        winners = winner_items[version]
        winner_index = 0
        for loser_start, loser_end, loser_value, loser_network in loser_items[version]:
            while winner_index < len(winners) and winners[winner_index][1] < loser_start:
                winner_index += 1
            scan_index = winner_index
            while scan_index < len(winners) and winners[scan_index][0] <= loser_end:
                winner_start, winner_end, _winner_value, winner_network = winners[scan_index]
                if winner_end >= loser_start and not _runtime_priority_overlap_is_protected(
                    loser_network,
                    winner_network,
                    loser_priority,
                    winner_priority,
                ):
                    if loser_value not in seen:
                        seen.add(loser_value)
                        delete_members.append(loser_value)
                    break
                scan_index += 1
    return delete_members


def _runtime_set_index():
    import route_intersections

    index = {}
    for route, sets in route_intersections.ROUTE_IPSET_SETS.items():
        for set_name, kind in sets:
            index[set_name] = {'route': route, 'kind': kind}
    return index


def _runtime_priority_set(route, kind):
    import route_intersections

    return (route_intersections.ROUTE_PRIORITY_IPSET_SETS.get(route) or {}).get(kind) or ''


def _runtime_cleanup_pairs_for_issue(issue, target_protocol):
    target_route = PROTOCOL_ROUTES.get(target_protocol)
    if not target_route:
        return []
    set_index = _runtime_set_index()
    issue_sets = [
        str(set_name or '').strip()
        for set_name in issue.get('set_names') or []
        if str(set_name or '').strip()
    ]
    pairs = []
    for winner_set in issue_sets:
        winner_meta = set_index.get(winner_set) or {}
        if winner_meta.get('route') != target_route:
            continue
        winner_kind = winner_meta.get('kind')
        for loser_set in issue_sets:
            if loser_set == winner_set:
                continue
            loser_meta = set_index.get(loser_set) or {}
            if not loser_meta or loser_meta.get('route') == target_route:
                continue
            if loser_meta.get('kind') != winner_kind:
                continue
            pairs.append({
                'loser_set': loser_set,
                'winner_set': winner_set,
                'loser_route': loser_meta.get('route') or '',
                'winner_route': target_route,
                'kind': winner_kind or '',
            })
    return pairs


def _delete_runtime_pair_overlaps(pair, *, run_command=subprocess.run):
    import route_intersections

    loser_set = pair.get('loser_set') or ''
    winner_set = pair.get('winner_set') or ''
    kind = pair.get('kind') or ''
    loser_priority_set = _runtime_priority_set(pair.get('loser_route'), kind)
    winner_priority_set = _runtime_priority_set(pair.get('winner_route'), kind)
    members = route_intersections.read_runtime_ipset_members_map(
        (loser_set, winner_set, loser_priority_set, winner_priority_set),
        run_command=run_command,
    )
    loser_members = members.get(loser_set, set())
    winner_members = members.get(winner_set, set())
    loser_priority = members.get(loser_priority_set, set())
    winner_priority = members.get(winner_priority_set, set())
    delete_members = _runtime_overlapping_loser_members(
        loser_members,
        winner_members,
        loser_priority_members=loser_priority,
        winner_priority_members=winner_priority,
    )
    service_networks = pair.get('service_networks')
    if service_networks is not None:
        delete_members = [
            member for member in delete_members
            if _runtime_network_overlaps_any(_runtime_ip_network(member), service_networks)
        ]
    deleted = 0
    failed = 0
    for member in delete_members:
        if _runtime_command_ok(['ipset', 'del', loser_set, member], run_command=run_command):
            deleted += 1
        else:
            failed += 1
    result = {
        **pair,
        'overlap_members': len(delete_members),
        'deleted_members': deleted,
        'failed_members': failed,
    }
    result.pop('service_networks', None)
    return result


def cleanup_runtime_service_route_intersections(
    *,
    report=None,
    service_items=None,
    unblock_dir=UNBLOCK_DIR,
    include_runtime=True,
    run_command=subprocess.run,
):
    if report is None:
        import route_intersections
        report = route_intersections.analyze_route_intersections(
            unblock_dir=unblock_dir,
            include_runtime=include_runtime,
            run_command=run_command,
        )
    service_item_ids = _service_item_id_set(service_items)
    route_entries = _read_all_routes(unblock_dir)
    pair_keys = set()
    pair_plans = []
    planned_services = set()
    skipped = []
    for issue in report.get('issues') or []:
        if issue.get('kind') != 'runtime_ipset_overlap':
            continue
        service_keys = _issue_service_keys(issue, service_item_ids)
        if not service_keys:
            skipped.append({'reason': 'unknown_service', 'issue': issue.get('message') or issue.get('entry') or ''})
            continue
        targets, missing_targets, unique_targets = _service_targets(
            service_keys,
            unblock_dir=unblock_dir,
            route_entries=route_entries,
        )
        if missing_targets:
            skipped.append({
                'reason': 'no_unique_target',
                'services': missing_targets,
                'issue': issue.get('message') or issue.get('entry') or '',
            })
        mixed_targets = len(unique_targets) > 1
        for service_key, target_protocol in targets.items():
            service_networks = None
            if mixed_targets:
                service_networks = _service_runtime_networks(service_key)
                if not service_networks:
                    skipped.append({
                        'reason': 'no_service_network_filter',
                        'services': [service_key],
                        'target_protocol': target_protocol,
                        'issue': issue.get('message') or issue.get('entry') or '',
                    })
                    continue
            pairs = _runtime_cleanup_pairs_for_issue(issue, target_protocol)
            if not pairs:
                skipped.append({
                    'reason': 'no_runtime_pair',
                    'services': [service_key],
                    'target_protocol': target_protocol,
                    'issue': issue.get('message') or issue.get('entry') or '',
                })
                continue
            for pair in pairs:
                key = (service_key, pair.get('loser_set'), pair.get('winner_set'), pair.get('kind'))
                if key in pair_keys:
                    continue
                pair_keys.add(key)
                pair['services'] = [service_key]
                pair['target_protocol'] = target_protocol
                pair['service_networks'] = service_networks
                pair_plans.append(pair)
                planned_services.add(service_key)

    applied = [
        _delete_runtime_pair_overlaps(pair, run_command=run_command)
        for pair in pair_plans
    ]
    return {
        'services': len(planned_services),
        'service_keys': sorted(planned_services),
        'pairs': len(applied),
        'deleted_members': sum(item.get('deleted_members', 0) for item in applied),
        'failed_members': sum(item.get('failed_members', 0) for item in applied),
        'overlap_members': sum(item.get('overlap_members', 0) for item in applied),
        'applied': applied,
        'skipped': skipped,
    }


def auto_resolve_service_route_intersections(
    *,
    report=None,
    service_items=None,
    unblock_dir=UNBLOCK_DIR,
    update_script=UNBLOCK_UPDATE_SCRIPT,
    before_update=None,
    include_runtime=True,
    run_command=subprocess.run,
):
    if report is None:
        import route_intersections
        report = route_intersections.analyze_route_intersections(
            unblock_dir=unblock_dir,
            include_runtime=include_runtime,
            run_command=run_command,
        )
    service_item_ids = _service_item_id_set(service_items)
    route_entries = _read_all_routes(unblock_dir)

    plans = {}
    resolved = []
    skipped = []
    for issue in report.get('issues') or []:
        service_keys = _issue_service_keys(issue, service_item_ids)
        if not service_keys:
            skipped.append({'reason': 'unknown_service', 'issue': issue.get('message') or issue.get('entry') or ''})
            continue

        targets, missing_targets, unique_targets = _service_targets(
            service_keys,
            unblock_dir=unblock_dir,
            route_entries=route_entries,
        )
        if missing_targets:
            skipped.append({
                'reason': 'no_unique_target',
                'services': missing_targets,
                'issue': issue.get('message') or issue.get('entry') or '',
            })
            continue
        if len(unique_targets) != 1:
            skipped.append({
                'reason': 'conflicting_targets',
                'services': service_keys,
                'targets': dict(targets),
                'issue': issue.get('message') or issue.get('entry') or '',
            })
            continue

        if issue.get('kind') != 'runtime_ipset_overlap':
            for service_key, target_protocol in targets.items():
                plans[service_key] = target_protocol
        resolved.append({
            'issue': issue.get('message') or issue.get('entry') or '',
            'services': list(service_keys),
            'target_protocol': next(iter(unique_targets)),
            'target_label': protocol_label(next(iter(unique_targets))),
            'routes': list(issue.get('routes') or []),
            'kind': issue.get('kind') or '',
        })

    applied = []
    for service_key, target_protocol in sorted(plans.items(), key=lambda item: ROUTE_ORDER.index(item[1])):
        applied.append(
            apply_service_route(
                service_key,
                target_protocol,
                remove_from_others=True,
                unblock_dir=unblock_dir,
                update_script='',
            )
        )
    runtime_cleanup = cleanup_runtime_service_route_intersections(
        report=report,
        service_items=service_items,
        unblock_dir=unblock_dir,
        run_command=run_command,
    )
    if applied:
        if callable(before_update):
            before_update()
        _run_update(update_script)

    resolved_service_keys = {
        str(item.get('service_key') or '').strip()
        for item in applied
        if str(item.get('service_key') or '').strip()
    }
    resolved_service_keys.update(
        str(service_key or '').strip()
        for service_key in runtime_cleanup.get('service_keys') or []
        if str(service_key or '').strip()
    )
    return {
        'issues': int(report.get('count') or 0),
        'services': len(resolved_service_keys),
        'entries_added': sum(item.get('added', 0) for item in applied),
        'entries_removed': (
            sum(item.get('removed', 0) for item in applied) +
            int(runtime_cleanup.get('deleted_members') or 0)
        ),
        'applied': applied,
        'runtime_cleanup': runtime_cleanup,
        'resolved': resolved,
        'skipped': skipped,
    }


def _profile_target(profile, service_key):
    if profile.get('id') == 'youtube_vless2_rest_vless' and service_key == 'youtube':
        return profile.get('youtube_protocol') or 'vless2'
    return profile.get('default_protocol') or 'vless'


def apply_service_profile(
    profile_id,
    *,
    service_items=None,
    unblock_dir=UNBLOCK_DIR,
    update_script=UNBLOCK_UPDATE_SCRIPT,
    before_update=None,
):
    profile = next((item for item in ROUTE_PROFILES if item.get('id') == profile_id), None)
    if not profile:
        raise ValueError('Неизвестный профиль маршрутизации')
    service_items = service_items or route_service_items()
    results = []
    for item in service_items:
        if not _service_profile_enabled(item['id']):
            continue
        target_protocol = _profile_target(profile, item['id'])
        results.append(
            apply_service_route(
                item['id'],
                target_protocol,
                remove_from_others=True,
                unblock_dir=unblock_dir,
                update_script='',
            )
        )
    repair = repair_service_route_catalog_drift(
        service_items=service_items,
        unblock_dir=unblock_dir,
        update_script='',
    )
    if callable(before_update):
        before_update()
    _run_update(update_script)
    return {
        'profile_id': profile_id,
        'profile_label': profile['label'],
        'services': len(results),
        'entries': sum(item.get('entries', 0) for item in results),
        'results': results,
        'repair': repair,
    }
