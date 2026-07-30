"""Compile user route-list entries into compact Xray transparent-route rules.

The Linux ipset remains a fast candidate selector.  These helpers provide the
second, application-layer check used by Xray when strict transparent routing is
enabled for a protocol.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse


SUPPORTED_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')
_DOMAIN_RE = re.compile(r'^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$')
_SUFFIX_PREFIXES = ('domain:', 'domain-suffix,', 'domain,', 'host-suffix,')

# Raw IP/CIDR records do not carry a hostname, therefore they are the one
# remaining ambiguous input to strict routing.  Limit them to ordinary
# application ports: a peer chosen by a torrent client normally uses an
# arbitrary high port and falls through to the direct route.
STRICT_TRANSPARENT_IP_PORTS = {
    'vmess': '80,443,5222',
    'vless': '80,443,5222',
    'vless2': '80,443',
}

def normalize_protocol_set(value, allowed=SUPPORTED_PROTOCOLS):
    """Return a stable set of configured protocol names.

    Router configuration historically accepts simple Python values, so both a
    comma-separated string and an iterable are deliberately supported.
    """
    if value is None:
        values = ()
    elif isinstance(value, str):
        values = re.split(r'[\s,;]+', value)
    else:
        try:
            values = tuple(value)
        except TypeError:
            values = ()
    allowed_values = {str(item).strip().lower() for item in allowed}
    return {
        str(item).strip().lower()
        for item in values
        if str(item).strip().lower() in allowed_values
    }


def _entry_value(value):
    return str(value or '').split('#', 1)[0].strip()


def _domain_token(value):
    token = _entry_value(value).lower().rstrip('.')
    if not token:
        return '', ''
    if token.startswith('full:'):
        return 'full', token[5:].lstrip('*.+').strip('/')
    for prefix in _SUFFIX_PREFIXES:
        if token.startswith(prefix):
            return 'domain', token[len(prefix):].lstrip('*.+').strip('/')
    if '://' in token:
        parsed = urlparse(token)
        token = (parsed.hostname or '').lower().rstrip('.')
    return 'domain', token.lstrip('*.+').strip('/')


def compile_route_entries(entries):
    """Split route-file entries into Xray domain and explicit IP matchers.

    Unsupported values are ignored rather than copied into Xray JSON.  ipset
    keeps processing the original list, so strict routing can always be turned
    off without changing list semantics.
    """
    domains = []
    addresses = []
    seen_domains = set()
    seen_addresses = set()
    for raw_value in entries or ():
        entry = _entry_value(raw_value)
        if not entry:
            continue
        try:
            address = str(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            address = ''
        if address:
            if address not in seen_addresses:
                seen_addresses.add(address)
                addresses.append(address)
            continue
        kind, domain = _domain_token(entry)
        if not _DOMAIN_RE.match(domain):
            continue
        rule_value = f'{kind}:{domain}'
        if rule_value not in seen_domains:
            seen_domains.add(rule_value)
            domains.append(rule_value)
    return {'domains': tuple(domains), 'ips': tuple(addresses)}


def compile_protocol_policies(entries_by_protocol, strict_protocols):
    """Return only policies requested by strict transparent routing."""
    requested = normalize_protocol_set(strict_protocols)
    source = entries_by_protocol or {}
    result = {}
    for protocol in requested:
        policy = compile_route_entries(source.get(protocol) or ())
        ip_ports = STRICT_TRANSPARENT_IP_PORTS.get(protocol)
        if ip_ports:
            policy['ip_ports'] = ip_ports
        result[protocol] = policy
    return result


def compile_unique_service_domain_override(entries_by_protocol, service_entries):
    """Route a service by sniffed domain when exactly one list fully owns it.

    The ipset layer can legitimately see the same Google edge IP for several
    domains.  A strict transparent inbound must therefore be able to recover
    the intended service route from TLS/HTTP sniffing instead of falling
    through to direct traffic merely because another ipset won the IP race.
    Explicit IP entries are deliberately excluded: they carry no hostname and
    remain under the existing ipset/TPROXY policy.
    """
    service_policy = compile_route_entries(service_entries)
    service_domains = tuple(service_policy.get('domains') or ())
    service_identities = {
        *service_domains,
        *(service_policy.get('ips') or ()),
    }
    if not service_domains or not service_identities:
        return {}

    source = entries_by_protocol or {}
    complete_owners = []
    for protocol in SUPPORTED_PROTOCOLS:
        route_policy = compile_route_entries(source.get(protocol) or ())
        route_identities = {
            *(route_policy.get('domains') or ()),
            *(route_policy.get('ips') or ()),
        }
        if service_identities <= route_identities:
            complete_owners.append(protocol)

    if len(complete_owners) != 1:
        return {}
    return {complete_owners[0]: {'domains': service_domains}}
