import re


POOL_PAGE_SIZE = 1000
POOL_PROTOCOL_BUTTON_PREFIXES = {
    'shadowsocks': 'SS',
    'vmess': 'VM',
    'vless': 'V1',
    'vless2': 'V2',
    'trojan': 'TR',
}
TELEGRAM_BUTTON_ICON = 'TG'
YOUTUBE_BUTTON_ICON = 'YT'

_BACK = '\U0001f519 \u041d\u0430\u0437\u0430\u0434'
_KEY_MENU = '\U0001f519 \u0412 \u043c\u0435\u043d\u044e \u043a\u043b\u044e\u0447\u0435\u0439'
_BACK_TO_PROTO = '\U0001f519 \u041a \u0432\u044b\u0431\u043e\u0440\u0443 \u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b\u0430'
_BACK_TO_POOL = '\U0001f519 \u041a \u043f\u0443\u043b\u0443'


def pool_proto_button_prefix(proto):
    return POOL_PROTOCOL_BUTTON_PREFIXES.get(proto, str(proto or '').upper())


def pool_proto_from_button_prefix(prefix):
    value = (prefix or '').strip().upper()
    for proto, proto_prefix in POOL_PROTOCOL_BUTTON_PREFIXES.items():
        if value == proto_prefix.upper():
            return proto
    return None


def shorten_button_text(text, limit=38):
    value = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(value) <= limit:
        return value
    return value[:max(1, limit - 1)].rstrip() + '\u2026'


def _button(types, label):
    return types.KeyboardButton(label)


def _markup(types):
    return types.ReplyKeyboardMarkup(resize_keyboard=True)


def add_page_controls(types, markup, info):
    if info['total_pages'] <= 1:
        return
    previous_button = '\u041a\u043b\u044e\u0447\u0438 \u25c0\ufe0f' if info['page'] > 0 else '\xb7'
    next_button = '\u041a\u043b\u044e\u0447\u0438 \u25b6\ufe0f' if info['page'] < info['total_pages'] - 1 else '\xb7'
    page_button = f'\u0421\u0442\u0440. {info["page"] + 1}/{info["total_pages"]}'
    markup.row(_button(types, previous_button), _button(types, page_button), _button(types, next_button))


def pool_protocol_markup(types, protocol_labels):
    markup = _markup(types)
    buttons = [_button(types, label) for label in protocol_labels]
    markup.row(buttons[0], buttons[1])
    markup.row(buttons[2], buttons[3])
    markup.row(buttons[4])
    markup.row(_button(types, _KEY_MENU), _button(types, _BACK))
    return markup


def pool_action_markup(types, key_labels, info):
    markup = _markup(types)
    for label in key_labels:
        markup.row(_button(types, label))
    add_page_controls(types, markup, info)
    markup.row(
        _button(types, '\u2795 \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043a\u043b\u044e\u0447\u0438'),
        _button(types, '\U0001f517 \u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c subscription'),
    )
    markup.row(
        _button(types, '\U0001f50d \u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043f\u0443\u043b'),
        _button(types, '\U0001f9f9 \u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u043f\u0443\u043b'),
    )
    markup.row(
        _button(types, '\U0001f5d1 \u0423\u0434\u0430\u043b\u0435\u043d\u0438\u0435'),
        _button(types, '\U0001f504 \u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u043f\u0443\u043b'),
    )
    markup.row(_button(types, _BACK_TO_PROTO), _button(types, _KEY_MENU))
    markup.row(_button(types, _BACK))
    return markup


def pool_delete_markup(types, key_labels, info):
    markup = _markup(types)
    for label in key_labels:
        markup.row(_button(types, label))
    add_page_controls(types, markup, info)
    markup.row(_button(types, _BACK_TO_POOL), _button(types, _BACK))
    return markup


def pool_clear_confirm_markup(types):
    markup = _markup(types)
    markup.row(
        _button(types, '\u2705 \u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u043f\u0443\u043b'),
        _button(types, '\u041e\u0442\u043c\u0435\u043d\u0430'),
    )
    markup.row(_button(types, _BACK_TO_POOL), _button(types, _BACK))
    return markup


def pool_input_markup(types):
    markup = _markup(types)
    markup.row(_button(types, _BACK_TO_POOL), _button(types, _BACK))
    return markup


def pool_probe_text(probe):
    if not isinstance(probe, dict) or not probe:
        return '\u043d\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u043b\u0441\u044f'
    badges = []
    if probe.get('tg_ok') is True:
        badges.append(f'{TELEGRAM_BUTTON_ICON}\u2705')
    elif probe.get('tg_ok') is False:
        badges.append(f'{TELEGRAM_BUTTON_ICON}\u274c')
    if probe.get('yt_ok') is True:
        badges.append(f'{YOUTUBE_BUTTON_ICON}\u2705')
    elif probe.get('yt_ok') is False:
        badges.append(f'{YOUTUBE_BUTTON_ICON}\u274c')
    if not badges:
        return '\u043d\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u043b\u0441\u044f'
    return ' '.join(badges)


def pool_probe_button_text(probe):
    if not isinstance(probe, dict) or not probe:
        return f'{TELEGRAM_BUTTON_ICON}? {YOUTUBE_BUTTON_ICON}?'
    tg = (
        f'{TELEGRAM_BUTTON_ICON}\u2705'
        if probe.get('tg_ok') is True
        else (f'{TELEGRAM_BUTTON_ICON}\u274c' if probe.get('tg_ok') is False else f'{TELEGRAM_BUTTON_ICON}?')
    )
    yt = (
        f'{YOUTUBE_BUTTON_ICON}\u2705'
        if probe.get('yt_ok') is True
        else (f'{YOUTUBE_BUTTON_ICON}\u274c' if probe.get('yt_ok') is False else f'{YOUTUBE_BUTTON_ICON}?')
    )
    return f'{tg} {yt}'


def pool_key_button_label(index, key_value, probe=None, current_key=None, proto=None, action='apply', display_name=str):
    key_name = shorten_button_text(display_name(key_value), limit=24)
    status = pool_probe_button_text(probe)
    proto_prefix = pool_proto_button_prefix(proto)
    if action == 'delete':
        prefix = f'\u2715 {proto_prefix} {index}.'
    elif current_key and key_value == current_key:
        prefix = f'\u2705 {proto_prefix} {index}.'
    else:
        prefix = f'{proto_prefix} {index}.'
    return shorten_button_text(f'{prefix} {key_name} {status}', limit=52)


def pool_key_line(index, key_value, probe=None, current_key=None, display_name=str, hash_key=str):
    marker = ' \u2014 \u0410\u041a\u0422\u0418\u0412\u0415\u041d' if current_key and key_value == current_key else ''
    key_name = display_name(key_value)
    key_hash = hash_key(key_value)[:8]
    return f'{index}. {key_name}{marker} [{key_hash}] \u2014 {pool_probe_text(probe)}'
