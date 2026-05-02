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
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

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
    yt_ok, yt_message = _check_http_through_proxy(proxy_url, url='https://www.youtube.com', connect_timeout=4, read_timeout=6)
    if yt_ok:
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

        _write_runtime_log(f'Auto-failover: YouTube недоступен через прокси >{AUTO_FAILOVER_GRACE_SECONDS}s (режим {proxy_mode}). Пробуем ключи из пулов.')
        for proto, key_value in candidates:
            try:
                result = _install_key_for_protocol(proto, key_value)
            except Exception as exc:
                _write_runtime_log(f'Auto-failover: ошибка установки {proto} ключа: {exc}')
                continue

            proxy_url = proxy_settings.get(proto)
            yt_ok2, _ = _check_http_through_proxy(proxy_url, url='https://www.youtube.com', connect_timeout=6, read_timeout=10)
            if yt_ok2:
                tg_ok, _ = _check_telegram_api_through_proxy(proxy_url, connect_timeout=3, read_timeout=5)
                update_proxy(proto)
                _set_active_key(proto, key_value)
                _record_key_probe(proto, key_value, tg_ok=tg_ok, yt_ok=True)
                auto_failover_state['last_ok'] = time.time()
                auto_failover_state['last_fail'] = 0.0
                _write_runtime_log(f'Auto-failover: переключено на {proto}; YouTube доступен через прокси. {result}')
                return

        _write_runtime_log('Auto-failover: перебор ключей из пулов не дал доступа к YouTube.')
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
        _write_runtime_log(f'Запрошена остановка бота: {reason}')
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
        return 'Legacy-пути бота уже доступны.'
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
    if action == '-update':
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
            'details': f'{endpoint_message} Прокси не может использовать этот ключ.',
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
                f'не поднялся. Текущий режим прокси {active_label} сохранён. {diagnostics}').strip()

    endpoint_ok, endpoint_message = _check_local_proxy_endpoint(key_type, current['port'])
    if not endpoint_ok:
        return (f'⚠️ {current["label"]} ключ сохранён, но {endpoint_message} '
                f'Текущий режим прокси {active_label} сохранён. {diagnostics}').strip()

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
                f'Текущий режим прокси {active_label} сохранён.').strip()
    return (f'⚠️ {current["label"]} ключ сохранён. {endpoint_message} '
            f'Но Telegram API не проходит через этот ключ. '
            f'Текущий режим прокси {active_label} сохранён. '
            f'❌ Не удалось подключиться к Telegram API: {api_probe_message} {diagnostics}').strip()


def update_proxy(proxy_type):
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
        'state_label': 'web-only режим',
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
        update_buttons_html = f'''<form method="get" action="/confirm-switch">
                <input type="hidden" name="command" value="update">
                <button type="submit">Переустановить из форка без сброса</button>
            </form>
            <form method="get" action="/confirm-switch">
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

        start_button_label = 'Повторить запуск прокси' if bot_ready else 'Запустить прокси'

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
                        <p>Страница показывает состояние процессов и реальный статус связи с Telegram и Youtube.</p>
                        <p><strong>Вставляйте ключ полной строкой, как в Telegram.</strong></p>
                </div>
        <div class="hero-actions">
            <button type="button" class="theme-toggle" onclick="toggleTheme()">
                <span>Тема</span>
                <span id="theme-toggle-label">Темная тема</span>
            </button>
        </div>
        </div>
    </div>
    {message_block}
    {command_block}
        <section class="panel start-card">
            <div>
                <span class="eyebrow">Запуск</span>
                <h2 class="section-title">Быстрый старт</h2>
                    <p class="section-subtitle">После установки ключей можно сразу запустить прокси.</p>
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
        elif path == '/confirm-switch':
            query = parse_qs(urlparse(self.path).query)
            command = query.get('command', [''])[0]
            self._send_html(self._build_switch_confirmation(command))
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
                result = f'Режим прокси установлен: {proxy_type}'
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
            result = 'Команда запуска принята. Прокси-сервисы запущены.'
            _set_web_flash_message(result)
            self._send_redirect('/')
            return

        if path == '/command':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            command = data.get('command', [''])[0]
            if command in ('update', 'update_independent') and data.get('confirm_switch', [''])[0] != 'yes':
                self._send_redirect('/confirm-switch?' + urlencode({'command': command}))
                return
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
    global proxy_mode
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
    _start_auto_failover_thread()
    _ensure_current_keys_in_pools()
    _probe_all_pool_keys_async()
    _write_runtime_log('Web-only сервер запущен. Ожидание команд...')
    try:
        while not shutdown_requested.is_set():
            shutdown_requested.wait(1)
    except KeyboardInterrupt:
        pass
    _finalize_shutdown()
if __name__ == '__main__':
    main()
