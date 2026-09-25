"""Pool views must remain readable while route/proxy application owns its lock."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

import pytest

APP = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(APP))
import key_pool_store
import key_pool_web
import web_form_blocks
from proxy_apply_coordinator import ApplyCoordinator, install_proxy_controls


@pytest.fixture
def views(tmp_path):
    stored = {'vless': ['saved-key']}
    current = {'vless': 'active-key'}
    writes = []
    env = {
        '_load_current_keys': lambda: current,
        '_load_key_pools': lambda: stored,
        '_key_pool_store': lambda: key_pool_store,
        '_save_key_pools': lambda pools: writes.append(pools),
        '_key_pool_web': lambda: key_pool_web,
        'web_form_blocks': web_form_blocks,
        'POOL_PROTOCOL_ORDER': key_pool_store.PROTOCOLS,
        '_subscription_public_settings': lambda: {},
        '_telegram_icon_html': lambda **kw: '',
        '_youtube_icon_html': lambda **kw: '',
        '_get_pool_probe_progress': lambda: {},
        '_load_custom_checks': lambda: [],
        '_load_key_probe_cache': lambda: {},
        '_service_route_summary': lambda: {},
        '_default_web_protocol': lambda: 'vless',
        '_pool_probe_progress_label': lambda *args: '',
        '_light_pool_summary_with_cache_fallback': lambda *args: {'note': 'summary'},
        '_pool_proto_label': lambda proto: proto,
        '_pool_key_display_name': lambda key: key,
        '_hash_key': lambda key: hashlib.sha256(key.encode()).hexdigest(),
        '_web_pool_snapshot_worker_payload': lambda **kw: None,
        '_overlay_live_pool_status': lambda value: value,
        '_background_task_economy_mode': lambda: False,
        'background_task_skip_log_at': {},
        'BACKGROUND_TASK_SKIP_LOG_INTERVAL_SECONDS': 60,
        '_write_runtime_log': lambda message: None,
        '_pool_summary_cache_signature': lambda *args: ('test',),
        'pool_summary_cache_lock': threading.Lock(),
        'pool_summary_cache': {},
        '_pool_summary_with_persisted_fallback': lambda value: value,
        '_pool_summary_with_latest_run': lambda value: value,
        'json': json,
        'time': time,
    }
    names = {
        '_ensure_current_keys_in_pools', '_key_pools_read_snapshot',
        '_web_pool_form_context', '_web_protocol_panel_html',
        '_web_pools_payload', '_web_pools_light_payload', '_web_pool_snapshot',
        '_web_custom_checks_light', '_format_pool_summary',
        '_pool_status_summary', '_pool_summary_count',
    }
    tree = ast.parse((APP / 'bot.py').read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP / 'bot.py'), 'exec'), env)
    control = ApplyCoordinator(tmp_path)
    install_proxy_controls(env, control, metadata=('_ensure_current_keys_in_pools',))
    return env, control, stored, current, writes


@pytest.mark.parametrize('view', ['form', 'panel', 'pools', 'light_pools', 'worker_pools',
                                  'snapshot', 'private_snapshot', 'summary', 'telegram'])
def test_views_complete_while_route_apply_is_busy(views, view):
    env, control, stored, current, writes = views
    original = copy.deepcopy(stored)
    if view == 'light_pools':
        env['_background_task_economy_mode'] = lambda: True
    if view == 'worker_pools':
        env['_web_pool_snapshot_worker_payload'] = lambda **kw: {'pools': {'vless': []}}
    calls = {
        'form': lambda: env['_web_pool_form_context'](current, {}, '', {'api_status': 'ok'}, False, {}),
        'panel': lambda: env['_web_protocol_panel_html']('vless', current, {}, ''),
        'pools': lambda: env['_web_pools_payload'](include_summary=True, include_custom_checks=True),
        'light_pools': lambda: env['_web_pools_payload'](include_summary=True, include_custom_checks=True),
        'worker_pools': lambda: env['_web_pools_payload'](),
        'snapshot': lambda: env['_web_pool_snapshot'](),
        'private_snapshot': lambda: env['_web_pool_snapshot'](include_keys=True),
        'summary': lambda: env['_pool_status_summary'](),
        'telegram': lambda: env['_format_pool_summary'](),
    }
    result, errors = [], []
    def read():
        try:
            result.append(calls[view]())
        except BaseException as error:
            errors.append(error)
    reader = threading.Thread(target=read)
    try:
        with control.mutation():
            reader.start()
            reader.join(2)
            assert not reader.is_alive(), 'A read waited for the route/proxy apply lock'
            assert not errors, errors
            assert result[0]
            assert not writes
            assert stored == original
    finally:
        reader.join(3)


@pytest.mark.parametrize('use_default', [True, False])
def test_read_snapshot_includes_active_key_without_persisting(views, use_default):
    env, _control, stored, current, writes = views
    snapshot = env['_key_pools_read_snapshot'](None if use_default else current)
    assert snapshot['vless'] == ['saved-key', 'active-key']
    snapshot['vless'].append('view-only')
    assert stored == {'vless': ['saved-key']}
    assert not writes
    assert env['_key_pools_read_snapshot']({})['vless'] == ['saved-key']


def test_write_sync_still_waits_for_apply_and_persists_active_key(views):
    env, control, _stored, _current, writes = views
    entered, finished = threading.Event(), threading.Event()
    def synchronize():
        entered.set()
        env['_ensure_current_keys_in_pools']()
        finished.set()
    writer = threading.Thread(target=synchronize)
    try:
        with control.mutation():
            writer.start()
            assert entered.wait(1)
            assert not finished.wait(.1)
            assert not writes
        assert finished.wait(2)
        assert writes[0]['vless'] == ['saved-key', 'active-key']
    finally:
        writer.join(3)
