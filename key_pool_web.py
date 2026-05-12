import html
import time
from urllib.parse import urlparse


POOL_PROTOCOL_ORDER = ['vless', 'vless2', 'vmess', 'trojan', 'shadowsocks']
POOL_PROTOCOL_LABELS = {
    'vless': 'Vless 1',
    'vless2': 'Vless 2',
    'vmess': 'Vmess',
    'trojan': 'Trojan',
    'shadowsocks': 'Shadowsocks',
}

_ACTIVE_KEYS_TEXT = '\u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043a\u043b\u044e\u0447\u0435\u0439'
_POOL_TOTAL_TEXT = '\u0412 \u043f\u0443\u043b\u0430\u0445'
_CHECKED_TEXT = '\u041f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043e'
_ALL_SERVICES_TEXT = '\u0412\u0441\u0435 \u0441\u0435\u0440\u0432\u0438\u0441\u044b'
_ANY_SERVICE_TEXT = '\u0425\u043e\u0442\u044f \u0431\u044b \u043e\u0434\u0438\u043d'


def pool_proto_label(proto):
    return POOL_PROTOCOL_LABELS.get(proto, proto)


def _service_counter(custom_checks):
    services = [
        {'label': 'Telegram', 'field': 'tg_ok', 'id': None, 'count': 0},
        {'label': 'YouTube', 'field': 'yt_ok', 'id': None, 'count': 0},
    ]
    for check in custom_checks or []:
        check_id = str(check.get('id') or '').strip()
        if not check_id:
            continue
        label = str(check.get('label') or check_id).strip() or check_id
        if len(label) > 18:
            label = label[:18] + '...'
        services.append({'label': label, 'field': None, 'id': check_id, 'count': 0})
    return services


def pool_status_summary(current_keys, key_pools, key_probe_cache, custom_checks, hash_key):
    current_keys = current_keys or {}
    key_pools = key_pools or {}
    key_probe_cache = key_probe_cache or {}
    services = _service_counter(custom_checks)

    total_count = 0
    checked_count = 0
    all_services_count = 0
    any_service_count = 0
    for proto in POOL_PROTOCOL_ORDER:
        for pool_key in key_pools.get(proto, []) or []:
            total_count += 1
            probe = key_probe_cache.get(hash_key(pool_key), {})
            if not isinstance(probe, dict):
                probe = {}
            custom = probe.get('custom', {})
            if not isinstance(custom, dict):
                custom = {}
            results = []
            for service in services:
                if service['field']:
                    if service['field'] not in probe:
                        continue
                    ok = bool(probe.get(service['field']))
                else:
                    if service['id'] not in custom:
                        continue
                    ok = bool(custom.get(service['id']))
                results.append(ok)
                if ok:
                    service['count'] += 1
            if len(results) == len(services):
                checked_count += 1
            if results and any(results):
                any_service_count += 1
            if len(results) == len(services) and all(results):
                all_services_count += 1

    active_key_count = sum(1 for proto in POOL_PROTOCOL_ORDER if (current_keys.get(proto) or '').strip())
    service_text = '. '.join(f"{service['label']}: {service['count']}" for service in services)
    note_parts = [
        f'{_POOL_TOTAL_TEXT}: {total_count}',
        f'{_CHECKED_TEXT}: {checked_count}',
    ]
    if service_text:
        note_parts.append(service_text)
    note_parts.append(f'{_ALL_SERVICES_TEXT}: {all_services_count}')
    note_parts.append(f'{_ANY_SERVICE_TEXT}: {any_service_count}')
    note = '. '.join(note_parts) + '.'
    return {
        'active_key_count': active_key_count,
        'protocol_count': len(POOL_PROTOCOL_ORDER),
        'active_text': f'{active_key_count} / {len(POOL_PROTOCOL_ORDER)} {_ACTIVE_KEYS_TEXT}',
        'note': note,
        'pool_total_count': total_count,
        'checked_pool_count': checked_count,
        'all_services_count': all_services_count,
        'any_service_count': any_service_count,
        'services': [{'label': service['label'], 'count': service['count']} for service in services],
    }


def web_custom_probe_states(probe, custom_checks):
    custom = (probe or {}).get('custom', {})
    if not isinstance(custom, dict):
        custom = {}
    result = {}
    for check in custom_checks or []:
        check_id = check.get('id')
        if not check_id:
            continue
        if check_id in custom:
            result[check_id] = 'ok' if custom.get(check_id) else 'fail'
        else:
            result[check_id] = 'unknown'
    return result


def web_probe_state(probe, key):
    if not probe or key not in probe:
        return 'unknown'
    value = probe.get(key)
    if value is None:
        return 'unknown'
    return 'ok' if value else 'fail'


def web_probe_checked_at(probe):
    try:
        ts = float((probe or {}).get('ts', 0))
    except (TypeError, ValueError):
        ts = 0
    if not ts:
        return ''
    return time.strftime('%d.%m %H:%M', time.localtime(ts))


def web_custom_checks(custom_checks):
    return [
        {
            'id': check.get('id', ''),
            'label': check.get('label', ''),
            'url': check.get('url', ''),
            'urls': check.get('urls') or [check.get('url', '')],
            'routes': check.get('routes') or [],
            'badge': check.get('badge', 'WEB'),
            'icon': check.get('icon', ''),
        }
        for check in custom_checks or []
    ]


def custom_check_url_text(check):
    urls = check.get('urls') if isinstance(check.get('urls'), list) else [check.get('url', '')]
    labels = []
    for url in urls:
        if not url:
            continue
        parsed = urlparse(url)
        label = parsed.netloc or url
        if parsed.path and parsed.path != '/':
            label += parsed.path
        labels.append(label)
    return ', '.join(labels)


def custom_check_icon_html(check, service_icon_html):
    if check.get('icon'):
        return f'<span class="preset-icon">{service_icon_html(check.get("icon"), check.get("label", "Service"), opacity=1.0, size=20)}</span>'
    return f'<span class="custom-service-badge custom-service-neutral">{html.escape(check.get("badge", "WEB"))}</span>'


def custom_check_status_icon_html(check, state, service_icon_html):
    if state == 'ok':
        return service_icon_html(check.get('icon'), check.get('label', 'Service'), opacity=1.0, size=18)
    if state == 'fail':
        return '<span class="service-probe-mark service-probe-fail">\u2715</span>'
    return '<span class="service-probe-mark service-probe-unknown">?</span>'


def custom_check_header_icons(custom_checks, service_icon_html):
    icons = []
    for check in custom_checks or []:
        label = check.get('label', 'Service')
        safe_label = html.escape(label)
        if check.get('icon'):
            content = service_icon_html(check.get('icon'), label, opacity=1.0, size=16)
        else:
            content = f'<span class="custom-service-badge custom-service-neutral">{html.escape(check.get("badge", "WEB"))}</span>'
        icons.append(f'<span class="custom-service-slot custom-service-header" title="{safe_label}">{content}</span>')
    return ''.join(icons)


def web_custom_check_badges(probe, custom_checks, service_icon_html):
    if not custom_checks:
        return ''
    states = web_custom_probe_states(probe, custom_checks)
    badges = []
    for check in custom_checks:
        state = states.get(check.get('id'), 'unknown')
        safe_label = html.escape(check.get('label', '\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430'))
        safe_url = html.escape(custom_check_url_text(check))
        badges.append(
            f'<span class="custom-service-slot custom-service-{state}" title="{safe_label}: {safe_url}">{custom_check_status_icon_html(check, state, service_icon_html)}</span>'
        )
    return ''.join(badges)


def web_custom_checks_html(custom_checks, service_icon_html, csrf_input_html=''):
    if not custom_checks:
        return '<div class="custom-check-empty">\u0414\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438 \u043f\u043e\u043a\u0430 \u043d\u0435 \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u044b.</div>'
    items = []
    for check in custom_checks:
        safe_id = html.escape(check.get('id', ''))
        safe_label = html.escape(check.get('label', '\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430'))
        safe_url = html.escape(custom_check_url_text(check))
        items.append(f'''<div class="custom-check-item">
            {custom_check_icon_html(check, service_icon_html)}
            <span class="custom-check-copy"><strong>{safe_label}</strong><small>{safe_url}</small></span>
            <form method="post" action="/custom_check_delete" data-async-action="custom-check-delete" data-confirm-title="\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443?" data-confirm-message="\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0434\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u0443\u044e \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443 {safe_label}?">
                {csrf_input_html}
                <input type="hidden" name="id" value="{safe_id}">
                <button type="submit" class="pool-delete-btn" title="\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443">\u0423\u0434\u0430\u043b\u0438\u0442\u044c</button>
            </form>
        </div>''')
    return ''.join(items)


def web_custom_presets_html(custom_checks, presets, service_icon_html, csrf_input_html=''):
    active_ids = {check.get('id') for check in custom_checks or []}
    items = []
    for preset in presets or []:
        safe_id = html.escape(preset['id'])
        safe_label = html.escape(preset['label'])
        safe_url = html.escape(preset.get('url', ''))
        disabled = ' disabled' if preset['id'] in active_ids else ''
        title = '\u0423\u0436\u0435 \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u043e' if disabled else f'\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443 {safe_label}'
        items.append(f'''<form method="post" action="/custom_check_add" data-async-action="custom-check-add">
            {csrf_input_html}
            <input type="hidden" name="preset" value="{safe_id}">
            <input type="hidden" name="label" value="{safe_label}">
            <input type="hidden" name="url" value="{safe_url}">
            <button type="submit" class="service-preset-btn"{disabled} data-custom-preset="{safe_id}" title="{html.escape(title)}">
                {custom_check_icon_html(preset, service_icon_html)}
                <span>{safe_label}</span>
            </button>
        </form>''')
    return ''.join(items)


def web_pool_snapshot(
    current_keys,
    pools,
    cache,
    custom_checks,
    *,
    include_keys,
    hash_key,
    display_name,
    probe_state,
    probe_checked_at,
):
    current_keys = current_keys or {}
    pools = pools or {}
    cache = cache or {}
    result = {}
    for proto in POOL_PROTOCOL_ORDER:
        current_key = current_keys.get(proto, '')
        rows = []
        for index, key_value in enumerate(pools.get(proto, []) or [], start=1):
            probe = cache.get(hash_key(key_value), {})
            row = {
                'index': index,
                'key_id': hash_key(key_value)[:12],
                'display_name': display_name(key_value),
                'active': bool(current_key and key_value == current_key),
                'tg': probe_state(probe, 'tg_ok'),
                'yt': probe_state(probe, 'yt_ok'),
                'custom': web_custom_probe_states(probe, custom_checks),
                'checked_at': probe_checked_at(probe),
                'checked_ts': int(probe.get('ts') or 0) if isinstance(probe, dict) else 0,
            }
            if include_keys:
                row['key'] = key_value
            rows.append(row)
        result[proto] = {
            'label': pool_proto_label(proto),
            'count': len(rows),
            'rows': rows,
        }
    return result
