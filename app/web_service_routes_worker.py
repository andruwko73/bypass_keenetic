import html
import json
import re
import sys

import custom_checks_store
import route_intersections
import service_routes
import web_route_tools_runtime
from app_version import APP_VERSION_LABEL


TELEGRAM_SVG_B64 = 'PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCA1MTIgNTEyIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxjaXJjbGUgY3g9IjI1NiIgY3k9IjI1NiIgcj0iMjU2IiBmaWxsPSIjMzdBRUUyIi8+PHBhdGggZD0iTTExOSAyNjVsMjY1LTEwNGMxMi01IDIzIDMgMTkgMTlsLTQ1IDIxMmMtMyAxMy0xMiAxNi0yNCAxMGwtNjYtNDktMzIgMzFjLTQgNC03IDctMTUgN2w2LTg1IDE1NS0xNDBjNy02LTItMTAtMTEtNGwtMTkyIDEyMS04My0yNmMtMTgtNi0xOC0xOCA0LTI2eiIgZmlsbD0iI2ZmZiIvPjwvc3ZnPg=='
YOUTUBE_SVG_B64 = 'PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCA0NDMgMzIwIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSI0NDMiIGhlaWdodD0iMzIwIiByeD0iNzAiIGZpbGw9IiNGRjAwMDAiLz48cG9seWdvbiBwb2ludHM9IjE3Nyw5NiAzNTUsMTYwIDE3NywyMjQiIGZpbGw9IiNmZmYiLz48L3N2Zz4='


def _telegram_icon_html(opacity=1.0):
    return _service_icon_html('telegram', 'Telegram', opacity=opacity, size=16)


def _youtube_icon_html(opacity=1.0):
    return _service_icon_html('youtube', 'YouTube', opacity=opacity, size=16)


def _service_icon_path(icon):
    icon = re.sub(r'[^a-z0-9_-]+', '', (icon or '').lower())
    if not icon:
        return ''
    return f'/static/service-icons/{icon}.png?v={APP_VERSION_LABEL}'


def _service_icon_html(icon, alt, opacity=1.0, size=18):
    src = _service_icon_path(icon)
    if not src:
        return ''
    safe_alt = html.escape(alt or icon)
    style = f'vertical-align:middle;opacity:{opacity:g}'
    return f'<img class="service-icon-img" src="{src}" width="{int(size)}" height="{int(size)}" alt="{safe_alt}" style="{style}">'


def _runtime():
    return web_route_tools_runtime.ServiceRouteToolsRuntime(
        custom_check_presets_getter=custom_checks_store.custom_check_presets,
        service_icon_html=_service_icon_html,
        telegram_icon_html=_telegram_icon_html,
        youtube_icon_html=_youtube_icon_html,
    )


def build_payload(runtime=None):
    custom_checks = custom_checks_store.load_custom_checks()
    runtime = runtime or _runtime()
    route_states = runtime.summary()
    return {
        'ok': True,
        'route_tools_html': runtime.tools_html(
            '',
            custom_checks,
            include_intersections=True,
            include_runtime_intersections=False,
        ),
        'route_states': service_routes.compact_route_summary(route_states),
    }


def execute_request(request):
    request = request if isinstance(request, dict) else {}
    action = str(request.get('action') or 'snapshot').strip().lower()
    if action == 'snapshot':
        return build_payload()
    if action == 'apply_service_route':
        result = service_routes.apply_service_route(
            str(request.get('service_key') or ''),
            str(request.get('target_protocol') or ''),
            update_script='',
        )
        return {'ok': True, 'result': result, 'apply_required': bool(result.get('changed'))}
    if action == 'apply_service_profile':
        runtime = _runtime()
        result = service_routes.apply_service_profile(
            str(request.get('profile_id') or ''),
            service_items=runtime.service_items(),
            update_script='',
        )
        return {'ok': True, 'result': result, 'apply_required': True}
    if action == 'resolve_route_intersections':
        result = route_intersections.resolve_route_intersections(
            str(request.get('target_route') or ''),
            update_script='',
        )
        return {'ok': True, 'result': result, 'apply_required': True}
    raise ValueError('Неизвестное действие worker маршрутов')


def main():
    try:
        request = json.load(sys.stdin)
    except Exception:
        request = {}
    try:
        payload = execute_request(request)
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
        return 0
    except Exception as exc:
        payload = {
            'ok': False,
            'error': str(exc),
            'error_type': type(exc).__name__,
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
