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

    def add(service_key, source=None):
        if service_key in seen:
            return
        source = source or SERVICE_LIST_SOURCES.get(service_key) or {}
        if not source.get('entries'):
            return
        seen.add(service_key)
        preset = next((item for item in (presets or CUSTOM_CHECK_PRESETS) if item.get('id') == service_key), {})
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
    for preset in presets or CUSTOM_CHECK_PRESETS:
        add(preset.get('id'))
    return items


def _service_entries(service_key):
    source = SERVICE_LIST_SOURCES.get(service_key) or {}
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


def service_route_state(service_key, *, unblock_dir=UNBLOCK_DIR):
    try:
        entries = set(_service_state_entries(service_key))
    except ValueError:
        entries = set()
    total = len(entries)
    routes = {}
    complete = []
    partial = []
    for proto in ROUTE_ORDER:
        route = PROTOCOL_ROUTES[proto]
        route_entries = _read_route(route, unblock_dir)
        matched = len(entries & route_entries)
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


def service_route_summary(service_items, *, unblock_dir=UNBLOCK_DIR):
    return {
        item['id']: service_route_state(item['id'], unblock_dir=unblock_dir)
        for item in service_items or []
    }


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
    route_entries = {route: _read_route(route, unblock_dir) for route in PROTOCOL_ROUTES.values()}
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
    route_entries = {route: _read_route(route, unblock_dir) for route in PROTOCOL_ROUTES.values()}
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
    if callable(before_update):
        before_update()
    _run_update(update_script)
    return {
        'profile_id': profile_id,
        'profile_label': profile['label'],
        'services': len(results),
        'entries': sum(item.get('entries', 0) for item in results),
        'results': results,
    }
