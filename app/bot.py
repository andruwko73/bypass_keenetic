#!/usr/bin/python3

import subprocess
import os
import re
import sys
import time
import hashlib
import threading
import signal
import ipaddress
import socket
import tempfile
import gc
import atexit
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlencode, unquote, urlparse

from app_version import APP_VERSION_LABEL
import app_runtime_mode
import bot_config as config

COMMAND_WORKER_MODE = os.environ.get('BYPASS_KEENETIC_COMMAND_WORKER') == '1'
POOL_PROBE_WORKER_MODE = os.environ.get('BYPASS_KEENETIC_POOL_PROBE_WORKER') == '1'
HEALTH_CHECK_WORKER_MODE = os.environ.get('BYPASS_KEENETIC_HEALTH_WORKER') == '1'


def _runtime_mode_at_import():
    return app_runtime_mode.load_app_runtime_mode(
        app_runtime_mode.APP_RUNTIME_MODE_FILE,
        default_mode=getattr(config, 'app_runtime_mode', 'advanced'),
    )


_IMPORT_RUNTIME_MODE = _runtime_mode_at_import()
_IMPORT_POOL_ENABLED = app_runtime_mode.app_mode_pool_enabled(_IMPORT_RUNTIME_MODE)
_IMPORT_TELEGRAM_ENABLED = app_runtime_mode.app_mode_telegram_enabled(_IMPORT_RUNTIME_MODE)

try:
    threading.stack_size(256 * 1024)
except (ValueError, RuntimeError):
    pass
from proxy_key_store import (
    load_current_keys as _store_load_current_keys,
    load_shadowsocks_key as _store_load_shadowsocks_key,
    load_trojan_key as _store_load_trojan_key,
    proxy_config_snapshot_paths as _store_proxy_config_snapshot_paths,
    read_v2ray_key as _store_read_v2ray_key,
    remove_file_if_exists as _store_remove_file_if_exists,
    save_v2ray_key as _store_save_v2ray_key,
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
_CUSTOM_CHECKS_PATH = '/opt/etc/bot/custom_checks.json'
if _IMPORT_POOL_ENABLED:
    import subscription_runtime
else:
    subscription_runtime = None
import entware_dns_runtime
import router_health_runtime
import router_metrics
try:
    import xray_compat_runtime
except Exception:
    xray_compat_runtime = None
if _IMPORT_TELEGRAM_ENABLED:
    from telegram_auth_state import build_authorized_identities as _build_authorized_identities
    import telegram_key_ui
    import telegram_info_runtime
    from telegram_auth_state import (
        MENU_STATE_UNSET,
        authorize_message as _telegram_authorize_message,
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
else:
    # Web-only registers inert handler declarations but never executes Telegram flows.
    def _build_authorized_identities(_raw_values):
        return set(), set()

    MENU_STATE_UNSET = object()
    TELEGRAM_CONFIRM_LEVEL = None
    INSTALL_MENU_TEXT = ''
from web_command_state import (
    command_state_snapshot as _command_state_snapshot,
    consume_command_state_for_render as _consume_command_state_for_render_impl,
    consume_flash_message as _consume_flash_message_impl,
    estimate_update_progress as _estimate_update_progress,
    finish_command as _finish_command_state,
    set_command_progress as _set_command_progress_state,
    set_flash_message as _set_flash_message_impl,
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
import web_background
import web_status_runtime
import web_commands_runtime
import event_history
import update_status
from web_status_builder import (
    active_protocol_status as _status_active_protocol_status,
    cached_protocol_status as _status_cached_protocol_status,
    empty_protocol_status as _status_empty_protocol_status,
    merge_light_status_with_cached_services as _status_merge_light_status_with_cached_services,
)

import shutil
import json
import html


def _config_sequence(name, default=()):
    value = getattr(config, name, default)
    if isinstance(value, str):
        return (value,)
    try:
        return tuple(value)
    except Exception:
        return tuple(default)


def _requests_module():
    import requests
    return requests


def _service_catalog():
    global _service_catalog_module
    if _service_catalog_module is None:
        import service_catalog as module

        _service_catalog_module = module
    return _service_catalog_module


def _custom_checks_store():
    global _custom_checks_store_module
    if _custom_checks_store_module is None:
        import custom_checks_store as module

        _custom_checks_store_module = module
    return _custom_checks_store_module


def _load_custom_checks():
    if not _IMPORT_POOL_ENABLED:
        return []
    return _custom_checks_store().load_custom_checks()


def _custom_check_presets():
    if not _IMPORT_POOL_ENABLED:
        return []
    return _custom_checks_store().custom_check_presets()


def _store_add_custom_check(*args, **kwargs):
    if not _IMPORT_POOL_ENABLED:
        raise ValueError('Дополнительные проверки недоступны в простом режиме.')
    return _custom_checks_store().add_custom_check(*args, **kwargs)


def _store_delete_custom_check(*args, **kwargs):
    if not _IMPORT_POOL_ENABLED:
        raise ValueError('Дополнительные проверки недоступны в простом режиме.')
    return _custom_checks_store().delete_custom_check(*args, **kwargs)


def _normalize_check_url(*args, **kwargs):
    if not _IMPORT_POOL_ENABLED:
        raise ValueError('Дополнительные проверки недоступны в простом режиме.')
    return _custom_checks_store().normalize_check_url(*args, **kwargs)


def _route_entries_from_values(values):
    if not _IMPORT_POOL_ENABLED:
        return []
    return _custom_checks_store().route_entries_from_values(values)


_pool_probe_runner_module = None
_pool_probe_controller_module = None
_probe_cache_module = None
_key_pool_store_module = None
_repo_update_module = None
_web_form_template_module = None
_web_form_template_lock = threading.Lock()
_web_route_tools_runtime = None
_key_pool_web_module = None
_telegram_pool_ui_module = None
_web_pool_form_blocks_module = None
_auto_failover_runtime_module = None
_telegram_call_learning_module = None
_youtube_edge_prefetch_module = None
_youtube_healthcheck_module = None
_subscription_runtime_module = subscription_runtime
_youtube_route_owner_module = None
_custom_checks_store_module = None
_service_catalog_module = None
_update_maintenance_runtime_module = None

_KEY_PROBE_CACHE_PATH = '/opt/etc/bot/key_probe_cache.json'
_KEY_PROBE_CACHE_SCHEMA_VERSION = 8
_KEY_PROBE_SUCCESS_DOWNGRADE_GRACE = 300
_POOL_SUMMARY_LAST_PATH = '/opt/etc/bot/pool_summary_last.json'
_YOUTUBE_QUALITY_DEFAULT_STABLE_LATENCY_MS = 2500
_YOUTUBE_QUALITY_DEFAULT_FAST_LATENCY_MS = 1500
_YOUTUBE_QUALITY_DEFAULT_1600P_MBPS = 25.0
_YOUTUBE_QUALITY_DEFAULT_4K_MBPS = 45.0
_POOL_YOUTUBE_HEALTHCHECK_URLS = (
    'https://www.youtube.com/generate_204',
    'https://www.youtube.com/',
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    'https://youtu.be/dQw4w9WgXcQ',
    'https://youtubei.googleapis.com/generate_204',
    'https://youtubei-att.googleapis.com/',
    'https://i.ytimg.com/generate_204',
    'https://www.gstatic.com/generate_204',
    'https://redirector.googlevideo.com/generate_204',
)
_POOL_YOUTUBE_HEALTHCHECK_MIN_OK = 8
_YOUTUBE_EDGE_PREFETCH_DEFAULT_HOSTS = (
    'www.youtube.com',
    'youtube.com',
    'm.youtube.com',
    'youtubei.googleapis.com',
    'youtubei-att.googleapis.com',
    'jnn-pa.googleapis.com',
    'play-fe.googleapis.com',
    'i.ytimg.com',
    's.ytimg.com',
    'yt3.ggpht.com',
    'www.gstatic.com',
    'manifest.googlevideo.com',
    'redirector.googlevideo.com',
)
_YOUTUBE_EDGE_PREFETCH_DEFAULT_DNS_SERVERS = ('local', '1.1.1.1', '8.8.8.8')
_TELEGRAM_CALL_LEARNING_PROTOCOL_IPSETS = {
    'shadowsocks': ('unblocksh', 'unblockshudp'),
    'vmess': ('unblockvmess', 'unblockvmessudp'),
    'vless': ('unblockvless', 'unblockvlessudp'),
    'vless2': ('unblockvless2', 'unblockvless2udp'),
    'trojan': ('unblocktroj', 'unblocktrojudp'),
}
_TELEGRAM_CALL_LEARNING_CLIENT_IPSETS = {
    'shadowsocks': 'bypass_call_clients_sh',
    'vmess': 'bypass_call_clients_vmess',
    'vless': 'bypass_call_clients_vless',
    'vless2': 'bypass_call_clients_vless2',
    'trojan': 'bypass_call_clients_troj',
}


class _PoolProbeProgress:
    def __init__(self):
        self._lock = threading.Lock()
        self._progress = {
            'running': False,
            'checked': 0,
            'total': 0,
            'scope': '',
            'note': '',
            'started_at': 0,
            'finished_at': 0,
        }

    def update(self, **updates):
        with self._lock:
            self._progress.update(updates)

    def snapshot(self):
        with self._lock:
            return dict(self._progress)


def _pool_probe_runner():
    global _pool_probe_runner_module
    if _pool_probe_runner_module is None:
        import pool_probe_runner as module

        _pool_probe_runner_module = module
    return _pool_probe_runner_module


def _pool_probe_controller():
    global _pool_probe_controller_module
    if _pool_probe_controller_module is None:
        import pool_probe_controller as module

        _pool_probe_controller_module = module
    return _pool_probe_controller_module


def _update_maintenance_runtime():
    global _update_maintenance_runtime_module
    if _update_maintenance_runtime_module is None:
        import update_maintenance_runtime as module

        _update_maintenance_runtime_module = module
    return _update_maintenance_runtime_module


def _probe_cache():
    global _probe_cache_module
    if _probe_cache_module is None:
        import probe_cache as module

        _probe_cache_module = module
    return _probe_cache_module


def _key_pool_store():
    global _key_pool_store_module
    if _key_pool_store_module is None:
        import key_pool_store as module

        _key_pool_store_module = module
    return _key_pool_store_module


def _key_pool_web():
    global _key_pool_web_module
    if _key_pool_web_module is None:
        import key_pool_web as module

        _key_pool_web_module = module
    return _key_pool_web_module


def _telegram_pool_ui():
    global _telegram_pool_ui_module
    if _telegram_pool_ui_module is None:
        import telegram_pool_ui as module

        _telegram_pool_ui_module = module
    return _telegram_pool_ui_module


def _web_pool_form_blocks():
    global _web_pool_form_blocks_module
    if _web_pool_form_blocks_module is None:
        import web_pool_form_blocks as module

        _web_pool_form_blocks_module = module
    return _web_pool_form_blocks_module


def _auto_failover_runtime():
    global _auto_failover_runtime_module
    if _auto_failover_runtime_module is None:
        import auto_failover_runtime as module

        _auto_failover_runtime_module = module
    return _auto_failover_runtime_module


def _telegram_call_learning():
    global _telegram_call_learning_module
    if _telegram_call_learning_module is None:
        import telegram_call_learning as module

        _telegram_call_learning_module = module
    return _telegram_call_learning_module


def _youtube_edge_prefetch():
    global _youtube_edge_prefetch_module
    if _youtube_edge_prefetch_module is None:
        import youtube_edge_prefetch as module

        _youtube_edge_prefetch_module = module
    return _youtube_edge_prefetch_module


def _youtube_healthcheck():
    global _youtube_healthcheck_module
    if _youtube_healthcheck_module is None:
        import youtube_healthcheck as module

        _youtube_healthcheck_module = module
    return _youtube_healthcheck_module


def _available_memory_kb(*args, **kwargs):
    value = _mem_available_kb_light(*args, **kwargs)
    return value if value > 0 else None


def _KeyProbeBatchRecorder(*args, **kwargs):
    return _probe_cache().KeyProbeBatchRecorder(*args, **kwargs)


def _forget_key_probes(*args, **kwargs):
    return _probe_cache().forget_key_probes(*args, **kwargs)


def _hash_key(value):
    return hashlib.sha1((value or '').encode('utf-8', errors='ignore')).hexdigest()


def _key_probe_is_fresh(*args, **kwargs):
    return _probe_cache().key_probe_is_fresh(*args, **kwargs)


def _load_key_probe_cache(*args, **kwargs):
    return _probe_cache().load_key_probe_cache(*args, **kwargs)


def _record_key_probe(*args, **kwargs):
    changed = _probe_cache().record_key_probe(*args, **kwargs)
    if changed:
        try:
            _invalidate_pool_data_cache()
        except NameError:
            pass
    return changed


def _record_light_telegram_probe(key_name, key_value, tg_ok, *, now=None):
    key_value = str(key_value or '').strip()
    if tg_ok is None or not key_value:
        return False
    cache = _read_json_file(_KEY_PROBE_CACHE_PATH, {}) or {}
    if not isinstance(cache, dict):
        cache = {}
    key_id = _hash_key(key_value)
    entry = cache.get(key_id, {})
    if not isinstance(entry, dict):
        entry = {}
    else:
        entry = dict(entry)
    now = time.time() if now is None else float(now)
    try:
        previous_ts = float(entry.get('ts') or 0)
    except (TypeError, ValueError):
        previous_ts = 0.0
    value = bool(tg_ok)
    if (
        value is False and
        previous_ts and
        now - previous_ts < _KEY_PROBE_SUCCESS_DOWNGRADE_GRACE and
        entry.get('tg_ok') is True
    ):
        return False

    changed = False
    if entry.get('schema') != _KEY_PROBE_CACHE_SCHEMA_VERSION:
        entry['schema'] = _KEY_PROBE_CACHE_SCHEMA_VERSION
        changed = True
    if entry.get('proto') != key_name:
        entry['proto'] = key_name
        changed = True
    if entry.get('tg_ok') is not value:
        entry['tg_ok'] = value
        changed = True
    if value is not True and 'tg_latency_ms' in entry:
        entry.pop('tg_latency_ms', None)
        changed = True
    if not changed:
        return False

    entry['ts'] = now
    cache[key_id] = entry
    _write_json_file(_KEY_PROBE_CACHE_PATH, cache)
    _invalidate_pool_data_cache()
    return True


def _load_light_key_probe_cache():
    cache = _read_json_file(_KEY_PROBE_CACHE_PATH, {}) or {}
    if not isinstance(cache, dict):
        return {}
    return {
        key_id: dict(entry)
        for key_id, entry in cache.items()
        if isinstance(entry, dict) and entry.get('schema') in (6, 7, _KEY_PROBE_CACHE_SCHEMA_VERSION)
    }


def _youtube_probe_state(entry):
    if not isinstance(entry, dict):
        return 'unknown'
    stability = str(entry.get('yt_stability') or '').strip().lower()
    if entry.get('yt_ok') is True:
        return 'ok'
    if stability == 'unstable':
        return 'warn'
    if entry.get('yt_ok') is False:
        return 'fail'
    return 'unknown'


def _repo_update():
    global _repo_update_module
    if _repo_update_module is None:
        import repo_update as module

        _repo_update_module = module
    return _repo_update_module


def _subscription_runtime():
    global _subscription_runtime_module
    if _subscription_runtime_module is None:
        import subscription_runtime as module

        _subscription_runtime_module = module
    return _subscription_runtime_module


def _youtube_route_owner():
    global _youtube_route_owner_module
    if _youtube_route_owner_module is None:
        import youtube_route_owner as module

        _youtube_route_owner_module = module
    return _youtube_route_owner_module


def _repo_direct_fetch_env(*args, **kwargs):
    return _repo_update().direct_fetch_env(*args, **kwargs)


def _repo_download_script(*args, **kwargs):
    return _repo_update().download_repo_script(*args, **kwargs)


def _fetch_remote_text(*args, **kwargs):
    return _repo_update().fetch_remote_text(*args, **kwargs)


def _repo_run_script_and_collect(*args, **kwargs):
    return _repo_update().run_script_and_collect(*args, **kwargs)


def _repo_write_script(*args, **kwargs):
    return _repo_update().write_script(*args, **kwargs)


def _web_form_template():
    global _web_form_template_module
    with _web_form_template_lock:
        if _web_form_template_module is None:
            import web_form_template as module

            _web_form_template_module = module
        return _web_form_template_module


def _clear_youtube_edge_prefetch_snapshot_cache():
    youtube_edge_prefetch_snapshot_cache['timestamp'] = 0.0
    youtube_edge_prefetch_snapshot_cache['payload'] = None


def render_web_form(*args, **kwargs):
    return _web_form_template().render_web_form(*args, **kwargs)


def render_web_script_asset(*args, **kwargs):
    return _web_form_template().render_web_script_asset(*args, **kwargs)


def render_web_style_asset(*args, **kwargs):
    return _web_form_template().render_web_style_asset(*args, **kwargs)


class _NoopTelegramApiHelper:
    proxy = {}

    @staticmethod
    def _get_req_session(reset=False):
        class _Session:
            def close(self):
                return None

        return _Session()


class _NoopTelegramMarkup:
    def __init__(self, *args, **kwargs):
        self.rows = []

    def row(self, *buttons):
        self.rows.append(list(buttons))


class _NoopTelegramTypes:
    KeyboardButton = str
    ReplyKeyboardMarkup = _NoopTelegramMarkup


class _NoopTeleBot:
    def __init__(self, *args, **kwargs):
        pass

    def message_handler(self, *args, **kwargs):
        return lambda func: func

    def callback_query_handler(self, *args, **kwargs):
        return lambda func: func

    def send_message(self, *args, **kwargs):
        return None

    def answer_callback_query(self, *args, **kwargs):
        return None

    def edit_message_reply_markup(self, *args, **kwargs):
        return None

    def infinity_polling(self, *args, **kwargs):
        return None

    def stop_polling(self):
        return None

    def stop_bot(self):
        return None

    def delete_webhook(self, *args, **kwargs):
        return None

    def close(self):
        return None


class _NoopTelegramModule:
    apihelper = _NoopTelegramApiHelper()
    TeleBot = _NoopTeleBot


if COMMAND_WORKER_MODE or not _IMPORT_TELEGRAM_ENABLED:
    telebot = _NoopTelegramModule()
    types = _NoopTelegramTypes()
else:
    import telebot
    from telebot import types

# --- Пул ключей и авто-фейловер Telegram API ---
KEY_POOLS_PATH = '/opt/etc/bot/key_pools.json'
SUBSCRIPTION_STATE_PATH = str(getattr(config, 'subscription_state_path', '/opt/etc/bot/subscriptions.json') or '').strip()
SUBSCRIPTION_NIGHTLY_POOL_PROBE_STATE_PATH = str(
    getattr(config, 'subscription_nightly_pool_probe_state_path', '/opt/etc/bot/subscription_nightly_pool_probe.json') or ''
).strip()
SUBSCRIPTION_MAX_BYTES = int(getattr(config, 'subscription_max_bytes', 2 * 1024 * 1024))
SUBSCRIPTION_ALLOW_PRIVATE_URLS = bool(getattr(config, 'subscription_allow_private_urls', False))
SUBSCRIPTION_HWID_VALUE = str(getattr(config, 'subscription_router_hwid', '') or '').strip()
SUBSCRIPTION_HWID_QUERY_PARAM = str(getattr(config, 'subscription_hwid_query_param', 'hwid') or 'hwid').strip()
_subscription_defaults = _subscription_runtime_module
SUBSCRIPTION_HWID_HEADER_NAMES = tuple(
    str(item).strip()
    for item in getattr(
        config,
        'subscription_hwid_header_names',
        getattr(_subscription_defaults, 'DEFAULT_HWID_HEADER_NAMES', ('X-HWID', 'X-Router-HWID', 'X-Device-ID')),
    )
    if str(item or '').strip()
)
SUBSCRIPTION_USER_AGENT = str(
    getattr(
        config,
        'subscription_user_agent',
        getattr(_subscription_defaults, 'DEFAULT_SUBSCRIPTION_USER_AGENT', 'v2rayN/6.45'),
    ) or ''
).strip()
SUBSCRIPTION_ACCEPT_HEADER = str(getattr(config, 'subscription_accept_header', 'text/plain, */*') or '').strip()
SUBSCRIPTION_AUTO_REFRESH_ENABLED = bool(getattr(config, 'subscription_auto_refresh_enabled', True))
SUBSCRIPTION_AUTO_REFRESH_INTERVAL_SECONDS = max(
    3600,
    int(getattr(config, 'subscription_auto_refresh_interval_seconds', 6 * 3600)),
)
SUBSCRIPTION_AUTO_REFRESH_RETRY_SECONDS = max(
    600,
    int(getattr(config, 'subscription_auto_refresh_retry_seconds', 3600)),
)
SUBSCRIPTION_AUTO_REFRESH_START_DELAY_SECONDS = max(
    60,
    int(getattr(config, 'subscription_auto_refresh_start_delay_seconds', 300)),
)
SUBSCRIPTION_AUTO_REFRESH_CHECK_SECONDS = max(
    300,
    int(getattr(config, 'subscription_auto_refresh_check_seconds', 300)),
)
SUBSCRIPTION_AUTO_REFRESH_MAX_BOT_RSS_KB = max(
    0,
    int(getattr(config, 'subscription_auto_refresh_max_bot_rss_kb', 70 * 1024)),
)
SUBSCRIPTION_AUTO_REFRESH_MIN_AVAILABLE_KB = max(
    0,
    int(getattr(config, 'subscription_auto_refresh_min_available_kb', 90 * 1024)),
)
SUBSCRIPTION_AUTO_REFRESH_MAX_CPU_PERCENT = max(
    0.0,
    float(getattr(config, 'subscription_auto_refresh_max_cpu_percent', 80.0)),
)
SUBSCRIPTION_AUTO_REFRESH_MAX_LOAD1 = max(
    0.0,
    float(getattr(config, 'subscription_auto_refresh_max_load1', 2.5)),
)
SUBSCRIPTION_NIGHTLY_POOL_PROBE_ENABLED = bool(getattr(config, 'subscription_nightly_pool_probe_enabled', True))
SUBSCRIPTION_NIGHTLY_POOL_PROBE_START_HOUR = max(
    0,
    min(23, int(getattr(config, 'subscription_nightly_pool_probe_start_hour', 3))),
)
SUBSCRIPTION_NIGHTLY_POOL_PROBE_END_HOUR = max(
    SUBSCRIPTION_NIGHTLY_POOL_PROBE_START_HOUR + 1,
    min(24, int(getattr(config, 'subscription_nightly_pool_probe_end_hour', 6))),
)
SUBSCRIPTION_NIGHTLY_POOL_PROBE_MAX_REFRESH_AGE_SECONDS = max(
    3600,
    int(getattr(config, 'subscription_nightly_pool_probe_max_refresh_age_seconds', 8 * 3600)),
)
AUTO_FAILOVER_GRACE_SECONDS = int(getattr(config, 'auto_failover_grace_seconds', 180))
AUTO_FAILOVER_POLL_SECONDS = int(getattr(config, 'auto_failover_poll_seconds', 60))
AUTO_FAILOVER_IDLE_LOG_INTERVAL_SECONDS = max(
    300,
    int(getattr(config, 'auto_failover_idle_log_interval_seconds', 900)),
)
AUTO_FAILOVER_SWITCH_COOLDOWN_SECONDS = int(getattr(config, 'auto_failover_switch_cooldown_seconds', 180))
AUTO_FAILOVER_CHECK_CONNECT_TIMEOUT = float(getattr(config, 'auto_failover_check_connect_timeout', 2))
AUTO_FAILOVER_CHECK_READ_TIMEOUT = float(getattr(config, 'auto_failover_check_read_timeout', 3))
AUTO_FAILOVER_RECENT_SUCCESS_TTL = max(0, int(getattr(config, 'auto_failover_recent_success_ttl', 900)))
AUTO_FAILOVER_CANDIDATE_FAILURE_BACKOFF_SECONDS = max(
    AUTO_FAILOVER_SWITCH_COOLDOWN_SECONDS,
    int(getattr(config, 'auto_failover_candidate_failure_backoff_seconds', 900)),
)
AUTO_FAILOVER_CONSECUTIVE_FAILURES = max(1, int(getattr(config, 'auto_failover_consecutive_failures', 3)))
AUTO_FAILOVER_TRAFFIC_GUARD_BYPASS_FAILURES = max(
    AUTO_FAILOVER_CONSECUTIVE_FAILURES,
    int(getattr(config, 'auto_failover_traffic_guard_bypass_failures', AUTO_FAILOVER_CONSECUTIVE_FAILURES)),
)
AUTO_FAILOVER_STARTUP_HOLD_SECONDS = max(
    180,
    int(getattr(config, 'auto_failover_startup_hold_seconds', 180)),
)
REALITY_ENDPOINT_REPAIR_ENABLED = bool(getattr(config, 'reality_endpoint_repair_enabled', True))
REALITY_ENDPOINT_REPAIR_BASE_PORT = max(19000, int(getattr(config, 'reality_endpoint_repair_base_port', 19050)))
REALITY_ENDPOINT_REPAIR_MAX_CANDIDATES = max(2, int(getattr(config, 'reality_endpoint_repair_max_candidates', 6)))
_REALITY_ENDPOINT_REPAIR_DNS_SERVERS_RAW = getattr(
    config,
    'reality_endpoint_repair_dns_servers',
    ('1.1.1.1', '8.8.8.8', '9.9.9.9'),
)
if isinstance(_REALITY_ENDPOINT_REPAIR_DNS_SERVERS_RAW, str):
    REALITY_ENDPOINT_REPAIR_DNS_SERVERS = tuple(
        item.strip() for item in _REALITY_ENDPOINT_REPAIR_DNS_SERVERS_RAW.replace(',', ' ').split() if item.strip()
    )
else:
    REALITY_ENDPOINT_REPAIR_DNS_SERVERS = tuple(
        str(item).strip() for item in (_REALITY_ENDPOINT_REPAIR_DNS_SERVERS_RAW or ()) if str(item).strip()
    )
auto_failover_state = {
    'started_at': time.time(),
    'last_ok': 0.0,
    'last_fail': 0.0,
    'last_failure_message': '',
    'last_attempt': 0.0,
    'last_idle_log': 0.0,
    'consecutive_failures': 0,
    'in_progress': False,
}


def _prime_auto_failover_after_telegram_failure(message):
    now = time.time()
    try:
        started_at = float(auto_failover_state.get('started_at') or now)
    except (TypeError, ValueError):
        started_at = now
    auto_failover_state['started_at'] = min(
        started_at,
        now - max(0, AUTO_FAILOVER_STARTUP_HOLD_SECONDS),
    )
    auto_failover_state['last_ok'] = 0.0
    auto_failover_state['last_fail'] = now - max(0, AUTO_FAILOVER_GRACE_SECONDS)
    auto_failover_state['last_failure_message'] = str(message or 'Telegram API failure')[:500]
    try:
        failures = int(auto_failover_state.get('consecutive_failures') or 0)
    except (TypeError, ValueError):
        failures = 0
    auto_failover_state['consecutive_failures'] = max(
        failures,
        max(1, AUTO_FAILOVER_CONSECUTIVE_FAILURES - 1),
    )


def _is_telegram_connectivity_error(error):
    text = f'{error.__class__.__name__}: {error}'.lower()
    markers = (
        'connectionerror',
        'connecttimeout',
        'readtimeout',
        'sslerror',
        'protocolerror',
        'connection reset',
        'connection aborted',
        'remote disconnected',
        'max retries',
        'timed out',
        'api.telegram.org',
    )
    return any(marker in text for marker in markers)


def _mark_active_telegram_failure(message):
    now = time.time()
    telegram_route_proto = _telegram_route_protocol() or proxy_mode
    active_key = (
        _load_current_keys().get(telegram_route_proto, '')
        if telegram_route_proto in POOL_PROTOCOL_ORDER else ''
    ).strip()
    if active_key:
        _record_key_probe(
            telegram_route_proto,
            active_key,
            tg_ok=False,
            allow_recent_success_downgrade=True,
        )
    _prime_auto_failover_after_telegram_failure(message)
    background_task_skip_until.pop('Telegram auto-failover', None)
    background_task_skip_reason.pop('Telegram auto-failover', None)
    _invalidate_key_status_cache()
    last_log = float(background_task_skip_log_at.get('Telegram polling failure') or 0.0)
    if now - last_log >= 60.0:
        background_task_skip_log_at['Telegram polling failure'] = now
        _write_runtime_log(
            f'Auto-failover: Telegram polling failed through {telegram_route_proto}; '
            'active key marked failed and recovery scheduled.'
        )


YOUTUBE_VLESS2_FAILOVER_ENABLED = bool(getattr(config, 'youtube_vless2_failover_enabled', True))
YOUTUBE_VLESS2_FAILOVER_GRACE_SECONDS = max(180, int(getattr(config, 'youtube_vless2_failover_grace_seconds', 180)))
YOUTUBE_VLESS2_FAILOVER_POLL_SECONDS = max(120, int(getattr(config, 'youtube_vless2_failover_poll_seconds', 120)))
YOUTUBE_VLESS2_FAILOVER_SWITCH_COOLDOWN_SECONDS = int(
    max(300, int(getattr(config, 'youtube_vless2_failover_switch_cooldown_seconds', 300)))
)
YOUTUBE_VLESS2_FAILOVER_CHECK_CONNECT_TIMEOUT = float(
    max(6.0, float(getattr(config, 'youtube_vless2_failover_check_connect_timeout', 6)))
)
YOUTUBE_VLESS2_FAILOVER_CHECK_READ_TIMEOUT = float(
    max(10.0, float(getattr(config, 'youtube_vless2_failover_check_read_timeout', 10)))
)
YOUTUBE_VLESS2_FAILOVER_CONFIRM_RETRIES = max(3, int(getattr(config, 'youtube_vless2_failover_confirm_retries', 3)))
YOUTUBE_VLESS2_FAILOVER_CONFIRM_DELAY_SECONDS = max(
    8.0,
    float(getattr(config, 'youtube_vless2_failover_confirm_delay_seconds', 8.0)),
)
YOUTUBE_VLESS2_FAILOVER_RECENT_SUCCESS_TTL = max(
    0,
    int(getattr(config, 'youtube_vless2_failover_recent_success_ttl', 900)),
)
YOUTUBE_VLESS2_HEALTHCHECK_URLS = tuple(getattr(config, 'youtube_vless2_healthcheck_urls', _POOL_YOUTUBE_HEALTHCHECK_URLS))
YOUTUBE_VLESS2_HEALTHCHECK_MIN_OK = max(1, int(getattr(config, 'youtube_vless2_healthcheck_min_ok', _POOL_YOUTUBE_HEALTHCHECK_MIN_OK)))
YOUTUBE_VLESS2_RESTART_RECHECK_ENABLED = bool(getattr(config, 'youtube_vless2_restart_recheck_enabled', True))
YOUTUBE_VLESS2_RESTART_RECHECK_COOLDOWN_SECONDS = max(
    120,
    int(getattr(config, 'youtube_vless2_restart_recheck_cooldown_seconds', 300)),
)
YOUTUBE_VLESS2_FAILOVER_CONSECUTIVE_FAILURES = max(
    1,
    int(getattr(config, 'youtube_vless2_failover_consecutive_failures', 3)),
)
YOUTUBE_VLESS2_HARD_FAILURE_RECOVERY_COOLDOWN_SECONDS = max(
    45,
    int(getattr(config, 'youtube_vless2_hard_failure_recovery_cooldown_seconds', 90)),
)
YOUTUBE_STREAM_GUARD_ENABLED = bool(getattr(config, 'youtube_stream_guard_enabled', True))
YOUTUBE_STREAM_GUARD_HOLD_SECONDS = max(60, int(getattr(config, 'youtube_stream_guard_hold_seconds', 300)))
YOUTUBE_STREAM_GUARD_FAILOVER_HOLD_SECONDS = max(15, int(getattr(config, 'youtube_stream_guard_failover_hold_seconds', 45)))
YOUTUBE_STREAM_GUARD_MIN_BYTES = max(1024, int(getattr(config, 'youtube_stream_guard_min_bytes', 8192)))
YOUTUBE_STREAM_GUARD_MIN_PACKETS = max(1, int(getattr(config, 'youtube_stream_guard_min_packets', 8)))
YOUTUBE_STREAM_GUARD_LOG_INTERVAL = max(60, int(getattr(config, 'youtube_stream_guard_log_interval_seconds', 180)))
YOUTUBE_STREAM_GUARD_EVENT_INTERVAL = max(
    1800,
    int(getattr(config, 'youtube_stream_guard_event_interval_seconds', 1800)),
)
YOUTUBE_STREAM_GUARD_SCAN_CACHE_SECONDS = max(
    1.0,
    float(getattr(config, 'youtube_stream_guard_scan_cache_seconds', 8.0)),
)
YOUTUBE_EDGE_PREFETCH_ENABLED = bool(getattr(config, 'youtube_edge_prefetch_enabled', True))
YOUTUBE_EDGE_PREFETCH_MODE = str(getattr(config, 'youtube_edge_prefetch_mode', 'external') or 'external').strip().lower()
YOUTUBE_EDGE_PREFETCH_START_DELAY_SECONDS = max(
    60,
    int(getattr(config, 'youtube_edge_prefetch_start_delay_seconds', 120)),
)
YOUTUBE_EDGE_PREFETCH_INTERVAL_SECONDS = max(
    0,
    int(getattr(config, 'youtube_edge_prefetch_interval_seconds', 0)),
)
YOUTUBE_EDGE_PREFETCH_CACHE_PATH = str(
    getattr(config, 'youtube_edge_prefetch_cache_path', '/opt/etc/bot/youtube_edge_cache.json') or ''
).strip()
YOUTUBE_EDGE_PREFETCH_STATUS_PATH = str(
    getattr(config, 'youtube_edge_prefetch_status_path', '/opt/etc/bot/youtube_edge_prefetch_status.json') or ''
).strip()
YOUTUBE_EDGE_PREFETCH_LOCK_DIR = str(
    getattr(config, 'youtube_edge_prefetch_lock_dir', '/tmp/bypass-youtube-edge-prefetch.lock') or ''
).strip()
YOUTUBE_EDGE_PREFETCH_CACHE_TTL_SECONDS = max(
    3600,
    int(getattr(config, 'youtube_edge_prefetch_cache_ttl_seconds', 72 * 3600)),
)
YOUTUBE_EDGE_PREFETCH_MAX_CACHE_ENTRIES = max(
    16,
    int(getattr(config, 'youtube_edge_prefetch_max_cache_entries', 128)),
)
YOUTUBE_EDGE_PREFETCH_MAX_HOSTS_PER_RUN = max(
    1,
    int(getattr(config, 'youtube_edge_prefetch_max_hosts_per_run', 6)),
)
YOUTUBE_EDGE_PREFETCH_MAX_RESOLVED_ADDRESSES = max(
    1,
    int(getattr(config, 'youtube_edge_prefetch_max_resolved_addresses', 16)),
)
YOUTUBE_EDGE_PREFETCH_MAX_CANDIDATES = max(
    YOUTUBE_EDGE_PREFETCH_MAX_RESOLVED_ADDRESSES,
    int(getattr(config, 'youtube_edge_prefetch_max_candidates', 32)),
)
YOUTUBE_EDGE_PREFETCH_MAX_ADDRESSES_PER_RUN = max(
    1,
    int(getattr(config, 'youtube_edge_prefetch_max_addresses_per_run', 8)),
)
YOUTUBE_EDGE_PREFETCH_MIN_AVAILABLE_KB = max(
    0,
    int(getattr(config, 'youtube_edge_prefetch_min_available_kb', 125000)),
)
YOUTUBE_EDGE_PREFETCH_MAX_RSS_KB = max(
    0,
    int(getattr(config, 'youtube_edge_prefetch_max_rss_kb', 65 * 1024)),
)
YOUTUBE_EDGE_PREFETCH_HOSTS = _config_sequence(
    'youtube_edge_prefetch_hosts',
    _YOUTUBE_EDGE_PREFETCH_DEFAULT_HOSTS,
)
YOUTUBE_EDGE_PREFETCH_DNS_SERVERS = _config_sequence(
    'youtube_edge_prefetch_dns_servers',
    _YOUTUBE_EDGE_PREFETCH_DEFAULT_DNS_SERVERS,
)
YOUTUBE_EDGE_PREFETCH_EXCLUSIVE_IPSETS = bool(getattr(config, 'youtube_edge_prefetch_exclusive_ipsets', True))
youtube_vless2_failover_state = {
    'last_ok': 0.0,
    'last_fail': 0.0,
    'last_attempt': 0.0,
    'consecutive_failures': 0,
    'in_progress': False,
}
youtube_failover_states = {'vless2': youtube_vless2_failover_state}
youtube_stream_guard_state = {
    'last_active': 0.0,
    'last_log': 0.0,
    'last_event': 0.0,
    'last_count': 0,
    'conntrack': {},
    'last_samples': [],
}
youtube_stream_guard_states = {'vless2': youtube_stream_guard_state}
youtube_core_restart_state = {
    'last_restart': 0.0,
}
youtube_hard_failure_recovery_state = {
    'last_attempt': 0.0,
}
udp_quic_drift_state = {
    'last_refresh': 0.0,
    'last_log': 0.0,
    'last_fast_add_signature': (),
    'last_fast_add_event': 0.0,
    'route_signature': (),
    'domains_by_protocol': {},
    'dns_cache': {},
}
background_task_skip_log_at = {}
background_task_skip_until = {}
background_task_skip_reason = {}
background_task_coordinator_lock = threading.Lock()
background_task_coordinator_state = {'name': '', 'started_at': 0.0}
background_maintenance_thread = None
youtube_edge_prefetch_state = {
    'enabled': YOUTUBE_EDGE_PREFETCH_ENABLED,
    'route_protocol': '',
    'last_run_at': 0.0,
    'last_success_at': 0.0,
    'last_added_at': 0.0,
    'skipped_reason': 'not_run',
    'candidates': 0,
    'cache_entries': 0,
    'added_addresses': 0,
    'added_sets': 0,
    'deleted_sets': 0,
    'failed_sets': 0,
    'last_message': 'not run',
    'last_log_signature': (),
    'next_host_index': 0,
}
youtube_edge_prefetch_snapshot_cache = {
    'timestamp': 0.0,
    'payload': None,
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
        return _key_pool_store().load_key_pools(KEY_POOLS_PATH)


def _dedupe_key_list(keys):
    return _key_pool_store().dedupe_key_list(keys)


def _save_key_pools(pools):
    with key_pool_lock:
        return _key_pool_store().save_key_pools(KEY_POOLS_PATH, pools)


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


def _read_router_hwid_command(command):
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout or ''
    except Exception:
        pass
    return ''


def _detect_router_hwid():
    texts = []
    for command in (
        ['ndmc', '-c', 'show version'],
        ['ndmc', '-c', 'show system'],
    ):
        text = _read_router_hwid_command(command)
        if text:
            texts.append(text)
    return _subscription_runtime().extract_router_hwid('\n'.join(texts))


def _router_hwid():
    if SUBSCRIPTION_HWID_VALUE:
        return SUBSCRIPTION_HWID_VALUE
    now = time.time()
    with subscription_hwid_lock:
        cached = subscription_hwid_cache.get('value')
        checked_at = float(subscription_hwid_cache.get('checked_at') or 0)
        if cached is not None and now - checked_at < 3600:
            return cached
        value = _detect_router_hwid()
        subscription_hwid_cache['value'] = value
        subscription_hwid_cache['checked_at'] = now
        return value


def _subscription_request_url_headers(url, use_router_hwid=False):
    if not use_router_hwid:
        return str(url or '').strip(), {}
    hwid = _router_hwid()
    if not hwid:
        raise ValueError('HWID роутера не определён')
    return _subscription_runtime().apply_hwid_to_subscription_request(
        url,
        hwid,
        query_param=SUBSCRIPTION_HWID_QUERY_PARAM,
        header_names=SUBSCRIPTION_HWID_HEADER_NAMES,
    )


def _fetch_keys_from_subscription(url, use_router_hwid=False):
    """Загружает ключи из subscription-ссылки (base64-encoded список)."""
    requests = _requests_module()
    try:
        parsed = urlparse(str(url or '').strip())
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise ValueError('subscription URL must be http:// or https://')
        if not SUBSCRIPTION_ALLOW_PRIVATE_URLS and _private_subscription_address(parsed.hostname):
            raise ValueError('private, local and reserved subscription hosts are not allowed')
        request_url, headers = _subscription_request_url_headers(url, use_router_hwid=use_router_hwid)
        request_headers = dict(headers or {})
        normalized_header_names = {str(name).lower() for name in request_headers}
        if SUBSCRIPTION_USER_AGENT and 'user-agent' not in normalized_header_names:
            request_headers['User-Agent'] = SUBSCRIPTION_USER_AGENT
        if SUBSCRIPTION_ACCEPT_HEADER and 'accept' not in normalized_header_names:
            request_headers['Accept'] = SUBSCRIPTION_ACCEPT_HEADER
        session = requests.Session()
        try:
            session.trust_env = False
            resp = session.get(request_url, headers=request_headers, stream=True, timeout=(5, 15))
            try:
                resp.raise_for_status()
                raw = _read_limited_response(resp, SUBSCRIPTION_MAX_BYTES)
            finally:
                resp.close()
        finally:
            session.close()
        return _key_pool_store().classify_subscription_keys(raw), None
    except requests.RequestException as exc:
        return None, f'Ошибка загрузки subscription: {exc}'
    except Exception as exc:
        return None, f'Ошибка обработки subscription: {exc}'
        


def _set_active_key(proto, key):
    with key_pool_lock:
        pools = _key_pool_store().set_active_key(_key_pool_store().load_key_pools(KEY_POOLS_PATH), proto, key)
        _key_pool_store().save_key_pools(KEY_POOLS_PATH, pools)


def _install_key_for_protocol(proto, key_value, verify=True):
    started_at = time.time()
    try:
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
    finally:
        duration_ms = int(max(0.0, time.time() - started_at) * 1000)
        _write_runtime_log(f'Key apply: protocol={proto} verify={int(bool(verify))} duration_ms={duration_ms}')


def _auto_failover_event_details(extra=None):
    now = time.time()
    try:
        last_ok = float(auto_failover_state.get('last_ok') or 0)
    except Exception:
        last_ok = 0.0
    try:
        last_fail = float(auto_failover_state.get('last_fail') or 0)
    except Exception:
        last_fail = 0.0
    try:
        last_attempt = float(auto_failover_state.get('last_attempt') or 0)
    except Exception:
        last_attempt = 0.0
    details = {
        'mode': proxy_mode,
        'consecutive_failures': int(auto_failover_state.get('consecutive_failures') or 0),
        'failure_threshold': AUTO_FAILOVER_CONSECUTIVE_FAILURES,
        'last_ok_age_s': int(now - last_ok) if last_ok else '',
        'last_fail_age_s': int(now - last_fail) if last_fail else '',
        'cooldown_left_s': int(max(0, AUTO_FAILOVER_SWITCH_COOLDOWN_SECONDS - (now - last_attempt))) if last_attempt else 0,
    }
    if isinstance(extra, dict):
        details.update(extra)
    return details


def _auto_failover_log(message):
    _write_runtime_log(message)
    text = str(message or '')
    lower_text = text.lower()
    level = 'warn' if any(marker in lower_text for marker in ('failed confirmation', 'failed', 'error')) else 'info'
    action = 'auto_failover'
    if 'failed confirmation' in lower_text:
        action = 'auto_failover_confirm_fail'
    elif 'switch skipped' in lower_text or 'пропущ' in lower_text:
        action = 'auto_failover_skip'
    elif 'switched' in lower_text or 'переключ' in lower_text:
        action = 'auto_failover_switch'
    _record_event(
        action,
        text,
        level=level,
        source='watchdog',
        protocol=proxy_mode,
        service='telegram',
        details=_auto_failover_event_details(),
    )


def _auto_failover_defer_switch_for_traffic_guard(**kwargs):
    if proxy_mode not in YOUTUBE_STREAM_GUARD_PROTOCOLS:
        return False
    try:
        failures = int(auto_failover_state.get('consecutive_failures') or 0)
    except Exception:
        failures = 0
    bypass_after = max(
        int(kwargs.get('min_consecutive_failures') or AUTO_FAILOVER_CONSECUTIVE_FAILURES),
        AUTO_FAILOVER_TRAFFIC_GUARD_BYPASS_FAILURES,
    )
    guarded = _vless_traffic_guard_active(
        'Telegram auto-failover',
        log=failures < bypass_after,
        hold_seconds=YOUTUBE_STREAM_GUARD_FAILOVER_HOLD_SECONDS,
    )
    if not guarded:
        return False
    if failures >= bypass_after:
        message = (
            f'Auto-failover: bypassing traffic guard after {failures} confirmed '
            'Telegram API failures.'
        )
        _write_runtime_log(message)
        _record_event(
            'auto_failover_guard_bypass',
            message,
            level='warn',
            source='watchdog',
            protocol=proxy_mode,
            service='telegram',
            details=_auto_failover_event_details({
                'guard_bypass_after_failures': bypass_after,
            }),
        )
        return False
    _auto_failover_log(
        f'Auto-failover: traffic guard deferred Telegram key switch after confirmed '
        f'failure {failures}/{bypass_after}.'
    )
    return True


def _auto_failover_has_pending_failure():
    try:
        failures = int(auto_failover_state.get('consecutive_failures') or 0)
    except (TypeError, ValueError):
        failures = 0
    if failures > 0:
        return True
    try:
        last_fail = float(auto_failover_state.get('last_fail') or 0.0)
    except (TypeError, ValueError):
        last_fail = 0.0
    return bool(last_fail or str(auto_failover_state.get('last_failure_message') or '').strip())


def _mark_auto_failover_polling_ok(now=None):
    if now is None:
        now = time.time()
    auto_failover_state['last_ok'] = now
    auto_failover_state['last_fail'] = 0.0
    auto_failover_state['consecutive_failures'] = 0
    auto_failover_state['last_failure_message'] = ''


def _restore_telegram_polling_after_verified_recovery():
    if _auto_failover_has_pending_failure():
        return False
    try:
        last_ok = float(auto_failover_state.get('last_ok') or 0.0)
    except (TypeError, ValueError):
        last_ok = 0.0
    if last_ok <= 0.0:
        return False
    globals()['bot_polling'] = True
    _invalidate_web_status_api_cache()
    _invalidate_web_status_cache()
    return True


def _auto_failover_idle_log(reason, now=None):
    if now is None:
        now = time.time()
    try:
        last_log = float(auto_failover_state.get('last_idle_log') or 0.0)
    except (TypeError, ValueError):
        last_log = 0.0
    if now - last_log < AUTO_FAILOVER_IDLE_LOG_INTERVAL_SECONDS:
        return
    auto_failover_state['last_idle_log'] = now
    try:
        rss_kb = int(_process_rss_kb() or 0)
    except Exception:
        rss_kb = 0
    _write_runtime_log(
        f'Telegram auto-failover: idle ({reason}); '
        f'no pending failure, bot RSS {rss_kb} KB.'
    )


def _auto_failover_should_run():
    if not _app_mode_pool_enabled():
        return False, 'pool disabled'
    if _auto_failover_has_pending_failure():
        return True, 'pending failure'
    if not _app_mode_telegram_enabled():
        return False, 'telegram disabled'
    if bot_polling:
        _mark_auto_failover_polling_ok()
        return False, 'Telegram polling is healthy'
    return True, 'Telegram polling stopped'


def _attempt_auto_failover():
    telegram_route_proto = _telegram_route_protocol()
    if not telegram_route_proto:
        return False
    if _app_mode_telegram_enabled() and bot_polling and not _auto_failover_has_pending_failure():
        _mark_auto_failover_polling_ok()
        return False
    if proxy_mode != telegram_route_proto:
        _auto_failover_log(
            f'Auto-failover: restoring Telegram route protocol {telegram_route_proto} '
            f'instead of current mode {proxy_mode}.'
        )
        ok, error = update_proxy(telegram_route_proto)
        if not ok:
            _auto_failover_log(
                f'Auto-failover: cannot restore Telegram route protocol {telegram_route_proto}: {error}'
            )
            return False
    switched = _auto_failover_runtime().attempt_auto_failover(
        state=auto_failover_state,
        pool_probe_locked=lambda: bool(globals().get('pool_probe_lock') and pool_probe_lock.locked()),
        proxy_mode=telegram_route_proto,
        proxy_url=proxy_settings.get(telegram_route_proto),
        check_telegram_api=_check_telegram_api_for_background,
        load_current_keys=_load_current_keys,
        load_key_pools=_load_key_pools,
        failover_candidates=_key_pool_store().failover_candidates,
        find_pool_failover_candidate=_find_pool_failover_candidate,
        install_key_for_protocol=_install_key_for_protocol,
        update_proxy=update_proxy,
        set_active_key=_set_active_key,
        record_key_probe=_record_key_probe,
        log=_auto_failover_log,
        audit_key_switch=_audit_key_switch,
        grace_seconds=AUTO_FAILOVER_GRACE_SECONDS,
        switch_cooldown_seconds=AUTO_FAILOVER_SWITCH_COOLDOWN_SECONDS,
        check_timeouts=(AUTO_FAILOVER_CHECK_CONNECT_TIMEOUT, AUTO_FAILOVER_CHECK_READ_TIMEOUT),
        key_probe_cache=_load_key_probe_cache,
        hash_key=_hash_key,
        is_transient_failure=_is_transient_telegram_api_failure,
        transient_success_ttl=TELEGRAM_TRANSIENT_OK_CACHE_TTL,
        recent_success_ttl=AUTO_FAILOVER_RECENT_SUCCESS_TTL,
        recent_failure_backoff_seconds=AUTO_FAILOVER_CANDIDATE_FAILURE_BACKOFF_SECONDS,
        skip_failed_candidates=True,
        startup_hold_seconds=AUTO_FAILOVER_STARTUP_HOLD_SECONDS,
        min_consecutive_failures=AUTO_FAILOVER_CONSECUTIVE_FAILURES,
        repair_active_proxy=_repair_active_reality_endpoint,
        protocols=(telegram_route_proto,),
        defer_switch=_auto_failover_defer_switch_for_traffic_guard,
    )
    _restore_telegram_polling_after_verified_recovery()
    return switched


def _youtube_route_protocol():
    try:
        owner = _youtube_route_owner().youtube_route_owner()
        return owner if owner in YOUTUBE_ROUTE_PROTOCOLS else ''
    except Exception:
        return ''


def _youtube_failover_state(proto):
    if proto not in youtube_failover_states:
        youtube_failover_states[proto] = {
            'last_ok': 0.0,
            'last_fail': 0.0,
            'last_attempt': 0.0,
            'in_progress': False,
        }
    return youtube_failover_states[proto]


def _check_youtube_protocol_once(proto=None, metrics=None):
    proto = proto or _youtube_route_protocol()
    if proto not in YOUTUBE_ROUTE_PROTOCOLS:
        return None, 'YouTube route owner is not determined'
    return _youtube_healthcheck().check_youtube_through_proxy(
        _check_http_through_proxy,
        proxy_settings.get(proto),
        urls=YOUTUBE_VLESS2_HEALTHCHECK_URLS,
        min_ok=YOUTUBE_VLESS2_HEALTHCHECK_MIN_OK,
        http_timeouts=(YOUTUBE_VLESS2_FAILOVER_CHECK_CONNECT_TIMEOUT, YOUTUBE_VLESS2_FAILOVER_CHECK_READ_TIMEOUT),
        http_retry_timeouts=(YOUTUBE_VLESS2_FAILOVER_CHECK_CONNECT_TIMEOUT, YOUTUBE_VLESS2_FAILOVER_CHECK_READ_TIMEOUT),
        retry_delay_seconds=POOL_PROBE_RETRY_DELAY_SECONDS,
        metrics=metrics,
        sleep=shutdown_requested.wait,
    )


def _schedule_youtube_cache_confirm(proto, key_value):
    if proto not in YOUTUBE_ROUTE_PROTOCOLS or not key_value or youtube_cache_confirm_lock.locked():
        return

    def worker():
        try:
            with youtube_cache_confirm_lock:
                yt_metrics = {}
                ok, _message = _check_youtube_protocol_for_background(proto, metrics=yt_metrics)
                if ok:
                    _record_key_probe(proto, key_value, yt_ok=True, **yt_metrics)
                    _invalidate_key_status_cache()
        finally:
            _memory_cleanup(f'{proto} youtube cache confirm')

    threading.Thread(target=worker, daemon=True).start()


def _confirm_youtube_key(proto):
    last_message = ''
    for attempt in range(YOUTUBE_VLESS2_FAILOVER_CONFIRM_RETRIES):
        ok, message = _check_youtube_protocol_for_background(proto)
        if ok is None:
            return None, message
        if ok:
            return True, message
        last_message = message
        if attempt + 1 < YOUTUBE_VLESS2_FAILOVER_CONFIRM_RETRIES:
            shutdown_requested.wait(YOUTUBE_VLESS2_FAILOVER_CONFIRM_DELAY_SECONDS)
            if shutdown_requested.is_set():
                break
    return False, last_message


def _restore_youtube_key_after_failed_failover(proto, original_key):
    current_key = (_load_current_keys().get(proto) or '').strip()
    if not original_key or current_key == original_key:
        return
    try:
        _install_key_for_protocol(proto, original_key, verify=False)
        _record_key_probe(proto, original_key, yt_ok=False)
        _audit_key_switch('youtube_failover_restore', proto, original_key, 'failed candidates')
        _write_runtime_log(f'YouTube failover: restored previous {_pool_proto_label(proto)} key after failed candidates.')
    except Exception as exc:
        _write_runtime_log(f'YouTube failover: failed to restore previous {_pool_proto_label(proto)} key: {exc}')


def _restart_core_proxy_and_recheck_youtube(route_proto, active_key, previous_message=''):
    if not YOUTUBE_VLESS2_RESTART_RECHECK_ENABLED:
        return False
    now = time.time()
    last_restart = float(youtube_core_restart_state.get('last_restart') or 0.0)
    if last_restart and now - last_restart < YOUTUBE_VLESS2_RESTART_RECHECK_COOLDOWN_SECONDS:
        return False
    if _vless_traffic_guard_active(
        f'{_pool_proto_label(route_proto)} core restart recheck',
        log=True,
        hold_seconds=YOUTUBE_STREAM_GUARD_FAILOVER_HOLD_SECONDS,
    ):
        return False
    youtube_core_restart_state['last_restart'] = now
    _write_runtime_log(
        f'YouTube failover: {_pool_proto_label(route_proto)} failed confirmation; '
        f'restarting core proxy before trying another key. Last confirmation: {previous_message}'
    )
    try:
        _write_all_proxy_core_config()
        result = subprocess.run(
            [CORE_PROXY_SERVICE_SCRIPT, 'restart'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            _write_runtime_log(f'YouTube failover: core proxy restart returned code {result.returncode}.')
            return False
        time.sleep(6)
    except Exception as exc:
        _write_runtime_log(f'YouTube failover: core proxy restart before key switch failed: {exc}')
        return False

    confirm_ok, confirm_message = _confirm_youtube_key(route_proto)
    if not confirm_ok:
        _write_runtime_log(f'YouTube failover: restart did not restore current key: {confirm_message}')
        return False

    state = _youtube_failover_state(route_proto)
    state['last_ok'] = time.time()
    state['last_fail'] = 0.0
    state['consecutive_failures'] = 0
    _record_key_probe(route_proto, active_key, yt_ok=True)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    _write_runtime_log(
        f'YouTube failover: core proxy restart restored current {_pool_proto_label(route_proto)} key; '
        'key switch skipped.'
    )
    return True


def _youtube_failure_is_hard_proxy_failure(message):
    text = str(message or '').casefold()
    return any(
        marker in text
        for marker in (
            'connection reset',
            'recv failure',
            'connection aborted',
            'remote disconnected',
            'unexpected_eof',
            'unexpected eof',
            'ssleoferror',
            'tls eof',
            'eof occurred',
            'connection refused',
            'failed to establish a new connection',
            'прокси-сервер разорвал',
            'разорвал tls',
        )
    )


def _refresh_ipset_after_youtube_recovery(route_proto, reason=''):
    try:
        result = subprocess.run(
            ['/opt/bin/unblock_update.sh'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=IPSET_REFRESH_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode == 0:
            _write_runtime_log(f'YouTube recovery: refreshed ipset after {_pool_proto_label(route_proto)} recovery. {reason}'.strip())
        else:
            _write_runtime_log(f'YouTube recovery: ipset refresh returned code {result.returncode}. {reason}'.strip())
    except Exception as exc:
        _write_runtime_log(f'YouTube recovery: ipset refresh failed after {_pool_proto_label(route_proto)} recovery: {exc}')


def _recover_current_youtube_route_after_hard_failure(route_proto, active_key, message):
    if not _youtube_failure_is_hard_proxy_failure(message):
        return False
    now = time.time()
    last_attempt = float(youtube_hard_failure_recovery_state.get('last_attempt') or 0.0)
    if last_attempt and now - last_attempt < YOUTUBE_VLESS2_HARD_FAILURE_RECOVERY_COOLDOWN_SECONDS:
        return False
    youtube_hard_failure_recovery_state['last_attempt'] = now
    _write_runtime_log(
        f'YouTube recovery: {_pool_proto_label(route_proto)} hard proxy failure detected; '
        f'repairing current key without failover. Last failure: {message}'
    )

    recovered = False
    if route_proto in ('vless', 'vless2'):
        try:
            repaired = _repair_active_reality_endpoint(route_proto, message, service='youtube')
        except Exception as exc:
            repaired = False
            _write_runtime_log(f'YouTube recovery: endpoint repair failed: {exc}')
        if repaired:
            confirm_ok, confirm_message = _confirm_youtube_key(route_proto)
            if confirm_ok:
                recovered = True
            else:
                _write_runtime_log(f'YouTube recovery: endpoint repair did not restore current key: {confirm_message}')

    if not recovered:
        recovered = _restart_core_proxy_and_recheck_youtube(route_proto, active_key, message)

    if recovered:
        state = _youtube_failover_state(route_proto)
        state['last_ok'] = time.time()
        state['last_fail'] = 0.0
        state['consecutive_failures'] = 0
        _record_key_probe(route_proto, active_key, yt_ok=True)
        _invalidate_web_status_cache()
        _invalidate_key_status_cache()
        _refresh_ipset_after_youtube_recovery(route_proto, 'current key kept')
        _write_runtime_log(f'YouTube recovery: current {_pool_proto_label(route_proto)} key restored; failover skipped.')
        return True

    return False


def _attempt_youtube_failover():
    route_proto = _youtube_route_protocol()
    if route_proto not in YOUTUBE_ROUTE_PROTOCOLS:
        return False
    state = _youtube_failover_state(route_proto)
    now = time.time()
    if not YOUTUBE_VLESS2_FAILOVER_ENABLED:
        return False
    if state['in_progress']:
        return False
    if globals().get('pool_probe_lock') and pool_probe_lock.locked():
        return False
    if state['last_attempt'] and now - state['last_attempt'] < YOUTUBE_VLESS2_FAILOVER_SWITCH_COOLDOWN_SECONDS:
        return False

    current_keys = _load_current_keys()
    active_key = (current_keys.get(route_proto) or '').strip()
    if not active_key:
        state['last_fail'] = 0.0
        return False
    cached_active_probe = _load_key_probe_cache().get(_hash_key(active_key), {})
    cached_fail_since = 0.0
    cached_youtube_state = _youtube_probe_state(cached_active_probe)
    if cached_youtube_state == 'warn':
        state['last_fail'] = 0.0
        state['consecutive_failures'] = 0
        return False
    if isinstance(cached_active_probe, dict) and cached_youtube_state == 'fail':
        try:
            cached_fail_since = float(cached_active_probe.get('ts') or 0.0)
        except Exception:
            cached_fail_since = 0.0
    if _recent_probe_ok(cached_active_probe, 'yt_ok', YOUTUBE_VLESS2_FAILOVER_RECENT_SUCCESS_TTL):
        state['last_fail'] = 0.0
        state['consecutive_failures'] = 0
        return False
    if (
        cached_youtube_state != 'fail' and
        _youtube_stream_guard_active(
            route_proto,
            f'{_pool_proto_label(route_proto)} failover idle check',
            log=False,
            hold_seconds=YOUTUBE_STREAM_GUARD_FAILOVER_HOLD_SECONDS,
        )
    ):
        state['last_ok'] = now
        state['last_fail'] = 0.0
        state['consecutive_failures'] = 0
        return False

    yt_metrics = {}
    ok, message = _check_youtube_protocol_for_background(route_proto, metrics=yt_metrics)
    if ok is None:
        _write_runtime_log(
            f'YouTube failover: {_pool_proto_label(route_proto)} health worker did not return a result; key switch deferred.'
        )
        return False
    if ok:
        state['last_ok'] = now
        state['last_fail'] = 0.0
        state['consecutive_failures'] = 0
        _record_key_probe(route_proto, active_key, yt_ok=True, **yt_metrics)
        return False

    if _recover_current_youtube_route_after_hard_failure(route_proto, active_key, message):
        return False

    if not state['last_fail']:
        state['last_fail'] = cached_fail_since or now
    if now - state['last_fail'] < YOUTUBE_VLESS2_FAILOVER_GRACE_SECONDS:
        return False

    confirm_ok, confirm_message = _confirm_youtube_key(route_proto)
    if confirm_ok is None:
        _write_runtime_log(
            f'YouTube failover: {_pool_proto_label(route_proto)} confirmation is unavailable; key switch deferred.'
        )
        return False
    if confirm_ok:
        state['last_ok'] = time.time()
        state['last_fail'] = 0.0
        state['consecutive_failures'] = 0
        _record_key_probe(route_proto, active_key, yt_ok=True)
        return False
    if (
        route_proto in ('vless', 'vless2') and
        not _vless_traffic_guard_active(
            f'{_pool_proto_label(route_proto)} endpoint repair',
            log=True,
            hold_seconds=YOUTUBE_STREAM_GUARD_FAILOVER_HOLD_SECONDS,
        )
    ):
        try:
            repaired = _repair_active_reality_endpoint(route_proto, confirm_message, service='youtube')
        except Exception as exc:
            repaired = False
            _write_runtime_log(f'YouTube failover: active endpoint repair failed: {exc}')
        if repaired:
            confirm_ok, confirm_message = _confirm_youtube_key(route_proto)
            if confirm_ok is None:
                _write_runtime_log(
                    f'YouTube failover: {_pool_proto_label(route_proto)} confirmation is unavailable after endpoint repair; '
                    'key switch deferred.'
                )
                return False
            if confirm_ok:
                state['last_ok'] = time.time()
                state['last_fail'] = 0.0
                state['consecutive_failures'] = 0
                _record_key_probe(route_proto, active_key, yt_ok=True)
                _invalidate_web_status_cache()
                _invalidate_key_status_cache()
                _write_runtime_log(
                    f'YouTube failover: Reality endpoint repair restored current {_pool_proto_label(route_proto)} key; '
                    'key switch skipped.'
                )
                return False
            _write_runtime_log(f'YouTube failover: endpoint repair did not restore current key: {confirm_message}')
    if _restart_core_proxy_and_recheck_youtube(route_proto, active_key, confirm_message):
        return False

    state['consecutive_failures'] = int(state.get('consecutive_failures') or 0) + 1
    if state['consecutive_failures'] < YOUTUBE_VLESS2_FAILOVER_CONSECUTIVE_FAILURES:
        _write_runtime_log(
            f'YouTube failover: {_pool_proto_label(route_proto)} failed confirmation '
            f'{state["consecutive_failures"]}/{YOUTUBE_VLESS2_FAILOVER_CONSECUTIVE_FAILURES}; '
            'current key is kept until failures repeat.'
        )
        return False

    _record_key_probe(route_proto, active_key, yt_ok=False, **yt_metrics)
    _invalidate_key_status_cache()
    state['in_progress'] = True
    state['last_attempt'] = now
    original_key = active_key
    try:
        pools = _load_key_pools()
        candidates = _key_pool_store().failover_candidates(
            pools,
            route_proto,
            active_key,
            protocols=(route_proto,),
            key_probe_cache=_load_key_probe_cache(),
            hash_key=_hash_key,
            service='youtube',
        )
        if not candidates:
            _write_runtime_log(f'YouTube failover: no {_pool_proto_label(route_proto)} pool candidates are available.')
            return False

        _write_runtime_log(
            f'YouTube failover: current {_pool_proto_label(route_proto)} key failed YouTube check; '
            f'testing {_pool_proto_label(route_proto)} pool candidates. Last confirmation: {confirm_message}'
        )
        remaining = list(candidates)
        while remaining and not shutdown_requested.is_set():
            candidate = _find_pool_failover_candidate(remaining, service='youtube')
            if not candidate:
                _write_runtime_log('YouTube failover: no candidate passed temporary xray checks.')
                break

            proto, key_value, tg_ok, yt_ok = candidate
            remaining = [(item_proto, item_key) for item_proto, item_key in remaining if item_key != key_value]
            if proto != route_proto:
                continue
            duplicate_active_proto = next(
                (
                    other_proto for other_proto, other_key in current_keys.items()
                    if other_proto != route_proto and str(other_key or '').strip() == key_value
                ),
                '',
            )
            if duplicate_active_proto:
                _write_runtime_log(
                    f'YouTube failover: candidate {_hash_key(key_value)[:12]} skipped because it is already active '
                    f'in {_pool_proto_label(duplicate_active_proto)}.'
                )
                continue

            key_hash = _hash_key(key_value)[:12]
            allow_guard_bypass = bool(
                cached_youtube_state == 'fail' and
                int(state.get('consecutive_failures') or 0) >= YOUTUBE_VLESS2_FAILOVER_CONSECUTIVE_FAILURES
            )
            other_traffic_guarded = _vless_traffic_guard_active(
                f'{_pool_proto_label(route_proto)} key switch',
                log=True,
                hold_seconds=YOUTUBE_STREAM_GUARD_FAILOVER_HOLD_SECONDS,
                exclude_proto=route_proto,
            )
            if other_traffic_guarded:
                state['last_attempt'] = 0.0
                _write_runtime_log(
                    f'YouTube failover: candidate {key_hash} is ready, '
                    'but switching is deferred because another Vless route has active traffic.'
                )
                return False
            if _youtube_stream_guard_active(
                route_proto,
                f'{_pool_proto_label(route_proto)} key switch',
                log=not allow_guard_bypass,
                hold_seconds=YOUTUBE_STREAM_GUARD_FAILOVER_HOLD_SECONDS,
            ):
                if allow_guard_bypass:
                    _write_runtime_log(
                        f'YouTube failover: bypassing stream guard for candidate {key_hash} '
                        f'because active {_pool_proto_label(route_proto)} key has confirmed hard failure.'
                    )
                else:
                    state['last_attempt'] = 0.0
                    _write_runtime_log(
                        f'YouTube failover: candidate {key_hash} is ready, '
                        f'but switching is deferred because {_pool_proto_label(route_proto)} traffic is active.'
                    )
                    return False
            try:
                result = _install_key_for_protocol(route_proto, key_value, verify=False)
            except Exception as exc:
                _record_key_probe(route_proto, key_value, tg_ok=tg_ok, yt_ok=False)
                _write_runtime_log(f'YouTube failover: failed to install candidate {key_hash}: {exc}')
                continue

            confirm_ok, confirm_message = _confirm_youtube_key(route_proto)
            if confirm_ok is None:
                _restore_youtube_key_after_failed_failover(route_proto, original_key)
                _write_runtime_log(
                    f'YouTube failover: candidate {key_hash} was not confirmed because the health worker is unavailable; '
                    'original key restored.'
                )
                return False
            if not confirm_ok:
                _record_key_probe(route_proto, key_value, tg_ok=tg_ok, yt_ok=False)
                _write_runtime_log(
                    f'YouTube failover: candidate {key_hash} passed temporary check '
                    f'but failed on permanent port: {confirm_message}'
                )
                continue

            if proxy_mode == route_proto:
                tg_ok, tg_message = _check_telegram_api_for_background(
                    proxy_settings.get(route_proto),
                    connect_timeout=AUTO_FAILOVER_CHECK_CONNECT_TIMEOUT,
                    read_timeout=AUTO_FAILOVER_CHECK_READ_TIMEOUT,
                )
                if tg_ok is None:
                    _restore_youtube_key_after_failed_failover(route_proto, original_key)
                    _write_runtime_log(
                        f'YouTube failover: candidate {key_hash} was not confirmed because Telegram health worker is unavailable; '
                        'original key restored.'
                    )
                    return False
                if not tg_ok:
                    _record_key_probe(route_proto, key_value, tg_ok=False, yt_ok=True)
                    _write_runtime_log(
                        f'YouTube failover: candidate {key_hash} has YouTube, '
                        f'but Telegram is required because bot mode is {_pool_proto_label(route_proto)}: {tg_message}'
                    )
                    continue

            _set_active_key(route_proto, key_value)
            _audit_key_switch('youtube_auto_failover', route_proto, key_value, confirm_message)
            _record_key_probe(route_proto, key_value, tg_ok=tg_ok, yt_ok=True)
            _invalidate_web_status_cache()
            _invalidate_key_status_cache()
            state['last_ok'] = time.time()
            state['last_fail'] = 0.0
            state['consecutive_failures'] = 0
            _write_runtime_log(
                f'YouTube failover: switched {_pool_proto_label(route_proto)} to {key_hash}; '
                f'YouTube is available on permanent port. {result}'
            )
            return True

        _restore_youtube_key_after_failed_failover(route_proto, original_key)
        _invalidate_web_status_cache()
        _invalidate_key_status_cache()
        return False
    finally:
        _memory_cleanup('youtube failover finished', force=True, clear_status=True)
        state['in_progress'] = False


def _attempt_youtube_vless2_failover():
    return _attempt_youtube_failover()


def _run_auto_failover_cycle():
    ran = False
    try:
        should_run, reason = _auto_failover_should_run()
        if not should_run:
            _auto_failover_idle_log(reason)
        elif _background_task_allowed(
            'Telegram auto-failover',
            allow_high_rss=reason in ('pending failure', 'Telegram polling stopped'),
        ):
            ran, _result = _run_coordinated_background_task(
                'Telegram auto-failover',
                _attempt_auto_failover,
            )
    except Exception as exc:
        _write_runtime_log(f'Auto-failover error: {exc}')
    finally:
        if ran:
            _memory_cleanup('Telegram auto-failover cycle', clear_status=False, log=False)


def _run_youtube_failover_cycle():
    if not YOUTUBE_VLESS2_FAILOVER_ENABLED or not _app_mode_pool_enabled():
        return
    ran = False
    try:
        if _background_task_allowed('YouTube failover', task_class='critical'):
            ran, _result = _run_coordinated_background_task(
                'YouTube failover',
                _attempt_youtube_vless2_failover,
            )
    except Exception as exc:
        _write_runtime_log(f'YouTube failover error: {exc}')
    finally:
        if ran:
            _memory_cleanup('YouTube failover cycle', clear_status=False, log=False)


token = getattr(config, 'token', '') or '0:WEBONLY_DISABLED'
TELEGRAM_BOT_NUM_THREADS = max(1, int(getattr(config, 'telegram_bot_num_threads', 1)))
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
localportsh_tproxy = str(getattr(config, 'localportsh_tproxy', 11802))
localportvmess_tproxy = str(getattr(config, 'localportvmess_tproxy', 11815))
localportvless_tproxy = str(getattr(config, 'localportvless_tproxy', 11812))
localportvless2_tproxy = str(getattr(config, 'localportvless2_tproxy', 11814))
localporttrojan_tproxy = str(getattr(config, 'localporttrojan_tproxy', 11829))
dnsovertlsport = config.dnsovertlsport
dnsoverhttpsport = config.dnsoverhttpsport

class _CommandWorkerTeleBot:
    def message_handler(self, *args, **kwargs):
        return lambda func: func

    def callback_query_handler(self, *args, **kwargs):
        return lambda func: func


class _TelegramPollingExceptionHandler:
    _MARK_INTERVAL_SECONDS = 10.0

    def __init__(self):
        self._lock = threading.Lock()
        self._last_marked_at = None

    def handle(self, exception):
        if not _is_telegram_connectivity_error(exception):
            return False
        globals()['bot_polling'] = False
        now = time.monotonic()
        with self._lock:
            if (
                self._last_marked_at is not None and
                now - self._last_marked_at < self._MARK_INTERVAL_SECONDS
            ):
                return False
            self._last_marked_at = now
        try:
            _mark_active_telegram_failure(exception)
            _reset_telegram_http_session('internal polling error')
        except Exception as handler_error:
            _write_runtime_log(f'Telegram polling exception handler failed: {handler_error}')
        return False


_telegram_polling_exception_handler = _TelegramPollingExceptionHandler()


def _create_telebot(token_value):
    try:
        return telebot.TeleBot(
            token_value,
            num_threads=TELEGRAM_BOT_NUM_THREADS,
            exception_handler=_telegram_polling_exception_handler,
        )
    except TypeError:
        try:
            return telebot.TeleBot(
                token_value,
                exception_handler=_telegram_polling_exception_handler,
            )
        except TypeError:
            return telebot.TeleBot(token_value)


bot = _CommandWorkerTeleBot() if COMMAND_WORKER_MODE else _create_telebot(token)
sid = "0"
PROXY_MODE_FILE = '/opt/etc/bot_proxy_mode'
BOT_AUTOSTART_FILE = '/opt/etc/bot_autostart'
TELEGRAM_COMMAND_JOB_FILE = '/opt/etc/bot/telegram_command_job.json'
TELEGRAM_COMMAND_RESULT_FILE = '/opt/etc/bot/telegram_command_result.json'
WEB_COMMAND_STATE_FILE = '/opt/etc/bot/web_command_state.json'
POOL_PROBE_RESUME_FILE = '/opt/etc/bot/pool_probe_resume.json'
COMMAND_JOB_STALE_AFTER = 1800
TELEGRAM_RESULT_RETRY_INTERVAL = 30

WEB_STATUS_CACHE_TTL = 60
KEY_STATUS_CACHE_TTL = 60
STATUS_CACHE_TTL = min(WEB_STATUS_CACHE_TTL, KEY_STATUS_CACHE_TTL)
STATUS_REFRESH_MIN_INTERVAL_SECONDS = max(
    60.0,
    float(getattr(config, 'status_refresh_min_interval_seconds', 180.0)),
)
STATUS_REFRESH_PENDING_MIN_INTERVAL_SECONDS = max(
    30.0,
    float(getattr(config, 'status_refresh_pending_min_interval_seconds', min(60.0, STATUS_REFRESH_MIN_INTERVAL_SECONDS))),
)
ACTIVE_MODE_STATUS_DURING_POOL_TTL = 30
TELEGRAM_TRANSIENT_OK_CACHE_TTL = int(getattr(config, 'telegram_transient_ok_cache_ttl', 180))
ACTIVE_STATUS_RECENT_SUCCESS_TTL = max(60, int(getattr(config, 'active_status_recent_success_ttl', 900)))
WEB_STATUS_API_CACHE_TTL = float(getattr(config, 'web_status_api_cache_ttl', 30.0))
WEB_POOLS_API_CACHE_TTL = float(getattr(config, 'web_pools_api_cache_ttl', 45.0))
WEB_POOLS_API_CACHE_MAX_ENTRIES = max(1, min(3, int(getattr(config, 'web_pools_api_cache_max_entries', 3))))
WEB_POOL_SNAPSHOT_WORKER_ENABLED = bool(getattr(config, 'web_pool_snapshot_worker_enabled', True))
WEB_POOL_SNAPSHOT_WORKER_TIMEOUT_SECONDS = max(
    2.0,
    float(getattr(config, 'web_pool_snapshot_worker_timeout_seconds', 8.0)),
)
WEB_SERVICE_ROUTES_WORKER_ENABLED = bool(getattr(config, 'web_service_routes_worker_enabled', True))
WEB_SERVICE_ROUTES_WORKER_TIMEOUT_SECONDS = max(
    2.0,
    float(getattr(config, 'web_service_routes_worker_timeout_seconds', 8.0)),
)
SERVICE_ROUTE_INTERSECTIONS_CACHE_TTL = float(getattr(config, 'service_route_intersections_cache_ttl', 60.0))
ROUTER_HEALTH_CACHE_TTL = float(getattr(config, 'router_health_cache_ttl', 30.0))
ROUTER_HEALTH_DNS_CACHE_TTL = float(getattr(config, 'router_health_dns_cache_ttl', 45.0))
ROUTER_HEALTH_NDMC_CACHE_TTL = float(getattr(config, 'router_health_ndmc_cache_ttl', 30.0))
ROUTER_HEALTH_RELATED_PROCESS_CACHE_TTL = float(getattr(config, 'router_health_related_process_cache_ttl', 45.0))
ROUTER_HEALTH_CPU_SMOOTHING_FACTOR = min(
    1.0,
    max(0.0, float(getattr(config, 'router_health_cpu_smoothing_factor', 0.35))),
)
ROUTER_METRICS_HISTORY_LIMIT = int(getattr(config, 'router_metrics_history_limit', 120))
ROUTER_METRICS_WARN_BOT_RSS_KB = int(getattr(config, 'router_metrics_warn_bot_rss_kb', 65 * 1024))
ROUTER_METRICS_CRITICAL_BOT_RSS_KB = int(getattr(config, 'router_metrics_critical_bot_rss_kb', 87040))
ROUTER_METRICS_WARN_LOAD1 = float(getattr(config, 'router_metrics_warn_load1', 3.0))
ROUTER_METRICS_COMPACT_CACHE_TTL = max(1.0, float(getattr(config, 'router_metrics_compact_cache_ttl', 8.0)))
WEB_STATUS_STARTUP_GRACE_PERIOD = 45
KEY_PROBE_MAX_PER_RUN = None
POOL_PROBE_ACTIVE_ONLY = False
POOL_PROBE_DELAY_SECONDS = float(getattr(config, 'pool_probe_delay_seconds', 3.0))
POOL_PROBE_MIN_AVAILABLE_KB = int(getattr(config, 'pool_probe_min_available_kb', 160000))
POOL_PROBE_SLOW_AVAILABLE_KB = max(
    POOL_PROBE_MIN_AVAILABLE_KB,
    int(getattr(config, 'pool_probe_slow_available_kb', POOL_PROBE_MIN_AVAILABLE_KB)),
)
POOL_PROBE_PAUSE_AVAILABLE_KB = max(
    0,
    int(getattr(config, 'pool_probe_pause_available_kb', min(125000, POOL_PROBE_MIN_AVAILABLE_KB))),
)
POOL_PROBE_SLOW_MEMORY_DELAY_SECONDS = max(
    0.0,
    float(getattr(config, 'pool_probe_slow_memory_delay_seconds', 3.0)),
)
POOL_PROBE_CPU_GUARD_ENABLED = bool(getattr(config, 'pool_probe_cpu_guard_enabled', True))
POOL_PROBE_MAX_CPU_PERCENT = max(0.0, float(getattr(config, 'pool_probe_max_cpu_percent', 45.0)))
POOL_PROBE_CPU_SAMPLE_SECONDS = max(0.1, float(getattr(config, 'pool_probe_cpu_sample_seconds', 0.35)))
POOL_PROBE_HIGH_CPU_DELAY_SECONDS = max(1.0, float(getattr(config, 'pool_probe_high_cpu_delay_seconds', 8.0)))
POOL_PROBE_HIGH_CPU_MAX_WAIT_SECONDS = max(0.0, float(getattr(config, 'pool_probe_high_cpu_max_wait_seconds', 120.0)))
POOL_PROBE_MAX_LOAD1 = max(0.0, float(getattr(config, 'pool_probe_max_load1', 2.0)))
POOL_PROBE_HIGH_LOAD_DELAY_SECONDS = max(1.0, float(getattr(config, 'pool_probe_high_load_delay_seconds', 10.0)))
POOL_PROBE_HIGH_LOAD_MAX_WAIT_SECONDS = max(0.0, float(getattr(config, 'pool_probe_high_load_max_wait_seconds', 120.0)))
BACKGROUND_TASK_CPU_GUARD_ENABLED = bool(getattr(config, 'background_task_cpu_guard_enabled', True))
BACKGROUND_TASK_MAX_CPU_PERCENT = max(0.0, float(getattr(config, 'background_task_max_cpu_percent', 45.0)))
BACKGROUND_TASK_CPU_SAMPLE_SECONDS = max(0.1, float(getattr(config, 'background_task_cpu_sample_seconds', 0.35)))
BACKGROUND_TASK_CPU_CACHE_TTL_SECONDS = max(
    0.0,
    float(getattr(config, 'background_task_cpu_cache_ttl_seconds', 20.0)),
)
BACKGROUND_TASK_MAX_BOT_RSS_KB = max(0, int(getattr(config, 'background_task_max_bot_rss_kb', 65 * 1024)))
BACKGROUND_TASK_CRITICAL_MAX_BOT_RSS_KB = max(
    BACKGROUND_TASK_MAX_BOT_RSS_KB,
    int(getattr(config, 'background_task_critical_max_bot_rss_kb', 70 * 1024)),
)
BACKGROUND_TASK_MAX_PROGRAM_RSS_KB = max(0, int(getattr(config, 'background_task_max_program_rss_kb', 100 * 1024)))
BACKGROUND_TASK_CRITICAL_MAX_PROGRAM_RSS_KB = max(
    BACKGROUND_TASK_MAX_PROGRAM_RSS_KB,
    int(getattr(config, 'background_task_critical_max_program_rss_kb', BACKGROUND_TASK_MAX_PROGRAM_RSS_KB)),
)
BACKGROUND_TASK_SKIP_LOG_INTERVAL_SECONDS = max(
    60.0,
    float(getattr(config, 'background_task_skip_log_interval_seconds', 300.0)),
)
BACKGROUND_TASK_BUSY_BACKOFF_SECONDS = max(
    30.0,
    float(getattr(config, 'background_task_busy_backoff_seconds', 180.0)),
)
BACKGROUND_TASK_SLOW_LOG_SECONDS = max(
    0.1,
    float(getattr(config, 'background_task_slow_log_seconds', 1.0)),
)
POOL_PROBE_LOW_MEMORY_DELAY_SECONDS = float(getattr(config, 'pool_probe_low_memory_delay_seconds', 12.0))
POOL_PROBE_LOW_MEMORY_MAX_WAIT_SECONDS = float(getattr(config, 'pool_probe_low_memory_max_wait_seconds', 180.0))
POOL_PROBE_TEST_PORT = str(getattr(config, 'pool_probe_test_port', 10991))
POOL_FAILOVER_TEST_PORT = str(getattr(config, 'pool_failover_test_port', int(POOL_PROBE_TEST_PORT) + 64))
POOL_FAILOVER_PROCESS_WORKER_ENABLED = bool(getattr(config, 'pool_failover_process_worker_enabled', True))
POOL_FAILOVER_PROCESS_WORKER_TIMEOUT_SECONDS = max(
    45.0,
    float(getattr(config, 'pool_failover_process_worker_timeout_seconds', 180.0)),
)
POOL_PROBE_BATCH_SIZE_CONFIGURED = hasattr(config, 'pool_probe_batch_size')
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
POOL_PROBE_YOUTUBE_PROFILE = str(getattr(config, 'pool_probe_youtube_profile', 'quick') or 'quick').strip().lower()
POOL_PROBE_QUALITY_ENABLED = bool(getattr(config, 'pool_probe_quality_enabled', True))
POOL_PROBE_QUALITY_DOWNLOAD_URL = str(
    getattr(config, 'pool_probe_quality_download_url', 'https://speed.cloudflare.com/__down?bytes={bytes}') or ''
).strip()
POOL_PROBE_QUALITY_DOWNLOAD_BYTES = max(0, int(getattr(config, 'pool_probe_quality_download_bytes', 524288)))
POOL_PROBE_QUALITY_MIN_AVAILABLE_KB = max(
    0,
    int(getattr(config, 'pool_probe_quality_min_available_kb', POOL_PROBE_SLOW_AVAILABLE_KB)),
)
POOL_PROBE_QUALITY_MAX_SAMPLES_PER_RUN = max(
    0,
    int(getattr(config, 'pool_probe_quality_max_samples_per_run', 6)),
)
POOL_PROBE_QUALITY_DOWNLOAD_CONNECT_TIMEOUT = float(
    getattr(config, 'pool_probe_quality_download_connect_timeout', POOL_PROBE_RETRY_CONNECT_TIMEOUT)
)
POOL_PROBE_QUALITY_DOWNLOAD_READ_TIMEOUT = float(
    getattr(config, 'pool_probe_quality_download_read_timeout', min(12.0, max(4.0, POOL_PROBE_RETRY_READ_TIMEOUT)))
)
POOL_PROBE_QUALITY_STABLE_LATENCY_MS = max(
    1,
    int(getattr(config, 'pool_probe_quality_stable_latency_ms', _YOUTUBE_QUALITY_DEFAULT_STABLE_LATENCY_MS)),
)
POOL_PROBE_QUALITY_FAST_LATENCY_MS = max(
    1,
    int(getattr(config, 'pool_probe_quality_fast_latency_ms', _YOUTUBE_QUALITY_DEFAULT_FAST_LATENCY_MS)),
)
POOL_PROBE_QUALITY_1600P_MIN_MBPS = max(
    0.1,
    float(getattr(config, 'pool_probe_quality_1600p_min_mbps', _YOUTUBE_QUALITY_DEFAULT_1600P_MBPS)),
)
POOL_PROBE_QUALITY_4K_MIN_MBPS = max(
    POOL_PROBE_QUALITY_1600P_MIN_MBPS,
    float(getattr(config, 'pool_probe_quality_4k_min_mbps', _YOUTUBE_QUALITY_DEFAULT_4K_MBPS)),
)
POOL_PROBE_SINGLE_TIMEOUT_SECONDS = max(
    8.0,
    POOL_PROBE_TG_CONNECT_TIMEOUT + POOL_PROBE_TG_READ_TIMEOUT +
    POOL_PROBE_HTTP_CONNECT_TIMEOUT + POOL_PROBE_HTTP_READ_TIMEOUT +
    POOL_PROBE_RETRY_CONNECT_TIMEOUT + POOL_PROBE_RETRY_READ_TIMEOUT +
    POOL_PROBE_TG_CONNECT_TIMEOUT + POOL_PROBE_TG_READ_TIMEOUT +
    POOL_PROBE_RETRY_CONNECT_TIMEOUT + POOL_PROBE_RETRY_READ_TIMEOUT +
    (POOL_PROBE_QUALITY_DOWNLOAD_CONNECT_TIMEOUT + POOL_PROBE_QUALITY_DOWNLOAD_READ_TIMEOUT if POOL_PROBE_QUALITY_ENABLED else 0) +
    3.0,
)
POOL_PROBE_BATCH_TIMEOUT_SECONDS = float(
    getattr(config, 'pool_probe_batch_timeout_seconds', POOL_PROBE_SINGLE_TIMEOUT_SECONDS + 5.0)
)
POOL_PROBE_TIMEOUTS = (
    POOL_PROBE_TG_CONNECT_TIMEOUT, POOL_PROBE_TG_READ_TIMEOUT,
    POOL_PROBE_HTTP_CONNECT_TIMEOUT, POOL_PROBE_HTTP_READ_TIMEOUT,
    POOL_PROBE_CUSTOM_CONNECT_TIMEOUT, POOL_PROBE_CUSTOM_READ_TIMEOUT,
    POOL_PROBE_SINGLE_TIMEOUT_SECONDS, POOL_PROBE_BATCH_TIMEOUT_SECONDS,
    POOL_PROBE_RETRY_CONNECT_TIMEOUT, POOL_PROBE_RETRY_READ_TIMEOUT,
)
MEMORY_WATCHDOG_ENABLED = bool(getattr(config, 'memory_watchdog_enabled', True))
MEMORY_WATCHDOG_RSS_LIMIT_KB = max(0, int(getattr(config, 'memory_watchdog_rss_limit_kb', 110 * 1024)))
MEMORY_WATCHDOG_RSS_SOFT_KB = max(0, int(getattr(config, 'memory_watchdog_rss_soft_kb', 85 * 1024)))
MEMORY_WATCHDOG_CHECK_INTERVAL = max(15.0, float(getattr(config, 'memory_watchdog_check_interval', 60.0)))
MEMORY_WATCHDOG_MIN_UPTIME_SECONDS = max(30.0, float(getattr(config, 'memory_watchdog_min_uptime_seconds', 300.0)))
MEMORY_WATCHDOG_RESTART_COOLDOWN_SECONDS = max(
    300.0,
    float(getattr(config, 'memory_watchdog_restart_cooldown_seconds', 1800.0)),
)
# Проверка пула работает в отдельном процессе. Штатный рестарт основного
# бота ради RSS не нужен и опасен при активном трафике.
MEMORY_WATCHDOG_IDLE_RESTART_RSS_KB = 0
MEMORY_WATCHDOG_IDLE_RESTART_HOLD_SECONDS = 0.0
POOL_PROBE_DEFAULT_MAX_PROCESS_RSS_KB = 65 * 1024
POOL_PROBE_MAX_PROCESS_RSS_KB = max(
    0,
    int(getattr(config, 'pool_probe_max_process_rss_kb', POOL_PROBE_DEFAULT_MAX_PROCESS_RSS_KB)),
)
POOL_PROBE_PROCESS_WORKER_ENABLED = bool(getattr(config, 'pool_probe_process_worker_enabled', True))
POOL_PROBE_INPROCESS_FALLBACK_ENABLED = bool(getattr(config, 'pool_probe_inprocess_fallback_enabled', False))
POOL_PROBE_PROCESS_WORKER_POLL_SECONDS = max(
    1.0,
    float(getattr(config, 'pool_probe_process_worker_poll_seconds', 2.0)),
)
POOL_PROBE_CACHE_APPLY_TIMEOUT_SECONDS = max(
    5.0,
    float(getattr(config, 'pool_probe_cache_apply_timeout_seconds', 30.0)),
)
MEMORY_TIMELINE_ENABLED = bool(getattr(config, 'memory_timeline_enabled', False))
MEMORY_TIMELINE_PATH = str(getattr(config, 'memory_timeline_path', '/opt/tmp/bypass_memory_timeline.jsonl') or '').strip()
MEMORY_TIMELINE_INTERVAL_SECONDS = max(
    30.0,
    float(getattr(config, 'memory_timeline_interval_seconds', 60.0)),
)
MEMORY_TIMELINE_MAX_EVENTS = max(30, int(getattr(config, 'memory_timeline_max_events', 720)))
MEMORY_TIMELINE_TRIM_MIN_INTERVAL_SECONDS = max(
    60.0,
    float(getattr(config, 'memory_timeline_trim_min_interval_seconds', 300.0)),
)
MEMORY_MALLOC_TRIM_ENABLED = bool(getattr(config, 'memory_malloc_trim_enabled', True))
MEMORY_MALLOC_TRIM_COOLDOWN_SECONDS = max(
    5.0,
    float(getattr(config, 'memory_malloc_trim_cooldown_seconds', 20.0)),
)
MEMORY_MALLOC_TRIM_MIN_RSS_KB = max(
    0,
    int(getattr(config, 'memory_malloc_trim_min_rss_kb', MEMORY_WATCHDOG_RSS_SOFT_KB)),
)
# Не выполняем тяжёлый GC на обычных API-запросах около целевой полки.
# Очистка допускается только при soft-пороге watchdog.
MEMORY_CLEANUP_RSS_KB = MEMORY_WATCHDOG_RSS_SOFT_KB
APP_BRANCH_LABEL = 'main'
APP_BRANCH_DESCRIPTION = 'единая версия'
APP_MODE_LABEL = 'Режим бота'
APP_MODE_NOUN = 'режим бота'
APP_START_IDLE_LABEL = 'Запустить бота'
APP_START_REPEAT_LABEL = 'Повторить запуск бота'
APP_START_RESULT = 'Команда запуска принята. Если Telegram API доступен, бот начнет отвечать через несколько секунд'
APP_QUICK_START_NOTE = 'После установки ключей можно сразу запустить или перезапустить Telegram-бота'
APP_PROXY_USER_LABEL = 'Бот'
APP_RUNTIME_MODE_FILE = app_runtime_mode.APP_RUNTIME_MODE_FILE
APP_RUNTIME_MODES = app_runtime_mode.APP_RUNTIME_MODES
APP_DEFAULT_RUNTIME_MODE = getattr(config, 'app_runtime_mode', 'advanced')
BOT_SOURCE_PATH = os.path.abspath(__file__)
BOT_DIR = os.path.dirname(BOT_SOURCE_PATH)
STATIC_DIR = os.path.join(BOT_DIR, 'static')
README_PATH = os.path.join(BOT_DIR, 'README.md')
BOT_SERVICE_SCRIPT = '/opt/etc/init.d/S99telegram_bot'
XRAY_SERVICE_SCRIPT = '/opt/etc/init.d/S24xray'
V2RAY_SERVICE_SCRIPT = '/opt/etc/init.d/S24v2ray'
XRAY_CONFIG_DIR = '/opt/etc/xray'
V2RAY_CONFIG_DIR = '/opt/etc/v2ray'
CORE_PROXY_CONFIG_DIR = XRAY_CONFIG_DIR if os.path.exists(XRAY_SERVICE_SCRIPT) else V2RAY_CONFIG_DIR
CORE_PROXY_SERVICE_SCRIPT = XRAY_SERVICE_SCRIPT if os.path.exists(XRAY_SERVICE_SCRIPT) else V2RAY_SERVICE_SCRIPT
CORE_PROXY_CONFIG_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'config.json')
CORE_PROXY_ERROR_LOG = os.path.join(CORE_PROXY_CONFIG_DIR, 'error.log')
CORE_PROXY_ACCESS_LOG = os.path.join(CORE_PROXY_CONFIG_DIR, 'access.log')
core_proxy_config_write_lock = threading.RLock()
UDP_POLICY_CONFIG_PATH = '/opt/etc/bot/udp_policy.conf'
CALL_SIGNAL_ROUTES_PATH = '/opt/etc/bot/call_signal_routes.txt'
UDP_QUIC_BLOCK_SHADOWSOCKS_ENABLED = bool(getattr(config, 'udp_quic_block_shadowsocks_enabled', True))
UDP_QUIC_BLOCK_VMESS_ENABLED = bool(getattr(config, 'udp_quic_block_vmess_enabled', True))
UDP_QUIC_BLOCK_VLESS_ENABLED = bool(getattr(config, 'udp_quic_block_vless_enabled', True))
UDP_QUIC_BLOCK_VLESS2_ENABLED = bool(getattr(config, 'udp_quic_block_vless2_enabled', True))
UDP_QUIC_BLOCK_TROJAN_ENABLED = bool(getattr(config, 'udp_quic_block_trojan_enabled', True))
YOUTUBE_QUIC_POLICY = str(getattr(config, 'youtube_quic_policy', 'auto') or 'auto').strip().lower()
if YOUTUBE_QUIC_POLICY not in ('auto', 'allow', 'block'):
    YOUTUBE_QUIC_POLICY = 'auto'
TELEGRAM_UDP_POLICY = str(getattr(config, 'telegram_udp_policy', 'auto') or 'auto').strip().lower()
if TELEGRAM_UDP_POLICY not in ('auto', 'allow', 'block'):
    TELEGRAM_UDP_POLICY = 'auto'
_REALITY_ENDPOINT_OVERRIDES_RAW = getattr(config, 'reality_endpoint_overrides', {})
REALITY_ENDPOINT_OVERRIDES = {
    str(host or '').strip().lower(): str(endpoint or '').strip()
    for host, endpoint in (_REALITY_ENDPOINT_OVERRIDES_RAW.items() if isinstance(_REALITY_ENDPOINT_OVERRIDES_RAW, dict) else [])
    if str(host or '').strip() and str(endpoint or '').strip()
}
reality_endpoint_runtime_overrides = {}
UDP_QUIC_DRIFT_CHECK_ENABLED = bool(getattr(config, 'udp_quic_drift_check_enabled', True))
UDP_QUIC_DRIFT_CHECK_INTERVAL_SECONDS = max(
    180,
    int(getattr(config, 'udp_quic_drift_check_interval_seconds', 300)),
)
UDP_QUIC_DRIFT_REFRESH_COOLDOWN_SECONDS = max(
    300,
    int(getattr(config, 'udp_quic_drift_refresh_cooldown_seconds', 900)),
)
UDP_QUIC_DRIFT_PRIORITY_REFRESH_COOLDOWN_SECONDS = min(
    UDP_QUIC_DRIFT_REFRESH_COOLDOWN_SECONDS,
    max(60, int(getattr(config, 'udp_quic_drift_priority_refresh_cooldown_seconds', 120))),
)
UDP_QUIC_DRIFT_DNS_CACHE_TTL_SECONDS = max(
    60.0,
    float(getattr(config, 'udp_quic_drift_dns_cache_ttl_seconds', 600.0)),
)
IPSET_REFRESH_COMMAND_TIMEOUT_SECONDS = max(
    240,
    int(getattr(config, 'ipset_refresh_command_timeout_seconds', 420)),
)
UDP_QUIC_DRIFT_SENTINEL_DOMAINS = tuple(getattr(config, 'udp_quic_drift_sentinel_domains', (
    'chatgpt.com',
    'api.openai.com',
    'oaistatic.com',
    'cdn.oaistatic.com',
    'auth.openai.com',
    'challenges.cloudflare.com',
    'claude.ai',
    'discord.com',
    'youtube.com',
    'youtu.be',
    'youtubei.googleapis.com',
    'youtubei-att.googleapis.com',
    'i.ytimg.com',
    'ytimg.com',
    'ggpht.com',
    'googlevideo.com',
)))
UDP_QUIC_DRIFT_PRIORITY_DOMAINS = tuple(getattr(config, 'udp_quic_drift_priority_domains', (
    'youtube.com',
    'youtu.be',
    'youtubei.googleapis.com',
    'youtubei-att.googleapis.com',
    'i.ytimg.com',
    'ytimg.com',
    'ggpht.com',
    'googlevideo.com',
)))
IPV6_BYPASS_FALLBACK_ENABLED = bool(getattr(config, 'ipv6_bypass_fallback_enabled', True))
VMESS_KEY_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'vmess.key')
VLESS_KEY_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'vless.key')
VLESS2_KEY_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'vless2.key')
KEY_SWITCH_AUDIT_LOG = '/opt/etc/bot/key_switch_audit.log'
YOUTUBE_ROUTE_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')
YOUTUBE_STREAM_GUARD_PROTOCOLS = ('vless', 'vless2')
UDP_QUIC_POLICY_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')
TELEGRAM_CALL_LEARNING_ENABLED = bool(getattr(config, 'telegram_call_learning_enabled', False))
TELEGRAM_CALL_LEARNING_DEFAULT_STATE_PATH = '/tmp/bypass_telegram_call_learning.json'
TELEGRAM_CALL_LEARNING_LEGACY_STATE_PATH = '/opt/tmp/bypass_telegram_call_learning.json'
TELEGRAM_CALL_LEARNING_STATE_PATH = str(
    getattr(config, 'telegram_call_learning_state_path', TELEGRAM_CALL_LEARNING_DEFAULT_STATE_PATH)
)
if TELEGRAM_CALL_LEARNING_STATE_PATH == TELEGRAM_CALL_LEARNING_LEGACY_STATE_PATH:
    TELEGRAM_CALL_LEARNING_STATE_PATH = TELEGRAM_CALL_LEARNING_DEFAULT_STATE_PATH
TELEGRAM_CALL_LEARNING_DEFAULT_DURATION_SECONDS = max(
    20,
    int(getattr(config, 'telegram_call_learning_default_duration_seconds', 90)),
)
TELEGRAM_CALL_LEARNING_MAX_DURATION_SECONDS = max(
    TELEGRAM_CALL_LEARNING_DEFAULT_DURATION_SECONDS,
    int(getattr(config, 'telegram_call_learning_max_duration_seconds', 180)),
)
TELEGRAM_CALL_LEARNING_POLL_INTERVAL_SECONDS = max(
    0.5,
    float(getattr(config, 'telegram_call_learning_poll_interval_seconds', 1.0)),
)
TELEGRAM_CALL_LEARNING_AUTO_ENABLED = bool(getattr(config, 'telegram_call_learning_auto_enabled', True))
TELEGRAM_CALL_LEARNING_SCAN_INTERVAL_SECONDS = max(
    1.0,
    float(getattr(config, 'telegram_call_learning_scan_interval_seconds', 5.0)),
)
TELEGRAM_CALL_LEARNING_IDLE_BACKOFF_SECONDS = max(
    TELEGRAM_CALL_LEARNING_SCAN_INTERVAL_SECONDS,
    float(getattr(config, 'telegram_call_learning_idle_backoff_seconds', 60.0)),
)
TELEGRAM_CALL_LEARNING_FAST_SCAN_LIMIT = max(
    1,
    int(getattr(config, 'telegram_call_learning_fast_scan_limit', 3)),
)
TELEGRAM_CALL_LEARNING_MIN_SCORE = max(1, int(getattr(config, 'telegram_call_learning_min_score', 5)))
TELEGRAM_CALL_LEARNING_MIN_PACKETS = max(1, int(getattr(config, 'telegram_call_learning_min_packets', 2)))
TELEGRAM_CALL_LEARNING_MIN_BYTES = max(1, int(getattr(config, 'telegram_call_learning_min_bytes', 240)))
TELEGRAM_CALL_LEARNING_MAX_CANDIDATES = max(1, int(getattr(config, 'telegram_call_learning_max_candidates', 20)))
TELEGRAM_CALL_LEARNING_MAX_SEEN_ADDRESSES = max(
    TELEGRAM_CALL_LEARNING_MAX_CANDIDATES,
    int(getattr(config, 'telegram_call_learning_max_seen_addresses', 512)),
)
TELEGRAM_CALL_LEARNING_APPLY_BY_DEFAULT = bool(getattr(config, 'telegram_call_learning_apply_by_default', True))
TELEGRAM_CALL_LEARNING_CLIENT_TIMEOUT_SECONDS = max(
    30,
    int(getattr(config, 'telegram_call_learning_client_timeout_seconds', 900)),
)
TELEGRAM_CALL_LEARNING_ADDRESS_TIMEOUT_SECONDS = max(
    120,
    int(getattr(config, 'telegram_call_learning_address_timeout_seconds', 14400)),
)
TELEGRAM_CALL_TPROXY_ENABLED = bool(getattr(config, 'telegram_call_tproxy_enabled', False))
TELEGRAM_CALL_LEARNING_CLIENT_IPSET = 'bypass_tg_call_clients'
TELEGRAM_CALL_LEARNING_CLIENT_IPSETS = dict(_TELEGRAM_CALL_LEARNING_CLIENT_IPSETS)
PROTOCOL_DISPLAY_ORDER = ('vless', 'vless2', 'vmess', 'trojan', 'shadowsocks')
TELEGRAM_CALL_LEARNING_PROTOCOL_ORDER = PROTOCOL_DISPLAY_ORDER

bot_ready = False
bot_polling = False
web_httpd = None
shutdown_requested = threading.Event()
UPDATE_MAINTENANCE_PATH = '/tmp/bypass_update_maintenance'
UPDATE_MAINTENANCE_READY_PATH = '/tmp/bypass_update_maintenance.ready'
update_maintenance_requested = threading.Event()
update_maintenance_ready_thread = None
update_maintenance_web_lock = threading.Lock()
update_maintenance_web_requests = 0
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
    'payloads': {},
}
web_pools_api_cache = {
    'timestamp': 0,
    'signature': None,
    'payload': None,
    'entries': {},
}
web_service_routes_cache = {
    'timestamp': 0.0,
    'signature': None,
    'payload': None,
}
WEB_SERVICE_ROUTES_CACHE_TTL_SECONDS = 20.0
pool_summary_cache = {
    'signature': None,
    'summary': None,
}
event_history_api_cache = {
    'signature': None,
    'payload': None,
}
router_metrics_compact_cache = {
    'timestamp': 0.0,
    'payload': None,
}
router_health = router_health_runtime.RouterHealthRuntime(
    cache_ttl=ROUTER_HEALTH_CACHE_TTL,
    dns_cache_ttl=ROUTER_HEALTH_DNS_CACHE_TTL,
    ndmc_cache_ttl=ROUTER_HEALTH_NDMC_CACHE_TTL,
    related_process_cache_ttl=ROUTER_HEALTH_RELATED_PROCESS_CACHE_TTL,
    cpu_smoothing_factor=ROUTER_HEALTH_CPU_SMOOTHING_FACTOR,
)
router_metrics_runtime = router_metrics.RouterMetricsRuntime(
    history_limit=ROUTER_METRICS_HISTORY_LIMIT,
    warn_bot_rss_kb=ROUTER_METRICS_WARN_BOT_RSS_KB,
    critical_bot_rss_kb=ROUTER_METRICS_CRITICAL_BOT_RSS_KB,
    warn_load1=ROUTER_METRICS_WARN_LOAD1,
)
active_mode_status_cache = {
    'timestamp': 0,
    'signature': None,
    'status': None,
}
active_mode_status_cache_lock = threading.Lock()
web_status_api_cache_lock = threading.Lock()
web_pools_api_cache_lock = threading.Lock()
web_pools_api_build_lock = threading.Lock()
web_service_routes_cache_lock = threading.Lock()
web_service_routes_build_lock = threading.Lock()
pool_summary_cache_lock = threading.Lock()
event_history_api_cache_lock = threading.Lock()
router_metrics_compact_cache_lock = threading.Lock()
status_refresh_lock = threading.Lock()
status_refresh_in_progress = set()
status_refresh_last_started_at = {}
status_refresh_last_finished_at = {}
background_cpu_busy_cache_lock = threading.Lock()
background_cpu_busy_cache = {'timestamp': 0.0, 'value': None}
key_pool_lock = threading.RLock()
subscription_state_lock = threading.RLock()
subscription_hwid_lock = threading.Lock()
subscription_hwid_cache = {'value': None, 'checked_at': 0.0}
subscription_auto_refresh_skip_log_at = {'rss': 0.0}
pool_probe_lock = threading.Lock()
pool_apply_lock = threading.Lock()
pool_probe_cancel_event = threading.Event()
pool_probe_resume_lock = threading.Lock()
youtube_cache_confirm_lock = threading.Lock()
vless2_youtube_cache_confirm_lock = youtube_cache_confirm_lock
pool_probe_resume_payload = None
pool_probe_resume_after_cancel = True
pool_probe_low_memory_resume_scheduled = False
pool_probe_process_state = {
    'process': None,
    'input_path': '',
    'progress_path': '',
    'result_path': '',
    'cancel_path': '',
    'progress_signature': None,
}
pool_probe_quality_sample_lock = threading.Lock()
pool_probe_quality_sample_count = 0
pool_probe_progress = _PoolProbeProgress()
process_started_at = time.time()
memory_watchdog_lock = threading.Lock()
memory_watchdog_restart_scheduled = False
memory_watchdog_last_restart_at = 0.0
memory_watchdog_high_rss_since = 0.0
app_service_restart_lock = threading.Lock()
app_service_restart_scheduled = False
memory_timeline_lock = threading.Lock()
memory_timeline_last_sample_at = 0.0
memory_timeline_last_error_at = 0.0
memory_timeline_last_trim_at = 0.0
memory_malloc_trim_lock = threading.Lock()
memory_malloc_trim_last_at = 0.0
memory_malloc_trim_libc = None
memory_malloc_trim_available = None
memory_cleanup_lock = threading.Lock()
memory_cleanup_last_at = 0.0
youtube_edge_prefetch_lock = threading.Lock()
telegram_call_learning_lock = threading.Lock()
telegram_call_learning_cancel_event = threading.Event()
telegram_call_learning_auto_thread = None
telegram_call_learning_state_last_write = 0.0
telegram_call_learning_state_last_digest = ''
telegram_call_learning_state = {
    'enabled': TELEGRAM_CALL_LEARNING_ENABLED,
    'auto_enabled': TELEGRAM_CALL_LEARNING_AUTO_ENABLED,
    'watching': False,
    'running': False,
    'device_ip': '',
    'protocol': '',
    'protocols': [],
    'route_protocols': [],
    'apply': TELEGRAM_CALL_LEARNING_APPLY_BY_DEFAULT,
    'duration_seconds': TELEGRAM_CALL_LEARNING_DEFAULT_DURATION_SECONDS,
    'started_at': 0.0,
    'updated_at': 0.0,
    'finished_at': 0.0,
    'last_scan_at': 0.0,
    'last_apply_at': 0.0,
    'seen_clients': [],
    'candidates': [],
    'added': [],
    'message': '',
    'error': '',
}
telegram_call_learning_route_cache = {
    'signature': None,
    'protocols': [],
}
WEB_UPDATE_COMMANDS = web_commands_runtime.WEB_UPDATE_COMMANDS
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
    'BYPASS_KEENETIC_COMMAND_WORKER',
    'HTTPS_PROXY',
    'HTTP_PROXY',
    'https_proxy',
    'http_proxy',
    'ALL_PROXY',
    'all_proxy',
    'REPO_REF',
    'UPDATE_ARCHIVE_ROOT',
    'RAW_GITHUB_USE_SOCKS',
    'RAW_GITHUB_BYPASS',
    'RAW_GITHUB_SOCKS_NOTICE_SHOWN',
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


def _load_app_runtime_mode():
    return app_runtime_mode.load_app_runtime_mode(
        APP_RUNTIME_MODE_FILE,
        APP_DEFAULT_RUNTIME_MODE,
        log=_write_runtime_log,
    )


def _save_app_runtime_mode(mode):
    return app_runtime_mode.save_app_runtime_mode(mode, APP_RUNTIME_MODE_FILE)


def _app_runtime_mode_label(mode=None):
    return app_runtime_mode.app_runtime_mode_label(mode or _load_app_runtime_mode())


def _app_runtime_mode_description(mode=None):
    return app_runtime_mode.app_runtime_mode_description(mode or _load_app_runtime_mode())


def _app_mode_pool_enabled(mode=None):
    return app_runtime_mode.app_mode_pool_enabled(mode or _load_app_runtime_mode())


def _app_mode_telegram_enabled(mode=None):
    return app_runtime_mode.app_mode_telegram_enabled(mode or _load_app_runtime_mode())


def _schedule_app_service_restart():
    import shlex

    global app_service_restart_scheduled
    with app_service_restart_lock:
        if app_service_restart_scheduled:
            _write_runtime_log('App mode restart already scheduled; keeping latest saved mode for pending restart')
            return False
        app_service_restart_scheduled = True
    command = f'sleep 1.5; {BOT_SERVICE_SCRIPT} restart >/tmp/bypass-bot-service-restart.log 2>&1'
    try:
        subprocess.Popen(
            ['/bin/sh', '-c', command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        with app_service_restart_lock:
            app_service_restart_scheduled = False
        _write_runtime_log(f'Failed to schedule detached bot restart: {exc}')
        os.system(f'nohup /bin/sh -c {shlex.quote(command)} >/dev/null 2>&1 &')
    return True


def _set_app_runtime_mode(mode):
    def set_telegram_autostart(enabled):
        globals()['bot_ready'] = bool(enabled)
        _save_bot_autostart(enabled)

    return app_runtime_mode.set_app_runtime_mode(
        mode,
        load_mode=_load_app_runtime_mode,
        save_mode=_save_app_runtime_mode,
        schedule_restart=_schedule_app_service_restart,
        set_telegram_autostart=set_telegram_autostart,
        invalidate_status_cache=_invalidate_web_status_cache,
        invalidate_key_status_cache=_invalidate_key_status_cache,
    )


GITHUB_ROOT_ASSETS = {'version.md', 'README.md', 'CHANGELOG.md', 'script.sh'}
GITHUB_APP_DIR = 'app'


def _raw_github_url(path):
    normalized_path = str(path or '').lstrip('/')
    if normalized_path and normalized_path not in GITHUB_ROOT_ASSETS and not normalized_path.startswith((GITHUB_APP_DIR + '/', 'bootstrap/')):
        normalized_path = f'{GITHUB_APP_DIR}/{normalized_path}'
    return f'https://raw.githubusercontent.com/{fork_repo_owner}/{fork_repo_name}/{APP_BRANCH_LABEL}/{normalized_path}?ts={int(time.time())}'


SOCIALNET_SOURCE_URL = 'https://raw.githubusercontent.com/tas-unn/bypass_keenetic/main/socialnet.txt'
SOCIALNET_LOCAL_PATHS = [
    os.path.join(BOT_DIR, 'socialnet.txt'),
    '/opt/etc/bot/socialnet.txt',
    '/opt/etc/unblock/socialnet.txt',
]



SOCIALNET_SERVICE_KEYS = (
    'chatgpt_services',
    'claude',
    'gemini',
    'copilot',
    'perplexity',
    'grok',
    'deepseek',
    'youtube',
    'telegram',
    'discord',
    'chrome_remote_desktop',
    'meta',
    'tiktok',
)
SOCIALNET_ALL_KEY = 'all'
SOCIALNET_EXCLUDED_ENTRIES = set()


def _service_list_alias_map():
    aliases = {}
    for key, source in _service_catalog().SERVICE_LIST_SOURCES.items():
        if key not in SOCIALNET_SERVICE_KEYS:
            continue
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


def _record_event(action, message='', level='info', source='system', protocol='system', service='', key_hash='', details=None):
    return event_history.record_event(
        action=action,
        message=message,
        level=level,
        source=source,
        protocol=protocol,
        service=service,
        key_hash=key_hash,
        details=details,
    )


def _recent_event_history_match(action, *, protocol='', service='', max_age_seconds=0, limit=40):
    try:
        now = time.time()
        max_age = float(max_age_seconds or 0)
    except Exception:
        return False
    if max_age <= 0:
        return False
    action = str(action or '')
    protocol = str(protocol or '').strip().lower()
    service = str(service or '').strip().lower()
    try:
        events = event_history.load_events(limit=limit)
    except Exception:
        return False
    for event in events:
        if str((event or {}).get('action') or '') != action:
            continue
        if protocol and str((event or {}).get('protocol') or '').strip().lower() != protocol:
            continue
        if service and str((event or {}).get('service') or '').strip().lower() != service:
            continue
        try:
            ts = float((event or {}).get('ts') or 0)
        except Exception:
            ts = 0.0
        if ts > 0 and now - ts < max_age:
            return True
    return False


def _audit_key_switch(source, proto, key_value, reason=''):
    key_value = (key_value or '').strip()
    key_id = _hash_key(key_value)[:12] if key_value else ''
    try:
        display_name = _pool_key_display_name(key_value) if key_value else ''
    except Exception:
        display_name = ''
    display_name = re.sub(r'[\r\n\t]+', ' ', display_name).strip()[:120]
    reason = re.sub(r'[\r\n\t]+', ' ', str(reason or '')).strip()[:220]
    line = (
        f'{time.strftime("%Y-%m-%d %H:%M:%S %z")}\t'
        f'source={source}\tproto={proto}\tkey_id={key_id}\tname={display_name}\treason={reason}\n'
    )
    try:
        os.makedirs(os.path.dirname(KEY_SWITCH_AUDIT_LOG), exist_ok=True)
        with open(KEY_SWITCH_AUDIT_LOG, 'a', encoding='utf-8', errors='ignore') as file:
            file.write(line)
    except Exception:
        pass
    _record_event(
        action='key_switch',
        source=source,
        protocol=proto,
        key_hash=key_id,
        message=f'{display_name} {reason}'.strip(),
    )


def _redact_sensitive_text(text):
    safe_text = '' if text is None else str(text)
    token_value = str(token or '')
    if token_value:
        safe_text = safe_text.replace(token_value, '<redacted-token>')
    return re.sub(r'bot[0-9]+:[A-Za-z0-9_-]+', 'bot<redacted-token>', event_history.redact_sensitive_text(safe_text))


def _log_telegram_api_status_failure(key_name, api_message):
    message = str(api_message or '').strip()
    if not message:
        return
    log_key = f'Telegram API status failure {key_name}'
    now = time.time()
    last_log = float(background_task_skip_log_at.get(log_key) or 0.0)
    if now - last_log < BACKGROUND_TASK_SKIP_LOG_INTERVAL_SECONDS:
        return
    background_task_skip_log_at[log_key] = now
    _write_runtime_log(
        f'Telegram API status check through {key_name} failed: {_redact_sensitive_text(message)}'
    )


def _telegram_send_error_is_transient(error):
    error_text = _redact_sensitive_text(error).lower()
    transient_markers = (
        'ssleoferror',
        'unexpected_eof',
        'max retries exceeded',
        'connection aborted',
        'remote disconnected',
        'connection reset',
        'read timed out',
        'connect timeout',
    )
    return any(marker in error_text for marker in transient_markers)


def _install_telegram_send_retry_wrapper():
    original_send_message = getattr(bot, 'send_message', None)
    if not callable(original_send_message) or getattr(original_send_message, '_bypass_retry_wrapper', False):
        return

    def send_message_with_retry(*args, **kwargs):
        try:
            return original_send_message(*args, **kwargs)
        except Exception as exc:
            if not _telegram_send_error_is_transient(exc):
                raise RuntimeError(_redact_sensitive_text(exc)) from exc
            _write_runtime_log(
                'Telegram send_message failed, resetting HTTP session and retrying: '
                + _redact_sensitive_text(exc)
            )
            _reset_telegram_http_session('send_message retry')
            try:
                return original_send_message(*args, **kwargs)
            except Exception as retry_exc:
                raise RuntimeError(_redact_sensitive_text(retry_exc)) from retry_exc

    send_message_with_retry._bypass_retry_wrapper = True
    bot.send_message = send_message_with_retry


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


def _write_json_file_private(path, payload):
    _write_json_file(path, payload)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _load_subscription_state():
    if not SUBSCRIPTION_STATE_PATH:
        return _subscription_runtime().normalize_subscription_state({})
    with subscription_state_lock:
        return _subscription_runtime().normalize_subscription_state(_read_json_file(SUBSCRIPTION_STATE_PATH, {}) or {})


def _subscription_public_settings():
    return _subscription_runtime().subscription_public_settings(_load_subscription_state())


def _subscription_record(proto):
    return _load_subscription_state().get(proto, {})


def _update_subscription_record(proto, **updates):
    if not SUBSCRIPTION_STATE_PATH:
        return dict(updates)
    with subscription_state_lock:
        state = _subscription_runtime().normalize_subscription_state(_read_json_file(SUBSCRIPTION_STATE_PATH, {}) or {})
        record = dict(state.get(proto, {}) or {})
        record.update(updates)
        state[proto] = record
        _write_json_file(SUBSCRIPTION_STATE_PATH, _subscription_runtime().serialize_subscription_state(state))
        return record


def _write_text_file_atomic(path, text, mode=0o644):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    current = ''
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as file:
            current = file.read()
    except Exception:
        pass
    if current == text:
        return False
    fd, temp_path = tempfile.mkstemp(prefix='.' + os.path.basename(path) + '.', suffix='.tmp', dir=directory or None)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
        try:
            os.chmod(path, mode)
        except Exception:
            pass
        return True
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def _normalize_route_match_token(entry):
    value = str(entry or '').split('#', 1)[0].strip().lower()
    if not value:
        return ''
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', value):
        try:
            value = urlparse(value).hostname or ''
        except Exception:
            value = ''
    value = re.sub(r'^(full:|domain:)', '', value)
    value = re.sub(r'^\+\.', '', value)
    return value.lstrip('*.').strip('.')


def _route_entry_matches_catalog_entry(entry, catalog_entry):
    entry_domain = _normalize_route_domain_entry(entry)
    catalog_domain = _normalize_route_domain_entry(catalog_entry)
    if entry_domain and catalog_domain:
        return _route_domain_matches(entry_domain, catalog_domain) or _route_domain_matches(catalog_domain, entry_domain)
    entry_token = _normalize_route_match_token(entry)
    catalog_token = _normalize_route_match_token(catalog_entry)
    return bool(entry_token and catalog_token and entry_token == catalog_token)


def _route_list_contains_catalog(proto, catalog_entries):
    try:
        route_name = _unblock_route_for_key_type(proto)
        entries = _read_unblock_list_entries(route_name)
    except Exception:
        entries = []
    return any(
        _route_entry_matches_catalog_entry(entry, catalog_entry)
        for entry in entries
        for catalog_entry in catalog_entries
    )


def _route_list_contains_youtube(proto):
    return _route_list_contains_catalog(proto, _service_catalog().YOUTUBE_UNBLOCK_ENTRIES)


def _route_list_contains_telegram(proto):
    return _route_list_contains_catalog(proto, _service_catalog().TELEGRAM_CALL_SIGNAL_ROUTE_ENTRIES)


def _route_list_contains_realtime_call(proto):
    return _route_list_contains_catalog(proto, _service_catalog().REALTIME_CALL_SIGNAL_ROUTE_ENTRIES)


def _telegram_call_learning_route_signature():
    signature = []
    for proto in TELEGRAM_CALL_LEARNING_PROTOCOL_ORDER:
        try:
            route_name = _unblock_route_for_key_type(proto)
            path = _unblock_list_path(route_name)
            stat = os.stat(path)
            signature.append((proto, int(stat.st_mtime_ns), int(stat.st_size)))
        except Exception:
            signature.append((proto, 0, 0))
    return tuple(signature)


def _telegram_call_learning_route_protocols():
    signature = _telegram_call_learning_route_signature()
    if telegram_call_learning_route_cache.get('signature') == signature:
        return list(telegram_call_learning_route_cache.get('protocols') or [])
    protocols = []
    for proto in TELEGRAM_CALL_LEARNING_PROTOCOL_ORDER:
        try:
            if _route_list_contains_realtime_call(proto):
                protocols.append(proto)
        except Exception:
            continue
    telegram_call_learning_route_cache.update({
        'signature': signature,
        'protocols': list(protocols),
    })
    return protocols


def _select_telegram_call_learning_protocol(requested=''):
    requested = str(requested or '').strip().lower()
    if requested in _TELEGRAM_CALL_LEARNING_PROTOCOL_IPSETS:
        return requested, []
    route_protocols = _telegram_call_learning_route_protocols()
    active = ''
    try:
        active = _load_proxy_mode()
    except Exception:
        active = str(proxy_mode or '')
    notes = []
    if active in route_protocols:
        return active, route_protocols
    if route_protocols:
        return route_protocols[0], route_protocols
    if active in _TELEGRAM_CALL_LEARNING_PROTOCOL_IPSETS:
        notes.append('telegram_route_not_found')
        return active, route_protocols
    notes.append('telegram_route_not_found')
    return 'vless', route_protocols


def _telegram_call_learning_target_protocols(requested=''):
    requested = str(requested or '').strip().lower()
    if requested in _TELEGRAM_CALL_LEARNING_PROTOCOL_IPSETS:
        return [requested], _telegram_call_learning_route_protocols()
    route_protocols = _telegram_call_learning_route_protocols()
    if route_protocols:
        return route_protocols, route_protocols
    try:
        active = _load_proxy_mode()
    except Exception:
        active = str(proxy_mode or '')
    if active in _TELEGRAM_CALL_LEARNING_PROTOCOL_IPSETS:
        return [active], route_protocols
    return ['vless'], route_protocols


def _telegram_call_learning_snapshot():
    with telegram_call_learning_lock:
        snapshot = dict(telegram_call_learning_state)
        snapshot['candidates'] = list(snapshot.get('candidates') or [])
        snapshot['added'] = list(snapshot.get('added') or [])
        snapshot['protocols'] = list(snapshot.get('protocols') or [])
        snapshot['route_protocols'] = list(snapshot.get('route_protocols') or [])
        snapshot['seen_clients'] = list(snapshot.get('seen_clients') or [])
    snapshot['enabled'] = TELEGRAM_CALL_LEARNING_ENABLED
    snapshot['auto_enabled'] = TELEGRAM_CALL_LEARNING_AUTO_ENABLED
    return snapshot


def _write_telegram_call_learning_state(snapshot=None):
    global telegram_call_learning_state_last_digest, telegram_call_learning_state_last_write
    if not TELEGRAM_CALL_LEARNING_STATE_PATH:
        return
    payload = snapshot or _telegram_call_learning_snapshot()
    try:
        digest_payload = dict(payload)
        digest_payload.pop('updated_at', None)
        digest_payload.pop('last_scan_at', None)
        digest = json.dumps(digest_payload, sort_keys=True, ensure_ascii=False)
    except Exception:
        digest = ''
    now = time.time()
    if (
        digest
        and digest == telegram_call_learning_state_last_digest
        and now - telegram_call_learning_state_last_write < 15
    ):
        return
    try:
        _write_json_file(TELEGRAM_CALL_LEARNING_STATE_PATH, payload)
        telegram_call_learning_state_last_digest = digest
        telegram_call_learning_state_last_write = now
    except Exception as exc:
        _write_runtime_log(f'Ошибка записи telegram_call_learning_state: {exc}')


def _set_telegram_call_learning_state(**updates):
    with telegram_call_learning_lock:
        telegram_call_learning_state.update(updates)
        telegram_call_learning_state['enabled'] = TELEGRAM_CALL_LEARNING_ENABLED
        telegram_call_learning_state['auto_enabled'] = TELEGRAM_CALL_LEARNING_AUTO_ENABLED
        telegram_call_learning_state['updated_at'] = time.time()
        snapshot = dict(telegram_call_learning_state)
        snapshot['candidates'] = list(snapshot.get('candidates') or [])
        snapshot['added'] = list(snapshot.get('added') or [])
        snapshot['protocols'] = list(snapshot.get('protocols') or [])
        snapshot['route_protocols'] = list(snapshot.get('route_protocols') or [])
        snapshot['seen_clients'] = list(snapshot.get('seen_clients') or [])
    _write_telegram_call_learning_state(snapshot)
    return snapshot


def _telegram_call_learning_candidate_payload(candidate, apply_results=None, conntrack_deleted=False):
    if isinstance(apply_results, dict):
        apply_results = [apply_results]
    apply_results = list(apply_results or [])
    applied_sets = []
    errors = []
    protocols = []
    sets = []
    for apply_result in apply_results:
        protocol = str(apply_result.get('protocol') or '')
        if protocol:
            protocols.append(protocol)
        sets.extend(str(item) for item in (apply_result.get('sets') or []))
        applied_sets.extend(str(item) for item in (apply_result.get('applied_sets') or []))
        errors.extend(str(item) for item in (apply_result.get('errors') or []))
    return {
        'address': str(candidate.get('address') or candidate.get('dst') or ''),
        'src': str(candidate.get('src') or ''),
        'dport': str(candidate.get('dport') or ''),
        'score': int(candidate.get('score') or 0),
        'packets': int(candidate.get('packets') or 0),
        'bytes': int(candidate.get('bytes') or 0),
        'packet_delta': int(candidate.get('packet_delta') or 0),
        'byte_delta': int(candidate.get('byte_delta') or 0),
        'reasons': list(candidate.get('reasons') or []),
        'udp_call_cluster': bool(candidate.get('udp_call_cluster')),
        'udp_call_active_media': bool(candidate.get('udp_call_active_media')),
        'protocols': protocols,
        'sets': sets,
        'applied_sets': applied_sets,
        'errors': errors,
        'protocol_results': apply_results,
        'conntrack_deleted': bool(conntrack_deleted),
    }


def _telegram_call_learning_status_message(snapshot):
    if not TELEGRAM_CALL_LEARNING_ENABLED:
        return 'Conntrack-learning отключён в bot_config.py.'
    if snapshot.get('error'):
        return f"Conntrack-learning завершён с ошибкой: {snapshot.get('error')}"
    if TELEGRAM_CALL_LEARNING_AUTO_ENABLED and snapshot.get('watching'):
        added_count = len(snapshot.get('added') or [])
        clients = len(snapshot.get('seen_clients') or [])
        return f'Conntrack-learning авто: найдено IP: {added_count}, клиентов: {clients}.'
    if snapshot.get('running'):
        added_count = len(snapshot.get('added') or [])
        mode = 'добавление' if snapshot.get('apply') else 'наблюдение'
        return f'Conntrack-learning выполняется: {mode}, найдено IP: {added_count}.'
    added_count = len(snapshot.get('added') or [])
    if snapshot.get('finished_at'):
        return f'Conntrack-learning завершён. Найдено IP: {added_count}.'
    return 'Conntrack-learning готов.'


def _trim_telegram_call_learning_seen(seen_addresses):
    seen_list = list(seen_addresses or [])
    if len(seen_list) <= TELEGRAM_CALL_LEARNING_MAX_SEEN_ADDRESSES:
        return set(seen_list)
    return set(seen_list[-TELEGRAM_CALL_LEARNING_MAX_SEEN_ADDRESSES:])


def _apply_telegram_call_learning_candidate(candidate, protocols, apply_entries=True):
    apply_results = []
    conntrack_deleted = False
    for protocol in protocols or []:
        apply_result = _telegram_call_learning().add_candidate_to_ipsets(
            candidate,
            protocol,
            apply=apply_entries,
        )
        apply_results.append(apply_result)
    if apply_entries and any(result.get('applied_sets') for result in apply_results):
        conntrack_deleted = _telegram_call_learning().delete_conntrack_candidate(candidate)
    return _telegram_call_learning_candidate_payload(candidate, apply_results, conntrack_deleted)


def _telegram_call_learning_ipset_members(set_name, include_timeouts=False):
    try:
        result = subprocess.run(
            ['ipset', 'list', str(set_name or '')],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return {} if include_timeouts else []
    if result.returncode != 0:
        return {} if include_timeouts else []
    members = {} if include_timeouts else []
    in_members = False
    default_timeout = 0
    for line in (result.stdout or '').splitlines():
        text = line.strip()
        if text.startswith('Header:'):
            parts = text.split()
            if 'timeout' in parts:
                try:
                    default_timeout = int(parts[parts.index('timeout') + 1])
                except Exception:
                    default_timeout = 0
            continue
        if text == 'Members:':
            in_members = True
            continue
        if not in_members or not text:
            continue
        address = text.split()[0].strip()
        if _telegram_call_learning().is_lan_ipv4(address):
            if include_timeouts:
                parts = text.split()
                timeout_value = default_timeout
                if 'timeout' in parts:
                    try:
                        timeout_value = int(parts[parts.index('timeout') + 1])
                    except Exception:
                        timeout_value = default_timeout
                members[address] = timeout_value
            else:
                members.append(address)
    if include_timeouts:
        return dict(sorted(members.items()))
    return sorted(set(members))


def _apply_telegram_call_learning_call_candidate(candidate, protocols, apply_entries=True):
    apply_results = []
    for protocol in protocols or []:
        apply_result = _telegram_call_learning().add_candidate_to_call_ipset(
            candidate,
            protocol,
            timeout=TELEGRAM_CALL_LEARNING_ADDRESS_TIMEOUT_SECONDS,
            apply=apply_entries,
        )
        apply_results.append(apply_result)
    conntrack_deleted = False
    if apply_entries and any(result.get('applied_sets') for result in apply_results):
        conntrack_deleted = _telegram_call_learning().delete_conntrack_candidate(candidate)
    return _telegram_call_learning_candidate_payload(candidate, apply_results, conntrack_deleted=conntrack_deleted)


def _telegram_call_learning_auto_scan(
    previous_flows,
    seen_addresses,
    candidates_payload,
    added_payload,
    active_clients=None,
    target_protocols=None,
    route_protocols=None,
):
    if target_protocols is None:
        protocols, resolved_route_protocols = _telegram_call_learning_target_protocols()
        route_protocols = resolved_route_protocols if route_protocols is None else route_protocols
    else:
        protocols = [
            str(proto or '').strip().lower()
            for proto in (target_protocols or [])
            if _telegram_call_learning().protocol_call_ipset(proto)
        ]
        route_protocols = list(route_protocols or _telegram_call_learning_route_protocols())
    active_clients = sorted(set(str(item or '').strip() for item in (active_clients or []) if str(item or '').strip()))
    current_flows = _telegram_call_learning().read_lan_conntrack_flows(
        router_ip=routerip,
        allowed_sources=active_clients,
    )
    candidates = _telegram_call_learning().learn_candidates(
        previous_flows,
        current_flows,
        seen_addresses=seen_addresses,
        min_score=TELEGRAM_CALL_LEARNING_MIN_SCORE,
        min_packets=TELEGRAM_CALL_LEARNING_MIN_PACKETS,
        min_bytes=TELEGRAM_CALL_LEARNING_MIN_BYTES,
        max_candidates=TELEGRAM_CALL_LEARNING_MAX_CANDIDATES,
    )
    changed = False
    applied_now = []
    for candidate in candidates:
        address = str(candidate.get('address') or '')
        if not address:
            continue
        if _telegram_call_learning().address_in_networks(address):
            continue
        if not candidate.get('udp_call_cluster'):
            continue
        seen_addresses.add(address)
        payload = _apply_telegram_call_learning_call_candidate(
            candidate,
            protocols,
            apply_entries=TELEGRAM_CALL_LEARNING_APPLY_BY_DEFAULT,
        )
        candidates_payload.append(payload)
        if payload.get('applied_sets') or (not TELEGRAM_CALL_LEARNING_APPLY_BY_DEFAULT and not payload.get('errors')):
            added_payload.append(payload)
            applied_now.append(payload)
            changed = True
    seen_addresses = _trim_telegram_call_learning_seen(seen_addresses)
    seen_clients = sorted({str(flow.get('src') or '') for flow in current_flows.values() if flow.get('src')})
    snapshot = _set_telegram_call_learning_state(
        watching=True,
        running=False,
        protocol=protocols[0] if protocols else '',
        protocols=protocols,
        route_protocols=route_protocols,
        apply=TELEGRAM_CALL_LEARNING_APPLY_BY_DEFAULT,
        last_scan_at=time.time(),
        last_apply_at=time.time() if applied_now else telegram_call_learning_state.get('last_apply_at', 0.0),
        seen_clients=active_clients or seen_clients,
        candidates=candidates_payload[-TELEGRAM_CALL_LEARNING_MAX_CANDIDATES:],
        added=added_payload[-TELEGRAM_CALL_LEARNING_MAX_CANDIDATES:],
        message='',
        error='',
    )
    if applied_now:
        applied_count = len(applied_now)
        _record_event(
            'telegram_call_learning_apply',
            f'Conntrack-learning добавил адреса для Telegram-звонка: {applied_count}.',
            source='watchdog',
            protocol=','.join(protocols) if protocols else 'system',
            service='telegram',
            details={
                'count': applied_count,
                'protocols': protocols,
                'route_protocols': route_protocols,
                'clients_count': len(active_clients or seen_clients),
            },
        )
        try:
            _invalidate_web_status_cache()
        except Exception:
            pass
    _set_telegram_call_learning_state(message=_telegram_call_learning_status_message(snapshot))
    return current_flows, seen_addresses, candidates_payload, added_payload, changed


def _telegram_call_learning_auto_worker():
    previous_flows_by_protocol = {}
    seen_addresses_by_protocol = {}
    candidates_payload = []
    added_payload = []
    was_watching = False
    idle_no_client_scans = 0
    previous_udp_activity_by_protocol = {}
    follow_up_scan_pending = False
    while not shutdown_requested.is_set():
        try:
            route_protocols = _telegram_call_learning_route_protocols()
            active_clients_by_protocol = {}
            poll_protocols = [
                proto for proto in (route_protocols or TELEGRAM_CALL_LEARNING_PROTOCOL_ORDER)
                if proto in TELEGRAM_CALL_LEARNING_CLIENT_IPSETS
            ]
            for proto in poll_protocols:
                set_name = TELEGRAM_CALL_LEARNING_CLIENT_IPSETS.get(proto, '')
                if not set_name:
                    continue
                clients = _telegram_call_learning_ipset_members(set_name)
                if clients:
                    active_clients_by_protocol[proto] = clients
            if active_clients_by_protocol:
                legacy_clients = []
            else:
                legacy_clients = _telegram_call_learning_ipset_members(TELEGRAM_CALL_LEARNING_CLIENT_IPSET)
            if legacy_clients:
                fallback_protocols, _fallback_routes = _telegram_call_learning_target_protocols()
                for proto in fallback_protocols:
                    active_clients_by_protocol.setdefault(proto, legacy_clients)
            if not active_clients_by_protocol:
                idle_no_client_scans += 1
                if was_watching and idle_no_client_scans >= TELEGRAM_CALL_LEARNING_FAST_SCAN_LIMIT:
                    previous_flows_by_protocol = {}
                    seen_addresses_by_protocol = {}
                    candidates_payload = []
                    added_payload = []
                    snapshot = _set_telegram_call_learning_state(
                        watching=False,
                        running=False,
                        seen_clients=[],
                        candidates=[],
                        added=[],
                        message=_telegram_call_learning_status_message({'watching': False, 'added': []}),
                        error='',
                    )
                    _set_telegram_call_learning_state(message=_telegram_call_learning_status_message(snapshot))
                    was_watching = False
                    previous_udp_activity_by_protocol = {}
                    follow_up_scan_pending = False
                wait_seconds = TELEGRAM_CALL_LEARNING_SCAN_INTERVAL_SECONDS
                if idle_no_client_scans >= TELEGRAM_CALL_LEARNING_FAST_SCAN_LIMIT:
                    wait_seconds = max(wait_seconds, TELEGRAM_CALL_LEARNING_IDLE_BACKOFF_SECONDS)
                shutdown_requested.wait(wait_seconds)
                continue
            needs_initial_scan = not was_watching
            was_watching = True
            idle_no_client_scans = 0
            current_udp_activity_by_protocol = {
                proto: _telegram_call_learning().udp_source_activity_signature(active_clients)
                for proto, active_clients in active_clients_by_protocol.items()
            }
            udp_activity_changed = current_udp_activity_by_protocol != previous_udp_activity_by_protocol
            previous_udp_activity_by_protocol = current_udp_activity_by_protocol
            scan_is_follow_up = follow_up_scan_pending
            if not needs_initial_scan and not udp_activity_changed and not scan_is_follow_up:
                shutdown_requested.wait(TELEGRAM_CALL_LEARNING_SCAN_INTERVAL_SECONDS)
                continue
            follow_up_scan_pending = False
            changed_any = False
            saw_relevant_flows = False
            combined_clients = []
            for proto, active_clients in active_clients_by_protocol.items():
                combined_clients.extend(active_clients)
                previous_flows, seen_addresses, candidates_payload, added_payload, changed = _telegram_call_learning_auto_scan(
                    previous_flows_by_protocol.get(proto, {}),
                    seen_addresses_by_protocol.get(proto, set()),
                    candidates_payload,
                    added_payload,
                    active_clients=active_clients,
                    target_protocols=[proto],
                    route_protocols=route_protocols,
                )
                previous_flows_by_protocol[proto] = previous_flows
                seen_addresses_by_protocol[proto] = seen_addresses
                changed_any = changed_any or changed
                saw_relevant_flows = saw_relevant_flows or bool(previous_flows)
            _set_telegram_call_learning_state(seen_clients=sorted(set(combined_clients)))
            # A complete conntrack pass is expensive on the router. A first
            # relevant signal gets one confirmation pass; without flows we
            # keep only the lightweight signature poll until a new signal.
            if not scan_is_follow_up and saw_relevant_flows:
                follow_up_scan_pending = True
        except Exception as exc:
            _write_runtime_log(f'Telegram call adaptive learning error: {exc}')
            _set_telegram_call_learning_state(
                watching=False,
                running=False,
                error=str(exc),
                message=_telegram_call_learning_status_message({'error': str(exc)}),
            )
            shutdown_requested.wait(max(5.0, TELEGRAM_CALL_LEARNING_SCAN_INTERVAL_SECONDS))
            continue
        wait_seconds = TELEGRAM_CALL_LEARNING_SCAN_INTERVAL_SECONDS
        if added_payload:
            wait_seconds = max(wait_seconds, 30.0)
        shutdown_requested.wait(wait_seconds)


def _start_telegram_call_learning_auto_thread():
    global telegram_call_learning_auto_thread
    message = 'Автообучение Telegram-звонков выполняется правилами iptables/ipset без фонового сканирования.'
    _set_telegram_call_learning_state(
        watching=False,
        running=False,
        message=(
            message
            if TELEGRAM_CALL_LEARNING_ENABLED
            else _telegram_call_learning_status_message({'watching': False})
        ),
    )
    if not TELEGRAM_CALL_LEARNING_ENABLED or not TELEGRAM_CALL_LEARNING_AUTO_ENABLED:
        return
    if telegram_call_learning_auto_thread and telegram_call_learning_auto_thread.is_alive():
        return
    telegram_call_learning_auto_thread = threading.Thread(
        target=_telegram_call_learning_auto_worker,
        name='telegram-call-learning-auto',
        daemon=True,
    )
    telegram_call_learning_auto_thread.start()


def _telegram_call_learning_worker(device_ip, protocol, apply_entries, duration_seconds):
    baseline = _telegram_call_learning().read_conntrack_flows(device_ip)
    seen_addresses = set()
    candidates_payload = []
    added_payload = []
    deadline = time.time() + duration_seconds
    error = ''
    try:
        while not telegram_call_learning_cancel_event.is_set():
            current = _telegram_call_learning().read_conntrack_flows(device_ip)
            candidates = _telegram_call_learning().learn_candidates(
                baseline,
                current,
                seen_addresses=seen_addresses,
                min_score=TELEGRAM_CALL_LEARNING_MIN_SCORE,
                min_packets=TELEGRAM_CALL_LEARNING_MIN_PACKETS,
                min_bytes=TELEGRAM_CALL_LEARNING_MIN_BYTES,
                max_candidates=TELEGRAM_CALL_LEARNING_MAX_CANDIDATES,
            )
            for candidate in candidates:
                address = str(candidate.get('address') or '')
                if not address:
                    continue
                seen_addresses.add(address)
                apply_result = _telegram_call_learning().add_candidate_to_ipsets(
                    candidate,
                    protocol,
                    apply=apply_entries,
                )
                conntrack_deleted = False
                if apply_entries and apply_result.get('applied_sets'):
                    conntrack_deleted = _telegram_call_learning().delete_conntrack_candidate(candidate)
                payload = _telegram_call_learning_candidate_payload(candidate, apply_result, conntrack_deleted)
                candidates_payload.append(payload)
                if payload.get('applied_sets') or not payload.get('errors'):
                    added_payload.append(payload)
            _set_telegram_call_learning_state(
                candidates=candidates_payload[-TELEGRAM_CALL_LEARNING_MAX_CANDIDATES:],
                added=added_payload[-TELEGRAM_CALL_LEARNING_MAX_CANDIDATES:],
                message=_telegram_call_learning_status_message({
                    'running': True,
                    'apply': apply_entries,
                    'added': added_payload,
                }),
            )
            if time.time() >= deadline:
                break
            telegram_call_learning_cancel_event.wait(TELEGRAM_CALL_LEARNING_POLL_INTERVAL_SECONDS)
    except Exception as exc:
        error = str(exc)
        _write_runtime_log(f'Ошибка conntrack-learning Telegram calls: {exc}')
    finally:
        cancelled = telegram_call_learning_cancel_event.is_set()
        snapshot = _set_telegram_call_learning_state(
            running=False,
            finished_at=time.time(),
            candidates=candidates_payload[-TELEGRAM_CALL_LEARNING_MAX_CANDIDATES:],
            added=added_payload[-TELEGRAM_CALL_LEARNING_MAX_CANDIDATES:],
            error=error,
            message=('Conntrack-learning остановлен.' if cancelled else ''),
        )
        _set_telegram_call_learning_state(message=_telegram_call_learning_status_message(snapshot))
        _record_event(
            'telegram_call_learning_finish',
            _telegram_call_learning_status_message(snapshot),
            source='web',
            protocol=protocol,
            service='telegram',
            details={
                'apply': bool(apply_entries),
                'added_count': len(added_payload),
                'error': error,
                'cancelled': cancelled,
            },
        )
        try:
            _invalidate_web_status_cache()
        except Exception:
            pass
        try:
            _memory_cleanup('telegram call learning finished', clear_status=True)
        except Exception:
            pass


def _start_telegram_call_learning(device_ip, protocol='', apply_entries=None, duration_seconds=None):
    if not TELEGRAM_CALL_LEARNING_ENABLED:
        snapshot = _telegram_call_learning_snapshot()
        return False, _telegram_call_learning_status_message(snapshot), snapshot
    device_ip = str(device_ip or '').strip()
    if not _telegram_call_learning().is_lan_ipv4(device_ip):
        snapshot = _telegram_call_learning_snapshot()
        return False, 'Укажите IPv4-адрес телефона или другого клиента в LAN.', snapshot
    selected_protocol, route_protocols = _select_telegram_call_learning_protocol(protocol)
    if not _telegram_call_learning().protocol_ipsets(selected_protocol):
        snapshot = _telegram_call_learning_snapshot()
        return False, 'Не удалось выбрать протокол для добавления IP в ipset.', snapshot
    if apply_entries is None:
        apply_entries = TELEGRAM_CALL_LEARNING_APPLY_BY_DEFAULT
    try:
        duration = int(float(duration_seconds or TELEGRAM_CALL_LEARNING_DEFAULT_DURATION_SECONDS))
    except Exception:
        duration = TELEGRAM_CALL_LEARNING_DEFAULT_DURATION_SECONDS
    duration = min(TELEGRAM_CALL_LEARNING_MAX_DURATION_SECONDS, max(20, duration))
    with telegram_call_learning_lock:
        if telegram_call_learning_state.get('running'):
            snapshot = dict(telegram_call_learning_state)
            snapshot['candidates'] = list(snapshot.get('candidates') or [])
            snapshot['added'] = list(snapshot.get('added') or [])
            return False, 'Conntrack-learning уже выполняется.', snapshot
        telegram_call_learning_cancel_event.clear()
        telegram_call_learning_state.update({
            'enabled': TELEGRAM_CALL_LEARNING_ENABLED,
            'running': True,
            'device_ip': device_ip,
            'protocol': selected_protocol,
            'route_protocols': route_protocols,
            'apply': bool(apply_entries),
            'duration_seconds': duration,
            'started_at': time.time(),
            'updated_at': time.time(),
            'finished_at': 0.0,
            'candidates': [],
            'added': [],
            'message': '',
            'error': '',
        })
        snapshot = dict(telegram_call_learning_state)
    _write_telegram_call_learning_state(snapshot)
    thread = threading.Thread(
        target=_telegram_call_learning_worker,
        args=(device_ip, selected_protocol, bool(apply_entries), duration),
        daemon=True,
    )
    thread.start()
    message = (
        f'Conntrack-learning запущен на {duration} сек. '
        f'Протокол: {selected_protocol}. Режим: {"добавление в ipset" if apply_entries else "наблюдение"}.'
    )
    _set_telegram_call_learning_state(message=message)
    _record_event(
        'telegram_call_learning_start',
        message,
        source='web',
        protocol=selected_protocol,
        service='telegram',
        details={'apply': bool(apply_entries), 'route_protocols': route_protocols, 'duration_seconds': duration},
    )
    try:
        _invalidate_web_status_cache()
    except Exception:
        pass
    return True, message, _telegram_call_learning_snapshot()


def _cancel_telegram_call_learning():
    snapshot = _telegram_call_learning_snapshot()
    if not snapshot.get('running'):
        return False, 'Conntrack-learning сейчас не выполняется.', snapshot
    telegram_call_learning_cancel_event.set()
    snapshot = _set_telegram_call_learning_state(message='Остановка conntrack-learning...')
    return True, 'Остановка conntrack-learning запрошена.', snapshot


def _udp_quic_block_enabled_for_protocol(proto, configured_enabled):
    if proto in UDP_QUIC_POLICY_PROTOCOLS and _route_list_contains_youtube(proto):
        if YOUTUBE_QUIC_POLICY == 'allow':
            return False
        if YOUTUBE_QUIC_POLICY == 'block':
            return True
        return True
    if proto in UDP_QUIC_POLICY_PROTOCOLS and _route_list_contains_telegram(proto):
        if TELEGRAM_UDP_POLICY == 'block':
            return True
        return False
    return bool(configured_enabled)


def _sync_udp_policy_config():
    block_shadowsocks = _udp_quic_block_enabled_for_protocol('shadowsocks', UDP_QUIC_BLOCK_SHADOWSOCKS_ENABLED)
    block_vmess = _udp_quic_block_enabled_for_protocol('vmess', UDP_QUIC_BLOCK_VMESS_ENABLED)
    block_vless = _udp_quic_block_enabled_for_protocol('vless', UDP_QUIC_BLOCK_VLESS_ENABLED)
    block_vless2 = _udp_quic_block_enabled_for_protocol('vless2', UDP_QUIC_BLOCK_VLESS2_ENABLED)
    block_trojan = _udp_quic_block_enabled_for_protocol('trojan', UDP_QUIC_BLOCK_TROJAN_ENABLED)
    telegram_routes = {
        'shadowsocks': _route_list_contains_telegram('shadowsocks'),
        'vmess': _route_list_contains_telegram('vmess'),
        'vless': _route_list_contains_telegram('vless'),
        'vless2': _route_list_contains_telegram('vless2'),
        'trojan': _route_list_contains_telegram('trojan'),
    }
    realtime_call_routes = {
        'shadowsocks': _route_list_contains_realtime_call('shadowsocks'),
        'vmess': _route_list_contains_realtime_call('vmess'),
        'vless': _route_list_contains_realtime_call('vless'),
        'vless2': _route_list_contains_realtime_call('vless2'),
        'trojan': _route_list_contains_realtime_call('trojan'),
    }
    call_signal_routes_payload = ''.join(
        f'{entry}\n' for entry in _service_catalog().REALTIME_CALL_SIGNAL_ROUTE_ENTRIES
    )
    payload = (
        '# Generated by bypass_keenetic. Edit bot_config.py values instead.\n'
        f'BYPASS_UDP_QUIC_BLOCK_SHADOWSOCKS={1 if block_shadowsocks else 0}\n'
        f'BYPASS_UDP_QUIC_BLOCK_VMESS={1 if block_vmess else 0}\n'
        f'BYPASS_UDP_QUIC_BLOCK_VLESS={1 if block_vless else 0}\n'
        f'BYPASS_UDP_QUIC_BLOCK_VLESS2={1 if block_vless2 else 0}\n'
        f'BYPASS_UDP_QUIC_BLOCK_TROJAN={1 if block_trojan else 0}\n'
        f'BYPASS_IPV6_FALLBACK_ENABLED={1 if IPV6_BYPASS_FALLBACK_ENABLED else 0}\n'
        f'BYPASS_TELEGRAM_CALL_LEARNING_ENABLED={1 if TELEGRAM_CALL_LEARNING_ENABLED else 0}\n'
        f'BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT={TELEGRAM_CALL_LEARNING_CLIENT_TIMEOUT_SECONDS}\n'
        f'BYPASS_TELEGRAM_CALL_ADDRESS_TIMEOUT={TELEGRAM_CALL_LEARNING_ADDRESS_TIMEOUT_SECONDS}\n'
        f'BYPASS_TELEGRAM_CALL_TPROXY_ENABLED={1 if TELEGRAM_CALL_TPROXY_ENABLED else 0}\n'
        'BYPASS_TELEGRAM_CALL_CLIENT_UDP_ROUTE_ENABLED=0\n'
        f'TELEGRAM_CALL_TPROXY_PORT_SHADOWSOCKS={localportsh_tproxy}\n'
        f'TELEGRAM_CALL_TPROXY_PORT_VMESS={localportvmess_tproxy}\n'
        f'TELEGRAM_CALL_TPROXY_PORT_VLESS={localportvless_tproxy}\n'
        f'TELEGRAM_CALL_TPROXY_PORT_VLESS2={localportvless2_tproxy}\n'
        f'TELEGRAM_CALL_TPROXY_PORT_TROJAN={localporttrojan_tproxy}\n'
        f'BYPASS_TELEGRAM_CALL_ROUTE_SHADOWSOCKS={1 if realtime_call_routes["shadowsocks"] else 0}\n'
        f'BYPASS_TELEGRAM_CALL_ROUTE_VMESS={1 if realtime_call_routes["vmess"] else 0}\n'
        f'BYPASS_TELEGRAM_CALL_ROUTE_VLESS={1 if realtime_call_routes["vless"] else 0}\n'
        f'BYPASS_TELEGRAM_CALL_ROUTE_VLESS2={1 if realtime_call_routes["vless2"] else 0}\n'
        f'BYPASS_TELEGRAM_CALL_ROUTE_TROJAN={1 if realtime_call_routes["trojan"] else 0}\n'
        f'BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_SHADOWSOCKS={1 if telegram_routes["shadowsocks"] else 0}\n'
        f'BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_VMESS={1 if telegram_routes["vmess"] else 0}\n'
        f'BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_VLESS={1 if telegram_routes["vless"] else 0}\n'
        f'BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_VLESS2={1 if telegram_routes["vless2"] else 0}\n'
        f'BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_TROJAN={1 if telegram_routes["trojan"] else 0}\n'
    )
    try:
        directory = os.path.dirname(UDP_POLICY_CONFIG_PATH)
        os.makedirs(directory, exist_ok=True)
        _write_text_file_atomic(UDP_POLICY_CONFIG_PATH, payload)
        _write_text_file_atomic(CALL_SIGNAL_ROUTES_PATH, call_signal_routes_payload)
    except Exception as exc:
        _write_runtime_log(f'UDP policy sync failed: {exc}')


def _normalize_route_domain_entry(entry):
    value = str(entry or '').split('#', 1)[0].strip().lower()
    if not value:
        return ''
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', value):
        try:
            value = urlparse(value).hostname or ''
        except Exception:
            value = ''
    value = re.sub(r'^(full:|domain:)', '', value)
    value = re.sub(r'^\+\.', '', value)
    value = value.lstrip('*.').strip('.')
    if not value or '/' in value or ':' in value:
        return ''
    if re.match(r'^[a-z0-9_.-]+\.[a-z0-9_.-]+$', value):
        return value
    return ''


def _route_domain_matches(domain, candidate):
    domain = _normalize_route_domain_entry(domain)
    candidate = _normalize_route_domain_entry(candidate)
    return bool(domain and candidate and (domain == candidate or domain.endswith('.' + candidate)))


def _udp_quic_policy_matches(domain):
    return any(_route_domain_matches(domain, policy) for policy in _service_catalog().UDP_QUIC_ROUTE_ENTRIES)


def _resolve_domain_ipv4_addresses(domain, external_dns=True):
    addresses = []
    seen = set()
    repair_dns_servers = {str(item).strip() for item in REALITY_ENDPOINT_REPAIR_DNS_SERVERS}

    def add_address(address):
        try:
            ip_obj = ipaddress.ip_address(str(address or '').strip())
        except Exception:
            return
        value = str(ip_obj)
        if value in repair_dns_servers:
            return
        if ip_obj.version == 4 and not ip_obj.is_private and not ip_obj.is_loopback and value not in seen:
            seen.add(value)
            addresses.append(value)

    try:
        infos = socket.getaddrinfo(domain, 443, socket.AF_INET, socket.SOCK_STREAM)
    except Exception:
        infos = []
    for item in infos:
        try:
            add_address(item[4][0])
        except Exception:
            continue
    if not external_dns:
        return addresses
    for dns_server in REALITY_ENDPOINT_REPAIR_DNS_SERVERS:
        outputs = []
        try:
            result = subprocess.run(
                ['dig', '+time=2', '+tries=1', '+short', 'A', str(domain), f'@{dns_server}'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=4,
                check=False,
            )
            if result.returncode == 0:
                outputs.append(result.stdout)
        except Exception:
            pass
        try:
            result = subprocess.run(
                ['nslookup', str(domain), str(dns_server)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=4,
                check=False,
            )
            if result.returncode == 0:
                outputs.append(result.stdout)
        except Exception:
            pass
        for output in outputs:
            for token in str(output or '').replace(',', ' ').split():
                add_address(token)
    return addresses


def _ipset_contains(set_name, address):
    try:
        result = subprocess.run(
            ['ipset', 'test', set_name, address],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def _ipset_ipv4_snapshot(set_name):
    try:
        result = subprocess.run(
            ['ipset', 'save', str(set_name or '')],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    networks = []
    for raw_line in (result.stdout or '').splitlines():
        parts = raw_line.split()
        if len(parts) < 3 or parts[0] != 'add' or parts[1] != set_name:
            continue
        try:
            network = ipaddress.ip_network(parts[2], strict=False)
        except ValueError:
            continue
        if network.version == 4:
            networks.append(network)
    return tuple(networks)


def _ipset_snapshot_contains(networks, address):
    if networks is None:
        return None
    try:
        address_obj = ipaddress.ip_address(str(address or '').strip())
    except ValueError:
        return False
    if address_obj.version != 4:
        return False
    return any(address_obj in network for network in networks)


def _ipset_add_address(set_name, address):
    try:
        result = subprocess.run(
            ['ipset', 'add', set_name, address, '-exist'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=2,
            check=False,
        )
        return result.returncode == 0, (result.stdout or '').strip()
    except Exception as exc:
        return False, str(exc)


def _ipset_delete_address(set_name, address):
    try:
        result = subprocess.run(
            ['ipset', 'del', set_name, address],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def _ipset_member_contains_address(member, address):
    try:
        address_obj = ipaddress.ip_address(str(address or '').strip())
        network = ipaddress.ip_network(str(member or '').strip(), strict=False)
    except Exception:
        return False
    return address_obj.version == network.version and address_obj in network


def _ipset_delete_overlaps(set_name, address):
    try:
        if not _youtube_edge_prefetch().is_public_ipv4(address):
            return 0
    except Exception:
        return 0
    try:
        result = subprocess.run(
            ['ipset', 'list', str(set_name)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return 0
    if result.returncode != 0:
        return 0
    deleted = 0
    in_members = False
    for raw_line in (result.stdout or '').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == 'Members:':
            in_members = True
            continue
        if not in_members:
            continue
        member = line.split()[0]
        if member == address or _ipset_member_contains_address(member, address):
            if _ipset_delete_address(set_name, member):
                deleted += 1
    return deleted


def _delete_conntrack_for_address(address):
    deleted = 0
    for proto in ('tcp', 'udp'):
        for direction in ('--orig-dst', '--reply-src'):
            try:
                result = subprocess.run(
                    ['conntrack', '-D', '-p', proto, direction, address],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
                if result.returncode == 0:
                    deleted += 1
            except Exception:
                continue
    return deleted


def _udp_quic_drift_domains_by_protocol(route_sets):
    route_sources = []
    route_names = {}
    for proto in route_sets:
        route_name = _unblock_route_for_key_type(proto)
        route_names[proto] = route_name
        try:
            stat = os.stat(_unblock_list_path(route_name))
            route_sources.append((proto, stat.st_mtime_ns, stat.st_size))
        except OSError:
            route_sources.append((proto, None, None))
    route_signature = tuple(route_sources)
    cached = udp_quic_drift_state.get('domains_by_protocol') or {}
    if udp_quic_drift_state.get('route_signature') == route_signature and cached:
        return cached

    domains_by_protocol = {}
    sentinels = tuple(
        domain
        for item in UDP_QUIC_DRIFT_SENTINEL_DOMAINS
        for domain in (_normalize_route_domain_entry(item),)
        if domain and _udp_quic_policy_matches(domain)
    )
    for proto, route_name in route_names.items():
        try:
            entries = tuple(
                entry
                for item in _read_unblock_list_entries(route_name)
                for entry in (_normalize_route_domain_entry(item),)
                if entry
            )
        except Exception:
            entries = ()
        domains_by_protocol[proto] = tuple(
            domain for domain in sentinels
            if any(_route_domain_matches(entry, domain) for entry in entries)
        )

    udp_quic_drift_state['route_signature'] = route_signature
    udp_quic_drift_state['domains_by_protocol'] = domains_by_protocol
    udp_quic_drift_state['dns_cache'] = {}
    return domains_by_protocol


def _udp_quic_drift_domain_addresses(domain):
    now = time.monotonic()
    cache = udp_quic_drift_state.setdefault('dns_cache', {})
    cached = cache.get(domain)
    if cached and now < cached['expires_at']:
        return cached['addresses']

    addresses = tuple(_resolve_domain_ipv4_addresses(domain, external_dns=False))
    cache[domain] = {
        'addresses': addresses,
        'expires_at': now + (
            UDP_QUIC_DRIFT_DNS_CACHE_TTL_SECONDS if addresses else min(60.0, UDP_QUIC_DRIFT_DNS_CACHE_TTL_SECONDS)
        ),
    }
    return addresses


def _udp_quic_drift_route_sets():
    return {
        proto: ipsets
        for proto in UDP_QUIC_POLICY_PROTOCOLS
        for ipsets in (_TELEGRAM_CALL_LEARNING_PROTOCOL_IPSETS.get(proto),)
        if isinstance(ipsets, tuple) and len(ipsets) == 2
    }


def _udp_quic_route_drift_findings():
    findings = []
    route_sets = _udp_quic_drift_route_sets()
    domains_by_protocol = _udp_quic_drift_domains_by_protocol(route_sets)
    route_sets = {
        proto: ipsets
        for proto, ipsets in route_sets.items()
        if domains_by_protocol.get(proto)
    }
    if not route_sets:
        return findings
    ipset_snapshots = {
        set_name: _ipset_ipv4_snapshot(set_name)
        for set_pair in route_sets.values()
        for set_name in set_pair
    }
    for proto, (main_set, udp_set) in route_sets.items():
        for domain in domains_by_protocol.get(proto, ()):
            for address in _udp_quic_drift_domain_addresses(domain):
                in_main = _ipset_snapshot_contains(ipset_snapshots.get(main_set), address)
                in_udp = _ipset_snapshot_contains(ipset_snapshots.get(udp_set), address)
                if in_main is None:
                    in_main = _ipset_contains(main_set, address)
                if in_udp is None:
                    in_udp = _ipset_contains(udp_set, address)
                if not in_main or not in_udp:
                    findings.append({
                        'proto': proto,
                        'domain': domain,
                        'address': address,
                        'main': in_main,
                        'udp': in_udp,
                    })
                    break
    return findings


def _apply_priority_udp_quic_drift_findings(findings):
    priority_findings = _udp_quic_drift_priority_findings(findings)
    if not priority_findings:
        return 0
    route_sets = {
        'vless': ('unblockvless', 'unblockvlessudp'),
        'vless2': ('unblockvless2', 'unblockvless2udp'),
    }
    added = []
    failed = []
    added_addresses = set()
    for item in priority_findings:
        if not isinstance(item, dict):
            continue
        proto = str(item.get('proto') or '').strip().lower()
        address = str(item.get('address') or '').strip()
        domain = str(item.get('domain') or '').strip()
        if proto not in route_sets or not address:
            continue
        main_set, udp_set = route_sets[proto]
        targets = []
        if not item.get('main'):
            targets.append(main_set)
        if not item.get('udp'):
            targets.append(udp_set)
        for set_name in targets:
            ok, output = _ipset_add_address(set_name, address)
            if ok:
                added.append((proto, domain, address, set_name))
                added_addresses.add(address)
            else:
                failed.append((proto, domain, address, set_name, output))
    conntrack_deleted = 0
    for address in sorted(added_addresses):
        conntrack_deleted += _delete_conntrack_for_address(address)
    if added:
        now = time.time()
        event_signature = tuple(sorted((proto, domain, set_name) for proto, domain, _address, set_name in added))
        suppress_repeated_event = (
            event_signature == tuple(udp_quic_drift_state.get('last_fast_add_signature') or ()) and
            now - float(udp_quic_drift_state.get('last_fast_add_event') or 0.0) < 1800
        )
        udp_quic_drift_state['last_fast_add_signature'] = event_signature
        udp_quic_drift_state['last_fast_add_event'] = now
        sample = ', '.join(f'{proto}:{domain}:{address}->{set_name}' for proto, domain, address, set_name in added[:4])
        message = (
            f'UDP/QUIC priority drift fast ipset add: {len(added)} entries, '
            f'conntrack cleared={conntrack_deleted}. {sample}'
        )
        if not suppress_repeated_event:
            _write_runtime_log(message)
            _record_event(
                'udp_quic_drift_fast_add',
                message,
                level='info',
                source='watchdog',
                protocol=added[0][0],
                service='youtube',
                details={'added': str(len(added)), 'conntrack_cleared': str(conntrack_deleted), 'sample': sample},
            )
    if failed:
        sample = ', '.join(f'{proto}:{domain}:{address}->{set_name}:{output}' for proto, domain, address, set_name, output in failed[:3])
        _write_runtime_log(f'UDP/QUIC priority drift fast ipset add failed: {sample}')
    return len(added)


def _udp_quic_drift_priority_findings(findings):
    priority_domains = [
        _normalize_route_domain_entry(domain)
        for domain in UDP_QUIC_DRIFT_PRIORITY_DOMAINS
    ]
    priority_domains = [domain for domain in priority_domains if domain]
    if not priority_domains:
        return []
    priority = []
    for item in findings or []:
        domain = _normalize_route_domain_entry(item.get('domain') if isinstance(item, dict) else '')
        if domain and any(_route_domain_matches(domain, priority_domain) for priority_domain in priority_domains):
            priority.append(item)
    return priority


def _udp_quic_drift_refresh_cooldown(findings):
    if _udp_quic_drift_priority_findings(findings):
        return UDP_QUIC_DRIFT_PRIORITY_REFRESH_COOLDOWN_SECONDS
    return UDP_QUIC_DRIFT_REFRESH_COOLDOWN_SECONDS


def _udp_quic_drift_refresh_guard_protocols(findings):
    protocols = []
    seen = set()
    for item in findings or []:
        if not isinstance(item, dict):
            continue
        proto = str(item.get('proto') or '').strip().lower()
        if proto in YOUTUBE_STREAM_GUARD_PROTOCOLS and proto not in seen:
            seen.add(proto)
            protocols.append(proto)
    return tuple(protocols) or tuple(YOUTUBE_STREAM_GUARD_PROTOCOLS)


def _udp_quic_drift_refresh_deferred_for_stream(findings):
    guarded_findings = _udp_quic_drift_priority_findings(findings) or findings
    for proto in _udp_quic_drift_refresh_guard_protocols(guarded_findings):
        if _youtube_stream_guard_active(
            proto,
            reason='UDP/QUIC drift refresh',
            log=True,
            hold_seconds=YOUTUBE_STREAM_GUARD_FAILOVER_HOLD_SECONDS,
        ):
            return True
    return False


def _refresh_ipset_for_udp_quic_drift(findings):
    now = time.time()
    priority_findings = _udp_quic_drift_priority_findings(findings)
    if priority_findings and _udp_quic_drift_refresh_deferred_for_stream(priority_findings):
        udp_quic_drift_state['last_log'] = now
        return
    if _apply_priority_udp_quic_drift_findings(priority_findings):
        udp_quic_drift_state['last_refresh'] = now
        udp_quic_drift_state['last_log'] = now
        return
    cooldown = _udp_quic_drift_refresh_cooldown(findings)
    if now - float(udp_quic_drift_state.get('last_refresh') or 0.0) < cooldown:
        if now - float(udp_quic_drift_state.get('last_log') or 0.0) >= 300:
            udp_quic_drift_state['last_log'] = now
            label = 'priority ' if priority_findings else ''
            _write_runtime_log(f'UDP/QUIC {label}drift detected, refresh skipped by cooldown.')
        return
    if _udp_quic_drift_refresh_deferred_for_stream(findings):
        udp_quic_drift_state['last_log'] = now
        return
    udp_quic_drift_state['last_refresh'] = now
    sample_findings = priority_findings or findings
    sample = ', '.join(
        f"{item['proto']}:{item['domain']}:{item['address']}:"
        f"{'tcp' if item['main'] else 'no-tcp'}/{'udp' if item['udp'] else 'no-udp'}"
        for item in sample_findings[:4]
    )
    label = 'priority ' if priority_findings else ''
    _write_runtime_log(f'UDP/QUIC {label}drift detected; refreshing ipset. {sample}')
    try:
        env = os.environ.copy()
        env['UNBLOCK_IPSET_LOCK_BUSY_QUIET'] = '1'
        result = subprocess.run(
            ['/opt/bin/unblock_ipset.sh'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            timeout=IPSET_REFRESH_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
        output = (result.stdout or '').strip()
        if result.returncode == 0:
            if 'already running' in output:
                _write_runtime_log('UDP/QUIC drift refresh skipped: unblock_ipset is already running.')
            else:
                suffix = f' {output}' if output else ''
                _write_runtime_log(f'UDP/QUIC drift refresh completed.{suffix}')
        else:
            _write_runtime_log(f'UDP/QUIC drift refresh failed with code {result.returncode}.')
    except Exception as exc:
        _write_runtime_log(f'UDP/QUIC drift refresh failed: {exc}')


def _run_udp_quic_drift_watchdog_cycle():
    if not UDP_QUIC_DRIFT_CHECK_ENABLED:
        return
    try:
        if _background_task_allowed('UDP/QUIC drift watchdog', task_class='critical'):
            def refresh_udp_quic_drift():
                findings = _udp_quic_route_drift_findings()
                if findings:
                    _refresh_ipset_for_udp_quic_drift(findings)
            _run_coordinated_background_task('UDP/QUIC drift watchdog', refresh_udp_quic_drift)
    except Exception as exc:
        _write_runtime_log(f'UDP/QUIC drift check failed: {exc}')


def _youtube_edge_prefetch_hosts_for_run():
    hosts = list(_youtube_edge_prefetch().normalize_hosts(YOUTUBE_EDGE_PREFETCH_HOSTS))
    if not hosts:
        return ()
    max_hosts = min(len(hosts), YOUTUBE_EDGE_PREFETCH_MAX_HOSTS_PER_RUN)
    start_index = int(youtube_edge_prefetch_state.get('next_host_index') or 0) % len(hosts)
    selected = tuple(hosts[(start_index + offset) % len(hosts)] for offset in range(max_hosts))
    youtube_edge_prefetch_state['next_host_index'] = (start_index + max_hosts) % len(hosts)
    return selected


def _youtube_edge_prefetch_snapshot():
    now = time.time()
    try:
        ttl = max(1.0, min(15.0, float(ROUTER_HEALTH_CACHE_TTL or 0)))
    except Exception:
        ttl = 10.0
    cached = youtube_edge_prefetch_snapshot_cache.get('payload')
    if isinstance(cached, dict) and now - float(youtube_edge_prefetch_snapshot_cache.get('timestamp') or 0.0) < ttl:
        return dict(cached)
    snapshot = dict(youtube_edge_prefetch_state)
    snapshot['enabled'] = bool(YOUTUBE_EDGE_PREFETCH_ENABLED)
    snapshot['mode'] = YOUTUBE_EDGE_PREFETCH_MODE
    if YOUTUBE_EDGE_PREFETCH_MODE == 'external':
        external_status = _load_youtube_edge_prefetch_external_status()
        if external_status:
            snapshot.update(external_status)
            snapshot['enabled'] = bool(YOUTUBE_EDGE_PREFETCH_ENABLED)
            snapshot['mode'] = YOUTUBE_EDGE_PREFETCH_MODE
    snapshot.pop('last_log_signature', None)
    snapshot.pop('next_host_index', None)
    if YOUTUBE_EDGE_PREFETCH_MODE == 'external':
        snapshot['running'] = bool(YOUTUBE_EDGE_PREFETCH_LOCK_DIR and os.path.isdir(YOUTUBE_EDGE_PREFETCH_LOCK_DIR))
        snapshot['last_message'] = str(snapshot.get('last_message') or _youtube_edge_prefetch_status_message(snapshot))
    else:
        snapshot['running'] = youtube_edge_prefetch_lock.locked()
    youtube_edge_prefetch_snapshot_cache['timestamp'] = now
    youtube_edge_prefetch_snapshot_cache['payload'] = dict(snapshot)
    return snapshot


def _load_youtube_edge_prefetch_external_status():
    if not YOUTUBE_EDGE_PREFETCH_STATUS_PATH:
        return {}
    try:
        if os.path.getsize(YOUTUBE_EDGE_PREFETCH_STATUS_PATH) > 65536:
            return {}
    except Exception:
        return {}
    status = _read_json_file(YOUTUBE_EDGE_PREFETCH_STATUS_PATH, default={})
    if not isinstance(status, dict):
        return {}
    return status


def _youtube_edge_prefetch_status_message(status):
    skipped = str((status or {}).get('skipped_reason') or '').strip()
    if skipped:
        return f'skipped: {skipped}'
    protocol = str((status or {}).get('route_protocol') or '').strip() or 'unknown'
    return (
        f'{protocol}: added {int((status or {}).get("added_addresses") or 0)} addresses, '
        f'candidates {int((status or {}).get("candidates") or 0)}, '
        f'cache {int((status or {}).get("cache_entries") or 0)}'
    )


def _store_youtube_edge_prefetch_status(status):
    now = time.time()
    status = dict(status or {})
    status['enabled'] = bool(YOUTUBE_EDGE_PREFETCH_ENABLED)
    status['last_message'] = _youtube_edge_prefetch_status_message(status)
    youtube_edge_prefetch_state.update(status)
    youtube_edge_prefetch_state['last_run_at'] = float(status.get('last_run_at') or now)
    if status.get('ok') and not status.get('skipped_reason'):
        youtube_edge_prefetch_state['last_success_at'] = now
    if int(status.get('added_addresses') or 0) > 0:
        youtube_edge_prefetch_state['last_added_at'] = now
    _clear_youtube_edge_prefetch_snapshot_cache()
    try:
        router_health.invalidate(include_heavy=False)
    except Exception:
        pass
    return youtube_edge_prefetch_state['last_message']


def _youtube_edge_prefetch_skip_reason():
    if not YOUTUBE_EDGE_PREFETCH_ENABLED:
        return 'disabled'
    if not _app_mode_pool_enabled():
        return 'simple_mode'
    try:
        if _memory_sensitive_operation_running():
            return 'busy'
    except Exception:
        pass
    rss_kb = int(_process_rss_kb() or 0)
    if YOUTUBE_EDGE_PREFETCH_MAX_RSS_KB > 0 and rss_kb >= YOUTUBE_EDGE_PREFETCH_MAX_RSS_KB:
        return 'high_rss'
    try:
        available_kb = int(_available_memory_kb() or 0)
    except Exception:
        available_kb = 0
    if (
        YOUTUBE_EDGE_PREFETCH_MIN_AVAILABLE_KB > 0 and
        available_kb > 0 and
        available_kb < YOUTUBE_EDGE_PREFETCH_MIN_AVAILABLE_KB
    ):
        return 'low_available_memory'
    return ''


def _start_youtube_edge_prefetch_external(trigger='manual-fast-key-apply'):
    if not YOUTUBE_EDGE_PREFETCH_ENABLED or YOUTUBE_EDGE_PREFETCH_MODE != 'external':
        return False
    runner_path = os.path.join(BOT_DIR, 'youtube_edge_prefetch_runner.py')
    if not os.path.isfile(runner_path):
        return False
    try:
        subprocess.Popen(
            [sys.executable or 'python3', runner_path, f'--trigger={trigger}'],
            cwd=BOT_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return True
    except Exception as exc:
        _write_runtime_log(f'YouTube edge prefetch external start failed: {type(exc).__name__}')
        return False


def _schedule_youtube_key_apply_prefetch(proto):
    route_proto = _youtube_route_protocol()
    if route_proto not in YOUTUBE_ROUTE_PROTOCOLS or str(proto or '').strip() != route_proto:
        return False
    return _start_youtube_edge_prefetch_external('manual-fast-key-apply')


def _run_youtube_edge_prefetch_once():
    if not youtube_edge_prefetch_lock.acquire(blocking=False):
        status = {
            'ok': False,
            'last_run_at': time.time(),
            'skipped_reason': 'already_running',
        }
        _store_youtube_edge_prefetch_status(status)
        return status
    try:
        route_proto = _youtube_route_protocol()
        skip_reason = _youtube_edge_prefetch_skip_reason()
        if route_proto not in YOUTUBE_ROUTE_PROTOCOLS:
            status = {
                'ok': False,
                'last_run_at': time.time(),
                'route_protocol': '',
                'skipped_reason': 'route_owner_unavailable',
                'candidates': 0,
                'cache_entries': int(youtube_edge_prefetch_state.get('cache_entries') or 0),
                'added_addresses': 0,
                'added_sets': 0,
                'deleted_sets': 0,
                'failed_sets': 0,
            }
        elif skip_reason:
            status = {
                'ok': False,
                'last_run_at': time.time(),
                'route_protocol': route_proto if skip_reason != 'disabled' else '',
                'skipped_reason': skip_reason,
                'candidates': 0,
                'cache_entries': int(youtube_edge_prefetch_state.get('cache_entries') or 0),
                'added_addresses': 0,
                'added_sets': 0,
                'deleted_sets': 0,
                'failed_sets': 0,
            }
            if skip_reason == 'high_rss':
                _memory_cleanup('youtube edge prefetch skipped high RSS', force=True, clear_status=False, log=False)
        else:
            status = _youtube_edge_prefetch().prefetch_once(
                route_protocol=route_proto,
                cache_path=YOUTUBE_EDGE_PREFETCH_CACHE_PATH,
                hosts=_youtube_edge_prefetch_hosts_for_run(),
                dns_servers=YOUTUBE_EDGE_PREFETCH_DNS_SERVERS,
                ipset_contains=_ipset_contains,
                ipset_add=_ipset_add_address,
                ipset_delete=_ipset_delete_address,
                ipset_delete_overlaps=_ipset_delete_overlaps,
                delete_conntrack=_delete_conntrack_for_address,
                cache_ttl_seconds=YOUTUBE_EDGE_PREFETCH_CACHE_TTL_SECONDS,
                max_cache_entries=YOUTUBE_EDGE_PREFETCH_MAX_CACHE_ENTRIES,
                max_hosts_per_run=YOUTUBE_EDGE_PREFETCH_MAX_HOSTS_PER_RUN,
                max_resolved_addresses=YOUTUBE_EDGE_PREFETCH_MAX_RESOLVED_ADDRESSES,
                max_candidates=YOUTUBE_EDGE_PREFETCH_MAX_CANDIDATES,
                max_addresses_per_run=YOUTUBE_EDGE_PREFETCH_MAX_ADDRESSES_PER_RUN,
                remove_from_other_sets=YOUTUBE_EDGE_PREFETCH_EXCLUSIVE_IPSETS,
            )
            if int(status.get('added_addresses') or 0) > 0:
                _memory_cleanup('youtube edge prefetch', clear_status=False, log=False)

        message = _store_youtube_edge_prefetch_status(status)
        signature = (
            str(status.get('skipped_reason') or ''),
            str(status.get('route_protocol') or ''),
            int(status.get('added_addresses') or 0),
            int(status.get('failed_sets') or 0),
        )
        previous_signature = tuple(youtube_edge_prefetch_state.get('last_log_signature') or ())
        should_log = (
            int(status.get('added_addresses') or 0) > 0 or
            int(status.get('failed_sets') or 0) > 0 or
            (status.get('skipped_reason') and signature != previous_signature)
        )
        youtube_edge_prefetch_state['last_log_signature'] = signature
        if should_log:
            _write_runtime_log(f'YouTube edge prefetch: {message}')
        _record_memory_timeline(
            'youtube edge prefetch',
            marker='youtube_edge_prefetch',
            extra={
                'route_protocol': str(status.get('route_protocol') or ''),
                'skipped_reason': str(status.get('skipped_reason') or ''),
                'added_addresses': int(status.get('added_addresses') or 0),
                'added_sets': int(status.get('added_sets') or 0),
                'deleted_sets': int(status.get('deleted_sets') or 0),
                'failed_sets': int(status.get('failed_sets') or 0),
                'cache_entries': int(status.get('cache_entries') or 0),
            },
            force=bool(status.get('skipped_reason') or int(status.get('added_addresses') or 0) > 0),
        )
        return status
    except Exception as exc:
        status = {
            'ok': False,
            'last_run_at': time.time(),
            'skipped_reason': 'error',
            'error': _redact_sensitive_text(exc),
        }
        _store_youtube_edge_prefetch_status(status)
        _write_runtime_log(f'YouTube edge prefetch failed: {_redact_sensitive_text(exc)}')
        return status
    finally:
        youtube_edge_prefetch_lock.release()


def _start_youtube_edge_prefetch_thread():
    if not YOUTUBE_EDGE_PREFETCH_ENABLED:
        return
    if YOUTUBE_EDGE_PREFETCH_MODE != 'thread':
        return
    if not _app_mode_pool_enabled():
        return
    if YOUTUBE_EDGE_PREFETCH_INTERVAL_SECONDS <= 0:
        return

    def worker():
        shutdown_requested.wait(YOUTUBE_EDGE_PREFETCH_START_DELAY_SECONDS)
        while not shutdown_requested.is_set():
            if not _update_maintenance_active():
                _run_youtube_edge_prefetch_once()
            shutdown_requested.wait(YOUTUBE_EDGE_PREFETCH_INTERVAL_SECONDS)

    threading.Thread(target=worker, daemon=True).start()


def _remove_file(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _process_rss_kb(pid='self'):
    try:
        with open(f'/proc/{pid}/status', 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                if line.startswith('VmRSS:'):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
    except Exception:
        return 0
    return 0


def _mem_available_kb_light():
    try:
        with open('/proc/meminfo', 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                if line.startswith('MemAvailable:'):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
    except Exception:
        return 0
    return 0


def _read_cpu_totals():
    try:
        with open('/proc/stat', 'r', encoding='utf-8', errors='ignore') as file:
            first = file.readline().split()
    except Exception:
        return None
    if not first or first[0] != 'cpu':
        return None
    try:
        values = [int(value) for value in first[1:]]
    except Exception:
        return None
    if not values:
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return total, idle


def _pool_probe_cpu_busy_percent():
    if not POOL_PROBE_CPU_GUARD_ENABLED:
        return None
    before = _read_cpu_totals()
    if not before:
        return None
    time.sleep(POOL_PROBE_CPU_SAMPLE_SECONDS)
    after = _read_cpu_totals()
    if not after:
        return None
    total_delta = after[0] - before[0]
    idle_delta = after[1] - before[1]
    if total_delta <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * (total_delta - idle_delta) / float(total_delta)))


def _pool_probe_load_average():
    try:
        with open('/proc/loadavg', 'r', encoding='utf-8', errors='ignore') as file:
            parts = file.read().split()
    except Exception:
        return None
    if not parts:
        return None
    try:
        return float(parts[0])
    except Exception:
        return None


def _background_cpu_busy_percent():
    if not BACKGROUND_TASK_CPU_GUARD_ENABLED:
        return None
    now = time.time()
    if BACKGROUND_TASK_CPU_CACHE_TTL_SECONDS > 0:
        with background_cpu_busy_cache_lock:
            cached_at = float(background_cpu_busy_cache.get('timestamp') or 0.0)
            if now - cached_at < BACKGROUND_TASK_CPU_CACHE_TTL_SECONDS:
                return background_cpu_busy_cache.get('value')
    before = _read_cpu_totals()
    if not before:
        return None
    shutdown_requested.wait(BACKGROUND_TASK_CPU_SAMPLE_SECONDS)
    after = _read_cpu_totals()
    if not after:
        return None
    total_delta = after[0] - before[0]
    idle_delta = after[1] - before[1]
    if total_delta <= 0:
        return None
    value = max(0.0, min(100.0, 100.0 * (total_delta - idle_delta) / float(total_delta)))
    if BACKGROUND_TASK_CPU_CACHE_TTL_SECONDS > 0:
        with background_cpu_busy_cache_lock:
            background_cpu_busy_cache['timestamp'] = time.time()
            background_cpu_busy_cache['value'] = value
    return value


def _background_task_rss_limit(task_class='', allow_high_rss=False):
    task_class = str(task_class or '').strip().lower()
    if allow_high_rss or task_class in ('critical', 'light'):
        return BACKGROUND_TASK_CRITICAL_MAX_BOT_RSS_KB
    return BACKGROUND_TASK_MAX_BOT_RSS_KB


def _background_task_program_rss_limit(task_class='', allow_high_rss=False):
    task_class = str(task_class or '').strip().lower()
    if allow_high_rss or task_class in ('critical', 'light'):
        return BACKGROUND_TASK_CRITICAL_MAX_PROGRAM_RSS_KB
    return BACKGROUND_TASK_MAX_PROGRAM_RSS_KB


def _program_rss_kb(probe_running=None):
    total = int(_process_rss_kb() or 0)
    try:
        if probe_running is None:
            probe_running = bool(pool_probe_lock.locked())
    except Exception:
        probe_running = False
    try:
        related = router_health._related_process_snapshot(time.time(), bool(probe_running))
    except Exception:
        try:
            related = router_health_runtime.related_program_process_snapshot(probe_running=bool(probe_running))
        except Exception:
            related = {}
    if not isinstance(related, dict):
        return total
    for key in (
        'xray_rss_kb',
        'pool_worker_rss_kb',
        'temporary_xray_rss_kb',
        'youtube_prefetch_rss_kb',
        'background_worker_rss_kb',
    ):
        try:
            total += int(related.get(key) or 0)
        except Exception:
            pass
    return total


def _background_task_economy_mode():
    rss_kb = int(_process_rss_kb() or 0)
    if BACKGROUND_TASK_MAX_BOT_RSS_KB > 0 and rss_kb >= BACKGROUND_TASK_MAX_BOT_RSS_KB:
        return True
    program_rss_kb = int(_program_rss_kb() or 0)
    return bool(
        BACKGROUND_TASK_MAX_PROGRAM_RSS_KB > 0 and
        program_rss_kb >= BACKGROUND_TASK_MAX_PROGRAM_RSS_KB
    )


def _background_task_allowed(task_name, *, allow_high_rss=False, task_class='normal'):
    if _update_maintenance_active():
        return False
    now = time.time()
    skip_until = float(background_task_skip_until.get(task_name) or 0.0)
    skip_reason = str(background_task_skip_reason.get(task_name) or '')
    bot_hard_limit_kb = _background_task_rss_limit('critical', allow_high_rss=True)
    program_limit_kb = _background_task_program_rss_limit(task_class, allow_high_rss=allow_high_rss)
    can_bypass_rss_skip = (
        skip_reason in ('rss', 'program_rss') and
        program_limit_kb > 0 and
        program_limit_kb > BACKGROUND_TASK_MAX_PROGRAM_RSS_KB
    )
    if skip_until and now < skip_until and not can_bypass_rss_skip:
        return False
    try:
        if _memory_sensitive_operation_running(ignore_status_refresh=(task_name == 'status refresh')):
            background_task_skip_until[task_name] = now + min(60.0, BACKGROUND_TASK_BUSY_BACKOFF_SECONDS)
            background_task_skip_reason[task_name] = 'busy'
            last_log = float(background_task_skip_log_at.get(task_name) or 0.0)
            if now - last_log >= BACKGROUND_TASK_SKIP_LOG_INTERVAL_SECONDS:
                background_task_skip_log_at[task_name] = now
                _write_runtime_log(f'{task_name}: skipped background check because another operation is running.')
            return False
    except Exception:
        pass
    rss_kb = int(_process_rss_kb() or 0)
    program_rss_kb = int(_program_rss_kb() or rss_kb)
    if program_limit_kb > 0 and program_rss_kb >= program_limit_kb:
        cleanup_label = (
            'status refresh skipped high program RSS'
            if task_name == 'status refresh' else
            f'{task_name} skipped high program RSS'
        )
        cleanup = _memory_cleanup(cleanup_label, force=True, clear_status=False, log=False)
        rss_kb = int(cleanup.get('rss_after_kb') or _process_rss_kb() or rss_kb)
        program_rss_kb = int(_program_rss_kb() or rss_kb)
        if program_rss_kb >= program_limit_kb:
            background_task_skip_until[task_name] = now + BACKGROUND_TASK_BUSY_BACKOFF_SECONDS
            background_task_skip_reason[task_name] = 'program_rss'
            last_log = float(background_task_skip_log_at.get(task_name) or 0.0)
            if now - last_log >= BACKGROUND_TASK_SKIP_LOG_INTERVAL_SECONDS:
                background_task_skip_log_at[task_name] = now
                _write_runtime_log(
                    f'{task_name}: skipped background check because program RSS is high '
                    f'({program_rss_kb} KB >= {program_limit_kb} KB; bot RSS {rss_kb} KB).'
                )
            return False
    if bot_hard_limit_kb > 0 and rss_kb >= bot_hard_limit_kb:
        cleanup_label = 'status refresh skipped high RSS' if task_name == 'status refresh' else f'{task_name} skipped high RSS'
        cleanup = _memory_cleanup(cleanup_label, force=True, clear_status=False, log=False)
        rss_kb = int(cleanup.get('rss_after_kb') or _process_rss_kb() or rss_kb)
        if rss_kb >= bot_hard_limit_kb:
            background_task_skip_until[task_name] = now + BACKGROUND_TASK_BUSY_BACKOFF_SECONDS
            background_task_skip_reason[task_name] = 'rss'
            last_log = float(background_task_skip_log_at.get(task_name) or 0.0)
            if now - last_log >= BACKGROUND_TASK_SKIP_LOG_INTERVAL_SECONDS:
                background_task_skip_log_at[task_name] = now
                _write_runtime_log(
                    f'{task_name}: skipped background check because bot RSS is high '
                    f'({rss_kb} KB >= {bot_hard_limit_kb} KB; program RSS {program_rss_kb} KB).'
                )
            return False
    if BACKGROUND_TASK_MAX_BOT_RSS_KB > 0 and rss_kb >= BACKGROUND_TASK_MAX_BOT_RSS_KB:
        log_key = f'{task_name}:soft_high_rss_allowed'
        last_log = float(background_task_skip_log_at.get(log_key) or 0.0)
        if now - last_log >= BACKGROUND_TASK_SKIP_LOG_INTERVAL_SECONDS:
            background_task_skip_log_at[log_key] = now
            _write_runtime_log(
                f'{task_name}: running with bot RSS above soft guard '
                f'({rss_kb} KB >= {BACKGROUND_TASK_MAX_BOT_RSS_KB} KB; '
                f'program RSS {program_rss_kb} KB, limit {program_limit_kb} KB).'
            )
    cpu_busy = _background_cpu_busy_percent()
    if cpu_busy is None or cpu_busy <= BACKGROUND_TASK_MAX_CPU_PERCENT:
        background_task_skip_until.pop(task_name, None)
        background_task_skip_reason.pop(task_name, None)
        return True
    background_task_skip_until[task_name] = now + BACKGROUND_TASK_BUSY_BACKOFF_SECONDS
    background_task_skip_reason[task_name] = 'cpu'
    last_log = float(background_task_skip_log_at.get(task_name) or 0.0)
    if now - last_log >= BACKGROUND_TASK_SKIP_LOG_INTERVAL_SECONDS:
        background_task_skip_log_at[task_name] = now
        _write_runtime_log(
            f'{task_name}: skipped background check because router CPU is busy '
            f'({cpu_busy:.1f}% > {BACKGROUND_TASK_MAX_CPU_PERCENT:.1f}%).'
        )
    return False


def _run_coordinated_background_task(task_name, callback):
    """Run one costly background operation at a time without dropping it."""
    if _update_maintenance_active():
        return False, None
    if not background_task_coordinator_lock.acquire(blocking=False):
        now = time.time()
        last_log = float(background_task_skip_log_at.get(f'{task_name}:coordinator') or 0.0)
        if now - last_log >= BACKGROUND_TASK_SKIP_LOG_INTERVAL_SECONDS:
            background_task_skip_log_at[f'{task_name}:coordinator'] = now
            active = str(background_task_coordinator_state.get('name') or 'another task')
            _write_runtime_log(f'{task_name}: deferred because {active} is already running.')
        return False, None
    background_task_coordinator_state.update({'name': str(task_name or ''), 'started_at': time.time()})
    try:
        return True, callback()
    finally:
        background_task_coordinator_state.update({'name': '', 'started_at': 0.0})
        background_task_coordinator_lock.release()


def _log_subscription_auto_refresh_skip(reason, detail):
    key = str(reason or 'unknown')
    now = time.time()
    last_log = float(subscription_auto_refresh_skip_log_at.get(key) or 0.0)
    if now - last_log < BACKGROUND_TASK_SKIP_LOG_INTERVAL_SECONDS:
        return
    subscription_auto_refresh_skip_log_at[key] = now
    _write_runtime_log(f'Subscription auto refresh skipped: {detail}')


def _subscription_auto_refresh_allowed(proto):
    task_name = 'Subscription auto refresh'
    now = time.time()
    skip_until = float(background_task_skip_until.get(task_name) or 0.0)
    if skip_until and now < skip_until:
        return False
    if not _background_task_allowed(task_name, task_class='critical'):
        _log_subscription_auto_refresh_skip('shared_guard', f'{proto}: shared background guard is busy')
        return False
    if globals().get('pool_probe_lock') and pool_probe_lock.locked():
        background_task_skip_until[task_name] = now + min(60.0, BACKGROUND_TASK_BUSY_BACKOFF_SECONDS)
        _log_subscription_auto_refresh_skip('pool_probe', f'{proto}: pool probe is running')
        return False
    rss_kb = int(_process_rss_kb() or 0)
    if SUBSCRIPTION_AUTO_REFRESH_MAX_BOT_RSS_KB > 0 and rss_kb >= SUBSCRIPTION_AUTO_REFRESH_MAX_BOT_RSS_KB:
        cleanup = _memory_cleanup('subscription auto refresh high RSS', clear_status=True, log=False)
        rss_kb = int(cleanup.get('rss_after_kb') or _process_rss_kb() or rss_kb)
        if rss_kb >= SUBSCRIPTION_AUTO_REFRESH_MAX_BOT_RSS_KB:
            background_task_skip_until[task_name] = now + BACKGROUND_TASK_BUSY_BACKOFF_SECONDS
            _log_subscription_auto_refresh_skip(
                'rss',
                f'{proto}: bot RSS {rss_kb} KB >= {SUBSCRIPTION_AUTO_REFRESH_MAX_BOT_RSS_KB} KB',
            )
            return False
    available_kb = int(_mem_available_kb_light() or 0)
    if (
        SUBSCRIPTION_AUTO_REFRESH_MIN_AVAILABLE_KB > 0 and
        available_kb > 0 and
        available_kb < SUBSCRIPTION_AUTO_REFRESH_MIN_AVAILABLE_KB
    ):
        background_task_skip_until[task_name] = now + BACKGROUND_TASK_BUSY_BACKOFF_SECONDS
        _log_subscription_auto_refresh_skip(
            'memory',
            f'{proto}: available memory {available_kb} KB < {SUBSCRIPTION_AUTO_REFRESH_MIN_AVAILABLE_KB} KB',
        )
        return False
    load1 = _pool_probe_load_average()
    if (
        SUBSCRIPTION_AUTO_REFRESH_MAX_LOAD1 > 0 and
        load1 is not None and
        load1 > SUBSCRIPTION_AUTO_REFRESH_MAX_LOAD1
    ):
        background_task_skip_until[task_name] = now + BACKGROUND_TASK_BUSY_BACKOFF_SECONDS
        _log_subscription_auto_refresh_skip(
            'load',
            f'{proto}: load1 {load1:.2f} > {SUBSCRIPTION_AUTO_REFRESH_MAX_LOAD1:.2f}',
        )
        return False
    cpu_busy = _background_cpu_busy_percent()
    if (
        SUBSCRIPTION_AUTO_REFRESH_MAX_CPU_PERCENT > 0 and
        cpu_busy is not None and
        cpu_busy > SUBSCRIPTION_AUTO_REFRESH_MAX_CPU_PERCENT
    ):
        background_task_skip_until[task_name] = now + BACKGROUND_TASK_BUSY_BACKOFF_SECONDS
        _log_subscription_auto_refresh_skip(
            'cpu',
            f'{proto}: CPU {cpu_busy:.1f}% > {SUBSCRIPTION_AUTO_REFRESH_MAX_CPU_PERCENT:.1f}%',
        )
        return False
    background_task_skip_until.pop(task_name, None)
    return True


def _youtube_stream_guard_state(proto):
    if proto not in youtube_stream_guard_states:
        youtube_stream_guard_states[proto] = {
            'last_active': 0.0,
            'last_log': 0.0,
            'last_event': 0.0,
            'last_count': 0,
            'last_scan_at': 0.0,
            'last_scan_count': 0,
            'conntrack': {},
            'last_samples': [],
        }
    return youtube_stream_guard_states[proto]


def _youtube_protocol_conntrack_ports(proto):
    ports = set()
    if proto not in YOUTUBE_STREAM_GUARD_PROTOCOLS:
        return ports
    for value in (globals().get(f'localport{proto}'), globals().get(f'localport{proto}_transparent')):
        try:
            port = int(str(value).strip())
        except Exception:
            continue
        if port > 0:
            ports.add(str(port))
    return ports


def _conntrack_packets_bytes(line):
    packets = 0
    bytes_count = 0
    try:
        for value in re.findall(r'\bpackets=(\d+)', line or ''):
            packets += int(value)
        for value in re.findall(r'\bbytes=(\d+)', line or ''):
            bytes_count += int(value)
    except Exception:
        return 0, 0
    return packets, bytes_count


def _conntrack_identity(line):
    fields = re.findall(r'\b(src|dst|sport|dport)=([^ ]+)', line or '')
    if not fields:
        return ''
    # The first two 4-tuples describe original and reply directions; timeouts and counters change often.
    return '|'.join(f'{name}={value}' for name, value in fields[:8])


def _conntrack_tuple_summary(line):
    fields = re.findall(r'\b(src|dst|sport|dport)=([^ ]+)', line or '')
    if len(fields) < 4:
        return {}
    summary = {}
    for index, (name, value) in enumerate(fields[:8]):
        prefix = 'orig' if index < 4 else 'reply'
        summary[f'{prefix}_{name}'] = value
    return summary


def _conntrack_route_diagnostic(proto, sample_limit=6):
    try:
        sample_limit = max(1, min(12, int(sample_limit or 6)))
    except Exception:
        sample_limit = 6
    state = _youtube_stream_guard_state(proto)
    samples = list(state.get('last_samples') or [])[:sample_limit]
    fastnat = []
    try:
        with open('/proc/net/nf_conntrack', 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                if len(fastnat) >= sample_limit:
                    break
                if '[FASTNAT]' not in line or ' dport=443 ' not in line or 'TIME_WAIT' in line or 'CLOSE' in line:
                    continue
                info = _conntrack_tuple_summary(line)
                src = info.get('orig_src', '')
                dst = info.get('orig_dst', '')
                if not src.startswith('192.168.'):
                    continue
                packets, bytes_count = _conntrack_packets_bytes(line)
                fastnat.append({
                    'src': src,
                    'dst': dst,
                    'sport': info.get('orig_sport', ''),
                    'packets': packets,
                    'bytes': bytes_count,
                })
    except Exception:
        pass
    return {
        'proxy_ports': sorted(_youtube_protocol_conntrack_ports(proto)),
        'proxy_samples': samples,
        'fastnat_samples': fastnat,
    }


def _youtube_active_connection_count(proto):
    if not YOUTUBE_STREAM_GUARD_ENABLED:
        return 0
    ports = _youtube_protocol_conntrack_ports(proto)
    if not ports:
        return 0
    now = time.time()
    state = _youtube_stream_guard_state(proto)
    last_scan_at = float(state.get('last_scan_at') or 0.0)
    if last_scan_at and now - last_scan_at < YOUTUBE_STREAM_GUARD_SCAN_CACHE_SECONDS:
        try:
            return max(0, int(state.get('last_scan_count') or 0))
        except Exception:
            return 0
    active = 0
    previous = state.get('conntrack')
    if not isinstance(previous, dict):
        previous = {}
    current = {}
    samples = []
    try:
        with open('/proc/net/nf_conntrack', 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                if ' dport=443 ' not in line and ' dport=443\n' not in line:
                    continue
                if 'TIME_WAIT' in line or 'CLOSE' in line:
                    continue
                if not any(f' sport={port} ' in line or line.rstrip().endswith(f' sport={port}') for port in ports):
                    continue
                packets, bytes_count = _conntrack_packets_bytes(line)
                identity = _conntrack_identity(line)
                if not identity:
                    continue
                current[identity] = {
                    'packets': packets,
                    'bytes': bytes_count,
                    'seen': now,
                }
                old = previous.get(identity, {})
                try:
                    packet_delta = packets - int(old.get('packets') or 0)
                    byte_delta = bytes_count - int(old.get('bytes') or 0)
                except Exception:
                    packet_delta = packets
                    byte_delta = bytes_count
                # On first observation protect already established streams; after that require fresh traffic.
                first_seen = identity not in previous
                if (
                    (first_seen and (packets >= YOUTUBE_STREAM_GUARD_MIN_PACKETS or bytes_count >= YOUTUBE_STREAM_GUARD_MIN_BYTES)) or
                    packet_delta >= YOUTUBE_STREAM_GUARD_MIN_PACKETS or
                    byte_delta >= YOUTUBE_STREAM_GUARD_MIN_BYTES
                ):
                    active += 1
                    if len(samples) < 8:
                        info = _conntrack_tuple_summary(line)
                        samples.append({
                            'src': info.get('orig_src', ''),
                            'dst': info.get('orig_dst', ''),
                            'sport': info.get('orig_sport', ''),
                            'reply_sport': info.get('reply_sport', ''),
                            'packets': packets,
                            'bytes': bytes_count,
                            'delta_packets': packet_delta,
                            'delta_bytes': byte_delta,
                        })
    except Exception:
        return 0
    state['conntrack'] = current
    state['last_samples'] = samples
    state['last_scan_at'] = now
    state['last_scan_count'] = active
    return active


def _youtube_stream_guard_active(proto, reason='', log=False, hold_seconds=None):
    if not YOUTUBE_STREAM_GUARD_ENABLED:
        return False
    now = time.time()
    state = _youtube_stream_guard_state(proto)
    active_count = _youtube_active_connection_count(proto)
    if active_count > 0:
        state['last_active'] = now
        state['last_count'] = active_count
    last_active = float(state.get('last_active') or 0.0)
    try:
        hold = float(hold_seconds if hold_seconds is not None else YOUTUBE_STREAM_GUARD_HOLD_SECONDS)
    except Exception:
        hold = float(YOUTUBE_STREAM_GUARD_HOLD_SECONDS)
    guarded = bool(last_active and now - last_active < max(1.0, hold))
    if guarded and log:
        last_log = float(state.get('last_log') or 0.0)
        if now - last_log >= YOUTUBE_STREAM_GUARD_LOG_INTERVAL:
            state['last_log'] = now
            age = max(0, int(now - last_active))
            count = int(state.get('last_count') or active_count or 0)
            reason_text = str(reason or 'operation')
            service_name = (
                'youtube'
                if proto == _youtube_route_protocol() and ('YouTube' in reason_text or 'UDP/QUIC drift' in reason_text)
                else 'network'
            )
            guard_label = 'YouTube stream guard' if service_name == 'youtube' else 'Traffic stream guard'
            message = (
                f'{guard_label}: deferred {reason_text}; '
                f'active {_pool_proto_label(proto)} connections={count}, last activity {age}s ago.'
            )
            _write_runtime_log(message)
            last_event = float(state.get('last_event') or 0.0)
            if now - last_event >= YOUTUBE_STREAM_GUARD_EVENT_INTERVAL:
                state['last_event'] = now
                if not _recent_event_history_match(
                    'stream_guard_defer',
                    protocol=proto,
                    service=service_name,
                    max_age_seconds=YOUTUBE_STREAM_GUARD_EVENT_INTERVAL,
                ):
                    route_diagnostic = _conntrack_route_diagnostic(proto)
                    _record_event(
                        'stream_guard_defer',
                        message,
                        level='info',
                        source='watchdog',
                        protocol=proto,
                        service=service_name,
                        details={
                            'reason': reason or 'operation',
                            'active_connections': count,
                            'last_activity_age_s': age,
                            'hold_seconds': int(max(1.0, hold)),
                            'scan_active_count': active_count,
                            'event_interval_seconds': int(YOUTUBE_STREAM_GUARD_EVENT_INTERVAL),
                            'route_diagnostic': route_diagnostic,
                        },
                    )
    return guarded


def _vless_traffic_guard_active(reason='', log=False, hold_seconds=None, exclude_proto=None):
    exclude_proto = str(exclude_proto or '').strip().lower()
    for proto in YOUTUBE_STREAM_GUARD_PROTOCOLS:
        if exclude_proto and proto == exclude_proto:
            continue
        if _youtube_stream_guard_active(proto, reason=reason, log=log, hold_seconds=hold_seconds):
            return True
    return False


def _clear_runtime_memory_caches(clear_status=False, *, clear_pool_summary=False):
    if not clear_status and not clear_pool_summary:
        return
    status_snapshot_cache.update({'timestamp': 0, 'data': None, 'signature': None})
    with status_refresh_lock:
        status_refresh_last_started_at.clear()
        status_refresh_last_finished_at.clear()
    with web_status_api_cache_lock:
        web_status_api_cache.update({'timestamp': 0, 'payload': None, 'payloads': {}})
    with active_mode_status_cache_lock:
        active_mode_status_cache.update({'timestamp': 0, 'signature': None, 'status': None})
    if clear_pool_summary:
        with pool_summary_cache_lock:
            pool_summary_cache.update({'signature': None, 'summary': None})
        _invalidate_web_pools_api_cache()
    with event_history_api_cache_lock:
        event_history_api_cache.update({'signature': None, 'payload': None})
    _clear_youtube_edge_prefetch_snapshot_cache()
    try:
        router_health.invalidate(include_heavy=bool(clear_status))
    except Exception:
        pass


def _process_hwm_kb(pid='self'):
    try:
        with open(f'/proc/{pid}/status', 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                if line.startswith('VmHWM:'):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
    except Exception:
        return 0
    return 0


def _safe_file_size(path):
    try:
        return int(os.path.getsize(path))
    except Exception:
        return 0


def _safe_dir_entry_count(path):
    try:
        return len(os.listdir(path))
    except Exception:
        return 0


def _temp_pool_probe_runtime_count():
    try:
        return sum(1 for name in os.listdir('/tmp') if name.startswith('bypass_pool_probe_'))
    except Exception:
        return 0


def _memory_timeline_payload(reason='', marker='', extra=None):
    progress = {}
    try:
        progress = _get_pool_probe_progress()
    except Exception:
        progress = {}
    web_command_running = False
    try:
        web_command_running = bool(_read_web_command_state_file().get('running'))
    except Exception:
        pass
    try:
        refresh_count = len(status_refresh_in_progress)
    except Exception:
        refresh_count = 0
    payload = {
        'ts': time.time(),
        'uptime_s': int(max(0, time.time() - process_started_at)),
        'marker': str(marker or '').strip(),
        'reason': str(reason or '').strip(),
        'rss_kb': int(_process_rss_kb() or 0),
        'hwm_kb': int(_process_hwm_kb() or 0),
        'threads': _safe_dir_entry_count('/proc/self/task'),
        'fd_count': _safe_dir_entry_count('/proc/self/fd'),
        'status_refresh_count': int(refresh_count or 0),
        'pool_probe_running': bool(progress.get('running')),
        'pool_probe_checked': int(progress.get('checked') or 0),
        'pool_probe_total': int(progress.get('total') or 0),
        'web_command_running': web_command_running,
        'key_probe_cache_bytes': _safe_file_size(_KEY_PROBE_CACHE_PATH),
        'event_history_bytes': _safe_file_size(getattr(event_history, 'EVENT_HISTORY_PATH', '')),
        'web_command_state_bytes': _safe_file_size(WEB_COMMAND_STATE_FILE),
        'pool_probe_resume_bytes': _safe_file_size(POOL_PROBE_RESUME_FILE),
        'temp_pool_probe_count': _temp_pool_probe_runtime_count(),
    }
    if isinstance(extra, dict):
        for key, value in extra.items():
            safe_key = str(key or '').strip()
            if safe_key and safe_key not in payload:
                payload[safe_key] = value
    return payload


def _trim_jsonl_file(path, max_events):
    if not path or max_events <= 0:
        return
    try:
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8', errors='ignore') as file:
            tail = deque(file, maxlen=max_events + 1)
        if len(tail) <= max_events:
            return
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix='.' + os.path.basename(path) + '.', suffix='.tmp', dir=directory or None)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as file:
                file.writelines(list(tail)[-max_events:])
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
    except Exception:
        pass


def _maybe_trim_memory_timeline_file(path, now=None):
    global memory_timeline_last_trim_at
    if not path or MEMORY_TIMELINE_MAX_EVENTS <= 0:
        return
    now = time.time() if now is None else float(now or 0)
    if (
        memory_timeline_last_trim_at and
        now - memory_timeline_last_trim_at < MEMORY_TIMELINE_TRIM_MIN_INTERVAL_SECONDS
    ):
        return
    try:
        size = os.path.getsize(path)
    except Exception:
        size = 0
    min_size = max(64 * 1024, MEMORY_TIMELINE_MAX_EVENTS * 512)
    if size and size < min_size:
        return
    _trim_jsonl_file(path, MEMORY_TIMELINE_MAX_EVENTS)
    memory_timeline_last_trim_at = now


def _record_memory_timeline(reason='', marker='', extra=None, force=False):
    global memory_timeline_last_sample_at, memory_timeline_last_error_at
    if not MEMORY_TIMELINE_ENABLED or not MEMORY_TIMELINE_PATH:
        return False
    now = time.time()
    if not force and marker == '' and now - memory_timeline_last_sample_at < MEMORY_TIMELINE_INTERVAL_SECONDS:
        return False
    with memory_timeline_lock:
        now = time.time()
        if not force and marker == '' and now - memory_timeline_last_sample_at < MEMORY_TIMELINE_INTERVAL_SECONDS:
            return False
        payload = _memory_timeline_payload(reason=reason, marker=marker, extra=extra)
        try:
            directory = os.path.dirname(MEMORY_TIMELINE_PATH)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(MEMORY_TIMELINE_PATH, 'a', encoding='utf-8') as file:
                file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n')
            memory_timeline_last_sample_at = now
            _maybe_trim_memory_timeline_file(MEMORY_TIMELINE_PATH, now=now)
            return True
        except Exception as exc:
            if now - memory_timeline_last_error_at >= 300:
                memory_timeline_last_error_at = now
                _write_runtime_log(f'Memory timeline write failed: {exc}')
    return False


def _run_memory_timeline_cycle():
    if MEMORY_TIMELINE_ENABLED and MEMORY_TIMELINE_PATH:
        _record_memory_timeline('periodic sample')


def _load_malloc_trim():
    global memory_malloc_trim_libc, memory_malloc_trim_available
    if memory_malloc_trim_available is not None:
        return memory_malloc_trim_libc
    memory_malloc_trim_available = False
    memory_malloc_trim_libc = None
    import ctypes

    for libc_name in (None, 'libc.so.6', 'libc.so'):
        try:
            libc = ctypes.CDLL(libc_name) if libc_name else ctypes.CDLL(None)
            trim = getattr(libc, 'malloc_trim', None)
            if trim is None:
                continue
            try:
                trim.argtypes = [ctypes.c_size_t]
                trim.restype = ctypes.c_int
            except Exception:
                pass
            memory_malloc_trim_libc = trim
            memory_malloc_trim_available = True
            return memory_malloc_trim_libc
        except Exception:
            continue
    return None


def _malloc_trim(reason='', force=False, rss_kb=None):
    global memory_malloc_trim_last_at
    result = {
        'attempted': False,
        'ok': False,
        'result': None,
        'available': None,
    }
    if not MEMORY_MALLOC_TRIM_ENABLED:
        result['available'] = False
        return result
    rss_kb = int(rss_kb or _process_rss_kb() or 0)
    if not force and MEMORY_MALLOC_TRIM_MIN_RSS_KB > 0 and rss_kb < MEMORY_MALLOC_TRIM_MIN_RSS_KB:
        return result
    now = time.time()
    with memory_malloc_trim_lock:
        if (
            not force and
            memory_malloc_trim_last_at and
            now - memory_malloc_trim_last_at < MEMORY_MALLOC_TRIM_COOLDOWN_SECONDS
        ):
            result['available'] = memory_malloc_trim_available
            return result
        trim = _load_malloc_trim()
        result['available'] = bool(trim)
        if not trim:
            return result
        memory_malloc_trim_last_at = now
        result['attempted'] = True
        try:
            trim_result = int(trim(0))
            result['result'] = trim_result
            result['ok'] = True
        except Exception as exc:
            result['error'] = type(exc).__name__
            if reason:
                _write_runtime_log(f'Memory malloc_trim failed during {reason}: {exc}')
    return result


def _memory_cleanup(reason='', force=False, clear_status=False, log=True):
    global memory_cleanup_last_at
    rss_before = int(_process_rss_kb() or 0)
    if clear_status:
        _clear_runtime_memory_caches(clear_status=True, clear_pool_summary=True)
    thresholds = [
        value for value in (
            int(MEMORY_CLEANUP_RSS_KB or 0),
            int(MEMORY_WATCHDOG_RSS_SOFT_KB or 0),
            int(MEMORY_MALLOC_TRIM_MIN_RSS_KB or 0),
        )
        if value > 0
    ]
    cleanup_threshold = min(thresholds) if thresholds else 0
    should_collect = cleanup_threshold <= 0 or rss_before >= cleanup_threshold
    no_cleanup = {
        'rss_before_kb': rss_before,
        'rss_after_kb': rss_before,
        'collected': 0,
        'malloc_trim': {'attempted': False, 'ok': False, 'result': None, 'available': None},
    }
    if not should_collect:
        return no_cleanup
    now = time.time()
    with memory_cleanup_lock:
        if memory_cleanup_last_at and now - memory_cleanup_last_at < MEMORY_MALLOC_TRIM_COOLDOWN_SECONDS:
            return no_cleanup
        memory_cleanup_last_at = now
        if not clear_status:
            _clear_runtime_memory_caches(clear_status=False, clear_pool_summary=False)
        collected = gc.collect()
        malloc_trim_info = _malloc_trim(
            reason or 'memory cleanup',
            force=False,
            rss_kb=rss_before,
        )
        rss_after = int(_process_rss_kb() or 0)
    if should_collect or force or clear_status:
        _record_memory_timeline(
            reason or 'memory cleanup',
            marker='cleanup',
            extra={
                'rss_before_kb': int(rss_before or 0),
                'rss_after_kb': int(rss_after or 0),
                'gc_collected': int(collected or 0),
                'released_modules': 0,
                'malloc_trim_attempted': bool(malloc_trim_info.get('attempted')),
                'malloc_trim_ok': bool(malloc_trim_info.get('ok')),
                'malloc_trim_result': malloc_trim_info.get('result'),
            },
            force=True,
        )
    if log and reason and should_collect:
        _write_runtime_log(
            f'Memory cleanup ({reason}): rss {rss_before} -> {rss_after} KB, '
            f'gc={collected}, malloc_trim={malloc_trim_info.get("result")}'
        )
    return {
        'rss_before_kb': rss_before,
        'rss_after_kb': rss_after,
        'collected': collected,
        'malloc_trim': malloc_trim_info,
    }


def _memory_sensitive_operation_running(ignore_status_refresh=False):
    try:
        if pool_probe_lock.locked() or pool_apply_lock.locked():
            return True
    except Exception:
        pass
    try:
        if not ignore_status_refresh and status_refresh_in_progress:
            return True
    except Exception:
        pass
    try:
        if _shared_command_job_running():
            return True
    except Exception:
        pass
    try:
        if _read_web_command_state_file().get('running') and _shared_command_job_running(source='web'):
            return True
    except Exception:
        pass
    return False


def _memory_restart_is_safe():
    uptime = time.time() - process_started_at
    if uptime < MEMORY_WATCHDOG_MIN_UPTIME_SECONDS:
        return False
    return not _memory_sensitive_operation_running()


def _schedule_memory_watchdog_restart(rss_kb):
    global memory_watchdog_restart_scheduled, memory_watchdog_last_restart_at
    now = time.time()
    with memory_watchdog_lock:
        if memory_watchdog_restart_scheduled:
            return False
        if memory_watchdog_last_restart_at and now - memory_watchdog_last_restart_at < MEMORY_WATCHDOG_RESTART_COOLDOWN_SECONDS:
            return False
        memory_watchdog_restart_scheduled = True
        memory_watchdog_last_restart_at = now
    try:
        router_health.invalidate(include_heavy=False)
    except Exception:
        pass
    _record_memory_timeline(
        'memory watchdog restart requested',
        marker='watchdog_restart',
        extra={'restart_rss_kb': int(rss_kb or 0)},
        force=True,
    )
    _write_runtime_log(f'Memory watchdog: RSS {rss_kb} KB exceeds limit, restarting bot service')
    try:
        subprocess.Popen(
            ['/bin/sh', '-c', f'sleep 2; {BOT_SERVICE_SCRIPT} restart >/dev/null 2>&1'],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return True
    except Exception as exc:
        with memory_watchdog_lock:
            memory_watchdog_restart_scheduled = False
        _write_runtime_log(f'Memory watchdog restart failed: {exc}')
        return False


def _memory_watchdog_idle_snapshot(payload=None):
    payload = payload or {}
    rss_kb = int(payload.get('bot_rss_kb') or _process_rss_kb() or 0)
    if MEMORY_WATCHDOG_IDLE_RESTART_RSS_KB <= 0:
        return {
            'memory_watchdog_idle_restart_pending': False,
            'memory_watchdog_idle_restart_since': 0.0,
            'memory_watchdog_idle_restart_in_seconds': 0,
            'memory_watchdog_idle_restart_hold_seconds': int(round(MEMORY_WATCHDOG_IDLE_RESTART_HOLD_SECONDS)),
            'memory_watchdog_restart_scheduled': False,
        }

    with memory_watchdog_lock:
        restart_scheduled = bool(memory_watchdog_restart_scheduled)
    since = float(memory_watchdog_high_rss_since or 0.0)
    pending = bool(rss_kb >= MEMORY_WATCHDOG_IDLE_RESTART_RSS_KB)
    remaining = 0
    if pending:
        if since:
            elapsed = max(0.0, time.time() - since)
            remaining = max(0, int(round(MEMORY_WATCHDOG_IDLE_RESTART_HOLD_SECONDS - elapsed)))
        else:
            remaining = int(round(MEMORY_WATCHDOG_IDLE_RESTART_HOLD_SECONDS))
    return {
        'memory_watchdog_idle_restart_pending': pending,
        'memory_watchdog_idle_restart_since': since if pending else 0.0,
        'memory_watchdog_idle_restart_in_seconds': remaining,
        'memory_watchdog_idle_restart_hold_seconds': int(round(MEMORY_WATCHDOG_IDLE_RESTART_HOLD_SECONDS)),
        'memory_watchdog_restart_scheduled': restart_scheduled,
    }


def _record_pool_probe_completion(
    bot_rss_before_kb=0,
    finished_rss_kb=0,
    bot_hwm_kb=0,
    scope='',
    worker_rss_before_kb=0,
    worker_hwm_kb=0,
):
    bot_rss_kb = int(_process_rss_kb() or finished_rss_kb or 0)
    details = [
        f'scope={scope or "manual"}',
        f'bot_rss={bot_rss_kb} KB',
        f'bot_hwm={int(bot_hwm_kb or 0)} KB',
        f'program_rss={int(_program_rss_kb() or 0)} KB',
        f'available={int(_mem_available_kb_light() or 0)} KB',
    ]
    if bot_rss_before_kb:
        details.append(f'bot_rss_before={int(bot_rss_before_kb)} KB')
    if worker_rss_before_kb or worker_hwm_kb:
        details.append(f'worker_rss_before={int(worker_rss_before_kb or 0)} KB')
        details.append(f'worker_hwm={int(worker_hwm_kb or 0)} KB')
    _write_runtime_log('Pool probe completed: ' + ', '.join(details) + '.')

def _run_memory_watchdog_cycle():
    if not MEMORY_WATCHDOG_ENABLED or MEMORY_WATCHDOG_RSS_LIMIT_KB <= 0:
        return
    try:
        rss_kb = _process_rss_kb()
        if rss_kb and MEMORY_WATCHDOG_RSS_SOFT_KB > 0 and rss_kb >= MEMORY_WATCHDOG_RSS_SOFT_KB:
            _memory_cleanup('watchdog-soft', clear_status=True)
            rss_kb = _process_rss_kb() or rss_kb
        if rss_kb and rss_kb >= MEMORY_WATCHDOG_RSS_LIMIT_KB and _memory_restart_is_safe():
            _memory_cleanup('watchdog-restart', force=True, clear_status=True)
            rss_kb = _process_rss_kb() or rss_kb
            _schedule_memory_watchdog_restart(rss_kb)
    except Exception as exc:
        _write_runtime_log(f'Memory watchdog error: {exc}')


def _pool_probe_runtime_cmdline_matches(cmdline):
    cmdline = bytes(cmdline or b'')
    if b'bypass_pool_probe_worker_' in cmdline:
        return False
    return b'bypass_pool_probe_' in cmdline


def _pool_probe_runtime_file_matches(name):
    name = str(name or '')
    if name.startswith('bypass_pool_probe_worker_'):
        return False
    return name.startswith('bypass_pool_probe_')


def _cleanup_pool_probe_runtime_light(kill_processes=False):
    if kill_processes and os.path.isdir('/proc'):
        for name in os.listdir('/proc'):
            if not name.isdigit():
                continue
            pid = int(name)
            if pid == os.getpid():
                continue
            try:
                with open(f'/proc/{name}/cmdline', 'rb') as file:
                    cmdline = file.read().replace(b'\x00', b' ')
            except Exception:
                continue
            if not _pool_probe_runtime_cmdline_matches(cmdline):
                continue
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    try:
        for directory in ('/tmp', '/opt/tmp'):
            if not os.path.isdir(directory):
                continue
            for name in os.listdir(directory):
                if not _pool_probe_runtime_file_matches(name):
                    continue
                path = os.path.join(directory, name)
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        os.remove(path)
                except Exception:
                    pass
    except Exception:
        pass


def _has_socks_support():
    try:
        import socks  # noqa: F401
        return True
    except Exception:
        return False


def _reset_telegram_http_session(reason=''):
    _record_memory_timeline(reason or 'telegram session reset', marker='telegram_session_reset', force=True)
    try:
        session = telebot.apihelper._get_req_session()
        close = getattr(session, 'close', None)
        if close:
            close()
    except Exception:
        pass
    try:
        telebot.apihelper._get_req_session(reset=True)
    except TypeError:
        pass
    except Exception as exc:
        if reason:
            _write_runtime_log(f'Не удалось сбросить Telegram HTTP-сессию ({reason}): {exc}')
    gc.collect()


_install_telegram_send_retry_wrapper()


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


def _update_maintenance_active():
    # The updater creates the marker before sending SIGUSR1 and does not replace
    # files until this process confirms readiness.  The in-process event is
    # therefore authoritative and avoids a filesystem stat on every web and
    # background check during normal operation.
    return update_maintenance_requested.is_set()


def _update_maintenance_web_request_started():
    global update_maintenance_web_requests
    with update_maintenance_web_lock:
        update_maintenance_web_requests += 1


def _update_maintenance_web_request_finished():
    global update_maintenance_web_requests
    with update_maintenance_web_lock:
        update_maintenance_web_requests = max(0, update_maintenance_web_requests - 1)


def _update_maintenance_locks_idle():
    locks = (
        background_task_coordinator_lock,
        pool_probe_lock,
        pool_apply_lock,
        youtube_edge_prefetch_lock,
        telegram_call_learning_lock,
    )
    if any(lock.locked() for lock in locks):
        return False
    with update_maintenance_web_lock:
        if update_maintenance_web_requests:
            return False
    with status_refresh_lock:
        return not status_refresh_in_progress


def _write_update_maintenance_ready():
    temporary = f'{UPDATE_MAINTENANCE_READY_PATH}.tmp.{os.getpid()}'
    try:
        with open(temporary, 'w', encoding='utf-8') as file:
            file.write(str(os.getpid()))
        os.replace(temporary, UPDATE_MAINTENANCE_READY_PATH)
    finally:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass
        except Exception:
            pass


def _update_maintenance_ready_worker():
    try:
        _cleanup_pool_probe_runtime_light(kill_processes=True)
        deadline = time.monotonic() + 30.0
        idle_since = 0.0
        while _update_maintenance_active() and not shutdown_requested.is_set():
            if _update_maintenance_locks_idle():
                if not idle_since:
                    idle_since = time.monotonic()
                elif time.monotonic() - idle_since >= 1.0:
                    _write_update_maintenance_ready()
                    _write_runtime_log('Update maintenance mode is ready; web interface remains available.')
                    return
            else:
                idle_since = 0.0
            if time.monotonic() >= deadline:
                _write_runtime_log('Update maintenance mode could not become idle in 30 seconds.')
                return
            shutdown_requested.wait(0.2)
    except Exception as exc:
        _write_runtime_log(f'Update maintenance preparation failed: {exc}')


def _request_update_maintenance(reason='update'):
    global bot_polling, update_maintenance_ready_thread
    update_maintenance_requested.set()
    bot_polling = False
    pool_probe_cancel_event.set()
    telegram_call_learning_cancel_event.set()
    try:
        bot.stop_polling()
    except Exception:
        pass
    if update_maintenance_ready_thread and update_maintenance_ready_thread.is_alive():
        return
    update_maintenance_ready_thread = threading.Thread(
        target=_update_maintenance_ready_worker,
        name='update-maintenance-ready',
        daemon=True,
    )
    update_maintenance_ready_thread.start()
    _write_runtime_log(f'Update maintenance mode requested: {reason}')


def _release_update_maintenance(reason='update cancelled'):
    update_maintenance_requested.clear()
    pool_probe_cancel_event.clear()
    telegram_call_learning_cancel_event.clear()
    try:
        os.remove(UPDATE_MAINTENANCE_READY_PATH)
    except FileNotFoundError:
        pass
    except Exception:
        pass
    _write_runtime_log(f'Update maintenance mode released: {reason}')


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

    _release_main_instance_lock()


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

    if hasattr(signal, 'SIGUSR1'):
        try:
            signal.signal(signal.SIGUSR1, lambda _signum, _frame: _request_update_maintenance('SIGUSR1'))
        except Exception:
            pass
    if hasattr(signal, 'SIGUSR2'):
        try:
            signal.signal(signal.SIGUSR2, lambda _signum, _frame: _release_update_maintenance('SIGUSR2'))
        except Exception:
            pass


MAIN_INSTANCE_LOCK_DIR = '/tmp/bypass_telegram_bot_main.lock'
MAIN_INSTANCE_PID_FILE = os.path.join(MAIN_INSTANCE_LOCK_DIR, 'pid')
main_instance_lock_acquired = False


def _main_instance_cmdline(pid):
    try:
        with open(f'/proc/{int(pid)}/cmdline', 'rb') as file:
            return file.read(4096).replace(b'\x00', b' ').decode('utf-8', errors='ignore')
    except Exception:
        return ''


def _pid_is_main_instance(pid):
    try:
        pid = int(pid)
    except Exception:
        return False
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    cmdline = _main_instance_cmdline(pid)
    if not cmdline:
        return False
    markers = {
        os.path.abspath(__file__),
        os.path.abspath(sys.argv[0]) if sys.argv else '',
        '/opt/etc/bot/main.py',
        '/opt/etc/bot/bot.py',
    }
    return 'python' in cmdline.lower() and any(marker and marker in cmdline for marker in markers)


def _read_main_instance_lock_pid():
    try:
        with open(MAIN_INSTANCE_PID_FILE, 'r', encoding='utf-8', errors='ignore') as file:
            return int((file.read(32) or '').strip() or '0')
    except Exception:
        return 0


def _release_main_instance_lock():
    global main_instance_lock_acquired
    if not main_instance_lock_acquired:
        return
    pid = _read_main_instance_lock_pid()
    if pid in (0, os.getpid()):
        try:
            shutil.rmtree(MAIN_INSTANCE_LOCK_DIR, ignore_errors=True)
        except Exception:
            pass
    main_instance_lock_acquired = False


def _acquire_main_instance_lock():
    global main_instance_lock_acquired
    if COMMAND_WORKER_MODE or POOL_PROBE_WORKER_MODE:
        return True
    for _ in range(2):
        try:
            os.mkdir(MAIN_INSTANCE_LOCK_DIR)
            with open(MAIN_INSTANCE_PID_FILE, 'w', encoding='utf-8') as file:
                file.write(str(os.getpid()))
            main_instance_lock_acquired = True
            atexit.register(_release_main_instance_lock)
            return True
        except FileExistsError:
            locked_pid = _read_main_instance_lock_pid()
            if locked_pid and locked_pid != os.getpid() and _pid_is_main_instance(locked_pid):
                message = f'Duplicate bot start skipped: main.py is already running as PID {locked_pid}'
                try:
                    _write_runtime_log(message)
                except Exception:
                    pass
                print(message, file=sys.stderr)
                return False
            try:
                shutil.rmtree(MAIN_INSTANCE_LOCK_DIR, ignore_errors=True)
            except Exception:
                pass
            continue
        except Exception as exc:
            try:
                _write_runtime_log(f'Main instance lock unavailable, continuing without singleton guard: {exc}')
            except Exception:
                pass
            return True
    return True


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
        ('/opt/etc/bot/bot_config.py', '/opt/etc/bot_config.py', False),
        ('/opt/etc/bot/main.py', '/opt/etc/bot.py', False),
        ('/opt/etc/bot/main.py', '/opt/etc/bot/bot.py', True),
    ]
    notes = []
    for source_path, legacy_path, replace_existing in mappings:
        try:
            if not os.path.exists(source_path):
                continue
            if os.path.islink(legacy_path):
                if os.path.realpath(legacy_path) == os.path.realpath(source_path):
                    continue
                os.remove(legacy_path)
            elif os.path.exists(legacy_path):
                if not replace_existing:
                    continue
                os.remove(legacy_path)
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
    requests = _requests_module()
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
    return _service_catalog().SERVICE_LIST_SOURCES.get(service_key, {}).get('label', service_key)


def _load_service_entries(service_key, _seen=None):
    seen = set(_seen or ())
    if service_key in seen:
        return []
    seen.add(service_key)
    source = _service_catalog().SERVICE_LIST_SOURCES.get(service_key)
    if not source:
        raise ValueError('Неизвестный сервис')
    if source.get('entries'):
        entries = _socialnet_entries_from_text('\n'.join(_service_catalog().service_route_entries(service_key)))
    else:
        raw_text = _fetch_remote_text(source['url'], timeout=25)
        entries = _parse_service_domains(raw_text)
    for linked_service in source.get('include_services') or []:
        try:
            entries.extend(_load_service_entries(linked_service, _seen=seen))
        except Exception:
            continue
    entries = _socialnet_entries_from_text('\n'.join(entries))
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
    _sync_udp_policy_config()
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
    preset_routes = {item.get('id'): item.get('routes') or [] for item in _custom_check_presets()}
    values = []
    for check in checks:
        check_id = check.get('id')
        source = _service_catalog().SERVICE_LIST_SOURCES.get(check_id) or {}
        if source.get('entries'):
            values.extend(_service_catalog().service_route_entries(check_id))
        else:
            values.extend(preset_routes.get(check_id, []))
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
    _sync_udp_policy_config()
    subprocess.run(["/opt/bin/unblock_update.sh"], check=False)
    _send_unblock_list_menu(message, bypass)
    return True


def _service_list_labels():
    sources = _service_catalog().SERVICE_LIST_SOURCES
    return [
        str(sources[key].get('label') or key)
        for key in SOCIALNET_SERVICE_KEYS
        if key in sources
    ]


def _service_list_markup():
    labels = _service_list_labels()
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
    _sync_udp_policy_config()
    subprocess.run(['/opt/bin/unblock_update.sh'], check=False)
    return len(existing) - before, len(existing)


def _handle_getlist_request(message, service_name, route_name=None, reply_markup=None):
    service_key = _resolve_service_list_name(service_name)
    if not service_key:
        names = ', '.join(_service_list_labels())
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

    source = _service_catalog().SERVICE_LIST_SOURCES[service_key]
    requests = _requests_module()
    try:
        entries = _load_service_entries(service_key)
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
    for proto in POOL_PROTOCOL_ORDER:
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
            names = ', '.join(_service_list_labels())
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
    if action == 'rollback_update':
        started, status_message = _start_telegram_background_command(
            'rollback_update',
            fork_repo_owner,
            fork_repo_name,
            chat_id,
            'main',
        )
        if not started:
            bot.send_message(chat_id, status_message, reply_markup=reply_markup)
            return
        bot.send_message(
            chat_id,
            'Запускаю откат последнего обновления. Будет восстановлена последняя резервная копия, '
            'после чего бот перезапустится и сам пришлёт в этот чат результат.',
            reply_markup=reply_markup,
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
    is_rollback = action == 'rollback_update'
    if is_rollback:
        update_status.write_update_status(
            command='rollback_update',
            running=True,
            progress=5,
            progress_label='Подготовка отката',
            message='Восстанавливается последняя резервная копия.',
        )
    try:
        if is_rollback:
            output = _rollback_last_update()
            return_code = 0 if output.startswith('Откат выполнен') else 1
        else:
            return_code, output = _run_script_action(action, repo_owner, repo_name, branch=branch)
    except Exception as exc:
        return_code = 1
        output = f'Ошибка запуска фоновой команды: {exc}'
    if is_rollback:
        update_status.finish_update_status('rollback_update', output, progress=100)
    _write_json_file(
        TELEGRAM_COMMAND_RESULT_FILE,
        _telegram_command_result_payload(action, chat_id, menu_name, return_code, output),
    )
    _remove_file(TELEGRAM_COMMAND_JOB_FILE)
    _memory_cleanup('telegram command finished', force=True, clear_status=True)


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
    requests = _requests_module()
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
        deliver_result=lambda: None if _update_maintenance_active() else _deliver_pending_telegram_command_result(),
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
    _record_event('script_action_start', f'{action} {repo_owner or ""}/{repo_name or ""}'.strip(), source='update', protocol='system')
    direct_env = _repo_direct_fetch_env(DIRECT_FETCH_ENV_KEYS)
    progress_callback = None
    if progress_command:
        def progress_callback(text):
            _set_web_command_progress(progress_command, text)
        progress_callback('\n'.join(logs))
    if repo_owner and repo_name:
        url, script_text, repo_ref = _repo_download_script(repo_owner, repo_name, branch=branch)
        direct_env['REPO_REF'] = repo_ref
        logs.append(f'Скрипт загружен из {url}')
        logs.append(f'Коммит обновления: {repo_ref[:12]}')
        if repo_owner == fork_repo_owner and 'BOT_CONFIG_PATH' not in script_text:
            logs.append('⚠️ GitHub отдал старую версию script.sh, но legacy-пути уже подготовлены на роутере.')
        if progress_callback:
            progress_callback('\n'.join(logs))
        _repo_write_script(script_text)

    return_code, output = _repo_run_script_and_collect(action, direct_env, logs, progress_callback)
    _record_event(
        'script_action_finish',
        f'{action}: return_code={return_code}',
        level='info' if return_code == 0 else 'warn',
        source='update',
        protocol='system',
    )
    return return_code, output


def _restart_router_services():
    _sync_udp_policy_config()
    commands = [
        '/opt/bin/unblock_update.sh',
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


def _refresh_dns_override_runtime(restart_dnsmasq=False):
    if restart_dnsmasq:
        subprocess.run(
            ['/opt/etc/init.d/S56dnsmasq', 'restart'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    subprocess.run(
        ['/opt/bin/unblock_update.sh'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _set_dns_override(enabled):
    _save_bot_autostart(True)
    if enabled:
        if _dns_override_enabled():
            _refresh_dns_override_runtime(restart_dnsmasq=True)
            return 'DNS Override уже включён. dnsmasq перезапущен, списки и ipset обновлены.'
        os.system("ndmc -c 'opkg dns-override'")
        time.sleep(2)
        os.system("ndmc -c 'system configuration save'")
        _refresh_dns_override_runtime(restart_dnsmasq=True)
        _schedule_router_reboot()
        return '✅ DNS Override включен. Роутер будет автоматически перезагружен через несколько секунд.'
    if not _dns_override_enabled():
        return 'DNS Override уже выключен.'
    os.system("ndmc -c 'no opkg dns-override'")
    time.sleep(2)
    os.system("ndmc -c 'system configuration save'")
    _refresh_dns_override_runtime(restart_dnsmasq=False)
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


def _latest_update_backup_dir(root='/opt/root'):
    try:
        candidates = [
            os.path.join(root, name)
            for name in os.listdir(root)
            if name.startswith('backup-') and os.path.isdir(os.path.join(root, name))
        ]
    except Exception:
        return ''
    if not candidates:
        return ''
    return max(candidates, key=lambda path: (os.path.getmtime(path), path))


def _restore_backup_file(source, target, mode=None):
    if not os.path.isfile(source):
        return False
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(source, target)
    if mode is not None:
        try:
            os.chmod(target, mode)
        except Exception:
            pass
    return True


def _sanitize_xray26_compat_files():
    if xray_compat_runtime is None:
        changed = []
        try:
            if os.path.isfile(CORE_PROXY_CONFIG_PATH):
                with open(CORE_PROXY_CONFIG_PATH, 'r', encoding='utf-8') as file:
                    config_data = json.load(file)
                before = json.dumps(config_data, sort_keys=True)

                def drop_removed_options(value):
                    if isinstance(value, dict):
                        value.pop('allowInsecure', None)
                        for child in value.values():
                            drop_removed_options(child)
                    elif isinstance(value, list):
                        for child in value:
                            drop_removed_options(child)

                drop_removed_options(config_data)
                after = json.dumps(config_data, sort_keys=True)
                if before != after:
                    with open(CORE_PROXY_CONFIG_PATH, 'w', encoding='utf-8') as file:
                        json.dump(config_data, file, ensure_ascii=False, indent=2)
                    changed.append('xray config')
        except Exception as exc:
            _write_runtime_log(f'Xray fallback migration failed for config: {exc}')

        protocols_path = os.path.join(BOT_DIR, 'proxy_protocols.py')
        try:
            if os.path.isfile(protocols_path):
                with open(protocols_path, 'r', encoding='utf-8', errors='ignore') as file:
                    text = file.read()
                if 'allowInsecure' in text:
                    filtered = ''.join(line for line in text.splitlines(True) if 'allowInsecure' not in line)
                    with open(protocols_path, 'w', encoding='utf-8') as file:
                        file.write(filtered)
                    changed.append('proxy_protocols.py')
        except Exception as exc:
            _write_runtime_log(f'Xray fallback migration failed for proxy_protocols.py: {exc}')
        return changed
    return xray_compat_runtime.sanitize_xray26_compat_files(
        config_paths=(CORE_PROXY_CONFIG_PATH,),
        protocols_path=os.path.join(BOT_DIR, 'proxy_protocols.py'),
        logger=_write_runtime_log,
    )


def _validate_xray_core_config():
    if os.path.basename(CORE_PROXY_SERVICE_SCRIPT) != 'S24xray':
        return {'ok': True, 'message': 'non-xray core validation skipped', 'returncode': 0}
    if xray_compat_runtime is None:
        try:
            result = subprocess.run(
                ['/opt/sbin/xray', 'run', '-test', '-c', CORE_PROXY_CONFIG_PATH],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=8,
                check=False,
            )
            validation = {
                'ok': result.returncode == 0,
                'message': '\n'.join((result.stdout or '').splitlines()[-8:]),
                'returncode': result.returncode,
            }
        except Exception as exc:
            validation = {'ok': False, 'message': str(exc), 'returncode': None}
    else:
        validation = xray_compat_runtime.validate_xray_config(CORE_PROXY_CONFIG_PATH, timeout=8)
    if not validation.get('ok'):
        message = str(validation.get('message') or '').strip()
        _write_runtime_log(f'Xray config validation failed: {message}')
    return validation


def _restart_core_proxy_after_validation():
    validation = _validate_xray_core_config()
    if not validation.get('ok'):
        return False, f'Xray config error: {str(validation.get("message") or "").strip()}'
    if xray_compat_runtime is None:
        try:
            result_obj = subprocess.run(
                [CORE_PROXY_SERVICE_SCRIPT, 'restart'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=20,
                check=False,
            )
            result = {
                'ok': result_obj.returncode == 0,
                'message': '\n'.join((result_obj.stdout or '').splitlines()[-5:]),
            }
        except Exception as exc:
            result = {'ok': False, 'message': str(exc)}
    else:
        result = xray_compat_runtime.restart_service(CORE_PROXY_SERVICE_SCRIPT, timeout=20)
    if not result.get('ok'):
        message = str(result.get('message') or '').strip()
        _write_runtime_log(f'Core proxy restart failed: {message}')
        return False, f'Core proxy restart failed: {message}'
    time.sleep(2)
    if xray_compat_runtime is None:
        service_ok = _port_is_listening(localportvless) and _port_is_listening(localportvless2)
        health = {'ok': service_ok}
        note = 'Xray: restarted; module fallback; ports checked.' if service_ok else 'Xray: restart requested; ports are not ready.'
    else:
        health = xray_compat_runtime.core_proxy_health(
            xray_config_path=CORE_PROXY_CONFIG_PATH,
            xray_service_path=CORE_PROXY_SERVICE_SCRIPT,
        )
        note = xray_compat_runtime.core_proxy_note(health)
    if not health.get('ok'):
        _write_runtime_log(f'Core proxy health warning: {note}')
    return bool(health.get('ok')), note


def _rollback_last_update():
    backup_dir = _latest_update_backup_dir()
    if not backup_dir:
        return 'Резервная копия обновления не найдена в /opt/root/backup-* .'
    restored = []
    main_source = os.path.join(backup_dir, 'bot.py')
    if _restore_backup_file(main_source, BOT_SOURCE_PATH, 0o755):
        restored.append('main.py')
    for name in os.listdir(backup_dir):
        if not name.endswith('.py') or name == 'bot.py':
            continue
        if _restore_backup_file(os.path.join(backup_dir, name), os.path.join(BOT_DIR, name), 0o644):
            restored.append(name)
    for name in ('version.md', 'README.md'):
        if _restore_backup_file(os.path.join(backup_dir, name), os.path.join(BOT_DIR, name), 0o644):
            restored.append(name)
    static_source = os.path.join(backup_dir, 'static')
    static_target = os.path.join(BOT_DIR, 'static')
    static_absent_marker = os.path.join(backup_dir, '.static-absent')
    try:
        if os.path.isdir(static_source):
            if os.path.exists(static_target) or os.path.islink(static_target):
                if os.path.islink(static_target) or os.path.isfile(static_target):
                    os.unlink(static_target)
                else:
                    shutil.rmtree(static_target)
            shutil.copytree(static_source, static_target)
            restored.append('static')
        elif os.path.exists(static_absent_marker) and (os.path.exists(static_target) or os.path.islink(static_target)):
            if os.path.islink(static_target) or os.path.isfile(static_target):
                os.unlink(static_target)
            else:
                shutil.rmtree(static_target)
            restored.append('static')
    except Exception as exc:
        return f'Backup найден ({backup_dir}), но static assets не удалось восстановить: {exc}'
    fixed_targets = {
        'bot_app_mode': (APP_RUNTIME_MODE_FILE, 0o644),
        'bot_proxy_mode': (PROXY_MODE_FILE, 0o644),
        'bot_autostart': (BOT_AUTOSTART_FILE, 0o644),
        'bot_config.py': (os.path.join(BOT_DIR, 'bot_config.py'), 0o644),
        'key_pools.json': (os.path.join(BOT_DIR, 'key_pools.json'), 0o644),
        'subscriptions.json': (os.path.join(BOT_DIR, 'subscriptions.json'), 0o644),
        'custom_checks.json': (os.path.join(BOT_DIR, 'custom_checks.json'), 0o644),
        'vmess.key': (VMESS_KEY_PATH, 0o600),
        'vless.key': (VLESS_KEY_PATH, 0o600),
        'vless2.key': (VLESS2_KEY_PATH, 0o600),
        'xray_config.json': ('/opt/etc/xray/config.json', 0o644),
        'v2ray_config.json': ('/opt/etc/v2ray/config.json', 0o644),
        'shadowsocks.json': ('/opt/etc/shadowsocks.json', 0o644),
        'trojan_config.json': ('/opt/etc/trojan/config.json', 0o644),
        'unblock_shadowsocks.txt': ('/opt/etc/unblock/shadowsocks.txt', 0o644),
        'unblock_trojan.txt': ('/opt/etc/unblock/trojan.txt', 0o644),
        'unblock_vmess.txt': ('/opt/etc/unblock/vmess.txt', 0o644),
        'unblock_vless.txt': ('/opt/etc/unblock/vless.txt', 0o644),
        'unblock_vless2.txt': ('/opt/etc/unblock/vless-2.txt', 0o644),
        'installer.py': ('/opt/etc/bot/installer.py', 0o755),
        'S98telegram_bot_installer': ('/opt/etc/init.d/S98telegram_bot_installer', 0o755),
        'S99telegram_bot': ('/opt/etc/init.d/S99telegram_bot', 0o755),
        'unblock_ipset.sh': ('/opt/bin/unblock_ipset.sh', 0o755),
        'unblock_dnsmasq.sh': ('/opt/bin/unblock_dnsmasq.sh', 0o755),
        'unblock_update.sh': ('/opt/bin/unblock_update.sh', 0o755),
        'dnsmasq.conf': ('/opt/etc/dnsmasq.conf', 0o644),
        'crontab': ('/opt/etc/crontab', 0o644),
        'S99unblock': ('/opt/etc/init.d/S99unblock', 0o755),
        '100-ipset.sh': ('/opt/etc/ndm/fs.d/100-ipset.sh', 0o755),
        '100-redirect.sh': ('/opt/etc/ndm/netfilter.d/100-redirect.sh', 0o755),
        'script.sh': ('/opt/root/script.sh', 0o755),
    }
    for name, (target, mode) in fixed_targets.items():
        if _restore_backup_file(os.path.join(backup_dir, name), target, mode):
            restored.append(name)
    bot_config_backup = os.path.join(backup_dir, 'bot_config.py')
    if os.path.exists(bot_config_backup) and _restore_backup_file(bot_config_backup, '/opt/etc/bot_config.py', 0o644):
        restored.append('bot_config.py legacy')
    restored.extend(_sanitize_xray26_compat_files())
    core_ok, core_message = _restart_core_proxy_after_validation()
    if not restored:
        return f'Backup найден ({backup_dir}), но в нём нет файлов для восстановления.'
    _invalidate_web_status_cache()
    _schedule_app_service_restart()
    core_tail = f' Core proxy: {core_message}'
    if not core_ok:
        core_tail = f' Внимание: {core_message}'
    return (
        f'Откат выполнен из {backup_dir}. Восстановлено файлов: {len(restored)}. '
        'Сервис бота будет перезапущен через несколько секунд.'
        f'{core_tail}'
    )


def _run_web_command(command):
    return web_commands_runtime.run_web_command(
        command,
        run_script_action=_run_script_action,
        fork_repo_owner=fork_repo_owner,
        fork_repo_name=fork_repo_name,
        rollback_last_update=_rollback_last_update,
        restart_router_services=_restart_router_services,
        set_dns_override=_set_dns_override,
    )


def _read_text_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            return file.read()
    except Exception:
        return ''


def _current_bot_version():
    return APP_VERSION_LABEL


def _save_unblock_list(list_name, text):
    if not os.path.basename(list_name).endswith('.txt'):
        raise ValueError('Список должен быть .txt файлом')
    safe_name = _save_unblock_list_file(list_name, text, before_update=_sync_udp_policy_config, async_update=True)
    return f'Список {safe_name} сохранён. Применение маршрутов запущено в фоне.'


def _route_tools_runtime():
    global _web_route_tools_runtime
    if _web_route_tools_runtime is None:
        from web_route_tools_runtime import ServiceRouteToolsRuntime

        _web_route_tools_runtime = ServiceRouteToolsRuntime(
            custom_check_presets_getter=_custom_check_presets,
            service_icon_html=_service_icon_html,
            telegram_icon_html=_telegram_icon_html,
            youtube_icon_html=_youtube_icon_html,
            sync_udp_policy_config=_sync_udp_policy_config,
            invalidate_web_status_cache=_invalidate_web_status_cache,
            intersections_cache_ttl=SERVICE_ROUTE_INTERSECTIONS_CACHE_TTL,
        )
    return _web_route_tools_runtime


def _service_route_summary():
    return _route_tools_runtime().summary()


def _standalone_custom_checks_light(custom_checks):
    route_service_ids = {'telegram', 'youtube'}
    try:
        route_service_ids.update(
            str(item.get('id') or '')
            for item in (_custom_check_presets() or [])
            if isinstance(item, dict) and item.get('id')
        )
    except Exception:
        pass
    return [
        check for check in (custom_checks or [])
        if str(check.get('id') or '') not in route_service_ids
    ]


def _route_intersections_snapshot():
    return _route_tools_runtime().intersections_snapshot()


def _apply_service_route(service_key, target_protocol):
    return _route_tools_runtime().apply_service_route(service_key, target_protocol)


def _apply_service_profile(profile_id):
    return _route_tools_runtime().apply_service_profile(profile_id)


def _resolve_route_intersections(target_route):
    return _route_tools_runtime().resolve_route_intersections(target_route)


def _event_history_snapshot(limit=50):
    return event_history.load_events(limit=limit)


def _event_history_payload(limit=50):
    try:
        limit_value = max(1, int(limit or 50))
    except Exception:
        limit_value = 50
    events = _event_history_snapshot(limit=limit_value)
    return {
        'events': events,
        'html': web_form_blocks.render_event_history_html(events),
    }


def _update_status_snapshot():
    state = update_status.read_update_status()
    command_state = _get_web_command_state()
    if command_state.get('running') and command_state.get('command') in WEB_UPDATE_COMMANDS:
        state.update({
            'running': True,
            'command': command_state.get('command'),
            'progress': command_state.get('progress', 0),
            'progress_label': command_state.get('progress_label', ''),
            'message': command_state.get('result', ''),
            'started_at': command_state.get('started_at', 0),
            'expected_seconds': command_state.get('expected_seconds', 0),
            'expected_samples': command_state.get('expected_samples', 0),
        })
    return state


def _route_tools_html(
    csrf_input_html,
    custom_checks=None,
    *,
    include_intersections=True,
    include_runtime_intersections=False,
):
    return _route_tools_runtime().tools_html(
        csrf_input_html,
        custom_checks,
        include_intersections=include_intersections,
        include_runtime_intersections=include_runtime_intersections,
    )


def _deferred_route_tools_html():
    return '''<div class="route-intersection-card" data-route-tools-deferred="1">
                <strong>Маршруты загружаются</strong>
                <small>Список сервисов и пересечения будут подставлены без блокировки проверки ключа.</small>
            </div>'''


def _web_service_routes_worker_payload():
    if not WEB_SERVICE_ROUTES_WORKER_ENABLED:
        return None
    worker_path = os.path.join(BOT_DIR, 'web_service_routes_worker.py')
    if not os.path.isfile(worker_path):
        return None
    try:
        result = subprocess.run(
            [sys.executable or 'python3', worker_path],
            input='{}',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=WEB_SERVICE_ROUTES_WORKER_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception as exc:
        _write_runtime_log(f'Web service routes worker unavailable: {type(exc).__name__}')
        return None
    if result.returncode != 0:
        error_text = str(result.stderr or '').strip().splitlines()[:1]
        error_label = error_text[0][:120] if error_text else f'exit {result.returncode}'
        _write_runtime_log(f'Web service routes worker failed: {error_label}')
        return None
    try:
        payload = json.loads(result.stdout or '{}')
    except Exception as exc:
        _write_runtime_log(f'Web service routes worker returned invalid JSON: {type(exc).__name__}')
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get('route_tools_html'), str):
        return None
    return payload


def _build_web_service_routes_payload():
    worker_payload = _web_service_routes_worker_payload()
    if worker_payload is not None:
        return worker_payload
    custom_checks = _load_custom_checks()
    return {
        'route_tools_html': _route_tools_html(
            '',
            custom_checks,
            include_intersections=True,
            include_runtime_intersections=False,
        ),
    }


def _web_service_routes_payload():
    signature = _web_service_routes_cache_signature()
    now = time.monotonic()
    with web_service_routes_cache_lock:
        cached_payload = web_service_routes_cache.get('payload')
        if (
            cached_payload is not None and
            web_service_routes_cache.get('signature') == signature and
            now - float(web_service_routes_cache.get('timestamp') or 0.0) < WEB_SERVICE_ROUTES_CACHE_TTL_SECONDS
        ):
            return dict(cached_payload)
    with web_service_routes_build_lock:
        now = time.monotonic()
        with web_service_routes_cache_lock:
            cached_payload = web_service_routes_cache.get('payload')
            if (
                cached_payload is not None and
                web_service_routes_cache.get('signature') == signature and
                now - float(web_service_routes_cache.get('timestamp') or 0.0) < WEB_SERVICE_ROUTES_CACHE_TTL_SECONDS
            ):
                return dict(cached_payload)
        payload = _build_web_service_routes_payload()
        with web_service_routes_cache_lock:
            web_service_routes_cache['timestamp'] = now
            web_service_routes_cache['signature'] = signature
            web_service_routes_cache['payload'] = dict(payload)
        return payload


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


def _web_unblock_list_payload(list_name):
    safe_base = _normalize_unblock_route_name(list_name)
    safe_name = f'{safe_base}.txt'
    visible = {entry.get('name'): entry for entry in _load_unblock_lists(with_content=False)}
    if safe_name not in visible:
        raise ValueError('Список недоступен для редактирования')
    content = _read_text_file(_unblock_list_path(safe_base)).strip()
    return {
        'ok': True,
        'name': safe_name,
        'label': visible[safe_name].get('label', safe_name),
        'content': content,
        'line_count': len([line for line in content.splitlines() if line.strip()]),
    }


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
    pools, changed = _key_pool_store().ensure_current_keys_in_pools(_load_key_pools(), current_keys)
    if changed:
        _save_key_pools(pools)
    return pools


def _invalidate_status_snapshot_cache():
    status_snapshot_cache['timestamp'] = 0
    status_snapshot_cache['data'] = None
    status_snapshot_cache['signature'] = None
    with status_refresh_lock:
        status_refresh_last_started_at.clear()
        status_refresh_last_finished_at.clear()
    _invalidate_web_status_api_cache()


def _invalidate_web_status_api_cache():
    with web_status_api_cache_lock:
        web_status_api_cache['timestamp'] = 0
        web_status_api_cache['payload'] = None
        web_status_api_cache['payloads'] = {}
    _invalidate_pool_summary_cache()


def _invalidate_pool_data_cache():
    _invalidate_web_status_api_cache()


def _invalidate_pool_summary_cache():
    with pool_summary_cache_lock:
        pool_summary_cache['signature'] = None
        pool_summary_cache['summary'] = None
    _invalidate_web_pools_api_cache()


def _invalidate_web_pools_api_cache():
    with web_pools_api_cache_lock:
        web_pools_api_cache['timestamp'] = 0
        web_pools_api_cache['signature'] = None
        web_pools_api_cache['payload'] = None
        web_pools_api_cache['entries'] = {}


def _file_cache_signature(path):
    try:
        stat_info = os.stat(path)
        return (stat_info.st_mtime_ns, stat_info.st_size)
    except Exception:
        return None


def _web_service_routes_cache_signature():
    route_names = ('vless', 'vless-2', 'vmess', 'trojan', 'shadowsocks')
    return (
        tuple((name, _file_cache_signature(_unblock_list_path(name))) for name in route_names),
        _file_cache_signature(_CUSTOM_CHECKS_PATH),
    )


def _pool_summary_cache_signature(current_keys, route_states=None):
    current_keys = current_keys or {}
    route_state_sig = []
    if isinstance(route_states, dict):
        for service_id, state in sorted(route_states.items()):
            if not isinstance(state, dict):
                continue
            route_state_sig.append((
                service_id,
                tuple(state.get('complete_protocols') or []),
                tuple(state.get('partial_protocols') or []),
            ))
    return (
        tuple((proto, current_keys.get(proto, '')) for proto in POOL_PROTOCOL_ORDER),
        _file_cache_signature(KEY_POOLS_PATH),
        _file_cache_signature(_KEY_PROBE_CACHE_PATH),
        _file_cache_signature(_CUSTOM_CHECKS_PATH),
        tuple(route_state_sig),
    )


def _get_web_status_api_cache(cache_key='full'):
    with web_status_api_cache_lock:
        payloads = web_status_api_cache.get('payloads') or {}
        cached = payloads.get(str(cache_key or 'full'))
        if isinstance(cached, dict) and cached.get('payload') is not None:
            return {
                'timestamp': cached.get('timestamp', 0),
                'payload': cached.get('payload'),
            }
        payload = web_status_api_cache.get('payload')
        return {
            'timestamp': web_status_api_cache.get('timestamp', 0),
            'payload': payload,
        } if payload is not None and str(cache_key or 'full') == 'full' else None


def _store_web_status_api_cache(payload, timestamp=None, cache_key='full'):
    rss_kb = int(_process_rss_kb() or 0)
    if rss_kb and MEMORY_CLEANUP_RSS_KB > 0 and rss_kb >= MEMORY_CLEANUP_RSS_KB:
        with web_status_api_cache_lock:
            web_status_api_cache.update({'timestamp': 0, 'payload': None, 'payloads': {}})
        return
    key = str(cache_key or 'full')
    cache_timestamp = time.time() if timestamp is None else timestamp
    with web_status_api_cache_lock:
        payloads = web_status_api_cache.setdefault('payloads', {})
        payloads[key] = {'timestamp': cache_timestamp, 'payload': payload}
        if key == 'full':
            web_status_api_cache['timestamp'] = cache_timestamp
            web_status_api_cache['payload'] = payload


def _web_pools_api_cache_signature(current_keys, protocols):
    return (
        tuple(protocols or ()),
        _pool_summary_cache_signature(current_keys),
    )


def _get_web_pools_api_cache(current_keys, protocols, now=None):
    now = time.time() if now is None else now
    signature = _web_pools_api_cache_signature(current_keys, protocols)
    cached_payload = None
    with web_pools_api_cache_lock:
        entries = web_pools_api_cache.get('entries') or {}
        cached = entries.get(signature)
        if (
            isinstance(cached, dict) and
            cached.get('payload') is not None and
            now - float(cached.get('timestamp') or 0.0) <= WEB_POOLS_API_CACHE_TTL
        ):
            cached_payload = cached.get('payload')
        payload = web_pools_api_cache.get('payload')
        if not cached_payload and (
            payload is not None and
            web_pools_api_cache.get('signature') == signature and
            now - float(web_pools_api_cache.get('timestamp') or 0.0) <= WEB_POOLS_API_CACHE_TTL
        ):
            cached_payload = payload
    return cached_payload if isinstance(cached_payload, str) else None


def _store_web_pools_api_cache(current_keys, protocols, payload, timestamp=None):
    try:
        serialized_payload = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    except (TypeError, ValueError):
        return
    rss_kb = int(_process_rss_kb() or 0)
    if rss_kb and MEMORY_CLEANUP_RSS_KB > 0 and rss_kb >= MEMORY_CLEANUP_RSS_KB:
        with web_pools_api_cache_lock:
            web_pools_api_cache.update({'timestamp': 0, 'signature': None, 'payload': None, 'entries': {}})
        return
    signature = _web_pools_api_cache_signature(current_keys, protocols)
    cache_timestamp = time.time() if timestamp is None else timestamp
    with web_pools_api_cache_lock:
        entries = web_pools_api_cache.setdefault('entries', {})
        entries[signature] = {'timestamp': cache_timestamp, 'payload': serialized_payload}
        if len(entries) > WEB_POOLS_API_CACHE_MAX_ENTRIES:
            oldest = sorted(entries.items(), key=lambda item: float((item[1] or {}).get('timestamp') or 0.0))
            for key, _value in oldest[:max(0, len(entries) - WEB_POOLS_API_CACHE_MAX_ENTRIES)]:
                entries.pop(key, None)
        web_pools_api_cache['timestamp'] = cache_timestamp
        web_pools_api_cache['signature'] = signature
        web_pools_api_cache['payload'] = serialized_payload


def _append_status_note(note, extra):
    clean_note = str(note or '').strip().rstrip('.')
    clean_extra = str(extra or '').strip().rstrip('.')
    if not clean_note:
        return clean_extra
    if not clean_extra:
        return clean_note
    note_lines = clean_note.split('\n\n')
    if len(note_lines) >= 2:
        note_lines[1] = '; '.join(part for part in (note_lines[1].strip().rstrip('.'), clean_extra) if part)
        return '\n\n'.join(note_lines)
    return '; '.join(part for part in (clean_note, clean_extra) if part)


def _router_health_snapshot(compact=False, sample_cpu=True, force_refresh=False, prime_cpu=False):
    payload = router_health.snapshot(
        _get_pool_probe_progress,
        compact=compact,
        sample_cpu=False,
        force_refresh=force_refresh,
        prime_cpu=False,
    )
    payload['memory_timeline_enabled'] = bool(MEMORY_TIMELINE_ENABLED and MEMORY_TIMELINE_PATH)
    payload['memory_timeline_path'] = MEMORY_TIMELINE_PATH if MEMORY_TIMELINE_ENABLED else ''
    payload['memory_timeline_bytes'] = _safe_file_size(MEMORY_TIMELINE_PATH) if MEMORY_TIMELINE_ENABLED else 0
    payload['youtube_edge_prefetch'] = _youtube_edge_prefetch_snapshot()
    idle_memory_state = _memory_watchdog_idle_snapshot(payload)
    payload.update(idle_memory_state)
    threshold_mb = int(round(MEMORY_WATCHDOG_IDLE_RESTART_RSS_KB / 1024.0)) if MEMORY_WATCHDOG_IDLE_RESTART_RSS_KB > 0 else 0
    if idle_memory_state.get('memory_watchdog_restart_scheduled'):
        note = str(payload.get('note') or '').strip()
        payload['note'] = _append_status_note(note, f'RSS бота выше порога {threshold_mb} MB; автоперезапуск уже запрошен')
    elif idle_memory_state.get('memory_watchdog_idle_restart_pending'):
        retry_in = int(idle_memory_state.get('memory_watchdog_idle_restart_in_seconds') or 0)
        if _memory_sensitive_operation_running():
            idle_note = f'RSS бота выше порога {threshold_mb} MB; автоперезапуск ждёт завершения фоновых операций'
        elif retry_in > 0:
            idle_note = f'RSS бота выше порога {threshold_mb} MB; автоперезапуск в простое примерно через {retry_in} с, если память не освободится'
        else:
            idle_note = f'RSS бота выше порога {threshold_mb} MB; watchdog выполнит очистку и перезапуск на ближайшем цикле'
        note = str(payload.get('note') or '').strip()
        payload['note'] = _append_status_note(note, idle_note)
    return payload


def _router_metrics_snapshot(include_history=False):
    if not include_history and ROUTER_METRICS_COMPACT_CACHE_TTL > 0:
        now = time.time()
        with router_metrics_compact_cache_lock:
            cached = router_metrics_compact_cache.get('payload')
            cached_at = float(router_metrics_compact_cache.get('timestamp') or 0.0)
            if cached is not None and now - cached_at <= ROUTER_METRICS_COMPACT_CACHE_TTL:
                return dict(cached)
    payload = router_metrics_runtime.snapshot(include_history=include_history)
    payload['version'] = APP_VERSION_LABEL
    payload['app_mode'] = _load_app_runtime_mode()
    if not include_history and ROUTER_METRICS_COMPACT_CACHE_TTL > 0:
        with router_metrics_compact_cache_lock:
            router_metrics_compact_cache['timestamp'] = time.time()
            router_metrics_compact_cache['payload'] = dict(payload)
    return payload


def _invalidate_key_status_cache():
    _invalidate_status_snapshot_cache()


def _check_http_through_proxy(proxy_url, url='https://www.youtube.com/generate_204', connect_timeout=2, read_timeout=3):
    return _status_check_http(proxy_url, url=url, connect_timeout=connect_timeout, read_timeout=read_timeout)


def _pool_probe_quality_download_url(bytes_limit=None):
    url = POOL_PROBE_QUALITY_DOWNLOAD_URL
    if not url:
        return ''
    bytes_value = max(0, int(bytes_limit or POOL_PROBE_QUALITY_DOWNLOAD_BYTES))
    if '{bytes}' in url:
        try:
            return url.format(bytes=bytes_value)
        except Exception:
            return url
    return url


def _pool_probe_quality_settings():
    return {
        'enabled': POOL_PROBE_QUALITY_ENABLED and POOL_PROBE_QUALITY_DOWNLOAD_BYTES > 0,
        'download_url': _pool_probe_quality_download_url(POOL_PROBE_QUALITY_DOWNLOAD_BYTES),
        'download_bytes': POOL_PROBE_QUALITY_DOWNLOAD_BYTES,
        'download_connect_timeout': POOL_PROBE_QUALITY_DOWNLOAD_CONNECT_TIMEOUT,
        'download_read_timeout': POOL_PROBE_QUALITY_DOWNLOAD_READ_TIMEOUT,
        'stable_latency_ms': POOL_PROBE_QUALITY_STABLE_LATENCY_MS,
        'fast_latency_ms': POOL_PROBE_QUALITY_FAST_LATENCY_MS,
        'min_1600p_mbps': POOL_PROBE_QUALITY_1600P_MIN_MBPS,
        'min_4k_mbps': POOL_PROBE_QUALITY_4K_MIN_MBPS,
    }


def _reset_pool_probe_quality_sample_budget():
    global pool_probe_quality_sample_count
    with pool_probe_quality_sample_lock:
        pool_probe_quality_sample_count = 0


def _pool_probe_quality_sample_allowed():
    if not POOL_PROBE_QUALITY_ENABLED or POOL_PROBE_QUALITY_DOWNLOAD_BYTES <= 0:
        return False
    available_kb = _available_memory_kb()
    if (
        POOL_PROBE_QUALITY_MIN_AVAILABLE_KB > 0 and
        available_kb is not None and
        available_kb < POOL_PROBE_QUALITY_MIN_AVAILABLE_KB
    ):
        return False
    if POOL_PROBE_QUALITY_MAX_SAMPLES_PER_RUN <= 0:
        return True
    global pool_probe_quality_sample_count
    with pool_probe_quality_sample_lock:
        if pool_probe_quality_sample_count >= POOL_PROBE_QUALITY_MAX_SAMPLES_PER_RUN:
            return False
        pool_probe_quality_sample_count += 1
    return True


def _measure_limited_pool_probe_quality_download(proxy_url, **kwargs):
    if not _pool_probe_quality_sample_allowed():
        return None, ''
    return _measure_quality_download_through_proxy(proxy_url, **kwargs)


def _measure_quality_download_through_proxy(proxy_url, url='', bytes_limit=0, connect_timeout=2, read_timeout=8):
    bytes_limit = max(0, int(bytes_limit or POOL_PROBE_QUALITY_DOWNLOAD_BYTES))
    target_url = str(url or _pool_probe_quality_download_url(bytes_limit)).strip()
    if not target_url or bytes_limit <= 0:
        return None, 'quality download sample is disabled'
    requests = _requests_module()
    session = requests.Session()
    session.trust_env = False
    started_at = time.monotonic()
    received = 0
    try:
        response = session.get(
            target_url,
            timeout=(connect_timeout, read_timeout),
            proxies={'https': proxy_url, 'http': proxy_url},
            headers={'User-Agent': 'bypass_keenetic quality check'},
            stream=True,
        )
        status_code = int(response.status_code)
        if status_code >= 500:
            response.close()
            return None, f'quality download returned HTTP {status_code}'
        for chunk in response.iter_content(chunk_size=32768):
            if not chunk:
                continue
            received += len(chunk)
            if received >= bytes_limit:
                break
        response.close()
        elapsed = max(0.001, time.monotonic() - started_at)
        if received < min(bytes_limit, 32768):
            return None, f'quality download sample too short: {received} bytes'
        return round((received * 8.0) / elapsed / 1000000.0, 2), ''
    except requests.exceptions.RequestException as exc:
        return None, str(exc).splitlines()[0][:180]
    finally:
        session.close()


def _check_youtube_health_through_proxy(proxy_url, metrics=None):
    return _youtube_healthcheck().check_youtube_through_proxy(
        _check_http_through_proxy,
        proxy_url,
        urls=YOUTUBE_VLESS2_HEALTHCHECK_URLS,
        min_ok=YOUTUBE_VLESS2_HEALTHCHECK_MIN_OK,
        http_timeouts=(POOL_PROBE_HTTP_CONNECT_TIMEOUT, POOL_PROBE_HTTP_READ_TIMEOUT),
        http_retry_timeouts=(POOL_PROBE_RETRY_CONNECT_TIMEOUT, POOL_PROBE_RETRY_READ_TIMEOUT),
        retry_delay_seconds=POOL_PROBE_RETRY_DELAY_SECONDS,
        metrics=metrics,
    )


def _recent_probe_ok(probe, field, ttl):
    if not isinstance(probe, dict) or probe.get(field) is not True:
        return False
    try:
        checked_at = float(probe.get('ts') or 0)
    except (TypeError, ValueError):
        checked_at = 0.0
    return bool(checked_at and time.time() - checked_at <= ttl)


def _active_status_can_use_recent_probe(probe, required_services=None):
    if not isinstance(probe, dict):
        return False
    try:
        checked_at = float(probe.get('ts') or 0)
    except (TypeError, ValueError):
        checked_at = 0.0
    if not checked_at or time.time() - checked_at > ACTIVE_STATUS_RECENT_SUCCESS_TTL:
        return False
    required = {str(item or '').strip().lower() for item in (required_services or ()) if str(item or '').strip()}
    if 'telegram' in required and probe.get('tg_ok') is not True:
        return False
    if 'youtube' in required and probe.get('yt_ok') is not True:
        return False
    if not required:
        return probe.get('tg_ok') is True or probe.get('yt_ok') is True
    return True


def _check_custom_target_through_proxy(proxy_url, url, connect_timeout=2, read_timeout=3):
    return _status_check_custom_target(
        _normalize_check_url,
        proxy_url,
        url,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
    )


def _probe_custom_targets_for_pool(proxy_url, custom_checks=None):
    return _status_probe_custom_targets(
        proxy_url,
        custom_checks if custom_checks is not None else _load_custom_checks(),
        _check_custom_target_through_proxy,
        connect_timeout=POOL_PROBE_CUSTOM_CONNECT_TIMEOUT,
        read_timeout=POOL_PROBE_CUSTOM_READ_TIMEOUT,
        retries=1,
        retry_connect_timeout=POOL_PROBE_RETRY_CONNECT_TIMEOUT,
        retry_read_timeout=POOL_PROBE_RETRY_READ_TIMEOUT,
        retry_delay_seconds=POOL_PROBE_RETRY_DELAY_SECONDS,
    )


def _check_telegram_api_through_proxy(proxy_url=None, connect_timeout=6, read_timeout=10, authenticated=None):
    authenticated_check = _app_mode_telegram_enabled() if authenticated is None else bool(authenticated)
    url = f'https://api.telegram.org/bot{token}/getMe' if authenticated_check else 'https://api.telegram.org/'
    proxies = {'https': proxy_url, 'http': proxy_url} if proxy_url else None
    requests = _requests_module()
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(url, timeout=(connect_timeout, read_timeout), proxies=proxies)
        if not authenticated_check:
            if response.status_code < 500:
                return True, 'Доступ к api.telegram.org подтверждён'
            response.raise_for_status()
        response.raise_for_status()
        data = response.json()
        if data.get('ok'):
            return True, 'Доступ к api.telegram.org подтверждён'
        return False, f'Telegram API ответил: {data.get("description", "Не удалось определить причину")}.'
    except requests.exceptions.ConnectTimeout:
        return False, 'Прокси не установил соединение с api.telegram.org за отведённое время.'
    except requests.exceptions.ReadTimeout:
        return False, 'Сервер Telegram не ответил вовремя через этот ключ.'
    except requests.exceptions.RequestException as exc:
        error_text = _redact_sensitive_text(exc)
        if 'Missing dependencies for SOCKS support' in error_text:
            return False, 'Отсутствует поддержка SOCKS (PySocks) для проверки Telegram API.'
        if 'SSLEOFError' in error_text or 'UNEXPECTED_EOF' in error_text:
            return False, 'Прокси-сервер разорвал TLS-соединение с api.telegram.org. Обычно это означает нерабочий ключ или проблему на удалённом сервере.'
        if 'Connection refused' in error_text:
            return False, 'Локальный SOCKS-порт отклонил соединение.'
        if 'RemoteDisconnected' in error_text:
            return False, 'Удалённая сторона закрыла соединение без ответа.'
        return False, f'Проверка Telegram API завершилась ошибкой: {error_text.splitlines()[0][:240]}'
    finally:
        session.close()


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


def _service_route_protocol(service_key, fallback=''):
    try:
        state = (_service_route_summary() or {}).get(service_key) or {}
    except Exception:
        return fallback
    complete = [
        str(proto or '').strip()
        for proto in (state.get('complete_protocols') or [])
        if str(proto or '').strip() in POOL_PROTOCOL_ORDER
    ]
    if not complete:
        return fallback
    if fallback in complete:
        return fallback
    return complete[0]


def _telegram_route_protocol():
    if not _app_mode_telegram_enabled():
        return ''
    fallback = proxy_mode if proxy_mode in POOL_PROTOCOL_ORDER else ''
    return _service_route_protocol('telegram', fallback=fallback)


def _telegram_required_for_protocol(key_name):
    return bool(key_name and key_name == _telegram_route_protocol())


def _core_proxy_runtime_name():
    if os.path.exists(XRAY_SERVICE_SCRIPT):
        return 'xray'
    return 'v2ray'


def _protocol_status_for_key(
    key_name,
    key_value,
    custom_checks=None,
    route_states=None,
    key_probe_cache=None,
    background_checks=False,
):
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

    custom_checks = custom_checks if custom_checks is not None else _load_custom_checks()
    if route_states is None:
        route_states = _service_route_summary()
    required_services = _key_pool_web().core_services_for_protocol(route_states, key_name)
    protocol_custom_checks = _key_pool_web().protocol_custom_checks(custom_checks, route_states, key_name)
    cache = key_probe_cache if key_probe_cache is not None else _load_key_probe_cache()
    cached_probe = cache.get(_hash_key(key_value), {})
    custom_states = _key_pool_web().web_custom_probe_states(cached_probe, protocol_custom_checks)
    active_telegram_required = bool(_app_mode_telegram_enabled() and _telegram_required_for_protocol(key_name))
    if (
        _active_status_can_use_recent_probe(cached_probe, required_services) and
        not (active_telegram_required and not bot_polling)
    ):
        return _status_cached_protocol_status(
            key_value,
            cached_probe,
            protocol_custom_checks,
            custom_states,
            api_required='telegram' in required_services,
            required_services=required_services,
        )

    proxy_url = proxy_settings.get(key_name)
    if background_checks:
        api_ok, api_message = _check_telegram_api_for_background(
            proxy_url,
            connect_timeout=5,
            read_timeout=8,
        )
    else:
        api_ok, api_message = _check_telegram_api_through_proxy(
            proxy_url,
            connect_timeout=5,
            read_timeout=8,
            authenticated=active_telegram_required,
        )
    api_unknown = api_ok is None
    if api_unknown:
        api_ok = bool(cached_probe.get('tg_ok')) if 'tg_ok' in cached_probe else False
        api_message = 'Фоновая проверка Telegram не вернула результат; сохранён последний подтверждённый статус.'
    if active_telegram_required and api_ok is False:
        _log_telegram_api_status_failure(key_name, api_message)
    api_transient = (not api_unknown) and (not api_ok) and _is_transient_telegram_api_failure(api_message)
    yt_metrics = {}
    if background_checks:
        yt_ok, yt_message = _check_youtube_protocol_for_background(key_name, metrics=yt_metrics)
    else:
        yt_ok, yt_message = _check_youtube_health_through_proxy(proxy_url, metrics=yt_metrics)
    yt_unknown = yt_ok is None
    cached_yt_state = _youtube_probe_state(cached_probe)
    if yt_unknown:
        yt_ok = cached_yt_state in ('ok', 'warn')
        yt_message = 'Фоновая проверка YouTube не вернула результат; сохранён последний подтверждённый статус.'
    if (
        api_transient and
        not active_telegram_required and
        _recent_probe_ok(cached_probe, 'tg_ok', TELEGRAM_TRANSIENT_OK_CACHE_TTL)
    ):
        api_ok = True
        api_transient = False
        api_message = f'Последняя успешная проверка Telegram сохранена; свежая проверка временно не ответила: {api_message}'
    probe_updates = {}
    if not api_unknown and not api_transient:
        probe_updates['tg_ok'] = api_ok
    if not yt_unknown:
        probe_updates['yt_ok'] = yt_ok
        probe_updates.update(yt_metrics)
    if probe_updates:
        _record_key_probe(key_name, key_value, **probe_updates)
    yt_state = 'pending' if yt_unknown else ('warn' if yt_ok and (
        str(yt_metrics.get('yt_stability') or '').lower() == 'unstable' or
        'unstable' in str(yt_message or '').lower()
    ) else ('ok' if yt_ok else 'fail'))
    return _status_active_protocol_status(
        endpoint_ok=endpoint_ok,
        endpoint_message=endpoint_message,
        api_ok=api_ok,
        api_message=api_message,
        api_transient=api_transient,
        api_pending=api_unknown,
        yt_ok=yt_ok,
        yt_message=yt_message,
        yt_pending=yt_unknown,
        yt_state=yt_state,
        custom_states=custom_states,
        custom_checks=protocol_custom_checks,
        api_required='telegram' in required_services,
        required_services=required_services,
    )


def _cached_protocol_status_for_key(
    key_name,
    key_value,
    custom_checks=None,
    key_probe_cache=None,
    allow_youtube_confirm=True,
    route_states=None,
):
    if not key_value.strip():
        return _status_empty_protocol_status()
    custom_checks = custom_checks if custom_checks is not None else _load_custom_checks()
    if route_states is None:
        route_states = _service_route_summary()
    required_services = _key_pool_web().core_services_for_protocol(route_states, key_name)
    protocol_custom_checks = _key_pool_web().protocol_custom_checks(custom_checks, route_states, key_name)
    cache = key_probe_cache if key_probe_cache is not None else _load_key_probe_cache()
    probe = cache.get(_hash_key(key_value), {})
    if (
        allow_youtube_confirm and
        key_name == _youtube_route_protocol() and
        _youtube_probe_state(probe) in ('fail', 'unknown')
    ):
        _schedule_youtube_cache_confirm(key_name, key_value)
    custom_states = _key_pool_web().web_custom_probe_states(probe, protocol_custom_checks)
    return _status_cached_protocol_status(
        key_value,
        probe,
        protocol_custom_checks,
        custom_states,
        api_required='telegram' in required_services,
        required_services=required_services,
    )


def _light_youtube_route_protocol():
    try:
        return _youtube_route_protocol()
    except Exception:
        return ''


def _light_required_services_for_protocol(key_name, *, youtube_proto=None):
    services = []
    if _app_mode_telegram_enabled() and key_name == proxy_mode:
        services.append('telegram')
    if youtube_proto is None:
        youtube_proto = _light_youtube_route_protocol()
    if key_name == youtube_proto:
        services.append('youtube')
    return tuple(services)


def _light_cached_protocol_status_for_key(key_name, key_value, key_probe_cache=None, *, youtube_proto=None):
    key_value = str(key_value or '').strip()
    if not key_value:
        return _status_empty_protocol_status()
    required_services = _light_required_services_for_protocol(key_name, youtube_proto=youtube_proto)
    api_required = 'telegram' in required_services
    probe = (key_probe_cache or {}).get(_hash_key(key_value), {})
    return _status_cached_protocol_status(
        key_value,
        probe if isinstance(probe, dict) else {},
        (),
        {},
        api_required=api_required,
        required_services=required_services,
    )


def _light_active_protocol_status_for_key(key_name, key_value, background_checks=False):
    key_value = str(key_value or '').strip()
    if not key_value:
        return _status_empty_protocol_status()
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
    api_required = bool(_app_mode_telegram_enabled() and key_name == proxy_mode)
    if api_required:
        if background_checks:
            api_ok, api_message = _check_telegram_api_for_background(
                proxy_url,
                connect_timeout=5,
                read_timeout=8,
            )
        else:
            api_ok, api_message = _check_telegram_api_through_proxy(
                proxy_url,
                connect_timeout=5,
                read_timeout=8,
                authenticated=True,
            )
        api_unknown = api_ok is None
        if api_unknown:
            api_ok = False
            api_message = 'Фоновая проверка Telegram не вернула результат; статус обновляется.'
        if api_ok is False:
            _log_telegram_api_status_failure(key_name, api_message)
    else:
        api_ok = False
        api_message = ''
        api_unknown = False
    api_transient = bool(
        api_required and not api_unknown and (not api_ok) and _is_transient_telegram_api_failure(api_message)
    )
    if api_required and not api_transient and not api_unknown:
        try:
            _record_light_telegram_probe(key_name, key_value, api_ok)
        except Exception as exc:
            _write_runtime_log(f'Ошибка обновления лёгкого кэша Telegram для {key_name}: {exc}')

    return _status_active_protocol_status(
        endpoint_ok=endpoint_ok,
        endpoint_message=endpoint_message,
        api_ok=api_ok,
        api_message=api_message,
        api_transient=api_transient,
        api_pending=api_unknown,
        yt_ok=False,
        yt_message='',
        yt_pending=False,
        yt_state='',
        custom_states={},
        custom_checks=(),
        api_required=api_required,
        required_services=('telegram',) if api_required else (),
    )


def _ordered_protocol_items(current_keys):
    current_keys = current_keys or {}
    ordered = []
    known = set()
    for proto in PROTOCOL_DISPLAY_ORDER:
        if proto in current_keys:
            ordered.append((proto, current_keys.get(proto, '')))
            known.add(proto)
    ordered.extend((proto, key_value) for proto, key_value in current_keys.items() if proto not in known)
    return ordered


def _placeholder_protocol_statuses(current_keys):
    return _status_placeholder_protocols(
        dict(_ordered_protocol_items(current_keys)),
        pending_details='Фоновая проверка ключа выполняется. Статус обновится без перезагрузки страницы',
    )


def _web_command_label(command):
    return web_commands_runtime.web_command_label(command)


def _web_command_state_defaults():
    return {
        'running': False,
        'command': '',
        'label': '',
        'result': '',
        'progress': 0,
        'progress_label': '',
        'target_version': '',
        'expected_seconds': 0,
        'expected_samples': 0,
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


def _attach_web_command_duration_estimate(state):
    state = dict(state or {})
    if state.get('command') not in WEB_UPDATE_COMMANDS:
        state['expected_seconds'] = 0
        state['expected_samples'] = 0
        return state
    expected_seconds, expected_samples = event_history.estimate_update_duration(command=state.get('command') or 'update')
    state['expected_seconds'] = expected_seconds
    state['expected_samples'] = expected_samples
    return state


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
    start_delay = 1.0 if command == 'rollback_update' else 0.0
    return (
        'import os, sys, time; '
        'os.environ["BYPASS_KEENETIC_COMMAND_WORKER"] = "1"; '
        f'time.sleep({start_delay!r}); '
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
    state = _attach_web_command_duration_estimate(state)
    if state.get('running') and state.get('command') in WEB_UPDATE_COMMANDS:
        update_state = update_status.read_update_status()
        if update_state.get('running') and update_state.get('command') == state.get('command'):
            state['target_version'] = update_state.get('target_version', '')
    with web_command_lock:
        web_command_state.update(state)
    return _command_state_snapshot(web_command_lock, web_command_state)


def _consume_web_command_state_for_render():
    _get_web_command_state()
    consumed = _consume_command_state_for_render_impl(
        web_command_lock,
        web_command_state,
        clear_finished_commands=WEB_UPDATE_COMMANDS,
    )
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
    if command in WEB_UPDATE_COMMANDS:
        snapshot = _command_state_snapshot(web_command_lock, web_command_state)
        update_status.write_update_status(
            command=command,
            running=True,
            progress=snapshot.get('progress', 0),
            progress_label=snapshot.get('progress_label', ''),
            message=result_text,
        )


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
    if command in WEB_UPDATE_COMMANDS:
        snapshot = _command_state_snapshot(web_command_lock, web_command_state)
        update_status.finish_update_status(command, result, progress=snapshot.get('progress', 100))
        _record_event(
            'web_command_finish',
            result,
            level='info',
            source='web',
            protocol='system',
            service=command,
        )
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
    _record_memory_timeline(
        f'web command started: {command}',
        marker='web_command_start',
        extra={'command': str(command or '')},
        force=True,
    )
    try:
        _execute_web_command(command)
    finally:
        _memory_cleanup('web command finished', force=True, clear_status=True)
        _record_memory_timeline(
            f'web command finished: {command}',
            marker='web_command_finish',
            extra={'command': str(command or '')},
            force=True,
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
    if command in WEB_UPDATE_COMMANDS:
        update_status.write_update_status(
            command=command,
            running=True,
            progress=state.get('progress', 0),
            progress_label=state.get('progress_label', ''),
            message='Команда запущена',
        )
        _record_event('web_command_start', label, source='web', protocol='system', service=command)
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
    return True, f'⏳ Команда "{label}" запущена. Статус обновится без перезагрузки страницы'


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
            for line in reversed(_read_tail(log_path, lines=80).splitlines()):
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
    key_hash = hashlib.sha256((key_value or '').encode('utf-8')).hexdigest()[:12]
    if key_type == 'shadowsocks':
        server, port, method, password = _decode_shadowsocks_uri(key_value)
        return ('Параметры Shadowsocks: server={server}, port={port}, method={method}, '
                'password_len={password_len}, key_hash=sha256:{key_hash}').format(
                    server=server,
                    port=port,
                    method=method,
                    password_len=len(password),
                    key_hash=key_hash)
    if key_type in ['vless', 'vless2']:
        data = _parse_vless_key(key_value)
        return ('Параметры VLESS: address={address}, host={host}, port={port}, network={type}, '
                'serviceName={serviceName}, sni={sni}, security={security}, flow={flow}, '
                'key_hash=sha256:{key_hash}').format(key_hash=key_hash, **data)
    if key_type == 'vmess':
        data = _parse_vmess_key(key_value)
        service_name = data.get('serviceName') or data.get('grpcSettings', {}).get('serviceName', '')
        return ('Параметры VMESS: host={add}, port={port}, network={net}, tls={tls}, '
                'serviceName={service_name}, key_hash=sha256:{key_hash}').format(
                    service_name=service_name,
                    key_hash=key_hash,
                    **data)
    if key_type == 'trojan':
        data = _parse_trojan_key(key_value)
        return ('Параметры Trojan: address={address}, port={port}, sni={sni}, security={security}, '
                'network={type}, password_len={password_len}, key_hash=sha256:{key_hash}').format(
                    address=data['address'],
                    port=data['port'],
                    sni=data['sni'],
                    security=data['security'],
                    type=data['type'],
                    password_len=len(data['password']),
                    key_hash=key_hash)
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


POOL_PROTOCOL_ORDER = list(PROTOCOL_DISPLAY_ORDER)
# Telegram прокручивает reply-клавиатуру целиком, без закрепления нижних строк.
# Поэтому показываем весь пул в одной прокручиваемой клавиатуре, а служебные
# кнопки добавляем после списка ключей.
POOL_PAGE_SIZE = 1000


def _pool_proto_label(proto):
    return _key_pool_web().pool_proto_label(proto)


def _pool_proto_from_button_prefix(prefix):
    return _telegram_pool_ui().pool_proto_from_button_prefix(prefix)
def _pool_protocol_markup():
    return _telegram_pool_ui().pool_protocol_markup(types, [_pool_proto_label(proto) for proto in POOL_PROTOCOL_ORDER])
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
    for proto, label in _key_pool_web().POOL_PROTOCOL_LABELS.items():
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
    return _telegram_pool_ui().pool_action_markup(types, labels, info)
def _pool_delete_markup(proto, page=0):
    _, info = _format_pool_page(proto, page)
    current_keys = _load_current_keys()
    current_key = current_keys.get(proto)
    cache = _load_key_probe_cache()
    labels = []
    for offset, key_value in enumerate(info['keys'][info['start']:info['end']], start=info['start'] + 1):
        probe = cache.get(_hash_key(key_value), {})
        labels.append(_pool_key_button_label(offset, key_value, probe=probe, current_key=current_key, proto=proto, action='delete'))
    return _telegram_pool_ui().pool_delete_markup(types, labels, info)
def _pool_clear_confirm_markup():
    return _telegram_pool_ui().pool_clear_confirm_markup(types)
def _pool_input_markup():
    return _telegram_pool_ui().pool_input_markup(types)
def _pool_key_button_label(index, key_value, probe=None, current_key=None, proto=None, action='apply'):
    return _telegram_pool_ui().pool_key_button_label(
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
    lines = ['📦 Пул ключей', 'Выберите протокол для управления пулом', '']
    for proto in POOL_PROTOCOL_ORDER:
        keys = pools.get(proto, []) or []
        current_key = current_keys.get(proto)
        active = 'активный есть' if current_key else 'активный не задан'
        lines.append(f'{_pool_proto_label(proto)}: {len(keys)} ключей, {active}')
    return '\n'.join(lines)


def _pool_summary_count(summary, field):
    try:
        return int((summary or {}).get(field) or 0)
    except Exception:
        return 0


def _load_persisted_pool_summary():
    payload = _read_json_file(_POOL_SUMMARY_LAST_PATH, {}) or {}
    summary = payload.get('summary') if isinstance(payload, dict) else None
    return summary if isinstance(summary, dict) else None


def _save_persisted_pool_summary(summary):
    if (
        _pool_summary_count(summary, 'checked_pool_count') <= 0 or
        _pool_summary_count(summary, 'pool_total_count') <= 0
    ):
        return
    payload = {
        'saved_at': time.time(),
        'summary': summary,
    }
    try:
        _write_json_file(_POOL_SUMMARY_LAST_PATH, payload)
    except Exception as exc:
        _write_runtime_log(f'Failed to persist pool summary: {type(exc).__name__}')


def _pool_summary_with_persisted_fallback(summary):
    if _pool_summary_count(summary, 'checked_pool_count') > 0:
        _save_persisted_pool_summary(summary)
        return summary
    persisted = _load_persisted_pool_summary()
    if (
        _pool_summary_count(persisted, 'checked_pool_count') > 0 and
        _pool_summary_count(persisted, 'pool_total_count') == _pool_summary_count(summary, 'pool_total_count')
    ):
        return persisted
    return summary


def _light_pool_summary_with_cache_fallback(current_keys, key_pools, custom_checks=None):
    empty_summary = _light_pool_status_summary(current_keys, key_pools, {}, custom_checks)
    persisted = _load_persisted_pool_summary()
    if (
        _pool_summary_count(persisted, 'checked_pool_count') > 0 and
        _pool_summary_count(persisted, 'pool_total_count') == _pool_summary_count(empty_summary, 'pool_total_count')
    ):
        return persisted
    light_cache = _load_light_key_probe_cache()
    if not light_cache:
        return empty_summary
    return _pool_summary_with_persisted_fallback(
        _light_pool_status_summary(current_keys, key_pools, light_cache, custom_checks)
    )


def _light_pool_status_summary(current_keys, key_pools, key_probe_cache, custom_checks=None):
    current_keys = current_keys or {}
    key_pools = key_pools or {}
    key_probe_cache = key_probe_cache or {}
    services = [
        {'label': 'Telegram', 'field': 'tg_ok', 'id': None, 'count': 0},
        {'label': 'YouTube', 'field': 'yt_ok', 'id': None, 'count': 0},
    ]
    for check in custom_checks or []:
        if not isinstance(check, dict):
            continue
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
            custom = probe.get('custom', {})
            if not isinstance(custom, dict):
                custom = {}
            results = []
            for service in services:
                if service['field'] == 'yt_ok':
                    state = _youtube_probe_state(probe)
                    if state == 'unknown':
                        continue
                    ok = state in ('ok', 'warn')
                elif service['field']:
                    if service['field'] not in probe or not isinstance(probe.get(service['field']), bool):
                        continue
                    ok = probe.get(service['field'])
                else:
                    if service['id'] not in custom or not isinstance(custom.get(service['id']), bool):
                        continue
                    ok = custom.get(service['id'])
                results.append(ok)
                if ok:
                    service['count'] += 1
            if results:
                checked_count += 1
                if any(results):
                    any_service_count += 1
                if all(results):
                    all_services_count += 1

    active_key_count = sum(1 for proto in POOL_PROTOCOL_ORDER if (current_keys.get(proto) or '').strip())
    service_text = '; '.join(f"{service['label']}: {service['count']}" for service in services)
    note_parts = [f'В пулах: {total_count}', f'Проверено: {checked_count}']
    if service_text:
        note_parts.append(service_text)
    return {
        'active_key_count': active_key_count,
        'protocol_count': len(POOL_PROTOCOL_ORDER),
        'active_text': f'{active_key_count} / {len(POOL_PROTOCOL_ORDER)} активных ключей',
        'note': '; '.join(note_parts),
        'pool_total_count': total_count,
        'checked_pool_count': checked_count,
        'all_services_count': all_services_count,
        'any_service_count': any_service_count,
        'services': [{'label': service['label'], 'count': service['count']} for service in services],
    }


def _pool_summary_can_keep_previous(previous_signature, current_signature):
    if not previous_signature or not current_signature:
        return False
    try:
        return (
            previous_signature[0] == current_signature[0] and
            previous_signature[1] == current_signature[1]
        )
    except Exception:
        return False


def _pool_status_summary(current_keys=None, key_pools=None, key_probe_cache=None, custom_checks=None, route_states=None):
    current_keys = current_keys if current_keys is not None else _load_current_keys()
    resolved_route_states = route_states if route_states is not None else _service_route_summary()
    can_use_cache = key_pools is None and key_probe_cache is None and custom_checks is None
    signature = _pool_summary_cache_signature(current_keys, resolved_route_states) if can_use_cache else None
    previous_signature = None
    previous_summary = None
    if can_use_cache:
        with pool_summary_cache_lock:
            previous_signature = pool_summary_cache.get('signature')
            previous_summary = pool_summary_cache.get('summary')
            if pool_summary_cache.get('signature') == signature and pool_summary_cache.get('summary') is not None:
                return pool_summary_cache['summary']
    resolved_key_pools = key_pools if key_pools is not None else _ensure_current_keys_in_pools(current_keys)
    resolved_key_probe_cache = key_probe_cache if key_probe_cache is not None else _load_key_probe_cache()
    resolved_custom_checks = custom_checks if custom_checks is not None else _load_custom_checks()
    summary = _key_pool_web().pool_status_summary(
        current_keys,
        resolved_key_pools,
        resolved_key_probe_cache,
        resolved_custom_checks,
        _hash_key,
        route_states=resolved_route_states,
    )
    if (
        can_use_cache and
        _pool_summary_count(summary, 'checked_pool_count') == 0 and
        _pool_summary_count(previous_summary, 'checked_pool_count') > 0 and
        _pool_summary_count(summary, 'pool_total_count') == _pool_summary_count(previous_summary, 'pool_total_count') and
        _pool_summary_can_keep_previous(previous_signature, signature)
    ):
        summary = previous_summary
    summary = _pool_summary_with_persisted_fallback(summary)
    if can_use_cache:
        with pool_summary_cache_lock:
            pool_summary_cache['signature'] = signature
            pool_summary_cache['summary'] = summary
    return summary
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
        bot.send_message(message.chat.id, 'Выберите протокол кнопкой внизу', reply_markup=_pool_protocol_markup())
        return True
    set_menu_state(21, proto)
    _send_pool_page(message.chat.id, proto, page=0)
    return True


def _send_pool_input_prompt(chat_id, proto, prompt):
    bot.send_message(chat_id, prompt.format(proto_label=_pool_proto_label(proto)), reply_markup=_pool_input_markup())


def _pool_probe_start_result(proto, *, mention_proto=True):
    started, queued = _probe_pool_keys_background(proto, _pool_keys_for_proto(proto), stale_only=False, resume_pending=True)
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


def _apply_pool_key(proto, key_value, schedule_probe=True):
    result = _install_key_for_protocol(proto, key_value, verify=False)
    _set_active_key(proto, key_value)
    _audit_key_switch('telegram_pool_apply', proto, key_value, 'manual pool apply')
    _schedule_youtube_key_apply_prefetch(proto)
    refreshed_status = _probe_applied_pool_key_services(proto, key_value) if schedule_probe else (
        'Статусы выбранного ключа обновит продолжающаяся проверка пула.'
    )
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    if refreshed_status:
        result = f'{result}\n{refreshed_status}'
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
        should_resume_probe = False
        try:
            should_resume_probe, pause_note = _pause_pool_probe_for_apply()
            result = _apply_pool_key(proto, key_value, schedule_probe=not should_resume_probe)
            display_name = _pool_key_display_name(key_value)
            prefix = f'✅ Ключ #{index} «{display_name}» применён для {_pool_proto_label(proto)}.\n{result}'
            if pause_note:
                prefix = f'{pause_note}\n{prefix}'
        except Exception as exc:
            prefix = f'Ошибка применения ключа #{index} из пула {_pool_proto_label(proto)}: {exc}'
        finally:
            pool_apply_lock.release()
            if should_resume_probe:
                _resume_cancelled_pool_probe()
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


def _forget_unreferenced_key_probes(key_values, pools=None):
    candidates = []
    seen = set()
    for key_value in key_values or []:
        value = str(key_value or '').strip()
        if value and value not in seen:
            candidates.append(value)
            seen.add(value)
    if not candidates:
        return 0
    referenced = set()
    try:
        current_pools = pools if isinstance(pools, dict) else _key_pool_store().load_key_pools(KEY_POOLS_PATH)
        for values in (current_pools or {}).values():
            for value in values or []:
                value = str(value or '').strip()
                if value:
                    referenced.add(value)
    except Exception:
        referenced.update(candidates)
    try:
        for value in (_load_current_keys() or {}).values():
            value = str(value or '').strip()
            if value:
                referenced.add(value)
    except Exception:
        referenced.update(candidates)
    return _forget_key_probes([value for value in candidates if value not in referenced])


def _delete_pool_key(proto, key_value):
    final_pools = None
    with key_pool_lock:
        pools, removed = _key_pool_store().delete_pool_key(_key_pool_store().load_key_pools(KEY_POOLS_PATH), proto, key_value)
        if not removed:
            raise ValueError('\u041a\u043b\u044e\u0447 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0432 \u043f\u0443\u043b\u0435.')
        current_key = (_load_current_keys().get(proto) or '').strip()
        was_current = bool(current_key and current_key == key_value)
        keys = _dedupe_key_list(pools.get(proto, []) or [])
        promoted_key = keys[0] if was_current and keys else ''
        should_clear_current = was_current and not promoted_key
        if not was_current:
            _key_pool_store().save_key_pools(KEY_POOLS_PATH, pools)
            final_pools = pools
            should_clear_current = False
    if promoted_key:
        _install_key_for_protocol(proto, promoted_key, verify=False)
        _audit_key_switch('pool_delete_promote', proto, promoted_key, 'active key deleted')
    elif should_clear_current:
        _clear_installed_key_for_protocol(proto)
    if was_current:
        with key_pool_lock:
            latest_pools, _ = _key_pool_store().delete_pool_key(
                _key_pool_store().load_key_pools(KEY_POOLS_PATH),
                proto,
                key_value,
            )
            if promoted_key:
                latest_pools = _key_pool_store().set_active_key(latest_pools, proto, promoted_key)
            _key_pool_store().save_key_pools(KEY_POOLS_PATH, latest_pools)
            final_pools = latest_pools
    _forget_unreferenced_key_probes([key_value], final_pools)
    if was_current:
        _invalidate_web_status_cache()
        _invalidate_key_status_cache()
    else:
        _invalidate_pool_data_cache()


def _clear_pool(proto):
    current_removed = False
    with key_pool_lock:
        pools, removed_keys = _key_pool_store().clear_pool(_key_pool_store().load_key_pools(KEY_POOLS_PATH), proto)
        _key_pool_store().save_key_pools(KEY_POOLS_PATH, pools)
        current_key = (_load_current_keys().get(proto) or '').strip()
        if current_key and current_key in removed_keys:
            current_removed = True
            _clear_installed_key_for_protocol(proto)
    if removed_keys:
        _forget_unreferenced_key_probes(removed_keys, pools)
    if current_removed:
        _invalidate_web_status_cache()
        _invalidate_key_status_cache()
    else:
        _invalidate_pool_data_cache()
    return len(removed_keys)


def _proxy_config_snapshot_paths():
    return _store_proxy_config_snapshot_paths(CORE_PROXY_CONFIG_PATH, VMESS_KEY_PATH, VLESS_KEY_PATH, VLESS2_KEY_PATH)


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
    scope = (progress or _get_pool_probe_progress()).get('scope')
    if scope == 'manual_all':
        return '\u041f\u043e\u043b\u043d\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0432\u0441\u0435\u0445 \u043a\u043b\u044e\u0447\u0435\u0439'
    if scope == 'protocol':
        return '\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u0433\u043e \u043f\u0443\u043b\u0430'
    return '\u0424\u043e\u043d\u043e\u0432\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u043f\u0443\u043b\u0430 \u043a\u043b\u044e\u0447\u0435\u0439'


def _pool_probe_timeout_budget(custom_checks=None, task_count=1, workers=1):
    return _pool_probe_controller().pool_probe_timeout_budget(
        custom_checks,
        task_count,
        workers,
        POOL_PROBE_TIMEOUTS,
        youtube_profile=POOL_PROBE_YOUTUBE_PROFILE,
    )


def _check_pool_key_through_proxy(proto, key_value, custom_checks=None, proxy_url=None, record_key_probe=None):
    return _pool_probe_controller().check_pool_key_through_proxy(
        proto,
        key_value,
        custom_checks,
        proxy_url or proxy_settings.get(proto),
        check_telegram_api=_check_telegram_api_through_proxy,
        check_http=_check_http_through_proxy,
        record_key_probe=record_key_probe or _record_key_probe,
        probe_custom_targets=_probe_custom_targets_for_pool,
        retry_delay_seconds=POOL_PROBE_RETRY_DELAY_SECONDS,
        telegram_timeouts=(POOL_PROBE_TG_CONNECT_TIMEOUT, POOL_PROBE_TG_READ_TIMEOUT),
        http_timeouts=(POOL_PROBE_HTTP_CONNECT_TIMEOUT, POOL_PROBE_HTTP_READ_TIMEOUT),
        http_retry_timeouts=(POOL_PROBE_RETRY_CONNECT_TIMEOUT, POOL_PROBE_RETRY_READ_TIMEOUT),
        telegram_required=_telegram_required_for_protocol(proto),
        youtube_profile=POOL_PROBE_YOUTUBE_PROFILE,
        measure_download=_measure_limited_pool_probe_quality_download if POOL_PROBE_QUALITY_ENABLED else None,
        quality_settings=_pool_probe_quality_settings(),
    )


def _schedule_applied_pool_key_probe(proto, key_value):
    if not key_value:
        return ''
    if pool_probe_lock.locked():
        return 'Статусы выбранного ключа обновятся после текущей проверки пула.'
    try:
        started, queued = _probe_pool_keys_background(
            proto,
            [key_value],
            max_keys=1,
            stale_only=False,
            scope='applied',
        )
        if started:
            _invalidate_web_status_cache()
            _invalidate_key_status_cache()
            return 'Статусы выбранного ключа обновляются фоновой проверкой.'
        if queued:
            return 'Фоновая проверка выбранного ключа уже выполняется.'
        return 'Ключ применён; проверка сервисов не запускалась.'
    except Exception as exc:
        _write_runtime_log(f'Applied pool key background probe failed for {proto}: {exc}')
        return f'⚠️ Ключ применён, но фоновую проверку сервисов не удалось запустить: {exc}'


def _probe_applied_pool_key_services(proto, key_value):
    return _schedule_applied_pool_key_probe(proto, key_value)


def _proxy_outbound_from_key(proto, key_value, tag, email='t@t.tt'):
    return _store_proxy_outbound_from_key(proto, key_value, tag, email=email)


def _find_pool_failover_candidate_inline(candidates, service='telegram'):
    """Find one working pool key through a temporary xray before touching the active proxy."""
    http_timeouts = (
        (YOUTUBE_VLESS2_FAILOVER_CHECK_CONNECT_TIMEOUT, YOUTUBE_VLESS2_FAILOVER_CHECK_READ_TIMEOUT)
        if service == 'youtube'
        else (POOL_PROBE_HTTP_CONNECT_TIMEOUT, POOL_PROBE_HTTP_READ_TIMEOUT)
    )
    return _pool_probe_runner().find_pool_failover_candidate(
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
        http_timeouts=http_timeouts,
    )


def _cleanup_failover_candidate_process_files(paths=None):
    for path in (paths or {}).values():
        _remove_file(path)


def _cleanup_health_check_process_files(paths=None):
    for path in (paths or {}).values():
        _remove_file(path)


def _failover_candidate_process_worker_code(input_path, result_path):
    module_dir = os.path.dirname(BOT_SOURCE_PATH)
    return (
        'import os, sys; '
        'os.environ["BYPASS_KEENETIC_COMMAND_WORKER"] = "1"; '
        'os.environ["BYPASS_KEENETIC_POOL_PROBE_WORKER"] = "1"; '
        f"sys.path.insert(0, {module_dir!r}); "
        'import failover_candidate_runner as runner; '
        'sys.exit(runner.run_failover_candidate_worker('
        f'{input_path!r}, {result_path!r}))'
    )


def _health_check_process_worker_code(input_path, result_path):
    module_dir = os.path.dirname(BOT_SOURCE_PATH)
    return (
        'import os, sys; '
        'os.environ["BYPASS_KEENETIC_COMMAND_WORKER"] = "1"; '
        'os.environ["BYPASS_KEENETIC_HEALTH_WORKER"] = "1"; '
        f"sys.path.insert(0, {module_dir!r}); "
        'import health_check_runner as runner; '
        'sys.exit(runner.run_health_check_worker('
        f'{input_path!r}, {result_path!r}))'
    )


def _run_health_check_process_worker(input_path, result_path):
    import health_check_runner

    return health_check_runner.run_health_check_worker(input_path, result_path)


def _health_check_in_process(payload):
    payload = dict(payload or {})
    kind = str(payload.get('kind') or '').strip().lower()
    if kind == 'telegram':
        payload.setdefault('authenticated', bool(_app_mode_telegram_enabled()))
    elif kind == 'youtube':
        proto = str(payload.get('proto') or '').strip() or _youtube_route_protocol()
        payload.update({
            'proto': proto,
            'proxy_url': proxy_settings.get(proto) or '',
            'urls': list(YOUTUBE_VLESS2_HEALTHCHECK_URLS),
            'min_ok': YOUTUBE_VLESS2_HEALTHCHECK_MIN_OK,
            'connect_timeout': YOUTUBE_VLESS2_FAILOVER_CHECK_CONNECT_TIMEOUT,
            'read_timeout': YOUTUBE_VLESS2_FAILOVER_CHECK_READ_TIMEOUT,
            'retry_delay_seconds': POOL_PROBE_RETRY_DELAY_SECONDS,
        })
    paths = _health_check_process_paths()
    try:
        _write_json_file_private(paths['input_path'], payload)
        env = dict(os.environ)
        env['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
        env['BYPASS_KEENETIC_HEALTH_WORKER'] = '1'
        result = subprocess.run(
            [sys.executable, '-c', _health_check_process_worker_code(
                paths['input_path'],
                paths['result_path'],
            )],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            env=env,
            timeout=POOL_FAILOVER_PROCESS_WORKER_TIMEOUT_SECONDS,
            check=False,
        )
        worker_payload = _read_json_file(paths['result_path'], {}) or {}
        if not isinstance(worker_payload, dict):
            worker_payload = {}
        if result.returncode != 0:
            error = str(worker_payload.get('error') or '').strip()
            if error:
                _write_runtime_log(f'Health check worker failed: {error}')
            else:
                _write_runtime_log(f'Health check worker returned code {result.returncode}.')
            return None
        return worker_payload
    except subprocess.TimeoutExpired:
        _write_runtime_log('Health check worker timed out.')
        return None
    except Exception as exc:
        _write_runtime_log(f'Health check worker could not start: {_redact_sensitive_text(exc)}')
        return None
    finally:
        _cleanup_health_check_process_files(paths)


def _check_telegram_api_for_background(proxy_url=None, connect_timeout=6, read_timeout=10):
    if POOL_FAILOVER_PROCESS_WORKER_ENABLED and not HEALTH_CHECK_WORKER_MODE:
        payload = _health_check_in_process({
            'kind': 'telegram',
            'proxy_url': str(proxy_url or ''),
            'connect_timeout': float(connect_timeout or 0),
            'read_timeout': float(read_timeout or 0),
        })
        if payload is None:
            return None, 'Telegram API check is unavailable; the last verified result is kept.'
        return bool(payload.get('ok')), str(payload.get('message') or '')
    return _check_telegram_api_through_proxy(
        proxy_url,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
    )


def _check_youtube_protocol_for_background(proto=None, metrics=None):
    if POOL_FAILOVER_PROCESS_WORKER_ENABLED and not HEALTH_CHECK_WORKER_MODE:
        payload = _health_check_in_process({
            'kind': 'youtube',
            'proto': str(proto or ''),
        })
        if payload is None:
            return None, 'YouTube check is unavailable; the last verified result is kept.'
        worker_metrics = payload.get('metrics') or {}
        if isinstance(metrics, dict) and isinstance(worker_metrics, dict):
            metrics.update(worker_metrics)
        return bool(payload.get('ok')), str(payload.get('message') or '')
    return _check_youtube_protocol_once(proto, metrics=metrics)


def _run_failover_candidate_process_worker(input_path, result_path):
    import failover_candidate_runner

    return failover_candidate_runner.run_failover_candidate_worker(input_path, result_path)


def _find_pool_failover_candidate_in_process(candidates, service='telegram'):
    candidates = [
        (str(proto or ''), str(key_value or '').strip())
        for proto, key_value in (candidates or [])
        if str(proto or '') in POOL_PROTOCOL_ORDER and str(key_value or '').strip()
    ]
    if not candidates:
        return None
    paths = _failover_candidate_process_paths()
    payload = {
        'service': str(service or 'telegram'),
        'candidates': candidates,
        'batch_size': POOL_PROBE_BATCH_SIZE,
        'test_port': POOL_FAILOVER_TEST_PORT,
        'telegram_timeouts': [POOL_PROBE_TG_CONNECT_TIMEOUT, POOL_PROBE_TG_READ_TIMEOUT],
        'http_timeouts': [
            YOUTUBE_VLESS2_FAILOVER_CHECK_CONNECT_TIMEOUT if service == 'youtube' else POOL_PROBE_HTTP_CONNECT_TIMEOUT,
            YOUTUBE_VLESS2_FAILOVER_CHECK_READ_TIMEOUT if service == 'youtube' else POOL_PROBE_HTTP_READ_TIMEOUT,
        ],
        'telegram_authenticated': bool(_app_mode_telegram_enabled()),
    }
    worker_timed_out = False
    try:
        _write_json_file_private(paths['input_path'], payload)
        env = dict(os.environ)
        env['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
        env['BYPASS_KEENETIC_POOL_PROBE_WORKER'] = '1'
        result = subprocess.run(
            [sys.executable, '-c', _failover_candidate_process_worker_code(
                paths['input_path'],
                paths['result_path'],
            )],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            env=env,
            timeout=POOL_FAILOVER_PROCESS_WORKER_TIMEOUT_SECONDS,
            check=False,
        )
        worker_payload = _read_json_file(paths['result_path'], {}) or {}
        if not isinstance(worker_payload, dict):
            worker_payload = {}
        if result.returncode not in (0, 2):
            error = str(worker_payload.get('error') or '').strip()
            if error:
                _write_runtime_log(f'Auto-failover: worker failed while checking candidates: {error}')
            else:
                _write_runtime_log(f'Auto-failover: worker returned code {result.returncode} while checking candidates.')
            return None
        candidate = worker_payload.get('candidate')
        if not worker_payload.get('ok') or not isinstance(candidate, list) or len(candidate) < 4:
            return None
        proto, key_value, tg_ok, yt_ok = candidate[:4]
        proto = str(proto or '')
        key_value = str(key_value or '').strip()
        if proto not in POOL_PROTOCOL_ORDER or not key_value:
            return None
        return proto, key_value, tg_ok, yt_ok
    except subprocess.TimeoutExpired:
        worker_timed_out = True
        _write_runtime_log('Auto-failover: worker timed out while checking candidates.')
        return None
    except Exception as exc:
        _write_runtime_log(f'Auto-failover: worker could not start candidate check: {exc}')
        return None
    finally:
        _cleanup_failover_candidate_process_files(paths)
        try:
            candidates.clear()
            payload['candidates'] = []
        except Exception:
            pass
        if worker_timed_out:
            # A normal child owns and reaps its temporary Xray.  Scan only
            # after a timeout, when the interpreter could not reach cleanup.
            _cleanup_pool_probe_runtime_light(kill_processes=True)


def _find_pool_failover_candidate(candidates, service='telegram'):
    if POOL_FAILOVER_PROCESS_WORKER_ENABLED and not POOL_PROBE_WORKER_MODE:
        return _find_pool_failover_candidate_in_process(candidates, service=service)
    return _find_pool_failover_candidate_inline(candidates, service=service)


def _select_pool_probe_tasks(tasks, max_keys=None, stale_only=False):
    custom_checks = _load_custom_checks()
    return _pool_probe_controller().select_pool_probe_tasks(
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
    _invalidate_pool_data_cache()


def _delete_pool_probe_resume_file():
    try:
        os.remove(POOL_PROBE_RESUME_FILE)
    except FileNotFoundError:
        pass
    except Exception as exc:
        _write_runtime_log(f'Failed to remove pool probe resume file: {exc}')


def _pool_probe_resume_task_id(proto, key_or_id):
    proto = str(proto or '').strip()
    key_or_id = str(key_or_id or '').strip()
    if proto not in POOL_PROTOCOL_ORDER or not key_or_id:
        return None
    if len(key_or_id) == 40 and all(char in '0123456789abcdefABCDEF' for char in key_or_id):
        return proto, key_or_id.lower()
    return proto, _hash_key(key_or_id)


def _normalize_pool_probe_resume_payload(payload):
    if not isinstance(payload, dict):
        return None
    tasks = []
    for item in payload.get('tasks') or []:
        if isinstance(item, dict):
            task_id = _pool_probe_resume_task_id(
                item.get('proto') or item.get('protocol'),
                item.get('key_id') or item.get('hash') or item.get('key'),
            )
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            task_id = _pool_probe_resume_task_id(item[0], item[1])
        else:
            continue
        if not task_id:
            continue
        tasks.append(task_id)
    if not tasks:
        return None

    checks = []
    for check in payload.get('checks') or []:
        if isinstance(check, dict):
            checks.append(dict(check))
    try:
        checked = int(payload.get('checked') or 0)
    except Exception:
        checked = 0
    try:
        total = int(payload.get('total') or 0)
    except Exception:
        total = 0
    checked = max(0, checked)
    total = max(total, checked + len(tasks), len(tasks))
    checked = min(checked, total)
    try:
        started_at = float(payload.get('started_at') or 0)
    except Exception:
        started_at = 0.0
    if started_at <= 0:
        started_at = time.time()
    return {
        'tasks': tasks,
        'checks': checks,
        'scope': str(payload.get('scope') or 'manual'),
        'checked': checked,
        'total': total,
        'started_at': started_at,
    }


def _resolve_pool_probe_resume_tasks(payload):
    payload = _normalize_pool_probe_resume_payload(payload)
    if not payload:
        return None
    pools = _ensure_current_keys_in_pools(_load_current_keys())
    lookup = {}
    for proto in POOL_PROTOCOL_ORDER:
        for key_value in pools.get(proto, []) or []:
            key_value = str(key_value or '').strip()
            if key_value:
                lookup[(proto, _hash_key(key_value))] = key_value
    resolved = []
    for proto, key_id in payload.get('tasks') or []:
        key_value = lookup.get((proto, key_id))
        if key_value:
            resolved.append((proto, key_value))
    if not resolved:
        return None
    resolved_payload = dict(payload)
    resolved_payload['tasks'] = resolved
    resolved_payload['total'] = max(
        int(resolved_payload.get('total') or 0),
        int(resolved_payload.get('checked') or 0) + len(resolved),
    )
    return resolved_payload


def _persist_pool_probe_resume_payload(payload):
    normalized = _normalize_pool_probe_resume_payload(payload)
    if not normalized:
        _delete_pool_probe_resume_file()
        return None
    serializable = dict(normalized)
    serializable['task_ref'] = 'key_hash'
    serializable['tasks'] = [
        {'proto': proto, 'key_id': key_id}
        for proto, key_id in normalized['tasks']
    ]
    try:
        _write_json_file(POOL_PROBE_RESUME_FILE, serializable)
        try:
            os.chmod(POOL_PROBE_RESUME_FILE, 0o600)
        except Exception:
            pass
    except Exception as exc:
        _write_runtime_log(f'Failed to persist pool probe resume queue: {exc}')
    return normalized


def _store_cancelled_pool_probe(probe_tasks, checks, scope):
    global pool_probe_resume_payload
    remaining = list(probe_tasks or [])
    if not remaining:
        return
    if not pool_probe_resume_after_cancel:
        return
    progress = _get_pool_probe_progress()
    try:
        original_total = int(progress.get('total') or 0)
    except Exception:
        original_total = 0
    if original_total <= 0:
        original_total = len(remaining)
    try:
        checked = int(progress.get('checked') or 0)
    except Exception:
        checked = 0
    checked = max(checked, original_total - len(remaining))
    payload = _persist_pool_probe_resume_payload({
        'tasks': remaining,
        'checks': list(checks or []),
        'scope': scope or 'manual',
        'checked': max(0, min(checked, original_total)),
        'total': original_total,
        'started_at': float(progress.get('started_at') or 0) or time.time(),
    })
    if not payload:
        return
    with pool_probe_resume_lock:
        pool_probe_resume_payload = payload
    if not pool_probe_cancel_event.is_set():
        _schedule_low_memory_pool_probe_resume()


def _take_cancelled_pool_probe():
    global pool_probe_resume_payload
    with pool_probe_resume_lock:
        payload = pool_probe_resume_payload
        pool_probe_resume_payload = None
    if not payload:
        payload = _normalize_pool_probe_resume_payload(_read_json_file(POOL_PROBE_RESUME_FILE, {}))
    _delete_pool_probe_resume_file()
    return payload if payload and payload.get('tasks') else None


def _has_pool_probe_resume_payload():
    with pool_probe_resume_lock:
        if pool_probe_resume_payload and pool_probe_resume_payload.get('tasks'):
            return True
    if os.path.exists(POOL_PROBE_RESUME_FILE):
        return bool(_normalize_pool_probe_resume_payload(_read_json_file(POOL_PROBE_RESUME_FILE, {})))
    return False


def _restore_pool_probe_resume_payload(payload):
    global pool_probe_resume_payload
    payload = _persist_pool_probe_resume_payload(payload)
    if not payload:
        return
    with pool_probe_resume_lock:
        if not pool_probe_resume_payload:
            pool_probe_resume_payload = payload


def _load_persisted_pool_probe_resume():
    global pool_probe_resume_payload
    payload = _normalize_pool_probe_resume_payload(_read_json_file(POOL_PROBE_RESUME_FILE, {}))
    if not payload:
        _delete_pool_probe_resume_file()
        return False
    with pool_probe_resume_lock:
        if not pool_probe_resume_payload:
            pool_probe_resume_payload = payload
    _set_pool_probe_progress(
        running=False,
        checked=payload['checked'],
        total=payload['total'],
        scope=payload['scope'],
        note='Проверка пула восстановлена после перезапуска бота и продолжится после освобождения памяти.',
        started_at=payload['started_at'],
        finished_at=0,
    )
    _schedule_low_memory_pool_probe_resume()
    return True


def _schedule_low_memory_pool_probe_resume():
    global pool_probe_low_memory_resume_scheduled
    with pool_probe_resume_lock:
        if pool_probe_low_memory_resume_scheduled:
            return
        pool_probe_low_memory_resume_scheduled = True

    def worker():
        global pool_probe_low_memory_resume_scheduled
        try:
            while not shutdown_requested.is_set():
                if not _has_pool_probe_resume_payload():
                    return
                if pool_probe_lock.locked():
                    shutdown_requested.wait(1)
                    continue
                available_kb = _available_memory_kb()
                rss_kb = _process_rss_kb()
                rss_ready = (
                    MEMORY_WATCHDOG_RSS_SOFT_KB <= 0 or
                    not rss_kb or
                    rss_kb < MEMORY_WATCHDOG_RSS_SOFT_KB
                )
                if not rss_ready:
                    cleanup = _memory_cleanup('pool probe resume wait', force=True, clear_status=True)
                    rss_kb = cleanup.get('rss_after_kb') or _process_rss_kb()
                    rss_ready = (
                        MEMORY_WATCHDOG_RSS_SOFT_KB <= 0 or
                        not rss_kb or
                        rss_kb < MEMORY_WATCHDOG_RSS_SOFT_KB
                    )
                if (available_kb is None or available_kb >= POOL_PROBE_PAUSE_AVAILABLE_KB) and rss_ready:
                    started, queued = _resume_cancelled_pool_probe('ожидания свободной памяти')
                    if started:
                        return
                if not rss_ready:
                    note = (
                        f'Проверка пула приостановлена до освобождения памяти бота: RSS {int(rss_kb or 0)} KB, '
                        f'порог {MEMORY_WATCHDOG_RSS_SOFT_KB} KB.'
                    )
                elif available_kb is None:
                    note = 'Проверка пула приостановлена до освобождения памяти.'
                else:
                    note = (
                        f'Проверка пула приостановлена до освобождения памяти: доступно {available_kb} KB, '
                        f'порог {POOL_PROBE_PAUSE_AVAILABLE_KB} KB.'
                    )
                _set_pool_probe_progress(note=note)
                shutdown_requested.wait(max(3.0, POOL_PROBE_LOW_MEMORY_DELAY_SECONDS))
        finally:
            with pool_probe_resume_lock:
                pool_probe_low_memory_resume_scheduled = False
            if _has_pool_probe_resume_payload() and not shutdown_requested.is_set():
                _schedule_low_memory_pool_probe_resume()

    threading.Thread(target=worker, daemon=True).start()


def _pool_probe_process_tmp_dir():
    for candidate in ('/opt/tmp', tempfile.gettempdir()):
        try:
            os.makedirs(candidate, exist_ok=True)
            if os.path.isdir(candidate):
                return candidate
        except Exception:
            continue
    return tempfile.gettempdir()


def _pool_probe_process_paths():
    base = os.path.join(
        _pool_probe_process_tmp_dir(),
        f'bypass_pool_probe_worker_{os.getpid()}_{int(time.time() * 1000)}',
    )
    return {
        'input_path': base + '.input.json',
        'progress_path': base + '.progress.json',
        'result_path': base + '.result.json',
        'cancel_path': base + '.cancel',
    }


def _failover_candidate_process_paths():
    base = os.path.join(
        _pool_probe_process_tmp_dir(),
        f'bypass_failover_worker_{os.getpid()}_{int(time.time() * 1000)}',
    )
    return {
        'input_path': base + '.input.json',
        'result_path': base + '.result.json',
    }


def _health_check_process_paths():
    base = os.path.join(
        _pool_probe_process_tmp_dir(),
        f'bypass_health_worker_{os.getpid()}_{int(time.time() * 1000)}',
    )
    return {
        'input_path': base + '.input.json',
        'result_path': base + '.result.json',
    }


def _pool_probe_progress_payload(*, running, checked, total, scope, note='', started_at=0, finished_at=0):
    return {
        'running': bool(running),
        'checked': max(0, int(checked or 0)),
        'total': max(0, int(total or 0)),
        'scope': str(scope or ''),
        'note': str(note or ''),
        'started_at': float(started_at or 0),
        'finished_at': float(finished_at or 0),
    }


def _pool_probe_write_progress(progress_path, **updates):
    current = _read_json_file(progress_path, {}) or {}
    if not isinstance(current, dict):
        current = {}
    current.update(updates)
    payload = _pool_probe_progress_payload(
        running=current.get('running'),
        checked=current.get('checked'),
        total=current.get('total'),
        scope=current.get('scope'),
        note=current.get('note', ''),
        started_at=current.get('started_at', 0),
        finished_at=current.get('finished_at', 0),
    )
    _write_json_file(progress_path, payload)
    return payload


def _pool_probe_sync_process_progress(progress_path):
    try:
        stat_result = os.stat(progress_path)
        signature = (int(stat_result.st_mtime_ns), int(stat_result.st_size))
    except OSError:
        signature = None
    with pool_probe_resume_lock:
        if (
            pool_probe_process_state.get('progress_path') == progress_path and
            signature is not None and
            pool_probe_process_state.get('progress_signature') == signature
        ):
            return {}
    progress = _read_json_file(progress_path, {}) or {}
    if not isinstance(progress, dict):
        return {}
    updates = {}
    for key in ('running', 'checked', 'total', 'scope', 'note', 'started_at', 'finished_at'):
        if key in progress:
            updates[key] = progress[key]
    if updates:
        _set_pool_probe_progress(**updates)
    if signature is not None:
        with pool_probe_resume_lock:
            if pool_probe_process_state.get('progress_path') == progress_path:
                pool_probe_process_state['progress_signature'] = signature
    return progress


def _pool_probe_process_worker_code(input_path, progress_path, result_path, cancel_path):
    module_dir = os.path.dirname(BOT_SOURCE_PATH)
    return (
        'import os, sys; '
        'os.environ["BYPASS_KEENETIC_COMMAND_WORKER"] = "1"; '
        'os.environ["BYPASS_KEENETIC_POOL_PROBE_WORKER"] = "1"; '
        f"sys.path.insert(0, {module_dir!r}); "
        'import pool_probe_process_runner as runner; '
        'sys.exit(runner.run_pool_probe_process_worker('
        f'{input_path!r}, {progress_path!r}, {result_path!r}, {cancel_path!r}))'
    )


def _pool_probe_records_apply_worker_code(records_path, result_path):
    module_dir = os.path.dirname(BOT_SOURCE_PATH)
    return (
        'import os, sys; '
        'os.environ["BYPASS_KEENETIC_COMMAND_WORKER"] = "1"; '
        'os.environ["BYPASS_KEENETIC_POOL_PROBE_WORKER"] = "1"; '
        f"sys.path.insert(0, {module_dir!r}); "
        'import pool_probe_process_runner as runner; '
        'sys.exit(runner.run_pool_probe_records_apply_worker('
        f'{records_path!r}, {result_path!r}))'
    )


def _run_pool_probe_process_worker(input_path, progress_path, result_path, cancel_path):
    """Compatibility entry point for manual worker invocation."""
    import pool_probe_process_runner

    return pool_probe_process_runner.run_pool_probe_process_worker(
        input_path,
        progress_path,
        result_path,
        cancel_path,
    )


def _apply_pool_probe_records_in_worker(records_path):
    records_path = str(records_path or '')
    if not records_path:
        return 0
    result_path = f'{records_path}.apply.json'
    _remove_file(result_path)
    env = dict(os.environ)
    env['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
    env['BYPASS_KEENETIC_POOL_PROBE_WORKER'] = '1'
    process = subprocess.Popen(
        [sys.executable, '-c', _pool_probe_records_apply_worker_code(records_path, result_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        env=env,
    )
    try:
        process.wait(timeout=POOL_PROBE_CACHE_APPLY_TIMEOUT_SECONDS)
        result = _read_json_file(result_path, {}) or {}
        if process.returncode != 0 or not result.get('ok'):
            raise RuntimeError(str(result.get('error') or 'cache apply worker failed'))
        return max(0, int(result.get('applied') or 0))
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
        raise RuntimeError('cache apply worker timed out')
    finally:
        _remove_file(result_path)


def _cleanup_pool_probe_process_files(state=None):
    state = state or pool_probe_process_state
    for key in ('input_path', 'progress_path', 'result_path', 'cancel_path'):
        path = state.get(key) if isinstance(state, dict) else ''
        if path:
            _remove_file(path)
            if key == 'result_path':
                _remove_file(f'{path}.records')
                _remove_file(f'{path}.records.apply.json')


def _request_pool_probe_process_cancel(resume=True):
    with pool_probe_resume_lock:
        cancel_path = pool_probe_process_state.get('cancel_path')
    if not cancel_path:
        return False
    try:
        with open(cancel_path, 'w', encoding='utf-8') as file:
            file.write(('resume' if resume else 'no-resume') + f' {time.time()}')
        try:
            os.chmod(cancel_path, 0o600)
        except Exception:
            pass
        return True
    except Exception as exc:
        _write_runtime_log(f'Failed to request pool probe process cancel: {exc}')
        return False


def _terminate_pool_probe_process_worker():
    with pool_probe_resume_lock:
        process = pool_probe_process_state.get('process')
    if not process or process.poll() is not None:
        return False
    _request_pool_probe_process_cancel()
    try:
        process.terminate()
    except Exception:
        pass
    deadline = time.time() + 3.0
    while process.poll() is None and time.time() < deadline:
        time.sleep(0.1)
    if process.poll() is None:
        try:
            process.kill()
        except Exception:
            pass
    return True


def _start_selected_pool_probe_process(selected, custom_checks, scope, *, initial_checked=0, total_count=None, started_at=None):
    selected = list(selected or [])
    if not selected:
        return False, 0
    queued_count = len(selected)
    if not pool_probe_lock.acquire(blocking=False):
        return False, queued_count
    pool_probe_cancel_event.clear()
    initial_checked = max(0, int(initial_checked or 0))
    total_count = len(selected) if total_count is None else max(initial_checked, int(total_count or 0))
    started_at = time.time() if started_at is None else float(started_at or time.time())
    paths = _pool_probe_process_paths()
    task_key_ids = [
        _probe_cache().hash_key(str(item[1] or ''))
        if isinstance(item, (list, tuple)) and len(item) >= 2 else ''
        for item in selected
    ]
    payload = {
        'tasks': selected,
        'task_key_ids': task_key_ids,
        'checks': list(custom_checks or []),
        'scope': scope,
        'initial_checked': initial_checked,
        'total_count': total_count,
        'started_at': started_at,
        'telegram_authenticated': bool(_app_mode_telegram_enabled()),
        'telegram_required_protocol': _telegram_route_protocol(),
    }
    try:
        _write_json_file_private(paths['input_path'], payload)
        _pool_probe_write_progress(
            paths['progress_path'],
            running=True,
            checked=initial_checked,
            total=total_count,
            scope=scope,
            note='',
            started_at=started_at,
            finished_at=0,
        )
        env = dict(os.environ)
        env['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
        env['BYPASS_KEENETIC_POOL_PROBE_WORKER'] = '1'
        process = subprocess.Popen(
            [sys.executable, '-c', _pool_probe_process_worker_code(
                paths['input_path'],
                paths['progress_path'],
                paths['result_path'],
                paths['cancel_path'],
            )],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            env=env,
        )
    except Exception:
        _cleanup_pool_probe_process_files(paths)
        pool_probe_lock.release()
        raise
    finally:
        try:
            selected.clear()
            payload['tasks'] = []
        except Exception:
            pass

    with pool_probe_resume_lock:
        pool_probe_process_state.update(paths)
        pool_probe_process_state['process'] = process
        pool_probe_process_state['progress_signature'] = None
    _set_pool_probe_progress(
        running=True,
        checked=initial_checked,
        total=total_count,
        scope=scope,
        note='',
        started_at=started_at,
        finished_at=0,
    )

    def monitor():
        result = {}
        try:
            while process.poll() is None:
                if pool_probe_cancel_event.is_set():
                    _request_pool_probe_process_cancel()
                _pool_probe_sync_process_progress(paths['progress_path'])
                shutdown_requested.wait(POOL_PROBE_PROCESS_WORKER_POLL_SECONDS)
            progress = _pool_probe_sync_process_progress(paths['progress_path'])
            result = _read_json_file(paths['result_path'], {}) or {}
            if not isinstance(result, dict):
                result = {}
            try:
                expected_records_path = f"{paths['result_path']}.records"
                records_path = str(result.get('probe_records_path') or '')
                if records_path == expected_records_path:
                    _apply_pool_probe_records_in_worker(records_path)
            except Exception as exc:
                _write_runtime_log(f'Pool probe cache apply failed: {type(exc).__name__}')
            remaining = result.get('remaining') or []
            if remaining and bool(result.get('resume_allowed', True)):
                _store_cancelled_pool_probe(remaining, custom_checks, scope)
            checked = int(result.get('absolute_checked') or progress.get('checked') or initial_checked)
            note = ''
            if process.returncode != 0:
                note = str(result.get('error') or f'pool probe worker exited with code {process.returncode}')
                _write_runtime_log(note)
            _set_pool_probe_progress(
                running=False,
                checked=max(0, checked),
                total=max(total_count, int(result.get('total') or progress.get('total') or total_count)),
                scope=scope,
                note=note,
                started_at=started_at,
                finished_at=float(result.get('finished_at') or time.time()),
            )
            _record_memory_timeline(
                'pool probe process finished',
                marker='pool_probe_process_finish',
                extra={
                    'pool_probe_scope': str(scope or ''),
                    'worker_returncode': int(process.returncode or 0),
                    'worker_rss_before_kb': int(result.get('rss_before_kb') or 0),
                    'worker_rss_after_kb': int(result.get('rss_after_kb') or 0),
                    'worker_hwm_kb': int(result.get('hwm_kb') or 0),
                    'main_rss_kb': int(_process_rss_kb() or 0),
                },
                force=True,
            )
        finally:
            _invalidate_probe_status_caches()
            # The child normally reaps its own temporary Xray.  A last, scoped
            # sweep protects the router if that child is killed before its
            # finally block runs; it only matches bypass_pool_probe_* runtime.
            _cleanup_pool_probe_runtime_light(kill_processes=True)
            _cleanup_pool_probe_process_files(paths)
            with pool_probe_resume_lock:
                if pool_probe_process_state.get('process') is process:
                    pool_probe_process_state.update({
                        'process': None,
                        'input_path': '',
                        'progress_path': '',
                        'result_path': '',
                        'cancel_path': '',
                        'progress_signature': None,
                    })
            try:
                pool_probe_lock.release()
            except RuntimeError:
                pass
            cleanup = _memory_cleanup('pool probe process finished', force=True, clear_status=False, log=False)
            finished_rss_kb = int(cleanup.get('rss_after_kb') or _process_rss_kb() or 0)
            _record_pool_probe_completion(
                worker_rss_before_kb=int(result.get('rss_before_kb') or 0),
                worker_hwm_kb=int(result.get('hwm_kb') or 0),
                finished_rss_kb=finished_rss_kb,
                bot_hwm_kb=int(_process_hwm_kb() or 0),
                scope=scope,
            )

    threading.Thread(target=monitor, daemon=True).start()
    return True, queued_count


def _start_selected_pool_probe_tasks(selected, custom_checks, scope, *, initial_checked=0, total_count=None, started_at=None):
    global pool_probe_resume_after_cancel
    pool_probe_resume_after_cancel = True
    _reset_pool_probe_quality_sample_budget()
    if not POOL_PROBE_WORKER_MODE:
        if POOL_PROBE_PROCESS_WORKER_ENABLED:
            return _start_selected_pool_probe_process(
                selected,
                custom_checks,
                scope,
                initial_checked=initial_checked,
                total_count=total_count,
                started_at=started_at,
            )
        if not POOL_PROBE_INPROCESS_FALLBACK_ENABLED:
            _write_runtime_log('Pool probe process worker is disabled; in-process pool probe fallback is disabled for router memory safety.')
            return False, len(selected or [])
    return _pool_probe_controller().start_pool_probe_worker(
        selected,
        custom_checks,
        scope=scope,
        lock=pool_probe_lock,
        set_progress=_set_pool_probe_progress,
        run_worker=lambda probe_tasks, checks, set_checked, invalidate_caches, cancel_event=None: _run_selected_pool_probe(
            probe_tasks,
            checks,
            set_checked,
            invalidate_caches,
            scope=scope,
            cancel_event=cancel_event,
        ),
        invalidate_caches=_invalidate_probe_status_caches,
        cancel_event=pool_probe_cancel_event,
        initial_checked=initial_checked,
        total_count=total_count,
        started_at=started_at,
    )


def _resume_cancelled_pool_probe(reason='применения ключа'):
    payload = _take_cancelled_pool_probe()
    if not payload:
        if pool_probe_cancel_event.is_set():
            def delayed_resume():
                deadline = time.time() + 60
                while pool_probe_lock.locked() and time.time() < deadline:
                    time.sleep(0.5)
                delayed_payload = _take_cancelled_pool_probe()
                delayed_payload = _resolve_pool_probe_resume_tasks(delayed_payload)
                if delayed_payload:
                    _start_selected_pool_probe_tasks(
                        delayed_payload.get('tasks') or [],
                        delayed_payload.get('checks') or [],
                        delayed_payload.get('scope') or 'manual',
                        initial_checked=delayed_payload.get('checked') or 0,
                        total_count=delayed_payload.get('total'),
                        started_at=delayed_payload.get('started_at') or None,
                    )
                elif not pool_probe_lock.locked():
                    pool_probe_cancel_event.clear()

            threading.Thread(target=delayed_resume, daemon=True).start()
        return False, 0
    resolved_payload = _resolve_pool_probe_resume_tasks(payload)
    if not resolved_payload:
        return False, 0
    started, queued = _start_selected_pool_probe_tasks(
        resolved_payload.get('tasks') or [],
        resolved_payload.get('checks') or [],
        resolved_payload.get('scope') or 'manual',
        initial_checked=resolved_payload.get('checked') or 0,
        total_count=resolved_payload.get('total'),
        started_at=resolved_payload.get('started_at') or None,
    )
    if not started:
        _restore_pool_probe_resume_payload(payload)
    if started:
        _write_runtime_log(f'Проверка пула продолжена после {reason}. Осталось в очереди: {queued}.')
    return started, queued


def _pause_pool_probe_for_apply(timeout=12.0):
    global pool_probe_resume_after_cancel
    if not pool_probe_lock.locked():
        return False, ''
    pool_probe_resume_after_cancel = True
    pool_probe_cancel_event.set()
    _request_pool_probe_process_cancel()
    _set_pool_probe_progress(note='Проверка пула приостанавливается для применения выбранного ключа.')
    deadline = time.time() + max(0.5, float(timeout or 0))
    while pool_probe_lock.locked() and time.time() < deadline:
        time.sleep(0.2)
    if pool_probe_lock.locked():
        _cleanup_pool_probe_runtime_light(kill_processes=True)
        _terminate_pool_probe_process_worker()
        force_deadline = time.time() + 5.0
        while pool_probe_lock.locked() and time.time() < force_deadline:
            time.sleep(0.2)
    if pool_probe_lock.locked():
        _resume_cancelled_pool_probe('неудачной паузы проверки пула')
        raise RuntimeError('Проверка пула ещё останавливается. Ключ не применён, чтобы не перезапускать основной Xray поверх активной проверки. Повторите применение через несколько секунд.')
    return True, 'Проверка пула приостановлена; после применения ключа она продолжится.'


def _cancel_pool_probe(timeout=2.0):
    global pool_probe_resume_after_cancel, pool_probe_resume_payload
    if not pool_probe_lock.locked():
        had_resume_payload = _has_pool_probe_resume_payload()
        with pool_probe_resume_lock:
            pool_probe_resume_payload = None
        _delete_pool_probe_resume_file()
        if had_resume_payload:
            _set_pool_probe_progress(running=False, checked=0, total=0, scope='', note='', finished_at=time.time())
            _invalidate_probe_status_caches()
            return True, 'Очередь проверки пула очищена.'
        return False, 'Проверка пула сейчас не выполняется.'
    pool_probe_resume_after_cancel = False
    with pool_probe_resume_lock:
        pool_probe_resume_payload = None
    _delete_pool_probe_resume_file()
    pool_probe_cancel_event.set()
    _request_pool_probe_process_cancel(resume=False)
    _set_pool_probe_progress(note='Остановка проверки пула после текущего ключа.')
    deadline = time.time() + max(0.2, float(timeout or 0))
    while pool_probe_lock.locked() and time.time() < deadline:
        time.sleep(0.2)
    if pool_probe_lock.locked():
        return True, 'Остановка проверки пула запрошена. Текущий ключ будет завершён, временный xray остановится.'
    return True, 'Проверка пула остановлена.'


def _run_selected_pool_probe(
    probe_tasks,
    checks,
    set_checked,
    invalidate_caches,
    scope='manual',
    cancel_event=None,
    set_note=None,
    store_cancelled_probe=None,
):
    probe_recorder = _KeyProbeBatchRecorder(
        flush_every=POOL_PROBE_CACHE_FLUSH_EVERY,
        flush_interval=POOL_PROBE_CACHE_FLUSH_INTERVAL,
    )
    start_rss_kb = int(_process_rss_kb() or 0)
    batch_size = POOL_PROBE_BATCH_SIZE
    if not POOL_PROBE_BATCH_SIZE_CONFIGURED:
        available_kb = _available_memory_kb()
        if available_kb is not None and available_kb >= 200000:
            batch_size = min(2, max(1, len(probe_tasks or [])))
    concurrency = max(1, min(POOL_PROBE_CONCURRENCY, batch_size))
    _record_memory_timeline(
        'pool probe started',
        marker='pool_probe_start',
        extra={
            'pool_probe_task_count': len(probe_tasks or []),
            'pool_probe_batch_size': int(batch_size),
            'pool_probe_concurrency': int(concurrency),
            'pool_probe_scope': str(scope or ''),
        },
        force=True,
    )
    try:
        return _pool_probe_runner().run_pool_probe_worker(
            probe_tasks,
            checks,
            batch_size=batch_size,
            concurrency=concurrency,
            delay_seconds=POOL_PROBE_DELAY_SECONDS,
            min_available_kb=POOL_PROBE_PAUSE_AVAILABLE_KB,
            test_port=POOL_PROBE_TEST_PORT,
            available_memory_kb=_available_memory_kb,
            log=_write_runtime_log,
            proto_label=_pool_proto_label,
            hash_key=_hash_key,
            set_checked=set_checked,
            validate_outbound=lambda proto, key_value: _pool_probe_runner().pool_probe_outbound(
                proto,
                key_value,
                'proxy-pool-probe-validate',
                _proxy_outbound_from_key,
            ),
            failed_custom_results=_pool_probe_controller().failed_custom_probe_results,
            record_key_probe=probe_recorder.record,
            start_xray_for_batch=lambda valid_batch: _pool_probe_runner().start_pool_probe_xray(
                _pool_probe_runner().build_pool_probe_core_config_batch(valid_batch, POOL_PROBE_TEST_PORT, _proxy_outbound_from_key)
            ),
            wait_for_socks5=_wait_for_socks5_handshake,
            check_pool_key=_check_pool_key_through_proxy,
            timeout_budget=_pool_probe_timeout_budget,
            stop_xray=_pool_probe_runner().stop_pool_probe_xray,
            cleanup_runtime=_pool_probe_runner().cleanup_pool_probe_runtime,
            invalidate_caches=invalidate_caches,
            cancel_event=cancel_event,
            on_cancelled_remaining=store_cancelled_probe or (
                lambda remaining: _store_cancelled_pool_probe(remaining, checks, scope)
            ),
            set_note=set_note or (lambda note: _set_pool_probe_progress(note=note)),
            cpu_busy_percent=_pool_probe_cpu_busy_percent if POOL_PROBE_CPU_GUARD_ENABLED else None,
            max_cpu_percent=POOL_PROBE_MAX_CPU_PERCENT,
            high_cpu_delay_seconds=POOL_PROBE_HIGH_CPU_DELAY_SECONDS,
            max_high_cpu_wait_seconds=POOL_PROBE_HIGH_CPU_MAX_WAIT_SECONDS,
            load_average=_pool_probe_load_average if POOL_PROBE_MAX_LOAD1 > 0 else None,
            max_load1=POOL_PROBE_MAX_LOAD1,
            high_load_delay_seconds=POOL_PROBE_HIGH_LOAD_DELAY_SECONDS,
            max_high_load_wait_seconds=POOL_PROBE_HIGH_LOAD_MAX_WAIT_SECONDS,
            low_memory_delay_seconds=POOL_PROBE_LOW_MEMORY_DELAY_SECONDS,
            max_low_memory_wait_seconds=POOL_PROBE_LOW_MEMORY_MAX_WAIT_SECONDS,
            slow_available_kb=POOL_PROBE_SLOW_AVAILABLE_KB,
            slow_memory_delay_seconds=POOL_PROBE_SLOW_MEMORY_DELAY_SECONDS,
            process_rss_kb=_process_rss_kb,
            max_process_rss_kb=POOL_PROBE_MAX_PROCESS_RSS_KB,
            memory_cleanup=None,
            rss_cleanup_delay_seconds=min(3.0, max(0.0, POOL_PROBE_LOW_MEMORY_DELAY_SECONDS)),
            max_rss_cleanup_attempts=3,
        )
    finally:
        probe_recorder.flush()
        _pool_probe_runner().cleanup_pool_probe_runtime(kill_processes=True)
        _cleanup_pool_probe_runtime_light(kill_processes=True)
        if not POOL_PROBE_WORKER_MODE:
            finished_rss_kb = int(_process_rss_kb() or 0)
            hwm_kb = int(_process_hwm_kb() or 0)
            _record_memory_timeline(
                'pool probe finished',
                marker='pool_probe_finish',
                extra={
                    'pool_probe_scope': str(scope or ''),
                    'rss_before_kb': start_rss_kb,
                    'rss_after_kb': finished_rss_kb,
                    'hwm_kb': hwm_kb,
                },
                force=True,
            )
            if start_rss_kb <= 0 and finished_rss_kb <= 0 and hwm_kb <= 0 and not scope:
                _record_pool_probe_completion()
            else:
                _record_pool_probe_completion(
                    bot_rss_before_kb=start_rss_kb,
                    finished_rss_kb=finished_rss_kb,
                    bot_hwm_kb=hwm_kb,
                    scope=scope,
                )


def _queue_pool_key_probe(tasks, max_keys=None, stale_only=False, scope='manual'):
    selected, custom_checks = _select_pool_probe_tasks(
        tasks,
        max_keys=max_keys,
        stale_only=stale_only,
    )
    if POOL_PROBE_ACTIVE_ONLY:
        selected = _pool_probe_controller().filter_active_probe_tasks(selected, _load_current_keys())
    return _start_selected_pool_probe_tasks(selected, custom_checks, scope)


def _probe_pool_keys_background(proto, keys, max_keys=KEY_PROBE_MAX_PER_RUN, stale_only=True, scope='protocol', resume_pending=False):
    if resume_pending and _has_pool_probe_resume_payload():
        return _resume_cancelled_pool_probe('ручного запуска')
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
        pools, added_by_proto = _key_pool_store().add_keys_to_pools_by_protocol(
            _key_pool_store().load_key_pools(KEY_POOLS_PATH),
            proto,
            keys_text,
        )
        _key_pool_store().save_key_pools(KEY_POOLS_PATH, pools)
    for added_proto, added_keys in added_by_proto.items():
        _probe_pool_keys_background(added_proto, added_keys)
    _invalidate_pool_data_cache()
    return sum(len(added_keys) for added_keys in added_by_proto.values())


def _import_keys_to_pools(proto, keys_text):
    lines = [
        line.strip()
        for line in str(keys_text or '').splitlines()
        if line.strip()
    ]
    supported_lines = [
        line
        for line in lines
        if _key_pool_store().key_has_supported_scheme(line)
    ]
    unrecognized_count = max(0, len(lines) - len(supported_lines))
    with key_pool_lock:
        pools, added_by_proto = _key_pool_store().add_keys_to_pools_by_protocol(
            _key_pool_store().load_key_pools(KEY_POOLS_PATH),
            proto,
            '\n'.join(supported_lines),
        )
        _key_pool_store().save_key_pools(KEY_POOLS_PATH, pools)
    for added_proto, added_keys in added_by_proto.items():
        _probe_pool_keys_background(added_proto, added_keys)
    _invalidate_pool_data_cache()
    added_counts = {item: len(values) for item, values in added_by_proto.items() if values}
    added_total = sum(added_counts.values())
    return {
        'input_count': len(lines),
        'supported_count': len(supported_lines),
        'added_total': added_total,
        'added_by_proto': added_counts,
        'duplicate_count': max(0, len(supported_lines) - added_total),
        'unrecognized_count': unrecognized_count,
    }


def _subscription_active_key_is_working(proto, key_value):
    key_value = str(key_value or '').strip()
    if not key_value:
        return False
    current_keys = _load_current_keys()
    if str((current_keys or {}).get(proto) or '').strip() != key_value:
        return False
    cache = _load_key_probe_cache()
    probe = cache.get(_hash_key(key_value), {}) if isinstance(cache, dict) else {}
    route_states = None
    required_services = ()
    try:
        route_states = _service_route_summary()
        required_services = _key_pool_web().core_services_for_protocol(route_states, proto)
    except Exception:
        route_states = None
        required_services = ()
    if _active_status_can_use_recent_probe(probe, required_services=required_services):
        return True
    if proto != proxy_mode or (globals().get('pool_probe_lock') and pool_probe_lock.locked()):
        return False
    try:
        status = _protocol_status_for_key(
            proto,
            key_value,
            key_probe_cache=cache,
            route_states=route_states,
        )
    except Exception as exc:
        _write_runtime_log(f'Subscription active key check for {proto} failed: {exc}')
        return False
    return bool(
        status.get('tone') in ('ok', 'warn') or
        status.get('api_ok') is True or
        status.get('yt_ok') is True
    )


def _subscription_preserve_active_keys(proto, fetched_keys, previous_managed_keys=None):
    previous_set = set(_key_pool_store().dedupe_key_list(previous_managed_keys or []))
    if not previous_set:
        return []
    fetched_set = set(_subscription_runtime().subscription_keys_for_protocol(proto, fetched_keys))
    current_key = str((_load_current_keys().get(proto) or '')).strip()
    if not current_key or current_key not in previous_set or current_key in fetched_set:
        return []
    if _subscription_active_key_is_working(proto, current_key):
        return [current_key]
    return []


def _add_subscription_keys_to_pool(proto, fetched_keys, *, sync_subscription=False, previous_managed_keys=None):
    retained_keys = []
    if sync_subscription:
        retained_keys = _subscription_preserve_active_keys(proto, fetched_keys, previous_managed_keys)
    with key_pool_lock:
        if sync_subscription:
            pools, added_keys, removed_keys, managed_keys = _subscription_runtime().sync_subscription_keys_to_pool(
                _key_pool_store().load_key_pools(KEY_POOLS_PATH),
                proto,
                fetched_keys,
                previous_managed_keys=previous_managed_keys,
                preserve_keys=retained_keys,
            )
        else:
            pools, added_keys = _key_pool_store().add_subscription_keys_to_pool(
                _key_pool_store().load_key_pools(KEY_POOLS_PATH),
                proto,
                fetched_keys,
            )
            removed_keys = []
            managed_keys = _subscription_runtime().subscription_keys_for_protocol(proto, fetched_keys)
        _key_pool_store().save_key_pools(KEY_POOLS_PATH, pools)
    if removed_keys:
        _forget_unreferenced_key_probes(removed_keys, pools)
    if added_keys:
        _probe_pool_keys_background(proto, added_keys)
    _invalidate_pool_data_cache()
    return pools, added_keys, removed_keys, managed_keys, retained_keys


def _import_subscription_keys_to_pools(proto, fetched_keys, *, sync_subscription=False, previous_managed_keys=None):
    selected_keys = _subscription_runtime().subscription_keys_for_protocol(proto, fetched_keys)
    pools, added_keys, removed_keys, managed_keys, retained_keys = _add_subscription_keys_to_pool(
        proto,
        fetched_keys,
        sync_subscription=sync_subscription,
        previous_managed_keys=previous_managed_keys,
    )
    selected_source = _subscription_runtime().subscription_source_protocol(proto)
    extra_lines = []
    for source_proto, keys in (fetched_keys or {}).items():
        if source_proto == selected_source:
            continue
        extra_lines.extend(_key_pool_store().dedupe_key_list(keys or []))
    extra_summary = _import_keys_to_pools(proto, '\n'.join(extra_lines)) if extra_lines else {
        'input_count': 0,
        'supported_count': 0,
        'added_total': 0,
        'added_by_proto': {},
        'duplicate_count': 0,
        'unrecognized_count': 0,
    }
    return {
        'selected_total': len(selected_keys),
        'selected_added': len(added_keys),
        'selected_duplicate_count': max(0, len(selected_keys) - len(added_keys)),
        'removed_count': len(removed_keys),
        'retained_count': len(retained_keys),
        'managed_keys': managed_keys,
        'extra': extra_summary,
    }


def _refresh_subscription_once(proto, record, *, source='auto'):
    url = str((record or {}).get('url') or '').strip()
    if not url or not bool((record or {}).get('hwid_enabled')):
        return False
    if source == 'auto':
        if not _subscription_auto_refresh_allowed(proto):
            return False
    attempt_at = time.time()
    try:
        fetched, error = _fetch_keys_from_subscription(url, use_router_hwid=True)
        if error:
            raise ValueError(error)
        selected_keys = _subscription_runtime().subscription_keys_for_protocol(proto, fetched)
        if not selected_keys:
            raise ValueError('subscription did not return keys for the selected protocol')
        pools, added_keys, removed_keys, _managed_keys, retained_keys = _add_subscription_keys_to_pool(
            proto,
            fetched,
            sync_subscription=True,
            previous_managed_keys=(record or {}).get('managed_keys', []),
        )
        _update_subscription_record(
            proto,
            url=url,
            hwid_enabled=True,
            last_attempt_at=attempt_at,
            last_success_at=time.time(),
            last_error='',
            managed_keys=_managed_keys,
        )
        _write_runtime_log(
            f'Subscription {source} refresh for {proto}: added={len(added_keys)}, '
            f'removed={len(removed_keys)}, retained_active={len(retained_keys)}, total={len(_managed_keys)}'
        )
        return True
    except Exception as exc:
        _update_subscription_record(
            proto,
            url=url,
            hwid_enabled=True,
            last_attempt_at=attempt_at,
            last_error=str(exc),
        )
        _write_runtime_log(f'Subscription {source} refresh for {proto} failed: {exc}')
        return False


def _subscription_refresh_due(record, now):
    if not record or not record.get('url') or not record.get('hwid_enabled'):
        return False
    last_success = float(record.get('last_success_at') or 0)
    last_attempt = float(record.get('last_attempt_at') or 0)
    if last_success:
        return now - last_success >= SUBSCRIPTION_AUTO_REFRESH_INTERVAL_SECONDS
    if last_attempt:
        return now - last_attempt >= SUBSCRIPTION_AUTO_REFRESH_RETRY_SECONDS
    return True


def _nightly_subscription_pool_probe_state():
    if not SUBSCRIPTION_NIGHTLY_POOL_PROBE_STATE_PATH:
        return {}
    payload = _read_json_file(SUBSCRIPTION_NIGHTLY_POOL_PROBE_STATE_PATH, {}) or {}
    return payload if isinstance(payload, dict) else {}


def _mark_nightly_subscription_pool_probe_started(window_date, now):
    if not SUBSCRIPTION_NIGHTLY_POOL_PROBE_STATE_PATH or not window_date:
        return
    _write_json_file(
        SUBSCRIPTION_NIGHTLY_POOL_PROBE_STATE_PATH,
        {
            'window_date': str(window_date),
            'started_at': float(now),
        },
    )


def _maybe_start_nightly_subscription_pool_probe(subscription_state, now=None):
    """Queue one full pool probe after a recent successful nightly subscription refresh."""
    if not SUBSCRIPTION_NIGHTLY_POOL_PROBE_ENABLED or not _app_mode_pool_enabled():
        return False
    now = time.time() if now is None else float(now)
    window_date = _subscription_runtime().nightly_pool_probe_window_date(
        now,
        start_hour=SUBSCRIPTION_NIGHTLY_POOL_PROBE_START_HOUR,
        end_hour=SUBSCRIPTION_NIGHTLY_POOL_PROBE_END_HOUR,
    )
    if not window_date:
        return False
    state = _nightly_subscription_pool_probe_state()
    if str(state.get('window_date') or '') == window_date:
        return False
    refreshed_at = _subscription_runtime().latest_recent_subscription_success_at(
        subscription_state,
        now,
        max_age_seconds=SUBSCRIPTION_NIGHTLY_POOL_PROBE_MAX_REFRESH_AGE_SECONDS,
    )
    if not refreshed_at:
        return False
    task_name = 'Nightly subscription pool probe'
    if not _background_task_allowed(task_name):
        return False
    if pool_probe_lock.locked() or _has_pool_probe_resume_payload():
        background_task_skip_until[task_name] = now + min(60.0, BACKGROUND_TASK_BUSY_BACKOFF_SECONDS)
        background_task_skip_reason[task_name] = 'pool_probe'
        return False
    coordinator_started, result = _run_coordinated_background_task(
        task_name,
        lambda: _probe_all_pool_keys_async(
            stale_only=False,
            max_keys=None,
            scope='nightly_subscription',
        ),
    )
    if not coordinator_started or not isinstance(result, tuple):
        return False
    probe_started, queued = result
    if not probe_started:
        return False
    _mark_nightly_subscription_pool_probe_started(window_date, now)
    _write_runtime_log(
        f'Nightly subscription pool probe started after refresh at {time.strftime("%H:%M", time.localtime(refreshed_at))}: '
        f'{int(queued or 0)} keys queued.'
    )
    return True


def _run_subscription_auto_refresh_cycle():
    if not SUBSCRIPTION_AUTO_REFRESH_ENABLED or not SUBSCRIPTION_STATE_PATH:
        return
    refreshed = False
    try:
        state = _load_subscription_state()
        now = time.time()
        for proto, record in state.items():
            if shutdown_requested.is_set():
                break
            if _subscription_refresh_due(record, now):
                started, result = _run_coordinated_background_task(
                    'Subscription auto refresh',
                    lambda: _refresh_subscription_once(proto, record, source='auto'),
                )
                refreshed = refreshed or bool(started and result)
    except Exception as exc:
        _write_runtime_log(f'Subscription auto refresh error: {exc}')
    finally:
        if refreshed:
            _memory_cleanup('Subscription auto refresh cycle', clear_status=False, log=False)
        try:
            _maybe_start_nightly_subscription_pool_probe(_load_subscription_state())
        except Exception as exc:
            _write_runtime_log(f'Nightly subscription pool probe scheduling error: {exc}')


def _background_maintenance_tasks():
    tasks = [('router CPU sample', 5.0, 0.0, router_health.sample_cpu)]
    if MEMORY_TIMELINE_ENABLED and MEMORY_TIMELINE_PATH:
        _record_memory_timeline('startup', marker='startup', force=True)
        tasks.append(('memory timeline', MEMORY_TIMELINE_INTERVAL_SECONDS, MEMORY_TIMELINE_INTERVAL_SECONDS, _run_memory_timeline_cycle))
    if MEMORY_WATCHDOG_ENABLED and MEMORY_WATCHDOG_RSS_LIMIT_KB > 0:
        tasks.append((
            'memory watchdog',
            MEMORY_WATCHDOG_CHECK_INTERVAL,
            min(MEMORY_WATCHDOG_CHECK_INTERVAL, MEMORY_WATCHDOG_MIN_UPTIME_SECONDS),
            _run_memory_watchdog_cycle,
        ))
    if not _app_mode_pool_enabled():
        return tasks
    if UDP_QUIC_DRIFT_CHECK_ENABLED:
        tasks.append(('UDP/QUIC drift watchdog', UDP_QUIC_DRIFT_CHECK_INTERVAL_SECONDS, 30.0, _run_udp_quic_drift_watchdog_cycle))
    if SUBSCRIPTION_AUTO_REFRESH_ENABLED and SUBSCRIPTION_STATE_PATH:
        tasks.append((
            'subscription auto refresh',
            SUBSCRIPTION_AUTO_REFRESH_CHECK_SECONDS,
            SUBSCRIPTION_AUTO_REFRESH_START_DELAY_SECONDS,
            _run_subscription_auto_refresh_cycle,
        ))
    tasks.append(('Telegram auto-failover', AUTO_FAILOVER_POLL_SECONDS, 0.0, _run_auto_failover_cycle))
    if YOUTUBE_VLESS2_FAILOVER_ENABLED:
        tasks.append(('YouTube failover', YOUTUBE_VLESS2_FAILOVER_POLL_SECONDS, 0.0, _run_youtube_failover_cycle))
    return tasks


def _start_background_maintenance_thread():
    global background_maintenance_thread
    if background_maintenance_thread and background_maintenance_thread.is_alive():
        return
    tasks = _background_maintenance_tasks()
    if not tasks:
        return
    due_at = {
        name: time.monotonic() + max(0.0, float(initial_delay or 0.0))
        for name, _interval, initial_delay, _callback in tasks
    }

    def worker():
        while not shutdown_requested.is_set():
            if _update_maintenance_active():
                shutdown_requested.wait(1.0)
                continue
            now = time.monotonic()
            next_due_at = now + 60.0
            for name, interval, _initial_delay, callback in tasks:
                scheduled_at = float(due_at.get(name) or now)
                if now >= scheduled_at:
                    started_at = time.monotonic()
                    try:
                        callback()
                    except Exception as exc:
                        _write_runtime_log(f'{name} scheduler error: {exc}')
                    duration_seconds = time.monotonic() - started_at
                    if duration_seconds >= BACKGROUND_TASK_SLOW_LOG_SECONDS:
                        _write_runtime_log(f'{name} scheduler duration: {duration_seconds:.2f}s')
                    scheduled_at = time.monotonic() + max(1.0, float(interval or 1.0))
                    due_at[name] = scheduled_at
                next_due_at = min(next_due_at, scheduled_at)
            shutdown_requested.wait(max(0.5, min(60.0, next_due_at - time.monotonic())))

    background_maintenance_thread = threading.Thread(
        target=worker,
        name='background-maintenance',
        daemon=True,
    )
    background_maintenance_thread.start()


def _web_custom_checks():
    return _key_pool_web().web_custom_checks(_load_custom_checks())

def _web_pool_snapshot_worker_payload(protocols=None, include_summary=False, include_custom_checks=False, include_pools=True):
    if not WEB_POOL_SNAPSHOT_WORKER_ENABLED:
        return None
    worker_path = os.path.join(BOT_DIR, 'web_pool_snapshot_worker.py')
    if not os.path.isfile(worker_path):
        return None
    request = {
        'protocols': list(protocols or []),
        'include_summary': bool(include_summary),
        'include_custom_checks': bool(include_custom_checks),
        'include_pools': bool(include_pools),
    }
    try:
        result = subprocess.run(
            [sys.executable or 'python3', worker_path],
            input=json.dumps(request, ensure_ascii=False, separators=(',', ':')),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=WEB_POOL_SNAPSHOT_WORKER_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception as exc:
        _write_runtime_log(f'Web pool snapshot worker unavailable: {type(exc).__name__}')
        return None
    if result.returncode != 0:
        error_text = str(result.stderr or '').strip().splitlines()[:1]
        error_label = error_text[0][:120] if error_text else f'exit {result.returncode}'
        _write_runtime_log(f'Web pool snapshot worker failed: {error_label}')
        return None
    try:
        payload = json.loads(result.stdout or '{}')
    except Exception as exc:
        _write_runtime_log(f'Web pool snapshot worker returned invalid JSON: {type(exc).__name__}')
        return None
    return payload if isinstance(payload, dict) and isinstance(payload.get('pools'), dict) else None


def _web_pools_light_payload(current_keys, key_pools, protocols=None, include_summary=False, include_custom_checks=False):
    custom_checks = _load_custom_checks() if include_custom_checks else []
    payload = {
        'pools': _key_pool_web().web_pool_snapshot(
            current_keys,
            key_pools,
            {},
            custom_checks,
            include_keys=False,
            hash_key=_hash_key,
            display_name=_pool_key_display_name,
            probe_state=_key_pool_web().web_probe_state,
            probe_checked_at=_key_pool_web().web_probe_checked_at,
            protocols=protocols,
            route_states=None,
        ),
        'pool_summary': None,
        'custom_checks': None,
    }
    if include_summary:
        payload['pool_summary'] = _light_pool_summary_with_cache_fallback(
            current_keys,
            key_pools,
            custom_checks,
        )
    if include_custom_checks:
        payload['custom_checks'] = _web_custom_checks_light(custom_checks)
    return payload


def _web_pools_payload(current_keys=None, protocols=None, include_summary=False, include_custom_checks=False):
    if not current_keys:
        current_keys = _load_current_keys()
    key_pools = _ensure_current_keys_in_pools(current_keys)
    if not include_summary and not include_custom_checks:
        worker_payload = _web_pool_snapshot_worker_payload(
            protocols=protocols,
            include_summary=False,
            include_custom_checks=False,
        )
        if worker_payload is not None:
            return worker_payload
    else:
        worker_payload = _web_pool_snapshot_worker_payload(
            protocols=protocols,
            include_summary=include_summary,
            include_custom_checks=include_custom_checks,
        )
        if worker_payload is not None:
            return worker_payload
    if _background_task_economy_mode():
        log_key = 'Web pool payload light fallback'
        now = time.time()
        last_log = float(background_task_skip_log_at.get(log_key) or 0.0)
        if now - last_log >= BACKGROUND_TASK_SKIP_LOG_INTERVAL_SECONDS:
            background_task_skip_log_at[log_key] = now
            _write_runtime_log('Web pool payload: using light fallback because bot RSS is high.')
        return _web_pools_light_payload(
            current_keys,
            key_pools,
            protocols=protocols,
            include_summary=include_summary,
            include_custom_checks=include_custom_checks,
        )
    custom_checks = _load_custom_checks()
    route_states = _service_route_summary()
    key_probe_cache = _load_key_probe_cache()
    payload = {
        'pools': _key_pool_web().web_pool_snapshot(
            current_keys,
            key_pools,
            key_probe_cache,
            custom_checks,
            include_keys=False,
            hash_key=_hash_key,
            display_name=_pool_key_display_name,
            probe_state=_key_pool_web().web_probe_state,
            probe_checked_at=_key_pool_web().web_probe_checked_at,
            protocols=protocols,
            route_states=route_states,
        ),
        'pool_summary': None,
        'custom_checks': None,
    }
    if include_summary:
        payload['pool_summary'] = _pool_status_summary(
            current_keys,
            key_pools,
            key_probe_cache,
            custom_checks,
            route_states,
        )
    if include_custom_checks:
        payload['custom_checks'] = _key_pool_web().web_custom_checks(custom_checks)
    return payload


def _web_pool_snapshot(current_keys=None, include_keys=False, protocols=None):
    if not include_keys:
        return _web_pools_payload(
            current_keys,
            protocols=protocols,
            include_summary=False,
            include_custom_checks=False,
        ).get('pools', {})
    current_keys = current_keys if current_keys is not None else _load_current_keys()
    custom_checks = _load_custom_checks()
    route_states = _service_route_summary()
    return _key_pool_web().web_pool_snapshot(
        current_keys,
        _ensure_current_keys_in_pools(current_keys),
        _load_key_probe_cache(),
        custom_checks,
        include_keys=include_keys,
        hash_key=_hash_key,
        display_name=_pool_key_display_name,
        probe_state=_key_pool_web().web_probe_state,
        probe_checked_at=_key_pool_web().web_probe_checked_at,
        protocols=protocols,
        route_states=route_states,
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
        youtube_route_protocol_getter=_youtube_route_protocol,
        youtube_timeouts=(YOUTUBE_VLESS2_FAILOVER_CHECK_CONNECT_TIMEOUT, YOUTUBE_VLESS2_FAILOVER_CHECK_READ_TIMEOUT),
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
            return '✅ Доступ к api.telegram.org подтверждён'
        if 'PySocks' in probe_message:
            return ('❌ Не удалось подключиться к Telegram API: отсутствует поддержка SOCKS (PySocks). '
                    'Установите python3-pysocks или используйте режим без SOCKS.')
        _log_telegram_api_status_failure(proxy_mode if proxy_mode != 'none' else 'direct', probe_message)
        if proxy_mode == 'none':
            last_result = web_status_runtime.telegram_api_direct_recovery_message()
        else:
            last_result = web_status_runtime.telegram_api_recovery_message(proxy_mode)
            if attempt < retries:
                time.sleep(retry_delay)
    return last_result


def _is_transient_telegram_api_failure(status_text):
    return _status_is_transient_text(status_text)


def _telegram_state_label():
    if not _app_mode_telegram_enabled():
        return 'Web only: Telegram-бот отключен'
    return 'polling активен' if bot_polling else ('ожидает запуска' if not bot_ready else 'процесс запущен, polling недоступен')


def _web_render_status_with_polling_guard(status, protocol_statuses, app_runtime_mode=None):
    if not (_app_mode_telegram_enabled(app_runtime_mode) and bot_ready and not bot_polling):
        return status, protocol_statuses
    guarded_status = dict(status or {})
    guarded_status['state_label'] = _telegram_state_label()
    guarded_status['api_status'] = web_status_runtime.telegram_api_refresh_message()

    guarded_protocols = dict(protocol_statuses or {})
    active_status = guarded_protocols.get(proxy_mode)
    if isinstance(active_status, dict) and active_status.get('api_ok') is True:
        active_status = dict(active_status)
        active_status['api_ok'] = False
        active_status['api_transient'] = True
        active_status['api_message'] = guarded_status['api_status']
        active_status['tone'] = 'warn'
        active_status['label'] = 'Частично работает'
        active_status['details'] = guarded_status['api_status']
        guarded_protocols[proxy_mode] = active_status
    return guarded_status, guarded_protocols


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
    return (
        _status_snapshot_signature_impl(current_keys, _load_custom_checks()),
        proxy_mode,
        _load_app_runtime_mode(),
        bool(bot_ready),
        bool(bot_polling),
    )


def _build_status_snapshot(current_keys, force_refresh=False, background_checks=False):
    signature = _status_snapshot_signature(current_keys)
    now = time.time()
    if pool_probe_lock.locked():
        return _active_mode_status_snapshot(current_keys)
    cached = None if force_refresh else _status_cached_snapshot(status_snapshot_cache, signature, STATUS_CACHE_TTL, now=now)
    if cached is not None:
        return cached

    custom_checks = _load_custom_checks()
    route_states = _service_route_summary() if custom_checks else None
    key_probe_cache = _load_key_probe_cache()
    protocols = {}
    for key_name, key_value in _ordered_protocol_items(current_keys):
        try:
            if key_name == proxy_mode:
                protocols[key_name] = _protocol_status_for_key(
                    key_name,
                    key_value,
                    custom_checks=custom_checks,
                    route_states=route_states,
                    key_probe_cache=key_probe_cache,
                    background_checks=background_checks,
                )
                _store_active_mode_protocol_status(current_keys, protocols[key_name])
            else:
                protocols[key_name] = _cached_protocol_status_for_key(
                    key_name,
                    key_value,
                    custom_checks=custom_checks,
                    key_probe_cache=key_probe_cache,
                    route_states=route_states,
                )
        except Exception as exc:
            _write_runtime_log(f'Ошибка проверки ключа {key_name}: {exc}')
            protocols[key_name] = _status_protocol_error(exc)

    snapshot = {
        'web': _build_web_status(current_keys, protocols=protocols),
        'protocols': protocols,
    }
    return _status_store_snapshot(status_snapshot_cache, signature, snapshot, now=now)


def _active_mode_status_snapshot(current_keys, background_checks=False, include_route_details=False):
    return _active_mode_status_snapshot_from_base(
        current_keys,
        None,
        background_checks=background_checks,
        include_route_details=include_route_details,
    )


def _active_mode_status_snapshot_from_base(
    current_keys,
    base_snapshot=None,
    *,
    background_checks=False,
    include_route_details=False,
):
    pool_locked = pool_probe_lock.locked()
    cached = base_snapshot if isinstance(base_snapshot, dict) else _cached_status_snapshot(current_keys)
    if cached is not None and isinstance(cached, dict):
        protocols = dict(cached.get('protocols') or {})
    else:
        protocols = _placeholder_protocol_statuses(current_keys)
    if include_route_details:
        custom_checks = _load_custom_checks()
        route_states = _service_route_summary() if custom_checks else None
    else:
        custom_checks = ()
        route_states = None
    if not pool_locked and (include_route_details or cached is None):
        key_probe_cache = None
        light_key_probe_cache = None
        light_youtube_proto = None
        for key_name, key_value in _ordered_protocol_items(current_keys):
            if key_name == proxy_mode:
                continue
            try:
                if include_route_details:
                    if key_probe_cache is None:
                        key_probe_cache = _load_key_probe_cache()
                    protocols[key_name] = _cached_protocol_status_for_key(
                        key_name,
                        str(key_value or ''),
                        custom_checks=custom_checks,
                        key_probe_cache=key_probe_cache,
                        allow_youtube_confirm=False,
                        route_states=route_states,
                    )
                else:
                    if light_key_probe_cache is None:
                        light_key_probe_cache = _load_light_key_probe_cache()
                    if light_youtube_proto is None:
                        light_youtube_proto = _light_youtube_route_protocol()
                    protocols[key_name] = _light_cached_protocol_status_for_key(
                        key_name,
                        key_value,
                        key_probe_cache=light_key_probe_cache,
                        youtube_proto=light_youtube_proto,
                    )
            except Exception as exc:
                _write_runtime_log(f'Ошибка восстановления кешированного статуса {key_name}: {exc}')

    if proxy_mode in current_keys:
        try:
            cached_active = _cached_active_mode_protocol_status(current_keys) if pool_locked else None
            if cached_active is not None:
                active_status = cached_active
                if not include_route_details:
                    active_status = _status_merge_light_status_with_cached_services(
                        active_status,
                        protocols.get(proxy_mode),
                        _load_custom_checks(),
                        required_services=_light_required_services_for_protocol(
                            proxy_mode,
                            youtube_proto=_light_youtube_route_protocol(),
                        ),
                    )
            elif pool_locked:
                if include_route_details:
                    active_status = _cached_protocol_status_for_key(
                        proxy_mode,
                        current_keys.get(proxy_mode, ''),
                        custom_checks=custom_checks,
                        allow_youtube_confirm=False,
                        route_states=route_states,
                    )
                else:
                    active_status = _light_cached_protocol_status_for_key(
                        proxy_mode,
                        current_keys.get(proxy_mode, ''),
                        key_probe_cache=_load_light_key_probe_cache(),
                        youtube_proto=_light_youtube_route_protocol(),
                    )
            else:
                if include_route_details:
                    active_status = _protocol_status_for_key(
                        proxy_mode,
                        current_keys.get(proxy_mode, ''),
                        custom_checks=custom_checks,
                        route_states=route_states,
                        background_checks=background_checks,
                    )
                else:
                    active_status = _light_active_protocol_status_for_key(
                        proxy_mode,
                        current_keys.get(proxy_mode, ''),
                        background_checks=background_checks,
                    )
                if not include_route_details:
                    previous_status = protocols.get(proxy_mode)
                    if isinstance(previous_status, dict) and previous_status.get('custom'):
                        active_status = _status_merge_light_status_with_cached_services(
                            active_status,
                            previous_status,
                            _load_custom_checks(),
                            required_services=_light_required_services_for_protocol(
                                proxy_mode,
                                youtube_proto=_light_youtube_route_protocol(),
                            ),
                        )
                _store_active_mode_protocol_status(current_keys, active_status)
            protocols[proxy_mode] = active_status
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


def _cached_status_snapshot(current_keys):
    signature = _status_snapshot_signature(current_keys)
    cached = _status_cached_snapshot(
        status_snapshot_cache,
        signature,
        STATUS_CACHE_TTL,
    )
    if cached is not None and not _status_snapshot_has_custom_services(cached):
        try:
            if _load_custom_checks():
                snapshot = _placeholder_status_snapshot(current_keys, include_pool_details=True)
                return _status_store_snapshot(status_snapshot_cache, signature, snapshot, now=time.time())
        except Exception as exc:
            _write_runtime_log(f'Unable to restore cached custom service statuses: {exc}')
    if cached is not None and _status_snapshot_has_pending_check(cached):
        try:
            snapshot = _active_mode_status_snapshot_from_base(current_keys, cached)
            return _status_store_snapshot(status_snapshot_cache, signature, snapshot, now=time.time())
        except Exception as exc:
            _write_runtime_log(f'Unable to replace pending status cache with light snapshot: {exc}')
    return cached


def _stale_status_snapshot(current_keys):
    signature = _status_snapshot_signature(current_keys)
    if status_snapshot_cache.get('signature') != signature:
        return None
    snapshot = status_snapshot_cache.get('data')
    return snapshot if isinstance(snapshot, dict) else None


def _status_snapshot_has_pending_check(snapshot):
    if not isinstance(snapshot, dict):
        return False
    try:
        return web_form_blocks.status_refresh_pending(
            snapshot.get('web') or {},
            snapshot.get('protocols') or {},
            False,
        )
    except Exception:
        return False


def _status_snapshot_has_custom_services(snapshot):
    protocols = (snapshot or {}).get('protocols') if isinstance(snapshot, dict) else {}
    return any(
        isinstance(status, dict) and bool(status.get('custom'))
        for status in (protocols or {}).values()
    )


def _active_mode_status_signature(current_keys):
    return (
        _status_active_mode_signature(proxy_mode, current_keys, _load_custom_checks()),
        _load_app_runtime_mode(),
        bool(bot_polling),
    )


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
        'api_status': web_status_runtime.telegram_api_refresh_message(),
        'socks_details': '',
        'fallback_reason': _last_proxy_disable_reason(),
    }


def _placeholder_status_snapshot(current_keys, include_pool_details=True):
    if not include_pool_details:
        return _active_mode_status_snapshot_from_base(
            current_keys,
            _placeholder_status_snapshot(current_keys, include_pool_details=True),
        )
    protocols = _placeholder_protocol_statuses(current_keys)
    key_probe_cache = _load_key_probe_cache()
    custom_checks = _load_custom_checks()
    route_states = _service_route_summary() if custom_checks else None
    for key_name, key_value in _ordered_protocol_items(current_keys):
        if not str(key_value or '').strip():
            continue
        protocols[key_name] = _cached_protocol_status_for_key(
            key_name,
            key_value,
            custom_checks=custom_checks,
            key_probe_cache=key_probe_cache,
            allow_youtube_confirm=False,
            route_states=route_states,
        )
    active_key = (current_keys or {}).get(proxy_mode, '')
    if active_key:
        cached_active = _cached_active_mode_protocol_status(current_keys)
        if cached_active is not None:
            protocols[proxy_mode] = _status_merge_light_status_with_cached_services(
                cached_active,
                protocols.get(proxy_mode),
                custom_checks,
                required_services=_light_required_services_for_protocol(
                    proxy_mode,
                    youtube_proto=_light_youtube_route_protocol(),
                ),
            )
        else:
            probe = _load_key_probe_cache().get(_hash_key(active_key), {})
            if isinstance(probe, dict) and ('tg_ok' in probe or 'yt_ok' in probe):
                protocols[proxy_mode] = _cached_protocol_status_for_key(
                    proxy_mode,
                    active_key,
                    custom_checks=custom_checks,
                    key_probe_cache={_hash_key(active_key): probe},
                    allow_youtube_confirm=False,
                    route_states=route_states,
                )
    return {
        'web': _build_web_status(current_keys, protocols=protocols),
        'protocols': protocols,
    }


def _refresh_status_caches_async(current_keys, active_only=False):
    if pool_probe_lock.locked():
        return
    try:
        if _read_web_command_state_file().get('running') or _shared_command_job_running(source='web'):
            return
    except Exception:
        pass
    if not active_only and _background_task_economy_mode():
        active_only = True
    signature = _status_snapshot_signature(current_keys)
    refresh_key = f'active:{signature}' if active_only else signature
    now = time.time()
    with status_refresh_lock:
        if refresh_key in status_refresh_in_progress:
            return
        last_refresh = max(
            float(status_refresh_last_started_at.get(refresh_key) or 0.0),
            float(status_refresh_last_finished_at.get(refresh_key) or 0.0),
        )
        cached_snapshot = status_snapshot_cache.get('data')
        refresh_interval = (
            STATUS_REFRESH_PENDING_MIN_INTERVAL_SECONDS
            if _status_snapshot_has_pending_check(cached_snapshot)
            else STATUS_REFRESH_MIN_INTERVAL_SECONDS
        )
        if (
            last_refresh and
            now - last_refresh < refresh_interval and
            status_snapshot_cache.get('signature') == signature and
            isinstance(cached_snapshot, dict)
        ):
            return
        status_refresh_in_progress.add(refresh_key)
        status_refresh_last_started_at[refresh_key] = now

    if not _background_task_allowed('status refresh', task_class='light' if active_only else 'normal'):
        with status_refresh_lock:
            status_refresh_in_progress.discard(refresh_key)
            status_refresh_last_finished_at[refresh_key] = time.time()
        return

    def worker():
        _record_memory_timeline(
            'status refresh started',
            marker='status_refresh_start',
            extra={'status_refresh_count': len(status_refresh_in_progress)},
            force=True,
        )
        try:
            if active_only:
                snapshot = _active_mode_status_snapshot(current_keys, background_checks=True)
                _status_store_snapshot(status_snapshot_cache, signature, snapshot, now=time.time())
            else:
                _build_status_snapshot(current_keys, force_refresh=True, background_checks=True)
        except Exception as exc:
            _write_runtime_log(f'Ошибка фонового обновления статусов: {exc}')
        finally:
            with status_refresh_lock:
                status_refresh_in_progress.discard(refresh_key)
                status_refresh_last_finished_at[refresh_key] = time.time()
                for cache in (status_refresh_last_started_at, status_refresh_last_finished_at):
                    for old_signature in list(cache):
                        if old_signature != refresh_key:
                            cache.pop(old_signature, None)
            _record_memory_timeline(
                'status refresh finished',
                marker='status_refresh_finish',
                extra={'status_refresh_count': len(status_refresh_in_progress)},
                force=True,
            )

    threading.Thread(target=worker, daemon=True).start()


def _probe_all_pool_keys_async(stale_only=True, max_keys=KEY_PROBE_MAX_PER_RUN, scope='manual_all'):
    """Запускает безопасную фоновую проверку пула через временный xray."""
    if _has_pool_probe_resume_payload():
        return _resume_cancelled_pool_probe('ручного запуска')
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
            redact_text=_redact_sensitive_text,
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
        apply_service_route=_apply_service_route,
        apply_service_profile=_apply_service_profile,
        resolve_route_intersections=_resolve_route_intersections,
        service_routes_payload=_web_service_routes_payload,
        record_event=_record_event,
        install_verify=False,
    )
    if pool_enabled:
        context.update(web_post_actions.pool_action_context(
            append_custom_checks_to_unblock_list=_append_custom_checks_to_unblock_list,
            unblock_route_for_key_type=_unblock_route_for_key_type,
            add_custom_check=_add_custom_check,
            delete_custom_check=_delete_custom_check,
            web_custom_checks=_web_custom_checks,
            load_current_keys=_load_current_keys,
            refresh_status_caches_async=_refresh_status_caches_async,
            web_pool_snapshot=_web_pool_snapshot,
            get_pool_probe_progress=_get_pool_probe_progress,
            has_pool_probe_resume_payload=_has_pool_probe_resume_payload,
            probe_all_pool_keys_async=_probe_all_pool_keys_async,
            pool_keys_for_proto=_pool_keys_for_proto,
            probe_pool_keys_background=_probe_pool_keys_background,
            pause_pool_probe_for_apply=_pause_pool_probe_for_apply,
            probe_applied_pool_key_services=_probe_applied_pool_key_services,
            cancel_pool_probe=_cancel_pool_probe,
            resume_cancelled_pool_probe=_resume_cancelled_pool_probe,
            add_keys_to_pool=_add_keys_to_pool,
            import_keys_to_pools=_import_keys_to_pools,
            delete_pool_key=_delete_pool_key,
            load_key_pools=_load_key_pools,
            hash_key=_hash_key,
            set_active_key=_set_active_key,
            audit_key_switch=_audit_key_switch,
            schedule_youtube_key_apply_prefetch=_schedule_youtube_key_apply_prefetch,
            clear_pool=_clear_pool,
            fetch_keys_from_subscription=_fetch_keys_from_subscription,
            add_subscription_keys_to_pool=_key_pool_store().add_subscription_keys_to_pool,
            add_subscription_keys_to_pool_saved=_add_subscription_keys_to_pool,
            import_subscription_keys_to_pools=_import_subscription_keys_to_pools,
            subscription_keys_for_protocol=_subscription_runtime().subscription_keys_for_protocol,
            subscription_record=_subscription_record,
            save_subscription_record=_update_subscription_record,
            save_key_pools=_save_key_pools,
            pool_apply_lock=pool_apply_lock,
            custom_checks_enabled=True,
            pool_actions_enabled=True,
        ))
    else:
        context.update(web_post_actions.pool_action_context(
            custom_checks_enabled=False,
            pool_actions_enabled=False,
        ))
    return context


def _web_get_context(handler):
    pool_enabled = _app_mode_pool_enabled()
    refresh_status_caches = (
        _refresh_status_caches_async if pool_enabled else
        (lambda current_keys: _refresh_status_caches_async(current_keys, active_only=True))
    )
    return {
        'build_form': handler._build_form,
        'build_protocol_panel': handler._build_protocol_panel,
        'build_protocol_check_panel': handler._build_protocol_check_panel,
        'build_style_asset': handler._build_style_asset,
        'build_script_asset': handler._build_script_asset,
        'consume_flash_message': _consume_web_flash_message,
        'load_current_keys': _load_current_keys,
        'cached_status_snapshot': _cached_status_snapshot,
        'stale_status_snapshot': _stale_status_snapshot,
        'placeholder_status_snapshot': _placeholder_status_snapshot,
        'active_mode_status_snapshot': _active_mode_status_snapshot,
        'refresh_status_caches_async': refresh_status_caches,
        'pool_probe_locked': pool_probe_lock.locked,
        'get_status_api_cache': _get_web_status_api_cache,
        'store_status_api_cache': _store_web_status_api_cache,
        'status_api_cache_ttl': WEB_STATUS_API_CACHE_TTL,
        'get_pools_api_cache': _get_web_pools_api_cache,
        'store_pools_api_cache': _store_web_pools_api_cache,
        'pools_api_cache_ttl': WEB_POOLS_API_CACHE_TTL,
        'pools_api_build_lock': web_pools_api_build_lock,
        'get_web_command_state': _get_web_command_state,
        'update_status_snapshot': _update_status_snapshot,
        'event_history_snapshot': _event_history_snapshot,
        'event_history_payload': _event_history_payload,
        'router_metrics_snapshot': _router_metrics_snapshot,
        'route_intersections_snapshot': _route_intersections_snapshot,
        'service_routes_payload': _web_service_routes_payload,
        'unblock_list_payload': _web_unblock_list_payload,
        'telegram_call_learning_snapshot': _telegram_call_learning_snapshot,
        'router_health_snapshot': _router_health_snapshot,
        'bot_ready': lambda: bool(bot_ready),
        'pool_enabled': pool_enabled,
        'get_pool_probe_progress': _get_pool_probe_progress,
        'has_pool_probe_resume_payload': _has_pool_probe_resume_payload,
        'web_pools_payload': _web_pools_payload,
        'web_pool_snapshot': _web_pool_snapshot,
        'pool_status_summary': _pool_status_summary,
        'web_custom_checks': _web_custom_checks,
        'time_provider': time.time,
        'static_dir': STATIC_DIR,
        'service_icons_enabled': True,
        'web_background_payload': lambda: web_background.store_for_unblock_dir().payload(),
        'web_background_file_path': lambda: web_background.store_for_unblock_dir().file_path(),
    }


def _web_background_form_value(data, name, default=''):
    values = data.get(name, []) if isinstance(data, dict) else []
    return str(values[0] if values else default)


def _handle_web_background_post(handler, path):
    store = web_background.store_for_unblock_dir()
    if path == '/api/ui_background/upload':
        if not handler._ensure_csrf_allowed():
            return True
        try:
            payload = store.upload(
                handler.rfile,
                handler.headers.get('Content-Length', ''),
                handler.headers.get('Content-Type', ''),
            )
        except ValueError as exc:
            handler._send_json({'ok': False, 'error': str(exc)}, status=400)
            return True
        except OSError:
            handler._send_json({'ok': False, 'error': 'Не удалось сохранить фон на накопителе роутера.'}, status=507)
            return True
        handler._send_json(payload, status=200)
        return True
    if path == '/api/ui_background/delete':
        if not handler._ensure_csrf_allowed():
            return True
        try:
            handler._send_json(store.delete(), status=200)
        except OSError:
            handler._send_json({'ok': False, 'error': 'Не удалось удалить фон с накопителя роутера.'}, status=500)
        return True
    if path != '/api/ui_background/settings':
        return False
    try:
        data = handler._read_post_data()
    except ValueError as exc:
        handler._send_json({'ok': False, 'error': str(exc)}, status=400)
        return True
    if not handler._ensure_csrf_allowed(data):
        return True
    try:
        payload = store.update_settings(
            _web_background_form_value(data, 'enabled'),
            _web_background_form_value(data, 'shade'),
            _web_background_form_value(data, 'panel_transparency'),
        )
        handler._send_json(payload, status=200)
    except OSError:
        handler._send_json({'ok': False, 'error': 'Не удалось сохранить настройку фона.'}, status=507)
    return True


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
    subscription_settings = _subscription_public_settings()
    _tabs_html, panel_html = web_form_blocks.render_light_protocol_tabs_and_panels(
        protocol_sections,
        current_keys,
        protocol_statuses,
        csrf_input_html,
        key_pools=key_pools,
        telegram_icon_html=_telegram_icon_html,
        youtube_icon_html=_youtube_icon_html,
        subscription_settings=subscription_settings,
        active_protocol=protocol,
        enable_key_pool=True,
        enable_custom_checks=True,
        pool_probe_pending=bool(_get_pool_probe_progress().get('running')),
    )
    return panel_html


def _web_protocol_check_html(protocol, current_keys, protocol_statuses, csrf_input_html):
    protocol_sections = [section for section in web_form_blocks.PROTOCOL_SECTIONS if section[0] == protocol]
    if not protocol_sections:
        raise ValueError('Неизвестный протокол')
    _key_name, title, _rows, _placeholder = protocol_sections[0]
    custom_checks = _load_custom_checks()
    standalone_checks = _standalone_custom_checks_light(custom_checks)
    custom_checks_html = ''
    if standalone_checks:
        custom_checks_html = _key_pool_web().web_custom_checks_html(
            standalone_checks,
            _service_icon_html,
            csrf_input_html=csrf_input_html,
            empty_message='',
        )
    return _web_pool_form_blocks().render_protocol_check_content(
        key_name=protocol,
        title=title,
        status_info=(protocol_statuses or {}).get(protocol) or _status_empty_protocol_status(),
        custom_presets_html='',
        custom_checks_html=custom_checks_html,
        route_tools_html=_deferred_route_tools_html(),
        csrf_input_html=csrf_input_html,
        enable_key_pool=True,
        enable_custom_checks=True,
        pool_probe_pending=bool(_get_pool_probe_progress().get('running')),
    )


def _web_custom_checks_light(custom_checks):
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
        for check in (custom_checks or [])
        if isinstance(check, dict)
    ]


def _web_pool_form_context(current_keys, protocol_statuses, csrf_input_html, status, pool_probe_pending, progress):
    key_pools = _ensure_current_keys_in_pools(current_keys)
    pool_counts = {proto: [None] * len(key_pools.get(proto, []) or []) for proto in POOL_PROTOCOL_ORDER}
    subscription_settings = _subscription_public_settings()
    # Initial pool rows are hydrated by /api/pools; avoid rendering full probe details twice.
    custom_checks = _load_custom_checks()
    protocol_tabs_html, protocol_panels_html = web_form_blocks.render_light_protocol_tabs_and_panels(
        web_form_blocks.PROTOCOL_SECTIONS,
        current_keys,
        protocol_statuses,
        csrf_input_html,
        key_pools=pool_counts,
        telegram_icon_html=_telegram_icon_html,
        youtube_icon_html=_youtube_icon_html,
        subscription_settings=subscription_settings,
        active_protocol=_default_web_protocol(),
        enable_key_pool=True,
        enable_custom_checks=True,
        pool_probe_pending=pool_probe_pending,
    )
    pool_summary = _light_pool_summary_with_cache_fallback(
        current_keys,
        key_pools,
        custom_checks,
    )
    return {
        'custom_checks_json': json.dumps(_web_custom_checks_light(custom_checks), ensure_ascii=False),
        'pool_summary': pool_summary,
        'pool_summary_note': web_form_blocks.pool_summary_note_with_progress(
            pool_summary['note'],
            pool_probe_pending,
            progress,
            _pool_probe_progress_label,
        ),
        'protocol_panels_html': protocol_panels_html,
        'protocol_tabs_html': protocol_tabs_html,
        'topbar_status_text': web_form_blocks.pool_probe_topbar_text(
            pool_probe_pending,
            progress,
            _pool_probe_progress_label,
            status['api_status'],
        ),
    }


def _web_simple_form_context(current_keys, protocol_statuses, csrf_input_html, status):
    tabs = []
    panels = []
    current_keys = current_keys or {}
    protocol_statuses = protocol_statuses or {}
    for index, (key_name, title, rows, placeholder) in enumerate(web_form_blocks.PROTOCOL_SECTIONS):
        active = index == 0
        active_class = ' active' if active else ''
        safe_key_name = html.escape(key_name, quote=True)
        safe_title = html.escape(title)
        safe_value = html.escape(current_keys.get(key_name, '') or '')
        safe_placeholder = html.escape(placeholder)
        status_info = protocol_statuses.get(key_name) or {}
        safe_tone = html.escape(status_info.get('tone', 'empty'), quote=True)
        safe_label = html.escape(status_info.get('label', ''), quote=True)
        safe_details = html.escape(str(status_info.get('details', '') or '').strip().rstrip('.'))
        tab_count = 1 if safe_value else 0
        tabs.append(f'''<button type="button" class="seg-tab protocol-tab{active_class}" data-protocol-target="{safe_key_name}">
                    <span>{safe_title}</span>
                    <span class="tab-count">{tab_count}</span>
                </button>''')
        panels.append(f'''<section class="protocol-workspace{active_class}" data-protocol-card="{safe_key_name}" data-protocol-panel="{safe_key_name}">
        <div class="workspace-head">
            <div>
                <h2 class="inline-page-title"><span class="title-kicker">Ключи</span><span>{safe_title}</span></h2>
                <p class="key-status-note" data-protocol-status-details>{safe_details}</p>
            </div>
            <span class="key-status-wrap"><span class="key-status-icons" data-protocol-status-icons></span><span class="key-status-badge key-status-{safe_tone}" data-protocol-status-label>{safe_label}</span></span>
        </div>
        <div class="protocol-subview active" data-subview="key">
            <form method="post" action="/install" data-async-action="install" class="key-editor-form">
                {csrf_input_html}
                <input type="hidden" name="type" value="{safe_key_name}">
                <label class="field-label">Активный ключ {safe_title}</label>
                <textarea name="key" rows="{int(rows)}" placeholder="{safe_placeholder}" required data-key-textarea>{safe_value}</textarea>
                <div class="form-actions">
                    <button type="submit">Сохранить {safe_title}</button>
                </div>
            </form>
        </div>
    </section>''')
    return {
        'custom_checks_json': '[]',
        'pool_summary': {'active_text': '', 'note': ''},
        'pool_summary_note': '',
        'protocol_panels_html': ''.join(panels),
        'protocol_tabs_html': ''.join(tabs),
        'topbar_status_text': status['api_status'],
    }


class KeyInstallHTTPRequestHandler(WebRequestMixin, BaseHTTPRequestHandler):
    csrf_error_as_json = True
    allow_authenticated_external = True
    quiet_log_prefixes = (
        '/api/status',
        '/api/pool_probe',
        '/api/command_state',
        '/api/update_status',
        '/api/event_history',
        '/api/router_metrics',
        '/api/telegram_call_learning',
        '/api/route_intersections',
        '/api/protocol_check_panel',
        '/static/',
    )
    local_client_checker = staticmethod(_web_is_local_client)
    web_auth_token_getter = staticmethod(lambda: _web_config_auth_token(config))
    web_auth_user_getter = staticmethod(lambda: _web_config_auth_user(config))
    flash_message_setter = staticmethod(_set_web_flash_message)

    def _build_style_asset(self):
        return _web_form_template().load_static_asset(
            os.path.join(STATIC_DIR, 'app.css'),
            lambda: render_web_style_asset(TELEGRAM_SVG_B64=TELEGRAM_SVG_B64),
        )

    def _build_script_asset(self):
        return _web_form_template().load_static_asset(
            os.path.join(STATIC_DIR, 'app.js'),
            lambda: render_web_script_asset(
                TELEGRAM_SVG_B64=TELEGRAM_SVG_B64,
                YOUTUBE_SVG_B64=YOUTUBE_SVG_B64,
                csrf_token='',
                custom_checks_json='[]',
                initial_command_running='false',
                initial_status_pending='false',
            ),
        )

    def _build_form(self, message=''):
        app_runtime_mode = _load_app_runtime_mode()
        pool_enabled = _app_mode_pool_enabled(app_runtime_mode)
        command_state = _consume_web_command_state_for_render()
        current_keys = _load_current_keys()
        if pool_enabled:
            snapshot = _cached_status_snapshot(current_keys)
            status = snapshot['web'] if snapshot is not None else _placeholder_web_status_snapshot()
            protocol_statuses = snapshot['protocols'] if snapshot is not None else _placeholder_protocol_statuses(current_keys)
            current_pool_probe_progress = _get_pool_probe_progress()
            pool_probe_pending = (
                bool(current_pool_probe_progress.get('running')) and
                int(current_pool_probe_progress.get('total') or 0) > 0
            )
            if snapshot is None:
                snapshot = _placeholder_status_snapshot(current_keys, include_pool_details=False)
                status = snapshot['web']
                protocol_statuses = snapshot['protocols']
                if not pool_probe_pending:
                    _refresh_status_caches_async(current_keys, active_only=True)
        else:
            snapshot = _cached_status_snapshot(current_keys)
            if snapshot is None:
                snapshot = _placeholder_status_snapshot(current_keys, include_pool_details=False)
            status = snapshot['web']
            protocol_statuses = snapshot['protocols']
            current_pool_probe_progress = {}
            pool_probe_pending = False
        status, protocol_statuses = _web_render_status_with_polling_guard(status, protocol_statuses, app_runtime_mode)
        unblock_lists = _load_unblock_lists(with_content=False)
        status_refresh_pending = web_form_blocks.status_refresh_pending(status, protocol_statuses, pool_probe_pending)
        router_health = _router_health_snapshot(compact=True, sample_cpu=False)

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
            event_history_html='',
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
            router_health=router_health,
            socks_block=form_basics['socks_block'],
            start_button_label=start_button_label,
            status=status,
            topbar_status_text=pool_view['topbar_status_text'],
            unblock_panels_html=unblock_panels_html,
            unblock_tabs_html=unblock_tabs_html,
            enable_custom_checks=pool_enabled,
            enable_key_pool=pool_enabled,
            enable_telegram=telegram_enabled,
            bot_ready=bool(bot_ready),
            bot_polling=bool(bot_polling),
        )

    def _build_protocol_panel(self, protocol):
        app_runtime_mode = _load_app_runtime_mode()
        if not _app_mode_pool_enabled(app_runtime_mode):
            raise ValueError('Пул ключей отключён в текущем режиме программы')
        current_keys = _load_current_keys()
        snapshot = _cached_status_snapshot(current_keys)
        if snapshot is None:
            snapshot = _placeholder_status_snapshot(current_keys, include_pool_details=False)
            if not pool_probe_lock.locked():
                _refresh_status_caches_async(current_keys, active_only=True)
        csrf_token = self._get_or_create_csrf_token()
        csrf_input_html = web_form_blocks.render_csrf_input(csrf_token)
        return _web_protocol_panel_html(protocol, current_keys, snapshot.get('protocols', {}), csrf_input_html)

    def _build_protocol_check_panel(self, protocol):
        app_runtime_mode = _load_app_runtime_mode()
        if not _app_mode_pool_enabled(app_runtime_mode):
            raise ValueError('Пул ключей отключён в текущем режиме программы')
        current_keys = _load_current_keys()
        snapshot = _cached_status_snapshot(current_keys)
        if snapshot is None:
            snapshot = _placeholder_status_snapshot(current_keys, include_pool_details=False)
            if not pool_probe_lock.locked():
                _refresh_status_caches_async(current_keys, active_only=True)
        csrf_token = self._get_or_create_csrf_token()
        csrf_input_html = web_form_blocks.render_csrf_input(csrf_token)
        return _web_protocol_check_html(protocol, current_keys, snapshot.get('protocols', {}), csrf_input_html)

    def do_GET(self):
        if not self._ensure_request_allowed():
            return
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if _update_maintenance_active():
            maintenance_status = update_status.read_update_status()
            if path == '/api/command_state':
                self._send_json(_update_maintenance_runtime().maintenance_command_state(maintenance_status))
            elif path == '/api/update_status':
                self._send_json(maintenance_status)
            elif path.startswith('/api/'):
                self._send_json({
                    'ok': False,
                    'updating': True,
                    'error': 'Функция временно приостановлена до завершения обновления.',
                }, status=503)
            elif path.startswith('/static/'):
                self._send_text_asset(
                    'Обновление выполняется.',
                    content_type='text/plain; charset=utf-8',
                    cache_seconds=0,
                )
            else:
                self._send_html(_update_maintenance_runtime().render_maintenance_page(
                    maintenance_status,
                    current_version=APP_VERSION_LABEL,
                ))
            return
        _update_maintenance_web_request_started()
        try:
            try:
                action = web_get_actions.dispatch(_web_get_context(self), path, parsed_url.query)
            except Exception as exc:
                if path.startswith('/api/'):
                    self._send_json({'error': str(exc)}, status=500)
                else:
                    self._send_html(f'<h1>500 Internal Server Error</h1><p>{html.escape(str(exc))}</p>', status=500)
                return
        finally:
            _update_maintenance_web_request_finished()
        if action is None:
            self._send_html('<h1>404 Not Found</h1>', status=404)
            return
        kind = action.get('kind')
        if kind == 'json':
            payload = action.get('payload', {})
            self._send_json(payload, status=action.get('status', 200))
        elif kind == 'json_text':
            self._send_text_asset(
                action.get('text', '{}'),
                content_type='application/json; charset=utf-8',
                cache_seconds=0,
            )
        elif kind == 'html':
            self._send_html(action.get('html', ''))
        elif kind == 'text':
            self._send_text_asset(
                action.get('text', ''),
                content_type=action.get('content_type', 'text/plain; charset=utf-8'),
                cache_seconds=action.get('cache_seconds', 0),
                asset_cache_key=path if path in ('/static/app.css', '/static/app.js') else '',
            )
        elif kind == 'png':
            self._send_png(action.get('path', ''))
        elif kind == 'file':
            self._send_binary_file(
                action.get('path', ''),
                action.get('content_type', 'application/octet-stream'),
                cache_control=action.get('cache_control', 'private, max-age=0, no-cache'),
            )
        else:
            self._send_html('<h1>404 Not Found</h1>', status=404)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        if not self._ensure_request_allowed():
            return
        path = urlparse(self.path).path
        if _update_maintenance_active():
            self._send_json({
                'ok': False,
                'updating': True,
                'error': 'Изменения временно запрещены до завершения обновления.',
            }, status=503)
            return
        _update_maintenance_web_request_started()
        try:
            if _handle_web_background_post(self, path):
                return
            try:
                data = self._read_post_data()
            except ValueError as exc:
                self._send_action_result(str(exc), success=False)
                return
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
        finally:
            _update_maintenance_web_request_finished()

def start_http_server():
    global web_httpd
    try:
        bind_host = _web_resolve_bind_host(routerip)
        class ReusableThreadingHTTPServer(ThreadingHTTPServer):
            allow_reuse_address = True
            # Several panels are loaded together; keep the kernel accept queue from
            # dropping an otherwise valid burst of browser requests.
            request_queue_size = 128

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


def _apply_reality_endpoint_override(key):
    key = str(key or '').strip()
    if not key or not REALITY_ENDPOINT_OVERRIDES:
        return key
    try:
        data = _parse_vless_key(key)
    except Exception:
        return key
    if str(data.get('security') or '').lower() != 'reality':
        return key
    address = str(data.get('address') or '').strip()
    override = REALITY_ENDPOINT_OVERRIDES.get(address.lower()) or reality_endpoint_runtime_overrides.get(address.lower())
    if not override:
        return key
    try:
        parsed = urlparse(key)
        host_part = f'[{override}]' if ':' in override and not override.startswith('[') else override
        netloc = f'{parsed.username}@{host_part}' if parsed.username else host_part
        if parsed.port:
            netloc = f'{netloc}:{parsed.port}'
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        if not any(name == 'sni' and value for name, value in query_pairs):
            query_pairs.append(('sni', address))
        return parsed._replace(netloc=netloc, query=urlencode(query_pairs, doseq=True)).geturl()
    except Exception:
        return key


def _vless_key_with_endpoint(key, endpoint, fallback_sni=''):
    key = str(key or '').strip()
    endpoint = str(endpoint or '').strip()
    if not key or not endpoint:
        return key
    parsed = urlparse(key)
    host_part = f'[{endpoint}]' if ':' in endpoint and not endpoint.startswith('[') else endpoint
    netloc = f'{parsed.username}@{host_part}' if parsed.username else host_part
    if parsed.port:
        netloc = f'{netloc}:{parsed.port}'
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if fallback_sni and not any(name == 'sni' and value for name, value in query_pairs):
        query_pairs.append(('sni', fallback_sni))
    return parsed._replace(netloc=netloc, query=urlencode(query_pairs, doseq=True)).geturl()


def _reality_endpoint_candidates(data, current_endpoint=''):
    seen = set()
    candidates = []

    def add(value):
        value = str(value or '').strip()
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            candidates.append(value)

    add(current_endpoint)
    add(data.get('address'))
    sni = str(data.get('sni') or data.get('host') or '').strip()
    if sni:
        add(sni)
        for address in _resolve_domain_ipv4_addresses(sni):
            add(address)
    return candidates[:REALITY_ENDPOINT_REPAIR_MAX_CANDIDATES]


def _set_reality_runtime_endpoint(address, endpoint):
    address = str(address or '').strip().lower()
    endpoint = str(endpoint or '').strip()
    if not address:
        return
    if endpoint and endpoint.lower() != address:
        reality_endpoint_runtime_overrides[address] = endpoint
    else:
        reality_endpoint_runtime_overrides.pop(address, None)


def _current_core_proxy_endpoint(outbound_tag):
    try:
        with open(CORE_PROXY_CONFIG_PATH, 'r', encoding='utf-8') as file:
            config_data = json.load(file)
        for outbound in config_data.get('outbounds', []):
            if outbound.get('tag') == outbound_tag:
                return str((outbound.get('settings', {}).get('vnext') or [{}])[0].get('address') or '').strip()
    except Exception:
        pass
    return ''


def _write_core_proxy_endpoint(outbound_tag, endpoint, server_name):
    with core_proxy_config_write_lock:
        with open(CORE_PROXY_CONFIG_PATH, 'r', encoding='utf-8') as file:
            config_data = json.load(file)
        changed = False
        for outbound in config_data.get('outbounds', []):
            if outbound.get('tag') != outbound_tag:
                continue
            vnext = outbound.get('settings', {}).get('vnext') or []
            if not vnext:
                continue
            reality_settings = outbound.get('streamSettings', {}).get('realitySettings', {})
            if vnext[0].get('address') != endpoint:
                vnext[0]['address'] = endpoint
                changed = True
            if server_name and reality_settings.get('serverName') != server_name:
                reality_settings['serverName'] = server_name
                changed = True
        if not changed:
            return False
        _write_json_file(CORE_PROXY_CONFIG_PATH, config_data)
        return True


def _probe_reality_endpoint_with_temp_xray(proto, key, endpoint, service='telegram'):
    port = REALITY_ENDPOINT_REPAIR_BASE_PORT + (1 if proto == 'vless2' else 0)
    data = _parse_vless_key(key)
    temp_key = _vless_key_with_endpoint(key, endpoint, data.get('sni') or data.get('host') or data.get('address') or '')
    temp_path = os.path.join(tempfile.gettempdir(), f'bypass-reality-repair-{proto}.json')
    temp_log_path = os.path.join(tempfile.gettempdir(), f'bypass-reality-repair-{proto}.log')
    keys = _load_current_keys()
    config_json = _builder_build_proxy_core_config(
        vmess_key=keys.get('vmess') or '',
        vless_key=temp_key if proto == 'vless' else keys.get('vless') or '',
        vless2_key=temp_key if proto == 'vless2' else keys.get('vless2') or '',
        shadowsocks_key=keys.get('shadowsocks') or '',
        trojan_key=keys.get('trojan') or '',
        ports={
            'vmess': localportvmess,
            'vmess_transparent': localportvmess_transparent,
            'vless': port if proto == 'vless' else localportvless,
            'vless_transparent': localportvless_transparent,
            'vless2': port if proto == 'vless2' else localportvless2,
            'vless2_transparent': localportvless2_transparent,
            'shadowsocks_bot': localportsh_bot,
            'trojan_bot': localporttrojan_bot,
        },
        error_log_path=temp_log_path,
        access_log_path='/dev/null',
        loglevel='warning',
        connectivity_check_domains=_service_catalog().CONNECTIVITY_CHECK_DOMAINS,
        include_vmess_transparent=True,
        include_tproxy_inbounds=False,
    )
    inbound_tag = 'in-vless' if proto == 'vless' else 'in-vless2'
    outbound_tag = 'proxy-vless' if proto == 'vless' else 'proxy-vless2'
    config_json['inbounds'] = [
        inbound for inbound in config_json.get('inbounds', [])
        if inbound.get('tag') == inbound_tag
    ]
    for inbound in config_json['inbounds']:
        inbound['listen'] = '127.0.0.1'
        inbound['port'] = port
    config_json['routing'] = {
        'domainStrategy': 'IPIfNonMatch',
        'rules': [{
            'type': 'field',
            'inboundTag': [inbound_tag],
            'outboundTag': outbound_tag,
        }],
    }
    with open(temp_path, 'w', encoding='utf-8') as file:
        json.dump(config_json, file, ensure_ascii=False, indent=2)
    validation = subprocess.run(
        ['/opt/sbin/xray', 'run', '-test', '-c', temp_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=8,
        check=False,
    )
    if validation.returncode != 0:
        return False
    log_file = open(temp_log_path, 'a', encoding='utf-8', errors='ignore')
    process = None
    try:
        process = subprocess.Popen(
            ['/opt/sbin/xray', 'run', '-c', temp_path],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        time.sleep(2)
        proxy_url = f'socks5h://127.0.0.1:{port}'
        if str(service or '').strip().lower() == 'youtube':
            ok, _message = _youtube_healthcheck().check_youtube_through_proxy(
                _check_http_through_proxy,
                proxy_url,
                urls=YOUTUBE_VLESS2_HEALTHCHECK_URLS,
                min_ok=YOUTUBE_VLESS2_HEALTHCHECK_MIN_OK,
                http_timeouts=(
                    YOUTUBE_VLESS2_FAILOVER_CHECK_CONNECT_TIMEOUT,
                    YOUTUBE_VLESS2_FAILOVER_CHECK_READ_TIMEOUT,
                ),
                http_retry_timeouts=(
                    YOUTUBE_VLESS2_FAILOVER_CHECK_CONNECT_TIMEOUT,
                    YOUTUBE_VLESS2_FAILOVER_CHECK_READ_TIMEOUT,
                ),
                retry_delay_seconds=POOL_PROBE_RETRY_DELAY_SECONDS,
                sleep=shutdown_requested.wait,
            )
        else:
            ok, _message = _check_telegram_api_through_proxy(
                proxy_url,
                connect_timeout=5,
                read_timeout=8,
                authenticated=False,
            )
        return bool(ok)
    finally:
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        try:
            log_file.close()
        except Exception:
            pass
        for path in (temp_path, temp_log_path):
            try:
                os.remove(path)
            except Exception:
                pass


def _repair_active_reality_endpoint(proto, failure_message='', service='telegram'):
    if not REALITY_ENDPOINT_REPAIR_ENABLED or proto not in ('vless', 'vless2'):
        return False
    keys = _load_current_keys()
    key = (keys.get(proto) or '').strip()
    if not key:
        return False
    try:
        data = _parse_vless_key(key)
    except Exception:
        return False
    if str(data.get('security') or '').strip().lower() != 'reality':
        return False
    outbound_tag = 'proxy-vless2' if proto == 'vless2' else 'proxy-vless'
    current_endpoint = _current_core_proxy_endpoint(outbound_tag)
    server_name = data.get('sni') or data.get('host') or data.get('address') or ''
    candidates = _reality_endpoint_candidates(data, current_endpoint=current_endpoint)
    if not candidates:
        return False
    service_name = 'YouTube' if str(service or '').strip().lower() == 'youtube' else 'Telegram'
    probe_field = 'yt_ok' if service_name == 'YouTube' else 'tg_ok'
    recent_ttl = (
        YOUTUBE_VLESS2_FAILOVER_RECENT_SUCCESS_TTL
        if service_name == 'YouTube'
        else AUTO_FAILOVER_RECENT_SUCCESS_TTL
    )
    try:
        active_probe = _load_key_probe_cache().get(_hash_key(key), {})
    except Exception:
        active_probe = {}
    if _recent_probe_ok(active_probe, probe_field, recent_ttl):
        _write_runtime_log(
            f'Reality endpoint repair skipped for {_pool_proto_label(proto)}: recent {service_name} success is still fresh.'
        )
        return False
    if _vless_traffic_guard_active(
        f'{_pool_proto_label(proto)} endpoint repair',
        log=True,
        hold_seconds=YOUTUBE_STREAM_GUARD_FAILOVER_HOLD_SECONDS,
    ):
        return False
    _write_runtime_log(
        f'Reality endpoint repair: probing {len(candidates)} endpoints for {_pool_proto_label(proto)} after {service_name} failure.'
    )
    for endpoint in candidates:
        if _probe_reality_endpoint_with_temp_xray(proto, key, endpoint, service=service):
            _set_reality_runtime_endpoint(data.get('address'), endpoint)
            if _write_core_proxy_endpoint(outbound_tag, endpoint, server_name):
                ok, message = _restart_core_proxy_after_validation()
                if not ok:
                    _write_runtime_log(f'Reality endpoint repair: core restart failed after selecting {endpoint}: {message}')
                    return False
            _write_runtime_log(f'Reality endpoint repair: {_pool_proto_label(proto)} restored via endpoint {endpoint}.')
            return True
    _write_runtime_log(
        f'Reality endpoint repair: no endpoint restored {_pool_proto_label(proto)}. Last {service_name} failure: {failure_message}'
    )
    return False


def _build_v2ray_config(vmess_key=None, vless_key=None, vless2_key=None, shadowsocks_key=None, trojan_key=None):
    return _builder_build_proxy_core_config(
        vmess_key=vmess_key,
        vless_key=_apply_reality_endpoint_override(vless_key),
        vless2_key=_apply_reality_endpoint_override(vless2_key),
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
            'shadowsocks_tproxy': localportsh_tproxy,
            'vmess_tproxy': localportvmess_tproxy,
            'vless_tproxy': localportvless_tproxy,
            'vless2_tproxy': localportvless2_tproxy,
            'trojan_tproxy': localporttrojan_tproxy,
        },
        error_log_path=CORE_PROXY_ERROR_LOG,
        access_log_path='/dev/null',
        loglevel='warning',
        connectivity_check_domains=_service_catalog().CONNECTIVITY_CHECK_DOMAINS,
        include_vmess_transparent=True,
    )


def _write_v2ray_config(vmess_key=None, vless_key=None, vless2_key=None, shadowsocks_key=None, trojan_key=None):
    config_json = _build_v2ray_config(vmess_key, vless_key, vless2_key, shadowsocks_key, trojan_key)
    os.makedirs(CORE_PROXY_CONFIG_DIR, exist_ok=True)
    with core_proxy_config_write_lock:
        _write_json_file(CORE_PROXY_CONFIG_PATH, config_json)


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
        _sanitize_xray26_compat_files()
        ok, message = _restart_core_proxy_after_validation()
        if not ok:
            _write_runtime_log(f'Core proxy startup validation failed: {message}')
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
        _save_proxy_mode(fallback_mode)
        return

    api_status = check_telegram_api(retries=0, retry_delay=0, connect_timeout=8, read_timeout=10)
    if not api_status.startswith('✅'):
        _write_runtime_log(f'Прокси-режим {proxy_mode} не подтверждён при старте: {api_status}')


def _run_telegram_polling_loop():
    global bot_polling
    while not shutdown_requested.is_set():
        if _update_maintenance_active():
            bot_polling = False
            shutdown_requested.wait(0.5)
            continue
        try:
            if proxy_mode in PROXY_LOCAL_PORTS:
                preflight_ok, preflight_message = _check_telegram_api_through_proxy(
                    proxy_settings.get(proxy_mode),
                    connect_timeout=max(2.0, AUTO_FAILOVER_CHECK_CONNECT_TIMEOUT),
                    read_timeout=max(3.0, AUTO_FAILOVER_CHECK_READ_TIMEOUT),
                    authenticated=True,
                )
                if not preflight_ok:
                    bot_polling = False
                    _mark_active_telegram_failure(preflight_message)
                    _memory_cleanup('telegram polling preflight failed', clear_status=False, log=False)
                    shutdown_requested.wait(10)
                    continue
            bot_polling = True
            bot.infinity_polling(timeout=60, long_polling_timeout=50)
        except Exception as err:
            bot_polling = False
            _write_runtime_log(err)
            if _is_telegram_connectivity_error(err):
                _mark_active_telegram_failure(err)
            _reset_telegram_http_session('polling error')
            _memory_cleanup('telegram polling error', force=True, clear_status=False)
            if shutdown_requested.is_set():
                break
            if _is_polling_conflict(err):
                _write_runtime_log('Обнаружен конфликт getUpdates, ожидание перед повторной попыткой 65 секунд')
                time.sleep(65)
            else:
                time.sleep(5)
        else:
            if shutdown_requested.is_set():
                break
            # A clean return can be the boundary between long-poll requests.
            # Keep the last healthy state until a preflight or polling error says otherwise.
            shutdown_requested.wait(2)


def main():
    if not _acquire_main_instance_lock():
        return
    _daemonize_process()
    _register_signal_handlers()
    _write_runtime_log('main() entered', mode='w')
    runtime_mode = _load_app_runtime_mode()
    pool_enabled = _app_mode_pool_enabled(runtime_mode)
    telegram_enabled = _app_mode_telegram_enabled(runtime_mode)
    _write_runtime_log(f'app runtime mode: {runtime_mode}')
    _cleanup_pool_probe_runtime_light(kill_processes=True)
    if not (os.path.isfile(UDP_POLICY_CONFIG_PATH) and os.path.isfile(CALL_SIGNAL_ROUTES_PATH)):
        _sync_udp_policy_config()
    if pool_enabled:
        _start_youtube_edge_prefetch_thread()
        _start_telegram_call_learning_auto_thread()
    start_http_server()
    _restart_core_proxy_at_startup()
    _mark_bot_ready_from_autostart()
    _restore_startup_proxy_mode()
    if pool_enabled:
        _ensure_current_keys_in_pools()
        _load_persisted_pool_probe_resume()
    _start_background_maintenance_thread()
    if telegram_enabled:
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
