from pathlib import Path
from io import BytesIO
import base64
import gzip
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
APP_ROOT = ROOT / 'app'
ROOT_RUNTIME_DOCS = {'version.md', 'README.md', 'CHANGELOG.md'}
sys.path.insert(0, str(APP_ROOT))
sys.path.insert(0, str(ROOT))


def source_path(name):
    return ROOT / name if name in ROOT_RUNTIME_DOCS else APP_ROOT / name

import key_pool_web
import key_pool_store
import subscription_runtime
import app_version
import app_runtime_mode
import router_health_runtime
import router_metrics
import xray_compat_runtime
import telegram_pool_ui
import web_get_actions
import web_background
import web_command_state
import web_commands_runtime
import web_form_blocks
import web_form_template
import web_http_common
import web_pool_form_blocks
import web_pool_snapshot_worker
import web_route_tools_runtime
import web_service_routes_worker
import web_status_builder
import web_post_actions
import web_status_runtime
import telegram_confirm
import telegram_auth_state
import telegram_jobs
import telegram_message_flow
import telegram_install_ui
import telegram_key_ui
import telegram_info_runtime
import telegram_call_learning
import telegram_healthcheck
import pool_probe_controller
import pool_probe_curl
import pool_probe_process_runner
import pool_probe_runner
import probe_cache
import auto_failover_runtime
import proxy_apply_runtime
import proxy_status
import proxy_protocols
import unblock_lists
import service_catalog
import custom_checks_store
import custom_check_policy
import installer_common
import installer
import repo_update
import entware_dns_runtime
import event_history
import failover_candidate_runner
import health_check_runner
import route_intersections
import service_routes
import update_status
import youtube_healthcheck
import youtube_edge_prefetch
import youtube_edge_prefetch_runner
import youtube_route_owner
from proxy_config_builder import build_proxy_core_config, build_shadowsocks_config, build_trojan_config


def test_pool_probe_runner_defers_failover_healthcheck_imports():
    script = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(APP_ROOT)!r})\n"
        "import pool_probe_runner\n"
        "names = ('telegram_healthcheck', 'youtube_healthcheck')\n"
        "print(json.dumps({name: name in sys.modules for name in names}, sort_keys=True))\n"
    )
    result = subprocess.run(
        [sys.executable, '-c', script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    assert json.loads(result.stdout) == {
        'telegram_healthcheck': False,
        'youtube_healthcheck': False,
    }


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
    'shadowsocks_tproxy': 11802,
    'vmess_tproxy': 11815,
    'vless_tproxy': 11812,
    'vless2_tproxy': 11814,
    'trojan_tproxy': 11829,
}


def _extract_udp_policy_python(script_text):
    marker = 'from service_catalog import REALTIME_CALL_SIGNAL_ROUTE_ENTRIES, TELEGRAM_CALL_SIGNAL_ROUTE_ENTRIES, YOUTUBE_UNBLOCK_ENTRIES'
    marker_at = script_text.index(marker)
    heredoc_at = script_text.rfind("<<'PY'", 0, marker_at)
    start = script_text.index('\n', heredoc_at) + 1
    end = script_text.index('\nPY\n', marker_at)
    return script_text[start:end]


def _run_udp_policy_python(
    script_path,
    policy,
    youtube_route='vless-2.txt',
    telegram_route='',
    realtime_call_route='',
    telegram_policy='auto',
    vless2_quic_enabled=None,
):
    source = _extract_udp_policy_python(script_path.read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        runtime_dir = tmp_path / 'runtime'
        unblock_dir = tmp_path / 'unblock'
        runtime_dir.mkdir()
        unblock_dir.mkdir()
        (runtime_dir / 'service_catalog.py').write_text(
            "TELEGRAM_UNBLOCK_ENTRIES = ('telegram.org', '149.154.160.0/20')\n"
            "TELEGRAM_CALL_SIGNAL_ROUTE_ENTRIES = ('telegram.org', '149.154.160.0/20')\n"
            "REALTIME_CALL_SIGNAL_ROUTE_ENTRIES = ('telegram.org', '149.154.160.0/20', 'discord.com', 'whatsapp.com')\n"
            "YOUTUBE_UNBLOCK_ENTRIES = ('youtube.com', 'www.youtube.com')\n",
            encoding='utf-8',
        )
        config_text = (
            f"youtube_quic_policy = {policy!r}\n"
            f"telegram_udp_policy = {telegram_policy!r}\n"
            "ipv6_bypass_fallback_enabled = True\n"
        )
        if vless2_quic_enabled is not None:
            config_text += f"udp_quic_block_vless2_enabled = {bool(vless2_quic_enabled)!r}\n"
        (runtime_dir / 'bot_config.py').write_text(config_text, encoding='utf-8')
        route_files = {
            filename: ['example.org']
            for filename in ('shadowsocks.txt', 'vmess.txt', 'vless.txt', 'vless-2.txt', 'trojan.txt')
        }
        if youtube_route:
            route_files.setdefault(youtube_route, []).append('www.youtube.com')
        if telegram_route:
            route_files.setdefault(telegram_route, []).append('telegram.org')
        if realtime_call_route:
            route_files.setdefault(realtime_call_route, []).append('discord.com')
        for filename, entries in route_files.items():
            (unblock_dir / filename).write_text('\n'.join(entries) + '\n', encoding='utf-8')
        env = os.environ.copy()
        env['PYTHONPATH'] = str(runtime_dir)
        env['UNBLOCK_DIR'] = str(unblock_dir)
        result = subprocess.run(
            [sys.executable, '-c', source],
            cwd=str(runtime_dir),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    return dict(
        line.split('=', 1)
        for line in result.stdout.splitlines()
        if line.startswith('BYPASS_') or line.startswith('TELEGRAM_CALL_')
    )


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
            'cpuload': 2,
        },
        load_text='0.10 / 0.14 / 0.10',
        cpu_percent=0.84,
        bot_rss_kb=52 * 1024,
        probe_progress={'running': False, 'total': 0},
        temp_xray_count=0,
        flash_storage={'path': '/opt', 'total_kb': 2048 * 1024, 'used_kb': 768 * 1024, 'free_kb': 1280 * 1024},
    )
    assert payload['memory_source'] == 'keenetic'
    assert payload['memory_text'] == 'Память: доступно 201 MB из 485 MB'
    assert payload['used_percent'] == 55
    assert payload['total_kb'] == 485 * 1024
    assert payload['router_total_kb'] == 512 * 1024
    assert payload['cpu_percent'] == 2
    assert payload['cpu_source'] == 'keenetic'
    assert payload['cpu_sample_percent'] == 0.84
    assert payload['pool_probe_text'] == 'Не запущена'
    assert payload['note'].splitlines()[0] == 'Занято по данным роутера: 281 MB (55%); Нагрузка CPU: 2%'
    assert 'Нагрузка CPU: 2%' in payload['note']
    assert 'Программа использует 52 MB RAM' in payload['note']
    assert 'Flash-носитель: занято 768 из 2048 MB (38%)' in payload['note']
    assert '\n\n' not in payload['note']
    assert 'Свободно:' not in payload['note']
    assert 'Доступно для приложений:' not in payload['note']
    assert 'Кэш и буферы:' not in payload['note']
    assert 'Swap:' not in payload['note']
    assert payload['flash_storage_path'] == '/opt'
    assert payload['flash_used_percent'] == 38
    assert not payload['note'].endswith('.')
    assert 'Проверка пула' not in payload['note']


def test_router_health_runtime_payload_uses_stable_cpu_label_before_first_sample():
    payload = router_health_runtime.build_router_health_payload(
        meminfo={'MemTotal': 512 * 1024, 'MemFree': 256 * 1024, 'MemAvailable': 256 * 1024},
        ndmc_system={'memory_used': 291 * 1024, 'memory_total': 512 * 1024},
        load_text='0.23 / 0.18 / 0.16',
        cpu_percent=None,
        bot_rss_kb=63 * 1024,
        probe_progress={'running': False, 'total': 0},
        temp_xray_count=0,
        flash_storage={'path': '/opt', 'total_kb': 29527 * 1024, 'used_kb': 862 * 1024, 'free_kb': 28665 * 1024},
    )
    assert payload['note'].splitlines()[0] == 'Занято по данным роутера: 291 MB (57%); Нагрузка CPU: -'
    assert 'Средняя нагрузка' not in payload['note']
    assert '\n\n' not in payload['note']


def test_router_health_runtime_payload_marks_proc_fallbacks_explicitly():
    payload = router_health_runtime.build_router_health_payload(
        meminfo={
            'MemTotal': 512 * 1024,
            'MemFree': 128 * 1024,
            'Buffers': 32 * 1024,
            'Cached': 64 * 1024,
            'SReclaimable': 16 * 1024,
            'MemAvailable': 224 * 1024,
        },
        ndmc_system={},
        load_text='0.10 / 0.08 / 0.06',
        cpu_percent=0.84,
        bot_rss_kb=52 * 1024,
        probe_progress={'running': False, 'total': 0},
        temp_xray_count=0,
    )
    assert payload['memory_source'] == 'proc'
    assert payload['memory_text'] == 'Память: доступно 224 MB из 512 MB'
    assert payload['available_kb'] == 224 * 1024
    assert payload['linux_cache_kb'] == 112 * 1024
    assert payload['router_cache_kb'] == 96 * 1024
    assert payload['cpu_percent'] == 0.84
    assert payload['cpu_source'] == 'proc'
    assert payload['cpu_sample_percent'] == 0.84
    assert payload['note'].splitlines()[0] == 'Занято: 288 MB (56%); Нагрузка CPU: 0.84%'


def test_router_health_runtime_program_rss_includes_related_processes():
    payload = router_health_runtime.build_router_health_payload(
        meminfo={'MemTotal': 512 * 1024, 'MemFree': 64 * 1024, 'MemAvailable': 160 * 1024},
        ndmc_system={'memory_used': 318 * 1024, 'memory_total': 512 * 1024},
        load_text='0.46 / 0.37 / 0.35',
        cpu_percent=53.28,
        bot_rss_kb=63 * 1024,
        xray_rss_kb=24 * 1024,
        pool_worker_rss_kb=38 * 1024,
        temporary_xray_rss_kb=18 * 1024,
        youtube_prefetch_rss_kb=14 * 1024,
        background_worker_rss_kb=7 * 1024,
        probe_progress={'running': True, 'checked': 104, 'total': 158},
        temp_xray_count=1,
        flash_storage={'path': '/opt', 'total_kb': 29527 * 1024, 'used_kb': 774 * 1024, 'free_kb': 28753 * 1024},
    )
    assert payload['program_rss_kb'] == 164 * 1024
    assert payload['xray_rss_kb'] == 24 * 1024
    assert payload['pool_worker_rss_kb'] == 38 * 1024
    assert payload['temporary_xray_rss_kb'] == 18 * 1024
    assert payload['youtube_prefetch_rss_kb'] == 14 * 1024
    assert payload['background_worker_rss_kb'] == 7 * 1024
    assert payload['note'].splitlines()[0] == 'Занято по данным роутера: 318 MB (62%); Нагрузка CPU: 53.28%'
    assert 'Программа использует 164 MB RAM: бот 63 MB, Xray 24 MB, проверка пула 38 MB, временный Xray 18 MB, YouTube prefetch 14 MB, фоновые задачи 7 MB' in payload['note']
    assert 'Flash-носитель: занято 774 из 29527 MB (3%)' in payload['note']
    assert '\n\n' not in payload['note']


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
    assert 'ipset обновлён: 1 мин назад' in payload['dns_note']
    assert '(успешно)' not in payload['dns_note']
    assert payload['dns_note'].count('ipset обновлён') == 1
    assert 'VLESS=12' in payload['dns_note']
    assert 'VLESSUDP=5' in payload['dns_note']
    assert 'VLESS2=34' in payload['dns_note']
    assert 'VLESS2UDP=12' in payload['dns_note']


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
            'xray_config_message': 'verbose config output that should not be echoed while healthy',
            'telegram_call': {'ok': True},
            'ports': {10811: True, 10812: True, 10813: True, 10814: True},
        },
    )
    assert payload['core_proxy_health']['ok'] is True
    assert 'xray_config_message' not in payload['core_proxy_health']
    assert 'telegram_call' not in payload['core_proxy_health']
    assert payload['telegram_call_health']['ok'] is True
    assert payload['core_proxy_note'] == 'Прокси: Xray работает на портах: 10811, 10812, 10813, 10814'
    warning_note = xray_compat_runtime.core_proxy_note({
        'ok': False,
        'xray_state': 'alive',
        'xray_config_ok': True,
        'ports': {10811: True, 10812: True, 10813: True, 10814: False},
    })
    assert warning_note == 'Прокси: Xray работает на портах: 10811, 10812, 10813. Порт 10814 не работает'
    error_payload = router_health_runtime.build_router_health_payload(
        meminfo={'MemTotal': 64 * 1024, 'MemFree': 8 * 1024, 'MemAvailable': 32 * 1024},
        ndmc_system={},
        load_text='0.01 / 0.02 / 0.03',
        bot_rss_kb=4 * 1024,
        probe_progress={'running': False, 'total': 0},
        temp_xray_count=0,
        core_proxy_health={
            'ok': False,
            'xray_state': 'dead',
            'xray_config_ok': False,
            'xray_config_message': 'line 1\nline 2\nline 3\nline 4',
            'ports': {10811: False},
        },
    )
    assert error_payload['core_proxy_health']['xray_config_message'] == 'line 2\nline 3\nline 4'
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
    status_counts = {
        'counts': {
            'unblockvless': '516',
            'unblockvless2': 221,
            'unblockvlessudp': '210',
            'unblockvless2udp': 207,
        },
        'updated_at': 100,
        'dns_backend': 'dnsmasq',
        'status': 'success',
        'message': 'ipset refresh completed.',
    }
    assert router_health_runtime.ipset_counts_from_status(status_counts)['unblockvless'] == 516
    commands = []

    def fake_run(command, timeout=2):
        commands.append(tuple(command))
        if command[:2] == ['netstat', '-lnptu']:
            return 'tcp 0 0 0.0.0.0:53 0.0.0.0:* LISTEN 12/dnsmasq\n'
        if command[:2] == ['/opt/etc/init.d/S56dnsmasq', 'status']:
            return 'running'
        if command[:2] == ['ipset', 'list']:
            raise AssertionError('ipset list should not run when status counts are available')
        return ''

    dns_health = router_health_runtime.read_dns_health(
        run_text=fake_run,
        read_text=lambda path, max_bytes=8192: json.dumps(status_counts),
        time_provider=lambda: 160,
    )
    assert dns_health['backend'] == 'dnsmasq'
    assert dns_health['ipset_counts']['unblockvless2'] == 221
    assert dns_health['ipset_refresh_age_seconds'] == 60
    assert not any(command[:2] == ('ipset', 'list') for command in commands)


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


def test_router_health_runtime_related_process_snapshot():
    temp_dir = tempfile.TemporaryDirectory()
    proc_root = Path(temp_dir.name) / 'proc'
    proc_root.mkdir()

    def add_proc(pid, cmdline, rss_kb):
        proc_dir = proc_root / str(pid)
        proc_dir.mkdir()
        (proc_dir / 'cmdline').write_text(cmdline, encoding='utf-8')
        (proc_dir / 'status').write_text(f'Name:\tproc\nVmRSS:\t  {rss_kb} kB\n', encoding='utf-8')

    add_proc(101, 'xray\x00run\x00-c\x00/opt/etc/xray/config.json\x00', 24000)
    add_proc(102, '/opt/sbin/xray\x00run\x00-c\x00/tmp/bypass_pool_probe_101.json\x00', 18000)
    add_proc(103, 'python3\x00-c\x00BYPASS_KEENETIC_POOL_PROBE_WORKER=1 _run_pool_probe_process_worker\x00', 38000)
    add_proc(104, 'python3\x00/opt/etc/bot/main.py\x00', 64000)
    add_proc(105, 'python3\x00/opt/etc/bot/youtube_edge_prefetch_runner.py\x00--trigger\x00ipset-refresh\x00', 14000)
    add_proc(106, 'python3\x00-c\x00BYPASS_KEENETIC_COMMAND_WORKER=1 other worker\x00', 7000)

    def fake_read(path, max_bytes=16384):
        return Path(path).read_text(encoding='utf-8')

    snapshot = router_health_runtime.related_program_process_snapshot(
        probe_running=True,
        proc_root=str(proc_root),
        read_text=fake_read,
    )
    assert snapshot == {
        'xray_count': 1,
        'xray_rss_kb': 24000,
        'pool_worker_count': 1,
        'pool_worker_rss_kb': 38000,
        'temporary_xray_count': 1,
        'temporary_xray_rss_kb': 18000,
        'youtube_prefetch_count': 1,
        'youtube_prefetch_rss_kb': 14000,
        'background_worker_count': 1,
        'background_worker_rss_kb': 7000,
    }
    idle_snapshot = router_health_runtime.related_program_process_snapshot(
        probe_running=False,
        proc_root=str(proc_root),
        read_text=fake_read,
    )
    assert idle_snapshot['pool_worker_count'] == 1
    assert idle_snapshot['pool_worker_rss_kb'] == 38000
    assert idle_snapshot['youtube_prefetch_count'] == 1
    assert idle_snapshot['background_worker_count'] == 1
    temp_dir.cleanup()


def test_router_health_runtime_related_process_snapshot_skips_unrelated_status_reads():
    temp_dir = tempfile.TemporaryDirectory()
    proc_root = Path(temp_dir.name) / 'proc'
    proc_root.mkdir()

    for pid in range(100, 200):
        proc_dir = proc_root / str(pid)
        proc_dir.mkdir()
        cmdline = 'xray\x00run\x00-c\x00/opt/etc/xray/config.json\x00' if pid == 100 else f'kernel-worker-{pid}\x00'
        (proc_dir / 'cmdline').write_text(cmdline, encoding='utf-8')
        (proc_dir / 'status').write_text('Name:\tproc\nVmRSS:\t  24000 kB\n', encoding='utf-8')

    reads = {'cmdline': 0, 'status': 0}

    def fake_read(path, max_bytes=16384):
        if str(path).endswith('/cmdline'):
            reads['cmdline'] += 1
        elif str(path).endswith('/status'):
            reads['status'] += 1
        return Path(path).read_text(encoding='utf-8')

    snapshot = router_health_runtime.related_program_process_snapshot(
        proc_root=str(proc_root),
        read_text=fake_read,
    )
    assert snapshot['xray_count'] == 1
    assert snapshot['xray_rss_kb'] == 24000
    assert reads == {'cmdline': 100, 'status': 1}
    temp_dir.cleanup()


def test_router_health_runtime_cpu_percent_parser():
    stat_text = 'cpu  100 0 0 900 0 0 0 0 0 0\ncpu0 50 0 0 450 0 0 0 0 0 0\n'
    assert router_health_runtime.parse_cpu_stat(stat_text) == (100, 0, 0, 900, 0, 0, 0, 0, 0, 0)
    assert router_health_runtime.cpu_percent_between((100, 0, 0, 900, 0), (110, 0, 10, 980, 0)) == 20.0
    assert router_health_runtime._format_cpu_percent(0.84) == '0.84%'
    assert router_health_runtime._format_cpu_percent(2.0) == '2%'


def test_router_metrics_runtime_snapshot():
    assert router_metrics.parse_loadavg('0.20 0.60 1.02 1/245 3982') == (0.2, 0.6, 1.02)
    assert router_metrics.parse_loadavg('bad') == (0.0, 0.0, 0.0)
    assert router_metrics.parse_proc_stat_ticks('cpu  100 0 0 900 0 0') == 1000
    assert router_metrics.parse_process_ticks('123 (python3) S 0 0 0 0 0 0 0 0 0 0 20 5 0') == 25
    assert router_metrics.parse_process_rss_kb('Name:\tpython\nVmRSS:\t  63480 kB\n') == 63480

    original = {
        'read_loadavg': router_metrics.read_loadavg,
        'read_system_ticks': router_metrics.read_system_ticks,
        'process_ticks': router_metrics.process_ticks,
        'process_rss_kb': router_metrics.process_rss_kb,
        'find_pid_by_cmdline': router_metrics.find_pid_by_cmdline,
        'pid_matches_cmdline': router_metrics.pid_matches_cmdline,
        'getpid': router_metrics.os.getpid,
    }
    system_ticks = iter((1000, 1100))
    proc_ticks = {111: [100, 110], 222: [50, 70]}
    pid_scans = []

    try:
        router_metrics.read_loadavg = lambda: (0.1, 0.2, 0.3)
        router_metrics.read_system_ticks = lambda: next(system_ticks)
        router_metrics.process_ticks = lambda pid: proc_ticks[pid].pop(0)
        router_metrics.process_rss_kb = lambda pid: 64000 if pid == 111 else 24000
        router_metrics.find_pid_by_cmdline = lambda marker: pid_scans.append(marker) or 222
        router_metrics.pid_matches_cmdline = lambda pid, marker: pid == 222 and marker == router_metrics.XRAY_CMD_MARKER
        router_metrics.os.getpid = lambda: 111
        runtime = router_metrics.RouterMetricsRuntime(history_limit=10, time_provider=lambda: 100.0)
        first = runtime.snapshot(include_history=False)
        second = runtime.snapshot()
    finally:
        router_metrics.read_loadavg = original['read_loadavg']
        router_metrics.read_system_ticks = original['read_system_ticks']
        router_metrics.process_ticks = original['process_ticks']
        router_metrics.process_rss_kb = original['process_rss_kb']
        router_metrics.find_pid_by_cmdline = original['find_pid_by_cmdline']
        router_metrics.pid_matches_cmdline = original['pid_matches_cmdline']
        router_metrics.os.getpid = original['getpid']

    assert first['processes']['bot']['cpu_percent'] == 0.0
    assert second['processes']['bot']['cpu_percent'] == 10.0
    assert second['processes']['xray']['cpu_percent'] == 20.0
    assert first['summary']['samples'] == 1
    assert second['summary']['samples'] == 1
    assert second['summary']['bot_rss_max_kb'] == 64000
    assert second['thresholds']['warn_bot_rss_kb'] == 66560
    assert second['thresholds']['critical_bot_rss_kb'] == 87040
    assert 'history' not in first
    assert len(second['history']) == 1
    assert pid_scans == [router_metrics.XRAY_CMD_MARKER]


def test_router_health_runtime_slow_snapshot_caches_heavy_checks():
    calls = {'ndmc': 0, 'dns': 0, 'core': 0, 'call': 0, 'cpu_stat': 0, 'flash': 0, 'proc': 0}
    original = {
        'read_proc_meminfo': router_health_runtime.read_proc_meminfo,
        'read_proc_text': router_health_runtime.read_proc_text,
        'read_cpu_stat': router_health_runtime.read_cpu_stat,
        'read_flash_storage': router_health_runtime.read_flash_storage,
        'process_rss_kb': router_health_runtime.process_rss_kb,
        'related_program_process_snapshot': router_health_runtime.related_program_process_snapshot,
        'read_ndmc_system_snapshot': router_health_runtime.read_ndmc_system_snapshot,
        'read_dns_health': router_health_runtime.read_dns_health,
        'telegram_call_proxy_health': router_health_runtime.telegram_call_proxy_health,
        'xray_compat_runtime': router_health_runtime.xray_compat_runtime,
    }

    def fake_ndmc():
        calls['ndmc'] += 1
        return {'memory_total': 512000, 'memory_used': 256000, 'memfree': 128000}

    def fake_dns(**kwargs):
        calls['dns'] += 1
        return {'backend': 'dnsmasq', 'dnsmasq_state': 'running', 'ipset_counts': {'unblockvless': 1}}

    def fake_core_health():
        calls['core'] += 1
        return {'ok': True, 'xray_state': 'alive', 'ports': {}}

    def fake_call_health():
        calls['call'] += 1
        return {'ok': True, 'enabled': True, 'tproxy_enabled': True, 'protocols': ['vless'], 'ports': {'vless': 11812}, 'port_states': {'11812': True}}

    cpu_stats = iter((
        (100, 0, 0, 900, 0),
        (110, 0, 10, 980, 0),
        (120, 0, 20, 1060, 0),
    ))

    def fake_cpu_stat(stat_path='/proc/stat'):
        calls['cpu_stat'] += 1
        return next(cpu_stats)

    def fake_flash_storage():
        calls['flash'] += 1
        return {'path': '/opt', 'total_kb': 1024 * 1024, 'used_kb': 256 * 1024, 'free_kb': 768 * 1024}

    def fake_related_processes(probe_running=False):
        calls['proc'] += 1
        return {
            'xray_count': 1,
            'xray_rss_kb': 20 * 1024,
            'pool_worker_count': 1 if probe_running else 0,
            'pool_worker_rss_kb': 30 * 1024 if probe_running else 0,
            'temporary_xray_count': 2,
            'temporary_xray_rss_kb': 40 * 1024,
            'youtube_prefetch_count': 1,
            'youtube_prefetch_rss_kb': 14 * 1024,
            'background_worker_count': 1,
            'background_worker_rss_kb': 7 * 1024,
        }

    now = [100.0]
    try:
        router_health_runtime.read_proc_meminfo = lambda: {'MemTotal': 512000, 'MemAvailable': 256000, 'MemFree': 128000}
        router_health_runtime.read_proc_text = lambda path, max_bytes=16384: '0.01 0.02 0.03 1/100 1\n'
        router_health_runtime.read_cpu_stat = fake_cpu_stat
        router_health_runtime.read_flash_storage = fake_flash_storage
        router_health_runtime.process_rss_kb = lambda pid='self': 64000
        router_health_runtime.related_program_process_snapshot = fake_related_processes
        router_health_runtime.read_ndmc_system_snapshot = fake_ndmc
        router_health_runtime.read_dns_health = fake_dns
        router_health_runtime.telegram_call_proxy_health = fake_call_health
        router_health_runtime.xray_compat_runtime = py_types.SimpleNamespace(
            core_proxy_health=fake_core_health,
            core_proxy_note=lambda health: 'Xray: alive',
        )
        runtime = router_health_runtime.RouterHealthRuntime(
            cache_ttl=0,
            time_provider=lambda: now[0],
            core_proxy_cache_ttl=60,
            dns_cache_ttl=60,
            ndmc_cache_ttl=60,
            related_process_cache_ttl=45,
            cpu_smoothing_factor=1.0,
        )
        first = runtime.snapshot(lambda: {'running': False, 'total': 0})
        now[0] += 10
        second = runtime.snapshot(lambda: {'running': False, 'total': 0})
        now[0] += 10
        third = runtime.snapshot(lambda: {'running': True, 'total': 10})
    finally:
        for name, value in original.items():
            setattr(router_health_runtime, name, value)

    assert first['dns_backend'] == 'dnsmasq'
    assert second['dns_backend'] == 'dnsmasq'
    assert first['cpu_percent'] is None
    assert second['cpu_percent'] == 20.0
    assert first['flash_used_percent'] == 25
    assert 'Flash-носитель: занято 256 из 1024 MB (25%)' in first['note']
    assert first['program_rss_kb'] == 64000 + (20 + 40 + 14 + 7) * 1024
    assert second['program_rss_kb'] == 64000 + (20 + 40 + 14 + 7) * 1024
    assert third['temporary_xray_count'] == 2
    assert third['program_rss_kb'] == 64000 + (20 + 30 + 40 + 14 + 7) * 1024
    assert calls == {'ndmc': 1, 'dns': 1, 'core': 1, 'call': 1, 'cpu_stat': 3, 'flash': 3, 'proc': 2}
    runtime.invalidate(include_heavy=False)
    assert runtime._cache['payload'] is None
    assert runtime._ndmc_cache['payload'] is not None
    assert runtime._dns_cache['payload'] is not None
    assert runtime._core_proxy_cache['payload'] is not None
    assert runtime._related_process_cache['payload'] is not None
    runtime.invalidate()
    assert runtime._ndmc_cache['payload'] is None
    assert runtime._dns_cache['payload'] is None
    assert runtime._core_proxy_cache['payload'] is None
    assert runtime._related_process_cache['payload'] is None


def test_router_health_runtime_compact_snapshot_keeps_route_notes_cached():
    calls = {'dns': 0, 'core': 0, 'call': 0}
    original = {
        'read_proc_meminfo': router_health_runtime.read_proc_meminfo,
        'read_proc_text': router_health_runtime.read_proc_text,
        'read_cpu_stat': router_health_runtime.read_cpu_stat,
        'read_flash_storage': router_health_runtime.read_flash_storage,
        'process_rss_kb': router_health_runtime.process_rss_kb,
        'related_program_process_snapshot': router_health_runtime.related_program_process_snapshot,
        'read_dns_health': router_health_runtime.read_dns_health,
        'telegram_call_proxy_health': router_health_runtime.telegram_call_proxy_health,
        'xray_compat_runtime': router_health_runtime.xray_compat_runtime,
    }

    def fake_dns(**kwargs):
        calls['dns'] += 1
        return {
            'backend': 'ndnproxy',
            'listener_backend': 'ndnproxy',
            'dnsmasq_state': 'dead',
            'ipset_counts': {'unblockvless': 12, 'unblockvless2': 34},
            'ipset_updated_at': 1000,
            'ipset_refresh_age_seconds': 90,
            'ipset_refresh_status': 'success',
        }

    def fake_core_health():
        calls['core'] += 1
        return {'ok': True, 'xray_state': 'alive', 'ports': {10811: True, 10812: True}}

    def fake_call_health():
        calls['call'] += 1
        return {
            'ok': True,
            'enabled': True,
            'tproxy_enabled': True,
            'chain_ok': True,
            'services': ['Telegram', 'WhatsApp', 'Discord'],
            'protocols': ['vless'],
            'ports': {'vless': 11812},
            'port_states': {'11812': True},
        }

    now = [100.0]
    try:
        router_health_runtime.read_proc_meminfo = lambda: {'MemTotal': 512000, 'MemAvailable': 256000, 'MemFree': 128000}
        router_health_runtime.read_proc_text = lambda path, max_bytes=16384: '0.01 0.02 0.03 1/100 1\n'
        router_health_runtime.read_cpu_stat = lambda stat_path='/proc/stat': None
        router_health_runtime.read_flash_storage = lambda: {}
        router_health_runtime.process_rss_kb = lambda pid='self': 64000
        router_health_runtime.related_program_process_snapshot = lambda probe_running=False: {'xray_rss_kb': 20 * 1024}
        router_health_runtime.read_dns_health = fake_dns
        router_health_runtime.telegram_call_proxy_health = fake_call_health
        router_health_runtime.xray_compat_runtime = py_types.SimpleNamespace(
            core_proxy_health=fake_core_health,
            core_proxy_note=lambda health: 'Прокси: Xray работает на портах: 10811, 10812',
        )
        runtime = router_health_runtime.RouterHealthRuntime(
            cache_ttl=0,
            time_provider=lambda: now[0],
            core_proxy_cache_ttl=60,
            dns_cache_ttl=60,
            related_process_cache_ttl=45,
        )
        first = runtime.snapshot(lambda: {'running': False, 'total': 0}, compact=True)
        now[0] += 10
        second = runtime.snapshot(lambda: {'running': False, 'total': 0}, compact=True)
    finally:
        for name, value in original.items():
            setattr(router_health_runtime, name, value)

    assert 'DNS: ndnproxy' in first['dns_note']
    assert 'VLESS=12' in first['dns_note']
    assert 'VLESS2=34' in first['dns_note']
    assert first['core_proxy_note'] == 'Прокси: Xray работает на портах: 10811, 10812'
    assert first['telegram_call_note'] == 'Звонки через TPROXY работают для Telegram/WhatsApp/Discord на порте: Vless 11812'
    assert second['dns_note'] == first['dns_note']
    assert second['core_proxy_note'] == first['core_proxy_note']
    assert second['telegram_call_note'] == first['telegram_call_note']
    assert calls == {'dns': 1, 'core': 1, 'call': 1}


def test_router_health_runtime_default_ndmc_ttl_matches_ui_refresh_window():
    runtime = router_health_runtime.RouterHealthRuntime()
    assert runtime.cache_ttl == 5.0
    assert runtime.ndmc_cache_ttl == 5.0


def test_router_health_runtime_compact_snapshot_refreshes_ndmc_by_ttl_and_force():
    calls = {'ndmc': 0}
    original = {
        'read_proc_meminfo': router_health_runtime.read_proc_meminfo,
        'read_proc_text': router_health_runtime.read_proc_text,
        'read_cpu_stat': router_health_runtime.read_cpu_stat,
        'read_flash_storage': router_health_runtime.read_flash_storage,
        'process_rss_kb': router_health_runtime.process_rss_kb,
        'related_program_process_snapshot': router_health_runtime.related_program_process_snapshot,
        'read_ndmc_system_snapshot': router_health_runtime.read_ndmc_system_snapshot,
        'read_dns_health': router_health_runtime.read_dns_health,
        'telegram_call_proxy_health': router_health_runtime.telegram_call_proxy_health,
        'xray_compat_runtime': router_health_runtime.xray_compat_runtime,
    }
    ndmc_payloads = [
        {'memory_total': 512 * 1024, 'memory_used': 256 * 1024, 'cpuload': 1},
        {'memory_total': 512 * 1024, 'memory_used': 300 * 1024, 'cpuload': 5},
        {'memory_total': 512 * 1024, 'memory_used': 320 * 1024, 'cpuload': 3},
    ]

    def fake_ndmc():
        index = min(calls['ndmc'], len(ndmc_payloads) - 1)
        calls['ndmc'] += 1
        return dict(ndmc_payloads[index])

    now = [100.0]
    try:
        router_health_runtime.read_proc_meminfo = lambda: {'MemTotal': 512 * 1024, 'MemAvailable': 224 * 1024, 'MemFree': 128 * 1024}
        router_health_runtime.read_proc_text = lambda path, max_bytes=16384: '0.01 0.02 0.03 1/100 1\n'
        router_health_runtime.read_cpu_stat = lambda stat_path='/proc/stat': None
        router_health_runtime.read_flash_storage = lambda: {}
        router_health_runtime.process_rss_kb = lambda pid='self': 64 * 1024
        router_health_runtime.related_program_process_snapshot = lambda probe_running=False: {}
        router_health_runtime.read_ndmc_system_snapshot = fake_ndmc
        router_health_runtime.read_dns_health = lambda **kwargs: {}
        router_health_runtime.telegram_call_proxy_health = lambda: {}
        router_health_runtime.xray_compat_runtime = None
        runtime = router_health_runtime.RouterHealthRuntime(
            cache_ttl=0,
            time_provider=lambda: now[0],
            core_proxy_cache_ttl=60,
            dns_cache_ttl=60,
            ndmc_cache_ttl=30,
            related_process_cache_ttl=45,
        )
        first = runtime.snapshot(lambda: {'running': False, 'total': 0}, compact=True)
        now[0] += 10
        cached = runtime.snapshot(lambda: {'running': False, 'total': 0}, compact=True)
        now[0] += 21
        refreshed = runtime.snapshot(lambda: {'running': False, 'total': 0}, compact=True)
        now[0] += 1
        forced = runtime.snapshot(lambda: {'running': False, 'total': 0}, compact=True, force_refresh=True)
    finally:
        for name, value in original.items():
            setattr(router_health_runtime, name, value)

    assert calls['ndmc'] == 3
    assert first['memory_text'] == 'Память: доступно 224 MB из 512 MB'
    assert first['cpu_percent'] == 1
    assert first['cpu_source'] == 'keenetic'
    assert cached['used_kb'] == first['used_kb']
    assert cached['cpu_percent'] == 1
    assert refreshed['used_kb'] == 300 * 1024
    assert refreshed['cpu_percent'] == 5
    assert forced['used_kb'] == 320 * 1024
    assert forced['cpu_percent'] == 3


def test_router_health_runtime_smooths_short_cpu_spikes():
    original = {
        'read_proc_meminfo': router_health_runtime.read_proc_meminfo,
        'read_proc_text': router_health_runtime.read_proc_text,
        'read_cpu_stat': router_health_runtime.read_cpu_stat,
        'read_flash_storage': router_health_runtime.read_flash_storage,
        'process_rss_kb': router_health_runtime.process_rss_kb,
        'related_program_process_snapshot': router_health_runtime.related_program_process_snapshot,
        'read_ndmc_system_snapshot': router_health_runtime.read_ndmc_system_snapshot,
        'read_dns_health': router_health_runtime.read_dns_health,
        'telegram_call_proxy_health': router_health_runtime.telegram_call_proxy_health,
        'xray_compat_runtime': router_health_runtime.xray_compat_runtime,
    }
    cpu_stats = iter((
        (100, 0, 0, 900, 0),
        (150, 0, 50, 900, 0),
        (160, 0, 50, 990, 0),
    ))
    now = [100.0]
    try:
        router_health_runtime.read_proc_meminfo = lambda: {'MemTotal': 512000, 'MemAvailable': 256000, 'MemFree': 128000}
        router_health_runtime.read_proc_text = lambda path, max_bytes=16384: '0.01 0.02 0.03 1/100 1\n'
        router_health_runtime.read_cpu_stat = lambda stat_path='/proc/stat': next(cpu_stats)
        router_health_runtime.read_flash_storage = lambda: {}
        router_health_runtime.process_rss_kb = lambda pid='self': 64000
        router_health_runtime.related_program_process_snapshot = lambda probe_running=False: {}
        router_health_runtime.read_ndmc_system_snapshot = lambda: {}
        router_health_runtime.read_dns_health = lambda **kwargs: {}
        router_health_runtime.telegram_call_proxy_health = lambda: {}
        router_health_runtime.xray_compat_runtime = None
        runtime = router_health_runtime.RouterHealthRuntime(
            cache_ttl=0,
            time_provider=lambda: now[0],
            core_proxy_cache_ttl=60,
            dns_cache_ttl=60,
            ndmc_cache_ttl=60,
            cpu_smoothing_factor=0.35,
        )
        first = runtime.snapshot(lambda: {'running': False, 'total': 0})
        now[0] += 10
        second = runtime.snapshot(lambda: {'running': False, 'total': 0})
        now[0] += 10
        third = runtime.snapshot(lambda: {'running': False, 'total': 0})
    finally:
        for name, value in original.items():
            setattr(router_health_runtime, name, value)

    assert first['cpu_percent'] is None
    assert second['cpu_percent'] == 100.0
    assert 60.0 < third['cpu_percent'] < 70.0


def test_router_health_runtime_primes_cpu_baseline_without_page_render_sample():
    original = {
        'read_proc_meminfo': router_health_runtime.read_proc_meminfo,
        'read_proc_text': router_health_runtime.read_proc_text,
        'read_cpu_stat': router_health_runtime.read_cpu_stat,
        'read_flash_storage': router_health_runtime.read_flash_storage,
        'process_rss_kb': router_health_runtime.process_rss_kb,
        'related_program_process_snapshot': router_health_runtime.related_program_process_snapshot,
        'read_ndmc_system_snapshot': router_health_runtime.read_ndmc_system_snapshot,
        'read_dns_health': router_health_runtime.read_dns_health,
        'telegram_call_proxy_health': router_health_runtime.telegram_call_proxy_health,
        'xray_compat_runtime': router_health_runtime.xray_compat_runtime,
    }
    calls = {'cpu': 0}
    cpu_stats = iter((
        (100, 0, 0, 900, 0),
        (110, 0, 10, 980, 0),
        (120, 0, 20, 1060, 0),
    ))
    now = [100.0]

    def fake_cpu_stat(stat_path='/proc/stat'):
        calls['cpu'] += 1
        return next(cpu_stats)

    try:
        router_health_runtime.read_proc_meminfo = lambda: {'MemTotal': 512000, 'MemAvailable': 256000, 'MemFree': 128000}
        router_health_runtime.read_proc_text = lambda path, max_bytes=16384: '0.01 0.02 0.03 1/100 1\n'
        router_health_runtime.read_cpu_stat = fake_cpu_stat
        router_health_runtime.read_flash_storage = lambda: {}
        router_health_runtime.process_rss_kb = lambda pid='self': 64000
        router_health_runtime.related_program_process_snapshot = lambda probe_running=False: {}
        router_health_runtime.read_ndmc_system_snapshot = lambda: {}
        router_health_runtime.read_dns_health = lambda **kwargs: {}
        router_health_runtime.telegram_call_proxy_health = lambda: {}
        router_health_runtime.xray_compat_runtime = None
        runtime = router_health_runtime.RouterHealthRuntime(
            cache_ttl=30,
            time_provider=lambda: now[0],
            core_proxy_cache_ttl=60,
            dns_cache_ttl=60,
            ndmc_cache_ttl=60,
            cpu_smoothing_factor=1.0,
        )
        page_render = runtime.snapshot(lambda: {'running': False, 'total': 0}, compact=True, sample_cpu=False, prime_cpu=True)
        runtime.sample_cpu()
        now[0] += 5
        first_api = runtime.snapshot(lambda: {'running': False, 'total': 0}, compact=True, sample_cpu=False, force_refresh=True)
        runtime.sample_cpu()
        now[0] += 5
        second_api = runtime.snapshot(lambda: {'running': False, 'total': 0}, compact=True, sample_cpu=False, force_refresh=True)
    finally:
        for name, value in original.items():
            setattr(router_health_runtime, name, value)

    assert calls['cpu'] == 2
    assert page_render['cpu_percent'] is None
    assert first_api['cpu_percent'] is None
    assert second_api['cpu_percent'] == 20.0


def test_web_commands_runtime_dispatch():
    calls = []

    def run_script(action, owner, repo, progress_command=None):
        calls.append((action, owner, repo, progress_command))
        return 0, f'{action}:{owner}/{repo}:{progress_command}'

    assert web_commands_runtime.web_command_label('dns_on') == 'DNS Override ВКЛ'
    assert web_commands_runtime.web_command_label('custom') == 'custom'
    assert web_commands_runtime.WEB_UPDATE_COMMANDS == ('update', 'rollback_update')
    bot_source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    assert "start_delay = 1.0 if command == 'rollback_update' else 0.0" in bot_source
    assert 'time.sleep({start_delay!r}); ' in bot_source
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
        and inbound['streamSettings']['sockopt']['tproxy'] == 'redirect'
    ]
    assert transparent_inbounds
    assert all(inbound['settings']['network'] == 'tcp,udp' for inbound in transparent_inbounds)
    assert all(inbound['streamSettings']['sockopt']['tproxy'] == 'redirect' for inbound in transparent_inbounds)
    assert all(inbound['sniffing']['enabled'] is True for inbound in transparent_inbounds)
    assert all(inbound['sniffing']['destOverride'] == ['http', 'tls', 'quic'] for inbound in transparent_inbounds)
    assert all(inbound['sniffing']['routeOnly'] is False for inbound in transparent_inbounds)
    tproxy_inbounds = [
        inbound for inbound in core_config['inbounds']
        if inbound.get('protocol') == 'dokodemo-door'
        and inbound['streamSettings']['sockopt']['tproxy'] == 'tproxy'
    ]
    assert {inbound['tag'] for inbound in tproxy_inbounds} == {
        'in-shadowsocks-tproxy',
        'in-vless-tproxy',
        'in-trojan-tproxy',
    }
    assert {inbound['port'] for inbound in tproxy_inbounds} == {11802, 11812, 11829}
    assert all(inbound['settings']['network'] == 'udp' for inbound in tproxy_inbounds)
    assert all(inbound['sniffing']['enabled'] is True for inbound in tproxy_inbounds)
    assert all(inbound['sniffing']['destOverride'] == ['http', 'tls', 'quic'] for inbound in tproxy_inbounds)
    assert all(inbound['sniffing']['routeOnly'] is False for inbound in tproxy_inbounds)
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
        _hash_key('vmess-key'): {
            'tg_ok': True,
            'yt_ok': True,
            'custom': {'custom': True},
            'yt_quality': 'fast',
            'yt_score': 96,
            'yt_stream_tier': '4k',
            'yt_latency_ms': 410,
            'googlevideo_latency_ms': 520,
            'yt_throughput_mbps': 58.5,
            'ts': 2,
        },
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
    assert snapshot['vless']['core_services'] == ['telegram', 'youtube']
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
    vmess_row = scoped_snapshot['vmess']['rows'][0]
    assert vmess_row['key_id'] == _hash_key('vmess-key')[:12]
    assert vmess_row['yt_quality_label'] == 'Быстро'
    assert vmess_row['yt_score'] == 96
    assert '58.5 Мбит/с' in vmess_row['quality_summary']
    def icon_html(icon, alt, opacity=1.0, size=18):
        return f'<img data-icon="{icon}" alt="{alt}">'
    check_defs = [{'id': 'custom', 'label': 'Custom', 'url': 'https://example.com/path', 'icon': 'chat'}]
    assert key_pool_web.custom_check_url_text(check_defs[0]) == 'example.com/path'
    assert 'custom-check-item' in key_pool_web.web_custom_checks_html(check_defs, icon_html)
    assert 'service-preset-btn' in key_pool_web.web_custom_presets_html([], check_defs, icon_html)
    assert 'custom-service-ok' in key_pool_web.web_custom_check_badges({'custom': {'custom': True}}, check_defs, icon_html)
    assert key_pool_web.web_probe_state({'tg_ok': True}, 'tg_ok') == 'ok'
    assert key_pool_web.web_probe_state({'tg_ok': False}, 'tg_ok') == 'fail'
    assert key_pool_web.web_probe_state({'tg_ok': None}, 'tg_ok') == 'unknown'
    assert key_pool_web.web_probe_state({'tg_ok': 'unknown'}, 'tg_ok') == 'unknown'
    assert key_pool_web.web_probe_state({'yt_ok': False, 'yt_stability': 'unstable'}, 'yt_ok') == 'warn'
    cache_key = probe_cache.hash_key('old-key')
    cache = {cache_key: {'schema': probe_cache.KEY_PROBE_CACHE_SCHEMA_VERSION, 'tg_ok': True, 'tg_latency_ms': 825, 'ts': 1}}
    changed = probe_cache.update_key_probe_cache_entry(cache, 'vless', 'old-key', tg_ok='unknown', now=2)
    assert changed is True
    assert cache[cache_key]['tg_ok'] is None
    assert 'tg_latency_ms' not in cache[cache_key]
    warn_summary = key_pool_web.pool_status_summary(
        {'vless2': 'warn-key'},
        {'vless2': ['warn-key']},
        {_hash_key('warn-key'): {'yt_ok': False, 'yt_stability': 'unstable', 'ts': 5}},
        [],
        _hash_key,
    )
    assert warn_summary['services'][1] == {'label': 'YouTube', 'count': 1}
    assert warn_summary['any_service_count'] == 1
    assert key_pool_web.web_custom_probe_states({'custom': {'custom': None}}, checks)['custom'] == 'unknown'
    scoped_checks = [
        {'id': 'discord', 'label': 'Discord'},
        {'id': 'claude', 'label': 'Claude'},
        {'id': 'chatgpt', 'label': 'ChatGPT'},
        {'id': 'manual', 'label': 'Manual'},
    ]
    route_states = {
        'discord': {'complete_protocols': ['vless'], 'partial_protocols': []},
        'claude': {'complete_protocols': [], 'partial_protocols': ['vless2']},
        'chatgpt': {'complete_protocols': ['vless'], 'partial_protocols': ['vless2']},
    }
    assert [
        check['id']
        for check in key_pool_web.protocol_custom_checks(scoped_checks, route_states, 'vless')
    ] == ['discord', 'chatgpt', 'manual']
    assert [
        check['id']
        for check in key_pool_web.protocol_custom_checks(scoped_checks, route_states, 'vless2')
    ] == ['manual']
    assert [
        check['id']
        for check in key_pool_web.protocol_custom_checks(scoped_checks, route_states, 'vmess')
    ] == ['manual']
    scoped_service_snapshot = key_pool_web.web_pool_snapshot(
        {'vmess': 'vmess-key'},
        {'vmess': ['vmess-key']},
        {
            _hash_key('vmess-key'): {
                'tg_ok': True,
                'yt_ok': True,
                'custom': {'discord': True, 'claude': True, 'manual': True},
                'ts': 4,
            },
        },
        scoped_checks,
        include_keys=False,
        hash_key=_hash_key,
        display_name=lambda value: value,
        probe_state=lambda probe, field: 'ok' if probe.get(field) else 'fail' if field in probe else 'unknown',
        probe_checked_at=lambda probe: str(probe.get('ts', '')),
        protocols=['vmess'],
        route_states=route_states,
    )
    scoped_row = scoped_service_snapshot['vmess']['rows'][0]
    assert scoped_row['tg'] == 'ok'
    assert scoped_row['yt'] == 'ok'
    assert scoped_row['custom'] == {'manual': 'ok'}
    assert [
        check['id']
        for check in scoped_service_snapshot['vmess']['custom_checks']
    ] == ['manual']
    core_route_states = {
        'telegram': {'complete_protocols': ['vless'], 'partial_protocols': []},
        'youtube': {'complete_protocols': ['vless2'], 'partial_protocols': ['vless']},
    }
    assert key_pool_web.core_service_applicability(core_route_states, 'vless') == {
        'telegram': True,
        'youtube': False,
    }
    scoped_core_snapshot = key_pool_web.web_pool_snapshot(
        {'vless2': 'yt-key', 'vless': 'tg-key'},
        {'vless2': ['yt-key'], 'vless': ['tg-key']},
        {
            _hash_key('yt-key'): {'tg_ok': True, 'yt_ok': False, 'yt_stability': 'unstable', 'ts': 8},
            _hash_key('tg-key'): {'tg_ok': True, 'yt_ok': False, 'yt_stability': 'fail', 'yt_score': 91, 'ts': 9},
        },
        [],
        include_keys=False,
        hash_key=_hash_key,
        display_name=lambda value: value,
        probe_state=key_pool_web.web_probe_state,
        probe_checked_at=lambda probe: str(probe.get('ts', '')),
        protocols=['vless', 'vless2'],
        route_states=core_route_states,
    )
    assert scoped_core_snapshot['vless']['rows'][0]['tg'] == 'ok'
    assert scoped_core_snapshot['vless']['rows'][0]['yt'] == 'fail'
    assert scoped_core_snapshot['vless']['rows'][0]['yt_score'] == 0
    assert scoped_core_snapshot['vless']['core_services'] == ['telegram']
    assert scoped_core_snapshot['vless2']['core_services'] == ['youtube']
    assert scoped_core_snapshot['vless2']['rows'][0]['tg'] == 'ok'
    assert scoped_core_snapshot['vless2']['rows'][0]['yt'] == 'warn'
    scoped_summary = key_pool_web.pool_status_summary(
        {'vless2': 'yt-key', 'vless': 'tg-key'},
        {'vless2': ['yt-key'], 'vless': ['tg-key']},
        {
            _hash_key('yt-key'): {'tg_ok': True, 'yt_ok': False, 'yt_stability': 'unstable', 'ts': 8},
            _hash_key('tg-key'): {'tg_ok': True, 'yt_ok': False, 'yt_stability': 'fail', 'ts': 9},
        },
        [],
        _hash_key,
        route_states=core_route_states,
    )
    assert scoped_summary['services'][:2] == [
        {'label': 'Telegram', 'count': 2},
        {'label': 'YouTube', 'count': 1},
    ]
    assert scoped_summary['checked_pool_count'] == 2
    assert scoped_summary['all_services_count'] == 1


def test_web_pool_snapshot_worker_payload_is_safe_and_complete():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        bot_dir = temp_path / 'bot'
        xray_dir = temp_path / 'xray'
        bot_dir.mkdir()
        xray_dir.mkdir()
        proxy_scheme = 'vless'
        active_key = f'{proxy_scheme}://00000000-0000-0000-0000-000000000000@example.test:443#active-vless'
        backup_key = f'{proxy_scheme}://00000000-0000-0000-0000-000000000001@backup.test:443#backup-vless'
        key_pools_path = bot_dir / 'key_pools.json'
        key_probe_path = bot_dir / 'key_probe_cache.json'
        custom_checks_path = bot_dir / 'custom_checks.json'
        (xray_dir / 'vless.key').write_text(active_key, encoding='utf-8')
        (xray_dir / 'vless2.key').write_text('', encoding='utf-8')
        (xray_dir / 'vmess.key').write_text('', encoding='utf-8')
        key_pools_path.write_text(json.dumps({'vless': [active_key, backup_key]}, ensure_ascii=False), encoding='utf-8')
        key_probe_path.write_text(json.dumps({
            probe_cache.hash_key(active_key): {
                'schema': probe_cache.KEY_PROBE_CACHE_SCHEMA_VERSION,
                'tg_ok': True,
                'yt_ok': False,
                'yt_stability': 'fail',
                'ts': 123,
            },
            probe_cache.hash_key(backup_key): {
                'schema': probe_cache.KEY_PROBE_CACHE_SCHEMA_VERSION,
                'tg_ok': False,
                'yt_ok': True,
                'yt_stability': 'stable',
                'ts': 124,
            },
        }, ensure_ascii=False), encoding='utf-8')
        custom_checks_path.write_text('[]', encoding='utf-8')

        old_worker_values = {
            'KEY_POOLS_PATH': web_pool_snapshot_worker.KEY_POOLS_PATH,
            'CORE_PROXY_CONFIG_DIR': web_pool_snapshot_worker.CORE_PROXY_CONFIG_DIR,
            'VMESS_KEY_PATH': web_pool_snapshot_worker.VMESS_KEY_PATH,
            'VLESS_KEY_PATH': web_pool_snapshot_worker.VLESS_KEY_PATH,
            'VLESS2_KEY_PATH': web_pool_snapshot_worker.VLESS2_KEY_PATH,
            'XRAY_CONFIG_DIR': web_pool_snapshot_worker.XRAY_CONFIG_DIR,
            'V2RAY_CONFIG_DIR': web_pool_snapshot_worker.V2RAY_CONFIG_DIR,
        }
        old_probe_path = probe_cache.KEY_PROBE_CACHE_PATH
        old_custom_path = custom_checks_store.CUSTOM_CHECKS_PATH
        try:
            web_pool_snapshot_worker.KEY_POOLS_PATH = str(key_pools_path)
            web_pool_snapshot_worker.CORE_PROXY_CONFIG_DIR = str(xray_dir)
            web_pool_snapshot_worker.VMESS_KEY_PATH = str(xray_dir / 'vmess.key')
            web_pool_snapshot_worker.VLESS_KEY_PATH = str(xray_dir / 'vless.key')
            web_pool_snapshot_worker.VLESS2_KEY_PATH = str(xray_dir / 'vless2.key')
            web_pool_snapshot_worker.XRAY_CONFIG_DIR = str(xray_dir)
            web_pool_snapshot_worker.V2RAY_CONFIG_DIR = str(temp_path / 'v2ray')
            probe_cache.KEY_PROBE_CACHE_PATH = str(key_probe_path)
            custom_checks_store.CUSTOM_CHECKS_PATH = str(custom_checks_path)
            payload = web_pool_snapshot_worker.build_payload(
                protocols=['vless'],
                include_summary=True,
                include_custom_checks=True,
            )
            summary_payload = web_pool_snapshot_worker.build_payload(
                protocols=['vless'],
                include_summary=True,
                include_custom_checks=False,
                include_pools=False,
            )
        finally:
            for name, value in old_worker_values.items():
                setattr(web_pool_snapshot_worker, name, value)
            probe_cache.KEY_PROBE_CACHE_PATH = old_probe_path
            custom_checks_store.CUSTOM_CHECKS_PATH = old_custom_path

    assert list(payload['pools']) == ['vless']
    assert payload['pools']['vless']['count'] == 2
    assert payload['pools']['vless']['rows'][0]['active'] is True
    assert payload['pools']['vless']['rows'][0]['display_name'] == 'active-vless'
    assert payload['pool_summary']['pool_total_count'] == 2
    assert payload['pool_summary']['checked_pool_count'] == 2
    assert payload['custom_checks'] == []
    serialized = json.dumps(payload, ensure_ascii=False)
    assert 'vless://' not in serialized
    scoped_summary = payload['pool_summary']
    assert '\u0412\u0441\u0435 \u0441\u0435\u0440\u0432\u0438\u0441\u044b' not in scoped_summary['note']
    assert '\u0425\u043e\u0442\u044f \u0431\u044b \u043e\u0434\u0438\u043d' not in scoped_summary['note']
    assert summary_payload['pools'] == {}
    assert summary_payload['pool_summary']['pool_total_count'] == 2
    assert summary_payload['pool_summary']['checked_pool_count'] == 2
    assert summary_payload['custom_checks'] is None
    assert key_pool_web.web_probe_checked_at({'ts': 0}) == ''
    assert key_pool_web.web_probe_quality_label({'yt_quality': 'stable', 'yt_latency_ms': 800}) == ''
    history_html = key_pool_web.web_event_history_html([
        {
            'ts': index + 1,
            'level': 'info',
            'action': f'test_{index}',
            'protocol': 'vless',
            'service': 'telegram',
            'source': 'watchdog',
            'message': 'ok',
            'details': {'active_connections': index},
        }
        for index in range(55)
    ])
    assert '<strong>История событий</strong>' not in history_html
    assert '<h3>История событий</h3>' not in history_html
    assert history_html.count('event-history-item') == 50
    assert 'test_49' in history_html
    assert 'test_50' not in history_html
    assert 'watchdog' in history_html
    assert 'active_connections=0' in history_html
    assert 'active_connections=49' in history_html


def test_web_service_routes_worker_payload_contains_route_tools():
    payload = web_service_routes_worker.build_payload()
    html_text = payload.get('route_tools_html') or ''

    assert 'service-route-tools' in html_text
    assert 'service-route-trigger' in html_text
    assert 'service-route-telegram-icon' in html_text
    assert 'service-route-youtube-icon' in html_text
    assert '/service_profile_apply' in html_text
    assert '/route_intersections_resolve' in html_text or 'route-intersection-ok' in html_text


def test_key_pool_subscription_helpers():
    vless_key = 'vless://uuid@example.com:443?security=tls#sample'
    vmess_key = 'vmess://sample'
    raw = '\n'.join([
        SS_KEY,
        vless_key,
        TROJAN_KEY,
    ])
    classified = key_pool_store.classify_subscription_keys(raw)
    assert classified['shadowsocks'] == [SS_KEY]
    assert classified['vless'] == [vless_key]
    assert classified['trojan'] == [TROJAN_KEY]

    pools, added = key_pool_store.add_subscription_keys_to_pool({'vless2': []}, 'vless2', classified)
    assert added == [vless_key]
    assert pools['vless2'] == added
    mixed_pools, added_by_proto = key_pool_store.add_keys_to_pools_by_protocol(
        {'vless2': []},
        'vless2',
        '\n'.join([vless_key, 'not-a-key-label', vmess_key, TROJAN_KEY, SS_KEY]),
    )
    assert added_by_proto == {
        'shadowsocks': [SS_KEY],
        'vmess': [vmess_key],
        'vless2': [vless_key],
        'trojan': [TROJAN_KEY],
    }
    assert mixed_pools['vless2'] == [vless_key]
    assert mixed_pools['vmess'] == [vmess_key]
    assert mixed_pools['trojan'] == [TROJAN_KEY]
    assert mixed_pools['shadowsocks'] == [SS_KEY]
    vless1_pools, vless1_added_by_proto = key_pool_store.add_keys_to_pools_by_protocol(
        {'vless': [], 'vless2': []},
        'vless',
        vless_key,
    )
    assert vless1_added_by_proto == {'vless': [vless_key]}
    assert vless1_pools['vless'] == [vless_key]
    assert vless1_pools['vless2'] == []
    repaired, moved = key_pool_store.repair_key_pool_protocols(
        {'vless2': [vless_key, vmess_key, TROJAN_KEY, SS_KEY]}
    )
    assert repaired['vless2'] == [vless_key]
    assert repaired['vmess'] == [vmess_key]
    assert repaired['trojan'] == [TROJAN_KEY]
    assert repaired['shadowsocks'] == [SS_KEY]
    assert moved == {'vless2': {'shadowsocks': 1, 'vmess': 1, 'trojan': 1}}
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
    duplicate_filtered_candidates = key_pool_store.failover_candidates(
        {'vless': ['active', 'other-active', 'next'], 'vless2': ['other-active']},
        'vless',
        'active',
        protocols=('vless',),
        exclude_keys={'other-active'},
    )
    assert duplicate_filtered_candidates == [('vless', 'next')]
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
    assert scored_candidates[:4] == [('vless', 'good'), ('vless', 'unknown'), ('vmess', 'vmess-key'), ('vless', 'bad')]
    recent_failure_filtered_candidates = key_pool_store.failover_candidates(
        {'vless': ['active', 'fresh-bad', 'old-bad', 'unknown']},
        'vless',
        'active',
        protocols=('vless',),
        key_probe_cache={
            _hash_key('fresh-bad'): {'tg_ok': False, 'ts': 900},
            _hash_key('old-bad'): {'tg_ok': False, 'ts': 100},
        },
        hash_key=_hash_key,
        recent_failure_backoff_seconds=300,
        now=1000,
    )
    assert recent_failure_filtered_candidates == [('vless', 'unknown'), ('vless', 'old-bad')]
    failed_skipped_candidates = key_pool_store.failover_candidates(
        {'vless': ['active', 'bad', 'unknown']},
        'vless',
        'active',
        protocols=('vless',),
        key_probe_cache={
            _hash_key('bad'): {'tg_ok': False, 'ts': 100},
        },
        hash_key=_hash_key,
        skip_failed=True,
        now=1000,
    )
    assert failed_skipped_candidates == [('vless', 'unknown')]
    youtube_scored_candidates = key_pool_store.failover_candidates(
        {'vless2': ['active', 'slow', 'fast', 'unchecked']},
        'vless2',
        'active',
        protocols=('vless2',),
        key_probe_cache={
            _hash_key('slow'): {'yt_ok': True, 'yt_score': 62, 'ts': 20},
            _hash_key('fast'): {'yt_ok': True, 'yt_score': 94, 'ts': 10},
        },
        hash_key=_hash_key,
        service='youtube',
    )
    assert youtube_scored_candidates[:3] == [('vless2', 'fast'), ('vless2', 'slow'), ('vless2', 'unchecked')]
    youtube_stable_candidates = key_pool_store.failover_candidates(
        {'vless2': ['active', 'unstable', 'stable']},
        'vless2',
        'active',
        protocols=('vless2',),
        key_probe_cache={
            _hash_key('unstable'): {'yt_ok': True, 'yt_score': 95, 'yt_stability': 'unstable', 'yt_error_rate': 0.125, 'ts': 30},
            _hash_key('stable'): {'yt_ok': True, 'yt_score': 80, 'yt_stability': 'stable', 'yt_error_rate': 0.0, 'ts': 20},
        },
        hash_key=_hash_key,
        service='youtube',
    )
    assert youtube_stable_candidates[:2] == [('vless2', 'stable'), ('vless2', 'unstable')]
    bot_source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    assert 'finally:\n            session.close()' in bot_source


def test_key_pool_import_routes_selected_protocol_and_vless_context():
    vless_key = 'vless://uuid@example.com:443?security=tls#sample'
    vmess_key = 'vmess://sample'
    cases = (
        ('shadowsocks', SS_KEY, 'shadowsocks'),
        ('vmess', vmess_key, 'vmess'),
        ('vless', vless_key, 'vless'),
        ('vless2', vless_key, 'vless2'),
        ('trojan', TROJAN_KEY, 'trojan'),
    )
    for selected_proto, selected_key, target_proto in cases:
        pools, added_by_proto = key_pool_store.add_keys_to_pools_by_protocol({}, selected_proto, selected_key)
        assert added_by_proto == {target_proto: [selected_key]}
        assert pools[target_proto] == [selected_key]

    for selected_proto in ('shadowsocks', 'vmess', 'trojan'):
        pools, added_by_proto = key_pool_store.add_keys_to_pools_by_protocol({}, selected_proto, vless_key)
        assert added_by_proto == {'vless': [vless_key]}
        assert pools['vless'] == [vless_key]
        assert pools[selected_proto] == []


def test_pool_import_hint_is_protocol_specific_in_both_renderers():
    protocols = (
        ('shadowsocks', 'Shadowsocks', 'ss://sample'),
        ('vmess', 'Vmess', 'vmess://...'),
        ('vless', 'Vless 1', 'vless://...'),
        ('vless2', 'Vless 2', 'vless://...'),
        ('trojan', 'Trojan', 'trojan://...'),
    )
    for key_name, title, placeholder in protocols:
        hint = web_form_blocks.pool_import_hint(title)
        assert hint == (
            'Вставьте один ключ, список ключей или ссылку на подписку. '
            f'Ключи {title} будут добавлены в этот пул, а ключи остальных протоколов — в соответствующие им пулы.'
        )
        assert 'Vless-ключи' not in hint
        light_panel = web_form_blocks._light_protocol_panel_html(
            key_name=key_name,
            title=title,
            rows=5,
            placeholder=placeholder,
            current_key_value='',
            status_info={'tone': 'empty', 'label': '', 'details': ''},
            active_status_icons='',
        )
        full_panel = web_pool_form_blocks.render_protocol_panel(
            key_name=key_name,
            title=title,
            rows=5,
            placeholder=placeholder,
            current_key_value='',
            status_info={'tone': 'empty', 'label': '', 'details': ''},
            active_status_icons='',
            pool_items_html='',
            pool_table_class='pool-table',
            pool_custom_col_width=32,
            pool_mobile_custom_col_width=28,
            custom_header_icons='',
            custom_presets_html='',
            custom_checks_html='',
            telegram_icon_html=lambda opacity=1.0: '',
            youtube_icon_html=lambda opacity=1.0: '',
        )
        assert hint in light_panel
        assert hint in full_panel
    assert 'загрузите подписку' in web_pool_form_blocks.POOL_EMPTY_ROW_HTML
    assert 'subscription' not in web_pool_form_blocks.POOL_EMPTY_ROW_HTML


def test_subscription_hwid_request_helpers():
    assert subscription_runtime.DEFAULT_SUBSCRIPTION_USER_AGENT == 'v2rayN/6.45'
    url, headers = subscription_runtime.apply_hwid_to_subscription_request(
        'https://sub.example.test/list?token=abc&hwid=old',
        'KN-12345',
    )
    assert url == 'https://sub.example.test/list?token=abc&hwid=KN-12345'
    assert headers == {
        'X-HWID': 'KN-12345',
        'X-Router-HWID': 'KN-12345',
        'X-Device-ID': 'KN-12345',
    }
    text = 'model: Keenetic\nserial number: ABCD123456\n'
    assert subscription_runtime.extract_router_hwid(text) == 'ABCD123456'
    text = 'model: Giga (KN-1012)\nhw_id: ABCD-1234\n'
    assert subscription_runtime.extract_router_hwid(text) == 'ABCD-1234'


def test_subscription_pool_sync_preserves_manual_keys():
    old_key = 'vless://old@example.com:443#old'
    new_key = 'vless://new@example.com:443#new'
    manual_key = 'vless://manual@example.com:443#manual'
    pools, added, removed, managed = subscription_runtime.sync_subscription_keys_to_pool(
        {'vless2': [manual_key, old_key]},
        'vless2',
        {'vless': [new_key]},
        previous_managed_keys=[old_key],
    )
    assert added == [new_key]
    assert removed == [old_key]
    assert managed == [new_key]
    assert pools['vless2'] == [manual_key, new_key]


def test_subscription_pool_sync_preserves_active_managed_key():
    active_key = 'vless://active@example.com:443#active'
    stale_key = 'vless://stale@example.com:443#stale'
    new_key = 'vless://new@example.com:443#new'
    pools, added, removed, managed = subscription_runtime.sync_subscription_keys_to_pool(
        {'vless2': [active_key, stale_key]},
        'vless2',
        {'vless': [new_key]},
        previous_managed_keys=[active_key, stale_key],
        preserve_keys=[active_key],
    )
    assert added == [new_key]
    assert removed == [stale_key]
    assert managed == [new_key, active_key]
    assert pools['vless2'] == [active_key, new_key]


def test_youtube_healthcheck_detects_first_load_instability():
    calls = []

    def check_http(_proxy_url, *, url, connect_timeout, read_timeout):
        calls.append((url, connect_timeout, read_timeout))
        if url == youtube_healthcheck.YOUTUBE_GOOGLEVIDEO_URL:
            return False, 'TLS connect error: unexpected EOF while reading'
        return True, 'ok'

    metrics = {}
    ok, message = youtube_healthcheck.check_youtube_through_proxy(
        check_http,
        'socks5h://127.0.0.1:10813',
        http_timeouts=(1, 2),
        metrics=metrics,
    )
    assert ok is False
    assert 'Required YouTube endpoint' in message
    assert metrics['yt_home_ok'] is True
    assert metrics['yt_bootstrap_ok'] is True
    assert metrics['googlevideo_ok'] is False
    assert metrics['yt_stability'] == 'fail'
    assert metrics['yt_error_rate'] > 0
    assert 'unexpected EOF' in metrics['yt_last_error']


def test_youtube_healthcheck_requires_watch_page():
    def check_http(_proxy_url, *, url, connect_timeout, read_timeout):
        if url == youtube_healthcheck.YOUTUBE_WATCH_URL:
            return False, 'TLS connect error: unexpected EOF while reading'
        return True, 'ok'

    metrics = {}
    ok, message = youtube_healthcheck.check_youtube_through_proxy(
        check_http,
        'socks5h://127.0.0.1:10813',
        http_timeouts=(1, 2),
        metrics=metrics,
    )

    assert ok is False
    assert 'Required YouTube endpoint did not respond' in message
    assert metrics['yt_home_ok'] is True
    assert metrics['yt_watch_ok'] is False
    assert metrics['yt_stability'] == 'fail'


def test_youtube_healthcheck_retries_transient_watch_page():
    calls = []

    def check_http(_proxy_url, *, url, connect_timeout, read_timeout):
        calls.append((url, connect_timeout, read_timeout))
        if url == youtube_healthcheck.YOUTUBE_WATCH_URL and len([item for item in calls if item[0] == url]) == 1:
            return False, 'TLS connect error: unexpected EOF while reading'
        return True, 'ok'

    metrics = {}
    ok, message = youtube_healthcheck.check_youtube_through_proxy(
        check_http,
        'socks5h://127.0.0.1:10813',
        http_timeouts=(1, 2),
        http_retry_timeouts=(3, 4),
        retry_delay_seconds=0,
        metrics=metrics,
    )

    assert ok is True
    assert 'confirmed' in message
    assert metrics['yt_watch_ok'] is True
    assert metrics['yt_stability'] == 'stable'
    assert calls.count((youtube_healthcheck.YOUTUBE_WATCH_URL, 3, 4)) == 2


def test_youtube_healthcheck_tolerates_transient_primary_generate_204():
    def check_http(_proxy_url, *, url, connect_timeout, read_timeout):
        if url == youtube_healthcheck.YOUTUBE_PRIMARY_URL:
            return False, 'TLS connect error: unexpected EOF while reading'
        return True, 'ok'

    metrics = {}
    ok, message = youtube_healthcheck.check_youtube_through_proxy(
        check_http,
        'socks5h://127.0.0.1:10811',
        http_timeouts=(1, 2),
        metrics=metrics,
    )

    assert ok is True
    assert 'soft diagnostic issue' in message
    assert metrics['yt_home_ok'] is True
    assert metrics['yt_watch_ok'] is True
    assert metrics['googlevideo_ok'] is True
    assert metrics['yt_stability'] == 'stable'
    assert metrics['yt_error_rate'] > 0


def test_youtube_healthcheck_rejects_http_client_error_status():
    def check_http(_proxy_url, *, url, connect_timeout, read_timeout):
        if url == youtube_healthcheck.YOUTUBE_HOME_URL:
            return True, 'Веб-доступ через ключ подтверждён (HTTP 451).'
        return True, 'ok'

    metrics = {}
    ok, message = youtube_healthcheck.check_youtube_through_proxy(
        check_http,
        'socks5h://127.0.0.1:10811',
        http_timeouts=(1, 2),
        profile='quick',
        metrics=metrics,
    )

    assert ok is False
    assert 'Required YouTube endpoint' in message
    assert metrics['yt_home_ok'] is False
    assert metrics['googlevideo_ok'] is True
    assert metrics['yt_stability'] == 'fail'


def test_youtube_healthcheck_tolerates_single_quick_home_timeout():
    def check_http(_proxy_url, *, url, connect_timeout, read_timeout):
        if url == youtube_healthcheck.YOUTUBE_HOME_URL:
            return False, 'Удалённый сервер не ответил вовремя через этот ключ.'
        return True, 'ok'

    metrics = {}
    ok, message = youtube_healthcheck.check_youtube_through_proxy(
        check_http,
        'socks5h://127.0.0.1:10811',
        http_timeouts=(1, 2),
        profile='quick',
        metrics=metrics,
    )

    assert ok is True
    assert 'soft diagnostic issue' in message
    assert metrics['yt_home_ok'] is False
    assert metrics['googlevideo_ok'] is True
    assert metrics['yt_stability'] == 'stable'
    assert metrics['yt_error_rate'] > 0


def test_youtube_healthcheck_tolerates_single_quick_googlevideo_timeout():
    def check_http(_proxy_url, *, url, connect_timeout, read_timeout):
        if url == youtube_healthcheck.YOUTUBE_GOOGLEVIDEO_URL:
            return False, 'TLS connect error: unexpected EOF while reading'
        return True, 'ok'

    metrics = {}
    ok, message = youtube_healthcheck.check_youtube_through_proxy(
        check_http,
        'socks5h://127.0.0.1:10811',
        http_timeouts=(1, 2),
        profile='quick',
        metrics=metrics,
    )

    assert ok is True
    assert 'soft diagnostic issue' in message
    assert metrics['yt_home_ok'] is True
    assert metrics['googlevideo_ok'] is False
    assert metrics['yt_stability'] == 'stable'
    assert metrics['yt_error_rate'] > 0


def test_youtube_healthcheck_tolerates_single_transient_bootstrap_failure():
    def check_http(_proxy_url, *, url, connect_timeout, read_timeout):
        if url == 'https://youtubei.googleapis.com/generate_204':
            return False, 'TLS connect error: unexpected EOF while reading'
        return True, 'ok'

    metrics = {}
    ok, message = youtube_healthcheck.check_youtube_through_proxy(
        check_http,
        'socks5h://127.0.0.1:10811',
        http_timeouts=(1, 2),
        metrics=metrics,
    )

    assert ok is True
    assert 'soft diagnostic issue' in message
    assert metrics['yt_home_ok'] is True
    assert metrics['yt_watch_ok'] is True
    assert metrics['googlevideo_ok'] is True
    assert metrics['yt_bootstrap_ok'] is False
    assert metrics['yt_stability'] == 'stable'


def test_youtube_healthcheck_tolerates_multiple_transient_bootstrap_failures():
    transient_urls = {
        'https://youtubei.googleapis.com/generate_204',
        'https://youtubei-att.googleapis.com/',
        'https://i.ytimg.com/generate_204',
    }

    def check_http(_proxy_url, *, url, connect_timeout, read_timeout):
        if url in transient_urls:
            return False, 'TLS connect error: unexpected EOF while reading'
        return True, 'ok'

    metrics = {}
    ok, message = youtube_healthcheck.check_youtube_through_proxy(
        check_http,
        'socks5h://127.0.0.1:10813',
        http_timeouts=(1, 2),
        metrics=metrics,
    )

    assert ok is True
    assert 'soft diagnostic issue' in message
    assert metrics['yt_home_ok'] is True
    assert metrics['yt_watch_ok'] is True
    assert metrics['googlevideo_ok'] is True
    assert metrics['yt_bootstrap_ok'] is False
    assert metrics['yt_stability'] == 'stable'
    assert metrics['yt_error_rate'] >= 0.3


def test_youtube_healthcheck_rejects_failed_googlevideo_media_endpoint():
    calls_by_url = {}

    def check_http(_proxy_url, *, url, connect_timeout, read_timeout):
        calls_by_url[url] = calls_by_url.get(url, 0) + 1
        if url == youtube_healthcheck.YOUTUBE_GOOGLEVIDEO_URL and calls_by_url[url] <= 2:
            return False, 'TLS connect error: unexpected EOF while reading'
        return True, 'ok'

    metrics = {}
    ok, message = youtube_healthcheck.check_youtube_through_proxy(
        check_http,
        'socks5h://127.0.0.1:10813',
        http_timeouts=(1, 2),
        metrics=metrics,
    )

    assert ok is False
    assert 'redirector.googlevideo.com' in message
    assert metrics['googlevideo_ok'] is False
    assert metrics['yt_stability'] == 'fail'
    assert metrics['yt_error_rate'] > 0


def test_telegram_call_learning_helpers():
    line = (
        'ipv4 2 udp 17 29 src=192.168.1.23 dst=149.154.167.91 sport=53122 dport=3478 '
        'packets=3 bytes=640 src=149.154.167.91 dst=192.168.1.23 sport=3478 dport=53122 '
        'packets=4 bytes=880 [ASSURED] mark=0 use=2'
    )
    flow = telegram_call_learning.parse_udp_flow(line, device_ip='192.168.1.23')
    assert flow['dst'] == '149.154.167.91'
    assert flow['dport'] == '3478'
    assert flow['packets'] == 7
    assert flow['bytes'] == 1520
    reverse_nat_line = (
        'ipv4 2 udp 17 135 src=197.89.55.30 dst=10.107.57.20 sport=49001 dport=43490 '
        'packets=15 bytes=1500 src=192.168.1.23 dst=197.89.55.30 sport=43490 dport=49001 '
        'packets=16 bytes=2200 [ASSURED] mark=0 use=2'
    )
    reverse_flow = telegram_call_learning.parse_udp_flow(reverse_nat_line, device_ip='192.168.1.23')
    assert reverse_flow['src'] == '192.168.1.23'
    assert reverse_flow['dst'] == '197.89.55.30'
    assert reverse_flow['dport'] == '49001'
    assert telegram_call_learning.parse_udp_flow(line, device_ip='192.168.1.24') is None
    assert telegram_call_learning.parse_udp_flow(line.replace('dport=3478', 'dport=53'), device_ip='192.168.1.23') is None
    assert telegram_call_learning.parse_udp_flow(line.replace('149.154.167.91', '192.168.1.200'), device_ip='192.168.1.23') is None
    grep_calls = []
    original_conntrack_runner = telegram_call_learning.subprocess.run

    def grep_runner(args, **kwargs):
        grep_calls.append((args, kwargs))
        return py_types.SimpleNamespace(returncode=0, stdout=line + '\n')

    try:
        telegram_call_learning.subprocess.run = grep_runner
        filtered_lines = list(
            telegram_call_learning._iter_conntrack_lines('/proc/net/nf_conntrack', source_tokens=('src=192.168.1.23',))
        )
    finally:
        telegram_call_learning.subprocess.run = original_conntrack_runner
    assert filtered_lines == [line + '\n']
    assert grep_calls[0][0] == ['grep', '-F', '-e', 'src=192.168.1.23', '/proc/net/nf_conntrack']
    signal_line = (
        'ipv4 2 tcp 6 1199 ESTABLISHED src=192.168.1.23 dst=149.154.167.41 '
        'sport=56440 dport=443 packets=30 bytes=6000 src=192.168.1.1 dst=192.168.1.23 '
        'sport=10812 dport=56440 packets=90 bytes=120000 [ASSURED] mark=0 use=2'
    )
    cluster_one = (
        'ipv4 2 udp 17 135 src=192.168.1.23 dst=197.89.55.30 sport=43490 dport=49001 '
        'packets=7 bytes=1700 src=197.89.55.30 dst=10.107.57.20 sport=49001 dport=43490 '
        'packets=8 bytes=1300 [ASSURED] mark=0 use=2'
    )
    cluster_two = (
        'ipv4 2 udp 17 135 src=91.132.107.120 dst=10.107.57.20 sport=5392 dport=43490 '
        'packets=6 bytes=1200 src=192.168.1.23 dst=91.132.107.120 sport=43490 dport=5392 '
        'packets=6 bytes=1400 [ASSURED] mark=0 use=2'
    )
    cluster_signal = (
        'ipv4 2 udp 17 135 src=192.168.1.23 dst=149.154.167.92 sport=43490 dport=54545 '
        'packets=5 bytes=1400 src=149.154.167.92 dst=10.107.57.20 sport=54545 dport=43490 '
        'packets=6 bytes=1800 [ASSURED] mark=0 use=2'
    )
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as tmp:
        tmp.write(line + '\n')
        tmp.write(line.replace('dport=3478', 'dport=53') + '\n')
        tmp.write(line.replace('149.154.167.91', '8.8.8.8').replace('sport=53122', 'sport=53123', 1) + '\n')
        tmp.write(signal_line + '\n')
        tmp.write(cluster_one + '\n')
        tmp.write(cluster_two + '\n')
        tmp.write(cluster_signal + '\n')
        for index in range(9):
            tmp.write(
                'ipv4 2 udp 17 135 src=192.168.1.23 dst=45.129.59.%d sport=45000 dport=50%03d '
                'packets=5 bytes=900 src=45.129.59.%d dst=10.107.57.20 sport=50%03d dport=45000 '
                'packets=5 bytes=900 [ASSURED] mark=0 use=2\n'
                % (index + 10, index, index + 10, index)
            )
        tmp_path = tmp.name
    try:
        lan_flows = telegram_call_learning.read_lan_conntrack_flows(router_ip='192.168.1.1', conntrack_path=tmp_path)
        device_flows = telegram_call_learning.read_conntrack_flows('192.168.1.23', conntrack_path=tmp_path)
        parsed_signature_lines = []
        original_parse_udp_flow = telegram_call_learning.parse_udp_flow

        def tracked_parse_udp_flow(value, *args, **kwargs):
            parsed_signature_lines.append(value)
            return original_parse_udp_flow(value, *args, **kwargs)

        telegram_call_learning.parse_udp_flow = tracked_parse_udp_flow
        try:
            udp_signature = telegram_call_learning.udp_source_activity_signature(['192.168.1.23'], conntrack_path=tmp_path)
        finally:
            telegram_call_learning.parse_udp_flow = original_parse_udp_flow
    finally:
        os.remove(tmp_path)
    assert list(lan_flows.values())[0]['src'] == '192.168.1.23'
    assert len(lan_flows) == 4
    cluster_flows = [item for item in lan_flows.values() if item.get('udp_call_cluster')]
    assert {item['dst'] for item in cluster_flows} == {'197.89.55.30', '91.132.107.120', '149.154.167.92'}
    assert all(item['cluster_flow_count'] == 3 for item in cluster_flows)
    assert all(item['cluster_telegram_flow_count'] == 1 for item in cluster_flows)
    assert not any(item.get('sport') == '45000' for item in lan_flows.values())
    assert any(item['dst'] == '149.154.167.91' for item in device_flows.values())
    assert udp_signature == (flow['identity'],)
    assert parsed_signature_lines == [
        line + '\n',
        line.replace('149.154.167.91', '8.8.8.8').replace('sport=53122', 'sport=53123', 1) + '\n',
    ]
    active_media_line = (
        'ipv4 2 udp 17 141 src=192.168.1.23 dst=80.234.76.169 sport=43490 dport=1624 '
        'packets=70 bytes=9000 src=80.234.76.169 dst=10.107.102.48 sport=1624 dport=43490 '
        'packets=71 bytes=6200 [ASSURED] mark=0 use=2'
    )
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as tmp:
        tmp.write(active_media_line + '\n')
        active_media_path = tmp.name
    try:
        active_media_flows = telegram_call_learning.read_lan_conntrack_flows(
            router_ip='192.168.1.1',
            conntrack_path=active_media_path,
            allowed_sources=['192.168.1.23'],
        )
    finally:
        os.remove(active_media_path)
    assert len(active_media_flows) == 1
    active_media_flow = next(iter(active_media_flows.values()))
    assert active_media_flow['dst'] == '80.234.76.169'
    assert active_media_flow['udp_call_active_media'] is True

    candidates = telegram_call_learning.learn_candidates(
        {},
        {flow['identity']: flow},
        min_score=5,
        min_packets=2,
        min_bytes=240,
    )
    assert len(candidates) == 1
    assert candidates[0]['address'] == '149.154.167.91'
    cluster_candidates = telegram_call_learning.learn_candidates(
        {},
        {item['identity']: item for item in cluster_flows},
        min_score=5,
        min_packets=2,
        min_bytes=240,
    )
    assert len(cluster_candidates) == 3
    assert all('udp-cluster' in item['reasons'] for item in cluster_candidates)
    assert len([item for item in cluster_candidates if not telegram_call_learning.address_in_networks(item['address'])]) == 2
    dry_run = telegram_call_learning.add_candidate_to_ipsets(candidates[0], 'vless', apply=False)
    assert dry_run['sets'] == ['unblockvless', 'unblockvlessudp']
    assert dry_run['applied_sets'] == []
    call_dry_run = telegram_call_learning.add_candidate_to_call_ipset(cluster_candidates[0], 'vless', apply=False)
    assert call_dry_run['sets'] == ['bypass_tg_call_vless']
    assert call_dry_run['applied_sets'] == []
    blocked_calls = []

    def known_route_runner(args, timeout=3):
        blocked_calls.append((args, timeout))
        if args[:2] == ['ipset', 'test'] and args[2] == 'unblockvless':
            return py_types.SimpleNamespace(returncode=0, stderr=b'')
        return py_types.SimpleNamespace(returncode=1, stderr=b'')

    non_telegram_call_candidate = next(
        item for item in cluster_candidates
        if not telegram_call_learning.address_in_networks(item['address'])
    )
    blocked_call = telegram_call_learning.add_candidate_to_call_ipset(
        non_telegram_call_candidate,
        'vless',
        apply=True,
        run_command=known_route_runner,
    )
    assert blocked_call['applied_sets'] == []
    assert blocked_call['errors'] == ['known_route_ipset']
    assert ['ipset', 'add', 'bypass_tg_call_vless', non_telegram_call_candidate['address'], 'timeout'] not in [
        item[0][:5] for item in blocked_calls
    ]
    telegram_call_adds = []

    def telegram_route_runner(args, timeout=3):
        telegram_call_adds.append((args, timeout))
        return py_types.SimpleNamespace(returncode=0, stderr=b'')

    telegram_call = telegram_call_learning.add_candidate_to_call_ipset(
        candidates[0],
        'vless',
        apply=True,
        run_command=telegram_route_runner,
    )
    assert telegram_call['applied_sets'] == ['bypass_tg_call_vless']
    assert telegram_call_adds[0][0][:3] == ['ipset', 'add', 'bypass_tg_call_vless']

    calls = []

    def runner(args, timeout=3):
        calls.append((args, timeout))
        return py_types.SimpleNamespace(returncode=0, stderr=b'')

    applied = telegram_call_learning.add_candidate_to_ipsets(candidates[0], 'vless2', apply=True, run_command=runner)
    assert applied['applied_sets'] == ['unblockvless2', 'unblockvless2udp']
    assert calls[0][0] == ['ipset', 'add', 'unblockvless2', '149.154.167.91', '-exist']
    assert telegram_call_learning.delete_conntrack_candidate(candidates[0], run_command=runner) is True
    assert calls[-1][0][:6] == ['conntrack', '-D', '-p', 'udp', '--orig-src', '192.168.1.23']


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
        fetch_keys_from_subscription=lambda url, **kwargs: ({}, ''),
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
        web_pool_snapshot=lambda keys, include_keys=False, protocols=None: snapshots.append({
            'include_keys': include_keys,
            'protocols': protocols,
        }) or {'vless': {'rows': []}},
        load_key_pools=lambda: {'vless': ['vless://one', 'vless://two']},
        hash_key=lambda key: 'id-one-1234' if key == 'vless://one' else 'id-two-1234',
        delete_pool_key=lambda proto, key: deleted.append((proto, key)),
        set_active_key=lambda proto, key: active.append((proto, key)),
        install_key_for_protocol=lambda proto, key, verify=True: 'installed',
        invalidate_web_status_cache=lambda: None,
        invalidate_key_status_cache=lambda: None,
    )
    import_calls = []
    pool_ctx.update(
        import_keys_to_pools=lambda proto, payload: import_calls.append((proto, payload)) or {
            'added_by_proto': {'vless2': 1, 'vmess': 1},
            'duplicate_count': 1,
            'unrecognized_count': 1,
        }
    )
    sample_vless_uri = 'vless' + '://one'
    sample_vmess_uri = 'vmess' + '://two'
    subscription_vless_uri = 'vless' + '://sub'
    old_vless_uri = 'vless' + '://old'
    subscription_trojan_uri = 'trojan' + '://sub'
    import_result = web_post_actions.dispatch(
        pool_ctx,
        '/pool_import',
        {'type': ['vless2'], 'import_payload': [f'{sample_vless_uri}\n{sample_vmess_uri}\nnot-a-key']},
    )
    assert import_result['success'] is True
    assert import_calls and import_calls[0][0] == 'vless2'
    assert 'добавлено: vless2: 1, vmess: 1' in import_result['result']
    assert 'дубли/уже были: 1' in import_result['result']
    assert 'не распознано: 1' in import_result['result']
    assert sample_vless_uri not in import_result['result']
    assert sample_vmess_uri not in import_result['result']
    subscription_calls = []
    subscription_saves = []
    pool_ctx.update(
        fetch_keys_from_subscription=lambda url, **kwargs: ({'vless': [subscription_vless_uri], 'trojan': [subscription_trojan_uri]}, ''),
        subscription_keys_for_protocol=lambda proto, fetched: fetched.get('vless', []) if proto == 'vless2' else fetched.get(proto, []),
        subscription_record=lambda proto: {'managed_keys': [old_vless_uri]},
        save_subscription_record=lambda proto, **updates: subscription_saves.append((proto, updates)),
        import_subscription_keys_to_pools=lambda proto, fetched, **kwargs: subscription_calls.append((proto, kwargs)) or {
            'selected_added': 1,
            'selected_duplicate_count': 0,
            'removed_count': 0,
            'retained_count': 0,
            'managed_keys': [subscription_vless_uri],
            'extra': {'added_by_proto': {'trojan': 1}, 'duplicate_count': 0, 'unrecognized_count': 0},
        },
    )
    subscription_result = web_post_actions.dispatch(
        pool_ctx,
        '/pool_import',
        {'type': ['vless2'], 'import_payload': ['https://subscription.example.test/path'], 'send_router_hwid': ['1']},
    )
    assert subscription_result['success'] is True
    assert subscription_result['result'].startswith('Подписка загружена;')
    assert 'Subscription' not in subscription_result['result']
    assert subscription_calls and subscription_calls[0][0] == 'vless2'
    assert subscription_calls[0][1]['sync_subscription'] is True
    assert subscription_calls[0][1]['previous_managed_keys'] == [old_vless_uri]
    assert subscription_saves and subscription_saves[0][0] == 'vless2'
    assert subscription_saves[0][1]['hwid_enabled'] is True
    assert subscription_saves[0][1]['managed_keys'] == [subscription_vless_uri]
    assert 'другие протоколы: trojan: 1' in subscription_result['result']
    assert 'subscription.example.test' not in subscription_result['result']
    subscription_saves.clear()
    pool_ctx.update(
        fetch_keys_from_subscription=lambda url, **kwargs: ({'trojan': [subscription_trojan_uri]}, ''),
        import_subscription_keys_to_pools=lambda proto, fetched, **kwargs: {
            'selected_added': 0,
            'selected_duplicate_count': 0,
            'removed_count': 0,
            'retained_count': 0,
            'managed_keys': [],
            'extra': {'added_by_proto': {'trojan': 1}, 'duplicate_count': 0, 'unrecognized_count': 0},
        },
    )
    no_selected_subscription_result = web_post_actions.dispatch(
        pool_ctx,
        '/pool_import',
        {'type': ['vless2'], 'import_payload': ['https://subscription.example.test/other'], 'send_router_hwid': ['1']},
    )
    assert no_selected_subscription_result['success'] is True
    assert subscription_saves == []
    assert 'другие протоколы: trojan: 1' in no_selected_subscription_result['result']
    delete_result = web_post_actions.dispatch(pool_ctx, '/pool_delete', {'type': ['vless'], 'key_id': ['id-two-1234']})
    assert delete_result['success'] is True
    assert deleted == [('vless', 'vless://two')]
    assert delete_result['extra']['key_id'] == 'id-two-1234'
    assert snapshots[-1] == {'include_keys': False, 'protocols': ['vless']}
    snapshot_count_before_apply = len(snapshots)
    apply_result = web_post_actions.dispatch(pool_ctx, '/pool_apply', {'type': ['vless'], 'key_id': ['id-one-1234']})
    assert apply_result['success'] is True
    assert active == [('vless', 'vless://one')]
    assert apply_result['extra']['key_id'] == 'id-one-1234'
    assert 'key' not in apply_result['extra']
    assert len(snapshots) == snapshot_count_before_apply
    install_result = web_post_actions.dispatch(pool_ctx, '/install', {'type': ['vless'], 'key': ['vless://one']})
    assert install_result['success'] is True
    assert 'key' not in install_result['extra']
    assert web_post_actions.dispatch(ctx, '/telegram_call_learn', {}) is None


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
    return f'1.{count}'


def test_codex_version_matches_commit_count():
    expected = _expected_codex_version_counter()
    version_md = (ROOT / 'version.md').read_text(encoding='utf-8')
    changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    installer = (APP_ROOT / 'installer.py').read_text(encoding='utf-8')
    bootstrap = (ROOT / 'bootstrap' / 'install.sh').read_text(encoding='utf-8')
    example = (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8')
    assert app_version.APP_VERSION_COUNTER == expected
    assert version_md.startswith(f'*v{expected} ')
    assert version_md.count('*v') == 1
    assert changelog.startswith(f'<a name="{expected}"></a>\n# [{expected}] - ')
    assert 'v{APP_VERSION_COUNTER}' in installer
    assert 'from app_version import APP_VERSION_COUNTER' in installer
    assert 'from app_version import APP_VERSION_COUNTER' in bootstrap
    assert 'memory_watchdog_rss_limit_kb = 112640' in example
    assert 'memory_watchdog_rss_limit_kb = 112640' in installer
    assert 'memory_watchdog_rss_limit_kb = 112640' in bootstrap
    assert 'pool_probe_pause_available_kb = 125000' in example
    assert 'pool_probe_pause_available_kb = 125000' in installer
    assert 'pool_probe_pause_available_kb = 125000' in bootstrap
    assert 'pool_probe_slow_available_kb = 190000' in example
    assert 'pool_probe_slow_available_kb = 190000' in installer
    assert 'pool_probe_slow_available_kb = 190000' in bootstrap
    assert 'pool_probe_delay_seconds = 3.0' in example
    assert 'pool_probe_delay_seconds = 3.0' in installer
    assert 'pool_probe_delay_seconds = 3.0' in bootstrap
    assert 'pool_probe_cpu_guard_enabled = True' in example
    assert 'pool_probe_cpu_guard_enabled = True' in installer
    assert 'pool_probe_cpu_guard_enabled = True' in bootstrap
    assert 'pool_probe_max_cpu_percent = 45.0' in example
    assert 'pool_probe_max_cpu_percent = 45.0' in installer
    assert 'pool_probe_max_cpu_percent = 45.0' in bootstrap
    assert 'pool_probe_high_cpu_delay_seconds = 8.0' in example
    assert 'pool_probe_high_cpu_delay_seconds = 8.0' in installer
    assert 'pool_probe_high_cpu_delay_seconds = 8.0' in bootstrap
    assert 'pool_probe_high_cpu_max_wait_seconds = 120.0' in example
    assert 'pool_probe_high_cpu_max_wait_seconds = 120.0' in installer
    assert 'pool_probe_high_cpu_max_wait_seconds = 120.0' in bootstrap
    assert 'pool_probe_max_load1 = 2.0' in example
    assert 'pool_probe_max_load1 = 2.0' in installer
    assert 'pool_probe_max_load1 = 2.0' in bootstrap
    assert 'pool_probe_quality_download_bytes = 524288' in example
    assert 'pool_probe_quality_download_bytes = 524288' in installer
    assert 'pool_probe_quality_download_bytes = 524288' in bootstrap
    assert 'pool_probe_quality_max_samples_per_run = 6' in example
    assert 'pool_probe_quality_max_samples_per_run = 6' in installer
    assert 'pool_probe_quality_max_samples_per_run = 6' in bootstrap
    assert 'pool_probe_max_process_rss_kb = 66560' in example
    assert 'pool_probe_max_process_rss_kb = 66560' in installer
    assert 'pool_probe_max_process_rss_kb = 66560' in bootstrap
    assert 'pool_failover_process_worker_enabled = True' in example
    assert 'pool_failover_process_worker_enabled = True' in installer
    assert 'pool_failover_process_worker_enabled = True' in bootstrap
    assert 'pool_failover_process_worker_timeout_seconds = 180.0' in example
    assert 'pool_failover_process_worker_timeout_seconds = 180.0' in installer
    assert 'pool_failover_process_worker_timeout_seconds = 180.0' in bootstrap
    assert "pool_probe_youtube_profile = 'quick'" in example
    assert "pool_probe_youtube_profile = 'quick'" in installer
    assert "pool_probe_youtube_profile = 'quick'" in bootstrap
    assert 'memory_watchdog_idle_restart_rss_kb' not in example
    assert 'memory_watchdog_idle_restart_rss_kb' not in installer
    assert 'memory_watchdog_idle_restart_rss_kb' not in bootstrap
    assert 'memory_timeline_enabled = False' in example
    assert 'memory_timeline_enabled = False' in installer
    assert 'memory_timeline_enabled = False' in bootstrap
    assert 'status_refresh_min_interval_seconds = 180.0' in example
    assert 'status_refresh_min_interval_seconds = 180.0' in installer
    assert 'status_refresh_min_interval_seconds = 180.0' in bootstrap
    assert 'status_refresh_pending_min_interval_seconds = 60.0' in example
    assert 'status_refresh_pending_min_interval_seconds = 60.0' in installer
    assert 'status_refresh_pending_min_interval_seconds = 60.0' in bootstrap
    assert 'router_health_cache_ttl = 30.0' in example
    assert 'router_health_cache_ttl = 30.0' in installer
    assert 'router_health_cache_ttl = 30.0' in bootstrap
    assert 'router_health_related_process_cache_ttl = 45.0' in example
    assert 'router_health_related_process_cache_ttl = 45.0' in installer
    assert 'router_health_related_process_cache_ttl = 45.0' in bootstrap
    assert 'router_health_cpu_smoothing_factor = 0.35' in example
    assert 'router_health_cpu_smoothing_factor = 0.35' in installer
    assert 'router_health_cpu_smoothing_factor = 0.35' in bootstrap
    assert 'web_status_api_cache_ttl = 30.0' in example
    assert 'web_status_api_cache_ttl = 30.0' in installer
    assert 'web_status_api_cache_ttl = 30.0' in bootstrap
    assert 'auto_failover_recent_success_ttl = 900' in example
    assert 'auto_failover_recent_success_ttl = 900' in installer
    assert 'auto_failover_recent_success_ttl = 900' in bootstrap
    assert 'auto_failover_idle_log_interval_seconds = 900' in example
    assert 'auto_failover_idle_log_interval_seconds = 900' in installer
    assert 'auto_failover_idle_log_interval_seconds = 900' in bootstrap
    assert 'subscription_auto_refresh_interval_seconds = 21600' in example
    assert 'subscription_auto_refresh_interval_seconds = 21600' in installer
    assert 'subscription_auto_refresh_interval_seconds = 21600' in bootstrap
    assert 'subscription_auto_refresh_check_seconds = 300' in example
    assert 'subscription_auto_refresh_check_seconds = 300' in installer
    assert 'subscription_auto_refresh_check_seconds = 300' in bootstrap
    assert 'router_metrics_history_limit = 120' in example
    assert 'router_metrics_history_limit = 120' in installer
    assert 'router_metrics_history_limit = 120' in bootstrap
    assert 'router_metrics_warn_bot_rss_kb = 66560' in example
    assert 'router_metrics_warn_bot_rss_kb = 66560' in installer
    assert 'router_metrics_warn_bot_rss_kb = 66560' in bootstrap
    assert 'router_metrics_critical_bot_rss_kb = 87040' in example
    assert 'router_metrics_critical_bot_rss_kb = 87040' in installer
    assert 'router_metrics_critical_bot_rss_kb = 87040' in bootstrap
    assert 'router_metrics_warn_load1 = 3.0' in example
    assert 'router_metrics_warn_load1 = 3.0' in installer
    assert 'router_metrics_warn_load1 = 3.0' in bootstrap
    assert 'web_pools_api_cache_ttl = 45.0' in example
    assert 'web_pools_api_cache_ttl = 45.0' in installer
    assert 'web_pools_api_cache_ttl = 45.0' in bootstrap
    assert 'service_route_intersections_cache_ttl = 60.0' in example
    assert 'service_route_intersections_cache_ttl = 60.0' in installer
    assert 'service_route_intersections_cache_ttl = 60.0' in bootstrap
    assert 'web_response_cleanup_rss_kb' not in example
    assert 'web_response_cleanup_rss_kb' not in installer
    assert 'web_response_cleanup_rss_kb' not in bootstrap
    assert 'web_response_light_cleanup_rss_kb' not in example
    assert 'web_response_light_cleanup_rss_kb' not in installer
    assert 'web_response_light_cleanup_rss_kb' not in bootstrap
    assert 'web_response_cleanup_min_interval_seconds' not in example
    assert 'web_response_cleanup_min_interval_seconds' not in installer
    assert 'web_response_cleanup_min_interval_seconds' not in bootstrap
    assert "memory_timeline_path = '/opt/tmp/bypass_memory_timeline.jsonl'" in example
    assert "memory_timeline_path = '/opt/tmp/bypass_memory_timeline.jsonl'" in installer
    assert "memory_timeline_path = '/opt/tmp/bypass_memory_timeline.jsonl'" in bootstrap
    assert 'memory_timeline_max_events = 720' in example
    assert 'memory_timeline_max_events = 720' in installer
    assert 'memory_timeline_max_events = 720' in bootstrap
    assert 'memory_timeline_trim_min_interval_seconds = 300.0' in example
    assert 'memory_timeline_trim_min_interval_seconds = 300.0' in installer
    assert 'memory_timeline_trim_min_interval_seconds = 300.0' in bootstrap
    assert 'background_task_cpu_cache_ttl_seconds = 20.0' in example
    assert 'background_task_cpu_cache_ttl_seconds = 20.0' in installer
    assert 'background_task_cpu_cache_ttl_seconds = 20.0' in bootstrap
    assert 'background_task_max_cpu_percent = 45.0' in example
    assert 'background_task_max_cpu_percent = 45.0' in installer
    assert 'background_task_max_cpu_percent = 45.0' in bootstrap
    assert 'background_task_max_bot_rss_kb = 66560' in example
    assert 'background_task_max_bot_rss_kb = 66560' in installer
    assert 'background_task_max_bot_rss_kb = 66560' in bootstrap
    assert 'background_task_critical_max_bot_rss_kb = 71680' in example
    assert 'background_task_critical_max_bot_rss_kb = 71680' in installer
    assert 'background_task_critical_max_bot_rss_kb = 71680' in bootstrap
    assert 'background_task_max_program_rss_kb = 102400' in example
    assert 'background_task_max_program_rss_kb = 102400' in installer
    assert 'background_task_max_program_rss_kb = 102400' in bootstrap
    assert 'background_task_critical_max_program_rss_kb = 102400' in example
    assert 'background_task_critical_max_program_rss_kb = 102400' in installer
    assert 'background_task_critical_max_program_rss_kb = 102400' in bootstrap
    assert 'memory_watchdog_idle_restart_hold_seconds' not in example
    assert 'memory_watchdog_idle_restart_hold_seconds' not in installer
    assert 'memory_watchdog_idle_restart_hold_seconds' not in bootstrap
    assert 'memory_post_pool_restart_rss_kb' not in example
    assert 'memory_post_pool_restart_rss_kb' not in installer
    assert 'memory_post_pool_restart_rss_kb' not in bootstrap
    assert 'memory_post_pool_cleanup_target_rss_kb' not in example
    assert 'memory_post_pool_cleanup_target_rss_kb' not in installer
    assert 'memory_post_pool_cleanup_target_rss_kb' not in bootstrap
    assert 'memory_post_pool_restart_retry_seconds' not in example
    assert 'memory_post_pool_restart_retry_seconds' not in installer
    assert 'memory_post_pool_restart_retry_seconds' not in bootstrap
    assert 'memory_post_pool_restart_max_wait_seconds' not in example
    assert 'memory_post_pool_restart_max_wait_seconds' not in installer
    assert 'memory_post_pool_restart_max_wait_seconds' not in bootstrap
    assert 'ipset_refresh_command_timeout_seconds = 420' in example
    assert 'ipset_refresh_command_timeout_seconds = 420' in installer
    assert 'ipset_refresh_command_timeout_seconds = 420' in bootstrap
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
    assert "youtube_quic_policy = 'auto'" in example
    assert "youtube_quic_policy = 'auto'" in installer
    assert "youtube_quic_policy = 'auto'" in bootstrap
    assert "telegram_udp_policy = 'auto'" in example
    assert "telegram_udp_policy = 'auto'" in installer
    assert "telegram_udp_policy = 'auto'" in bootstrap
    for config_line in (
        'youtube_edge_prefetch_enabled = True',
        "youtube_edge_prefetch_mode = 'external'",
        'youtube_edge_prefetch_start_delay_seconds = 120',
        'youtube_edge_prefetch_interval_seconds = 0',
        "youtube_edge_prefetch_cache_path = '/opt/etc/bot/youtube_edge_cache.json'",
        "youtube_edge_prefetch_status_path = '/opt/etc/bot/youtube_edge_prefetch_status.json'",
        "youtube_edge_prefetch_lock_dir = '/tmp/bypass-youtube-edge-prefetch.lock'",
        'youtube_edge_prefetch_cache_ttl_seconds = 259200',
        'youtube_edge_prefetch_max_cache_entries = 128',
        'youtube_edge_prefetch_max_hosts_per_run = 6',
        'youtube_edge_prefetch_max_resolved_addresses = 16',
        'youtube_edge_prefetch_max_candidates = 32',
        'youtube_edge_prefetch_max_addresses_per_run = 8',
        'youtube_edge_prefetch_min_available_kb = 125000',
        'youtube_edge_prefetch_max_rss_kb = 66560',
        'youtube_edge_prefetch_exclusive_ipsets = True',
        'youtube_edge_prefetch_protect_shared_google = True',
        'youtube_edge_prefetch_cache_restore_enabled = True',
        'youtube_edge_prefetch_cache_restore_max_addresses = 16',
        'youtube_edge_prefetch_cache_restore_require_quality_ok = True',
        'youtube_edge_prefetch_fast_warm_enabled = True',
        'youtube_edge_prefetch_fast_hosts = (',
        'youtube_edge_prefetch_fast_max_hosts_per_run = 4',
        'youtube_edge_prefetch_fast_max_candidates = 16',
        'youtube_edge_prefetch_quality_probe_enabled = True',
        'youtube_edge_prefetch_quality_target_ms = 1000',
        'youtube_edge_prefetch_quality_timeout_seconds = 5',
        'youtube_edge_prefetch_quality_bad_cooldown_seconds = 3600',
        'youtube_edge_prefetch_quality_max_candidates = 12',
        'youtube_edge_prefetch_scheduler_max_cpu_percent = 45',
        'youtube_edge_prefetch_scheduler_max_load1 = 2.0',
        'youtube_edge_prefetch_cpu_sample_ms = 250',
        'youtube_edge_prefetch_skip_when_unblock_running = True',
        'youtube_edge_prefetch_skip_when_pool_probe_running = True',
        "youtube_edge_prefetch_unblock_lock_dir = '/tmp/bypass-unblock-ipset.lock'",
        'youtube_edge_prefetch_unblock_lock_stale_seconds = 600',
        'youtube_edge_watch_warm_enabled = True',
        'youtube_edge_watch_warm_urls = (',
        "'https://www.youtube.com/watch?v=jfKfPfyJRdk'",
        'youtube_edge_watch_warm_max_pages = 1',
        'youtube_edge_watch_warm_max_hosts = 6',
        'youtube_edge_watch_warm_max_bytes = 450000',
        'youtube_edge_watch_warm_connect_timeout = 4',
        'youtube_edge_watch_warm_max_time = 10',
        "youtube_edge_prefetch_dns_servers = ('local', '1.1.1.1', '8.8.8.8')",
        'youtube_edge_prefetch_hosts = (',
    ):
        assert config_line in example
        assert config_line in installer
        assert config_line in bootstrap
    assert "youtube_edge_prefetch_min_available_kb[[:space:]]*=[[:space:]]*160000" in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_prefetch_min_available_kb = 125000' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert "youtube_edge_prefetch_max_hosts_per_run[[:space:]]*=[[:space:]]*(4|12)" in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_prefetch_max_hosts_per_run = 6' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_prefetch_quality_target_ms = 1000' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_prefetch_cache_restore_enabled = True' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_prefetch_cache_restore_max_addresses = 16' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_prefetch_cache_restore_require_quality_ok = True' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_prefetch_fast_max_hosts_per_run = 4' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_prefetch_skip_when_unblock_running = True' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_prefetch_skip_when_pool_probe_running = True' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_watch_warm_max_pages = 1' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_watch_warm_max_hosts = 6' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_watch_warm_max_bytes = 450000' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'web_response_cleanup_rss_kb' not in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'web_response_light_cleanup_rss_kb' not in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'web_response_cleanup_min_interval_seconds' not in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'router_health_related_process_cache_ttl = 45.0' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'router_health_cache_ttl = 30.0' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'router_health_cpu_smoothing_factor = 0.35' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'background_task_cpu_cache_ttl_seconds = 20.0' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'background_task_max_cpu_percent = 45.0' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'status_refresh_pending_min_interval_seconds = 60.0' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert '[ "$BOT_CONFIG_PATH" != "/opt/etc/bot_config.py" ] && [ -f "/opt/etc/bot_config.py" ]' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'service_route_intersections_cache_ttl = 60.0' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_prefetch_scheduler_max_cpu_percent = 45' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_prefetch_scheduler_max_load1 = 2.0' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_edge_prefetch_cpu_sample_ms = 250' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'active_status_recent_success_ttl = 900' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'auto_failover_recent_success_ttl = 900' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'youtube_vless2_failover_recent_success_ttl = 900' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'jfKfPfyJRdk' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    for config_line in (
        'telegram_call_learning_enabled = True',
        "telegram_call_learning_state_path = '/tmp/bypass_telegram_call_learning.json'",
        'telegram_call_learning_default_duration_seconds = 90',
        'telegram_call_learning_max_duration_seconds = 180',
        'telegram_call_learning_poll_interval_seconds = 1.0',
        'telegram_call_learning_auto_enabled = True',
        'telegram_call_learning_scan_interval_seconds = 5.0',
        'telegram_call_learning_min_score = 5',
        'telegram_call_learning_min_packets = 2',
        'telegram_call_learning_min_bytes = 240',
        'telegram_call_learning_max_candidates = 20',
        'telegram_call_learning_max_seen_addresses = 512',
        'telegram_call_learning_apply_by_default = True',
        'telegram_call_learning_client_timeout_seconds = 900',
        'telegram_call_learning_address_timeout_seconds = 14400',
        'telegram_call_tproxy_enabled = True',
        "localportsh_tproxy = '11802'",
        "localportvmess_tproxy = '11815'",
        "localportvless_tproxy = '11812'",
        "localportvless2_tproxy = '11814'",
        "localporttrojan_tproxy = '11829'",
    ):
        assert config_line in example
        assert config_line in installer
        assert config_line in bootstrap
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
    assert 'auto_failover_consecutive_failures = 3' in example
    assert 'auto_failover_consecutive_failures = 3' in installer
    assert 'auto_failover_consecutive_failures = 3' in bootstrap
    assert 'auto_failover_traffic_guard_bypass_failures = 3' in example
    assert 'auto_failover_traffic_guard_bypass_failures = 3' in installer
    assert 'auto_failover_traffic_guard_bypass_failures = 3' in bootstrap
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


def test_ui_smoke_package_scripts_are_declared():
    package = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
    scripts = package.get('scripts') or {}
    dev_dependencies = package.get('devDependencies') or {}
    assert package.get('private') is True
    assert scripts.get('ui:check') == 'node --check tests/ui_smoke.js && node --check tests/run_ui_smoke_fixture.js'
    assert scripts.get('ui:smoke') == 'node tests/run_ui_smoke_fixture.js'
    assert scripts.get('ui:install-browsers') == 'playwright install --with-deps chromium'
    assert dev_dependencies.get('playwright') == '1.60.0'


def test_update_script_socks_download_notice_is_not_repeated():
    script = (ROOT / 'script.sh').read_text(encoding='utf-8')
    unblock_dnsmasq = (APP_ROOT / 'unblock.dnsmasq').read_text(encoding='utf-8')
    assert 'Downloaded via local SOCKS port' not in script
    assert 'Downloading GitHub files via local SOCKS port ${port}.' in script
    assert 'RAW_GITHUB_SOCKS_NOTICE_SHOWN=1' in script
    assert 'remove_path /opt/root/get-pip.py' in script
    assert 'chmod 777 /opt/root/get-pip.py || rm' not in script
    assert 'touch /opt/etc/hosts && chmod 0644 /opt/etc/hosts' in script
    assert "normalize_line()" in unblock_dnsmasq
    assert "s/\\r//g" in unblock_dnsmasq
    assert 'UNBLOCK_DIR="${UNBLOCK_DIR:-/opt/etc/unblock}"' in unblock_dnsmasq
    assert 'DNSMASQ_OUTPUT_TARGET="${DNSMASQ_OUTPUT_FILE:-/opt/etc/unblock.dnsmasq}"' in unblock_dnsmasq
    assert 'DNSMASQ_OUTPUT_FILE="${DNSMASQ_OUTPUT_TARGET}.tmp.$$"' in unblock_dnsmasq
    assert 'mv -f "$DNSMASQ_OUTPUT_FILE" "$DNSMASQ_OUTPUT_TARGET"' in unblock_dnsmasq
    assert 'YOUTUBE_ROUTE_PRIORITY_DOMAINS="${YOUTUBE_ROUTE_PRIORITY_DOMAINS:-youtube.com www.youtube.com' in unblock_dnsmasq
    assert 'YOUTUBE_ROUTE_PROTOCOL="$(youtube_route_protocol)"' in unblock_dnsmasq
    assert 'write_route_domain()' in unblock_dnsmasq
    assert 'append_youtube_priority_domains()' in unblock_dnsmasq
    assert 'dedupe_dnsmasq_output()' in unblock_dnsmasq
    assert 'line=$(normalize_line "$line")' in unblock_dnsmasq
    assert 'connectivity_check_domain()' in unblock_dnsmasq
    assert 'connectivity_check_domain "$line" && return 0' in unblock_dnsmasq
    assert 'udp_quic_domain()' in unblock_dnsmasq
    assert 'call_signal_domain()' in unblock_dnsmasq
    assert 'append_dnsmasq_domain "$line" "$main_set" "$udp_set" "$call_signal_set"' in unblock_dnsmasq
    assert 'write_route_domain shadowsocks "$line" unblocksh unblockshudp bypass_call_signal_sh 1' in unblock_dnsmasq
    assert 'write_route_domain vmess "$line" unblockvmess unblockvmessudp bypass_call_signal_vmess 0' in unblock_dnsmasq
    assert 'write_route_domain vless "$line" unblockvless unblockvlessudp bypass_call_signal_vless 0' in unblock_dnsmasq
    assert 'write_route_domain vless2 "$line" unblockvless2 unblockvless2udp bypass_call_signal_vless2 0' in unblock_dnsmasq
    assert 'write_route_domain trojan "$line" unblocktroj unblocktrojudp bypass_call_signal_troj 0' in unblock_dnsmasq


def test_unblock_dnsmasq_routes_youtube_to_single_owner(tmp_path):
    def shell_path(path):
        value = str(Path(path).resolve()).replace('\\', '/')
        if re.match(r'^[A-Za-z]:/', value):
            return f'/mnt/{value[0].lower()}{value[2:]}'
        return value

    def shell_quote(value):
        return "'" + str(value).replace("'", "'\"'\"'") + "'"

    unblock_dir = tmp_path / 'unblock'
    unblock_dir.mkdir()
    for file_name in ('shadowsocks.txt', 'vmess.txt', 'trojan.txt'):
        (unblock_dir / file_name).write_text('', encoding='utf-8')
    (unblock_dir / 'vless.txt').write_text('youtube.com\nexample-vless.test\n', encoding='utf-8')
    (unblock_dir / 'vless-2.txt').write_text(
        'youtube.com\nwww.youtube.com\ngooglevideo.com\nexample-vless2.test\n',
        encoding='utf-8',
    )
    udp_policy = tmp_path / 'udp.txt'
    call_policy = tmp_path / 'call.txt'
    output = tmp_path / 'out.dnsmasq'
    log_file = tmp_path / 'dnsmasq.log'
    owner_state = tmp_path / 'youtube-owner.json'
    udp_policy.write_text('', encoding='utf-8')
    call_policy.write_text('', encoding='utf-8')

    command = ' '.join((
        f'UNBLOCK_DIR={shell_quote(shell_path(unblock_dir))}',
        f'DNSMASQ_OUTPUT_FILE={shell_quote(shell_path(output))}',
        f'DNSMASQ_LOG_FILE={shell_quote(shell_path(log_file))}',
        f'UDP_QUIC_POLICY_FILE={shell_quote(shell_path(udp_policy))}',
        f'CALL_SIGNAL_POLICY_FILE={shell_quote(shell_path(call_policy))}',
        f'YOUTUBE_ROUTE_OWNER_STATE_FILE={shell_quote(shell_path(owner_state))}',
        f'BOT_DIR={shell_quote(shell_path(APP_ROOT))}',
        'bash',
        shell_quote(shell_path(APP_ROOT / 'unblock.dnsmasq')),
    ))
    subprocess.run(
        ['bash', '-lc', command],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    dnsmasq_text = output.read_text(encoding='utf-8')
    assert 'ipset=/youtube.com/unblockvless2' in dnsmasq_text

    assert 'ipset=/www.youtube.com/unblockvless2' in dnsmasq_text
    assert 'ipset=/m.youtube.com/unblockvless2' in dnsmasq_text
    assert 'ipset=/googlevideo.com/unblockvless2' in dnsmasq_text
    assert 'ipset=/youtube.com/unblockvless/' not in dnsmasq_text
    assert 'ipset=/googlevideo.com/unblockvless/' not in dnsmasq_text
    assert 'ipset=/example-vless.test/unblockvless' in dnsmasq_text
    assert 'ipset=/example-vless2.test/unblockvless2' in dnsmasq_text
    assert 'youtube_route=vless2' in log_file.read_text(encoding='utf-8')

    (unblock_dir / 'vless.txt').write_text(
        'youtube.com\nwww.youtube.com\ngooglevideo.com\nexample-vless.test\n',
        encoding='utf-8',
    )
    (unblock_dir / 'vless-2.txt').write_text('youtube.com\nexample-vless2.test\n', encoding='utf-8')
    subprocess.run(
        ['bash', '-lc', command],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    dnsmasq_text = output.read_text(encoding='utf-8')
    assert 'ipset=/youtube.com/unblockvless\n' in dnsmasq_text
    assert 'ipset=/googlevideo.com/unblockvless\n' in dnsmasq_text
    assert 'ipset=/youtube.com/unblockvless2' not in dnsmasq_text
    assert 'ipset=/googlevideo.com/unblockvless2' not in dnsmasq_text

    route_sets = {
        'shadowsocks': ('shadowsocks.txt', 'unblocksh'),
        'vmess': ('vmess.txt', 'unblockvmess'),
        'vless': ('vless.txt', 'unblockvless'),
        'vless2': ('vless-2.txt', 'unblockvless2'),
        'trojan': ('trojan.txt', 'unblocktroj'),
    }
    for protocol, (file_name, ipset_name) in route_sets.items():
        for other_file_name, _other_set in route_sets.values():
            (unblock_dir / other_file_name).write_text('example.com\n', encoding='utf-8')
        (unblock_dir / file_name).write_text(
            'youtube.com\nwww.youtube.com\ngooglevideo.com\n',
            encoding='utf-8',
        )
        owner_state.unlink(missing_ok=True)
        subprocess.run(
            ['bash', '-lc', command],
            check=True,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        dnsmasq_text = output.read_text(encoding='utf-8')
        assert f'ipset=/youtube.com/{ipset_name}\n' in dnsmasq_text
        assert f'ipset=/googlevideo.com/{ipset_name}\n' in dnsmasq_text
        for other_protocol, (_other_file_name, other_set) in route_sets.items():
            if other_protocol != protocol:
                assert f'ipset=/youtube.com/{other_set}\n' not in dnsmasq_text
        assert f'youtube_route={protocol}' in log_file.read_text(encoding='utf-8')


def test_shell_youtube_route_owner_uses_shared_resolver():
    for script_name in ('unblock.dnsmasq', 'unblock_ipset.sh', 'S99unblock'):
        source = (APP_ROOT / script_name).read_text(encoding='utf-8')
        assert 'from youtube_route_owner import youtube_route_owner' in source
        assert 'YOUTUBE_ROUTE_PROTOCOL_CACHE' in source
        assert 'YOUTUBE_ROUTE_OWNER_STATE_FILE' in source
        assert 'state_path=sys.argv[2]' in source
        assert 'default=\'vless2\'' not in source
        assert 'route_file_marker_count()' not in source


def test_youtube_route_owner_supports_every_protocol_without_forced_fallback(tmp_path):
    unblock_dir = tmp_path / 'unblock'
    unblock_dir.mkdir()
    state_path = tmp_path / 'owner.json'
    for protocol, file_name in youtube_route_owner.ROUTE_FILES:
        for _other_protocol, other_file_name in youtube_route_owner.ROUTE_FILES:
            (unblock_dir / other_file_name).write_text('example.com\n', encoding='utf-8')
        (unblock_dir / file_name).write_text('youtube.com\n', encoding='utf-8')
        resolution = youtube_route_owner.resolve_youtube_route_owner(
            unblock_dir=str(unblock_dir),
            state_path=str(state_path),
        )
        assert resolution == {'protocol': protocol, 'source': 'partial'}

    for _protocol, file_name in youtube_route_owner.ROUTE_FILES:
        (unblock_dir / file_name).write_text('youtube.com\n', encoding='utf-8')
    assert youtube_route_owner.resolve_youtube_route_owner(
        unblock_dir=str(unblock_dir),
        state_path=str(state_path),
    ) == {'protocol': 'trojan', 'source': 'last_confirmed'}

    fresh_state_path = tmp_path / 'fresh-owner.json'
    assert youtube_route_owner.resolve_youtube_route_owner(
        unblock_dir=str(unblock_dir),
        state_path=str(fresh_state_path),
    ) == {'protocol': '', 'source': 'ambiguous'}
    assert youtube_edge_prefetch_runner.detect_youtube_route_protocol(
        str(unblock_dir),
        state_path=str(fresh_state_path),
    ) == ''


def test_direct_update_script_records_update_status():
    script = (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'write_cli_update_status()' in script
    assert "path = '/opt/etc/bot/update_status.json'" in script
    assert 'write_cli_update_status update true 3 Preparing "CLI update started"' in script
    assert 'write_cli_update_status update true 10 Downloading "Downloading update files"' in script
    assert 'download_update_file "$(repo_file_url script.sh)"' in script
    assert '"$stage_dir/script.sh" "#!/bin/sh" "script.sh"' in script
    assert 'staged_runtime_modules=$(sed -n' in script
    assert 'for module in $staged_runtime_modules; do' in script
    assert 'target_release=$(sed -n' in script
    assert 'write_cli_update_status update true 40 Staged "Update files staged" "$target_release"' in script
    assert 'mv /opt/root/script.sh "$backup_dir"/script.sh' in script
    assert 'mv "$stage_dir/script.sh" /opt/root/script.sh' in script
    assert 'restore_file script.sh /opt/root/script.sh' in script
    assert 'write_cli_update_status update true 85 Restarting "Restarting services"' in script
    assert 'write_cli_update_status update false 100 Done "CLI update complete"' in script
    assert 'write_cli_update_status update false 100 Done "CLI update complete; installer started"' in script
    assert 'write_cli_update_status update false 100 Error "CLI update failed"' in script
    assert 'keep_count="${1:-1}"' in script
    assert 'cleanup_update_artifacts 1' in script
    assert 'cleanup_update_artifacts 3' not in script
    bootstrap = (ROOT / 'bootstrap' / 'install.sh').read_text(encoding='utf-8')
    assert 'cleanup_bootstrap_backups()' in bootstrap
    assert 'cleanup_bootstrap_backups 1' in bootstrap


def test_update_static_assets_use_archive_fallback():
    script = (ROOT / 'script.sh').read_text(encoding='utf-8')
    update_body = re.search(r'download_update_file\(\) \{(?P<body>.*?)\nruntime_module_url\(\)', script, re.S).group('body')
    update_archive_index = update_body.index('download_repo_file_from_archive "$url" "$target"')
    update_api_index = update_body.index('download_repo_file_via_api "$url" "$target"')
    update_raw_index = update_body.index('curl -fsSL --connect-timeout 5 --max-time 8')
    update_socks_notice_index = update_body.index('Direct GitHub archive/API and raw download failed')
    assert update_archive_index < update_api_index < update_raw_index < update_socks_notice_index
    assert 'raw.githubusercontent.com direct download failed for ${description}; trying local SOCKS.' not in update_body
    function_body = re.search(r'download_static_asset\(\) \{(?P<body>.*?)\n\}', script, re.S).group('body')
    archive_index = function_body.index('download_repo_file_from_archive "$url" "$target"')
    api_index = function_body.index('download_repo_file_via_api "$url" "$target"')
    curl_index = function_body.index('curl -fsSL')
    assert archive_index < api_index < curl_index
    assert 'install_static_assets' in script
    assert 'static/service-icons/${icon}.png' in script


def test_local_archive_update_env_is_preserved():
    script = (ROOT / 'script.sh').read_text(encoding='utf-8')
    top_block = script.split('config_get() {', 1)[0]
    assert 'if [ "${RAW_GITHUB_BYPASS:-0}" = "1" ] || [ -n "${UPDATE_ARCHIVE_ROOT:-}" ]; then' in top_block
    assert 'unset UPDATE_ARCHIVE_ROOT RAW_GITHUB_USE_SOCKS RAW_GITHUB_BYPASS RAW_GITHUB_SOCKS_NOTICE_SHOWN' in top_block
    clear_body = re.search(r'clear_runtime_update_env\(\) \{(?P<body>.*?)\n\}', script, re.S).group('body')
    assert 'if [ "${RAW_GITHUB_BYPASS:-0}" = "1" ] || [ -n "${UPDATE_ARCHIVE_ROOT:-}" ]; then' in clear_body
    assert 'unset RAW_GITHUB_USE_SOCKS RAW_GITHUB_SOCKS_NOTICE_SHOWN' in clear_body
    assert 'unset REPO_REF UPDATE_ARCHIVE_ROOT RAW_GITHUB_USE_SOCKS RAW_GITHUB_BYPASS RAW_GITHUB_SOCKS_NOTICE_SHOWN' in clear_body


def test_realtime_call_signal_catalog_is_call_specific():
    entries = set(service_catalog.REALTIME_CALL_SIGNAL_ROUTE_ENTRIES)
    assert 'api.telegram.org' in entries
    assert 'discord.com' in entries
    assert 'whatsapp.com' in entries
    assert 'facebook.com' not in entries
    assert 'instagram.com' not in entries
    assert 'youtube.com' not in entries
    assert '64.233.164.188' not in entries
    assert set(service_catalog.TELEGRAM_CALL_SIGNAL_ROUTE_ENTRIES) <= set(service_catalog.TELEGRAM_UNBLOCK_ENTRIES)


def test_ipset_refresh_is_backend_aware_and_atomic():
    script = (ROOT / 'script.sh').read_text(encoding='utf-8')
    bootstrap = (ROOT / 'bootstrap' / 'install.sh').read_text(encoding='utf-8')
    bot_source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    installer_source = (APP_ROOT / 'installer.py').read_text(encoding='utf-8')
    update_script = (APP_ROOT / 'unblock_update.sh').read_text(encoding='utf-8')
    unblock_dnsmasq = (APP_ROOT / 'unblock.dnsmasq').read_text(encoding='utf-8')
    ipset_script = (APP_ROOT / 'unblock_ipset.sh').read_text(encoding='utf-8')
    ipset_boot_script = (APP_ROOT / '100-ipset.sh').read_text(encoding='utf-8')
    redirect_script = (APP_ROOT / '100-redirect.sh').read_text(encoding='utf-8')
    crontab = (APP_ROOT / 'crontab').read_text(encoding='utf-8')
    s99unblock = (APP_ROOT / 'S99unblock').read_text(encoding='utf-8')

    assert 'flush_set' not in update_script
    assert 'Use DNS Override ON button to make dnsmasq the primary DNS' in update_script
    assert 'Using Keenetic ndnproxy fallback, preloading ipset' in update_script
    assert '/opt/bin/unblock_ipset.sh &' not in update_script
    assert 'download_update_file "$(repo_file_url crontab)"' in script
    assert '"$stage_dir/crontab" "S99unblock tick" "crontab"' in script
    assert 'mv "$stage_dir/crontab" /opt/etc/crontab' in script
    assert 'install_unblock_ipset_cron_job()' in script
    assert "grep -v '/opt/bin/unblock_ipset.sh' \\" in script
    assert "grep -v '/opt/etc/init.d/S99unblock refresh' \\" in script
    assert "grep -v '/opt/etc/init.d/S99unblock tick' \\" in script
    assert "grep -v '^# DO NOT EDIT THIS FILE' \\" in script
    assert "grep -v '^# (.* installed on ' \\" in script
    assert "sed '/^[[:space:]]*$/d' || true" in script
    assert "grep -v '^# DO NOT EDIT THIS FILE' \\\\" in bootstrap
    assert "printf '%s\\n' '*/15 * * * * /opt/etc/init.d/S99unblock tick >/dev/null 2>&1'" in script
    assert 'install_unblock_ipset_cron_job || true' in script
    assert 'install_unblock_ipset_cron_job || true' in bootstrap
    assert 'chmod 600 /opt/var/spool/cron/crontabs/root' in script
    assert 'chmod 600 /opt/var/spool/cron/crontabs/root' in bootstrap
    assert '/opt/etc/init.d/S10cron restart' in script
    assert 'download_update_file "$(repo_file_url S99unblock)"' in script
    assert 'mv "$stage_dir/S99unblock" /opt/etc/init.d/S99unblock' in script
    assert '/opt/etc/init.d/S99unblock restart' in script
    assert 'BYPASS_UNBLOCK_REFRESH_INTERVAL_SECONDS:-900' in s99unblock
    assert 'BYPASS_UNBLOCK_DNSMASQ_REFRESH_INTERVAL_SECONDS:-3600' in s99unblock
    assert 'BYPASS_UNBLOCK_REFRESH_STATE_FILE' in s99unblock
    assert 'BYPASS_UNBLOCK_DNSMASQ_FULL_REFRESH_FORCE_INTERVAL_SECONDS:-21600' in s99unblock
    assert 'BYPASS_UNBLOCK_REFRESH_CHECK_INTERVAL_SECONDS:-60' in s99unblock
    assert 'BYPASS_RUNTIME_DEDUPE_INTERVAL_SECONDS:-60' in s99unblock
    assert 'BYPASS_RUNTIME_DEDUPE_LOCK_STALE_SECONDS:-120' in s99unblock
    assert 'BYPASS_VLESS_PRIORITY_REFRESH_INTERVAL_SECONDS:-900' in s99unblock
    assert 'BYPASS_VLESS_PRIORITY_REFRESH_STATE_FILE' in s99unblock
    scheduler_pids_block = s99unblock.split('scheduler_pids() {', 1)[1].split('\n}', 1)[0]
    assert 'S99unblock scheduler' in scheduler_pids_block
    assert 'S99unblock start' not in scheduler_pids_block
    assert 'S99unblock restart' not in scheduler_pids_block
    assert 'apply_vless_priority_domain_ips_if_due()' in s99unblock
    assert 'priority_refresh_due()' in s99unblock
    assert 'dedupe_vless_priority_overlaps()' in s99unblock
    assert 'remove_runtime_overlap_from_set "unblockvlesspriority" "unblockvless2udp"' in s99unblock
    assert 'YOUTUBE_EDGE_PREFETCH_INTERVAL_SECONDS="${YOUTUBE_EDGE_PREFETCH_INTERVAL_SECONDS:-0}"' in s99unblock
    assert 'YOUTUBE_EDGE_PREFETCH_RETRY_SECONDS="${YOUTUBE_EDGE_PREFETCH_RETRY_SECONDS:-180}"' in s99unblock
    assert 'APP_RUNTIME_MODE_FILE="${APP_RUNTIME_MODE_FILE:-/opt/etc/bot_app_mode}"' in s99unblock
    assert 'dedupe_lock_pid_is_active()' in s99unblock
    assert 'dedupe_lock_age_seconds()' in s99unblock
    assert 'youtube_edge_prefetch_skipped_reason()' in s99unblock
    assert '[ "$skipped_reason" = "low_available_memory" ]' in s99unblock
    assert 'refresh_skip_allowed()' in s99unblock
    assert 'refresh_effective_updated_at()' in s99unblock
    assert 'mark_refresh_state()' in s99unblock
    assert 'run_refresh_if_due()' in s99unblock
    assert 'run_refresh_if_check_due()' in s99unblock
    assert 'run_youtube_edge_prefetch_if_due()' in s99unblock
    assert 'base_interval="$YOUTUBE_EDGE_PREFETCH_INTERVAL_SECONDS"' in s99unblock
    assert 'case "$trigger" in' in s99unblock
    assert "scheduler|'') youtube_edge_prefetch_due || return 0 ;;" in s99unblock
    assert '\'\'|*[!0-9]*|0) return 1 ;;' in s99unblock
    assert '\'\'|*[!0-9]*|0) interval="$base_interval" ;;' in s99unblock
    assert 'youtube_edge_prefetch_background_busy()' in s99unblock
    assert 'YOUTUBE_EDGE_PREFETCH_AFTER_REFRESH_DELAY_SECONDS="${YOUTUBE_EDGE_PREFETCH_AFTER_REFRESH_DELAY_SECONDS:-120}"' in s99unblock
    assert 'youtube_edge_prefetch_recent_refresh_busy()' in s99unblock
    assert 'PARALLEL_JOBS="${UNBLOCK_IPSET_PARALLEL_JOBS:-4}"' in s99unblock
    assert 'IPV6_RESOLVE_ENABLED="${UNBLOCK_IPSET_IPV6_RESOLVE_ENABLED:-auto}"' in s99unblock
    assert 'youtube_edge_prefetch_runtime_allowed()' in s99unblock
    assert '[ "$(app_runtime_mode_value)" != "simple" ]' in s99unblock
    assert 'YOUTUBE_EDGE_PREFETCH_RUNNER="${YOUTUBE_EDGE_PREFETCH_RUNNER:-/opt/etc/bot/youtube_edge_prefetch_runner.py}"' in s99unblock
    assert 'PYTHONPATH="/opt/etc/bot" "$python_bin" "$YOUTUBE_EDGE_PREFETCH_RUNNER" --trigger "$trigger"' in s99unblock
    assert 'UNBLOCK_IPSET_LOCK_DIR="${UNBLOCK_IPSET_LOCK_DIR:-/tmp/bypass-unblock-ipset.lock}"' in s99unblock
    assert 'UNBLOCK_IPSET_LOCK_STALE_SECONDS="${UNBLOCK_IPSET_LOCK_STALE_SECONDS:-600}"' in s99unblock
    assert 'unblock_ipset_running()' in s99unblock
    assert 'unblock_ipset_running && return 0' in s99unblock
    assert 'UNBLOCK_IPSET_LOCK_BUSY_QUIET=1 /opt/bin/unblock_ipset.sh >> "$LOG_FILE" 2>&1 || true' in s99unblock
    assert 'last_refresh_check=0' in s99unblock
    assert 'refresh)' in s99unblock
    refresh_case = s99unblock.split('\n    refresh)\n', 1)[1].split(';;', 1)[0]
    assert 'if is_running' not in refresh_case
    assert 'run_refresh force' in refresh_case
    assert 'run_youtube_edge_prefetch_if_due "manual-refresh"' in refresh_case
    assert 'run_refresh_if_due' not in refresh_case
    assert 'tick)' in s99unblock
    assert 'run_tick()' in s99unblock
    tick_case = s99unblock.split('\n    tick)\n', 1)[1].split(';;', 1)[0]
    assert 'run_tick' in tick_case
    tick_body = s99unblock.split('run_tick() {', 1)[1].split('\n}', 1)[0]
    assert 'if ! is_running' in tick_body
    assert 'start_scheduler' in tick_body
    assert 'run_refresh_if_due' in tick_body
    assert 'while :' in s99unblock
    assert 'scheduler_pids()' in s99unblock
    assert 'run_scheduler_loop()' in s99unblock
    assert '"/opt/etc/init.d/S99unblock scheduler"' in s99unblock
    assert '"$0" scheduler &' in s99unblock
    assert 'cleanup_orphan_schedulers' in s99unblock
    assert 'stop_scheduler_pid "$pid"' in s99unblock
    assert 'run_service_runtime_dedupe()' in s99unblock
    assert 'cleanup_runtime_service_route_intersections' in s99unblock
    assert 'run_service_runtime_dedupe' in s99unblock
    assert 'VLESS_PRIORITY_DOMAINS="${VLESS_PRIORITY_DOMAINS:-remotedesktop.google.com' in s99unblock
    assert 'ROUTE_IPSET_SIGNATURE_SETS="${ROUTE_IPSET_SIGNATURE_SETS:-unblocksh unblockshudp unblocksh6' in s99unblock
    assert 'accounts.google.com oauth2.googleapis.com www.googleapis.com apis.google.com' in s99unblock
    assert 'clients2.google.com clients3.google.com clients4.google.com clients6.google.com' in s99unblock
    assert 'fonts.googleapis.com fonts.gstatic.com www.googletagmanager.com' in s99unblock
    assert 'YOUTUBE_ROUTE_PRIORITY_DOMAINS="${YOUTUBE_ROUTE_PRIORITY_DOMAINS:-youtube.com www.youtube.com' in s99unblock
    assert 'youtu.be youtube-nocookie.com youtube.googleapis.com' in s99unblock
    assert 'googlevideo.com manifest.googlevideo.com redirector.googlevideo.com c.youtube.com' in s99unblock
    assert 'ytimg.com i.ytimg.com s.ytimg.com ggpht.com yt3.ggpht.com gvt1.com' in s99unblock
    assert 'domain_in_list "$YOUTUBE_ROUTE_PRIORITY_DOMAINS" "$priority_domain"' in s99unblock
    assert 'force_youtube_route=1' in s99unblock
    assert 'youtube_route="$(youtube_route_protocol)"\n    for priority_domain in $VLESS_PRIORITY_DOMAINS; do' in s99unblock
    assert 'rutracker.org feed.rutracker.cc rutracker.wiki static.rutracker.cc' in s99unblock
    assert 'apply_vless_priority_domain_ips' in s99unblock
    assert 'route_file_signature()' in s99unblock
    assert 'portable_stream_signature()' in s99unblock
    assert 'ipset_members_signature()' in s99unblock
    assert 'runtime_ipset_save_signature()' in s99unblock
    assert 'runtime_ipset_signature()' in s99unblock
    assert 'runtime_ipsets=$(runtime_ipset_signature)' in s99unblock
    assert 'ipset save 2>/dev/null | awk' in s99unblock
    assert 'sha256sum 2>/dev/null | awk' in s99unblock
    assert 'wc -c < "$route_file"' in s99unblock
    assert 'from youtube_route_owner import youtube_route_owner' in s99unblock
    assert 'YOUTUBE_ROUTE_PROTOCOL_CACHE' in s99unblock
    assert 'RUNTIME_DEDUPE_STATE_FILE="${BYPASS_RUNTIME_DEDUPE_STATE_FILE:-/tmp/bypass-runtime-dedupe.state}"' in s99unblock
    assert 'DEDUP_FORCE_INTERVAL_SECONDS="${BYPASS_RUNTIME_DEDUPE_FORCE_INTERVAL_SECONDS:-900}"' in s99unblock
    assert '"$UNBLOCK_DIR/shadowsocks.txt"' in s99unblock
    assert '"$UNBLOCK_DIR/trojan.txt"' in s99unblock
    assert 'runtime_dedupe_due()' in s99unblock
    assert 'mark_runtime_dedupe_done' in s99unblock
    assert 'acquire_runtime_dedupe_lock || return 0' in s99unblock
    assert '*unblock_ipset.sh*) continue ;;' in s99unblock
    assert 'dedupe_vless_final_ipsets()' in ipset_script
    assert 'from youtube_route_owner import youtube_route_owner' in ipset_script
    assert 'YOUTUBE_ROUTE_PROTOCOL_CACHE' in ipset_script
    assert 'LOCK_BUSY_QUIET="${UNBLOCK_IPSET_LOCK_BUSY_QUIET:-0}"' in ipset_script
    assert 'lock_busy_exit()' in ipset_script
    assert 'remove_runtime_overlap_from_set "unblockvless" "unblockvless2"' in ipset_script
    assert 'remove_runtime_overlap_from_set "unblockvless2" "unblockvless"' in ipset_script
    assert 'remove_runtime_overlap_from_set "unblockvlesspriority" "unblockvless2udp"' in ipset_script
    assert 'remove_runtime_overlap_from_set "unblockvless2priority" "unblockvlessudp"' in ipset_script
    assert 'VLESS_PRIORITY_DOMAINS="${VLESS_PRIORITY_DOMAINS:-remotedesktop.google.com' in ipset_script
    assert 'accounts.google.com oauth2.googleapis.com www.googleapis.com apis.google.com' in ipset_script
    assert 'clients2.google.com clients3.google.com clients4.google.com clients6.google.com' in ipset_script
    assert 'fonts.googleapis.com fonts.gstatic.com www.googletagmanager.com' in ipset_script
    assert 'YOUTUBE_ROUTE_PRIORITY_DOMAINS="${YOUTUBE_ROUTE_PRIORITY_DOMAINS:-youtube.com www.youtube.com' in ipset_script
    assert 'youtu.be youtube-nocookie.com youtube.googleapis.com' in ipset_script
    assert 'googlevideo.com manifest.googlevideo.com redirector.googlevideo.com c.youtube.com' in ipset_script
    assert 'ytimg.com i.ytimg.com s.ytimg.com ggpht.com yt3.ggpht.com gvt1.com' in ipset_script
    assert 'domain_in_list "$YOUTUBE_ROUTE_PRIORITY_DOMAINS" "$priority_domain"' in ipset_script
    assert 'force_youtube_route=1' in ipset_script
    assert 'youtube_route="$(youtube_route_protocol)"\n\tfor priority_domain in $VLESS_PRIORITY_DOMAINS; do' in ipset_script
    assert 'youtube.com www.youtube.com m.youtube.com youtu.be' in ipset_script
    assert 'rutracker.org feed.rutracker.cc rutracker.wiki static.rutracker.cc' in ipset_script
    assert 'apply_vless_priority_domain_ips unblockvless unblockvless2 unblockvless6 unblockvless2v6' in ipset_script
    last_swap_idx = ipset_script.index('swap_or_preserve_set unblocktroj6')
    final_dedupe_call_idx = ipset_script.index('dedupe_vless_final_ipsets', last_swap_idx)
    priority_call_idx = ipset_script.index(
        'apply_vless_priority_domain_ips unblockvless unblockvless2 unblockvless6 unblockvless2v6',
        final_dedupe_call_idx,
    )
    post_priority_dedupe_call_idx = ipset_script.index('dedupe_vless_final_ipsets', priority_call_idx)
    assert last_swap_idx < final_dedupe_call_idx < priority_call_idx < post_priority_dedupe_call_idx
    route_log_call_idx = ipset_script.index('log_youtube_route_ipset_counts', post_priority_dedupe_call_idx)
    assert 'IPSET_ROUTE_LOG_FILE="${IPSET_ROUTE_LOG_FILE:-/opt/var/log/bypass-ipset-route.log}"' in ipset_script
    assert 'youtube_route=%s ipset_main=%s ipset_udp=%s ipset_priority=%s' in ipset_script
    assert post_priority_dedupe_call_idx < route_log_call_idx
    assert 'run_update_ipset_refresh()' in script
    assert 'UPDATE_IPSET_REFRESH_TIMEOUT_SECONDS:-75' in script
    assert 'continuing update while refresh finishes in background' in script
    assert 'run_update_ipset_refresh "Post-update"' in script
    assert 'run_youtube_edge_prefetch_once "Post-install"' in script
    assert 'run_youtube_edge_prefetch_once "Post-update"' in script
    assert 'youtube_edge_prefetch_skipped_reason()' in script
    assert 'run_youtube_edge_prefetch_retry_if_skipped()' in script
    assert 'low_available_memory|lock_busy|unblock_running|pool_probe_running)' in script
    assert 'run_youtube_edge_prefetch_retry_if_skipped "Post-update-late" 90' in script
    assert "Key apply: protocol={proto} verify={int(bool(verify))} duration_ms={duration_ms}" in bot_source
    key_apply_log_idx = bot_source.index('Key apply: protocol={proto}')
    assert 'key_value' not in bot_source[key_apply_log_idx:key_apply_log_idx + 180]
    assert 'def youtube_edge_prefetch_shell(trigger):' in installer_source
    assert 'switch_to_main_bot(run_youtube_prefetch=True)' in installer_source
    assert 'YOUTUBE_EDGE_PREFETCH_RUNNER} --trigger "{safe_trigger}"' in installer_source
    assert '/opt/bin/unblock_update.sh >/dev/null 2>&1 || true' in bootstrap
    assert "'/opt/bin/unblock_update.sh'" in bot_source
    assert 'def _refresh_dns_override_runtime(restart_dnsmasq=False)' in bot_source
    assert "['/opt/etc/init.d/S56dnsmasq', 'restart']" in bot_source
    assert bot_source.count('_refresh_dns_override_runtime(restart_dnsmasq=True)') == 2
    assert bot_source.count('_refresh_dns_override_runtime(restart_dnsmasq=False)') == 2
    assert bot_source.find("ndmc -c 'opkg dns-override'") < bot_source.find('_refresh_dns_override_runtime(restart_dnsmasq=True)', bot_source.find("ndmc -c 'opkg dns-override'"))
    assert bot_source.find("ndmc -c 'no opkg dns-override'") < bot_source.find('_refresh_dns_override_runtime(restart_dnsmasq=False)', bot_source.find("ndmc -c 'no opkg dns-override'"))
    reboot_block = script.split('if [ "$1" = "-reboot" ]; then', 1)[1].split('fi', 1)[0]
    assert "opkg dns-override" not in reboot_block
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
    assert 'from service_catalog import REALTIME_CALL_SIGNAL_ROUTE_ENTRIES, TELEGRAM_CALL_SIGNAL_ROUTE_ENTRIES, YOUTUBE_UNBLOCK_ENTRIES' in script
    assert 'from service_catalog import REALTIME_CALL_SIGNAL_ROUTE_ENTRIES, TELEGRAM_CALL_SIGNAL_ROUTE_ENTRIES, YOUTUBE_UNBLOCK_ENTRIES' in bootstrap
    assert 'def telegram_udp_policy()' in script
    assert 'def telegram_udp_policy()' in bootstrap
    assert 'route_contains_telegram(filename)' in script
    assert 'route_contains_telegram(filename)' in bootstrap
    assert 'route_contains_youtube(filename)' in script
    assert 'route_contains_youtube(filename)' in bootstrap
    assert "('VLESS', 'vless.txt', 'udp_quic_block_vless_enabled')" in script
    assert "('VLESS2', 'vless-2.txt', 'udp_quic_block_vless2_enabled')" in script
    assert "print(f'BYPASS_UDP_QUIC_BLOCK_{env_name}={1 if enabled else 0}')" in script
    assert "BYPASS_TELEGRAM_CALL_LEARNING_ENABLED" in script
    assert "BYPASS_TELEGRAM_CALL_ROUTE_{env_name}" in script
    assert "BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_{env_name}" in script
    assert "BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT" in script
    assert "BYPASS_TELEGRAM_CALL_ADDRESS_TIMEOUT" in script
    assert "BYPASS_TELEGRAM_CALL_TPROXY_ENABLED" in script
    assert "TELEGRAM_CALL_TPROXY_PORT_VLESS" in script
    assert "TELEGRAM_CALL_TPROXY_PORT_VLESS2" in bootstrap
    service_routes_source = (APP_ROOT / 'service_routes.py').read_text(encoding='utf-8')
    assert 'def repair_service_route_catalog_drift(' in service_routes_source
    assert 'update_script=UNBLOCK_UPDATE_SCRIPT' in service_routes_source
    assert 'ensure_runtime_legacy_paths\n    generate_udp_quic_policy_file' in script
    assert 'migrate_runtime_config_defaults\n    generate_udp_quic_policy_file\n    repair_service_route_catalog_drift' in script
    assert 'Service route catalog repaired:' in script
    assert script.count('repair_service_route_catalog_drift') == 3
    assert bootstrap.count('repair_service_route_catalog_drift') == 0

    for script_path in (ROOT / 'script.sh', ROOT / 'bootstrap' / 'install.sh'):
        auto_policy = _run_udp_policy_python(script_path, 'auto')
        allow_policy = _run_udp_policy_python(script_path, 'allow')
        block_policy = _run_udp_policy_python(script_path, 'block')
        legacy_disabled_policy = _run_udp_policy_python(script_path, 'auto', vless2_quic_enabled=False)
        assert auto_policy['BYPASS_UDP_QUIC_BLOCK_VLESS2'] == '1'
        assert allow_policy['BYPASS_UDP_QUIC_BLOCK_VLESS2'] == '0'
        assert block_policy['BYPASS_UDP_QUIC_BLOCK_VLESS2'] == '1'
        assert legacy_disabled_policy['BYPASS_UDP_QUIC_BLOCK_VLESS2'] == '1'
        assert auto_policy['BYPASS_UDP_QUIC_BLOCK_VLESS'] == '1'
        assert block_policy['BYPASS_IPV6_FALLBACK_ENABLED'] == '1'
        vless_auto_policy = _run_udp_policy_python(script_path, 'auto', youtube_route='vless.txt')
        vless_block_policy = _run_udp_policy_python(script_path, 'block', youtube_route='vless.txt')
        telegram_auto_policy = _run_udp_policy_python(script_path, 'block', telegram_route='vless.txt')
        telegram_block_policy = _run_udp_policy_python(
            script_path,
            'auto',
            youtube_route='',
            telegram_route='vless.txt',
            telegram_policy='block',
        )
        combined_policy = _run_udp_policy_python(
            script_path,
            'block',
            youtube_route='vless.txt',
            telegram_route='vless.txt',
            telegram_policy='auto',
        )
        combined_auto_policy = _run_udp_policy_python(
            script_path,
            'auto',
            youtube_route='vless.txt',
            telegram_route='vless.txt',
            telegram_policy='auto',
        )
        assert vless_auto_policy['BYPASS_UDP_QUIC_BLOCK_VLESS'] == '1'
        assert vless_auto_policy['BYPASS_UDP_QUIC_BLOCK_VLESS2'] == '1'
        assert vless_block_policy['BYPASS_UDP_QUIC_BLOCK_VLESS'] == '1'
        assert telegram_auto_policy['BYPASS_UDP_QUIC_BLOCK_VLESS'] == '0'
        assert telegram_block_policy['BYPASS_UDP_QUIC_BLOCK_VLESS'] == '1'
        assert combined_policy['BYPASS_UDP_QUIC_BLOCK_VLESS'] == '1'
        assert combined_auto_policy['BYPASS_UDP_QUIC_BLOCK_VLESS'] == '1'
        assert auto_policy['BYPASS_TELEGRAM_CALL_LEARNING_ENABLED'] == '1'
        assert auto_policy['BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT'] == '900'
        assert auto_policy['BYPASS_TELEGRAM_CALL_ADDRESS_TIMEOUT'] == '14400'
        assert auto_policy['BYPASS_TELEGRAM_CALL_TPROXY_ENABLED'] == '1'
        assert auto_policy['BYPASS_TELEGRAM_CALL_CLIENT_UDP_ROUTE_ENABLED'] == '0'
        assert auto_policy['TELEGRAM_CALL_TPROXY_PORT_VLESS'] == '11812'
        assert auto_policy['TELEGRAM_CALL_TPROXY_PORT_VLESS2'] == '11814'
        assert auto_policy['BYPASS_TELEGRAM_CALL_ROUTE_VLESS2'] == '0'
        assert telegram_auto_policy['BYPASS_TELEGRAM_CALL_ROUTE_VLESS'] == '1'
        assert telegram_auto_policy['BYPASS_TELEGRAM_CALL_ROUTE_VLESS2'] == '0'
        assert combined_policy['BYPASS_TELEGRAM_CALL_ROUTE_VLESS'] == '1'
        vless2_telegram_policy = _run_udp_policy_python(script_path, 'auto', telegram_route='vless-2.txt')
        vmess_telegram_policy = _run_udp_policy_python(script_path, 'auto', telegram_route='vmess.txt')
        vless2_discord_policy = _run_udp_policy_python(script_path, 'auto', realtime_call_route='vless-2.txt')
        assert vless2_telegram_policy['BYPASS_TELEGRAM_CALL_ROUTE_VLESS2'] == '1'
        assert vless2_discord_policy['BYPASS_TELEGRAM_CALL_ROUTE_VLESS2'] == '1'
        assert vless2_discord_policy['BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_VLESS2'] == '0'
        assert vmess_telegram_policy['BYPASS_TELEGRAM_CALL_ROUTE_VMESS'] == '1'

    assert 'LOCK_DIR="${LOCK_DIR:-/tmp/bypass-unblock-ipset.lock}"' in ipset_script
    assert 'LOCK_STALE_SECONDS="${LOCK_STALE_SECONDS:-900}"' in ipset_script
    assert 'PARALLEL_JOBS="${PARALLEL_JOBS:-4}"' in ipset_script
    assert 'IPV6_RESOLVE_ENABLED="${IPV6_RESOLVE_ENABLED:-auto}"' in ipset_script
    assert 'IPV6_ACTIVE_CONNTRACK_TEST_LIMIT="${IPV6_ACTIVE_CONNTRACK_TEST_LIMIT:-128}"' in ipset_script
    assert 'collect_active_ipv6_addresses()' in ipset_script
    assert 'active_ipv6_route_in_sets()' in ipset_script
    assert 'ipv6_resolve_should_run()' in ipset_script
    assert 'ipset test "$current_ipv6_set" "$active_ipv6"' in ipset_script
    assert 'ipv6_resolve_should_run || return 0' in ipset_script
    assert 'lock_pid_is_active()' in ipset_script
    assert 'lock_pid_is_unblock_refresh()' in ipset_script
    assert 'stop_stale_lock_process()' in ipset_script
    assert 'recover_existing_lock()' in ipset_script
    assert 'Stopped stale unblock_ipset process pid' in ipset_script
    assert 'cleanup_stale_tmp_unblock_sets' in ipset_script
    assert "grep '^tmp_unblock'" in ipset_script
    assert 'ipset_references "$stale_set"' in ipset_script
    assert 'Removed stale unblock_ipset lock with non-refresh pid' in ipset_script
    assert 'Removed stale unblock_ipset lock without active pid' in ipset_script
    assert 'Removed stale unblock_ipset lock' in ipset_script
    assert 'printf \'%s\\n\' "$$" > "$LOCK_DIR/pid"' in ipset_script
    assert 'rm -f "$LOCK_DIR/pid" "$LOCK_DIR/started_at"' in ipset_script
    assert 'mkdir -p "$tmp_dir" || {\n\trm -f "$LOCK_DIR/pid" "$LOCK_DIR/started_at"' in ipset_script
    assert 'STATUS_FILE="${IPSET_STATUS_FILE:-/opt/tmp/bypass_ipset_status.json}"' in ipset_script
    assert 'DNS_WAIT_SECONDS="${DNS_WAIT_SECONDS:-60}"' in ipset_script
    assert 'for set_name in $SET_NAMES $EXTRA_SET_NAMES; do' in ipset_script
    assert 'ipset swap "$swap_tmp_set" "$set_name"' in ipset_script
    assert 'ipset save "$set_name" > "$tmp_dir/${set_name}.backup"' in ipset_script
    assert 'ipset flush "$set_name"' in ipset_script
    assert 'reloaded via flush/restore fallback' in ipset_script
    assert 'unblockshudp "tmp_unblockshudp_$$"' in ipset_script
    assert 'unblockvmessudp "tmp_unblockvmessudp_$$"' in ipset_script
    assert 'unblockvlessudp "tmp_unblockvlessudp_$$"' in ipset_script
    assert 'unblockvless2udp "tmp_unblockvless2udp_$$"' in ipset_script
    assert 'unblocktrojudp "tmp_unblocktrojudp_$$"' in ipset_script
    assert 'resolve_ipv6_domains "$ipv6_tmp_set" "$domain_file"' in ipset_script
    assert 'unblockvless6 "tmp_unblockvless6_$$"' in ipset_script
    assert 'unblockvless2v6 "tmp_unblockvless2v6_$$"' in ipset_script
    assert 'udp_quic_domain "$domain"' in ipset_script
    assert 'connectivity_check_domain "$domain" && continue' in ipset_script
    assert 'udp_quic_direct_entry "$direct_entry"' in ipset_script
    assert 'extract_ipv6_direct_entry()' in ipset_script
    assert 'append_restore "$ipv6_tmp_set" "$direct_ipv6_entry"' in ipset_script
    assert 'entry ~ /^[0-9.]+(\\/[0-9]+)?$/' in ipset_script
    assert 'UDP_QUIC_POLICY_FILE="${UDP_QUIC_POLICY_FILE:-/opt/etc/bot/udp_quic_routes.txt}"' in ipset_script
    assert 'UDP_QUIC_EXCLUDE_FILE="${UDP_QUIC_EXCLUDE_FILE:-/opt/etc/bot/udp_quic_exclude.txt}"' in ipset_script
    assert 'from service_catalog import UDP_QUIC_ROUTE_ENTRIES' in ipset_script
    assert 'from service_catalog import UDP_QUIC_EXCLUDE_ENTRIES' in ipset_script
    assert 'YOUTUBE_DNS_SAMPLE_SERVERS="${YOUTUBE_DNS_SAMPLE_SERVERS:-8.8.8.8 8.8.4.4 1.1.1.1 9.9.9.9}"' in ipset_script
    assert 'for sample_dns in $extra_dns_servers; do' in ipset_script
    assert 'dig +time=2 +tries=1 +short "$domain" @"$DNS_HOST" -p "$DNS_PORT"' in ipset_script
    assert 'dig +time=2 +tries=1 +short AAAA "$domain" @"$DNS_HOST" -p "$DNS_PORT"' in ipset_script
    assert "tr -d '\\r' < \"$route_file\" | grep -Fxs \"$marker\"" in ipset_script
    assert 'YOUTUBE_VIDEO_PRELOAD' not in ipset_script
    assert 'preload_youtube_video_hosts' not in ipset_script
    assert '--socks5-hostname "127.0.0.1:$socks_port"' not in ipset_script
    assert 'function cidr64(ip, parts, net)' in ipset_script
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
    assert 'ipset create unblockvlesspriority hash:net -exist' in ipset_boot_script
    assert 'ipset create unblockvlessudp hash:net -exist' in ipset_boot_script
    assert 'ipset create unblockvless2priority hash:net -exist' in ipset_boot_script
    assert 'ipset create unblockvless2udp hash:net -exist' in ipset_boot_script
    assert 'ipset create unblocktrojudp hash:net -exist' in ipset_boot_script
    assert 'ipset create unblockvless6 hash:net family inet6 -exist' in ipset_boot_script
    assert 'ipset create unblockvlesspriority6 hash:net family inet6 -exist' in ipset_boot_script
    assert 'ipset create unblockvless2v6 hash:net family inet6 -exist' in ipset_boot_script
    assert 'ipset create unblockvless2priority6 hash:net family inet6 -exist' in ipset_boot_script
    assert 'UDP_QUIC_REJECT_PORT="${UDP_QUIC_REJECT_PORT:-10944}"' in redirect_script
    assert 'install_udp_quic_block_rule unblockshudp "$BYPASS_UDP_QUIC_BLOCK_SHADOWSOCKS"' in redirect_script
    assert 'install_udp_quic_block_rule unblockvmessudp "$BYPASS_UDP_QUIC_BLOCK_VMESS"' in redirect_script
    assert 'install_udp_quic_block_rule unblockvlessudp "$BYPASS_UDP_QUIC_BLOCK_VLESS"' in redirect_script
    assert 'install_udp_quic_block_rule unblockvless2udp "$BYPASS_UDP_QUIC_BLOCK_VLESS2"' in redirect_script
    assert 'install_udp_quic_block_rule unblocktrojudp "$BYPASS_UDP_QUIC_BLOCK_TROJAN"' in redirect_script
    assert '--match-set "$set_name" dst -m udp --dport 443 -j REDIRECT --to-ports "$UDP_QUIC_REJECT_PORT"' in redirect_script
    assert 'BYPASS_TELEGRAM_CALL_LEARNING_ENABLED="${BYPASS_TELEGRAM_CALL_LEARNING_ENABLED:-0}"' in redirect_script
    assert 'BYPASS_TELEGRAM_CALL_CLIENT_UDP_ROUTE_ENABLED="${BYPASS_TELEGRAM_CALL_CLIENT_UDP_ROUTE_ENABLED:-0}"' in redirect_script
    assert 'TELEGRAM_CALL_CLIENT_SET="${TELEGRAM_CALL_CLIENT_SET:-bypass_tg_call_clients}"' in redirect_script
    assert 'TELEGRAM_CALL_SIGNAL_SET="${TELEGRAM_CALL_SIGNAL_SET:-bypass_tg_call_signal}"' in redirect_script
    assert 'CALL_CLIENT_SET_VLESS="${CALL_CLIENT_SET_VLESS:-bypass_call_clients_vless}"' in redirect_script
    assert 'CALL_SIGNAL_SET_VLESS2="${CALL_SIGNAL_SET_VLESS2:-bypass_call_signal_vless2}"' in redirect_script
    assert 'TELEGRAM_CALL_TPROXY_CHAIN="${TELEGRAM_CALL_TPROXY_CHAIN:-BYPASS_TG_CALL_TPROXY}"' in redirect_script
    assert 'BYPASS_TELEGRAM_CALL_TPROXY_ENABLED="${BYPASS_TELEGRAM_CALL_TPROXY_ENABLED:-0}"' in redirect_script
    assert 'load_tproxy_module xt_TPROXY' in redirect_script
    assert 'load_tproxy_module xt_socket' in redirect_script
    assert 'ip rule add fwmark "$BYPASS_TELEGRAM_CALL_TPROXY_MARK"' in redirect_script
    assert 'ip route add local 0.0.0.0/0 dev lo table "$BYPASS_TELEGRAM_CALL_TPROXY_TABLE"' in redirect_script
    assert 'refresh_telegram_call_learning_rules()' in redirect_script
    assert 'refresh_telegram_call_signal_set()' in redirect_script
    assert 'BYPASS_TG_CALL_LEARN' in redirect_script
    assert 'BYPASS_TG_CALL_ROUTE' in redirect_script
    assert 'BYPASS_TG_CALL_TPROXY' in redirect_script
    assert 'ipset create "$set_name" hash:ip timeout "$timeout_value" maxelem "$maxelem" -exist' in redirect_script
    assert 'current_timeout="$(' in redirect_script
    assert 'ipset create "$TELEGRAM_CALL_SIGNAL_SET" hash:net -exist' in redirect_script
    assert 'ipset create "$signal_set" hash:net -exist' in redirect_script
    assert 'ensure_timeout_ipset "$client_set" "$BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT" 64' in redirect_script
    assert '149.154.160.0/20' in redirect_script
    assert '--match-set "$signal_set" dst --dport "$signal_port"' in redirect_script
    assert 'iptables -t mangle -I PREROUTING -p udp -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN"' in redirect_script
    assert '-p tcp -m tcp --dport "$signal_port" -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN"' in redirect_script
    assert 'telegram_call_client_udp_ports()' in redirect_script
    assert 'Client-wide UDP routing is intentionally disabled' in redirect_script
    assert 'telegram_call_client_udp_cleanup_ports()' in redirect_script
    assert "printf '%s\\n' 443 1024:65535" in redirect_script
    assert 'telegram_call_known_route_sets()' in redirect_script
    assert 'unblockvless2udp' in redirect_script
    assert 'telegram_call_ipset_has_entries()' in redirect_script
    assert 'telegram_call_chains_installed()' in redirect_script
    assert 'REDIRECT_LOCK_STALE_SECONDS="${REDIRECT_LOCK_STALE_SECONDS:-120}"' in redirect_script
    assert 'REDIRECT_LOCK_DIR="${REDIRECT_LOCK_DIR:-/tmp/bypass-redirect-${type:-iptables}-${table:-unknown}.lock}"' in redirect_script
    assert 'if telegram_call_ipset_has_entries "$TELEGRAM_CALL_CLIENT_SET" && telegram_call_chains_installed; then' not in redirect_script
    assert 'telegram_call_mangle_tproxy_insert_index()' in redirect_script
    assert 'install_telegram_call_tproxy_prerouting_rule()' in redirect_script
    assert 'iptables -t mangle -I PREROUTING "$insert_index" "$@"' in redirect_script
    assert 'iptables -t mangle -A PREROUTING -p udp -m set --match-set "$learned_set" dst -j "$TELEGRAM_CALL_TPROXY_CHAIN"' not in redirect_script
    assert 'for client_udp_port in $(telegram_call_client_udp_cleanup_ports); do' in redirect_script
    assert '-p udp -m set --match-set "$learned_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN"' in redirect_script
    active_call_prerouting = redirect_script.split('install_telegram_call_prerouting_jumps() {', 1)[1].split('\n}', 1)[0]
    assert '-p udp -m udp --dport "$client_udp_port" -m set --match-set "$TELEGRAM_CALL_CLIENT_SET" src -j "$TELEGRAM_CALL_LEARN_CHAIN"' not in active_call_prerouting
    assert 'install_telegram_call_tproxy_prerouting_rule -p udp -m udp --dport "$client_udp_port" -m set --match-set "$client_set" src' not in redirect_script
    assert 'iptables -t mangle -A "$TELEGRAM_CALL_TPROXY_CHAIN" -p udp -m udp -m set --match-set "$client_set" src --dport "$client_udp_port"' not in redirect_script
    assert 'iptables -t nat -A "$TELEGRAM_CALL_ROUTE_CHAIN" -p udp -m udp -m set --match-set "$client_set" src --dport "$client_udp_port"' not in redirect_script
    assert 'iptables -t nat -I PREROUTING -p udp -m udp --dport "$client_udp_port" -m set --match-set "$client_set" src' not in redirect_script
    assert 'iptables -t "$table_name" -I PREROUTING -j "$chain_name"' not in redirect_script
    assert 'iptables -t mangle -I PREROUTING -j "$TELEGRAM_CALL_LEARN_CHAIN"' not in redirect_script
    assert 'iptables -t nat -I PREROUTING -j "$TELEGRAM_CALL_ROUTE_CHAIN"' not in redirect_script
    assert '-j SET --add-set "$client_set" src --exist --timeout "$BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT"' in redirect_script
    assert '-j SET --add-set "$learned_set" dst --exist --timeout "$BYPASS_TELEGRAM_CALL_ADDRESS_TIMEOUT"' in redirect_script
    assert 'iptables -t mangle -A "$TELEGRAM_CALL_LEARN_CHAIN" -p udp -m set --match-set "$known_set" dst -j RETURN' in redirect_script
    assert 'iptables -t mangle -A "$TELEGRAM_CALL_TPROXY_CHAIN" -p udp -m set --match-set "$known_set" dst -j RETURN' in redirect_script
    assert 'iptables -t nat -A "$TELEGRAM_CALL_ROUTE_CHAIN" -p udp -m set --match-set "$known_set" dst -j RETURN' in redirect_script
    assert '-m set --match-set "$learned_set" dst \\' in redirect_script
    assert '-j TPROXY --on-port "$tproxy_port" --tproxy-mark "$BYPASS_TELEGRAM_CALL_TPROXY_MARK/$BYPASS_TELEGRAM_CALL_TPROXY_MARK"' in redirect_script
    assert 'iptables -t nat -A "$TELEGRAM_CALL_ROUTE_CHAIN" -p udp -m set --match-set "$learned_set" dst -j REDIRECT --to-ports "$target_port"' in redirect_script
    signal_tproxy = 'iptables -t mangle -A "$TELEGRAM_CALL_TPROXY_CHAIN" -p udp -m set --match-set "$signal_set" dst'
    known_tproxy_return = 'iptables -t mangle -A "$TELEGRAM_CALL_TPROXY_CHAIN" -p udp -m set --match-set "$known_set" dst -j RETURN'
    learned_tproxy = 'iptables -t mangle -A "$TELEGRAM_CALL_TPROXY_CHAIN" -p udp -m set --match-set "$learned_set" dst'
    assert redirect_script.index(signal_tproxy) < redirect_script.index(known_tproxy_return)
    assert redirect_script.index(known_tproxy_return) < redirect_script.index(learned_tproxy)
    assert 'telegram_call_route_enabled "$proto"' in redirect_script
    assert 'vless2) [ -n "$vless2_key_path" ] && printf' in redirect_script
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
    assert 'refresh_vless_priority_redirects()' in redirect_script
    assert '-p tcp -m set --match-set unblockvlesspriority dst -j REDIRECT --to-ports 10812' in redirect_script
    assert '-p tcp -m set --match-set unblockvless2priority dst -j REDIRECT --to-ports 10814' in redirect_script
    assert 'resolved to zero entries, preserving' in ipset_script
    assert '*/15 * * * * root /opt/etc/init.d/S99unblock tick >/dev/null 2>&1' in crontab


def test_vless_tcp_redirect_keeps_mobile_push_connections_reliable():
    redirect_script = (APP_ROOT / '100-redirect.sh').read_text(encoding='utf-8')
    assert 'refresh_vless_tcp_priority()' in redirect_script
    assert 'telegram_route_protocol()' in redirect_script
    assert 'refresh_mobile_push_priority()' in redirect_script
    assert 'remove_vless_tcp_forward_guard()' in redirect_script
    assert 'refresh_vless_priority_redirects()' in redirect_script
    assert 'iptables -I FORWARD -w -p tcp -m set --match-set "$guard_set" dst -j REJECT --reject-with tcp-reset' not in redirect_script
    assert 'Shared Google IPs must follow the YouTube route for video streams.' in redirect_script
    assert 'BYPASS_MOBILE_PUSH_CONNTRACK_MIN_TIMEOUT="${BYPASS_MOBILE_PUSH_CONNTRACK_MIN_TIMEOUT:-3600}"' in redirect_script
    assert 'ensure_mobile_push_conntrack_timeout()' in redirect_script
    assert 'nf_conntrack_tcp_timeout_established' in redirect_script
    assert '[ "$current_timeout" -ge "$desired_timeout" ]' in redirect_script
    vless2_insert = (
        'iptables -I PREROUTING -w -t nat -p tcp -m set --match-set '
        'unblockvless2 dst -j REDIRECT --to-ports 10814'
    )
    vless1_insert = (
        'iptables -I PREROUTING -w -t nat -p tcp -m set --match-set '
        'unblockvless dst -j REDIRECT --to-ports 10812'
    )
    priority_block = redirect_script.split('refresh_vless_tcp_priority() {', 1)[1].split('\n}', 1)[0]
    # iptables -I inserts each rule at the top, so the command emitted last has
    # effective priority in the final chain.
    assert priority_block.index(vless1_insert) < priority_block.index(vless2_insert)
    priority_redirect_block = redirect_script.split('refresh_vless_priority_redirects() {', 1)[1].split('\n}', 1)[0]
    assert 'ipset create unblockvlesspriority hash:net -exist' in priority_redirect_block
    assert 'ipset create unblockvless2priority hash:net -exist' in priority_redirect_block
    assert 'unblockvlesspriority dst -j REDIRECT --to-ports 10812' in priority_redirect_block
    assert 'unblockvless2priority dst -j REDIRECT --to-ports 10814' in priority_redirect_block
    tcp_priority_call = redirect_script.index('\nrefresh_vless_tcp_priority\n')
    service_priority_call = redirect_script.index('\nrefresh_vless_priority_redirects\n')
    assert tcp_priority_call < service_priority_call
    assert 'UNBLOCK_DIR="${UNBLOCK_DIR:-/opt/etc/unblock}"' in redirect_script
    assert 'route_file_marker_count()' in redirect_script
    assert '"shadowsocks:$UNBLOCK_DIR/shadowsocks.txt"' in redirect_script
    assert '"trojan:$UNBLOCK_DIR/trojan.txt"' in redirect_script
    push_block = redirect_script.split('refresh_mobile_push_priority() {', 1)[1].split('\n}', 1)[0]
    assert 'ensure_mobile_push_conntrack_timeout' in push_block
    assert 'for push_port in $(mobile_push_legacy_priority_ports)' in push_block
    assert 'telegram_route="$(telegram_route_protocol)"' in push_block
    assert 'target_port="$(telegram_call_target_port "$telegram_route")"' in push_block
    assert 'for push_set in $(mobile_push_route_sets)' in push_block
    assert 'for stale_port in $(mobile_push_proxy_target_ports)' in push_block
    assert '--dport "$push_port" -j REDIRECT --to-ports "$stale_port"' in push_block
    assert 'for direct_port in $(mobile_push_direct_ports)' in push_block
    assert '--dport "$direct_port" -j RETURN' in push_block
    assert '--dport 5222 -j REDIRECT --to-ports "$target_port"' in push_block
    mobile_priority_call = redirect_script.index('\nrefresh_mobile_push_priority\n')
    call_routes_refresh = redirect_script.index('\nrefresh_telegram_call_learning_rules\n')
    assert call_routes_refresh < mobile_priority_call
    assert mobile_priority_call < redirect_script.index('\nexit 0\n')
    direct_ports = redirect_script.split('mobile_push_direct_ports() {', 1)[1].split('\n}', 1)[0]
    assert "printf '%s\\n' 5223 5228 5229 5230" in direct_ports
    signal_route_refresh = redirect_script.split('refresh_telegram_call_learning_rules() {', 1)[1]
    signal_route_block = signal_route_refresh.split(
        'if [ "$BYPASS_TELEGRAM_CALL_SIGNAL_ROUTE_ENABLED" != "0" ]; then', 1
    )[1].split('\n\t\tfi', 1)[0]
    assert 'if mobile_push_port_is_direct "$signal_port"; then' in signal_route_block
    assert '--dport "$signal_port" -j RETURN' in signal_route_block
    telegram_owner_block = redirect_script.split('telegram_route_protocol() {', 1)[1].split('\n}', 1)[0]
    for route_spec in (
        'shadowsocks:$UNBLOCK_DIR/shadowsocks.txt',
        'vmess:$UNBLOCK_DIR/vmess.txt',
        'vless:$UNBLOCK_DIR/vless.txt',
        'vless2:$UNBLOCK_DIR/vless-2.txt',
        'trojan:$UNBLOCK_DIR/trojan.txt',
    ):
        assert f'"{route_spec}"' in telegram_owner_block
    assert 'route_file_marker_count "$route_file" $telegram_markers' in telegram_owner_block
    assert 'mtalk.google.com' not in telegram_owner_block
    assert '17.249.0.0/16' not in telegram_owner_block
    route_sets = redirect_script.split('mobile_push_route_sets() {', 1)[1].split('\n}', 1)[0]
    assert "printf '%s\\n' unblocksh unblockvmess unblockvless unblockvless2 unblocktroj" in route_sets
    target_ports = redirect_script.split('mobile_push_proxy_target_ports() {', 1)[1].split('\n}', 1)[0]
    assert "printf '%s\\n' 1082 10815 10812 10814 10829" in target_ports


def test_runtime_startup_limits_router_flash_and_overhead():
    service = (APP_ROOT / 'S99telegram_bot').read_text(encoding='utf-8')
    source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    pool_controller_source = (APP_ROOT / 'pool_probe_controller.py').read_text(encoding='utf-8')
    pool_runner_source = (APP_ROOT / 'pool_probe_runner.py').read_text(encoding='utf-8')
    proxy_apply_source = (APP_ROOT / 'proxy_apply_runtime.py').read_text(encoding='utf-8')
    youtube_health_source = (APP_ROOT / 'youtube_healthcheck.py').read_text(encoding='utf-8')
    youtube_source = source + pool_controller_source + pool_runner_source + proxy_apply_source + youtube_health_source
    assert 'PYTHONDONTWRITEBYTECODE=1 python3 "$MAIN_SCRIPT"' in service
    assert 'cleanup_python_bytecode' in service
    assert 'trim_runtime_logs' in service
    assert 'unset BYPASS_KEENETIC_COMMAND_WORKER' in service
    assert 'SERVICE_LOCK_DIR="/tmp/bypass_telegram_bot_service.lock"' in service
    assert 'def release_service_lock' not in service
    assert 'release_service_lock()' in service
    assert 'acquire_service_lock()' in service
    assert 'export BYPASS_BOT_SERVICE_LOCKED=1' in service
    assert 'found=0' in service
    assert 'found=1' in service
    assert 'return 0' not in service.split('check_process() {', 1)[1].split('has_running_process()', 1)[0]
    assert 'threading.stack_size(256 * 1024)' in source
    assert 'subprocess.Popen(' in source
    assert 'bypass-bot-service-restart.log' in source
    assert 'app_service_restart_scheduled = False' in source
    assert 'App mode restart already scheduled' in source
    assert 'sys.modules.pop(module_name, None)' not in source
    assert 'def _unload_pool_probe_modules' not in source
    assert "'Pool probe completed: '" in source
    assert 'post-pool memory restart requested' not in source
    assert "pool_probe_min_available_kb', 160000" in source
    assert "pool_probe_pause_available_kb', min(125000, POOL_PROBE_MIN_AVAILABLE_KB)" in source
    assert 'slow_available_kb=POOL_PROBE_SLOW_AVAILABLE_KB' in source
    assert 'pool_probe_quality_max_samples_per_run' in source
    assert "memory_watchdog_rss_limit_kb', 110 * 1024" in source
    assert 'MEMORY_WATCHDOG_IDLE_RESTART_RSS_KB = 0' in source
    assert "background_task_max_bot_rss_kb', 65 * 1024" in source
    assert "background_task_critical_max_bot_rss_kb', 70 * 1024" in source
    assert "background_task_max_program_rss_kb', 100 * 1024" in source
    assert "background_task_critical_max_program_rss_kb', BACKGROUND_TASK_MAX_PROGRAM_RSS_KB" in source
    assert "background_task_max_cpu_percent', 45.0" in source
    assert 'MEMORY_WATCHDOG_IDLE_RESTART_HOLD_SECONDS = 0.0' in source
    assert "getattr(config, 'router_metrics_history_limit', 120)" in source
    assert "getattr(config, 'router_metrics_warn_bot_rss_kb', 65 * 1024)" in source
    assert "getattr(config, 'router_metrics_compact_cache_ttl', 8.0)" in source
    assert 'router_metrics_compact_cache' in source
    assert 'router_metrics.RouterMetricsRuntime' in source
    assert "'router_metrics_snapshot': _router_metrics_snapshot" in source
    assert 'def _router_health_snapshot(compact=False, sample_cpu=True, force_refresh=False, prime_cpu=False)' in source
    assert '_router_health_snapshot(compact=True, sample_cpu=False)' in source
    assert "'web_pools_payload': _web_pools_payload" in source
    assert 'web_pool_snapshot_worker.py' in source
    assert "input=json.dumps(request" in source
    assert "'route_states': _service_route_summary()" not in source
    assert "memory_timeline_path', '/opt/tmp/bypass_memory_timeline.jsonl'" in source
    assert 'def _record_memory_timeline' in source
    assert 'def _start_memory_timeline_thread' not in source
    assert "_start_background_maintenance_thread()" in source
    assert "getattr(config, 'status_refresh_min_interval_seconds', 180.0)" in source
    assert "getattr(config, 'status_refresh_pending_min_interval_seconds'" in source
    assert 'status_refresh_last_finished_at' in source
    assert 'def _stale_status_snapshot' in source
    assert 'def _sync_udp_policy_config' in source
    assert 'YOUTUBE_UNBLOCK_ENTRIES' in source
    assert 'SERVICE_LIST_SOURCES' in source
    assert 'TELEGRAM_UDP_POLICY' in source
    assert "UDP_QUIC_POLICY_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')" in source
    assert 'def _route_list_contains_telegram' in source
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
    assert 'active_telegram_required = bool(_app_mode_telegram_enabled() and _telegram_required_for_protocol(key_name))' in source
    assert 'authenticated=active_telegram_required' in source
    assert 'def _start_udp_quic_drift_watchdog_thread' not in source
    assert 'UDP_QUIC_DRIFT_SENTINEL_DOMAINS' in source
    assert 'UDP_QUIC_DRIFT_PRIORITY_REFRESH_COOLDOWN_SECONDS' in source
    assert 'UDP_QUIC_DRIFT_PRIORITY_DOMAINS' in source
    assert 'import youtube_edge_prefetch' in source
    assert "getattr(config, 'youtube_edge_prefetch_enabled', True)" in source
    assert "getattr(config, 'youtube_edge_prefetch_mode', 'external')" in source
    assert "getattr(config, 'youtube_edge_prefetch_status_path', '/opt/etc/bot/youtube_edge_prefetch_status.json')" in source
    assert "getattr(config, 'youtube_edge_prefetch_lock_dir', '/tmp/bypass-youtube-edge-prefetch.lock')" in source
    assert "getattr(config, 'youtube_edge_prefetch_max_rss_kb', 65 * 1024)" in source
    assert "getattr(config, 'youtube_edge_prefetch_min_available_kb', 125000)" in source
    assert 'def _start_youtube_edge_prefetch_thread' in source
    assert "if YOUTUBE_EDGE_PREFETCH_MODE != 'thread':" in source
    assert 'def _load_youtube_edge_prefetch_external_status' in source
    assert '_start_youtube_edge_prefetch_thread()' in source
    assert '_youtube_edge_prefetch().prefetch_once(' in source
    assert "_memory_cleanup('youtube edge prefetch skipped high RSS', force=True" in source
    assert "['ipset', 'del', set_name, address]" in source
    assert "payload['youtube_edge_prefetch'] = _youtube_edge_prefetch_snapshot()" in source
    assert 'def _udp_quic_drift_priority_findings' in source
    assert 'def _udp_quic_drift_refresh_cooldown' in source
    assert 'def _udp_quic_drift_refresh_deferred_for_stream' in source
    assert 'def _apply_priority_udp_quic_drift_findings' in source
    assert 'def _delete_conntrack_for_address' in source
    assert "['conntrack', '-D', '-p', proto, direction, address]" in source
    assert "['ipset', 'add', set_name, address, '-exist']" in source
    assert "'udp_quic_drift_fast_add'" in source
    assert 'last_fast_add_signature' in source
    assert "'conntrack_cleared': str(conntrack_deleted)" in source
    assert "if priority_findings and _udp_quic_drift_refresh_deferred_for_stream(priority_findings):" in source
    assert source.find('if priority_findings and _udp_quic_drift_refresh_deferred_for_stream(priority_findings):') < source.find('if _apply_priority_udp_quic_drift_findings(priority_findings):')
    assert "_background_task_allowed('UDP/QUIC drift watchdog', task_class='critical')" in source
    assert "'youtu.be'," in source
    assert "'i.ytimg.com'," in source
    assert "getattr(config, 'ipset_refresh_command_timeout_seconds', 420)" in source
    assert 'timeout=IPSET_REFRESH_COMMAND_TIMEOUT_SECONDS' in source
    assert "subprocess.run(\n            ['/opt/bin/unblock_ipset.sh']" in source
    assert 'stdout=subprocess.PIPE' in source
    assert "'UDP/QUIC drift refresh'" in source
    assert 'UDP/QUIC drift refresh skipped: unblock_ipset is already running.' in source
    assert 'memory_watchdog_high_rss_since' in source
    assert 'memory_watchdog_idle_restart_pending' in source
    assert 'memory_watchdog_idle_restart_in_seconds' in source
    assert 'автоперезапуск уже запрошен' in source
    assert 'Автоперезапуск бота в простое: порог' not in source
    assert 'def _start_memory_watchdog_thread' not in source
    assert 'def _memory_cleanup' in source
    assert "f'{task_name} skipped high RSS'" in source
    assert 'background_task_cpu_cache_ttl_seconds' in source
    assert 'background_cpu_busy_cache' in source
    assert 'background_task_skip_reason = {}' in source
    assert "skip_reason = str(background_task_skip_reason.get(task_name) or '')" in source
    assert 'can_bypass_rss_skip' in source
    assert "task_class in ('critical', 'light')" in source
    assert 'def _program_rss_kb' in source
    assert 'program_rss_kb >= program_limit_kb' in source
    assert "background_task_skip_reason[task_name] = 'program_rss'" in source
    assert "background_task_skip_reason[task_name] = 'cpu'" in source
    assert "'status refresh skipped high RSS'" in source
    assert "_background_task_allowed('YouTube failover', task_class='critical')" in source
    assert 'background_task_coordinator_lock = threading.Lock()' in source
    assert 'def _run_coordinated_background_task(task_name, callback):' in source
    assert "_run_coordinated_background_task(\n                'Telegram auto-failover'" in source
    assert "_run_coordinated_background_task(\n                'YouTube failover'" in source
    assert "_run_coordinated_background_task('UDP/QUIC drift watchdog', refresh_udp_quic_drift)" in source
    assert 'ignore_status_refresh=(task_name == \'status refresh\')' in source
    assert 'status_refresh_in_progress.add(refresh_key)' in source
    assert source.find('status_refresh_in_progress.add(refresh_key)') < source.find(
        "if not _background_task_allowed('status refresh', task_class='light' if active_only else 'normal'):"
    )
    assert 'def _recent_event_history_match' in source
    stream_guard_block = source.split('def _youtube_stream_guard_active', 1)[1].split('def _vless_traffic_guard_active', 1)[0]
    assert "_recent_event_history_match(\n                    'stream_guard_defer'" in stream_guard_block
    assert "_memory_cleanup('telegram polling error', force=True, clear_status=False)" in source
    assert 'def _malloc_trim' in source
    assert 'def _pool_probe_memory_checkpoint' not in source
    assert "'payloads': {}" in source
    assert "def _get_web_status_api_cache(cache_key='full')" in source
    assert "def _store_web_status_api_cache(payload, timestamp=None, cache_key='full')" in source
    assert 'def _record_pool_probe_completion' in source
    assert "float(getattr(config, 'pool_probe_process_worker_poll_seconds', 2.0))" in source
    assert "signature = (int(stat_result.st_mtime_ns), int(stat_result.st_size))" in source
    assert "pool_probe_process_state.get('progress_signature') == signature" in source
    assert "'Pool probe completed: '" in source
    assert 'def _record_post_pool_router_cleanup' not in source
    assert "MAIN_INSTANCE_LOCK_DIR = '/tmp/bypass_telegram_bot_main.lock'" in source
    assert 'def _acquire_main_instance_lock()' in source
    assert 'if COMMAND_WORKER_MODE or POOL_PROBE_WORKER_MODE:' in source
    assert 'Duplicate bot start skipped' in source
    assert 'if not _acquire_main_instance_lock()' in source
    assert '_release_main_instance_lock()' in source
    assert "getattr(config, 'memory_malloc_trim_enabled', True)" in source
    assert 'malloc_trim_attempted' in source
    assert 'MEMORY_WATCHDOG_IDLE_RESTART_RSS_KB = 0' in source
    assert 'worker_rss_before=' in source
    assert 'memory_post_pool_cleanup_target_rss_kb' not in source
    assert 'def _post_pool_program_target_reached' not in source
    assert 'POOL_PROBE_DEFAULT_MAX_PROCESS_RSS_KB = 65 * 1024' in source
    assert "getattr(config, 'pool_probe_max_process_rss_kb', POOL_PROBE_DEFAULT_MAX_PROCESS_RSS_KB)" in source
    assert "getattr(config, 'pool_probe_process_worker_enabled', True)" in source
    assert "BYPASS_KEENETIC_POOL_PROBE_WORKER" in source
    assert "def _run_pool_probe_process_worker" in source
    assert "def _start_selected_pool_probe_process" in source
    available_memory_block = source.split('def _available_memory_kb', 1)[1].split('def _probe_cache', 1)[0]
    assert '_mem_available_kb_light' in available_memory_block
    assert '_pool_probe_controller().available_memory_kb' not in available_memory_block
    progress_label_block = source.split('def _pool_probe_progress_label', 1)[1].split('def _pool_probe_timeout_budget', 1)[0]
    assert '_pool_probe_controller().pool_probe_progress_label' not in progress_label_block
    assert "\\u041f\\u043e\\u043b\\u043d\\u0430\\u044f" in progress_label_block
    process_monitor_block = source.split('def _start_selected_pool_probe_process', 1)[1].split('def _start_selected_pool_probe_tasks', 1)[0]
    assert "_record_pool_probe_completion(" in process_monitor_block
    assert "_memory_cleanup('pool probe process finished', force=True, clear_status=False, log=False)" in process_monitor_block
    assert 'def _forget_unreferenced_key_probes' in source
    delete_pool_block = source.split('def _delete_pool_key', 1)[1].split('def _clear_pool', 1)[0]
    clear_pool_block = source.split('def _clear_pool', 1)[1].split('def _proxy_config_snapshot_paths', 1)[0]
    subscription_add_block = source.split('def _add_subscription_keys_to_pool', 1)[1].split('def _refresh_subscription_once', 1)[0]
    assert '_forget_unreferenced_key_probes([key_value], final_pools)' in delete_pool_block
    assert '_forget_key_probes([key_value])' not in delete_pool_block
    assert '_forget_unreferenced_key_probes(removed_keys, pools)' in clear_pool_block
    assert '_forget_key_probes(removed_keys)' not in clear_pool_block
    assert '_forget_unreferenced_key_probes(removed_keys, pools)' in subscription_add_block
    assert 'def _invalidate_pool_data_cache' in source
    add_pool_block = source.split('def _add_keys_to_pool', 1)[1].split('def _subscription_active_key_is_working', 1)[0]
    probe_invalidate_block = source.split('def _invalidate_probe_status_caches', 1)[1].split('def _delete_pool_probe_resume_file', 1)[0]
    assert '_invalidate_pool_data_cache()' in add_pool_block
    assert '_invalidate_pool_data_cache()' in subscription_add_block
    assert '_invalidate_pool_data_cache()' in probe_invalidate_block
    assert '_invalidate_key_status_cache()' not in probe_invalidate_block
    assert 'import pool_probe_process_runner as runner' in source
    assert "_request_pool_probe_process_cancel(resume=False)" in source
    assert "'no-resume'" in source
    assert "_write_json_file_private(paths['input_path'], payload)" in source
    assert "selected.clear()" in source
    assert "payload['tasks'] = []" in source
    assert 'process_rss_kb=_process_rss_kb' in source
    assert 'max_process_rss_kb=POOL_PROBE_MAX_PROCESS_RSS_KB' in source
    assert 'memory_cleanup=None' in source
    assert 'max_rss_cleanup_attempts=3' in source
    assert "getattr(config, 'pool_failover_process_worker_enabled', True)" in source
    assert 'def _find_pool_failover_candidate_inline' in source
    assert 'def _find_pool_failover_candidate_in_process' in source
    assert 'def _run_failover_candidate_process_worker' in source
    assert 'BYPASS_KEENETIC_HEALTH_WORKER' in source
    assert 'def _run_health_check_process_worker' in source
    assert 'def _check_telegram_api_for_background' in source
    assert 'def _check_youtube_protocol_for_background' in source
    assert 'POOL_FAILOVER_PROCESS_WORKER_ENABLED and not POOL_PROBE_WORKER_MODE' in source
    assert 'POOL_FAILOVER_PROCESS_WORKER_ENABLED and not HEALTH_CHECK_WORKER_MODE' in source
    assert 'check_telegram_api=_check_telegram_api_for_background' in source
    assert '_check_youtube_protocol_for_background(route_proto, metrics=yt_metrics)' in source
    candidate_parent_block = source.split('def _find_pool_failover_candidate_in_process', 1)[1].split(
        'def _find_pool_failover_candidate', 1
    )[0]
    assert 'worker_timed_out' in candidate_parent_block
    assert "_memory_cleanup('failover candidate process finished'" not in candidate_parent_block
    assert 'health check process finished' not in source
    assert 'health check worker finished' not in source
    assert 'memory_timeline_trim_min_interval_seconds' in source
    assert 'def _maybe_trim_memory_timeline_file' in source
    assert '_maybe_trim_memory_timeline_file(MEMORY_TIMELINE_PATH, now=now)' in source
    assert '\nimport requests\n' not in source
    assert 'def _requests_module' in source
    proxy_status_source = (APP_ROOT / 'proxy_status.py').read_text(encoding='utf-8')
    assert '\nimport requests\n' not in proxy_status_source
    assert 'def _requests_module' in proxy_status_source
    pool_runner_text = (APP_ROOT / 'pool_probe_runner.py').read_text(encoding='utf-8')
    assert "run_memory_cleanup('pool probe key checkpoint', force=True" not in pool_runner_text
    assert "run_memory_cleanup('pool probe batch checkpoint', force=True" not in pool_runner_text
    assert "run_memory_cleanup('pool probe worker final checkpoint', force=True" not in pool_runner_text
    assert 'def _pool_probe_runtime_cmdline_matches' in source
    assert "if b'bypass_pool_probe_worker_' in cmdline:" in source
    assert 'def _pool_probe_runtime_file_matches' in source
    assert "if name.startswith('bypass_pool_probe_worker_'):" in source
    assert 'not _pool_probe_runtime_cmdline_matches(cmdline)' in source
    assert 'not _pool_probe_runtime_file_matches(name)' in source
    assert "_cleanup_pool_probe_runtime_light(kill_processes=True)" in source
    assert 'if pid == os.getpid()' in source
    startup_restore = source.split('def _restore_startup_proxy_mode():', 1)[1].split('def _run_telegram_polling_loop():', 1)[0]
    assert "update_proxy('none', persist=False)" not in startup_restore
    polling_loop = source.split('def _run_telegram_polling_loop():', 1)[1].split('def main():', 1)[0]
    assert 'Keep the last healthy state until a preflight or polling error says otherwise.' in polling_loop
    assert 'bot_polling = False\n            if shutdown_requested.is_set()' not in polling_loop
    assert 'shutdown_requested.wait(2)' in polling_loop
    readme_source = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert 'https://raw.githubusercontent.com/andruwko73/bypass_keenetic/main/bootstrap/install.sh' in readme_source
    assert 'https://codeload.github.com/andruwko73/bypass_keenetic/tar.gz/refs/heads/main' in readme_source
    assert 'tmp/bypass-bootstrap-install' in readme_source
    assert 'Прогрев YouTube выполняется отдельным коротким процессом для ускорения загрузки видео' in readme_source
    assert 'не увеличивает постоянный RSS Telegram-бота' not in readme_source
    bootstrap_source = (ROOT / 'bootstrap' / 'install.sh').read_text(encoding='utf-8')
    assert 'prepare_repo_archive()' in bootstrap_source
    assert 'download_file_from_archive()' in bootstrap_source
    assert 'https://codeload.github.com/${REPO_OWNER}/${REPO_NAME}/tar.gz/${archive_ref}' in bootstrap_source
    assert 'raw.githubusercontent.com unavailable for $(basename "$target"); using GitHub archive fallback.' in bootstrap_source
    assert 'download_optional_file "$(repo_file_url static/telegram.svg)"' in bootstrap_source
    script_source = (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'migrate_runtime_config_defaults' in script_source
    assert 'memory_watchdog_idle_restart_rss_kb' not in script_source
    assert 'router_metrics_history_limit = 120' in script_source
    assert 'router_metrics_warn_bot_rss_kb = 66560' in script_source
    assert 'router_metrics_critical_bot_rss_kb = 87040' in script_source
    assert 'router_metrics_warn_load1 = 3.0' in script_source
    assert 'memory_post_pool_restart_rss_kb' not in script_source
    assert 'memory_post_pool_cleanup_target_rss_kb' not in script_source
    assert 'pool_probe_max_process_rss_kb = 66560' in script_source
    assert 'pool_probe_process_worker_enabled = True' in script_source
    assert 'pool_probe_process_worker_poll_seconds = 0.75' in script_source
    assert 'pool_failover_process_worker_enabled = True' in script_source
    assert 'pool_failover_process_worker_timeout_seconds = 180.0' in script_source
    assert "pool_probe_max_process_rss_kb[[:space:]]*=[[:space:]]*(65536|71680|87040)" in script_source
    assert "memory_timeline_path = '/opt/tmp/bypass_memory_timeline.jsonl'" in script_source
    assert 'memory_timeline_max_events = 720' in script_source
    assert "memory_timeline_max_events[[:space:]]*=[[:space:]]*240" in script_source
    assert 'memory_timeline_trim_min_interval_seconds = 300.0' in script_source
    assert 'memory_malloc_trim_enabled = True' in script_source
    assert 'memory_malloc_trim_min_rss_kb = 61440' in script_source
    assert "getattr(config, 'memory_malloc_trim_min_rss_kb', MEMORY_WATCHDOG_RSS_SOFT_KB)" in source
    assert 'background_task_max_bot_rss_kb = 66560' in script_source
    assert 'background_task_critical_max_bot_rss_kb = 71680' in script_source
    assert 'background_task_max_program_rss_kb = 102400' in script_source
    assert 'background_task_critical_max_program_rss_kb = 102400' in script_source
    assert 'auto_failover_idle_log_interval_seconds = 900' in script_source
    assert 'subscription_auto_refresh_interval_seconds = 21600' in script_source
    assert "subscription_auto_refresh_interval_seconds[[:space:]]*=[[:space:]]*86400" in script_source
    assert 'subscription_auto_refresh_check_seconds = 300' in script_source
    assert "subscription_auto_refresh_check_seconds[[:space:]]*=[[:space:]]*3600" in script_source
    assert "getattr(config, 'subscription_auto_refresh_check_seconds', 300)" in source
    assert "telegram_udp_policy = 'auto'" in script_source
    assert 'youtube_edge_prefetch_enabled = True' in script_source
    assert 'youtube_edge_prefetch_max_rss_kb = 66560' in script_source
    assert "youtube_edge_prefetch_dns_servers = ('local', '1.1.1.1', '8.8.8.8')" in script_source
    assert "telegram_call_learning_state_path = '/tmp/bypass_telegram_call_learning.json'" in script_source
    assert '/opt/tmp/bypass_telegram_call_learning.json' in source
    assert "getattr(config, 'telegram_call_learning_default_duration_seconds', 90)" in source
    assert "getattr(config, 'telegram_call_learning_auto_enabled', True)" in source
    assert "getattr(config, 'telegram_call_learning_scan_interval_seconds', 5.0)" in source
    assert "getattr(config, 'telegram_call_learning_client_timeout_seconds', 900)" in source
    assert "getattr(config, 'telegram_call_learning_address_timeout_seconds', 14400)" in source
    assert "getattr(config, 'telegram_call_tproxy_enabled', False)" in source
    assert "getattr(config, 'localportvless_tproxy', 11812)" in source
    assert 'TELEGRAM_CALL_TPROXY_PORT_VLESS={localportvless_tproxy}' in source
    assert 'def _start_telegram_call_learning_auto_thread' in source
    assert '_start_telegram_call_learning_auto_thread()' in source
    auto_start = source.split('def _start_telegram_call_learning_auto_thread', 1)[1].split('def _telegram_call_learning_worker', 1)[0]
    assert 'threading.Thread' in auto_start
    assert '_telegram_call_learning_auto_worker' in auto_start
    assert 'read_lan_conntrack_flows' in source
    assert 'TELEGRAM_CALL_LEARNING_CLIENT_IPSET' in source
    assert 'add_candidate_to_call_ipset' in source
    assert 'iptables/ipset без фонового сканирования' in auto_start
    assert 'telegram_call_learning_apply_by_default = True' in script_source
    assert 'telegram_call_learning_client_timeout_seconds = 900' in script_source
    assert 'telegram_call_learning_address_timeout_seconds = 14400' in script_source
    assert 'telegram_call_tproxy_enabled = True' in script_source
    assert "localportvless_tproxy = '11812'" in script_source
    assert 'Refreshing ipset after proxy core startup.' in script_source
    assert script_source.find('start_preferred_core_service || exit 1') < script_source.find('Refreshing ipset after proxy core startup.')
    assert script_source.find('/opt/etc/init.d/S10cron restart') < script_source.find('start_preferred_core_service || exit 1')
    assert script_source.find('run_update_ipset_refresh "Post-update"') > script_source.find('Refreshing ipset after proxy core startup.')
    assert 'write_update_rollback_script()' in script_source
    assert 'ln -sf "$rollback_path" /opt/root/bypass-last-update-rollback.sh' in script_source
    assert 'backup_runtime_state_files' in script_source
    assert 'backup_runtime_state_file /opt/etc/xray/vless2.key vless2.key' in script_source
    assert 'backup_runtime_state_file /opt/etc/shadowsocks.json shadowsocks.json' in script_source
    assert 'backup_runtime_state_file /opt/etc/trojan/config.json trojan_config.json' in script_source
    assert 'restore_runtime_state_files_after_update()' in script_source
    assert 'restore_runtime_state_file_after_update bot_app_mode /opt/etc/bot_app_mode 0644' in script_source
    assert 'restore_runtime_state_file_after_update bot_proxy_mode /opt/etc/bot_proxy_mode 0644' in script_source
    assert 'restore_runtime_state_file_after_update bot_autostart /opt/etc/bot_autostart 0644' in script_source
    assert 'restore_runtime_state_file_after_update subscriptions.json "$BOT_RUNTIME_DIR/subscriptions.json" 0644' in script_source
    assert 'restore_runtime_state_file_after_update key_pools.json "$BOT_RUNTIME_DIR/key_pools.json" 0644' in script_source
    assert 'restore_runtime_state_file_after_update custom_checks.json "$BOT_RUNTIME_DIR/custom_checks.json" 0644' in script_source
    assert 'restore_runtime_state_file_after_update vmess.key /opt/etc/xray/vmess.key 0600' in script_source
    assert 'restore_runtime_state_file_after_update vless.key /opt/etc/xray/vless.key 0600' in script_source
    assert 'restore_runtime_state_file_after_update vless2.key /opt/etc/xray/vless2.key 0600' in script_source
    assert 'restore_runtime_state_file_after_update xray_config.json /opt/etc/xray/config.json 0644' in script_source
    assert 'restore_runtime_state_file_after_update v2ray_config.json /opt/etc/v2ray/config.json 0644' in script_source
    assert 'restore_runtime_state_file_after_update shadowsocks.json /opt/etc/shadowsocks.json 0600' in script_source
    assert 'restore_runtime_state_file_after_update trojan_config.json /opt/etc/trojan/config.json 0600' in script_source
    assert 'restore_runtime_state_file_after_update unblock_shadowsocks.txt /opt/etc/unblock/shadowsocks.txt 0644' in script_source
    assert 'restore_runtime_state_file_after_update unblock_trojan.txt /opt/etc/unblock/trojan.txt 0644' in script_source
    assert 'restore_runtime_state_file_after_update unblock_vmess.txt /opt/etc/unblock/vmess.txt 0644' in script_source
    assert 'restore_runtime_state_file_after_update unblock_vless.txt /opt/etc/unblock/vless.txt 0644' in script_source
    assert 'restore_runtime_state_file_after_update unblock_vless2.txt /opt/etc/unblock/vless-2.txt 0644' in script_source
    restore_state_call = '\n    restore_runtime_state_files_after_update\n'
    migrate_defaults_call = '\n    migrate_runtime_config_defaults\n'
    assert script_source.find('activate_runtime_modules $BOT_RUNTIME_MODULES') < script_source.find(restore_state_call)
    assert script_source.find(restore_state_call) < script_source.find(migrate_defaults_call)
    assert 'mv "$INSTALLER_MAIN_PATH" "$backup_dir"/installer.py' in script_source
    assert 'mv "$INSTALLER_SERVICE_PATH" "$backup_dir"/S98telegram_bot_installer' in script_source
    assert 'mv "$BOT_SERVICE_PATH" "$backup_dir"/S99telegram_bot' in script_source
    assert 'mv /opt/root/script.sh "$backup_dir"/script.sh' in script_source
    assert 'restore_file S99telegram_bot "\\$BOT_SERVICE_PATH"' in script_source
    assert 'restore_file script.sh /opt/root/script.sh' in script_source
    assert 'restore_file bot_app_mode /opt/etc/bot_app_mode' in script_source
    assert 'restore_file bot_proxy_mode /opt/etc/bot_proxy_mode' in script_source
    assert 'restore_file bot_config.py /opt/etc/bot_config.py' in script_source
    assert 'restore_file vless2.key /opt/etc/xray/vless2.key' in script_source
    assert 'restore_file shadowsocks.json /opt/etc/shadowsocks.json' in script_source
    assert 'restore_file trojan_config.json /opt/etc/trojan/config.json' in script_source
    assert 'if [ -s /opt/etc/shadowsocks.json ]; then' in script_source
    assert 'if [ -s /opt/etc/trojan/config.json ]; then' in script_source
    assert 'pip_cmd="python3 -m pip"' in script_source
    assert '$pip_cmd install pyTelegramBotAPI pysocks' in script_source
    assert "for name in ('version.md', 'README.md')" in source
    assert "'crontab': ('/opt/etc/crontab', 0o644)" in source
    assert "'S99unblock': ('/opt/etc/init.d/S99unblock', 0o755)" in source
    assert "'script.sh': ('/opt/root/script.sh', 0o755)" in source
    assert "_restore_backup_file(bot_config_backup, '/opt/etc/bot_config.py', 0o644)" in source
    assert 'def _placeholder_status_snapshot' in source
    assert "'placeholder_status_snapshot': _placeholder_status_snapshot" in source
    assert 'for key_name, key_value in _ordered_protocol_items(current_keys):' in source
    assert 'cached_active = _cached_active_mode_protocol_status(current_keys)' in source
    assert 'allow_youtube_confirm=False' in source
    assert 'def _pool_probe_cpu_busy_percent' in source
    assert 'def _record_pool_probe_completion' in source
    assert "POOL_PROBE_RESUME_FILE = '/opt/etc/bot/pool_probe_resume.json'" in source
    assert 'def _persist_pool_probe_resume_payload' in source
    assert "serializable['task_ref'] = 'key_hash'" in source
    assert 'def _resolve_pool_probe_resume_tasks' in source
    assert 'def _load_persisted_pool_probe_resume' in source
    assert '_load_persisted_pool_probe_resume()' in source
    assert "_record_pool_probe_completion()" in source
    assert 'def _refresh_status_caches_async(current_keys, active_only=False)' in source
    assert "if not _background_task_allowed('status refresh', task_class='light' if active_only else 'normal')" in source
    assert "refresh_key = f'active:{signature}' if active_only else signature" in source
    assert "_refresh_status_caches_async(current_keys, active_only=True)" in source
    assert 'def _placeholder_status_snapshot(current_keys, include_pool_details=True)' in source
    assert '_placeholder_status_snapshot(current_keys, include_pool_details=False)' in source
    assert 'def _status_snapshot_has_custom_services(snapshot):' in source
    assert 'if cached is not None and not _status_snapshot_has_custom_services(cached):' in source
    assert "_active_mode_status_snapshot_from_base(\n            current_keys,\n            _placeholder_status_snapshot(current_keys, include_pool_details=True)," in source
    assert 'if not pool_enabled:\n            status_refresh_pending = False' not in source
    assert 'def _web_light_pool_summary' not in source
    assert 'def _light_pool_status_summary(current_keys, key_pools, key_probe_cache, custom_checks=None)' in source
    assert 'def _minimal_pool_summary' not in source
    pool_form_context = source.split('def _web_pool_form_context', 1)[1].split('def _web_simple_form_context', 1)[0]
    assert 'summary_probe_cache = _load_key_probe_cache()' not in pool_form_context
    assert 'render_light_protocol_tabs_and_panels' in pool_form_context
    assert '_key_pool_web()' not in pool_form_context
    assert '_web_pool_form_blocks()' not in pool_form_context
    assert '_light_pool_summary_with_cache_fallback(' in pool_form_context
    assert '_service_route_summary()' not in pool_form_context
    assert '_pool_status_summary(current_keys, key_pools, key_probe_cache, custom_checks, route_states)' not in pool_form_context
    assert "'refresh_status_caches_async': refresh_status_caches" in source
    assert "event_history_html=''" in source
    assert "allow_youtube_confirm=True" in source
    assert "allow_youtube_confirm=False" in source
    assert "elif pool_locked:" in source
    assert 'def _attempt_youtube_vless2_failover' in source
    assert '_start_youtube_vless2_failover_thread()' not in source
    assert 'def _probe_applied_pool_key_services' in source
    assert 'probe_applied_pool_key_services=_probe_applied_pool_key_services' in source
    assert "telegram_required=_telegram_required_for_protocol(proto)" in source
    assert "'probe_applied_pool_key_services'" not in (APP_ROOT / 'web_post_actions.py').read_text(encoding='utf-8')
    assert 'def _telegram_route_protocol' in source
    assert "telegram_route_proto = _telegram_route_protocol()" in source
    assert 'proxy_mode=telegram_route_proto' in source
    assert 'protocols=(telegram_route_proto,)' in source
    assert "auto_failover_recent_success_ttl', 900" in source
    assert "auto_failover_candidate_failure_backoff_seconds', 900" in source
    assert "auto_failover_startup_hold_seconds', 180" in source
    assert "auto_failover_consecutive_failures', 3" in source
    assert "auto_failover_traffic_guard_bypass_failures" in source
    assert 'def _event_history_snapshot(limit=50)' in source
    assert 'startup_hold_seconds=AUTO_FAILOVER_STARTUP_HOLD_SECONDS' in source
    assert 'min_consecutive_failures=AUTO_FAILOVER_CONSECUTIVE_FAILURES' in source
    assert 'def _auto_failover_defer_switch_for_traffic_guard' in source
    assert 'defer_switch=_auto_failover_defer_switch_for_traffic_guard' in source
    assert 'bypassing traffic guard after' in source
    assert 'def _auto_failover_log' in source
    assert "'auto_failover_confirm_fail'" in source
    assert 'def _auto_failover_should_run' in source
    assert 'def _mark_auto_failover_polling_ok' in source
    assert "return False, 'Telegram polling is healthy'" in source
    assert "allow_high_rss=reason in ('pending failure', 'Telegram polling stopped')" in source
    assert "if ran:\n            _memory_cleanup('Telegram auto-failover cycle'" in source
    assert "if ran:\n            _memory_cleanup('YouTube failover cycle'" in source
    assert "auto_failover_idle_log_interval_seconds', 900" in source
    assert 'recent_failure_backoff_seconds=AUTO_FAILOVER_CANDIDATE_FAILURE_BACKOFF_SECONDS' in source
    assert 'skip_failed_candidates=True' in source
    assert 'def _mark_active_telegram_failure' in source
    assert "auto_failover_state['last_ok'] = 0.0" in source
    assert 'telegram_route_proto = _telegram_route_protocol() or proxy_mode' in source
    assert 'def _log_telegram_api_status_failure' in source
    assert 'Telegram API status check through' in source
    assert 'allow_recent_success_downgrade=True' in source
    assert "background_task_skip_until.pop('Telegram auto-failover', None)" in source
    assert "background_task_skip_reason.pop('Telegram auto-failover', None)" in source
    assert 'active key marked failed and recovery scheduled' in source
    assert 'telegram polling preflight failed' in source
    assert 'authenticated=True' in source
    assert 'if _is_telegram_connectivity_error(err):' in source
    assert '_mark_active_telegram_failure(err)' in source
    assert 'class _TelegramPollingExceptionHandler' in source
    assert 'exception_handler=_telegram_polling_exception_handler' in source
    assert "_reset_telegram_http_session('internal polling error')" in source
    assert 'def _restore_telegram_polling_after_verified_recovery' in source
    assert '_restore_telegram_polling_after_verified_recovery()' in source
    assert 'not (active_telegram_required and not bot_polling)' in source
    assert 'def _web_render_status_with_polling_guard' in source
    assert "active_status['api_transient'] = True" in source
    assert 'bool(bot_ready)' in source
    assert 'bool(bot_polling)' in source
    assert "'stream_guard_defer'" in source
    assert "youtube_vless2_failover_recent_success_ttl', 900" in source
    assert 'def _youtube_route_protocol' in source
    assert 'def _youtube_route_owner' in source
    assert 'youtube_route_owner(default=\'vless2\')' not in source
    assert "return owner if owner in YOUTUBE_ROUTE_PROTOCOLS else ''" in source
    assert "'route_owner_unavailable'" in source
    assert 'def _youtube_route_marker_count' not in source
    assert "YOUTUBE_ROUTE_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')" in source
    assert "YOUTUBE_STREAM_GUARD_PROTOCOLS = ('vless', 'vless2')" in source
    assert "if proxy_mode not in YOUTUBE_STREAM_GUARD_PROTOCOLS" in source
    assert "_vless_traffic_guard_active(\n        'Telegram auto-failover'" in source
    assert "_vless_traffic_guard_active(\n        f'{_pool_proto_label(route_proto)} core restart recheck'" in source
    assert "_vless_traffic_guard_active(\n            f'{_pool_proto_label(route_proto)} endpoint repair'" in source
    assert "exclude_proto=route_proto" in source
    assert 'another Vless route has active traffic' in source
    assert "_youtube_stream_guard_active(\n                route_proto,\n                f'{_pool_proto_label(route_proto)} key switch'" in source
    assert 'allow_guard_bypass = bool(' in source
    assert 'bypassing stream guard for candidate' in source
    assert "proxy_mode == route_proto" in source
    assert 'Telegram is required because bot mode is' in source
    assert 'YOUTUBE_VLESS2_HEALTHCHECK_URLS' in source
    assert "youtube_stream_guard_failover_hold_seconds" in source
    assert "youtube_stream_guard_scan_cache_seconds" in source
    assert "youtube_stream_guard_event_interval_seconds" in (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8')
    assert "YOUTUBE_STREAM_GUARD_EVENT_INTERVAL" in source
    assert "state['last_event'] = now" in source
    assert source.find("last_event = float(state.get('last_event') or 0.0)") < source.find("_conntrack_route_diagnostic(proto)")
    assert "YOUTUBE_STREAM_GUARD_SCAN_CACHE_SECONDS" in source
    assert 'def _release_runtime_pressure_modules' not in source
    assert 'def _key_pool_store()' in source
    assert '\nimport key_pool_store\n' not in source
    assert "service_route_intersections_cache_ttl', 60.0" in source
    assert 'intersections_cache_ttl=SERVICE_ROUTE_INTERSECTIONS_CACHE_TTL' in source
    assert '_web_response_cleanup' not in source
    assert "elif kind == 'json_text':" in source
    assert "include_pool_ui=True" not in source
    assert "include_route_tools=True" not in source
    assert "malloc_trim_info = _malloc_trim(reason, force=True, rss_kb=rss_before)" not in source
    assert "router_health.invalidate(include_heavy=bool(clear_status))" in source
    assert "if not POOL_PROBE_WORKER_MODE:" in source
    assert "memory_cleanup_rss_kb" not in (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8')
    assert "web_response_cleanup_rss_kb" not in (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8')
    assert "web_response_light_cleanup_rss_kb" not in (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8')
    assert "MEMORY_CLEANUP_RSS_KB" in source
    assert '_clear_runtime_memory_caches(clear_status=True, clear_pool_summary=True)' in source
    assert 'with memory_cleanup_lock:' in source
    assert "pool_summary_cache.update({'signature': None, 'summary': None})" in source
    assert 'def _pool_summary_can_keep_previous' in source
    assert "_pool_summary_count(previous_summary, 'checked_pool_count') > 0" in source
    assert "web_pools_api_cache.setdefault('entries', {})" in source
    assert 'WEB_POOLS_API_CACHE_MAX_ENTRIES' in source
    assert "entries.pop(key, None)" in source
    assert 'serialized_payload = json.dumps(payload' in source
    assert 'return cached_payload if isinstance(cached_payload, str) else None' in source
    assert 'asset_cache_key=path if path in' in source
    assert "action === 'pool-apply'" in (APP_ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
    assert 'avoid rendering full probe details twice' in source
    assert 'event_history_api_cache[\'payload\'] = payload' not in source
    assert "last_scan_count" in source
    assert "cached_fail_since or now" in source
    assert "getattr(config, 'youtube_vless2_failover_check_connect_timeout', 6)" in source
    assert "getattr(config, 'youtube_vless2_failover_check_read_timeout', 10)" in source
    assert 'YOUTUBE_VLESS2_HARD_FAILURE_RECOVERY_COOLDOWN_SECONDS' in source
    assert 'REALITY_ENDPOINT_REPAIR_DNS_SERVERS' in source
    assert 'def _resolve_domain_ipv4_addresses(domain, external_dns=True):' in source
    assert '_resolve_domain_ipv4_addresses(domain, external_dns=False)' in source
    assert 'repair_dns_servers = {str(item).strip() for item in REALITY_ENDPOINT_REPAIR_DNS_SERVERS}' in source
    assert 'if value in repair_dns_servers:' in source
    assert "['dig', '+time=2', '+tries=1', '+short', 'A'" in source
    assert "['nslookup', str(domain), str(dns_server)]" in source
    assert 'def _recover_current_youtube_route_after_hard_failure' in source
    assert source.find("_recent_probe_ok(cached_active_probe, 'yt_ok'") < source.find('ok, message = _check_youtube_protocol_for_background(route_proto')
    assert 'Required YouTube endpoint did not respond through this key: ' in youtube_health_source
    assert 'youtube_timeouts=(YOUTUBE_VLESS2_FAILOVER_CHECK_CONNECT_TIMEOUT, YOUTUBE_VLESS2_FAILOVER_CHECK_READ_TIMEOUT)' in source
    assert 'http_retry_timeouts=(POOL_PROBE_RETRY_CONNECT_TIMEOUT, POOL_PROBE_RETRY_READ_TIMEOUT)' in source
    assert 'redirector.googlevideo.com/generate_204' in youtube_source
    assert 'googlevideo.com/generate_204' in youtube_source
    assert 'i.ytimg.com/generate_204' in youtube_source
    assert 'YOUTUBE_SHORT_URL' in youtube_source
    assert 'https://youtu.be/' in youtube_source
    assert 'YOUTUBE_WATCH_URL' in youtube_source
    assert 'YOUTUBE_HEALTHCHECK_MIN_OK = 8' in youtube_source
    assert len(youtube_healthcheck.YOUTUBE_HEALTHCHECK_URLS) == len(set(youtube_healthcheck.YOUTUBE_HEALTHCHECK_URLS))
    assert 'YOUTUBE_HEALTHCHECK_REQUIRED_URLS' in youtube_source
    assert "host.endswith('.c.youtube.com')" in youtube_source
    assert "host == 'youtu.be'" in youtube_source
    assert "'yt_short_ok'" in youtube_source
    assert 'youtubei-att.googleapis.com' in youtube_source
    assert 'yt_error_rate' in youtube_source
    assert 'yt_stability' in youtube_source
    unblock_source = (APP_ROOT / 'unblock_ipset.sh').read_text(encoding='utf-8')
    assert 'yt4.googleusercontent.com' in unblock_source
    assert 'add_cidr64="$youtube_ipv6_domain"' in unblock_source
    assert 'extra_dns_servers="$YOUTUBE_DNS_SAMPLE_SERVERS"' in unblock_source
    assert 'for sample_dns in $extra_dns_servers; do' in unblock_source
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
    assert "_memory_cleanup('pool probe finished'" not in source
    assert "_memory_cleanup('web command finished'" in source
    assert 'os.environ["BYPASS_KEENETIC_COMMAND_WORKER"] = "1"' in source
    assert 'from pool_probe_runner import' not in source
    assert 'from repo_update import' not in source
    assert 'from web_form_template import' not in source
    assert 'not _IMPORT_TELEGRAM_ENABLED' in source
    assert 'from pool_probe_controller import' not in source
    assert 'from probe_cache import' not in source
    assert '\nimport key_pool_web\n' not in source
    assert '\nimport telegram_pool_ui\n' not in source
    assert '\nimport web_pool_form_blocks\n' not in source
    assert '\nimport auto_failover_runtime\n' not in source
    assert '\nimport telegram_call_learning\n' not in source
    assert '\nimport youtube_edge_prefetch\n' not in source
    assert 'def _key_pool_web()' in source
    assert 'def _probe_cache()' in source
    assert 'class _NoopTeleBot' in source


def test_simple_mode_import_skips_advanced_modules():
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    mode_file = temp_path / 'bot_app_mode'
    mode_file.write_text('simple\n', encoding='utf-8')
    (temp_path / 'bot_config.py').write_text(
        (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8'),
        encoding='utf-8',
    )
    advanced_modules = (
        'custom_checks_store',
        'pool_probe_controller',
        'probe_cache',
        'key_pool_web',
        'telegram_pool_ui',
        'web_pool_form_blocks',
        'auto_failover_runtime',
        'telegram_call_learning',
        'youtube_edge_prefetch',
        'subscription_runtime',
        'service_catalog',
    )
    script = (
        "import json, os, sys\n"
        f"sys.path.insert(0, {str(APP_ROOT)!r})\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        f"sys.path.insert(0, {str(temp_path)!r})\n"
        "import app_runtime_mode\n"
        f"app_runtime_mode.APP_RUNTIME_MODE_FILE = {str(mode_file)!r}\n"
        "import bot\n"
        "current_keys = bot._load_current_keys()\n"
        "bot._web_simple_form_context(current_keys, bot._placeholder_protocol_statuses(current_keys), '', bot._placeholder_web_status_snapshot())\n"
        f"mods = {advanced_modules!r}\n"
        "print(json.dumps({name: name in sys.modules for name in mods}, sort_keys=True))\n"
    )
    env = os.environ.copy()
    env['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
    try:
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        loaded = json.loads(result.stdout.strip())
        assert loaded == {name: False for name in advanced_modules}
    finally:
        temp_dir.cleanup()


def test_web_only_import_skips_telegram_only_modules():
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    mode_file = temp_path / 'bot_app_mode'
    mode_file.write_text('web_only\n', encoding='utf-8')
    (temp_path / 'bot_config.py').write_text(
        (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8'),
        encoding='utf-8',
    )
    telegram_only_modules = (
        'telebot',
        'telegram_key_ui',
        'telegram_info_runtime',
        'telegram_jobs',
        'telegram_message_flow',
        'telegram_confirm',
        'telegram_install_ui',
        'telegram_auth_state',
    )
    script = (
        "import json, os, sys\n"
        f"sys.path.insert(0, {str(APP_ROOT)!r})\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        f"sys.path.insert(0, {str(temp_path)!r})\n"
        "import app_runtime_mode\n"
        f"app_runtime_mode.APP_RUNTIME_MODE_FILE = {str(mode_file)!r}\n"
        "import bot\n"
        f"mods = {telegram_only_modules!r}\n"
        "print(json.dumps({name: name in sys.modules for name in mods}, sort_keys=True))\n"
    )
    env = os.environ.copy()
    env['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
    try:
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        loaded = json.loads(result.stdout.strip())
        assert loaded == {name: False for name in telegram_only_modules}
    finally:
        temp_dir.cleanup()


def test_http_api_handles_parallel_status_pool_and_asset_requests():
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    script = (
        "import concurrent.futures, json, socket, sys, tempfile, time, urllib.request\n"
        "from collections import Counter\n"
        "from pathlib import Path\n"
        f"root = Path({str(ROOT)!r})\n"
        "app = root / 'app'\n"
        "with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:\n"
        "    sock.bind(('127.0.0.1', 0))\n"
        "    port = sock.getsockname()[1]\n"
        f"temp = Path({str(temp_path)!r})\n"
        "config_text = (app / 'bot_config.example.py').read_text(encoding='utf-8')\n"
        "config_text += f\"\\nrouterip = '127.0.0.1'\\nbrowser_port = '{port}'\\nweb_auth_disabled = True\\napp_runtime_mode = 'advanced'\\n\"\n"
        "(temp / 'bot_config.py').write_text(config_text, encoding='utf-8')\n"
        "(temp / 'bot_app_mode').write_text('advanced\\n', encoding='utf-8')\n"
        "sys.path[:0] = [str(temp), str(app), str(root)]\n"
        "import app_runtime_mode\n"
        "app_runtime_mode.APP_RUNTIME_MODE_FILE = str(temp / 'bot_app_mode')\n"
        "import bot\n"
        "bot.start_http_server()\n"
        "time.sleep(0.2)\n"
        "paths = ('/api/status?compact=1&lite=1', '/api/pools?protocol=vless', '/static/app.js', '/static/app.css')\n"
        "def fetch(index):\n"
        "    request = urllib.request.Request(f'http://127.0.0.1:{port}{paths[index % len(paths)]}')\n"
        "    with urllib.request.urlopen(request, timeout=15) as response:\n"
        "        response.read()\n"
        "        return response.status\n"
        "try:\n"
        "    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:\n"
        "        results = list(executor.map(fetch, range(50)))\n"
        "    print(json.dumps({'responses': dict(Counter(results)), 'requests': len(results)}, sort_keys=True))\n"
        "finally:\n"
        "    if bot.web_httpd:\n"
        "        bot.web_httpd.shutdown()\n"
        "        bot.web_httpd.server_close()\n"
    )
    env = os.environ.copy()
    env['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
    try:
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=True,
        )
        payload = json.loads(result.stdout.strip())
        assert payload == {'requests': 50, 'responses': {'200': 50}}
    finally:
        temp_dir.cleanup()


def test_advanced_initial_web_context_skips_heavy_pool_modules():
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    mode_file = temp_path / 'bot_app_mode'
    mode_file.write_text('advanced\n', encoding='utf-8')
    (temp_path / 'bot_config.py').write_text(
        (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8'),
        encoding='utf-8',
    )
    heavy_modules = (
        'probe_cache',
        'key_pool_web',
        'web_pool_form_blocks',
    )
    script = (
        "import json, os, sys\n"
        f"sys.path.insert(0, {str(APP_ROOT)!r})\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        f"sys.path.insert(0, {str(temp_path)!r})\n"
        "import app_runtime_mode\n"
        f"app_runtime_mode.APP_RUNTIME_MODE_FILE = {str(mode_file)!r}\n"
        "import bot\n"
        "bot.WEB_POOL_SNAPSHOT_WORKER_ENABLED = False\n"
        "bot._load_key_pools = lambda: {proto: [] for proto in bot.POOL_PROTOCOL_ORDER}\n"
        "bot._save_key_pools = lambda pools: None\n"
        "bot._subscription_public_settings = lambda: {}\n"
        "bot._load_custom_checks = lambda: []\n"
        "current_keys = bot._load_current_keys()\n"
        "bot._web_pool_form_context(\n"
        "    current_keys,\n"
        "    bot._placeholder_protocol_statuses(current_keys),\n"
        "    '',\n"
        "    bot._placeholder_web_status_snapshot(),\n"
        "    False,\n"
        "    {},\n"
        ")\n"
        f"mods = {heavy_modules!r}\n"
        "print(json.dumps({name: name in sys.modules for name in mods}, sort_keys=True))\n"
    )
    env = os.environ.copy()
    env['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
    try:
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        loaded = json.loads(result.stdout.strip())
        assert loaded == {name: False for name in heavy_modules}
    finally:
        temp_dir.cleanup()


def test_light_pool_summary_rebuilds_when_pool_size_changes():
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    mode_file = temp_path / 'bot_app_mode'
    mode_file.write_text('advanced\n', encoding='utf-8')
    (temp_path / 'bot_config.py').write_text(
        (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8'),
        encoding='utf-8',
    )
    script = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(APP_ROOT)!r})\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        f"sys.path.insert(0, {str(temp_path)!r})\n"
        "import app_runtime_mode\n"
        f"app_runtime_mode.APP_RUNTIME_MODE_FILE = {str(mode_file)!r}\n"
        "import bot\n"
        f"bot._KEY_PROBE_CACHE_PATH = {str(temp_path / 'key_probe_cache.json')!r}\n"
        f"bot._POOL_SUMMARY_LAST_PATH = {str(temp_path / 'pool_summary_last.json')!r}\n"
        "keys = ['vless://one', 'vless://two']\n"
        "cache = {bot._hash_key(key): {'schema': 8, 'tg_ok': True, 'yt_ok': True} for key in keys}\n"
        "with open(bot._KEY_PROBE_CACHE_PATH, 'w', encoding='utf-8') as handle: json.dump(cache, handle)\n"
        "with open(bot._POOL_SUMMARY_LAST_PATH, 'w', encoding='utf-8') as handle: json.dump({'summary': {'pool_total_count': 1, 'checked_pool_count': 1}}, handle)\n"
        "pools = {proto: [] for proto in bot.POOL_PROTOCOL_ORDER}\n"
        "pools['vless'] = keys\n"
        "summary = bot._light_pool_summary_with_cache_fallback({'vless': keys[0]}, pools, [])\n"
        "print(json.dumps(summary, sort_keys=True))\n"
    )
    env = os.environ.copy()
    env['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
    try:
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        summary = json.loads(result.stdout.strip())
        assert summary['pool_total_count'] == 2
        assert summary['checked_pool_count'] == 2
        assert summary['services'][0] == {'count': 2, 'label': 'Telegram'}
        assert summary['services'][1] == {'count': 2, 'label': 'YouTube'}
    finally:
        temp_dir.cleanup()


def test_active_status_refresh_skips_heavy_pool_modules():
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    mode_file = temp_path / 'bot_app_mode'
    mode_file.write_text('advanced\n', encoding='utf-8')
    (temp_path / 'bot_config.py').write_text(
        (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8'),
        encoding='utf-8',
    )
    heavy_modules = (
        'probe_cache',
        'key_pool_web',
        'web_pool_form_blocks',
        'web_route_tools_runtime',
        'route_intersections',
        'service_routes',
    )
    script = (
        "import json, os, sys\n"
        f"sys.path.insert(0, {str(APP_ROOT)!r})\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        f"sys.path.insert(0, {str(temp_path)!r})\n"
        "import app_runtime_mode\n"
        f"app_runtime_mode.APP_RUNTIME_MODE_FILE = {str(mode_file)!r}\n"
        "import bot\n"
        "bot.proxy_mode = 'vless'\n"
        "bot.bot_ready = True\n"
        "bot.bot_polling = True\n"
        "bot._load_custom_checks = lambda: [{'id': 'chat', 'label': 'Chat', 'url': 'https://example.com/'}]\n"
        "bot._check_local_proxy_endpoint = lambda key, port: (True, 'SOCKS ok.')\n"
        "bot._check_telegram_api_for_background = lambda *args, **kwargs: (True, 'ok')\n"
        "bot._check_telegram_api_through_proxy = lambda *args, **kwargs: (True, 'ok')\n"
        "bot._key_requires_xray = lambda *args, **kwargs: False\n"
        f"bot._KEY_PROBE_CACHE_PATH = {str(temp_path / 'key_probe_cache.json')!r}\n"
        "current_keys = {'vless': 'active-key-placeholder', 'vless2': 'other-key-placeholder'}\n"
        "with open(bot._KEY_PROBE_CACHE_PATH, 'w', encoding='utf-8') as file:\n"
        "    json.dump({bot._hash_key(current_keys['vless2']): {'schema': 8, 'proto': 'vless2', 'tg_ok': False, 'yt_ok': True, 'yt_stability': 'stable', 'ts': 123}}, file)\n"
        "snapshot = bot._active_mode_status_snapshot(current_keys, background_checks=True)\n"
        "assert snapshot['protocols']['vless']['api_ok'] is True\n"
        "assert 'YouTube:' not in snapshot['protocols']['vless']['details']\n"
        "assert snapshot['protocols']['vless2']['tone'] == 'empty'\n"
        "assert snapshot['protocols']['vless2']['yt_ok'] is False\n"
        "assert snapshot['protocols']['vless2']['api_ok'] is False\n"
        "cache = json.load(open(bot._KEY_PROBE_CACHE_PATH, encoding='utf-8'))\n"
        "active_entry = cache[bot._hash_key(current_keys['vless'])]\n"
        "assert active_entry['proto'] == 'vless'\n"
        "assert active_entry['tg_ok'] is True\n"
        f"mods = {heavy_modules!r}\n"
        "print(json.dumps({name: name in sys.modules for name in mods}, sort_keys=True))\n"
    )
    env = os.environ.copy()
    env['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
    try:
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        loaded = json.loads(result.stdout.strip())
        assert loaded == {name: False for name in heavy_modules}
    finally:
        temp_dir.cleanup()


def test_light_protocol_panel_skips_heavy_pool_modules():
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    mode_file = temp_path / 'bot_app_mode'
    mode_file.write_text('advanced\n', encoding='utf-8')
    (temp_path / 'bot_config.py').write_text(
        (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8'),
        encoding='utf-8',
    )
    heavy_modules = (
        'probe_cache',
        'key_pool_web',
        'web_pool_form_blocks',
        'web_route_tools_runtime',
        'route_intersections',
        'service_routes',
    )
    script = (
        "import json, os, sys\n"
        f"sys.path.insert(0, {str(APP_ROOT)!r})\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        f"sys.path.insert(0, {str(temp_path)!r})\n"
        "import app_runtime_mode\n"
        f"app_runtime_mode.APP_RUNTIME_MODE_FILE = {str(mode_file)!r}\n"
        "import bot\n"
        "bot._load_key_pools = lambda: {proto: [] for proto in bot.POOL_PROTOCOL_ORDER}\n"
        "bot._save_key_pools = lambda pools: None\n"
        "bot._subscription_public_settings = lambda: {}\n"
        "html = bot._web_protocol_panel_html('vless', {'vless': 'active-key-placeholder'}, {}, '<input>')\n"
        "assert 'data-protocol-panel=\"vless\"' in html\n"
        f"mods = {heavy_modules!r}\n"
        "print(json.dumps({name: name in sys.modules for name in mods}, sort_keys=True))\n"
    )
    env = os.environ.copy()
    env['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
    try:
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        loaded = json.loads(result.stdout.strip())
        assert loaded == {name: False for name in heavy_modules}
    finally:
        temp_dir.cleanup()


def test_protocol_check_panel_defers_route_tools_modules():
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    mode_file = temp_path / 'bot_app_mode'
    mode_file.write_text('advanced\n', encoding='utf-8')
    (temp_path / 'bot_config.py').write_text(
        (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8'),
        encoding='utf-8',
    )
    heavy_modules = (
        'key_pool_web',
        'web_route_tools_runtime',
        'route_intersections',
        'service_routes',
    )
    script = (
        "import json, os, sys\n"
        f"sys.path.insert(0, {str(APP_ROOT)!r})\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        f"sys.path.insert(0, {str(temp_path)!r})\n"
        "import app_runtime_mode\n"
        f"app_runtime_mode.APP_RUNTIME_MODE_FILE = {str(mode_file)!r}\n"
        "import bot\n"
        "bot._load_custom_checks = lambda: [{'id': 'chatgpt_services', 'label': 'ChatGPT', 'url': 'https://example.com/'}]\n"
        "html = bot._web_protocol_check_html('vless', {'vless': 'active-key-placeholder'}, {}, '<input>')\n"
        "assert 'data-route-tools-deferred=\"1\"' in html\n"
        "assert 'service-route-trigger' not in html\n"
        f"mods = {heavy_modules!r}\n"
        "print(json.dumps({name: name in sys.modules for name in mods}, sort_keys=True))\n"
    )
    env = os.environ.copy()
    env['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
    try:
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        loaded = json.loads(result.stdout.strip())
        assert loaded == {name: False for name in heavy_modules}
    finally:
        temp_dir.cleanup()


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
        assert source_path(module).exists()
    for module in ('app_version.py', 'app_runtime_mode.py', 'router_health_runtime.py', 'router_metrics.py', 'telegram_call_learning.py', 'web_commands_runtime.py'):
        assert module in script
        assert f'repo_file_url {module}' in bootstrap or 'repo_file_url "$module"' in bootstrap
    assert f'$BOT_DIR/{module}' in bootstrap
    assert 'web_pool_snapshot_worker.py' in script_modules
    assert 'web_pool_snapshot_worker.py' in bootstrap_modules
    assert 'web_service_routes_worker.py' in script_modules
    assert 'web_service_routes_worker.py' in bootstrap_modules
    assert 'CHANGELOG.md' not in script_modules
    assert 'ROLLBACK_MODULES="$BOT_RUNTIME_MODULES CHANGELOG.md"' in script
    assert 'rm -f "$BOT_DIR/CHANGELOG.md"' in bootstrap
    assert 'youtube_edge_prefetch.py' in script_modules
    assert 'youtube_edge_prefetch_runner.py' in script_modules
    assert 'youtube_edge_prefetch_runner.py' in bootstrap_modules


def test_youtube_edge_prefetch_runner_detects_current_youtube_route(tmp_path):
    unblock_dir = tmp_path / 'unblock'
    unblock_dir.mkdir()
    state_path = tmp_path / 'owner.json'
    for _, file_name in youtube_route_owner.ROUTE_FILES:
        (unblock_dir / file_name).write_text('example.com\n', encoding='utf-8')

    (unblock_dir / 'vless.txt').write_text('www.youtube.com\ni.ytimg.com\n', encoding='utf-8')
    assert youtube_edge_prefetch_runner.detect_youtube_route_protocol(str(unblock_dir), state_path=str(state_path)) == 'vless'

    (unblock_dir / 'vless.txt').write_text('example.com\n', encoding='utf-8')
    (unblock_dir / 'vless-2.txt').write_text('youtube.com\ngooglevideo.com\nyt3.ggpht.com\n', encoding='utf-8')
    assert youtube_edge_prefetch_runner.detect_youtube_route_protocol(str(unblock_dir), state_path=str(state_path)) == 'vless2'

    (unblock_dir / 'vless-2.txt').write_text('example.com\n', encoding='utf-8')
    (unblock_dir / 'vmess.txt').write_text('domain:youtubei.googleapis.com\n', encoding='utf-8')
    assert youtube_edge_prefetch_runner.detect_youtube_route_protocol(str(unblock_dir), state_path=str(state_path)) == 'vmess'


def test_youtube_edge_prefetch_runner_prefers_bot_config_over_legacy_config():
    source = source_path('youtube_edge_prefetch_runner.py').read_text(encoding='utf-8')

    assert "('/opt/etc', '/opt/etc/bot')" in source
    assert 'while config_dir in sys.path:' in source
    assert 'sys.path.remove(config_dir)' in source
    assert 'sys.path.insert(0, config_dir)' in source


def test_background_maintenance_scheduler_combines_periodic_tasks():
    source = source_path('bot.py').read_text(encoding='utf-8')

    assert 'def _background_maintenance_tasks()' in source
    assert 'def _start_background_maintenance_thread()' in source
    assert "name='background-maintenance'" in source
    assert '    _start_background_maintenance_thread()\n    if telegram_enabled:' in source
    assert 'BACKGROUND_TASK_SLOW_LOG_SECONDS' in source
    assert "scheduler duration: {duration_seconds:.2f}s" in source
    assert 'def _ipset_ipv4_snapshot(set_name):' in source
    assert 'def _ipset_snapshot_contains(networks, address):' in source
    assert "['ipset', 'save', str(set_name or '')]" in source
    assert 'UDP_QUIC_DRIFT_DNS_CACHE_TTL_SECONDS' in source
    assert 'def _udp_quic_drift_domains_by_protocol(route_sets):' in source
    assert 'def _udp_quic_drift_domain_addresses(domain):' in source
    assert 'def _udp_quic_drift_route_sets():' in source
    assert 'for proto in UDP_QUIC_POLICY_PROTOCOLS' in source
    assert 'if domains_by_protocol.get(proto)' in source
    for callback in (
        '_run_auto_failover_cycle',
        '_run_youtube_failover_cycle',
        '_run_udp_quic_drift_watchdog_cycle',
        '_run_subscription_auto_refresh_cycle',
        '_run_memory_watchdog_cycle',
    ):
        assert f'def {callback}' in source


def test_youtube_edge_prefetch_cache_is_bounded_and_public_only():
    now = 1_800_000
    cache = {
        'version': 1,
        'updated_at': now,
        'entries': {
            '142.250.150.119': {'host': 'www.youtube.com', 'source': 'dns', 'last_seen': now - 10, 'hits': 2},
            '172.217.20.170': {'host': 'i.ytimg.com', 'source': 'dns', 'last_seen': now - 20, 'hits': 1},
            '10.0.0.1': {'host': 'bad', 'source': 'dns', 'last_seen': now, 'hits': 9},
            '142.251.38.106': {'host': 'old', 'source': 'dns', 'last_seen': now - 4000, 'hits': 1},
            '142.251.38.110': {'host': 'extra', 'source': 'dns', 'last_seen': now - 5, 'hits': 1},
        },
    }

    pruned = youtube_edge_prefetch.prune_cache(cache, now=now, ttl_seconds=3600, max_entries=2)

    assert list(pruned['entries']) == ['142.251.38.110', '142.250.150.119']
    assert '10.0.0.1' not in pruned['entries']
    assert '142.251.38.106' not in pruned['entries']
    assert youtube_edge_prefetch.parse_ipv4_tokens('A 142.250.150.119 private 192.168.1.10') == ['142.250.150.119']


def test_youtube_edge_prefetch_collects_limited_dns_candidates():
    class Result:
        returncode = 0
        stdout = '142.251.38.106\n10.0.0.1\n'

    def fake_getaddrinfo(host, port, family, socktype):
        assert host == 'www.youtube.com'
        return [(family, socktype, 0, '', ('142.250.150.119', port))]

    def fake_run_command(args, timeout):
        raise AssertionError(f'external DNS must remain fallback-only: {args!r}')

    candidates, cache = youtube_edge_prefetch.collect_prefetch_candidates(
        hosts=('www.youtube.com', 'i.ytimg.com'),
        dns_servers=('local', '1.1.1.1'),
        cache=None,
        now=1_800_000,
        max_hosts_per_run=1,
        max_resolved_addresses=4,
        getaddrinfo=fake_getaddrinfo,
        run_command=fake_run_command,
    )

    addresses = [item['address'] for item in candidates]
    assert addresses == ['142.250.150.119']
    assert set(cache['entries']) == set(addresses)


def test_youtube_edge_prefetch_can_prefer_fresh_dns_before_cache():
    now = 1_800_000
    cache = {
        'version': 1,
        'updated_at': now,
        'entries': {
            '172.217.20.170': {'host': 'i.ytimg.com', 'source': 'dns', 'last_seen': now - 10, 'hits': 2},
        },
    }

    def fake_getaddrinfo(host, port, family, socktype):
        return [(family, socktype, 0, '', ('142.250.150.119', port))]

    candidates, _ = youtube_edge_prefetch.collect_prefetch_candidates(
        hosts=('www.youtube.com',),
        dns_servers=('local',),
        cache=cache,
        now=now,
        max_hosts_per_run=1,
        max_resolved_addresses=1,
        max_candidates=2,
        cache_before_dns=False,
        getaddrinfo=fake_getaddrinfo,
        run_command=lambda args, timeout: '',
    )

    assert [item['address'] for item in candidates] == ['142.250.150.119', '172.217.20.170']


def test_youtube_edge_prefetch_extracts_watch_edge_hosts():
    html = (
        r'https:\/\/rr3---sn-4g5ednsl.googlevideo.com\/videoplayback?expire=1\u0026id=o'
        ' https://rr2---sn-4g5ednse.c.youtube.com/videoplayback'
        ' https://googlevideo.com/not-an-edge'
    )

    hosts = youtube_edge_prefetch.extract_watch_edge_hosts(html, max_hosts=3)

    assert hosts == (
        'rr3---sn-4g5ednsl.googlevideo.com',
        'rr2---sn-4g5ednse.c.youtube.com',
    )


def test_youtube_edge_prefetch_priority_hosts_are_tried_before_cache():
    now = 1_800_000
    cache = {
        'version': 1,
        'updated_at': now,
        'entries': {
            '142.250.150.119': {'host': 'www.youtube.com', 'source': 'dns', 'last_seen': now - 10, 'hits': 2},
        },
    }

    def fake_getaddrinfo(host, port, family, socktype):
        addresses = {
            'rr3---sn-4g5ednsl.googlevideo.com': '173.194.188.72',
            'www.youtube.com': '64.233.162.198',
        }
        return [(family, socktype, 0, '', (addresses[host], port))]

    candidates, cache = youtube_edge_prefetch.collect_prefetch_candidates(
        hosts=('www.youtube.com',),
        priority_hosts=('rr3---sn-4g5ednsl.googlevideo.com',),
        dns_servers=('local',),
        cache=cache,
        now=now,
        max_hosts_per_run=1,
        max_resolved_addresses=4,
        getaddrinfo=fake_getaddrinfo,
        run_command=lambda args, timeout: '',
    )

    assert candidates[0]['address'] == '173.194.188.72'
    assert candidates[0]['route_member'] == '173.194.188.0/24'
    assert candidates[0]['source'] == 'watch'
    assert cache['entries']['173.194.188.72']['source'] == 'watch'
    assert cache['entries']['173.194.188.72']['route_member'] == '173.194.188.0/24'


def test_youtube_edge_prefetch_watch_googlevideo_adds_network_priority_route():
    address = '173.194.5.1'
    member = '173.194.5.0/24'
    present = {
        ('unblockvless', address),
        ('unblockvlessudp', member),
        ('unblockvlesspriority', member),
    }
    added = []
    deleted = []

    def overlaps(member_value, target_value):
        try:
            member_network = youtube_edge_prefetch.ipaddress.ip_network(member_value, strict=False)
            target_network = youtube_edge_prefetch.ipaddress.ip_network(target_value, strict=False)
        except Exception:
            return False
        return member_network.version == target_network.version and member_network.overlaps(target_network)

    def ipset_contains(set_name, ip):
        return (set_name, ip) in present

    def ipset_add(set_name, ip):
        present.add((set_name, ip))
        added.append((set_name, ip))
        return True, ''

    def ipset_delete_overlaps(set_name, ip):
        removed = [
            (existing_set, existing_member)
            for existing_set, existing_member in list(present)
            if existing_set == set_name and overlaps(existing_member, ip)
        ]
        for item in removed:
            present.discard(item)
            deleted.append(item)
        return len(removed)

    def fake_getaddrinfo(host, port, family, socktype):
        assert host == 'rr1---sn-2oaig5-5n.googlevideo.com'
        return [(family, socktype, 0, '', (address, port))]

    with tempfile.TemporaryDirectory() as tmp:
        status = youtube_edge_prefetch.prefetch_once(
            route_protocol='vless2',
            cache_path=str(Path(tmp) / 'youtube_edge_cache.json'),
            hosts=(),
            priority_hosts=('rr1---sn-2oaig5-5n.googlevideo.com',),
            dns_servers=('local',),
            ipset_contains=ipset_contains,
            ipset_add=ipset_add,
            ipset_delete_overlaps=ipset_delete_overlaps,
            delete_conntrack=lambda ip: 1,
            now_provider=lambda: 1_800_000,
            max_resolved_addresses=1,
            max_addresses_per_run=1,
            getaddrinfo=fake_getaddrinfo,
            run_command=lambda args, timeout: '',
        )

    assert status['ok'] is True
    assert status['added_addresses'] == 1
    assert ('unblockvless2', member) in added
    assert ('unblockvless2udp', member) in added
    assert ('unblockvless2priority', member) in added
    assert ('unblockvless', address) in deleted
    assert ('unblockvlessudp', member) in deleted
    assert ('unblockvlesspriority', member) in deleted


def test_youtube_edge_prefetch_adds_active_route_and_removes_overlaps():
    address = '142.250.150.119'
    present = {
        ('unblockvless', address),
        ('unblockvlessudp', address),
        ('unblockvmess', '142.250.150.0/24'),
    }
    added = []
    deleted = []

    def ipset_contains(set_name, ip):
        return (set_name, ip) in present

    def ipset_add(set_name, ip):
        present.add((set_name, ip))
        added.append((set_name, ip))
        return True, ''

    def ipset_delete(set_name, ip):
        existed = (set_name, ip) in present
        present.discard((set_name, ip))
        if existed:
            deleted.append((set_name, ip))
        return existed

    def ipset_delete_overlaps(set_name, ip):
        removed = []
        for existing_set, member in list(present):
            if existing_set != set_name:
                continue
            try:
                address_obj = youtube_edge_prefetch.ipaddress.ip_address(ip)
                network = youtube_edge_prefetch.ipaddress.ip_network(member, strict=False)
            except Exception:
                continue
            if address_obj.version == network.version and address_obj in network:
                removed.append((existing_set, member))
        for item in removed:
            present.discard(item)
            deleted.append(item)
        return len(removed)

    def fake_getaddrinfo(host, port, family, socktype):
        return [(family, socktype, 0, '', (address, port))]

    with tempfile.TemporaryDirectory() as tmp:
        status = youtube_edge_prefetch.prefetch_once(
            route_protocol='vless2',
            cache_path=str(Path(tmp) / 'youtube_edge_cache.json'),
            hosts=('www.youtube.com',),
            dns_servers=('local',),
            ipset_contains=ipset_contains,
            ipset_add=ipset_add,
            ipset_delete=ipset_delete,
            ipset_delete_overlaps=ipset_delete_overlaps,
            delete_conntrack=lambda ip: 1,
            now_provider=lambda: 1_800_000,
            max_addresses_per_run=1,
            getaddrinfo=fake_getaddrinfo,
            run_command=lambda args, timeout: '',
        )

    assert status['ok'] is True
    assert status['added_addresses'] == 1
    assert ('unblockvless2', address) in added
    assert ('unblockvless2udp', address) in added
    assert ('unblockvless', address) in deleted
    assert ('unblockvlessudp', address) in deleted
    assert ('unblockvmess', '142.250.150.0/24') in deleted
    assert ('unblockvless', address) not in present
    assert ('unblockvmess', '142.250.150.0/24') not in present
    assert ('unblockvless2', address) in present


def test_youtube_edge_prefetch_runner_deletes_covering_ipset_network():
    original_run_command = youtube_edge_prefetch_runner._run_command
    deleted = []

    def fake_run_command(args, timeout=3):
        if args[:2] == ['ipset', 'list']:
            return py_types.SimpleNamespace(
                returncode=0,
                stdout='Name: unblockvless\nMembers:\n142.250.150.0/24\n8.8.8.8\n',
            )
        if args[:2] == ['ipset', 'del']:
            deleted.append(tuple(args[1:]))
            return py_types.SimpleNamespace(returncode=0, stdout='')
        return py_types.SimpleNamespace(returncode=1, stdout='')

    try:
        youtube_edge_prefetch_runner._run_command = fake_run_command
        count = youtube_edge_prefetch_runner.ipset_delete_overlaps(
            'unblockvless',
            '142.250.150.119',
        )
    finally:
        youtube_edge_prefetch_runner._run_command = original_run_command

    assert count == 1
    assert ('del', 'unblockvless', '142.250.150.0/24') in deleted
    assert ('del', 'unblockvless', '8.8.8.8') not in deleted


def test_youtube_edge_prefetch_cleans_other_sets_when_target_network_already_contains_ip():
    address = '142.250.150.119'
    present = {
        ('unblockvless2', '142.250.150.0/24'),
        ('unblockvless2udp', '142.250.150.0/24'),
        ('unblockvless', address),
    }
    added = []
    deleted = []

    def member_contains_ip(member, ip):
        try:
            address_obj = youtube_edge_prefetch.ipaddress.ip_address(ip)
            network = youtube_edge_prefetch.ipaddress.ip_network(member, strict=False)
        except Exception:
            return False
        return address_obj.version == network.version and address_obj in network

    def ipset_contains(set_name, ip):
        return any(existing_set == set_name and member_contains_ip(member, ip) for existing_set, member in present)

    def ipset_add(set_name, ip):
        added.append((set_name, ip))
        return True, ''

    def ipset_delete_overlaps(set_name, ip):
        removed = [
            (existing_set, member)
            for existing_set, member in list(present)
            if existing_set == set_name and member_contains_ip(member, ip)
        ]
        for item in removed:
            present.discard(item)
            deleted.append(item)
        return len(removed)

    def fake_getaddrinfo(host, port, family, socktype):
        return [(family, socktype, 0, '', (address, port))]

    with tempfile.TemporaryDirectory() as tmp:
        status = youtube_edge_prefetch.prefetch_once(
            route_protocol='vless2',
            cache_path=str(Path(tmp) / 'youtube_edge_cache.json'),
            hosts=('www.youtube.com',),
            dns_servers=('local',),
            ipset_contains=ipset_contains,
            ipset_add=ipset_add,
            ipset_delete_overlaps=ipset_delete_overlaps,
            delete_conntrack=lambda ip: 1,
            now_provider=lambda: 1_800_000,
            max_addresses_per_run=1,
            getaddrinfo=fake_getaddrinfo,
            run_command=lambda args, timeout: '',
        )

    assert status['ok'] is True
    assert status['added_addresses'] == 0
    assert added == []
    assert status['deleted_sets'] == 1
    assert ('unblockvless', address) in deleted
    assert ('unblockvless', address) not in present
    assert ('unblockvless2', '142.250.150.0/24') in present


def test_youtube_edge_prefetch_quality_probe_filters_slow_and_eof():
    addresses = {
        'www.youtube.com': '142.250.150.119',
        'youtubei.googleapis.com': '142.251.38.106',
        'manifest.googlevideo.com': '172.217.20.170',
    }
    added = []

    def fake_getaddrinfo(host, port, family, socktype):
        return [(family, socktype, 0, '', (addresses[host], port))]

    def quality_probe(candidate):
        address = candidate['address']
        if address == '142.250.150.119':
            return {'ok': True, 'latency_ms': 850, 'reason': 'ok'}
        if address == '142.251.38.106':
            return {'ok': True, 'latency_ms': 1500, 'reason': 'ok'}
        return {'ok': False, 'latency_ms': 300, 'reason': 'eof'}

    with tempfile.TemporaryDirectory() as tmp:
        status = youtube_edge_prefetch.prefetch_once(
            route_protocol='vless2',
            cache_path=str(Path(tmp) / 'youtube_edge_cache.json'),
            hosts=tuple(addresses),
            dns_servers=('local',),
            ipset_contains=lambda set_name, ip: False,
            ipset_add=lambda set_name, ip: added.append((set_name, ip)) or True,
            now_provider=lambda: 1_800_000,
            max_hosts_per_run=3,
            max_resolved_addresses=3,
            max_addresses_per_run=3,
            quality_probe=quality_probe,
            quality_probe_enabled=True,
            quality_probe_target_ms=1000,
            getaddrinfo=fake_getaddrinfo,
            run_command=lambda args, timeout: '',
        )

    assert status['ok'] is True
    assert status['quality_tested'] == 3
    assert status['quality_accepted'] == 1
    assert status['quality_rejected_slow'] == 1
    assert status['quality_rejected_eof'] == 1
    assert status['added_addresses'] == 1
    assert added == [
        ('unblockvless2', '142.250.150.119'),
        ('unblockvless2udp', '142.250.150.119'),
    ]


def test_youtube_edge_prefetch_skips_recent_bad_quality_cache():
    now = 1_800_000
    cache = {
        'version': 1,
        'updated_at': now,
        'entries': {
            '142.250.150.119': {
                'host': 'www.youtube.com',
                'source': 'dns',
                'last_seen': now - 10,
                'hits': 2,
                'quality_last_fail': now - 60,
                'quality_fail_reason': 'eof',
            },
        },
    }
    probe_calls = []

    with tempfile.TemporaryDirectory() as tmp:
        cache_path = Path(tmp) / 'youtube_edge_cache.json'
        cache_path.write_text(json.dumps(cache), encoding='utf-8')
        status = youtube_edge_prefetch.prefetch_once(
            route_protocol='vless2',
            cache_path=str(cache_path),
            hosts=(),
            dns_servers=('local',),
            ipset_contains=lambda set_name, ip: False,
            ipset_add=lambda set_name, ip: True,
            now_provider=lambda: now,
            quality_probe=lambda candidate: probe_calls.append(candidate) or {'ok': True, 'latency_ms': 700},
            quality_probe_enabled=True,
            quality_probe_bad_cooldown_seconds=3600,
            getaddrinfo=lambda host, port, family, socktype: [],
            run_command=lambda args, timeout: '',
        )

    assert status['quality_rejected_cached'] == 1
    assert status['added_addresses'] == 0
    assert probe_calls == []


def test_youtube_edge_prefetch_quality_probe_can_score_existing_ipset_entries():
    address = '142.250.150.119'
    quality_calls = []

    def fake_getaddrinfo(host, port, family, socktype):
        return [(family, socktype, 0, '', (address, port))]

    with tempfile.TemporaryDirectory() as tmp:
        status = youtube_edge_prefetch.prefetch_once(
            route_protocol='vless2',
            cache_path=str(Path(tmp) / 'youtube_edge_cache.json'),
            hosts=('www.youtube.com',),
            dns_servers=('local',),
            ipset_contains=lambda set_name, ip: True,
            ipset_add=lambda set_name, ip: False,
            now_provider=lambda: 1_800_000,
            max_hosts_per_run=1,
            max_resolved_addresses=1,
            quality_probe=lambda candidate: quality_calls.append(candidate) or {'ok': True, 'latency_ms': 800},
            quality_probe_enabled=True,
            quality_probe_existing=True,
            getaddrinfo=fake_getaddrinfo,
            run_command=lambda args, timeout: '',
        )

    assert status['quality_tested'] == 1
    assert status['quality_accepted'] == 1
    assert status['added_addresses'] == 0
    assert quality_calls[0]['address'] == address


def test_youtube_edge_prefetch_protects_shared_google_candidates():
    assert youtube_edge_prefetch.youtube_owned_host('rr3---sn-4g5ednsl.googlevideo.com')
    assert not youtube_edge_prefetch.youtube_owned_host('remotedesktop-pa.googleapis.com')
    assert not youtube_edge_prefetch.youtube_owned_host('www.gstatic.com')

    def fake_getaddrinfo(host, port, family, socktype):
        return [(family, socktype, 0, '', ('142.250.150.120', port))]

    with tempfile.TemporaryDirectory() as tmp:
        status = youtube_edge_prefetch.prefetch_once(
            route_protocol='vless2',
            cache_path=str(Path(tmp) / 'youtube_edge_cache.json'),
            hosts=('www.gstatic.com',),
            dns_servers=('local',),
            ipset_contains=lambda set_name, ip: False,
            ipset_add=lambda set_name, ip: True,
            now_provider=lambda: 1_800_000,
            max_hosts_per_run=1,
            max_resolved_addresses=1,
            quality_probe=lambda candidate: {'ok': True, 'latency_ms': 100},
            quality_probe_enabled=True,
            getaddrinfo=fake_getaddrinfo,
            run_command=lambda args, timeout: '',
        )

    assert status['shared_candidates_skipped'] == 1
    assert status['quality_tested'] == 0
    assert status['added_addresses'] == 0


def test_youtube_edge_prefetch_restores_only_quality_approved_cache():
    now = 1_800_000
    good_address = '142.250.150.119'
    shared_address = '142.250.150.120'
    failed_address = '142.250.150.121'
    untested_address = '142.250.150.122'
    cache = {
        'version': 1,
        'updated_at': now,
        'entries': {
            good_address: {
                'host': 'rr3---sn-4g5ednsl.googlevideo.com',
                'source': 'watch',
                'last_seen': now - 10,
                'hits': 4,
                'quality_last_ok': now - 10,
                'quality_latency_ms': 420,
            },
            shared_address: {
                'host': 'www.gstatic.com',
                'source': 'dns',
                'last_seen': now - 8,
                'hits': 3,
                'quality_last_ok': now - 8,
                'quality_latency_ms': 200,
            },
            failed_address: {
                'host': 'rr4---sn-4g5ednsl.googlevideo.com',
                'source': 'watch',
                'last_seen': now - 6,
                'hits': 2,
                'quality_last_ok': now - 120,
                'quality_last_fail': now - 20,
                'quality_fail_reason': 'slow',
            },
            untested_address: {
                'host': 'rr5---sn-4g5ednsl.googlevideo.com',
                'source': 'watch',
                'last_seen': now - 4,
                'hits': 1,
            },
        },
    }
    added = []
    deleted = []

    with tempfile.TemporaryDirectory() as tmp:
        cache_path = Path(tmp) / 'youtube_edge_cache.json'
        cache_path.write_text(json.dumps(cache), encoding='utf-8')
        status = youtube_edge_prefetch.restore_cached_ipsets(
            route_protocol='vless2',
            cache_path=str(cache_path),
            ipset_contains=lambda set_name, ip: False,
            ipset_add=lambda set_name, ip: added.append((set_name, ip)) or True,
            ipset_delete=lambda set_name, ip: deleted.append((set_name, ip)) or False,
            now_provider=lambda: now,
            max_addresses=16,
            require_quality_ok=True,
        )

    assert status['ok'] is True
    assert status['candidates'] == 1
    assert status['added_addresses'] == 1
    assert ('unblockvless2', '142.250.150.0/24') in added
    assert ('unblockvless2udp', '142.250.150.0/24') in added
    assert ('unblockvless2priority', '142.250.150.0/24') in added
    assert ('unblockvlesspriority', '142.250.150.0/24') in deleted
    assert all(ip == '142.250.150.0/24' for _set_name, ip in added)
    assert all(ip == '142.250.150.0/24' for _set_name, ip in deleted)
    assert status['shared_candidates_skipped'] == 1
    assert status['cache_restore_skipped_recent_bad_quality'] == 1
    assert status['cache_restore_skipped_no_quality'] == 1


def test_youtube_edge_prefetch_removes_opposite_priority_for_existing_target():
    address = '216.58.198.174'
    deleted = []

    def fake_getaddrinfo(host, port, family, socktype):
        return [(family, socktype, 0, '', (address, port))]

    def fake_contains(set_name, ip):
        return set_name in ('unblockvless2', 'unblockvless2udp')

    with tempfile.TemporaryDirectory() as tmp:
        status = youtube_edge_prefetch.prefetch_once(
            route_protocol='vless2',
            cache_path=str(Path(tmp) / 'youtube_edge_cache.json'),
            hosts=('www.youtube.com',),
            dns_servers=('local',),
            ipset_contains=fake_contains,
            ipset_add=lambda set_name, ip: False,
            ipset_delete=lambda set_name, ip: deleted.append((set_name, ip)) or True,
            now_provider=lambda: 1_800_000,
            max_hosts_per_run=1,
            max_resolved_addresses=1,
            getaddrinfo=fake_getaddrinfo,
            run_command=lambda args, timeout: '',
        )

    assert status['ok'] is True
    assert status['added_addresses'] == 0
    assert ('unblockvlesspriority', address) in deleted
    assert ('unblockvless', address) in deleted
    assert ('unblockvlessudp', address) in deleted


def test_youtube_edge_prefetch_runner_collects_watch_hosts_through_route_socks():
    original_config = youtube_edge_prefetch_runner.config
    original_fetch = youtube_edge_prefetch_runner._fetch_watch_page
    calls = []

    try:
        youtube_edge_prefetch_runner.config = py_types.SimpleNamespace(
            youtube_edge_watch_warm_enabled=True,
            youtube_edge_watch_warm_urls=('https://www.youtube.com/watch?v=aqz-KE-bpKQ',),
            youtube_edge_watch_warm_max_pages=1,
            youtube_edge_watch_warm_max_hosts=2,
            youtube_edge_watch_warm_max_bytes=200000,
            youtube_edge_watch_warm_connect_timeout=1,
            youtube_edge_watch_warm_max_time=2,
            localportvless='12000',
        )

        def fake_fetch(url, socks_port, **kwargs):
            calls.append((url, socks_port, kwargs))
            return 'https://rr3---sn-4g5ednsl.googlevideo.com/videoplayback'

        youtube_edge_prefetch_runner._fetch_watch_page = fake_fetch

        hosts, status = youtube_edge_prefetch_runner.collect_watch_edge_hosts('vless2')
    finally:
        youtube_edge_prefetch_runner.config = original_config
        youtube_edge_prefetch_runner._fetch_watch_page = original_fetch

    assert hosts == ('rr3---sn-4g5ednsl.googlevideo.com',)
    assert calls[0][1] == 12002
    assert status['socks_port'] == 12002
    assert status['hosts'] == 1


def test_youtube_edge_prefetch_runner_extends_existing_prefetch_hosts():
    original_config = youtube_edge_prefetch_runner.config
    try:
        youtube_edge_prefetch_runner.config = py_types.SimpleNamespace(
            youtube_edge_prefetch_hosts=('www.youtube.com', 'i.ytimg.com'),
        )

        hosts = youtube_edge_prefetch_runner.prefetch_hosts_for_run()
    finally:
        youtube_edge_prefetch_runner.config = original_config

    assert hosts[:2] == ('www.youtube.com', 'i.ytimg.com')
    assert 'youtube.com' in hosts
    assert 'manifest.googlevideo.com' in hosts
    assert 'jnn-pa.googleapis.com' in hosts
    assert 'play-fe.googleapis.com' in hosts


def test_youtube_edge_prefetch_runner_extends_existing_watch_urls():
    original_config = youtube_edge_prefetch_runner.config
    try:
        youtube_edge_prefetch_runner.config = py_types.SimpleNamespace(
            youtube_edge_watch_warm_urls=(
                'https://www.youtube.com/watch?v=aqz-KE-bpKQ',
                'https://www.youtube.com/live/MFpQKwwh29E',
            ),
        )

        urls = youtube_edge_prefetch_runner.watch_urls_for_run()
    finally:
        youtube_edge_prefetch_runner.config = original_config

    assert urls[0] == 'https://www.youtube.com/watch?v=aqz-KE-bpKQ'
    assert 'https://www.youtube.com/live/MFpQKwwh29E' in urls
    assert 'https://www.youtube.com/watch?v=jfKfPfyJRdk' in urls


def test_youtube_edge_prefetch_runner_warms_one_watch_page_by_default():
    original_config = youtube_edge_prefetch_runner.config
    original_fetch = youtube_edge_prefetch_runner._fetch_watch_page
    calls = []

    try:
        youtube_edge_prefetch_runner.config = py_types.SimpleNamespace(
            youtube_edge_watch_warm_enabled=True,
            youtube_edge_watch_warm_urls=(
                'https://www.youtube.com/watch?v=aqz-KE-bpKQ',
                'https://www.youtube.com/live/MFpQKwwh29E',
            ),
            youtube_edge_watch_warm_max_hosts=6,
            youtube_edge_watch_warm_max_bytes=200000,
            youtube_edge_watch_warm_connect_timeout=1,
            youtube_edge_watch_warm_max_time=2,
            localportvless='12000',
        )

        def fake_fetch(url, socks_port, **kwargs):
            calls.append((url, socks_port, kwargs))
            return f'https://rr{len(calls)}---sn-4g5ednsl.googlevideo.com/videoplayback'

        youtube_edge_prefetch_runner._fetch_watch_page = fake_fetch

        hosts, status = youtube_edge_prefetch_runner.collect_watch_edge_hosts('vless2')
    finally:
        youtube_edge_prefetch_runner.config = original_config
        youtube_edge_prefetch_runner._fetch_watch_page = original_fetch

    assert len(calls) == 1
    assert hosts == (
        'rr1---sn-4g5ednsl.googlevideo.com',
    )
    assert status['fetched_pages'] == 1


def test_youtube_edge_prefetch_runner_uses_fast_hosts_for_start_triggers():
    original_config = youtube_edge_prefetch_runner.config
    try:
        youtube_edge_prefetch_runner.config = py_types.SimpleNamespace(
            youtube_edge_prefetch_fast_warm_enabled=True,
            youtube_edge_prefetch_fast_hosts=('youtubei.googleapis.com', 'www.youtube.com'),
        )

        hosts = youtube_edge_prefetch_runner.prefetch_hosts_for_run(fast=True)
    finally:
        youtube_edge_prefetch_runner.config = original_config

    assert youtube_edge_prefetch_runner._fast_warm_enabled_for_trigger('Post-update-late')
    assert not youtube_edge_prefetch_runner._fast_warm_enabled_for_trigger('scheduler')
    assert hosts[:2] == ('youtubei.googleapis.com', 'www.youtube.com')
    assert 'youtube.com' in hosts
    assert 'manifest.googlevideo.com' in hosts
    assert 'i.ytimg.com' in hosts
    assert 's.ytimg.com' in hosts
    assert 'yt3.ggpht.com' in hosts


def test_youtube_edge_prefetch_runner_skips_scheduler_full_run_on_high_cpu():
    original_config = youtube_edge_prefetch_runner.config
    original_read_cpu_percent = youtube_edge_prefetch_runner.read_cpu_percent
    original_read_load1 = youtube_edge_prefetch_runner.read_load1
    try:
        youtube_edge_prefetch_runner.config = py_types.SimpleNamespace(
            youtube_edge_prefetch_scheduler_max_cpu_percent=45,
            youtube_edge_prefetch_scheduler_max_load1=2.0,
            youtube_edge_prefetch_cpu_sample_ms=50,
        )
        youtube_edge_prefetch_runner.read_cpu_percent = lambda sample_seconds=0.25: 88.5
        youtube_edge_prefetch_runner.read_load1 = lambda: 2.75

        assert youtube_edge_prefetch_runner._scheduler_full_run_cpu_busy('scheduler', False) == 88.5
        assert youtube_edge_prefetch_runner._scheduler_full_run_cpu_busy('ipset-refresh', False) == 88.5
        assert youtube_edge_prefetch_runner._scheduler_full_run_cpu_busy('manual-refresh', False) == 88.5
        assert youtube_edge_prefetch_runner._scheduler_full_run_cpu_busy('Post-update', False) is None
        assert youtube_edge_prefetch_runner._scheduler_full_run_cpu_busy('scheduler', True) is None
        assert youtube_edge_prefetch_runner._scheduler_full_run_load_busy('scheduler', False) == 2.75
        assert youtube_edge_prefetch_runner._scheduler_full_run_load_busy('ipset-refresh', False) == 2.75
        assert youtube_edge_prefetch_runner._scheduler_full_run_load_busy('manual-refresh', False) == 2.75
        assert youtube_edge_prefetch_runner._scheduler_full_run_load_busy('Post-update', False) is None
        assert youtube_edge_prefetch_runner._scheduler_full_run_load_busy('scheduler', True) is None
    finally:
        youtube_edge_prefetch_runner.config = original_config
        youtube_edge_prefetch_runner.read_cpu_percent = original_read_cpu_percent
        youtube_edge_prefetch_runner.read_load1 = original_read_load1


def test_youtube_edge_prefetch_runner_uses_cache_restore_for_start_triggers():
    original_config = youtube_edge_prefetch_runner.config
    try:
        youtube_edge_prefetch_runner.config = py_types.SimpleNamespace(
            youtube_edge_prefetch_cache_restore_enabled=True,
        )

        assert youtube_edge_prefetch_runner._cache_restore_enabled_for_trigger('Post-update')
        assert youtube_edge_prefetch_runner._cache_restore_enabled_for_trigger('Post-update-late')
        assert youtube_edge_prefetch_runner._cache_restore_enabled_for_trigger('startup')
        assert youtube_edge_prefetch_runner._cache_restore_enabled_for_trigger('manual-restore')
        assert youtube_edge_prefetch_runner._cache_restore_only_for_trigger('manual-restore')
        assert not youtube_edge_prefetch_runner._cache_restore_enabled_for_trigger('scheduler')
    finally:
        youtube_edge_prefetch_runner.config = original_config


def test_youtube_edge_prefetch_runner_cache_restore_skips_fast_prefetch_when_sufficient(tmp_path):
    original_config = youtube_edge_prefetch_runner.config
    original_acquire_lock = youtube_edge_prefetch_runner.acquire_lock
    original_release_lock = youtube_edge_prefetch_runner.release_lock
    original_read_available = youtube_edge_prefetch_runner.read_available_memory_kb
    original_detect_route = youtube_edge_prefetch_runner.detect_youtube_route_protocol
    original_self_test = youtube_edge_prefetch_runner.youtube_route_self_test
    original_restore = youtube_edge_prefetch_runner.youtube_edge_prefetch.restore_cached_ipsets
    original_prefetch = youtube_edge_prefetch_runner.youtube_edge_prefetch.prefetch_once
    restore_calls = []
    try:
        youtube_edge_prefetch_runner.config = py_types.SimpleNamespace(
            youtube_edge_prefetch_enabled=True,
            youtube_edge_prefetch_fast_warm_enabled=True,
            youtube_edge_prefetch_cache_restore_enabled=True,
            youtube_edge_prefetch_min_available_kb=0,
            youtube_edge_prefetch_lock_dir=str(tmp_path / 'lock'),
        )
        youtube_edge_prefetch_runner.acquire_lock = lambda lock_dir: True
        youtube_edge_prefetch_runner.release_lock = lambda lock_dir: None
        youtube_edge_prefetch_runner.read_available_memory_kb = lambda: 200000
        youtube_edge_prefetch_runner.detect_youtube_route_protocol = lambda **kwargs: 'vless2'
        youtube_edge_prefetch_runner.youtube_route_self_test = lambda protocol: {
            'ok': False,
            'reason': 'request_failed',
            'http_code': '000',
            'duration_ms': 1,
        }

        def fake_restore(**kwargs):
            restore_calls.append(kwargs)
            return {
                'ok': True,
                'route_protocol': 'vless2',
                'last_run_at': 100.0,
                'skipped_reason': '',
                'mode': 'cache_restore',
                'candidates': 3,
                'cache_entries': 4,
                'added_addresses': 1,
                'added_sets': 2,
                'deleted_sets': 0,
                'cache_restore_skipped_no_quality': 0,
                'cache_restore_skipped_failed_quality': 0,
                'cache_restore_skipped_recent_bad_quality': 0,
            }

        youtube_edge_prefetch_runner.youtube_edge_prefetch.restore_cached_ipsets = fake_restore
        youtube_edge_prefetch_runner.youtube_edge_prefetch.prefetch_once = (
            lambda **kwargs: (_ for _ in ()).throw(AssertionError('prefetch_once must not run'))
        )

        status = youtube_edge_prefetch_runner.run_prefetch(
            trigger='Post-update',
            status_path=str(tmp_path / 'status.json'),
            cache_path=str(tmp_path / 'cache.json'),
            unblock_dir=str(tmp_path / 'unblock'),
        )
    finally:
        youtube_edge_prefetch_runner.config = original_config
        youtube_edge_prefetch_runner.acquire_lock = original_acquire_lock
        youtube_edge_prefetch_runner.release_lock = original_release_lock
        youtube_edge_prefetch_runner.read_available_memory_kb = original_read_available
        youtube_edge_prefetch_runner.detect_youtube_route_protocol = original_detect_route
        youtube_edge_prefetch_runner.youtube_route_self_test = original_self_test
        youtube_edge_prefetch_runner.youtube_edge_prefetch.restore_cached_ipsets = original_restore
        youtube_edge_prefetch_runner.youtube_edge_prefetch.prefetch_once = original_prefetch

    assert len(restore_calls) == 1
    assert status['ok'] is True
    assert status['warm_mode'] == 'cache_restore'
    assert status['prefetch_skipped_reason'] == 'cache_restore_sufficient'
    assert status['cache_restored_addresses'] == 1
    assert status['last_message'] == 'vless2: added 1 addresses, candidates 3, cache 4'


def test_youtube_edge_prefetch_runner_skips_warmup_after_successful_self_test(tmp_path):
    original_config = youtube_edge_prefetch_runner.config
    original_acquire_lock = youtube_edge_prefetch_runner.acquire_lock
    original_release_lock = youtube_edge_prefetch_runner.release_lock
    original_read_available = youtube_edge_prefetch_runner.read_available_memory_kb
    original_detect_route = youtube_edge_prefetch_runner.detect_youtube_route_protocol
    original_self_test = youtube_edge_prefetch_runner.youtube_route_self_test
    original_restore = youtube_edge_prefetch_runner.youtube_edge_prefetch.restore_cached_ipsets
    original_prefetch = youtube_edge_prefetch_runner.youtube_edge_prefetch.prefetch_once
    try:
        youtube_edge_prefetch_runner.config = py_types.SimpleNamespace(
            youtube_edge_prefetch_enabled=True,
            youtube_edge_prefetch_fast_warm_enabled=True,
            youtube_edge_prefetch_cache_restore_enabled=True,
            youtube_edge_prefetch_min_available_kb=0,
            youtube_edge_prefetch_lock_dir=str(tmp_path / 'lock'),
        )
        youtube_edge_prefetch_runner.acquire_lock = lambda lock_dir: True
        youtube_edge_prefetch_runner.release_lock = lambda lock_dir: None
        youtube_edge_prefetch_runner.read_available_memory_kb = lambda: 200000
        youtube_edge_prefetch_runner.detect_youtube_route_protocol = lambda **kwargs: 'trojan'
        youtube_edge_prefetch_runner.youtube_route_self_test = lambda protocol: {'ok': True, 'protocol': protocol}
        youtube_edge_prefetch_runner.youtube_edge_prefetch.restore_cached_ipsets = (
            lambda **kwargs: (_ for _ in ()).throw(AssertionError('cache restore must not run'))
        )
        youtube_edge_prefetch_runner.youtube_edge_prefetch.prefetch_once = (
            lambda **kwargs: (_ for _ in ()).throw(AssertionError('prefetch must not run'))
        )

        status = youtube_edge_prefetch_runner.run_prefetch(
            trigger='route-change',
            status_path=str(tmp_path / 'status.json'),
            cache_path=str(tmp_path / 'cache.json'),
            unblock_dir=str(tmp_path / 'unblock'),
        )
    finally:
        youtube_edge_prefetch_runner.config = original_config
        youtube_edge_prefetch_runner.acquire_lock = original_acquire_lock
        youtube_edge_prefetch_runner.release_lock = original_release_lock
        youtube_edge_prefetch_runner.read_available_memory_kb = original_read_available
        youtube_edge_prefetch_runner.detect_youtube_route_protocol = original_detect_route
        youtube_edge_prefetch_runner.youtube_route_self_test = original_self_test
        youtube_edge_prefetch_runner.youtube_edge_prefetch.restore_cached_ipsets = original_restore
        youtube_edge_prefetch_runner.youtube_edge_prefetch.prefetch_once = original_prefetch

    assert status['ok'] is True
    assert status['skipped_reason'] == 'self_test_ok'
    assert status['warm_mode'] == 'not_needed'


def test_entware_dns_runtime_helpers():
    class _Result:
        def __init__(self, returncode):
            self.returncode = returncode

    assert hasattr(entware_dns_runtime, 'prepare_entware_dns')
    assert entware_dns_runtime.entware_dns_is_available(run_quiet=lambda args: _Result(0))
    assert not entware_dns_runtime.entware_dns_is_available(run_quiet=lambda args: _Result(1))
    assert entware_dns_runtime.entware_ip_from_lookup('Address 1: 1.1.1.1\nAddress 2: 2.2.2.2') == '2.2.2.2'
    source = (APP_ROOT / 'entware_dns_runtime.py').read_text(encoding='utf-8')
    assert "no opkg dns-override" not in source


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
    assert 'Программа подбирает рабочий ключ из пула текущего режима' in pending['api_status']
    assert pending['socks_details'] == 'SOCKS ok.'
    ok_with_service_recheck = web_status_runtime.build_web_status_snapshot(
        state_label='state',
        proxy_mode='vless',
        protocols={
            'vless': {
                'endpoint_ok': True,
                'endpoint_message': 'SOCKS ok.',
                'api_ok': True,
                'api_message': 'Доступ к api.telegram.org подтверждён',
                'details': 'Telegram: работает, YouTube: нестабильно, перепроверяется',
            }
        },
        ports={'vless': 10811},
        check_socks5=lambda port: False,
        check_telegram_api=lambda **kwargs: 'unused',
        is_transient=lambda text: False,
        fallback_reason='',
    )
    assert ok_with_service_recheck['api_status'].startswith('✅')
    assert not web_status_runtime.protocol_status_is_pending({
        'api_ok': True,
        'details': 'Telegram: работает, YouTube: нестабильно, перепроверяется',
    })
    raw_failure = web_status_runtime.build_web_status_snapshot(
        state_label='state',
        proxy_mode='vless',
        protocols={
            'vless': {
                'endpoint_ok': True,
                'endpoint_message': 'SOCKS ok.',
                'api_ok': False,
                'api_message': 'HTTPSConnectionPool(host="api.telegram.org", port=443): Max retries exceeded',
            }
        },
        ports={'vless': 10811},
        check_socks5=lambda port: False,
        check_telegram_api=lambda **kwargs: 'unused',
        is_transient=lambda text: False,
        fallback_reason='',
    )
    assert raw_failure['api_status'].startswith('❌ Доступ к Telegram API через режим vless не проходит.')
    assert 'Программа подбирает рабочий ключ из пула текущего режима' in raw_failure['api_status']
    assert 'Техническая ошибка записана в лог' in raw_failure['api_status']
    assert 'HTTPSConnectionPool' not in raw_failure['api_status']
    assert 'Max retries exceeded' not in raw_failure['api_status']
    direct_raw_failure = web_status_runtime.build_web_status_snapshot(
        state_label='state',
        proxy_mode='none',
        protocols={},
        ports={},
        check_socks5=lambda port: False,
        check_telegram_api=lambda **kwargs: '❌ Прямой доступ к api.telegram.org не проходит: HTTPSConnectionPool(host="api.telegram.org", port=443): Max retries exceeded',
        is_transient=lambda text: False,
        fallback_reason='',
    )
    assert direct_raw_failure['api_status'].startswith('❌ Прямой доступ к api.telegram.org не проходит.')
    assert 'Программа подбирает рабочий ключ из пула текущего режима' in direct_raw_failure['api_status']
    assert 'Техническая ошибка записана в лог' in direct_raw_failure['api_status']
    assert 'HTTPSConnectionPool' not in direct_raw_failure['api_status']
    assert 'Max retries exceeded' not in direct_raw_failure['api_status']
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
    assert 'Статус обновляется' in placeholder['api_status']
    assert 'Проверяется актуальное состояние' in placeholder['api_status']
    assert 'Программа подбирает рабочий ключ из пула текущего режима' not in placeholder['api_status']
    assert 'не проходит:' not in placeholder['api_status']
    unchecked = web_status_runtime.build_web_status_snapshot(
        state_label='state',
        proxy_mode='vless',
        protocols={'vless': {'tone': 'warn', 'label': 'unchecked', 'details': 'waiting for background check', 'api_ok': False, 'api_message': ''}},
        ports={'vless': 10811},
        check_socks5=lambda port: False,
        check_telegram_api=lambda **kwargs: 'unused',
        is_transient=lambda text: False,
        fallback_reason='',
    )
    assert 'Статус обновляется' in unchecked['api_status']
    assert 'Проверяется актуальное состояние' in unchecked['api_status']
    assert 'Программа подбирает рабочий ключ из пула текущего режима' not in unchecked['api_status']
    assert 'не проходит:' not in unchecked['api_status']
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
    assert 'Программа подбирает рабочий ключ из пула текущего режима' in fallback['api_status']
    attention = web_form_template._attention_items(
        {'api_status': '❌ Доступ к Telegram API через режим vless не проходит:'},
        {'used_percent': 0},
        '',
        True,
    )
    assert attention[0][0] == 'warn'


def test_telegram_call_router_health_note():
    policy = '\n'.join([
        'BYPASS_TELEGRAM_CALL_LEARNING_ENABLED=1',
        'BYPASS_TELEGRAM_CALL_TPROXY_ENABLED=1',
        'BYPASS_TELEGRAM_CALL_ROUTE_VLESS=1',
        'BYPASS_TELEGRAM_CALL_ROUTE_VLESS2=0',
        'TELEGRAM_CALL_TPROXY_PORT_VLESS=11812',
    ])
    commands = []

    def run_text(command, timeout=2):
        commands.append(tuple(command))
        if command[:2] == ['netstat', '-lnp']:
            return 'udp        0      0 0.0.0.0:11812           0.0.0.0:*                           123/xray\n'
        if command[:4] == ['iptables', '-t', 'mangle', '-nL']:
            return 'Chain BYPASS_TG_CALL_TPROXY (3 references)\n'
        return ''

    health = router_health_runtime.telegram_call_proxy_health(
        run_text=run_text,
        read_values=lambda _path: router_health_runtime.parse_key_value_text(policy),
    )
    assert health['ok'] is True
    assert health['ports'] == {'vless': 11812}
    assert router_health_runtime.telegram_call_proxy_note(health) == 'Звонки через TPROXY работают для Telegram/WhatsApp/Discord на порте: Vless 11812'
    assert ('netstat', '-lnp') in commands


def test_telegram_call_learning_idle_backoff_source():
    source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    config_source = (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8')
    installer_source = (ROOT / 'script.sh').read_text(encoding='utf-8')
    auto_scan = source.split('def _telegram_call_learning_auto_scan', 1)[1].split('def _telegram_call_learning_auto_worker', 1)[0]
    assert 'TELEGRAM_CALL_LEARNING_IDLE_BACKOFF_SECONDS' in source
    assert 'TELEGRAM_CALL_LEARNING_FAST_SCAN_LIMIT' in source
    assert 'idle_no_client_scans' in source
    assert 'needs_initial_scan = not was_watching' in source
    assert 'udp_source_activity_signature(active_clients)' in source
    assert 'follow_up_scan_pending = False' in source
    assert 'scan_is_follow_up = follow_up_scan_pending' in source
    assert 'if not needs_initial_scan and not udp_activity_changed and not scan_is_follow_up:' in source
    assert 'if not scan_is_follow_up and saw_relevant_flows:' in source
    assert 'if was_watching and idle_no_client_scans >= TELEGRAM_CALL_LEARNING_FAST_SCAN_LIMIT:' in source
    call_learning_source = (APP_ROOT / 'telegram_call_learning.py').read_text(encoding='utf-8')
    assert "command = ['grep', '-F']" in call_learning_source
    assert 'source_tokens=allowed_source_tokens' in call_learning_source
    assert 'def udp_source_activity_signature' in call_learning_source
    assert 'idle_no_client_scans >= TELEGRAM_CALL_LEARNING_FAST_SCAN_LIMIT' in source
    assert 'idle_active_scans >= TELEGRAM_CALL_LEARNING_FAST_SCAN_LIMIT' not in source
    route_signature = source.split('def _telegram_call_learning_route_signature', 1)[1].split(
        'def _telegram_call_learning_route_protocols', 1
    )[0]
    route_cache = source.split('def _telegram_call_learning_route_protocols', 1)[1].split(
        'def _select_telegram_call_learning_protocol', 1
    )[0]
    assert 'stat.st_mtime_ns' in route_signature
    assert 'time.time()' not in route_cache
    assert "telegram_call_learning_route_cache.get('signature') == signature" in route_cache
    assert "'timestamp':" not in route_cache
    assert "if not candidate.get('udp_call_cluster'):" in auto_scan
    assert "not candidate.get('udp_call_active_media')" not in auto_scan
    assert 'telegram_call_learning_idle_backoff_seconds = 60.0' in config_source
    assert 'telegram_call_learning_idle_backoff_seconds = 60.0' in installer_source


def test_cached_protocol_status_description_has_no_static_trailing_period():
    status = web_status_builder.cached_protocol_status(
        'vless://sample',
        {'tg_ok': True, 'yt_ok': True},
        [{'id': 'discord', 'label': 'Discord'}],
        {'discord': 'ok'},
    )
    assert status['details'].endswith('Discord: работает')
    assert not status['details'].endswith('.')
    warn_status = web_status_builder.cached_protocol_status(
        'vless://sample',
        {'tg_ok': True, 'yt_ok': False, 'yt_stability': 'unstable'},
        [],
        {},
    )
    assert warn_status['tone'] == 'warn'
    assert warn_status['yt_ok'] is True
    assert warn_status['yt_state'] == 'warn'
    assert 'YouTube:' in warn_status['details']


def test_active_protocol_status_description_has_no_trailing_period():
    status = web_status_builder.active_protocol_status(
        endpoint_ok=True,
        endpoint_message='Локальный SOCKS-порт 127.0.0.1:10811 отвечает как SOCKS5.',
        api_ok=True,
        api_message='ok',
        api_transient=False,
        yt_ok=True,
        yt_message='ok',
        custom_states={},
        custom_checks=[],
    )
    assert status['details'].endswith('YouTube: работает')
    assert not status['details'].endswith('.')


def test_active_protocol_status_keeps_confirmed_services_while_refresh_is_pending():
    status = web_status_builder.active_protocol_status(
        endpoint_ok=True,
        endpoint_message='SOCKS ok.',
        api_ok=True,
        api_message='cached Telegram result',
        api_transient=False,
        api_pending=True,
        yt_ok=True,
        yt_message='cached YouTube result',
        yt_pending=True,
        custom_states={'discord': 'ok'},
        custom_checks=[{'id': 'discord', 'label': 'Discord'}],
        required_services=('telegram', 'youtube'),
    )
    assert status['label'] == 'Статус обновляется'
    assert status['api_ok'] is True
    assert status['yt_ok'] is True
    assert status['api_pending'] is True
    assert status['yt_pending'] is True
    assert web_status_runtime.protocol_status_is_pending(status)
    assert 'Последний подтверждённый результат сохранён' in status['details']


def test_light_status_keeps_confirmed_custom_services():
    light_status = {
        'tone': 'ok',
        'label': 'ok',
        'details': 'Telegram: ok',
        'endpoint_ok': True,
        'endpoint_message': 'SOCKS ok',
        'api_ok': True,
        'api_message': 'ok',
        'api_pending': False,
        'yt_ok': False,
        'yt_message': '',
        'yt_pending': False,
        'yt_state': 'unused',
        'custom': {},
    }
    previous_status = {
        'custom': {'discord': 'ok', 'claude': 'fail'},
        'yt_ok': False,
        'yt_message': '',
        'yt_pending': False,
        'yt_state': 'unused',
    }
    status = web_status_builder.merge_light_status_with_cached_services(
        light_status,
        previous_status,
        [
            {'id': 'discord', 'label': 'Discord'},
            {'id': 'claude', 'label': 'Claude'},
        ],
        required_services=('telegram',),
    )
    assert status['custom'] == previous_status['custom']
    assert status['tone'] == 'warn'
    assert 'Discord' in status['details']
    assert 'Claude' in status['details']


def test_internal_telegram_polling_exception_marks_failover_state():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / 'bot_config.py').write_text(
            (APP_ROOT / 'bot_config.example.py').read_text(encoding='utf-8'),
            encoding='utf-8',
        )
        script = (
            "import json, sys\n"
            f"sys.path.insert(0, {str(APP_ROOT)!r})\n"
            f"sys.path.insert(0, {str(root)!r})\n"
            "import bot\n"
            "bot.auto_failover_state.update(last_ok=123.0, last_fail=0.0, "
            "last_failure_message='', consecutive_failures=0)\n"
            "bot._prime_auto_failover_after_telegram_failure('forced failure')\n"
            "primed_last_ok = bot.auto_failover_state['last_ok']\n"
            "events = []\n"
            "bot._mark_active_telegram_failure = lambda _error: events.append('mark')\n"
            "bot._reset_telegram_http_session = lambda reason='': events.append('reset:' + reason)\n"
            "handler = bot._TelegramPollingExceptionHandler()\n"
            "bot.bot_polling = True\n"
            "first = handler.handle(ConnectionError('connection reset'))\n"
            "bot.bot_polling = True\n"
            "second = handler.handle(ConnectionError('connection reset'))\n"
            "polling_after_exception = bot.bot_polling\n"
            "bot._invalidate_web_status_api_cache = lambda: events.append('invalidate-api')\n"
            "bot._invalidate_web_status_cache = lambda: events.append('invalidate-status')\n"
            "bot.auto_failover_state.update(last_ok=456.0, last_fail=0.0, "
            "last_failure_message='', consecutive_failures=0)\n"
            "restored = bot._restore_telegram_polling_after_verified_recovery()\n"
            "print(json.dumps({'first': first, 'second': second, 'polling_after_exception': polling_after_exception, "
            "'polling_after_recovery': bot.bot_polling, 'restored': restored, "
            "'events': events, 'primed_last_ok': primed_last_ok}, sort_keys=True))\n"
        )
        env = os.environ.copy()
        env['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        assert json.loads(result.stdout) == {
            'events': [
                'mark',
                'reset:internal polling error',
                'invalidate-api',
                'invalidate-status',
            ],
            'first': False,
            'polling_after_exception': False,
            'polling_after_recovery': True,
            'primed_last_ok': 0.0,
            'restored': True,
            'second': False,
        }


def test_auto_failover_defers_when_health_worker_result_is_unknown():
    state = {
        'in_progress': False,
        'last_attempt': 0.0,
        'last_fail': 0.0,
        'last_ok': 0.0,
        'consecutive_failures': 0,
        'last_failure_message': '',
    }
    logs = []
    switched = auto_failover_runtime.attempt_auto_failover(
        state=state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='socks5://127.0.0.1:10811',
        check_telegram_api=lambda *_args, **_kwargs: (None, 'worker unavailable'),
        load_current_keys=lambda: {'vless': 'active'},
        load_key_pools=lambda: {'vless': ['candidate']},
        failover_candidates=lambda *_args, **_kwargs: [('vless', 'candidate')],
        find_pool_failover_candidate=lambda *_args, **_kwargs: ('vless', 'candidate', True, True),
        install_key_for_protocol=lambda *_args, **_kwargs: 'installed',
        update_proxy=lambda *_args, **_kwargs: (True, ''),
        set_active_key=lambda *_args, **_kwargs: None,
        record_key_probe=lambda *_args, **_kwargs: None,
        log=logs.append,
        grace_seconds=0,
        switch_cooldown_seconds=0,
        startup_hold_seconds=0,
        min_consecutive_failures=1,
    )
    assert switched is False
    assert state['last_fail'] == 0.0
    assert state['consecutive_failures'] == 0
    assert any('did not return a result' in message for message in logs)


def test_health_check_runner_writes_sanitized_unsupported_result():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        input_path = root / 'input.json'
        result_path = root / 'result.json'
        input_path.write_text(json.dumps({'kind': 'unsupported'}), encoding='utf-8')
        assert health_check_runner.run_health_check_worker(str(input_path), str(result_path)) == 1
        result = json.loads(result_path.read_text(encoding='utf-8'))
        assert result['ok'] is False
        assert result['error'] == 'unsupported health check kind: unsupported'
        assert result['rss_before_kb'] >= 0
        assert result['hwm_kb'] >= 0


def test_health_check_worker_command_uses_narrow_runner():
    source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    worker_block = source.split('def _health_check_process_worker_code', 1)[1].split(
        'def _run_health_check_process_worker', 1
    )[0]
    assert 'import health_check_runner as runner' in worker_block
    assert 'import main as bot_module' not in worker_block
    assert 'health_check_runner.py' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'health_check_runner.py' in (ROOT / 'bootstrap' / 'install.sh').read_text(encoding='utf-8')


def test_failover_candidate_worker_command_uses_narrow_runner():
    source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    worker_block = source.split('def _failover_candidate_process_worker_code', 1)[1].split(
        'def _health_check_process_worker_code', 1
    )[0]
    assert 'import failover_candidate_runner as runner' in worker_block
    assert 'import main as bot_module' not in worker_block
    assert 'failover_candidate_runner.py' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'failover_candidate_runner.py' in (ROOT / 'bootstrap' / 'install.sh').read_text(encoding='utf-8')
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        input_path = root / 'input.json'
        result_path = root / 'result.json'
        input_path.write_text(json.dumps({'service': 'telegram', 'candidates': []}), encoding='utf-8')
        assert failover_candidate_runner.run_failover_candidate_worker(str(input_path), str(result_path)) == 2
        result = json.loads(result_path.read_text(encoding='utf-8'))
        assert result['ok'] is False
        assert result['candidate'] is None
        assert result['hwm_kb'] >= 0


def test_pool_probe_worker_command_uses_narrow_runner():
    source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    worker_block = source.split('def _pool_probe_process_worker_code', 1)[1].split(
        'def _run_pool_probe_process_worker', 1
    )[0]
    assert 'import pool_probe_process_runner as runner' in worker_block
    assert 'import main as bot_module' not in worker_block
    assert 'pool_probe_process_runner.py' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'pool_probe_process_runner.py' in (ROOT / 'bootstrap' / 'install.sh').read_text(encoding='utf-8')
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        input_path = root / 'input.json'
        progress_path = root / 'progress.json'
        result_path = root / 'result.json'
        cancel_path = root / 'cancel'
        input_path.write_text(json.dumps({'tasks': [], 'checks': []}), encoding='utf-8')
        assert pool_probe_process_runner.run_pool_probe_process_worker(
            str(input_path), str(progress_path), str(result_path), str(cancel_path)
        ) == 0
        result = json.loads(result_path.read_text(encoding='utf-8'))
        assert result['ok'] is True
        assert result['checked'] == 0
        assert result['hwm_kb'] >= 0


def test_pool_probe_curl_helpers_do_not_import_requests():
    class Result:
        returncode = 0
        stderr = b''
        stdout = b'\n__BK_HTTP_CODE__204\n__BK_URL__https://example.com/final'

    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        Path(args[args.index('--output') + 1]).write_bytes(b'ok')
        return Result()

    status_code, final_url, body, error = pool_probe_curl._run_curl(
        'socks5://127.0.0.1:10811',
        'https://example.com/',
        2,
        3,
        command_runner=fake_run,
    )
    assert (status_code, final_url, body, error) == (204, 'https://example.com/final', b'ok', '')
    assert '--proxy' in calls[0][0]
    assert 'socks5h://127.0.0.1:10811' in calls[0][0]
    assert '--config' in calls[0][0]
    assert '--output' in calls[0][0]
    assert 'https://example.com/' not in calls[0][0]
    assert b'https://example.com/' in calls[0][1]['input']
    assert not Path(calls[0][0][calls[0][0].index('--output') + 1]).exists()
    original_run_curl = pool_probe_curl._run_curl
    try:
        pool_probe_curl._run_curl = lambda *args, **kwargs: (0, '', b'', '')
        assert pool_probe_curl.check_http_through_proxy('socks5://127.0.0.1:10811', 'https://example.com/')[0] is False
        assert pool_probe_curl.check_custom_target_through_proxy(
            lambda value: 'https://example.com/',
            'socks5://127.0.0.1:10811',
            'example.com',
        )[0] is False
        assert pool_probe_curl.check_telegram_api(False, 'socks5://127.0.0.1:10811')[0] is False
    finally:
        pool_probe_curl._run_curl = original_run_curl
    assert 'import requests' not in (APP_ROOT / 'pool_probe_curl.py').read_text(encoding='utf-8')
    assert proxy_status.CUSTOM_TARGET_DENY_MARKERS == custom_check_policy.CUSTOM_TARGET_DENY_MARKERS
    runner_source = (APP_ROOT / 'pool_probe_process_runner.py').read_text(encoding='utf-8')
    assert 'curl_check_telegram' in runner_source
    assert 'check_http=curl_check_http' in runner_source
    assert 'pool_probe_curl.py' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'pool_probe_curl.py' in (ROOT / 'bootstrap' / 'install.sh').read_text(encoding='utf-8')
    assert 'custom_check_policy.py' in (ROOT / 'script.sh').read_text(encoding='utf-8')
    assert 'custom_check_policy.py' in (ROOT / 'bootstrap' / 'install.sh').read_text(encoding='utf-8')


def test_pool_probe_worker_streams_hashed_records_without_cache_import():
    with tempfile.TemporaryDirectory() as directory:
        records_path = Path(directory) / 'records.jsonl'
        recorder = pool_probe_process_runner._WorkerProbeRecorder(
            {('vless', 'key'): 'hash-id'},
            str(records_path),
        )
        recorder.record('vless', 'key', tg_ok=True, yt_ok=True, allow_recent_success_downgrade=True)
        recorder.record('vless', 'key', custom={'service': True}, custom_checks=[{'id': 'service'}])
        assert recorder.close() == str(records_path)
        records = [json.loads(line) for line in records_path.read_text(encoding='utf-8').splitlines()]
    assert records == [{
        'key_id': 'hash-id',
        'proto': 'vless',
        'values': {'tg_ok': True, 'yt_ok': True, 'allow_recent_success_downgrade': True},
    }, {
        'key_id': 'hash-id',
        'proto': 'vless',
        'values': {'custom': {'service': True}, 'custom_checks': [{'id': 'service'}]},
    }]
    source = (APP_ROOT / 'pool_probe_process_runner.py').read_text(encoding='utf-8')
    worker_source = source.split('def apply_pool_probe_records_file', 1)[0]
    assert 'from probe_cache import' not in worker_source
    assert "result['probe_records_path'] = recorder.close()" in source
    assert 'threading.stack_size(128 * 1024)' in source


def test_pool_probe_records_apply_in_disposable_worker(tmp_path, monkeypatch):
    records_path = tmp_path / 'records.jsonl'
    result_path = tmp_path / 'apply.json'
    records_path.write_text(
        '\n'.join((
            json.dumps({'key_id': 'hash-one', 'proto': 'vless', 'values': {'tg_ok': True}}),
            json.dumps({'key_id': 'hash-two', 'proto': 'vless2', 'values': {'yt_ok': True, 'custom': {'chat': True}}}),
            '{invalid json}',
        )),
        encoding='utf-8',
    )
    cache = {}
    saved = []

    def update_entry(current, proto, _key_value, *, key_id, **updates):
        current[(proto, key_id)] = dict(updates)
        return True

    monkeypatch.setattr(probe_cache, 'load_key_probe_cache', lambda: cache)
    monkeypatch.setattr(probe_cache, 'save_key_probe_cache', lambda current: saved.append(dict(current)))
    monkeypatch.setattr(probe_cache, 'update_key_probe_cache_entry', update_entry)
    assert pool_probe_process_runner.run_pool_probe_records_apply_worker(
        str(records_path), str(result_path)
    ) == 0
    result = json.loads(result_path.read_text(encoding='utf-8'))
    assert result == {'ok': True, 'applied': 2, 'error': ''}
    assert cache[('vless', 'hash-one')]['tg_ok'] is True
    assert cache[('vless2', 'hash-two')]['custom'] == {'chat': True}
    assert len(saved) == 1


def test_pool_probe_completion_log_separates_bot_and_worker_hwm():
    source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    assert "f'bot_hwm={int(bot_hwm_kb or 0)} KB'" in source
    assert "f'worker_hwm={int(worker_hwm_kb or 0)} KB'" in source
    assert 'def _apply_pool_probe_records_in_worker(records_path):' in source
    assert 'def _apply_pool_probe_records(records):' not in source
    process_monitor = source.split('def _start_selected_pool_probe_process', 1)[1].split('def _start_selected_pool_probe_tasks', 1)[0]
    assert '_apply_pool_probe_records_in_worker(records_path)' in process_monitor
    assert "worker_hwm_kb=int(result.get('hwm_kb') or 0)" in process_monitor
    assert "bot_hwm_kb=int(_process_hwm_kb() or 0)" in process_monitor


def test_web_assets_are_cached_once_without_request_icons():
    styles = web_form_template.render_web_style_asset('ignored')
    scripts = web_form_template.render_web_script_asset(csrf_token='ignored')
    assert styles == (APP_ROOT / 'static' / 'app.css').read_text(encoding='utf-8')
    assert scripts == (APP_ROOT / 'static' / 'app.js').read_text(encoding='utf-8')


def test_telegram_confirm_state_source():
    source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    install_source = (APP_ROOT / 'telegram_install_ui.py').read_text(encoding='utf-8')
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


    secret_message = type('Message', (), {})()
    secret_message.text = (
        'vless://uuid@example.test:443?security=tls#secret '
        'https://subscription.example.test/path?token=secret '
        'bot=123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    )
    debug_text = telegram_auth_state.message_debug_text(secret_message)
    assert 'vless://' not in debug_text
    assert 'subscription.example.test' not in debug_text
    assert 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' not in debug_text
    assert '<proxy-key-hidden>' in debug_text
    logs = []
    telegram_auth_state.authorize_message(secret_message, 'secret', set(), set(), log_callback=logs.append)
    assert logs and 'vless://' not in logs[0] and 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' not in logs[0]


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
    assert telegram_key_ui.key_menu_rows()[:3] == (
        ('Vless 1', 'Vless 2'),
        ('Vmess', 'Trojan'),
        ('Shadowsocks',),
    )
    assert ('📦 Пул ключей' in telegram_key_ui.key_menu_rows(include_pool=True)[3])
    assert telegram_key_ui.key_input_level('Trojan', trojan_level=13) == 13
    assert telegram_key_ui.key_input_level('Vless 2', trojan_level=13) == 12
    assert telegram_key_ui.key_install_protocol(13, trojan_level=13) == 'trojan'
    assert telegram_key_ui.key_install_protocol(12, trojan_level=13) == 'vless2'
    assert 'http://192.168.1.1:8080/' in telegram_key_ui.browser_hint('192.168.1.1', 8080)
    bot_source = (ROOT / 'app' / 'bot.py').read_text(encoding='utf-8')
    report_start = bot_source.index('def _send_key_status_report(')
    report_end = bot_source.index('\ndef ', report_start + 1)
    assert 'for proto in POOL_PROTOCOL_ORDER:' in bot_source[report_start:report_end]


def test_proxy_diagnostics_redact_credential_ids():
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
    try:
        bot_module = importlib.import_module('bot')
        vless_id = '11111111-2222-3333-4444-555555555555'
        vless_key = f'vless://{vless_id}@example.com:443?security=tls&type=tcp&sni=sni.example#sample'
        vless_diag = bot_module._build_proxy_diagnostics('vless', vless_key)
        assert vless_id not in vless_diag
        assert 'uuid=' not in vless_diag
        assert 'key_hash=sha256:' in vless_diag

        vmess_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        vmess_key = 'vmess://' + base64.b64encode(json.dumps({
            'v': '2',
            'ps': 'sample',
            'add': 'vmess.example.com',
            'port': '443',
            'id': vmess_id,
            'aid': '0',
            'net': 'tcp',
            'type': 'none',
            'host': '',
            'tls': 'tls',
        }).encode('utf-8')).decode('ascii').rstrip('=')
        vmess_diag = bot_module._build_proxy_diagnostics('vmess', vmess_key)
        assert vmess_id not in vmess_diag
        assert 'id=' not in vmess_diag
        assert 'key_hash=sha256:' in vmess_diag

        original = {
            'rss': bot_module._process_rss_kb,
            'clear': bot_module._clear_runtime_memory_caches,
            'collect': bot_module.gc.collect,
            'trim': bot_module._malloc_trim,
            'timeline': bot_module._record_memory_timeline,
            'trim_min': bot_module.MEMORY_MALLOC_TRIM_MIN_RSS_KB,
        }
        trim_calls = []
        try:
            bot_module.MEMORY_MALLOC_TRIM_MIN_RSS_KB = 61440
            bot_module._process_rss_kb = lambda: 65000
            bot_module._clear_runtime_memory_caches = lambda **_kwargs: None
            bot_module.gc.collect = lambda: 0
            bot_module._record_memory_timeline = lambda *_args, **_kwargs: None
            bot_module._malloc_trim = lambda *_args, **kwargs: trim_calls.append(kwargs) or {
                'attempted': True,
                'ok': True,
                'result': 1,
                'available': True,
            }
            result = bot_module._memory_cleanup('test threshold', force=True, clear_status=False, log=False)
            assert len(trim_calls) == 1
            assert trim_calls[0]['rss_kb'] == 65000
            assert result['malloc_trim']['attempted'] is True
        finally:
            bot_module._process_rss_kb = original['rss']
            bot_module._clear_runtime_memory_caches = original['clear']
            bot_module.gc.collect = original['collect']
            bot_module._malloc_trim = original['trim']
            bot_module._record_memory_timeline = original['timeline']
            bot_module.MEMORY_MALLOC_TRIM_MIN_RSS_KB = original['trim_min']
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
            ('Vless 1', 'vless'),
            ('Vless 2', 'vless-2'),
            ('Vmess', 'vmess'),
            ('Trojan', 'trojan'),
            ('Shadowsocks', 'shadowsocks'),
        ]

        assert bot_module.AUTHORIZED_USERNAMES == {'alloweduser'}
        assert bot_module.AUTHORIZED_USER_IDS == set()
        assert bot_module._build_main_menu_markup().rows == [
            ['🔰 Установка и удаление'],
            ['🔑 Ключи', '📝 Списки обхода'],
            ['📄 Информация', '⚙️ Сервис'],
        ]
        assert ['♻️ Перезагрузить сервисы', '‼️Перезагрузить роутер'] in bot_module._build_service_menu_markup().rows
        assert bot_module._build_keys_menu_markup().rows[:3] == [
            ['Vless 1', 'Vless 2'],
            ['Vmess', 'Trojan'],
            ['Shadowsocks'],
        ]
        service_labels = [label for row in bot_module._service_list_markup().rows[:-1] for label in row]
        assert service_labels.count('Grok / X / Twitter') == 1
        assert 'X / Twitter' not in service_labels
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
    assert state['last_failure_message'] == ''
    assert state['last_fail'] == 0.0
    assert ('update', 'vless') in calls
    assert any(call[0] == 'probe' and call[3] == {'tg_ok': True, 'yt_ok': None} for call in calls)
    transient_calls = []
    transient_state = {
        'last_ok': 0.0,
        'last_fail': 1.0,
        'last_failure_message': 'SSLEOFError: UNEXPECTED_EOF_WHILE_READING',
        'last_attempt': 0.0,
        'in_progress': False,
    }
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
    last_ok_state = {
        'last_ok': 19.0,
        'last_fail': 1.0,
        'last_failure_message': 'Read timed out',
        'last_attempt': 0.0,
        'in_progress': False,
    }
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
    assert last_ok_state['last_failure_message'] == ''
    assert not any(call[0] == 'install' for call in last_ok_calls)
    recent_probe_calls = []
    recent_probe_state = {'last_ok': 0.0, 'last_fail': 1.0, 'last_attempt': 0.0, 'in_progress': False}
    assert auto_failover_runtime.attempt_auto_failover(
        state=recent_probe_state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: recent_probe_calls.append(('check', kwargs)) or (False, 'TLS EOF'),
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
    assert not any(call[0] == 'check' for call in recent_probe_calls)
    assert not any(call[0] == 'install' for call in recent_probe_calls)
    fresh_fail_calls = []
    fresh_fail_state = {'last_ok': 0.0, 'last_fail': 95.0, 'last_attempt': 0.0, 'in_progress': False}
    assert auto_failover_runtime.attempt_auto_failover(
        state=fresh_fail_state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: fresh_fail_calls.append(('check', kwargs)) or (False, 'fail'),
        load_current_keys=lambda: {'vless': 'active'},
        load_key_pools=lambda: {'vless': ['active', 'next']},
        failover_candidates=lambda pools, mode, active, protocols=(), **kwargs: [('vless', 'next')],
        find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
        install_key_for_protocol=lambda proto, key, verify=True: fresh_fail_calls.append(('install', proto, key)),
        update_proxy=lambda proto: fresh_fail_calls.append(('update', proto)),
        set_active_key=lambda proto, key: fresh_fail_calls.append(('active', proto, key)),
        record_key_probe=lambda proto, key, **kwargs: fresh_fail_calls.append(('probe', proto, key, kwargs)),
        log=lambda message: fresh_fail_calls.append(('log', message)),
        grace_seconds=60,
        switch_cooldown_seconds=30,
        time_provider=lambda: 120.0,
    ) is False
    assert fresh_fail_calls == []
    first_success_calls = []
    first_success_state = {'last_ok': 0.0, 'last_fail': 0.0, 'last_attempt': 0.0, 'in_progress': False}
    assert auto_failover_runtime.attempt_auto_failover(
        state=first_success_state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: first_success_calls.append(('check', kwargs)) or (True, 'ok'),
        load_current_keys=lambda: {'vless': 'active'},
        load_key_pools=lambda: {'vless': ['active', 'next']},
        failover_candidates=lambda pools, mode, active, protocols=(), **kwargs: [('vless', 'next')],
        find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
        install_key_for_protocol=lambda proto, key, verify=True: first_success_calls.append(('install', proto, key)),
        update_proxy=lambda proto: first_success_calls.append(('update', proto)),
        set_active_key=lambda proto, key: first_success_calls.append(('active', proto, key)),
        record_key_probe=lambda proto, key, **kwargs: first_success_calls.append(('probe', proto, key, kwargs)),
        log=lambda message: first_success_calls.append(('log', message)),
        grace_seconds=60,
        switch_cooldown_seconds=30,
        time_provider=lambda: 120.0,
    ) is False
    assert ('probe', 'vless', 'active', {'tg_ok': True, 'yt_ok': None}) in first_success_calls
    recent_repair_calls = []
    recent_repair_state = {'last_ok': 0.0, 'last_fail': 1.0, 'last_attempt': 0.0, 'in_progress': False}
    assert auto_failover_runtime.attempt_auto_failover(
        state=recent_repair_state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: (False, 'TLS EOF'),
        load_current_keys=lambda: {'vless': 'active'},
        load_key_pools=lambda: {'vless': ['active', 'next']},
        failover_candidates=lambda pools, mode, active, protocols=(), **kwargs: [('vless', 'next')],
        find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
        install_key_for_protocol=lambda proto, key, verify=True: recent_repair_calls.append(('install', proto, key)),
        update_proxy=lambda proto: recent_repair_calls.append(('update', proto)),
        set_active_key=lambda proto, key: recent_repair_calls.append(('active', proto, key)),
        record_key_probe=lambda proto, key, **kwargs: recent_repair_calls.append(('probe', proto, key, kwargs)),
        log=lambda message: recent_repair_calls.append(('log', message)),
        grace_seconds=10,
        switch_cooldown_seconds=30,
        key_probe_cache={'active-hash': {'tg_ok': True, 'ts': 19.0}},
        hash_key=lambda key: f'{key}-hash',
        recent_success_ttl=60,
        repair_active_proxy=lambda proto, message: recent_repair_calls.append(('repair', proto, message)) or True,
        time_provider=lambda: 20.0,
    ) is False
    assert not any(call[0] == 'repair' for call in recent_repair_calls)
    confirm_calls = []
    confirm_state = {'last_ok': 0.0, 'last_fail': 1.0, 'last_attempt': 0.0, 'in_progress': False}
    confirm_results = iter([(True, 'confirm ok')])
    assert auto_failover_runtime.attempt_auto_failover(
        state=confirm_state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: confirm_calls.append(('check', kwargs)) or next(confirm_results),
        load_current_keys=lambda: {'vless': 'active'},
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
        ('check', {'connect_timeout': 5.0, 'read_timeout': 8.0}),
        ('probe', 'vless', 'active', {'tg_ok': True, 'yt_ok': None}),
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
    assert 'check' not in startup_hold_calls
    assert not any(isinstance(call, tuple) and call[0] == 'install' for call in startup_hold_calls)
    repair_calls = []
    repair_state = {
        'last_ok': 0.0,
        'last_fail': 1.0,
        'last_failure_message': 'previous failure',
        'last_attempt': 0.0,
        'in_progress': False,
    }
    repair_checks = iter([(False, 'confirm fail'), (True, 'after repair')])
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
    assert repair_state['last_failure_message'] == ''
    assert any(call[0] == 'repair' for call in repair_calls)
    assert not any(call[0] == 'install' for call in repair_calls)
    assert any(call[0] == 'log' and 'endpoint repair restored' in call[1] for call in repair_calls)

    repeated_calls = []
    repeated_state = {
        'last_ok': 0.0,
        'last_fail': 1.0,
        'last_attempt': 0.0,
        'consecutive_failures': 0,
        'in_progress': False,
    }

    def repeated_attempt(now_value):
        return auto_failover_runtime.attempt_auto_failover(
            state=repeated_state,
            pool_probe_locked=lambda: False,
            proxy_mode='vless',
            proxy_url='proxy',
            check_telegram_api=lambda proxy, **kwargs: (False, 'fail'),
            load_current_keys=lambda: {'vless': 'active'},
            load_key_pools=lambda: {'vless': ['active', 'next']},
            failover_candidates=lambda pools, mode, active, protocols=(), **kwargs: [('vless', 'next')],
            find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
            install_key_for_protocol=lambda proto, key, verify=True: repeated_calls.append(('install', proto, key, verify)) or 'ok',
            update_proxy=lambda proto: repeated_calls.append(('update', proto)),
            set_active_key=lambda proto, key: repeated_calls.append(('active', proto, key)),
            record_key_probe=lambda proto, key, **kwargs: repeated_calls.append(('probe', proto, key, kwargs)),
            log=lambda message: repeated_calls.append(('log', message)),
            grace_seconds=10,
            switch_cooldown_seconds=30,
            min_consecutive_failures=3,
            time_provider=iter([now_value, now_value + 1]).__next__,
        )

    assert repeated_attempt(20.0) is False
    assert repeated_state['consecutive_failures'] == 1
    assert not any(call[0] == 'install' for call in repeated_calls)
    assert repeated_attempt(30.0) is False
    assert repeated_state['consecutive_failures'] == 2
    assert not any(call[0] == 'install' for call in repeated_calls)
    assert repeated_attempt(40.0) is True
    assert repeated_state['consecutive_failures'] == 0
    assert ('update', 'vless') in repeated_calls

    deferred_calls = []
    deferred_state = {
        'last_ok': 0.0,
        'last_fail': 1.0,
        'last_attempt': 0.0,
        'consecutive_failures': 0,
        'in_progress': False,
    }
    assert auto_failover_runtime.attempt_auto_failover(
        state=deferred_state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: (False, 'fail'),
        load_current_keys=lambda: {'vless': 'active'},
        load_key_pools=lambda: {'vless': ['active', 'next']},
        failover_candidates=lambda pools, mode, active, protocols=(), **kwargs: [('vless', 'next')],
        find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
        install_key_for_protocol=lambda proto, key, verify=True: deferred_calls.append(('install', proto, key, verify)) or 'ok',
        update_proxy=lambda proto: deferred_calls.append(('update', proto)),
        set_active_key=lambda proto, key: deferred_calls.append(('active', proto, key)),
        record_key_probe=lambda proto, key, **kwargs: deferred_calls.append(('probe', proto, key, kwargs)),
        log=lambda message: deferred_calls.append(('log', message)),
        grace_seconds=10,
        switch_cooldown_seconds=30,
        min_consecutive_failures=1,
        defer_switch=lambda **kwargs: deferred_calls.append(('defer', kwargs['state']['consecutive_failures'])) or True,
        time_provider=iter([20.0, 21.0]).__next__,
    ) is False
    assert deferred_state['consecutive_failures'] == 1
    assert ('defer', 1) in deferred_calls
    assert not any(call[0] == 'install' for call in deferred_calls)

    exclude_calls = []
    exclude_state = {
        'last_ok': 0.0,
        'last_fail': 1.0,
        'last_attempt': 0.0,
        'consecutive_failures': 0,
        'in_progress': False,
    }

    def exclude_failover_candidates(pools, mode, active, protocols=(), **kwargs):
        exclude_calls.append(('exclude', tuple(sorted(kwargs.get('exclude_keys') or ()))))
        return [('vless', 'next')]

    assert auto_failover_runtime.attempt_auto_failover(
        state=exclude_state,
        pool_probe_locked=lambda: False,
        proxy_mode='vless',
        proxy_url='proxy',
        check_telegram_api=lambda proxy, **kwargs: (False, 'fail'),
        load_current_keys=lambda: {'vless': 'active', 'vless2': 'other-active'},
        load_key_pools=lambda: {'vless': ['active', 'other-active', 'next']},
        failover_candidates=exclude_failover_candidates,
        find_pool_failover_candidate=lambda candidates, service='telegram': ('vless', 'next', True, None),
        install_key_for_protocol=lambda proto, key, verify=True: exclude_calls.append(('install', proto, key, verify)) or 'ok',
        update_proxy=lambda proto: exclude_calls.append(('update', proto)),
        set_active_key=lambda proto, key: exclude_calls.append(('active', proto, key)),
        record_key_probe=lambda proto, key, **kwargs: exclude_calls.append(('probe', proto, key, kwargs)),
        log=lambda message: exclude_calls.append(('log', message)),
        grace_seconds=10,
        switch_cooldown_seconds=30,
        min_consecutive_failures=1,
        time_provider=lambda: 20.0,
    ) is True
    assert ('exclude', ('other-active',)) in exclude_calls
    assert ('install', 'vless', 'next', False) in exclude_calls


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
        return True, 'probe'

    youtube_ok, _ = proxy_apply_runtime.check_youtube_health(
        proxy_apply_youtube_check,
        'proxy-url',
        timeouts=(1, 1),
    )
    assert youtube_ok is True
    assert youtube_calls == list(youtube_healthcheck.YOUTUBE_HEALTHCHECK_QUICK_URLS)

    full_youtube_calls = []
    youtube_ok, _ = proxy_apply_runtime.check_youtube_health(
        lambda proxy, **kwargs: full_youtube_calls.append(kwargs['url']) or (True, 'probe'),
        'proxy-url',
        timeouts=(1, 1),
        profile='full',
    )
    assert youtube_ok is True
    assert full_youtube_calls == list(proxy_apply_runtime.YOUTUBE_HEALTHCHECK_URLS)

    primary_transient_ok, primary_transient_message = proxy_apply_runtime.check_youtube_health(
        lambda proxy, **kwargs: (
            kwargs['url'] != proxy_apply_runtime.YOUTUBE_HEALTHCHECK_URLS[0],
            'primary eof',
        ),
        'proxy-url',
        timeouts=(1, 1),
    )
    assert primary_transient_ok is True
    assert 'soft diagnostic issue' in primary_transient_message

    short_transient_ok, short_transient_message = proxy_apply_runtime.check_youtube_health(
        lambda proxy, **kwargs: (
            kwargs['url'] != proxy_apply_runtime.YOUTUBE_SHORT_URL,
            'short eof',
        ),
        'proxy-url',
        timeouts=(1, 1),
    )
    assert short_transient_ok is False
    assert 'Required YouTube endpoint' in short_transient_message

    googlevideo_attempts = {'count': 0}
    def googlevideo_transient_check(proxy, **kwargs):
        if 'redirector.googlevideo.com' in kwargs['url'] and googlevideo_attempts['count'] == 0:
            googlevideo_attempts['count'] += 1
            return False, 'googlevideo eof'
        return True, 'ok'

    googlevideo_transient_ok, _ = proxy_apply_runtime.check_youtube_health(
        googlevideo_transient_check,
        'proxy-url',
        timeouts=(1, 1),
    )
    assert googlevideo_transient_ok is True
    assert googlevideo_attempts['count'] == 1

    commands = []
    sleeps = []
    records = []
    ensure_calls = []
    result = proxy_apply_runtime.apply_installed_proxy_runtime(
        'vless',
        'key',
        settings=settings,
        app_mode_noun='режим бота',
        load_proxy_mode=lambda: 'none',
        proxy_mode_label=lambda mode: 'Без прокси',
        proxy_url_getter=lambda proto: 'proxy-url',
        build_diagnostics=lambda proto, key: 'diag',
        ensure_service_port=lambda port, restart_cmd, **kwargs: ensure_calls.append((port, restart_cmd, kwargs)) or True,
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
    assert ensure_calls[0][2]['timeout'] == 18
    assert len(records) == 1
    assert records[0][0:2] == ('vless', 'key')
    assert records[0][2]['tg_ok'] is True
    assert records[0][2]['yt_ok'] is False
    assert records[0][2]['yt_stability'] == 'fail'
    pending_ensure_calls = []
    pending = proxy_apply_runtime.apply_installed_proxy_runtime(
        'trojan',
        'key',
        settings=settings,
        app_mode_noun='режим бота',
        load_proxy_mode=lambda: 'trojan',
        proxy_mode_label=lambda mode: 'Trojan',
        proxy_url_getter=lambda proto: 'unused',
        build_diagnostics=lambda proto, key: '',
        ensure_service_port=lambda port, restart_cmd, **kwargs: pending_ensure_calls.append((port, restart_cmd, kwargs)) or True,
        check_local_endpoint=lambda proto, port: (True, 'SOCKS ok.'),
        check_telegram_api=lambda proxy, **kwargs: (_ for _ in ()).throw(AssertionError('must not verify')),
        verify=False,
        run_command=lambda command: None,
        sleep=lambda seconds: None,
    )
    assert 'в фоне' in pending
    assert pending_ensure_calls[0][2]['timeout'] == 5
    assert pending_ensure_calls[0][1] is None
    assert pending_ensure_calls[0][2]['retries'] == 0
    fallback_ensure_calls = []
    fallback_results = iter([False, True])
    fallback_pending = proxy_apply_runtime.apply_installed_proxy_runtime(
        'trojan',
        'key',
        settings=settings,
        app_mode_noun='режим бота',
        load_proxy_mode=lambda: 'trojan',
        proxy_mode_label=lambda mode: 'Trojan',
        proxy_url_getter=lambda proto: 'unused',
        build_diagnostics=lambda proto, key: '',
        ensure_service_port=lambda port, restart_cmd, **kwargs: (
            fallback_ensure_calls.append((port, restart_cmd, kwargs)) or next(fallback_results)
        ),
        check_local_endpoint=lambda proto, port: (True, 'SOCKS ok.'),
        check_telegram_api=lambda proxy, **kwargs: (_ for _ in ()).throw(AssertionError('must not verify')),
        verify=False,
        run_command=lambda command: None,
        sleep=lambda seconds: None,
    )
    assert 'в фоне' in fallback_pending
    assert [call[2]['timeout'] for call in fallback_ensure_calls] == [5, 8]
    assert all(call[1] is None for call in fallback_ensure_calls)
    assert all(call[2]['retries'] == 0 for call in fallback_ensure_calls)
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
    assert len(vless2_records) == 1
    assert vless2_records[0][0:2] == ('vless2', 'yt-key')
    assert vless2_records[0][2]['tg_ok'] is None
    assert vless2_records[0][2]['yt_ok'] is True
    assert vless2_records[0][2]['yt_stability'] == 'stable'

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
    assert len(routed_vless_records) == 1
    assert routed_vless_records[0][0:2] == ('vless', 'yt-on-vless1')
    assert routed_vless_records[0][2]['tg_ok'] is None
    assert routed_vless_records[0][2]['yt_ok'] is True
    assert routed_vless_records[0][2]['yt_stability'] == 'stable'


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
    ) == 155.0
    assert pool_probe_controller.pool_probe_timeout_budget(
        [{'urls': ['https://a', 'https://b']}],
        1,
        1,
        (1, 2, 3, 4, 5, 6, 10, 20, 7, 8),
    ) == 125.0
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
    selected, _ = pool_probe_controller.select_pool_probe_tasks(
        [('vless', 'same-key'), ('vless2', 'same-key'), ('vless2', 'other-key')],
        protocol_order=('vless', 'vless2'),
        custom_checks=[],
        cache={},
        hash_key=lambda value: 'h:' + value,
        is_fresh=lambda probe, **kwargs: False,
    )
    assert selected == [('vless', 'same-key'), ('vless2', 'other-key')]
    assert pool_probe_controller.filter_active_probe_tasks(
        [('vless', 'active'), ('vmess', 'old')],
        {'vless': 'active', 'vmess': 'new'},
    ) == [('vless', 'active')]

    state = {}
    invalidated = []
    collected = []
    task_list = [('vless', 'key')]
    worker_task_ref = {}
    times = iter([10.0, 20.0])

    def set_progress(**updates):
        state.update(updates)

    def run_worker(tasks, checks, set_checked, invalidate_caches):
        worker_task_ref['tasks'] = tasks
        assert tasks == [('vless', 'key')]
        assert checks == [{'id': 'custom'}]
        set_checked(1)
        invalidate_caches()
        return 1, len(tasks)

    started, count = pool_probe_controller.start_pool_probe_worker(
        task_list,
        [{'id': 'custom'}],
        scope='manual_all',
        lock=threading.Lock(),
        set_progress=set_progress,
        run_worker=run_worker,
        invalidate_caches=lambda: invalidated.append('cache'),
        time_provider=lambda: next(times),
        collect_garbage=lambda: collected.append(('gc', list(worker_task_ref['tasks']))),
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
    assert task_list == [('vless', 'key')]
    assert collected == [('gc', [])]

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

    class _FailingThread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            raise RuntimeError('thread start failed')

    failed_state = {}
    failed_lock = threading.Lock()
    collected_after_start_failure = []
    started, count = pool_probe_controller.start_pool_probe_worker(
        [('vless', 'cannot-start')],
        [],
        scope='manual_all',
        lock=failed_lock,
        set_progress=lambda **updates: failed_state.update(updates),
        run_worker=lambda *_args, **_kwargs: (0, 0),
        invalidate_caches=lambda: None,
        time_provider=lambda: 50.0,
        collect_garbage=lambda: collected_after_start_failure.append(True),
        thread_factory=_FailingThread,
    )
    assert started is False
    assert count == 1
    assert failed_state['running'] is False
    assert failed_state['note'] == 'Не удалось запустить проверку пула.'
    assert not failed_lock.locked()
    assert collected_after_start_failure == [True]

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
    assert len(records) == 2
    assert records[0][0:2] == ('vless', 'key')
    assert records[0][2]['tg_ok'] is False
    assert records[0][2]['yt_ok'] is False
    assert records[0][2]['yt_stability'] == 'fail'
    assert records[1] == (
        'vless',
        'key',
        {
            'custom': {'custom': False},
            'custom_checks': [{'id': 'custom'}],
            'allow_recent_success_downgrade': True,
        },
    )

    records = []
    http_calls = []
    def check_http_for_pool_key(proxy, **kwargs):
        http_calls.append(kwargs)
        if kwargs.get('url') == 'https://web.telegram.org/':
            return True, 'telegram ok'
        return True, 'ok'

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
        {'url': 'https://web.telegram.org/', 'connect_timeout': 1.0, 'read_timeout': 1.5},
    ] + [
        {
            'url': url,
            'connect_timeout': 3,
            'read_timeout': 4,
        }
        for url in youtube_healthcheck.YOUTUBE_HEALTHCHECK_QUICK_URLS
    ]
    assert len(records) == 1
    assert records[0][0:2] == ('vless', 'key')
    assert records[0][2]['tg_ok'] is True
    assert records[0][2]['yt_ok'] is True
    assert records[0][2]['yt_stability'] == 'stable'

    metrics = {}
    tcp_calls = []
    tg_ok, tg_message = telegram_healthcheck.check_telegram_service_through_proxy(
        lambda proxy, **kwargs: (False, 'bot api failed'),
        lambda proxy, **kwargs: (False, 'telegram web fail'),
        'socks5h://127.0.0.1:10811',
        telegram_timeouts=(1, 2),
        http_timeouts=(1, 1),
        metrics=metrics,
        check_app_tcp=lambda proxy, **kwargs: tcp_calls.append((proxy, kwargs)) or (True, 'telegram dc ok'),
    )
    assert tg_ok is True
    assert tg_message == 'telegram dc ok'
    assert tcp_calls and tcp_calls[0][0] == 'socks5h://127.0.0.1:10811'
    assert 'tg_latency_ms' in metrics

    tg_ok, tg_message = telegram_healthcheck.check_telegram_service_through_proxy(
        lambda proxy, **kwargs: (True, 'bot api ok'),
        lambda proxy, **kwargs: (True, 'Веб-доступ через ключ подтверждён (HTTP 403).'),
        'socks5h://127.0.0.1:10811',
        telegram_timeouts=(1, 2),
        http_timeouts=(1, 1),
        allow_app_endpoints_without_api=False,
    )
    assert tg_ok is False
    assert 'HTTP 403' in tg_message

    records = []
    full_http_calls = []
    pool_probe_controller.check_pool_key_through_proxy(
        'vless',
        'full-youtube-key',
        [],
        'proxy',
        check_telegram_api=lambda proxy, **kwargs: (True, ''),
        check_http=lambda proxy, **kwargs: full_http_calls.append(kwargs) or (True, 'ok'),
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        probe_custom_targets=lambda proxy, custom_checks=None: {},
        retry_delay_seconds=0,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        http_retry_timeouts=(6, 10),
        youtube_profile='full',
        sleep=lambda seconds: None,
    )
    assert full_http_calls == [
        {'url': 'https://web.telegram.org/', 'connect_timeout': 3, 'read_timeout': 4},
    ] + [
        {
            'url': url,
            'connect_timeout': 3 if index == 0 else 6,
            'read_timeout': 4 if index == 0 else 10,
        }
        for index, url in enumerate(pool_probe_controller.YOUTUBE_HEALTHCHECK_URLS)
    ]

    records = []
    optional_tg_calls = []

    def check_optional_tg_retry_is_skipped(proxy, **kwargs):
        optional_tg_calls.append(kwargs)
        return False, 'fail'

    pool_probe_controller.check_pool_key_through_proxy(
        'vless2',
        'optional-telegram-key',
        [],
        'proxy',
        check_telegram_api=lambda proxy, **kwargs: (False, 'telegram fail'),
        check_http=check_optional_tg_retry_is_skipped,
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        probe_custom_targets=lambda proxy, custom_checks=None: {},
        retry_delay_seconds=0,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        http_retry_timeouts=(6, 10),
        telegram_required=False,
        sleep=lambda seconds: None,
    )
    assert optional_tg_calls[:1] == [
        {'url': 'https://web.telegram.org/', 'connect_timeout': 1.0, 'read_timeout': 1.5},
    ]
    assert len(optional_tg_calls) == 1 + len(youtube_healthcheck.YOUTUBE_HEALTHCHECK_QUICK_URLS)
    assert all(
        call['connect_timeout'] == 3 and call['read_timeout'] == 4
        for call in optional_tg_calls[1:]
    )
    assert records[0][2]['tg_ok'] is False

    records = []
    pool_probe_controller.check_pool_key_through_proxy(
        'vless',
        'quality-key',
        [],
        'proxy',
        check_telegram_api=lambda proxy, **kwargs: (True, ''),
        check_http=lambda proxy, **kwargs: (True, 'ok'),
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        probe_custom_targets=lambda proxy, custom_checks=None: {},
        retry_delay_seconds=0,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        http_retry_timeouts=(6, 10),
        measure_download=lambda proxy, **kwargs: (55.0, ''),
        quality_settings={
            'enabled': True,
            'download_bytes': 1048576,
            'stable_latency_ms': 2500,
            'fast_latency_ms': 1500,
            'min_1600p_mbps': 25.0,
            'min_4k_mbps': 45.0,
        },
        sleep=lambda seconds: None,
    )
    quality_record = records[0][2]
    assert quality_record['tg_ok'] is True
    assert quality_record['yt_ok'] is True
    assert quality_record['yt_throughput_mbps'] == 55.0
    assert 'tg_latency_ms' in quality_record
    assert 'yt_latency_ms' in quality_record
    assert 'googlevideo_latency_ms' in quality_record
    assert quality_record['min_4k_mbps'] == 45.0

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
    assert http_calls[:1] == [{'url': 'https://web.telegram.org/', 'connect_timeout': 1.0, 'read_timeout': 1.5}]
    assert len(records) == 1
    assert records[0][0:2] == ('vless', 'app-telegram-key')
    assert records[0][2]['tg_ok'] is False
    assert records[0][2]['yt_ok'] is True
    assert records[0][2]['yt_stability'] == 'stable'

    records = []

    def check_http_without_app_telegram(proxy, **kwargs):
        if kwargs.get('url') in pool_probe_controller.TELEGRAM_HEALTHCHECK_URLS:
            return False, 'telegram app fail'
        return True, 'ok'

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
    assert len(records) == 1
    assert records[0][0:2] == ('vless2', 'youtube-only')
    assert records[0][2]['tg_ok'] is False
    assert records[0][2]['yt_ok'] is True
    assert records[0][2]['yt_stability'] == 'stable'

    records = []
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
    assert len(records) == 1
    assert records[0][0:2] == ('vless2', 'bot-mode-vless2')
    assert records[0][2]['tg_ok'] is False
    assert records[0][2]['yt_ok'] is True
    assert records[0][2]['yt_stability'] == 'stable'

    records = []
    pool_probe_controller.check_pool_key_through_proxy(
        'vless',
        'bot-mode-transient-telegram',
        [],
        'proxy',
        check_telegram_api=lambda proxy, **kwargs: (False, 'Прокси не установил соединение с api.telegram.org за отведённое время.'),
        check_http=check_http_without_app_telegram,
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        probe_custom_targets=lambda proxy, custom_checks=None: {},
        retry_delay_seconds=0,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        telegram_required=True,
        sleep=lambda seconds: None,
    )
    assert len(records) == 1
    assert records[0][0:2] == ('vless', 'bot-mode-transient-telegram')
    assert records[0][2]['tg_ok'] is False
    assert records[0][2]['yt_ok'] is True
    assert telegram_healthcheck.telegram_failure_is_transient(records[0][2].get('tg_ok')) is False
    assert telegram_healthcheck.telegram_failure_is_transient('SOCKSHTTPSConnectionPool: Max retries exceeded') is True

    records = []
    telegram_web_attempts = []

    def check_http_retry_required_telegram(proxy, **kwargs):
        url = kwargs.get('url')
        if url == 'https://web.telegram.org/':
            telegram_web_attempts.append(kwargs)
            return len(telegram_web_attempts) >= 2, 'telegram app retry'
        if url in pool_probe_controller.TELEGRAM_HEALTHCHECK_URLS:
            return False, 'telegram app fail'
        return True, 'ok'

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
    assert len(records) == 1
    assert records[0][0:2] == ('vless', 'bot-mode-retry')
    assert records[0][2]['tg_ok'] is False
    assert records[0][2]['yt_ok'] is True
    assert records[0][2]['yt_stability'] == 'stable'
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

    records.clear()
    result = pool_probe_runner.find_pool_failover_candidate(
        [('vless', 'fail'), ('vless', 'ok')],
        service='telegram',
        batch_size=2,
        test_port='1200',
        proxy_outbound_from_key=lambda *args, **kwargs: {},
        wait_for_socks5=lambda port, timeout=6: True,
        check_telegram_api=lambda proxy, **kwargs: (not proxy.endswith(':1200'), 'telegram'),
        check_http=lambda proxy, **kwargs: (True, 'telegram web ok'),
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        proto_label=lambda proto: proto,
        log=logs.append,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        validate_outbound=lambda *args, **kwargs: None,
        build_config_batch=lambda valid_batch, test_port, proxy_outbound_from_key: {'valid': valid_batch},
        start_xray=lambda config: ('process', 'config.json'),
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        collect_garbage=lambda: None,
    )
    assert result == ('vless', 'ok', True, None)
    assert records[0] == ('vless', 'fail', {'tg_ok': False, 'yt_ok': None, 'allow_recent_success_downgrade': True})
    assert records[1] == ('vless', 'ok', {'tg_ok': True, 'yt_ok': None})
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
    assert api_only_records == [('vless', 'api-only', {'tg_ok': False, 'yt_ok': None, 'allow_recent_success_downgrade': True})]

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
    assert len(youtube_records) == 1
    assert youtube_records[0][0:2] == ('vless2', 'yt-ok')
    assert youtube_records[0][2]['tg_ok'] is None
    assert youtube_records[0][2]['yt_ok'] is True
    assert youtube_records[0][2]['yt_stability'] == 'stable'

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

    startup_errors = []
    checked, total = pool_probe_runner.run_pool_probe_worker(
        [('vless', 'broken-start')],
        [],
        batch_size=1,
        concurrency=1,
        delay_seconds=0,
        min_available_kb=0,
        test_port='1200',
        available_memory_kb=lambda: 999999,
        log=startup_errors.append,
        proto_label=lambda proto: proto,
        hash_key=_hash_key,
        set_checked=lambda value: None,
        validate_outbound=lambda proto, key: None,
        failed_custom_results=lambda checks: {},
        record_key_probe=lambda proto, key, **kwargs: None,
        start_xray_for_batch=lambda batch: (_ for _ in ()).throw(RuntimeError('xray start failed')),
        wait_for_socks5=lambda port, timeout=6: True,
        check_pool_key=lambda proto, key, checks, proxy_url: None,
        timeout_budget=lambda checks, task_count, workers: 1,
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        invalidate_caches=lambda: None,
    )
    assert (checked, total) == (1, 1)
    assert any('xray start failed' in message for message in startup_errors)

    high_load_notes = []
    high_load_logs = []
    high_load_remaining = []
    high_load_time = iter([0.0, 2.0])
    checked, total = pool_probe_runner.run_pool_probe_worker(
        [('vless', 'load-high')],
        [],
        batch_size=1,
        concurrency=1,
        delay_seconds=0,
        min_available_kb=0,
        test_port='1200',
        available_memory_kb=lambda: 999999,
        log=high_load_logs.append,
        proto_label=lambda proto: proto,
        hash_key=_hash_key,
        set_checked=lambda value: None,
        validate_outbound=lambda proto, key: (_ for _ in ()).throw(AssertionError('load guard should stop before validation')),
        failed_custom_results=lambda checks: {},
        record_key_probe=lambda proto, key, **kwargs: None,
        start_xray_for_batch=lambda batch: (_ for _ in ()).throw(AssertionError('load guard should stop before xray')),
        wait_for_socks5=lambda port, timeout=6: True,
        check_pool_key=lambda proto, key, checks, proxy_url: None,
        timeout_budget=lambda checks, task_count, workers: 1,
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        invalidate_caches=lambda: None,
        on_cancelled_remaining=high_load_remaining.extend,
        set_note=high_load_notes.append,
        load_average=lambda: 2.75,
        max_load1=2.0,
        high_load_delay_seconds=0,
        max_high_load_wait_seconds=1,
        sleep=lambda seconds: None,
        time_provider=lambda: next(high_load_time),
    )
    assert (checked, total) == (0, 1)
    assert high_load_remaining == [('vless', 'load-high')]
    assert any('load1 2.75' in note and '2.00' in note for note in high_load_notes)
    assert any('Remaining keys are paused' in item for item in high_load_logs)

    cancel_event = threading.Event()
    cancel_started = threading.Event()
    cancel_release = threading.Event()
    cancel_remaining = []
    cancel_records = []
    cancel_logs = []

    def slow_cancelled_check(proto, key, checks, proxy_url, record_key_probe=None):
        cancel_started.set()
        cancel_event.set()
        cancel_release.wait(timeout=1)
        if record_key_probe:
            record_key_probe(proto, key, tg_ok=False, yt_ok=False)

    checked, total = pool_probe_runner.run_pool_probe_worker(
        [('vless', 'cancel-current-batch')],
        [],
        batch_size=1,
        concurrency=1,
        delay_seconds=0,
        min_available_kb=0,
        test_port='1200',
        available_memory_kb=lambda: 999999,
        log=cancel_logs.append,
        proto_label=lambda proto: proto,
        hash_key=_hash_key,
        set_checked=lambda value: None,
        validate_outbound=lambda proto, key: None,
        failed_custom_results=lambda checks: {},
        record_key_probe=lambda proto, key, **kwargs: cancel_records.append((proto, key, kwargs)),
        start_xray_for_batch=lambda batch: ('process', 'config.json'),
        wait_for_socks5=lambda port, timeout=6: True,
        check_pool_key=slow_cancelled_check,
        timeout_budget=lambda checks, task_count, workers: 5,
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        invalidate_caches=lambda: None,
        cancel_event=cancel_event,
        on_cancelled_remaining=cancel_remaining.extend,
    )
    assert cancel_started.wait(timeout=1)
    assert (checked, total) == (0, 1)
    assert cancel_remaining == [('vless', 'cancel-current-batch')]
    cancel_release.set()
    time.sleep(0.05)
    assert cancel_records == []
    assert any('текущую пачку' in message for message in cancel_logs)

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

    rss_notes = []
    rss_logs = []
    rss_remaining = []
    checked, total = pool_probe_runner.run_pool_probe_worker(
        [('vless2', 'rss-high'), ('vless2', 'rss-next')],
        [],
        batch_size=1,
        concurrency=1,
        delay_seconds=0,
        min_available_kb=0,
        test_port='1200',
        available_memory_kb=lambda: 999999,
        log=rss_logs.append,
        proto_label=lambda proto: proto,
        hash_key=_hash_key,
        set_checked=lambda value: None,
        validate_outbound=lambda proto, key: (_ for _ in ()).throw(AssertionError('rss guard should stop before validation')),
        failed_custom_results=lambda checks: {},
        record_key_probe=lambda proto, key, **kwargs: None,
        start_xray_for_batch=lambda batch: (_ for _ in ()).throw(AssertionError('rss guard should stop before xray')),
        wait_for_socks5=lambda port, timeout=6: True,
        check_pool_key=lambda proto, key, checks, proxy_url: None,
        timeout_budget=lambda checks, task_count, workers: 1,
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        invalidate_caches=lambda: None,
        on_cancelled_remaining=rss_remaining.extend,
        set_note=rss_notes.append,
        process_rss_kb=lambda: 73000,
        max_process_rss_kb=71680,
    )
    assert (checked, total) == (0, 2)
    assert rss_remaining == [('vless2', 'rss-high'), ('vless2', 'rss-next')]
    assert any('RSS' in note and '71680' in note for note in rss_notes)
    assert any('RSS' in item for item in rss_logs)

    rss_values = iter([73000, 70000, 70000])
    rss_cleanup_calls = []
    rss_processed = []
    checked, total = pool_probe_runner.run_pool_probe_worker(
        [('vless2', 'rss-recovers')],
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
        check_pool_key=lambda proto, key, checks, proxy_url: rss_processed.append((proto, key)),
        timeout_budget=lambda checks, task_count, workers: 1,
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        invalidate_caches=lambda: None,
        process_rss_kb=lambda: next(rss_values),
        max_process_rss_kb=71680,
        memory_cleanup=lambda **kwargs: rss_cleanup_calls.append(kwargs) or {'rss_after_kb': 70000},
        rss_cleanup_delay_seconds=0,
        max_rss_cleanup_attempts=2,
    )
    assert (checked, total) == (1, 1)
    assert rss_processed == [('vless2', 'rss-recovers')]
    assert any(call.get('reason') == 'pool probe rss guard' and call.get('force') is True for call in rss_cleanup_calls)
    assert not any(call.get('reason') == 'pool probe key checkpoint' for call in rss_cleanup_calls)
    assert not any(call.get('reason') == 'pool probe batch checkpoint' for call in rss_cleanup_calls)

    slow_notes = []
    slow_sleeps = []
    slow_processed = []
    checked, total = pool_probe_runner.run_pool_probe_worker(
        [('vless', 'slow-memory')],
        [],
        batch_size=1,
        concurrency=1,
        delay_seconds=0,
        min_available_kb=125000,
        slow_available_kb=190000,
        slow_memory_delay_seconds=3.0,
        test_port='1200',
        available_memory_kb=lambda: 150000,
        log=logs.append,
        proto_label=lambda proto: proto,
        hash_key=_hash_key,
        set_checked=lambda value: None,
        validate_outbound=lambda proto, key: None,
        failed_custom_results=lambda checks: {},
        record_key_probe=lambda proto, key, **kwargs: None,
        start_xray_for_batch=lambda batch: ('process', 'config.json'),
        wait_for_socks5=lambda port, timeout=6: True,
        check_pool_key=lambda proto, key, checks, proxy_url: slow_processed.append((proto, key)),
        timeout_budget=lambda checks, task_count, workers: 1,
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        invalidate_caches=lambda: None,
        set_note=slow_notes.append,
        sleep=slow_sleeps.append,
    )
    assert (checked, total) == (1, 1)
    assert slow_processed == [('vless', 'slow-memory')]
    assert slow_sleeps == [3.0]
    assert any('экономном режиме' in note for note in slow_notes)

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
        (
            'vless',
            'sockless',
            {
                'tg_ok': 'unknown',
                'yt_ok': 'unknown',
                'custom': {'custom': 'unknown'},
                'custom_checks': [{'id': 'custom'}],
                'timeout': True,
                'timeout_reason': 'socks port 1200 not ready',
            },
        ),
    ]

    exception_records = []
    checked, total = pool_probe_runner.run_pool_probe_worker(
        [('vless', 'probe-exception')],
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
        set_checked=lambda value: None,
        validate_outbound=lambda proto, key: None,
        failed_custom_results=lambda checks: {'custom': False},
        record_key_probe=lambda proto, key, **kwargs: exception_records.append((proto, key, kwargs)),
        start_xray_for_batch=lambda batch: ('process', 'config.json'),
        wait_for_socks5=lambda port, timeout=6: True,
        check_pool_key=lambda proto, key, checks, proxy_url: (_ for _ in ()).throw(RuntimeError('temporary probe error')),
        timeout_budget=lambda checks, task_count, workers: 1,
        stop_xray=lambda process, config_path: None,
        cleanup_runtime=lambda kill_processes=False: None,
        invalidate_caches=lambda: None,
    )
    assert (checked, total) == (1, 1)
    assert exception_records == [
        (
            'vless',
            'probe-exception',
            {
                'tg_ok': 'unknown',
                'yt_ok': 'unknown',
                'custom': {'custom': 'unknown'},
                'custom_checks': [{'id': 'custom'}],
                'timeout': True,
                'timeout_reason': 'probe exception: temporary probe error',
            },
        ),
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
    original_requests_module = proxy_status._requests_module

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

        proxy_status._requests_module = lambda: py_types.SimpleNamespace(Session=_Session)
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
        proxy_status._requests_module = original_requests_module

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
    old_dir = unblock_lists.UNBLOCK_DIR
    old_popen = unblock_lists.subprocess.Popen
    old_run = unblock_lists.subprocess.run
    with tempfile.TemporaryDirectory() as tmp_dir:
        popen_calls = []
        try:
            unblock_lists.UNBLOCK_DIR = tmp_dir
            unblock_lists.subprocess.run = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('save should not wait for unblock_update.sh'))
            unblock_lists.subprocess.Popen = lambda cmd, **kwargs: popen_calls.append((cmd, kwargs))
            assert unblock_lists.save_unblock_list_file('vless.txt', 'b.example\na.example\n', async_update=True) == 'vless.txt'
            try:
                unblock_lists.save_unblock_list_file('legacy.txt', 'example.org\n', async_update=True)
                assert False, 'legacy.txt must not be editable from web save helper'
            except ValueError:
                pass
        finally:
            unblock_lists.UNBLOCK_DIR = old_dir
            unblock_lists.subprocess.Popen = old_popen
            unblock_lists.subprocess.run = old_run
    assert popen_calls and popen_calls[0][0] == [unblock_lists.UNBLOCK_UPDATE_SCRIPT]
    assert popen_calls[0][1]['stdout'] is unblock_lists.subprocess.DEVNULL


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
        for line in (APP_ROOT / 'vless-2.txt').read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    }
    assert set(service_catalog.service_route_entries('youtube')) <= entries
    assert 'googleapis.com' not in entries
    assert 'googleusercontent.com' not in entries
    assert 'remotedesktop-pa.googleapis.com' not in entries
    assert 'instantmessaging-pa.googleapis.com' not in entries
    assert {
        'apis.google.com',
        'client-channel.google.com',
        'fonts.googleapis.com',
        'youtubei-att.googleapis.com',
    } <= entries
    youtube_allowed_global = set(
        service_catalog.SERVICE_LIST_SOURCES['youtube'].get('route_global_exclude_allow') or []
    )
    assert set(service_catalog.global_route_exclude_entries()) & entries <= youtube_allowed_global
    assert {'accounts.google.com', 'clients4.google.com', 'www.google.com', 'www.gstatic.com'} <= entries
    assert {
        '173.194.10.0/24',
        '173.194.18.0/24',
        '173.194.19.0/24',
        '173.194.182.0/24',
        '173.194.187.0/24',
        '74.125.13.0/24',
        '74.125.104.0/24',
        '74.125.160.0/24',
        '74.125.162.0/24',
    } <= entries
    assert {
        '142.251.38.106',
        '142.251.38.110',
        '142.251.142.234',
        '172.217.20.170',
    } <= entries
    vless_entries = {
        line.strip()
        for line in (APP_ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    }
    assert 'accounts.google.com' in vless_entries
    router_preserved_global = {'clients3.google.com'}
    assert set(service_catalog.global_route_exclude_entries()) & vless_entries <= router_preserved_global
    assert 'rutracker.org' in entries
    assert 'rutracker.wiki' in entries
    assert service_routes.service_route_state('telegram', unblock_dir=str(APP_ROOT))['label'] == 'Vless 1'
    assert service_routes.service_route_state('youtube', unblock_dir=str(APP_ROOT))['label'] == 'Vless 2'
    assert service_routes.service_route_state('gemini', unblock_dir=str(APP_ROOT))['label'] == 'Vless 1'
    chrome_remote_desktop_state = service_routes.service_route_state('chrome_remote_desktop', unblock_dir=str(APP_ROOT))
    assert chrome_remote_desktop_state['complete_protocols'] == []
    assert chrome_remote_desktop_state['partial_protocols'] == []
    assert 'static.rutracker.cc' in entries
    assert 'feed.rutracker.cc' in entries
    assert 'rutracker.org' not in vless_entries
    assert 'rutracker.wiki' not in vless_entries
    assert 'static.rutracker.cc' not in vless_entries
    assert 'feed.rutracker.cc' not in vless_entries
    assert {'one-way.work', 'rmr.rocks', 'aaa200.one', 'static.librebook.me'} <= vless_entries
    assert 'thepiratebay.org' not in entries
    assert 'discord-attachments-uploads-prd.storage.googleapis.com' not in entries
    assert 'redirector.googlevideo.com' in entries
    assert 'yt4.ggpht.com' in entries
    assert 'yt4.googleusercontent.com' in entries
    assert {
        'ggpht.cn',
        'withyoutube.com',
        'youtubefanfest.com',
        'youtubegaming.com',
        'youtubego.com',
        'youtubego.co.id',
        'youtubego.co.in',
        'youtubego.com.br',
        'youtubego.id',
        'youtubego.in',
        'youtubemobilesupport.com',
    } <= entries
    assert set(service_catalog.YOUTUBE_AD_DECISION_ROUTE_ENTRIES) <= entries
    assert not (set(service_catalog.YOUTUBE_AD_DECISION_ROUTE_ENTRIES) & vless_entries)
    assert set(service_catalog.YOUTUBE_PLAYER_API_IP_ENTRIES) <= entries
    assert not (set(service_catalog.YOUTUBE_PLAYER_API_IP_ENTRIES) & vless_entries)
    assert set(service_catalog.YOUTUBE_EDGE_IP_ENTRIES) <= entries
    assert not (set(service_catalog.YOUTUBE_EDGE_IP_ENTRIES) & vless_entries)
    assert {
        '142.251.38.67',
        '142.251.38.72',
        '142.251.38.81',
        '142.251.38.91',
        '142.251.150.119',
        '142.251.151.119',
        '142.251.152.119',
        '142.251.153.119',
        '142.251.154.119',
        '142.251.155.119',
        '142.251.157.119',
        '173.194.188.72',
        '216.239.34.36',
    } <= set(service_catalog.YOUTUBE_EDGE_IP_ENTRIES)
    assert '74.125.172.0/24' in entries
    assert '173.194.31.0/24' in entries
    assert '74.125.174.0/24' in entries
    assert '2a00:1450:4010:c22::/64' in entries
    assert {
        '157.240.0.0/16',
        'thepiratebay.org',
        'discord-attachments-uploads-prd.storage.googleapis.com',
    } <= vless_entries
    assert {'104.21.0.0/16', '172.67.0.0/16', '188.114.0.0/16'} <= vless_entries
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


def test_chrome_remote_desktop_routes_stay_manual_only():
    entries = {
        line.split('#', 1)[0].strip()
        for line in (APP_ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.split('#', 1)[0].strip()
    }
    source = service_catalog.SERVICE_LIST_SOURCES['chrome_remote_desktop']
    state_entries = set(service_catalog.service_route_entries('chrome_remote_desktop'))
    assert source.get('route_profile_enabled') is False
    assert state_entries == set(service_catalog.CHROME_REMOTE_DESKTOP_CORE_ROUTE_ENTRIES)
    assert not (state_entries & entries)
    assert not (set(service_catalog.CHROME_REMOTE_DESKTOP_SHARED_ROUTE_ENTRIES) & state_entries)
    assert 'full:instantmessaging-pa.googleapis.com' not in service_catalog.CONNECTIVITY_CHECK_DOMAINS
    assert 'full:remotedesktop-pa.googleapis.com' not in service_catalog.CONNECTIVITY_CHECK_DOMAINS


def test_chatgpt_codex_routes_are_synced():
    entries = {
        line.split('#', 1)[0].strip()
        for line in (APP_ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.split('#', 1)[0].strip()
    }
    assert set(service_catalog.service_route_entries('chatgpt_services')) <= entries
    assert set(service_catalog.CHATGPT_EDGE_IP_ENTRIES) <= entries
    assert {'ab.chatgpt.com', 'api.chatgpt.com', 'api.statsig.com', 'browser-intake-datadoghq.com'} <= entries
    assert {'humb.apple.com', 'statsigapi.net', 'workos.imgix.net'} <= entries
    assert {'persistent.oaistatic.com', 'openaiassets.blob.core.windows.net', 'images.ctfassets.net'} <= entries
    assert {'api.statsigcdn.com', 'cloudflare-dns.com', 'accounts.google.com'} <= entries
    assert 'www.google.com' not in entries
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
    bot_source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    assert "'chatgpt_services'" in bot_source
    assert "'youtube'" in bot_source


def test_ai_assistant_custom_routes_are_synced():
    entries = {
        line.split('#', 1)[0].strip()
        for line in (APP_ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.split('#', 1)[0].strip()
    }
    presets = {item['id']: item for item in service_catalog.CUSTOM_CHECK_PRESETS}

    assert set(service_catalog.CLAUDE_ROUTE_ENTRIES) <= entries
    gemini_state_entries = set(service_catalog.service_route_entries('gemini'))
    assert gemini_state_entries <= entries
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
    assert set(service_catalog.YOUTUBE_AD_DECISION_ROUTE_ENTRIES).isdisjoint(
        service_catalog.GEMINI_ROUTE_ENTRIES
    )
    bot_source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    assert "'claude'" in bot_source
    assert "'gemini'" in bot_source


def test_primary_vless_does_not_capture_gmail_domains():
    entries = {
        line.split('#', 1)[0].strip()
        for line in (APP_ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
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
        for line in (APP_ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.split('#', 1)[0].strip()
    }
    bot_source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
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
        applied_routes = set(service_catalog.service_route_entries(preset['id']))
        assert source_entries
        assert preset_routes <= source_entries
        assert applied_routes <= source_entries
        if source.get('route_profile_enabled') is False:
            assert not (applied_routes & entries)
            continue
        assert applied_routes <= entries

    assert service_catalog.SERVICE_LIST_SOURCES['discord']['entries'] == service_catalog.DISCORD_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['copilot']['entries'] == service_catalog.COPILOT_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['perplexity']['entries'] == service_catalog.PERPLEXITY_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['grok']['entries'] == service_catalog.GROK_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['grok']['label'] == 'Grok / X / Twitter'
    assert service_catalog.SERVICE_LIST_SOURCES['grok']['include_services'] == ['twitter']
    assert service_catalog.SERVICE_LIST_SOURCES['deepseek']['entries'] == service_catalog.DEEPSEEK_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['telegram']['entries'] == service_catalog.TELEGRAM_UNBLOCK_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['meta']['entries'] == service_catalog.META_PLATFORM_ROUTE_ENTRIES
    assert service_catalog.SERVICE_LIST_SOURCES['meta']['label'] == 'Instagram / Facebook'
    assert 'telegram' in button_keys
    assert 'meta' in button_keys
    assert 'grok' in button_keys
    assert 'twitter' not in button_keys
    assert {'meta_ai', 'instagram', 'facebook'}.isdisjoint(button_keys)
    assert {'meta_ai', 'instagram', 'facebook'}.isdisjoint(preset_ids)
    assert presets['meta']['routes'] == service_catalog.META_PLATFORM_ROUTE_ENTRIES
    assert presets['meta']['urls'] == [
        'https://www.meta.ai',
        'https://www.instagram.com',
        'https://www.facebook.com',
        'https://graph.facebook.com',
    ]
    assert presets['grok']['label'] == 'Grok / X / Twitter'
    assert "source.get('include_services')" in bot_source
    assert 'def _service_list_labels():' in bot_source
    assert "names = ', '.join(_service_list_labels())" in bot_source
    assert 'entries = _load_service_entries(service_key)' in bot_source


def test_telegram_routes_include_mini_app_dependencies():
    entries = {
        line.split('#', 1)[0].strip()
        for line in (APP_ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
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
        '142.251.169.188', '172.253.145.188',
        'stel.com', '2001:b28:f23c::/48', '2a0a:f280::/32',
        '2a0a:f280:203::/48',
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
    assert checks[0]['label'] == 'Instagram / Facebook'
    assert checks[0]['routes'] == service_catalog.META_PLATFORM_ROUTE_ENTRIES


def test_chrome_remote_desktop_routes_are_manual_only():
    entries = {
        line.split('#', 1)[0].strip()
        for line in (APP_ROOT / 'vless.txt').read_text(encoding='utf-8').splitlines()
        if line.split('#', 1)[0].strip()
    }
    source = service_catalog.SERVICE_LIST_SOURCES['chrome_remote_desktop']
    state_entries = set(service_catalog.service_route_entries('chrome_remote_desktop'))
    assert source.get('route_profile_enabled') is False
    assert state_entries == set(service_catalog.CHROME_REMOTE_DESKTOP_CORE_ROUTE_ENTRIES)
    assert not (state_entries & entries)
    assert service_catalog.SERVICE_LIST_SOURCES['chrome_remote_desktop']['entries'] == service_catalog.CHROME_REMOTE_DESKTOP_ROUTE_ENTRIES
    presets = {item['id']: item for item in service_catalog.CUSTOM_CHECK_PRESETS}
    assert presets['chrome_remote_desktop']['routes'] == service_catalog.CHROME_REMOTE_DESKTOP_ROUTE_ENTRIES
    bot_source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    assert "'chrome_remote_desktop'" in bot_source


def test_web_command_state_helpers():
    assert web_command_state.estimate_update_progress('noop', '', ('update',)) == (0, '')
    assert web_command_state.estimate_update_progress('update', 'Бэкап создан.') == (70, 'Резервная копия готова, идёт замена файлов')
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'events.jsonl'
        event_history.record_event(
            action='web_command_start',
            source='web',
            protocol='system',
            service='update',
            event_path=str(path),
            time_provider=lambda: 100,
        )
        event_history.record_event(
            action='web_command_finish',
            source='web',
            protocol='system',
            service='update',
            event_path=str(path),
            time_provider=lambda: 280,
        )
        assert event_history.estimate_update_duration(event_path=str(path)) == (240, 1)
        event_history.record_event(
            action='web_command_start',
            source='web',
            protocol='system',
            service='update',
            event_path=str(path),
            time_provider=lambda: 300,
        )
        event_history.record_event(
            action='web_command_finish',
            message='Error: crontab failed content validation',
            source='web',
            protocol='system',
            service='update',
            event_path=str(path),
            time_provider=lambda: 900,
        )
        assert event_history.estimate_update_duration(event_path=str(path)) == (240, 1)
        event_history.record_event(
            action='web_command_start',
            source='web',
            protocol='system',
            service='update',
            event_path=str(path),
            time_provider=lambda: 1000,
        )
        event_history.record_event(
            action='web_command_finish',
            message='Further update output is saved',
            source='web',
            protocol='system',
            service='update',
            event_path=str(path),
            time_provider=lambda: 1240,
        )
        assert event_history.estimate_update_duration(event_path=str(path)) == (210, 2)
    state = {}
    lock = threading.Lock()
    web_command_state.set_flash_message(lock, state, 'ok')
    assert web_command_state.consume_flash_message(lock, state) == 'ok'
    assert web_command_state.consume_flash_message(lock, state) == ''
    state = {
        'running': False,
        'command': 'update',
        'label': 'Обновить до последнего релиза',
        'result': 'done',
        'progress': 100,
        'progress_label': 'Завершено',
        'started_at': 10,
        'finished_at': 20,
        'shown_after_finish': False,
    }
    consumed = web_command_state.consume_command_state_for_render(
        lock,
        state,
        clear_finished_commands=('update',),
    )
    assert consumed['label'] == ''
    assert state['label'] == ''
    state = {
        'running': False,
        'command': 'restart',
        'label': 'Перезапустить сервисы',
        'result': 'done',
        'progress': 100,
        'progress_label': 'Завершено',
        'started_at': 10,
        'finished_at': 20,
        'shown_after_finish': False,
    }
    consumed = web_command_state.consume_command_state_for_render(
        lock,
        state,
        clear_finished_commands=('update',),
    )
    assert consumed['label'] == 'Перезапустить сервисы'
    assert state['shown_after_finish'] is True


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
    local_no_auth = _NoAuthRequest()
    local_no_auth.headers = {'Host': '192.168.1.1:8080'}
    assert local_no_auth._ensure_web_auth() is True
    external_no_auth = _NoAuthRequest()
    external_no_auth.headers = {'Host': 'bypass.keenetic-2969.netcraze.pro'}
    assert external_no_auth._ensure_web_auth() is False
    assert external_no_auth.status_code == 401
    assert b'external web access' in external_no_auth.wfile.getvalue()

    class _ExternalRequest(_Request):
        allow_authenticated_external = True
        local_client_checker = staticmethod(lambda address: False)

        def __init__(self, header='', token='secret'):
            super().__init__(header)
            self.client_address = ('203.0.113.10', 12345)
            self.web_auth_token_getter = staticmethod(lambda: token)

    external_missing_token = _ExternalRequest(token='')
    assert external_missing_token._ensure_request_allowed() is False
    assert external_missing_token.status_code == 403

    external_missing_auth = _ExternalRequest()
    assert external_missing_auth._ensure_request_allowed() is False
    assert external_missing_auth.status_code == 401

    external_authenticated = _ExternalRequest('Basic ' + good)
    assert external_authenticated._ensure_request_allowed() is True


def test_web_http_gzip_and_head_responses():
    class _Request(web_http_common.WebRequestMixin):
        def __init__(self, headers=None, command='GET'):
            self.headers = headers or {}
            self.command = command
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

    request = _Request({'Accept-Encoding': 'br, gzip'})
    html = '<main>' + ('external web ui ' * 512) + '</main>'
    request._send_html(html)
    headers = dict(request.sent_headers)

    assert request.status_code == 200
    assert headers['Content-Encoding'] == 'gzip'
    assert headers['Vary'] == 'Accept-Encoding'
    assert int(headers['Content-Length']) == len(request.wfile.getvalue())
    assert gzip.decompress(request.wfile.getvalue()).decode('utf-8') == html
    assert request.close_connection is True

    no_gzip = _Request({'Accept-Encoding': 'gzip;q=0'})
    no_gzip._send_html(html)
    no_gzip_headers = dict(no_gzip.sent_headers)
    assert 'Content-Encoding' not in no_gzip_headers
    assert no_gzip.wfile.getvalue().decode('utf-8') == html

    head_request = _Request({'Accept-Encoding': 'gzip'}, command='HEAD')
    head_request._send_json({'payload': 'external web ui ' * 512})
    head_headers = dict(head_request.sent_headers)

    assert head_request.status_code == 200
    assert head_headers['Content-Encoding'] == 'gzip'
    assert int(head_headers['Content-Length']) > 0
    assert head_request.wfile.getvalue() == b''
    assert head_request.close_connection is True

    asset_one = _Request({'Accept-Encoding': 'gzip'})
    asset_one._send_text_asset(html, 'text/css; charset=utf-8', asset_cache_key='test.css')
    asset_two = _Request({'Accept-Encoding': 'gzip'})
    asset_two._send_text_asset(html, 'text/css; charset=utf-8', asset_cache_key='test.css')
    assert asset_two.wfile.getvalue() == asset_one.wfile.getvalue()
    assert ('test.css', True) in web_http_common.WebRequestMixin.static_asset_body_cache
    immutable_asset = _Request({'Accept-Encoding': 'gzip'})
    immutable_asset._send_text_asset(html, 'text/css; charset=utf-8', cache_seconds=31536000, asset_cache_key='immutable.css')
    assert dict(immutable_asset.sent_headers)['Cache-Control'] == 'public, max-age=31536000, immutable'
    with tempfile.TemporaryDirectory() as tmp:
        first_path = Path(tmp) / 'first.css'
        second_path = Path(tmp) / 'second.js'
        first_path.write_text('first', encoding='utf-8')
        second_path.write_text('second', encoding='utf-8')
        web_form_template._static_asset_cache.clear()
        assert web_form_template.load_static_asset(str(first_path), lambda: '') == 'first'
        assert web_form_template.load_static_asset(str(second_path), lambda: '') == 'second'
        assert len(web_form_template._static_asset_cache) == 2


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
    user, note = installer_common.web_auth_summary({'web_auth_user': 'admin', 'web_auth_token': ''})
    assert user == 'admin'
    assert 'только локальный адрес' in note
    assert 'вход будет без пароля' not in note
    assert installer_common.validate_installer_form(
        {'token': 'x', 'username': 'u', 'browser_port': '8080'},
        ['token', 'username'],
    ) == (True, '')
    assert installer_common.browser_port_is_valid('1') is True
    assert installer_common.browser_port_is_valid('65535') is True
    assert installer_common.browser_port_is_valid('0') is False
    assert installer_common.browser_port_is_valid('65536') is False
    assert installer_common.browser_port_is_valid('99999') is False
    assert installer_common.browser_port_is_valid('-1') is False
    ok, message = installer_common.validate_installer_form(
        {'token': 'x', 'username': 'u', 'browser_port': 'bad'},
        ['token', 'username'],
    )
    assert ok is False
    assert 'browser_port' in message
    ok, message = installer_common.validate_installer_form(
        {'token': 'x', 'username': 'u', 'browser_port': '99999'},
        ['token', 'username'],
    )
    assert ok is False
    assert '1-65535' in message
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

    bot_source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    assert "direct_env['REPO_REF'] = repo_ref" in bot_source
    assert "direct_env['REPO_REF'] = branch" not in bot_source
    assert repo_update.download_repo_script.__defaults__ == ('main',)
    assert telegram_jobs.start_background_command.__kwdefaults__['branch'] == 'main'
    assert repo_update.direct_fetch_env(('HTTP_PROXY',), {'HTTP_PROXY': 'x', 'keep': 'y'}) == {'keep': 'y'}


def test_web_background_helpers():
    def webp_vp8x(width=1600, height=1000, padding=0):
        header = bytearray(10)
        header[4:7] = (width - 1).to_bytes(3, 'little')
        header[7:10] = (height - 1).to_bytes(3, 'little')
        body = b'WEBP' + b'VP8X' + (10).to_bytes(4, 'little') + bytes(header)
        if padding:
            padding_bytes = b'0' * padding
            body += b'JUNK' + len(padding_bytes).to_bytes(4, 'little') + padding_bytes
            if len(padding_bytes) & 1:
                body += b'\0'
        return b'RIFF' + len(body).to_bytes(4, 'little') + body

    class TrackingReader(BytesIO):
        def __init__(self, value):
            super().__init__(value)
            self.max_request = 0

        def read(self, size=-1):
            self.max_request = max(self.max_request, size)
            return super().read(size)

    with tempfile.TemporaryDirectory() as tmpdir:
        store = web_background.WebBackgroundStore(tmpdir)
        assert store.payload()['available'] is False
        image = webp_vp8x(padding=web_background.STREAM_CHUNK_BYTES * 2 + 7)
        reader = TrackingReader(image)
        payload = store.upload(reader, len(image), 'image/webp; charset=binary')
        assert reader.max_request <= web_background.STREAM_CHUNK_BYTES
        assert payload['available'] is True
        assert payload['enabled'] is True
        assert payload['width'] == 1600
        assert payload['height'] == 1000
        assert web_background.webp_dimensions(store.file_path()) == (1600, 1000)
        assert os.path.getsize(store.file_path()) == len(image)
        assert store.update_settings('0', '91')['enabled'] is False
        assert store.payload()['shade'] == 91
        previous = Path(store.file_path()).read_bytes()
        try:
            store.upload(BytesIO(image[:-1]), len(image), 'image/webp')
            raise AssertionError('interrupted upload must fail')
        except ValueError as exc:
            assert 'прервалась' in str(exc)
        assert Path(store.file_path()).read_bytes() == previous
        for content_length, content_type in ((web_background.MAX_BACKGROUND_BYTES + 1, 'image/webp'), (len(image), 'image/png')):
            try:
                store.upload(BytesIO(image), content_length, content_type)
                raise AssertionError('invalid upload must fail')
            except ValueError:
                pass
        bad_path = Path(tmpdir) / 'bad.webp'
        bad_path.write_bytes(b'not-webp')
        try:
            web_background.webp_dimensions(str(bad_path))
            raise AssertionError('invalid WebP must fail')
        except ValueError:
            pass
        context = {
            'web_background_payload': store.payload,
            'web_background_file_path': store.file_path,
        }
        api_action = web_get_actions.dispatch(context, '/api/ui_background')
        assert api_action['payload']['available'] is True
        file_action = web_get_actions.dispatch(context, '/ui/background.webp')
        assert file_action['kind'] == 'file'
        assert file_action['content_type'] == 'image/webp'
        assert file_action['cache_control'].startswith('private')
        class StreamingHandler(web_http_common.WebRequestMixin):
            def __init__(self):
                self.command = 'GET'
                self.wfile = BytesIO()
                self.headers = {}
                self.response_status = None
                self.response_headers = {}
                self.close_connection = False

            def send_response(self, status):
                self.response_status = status

            def send_header(self, name, value):
                self.response_headers[name.lower()] = value

            def end_headers(self):
                return None

        handler = StreamingHandler()
        handler._send_binary_file(store.file_path(), 'image/webp')
        assert handler.response_status == 200
        assert handler.response_headers['content-type'] == 'image/webp'
        assert handler.wfile.getvalue() == image
        common_source = source_path('web_http_common.py').read_text(encoding='utf-8')
        assert "handle.read(64 * 1024)" in common_source
        update_source = (ROOT / 'script.sh').read_text(encoding='utf-8')
        assert 'web_background.py WebBackgroundStore' in update_source
        assert '/opt/etc/unblock/web-ui/background.webp' in update_source
        assert store.delete()['available'] is False
        assert web_get_actions.dispatch(context, '/ui/background.webp') is None


def test_web_get_actions_helpers():
    refreshed = []
    pool_snapshot_calls = []
    pool_summary_calls = []
    current_keys = {'vless': 'key'}
    def pool_snapshot(keys, include_keys=False, protocols=None):
        pool_snapshot_calls.append((keys, include_keys, protocols))
        return {proto: {'rows': []} for proto in (protocols or ['vless'])}
    router_health_calls = []
    ctx = {
        'build_form': lambda message: 'form:' + message,
        'build_protocol_panel': lambda proto: 'panel:' + proto,
        'build_protocol_check_panel': lambda proto: 'check:' + proto,
        'consume_flash_message': lambda: 'saved',
        'load_current_keys': lambda: current_keys,
        'cached_status_snapshot': lambda keys: None,
        'active_mode_status_snapshot': lambda keys: {'web': {'state': 'active'}, 'protocols': {'vless': {}}},
        'refresh_status_caches_async': lambda keys: refreshed.append(keys),
        'pool_probe_locked': lambda: False,
        'get_web_command_state': lambda: {'running': False},
        'pool_enabled': True,
        'bot_ready': lambda: True,
        'get_pool_probe_progress': lambda: {'running': True, 'total': 2},
        'web_pool_snapshot': pool_snapshot,
        'pool_status_summary': lambda keys: pool_summary_calls.append(keys) or {'active_text': '1 / 5'},
        'web_custom_checks': lambda: [{'id': 'custom'}],
        'service_routes_payload': lambda: {'route_tools_html': '<div>routes</div>'},
        'unblock_list_payload': lambda name: {'ok': True, 'name': name, 'content': 'example.org', 'line_count': 1},
        'telegram_call_learning_snapshot': lambda: {'watching': True, 'seen_clients': ['192.168.1.23']},
        'router_health_snapshot': lambda **kwargs: router_health_calls.append(kwargs) or {'cpu_percent': 2.0},
        'router_metrics_snapshot': lambda: {'load': {'load1': 0.1}, 'summary': {'samples': 1}},
        'time_provider': lambda: 123.0,
        'static_dir': '/tmp/static',
        'service_icons_enabled': True,
    }
    assert web_get_actions.dispatch(ctx, '/') == {'kind': 'html', 'html': 'form:saved'}
    unblock_payload = web_get_actions.dispatch(ctx, '/api/unblock_list', 'name=vless.txt')
    assert unblock_payload['payload']['content'] == 'example.org'
    status = web_get_actions.dispatch(ctx, '/api/status')
    assert status['payload']['pool_probe_running'] is True
    assert status['payload']['bot_ready'] is True
    assert status['payload']['timestamp'] == 123.0
    assert 'telegram_call_learning' not in status['payload']
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
    compact_placeholder_calls = []
    compact_placeholder_refreshed = []
    compact_placeholder_ctx = dict(placeholder_ctx)
    compact_placeholder_ctx.update({
        'placeholder_status_snapshot': lambda keys: compact_placeholder_calls.append(keys) or {
            'web': {'state': 'compact-placeholder'},
            'protocols': {'vless': {'label': 'pending'}},
        },
        'refresh_status_caches_async': lambda keys: compact_placeholder_refreshed.append(keys),
    })
    compact_placeholder_status = web_get_actions.dispatch(compact_placeholder_ctx, '/api/status', 'compact=1&lite=1')
    assert compact_placeholder_status['payload']['web'] == {'state': 'compact-placeholder'}
    assert compact_placeholder_calls == [current_keys]
    assert compact_placeholder_refreshed == [current_keys]
    stale_refreshed = []
    stale_ctx = dict(ctx)
    stale_ctx.update({
        'stale_status_snapshot': lambda keys: {'web': {'state': 'stale'}, 'protocols': {'vless': {'label': 'cached'}}},
        'placeholder_status_snapshot': lambda keys: (_ for _ in ()).throw(AssertionError('stale status should avoid placeholder')),
        'refresh_status_caches_async': lambda keys: stale_refreshed.append(keys),
        'get_pool_probe_progress': lambda: {'running': False, 'total': 0},
    })
    stale_status = web_get_actions.dispatch(stale_ctx, '/api/status')
    assert stale_status['payload']['web'] == {'state': 'stale'}
    assert stale_refreshed == [current_keys]
    command_refreshed = []
    command_ctx = dict(placeholder_ctx)
    command_ctx.update({
        'refresh_status_caches_async': lambda keys: command_refreshed.append(keys),
        'get_web_command_state': lambda: {'running': True, 'command': 'update'},
        'refresh_status_on_api': True,
    })
    command_status = web_get_actions.dispatch(command_ctx, '/api/status')
    assert command_status['payload']['web'] == {'state': 'placeholder'}
    assert command_refreshed == []
    cached_status_ctx = dict(ctx)
    cached_status_ctx.update({
        'get_pool_probe_progress': lambda: {'running': False, 'total': 0},
        'status_api_cache_ttl': 30,
        'get_status_api_cache': lambda cache_key='full': {
            'timestamp': 122.0,
            'payload': {'cached': cache_key},
        } if cache_key == 'compact' else None,
        'cached_status_snapshot': lambda keys: (_ for _ in ()).throw(AssertionError('cached compact status should not rebuild snapshot')),
        'time_provider': lambda: 123.0,
    })
    cached_compact_status = web_get_actions.dispatch(cached_status_ctx, '/api/status', 'compact=1')
    assert cached_compact_status['payload'] == {'cached': 'compact'}
    stored_status_payloads = []
    stored_status_ctx = dict(ctx)
    stored_status_ctx.update({
        'get_pool_probe_progress': lambda: {'running': False, 'total': 0},
        'status_api_cache_ttl': 30,
        'cached_status_snapshot': lambda keys: {'web': {'state': 'cached'}, 'protocols': {'vless': {}}},
        'get_status_api_cache': lambda cache_key='full': None,
        'store_status_api_cache': lambda payload, timestamp=None, cache_key='full': stored_status_payloads.append((cache_key, timestamp, payload)),
    })
    stored_compact_status = web_get_actions.dispatch(stored_status_ctx, '/api/status', 'compact=1')
    assert stored_compact_status['payload']['pool_summary'] is None
    assert stored_status_payloads and stored_status_payloads[0][0] == 'compact'
    lite_status_payloads = []
    lite_status_ctx = dict(stored_status_ctx)
    lite_status_ctx.update({
        'router_health_snapshot': lambda: (_ for _ in ()).throw(AssertionError('lite status must not rebuild router health')),
        'store_status_api_cache': lambda payload, timestamp=None, cache_key='full': lite_status_payloads.append((cache_key, timestamp, payload)),
    })
    lite_status = web_get_actions.dispatch(lite_status_ctx, '/api/status', 'compact=1&lite=1')
    assert 'router_health' not in lite_status['payload']
    assert lite_status_payloads and lite_status_payloads[0][0] == 'lite'
    pools = web_get_actions.dispatch(ctx, '/api/pools')
    assert pools['payload']['pools'] == {'vless': {'rows': []}}
    assert pools['payload']['custom_checks'] == [{'id': 'custom'}]
    assert pools['payload']['pool_summary'] == {'active_text': '1 / 5'}
    assert pools['payload']['pool_probe_running'] is True
    assert pools['payload']['pool_probe_progress'] == {'running': True, 'total': 2}
    builder_calls = []
    builder_ctx = dict(ctx)
    builder_ctx.update({
        'get_pool_probe_progress': lambda: {'running': False, 'total': 0},
        'web_pools_payload': lambda keys, protocols=None, include_summary=False, include_custom_checks=False: builder_calls.append(
            (keys, protocols, include_summary, include_custom_checks)
        ) or {
            'pools': {'worker': {'rows': []}},
            'pool_summary': {'active_text': 'worker'},
            'custom_checks': [{'id': 'worker'}],
        },
        'web_pool_snapshot': lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('builder should replace direct pool snapshot')),
        'pool_status_summary': lambda keys: (_ for _ in ()).throw(AssertionError('builder should replace direct pool summary')),
        'web_custom_checks': lambda: (_ for _ in ()).throw(AssertionError('builder should replace direct custom checks')),
    })
    builder_pools = web_get_actions.dispatch(builder_ctx, '/api/pools')
    assert builder_pools['payload']['pools'] == {'worker': {'rows': []}}
    assert builder_pools['payload']['pool_summary'] == {'active_text': 'worker'}
    assert builder_pools['payload']['custom_checks'] == [{'id': 'worker'}]
    assert builder_calls == [(current_keys, None, True, True)]
    scoped_builder = web_get_actions.dispatch(builder_ctx, '/api/pools', 'protocols=vless')
    assert scoped_builder['payload']['pool_summary'] is None
    assert scoped_builder['payload']['custom_checks'] is None
    assert builder_calls[-1] == (current_keys, ['vless'], False, False)
    summary_calls_before_scoped_pools = len(pool_summary_calls)
    sensitive_pools = web_get_actions.dispatch(ctx, '/api/pools', 'include_keys=1&protocols=vless')
    assert sensitive_pools['payload']['pools'] == {'vless': {'rows': []}}
    assert sensitive_pools['payload']['pool_summary'] is None
    assert sensitive_pools['payload']['custom_checks'] is None
    assert pool_snapshot_calls[-1] == (current_keys, False, ['vless'])
    service_routes_payload = web_get_actions.dispatch(ctx, '/api/service_routes')
    assert service_routes_payload['payload'] == {'route_tools_html': '<div>routes</div>'}
    scoped_pools = web_get_actions.dispatch(ctx, '/api/pools', 'protocols=vless,vmess')
    assert scoped_pools['payload']['pools'] == {'vless': {'rows': []}, 'vmess': {'rows': []}}
    assert scoped_pools['payload']['pool_summary'] is None
    assert scoped_pools['payload']['custom_checks'] is None
    assert len(pool_summary_calls) == summary_calls_before_scoped_pools
    assert pool_snapshot_calls[-1] == (current_keys, False, ['vless', 'vmess'])
    cached_pool_ctx = dict(ctx)
    cached_pool_payload = {
        'pools': {'cached': {'rows': []}},
        'pool_summary': {'active_text': 'cached'},
        'pool_probe_running': False,
        'pool_probe_paused': False,
        'pool_probe_progress': {'running': False, 'total': 0},
        'custom_checks': [],
        'timestamp': 124.0,
    }
    cached_pool_ctx.update({
        'get_pool_probe_progress': lambda: {'running': False, 'total': 0},
        'pools_api_cache_ttl': 10,
        'get_pools_api_cache': lambda keys, protocols, now=None: cached_pool_payload,
        'web_pool_snapshot': lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('cached pools should not rebuild snapshot')),
    })
    cached_pools = web_get_actions.dispatch(cached_pool_ctx, '/api/pools', 'protocols=vless')
    assert cached_pools['payload'] == cached_pool_payload
    raw_cached_pool_ctx = dict(cached_pool_ctx)
    raw_cached_pool_ctx['get_pools_api_cache'] = lambda keys, protocols, now=None: json.dumps(cached_pool_payload)
    raw_cached_pools = web_get_actions.dispatch(raw_cached_pool_ctx, '/api/pools', 'protocols=vless')
    assert raw_cached_pools['kind'] == 'json_text'
    assert json.loads(raw_cached_pools['text']) == cached_pool_payload
    stored_pool_payloads = []
    stored_pool_ctx = dict(ctx)
    stored_pool_ctx.update({
        'get_pool_probe_progress': lambda: {'running': False, 'total': 0},
        'pools_api_cache_ttl': 10,
        'get_pools_api_cache': lambda keys, protocols, now=None: None,
        'store_pools_api_cache': lambda keys, protocols, payload, timestamp=None: stored_pool_payloads.append((protocols, payload, timestamp)),
    })
    stored_pools = web_get_actions.dispatch(stored_pool_ctx, '/api/pools', 'protocols=vless')
    assert stored_pools['payload']['pool_probe_running'] is False
    assert stored_pool_payloads and stored_pool_payloads[0][0] == ['vless']
    cached_rows = {}
    cached_rows_builds = []
    cached_rows_ctx = dict(builder_ctx)
    cached_rows_ctx.update({
        'pools_api_cache_ttl': 10,
        'pools_api_build_lock': threading.Lock(),
        'get_pools_api_cache': lambda keys, protocols, now=None: cached_rows.get(tuple(protocols or ())),
        'store_pools_api_cache': lambda keys, protocols, payload, timestamp=None: cached_rows.setdefault(
            tuple(protocols or ()), payload
        ),
        'web_pools_payload': lambda keys, protocols=None, include_summary=False, include_custom_checks=False: cached_rows_builds.append(
            tuple(protocols or ())
        ) or {'pools': {'vless': {'rows': [{'key_id': 'cached-row'}]}}, 'pool_summary': None, 'custom_checks': None},
    })
    first_cached_rows = web_get_actions.dispatch(cached_rows_ctx, '/api/pools', 'protocols=vless')
    second_cached_rows = web_get_actions.dispatch(cached_rows_ctx, '/api/pools', 'protocols=vless')
    assert first_cached_rows['payload'] == second_cached_rows['payload']
    assert cached_rows_builds == [('vless',)]
    probe = web_get_actions.dispatch(ctx, '/api/pool_probe')
    assert probe['payload']['status'] == 'running'
    learning = web_get_actions.dispatch(ctx, '/api/telegram_call_learning')
    assert learning['payload']['telegram_call_learning']['seen_clients'] == ['192.168.1.23']
    metrics = web_get_actions.dispatch(ctx, '/api/router_metrics')
    assert metrics['payload']['summary']['samples'] == 1
    health = web_get_actions.dispatch(ctx, '/api/router_health', 'compact=1&force=1')
    assert health['payload']['cpu_percent'] == 2.0
    assert router_health_calls[-1] == {'compact': True, 'sample_cpu': True, 'force_refresh': True, 'prime_cpu': False}
    primed_health = web_get_actions.dispatch(ctx, '/api/router_health', 'compact=1&skip_cpu=1&prime=1')
    assert primed_health['payload']['cpu_percent'] == 2.0
    assert router_health_calls[-1] == {'compact': True, 'sample_cpu': False, 'force_refresh': False, 'prime_cpu': True}
    assert metrics['status'] == 200
    paused_ctx = dict(ctx)
    paused_ctx.update({
        'get_pool_probe_progress': lambda: {'running': False, 'checked': 4, 'total': 10, 'note': 'paused'},
        'has_pool_probe_resume_payload': lambda: True,
    })
    paused_status = web_get_actions.dispatch(paused_ctx, '/api/status')
    assert paused_status['payload']['pool_probe_running'] is False
    assert paused_status['payload']['pool_probe_paused'] is True
    paused_pools = web_get_actions.dispatch(paused_ctx, '/api/pools')
    assert paused_pools['payload']['pool_probe_paused'] is True
    paused_probe = web_get_actions.dispatch(paused_ctx, '/api/pool_probe')
    assert paused_probe['payload']['status'] == 'paused'
    assert paused_probe['payload']['paused'] is True
    panel = web_get_actions.dispatch(ctx, '/api/protocol_panel', 'proto=vless')
    assert panel['payload'] == {'ok': True, 'protocol': 'vless', 'html': 'panel:vless'}
    alias_panel = web_get_actions.dispatch(ctx, '/api/protocol_panel', 'protocol=vless2')
    assert alias_panel['payload'] == {'ok': True, 'protocol': 'vless2', 'html': 'panel:vless2'}
    check_panel = web_get_actions.dispatch(ctx, '/api/protocol_check_panel', 'proto=vless')
    assert check_panel['payload'] == {'ok': True, 'protocol': 'vless', 'html': 'check:vless'}
    script_asset = web_get_actions.dispatch({'build_script_asset': lambda: 'js'}, '/static/app.js')
    assert script_asset['cache_seconds'] == 31536000
    style_asset = web_get_actions.dispatch({'build_style_asset': lambda: 'css'}, '/static/app.css')
    assert style_asset['cache_seconds'] == 31536000
    static = web_get_actions.dispatch(ctx, '/static/service-icons/test.png')
    assert static['path'].replace('\\', '/').endswith('/service-icons/test.png')


def test_web_form_blocks_helpers():
    expected_protocol_order = ('vless', 'vless2', 'vmess', 'trojan', 'shadowsocks')
    assert key_pool_store.PROTOCOLS == expected_protocol_order
    assert web_form_blocks.PROXY_PROTOCOLS == expected_protocol_order
    assert tuple(item[0] for item in web_form_blocks.PROTOCOL_SECTIONS) == expected_protocol_order
    bot_source = source_path('bot.py').read_text(encoding='utf-8')
    assert "PROTOCOL_DISPLAY_ORDER = ('vless', 'vless2', 'vmess', 'trojan', 'shadowsocks')" in bot_source
    assert 'for key_name, key_value in _ordered_protocol_items(current_keys):' in bot_source
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
    assert web_form_blocks.status_refresh_pending(
        {'proxy_mode': 'vless', 'api_status': '✅ ok'},
        {'vless2': {'label': 'Проверяется'}},
        pool_probe_pending=False,
    ) is False
    assert web_form_blocks.status_refresh_pending(
        {'proxy_mode': 'vless', 'api_status': '✅ ok'},
        {'vless': {'label': 'Проверяется'}},
        pool_probe_pending=False,
    ) is True
    assert web_form_blocks.status_refresh_pending(
        {'proxy_mode': 'vless', 'api_status': '⏳ Telegram API не ответил вовремя через текущий режим.'},
        {'vless': {'label': 'Работает'}},
        pool_probe_pending=False,
    ) is True
    assert web_form_blocks.status_refresh_pending(
        {'proxy_mode': 'vless', 'api_status': 'Программа подбирает рабочий ключ из пула текущего режима; статус обновится без перезагрузки страницы'},
        {'vless': {'label': 'Работает'}},
        pool_probe_pending=False,
    ) is True
    quick_key = web_form_blocks.quick_key_context({'proxy_mode': 'none'}, {'vless': 'vless://sample'}, 'Без прокси')
    assert quick_key == {'proto': 'vless', 'label': 'Vless 1', 'value': 'vless://sample'}
    command_html = web_form_blocks.render_command_block(
        {
            'label': 'Обновить до последнего релиза',
            'command': 'update',
            'running': True,
            'progress_label': 'Подготовка',
        },
        live=True,
    )
    assert 'command-timer-block' in command_html
    assert 'command-progress-track' not in command_html
    assert 'data-command-progress-fill' not in command_html
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
    expected_mode_order = ('vless', 'vless2', 'vmess', 'trojan', 'shadowsocks', 'none')
    assert [button_picker.index(f'data-mode-value="{mode}"') for mode in expected_mode_order] == sorted(
        button_picker.index(f'data-mode-value="{mode}"') for mode in expected_mode_order
    )
    select_picker = web_form_blocks.render_select_mode_picker('none', '<input>')
    assert '<select' in select_picker
    assert [select_picker.index(f'value="{mode}"') for mode in expected_mode_order] == sorted(
        select_picker.index(f'value="{mode}"') for mode in expected_mode_order
    )
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
    light_tabs, light_panels = web_form_blocks.render_light_protocol_tabs_and_panels(
        [('vless', 'Vless 1', 3, 'vless://...')],
        {'vless': 'vless://sample'},
        {'vless': {'tone': 'ok', 'label': 'OK', 'details': 'details', 'endpoint_ok': True}},
        '<input name="csrf_token" value="token">',
        key_pools={'vless': ['vless://sample']},
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
    )
    assert 'data-protocol-target="vless"' in light_tabs
    assert 'data-core-service-head="telegram">TG</th>' in light_panels
    assert 'data-core-service-head="youtube">YT</th>' in light_panels
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
    assert 'data-list-line-count>2</span>' in panels
    assert 'csrf_token' in panels
    _tabs, lazy_panels = web_form_blocks.render_unblock_lists(
        [{'name': 'custom', 'label': 'Custom'}],
        '<input name="csrf_token">',
        (),
        'all',
        lambda key: key,
    )
    assert 'data-list-loaded="0"' in lazy_panels
    assert 'textarea name="content"' in lazy_panels and ' disabled>' in lazy_panels

def test_web_pool_form_blocks_helpers():
    table_class, custom_width, mobile_width = web_pool_form_blocks.pool_table_layout([{'id': 'chat'}])
    assert table_class == 'pool-table has-custom-checks'
    assert custom_width == 32
    assert mobile_width == 28
    progress = web_form_blocks.pool_probe_topbar_text(
        True,
        {'checked': 1, 'total': 2},
        lambda data: 'Проверка',
        'ok',
    )
    assert '1/2' in progress
    assert progress != 'ok'
    assert web_form_blocks.pool_summary_note_with_progress(
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
        key_probe_cache={'hash-vless': {
            'tg_ok': True,
            'yt_ok': True,
            'yt_quality': 'fast',
            'yt_score': 97,
            'yt_stream_tier': '4k',
            'yt_latency_ms': 350,
            'googlevideo_latency_ms': 480,
            'yt_throughput_mbps': 61.25,
        }},
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
    assert 'data-quality-score="97"' in pool_rows
    assert 'pool-quality-fast' in pool_rows
    assert 'Быстро' in pool_rows
    assert '61.25 Мбит/с' in pool_rows
    assert 'data-key=' not in pool_rows
    assert 'name="key_id" value="hash-vless"' in pool_rows
    assert 'name="key" value=' not in pool_rows
    assert 'vless://sample' not in pool_rows
    assert 'csrf_token' in pool_rows
    assert 'pool-delete-icon' in pool_rows
    assert '&times;' in pool_rows
    assert 'data-pool-mobile-checked' in pool_rows
    assert '>now</span>' in pool_rows
    warn_rows = web_pool_form_blocks.render_pool_items(
        key_name='vless2',
        title='Vless 2',
        pool_keys=['warn-key-value'],
        current_key='',
        key_probe_cache={'hash-warn': {'yt_ok': False, 'yt_stability': 'unstable'}},
        custom_checks=[],
        key_display_name=lambda key: 'warn-key',
        hash_key=lambda key: 'hash-warn',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        custom_check_badges=lambda probe, checks: '',
        probe_checked_at=lambda probe: '',
        csrf_input_html='<input name="csrf_token" value="token">',
    )
    assert 'data-yt-state="warn"' in warn_rows
    assert 'service-probe-warn' in warn_rows
    assert 'service-probe-icon-warn' in warn_rows
    assert 'YT</span>' in warn_rows
    assert 'service-probe-warn">!</span>' not in warn_rows
    unknown_rows = web_pool_form_blocks.render_pool_items(
        key_name='vless',
        title='Vless 1',
        pool_keys=['unknown-key-value'],
        current_key='',
        key_probe_cache={'hash-unknown': {'tg_ok': None, 'yt_ok': None}},
        custom_checks=[],
        key_display_name=lambda key: 'unknown-key',
        hash_key=lambda key: 'hash-unknown',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        custom_check_badges=lambda probe, checks: '',
        probe_checked_at=lambda probe: '',
        csrf_input_html='<input name="csrf_token" value="token">',
    )
    assert 'data-tg-state="unknown"' in unknown_rows
    assert 'data-yt-state="unknown"' in unknown_rows
    assert unknown_rows.count('service-probe-unknown">?</span>') >= 2
    assert '>TG<' not in unknown_rows
    not_applicable_rows = web_pool_form_blocks.render_pool_items(
        key_name='vless2',
        title='Vless 2',
        pool_keys=['route-scoped-key'],
        current_key='',
        key_probe_cache={'hash-scoped': {'tg_ok': True, 'yt_ok': False, 'yt_stability': 'fail', 'yt_score': 91}},
        custom_checks=[],
        key_display_name=lambda key: 'route-scoped',
        hash_key=lambda key: 'hash-scoped',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        custom_check_badges=lambda probe, checks: '',
        probe_checked_at=lambda probe: 'now',
        csrf_input_html='<input name="csrf_token" value="token">',
        service_applicability={'telegram': False, 'youtube': False},
    )
    assert 'data-tg-state="ok"' in not_applicable_rows
    assert 'data-yt-state="fail"' in not_applicable_rows
    assert 'data-quality-score="91"' in not_applicable_rows
    assert 'data-pool-tg' in not_applicable_rows
    assert 'data-pool-yt' in not_applicable_rows
    assert 'service-probe-na' not in not_applicable_rows
    assert 'pool-quality-' not in not_applicable_rows
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
        subscription_settings={'hwid_enabled': True},
    )
    assert 'protocol-workspace active' in panel
    assert 'vless://sample' in panel
    assert 'Ключ и подписка' in panel
    assert 'data-subview-target="subscription"' not in panel
    assert 'action="/pool_import"' in panel
    assert 'class="pool-import-form"' in panel
    assert 'name="import_payload"' in panel
    assert 'Импорт ключей и подписки' in panel
    assert 'pool-sort-control' in panel
    assert 'data-pool-sort-value="telegram"' in panel
    assert 'data-pool-sort-value="quality"' in panel
    assert 'data-pool-sort-value="active"' not in panel
    assert 'data-pool-sort-value="problem"' in panel
    assert 'custom-check-form' in panel
    assert 'data-pool-probe-start-button aria-disabled="false"' in panel
    assert 'data-pool-probe-cancel-button disabled aria-disabled="true"' in panel
    assert 'name="send_router_hwid" value="1" checked' in panel
    assert 'Передавать HWID роутера' in panel
    check_content = web_pool_form_blocks.render_protocol_check_content(
        key_name='vless',
        title='Vless 1',
        status_info={'tone': 'ok', 'label': 'OK', 'details': 'details'},
        custom_presets_html='<div>preset</div>',
        custom_checks_html='<div>checks</div>',
        route_tools_html='<div>routes</div>',
        csrf_input_html='<input name="csrf_token" value="token">',
    )
    assert 'custom-check-form' in check_content
    assert 'data-route-tools-root' in check_content
    assert '<div>routes</div>' in check_content
    assert '<div>checks</div>' in check_content
    deferred_check_panel = web_pool_form_blocks.render_protocol_panel(
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
        custom_presets_html='<div>preset</div>',
        custom_checks_html='<div>checks</div>',
        route_tools_html='<div>routes</div>',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        csrf_input_html='<input name="csrf_token" value="token">',
        defer_check_content=True,
    )
    assert 'data-protocol-check-deferred="vless"' in deferred_check_panel
    assert 'custom-check-form' not in deferred_check_panel
    assert '<div>routes</div>' not in deferred_check_panel
    assert '<div>checks</div>' not in deferred_check_panel
    youtube_panel = web_pool_form_blocks.render_protocol_panel(
        key_name='vless2',
        title='Vless 2',
        rows=3,
        placeholder='vless://...',
        current_key_value='',
        status_info={'tone': 'ok', 'label': 'OK', 'details': 'details'},
        active_status_icons='',
        pool_items_html=web_pool_form_blocks.POOL_EMPTY_ROW_HTML,
        pool_table_class='pool-table',
        pool_custom_col_width=32,
        pool_mobile_custom_col_width=28,
        custom_header_icons='',
        custom_presets_html='',
        custom_checks_html='',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        csrf_input_html='<input name="csrf_token" value="token">',
    )
    assert 'data-core-service-head="telegram"' in youtube_panel
    assert 'data-core-service-head="youtube"' in youtube_panel
    assert 'colspan="6"' in youtube_panel
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
    assert 'pool-import-form' not in main_panel
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
    assert 'data-core-services-loaded="0"' in panels_html
    assert 'data-protocol-live-status="0"' in panels_html
    assert 'vless://sample' in panels_html
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
    deferred_tabs_html, deferred_panels_html = web_pool_form_blocks.render_protocol_tabs_and_panels(
        [('vless', 'Vless 1', 3, 'vless://...')],
        {'vless': ''},
        {'vless': {'tone': 'ok', 'label': 'OK', 'details': 'details'}},
        '<input name="csrf_token" value="token">',
        key_pools={'vless': ['deferred-pool-key']},
        key_display_name=lambda key: 'deferred display',
        hash_key=lambda key: 'deferredhash',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        defer_pool_rows=True,
        defer_check_content=True,
    )
    assert 'tab-count">1</span>' in deferred_tabs_html
    assert 'data-pool-deferred="1"' in deferred_panels_html
    assert 'data-protocol-check-deferred="vless"' in deferred_panels_html
    assert 'pool-empty-row' in deferred_panels_html
    assert 'Загружаю пул ключей...' in deferred_panels_html
    assert 'Пул пуст. Добавьте ключи или загрузите subscription' not in deferred_panels_html
    assert 'deferred-pool-key' not in deferred_panels_html
    assert 'deferred display' not in deferred_panels_html
    scoped_tabs_html, scoped_panels_html = web_pool_form_blocks.render_protocol_tabs_and_panels(
        [
            ('vless', 'Vless 1', 3, 'vless://...'),
            ('vmess', 'Vmess', 3, 'vmess://...'),
        ],
        {'vless': 'vless://sample', 'vmess': 'vmess://sample'},
        {
            'vless': {'tone': 'ok', 'label': 'OK', 'details': 'details'},
            'vmess': {'tone': 'ok', 'label': 'OK', 'details': 'details'},
        },
        '<input name="csrf_token" value="token">',
        key_pools={'vless': ['vless://sample'], 'vmess': ['vmess://sample']},
        key_probe_cache={
            'vless://sample': {'tg_ok': True, 'yt_ok': True, 'custom': {'discord': True}},
            'vmess://sample': {'tg_ok': True, 'yt_ok': True, 'custom': {'discord': True}},
        },
        custom_checks=[{'id': 'discord', 'label': 'Discord'}],
        custom_checks_for_protocol=lambda protocol, checks: checks if protocol == 'vless' else [],
        custom_header_icons_for_protocol=lambda protocol, checks: ''.join(f'H-{check["id"]}' for check in checks),
        custom_check_badges=lambda probe, checks: ''.join(f'B-{check["id"]}' for check in checks),
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
    )
    assert scoped_tabs_html.count('protocol-tab') == 2
    assert 'H-discord' in scoped_panels_html
    assert 'B-discord' in scoped_panels_html
    vmess_panel_html = scoped_panels_html.split('data-protocol-panel="vmess"', 1)[1]
    assert 'H-discord' not in vmess_panel_html
    assert 'B-discord' not in vmess_panel_html
    status_tabs_html, status_panels_html = web_pool_form_blocks.render_protocol_tabs_and_panels(
        [('vless', 'Vless 1', 3, 'vless://...')],
        {'vless': 'vless://sample'},
        {'vless': {'tone': 'ok', 'label': 'OK', 'details': 'details', 'endpoint_ok': True, 'api_ok': True, 'yt_ok': False}},
        '<input name="csrf_token" value="token">',
        key_pools={'vless': ['vless://sample']},
        key_probe_cache={'vless://sample': {'tg_ok': False, 'yt_ok': True}},
        core_service_applicability_for_protocol=lambda protocol: {'telegram': True, 'youtube': False},
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
    )
    assert 'protocol-tab active' in status_tabs_html
    assert 'data-protocol-live-status="1"' in status_panels_html
    assert '<span class="key-status-icons" data-protocol-status-icons>TG</span>' in status_panels_html
    assert 'key-status-ok' in status_panels_html
    vless2_status_tabs_html, vless2_status_panels_html = web_pool_form_blocks.render_protocol_tabs_and_panels(
        [('vless2', 'Vless 2', 3, 'vless://...')],
        {'vless2': 'checked-key-value'},
        {'vless2': {'tone': 'empty', 'label': 'Not checked', 'details': 'empty', 'api_ok': False, 'yt_ok': False}},
        '<input name="csrf_token" value="token">',
        key_pools={'vless2': ['checked-key-value']},
        key_probe_cache={'checked-key-value': {'tg_ok': False, 'yt_ok': True}},
        core_service_applicability_for_protocol=lambda protocol: {'telegram': False, 'youtube': True},
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
    )
    assert 'protocol-tab active' in vless2_status_tabs_html
    assert 'data-core-services="youtube"' in vless2_status_panels_html
    assert 'data-core-services-loaded="1"' in vless2_status_panels_html
    assert 'key-status-ok' in vless2_status_panels_html
    assert 'key-status-empty' not in vless2_status_panels_html
    assert '<span class="key-status-icons" data-protocol-status-icons>YT</span>' in vless2_status_panels_html


def test_web_status_builder_helpers():
    assert web_status_builder.empty_protocol_status()['tone'] == 'empty'
    unused_cached = web_status_builder.cached_protocol_status(
        'key',
        {},
        [],
        {},
        required_services=(),
    )
    assert unused_cached['tone'] == 'empty'
    assert unused_cached['yt_state'] == 'unused'
    unused_active = web_status_builder.active_protocol_status(
        endpoint_ok=True,
        endpoint_message='SOCKS ok.',
        api_ok=False,
        api_message='',
        api_transient=False,
        yt_ok=False,
        yt_message='',
        custom_states={},
        custom_checks=[],
        required_services=(),
    )
    assert unused_active['tone'] == 'empty'
    assert unused_active['yt_state'] == 'unused'
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
    telegram_scoped = web_status_builder.cached_protocol_status(
        'key',
        {'tg_ok': True, 'yt_ok': False, 'yt_stability': 'unstable'},
        [],
        {},
        required_services=['telegram'],
    )
    assert telegram_scoped['tone'] == 'ok'
    assert telegram_scoped['label'] == 'Работает'
    youtube_scoped = web_status_builder.cached_protocol_status(
        'key',
        {'tg_ok': False, 'yt_ok': False, 'yt_stability': 'unstable'},
        [],
        {},
        required_services=['youtube'],
    )
    assert youtube_scoped['tone'] == 'ok'
    assert youtube_scoped['label'] == 'Работает'
    youtube_only = web_status_builder.cached_protocol_status(
        'key',
        {'tg_ok': False, 'yt_ok': True},
        [],
        {},
        api_required=False,
    )
    assert youtube_only['tone'] == 'ok'
    scoped_checks = key_pool_web.protocol_custom_checks(
        [{'id': 'discord', 'label': 'Discord'}],
        {'discord': {'complete_protocols': ['vless'], 'partial_protocols': []}},
        'vmess',
    )
    scoped_states = key_pool_web.web_custom_probe_states(
        {'tg_ok': True, 'yt_ok': True, 'custom': {'discord': True}},
        scoped_checks,
    )
    scoped_status = web_status_builder.cached_protocol_status(
        'key',
        {'tg_ok': True, 'yt_ok': True, 'custom': {'discord': True}},
        scoped_checks,
        scoped_states,
    )
    assert scoped_status['custom'] == {}
    assert 'Discord' not in scoped_status['details']
    assert 'не требуется для текущего режима' in youtube_only['details']


def test_web_template_styles_helpers():
    styles = (APP_ROOT / 'static' / 'app.css').read_text(encoding='utf-8')
    assert ':root{' in styles
    assert '.app-shell' in styles
    assert 'url("/static/telegram.svg")' in styles
    assert 'tg-icon' not in styles
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
    assert 'body.event-history-open{overflow:hidden;}' in styles
    assert '.event-history-backdrop{position:fixed;inset:0;z-index:720;display:flex;align-items:stretch;justify-content:flex-end;padding:14px;background:rgba(2,6,23,.62);overscroll-behavior:contain;}' in styles
    assert '.event-history-drawer{width:min(720px,calc(100vw - 28px));max-height:calc(100dvh - 28px);' in styles
    assert '.event-history-drawer [data-event-history-list]{min-height:0;overflow:hidden;display:grid;}' in styles
    assert '.event-history-drawer .event-history-list{min-height:0;max-height:100%;overflow:auto;padding-right:4px;grid-template-columns:1fr;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;}' in styles
    assert '.event-history-drawer{width:100%;height:100dvh;max-height:100dvh;' in styles
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
    assert '.topbar-status{justify-content:flex-start;gap:8px;text-align:left;overflow:hidden;white-space:normal;max-height:60px;}' in styles
    assert '.topbar-status-copy span{display:-webkit-box;min-width:0;color:#b9c6d3;font-size:11px;font-weight:700;line-height:1.22;max-height:calc(1.22em * 2);white-space:normal;overflow:hidden;text-overflow:ellipsis;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow-wrap:anywhere;word-break:normal;}' in styles
    assert '.topbar-status{white-space:normal;text-overflow:clip;}' in styles
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
    assert '.topbar-actions.topbar-actions-web-only{grid-template-columns:minmax(0,1fr) minmax(170px,.38fr) auto;}' in styles
    assert '.topbar-actions-web-only .theme-control{justify-self:stretch;width:100%;}' in styles
    assert '.topbar-actions-web-only .theme-toggle{width:100%;min-width:0;}' in styles
    assert '.topbar-actions-web-only .theme-control{grid-column:1 / -1;grid-row:2;justify-self:stretch;width:100%;}' in styles
    assert '.app-caption strong{max-width:none;padding-right:60px;font-size:14px;line-height:1.18;white-space:normal;}' in styles
    assert '.app-branch{font-size:10.5px;line-height:1.18;white-space:nowrap;overflow:hidden;text-overflow:clip;overflow-wrap:normal;word-break:normal;}' in styles
    assert '.topbar{position:relative;z-index:260;' in styles
    assert '.mode-control,.theme-control{position:relative;min-width:0;}' in styles
    assert '.mode-control #mode-picker,.theme-control .theme-picker{top:calc(100% + 8px);width:min(320px,calc(100vw - 32px));min-width:260px;z-index:330;}' in styles
    assert '.mode-control #mode-picker,.theme-control .theme-picker{position:absolute;top:calc(100% + 8px);width:min(260px,calc(100vw - 42px));min-width:0;max-height:min(360px,calc(100vh - 220px));overflow:auto;z-index:330;}' in styles
    assert 'html.command-running body{min-height:100vh;}' in styles
    assert 'html.command-running .app-main,' in styles
    assert '.app-view[data-view="status"].active{grid-template-rows:auto auto auto auto;align-content:start;gap:8px;overflow:hidden;}' in styles
    assert '.topbar{position:relative;z-index:260;top:0;padding:8px 10px;margin-bottom:8px;' in styles
    assert '.workspace-layout{flex:1;min-height:0;gap:8px;align-items:stretch;}' in styles
    assert '.view-head,.segmented,.status-dashboard,.overview-service-grid{margin-bottom:0;}' in styles
    assert '.status-dashboard-with-pool .status-dashboard-column{display:grid;grid-template-rows:auto minmax(0,1fr);gap:8px;align-content:stretch;align-items:stretch;min-width:0;height:100%;}' in styles
    assert '.status-dashboard-with-pool .router-health-card,.status-dashboard-with-pool .key-pool-card{height:100%;align-self:stretch;}' in styles
    assert '.router-health-card #router-health-note{white-space:pre-line;}' in styles
    assert '.inline-page-title{display:flex;align-items:baseline;gap:8px;min-width:0;margin:0 0 4px;color:var(--text);font-size:13px;font-weight:800;line-height:1.22;' in styles
    assert '.inline-page-title .title-kicker{flex:none;color:#d3a557;font-size:inherit;font-weight:inherit;letter-spacing:0;text-transform:none;line-height:inherit;}' in styles
    assert '.section-subtitle{font-size:12px;line-height:1.35;}' in styles
    assert '.key-status-note{margin:3px 0 0;font-size:12px;line-height:1.35;}' in styles
    assert '.protocol-subview-check.active > .status-card .status-note{white-space:normal;overflow:visible;text-overflow:clip;' in styles
    assert '.pool-controls{display:grid;grid-template-columns:minmax(240px,520px) minmax(180px,240px);' in styles
    assert '.pool-sort-menu.hidden{display:none;}' in styles
    assert '.pool-sort-divider' in styles
    assert '#f7f3ea' not in styles
    assert '#ece3d4' not in styles
    assert '#fff1d7' not in styles
    assert '#f4f7fb' not in styles
    assert '#f8fbff' not in styles
    assert 'rgba(238,222,191' not in styles
    assert '--bg:#dde2e8;' in styles
    assert '--surface:#e7ebf0;' in styles
    assert '.pool-apply-btn{width:100%;min-width:0;padding:4px 0;border:none;background:transparent;box-shadow:none;color:var(--text);font-size:12px;font-weight:700;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:flex;align-items:center;justify-content:flex-start;gap:6px;}' in styles
    assert '.pool-apply-btn{display:flex;width:100%;font-size:10.5px;line-height:1.18;text-align:left;justify-content:flex-start;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;gap:4px;}' in styles
    assert '.subtabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));' in styles
    assert '.protocol-subview-key.active{display:grid;gap:8px;align-content:start;overflow:visible;}' in styles
    assert '.protocol-subview-key .key-editor-form,.protocol-subview-key .pool-import-form{padding:8px;border:1px solid rgba(91,124,150,.28);border-radius:9px;background:rgba(255,255,255,.025);min-width:0;}' in styles
    assert '.pool-import-form{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:end;}' in styles
    assert '.pool-import-form textarea{min-width:0;width:100%;max-width:100%;min-height:92px;resize:none;overflow:hidden;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;}' in styles
    assert '.protocol-subview-key .key-editor-form{display:grid;grid-template-columns:minmax(0,1fr) 180px;grid-template-rows:auto auto;gap:6px 10px;align-items:start;}' in styles
    assert '.protocol-subview-key .key-editor-form textarea[data-key-textarea]{grid-column:1;grid-row:2;height:72px;min-height:72px;max-height:none;resize:none;white-space:pre-wrap;overflow:hidden;overflow-wrap:anywhere;word-break:break-all;}' in styles
    assert '.subtabs .subtab:nth-child(3){grid-column:1 / -1;}' in styles
    assert '.subtabs .subtab:nth-child(3):last-child{grid-column:1 / -1;}' in styles
    assert '.pool-import-form button{grid-column:2;grid-row:3;justify-self:stretch;width:100%;align-self:start;}' in styles
    assert '.health-meter.warn span' in styles
    assert '.status-overview-head{display:block;padding:12px 14px;}' in styles
    assert '.topbar-status-icon-telegram{background-image:url("/static/telegram.svg");}' in styles
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

    assert probe_cache.update_key_probe_cache_entry(
        cache,
        'vless',
        'string-key',
        tg_ok='false',
        yt_ok='0',
        custom={'custom': 'no'},
        custom_checks=[{'id': 'custom', 'urls': ['https://example.test']}],
        now=100,
        min_write_interval=0,
    )
    string_entry = cache[probe_cache.hash_key('string-key')]
    assert string_entry['tg_ok'] is False
    assert string_entry['yt_ok'] is False
    assert string_entry['custom']['custom'] is False

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


def test_probe_cache_trims_error_text_fields():
    cache = {}
    long_error = 'network error\n' + ('x' * 300)
    assert probe_cache.update_key_probe_cache_entry(
        cache,
        'vless',
        'error-key',
        yt_ok=False,
        timeout=True,
        timeout_reason=long_error,
        yt_last_error=long_error,
        quality_error=long_error,
        now=100,
    )
    entry = cache[probe_cache.hash_key('error-key')]
    assert len(entry['timeout_reason']) <= probe_cache.KEY_PROBE_ERROR_TEXT_MAX_CHARS
    assert len(entry['yt_last_error']) <= probe_cache.KEY_PROBE_ERROR_TEXT_MAX_CHARS
    assert len(entry['quality_error']) <= probe_cache.KEY_PROBE_ERROR_TEXT_MAX_CHARS
    assert '\n' not in entry['timeout_reason']
    assert entry['timeout_reason'].startswith('network error')


def test_probe_cache_quality_metrics():
    cache = {}
    assert probe_cache.update_key_probe_cache_entry(
        cache,
        'vless2',
        'quality-key',
        tg_ok=True,
        yt_ok=True,
        tg_latency_ms=420.4,
        yt_latency_ms=510.1,
        googlevideo_latency_ms=630.8,
        yt_watch_ok=True,
        yt_short_ok=True,
        yt_throughput_mbps=52.6,
        now=100,
        min_1600p_mbps=25.0,
        min_4k_mbps=45.0,
    )
    entry = cache[probe_cache.hash_key('quality-key')]
    assert entry['tg_latency_ms'] == 420
    assert entry['yt_latency_ms'] == 510
    assert entry['googlevideo_latency_ms'] == 631
    assert entry['yt_watch_ok'] is True
    assert entry['yt_short_ok'] is True
    assert entry['yt_throughput_mbps'] == 52.6
    assert entry['yt_throughput_ts'] == 100
    assert entry['yt_quality'] == 'fast'
    assert entry['yt_stream_tier'] == '4k'
    assert entry['yt_score'] >= 90

    assert probe_cache.update_key_probe_cache_entry(
        cache,
        'vless2',
        'quality-key',
        yt_ok=True,
        yt_latency_ms=600,
        googlevideo_latency_ms=700,
        now=200,
        min_1600p_mbps=25.0,
        min_4k_mbps=45.0,
    )
    refreshed_entry = cache[probe_cache.hash_key('quality-key')]
    assert 'yt_throughput_mbps' not in refreshed_entry
    assert 'yt_quality' not in refreshed_entry
    assert 'yt_stream_tier' not in refreshed_entry

    stable = probe_cache.youtube_quality_score(
        yt_ok=True,
        yt_latency_ms=1200,
        googlevideo_latency_ms=1300,
        yt_throughput_mbps=28.0,
        min_1600p_mbps=25.0,
        min_4k_mbps=45.0,
    )
    assert stable['yt_quality'] == 'stable'
    assert stable['yt_stream_tier'] == '1600p'

    stable_with_soft_error = probe_cache.youtube_quality_score(
        yt_ok=True,
        yt_latency_ms=500,
        googlevideo_latency_ms=600,
        googlevideo_ok=True,
        yt_error_rate=0.125,
        yt_stability='stable',
        yt_throughput_mbps=55.0,
        min_1600p_mbps=25.0,
        min_4k_mbps=45.0,
    )
    assert stable_with_soft_error['yt_score'] > 55
    assert stable_with_soft_error['yt_quality'] == 'fast'

    latency_only = probe_cache.youtube_quality_score(
        yt_ok=True,
        yt_latency_ms=700,
        googlevideo_latency_ms=800,
        yt_throughput_mbps=None,
        min_1600p_mbps=25.0,
        min_4k_mbps=45.0,
    )
    assert latency_only['yt_quality'] == ''
    assert latency_only['yt_stream_tier'] == ''

    unstable = probe_cache.youtube_quality_score(
        yt_ok=True,
        yt_latency_ms=500,
        googlevideo_latency_ms=600,
        googlevideo_ok=False,
        yt_error_rate=0.125,
        yt_stability='unstable',
        yt_throughput_mbps=55.0,
        min_1600p_mbps=25.0,
        min_4k_mbps=45.0,
    )
    assert 0 < unstable['yt_score'] <= 55
    assert unstable['yt_quality'] == ''
    ok_with_unstable_metrics = {
        'schema': probe_cache.KEY_PROBE_CACHE_SCHEMA_VERSION,
        'ts': 100,
        'yt_ok': True,
        'yt_stability': 'unstable',
    }
    assert probe_cache.youtube_probe_state(ok_with_unstable_metrics) == 'ok'
    warn_entry = {
        'schema': probe_cache.KEY_PROBE_CACHE_SCHEMA_VERSION,
        'ts': 100,
        'yt_ok': False,
        'yt_stability': 'unstable',
    }
    assert probe_cache.youtube_probe_state(warn_entry) == 'warn'
    assert probe_cache.youtube_probe_effective_ok(warn_entry) is True
    assert probe_cache.key_probe_is_fresh(warn_entry, now=100 + probe_cache.KEY_PROBE_FAILURE_TTL + 10) is True


def test_probe_cache_ignores_stale_schema(tmp_path):
    cache_path = tmp_path / 'key_probe_cache.json'
    old_path = probe_cache.KEY_PROBE_CACHE_PATH
    probe_cache.KEY_PROBE_CACHE_PATH = str(cache_path)
    try:
        fresh_key = probe_cache.hash_key('fresh')
        compat_key = probe_cache.hash_key('compat')
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
                compat_key: {
                    'schema': 6,
                    'proto': 'vless2',
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
    assert loaded[compat_key]['schema'] == probe_cache.KEY_PROBE_CACHE_SCHEMA_VERSION
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
        'key-override',
        tg_ok=True,
        yt_ok=True,
        custom={'chatgpt_services': True},
        custom_checks=checks,
        now=100,
    )
    assert probe_cache.update_key_probe_cache_entry(
        cache,
        'vless',
        'key-override',
        tg_ok=False,
        yt_ok=False,
        custom={'chatgpt_services': False},
        custom_checks=checks,
        now=120,
        min_write_interval=0,
        allow_recent_success_downgrade=True,
    )
    override_entry = cache[probe_cache.hash_key('key-override')]
    assert override_entry['tg_ok'] is False
    assert override_entry['yt_ok'] is False
    assert override_entry['custom']['chatgpt_services'] is False

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
    scripts = (APP_ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
    assert 'const APP_CONFIG = window.BK_APP_CONFIG || {};' in scripts
    assert 'const INITIAL_STATUS_PENDING = !!APP_CONFIG.initialStatusPending;' in scripts
    assert 'const STATUS_ACTIVE_POLL_MS = 8000;' in scripts
    assert "const STATUS_IDLE_POLL_MS = Math.max(30000, Number(APP_CONFIG.statusIdlePollMs || 60000));" in scripts
    assert "const POOL_PROBE_STATUS_POLL_MS = Math.max(5000, Number(APP_CONFIG.poolProbeStatusPollMs || 10000));" in scripts
    assert "const POOL_PROBE_POOL_REFRESH_MS = Math.max(10000, Number(APP_CONFIG.poolProbePoolRefreshMs || 15000));" in scripts
    assert "if (!ENABLE_LIVE_STATUS || document.hidden)" in scripts
    assert "fetch('/api/status?compact=1&lite=1'" in scripts
    assert "fetch('/api/router_health?compact=1' + forceQuery" in scripts
    assert "fetch('/api/router_health?compact=1&skip_cpu=1&prime=1'" not in scripts
    assert "refreshRouterHealth(false, 0);" in scripts
    assert 'scheduleRouterHealthRefresh(10000)' in scripts
    startup_setup = scripts.split('setupViewNavigation();', 1)[1].split('setupLiquidPointer();', 1)[0]
    assert 'refreshDeferredServiceRouteTools();' not in startup_setup
    check_loader = scripts.split('function loadProtocolCheck', 1)[1].split('function setupProtocolSubtabs', 1)[0]
    assert 'refreshDeferredServiceRouteTools();' in check_loader
    assert "fetch('/api/unblock_list?name='" in scripts
    assert "const delay = Date.now() < statusPollUntil ? STATUS_ACTIVE_POLL_MS : STATUS_IDLE_POLL_MS;" in scripts
    assert "scheduleStatusPolling(STATUS_IDLE_POLL_MS, STATUS_IDLE_POLL_MS);" in scripts
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
    assert 'function protocolQuery(protocols)' in scripts
    assert 'function loadedPoolProtocolQuery(requestedProtocols)' in scripts
    assert 'function deferredPoolProtocols()' in scripts
    assert 'function clearPoolDeferred(body)' in scripts
    assert 'body.removeAttribute(\'data-pool-deferred\')' in scripts
    assert '[data-pool-deferred="1"]' in scripts
    assert 'function keysViewActive()' in scripts
    assert 'function refreshDeferredPoolForProtocol(protocol)' in scripts
    assert "if (selected === 'keys')" in scripts
    assert 'refreshDeferredPoolForProtocol(selected)' in scripts
    assert 'const pendingPoolDataProtocols = new Set();' in scripts
    assert 'pendingPoolDataProtocols.add(proto);' in scripts
    assert 'const requestedProtocols = poolDataRefreshAll ? [] : Array.from(pendingPoolDataProtocols);' in scripts
    assert 'refreshPoolData(0, protocol)' in scripts
    assert 'function schedulePoolView(proto, delayMs)' in scripts
    assert 'const rowByKeyId = new Map();' in scripts
    assert 'Object.prototype.hasOwnProperty.call(stateMap, check.id)' in scripts
    assert "fetch('/api/pools' + loadedPoolProtocolQuery(requestedProtocols.length ? requestedProtocols : null)" in scripts
    assert "setPoolBodyMessage(proto, 'Загружаю пул ключей...', true)" in scripts
    assert "refreshPoolData(3000, retryProtocols)" in scripts
    assert 'function webStatusIsPending(apiStatus)' in scripts
    assert 'function webStatusIsRealFailure(apiStatus)' in scripts
    assert 'return pending && !webStatusIsRealFailure(text);' in scripts
    pending_start = scripts.index('function markProtocolPending(proto, text)')
    pending_end = scripts.index('function markPoolKeyActive(proto, keyId)', pending_start)
    pending_body = scripts[pending_start:pending_end]
    assert "badge.textContent = 'Статус обновляется';" in pending_body
    assert "icons.innerHTML = '';" not in pending_body
    assert "return ['info', 'Статус обновляется', 'Проверяется актуальное состояние', botReady];" in scripts
    assert 'function scheduleStatusPolling(durationMs, initialDelayMs)' in scripts
    assert 'const initialDelay = Math.max(0, Number(initialDelayMs || 0));' in scripts
    assert 'scheduleStatusPolling(STATUS_IDLE_POLL_MS, STATUS_IDLE_POLL_MS)' in scripts
    assert "let pending = webStatusIsPending(web.api_status || '')" in scripts
    assert "proto === web.proxy_mode && status && (status.label === 'Проверяется' || status.api_pending)" in scripts
    assert "(web.api_status || '').indexOf('перепроверяется')" not in scripts
    assert 'function updateTelegramCallLearning(state)' not in scripts
    assert "fetch('/api/telegram_call_learning'" not in scripts
    assert "action === 'telegram-call-learn'" not in scripts
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
    assert 'payload.key;' not in scripts
    assert 'payload.key ||' not in scripts
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
    assert 'function setCommandRunningLayout(running)' in scripts
    assert "document.documentElement.classList.toggle('command-running', !!running);" in scripts
    assert 'function commandTimerText(state)' in scripts
    assert 'expected_seconds' in scripts
    assert 'в среднем' in scripts
    assert 'expectedWithRestart = expected + 5' in scripts
    assert 'обычно около' not in scripts
    assert 'дольше среднего' in scripts
    assert 'осталось около' not in scripts
    assert 'elapsed * (100 - progress) / progress' not in scripts
    assert 'data-command-progress-fill' not in scripts
    assert "sortMode === 'quality'" in scripts
    assert "state === 'warn'" in scripts
    assert 'service-probe-warn' in scripts
    assert 'service-probe-icon-warn' in scripts
    assert 'function poolCoreServices(pool)' in scripts
    assert 'Array.isArray(pool.core_services)' in scripts
    assert 'function poolTableCoreServices()' in scripts
    assert "const statusCoreServices = poolCoreServices(pool);" in scripts
    assert "const coreServices = poolTableCoreServices();" in scripts
    assert "if (tgState === 'ok' || tgState === 'warn') {" in scripts
    assert "icons += serviceIcon(TELEGRAM_ICON_SRC, 'Telegram');" in scripts
    assert "icons += serviceIcon(YOUTUBE_ICON_SRC, 'YouTube');" in scripts
    assert "card.dataset.protocolLiveStatus === '1'" in scripts
    assert 'function seedProtocolStatusIcons(card)' in scripts
    assert "icons.innerHTML = stableProtocolStatusIcons(card, status.icons, true, false);" in scripts
    assert 'refreshPoolData: refreshPoolData' in scripts
    assert 'function poolCustomChecks(pool)' in scripts
    assert 'pool && Array.isArray(pool.custom_checks)' in scripts
    assert 'renderCustomBadges(row.custom, checks)' in scripts
    assert 'head.innerHTML = customHeaderIcons(checks)' in scripts
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
    assert 'function parseJsonPayload(response)' in scripts
    assert "return response.text().then(function(text)" in scripts
    assert "lowerMessage.indexOf('http 404')" in scripts
    assert "fetch('/api/protocol_panel?proto='" in scripts
    assert 'function protocolLoadErrorMessage(error)' in scripts
    assert "lowerMessage.indexOf('failed to fetch')" in scripts
    assert 'function showLoadNotice(panel, message)' in scripts
    assert 'loadPanel(protocol, panel, retryCount + 1)' in scripts
    assert 'function loadProtocolCheck(panel, retryCount)' in scripts
    assert "fetch('/api/protocol_check_panel?proto='" in scripts
    assert 'if (retryCount < 6 && !document.hidden)' in scripts
    assert 'data-protocol-check-retry' in scripts
    assert 'loadProtocolCheck(panel, retryCount + 1)' in scripts
    assert 'data-protocol-check-deferred' in scripts
    assert 'setupServiceRouteMenus(subview)' in scripts
    assert 'setupAsyncForms(subview)' in scripts
    assert 'data-key="' not in scripts
    assert 'name="key_id"' in scripts
    assert 'function setupProtocolSubtabs(root)' in scripts
    assert 'function renderStatusAttention(snapshot)' in scripts
    assert 'function renderTopbarStatus(snapshot)' in scripts
    assert "items.push(['info', 'Проверка пула выполняется'" not in scripts
    assert 'проверка пула сейчас не мешает работе' not in scripts
    assert 'poolProbeVisible' in scripts
    assert "pill.innerHTML = (showTelegramIcon" in scripts
    assert 'function updatePoolProbeControls(active, paused)' in scripts
    assert 'function freshPoolProbeProgress(progress)' in scripts
    assert 'startedAt === previousStartedAt && checked < previousChecked' in scripts
    assert 'let latestPoolSummary = null;' in scripts
    assert 'function autoResizeTextarea(textarea)' in scripts
    assert 'function stablePoolSummary(poolSummary, running, paused)' in scripts
    assert 'latestChecked > 0 && checked === 0 && total >= latestTotal' in scripts
    assert 'textarea.offsetParent === null' in scripts
    assert 'textarea.getBoundingClientRect().width < 80' in scripts
    assert 'setupAutoResizeTextareas(panel);' in scripts
    assert 'function poolProbeSummaryText(progress, fallbackNote)' in scripts
    assert 'function pollPoolProbeStatus()' in scripts
    assert "fetch('/api/pool_probe'" in scripts
    assert 'function applyPoolProbeStatusPayload(payload)' in scripts
    assert 'function refreshStatusSoon(delayMs, durationMs)' in scripts
    assert "['pool-add', 'pool-delete', 'pool-clear', 'pool-subscribe', 'pool-import']" in scripts
    assert 'schedulePoolProbePolling(1200)' in scripts
    assert "setOptionalText('pool-summary-note', progressSummary)" in scripts
    assert "document.querySelectorAll('[data-pool-probe-cancel-button]')" in scripts
    assert 'if ((poolProbeActive || poolProbePaused) && !document.hidden)' in scripts
    assert 'refreshPoolData(POOL_PROBE_POOL_REFRESH_MS)' in scripts
    assert 'statusPollUntil = Math.max(statusPollUntil, Date.now() + POOL_PROBE_POLL_EXTENSION_MS)' not in scripts
    assert 'refreshPoolData(2500)' not in scripts
    assert 'function fetchRouterMetrics()' in scripts
    assert "fetch('/api/router_metrics?compact=1'" in scripts
    assert 'refreshPoolData(0, deferredProtocols)' not in scripts
    assert 'function fetchEventHistory()' in scripts
    assert "fetch('/api/event_history'" in scripts
    assert 'Загружаю историю...' in scripts
    assert 'История временно недоступна' in scripts
    assert 'Р—Р°РіСЂ' not in scripts
    assert 'function lockPageScroll()' in scripts
    assert "document.body.style.position = 'fixed';" in scripts
    assert 'function unlockPageScroll()' in scripts
    assert 'window.scrollTo(0, lockedScrollY);' in scripts
    assert 'data-event-history-tab' not in scripts
    assert "modal.querySelectorAll('[data-router-metrics-refresh]')" in scripts
    assert 'function activateTab' not in scripts
    assert 'function poolRowMatchesState(row, state)' in scripts
    assert 'function poolStateFilterFromMode(mode)' in scripts
    assert "formData.set('confirm_switch', 'yes');" in scripts
    assert '{{' not in scripts


def test_web_form_template_smoke():
    page = web_form_template.render_web_form(
        APP_BRANCH_DESCRIPTION='test',
        APP_BRANCH_LABEL='codex/test',
        APP_VERSION_LABEL='1',
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
        event_history_html='',
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
        bot_ready=True,
        bot_polling=True,
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
    assert 'data-event-history-tab' not in page
    assert 'router-metrics-compact' in page
    assert 'data-router-metrics-refresh' in page
    assert 'router-metrics-history' not in page
    assert 'router-metrics-grid' not in page
    assert 'data-event-history-pane="events"' in page
    assert 'router-memory-text' in page
    assert 'router-memory-meter' in page
    assert 'call-learn-details' not in page
    assert 'telegram_call_learn' not in page
    assert 'status-attention-list' not in page
    assert 'topbar-status-icon-telegram' in page
    assert '"botReady":true' in page
    assert '"botPolling":true' in page
    assert 'status-overview-head' in page
    assert 'Панель состояния' not in page
    assert '10 / 64 MB' in page
    assert 'DNS: ndnproxy' in page
    assert 'value="update"' not in page
    assert 'Локальная панель управления обходом на роутере' in page
    assert 'Режим работы: интерфейс с пулом ключей и Telegram-бот' in page
    assert 'Связь, активный режим и сервисные действия собраны в одном месте.' not in page
    assert 'Выберите протокол, сохраните активный ключ или управляйте его пулом.' not in page
    assert 'Домены из выбранного списка будут отправляться через соответствующий протокол.' not in page
    assert 'Переустановка компонентов' not in page
    assert '{TELEGRAM_SVG_B64}' not in page
    assert 'window.BK_APP_CONFIG=' in page
    assert '"csrfToken":"token"' in page
    assert '"enableKeyPool":false' in page
    assert '"enableTelegram":true' in page
    assert '<script src="/static/app.js' in page
    assert 'command-running' not in page
    assert 'command-progress-track' not in page
    assert 'data-command-progress-fill' not in page
    process_without_polling_page = web_form_template.render_web_form(
        APP_BRANCH_DESCRIPTION='test',
        APP_BRANCH_LABEL='codex/test',
        APP_VERSION_LABEL='1',
        TELEGRAM_SVG_B64='tg-icon',
        YOUTUBE_SVG_B64='',
        _telegram_icon_html=lambda opacity=1.0: 'TG',
        csrf_token='token',
        command_block='',
        command_buttons_html='',
        app_runtime_mode_description='test',
        app_runtime_mode_label='test',
        app_runtime_mode_picker_block='',
        current_mode_label='test',
        custom_checks_json='[]',
        fallback_block='',
        event_history_html='',
        initial_command_running='false',
        initial_status_pending='false',
        list_route_label='list',
        message_block='',
        mode_picker_block='',
        mode_toggle_label='mode',
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
        start_button_label='start',
        status={'api_status': 'ok'},
        topbar_status_text='ok',
        unblock_panels_html='',
        unblock_tabs_html='',
        enable_key_pool=False,
        enable_custom_checks=False,
        bot_ready=True,
        bot_polling=False,
    )
    assert 'Telegram-бот работает' not in process_without_polling_page
    assert 'Статус обновляется' in process_without_polling_page
    assert 'Проверяется актуальное состояние' in process_without_polling_page
    assert 'Telegram API требует внимания' not in process_without_polling_page
    assert 'Программа подбирает рабочий ключ из пула текущего режима' not in process_without_polling_page
    assert 'Telegram API отвечает' not in process_without_polling_page
    assert 'topbar-status-icon-telegram' not in process_without_polling_page
    assert 'data-bot-ready="true"' in process_without_polling_page
    assert 'data-bot-polling="false"' in process_without_polling_page
    assert '"botReady":true' in process_without_polling_page
    assert '"botPolling":false' in process_without_polling_page
    pending_page = web_form_template.render_web_form(
        APP_BRANCH_DESCRIPTION='test',
        APP_BRANCH_LABEL='codex/test',
        APP_VERSION_LABEL='1',
        TELEGRAM_SVG_B64='tg-icon',
        YOUTUBE_SVG_B64='',
        _telegram_icon_html=lambda opacity=1.0: 'TG',
        csrf_token='token',
        command_block='',
        command_buttons_html='',
        app_runtime_mode_description='test',
        app_runtime_mode_label='test',
        app_runtime_mode_picker_block='',
        current_mode_label='test',
        custom_checks_json='[]',
        fallback_block='',
        event_history_html='',
        initial_command_running='false',
        initial_status_pending='false',
        list_route_label='list',
        message_block='',
        mode_picker_block='',
        mode_toggle_label='mode',
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
        start_button_label='start',
        status={'api_status': '⏳ Telegram API не ответил вовремя через текущий режим.'},
        topbar_status_text='⏳ Telegram API не ответил вовремя через текущий режим.',
        unblock_panels_html='',
        unblock_tabs_html='',
        enable_key_pool=False,
        enable_custom_checks=False,
        bot_ready=True,
        bot_polling=False,
    )
    assert 'Статус обновляется' in pending_page
    assert 'Проверяется актуальное состояние' in pending_page
    assert 'Telegram API требует внимания' not in pending_page
    assert 'Программа подбирает рабочий ключ из пула текущего режима' not in pending_page
    assert 'Telegram API отвечает' not in pending_page
    neutral_pending = web_form_template._topbar_status_item(
        {'api_status': '⏳ Telegram API не ответил вовремя через текущий режим. Программа подбирает рабочий ключ из пула текущего режима; статус обновится без перезагрузки страницы'},
        {'used_percent': 58},
        '',
        True,
        enable_telegram=True,
        bot_ready=True,
        bot_polling=False,
    )
    assert neutral_pending == ('info', 'Статус обновляется', 'Проверяется актуальное состояние')
    warning_failure = web_form_template._topbar_status_item(
        {'api_status': '❌ Доступ к Telegram API через режим vless не проходит: техническая ошибка записана в лог'},
        {'used_percent': 58},
        '',
        True,
        enable_telegram=True,
        bot_ready=True,
        bot_polling=True,
    )
    assert warning_failure[0] == 'warn'
    assert warning_failure[1] == 'Telegram API требует внимания'
    running_page = web_form_template.render_web_form(
        APP_BRANCH_DESCRIPTION='test',
        APP_BRANCH_LABEL='codex/test',
        APP_VERSION_LABEL='1',
        TELEGRAM_SVG_B64='tg-icon',
        YOUTUBE_SVG_B64='',
        _telegram_icon_html=lambda opacity=1.0: 'TG',
        csrf_token='token',
        command_block='<div id="web-command-status" class="notice notice-status"><strong>Команда выполняется</strong><pre class="log-output">running</pre></div>',
        command_buttons_html='',
        app_runtime_mode_description='test',
        app_runtime_mode_label='test',
        app_runtime_mode_picker_block='',
        current_mode_label='test',
        custom_checks_json='[]',
        fallback_block='',
        initial_command_running='true',
        initial_status_pending='false',
        list_route_label='list',
        message_block='',
        mode_picker_block='',
        mode_toggle_label='mode',
        pool_summary={'active_text': 'none'},
        pool_summary_note='',
        protocol_panels_html='',
        protocol_tabs_html='',
        quick_key_label='Vless 1',
        quick_key_proto='vless',
        quick_key_value='',
        quick_start_note='note',
        router_health={},
        socks_block='',
        start_button_label='',
        status={'api_status': 'ok'},
        topbar_status_text='ok',
        unblock_panels_html='',
        unblock_tabs_html='',
    )
    assert '<html lang="ru" class="command-running">' in running_page
    assert '<body class="command-running">' in running_page
    web_only_page = web_form_template.render_web_form(
        APP_BRANCH_DESCRIPTION='test',
        APP_BRANCH_LABEL='codex/test',
        APP_VERSION_LABEL='1',
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
    assert markup.rows[:3] == [
        ['Vless 1', 'Vless 2'],
        ['Vmess', 'Trojan'],
        ['Shadowsocks'],
    ]
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
    source = (APP_ROOT / 'bot.py').read_text(encoding='utf-8')
    assert 'key_name == _youtube_route_protocol()' in source
    assert "_youtube_probe_state(probe) in ('fail', 'unknown')" in source
    assert "def _schedule_youtube_cache_confirm" in source
    assert "def _schedule_vless2_youtube_cache_confirm" not in source
    assert "YOUTUBE_VLESS2_HEALTHCHECK_MIN_OK" in source
    assert "_youtube_healthcheck().check_youtube_through_proxy" in source
    assert "service='youtube'" in source
    assert 'Reality endpoint repair restored current' in source
    assert "_record_key_probe(proto, key_value, yt_ok=True, **yt_metrics)" in source
    assert "_invalidate_key_status_cache()" in source


def test_event_history_helpers():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'events.jsonl'
        assert event_history.record_event(
            action='route',
            message='installed vless://secret@example.test:443#name',
            protocol='vless',
            service='telegram',
            details={'last_activity_age_s': 0},
            event_path=str(path),
        )
        for index in range(60):
            assert event_history.record_event(
                action=f'event_{index}',
                message=f'message {index}',
                protocol='vless',
                event_path=str(path),
            )
        events = event_history.load_events(event_path=str(path))
        redacted_events = event_history.load_events(limit=100, event_path=str(path))
    assert len(events) == 50
    assert events[0]['action'] == 'event_59'
    assert events[-1]['action'] == 'event_10'
    assert redacted_events[-1]['protocol_label'] == 'Vless 1'
    assert '<proxy-key-hidden>' in redacted_events[-1]['message']
    assert 'vless://' not in redacted_events[-1]['message']
    assert redacted_events[-1]['details']['last_activity_age_s'] == '0'


def test_telegram_call_learning_event_history_redacts_ip_addresses():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'events.jsonl'
        assert event_history.record_event(
            action='telegram_call_learning_apply',
            message='added 149.154.167.91 from 192.168.1.23',
            protocol='vless',
            service='telegram',
            details={
                'address': '149.154.167.91',
                'clients': ['192.168.1.23'],
                'count': 1,
            },
            event_path=str(path),
        )
        with path.open('a', encoding='utf-8') as file:
            file.write(json.dumps({
                'ts': 2,
                'level': 'info',
                'action': 'telegram_call_learning_finish',
                'source': 'web',
                'protocol': 'vless',
                'service': 'telegram',
                'key_hash': '',
                'message': 'finished for 149.154.167.92 and 192.168.1.24',
                'details': {'device_ip': '192.168.1.24', 'address': '149.154.167.92'},
            }, ensure_ascii=False) + '\n')
        events = event_history.load_events(event_path=str(path))
    serialized = json.dumps(events, ensure_ascii=False)
    assert '149.154.167.91' not in serialized
    assert '149.154.167.92' not in serialized
    assert '192.168.1.23' not in serialized
    assert '192.168.1.24' not in serialized
    assert '<ip-hidden>' in serialized
    assert events[1]['details']['count'] == '1'


def test_stream_guard_event_history_redacts_ip_samples_and_compacts_details():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'events.jsonl'
        assert event_history.record_event(
            action='stream_guard_defer',
            message='active flow 192.168.1.23 -> 142.250.74.110',
            details={
                'reason': 'active_stream',
                'route_diagnostic': {
                    'proxy_ports': [10812, 11812],
                    'proxy_samples': ['192.168.1.23:51000 -> 142.250.74.110:443'],
                    'fastnat_samples': ['142.250.74.110:443'],
                },
                'sample': '192.168.1.23 -> 142.250.74.110',
            },
            event_path=str(path),
        )
        with path.open('a', encoding='utf-8') as file:
            file.write(json.dumps({
                'ts': 2,
                'level': 'info',
                'action': 'stream_guard_defer',
                'source': 'watchdog',
                'protocol': 'vless',
                'service': 'youtube',
                'message': 'legacy 192.168.1.23 -> 142.250.74.110',
                'details': {
                    'route_diagnostic': "{'proxy_ports': ['10811'], 'proxy_samples': [{'src': '192.168.1.23', 'dst': '142.250.74.110'}]}",
                },
            }, ensure_ascii=False) + '\n')
        events = event_history.load_events(event_path=str(path))
    serialized = json.dumps(events, ensure_ascii=False)
    assert '192.168.1.23' not in serialized
    assert '142.250.74.110' not in serialized
    assert '<ip-hidden>' in serialized
    assert events[1]['details']['route_diagnostic'] == 'proxy_ports=2; proxy_samples=1; fastnat_samples=1'
    assert events[0]['details']['route_diagnostic'].startswith('route_diagnostic compacted;')


def test_update_status_helpers():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'update.json'
        status = update_status.write_update_status(
            command='update',
            running=True,
            progress=42,
            progress_label='Downloading',
            message='step',
            target_version='v1.956',
            path=str(path),
        )
        assert status['running'] is True
        assert update_status.read_update_status(str(path))['progress'] == 42
        assert update_status.read_update_status(str(path))['target_version'] == 'v1.956'
        assert update_status.write_update_status(
            command='update', running=True, progress=50, path=str(path)
        )['target_version'] == 'v1.956'
        assert update_status.write_update_status(
            command='update', running=True, progress=50, target_version='unsafe version!', path=str(path)
        )['target_version'] == ''
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
            service_items=[{'id': 'youtube'}, {'id': 'telegram'}, {'id': 'chrome_remote_desktop'}],
            unblock_dir=tmp,
            update_script='',
            before_update=lambda: callbacks.append('profile'),
        )
        assert profile['services'] == 2
        assert callbacks == ['route', 'profile']
        assert service_catalog.YOUTUBE_UNBLOCK_ENTRIES[0] in (Path(tmp) / 'vless-2.txt').read_text(encoding='utf-8')
        assert service_catalog.TELEGRAM_UNBLOCK_ENTRIES[0] in (Path(tmp) / 'vless.txt').read_text(encoding='utf-8')
        vless_after_profile = set((Path(tmp) / 'vless.txt').read_text(encoding='utf-8').splitlines())
        vless2_after_profile = set((Path(tmp) / 'vless-2.txt').read_text(encoding='utf-8').splitlines())
        assert set(service_catalog.service_route_entries('telegram')) <= vless_after_profile
        assert set(service_catalog.service_route_entries('youtube')) <= vless2_after_profile
        assert service_routes.service_route_state('youtube', unblock_dir=tmp)['label'] == 'Vless 2'
        assert not (set(service_catalog.SERVICE_LIST_SOURCES['telegram'].get('route_state_exclude') or []) & vless_after_profile)
        assert not (set(service_catalog.CHROME_REMOTE_DESKTOP_CORE_ROUTE_ENTRIES) & vless_after_profile)
        same_route_dir = Path(tmp) / 'same-route'
        same_route_dir.mkdir()
        for route_file in ('vless.txt', 'vless-2.txt', 'vmess.txt', 'trojan.txt', 'shadowsocks.txt'):
            (same_route_dir / route_file).write_text('', encoding='utf-8')
        youtube_same = service_routes.apply_service_route('youtube', 'vmess', unblock_dir=str(same_route_dir), update_script='')
        telegram_same = service_routes.apply_service_route('telegram', 'vmess', unblock_dir=str(same_route_dir), update_script='')
        vmess_text = (same_route_dir / 'vmess.txt').read_text(encoding='utf-8')
        vless_text = (same_route_dir / 'vless.txt').read_text(encoding='utf-8')
        assert youtube_same['target_protocol'] == 'vmess'
        assert telegram_same['target_protocol'] == 'vmess'
        assert service_catalog.YOUTUBE_UNBLOCK_ENTRIES[0] in vmess_text
        assert service_catalog.TELEGRAM_UNBLOCK_ENTRIES[0] in vmess_text
        assert service_catalog.YOUTUBE_UNBLOCK_ENTRIES[0] not in vless_text
        assert service_catalog.TELEGRAM_UNBLOCK_ENTRIES[0] not in vless_text
        drift_dir = Path(tmp) / 'drift'
        drift_dir.mkdir()
        old_youtube = service_catalog.YOUTUBE_UNBLOCK_ENTRIES[:-4]
        for route_file in ('vless.txt', 'vmess.txt', 'trojan.txt', 'shadowsocks.txt'):
            (drift_dir / route_file).write_text('', encoding='utf-8')
        (drift_dir / 'vless-2.txt').write_text('\n'.join(old_youtube) + '\n', encoding='utf-8')
        (drift_dir / 'vless.txt').write_text(
            service_catalog.YOUTUBE_UNBLOCK_ENTRIES[-1] + '\nclients3.google.com\n',
            encoding='utf-8',
        )
        before = service_routes.service_route_state('youtube', unblock_dir=str(drift_dir))
        assert before['complete_protocols'] == []
        assert set(before['partial_protocols']) == {'vless', 'vless2'}
        repaired = service_routes.repair_service_route_catalog_drift(
            service_items=[{'id': 'youtube'}, {'id': 'telegram'}],
            unblock_dir=str(drift_dir),
            update_script='',
        )
        assert repaired['services'] == 1
        assert repaired['entries_added'] == 7
        assert repaired['global_entries_removed'] == 4
        assert repaired['entries_removed'] == 5
        after = service_routes.service_route_state('youtube', unblock_dir=str(drift_dir))
        assert after['label'] == 'Vless 2'
        repaired_text = '\n'.join(
            (drift_dir / route_file).read_text(encoding='utf-8')
            for route_file in ('vless.txt', 'vless-2.txt')
        )
        assert set(service_catalog.global_route_exclude_entries()) & set(repaired_text.splitlines()) <= set(
            service_catalog.SERVICE_LIST_SOURCES['youtube'].get('route_global_exclude_allow') or []
        )
        assert route_intersections.analyze_route_intersections(
            unblock_dir=str(drift_dir),
            include_runtime=False,
        )['count'] == 0


def test_route_intersections_helpers():
    with tempfile.TemporaryDirectory() as tmp:
        callbacks = []
        (Path(tmp) / 'vless.txt').write_text('discord.com\nexample.com\n198.51.100.0/24\n', encoding='utf-8')
        (Path(tmp) / 'vless-2.txt').write_text('discord.com\napi.example.com\n198.51.100.10\n', encoding='utf-8')
        report = route_intersections.analyze_route_intersections(unblock_dir=tmp)
        assert report['count'] >= 2
        discord_issue = next(issue for issue in report['issues'] if 'discord.com' in issue.get('entries', []))
        assert 'Discord' in discord_issue['services']
        assert discord_issue['service_keys'] == ['discord']
        assert discord_issue['service_hint'] == 'Discord'
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


def test_route_intersections_filters_comments_and_ip_domain_noise():
    with tempfile.TemporaryDirectory() as tmp:
        for route_file in ('vmess.txt', 'trojan.txt', 'shadowsocks.txt'):
            (Path(tmp) / route_file).write_text('', encoding='utf-8')
        shared_comment = '# synced from router'
        (Path(tmp) / 'vless.txt').write_text(
            f'{shared_comment}\n198.51.100.10\nexample.com\n203.0.113.5\n',
            encoding='utf-8',
        )
        (Path(tmp) / 'vless-2.txt').write_text(
            f'{shared_comment}\n198.51.100.10\napi.example.com\n203.0.113.0/24\n',
            encoding='utf-8',
        )

        report = route_intersections.analyze_route_intersections(
            unblock_dir=tmp,
            include_runtime=False,
        )
        kinds = [issue['kind'] for issue in report['issues']]
        assert kinds.count('exact') == 1
        assert kinds.count('domain_suffix') == 1
        assert kinds.count('ip_overlap') == 1
        assert all(not str(issue.get('entry', '')).startswith('#') for issue in report['issues'])
        assert all('198.51.100.10 / 198.51.100.10' not in str(issue.get('message', '')) for issue in report['issues'])


def test_service_route_repair_preserves_shared_entries():
    shared_entry = 'accounts.google.com'
    assert shared_entry in service_catalog.shared_service_route_entries()
    with tempfile.TemporaryDirectory() as tmp:
        for route_file in ('vless.txt', 'vless-2.txt', 'vmess.txt', 'trojan.txt', 'shadowsocks.txt'):
            (Path(tmp) / route_file).write_text('', encoding='utf-8')
        youtube_entries = service_catalog.service_route_entries('youtube')
        chatgpt_entries = service_catalog.service_route_entries('chatgpt_services')
        (Path(tmp) / 'vless-2.txt').write_text(
            '\n'.join(entry for entry in youtube_entries if entry != shared_entry) + '\n',
            encoding='utf-8',
        )
        (Path(tmp) / 'vless.txt').write_text('\n'.join(chatgpt_entries) + '\n', encoding='utf-8')

        before = service_routes.service_route_state('youtube', unblock_dir=str(tmp))
        assert before['complete_protocols'] == []
        assert 'vless2' in before['partial_protocols']
        repaired = service_routes.repair_service_route_catalog_drift(unblock_dir=str(tmp), update_script='')
        assert repaired['services'] >= 1

        vless_entries = set((Path(tmp) / 'vless.txt').read_text(encoding='utf-8').splitlines())
        vless2_entries = set((Path(tmp) / 'vless-2.txt').read_text(encoding='utf-8').splitlines())
        assert shared_entry in vless_entries
        assert shared_entry in vless2_entries
        assert service_routes.service_route_state('youtube', unblock_dir=str(tmp))['label'] == 'Vless 2'
        assert service_routes.service_route_state('chatgpt_services', unblock_dir=str(tmp))['label'] == 'Vless 1'
        assert route_intersections.analyze_route_intersections(
            unblock_dir=str(tmp),
            include_runtime=False,
        )['count'] == 0


def test_service_route_auto_resolves_known_service_intersections():
    with tempfile.TemporaryDirectory() as tmp:
        callbacks = []
        for route_file in ('vless.txt', 'vmess.txt', 'trojan.txt', 'shadowsocks.txt'):
            (Path(tmp) / route_file).write_text('', encoding='utf-8')
        youtube_entries = service_catalog.service_route_entries('youtube')
        (Path(tmp) / 'vless-2.txt').write_text('\n'.join(youtube_entries) + '\n', encoding='utf-8')
        (Path(tmp) / 'vless.txt').write_text(youtube_entries[0] + '\n', encoding='utf-8')

        report = route_intersections.analyze_route_intersections(
            unblock_dir=tmp,
            include_runtime=False,
        )
        assert report['file_count'] >= 1
        assert any(issue.get('service_keys') == ['youtube'] for issue in report['issues'])

        result = service_routes.auto_resolve_service_route_intersections(
            report=report,
            service_items=[{'id': 'youtube'}],
            unblock_dir=tmp,
            update_script='',
            before_update=lambda: callbacks.append('update'),
        )

        assert result['services'] == 1
        assert result['entries_removed'] >= 1
        assert callbacks == ['update']
        assert youtube_entries[0] not in (Path(tmp) / 'vless.txt').read_text(encoding='utf-8')
        assert set(youtube_entries) <= set((Path(tmp) / 'vless-2.txt').read_text(encoding='utf-8').splitlines())
        assert route_intersections.analyze_route_intersections(
            unblock_dir=tmp,
            include_runtime=False,
        )['count'] == 0


def test_service_route_auto_resolves_partial_service_target():
    with tempfile.TemporaryDirectory() as tmp:
        for route_file in ('vless.txt', 'vmess.txt', 'trojan.txt', 'shadowsocks.txt'):
            (Path(tmp) / route_file).write_text('', encoding='utf-8')
        youtube_entries = service_catalog.service_route_entries('youtube')
        (Path(tmp) / 'vless-2.txt').write_text(
            '\n'.join(youtube_entries[:2]) + '\n',
            encoding='utf-8',
        )
        (Path(tmp) / 'vless.txt').write_text(youtube_entries[0] + '\n', encoding='utf-8')

        report = route_intersections.analyze_route_intersections(
            unblock_dir=tmp,
            include_runtime=False,
        )
        result = service_routes.auto_resolve_service_route_intersections(
            report=report,
            service_items=[{'id': 'youtube'}],
            unblock_dir=tmp,
            update_script='',
        )

        assert result['services'] == 1
        assert result['applied'][0]['target_protocol'] == 'vless2'
        assert youtube_entries[0] not in (Path(tmp) / 'vless.txt').read_text(encoding='utf-8')
        assert set(youtube_entries) <= set((Path(tmp) / 'vless-2.txt').read_text(encoding='utf-8').splitlines())


def test_service_route_auto_refreshes_runtime_only_known_intersections():
    with tempfile.TemporaryDirectory() as tmp:
        callbacks = []
        deleted = []
        for route_file in ('vless.txt', 'vmess.txt', 'trojan.txt', 'shadowsocks.txt'):
            (Path(tmp) / route_file).write_text('', encoding='utf-8')
        youtube_entries = service_catalog.service_route_entries('youtube')
        (Path(tmp) / 'vless-2.txt').write_text('\n'.join(youtube_entries) + '\n', encoding='utf-8')
        ipsets = {
            'unblockvless': ['64.233.161.94'],
            'unblockvless2': ['64.233.161.0/24'],
        }

        def fake_run(args, stdout=None, stderr=None, text=None, timeout=None, check=None):
            if args[:2] == ['ipset', 'list']:
                set_name = args[-1]
                members = ipsets.get(set_name, [])
                output = 'Name: {0}\nMembers:\n{1}\n'.format(set_name, '\n'.join(members))
                return py_types.SimpleNamespace(stdout=output, returncode=0)
            if args[:2] == ['ipset', 'del']:
                _, _, set_name, member = args
                deleted.append((set_name, member))
                if member in ipsets.get(set_name, []):
                    ipsets[set_name].remove(member)
                    return py_types.SimpleNamespace(stdout='', returncode=0)
                return py_types.SimpleNamespace(stdout='', returncode=1)
            return py_types.SimpleNamespace(stdout='', returncode=0)

        report = {
            'count': 1,
            'file_count': 0,
            'runtime_count': 1,
            'issues': [{
                'kind': 'runtime_ipset_overlap',
                'routes': ['vless', 'vless-2'],
                'set_names': ['unblockvless', 'unblockvless2'],
                'samples': ['64.233.161.94 / 64.233.161.0/24'],
                'services': ['YouTube'],
                'service_keys': ['youtube'],
                'service_matches': [{'key': 'youtube', 'label': 'YouTube'}],
                'message': 'runtime overlap',
            }],
        }

        result = service_routes.auto_resolve_service_route_intersections(
            report=report,
            service_items=[{'id': 'youtube'}],
            unblock_dir=tmp,
            update_script='',
            before_update=lambda: callbacks.append('refresh'),
            run_command=fake_run,
        )

        assert result['services'] == 1
        assert result['entries_added'] >= 0
        assert result['entries_removed'] == 1
        assert result['runtime_cleanup']['deleted_members'] == 1
        assert deleted == [('unblockvless', '64.233.161.94')]
        assert callbacks == []


def test_service_route_runtime_cleanup_uses_service_owner_for_catalog_services():
    with tempfile.TemporaryDirectory() as tmp:
        deleted = []
        for route_file in ('vless.txt', 'vmess.txt', 'trojan.txt', 'shadowsocks.txt'):
            (Path(tmp) / route_file).write_text('', encoding='utf-8')
        discord_entries = service_catalog.service_route_entries('discord')
        (Path(tmp) / 'vless-2.txt').write_text('\n'.join(discord_entries) + '\n', encoding='utf-8')
        ipsets = {
            'unblockvless': ['203.0.113.10', '198.51.100.1'],
            'unblockvless2': ['203.0.113.0/24'],
        }

        def fake_run(args, stdout=None, stderr=None, text=None, timeout=None, check=None):
            if args[:2] == ['ipset', 'list']:
                set_name = args[-1]
                members = ipsets.get(set_name, [])
                output = 'Name: {0}\nMembers:\n{1}\n'.format(set_name, '\n'.join(members))
                return py_types.SimpleNamespace(stdout=output, returncode=0)
            if args[:2] == ['ipset', 'del']:
                _, _, set_name, member = args
                deleted.append((set_name, member))
                if member in ipsets.get(set_name, []):
                    ipsets[set_name].remove(member)
                    return py_types.SimpleNamespace(stdout='', returncode=0)
                return py_types.SimpleNamespace(stdout='', returncode=1)
            return py_types.SimpleNamespace(stdout='', returncode=0)

        result = service_routes.cleanup_runtime_service_route_intersections(
            report={
                'count': 1,
                'file_count': 0,
                'runtime_count': 1,
                'issues': [{
                    'kind': 'runtime_ipset_overlap',
                    'routes': ['vless', 'vless-2'],
                    'set_names': ['unblockvless', 'unblockvless2'],
                    'samples': ['203.0.113.10 / 203.0.113.0/24'],
                    'services': ['Discord'],
                    'service_keys': ['discord'],
                    'service_matches': [{'key': 'discord', 'label': 'Discord'}],
                    'message': 'runtime overlap',
                }],
            },
            service_items=[{'id': 'discord'}],
            unblock_dir=tmp,
            run_command=fake_run,
        )

        assert result['services'] == 1
        assert result['service_keys'] == ['discord']
        assert result['pairs'] == 1
        assert result['deleted_members'] == 1
        assert deleted == [('unblockvless', '203.0.113.10')]
        assert ipsets['unblockvless'] == ['198.51.100.1']


def test_service_route_runtime_cleanup_splits_mixed_service_targets():
    with tempfile.TemporaryDirectory() as tmp:
        deleted = []
        for route_file in ('vmess.txt', 'trojan.txt', 'shadowsocks.txt'):
            (Path(tmp) / route_file).write_text('', encoding='utf-8')
        telegram_entries = service_catalog.service_route_entries('telegram')
        youtube_entries = service_catalog.service_route_entries('youtube')
        (Path(tmp) / 'vless.txt').write_text('\n'.join(telegram_entries) + '\n', encoding='utf-8')
        (Path(tmp) / 'vless-2.txt').write_text('\n'.join(youtube_entries) + '\n', encoding='utf-8')
        ipsets = {
            'unblockvless': ['64.233.161.97', '104.21.0.0/16'],
            'unblockvless2': ['64.233.161.0/24', '104.21.72.109'],
        }

        def fake_run(args, stdout=None, stderr=None, text=None, timeout=None, check=None):
            if args[:2] == ['ipset', 'list']:
                set_name = args[-1]
                members = ipsets.get(set_name, [])
                output = 'Name: {0}\nMembers:\n{1}\n'.format(set_name, '\n'.join(members))
                return py_types.SimpleNamespace(stdout=output, returncode=0)
            if args[:2] == ['ipset', 'del']:
                _, _, set_name, member = args
                deleted.append((set_name, member))
                if member in ipsets.get(set_name, []):
                    ipsets[set_name].remove(member)
                    return py_types.SimpleNamespace(stdout='', returncode=0)
                return py_types.SimpleNamespace(stdout='', returncode=1)
            return py_types.SimpleNamespace(stdout='', returncode=0)

        result = service_routes.cleanup_runtime_service_route_intersections(
            report={
                'count': 1,
                'file_count': 0,
                'runtime_count': 1,
                'issues': [{
                    'kind': 'runtime_ipset_overlap',
                    'routes': ['vless', 'vless-2'],
                    'set_names': ['unblockvless', 'unblockvless2'],
                        'samples': [
                            '64.233.161.97 / 64.233.161.0/24',
                            '104.21.0.0/16 / 104.21.72.109',
                        ],
                    'services': ['YouTube', 'Telegram'],
                    'service_keys': ['youtube', 'telegram'],
                    'message': 'mixed runtime overlap',
                }],
            },
            service_items=[{'id': 'youtube'}, {'id': 'telegram'}],
            unblock_dir=tmp,
            run_command=fake_run,
        )

        assert result['services'] == 2
        assert result['service_keys'] == ['telegram', 'youtube']
        assert result['pairs'] == 2
        assert result['deleted_members'] == 2
        assert deleted == [
            ('unblockvless', '64.233.161.97'),
            ('unblockvless2', '104.21.72.109'),
        ]
        assert ipsets['unblockvless'] == ['104.21.0.0/16']
        assert ipsets['unblockvless2'] == ['64.233.161.0/24']


def test_route_intersections_detect_runtime_ipset_overlap():
    with tempfile.TemporaryDirectory() as tmp:
        for route_file, content in (
            ('vless.txt', 'telegram.org\n'),
            ('vless-2.txt', 'youtube.com\n'),
            ('vmess.txt', ''),
            ('trojan.txt', ''),
            ('shadowsocks.txt', ''),
        ):
            (Path(tmp) / route_file).write_text(content, encoding='utf-8')

        ipsets = {
            'unblockvless': ['1.1.1.1', '8.8.8.8', '142.251.156.119'],
            'unblockvlessudp': ['8.8.4.4', '64.233.163.119'],
            'unblockvless2': ['8.8.8.8', '9.9.9.9', '142.251.156.0/24'],
            'unblockvless2udp': ['8.8.4.4', '9.9.9.9', '64.233.163.0/24'],
        }
        ipset_calls = []

        def fake_run(args, stdout=None, stderr=None, text=None, timeout=None, check=None):
            ipset_calls.append(tuple(args))
            if args == ['ipset', 'save']:
                output = []
                for set_name, members in ipsets.items():
                    output.append(f'create {set_name} hash:net')
                    output.extend(f'add {set_name} {member}' for member in members)
                return py_types.SimpleNamespace(stdout='\n'.join(output), returncode=0)
            set_name = args[-1]
            members = ipsets.get(set_name, [])
            output = 'Name: {0}\nMembers:\n{1}\n'.format(set_name, '\n'.join(members))
            return py_types.SimpleNamespace(stdout=output, returncode=0)

        report = route_intersections.analyze_route_intersections(
            unblock_dir=tmp,
            run_command=fake_run,
        )
        assert report['file_count'] == 0
        assert report['runtime_count'] == 2
        assert report['runtime_match_count'] == 4
        assert ipset_calls.count(('ipset', 'save')) == 1
        assert not any(call[:2] == ('ipset', 'list') for call in ipset_calls)
        assert {issue['kind'] for issue in report['issues']} == {'runtime_ipset_overlap'}
        assert any('142.251.156.119 / 142.251.156.0/24' in issue.get('samples', []) for issue in report['issues'])
        assert any('youtube' in issue.get('service_keys', []) for issue in report['issues'])

        result = route_intersections.resolve_route_intersections(
            'vless-2',
            unblock_dir=tmp,
            update_script='',
        )
        assert result['moved'] == 0


def test_route_intersections_ignores_priority_runtime_overlap():
    with tempfile.TemporaryDirectory() as tmp:
        for route_file, content in (
            ('vless.txt', 'mtalk.google.com\n'),
            ('vless-2.txt', 'youtube.com\n'),
            ('vmess.txt', ''),
            ('trojan.txt', ''),
            ('shadowsocks.txt', ''),
        ):
            (Path(tmp) / route_file).write_text(content, encoding='utf-8')

        ipsets = {
            'unblockvless': ['64.233.162.100', '64.233.162.101'],
            'unblockvlesspriority': ['64.233.162.100'],
            'unblockvless2': ['64.233.162.0/24'],
        }

        def fake_run(args, stdout=None, stderr=None, text=None, timeout=None, check=None):
            set_name = args[-1]
            members = ipsets.get(set_name, [])
            output = 'Name: {0}\nMembers:\n{1}\n'.format(set_name, '\n'.join(members))
            return py_types.SimpleNamespace(stdout=output, returncode=0)

        report = route_intersections.analyze_route_intersections(
            unblock_dir=tmp,
            run_command=fake_run,
        )
        assert report['file_count'] == 0
        assert report['runtime_count'] == 1
        assert report['runtime_match_count'] == 1
        assert report['issues'][0]['samples'] == ['64.233.162.101 / 64.233.162.0/24']


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
    assert 'В одной карточке видно, через какой список идёт сервис, и добавлена ли его проверка в пул.</small>' not in html_text
    assert 'service-route-trigger' in html_text
    assert 'service-route-menu-item active' in html_text
    assert 'service-route-telegram-icon' in html_text
    assert 'service-route-youtube-icon' in html_text
    assert 'service-route-choice' not in html_text
    assert '/custom_check_delete' in html_text
    assert '<select' not in html_text
    assert 'Перенести</button>' not in html_text
    intersections_html = key_pool_web.web_route_intersections_html({'count': 0}, service_routes.protocol_options())
    assert intersections_html
    assert 'IP-сетей.</small>' not in intersections_html
    intersections_warn_html = key_pool_web.web_route_intersections_html(
        {
            'count': 1,
            'file_count': 1,
            'issues': [{
                'message': 'discord.com: duplicate',
                'routes': ['vless', 'vless-2'],
                'services': ['Discord'],
                'entries': ['discord.com'],
            }],
        },
        service_routes.protocol_options(),
    )
    assert 'Discord' in intersections_warn_html
    assert 'discord.com' in intersections_warn_html
    assert '/route_intersections_resolve' in intersections_warn_html
    runtime_pending_html = key_pool_web.web_route_intersections_html(
        {
            'count': 1,
            'file_count': 0,
            'runtime_count': 1,
            'auto_resolve_pending': {'status': 'running', 'external': True},
            'issues': [{
                'message': 'runtime overlap',
                'routes': ['vless', 'vless-2'],
                'services': ['YouTube'],
                'samples': ['64.233.161.94 / 64.233.161.0/24'],
            }],
        },
        service_routes.protocol_options(),
    )
    assert 'ipset' in runtime_pending_html
    assert '64.233.161.94' not in runtime_pending_html
    assert '/route_intersections_resolve' not in runtime_pending_html
    profiles_html = key_pool_web.web_route_profiles_html([{'id': 'all', 'label': 'Все сервисы', 'description': 'desc'}])
    assert 'из каталога.</small>' not in profiles_html
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
        auto_resolve_lock_path='',
    )
    items = runtime.service_items()
    item_ids = {item['id'] for item in items}
    assert {'telegram', 'youtube', 'chatgpt_services'} <= item_ids
    mutable_presets = [
        dict(item)
        for item in service_catalog.CUSTOM_CHECK_PRESETS
        if item.get('id') != 'chatgpt_services'
    ]
    mutable_runtime = web_route_tools_runtime.ServiceRouteToolsRuntime(
        custom_check_presets_getter=lambda: mutable_presets,
        service_icon_html=lambda icon, label, opacity=1.0, size=18: f'<span>{label}</span>',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        auto_resolve_lock_path='',
    )
    assert 'chatgpt_services' not in {item['id'] for item in mutable_runtime.service_items()}
    chatgpt_preset = next(item for item in service_catalog.CUSTOM_CHECK_PRESETS if item.get('id') == 'chatgpt_services')
    mutable_presets.append(dict(chatgpt_preset))
    assert 'chatgpt_services' in {item['id'] for item in mutable_runtime.service_items()}
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


def test_service_route_runtime_intersections_cache_uses_signatures():
    original_route_signature = web_route_tools_runtime.route_intersections.route_files_signature
    original_runtime_signature = web_route_tools_runtime.route_intersections.runtime_ipset_signature
    original_analyze = web_route_tools_runtime.route_intersections.analyze_route_intersections
    route_signature = [('vless', 1, 10)]
    runtime_signature = ('status', 1, 10)
    now = [1000.0]
    calls = []

    try:
        web_route_tools_runtime.route_intersections.route_files_signature = lambda: tuple(route_signature)
        web_route_tools_runtime.route_intersections.runtime_ipset_signature = lambda: runtime_signature

        def fake_analyze():
            calls.append((tuple(route_signature), runtime_signature))
            return {'count': len(calls), 'issues': [], 'file_count': 0, 'runtime_count': 0}

        web_route_tools_runtime.route_intersections.analyze_route_intersections = fake_analyze
        runtime = web_route_tools_runtime.ServiceRouteToolsRuntime(
            custom_check_presets_getter=lambda: service_catalog.CUSTOM_CHECK_PRESETS,
            service_icon_html=lambda icon, label, opacity=1.0, size=18: f'<span>{label}</span>',
            telegram_icon_html=lambda opacity=1.0: 'TG',
            youtube_icon_html=lambda opacity=1.0: 'YT',
            intersections_cache_ttl=1,
            auto_resolve_lock_path='',
            time_provider=lambda: now[0],
        )
        assert runtime.intersections_snapshot()['count'] == 1
        assert runtime.intersections_snapshot()['count'] == 1
        assert len(calls) == 1
        runtime_signature = ('status', 2, 20)
        assert runtime.intersections_snapshot()['count'] == 2
        assert len(calls) == 2
        now[0] += 1.05
        assert runtime.intersections_snapshot()['count'] == 3
        assert len(calls) == 3
    finally:
        web_route_tools_runtime.route_intersections.route_files_signature = original_route_signature
        web_route_tools_runtime.route_intersections.runtime_ipset_signature = original_runtime_signature
        web_route_tools_runtime.route_intersections.analyze_route_intersections = original_analyze


def test_service_route_runtime_auto_resolves_known_intersections():
    original_route_signature = web_route_tools_runtime.route_intersections.route_files_signature
    original_runtime_signature = web_route_tools_runtime.route_intersections.runtime_ipset_signature
    original_analyze = web_route_tools_runtime.route_intersections.analyze_route_intersections
    original_auto_resolve = web_route_tools_runtime.service_routes.auto_resolve_service_route_intersections
    route_signature = [('vless', 1, 10)]
    runtime_signature = ('status', 1, 10)
    analyze_calls = []
    auto_calls = []
    invalidations = []

    class ImmediateThread:
        def __init__(self, target, args=(), daemon=None):
            self.target = target
            self.args = args
            self.daemon = daemon
            self._alive = False

        def start(self):
            self._alive = True
            try:
                self.target(*self.args)
            finally:
                self._alive = False

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return self._alive

    try:
        web_route_tools_runtime.route_intersections.route_files_signature = lambda: tuple(route_signature)
        web_route_tools_runtime.route_intersections.runtime_ipset_signature = lambda: runtime_signature

        def fake_analyze():
            analyze_calls.append('analyze')
            if len(analyze_calls) == 1:
                return {
                    'count': 1,
                    'file_count': 0,
                    'runtime_count': 1,
                    'issues': [{
                        'kind': 'runtime_ipset_overlap',
                        'routes': ['vless', 'vless-2'],
                        'samples': ['64.233.161.94 / 64.233.161.0/24'],
                        'services': ['YouTube'],
                        'service_keys': ['youtube'],
                        'message': 'runtime overlap',
                    }],
                }
            return {'count': 0, 'issues': [], 'file_count': 0, 'runtime_count': 0}

        def fake_auto_resolve(**kwargs):
            auto_calls.append(kwargs)
            return {
                'services': 1,
                'status': 'finished',
                'applied': [{
                    'service_key': 'youtube',
                    'service_label': 'YouTube',
                    'target_protocol': 'vless2',
                    'target_label': 'Vless 2',
                    'added': 0,
                    'removed': 0,
                }],
            }

        web_route_tools_runtime.route_intersections.analyze_route_intersections = fake_analyze
        web_route_tools_runtime.service_routes.auto_resolve_service_route_intersections = fake_auto_resolve
        with tempfile.TemporaryDirectory() as tmp:
            runtime = web_route_tools_runtime.ServiceRouteToolsRuntime(
                custom_check_presets_getter=lambda: service_catalog.CUSTOM_CHECK_PRESETS,
                service_icon_html=lambda icon, label, opacity=1.0, size=18: f'<span>{label}</span>',
                telegram_icon_html=lambda opacity=1.0: 'TG',
                youtube_icon_html=lambda opacity=1.0: 'YT',
                invalidate_web_status_cache=lambda: invalidations.append('status'),
                intersections_cache_ttl=1,
                auto_resolve_lock_path=str(Path(tmp) / 'auto-resolve.lock'),
                thread_factory=ImmediateThread,
            )
            report = runtime.intersections_snapshot()
            assert report['count'] == 1
            assert report['auto_resolve_pending']['status'] == 'scheduled'
            assert len(auto_calls) == 1
            assert not runtime._auto_resolve_worker.is_alive()
            assert invalidations == ['status']
            assert runtime.intersections_snapshot()['count'] == 0
            assert len(auto_calls) == 1
    finally:
        web_route_tools_runtime.route_intersections.route_files_signature = original_route_signature
        web_route_tools_runtime.route_intersections.runtime_ipset_signature = original_runtime_signature
        web_route_tools_runtime.route_intersections.analyze_route_intersections = original_analyze
        web_route_tools_runtime.service_routes.auto_resolve_service_route_intersections = original_auto_resolve


def test_service_route_runtime_pending_auto_resolve_is_cached():
    original_route_signature = web_route_tools_runtime.route_intersections.route_files_signature
    original_runtime_signature = web_route_tools_runtime.route_intersections.runtime_ipset_signature
    original_analyze = web_route_tools_runtime.route_intersections.analyze_route_intersections
    route_signature = [('vless', 1, 10)]
    runtime_signature = ('status', 1, 10)
    analyze_calls = []

    class DeferredThread:
        def __init__(self, target, args=(), daemon=None):
            self.target = target
            self.args = args
            self.daemon = daemon
            self._alive = False

        def start(self):
            self._alive = True

        def is_alive(self):
            return self._alive

    try:
        web_route_tools_runtime.route_intersections.route_files_signature = lambda: tuple(route_signature)
        web_route_tools_runtime.route_intersections.runtime_ipset_signature = lambda: runtime_signature

        def fake_analyze():
            analyze_calls.append('analyze')
            return {
                'count': 1,
                'file_count': 0,
                'runtime_count': 1,
                'issues': [{
                    'kind': 'runtime_ipset_overlap',
                    'routes': ['vless', 'vless-2'],
                    'samples': ['64.233.161.94 / 64.233.161.0/24'],
                    'services': ['YouTube'],
                    'service_keys': ['youtube'],
                    'message': 'runtime overlap',
                }],
            }

        web_route_tools_runtime.route_intersections.analyze_route_intersections = fake_analyze
        with tempfile.TemporaryDirectory() as tmp:
            runtime = web_route_tools_runtime.ServiceRouteToolsRuntime(
                custom_check_presets_getter=lambda: service_catalog.CUSTOM_CHECK_PRESETS,
                service_icon_html=lambda icon, label, opacity=1.0, size=18: f'<span>{label}</span>',
                telegram_icon_html=lambda opacity=1.0: 'TG',
                youtube_icon_html=lambda opacity=1.0: 'YT',
                intersections_cache_ttl=60,
                auto_resolve_lock_path=str(Path(tmp) / 'auto-resolve.lock'),
                thread_factory=DeferredThread,
            )
            first = runtime.intersections_snapshot()
            second = runtime.intersections_snapshot()
            assert first['auto_resolve_pending']['status'] == 'scheduled'
            assert second['auto_resolve_pending']['status'] == 'scheduled'
            assert len(analyze_calls) == 1
    finally:
        web_route_tools_runtime.route_intersections.route_files_signature = original_route_signature
        web_route_tools_runtime.route_intersections.runtime_ipset_signature = original_runtime_signature
        web_route_tools_runtime.route_intersections.analyze_route_intersections = original_analyze


def test_service_route_runtime_auto_resolve_uses_cross_runtime_lock():
    original_route_signature = web_route_tools_runtime.route_intersections.route_files_signature
    original_runtime_signature = web_route_tools_runtime.route_intersections.runtime_ipset_signature
    original_analyze = web_route_tools_runtime.route_intersections.analyze_route_intersections
    original_auto_resolve = web_route_tools_runtime.service_routes.auto_resolve_service_route_intersections
    route_signature = [('vless', 1, 10)]
    runtime_signature = ('status', 1, 10)
    auto_calls = []

    try:
        web_route_tools_runtime.route_intersections.route_files_signature = lambda: tuple(route_signature)
        web_route_tools_runtime.route_intersections.runtime_ipset_signature = lambda: runtime_signature

        def fake_analyze():
            return {
                'count': 1,
                'file_count': 0,
                'runtime_count': 1,
                'issues': [{
                    'kind': 'runtime_ipset_overlap',
                    'routes': ['vless', 'vless-2'],
                    'samples': ['64.233.161.94 / 64.233.161.0/24'],
                    'services': ['YouTube'],
                    'service_keys': ['youtube'],
                    'message': 'runtime overlap',
                }],
            }

        def fake_auto_resolve(**kwargs):
            auto_calls.append(kwargs)
            return {'services': 1, 'status': 'finished', 'applied': []}

        web_route_tools_runtime.route_intersections.analyze_route_intersections = fake_analyze
        web_route_tools_runtime.service_routes.auto_resolve_service_route_intersections = fake_auto_resolve

        with tempfile.TemporaryDirectory() as tmp:
            lock_path = str(Path(tmp) / 'auto-resolve.lock')
            Path(lock_path).write_text(f'{os.getpid()} 1000.0\n', encoding='utf-8')

            def make_runtime():
                return web_route_tools_runtime.ServiceRouteToolsRuntime(
                    custom_check_presets_getter=lambda: service_catalog.CUSTOM_CHECK_PRESETS,
                    service_icon_html=lambda icon, label, opacity=1.0, size=18: f'<span>{label}</span>',
                    telegram_icon_html=lambda opacity=1.0: 'TG',
                    youtube_icon_html=lambda opacity=1.0: 'YT',
                    intersections_cache_ttl=1,
                    auto_resolve_lock_path=lock_path,
                    auto_resolve_lock_ttl=60,
                    time_provider=lambda: 1001.0,
                )

            second = make_runtime()
            second_report = second.intersections_snapshot()
            assert second_report['auto_resolve_pending']['status'] == 'running'
            assert second_report['auto_resolve_pending'].get('external') is True
            assert len(auto_calls) == 0
            assert Path(lock_path).exists()
    finally:
        web_route_tools_runtime.route_intersections.route_files_signature = original_route_signature
        web_route_tools_runtime.route_intersections.runtime_ipset_signature = original_runtime_signature
        web_route_tools_runtime.route_intersections.analyze_route_intersections = original_analyze
        web_route_tools_runtime.service_routes.auto_resolve_service_route_intersections = original_auto_resolve


def main():
    test_app_runtime_mode_setter_callbacks()
    test_router_health_runtime_payload_uses_keenetic_memory()
    test_router_health_runtime_payload_uses_stable_cpu_label_before_first_sample()
    test_router_health_runtime_payload_marks_proc_fallbacks_explicitly()
    test_router_health_runtime_program_rss_includes_related_processes()
    test_router_health_runtime_dns_payload()
    test_router_health_runtime_core_proxy_payload()
    test_router_health_runtime_dns_parsers()
    test_xray_compat_runtime_helpers()
    test_router_health_runtime_process_rss_parser()
    test_router_health_runtime_related_process_snapshot()
    test_router_metrics_runtime_snapshot()
    test_router_health_runtime_slow_snapshot_caches_heavy_checks()
    test_router_health_runtime_compact_snapshot_keeps_route_notes_cached()
    test_router_health_runtime_default_ndmc_ttl_matches_ui_refresh_window()
    test_router_health_runtime_compact_snapshot_refreshes_ndmc_by_ttl_and_force()
    test_router_health_runtime_smooths_short_cpu_spikes()
    test_router_health_runtime_primes_cpu_baseline_without_page_render_sample()
    test_proxy_config_builder()
    test_proxy_status_runtime_helpers()
    test_unblock_list_helpers()
    test_unblock_lists_hide_legacy_txt_files()
    test_vless2_youtube_routes_are_scoped()
    test_chrome_remote_desktop_routes_stay_manual_only()
    test_chatgpt_codex_routes_are_synced()
    test_ai_assistant_custom_routes_are_synced()
    test_primary_vless_does_not_capture_gmail_domains()
    test_custom_check_service_sources_are_synced()
    test_direct_update_script_records_update_status()
    test_update_static_assets_use_archive_fallback()
    test_local_archive_update_env_is_preserved()
    test_chatgpt_codex_custom_check_migration()
    test_preset_custom_checks_are_hydrated_from_catalog()
    test_meta_custom_check_migration()
    test_chrome_remote_desktop_routes_are_manual_only()
    test_web_command_state_helpers()
    test_web_http_common_helpers()
    test_web_http_basic_auth_accepts_and_rejects_credentials()
    test_installer_common_helpers()
    test_installer_page_is_bot_setup_only()
    test_repo_update_helpers()
    test_key_pool_web()
    test_web_pool_snapshot_worker_payload_is_safe_and_complete()
    test_youtube_healthcheck_detects_first_load_instability()
    test_youtube_healthcheck_requires_watch_page()
    test_youtube_healthcheck_retries_transient_watch_page()
    test_youtube_healthcheck_tolerates_transient_primary_generate_204()
    test_youtube_healthcheck_rejects_http_client_error_status()
    test_youtube_healthcheck_tolerates_single_quick_home_timeout()
    test_youtube_healthcheck_tolerates_single_quick_googlevideo_timeout()
    test_youtube_healthcheck_tolerates_single_transient_bootstrap_failure()
    test_youtube_healthcheck_tolerates_multiple_transient_bootstrap_failures()
    test_youtube_healthcheck_rejects_failed_googlevideo_media_endpoint()
    test_key_pool_subscription_helpers()
    test_key_pool_import_routes_selected_protocol_and_vless_context()
    test_pool_import_hint_is_protocol_specific_in_both_renderers()
    test_subscription_hwid_request_helpers()
    test_subscription_pool_sync_preserves_manual_keys()
    test_subscription_pool_sync_preserves_active_managed_key()
    test_telegram_pool_ui()
    test_web_background_helpers()
    test_web_get_actions_helpers()
    test_web_form_blocks_helpers()
    test_web_pool_form_blocks_helpers()
    test_web_status_builder_helpers()
    test_web_template_styles_helpers()
    test_probe_cache_update_entry_min_interval()
    test_probe_cache_quality_metrics()
    test_probe_cache_invalidates_changed_custom_check_targets()
    test_probe_cache_failed_results_expire_quickly()
    test_probe_cache_keeps_recent_success_on_transient_downgrade()
    test_telegram_call_learning_helpers()
    test_web_template_scripts_helpers()
    test_web_form_template_smoke()
    test_web_post_actions_helpers()
    test_web_action_feature_gates()
    test_service_route_apply_can_add_check()
    test_codex_version_matches_commit_count()
    test_ui_smoke_package_scripts_are_declared()
    test_ipset_refresh_is_backend_aware_and_atomic()
    test_runtime_startup_limits_router_flash_and_overhead()
    test_simple_mode_import_skips_advanced_modules()
    test_advanced_initial_web_context_skips_heavy_pool_modules()
    test_web_response_body_ignores_client_disconnect()
    test_youtube_edge_prefetch_cache_is_bounded_and_public_only()
    test_youtube_edge_prefetch_collects_limited_dns_candidates()
    test_youtube_edge_prefetch_can_prefer_fresh_dns_before_cache()
    test_youtube_edge_prefetch_extracts_watch_edge_hosts()
    test_youtube_edge_prefetch_priority_hosts_are_tried_before_cache()
    test_youtube_edge_prefetch_adds_active_route_and_removes_overlaps()
    test_youtube_edge_prefetch_runner_deletes_covering_ipset_network()
    test_youtube_edge_prefetch_cleans_other_sets_when_target_network_already_contains_ip()
    test_youtube_edge_prefetch_quality_probe_filters_slow_and_eof()
    test_youtube_edge_prefetch_skips_recent_bad_quality_cache()
    test_youtube_edge_prefetch_quality_probe_can_score_existing_ipset_entries()
    test_youtube_edge_prefetch_protects_shared_google_candidates()
    test_youtube_edge_prefetch_restores_only_quality_approved_cache()
    test_youtube_edge_prefetch_runner_collects_watch_hosts_through_route_socks()
    test_youtube_edge_prefetch_runner_extends_existing_prefetch_hosts()
    test_youtube_edge_prefetch_runner_extends_existing_watch_urls()
    test_youtube_edge_prefetch_runner_uses_fast_hosts_for_start_triggers()
    test_youtube_edge_prefetch_runner_skips_scheduler_full_run_on_high_cpu()
    test_youtube_edge_prefetch_runner_uses_cache_restore_for_start_triggers()
    test_entware_dns_runtime_helpers()
    test_web_status_runtime_helpers()
    test_cached_protocol_status_description_has_no_static_trailing_period()
    test_active_protocol_status_description_has_no_trailing_period()
    test_telegram_confirm_state_source()
    test_telegram_confirm_helpers()
    test_telegram_auth_state_helpers()
    test_telegram_message_flow_helpers()
    test_telegram_jobs_helpers()
    test_telegram_install_ui_helpers()
    test_telegram_key_ui_helpers()
    test_proxy_diagnostics_redact_credential_ids()
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
    test_route_intersections_filters_comments_and_ip_domain_noise()
    test_service_route_auto_resolves_known_service_intersections()
    test_service_route_auto_resolves_partial_service_target()
    test_service_route_auto_refreshes_runtime_only_known_intersections()
    test_route_intersections_detect_runtime_ipset_overlap()
    test_route_intersections_ignores_priority_runtime_overlap()
    test_service_route_ui_helpers()
    test_service_route_runtime_helpers()
    test_service_route_runtime_intersections_cache_uses_signatures()
    test_service_route_runtime_auto_resolves_known_intersections()
    test_service_route_runtime_pending_auto_resolve_is_cached()
    test_service_route_runtime_auto_resolve_uses_cross_runtime_lock()
    test_pool_probe_runner_failover_candidate()
    print('smoke_modules: ok')


if __name__ == '__main__':
    main()
