#!/usr/bin/python3

#  2023. Keenetic DNS bot /  Проект: bypass_keenetic / Автор: tas_unn
#  GitHub: https://github.com/tas-unn/bypass_keenetic
#  Web-only версия (Telegram bot удалён)
#
#  Файл: web_bot.py, Версия 2.2.1

import subprocess
import os
import ipaddress
import re
import stat
import sys
import time
import threading
import signal
import traceback
import gc
import tarfile
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
import key_pool_store
from service_catalog import (
    CHATGPT_ROUTE_ENTRIES,
    CLAUDE_ROUTE_ENTRIES,
    CONNECTIVITY_CHECK_DOMAINS,
    CUSTOM_CHECK_PRESETS,
    DISCORD_ROUTE_ENTRIES,
    GROK_ROUTE_ENTRIES,
    SERVICE_LIST_SOURCES,
    TELEGRAM_UNBLOCK_ENTRIES,
    YOUTUBE_UNBLOCK_ENTRIES,
)
from pool_probe_runner import run_pool_probe_worker
from web_form_template import render_web_form

import base64
import shutil
# import datetime
import requests
import json
import html
import bot_config as config

# --- Пул ключей и авто-фейловер Telegram API ---
KEY_POOLS_PATH = '/opt/etc/bot/key_pools.json'
KEY_PROBE_CACHE_PATH = '/opt/etc/bot/key_probe_cache.json'
CUSTOM_CHECKS_PATH = '/opt/etc/bot/custom_checks.json'
AUTO_FAILOVER_GRACE_SECONDS = 60
AUTO_FAILOVER_POLL_SECONDS = 10
AUTO_FAILOVER_SWITCH_COOLDOWN_SECONDS = int(getattr(config, 'auto_failover_switch_cooldown_seconds', 180))
auto_failover_state = {
    'last_ok': 0.0,
    'last_fail': 0.0,
    'last_attempt': 0.0,
    'in_progress': False,
}
key_probe_cache_lock = threading.Lock()


def _hash_key(value):
    import hashlib
    return hashlib.sha1((value or '').encode('utf-8', errors='ignore')).hexdigest()


def _load_key_probe_cache():
    try:
        with open(KEY_PROBE_CACHE_PATH, 'r', encoding='utf-8') as f:
            value = json.load(f)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _save_key_probe_cache(cache):
    os.makedirs(os.path.dirname(KEY_PROBE_CACHE_PATH), exist_ok=True)
    tmp_path = f'{KEY_PROBE_CACHE_PATH}.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp_path, KEY_PROBE_CACHE_PATH)








CUSTOM_CHECK_MAX = 12
CUSTOM_CHECK_REMOVED_IDS = {'mistral'}


def _normalize_check_url(value):
    url = (value or '').strip()
    if not url:
        raise ValueError('Укажите адрес для проверки')
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', url):
        url = 'https://' + url
    parsed = urlparse(url)
    if parsed.scheme not in ['http', 'https'] or not parsed.netloc:
        raise ValueError('Адрес должен быть HTTP/HTTPS URL или доменом')
    return url


def _route_entry_from_target(value):
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


def _route_entries_from_values(values):
    entries = []
    seen = set()
    for value in values or []:
        entry = _route_entry_from_target(value)
        if entry and entry not in seen:
            seen.add(entry)
            entries.append(entry)
    return entries


def _custom_check_id(label, url):
    base = re.sub(r'[^a-z0-9]+', '_', (label or '').lower()).strip('_')[:24]
    return base or ('target_' + _hash_key(url)[:8])


def _sanitize_custom_check(item):
    if not isinstance(item, dict):
        return None
    try:
        raw_urls = item.get('urls')
        if isinstance(raw_urls, list):
            urls = []
            for value in raw_urls:
                normalized = _normalize_check_url(value)
                if normalized not in urls:
                    urls.append(normalized)
        else:
            urls = [_normalize_check_url(item.get('url', ''))]
    except ValueError:
        return None
    if not urls:
        return None
    url = urls[0]
    label = str(item.get('label') or urlparse(url).netloc or url).strip()[:40]
    check_id = str(item.get('id') or _custom_check_id(label, url)).strip()[:40]
    check_id = re.sub(r'[^a-zA-Z0-9_-]+', '_', check_id).strip('_') or _custom_check_id(label, url)
    badge = str(item.get('badge') or label[:3] or 'WEB').strip().upper()[:5]
    result = {
        'id': check_id,
        'label': label,
        'url': url,
        'badge': badge,
    }
    if len(urls) > 1:
        result['urls'] = urls[:4]
    routes = _route_entries_from_values(item.get('routes') or [])
    if routes:
        result['routes'] = routes[:80]
    if item.get('icon'):
        result['icon'] = str(item.get('icon'))[:24]
    return result


def _load_custom_checks():
    try:
        with open(CUSTOM_CHECKS_PATH, 'r', encoding='utf-8') as f:
            value = json.load(f)
    except Exception:
        return []
    source = value.get('checks', []) if isinstance(value, dict) else value
    if not isinstance(source, list):
        return []
    result = []
    seen = set()
    for item in source:
        check = _sanitize_custom_check(item)
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
            preset = _sanitize_custom_check(CUSTOM_CHECK_PRESETS[0])
            if preset:
                result.insert(0, preset)
    return result


def _save_custom_checks(checks):
    result = []
    seen_ids = set()
    seen_urls = set()
    for item in checks or []:
        check = _sanitize_custom_check(item)
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
    with open(CUSTOM_CHECKS_PATH, 'w', encoding='utf-8') as f:
        json.dump({'checks': result}, f, ensure_ascii=False, indent=2)
    return result


def _custom_check_presets():
    return [dict(item) for item in CUSTOM_CHECK_PRESETS]


def _add_custom_check(label='', url='', preset_id=''):
    checks = _load_custom_checks()
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
    check = _sanitize_custom_check(item)
    if not check:
        raise ValueError('Не удалось добавить проверку: проверьте название и URL')
    for existing in checks:
        if existing['id'] == check['id'] or tuple(existing.get('urls') or [existing['url']]) == tuple(check.get('urls') or [check['url']]):
            return checks, f'Проверка "{check["label"]}" уже есть в списке.'
    checks.append(check)
    checks = _save_custom_checks(checks)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return checks, f'Проверка "{check["label"]}" добавлена.'


def _delete_custom_check(check_id):
    check_id = (check_id or '').strip()
    checks = _load_custom_checks()
    next_checks = [item for item in checks if item.get('id') != check_id]
    if len(next_checks) == len(checks):
        raise ValueError('Проверка не найдена')
    checks = _save_custom_checks(next_checks)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return checks


def _record_key_probe(proto, key_value, tg_ok=None, yt_ok=None, custom=None):
    with key_probe_cache_lock:
        cache = _load_key_probe_cache()
        key_id = _hash_key(key_value)
        entry = cache.get(key_id, {})
        if not isinstance(entry, dict):
            entry = {}
        entry['proto'] = proto
        entry['ts'] = time.time()
        if tg_ok is not None:
            if tg_ok == 'unknown':
                entry['tg_ok'] = None
            else:
                entry['tg_ok'] = bool(tg_ok)
        if yt_ok is not None:
            if yt_ok == 'unknown':
                entry['yt_ok'] = None
            else:
                entry['yt_ok'] = bool(yt_ok)
        if custom is not None:
            existing_custom = entry.get('custom', {})
            if not isinstance(existing_custom, dict):
                existing_custom = {}
            for check_id, ok in (custom or {}).items():
                existing_custom[str(check_id)] = bool(ok)
            entry['custom'] = existing_custom
        cache[key_id] = entry
        _save_key_probe_cache(cache)


def _key_probe_is_fresh(entry, now=None, custom_checks=None):
    if not isinstance(entry, dict):
        return False
    try:
        ts = float(entry.get('ts', 0))
    except (TypeError, ValueError):
        return False
    if (now or time.time()) - ts >= KEY_PROBE_CACHE_TTL:
        return False
    custom_checks = custom_checks or []
    if custom_checks:
        custom = entry.get('custom', {})
        if not isinstance(custom, dict):
            return False
        return all(check.get('id') in custom for check in custom_checks)
    return True


def _key_probe_has_required_results(entry, custom_checks=None):
    if not isinstance(entry, dict):
        return False
    if 'tg_ok' not in entry or 'yt_ok' not in entry:
        return False
    custom_checks = custom_checks or []
    if custom_checks:
        custom = entry.get('custom', {})
        if not isinstance(custom, dict):
            return False
        return all(check.get('id') in custom for check in custom_checks)
    return True


TELEGRAM_SVG_B64 = 'PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCA1MTIgNTEyIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxjaXJjbGUgY3g9IjI1NiIgY3k9IjI1NiIgcj0iMjU2IiBmaWxsPSIjMzdBRUUyIi8+PHBhdGggZD0iTTExOSAyNjVsMjY1LTEwNGMxMi01IDIzIDMgMTkgMTlsLTQ1IDIxMmMtMyAxMy0xMiAxNi0yNCAxMGwtNjYtNDktMzIgMzFjLTQgNC03IDctMTUgN2w2LTg1IDE1NS0xNDBjNy02LTItMTAtMTEtNGwtMTkyIDEyMS04My0yNmMtMTgtNi0xOC0xOCA0LTI2eiIgZmlsbD0iI2ZmZiIvPjwvc3ZnPg=='
YOUTUBE_SVG_B64 = 'PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCA0NDMgMzIwIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSI0NDMiIGhlaWdodD0iMzIwIiByeD0iNzAiIGZpbGw9IiNGRjAwMDAiLz48cG9seWdvbiBwb2ludHM9IjE3Nyw5NiAzNTUsMTYwIDE3NywyMjQiIGZpbGw9IiNmZmYiLz48L3N2Zz4='


def _telegram_icon_html(opacity=1.0):
    style = f'vertical-align:middle;opacity:{opacity:g}'
    return f'<img src="data:image/svg+xml;base64,{TELEGRAM_SVG_B64}" width="16" height="16" alt="Telegram" style="{style}">'


def _youtube_icon_html(opacity=1.0):
    style = f'vertical-align:middle;opacity:{opacity:g}'
    return f'<img src="data:image/svg+xml;base64,{YOUTUBE_SVG_B64}" width="16" height="16" alt="YouTube" style="{style}">'


def _chatgpt_icon_html(opacity=1.0):
    style = f'vertical-align:middle;opacity:{opacity:g}'
    return f'<img src="/static/service-icons/chatgpt.png" width="18" height="18" alt="ChatGPT" style="{style}">'


def _service_icon_path(icon):
    icon = re.sub(r'[^a-z0-9_-]+', '', (icon or '').lower())
    if not icon:
        return ''
    return f'/static/service-icons/{icon}.png'


def _service_icon_html(icon, alt, opacity=1.0, size=18):
    src = _service_icon_path(icon)
    if not src:
        return ''
    safe_alt = html.escape(alt or icon)
    style = f'vertical-align:middle;opacity:{opacity:g}'
    return f'<img class="service-icon-img" src="{src}" width="{size}" height="{size}" alt="{safe_alt}" style="{style}">'

def _load_key_pools():
    return key_pool_store.load_key_pools(KEY_POOLS_PATH)


def _dedupe_key_list(keys):
    return key_pool_store.dedupe_key_list(keys)


def _normalize_key_pools(pools):
    return key_pool_store.normalize_key_pools(pools)


def _save_key_pools(pools):
    return key_pool_store.save_key_pools(KEY_POOLS_PATH, pools)


def _fetch_keys_from_subscription(url):
    """Загружает ключи из subscription-ссылки (base64-encoded список)."""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        raw = resp.text.strip()
        # Пробуем декодировать как base64
        try:
            decoded = base64.b64decode(raw + '=' * (-len(raw) % 4)).decode('utf-8')
        except Exception:
            decoded = raw
        keys = [k.strip() for k in decoded.split('\n') if k.strip()]
        # Фильтруем только ключи известных протоколов
        result = {'shadowsocks': [], 'vmess': [], 'vless': [], 'vless2': [], 'trojan': []}
        for k in keys:
            if k.startswith('ss://'):
                result['shadowsocks'].append(k)
            elif k.startswith('vmess://'):
                result['vmess'].append(k)
            elif k.startswith('vless://'):
                result['vless'].append(k)
            elif k.startswith('trojan://'):
                result['trojan'].append(k)
        return result, None
    except requests.RequestException as exc:
        return None, f'Ошибка загрузки subscription: {exc}'
    except Exception as exc:
        return None, f'Ошибка обработки subscription: {exc}'
        


def _set_active_key(proto, key):
    pools = key_pool_store.set_active_key(_load_key_pools(), proto, key)
    _save_key_pools(pools)


def _install_key_for_protocol(proto, key_value, verify=True):
    if proto == 'shadowsocks':
        shadowsocks(key_value)
        return _apply_installed_proxy('shadowsocks', key_value, verify=verify)
    if proto == 'vmess':
        vmess(key_value)
        return _apply_installed_proxy('vmess', key_value, verify=verify)
    if proto == 'vless':
        vless(key_value)
        return _apply_installed_proxy('vless', key_value, verify=verify)
    if proto == 'vless2':
        vless2(key_value)
        return _apply_installed_proxy('vless2', key_value, verify=verify)
    if proto == 'trojan':
        trojan(key_value)
        return _apply_installed_proxy('trojan', key_value, verify=verify)
    raise ValueError(f'Unsupported protocol: {proto}')



def _attempt_auto_failover():
    now = time.time()
    if globals().get('pool_probe_lock') and pool_probe_lock.locked():
        return
    if auto_failover_state['in_progress']:
        return
    if (auto_failover_state['last_attempt'] and
            now - auto_failover_state['last_attempt'] < AUTO_FAILOVER_SWITCH_COOLDOWN_SECONDS):
        return

    proxy_url = proxy_settings.get(proxy_mode)
    ok, probe_message = _check_telegram_api_through_proxy(proxy_url, connect_timeout=4, read_timeout=6)
    if ok:
        auto_failover_state['last_ok'] = now
        auto_failover_state['last_fail'] = 0.0
        return

    if not auto_failover_state['last_fail']:
        auto_failover_state['last_fail'] = now

    if now - auto_failover_state['last_fail'] < AUTO_FAILOVER_GRACE_SECONDS:
        return

    auto_failover_state['in_progress'] = True
    auto_failover_state['last_attempt'] = now
    try:
        current_keys = _load_current_keys()
        active_key = (current_keys.get(proxy_mode) or '').strip()
        pools = _load_key_pools()
        candidates = []
        for proto in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
            for key_value in pools.get(proto, []) or []:
                key_value = (key_value or '').strip()
                if not key_value:
                    continue
                if proto == proxy_mode and key_value == active_key:
                    continue
                candidates.append((proto, key_value))

        if not candidates:
            _write_runtime_log('Auto-failover: ключей в пулах нет, переключать не на что.')
            return

        _write_runtime_log(
            f'Auto-failover: Telegram API не отвечает >{AUTO_FAILOVER_GRACE_SECONDS}s '
            f'(режим {proxy_mode}). Проверяем кандидатов через временный xray.'
        )
        candidate = _find_pool_failover_candidate(candidates, service='telegram')
        if candidate:
            proto, key_value, tg_ok, yt_ok = candidate
            try:
                result = _install_key_for_protocol(proto, key_value, verify=False)
            except Exception as exc:
                _write_runtime_log(f'Auto-failover: ошибка установки {proto} ключа: {exc}')
                return
            update_proxy(proto)
            _set_active_key(proto, key_value)
            _record_key_probe(proto, key_value, tg_ok=tg_ok, yt_ok=yt_ok)
            auto_failover_state['last_ok'] = time.time()
            auto_failover_state['last_fail'] = 0.0
            _write_runtime_log(f'Auto-failover: переключено на {proto}; Telegram API доступен. {result}')
            return

        _write_runtime_log('Auto-failover: перебор ключей из пулов не дал доступа к Telegram API.')
    finally:
        auto_failover_state['in_progress'] = False


def _start_auto_failover_thread():
    def worker():
        while not shutdown_requested.is_set():
            try:
                _attempt_auto_failover()
            except Exception as exc:
                _write_runtime_log(f'Auto-failover error: {exc}')
            shutdown_requested.wait(AUTO_FAILOVER_POLL_SECONDS)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

token = None
usernames = []
routerip = config.routerip
browser_port = config.browser_port
fork_repo_owner = getattr(config, 'fork_repo_owner', 'andruwko73')
fork_repo_name = getattr(config, 'fork_repo_name', 'bypass_keenetic')
fork_button_label = getattr(config, 'fork_button_label', f'Fork by {fork_repo_owner}')
localportsh = config.localportsh
localporttrojan = config.localporttrojan
localportvmess = config.localportvmess
localportvless = config.localportvless
localportvless_transparent = str(int(localportvless) + 1)
localportvless2 = str(int(localportvless) + 2)
localportvless2_transparent = str(int(localportvless) + 3)
localportvmess_transparent = str(int(localportvless) + 4)
localportsh_bot = str(getattr(config, 'localportsh_bot', 10820))
localporttrojan_bot = str(getattr(config, 'localporttrojan_bot', 10830))
dnsovertlsport = config.dnsovertlsport
dnsoverhttpsport = config.dnsoverhttpsport

sid = "0"
PROXY_MODE_FILE = '/opt/etc/bot_proxy_mode'
BOT_AUTOSTART_FILE = '/opt/etc/bot_autostart'

WEB_STATUS_CACHE_TTL = 60
KEY_STATUS_CACHE_TTL = 60
STATUS_CACHE_TTL = min(WEB_STATUS_CACHE_TTL, KEY_STATUS_CACHE_TTL)
ACTIVE_MODE_STATUS_DURING_POOL_TTL = 30
WEB_STATUS_STARTUP_GRACE_PERIOD = 45
KEY_PROBE_CACHE_TTL = 3600
KEY_PROBE_MAX_PER_RUN = None
POOL_PROBE_ACTIVE_ONLY = False
POOL_PROBE_DELAY_SECONDS = float(getattr(config, 'pool_probe_delay_seconds', 0.3))
POOL_PROBE_MIN_AVAILABLE_KB = 120000
POOL_PROBE_TEST_PORT = str(getattr(config, 'pool_probe_test_port', 10991))
POOL_PROBE_BATCH_SIZE = max(1, int(getattr(config, 'pool_probe_batch_size', 3)))
POOL_PROBE_CONCURRENCY = max(1, min(int(getattr(config, 'pool_probe_concurrency', 1)), POOL_PROBE_BATCH_SIZE))
POOL_PROBE_PAGE_MAX_KEYS = max(1, int(getattr(config, 'pool_probe_page_max_keys', 12)))
POOL_PROBE_TG_CONNECT_TIMEOUT = float(getattr(config, 'pool_probe_tg_connect_timeout', 2))
POOL_PROBE_TG_READ_TIMEOUT = float(getattr(config, 'pool_probe_tg_read_timeout', 3))
POOL_PROBE_HTTP_CONNECT_TIMEOUT = float(getattr(config, 'pool_probe_http_connect_timeout', 2))
POOL_PROBE_HTTP_READ_TIMEOUT = float(getattr(config, 'pool_probe_http_read_timeout', 3))
POOL_PROBE_CUSTOM_CONNECT_TIMEOUT = float(getattr(config, 'pool_probe_custom_connect_timeout', 1.5))
POOL_PROBE_CUSTOM_READ_TIMEOUT = float(getattr(config, 'pool_probe_custom_read_timeout', 2.5))
POOL_PROBE_RETRY_CONNECT_TIMEOUT = float(getattr(config, 'pool_probe_retry_connect_timeout', 6))
POOL_PROBE_RETRY_READ_TIMEOUT = float(getattr(config, 'pool_probe_retry_read_timeout', 10))
POOL_PROBE_RETRY_DELAY_SECONDS = float(getattr(config, 'pool_probe_retry_delay_seconds', 0.2))
POOL_PROBE_PAGE_REFRESH_INTERVAL = float(getattr(config, 'pool_probe_page_refresh_interval', 1800))
POOL_PROBE_SINGLE_TIMEOUT_SECONDS = max(
    8.0,
    POOL_PROBE_TG_CONNECT_TIMEOUT + POOL_PROBE_TG_READ_TIMEOUT +
    POOL_PROBE_HTTP_CONNECT_TIMEOUT + POOL_PROBE_HTTP_READ_TIMEOUT +
    POOL_PROBE_TG_CONNECT_TIMEOUT + POOL_PROBE_TG_READ_TIMEOUT +
    POOL_PROBE_HTTP_CONNECT_TIMEOUT + POOL_PROBE_HTTP_READ_TIMEOUT + 3.0,
)
POOL_PROBE_BATCH_TIMEOUT_SECONDS = float(
    getattr(config, 'pool_probe_batch_timeout_seconds', POOL_PROBE_SINGLE_TIMEOUT_SECONDS + 5.0)
)
POOL_PROBE_UI_POLL_EXTENSION_MS = int(getattr(config, 'pool_probe_ui_poll_extension_ms', 180000))
APP_BRANCH_LABEL = 'codex/web-only-v1'
APP_BRANCH_DESCRIPTION = 'без Telegram бота'
APP_VERSION_COUNTER = '1.01'
APP_VERSION_LABEL = f'v{APP_VERSION_COUNTER}'
APP_MODE_LABEL = 'Режим прокси'
APP_MODE_NOUN = 'режим прокси'
APP_START_IDLE_LABEL = 'Запустить прокси'
APP_START_REPEAT_LABEL = 'Повторить запуск прокси'
APP_START_RESULT = 'Команда запуска принята. Прокси-сервисы запущены.'
APP_QUICK_START_NOTE = 'После установки ключей можно сразу запустить или перезапустить прокси-сервисы.'
APP_PROXY_USER_LABEL = 'Прокси-сервис'
BOT_SOURCE_PATH = os.path.abspath(__file__)
BOT_DIR = os.path.dirname(BOT_SOURCE_PATH)
STATIC_DIR = os.path.join(BOT_DIR, 'static')
README_PATH = os.path.join(BOT_DIR, 'README.md')
XRAY_SERVICE_SCRIPT = '/opt/etc/init.d/S24xray'
V2RAY_SERVICE_SCRIPT = '/opt/etc/init.d/S24v2ray'
XRAY_CONFIG_DIR = '/opt/etc/xray'
V2RAY_CONFIG_DIR = '/opt/etc/v2ray'
CORE_PROXY_CONFIG_DIR = XRAY_CONFIG_DIR if os.path.exists(XRAY_SERVICE_SCRIPT) else V2RAY_CONFIG_DIR
CORE_PROXY_SERVICE_SCRIPT = XRAY_SERVICE_SCRIPT if os.path.exists(XRAY_SERVICE_SCRIPT) else V2RAY_SERVICE_SCRIPT
CORE_PROXY_CONFIG_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'config.json')
CORE_PROXY_ERROR_LOG = os.path.join(CORE_PROXY_CONFIG_DIR, 'error.log')
CORE_PROXY_ACCESS_LOG = os.path.join(CORE_PROXY_CONFIG_DIR, 'access.log')
VMESS_KEY_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'vmess.key')
VLESS_KEY_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'vless.key')
VLESS2_KEY_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'vless2.key')

bot_ready = False
web_httpd = None
shutdown_requested = threading.Event()
proxy_mode = config.default_proxy_mode
proxy_settings = {
    'none': None,
    'shadowsocks': f'socks5h://127.0.0.1:{localportsh_bot}',
    'vmess': f'socks5h://127.0.0.1:{localportvmess}',
    'vless': f'socks5h://127.0.0.1:{localportvless}',
    'vless2': f'socks5h://127.0.0.1:{localportvless2}',
    'trojan': f'socks5h://127.0.0.1:{localporttrojan_bot}',
}
proxy_supports_http = {
    'none': True,
    'shadowsocks': True,
    'vmess': True,
    'vless': True,
    'vless2': True,
    'trojan': True,
}
status_snapshot_cache = {
    'timestamp': 0,
    'data': None,
    'signature': None,
}
active_mode_status_cache = {
    'timestamp': 0,
    'signature': None,
    'status': None,
}
active_mode_status_cache_lock = threading.Lock()
status_refresh_lock = threading.Lock()
status_refresh_in_progress = set()
pool_probe_lock = threading.Lock()
pool_probe_auto_lock = threading.Lock()
pool_apply_lock = threading.Lock()
pool_probe_last_auto_started_at = 0
pool_probe_progress_lock = threading.Lock()
pool_probe_progress = {
    'running': False,
    'checked': 0,
    'total': 0,
    'scope': '',
    'started_at': 0,
    'finished_at': 0,
}
process_started_at = time.time()
web_command_lock = threading.Lock()
web_command_state = {
    'running': False,
    'command': '',
    'label': '',
    'result': '',
    'progress': 0,
    'progress_label': '',
    'started_at': 0,
    'finished_at': 0,
    'shown_after_finish': False,
}
web_flash_lock = threading.Lock()
web_flash_message = ''
DIRECT_FETCH_ENV_KEYS = [
    'HTTPS_PROXY',
    'HTTP_PROXY',
    'https_proxy',
    'http_proxy',
    'ALL_PROXY',
    'all_proxy',
]
RUNTIME_ERROR_LOG_PATHS = [
    '/opt/etc/error.log',
    '/opt/etc/bot/error.log',
]



def _is_local_web_client(address):
    try:
        ip_obj = ipaddress.ip_address((address or '').strip())
    except ValueError:
        return False
    return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local


def _resolve_web_bind_host():
    candidate = str(routerip or '').strip()
    if not candidate:
        return ''
    try:
        ip_obj = ipaddress.ip_address(candidate)
    except ValueError:
        return ''
    if ip_obj.is_unspecified:
        return ''
    return candidate



def _raw_github_url(path):
    return f'https://raw.githubusercontent.com/{fork_repo_owner}/{fork_repo_name}/{APP_BRANCH_LABEL}/{path}?ts={int(time.time())}'


def _fetch_remote_text(url, timeout=20):
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


SOCIALNET_SOURCE_URL = 'https://raw.githubusercontent.com/tas-unn/bypass_keenetic/main/socialnet.txt'
SOCIALNET_LOCAL_PATHS = [
    os.path.join(BOT_DIR, 'socialnet.txt'),
    '/opt/etc/bot/socialnet.txt',
    '/opt/etc/unblock/socialnet.txt',
]




SOCIALNET_SERVICE_KEYS = ('youtube', 'telegram', 'meta', 'discord', 'tiktok', 'twitter')
SOCIALNET_ALL_KEY = 'all'
SOCIALNET_EXCLUDED_ENTRIES = set()


def _service_list_alias_map():
    aliases = {}
    for key, source in SERVICE_LIST_SOURCES.items():
        aliases[key] = key
        aliases[source.get('label', key).lower()] = key
        for alias in source.get('aliases', []):
            aliases[alias.lower()] = key
    return aliases




def _write_runtime_log(message, mode='a'):
    text = '' if message is None else str(message)
    if text and not text.endswith('\n'):
        text += '\n'
    for log_path in RUNTIME_ERROR_LOG_PATHS:
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, mode, encoding='utf-8', errors='ignore') as file:
                file.write(text)
        except Exception:
            continue





def _read_json_file(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception:
        return default


def _write_json_file(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(payload, file, ensure_ascii=False)


def _remove_file(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _has_socks_support():
    try:
        import socks  # noqa: F401
        return True
    except Exception:
        return False


def _daemonize_process():
    if os.name != 'posix':
        return
    try:
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    except Exception:
        pass


def _request_shutdown(reason=''):
    if shutdown_requested.is_set():
        return
    shutdown_requested.set()
    if reason:
        _write_runtime_log(f'Запрошена остановка web-only сервиса: {reason}')
    if web_httpd is not None:
        try:
            threading.Thread(target=web_httpd.shutdown, daemon=True).start()
        except Exception:
            pass


def _finalize_shutdown():
    if web_httpd is not None:
        try:
            web_httpd.server_close()
        except Exception:
            pass


def _register_signal_handlers():
    if os.name != 'posix':
        return

    def _handle_stop_signal(signum, frame):
        try:
            signal_name = signal.Signals(signum).name
        except Exception:
            signal_name = str(signum)
        _request_shutdown(signal_name)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_stop_signal)
        except Exception:
            pass



def _save_proxy_mode(proxy_type):
    try:
        os.makedirs(os.path.dirname(PROXY_MODE_FILE), exist_ok=True)
        with open(PROXY_MODE_FILE, 'w', encoding='utf-8') as file:
            file.write(proxy_type)
    except Exception:
        pass


def _proxy_mode_label(proxy_type):
    labels = {
        'none': 'None',
        'shadowsocks': 'Shadowsocks',
        'vmess': 'Vmess',
        'vless': 'Vless 1',
        'vless2': 'Vless 2',
        'trojan': 'Trojan',
    }
    return labels.get(proxy_type, proxy_type)


def _save_bot_autostart(enabled):
    try:
        if enabled:
            with open(BOT_AUTOSTART_FILE, 'w', encoding='utf-8') as file:
                file.write('1')
        elif os.path.exists(BOT_AUTOSTART_FILE):
            os.remove(BOT_AUTOSTART_FILE)
    except Exception:
        pass


def _prepare_entware_dns():
    try:
        result = subprocess.run(
            ['nslookup', 'bin.entware.net', '192.168.1.1'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return 'Entware DNS уже доступен.'
    except Exception:
        pass

    notes = []
    try:
        subprocess.run(['ndmc', '-c', 'no opkg dns-override'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        subprocess.run(['ndmc', '-c', 'system configuration save'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        notes.append('opkg dns-override отключён')
    except Exception:
        notes.append('не удалось отключить opkg dns-override')

    try:
        resolv_conf = '/etc/resolv.conf'
        preserved_lines = []
        if os.path.exists(resolv_conf):
            with open(resolv_conf, 'r', encoding='utf-8', errors='ignore') as file:
                preserved_lines = [
                    line.rstrip('\n')
                    for line in file
                    if line.strip() and not line.lstrip().startswith('nameserver')
                ]
        with open(resolv_conf, 'w', encoding='utf-8') as file:
            file.write('nameserver 8.8.8.8\n')
            file.write('nameserver 1.1.1.1\n')
            if preserved_lines:
                file.write('\n'.join(preserved_lines) + '\n')
        notes.append('внешние DNS записаны первыми в /etc/resolv.conf')
    except Exception:
        notes.append('не удалось обновить /etc/resolv.conf')

    try:
        lookup_output = subprocess.check_output(
            ['nslookup', 'bin.entware.net', '8.8.8.8'],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        host_matches = re.findall(r'Address\s+\d+:\s+((?:\d{1,3}\.){3}\d{1,3})', lookup_output)
        entware_ip = host_matches[-1] if host_matches else ''
        if entware_ip:
            hosts_path = '/etc/hosts'
            preserved_lines = []
            if os.path.exists(hosts_path):
                with open(hosts_path, 'r', encoding='utf-8', errors='ignore') as file:
                    preserved_lines = [line.rstrip('\n') for line in file if 'bin.entware.net' not in line]
            with open(hosts_path, 'w', encoding='utf-8') as file:
                if preserved_lines:
                    file.write('\n'.join(preserved_lines) + '\n')
                file.write(f'{entware_ip} bin.entware.net\n')
            notes.append(f'bin.entware.net закреплён в /etc/hosts как {entware_ip}')
    except Exception:
        notes.append('не удалось закрепить bin.entware.net в /etc/hosts')

    return 'Подготовка Entware DNS: ' + ', '.join(notes)


def _cleanup_after_foreign_update():
    """После обновления из веток main/independent-rework удаляем bot.py
    и Telegram-сервисы, оставляя только web-only версию."""
    notes = []
    try:
        if os.path.exists('/opt/etc/bot.py'):
            os.remove('/opt/etc/bot.py')
            notes.append('bot.py удалён')
        if os.path.exists('/opt/etc/init.d/S99telegram_bot'):
            os.remove('/opt/etc/init.d/S99telegram_bot')
            notes.append('S99telegram_bot удалён')
        if os.path.exists('/opt/etc/init.d/S98telegram_bot_installer'):
            os.remove('/opt/etc/init.d/S98telegram_bot_installer')
            notes.append('S98telegram_bot_installer удалён')
        bot_pids_str = subprocess.check_output(
            ['pgrep', '-f', '/opt/etc/bot.py'],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        if bot_pids_str:
            for pid_str in bot_pids_str.splitlines():
                pid = pid_str.strip()
                if pid and pid != str(os.getpid()):
                    os.kill(int(pid), signal.SIGTERM)
                    notes.append(f'Процесс bot.py (PID {pid}) остановлен')
    except subprocess.CalledProcessError:
        pass
    except Exception as exc:
        notes.append(f'Ошибка очистки: {exc}')
    if notes:
        return 'Очистка после чужого обновления: ' + ', '.join(notes)
    return ''


def _ensure_legacy_bot_paths():
    mappings = [
        ('/opt/etc/bot/bot_config.py', '/opt/etc/bot_config.py'),
        ('/opt/etc/bot/main.py', '/opt/etc/bot.py'),
    ]
    notes = []
    for source_path, legacy_path in mappings:
        try:
            if not os.path.exists(source_path):
                continue
            if os.path.islink(legacy_path):
                if os.path.realpath(legacy_path) == os.path.realpath(source_path):
                    continue
                os.remove(legacy_path)
            elif os.path.exists(legacy_path):
                continue
            os.symlink(source_path, legacy_path)
            notes.append(f'{legacy_path} -> {source_path}')
        except Exception:
            try:
                shutil.copyfile(source_path, legacy_path)
                notes.append(f'{legacy_path} скопирован из {source_path}')
            except Exception:
                notes.append(f'не удалось подготовить {legacy_path}')
    if not notes:
        return 'Legacy-пути уже доступны.'
    return 'Подготовка legacy-путей: ' + ', '.join(notes)




def _unblock_list_path(list_name):
    return os.path.join('/opt/etc/unblock', f'{list_name}.txt')


def _read_unblock_list_entries(list_name):
    list_path = _unblock_list_path(list_name)
    if not os.path.exists(list_path):
        raise FileNotFoundError(list_path)
    with open(list_path, encoding='utf-8') as file:
        return [line.strip() for line in file if line.strip()]


def _write_unblock_list_entries(list_name, entries):
    list_path = _unblock_list_path(list_name)
    with open(list_path, 'w', encoding='utf-8') as file:
        for line in sorted(set(entries)):
            if line:
                file.write(line + '\n')


def _normalize_unblock_route_name(list_name):
    safe_name = os.path.basename((list_name or '').strip())
    if safe_name.endswith('.txt'):
        safe_name = safe_name[:-4]
    if not safe_name or not re.match(r'^[A-Za-z0-9_-]+$', safe_name):
        raise ValueError('Некорректное имя списка')
    return safe_name


def _socialnet_entries_from_text(text):
    entries = []
    seen = set()
    for raw_line in (text or '').replace('\r', '\n').split('\n'):
        line = raw_line.split('#', 1)[0].strip()
        if not line or line.lower() in SOCIALNET_EXCLUDED_ENTRIES or line in seen:
            continue
        seen.add(line)
        entries.append(line)
    return entries


def _resolve_socialnet_service(value):
    normalized = (value or '').strip().lower()
    if normalized in ('', SOCIALNET_ALL_KEY, 'all', 'все', 'все соцсети', 'все сервисы', 'все в список'):
        return SOCIALNET_ALL_KEY
    aliases = _service_list_alias_map()
    key = aliases.get(normalized)
    if key in SOCIALNET_SERVICE_KEYS:
        return key
    return None


def _socialnet_service_label(service_key):
    if service_key == SOCIALNET_ALL_KEY:
        return 'Все сервисы'
    return SERVICE_LIST_SOURCES.get(service_key, {}).get('label', service_key)


def _load_service_entries(service_key):
    source = SERVICE_LIST_SOURCES.get(service_key)
    if not source:
        raise ValueError('Неизвестный сервис')
    if source.get('entries'):
        return _socialnet_entries_from_text('\n'.join(source['entries']))
    raw_text = _fetch_remote_text(source['url'], timeout=25)
    entries = _parse_service_domains(raw_text)
    if not entries:
        raise ValueError(f'Список {source["label"]} пуст')
    return entries


def _load_socialnet_entries(service_key=SOCIALNET_ALL_KEY):
    service_key = _resolve_socialnet_service(service_key)
    if not service_key:
        raise ValueError('Неизвестный сервис')
    if service_key != SOCIALNET_ALL_KEY:
        return _load_service_entries(service_key)
    combined = []
    for key in SOCIALNET_SERVICE_KEYS:
        try:
            combined.extend(_load_service_entries(key))
        except Exception:
            continue
    entries = _socialnet_entries_from_text('\n'.join(combined))
    if entries:
        return entries
    for path in SOCIALNET_LOCAL_PATHS:
        try:
            if os.path.exists(path):
                entries = _socialnet_entries_from_text(_read_text_file(path))
                if entries:
                    return entries
        except Exception:
            continue
    social_text = _fetch_remote_text(SOCIALNET_SOURCE_URL, timeout=25)
    entries = _socialnet_entries_from_text(social_text)
    if not entries:
        raise ValueError('Список соцсетей пуст')
    return entries


def _apply_entries_to_unblock_list(list_name, entries, service_label, remove=False):
    route_name = _normalize_unblock_route_name(list_name)
    entries = {entry.strip() for entry in entries or [] if str(entry).strip()}
    if not entries:
        raise ValueError('Нет записей для добавления')
    list_path = _unblock_list_path(route_name)
    current = set(_read_unblock_list_entries(route_name)) if os.path.exists(list_path) else set()
    before = len(current)
    if remove:
        current.difference_update(entries)
        changed = before - len(current)
        action = 'удалено'
    else:
        current.update(entries)
        changed = len(current) - before
        action = 'добавлено'
    _write_unblock_list_entries(route_name, current)
    subprocess.run(['/opt/bin/unblock_update.sh'], check=False)
    label = _list_label(f'{route_name}.txt')
    return f'✅ {service_label}: {action} {changed} записей в {label}. Всего в списке: {len(current)}.'


def _apply_socialnet_list(list_name, service_key=SOCIALNET_ALL_KEY, remove=False):
    service_key = _resolve_socialnet_service(service_key)
    if not service_key:
        raise ValueError('Неизвестный сервис')
    entries = _load_socialnet_entries(service_key)
    return _apply_entries_to_unblock_list(
        list_name,
        entries,
        _socialnet_service_label(service_key),
        remove=remove,
    )


def _unblock_route_for_key_type(key_type):
    routes = {
        'shadowsocks': 'shadowsocks',
        'vmess': 'vmess',
        'vless': 'vless',
        'vless2': 'vless-2',
        'trojan': 'trojan',
    }
    return routes.get(key_type, key_type)


def _custom_check_route_entries(custom_checks=None):
    checks = custom_checks if custom_checks is not None else _load_custom_checks()
    preset_routes = {item.get('id'): item.get('routes') or [] for item in CUSTOM_CHECK_PRESETS}
    values = []
    for check in checks:
        values.extend(preset_routes.get(check.get('id'), []))
        values.extend(check.get('routes') or [])
        values.extend(check.get('urls') or [check.get('url', '')])
    return _route_entries_from_values(values)


def _append_custom_checks_to_unblock_list(list_name, custom_checks=None):
    route_name = _normalize_unblock_route_name(_unblock_route_for_key_type(list_name))
    entries = _custom_check_route_entries(custom_checks)
    if not entries:
        raise ValueError('Сначала добавьте хотя бы одну дополнительную проверку')
    return _apply_entries_to_unblock_list(route_name, entries, 'Дополнительные сервисы', remove=False)



def _resolve_service_list_name(value):
    normalized = (value or '').strip().lower()
    return _service_list_alias_map().get(normalized)


def _parse_service_domains(text):
    domains = []
    seen = set()
    for raw_line in text.replace('\r', '\n').split('\n'):
        line = raw_line.split('#', 1)[0].strip()
        if not line:
            continue
        for token in re.split(r'[\s,]+', line):
            item = token.strip().strip('"\'')
            item = re.sub(r'^(DOMAIN-SUFFIX|DOMAIN|HOST-SUFFIX),', '', item, flags=re.IGNORECASE)
            item = re.sub(r'^\+\.', '', item)
            item = re.sub(r'^\*\.', '', item)
            item = item.strip('/').lower()
            if not item or '/' in item or ':' in item:
                continue
            if not re.match(r'^[a-z0-9*_.-]+\.[a-z0-9_.-]+$', item):
                continue
            if item not in seen:
                seen.add(item)
                domains.append(item)
    return domains


def _append_entries_to_unblock_list(list_name, entries):
    existing = set(_read_unblock_list_entries(list_name)) if os.path.exists(_unblock_list_path(list_name)) else set()
    before = len(existing)
    existing.update(entries)
    _write_unblock_list_entries(list_name, existing)
    subprocess.run(['/opt/bin/unblock_update.sh'], check=False)
    return len(existing) - before, len(existing)





# web-only: Telegram menu removed







def _download_repo_file_from_archive(session, repo_owner, repo_name, repo_ref, path):
    archive_ref = repo_ref if '/' not in repo_ref else f'refs/heads/{repo_ref}'
    archive_url = f'https://codeload.github.com/{repo_owner}/{repo_name}/tar.gz/{archive_ref}'
    suffix = '/' + path.strip('/')
    with session.get(archive_url, stream=True, timeout=(10, 90)) as response:
        response.raise_for_status()
        response.raw.decode_content = True
        with tarfile.open(fileobj=response.raw, mode='r|gz') as archive:
            for member in archive:
                if member.isfile() and member.name.endswith(suffix):
                    extracted = archive.extractfile(member)
                    if extracted is not None:
                        return archive_url, extracted.read().decode('utf-8')
    raise ValueError(f'GitHub archive did not contain {path}')


def _download_repo_file_text(session, repo_owner, repo_name, repo_ref, path):
    headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
    raw_url = f'https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{repo_ref}/{path}'
    try:
        response = session.get(raw_url, headers=headers, timeout=(5, 8))
        response.raise_for_status()
        return raw_url, response.text
    except requests.RequestException:
        pass

    try:
        return _download_repo_file_from_archive(session, repo_owner, repo_name, repo_ref, path)
    except Exception:
        pass

    api_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{quote(path, safe="/")}'
    response = session.get(
        api_url,
        params={'ref': repo_ref},
        headers={'Accept': 'application/vnd.github+json', **headers},
        timeout=(10, 30),
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get('encoding') != 'base64' or 'content' not in payload:
        raise ValueError('GitHub contents API returned unexpected file payload')
    content = ''.join(str(payload.get('content', '')).split())
    return response.url, base64.b64decode(content).decode('utf-8')


def _download_repo_script(repo_owner, repo_name, branch='codex/main-v1'):
    session = requests.Session()
    session.trust_env = False
    url, script_text = _download_repo_file_text(session, repo_owner, repo_name, branch, 'script.sh')
    if '#!/bin/sh' not in script_text:
        raise ValueError('GitHub returned invalid script.sh')
    with open('/opt/root/script.sh', 'w', encoding='utf-8') as file:
        file.write(script_text)
    os.chmod('/opt/root/script.sh', stat.S_IRWXU)
    return url, script_text, branch


def _build_direct_fetch_env():
    env = os.environ.copy()
    for key in DIRECT_FETCH_ENV_KEYS:
        env.pop(key, None)
    return env


def _run_script_action(action, repo_owner=None, repo_name=None, progress_command=None, branch='codex/main-v1',
                       cleanup_web_only=False):
    logs = [_prepare_entware_dns(), _ensure_legacy_bot_paths()]
    direct_env = _build_direct_fetch_env()
    if progress_command:
        _set_web_command_progress(progress_command, '\n'.join(logs))
    if repo_owner and repo_name:
        url, script_text, repo_ref = _download_repo_script(repo_owner, repo_name, branch=branch)
        direct_env['REPO_REF'] = branch
        logs.append(f'Скрипт загружен из {url}')
        logs.append(f'Коммит обновления: {repo_ref[:12]}')
        if repo_owner == fork_repo_owner and 'BOT_CONFIG_PATH' not in script_text:
            logs.append('⚠️ GitHub отдал старую версию script.sh, но legacy-пути уже подготовлены на роутере.')
        if progress_command:
            _set_web_command_progress(progress_command, '\n'.join(logs))
        with open('/opt/root/script.sh', 'w', encoding='utf-8') as file:
            file.write(script_text)
        os.chmod('/opt/root/script.sh', stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

    process = subprocess.Popen(
        ['/bin/sh', '/opt/root/script.sh', action],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=direct_env,
    )
    for line in process.stdout:
        clean_line = line.strip()
        if clean_line:
            logs.append(clean_line)
            if progress_command:
                _set_web_command_progress(progress_command, '\n'.join(logs))
    return_code = process.wait()
    if return_code != 0:
        logs.append(f'Команда завершилась с кодом {return_code}.')
    if action == '-update' and cleanup_web_only:
        cleanup_note = _cleanup_after_foreign_update()
        if cleanup_note:
            logs.append(cleanup_note)
    return return_code, '\n'.join(logs)


def _restart_router_services():
    commands = [
        '/opt/etc/init.d/S56dnsmasq restart',
        '/opt/etc/init.d/S22shadowsocks restart',
        CORE_PROXY_SERVICE_SCRIPT + ' restart',
        '/opt/etc/init.d/S22trojan restart',
    ]
    for command in commands:
        os.system(command)
    _invalidate_web_status_cache()
    return '✅ Сервисы перезагружены.'



def _schedule_router_reboot(delay_seconds=5):
    delay = max(1, int(delay_seconds))
    subprocess.Popen(
        ['/bin/sh', '-c', f'sleep {delay}; ndmc -c "system reboot" >/dev/null 2>&1'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )


def _set_dns_override(enabled):
    _save_bot_autostart(True)
    if enabled:
        os.system("ndmc -c 'opkg dns-override'")
        time.sleep(2)
        os.system("ndmc -c 'system configuration save'")
        _schedule_router_reboot()
        return '✅ DNS Override включен. Роутер будет автоматически перезагружен через несколько секунд.'
    os.system("ndmc -c 'no opkg dns-override'")
    time.sleep(2)
    os.system("ndmc -c 'system configuration save'")
    _schedule_router_reboot()
    return '✅ DNS Override выключен. Роутер будет автоматически перезагружен через несколько секунд.'


def _dns_override_enabled():
    try:
        result = subprocess.run(
            ['ndmc', '-c', 'show running-config'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        return 'opkg dns-override' in (result.stdout or '')
    except Exception:
        return False


def _run_web_command(command):
    if command == 'install_original':
        _, output = _run_script_action('-install', 'tas-unn', 'bypass_keenetic')
        return output
    if command == 'update':
        _, output = _run_script_action('-update', fork_repo_owner, fork_repo_name, progress_command='update')
        return output
    if command == 'update_independent':
        _, output = _run_script_action(
            '-update',
            'andruwko73',
            'bypass_keenetic',
            progress_command='update_independent',
            branch='codex/independent-v1',
        )
        return output
    if command == 'update_no_bot':
        _, output = _run_script_action(
            '-update',
            'andruwko73',
            'bypass_keenetic',
            progress_command='update_no_bot',
            branch='codex/web-only-v1',
            cleanup_web_only=True,
        )
        return output
    if command == 'remove':
        _, output = _run_script_action('-remove', fork_repo_owner, fork_repo_name)
        return output
    if command == 'restart_services':
        return _restart_router_services()
    if command == 'dns_on':
        return _set_dns_override(True)
    if command == 'dns_off':
        return _set_dns_override(False)
    if command == 'reboot':
        os.system('ndmc -c system reboot')
        return '🔄 Роутер перезагружается. Это займёт около 2 минут.'
    return 'Команда не распознана.'


def _read_text_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            return file.read()
    except Exception:
        return ''


def _current_bot_version():
    source_text = _read_text_file(BOT_SOURCE_PATH)
    match = re.search(r'^#\s*ВЕРСИЯ СКРИПТА\s+(.+?)\s*$', source_text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    match = re.search(r'Версия\s+([0-9][0-9.]*)', source_text)
    if match:
        return match.group(1).strip()
    for line in source_text.splitlines():
        if line.startswith('# ВЕРСИЯ СКРИПТА'):
            return line.replace('# ВЕРСИЯ СКРИПТА', '').strip()
    return 'неизвестна'


def _normalize_unblock_list(text):
    items = []
    seen = set()
    for raw_line in text.replace('\r', '\n').split('\n'):
        line = raw_line.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        items.append(line)
    items.sort()
    return '\n'.join(items)


def _save_unblock_list(list_name, text):
    safe_name = os.path.basename(list_name)
    target_path = os.path.join('/opt/etc/unblock', safe_name)
    if not target_path.endswith('.txt'):
        raise ValueError('Список должен быть .txt файлом')
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    normalized = _normalize_unblock_list(text)
    with open(target_path, 'w', encoding='utf-8') as file:
        if normalized:
            file.write(normalized + '\n')
    subprocess.run(['/opt/bin/unblock_update.sh'], check=False)
    return f'✅ Список {safe_name} сохранён и применён.'


def _append_socialnet_list(list_name, service_key=SOCIALNET_ALL_KEY):
    return _apply_socialnet_list(list_name, service_key=service_key, remove=False)


def _remove_socialnet_list(list_name, service_key=SOCIALNET_ALL_KEY):
    return _apply_socialnet_list(list_name, service_key=service_key, remove=True)


def _list_label(file_name):
    base = file_name[:-4] if file_name.endswith('.txt') else file_name
    labels = {
        'shadowsocks': 'Shadowsocks',
        'vmess': 'Vmess',
        'vless': 'Vless 1',
        'vless-2': 'Vless 2',
        'trojan': 'Trojan',
    }
    return labels.get(base, base)


def _load_unblock_lists(with_content=True):
    unblock_dir = '/opt/etc/unblock'
    try:
        file_names = sorted(name for name in os.listdir(unblock_dir) if name.endswith('.txt'))
    except Exception:
        file_names = []
    file_names = [name for name in file_names if name not in ['vpn.txt', 'tor.txt'] and not name.startswith('vpn-')]
    preferred_order = ['vless.txt', 'vless-2.txt', 'vmess.txt', 'trojan.txt', 'shadowsocks.txt']
    ordered = []
    for item in preferred_order:
        if item in file_names:
            ordered.append(item)
    for item in file_names:
        if item not in ordered:
            ordered.append(item)
    result = []
    for file_name in ordered:
        entry = {
            'name': file_name,
            'label': _list_label(file_name),
        }
        if with_content:
            entry['content'] = _read_text_file(os.path.join(unblock_dir, file_name)).strip()
        result.append(entry)
    return result




def _transparent_list_route_label():
    config_text = _read_text_file(CORE_PROXY_CONFIG_PATH)
    has_vless_1 = 'in-vless-transparent' in config_text and 'proxy-vless' in config_text
    has_vless_2 = 'in-vless2-transparent' in config_text and 'proxy-vless2' in config_text
    if has_vless_1 and has_vless_2:
        return 'Vless 1 / Vless 2'
    if has_vless_1:
        return 'Vless 1'
    if has_vless_2:
        return 'Vless 2'
    return 'Не определён'


def _load_shadowsocks_key():
    try:
        with open('/opt/etc/shadowsocks.json', 'r', encoding='utf-8') as file:
            data = json.load(file)
        raw_uri = str(data.get('raw_uri', '') or '').strip()
        if raw_uri.startswith('ss://'):
            return raw_uri
        server = (data.get('server') or [''])[0]
        port = data.get('server_port', '')
        method = data.get('method', '')
        password = data.get('password', '')
        if not server or not port or not method:
            return ''
        encoded = base64.urlsafe_b64encode(f'{method}:{password}'.encode('utf-8')).decode('utf-8').rstrip('=')
        return f'ss://{encoded}@{server}:{port}'
    except Exception:
        return ''


def _load_trojan_key():
    try:
        with open('/opt/etc/trojan/config.json', 'r', encoding='utf-8') as file:
            data = json.load(file)
        raw_uri = str(data.get('raw_uri', '') or '').strip()
        if raw_uri.startswith('trojan://'):
            return raw_uri
        password = (data.get('password') or [''])[0]
        address = data.get('remote_addr', '')
        port = data.get('remote_port', '')
        if (
            str(address).strip().lower() == 'ownade' and
            str(port).strip() == '65432' and
            str(password).strip() == 'pw'
        ):
            return ''
        if not password or not address or not port:
            return ''
        query_params = []
        trojan_type = str(data.get('type', '') or '').strip()
        if trojan_type and trojan_type != 'tcp':
            query_params.append(('type', trojan_type))

        security = str(data.get('security', '') or '').strip()
        if security and security != 'tls':
            query_params.append(('security', security))

        sni = str(data.get('sni', '') or '').strip()
        if sni:
            query_params.append(('sni', sni))

        host = str(data.get('host', '') or '').strip()
        if host:
            query_params.append(('host', host))

        path = str(data.get('path', '') or '').strip()
        if path and path != '/':
            query_params.append(('path', path))

        service_name = str(data.get('serviceName', '') or '').strip()
        if service_name:
            query_params.append(('serviceName', service_name))

        fingerprint = str(data.get('fingerprint', '') or '').strip()
        if fingerprint and fingerprint != 'chrome':
            query_params.append(('fp', fingerprint))

        alpn = str(data.get('alpn', '') or '').strip()
        if alpn:
            query_params.append(('alpn', alpn))

        query_suffix = ''
        if query_params:
            query_suffix = '?' + urlencode(query_params)

        fragment = str(data.get('fragment', '') or '').strip()
        fragment_suffix = f'#{quote(fragment)}' if fragment else ''

        return f'trojan://{password}@{address}:{port}{query_suffix}{fragment_suffix}'
    except Exception:
        return ''


def _load_current_keys():
    return {
        'shadowsocks': _load_shadowsocks_key(),
        'vmess': _read_v2ray_key(VMESS_KEY_PATH) or '',
        'vless': _read_v2ray_key(VLESS_KEY_PATH) or '',
        'vless2': _read_v2ray_key(VLESS2_KEY_PATH) or '',
        'trojan': _load_trojan_key(),
    }


def _ensure_current_keys_in_pools(current_keys=None):
    current_keys = current_keys if current_keys is not None else _load_current_keys()
    pools, changed = key_pool_store.ensure_current_keys_in_pools(_load_key_pools(), current_keys)
    if changed:
        _save_key_pools(pools)
    return pools


def _invalidate_status_snapshot_cache():
    status_snapshot_cache['timestamp'] = 0
    status_snapshot_cache['data'] = None
    status_snapshot_cache['signature'] = None


def _invalidate_key_status_cache():
    _invalidate_status_snapshot_cache()


def _check_http_through_proxy(proxy_url, url='https://www.youtube.com', connect_timeout=2, read_timeout=3):
    try:
        response = requests.get(
            url,
            timeout=(connect_timeout, read_timeout),
            proxies={'https': proxy_url, 'http': proxy_url},
            stream=True,
        )
        status_code = response.status_code
        response.close()
        if status_code < 500:
            return True, f'Веб-доступ через ключ подтверждён (HTTP {status_code}).'
        return False, f'Веб-проверка через ключ вернула HTTP {status_code}.'
    except requests.exceptions.ConnectTimeout:
        return False, 'Прокси не установил соединение за отведённое время.'
    except requests.exceptions.ReadTimeout:
        return False, 'Удалённый сервер не ответил вовремя через этот ключ.'
    except requests.exceptions.RequestException as exc:
        return False, f'Веб-проверка через ключ завершилась ошибкой: {exc}'
def _check_custom_target_through_proxy(proxy_url, url, connect_timeout=2, read_timeout=3):
    try:
        target_url = _normalize_check_url(url)
        response = requests.get(
            target_url,
            timeout=(connect_timeout, read_timeout),
            proxies={'https': proxy_url, 'http': proxy_url},
            headers={'User-Agent': 'bypass_keenetic health check'},
            stream=True,
        )
        status_code = response.status_code
        response.close()
        if status_code < 500:
            return True, f'Доступ к {urlparse(target_url).netloc} подтверждён (HTTP {status_code}).'
        return False, f'{urlparse(target_url).netloc} вернул HTTP {status_code}.'
    except ValueError as exc:
        return False, str(exc)
    except requests.exceptions.ConnectTimeout:
        return False, 'Прокси не установил соединение за отведённое время.'
    except requests.exceptions.ReadTimeout:
        return False, 'Сервис не ответил вовремя через этот ключ.'
    except requests.exceptions.RequestException as exc:
        return False, f'Проверка сервиса завершилась ошибкой: {str(exc).splitlines()[0][:180]}'


def _probe_custom_targets(proxy_url, custom_checks=None, connect_timeout=2, read_timeout=3):
    results = {}
    for check in (custom_checks if custom_checks is not None else _load_custom_checks()):
        check_id = check.get('id')
        if not check_id:
            continue
        targets = check.get('urls') if isinstance(check.get('urls'), list) else [check.get('url', '')]
        targets = targets[:2]
        target_results = []
        for target in targets:
            ok, _ = _check_custom_target_through_proxy(
                proxy_url,
                target,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
            )
            target_results.append(ok)
            if ok:
                break
        results[check_id] = any(target_results)
    return results




def _probe_custom_targets_for_pool(proxy_url, custom_checks=None):
    results = {}
    for check in (custom_checks if custom_checks is not None else _load_custom_checks()):
        check_id = check.get('id')
        if not check_id:
            continue
        targets = check.get('urls') if isinstance(check.get('urls'), list) else [check.get('url', '')]
        target_results = []
        for target in targets:
            ok, _ = _check_custom_target_through_proxy(
                proxy_url,
                target,
                connect_timeout=POOL_PROBE_CUSTOM_CONNECT_TIMEOUT,
                read_timeout=POOL_PROBE_CUSTOM_READ_TIMEOUT,
            )
            target_results.append(ok)
            if ok:
                break
        results[check_id] = any(target_results)
    return results


def _check_telegram_api_through_proxy(proxy_url=None, connect_timeout=6, read_timeout=10):
    url = 'https://api.telegram.org/'
    proxies = {'https': proxy_url, 'http': proxy_url} if proxy_url else None
    try:
        response = requests.get(
            url,
            timeout=(connect_timeout, read_timeout),
            proxies=proxies,
            allow_redirects=False,
            stream=True,
        )
        status_code = response.status_code
        response.close()
        if status_code < 500:
            return True, 'Доступ к api.telegram.org подтверждён.'
        return False, f'Telegram API вернул HTTP {status_code}.'
    except requests.exceptions.ConnectTimeout:
        return False, 'Прокси не установил соединение с api.telegram.org за отведённое время.'
    except requests.exceptions.ReadTimeout:
        return False, 'Сервер Telegram не ответил вовремя через этот ключ.'
    except requests.exceptions.RequestException as exc:
        error_text = str(exc)
        if 'Missing dependencies for SOCKS support' in error_text:
            return False, 'Отсутствует поддержка SOCKS (PySocks) для проверки Telegram API.'
        if 'SSLEOFError' in error_text or 'UNEXPECTED_EOF' in error_text:
            return False, 'Прокси-сервер разорвал TLS-соединение с api.telegram.org. Обычно это означает нерабочий ключ или проблему на удалённом сервере.'
        if 'Connection refused' in error_text:
            return False, 'Локальный SOCKS-порт отклонил соединение.'
        if 'RemoteDisconnected' in error_text:
            return False, 'Удалённая сторона закрыла соединение без ответа.'
        return False, f'Проверка Telegram API завершилась ошибкой: {error_text.splitlines()[0][:240]}'


def _key_requires_xray(key_name, key_value):
    if key_name not in ['vless', 'vless2']:
        return False
    try:
        parsed = _parse_vless_key(key_value)
    except Exception:
        return False
    security = (parsed.get('security') or '').strip().lower()
    flow = (parsed.get('flow') or '').strip().lower()
    return security == 'reality' or flow == 'xtls-rprx-vision'


def _core_proxy_runtime_name():
    if os.path.exists(XRAY_SERVICE_SCRIPT):
        return 'xray'
    return 'v2ray'


def _protocol_status_for_key(key_name, key_value):
    now = time.time()
    if not key_value.strip():
        return {
            'tone': 'empty',
            'label': 'Не сохранён',
            'details': 'Ключ ещё не сохранён на роутере.',
        }
    ports = {
        'shadowsocks': localportsh_bot,
        'vmess': localportvmess,
        'vless': localportvless,
        'vless2': localportvless2,
        'trojan': localporttrojan_bot,
    }
    port = ports.get(key_name)
    endpoint_ok, endpoint_message = _check_local_proxy_endpoint(key_name, port)
    if not endpoint_ok:
        return {
            'tone': 'fail',
            'label': 'Не работает',
            'details': f'{endpoint_message} {APP_PROXY_USER_LABEL} не может использовать этот ключ.',
        }

    if _key_requires_xray(key_name, key_value) and _core_proxy_runtime_name() != 'xray':
        return {
            'tone': 'warn',
            'label': 'Требует Xray',
            'details': (f'{endpoint_message} Этот ключ использует VLESS Reality/XTLS и должен работать через Xray, '
                        'а сейчас активен V2Ray. Локальный SOCKS поднят, но внешний трафик через ключ может не пройти.'),
        }

    proxy_url = proxy_settings.get(key_name)
    api_ok, api_message = _check_telegram_api_through_proxy(
        proxy_url,
        connect_timeout=5,
        read_timeout=8,
    )
    api_transient = (not api_ok) and _is_transient_telegram_api_failure(api_message)
    yt_ok, yt_message = _check_http_through_proxy(
        proxy_url,
        url='https://www.youtube.com',
        connect_timeout=2,
        read_timeout=3,
    )
    custom_checks = _load_custom_checks()
    cached_probe = _load_key_probe_cache().get(_hash_key(key_value), {})
    custom_states = _web_custom_probe_states(cached_probe, custom_checks)
    if api_transient:
        _record_key_probe(key_name, key_value, yt_ok=yt_ok)
    else:
        _record_key_probe(key_name, key_value, tg_ok=api_ok, yt_ok=yt_ok)
    custom_ok = any(state == 'ok' for state in custom_states.values())
    any_ok = api_ok or yt_ok or custom_ok
    service_parts = [
        f'Telegram: {"работает" if api_ok else ("перепроверяется" if api_transient else "не работает")}',
        f'YouTube: {"работает" if yt_ok else "не работает"}',
    ]
    for check in custom_checks:
        check_id = check.get('id')
        state = custom_states.get(check_id)
        if state in ('ok', 'fail'):
            service_parts.append(f'{check.get("label", "Сервис")}: {"работает" if state == "ok" else "не работает"}')
    details = f'Показан результат проверки активного ключа. {endpoint_message} ' + ', '.join(service_parts) + '.'
    if endpoint_ok and api_transient:
        return {
            'tone': 'warn',
            'label': 'Проверяется',
            'details': (f'{endpoint_message} Telegram API не ответил вовремя, идёт повторная проверка. '
                        'Статус обновится без перезагрузки страницы.').strip(),
            'endpoint_ok': endpoint_ok,
            'endpoint_message': endpoint_message,
            'api_ok': False,
            'api_message': api_message,
            'api_pending': True,
            'yt_ok': yt_ok,
            'yt_message': yt_message,
            'custom': custom_states,
        }
    return {
        'tone': 'ok' if api_ok else ('warn' if any_ok else 'fail'),
        'label': 'Работает' if api_ok else ('Частично работает' if any_ok else 'Не работает'),
        'details': details.strip(),
        'endpoint_ok': endpoint_ok,
        'endpoint_message': endpoint_message,
        'api_ok': api_ok,
        'api_message': api_message,
        'yt_ok': yt_ok,
        'yt_message': yt_message,
        'custom': custom_states,
    }
def _cached_protocol_status_for_key(key_name, key_value, custom_checks=None):
    if not key_value.strip():
        return {
            'tone': 'empty',
            'label': 'Не сохранён',
            'details': 'Ключ ещё не сохранён на роутере.',
        }
    custom_checks = custom_checks if custom_checks is not None else _load_custom_checks()
    probe = _load_key_probe_cache().get(_hash_key(key_value), {})
    custom_states = _web_custom_probe_states(probe, custom_checks)
    has_probe_result = (
        'tg_ok' in probe or
        'yt_ok' in probe or
        any(state in ('ok', 'fail') for state in custom_states.values())
    )
    if has_probe_result:
        api_ok = bool(probe.get('tg_ok')) if 'tg_ok' in probe else False
        yt_ok = bool(probe.get('yt_ok')) if 'yt_ok' in probe else False
        custom_ok = any(state == 'ok' for state in custom_states.values())
        any_ok = api_ok or yt_ok or custom_ok
        service_parts = []
        if 'tg_ok' in probe:
            service_parts.append(f'Telegram: {"работает" if api_ok else "не работает"}')
        if 'yt_ok' in probe:
            service_parts.append(f'YouTube: {"работает" if yt_ok else "не работает"}')
        for check in custom_checks:
            check_id = check.get('id')
            state = custom_states.get(check_id)
            if state in ('ok', 'fail'):
                service_parts.append(f'{check.get("label", "Сервис")}: {"работает" if state == "ok" else "не работает"}')
        details = 'Показан последний результат проверки пула.'
        if service_parts:
            details += ' ' + ', '.join(service_parts) + '.'
        return {
            'tone': 'ok' if api_ok else ('warn' if any_ok else 'fail'),
            'label': 'Работает' if api_ok else ('Частично работает' if any_ok else 'Не работает'),
            'details': details,
            'endpoint_ok': None,
            'endpoint_message': '',
            'api_ok': api_ok,
            'api_message': '',
            'yt_ok': yt_ok,
            'yt_message': '',
            'custom': custom_states,
        }
    return {
        'tone': 'warn',
        'label': 'Не проверялся',
        'details': 'Ключ ждёт фоновой проверки. Чтобы не перегружать роутер, ключи проверяются по одному.',
        'endpoint_ok': None,
        'endpoint_message': '',
        'api_ok': False,
        'api_message': '',
        'yt_ok': False,
        'yt_message': '',
        'custom': custom_states,
    }




def _placeholder_protocol_statuses(current_keys):
    result = {}
    for key_name, key_value in current_keys.items():
        if key_value.strip():
            result[key_name] = {
                'tone': 'warn',
                'label': 'Проверяется',
                'details': 'Фоновая проверка ключа выполняется. Статус обновится без перезагрузки страницы.',
            }
        else:
            result[key_name] = {
                'tone': 'empty',
                'label': 'Не сохранён',
                'details': 'Ключ ещё не сохранён на роутере.',
            }
    return result



def _web_command_label(command):
    labels = {
        'install_original': 'Установить оригинальную версию',
        'update': 'Переустановить из форка без сброса',
        'update_independent': 'Переустановка (ветка independent)',
        'update_no_bot': 'Переустановка (без Telegram бота)',
        'remove': 'Удалить компоненты',
        'restart_services': 'Перезапустить сервисы',
        'dns_on': 'DNS Override ВКЛ',
        'dns_off': 'DNS Override ВЫКЛ',
        'reboot': 'Перезагрузить роутер',
    }
    return labels.get(command, command)


def _get_web_command_state():
    with web_command_lock:
        return dict(web_command_state)


def _consume_web_command_state_for_render():
    with web_command_lock:
        snapshot = dict(web_command_state)
        if (snapshot.get('label') and not snapshot.get('running') and
                snapshot.get('finished_at') and snapshot.get('shown_after_finish')):
            cleared = {
                'running': False,
                'command': '',
                'label': '',
                'result': '',
                'progress': 0,
                'progress_label': '',
                'started_at': 0,
                'finished_at': 0,
                'shown_after_finish': False,
            }
            web_command_state.update(cleared)
            return cleared
        elif snapshot.get('label') and not snapshot.get('running') and snapshot.get('finished_at'):
            web_command_state['shown_after_finish'] = True
        return snapshot


def _estimate_web_command_progress(command, result_text):
    if command not in ('update', 'update_independent', 'update_no_bot'):
        return 0, ''
    if not result_text:
        return 5, 'Подготовка запуска обновления'

    progress_steps = [
        ('Прокси запущен.', 100, 'Прокси перезапущен, обновление завершено'),
        ('Обновление выполнено. Сервисы перезапущены.', 96, 'Сервисы обновлены, идёт перезапуск прокси'),
        ('Версия прокси', 90, 'Проверка версии и завершение обновления'),
        ('Обновления скачены, права настроены.', 82, 'Новые файлы установлены'),
        ('Бэкап создан.', 70, 'Резервная копия готова, идёт замена файлов'),
        ('Сервисы остановлены.', 60, 'Сервисы остановлены перед заменой файлов'),
        ('Файлы успешно скачаны и подготовлены.', 45, 'Файлы загружены, подготавливается установка'),
        ('Скачиваем обновления во временную папку и проверяем файлы.', 30, 'Идёт загрузка файлов из GitHub'),
        ('Пакеты обновлены.', 20, 'Пакеты Entware обновлены'),
        ('Начинаем обновление.', 12, 'Запущен сценарий обновления'),
        ('Скрипт загружен из', 8, 'Сценарий обновления получен с GitHub'),
        ('Legacy-пути уже доступны.', 6, 'Проверка путей запуска'),
        ('Подготовка legacy-путей:', 6, 'Подготовка путей запуска'),
        ('Подготовка Entware DNS:', 4, 'Проверка доступа Entware и GitHub'),
    ]
    for marker, percent, label in progress_steps:
        if marker in result_text:
            return percent, label
    return 8, 'Обновление запущено'


def _set_web_command_progress(command, result_text):
    progress, progress_label = _estimate_web_command_progress(command, result_text)
    with web_command_lock:
        web_command_state['result'] = result_text
        web_command_state['progress'] = progress
        web_command_state['progress_label'] = progress_label
        web_command_state['shown_after_finish'] = False


def _set_web_flash_message(message):
    global web_flash_message
    with web_flash_lock:
        web_flash_message = message or ''


def _consume_web_flash_message():
    global web_flash_message
    with web_flash_lock:
        message = web_flash_message
        web_flash_message = ''
    return message


def _finish_web_command(command, result):
    with web_command_lock:
        web_command_state['running'] = False
        web_command_state['command'] = command
        web_command_state['label'] = _web_command_label(command)
        web_command_state['result'] = result
        web_command_state['progress'] = 100 if command in ('update', 'update_independent', 'update_no_bot') else web_command_state.get('progress', 0)
        web_command_state['progress_label'] = 'Завершено' if command in ('update', 'update_independent', 'update_no_bot') else ''
        web_command_state['finished_at'] = time.time()
        web_command_state['shown_after_finish'] = False


def _execute_web_command(command):
    try:
        result = _run_web_command(command)
    except Exception as exc:
        result = f'Ошибка выполнения команды: {exc}'
    _finish_web_command(command, result)


def _start_web_command(command):
    label = _web_command_label(command)
    with web_command_lock:
        if web_command_state['running']:
            current_label = web_command_state['label'] or web_command_state['command']
            return False, f'⏳ Уже выполняется команда: {current_label}. Дождитесь завершения текущего запуска.'
        web_command_state['running'] = True
        web_command_state['command'] = command
        web_command_state['label'] = label
        web_command_state['result'] = ''
        web_command_state['progress'] = 5 if command in ('update', 'update_independent', 'update_no_bot') else 0
        web_command_state['progress_label'] = 'Подготовка запуска обновления' if command in ('update', 'update_independent', 'update_no_bot') else ''
        web_command_state['started_at'] = time.time()
        web_command_state['finished_at'] = 0
        web_command_state['shown_after_finish'] = False
    thread = threading.Thread(target=_execute_web_command, args=(command,), daemon=True)
    thread.start()
    return True, f'⏳ Команда "{label}" запущена. Статус обновится без перезагрузки страницы.'


def _load_bot_autostart():
    try:
        with open(BOT_AUTOSTART_FILE, 'r', encoding='utf-8') as file:
            return file.read().strip() == '1'
    except Exception:
        return False


def _invalidate_web_status_cache():
    _invalidate_status_snapshot_cache()


def _last_proxy_disable_reason():
    try:
        for log_path in RUNTIME_ERROR_LOG_PATHS:
            if not os.path.exists(log_path):
                continue
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as file:
                lines = file.readlines()
            for line in reversed(lines[-80:]):
                marker = 'Прокси-режим '
                if marker not in line or ' отключён при старте: ' not in line:
                    continue
                tail = line.split(' отключён при старте: ', 1)[1].strip()
                return tail
    except Exception:
        return ''
    return ''


def _load_proxy_mode():
    try:
        with open(PROXY_MODE_FILE, 'r', encoding='utf-8') as file:
            saved = file.read().strip()
        if saved in proxy_settings:
            return saved
    except Exception:
        pass
    return config.default_proxy_mode


def _wait_for_port(hosts, port, timeout=15):
    import socket
    if hosts is None:
        hosts = ['127.0.0.1', '::1', 'localhost']
    elif isinstance(hosts, str):
        hosts = [hosts]
    deadline = time.time() + timeout
    while time.time() < deadline:
        for host in hosts:
            try:
                addrs = socket.getaddrinfo(host, int(port), type=socket.SOCK_STREAM)
            except OSError:
                continue
            for family, socktype, proto, canonname, sockaddr in addrs:
                try:
                    with socket.socket(family, socktype, proto) as sock:
                        sock.settimeout(2)
                        sock.connect(sockaddr)
                        return True
                except OSError:
                    continue
        time.sleep(1)
    return False


def _port_is_listening(port):
    try:
        output = subprocess.check_output(['netstat', '-ltn'], stderr=subprocess.DEVNULL, text=True)
        for line in output.splitlines():
            if f':{port} ' in line or line.endswith(f':{port}'):
                return True
    except Exception:
        pass
    try:
        output = subprocess.check_output(['ss', '-ltn'], stderr=subprocess.DEVNULL, text=True)
        for line in output.splitlines():
            if f':{port} ' in line or line.endswith(f':{port}'):
                return True
    except Exception:
        pass
    return False

def _check_socks5_handshake(port, timeout=3):
    import socket
    try:
        with socket.create_connection(('127.0.0.1', int(port)), timeout=timeout) as sock:
            sock.sendall(b'\x05\x01\x00')
            data = sock.recv(2)
            return data == b'\x05\x00'
    except Exception:
        return False


def _wait_for_socks5_handshake(port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _check_socks5_handshake(port):
            return True
        time.sleep(1)
    return False


def _ensure_service_port(port, restart_cmd=None, retries=2, sleep_after_restart=5, timeout=20):
    if _wait_for_port(None, port, timeout=timeout):
        return True
    if _port_is_listening(port):
        return True
    if restart_cmd:
        for _ in range(retries):
            os.system(restart_cmd)
            time.sleep(sleep_after_restart)
            if _wait_for_port(None, port, timeout=timeout):
                return True
            if _port_is_listening(port):
                return True
    return False


def _read_tail(file_path, lines=12):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.readlines()
        if not content:
            return ''
        return ''.join(content[-lines:]).strip()
    except Exception as exc:
        return f'Не удалось прочитать {file_path}: {exc}'


def _v2ray_diagnostics():
    config_path = CORE_PROXY_CONFIG_PATH
    error_path = CORE_PROXY_ERROR_LOG
    diagnostics = []
    if not os.path.exists(config_path):
        diagnostics.append(f'Конфигурация v2ray не найдена: {config_path}')
    else:
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config_data = json.load(file)
            inbounds = config_data.get('inbounds', [])
            ports = [str(inbound.get('port', '?')) for inbound in inbounds]
            details = [f'{port}({inbound.get("protocol", "?")})' for inbound, port in zip(inbounds, ports)]
            socks_status = []
            for inbound in inbounds:
                if inbound.get('protocol') == 'socks':
                    port = inbound.get('port')
                    if port:
                        socks_status.append(f'{port}:sock5={"ok" if _check_socks5_handshake(port) else "fail"}')
            if socks_status:
                details.append('socks:' + ','.join(socks_status))
            outbounds = []
            for outbound in config_data.get('outbounds', []):
                tag = outbound.get('tag', '')
                protocol = outbound.get('protocol', '')
                if protocol in ['vless', 'vmess']:
                    vnext = outbound.get('settings', {}).get('vnext', [])
                    if vnext:
                        entry = vnext[0]
                        addr = entry.get('address', '')
                        port = entry.get('port', '')
                        outbounds.append(f'{tag}:{protocol}->{addr}:{port}')
                    else:
                        outbounds.append(f'{tag}:{protocol}')
                else:
                    outbounds.append(f'{tag}:{protocol}')
            summary = f'Конфиг v2ray валиден. inbounds: {", ".join(ports)}'
            if details:
                summary += f' ({"; ".join(details)})'
            if outbounds:
                summary += f'; outbounds: {", ".join(outbounds)}'
            diagnostics.append(summary)
        except Exception as exc:
            diagnostics.append(f'Ошибка парсинга конфига v2ray: {exc}')
    error_tail = _read_tail(error_path, lines=12)
    if error_tail:
        diagnostics.append(f'Последние строки лога v2ray ({error_path}):\n{error_tail}')
    return ' '.join(diagnostics)


def _format_proxy_key_summary(key_type, key_value):
    if key_type == 'shadowsocks':
        server, port, method, password = _decode_shadowsocks_uri(key_value)
        return ('Параметры Shadowsocks: server={server}, port={port}, method={method}, '
                'password_len={password_len}').format(
                    server=server,
                    port=port,
                    method=method,
                    password_len=len(password))
    if key_type in ['vless', 'vless2']:
        data = _parse_vless_key(key_value)
        return ('Параметры VLESS: address={address}, host={host}, port={port}, uuid={id}, network={type}, '
                'serviceName={serviceName}, sni={sni}, security={security}, flow={flow}').format(**data)
    if key_type == 'vmess':
        data = _parse_vmess_key(key_value)
        service_name = data.get('serviceName') or data.get('grpcSettings', {}).get('serviceName', '')
        return ('Параметры VMESS: host={add}, port={port}, id={id}, network={net}, tls={tls}, '
                'serviceName={service_name}').format(service_name=service_name, **data)
    if key_type == 'trojan':
        data = _parse_trojan_key(key_value)
        return ('Параметры Trojan: address={address}, port={port}, sni={sni}, security={security}, '
                'network={type}, password_len={password_len}').format(
                    address=data['address'],
                    port=data['port'],
                    sni=data['sni'],
                    security=data['security'],
                    type=data['type'],
                    password_len=len(data['password']))
    return ''


def _v2ray_outbound_summary(vmess_key=None, vless_key=None):
    try:
        config_data = _build_v2ray_config(vmess_key, vless_key)
        lines = []
        for outbound in config_data.get('outbounds', []):
            tag = outbound.get('tag', '')
            protocol = outbound.get('protocol', '')
            stream = outbound.get('streamSettings', {})
            if protocol in ['vless', 'vmess']:
                vnext = outbound.get('settings', {}).get('vnext', [])
                if vnext:
                    entry = vnext[0]
                    addr = entry.get('address', '')
                    port = entry.get('port', '')
                    lines.append(f'{tag}:{protocol} -> {addr}:{port} stream={stream}')
                else:
                    lines.append(f'{tag}:{protocol} stream={stream}')
            else:
                lines.append(f'{tag}:{protocol} stream={stream}')
        return ' '.join(lines)
    except Exception as exc:
        return f'Не удалось построить сводный outbound-конфиг: {exc}'


def _parse_trojan_key(key):
    parsed = urlparse(key)
    if parsed.scheme != 'trojan':
        raise ValueError('Неверный протокол, ожидается trojan://')
    if not parsed.hostname:
        raise ValueError('В trojan-ключе отсутствует адрес сервера')
    if not parsed.username:
        raise ValueError('В trojan-ключе отсутствует пароль')
    params = parse_qs(parsed.query)
    return {
        'address': parsed.hostname,
        'port': parsed.port or 443,
        'password': parsed.username,
        'sni': params.get('sni', [''])[0],
        'security': params.get('security', ['tls'])[0],
        'type': params.get('type', ['tcp'])[0],
        'host': params.get('host', [''])[0],
        'path': params.get('path', ['/'])[0] or '/',
        'serviceName': params.get('serviceName', [''])[0],
        'fingerprint': params.get('fp', params.get('fingerprint', ['chrome']))[0],
        'alpn': params.get('alpn', [''])[0],
        'fragment': unquote(parsed.fragment or ''),
    }


def _build_proxy_diagnostics(key_type, key_value):
    key_summary = _format_proxy_key_summary(key_type, key_value)
    if key_type not in ['vmess', 'vless', 'vless2']:
        return key_summary
    error_tail = _read_tail(CORE_PROXY_ERROR_LOG, lines=25)
    lines = [line.strip() for line in error_tail.splitlines() if line.strip()]
    last_issue = ''
    for line in reversed(lines):
        if ('failed to process outbound traffic' in line or
                'failed to find an available destination' in line or
                'dial tcp' in line or
                'lookup ' in line):
            last_issue = line
            break
    issue_summary = ''
    if last_issue:
        lookup_match = re.search(r'lookup\s+([^\s]+)', last_issue)
        dial_match = re.search(r'dial tcp\s+([^:]+:\d+)', last_issue)
        if 'server misbehaving' in last_issue and lookup_match:
            issue_summary = f'Причина: прокси-ядро не смогло разрешить адрес {lookup_match.group(1)} через локальный DNS.'
        elif 'operation was canceled' in last_issue and dial_match:
            issue_summary = f'Причина: сервер {dial_match.group(1)} не установил соединение через прокси-ядро.'
        elif 'connection refused' in last_issue and dial_match:
            issue_summary = f'Причина: сервер {dial_match.group(1)} отклонил соединение.'
        elif 'timed out' in last_issue or 'i/o timeout' in last_issue:
            issue_summary = 'Причина: соединение через прокси завершилось по таймауту.'
        elif 'failed to find an available destination' in last_issue:
            issue_summary = 'Причина: прокси-ядро не смогло построить рабочее исходящее соединение.'
    parts = []
    if issue_summary:
        parts.append(issue_summary)
    elif key_summary:
        parts.append(key_summary)
    return ' '.join(parts)


def _pool_key_display_name(key_value):
    raw_key = (key_value or '').strip()
    label = ''
    try:
        if raw_key.startswith('vmess://'):
            data = _parse_vmess_key(raw_key)
            label = data.get('ps') or data.get('add') or ''
        else:
            parsed = urlparse(raw_key)
            label = unquote(parsed.fragment or '').strip()
            if not label and parsed.hostname:
                label = parsed.hostname
    except Exception:
        label = ''

    label = re.sub(r'\s+', ' ', label).strip()
    return label or 'Ключ прокси'


POOL_PROTOCOL_ORDER = ['vless', 'vless2', 'vmess', 'trojan', 'shadowsocks']
POOL_PROTOCOL_LABELS = {
    'vless': 'Vless 1',
    'vless2': 'Vless 2',
    'vmess': 'Vmess',
    'trojan': 'Trojan',
    'shadowsocks': 'Shadowsocks',
}


def _pool_proto_label(proto):
    return POOL_PROTOCOL_LABELS.get(proto, proto)


def _pool_status_summary(current_keys=None, key_pools=None, key_probe_cache=None, custom_checks=None):
    current_keys = current_keys if current_keys is not None else _load_current_keys()
    key_pools = key_pools if key_pools is not None else _ensure_current_keys_in_pools(current_keys)
    key_probe_cache = key_probe_cache if key_probe_cache is not None else _load_key_probe_cache()
    custom_checks = custom_checks if custom_checks is not None else _load_custom_checks()
    services = [
        {'label': 'Telegram', 'field': 'tg_ok', 'id': None, 'count': 0},
        {'label': 'YouTube', 'field': 'yt_ok', 'id': None, 'count': 0},
    ]
    for check in custom_checks:
        check_id = str(check.get('id') or '').strip()
        if not check_id:
            continue
        label = str(check.get('label') or check_id).strip() or check_id
        if len(label) > 18:
            label = label[:18] + '...'
        services.append({'label': label, 'field': None, 'id': check_id, 'count': 0})

    total_count = 0
    checked_count = 0
    all_services_count = 0
    any_service_count = 0
    for proto in POOL_PROTOCOL_ORDER:
        for pool_key in key_pools.get(proto, []) or []:
            total_count += 1
            probe = key_probe_cache.get(_hash_key(pool_key), {})
            if not isinstance(probe, dict):
                probe = {}
            custom = probe.get('custom', {}) if isinstance(probe, dict) else {}
            if not isinstance(custom, dict):
                custom = {}
            results = []
            for service in services:
                if service['field']:
                    if service['field'] not in probe:
                        continue
                    ok = bool(probe.get(service['field']))
                else:
                    if service['id'] not in custom:
                        continue
                    ok = bool(custom.get(service['id']))
                results.append(ok)
                if ok:
                    service['count'] += 1
            if len(results) == len(services):
                checked_count += 1
            if results and any(results):
                any_service_count += 1
            if len(results) == len(services) and all(results):
                all_services_count += 1

    active_key_count = sum(1 for proto in POOL_PROTOCOL_ORDER if (current_keys.get(proto) or '').strip())
    service_text = '. '.join(f"{service['label']}: {service['count']}" for service in services)
    note_parts = [
        f'В пулах: {total_count}',
        f'Проверено: {checked_count}',
    ]
    if service_text:
        note_parts.append(service_text)
    note_parts.append(f'Все сервисы: {all_services_count}')
    note_parts.append(f'Хотя бы один: {any_service_count}')
    note = '. '.join(note_parts) + '.'
    return {
        'active_key_count': active_key_count,
        'protocol_count': len(POOL_PROTOCOL_ORDER),
        'active_text': f'{active_key_count} / {len(POOL_PROTOCOL_ORDER)} активных ключей',
        'note': note,
        'pool_total_count': total_count,
        'checked_pool_count': checked_count,
        'all_services_count': all_services_count,
        'any_service_count': any_service_count,
        'services': [{'label': service['label'], 'count': service['count']} for service in services],
    }


def _pool_keys_for_proto(proto):
    pools = _ensure_current_keys_in_pools()
    return list(pools.get(proto, []) or [])


def _v2ray_key_file_candidates(file_path):
    paths = [file_path]
    file_name = os.path.basename(file_path)
    for directory in (XRAY_CONFIG_DIR, V2RAY_CONFIG_DIR):
        candidate = os.path.join(directory, file_name)
        if candidate not in paths:
            paths.append(candidate)
    return paths


def _remove_file_if_exists(file_path):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as exc:
        _write_runtime_log(f'Не удалось удалить {file_path}: {exc}')


def _clear_installed_key_for_protocol(proto):
    if proto == 'vmess':
        for file_path in _v2ray_key_file_candidates(VMESS_KEY_PATH):
            _remove_file_if_exists(file_path)
    elif proto == 'vless':
        for file_path in _v2ray_key_file_candidates(VLESS_KEY_PATH):
            _remove_file_if_exists(file_path)
    elif proto == 'vless2':
        for file_path in _v2ray_key_file_candidates(VLESS2_KEY_PATH):
            _remove_file_if_exists(file_path)
    elif proto == 'shadowsocks':
        _remove_file_if_exists('/opt/etc/shadowsocks.json')
    elif proto == 'trojan':
        _remove_file_if_exists('/opt/etc/trojan/config.json')
    else:
        raise ValueError('Неизвестный протокол')
    if _load_proxy_mode() == proto:
        update_proxy('none')
    _write_all_proxy_core_config()
    _restart_proxy_services_for_protocols([proto])


def _delete_pool_key(proto, key_value):
    pools, removed = key_pool_store.delete_pool_key(_load_key_pools(), proto, key_value)
    if not removed:
        raise ValueError('\u041a\u043b\u044e\u0447 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0432 \u043f\u0443\u043b\u0435.')
    current_key = (_load_current_keys().get(proto) or '').strip()
    was_current = bool(current_key and current_key == key_value)
    keys = _dedupe_key_list(pools.get(proto, []) or [])
    promoted_key = keys[0] if was_current and keys else ''
    if promoted_key:
        _install_key_for_protocol(proto, promoted_key, verify=False)
        pools = key_pool_store.set_active_key(pools, proto, promoted_key)
    elif was_current:
        _clear_installed_key_for_protocol(proto)
    _save_key_pools(pools)
    with key_probe_cache_lock:
        cache = _load_key_probe_cache()
        cache.pop(_hash_key(key_value), None)
        _save_key_probe_cache(cache)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()


def _clear_pool(proto):
    pools, removed_keys = key_pool_store.clear_pool(_load_key_pools(), proto)
    _save_key_pools(pools)
    current_key = (_load_current_keys().get(proto) or '').strip()
    if current_key and current_key in removed_keys:
        _clear_installed_key_for_protocol(proto)
    if removed_keys:
        with key_probe_cache_lock:
            cache = _load_key_probe_cache()
            for key_value in removed_keys:
                cache.pop(_hash_key(key_value), None)
            _save_key_probe_cache(cache)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return len(removed_keys)

def _failed_custom_probe_results(custom_checks):
    return {
        check.get('id'): False
        for check in (custom_checks or [])
        if check.get('id')
    }


def _available_memory_kb():
    try:
        with open('/proc/meminfo', 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                if line.startswith('MemAvailable:'):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
    except Exception:
        pass
    return None


def _set_pool_probe_progress(**updates):
    with pool_probe_progress_lock:
        pool_probe_progress.update(updates)


def _get_pool_probe_progress():
    with pool_probe_progress_lock:
        return dict(pool_probe_progress)


def _pool_probe_progress_label(progress=None):
    progress = progress or _get_pool_probe_progress()
    scope = progress.get('scope')
    if scope == 'auto_missing':
        return 'Автопроверка непроверенных ключей'
    if scope == 'manual_all':
        return 'Полная проверка всех ключей'
    if scope == 'protocol':
        return 'Проверка выбранного пула'
    return 'Фоновая проверка пула ключей'


def _pool_probe_timeout_budget(custom_checks=None, task_count=1, workers=1):
    custom_target_count = 0
    for check in custom_checks or []:
        targets = check.get('urls') if isinstance(check.get('urls'), list) else [check.get('url', '')]
        custom_target_count += len([target for target in targets[:2] if target])
    base_per_key = (
        POOL_PROBE_TG_CONNECT_TIMEOUT + POOL_PROBE_TG_READ_TIMEOUT +
        POOL_PROBE_HTTP_CONNECT_TIMEOUT + POOL_PROBE_HTTP_READ_TIMEOUT +
        custom_target_count * (POOL_PROBE_CUSTOM_CONNECT_TIMEOUT + POOL_PROBE_CUSTOM_READ_TIMEOUT)
    )
    retry_per_key = POOL_PROBE_TG_CONNECT_TIMEOUT + POOL_PROBE_TG_READ_TIMEOUT
    per_key = max(POOL_PROBE_SINGLE_TIMEOUT_SECONDS, base_per_key + retry_per_key + 5.0)
    workers = max(1, int(workers or 1))
    task_count = max(1, int(task_count or 1))
    waves = (task_count + workers - 1) // workers
    return max(POOL_PROBE_BATCH_TIMEOUT_SECONDS, per_key * waves + 5.0)


def _check_pool_key_through_proxy(proto, key_value, custom_checks=None, proxy_url=None):
    proxy_url = proxy_url or proxy_settings.get(proto)
    tg_ok, _ = _check_telegram_api_through_proxy(
        proxy_url,
        connect_timeout=POOL_PROBE_TG_CONNECT_TIMEOUT,
        read_timeout=POOL_PROBE_TG_READ_TIMEOUT,
    )
    yt_ok, _ = _check_http_through_proxy(
        proxy_url,
        connect_timeout=POOL_PROBE_HTTP_CONNECT_TIMEOUT,
        read_timeout=POOL_PROBE_HTTP_READ_TIMEOUT,
    )
    if not tg_ok and not yt_ok:
        time.sleep(POOL_PROBE_RETRY_DELAY_SECONDS)
        tg_ok, _ = _check_telegram_api_through_proxy(
            proxy_url,
            connect_timeout=POOL_PROBE_TG_CONNECT_TIMEOUT,
            read_timeout=POOL_PROBE_TG_READ_TIMEOUT,
        )
        yt_ok, _ = _check_http_through_proxy(
            proxy_url,
            connect_timeout=POOL_PROBE_HTTP_CONNECT_TIMEOUT,
            read_timeout=POOL_PROBE_HTTP_READ_TIMEOUT,
        )
    elif not yt_ok:
        time.sleep(POOL_PROBE_RETRY_DELAY_SECONDS)
        yt_ok, _ = _check_http_through_proxy(
            proxy_url,
            connect_timeout=POOL_PROBE_HTTP_CONNECT_TIMEOUT,
            read_timeout=POOL_PROBE_HTTP_READ_TIMEOUT,
        )
    record_tg_ok = tg_ok if (tg_ok or not yt_ok) else 'unknown'
    _record_key_probe(proto, key_value, tg_ok=record_tg_ok, yt_ok=yt_ok)
    if custom_checks and not tg_ok and not yt_ok:
        _record_key_probe(proto, key_value, custom=_failed_custom_probe_results(custom_checks))
        return
    if custom_checks:
        custom_results = _probe_custom_targets_for_pool(
            proxy_url,
            custom_checks=custom_checks,
        )
        _record_key_probe(proto, key_value, custom=custom_results)


def _pool_probe_socks_inbound(port, tag):
    return {
        'port': int(port),
        'listen': '127.0.0.1',
        'protocol': 'socks',
        'settings': {'auth': 'noauth', 'udp': True, 'ip': '127.0.0.1'},
        'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
        'tag': tag,
    }


def _proxy_outbound_from_key(proto, key_value, tag, email='t@t.tt'):
    if proto == 'shadowsocks':
        server, port, method, password = _decode_shadowsocks_uri(key_value)
        return {
            'tag': tag,
            'protocol': 'shadowsocks',
            'settings': {
                'servers': [{
                    'address': server,
                    'port': int(port),
                    'method': method,
                    'password': password,
                    'level': 0,
                }]
            },
        }
    if proto == 'vmess':
        data = _parse_vmess_key(key_value)
        stream_settings = {'network': data.get('net', 'tcp')}
        tls_mode = data.get('tls', 'tls')
        if tls_mode in ['tls', 'xtls']:
            stream_settings['security'] = tls_mode
            stream_settings[f'{tls_mode}Settings'] = {
                'allowInsecure': True,
                'serverName': data.get('add', ''),
            }
        else:
            stream_settings['security'] = 'none'
        if stream_settings['network'] == 'ws':
            stream_settings['wsSettings'] = {
                'path': data.get('path', '/'),
                'headers': {'Host': data.get('host', '')},
            }
        elif stream_settings['network'] == 'grpc':
            grpc_service = data.get('serviceName', '') or data.get('grpcSettings', {}).get('serviceName', '')
            stream_settings['grpcSettings'] = {'serviceName': grpc_service, 'multiMode': False}
        return {
            'tag': tag,
            'domainStrategy': 'UseIPv4',
            'protocol': 'vmess',
            'settings': {
                'vnext': [{
                    'address': data['add'],
                    'port': int(data['port']),
                    'users': [{
                        'id': data['id'],
                        'alterId': int(data.get('aid', 0)),
                        'email': email,
                        'security': 'auto',
                    }],
                }]
            },
            'streamSettings': stream_settings,
            'mux': {'enabled': True, 'concurrency': -1, 'xudpConcurrency': 16, 'xudpProxyUDP443': 'reject'},
        }
    if proto in ('vless', 'vless2'):
        data = _parse_vless_key(key_value)
        network = data.get('type', 'tcp') or 'tcp'
        security = data.get('security', 'none')
        stream_settings = {'network': network}
        if security in ['tls', 'xtls']:
            stream_settings['security'] = security
            stream_settings[f'{security}Settings'] = {
                'allowInsecure': True,
                'serverName': data.get('sni', ''),
            }
        elif security == 'reality':
            stream_settings['security'] = 'reality'
            stream_settings['realitySettings'] = {
                'serverName': data.get('sni', '') or data.get('host', '') or data.get('address', ''),
                'publicKey': data.get('publicKey', ''),
                'shortId': data.get('shortId', ''),
                'fingerprint': data.get('fingerprint', 'chrome'),
                'spiderX': data.get('spiderX', '/'),
            }
            if data.get('alpn'):
                stream_settings['realitySettings']['alpn'] = [item.strip() for item in data['alpn'].split(',') if item.strip()]
        else:
            stream_settings['security'] = 'none'
        if network == 'ws':
            stream_settings['wsSettings'] = {
                'path': data.get('path', '/'),
                'headers': {'Host': data.get('host', '')},
            }
        elif network == 'grpc':
            stream_settings['grpcSettings'] = {'serviceName': data.get('serviceName', ''), 'multiMode': False}
        return {
            'tag': tag,
            'domainStrategy': 'UseIPv4',
            'protocol': 'vless',
            'settings': {
                'vnext': [{
                    'address': data.get('address', data.get('host', '')),
                    'port': int(data['port']),
                    'users': [{
                        'id': data['id'],
                        'encryption': data.get('encryption', 'none'),
                        'flow': data.get('flow', ''),
                        'level': 0,
                    }],
                }]
            },
            'streamSettings': stream_settings,
        }
    if proto == 'trojan':
        data = _parse_trojan_key(key_value)
        stream_settings = {'network': data.get('type', 'tcp') or 'tcp', 'security': 'none'}
        if data.get('security', 'tls') == 'tls':
            stream_settings['security'] = 'tls'
            stream_settings['tlsSettings'] = {
                'allowInsecure': True,
                'serverName': data.get('sni') or data.get('host') or data.get('address', ''),
                'fingerprint': data.get('fingerprint', 'chrome'),
            }
            if data.get('alpn'):
                stream_settings['tlsSettings']['alpn'] = [item.strip() for item in data['alpn'].split(',') if item.strip()]
        if stream_settings['network'] == 'ws':
            stream_settings['wsSettings'] = {
                'path': data.get('path', '/'),
                'headers': {'Host': data.get('host') or data.get('sni') or data.get('address', '')},
            }
        elif stream_settings['network'] == 'grpc':
            stream_settings['grpcSettings'] = {'serviceName': data.get('serviceName', ''), 'multiMode': False}
        return {
            'tag': tag,
            'protocol': 'trojan',
            'settings': {
                'servers': [{
                    'address': data['address'],
                    'port': int(data['port']),
                    'password': data['password'],
                    'level': 0,
                }]
            },
            'streamSettings': stream_settings,
        }
    raise ValueError(f'Unsupported protocol: {proto}')


def _pool_probe_outbound(proto, key_value, tag):
    return _proxy_outbound_from_key(proto, key_value, tag, email='pool-probe@local')


def _build_pool_probe_core_config_batch(probe_tasks):
    config_json = {
        'log': {
            'access': '/dev/null',
            'error': '/dev/null',
            'loglevel': 'warning',
        },
        'dns': {
            'hosts': {
                'api.telegram.org': '149.154.167.220',
            },
            'servers': ['8.8.8.8', '1.1.1.1', 'localhost'],
            'queryStrategy': 'UseIPv4',
        },
        'inbounds': [],
        'outbounds': [],
        'routing': {
            'domainStrategy': 'IPIfNonMatch',
            'rules': [],
        },
    }
    test_routes = []
    for offset, (proto, key_value) in enumerate(probe_tasks):
        port = str(int(POOL_PROBE_TEST_PORT) + offset)
        inbound_tag = f'in-pool-probe-{offset}'
        outbound_tag = f'proxy-pool-probe-{offset}'
        config_json.setdefault('inbounds', []).append(_pool_probe_socks_inbound(port, inbound_tag))
        config_json.setdefault('outbounds', []).append(_pool_probe_outbound(proto, key_value, outbound_tag))
        test_routes.append({
            'type': 'field',
            'inboundTag': [inbound_tag],
            'outboundTag': outbound_tag,
            'enabled': True,
        })
    config_json['outbounds'].append({'protocol': 'freedom', 'tag': 'direct'})
    config_json['routing']['rules'] = test_routes
    return config_json


def _start_pool_probe_xray(config_json):
    xray_binary = shutil.which('xray') or '/opt/sbin/xray'
    config_path = f'/tmp/bypass_pool_probe_{os.getpid()}_{threading.get_ident()}.json'
    with open(config_path, 'w', encoding='utf-8') as file:
        json.dump(config_json, file, ensure_ascii=False, separators=(',', ':'))
    preexec_fn = None
    if os.name == 'posix' and hasattr(os, 'nice'):
        def lower_priority():
            try:
                os.nice(10)
            except Exception:
                pass
        preexec_fn = lower_priority
    process = subprocess.Popen(
        [xray_binary, 'run', '-c', config_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        preexec_fn=preexec_fn,
    )
    return process, config_path


def _stop_pool_probe_xray(process, config_path):
    pid = None
    try:
        pid = process.pid if process else None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                    process.wait(timeout=2)
                except Exception:
                    if pid:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except Exception:
                            pass
    except Exception:
        pass
    if pid:
        try:
            os.waitpid(pid, os.WNOHANG)
        except Exception:
            pass
    try:
        if config_path and os.path.exists(config_path):
            os.remove(config_path)
    except Exception:
        pass


def _find_pool_failover_candidate(candidates, service='telegram'):
    """Find one working pool key through a temporary xray before touching the active proxy."""
    probe_tasks = [(proto, (key_value or '').strip()) for proto, key_value in candidates if (key_value or '').strip()]
    while probe_tasks:
        raw_batch = probe_tasks[:POOL_PROBE_BATCH_SIZE]
        del probe_tasks[:POOL_PROBE_BATCH_SIZE]
        valid_batch = []
        for proto, key_value in raw_batch:
            try:
                _pool_probe_outbound(proto, key_value, 'proxy-failover-validate')
                valid_batch.append((proto, key_value))
            except Exception as exc:
                _write_runtime_log(f'Auto-failover: ключ {proto} не подготовлен для проверки: {exc}')
        if not valid_batch:
            continue

        process = None
        config_path = None
        try:
            process, config_path = _start_pool_probe_xray(_build_pool_probe_core_config_batch(valid_batch))
            for offset, (proto, key_value) in enumerate(valid_batch):
                port = str(int(POOL_PROBE_TEST_PORT) + offset)
                if not _wait_for_socks5_handshake(port, timeout=6):
                    _write_runtime_log(
                        f'Auto-failover: тестовый SOCKS-порт {port} не поднялся для {_pool_proto_label(proto)}; '
                        'прежний статус ключа оставлен без изменений.'
                    )
                    continue
                proxy_url = f'socks5h://127.0.0.1:{port}'
                if service == 'youtube':
                    primary_ok, _ = _check_http_through_proxy(
                        proxy_url,
                        url='https://www.youtube.com',
                        connect_timeout=POOL_PROBE_HTTP_CONNECT_TIMEOUT,
                        read_timeout=POOL_PROBE_HTTP_READ_TIMEOUT,
                    )
                    tg_ok, _ = _check_telegram_api_through_proxy(
                        proxy_url,
                        connect_timeout=POOL_PROBE_TG_CONNECT_TIMEOUT,
                        read_timeout=POOL_PROBE_TG_READ_TIMEOUT,
                    )
                    yt_ok = primary_ok
                else:
                    primary_ok, _ = _check_telegram_api_through_proxy(
                        proxy_url,
                        connect_timeout=POOL_PROBE_TG_CONNECT_TIMEOUT,
                        read_timeout=POOL_PROBE_TG_READ_TIMEOUT,
                    )
                    tg_ok = primary_ok
                    yt_ok, _ = _check_http_through_proxy(
                        proxy_url,
                        url='https://www.youtube.com',
                        connect_timeout=POOL_PROBE_HTTP_CONNECT_TIMEOUT,
                        read_timeout=POOL_PROBE_HTTP_READ_TIMEOUT,
                    )
                _record_key_probe(proto, key_value, tg_ok=tg_ok, yt_ok=yt_ok)
                if primary_ok:
                    return proto, key_value, tg_ok, yt_ok
        except Exception as exc:
            _write_runtime_log(f'Auto-failover: ошибка проверки кандидатов через временный xray: {exc}')
        finally:
            _stop_pool_probe_xray(process, config_path)
            _cleanup_pool_probe_runtime(kill_processes=True)
            gc.collect()
    return None


def _cleanup_pool_probe_runtime(kill_processes=False):
    if kill_processes:
        try:
            output = subprocess.check_output(
                ['pgrep', '-f', '/tmp/bypass_pool_probe_'],
                stderr=subprocess.DEVNULL,
            ).decode('utf-8', errors='ignore')
            for raw_pid in output.split():
                try:
                    pid = int(raw_pid)
                except ValueError:
                    continue
                if pid != os.getpid():
                    os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        time.sleep(0.2)
        try:
            output = subprocess.check_output(
                ['pgrep', '-f', '/tmp/bypass_pool_probe_'],
                stderr=subprocess.DEVNULL,
            ).decode('utf-8', errors='ignore')
            for raw_pid in output.split():
                try:
                    pid = int(raw_pid)
                except ValueError:
                    continue
                if pid != os.getpid():
                    os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

    try:
        for name in os.listdir('/tmp'):
            if name.startswith('bypass_pool_probe_') and name.endswith('.json'):
                try:
                    os.remove(os.path.join('/tmp', name))
                except Exception:
                    pass
    except Exception:
        pass


def _select_pool_probe_tasks(tasks, max_keys=None, stale_only=False, missing_only=False):
    custom_checks = _load_custom_checks()
    cache = _load_key_probe_cache() if stale_only or missing_only else {}
    now = time.time()
    selected = []
    seen = set()
    for proto, key_value in tasks:
        key_value = (key_value or '').strip()
        if proto not in POOL_PROTOCOL_ORDER or not key_value:
            continue
        task_id = (proto, _hash_key(key_value))
        if task_id in seen:
            continue
        seen.add(task_id)
        if missing_only and _key_probe_has_required_results(cache.get(_hash_key(key_value)), custom_checks=custom_checks):
            continue
        if stale_only and _key_probe_is_fresh(cache.get(_hash_key(key_value)), now=now, custom_checks=custom_checks):
            continue
        selected.append((proto, key_value))
        if max_keys is not None and len(selected) >= max_keys:
            break
    return selected, custom_checks


def _queue_pool_key_probe(tasks, max_keys=None, stale_only=False, missing_only=False, scope='manual'):
    selected, custom_checks = _select_pool_probe_tasks(
        tasks,
        max_keys=max_keys,
        stale_only=stale_only,
        missing_only=missing_only,
    )
    if POOL_PROBE_ACTIVE_ONLY:
        current_keys = _load_current_keys()
        selected = [
            (proto, key_value)
            for proto, key_value in selected
            if key_value == (current_keys.get(proto) or '').strip()
        ]
    if not selected:
        return False, 0
    if not pool_probe_lock.acquire(blocking=False):
        return False, len(selected)

    _set_pool_probe_progress(
        running=True,
        checked=0,
        total=len(selected),
        scope=scope,
        started_at=time.time(),
        finished_at=0,
    )

    def invalidate_probe_status():
        _invalidate_web_status_cache()
        _invalidate_key_status_cache()

    def worker(probe_tasks, checks):
        checked = 0
        total = len(probe_tasks)
        try:
            checked, total = run_pool_probe_worker(
                probe_tasks,
                checks,
                batch_size=POOL_PROBE_BATCH_SIZE,
                concurrency=POOL_PROBE_CONCURRENCY,
                delay_seconds=POOL_PROBE_DELAY_SECONDS,
                min_available_kb=POOL_PROBE_MIN_AVAILABLE_KB,
                test_port=POOL_PROBE_TEST_PORT,
                available_memory_kb=_available_memory_kb,
                log=_write_runtime_log,
                proto_label=_pool_proto_label,
                hash_key=_hash_key,
                set_checked=lambda value: _set_pool_probe_progress(checked=value),
                validate_outbound=lambda proto, key_value: _pool_probe_outbound(
                    proto,
                    key_value,
                    'proxy-pool-probe-validate',
                ),
                failed_custom_results=_failed_custom_probe_results,
                record_key_probe=_record_key_probe,
                start_xray_for_batch=lambda valid_batch: _start_pool_probe_xray(
                    _build_pool_probe_core_config_batch(valid_batch)
                ),
                wait_for_socks5=_wait_for_socks5_handshake,
                check_pool_key=_check_pool_key_through_proxy,
                timeout_budget=_pool_probe_timeout_budget,
                stop_xray=_stop_pool_probe_xray,
                cleanup_runtime=_cleanup_pool_probe_runtime,
                invalidate_caches=invalidate_probe_status,
            )
        finally:
            invalidate_probe_status()
            _set_pool_probe_progress(
                running=False,
                checked=checked,
                total=total,
                scope=scope,
                finished_at=time.time(),
            )
            pool_probe_lock.release()
            gc.collect()

    threading.Thread(target=worker, args=(selected, custom_checks), daemon=True).start()
    return True, len(selected)


def _probe_pool_keys_background(proto, keys, max_keys=KEY_PROBE_MAX_PER_RUN, stale_only=True, scope='protocol'):
    if POOL_PROBE_ACTIVE_ONLY:
        current_key = (_load_current_keys().get(proto) or '').strip()
        keys = [current_key] if current_key and current_key in (keys or []) else []
        stale_only = False
    return _queue_pool_key_probe(
        [(proto, key_value) for key_value in (keys or [])],
        max_keys=max_keys,
        stale_only=stale_only,
        scope=scope,
    )


def _add_keys_to_pool(proto, keys_text):
    pools, added_keys = key_pool_store.add_keys_to_pool(_load_key_pools(), proto, keys_text)
    _save_key_pools(pools)
    _probe_pool_keys_background(proto, added_keys)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return len(added_keys)


def _web_probe_state(probe, key):
    if not probe or key not in probe:
        return 'unknown'
    value = probe.get(key)
    if value is None:
        return 'unknown'
    return 'ok' if value else 'fail'


def _web_probe_checked_at(probe):
    try:
        ts = float((probe or {}).get('ts', 0))
    except (TypeError, ValueError):
        ts = 0
    if not ts:
        return ''
    return time.strftime('%d.%m %H:%M', time.localtime(ts))


def _web_custom_probe_states(probe, custom_checks=None):
    custom = (probe or {}).get('custom', {})
    if not isinstance(custom, dict):
        custom = {}
    result = {}
    for check in (custom_checks if custom_checks is not None else _load_custom_checks()):
        check_id = check.get('id')
        if not check_id:
            continue
        if check_id in custom:
            result[check_id] = 'ok' if custom.get(check_id) else 'fail'
        else:
            result[check_id] = 'unknown'
    return result


def _web_custom_checks():
    return [
        {
            'id': check.get('id', ''),
            'label': check.get('label', ''),
            'url': check.get('url', ''),
            'urls': check.get('urls') or [check.get('url', '')],
            'routes': check.get('routes') or [],
            'badge': check.get('badge', 'WEB'),
            'icon': check.get('icon', ''),
        }
        for check in _load_custom_checks()
    ]


def _web_custom_check_badges(probe, custom_checks=None):
    checks = custom_checks if custom_checks is not None else _load_custom_checks()
    if not checks:
        return ''
    states = _web_custom_probe_states(probe, checks)
    badges = []
    for check in checks:
        state = states.get(check.get('id'), 'unknown')
        safe_label = html.escape(check.get('label', 'Проверка'))
        safe_url = html.escape(_custom_check_url_text(check))
        badges.append(
            f'<span class="custom-service-slot custom-service-{state}" title="{safe_label}: {safe_url}">{_custom_check_status_icon_html(check, state)}</span>'
        )
    return ''.join(badges)


def _custom_check_url_text(check):
    urls = check.get('urls') if isinstance(check.get('urls'), list) else [check.get('url', '')]
    labels = []
    for url in urls:
        if not url:
            continue
        parsed = urlparse(url)
        label = parsed.netloc or url
        if parsed.path and parsed.path != '/':
            label += parsed.path
        labels.append(label)
    return ', '.join(labels)


def _custom_check_icon_html(check):
    if check.get('icon'):
        return f'<span class="preset-icon">{_service_icon_html(check.get("icon"), check.get("label", "Service"), opacity=1.0, size=20)}</span>'
    return f'<span class="custom-service-badge custom-service-neutral">{html.escape(check.get("badge", "WEB"))}</span>'


def _custom_check_status_icon_html(check, state):
    if state == 'ok':
        return _service_icon_html(check.get('icon'), check.get('label', 'Service'), opacity=1.0, size=18)
    if state == 'fail':
        return '<span class="service-probe-mark service-probe-fail">✕</span>'
    return '<span class="service-probe-mark service-probe-unknown">?</span>'


def _custom_check_header_icons(custom_checks=None):
    checks = custom_checks if custom_checks is not None else _load_custom_checks()
    icons = []
    for check in checks:
        label = check.get('label', 'Service')
        safe_label = html.escape(label)
        if check.get('icon'):
            content = _service_icon_html(check.get('icon'), label, opacity=1.0, size=16)
        else:
            content = f'<span class="custom-service-badge custom-service-neutral">{html.escape(check.get("badge", "WEB"))}</span>'
        icons.append(f'<span class="custom-service-slot custom-service-header" title="{safe_label}">{content}</span>')
    return ''.join(icons)


def _web_custom_checks_html(checks=None):
    checks = checks if checks is not None else _load_custom_checks()
    if not checks:
        return '<div class="custom-check-empty">Дополнительные проверки пока не добавлены.</div>'
    items = []
    for check in checks:
        safe_id = html.escape(check.get('id', ''))
        safe_label = html.escape(check.get('label', 'Проверка'))
        safe_url = html.escape(_custom_check_url_text(check))
        icon_html = _custom_check_icon_html(check)
        items.append(f'''<div class="custom-check-item">
            {icon_html}
            <span class="custom-check-copy"><strong>{safe_label}</strong><small>{safe_url}</small></span>
            <form method="post" action="/custom_check_delete" data-async-action="custom-check-delete" data-confirm-title="Удалить проверку?" data-confirm-message="Удалить дополнительную проверку {safe_label}?">
                <input type="hidden" name="id" value="{safe_id}">
                <button type="submit" class="pool-delete-btn" title="Удалить проверку">Удалить</button>
            </form>
        </div>''')
    return ''.join(items)


def _web_custom_presets_html(checks=None):
    checks = checks if checks is not None else _load_custom_checks()
    active_ids = {check.get('id') for check in checks}
    items = []
    for preset in _custom_check_presets():
        safe_id = html.escape(preset['id'])
        safe_label = html.escape(preset['label'])
        safe_url = html.escape(preset.get('url', ''))
        icon_html = _custom_check_icon_html(preset)
        disabled = ' disabled' if preset['id'] in active_ids else ''
        title = 'Уже добавлено' if disabled else f'Добавить проверку {safe_label}'
        items.append(f'''<form method="post" action="/custom_check_add" data-async-action="custom-check-add">
            <input type="hidden" name="preset" value="{safe_id}">
            <input type="hidden" name="label" value="{safe_label}">
            <input type="hidden" name="url" value="{safe_url}">
            <button type="submit" class="service-preset-btn"{disabled} data-custom-preset="{safe_id}" title="{html.escape(title)}">
                {icon_html}
                <span>{safe_label}</span>
            </button>
        </form>''')
    return ''.join(items)


def _web_pool_snapshot(current_keys=None, include_keys=False):
    current_keys = current_keys if current_keys is not None else _load_current_keys()
    pools = _ensure_current_keys_in_pools(current_keys)
    cache = _load_key_probe_cache()
    custom_checks = _load_custom_checks()
    result = {}
    for proto in POOL_PROTOCOL_ORDER:
        current_key = current_keys.get(proto, '')
        rows = []
        for index, key_value in enumerate(pools.get(proto, []) or [], start=1):
            probe = cache.get(_hash_key(key_value), {})
            row = {
                'index': index,
                'key_id': _hash_key(key_value)[:12],
                'display_name': _pool_key_display_name(key_value),
                'active': bool(current_key and key_value == current_key),
                'tg': _web_probe_state(probe, 'tg_ok'),
                'yt': _web_probe_state(probe, 'yt_ok'),
                'custom': _web_custom_probe_states(probe, custom_checks),
                'checked_at': _web_probe_checked_at(probe),
            }
            if include_keys:
                row['key'] = key_value
            rows.append(row)
        result[proto] = {
            'label': _pool_proto_label(proto),
            'count': len(rows),
            'rows': rows,
        }
    return result

def _check_local_proxy_endpoint(key_type, port):
    if key_type in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
        if _wait_for_socks5_handshake(port, timeout=3):
            return True, f'Локальный SOCKS-порт 127.0.0.1:{port} отвечает как SOCKS5.'
        if _port_is_listening(port):
            return False, f'Локальный порт 127.0.0.1:{port} открыт, но не отвечает как SOCKS5.'
        return False, f'Локальный порт 127.0.0.1:{port} недоступен.'
    return True, ''


def _shadowsocks_runtime_mode():
    init_script = _read_text_file('/opt/etc/init.d/S22shadowsocks')
    if 'PROCS=ss-redir' in init_script or 'ss-redir' in init_script:
        return 'redir'
    if 'PROCS=ss-local' in init_script or 'ss-local' in init_script:
        return 'socks'
    return 'unknown'


def _apply_installed_proxy(key_type, key_value, verify=True):
    settings = {
        'shadowsocks': {
            'label': 'Shadowsocks',
            'port': localportsh_bot,
            'restart_cmds': ['/opt/etc/init.d/S22shadowsocks restart', CORE_PROXY_SERVICE_SCRIPT + ' restart'],
            'startup_wait': 8,
        },
        'vmess': {
            'label': 'Vmess',
            'port': localportvmess,
            'restart_cmds': [CORE_PROXY_SERVICE_SCRIPT + ' restart'],
            'startup_wait': 18,
        },
        'vless': {
            'label': 'Vless 1',
            'port': localportvless,
            'restart_cmds': [CORE_PROXY_SERVICE_SCRIPT + ' restart'],
            'startup_wait': 18,
        },
        'vless2': {
            'label': 'Vless 2',
            'port': localportvless2,
            'restart_cmds': [CORE_PROXY_SERVICE_SCRIPT + ' restart'],
            'startup_wait': 18,
        },
        'trojan': {
            'label': 'Trojan',
            'port': localporttrojan_bot,
            'restart_cmds': ['/opt/etc/init.d/S22trojan restart', CORE_PROXY_SERVICE_SCRIPT + ' restart'],
            'startup_wait': 8,
        }
    }
    current = settings[key_type]
    active_mode = _load_proxy_mode()
    active_label = _proxy_mode_label(active_mode)
    for command in current['restart_cmds']:
        os.system(command)
    time.sleep(current['startup_wait'])

    diagnostics = _build_proxy_diagnostics(key_type, key_value)
    restart_cmd = current['restart_cmds'][-1]
    if not _ensure_service_port(current['port'], restart_cmd, retries=2, sleep_after_restart=5):
        return (f'⚠️ {current["label"]} ключ сохранён, но локальный порт 127.0.0.1:{current["port"]} '
                f'не поднялся. Текущий {APP_MODE_NOUN} {active_label} сохранён. {diagnostics}').strip()

    endpoint_ok, endpoint_message = _check_local_proxy_endpoint(key_type, current['port'])
    if not endpoint_ok:
        return (f'⚠️ {current["label"]} ключ сохранён, но {endpoint_message} '
                f'Текущий {APP_MODE_NOUN} {active_label} сохранён. {diagnostics}').strip()

    if not verify:
        return (f'✅ {current["label"]} ключ сохранён. {endpoint_message} '
                'Проверка Telegram API и YouTube выполняется в фоне; '
                f'статус обновится без перезагрузки страницы. Текущий {APP_MODE_NOUN} {active_label} сохранён.').strip()

    api_ok, api_probe_message = _check_telegram_api_through_proxy(
        proxy_settings.get(key_type),
        connect_timeout=10,
        read_timeout=15,
    )
    yt_ok, _ = _check_http_through_proxy(proxy_settings.get(key_type), url='https://www.youtube.com', connect_timeout=3, read_timeout=5)
    _record_key_probe(key_type, key_value, tg_ok=api_ok, yt_ok=yt_ok)
    if api_ok:
        return (f'✅ {current["label"]} ключ сохранён. {endpoint_message} '
                f'Доступ к Telegram API через этот ключ подтверждён. '
                f'Текущий {APP_MODE_NOUN} {active_label} сохранён.').strip()
    return (f'⚠️ {current["label"]} ключ сохранён. {endpoint_message} '
            f'Но Telegram API не проходит через этот ключ. '
            f'Текущий {APP_MODE_NOUN} {active_label} сохранён. '
            f'❌ Не удалось подключиться к Telegram API: {api_probe_message} {diagnostics}').strip()



def update_proxy(proxy_type, persist=True):
    global proxy_mode
    proxy_url = proxy_settings.get(proxy_type)
    if proxy_url and proxy_url.startswith('socks') and not _has_socks_support():
        return False, ('Для SOCKS-прокси требуется модуль PySocks. '
                       'Установите python3-pysocks или выберите другой режим.')

    proxy_mode = proxy_type
    if proxy_supports_http.get(proxy_type, False) and proxy_url:
        os.environ['HTTPS_PROXY'] = proxy_url
        os.environ['HTTP_PROXY'] = proxy_url
        os.environ['https_proxy'] = proxy_url
        os.environ['http_proxy'] = proxy_url
    else:
        for key in ['HTTPS_PROXY', 'HTTP_PROXY', 'https_proxy', 'http_proxy']:
            if key in os.environ:
                del os.environ[key]

    if persist:
        _save_proxy_mode(proxy_type)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return True, None


def check_telegram_api(retries=2, retry_delay=7, connect_timeout=30, read_timeout=45):
    last_result = None
    for attempt in range(retries + 1):
        proxy_url = proxy_settings.get(proxy_mode)
        ok, probe_message = _check_telegram_api_through_proxy(proxy_url, connect_timeout=connect_timeout, read_timeout=read_timeout)
        if ok:
            return '✅ Доступ к api.telegram.org подтверждён.'
        if 'PySocks' in probe_message:
            return ('❌ Не удалось подключиться к Telegram API: отсутствует поддержка SOCKS (PySocks). '
                    'Установите python3-pysocks или используйте режим без SOCKS.')
        if proxy_mode == 'none':
            last_result = f'❌ Прямой доступ к api.telegram.org не проходит: {probe_message}'
        else:
            last_result = f'❌ Доступ к Telegram API через режим {proxy_mode} не проходит: {probe_message}'
            if attempt < retries:
                time.sleep(retry_delay)
    return last_result


def _is_transient_telegram_api_failure(status_text):
    text = str(status_text or '').casefold()
    markers = [
        'network is unreachable',
        'timed out',
        'timeout',
        'таймаут',
        'не ответил вовремя',
        'за отведённое время',
        'за отведенное время',
        'max retries exceeded',
        'failed to establish a new connection',
        'connection reset',
    ]
    return any(marker in text for marker in markers)


def _build_web_status(current_keys, protocols=None):
    now = time.time()
    state_label = 'web-only режим'
    socks_details = ''
    socks_ok = False
    current_protocol = protocols.get(proxy_mode) if isinstance(protocols, dict) else None
    if current_protocol and proxy_mode in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
        socks_ok = bool(current_protocol.get('endpoint_ok'))
        socks_details = current_protocol.get('endpoint_message', '')
        api_ok = bool(current_protocol.get('api_ok'))
        api_message = str(current_protocol.get('api_message', '') or '')
        if api_ok:
            api_status = '✅ Доступ к api.telegram.org подтверждён.'
        elif socks_ok and _is_transient_telegram_api_failure(api_message):
            api_status = ('⏳ Telegram API не ответил вовремя через текущий режим. '
                          'Локальный SOCKS работает, идёт повторная проверка. '
                          'Статус обновится без перезагрузки страницы.')
        elif proxy_mode == 'none':
            api_status = f'❌ Прямой доступ к api.telegram.org не проходит: {api_message}'
        else:
            api_status = f'❌ Доступ к Telegram API через режим {proxy_mode} не проходит: {api_message}'
    elif proxy_mode in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
        port = {
            'shadowsocks': localportsh_bot,
            'vmess': localportvmess,
            'vless': localportvless,
            'vless2': localportvless2,
            'trojan': localporttrojan_bot,
        }.get(proxy_mode)
        if port:
            socks_ok = _check_socks5_handshake(port)
            socks_details = f'Локальный SOCKS {proxy_mode} 127.0.0.1:{port}: {"доступен" if socks_ok else "не отвечает как SOCKS5"}'
        api_status = check_telegram_api(retries=0, retry_delay=0, connect_timeout=5, read_timeout=8)
        if (proxy_mode != 'none' and socks_ok and not api_status.startswith('✅') and
                _is_transient_telegram_api_failure(api_status)):
            api_status = ('⏳ Telegram API не ответил вовремя через текущий режим. '
                          'Локальный SOCKS работает, идёт повторная проверка. '
                          'Статус обновится без перезагрузки страницы.')
    else:
        api_status = check_telegram_api(retries=0, retry_delay=0, connect_timeout=5, read_timeout=8)
    snapshot = {
        'state_label': state_label,
        'proxy_mode': proxy_mode,
        'api_status': api_status,
        'socks_details': socks_details,
        'fallback_reason': _last_proxy_disable_reason(),
    }
    return snapshot


def _status_snapshot_signature(current_keys):
    custom_signature = tuple((item.get('id'), item.get('url')) for item in _load_custom_checks())
    return (
        tuple((name, current_keys.get(name, '')) for name in sorted(current_keys)),
        custom_signature,
    )


def _build_status_snapshot(current_keys, force_refresh=False):
    signature = _status_snapshot_signature(current_keys)
    now = time.time()
    if pool_probe_lock.locked():
        return _active_mode_status_snapshot(current_keys)
    if (
        not force_refresh and
        status_snapshot_cache['data'] is not None and
        status_snapshot_cache['signature'] == signature and
        now - status_snapshot_cache['timestamp'] < STATUS_CACHE_TTL
    ):
        return status_snapshot_cache['data']

    custom_checks = _load_custom_checks()
    protocols = {}
    for key_name, key_value in current_keys.items():
        try:
            if key_name == proxy_mode:
                protocols[key_name] = _protocol_status_for_key(key_name, key_value)
                _store_active_mode_protocol_status(current_keys, protocols[key_name])
            else:
                protocols[key_name] = _cached_protocol_status_for_key(key_name, key_value, custom_checks=custom_checks)
        except Exception as exc:
            _write_runtime_log(f'Ошибка проверки ключа {key_name}: {exc}')
            protocols[key_name] = {
                'tone': 'warn',
                'label': 'Ошибка проверки',
                'details': f'Не удалось завершить проверку ключа: {exc}',
            }

    snapshot = {
        'web': _build_web_status(current_keys, protocols=protocols),
        'protocols': protocols,
    }
    status_snapshot_cache['timestamp'] = now
    status_snapshot_cache['data'] = snapshot
    status_snapshot_cache['signature'] = signature
    return snapshot


def _active_mode_status_snapshot(current_keys):
    cached = _cached_status_snapshot(current_keys)
    if cached is not None and isinstance(cached, dict):
        protocols = dict(cached.get('protocols') or {})
    else:
        protocols = _placeholder_protocol_statuses(current_keys)

    if proxy_mode in current_keys:
        try:
            cached_active = _cached_active_mode_protocol_status(current_keys) if pool_probe_lock.locked() else None
            if cached_active is not None:
                protocols[proxy_mode] = cached_active
            else:
                protocols[proxy_mode] = _protocol_status_for_key(proxy_mode, current_keys.get(proxy_mode, ''))
                _store_active_mode_protocol_status(current_keys, protocols[proxy_mode])
        except Exception as exc:
            _write_runtime_log(f'Ошибка быстрой проверки активного режима {proxy_mode}: {exc}')
            protocols[proxy_mode] = {
                'tone': 'warn',
                'label': 'Ошибка проверки',
                'details': f'Не удалось завершить быструю проверку активного режима: {exc}',
            }
    return {
        'web': _build_web_status(current_keys, protocols=protocols),
        'protocols': protocols,
    }


def _web_status_snapshot(force_refresh=False):
    current_keys = _load_current_keys()
    return _build_status_snapshot(current_keys, force_refresh=force_refresh)['web']


def _cached_status_snapshot(current_keys):
    now = time.time()
    signature = _status_snapshot_signature(current_keys)
    if (
        status_snapshot_cache['data'] is not None and
        status_snapshot_cache['signature'] == signature and
        now - status_snapshot_cache['timestamp'] < STATUS_CACHE_TTL
    ):
        return status_snapshot_cache['data']
    return None


def _active_mode_status_signature(current_keys):
    custom_signature = tuple((item.get('id'), tuple(item.get('urls') or [item.get('url')])) for item in _load_custom_checks())
    return (proxy_mode, current_keys.get(proxy_mode, ''), custom_signature)


def _cached_active_mode_protocol_status(current_keys):
    now = time.time()
    signature = _active_mode_status_signature(current_keys)
    with active_mode_status_cache_lock:
        if (
            active_mode_status_cache['status'] is not None and
            active_mode_status_cache['signature'] == signature and
            now - active_mode_status_cache['timestamp'] < ACTIVE_MODE_STATUS_DURING_POOL_TTL
        ):
            return dict(active_mode_status_cache['status'])
    return None


def _store_active_mode_protocol_status(current_keys, status):
    if not isinstance(status, dict):
        return
    with active_mode_status_cache_lock:
        active_mode_status_cache['timestamp'] = time.time()
        active_mode_status_cache['signature'] = _active_mode_status_signature(current_keys)
        active_mode_status_cache['status'] = dict(status)


def _placeholder_web_status_snapshot():
    return {
        'state_label': 'web-only режим',
        'proxy_mode': proxy_mode,
        'api_status': '⏳ Проверяется связь текущего режима. Статус обновится без перезагрузки страницы.',
        'socks_details': '',
        'fallback_reason': _last_proxy_disable_reason(),
    }


def _protocol_status_snapshot(current_keys, force_refresh=False):
    return _build_status_snapshot(current_keys, force_refresh=force_refresh)['protocols']


def _cached_protocol_status_snapshot(current_keys):
    snapshot = _cached_status_snapshot(current_keys)
    if snapshot is not None:
        return snapshot['protocols']
    return None


def _refresh_status_caches_async(current_keys):
    if pool_probe_lock.locked():
        return
    signature = _status_snapshot_signature(current_keys)
    with status_refresh_lock:
        if signature in status_refresh_in_progress:
            return
        status_refresh_in_progress.add(signature)

    def worker():
        try:
            _build_status_snapshot(current_keys, force_refresh=True)
        except Exception as exc:
            _write_runtime_log(f'Ошибка фонового обновления статусов: {exc}')
        finally:
            with status_refresh_lock:
                status_refresh_in_progress.discard(signature)

    threading.Thread(target=worker, daemon=True).start()


def _probe_all_pool_keys_async(stale_only=True, max_keys=KEY_PROBE_MAX_PER_RUN, missing_only=False, scope='manual_all'):
    """Запускает безопасную фоновую проверку пула через временный xray."""
    if POOL_PROBE_ACTIVE_ONLY:
        active_proto = proxy_mode if proxy_mode in POOL_PROTOCOL_ORDER else ''
        active_key = (_load_current_keys().get(active_proto, '') if active_proto else '').strip()
        tasks = [(active_proto, active_key)] if active_proto and active_key else []
        return _queue_pool_key_probe(tasks, max_keys=1, stale_only=False, scope=scope)
    pools = _ensure_current_keys_in_pools(_load_current_keys())
    tasks = [
        (proto, key_value)
        for proto in POOL_PROTOCOL_ORDER
        for key_value in (pools.get(proto, []) or [])
    ]
    return _queue_pool_key_probe(tasks, max_keys=max_keys, stale_only=stale_only, missing_only=missing_only, scope=scope)


def _probe_pool_keys_on_page_load():
    """Refresh only stale or missing pool statuses on page open."""
    global pool_probe_last_auto_started_at

    if POOL_PROBE_PAGE_REFRESH_INTERVAL <= 0:
        return False, 0

    now = time.time()
    progress = _get_pool_probe_progress()
    recent_probe_at = max(float(progress.get('started_at') or 0), float(progress.get('finished_at') or 0))
    if progress.get('running') or (recent_probe_at and now - recent_probe_at < POOL_PROBE_PAGE_REFRESH_INTERVAL):
        return False, 0

    with pool_probe_auto_lock:
        if now - pool_probe_last_auto_started_at < POOL_PROBE_PAGE_REFRESH_INTERVAL:
            return False, 0
        pool_probe_last_auto_started_at = now

    started, queued = _probe_all_pool_keys_async(
        stale_only=False,
        max_keys=None,
        missing_only=True,
        scope='auto_missing',
    )
    if started or queued:
        return started, queued
    return False, 0


class KeyInstallHTTPRequestHandler(BaseHTTPRequestHandler):
    def _request_is_allowed(self):
        client_ip = self.client_address[0] if self.client_address else ''
        return _is_local_web_client(client_ip)

    def _ensure_request_allowed(self):
        if self._request_is_allowed():
            return True
        self._send_html('<h1>403 Forbidden</h1><p>Веб-интерфейс доступен только из локальной сети.</p>', status=403)
        return False

    def _send_html(self, html, status=200):
        body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = False

    def _send_redirect(self, location='/'):
        self.send_response(303)
        self.send_header('Location', location)
        self.send_header('Content-Length', '0')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()
        self.close_connection = False

    def _send_png(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                body = f.read()
            self.send_response(200)
            content_type = 'image/png'
            if body.lstrip().startswith(b'<svg'):
                content_type = 'image/svg+xml'
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Content-Length', '9')
            self.end_headers()
            self.wfile.write(b'Not Found')
        self.close_connection = False

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = False

    def _wants_json(self):
        accept = self.headers.get('Accept', '')
        requested_with = self.headers.get('X-Requested-With', '')
        return 'application/json' in accept or requested_with == 'fetch'


    def _send_action_result(self, result, success=True, extra=None, redirect='/'):
        if self._wants_json():
            payload = {
                'ok': bool(success),
                'result': result or '',
                'status': 'ok' if success else 'error',
            }
            if extra:
                payload.update(extra)
            self._send_json(payload, status=200 if success else 400)
            return
        _set_web_flash_message(result)
        self._send_redirect(redirect)

    def _build_form(self, message=''):
        command_state = _consume_web_command_state_for_render()
        current_keys = _load_current_keys()
        snapshot = _cached_status_snapshot(current_keys)
        status = snapshot['web'] if snapshot is not None else _placeholder_web_status_snapshot()
        protocol_statuses = snapshot['protocols'] if snapshot is not None else _placeholder_protocol_statuses(current_keys)
        pool_probe_started, pool_probe_queued = _probe_pool_keys_on_page_load()
        current_pool_probe_progress = _get_pool_probe_progress()
        pool_probe_pending = (
            bool(current_pool_probe_progress.get('running')) and
            int(current_pool_probe_progress.get('total') or 0) > 0
        )
        if snapshot is None:
            snapshot = _active_mode_status_snapshot(current_keys)
            status = snapshot['web']
            protocol_statuses = snapshot['protocols']
            if not pool_probe_pending:
                _refresh_status_caches_async(current_keys)
        unblock_lists = _load_unblock_lists()
        status_refresh_pending = (
            'Фоновая проверка связи выполняется' in status.get('api_status', '') or
            any(item.get('label') == 'Проверяется' for item in protocol_statuses.values()) or
            pool_probe_pending
        )

        message_block = ''
        if message:
            safe_message = html.escape(message)
            message_block = f'''<div id="web-action-message" class="notice notice-result">
  <strong>Результат</strong>
  <pre class="log-output">{safe_message}</pre>
</div>'''
        else:
            message_block = '''<div id="web-action-message" class="notice notice-result hidden">
  <strong>Результат</strong>
  <pre class="log-output"></pre>
</div>'''

        command_block = ''
        if command_state['label']:
            command_title = 'Команда выполняется' if command_state['running'] else 'Последняя команда'
            command_text = command_state['result'] or f'⏳ {command_state["label"]} ещё выполняется. Статус обновится без перезагрузки страницы.'
            command_block = f'''<div id="web-command-status" class="notice notice-status">
  <strong>{html.escape(command_title)}: {html.escape(command_state['label'])}</strong>
  <pre class="log-output">{html.escape(command_text)}</pre>
</div>'''
        else:
            command_block = '''<div id="web-command-status" class="notice notice-status hidden">
  <strong></strong>
  <pre class="log-output"></pre>
</div>'''

        socks_hidden = '' if status['socks_details'] else ' hidden'
        socks_block = f'<p id="web-socks-details" class="status-note"{socks_hidden}>{html.escape(status.get("socks_details", ""))}</p>'
        fallback_block = ''
        if status.get('fallback_reason') and status['proxy_mode'] == 'none':
            fallback_block = f'<p id="web-fallback-reason" class="status-note">Последняя неудачная попытка прокси: {html.escape(status["fallback_reason"])}</p>'
        else:
            fallback_block = '<p id="web-fallback-reason" class="status-note hidden"></p>'

        current_mode_label = {
            'none': 'Без прокси',
            'shadowsocks': 'Shadowsocks',
            'vmess': 'Vmess',
            'vless': 'Vless 1',
            'vless2': 'Vless 2',
            'trojan': 'Trojan',
        }.get(status['proxy_mode'], status['proxy_mode'])
        list_route_label = _transparent_list_route_label()

        mode_options = [
            ('none', 'Без прокси'),
            ('shadowsocks', 'Shadowsocks'),
            ('vmess', 'Vmess'),
            ('vless', 'Vless 1'),
            ('vless2', 'Vless 2'),
            ('trojan', 'Trojan'),
        ]
        mode_buttons_html = ''.join(
            f'''<form method="post" action="/set_proxy" data-async-action="set-proxy">
        <input type="hidden" name="proxy_type" value="{value}">
        <button type="submit" class="mode-choice{' active' if proxy_mode == value else ''}" data-mode-value="{value}">
            <span>{html.escape(label)}</span>
        </button>
    </form>'''
            for value, label in mode_options
        )
        mode_picker_block = f'''<div id="mode-picker" class="hero-popover mode-picker hidden">
    <div class="mode-picker-form">
        <span class="mode-picker-label">Активный протокол</span>
        <div class="mode-choice-grid">{mode_buttons_html}</div>
    </div>
</div>'''

        protocol_sections = [
            ('vless', 'Vless 1', 6, 'vless://...'),
            ('vless2', 'Vless 2', 6, 'vless://...'),
            ('vmess', 'Vmess', 6, 'vmess://...'),
            ('trojan', 'Trojan', 5, 'trojan://...'),
            ('shadowsocks', 'Shadowsocks', 5, 'shadowsocks://...'),
        ]
        key_pools = _ensure_current_keys_in_pools(current_keys)
        key_probe_cache = _load_key_probe_cache()
        custom_checks = _load_custom_checks()
        custom_checks_html = _web_custom_checks_html(custom_checks)
        custom_presets_html = _web_custom_presets_html(custom_checks)
        custom_header_icons = _custom_check_header_icons(custom_checks)
        custom_checks_json = json.dumps(_web_custom_checks(), ensure_ascii=False)
        if pool_probe_pending:
            progress_total = int(current_pool_probe_progress.get('total') or 0)
            progress_checked = int(current_pool_probe_progress.get('checked') or 0)
            progress_label = _pool_probe_progress_label(current_pool_probe_progress)
            topbar_status_text = (
                f'⏳ {progress_label}: {progress_checked}/{progress_total}. '
                'Статусы обновятся без перезагрузки страницы.'
            )
        else:
            topbar_status_text = status['api_status']
        pool_table_class = 'pool-table has-custom-checks' if custom_checks else 'pool-table'
        pool_custom_col_width = 32 * max(1, len(custom_checks))
        pool_mobile_custom_col_width = max(28, 28 * len(custom_checks))
        protocol_tabs = []
        protocol_panels = []
        for panel_index, (key_name, title, rows, placeholder) in enumerate(protocol_sections):
            safe_value = html.escape(current_keys.get(key_name, ''))
            safe_title = html.escape(title)
            status_info = protocol_statuses.get(key_name, {'tone': 'empty', 'label': 'Не сохранён', 'details': 'Ключ ещё не сохранён на роутере.'})
            api_ok = status_info.get('api_ok', False)
            current_probe = key_probe_cache.get(_hash_key(current_keys.get(key_name, '')), {})
            if not isinstance(current_probe, dict):
                current_probe = {}
            current_tg_ok = api_ok or bool(current_probe.get('tg_ok'))
            current_yt_ok = bool(status_info.get('yt_ok', current_probe.get('yt_ok', False)))
            custom_states = status_info.get('custom') or _web_custom_probe_states(current_probe, custom_checks)
            active_status_icons = ''.join([
                _telegram_icon_html(opacity=1.0) if current_tg_ok else '',
                _youtube_icon_html(opacity=1.0) if current_yt_ok else '',
            ] + [
                _service_icon_html(check.get('icon'), check.get('label', 'Service'), opacity=1.0, size=18)
                for check in custom_checks
                if custom_states.get(check.get('id')) == 'ok'
            ])
            pool_keys = key_pools.get(key_name, [])
            pool_items_html = ''
            if pool_keys:
                for i, pk in enumerate(pool_keys):
                    safe_pk = html.escape(pk)
                    display_name = html.escape(_pool_key_display_name(pk))
                    key_id = _hash_key(pk)[:12]
                    is_current_key = bool(current_keys.get(key_name) and pk == current_keys.get(key_name))
                    is_active = 'активен' if is_current_key else ''
                    active_class = ' pool-row-active' if is_current_key else ''
                    probe = key_probe_cache.get(_hash_key(pk), {})
                    if not isinstance(probe, dict):
                        probe = {}
                    tg_badge = _telegram_icon_html(opacity=1.0) if probe.get('tg_ok') else (
                        '<span class="service-probe-mark service-probe-fail">✕</span>'
                        if 'tg_ok' in probe else
                        '<span class="service-probe-mark service-probe-unknown">?</span>'
                    )
                    yt_badge = _youtube_icon_html(opacity=1.0) if probe.get('yt_ok') else (
                        '<span class="service-probe-mark service-probe-fail">✕</span>'
                        if 'yt_ok' in probe else
                        '<span class="service-probe-mark service-probe-unknown">?</span>'
                    )
                    custom_badges = _web_custom_check_badges(probe, custom_checks)
                    checked_at = html.escape(_web_probe_checked_at(probe))
                    pool_items_html += f'''<tr class="pool-row{active_class}" data-pool-row data-protocol="{key_name}" data-key-id="{key_id}" data-key="{safe_pk}">
                        <td class="pool-key-cell">
                            <form method="post" action="/pool_apply" class="pool-apply-form" data-async-action="pool-apply">
                                <input type="hidden" name="type" value="{key_name}">
                                <input type="hidden" name="key" value="{safe_pk}">
                                <button type="submit" class="pool-apply-btn" title="Применить этот ключ">{display_name}</button>
                            </form>
                            <span class="pool-mobile-active" data-pool-key-meta data-pool-mobile-active>{is_active}</span>
                            <span class="pool-hash">{key_id}</span>
                        </td>
                        <td class="pool-service-cell" data-pool-tg>{tg_badge}</td>
                        <td class="pool-service-cell" data-pool-yt>{yt_badge}</td>
                        <td class="pool-custom-cell" data-pool-custom>{custom_badges}</td>
                        <td class="pool-checked-cell" data-pool-checked>{checked_at}</td>
                        <td class="pool-actions-cell">
                            <form method="post" action="/pool_delete" class="pool-item-form" data-async-action="pool-delete" data-confirm-title="Удалить ключ?" data-confirm-message="Удалить ключ из пула {safe_title}?">
                                <input type="hidden" name="type" value="{key_name}">
                                <input type="hidden" name="key" value="{safe_pk}">
                                <button type="submit" class="pool-delete-btn" title="Удалить ключ из пула">Удалить</button>
                            </form>
                        </td>
                    </tr>'''
            if not pool_items_html:
                pool_items_html = '<tr class="pool-row pool-empty-row"><td colspan="6">Пул пуст. Добавьте ключи или загрузите subscription.</td></tr>'
            tab_active = ' active' if panel_index == 0 else ''
            protocol_tabs.append(
                f'''<button type="button" class="seg-tab protocol-tab{tab_active}" data-protocol-target="{key_name}">
                    <span>{safe_title}</span>
                    <span class="tab-count">{len(pool_keys)}</span>
                </button>'''
            )
            protocol_panels.append(f'''<section class="protocol-workspace{tab_active}" data-protocol-card="{key_name}" data-protocol-panel="{key_name}">
        <div class="workspace-head">
            <div>
                <span class="eyebrow">Ключи и мосты</span>
                <h2>{safe_title}</h2>
                <p class="key-status-note" data-protocol-status-details>{html.escape(status_info['details'])}</p>
            </div>
            <span class="key-status-wrap"><span class="key-status-icons" data-protocol-status-icons>{active_status_icons}</span><span class="key-status-badge key-status-{status_info['tone']}" data-protocol-status-label>{status_info['label']}</span></span>
        </div>
        <div class="subtabs">
            <button type="button" class="subtab active" data-subview-target="key">Ключ</button>
            <button type="button" class="subtab" data-subview-target="pool">Пул ключей</button>
            <button type="button" class="subtab" data-subview-target="subscription">Subscription</button>
            <button type="button" class="subtab" data-subview-target="check">Проверка</button>
        </div>
        <div class="protocol-subview active" data-subview="key">
            <form method="post" action="/install" data-async-action="install" class="key-editor-form">
                <input type="hidden" name="type" value="{key_name}">
                <label class="field-label">Активный ключ {safe_title}</label>
                <textarea name="key" rows="{rows}" placeholder="{html.escape(placeholder)}" required data-key-textarea>{safe_value}</textarea>
                <div class="form-actions">
                    <button type="submit">Сохранить {safe_title}</button>
                </div>
            </form>
        </div>
        <div class="protocol-subview" data-subview="pool">
            <div class="pool-toolbar">
                <form method="post" action="/pool_probe" data-async-action="pool-probe">
                    <input type="hidden" name="type" value="{key_name}">
                    <button type="submit" class="secondary-button">Проверить пул</button>
                </form>
                <form method="post" action="/pool_clear" data-async-action="pool-clear" data-confirm-title="Очистить пул?" data-confirm-message="Очистить весь пул ключей для {safe_title}?">
                    <input type="hidden" name="type" value="{key_name}">
                    <button type="submit" class="danger pool-clear-btn">Очистить пул</button>
                </form>
            </div>
            <div class="pool-table-wrap">
                <table class="{pool_table_class}" style="--custom-col-mobile:{pool_mobile_custom_col_width}px">
                    <colgroup>
                        <col class="pool-col-key">
                        <col class="pool-col-icon">
                        <col class="pool-col-icon">
                        <col class="pool-col-custom" style="width:{pool_custom_col_width}px">
                        <col class="pool-col-checked">
                        <col class="pool-col-actions">
                    </colgroup>
                    <thead><tr><th class="pool-key-head">Ключ</th><th class="pool-icon-head">{_telegram_icon_html(opacity=1.0)}</th><th class="pool-icon-head">{_youtube_icon_html(opacity=1.0)}</th><th class="pool-icon-head pool-custom-head" data-custom-check-head>{custom_header_icons}</th><th class="pool-checked-head">Проверка</th><th class="pool-actions-head">Действия</th></tr></thead>
                    <tbody data-pool-body="{key_name}">{pool_items_html}</tbody>
                </table>
            </div>
        </div>
        <div class="protocol-subview protocol-subview-import" data-subview="subscription">
            <form method="post" action="/pool_add" class="pool-add-form" data-async-action="pool-add">
                <input type="hidden" name="type" value="{key_name}">
                <label class="field-label">Добавить ключи в пул</label>
                <textarea name="keys" rows="4" placeholder="Вставьте ключи, каждый с новой строки"></textarea>
                <button type="submit" class="secondary-button">Добавить в пул</button>
            </form>
            <form method="post" action="/pool_subscribe" class="pool-subscribe-form" data-async-action="pool-subscribe">
                <input type="hidden" name="type" value="{key_name}">
                <label class="field-label">Загрузить subscription</label>
                <input type="url" name="url" placeholder="https://sub.example.com/...">
                <button type="submit" class="secondary-button">Загрузить subscription</button>
            </form>
        </div>
        <div class="protocol-subview protocol-subview-check" data-subview="check">
            <div class="status-card">
                <span class="status-label">Состояние ключа</span>
                <span class="status-value">{status_info['label']}</span>
                <p class="status-note">{html.escape(status_info['details'])}</p>
            </div>
            <div class="custom-check-card">
                <div class="custom-check-head">
                    <span>
                        <strong>Дополнительные сервисы</strong>
                        <small>Проверяются через выбранный прокси вместе с Telegram и YouTube.</small>
                    </span>
                </div>
                <div class="service-preset-grid">{custom_presets_html}</div>
                <div class="custom-check-list" data-custom-check-list>{custom_checks_html}</div>
                <form method="post" action="/custom_check_add" class="custom-check-form" data-async-action="custom-check-add">
                    <input type="hidden" name="type" value="{key_name}">
                    <input type="text" name="label" placeholder="Название, например ChatGPT">
                    <input type="text" name="url" placeholder="Домен, IP или URL: chatgpt.com">
                    <button type="submit" class="secondary-button">Добавить проверку</button>
                    <button type="submit" class="secondary-button" formaction="/custom_checks_to_list" data-confirm-title="Добавить проверки в список обхода?" data-confirm-message="Домены выбранных дополнительных проверок будут добавлены в список {safe_title}.">Добавить в список обхода</button>
                </form>
            </div>
            <form method="post" action="/pool_probe" data-async-action="pool-probe">
                <input type="hidden" name="type" value="{key_name}">
                <button type="submit">Проверить пул {safe_title}</button>
            </form>
        </div>
    </section>''')
        protocol_tabs_html = ''.join(protocol_tabs)
        protocol_panels_html = ''.join(protocol_panels)
        quick_key_proto = status['proxy_mode'] if status['proxy_mode'] in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan'] else 'vless'
        quick_key_label = current_mode_label if quick_key_proto == status['proxy_mode'] else 'Vless 1'
        quick_key_value = html.escape(current_keys.get(quick_key_proto, ''))
        pool_summary = _pool_status_summary(current_keys, key_pools, key_probe_cache, custom_checks)
        pool_summary_note = pool_summary['note']
        if pool_probe_pending:
            pool_summary_note = (
                f"{_pool_probe_progress_label(current_pool_probe_progress)}: {int(current_pool_probe_progress.get('checked') or 0)}/"
                f"{int(current_pool_probe_progress.get('total') or 0)}. {pool_summary_note}"
            )

        dns_override_active = _dns_override_enabled()
        update_buttons_html = f'''<form method="post" action="/command" data-async-action="command" data-confirm-title="Переустановить из форка?" data-confirm-message="Код и служебные файлы будут обновлены без сброса сохраненных ключей и списков.">
                <input type="hidden" name="command" value="update">
                <button type="submit">Переустановить из форка без сброса</button>
            </form>
            <form method="post" action="/command" data-async-action="command" data-confirm-title="Переустановить independent?" data-confirm-message="Будет установлена ветка codex/independent-v1 с сохранением локальных настроек.">
                <input type="hidden" name="command" value="update_independent">
                <button type="submit">Переустановка (ветка independent)</button>
            </form>
            <form method="post" action="/command" data-async-action="command" data-confirm-title="Перейти в web-only?" data-confirm-message="Будет установлена версия без Telegram-бота. Ключи, настройки и списки сохранятся локально.">
                <input type="hidden" name="command" value="update_no_bot">
                <button type="submit">Переустановка (без Telegram бота)</button>
            </form>'''
        command_buttons = [
            ('restart_services', 'Перезапустить сервисы', '', 'Перезапустить сервисы?', 'Службы прокси и DNS будут перезапущены; соединение может кратко пропасть.'),
            ('dns_on', 'DNS Override ВКЛ', 'success-button' if dns_override_active else '', 'Включить DNS Override?', 'Роутер сохранит конфигурацию и перезагрузится.'),
            ('dns_off', 'DNS Override ВЫКЛ', 'danger', 'Выключить DNS Override?', 'Роутер сохранит конфигурацию и перезагрузится.'),
            ('remove', 'Удалить компоненты', 'danger', 'Удалить компоненты?', 'Будут удалены установленные компоненты программы. Настройки роутера могут измениться.'),
            ('reboot', 'Перезагрузить роутер', 'danger', 'Перезагрузить роутер?', 'Связь с веб-интерфейсом временно пропадет.'),
        ]
        command_buttons_html = ''.join(
            f'''<form method="post" action="/command" data-async-action="command"{f' data-confirm-title="{html.escape(confirm_title)}" data-confirm-message="{html.escape(confirm_message)}"' if confirm_title else ''}>
            <input type="hidden" name="command" value="{command}">
            <button type="submit" class="{button_class}">{html.escape(label)}</button>
        </form>'''
            for command, label, button_class, confirm_title, confirm_message in command_buttons
        )

        unblock_tabs = []
        unblock_panels = []
        for list_index, entry in enumerate(unblock_lists):
            safe_name = html.escape(entry['name'])
            safe_label = html.escape(entry['label'])
            safe_content = html.escape(entry['content'])
            active_class = ' active' if list_index == 0 else ''
            social_service_buttons = ''.join(
                f'''<button type="submit" name="service_key" value="{html.escape(key)}" formaction="/append_socialnet" class="secondary-button" data-confirm-title="Добавить {_socialnet_service_label(key)}?" data-confirm-message="Добавить {_socialnet_service_label(key)} в {safe_label}?">{html.escape(_socialnet_service_label(key))}</button>'''
                for key in SOCIALNET_SERVICE_KEYS
            )
            unblock_tabs.append(f'''<button type="button" class="seg-tab list-tab{active_class}" data-list-target="{safe_name}">{safe_label}</button>''')
            line_count = len([line for line in entry['content'].splitlines() if line.strip()])
            unblock_panels.append(f'''<section class="list-workspace{active_class}" data-list-panel="{safe_name}">
        <div class="workspace-head">
            <div>
                <span class="eyebrow">Список обхода</span>
                <h2>{safe_label}</h2>
                <p class="section-subtitle">Записей: {line_count}. Файл: <span class="file-chip">{safe_name}</span></p>
            </div>
        </div>
        <form method="post" action="/save_unblock_list" data-async-action="save-list" class="list-editor-form">
            <input type="hidden" name="list_name" value="{safe_name}">
            <textarea name="content" rows="12" placeholder="example.org&#10;api.telegram.org">{safe_content}</textarea>
            <div class="form-actions">
                <button type="submit">Сохранить список</button>
            </div>
            <div class="social-list-actions">
                <span class="social-list-title">Добавить в список</span>
                {social_service_buttons}
                <button type="submit" name="service_key" value="{SOCIALNET_ALL_KEY}" formaction="/append_socialnet" class="secondary-button" data-confirm-title="Добавить все сервисы?" data-confirm-message="Добавить все сервисы в {safe_label}?">{html.escape(_socialnet_service_label(SOCIALNET_ALL_KEY))}</button>
                <button type="submit" name="service_key" value="{SOCIALNET_ALL_KEY}" formaction="/remove_socialnet" class="danger" data-confirm-title="Удалить все сервисы?" data-confirm-message="Удалить все сервисы из {safe_label}?">Удалить сервисы</button>
            </div>
        </form>
    </section>''')
        unblock_tabs_html = ''.join(unblock_tabs)
        unblock_panels_html = ''.join(unblock_panels)

        initial_status_pending = 'true' if status_refresh_pending else 'false'
        initial_command_running = 'true' if command_state['running'] else 'false'

        start_button_label = APP_START_REPEAT_LABEL if bot_ready else APP_START_IDLE_LABEL
        mode_toggle_label = f'{APP_MODE_LABEL}:'
        quick_start_note = APP_QUICK_START_NOTE


        return render_web_form(
            APP_BRANCH_DESCRIPTION=APP_BRANCH_DESCRIPTION,
            APP_BRANCH_LABEL=APP_BRANCH_LABEL,
            APP_VERSION_LABEL=APP_VERSION_LABEL,
            POOL_PROBE_UI_POLL_EXTENSION_MS=POOL_PROBE_UI_POLL_EXTENSION_MS,
            TELEGRAM_SVG_B64=TELEGRAM_SVG_B64,
            YOUTUBE_SVG_B64=YOUTUBE_SVG_B64,
            _telegram_icon_html=_telegram_icon_html,
            command_block=command_block,
            command_buttons_html=command_buttons_html,
            current_mode_label=current_mode_label,
            custom_checks_json=custom_checks_json,
            fallback_block=fallback_block,
            initial_command_running=initial_command_running,
            initial_status_pending=initial_status_pending,
            list_route_label=list_route_label,
            message_block=message_block,
            mode_picker_block=mode_picker_block,
            mode_toggle_label=mode_toggle_label,
            pool_summary=pool_summary,
            pool_summary_note=pool_summary_note,
            protocol_panels_html=protocol_panels_html,
            protocol_tabs_html=protocol_tabs_html,
            quick_key_label=quick_key_label,
            quick_key_proto=quick_key_proto,
            quick_key_value=quick_key_value,
            quick_start_note=quick_start_note,
            socks_block=socks_block,
            start_button_label=start_button_label,
            status=status,
            topbar_status_text=topbar_status_text,
            unblock_panels_html=unblock_panels_html,
            unblock_tabs_html=unblock_tabs_html,
            update_buttons_html=update_buttons_html,
        )


    def _build_switch_confirmation(self, command):
        labels = {
            'update': 'main',
            'update_independent': 'independent',
        }
        target_label = labels.get(command)
        if not target_label:
            return self._build_form('Неизвестная версия для перехода.')

        safe_command = html.escape(command, quote=True)
        safe_target = html.escape(target_label)
        return f'''<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Подтверждение перехода</title>
  <style>
    :root {{ color-scheme: dark; --bg:#101418; --panel:#182028; --text:#f4f7fb; --muted:#9fb0c3; --line:#2a3846; --danger:#ff6b6b; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; padding:24px; font-family:Segoe UI, Arial, sans-serif; background:var(--bg); color:var(--text); }}
    .panel {{ width:min(680px, 100%); background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:24px; }}
    h1 {{ margin:0 0 12px; font-size:28px; }}
    p {{ color:var(--muted); line-height:1.5; }}
    .actions {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:20px; }}
    button, a {{ display:block; width:100%; text-align:center; padding:14px 16px; border-radius:10px; border:1px solid var(--line); font-weight:700; text-decoration:none; cursor:pointer; }}
    button {{ background:var(--danger); color:#fff; }}
    a {{ background:#243241; color:var(--text); }}
    @media (max-width: 560px) {{ .actions {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <section class="panel">
    <h1>Перейти на версию {safe_target}?</h1>
    <p>Сейчас установлена web-only версия без Telegram-бота. Если перейти на {safe_target}, после переустановки может открыться форма заполнения Telegram-настроек. Можно остаться на web-only и ничего не менять.</p>
    <div class="actions">
      <form method="post" action="/command">
        <input type="hidden" name="command" value="{safe_command}">
        <input type="hidden" name="confirm_switch" value="yes">
        <button type="submit">Да, перейти</button>
      </form>
      <a href="/">Остаться на web-only</a>
    </div>
  </section>
</body>
</html>'''

    def do_GET(self):
        if not self._ensure_request_allowed():
            return
        path = urlparse(self.path).path
        if path in ['/', '/index.html', '/command']:
            self._send_html(self._build_form(_consume_web_flash_message()))
        elif path == '/api/status':
            try:
                current_keys = _load_current_keys()
                snapshot = _cached_status_snapshot(current_keys)
                if snapshot is None:
                    snapshot = _active_mode_status_snapshot(current_keys)
                    if not pool_probe_lock.locked():
                        _refresh_status_caches_async(current_keys)
                progress = _get_pool_probe_progress()
                pool_probe_running = (
                    bool(progress.get('running')) and
                    int(progress.get('total') or 0) > 0
                )
                payload = {
                    'web': snapshot.get('web', {}) if isinstance(snapshot, dict) else {},
                    'protocols': snapshot.get('protocols', {}) if isinstance(snapshot, dict) else {},
                    'pools': _web_pool_snapshot(current_keys),
                    'pool_summary': _pool_status_summary(current_keys),
                    'custom_checks': _web_custom_checks(),
                    'pool_probe_running': pool_probe_running,
                    'pool_probe_progress': progress,
                    'timestamp': time.time(),
                }
                self._send_json(payload, status=200)
            except Exception as exc:
                self._send_json({'error': str(exc)}, status=500)
        elif path == '/api/command_state':
            try:
                self._send_json(_get_web_command_state(), status=200)
            except Exception as exc:
                self._send_json({'error': str(exc)}, status=500)
        elif path == '/api/pool_probe':
            # Запустить безопасную фоновую проверку пула без массовых рестартов xray.
            try:
                started, queued = _probe_all_pool_keys_async(stale_only=False)
                status = 'started' if started else ('busy' if queued else 'empty')
                self._send_json({'status': status, 'queued': queued}, status=200)
            except Exception as exc:
                self._send_json({'error': str(exc)}, status=500)
        elif path == '/static/telegram.png':
            self._send_png(os.path.join(STATIC_DIR, 'telegram.png'))
        elif path == '/static/youtube.png':
            self._send_png(os.path.join(STATIC_DIR, 'youtube.png'))
        elif path.startswith('/static/service-icons/'):
            icon_name = os.path.basename(path)
            self._send_png(os.path.join(STATIC_DIR, 'service-icons', icon_name))
        else:
            self._send_html('<h1>404 Not Found</h1>', status=404)


    def do_POST(self):
        if not self._ensure_request_allowed():
            return
        path = urlparse(self.path).path
        if path == '/set_proxy':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proxy_type = data.get('proxy_type', ['none'])[0]
            ok, error = update_proxy(proxy_type)
            if ok:
                result = f'{APP_MODE_LABEL} установлен: {proxy_type}'
            else:
                result = f'⚠️ {error}'
            _invalidate_web_status_cache()
            _invalidate_key_status_cache()
            self._send_action_result(
                result,
                success=ok,
                extra={'proxy_mode': proxy_type, 'proxy_label': _proxy_mode_label(proxy_type)},
            )
            return

        if path == '/start':
            global bot_ready
            bot_ready = True
            _save_bot_autostart(True)
            _invalidate_web_status_cache()
            result = APP_START_RESULT
            self._send_action_result(result, success=True)
            return

        if path == '/command':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            command = data.get('command', [''])[0]
            started, result = _start_web_command(command)
            self._send_action_result(
                result,
                success=started,
                extra={'command_state': _get_web_command_state()},
            )
            return

        if path == '/save_unblock_list':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            list_name = data.get('list_name', [''])[0]
            content = data.get('content', [''])[0]
            success = True
            try:
                result = _save_unblock_list(list_name, content)
            except Exception as exc:
                success = False
                result = f'Ошибка сохранения списка: {exc}'
            list_content = _read_text_file(os.path.join('/opt/etc/unblock', os.path.basename(list_name))).strip() if success else ''
            self._send_action_result(
                result,
                success=success,
                extra={'list_name': os.path.basename(list_name), 'list_content': list_content},
            )
            return

        if path == '/append_socialnet':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            list_name = data.get('target_list_name', data.get('list_name', ['']))[0]
            service_key = data.get('service_key', [SOCIALNET_ALL_KEY])[0]
            success = True
            try:
                result = _append_socialnet_list(list_name, service_key=service_key)
            except Exception as exc:
                success = False
                result = f'Ошибка добавления сервисов: {exc}'
            safe_name = _normalize_unblock_route_name(list_name) + '.txt' if success else os.path.basename(list_name)
            list_content = _read_text_file(os.path.join('/opt/etc/unblock', safe_name)).strip() if success else ''
            self._send_action_result(
                result,
                success=success,
                extra={'list_name': safe_name, 'list_content': list_content},
            )
            return

        if path == '/remove_socialnet':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            list_name = data.get('target_list_name', data.get('list_name', ['']))[0]
            service_key = data.get('service_key', [SOCIALNET_ALL_KEY])[0]
            success = True
            try:
                result = _remove_socialnet_list(list_name, service_key=service_key)
            except Exception as exc:
                success = False
                result = f'Ошибка удаления сервисов: {exc}'
            safe_name = _normalize_unblock_route_name(list_name) + '.txt' if success else os.path.basename(list_name)
            list_content = _read_text_file(os.path.join('/opt/etc/unblock', safe_name)).strip() if success else ''
            self._send_action_result(
                result,
                success=success,
                extra={'list_name': safe_name, 'list_content': list_content},
            )
            return

        if path == '/custom_checks_to_list':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            list_name = data.get('target_list_name', data.get('list_name', data.get('type', [''])))[0]
            success = True
            try:
                result = _append_custom_checks_to_unblock_list(list_name)
            except Exception as exc:
                success = False
                result = f'Ошибка добавления проверок в список обхода: {exc}'
            safe_name = _normalize_unblock_route_name(_unblock_route_for_key_type(list_name)) + '.txt' if success else os.path.basename(list_name)
            list_content = _read_text_file(os.path.join('/opt/etc/unblock', safe_name)).strip() if success else ''
            self._send_action_result(
                result,
                success=success,
                extra={'list_name': safe_name, 'list_content': list_content},
            )
            return

        if path == '/custom_check_add':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            preset_id = data.get('preset', [''])[0]
            label = data.get('label', [''])[0]
            url = data.get('url', [''])[0]
            success = True
            try:
                checks, result = _add_custom_check(label=label, url=url, preset_id=preset_id)
                _probe_all_pool_keys_async(stale_only=False)
                _refresh_status_caches_async(_load_current_keys())
                if success and 'уже есть' not in result:
                    result += ' Фоновая проверка пула запущена.'
            except Exception as exc:
                success = False
                checks = _load_custom_checks()
                result = f'Ошибка добавления проверки: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={
                    'custom_checks': _web_custom_checks(),
                    'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True),
                },
            )
            return

        if path == '/custom_check_delete':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            check_id = data.get('id', [''])[0]
            success = True
            try:
                _delete_custom_check(check_id)
                result = 'Проверка удалена.'
            except Exception as exc:
                success = False
                result = f'Ошибка удаления проверки: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={
                    'custom_checks': _web_custom_checks(),
                    'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True),
                },
            )
            return

        if path == '/pool_probe':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            success = True
            try:
                if not proto:
                    started, queued = _probe_all_pool_keys_async(stale_only=False)
                    if started:
                        result = f'Безопасная проверка всех пулов запущена. В очереди: {queued}. Проверка идет через временный тестовый xray и не разрывает текущее подключение.'
                    elif queued:
                        result = 'Проверка пулов уже выполняется. Дождитесь обновления статусов.'
                    else:
                        result = 'В пулах нет ключей, которым нужна проверка.'
                elif proto not in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    raise ValueError('Неизвестный протокол')
                else:
                    keys = _pool_keys_for_proto(proto)
                    started, queued = _probe_pool_keys_background(proto, keys, stale_only=False)
                    if started:
                        result = f'Безопасная проверка пула {proto} запущена. В очереди: {queued}. Проверка идет через временный тестовый xray и не разрывает текущее подключение.'
                    elif queued:
                        result = 'Проверка пула уже выполняется. Дождитесь обновления статусов.'
                    else:
                        result = f'В пуле {proto} нет ключей, которым нужна проверка.'
            except Exception as exc:
                success = False
                result = f'Ошибка запуска проверки пула: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={'pool_probe_started': success},
            )
            return

        if path == '/pool_add':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            keys_text = data.get('keys', [''])[0]
            success = True
            try:
                if proto not in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    raise ValueError('Неизвестный протокол')
                added = _add_keys_to_pool(proto, keys_text)
                result = f'Добавлено ключей в пул {proto}: {added}'
            except Exception as exc:
                success = False
                result = f'Ошибка добавления в пул: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True)},
            )
            return

        if path == '/pool_delete':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            key_to_delete = data.get('key', [''])[0]
            success = True
            try:
                _delete_pool_key(proto, key_to_delete)
                result = f'Ключ удалён из пула {proto}'
            except Exception as exc:
                success = False
                result = f'Ошибка удаления из пула: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True)},
            )
            return

        if path == '/pool_apply':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            key_to_apply = data.get('key', [''])[0]
            success = True
            apply_lock_acquired = False
            try:
                if not pool_apply_lock.acquire(blocking=False):
                    raise ValueError('Сейчас выполняется проверка или применение ключа. Дождитесь завершения операции.')
                apply_lock_acquired = True
                pools = _load_key_pools()
                if proto not in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    raise ValueError('Неизвестный протокол')
                if key_to_apply not in (pools.get(proto, []) or []):
                    raise ValueError('Ключ не найден в пуле')
                result = _install_key_for_protocol(proto, key_to_apply, verify=False)
                _set_active_key(proto, key_to_apply)
                _invalidate_web_status_cache()
                _invalidate_key_status_cache()
                _refresh_status_caches_async(_load_current_keys())
            except Exception as exc:
                success = False
                result = f'Ошибка применения ключа из пула: {exc}'
            finally:
                if apply_lock_acquired:
                    pool_apply_lock.release()
            self._send_action_result(
                result,
                success=success,
                extra={'protocol': proto, 'key': key_to_apply, 'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True)},
            )
            return

        if path == '/pool_clear':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            success = True
            try:
                if proto not in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    raise ValueError('Неизвестный протокол')
                removed = _clear_pool(proto)
                result = f'Пул {proto} очищен. Удалено ключей: {removed}'
            except Exception as exc:
                success = False
                result = f'Ошибка очистки пула: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True)},
            )
            return

        if path == '/pool_subscribe':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            sub_url = data.get('url', [''])[0]
            success = True
            try:
                if proto not in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    raise ValueError('Неизвестный протокол')
                fetched, error = _fetch_keys_from_subscription(sub_url)
                if error:
                    raise ValueError(error)
                pools = _load_key_pools()
                if proto not in pools:
                    pools[proto] = []
                added = 0
                added_keys = []
                # Если выбран vless2, добавляем vless:// ключи в пул vless2
                source_proto = proto
                if proto == 'vless2':
                    source_proto = 'vless'
                for k in fetched.get(source_proto, []):
                    if k not in pools[proto]:
                        pools[proto].append(k)
                        added += 1
                        added_keys.append(k)
                _save_key_pools(pools)
                # Запускаем фоновую проверку для добавленных ключей
                if added_keys:
                    _probe_pool_keys_background(proto, added_keys)
                result = f'Загружено из subscription и добавлено в пул {proto}: {added} ключей'
                _invalidate_web_status_cache()
                _invalidate_key_status_cache()
            except Exception as exc:
                success = False
                result = f'Ошибка загрузки subscription: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True)},
            )
            return
        

        # /pool_check убран: проверка выполняется автоматически и отображается значками в пуле.

        if path != '/install':
            self._send_html('<h1>404 Not Found</h1>', status=404)
            return
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8')
        data = parse_qs(body)
        key_type = data.get('type', [''])[0]
        key_value = data.get('key', [''])[0]
        result = 'Ключ установлен.'
        success = True
        apply_lock_acquired = False
        try:
            if not pool_apply_lock.acquire(blocking=False):
                raise ValueError('Сейчас выполняется проверка или применение ключа. Дождитесь завершения операции.')
            apply_lock_acquired = True
            if key_type == 'shadowsocks':
                shadowsocks(key_value)
                result = _apply_installed_proxy('shadowsocks', key_value, verify=False)
            elif key_type == 'vmess':
                vmess(key_value)
                result = _apply_installed_proxy('vmess', key_value, verify=False)
            elif key_type == 'vless':
                vless(key_value)
                result = _apply_installed_proxy('vless', key_value, verify=False)
            elif key_type == 'vless2':
                vless2(key_value)
                result = _apply_installed_proxy('vless2', key_value, verify=False)
            elif key_type == 'trojan':
                trojan(key_value)
                result = _apply_installed_proxy('trojan', key_value, verify=False)
            else:
                success = False
                result = 'Тип ключа не распознан.'
        except Exception as exc:
            success = False
            result = f'Ошибка установки: {exc}'
        else:
            if success and key_type in ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan'):
                _set_active_key(key_type, key_value)
                _invalidate_web_status_cache()
                _invalidate_key_status_cache()
                _refresh_status_caches_async(_load_current_keys())
        finally:
            if apply_lock_acquired:
                pool_apply_lock.release()

        self._send_action_result(
            result,
            success=success,
            extra={'protocol': key_type, 'key': key_value, 'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True)},
        )



def start_http_server():
    global web_httpd
    try:
        bind_host = _resolve_web_bind_host()
        class ReusableThreadingHTTPServer(ThreadingHTTPServer):
            allow_reuse_address = True

        server_address = (bind_host, int(browser_port))
        httpd = ReusableThreadingHTTPServer(server_address, KeyInstallHTTPRequestHandler)
        httpd.daemon_threads = True
        web_httpd = httpd
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        listen_host = bind_host or '0.0.0.0'
        _write_runtime_log(f'HTTP server listening on {listen_host}:{browser_port}; LAN-only access enforced')
    except Exception as err:
        _write_runtime_log(f'HTTP server start failed on port {browser_port}: {err}', mode='w')


def wait_for_bot_start():
    global bot_ready
    while not bot_ready and not shutdown_requested.is_set():
        time.sleep(1)


def _read_v2ray_key(file_path):
    candidate_paths = [file_path]
    file_name = os.path.basename(file_path)
    current_dir = os.path.dirname(file_path)
    alternate_dirs = []
    if current_dir == XRAY_CONFIG_DIR:
        alternate_dirs.append(V2RAY_CONFIG_DIR)
    elif current_dir == V2RAY_CONFIG_DIR:
        alternate_dirs.append(XRAY_CONFIG_DIR)
    for directory in alternate_dirs:
        candidate_paths.append(os.path.join(directory, file_name))

    for candidate_path in candidate_paths:
        try:
            with open(candidate_path, 'r', encoding='utf-8') as f:
                value = f.read().strip()
            if value:
                return value
        except Exception:
            continue
    return None


def _save_v2ray_key(file_path, key):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(key.strip())


def _parse_vmess_key(key):
    if not key.startswith('vmess://'):
        raise ValueError('Неверный протокол, ожидается vmess://')
    encodedkey = key[8:]
    try:
        decoded = base64.b64decode(encodedkey + '=' * (-len(encodedkey) % 4)).decode('utf-8')
    except Exception as exc:
        raise ValueError(f'Не удалось декодировать vmess-ключ: {exc}')
    try:
        data = json.loads(decoded.replace("'", '"'))
    except Exception as exc:
        raise ValueError(f'Неверный JSON в vmess-ключе: {exc}')
    if not data.get('add') or not data.get('port') or not data.get('id'):
        raise ValueError('В vmess-ключе нет server/port/id')
    if data.get('net') == 'grpc':
        service_name = data.get('serviceName') or data.get('grpcSettings', {}).get('serviceName')
        if not service_name:
            data['serviceName'] = data.get('add')
    return data


def _parse_vless_key(key):
    parsed = urlparse(key)
    if parsed.scheme != 'vless':
        raise ValueError('Неверный протокол, ожидается vless://')
    if not parsed.hostname:
        raise ValueError('В vless-ключе отсутствует адрес сервера')
    if not parsed.username:
        raise ValueError('В vless-ключе отсутствует UUID')
    params = parse_qs(parsed.query)
    address = parsed.hostname
    port = parsed.port or 443
    user_id = parsed.username
    security = params.get('security', ['none'])[0]
    encryption = params.get('encryption', ['none'])[0]
    flow = params.get('flow', [''])[0]
    host = params.get('host', [''])[0]
    if not address and host:
        address = host
    network = params.get('type', params.get('network', ['tcp']))[0]
    path = params.get('path', ['/'])[0]
    if path == '':
        path = '/'
    sni = params.get('sni', [''])[0] or host or address
    service_name = params.get('serviceName', [''])[0]
    public_key = params.get('pbk', params.get('publicKey', ['']))[0]
    short_id = params.get('sid', params.get('shortId', ['']))[0]
    fingerprint = params.get('fp', params.get('fingerprint', ['']))[0]
    spider_x = params.get('spx', params.get('spiderX', ['']))[0]
    alpn = params.get('alpn', [''])[0]
    if not service_name and (network == 'grpc' or security == 'reality'):
        service_name = address
    return {
        'address': address,
        'port': port,
        'id': user_id,
        'security': security,
        'encryption': encryption,
        'flow': flow,
        'host': host,
        'path': path,
        'sni': sni,
        'type': network,
        'serviceName': service_name,
        'publicKey': public_key,
        'shortId': short_id,
        'fingerprint': fingerprint,
        'spiderX': spider_x,
        'alpn': alpn
    }


def _build_v2ray_config(vmess_key=None, vless_key=None, vless2_key=None, shadowsocks_key=None, trojan_key=None):
    config_data = {
        'log': {
            'access': '/dev/null',
            'error': CORE_PROXY_ERROR_LOG,
            'loglevel': 'warning'
        },
        'dns': {
            'hosts': {
                'api.telegram.org': '149.154.167.220'
            },
            'servers': ['8.8.8.8', '1.1.1.1', 'localhost'],
            'queryStrategy': 'UseIPv4'
        },
        'inbounds': [],
        'outbounds': [],
        'routing': {
            'domainStrategy': 'IPIfNonMatch',
            'rules': []
        }
    }

    if vmess_key:
        vmess_outbound = _proxy_outbound_from_key('vmess', vmess_key, 'proxy-vmess')
        config_data['inbounds'].append({
            'port': int(localportvmess),
            'listen': '127.0.0.1',
            'protocol': 'socks',
            'settings': {
                'auth': 'noauth',
                'udp': True,
                'ip': '127.0.0.1'
            },
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
            'tag': 'in-vmess'
        })
        config_data['inbounds'].append({
            'port': int(localportvmess_transparent),
            'listen': '0.0.0.0',
            'protocol': 'dokodemo-door',
            'settings': {
                'network': 'tcp',
                'followRedirect': True
            },
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
            'tag': 'in-vmess-transparent'
        })
        config_data['outbounds'].append(vmess_outbound)
        config_data['routing']['rules'].append({
            'type': 'field',
            'inboundTag': ['in-vmess', 'in-vmess-transparent'],
            'outboundTag': 'proxy-vmess',
            'enabled': True
        })

    if shadowsocks_key:
        shadowsocks_outbound = _proxy_outbound_from_key('shadowsocks', shadowsocks_key, 'proxy-shadowsocks')
        config_data['inbounds'].append({
            'port': int(localportsh_bot),
            'listen': '127.0.0.1',
            'protocol': 'socks',
            'settings': {
                'auth': 'noauth',
                'udp': True,
                'ip': '127.0.0.1'
            },
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
            'tag': 'in-shadowsocks'
        })
        config_data['outbounds'].append(shadowsocks_outbound)
        config_data['routing']['rules'].append({
            'type': 'field',
            'inboundTag': ['in-shadowsocks'],
            'outboundTag': 'proxy-shadowsocks',
            'enabled': True
        })

    def add_vless_route(key_value, socks_port, transparent_port, socks_tag, transparent_tag, outbound_tag):
        if not key_value:
            return
        vless_outbound = _proxy_outbound_from_key('vless', key_value, outbound_tag)
        config_data['inbounds'].append({
            'port': int(socks_port),
            'listen': '127.0.0.1',
            'protocol': 'socks',
            'settings': {
                'auth': 'noauth',
                'udp': True,
                'ip': '127.0.0.1'
            },
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
            'tag': socks_tag
        })
        config_data['inbounds'].append({
            'port': int(transparent_port),
            'listen': '0.0.0.0',
            'protocol': 'dokodemo-door',
            'settings': {
                'network': 'tcp',
                'followRedirect': True
            },
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
            'tag': transparent_tag
        })
        config_data['outbounds'].append(vless_outbound)
        config_data['routing']['rules'].append({
            'type': 'field',
            'inboundTag': [socks_tag, transparent_tag],
            'outboundTag': outbound_tag,
            'enabled': True
        })

    add_vless_route(vless_key, localportvless, localportvless_transparent, 'in-vless', 'in-vless-transparent', 'proxy-vless')
    add_vless_route(vless2_key, localportvless2, localportvless2_transparent, 'in-vless2', 'in-vless2-transparent', 'proxy-vless2')

    if trojan_key:
        trojan_outbound = _proxy_outbound_from_key('trojan', trojan_key, 'proxy-trojan')
        config_data['inbounds'].append({
            'port': int(localporttrojan_bot),
            'listen': '127.0.0.1',
            'protocol': 'socks',
            'settings': {
                'auth': 'noauth',
                'udp': True,
                'ip': '127.0.0.1'
            },
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
            'tag': 'in-trojan'
        })
        config_data['outbounds'].append(trojan_outbound)
        config_data['routing']['rules'].append({
            'type': 'field',
            'inboundTag': ['in-trojan'],
            'outboundTag': 'proxy-trojan',
            'enabled': True
        })

    if config_data['outbounds']:
        config_data['outbounds'].append({'protocol': 'freedom', 'tag': 'direct'})
        config_data['routing']['rules'].insert(0, {
            'type': 'field',
            'domain': CONNECTIVITY_CHECK_DOMAINS,
            'outboundTag': 'direct',
            'enabled': True
        })
        config_data['routing']['rules'].append({
            'type': 'field',
            'port': '0-65535',
            'outboundTag': 'direct',
            'enabled': True
        })

    return config_data


def _write_v2ray_config(vmess_key=None, vless_key=None, vless2_key=None, shadowsocks_key=None, trojan_key=None):
    config_json = _build_v2ray_config(vmess_key, vless_key, vless2_key, shadowsocks_key, trojan_key)
    os.makedirs(CORE_PROXY_CONFIG_DIR, exist_ok=True)
    with open(CORE_PROXY_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config_json, f, ensure_ascii=False, indent=2)


def _write_all_proxy_core_config():
    _write_v2ray_config(
        _read_v2ray_key(VMESS_KEY_PATH),
        _read_v2ray_key(VLESS_KEY_PATH),
        _read_v2ray_key(VLESS2_KEY_PATH),
        _load_shadowsocks_key(),
        _load_trojan_key(),
    )


def vless(key):
    _parse_vless_key(key)
    _save_v2ray_key(VLESS_KEY_PATH, key)
    _write_all_proxy_core_config()


def vless2(key):
    _parse_vless_key(key)
    _save_v2ray_key(VLESS2_KEY_PATH, key)
    _write_all_proxy_core_config()


def vmess(key):
    _parse_vmess_key(key)
    _save_v2ray_key(VMESS_KEY_PATH, key)
    _write_all_proxy_core_config()

def trojan(key):
    raw_key = key.strip()
    trojan_data = _parse_trojan_key(raw_key)
    config = {
        'run_type': 'nat',
        'local_addr': '::',
        'local_port': int(localporttrojan),
        'remote_addr': trojan_data['address'],
        'remote_port': int(trojan_data['port']),
        'password': [trojan_data['password']],
        'raw_uri': raw_key,
        'type': trojan_data['type'],
        'security': trojan_data['security'],
        'sni': trojan_data['sni'],
        'host': trojan_data['host'],
        'path': trojan_data['path'],
        'serviceName': trojan_data['serviceName'],
        'fingerprint': trojan_data['fingerprint'],
        'alpn': trojan_data['alpn'],
        'fragment': trojan_data['fragment'],
        'ssl': {
            'verify': False,
            'verify_hostname': False,
        }
    }
    with open('/opt/etc/trojan/config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, separators=(',', ':'))
    _write_all_proxy_core_config()

def _decode_shadowsocks_uri(key):
    if not key.startswith('ss://'):
        raise ValueError('Неверный протокол, ожидается ss://')
    payload = key[5:]
    payload, _, _ = payload.partition('#')
    payload, _, _ = payload.partition('?')
    if '@' in payload:
        left, right = payload.rsplit('@', 1)
        host_part = right
        if ':' not in host_part:
            raise ValueError('Не удалось определить host:port в Shadowsocks-ключе')
        server, port = host_part.split(':', 1)
        try:
            decoded = base64.urlsafe_b64decode(left + '=' * (-len(left) % 4)).decode('utf-8')
            if ':' not in decoded:
                raise ValueError('Неверный формат декодированного payload Shadowsocks')
            method, password = decoded.split(':', 1)
        except Exception:
            decoded = unquote(left)
            if ':' not in decoded:
                raise ValueError('Неверный формат Shadowsocks credentials')
            method, password = decoded.split(':', 1)
    else:
        decoded = base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)).decode('utf-8')
        if '@' not in decoded:
            raise ValueError('Не удалось разобрать Shadowsocks-ключ')
        creds, host_part = decoded.rsplit('@', 1)
        if ':' not in host_part or ':' not in creds:
            raise ValueError('Неверный формат раскодированного Shadowsocks-URI')
        server, port = host_part.split(':', 1)
        method, password = creds.split(':', 1)
    return server, port, method, password


def shadowsocks(key=None):
    raw_key = key.strip()
    server, port, method, password = _decode_shadowsocks_uri(raw_key)
    config = {
        'server': [server],
        'mode': 'tcp_and_udp',
        'server_port': int(port),
        'password': password,
        'timeout': 86400,
        'method': method,
        'local_address': '::',
        'local_port': int(localportsh),
        'fast_open': False,
        'ipv6_first': True,
        'raw_uri': raw_key
    }
    with open('/opt/etc/shadowsocks.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    _write_all_proxy_core_config()

def main():
    global proxy_mode
    _daemonize_process()
    _register_signal_handlers()
    _write_runtime_log('main() entered', mode='w')
    _cleanup_pool_probe_runtime(kill_processes=True)
    start_http_server()
    try:
        _write_all_proxy_core_config()
        os.system(CORE_PROXY_SERVICE_SCRIPT + ' restart')
    except Exception as exc:
        _write_runtime_log(f'Не удалось пересобрать core proxy config при старте: {exc}')
    if _load_bot_autostart():
        globals()['bot_ready'] = True
    saved_proxy_mode = _load_proxy_mode()
    proxy_mode = saved_proxy_mode
    ok, error = update_proxy(proxy_mode)
    if not ok:
        proxy_mode = config.default_proxy_mode
        update_proxy(proxy_mode, persist=False)
        if saved_proxy_mode in proxy_settings:
            _save_proxy_mode(saved_proxy_mode)
    elif proxy_mode in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
        startup_settings = {
            'shadowsocks': localportsh_bot,
            'vmess': localportvmess,
            'vless': localportvless,
            'vless2': localportvless2,
            'trojan': localporttrojan_bot,
        }
        startup_port = startup_settings.get(proxy_mode)
        endpoint_ok, endpoint_message = _check_local_proxy_endpoint(proxy_mode, startup_port)
        if not endpoint_ok:
            _write_runtime_log(f'Прокси-режим {proxy_mode} не ответил при старте: {endpoint_message}. Перезапускаю core proxy.')
            try:
                os.system(CORE_PROXY_SERVICE_SCRIPT + ' restart')
                time.sleep(3)
            except Exception:
                pass
            endpoint_ok, endpoint_message = _check_local_proxy_endpoint(proxy_mode, startup_port)
        if not endpoint_ok:
            fallback_mode = proxy_mode
            _write_runtime_log(f'Прокси-режим {fallback_mode} временно отключён при старте: {endpoint_message}')
            update_proxy('none', persist=False)
            _save_proxy_mode(fallback_mode)
        else:
            api_status = check_telegram_api(retries=0, retry_delay=0, connect_timeout=8, read_timeout=10)
            if not api_status.startswith('✅'):
                _write_runtime_log(f'Прокси-режим {proxy_mode} не подтверждён при старте: {api_status}')
    _start_auto_failover_thread()
    _ensure_current_keys_in_pools()
    _write_runtime_log('Web-only сервер запущен. Ожидание команд...')
    try:
        while not shutdown_requested.is_set():
            shutdown_requested.wait(1)
    except KeyboardInterrupt:
        pass
    _finalize_shutdown()
if __name__ == '__main__':
    main()
