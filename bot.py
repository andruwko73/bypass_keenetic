#!/usr/bin/python3

#  2023. Keenetic DNS bot /  Проект: bypass_keenetic / Автор: tas_unn
#  GitHub: https://github.com/tas-unn/bypass_keenetic
#  Данный бот предназначен для управления обхода блокировок на роутерах Keenetic
#  Демо-бот: https://t.me/keenetic_dns_bot
#
#  Файл: bot.py, Версия 2.2.1, последнее изменение: 19.04.2026, 15:10

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
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

import telebot
from telebot import types
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
AUTO_FAILOVER_GRACE_SECONDS = 60
AUTO_FAILOVER_POLL_SECONDS = 10
auto_failover_state = {
    'last_ok': 0.0,
    'last_fail': 0.0,
    'last_attempt': 0.0,
    'in_progress': False,
}


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
    with open(KEY_PROBE_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _record_key_probe(proto, key_value, tg_ok=None, yt_ok=None):
    cache = _load_key_probe_cache()
    key_id = _hash_key(key_value)
    entry = cache.get(key_id, {})
    if not isinstance(entry, dict):
        entry = {}
    entry['proto'] = proto
    entry['ts'] = time.time()
    if tg_ok is not None:
        entry['tg_ok'] = bool(tg_ok)
    if yt_ok is not None:
        entry['yt_ok'] = bool(yt_ok)
    cache[key_id] = entry
    _save_key_probe_cache(cache)


def _key_probe_is_fresh(entry, now=None):
    if not entry:
        return False
    try:
        ts = float(entry.get('ts', 0))
    except (TypeError, ValueError):
        return False
    return (now or time.time()) - ts < KEY_PROBE_CACHE_TTL


TELEGRAM_SVG_B64 = 'PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCA1MTIgNTEyIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxjaXJjbGUgY3g9IjI1NiIgY3k9IjI1NiIgcj0iMjU2IiBmaWxsPSIjMzdBRUUyIi8+PHBhdGggZD0iTTExOSAyNjVsMjY1LTEwNGMxMi01IDIzIDMgMTkgMTlsLTQ1IDIxMmMtMyAxMy0xMiAxNi0yNCAxMGwtNjYtNDktMzIgMzFjLTQgNC03IDctMTUgN2w2LTg1IDE1NS0xNDBjNy02LTItMTAtMTEtNGwtMTkyIDEyMS04My0yNmMtMTgtNi0xOC0xOCA0LTI2eiIgZmlsbD0iI2ZmZiIvPjwvc3ZnPg=='
YOUTUBE_SVG_B64 = 'PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCA0NDMgMzIwIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSI0NDMiIGhlaWdodD0iMzIwIiByeD0iNzAiIGZpbGw9IiNGRjAwMDAiLz48cG9seWdvbiBwb2ludHM9IjE3Nyw5NiAzNTUsMTYwIDE3NywyMjQiIGZpbGw9IiNmZmYiLz48L3N2Zz4='


def _telegram_icon_html(opacity=1.0):
    style = f'vertical-align:middle;opacity:{opacity:g}'
    return f'<img src="data:image/svg+xml;base64,{TELEGRAM_SVG_B64}" width="16" height="16" alt="Telegram" style="{style}">'


def _youtube_icon_html(opacity=1.0):
    style = f'vertical-align:middle;opacity:{opacity:g}'
    return f'<img src="data:image/svg+xml;base64,{YOUTUBE_SVG_B64}" width="16" height="16" alt="YouTube" style="{style}">'


def _load_key_pools():
    try:
        with open(KEY_POOLS_PATH, 'r', encoding='utf-8') as f:
            value = json.load(f)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return {proto: [] for proto in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']}


def _save_key_pools(pools):
    os.makedirs(os.path.dirname(KEY_POOLS_PATH), exist_ok=True)
    with open(KEY_POOLS_PATH, 'w', encoding='utf-8') as f:
        json.dump(pools, f, ensure_ascii=False, indent=2)


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
    pools = _load_key_pools()
    keys = list(pools.get(proto, []) or [])
    if key in keys:
        keys.remove(key)
    keys.insert(0, key)
    pools[proto] = keys
    _save_key_pools(pools)


def _install_key_for_protocol(proto, key_value):
    if proto == 'shadowsocks':
        shadowsocks(key_value)
        return _apply_installed_proxy('shadowsocks', key_value)
    if proto == 'vmess':
        vmess(key_value)
        return _apply_installed_proxy('vmess', key_value)
    if proto == 'vless':
        vless(key_value)
        return _apply_installed_proxy('vless', key_value)
    if proto == 'vless2':
        vless2(key_value)
        return _apply_installed_proxy('vless2', key_value)
    if proto == 'trojan':
        trojan(key_value)
        return _apply_installed_proxy('trojan', key_value)
    raise ValueError(f'Unsupported protocol: {proto}')


def _attempt_auto_failover():
    now = time.time()
    if auto_failover_state['in_progress']:
        return
    if auto_failover_state['last_attempt'] and now - auto_failover_state['last_attempt'] < 30:
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
        pools = _load_key_pools()
        candidates = []
        for proto in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
            for key_value in pools.get(proto, []) or []:
                candidates.append((proto, key_value))

        if not candidates:
            _write_runtime_log('Auto-failover: ключей в пулах нет, переключать не на что.')
            return

        _write_runtime_log(f'Auto-failover: Telegram API не отвечает >{AUTO_FAILOVER_GRACE_SECONDS}s (режим {proxy_mode}). Пробуем ключи из пулов.')
        for proto, key_value in candidates:
            try:
                result = _install_key_for_protocol(proto, key_value)
            except Exception as exc:
                _write_runtime_log(f'Auto-failover: ошибка установки {proto} ключа: {exc}')
                continue

            proxy_url = proxy_settings.get(proto)
            ok2, _ = _check_telegram_api_through_proxy(proxy_url, connect_timeout=6, read_timeout=10)
            if ok2:
                yt_ok, _ = _check_http_through_proxy(proxy_url, url='https://www.youtube.com', connect_timeout=3, read_timeout=5)
                update_proxy(proto)
                _set_active_key(proto, key_value)
                _record_key_probe(proto, key_value, tg_ok=True, yt_ok=yt_ok)
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

token = config.token
usernames = config.usernames
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

bot = telebot.TeleBot(token)
sid = "0"
PROXY_MODE_FILE = '/opt/etc/bot_proxy_mode'
BOT_AUTOSTART_FILE = '/opt/etc/bot_autostart'
TELEGRAM_COMMAND_JOB_FILE = '/opt/etc/bot/telegram_command_job.json'
TELEGRAM_COMMAND_RESULT_FILE = '/opt/etc/bot/telegram_command_result.json'
TELEGRAM_RESULT_RETRY_INTERVAL = 30

WEB_STATUS_CACHE_TTL = 60
KEY_STATUS_CACHE_TTL = 60
STATUS_CACHE_TTL = min(WEB_STATUS_CACHE_TTL, KEY_STATUS_CACHE_TTL)
WEB_STATUS_STARTUP_GRACE_PERIOD = 45
KEY_PROBE_CACHE_TTL = 3600
KEY_PROBE_MAX_PER_RUN = 8
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
bot_polling = False
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
status_refresh_lock = threading.Lock()
status_refresh_in_progress = set()
pool_probe_lock = threading.Lock()
pool_apply_lock = threading.Lock()
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
MENU_STATE_UNSET = object()
chat_menu_state_lock = threading.Lock()
chat_menu_states = {}
chat_pool_pages = {}


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


def _normalize_username(value):
    if value is None:
        return ''
    normalized = str(value).strip()
    if normalized.startswith('@'):
        normalized = normalized[1:]
    return normalized.casefold()


def _build_authorized_identities(raw_values):
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
        normalized = _normalize_username(text)
        if normalized:
            normalized_usernames.add(normalized)
    return normalized_usernames, numeric_ids


AUTHORIZED_USERNAMES, AUTHORIZED_USER_IDS = _build_authorized_identities(usernames)
EXTRA_AUTHORIZED_USER_IDS = getattr(config, 'authorized_user_ids', [])
_, EXTRA_NUMERIC_USER_IDS = _build_authorized_identities(EXTRA_AUTHORIZED_USER_IDS)
AUTHORIZED_USER_IDS.update(EXTRA_NUMERIC_USER_IDS)


def _raw_github_url(path):
    return f'https://raw.githubusercontent.com/{fork_repo_owner}/{fork_repo_name}/main/{path}?ts={int(time.time())}'


def _fetch_remote_text(url, timeout=20):
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


SERVICE_LIST_SOURCES = {
    'youtube': {
        'label': 'YouTube',
        'aliases': ['youtube', 'yt', 'ютуб'],
        'url': 'https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/youtube.lst',
    },
    'telegram': {
        'label': 'Telegram',
        'aliases': ['telegram', 'tg', 'телеграм', 'телега'],
        'url': 'https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/telegram.lst',
    },
    'meta': {
        'label': 'Instagram / Meta',
        'aliases': ['meta', 'instagram', 'insta', 'facebook', 'whatsapp', 'threads', 'инстаграм'],
        'url': 'https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/meta.lst',
    },
    'discord': {
        'label': 'Discord',
        'aliases': ['discord', 'дискорд'],
        'url': 'https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/discord.lst',
    },
    'tiktok': {
        'label': 'TikTok',
        'aliases': ['tiktok', 'tik-tok', 'тик ток', 'тикток'],
        'url': 'https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/tiktok.lst',
    },
    'twitter': {
        'label': 'X / Twitter',
        'aliases': ['twitter', 'x', 'твиттер'],
        'url': 'https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/twitter.lst',
    },
}


def _service_list_alias_map():
    aliases = {}
    for key, source in SERVICE_LIST_SOURCES.items():
        aliases[key] = key
        aliases[source.get('label', key).lower()] = key
        for alias in source.get('aliases', []):
            aliases[alias.lower()] = key
    return aliases


def _get_chat_menu_state(chat_id):
    with chat_menu_state_lock:
        state = chat_menu_states.get(chat_id)
        if state is None:
            state = {'level': 0, 'bypass': None}
            chat_menu_states[chat_id] = state
        return dict(state)


def _set_chat_menu_state(chat_id, level=MENU_STATE_UNSET, bypass=MENU_STATE_UNSET):
    with chat_menu_state_lock:
        state = chat_menu_states.get(chat_id)
        if state is None:
            state = {'level': 0, 'bypass': None}
            chat_menu_states[chat_id] = state
        if level is not MENU_STATE_UNSET:
            state['level'] = level
        if bypass is not MENU_STATE_UNSET:
            state['bypass'] = bypass


def _get_pool_page(chat_id):
    with chat_menu_state_lock:
        return int(chat_pool_pages.get(chat_id, 0) or 0)


def _set_pool_page(chat_id, page):
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 0
    with chat_menu_state_lock:
        chat_pool_pages[chat_id] = max(0, page)


def _clear_pool_page(chat_id):
    with chat_menu_state_lock:
        chat_pool_pages.pop(chat_id, None)


def _telegram_info_text_from_readme():
    readme_text = ''
    try:
        readme_text = _fetch_remote_text(_raw_github_url('README.md'))
    except Exception:
        readme_text = _read_text_file(README_PATH)

    if not readme_text.strip():
        return (
            'Информация временно недоступна: README.md не найден.\n\n'
            'Откройте страницу роутера 192.168.1.1:8080 или README в репозитории форка.'
        )

    lines = readme_text.splitlines()
    sections = []
    current_title = ''
    current_lines = []

    def flush_section():
        if current_title and current_lines:
            sections.append((current_title, current_lines[:]))

    for raw_line in lines:
        line = raw_line.rstrip()
        if line.startswith('## '):
            flush_section()
            current_title = line[3:].strip()
            current_lines = []
            continue
        if current_title:
            current_lines.append(line)
    flush_section()

    wanted_titles = ['Об этом форке', 'Как работает бот на странице 192.168.1.1:8080']
    selected = []
    for wanted in wanted_titles:
        for title, section_lines in sections:
            if title == wanted:
                selected.append((title, section_lines))
                break

    if not selected:
        selected = sections[:2]

    text_lines = []
    for title, section_lines in selected:
        if text_lines:
            text_lines.append('')
        text_lines.append(f'<b>{html.escape(title)}</b>')
        for line in section_lines:
            stripped = line.strip()
            if stripped.startswith('### Скриншоты интерфейса'):
                break
            if not stripped:
                if text_lines and text_lines[-1] != '':
                    text_lines.append('')
                continue
            if stripped.startswith('<') or stripped.startswith('```'):
                continue
            if stripped.startswith('!['):
                continue
            cleaned = html.escape(stripped.replace('`', ''))
            cleaned = re.sub(
                r'\[([^\]]+)\]\(([^\)]+)\)',
                lambda match: f'<a href="{html.escape(match.group(2), quote=True)}">{html.escape(match.group(1))}</a>',
                cleaned,
            )
            text_lines.append(cleaned)

    cleaned_lines = []
    previous_blank = False
    for line in text_lines:
        if not line:
            if not previous_blank:
                cleaned_lines.append('')
            previous_blank = True
            continue
        cleaned_lines.append(line)
        previous_blank = False

    result = '\n'.join(cleaned_lines).strip()
    if not result:
        return 'Информация временно недоступна: README.md не содержит подходящего текста.'
    return result[:3900]


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


def _message_debug_text(message):
    text = getattr(message, 'text', None)
    if text is None:
        return '<non-text>'
    text = str(text).replace('\r', ' ').replace('\n', ' ')
    if len(text) > 120:
        return text[:117] + '...'
    return text


def _authorize_message(message, handler_name):
    user = getattr(message, 'from_user', None)
    chat = getattr(message, 'chat', None)
    user_id = getattr(user, 'id', None)
    username = getattr(user, 'username', None)
    normalized_username = _normalize_username(username)
    chat_id = getattr(chat, 'id', None)
    chat_type = getattr(chat, 'type', None)

    authorized = False
    reason = 'unauthorized'
    if user_id in AUTHORIZED_USER_IDS:
        authorized = True
        reason = 'user_id'
    elif normalized_username and normalized_username in AUTHORIZED_USERNAMES:
        authorized = True
        reason = 'username'
    elif not normalized_username:
        reason = 'missing_username'

    _write_runtime_log(
        f'handler={handler_name} chat_id={chat_id} chat_type={chat_type} '
        f'user_id={user_id} username={username!r} authorized={authorized} '
        f'reason={reason} text={_message_debug_text(message)}'
    )
    return authorized, reason


def _send_unauthorized_message(message, reason):
    if reason == 'missing_username':
        text = 'У вашего Telegram-аккаунта не задан username. Задайте username в настройках Telegram и повторите команду.'
    else:
        text = 'Вы не являетесь автором канала'
    bot.send_message(message.chat.id, text)


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
    global bot_polling
    if shutdown_requested.is_set():
        return
    shutdown_requested.set()
    bot_polling = False
    if reason:
        _write_runtime_log(f'Запрошена остановка бота: {reason}')
    try:
        bot.stop_polling()
    except Exception:
        pass
    try:
        bot.stop_bot()
    except Exception:
        pass
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
    try:
        bot.delete_webhook(timeout=10)
    except Exception as exc:
        _write_runtime_log(f'Не удалось удалить webhook при остановке: {exc}')
    try:
        bot.close()
    except Exception as exc:
        close_error = str(exc).lower()
        if '429' in close_error or 'too many requests' in close_error:
            _write_runtime_log('Bot API close недоступен в первые 10 минут после старта, остановка продолжена без него')
        else:
            _write_runtime_log(f'Не удалось закрыть bot instance при остановке: {exc}')


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


def _is_polling_conflict(err):
    text = str(err).lower()
    return 'terminated by other getupdates request' in text or '409 conflict' in text


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
        return 'Legacy-пути бота уже доступны.'
    return 'Подготовка legacy-путей: ' + ', '.join(notes)


def _chunk_text(text, limit=3500):
    if not text or not text.strip():
        return []
    chunks = []
    current = []
    current_len = 0
    for line in text.splitlines():
        extra = len(line) + 1
        if current and current_len + extra > limit:
            chunks.append('\n'.join(current))
            current = [line]
            current_len = extra
        else:
            current.append(line)
            current_len += extra
    if current:
        chunks.append('\n'.join(current))
    return chunks or ['']


def _send_telegram_chunks(chat_id, text, reply_markup=None):
    chunks = [chunk for chunk in _chunk_text(text) if chunk.strip()]
    for index, chunk in enumerate(chunks):
        markup = reply_markup if index == len(chunks) - 1 else None
        bot.send_message(chat_id, chunk, reply_markup=markup)


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


def _service_list_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [types.KeyboardButton(source['label']) for source in SERVICE_LIST_SOURCES.values()]
    for index in range(0, len(buttons), 2):
        markup.row(*buttons[index:index + 2])
    markup.add(types.KeyboardButton("🔙 Назад"))
    return markup


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


def _handle_getlist_request(message, service_name, route_name=None, reply_markup=None):
    service_key = _resolve_service_list_name(service_name)
    if not service_key:
        names = ', '.join(source['label'] for source in SERVICE_LIST_SOURCES.values())
        bot.send_message(message.chat.id, f'⚠️ Не знаю такой сервис. Доступно: {names}', reply_markup=reply_markup)
        return

    route = _resolve_unblock_list_selection(route_name) if route_name else None
    if route and route.endswith('.txt'):
        route = route[:-4]
    if not route:
        state = _get_chat_menu_state(message.chat.id)
        route = state.get('bypass') or 'vless'
    if not re.match(r'^[A-Za-z0-9_-]+$', route or ''):
        bot.send_message(message.chat.id, '⚠️ Некорректное имя маршрута.', reply_markup=reply_markup)
        return

    source = SERVICE_LIST_SOURCES[service_key]
    try:
        raw_text = _fetch_remote_text(source['url'], timeout=25)
        entries = _parse_service_domains(raw_text)
        if not entries:
            bot.send_message(message.chat.id, f'⚠️ Список {source["label"]} загружен, но домены не найдены.', reply_markup=reply_markup)
            return
        added, total = _append_entries_to_unblock_list(route, entries)
    except requests.RequestException as exc:
        bot.send_message(message.chat.id, f'⚠️ Не удалось загрузить список {source["label"]}: {exc}', reply_markup=reply_markup)
        return
    except Exception as exc:
        bot.send_message(message.chat.id, f'⚠️ Не удалось применить список {source["label"]}: {exc}', reply_markup=reply_markup)
        return

    label = _list_label(f'{route}.txt')
    bot.send_message(
        message.chat.id,
        f'✅ {source["label"]}: добавлено {added} новых записей, всего в маршруте {label}: {total}. Списки применяются.',
        reply_markup=reply_markup,
    )


def _build_main_menu_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("🔰 Установка и удаление")
    item2 = types.KeyboardButton("🔑 Ключи и мосты")
    item3 = types.KeyboardButton("📝 Списки обхода")
    item4 = types.KeyboardButton("📄 Информация")
    item5 = types.KeyboardButton("⚙️ Сервис")
    markup.add(item1)
    markup.add(item2, item3)
    markup.add(item4, item5)
    return markup


def _build_keys_menu_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("Shadowsocks")
    item2 = types.KeyboardButton("Vmess")
    item3 = types.KeyboardButton("Vless 1")
    item4 = types.KeyboardButton("Vless 2")
    item5 = types.KeyboardButton("Trojan")
    item6 = types.KeyboardButton("Где брать ключи❔")
    item7 = types.KeyboardButton("🌐 Через браузер")
    item8 = types.KeyboardButton("📦 Пул ключей")
    markup.add(item1, item2)
    markup.add(item3, item4)
    markup.add(item5)
    markup.add(item6, item8)
    markup.add(item7)
    markup.add(types.KeyboardButton("🔙 Назад"))
    return markup


def _build_service_menu_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("♻️ Перезагрузить сервисы")
    item2 = types.KeyboardButton("‼️Перезагрузить роутер")
    item3 = types.KeyboardButton("‼️DNS Override")
    item4 = types.KeyboardButton("📊 Статус ключей")
    back = types.KeyboardButton("🔙 Назад")
    markup.add(item1, item2)
    markup.add(item3, item4)
    markup.add(back)
    return markup


def _telegram_command_markup(menu_name):
    return _build_service_menu_markup() if menu_name == 'service' else _build_main_menu_markup()


def _run_telegram_command_worker(action, repo_owner, repo_name, chat_id, menu_name, branch='main'):
    try:
        return_code, output = _run_script_action(action, repo_owner, repo_name, branch=branch)
    except Exception as exc:
        return_code = 1
        output = f'Ошибка запуска фоновой команды: {exc}'
    result = {
        'action': action,
        'chat_id': int(chat_id),
        'menu_name': menu_name,
        'return_code': return_code,
        'output': output,
        'finished_at': time.time(),
    }
    _write_json_file(TELEGRAM_COMMAND_RESULT_FILE, result)
    _remove_file(TELEGRAM_COMMAND_JOB_FILE)


def _start_telegram_background_command(action, repo_owner, repo_name, chat_id, menu_name, branch='main'):
    state = _read_json_file(TELEGRAM_COMMAND_JOB_FILE, {}) or {}
    started_at = float(state.get('started_at', 0) or 0)
    if state.get('running') and started_at and time.time() - started_at < 1800:
        return False, '⏳ Уже выполняется обновление. Дождитесь итогового сообщения после перезапуска бота.'

    _write_json_file(TELEGRAM_COMMAND_JOB_FILE, {
        'running': True,
        'action': action,
        'chat_id': int(chat_id),
        'menu_name': menu_name,
        'started_at': time.time(),
    })

    module_name = os.path.splitext(os.path.basename(BOT_SOURCE_PATH))[0]
    module_dir = os.path.dirname(BOT_SOURCE_PATH)
    code = (
        'import sys; '
        f"sys.path.insert(0, {module_dir!r}); "
        f'import {module_name} as bot_module; '
        f'bot_module._run_telegram_command_worker({action!r}, {repo_owner!r}, {repo_name!r}, {int(chat_id)!r}, {menu_name!r}, branch={branch!r})'
    )
    subprocess.Popen(
        [sys.executable, '-c', code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    return True, ''


def _deliver_pending_telegram_command_result():
    result = _read_json_file(TELEGRAM_COMMAND_RESULT_FILE)
    if not isinstance(result, dict):
        return

    chat_id = result.get('chat_id')
    if not chat_id:
        _remove_file(TELEGRAM_COMMAND_RESULT_FILE)
        return

    markup = _telegram_command_markup(result.get('menu_name', 'main'))
    action = result.get('action', '')
    return_code = int(result.get('return_code', 1))
    output = (result.get('output') or '').strip()

    try:
        if output:
            _send_telegram_chunks(chat_id, output, reply_markup=markup)
        if return_code == 0:
            final_message = '✅ Обновление завершено. Лог отправлен выше.' if action == '-update' else '✅ Команда завершена. Лог отправлен выше.'
        else:
            final_message = '⚠️ Обновление завершилось с ошибкой. Полный лог отправлен выше.' if action == '-update' else '⚠️ Команда завершилась с ошибкой. Полный лог отправлен выше.'
        bot.send_message(chat_id, final_message, reply_markup=markup)
        _remove_file(TELEGRAM_COMMAND_RESULT_FILE)
    except Exception as exc:
        _write_runtime_log(f'Не удалось доставить результат фоновой Telegram-команды: {exc}')


def _start_telegram_result_retry_worker():
    def worker():
        while not shutdown_requested.is_set():
            try:
                if os.path.exists(TELEGRAM_COMMAND_RESULT_FILE):
                    _deliver_pending_telegram_command_result()
            except Exception as exc:
                _write_runtime_log(f'Ошибка retry-доставки результата фоновой Telegram-команды: {exc}')
            shutdown_requested.wait(TELEGRAM_RESULT_RETRY_INTERVAL)

    threading.Thread(target=worker, daemon=True).start()


def _install_proxy_from_message(message, key_type, key_value, reply_markup):
    installers = {
        'shadowsocks': shadowsocks,
        'vmess': vmess,
        'vless': vless,
        'vless2': vless2,
        'trojan': trojan,
    }
    try:
        installers[key_type](key_value)
        result = _apply_installed_proxy(key_type, key_value)
    except Exception as exc:
        result = f'Ошибка установки: {exc}'

    level_reset_markup = reply_markup
    try:
        bot.send_message(message.chat.id, result, reply_markup=level_reset_markup)
    except Exception:
        fallback_result = (
            f'{result}\n\n'
            'Текущий режим бота сохранён, но отправить подтверждение в этот чат не удалось.'
        )
        try:
            bot.send_message(message.chat.id, fallback_result, reply_markup=level_reset_markup)
        except Exception:
            pass
    return result


def _download_repo_script(repo_owner, repo_name, branch='main'):
    session = requests.Session()
    session.trust_env = False
    api_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/commits/{branch}'
    api_response = session.get(
        api_url,
        headers={'Accept': 'application/vnd.github+json', 'Cache-Control': 'no-cache', 'Pragma': 'no-cache'},
        timeout=30,
    )
    api_response.raise_for_status()
    repo_ref = str(api_response.json().get('sha', '')).strip()
    if not repo_ref:
        raise ValueError('GitHub не вернул commit SHA для script.sh')

    url = f'https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{repo_ref}/script.sh'
    response = session.get(
        url,
        headers={'Cache-Control': 'no-cache', 'Pragma': 'no-cache'},
        timeout=30,
    )
    response.raise_for_status()
    script_text = response.text
    if '#!/bin/sh' not in script_text:
        raise ValueError('GitHub вернул некорректный script.sh')
    with open('/opt/root/script.sh', 'w', encoding='utf-8') as file:
        file.write(script_text)
    os.chmod('/opt/root/script.sh', stat.S_IRWXU)
    return url, script_text, repo_ref


def _build_direct_fetch_env():
    env = os.environ.copy()
    for key in DIRECT_FETCH_ENV_KEYS:
        env.pop(key, None)
    return env


def _run_script_action(action, repo_owner=None, repo_name=None, progress_command=None, branch='main'):
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


def _send_message_after_service_restart(chat_id, text, reply_markup=None):
    active_mode = _load_proxy_mode()
    if active_mode in proxy_settings:
        update_proxy(active_mode)
    proxy_url = proxy_settings.get(active_mode)
    port = None
    if proxy_url:
        match = re.search(r':(\d+)$', proxy_url)
        if match:
            port = match.group(1)
    if port:
        for _ in range(12):
            if _check_socks5_handshake(port):
                break
            time.sleep(1)
    for _ in range(3):
        try:
            bot.send_message(chat_id, text, reply_markup=reply_markup)
            return True
        except Exception as exc:
            _write_runtime_log(f'Не удалось отправить Telegram-сообщение после перезапуска сервисов: {exc}')
            time.sleep(2)
    try:
        previous_mode = proxy_mode
        update_proxy('none')
        bot.send_message(chat_id, text, reply_markup=reply_markup)
        if previous_mode in proxy_settings:
            update_proxy(previous_mode)
        return True
    except Exception as exc:
        _write_runtime_log(f'Не удалось отправить Telegram-сообщение после перезапуска сервисов напрямую: {exc}')
        if active_mode in proxy_settings:
            update_proxy(active_mode)
        return False


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
            branch='feature/independent-rework',
        )
        return output
    if command == 'update_no_bot':
        _, output = _run_script_action(
            '-update',
            'andruwko73',
            'bypass_keenetic',
            progress_command='update_no_bot',
            branch='feature/web-only',
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


def _append_socialnet_list(list_name):
    safe_name = os.path.basename(list_name)
    target_path = os.path.join('/opt/etc/unblock', safe_name)
    current = _read_text_file(target_path)
    social_text = _fetch_remote_text('https://raw.githubusercontent.com/tas-unn/bypass_keenetic/main/socialnet.txt')
    return _save_unblock_list(safe_name, current + '\n' + social_text)


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


def _telegram_unblock_list_options():
    return [(entry['label'], entry['name'][:-4]) for entry in _load_unblock_lists(with_content=False)]


def _resolve_unblock_list_selection(text):
    normalized = text.strip()
    for label, base_name in _telegram_unblock_list_options():
        if normalized in [label, base_name]:
            return base_name
    return normalized


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
    pools = _load_key_pools()
    changed = False
    for proto in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
        key_value = (current_keys.get(proto) or '').strip()
        if not key_value:
            continue
        keys = list(pools.get(proto, []) or [])
        if key_value in keys:
            continue
        keys.insert(0, key_value)
        pools[proto] = keys
        changed = True
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


def _check_telegram_api_through_proxy(proxy_url=None, connect_timeout=6, read_timeout=10):
    url = 'https://api.telegram.org/'
    proxies = {'https': proxy_url, 'http': proxy_url} if proxy_url else None
    try:
        response = requests.get(url, timeout=(connect_timeout, read_timeout), proxies=proxies)
        if response.status_code < 500:
            return True, 'Доступ к api.telegram.org подтверждён.'
        return False, f'Telegram API вернул HTTP {response.status_code}.'
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
            'details': f'{endpoint_message} Бот не может использовать этот ключ.',
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
        connect_timeout=3,
        read_timeout=4,
    )
    yt_ok, yt_message = _check_http_through_proxy(
        proxy_url,
        url='https://www.youtube.com',
        connect_timeout=2,
        read_timeout=3,
    )
    _record_key_probe(key_name, key_value, tg_ok=api_ok, yt_ok=yt_ok)
    if (endpoint_ok and not api_ok and now - process_started_at < WEB_STATUS_STARTUP_GRACE_PERIOD and
            _is_transient_telegram_api_failure(api_message)):
        return {
            'tone': 'warn',
            'label': 'Проверяется',
            'details': (f'{endpoint_message} Telegram API ещё перепроверяется после рестарта. '
                        'Обновите страницу через несколько секунд.').strip(),
            'endpoint_ok': endpoint_ok,
            'endpoint_message': endpoint_message,
            'api_ok': False,
            'api_message': api_message,
            'yt_ok': yt_ok,
            'yt_message': yt_message,
        }
    return {
        'tone': 'ok' if api_ok else 'warn',
        'label': 'Работает' if api_ok else f'Прокси поднят, но трафик не проходит к&nbsp;{_telegram_icon_html(opacity=1.0)}',
        'details': f'{endpoint_message} {api_message}'.strip(),
        'endpoint_ok': endpoint_ok,
        'endpoint_message': endpoint_message,
        'api_ok': api_ok,
        'api_message': api_message,
        'yt_ok': yt_ok,
        'yt_message': yt_message,
    }


def _placeholder_protocol_statuses(current_keys):
    result = {}
    for key_name, key_value in current_keys.items():
        if key_value.strip():
            result[key_name] = {
                'tone': 'warn',
                'label': 'Проверяется',
                'details': 'Фоновая проверка ключа выполняется. Обновите страницу через несколько секунд.',
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
        ('Бот запущен.', 100, 'Бот перезапущен, обновление завершено'),
        ('Обновление выполнено. Сервисы перезапущены.', 96, 'Сервисы обновлены, идёт перезапуск бота'),
        ('Версия бота', 90, 'Проверка версии и завершение обновления'),
        ('Обновления скачены, права настроены.', 82, 'Новые файлы установлены'),
        ('Бэкап создан.', 70, 'Резервная копия готова, идёт замена файлов'),
        ('Сервисы остановлены.', 60, 'Сервисы остановлены перед заменой файлов'),
        ('Файлы успешно скачаны и подготовлены.', 45, 'Файлы загружены, подготавливается установка'),
        ('Скачиваем обновления во временную папку и проверяем файлы.', 30, 'Идёт загрузка файлов из GitHub'),
        ('Пакеты обновлены.', 20, 'Пакеты Entware обновлены'),
        ('Начинаем обновление.', 12, 'Запущен сценарий обновления'),
        ('Скрипт загружен из', 8, 'Сценарий обновления получен с GitHub'),
        ('Legacy-пути бота уже доступны.', 6, 'Проверка путей запуска бота'),
        ('Подготовка legacy-путей:', 6, 'Подготовка путей запуска бота'),
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
    return True, f'⏳ Команда "{label}" запущена. Страница обновится автоматически.'


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
# Telegram прокручивает reply-клавиатуру целиком, без закрепления нижних строк.
# Поэтому показываем весь пул в одной прокручиваемой клавиатуре, а служебные
# кнопки добавляем после списка ключей.
POOL_PAGE_SIZE = 1000
POOL_PROTOCOL_LABELS = {
    'shadowsocks': 'Shadowsocks',
    'vmess': 'Vmess',
    'vless': 'Vless 1',
    'vless2': 'Vless 2',
    'trojan': 'Trojan',
}
POOL_PROTOCOL_BUTTON_PREFIXES = {
    'shadowsocks': 'SS',
    'vmess': 'VM',
    'vless': 'V1',
    'vless2': 'V2',
    'trojan': 'TR',
}
TELEGRAM_BUTTON_ICON = 'TG'
YOUTUBE_BUTTON_ICON = 'YT'


def _pool_proto_label(proto):
    return POOL_PROTOCOL_LABELS.get(proto, proto)


def _pool_proto_button_prefix(proto):
    return POOL_PROTOCOL_BUTTON_PREFIXES.get(proto, str(proto or '').upper())


def _pool_proto_from_button_prefix(prefix):
    value = (prefix or '').strip().upper()
    for proto, proto_prefix in POOL_PROTOCOL_BUTTON_PREFIXES.items():
        if value == proto_prefix.upper():
            return proto
    return None


def _shorten_button_text(text, limit=38):
    value = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(value) <= limit:
        return value
    return value[:max(1, limit - 1)].rstrip() + '…'


def _pool_add_page_controls(markup, info):
    if info['total_pages'] <= 1:
        return
    previous_button = 'Ключи ◀️' if info['page'] > 0 else '·'
    next_button = 'Ключи ▶️' if info['page'] < info['total_pages'] - 1 else '·'
    page_button = f'Стр. {info["page"] + 1}/{info["total_pages"]}'
    markup.row(
        types.KeyboardButton(previous_button),
        types.KeyboardButton(page_button),
        types.KeyboardButton(next_button),
    )


def _pool_protocol_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [types.KeyboardButton(_pool_proto_label(proto)) for proto in POOL_PROTOCOL_ORDER]
    markup.row(buttons[0], buttons[1])
    markup.row(buttons[2], buttons[3])
    markup.row(buttons[4])
    markup.row(types.KeyboardButton('🔙 В меню ключей'), types.KeyboardButton('🔙 Назад'))
    return markup


def _resolve_pool_protocol(text):
    value = (text or '').strip().lower()
    aliases = {
        'shadowsocks': 'shadowsocks',
        'ss': 'shadowsocks',
        'vmess': 'vmess',
        'vless': 'vless',
        'vless 1': 'vless',
        'vless1': 'vless',
        'vless 2': 'vless2',
        'vless2': 'vless2',
        'trojan': 'trojan',
    }
    for proto, label in POOL_PROTOCOL_LABELS.items():
        aliases[label.lower()] = proto
        aliases[f'📦 {label}'.lower()] = proto
    return aliases.get(value)


def _remove_inline_keyboard(chat_id, message_id):
    if not chat_id or not message_id:
        return
    try:
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
    except Exception as exc:
        if 'message is not modified' not in str(exc).lower():
            _write_runtime_log(f'Ошибка удаления inline-клавиатуры пула: {exc}')


def _clear_pool_inline_keyboard(chat_id, message_id=None):
    if message_id:
        _remove_inline_keyboard(chat_id, message_id)


def _pool_action_markup(proto, page=0):
    _, info = _format_pool_page(proto, page)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    current_keys = _load_current_keys()
    current_key = current_keys.get(proto)
    cache = _load_key_probe_cache()
    for offset, key_value in enumerate(info['keys'][info['start']:info['end']], start=info['start'] + 1):
        probe = cache.get(_hash_key(key_value), {})
        markup.row(types.KeyboardButton(_pool_key_button_label(offset, key_value, probe=probe, current_key=current_key, proto=proto)))
    _pool_add_page_controls(markup, info)
    markup.row(types.KeyboardButton('➕ Добавить ключи'), types.KeyboardButton('🔗 Загрузить subscription'))
    markup.row(types.KeyboardButton('🔍 Проверить пул'), types.KeyboardButton('🧹 Очистить пул'))
    markup.row(types.KeyboardButton('🗑 Удаление'), types.KeyboardButton('🔄 Обновить пул'))
    markup.row(types.KeyboardButton('🔙 К выбору протокола'), types.KeyboardButton('🔙 В меню ключей'))
    markup.row(types.KeyboardButton('🔙 Назад'))
    return markup


def _pool_delete_markup(proto, page=0):
    _, info = _format_pool_page(proto, page)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    current_keys = _load_current_keys()
    current_key = current_keys.get(proto)
    cache = _load_key_probe_cache()
    for offset, key_value in enumerate(info['keys'][info['start']:info['end']], start=info['start'] + 1):
        probe = cache.get(_hash_key(key_value), {})
        markup.row(types.KeyboardButton(_pool_key_button_label(offset, key_value, probe=probe, current_key=current_key, proto=proto, action='delete')))
    _pool_add_page_controls(markup, info)
    markup.row(types.KeyboardButton('🔙 К пулу'), types.KeyboardButton('🔙 Назад'))
    return markup


def _pool_clear_confirm_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton('✅ Очистить пул'), types.KeyboardButton('Отмена'))
    markup.row(types.KeyboardButton('🔙 К пулу'), types.KeyboardButton('🔙 Назад'))
    return markup


def _pool_input_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton('🔙 К пулу'), types.KeyboardButton('🔙 Назад'))
    return markup


def _pool_probe_text(probe):
    if not probe:
        return 'не проверялся'
    badges = []
    if probe.get('tg_ok'):
        badges.append(f'{TELEGRAM_BUTTON_ICON}✅')
    elif 'tg_ok' in probe:
        badges.append(f'{TELEGRAM_BUTTON_ICON}❌')
    if probe.get('yt_ok'):
        badges.append(f'{YOUTUBE_BUTTON_ICON}✅')
    elif 'yt_ok' in probe:
        badges.append(f'{YOUTUBE_BUTTON_ICON}❌')
    if not badges:
        return 'не проверялся'
    return ' '.join(badges)


def _pool_probe_button_text(probe):
    if not probe:
        return f'{TELEGRAM_BUTTON_ICON}? {YOUTUBE_BUTTON_ICON}?'
    tg = f'{TELEGRAM_BUTTON_ICON}✅' if probe.get('tg_ok') else (f'{TELEGRAM_BUTTON_ICON}❌' if 'tg_ok' in probe else f'{TELEGRAM_BUTTON_ICON}?')
    yt = f'{YOUTUBE_BUTTON_ICON}✅' if probe.get('yt_ok') else (f'{YOUTUBE_BUTTON_ICON}❌' if 'yt_ok' in probe else f'{YOUTUBE_BUTTON_ICON}?')
    return f'{tg} {yt}'


def _pool_key_button_label(index, key_value, probe=None, current_key=None, proto=None, action='apply'):
    display_name = _shorten_button_text(_pool_key_display_name(key_value), limit=24)
    status = _pool_probe_button_text(probe)
    proto_prefix = _pool_proto_button_prefix(proto)
    if action == 'delete':
        prefix = f'✕ {proto_prefix} {index}.'
    elif current_key and key_value == current_key:
        prefix = f'✅ {proto_prefix} {index}.'
    else:
        prefix = f'{proto_prefix} {index}.'
    return _shorten_button_text(f'{prefix} {display_name} {status}', limit=52)


def _pool_key_line(index, key_value, probe=None, current_key=None):
    marker = ' — АКТИВЕН' if current_key and key_value == current_key else ''
    display_name = _pool_key_display_name(key_value)
    key_hash = _hash_key(key_value)[:8]
    return f'{index}. {display_name}{marker} [{key_hash}] — {_pool_probe_text(probe)}'


def _format_pool_summary():
    current_keys = _load_current_keys()
    pools = _ensure_current_keys_in_pools(current_keys)
    lines = ['📦 Пул ключей', 'Выберите протокол для управления пулом.', '']
    for proto in POOL_PROTOCOL_ORDER:
        keys = pools.get(proto, []) or []
        current_key = current_keys.get(proto)
        active = 'активный есть' if current_key else 'активный не задан'
        lines.append(f'{_pool_proto_label(proto)}: {len(keys)} ключей, {active}')
    return '\n'.join(lines)


def _format_pool_details(proto):
    current_keys = _load_current_keys()
    pools = _ensure_current_keys_in_pools(current_keys)
    cache = _load_key_probe_cache()
    keys = pools.get(proto, []) or []
    label = _pool_proto_label(proto)
    if not keys:
        return f'📦 {label}: пул пуст.'
    lines = [f'📦 {label}: {len(keys)} ключей', '* — текущий активный ключ', '']
    current_key = current_keys.get(proto)
    for index, key_value in enumerate(keys, start=1):
        probe = cache.get(_hash_key(key_value), {})
        lines.append(_pool_key_line(index, key_value, probe=probe, current_key=current_key))
    return '\n'.join(lines)


def _pool_page_info(proto, page=0):
    keys = _pool_keys_for_proto(proto)
    total = len(keys)
    total_pages = max(1, (total + POOL_PAGE_SIZE - 1) // POOL_PAGE_SIZE)
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 0
    page = max(0, min(page, total_pages - 1))
    start = page * POOL_PAGE_SIZE
    end = min(start + POOL_PAGE_SIZE, total)
    return {
        'keys': keys,
        'total': total,
        'total_pages': total_pages,
        'page': page,
        'start': start,
        'end': end,
    }


def _format_pool_page(proto, page=0, prefix=None):
    info = _pool_page_info(proto, page)
    label = _pool_proto_label(proto)
    header = f'📦 {label}: {info["total"]} ключей'
    if info['total_pages'] > 1:
        header += f' · стр. {info["page"] + 1}/{info["total_pages"]}'
    lines = []
    if prefix:
        lines.extend([prefix, ''])
    lines.append(header)
    if not info['keys']:
        lines.append('Пул пуст. Добавьте ключи вручную или через subscription.')
    else:
        lines.append('Ключи выведены в нижней клавиатуре.')
        lines.append('Нажмите кнопку с кодом протокола V1/V2/VM/TR/SS, чтобы применить ключ. Для удаления нажмите «🗑 Удаление».')
    return '\n'.join(lines), info


def _send_pool_page(chat_id, proto, page=0, prefix=None):
    text, info = _format_pool_page(proto, page, prefix=prefix)
    _set_pool_page(chat_id, info['page'])
    bot.send_message(chat_id, text, reply_markup=_pool_action_markup(proto, info['page']))


def _send_pool_delete_page(chat_id, proto, page=0, prefix=None):
    text, info = _format_pool_page(proto, page, prefix=prefix)
    _set_pool_page(chat_id, info['page'])
    bot.send_message(chat_id, text, reply_markup=_pool_delete_markup(proto, info['page']))


def _send_pool_details(chat_id, proto, prefix=None, suffix=None, reply_markup=None):
    parts = [part for part in (prefix, _format_pool_details(proto), suffix) if part]
    _send_telegram_chunks(chat_id, '\n\n'.join(parts), reply_markup=reply_markup)


def _pool_keys_for_proto(proto):
    pools = _ensure_current_keys_in_pools()
    return list(pools.get(proto, []) or [])


def _pool_key_by_index(proto, raw_index):
    keys = _pool_keys_for_proto(proto)
    try:
        index = int(str(raw_index).strip())
    except Exception:
        raise ValueError('Введите номер ключа из списка.')
    if index < 1 or index > len(keys):
        raise ValueError(f'Номер вне диапазона. В пуле {_pool_proto_label(proto)} ключей: {len(keys)}.')
    return index, keys[index - 1]


def _pool_reply_key_action(text):
    value = (text or '').strip()
    action = 'apply'
    lowered = value.lower()
    for marker in ('✕', '×', '❌', '🗑', 'x'):
        if lowered.startswith(marker.lower()):
            action = 'delete'
            value = value[len(marker):].strip()
            break
    for marker in ('✅', '✔️', '✔', '✓'):
        if value.startswith(marker):
            value = value[len(marker):].strip()
            break

    parts = value.split(maxsplit=1)
    if len(parts) == 2:
        button_proto = _pool_proto_from_button_prefix(parts[0])
        if button_proto:
            index_match = re.match(r'^(\d+)(?:[.)]\s|$)', parts[1])
            if index_match:
                return action, index_match.group(1), button_proto

    legacy_match = re.match(r'^(\d+)(?:[.)]\s|$)', value)
    if legacy_match:
        return 'legacy', legacy_match.group(1), None
    return None, None, None


def _pool_reply_page_delta(text):
    value = (text or '').strip()
    if value in ('Ключи ◀️', 'Ключи ◀', '◀️ Предыдущая', '◀ Предыдущая'):
        return -1
    if value in ('Ключи ▶️', 'Ключи ▶', 'Следующая ▶️', 'Следующая ▶'):
        return 1
    return 0


def _is_pool_page_indicator(text):
    return bool(re.match(r'^Стр\.\s+\d+/\d+$', (text or '').strip()))


def _is_pool_page_noop(text):
    value = (text or '').strip()
    return value in ('·', '') or _is_pool_page_indicator(value)


def _pool_key_by_callback_id(proto, key_id):
    key_id = (key_id or '').strip()
    for index, key_value in enumerate(_pool_keys_for_proto(proto), start=1):
        if _hash_key(key_value)[:12] == key_id:
            return index, key_value
    raise ValueError('Ключ не найден в пуле. Обновите пул и попробуйте снова.')


def _apply_pool_key(proto, key_value):
    result = _install_key_for_protocol(proto, key_value)
    _set_active_key(proto, key_value)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return result


def _apply_pool_key_background(chat_id, proto, key_value, index, page=0):
    def worker():
        if not pool_apply_lock.acquire(blocking=False):
            bot.send_message(
                chat_id,
                'Уже выполняется применение ключа. Дождитесь результата и попробуйте снова.',
                reply_markup=_pool_action_markup(proto, page),
            )
            return
        try:
            result = _apply_pool_key(proto, key_value)
            display_name = _pool_key_display_name(key_value)
            prefix = f'✅ Ключ #{index} «{display_name}» применён для {_pool_proto_label(proto)}.\n{result}'
        except Exception as exc:
            prefix = f'Ошибка применения ключа #{index} из пула {_pool_proto_label(proto)}: {exc}'
        finally:
            pool_apply_lock.release()
        _send_pool_page(chat_id, proto, page=page, prefix=prefix)

    threading.Thread(target=worker, daemon=True).start()


def _delete_pool_key(proto, key_value):
    pools = _load_key_pools()
    keys = list(pools.get(proto, []) or [])
    if key_value not in keys:
        raise ValueError('Ключ не найден в пуле.')
    keys.remove(key_value)
    pools[proto] = keys
    _save_key_pools(pools)
    cache = _load_key_probe_cache()
    cache.pop(_hash_key(key_value), None)
    _save_key_probe_cache(cache)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()


def _clear_pool(proto):
    pools = _load_key_pools()
    removed_keys = list(pools.get(proto, []) or [])
    pools[proto] = []
    _save_key_pools(pools)
    if removed_keys:
        cache = _load_key_probe_cache()
        for key_value in removed_keys:
            cache.pop(_hash_key(key_value), None)
        _save_key_probe_cache(cache)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return len(removed_keys)


def _probe_pool_keys_background(proto, keys):
    if not keys:
        return

    def worker():
        proxy_url = proxy_settings.get(proto)
        for key_value in keys:
            try:
                tg_ok, _ = _check_telegram_api_through_proxy(proxy_url, connect_timeout=3, read_timeout=4)
                yt_ok, _ = _check_http_through_proxy(proxy_url, connect_timeout=2, read_timeout=3)
                _record_key_probe(proto, key_value, tg_ok=tg_ok, yt_ok=yt_ok)
            except Exception:
                pass
        _invalidate_web_status_cache()
        _invalidate_key_status_cache()

    threading.Thread(target=worker, daemon=True).start()


def _add_keys_to_pool(proto, keys_text):
    pools = _load_key_pools()
    if proto not in pools:
        pools[proto] = []
    new_keys = [line.strip() for line in (keys_text or '').splitlines() if line.strip()]
    added_keys = []
    for key_value in new_keys:
        if key_value not in pools[proto]:
            pools[proto].append(key_value)
            added_keys.append(key_value)
    _save_key_pools(pools)
    _probe_pool_keys_background(proto, added_keys)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return len(added_keys)


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


def _apply_installed_proxy(key_type, key_value):
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
                f'не поднялся. Текущий режим бота {active_label} сохранён. {diagnostics}').strip()

    endpoint_ok, endpoint_message = _check_local_proxy_endpoint(key_type, current['port'])
    if not endpoint_ok:
        return (f'⚠️ {current["label"]} ключ сохранён, но {endpoint_message} '
                f'Текущий режим бота {active_label} сохранён. {diagnostics}').strip()

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
                f'Текущий режим бота {active_label} сохранён.').strip()
    return (f'⚠️ {current["label"]} ключ сохранён. {endpoint_message} '
            f'Но Telegram API не проходит через этот ключ. '
            f'Текущий режим бота {active_label} сохранён. '
            f'❌ Не удалось подключиться к Telegram API: {api_probe_message} {diagnostics}').strip()


def update_proxy(proxy_type):
    global proxy_mode
    proxy_url = proxy_settings.get(proxy_type)
    if proxy_url and proxy_url.startswith('socks') and not _has_socks_support():
        return False, ('Для SOCKS-прокси требуется модуль PySocks. ' 
                       'Установите python3-pysocks или выберите другой режим.')

    proxy_mode = proxy_type
    if proxy_supports_http.get(proxy_type, False) and proxy_url:
        telebot.apihelper.proxy = {'https': proxy_url, 'http': proxy_url}
        os.environ['HTTPS_PROXY'] = proxy_url
        os.environ['HTTP_PROXY'] = proxy_url
        os.environ['https_proxy'] = proxy_url
        os.environ['http_proxy'] = proxy_url
    else:
        telebot.apihelper.proxy = {}
        for key in ['HTTPS_PROXY', 'HTTP_PROXY', 'https_proxy', 'http_proxy']:
            if key in os.environ:
                del os.environ[key]

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
        'max retries exceeded',
        'failed to establish a new connection',
        'connection reset',
    ]
    return any(marker in text for marker in markers)


def _build_web_status(current_keys, protocols=None):
    now = time.time()
    state_label = 'polling активен' if bot_polling else ('ожидает запуска' if not bot_ready else 'процесс запущен, polling недоступен')
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
        elif (socks_ok and now - process_started_at < WEB_STATUS_STARTUP_GRACE_PERIOD and
                _is_transient_telegram_api_failure(api_message)):
            api_status = ('⏳ Прокси-режим поднят, Telegram API ещё перепроверяется после рестарта. '
                          'Обновите страницу через несколько секунд.')
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
        api_status = check_telegram_api(retries=0, retry_delay=0, connect_timeout=3, read_timeout=4)
        if (proxy_mode != 'none' and socks_ok and not api_status.startswith('✅') and
                now - process_started_at < WEB_STATUS_STARTUP_GRACE_PERIOD and
                _is_transient_telegram_api_failure(api_status)):
            api_status = ('⏳ Прокси-режим поднят, Telegram API ещё перепроверяется после рестарта. '
                          'Обновите страницу через несколько секунд.')
    else:
        api_status = check_telegram_api(retries=0, retry_delay=0, connect_timeout=3, read_timeout=4)
    snapshot = {
        'state_label': state_label,
        'proxy_mode': proxy_mode,
        'api_status': api_status,
        'socks_details': socks_details,
        'fallback_reason': _last_proxy_disable_reason(),
    }
    return snapshot


def _status_snapshot_signature(current_keys):
    return tuple((name, current_keys.get(name, '')) for name in sorted(current_keys))


def _build_status_snapshot(current_keys, force_refresh=False):
    signature = _status_snapshot_signature(current_keys)
    now = time.time()
    if (
        not force_refresh and
        status_snapshot_cache['data'] is not None and
        status_snapshot_cache['signature'] == signature and
        now - status_snapshot_cache['timestamp'] < STATUS_CACHE_TTL
    ):
        return status_snapshot_cache['data']

    protocols = {}
    for key_name, key_value in current_keys.items():
        try:
            protocols[key_name] = _protocol_status_for_key(key_name, key_value)
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


def _placeholder_web_status_snapshot():
    return {
        'state_label': 'polling активен' if bot_polling else ('ожидает запуска' if not bot_ready else 'процесс запущен, polling недоступен'),
        'proxy_mode': proxy_mode,
        'api_status': '⏳ Фоновая проверка связи выполняется. Обновите страницу через несколько секунд.',
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


def _probe_all_pool_keys_async():
    """Фоновая проверка всех ключей во всех пулах для отображения значков Telegram/YouTube."""
    if not pool_probe_lock.acquire(blocking=False):
        return

    def worker():
        try:
            pools = _load_key_pools()
            cache = _load_key_probe_cache()
            now = time.time()
            checked = 0
            for proto, keys in pools.items():
                proxy_url = proxy_settings.get(proto)
                for k in keys:
                    if checked >= KEY_PROBE_MAX_PER_RUN:
                        return
                    if _key_probe_is_fresh(cache.get(_hash_key(k)), now=now):
                        continue
                    try:
                        tg_ok, _ = _check_telegram_api_through_proxy(proxy_url, connect_timeout=3, read_timeout=4)
                        yt_ok, _ = _check_http_through_proxy(proxy_url, connect_timeout=2, read_timeout=3)
                        _record_key_probe(proto, k, tg_ok=tg_ok, yt_ok=yt_ok)
                        checked += 1
                    except Exception:
                        pass
        except Exception as exc:
            _write_runtime_log(f'Ошибка фоновой проверки пула ключей: {exc}')
        finally:
            pool_probe_lock.release()
    threading.Thread(target=worker, daemon=True).start()


def _authorize_callback(call, handler_name):
    proxy = type('CallbackMessageProxy', (), {})()
    proxy.from_user = getattr(call, 'from_user', None)
    proxy.chat = getattr(getattr(call, 'message', None), 'chat', None)
    proxy.text = getattr(call, 'data', '')
    return _authorize_message(proxy, handler_name)


# список смайлов для меню
#  ✅ ❌ ♻️ 📃 📆 🔑 📄 ❗ ️⚠️ ⚙️ 📝 📆 🗑 📄️⚠️ 🔰 ❔ ‼️ 📑
@bot.message_handler(commands=['start'])
def start(message):
    authorized, reason = _authorize_message(message, 'start')
    if not authorized:
        _send_unauthorized_message(message, reason)
        return
    _set_chat_menu_state(message.chat.id, level=0, bypass=None)
    markup = _build_main_menu_markup()
    bot.send_message(message.chat.id, '✅ Добро пожаловать в меню!', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: bool((getattr(call, 'data', '') or '').startswith('pool:')))
def pool_callback(call):
    try:
        authorized, reason = _authorize_callback(call, 'pool_callback')
        if not authorized:
            bot.answer_callback_query(call.id, 'Нет доступа', show_alert=True)
            return

        data = (call.data or '').split(':')
        action = data[1] if len(data) > 1 else ''
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        _clear_pool_inline_keyboard(chat_id, message_id)

        if action == 'protocols':
            _set_chat_menu_state(chat_id, level=20, bypass=None)
            _clear_pool_page(chat_id)
            bot.answer_callback_query(call.id, 'Кнопки перенесены вниз')
            bot.send_message(chat_id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
            return

        if action == 'keys-menu':
            _set_chat_menu_state(chat_id, level=8, bypass=None)
            _clear_pool_page(chat_id)
            bot.answer_callback_query(call.id, 'Открыто меню ключей')
            bot.send_message(chat_id, '🔑 Ключи и мосты', reply_markup=_build_keys_menu_markup())
            return

        if action == 'select' and len(data) >= 3:
            proto = _resolve_pool_protocol(data[2])
            if not proto:
                raise ValueError('Неизвестный протокол.')
            _set_chat_menu_state(chat_id, level=21, bypass=proto)
            bot.answer_callback_query(call.id, f'Открыт пул {_pool_proto_label(proto)}')
            _send_pool_page(chat_id, proto, page=0)
            return

        if len(data) < 3:
            raise ValueError('Некорректная команда пула.')

        proto = _resolve_pool_protocol(data[2])
        if not proto:
            raise ValueError('Неизвестный протокол.')

        if action == 'page':
            page = data[3] if len(data) > 3 else 0
            _set_chat_menu_state(chat_id, level=21, bypass=proto)
            bot.answer_callback_query(call.id)
            _send_pool_page(chat_id, proto, page=page)
            return

        if action == 'add':
            _set_chat_menu_state(chat_id, level=22, bypass=proto)
            bot.answer_callback_query(call.id)
            bot.send_message(
                chat_id,
                f'Отправьте один или несколько ключей для пула {_pool_proto_label(proto)}. Каждый ключ с новой строки.',
                reply_markup=_pool_input_markup(),
            )
            return

        if action == 'subscribe':
            _set_chat_menu_state(chat_id, level=23, bypass=proto)
            bot.answer_callback_query(call.id)
            bot.send_message(
                chat_id,
                f'Отправьте subscription URL для пула {_pool_proto_label(proto)}.',
                reply_markup=_pool_input_markup(),
            )
            return

        if action == 'probe':
            page = data[3] if len(data) > 3 else 0
            _probe_pool_keys_background(proto, _pool_keys_for_proto(proto))
            bot.answer_callback_query(call.id, 'Проверка запущена')
            _set_chat_menu_state(chat_id, level=21, bypass=proto)
            _send_pool_page(chat_id, proto, page=page, prefix='Запущена фоновая проверка пула. Статусы обновятся через несколько секунд.')
            return

        if action == 'clear-confirm':
            page = data[3] if len(data) > 3 else 0
            _set_chat_menu_state(chat_id, level=26, bypass=proto)
            _set_pool_page(chat_id, page)
            bot.answer_callback_query(call.id)
            bot.send_message(
                chat_id,
                f'Очистить весь пул {_pool_proto_label(proto)}? Это удалит все ключи из пула.',
                reply_markup=_pool_clear_confirm_markup(),
            )
            return

        if action == 'clear':
            page = data[3] if len(data) > 3 else 0
            removed = _clear_pool(proto)
            bot.answer_callback_query(call.id, 'Пул очищен')
            _set_chat_menu_state(chat_id, level=21, bypass=proto)
            _send_pool_page(chat_id, proto, page=page, prefix=f'Пул {_pool_proto_label(proto)} очищен. Удалено ключей: {removed}.')
            return

        if action in ('apply', 'delete') and len(data) >= 5:
            key_id = data[3]
            page = data[4]
            index, key_value = _pool_key_by_callback_id(proto, key_id)
            if action == 'apply':
                bot.answer_callback_query(call.id, f'Применяю ключ #{index}...')
                _set_chat_menu_state(chat_id, level=21, bypass=proto)
                bot.send_message(
                    chat_id,
                    f'Применяю ключ #{index} для {_pool_proto_label(proto)}. Это может занять до 30 секунд.',
                    reply_markup=_pool_action_markup(proto, page),
                )
                _apply_pool_key_background(chat_id, proto, key_value, index, page=page)
            else:
                _delete_pool_key(proto, key_value)
                bot.answer_callback_query(call.id, f'Ключ #{index} удалён')
                _set_chat_menu_state(chat_id, level=21, bypass=proto)
                _send_pool_page(chat_id, proto, page=page, prefix=f'Ключ #{index} удалён из пула {_pool_proto_label(proto)}.')
            return

        raise ValueError('Неизвестная команда пула.')
    except Exception as exc:
        _write_runtime_log(f'Ошибка callback пула ключей: {exc}')
        try:
            bot.answer_callback_query(call.id, f'Ошибка: {exc}', show_alert=True)
        except Exception:
            pass


@bot.message_handler(content_types=['text'])
def bot_message(message):
    try:
        authorized, reason = _authorize_message(message, 'text')
        if not authorized:
            _send_unauthorized_message(message, reason)
            return

        main = types.ReplyKeyboardMarkup(resize_keyboard=True)
        m1 = types.KeyboardButton("🔰 Установка и удаление")
        m2 = types.KeyboardButton("🔑 Ключи и мосты")
        m3 = types.KeyboardButton("📝 Списки обхода")
        m4 = types.KeyboardButton("📄 Информация")
        m5 = types.KeyboardButton("⚙️ Сервис")
        main.add(m1)
        main.add(m2, m3)
        main.add(m4, m5)

        service = types.ReplyKeyboardMarkup(resize_keyboard=True)
        m1 = types.KeyboardButton("♻️ Перезагрузить сервисы")
        m2 = types.KeyboardButton("‼️Перезагрузить роутер")
        m3 = types.KeyboardButton("‼️DNS Override")
        m4 = types.KeyboardButton("📊 Статус ключей")
        back = types.KeyboardButton("🔙 Назад")
        service.add(m1, m2)
        service.add(m3, m4)
        service.add(back)

        if message.chat.type == 'private':
            command = message.text.split(maxsplit=1)[0].split('@', 1)[0]
            if command == '/getlist':
                parts = message.text.split()
                if len(parts) < 2:
                    names = ', '.join(source['label'] for source in SERVICE_LIST_SOURCES.values())
                    bot.send_message(message.chat.id, f'Использование: /getlist название [маршрут]\nДоступно: {names}', reply_markup=main)
                    return
                route_name = parts[2] if len(parts) > 2 else None
                _handle_getlist_request(message, parts[1], route_name=route_name, reply_markup=main)
                return

            if message.text == '📊 Статус ключей':
                text_lines = ['<b>Статус доступа к Telegram по ключам (web):</b>']
                emoji = {'ok': '✅', 'warn': '⚠️', 'fail': '❌', 'empty': '➖'}
                proto_labels = {
                    'shadowsocks': 'Shadowsocks',
                    'vmess': 'Vmess',
                    'vless': 'Vless 1',
                    'vless2': 'Vless 2',
                    'trojan': 'Trojan',
                }
                try:
                    current_keys = _load_current_keys()
                    snapshot = _build_status_snapshot(current_keys, force_refresh=True)
                    statuses = snapshot.get('protocols', {}) if isinstance(snapshot, dict) else {}
                except Exception as exc:
                    statuses = {}
                    text_lines.append(f'❌ Ошибка получения статуса: {html.escape(str(exc))}')
                for proto in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    st = statuses.get(proto, {}) if isinstance(statuses, dict) else {}
                    mark = emoji.get(st.get('tone', 'empty'), '➖')
                    label = proto_labels.get(proto, proto)
                    status = st.get('label', 'Нет данных')
                    status_text = html.unescape(status).replace('\xa0', ' ')
                    has_telegram_icon = '<img' in status or 'Telegram' in status_text
                    # Удаляем HTML-теги из статуса: Telegram-сообщение не поддерживает <img>.
                    status_clean = re.sub(r'<[^>]+>', '', status_text).strip()
                    if has_telegram_icon and 'Telegram' not in status_clean:
                        status_clean = f'{status_clean} 📱 Telegram'
                    details = st.get('details', '')
                    text_lines.append(f"{mark} <b>{label}</b>: {status_clean}")
                    if details:
                        text_lines.append(f"<i>{details}</i>")
                bot.send_message(message.chat.id, '\n'.join(text_lines), parse_mode='HTML', reply_markup=service)
                return

            if message.text in ('📦 Пул ключей', '/pool'):
                _set_chat_menu_state(message.chat.id, level=20, bypass=None)
                _clear_pool_inline_keyboard(message.chat.id)
                _clear_pool_page(message.chat.id)
                bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                return

        if message.chat.type == 'private':

            state = _get_chat_menu_state(message.chat.id)
            level = state['level']
            bypass = state['bypass']

            def set_menu_state(new_level=MENU_STATE_UNSET, new_bypass=MENU_STATE_UNSET):
                nonlocal level, bypass
                if new_level is not MENU_STATE_UNSET:
                    level = new_level
                if new_bypass is not MENU_STATE_UNSET:
                    bypass = new_bypass
                _set_chat_menu_state(message.chat.id, level=level, bypass=bypass)

            if message.text == '⚙️ Сервис':
                bot.send_message(message.chat.id, '⚙️ Сервисное меню!', reply_markup=service)
                return

            if message.text == '♻️ Перезагрузить сервисы' or message.text == 'Перезагрузить сервисы':
                bot.send_message(message.chat.id, '🔄 Выполняется перезагрузка сервисов!', reply_markup=service)
                _restart_router_services()
                _send_message_after_service_restart(message.chat.id, '✅ Сервисы перезагружены!', reply_markup=service)
                return

            if message.text == '‼️Перезагрузить роутер' or message.text == 'Перезагрузить роутер':
                os.system("ndmc -c system reboot")
                service_router_reboot = "🔄 Роутер перезагружается!\nЭто займет около 2 минут."
                bot.send_message(message.chat.id, service_router_reboot, reply_markup=service)
                return

            if message.text == '‼️DNS Override' or message.text == 'DNS Override':
                service = types.ReplyKeyboardMarkup(resize_keyboard=True)
                m1 = types.KeyboardButton("✅ DNS Override ВКЛ")
                m2 = types.KeyboardButton("❌ DNS Override ВЫКЛ")
                back = types.KeyboardButton("🔙 Назад")
                service.add(m1, m2)
                service.add(back)
                bot.send_message(message.chat.id, '‼️DNS Override!', reply_markup=service)
                return

            if message.text == "✅ DNS Override ВКЛ" or message.text == "❌ DNS Override ВЫКЛ":
                if message.text == "✅ DNS Override ВКЛ":
                    bot.send_message(
                        message.chat.id,
                        _set_dns_override(True),
                        reply_markup=service,
                    )
                    return

                if message.text == "❌ DNS Override ВЫКЛ":
                    bot.send_message(
                        message.chat.id,
                        _set_dns_override(False),
                        reply_markup=service,
                    )
                    return

            # Кнопка "Обновление" убрана из меню "Сервис" (заменена на "Статус ключей").

            if message.text == '📄 Информация':
                info_bot = _telegram_info_text_from_readme()
                bot.send_message(
                    message.chat.id,
                    info_bot,
                    parse_mode='HTML',
                    disable_web_page_preview=True,
                    reply_markup=main,
                )
                return

            if message.text == '/keys_free':
                url = _raw_github_url('keys.md')
                try:
                    keys_free = _fetch_remote_text(url)
                except requests.RequestException as exc:
                    bot.send_message(message.chat.id, f'⚠️ Не удалось загрузить список ключей: {exc}', reply_markup=main)
                    return
                bot.send_message(message.chat.id, keys_free, parse_mode='Markdown', disable_web_page_preview=True)
                return

            if message.text == '🔄 Обновления' or message.text == '/check_update':
                url = _raw_github_url('version.md')
                try:
                    bot_new_version = _fetch_remote_text(url)
                except requests.RequestException as exc:
                    bot.send_message(message.chat.id, f'⚠️ Не удалось проверить обновления: {exc}', reply_markup=service)
                    return
                bot_version = _current_bot_version()
                service_bot_version = "*ВАША ТЕКУЩАЯ " + str(bot_version) + "*\n\n"
                service_new_version = "*ПОСЛЕДНЯЯ ДОСТУПНАЯ ВЕРСИЯ:*\n\n" + str(bot_new_version)
                service_update_info = service_bot_version + service_new_version
                # bot.send_message(message.chat.id, service_bot_version, parse_mode='Markdown', reply_markup=service)
                bot.send_message(message.chat.id, service_update_info, parse_mode='Markdown', reply_markup=service)

                service_update_msg = "Если вы хотите обновить текущую версию на более новую, нажмите сюда /update"
                bot.send_message(message.chat.id, service_update_msg, parse_mode='Markdown', reply_markup=service)
                return

            if message.text == '/update':
                started, status_message = _start_telegram_background_command(
                    '-update',
                    fork_repo_owner,
                    fork_repo_name,
                    message.chat.id,
                    'service',
                )
                if not started:
                    bot.send_message(message.chat.id, status_message, reply_markup=service)
                    return
                bot.send_message(
                    message.chat.id,
                    f'Запускаю обновление из форка {fork_repo_owner}/{fork_repo_name}. Обычно это занимает 1-3 минуты. '
                    'Во время обновления бот может временно пропасть из сети, потому что сервис будет перезапущен. '
                    'После запуска бот сам пришлет в этот чат лог и итоговое сообщение.',
                    reply_markup=service,
                )
                return

            if message.text == "📥 Сервисы по запросу":
                set_menu_state(10, 'vless')
                bot.send_message(message.chat.id, 'Выберите сервис. По умолчанию список будет добавлен в маршрут Vless 1.', reply_markup=_service_list_markup())
                return

            if message.text == '🔙 Назад' or message.text == "Назад":
                _clear_pool_inline_keyboard(message.chat.id)
                _clear_pool_page(message.chat.id)
                bot.send_message(message.chat.id, '✅ Добро пожаловать в меню!', reply_markup=main)
                set_menu_state(0, None)
                return

            if level == 1:
                # значит это список обхода блокировок
                selected_list = _resolve_unblock_list_selection(message.text)
                dirname = '/opt/etc/unblock/'
                dirfiles = os.listdir(dirname)

                for fln in dirfiles:
                    if fln == selected_list + '.txt':
                        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                        item1 = types.KeyboardButton("📑 Показать список")
                        item2 = types.KeyboardButton("📝 Добавить в список")
                        item3 = types.KeyboardButton("🗑 Удалить из списка")
                        item4 = types.KeyboardButton("📥 Сервисы по запросу")
                        back = types.KeyboardButton("🔙 Назад")
                        markup.row(item1, item2, item3)
                        markup.row(item4)
                        markup.row(back)
                        set_menu_state(2, selected_list)
                        bot.send_message(message.chat.id, "Меню " + _list_label(fln), reply_markup=markup)
                        return

                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                back = types.KeyboardButton("🔙 Назад")
                markup.add(back)
                bot.send_message(message.chat.id, "Не найден", reply_markup=markup)
                return

            if level == 2 and message.text == "📑 Показать список":
                try:
                    sites = sorted(_read_unblock_list_entries(bypass))
                except FileNotFoundError:
                    bot.send_message(message.chat.id, '⚠️ Файл списка не найден. Откройте список заново.', reply_markup=main)
                    set_menu_state(1, None)
                    return
                s = 'Список пуст'
                if sites:
                    s = '\n'.join(sites)
                if len(s) > 4096:
                    for x in range(0, len(s), 4096):
                        bot.send_message(message.chat.id, s[x:x + 4096])
                else:
                    bot.send_message(message.chat.id, s)
                #bot.send_message(message.chat.id, s)
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                item1 = types.KeyboardButton("📑 Показать список")
                item2 = types.KeyboardButton("📝 Добавить в список")
                item3 = types.KeyboardButton("🗑 Удалить из списка")
                item4 = types.KeyboardButton("📥 Сервисы по запросу")
                back = types.KeyboardButton("🔙 Назад")
                markup.row(item1, item2, item3)
                markup.row(item4)
                markup.row(back)
                bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=markup)
                return

            if level == 2 and message.text == "📥 Сервисы по запросу":
                set_menu_state(10)
                bot.send_message(message.chat.id, f'Выберите сервис для маршрута {_list_label(bypass + ".txt")}', reply_markup=_service_list_markup())
                return

            if level == 2 and message.text == "📝 Добавить в список":
                bot.send_message(message.chat.id,
                                 "Введите имя сайта или домена для разблокировки, "
                                 "либо воспользуйтесь меню для других действий")
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                item1 = types.KeyboardButton("Добавить обход блокировок соцсетей")
                back = types.KeyboardButton("🔙 Назад")
                markup.add(item1, back)
                set_menu_state(3)
                bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=markup)
                return

            if level == 2 and message.text == "🗑 Удалить из списка":
                bot.send_message(message.chat.id,
                                 "Введите имя сайта или домена для удаления из листа разблокировки,"
                                 "либо возвратитесь в главное меню")
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                back = types.KeyboardButton("🔙 Назад")
                markup.add(back)
                set_menu_state(4)
                bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=markup)
                return

            if level == 3:
                try:
                    mylist = set(_read_unblock_list_entries(bypass))
                except FileNotFoundError:
                    bot.send_message(message.chat.id, '⚠️ Файл списка не найден. Откройте список заново.', reply_markup=main)
                    set_menu_state(1, None)
                    return
                k = len(mylist)
                if message.text == "Добавить обход блокировок соцсетей":
                    url = "https://raw.githubusercontent.com/tas-unn/bypass_keenetic/main/socialnet.txt"
                    try:
                        s = _fetch_remote_text(url)
                    except requests.RequestException as exc:
                        bot.send_message(message.chat.id, f'⚠️ Не удалось загрузить список соцсетей: {exc}', reply_markup=main)
                        set_menu_state(2)
                        return
                    lst = s.split('\n')
                    for line in lst:
                        if len(line) > 1:
                            mylist.add(line.replace('\n', ''))
                else:
                    if len(message.text) > 1:
                        mas = message.text.split('\n')
                        for site in mas:
                            mylist.add(site)
                sortlist = sorted(mylist)
                _write_unblock_list_entries(bypass, sortlist)
                if k != len(sortlist):
                    bot.send_message(message.chat.id, "✅ Успешно добавлено")
                else:
                    bot.send_message(message.chat.id, "Было добавлено ранее")
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                item1 = types.KeyboardButton("📑 Показать список")
                item2 = types.KeyboardButton("📝 Добавить в список")
                item3 = types.KeyboardButton("🗑 Удалить из списка")
                item4 = types.KeyboardButton("📥 Сервисы по запросу")
                back = types.KeyboardButton("🔙 Назад")
                markup.row(item1, item2, item3)
                markup.row(item4)
                markup.row(back)
                subprocess.run(["/opt/bin/unblock_update.sh"], check=False)
                set_menu_state(2)
                bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=markup)
                return

            if level == 4:
                try:
                    mylist = set(_read_unblock_list_entries(bypass))
                except FileNotFoundError:
                    bot.send_message(message.chat.id, '⚠️ Файл списка не найден. Откройте список заново.', reply_markup=main)
                    set_menu_state(1, None)
                    return
                k = len(mylist)
                mas = message.text.split('\n')
                for site in mas:
                    mylist.discard(site)
                _write_unblock_list_entries(bypass, mylist)
                if k != len(mylist):
                    bot.send_message(message.chat.id, "✅ Успешно удалено")
                else:
                    bot.send_message(message.chat.id, "Не найдено в списке")
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                item1 = types.KeyboardButton("📑 Показать список")
                item2 = types.KeyboardButton("📝 Добавить в список")
                item3 = types.KeyboardButton("🗑 Удалить из списка")
                item4 = types.KeyboardButton("📥 Сервисы по запросу")
                back = types.KeyboardButton("🔙 Назад")
                markup.row(item1, item2, item3)
                markup.row(item4)
                markup.row(back)
                set_menu_state(2)
                subprocess.run(["/opt/bin/unblock_update.sh"], check=False)
                bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=markup)
                return

            if level == 10:
                _handle_getlist_request(message, message.text, route_name=bypass, reply_markup=_service_list_markup())
                return

            if level == 20:
                if message.text == '🔙 В меню ключей':
                    set_menu_state(8, None)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, '🔑 Ключи и мосты', reply_markup=_build_keys_menu_markup())
                    return
                proto = _resolve_pool_protocol(message.text)
                if not proto:
                    bot.send_message(message.chat.id, 'Выберите протокол кнопкой внизу.', reply_markup=_pool_protocol_markup())
                    return
                set_menu_state(21, proto)
                _send_pool_page(message.chat.id, proto, page=0)
                return

            if level == 21:
                proto = _resolve_pool_protocol(bypass)
                if not proto:
                    set_menu_state(20, None)
                    _clear_pool_inline_keyboard(message.chat.id)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                page = _get_pool_page(message.chat.id)
                if message.text == '🔙 В меню ключей':
                    set_menu_state(8, None)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, '🔑 Ключи и мосты', reply_markup=_build_keys_menu_markup())
                    return
                selected_proto = _resolve_pool_protocol(message.text)
                if selected_proto:
                    set_menu_state(21, selected_proto)
                    _send_pool_page(message.chat.id, selected_proto, page=0)
                    return
                if message.text == '🔙 К выбору протокола':
                    set_menu_state(20, None)
                    _clear_pool_inline_keyboard(message.chat.id)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                page_delta = _pool_reply_page_delta(message.text)
                if page_delta:
                    _send_pool_page(message.chat.id, proto, page=page + page_delta)
                    return
                if _is_pool_page_noop(message.text):
                    _send_pool_page(message.chat.id, proto, page=page)
                    return
                action, raw_index, button_proto = _pool_reply_key_action(message.text)
                if action:
                    if action == 'legacy' or not button_proto:
                        bot.send_message(
                            message.chat.id,
                            'Эта кнопка пула устарела и не содержит протокол. Откройте пул заново и нажмите кнопку вида V1/V2/VM/TR/SS.',
                            reply_markup=_pool_action_markup(proto, page),
                        )
                        return
                    if button_proto != proto:
                        proto = button_proto
                        page = 0
                        set_menu_state(21, proto)
                    if action == 'delete':
                        bot.send_message(
                            message.chat.id,
                            'Удаление доступно только через кнопку «🗑 Удаление». Это защищает от случайного нажатия старой кнопки.',
                            reply_markup=_pool_action_markup(proto, page),
                        )
                        return
                    try:
                        index, key_value = _pool_key_by_index(proto, raw_index)
                    except Exception as exc:
                        bot.send_message(message.chat.id, f'Ошибка выбора ключа: {exc}', reply_markup=_pool_action_markup(proto, page))
                        return
                    if action == 'apply':
                        bot.send_message(
                            message.chat.id,
                            f'Применяю ключ #{index} для {_pool_proto_label(proto)}. Это может занять до 30 секунд.',
                            reply_markup=_pool_action_markup(proto, page),
                        )
                        _apply_pool_key_background(message.chat.id, proto, key_value, index, page=page)
                    else:
                        try:
                            _delete_pool_key(proto, key_value)
                            _send_pool_page(message.chat.id, proto, page=page, prefix=f'Ключ #{index} удалён из пула {_pool_proto_label(proto)}.')
                        except Exception as exc:
                            bot.send_message(message.chat.id, f'Ошибка удаления ключа из пула: {exc}', reply_markup=_pool_action_markup(proto, page))
                    return
                if message.text in ('📋 Показать пул', '🔄 Обновить пул'):
                    _send_pool_page(message.chat.id, proto, page=page)
                    return
                if message.text == '🔙 К пулу':
                    _send_pool_page(message.chat.id, proto, page=page)
                    return
                if message.text == '➕ Добавить ключи':
                    set_menu_state(22)
                    bot.send_message(
                        message.chat.id,
                        f'Отправьте один или несколько ключей для пула {_pool_proto_label(proto)}. Каждый ключ с новой строки.',
                        reply_markup=_pool_input_markup(),
                    )
                    return
                if message.text == '🔗 Загрузить subscription':
                    set_menu_state(23)
                    bot.send_message(
                        message.chat.id,
                        f'Отправьте subscription URL для пула {_pool_proto_label(proto)}.',
                        reply_markup=_pool_input_markup(),
                    )
                    return
                if message.text == '✅ Применить ключ':
                    bot.send_message(message.chat.id, 'Используйте нижние кнопки ✅ с номером нужного ключа.', reply_markup=_pool_action_markup(proto, page))
                    return
                if message.text == '🗑 Удалить ключ':
                    bot.send_message(message.chat.id, 'Используйте нижние кнопки ✕ с номером нужного ключа.', reply_markup=_pool_action_markup(proto, page))
                    return
                if message.text == '🗑 Удаление':
                    set_menu_state(25)
                    bot.send_message(
                        message.chat.id,
                        f'Выберите ключ для удаления из пула {_pool_proto_label(proto)}. Активный ключ удалить можно, но режим бота останется прежним до применения другого ключа.',
                        reply_markup=_pool_delete_markup(proto, page),
                    )
                    return
                if message.text == '🧹 Очистить пул':
                    set_menu_state(26)
                    bot.send_message(
                        message.chat.id,
                        f'Очистить весь пул {_pool_proto_label(proto)}? Это удалит все ключи из пула.',
                        reply_markup=_pool_clear_confirm_markup(),
                    )
                    return
                if message.text == '🔍 Проверить пул':
                    _probe_pool_keys_background(proto, _pool_keys_for_proto(proto))
                    _send_pool_page(
                        message.chat.id,
                        proto,
                        page=page,
                        prefix=f'Запущена фоновая проверка пула {_pool_proto_label(proto)}. Статусы обновятся через несколько секунд.',
                    )
                    return
                bot.send_message(message.chat.id, 'Выберите действие кнопкой внизу.', reply_markup=_pool_action_markup(proto, page))
                return

            if level == 22:
                proto = _resolve_pool_protocol(bypass)
                if not proto:
                    set_menu_state(20, None)
                    _clear_pool_inline_keyboard(message.chat.id)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                if message.text == '🔙 К пулу':
                    set_menu_state(21)
                    _send_pool_page(message.chat.id, proto, page=_get_pool_page(message.chat.id))
                    return
                added = _add_keys_to_pool(proto, message.text)
                set_menu_state(21)
                _send_pool_page(
                    message.chat.id,
                    proto,
                    page=_get_pool_page(message.chat.id),
                    prefix=f'Добавлено ключей в пул {_pool_proto_label(proto)}: {added}',
                )
                return

            if level == 23:
                proto = _resolve_pool_protocol(bypass)
                if not proto:
                    set_menu_state(20, None)
                    _clear_pool_inline_keyboard(message.chat.id)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                if message.text == '🔙 К пулу':
                    set_menu_state(21)
                    _send_pool_page(message.chat.id, proto, page=_get_pool_page(message.chat.id))
                    return
                try:
                    fetched, error = _fetch_keys_from_subscription(message.text.strip())
                    if error:
                        raise ValueError(error)
                    source_proto = 'vless' if proto == 'vless2' else proto
                    added = _add_keys_to_pool(proto, '\n'.join(fetched.get(source_proto, []) or []))
                    result = f'Загружено из subscription в пул {_pool_proto_label(proto)}: {added} новых ключей.'
                except Exception as exc:
                    result = f'Ошибка загрузки subscription: {exc}'
                set_menu_state(21)
                _send_pool_page(message.chat.id, proto, page=_get_pool_page(message.chat.id), prefix=result)
                return

            if level == 26:
                proto = _resolve_pool_protocol(bypass)
                if not proto:
                    set_menu_state(20, None)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                page = _get_pool_page(message.chat.id)
                if message.text == '✅ Очистить пул':
                    removed = _clear_pool(proto)
                    set_menu_state(21)
                    _send_pool_page(message.chat.id, proto, page=page, prefix=f'Пул {_pool_proto_label(proto)} очищен. Удалено ключей: {removed}.')
                    return
                if message.text in ('Отмена', '🔙 К пулу'):
                    set_menu_state(21)
                    _send_pool_page(message.chat.id, proto, page=page, prefix='Очистка пула отменена.')
                    return
                bot.send_message(message.chat.id, 'Подтвердите очистку или нажмите отмену.', reply_markup=_pool_clear_confirm_markup())
                return

            if level == 24:
                proto = _resolve_pool_protocol(bypass)
                if not proto:
                    set_menu_state(20, None)
                    _clear_pool_inline_keyboard(message.chat.id)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                try:
                    index, key_value = _pool_key_by_index(proto, message.text)
                    result = _apply_pool_key(proto, key_value)
                    result = f'Ключ #{index} применён для {_pool_proto_label(proto)}.\n{result}'
                except Exception as exc:
                    result = f'Ошибка применения ключа из пула: {exc}'
                set_menu_state(21)
                _send_pool_page(message.chat.id, proto, prefix=result)
                return

            if level == 25:
                proto = _resolve_pool_protocol(bypass)
                if not proto:
                    set_menu_state(20, None)
                    _clear_pool_inline_keyboard(message.chat.id)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                page = _get_pool_page(message.chat.id)
                if message.text in ('🔙 К пулу', '🔙 Назад'):
                    set_menu_state(21)
                    _send_pool_page(message.chat.id, proto, page=page)
                    return
                page_delta = _pool_reply_page_delta(message.text)
                if page_delta:
                    set_menu_state(25)
                    _send_pool_delete_page(
                        message.chat.id,
                        proto,
                        page=page + page_delta,
                        prefix='Режим удаления: выберите ключ кнопкой ниже.',
                    )
                    return
                if _is_pool_page_noop(message.text):
                    _send_pool_delete_page(message.chat.id, proto, page=page)
                    return
                action, raw_index, button_proto = _pool_reply_key_action(message.text)
                if not action:
                    bot.send_message(message.chat.id, 'Выберите ключ для удаления кнопкой с кодом протокола V1/V2/VM/TR/SS.', reply_markup=_pool_delete_markup(proto, page))
                    return
                if action == 'legacy' or not button_proto:
                    bot.send_message(
                        message.chat.id,
                        'Эта кнопка пула устарела и не содержит протокол. Откройте пул заново и нажмите кнопку удаления вида ✕ V1/V2/VM/TR/SS.',
                        reply_markup=_pool_delete_markup(proto, page),
                    )
                    return
                if button_proto != proto:
                    proto = button_proto
                    page = 0
                    set_menu_state(25, proto)
                if action != 'delete':
                    bot.send_message(message.chat.id, 'Сейчас включен режим удаления. Нажмите кнопку ключа с префиксом ✕ или вернитесь к пулу.', reply_markup=_pool_delete_markup(proto, page))
                    return
                try:
                    index, key_value = _pool_key_by_index(proto, raw_index)
                    _delete_pool_key(proto, key_value)
                    result = f'Ключ #{index} удалён из пула {_pool_proto_label(proto)}.'
                except Exception as exc:
                    result = f'Ошибка удаления ключа из пула: {exc}'
                set_menu_state(21)
                _send_pool_page(message.chat.id, proto, page=page, prefix=result)
                return

            if level == 5:
                set_menu_state(0)
                _install_proxy_from_message(message, 'shadowsocks', message.text, main)
                return

            if level == 8:
                # значит это ключи и мосты
                if message.text == 'Где брать ключи❔':
                    url = _raw_github_url('keys.md')
                    try:
                        keys = _fetch_remote_text(url)
                    except requests.RequestException as exc:
                        bot.send_message(message.chat.id, f'⚠️ Не удалось загрузить справку по ключам: {exc}', reply_markup=main)
                        return
                    bot.send_message(message.chat.id, keys, parse_mode='Markdown', disable_web_page_preview=True)
                    set_menu_state(8)

                if message.text == 'Shadowsocks':
                    #bot.send_message(message.chat.id, "Скопируйте ключ сюда")
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    back = types.KeyboardButton("🔙 Назад")
                    markup.add(back)
                    set_menu_state(5)
                    bot.send_message(message.chat.id, "🔑 Скопируйте ключ сюда", reply_markup=markup)
                    return

                if message.text == 'Vmess':
                    #bot.send_message(message.chat.id, "Скопируйте ключ сюда")
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    back = types.KeyboardButton("🔙 Назад")
                    markup.add(back)
                    set_menu_state(9)
                    bot.send_message(message.chat.id, "🔑 Скопируйте ключ сюда", reply_markup=markup)
                    return

                if message.text == 'Vless' or message.text == 'Vless 1':
                    #bot.send_message(message.chat.id, "Скопируйте ключ сюда")
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    back = types.KeyboardButton("🔙 Назад")
                    markup.add(back)
                    set_menu_state(11)
                    bot.send_message(message.chat.id, "🔑 Скопируйте ключ сюда", reply_markup=markup)
                    return

                if message.text == 'Vless 2':
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    back = types.KeyboardButton("🔙 Назад")
                    markup.add(back)
                    set_menu_state(12)
                    bot.send_message(message.chat.id, "🔑 Скопируйте ключ сюда", reply_markup=markup)
                    return

                if message.text == 'Trojan':
                    #bot.send_message(message.chat.id, "Скопируйте ключ сюда")
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    back = types.KeyboardButton("🔙 Назад")
                    markup.add(back)
                    set_menu_state(10)
                    bot.send_message(message.chat.id, "🔑 Скопируйте ключ сюда", reply_markup=markup)
                    return

            if level == 9:
                set_menu_state(0)
                _install_proxy_from_message(message, 'vmess', message.text, main)
                return

            if level == 10:
                set_menu_state(0)
                _install_proxy_from_message(message, 'trojan', message.text, main)
                return

            if level == 11:
                set_menu_state(0)
                _install_proxy_from_message(message, 'vless', message.text, main)
                return

            if level == 12:
                set_menu_state(0)
                _install_proxy_from_message(message, 'vless2', message.text, main)
                return

            if message.text == '🌐 Через браузер':
                bot.send_message(message.chat.id,
                                 f'Откройте в браузере: http://{routerip}:{browser_port}/\n'
                                 'Введите ключ Shadowsocks, Vmess, Vless 1, Vless 2 или Trojan на странице.', reply_markup=main)
                return

            if message.text == '🔰 Установка и удаление':
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                item1 = types.KeyboardButton("♻️ Установка / переустановка (ветка main)")
                item2 = types.KeyboardButton("♻️ Переустановка (ветка independent)")
                item3 = types.KeyboardButton("⚠️ Удаление")
                back = types.KeyboardButton("🔙 Назад")
                markup.row(item1)
                markup.row(item2)
                markup.row(item3)
                markup.row(back)
                bot.send_message(message.chat.id, '🔰 Установка и удаление', reply_markup=markup)
                return

            if message.text in (
                '♻️ Установка / переустановка (ветка main)',
                '♻️ Установка переустановка (ветка main)',
                '♻️ Установка и переустановка',
                '♻️ Установка & переустановка',
            ):
                started, status_message = _start_telegram_background_command(
                    '-update',
                    fork_repo_owner,
                    fork_repo_name,
                    message.chat.id,
                    'main',
                )
                if not started:
                    bot.send_message(message.chat.id, status_message, reply_markup=main)
                    return
                bot.send_message(message.chat.id,
                                 f'Запускаю установку/переустановку из ветки main форка {fork_repo_owner}/{fork_repo_name} без сброса ключей и списков. '
                                 'Обычно это занимает 1-3 минуты. Во время обновления бот может временно пропасть из сети, '
                                 'потому что сервис будет перезапущен. После запуска бот сам пришлет в этот чат лог и итоговое сообщение.',
                                 reply_markup=main)
                return

            if message.text == '♻️ Переустановка (ветка independent)':
                started, status_message = _start_telegram_background_command(
                    '-update',
                    'andruwko73',
                    'bypass_keenetic',
                    message.chat.id,
                    'main',
                    branch='feature/independent-rework',
                )
                if not started:
                    bot.send_message(message.chat.id, status_message, reply_markup=main)
                    return
                bot.send_message(
                    message.chat.id,
                    'Запускаю переустановку из ветки andruwko73/bypass_keenetic (feature/independent-rework) без сброса ключей и списков.\n'
                    'Обычно это занимает 1-3 минуты. Во время обновления бот может временно пропасть из сети.\n'
                    'После запуска бот сам пришлет лог и итоговое сообщение.',
                    reply_markup=main,
                )
                return

            if message.text == '⚠️ Удаление':
                return_code, output = _run_script_action('-remove', fork_repo_owner, fork_repo_name)
                _send_telegram_chunks(message.chat.id, output, reply_markup=service)
                if return_code == 0:
                    bot.send_message(message.chat.id, '✅ Удаление завершено.', reply_markup=service)
                else:
                    bot.send_message(message.chat.id, '⚠️ Удаление завершилось с ошибкой. Полный лог отправлен выше.', reply_markup=service)
                return

            if message.text == "📝 Списки обхода":
                set_menu_state(1, None)
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                options = _telegram_unblock_list_options()
                buttons = [types.KeyboardButton(label) for label, _ in options]
                for index in range(0, len(buttons), 2):
                    markup.row(*buttons[index:index + 2])
                markup.add(types.KeyboardButton("📥 Сервисы по запросу"))
                back = types.KeyboardButton("🔙 Назад")
                markup.add(back)
                bot.send_message(message.chat.id, "📝 Списки обхода", reply_markup=markup)
                return

            if message.text == "🔑 Ключи и мосты":
                set_menu_state(8, None)
                bot.send_message(message.chat.id, "🔑 Ключи и мосты", reply_markup=_build_keys_menu_markup())
                return

    except Exception as error:
        _write_runtime_log(traceback.format_exc(), mode='w')
        try:
            os.chmod(r"/opt/etc/error.log", 0o0755)
        except Exception:
            pass
        try:
            if getattr(getattr(message, 'chat', None), 'type', None) == 'private':
                _set_chat_menu_state(message.chat.id, level=0, bypass=None)
                bot.send_message(
                    message.chat.id,
                    f'⚠️ Команда не выполнена из-за внутренней ошибки: {error}',
                    reply_markup=_build_main_menu_markup(),
                )
        except Exception:
            pass

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

    def _build_form(self, message=''):
        command_state = _consume_web_command_state_for_render()
        current_keys = _load_current_keys()
        snapshot = _cached_status_snapshot(current_keys)
        status = snapshot['web'] if snapshot is not None else _placeholder_web_status_snapshot()
        protocol_statuses = snapshot['protocols'] if snapshot is not None else _placeholder_protocol_statuses(current_keys)
        _refresh_status_caches_async(current_keys)
        _probe_all_pool_keys_async()
        unblock_lists = _load_unblock_lists()
        status_refresh_pending = (
            'Фоновая проверка связи выполняется' in status.get('api_status', '') or
            any(item.get('label') == 'Проверяется' for item in protocol_statuses.values())
        )

        message_block = ''
        if message:
            safe_message = html.escape(message)
            message_block = f'''<div class="notice notice-result">
  <strong>Результат</strong>
  <pre class="log-output">{safe_message}</pre>
</div>'''

        command_block = ''
        if command_state['label']:
            command_title = 'Команда выполняется' if command_state['running'] else 'Последняя команда'
            command_text = command_state['result'] or f'⏳ {command_state["label"]} ещё выполняется. Обновление страницы происходит автоматически.'
            command_block = f'''<div class="notice notice-status">
  <strong>{html.escape(command_title)}: {html.escape(command_state['label'])}</strong>
  <pre class="log-output">{html.escape(command_text)}</pre>
</div>'''

        socks_block = ''
        if status['socks_details']:
            socks_block = f'<p class="status-note">{html.escape(status["socks_details"])}' + '</p>'
        fallback_block = ''
        if status.get('fallback_reason') and status['proxy_mode'] == 'none':
            fallback_block = f'<p class="status-note">Последняя неудачная попытка прокси: {html.escape(status["fallback_reason"])}</p>'

        current_mode_label = {
            'none': 'Без прокси',
            'shadowsocks': 'Shadowsocks',
            'vmess': 'Vmess',
            'vless': 'Vless 1',
            'vless2': 'Vless 2',
            'trojan': 'Trojan',
        }.get(status['proxy_mode'], status['proxy_mode'])
        list_route_label = _transparent_list_route_label()

        status_block = f'''<div class="notice notice-status hero-status hero-status-compact">
    <div class="hero-status-header">
        <strong>Связь с Telegram API</strong>
        <div class="traffic-inline">
            <span class="traffic-chip"><span class="traffic-chip-label">Бот</span><span class="traffic-chip-value">{html.escape(current_mode_label)}</span></span>
            <span class="traffic-chip"><span class="traffic-chip-label">Списки</span><span class="traffic-chip-value">{html.escape(list_route_label)}</span></span>
        </div>
    </div>
    <p>{html.escape(status['api_status'])}</p>
    {socks_block}
    {fallback_block}
</div>'''

        mode_picker_block = f'''<div id="mode-picker" class="hero-popover mode-picker hidden">
    <form method="post" action="/set_proxy" class="mode-picker-form">
        <label class="mode-picker-label" for="hero-proxy-type">Активный протокол</label>
        <select id="hero-proxy-type" name="proxy_type">
            <option value="none"{' selected' if proxy_mode == 'none' else ''}>Без прокси (по умолчанию)</option>
            <option value="shadowsocks"{' selected' if proxy_mode == 'shadowsocks' else ''}>Shadowsocks</option>
            <option value="vmess"{' selected' if proxy_mode == 'vmess' else ''}>Vmess</option>
            <option value="vless"{' selected' if proxy_mode == 'vless' else ''}>Vless 1</option>
            <option value="vless2"{' selected' if proxy_mode == 'vless2' else ''}>Vless 2</option>
            <option value="trojan"{' selected' if proxy_mode == 'trojan' else ''}>Trojan</option>
        </select>
        <button type="submit">Применить режим</button>
    </form>
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
        protocol_cards = []
        for key_name, title, rows, placeholder in protocol_sections:
            safe_value = html.escape(current_keys.get(key_name, ''))
            safe_title = html.escape(title)
            status_info = protocol_statuses.get(key_name, {'tone': 'empty', 'label': 'Не сохранён', 'details': 'Ключ ещё не сохранён на роутере.'})
            api_ok = status_info.get('api_ok', False)
            current_probe = key_probe_cache.get(_hash_key(current_keys.get(key_name, '')), {})
            current_tg_ok = api_ok or bool(current_probe.get('tg_ok'))
            current_yt_ok = bool(status_info.get('yt_ok', current_probe.get('yt_ok', False)))
            active_status_icons = ''.join([
                _telegram_icon_html(opacity=1.0) if current_tg_ok else '',
                _youtube_icon_html(opacity=1.0) if current_yt_ok else '',
            ])
            # Пул ключей для этого протокола
            pool_keys = key_pools.get(key_name, [])
            pool_items_html = ''
            if pool_keys:
                for i, pk in enumerate(pool_keys):
                    safe_pk = html.escape(pk)
                    display_name = html.escape(_pool_key_display_name(pk))
                    is_active = 'активен' if i == 0 else ''
                    probe = key_probe_cache.get(_hash_key(pk), {})
                    tg_badge = _telegram_icon_html(opacity=1.0) if probe.get('tg_ok') else ''
                    yt_badge = _youtube_icon_html(opacity=1.0) if probe.get('yt_ok') else ''
                    pool_items_html += f'''<li class="pool-item">
                        <form method="post" action="/pool_apply" class="pool-apply-form">
                            <input type="hidden" name="type" value="{key_name}">
                            <input type="hidden" name="key" value="{safe_pk}">
                            <button type="submit" class="pool-apply-btn" title="Применить этот ключ">{display_name}</button>
                        </form>
                        <span class="pool-key-icons">{tg_badge}{yt_badge}</span>
                        <span class="pool-key-meta">{is_active}</span>
                        <form method="post" action="/pool_delete" class="pool-item-form">
                            <input type="hidden" name="type" value="{key_name}">
                            <input type="hidden" name="key" value="{safe_pk}">
                            <button type="submit" class="pool-delete-btn" title="Удалить ключ из пула">✕</button>
                        </form>
                    </li>'''
            if not pool_items_html:
                pool_items_html = '<li class="pool-item pool-empty">Пул пуст. Добавьте ключи ниже.</li>'
            protocol_cards.append(f'''<section class="panel protocol-card">
        <div class="card-topline">
            <span class="eyebrow">Ключ подключения</span>
            <span class="key-status-wrap"><span class="key-status-icons">{active_status_icons}</span><span class="key-status-badge key-status-{status_info['tone']}">{status_info['label']}</span></span>
        </div>
        <h2>{safe_title}</h2>
        <p class="key-status-note">{html.escape(status_info['details'])}</p>
    <form method="post" action="/install">
      <input type="hidden" name="type" value="{key_name}">
      <textarea name="key" rows="{rows}" placeholder="{html.escape(placeholder)}" required>{safe_value}</textarea>
      <button type="submit">Сохранить {safe_title}</button>
    </form>
    <details class="pool-details">
        <summary class="pool-summary">📦 Пул ключей ({len(pool_keys)})</summary>
        <ul class="pool-list">{pool_items_html}</ul>
        <form method="post" action="/pool_add" class="pool-add-form">
            <input type="hidden" name="type" value="{key_name}">
            <textarea name="keys" rows="3" placeholder="Вставьте ключи, каждый с новой строки"></textarea>
            <div class="pool-add-actions">
                <button type="submit" class="secondary-button">➕ Добавить в пул</button>
            </div>
        </form>
        <div class="pool-subscribe-row">
            <form method="post" action="/pool_subscribe" class="pool-subscribe-form">
                <input type="hidden" name="type" value="{key_name}">
                <input type="url" name="url" placeholder="https://sub.example.com/... (subscription-ссылка)" style="font-size:13px;padding:10px 12px;">
                <button type="submit" class="secondary-button">📥 Загрузить из subscription</button>
            </form>
            <form method="post" action="/pool_clear" class="pool-clear-form" onsubmit="return confirm('Очистить весь пул ключей для {safe_title}?');">
                <input type="hidden" name="type" value="{key_name}">
                <button type="submit" class="danger pool-clear-btn">Очистить пул</button>
            </form>
        </div>
    </details>
  </section>''')
        protocol_cards_html = ''.join(protocol_cards)

        dns_override_active = _dns_override_enabled()
        update_buttons_html = f'''<form method="post" action="/command">
                <input type="hidden" name="command" value="update">
                <button type="submit">Переустановить из форка без сброса</button>
            </form>
            <form method="post" action="/command">
                <input type="hidden" name="command" value="update_independent">
                <button type="submit">Переустановка (ветка independent)</button>
            </form>
            <form method="post" action="/command">
                <input type="hidden" name="command" value="update_no_bot">
                <button type="submit">Переустановка (без Telegram бота)</button>
            </form>'''
        command_buttons = [
            ('restart_services', 'Перезапустить сервисы', ''),
            ('dns_on', 'DNS Override ВКЛ', 'success-button' if dns_override_active else ''),
            ('dns_off', 'DNS Override ВЫКЛ', 'danger'),
            ('remove', 'Удалить компоненты', 'danger'),
            ('reboot', 'Перезагрузить роутер', 'danger'),
        ]
        command_buttons_html = ''.join(
            f'''<form method="post" action="/command">
            <input type="hidden" name="command" value="{command}">
            <button type="submit" class="{button_class}">{html.escape(label)}</button>
        </form>'''
            for command, label, button_class in command_buttons
        )

        unblock_cards = []
        for entry in unblock_lists:
            safe_name = html.escape(entry['name'])
            safe_label = html.escape(entry['label'])
            safe_content = html.escape(entry['content'])
            unblock_cards.append(f'''<section class="panel unblock-card">
        <div class="card-topline">
            <span class="eyebrow">Список обхода</span>
            <span class="file-chip">{safe_name}</span>
        </div>
    <h2>{safe_label}</h2>
    <form method="post" action="/save_unblock_list">
      <input type="hidden" name="list_name" value="{safe_name}">
      <textarea name="content" rows="8" placeholder="example.org&#10;api.telegram.org">{safe_content}</textarea>
      <button type="submit">Сохранить список</button>
    </form>
  </section>''')
        unblock_lists_block = ''.join(unblock_cards)

        auto_refresh_script = ''
        if status_refresh_pending or command_state['running']:
            auto_refresh_script = '''
    <script>
        setTimeout(function() {
            if (!document.hidden) {
                window.location.reload();
            }
        }, 4000);
    </script>'''

        start_button_label = 'Повторить запуск бота' if bot_ready else 'Запустить бота'

        return f'''<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    {'<meta http-equiv="refresh" content="4">' if command_state['running'] else ''}
  <title>Установка ключей прокси</title>
    <style>
        :root{{
            --bg:#12161d;
            --bg-accent:#1a2330;
            --surface:#171e28;
            --surface-soft:#202a38;
            --surface-strong:#263243;
            --border:#334155;
            --text:#edf3ff;
            --muted:#9fb0c8;
            --primary:#4f8cff;
            --primary-hover:#6aa0ff;
            --secondary:#d78644;
            --danger:#c95a47;
            --success-bg:#163326;
            --success-border:#2d7650;
            --warn-bg:#3e2e16;
            --warn-border:#b78332;
            --shadow:0 18px 40px rgba(2, 6, 23, 0.34);
        }}
        [data-theme="light"]{{
            --bg:#f3efe6;
            --bg-accent:#e7dcc7;
            --surface:#fffdf8;
            --surface-soft:#f5ede0;
            --surface-strong:#efe2cb;
            --border:#d7c5aa;
            --text:#1f2933;
            --muted:#6f7a86;
            --primary:#1f7a6a;
            --primary-hover:#165f53;
            --secondary:#c96f32;
            --danger:#a8442f;
            --success-bg:#e5f4ea;
            --success-border:#8cb79a;
            --warn-bg:#fff0d9;
            --warn-border:#d6a35b;
            --shadow:0 18px 40px rgba(76, 58, 36, 0.12);
        }}
        *{{box-sizing:border-box;}}
        body{{
            margin:0;
                        font-family:Segoe UI,Helvetica,Arial,sans-serif;
            color:var(--text);
                        background:
                radial-gradient(circle at top left, rgba(215,134,68,.16), transparent 34%),
                radial-gradient(circle at top right, rgba(79,140,255,.16), transparent 28%),
                linear-gradient(180deg, #0f141c 0%, var(--bg) 100%);
                        padding:20px;
        }}
        [data-theme="light"] body{{
            background:
                radial-gradient(circle at top left, rgba(201,111,50,.18), transparent 34%),
                radial-gradient(circle at top right, rgba(31,122,106,.16), transparent 28%),
                linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
        }}
                .shell{{max-width:1180px;margin:0 auto;}}
        .hero{{margin-bottom:16px;padding:22px 24px;border:1px solid var(--border);border-radius:24px;background:linear-gradient(140deg, rgba(23,30,40,.98), rgba(32,42,56,.9));box-shadow:var(--shadow);}}
        [data-theme="light"] .hero{{background:linear-gradient(140deg, rgba(255,253,248,.98), rgba(239,226,203,.88));}}
                .hero-copy{{max-width:700px;}}
                .hero-row{{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;}}
                .hero-actions{{display:flex;align-items:flex-start;gap:10px;flex-wrap:wrap;position:relative;justify-content:flex-end;}}
        .hero-meta{{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 0;}}
        .hero-chip{{display:inline-flex;align-items:center;padding:8px 12px;border-radius:999px;background:rgba(79,140,255,.08);border:1px solid rgba(96,165,250,.18);font-size:13px;font-weight:700;color:var(--text);}}
        .theme-toggle{{display:inline-flex;align-items:center;gap:8px;padding:10px 14px;border-radius:999px;border:1px solid var(--border);background:rgba(255,255,255,.03);color:var(--text);font-size:13px;font-weight:700;cursor:pointer;box-shadow:none;white-space:nowrap;}}
                .mode-toggle{{display:inline-flex;align-items:center;gap:8px;padding:10px 14px;border-radius:999px;border:1px solid var(--border);background:rgba(255,255,255,.03);color:var(--text);font-size:13px;font-weight:700;cursor:pointer;box-shadow:none;white-space:nowrap;}}
        .theme-toggle:hover{{filter:none;transform:none;background:rgba(255,255,255,.06);}}
                .mode-toggle:hover{{filter:none;transform:none;background:rgba(255,255,255,.06);}}
                .hero-popover{{position:absolute;top:54px;right:0;min-width:260px;padding:14px;border:1px solid var(--border);border-radius:18px;background:linear-gradient(180deg, rgba(23,30,40,.98), rgba(32,42,56,.96));box-shadow:var(--shadow);z-index:10;}}
                [data-theme="light"] .hero-popover{{background:linear-gradient(180deg, rgba(255,253,248,.98), rgba(245,237,224,.96));}}
                .hidden{{display:none;}}
                .mode-picker-form{{display:grid;gap:10px;}}
                .mode-picker-label{{font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);}}
        h1{{margin:0 0 8px;font-size:clamp(30px,5vw,48px);line-height:1.02;letter-spacing:-0.04em;color:var(--text);}}
        h2{{margin:0 0 14px;font-size:20px;color:var(--text);}}
            p{{margin:0 0 8px;line-height:1.5;color:var(--muted);}}
        .hero strong{{color:var(--text);}}
                .layout{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:16px;}}
        .panel{{min-width:0;padding:18px;border:1px solid var(--border);border-radius:22px;background:linear-gradient(180deg, rgba(23,30,40,.96), rgba(32,42,56,.94));box-shadow:var(--shadow);}}
        [data-theme="light"] .panel{{background:linear-gradient(180deg, rgba(255,253,248,.96), rgba(245,237,224,.94));}}
        form{{display:grid;gap:12px;}}
                input,textarea,select{{width:100%;padding:13px 14px;border-radius:14px;border:1px solid var(--border);background:var(--surface-soft);color:var(--text);font-size:16px;outline:none;}}
                input:focus,textarea:focus,select:focus{{border-color:rgba(31,122,106,.6);box-shadow:0 0 0 4px rgba(31,122,106,.08);}}
        textarea{{min-height:138px;resize:vertical;}}
                input::placeholder,textarea::placeholder{{color:#8b8f92;}}
                button{{padding:13px 16px;border:none;border-radius:14px;background:linear-gradient(135deg, var(--primary), #246f61);color:#fff;font-size:15px;font-weight:700;cursor:pointer;transition:transform .15s ease, filter .15s ease, box-shadow .15s ease;box-shadow:0 10px 20px rgba(31,122,106,.18);}}
        button:hover{{filter:brightness(1.08);transform:translateY(-1px);}}
                button.danger{{background:linear-gradient(135deg, var(--danger), #85311f);box-shadow:0 10px 20px rgba(168,68,47,.18);}}
                .success-button{{background:linear-gradient(135deg, #0f5c2d, #0b4120);box-shadow:0 10px 20px rgba(15,92,45,.28);}}
                .secondary-button{{background:linear-gradient(135deg, var(--secondary), #b85b27);box-shadow:0 10px 20px rgba(201,111,50,.18);}}
        .status-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:14px;}}
                .status-card{{padding:14px;border-radius:18px;background:rgba(79,140,255,.08);border:1px solid rgba(96,165,250,.18);}}
                .status-label{{display:block;margin-bottom:8px;font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:#90a5c4;}}
                .status-value{{font-size:16px;color:var(--text);}}
                .notice{{padding:12px 14px;border-radius:16px;margin-bottom:14px;}}
                .notice strong{{display:block;margin-bottom:8px;color:var(--text);}}
        .notice-result{{background:var(--warn-bg);border:1px solid var(--warn-border);}}
        .notice-status{{background:var(--success-bg);border:1px solid var(--success-border);}}
            .hero-status{{margin-top:12px;margin-bottom:0;}}
            .hero-status-compact p:last-child{{margin-bottom:0;}}
            .hero-status-header{{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:6px;}}
            .traffic-inline{{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;}}
            .traffic-chip{{display:inline-flex;align-items:center;gap:8px;padding:6px 10px;border-radius:999px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);}}
            .traffic-chip-label{{font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);}}
            .traffic-chip-value{{font-size:13px;font-weight:700;color:var(--text);}}
                .status-note{{margin-top:6px;color:var(--text);font-size:14px;line-height:1.4;}}
                .command-progress-block{{margin:14px 0 10px;padding:12px 14px;border:1px solid var(--border);border-radius:14px;background:rgba(255,255,255,.03);}}
                .command-progress-header{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px;color:var(--text);font-size:13px;font-weight:700;}}
                .command-progress-track{{width:100%;height:10px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden;}}
                .command-progress-fill{{height:100%;border-radius:999px;background:linear-gradient(90deg, var(--secondary), var(--primary));transition:width .35s ease;}}
                .log-output{{margin:0;white-space:pre-wrap;word-break:break-word;font:13px/1.45 Consolas,Monaco,monospace;color:var(--text);}}
                .eyebrow{{display:inline-block;margin-bottom:10px;font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#8b6f4a;}}
                .section-title{{margin:0 0 6px;font-size:24px;color:var(--text);}}
                .section-subtitle{{margin:0;color:var(--muted);}}
                .start-card{{display:flex;flex-direction:column;justify-content:space-between;}}
                .command-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px;}}
                .card-topline{{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:8px;}}
                .file-chip{{display:inline-flex;align-items:center;padding:6px 10px;border-radius:999px;background:rgba(201,111,50,.12);border:1px solid rgba(201,111,50,.2);font-size:12px;font-weight:700;color:#7c4b21;}}
                .key-status-wrap{{display:inline-flex;align-items:center;justify-content:flex-end;gap:8px;max-width:62%;}}
                .key-status-icons{{display:inline-flex;gap:6px;align-items:center;flex:none;}}
                .key-status-badge{{display:inline-flex;align-items:center;max-width:100%;padding:6px 10px;border-radius:999px;border:1px solid transparent;font-size:12px;font-weight:700;white-space:normal;line-height:1.25;text-align:right;}}
                .key-status-ok{{background:rgba(31,122,106,.14);border-color:rgba(31,122,106,.3);color:#9be4d3;}}
                .key-status-fail{{background:rgba(168,68,47,.14);border-color:rgba(168,68,47,.28);color:#ffbeb2;}}
                .key-status-warn{{background:rgba(201,111,50,.14);border-color:rgba(201,111,50,.28);color:#f6c892;}}
                .key-status-empty{{background:rgba(159,176,200,.1);border-color:rgba(159,176,200,.18);color:var(--muted);}}
                .key-status-note{{margin:-4px 0 4px;color:var(--muted);font-size:14px;line-height:1.45;overflow-wrap:anywhere;}}
        .protocol-card{{min-width:0;}}
        .pool-details{{margin-top:12px;border-top:1px solid var(--border);padding-top:12px;cursor:pointer;}}
        .pool-summary{{font-size:13px;font-weight:700;color:var(--text);padding:4px 0;}}
        .pool-list{{list-style:none;padding:0;margin:8px 0;display:grid;gap:6px;}}
        .pool-item{{display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:10px;background:rgba(255,255,255,.03);border:1px solid var(--border);font-size:12px;}}
        .pool-apply-form{{flex:1;min-width:0;margin:0;display:block;}}
        .pool-apply-btn{{width:100%;min-width:0;padding:4px 0;border:none;background:transparent;box-shadow:none;color:var(--text);font-size:12px;font-weight:700;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
        .pool-apply-btn:hover{{background:transparent;filter:none;transform:none;color:var(--primary-hover);}}
        .pool-key-icons{{display:inline-flex;gap:6px;align-items:center;}}
        .pool-key-meta{{color:var(--muted);font-size:11px;white-space:nowrap;}}
        .pool-item-form{{margin:0;padding:0;display:inline;}}
        .pool-delete-btn{{padding:2px 8px;border:none;border-radius:6px;background:rgba(168,68,47,.2);color:#ffbeb2;font-size:13px;cursor:pointer;line-height:1.4;box-shadow:none;min-width:0;}}
        .pool-delete-btn:hover{{background:rgba(168,68,47,.4);filter:none;transform:none;}}
        .pool-empty{{color:var(--muted);justify-content:center;}}
        .pool-add-form{{margin-top:8px;display:grid;gap:8px;}}
        .pool-add-actions{{display:flex;gap:8px;}}
        .pool-add-actions button{{padding:8px 14px;font-size:13px;}}
        .pool-subscribe-row{{margin-top:8px;display:flex;align-items:stretch;gap:8px;}}
        .pool-subscribe-form{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;flex:1;}}
        .pool-subscribe-form button,.pool-clear-btn{{padding:8px 14px;font-size:13px;line-height:1.2;min-height:40px;white-space:nowrap;}}
        .pool-clear-form{{margin:0;display:flex;}}
        .pool-clear-btn{{height:100%;}}
        .secondary-button{{background:linear-gradient(135deg, var(--secondary), #b85b27);box-shadow:0 10px 20px rgba(201,111,50,.18);}}
        .wide{{grid-column:1 / -1;}}
        @media (max-width: 760px){{
            body{{padding:12px;}}
                        .hero{{padding:16px;border-radius:20px;}}
            .hero-row{{flex-direction:column;align-items:stretch;}}
            .hero-actions{{width:100%;justify-content:stretch;}}
            .hero-status-header{{flex-direction:column;align-items:flex-start;}}
            .traffic-inline{{justify-content:flex-start;}}
            .theme-toggle,.mode-toggle{{justify-content:center;}}
            .hero-popover{{position:static;min-width:0;width:100%;}}
            .layout{{grid-template-columns:1fr;gap:12px;}}
                        .command-grid{{grid-template-columns:1fr;}}
            .status-grid{{grid-template-columns:1fr;}}
                        .panel{{padding:16px;border-radius:18px;}}
            .pool-subscribe-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:stretch;}}
            .pool-subscribe-form{{display:contents;}}
            .pool-subscribe-form input{{grid-column:1 / -1;}}
            button,input,textarea,select{{font-size:16px;}}
        }}
    </style>
    <script>
        (function() {{
            const savedTheme = localStorage.getItem('router-theme');
            const theme = savedTheme === 'light' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', theme);
        }})();

        function toggleTheme() {{
            const root = document.documentElement;
            const nextTheme = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
            root.setAttribute('data-theme', nextTheme);
            localStorage.setItem('router-theme', nextTheme);
            const label = document.getElementById('theme-toggle-label');
            if (label) {{
                label.textContent = nextTheme === 'light' ? 'Светлая тема' : 'Темная тема';
            }}
        }}

        function toggleModePicker() {{
            const picker = document.getElementById('mode-picker');
            if (!picker) {{
                return;
            }}
            picker.classList.toggle('hidden');
        }}

        document.addEventListener('DOMContentLoaded', function() {{
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
            const label = document.getElementById('theme-toggle-label');
            if (label) {{
                label.textContent = currentTheme === 'light' ? 'Светлая тема' : 'Темная тема';
            }}
            document.addEventListener('click', function(event) {{
                const picker = document.getElementById('mode-picker');
                const toggle = document.getElementById('mode-toggle-button');
                if (!picker || !toggle) {{
                    return;
                }}
                if (picker.classList.contains('hidden')) {{
                    return;
                }}
                if (!picker.contains(event.target) && !toggle.contains(event.target)) {{
                    picker.classList.add('hidden');
                }}
            }});
        }});
    </script>
{auto_refresh_script}
</head>
<body>
    <div class="shell">
    <div class="hero">
        <div class="hero-row">
                <div class="hero-copy">
                        <h1>Установка ключей прокси</h1>
                        <p>Страница показывает не только состояние процесса, но и реальный статус связи с Telegram API.</p>
                        <p><strong>Вставляйте ключ полной строкой, как в Telegram.</strong></p>
                </div>
        <div class="hero-actions">
            <button type="button" id="mode-toggle-button" class="mode-toggle" onclick="toggleModePicker()">
                <span>Режим</span>
                <span>{html.escape(current_mode_label)}</span>
            </button>
            <button type="button" class="theme-toggle" onclick="toggleTheme()">
                <span>Тема</span>
                <span id="theme-toggle-label">Темная тема</span>
            </button>
            {mode_picker_block}
        </div>
        </div>
                {status_block}
    </div>
    {message_block}
    {command_block}
        <section class="panel start-card">
            <div>
                <span class="eyebrow">Запуск</span>
                <h2 class="section-title">Быстрый старт</h2>
                    <p class="section-subtitle">После установки ключей можно сразу запустить бота.</p>
            </div>
            <form method="post" action="/start">
                <button type="submit">{start_button_label}</button>
            </form>
        </section>
        <div class="layout">
        <section class="panel wide">
            <span class="eyebrow">Ключи и мосты</span>
            <h2 class="section-title">Подключения по протоколам</h2>
            <p class="section-subtitle">Храните рабочий ключ в нужной карточке. Текущий режим выбирается отдельно выше.</p>
        </section>
        {protocol_cards_html}
        <section class="panel wide">
                <span class="eyebrow">Сервис роутера</span>
                <h2 class="section-title">Команды установки и обслуживания</h2>
            <p class="section-subtitle">Переустановка из форка обновляет код и служебные файлы поверх текущей установки, не затирая сохранённые ключи и списки обхода. Обычные действия и потенциально опасные команды разделены по цвету, чтобы ими было труднее ошибиться.</p>
                <div class="command-grid">
                        {update_buttons_html}
                        {command_buttons_html}
                </div>
        </section>
        <section class="panel wide">
                <span class="eyebrow">Маршрутизация</span>
                <h2 class="section-title">Списки обхода по протоколам</h2>
                <p class="section-subtitle">Здесь редактируются адреса и домены, которые будут отправляться через соответствующий протокол. Эти правила применяются и к клиентам, подключённым к роутеру извне по VPN.</p>
    </section>
    {unblock_lists_block}
    </div>
    </div>
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
                    snapshot = {
                        'web': _placeholder_web_status_snapshot(),
                        'protocols': _placeholder_protocol_statuses(current_keys),
                    }
                    _refresh_status_caches_async(current_keys)
                payload = {
                    'web': snapshot.get('web', {}) if isinstance(snapshot, dict) else {},
                    'protocols': snapshot.get('protocols', {}) if isinstance(snapshot, dict) else {},
                    'timestamp': time.time(),
                }
                self._send_json(payload, status=200)
            except Exception as exc:
                self._send_json({'error': str(exc)}, status=500)
        elif path == '/api/pool_probe':
            # Запустить фоновую проверку всех ключей в пулах
            try:
                pools = _load_key_pools()
                count = 0
                for proto, keys in pools.items():
                    proxy_url = proxy_settings.get(proto)
                    for k in keys:
                        try:
                            tg_ok, _ = _check_telegram_api_through_proxy(proxy_url, connect_timeout=3, read_timeout=4)
                            yt_ok, _ = _check_http_through_proxy(proxy_url, connect_timeout=2, read_timeout=3)
                            _record_key_probe(proto, k, tg_ok=tg_ok, yt_ok=yt_ok)
                            count += 1
                        except Exception:
                            pass
                self._send_json({'status': 'ok', 'probed': count}, status=200)
            except Exception as exc:
                self._send_json({'error': str(exc)}, status=500)
        elif path == '/static/telegram.png':
            self._send_png(os.path.join(STATIC_DIR, 'telegram.png'))
        elif path == '/static/youtube.png':
            self._send_png(os.path.join(STATIC_DIR, 'youtube.png'))
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
                result = f'Режим бота установлен: {proxy_type}'
            else:
                result = f'⚠️ {error}'
            _invalidate_web_status_cache()
            _invalidate_key_status_cache()
            _set_web_flash_message(result)
            self._send_redirect('/')
            return

        if path == '/start':
            global bot_ready
            bot_ready = True
            _save_bot_autostart(True)
            _invalidate_web_status_cache()
            result = 'Команда запуска принята. Если Telegram API доступен, бот начнет отвечать через несколько секунд.'
            _set_web_flash_message(result)
            self._send_redirect('/')
            return

        if path == '/command':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            command = data.get('command', [''])[0]
            _, result = _start_web_command(command)
            _set_web_flash_message(result)
            self._send_redirect('/')
            return

        if path == '/save_unblock_list':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            list_name = data.get('list_name', [''])[0]
            content = data.get('content', [''])[0]
            try:
                result = _save_unblock_list(list_name, content)
            except Exception as exc:
                result = f'Ошибка сохранения списка: {exc}'
            _set_web_flash_message(result)
            self._send_redirect('/')
            return

        if path == '/append_socialnet':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            list_name = data.get('list_name', [''])[0]
            try:
                result = _append_socialnet_list(list_name)
            except Exception as exc:
                result = f'Ошибка добавления соцсетей: {exc}'
            _set_web_flash_message(result)
            self._send_redirect('/')
            return

        if path == '/pool_add':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            keys_text = data.get('keys', [''])[0]
            try:
                pools = _load_key_pools()
                if proto not in pools:
                    pools[proto] = []
                new_keys = [k.strip() for k in keys_text.split('\n') if k.strip()]
                added = 0
                added_keys = []
                for k in new_keys:
                    if k not in pools[proto]:
                        pools[proto].append(k)
                        added += 1
                        added_keys.append(k)
                _save_key_pools(pools)
                result = f'Добавлено ключей в пул {proto}: {added}'
                _invalidate_web_status_cache()
                _invalidate_key_status_cache()
                # Запускаем фоновую проверку для добавленных ключей
                if added_keys:
                    def _probe_added_keys(proto, keys):
                        proxy_url = proxy_settings.get(proto)
                        for k in keys:
                            try:
                                tg_ok, _ = _check_telegram_api_through_proxy(proxy_url, connect_timeout=3, read_timeout=4)
                                yt_ok, _ = _check_http_through_proxy(proxy_url, connect_timeout=2, read_timeout=3)
                                _record_key_probe(proto, k, tg_ok=tg_ok, yt_ok=yt_ok)
                            except Exception:
                                pass
                    threading.Thread(target=_probe_added_keys, args=(proto, added_keys), daemon=True).start()
            except Exception as exc:
                result = f'Ошибка добавления в пул: {exc}'
            _set_web_flash_message(result)
            self._send_redirect('/')
            return

        if path == '/pool_delete':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            key_to_delete = data.get('key', [''])[0]
            try:
                pools = _load_key_pools()
                if proto in pools and key_to_delete in pools[proto]:
                    pools[proto].remove(key_to_delete)
                    _save_key_pools(pools)
                    result = f'Ключ удалён из пула {proto}'
                    _invalidate_web_status_cache()
                    _invalidate_key_status_cache()
                else:
                    result = 'Ключ не найден в пуле'
            except Exception as exc:
                result = f'Ошибка удаления из пула: {exc}'
            _set_web_flash_message(result)
            self._send_redirect('/')
            return

        if path == '/pool_apply':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            key_to_apply = data.get('key', [''])[0]
            try:
                pools = _load_key_pools()
                if proto not in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    raise ValueError('Неизвестный протокол')
                if key_to_apply not in (pools.get(proto, []) or []):
                    raise ValueError('Ключ не найден в пуле')
                result = _install_key_for_protocol(proto, key_to_apply)
                _set_active_key(proto, key_to_apply)
                _invalidate_web_status_cache()
                _invalidate_key_status_cache()
            except Exception as exc:
                result = f'Ошибка применения ключа из пула: {exc}'
            _set_web_flash_message(result)
            self._send_redirect('/')
            return

        if path == '/pool_clear':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            try:
                if proto not in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    raise ValueError('Неизвестный протокол')
                pools = _load_key_pools()
                removed_keys = list(pools.get(proto, []) or [])
                pools[proto] = []
                _save_key_pools(pools)
                if removed_keys:
                    cache = _load_key_probe_cache()
                    for key_value in removed_keys:
                        cache.pop(_hash_key(key_value), None)
                    _save_key_probe_cache(cache)
                result = f'Пул {proto} очищен. Удалено ключей: {len(removed_keys)}'
                _invalidate_web_status_cache()
                _invalidate_key_status_cache()
            except Exception as exc:
                result = f'Ошибка очистки пула: {exc}'
            _set_web_flash_message(result)
            self._send_redirect('/')
            return

        if path == '/pool_subscribe':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            sub_url = data.get('url', [''])[0]
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
                    def _probe_added_keys(proto, keys):
                        proxy_url = proxy_settings.get(proto)
                        for k in keys:
                            try:
                                tg_ok, _ = _check_telegram_api_through_proxy(proxy_url, connect_timeout=3, read_timeout=4)
                                yt_ok, _ = _check_http_through_proxy(proxy_url, connect_timeout=2, read_timeout=3)
                                _record_key_probe(proto, k, tg_ok=tg_ok, yt_ok=yt_ok)
                            except Exception:
                                pass
                    threading.Thread(target=_probe_added_keys, args=(proto, added_keys), daemon=True).start()
                result = f'Загружено из subscription и добавлено в пул {proto}: {added} ключей'
                _invalidate_web_status_cache()
                _invalidate_key_status_cache()
            except Exception as exc:
                result = f'Ошибка загрузки subscription: {exc}'
            _set_web_flash_message(result)
            self._send_redirect('/')
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
        try:
            if key_type == 'shadowsocks':
                shadowsocks(key_value)
                result = _apply_installed_proxy('shadowsocks', key_value)
            elif key_type == 'vmess':
                vmess(key_value)
                result = _apply_installed_proxy('vmess', key_value)
            elif key_type == 'vless':
                vless(key_value)
                result = _apply_installed_proxy('vless', key_value)
            elif key_type == 'vless2':
                vless2(key_value)
                result = _apply_installed_proxy('vless2', key_value)
            elif key_type == 'trojan':
                trojan(key_value)
                result = _apply_installed_proxy('trojan', key_value)
            else:
                result = 'Тип ключа не распознан.'
        except Exception as exc:
            result = f'Ошибка установки: {exc}'
        else:
            if key_type in ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan'):
                _set_active_key(key_type, key_value)
            _invalidate_web_status_cache()
            _invalidate_key_status_cache()

        _set_web_flash_message(result)
        self._send_redirect('/')


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
            'access': CORE_PROXY_ACCESS_LOG,
            'error': CORE_PROXY_ERROR_LOG,
            'loglevel': 'info'
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
        vmess_data = _parse_vmess_key(vmess_key)
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
        stream_settings = {'network': vmess_data.get('net', 'tcp')}
        tls_mode = vmess_data.get('tls', 'tls')
        if tls_mode in ['tls', 'xtls']:
            stream_settings['security'] = tls_mode
            stream_settings[f'{tls_mode}Settings'] = {
                'allowInsecure': True,
                'serverName': vmess_data.get('add', '')
            }
        else:
            stream_settings['security'] = 'none'
        if stream_settings['network'] == 'ws':
            stream_settings['wsSettings'] = {
                'path': vmess_data.get('path', '/'),
                'headers': {'Host': vmess_data.get('host', '')}
            }
        elif stream_settings['network'] == 'grpc':
            grpc_service = vmess_data.get('serviceName', '') or vmess_data.get('grpcSettings', {}).get('serviceName', '')
            stream_settings['grpcSettings'] = {
                'serviceName': grpc_service,
                'multiMode': False
            }
        config_data['outbounds'].append({
            'tag': 'proxy-vmess',
            'domainStrategy': 'UseIPv4',
            'protocol': 'vmess',
            'settings': {
                'vnext': [{
                    'address': vmess_data['add'],
                    'port': int(vmess_data['port']),
                    'users': [{
                        'id': vmess_data['id'],
                        'alterId': int(vmess_data.get('aid', 0)),
                        'email': 't@t.tt',
                        'security': 'auto'
                    }]
                }]
            },
            'streamSettings': stream_settings,
            'mux': {
                'enabled': True,
                'concurrency': -1,
                'xudpConcurrency': 16,
                'xudpProxyUDP443': 'reject'
            }
        })
        config_data['routing']['rules'].append({
            'type': 'field',
            'inboundTag': ['in-vmess', 'in-vmess-transparent'],
            'outboundTag': 'proxy-vmess',
            'enabled': True
        })

    if shadowsocks_key:
        server, port, method, password = _decode_shadowsocks_uri(shadowsocks_key)
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
        config_data['outbounds'].append({
            'tag': 'proxy-shadowsocks',
            'protocol': 'shadowsocks',
            'settings': {
                'servers': [{
                    'address': server,
                    'port': int(port),
                    'method': method,
                    'password': password,
                    'level': 0
                }]
            }
        })
        config_data['routing']['rules'].append({
            'type': 'field',
            'inboundTag': ['in-shadowsocks'],
            'outboundTag': 'proxy-shadowsocks',
            'enabled': True
        })

    def add_vless_route(key_value, socks_port, transparent_port, socks_tag, transparent_tag, outbound_tag):
        if not key_value:
            return
        vless_data = _parse_vless_key(key_value)
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
        network = vless_data.get('type', 'tcp') or 'tcp'
        stream_settings = {'network': network}
        security = vless_data.get('security', 'none')
        if security in ['tls', 'xtls']:
            stream_settings['security'] = security
            stream_settings[f'{security}Settings'] = {
                'allowInsecure': True,
                'serverName': vless_data.get('sni', '')
            }
        else:
            stream_settings['security'] = 'none'
        if network == 'ws':
            stream_settings['wsSettings'] = {
                'path': vless_data.get('path', '/'),
                'headers': {'Host': vless_data.get('host', '')}
            }
        elif network == 'grpc':
            stream_settings['grpcSettings'] = {
                'serviceName': vless_data.get('serviceName', ''),
                'multiMode': False
            }
        elif security == 'reality':
            stream_settings['security'] = 'reality'
            stream_settings['realitySettings'] = {
                'serverName': vless_data.get('sni', '') or vless_data.get('host', '') or vless_data.get('address', ''),
                'publicKey': vless_data.get('publicKey', ''),
                'shortId': vless_data.get('shortId', ''),
                'fingerprint': vless_data.get('fingerprint', 'chrome'),
                'spiderX': vless_data.get('spiderX', '/')
            }
            if vless_data.get('alpn'):
                stream_settings['realitySettings']['alpn'] = [item.strip() for item in vless_data['alpn'].split(',') if item.strip()]
        config_data['outbounds'].append({
            'tag': outbound_tag,
            'domainStrategy': 'UseIPv4',
            'protocol': 'vless',
            'settings': {
                'vnext': [{
                    'address': vless_data.get('address', vless_data.get('host', '')),
                    'port': int(vless_data['port']),
                    'users': [{
                        'id': vless_data['id'],
                        'encryption': vless_data.get('encryption', 'none'),
                        'flow': vless_data.get('flow', ''),
                        'level': 0
                    }]
                }]
            },
            'streamSettings': stream_settings
        })
        config_data['routing']['rules'].append({
            'type': 'field',
            'inboundTag': [socks_tag, transparent_tag],
            'outboundTag': outbound_tag,
            'enabled': True
        })

    add_vless_route(vless_key, localportvless, localportvless_transparent, 'in-vless', 'in-vless-transparent', 'proxy-vless')
    add_vless_route(vless2_key, localportvless2, localportvless2_transparent, 'in-vless2', 'in-vless2-transparent', 'proxy-vless2')

    if trojan_key:
        trojan_data = _parse_trojan_key(trojan_key)
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
        trojan_stream = {
            'network': trojan_data.get('type', 'tcp') or 'tcp',
            'security': 'none'
        }
        if trojan_data.get('security', 'tls') == 'tls':
            trojan_stream['security'] = 'tls'
            trojan_stream['tlsSettings'] = {
                'allowInsecure': True,
                'serverName': trojan_data.get('sni') or trojan_data.get('host') or trojan_data.get('address', ''),
                'fingerprint': trojan_data.get('fingerprint', 'chrome')
            }
            if trojan_data.get('alpn'):
                trojan_stream['tlsSettings']['alpn'] = [item.strip() for item in trojan_data['alpn'].split(',') if item.strip()]
        if trojan_stream['network'] == 'ws':
            trojan_stream['wsSettings'] = {
                'path': trojan_data.get('path', '/'),
                'headers': {'Host': trojan_data.get('host') or trojan_data.get('sni') or trojan_data.get('address', '')}
            }
        elif trojan_stream['network'] == 'grpc':
            trojan_stream['grpcSettings'] = {
                'serviceName': trojan_data.get('serviceName', ''),
                'multiMode': False
            }
        config_data['outbounds'].append({
            'tag': 'proxy-trojan',
            'protocol': 'trojan',
            'settings': {
                'servers': [{
                    'address': trojan_data['address'],
                    'port': int(trojan_data['port']),
                    'password': trojan_data['password'],
                    'level': 0
                }]
            },
            'streamSettings': trojan_stream
        })
        config_data['routing']['rules'].append({
            'type': 'field',
            'inboundTag': ['in-trojan'],
            'outboundTag': 'proxy-trojan',
            'enabled': True
        })

    if config_data['outbounds']:
        config_data['outbounds'].append({'protocol': 'freedom', 'tag': 'direct'})
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
    global proxy_mode, bot_polling
    _daemonize_process()
    _register_signal_handlers()
    _write_runtime_log('main() entered', mode='w')
    start_http_server()
    try:
        _write_all_proxy_core_config()
        os.system(CORE_PROXY_SERVICE_SCRIPT + ' restart')
    except Exception as exc:
        _write_runtime_log(f'Не удалось пересобрать core proxy config при старте: {exc}')
    if _load_bot_autostart():
        globals()['bot_ready'] = True
    proxy_mode = _load_proxy_mode()
    ok, error = update_proxy(proxy_mode)
    if not ok:
        proxy_mode = config.default_proxy_mode
        update_proxy(proxy_mode)
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
            _write_runtime_log(f'Прокси-режим {proxy_mode} отключён при старте: {endpoint_message}')
            proxy_mode = 'none'
            update_proxy('none')
        else:
            api_status = check_telegram_api(retries=0, retry_delay=0, connect_timeout=8, read_timeout=10)
            if not api_status.startswith('✅'):
                _write_runtime_log(f'Прокси-режим {proxy_mode} не подтверждён при старте: {api_status}')
    _deliver_pending_telegram_command_result()
    _start_telegram_result_retry_worker()
    _start_auto_failover_thread()
    _ensure_current_keys_in_pools()
    _probe_all_pool_keys_async()
    wait_for_bot_start()
    while not shutdown_requested.is_set():
        try:
            bot_polling = True
            bot.infinity_polling(timeout=60, long_polling_timeout=50)
        except Exception as err:
            bot_polling = False
            _write_runtime_log(err)
            if shutdown_requested.is_set():
                break
            if _is_polling_conflict(err):
                _write_runtime_log('Обнаружен конфликт getUpdates, ожидание перед повторной попыткой 65 секунд')
                time.sleep(65)
            else:
                time.sleep(5)
        else:
            bot_polling = False
            if shutdown_requested.is_set():
                break
            time.sleep(2)
    _finalize_shutdown()


if __name__ == '__main__':
    main()
