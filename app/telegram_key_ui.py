KEY_HELP_TEXT = 'Где брать ключи❔'
KEY_BROWSER_TEXT = '🌐 Через браузер'
KEY_COPY_PROMPT = '🔑 Скопируйте ключ сюда'

KEY_INPUT_LEVELS = {
    'Shadowsocks': 5,
    'Vmess': 9,
    'Vless': 11,
    'Vless 1': 11,
    'Vless 2': 12,
}

KEY_INSTALL_PROTOCOLS = {
    5: 'shadowsocks',
    9: 'vmess',
    11: 'vless',
    12: 'vless2',
}


def key_menu_rows(include_pool=False):
    help_row = (KEY_HELP_TEXT, '📦 Пул ключей') if include_pool else (KEY_HELP_TEXT,)
    return (
        ('Vless 1', 'Vless 2'),
        ('Vmess', 'Trojan'),
        ('Shadowsocks',),
        help_row,
        (KEY_BROWSER_TEXT,),
        ('🔙 Назад',),
    )


def key_input_level(text, trojan_level):
    if text == 'Trojan':
        return trojan_level
    return KEY_INPUT_LEVELS.get(text)


def key_install_protocol(level, trojan_level):
    if level == trojan_level:
        return 'trojan'
    return KEY_INSTALL_PROTOCOLS.get(level)


def browser_hint(router_ip, browser_port):
    return (
        f'Откройте в браузере: http://{router_ip}:{browser_port}/\n'
        'Введите ключ Shadowsocks, Vmess, Vless 1, Vless 2 или Trojan на странице.'
    )
