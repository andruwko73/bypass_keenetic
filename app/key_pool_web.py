import html
import time
from urllib.parse import urlparse

from web_status_builder import (
    pool_status_summary as build_pool_status_summary,
    youtube_probe_state,
)
from web_form_blocks import render_event_history_html


POOL_PROTOCOL_ORDER = ['vless', 'vless2', 'vmess', 'trojan', 'shadowsocks']
POOL_PROTOCOL_LABELS = {
    'vless': 'Vless 1',
    'vless2': 'Vless 2',
    'vmess': 'Vmess',
    'trojan': 'Trojan',
    'shadowsocks': 'Shadowsocks',
}
_ACTIVE_KEYS_TEXT = '\u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b\u043e\u0432 \u0441 \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u044b\u043c \u043a\u043b\u044e\u0447\u043e\u043c'
_POOL_TOTAL_TEXT = '\u0417\u0430\u043f\u0438\u0441\u0435\u0439 \u0432 \u043f\u0443\u043b\u0430\u0445'
_CHECKED_TEXT = '\u0421 \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u044b\u043c \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u043e\u043c'
def pool_proto_label(proto):
    return POOL_PROTOCOL_LABELS.get(proto, proto)


def _route_list_label(route):
    proto = 'vless2' if route == 'vless-2' else route
    return pool_proto_label(proto)


def _service_route_display_label(state):
    state = state if isinstance(state, dict) else {}
    routes = state.get('routes') if isinstance(state.get('routes'), dict) else {}
    parts = []
    for field, qualifier in (
        ('complete_protocols', 'полностью'),
        ('partial_protocols', 'частично'),
    ):
        protocols = state.get(field) if isinstance(state.get(field), list) else []
        for proto in protocols:
            route = routes.get(proto) if isinstance(routes.get(proto), dict) else {}
            try:
                matched = int(route.get('matched') or 0)
                total = int(route.get('total') or state.get('total') or 0)
            except (TypeError, ValueError):
                matched = 0
                total = 0
            coverage = f' {matched}/{total}' if total > 0 else ''
            parts.append(f'{pool_proto_label(proto)} — {qualifier}{coverage}')
    if parts:
        return '; '.join(parts)
    return str(state.get('label') or 'не добавлен')


def web_event_history_html(events):
    return render_event_history_html(events)


def service_applies_to_protocol(route_states, service_id, protocol):
    if not isinstance(route_states, dict):
        return True
    state = route_states.get(service_id)
    if not isinstance(state, dict):
        return True
    route_protocols = set(state.get('complete_protocols') or [])
    if not route_protocols:
        return False
    return str(protocol or '').strip() in route_protocols


def core_service_applicability(route_states, protocol):
    return {
        'telegram': service_applies_to_protocol(route_states, 'telegram', protocol),
        'youtube': service_applies_to_protocol(route_states, 'youtube', protocol),
    }


def core_services_for_protocol(route_states, protocol):
    applicability = core_service_applicability(route_states, protocol)
    return [
        service_id for service_id in ('telegram', 'youtube')
        if applicability.get(service_id, True)
    ]


def pool_status_summary(current_keys, key_pools, key_probe_cache, custom_checks, hash_key, route_states=None):
    return build_pool_status_summary(
        current_keys,
        key_pools,
        key_probe_cache,
        custom_checks,
        hash_key,
        protocol_order=POOL_PROTOCOL_ORDER,
        active_keys_text=_ACTIVE_KEYS_TEXT,
        pool_total_text=_POOL_TOTAL_TEXT,
        checked_text=_CHECKED_TEXT,
    )


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
            value = custom.get(check_id)
            if value is None:
                result[check_id] = 'unknown'
            else:
                result[check_id] = 'ok' if value else 'fail'
        else:
            result[check_id] = 'unknown'
    return result

def custom_check_applies_to_protocol(route_states, check_id, protocol):
    if not isinstance(route_states, dict):
        return True
    route_state = route_states.get(str(check_id or '').strip())
    if not isinstance(route_state, dict):
        return True
    complete_protocols = set(route_state.get('complete_protocols') or [])
    if complete_protocols:
        return str(protocol or '').strip() in complete_protocols
    return False


def protocol_custom_checks(custom_checks, route_states, protocol):
    if not custom_checks:
        return []
    if not isinstance(route_states, dict):
        return list(custom_checks or [])
    protocol = str(protocol or '').strip()
    result = []
    for check in custom_checks or []:
        check_id = str(check.get('id') or '').strip()
        if not check_id:
            continue
        if custom_check_applies_to_protocol(route_states, check_id, protocol):
            result.append(check)
    return result


def web_probe_state(probe, key):
    if key == 'yt_ok':
        return youtube_probe_state(probe)
    if not probe or key not in probe:
        return 'unknown'
    value = probe.get(key)
    if value is None:
        return 'unknown'
    if value is True:
        return 'ok'
    if value is False:
        return 'fail'
    return 'unknown'


def web_probe_checked_at(probe):
    try:
        ts = float((probe or {}).get('ts', 0))
    except (TypeError, ValueError):
        ts = 0
    if not ts:
        return ''
    return time.strftime('%d.%m %H:%M', time.localtime(ts))


def web_probe_quality_label(probe):
    if not isinstance(probe, dict):
        return ''
    try:
        throughput = float(probe.get('yt_throughput_mbps'))
    except Exception:
        throughput = 0.0
    if throughput <= 0:
        return ''
    quality = str(probe.get('yt_quality') or '').strip().lower()
    if quality == 'fast':
        return 'Быстро'
    if quality == 'stable':
        return 'Стабильно'
    return ''


def web_probe_quality_summary(probe):
    if not isinstance(probe, dict):
        return 'Качество еще не измерено'
    parts = []
    label = web_probe_quality_label(probe)
    if label:
        parts.append(f'YouTube: {label}')
    try:
        score = int(probe.get('yt_score'))
    except Exception:
        score = None
    if score is not None:
        parts.append(f'score {score}/100')
    stability = str(probe.get('yt_stability') or '').strip().lower()
    if stability and stability != 'stable':
        parts.append(f'YouTube {stability}')
    try:
        first_load = int(probe.get('yt_first_load_ms'))
    except Exception:
        first_load = 0
    if first_load:
        parts.append(f'first load {first_load} ms')
    try:
        error_rate = float(probe.get('yt_error_rate'))
    except Exception:
        error_rate = 0.0
    if error_rate:
        parts.append(f'errors {int(round(error_rate * 100))}%')
    tier = str(probe.get('yt_stream_tier') or '').strip() if label else ''
    if tier:
        parts.append(f'порог {tier}')
    try:
        tg_latency = int(probe.get('tg_latency_ms'))
    except Exception:
        tg_latency = 0
    if tg_latency:
        parts.append(f'Telegram {tg_latency} мс')
    try:
        yt_latency = int(probe.get('yt_latency_ms'))
    except Exception:
        yt_latency = 0
    if yt_latency:
        parts.append(f'YouTube {yt_latency} мс')
    try:
        googlevideo_latency = int(probe.get('googlevideo_latency_ms'))
    except Exception:
        googlevideo_latency = 0
    if googlevideo_latency:
        parts.append(f'Googlevideo {googlevideo_latency} мс')
    try:
        throughput = float(probe.get('yt_throughput_mbps'))
    except Exception:
        throughput = 0.0
    if throughput:
        parts.append(f'скорость {throughput:g} Мбит/с')
    error = str(probe.get('quality_error') or '').strip()
    if error:
        parts.append(f'замер скорости: {error}')
    yt_error = str(probe.get('yt_last_error') or '').strip()
    if yt_error:
        parts.append(f'YouTube check: {html.escape(yt_error)}')
    if not parts:
        return 'Качество еще не измерено'
    checked_at = web_probe_checked_at(probe)
    if checked_at:
        parts.append(f'проверено {checked_at}')
    return '; '.join(parts)


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








def web_custom_checks_html(custom_checks, service_icon_html, csrf_input_html='', empty_message='Дополнительные проверки пока не добавлены'):
    if not custom_checks:
        if not empty_message:
            return ''
        return f'<div class="custom-check-empty">{html.escape(empty_message)}</div>'
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





def web_service_route_tools_html(
    service_items,
    route_states,
    protocol_options,
    service_icon_html,
    csrf_input_html='',
    active_check_ids=None,
    core_icon_html=None,
):
    service_items = service_items or []
    if not service_items:
        return ''
    active_check_ids = set(active_check_ids or [])
    core_icon_html = core_icon_html or {}
    protocol_options = protocol_options or []
    cards = []
    for service in service_items:
        service_id = str(service.get('id') or '')
        safe_id = html.escape(service_id, quote=True)
        safe_label = html.escape(service.get('label') or service_id)
        state = route_states.get(service_id) or {}
        route_label = html.escape(_service_route_display_label(state))
        if service_id in core_icon_html:
            service_icon = (
                f'<span class="service-route-core-icon service-route-{html.escape(service_id, quote=True)}-icon">'
                f'{core_icon_html[service_id]}</span>'
            )
        else:
            service_icon = custom_check_icon_html(service, service_icon_html)
        selected_protocol = ''
        for field in ('complete_protocols', 'partial_protocols'):
            values = state.get(field) if isinstance(state.get(field), list) else []
            if values:
                selected_protocol = values[0]
                break
        add_check_input = ''
        is_custom_check = bool(service.get('is_custom_check'))
        check_is_active = service_id in active_check_ids
        if is_custom_check:
            check_status = 'Добавлена' if check_is_active else 'Добавится при выборе'
            if not check_is_active:
                add_check_input = '<input type="hidden" name="add_check" value="1">'
        else:
            check_status = 'Базовая'
        safe_check_status = html.escape(check_status)
        menu_items = []
        for item in protocol_options:
            value = html.escape(item['value'], quote=True)
            label = html.escape(item['label'])
            is_active = item['value'] == selected_protocol
            no_check_action = is_custom_check and not check_is_active
            status_label = 'текущий маршрут' if is_active and not no_check_action else 'перенести сюда'
            menu_items.append(
                f'''<form method="post" action="/service_route_apply" class="service-route-form" data-async-action="service-route">
                    {csrf_input_html}
                    <input type="hidden" name="service_key" value="{safe_id}">
                    {add_check_input}
                    <button type="submit" name="target_protocol" value="{value}" class="service-route-menu-item{' active' if is_active else ''}" role="menuitem" title="Перенести {safe_label} в {label}">
                        <span>{label}</span>
                        <small>{status_label}</small>
                    </button>
                </form>'''
            )
        check_menu_action = ''
        if is_custom_check and check_is_active:
            check_menu_action = f'''<form method="post" action="/custom_check_delete" class="service-route-form" data-async-action="custom-check-delete" data-confirm-title="Удалить проверку?" data-confirm-message="Удалить дополнительную проверку {safe_label}?">
                    {csrf_input_html}
                    <input type="hidden" name="id" value="{safe_id}">
                    <button type="submit" class="service-route-menu-item danger" role="menuitem" title="Удалить проверку {safe_label}">
                        <span>Удалить проверку</span>
                        <small>только из пула проверок</small>
                    </button>
                </form>'''
        cards.append(f'''<div class="service-route-card" data-service-route-id="{safe_id}">
            <details class="service-route-menu">
                <summary class="service-route-trigger" aria-label="Выбрать список обхода для {safe_label}">
                    <span class="service-route-title">
                        {service_icon}
                        <span><strong>{safe_label}</strong><small>Маршрут: {route_label} · {safe_check_status}</small></span>
                    </span>
                    <span class="service-route-caret" aria-hidden="true">v</span>
                </summary>
                <div class="service-route-menu-list" role="menu" aria-label="Списки обхода для {safe_label}">
                    {''.join(menu_items)}
                    {check_menu_action}
                </div>
            </details>
        </div>''')
    return f'''<div class="service-route-tools">
        <div class="route-section-head">
            <strong>Сервисы и маршруты</strong>
            <small>В одной карточке видно, через какой список идёт сервис, и добавлена ли его проверка в пул</small>
        </div>
        <div class="service-route-grid">{''.join(cards)}</div>
    </div>'''


def web_route_profiles_html(profiles, csrf_input_html=''):
    profiles = profiles or []
    if not profiles:
        return ''
    buttons = []
    for profile in profiles:
        safe_id = html.escape(profile.get('id', ''), quote=True)
        safe_label = html.escape(profile.get('label', 'Профиль'))
        safe_description = html.escape(profile.get('description', ''))
        buttons.append(f'''<form method="post" action="/service_profile_apply" data-async-action="service-route">
            {csrf_input_html}
            <input type="hidden" name="profile_id" value="{safe_id}">
            <button type="submit" class="route-profile-btn" title="{safe_description}">
                <span>{safe_label}</span>
            </button>
        </form>''')
    return f'''<div class="route-profile-panel">
        <div class="route-section-head">
            <strong>Быстрые сценарии маршрутов</strong>
            <small>Профиль переносит только известные адреса сервисов из каталога</small>
        </div>
        <div class="route-profile-grid">{''.join(buttons)}</div>
    </div>'''


def _allowed_shared_entries_html(report, *, clean=False):
    report = report or {}
    count = int(report.get('allowed_shared_count') or 0)
    if count <= 0:
        return ''
    rows = []
    for item in (report.get('allowed_shared_entries') or []):
        entry = html.escape(str(item.get('entry') or ''))
        entry_type = {
            'domain': 'домен',
            'ip': 'IP-адрес',
            'cidr': 'IP-сеть',
        }.get(str(item.get('entry_type') or ''), 'адрес')
        routes = [str(route or '') for route in (item.get('routes') or []) if route]
        files = [str(value or '') for value in (item.get('files') or []) if value]
        if not files:
            files = [f'{route}.txt' for route in routes]
        services = [str(value or '') for value in (item.get('services') or []) if value]
        route_entries = item.get('route_entries') if isinstance(item.get('route_entries'), dict) else {}
        route_rows = []
        for route in routes:
            raw_entries = route_entries.get(route) if isinstance(route_entries.get(route), list) else []
            if not raw_entries:
                raw_entries = [item.get('entry') or '']
            raw_html = ' · '.join(
                f'<code>{html.escape(str(raw_entry or ""))}</code>'
                for raw_entry in raw_entries
                if str(raw_entry or '').strip()
            )
            if not raw_html:
                continue
            route_rows.append(
                '<span class="route-shared-file-row">'
                f'<strong>{html.escape(f"{route}.txt")}</strong>{raw_html}'
                '</span>'
            )
        route_text = ', '.join(_route_list_label(route) for route in routes)
        service_text = ', '.join(services) if services else 'сервис не распознан по каталогу'
        rows.append(f'''<li class="route-shared-entry">
            <span class="route-shared-address"><span>{html.escape(entry_type)}:</span><code>{entry}</code></span>
            <small>Файлы: {html.escape(', '.join(files))}</small>
            <small>Маршруты: {html.escape(route_text)} · Сервисы: {html.escape(service_text)}</small>
            <span class="route-shared-file-list">{''.join(route_rows)}</span>
        </li>''')
    shown = len(rows)
    truncated = bool(report.get('allowed_shared_truncated')) or count > shown
    truncated_html = (
        f'<small class="route-shared-truncated">Показаны первые {shown} из {count} общих записей</small>'
        if truncated else ''
    )
    open_attr = ' open' if count <= 8 else ''
    heading = 'Конфликтных пересечений не найдено' if clean else f'Разрешённые общие записи: {count}'
    return f'''<div class="route-intersection-card route-intersection-ok route-shared-card">
        <div>
            <strong>{heading}</strong>
            <small>Общие адреса каталогов могут находиться в нескольких файлах и не считаются конфликтом</small>
            <details class="route-shared-details"{open_attr}>
                <summary>Общие адреса: {count}</summary>
                <ul>{''.join(rows)}</ul>
                {truncated_html}
            </details>
        </div>
    </div>'''


def web_route_intersections_html(report, protocol_options, csrf_input_html=''):
    report = report or {}
    count = int(report.get('count') or 0)
    file_count = int(report.get('file_count') if report.get('file_count') is not None else count)
    shared_html = _allowed_shared_entries_html(report, clean=count <= 0)
    if count <= 0:
        if shared_html:
            return shared_html
        return '''<div class="route-intersection-card route-intersection-ok">
            <strong>Конфликтных пересечений и общих записей не найдено</strong>
            <small>Файлы обхода не содержат несовместимых доменов или пересекающихся IP-сетей</small>
        </div>'''
    examples = []
    for issue in (report.get('issues') or [])[:8]:
        message = html.escape(issue.get("message") or issue.get("entry") or "")
        routes = ', '.join(issue.get('routes') or [])
        services = ', '.join(issue.get('services') or [])
        service_text = services if services else 'сервис не распознан по каталогу'
        samples = ', '.join((issue.get('samples') or issue.get('entries') or [])[:3])
        samples_html = f'<small>Адреса: {html.escape(samples)}</small>' if samples else ''
        examples.append(f'''<li>
            <strong>{message}</strong>
            <small>Списки: {html.escape(routes)} · Сервис: {html.escape(service_text)}</small>
            {samples_html}
        </li>''')
    examples_html = f'<ul>{"".join(examples)}</ul>' if examples else ''
    runtime_note = ''
    if int(report.get('runtime_count') or 0) and not file_count:
        runtime_note = '<small>Файлы списков уже могут быть чистыми; пересечение найдено только в загруженных ipset, обновите маршруты.</small>'
    auto_note = ''
    auto_resolved = report.get('auto_resolved') or {}
    auto_applied = auto_resolved.get('applied') or []
    if auto_applied:
        labels = []
        for item in auto_applied[:4]:
            service_label = item.get('service_label') or item.get('service_key') or ''
            target_label = item.get('target_label') or item.get('target_protocol') or ''
            if service_label and target_label:
                labels.append(f'{service_label} -> {target_label}')
        if labels:
            auto_note = f'<small>Автоматически применено: {html.escape(", ".join(labels))}</small>'
    auto_pending = report.get('auto_resolve_pending') or {}
    auto_status = str(auto_pending.get('status') or '').strip()
    if auto_pending and not auto_note:
        if auto_status in ('scheduled', 'running'):
            auto_note = '<small>Автоматическое исправление известных пересечений запущено в фоне. Обновите проверку через минуту.</small>'
    if int(report.get('runtime_count') or 0) and not file_count and auto_status in ('scheduled', 'running'):
        return f'''<div class="route-intersection-card route-intersection-warn">
            <div>
                <strong>Маршруты применяются</strong>
                <small>Файлы списков уже очищены, загруженные ipset обновляются в фоне. Пересечения исчезнут после завершения refresh.</small>
                {auto_note}
            </div>
        </div>{shared_html}'''
    buttons = []
    for item in ((protocol_options or []) if file_count else []):
        route_value = 'vless-2' if item['value'] == 'vless2' else item['value']
        buttons.append(f'''<form method="post" action="/route_intersections_resolve" data-async-action="service-route" data-confirm-title="Перенести пересечения?" data-confirm-message="Все найденные пересекающиеся адреса будут оставлены только в списке {html.escape(item['label'])}.">
            {csrf_input_html}
            <input type="hidden" name="target_route" value="{html.escape(route_value, quote=True)}">
            <button type="submit" class="outline-button">{html.escape(item['label'])}</button>
        </form>''')
    conflict_html = f'''<div class="route-intersection-card route-intersection-warn">
        <div>
            <strong>Найдены конфликтные пересечения списков: {count}</strong>
            <small>Это может отправлять один сервис через разные ключи и вызывать обрывы</small>
            {runtime_note}
            {auto_note}
            {examples_html}
        </div>
        <div class="route-intersection-actions">
            {''.join(buttons)}
        </div>
    </div>'''
    return conflict_html + shared_html


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
    protocols=None,
    route_states=None,
):
    current_keys = current_keys or {}
    pools = pools or {}
    cache = cache or {}
    result = {}
    protocol_order = [
        proto for proto in (protocols or POOL_PROTOCOL_ORDER)
        if proto in POOL_PROTOCOL_ORDER
    ]
    for proto in protocol_order:
        current_key = current_keys.get(proto, '')
        core_services = core_services_for_protocol(route_states, proto)
        protocol_checks = protocol_custom_checks(custom_checks, route_states, proto)
        rows = []
        for index, key_value in enumerate(pools.get(proto, []) or [], start=1):
            key_hash = hash_key(key_value)
            probe = cache.get(key_hash, {})
            tg_state = web_probe_state(probe, 'tg_ok')
            yt_state = web_probe_state(probe, 'yt_ok')
            quality_label = web_probe_quality_label(probe)
            row = {
                'index': index,
                'key_id': key_hash[:12],
                'display_name': display_name(key_value),
                'active': bool(current_key and key_value == current_key),
                'tg': tg_state,
                'yt': yt_state,
                'custom': web_custom_probe_states(probe, protocol_checks),
                'checked_at': probe_checked_at(probe),
                'checked_ts': int(probe.get('ts') or 0) if isinstance(probe, dict) else 0,
                'yt_score': int(probe.get('yt_score') or 0) if quality_label and isinstance(probe, dict) else 0,
                'yt_quality': str(probe.get('yt_quality') or '') if quality_label and isinstance(probe, dict) else '',
                'yt_quality_label': quality_label,
                'yt_stream_tier': str(probe.get('yt_stream_tier') or '') if quality_label and isinstance(probe, dict) else '',
                'quality_summary': web_probe_quality_summary(probe),
            }
            if include_keys:
                row['key'] = key_value
            rows.append(row)
        result[proto] = {
            'label': pool_proto_label(proto),
            'count': len(rows),
            'core_services': core_services,
            'custom_checks': web_custom_checks(protocol_checks),
            'rows': rows,
        }
    return result
