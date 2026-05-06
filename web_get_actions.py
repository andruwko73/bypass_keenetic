import os
import posixpath
import time


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


def _status_payload(ctx):
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
    }
    if not _ctx(ctx, 'pool_enabled', False):
        payload.update({
            'custom_checks': [],
            'pool_summary': {'active_text': '', 'note': ''},
            'pool_probe_running': False,
            'pool_probe_progress': {},
        })
        return payload

    progress = _ctx(ctx, 'get_pool_probe_progress')()
    payload.update({
        'pools': _ctx(ctx, 'web_pool_snapshot')(current_keys),
        'pool_summary': _ctx(ctx, 'pool_status_summary')(current_keys),
        'custom_checks': _ctx(ctx, 'web_custom_checks')(),
        'pool_probe_running': _pool_probe_running(progress),
        'pool_probe_progress': progress,
        'timestamp': _ctx(ctx, 'time_provider', time.time)(),
    })
    return payload


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


def dispatch(ctx, path):
    if path in PAGE_ROUTES:
        build_form = _ctx(ctx, 'build_form')
        consume_flash_message = _ctx(ctx, 'consume_flash_message')
        return {'kind': 'html', 'html': build_form(consume_flash_message())}
    if path == '/api/status':
        return {'kind': 'json', 'payload': _status_payload(ctx), 'status': 200}
    if path == '/api/command_state':
        return {'kind': 'json', 'payload': _ctx(ctx, 'get_web_command_state')(), 'status': 200}
    if path == '/api/pool_probe' and _ctx(ctx, 'pool_enabled', False):
        return {'kind': 'json', 'payload': _pool_probe_payload(ctx), 'status': 200}

    filepath = _static_file(ctx, path)
    if filepath:
        return {'kind': 'png', 'path': filepath}
    return None
