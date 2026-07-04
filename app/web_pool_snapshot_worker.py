import base64
import json
import os
import re
import sys
from urllib.parse import unquote, urlparse

import custom_checks_store
import key_pool_store
import key_pool_web
import probe_cache
import proxy_key_store
import service_routes


BOT_DIR = '/opt/etc/bot'
KEY_POOLS_PATH = os.path.join(BOT_DIR, 'key_pools.json')
XRAY_SERVICE_SCRIPT = '/opt/etc/init.d/S24xray'
XRAY_CONFIG_DIR = '/opt/etc/xray'
V2RAY_CONFIG_DIR = '/opt/etc/v2ray'
CORE_PROXY_CONFIG_DIR = XRAY_CONFIG_DIR if os.path.exists(XRAY_SERVICE_SCRIPT) else V2RAY_CONFIG_DIR
VMESS_KEY_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'vmess.key')
VLESS_KEY_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'vless.key')
VLESS2_KEY_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'vless2.key')
VMESS_URI_PREFIX = 'vmess' + '://'


def _parse_vmess_key(key_value):
    raw = str(key_value or '').strip()
    if raw.startswith(VMESS_URI_PREFIX):
        raw = raw[len(VMESS_URI_PREFIX):]
    try:
        decoded = base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)).decode('utf-8', errors='ignore')
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _pool_key_display_name(key_value):
    raw_key = str(key_value or '').strip()
    label = ''
    try:
        if raw_key.startswith(VMESS_URI_PREFIX):
            data = _parse_vmess_key(raw_key)
            label = str(data.get('ps') or data.get('add') or '').strip()
        else:
            parsed = urlparse(raw_key)
            label = unquote(parsed.fragment or '').strip()
            if not label and parsed.hostname:
                label = parsed.hostname
    except Exception:
        label = ''
    label = re.sub(r'\s+', ' ', label).strip()
    return label or 'Ключ прокси'


def _load_current_keys():
    return proxy_key_store.load_current_keys(
        VMESS_KEY_PATH,
        VLESS_KEY_PATH,
        VLESS2_KEY_PATH,
        XRAY_CONFIG_DIR,
        V2RAY_CONFIG_DIR,
    )


def _route_states(custom_checks, provided=None):
    if isinstance(provided, dict):
        return provided
    service_items = service_routes.route_service_items(presets=custom_checks_store.custom_check_presets())
    return service_routes.service_route_summary(service_items) if service_items or custom_checks else None


def build_payload(protocols=None, include_summary=False, include_custom_checks=False, route_states=None):
    custom_checks = custom_checks_store.load_custom_checks()
    route_states = _route_states(custom_checks, route_states)
    current_keys = _load_current_keys()
    key_pools = key_pool_store.load_key_pools(KEY_POOLS_PATH)
    key_pools, _changed = key_pool_store.ensure_current_keys_in_pools(key_pools, current_keys)
    cache = probe_cache.load_key_probe_cache()
    payload = {
        'pools': key_pool_web.web_pool_snapshot(
            current_keys,
            key_pools,
            cache,
            custom_checks,
            include_keys=False,
            hash_key=custom_checks_store.hash_key,
            display_name=_pool_key_display_name,
            probe_state=key_pool_web.web_probe_state,
            probe_checked_at=key_pool_web.web_probe_checked_at,
            protocols=protocols,
            route_states=route_states,
        ),
        'pool_summary': None,
        'custom_checks': None,
    }
    if include_summary:
        payload['pool_summary'] = key_pool_web.pool_status_summary(
            current_keys,
            key_pools,
            cache,
            custom_checks,
            custom_checks_store.hash_key,
            route_states=route_states,
        )
    if include_custom_checks:
        payload['custom_checks'] = key_pool_web.web_custom_checks(custom_checks)
    return payload


def _clean_protocols(value):
    result = []
    seen = set()
    for item in value or []:
        proto = str(item or '').strip()
        if proto in key_pool_web.POOL_PROTOCOL_ORDER and proto not in seen:
            seen.add(proto)
            result.append(proto)
    return result or None


def main():
    try:
        request = json.load(sys.stdin)
        protocols = _clean_protocols(request.get('protocols') if isinstance(request, dict) else None)
        payload = build_payload(
            protocols=protocols,
            include_summary=bool((request or {}).get('include_summary')),
            include_custom_checks=bool((request or {}).get('include_custom_checks')),
            route_states=(request or {}).get('route_states'),
        )
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
        return 0
    except Exception as exc:
        sys.stderr.write(f'{type(exc).__name__}: {exc}\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
