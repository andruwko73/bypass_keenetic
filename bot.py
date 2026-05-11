#!/usr/bin/python3

#  2023. Keenetic DNS bot /  Проект: bypass_keenetic / Автор: tas_unn
#  GitHub: https://github.com/tas-unn/bypass_keenetic
#  Данный бот предназначен для управления обхода блокировок на роутерах Keenetic
#  Демо-бот: https://t.me/keenetic_dns_bot
#
#  Файл: bot.py, Версия v1.558, последнее изменение: 11.05.2026

import subprocess
import os
import re
import sys
import time
import threading
import signal
import ipaddress
import socket
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse
from proxy_key_store import (
    load_current_keys as _store_load_current_keys,
    load_shadowsocks_key as _store_load_shadowsocks_key,
    load_trojan_key as _store_load_trojan_key,
    proxy_config_snapshot_paths as _store_proxy_config_snapshot_paths,
    read_v2ray_key as _store_read_v2ray_key,
    remove_file_if_exists as _store_remove_file_if_exists,
    restore_proxy_config_files as _store_restore_proxy_config_files,
    save_v2ray_key as _store_save_v2ray_key,
    snapshot_proxy_config_files as _store_snapshot_proxy_config_files,
    v2ray_key_file_candidates as _store_v2ray_key_file_candidates,
)
from proxy_protocols import (
    decode_shadowsocks_uri as _store_decode_shadowsocks_uri,
    parse_trojan_key as _store_parse_trojan_key,
    parse_vless_key as _store_parse_vless_key,
    parse_vmess_key as _store_parse_vmess_key,
    proxy_outbound_from_key as _store_proxy_outbound_from_key,
)
from proxy_config_builder import (
    build_proxy_core_config as _builder_build_proxy_core_config,
    build_shadowsocks_config as _builder_build_shadowsocks_config,
    build_trojan_config as _builder_build_trojan_config,
)
from proxy_apply_runtime import (
    apply_installed_proxy_runtime as _runtime_apply_installed_proxy,
    proxy_apply_settings as _runtime_proxy_apply_settings,
)
from proxy_status import (
    active_mode_status_signature as _status_active_mode_signature,
    cached_active_status as _status_cached_active_status,
    cached_snapshot as _status_cached_snapshot,
    check_custom_target_through_proxy as _status_check_custom_target,
    check_http_through_proxy as _status_check_http,
    check_socks5_handshake as _check_socks5_handshake,
    ensure_service_port as _ensure_service_port,
    is_transient_status_text as _status_is_transient_text,
    placeholder_protocol_statuses as _status_placeholder_protocols,
    port_is_listening as _port_is_listening,
    protocol_error_status as _status_protocol_error,
    probe_custom_targets as _status_probe_custom_targets,
    read_tail as _read_tail,
    status_snapshot_signature as _status_snapshot_signature_impl,
    store_active_status as _status_store_active_status,
    store_snapshot as _status_store_snapshot,
    wait_for_socks5_handshake as _wait_for_socks5_handshake,
)
from unblock_lists import (
    entries_from_service_text as _entries_from_service_text,
    list_label as _unblock_list_label,
    load_unblock_lists as _load_unblock_lists_store,
    normalize_unblock_route_name as _normalize_unblock_route_name,
    read_unblock_list_entries as _read_unblock_list_entries,
    save_unblock_list_file as _save_unblock_list_file,
    unblock_list_path as _unblock_list_path,
    write_unblock_list_entries as _write_unblock_list_entries,
)
from custom_checks_store import (
    add_custom_check as _store_add_custom_check,
    custom_check_presets as _custom_check_presets,
    delete_custom_check as _store_delete_custom_check,
    load_custom_checks as _load_custom_checks,
    normalize_check_url as _normalize_check_url,
    route_entries_from_values as _route_entries_from_values,
)
import key_pool_store
import key_pool_web
import telegram_pool_ui
import web_pool_form_blocks
import telegram_key_ui
import entware_dns_runtime
import telegram_info_runtime
import auto_failover_runtime
from telegram_auth_state import (
    MENU_STATE_UNSET,
    authorize_message as _telegram_authorize_message,
    build_authorized_identities as _build_authorized_identities,
    callback_as_message as _telegram_callback_as_message,
    get_chat_menu_state as _get_chat_menu_state_impl,
    set_chat_menu_state as _set_chat_menu_state_impl,
    unauthorized_message_text as _telegram_unauthorized_text,
)
from telegram_jobs import (
    command_result_payload as _telegram_command_result_payload,
    final_message as _telegram_final_command_message,
    start_background_command as _telegram_start_background_command,
    start_result_retry_worker as _telegram_start_result_retry_worker,
)
from telegram_message_flow import (
    is_private_message as _telegram_is_private_message,
    private_menu_session as _telegram_private_menu_session,
    recover_private_message_error as _telegram_recover_private_message_error,
    run_handlers as _telegram_run_handlers,
)
from telegram_confirm import (
    TELEGRAM_CONFIRM_LEVEL,
    telegram_confirm_prompt as _telegram_confirm_prompt,
    telegram_is_cancel as _telegram_is_cancel_confirmation,
    telegram_is_confirm as _telegram_is_confirm_confirmation,
)
from telegram_install_ui import (
    INSTALL_MENU_TEXT,
    install_action_for_text as _telegram_install_action,
    install_menu_rows as _telegram_install_menu_rows,
)
from pool_probe_controller import (
    PoolProbeProgress,
    available_memory_kb as _available_memory_kb,
    check_pool_key_through_proxy as _controller_check_pool_key_through_proxy,
    failed_custom_probe_results as _failed_custom_probe_results,
    filter_active_probe_tasks as _controller_filter_active_probe_tasks,
    pool_probe_progress_label as _controller_pool_probe_progress_label,
    pool_probe_timeout_budget as _controller_pool_probe_timeout_budget,
    select_pool_probe_tasks as _controller_select_pool_probe_tasks,
    start_pool_probe_worker,
)
from probe_cache import (
    KeyProbeBatchRecorder as _KeyProbeBatchRecorder,
    forget_key_probes as _forget_key_probes,
    hash_key as _hash_key,
    key_probe_is_fresh as _key_probe_is_fresh,
    load_key_probe_cache as _load_key_probe_cache,
    record_key_probe as _record_key_probe,
)
from service_catalog import (
    CONNECTIVITY_CHECK_DOMAINS,
    CUSTOM_CHECK_PRESETS,
    SERVICE_LIST_SOURCES,
)
from pool_probe_runner import (
    build_pool_probe_core_config_batch as _runner_build_pool_probe_core_config_batch,
    cleanup_pool_probe_runtime as _runner_cleanup_pool_probe_runtime,
    find_pool_failover_candidate as _runner_find_pool_failover_candidate,
    pool_probe_outbound as _runner_pool_probe_outbound,
    run_pool_probe_worker,
    start_pool_probe_xray as _runner_start_pool_probe_xray,
    stop_pool_probe_xray as _runner_stop_pool_probe_xray,
)
from web_command_state import (
    command_state_snapshot as _command_state_snapshot,
    consume_command_state_for_render as _consume_command_state_for_render_impl,
    consume_flash_message as _consume_flash_message_impl,
    estimate_update_progress as _estimate_update_progress,
    finish_command as _finish_command_state,
    set_command_progress as _set_command_progress_state,
    set_flash_message as _set_flash_message_impl,
    start_command as _start_command_state,
)
from web_http_common import (
    WebRequestMixin,
    config_web_auth_token as _web_config_auth_token,
    config_web_auth_user as _web_config_auth_user,
    is_local_web_client as _web_is_local_client,
    resolve_bind_host as _web_resolve_bind_host,
)
import web_form_blocks
import web_get_actions
import web_post_actions
import web_status_runtime
from web_form_template import render_web_form, render_web_script_asset, render_web_style_asset
from web_status_builder import (
    active_protocol_status as _status_active_protocol_status,
    cached_protocol_status as _status_cached_protocol_status,
    empty_protocol_status as _status_empty_protocol_status,
)
from repo_update import (
    direct_fetch_env as _repo_direct_fetch_env,
    download_repo_script as _repo_download_script,
    fetch_remote_text as _fetch_remote_text,
    run_script_and_collect as _repo_run_script_and_collect,
    write_script as _repo_write_script,
)

import telebot
from telebot import types
import shutil
# import datetime
import requests
import json
import html
import bot_config as config

# --- Пул ключей и авто-фейловер Telegram API ---
KEY_POOLS_PATH = '/opt/etc/bot/key_pools.json'
SUBSCRIPTION_MAX_BYTES = int(getattr(config, 'subscription_max_bytes', 2 * 1024 * 1024))
SUBSCRIPTION_ALLOW_PRIVATE_URLS = bool(getattr(config, 'subscription_allow_private_urls', False))
AUTO_FAILOVER_GRACE_SECONDS = int(getattr(config, 'auto_failover_grace_seconds', 180))
AUTO_FAILOVER_POLL_SECONDS = int(getattr(config, 'auto_failover_poll_seconds', 60))
AUTO_FAILOVER_SWITCH_COOLDOWN_SECONDS = int(getattr(config, 'auto_failover_switch_cooldown_seconds', 180))
AUTO_FAILOVER_CHECK_CONNECT_TIMEOUT = float(getattr(config, 'auto_failover_check_connect_timeout', 2))
AUTO_FAILOVER_CHECK_READ_TIMEOUT = float(getattr(config, 'auto_failover_check_read_timeout', 3))
auto_failover_state = {
    'last_ok': 0.0,
    'last_fail': 0.0,
    'last_attempt': 0.0,
    'in_progress': False,
}

def _add_custom_check(label='', url='', preset_id=''):
    checks, result = _store_add_custom_check(label=label, url=url, preset_id=preset_id)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return checks, result


def _delete_custom_check(check_id):
    checks = _store_delete_custom_check(check_id)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return checks

TELEGRAM_SVG_B64 = 'PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCA1MTIgNTEyIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxjaXJjbGUgY3g9IjI1NiIgY3k9IjI1NiIgcj0iMjU2IiBmaWxsPSIjMzdBRUUyIi8+PHBhdGggZD0iTTExOSAyNjVsMjY1LTEwNGMxMi01IDIzIDMgMTkgMTlsLTQ1IDIxMmMtMyAxMy0xMiAxNi0yNCAxMGwtNjYtNDktMzIgMzFjLTQgNC03IDctMTUgN2w2LTg1IDE1NS0xNDBjNy02LTItMTAtMTEtNGwtMTkyIDEyMS04My0yNmMtMTgtNi0xOC0xOCA0LTI2eiIgZmlsbD0iI2ZmZiIvPjwvc3ZnPg=='
YOUTUBE_SVG_B64 = 'PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCA0NDMgMzIwIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSI0NDMiIGhlaWdodD0iMzIwIiByeD0iNzAiIGZpbGw9IiNGRjAwMDAiLz48cG9seWdvbiBwb2ludHM9IjE3Nyw5NiAzNTUsMTYwIDE3NywyMjQiIGZpbGw9IiNmZmYiLz48L3N2Zz4='


def _telegram_icon_html(opacity=1.0):
    style = f'vertical-align:middle;opacity:{opacity:g}'
    return f'<img src="data:image/svg+xml;base64,{TELEGRAM_SVG_B64}" width="16" height="16" alt="Telegram" style="{style}">'


def _youtube_icon_html(opacity=1.0):
    style = f'vertical-align:middle;opacity:{opacity:g}'
    return f'<img src="data:image/svg+xml;base64,{YOUTUBE_SVG_B64}" width="16" height="16" alt="YouTube" style="{style}">'


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
    with key_pool_lock:
        return key_pool_store.load_key_pools(KEY_POOLS_PATH)


def _dedupe_key_list(keys):
    return key_pool_store.dedupe_key_list(keys)


def _save_key_pools(pools):
    with key_pool_lock:
        return key_pool_store.save_key_pools(KEY_POOLS_PATH, pools)


def _private_subscription_address(hostname):
    host = str(hostname or '').strip()
    if not host:
        return True
    addresses = set()
    try:
        addresses.add(ipaddress.ip_address(host))
    except ValueError:
        try:
            for item in socket.getaddrinfo(host, None):
                addresses.add(ipaddress.ip_address(item[4][0]))
        except Exception:
            return True
    for address in addresses:
        if (
            address.is_private or
            address.is_loopback or
            address.is_link_local or
            address.is_multicast or
            address.is_unspecified or
            address.is_reserved
        ):
            return True
    return False


def _read_limited_response(response, max_bytes):
    content_length = response.headers.get('Content-Length')
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise ValueError('subscription response is too large')
        except ValueError:
            raise ValueError('subscription response is too large')
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=16384, decode_unicode=False):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise ValueError('subscription response is too large')
        chunks.append(chunk)
    encoding = response.encoding or 'utf-8'
    return b''.join(chunks).decode(encoding, errors='replace').strip()


def _fetch_keys_from_subscription(url):
    """Загружает ключи из subscription-ссылки (base64-encoded список)."""
    try:
        parsed = urlparse(str(url or '').strip())
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise ValueError('subscription URL must be http:// or https://')
        if not SUBSCRIPTION_ALLOW_PRIVATE_URLS and _private_subscription_address(parsed.hostname):
            raise ValueError('private, local and reserved subscription hosts are not allowed')
        session = requests.Session()
        session.trust_env = False
        resp = session.get(url, stream=True, timeout=(5, 15))
        try:
            resp.raise_for_status()
            raw = _read_limited_response(resp, SUBSCRIPTION_MAX_BYTES)
        finally:
            resp.close()
        return key_pool_store.classify_subscription_keys(raw), None
    except requests.RequestException as exc:
        return None, f'Ошибка загрузки subscription: {exc}'
    except Exception as exc:
        return None, f'Ошибка обработки subscription: {exc}'
        


def _set_active_key(proto, key):
    with key_pool_lock:
        pools = key_pool_store.set_active_key(key_pool_store.load_key_pools(KEY_POOLS_PATH), proto, key)
        key_pool_store.save_key_pools(KEY_POOLS_PATH, pools)


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
    return auto_failover_runtime.attempt_auto_failover(
        state=auto_failover_state,
        pool_probe_locked=lambda: bool(globals().get('pool_probe_lock') and pool_probe_lock.locked()),
        proxy_mode=proxy_mode,
        proxy_url=proxy_settings.get(proxy_mode),
        check_telegram_api=_check_telegram_api_through_proxy,
        load_current_keys=_load_current_keys,
        load_key_pools=_load_key_pools,
        failover_candidates=key_pool_store.failover_candidates,
        find_pool_failover_candidate=_find_pool_failover_candidate,
        install_key_for_protocol=_install_key_for_protocol,
        update_proxy=update_proxy,
        set_active_key=_set_active_key,
        record_key_probe=_record_key_probe,
        log=_write_runtime_log,
        grace_seconds=AUTO_FAILOVER_GRACE_SECONDS,
        switch_cooldown_seconds=AUTO_FAILOVER_SWITCH_COOLDOWN_SECONDS,
        check_timeouts=(AUTO_FAILOVER_CHECK_CONNECT_TIMEOUT, AUTO_FAILOVER_CHECK_READ_TIMEOUT),
    )


def _start_auto_failover_thread():
    def worker():
        while not shutdown_requested.is_set():
            try:
                if _app_mode_pool_enabled():
                    _attempt_auto_failover()
            except Exception as exc:
                _write_runtime_log(f'Auto-failover error: {exc}')
            shutdown_requested.wait(AUTO_FAILOVER_POLL_SECONDS)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

token = getattr(config, 'token', '') or '0:WEBONLY_DISABLED'
usernames = getattr(config, 'usernames', [])
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
WEB_COMMAND_STATE_FILE = '/opt/etc/bot/web_command_state.json'
COMMAND_JOB_STALE_AFTER = 1800
TELEGRAM_RESULT_RETRY_INTERVAL = 30

WEB_STATUS_CACHE_TTL = 60
KEY_STATUS_CACHE_TTL = 60
STATUS_CACHE_TTL = min(WEB_STATUS_CACHE_TTL, KEY_STATUS_CACHE_TTL)
ACTIVE_MODE_STATUS_DURING_POOL_TTL = 30
WEB_STATUS_API_CACHE_TTL = float(getattr(config, 'web_status_api_cache_ttl', 3.0))
WEB_STATUS_STARTUP_GRACE_PERIOD = 45
KEY_PROBE_MAX_PER_RUN = None
POOL_PROBE_ACTIVE_ONLY = False
POOL_PROBE_DELAY_SECONDS = float(getattr(config, 'pool_probe_delay_seconds', 0.8))
POOL_PROBE_MIN_AVAILABLE_KB = 120000
POOL_PROBE_TEST_PORT = str(getattr(config, 'pool_probe_test_port', 10991))
POOL_FAILOVER_TEST_PORT = str(getattr(config, 'pool_failover_test_port', int(POOL_PROBE_TEST_PORT) + 64))
POOL_PROBE_BATCH_SIZE = max(1, int(getattr(config, 'pool_probe_batch_size', 1)))
POOL_PROBE_CONCURRENCY = max(1, min(int(getattr(config, 'pool_probe_concurrency', 1)), POOL_PROBE_BATCH_SIZE))
POOL_PROBE_CACHE_FLUSH_EVERY = max(1, int(getattr(config, 'pool_probe_cache_flush_every', 5)))
POOL_PROBE_CACHE_FLUSH_INTERVAL = max(0.2, float(getattr(config, 'pool_probe_cache_flush_interval', 2.0)))
POOL_PROBE_TG_CONNECT_TIMEOUT = float(getattr(config, 'pool_probe_tg_connect_timeout', 2))
POOL_PROBE_TG_READ_TIMEOUT = float(getattr(config, 'pool_probe_tg_read_timeout', 3))
POOL_PROBE_HTTP_CONNECT_TIMEOUT = float(getattr(config, 'pool_probe_http_connect_timeout', 2))
POOL_PROBE_HTTP_READ_TIMEOUT = float(getattr(config, 'pool_probe_http_read_timeout', 3))
POOL_PROBE_CUSTOM_CONNECT_TIMEOUT = float(getattr(config, 'pool_probe_custom_connect_timeout', 1.5))
POOL_PROBE_CUSTOM_READ_TIMEOUT = float(getattr(config, 'pool_probe_custom_read_timeout', 2.5))
POOL_PROBE_RETRY_CONNECT_TIMEOUT = float(getattr(config, 'pool_probe_retry_connect_timeout', 6))
POOL_PROBE_RETRY_READ_TIMEOUT = float(getattr(config, 'pool_probe_retry_read_timeout', 10))
POOL_PROBE_RETRY_DELAY_SECONDS = float(getattr(config, 'pool_probe_retry_delay_seconds', 0.2))
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
POOL_PROBE_TIMEOUTS = (
    POOL_PROBE_TG_CONNECT_TIMEOUT, POOL_PROBE_TG_READ_TIMEOUT,
    POOL_PROBE_HTTP_CONNECT_TIMEOUT, POOL_PROBE_HTTP_READ_TIMEOUT,
    POOL_PROBE_CUSTOM_CONNECT_TIMEOUT, POOL_PROBE_CUSTOM_READ_TIMEOUT,
    POOL_PROBE_SINGLE_TIMEOUT_SECONDS, POOL_PROBE_BATCH_TIMEOUT_SECONDS,
)
POOL_PROBE_UI_POLL_EXTENSION_MS = int(getattr(config, 'pool_probe_ui_poll_extension_ms', 180000))
APP_BRANCH_LABEL = 'main'
APP_BRANCH_DESCRIPTION = 'единая версия'
APP_VERSION_COUNTER = '1.558'
APP_VERSION_LABEL = APP_VERSION_COUNTER
APP_MODE_LABEL = 'Режим бота'
APP_MODE_NOUN = 'режим бота'
APP_START_IDLE_LABEL = 'Запустить бота'
APP_START_REPEAT_LABEL = 'Повторить запуск бота'
APP_START_RESULT = 'Команда запуска принята. Если Telegram API доступен, бот начнет отвечать через несколько секунд.'
APP_QUICK_START_NOTE = 'После установки ключей можно сразу запустить или перезапустить Telegram-бота.'
APP_PROXY_USER_LABEL = 'Бот'
APP_RUNTIME_MODE_FILE = '/opt/etc/bot_app_mode'
APP_RUNTIME_MODES = (
    ('simple', 'Простой', 'интерфейс и Telegram-бот'),
    ('advanced', 'Сложный', 'интерфейс с пулом ключей и Telegram-бот'),
    ('web_only', 'Web only', 'интерфейс с пулом ключей без Telegram-бота'),
)
APP_RUNTIME_MODE_DATA = {
    value: {'label': label, 'description': description}
    for value, label, description in APP_RUNTIME_MODES
}
APP_DEFAULT_RUNTIME_MODE = getattr(config, 'app_runtime_mode', 'advanced')
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
PROXY_LOCAL_PORTS = {
    'shadowsocks': localportsh_bot,
    'vmess': localportvmess,
    'vless': localportvless,
    'vless2': localportvless2,
    'trojan': localporttrojan_bot,
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
web_status_api_cache = {
    'timestamp': 0,
    'payload': None,
}
active_mode_status_cache = {
    'timestamp': 0,
    'signature': None,
    'status': None,
}
active_mode_status_cache_lock = threading.Lock()
web_status_api_cache_lock = threading.Lock()
status_refresh_lock = threading.Lock()
status_refresh_in_progress = set()
key_pool_lock = threading.RLock()
pool_probe_lock = threading.Lock()
pool_apply_lock = threading.Lock()
pool_probe_progress = PoolProbeProgress()
process_started_at = time.time()
WEB_UPDATE_COMMANDS = ('update',)
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
web_flash_state = {'message': ''}
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
chat_menu_state_lock = threading.Lock()
chat_menu_states = {}
chat_pool_pages = {}


AUTHORIZED_USERNAMES, AUTHORIZED_USER_IDS = _build_authorized_identities(usernames)
EXTRA_AUTHORIZED_USER_IDS = getattr(config, 'authorized_user_ids', [])
_, EXTRA_NUMERIC_USER_IDS = _build_authorized_identities(EXTRA_AUTHORIZED_USER_IDS)
AUTHORIZED_USER_IDS.update(EXTRA_NUMERIC_USER_IDS)


def _normalize_app_runtime_mode(mode):
    mode = str(mode or '').strip().lower().replace('-', '_')
    return mode if mode in APP_RUNTIME_MODE_DATA else 'advanced'


def _load_app_runtime_mode():
    try:
        with open(APP_RUNTIME_MODE_FILE, 'r', encoding='utf-8') as f:
            mode = f.read().strip()
    except FileNotFoundError:
        mode = APP_DEFAULT_RUNTIME_MODE
    except Exception as exc:
        _write_runtime_log(f'Не удалось прочитать режим программы: {exc}')
        mode = APP_DEFAULT_RUNTIME_MODE
    return _normalize_app_runtime_mode(mode)


def _save_app_runtime_mode(mode):
    mode = _normalize_app_runtime_mode(mode)
    os.makedirs(os.path.dirname(APP_RUNTIME_MODE_FILE), exist_ok=True)
    with open(APP_RUNTIME_MODE_FILE, 'w', encoding='utf-8') as f:
        f.write(mode + '\n')
    return mode


def _app_runtime_mode_label(mode=None):
    mode = _normalize_app_runtime_mode(mode or _load_app_runtime_mode())
    return APP_RUNTIME_MODE_DATA[mode]['label']


def _app_runtime_mode_description(mode=None):
    mode = _normalize_app_runtime_mode(mode or _load_app_runtime_mode())
    return APP_RUNTIME_MODE_DATA[mode]['description']


def _app_mode_pool_enabled(mode=None):
    return _normalize_app_runtime_mode(mode or _load_app_runtime_mode()) in ('advanced', 'web_only')


def _app_mode_telegram_enabled(mode=None):
    return _normalize_app_runtime_mode(mode or _load_app_runtime_mode()) != 'web_only'


def _schedule_app_service_restart():
    def worker():
        time.sleep(1.5)
        os.system('/opt/etc/init.d/S99telegram_bot restart >/dev/null 2>&1 &')

    threading.Thread(target=worker, daemon=True).start()


def _set_app_runtime_mode(mode):
    requested = str(mode or '').strip().lower().replace('-', '_')
    if requested not in APP_RUNTIME_MODE_DATA:
        return False, 'Неизвестный режим программы.', {
            'app_mode': _load_app_runtime_mode(),
            'app_mode_label': _app_runtime_mode_label(),
        }
    previous = _load_app_runtime_mode()
    current = _save_app_runtime_mode(requested)
    restart_required = (
        _app_mode_telegram_enabled(previous) != _app_mode_telegram_enabled(current) or
        _app_mode_pool_enabled(previous) != _app_mode_pool_enabled(current)
    )
    if current == 'web_only':
        globals()['bot_ready'] = False
        _save_bot_autostart(False)
    elif previous == 'web_only':
        globals()['bot_ready'] = True
        _save_bot_autostart(True)
    if restart_required:
        _schedule_app_service_restart()
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    label = _app_runtime_mode_label(current)
    suffix = ' Сервис перезапускается для применения режима.' if restart_required else ' Страница обновится для применения интерфейса.'
    return True, f'Режим программы установлен: {label}.{suffix}', {
        'app_mode': current,
        'app_mode_label': label,
        'pool_enabled': _app_mode_pool_enabled(current),
        'telegram_enabled': _app_mode_telegram_enabled(current),
        'reload_after_ms': 2500 if restart_required else 1200,
    }


def _raw_github_url(path):
    return f'https://raw.githubusercontent.com/{fork_repo_owner}/{fork_repo_name}/{APP_BRANCH_LABEL}/{path}?ts={int(time.time())}'


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


def _get_chat_menu_state(chat_id):
    return _get_chat_menu_state_impl(chat_menu_state_lock, chat_menu_states, chat_id)


def _set_chat_menu_state(chat_id, level=MENU_STATE_UNSET, bypass=MENU_STATE_UNSET):
    _set_chat_menu_state_impl(chat_menu_state_lock, chat_menu_states, chat_id, level=level, bypass=bypass)


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
    return telegram_info_runtime.telegram_info_text_from_readme(
        _fetch_remote_text,
        _raw_github_url,
        _read_text_file,
        README_PATH,
    )


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


def _authorize_message(message, handler_name):
    return _telegram_authorize_message(
        message,
        handler_name,
        AUTHORIZED_USERNAMES,
        AUTHORIZED_USER_IDS,
        log_callback=_write_runtime_log,
    )


def _send_unauthorized_message(message, reason):
    bot.send_message(message.chat.id, _telegram_unauthorized_text(reason))


def _read_json_file(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception:
        return default


def _write_json_file(path, payload):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix='.' + os.path.basename(path) + '.', suffix='.tmp', dir=directory or None)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(payload, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


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


def _reset_telegram_http_session(reason=''):
    try:
        telebot.apihelper._get_req_session(reset=True)
    except TypeError:
        try:
            session = telebot.apihelper._get_req_session()
            close = getattr(session, 'close', None)
            if close:
                close()
        except Exception:
            pass
    except Exception as exc:
        if reason:
            _write_runtime_log(f'Не удалось сбросить Telegram HTTP-сессию ({reason}): {exc}')


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
    return entware_dns_runtime.prepare_entware_dns()


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


def _send_remote_markdown_file(message, path, error_message, reply_markup=None):
    try:
        text = _fetch_remote_text(_raw_github_url(path))
    except requests.RequestException as exc:
        bot.send_message(message.chat.id, f'⚠️ {error_message}: {exc}', reply_markup=reply_markup)
        return False
    bot.send_message(message.chat.id, text, parse_mode='Markdown', disable_web_page_preview=True)
    return True


def _socialnet_entries_from_text(text):
    return _entries_from_service_text(text, SOCIALNET_EXCLUDED_ENTRIES)


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


def _reply_keyboard(*rows):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for row in rows:
        markup.row(*(types.KeyboardButton(label) for label in row))
    return markup


def _socialnet_service_markup():
    options = [_socialnet_service_label(key) for key in SOCIALNET_SERVICE_KEYS]
    options.append(_socialnet_service_label(SOCIALNET_ALL_KEY))
    rows = [tuple(options[index:index + 2]) for index in range(0, len(options), 2)]
    return _reply_keyboard(*rows, ("🔙 Назад",))


def _list_actions_markup():
    return _reply_keyboard(
        ("📑 Показать список", "📝 Добавить в список", "🗑 Удалить из списка"),
        ("📥 Сервисы по запросу",),
        ("🔙 Назад",),
    )


def _send_unblock_list_file_missing(message, set_menu_state, reply_markup):
    bot.send_message(message.chat.id, '⚠️ Файл списка не найден. Откройте список заново.', reply_markup=reply_markup)
    set_menu_state(1, None)


def _send_unblock_list_menu(message, list_name):
    bot.send_message(message.chat.id, "Меню " + list_name, reply_markup=_list_actions_markup())


def _handle_unblock_list_selection(message, set_menu_state):
    selected_list = _resolve_unblock_list_selection(message.text)
    for file_name in os.listdir('/opt/etc/unblock/'):
        if file_name == selected_list + '.txt':
            set_menu_state(2, selected_list)
            bot.send_message(message.chat.id, "Меню " + _list_label(file_name), reply_markup=_list_actions_markup())
            return
    bot.send_message(message.chat.id, "Не найден", reply_markup=_reply_keyboard(("🔙 Назад",)))


def _send_unblock_list_contents(message, list_name, set_menu_state, reply_markup):
    try:
        sites = sorted(_read_unblock_list_entries(list_name))
    except FileNotFoundError:
        _send_unblock_list_file_missing(message, set_menu_state, reply_markup)
        return
    _send_telegram_chunks(message.chat.id, '\n'.join(sites) if sites else 'Список пуст')
    _send_unblock_list_menu(message, list_name)


def _start_unblock_list_edit(message, list_name, set_menu_state, next_level, prompt, service_action):
    bot.send_message(message.chat.id, prompt)
    set_menu_state(next_level)
    bot.send_message(message.chat.id, "Меню " + list_name, reply_markup=_reply_keyboard((service_action, "🔙 Назад")))


def _apply_unblock_list_text_change(current_entries, text, remove=False):
    entries = set(current_entries)
    count = len(entries)
    if remove:
        for site in text.split('\n'):
            entries.discard(site)
    elif len(text) > 1:
        entries.update(text.split('\n'))
    return entries, count != len(entries)


def _handle_socialnet_list_choice(message, list_name, set_menu_state, action_func, error_message):
    if message.text in ('🔙 Назад', 'Назад'):
        set_menu_state(2)
        _send_unblock_list_menu(message, list_name)
        return True
    service_key = _resolve_socialnet_service(message.text)
    try:
        result = action_func(list_name, service_key=service_key)
    except Exception as exc:
        bot.send_message(message.chat.id, f'⚠️ {error_message}: {exc}', reply_markup=_socialnet_service_markup())
        return True
    set_menu_state(2)
    bot.send_message(message.chat.id, result)
    _send_unblock_list_menu(message, list_name)
    return True


def _handle_unblock_list_state(message, level, bypass, set_menu_state, reply_markup):
    if level == 1:
        _handle_unblock_list_selection(message, set_menu_state)
        return True
    if level == 2 and message.text == "📑 Показать список":
        _send_unblock_list_contents(message, bypass, set_menu_state, reply_markup)
        return True
    if level == 2 and message.text == "📝 Добавить в список":
        _start_unblock_list_edit(
            message, bypass, set_menu_state, 3,
            "Введите имя сайта или домена для разблокировки, либо воспользуйтесь меню для других действий",
            "Добавить обход блокировок соцсетей",
        )
        return True
    if level == 2 and message.text == "🗑 Удалить из списка":
        _start_unblock_list_edit(
            message, bypass, set_menu_state, 4,
            "Введите имя сайта или домена для удаления из листа разблокировки,либо возвратитесь в главное меню",
            "Удалить обход блокировок соцсетей",
        )
        return True
    if level == 31:
        return _handle_socialnet_list_choice(message, bypass, set_menu_state, _append_socialnet_list, 'Не удалось добавить сервисы')
    if level == 32:
        return _handle_socialnet_list_choice(message, bypass, set_menu_state, _remove_socialnet_list, 'Не удалось удалить сервисы')
    if level not in (3, 4):
        return False
    try:
        current_entries = set(_read_unblock_list_entries(bypass))
    except FileNotFoundError:
        _send_unblock_list_file_missing(message, set_menu_state, reply_markup)
        return True
    if level == 3 and message.text == "Добавить обход блокировок соцсетей":
        set_menu_state(31)
        bot.send_message(message.chat.id, f'Выберите сервис для добавления в {_list_label(bypass + ".txt")}.', reply_markup=_socialnet_service_markup())
        return True
    if level == 4 and message.text == "Удалить обход блокировок соцсетей":
        set_menu_state(32)
        bot.send_message(message.chat.id, f'Выберите сервис для удаления из {_list_label(bypass + ".txt")}.', reply_markup=_socialnet_service_markup())
        return True
    updated_entries, changed = _apply_unblock_list_text_change(current_entries, message.text, remove=(level == 4))
    _write_unblock_list_entries(bypass, updated_entries)
    bot.send_message(message.chat.id, "✅ Успешно удалено" if changed and level == 4 else
                     "✅ Успешно добавлено" if changed else "Не найдено в списке" if level == 4 else "Было добавлено ранее")
    set_menu_state(2)
    subprocess.run(["/opt/bin/unblock_update.sh"], check=False)
    _send_unblock_list_menu(message, bypass)
    return True


def _service_list_markup():
    labels = [source['label'] for source in SERVICE_LIST_SOURCES.values()]
    rows = [tuple(labels[index:index + 2]) for index in range(0, len(labels), 2)]
    return _reply_keyboard(*rows, ("🔙 Назад",))


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
    if service_key == 'telegram' and not route:
        route = 'vless'
    if not route:
        state = _get_chat_menu_state(message.chat.id)
        route = state.get('bypass')
    if not route:
        route = 'vless'
    if not re.match(r'^[A-Za-z0-9_-]+$', route or ''):
        bot.send_message(message.chat.id, '⚠️ Некорректное имя маршрута.', reply_markup=reply_markup)
        return

    source = SERVICE_LIST_SOURCES[service_key]
    try:
        if source.get('entries'):
            entries = list(source['entries'])
        else:
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


def _send_key_status_report(message, service_markup):
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
        status_clean = re.sub(r'<[^>]+>', '', status_text).strip()
        if has_telegram_icon and 'Telegram' not in status_clean:
            status_clean = f'{status_clean} 📱 Telegram'
        details = st.get('details', '')
        text_lines.append(f"{mark} <b>{label}</b>: {status_clean}")
        if details:
            text_lines.append(f"<i>{details}</i>")
    bot.send_message(message.chat.id, '\n'.join(text_lines), parse_mode='HTML', reply_markup=service_markup)


def _handle_private_stateless_command(message, main, service):
    command = message.text.split(maxsplit=1)[0].split('@', 1)[0]
    if command == '/getlist':
        parts = message.text.split()
        if len(parts) < 2:
            names = ', '.join(source['label'] for source in SERVICE_LIST_SOURCES.values())
            bot.send_message(message.chat.id, f'Использование: /getlist название [маршрут]\nДоступно: {names}', reply_markup=main)
            return True
        route_name = parts[2] if len(parts) > 2 else None
        _handle_getlist_request(message, parts[1], route_name=route_name, reply_markup=main)
        return True

    if message.text == '📊 Статус ключей':
        _send_key_status_report(message, service)
        return True

    if message.text in ('📦 Пул ключей', '/pool'):
        if not _app_mode_pool_enabled():
            bot.send_message(message.chat.id, 'Пул ключей отключен в простом режиме.', reply_markup=main)
            return True
        _set_chat_menu_state(message.chat.id, level=20, bypass=None)
        _clear_pool_inline_keyboard(message.chat.id)
        _clear_pool_page(message.chat.id)
        bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
        return True

    return False


def _build_main_menu_markup():
    return _reply_keyboard(
        ("🔰 Установка и удаление",),
        ("🔑 Ключи", "📝 Списки обхода"),
        ("📄 Информация", "⚙️ Сервис"),
    )


def _build_keys_menu_markup():
    return _reply_keyboard(*telegram_key_ui.key_menu_rows(include_pool=_app_mode_pool_enabled()))


def _handle_key_menu_message(message, level, set_menu_state, reply_markup):
    if level == 8:
        if message.text == telegram_key_ui.KEY_HELP_TEXT:
            if _send_remote_markdown_file(message, 'keys.md', 'Не удалось загрузить справку по ключам', reply_markup):
                set_menu_state(8)
            return True
        target_level = telegram_key_ui.key_input_level(message.text, trojan_level=13)
        if target_level is not None:
            set_menu_state(target_level)
            bot.send_message(message.chat.id, telegram_key_ui.KEY_COPY_PROMPT, reply_markup=_reply_keyboard(("🔙 Назад",)))
            return True
    key_install_proto = telegram_key_ui.key_install_protocol(level, trojan_level=13)
    if key_install_proto:
        set_menu_state(0)
        _install_proxy_from_message(message, key_install_proto, message.text, reply_markup)
        return True
    if message.text == telegram_key_ui.KEY_BROWSER_TEXT:
        bot.send_message(message.chat.id, telegram_key_ui.browser_hint(routerip, browser_port), reply_markup=reply_markup)
        return True
    return False


def _build_service_menu_markup():
    return _reply_keyboard(
        ("♻️ Перезагрузить сервисы", "‼️Перезагрузить роутер"),
        ("‼️DNS Override", "📊 Статус ключей"),
        ("🔙 Назад",),
    )


def _build_telegram_confirm_markup():
    return _reply_keyboard(("✅ Подтвердить", "Отмена"), ("🔙 Назад",))


def _request_telegram_confirmation(message, set_menu_state, action):
    set_menu_state(TELEGRAM_CONFIRM_LEVEL, action)
    bot.send_message(message.chat.id, _telegram_confirm_prompt(action), reply_markup=_build_telegram_confirm_markup())


def _execute_confirmed_telegram_action(chat_id, action, reply_markup):
    if action in ('update_independent', 'update_no_bot'):
        action = 'update_main'
    update_actions = {
        'update_main': {
            'repo_owner': fork_repo_owner,
            'repo_name': fork_repo_name,
            'branch': 'main',
            'message': (
                f'Запускаю установку/переустановку из ветки main форка {fork_repo_owner}/{fork_repo_name} без сброса ключей и списков. '
                'Обычно это занимает 1-3 минуты. Во время обновления бот может временно пропасть из сети, '
                'потому что сервис будет перезапущен. После запуска бот сам пришлет в этот чат лог и итоговое сообщение.'
            ),
        },
    }
    if action in update_actions:
        params = update_actions[action]
        _start_telegram_update_from_chat(
            chat_id,
            reply_markup,
            menu_name='main',
            repo_owner=params['repo_owner'],
            repo_name=params['repo_name'],
            branch=params['branch'],
            start_message=params['message'],
        )
        return
    if action == 'restart_services':
        bot.send_message(chat_id, '🔄 Выполняется перезагрузка сервисов!', reply_markup=reply_markup)
        _restart_router_services()
        _send_message_after_service_restart(chat_id, '✅ Сервисы перезагружены!', reply_markup=reply_markup)
        return
    if action == 'reboot':
        bot.send_message(chat_id, '🔄 Роутер перезагружается. Это займёт около 2 минут.', reply_markup=reply_markup)
        _schedule_router_reboot()
        return
    if action == 'dns_on':
        bot.send_message(chat_id, _set_dns_override(True), reply_markup=reply_markup)
        return
    if action == 'dns_off':
        bot.send_message(chat_id, _set_dns_override(False), reply_markup=reply_markup)
        return
    if action == 'remove':
        return_code, output = _run_script_action('-remove', fork_repo_owner, fork_repo_name)
        _send_telegram_chunks(chat_id, output, reply_markup=reply_markup)
        if return_code == 0:
            bot.send_message(chat_id, '✅ Удаление завершено.', reply_markup=reply_markup)
        else:
            bot.send_message(chat_id, '⚠️ Удаление завершилось с ошибкой. Полный лог отправлен выше.', reply_markup=reply_markup)
        return
    bot.send_message(chat_id, 'Команда не распознана.', reply_markup=reply_markup)


def _handle_telegram_confirmation(message, level, bypass, set_menu_state, reply_markup):
    if level != TELEGRAM_CONFIRM_LEVEL:
        return False
    if _telegram_is_confirm_confirmation(message.text):
        action = bypass
        set_menu_state(0, None)
        _execute_confirmed_telegram_action(message.chat.id, action, reply_markup)
        return True
    if _telegram_is_cancel_confirmation(message.text):
        set_menu_state(0, None)
        bot.send_message(message.chat.id, 'Действие отменено.', reply_markup=reply_markup)
        return True
    bot.send_message(message.chat.id, _telegram_confirm_prompt(bypass), reply_markup=_build_telegram_confirm_markup())
    return True


def _handle_install_menu_message(message, set_menu_state):
    action = _telegram_install_action(message.text, include_web_only=True)
    if action == 'menu':
        bot.send_message(message.chat.id, INSTALL_MENU_TEXT, reply_markup=_reply_keyboard(*_telegram_install_menu_rows(include_web_only=True)))
        return True
    if action:
        _request_telegram_confirmation(message, set_menu_state, action)
        return True
    return False


def _send_telegram_readme_info(message, reply_markup):
    bot.send_message(message.chat.id, _telegram_info_text_from_readme(), parse_mode='HTML',
                     disable_web_page_preview=True, reply_markup=reply_markup)


TELEGRAM_MENU_CONFIRM_ACTIONS = {
    '♻️ Перезагрузить сервисы': 'restart_services',
    'Перезагрузить сервисы': 'restart_services',
    '‼️Перезагрузить роутер': 'reboot',
    'Перезагрузить роутер': 'reboot',
    '✅ DNS Override ВКЛ': 'dns_on',
    '❌ DNS Override ВЫКЛ': 'dns_off',
}


def _handle_common_telegram_menu_message(message, level, bypass, set_menu_state, main, service):
    if _handle_telegram_confirmation(message, level, bypass, set_menu_state, service):
        return True

    if message.text == '⚙️ Сервис':
        bot.send_message(message.chat.id, '⚙️ Сервисное меню!', reply_markup=service)
        return True

    if message.text == '‼️DNS Override' or message.text == 'DNS Override':
        dns_menu = _reply_keyboard(("✅ DNS Override ВКЛ", "❌ DNS Override ВЫКЛ"), ("🔙 Назад",))
        bot.send_message(message.chat.id, '‼️DNS Override!', reply_markup=dns_menu)
        return True

    action = TELEGRAM_MENU_CONFIRM_ACTIONS.get(message.text)
    if action:
        _request_telegram_confirmation(message, set_menu_state, action)
        return True

    # Кнопка "Обновление" убрана из меню "Сервис" (заменена на "Статус ключей").
    if message.text == '📄 Информация':
        _send_telegram_readme_info(message, main)
        return True

    if message.text == '/keys_free':
        _send_remote_markdown_file(message, 'keys.md', 'Не удалось загрузить список ключей', main)
        return True

    if message.text == '🔄 Обновления' or message.text == '/check_update':
        _send_telegram_update_status(message, service)
        return True

    if message.text == '/update':
        _request_telegram_confirmation(message, set_menu_state, 'update_main')
        return True

    return False


def _handle_service_request_menu(message, level, bypass, set_menu_state):
    if message.text != "📥 Сервисы по запросу":
        return False
    if level == 2 and bypass:
        set_menu_state(10)
        bot.send_message(message.chat.id, f'Выберите сервис для маршрута {_list_label(bypass + ".txt")}', reply_markup=_service_list_markup())
    else:
        set_menu_state(10, 'vless')
        bot.send_message(
            message.chat.id,
            'Выберите сервис. По умолчанию список будет добавлен в маршрут Vless 1.',
            reply_markup=_service_list_markup(),
        )
    return True


def _handle_back_to_main_message(message, set_menu_state, main):
    if message.text not in ('🔙 Назад', 'Назад'):
        return False
    _clear_pool_inline_keyboard(message.chat.id)
    _clear_pool_page(message.chat.id)
    bot.send_message(message.chat.id, '✅ Добро пожаловать в меню!', reply_markup=main)
    set_menu_state(0, None)
    return True


def _handle_service_list_state(message, level, bypass, set_menu_state):
    if level != 10:
        return False
    target_route = bypass
    reply_markup = _list_actions_markup() if target_route else _service_list_markup()
    _handle_getlist_request(message, message.text, route_name=target_route, reply_markup=reply_markup)
    if target_route:
        set_menu_state(2, target_route)
    return True


def _handle_main_menu_openers(message, set_menu_state):
    if message.text == "📝 Списки обхода":
        set_menu_state(1, None)
        bot.send_message(
            message.chat.id,
            "📝 Списки обхода",
            reply_markup=_telegram_unblock_lists_markup(("📥 Сервисы по запросу",)),
        )
        return True
    if message.text in ("🔑 Ключи", "🔑 Ключи и мосты"):
        set_menu_state(8, None)
        bot.send_message(message.chat.id, "🔑 Ключи", reply_markup=_build_keys_menu_markup())
        return True
    return False


def _telegram_command_markup(menu_name):
    return _build_service_menu_markup() if menu_name == 'service' else _build_main_menu_markup()


def _run_telegram_command_worker(action, repo_owner, repo_name, chat_id, menu_name, branch='main'):
    try:
        return_code, output = _run_script_action(action, repo_owner, repo_name, branch=branch)
    except Exception as exc:
        return_code = 1
        output = f'Ошибка запуска фоновой команды: {exc}'
    _write_json_file(
        TELEGRAM_COMMAND_RESULT_FILE,
        _telegram_command_result_payload(action, chat_id, menu_name, return_code, output),
    )
    _remove_file(TELEGRAM_COMMAND_JOB_FILE)


def _start_telegram_background_command(action, repo_owner, repo_name, chat_id, menu_name, branch='main'):
    return _telegram_start_background_command(
        job_file=TELEGRAM_COMMAND_JOB_FILE,
        action=action,
        repo_owner=repo_owner,
        repo_name=repo_name,
        chat_id=chat_id,
        menu_name=menu_name,
        branch=branch,
        bot_source_path=BOT_SOURCE_PATH,
        sys_executable=sys.executable,
        read_json_file=_read_json_file,
        write_json_file=_write_json_file,
        stale_after=COMMAND_JOB_STALE_AFTER,
    )


def _send_telegram_update_status(message, reply_markup):
    try:
        bot_new_version = _fetch_remote_text(_raw_github_url('version.md'))
    except requests.RequestException as exc:
        bot.send_message(message.chat.id, f'⚠️ Не удалось проверить обновления: {exc}', reply_markup=reply_markup)
        return
    bot.send_message(
        message.chat.id,
        "*ВАША ТЕКУЩАЯ " + str(_current_bot_version()) + "*\n\n"
        "*ПОСЛЕДНЯЯ ДОСТУПНАЯ ВЕРСИЯ:*\n\n" + str(bot_new_version),
        parse_mode='Markdown',
        reply_markup=reply_markup,
    )
    bot.send_message(
        message.chat.id,
        "Если вы хотите обновить текущую версию на более новую, нажмите сюда /update",
        parse_mode='Markdown',
        reply_markup=reply_markup,
    )


def _start_telegram_update_from_chat(chat_id, reply_markup, *, menu_name='service', repo_owner=None, repo_name=None,
                                     branch='main', start_message=None):
    repo_owner = repo_owner or fork_repo_owner
    repo_name = repo_name or fork_repo_name
    started, status_message = _start_telegram_background_command('-update', repo_owner, repo_name, chat_id, menu_name, branch=branch)
    if not started:
        bot.send_message(chat_id, status_message, reply_markup=reply_markup)
        return
    bot.send_message(
        chat_id,
        start_message or (
            f'Запускаю обновление из форка {repo_owner}/{repo_name}. Обычно это занимает 1-3 минуты. '
            'Во время обновления бот может временно пропасть из сети, потому что сервис будет перезапущен. '
            'После запуска бот сам пришлет в этот чат лог и итоговое сообщение.'
        ),
        reply_markup=reply_markup,
    )


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
        bot.send_message(chat_id, _telegram_final_command_message(action, return_code), reply_markup=markup)
        _remove_file(TELEGRAM_COMMAND_RESULT_FILE)
    except Exception as exc:
        _write_runtime_log(f'Не удалось доставить результат фоновой Telegram-команды: {exc}')


def _start_telegram_result_retry_worker():
    _telegram_start_result_retry_worker(
        shutdown_event=shutdown_requested,
        result_file=TELEGRAM_COMMAND_RESULT_FILE,
        deliver_result=_deliver_pending_telegram_command_result,
        log_callback=_write_runtime_log,
        retry_interval=TELEGRAM_RESULT_RETRY_INTERVAL,
    )


def _install_proxy_from_message(message, key_type, key_value, reply_markup):
    try:
        PROXY_KEY_INSTALLERS[key_type](key_value)
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


def _run_script_action(action, repo_owner=None, repo_name=None, progress_command=None, branch='main'):
    logs = [_prepare_entware_dns(), _ensure_legacy_bot_paths()]
    direct_env = _repo_direct_fetch_env(DIRECT_FETCH_ENV_KEYS)
    progress_callback = None
    if progress_command:
        def progress_callback(text):
            _set_web_command_progress(progress_command, text)
        progress_callback('\n'.join(logs))
    if repo_owner and repo_name:
        url, script_text, repo_ref = _repo_download_script(repo_owner, repo_name, branch=branch)
        direct_env['REPO_REF'] = branch
        logs.append(f'Скрипт загружен из {url}')
        logs.append(f'Коммит обновления: {repo_ref[:12]}')
        if repo_owner == fork_repo_owner and 'BOT_CONFIG_PATH' not in script_text:
            logs.append('⚠️ GitHub отдал старую версию script.sh, но legacy-пути уже подготовлены на роутере.')
        if progress_callback:
            progress_callback('\n'.join(logs))
        _repo_write_script(script_text)

    return _repo_run_script_and_collect(action, direct_env, logs, progress_callback)


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
    if command in ('update_independent', 'update_no_bot'):
        command = 'update'
    if command == 'install_original':
        _, output = _run_script_action('-install', 'tas-unn', 'bypass_keenetic')
        return output
    if command == 'update':
        _, output = _run_script_action('-update', fork_repo_owner, fork_repo_name, progress_command='update')
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
    match = re.search(r'Версия\s+(v?[0-9][0-9.]*)', source_text)
    if match:
        return match.group(1).strip()
    for line in source_text.splitlines():
        if line.startswith('# ВЕРСИЯ СКРИПТА'):
            return line.replace('# ВЕРСИЯ СКРИПТА', '').strip()
    return 'неизвестна'


def _save_unblock_list(list_name, text):
    if not os.path.basename(list_name).endswith('.txt'):
        raise ValueError('Список должен быть .txt файлом')
    safe_name = _save_unblock_list_file(list_name, text)
    return f'✅ Список {safe_name} сохранён и применён.'


def _append_socialnet_list(list_name, service_key=SOCIALNET_ALL_KEY):
    return _apply_socialnet_list(list_name, service_key=service_key, remove=False)


def _remove_socialnet_list(list_name, service_key=SOCIALNET_ALL_KEY):
    return _apply_socialnet_list(list_name, service_key=service_key, remove=True)


def _list_label(file_name):
    return _unblock_list_label(file_name, include_vpn=False)


def _load_unblock_lists(with_content=True):
    return _load_unblock_lists_store(
        with_content=with_content,
        read_text_file=_read_text_file,
        include_vpn=False,
    )


def _telegram_unblock_list_options():
    return [(entry['label'], entry['name'][:-4]) for entry in _load_unblock_lists(with_content=False)]


def _telegram_unblock_lists_markup(*extra_rows):
    labels = [label for label, _ in _telegram_unblock_list_options()]
    rows = [tuple(labels[index:index + 2]) for index in range(0, len(labels), 2)]
    rows.extend(extra_rows)
    return _reply_keyboard(*rows, ("🔙 Назад",))


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
    return _store_load_shadowsocks_key()


def _load_trojan_key():
    return _store_load_trojan_key()


def _load_current_keys():
    return _store_load_current_keys(VMESS_KEY_PATH, VLESS_KEY_PATH, VLESS2_KEY_PATH, XRAY_CONFIG_DIR, V2RAY_CONFIG_DIR)


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
    _invalidate_web_status_api_cache()


def _invalidate_web_status_api_cache():
    with web_status_api_cache_lock:
        web_status_api_cache['timestamp'] = 0
        web_status_api_cache['payload'] = None


def _get_web_status_api_cache():
    with web_status_api_cache_lock:
        payload = web_status_api_cache.get('payload')
        return {
            'timestamp': web_status_api_cache.get('timestamp', 0),
            'payload': payload,
        } if payload is not None else None


def _store_web_status_api_cache(payload, timestamp=None):
    with web_status_api_cache_lock:
        web_status_api_cache['timestamp'] = time.time() if timestamp is None else timestamp
        web_status_api_cache['payload'] = payload


def _invalidate_key_status_cache():
    _invalidate_status_snapshot_cache()


def _check_http_through_proxy(proxy_url, url='https://www.youtube.com', connect_timeout=2, read_timeout=3):
    return _status_check_http(proxy_url, url=url, connect_timeout=connect_timeout, read_timeout=read_timeout)


def _check_custom_target_through_proxy(proxy_url, url, connect_timeout=2, read_timeout=3):
    return _status_check_custom_target(
        _normalize_check_url,
        proxy_url,
        url,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
    )


def _probe_custom_targets(proxy_url, custom_checks=None, connect_timeout=2, read_timeout=3):
    return _status_probe_custom_targets(
        proxy_url,
        custom_checks if custom_checks is not None else _load_custom_checks(),
        _check_custom_target_through_proxy,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        max_targets=2,
    )


def _probe_custom_targets_for_pool(proxy_url, custom_checks=None):
    return _status_probe_custom_targets(
        proxy_url,
        custom_checks if custom_checks is not None else _load_custom_checks(),
        _check_custom_target_through_proxy,
        connect_timeout=POOL_PROBE_CUSTOM_CONNECT_TIMEOUT,
        read_timeout=POOL_PROBE_CUSTOM_READ_TIMEOUT,
    )


def _check_telegram_api_through_proxy(proxy_url=None, connect_timeout=6, read_timeout=10):
    authenticated_check = _app_mode_telegram_enabled()
    url = f'https://api.telegram.org/bot{token}/getMe' if authenticated_check else 'https://api.telegram.org/'
    proxies = {'https': proxy_url, 'http': proxy_url} if proxy_url else None
    try:
        response = requests.get(url, timeout=(connect_timeout, read_timeout), proxies=proxies)
        if not authenticated_check:
            if response.status_code < 500:
                return True, 'Доступ к api.telegram.org подтверждён.'
            response.raise_for_status()
        response.raise_for_status()
        data = response.json()
        if data.get('ok'):
            return True, 'Доступ к api.telegram.org подтверждён.'
        return False, f'Telegram API ответил: {data.get("description", "Не удалось определить причину")}.'
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
    port = PROXY_LOCAL_PORTS.get(key_name)
    endpoint_ok, endpoint_message = _check_local_proxy_endpoint(key_name, port)
    preflight = web_status_runtime.protocol_preflight_status(
        key_value,
        endpoint_ok,
        endpoint_message,
        proxy_user_label=APP_PROXY_USER_LABEL,
        xray_required=_key_requires_xray(key_name, key_value) and _core_proxy_runtime_name() != 'xray',
    )
    if preflight:
        return preflight

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
    custom_states = key_pool_web.web_custom_probe_states(cached_probe, custom_checks)
    if api_transient:
        _record_key_probe(key_name, key_value, yt_ok=yt_ok)
    else:
        _record_key_probe(key_name, key_value, tg_ok=api_ok, yt_ok=yt_ok)
    return _status_active_protocol_status(
        endpoint_ok=endpoint_ok,
        endpoint_message=endpoint_message,
        api_ok=api_ok,
        api_message=api_message,
        api_transient=api_transient,
        yt_ok=yt_ok,
        yt_message=yt_message,
        custom_states=custom_states,
        custom_checks=custom_checks,
    )


def _cached_protocol_status_for_key(key_name, key_value, custom_checks=None, key_probe_cache=None):
    if not key_value.strip():
        return _status_empty_protocol_status()
    custom_checks = custom_checks if custom_checks is not None else _load_custom_checks()
    cache = key_probe_cache if key_probe_cache is not None else _load_key_probe_cache()
    probe = cache.get(_hash_key(key_value), {})
    custom_states = key_pool_web.web_custom_probe_states(probe, custom_checks)
    return _status_cached_protocol_status(key_value, probe, custom_checks, custom_states)


def _placeholder_protocol_statuses(current_keys):
    return _status_placeholder_protocols(
        current_keys,
        pending_details='Фоновая проверка ключа выполняется. Статус обновится без перезагрузки страницы.',
    )


def _web_command_label(command):
    labels = {
        'install_original': 'Установить оригинальную версию',
        'update': 'Обновить до последнего релиза',
        'remove': 'Удалить компоненты',
        'restart_services': 'Перезапустить сервисы',
        'dns_on': 'DNS Override ВКЛ',
        'dns_off': 'DNS Override ВЫКЛ',
        'reboot': 'Перезагрузить роутер',
    }
    return labels.get(command, command)


def _web_command_state_defaults():
    return {
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


def _normalize_web_command_state(value):
    state = _web_command_state_defaults()
    if isinstance(value, dict):
        state.update(value)
    return state


def _read_web_command_state_file():
    return _normalize_web_command_state(_read_json_file(WEB_COMMAND_STATE_FILE, {}) or {})


def _write_web_command_state_file(state):
    _write_json_file(WEB_COMMAND_STATE_FILE, _normalize_web_command_state(state))


def _shared_command_job_running(state=None, source=None):
    state = _read_json_file(TELEGRAM_COMMAND_JOB_FILE, {}) if state is None else (state or {})
    if not state.get('running'):
        return False
    if source and state.get('source') != source:
        return False
    started_at = float(state.get('started_at') or 0)
    return bool(started_at and time.time() - started_at < COMMAND_JOB_STALE_AFTER)


def _web_background_command_code(command):
    module_name = os.path.splitext(os.path.basename(BOT_SOURCE_PATH))[0]
    module_dir = os.path.dirname(BOT_SOURCE_PATH)
    return (
        'import sys; '
        f"sys.path.insert(0, {module_dir!r}); "
        f'import {module_name} as bot_module; '
        f'bot_module._run_web_command_worker({command!r})'
    )


def _get_web_command_state():
    state = _read_web_command_state_file()
    if state.get('running') and not _shared_command_job_running(source='web'):
        state['running'] = False
        state['result'] = state.get('result') or 'Команда прервана или сервис был перезапущен до записи результата.'
        state['progress_label'] = ''
        state['finished_at'] = time.time()
        _write_web_command_state_file(state)
    with web_command_lock:
        web_command_state.update(state)
    return _command_state_snapshot(web_command_lock, web_command_state)


def _consume_web_command_state_for_render():
    _get_web_command_state()
    consumed = _consume_command_state_for_render_impl(web_command_lock, web_command_state)
    _write_web_command_state_file(_command_state_snapshot(web_command_lock, web_command_state))
    return consumed


def _estimate_web_command_progress(command, result_text):
    return _estimate_update_progress(command, result_text, WEB_UPDATE_COMMANDS)


def _set_web_command_progress(command, result_text):
    _set_command_progress_state(
        web_command_lock,
        web_command_state,
        command,
        result_text,
        _estimate_web_command_progress,
    )
    _write_web_command_state_file(_command_state_snapshot(web_command_lock, web_command_state))


def _set_web_flash_message(message):
    _set_flash_message_impl(web_flash_lock, web_flash_state, message)


def _consume_web_flash_message():
    return _consume_flash_message_impl(web_flash_lock, web_flash_state)


def _finish_web_command(command, result):
    _finish_command_state(
        web_command_lock,
        web_command_state,
        command,
        result,
        _web_command_label,
        update_commands=WEB_UPDATE_COMMANDS,
        finished_progress_label='Завершено',
    )
    _write_web_command_state_file(_command_state_snapshot(web_command_lock, web_command_state))
    job_state = _read_json_file(TELEGRAM_COMMAND_JOB_FILE, {}) or {}
    if job_state.get('source') == 'web':
        _remove_file(TELEGRAM_COMMAND_JOB_FILE)


def _execute_web_command(command):
    try:
        result = _run_web_command(command)
    except Exception as exc:
        result = f'Ошибка выполнения команды: {exc}'
    _finish_web_command(command, result)


def _run_web_command_worker(command):
    with web_command_lock:
        web_command_state.update(_read_web_command_state_file())
    _execute_web_command(command)


def _start_web_command_legacy(command):
    return _start_command_state(
        web_command_lock,
        web_command_state,
        command,
        _web_command_label,
        _execute_web_command,
        update_commands=WEB_UPDATE_COMMANDS,
        initial_progress_label='Подготовка запуска обновления',
        already_running_message=lambda current_label: (
            f'⏳ Уже выполняется команда: {current_label}. Дождитесь завершения текущего запуска.'
        ),
        started_message=lambda label: (
            f'⏳ Команда "{label}" запущена. Статус обновится без перезагрузки страницы.'
        ),
    )


def _start_web_command(command):
    label = _web_command_label(command)
    job_state = _read_json_file(TELEGRAM_COMMAND_JOB_FILE, {}) or {}
    if _shared_command_job_running(job_state):
        current_label = 'служебная команда Telegram'
        if job_state.get('source') == 'web':
            current_label = _web_command_label(job_state.get('command') or command)
        return False, f'⏳ Уже выполняется команда: {current_label}. Дождитесь завершения текущего запуска.'

    state = _web_command_state_defaults()
    state.update({
        'running': True,
        'command': command,
        'label': label,
        'progress': 5 if command in WEB_UPDATE_COMMANDS else 0,
        'progress_label': 'Подготовка запуска обновления' if command in WEB_UPDATE_COMMANDS else '',
        'started_at': time.time(),
        'finished_at': 0,
    })
    with web_command_lock:
        web_command_state.update(state)
    _write_web_command_state_file(state)
    _write_json_file(TELEGRAM_COMMAND_JOB_FILE, {
        'running': True,
        'source': 'web',
        'command': command,
        'started_at': state['started_at'],
    })
    subprocess.Popen(
        [sys.executable, '-c', _web_background_command_code(command)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
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


def _parse_trojan_key(key):
    return _store_parse_trojan_key(key)


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


POOL_PROTOCOL_ORDER = key_pool_web.POOL_PROTOCOL_ORDER
# Telegram прокручивает reply-клавиатуру целиком, без закрепления нижних строк.
# Поэтому показываем весь пул в одной прокручиваемой клавиатуре, а служебные
# кнопки добавляем после списка ключей.
POOL_PAGE_SIZE = telegram_pool_ui.POOL_PAGE_SIZE


def _pool_proto_label(proto):
    return key_pool_web.pool_proto_label(proto)


def _pool_proto_from_button_prefix(prefix):
    return telegram_pool_ui.pool_proto_from_button_prefix(prefix)
def _pool_protocol_markup():
    return telegram_pool_ui.pool_protocol_markup(types, [_pool_proto_label(proto) for proto in POOL_PROTOCOL_ORDER])
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
    for proto, label in key_pool_web.POOL_PROTOCOL_LABELS.items():
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
    current_keys = _load_current_keys()
    current_key = current_keys.get(proto)
    cache = _load_key_probe_cache()
    labels = []
    for offset, key_value in enumerate(info['keys'][info['start']:info['end']], start=info['start'] + 1):
        probe = cache.get(_hash_key(key_value), {})
        labels.append(_pool_key_button_label(offset, key_value, probe=probe, current_key=current_key, proto=proto))
    return telegram_pool_ui.pool_action_markup(types, labels, info)
def _pool_delete_markup(proto, page=0):
    _, info = _format_pool_page(proto, page)
    current_keys = _load_current_keys()
    current_key = current_keys.get(proto)
    cache = _load_key_probe_cache()
    labels = []
    for offset, key_value in enumerate(info['keys'][info['start']:info['end']], start=info['start'] + 1):
        probe = cache.get(_hash_key(key_value), {})
        labels.append(_pool_key_button_label(offset, key_value, probe=probe, current_key=current_key, proto=proto, action='delete'))
    return telegram_pool_ui.pool_delete_markup(types, labels, info)
def _pool_clear_confirm_markup():
    return telegram_pool_ui.pool_clear_confirm_markup(types)
def _pool_input_markup():
    return telegram_pool_ui.pool_input_markup(types)
def _pool_key_button_label(index, key_value, probe=None, current_key=None, proto=None, action='apply'):
    return telegram_pool_ui.pool_key_button_label(
        index,
        key_value,
        probe=probe,
        current_key=current_key,
        proto=proto,
        action=action,
        display_name=_pool_key_display_name,
    )
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


def _pool_status_summary(current_keys=None, key_pools=None, key_probe_cache=None, custom_checks=None):
    current_keys = current_keys if current_keys is not None else _load_current_keys()
    key_pools = key_pools if key_pools is not None else _ensure_current_keys_in_pools(current_keys)
    key_probe_cache = key_probe_cache if key_probe_cache is not None else _load_key_probe_cache()
    custom_checks = custom_checks if custom_checks is not None else _load_custom_checks()
    return key_pool_web.pool_status_summary(
        current_keys,
        key_pools,
        key_probe_cache,
        custom_checks,
        _hash_key,
    )
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


def _show_pool_protocol_menu(message, set_menu_state, clear_inline=True):
    set_menu_state(20, None)
    if clear_inline:
        _clear_pool_inline_keyboard(message.chat.id)
    _clear_pool_page(message.chat.id)
    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())


def _return_to_key_menu_from_pool(message, set_menu_state):
    set_menu_state(8, None)
    _clear_pool_page(message.chat.id)
    bot.send_message(message.chat.id, '🔑 Ключи', reply_markup=_build_keys_menu_markup())


def _pool_state_proto_or_menu(message, bypass, set_menu_state, clear_inline=True):
    proto = _resolve_pool_protocol(bypass)
    if not proto:
        _show_pool_protocol_menu(message, set_menu_state, clear_inline=clear_inline)
    return proto


def _return_to_pool_page(message, set_menu_state, proto, page=None, prefix=None):
    set_menu_state(21)
    _send_pool_page(message.chat.id, proto, page=_get_pool_page(message.chat.id) if page is None else page, prefix=prefix)


def _handle_pool_protocol_state(message, set_menu_state):
    if message.text == '🔙 В меню ключей':
        _return_to_key_menu_from_pool(message, set_menu_state)
        return True
    proto = _resolve_pool_protocol(message.text)
    if not proto:
        bot.send_message(message.chat.id, 'Выберите протокол кнопкой внизу.', reply_markup=_pool_protocol_markup())
        return True
    set_menu_state(21, proto)
    _send_pool_page(message.chat.id, proto, page=0)
    return True


def _send_pool_input_prompt(chat_id, proto, prompt):
    bot.send_message(chat_id, prompt.format(proto_label=_pool_proto_label(proto)), reply_markup=_pool_input_markup())


def _pool_probe_start_result(proto, *, mention_proto=True):
    started, queued = _probe_pool_keys_background(proto, _pool_keys_for_proto(proto), stale_only=False)
    if started:
        target = f'пула {_pool_proto_label(proto)}' if mention_proto else 'пула'
        return started, queued, (
            f'Запущена безопасная фоновая проверка {target}. В очереди: {queued}. '
            'Ключи проверяются по одному с паузой, чтобы не перегружать память роутера.'
        )
    if queued:
        return started, queued, 'Проверка пула уже выполняется. Дождитесь обновления статусов.'
    return started, queued, 'В пуле нет ключей для проверки.'


def _handle_pool_action_button(message, proto, page, set_menu_state):
    selection = _pool_reply_selection(
        message,
        proto,
        page,
        set_menu_state,
        21,
        _pool_action_markup,
        'Эта кнопка пула устарела и не содержит протокол. Откройте пул заново и нажмите кнопку вида V1/V2/VM/TR/SS.',
    )
    if not selection:
        return False
    if selection['handled']:
        return True
    action = selection['action']
    raw_index = selection['raw_index']
    proto = selection['proto']
    page = selection['page']
    if action == 'delete':
        bot.send_message(
            message.chat.id,
            'Удаление доступно только через кнопку «🗑 Удаление». Это защищает от случайного нажатия старой кнопки.',
            reply_markup=_pool_action_markup(proto, page),
        )
        return True
    try:
        index, key_value = _pool_key_by_index(proto, raw_index)
    except Exception as exc:
        bot.send_message(message.chat.id, f'Ошибка выбора ключа: {exc}', reply_markup=_pool_action_markup(proto, page))
        return True
    if action == 'apply':
        bot.send_message(
            message.chat.id,
            f'Применяю ключ #{index} для {_pool_proto_label(proto)}. Это может занять до 30 секунд.',
            reply_markup=_pool_action_markup(proto, page),
        )
        _apply_pool_key_background(message.chat.id, proto, key_value, index, page=page)
        return True
    try:
        _delete_pool_key(proto, key_value)
        _send_pool_page(message.chat.id, proto, page=page, prefix=f'Ключ #{index} удалён из пула {_pool_proto_label(proto)}.')
    except Exception as exc:
        bot.send_message(message.chat.id, f'Ошибка удаления ключа из пула: {exc}', reply_markup=_pool_action_markup(proto, page))
    return True


def _handle_pool_manage_state(message, bypass, set_menu_state):
    proto = _pool_state_proto_or_menu(message, bypass, set_menu_state)
    if not proto:
        return True
    page = _get_pool_page(message.chat.id)
    if message.text == '🔙 В меню ключей':
        _return_to_key_menu_from_pool(message, set_menu_state)
        return True
    selected_proto = _resolve_pool_protocol(message.text)
    if selected_proto:
        set_menu_state(21, selected_proto)
        _send_pool_page(message.chat.id, selected_proto, page=0)
        return True
    if message.text == '🔙 К выбору протокола':
        _show_pool_protocol_menu(message, set_menu_state)
        return True
    page_delta = _pool_reply_page_delta(message.text)
    if page_delta:
        _send_pool_page(message.chat.id, proto, page=page + page_delta)
        return True
    if _is_pool_page_noop(message.text) or message.text in ('📋 Показать пул', '🔄 Обновить пул', '🔙 К пулу'):
        _send_pool_page(message.chat.id, proto, page=page)
        return True
    if _handle_pool_action_button(message, proto, page, set_menu_state):
        return True
    if message.text == '➕ Добавить ключи':
        set_menu_state(22)
        _send_pool_input_prompt(
            message.chat.id,
            proto,
            'Отправьте один или несколько ключей для пула {proto_label}. Каждый ключ с новой строки.',
        )
        return True
    if message.text == '🔗 Загрузить subscription':
        set_menu_state(23)
        _send_pool_input_prompt(message.chat.id, proto, 'Отправьте subscription URL для пула {proto_label}.')
        return True
    if message.text == '✅ Применить ключ':
        bot.send_message(message.chat.id, 'Используйте нижние кнопки ✅ с номером нужного ключа.', reply_markup=_pool_action_markup(proto, page))
        return True
    if message.text == '🗑 Удалить ключ':
        bot.send_message(message.chat.id, 'Используйте нижние кнопки ✕ с номером нужного ключа.', reply_markup=_pool_action_markup(proto, page))
        return True
    if message.text == '🗑 Удаление':
        set_menu_state(25)
        bot.send_message(
            message.chat.id,
            f'Выберите ключ для удаления из пула {_pool_proto_label(proto)}. Активный ключ удалить можно, но режим бота останется прежним до применения другого ключа.',
            reply_markup=_pool_delete_markup(proto, page),
        )
        return True
    if message.text == '🧹 Очистить пул':
        set_menu_state(26)
        bot.send_message(message.chat.id, f'Очистить весь пул {_pool_proto_label(proto)}? Это удалит все ключи из пула.', reply_markup=_pool_clear_confirm_markup())
        return True
    if message.text in ['🔍 Проверить пул', '🔍 Проверить активный']:
        _started, _queued, prefix = _pool_probe_start_result(proto, mention_proto=True)
        _send_pool_page(message.chat.id, proto, page=page, prefix=prefix)
        return True
    bot.send_message(message.chat.id, 'Выберите действие кнопкой внизу.', reply_markup=_pool_action_markup(proto, page))
    return True


def _handle_pool_add_state(message, bypass, set_menu_state):
    proto = _pool_state_proto_or_menu(message, bypass, set_menu_state)
    if not proto:
        return True
    if message.text == '🔙 К пулу':
        _return_to_pool_page(message, set_menu_state, proto)
        return True
    added = _add_keys_to_pool(proto, message.text)
    _return_to_pool_page(message, set_menu_state, proto, prefix=f'Добавлено ключей в пул {_pool_proto_label(proto)}: {added}')
    return True


def _handle_pool_subscription_state(message, bypass, set_menu_state):
    proto = _pool_state_proto_or_menu(message, bypass, set_menu_state)
    if not proto:
        return True
    if message.text == '🔙 К пулу':
        _return_to_pool_page(message, set_menu_state, proto)
        return True
    try:
        fetched, error = _fetch_keys_from_subscription(message.text.strip())
        if error:
            raise ValueError(error)
        source_proto = 'vless' if proto == 'vless2' else proto
        added = _add_keys_to_pool(proto, '\n'.join(fetched.get(source_proto, []) or []))
        result = f'Загружено из subscription в пул {_pool_proto_label(proto)}: {added} новых ключей.'
    except Exception as exc:
        result = f'Ошибка загрузки subscription: {exc}'
    _return_to_pool_page(message, set_menu_state, proto, prefix=result)
    return True


def _handle_pool_clear_state(message, bypass, set_menu_state):
    proto = _pool_state_proto_or_menu(message, bypass, set_menu_state, clear_inline=False)
    if not proto:
        return True
    page = _get_pool_page(message.chat.id)
    if message.text == '✅ Очистить пул':
        removed = _clear_pool(proto)
        _return_to_pool_page(message, set_menu_state, proto, page=page, prefix=f'Пул {_pool_proto_label(proto)} очищен. Удалено ключей: {removed}.')
        return True
    if message.text in ('Отмена', '🔙 К пулу'):
        _return_to_pool_page(message, set_menu_state, proto, page=page, prefix='Очистка пула отменена.')
        return True
    bot.send_message(message.chat.id, 'Подтвердите очистку или нажмите отмену.', reply_markup=_pool_clear_confirm_markup())
    return True


def _handle_pool_apply_state(message, bypass, set_menu_state):
    proto = _pool_state_proto_or_menu(message, bypass, set_menu_state)
    if not proto:
        return True
    try:
        index, key_value = _pool_key_by_index(proto, message.text)
        result = f'Ключ #{index} применён для {_pool_proto_label(proto)}.\n{_apply_pool_key(proto, key_value)}'
    except Exception as exc:
        result = f'Ошибка применения ключа из пула: {exc}'
    set_menu_state(21)
    _send_pool_page(message.chat.id, proto, prefix=result)
    return True


def _handle_pool_delete_state(message, bypass, set_menu_state):
    proto = _pool_state_proto_or_menu(message, bypass, set_menu_state)
    if not proto:
        return True
    page = _get_pool_page(message.chat.id)
    if message.text in ('🔙 К пулу', '🔙 Назад'):
        _return_to_pool_page(message, set_menu_state, proto, page=page)
        return True
    page_delta = _pool_reply_page_delta(message.text)
    if page_delta:
        set_menu_state(25)
        _send_pool_delete_page(message.chat.id, proto, page=page + page_delta, prefix='Режим удаления: выберите ключ кнопкой ниже.')
        return True
    if _is_pool_page_noop(message.text):
        _send_pool_delete_page(message.chat.id, proto, page=page)
        return True
    selection = _pool_reply_selection(
        message,
        proto,
        page,
        set_menu_state,
        25,
        _pool_delete_markup,
        'Эта кнопка пула устарела и не содержит протокол. Откройте пул заново и нажмите кнопку удаления вида ✕ V1/V2/VM/TR/SS.',
    )
    if not selection:
        bot.send_message(message.chat.id, 'Выберите ключ для удаления кнопкой с кодом протокола V1/V2/VM/TR/SS.', reply_markup=_pool_delete_markup(proto, page))
        return True
    if selection['handled']:
        return True
    action = selection['action']
    raw_index = selection['raw_index']
    proto = selection['proto']
    page = selection['page']
    if action != 'delete':
        bot.send_message(message.chat.id, 'Сейчас включен режим удаления. Нажмите кнопку ключа с префиксом ✕ или вернитесь к пулу.', reply_markup=_pool_delete_markup(proto, page))
        return True
    try:
        index, key_value = _pool_key_by_index(proto, raw_index)
        _delete_pool_key(proto, key_value)
        result = f'Ключ #{index} удалён из пула {_pool_proto_label(proto)}.'
    except Exception as exc:
        result = f'Ошибка удаления ключа из пула: {exc}'
    _return_to_pool_page(message, set_menu_state, proto, page=page, prefix=result)
    return True


def _handle_telegram_pool_state(message, level, bypass, set_menu_state):
    if not _app_mode_pool_enabled():
        return False
    handlers = {
        20: lambda: _handle_pool_protocol_state(message, set_menu_state),
        21: lambda: _handle_pool_manage_state(message, bypass, set_menu_state),
        22: lambda: _handle_pool_add_state(message, bypass, set_menu_state),
        23: lambda: _handle_pool_subscription_state(message, bypass, set_menu_state),
        24: lambda: _handle_pool_apply_state(message, bypass, set_menu_state),
        25: lambda: _handle_pool_delete_state(message, bypass, set_menu_state),
        26: lambda: _handle_pool_clear_state(message, bypass, set_menu_state),
    }
    handler = handlers.get(level)
    return handler() if handler else False


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


def _pool_reply_selection(message, proto, page, set_menu_state, state_level, markup_builder, stale_message):
    action, raw_index, button_proto = _pool_reply_key_action(message.text)
    if not action:
        return None
    if action == 'legacy' or not button_proto:
        bot.send_message(message.chat.id, stale_message, reply_markup=markup_builder(proto, page))
        return {'handled': True}
    if button_proto != proto:
        proto = button_proto
        page = 0
        set_menu_state(state_level, proto)
    return {
        'handled': False,
        'action': action,
        'raw_index': raw_index,
        'proto': proto,
        'page': page,
    }


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


def _v2ray_key_file_candidates(file_path):
    return _store_v2ray_key_file_candidates(file_path, XRAY_CONFIG_DIR, V2RAY_CONFIG_DIR)


def _remove_file_if_exists(file_path):
    _store_remove_file_if_exists(file_path, logger=_write_runtime_log)


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
    with key_pool_lock:
        pools, removed = key_pool_store.delete_pool_key(key_pool_store.load_key_pools(KEY_POOLS_PATH), proto, key_value)
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
        key_pool_store.save_key_pools(KEY_POOLS_PATH, pools)
    _forget_key_probes([key_value])
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()


def _clear_pool(proto):
    with key_pool_lock:
        pools, removed_keys = key_pool_store.clear_pool(key_pool_store.load_key_pools(KEY_POOLS_PATH), proto)
        key_pool_store.save_key_pools(KEY_POOLS_PATH, pools)
        current_key = (_load_current_keys().get(proto) or '').strip()
        if current_key and current_key in removed_keys:
            _clear_installed_key_for_protocol(proto)
    if removed_keys:
        _forget_key_probes(removed_keys)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return len(removed_keys)


def _proxy_config_snapshot_paths():
    return _store_proxy_config_snapshot_paths(CORE_PROXY_CONFIG_PATH, VMESS_KEY_PATH, VLESS_KEY_PATH, VLESS2_KEY_PATH)


def _snapshot_proxy_config_files():
    return _store_snapshot_proxy_config_files(_proxy_config_snapshot_paths(), logger=_write_runtime_log)


def _restore_proxy_config_files(snapshot):
    _store_restore_proxy_config_files(snapshot, logger=_write_runtime_log)


def _restart_proxy_services_for_protocols(protocols):
    commands = []
    if 'shadowsocks' in protocols:
        commands.append('/opt/etc/init.d/S22shadowsocks restart')
    if protocols:
        commands.append(CORE_PROXY_SERVICE_SCRIPT + ' restart')
    if 'trojan' in protocols:
        commands.append('/opt/etc/init.d/S22trojan restart')
    for command in dict.fromkeys(commands):
        os.system(command)
    if commands:
        time.sleep(3)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()


def _set_pool_probe_progress(**updates):
    pool_probe_progress.update(**updates)


def _get_pool_probe_progress():
    return pool_probe_progress.snapshot()


def _pool_probe_progress_label(progress=None):
    return _controller_pool_probe_progress_label(progress or _get_pool_probe_progress())


def _pool_probe_timeout_budget(custom_checks=None, task_count=1, workers=1):
    return _controller_pool_probe_timeout_budget(custom_checks, task_count, workers, POOL_PROBE_TIMEOUTS)


def _check_pool_key_through_proxy(proto, key_value, custom_checks=None, proxy_url=None):
    return _controller_check_pool_key_through_proxy(
        proto,
        key_value,
        custom_checks,
        proxy_url or proxy_settings.get(proto),
        check_telegram_api=_check_telegram_api_through_proxy,
        check_http=_check_http_through_proxy,
        record_key_probe=_record_key_probe,
        probe_custom_targets=_probe_custom_targets_for_pool,
        retry_delay_seconds=POOL_PROBE_RETRY_DELAY_SECONDS,
        telegram_timeouts=(POOL_PROBE_TG_CONNECT_TIMEOUT, POOL_PROBE_TG_READ_TIMEOUT),
        http_timeouts=(POOL_PROBE_HTTP_CONNECT_TIMEOUT, POOL_PROBE_HTTP_READ_TIMEOUT),
    )


def _proxy_outbound_from_key(proto, key_value, tag, email='t@t.tt'):
    return _store_proxy_outbound_from_key(proto, key_value, tag, email=email)


def _find_pool_failover_candidate(candidates, service='telegram'):
    """Find one working pool key through a temporary xray before touching the active proxy."""
    return _runner_find_pool_failover_candidate(
        candidates,
        service=service,
        batch_size=POOL_PROBE_BATCH_SIZE,
        test_port=POOL_FAILOVER_TEST_PORT,
        proxy_outbound_from_key=_proxy_outbound_from_key,
        wait_for_socks5=_wait_for_socks5_handshake,
        check_telegram_api=_check_telegram_api_through_proxy,
        check_http=_check_http_through_proxy,
        record_key_probe=_record_key_probe,
        proto_label=_pool_proto_label,
        log=_write_runtime_log,
        telegram_timeouts=(POOL_PROBE_TG_CONNECT_TIMEOUT, POOL_PROBE_TG_READ_TIMEOUT),
        http_timeouts=(POOL_PROBE_HTTP_CONNECT_TIMEOUT, POOL_PROBE_HTTP_READ_TIMEOUT),
    )


def _select_pool_probe_tasks(tasks, max_keys=None, stale_only=False):
    custom_checks = _load_custom_checks()
    return _controller_select_pool_probe_tasks(
        tasks,
        protocol_order=POOL_PROTOCOL_ORDER,
        custom_checks=custom_checks,
        cache=_load_key_probe_cache() if stale_only else {},
        hash_key=_hash_key,
        is_fresh=_key_probe_is_fresh,
        max_keys=max_keys,
        stale_only=stale_only,
    )


def _invalidate_probe_status_caches():
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()


def _run_selected_pool_probe(probe_tasks, checks, set_checked, invalidate_caches):
    probe_recorder = _KeyProbeBatchRecorder(
        flush_every=POOL_PROBE_CACHE_FLUSH_EVERY,
        flush_interval=POOL_PROBE_CACHE_FLUSH_INTERVAL,
    )
    try:
        return run_pool_probe_worker(
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
            set_checked=set_checked,
            validate_outbound=lambda proto, key_value: _runner_pool_probe_outbound(
                proto,
                key_value,
                'proxy-pool-probe-validate',
                _proxy_outbound_from_key,
            ),
            failed_custom_results=_failed_custom_probe_results,
            record_key_probe=probe_recorder.record,
            start_xray_for_batch=lambda valid_batch: _runner_start_pool_probe_xray(
                _runner_build_pool_probe_core_config_batch(valid_batch, POOL_PROBE_TEST_PORT, _proxy_outbound_from_key)
            ),
            wait_for_socks5=_wait_for_socks5_handshake,
            check_pool_key=_check_pool_key_through_proxy,
            timeout_budget=_pool_probe_timeout_budget,
            stop_xray=_runner_stop_pool_probe_xray,
            cleanup_runtime=_runner_cleanup_pool_probe_runtime,
            invalidate_caches=invalidate_caches,
        )
    finally:
        probe_recorder.flush()


def _queue_pool_key_probe(tasks, max_keys=None, stale_only=False, scope='manual'):
    selected, custom_checks = _select_pool_probe_tasks(
        tasks,
        max_keys=max_keys,
        stale_only=stale_only,
    )
    if POOL_PROBE_ACTIVE_ONLY:
        selected = _controller_filter_active_probe_tasks(selected, _load_current_keys())
    return start_pool_probe_worker(
        selected,
        custom_checks,
        scope=scope,
        lock=pool_probe_lock,
        set_progress=_set_pool_probe_progress,
        run_worker=_run_selected_pool_probe,
        invalidate_caches=_invalidate_probe_status_caches,
    )


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
    with key_pool_lock:
        pools, added_keys = key_pool_store.add_keys_to_pool(key_pool_store.load_key_pools(KEY_POOLS_PATH), proto, keys_text)
        key_pool_store.save_key_pools(KEY_POOLS_PATH, pools)
    _probe_pool_keys_background(proto, added_keys)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return len(added_keys)


def _add_subscription_keys_to_pool(proto, fetched_keys):
    with key_pool_lock:
        pools, added_keys = key_pool_store.add_subscription_keys_to_pool(
            key_pool_store.load_key_pools(KEY_POOLS_PATH),
            proto,
            fetched_keys,
        )
        key_pool_store.save_key_pools(KEY_POOLS_PATH, pools)
    if added_keys:
        _probe_pool_keys_background(proto, added_keys)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return pools, added_keys


def _web_custom_checks():
    return key_pool_web.web_custom_checks(_load_custom_checks())

def _web_pool_snapshot(current_keys=None, include_keys=False):
    current_keys = current_keys if current_keys is not None else _load_current_keys()
    return key_pool_web.web_pool_snapshot(
        current_keys,
        _ensure_current_keys_in_pools(current_keys),
        _load_key_probe_cache(),
        _load_custom_checks(),
        include_keys=include_keys,
        hash_key=_hash_key,
        display_name=_pool_key_display_name,
        probe_state=key_pool_web.web_probe_state,
        probe_checked_at=key_pool_web.web_probe_checked_at,
    )


def _check_local_proxy_endpoint(key_type, port):
    if key_type in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
        if _wait_for_socks5_handshake(port, timeout=3):
            return True, f'Локальный SOCKS-порт 127.0.0.1:{port} отвечает как SOCKS5.'
        if _port_is_listening(port):
            return False, f'Локальный порт 127.0.0.1:{port} открыт, но не отвечает как SOCKS5.'
        return False, f'Локальный порт 127.0.0.1:{port} недоступен.'
    return True, ''


def _proxy_apply_settings():
    return _runtime_proxy_apply_settings(
        CORE_PROXY_SERVICE_SCRIPT,
        PROXY_LOCAL_PORTS,
    )


def _apply_installed_proxy(key_type, key_value, verify=True):
    return _runtime_apply_installed_proxy(
        key_type,
        key_value,
        settings=_proxy_apply_settings(),
        app_mode_noun=APP_MODE_NOUN,
        load_proxy_mode=_load_proxy_mode,
        proxy_mode_label=_proxy_mode_label,
        proxy_url_getter=lambda proto: proxy_settings.get(proto),
        build_diagnostics=_build_proxy_diagnostics,
        ensure_service_port=_ensure_service_port,
        check_local_endpoint=_check_local_proxy_endpoint,
        check_telegram_api=_check_telegram_api_through_proxy,
        check_http=_check_http_through_proxy,
        record_key_probe=_record_key_probe,
        verify=verify,
    )


def update_proxy(proxy_type, persist=True):
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
    _reset_telegram_http_session(f'proxy={proxy_type}')

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
    return _status_is_transient_text(status_text)


def _telegram_state_label():
    if not _app_mode_telegram_enabled():
        return 'Web only: Telegram-бот отключен'
    return 'polling активен' if bot_polling else ('ожидает запуска' if not bot_ready else 'процесс запущен, polling недоступен')


def _build_web_status(current_keys, protocols=None):
    state_label = _telegram_state_label()
    return web_status_runtime.build_web_status_snapshot(
        state_label=state_label,
        proxy_mode=proxy_mode,
        protocols=protocols,
        ports=PROXY_LOCAL_PORTS,
        check_socks5=_check_socks5_handshake,
        check_telegram_api=check_telegram_api,
        is_transient=_is_transient_telegram_api_failure,
        fallback_reason=_last_proxy_disable_reason(),
    )


def _status_snapshot_signature(current_keys):
    return _status_snapshot_signature_impl(current_keys, _load_custom_checks())


def _build_status_snapshot(current_keys, force_refresh=False):
    signature = _status_snapshot_signature(current_keys)
    now = time.time()
    if pool_probe_lock.locked():
        return _active_mode_status_snapshot(current_keys)
    cached = None if force_refresh else _status_cached_snapshot(status_snapshot_cache, signature, STATUS_CACHE_TTL, now=now)
    if cached is not None:
        return cached

    custom_checks = _load_custom_checks()
    key_probe_cache = _load_key_probe_cache()
    protocols = {}
    for key_name, key_value in current_keys.items():
        try:
            if key_name == proxy_mode:
                protocols[key_name] = _protocol_status_for_key(key_name, key_value)
                _store_active_mode_protocol_status(current_keys, protocols[key_name])
            else:
                protocols[key_name] = _cached_protocol_status_for_key(
                    key_name,
                    key_value,
                    custom_checks=custom_checks,
                    key_probe_cache=key_probe_cache,
                )
        except Exception as exc:
            _write_runtime_log(f'Ошибка проверки ключа {key_name}: {exc}')
            protocols[key_name] = _status_protocol_error(exc)

    snapshot = {
        'web': _build_web_status(current_keys, protocols=protocols),
        'protocols': protocols,
    }
    return _status_store_snapshot(status_snapshot_cache, signature, snapshot, now=now)


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
    return _status_cached_snapshot(
        status_snapshot_cache,
        _status_snapshot_signature(current_keys),
        STATUS_CACHE_TTL,
    )


def _active_mode_status_signature(current_keys):
    return _status_active_mode_signature(proxy_mode, current_keys, _load_custom_checks())


def _cached_active_mode_protocol_status(current_keys):
    return _status_cached_active_status(
        active_mode_status_cache,
        _active_mode_status_signature(current_keys),
        ACTIVE_MODE_STATUS_DURING_POOL_TTL,
        active_mode_status_cache_lock,
    )


def _store_active_mode_protocol_status(current_keys, status):
    _status_store_active_status(
        active_mode_status_cache,
        _active_mode_status_signature(current_keys),
        status,
        active_mode_status_cache_lock,
    )


def _placeholder_web_status_snapshot():
    return {
        'state_label': _telegram_state_label(),
        'proxy_mode': proxy_mode,
        'api_status': '⏳ Проверяется связь текущего режима. Статус обновится без перезагрузки страницы.',
        'socks_details': '',
        'fallback_reason': _last_proxy_disable_reason(),
    }


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


def _probe_all_pool_keys_async(stale_only=True, max_keys=KEY_PROBE_MAX_PER_RUN, scope='manual_all'):
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
    return _queue_pool_key_probe(tasks, max_keys=max_keys, stale_only=stale_only, scope=scope)


def _authorize_callback(call, handler_name):
    return _authorize_message(_telegram_callback_as_message(call), handler_name)


def _pool_callback_parts(call):
    data = (call.data or '').split(':')
    return data, data[1] if len(data) > 1 else '', call.message.chat.id, call.message.message_id


def _pool_callback_protocol(data):
    if len(data) < 3:
        raise ValueError('Некорректная команда пула.')
    proto = _resolve_pool_protocol(data[2])
    if not proto:
        raise ValueError('Неизвестный протокол.')
    return proto


def _handle_pool_root_callback(call_id, action, data, chat_id):
    if action == 'protocols':
        _set_chat_menu_state(chat_id, level=20, bypass=None)
        _clear_pool_page(chat_id)
        bot.answer_callback_query(call_id, 'Кнопки перенесены вниз')
        bot.send_message(chat_id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
        return True

    if action == 'keys-menu':
        _set_chat_menu_state(chat_id, level=8, bypass=None)
        _clear_pool_page(chat_id)
        bot.answer_callback_query(call_id, 'Открыто меню ключей')
        bot.send_message(chat_id, '🔑 Ключи', reply_markup=_build_keys_menu_markup())
        return True

    if action == 'select' and len(data) >= 3:
        proto = _pool_callback_protocol(data)
        _set_chat_menu_state(chat_id, level=21, bypass=proto)
        bot.answer_callback_query(call_id, f'Открыт пул {_pool_proto_label(proto)}')
        _send_pool_page(chat_id, proto, page=0)
        return True

    return False


def _handle_pool_key_callback(call_id, action, data, chat_id, proto):
    if action not in ('apply', 'delete') or len(data) < 5:
        return False
    key_id = data[3]
    page = data[4]
    index, key_value = _pool_key_by_callback_id(proto, key_id)
    if action == 'apply':
        bot.answer_callback_query(call_id, f'Применяю ключ #{index}...')
        _set_chat_menu_state(chat_id, level=21, bypass=proto)
        bot.send_message(
            chat_id,
            f'Применяю ключ #{index} для {_pool_proto_label(proto)}. Это может занять до 30 секунд.',
            reply_markup=_pool_action_markup(proto, page),
        )
        _apply_pool_key_background(chat_id, proto, key_value, index, page=page)
        return True

    _delete_pool_key(proto, key_value)
    bot.answer_callback_query(call_id, f'Ключ #{index} удалён')
    _set_chat_menu_state(chat_id, level=21, bypass=proto)
    _send_pool_page(chat_id, proto, page=page, prefix=f'Ключ #{index} удалён из пула {_pool_proto_label(proto)}.')
    return True


def _handle_pool_protocol_callback(call_id, action, data, chat_id, proto):
    page = data[3] if len(data) > 3 else 0
    if action == 'page':
        _set_chat_menu_state(chat_id, level=21, bypass=proto)
        bot.answer_callback_query(call_id)
        _send_pool_page(chat_id, proto, page=page)
        return True

    if action == 'add':
        _set_chat_menu_state(chat_id, level=22, bypass=proto)
        bot.answer_callback_query(call_id)
        _send_pool_input_prompt(
            chat_id,
            proto,
            'Отправьте один или несколько ключей для пула {proto_label}. Каждый ключ с новой строки.',
        )
        return True

    if action == 'subscribe':
        _set_chat_menu_state(chat_id, level=23, bypass=proto)
        bot.answer_callback_query(call_id)
        _send_pool_input_prompt(chat_id, proto, 'Отправьте subscription URL для пула {proto_label}.')
        return True

    if action == 'probe':
        started, queued, prefix = _pool_probe_start_result(proto, mention_proto=False)
        answer = 'Проверка запущена' if started else ('Проверка уже выполняется' if queued else 'В пуле нет ключей')
        bot.answer_callback_query(call_id, answer)
        _set_chat_menu_state(chat_id, level=21, bypass=proto)
        _send_pool_page(chat_id, proto, page=page, prefix=prefix)
        return True

    if action == 'clear-confirm':
        _set_chat_menu_state(chat_id, level=26, bypass=proto)
        _set_pool_page(chat_id, page)
        bot.answer_callback_query(call_id)
        bot.send_message(
            chat_id,
            f'Очистить весь пул {_pool_proto_label(proto)}? Это удалит все ключи из пула.',
            reply_markup=_pool_clear_confirm_markup(),
        )
        return True

    if action == 'clear':
        removed = _clear_pool(proto)
        bot.answer_callback_query(call_id, 'Пул очищен')
        _set_chat_menu_state(chat_id, level=21, bypass=proto)
        _send_pool_page(chat_id, proto, page=page, prefix=f'Пул {_pool_proto_label(proto)} очищен. Удалено ключей: {removed}.')
        return True

    return _handle_pool_key_callback(call_id, action, data, chat_id, proto)


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
        if not _app_mode_pool_enabled():
            bot.answer_callback_query(call.id, 'Пул ключей отключен в простом режиме', show_alert=True)
            return

        data, action, chat_id, message_id = _pool_callback_parts(call)
        _clear_pool_inline_keyboard(chat_id, message_id)

        if _handle_pool_root_callback(call.id, action, data, chat_id):
            return

        proto = _pool_callback_protocol(data)
        if _handle_pool_protocol_callback(call.id, action, data, chat_id, proto):
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

        main = _build_main_menu_markup()
        service = _build_service_menu_markup()

        if not _telegram_is_private_message(message):
            return

        if _handle_private_stateless_command(message, main, service):
            return

        menu_session = _telegram_private_menu_session(
            message,
            _get_chat_menu_state,
            _set_chat_menu_state,
            unset_marker=MENU_STATE_UNSET,
        )
        if _telegram_run_handlers(
            lambda: _handle_common_telegram_menu_message(
                message, menu_session.level, menu_session.bypass, menu_session.set, main, service
            ),
            lambda: _handle_service_request_menu(message, menu_session.level, menu_session.bypass, menu_session.set),
            lambda: _handle_back_to_main_message(message, menu_session.set, main),
            lambda: _handle_unblock_list_state(message, menu_session.level, menu_session.bypass, menu_session.set, main),
            lambda: _handle_service_list_state(message, menu_session.level, menu_session.bypass, menu_session.set),
            lambda: _handle_telegram_pool_state(message, menu_session.level, menu_session.bypass, menu_session.set),
            lambda: _handle_key_menu_message(message, menu_session.level, menu_session.set, main),
            lambda: _handle_install_menu_message(message, menu_session.set),
            lambda: _handle_main_menu_openers(message, menu_session.set),
        ):
            return

    except Exception as error:
        _telegram_recover_private_message_error(
            message,
            error,
            write_log=_write_runtime_log,
            reset_state=lambda chat_id: _set_chat_menu_state(chat_id, level=0, bypass=None),
            send_message=bot.send_message,
            main_markup=_build_main_menu_markup,
        )


def _start_web_bot_action():
    global bot_ready
    if not _app_mode_telegram_enabled():
        bot_ready = False
        _save_bot_autostart(False)
        _invalidate_web_status_cache()
        return 'Сейчас выбран режим Web only. Telegram-бот отключен.'
    bot_ready = True
    _save_bot_autostart(True)
    _invalidate_web_status_cache()
    return APP_START_RESULT


def _web_action_context():
    pool_enabled = _app_mode_pool_enabled()
    context = web_post_actions.base_action_context(
        app_mode_label=APP_MODE_LABEL,
        set_app_runtime_mode=_set_app_runtime_mode,
        update_proxy=update_proxy,
        proxy_mode_label=_proxy_mode_label,
        invalidate_web_status_cache=_invalidate_web_status_cache,
        invalidate_key_status_cache=_invalidate_key_status_cache,
        start_bot=_start_web_bot_action,
        start_web_command=_start_web_command,
        get_web_command_state=_get_web_command_state,
        save_unblock_list=_save_unblock_list,
        read_text_file=_read_text_file,
        append_socialnet_list=_append_socialnet_list,
        remove_socialnet_list=_remove_socialnet_list,
        append_service_error='Ошибка добавления сервисов',
        remove_service_error='Ошибка удаления сервисов',
        socialnet_all_key=SOCIALNET_ALL_KEY,
        normalize_unblock_route_name=_normalize_unblock_route_name,
        install_key_for_protocol=_install_key_for_protocol,
        install_verify=False,
    )
    context.update(web_post_actions.pool_action_context(
        append_custom_checks_to_unblock_list=_append_custom_checks_to_unblock_list,
        unblock_route_for_key_type=_unblock_route_for_key_type,
        add_custom_check=_add_custom_check,
        delete_custom_check=_delete_custom_check,
        web_custom_checks=_web_custom_checks,
        load_current_keys=_load_current_keys,
        refresh_status_caches_async=_refresh_status_caches_async,
        web_pool_snapshot=_web_pool_snapshot,
        probe_all_pool_keys_async=_probe_all_pool_keys_async,
        pool_keys_for_proto=_pool_keys_for_proto,
        probe_pool_keys_background=_probe_pool_keys_background,
        add_keys_to_pool=_add_keys_to_pool,
        delete_pool_key=_delete_pool_key,
        load_key_pools=_load_key_pools,
        set_active_key=_set_active_key,
        clear_pool=_clear_pool,
        fetch_keys_from_subscription=_fetch_keys_from_subscription,
        add_subscription_keys_to_pool=key_pool_store.add_subscription_keys_to_pool,
        add_subscription_keys_to_pool_saved=_add_subscription_keys_to_pool,
        save_key_pools=_save_key_pools,
        pool_apply_lock=pool_apply_lock,
        custom_checks_enabled=pool_enabled,
        pool_actions_enabled=pool_enabled,
    ))
    return context


def _web_get_context(handler):
    pool_enabled = _app_mode_pool_enabled()
    return {
        'build_form': handler._build_form,
        'build_protocol_panel': handler._build_protocol_panel,
        'build_style_asset': handler._build_style_asset,
        'build_script_asset': handler._build_script_asset,
        'consume_flash_message': _consume_web_flash_message,
        'load_current_keys': _load_current_keys,
        'cached_status_snapshot': _cached_status_snapshot,
        'active_mode_status_snapshot': _active_mode_status_snapshot,
        'refresh_status_caches_async': _refresh_status_caches_async,
        'pool_probe_locked': pool_probe_lock.locked,
        'get_status_api_cache': _get_web_status_api_cache,
        'store_status_api_cache': _store_web_status_api_cache,
        'status_api_cache_ttl': WEB_STATUS_API_CACHE_TTL,
        'get_web_command_state': _get_web_command_state,
        'pool_enabled': pool_enabled,
        'get_pool_probe_progress': _get_pool_probe_progress,
        'web_pool_snapshot': _web_pool_snapshot,
        'pool_status_summary': _pool_status_summary,
        'web_custom_checks': _web_custom_checks,
        'time_provider': time.time,
        'static_dir': STATIC_DIR,
        'service_icons_enabled': True,
    }


def _default_web_protocol():
    protocol_keys = [section[0] for section in web_form_blocks.PROTOCOL_SECTIONS]
    if proxy_mode in protocol_keys:
        return proxy_mode
    return protocol_keys[0] if protocol_keys else ''


def _web_protocol_panel_html(protocol, current_keys, protocol_statuses, csrf_input_html):
    protocol_sections = [section for section in web_form_blocks.PROTOCOL_SECTIONS if section[0] == protocol]
    if not protocol_sections:
        raise ValueError('Неизвестный протокол')
    key_pools = _ensure_current_keys_in_pools(current_keys)
    key_probe_cache = _load_key_probe_cache()
    custom_checks = _load_custom_checks()
    custom_checks_html = key_pool_web.web_custom_checks_html(
        custom_checks,
        _service_icon_html,
        csrf_input_html=csrf_input_html,
    )
    custom_presets_html = key_pool_web.web_custom_presets_html(
        custom_checks,
        _custom_check_presets(),
        _service_icon_html,
        csrf_input_html=csrf_input_html,
    )
    pool_table_class, pool_custom_col_width, pool_mobile_custom_col_width = (
        web_pool_form_blocks.pool_table_layout(custom_checks)
    )
    _tabs_html, panel_html = web_pool_form_blocks.render_protocol_tabs_and_panels(
        protocol_sections,
        current_keys,
        protocol_statuses,
        csrf_input_html,
        key_pools=key_pools,
        key_probe_cache=key_probe_cache,
        custom_checks=custom_checks,
        key_display_name=_pool_key_display_name,
        hash_key=_hash_key,
        telegram_icon_html=_telegram_icon_html,
        youtube_icon_html=_youtube_icon_html,
        custom_check_badges=lambda probe, checks: key_pool_web.web_custom_check_badges(probe, checks, _service_icon_html),
        probe_checked_at=key_pool_web.web_probe_checked_at,
        custom_probe_states=key_pool_web.web_custom_probe_states,
        service_icon_html=_service_icon_html,
        pool_table_class=pool_table_class,
        pool_custom_col_width=pool_custom_col_width,
        pool_mobile_custom_col_width=pool_mobile_custom_col_width,
        custom_header_icons=key_pool_web.custom_check_header_icons(custom_checks, _service_icon_html),
        custom_presets_html=custom_presets_html,
        custom_checks_html=custom_checks_html,
        active_protocol=protocol,
    )
    return panel_html


def _web_pool_form_context(current_keys, protocol_statuses, csrf_input_html, status, pool_probe_pending, progress):
    key_pools = _ensure_current_keys_in_pools(current_keys)
    key_probe_cache = _load_key_probe_cache()
    custom_checks = _load_custom_checks()
    custom_checks_html = key_pool_web.web_custom_checks_html(
        custom_checks,
        _service_icon_html,
        csrf_input_html=csrf_input_html,
    )
    custom_presets_html = key_pool_web.web_custom_presets_html(
        custom_checks,
        _custom_check_presets(),
        _service_icon_html,
        csrf_input_html=csrf_input_html,
    )
    pool_table_class, pool_custom_col_width, pool_mobile_custom_col_width = (
        web_pool_form_blocks.pool_table_layout(custom_checks)
    )
    protocol_tabs_html, protocol_panels_html = web_pool_form_blocks.render_protocol_tabs_and_panels(
        web_form_blocks.PROTOCOL_SECTIONS,
        current_keys,
        protocol_statuses,
        csrf_input_html,
        key_pools=key_pools,
        key_probe_cache=key_probe_cache,
        custom_checks=custom_checks,
        key_display_name=_pool_key_display_name,
        hash_key=_hash_key,
        telegram_icon_html=_telegram_icon_html,
        youtube_icon_html=_youtube_icon_html,
        custom_check_badges=lambda probe, checks: key_pool_web.web_custom_check_badges(probe, checks, _service_icon_html),
        probe_checked_at=key_pool_web.web_probe_checked_at,
        custom_probe_states=key_pool_web.web_custom_probe_states,
        service_icon_html=_service_icon_html,
        pool_table_class=pool_table_class,
        pool_custom_col_width=pool_custom_col_width,
        pool_mobile_custom_col_width=pool_mobile_custom_col_width,
        custom_header_icons=key_pool_web.custom_check_header_icons(custom_checks, _service_icon_html),
        custom_presets_html=custom_presets_html,
        custom_checks_html=custom_checks_html,
        active_protocol=_default_web_protocol(),
        lazy_protocol_panels=True,
    )
    pool_summary = _pool_status_summary(current_keys, key_pools, key_probe_cache, custom_checks)
    return {
        'custom_checks_json': json.dumps(key_pool_web.web_custom_checks(custom_checks), ensure_ascii=False),
        'pool_summary': pool_summary,
        'pool_summary_note': web_pool_form_blocks.pool_summary_note_with_progress(
            pool_summary['note'],
            pool_probe_pending,
            progress,
            _pool_probe_progress_label,
        ),
        'protocol_panels_html': protocol_panels_html,
        'protocol_tabs_html': protocol_tabs_html,
        'topbar_status_text': web_pool_form_blocks.pool_probe_topbar_text(
            pool_probe_pending,
            progress,
            _pool_probe_progress_label,
            status['api_status'],
        ),
    }


def _web_simple_form_context(current_keys, protocol_statuses, csrf_input_html, status):
    protocol_tabs_html, protocol_panels_html = web_pool_form_blocks.render_protocol_tabs_and_panels(
        web_form_blocks.PROTOCOL_SECTIONS,
        current_keys,
        protocol_statuses,
        csrf_input_html,
        enable_key_pool=False,
        enable_custom_checks=False,
    )
    return {
        'custom_checks_json': '[]',
        'pool_summary': {'active_text': '', 'note': ''},
        'pool_summary_note': '',
        'protocol_panels_html': protocol_panels_html,
        'protocol_tabs_html': protocol_tabs_html,
        'topbar_status_text': status['api_status'],
    }


class KeyInstallHTTPRequestHandler(WebRequestMixin, BaseHTTPRequestHandler):
    csrf_error_as_json = True
    quiet_log_prefixes = ('/api/status', '/api/pool_probe', '/api/command_state', '/static/')
    local_client_checker = staticmethod(_web_is_local_client)
    web_auth_token_getter = staticmethod(lambda: _web_config_auth_token(config))
    web_auth_user_getter = staticmethod(lambda: _web_config_auth_user(config))
    flash_message_setter = staticmethod(_set_web_flash_message)

    def _build_style_asset(self):
        return render_web_style_asset(TELEGRAM_SVG_B64=TELEGRAM_SVG_B64)

    def _build_script_asset(self):
        app_runtime_mode = _load_app_runtime_mode()
        pool_enabled = _app_mode_pool_enabled(app_runtime_mode)
        csrf_token = self._get_or_create_csrf_token()
        current_keys = _load_current_keys()
        snapshot = _cached_status_snapshot(current_keys)
        progress = _get_pool_probe_progress()
        pool_probe_pending = bool(progress.get('running')) and int(progress.get('total') or 0) > 0
        if snapshot is None:
            snapshot = _active_mode_status_snapshot(current_keys)
        status_refresh_pending = web_form_blocks.status_refresh_pending(
            snapshot.get('web', {}),
            snapshot.get('protocols', {}),
            pool_probe_pending,
        )
        custom_checks_json = (
            json.dumps(key_pool_web.web_custom_checks(_load_custom_checks()), ensure_ascii=False)
            if pool_enabled else
            '[]'
        )
        return render_web_script_asset(
            POOL_PROBE_UI_POLL_EXTENSION_MS=POOL_PROBE_UI_POLL_EXTENSION_MS,
            TELEGRAM_SVG_B64=TELEGRAM_SVG_B64,
            YOUTUBE_SVG_B64=YOUTUBE_SVG_B64,
            csrf_token=csrf_token,
            custom_checks_json=custom_checks_json,
            initial_command_running=web_form_blocks.js_bool(bool(_get_web_command_state().get('running'))),
            initial_status_pending=web_form_blocks.js_bool(status_refresh_pending),
            enable_async_forms=True,
            enable_custom_checks=pool_enabled,
            enable_key_pool=pool_enabled,
            enable_live_status=True,
        )

    def _build_form(self, message=''):
        app_runtime_mode = _load_app_runtime_mode()
        pool_enabled = _app_mode_pool_enabled(app_runtime_mode)
        command_state = _consume_web_command_state_for_render()
        current_keys = _load_current_keys()
        snapshot = _cached_status_snapshot(current_keys)
        status = snapshot['web'] if snapshot is not None else _placeholder_web_status_snapshot()
        protocol_statuses = snapshot['protocols'] if snapshot is not None else _placeholder_protocol_statuses(current_keys)
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
        status_refresh_pending = web_form_blocks.status_refresh_pending(status, protocol_statuses, pool_probe_pending)

        current_mode_label = web_form_blocks.proxy_mode_label(status['proxy_mode'])
        form_basics = web_form_blocks.render_form_basics(message, command_state, status, current_keys, current_mode_label, live=True)
        list_route_label = _transparent_list_route_label()

        csrf_token = self._get_or_create_csrf_token()
        csrf_input_html = web_form_blocks.render_csrf_input(csrf_token)
        mode_picker_block = web_form_blocks.render_button_mode_picker(
            proxy_mode,
            csrf_input_html=csrf_input_html,
        )
        app_runtime_mode_picker_block = web_form_blocks.render_app_runtime_mode_picker(
            app_runtime_mode,
            APP_RUNTIME_MODES,
            csrf_input_html=csrf_input_html,
        )

        if pool_enabled:
            pool_view = _web_pool_form_context(
                current_keys,
                protocol_statuses,
                csrf_input_html,
                status,
                pool_probe_pending,
                current_pool_probe_progress,
            )
        else:
            pool_view = _web_simple_form_context(current_keys, protocol_statuses, csrf_input_html, status)
        quick_key = form_basics['quick_key']

        dns_override_active = _dns_override_enabled()
        command_buttons_html = web_form_blocks.render_router_command_buttons(csrf_input_html, dns_override_active)

        unblock_tabs_html, unblock_panels_html = web_form_blocks.render_unblock_lists(
            unblock_lists,
            csrf_input_html,
            SOCIALNET_SERVICE_KEYS,
            SOCIALNET_ALL_KEY,
            _socialnet_service_label,
        )

        initial_status_pending = web_form_blocks.js_bool(status_refresh_pending)
        initial_command_running = form_basics['initial_command_running']

        telegram_enabled = _app_mode_telegram_enabled(app_runtime_mode)
        start_button_label = '' if not telegram_enabled else (
            APP_START_REPEAT_LABEL if bot_ready else APP_START_IDLE_LABEL
        )
        mode_toggle_label = f'{APP_MODE_LABEL}:'
        quick_start_note = (
            'В режиме Web only Telegram-бот отключен; управление доступно через веб-интерфейс.'
            if not telegram_enabled else APP_QUICK_START_NOTE
        )


        return render_web_form(
            APP_BRANCH_DESCRIPTION=APP_BRANCH_DESCRIPTION,
            APP_BRANCH_LABEL=APP_BRANCH_LABEL,
            APP_VERSION_LABEL=APP_VERSION_LABEL,
            POOL_PROBE_UI_POLL_EXTENSION_MS=POOL_PROBE_UI_POLL_EXTENSION_MS,
            TELEGRAM_SVG_B64=TELEGRAM_SVG_B64,
            YOUTUBE_SVG_B64=YOUTUBE_SVG_B64,
            _telegram_icon_html=_telegram_icon_html,
            app_runtime_mode_description=_app_runtime_mode_description(app_runtime_mode),
            app_runtime_mode_label=_app_runtime_mode_label(app_runtime_mode),
            app_runtime_mode_picker_block=app_runtime_mode_picker_block,
            csrf_token=csrf_token,
            command_block=form_basics['command_block'],
            command_buttons_html=command_buttons_html,
            current_mode_label=current_mode_label,
            custom_checks_json=pool_view['custom_checks_json'],
            fallback_block=form_basics['fallback_block'],
            initial_command_running=initial_command_running,
            initial_status_pending=initial_status_pending,
            list_route_label=list_route_label,
            message_block=form_basics['message_block'],
            mode_picker_block=mode_picker_block,
            mode_toggle_label=mode_toggle_label,
            pool_summary=pool_view['pool_summary'],
            pool_summary_note=pool_view['pool_summary_note'],
            protocol_panels_html=pool_view['protocol_panels_html'],
            protocol_tabs_html=pool_view['protocol_tabs_html'],
            quick_key_label=quick_key['label'],
            quick_key_proto=quick_key['proto'],
            quick_key_value=quick_key['value'],
            quick_start_note=quick_start_note,
            socks_block=form_basics['socks_block'],
            start_button_label=start_button_label,
            status=status,
            topbar_status_text=pool_view['topbar_status_text'],
            unblock_panels_html=unblock_panels_html,
            unblock_tabs_html=unblock_tabs_html,
            enable_custom_checks=pool_enabled,
            enable_key_pool=pool_enabled,
        )

    def _build_protocol_panel(self, protocol):
        app_runtime_mode = _load_app_runtime_mode()
        if not _app_mode_pool_enabled(app_runtime_mode):
            raise ValueError('Пул ключей отключён в текущем режиме программы')
        current_keys = _load_current_keys()
        snapshot = _cached_status_snapshot(current_keys)
        if snapshot is None:
            snapshot = _active_mode_status_snapshot(current_keys)
            if not pool_probe_lock.locked():
                _refresh_status_caches_async(current_keys)
        csrf_token = self._get_or_create_csrf_token()
        csrf_input_html = web_form_blocks.render_csrf_input(csrf_token)
        return _web_protocol_panel_html(protocol, current_keys, snapshot.get('protocols', {}), csrf_input_html)

    def do_GET(self):
        if not self._ensure_request_allowed():
            return
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        try:
            action = web_get_actions.dispatch(_web_get_context(self), path, parsed_url.query)
        except Exception as exc:
            if path.startswith('/api/'):
                self._send_json({'error': str(exc)}, status=500)
            else:
                self._send_html(f'<h1>500 Internal Server Error</h1><p>{html.escape(str(exc))}</p>', status=500)
            return
        if action is None:
            self._send_html('<h1>404 Not Found</h1>', status=404)
            return
        kind = action.get('kind')
        if kind == 'json':
            self._send_json(action.get('payload', {}), status=action.get('status', 200))
        elif kind == 'html':
            self._send_html(action.get('html', ''))
        elif kind == 'text':
            self._send_text_asset(
                action.get('text', ''),
                content_type=action.get('content_type', 'text/plain; charset=utf-8'),
                cache_seconds=action.get('cache_seconds', 0),
            )
        elif kind == 'png':
            self._send_png(action.get('path', ''))
        else:
            self._send_html('<h1>404 Not Found</h1>', status=404)

    def do_POST(self):
        if not self._ensure_request_allowed():
            return
        path = urlparse(self.path).path
        data = self._read_post_data()
        if not self._ensure_csrf_allowed(data):
            return
        action = web_post_actions.dispatch(_web_action_context(), path, data)
        if action is None:
            self._send_html('<h1>404 Not Found</h1>', status=404)
            return
        self._send_action_result(
            action.get('result', ''),
            success=action.get('success', True),
            extra=action.get('extra') or None,
        )

def start_http_server():
    global web_httpd
    try:
        bind_host = _web_resolve_bind_host(routerip)
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
    return _store_read_v2ray_key(file_path, XRAY_CONFIG_DIR, V2RAY_CONFIG_DIR)


def _save_v2ray_key(file_path, key):
    _store_save_v2ray_key(file_path, key)


def _parse_vmess_key(key):
    return _store_parse_vmess_key(key)


def _parse_vless_key(key):
    return _store_parse_vless_key(key)


def _build_v2ray_config(vmess_key=None, vless_key=None, vless2_key=None, shadowsocks_key=None, trojan_key=None):
    return _builder_build_proxy_core_config(
        vmess_key=vmess_key,
        vless_key=vless_key,
        vless2_key=vless2_key,
        shadowsocks_key=shadowsocks_key,
        trojan_key=trojan_key,
        ports={
            'vmess': localportvmess,
            'vmess_transparent': localportvmess_transparent,
            'vless': localportvless,
            'vless_transparent': localportvless_transparent,
            'vless2': localportvless2,
            'vless2_transparent': localportvless2_transparent,
            'shadowsocks_bot': localportsh_bot,
            'trojan_bot': localporttrojan_bot,
        },
        error_log_path=CORE_PROXY_ERROR_LOG,
        access_log_path='/dev/null',
        loglevel='warning',
        connectivity_check_domains=CONNECTIVITY_CHECK_DOMAINS,
        include_vmess_transparent=True,
    )


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
    config = _builder_build_trojan_config(raw_key, localporttrojan)
    with open('/opt/etc/trojan/config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, separators=(',', ':'))
    _write_all_proxy_core_config()

def _decode_shadowsocks_uri(key):
    return _store_decode_shadowsocks_uri(key)


def shadowsocks(key=None):
    config = _builder_build_shadowsocks_config(key, localportsh)
    with open('/opt/etc/shadowsocks.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    _write_all_proxy_core_config()


PROXY_KEY_INSTALLERS = {
    'shadowsocks': shadowsocks,
    'vmess': vmess,
    'vless': vless,
    'vless2': vless2,
    'trojan': trojan,
}


def _restart_core_proxy_at_startup():
    try:
        _write_all_proxy_core_config()
        os.system(CORE_PROXY_SERVICE_SCRIPT + ' restart')
    except Exception as exc:
        _write_runtime_log(f'Не удалось пересобрать core proxy config при старте: {exc}')


def _mark_bot_ready_from_autostart():
    if _app_mode_telegram_enabled() and _load_bot_autostart():
        globals()['bot_ready'] = True


def _check_startup_proxy_endpoint():
    endpoint_ok, endpoint_message = _check_local_proxy_endpoint(proxy_mode, PROXY_LOCAL_PORTS.get(proxy_mode))
    if endpoint_ok:
        return True, endpoint_message
    _write_runtime_log(f'Прокси-режим {proxy_mode} не ответил при старте: {endpoint_message}. Перезапускаю core proxy.')
    try:
        os.system(CORE_PROXY_SERVICE_SCRIPT + ' restart')
        time.sleep(3)
    except Exception:
        pass
    return _check_local_proxy_endpoint(proxy_mode, PROXY_LOCAL_PORTS.get(proxy_mode))


def _restore_startup_proxy_mode():
    global proxy_mode
    saved_proxy_mode = _load_proxy_mode()
    proxy_mode = saved_proxy_mode
    ok, _ = update_proxy(proxy_mode)
    if not ok:
        proxy_mode = config.default_proxy_mode
        update_proxy(proxy_mode, persist=False)
        if saved_proxy_mode in proxy_settings:
            _save_proxy_mode(saved_proxy_mode)
        return
    if proxy_mode not in PROXY_LOCAL_PORTS:
        return

    endpoint_ok, endpoint_message = _check_startup_proxy_endpoint()
    if not endpoint_ok:
        fallback_mode = proxy_mode
        _write_runtime_log(f'Прокси-режим {fallback_mode} временно отключён при старте: {endpoint_message}')
        update_proxy('none', persist=False)
        _save_proxy_mode(fallback_mode)
        return

    api_status = check_telegram_api(retries=0, retry_delay=0, connect_timeout=8, read_timeout=10)
    if not api_status.startswith('✅'):
        _write_runtime_log(f'Прокси-режим {proxy_mode} не подтверждён при старте: {api_status}')


def _run_telegram_polling_loop():
    global bot_polling
    while not shutdown_requested.is_set():
        try:
            bot_polling = True
            bot.infinity_polling(timeout=60, long_polling_timeout=50)
        except Exception as err:
            bot_polling = False
            _write_runtime_log(err)
            _reset_telegram_http_session('polling error')
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


def main():
    _daemonize_process()
    _register_signal_handlers()
    _write_runtime_log('main() entered', mode='w')
    _runner_cleanup_pool_probe_runtime(kill_processes=True)
    runtime_mode = _load_app_runtime_mode()
    _write_runtime_log(f'app runtime mode: {runtime_mode}')
    start_http_server()
    _restart_core_proxy_at_startup()
    _mark_bot_ready_from_autostart()
    _restore_startup_proxy_mode()
    if _app_mode_pool_enabled(runtime_mode):
        _start_auto_failover_thread()
        _ensure_current_keys_in_pools()
    if _app_mode_telegram_enabled(runtime_mode):
        _deliver_pending_telegram_command_result()
        _start_telegram_result_retry_worker()
        wait_for_bot_start()
        _run_telegram_polling_loop()
    else:
        globals()['bot_ready'] = False
        _save_bot_autostart(False)
        while not shutdown_requested.is_set():
            shutdown_requested.wait(1)
    _finalize_shutdown()


if __name__ == '__main__':
    main()
