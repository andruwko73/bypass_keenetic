"""Application binding and post-apply ABA race checks without router access."""
import ast
import os
from pathlib import Path
import sys
import threading

import pytest

APP = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(APP))
from post_apply_runtime import PostApplyCoordinator
from proxy_apply_coordinator import ApplyCoordinator, StaleApply, install_proxy_controls


def bot_function(name, env):
    tree = ast.parse((APP / 'bot.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(APP / 'bot.py'), 'exec'), env)
    return env[name]


def test_application_registry_binds_real_entry_points_and_shared_lock(tmp_path):
    tree = ast.parse((APP / 'bot.py').read_text(encoding='utf-8'))
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    initializer = functions['_initialize_proxy_apply_control']
    registration = next(n for n in ast.walk(initializer) if isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Name) and n.func.id == 'install_proxy_controls')
    groups = {
        key.arg: tuple(ast.literal_eval(name) for name in key.value.keys)
        if key.arg == 'recoveries' else ast.literal_eval(key.value)
        for key in registration.keywords
    }
    assert all(name in functions for values in groups.values() for name in values)
    assert '_clear_pool' in groups['writers'], 'take apply lock before the pool lock'
    assert '_apply_manual_key_safely' in groups['manual']
    assert {'_attempt_auto_failover', '_attempt_youtube_failover'} <= set(groups['background'])
    env = {'ApplyCoordinator': ApplyCoordinator, 'install_proxy_controls': install_proxy_controls,
           'private_runtime_directory': lambda _: tmp_path, 'proxy_apply_control': None,
           'os': os,
           'YOUTUBE_FAILOVER_TRANSACTION_FILE': tmp_path / 'youtube-transaction.json',
           'TELEGRAM_FAILOVER_TRANSACTION_FILE': tmp_path / 'telegram-transaction.json'}
    def stub(name):
        def call(*args, **kwargs):
            return env['proxy_apply_control'].active_ticket()
        call.__name__ = name
        return call
    for values in groups.values():
        for name in values:
            env[name] = stub(name)
    env['PROXY_KEY_INSTALLERS'] = {proto: env[proto] for proto in ('vless', 'vless2', 'vmess', 'trojan', 'shadowsocks', 'hysteria2')}
    initialize = bot_function('_initialize_proxy_apply_control', env)
    control = initialize()
    assert env['pool_apply_lock'] is env['core_proxy_config_write_lock'] is control.lock
    assert initialize() is control
    for proto, handler in env['PROXY_KEY_INSTALLERS'].items():
        assert handler is env[proto]
        assert handler._proxy_control_kind == 'writer'
    assert env['_apply_manual_key_safely']().manual_epoch >= 1
    for service in ('youtube', 'telegram'):
        recovery = env[f'_recover_interrupted_{service}_failover_transaction']
        journal = env[f'{service.upper()}_FAILOVER_TRANSACTION_FILE']
        assert recovery._proxy_control_kind == 'recovery'
        before = control.token()
        assert recovery() is None
        assert control.token() == before, 'an absent journal must not invalidate probes'
        journal.write_text('{}', encoding='utf-8')
        try:
            ticket = recovery()
            assert ticket is not None
            assert control.token() != before, 'actual recovery must invalidate probes'
        finally:
            journal.unlink()
        recovered = control.token()
        assert recovery() is None
        assert control.token() == recovered
    main_calls = {n.func.id: n.lineno for n in ast.walk(functions['main'])
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert main_calls['_initialize_proxy_apply_control'] < main_calls['start_http_server']


def test_post_apply_skips_queued_a_after_a_b_a_generation_change():
    generation = [1]
    ready, stopped = threading.Event(), threading.Event()
    probed, resumed = [], []
    coordinator = PostApplyCoordinator(
        current_matches=lambda *_: True, ready=ready.is_set,
        probe=lambda *args: probed.append(args), generation_getter=lambda: generation[0],
        resume_pool_probe=lambda: resumed.append(True), shutdown_event=stopped, poll_seconds=.05,
    )
    coordinator.schedule('vless', 'same-key-A', resume_pool_probe=True)
    worker = coordinator._worker
    try:
        generation[0] = 3  # A -> B -> A, key text is again identical.
        ready.set()
        worker.join(3)
        assert not worker.is_alive()
        assert not probed
        assert resumed == [True]
    finally:
        stopped.set()
        worker.join(3)


def test_post_apply_does_not_prefetch_after_mid_probe_generation_change():
    generation = [1]
    entered, finish, stopped = threading.Event(), threading.Event(), threading.Event()
    prefetched, tokens = [], []
    def probe(proto, key, token):
        tokens.append(token)
        entered.set()
        assert finish.wait(3)
        return {'yt_ok': True}
    coordinator = PostApplyCoordinator(
        current_matches=lambda *_: True, ready=lambda: True, probe=lambda *_: None,
        generation_getter=lambda: generation[0], generation_probe=probe,
        prefetch=lambda *args: prefetched.append(args), shutdown_event=stopped,
    )
    coordinator.schedule('vless', 'same-key-A')
    worker = coordinator._worker
    try:
        assert entered.wait(3)
        generation[0] = 3
        finish.set()
        worker.join(3)
        assert not worker.is_alive()
        assert tokens == [1]
        assert not prefetched
    finally:
        stopped.set()
        finish.set()
        worker.join(3)


def test_actual_bot_probe_cannot_commit_stale_result(tmp_path):
    coordinator = ApplyCoordinator(tmp_path)
    recorded, accepted = [], []
    token = coordinator.token(), 'boot:42:100'
    def check(proto, key, **kwargs):
        with coordinator.mutation(manual=True):
            pass
        accepted.append(kwargs['record_key_probe'](proto, key, tg_ok=True))
        return {'tg_ok': True}
    env = {
        'proxy_apply_control': coordinator, 'StaleApply': StaleApply,
        '_proxy_probe_generation': lambda: (coordinator.token(), 'boot:42:100'),
        '_post_apply_current_matches': lambda *_: True,
        '_record_key_probe': lambda *args, **kwargs: recorded.append((args, kwargs)),
        '_check_pool_key_through_proxy': check, '_load_custom_checks': lambda: {},
        'proxy_settings': {'vless': 'synthetic'}, '_youtube_route_protocol': lambda: 'vless2',
        '_memory_cleanup': lambda *args, **kwargs: None,
    }
    probe = bot_function('_run_applied_key_live_probe', env)
    probe('vless', 'same-key-A', token)
    assert accepted == [False]
    assert not recorded


def test_manual_choice_cancels_only_its_older_recovery_transactions():
    cleared = []
    env = {'_telegram_route_protocol': lambda: 'vless', '_youtube_route_protocol': lambda: 'vless2',
           '_clear_telegram_failover_transaction': lambda: cleared.append('telegram'),
           '_clear_youtube_failover_transaction': lambda: cleared.append('youtube')}
    discard = bot_function('_discard_superseded_failover_transactions', env)
    discard('vless')
    assert cleared == ['telegram']
    discard('vmess')
    assert cleared == ['telegram']
    discard('vless2')
    assert cleared == ['telegram', 'youtube']


@pytest.mark.parametrize('outcome', ['hot', 'noop', 'unhealthy', 'error', None])
def test_bot_install_uses_live_result_without_hidden_restart(tmp_path, outcome):
    import time
    from types import SimpleNamespace
    coordinator = ApplyCoordinator(tmp_path)
    calls = []
    def apply(*args, **kwargs):
        assert kwargs['ticket'] == coordinator.active_ticket()
        calls.append('live')
        if outcome == 'error':
            raise OSError('synthetic private detail must not escape')
        return outcome
    env = {
        'time': time, 'proxy_apply_control': coordinator,
        'proxy_live_backend': SimpleNamespace(allowed_protocols=('vless',), try_apply=apply),
        '_logical_proxy_config': lambda *args: {'synthetic': True},
        '_proxy_apply_settings': lambda: {'vless': {'label': 'Vless 1'}},
        'PROXY_KEY_INSTALLERS': {'vless': lambda key: calls.append('installer')},
        '_apply_installed_proxy': lambda *args, **kwargs: calls.append('cold') or 'cold-result',
        '_write_runtime_log': lambda *args: None,
    }
    bot_function('_try_live_key_apply', env)
    install = bot_function('_install_key_for_protocol', env)
    with coordinator.mutation(manual=True):
        if outcome in ('error', 'unhealthy'):
            with pytest.raises(RuntimeError) as failure:
                install('vless', 'synthetic', verify=False)
            assert 'private detail' not in str(failure.value)
            assert calls == ['live']
        else:
            result = install('vless', 'synthetic', verify=False)
            assert calls == (['live', 'installer', 'cold'] if outcome is None else ['live'])
            assert ('без перезапуска' in result) == (outcome is not None)


def test_socket_health_alone_no_longer_produces_noop():
    env = {'_post_apply_current_matches': lambda *_: True,
           '_check_local_proxy_endpoint': lambda *_: (True, 'SOCKS greeting'),
           'proxy_live_backend': None}
    healthy = bot_function('_active_key_endpoint_healthy', env)
    assert healthy('vless', 'same-saved-text') is False


def test_managed_config_written_before_controlled_load_receipt(tmp_path):
    import json
    import os
    from types import SimpleNamespace
    from xray_live_apply import managed_config
    path = tmp_path / 'config.json'
    logical = {'inbounds': [{'tag': 'in', 'protocol': 'socks', 'port': 10811}],
               'outbounds': [{'tag': 'proxy-vless', 'protocol': 'vless'}],
               'routing': {'rules': [{'type': 'field', 'network': 'tcp,udp', 'outboundTag': 'proxy-vless'}]}}
    coordinator = ApplyCoordinator(tmp_path)
    receipts = []
    def record(config, **kwargs):
        assert json.loads(path.read_text()) == managed_config(config, api_port=10899)
        receipts.append(kwargs)
    backend = SimpleNamespace(config_for_load=lambda c: managed_config(c, api_port=10899),
                              register_controlled_load=record)
    env = {'os': os, 'proxy_live_backend': backend, 'proxy_apply_control': coordinator,
           'CORE_PROXY_CONFIG_DIR': str(tmp_path), 'CORE_PROXY_CONFIG_PATH': str(path),
           'core_proxy_config_write_lock': coordinator.lock, '_build_v2ray_config': lambda *args: logical,
           '_write_json_file': lambda p, value: Path(p).write_text(json.dumps(value))}
    write = bot_function('_write_v2ray_config', env)
    confirm = bot_function('_confirm_proxy_controlled_load', env)
    with coordinator.mutation():
        write()
        assert not receipts
        confirm('previous-core')
    assert receipts == [{'previous_identity': 'previous-core', 'generation': 1}]
