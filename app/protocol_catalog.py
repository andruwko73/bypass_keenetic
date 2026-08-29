"""Shared metadata for proxy protocols exposed by the application."""


PROTOCOL_DISPLAY_ORDER = (
    'vless',
    'vless2',
    'vmess',
    'trojan',
    'hysteria2',
    'shadowsocks',
)

PROTOCOL_LABELS = {
    'vless': 'Vless 1',
    'vless2': 'Vless 2',
    'vmess': 'Vmess',
    'trojan': 'Trojan',
    'hysteria2': 'Hysteria2',
    'shadowsocks': 'Shadowsocks',
}

PROTOCOL_URI_SCHEMES = {
    'vless': ('vless',),
    'vless2': ('vless',),
    'vmess': ('vmess',),
    'trojan': ('trojan',),
    'hysteria2': ('hysteria2', 'hy2'),
    'shadowsocks': ('ss',),
}

SCHEME_PROTOCOLS = {
    'ss': 'shadowsocks',
    'vmess': 'vmess',
    'trojan': 'trojan',
    'hysteria2': 'hysteria2',
    'hy2': 'hysteria2',
}

SUPPORTED_KEY_SCHEMES = frozenset(('vless',) + tuple(SCHEME_PROTOCOLS))

PROTOCOL_FORM_SECTIONS = (
    ('vless', 'Vless 1', 6, 'vless://...'),
    ('vless2', 'Vless 2', 6, 'vless://...'),
    ('vmess', 'Vmess', 6, 'vmess://...'),
    ('trojan', 'Trojan', 5, 'trojan://...'),
    ('hysteria2', 'Hysteria2', 5, 'hysteria2:' + '//... или hy2:' + '//...'),
    ('shadowsocks', 'Shadowsocks', 5, 'ss://...'),
)

PROTOCOL_ROUTE_NAMES = {
    'vless': 'vless',
    'vless2': 'vless-2',
    'vmess': 'vmess',
    'trojan': 'trojan',
    'hysteria2': 'hysteria2',
    'shadowsocks': 'shadowsocks',
}

PROTOCOL_KEY_FILENAMES = {
    'vmess': 'vmess.key',
    'vless': 'vless.key',
    'vless2': 'vless2.key',
    'hysteria2': 'hysteria2.key',
}


def protocol_label(proto, default=None):
    return PROTOCOL_LABELS.get(str(proto or ''), default if default is not None else str(proto or ''))


def protocol_for_scheme(scheme, default=''):
    scheme = str(scheme or '').strip().casefold()
    if scheme == 'vless':
        return default if default in ('vless', 'vless2') else 'vless'
    return SCHEME_PROTOCOLS.get(scheme, default)
