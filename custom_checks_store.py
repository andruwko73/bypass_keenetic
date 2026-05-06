import ipaddress
import json
import os
import re
from urllib.parse import urlparse

from service_catalog import CUSTOM_CHECK_PRESETS
from probe_cache import hash_key


CUSTOM_CHECKS_PATH = '/opt/etc/bot/custom_checks.json'
CUSTOM_CHECK_MAX = 12
CUSTOM_CHECK_REMOVED_IDS = {'mistral'}


def normalize_check_url(value):
    url = (value or '').strip()
    if not url:
        raise ValueError('Укажите адрес для проверки')
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', url):
        url = 'https://' + url
    parsed = urlparse(url)
    if parsed.scheme not in ['http', 'https'] or not parsed.netloc:
        raise ValueError('Адрес должен быть HTTP/HTTPS URL или доменом')
    return url


def route_entry_from_target(value):
    item = (value or '').strip().split('#', 1)[0].strip()
    if not item:
        return ''
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', item):
        parsed = urlparse(item)
        return (parsed.hostname or '').strip('.').lower()
    item = re.sub(r'^\+\.', '', item)
    item = re.sub(r'^\*\.', '', item)
    if '/' in item:
        try:
            return str(ipaddress.ip_network(item, strict=False))
        except ValueError:
            pass
    if '/' in item:
        parsed = urlparse('https://' + item)
        item = parsed.hostname or ''
    if ':' in item and item.count(':') == 1:
        host, port = item.rsplit(':', 1)
        if port.isdigit():
            item = host
    item = item.strip('.').lower()
    try:
        return str(ipaddress.ip_address(item))
    except ValueError:
        pass
    if re.match(r'^[a-z0-9_.-]+\.[a-z0-9_.-]+$', item):
        return item
    return ''


def route_entries_from_values(values):
    entries = []
    seen = set()
    for value in values or []:
        entry = route_entry_from_target(value)
        if entry and entry not in seen:
            seen.add(entry)
            entries.append(entry)
    return entries


def custom_check_id(label, url):
    base = re.sub(r'[^a-z0-9]+', '_', (label or '').lower()).strip('_')[:24]
    return base or ('target_' + hash_key(url)[:8])


def sanitize_custom_check(item):
    if not isinstance(item, dict):
        return None
    try:
        raw_urls = item.get('urls')
        if isinstance(raw_urls, list):
            urls = []
            for value in raw_urls:
                normalized = normalize_check_url(value)
                if normalized not in urls:
                    urls.append(normalized)
        else:
            urls = [normalize_check_url(item.get('url', ''))]
    except ValueError:
        return None
    if not urls:
        return None
    url = urls[0]
    label = str(item.get('label') or urlparse(url).netloc or url).strip()[:40]
    check_id = str(item.get('id') or custom_check_id(label, url)).strip()[:40]
    check_id = re.sub(r'[^a-zA-Z0-9_-]+', '_', check_id).strip('_') or custom_check_id(label, url)
    badge = str(item.get('badge') or label[:3] or 'WEB').strip().upper()[:5]
    result = {
        'id': check_id,
        'label': label,
        'url': url,
        'badge': badge,
    }
    if len(urls) > 1:
        result['urls'] = urls[:4]
    routes = route_entries_from_values(item.get('routes') or [])
    if routes:
        result['routes'] = routes[:80]
    if item.get('icon'):
        result['icon'] = str(item.get('icon'))[:24]
    return result


def load_custom_checks():
    try:
        with open(CUSTOM_CHECKS_PATH, 'r', encoding='utf-8') as file:
            value = json.load(file)
    except Exception:
        return []
    source = value.get('checks', []) if isinstance(value, dict) else value
    if not isinstance(source, list):
        return []
    result = []
    seen = set()
    for item in source:
        check = sanitize_custom_check(item)
        if not check:
            continue
        if check['id'] in CUSTOM_CHECK_REMOVED_IDS:
            continue
        unique_key = (check['id'], tuple(check.get('urls') or [check['url']]))
        if unique_key in seen:
            continue
        seen.add(unique_key)
        result.append(check)
        if len(result) >= CUSTOM_CHECK_MAX:
            break
    legacy_chatgpt_ids = {'chatgpt', 'codex', 'openai_api'}
    if any(item.get('id') in legacy_chatgpt_ids for item in result):
        result = [item for item in result if item.get('id') not in legacy_chatgpt_ids]
        if not any(item.get('id') == 'chatgpt_services' for item in result):
            preset = sanitize_custom_check(CUSTOM_CHECK_PRESETS[0])
            if preset:
                result.insert(0, preset)
    return result


def save_custom_checks(checks):
    result = []
    seen_ids = set()
    seen_urls = set()
    for item in checks or []:
        check = sanitize_custom_check(item)
        if not check:
            continue
        if check['id'] in CUSTOM_CHECK_REMOVED_IDS:
            continue
        urls_key = tuple(check.get('urls') or [check['url']])
        if check['id'] in seen_ids or urls_key in seen_urls:
            continue
        seen_ids.add(check['id'])
        seen_urls.add(urls_key)
        result.append(check)
        if len(result) >= CUSTOM_CHECK_MAX:
            break
    os.makedirs(os.path.dirname(CUSTOM_CHECKS_PATH), exist_ok=True)
    with open(CUSTOM_CHECKS_PATH, 'w', encoding='utf-8') as file:
        json.dump({'checks': result}, file, ensure_ascii=False, indent=2)
    return result


def custom_check_presets():
    return [dict(item) for item in CUSTOM_CHECK_PRESETS]


def add_custom_check(label='', url='', preset_id=''):
    checks = load_custom_checks()
    if len(checks) >= CUSTOM_CHECK_MAX:
        raise ValueError(f'Можно хранить не больше {CUSTOM_CHECK_MAX} дополнительных проверок')
    item = None
    if preset_id:
        for preset in CUSTOM_CHECK_PRESETS:
            if preset['id'] == preset_id:
                item = dict(preset)
                break
        if not item:
            raise ValueError('Неизвестный пресет проверки')
    else:
        item = {
            'label': (label or '').strip(),
            'url': (url or '').strip(),
        }
    check = sanitize_custom_check(item)
    if not check:
        raise ValueError('Не удалось добавить проверку: проверьте название и URL')
    for existing in checks:
        if existing['id'] == check['id'] or tuple(existing.get('urls') or [existing['url']]) == tuple(check.get('urls') or [check['url']]):
            return checks, f'Проверка "{check["label"]}" уже есть в списке.'
    checks.append(check)
    checks = save_custom_checks(checks)
    return checks, f'Проверка "{check["label"]}" добавлена.'


def delete_custom_check(check_id):
    check_id = (check_id or '').strip()
    checks = load_custom_checks()
    next_checks = [item for item in checks if item.get('id') != check_id]
    if len(next_checks) == len(checks):
        raise ValueError('Проверка не найдена')
    return save_custom_checks(next_checks)
