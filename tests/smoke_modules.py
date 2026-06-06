from pathlib import Path
from io import BytesIO
import base64
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import types as py_types

# ruff: noqa: E402


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import key_pool_web
import key_pool_store
import app_version
import app_runtime_mode
import router_health_runtime
import xray_compat_runtime
import telegram_pool_ui
import web_get_actions
import web_command_state
import web_commands_runtime
import web_form_blocks
import web_form_template
import web_http_common
import web_pool_form_blocks
import web_route_tools_runtime
import web_status_builder
import web_template_styles
import web_template_scripts
import web_post_actions
import web_status_runtime
import telegram_confirm
import telegram_auth_state
import telegram_jobs
import telegram_message_flow
import telegram_install_ui
import telegram_key_ui
import telegram_info_runtime
import pool_probe_controller
import pool_probe_runner
import probe_cache
import auto_failover_runtime
import proxy_apply_runtime
import proxy_status
import proxy_protocols
import unblock_lists
import service_catalog
import custom_checks_store
import installer_common
import installer
import repo_update
import entware_dns_runtime
import event_history
import route_intersections
import service_routes
import update_status
from proxy_config_builder import build_proxy_core_config, build_shadowsocks_config, build_trojan_config


SS_KEY = 'ss://YWVzLTEyOC1nY206cGFzc3dvcmQ@example.com:8388#sample'
TROJAN_KEY = 'trojan://secret@example.com:443?sni=example.com#sample'
PORTS = {
    'vmess': 10810,
    'vmess_transparent': 10817,
    'vless': 10811,
    'vless_transparent': 10812,
    'vless2': 10813,
    'vless2_transparent': 10814,
    'shadowsocks_bot': 10815,
    'trojan_bot': 10816,
}


class _FakeButton:
    def __init__(self, text):
        self.text = text


class _FakeMarkup:
    def __init__(self, resize_keyboard=False):
        self.resize_keyboard = resize_keyboard
        self.rows = []

    def row(self, *buttons):
        self.rows.append([button.text for button in buttons])


class _FakeTypes:
    KeyboardButton = _FakeButton
    ReplyKeyboardMarkup = _FakeMarkup


def test_app_runtime_mode_helpers(tmp_path):
    mode_path = tmp_path / 'bot_app_mode'
    assert app_runtime_mode.normalize_app_runtime_mode('web-only') == 'web_only'
    assert app_runtime_mode.normalize_app_runtime_mode('bad') == 'advanced'
    assert app_runtime_mode.load_app_runtime_mode(mode_path, default_mode='simple') == 'simple'
    assert app_runtime_mode.save_app_runtime_mode('web-only', mode_path) == 'web_only'
    assert mode_path.read_text(encoding='utf-8') == 'web_only\n'
    assert app_runtime_mode.load_app_runtime_mode(mode_path, default_mode='simple') == 'web_only'
    assert app_runtime_mode.app_runtime_mode_label('advanced') == 'Сложный'
    assert app_runtime_mode.app_mode_pool_enabled('web_only')
    assert not app_runtime_mode.app_mode_telegram_enabled('web_only')


def test_app_runtime_mode_setter_callbacks():
    current = {'mode': 'advanced'}
    calls = []

    def load_mode():
        return current['mode']

    def save_mode(mode):
        current['mode'] = app_runtime_mode.normalize_app_runtime_mode(mode)
        calls.append(('save', current['mode']))
        return current['mode']

    ok, message, extra = app_runtime_mode.set_app_runtime_mode(
        'web-only',
        load_mode=load_mode,
        save_mode=save_mode,
        schedule_restart=lambda: calls.append(('restart', None)),
        set_telegram_autostart=lambda enabled: calls.append(('telegram', enabled)),
        invalidate_status_cache=lambda: calls.append(('status', None)),
        invalidate_key_status_cache=lambda: calls.append(('keys', None)),
    )
    assert ok
    assert 'Web only' in message
    assert extra['app_mode'] == 'web_only'
    assert extra['pool_enabled'] is True
    assert extra['telegram_enabled'] is False
    assert ('telegram', False) in calls
    assert ('restart', None) in calls

    ok, _, extra = app_runtime_mode.set_app_runtime_mode(
        'missing',
        load_mode=load_mode,
        save_mode=save_mode,
        schedule_restart=lambda: calls.append(('bad-restart', None)),
        set_telegram_autostart=lambda enabled: calls.append(('bad-telegram', enabled)),
        invalidate_status_cache=lambda: calls.append(('bad-status', None)),
        invalidate_key_status_cache=lambda: calls.append(('bad-keys', None)),
    )
    assert not ok
    assert extra['app_mode'] == 'web_only'
    assert ('bad-restart', None) not in calls


def test_router_health_runtime_payload_uses_keenetic_memory():
    payload = router_health_runtime.build_router_health_payload(
        meminfo={
            'MemTotal': 485 * 1024,
            'MemFree': 80 * 1024,
            'Buffers': 20 * 1024,
            'Cached': 100 * 1024,
            'SReclaimable': 30 * 1024,
            'MemAvailable': 201 * 1024,
            'SwapTotal': 472 * 1024,
            'SwapFree': 472 * 1024,
        },
        ndmc_system={
            'memory_used': 281 * 1024,
            'memory_total': 512 * 1024,
            'memfree': 80 * 1024,
            'membuffers': 20 * 1024,
            'memcache': 130 * 1024,
        },
        load_text='0.10 / 0.14 / 0.10',
        bot_rss_kb=52 * 1024,
        probe_progress={'running': False, 'total': 0},
        temp_xray_count=0,
    )
    assert payload['memory_source'] == 'keenetic'
    assert payload['memory_text'] == 'Память: доступно 201 MB, занято 281 из 512 MB'
    assert payload['used_percent'] == 55
    assert payload['pool_probe_text'] == 'Не запущена'
    assert 'Бот использует 52 MB RAM.' in payload['note']
    assert 'Проверка пула' not in payload['note']


def test_router_health_runtime_dns_payload():
    payload = router_health_runtime.build_router_health_payload(
        meminfo={'MemTotal': 64 * 1024, 'MemFree': 8 * 1024, 'MemAvailable': 32 * 1024},
        ndmc_system={},
        load_text='0.01 / 0.02 / 0.03',
        bot_rss_kb=4 * 1024,
        probe_progress={'running': False, 'total': 0},
        temp_xray_count=0,
        dns_health={
            'backend': 'ndnproxy',
            'listener_backend': 'ndnproxy',
            'dnsmasq_state': 'dead',
            'ipset_counts': {'unblockvless': 12, 'unblockvlessudp': 5, 'unblockvless2': 34, 'unblockvless2udp': 12},
            'ipset_updated_at': 1000,
            'ipset_refresh_age_seconds': 90,
            'ipset_refresh_status': 'success',
            'ipset_refresh_message': 'ipset refresh completed.',
        },
    )
    assert payload['dns_backend'] == 'ndnproxy'
    assert payload['dnsmasq_state'] == 'dead'
    assert payload['ipset_counts']['unblockvless2'] == 34
    assert payload['ipset_counts']['unblockvlessudp'] == 5
    assert payload['ipset_counts']['unblockvless2udp'] == 12
    assert 'DNS: ndnproxy (S56dnsmasq не используется)' in payload['dns_note']
    assert 'DNS: ndnproxy' not in payload['note']
    assert 'S56dnsmasq: не запущен' not in payload['note']
    assert 'ipset обновлён: 1 мин назад (успешно)' in payload['dns_note']
    assert payload['dns_note'].count('ipset обновлён') == 1
    assert 'unblockvless2=34' in payload['dns_note']
    assert 'unblockvlessudp=5' in payload['dns_note']
    assert 'unblockvless2udp=12' in payload['dns_note']


def test_router_health_runtime_core_proxy_payload():
    payload = router_health_runtime.build_router_health_payload(
        meminfo={'MemTotal': 64 * 1024, 'MemFree': 8 * 1024, 'MemAvailable': 32 * 1024},
        ndmc_system={},
        load_text='0.01 / 0.02 / 0.03',
        bot_rss_kb=4 * 1024,
        probe_progress={'running': False, 'total': 0},
        temp_xray_count=0,
        core_proxy_health={
            'ok': True,
            'xray_state': 'alive',
            'xray_config_ok': True,
            'ports': {10811: True, 10812: True, 10813: True, 10814: True},
        },
    )
    assert payload['core_proxy_health']['ok'] is True
    assert 'Xray: alive' in payload['core_proxy_note']
    assert '10813:ok' in payload['core_proxy_note']
    original_module = router_health_runtime.xray_compat_runtime
    try:
        router_health_runtime.xray_compat_runtime = None
        fallback_payload = router_health_runtime.build_router_health_payload(
            meminfo={'MemTotal': 64 * 1024, 'MemFree': 8 * 1024, 'MemAvailable': 32 * 1024},
            ndmc_system={},
            load_text='0.01 / 0.02 / 0.03',
            bot_rss_kb=4 * 1024,
            probe_progress={'running': False, 'total': 0},
            temp_xray_count=0,
            core_proxy_health={'ok': False},
        )
        assert fallback_payload['core_proxy_note'] == 'Xray: health module unavailable.'
    finally:
        router_health_runtime.xray_compat_runtime = original_module


def test_router_health_runtime_dns_parsers():
    assert router_health_runtime.parse_dns_backend('udp 0 0 0.0.0.0:53 0.0.0.0:* 759/ndnproxy') == 'ndnproxy'
    assert router_health_runtime.parse_dns_backend('tcp 0 0 0.0.0.0:53 0.0.0.0:* LISTEN 12/dnsmasq') == 'dnsmasq'
    assert router_health_runtime.parse_dns_backend('tcp 0 0 0.0.0.0:53 0.0.0.0:* LISTEN') == 'unknown'
    assert router_health_runtime.parse_dns_backend('') == 'none'
    assert router_health_runtime.parse_ipset_member_count('Name: unblockvless2\nMembers:\n1.1.1.1\n2.2.2.0/24\n') == 2
    assert router_health_runtime.parse_ipset_member_count('Name: unblockvless2\nNumber of entries: 42\nMembers:\n') == 42


def test_xray_compat_runtime_helpers():
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / 'config.json'
        config_path.write_text(
            json.dumps({
                'outbounds': [
                    {'streamSettings': {'security': 'tls', 'tlsSettings': {'allowInsecure': True}}},
                    {'settings': {'nested': [{'allowInsecure': False, 'value': 1}]}},
                ],
            }),
            encoding='utf-8',
        )
        assert xray_compat_runtime.sanitize_xray_config_file(str(config_path))
        sanitized = json.loads(config_path.read_text(encoding='utf-8'))
    assert 'allowInsecure' not in json.dumps(sanitized)
    netstat_text = (
        'tcp 0 0 127.0.0.1:10811 0.0.0.0:* LISTEN 1/xray\n'
        'tcp 0 0 127.0.0.1:10813 0.0.0.0:* LISTEN 1/xray\n'
    )
    ports = xray_compat_runtime.listening_ports((10811, 10812, 10813), netstat_text=netstat_text)
    assert ports == {10811: True, 10812: False, 10813: True}


def test_router_health_runtime_process_rss_parser():
    def fake_read(_path, max_bytes=16384):
        return 'Name:\tpython\nVmRSS:\t  54321 kB\n'

    assert router_health_runtime.process_rss_kb('self', read_text=fake_read) == 54321


def test_web_commands_runtime_dispatch():
    calls = []

    def run_script(action, owner, repo, progress_command=None):
        calls.append((action, owner, repo, progress_command))
        return 0, f'{action}:{owner}/{repo}:{progress_command}'

    assert web_commands_runtime.web_command_label('dns_on') == 'DNS Override ВКЛ'
    assert web_commands_runtime.web_command_label('custom') == 'custom'
    assert web_commands_runtime.run_web_command(
        'update_no_bot',
        run_script_action=run_script,
        fork_repo_owner='fork-owner',
        fork_repo_name='fork-repo',
        rollback_last_update=lambda: 'rollback',
        restart_router_services=lambda: 'restart',
        set_dns_override=lambda enabled: f'dns:{enabled}',
    ) == '-update:fork-owner/fork-repo:update'
    assert calls[-1] == ('-update', 'fork-owner', 'fork-repo', 'update')
    assert web_commands_runtime.run_web_command(
        'dns_off',
        run_script_action=run_script,
        fork_repo_owner='fork-owner',
        fork_repo_name='fork-repo',
        rollback_last_update=lambda: 'rollback',
        restart_router_services=lambda: 'restart',
        set_dns_override=lambda enabled: f'dns:{enabled}',
    ) == 'dns:False'


class _InlineThread:
    def __init__(self, target, daemon=False):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


class _FakeChat:
    def __init__(self, chat_id, chat_type='private'):
        self.id = chat_id
        self.type = chat_type


class _FakeMessage:
    def __init__(self, chat_id=1, chat_type='private'):
        self.chat = _FakeChat(chat_id, chat_type)


def _hash_key(value):
    return 'h:' + value


def test_proxy_config_builder():
    ss_config = build_shadowsocks_config(SS_KEY, 1082)
    assert ss_config['server'] == ['example.com']
    assert ss_config['server_port'] == 8388
    assert ss_config['method'] == 'aes-128-gcm'

    trojan_config = build_trojan_config(TROJAN_KEY, 1090)
    assert trojan_config['remote_addr'] == 'example.com'
    assert trojan_config['remote_port'] == 443
    assert trojan_config['password'] == ['secret']

    core_config = build_proxy_core_config(
        shadowsocks_key=SS_KEY,
        vless_key='vless://00000000-0000-0000-0000-000000000000@example.com:443?security=tls#sample',
        trojan_key=TROJAN_KEY,
        ports=PORTS,
        error_log_path='/tmp/xray-error.log',
        connectivity_check_domains=['api.telegram.org'],
        include_vmess_transparent=True,
    )
    outbound_tags = {outbound.get('tag') for outbound in core_config['outbounds']}
    assert {'proxy-shadowsocks', 'proxy-trojan', 'direct'} <= outbound_tags
    assert 'allowInsecure' not in json.dumps(core_config)
    assert core_config['routing']['rules'][0]['outboundTag'] == 'direct'
    transparent_inbounds = [
        inbound for inbound in core_config['inbounds']
        if inbound.get('protocol') == 'dokodemo-door'
    ]
    assert transparent_inbounds
    assert all(inbound['settings']['network'] == 'tcp,udp' for inbound in transparent_inbounds)
    assert all(inbound['streamSettings']['sockopt']['tproxy'] == 'redirect' for inbound in transparent_inbounds)
    assert all(inbound['sniffing']['enabled'] is False for inbound in transparent_inbounds)
    reality_outbound = proxy_protocols.proxy_outbound_from_key(
        'vless',
        'vless://00000000-0000-0000-0000-000000000000@example.com:443'
        '?security=reality&flow=xtls-rprx-vision&pbk=pub&sid=short&fp=firefox&type=tcp#sample',
        'proxy-vless',
    )
    assert reality_outbound['streamSettings']['realitySettings']['fingerprint'] == 'firefox'
    assert reality_outbound['streamSettings']['realitySettings']['spiderX'] == '/'
    stale_ip_reality_outbound = proxy_protocols.proxy_outbound_from_key(
        'vless',
        'vless://00000000-0000-0000-0000-000000000000@198.51.100.10:443'
        '?security=reality&sni=alive.example.com&flow=xtls-rprx-vision&pbk=pub&sid=short&type=tcp#sample',
        'proxy-vless',
    )
    assert stale_ip_reality_outbound['settings']['vnext'][0]['address'] == '198.51.100.10'
    assert stale_ip_reality_outbound['streamSettings']['realitySettings']['serverName'] == 'alive.example.com'
    vless2_reality_outbound = proxy_protocols.proxy_outbound_from_key(
        'vless2',
        'vless://00000000-0000-0000-0000-000000000000@198.51.100.11:443'
        '?security=reality&sni=alive-v2.example.com&flow=xtls-rprx-vision&pbk=pub&sid=short&type=tcp#sample',
        'proxy-vless2',
    )
    assert vless2_reality_outbound['settings']['vnext'][0]['address'] == '198.51.100.11'
    assert vless2_reality_outbound['streamSettings']['realitySettings']['serverName'] == 'alive-v2.example.com'
    vmess_key = 'vmess://' + base64.b64encode(json.dumps({
        'v': '2',
        'ps': 'sample',
        'add': '198.51.100.20',
        'port': '443',
        'id': '00000000-0000-0000-0000-000000000000',
        'aid': '0',
        'net': 'tcp',
        'type': 'none',
        'host': 'host.example.com',
        'tls': 'tls',
        'sni': 'alive-vmess.example.com',
    }).encode('utf-8')).decode('ascii').rstrip('=')
    vmess_outbound = proxy_protocols.proxy_outbound_from_key('vmess', vmess_key, 'proxy-vmess')
    assert vmess_outbound['settings']['vnext'][0]['address'] == '198.51.100.20'
    assert vmess_outbound['streamSettings']['tlsSettings']['serverName'] == 'alive-vmess.example.com'
    trojan_ip_outbound = proxy_protocols.proxy_outbound_from_key(
        'trojan',
        'trojan://secret@198.51.100.30:443?sni=alive-trojan.example.com&type=tcp#sample',
        'proxy-trojan',
    )
    assert trojan_ip_outbound['settings']['servers'][0]['address'] == '198.51.100.30'
    assert trojan_ip_outbound['streamSettings']['tlsSettings']['serverName'] == 'alive-trojan.example.com'
    default_reality_outbound = proxy_protocols.proxy_outbound_from_key(
        'vless',
        'vless://00000000-0000-0000-0000-000000000000@example.com:443'
        '?security=reality&flow=xtls-rprx-vision&pbk=pub&sid=short&type=tcp#sample',
        'proxy-vless',
    )
    assert default_reality_outbound['streamSettings']['realitySettings']['fingerprint'] == 'chrome'


def test_key_pool_web():
    checks = [{'id': 'custom', 'label': 'Custom'}]
    current = {'vless': 'vless-key'}
    pools = {'vless': ['vless-key', 'unused-key'], 'vmess': ['vmess-key']}
    cache = {
        _hash_key('vless-key'): {'tg_ok': True, 'yt_ok': False, 'custom': {'custom': True}, 'ts': 1},
        _hash_key('unused-key'): {'tg_ok': None, 'yt_ok': None, 'custom': {'custom': None}, 'timeout': True, 'ts': 3},
        _hash_key('vmess-key'): {'tg_ok': True, 'yt_ok': True, 'custom': {'custom': True}, 'ts': 2},
    }

    summary = key_pool_web.pool_status_summary(current, pools, cache, checks, _hash_key)
    assert summary['active_key_count'] == 1
    assert summary['pool_total_count'] == 3
    assert summary['checked_pool_count'] == 2
    assert summary['all_services_count'] == 1
    assert summary['any_service_count'] == 2
    assert summary['services'] == [
        {'label': 'Telegram', 'count': 2},
        {'label': 'YouTube', 'count': 1},
        {'label': 'Custom', 'count': 2},
    ]

    snapshot = key_pool_web.web_pool_snapshot(
        current,
        pools,
        cache,
        checks,
        include_keys=True,
        hash_key=_hash_key,
        display_name=lambda value: value.upper(),
        probe_state=lambda probe, field: 'ok' if probe.get(field) else 'fail' if field in probe else 'unknown',
        probe_checked_at=lambda probe: str(probe.get('ts', '')),
    )
    row = snapshot['vless']['rows'][0]
    assert row['active'] is True
    assert row['display_name'] == 'VLESS-KEY'
    assert row['custom'] == {'custom': 'ok'}
    assert row['key'] == 'vless-key'
    scoped_snapshot = key_pool_web.web_pool_snapshot(
        current,
        pools,
        cache,
        checks,
        include_keys=False,
        hash_key=_hash_key,
        display_name=lambda value: value.upper(),
        probe_state=lambda probe, field: 'ok' if probe.get(field) else 'fail' if field in probe else 'unknown',
        probe_checked_at=lambda probe: str(probe.get('ts', '')),
        protocols=['vmess'],
    )
    assert list(scoped_snapshot) == ['vmess']
    assert scoped_snapshot['vmess']['rows'][0]['key_id'] == _hash_key('vmess-key')[:12]
    def icon_html(icon, alt, opacity=1.0, size=18):
        return f'<img data-icon="{icon}" alt="{alt}">'
    check_defs = [{'id': 'custom', 'label': 'Custom', 'url': 'https://example.com/path', 'icon': 'chat'}]
    assert key_pool_web.custom_check_url_text(check_defs[0]) == 'example.com/path'
    assert 'custom-check-item' in key_pool_web.web_custom_checks_html(check_defs, icon_html)
    assert 'service-preset-btn' in key_pool_web.web_custom_presets_html([], check_defs, icon_html)
    assert 'custom-service-ok' in key_pool_web.web_custom_check_badges({'custom': {'custom': True}}, check_defs, icon_html)
    assert key_pool_web.web_probe_state({'tg_ok': True}, 'tg_ok') == 'ok'
    assert key_pool_web.web_probe_state({'tg_ok': None}, 'tg_ok') == 'unknown'
    assert key_pool_web.web_custom_probe_states({'custom': {'custom': None}}, checks)['custom'] == 'unknown'
    assert key_pool_web.web_probe_checked_at({'ts': 0}) == ''

def test_key_pool_subscription_helpers():
    raw = '\n'.join([
        SS_KEY,
        'vless://uuid@example.com:443?security=tls#sample',
        TROJAN_KEY,
    ])
    classified = key_pool_store.classify_subscription_keys(raw)
    assert classified['shadowsocks'] == [SS_KEY]
    assert classified['vless'] == ['vless://uuid@example.com:443?security=tls#sample']
    assert classified['trojan'] == [TROJAN_KEY]

    pools, added = key_pool_store.add_subscription_keys_to_pool({'vless2': []}, 'vless2', classified)
    assert added == ['vless://uuid@example.com:443?security=tls#sample']
    assert pools['vless2'] == added
    ensured, changed = key_pool_store.ensure_current_keys_in_pools(
        {'vless': ['first', 'active', 'last']},
        {'vless': 'active'},
    )
    assert changed is False
    assert ensured['vless'] == ['first', 'active', 'last']
    ensured_missing, changed_missing = key_pool_store.ensure_current_keys_in_pools(
        {'vless': ['first', 'last']},
        {'vless': 'active'},
    )
    assert changed_missing is True
    assert ensured_missing['vless'] == ['first', 'last', 'active']
    selected = key_pool_store.set_active_key({'vless': ['first', 'active', 'last']}, 'vless', 'active')
    assert selected['vless'] == ['first', 'active', 'last']
    selected_missing = key_pool_store.set_active_key({'vless': ['first', 'last']}, 'vless', 'active')
    assert selected_missing['vless'] == ['first', 'last', 'active']
    candidates = key_pool_store.failover_candidates(
        {'vless': ['active', 'next'], 'vmess': ['vmess-key']},
        'vless',
        'active',
        protocols=('vless', 'vmess'),
    )
    assert candidates == [('vless', 'next'), ('vmess', 'vmess-key')]
    scored_candidates = key_pool_store.failover_candidates(
        {'vless': ['active', 'bad', 'good', 'unknown'], 'vmess': ['vmess-key']},
        'vless',
        'active',
        protocols=('vless', 'vmess'),
        key_probe_cache={
            _hash_key('bad'): {'tg_ok': False, 'ts': 9},
            _hash_key('good'): {'tg_ok': True, 'ts': 1},
        },
        hash_key=_hash_key,
    )
    assert scored_candidates[:3] == [('vless', 'good'), ('vless', 'unknown'), ('vless', 'bad')]


def test_web_post_actions_helpers():
    data = {'target_list_name': ['custom'], 'list_name': ['fallback']}
    assert web_post_actions.form_value(data, 'missing', 'none') == 'none'
    assert web_post_actions.first_form_value(data, ('target_list_name', 'list_name')) == 'custom'
    assert web_post_actions.dispatch({}, '/pool_add', {}) is None
    ctx = web_post_actions.base_action_context(
        app_mode_label='Режим',
        update_proxy=lambda mode: (True, ''),
        proxy_mode_label=lambda mode: mode,
        invalidate_web_status_cache=lambda: None,
        invalidate_key_status_cache=lambda: None,
        start_bot=lambda: 'started',
        start_web_command=lambda command: (True, command),
        get_web_command_state=lambda: {},
        save_unblock_list=lambda name, content: 'saved',
        read_text_file=lambda path: '',
        append_socialnet_list=lambda name, service_key=None: 'added',
        remove_socialnet_list=lambda name, service_key=None: 'removed',
        socialnet_all_key='all',
        normalize_unblock_route_name=lambda name: name,
        install_key_for_protocol=lambda proto, key, verify=True: 'installed',
    )
    assert ctx['app_mode_label'] == 'Режим'
    assert ctx['install_verify'] is True
    pool_ctx = web_post_actions.pool_action_context(
        append_custom_checks_to_unblock_list=lambda name: None,
        unblock_route_for_key_type=lambda key_type: key_type,
        add_custom_check=lambda **kwargs: None,
        delete_custom_check=lambda check_id: None,
        web_custom_checks=lambda: [],
        load_current_keys=lambda: {},
        refresh_status_caches_async=lambda keys: None,
        web_pool_snapshot=lambda keys, include_keys=False: {},
        probe_all_pool_keys_async=lambda **kwargs: (False, 0),
        pool_keys_for_proto=lambda proto: [],
        probe_pool_keys_background=lambda proto, keys, **kwargs: (False, 0),
        cancel_pool_probe=lambda: (False, 'idle'),
        add_keys_to_pool=lambda proto, text: 0,
        delete_pool_key=lambda proto, key: None,
        load_key_pools=lambda: {},
        set_active_key=lambda proto, key: None,
        clear_pool=lambda proto: 0,
        fetch_keys_from_subscription=lambda url: ({}, ''),
        add_subscription_keys_to_pool=lambda pools, proto, fetched: (pools, []),
        save_key_pools=lambda pools: None,
        pool_apply_lock=None,
    )
    assert pool_ctx['pool_actions_enabled'] is True
    assert pool_ctx['custom_checks_enabled'] is True
    deleted = []
    active = []
    snapshots = []
    pool_ctx.update(
        load_current_keys=lambda: {'vless': 'vless://one'},
        web_pool_snapshot=lambda keys, include_keys=False: snapshots.append(include_keys) or {'vless': {'rows': []}},
        load_key_pools=lambda: {'vless': ['vless://one', 'vless://two']},
        hash_key=lambda key: 'id-one-1234' if key == 'vless://one' else 'id-two-1234',
        delete_pool_key=lambda proto, key: deleted.append((proto, key)),
        set_active_key=lambda proto, key: active.append((proto, key)),
        install_key_for_protocol=lambda proto, key, verify=True: 'installed',
        invalidate_web_status_cache=lambda: None,
        invalidate_key_status_cache=lambda: None,
    )
    delete_result = web_post_actions.dispatch(pool_ctx, '/pool_delete', {'type': ['vless'], 'key_id': ['id-two-1234']})
    assert delete_result['success'] is True
    assert deleted == [('vless', 'vless://two')]
    assert delete_result['extra']['key_id'] == 'id-two-1234'
    assert snapshots[-1] is False
    apply_result = web_post_actions.dispatch(pool_ctx, '/pool_apply', {'type': ['vless'], 'key_id': ['id-one-1234']})
    assert apply_result['success'] is True
    assert active == [('vless', 'vless://one')]
    assert apply_result['extra']['key_id'] == 'id-one-1234'
    assert apply_result['extra']['key'] == 'vless://one'
    assert snapshots[-1] is False


def test_web_action_feature_gates():
    calls = []
    disabled_ctx = {
        'pool_actions_enabled': False,
        'custom_checks_enabled': False,
        'probe_all_pool_keys_async': lambda **kwargs: calls.append('pool-probe'),
        'add_custom_check': lambda **kwargs: calls.append('custom-check'),
    }
    assert web_post_actions.dispatch(disabled_ctx, '/pool_probe', {}) is None
    assert web_post_actions.dispatch(disabled_ctx, '/pool_probe_cancel', {}) is None
    assert web_post_actions.dispatch(disabled_ctx, '/custom_check_add', {}) is None
    probe = web_get_actions.dispatch({'pool_enabled': True, 'get_pool_probe_progress': lambda: {'running': False, 'total': 0}}, '/api/pool_probe')
    assert probe['payload']['status'] == 'idle'
    assert calls == []


def test_service_route_apply_can_add_check():
    calls = []
    ctx = {
        'custom_checks_enabled': True,
        'apply_service_route': lambda service_key, proto: {
            'service_label': service_key,
            'target_label': proto,
            'entries': 5,
        },
        'add_custom_check': lambda **kwargs: calls.append(('add', kwargs)) or ([], 'Проверка добавлена.'),
        'probe_all_pool_keys_async': lambda **kwargs: calls.append(('probe', kwargs)),
        'record_event': lambda **kwargs: calls.append(('event', kwargs)),
        'invalidate_web_status_cache': lambda: calls.append(('invalidate-web', {})),
        'invalidate_key_status_cache': lambda: calls.append(('invalidate-key', {})),
        'service_routes_payload': lambda: {'route_tools_html': '<div>routes</div>'},
        'web_custom_checks': lambda: [{'id': 'gemini'}],
    }
    result = web_post_actions.dispatch(
        ctx,
        '/service_route_apply',
        {'service_key': ['gemini'], 'target_protocol': ['vless'], 'add_check': ['1']},
    )
    assert result['success'] is True
    assert ('add', {'preset_id': 'gemini'}) in calls
    assert any(item[0] == 'probe' for item in calls)
    assert 'Проверка добавлена' in result['result']
    assert result['extra']['route_tools_html'] == '<div>routes</div>'
    assert result['extra']['custom_checks'] == [{'id': 'gemini'}]
    assert 'reload_after_ms' not in result['extra']


def _expected_codex_version_counter():
    count = int(subprocess.check_output(['git', 'rev-list', '--count', 'HEAD'], cwd=ROOT, text=True).strip())
    dirty = subprocess.check_output(
        ['git', 'status', '--short', '--untracked-files=no'],
        cwd=ROOT,
        text=True,
    ).strip()
    return f'1.{count + (1 if dirty else 0)}'


def test_codex_version_matches_commit_count():
    expected = _expected_codex_version_counter()
    source = (ROOT / 'bot.py').read_text(encoding='utf-8')
    version_md = (ROOT / 'version.md').read_text(encoding='utf-8')
    installer = (ROOT / 'installer.py').read_text(encoding='utf-8')
    bootstrap = (ROOT / 'bootstrap' / 'install.sh').read_text(encoding='utf-8')
    example = (ROOT / 'bot_config.example.py').read_text(encoding='utf-8')
    assert app_version.APP_VERSION_COUNTER == expected
    assert re.search(rf'Версия\s+v{re.escape(expected)}\b', source)
    assert version_md.startswith(f'*v{expected} ')
    assert f'v{{APP_VERSION_COUNTER}}' in installer
    assert 'from app_version import APP_VERSION_COUNTER' in installer
    assert 'from app_version import APP_VERSION_COUNTER' in bootstrap
    assert 'memory_watchdog_rss_limit_kb = 112640' in example
    assert 'memory_watchdog_rss_limit_kb = 112640' in installer
    assert 'memory_watchdog_rss_limit_kb = 112640' in bootstrap
    assert 'pool_probe_delay_seconds = 1.5' in example
    assert 'pool_probe_delay_seconds = 1.5' in installer
    assert 'pool_probe_delay_seconds = 1.5' in bootstrap
    assert 'pool_probe_cpu_guard_enabled = True' in example
    assert 'pool_probe_cpu_guard_enabled = True' in installer
    assert 'pool_probe_cpu_guard_enabled = True' in bootstrap
    assert 'pool_probe_max_cpu_percent = 70.0' in example
    assert 'pool_probe_max_cpu_percent = 70.0' in installer
    assert 'pool_probe_max_cpu_percent = 70.0' in bootstrap
    assert 'memory_watchdog_idle_restart_rss_kb = 71680' in example
    assert 'memory_watchdog_idle_restart_rss_kb = 71680' in installer
    assert 'memory_watchdog_idle_restart_rss_kb = 71680' in bootstrap
    assert 'memory_watchdog_idle_restart_hold_seconds = 120.0' in example
    assert 'memory_watchdog_idle_restart_hold_seconds = 120.0' in installer
    assert 'memory_watchdog_idle_restart_hold_seconds = 120.0' in bootstrap
    assert 'memory_post_pool_restart_rss_kb = 71680' in example
    assert 'memory_post_pool_restart_rss_kb = 71680' in installer
    assert 'memory_post_pool_restart_rss_kb = 71680' in bootstrap
    assert 'memory_post_pool_restart_retry_seconds = 30.0' in example
    assert 'memory_post_pool_restart_retry_seconds = 30.0' in installer
    assert 'memory_post_pool_restart_retry_seconds = 30.0' in bootstrap
    assert 'memory_post_pool_restart_max_wait_seconds = 300.0' in example
    assert 'memory_post_pool_restart_max_wait_seconds = 300.0' in installer
    assert 'memory_post_pool_restart_max_wait_seconds = 300.0' in bootstrap
    assert 'udp_quic_block_shadowsocks_enabled = True' in example
    assert 'udp_quic_block_shadowsocks_enabled = True' in installer
    assert 'udp_quic_block_shadowsocks_enabled = True' in bootstrap
    assert 'udp_quic_block_vmess_enabled = True' in example
    assert 'udp_quic_block_vmess_enabled = True' in installer
    assert 'udp_quic_block_vmess_enabled = True' in bootstrap
    assert 'udp_quic_block_vless_enabled = True' in example
    assert 'udp_quic_block_vless_enabled = True' in installer
    assert 'udp_quic_block_vless_enabled = True' in bootstrap
    assert 'udp_quic_block_vless2_enabled = True' in example
    assert 'udp_quic_block_vless2_enabled = True' in installer
    assert 'udp_quic_block_vless2_enabled = True' in bootstrap
    assert 'udp_quic_block_trojan_enabled = True' in example
    assert 'udp_quic_block_trojan_enabled = True' in installer
    assert 'udp_quic_block_trojan_enabled = True' in bootstrap
    assert 'ipv6_bypass_fallback_enabled = True' in example
    assert 'ipv6_bypass_fallback_enabled = True' in installer
    assert 'ipv6_bypass_fallback_enabled = True' in bootstrap
    assert 'reality_endpoint_overrides = {}' in example
    assert 'reality_endpoint_overrides = {{}}' in installer
    assert 'reality_endpoint_overrides = {}' in bootstrap
    assert 'reality_endpoint_repair_enabled = True' in example
    assert 'reality_endpoint_repair_enabled = True' in installer
    assert 'reality_endpoint_repair_enabled = True' in bootstrap
    assert "reality_endpoint_repair_dns_servers = ('1.1.1.1', '8.8.8.8', '9.9.9.9')" in example
    assert "reality_endpoint_repair_dns_servers = ('1.1.1.1', '8.8.8.8', '9.9.9.9')" in installer
    assert "reality_endpoint_repair_dns_servers = ('1.1.1.1', '8.8.8.8', '9.9.9.9')" in bootstrap
    assert 'auto_failover_startup_hold_seconds = 180' in example
    assert 'auto_failover_startup_hold_seconds = 180' in installer
    assert 'auto_failover_startup_hold_seconds = 180' in bootstrap
    assert 'youtube_vless2_failover_enabled = True' in example
    assert 'youtube_vless2_failover_enabled = True' in installer
    assert 'youtube_vless2_failover_enabled = True' in bootstrap
    assert 'youtube_vless2_failover_check_connect_timeout = 6' in example
    assert 'youtube_vless2_failover_check_connect_timeout = 6' in installer
    assert 'youtube_vless2_failover_check_connect_timeout = 6' in bootstrap
    assert 'youtube_vless2_failover_check_read_timeout = 10' in example
    assert 'youtube_vless2_failover_check_read_timeout = 10' in installer
    assert 'youtube_vless2_failover_check_read_timeout = 10' in bootstrap
    assert f'# ВЕРСИЯ СКРИПТА v{expected}' in example


def test_update_script_socks_download_notice_is_not_repeated():
    script = (ROOT / 'script.sh').read_text(encoding='utf-8')
    unblock_dnsmasq = (ROOT / 'unblock.dnsmasq').read_text(encoding='utf-8')
    assert 'Downloaded via local SOCKS port' not in script
    assert 'Downloading GitHub files via local SOCKS port ${port}.' in script
    assert 'RAW_GITHUB_SOCKS_NOTICE_SHOWN=1' in script
    assert 'remove_path /opt/root/get-pip.py' in script
    assert 'chmod 777 /opt/root/get-pip.py || rm' not in script
    assert 'touch /opt/etc/hosts && chmod 0644 /opt/etc/hosts' in script
    assert "normalize_line()" in unblock_dnsmasq
    assert "s/\\r//g" in unblock_dnsmasq
    assert 'line=$(normalize_line "$line")' in unblock_dnsmasq
    assert 'udp_quic_domain()' in unblock_dnsmasq
    assert 'ipset_targets "$line" unblocksh unblockshudp' in unblock_dnsmasq
    assert 'ipset_targets "$line" unblockvmess unblockvmessudp' in unblock_dnsmasq
    assert 'ipset_targets "$line" unblockvless unblockvlessudp' in unblock_dnsmasq
    assert 'ipset_targets "$line" unblockvless2 unblockvless2udp' in unblock_dnsmasq
    assert 'ipset_targets "$line" unblocktroj unblocktrojudp' in unblock_dnsmasq


def test_ipset_refresh_is_backend_aware_and_atomic():
    script = (ROOT / 'script.sh').read_text(encoding='utf-8')
    bootstrap = (ROOT / 'bootstrap' / 'install.sh').read_text(encoding='utf-8')
    bot_source = (ROOT / 'bot.py').read_text(encoding='utf-8')
    update_script = (ROOT / 'unblock_update.sh').read_text(encoding='utf-8')
    unblock_dnsmasq = (ROOT / 'unblock.dnsmasq').read_text(encoding='utf-8')
    ipset_script = (ROOT / 'unblock_ipset.sh').read_text(encoding='utf-8')
    ipset_boot_script = (ROOT / '100-ipset.sh').read_text(encoding='utf-8')
    redirect_script = (ROOT / '100-redirect.sh').read_text(encoding='utf-8')
    crontab = (ROOT / 'crontab').read_text(encoding='utf-8')

    assert 'flush_set' not in update_script
    assert 'Using Keenetic ndnproxy, preloading ipset' in update_script
    assert '/opt/bin/unblock_ipset.sh &' not in update_script
    assert 'download_update_file "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/crontab"' in script
    assert 'mv "$stage_dir/crontab" /opt/etc/crontab' in script
    assert '/opt/etc/init.d/S10cron restart' in script
    assert '/opt/bin/unblock_update.sh > /dev/null 2>&1 || true' in script
    assert '/opt/bin/unblock_update.sh >/dev/null 2>&1 || true' in bootstrap
    assert "'/opt/bin/unblock_update.sh'" in bot_source
    assert 'detect_ipset_type()' in script
    assert script.count('set_type="$(detect_ipset_type)"') == 2
    assert 'sed -i "s/hash:net/${set_type}/g" "$stage_dir/100-ipset.sh"' in script
    assert 'sed -i "s/hash:net/${set_type}/g" "$stage_dir/100-redirect.sh"' in script
    assert 'ensure_runtime_legacy_paths' in script
    assert 'rm -f /opt/etc/bot/bot.py' in script
    assert 'ln -s main.py /opt/etc/bot/bot.py' in script
    assert 'ensure_symlink_or_copy "$BOT_MAIN_PATH" "$BOT_DIR/bot.py"' in bootstrap
    assert 'generate_udp_quic_policy_file' in script
    assert 'generate_udp_quic_policy_file' in bootstrap
    assert 'UDP_QUIC_EXCLUDE_ENTRIES' in script
    assert 'UDP_QUIC_EXCLUDE_ENTRIES' in bootstrap
    assert 'from service_catalog import YOUTUBE_UNBLOCK_ENTRIES' in script
    assert 'from service_catalog import YOUTUBE_UNBLOCK_ENTRIES' in bootstrap
    assert 'route_contains_youtube(filename)' in script
    assert 'route_contains_youtube(filename)' in bootstrap
    assert "('VLESS', 'vless.txt', 'udp_quic_block_vless_enabled')" in script
    assert "('VLESS2', 'vless-2.txt', 'udp_quic_block_vless2_enabled')" in script
    assert "print(f'BYPASS_UDP_QUIC_BLOCK_{env_name}={1 if enabled else 0}')" in script

    assert 'LOCK_DIR="${LOCK_DIR:-/tmp/bypass-unblock-ipset.lock}"' in ipset_script
    assert 'STATUS_FILE="${IPSET_STATUS_FILE:-/opt/tmp/bypass_ipset_status.json}"' in ipset_script
    assert 'DNS_WAIT_SECONDS="${DNS_WAIT_SECONDS:-60}"' in ipset_script
    assert 'for set_name in $SET_NAMES $EXTRA_SET_NAMES; do' in ipset_script
    assert 'ipset swap "$swap_tmp_set" "$set_name"' in ipset_script
    assert 'unblockshudp "tmp_unblockshudp_$$"' in ipset_script
    assert 'unblockvmessudp "tmp_unblockvmessudp_$$"' in ipset_script
    assert 'unblockvlessudp "tmp_unblockvlessudp_$$"' in ipset_script
    assert 'unblockvless2udp "tmp_unblockvless2udp_$$"' in ipset_script
    assert 'unblocktrojudp "tmp_unblocktrojudp_$$"' in ipset_script
    assert 'resolve_ipv6_domains "$ipv6_tmp_set" "$domain_file"' in ipset_script
    assert 'dig +short AAAA "$domain"' in ipset_script
    assert 'unblockvless6 "tmp_unblockvless6_$$"' in ipset_script
    assert 'unblockvless2v6 "tmp_unblockvless2v6_$$"' in ipset_script
    assert 'udp_quic_domain "$domain"' in ipset_script
    assert 'udp_quic_direct_entry "$direct_entry"' in ipset_script
    assert 'extract_ipv6_direct_entry()' in ipset_script
    assert 'append_restore "$ipv6_tmp_set" "$direct_ipv6_entry"' in ipset_script
    assert 'entry ~ /^[0-9.]+(\\/[0-9]+)?$/' in ipset_script
    assert 'UDP_QUIC_POLICY_FILE="${UDP_QUIC_POLICY_FILE:-/opt/etc/bot/udp_quic_routes.txt}"' in ipset_script
    assert 'UDP_QUIC_EXCLUDE_FILE="${UDP_QUIC_EXCLUDE_FILE:-/opt/etc/bot/udp_quic_exclude.txt}"' in ipset_script
    assert 'from service_catalog import UDP_QUIC_ROUTE_ENTRIES' in ipset_script
    assert 'from service_catalog import UDP_QUIC_EXCLUDE_ENTRIES' in ipset_script
    assert 'YOUTUBE_VIDEO_PRELOAD_URL="${YOUTUBE_VIDEO_PRELOAD_URL:-https://www.youtube.com/watch?v=dQw4w9WgXcQ}"' in ipset_script
    assert 'YOUTUBE_VIDEO_PRELOAD_EXTRA_URLS="${YOUTUBE_VIDEO_PRELOAD_EXTRA_URLS:-https://www.youtube.com/watch?v=C1ZicUtxD-0}"' in ipset_script
    assert 'YOUTUBE_DNS_SAMPLE_SERVERS="${YOUTUBE_DNS_SAMPLE_SERVERS:-8.8.8.8 8.8.4.4 1.1.1.1 9.9.9.9}"' in ipset_script
    assert 'for sample_dns in $extra_dns_servers; do' in ipset_script
    assert 'preload_youtube_video_hosts()' in ipset_script
    assert '--socks5-hostname "127.0.0.1:$socks_port"' in ipset_script
    assert "grep -Eo '[A-Za-z0-9.-]+\\.googlevideo\\.com'" in ipset_script
    assert 'function cidr24(ip)' in ipset_script
    assert 'function cidr64(ip, parts, net)' in ipset_script
    assert 'print "add " tmp_set " " cidr24($1);' in ipset_script
    assert 'if (net != "") print "add " tmp_set " " net;' in ipset_script
    assert 'preload_youtube_video_hosts "$set_name" "$main_tmp_set" "$mirror_tmp_set" "$domain_file" "$ipv6_tmp_set"' in ipset_script
    assert 'from service_catalog import UDP_QUIC_ROUTE_ENTRIES' in unblock_dnsmasq
    assert 'chatgpt.com|*.chatgpt.com' not in ipset_script
    assert 'chatgpt.com|*.chatgpt.com' not in unblock_dnsmasq
    assert '8.6.112.6|8.47.69.6|35.190.80.1|64.239.109.65' not in ipset_script
    assert 'swap_or_preserve_set unblockshudp "tmp_unblockshudp_$$"' in ipset_script
    assert 'swap_or_preserve_set unblockvmessudp "tmp_unblockvmessudp_$$"' in ipset_script
    assert 'swap_or_preserve_set unblockvlessudp "tmp_unblockvlessudp_$$"' in ipset_script
    assert 'swap_or_preserve_set unblockvless2udp "tmp_unblockvless2udp_$$"' in ipset_script
    assert 'swap_or_preserve_set unblocktrojudp "tmp_unblocktrojudp_$$"' in ipset_script
    assert 'ipset create unblockshudp hash:net -exist' in ipset_boot_script
    assert 'ipset create unblockvmessudp hash:net -exist' in ipset_boot_script
    assert 'ipset create unblockvlessudp hash:net -exist' in ipset_boot_script
    assert 'ipset create unblockvless2udp hash:net -exist' in ipset_boot_script
    assert 'ipset create unblocktrojudp hash:net -exist' in ipset_boot_script
    assert 'ipset create unblockvless6 hash:net family inet6 -exist' in ipset_boot_script
    assert 'ipset create unblockvless2v6 hash:net family inet6 -exist' in ipset_boot_script
    assert 'UDP_QUIC_REJECT_PORT="${UDP_QUIC_REJECT_PORT:-10944}"' in redirect_script
    assert 'install_udp_quic_block_rule unblockshudp "$BYPASS_UDP_QUIC_BLOCK_SHADOWSOCKS"' in redirect_script
    assert 'install_udp_quic_block_rule unblockvmessudp "$BYPASS_UDP_QUIC_BLOCK_VMESS"' in redirect_script
    assert 'install_udp_quic_block_rule unblockvlessudp "$BYPASS_UDP_QUIC_BLOCK_VLESS"' in redirect_script
    assert 'install_udp_quic_block_rule unblockvless2udp "$BYPASS_UDP_QUIC_BLOCK_VLESS2"' in redirect_script
    assert 'install_udp_quic_block_rule unblocktrojudp "$BYPASS_UDP_QUIC_BLOCK_TROJAN"' in redirect_script
    assert '--match-set "$set_name" dst -m udp --dport 443 -j REDIRECT --to-ports "$UDP_QUIC_REJECT_PORT"' in redirect_script
    assert 'iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblockvlessudp dst --dport 443 -j REDIRECT --to-ports 10812' not in redirect_script
    assert 'iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblockvless2udp dst --dport 443 -j REDIRECT --to-ports 10814' not in redirect_script
    assert 'iptables -I FORWARD -w -p udp -m set --match-set unblockvlessudp dst --dport 443 -j REJECT' not in redirect_script
    assert 'iptables -I FORWARD -w -p udp -m set --match-set unblockvless2udp dst --dport 443 -j REJECT' not in redirect_script
    assert 'refresh_udp_quic_block_rules' in redirect_script
    assert '-p udp --dport "$reject_port" -j REJECT --reject-with icmp-port-unreachable' in redirect_script
    assert 'install_ipv6_fallback_rules()' in redirect_script
    assert 'BYPASS_IPV6_FALLBACK_ENABLED="${BYPASS_IPV6_FALLBACK_ENABLED:-1}"' in redirect_script
    assert 'ip6tables -I FORWARD -w -p "$protocol" -m set --match-set "$set_name" dst --dport 443 -j REJECT' in redirect_script
    assert 'iptables -I FORWARD -w -p udp -m set --match-set unblockvless dst --dport 443 -j REJECT' not in redirect_script
    assert 'iptables -I FORWARD -w -p udp -m set --match-set unblockvless2 dst --dport 443 -j REJECT' not in redirect_script
    assert '-p udp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10812' in redirect_script
    assert '-p udp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10814' in redirect_script
    assert 'resolved to zero entries, preserving' in ipset_script
    assert '*/15 * * * * root /opt/bin/unblock_ipset.sh >/dev/null 2>&1' in crontab


def test_vless_tcp_redirect_prioritizes_vless1_for_overlapping_google_ips():
    redirect_script = (ROOT / '100-redirect.sh').read_text(encoding='utf-8')
    assert 'refresh_vless_tcp_priority()' in redirect_script
    assert 'telegram_route_protocol()' in redirect_script
    assert 'refresh_mobile_push_priority()' in redirect_script
    assert 'remove_vless_tcp_forward_guard()' in redirect_script
    assert 'iptables -I FORWARD -w -p tcp -m set --match-set "$guard_set" dst -j REJECT --reject-with tcp-reset' not in redirect_script
    assert 'CRD/Telegram-style service routes do not get captured by the YouTube key' in redirect_script
    vless2_insert = (
        'iptables -I PREROUTING -w -t nat -p tcp -m set --match-set '
        'unblockvless2 dst -j REDIRECT --to-ports 10814'
    )
    vless1_insert = (
        'iptables -I PREROUTING -w -t nat -p tcp -m set --match-set '
        'unblockvless dst -j REDIRECT --to-ports 10812'
    )
    priority_block = redirect_script.split('refresh_vless_tcp_priority() {', 1)[1].split('\n}', 1)[0]
    assert priority_block.index(vless2_insert) < priority_block.index(vless1_insert)
    assert 'UNBLOCK_DIR="${UNBLOCK_DIR:-/opt/etc/unblock}"' in redirect_script
    assert 'grep -Fxs "$marker" "$UNBLOCK_DIR/vless-2.txt"' in redirect_script
    push_block = redirect_script.split('refresh_mobile_push_priority() {', 1)[1].split('\n}', 1)[0]
    assert 'for push_port in 5222 5223 5228 5229 5230' in push_block
    assert 'telegram_route="$(telegram_route_protocol)"' in push_block
    assert '[ "$telegram_route" = "vless2" ] && [ -n "$vless2_key_path" ] && target_port=10814' in push_block
    assert 'for push_set in unblockvless unblockvless2' in push_block
    assert '--dport "$push_port" -j REDIRECT --to-ports "$target_port"' in push_block


def test_runtime_startup_limits_router_flash_and_overhead():
    service = (ROOT / 'S99telegram_bot').read_text(encoding='utf-8')
    source = (ROOT / 'bot.py').read_text(encoding='utf-8')
    pool_controller_source = (ROOT / 'pool_probe_controller.py').read_text(encoding='utf-8')
    pool_runner_source = (ROOT / 'pool_probe_runner.py').read_text(encoding='utf-8')
    proxy_apply_source = (ROOT / 'proxy_apply_runtime.py').read_text(encoding='utf-8')
    youtube_source = source + pool_controller_source + pool_runner_source + proxy_apply_source
    assert 'PYTHONDONTWRITEBYTECODE=1 python3 "$MAIN_SCRIPT"' in service
    assert 'cleanup_python_bytecode' in service
    assert 'trim_runtime_logs' in service
    assert 'unset BYPASS_KEENETIC_COMMAND_WORKER' in service
    assert 'threading.stack_size(256 * 1024)' in source
    assert 'subprocess.Popen(' in source
    assert 'bypass-bot-service-restart.log' in source
    assert "pool_probe_min_available_kb', 160000" in source
    assert "memory_watchdog_rss_limit_kb', 110 * 1024" in source
    assert "memory_watchdog_idle_restart_rss_kb', 70 * 1024" in source
    assert "memory_watchdog_idle_restart_hold_seconds', 120.0" in source
    assert 'def _sync_udp_policy_config' in source
    assert 'YOUTUBE_UNBLOCK_ENTRIES' in source
    assert "UDP_QUIC_POLICY_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')" in source
    assert 'def _route_list_contains_youtube' in source
    assert 'def _udp_quic_block_enabled_for_protocol' in source
    assert "_udp_quic_block_enabled_for_protocol('vless', UDP_QUIC_BLOCK_VLESS_ENABLED)" in source
    assert "_udp_quic_block_enabled_for_protocol('vless2', UDP_QUIC_BLOCK_VLESS2_ENABLED)" in source
    assert 'def _apply_reality_endpoint_override' in source
    assert 'REALITY_ENDPOINT_OVERRIDES' in source
    assert 'def _repair_active_reality_endpoint' in source
    assert 'def _probe_reality_endpoint_with_temp_xray' in source
    assert 'repair_active_proxy=_repair_active_reality_endpoint' in source
    assert "_repair_active_reality_endpoint(route_proto, confirm_message, service='youtube')" in source
    assert "_probe_reality_endpoint_with_temp_xray(proto, key, endpoint, service=service)" in source
    assert "proto not in ('vless', 'vless2')" in source
    assert 'authenticated=False' in source
    assert 'def _start_udp_quic_drift_watchdog_thread' in source
    assert 'UDP_QUIC_DRIFT_SENTINEL_DOMAINS' in source
    assert "subprocess.run(\n            ['/opt/bin/unblock_ipset.sh']" in source
    assert 'memory_watchdog_high_rss_since' in source
    assert 'memory_watchdog_idle_restart_pending' in source
    assert 'memory_watchdog_idle_restart_in_seconds' in source
    assert 'автоперезапуск уже запрошен' in source
    assert 'def _start_memory_watchdog_thread' in source
    assert 'def _memory_cleanup' in source
    assert "memory_post_pool_restart_rss_kb', 70 * 1024" in source
    script_source = (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'migrate_runtime_config_defaults' in script_source
    assert 'memory_watchdog_idle_restart_rss_kb = 71680' in script_source
    assert 'memory_post_pool_restart_rss_kb = 71680' in script_source
    assert 'Refreshing ipset after proxy core startup.' in script_source
    assert script_source.find('start_preferred_core_service || exit 1') < script_source.find('Refreshing ipset after proxy core startup.')
    assert 'write_update_rollback_script()' in script_source
    assert 'ln -sf "$rollback_path" /opt/root/bypass-last-update-rollback.sh' in script_source
    assert 'mv "$INSTALLER_MAIN_PATH" "$backup_dir"/installer.py' in script_source
    assert 'mv "$INSTALLER_SERVICE_PATH" "$backup_dir"/S98telegram_bot_installer' in script_source
    assert 'mv "$BOT_SERVICE_PATH" "$backup_dir"/S99telegram_bot' in script_source
    assert 'restore_file S99telegram_bot "\\$BOT_SERVICE_PATH"' in script_source
    assert 'def _placeholder_status_snapshot' in source
    assert "'placeholder_status_snapshot': _placeholder_status_snapshot" in source
    assert 'cached_active = _cached_active_mode_protocol_status(current_keys)' in source
    assert 'allow_youtube_confirm=False' in source
    assert 'def _pool_probe_cpu_busy_percent' in source
    assert 'def _schedule_post_pool_memory_cleanup' in source
    assert "POOL_PROBE_RESUME_FILE = '/opt/etc/bot/pool_probe_resume.json'" in source
    assert 'def _persist_pool_probe_resume_payload' in source
    assert 'def _load_persisted_pool_probe_resume' in source
    assert '_load_persisted_pool_probe_resume()' in source
    assert "_schedule_post_pool_memory_cleanup()" in source
    assert "allow_youtube_confirm=True" in source
    assert "allow_youtube_confirm=False" in source
    assert "elif pool_locked:" in source
    assert 'def _attempt_youtube_vless2_failover' in source
    assert '_start_youtube_vless2_failover_thread()' in source
    assert 'def _probe_applied_pool_key_services' in source
    assert 'probe_applied_pool_key_services=_probe_applied_pool_key_services' in source
    assert "telegram_required=_telegram_required_for_protocol(proto)" in source
    assert "'probe_applied_pool_key_services'" in (ROOT / 'web_post_actions.py').read_text(encoding='utf-8')
    assert 'protocols=(proxy_mode,) if proxy_mode in POOL_PROTOCOL_ORDER else POOL_PROTOCOL_ORDER' in source
    assert "auto_failover_recent_success_ttl', 300" in source
    assert "auto_failover_startup_hold_seconds', 180" in source
    assert 'startup_hold_seconds=AUTO_FAILOVER_STARTUP_HOLD_SECONDS' in source
    assert "youtube_vless2_failover_recent_success_ttl', 300" in source
    assert 'def _youtube_route_protocol' in source
    assert "YOUTUBE_ROUTE_PROTOCOLS = ('vless', 'vless2')" in source
    assert "proxy_mode == route_proto" in source
    assert 'Telegram is required because bot mode is' in source
    assert 'YOUTUBE_VLESS2_HEALTHCHECK_URLS' in source
    assert "youtube_stream_guard_failover_hold_seconds" in source
    assert "cached_fail_since or now" in source
    assert "getattr(config, 'youtube_vless2_failover_check_connect_timeout', 6)" in source
    assert "getattr(config, 'youtube_vless2_failover_check_read_timeout', 10)" in source
    assert 'YOUTUBE_VLESS2_HARD_FAILURE_RECOVERY_COOLDOWN_SECONDS' in source
    assert 'REALITY_ENDPOINT_REPAIR_DNS_SERVERS' in source
    assert 'repair_dns_servers = {str(item).strip() for item in REALITY_ENDPOINT_REPAIR_DNS_SERVERS}' in source
    assert 'if value in repair_dns_servers:' in source
    assert "['dig', '+time=2', '+tries=1', '+short', 'A'" in source
    assert "['nslookup', str(domain), str(dns_server)]" in source
    assert 'def _recover_current_youtube_route_after_hard_failure' in source
    assert source.find('_recover_current_youtube_route_after_hard_failure(route_proto, active_key, message)') < source.find("_recent_probe_ok(cached_active_probe")
    assert 'Primary YouTube connectivity endpoint did not respond through this key: ' in pool_controller_source
    assert 'Primary YouTube connectivity endpoint did not respond through this key: ' in pool_runner_source
    assert 'Primary YouTube connectivity endpoint did not respond through this key: ' in proxy_apply_source
    assert 'youtube_timeouts=(YOUTUBE_VLESS2_FAILOVER_CHECK_CONNECT_TIMEOUT, YOUTUBE_VLESS2_FAILOVER_CHECK_READ_TIMEOUT)' in source
    assert 'http_retry_timeouts=(POOL_PROBE_RETRY_CONNECT_TIMEOUT, POOL_PROBE_RETRY_READ_TIMEOUT)' in source
    assert 'redirector.googlevideo.com/generate_204' in youtube_source
    assert 'googlevideo.com/generate_204' in youtube_source
    assert 'i.ytimg.com/generate_204' in youtube_source
    assert 'YOUTUBE_HEALTHCHECK_MIN_OK = 2' in youtube_source
    assert 'YOUTUBE_HEALTHCHECK_REQUIRED_URLS' in youtube_source
    unblock_source = (ROOT / 'unblock_ipset.sh').read_text(encoding='utf-8')
    assert 'yt4.googleusercontent.com' in unblock_source
    assert 'add_cidr64="$youtube_ipv6_domain"' in unblock_source
    assert 'for sample_dns in $YOUTUBE_DNS_SAMPLE_SERVERS' in unblock_source
    assert 'Last confirmation:' in source
    assert 'def _check_youtube_health_through_proxy' in source
    assert 'read_timeout=8' in source
    assert 'def _redact_sensitive_text' in source
    assert 'bot<redacted-token>' in source
    assert "'BYPASS_KEENETIC_COMMAND_WORKER'" in source
    assert 'error_text = _redact_sensitive_text(exc)' in source
    assert 'def _telegram_send_error_is_transient' in source
    assert 'def _install_telegram_send_retry_wrapper' in source
    assert "_reset_telegram_http_session('send_message retry')" in source
    assert 'redact_text=_redact_sensitive_text' in source
    assert "_memory_cleanup('pool probe finished'" in source
    assert "_memory_cleanup('web command finished'" in source
    assert "_memory_cleanup('protocol panel render'" in source
    assert 'os.environ["BYPASS_KEENETIC_COMMAND_WORKER"] = "1"' in source
    assert 'from pool_probe_runner import' not in source
    assert 'from repo_update import' not in source
    assert 'from web_form_template import' not in source
    assert 'not app_runtime_mode.app_mode_telegram_enabled(_runtime_mode_at_import())' in source
    assert 'class _NoopTeleBot' in source


def test_web_response_body_ignores_client_disconnect():
    class BrokenWriter:
        def write(self, _body):
            raise ConnectionResetError('client closed')

    request = object.__new__(web_http_common.WebRequestMixin)
    request.wfile = BrokenWriter()
    request.close_connection = False

    assert request._write_response_body(b'body') is False
    assert request.close_connection is True


def test_runtime_modules_are_installed_by_update_scripts():
    script = (ROOT / 'script.sh').read_text(encoding='utf-8')
    bootstrap = (ROOT / 'bootstrap' / 'install.sh').read_text(encoding='utf-8')
    script_modules = set(re.search(r'BOT_RUNTIME_MODULES="([^"]+)"', script).group(1).split())
    bootstrap_modules = set(re.search(r'BOT_RUNTIME_MODULES="([^"]+)"', bootstrap).group(1).split())
    assert script_modules == bootstrap_modules
    for module in script_modules:
        assert (ROOT / module).exists()
    for module in ('app_version.py', 'app_runtime_mode.py', 'router_health_runtime.py', 'web_commands_runtime.py'):
        assert module in script
        assert f'$RAW_BASE/{module}' in bootstrap
        assert f'$BOT_DIR/{module}' in bootstrap


def test_entware_dns_runtime_helpers():
    class _Result:
        def __init__(self, returncode):
            self.returncode = returncode

    assert hasattr(entware_dns_runtime, 'prepare_entware_dns')
    assert entware_dns_runtime.entware_dns_is_available(run_quiet=lambda args: _Result(0))
    assert not entware_dns_runtime.entware_dns_is_available(run_quiet=lambda args: _Result(1))
    assert entware_dns_runtime.entware_ip_from_lookup('Address 1: 1.1.1.1\nAddress 2: 2.2.2.2') == '2.2.2.2'


def test_web_status_runtime_helpers():
    assert web_status_runtime.protocol_preflight_status('', True, '')['tone'] == 'empty'
    failed = web_status_runtime.protocol_preflight_status('key', False, 'SOCKS fail', proxy_user_label='Web')
    assert failed['tone'] == 'fail' and 'Web' in failed['details']
    assert web_status_runtime.protocol_preflight_status('key', True, 'SOCKS ok', xray_required=True)['label'] == 'Требует Xray'
    assert proxy_status.is_transient_status_text('SSLEOFError: UNEXPECTED_EOF_WHILE_READING')
    assert proxy_status.is_transient_status_text('Прокси-сервер разорвал TLS-соединение с api.telegram.org.')
    pending = web_status_runtime.build_web_status_snapshot(
        state_label='state',
        proxy_mode='vless',
        protocols={'vless': {'endpoint_ok': True, 'endpoint_message': 'SOCKS ok.', 'api_ok': False, 'api_message': 'timeout'}},
        ports={'vless': 10811},
        check_socks5=lambda port: False,
        check_telegram_api=lambda **kwargs: 'unused',
        is_transient=lambda text: 'timeout' in text,
        fallback_reason='fallback',
    )
    assert pending['api_status'].startswith('⏳ Telegram API')
    assert pending['socks_details'] == 'SOCKS ok.'
    placeholder = web_status_runtime.build_web_status_snapshot(
        state_label='state',
        proxy_mode='vless',
        protocols={'vless': {'tone': 'warn', 'label': 'Проверяется', 'details': 'Фоновая проверка ключа выполняется.'}},
        ports={'vless': 10811},
        check_socks5=lambda port: False,
        check_telegram_api=lambda **kwargs: 'unused',
        is_transient=lambda text: False,
        fallback_reason='',
    )
    assert placeholder['api_status'].startswith('⏳ Telegram API')
    assert 'не проходит:' not in placeholder['api_status']
    fallback = web_status_runtime.build_web_status_snapshot(
        state_label='state',
        proxy_mode='vless',
        protocols={},
        ports={'vless': 10811},
        check_socks5=lambda port: True,
        check_telegram_api=lambda **kwargs: '❌ timeout',
        is_transient=lambda text: 'timeout' in text,
        fallback_reason='',
    )
    assert fallback['socks_details'].endswith('доступен')
    assert fallback['api_status'].startswith('⏳ Telegram API')
    attention = web_form_template._attention_items(
        {'api_status': '❌ Доступ к Telegram API через режим vless не проходит:'},
        {'used_percent': 0},
        '',
        True,
    )
    assert attention[0][0] == 'warn'


def test_telegram_confirm_state_source():
    source = (ROOT / 'bot.py').read_text(encoding='utf-8')
    install_source = (ROOT / 'telegram_install_ui.py').read_text(encoding='utf-8')
    assert 'def _handle_telegram_confirmation(' in source
    assert '_handle_telegram_confirmation(message, level, bypass, set_menu_state, service)' in source
    assert 'if level != TELEGRAM_CONFIRM_LEVEL:' in source
    assert '_telegram_is_confirm_confirmation(message.text)' in source
    assert '_telegram_is_cancel_confirmation(message.text)' in source
    assert '_execute_confirmed_telegram_action(message.chat.id, action, reply_markup)' in source
    assert 'def _handle_install_menu_message(' in source
    assert '_telegram_install_action(message.text, include_web_only=True)' in source
    assert '_request_telegram_confirmation(message, set_menu_state, action)' in source
    for action in ('restart_services', 'reboot', 'dns_on', 'dns_off'):
        assert f"'{action}'" in source
    assert "_request_telegram_confirmation(message, set_menu_state, 'update_main')" in source
    for action in ('update_main', 'remove'):
        assert f"'{action}'" in install_source


def test_telegram_confirm_helpers():
    assert telegram_confirm.TELEGRAM_CONFIRM_LEVEL == 30
    assert telegram_confirm.telegram_is_confirm('✅ Подтвердить')
    assert telegram_confirm.telegram_is_cancel('Отмена')
    assert 'Обновить до последнего релиза?' in telegram_confirm.telegram_confirm_prompt('update_main')
    assert 'Перезагрузить роутер?' in telegram_confirm.telegram_confirm_prompt('reboot')


def test_telegram_auth_state_helpers():
    assert telegram_auth_state.normalize_username('@Admin') == 'admin'
    usernames, user_ids = telegram_auth_state.build_authorized_identities(['@Admin', '123'])
    assert usernames == {'admin'}
    assert user_ids == {123}
    states = {}
    lock = threading.Lock()
    assert telegram_auth_state.get_chat_menu_state(lock, states, 1) == {'level': 0, 'bypass': None}
    telegram_auth_state.set_chat_menu_state(lock, states, 1, level=8, bypass='vless')
    assert telegram_auth_state.get_chat_menu_state(lock, states, 1) == {'level': 8, 'bypass': 'vless'}
    assert telegram_auth_state.unauthorized_message_text('missing_username').startswith('У вашего Telegram-аккаунта')


def test_telegram_message_flow_helpers():
    message = _FakeMessage(chat_id=7)
    saved = []
    session = telegram_message_flow.private_menu_session(
        message,
        lambda chat_id: {'level': 2, 'bypass': 'vless'},
        lambda chat_id, level, bypass: saved.append((chat_id, level, bypass)),
        unset_marker=telegram_auth_state.MENU_STATE_UNSET,
    )
    assert telegram_message_flow.is_private_message(message)
    assert session.level == 2 and session.bypass == 'vless'
    session.set(3)
    session.set(telegram_auth_state.MENU_STATE_UNSET, 'vmess')
    session.set(new_bypass=None)
    assert saved == [(7, 3, 'vless'), (7, 3, 'vmess'), (7, 3, None)]
    calls = []
    assert telegram_message_flow.run_handlers(lambda: False, lambda: calls.append('hit') or True)
    assert calls == ['hit']
    assert not telegram_message_flow.is_private_message(_FakeMessage(chat_type='group'))


def test_telegram_jobs_helpers():
    payload = telegram_jobs.command_result_payload('-update', '42', 'service', 0, 'ok', now=lambda: 123.0)
    assert payload['chat_id'] == 42
    assert payload['finished_at'] == 123.0
    assert telegram_jobs.final_message('-update', 0).startswith('✅ Обновление')
    assert telegram_jobs.final_message('-remove', 1).startswith('⚠️ Команда')
    code = telegram_jobs.background_command_code('/opt/etc/bot/main.py', '-update', 'owner', 'repo', 42, 'service', 'branch')
    assert 'sys.path.insert' in code
    assert 'BYPASS_KEENETIC_COMMAND_WORKER' in code
    assert 'branch=' in code

    written = []
    popen_calls = []
    started, message = telegram_jobs.start_background_command(
        job_file='job.json',
        action='-update',
        repo_owner='owner',
        repo_name='repo',
        chat_id=42,
        menu_name='service',
        bot_source_path='/opt/etc/bot/main.py',
        sys_executable='python',
        read_json_file=lambda path, default=None: {},
        write_json_file=lambda path, payload: written.append((path, payload)),
        popen=lambda *args, **kwargs: popen_calls.append((args, kwargs)),
        now=lambda: 10.0,
    )
    assert started is True and message == ''
    assert written[0][1]['started_at'] == 10.0
    assert popen_calls


def test_telegram_install_ui_helpers():
    assert telegram_install_ui.install_action_for_text('🔰 Установка и удаление', include_web_only=True) == 'menu'
    assert telegram_install_ui.install_action_for_text('⬆️ Обновить до последнего релиза', include_web_only=True) == 'update_main'
    assert telegram_install_ui.install_action_for_text('♻️ Установка и переустановка', include_web_only=True) == 'update_main'
    assert telegram_install_ui.install_action_for_text('♻️ Переустановка (ветка independent)', include_web_only=True) is None
    assert telegram_install_ui.install_action_for_text('♻️ Переустановка (без Telegram бота)', include_web_only=True) is None


def test_telegram_recovery_redacts_bot_api_token():
    messages = []
    logs = []
    message = py_types.SimpleNamespace(chat=py_types.SimpleNamespace(id=7001, type='private'))

    try:
        raise RuntimeError('https://api.telegram.org/bot123456:secret-token/sendMessage failed')
    except RuntimeError as exc:
        telegram_message_flow.recover_private_message_error(
            message,
            exc,
            write_log=lambda text, mode='a': logs.append(text),
            reset_state=lambda chat_id: None,
            send_message=lambda chat_id, text, **kwargs: messages.append(text),
            main_markup=lambda: None,
            redact_text=lambda value: str(value).replace('123456:secret-token', '<redacted-token>'),
        )

    assert messages
    assert '<redacted-token>' in messages[-1]
    assert '123456:secret-token' not in messages[-1]
    assert logs
    assert '123456:secret-token' not in logs[-1]


def test_telegram_key_ui_helpers():
    assert telegram_key_ui.key_menu_rows()[0] == ('Shadowsocks', 'Vmess')
    assert ('📦 Пул ключей' in telegram_key_ui.key_menu_rows(include_pool=True)[3])
    assert telegram_key_ui.key_input_level('Trojan', trojan_level=13) == 13
    assert telegram_key_ui.key_input_level('Vless 2', trojan_level=13) == 12
    assert telegram_key_ui.key_install_protocol(13, trojan_level=13) == 'trojan'
    assert telegram_key_ui.key_install_protocol(12, trojan_level=13) == 'vless2'
    assert 'http://192.168.1.1:8080/' in telegram_key_ui.browser_hint('192.168.1.1', 8080)


def test_telegram_bot_menu_button_smoke():
    old_worker = os.environ.get('BYPASS_KEENETIC_COMMAND_WORKER')
    old_config = sys.modules.get('bot_config')
    old_bot_module = sys.modules.pop('bot', None)
    os.environ['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
    sys.modules['bot_config'] = py_types.SimpleNamespace(
        token='123456:test-token',
        usernames=['AllowedUser'],
        routerip='192.168.1.1',
        browser_port='8080',
        localportsh='1082',
        localporttrojan='10829',
        localportvmess='10810',
        localportvless='10811',
        dnsovertlsport='40500',
        dnsoverhttpsport='40508',
        default_proxy_mode='none',
        app_runtime_mode='advanced',
        fork_repo_owner='andruwko73',
        fork_repo_name='bypass_keenetic',
        fork_button_label='Fork by andruwko73',
        web_auth_token='',
        web_auth_disabled=True,
    )

    class _RecorderBot:
        def __init__(self):
            self.messages = []
            self.callbacks = []

        def send_message(self, chat_id, text, **kwargs):
            self.messages.append({'chat_id': chat_id, 'text': text, 'kwargs': kwargs})
            return py_types.SimpleNamespace(message_id=len(self.messages))

        def answer_callback_query(self, call_id, text='', **kwargs):
            self.callbacks.append({'id': call_id, 'text': text, 'kwargs': kwargs})

        def edit_message_reply_markup(self, *args, **kwargs):
            return None

    def message(text, username='AllowedUser', chat_id=7001):
        return py_types.SimpleNamespace(
            text=text,
            chat=py_types.SimpleNamespace(id=chat_id, type='private'),
            from_user=py_types.SimpleNamespace(id=777000, username=username),
        )

    try:
        bot_module = importlib.import_module('bot')
        bot_module.types = _FakeTypes
        recorder = _RecorderBot()
        bot_module.bot = recorder
        bot_module._send_telegram_readme_info = (
            lambda msg, reply_markup: recorder.send_message(msg.chat.id, 'INFO', reply_markup=reply_markup)
        )
        bot_module._send_key_status_report = (
            lambda msg, service_markup: recorder.send_message(msg.chat.id, 'STATUS', reply_markup=service_markup)
        )
        bot_module._send_remote_markdown_file = (
            lambda msg, path, error_message, reply_markup=None: (
                recorder.send_message(msg.chat.id, f'MARKDOWN:{path}', reply_markup=reply_markup) or True
            )
        )
        bot_module._format_pool_summary = lambda: 'POOL SUMMARY'
        bot_module._telegram_unblock_list_options = lambda: [
            ('Shadowsocks', 'shadowsocks'),
            ('Vmess', 'vmess'),
            ('Vless 1', 'vless'),
            ('Vless 2', 'vless-2'),
            ('Trojan', 'trojan'),
        ]

        assert bot_module.AUTHORIZED_USERNAMES == {'alloweduser'}
        assert bot_module.AUTHORIZED_USER_IDS == set()
        assert bot_module._build_main_menu_markup().rows == [
            ['🔰 Установка и удаление'],
            ['🔑 Ключи', '📝 Списки обхода'],
            ['📄 Информация', '⚙️ Сервис'],
        ]
        assert ['♻️ Перезагрузить сервисы', '‼️Перезагрузить роутер'] in bot_module._build_service_menu_markup().rows
        assert ['Shadowsocks', 'Vmess'] in bot_module._build_keys_menu_markup().rows
        assert ['✅ Подтвердить', 'Отмена'] in bot_module._build_telegram_confirm_markup().rows

        bot_module.start(message('/start'))
        assert recorder.messages[-1]['text'] == '✅ Добро пожаловать в меню!'
        bot_module.start(message('/start', username='WrongUser'))
        assert 'не являетесь' in recorder.messages[-1]['text']

        for text, expected in (
            ('🔰 Установка и удаление', '🔰 Установка и удаление'),
            ('🔑 Ключи', '🔑 Ключи'),
            ('📝 Списки обхода', '📝 Списки обхода'),
            ('📄 Информация', 'INFO'),
            ('⚙️ Сервис', '⚙️ Сервисное меню!'),
            ('‼️DNS Override', '‼️DNS Override!'),
            ('📊 Статус ключей', 'STATUS'),
            ('📦 Пул ключей', 'POOL SUMMARY'),
        ):
            bot_module._set_chat_menu_state(7001, level=0, bypass=None)
            bot_module.bot_message(message(text))
            assert recorder.messages[-1]['text'] == expected

        for text in ('♻️ Перезагрузить сервисы', '‼️Перезагрузить роутер', '✅ DNS Override ВКЛ', '❌ DNS Override ВЫКЛ'):
            bot_module._set_chat_menu_state(7001, level=0, bypass=None)
            bot_module.bot_message(message(text))
            assert '?' in recorder.messages[-1]['text']
            assert recorder.messages[-1]['kwargs']['reply_markup'].rows == [['✅ Подтвердить', 'Отмена'], ['🔙 Назад']]

        for text in ('Shadowsocks', 'Vmess', 'Vless 1', 'Vless 2', 'Trojan'):
            bot_module._set_chat_menu_state(7001, level=8, bypass=None)
            bot_module.bot_message(message(text))
            assert recorder.messages[-1]['text'] == telegram_key_ui.KEY_COPY_PROMPT

        bot_module._set_chat_menu_state(7001, level=8, bypass=None)
        bot_module.bot_message(message(telegram_key_ui.KEY_BROWSER_TEXT))
        assert 'http://192.168.1.1:8080/' in recorder.messages[-1]['text']
        bot_module._set_chat_menu_state(7001, level=8, bypass=None)
        bot_module.bot_message(message(telegram_key_ui.KEY_HELP_TEXT))
        assert recorder.messages[-1]['text'] == 'MARKDOWN:keys.md'
    finally:
        sys.modules.pop('bot', None)
        if old_bot_module is not None:
            sys.modules['bot'] = old_bot_module
        if old_config is None:
            sys.modules.pop('bot_config', None)
        else:
            sys.modules['bot_config'] = old_config
        if old_worker is None:
            os.environ.pop('BYPASS_KEENETIC_COMMAND_WORKER', None)
        else:
            os.environ['BYPASS_KEENETIC_COMMAND_WORKER'] = old_worker


def test_telegram_info_runtime_helpers():
    readme = (
        '# Title\n'
        '## Об этом форке\n'
        'Текст с [ссылкой](https://example.com) и `кодом`.\n'
        '\n'
        '![screen](screen.png)\n'
        '## Как работает бот на странице 192.168.1.1:8080\n'
        'Второй раздел.\n'
        '### Скриншоты интерфейса\n'
        'Не показывать.\n'
    )
    text = telegram_info_runtime.telegram_info_html(readme)
    assert '<b>Об этом форке</b>' in text
    assert '<a href="https://example.com">ссылкой</a>' in text
    assert 'screen.png' not in text
    assert 'Не показывать' not in text
    current_readme_text = telegram_info_runtime.telegram_info_html((ROOT / 'README.md').read_text(encoding='utf-8'))
    assert '<b>Возможности</b>' in current_readme_text
    assert 'Telegram-бот' in current_readme_text
    script_source = (ROOT / 'script.sh').read_text(encoding='utf-8')
    bootstrap_source = (ROOT / 'bootstrap' / 'install.sh').read_text(encoding='utf-8')
    assert 'README.md' in script_source.split('BOT_RUNTIME_MODULES=', 1)[1].split('\n', 1)[0]
    assert 'README.md' in bootstrap_source.split('BOT_RUNTIME_MODULES=', 1)[1].split('\n', 1)[0]
    assert telegram_info_runtime.telegram_info_html('').startswith('Информация временно недоступна')


def test_auto_failover_runtime_helpers():
    state = {'last_ok': 0.0, 'last_fail': 1.0, 'last_attempt': 0.0, 'in_progress': False}
    calls = []
    switched = auto_failover_runtime.attempt_auto_failover(
        state=state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: (False, 'fail'),
        load_current_keys=lambda: {'vless': 'active'},
        load_key_pools=lambda: {'vless': ['active', 'next']},
        failover_candidates=lambda pools, mode, active, protocols=(), **kwargs: [('vless', 'next')],
        find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
        install_key_for_protocol=lambda proto, key, verify=True: calls.append(('install', proto, key, verify)) or 'ok',
        update_proxy=lambda proto: calls.append(('update', proto)),
        set_active_key=lambda proto, key: calls.append(('active', proto, key)),
        record_key_probe=lambda proto, key, **kwargs: calls.append(('probe', proto, key, kwargs)),
        log=lambda message: calls.append(('log', message)),
        grace_seconds=10,
        switch_cooldown_seconds=30,
        time_provider=iter([20.0, 21.0]).__next__,
    )
    assert switched is True
    assert state['last_ok'] == 21.0
    assert state['last_fail'] == 0.0
    assert ('update', 'vless') in calls
    assert any(call[0] == 'probe' and call[3] == {'tg_ok': True, 'yt_ok': None} for call in calls)
    transient_calls = []
    transient_state = {'last_ok': 0.0, 'last_fail': 1.0, 'last_attempt': 0.0, 'in_progress': False}
    assert auto_failover_runtime.attempt_auto_failover(
        state=transient_state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: (False, 'SSLEOFError: UNEXPECTED_EOF_WHILE_READING'),
        load_current_keys=lambda: {'vless': 'active'},
        load_key_pools=lambda: {'vless': ['active', 'next']},
        failover_candidates=lambda pools, mode, active, protocols=(), **kwargs: [('vless', 'next')],
        find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
        install_key_for_protocol=lambda proto, key, verify=True: transient_calls.append(('install', proto, key)),
        update_proxy=lambda proto: transient_calls.append(('update', proto)),
        set_active_key=lambda proto, key: transient_calls.append(('active', proto, key)),
        record_key_probe=lambda proto, key, **kwargs: transient_calls.append(('probe', proto, key, kwargs)),
        log=lambda message: transient_calls.append(('log', message)),
        grace_seconds=10,
        switch_cooldown_seconds=30,
        key_probe_cache={'active-hash': {'tg_ok': True, 'ts': 19.0}},
        hash_key=lambda key: f'{key}-hash',
        is_transient_failure=lambda text: 'SSLEOFError' in text,
        transient_success_ttl=60,
        time_provider=lambda: 20.0,
    ) is False
    assert transient_state['last_fail'] == 0.0
    assert not any(call[0] == 'install' for call in transient_calls)
    assert any(call[0] == 'log' and 'временный сбой' in call[1] for call in transient_calls)
    last_ok_calls = []
    last_ok_state = {'last_ok': 19.0, 'last_fail': 1.0, 'last_attempt': 0.0, 'in_progress': False}
    assert auto_failover_runtime.attempt_auto_failover(
        state=last_ok_state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: (False, 'Read timed out'),
        load_current_keys=lambda: (_ for _ in ()).throw(AssertionError('recent last_ok should skip key lookup')),
        load_key_pools=lambda: {'vless': ['active', 'next']},
        failover_candidates=lambda pools, mode, active, protocols=(), **kwargs: [('vless', 'next')],
        find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
        install_key_for_protocol=lambda proto, key, verify=True: last_ok_calls.append(('install', proto, key)),
        update_proxy=lambda proto: last_ok_calls.append(('update', proto)),
        set_active_key=lambda proto, key: last_ok_calls.append(('active', proto, key)),
        record_key_probe=lambda proto, key, **kwargs: last_ok_calls.append(('probe', proto, key, kwargs)),
        log=lambda message: last_ok_calls.append(('log', message)),
        grace_seconds=10,
        switch_cooldown_seconds=30,
        is_transient_failure=lambda text: 'timed out' in text,
        transient_success_ttl=60,
        time_provider=lambda: 20.0,
    ) is False
    assert last_ok_state['last_fail'] == 0.0
    assert not any(call[0] == 'install' for call in last_ok_calls)
    recent_probe_calls = []
    recent_probe_state = {'last_ok': 0.0, 'last_fail': 1.0, 'last_attempt': 0.0, 'in_progress': False}
    assert auto_failover_runtime.attempt_auto_failover(
        state=recent_probe_state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: (False, 'TLS EOF'),
        load_current_keys=lambda: {'vless': 'active'},
        load_key_pools=lambda: {'vless': ['active', 'next']},
        failover_candidates=lambda pools, mode, active, protocols=(), **kwargs: [('vless', 'next')],
        find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
        install_key_for_protocol=lambda proto, key, verify=True: recent_probe_calls.append(('install', proto, key)),
        update_proxy=lambda proto: recent_probe_calls.append(('update', proto)),
        set_active_key=lambda proto, key: recent_probe_calls.append(('active', proto, key)),
        record_key_probe=lambda proto, key, **kwargs: recent_probe_calls.append(('probe', proto, key, kwargs)),
        log=lambda message: recent_probe_calls.append(('log', message)),
        grace_seconds=10,
        switch_cooldown_seconds=30,
        key_probe_cache={'active-hash': {'tg_ok': True, 'ts': 19.0}},
        hash_key=lambda key: f'{key}-hash',
        recent_success_ttl=60,
        time_provider=lambda: 20.0,
    ) is False
    assert recent_probe_state['last_fail'] == 0.0
    assert not any(call[0] == 'install' for call in recent_probe_calls)
    assert any(call[0] == 'log' and 'recently marked working' in call[1] for call in recent_probe_calls)
    confirm_calls = []
    confirm_state = {'last_ok': 0.0, 'last_fail': 1.0, 'last_attempt': 0.0, 'in_progress': False}
    confirm_results = iter([(False, 'first fail'), (True, 'confirm ok')])
    assert auto_failover_runtime.attempt_auto_failover(
        state=confirm_state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: confirm_calls.append(('check', kwargs)) or next(confirm_results),
        load_current_keys=lambda: (_ for _ in ()).throw(AssertionError('confirmed active key should skip key lookup')),
        load_key_pools=lambda: {'vless': ['active', 'next']},
        failover_candidates=lambda pools, mode, active, protocols=(), **kwargs: [('vless', 'next')],
        find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
        install_key_for_protocol=lambda proto, key, verify=True: confirm_calls.append(('install', proto, key)),
        update_proxy=lambda proto: confirm_calls.append(('update', proto)),
        set_active_key=lambda proto, key: confirm_calls.append(('active', proto, key)),
        record_key_probe=lambda proto, key, **kwargs: confirm_calls.append(('probe', proto, key, kwargs)),
        log=lambda message: confirm_calls.append(('log', message)),
        grace_seconds=10,
        switch_cooldown_seconds=30,
        check_timeouts=(2, 3),
        time_provider=lambda: 20.0,
    ) is False
    assert confirm_state['last_fail'] == 0.0
    assert confirm_calls[:2] == [
        ('check', {'connect_timeout': 2, 'read_timeout': 3}),
        ('check', {'connect_timeout': 5.0, 'read_timeout': 8.0}),
    ]
    assert not any(call[0] == 'install' for call in confirm_calls)
    locked_calls = []
    locked_state = {'last_ok': 0.0, 'last_fail': 1.0, 'last_attempt': 0.0, 'in_progress': False}
    assert auto_failover_runtime.attempt_auto_failover(
        state=locked_state,
        pool_probe_locked=lambda: True,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: locked_calls.append('check') or (False, 'fail'),
        load_current_keys=lambda: {'vless': 'active'},
        load_key_pools=lambda: {'vless': ['active', 'next']},
        failover_candidates=lambda pools, mode, active, protocols=(), **kwargs: [('vless', 'next')],
        find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
        install_key_for_protocol=lambda proto, key, verify=True: None,
        update_proxy=lambda proto: None,
        set_active_key=lambda proto, key: None,
        record_key_probe=lambda proto, key, **kwargs: None,
        log=lambda message: None,
        grace_seconds=10,
        switch_cooldown_seconds=30,
        time_provider=lambda: 20.0,
    ) is False
    assert locked_calls == []
    startup_hold_calls = []
    startup_hold_state = {
        'started_at': 95.0,
        'last_ok': 0.0,
        'last_fail': 1.0,
        'last_attempt': 0.0,
        'in_progress': False,
    }
    assert auto_failover_runtime.attempt_auto_failover(
        state=startup_hold_state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: startup_hold_calls.append('check') or (False, 'fail'),
        load_current_keys=lambda: {'vless': 'active'},
        load_key_pools=lambda: {'vless': ['active', 'next']},
        failover_candidates=lambda pools, mode, active, protocols=(), **kwargs: [('vless', 'next')],
        find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
        install_key_for_protocol=lambda proto, key, verify=True: startup_hold_calls.append(('install', proto, key)),
        update_proxy=lambda proto: startup_hold_calls.append(('update', proto)),
        set_active_key=lambda proto, key: startup_hold_calls.append(('active', proto, key)),
        record_key_probe=lambda proto, key, **kwargs: startup_hold_calls.append(('probe', proto, key, kwargs)),
        log=lambda message: startup_hold_calls.append(('log', message)),
        grace_seconds=10,
        switch_cooldown_seconds=30,
        startup_hold_seconds=180,
        time_provider=lambda: 100.0,
    ) is False
    assert 'check' in startup_hold_calls
    assert not any(isinstance(call, tuple) and call[0] == 'install' for call in startup_hold_calls)
    repair_calls = []
    repair_state = {'last_ok': 0.0, 'last_fail': 1.0, 'last_attempt': 0.0, 'in_progress': False}
    repair_checks = iter([(False, 'first fail'), (True, 'after repair')])
    assert auto_failover_runtime.attempt_auto_failover(
        state=repair_state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: repair_calls.append(('check', kwargs)) or next(repair_checks),
        load_current_keys=lambda: {'vless': 'active'},
        load_key_pools=lambda: {'vless': ['active', 'next']},
        failover_candidates=lambda pools, mode, active, protocols=(), **kwargs: [('vless', 'next')],
        find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
        install_key_for_protocol=lambda proto, key, verify=True: repair_calls.append(('install', proto, key)),
        update_proxy=lambda proto: repair_calls.append(('update', proto)),
        set_active_key=lambda proto, key: repair_calls.append(('active', proto, key)),
        record_key_probe=lambda proto, key, **kwargs: repair_calls.append(('probe', proto, key, kwargs)),
        log=lambda message: repair_calls.append(('log', message)),
        grace_seconds=10,
        switch_cooldown_seconds=30,
        repair_active_proxy=lambda proto, message: repair_calls.append(('repair', proto, message)) or True,
        time_provider=lambda: 20.0,
    ) is False
    assert repair_state['last_fail'] == 0.0
    assert any(call[0] == 'repair' for call in repair_calls)
    assert not any(call[0] == 'install' for call in repair_calls)
    assert any(call[0] == 'log' and 'endpoint repair restored' in call[1] for call in repair_calls)


def test_proxy_apply_runtime_helpers():
    settings = proxy_apply_runtime.proxy_apply_settings('/opt/etc/init.d/S24xray', {
        'shadowsocks': 10815,
        'vmess': 10810,
        'vless': 10811,
        'vless2': 10813,
        'trojan': 10816,
    })
    youtube_calls = []
    def proxy_apply_youtube_check(proxy, **kwargs):
        youtube_calls.append(kwargs['url'])
        return kwargs['url'] in (
            'https://www.youtube.com/generate_204',
            'https://i.ytimg.com/generate_204',
        ), 'probe'

    youtube_ok, _ = proxy_apply_runtime.check_youtube_health(
        proxy_apply_youtube_check,
        'proxy-url',
        timeouts=(1, 1),
    )
    assert youtube_ok is True
    assert youtube_calls == list(proxy_apply_runtime.YOUTUBE_HEALTHCHECK_URLS[:3])

    primary_transient_ok, primary_transient_message = proxy_apply_runtime.check_youtube_health(
        lambda proxy, **kwargs: (
            kwargs['url'] != proxy_apply_runtime.YOUTUBE_HEALTHCHECK_URLS[0],
            'primary eof',
        ),
        'proxy-url',
        timeouts=(1, 1),
    )
    assert primary_transient_ok is True
    assert primary_transient_message == 'YouTube endpoints confirmed without primary'

    commands = []
    sleeps = []
    records = []
    result = proxy_apply_runtime.apply_installed_proxy_runtime(
        'vless',
        'key',
        settings=settings,
        app_mode_noun='режим бота',
        load_proxy_mode=lambda: 'none',
        proxy_mode_label=lambda mode: 'Без прокси',
        proxy_url_getter=lambda proto: 'proxy-url',
        build_diagnostics=lambda proto, key: 'diag',
        ensure_service_port=lambda port, restart_cmd, **kwargs: True,
        check_local_endpoint=lambda proto, port: (True, 'SOCKS ok.'),
        check_telegram_api=lambda proxy, **kwargs: (True, 'tg ok'),
        check_http=lambda proxy, **kwargs: (False, 'yt fail'),
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        run_command=commands.append,
        sleep=sleeps.append,
    )
    assert result.startswith('✅ Vless 1 ключ сохранён.')
    assert commands == ['/opt/etc/init.d/S24xray restart']
    assert sleeps == []
    assert records == [('vless', 'key', {'tg_ok': True, 'yt_ok': False})]
    pending = proxy_apply_runtime.apply_installed_proxy_runtime(
        'trojan',
        'key',
        settings=settings,
        app_mode_noun='режим бота',
        load_proxy_mode=lambda: 'trojan',
        proxy_mode_label=lambda mode: 'Trojan',
        proxy_url_getter=lambda proto: 'unused',
        build_diagnostics=lambda proto, key: '',
        ensure_service_port=lambda port, restart_cmd, **kwargs: True,
        check_local_endpoint=lambda proto, port: (True, 'SOCKS ok.'),
        check_telegram_api=lambda proxy, **kwargs: (_ for _ in ()).throw(AssertionError('must not verify')),
        verify=False,
        run_command=lambda command: None,
        sleep=lambda seconds: None,
    )
    assert 'в фоне' in pending
    vless2_records = []
    vless2_result = proxy_apply_runtime.apply_installed_proxy_runtime(
        'vless2',
        'yt-key',
        settings=settings,
        app_mode_noun='режим бота',
        load_proxy_mode=lambda: 'vless',
        proxy_mode_label=lambda mode: 'Vless 1',
        proxy_url_getter=lambda proto: 'proxy-url',
        build_diagnostics=lambda proto, key: 'diag',
        ensure_service_port=lambda port, restart_cmd, **kwargs: True,
        check_local_endpoint=lambda proto, port: (True, 'SOCKS ok.'),
        check_telegram_api=lambda proxy, **kwargs: (_ for _ in ()).throw(AssertionError('telegram must not block vless2 youtube apply')),
        check_http=lambda proxy, **kwargs: (True, 'yt ok'),
        record_key_probe=lambda proto, key, **kwargs: vless2_records.append((proto, key, kwargs)),
        run_command=lambda command: None,
        sleep=lambda seconds: None,
    )
    assert 'YouTube' in vless2_result
    assert vless2_records == [('vless2', 'yt-key', {'tg_ok': None, 'yt_ok': True})]

    routed_vless_records = []
    routed_vless_result = proxy_apply_runtime.apply_installed_proxy_runtime(
        'vless',
        'yt-on-vless1',
        settings=settings,
        app_mode_noun='СЂРµР¶РёРј Р±РѕС‚Р°',
        load_proxy_mode=lambda: 'vless2',
        proxy_mode_label=lambda mode: 'Vless 2',
        proxy_url_getter=lambda proto: 'proxy-url',
        build_diagnostics=lambda proto, key: 'diag',
        ensure_service_port=lambda port, restart_cmd, **kwargs: True,
        check_local_endpoint=lambda proto, port: (True, 'SOCKS ok.'),
        check_telegram_api=lambda proxy, **kwargs: (_ for _ in ()).throw(AssertionError('telegram must not block selected youtube route')),
        check_http=lambda proxy, **kwargs: (True, 'yt ok'),
        record_key_probe=lambda proto, key, **kwargs: routed_vless_records.append((proto, key, kwargs)),
        youtube_route_protocol_getter=lambda: 'vless',
        run_command=lambda command: None,
        sleep=lambda seconds: None,
    )
    assert 'YouTube' in routed_vless_result
    assert routed_vless_records == [('vless', 'yt-on-vless1', {'tg_ok': None, 'yt_ok': True})]


def test_pool_probe_controller_helpers():
    progress = pool_probe_controller.PoolProbeProgress()
    assert progress.snapshot()['running'] is False
    progress.update(running=True, checked=2)
    assert progress.snapshot()['checked'] == 2
    assert pool_probe_controller.pool_probe_progress_label({'scope': 'protocol'}) == 'Проверка выбранного пула'
    assert pool_probe_controller.failed_custom_probe_results([{'id': 'tg'}, {'label': 'empty'}]) == {'tg': False}
    assert pool_probe_controller.pool_probe_timeout_budget(
        [{'urls': ['https://a', 'https://b', 'https://ignored']}],
        2,
        1,
        (1, 2, 3, 4, 5, 6, 10, 20),
    ) == 113.0
    assert pool_probe_controller.pool_probe_timeout_budget(
        [{'urls': ['https://a', 'https://b']}],
        1,
        1,
        (1, 2, 3, 4, 5, 6, 10, 20, 7, 8),
    ) == 119.0
    meminfo_path = ROOT / 'tests' / '_meminfo.tmp'
    try:
        meminfo_path.write_text('MemAvailable:        12345 kB\n', encoding='utf-8')
        assert pool_probe_controller.available_memory_kb(meminfo_path) == 12345
    finally:
        meminfo_path.unlink(missing_ok=True)
    selected, checks = pool_probe_controller.select_pool_probe_tasks(
        [('vless', 'fresh'), ('vless', 'new'), ('bad', 'skip'), ('vless', 'new')],
        protocol_order=('vless',),
        custom_checks=[{'id': 'tg'}],
        cache={'h:fresh': {'fresh': True}},
        hash_key=lambda value: 'h:' + value,
        is_fresh=lambda probe, **kwargs: bool(probe and probe.get('fresh')),
        stale_only=True,
    )
    assert selected == [('vless', 'new')]
    assert checks == [{'id': 'tg'}]
    assert pool_probe_controller.filter_active_probe_tasks(
        [('vless', 'active'), ('vmess', 'old')],
        {'vless': 'active', 'vmess': 'new'},
    ) == [('vless', 'active')]

    state = {}
    invalidated = []
    collected = []
    times = iter([10.0, 20.0])

    def set_progress(**updates):
        state.update(updates)

    def run_worker(tasks, checks, set_checked, invalidate_caches):
        assert tasks == [('vless', 'key')]
        assert checks == [{'id': 'custom'}]
        set_checked(1)
        invalidate_caches()
        return 1, len(tasks)

    started, count = pool_probe_controller.start_pool_probe_worker(
        [('vless', 'key')],
        [{'id': 'custom'}],
        scope='manual_all',
        lock=threading.Lock(),
        set_progress=set_progress,
        run_worker=run_worker,
        invalidate_caches=lambda: invalidated.append('cache'),
        time_provider=lambda: next(times),
        collect_garbage=lambda: collected.append('gc'),
        thread_factory=_InlineThread,
    )
    assert started is True
    assert count == 1
    assert state['running'] is False
    assert state['checked'] == 1
    assert state['total'] == 1
    assert state['started_at'] == 10.0
    assert state['finished_at'] == 20.0
    assert invalidated == ['cache', 'cache']
    assert collected == ['gc']

    state = {}
    checked_updates = []
    times = iter([30.0, 40.0])

    def set_resumed_progress(**updates):
        state.update(updates)
        if 'checked' in updates:
            checked_updates.append(updates['checked'])

    started, count = pool_probe_controller.start_pool_probe_worker(
        [('vless', 'remaining-1'), ('vless', 'remaining-2')],
        [],
        scope='manual_all',
        lock=threading.Lock(),
        set_progress=set_resumed_progress,
        run_worker=lambda tasks, checks, set_checked, invalidate_caches: (
            set_checked(1) or set_checked(2) or (2, len(tasks))
        ),
        invalidate_caches=lambda: None,
        time_provider=lambda: next(times),
        thread_factory=_InlineThread,
        initial_checked=37,
        total_count=139,
        started_at=12.0,
    )
    assert started is True
    assert count == 2
    assert checked_updates == [37, 38, 39, 39]
    assert state['checked'] == 39
    assert state['total'] == 139
    assert state['started_at'] == 12.0

    records = []
    tg_results = iter([(False, ''), (False, '')])
    pool_probe_controller.check_pool_key_through_proxy(
        'vless',
        'key',
        [{'id': 'custom'}],
        'proxy',
        check_telegram_api=lambda proxy, **kwargs: next(tg_results),
        check_http=lambda proxy, **kwargs: (False, ''),
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        probe_custom_targets=lambda proxy, custom_checks=None: {'custom': True},
        retry_delay_seconds=0,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        sleep=lambda seconds: None,
    )
    assert records == [
        ('vless', 'key', {'tg_ok': False, 'yt_ok': False}),
        ('vless', 'key', {'custom': {'custom': False}, 'custom_checks': [{'id': 'custom'}]}),
    ]

    records = []
    http_calls = []
    yt_results = iter([(True, 'ok'), (False, 'timeout'), (True, 'ok')])
    def check_http_for_pool_key(proxy, **kwargs):
        http_calls.append(kwargs)
        if kwargs.get('url') == 'https://web.telegram.org/':
            return True, 'telegram ok'
        return next(yt_results)

    pool_probe_controller.check_pool_key_through_proxy(
        'vless',
        'key',
        [],
        'proxy',
        check_telegram_api=lambda proxy, **kwargs: (True, ''),
        check_http=check_http_for_pool_key,
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        probe_custom_targets=lambda proxy, custom_checks=None: {},
        retry_delay_seconds=0,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        http_retry_timeouts=(6, 10),
        sleep=lambda seconds: None,
    )
    assert http_calls == [
        {'url': 'https://web.telegram.org/', 'connect_timeout': 3, 'read_timeout': 4},
        {'url': 'https://www.youtube.com/generate_204', 'connect_timeout': 3, 'read_timeout': 4},
        {'url': 'https://redirector.googlevideo.com/generate_204', 'connect_timeout': 6, 'read_timeout': 10},
        {'url': 'https://i.ytimg.com/generate_204', 'connect_timeout': 6, 'read_timeout': 10},
    ]
    assert records == [('vless', 'key', {'tg_ok': True, 'yt_ok': True})]

    records = []
    http_calls = []

    def check_http_with_app_telegram(proxy, **kwargs):
        http_calls.append(kwargs)
        url = kwargs.get('url')
        if url == 'https://web.telegram.org/':
            return True, 'telegram app ok'
        return True, 'ok'

    pool_probe_controller.check_pool_key_through_proxy(
        'vless',
        'app-telegram-key',
        [],
        'proxy',
        check_telegram_api=lambda proxy, **kwargs: (False, 'bot api failed'),
        check_http=check_http_with_app_telegram,
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        probe_custom_targets=lambda proxy, custom_checks=None: {},
        retry_delay_seconds=0,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        sleep=lambda seconds: None,
    )
    assert http_calls[:1] == [{'url': 'https://web.telegram.org/', 'connect_timeout': 3, 'read_timeout': 4}]
    assert records == [('vless', 'app-telegram-key', {'tg_ok': True, 'yt_ok': True})]

    records = []
    yt_results = iter([(True, 'ok'), (True, 'ok')])

    def check_http_without_app_telegram(proxy, **kwargs):
        if kwargs.get('url') in pool_probe_controller.TELEGRAM_HEALTHCHECK_URLS:
            return False, 'telegram app fail'
        return next(yt_results)

    pool_probe_controller.check_pool_key_through_proxy(
        'vless2',
        'youtube-only',
        [],
        'proxy',
        check_telegram_api=lambda proxy, **kwargs: (False, 'telegram fail'),
        check_http=check_http_without_app_telegram,
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        probe_custom_targets=lambda proxy, custom_checks=None: {},
        retry_delay_seconds=0,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        sleep=lambda seconds: None,
    )
    assert records == [('vless2', 'youtube-only', {'tg_ok': 'unknown', 'yt_ok': True})]

    records = []
    yt_results = iter([(True, 'ok'), (True, 'ok')])
    pool_probe_controller.check_pool_key_through_proxy(
        'vless2',
        'bot-mode-vless2',
        [],
        'proxy',
        check_telegram_api=lambda proxy, **kwargs: (False, 'telegram fail'),
        check_http=check_http_without_app_telegram,
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        probe_custom_targets=lambda proxy, custom_checks=None: {},
        retry_delay_seconds=0,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        telegram_required=True,
        sleep=lambda seconds: None,
    )
    assert records == [('vless2', 'bot-mode-vless2', {'tg_ok': False, 'yt_ok': True})]

    records = []
    yt_results = iter([(True, 'ok'), (True, 'ok')])
    telegram_web_attempts = []

    def check_http_retry_required_telegram(proxy, **kwargs):
        url = kwargs.get('url')
        if url == 'https://web.telegram.org/':
            telegram_web_attempts.append(kwargs)
            return len(telegram_web_attempts) >= 2, 'telegram app retry'
        if url in pool_probe_controller.TELEGRAM_HEALTHCHECK_URLS:
            return False, 'telegram app fail'
        return next(yt_results)

    pool_probe_controller.check_pool_key_through_proxy(
        'vless',
        'bot-mode-retry',
        [],
        'proxy',
        check_telegram_api=lambda proxy, **kwargs: (False, 'telegram api fail'),
        check_http=check_http_retry_required_telegram,
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        probe_custom_targets=lambda proxy, custom_checks=None: {},
        retry_delay_seconds=0,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        http_retry_timeouts=(6, 10),
        telegram_required=True,
        sleep=lambda seconds: None,
    )
    assert records == [('vless', 'bot-mode-retry', {'tg_ok': True, 'yt_ok': True})]
    assert telegram_web_attempts == [
        {'url': 'https://web.telegram.org/', 'connect_timeout': 3, 'read_timeout': 4},
        {'url': 'https://web.telegram.org/', 'connect_timeout': 6, 'read_timeout': 10},
    ]


def test_pool_probe_runner_failover_candidate():
    records = []
    logs = []
    stopped = []
    cleaned = []

    def validate_outbound(proto, key_value, tag, proxy_outbound_from_key):
        assert tag == 'proxy-failover-validate'
        if key_value == 'bad':
            raise ValueError('bad key')

    failover_http_calls = []
    result = pool_probe_runner.find_pool_failover_candidate(
        [('vless', 'bad'), ('vless', 'ok')],
        service='telegram',
        batch_size=2,
        test_port='1200',
        proxy_outbound_from_key=lambda *args, **kwargs: {},
        wait_for_socks5=lambda port, timeout=6: port == '1200',
        check_telegram_api=lambda proxy, **kwargs: (True, 'ok'),
        check_http=lambda proxy, **kwargs: failover_http_calls.append(kwargs) or (True, 'telegram ok'),
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        proto_label=lambda proto: proto,
        log=logs.append,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        validate_outbound=validate_outbound,
        build_config_batch=lambda valid_batch, test_port, proxy_outbound_from_key: {'valid': valid_batch},
        start_xray=lambda config: ('process', 'config.json'),
        stop_xray=lambda process, config_path: stopped.append((process, config_path)),
        cleanup_runtime=lambda kill_processes=False: cleaned.append(kill_processes),
        collect_garbage=lambda: None,
    )
    assert result == ('vless', 'ok', True, None)
    assert records == [('vless', 'ok', {'tg_ok': True, 'yt_ok': None})]
    assert failover_http_calls == [{'url': 'https://web.telegram.org/', 'connect_timeout': 3, 'read_timeout': 4}]
    assert stopped == [('process', 'config.json')]
    assert cleaned == [True]
    assert 'не подготовлен' in logs[0]

    api_only_records = []
    api_only_result = pool_probe_runner.find_pool_failover_candidate(
        [('vless', 'api-only')],
        service='telegram',
        batch_size=1,
        test_port='1250',
        proxy_outbound_from_key=lambda *args, **kwargs: {},
        wait_for_socks5=lambda port, timeout=6: True,
        check_telegram_api=lambda proxy, **kwargs: (True, 'api ok'),
        check_http=lambda proxy, **kwargs: (False, 'web timeout'),
        record_key_probe=lambda proto, key, **kwargs: api_only_records.append((proto, key, kwargs)),
        proto_label=lambda proto: proto,
        log=logs.append,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        validate_outbound=validate_outbound,
        build_config_batch=lambda valid_batch, test_port, proxy_outbound_from_key: {'valid': valid_batch},
        start_xray=lambda config: ('api-process', 'api-config.json'),
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        collect_garbage=lambda: None,
    )
    assert api_only_result is None
    assert api_only_records == [('vless', 'api-only', {'tg_ok': False, 'yt_ok': None})]

    youtube_records = []
    youtube_result = pool_probe_runner.find_pool_failover_candidate(
        [('vless2', 'yt-ok')],
        service='youtube',
        batch_size=1,
        test_port='1300',
        proxy_outbound_from_key=lambda *args, **kwargs: {},
        wait_for_socks5=lambda port, timeout=6: True,
        check_telegram_api=lambda proxy, **kwargs: (_ for _ in ()).throw(AssertionError('telegram must not block youtube failover')),
        check_http=lambda proxy, **kwargs: (True, 'yt ok'),
        record_key_probe=lambda proto, key, **kwargs: youtube_records.append((proto, key, kwargs)),
        proto_label=lambda proto: proto,
        log=logs.append,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        validate_outbound=validate_outbound,
        build_config_batch=lambda valid_batch, test_port, proxy_outbound_from_key: {'valid': valid_batch},
        start_xray=lambda config: ('yt-process', 'yt-config.json'),
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        collect_garbage=lambda: None,
    )
    assert youtube_result == ('vless2', 'yt-ok', None, True)
    assert youtube_records == [('vless2', 'yt-ok', {'tg_ok': None, 'yt_ok': True})]

    cancel_event = threading.Event()
    cancel_event.set()
    remaining = []
    checked, total = pool_probe_runner.run_pool_probe_worker(
        [('vless', 'left')],
        [],
        batch_size=1,
        concurrency=1,
        delay_seconds=0,
        min_available_kb=0,
        test_port='1200',
        available_memory_kb=lambda: 999999,
        log=logs.append,
        proto_label=lambda proto: proto,
        hash_key=_hash_key,
        set_checked=lambda value: None,
        validate_outbound=lambda proto, key: (_ for _ in ()).throw(AssertionError('cancelled')),
        failed_custom_results=lambda checks: {},
        record_key_probe=lambda proto, key, **kwargs: None,
        start_xray_for_batch=lambda batch: None,
        wait_for_socks5=lambda port, timeout=6: True,
        check_pool_key=lambda proto, key, checks, proxy_url: None,
        timeout_budget=lambda checks, task_count, workers: 1,
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        invalidate_caches=lambda: None,
        cancel_event=cancel_event,
        on_cancelled_remaining=remaining.extend,
    )
    assert (checked, total) == (0, 1)
    assert remaining == [('vless', 'left')]

    memory_values = iter([999999, 1000, 1000])
    time_values = iter([0.0, 2.0])
    started_batches = []
    stopped = []
    cleaned = []
    memory_logs = []
    paused_remaining = []
    checked, total = pool_probe_runner.run_pool_probe_worker(
        [('vless', 'low-memory')],
        [],
        batch_size=1,
        concurrency=1,
        delay_seconds=0,
        min_available_kb=190000,
        test_port='1200',
        available_memory_kb=lambda: next(memory_values),
        log=memory_logs.append,
        proto_label=lambda proto: proto,
        hash_key=_hash_key,
        set_checked=lambda value: None,
        validate_outbound=lambda proto, key: None,
        failed_custom_results=lambda checks: {},
        record_key_probe=lambda proto, key, **kwargs: None,
        start_xray_for_batch=lambda batch: started_batches.append(list(batch)) or ('process', 'config.json'),
        wait_for_socks5=lambda port, timeout=6: (_ for _ in ()).throw(AssertionError('memory guard should stop before socks wait')),
        check_pool_key=lambda proto, key, checks, proxy_url: None,
        timeout_budget=lambda checks, task_count, workers: 1,
        stop_xray=lambda process, config_path: stopped.append((process, config_path)),
        cleanup_runtime=lambda kill_processes=False: cleaned.append(kill_processes),
        invalidate_caches=lambda: None,
        on_cancelled_remaining=paused_remaining.extend,
        low_memory_delay_seconds=0,
        max_low_memory_wait_seconds=1,
        sleep=lambda seconds: None,
        time_provider=lambda: next(time_values),
    )
    assert (checked, total) == (0, 1)
    assert started_batches == [[('vless', 'low-memory')]]
    assert stopped == [('process', 'config.json')]
    assert cleaned == [True]
    assert paused_remaining == [('vless', 'low-memory')]
    assert '190000' in memory_logs[-1]

    cpu_values = iter([92.0, 20.0])
    time_values = iter([0.0, 1.0])
    cpu_notes = []
    cpu_sleeps = []
    cpu_processed = []
    checked, total = pool_probe_runner.run_pool_probe_worker(
        [('vless', 'cpu-guard')],
        [],
        batch_size=1,
        concurrency=1,
        delay_seconds=0,
        min_available_kb=0,
        test_port='1200',
        available_memory_kb=lambda: 999999,
        log=logs.append,
        proto_label=lambda proto: proto,
        hash_key=_hash_key,
        set_checked=lambda value: None,
        validate_outbound=lambda proto, key: None,
        failed_custom_results=lambda checks: {},
        record_key_probe=lambda proto, key, **kwargs: None,
        start_xray_for_batch=lambda batch: ('process', 'config.json'),
        wait_for_socks5=lambda port, timeout=6: True,
        check_pool_key=lambda proto, key, checks, proxy_url: cpu_processed.append((proto, key)),
        timeout_budget=lambda checks, task_count, workers: 1,
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        invalidate_caches=lambda: None,
        set_note=cpu_notes.append,
        cpu_busy_percent=lambda: next(cpu_values),
        max_cpu_percent=70.0,
        high_cpu_delay_seconds=5.0,
        max_high_cpu_wait_seconds=45.0,
        sleep=cpu_sleeps.append,
        time_provider=lambda: next(time_values),
    )
    assert (checked, total) == (1, 1)
    assert cpu_processed == [('vless', 'cpu-guard')]
    assert cpu_sleeps == [5.0]
    assert any('CPU' in note and '70' in note for note in cpu_notes)

    failure_records = []
    checked_values = []
    checked, total = pool_probe_runner.run_pool_probe_worker(
        [('vless', 'sockless')],
        [{'id': 'custom'}],
        batch_size=1,
        concurrency=1,
        delay_seconds=0,
        min_available_kb=0,
        test_port='1200',
        available_memory_kb=lambda: 999999,
        log=logs.append,
        proto_label=lambda proto: proto,
        hash_key=_hash_key,
        set_checked=checked_values.append,
        validate_outbound=lambda proto, key: None,
        failed_custom_results=lambda checks: {'custom': False},
        record_key_probe=lambda proto, key, **kwargs: failure_records.append((proto, key, kwargs)),
        start_xray_for_batch=lambda batch: ('process', 'config.json'),
        wait_for_socks5=lambda port, timeout=6: False,
        check_pool_key=lambda proto, key, checks, proxy_url: (_ for _ in ()).throw(AssertionError('not ready')),
        timeout_budget=lambda checks, task_count, workers: 1,
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        invalidate_caches=lambda: None,
    )
    assert (checked, total) == (1, 1)
    assert checked_values == [1]
    assert failure_records == [
        ('vless', 'sockless', {'tg_ok': False, 'yt_ok': False, 'custom': {'custom': False}}),
    ]

    timeout_records = []
    timeout_logs = []
    timeout_started = threading.Event()
    timeout_release = threading.Event()

    def slow_check(proto, key, checks, proxy_url, record_key_probe=None):
        timeout_started.set()
        timeout_release.wait(timeout=1)
        if record_key_probe:
            record_key_probe(proto, key, tg_ok=False, yt_ok=False)

    checked, total = pool_probe_runner.run_pool_probe_worker(
        [('vless', 'late-timeout')],
        [],
        batch_size=1,
        concurrency=1,
        delay_seconds=0,
        min_available_kb=0,
        test_port='1200',
        available_memory_kb=lambda: 999999,
        log=timeout_logs.append,
        proto_label=lambda proto: proto,
        hash_key=_hash_key,
        set_checked=lambda value: None,
        validate_outbound=lambda proto, key: None,
        failed_custom_results=lambda checks: {},
        record_key_probe=lambda proto, key, **kwargs: timeout_records.append((proto, key, kwargs)),
        start_xray_for_batch=lambda batch: ('process', 'config.json'),
        wait_for_socks5=lambda port, timeout=6: True,
        check_pool_key=slow_check,
        timeout_budget=lambda checks, task_count, workers: 0.01,
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        invalidate_caches=lambda: None,
    )
    assert timeout_started.wait(timeout=1)
    assert (checked, total) == (1, 1)
    timeout_release.set()
    time.sleep(0.05)
    assert timeout_records == [
        (
            'vless',
            'late-timeout',
            {
                'tg_ok': 'unknown',
                'yt_ok': 'unknown',
                'custom': {},
                'custom_checks': [],
                'timeout': True,
                'timeout_reason': 'batch timeout 0.01s',
            },
        )
    ]
    assert not any(record[2].get('tg_ok') is False or record[2].get('yt_ok') is False for record in timeout_records)
    assert any('timeout/unknown' in message for message in timeout_logs)

    ordered_tasks = [('vless', f'key-{index}') for index in range(8)]
    processed = []
    checked_values = []
    checked, total = pool_probe_runner.run_pool_probe_worker(
        ordered_tasks,
        [],
        batch_size=1,
        concurrency=1,
        delay_seconds=0,
        min_available_kb=0,
        test_port='1200',
        available_memory_kb=lambda: 999999,
        log=logs.append,
        proto_label=lambda proto: proto,
        hash_key=_hash_key,
        set_checked=checked_values.append,
        validate_outbound=lambda proto, key: None,
        failed_custom_results=lambda checks: {},
        record_key_probe=lambda proto, key, **kwargs: None,
        start_xray_for_batch=lambda batch: ('process', 'config.json'),
        wait_for_socks5=lambda port, timeout=6: True,
        check_pool_key=lambda proto, key, checks, proxy_url: processed.append((proto, key)),
        timeout_budget=lambda checks, task_count, workers: 1,
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        invalidate_caches=lambda: None,
    )
    assert (checked, total) == (len(ordered_tasks), len(ordered_tasks))
    assert processed == ordered_tasks
    assert checked_values == list(range(1, len(ordered_tasks) + 1))


def test_proxy_status_runtime_helpers():
    assert proxy_status.port_is_listening(
        8080,
        command_runner=lambda *args, **kwargs: 'tcp 0 0 0.0.0.0:8080 0.0.0.0:* LISTEN\n',
    )
    original_session = proxy_status.requests.Session

    class _Response:
        status_code = 204

        def iter_content(self, chunk_size=4096):
            return iter(())

        def close(self):
            pass

    calls = []
    sessions = []

    try:
        class _Session:
            trust_env = True

            def __init__(self):
                sessions.append(self)

            def get(self, *args, **kwargs):
                calls.append((args, kwargs, self.trust_env))
                return _Response()

            def close(self):
                pass

        proxy_status.requests.Session = _Session
        ok, message = proxy_status.check_http_through_proxy('socks5://127.0.0.1:1080')
        assert ok is True
        assert 'HTTP 204' in message
        assert calls[-1][0][0] == 'https://www.youtube.com/generate_204'
        assert calls[-1][2] is False
        ok, message = proxy_status.check_custom_target_through_proxy(
            lambda value: 'https://example.com/path',
            'socks5://127.0.0.1:1080',
            'example.com',
        )
        assert ok is True
        assert 'example.com' in message
        assert calls[-1][2] is False

        class _ForbiddenResponse:
            status_code = 403
            url = 'https://api.openai.com/v1/models'

            def iter_content(self, chunk_size=4096):
                return iter([b'{"error":{"code":"unsupported_country_region_territory"}}'])

            def close(self):
                pass

        class _RegionPageResponse:
            status_code = 200
            url = 'https://claude.com/app-unavailable-in-region'

            def iter_content(self, chunk_size=4096):
                return iter([b'not available in your region'])

            def close(self):
                pass

        class _AuthResponse:
            status_code = 401
            url = 'https://api.anthropic.com/v1/models'

            def iter_content(self, chunk_size=4096):
                return iter([b'{"error":{"type":"authentication_error"}}'])

            def close(self):
                pass

        responses = iter([_ForbiddenResponse(), _RegionPageResponse(), _AuthResponse()])
        _Session.get = lambda self, *args, **kwargs: next(responses)
        ok, _ = proxy_status.check_custom_target_through_proxy(lambda value: value, 'proxy', 'https://api.openai.com/v1/models')
        assert ok is False
        ok, _ = proxy_status.check_custom_target_through_proxy(lambda value: value, 'proxy', 'https://claude.ai')
        assert ok is False
        ok, _ = proxy_status.check_custom_target_through_proxy(lambda value: value, 'proxy', 'https://api.anthropic.com/v1/models')
        assert ok is True
    finally:
        proxy_status.requests.Session = original_session

    custom_results = proxy_status.probe_custom_targets(
        'proxy',
        [{'id': 'custom', 'urls': ['bad', 'ok']}, {'label': 'skip'}],
        lambda proxy, target, **kwargs: (target == 'ok', ''),
        connect_timeout=1,
        read_timeout=1,
    )
    assert custom_results == {'custom': True}
    retry_calls = []

    def custom_retry_checker(proxy, target, **kwargs):
        retry_calls.append((target, kwargs))
        if len(retry_calls) == 1:
            return False, 'Max retries exceeded with url'
        return True, 'HTTP 401'

    custom_results = proxy_status.probe_custom_targets(
        'proxy',
        [{'id': 'custom', 'url': 'retry'}],
        custom_retry_checker,
        connect_timeout=1,
        read_timeout=2,
        retries=1,
        retry_connect_timeout=6,
        retry_read_timeout=10,
        retry_delay_seconds=0,
    )
    assert custom_results == {'custom': True}
    assert retry_calls == [
        ('retry', {'connect_timeout': 1, 'read_timeout': 2}),
        ('retry', {'connect_timeout': 6, 'read_timeout': 10}),
    ]
    tail_path = ROOT / 'tests' / '_tail.tmp'
    try:
        tail_path.write_text('one\ntwo\nthree\n', encoding='utf-8')
        assert proxy_status.read_tail(tail_path, lines=2) == 'two\nthree'
    finally:
        tail_path.unlink(missing_ok=True)


def test_unblock_list_helpers():
    assert unblock_lists.normalize_unblock_route_name('vless.txt') == 'vless'
    assert unblock_lists.entries_from_service_text('one\n#comment\ntwo # note\none', {'skip'}) == ['one', 'two']


def test_unblock_lists_hide_legacy_txt_files():
    old_dir = unblock_lists.UNBLOCK_DIR
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        try:
            unblock_lists.UNBLOCK_DIR = str(tmp_path)
            for name in (
                'socialnet.txt',
                'vless.txt.20260505.backup',
                'vless.txt',
                'vless-2.txt',
                'vmess.txt',
            ):
                (tmp_path / name).write_text('example.org\n', encoding='utf-8')
            lists = unblock_lists.load_unblock_lists(with_content=False)
        finally:
            unblock_lists.UNBLOCK_DIR = old_dir

    assert [entry['name'] for entry in lists] == ['vless.txt', 'vless-2.txt', 'vmess.txt']


def test_vless2_youtube_routes_are_scoped():
    entries = {
        line.strip()
        for line in (ROOT / 'vless-2.txt').read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    }
    assert set(service_catalog.YOUTUBE_UNBLOCK_ENTRIES) <= entries
    assert 'googleapis.com' not in entries
    assert 'googleusercontent.com' not in entries
    assert 'remotedesktop-pa.googleapis.com' not in entries
    assert 'instantmessaging-pa.googleapis.com' not in entries
    vless_entries = {
        line.strip()
        for line in (ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    }
    assert 'rutracker.org' not in entries
    assert 'rutracker.wiki' not in entries
    assert 'static.rutracker.cc' not in entries
    assert 'feed.rutracker.cc' not in entries
    assert 'rutracker.org' in vless_entries
    assert 'rutracker.wiki' in vless_entries
    assert 'static.rutracker.cc' in vless_entries
    assert 'feed.rutracker.cc' in vless_entries
    assert 'thepiratebay.org' not in entries
    assert 'discord-attachments-uploads-prd.storage.googleapis.com' not in entries
    assert 'redirector.googlevideo.com' in entries
    assert 'yt4.ggpht.com' in entries
    assert 'yt4.googleusercontent.com' in entries
    assert '74.125.172.0/24' in entries
    assert '173.194.31.0/24' in entries
    assert '74.125.174.0/24' in entries
    assert '2a00:1450:4010:c22::/64' in entries
    assert {
        '104.21.0.0/16',
        '157.240.0.0/16',
        'thepiratebay.org',
        'discord-attachments-uploads-prd.storage.googleapis.com',
    } <= vless_entries
    assert not {
        '64.233.0.0/16',
        '72.14.0.0/16',
        '74.125.0.0/16',
        '108.177.0.0/16',
        '142.250.0.0/15',
        '172.217.0.0/16',
        '172.253.0.0/16',
        '173.194.0.0/16',
        '209.85.0.0/16',
        '216.58.192.0/18',
    } & (entries | vless_entries)
    assert 'domain:remotedesktop.google.com' not in service_catalog.CONNECTIVITY_CHECK_DOMAINS
    assert 'full:remotedesktop-pa.googleapis.com' not in service_catalog.CONNECTIVITY_CHECK_DOMAINS
    assert 'full:instantmessaging-pa.googleapis.com' not in service_catalog.CONNECTIVITY_CHECK_DOMAINS
    assert not {
        '34.0.0.0/10',
        '34.64.0.0/10',
        '35.184.0.0/13',
        '216.239.0.0/16',
        '216.58.0.0/16',
        '8.8.8.0/24',
    } & entries


def test_chrome_remote_desktop_routes_stay_on_vless():
    entries = {
        line.split('#', 1)[0].strip()
        for line in (ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.split('#', 1)[0].strip()
    }
    assert set(service_catalog.CHROME_REMOTE_DESKTOP_ROUTE_ENTRIES) <= entries
    assert set(service_catalog.CHROME_REMOTE_DESKTOP_SIGNAL_IP_ENTRIES) <= entries
    assert 'full:instantmessaging-pa.googleapis.com' not in service_catalog.CONNECTIVITY_CHECK_DOMAINS
    assert 'full:remotedesktop-pa.googleapis.com' not in service_catalog.CONNECTIVITY_CHECK_DOMAINS


def test_chatgpt_codex_routes_are_synced():
    entries = {
        line.split('#', 1)[0].strip()
        for line in (ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.split('#', 1)[0].strip()
    }
    assert set(service_catalog.CHATGPT_ROUTE_ENTRIES) <= entries
    assert set(service_catalog.CHATGPT_EDGE_IP_ENTRIES) <= entries
    assert {'ab.chatgpt.com', 'api.chatgpt.com', 'api.statsig.com', 'browser-intake-datadoghq.com'} <= entries
    assert {'humb.apple.com', 'statsigapi.net', 'workos.imgix.net'} <= entries
    assert {'persistent.oaistatic.com', 'openaiassets.blob.core.windows.net', 'images.ctfassets.net'} <= entries
    assert {'api.statsigcdn.com', 'cloudflare-dns.com', 'accounts.google.com', 'www.google.com'} <= entries
    assert 'google.com' not in entries
    assert {'cdn.auth0.com', 'assets.auth0.com', 'static.auth0.com', 'login.openai.com'} <= entries
    assert {'js.hcaptcha.com', 'client-api.arkoselabs.com', 'openai-api.arkoselabs.com'} <= entries
    assert {'q.stripe.com', 'm.stripe.network', 'turnstile.cloudflare.com'} <= entries

    presets = {item['id']: item for item in service_catalog.CUSTOM_CHECK_PRESETS}
    assert 'chatgpt_services' in presets
    assert 'openai_codex' not in presets
    assert presets['chatgpt_services']['label'] == 'ChatGPT / Codex'
    assert presets['chatgpt_services']['urls'] == ['https://api.openai.com/v1/models']
    assert presets['chatgpt_services']['routes'] == service_catalog.CHATGPT_ROUTE_ENTRIES
    source = service_catalog.SERVICE_LIST_SOURCES['chatgpt_services']
    assert source['label'] == 'ChatGPT / Codex'
    assert source['entries'] == service_catalog.CHATGPT_ROUTE_ENTRIES
    assert 'codex' in source['aliases']
    assert source['udp_quic'] is True
    assert service_catalog.SERVICE_LIST_SOURCES['youtube']['udp_quic'] is True
    assert service_catalog.SERVICE_LIST_SOURCES['telegram'].get('udp_quic') is not True
    assert 'chatgpt.com' in service_catalog.UDP_QUIC_ROUTE_ENTRIES
    assert 'youtube.com' in service_catalog.UDP_QUIC_ROUTE_ENTRIES
    udp_routes = set(service_catalog.UDP_QUIC_ROUTE_ENTRIES)
    assert 'api.telegram.org' not in udp_routes
    assert 'telegram.org' not in udp_routes
    assert '149.154.160.0/20' not in udp_routes
    assert '91.108.36.0/22' not in udp_routes
    assert '2001:67c:4e8::/48' not in udp_routes
    assert '17.249.0.0/16' not in udp_routes
    assert '23.216.134.15' not in udp_routes
    assert set(service_catalog.CHATGPT_EDGE_IP_ENTRIES) <= udp_routes
    assert '8.6.112.6' in udp_routes
    assert '8.47.69.6' in udp_routes
    assert not set(service_catalog.CHATGPT_EDGE_IP_ENTRIES) & set(service_catalog.UDP_QUIC_EXCLUDE_ENTRIES)
    bot_source = (ROOT / 'bot.py').read_text(encoding='utf-8')
    assert "'chatgpt_services'" in bot_source
    assert "'youtube'" in bot_source


def test_ai_assistant_custom_routes_are_synced():
    entries = {
        line.split('#', 1)[0].strip()
        for line in (ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.split('#', 1)[0].strip()
    }
    presets = {item['id']: item for item in service_catalog.CUSTOM_CHECK_PRESETS}

    assert set(service_catalog.CLAUDE_ROUTE_ENTRIES) <= entries
    assert set(service_catalog.GEMINI_ROUTE_ENTRIES) <= entries
    assert presets['claude']['routes'] == service_catalog.CLAUDE_ROUTE_ENTRIES
    assert presets['gemini']['routes'] == service_catalog.GEMINI_ROUTE_ENTRIES
    assert presets['claude']['urls'] == ['https://api.anthropic.com/v1/models']
    assert presets['discord']['urls'] == ['https://discord.com/api/v10/gateway']
    assert presets['discord']['routes'] == service_catalog.DISCORD_ROUTE_ENTRIES
    assert 'https://aistudio.google.com' in presets['gemini']['urls']
    assert service_catalog.SERVICE_LIST_SOURCES['claude']['entries'] == service_catalog.CLAUDE_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['gemini']['entries'] == service_catalog.GEMINI_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['claude']['udp_quic'] is True
    assert service_catalog.SERVICE_LIST_SOURCES['gemini']['udp_quic'] is True
    assert 'claude.ai' in service_catalog.UDP_QUIC_ROUTE_ENTRIES
    assert 'gemini.google.com' in service_catalog.UDP_QUIC_ROUTE_ENTRIES
    assert 'generativelanguage.googleapis.com' in service_catalog.UDP_QUIC_ROUTE_ENTRIES
    assert {'www.youtube.com', 'i.ytimg.com', 'yt3.ggpht.com', 'jnn-pa.googleapis.com'}.isdisjoint(
        service_catalog.GEMINI_ROUTE_ENTRIES
    )
    bot_source = (ROOT / 'bot.py').read_text(encoding='utf-8')
    assert "'claude'" in bot_source
    assert "'gemini'" in bot_source


def test_primary_vless_does_not_capture_gmail_domains():
    entries = {
        line.split('#', 1)[0].strip()
        for line in (ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.split('#', 1)[0].strip()
    }
    assert not ({
        'mail.google.com',
        'gmail.com',
        'www.gmail.com',
        'googlemail.com',
        'www.googlemail.com',
        'mail-attachment.google.com',
        'mail-attachment.googleusercontent.com',
        'client-channel.google.com',
        'clients1.google.com',
        'clients5.google.com',
        'contacts.google.com',
    } & entries)


def test_custom_check_service_sources_are_synced():
    entries = {
        line.split('#', 1)[0].strip()
        for line in (ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.split('#', 1)[0].strip()
    }
    bot_source = (ROOT / 'bot.py').read_text(encoding='utf-8')
    keys_match = re.search(r'SOCIALNET_SERVICE_KEYS\s*=\s*\((.*?)\)', bot_source, re.S)
    assert keys_match
    button_keys = set(re.findall(r"'([^']+)'", keys_match.group(1)))
    presets = {preset['id']: preset for preset in service_catalog.CUSTOM_CHECK_PRESETS}
    preset_ids = {preset['id'] for preset in service_catalog.CUSTOM_CHECK_PRESETS}

    assert preset_ids <= set(service_catalog.SERVICE_LIST_SOURCES)
    assert preset_ids <= button_keys
    assert button_keys <= set(service_catalog.SERVICE_LIST_SOURCES)

    for preset in service_catalog.CUSTOM_CHECK_PRESETS:
        source = service_catalog.SERVICE_LIST_SOURCES[preset['id']]
        source_entries = set(source.get('entries') or [])
        preset_routes = set(preset.get('routes') or [])
        assert source_entries
        assert preset_routes <= source_entries
        assert preset_routes <= entries

    assert service_catalog.SERVICE_LIST_SOURCES['discord']['entries'] == service_catalog.DISCORD_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['copilot']['entries'] == service_catalog.COPILOT_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['perplexity']['entries'] == service_catalog.PERPLEXITY_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['grok']['entries'] == service_catalog.GROK_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['deepseek']['entries'] == service_catalog.DEEPSEEK_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['telegram']['entries'] == service_catalog.TELEGRAM_UNBLOCK_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['meta']['entries'] == service_catalog.META_PLATFORM_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['meta']['label'] == 'Meta AI / Instagram / Facebook'
    assert 'telegram' in button_keys
    assert 'meta' in button_keys
    assert {'meta_ai', 'instagram', 'facebook'}.isdisjoint(button_keys)
    assert {'meta_ai', 'instagram', 'facebook'}.isdisjoint(preset_ids)
    assert presets['meta']['routes'] == service_catalog.META_PLATFORM_ROUTE_ENTRIES
    assert presets['meta']['urls'] == [
        'https://www.meta.ai',
        'https://www.instagram.com',
        'https://www.facebook.com',
        'https://graph.facebook.com',
    ]


def test_telegram_routes_include_mini_app_dependencies():
    entries = {
        line.split('#', 1)[0].strip()
        for line in (ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.split('#', 1)[0].strip()
    }
    expected = {
        'ton.org', 'usercontent.dev', 'fragment.com', 'telegram.org', 'web.telegram.org',
        'walletbot.me', 'toncenter.walletbot.me', 'ston.fi', 't-bank-app.ru',
        'wallet.tg', 'app.tonkeeper.com', 'bridge.tonapi.io', 'ton-connect.github.io',
        'mytonwallet.io', 'tonhub.com', 'connect.tonhubapi.com',
        'acdn.tinkoff.ru', '194.221.250.50', '23.216.134.15',
        '104.21.72.109', '151.101.129.91', 'internal.api.vk.ru',
        'queuev4.vk.ru', 'tracker-api.vk-analytics.ru',
        '17.249.0.0/16', '17.252.0.0/16', '17.188.128.0/18',
        '64.233.164.188', '142.251.169.188', '172.253.145.188',
    }
    assert expected <= set(service_catalog.TELEGRAM_UNBLOCK_ENTRIES)
    assert expected <= entries


def test_chatgpt_codex_custom_check_migration():
    checks = custom_checks_store.merge_chatgpt_custom_checks([
        {
            'id': 'chatgpt_services',
            'label': 'ChatGPT',
            'url': 'https://chatgpt.com',
            'urls': ['https://chatgpt.com'],
            'badge': 'GPT',
            'icon': 'chatgpt',
        },
        {
            'id': 'openai_codex',
            'label': 'Codex',
            'url': 'https://chatgpt.com/codex',
            'badge': 'CDX',
            'icon': 'chatgpt',
        },
        {'id': 'discord', 'label': 'Discord', 'url': 'https://discord.com'},
    ])
    assert [item['id'] for item in checks] == ['chatgpt_services', 'discord']
    assert checks[0]['label'] == 'ChatGPT / Codex'
    assert checks[0]['url'] == 'https://api.openai.com/v1/models'
    assert 'urls' not in checks[0]


def test_preset_custom_checks_are_hydrated_from_catalog():
    checks = custom_checks_store.merge_preset_custom_checks([
        {'id': 'claude', 'label': 'Claude', 'url': 'https://claude.ai'},
        {'id': 'gemini', 'label': 'Gemini', 'url': 'https://gemini.google.com'},
    ])
    by_id = {item['id']: item for item in checks}
    assert by_id['claude']['url'] == 'https://api.anthropic.com/v1/models'
    assert 'urls' not in by_id['claude']
    assert by_id['claude']['routes'] == service_catalog.CLAUDE_ROUTE_ENTRIES
    assert by_id['gemini']['urls'] == [
        'https://gemini.google.com',
        'https://aistudio.google.com',
        'https://ai.google.dev',
        'https://generativelanguage.googleapis.com',
    ]
    assert by_id['gemini']['routes'] == service_catalog.GEMINI_ROUTE_ENTRIES


def test_meta_custom_check_migration():
    checks = custom_checks_store.merge_preset_custom_checks([
        {'id': 'instagram', 'label': 'Instagram', 'url': 'https://www.instagram.com'},
        {'id': 'facebook', 'label': 'Facebook', 'url': 'https://www.facebook.com'},
        {'id': 'meta_ai', 'label': 'Meta AI', 'url': 'https://www.meta.ai'},
    ])
    assert [item['id'] for item in checks] == ['meta']
    assert checks[0]['label'] == 'Meta AI / Instagram / Facebook'
    assert checks[0]['routes'] == service_catalog.META_PLATFORM_ROUTE_ENTRIES


def test_chrome_remote_desktop_routes_are_in_vless():
    entries = {
        line.split('#', 1)[0].strip()
        for line in (ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.split('#', 1)[0].strip()
    }
    assert set(service_catalog.CHROME_REMOTE_DESKTOP_ROUTE_ENTRIES) <= entries
    assert service_catalog.SERVICE_LIST_SOURCES['chrome_remote_desktop']['entries'] == service_catalog.CHROME_REMOTE_DESKTOP_ROUTE_ENTRIES
    presets = {item['id']: item for item in service_catalog.CUSTOM_CHECK_PRESETS}
    assert presets['chrome_remote_desktop']['routes'] == service_catalog.CHROME_REMOTE_DESKTOP_ROUTE_ENTRIES
    bot_source = (ROOT / 'bot.py').read_text(encoding='utf-8')
    assert "'chrome_remote_desktop'" in bot_source


def test_web_command_state_helpers():
    assert web_command_state.estimate_update_progress('noop', '', ('update',)) == (0, '')
    assert web_command_state.estimate_update_progress('update', 'Бэкап создан.') == (70, 'Резервная копия готова, идёт замена файлов')
    state = {}
    lock = threading.Lock()
    web_command_state.set_flash_message(lock, state, 'ok')
    assert web_command_state.consume_flash_message(lock, state) == 'ok'
    assert web_command_state.consume_flash_message(lock, state) == ''


def test_web_http_common_helpers():
    class _Config:
        web_auth_user = 'root'
        web_auth_token = ' secret '
        web_auth_disabled = False

    assert web_http_common.is_local_web_client('192.168.1.2')
    assert web_http_common.is_local_web_client('127.0.0.1')
    assert not web_http_common.is_local_web_client('8.8.8.8')
    assert web_http_common.resolve_bind_host('192.168.1.1') == '192.168.1.1'
    assert web_http_common.resolve_bind_host('0.0.0.0') == ''
    assert web_http_common.resolve_bind_host('bad') == ''
    assert web_http_common.config_web_auth_token(_Config) == 'secret'
    assert web_http_common.config_web_auth_user(_Config) == 'root'
    _Config.web_auth_disabled = True
    assert web_http_common.config_web_auth_token(_Config) == ''


def test_web_http_basic_auth_accepts_and_rejects_credentials():
    class _Request(web_http_common.WebRequestMixin):
        web_auth_token_getter = staticmethod(lambda: 'secret')
        web_auth_user_getter = staticmethod(lambda: 'root')

        def __init__(self, header=''):
            self.headers = {'Authorization': header} if header else {}
            self.wfile = BytesIO()
            self.status_code = None
            self.sent_headers = []
            self.close_connection = False

        def send_response(self, status):
            self.status_code = status

        def send_header(self, name, value):
            self.sent_headers.append((name, value))

        def end_headers(self):
            pass

    good = base64.b64encode(b'root:secret').decode('ascii')
    bad = base64.b64encode(b'root:bad').decode('ascii')
    assert _Request('Basic ' + good)._ensure_web_auth() is True

    bad_request = _Request('Basic ' + bad)
    assert bad_request._ensure_web_auth() is False
    assert bad_request.status_code == 401
    assert bad_request.close_connection is True
    assert b'Authentication required' in bad_request.wfile.getvalue()

    missing_request = _Request()
    assert missing_request._ensure_web_auth() is False
    assert missing_request.status_code == 401

    class _NoAuthRequest(_Request):
        web_auth_token_getter = staticmethod(lambda: '')

    assert _NoAuthRequest()._ensure_web_auth() is True


def test_installer_common_helpers():
    class _Handler:
        def __init__(self, content_length, body=b''):
            self.headers = {'Content-Length': content_length}
            self.rfile = BytesIO(body)

    form = {'web_auth_user': ' ', 'web_auth_token': ' secret '}
    installer_common.normalize_web_auth_form(form)
    assert form['web_auth_user'] == 'admin'
    assert form['web_auth_token'] == 'secret'
    user, note = installer_common.web_auth_summary(form)
    assert user == 'admin'
    assert 'secret' not in note
    assert 'задан' in note
    assert installer_common.validate_installer_form(
        {'token': 'x', 'username': 'u', 'browser_port': '8080'},
        ['token', 'username'],
    ) == (True, '')
    ok, message = installer_common.validate_installer_form(
        {'token': 'x', 'username': 'u', 'browser_port': 'bad'},
        ['token', 'username'],
    )
    assert ok is False
    assert 'browser_port' in message
    assert installer_common.installer_target_url(
        {'routerip': '192.168.1.2', 'browser_port': '9090'},
        8080,
    ) == 'http://192.168.1.2:9090/'
    notice, redirect_head, redirect_script = installer_common.installer_page_parts('<ok>', 'http://192.168.1.2/', 2)
    assert '&lt;ok&gt;' in notice
    assert '2;url=' in redirect_head
    assert 'window.location.replace' in redirect_script
    assert installer_common.parse_urlencoded_request(_Handler('-1', b'token=x')) == {}
    assert installer_common.parse_urlencoded_request(_Handler('7', b'a=1&b=')) == {'a': '1', 'b': ''}
    try:
        installer_common.parse_urlencoded_request(_Handler('20', b'a=1'), max_bytes=5)
        assert False, 'oversized POST body should be rejected'
    except ValueError as exc:
        assert 'too large' in str(exc)


def test_installer_page_is_bot_setup_only():
    original_detect_router_ip = installer.detect_router_ip
    try:
        installer.detect_router_ip = lambda: '192.168.1.1'
        page = installer.page_html(csrf_token='csrf-token-for-test-123456789012345')
    finally:
        installer.detect_router_ip = original_detect_router_ip
    assert 'BotFather token' in page
    assert 'Telegram username' in page
    assert 'name="csrf_token"' in page
    assert 'Пул ключей' not in page
    assert 'proto-select' not in page
    assert '/api/keys' not in page


def test_repo_update_helpers():
    class _Response:
        def __init__(self, url, text='', payload=None, fail=False):
            self.url = url
            self.text = text
            self._payload = payload or {}
            self._fail = fail
            self.raw = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            if self._fail:
                raise repo_update.requests.RequestException('fail')

        def json(self):
            return self._payload

    class _Session:
        def __init__(self):
            self.calls = []

        def get(self, url, **_kwargs):
            self.calls.append(url)
            if 'raw.githubusercontent.com' in url or 'codeload.github.com' in url:
                return _Response(url, fail=True)
            return _Response(url, payload={'encoding': 'base64', 'content': 'aGVsbG8='})

    session = _Session()
    url, text = repo_update.download_repo_file_text(session, 'owner', 'repo', 'branch/name', 'script.sh')
    assert text == 'hello'
    assert 'api.github.com' in url
    assert any('raw.githubusercontent.com' in call for call in session.calls)
    assert any('codeload.github.com' in call for call in session.calls)
    assert any('/refs/tags/branch/name' in call for call in session.calls)

    class _ScriptSession:
        def __init__(self):
            self.calls = []
            self.trust_env = True

        def get(self, url, **_kwargs):
            self.calls.append(url)
            if '/commits/' in url:
                return _Response(url, payload={'sha': 'abc123def456'})
            return _Response(url, text='#!/bin/sh\necho update\n')

    original_session_factory = repo_update.requests.Session
    script_session = _ScriptSession()
    try:
        repo_update.requests.Session = lambda: script_session
        script_url, script_text, repo_ref = repo_update.download_repo_script('owner', 'repo', branch='main')
    finally:
        repo_update.requests.Session = original_session_factory
    assert repo_ref == 'abc123def456'
    assert script_text.startswith('#!/bin/sh')
    assert '/abc123def456/script.sh' in script_url
    assert script_session.trust_env is False

    bot_source = (ROOT / 'bot.py').read_text(encoding='utf-8')
    assert "direct_env['REPO_REF'] = repo_ref" in bot_source
    assert "direct_env['REPO_REF'] = branch" not in bot_source
    assert repo_update.download_repo_script.__defaults__ == ('main',)
    assert telegram_jobs.start_background_command.__kwdefaults__['branch'] == 'main'
    assert repo_update.direct_fetch_env(('HTTP_PROXY',), {'HTTP_PROXY': 'x', 'keep': 'y'}) == {'keep': 'y'}


def test_web_get_actions_helpers():
    refreshed = []
    pool_snapshot_calls = []
    current_keys = {'vless': 'key'}
    def pool_snapshot(keys, include_keys=False, protocols=None):
        pool_snapshot_calls.append((keys, include_keys, protocols))
        return {proto: {'rows': []} for proto in (protocols or ['vless'])}
    ctx = {
        'build_form': lambda message: 'form:' + message,
        'build_protocol_panel': lambda proto: 'panel:' + proto,
        'consume_flash_message': lambda: 'saved',
        'load_current_keys': lambda: current_keys,
        'cached_status_snapshot': lambda keys: None,
        'active_mode_status_snapshot': lambda keys: {'web': {'state': 'active'}, 'protocols': {'vless': {}}},
        'refresh_status_caches_async': lambda keys: refreshed.append(keys),
        'pool_probe_locked': lambda: False,
        'get_web_command_state': lambda: {'running': False},
        'pool_enabled': True,
        'get_pool_probe_progress': lambda: {'running': True, 'total': 2},
        'web_pool_snapshot': pool_snapshot,
        'pool_status_summary': lambda keys: {'active_text': '1 / 5'},
        'web_custom_checks': lambda: [{'id': 'custom'}],
        'service_routes_payload': lambda: {'route_tools_html': '<div>routes</div>'},
        'time_provider': lambda: 123.0,
        'static_dir': '/tmp/static',
        'service_icons_enabled': True,
    }
    assert web_get_actions.dispatch(ctx, '/') == {'kind': 'html', 'html': 'form:saved'}
    status = web_get_actions.dispatch(ctx, '/api/status')
    assert status['payload']['pool_probe_running'] is True
    assert status['payload']['timestamp'] == 123.0
    assert 'pools' not in status['payload']
    assert refreshed == [current_keys]
    placeholder_refreshed = []
    placeholder_ctx = dict(ctx)
    placeholder_ctx.update({
        'placeholder_status_snapshot': lambda keys: {'web': {'state': 'placeholder'}, 'protocols': {'vless': {'label': 'pending'}}},
        'active_mode_status_snapshot': lambda keys: (_ for _ in ()).throw(AssertionError('status API must not block on active checks')),
        'refresh_status_caches_async': lambda keys: placeholder_refreshed.append(keys),
        'get_pool_probe_progress': lambda: {'running': False, 'total': 0},
    })
    placeholder_status = web_get_actions.dispatch(placeholder_ctx, '/api/status')
    assert placeholder_status['payload']['web'] == {'state': 'placeholder'}
    assert placeholder_refreshed == [current_keys]
    pools = web_get_actions.dispatch(ctx, '/api/pools')
    assert pools['payload']['pools'] == {'vless': {'rows': []}}
    assert pools['payload']['custom_checks'] == [{'id': 'custom'}]
    assert pools['payload']['pool_probe_running'] is True
    assert pools['payload']['pool_probe_progress'] == {'running': True, 'total': 2}
    service_routes_payload = web_get_actions.dispatch(ctx, '/api/service_routes')
    assert service_routes_payload['payload'] == {'route_tools_html': '<div>routes</div>'}
    scoped_pools = web_get_actions.dispatch(ctx, '/api/pools', 'protocols=vless,vmess')
    assert scoped_pools['payload']['pools'] == {'vless': {'rows': []}, 'vmess': {'rows': []}}
    assert pool_snapshot_calls[-1] == (current_keys, False, ['vless', 'vmess'])
    probe = web_get_actions.dispatch(ctx, '/api/pool_probe')
    assert probe['payload']['status'] == 'running'
    panel = web_get_actions.dispatch(ctx, '/api/protocol_panel', 'proto=vless')
    assert panel['payload'] == {'ok': True, 'protocol': 'vless', 'html': 'panel:vless'}
    alias_panel = web_get_actions.dispatch(ctx, '/api/protocol_panel', 'protocol=vless2')
    assert alias_panel['payload'] == {'ok': True, 'protocol': 'vless2', 'html': 'panel:vless2'}
    script_asset = web_get_actions.dispatch({'build_script_asset': lambda: 'js'}, '/static/app.js')
    assert script_asset['cache_seconds'] == 86400
    static = web_get_actions.dispatch(ctx, '/static/service-icons/test.png')
    assert static['path'].replace('\\', '/').endswith('/service-icons/test.png')


def test_web_form_blocks_helpers():
    assert web_form_blocks.proxy_mode_label('none') == 'Без прокси'
    assert web_form_blocks.js_bool(True) == 'true'
    assert web_form_blocks.js_bool(False) == 'false'
    assert 'csrf_token' in web_form_blocks.render_csrf_input('token')
    assert 'notice-result' in web_form_blocks.render_message_block('ok')
    assert web_form_blocks.render_message_block('', live=False) == ''
    assert 'hidden' in web_form_blocks.render_message_block('', live=True)
    status_blocks = web_form_blocks.render_status_blocks(
        'ok',
        {'label': 'cmd', 'running': False, 'result': 'done'},
        {'socks_details': 'socks ok'},
        live=True,
    )
    assert 'web-action-message' in status_blocks['message_block']
    assert 'cmd' in status_blocks['command_block']
    assert 'socks ok' in status_blocks['socks_block']
    quick_key = web_form_blocks.quick_key_context({'proxy_mode': 'none'}, {'vless': 'vless://sample'}, 'Без прокси')
    assert quick_key == {'proto': 'vless', 'label': 'Vless 1', 'value': 'vless://sample'}
    basics = web_form_blocks.render_form_basics(
        '',
        {'running': True},
        {'proxy_mode': 'vless'},
        {'vless': 'vless://sample'},
        'Vless 1',
    )
    assert basics['quick_key']['proto'] == 'vless'
    assert basics['initial_command_running'] == 'true'
    button_picker = web_form_blocks.render_button_mode_picker('vless', csrf_input_html='<input name="csrf_token">')
    assert 'mode-choice-grid' in button_picker
    assert 'csrf_token' in button_picker
    assert '<select' in web_form_blocks.render_select_mode_picker('none', '<input>')
    app_picker = web_form_blocks.render_app_runtime_mode_picker(
        'advanced',
        [('advanced', 'Сложный', 'интерфейс с пулом ключей и Telegram-бот')],
        csrf_input_html='<input name="csrf_token">',
    )
    assert 'Режим работы программы' in app_picker
    assert 'data-confirm-title=' in app_picker
    assert 'data-app-mode-value="advanced"' in app_picker
    assert '<small>' not in app_picker
    command_buttons = web_form_blocks.render_command_button_forms(
        [('restart_services', 'Restart', '', 'Confirm?', 'Do it?')],
        '<input name="csrf_token">',
    )
    assert 'restart_services' in command_buttons
    assert 'csrf_token' in command_buttons
    router_buttons = web_form_blocks.render_router_command_buttons('<input name="csrf_token">', dns_override_active=True)
    assert 'DNS Override ВКЛ' in router_buttons and 'success-button' in router_buttons
    assert router_buttons.index('value="update"') < router_buttons.index('value="rollback_update"')
    tabs, panels = web_form_blocks.render_unblock_lists(
        [{'name': 'custom', 'label': 'Custom', 'content': 'one\n\n two'}],
        '<input name="csrf_token">',
        ('vk',),
        'all',
        lambda key: 'All' if key == 'all' else key.upper(),
    )
    assert 'data-list-target="custom"' in tabs
    assert 'Записей: 2' in panels
    assert 'csrf_token' in panels

def test_web_pool_form_blocks_helpers():
    table_class, custom_width, mobile_width = web_pool_form_blocks.pool_table_layout([{'id': 'chat'}])
    assert table_class == 'pool-table has-custom-checks'
    assert custom_width == 32
    assert mobile_width == 28
    progress = web_pool_form_blocks.pool_probe_topbar_text(
        True,
        {'checked': 1, 'total': 2},
        lambda data: 'Проверка',
        'ok',
    )
    assert '1/2' in progress
    assert progress != 'ok'
    assert web_pool_form_blocks.pool_summary_note_with_progress(
        'note',
        True,
        {'checked': 1, 'total': 2},
        lambda data: 'Проверка',
    ) == 'Проверка: 1/2. note'
    pool_rows = web_pool_form_blocks.render_pool_items(
        key_name='vless',
        title='Vless 1',
        pool_keys=['vless://sample'],
        current_key='vless://sample',
        key_probe_cache={'hash-vless': {'tg_ok': True}},
        custom_checks=[],
        key_display_name=lambda key: 'sample-key',
        hash_key=lambda key: 'hash-vless',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        custom_check_badges=lambda probe, checks: '',
        probe_checked_at=lambda probe: 'now',
        csrf_input_html='<input name="csrf_token" value="token">',
    )
    assert 'pool-row-active' in pool_rows
    assert 'data-search="sample-key hash-vless"' in pool_rows
    assert 'data-key=' not in pool_rows
    assert 'name="key_id" value="hash-vless"' in pool_rows
    assert 'name="key" value=' not in pool_rows
    assert 'vless://sample' not in pool_rows
    assert 'csrf_token' in pool_rows
    assert 'pool-delete-icon' in pool_rows
    assert '&times;' in pool_rows
    assert 'data-pool-mobile-checked' in pool_rows
    assert '>now</span>' in pool_rows
    panel = web_pool_form_blocks.render_protocol_panel(
        key_name='vless',
        title='Vless 1',
        rows=3,
        placeholder='vless://...',
        current_key_value='vless://sample',
        status_info={'tone': 'ok', 'label': 'OK', 'details': 'details'},
        active_status_icons='',
        pool_items_html=pool_rows,
        pool_table_class='pool-table',
        pool_custom_col_width=32,
        pool_mobile_custom_col_width=28,
        custom_header_icons='',
        custom_presets_html='',
        custom_checks_html='',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        active=True,
        csrf_input_html='<input name="csrf_token" value="token">',
    )
    assert 'protocol-workspace active' in panel
    assert 'pool-sort-control' in panel
    assert 'data-pool-sort-value="telegram"' in panel
    assert 'data-pool-sort-value="active"' not in panel
    assert 'data-pool-sort-value="problem"' in panel
    assert 'custom-check-form' in panel
    assert 'data-pool-probe-start-button aria-disabled="false"' in panel
    assert 'data-pool-probe-cancel-button disabled aria-disabled="true"' in panel
    main_panel = web_pool_form_blocks.render_protocol_panel(
        key_name='vless',
        title='Vless 1',
        rows=3,
        placeholder='vless://...',
        current_key_value='vless://sample',
        status_info={'tone': 'ok', 'label': 'OK', 'details': 'details'},
        active_status_icons='',
        pool_items_html='',
        pool_table_class='pool-table',
        pool_custom_col_width=32,
        pool_mobile_custom_col_width=28,
        custom_header_icons='',
        custom_presets_html='',
        custom_checks_html='',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        csrf_input_html='<input name="csrf_token" value="token">',
        enable_key_pool=False,
        enable_custom_checks=False,
    )
    assert 'Пул ключей' not in main_panel
    assert 'custom-check-form' not in main_panel
    tabs_html, panels_html = web_pool_form_blocks.render_protocol_tabs_and_panels(
        [('vless', 'Vless 1', 3, 'vless://...')],
        {'vless': 'vless://sample'},
        {'vless': {'tone': 'ok', 'label': 'OK', 'details': 'details'}},
        '<input name="csrf_token" value="token">',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        enable_key_pool=False,
        enable_custom_checks=False,
    )
    assert 'protocol-tab active' in tabs_html
    assert 'protocol-workspace active' in panels_html
    assert 'csrf_token' in panels_html
    lazy_tabs_html, lazy_panels_html = web_pool_form_blocks.render_protocol_tabs_and_panels(
        [
            ('vless', 'Vless 1', 3, 'vless://...'),
            ('vless2', 'Vless 2', 3, 'vless://...'),
        ],
        {'vless': 'vless://sample', 'vless2': 'vless://hidden'},
        {'vless': {'tone': 'ok', 'label': 'OK', 'details': 'details'}},
        '<input name="csrf_token" value="token">',
        key_pools={'vless': ['vless://sample'], 'vless2': ['vless://hidden']},
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        active_protocol='vless',
        lazy_protocol_panels=True,
    )
    assert lazy_tabs_html.count('protocol-tab') == 2
    assert 'data-protocol-panel-lazy="1"' in lazy_panels_html
    assert 'vless://hidden' not in lazy_panels_html


def test_web_status_builder_helpers():
    assert web_status_builder.empty_protocol_status()['tone'] == 'empty'
    active = web_status_builder.active_protocol_status(
        endpoint_ok=True,
        endpoint_message='SOCKS ok.',
        api_ok=False,
        api_message='timeout',
        api_transient=True,
        yt_ok=True,
        yt_message='ok',
        custom_states={'chat': 'ok'},
        custom_checks=[{'id': 'chat', 'label': 'Chat'}],
    )
    assert active['tone'] == 'warn'
    assert active['api_pending'] is True
    cached = web_status_builder.cached_protocol_status(
        'key',
        {'tg_ok': False, 'yt_ok': True},
        [{'id': 'chat', 'label': 'Chat'}],
        {'chat': 'fail'},
    )
    assert cached['tone'] == 'warn'
    assert 'YouTube: работает' in cached['details']
    youtube_only = web_status_builder.cached_protocol_status(
        'key',
        {'tg_ok': False, 'yt_ok': True},
        [],
        {},
        api_required=False,
    )
    assert youtube_only['tone'] == 'ok'
    assert 'не требуется для текущего режима' in youtube_only['details']


def test_web_template_styles_helpers():
    styles = web_template_styles.render_web_styles(TELEGRAM_SVG_B64='tg-icon')
    assert ':root{' in styles
    assert '.app-shell' in styles
    assert 'tg-icon' in styles
    assert '[data-theme="glass"]' in styles
    assert '--glass-blur' in styles
    assert '@supports not ((backdrop-filter:blur(1px))' in styles
    assert '@media (prefers-reduced-motion: reduce)' in styles
    assert '@media (prefers-contrast: more)' in styles
    assert '[data-liquid]::before' in styles
    assert '[data-liquid]::after' in styles
    assert '[data-liquid].liquid-active{' in styles
    assert '@media (hover: hover)' in styles
    assert 'radial-gradient(circle at var(--mx, 50%) var(--my, 50%)' in styles
    assert '.liquid-global-lens' in styles
    assert '.liquid-global-lens-active' in styles
    assert '.liquid-global-lens::before' in styles
    assert '@keyframes liquid-caustic' not in styles
    assert '--lsx' not in styles
    assert 'radial-gradient(circle at 20% 18%' in styles
    assert 'backdrop-filter:blur(.18px) saturate(125%) contrast(1.02) brightness(1.04)' in styles
    assert 'background:rgba(255,255,255,.004)' in styles
    assert '[data-theme="glass"] .topbar-actions[data-liquid]' not in styles
    assert '[data-theme="glass"] .mobile-nav[data-liquid]' in styles
    assert '[data-theme="glass"] .mobile-nav[data-liquid]{position:fixed;}' in styles
    assert '[data-theme="glass"] .side-nav[data-liquid]{position:sticky;}' in styles
    assert '@media (min-width: 1024px){[data-theme="glass"] .side-nav[data-liquid]{position:static;}}' in styles
    assert 'width:72px;' in styles
    assert 'z-index:300;' in styles
    assert '[data-theme="glass"] .liquid-global-lens{width:88px;height:88px;}' in styles
    assert '.api-pill{display:flex;align-items:center;width:100%;height:auto;min-height:calc(var(--control-height) + 8px);' in styles
    assert '.attention-telegram-icon{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;' in styles
    assert '.attention-ok{grid-template-columns:minmax(0,1fr);}' in styles
    assert '.attention-ok .attention-dot{display:none;}' in styles
    assert '.attention-item > div > span{display:block;' in styles
    assert '.attention-item span:last-child{display:block;' not in styles
    assert '.api-pill::before' not in styles
    assert 'grid-template-columns:minmax(420px,.85fr) minmax(520px,1.4fr) minmax(176px,220px) auto;' in styles
    assert '.theme-control{justify-self:end;width:100%;}' in styles
    assert '.app-caption strong{display:block;max-width:none;font-size:15px;font-weight:800;line-height:1.18;letter-spacing:0;white-space:normal;overflow:visible;text-overflow:clip;' in styles
    assert '.topbar-actions{width:100%;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));justify-content:stretch;gap:8px;}' in styles
    assert '.app-caption strong{max-width:none;padding-right:60px;font-size:14px;line-height:1.18;white-space:normal;}' in styles
    assert '.app-branch{font-size:10.5px;line-height:1.18;white-space:nowrap;overflow:hidden;text-overflow:clip;overflow-wrap:normal;word-break:normal;}' in styles
    assert '.topbar{position:relative;z-index:260;' in styles
    assert '.mode-control,.theme-control{position:relative;min-width:0;}' in styles
    assert '.mode-control #mode-picker,.theme-control .theme-picker{top:calc(100% + 8px);width:min(320px,calc(100vw - 32px));min-width:260px;z-index:330;}' in styles
    assert '.mode-control #mode-picker,.theme-control .theme-picker{position:absolute;top:calc(100% + 8px);width:min(260px,calc(100vw - 42px));min-width:0;max-height:min(360px,calc(100vh - 220px));overflow:auto;z-index:330;}' in styles
    assert '.pool-controls{display:grid;grid-template-columns:minmax(240px,520px) minmax(180px,240px);' in styles
    assert '.pool-sort-menu.hidden{display:none;}' in styles
    assert '.pool-sort-divider' in styles
    assert '.health-meter.warn span' in styles
    assert '.status-overview-head{display:grid;' in styles
    assert '.version-badge{grid-column:2;grid-row:1;justify-self:end;align-self:start;width:auto;min-width:48px;' in styles
    assert '@media (hover: none), (pointer: coarse)' in styles
    assert '[data-theme="glass"] [data-liquid]:not(.liquid-active):hover::before' in styles
    assert '[data-theme="glass"] .mobile-nav .nav-item.active' in styles
    assert '[data-theme="glass"] .topbar .hero-popover' in styles
    assert 'rgba(15,28,38,.96)' in styles
    assert '[data-theme="glass"] [data-liquid].liquid-resetting::before' in styles
    assert '[data-theme="glass"] [data-liquid-group="true"].liquid-active::before' in styles
    assert 'repeating-linear-gradient' not in styles
    assert '{TELEGRAM_SVG_B64}' not in styles
    assert '{{' not in styles


def test_probe_cache_update_entry_min_interval():
    cache = {}
    assert probe_cache.update_key_probe_cache_entry(
        cache,
        'vless',
        'key-1',
        tg_ok=True,
        yt_ok=False,
        now=100,
        min_write_interval=30,
    )
    key_id = probe_cache.hash_key('key-1')
    assert cache[key_id]['schema'] == probe_cache.KEY_PROBE_CACHE_SCHEMA_VERSION
    assert cache[key_id]['ts'] == 100
    assert cache[key_id]['tg_ok'] is True
    assert cache[key_id]['yt_ok'] is False

    assert not probe_cache.update_key_probe_cache_entry(
        cache,
        'vless',
        'key-1',
        tg_ok=True,
        yt_ok=False,
        now=120,
        min_write_interval=30,
    )
    assert cache[key_id]['ts'] == 100

    assert probe_cache.update_key_probe_cache_entry(
        cache,
        'vless',
        'key-1',
        tg_ok='unknown',
        now=121,
        min_write_interval=30,
    )
    assert cache[key_id]['tg_ok'] is None
    assert cache[key_id]['ts'] == 121

    assert probe_cache.update_key_probe_cache_entry(
        cache,
        'vless',
        'key-1',
        tg_ok='unknown',
        yt_ok=False,
        now=152,
        min_write_interval=30,
    )
    assert cache[key_id]['ts'] == 152

    assert not probe_cache.update_key_probe_cache_entry(
        cache,
        'vless',
        'key-1',
        tg_ok=False,
        yt_ok=True,
        now=151,
        min_write_interval=0,
    )
    assert cache[key_id]['ts'] == 152
    assert cache[key_id]['tg_ok'] is None

    assert probe_cache.update_key_probe_cache_entry(
        cache,
        'vless',
        'key-1',
        tg_ok='unknown',
        yt_ok='unknown',
        custom={'custom': 'unknown'},
        custom_checks=[{'id': 'custom', 'urls': ['https://example.test']}],
        timeout=True,
        timeout_reason='batch timeout 1s',
        now=200,
        min_write_interval=0,
    )
    assert cache[key_id]['timeout'] is True
    assert cache[key_id]['timeout_reason'] == 'batch timeout 1s'
    assert cache[key_id]['tg_ok'] is None
    assert cache[key_id]['yt_ok'] is None
    assert cache[key_id]['custom']['custom'] is None
    assert not probe_cache.key_probe_is_fresh(
        cache[key_id],
        now=201,
        custom_checks=[{'id': 'custom', 'urls': ['https://example.test']}],
    )
    assert not probe_cache.key_probe_has_required_results(
        cache[key_id],
        custom_checks=[{'id': 'custom', 'urls': ['https://example.test']}],
    )


def test_probe_cache_ignores_stale_schema(tmp_path):
    cache_path = tmp_path / 'key_probe_cache.json'
    old_path = probe_cache.KEY_PROBE_CACHE_PATH
    probe_cache.KEY_PROBE_CACHE_PATH = str(cache_path)
    try:
        fresh_key = probe_cache.hash_key('fresh')
        stale_key = probe_cache.hash_key('stale')
        cache_path.write_text(
            json.dumps({
                fresh_key: {
                    'schema': probe_cache.KEY_PROBE_CACHE_SCHEMA_VERSION,
                    'proto': 'vless',
                    'tg_ok': True,
                    'yt_ok': True,
                    'ts': 100,
                },
                stale_key: {
                    'proto': 'vless',
                    'tg_ok': True,
                    'yt_ok': True,
                    'custom': {'chatgpt_services': True, 'claude': True},
                    'ts': 100,
                },
            }),
            encoding='utf-8',
        )
        loaded = probe_cache.load_key_probe_cache()
    finally:
        probe_cache.KEY_PROBE_CACHE_PATH = old_path

    assert fresh_key in loaded
    assert stale_key not in loaded
    assert not probe_cache.key_probe_is_fresh({'ts': 100}, now=101)
    assert not probe_cache.key_probe_has_required_results({'tg_ok': True, 'yt_ok': True})


def test_probe_cache_invalidates_changed_custom_check_targets():
    cache = {}
    old_checks = [{'id': 'chatgpt_services', 'urls': ['https://old.example.test']}]
    new_checks = [{'id': 'chatgpt_services', 'urls': ['https://api.openai.com/v1/models']}]
    assert probe_cache.update_key_probe_cache_entry(
        cache,
        'vless',
        'key-1',
        tg_ok=True,
        yt_ok=True,
        custom={'chatgpt_services': True},
        custom_checks=old_checks,
        now=100,
    )
    entry = cache[probe_cache.hash_key('key-1')]
    assert probe_cache.key_probe_is_fresh(entry, now=101, custom_checks=old_checks)
    assert probe_cache.key_probe_has_required_results(entry, custom_checks=old_checks)
    assert not probe_cache.key_probe_is_fresh(entry, now=101, custom_checks=new_checks)
    assert not probe_cache.key_probe_has_required_results(entry, custom_checks=new_checks)


def test_probe_cache_failed_results_expire_quickly():
    checks = [{'id': 'discord', 'urls': ['https://discord.com']}]
    entry = {
        'schema': probe_cache.KEY_PROBE_CACHE_SCHEMA_VERSION,
        'proto': 'vless2',
        'tg_ok': 'unknown',
        'yt_ok': False,
        'custom': {'discord': True},
        'custom_sig': probe_cache.custom_checks_signature(checks),
        'ts': 100,
    }
    assert probe_cache.key_probe_is_fresh(
        entry,
        now=100 + probe_cache.KEY_PROBE_FAILURE_TTL - 1,
        custom_checks=checks,
    )
    assert not probe_cache.key_probe_is_fresh(
        entry,
        now=100 + probe_cache.KEY_PROBE_FAILURE_TTL,
        custom_checks=checks,
    )


def test_probe_cache_keeps_recent_success_on_transient_downgrade():
    cache = {}
    checks = [{'id': 'chatgpt_services', 'urls': ['https://api.openai.com/v1/models']}]
    assert probe_cache.update_key_probe_cache_entry(
        cache,
        'vless',
        'key-1',
        tg_ok=True,
        yt_ok=True,
        custom={'chatgpt_services': True},
        custom_checks=checks,
        now=100,
    )
    entry = cache[probe_cache.hash_key('key-1')]
    assert not probe_cache.update_key_probe_cache_entry(
        cache,
        'vless',
        'key-1',
        tg_ok=False,
        yt_ok=False,
        custom={'chatgpt_services': False},
        custom_checks=checks,
        now=120,
        min_write_interval=0,
    )
    assert entry['tg_ok'] is True
    assert entry['yt_ok'] is True
    assert entry['custom']['chatgpt_services'] is True
    assert entry['ts'] == 100

    assert probe_cache.update_key_probe_cache_entry(
        cache,
        'vless',
        'key-1',
        tg_ok=False,
        yt_ok=False,
        custom={'chatgpt_services': False},
        custom_checks=checks,
        now=500,
        min_write_interval=0,
    )
    entry = cache[probe_cache.hash_key('key-1')]
    assert entry['tg_ok'] is False
    assert entry['yt_ok'] is False
    assert entry['custom']['chatgpt_services'] is False
    assert entry['ts'] == 500


def test_pool_probe_config_does_not_pin_telegram_api_ip():
    config = pool_probe_runner.build_pool_probe_core_config_batch(
        [('vless', 'vless://id@example.com:443?security=tls#sample')],
        29000,
        lambda proto, key, tag, email='pool-probe@local': {
            'protocol': 'freedom',
            'tag': tag,
            'settings': {},
        },
    )
    assert config['dns']['queryStrategy'] == 'UseIPv4'
    assert 'api.telegram.org' not in config['dns'].get('hosts', {})
    assert '149.154.167.220' not in json.dumps(config)


def test_web_template_scripts_helpers():
    scripts = web_template_scripts.render_web_scripts(
        POOL_PROBE_UI_POLL_EXTENSION_MS=1000,
        TELEGRAM_SVG_B64='tg',
        YOUTUBE_SVG_B64='yt',
        csrf_token='token',
        custom_checks_json='[{"id":"x"}]',
        initial_command_running='false',
        initial_status_pending='false',
        enable_key_pool=False,
        enable_custom_checks=False,
    )
    assert 'const APP_CONFIG = window.BK_APP_CONFIG || {};' in scripts
    assert 'const INITIAL_STATUS_PENDING = !!APP_CONFIG.initialStatusPending;' in scripts
    assert 'const ENABLE_KEY_POOL = APP_CONFIG.enableKeyPool !== false;' in scripts
    assert "const CSRF_TOKEN = String(APP_CONFIG.csrfToken || '');" in scripts
    assert '"token"' not in scripts
    assert "glass: 'Liquid Glass'" in scripts
    assert 'function toggleThemePicker()' in scripts
    assert 'function setupLiquidPointer()' in scripts
    assert 'liquid-global-lens' in scripts
    assert '.topbar-actions' not in scripts
    assert 'button:not(.pool-delete-btn)' in scripts
    assert '.mobile-nav' in scripts
    assert '.segmented' in scripts
    assert 'data-liquid-group' in scripts
    assert 'function isLiquidGroupElement(element)' in scripts
    assert ".hero-popover [data-liquid=\"true\"]" in scripts
    assert 'function moveGlobalLens(clientX, clientY, holdMs)' in scripts
    assert 'function clampLiquidLensPoint(clientX, clientY)' in scripts
    assert 'window.visualViewport' in scripts
    assert "globalLens.style.setProperty('--lx', lensPoint.x.toFixed(1) + 'px')" in scripts
    assert 'function findLiquidAction(clientX, clientY)' in scripts
    assert 'function applyLiquidAction(clientX, clientY)' in scripts
    assert 'function trackLiquidMovement(state, clientX, clientY)' in scripts
    assert 'function resetLiquidState()' in scripts
    assert 'function loadedPoolProtocolQuery()' in scripts
    assert 'function schedulePoolView(proto, delayMs)' in scripts
    assert 'const rowByKeyId = new Map();' in scripts
    assert "fetch('/api/pools' + loadedPoolProtocolQuery()" in scripts
    assert 'state.scrolled = true' in scripts
    assert "if (typeof delay === 'number' && delay <= 0)" in scripts
    assert 'if (liquidTouchState && liquidTouchState.scrolled)' in scripts
    assert 'if (liquidPointerState.scrolled)' in scripts
    assert "window.addEventListener('scroll'" in scripts
    assert "document.addEventListener('visibilitychange'" in scripts
    assert 'window.scrollY || window.pageYOffset || 0' in scripts
    assert "document.querySelectorAll('[data-liquid].liquid-active')" in scripts
    assert 'action.blur' in scripts
    assert 'function shouldAnimateLiquidFocus(element)' in scripts
    assert "element.matches(':focus-visible')" in scripts
    assert 'function suppressLiquidFocus(ms)' in scripts
    assert "element.classList.add('liquid-resetting')" in scripts
    assert "element.classList.remove('liquid-resetting')" in scripts
    assert 'button[type="button"], a[href], [role="button"]' in scripts
    assert 'liquidSyntheticTarget' in scripts
    assert 'lastLensPoint' not in scripts
    assert "globalLens.style.setProperty('--lr'" not in scripts
    assert "globalLens.style.setProperty('--lsx'" not in scripts
    assert 'lensTarget' not in scripts
    assert 'function renderLiquidLens()' not in scripts
    assert 'function queueActivateFromPoint(clientX, clientY, holdMs)' in scripts
    assert 'if (!glassThemeActive())' in scripts
    assert 'function cancelQueuedLiquidMove()' in scripts
    assert 'window.requestAnimationFrame' in scripts
    assert 'function hideActionMessage()' in scripts
    assert 'function scheduleActionMessageHide(delayMs)' in scripts
    assert 'function maybeReloadAfterUpdateCommand(state)' in scripts
    assert 'actionMessageTimer' in scripts
    assert 'activeCommandName' in scripts
    assert "document.addEventListener('touchstart'" in scripts
    assert "document.addEventListener('touchmove'" in scripts
    assert "document.addEventListener('touchend'" in scripts
    assert "document.addEventListener('pointercancel'" in scripts
    assert 'elementFromPoint' in scripts
    assert "localStorage.setItem('router-theme', nextTheme);" in scripts
    assert 'function setupAsyncForms' in scripts
    assert 'function setupProtocolTabs()' in scripts
    assert "fetch('/api/protocol_panel?proto='" in scripts
    assert 'data-key="' not in scripts
    assert 'name="key_id"' in scripts
    assert 'function setupProtocolSubtabs(root)' in scripts
    assert 'function renderStatusAttention(snapshot)' in scripts
    assert "items.push(['info', 'Проверка пула выполняется'" not in scripts
    assert 'проверка пула сейчас не мешает работе' not in scripts
    assert 'poolProbeVisible' in scripts
    assert "apiPill.textContent = poolProbeVisible" in scripts
    assert 'function updatePoolProbeControls(active)' in scripts
    assert "document.querySelectorAll('[data-pool-probe-cancel-button]')" in scripts
    assert 'if (poolProbeActive && !document.hidden)' in scripts
    assert 'refreshPoolData(2500)' in scripts
    assert 'function poolRowMatchesState(row, state)' in scripts
    assert 'function poolStateFilterFromMode(mode)' in scripts
    assert "formData.set('confirm_switch', 'yes');" in scripts
    assert '{{' not in scripts


def test_web_form_template_smoke():
    page = web_form_template.render_web_form(
        APP_BRANCH_DESCRIPTION='test',
        APP_BRANCH_LABEL='codex/test',
        APP_VERSION_LABEL='1',
        POOL_PROBE_UI_POLL_EXTENSION_MS=1000,
        TELEGRAM_SVG_B64='tg-icon',
        YOUTUBE_SVG_B64='',
        _telegram_icon_html=lambda opacity=1.0: 'TG',
        csrf_token='token',
        command_block='',
        command_buttons_html='',
        app_runtime_mode_description='интерфейс с пулом ключей и Telegram-бот',
        app_runtime_mode_label='Сложный',
        app_runtime_mode_picker_block='',
        current_mode_label='Без прокси',
        custom_checks_json='[]',
        fallback_block='',
        initial_command_running='false',
        initial_status_pending='false',
        list_route_label='list',
        message_block='',
        mode_picker_block='',
        mode_toggle_label='Режим:',
        pool_summary={'active_text': 'none'},
        pool_summary_note='',
        protocol_panels_html='',
        protocol_tabs_html='',
        quick_key_label='Vless 1',
        quick_key_proto='vless',
        quick_key_value='',
        quick_start_note='note',
        router_health={'memory_text': '10 / 64 MB', 'note': 'load 0.01', 'dns_note': 'DNS: ndnproxy'},
        socks_block='',
        start_button_label='start',
        status={'api_status': 'ok'},
        topbar_status_text='ok',
        unblock_panels_html='',
        unblock_tabs_html='',
        enable_key_pool=False,
        enable_custom_checks=False,
    )
    assert '/static/app.css?v=' in page
    assert '/static/app.js?v=' in page
    assert 'class="app-shell"' in page
    assert 'app-mode-toggle-button' in page
    assert 'active-mode-control' in page
    assert 'active-mode-dns-note' in page
    assert 'theme-picker' in page
    assert 'data-theme-choice="glass"' in page
    assert 'Liquid Glass' in page
    assert 'service-command-grid' in page
    assert 'quick-start-actions' in page
    assert 'router-memory-text' in page
    assert 'router-memory-meter' in page
    assert 'status-attention-list' in page
    assert 'status-overview-head' in page
    assert 'Панель состояния' not in page
    assert '10 / 64 MB' in page
    assert 'DNS: ndnproxy' in page
    assert 'value="update"' not in page
    assert 'Локальная панель управления обходом на роутере' in page
    assert 'Режим работы: интерфейс с пулом ключей и Telegram-бот' in page
    assert 'Переустановка компонентов' not in page
    assert '{TELEGRAM_SVG_B64}' not in page
    assert 'window.BK_APP_CONFIG=' in page
    assert '"csrfToken":"token"' in page
    assert '"enableKeyPool":false' in page
    assert '"enableTelegram":true' in page
    assert '<script src="/static/app.js' in page
    web_only_page = web_form_template.render_web_form(
        APP_BRANCH_DESCRIPTION='test',
        APP_BRANCH_LABEL='codex/test',
        APP_VERSION_LABEL='1',
        POOL_PROBE_UI_POLL_EXTENSION_MS=1000,
        TELEGRAM_SVG_B64='tg-icon',
        YOUTUBE_SVG_B64='',
        _telegram_icon_html=lambda opacity=1.0: 'TG',
        csrf_token='token',
        command_block='',
        command_buttons_html='',
        app_runtime_mode_description='интерфейс с пулом ключей без Telegram-бота',
        app_runtime_mode_label='Web only',
        app_runtime_mode_picker_block='',
        current_mode_label='Без прокси',
        custom_checks_json='[]',
        fallback_block='',
        initial_command_running='false',
        initial_status_pending='false',
        list_route_label='list',
        message_block='',
        mode_picker_block='',
        mode_toggle_label='Режим:',
        pool_summary={'active_text': 'none'},
        pool_summary_note='',
        protocol_panels_html='',
        protocol_tabs_html='',
        quick_key_label='Vless 1',
        quick_key_proto='vless',
        quick_key_value='',
        quick_start_note='note',
        router_health={'memory_text': '10 / 64 MB', 'note': 'load 0.01'},
        socks_block='',
        start_button_label='',
        status={'api_status': 'ok'},
        topbar_status_text='ok',
        unblock_panels_html='',
        unblock_tabs_html='',
        enable_key_pool=True,
        enable_custom_checks=True,
        enable_telegram=False,
    )
    assert 'action="/start"' not in web_only_page
    assert 'Telegram отключ' not in web_only_page
    assert 'web-api-pill' not in web_only_page
    assert 'id="mode-toggle-button"' not in web_only_page
    assert 'active-mode-card' not in web_only_page
    assert 'data-pool-probe-cancel-button disabled aria-disabled="true"' in web_only_page
    assert 'Telegram API отвечает' not in web_only_page
    assert 'Веб-интерфейс, состояние роутера' in web_only_page
    assert '"enableTelegram":false' in web_only_page
    assert 'value="update"' not in web_only_page


def test_telegram_pool_ui():
    markup = telegram_pool_ui.pool_protocol_markup(
        _FakeTypes,
        ['Vless 1', 'Vless 2', 'Vmess', 'Trojan', 'Shadowsocks'],
    )
    assert markup.resize_keyboard is True
    assert markup.rows[0] == ['Vless 1', 'Vless 2']
    assert markup.rows[-1][0].startswith('\U0001f519')

    label = telegram_pool_ui.pool_key_button_label(
        1,
        'key-value',
        probe={'tg_ok': True, 'yt_ok': False},
        current_key='key-value',
        proto='vless',
        display_name=lambda value: 'Example Key',
    )
    assert label.startswith('\u2705 V1 1.')
    assert 'TG\u2705 YT\u274c' in label


def test_vless2_cached_youtube_failure_is_rechecked_on_permanent_port():
    source = (ROOT / 'bot.py').read_text(encoding='utf-8')
    assert 'key_name == _youtube_route_protocol()' in source
    assert "probe.get('yt_ok') is not True" in source
    assert "def _schedule_youtube_cache_confirm" in source
    assert "def _schedule_vless2_youtube_cache_confirm" in source
    assert "YOUTUBE_VLESS2_HEALTHCHECK_MIN_OK" in source
    assert "_controller_check_youtube_through_proxy" in source
    assert "service='youtube'" in source
    assert 'Reality endpoint repair restored current' in source
    assert "_record_key_probe(proto, key_value, yt_ok=True)" in source
    assert "_invalidate_key_status_cache()" in source


def test_event_history_helpers():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'events.jsonl'
        assert event_history.record_event(
            action='route',
            message='installed vless://secret@example.test:443#name',
            protocol='vless',
            service='telegram',
            event_path=str(path),
        )
        events = event_history.load_events(event_path=str(path))
    assert events[0]['protocol_label'] == 'Vless 1'
    assert '<proxy-key-hidden>' in events[0]['message']
    assert 'vless://' not in events[0]['message']


def test_update_status_helpers():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'update.json'
        status = update_status.write_update_status(
            command='update',
            running=True,
            progress=42,
            progress_label='Downloading',
            message='step',
            path=str(path),
        )
        assert status['running'] is True
        assert update_status.read_update_status(str(path))['progress'] == 42
        finished = update_status.finish_update_status('update', 'done', path=str(path))
        assert finished['running'] is False
        assert finished['progress'] == 100


def test_service_routes_apply_and_profile():
    with tempfile.TemporaryDirectory() as tmp:
        callbacks = []
        discord_entries = service_catalog.SERVICE_LIST_SOURCES['discord']['entries']
        (Path(tmp) / 'vless.txt').write_text(discord_entries[0] + '\n', encoding='utf-8')
        (Path(tmp) / 'vless-2.txt').write_text('\n'.join(discord_entries[:2]) + '\n', encoding='utf-8')
        result = service_routes.apply_service_route(
            'discord',
            'vless',
            unblock_dir=tmp,
            update_script='',
            before_update=lambda: callbacks.append('route'),
        )
        assert result['target_label'] == 'Vless 1'
        assert callbacks == ['route']
        vless_entries = (Path(tmp) / 'vless.txt').read_text(encoding='utf-8').splitlines()
        vless2_entries = (Path(tmp) / 'vless-2.txt').read_text(encoding='utf-8').splitlines()
        assert set(discord_entries) <= set(vless_entries)
        assert not (set(discord_entries) & set(vless2_entries))
        profile = service_routes.apply_service_profile(
            'youtube_vless2_rest_vless',
            service_items=[{'id': 'youtube'}, {'id': 'telegram'}],
            unblock_dir=tmp,
            update_script='',
            before_update=lambda: callbacks.append('profile'),
        )
        assert profile['services'] == 2
        assert callbacks == ['route', 'profile']
        assert service_catalog.YOUTUBE_UNBLOCK_ENTRIES[0] in (Path(tmp) / 'vless-2.txt').read_text(encoding='utf-8')
        assert service_catalog.TELEGRAM_UNBLOCK_ENTRIES[0] in (Path(tmp) / 'vless.txt').read_text(encoding='utf-8')


def test_route_intersections_helpers():
    with tempfile.TemporaryDirectory() as tmp:
        callbacks = []
        (Path(tmp) / 'vless.txt').write_text('example.com\n198.51.100.0/24\n', encoding='utf-8')
        (Path(tmp) / 'vless-2.txt').write_text('api.example.com\n198.51.100.10\n', encoding='utf-8')
        report = route_intersections.analyze_route_intersections(unblock_dir=tmp)
        assert report['count'] >= 2
        result = route_intersections.resolve_route_intersections(
            'vless-2',
            unblock_dir=tmp,
            update_script='',
            before_update=lambda: callbacks.append('sync'),
        )
        assert result['moved'] >= 2
        assert callbacks == ['sync']
        assert 'example.com' in (Path(tmp) / 'vless-2.txt').read_text(encoding='utf-8')
        assert 'example.com' not in (Path(tmp) / 'vless.txt').read_text(encoding='utf-8')


def test_service_route_ui_helpers():
    service_items = service_routes.route_service_items(presets=service_catalog.CUSTOM_CHECK_PRESETS)
    assert any(item['id'] == 'telegram' for item in service_items)
    assert any(item['id'] == 'youtube' for item in service_items)
    route_states = {item['id']: {'label': 'Vless 1', 'complete_protocols': ['vless']} for item in service_items[:2]}
    route_items = service_items[:3]
    html_text = key_pool_web.web_service_route_tools_html(
        route_items,
        route_states,
        service_routes.protocol_options(),
        lambda icon, label, opacity=1.0, size=18: f'<span>{label}</span>',
        csrf_input_html='<input type="hidden" name="csrf_token" value="x">',
        active_check_ids={route_items[2]['id']},
        core_icon_html={'telegram': 'TG', 'youtube': 'YT'},
    )
    assert '/service_route_apply' in html_text
    assert 'Сервисы и маршруты' in html_text
    assert 'service-route-trigger' in html_text
    assert 'service-route-menu-item active' in html_text
    assert 'service-route-telegram-icon' in html_text
    assert 'service-route-youtube-icon' in html_text
    assert 'service-route-choice' not in html_text
    assert '/custom_check_delete' in html_text
    assert '<select' not in html_text
    assert 'Перенести</button>' not in html_text
    assert key_pool_web.web_route_intersections_html({'count': 0}, service_routes.protocol_options())
    inactive_preset_html = key_pool_web.web_service_route_tools_html(
        [route_items[2]],
        {route_items[2]['id']: {'label': 'Vless 1', 'complete_protocols': ['vless']}},
        service_routes.protocol_options(),
        lambda icon, label, opacity=1.0, size=18: f'<span>{label}</span>',
        csrf_input_html='<input type="hidden" name="csrf_token" value="x">',
        active_check_ids=set(),
    )
    assert 'Добавится при выборе' in inactive_preset_html
    assert 'текущий маршрут' not in inactive_preset_html


def test_service_route_runtime_helpers():
    runtime = web_route_tools_runtime.ServiceRouteToolsRuntime(
        custom_check_presets_getter=lambda: service_catalog.CUSTOM_CHECK_PRESETS,
        service_icon_html=lambda icon, label, opacity=1.0, size=18: f'<span>{label}</span>',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
    )
    items = runtime.service_items()
    item_ids = {item['id'] for item in items}
    assert {'telegram', 'youtube', 'chatgpt_services'} <= item_ids
    standalone = runtime.standalone_custom_checks([
        {'id': 'chatgpt_services'},
        {'id': 'manual_check'},
    ])
    assert standalone == [{'id': 'manual_check'}]
    html_text = runtime.tools_html(
        '<input type="hidden" name="csrf_token" value="x">',
        custom_checks=[{'id': 'chatgpt_services'}],
    )
    assert 'service-route-trigger' in html_text
    assert 'service-route-telegram-icon' in html_text
    assert 'service-route-youtube-icon' in html_text


def main():
    test_app_runtime_mode_setter_callbacks()
    test_router_health_runtime_payload_uses_keenetic_memory()
    test_router_health_runtime_dns_payload()
    test_router_health_runtime_core_proxy_payload()
    test_router_health_runtime_dns_parsers()
    test_xray_compat_runtime_helpers()
    test_router_health_runtime_process_rss_parser()
    test_proxy_config_builder()
    test_proxy_status_runtime_helpers()
    test_unblock_list_helpers()
    test_unblock_lists_hide_legacy_txt_files()
    test_vless2_youtube_routes_are_scoped()
    test_chatgpt_codex_routes_are_synced()
    test_ai_assistant_custom_routes_are_synced()
    test_primary_vless_does_not_capture_gmail_domains()
    test_custom_check_service_sources_are_synced()
    test_chatgpt_codex_custom_check_migration()
    test_preset_custom_checks_are_hydrated_from_catalog()
    test_meta_custom_check_migration()
    test_chrome_remote_desktop_routes_are_in_vless()
    test_web_command_state_helpers()
    test_web_http_common_helpers()
    test_web_http_basic_auth_accepts_and_rejects_credentials()
    test_installer_common_helpers()
    test_installer_page_is_bot_setup_only()
    test_repo_update_helpers()
    test_key_pool_web()
    test_key_pool_subscription_helpers()
    test_telegram_pool_ui()
    test_web_get_actions_helpers()
    test_web_form_blocks_helpers()
    test_web_pool_form_blocks_helpers()
    test_web_status_builder_helpers()
    test_web_template_styles_helpers()
    test_probe_cache_update_entry_min_interval()
    test_probe_cache_invalidates_changed_custom_check_targets()
    test_probe_cache_failed_results_expire_quickly()
    test_probe_cache_keeps_recent_success_on_transient_downgrade()
    test_web_template_scripts_helpers()
    test_web_form_template_smoke()
    test_web_post_actions_helpers()
    test_web_action_feature_gates()
    test_service_route_apply_can_add_check()
    test_codex_version_matches_commit_count()
    test_ipset_refresh_is_backend_aware_and_atomic()
    test_runtime_startup_limits_router_flash_and_overhead()
    test_web_response_body_ignores_client_disconnect()
    test_entware_dns_runtime_helpers()
    test_web_status_runtime_helpers()
    test_telegram_confirm_state_source()
    test_telegram_confirm_helpers()
    test_telegram_auth_state_helpers()
    test_telegram_message_flow_helpers()
    test_telegram_jobs_helpers()
    test_telegram_install_ui_helpers()
    test_telegram_key_ui_helpers()
    test_telegram_bot_menu_button_smoke()
    test_telegram_info_runtime_helpers()
    test_auto_failover_runtime_helpers()
    test_proxy_apply_runtime_helpers()
    test_pool_probe_controller_helpers()
    test_vless2_cached_youtube_failure_is_rechecked_on_permanent_port()
    test_event_history_helpers()
    test_update_status_helpers()
    test_service_routes_apply_and_profile()
    test_route_intersections_helpers()
    test_service_route_ui_helpers()
    test_service_route_runtime_helpers()
    test_pool_probe_runner_failover_candidate()
    print('smoke_modules: ok')


if __name__ == '__main__':
    main()
