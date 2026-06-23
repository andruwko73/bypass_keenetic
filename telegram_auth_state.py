import re


MENU_STATE_UNSET = object()
SENSITIVE_MESSAGE_TEXT_PATTERNS = (
    (re.compile(r'\b(?:vless|vmess|trojan|ss)://[^\s\'"<>]+', re.I), '<proxy-key-hidden>'),
    (re.compile(r'\b\d{6,}:[A-Za-z0-9_-]{20,}\b'), '<bot-token-hidden>'),
    (re.compile(r'https?://[^\s\'"<>]+', re.I), '<url-hidden>'),
    (re.compile(r'((?:token|password|passwd|secret|credential|subscription)\s*[=:]\s*)[^\s\'"]+', re.I), r'\1<hidden>'),
)


def normalize_username(value):
    if value is None:
        return ''
    normalized = str(value).strip()
    if normalized.startswith('@'):
        normalized = normalized[1:]
    return normalized.casefold()


def build_authorized_identities(raw_values):
    if isinstance(raw_values, (str, int)):
        values = [raw_values]
    else:
        values = list(raw_values or [])

    normalized_usernames = set()
    numeric_ids = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        if text.lstrip('-').isdigit():
            try:
                numeric_ids.add(int(text))
                continue
            except ValueError:
                pass
        normalized = normalize_username(text)
        if normalized:
            normalized_usernames.add(normalized)
    return normalized_usernames, numeric_ids


def get_chat_menu_state(lock, states, chat_id):
    with lock:
        state = states.get(chat_id)
        if state is None:
            state = {'level': 0, 'bypass': None}
            states[chat_id] = state
        return dict(state)


def set_chat_menu_state(lock, states, chat_id, level=MENU_STATE_UNSET, bypass=MENU_STATE_UNSET):
    with lock:
        state = states.get(chat_id)
        if state is None:
            state = {'level': 0, 'bypass': None}
            states[chat_id] = state
        if level is not MENU_STATE_UNSET:
            state['level'] = level
        if bypass is not MENU_STATE_UNSET:
            state['bypass'] = bypass


def _redact_message_debug_text(text):
    redacted = str(text or '')
    for pattern, replacement in SENSITIVE_MESSAGE_TEXT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def message_debug_text(message):
    text = getattr(message, 'text', None)
    if text is None:
        return '<non-text>'
    text = str(text).replace('\r', ' ').replace('\n', ' ')
    text = _redact_message_debug_text(text)
    if len(text) > 120:
        return text[:117] + '...'
    return text


def authorize_message(message, handler_name, authorized_usernames, authorized_user_ids, log_callback=None):
    user = getattr(message, 'from_user', None)
    chat = getattr(message, 'chat', None)
    user_id = getattr(user, 'id', None)
    username = getattr(user, 'username', None)
    normalized_username = normalize_username(username)
    chat_id = getattr(chat, 'id', None)
    chat_type = getattr(chat, 'type', None)

    authorized = False
    reason = 'unauthorized'
    if user_id in authorized_user_ids:
        authorized = True
        reason = 'user_id'
    elif normalized_username and normalized_username in authorized_usernames:
        authorized = True
        reason = 'username'
    elif not normalized_username:
        reason = 'missing_username'

    if log_callback:
        log_callback(
            f'handler={handler_name} chat_id={chat_id} chat_type={chat_type} '
            f'user_id={user_id} username={username!r} authorized={authorized} '
            f'reason={reason} text={message_debug_text(message)}'
        )
    return authorized, reason


def unauthorized_message_text(reason):
    if reason == 'missing_username':
        return 'У вашего Telegram-аккаунта не задан username. Задайте username в настройках Telegram и повторите команду.'
    return 'Вы не являетесь автором канала'


def callback_as_message(call):
    proxy = type('CallbackMessageProxy', (), {})()
    proxy.from_user = getattr(call, 'from_user', None)
    proxy.chat = getattr(getattr(call, 'message', None), 'chat', None)
    proxy.text = getattr(call, 'data', '')
    return proxy
