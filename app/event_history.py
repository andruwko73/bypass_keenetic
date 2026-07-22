import json
import os
import re
import threading
import time
from collections import deque


EVENT_HISTORY_PATH = '/opt/etc/bot/event_history.jsonl'
MAX_EVENTS = 120
TRIM_EVERY_WRITES = 10
TRIM_SIZE_BYTES = 96 * 1024
_trim_write_counts = {}
_recent_event_lock = threading.Lock()
_recent_event_fingerprints = {}
MAX_RECENT_EVENT_FINGERPRINTS = 128
NEVER_DEDUPLICATE_ACTIONS = frozenset({'key_switch', 'key_switch_auto'})
DISPLAY_COMPACT_ACTIONS = frozenset({
    'stream_guard_defer',
    'udp_quic_drift_fast_add',
    'auto_failover_skip',
})

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
IP_REDACT_ACTION_PREFIXES = (
    'telegram_call_learning',
    'stream_guard',
    'udp_quic_drift',
)


def _action_redacts_ip(action):
    action_text = str(action or '')
    return any(action_text.startswith(prefix) for prefix in IP_REDACT_ACTION_PREFIXES)


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


def _compact_event_detail(action, key, value):
    key_text = str(key or '')
    if key_text == 'route_diagnostic' and isinstance(value, dict):
        ports = value.get('proxy_ports') or []
        proxy_samples = value.get('proxy_samples') or []
        fastnat_samples = value.get('fastnat_samples') or []
        return (
            f'proxy_ports={len(ports)}; '
            f'proxy_samples={len(proxy_samples)}; '
            f'fastnat_samples={len(fastnat_samples)}'
        )
    if key_text == 'route_diagnostic' and isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith('proxy_ports=') or stripped.startswith('route_diagnostic compacted;'):
            return stripped
        redacted = redact_sensitive_text(value)
        return (
            f'route_diagnostic compacted; '
            f'chars={len(redacted)}; '
            f'redacted_ip_markers={redacted.count("<ip-hidden>")}'
        )
    if key_text in ('proxy_samples', 'fastnat_samples') and isinstance(value, (list, tuple)):
        return f'{key_text}={len(value)}'
    if key_text == 'sample' and _action_redacts_ip(action):
        return _limit_text(value, 180, redact_ip=True)
    return value


def _event_fingerprint(event):
    return json.dumps(
        {
            'action': event.get('action') or '',
            'level': event.get('level') or '',
            'source': event.get('source') or '',
            'protocol': event.get('protocol') or '',
            'service': event.get('service') or '',
            'key_hash': event.get('key_hash') or '',
            'message': event.get('message') or '',
            'details': event.get('details') or {},
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    )


def _event_is_recent_duplicate(event, path, dedupe_seconds):
    try:
        window = max(0, int(dedupe_seconds or 0))
        timestamp = int(event.get('ts') or 0)
    except (TypeError, ValueError):
        return False
    if not window or event.get('action') in NEVER_DEDUPLICATE_ACTIONS:
        return False
    key = (str(path or ''), _event_fingerprint(event))
    with _recent_event_lock:
        previous = _recent_event_fingerprints.get(key)
        _recent_event_fingerprints[key] = timestamp
        if len(_recent_event_fingerprints) > MAX_RECENT_EVENT_FINGERPRINTS:
            _recent_event_fingerprints.pop(next(iter(_recent_event_fingerprints)), None)
    return previous is not None and timestamp >= previous and timestamp - previous < window


def _trim_history(path, max_events, *, force=False):
    if not force:
        _trim_write_counts[path] = int(_trim_write_counts.get(path, 0) or 0) + 1
        try:
            file_size = os.path.getsize(path)
        except Exception:
            file_size = 0
        if _trim_write_counts[path] % TRIM_EVERY_WRITES and file_size < TRIM_SIZE_BYTES:
            return
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
    _trim_write_counts[path] = 0
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
    dedupe_seconds=0,
    time_provider=time.time,
):
    path = _event_path(event_path)
    action_text = _limit_text(action, 80)
    redact_ip = _action_redacts_ip(action_text)
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
            _limit_text(key, 80): _limit_text(
                _compact_event_detail(action_text, key, value),
                220,
                redact_ip=redact_ip,
            )
            for key, value in details.items()
            if value is not None
        }
    if _event_is_recent_duplicate(event, path, dedupe_seconds):
        return True
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
    if not _action_redacts_ip(action_text):
        return event
    event['message'] = _limit_text(event.get('message', ''), 800, redact_ip=True)
    details = event.get('details')
    if isinstance(details, dict):
        event['details'] = {
            _limit_text(key, 80): _limit_text(
                _compact_event_detail(action_text, key, value),
                220,
                redact_ip=True,
            )
            for key, value in details.items()
            if value is not None
        }
    return event


def _display_compact_key(event):
    """Return the display group for noisy technical events, never key switches."""
    action = str(event.get('action') or '')
    if action not in DISPLAY_COMPACT_ACTIONS:
        return None
    details = event.get('details')
    reason = details.get('reason') if isinstance(details, dict) else ''
    return (
        action,
        str(event.get('source') or ''),
        _normalize_protocol(event.get('protocol')),
        str(event.get('service') or ''),
        str(reason or ''),
    )


def load_events(limit=50, *, event_path=None):
    path = _event_path(event_path)
    try:
        limit_value = max(1, int(limit or 50))
    except Exception:
        limit_value = 50
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as file:
            # The on-disk history is capped at MAX_EVENTS, so one bounded read can
            # compact every technical repeat before applying the display limit.
            lines = deque((line.strip() for line in file if line.strip()), maxlen=MAX_EVENTS)
    except Exception:
        return []
    events = []
    compacted = {}
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except Exception:
            continue
        if isinstance(event, dict):
            event = _redact_loaded_event(event)
            event['protocol_label'] = PROTOCOL_LABELS.get(event.get('protocol'), event.get('protocol') or 'Система')
            compact_key = _display_compact_key(event)
            if compact_key:
                previous = compacted.get(compact_key)
                if previous is not None:
                    previous['repeat_count'] = int(previous.get('repeat_count') or 1) + 1
                    continue
                event['repeat_count'] = 1
                compacted[compact_key] = event
            events.append(event)
        if len(events) >= limit_value:
            break
    return events


def _web_update_finish_failed(event):
    message = str((event or {}).get('message') or '').lower()
    failure_markers = (
        'error:',
        ' failed',
        'failed ',
        'traceback',
        'return_code=1',
        'command exited with code 1',
        'команда завершилась с кодом 1',
        'ошибка',
    )
    return any(marker in message for marker in failure_markers)


def _median_seconds(values):
    ordered = sorted(int(value) for value in values)
    count = len(ordered)
    if not count:
        return 0
    middle = count // 2
    if count % 2:
        return ordered[middle]
    return int(round((ordered[middle - 1] + ordered[middle]) / 2.0))


def estimate_update_duration(
    command='update',
    *,
    event_path=None,
    limit=300,
    default_seconds=240,
    min_seconds=30,
    max_seconds=900,
    min_samples=2,
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
            if min_seconds <= duration <= max_seconds and not _web_update_finish_failed(event):
                durations.append(duration)
    if not durations:
        return int(default_seconds), 0
    if len(durations) < int(min_samples or 1):
        return int(default_seconds), len(durations)
    recent = durations[-8:]
    if len(recent) >= 5:
        recent = sorted(recent)[1:-1]
    return _median_seconds(recent), len(durations)
