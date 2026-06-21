import json
import os
import re
import time


EVENT_HISTORY_PATH = '/opt/etc/bot/event_history.jsonl'
MAX_EVENTS = 300

PROTOCOL_LABELS = {
    'shadowsocks': 'Shadowsocks',
    'vmess': 'Vmess',
    'vless': 'Vless 1',
    'vless2': 'Vless 2',
    'vless-2': 'Vless 2',
    'trojan': 'Trojan',
    'web-only': 'Web only',
    'none': 'Без прокси',
    'system': 'Система',
}

SECRET_PATTERNS = [
    (re.compile(r'\b(?:vless|vmess|trojan|ss)://[^\s\'"<>]+', re.I), '<proxy-key-hidden>'),
    (re.compile(r'\bbot\d{6,}:[A-Za-z0-9_-]{20,}\b'), 'bot<token-hidden>'),
    (re.compile(r'((?:token|password|secret|passwd|web_auth_token)\s*[=:]\s*)[^\s\'"]+', re.I), r'\1<hidden>'),
]
IPV4_PATTERN = re.compile(
    r'\b(?:25[0-5]|2[0-4]\d|1?\d?\d)'
    r'(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b'
)


def redact_sensitive_text(value):
    text = '' if value is None else str(value)
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _event_path(path=None):
    return path or EVENT_HISTORY_PATH


def _normalize_protocol(protocol):
    protocol = str(protocol or 'system').strip().lower()
    if protocol == 'vless-2':
        return 'vless2'
    return protocol or 'system'


def _limit_text(value, max_len=800, redact_ip=False):
    text = redact_sensitive_text(value)
    if redact_ip:
        text = IPV4_PATTERN.sub('<ip-hidden>', text)
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + '...'


def _trim_history(path, max_events):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as file:
            lines = [line for line in file if line.strip()]
    except FileNotFoundError:
        return
    except Exception:
        return
    max_events = max(1, int(max_events or MAX_EVENTS))
    if len(lines) <= max_events:
        return
    tmp_path = path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as file:
            file.writelines(lines[-max_events:])
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception:
            pass


def record_event(
    *,
    action,
    message='',
    level='info',
    source='system',
    protocol='system',
    service='',
    key_hash='',
    details=None,
    event_path=None,
    max_events=MAX_EVENTS,
    time_provider=time.time,
):
    path = _event_path(event_path)
    action_text = _limit_text(action, 80)
    redact_ip = action_text.startswith('telegram_call_learning')
    event = {
        'ts': int(time_provider()),
        'level': _limit_text(level, 40),
        'action': action_text,
        'source': _limit_text(source, 80),
        'protocol': _normalize_protocol(protocol),
        'service': _limit_text(service, 120),
        'key_hash': _limit_text(key_hash, 80),
        'message': _limit_text(message, 800, redact_ip=redact_ip),
        'details': {},
    }
    if isinstance(details, dict):
        event['details'] = {
            _limit_text(key, 80): _limit_text(value, 300, redact_ip=redact_ip)
            for key, value in details.items()
            if value is not None
        }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a', encoding='utf-8') as file:
            file.write(json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n')
        _trim_history(path, max_events)
    except Exception:
        return False
    return True


def _redact_loaded_event(event):
    if not isinstance(event, dict):
        return event
    action_text = _limit_text(event.get('action'), 80)
    if not action_text.startswith('telegram_call_learning'):
        return event
    event['message'] = _limit_text(event.get('message', ''), 800, redact_ip=True)
    details = event.get('details')
    if isinstance(details, dict):
        event['details'] = {
            _limit_text(key, 80): _limit_text(value, 300, redact_ip=True)
            for key, value in details.items()
            if value is not None
        }
    return event


def load_events(limit=50, *, event_path=None):
    path = _event_path(event_path)
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as file:
            lines = [line.strip() for line in file if line.strip()]
    except Exception:
        return []
    events = []
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except Exception:
            continue
        if isinstance(event, dict):
            event = _redact_loaded_event(event)
            event['protocol_label'] = PROTOCOL_LABELS.get(event.get('protocol'), event.get('protocol') or 'Система')
            events.append(event)
        if len(events) >= int(limit or 50):
            break
    return events


def estimate_update_duration(
    command='update',
    *,
    event_path=None,
    limit=300,
    default_seconds=180,
    min_seconds=30,
    max_seconds=900,
):
    events = list(reversed(load_events(limit=limit, event_path=event_path)))
    durations = []
    current_start = None
    for event in events:
        if event.get('source') != 'web' or event.get('service') != command:
            continue
        action = event.get('action')
        try:
            ts = int(event.get('ts') or 0)
        except Exception:
            ts = 0
        if ts <= 0:
            continue
        if action == 'web_command_start':
            current_start = ts
            continue
        if action == 'web_command_finish' and current_start:
            duration = ts - current_start
            current_start = None
            if min_seconds <= duration <= max_seconds:
                durations.append(duration)
    if not durations:
        return int(default_seconds), 0
    recent = durations[-8:]
    if len(recent) >= 5:
        recent = sorted(recent)[1:-1]
    return int(round(sum(recent) / float(len(recent)))), len(durations)
