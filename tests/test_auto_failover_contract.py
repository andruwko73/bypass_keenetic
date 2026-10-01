"""Regressions for the actual recorder, apply caller and durable commit boundary."""
from copy import deepcopy
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

APP = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(APP))
import probe_cache
import background_policy
from proxy_apply_result import ApplyRequirement, AutomaticApplyBlocked
from youtube_healthcheck import check_youtube_through_proxy, youtube_health_state, YOUTUBE_GOOGLEVIDEO_URL
from youtube_stream_evidence import media_addresses
from test_proxy_control_integration import bot_function
from test_proxy_live_runtime import setup


@pytest.mark.parametrize('old_network,new_network', [('tcp', 'xhttp'), ('xhttp', 'tcp'), ('xhttp', 'xhttp')])
def test_both_transport_capabilities_are_checked_before_api_or_probes(setup, old_network, new_network):
    runtime, config, _ = setup
    current = deepcopy(config)
    current['outbounds'][0].setdefault('streamSettings', {})['network'] = old_network
    desired = deepcopy(current)
    desired['outbounds'][0]['streamSettings']['network'] = new_network
    desired['outbounds'][0]['settings']['synthetic'] = 'candidate-key'
    assert runtime.apply_requirement('vless', current=current, desired=desired) is ApplyRequirement.COMMON_CORE_RESTART
    assert runtime.api.calls == [] and runtime.key_paths['vless'].read_text() == 'old-key\n'


def test_maintenance_expires_without_fabricating_healthy_evidence():
    clock = [100]
    state = {'last_ok': 1, 'last_fail': 2, 'consecutive_failures': 3, 'force_recovery': True}
    env = {'time': SimpleNamespace(monotonic=lambda: clock[0]), 'auto_failover_state': state,
           '_key_apply_maintenance_until': 160}
    guard = bot_function('_key_apply_maintenance_active', env)
    assert guard() and state['last_fail'] == 2
    clock[0] = 161
    assert not guard() and state['last_fail'] == 0 and state['last_ok'] == 1
    assert not state['force_recovery'] and not guard()


def test_telegram_check_overlapping_own_restart_is_discarded():
    env = {'POOL_FAILOVER_PROCESS_WORKER_ENABLED': False, '_key_apply_maintenance_generation': 1,
           '_key_apply_maintenance_active': lambda: False}
    def check(*args, **kwargs):
        env['_key_apply_maintenance_generation'] = 2
        return False, 'timed out'
    env['_check_telegram_api_through_proxy'] = check
    assert bot_function('_check_telegram_api_for_background', env)()[0] is None


@pytest.mark.parametrize('field', ['quality_error', 'yt_quality_error'])
def test_real_recorder_accepts_current_and_queued_quality_errors(field):
    cache = {}
    assert probe_cache.update_key_probe_cache_entry(cache, 'vless2', 'fixture-key', yt_ok=True,
                                                    **{field: 'measurement timed out'})
    record = cache[probe_cache.hash_key('fixture-key')]
    assert record['yt_ok'] is True and record['quality_error'] == 'measurement timed out'
    assert 'yt_quality_error' not in record


@pytest.mark.parametrize('stamp', ['broken', None, float('nan'), float('inf')])
def test_old_or_invalid_finished_time_cannot_replace_real_completion(stamp):
    lines = background_policy.status_lines({}, {'status': 'completed', 'finished_at': 100},
        {'status': 'completed', 'finished_at': stamp}, [], time_text=str)
    assert '100' in lines['last_check']


def test_real_batch_and_worker_preserve_contract(tmp_path, monkeypatch):
    import pool_probe_process_runner as worker
    path = tmp_path / 'cache.json'
    monkeypatch.setattr(probe_cache, 'KEY_PROBE_CACHE_PATH', str(path))
    recorder = probe_cache.KeyProbeBatchRecorder(flush_every=1)
    recorder.record('vless2', 'fixture-key', yt_ok=True, yt_quality_error='timeout')
    recorder.flush()
    assert probe_cache.load_key_probe_cache()[probe_cache.hash_key('fixture-key')]['quality_error'] == 'timeout'
    import json
    key_id = probe_cache.hash_key('worker-key')
    records = tmp_path / 'records.jsonl'
    points = [{'kind': 'home', 'ok': False, 'latency_ms': 10, 'error': 'unstable'}]
    records.write_text(json.dumps({'key_id': key_id, 'proto': 'vless2', 'observed_at': time.time(),
                                  'values': {'yt_ok': True, 'yt_quality_error': 'timeout',
                                             'yt_endpoint_results': points}}) + '\n')
    assert worker.apply_pool_probe_records_file(str(records))['applied_count'] == 1
    record = probe_cache.load_key_probe_cache()[key_id]
    assert record['quality_error'] == 'timeout' and record['yt_endpoint_results'] == points


def test_optional_recorder_error_is_bounded_and_does_not_escape():
    logs = []
    env = {'time': time, '_write_runtime_log': logs.append,
           '_probe_cache': lambda: SimpleNamespace(record_key_probe=lambda *a, **k: (_ for _ in ()).throw(OSError('private')))}
    record = bot_function('_record_key_probe', env)
    for _ in range(5):
        assert record('vless2', 'fixture-key', yt_ok=True) is False
    assert len(logs) == 1 and 'private' not in logs[0]


@pytest.mark.parametrize('protocol', ['vless', 'vless2', 'vmess', 'trojan', 'shadowsocks', 'hysteria2'])
@pytest.mark.parametrize('outcome', [None, ApplyRequirement.COMMON_CORE_RESTART, 'api-error'])
def test_every_automatic_pool_rejects_hidden_cold_apply(protocol, outcome):
    calls = []
    def live(*args, **kwargs):
        assert kwargs['automatic'] is True
        if outcome == 'api-error':
            raise RuntimeError('API unavailable')
        return outcome
    env = {'time': time, '_try_live_key_apply': live, '_write_runtime_log': lambda *a: None,
           'PROXY_KEY_INSTALLERS': {protocol: lambda *a: calls.append('installer')},
           '_apply_installed_proxy': lambda *a, **k: calls.append('restart')}
    with pytest.raises(RuntimeError):
        bot_function('_install_key_for_protocol', env)(protocol, 'fixture-key', verify=False)
    assert calls == []


@pytest.mark.parametrize('manual,automatic,expected', [(100, 200, 200), (300, 200, 300), (100, 0, 100), (0, 200, 200), (0, 0, 0)])
def test_one_last_check_uses_terminal_chronology(manual, automatic, expected):
    lines = background_policy.status_lines({}, {'status': 'completed', 'finished_at': manual},
                                            {'status': 'completed', 'finished_at': automatic}, [], time_text=str)
    assert set(lines) == {'subscriptions', 'queue', 'last_check'}
    assert lines['last_check'].count('Последняя проверка:') == 1
    assert str(expected) in lines['last_check'] if expected else 'пока нет' in lines['last_check']


def test_new_running_probe_does_not_replace_finished_timestamp():
    lines = background_policy.status_lines({'status': 'running', 'started_at': 300},
        {'status': 'completed', 'finished_at': 100}, {'status': 'running', 'finished_at': 500}, [], time_text=str)
    assert '100' in lines['last_check'] and '500' not in lines['last_check']


def test_partial_pulse_is_not_complete_outage_or_proof_of_playback():
    metrics = {}
    ok, _ = check_youtube_through_proxy(lambda proxy, **kw: (kw['url'] == YOUTUBE_GOOGLEVIDEO_URL, 'request timed out'),
                                       None, profile='pulse', retry_unstable=False, metrics=metrics, http_timeouts=(1, 1))
    assert ok is False and youtube_health_state(ok, metrics)[0] == 'partial'
    assert [p['ok'] for p in metrics['yt_endpoint_results']] == [False, False, True]
    assert not any('playback' in k for k in metrics)
    cache = {}
    assert probe_cache.update_key_probe_cache_entry(cache, 'vless2', 'fixture-key', yt_ok=ok, **metrics)
    assert cache[probe_cache.hash_key('fixture-key')]['yt_stability'] == 'partial'


def test_only_fresh_identified_media_destinations_can_support_hold():
    cache = {'entries': {'203.0.113.1': {'host': 'r1---sn-fixture.googlevideo.com', 'last_seen': 100},
                         '203.0.113.2': {'host': 'redirector.googlevideo.com', 'last_seen': 100},
                         '203.0.113.3': {'host': 'r2---sn-old.googlevideo.com', 'last_seen': 1},
                         '203.0.113.4': {'host': 'example.invalid', 'last_seen': 100}}}
    assert media_addresses(cache, now=110, ttl_seconds=60) == {'203.0.113.1'}


def switch_fixture():
    current = {'vless2': 'original'}
    state = {'in_progress': False, 'last_fail': 50, 'consecutive_failures': 3}
    logs, events = [], []
    def install(proto, key, **kwargs):
        current[proto] = key
        events.append(('install', key))
        return 'hot'
    def restore(proto, key, **kwargs):
        current[proto] = key
        events.append(('restore', key))
        return True
    env = {'time': time, '_youtube_switch_cooldown_remaining': lambda *a: 0,
        '_load_key_pools': lambda: {'vless2': ['original', 'candidate']}, '_load_key_probe_cache': lambda: {},
        '_key_pool_store': lambda: SimpleNamespace(failover_candidates=lambda *a, **k: [('vless2', 'candidate')]),
        '_hash_key': lambda k: k, '_pool_key_display_name': lambda k: k,
        '_youtube_failover_policy': lambda: SimpleNamespace(prioritize_candidates=lambda c, **k: c),
        'YOUTUBE_ROUTE_FAILOVER_MAX_CANDIDATES': 3, 'YOUTUBE_ROUTE_QUALITY_CANDIDATE_MIN_SCORE': 60,
        'YOUTUBE_ROUTE_QUALITY_MIN_IMPROVEMENT': 10, 'YOUTUBE_ROUTE_FAILOVER_SWITCH_COOLDOWN_SECONDS': 300,
        '_write_runtime_log': logs.append, '_pool_proto_label': lambda p: p,
        '_find_pool_failover_candidate': lambda *a, **k: ('vless2', 'candidate', True, True),
        '_youtube_probe_score_for_key': lambda *a: (90, {}),
        'shutdown_requested': SimpleNamespace(is_set=lambda: False), '_youtube_stream_guard_active': lambda *a, **k: False,
        '_load_current_keys': lambda: dict(current), 'pool_apply_lock': threading.Lock(),
        '_failover_candidate_still_valid': lambda *a: True, '_begin_youtube_failover_transaction': lambda *a: True,
        '_install_key_for_protocol': install, '_update_youtube_failover_transaction': lambda *a: True,
        '_confirm_youtube_key_detailed': lambda *a, **k: (True, 'candidate confirmed', 1, {'yt_score': 90, 'quality_error': 'timeout'}),
        '_youtube_health_state': lambda ok, metrics: ('healthy', 'healthy', metrics), 'proxy_mode': 'vless',
        '_confirm_failover_services': lambda *a, **k: (True, ''), '_set_active_key': lambda *a: None,
        '_clear_youtube_failover_transaction': lambda: events.append(('clear',)) or True,
        '_audit_key_switch': lambda *a, **k: events.append(('audit', a[3], k)),
        '_record_key_probe': lambda *a, **k: events.append(('record',)),
        '_invalidate_web_status_cache': lambda: None, '_invalidate_key_status_cache': lambda: None,
        '_reset_youtube_quality_state': lambda s, **k: s.update(last_health_state=k['health_state']),
        '_restore_youtube_key_after_failed_failover': restore, '_memory_cleanup': lambda *a, **k: None,
        'YOUTUBE_STREAM_GUARD_FAILOVER_HOLD_SECONDS': 45}
    return env, state, current, events


@pytest.mark.parametrize('fault', ['_record_key_probe', '_audit_key_switch', '_invalidate_web_status_cache', '_memory_cleanup'])
def test_exception_after_commit_preserves_verified_key_and_resets_cycle(fault):
    env, state, current, events = switch_fixture()
    env[fault] = lambda *a, **k: (_ for _ in ()).throw(OSError('private'))
    switch = bot_function('_switch_youtube_to_verified_candidate', env)
    assert switch('vless2', 'original', dict(current), state, trigger='partial', reason='control timeout') is True
    assert current['vless2'] == 'candidate' and state['in_progress'] is False
    assert state['last_fail'] == state['consecutive_failures'] == 0
    assert not any(e[0] == 'restore' for e in events)


def test_audit_keeps_trigger_separate_from_candidate_confirmation():
    env, state, current, events = switch_fixture()
    assert bot_function('_switch_youtube_to_verified_candidate', env)(
        'vless2', 'original', dict(current), state, trigger='partial', reason='control timeout')
    audit = next(e for e in events if e[0] == 'audit')
    assert audit[1] == 'control timeout' and audit[2]['confirmation'] == 'candidate confirmed'


def test_exception_before_confirmation_restores_and_releases_operation():
    env, state, current, events = switch_fixture()
    env['_confirm_youtube_key_detailed'] = lambda *a, **k: (_ for _ in ()).throw(OSError('private'))
    assert not bot_function('_switch_youtube_to_verified_candidate', env)(
        'vless2', 'original', dict(current), state, trigger='partial', reason='control timeout')
    assert current['vless2'] == 'original' and not state['in_progress']
    assert ('restore', 'original') in events


def test_unsupported_apply_does_not_damage_candidate_rating():
    env, state, current, events = switch_fixture()
    env['_install_key_for_protocol'] = lambda *a, **k: (_ for _ in ()).throw(AutomaticApplyBlocked('restart required'))
    assert not bot_function('_switch_youtube_to_verified_candidate', env)(
        'vless2', 'original', dict(current), state, trigger='partial', reason='control timeout')
    assert current['vless2'] == 'original' and state['retry_not_before'] > time.time()
    assert not any(e[0] in ('record', 'restore') for e in events)
