import os
import posixpath
import time
from urllib.parse import parse_qs


PAGE_ROUTES = ('/', '/index.html', '/command')


def _ctx(ctx, name, default=None):
    return ctx.get(name, default)


def _call(ctx, name, *args, **kwargs):
    func = _ctx(ctx, name)
    if not func:
        return None
    return func(*args, **kwargs)


def _pool_probe_running(progress):
    try:
        total = int((progress or {}).get('total') or 0)
    except Exception:
        total = 0
    return bool((progress or {}).get('running')) and total > 0


def _requested_protocols(params):
    raw_values = []
    for name in ('protocols', 'protocol', 'proto'):
        raw_values.extend(params.get(name, []))
    protocols = []
    seen = set()
    for item in ','.join(str(value or '') for value in raw_values).split(','):
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            protocols.append(item)
    return protocols or None


def _status_payload(ctx):
    now = _ctx(ctx, 'time_provider', time.time)()
    cache_ttl = float(_ctx(ctx, 'status_api_cache_ttl', 0) or 0)
    pool_enabled = _ctx(ctx, 'pool_enabled', False)
    progress = _ctx(ctx, 'get_pool_probe_progress', lambda: {})() if pool_enabled else {}
    pool_probe_running = _pool_probe_running(progress)
    cache_getter = _ctx(ctx, 'get_status_api_cache')
    if cache_ttl > 0 and cache_getter and not pool_probe_running:
        cached = cache_getter()
        if (
            isinstance(cached, dict) and
            cached.get('payload') is not None and
            now - float(cached.get('timestamp') or 0) < cache_ttl
        ):
            return cached['payload']

    current_keys = _ctx(ctx, 'load_current_keys')()
    snapshot = _ctx(ctx, 'cached_status_snapshot')(current_keys)
    if snapshot is None:
        active_snapshot = _ctx(ctx, 'active_mode_status_snapshot')
        if active_snapshot:
            snapshot = active_snapshot(current_keys)
            pool_probe_locked = _ctx(ctx, 'pool_probe_locked', lambda: False)
            if not pool_probe_locked():
                _call(ctx, 'refresh_status_caches_async', current_keys)
        else:
            snapshot = {
                'web': _ctx(ctx, 'placeholder_web_status_snapshot')(),
                'protocols': _ctx(ctx, 'placeholder_protocol_statuses')(current_keys),
            }
    if _ctx(ctx, 'refresh_status_on_api', False):
        _call(ctx, 'refresh_status_caches_async', current_keys)

    payload = {
        'web': snapshot.get('web', {}) if isinstance(snapshot, dict) else {},
        'protocols': snapshot.get('protocols', {}) if isinstance(snapshot, dict) else {},
        'router_health': _ctx(ctx, 'router_health_snapshot', lambda: {})(),
    }
    if not pool_enabled:
        payload.update({
            'custom_checks': [],
            'pool_summary': {'active_text': '', 'note': ''},
            'pool_probe_running': False,
            'pool_probe_progress': {},
        })
        return payload

    payload.update({
        'pool_summary': _ctx(ctx, 'pool_status_summary')(current_keys),
        'pool_probe_running': pool_probe_running,
        'pool_probe_progress': progress,
        'timestamp': now,
    })
    cache_store = _ctx(ctx, 'store_status_api_cache')
    if cache_ttl > 0 and cache_store and not pool_probe_running:
        cache_store(payload, now)
    return payload


def _pools_payload(ctx, query=''):
    if not _ctx(ctx, 'pool_enabled', False):
        return {
            'pools': {},
            'pool_summary': {'active_text': '', 'note': ''},
            'custom_checks': [],
            'timestamp': _ctx(ctx, 'time_provider', time.time)(),
        }
    params = parse_qs(query or '', keep_blank_values=True)
    include_keys = str((params.get('include_keys') or [''])[0]).lower() in ('1', 'true', 'yes')
    protocols = _requested_protocols(params)
    current_keys = _ctx(ctx, 'load_current_keys')()
    return {
        'pools': _ctx(ctx, 'web_pool_snapshot')(current_keys, include_keys=include_keys, protocols=protocols),
        'pool_summary': _ctx(ctx, 'pool_status_summary')(current_keys),
        'custom_checks': _ctx(ctx, 'web_custom_checks')(),
        'timestamp': _ctx(ctx, 'time_provider', time.time)(),
    }


def _pool_probe_payload(ctx):
    progress = _ctx(ctx, 'get_pool_probe_progress')()
    running = _pool_probe_running(progress)
    return {
        'status': 'running' if running else 'idle',
        'running': running,
        'progress': progress,
    }


def _static_file(ctx, path):
    static_dir = _ctx(ctx, 'static_dir')
    if not static_dir:
        return None
    if path == '/static/telegram.png':
        return os.path.join(static_dir, 'telegram.png')
    if path == '/static/youtube.png':
        return os.path.join(static_dir, 'youtube.png')
    if _ctx(ctx, 'service_icons_enabled', False) and path.startswith('/static/service-icons/'):
        icon_name = posixpath.basename(path)
        return os.path.join(static_dir, 'service-icons', icon_name)
    return None


def _protocol_panel_payload(ctx, query):
    params = parse_qs(query or '', keep_blank_values=True)
    protocol = (params.get('proto') or [''])[0]
    build_protocol_panel = _ctx(ctx, 'build_protocol_panel')
    if not protocol or not build_protocol_panel:
        return {'ok': False, 'error': 'Неизвестный протокол'}
    try:
        panel_html = build_protocol_panel(protocol)
    except ValueError as exc:
        return {'ok': False, 'error': str(exc)}
    return {'ok': True, 'protocol': protocol, 'html': panel_html}


def dispatch(ctx, path, query=''):
    if path in PAGE_ROUTES:
        build_form = _ctx(ctx, 'build_form')
        consume_flash_message = _ctx(ctx, 'consume_flash_message')
        return {'kind': 'html', 'html': build_form(consume_flash_message())}
    if path == '/static/app.css':
        return {
            'kind': 'text',
            'text': _call(ctx, 'build_style_asset') or '',
            'content_type': 'text/css; charset=utf-8',
            'cache_seconds': 86400,
        }
    if path == '/static/app.js':
        return {
            'kind': 'text',
            'text': _call(ctx, 'build_script_asset') or '',
            'content_type': 'application/javascript; charset=utf-8',
            'cache_seconds': 86400,
        }
    if path == '/api/status':
        return {'kind': 'json', 'payload': _status_payload(ctx), 'status': 200}
    if path == '/api/pools' and _ctx(ctx, 'pool_enabled', False):
        return {'kind': 'json', 'payload': _pools_payload(ctx, query), 'status': 200}
    if path == '/api/command_state':
        return {'kind': 'json', 'payload': _ctx(ctx, 'get_web_command_state')(), 'status': 200}
    if path == '/api/pool_probe' and _ctx(ctx, 'pool_enabled', False):
        return {'kind': 'json', 'payload': _pool_probe_payload(ctx), 'status': 200}
    if path == '/api/protocol_panel' and _ctx(ctx, 'pool_enabled', False):
        payload = _protocol_panel_payload(ctx, query)
        return {'kind': 'json', 'payload': payload, 'status': 200 if payload.get('ok') else 400}

    filepath = _static_file(ctx, path)
    if filepath:
        return {'kind': 'png', 'path': filepath}
    return None
