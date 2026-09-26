"""Route-scoped admission policy shared by Telegram and YouTube failover."""
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from protocol_catalog import PROTOCOL_ROUTE_NAMES
from transparent_route_policy import compile_route_entries

FAILURE_TTL = 300
MAX_CANDIDATES = 8


def service_label(service):
    return {'chatgpt_services': 'ChatGPT / Codex', 'discord': 'Discord',
            'meta': 'Instagram / Facebook', 'telegram': 'Telegram', 'youtube': 'YouTube',
            'budget': 'лимит времени'}.get(service, service)


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def check_signature(check):
    return signature({'id': check['id'], 'urls': check.get('urls') or [check.get('url', '')]})


def target_owners(target, policies):
    host = (urlsplit(target).hostname or '').lower().rstrip('.')
    owners = set()
    for proto, policy in policies.items():
        for token in policy['domains']:
            kind, domain = token.split(':', 1)
            if host == domain or (kind == 'domain' and host.endswith('.' + domain)):
                owners.add(proto)
                break
        try:
            import ipaddress
            address = ipaddress.ip_address(host)
            if any(address in ipaddress.ip_network(net) for net in policy['ips']):
                owners.add(proto)
        except ValueError:
            pass
    return owners


def build_contracts(checks, routes, *, telegram_proto='', youtube_proto=''):
    """Protect only enabled checks belonging to a route, never shared CDN IPs.

    Split checks retain only their route's endpoints. Ambiguous domain owners
    protect both possible routes instead of guessing which inbound wins.
    """
    from probe_cache import custom_checks_signature
    policies = {p: compile_route_entries(entries) for p, entries in routes.items()}
    result = {p: {'custom': [], 'telegram': p == telegram_proto,
                  'youtube': p == youtube_proto} for p in PROTOCOL_ROUTE_NAMES}
    for check in checks:
        targets = check.get('urls') or [check.get('url', '')]
        for proto in result:
            selected = [url for url in targets if proto in target_owners(url, policies)]
            if selected:
                item = dict(check, url=selected[0], urls=selected)
                result[proto]['custom'].append(item)
    revision = signature({'checks': checks, 'routes': {p: sorted(v) for p, v in routes.items()},
                          'telegram': telegram_proto, 'youtube': youtube_proto})
    for contract in result.values():
        contract['revision'] = revision
        contract['legacy_signature'] = custom_checks_signature(checks)
        contract['legacy_checks'] = {c['id']: check_signature(c) for c in checks}
    return result


def load_contracts(checks, *, telegram_proto='', youtube_proto='', unblock_dir='/opt/etc/unblock'):
    routes = {}
    for proto, route in PROTOCOL_ROUTE_NAMES.items():
        path = Path(unblock_dir, route + '.txt')
        try:
            routes[proto] = path.read_text(encoding='utf-8').splitlines()
        except FileNotFoundError:
            routes[proto] = []
    return build_contracts(checks, routes, telegram_proto=telegram_proto, youtube_proto=youtube_proto)


def recent_failure(entry, contract, *, now=None):
    now = time.time() if now is None else now
    for check in contract.get('custom', []):
        check_id = check['id']
        stamp = (entry.get('custom_times') or {}).get(check_id, 0)
        sig = (entry.get('custom_signatures') or {}).get(check_id)
        if not sig and entry.get('custom_sig') == contract.get('legacy_signature'):
            sig = (contract.get('legacy_checks') or {}).get(check_id)
            stamp = entry.get('custom_ts', 0)
        if (entry.get('custom') or {}).get(check_id) is False and sig == check_signature(check):
            try:
                stamp = float(stamp or 0)
            except (TypeError, ValueError):
                stamp = 0
            if stamp > 0 and 0 <= now - stamp < FAILURE_TTL:
                return check_id
    return ''


def check_required(proxy_url, contract, *, primary, check_telegram, check_http,
                   check_custom, timeouts=(2, 3), deadline=None, clock=time.monotonic):
    """Return tri-state verdict and results; unknown is never saved as a failure."""
    from proxy_status import is_transient_status_text
    from youtube_healthcheck import check_youtube_through_proxy
    values = {'custom': {}}
    def budget():
        return deadline is None or clock() < deadline
    def limits():
        remaining = max(0.2, deadline - clock()) if deadline is not None else sum(timeouts)
        return min(timeouts[0], remaining / 2), min(timeouts[1], remaining / 2)
    for service in ('telegram', 'youtube'):
        if service == primary or not contract.get(service):
            continue
        if not budget():
            return None, 'budget', values
        connect, read = limits()
        if service == 'telegram':
            ok, _ = check_telegram(proxy_url, connect_timeout=connect, read_timeout=read)
            values['tg_ok'] = ok
        else:
            ok, _ = check_youtube_through_proxy(check_http, proxy_url,
                http_timeouts=(connect, read), profile='pulse', retry_unstable=False)
            values['yt_ok'] = ok
        if ok is not True:
            return ok, service, values
    for check in contract.get('custom', []):
        verdict = False
        for url in check.get('urls') or [check['url']]:
            for attempt in range(2):
                if not budget():
                    return None, 'budget', values
                connect, read = limits()
                ok, message = check_custom(proxy_url, url, connect_timeout=connect, read_timeout=read)
                if ok is None:
                    return None, check['id'], values
                if ok or attempt or not is_transient_status_text(message):
                    break
            if ok:
                verdict = True
                break
        values['custom'][check['id']] = verdict
        if not verdict:
            return False, check['id'], values
    return True, '', values


def record_required(record, proto, key, contract, values, *, kind='screening'):
    kwargs = {k: v for k, v in values.items() if k != 'custom' and v is not None}
    custom = values.get('custom') or {}
    if custom:
        kwargs.update(custom=custom, custom_checks=[c for c in contract.get('custom', []) if c['id'] in custom])
    if kwargs:
        record(proto, key, verification_kind=kind, allow_recent_success_downgrade=True, **kwargs)
