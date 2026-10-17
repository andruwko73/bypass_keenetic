"""Service ownership, shared recovery holds and user-visible commit history."""
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import event_history
import failover_services as policy
import failover_candidate_runner as worker
import key_pool_store
import pool_probe_runner
from protocol_catalog import PROTOCOL_DISPLAY_ORDER as PROTOCOLS
from test_failover_services import bot_function


@pytest.mark.parametrize('proto', PROTOCOLS)
@pytest.mark.parametrize('telegram_here', [False, True])
def test_entire_candidate_pipeline_only_checks_assigned_services(proto, telegram_here, monkeypatch):
    import telegram_healthcheck
    monkeypatch.setattr(telegram_healthcheck, 'check_telegram_service_through_proxy',
                        lambda *a, **kw: pytest.fail('implicit primary Telegram check'))
    check = {'id': 'chatgpt_services', 'url': 'https://chat.example.invalid'}
    contract = policy.build_contracts([check], {proto: ['chat.example.invalid']},
                                     telegram_proto=proto if telegram_here else '')[proto]
    assert contract['telegram'] is telegram_here
    calls = []; records = []; stopped = []
    def telegram(*a, **kw):
        assert telegram_here
        calls.append('telegram')
        return True, ''
    def custom(*a, **kw):
        calls.append('chatgpt')
        return True, ''
    cache = {'first': {'tg_ok': False, 'ts': 99}, 'second': {'tg_ok': True, 'ts': 100}}
    candidates = key_pool_store.failover_candidates(
        {proto: ['old', 'first', 'second']}, proto, 'old', protocols=(proto,),
        service='route', key_probe_cache=cache, hash_key=str, skip_failed=True,
        recent_failure_backoff_seconds=300, now=110)
    assert candidates == [(proto, 'first'), (proto, 'second')]
    result = pool_probe_runner.find_pool_failover_candidate(
        candidates, service='route', service_contracts={proto: contract}, check_custom=custom,
        batch_size=1, test_port='12000', proxy_outbound_from_key=lambda *a: {},
        wait_for_socks5=lambda *a, **kw: True, check_telegram_api=telegram,
        check_http=lambda *a, **kw: pytest.fail('unassigned YouTube'),
        record_key_probe=lambda *a, **kw: records.append(kw), proto_label=str,
        log=lambda *a: None, telegram_timeouts=(1, 1), http_timeouts=(1, 1),
        validate_outbound=lambda *a: None, build_config_batch=lambda *a: {},
        start_xray=lambda *a: ('process', 'config'), stop_xray=lambda *a: stopped.append(a),
        cleanup_runtime=lambda **kw: None)
    assert result[:2] == (proto, 'first') and stopped
    assert calls == (['telegram', 'chatgpt'] if telegram_here else ['chatgpt'])
    assert records[-1]['custom'] == {'chatgpt_services': True}
    assert all('tg_ok' not in r for r in records) if not telegram_here else records[-1]['tg_ok']


@pytest.mark.parametrize('proto', PROTOCOLS)
def test_active_confirmation_worker_preserves_failure_identity_without_telegram(proto, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, '_telegram_check', lambda *a: lambda *a, **kw: pytest.fail('Telegram'))
    monkeypatch.setattr(worker, '_check_custom', lambda *a, **kw: (False, 'HTTP 451'))
    monkeypatch.setattr(worker, 'record_key_probe', lambda *a, **kw: None)
    monkeypatch.setattr(worker, 'find_pool_failover_candidate', lambda *a, **kw: pytest.fail('new Xray'))
    source, result = tmp_path/'input', tmp_path/'result'
    source.write_text(json.dumps({'service': 'route', 'confirmation_proxy': 'fixture',
        'confirmation_verdict': True, 'candidates': [[proto, 'old']],
        'service_contracts': {proto: {'telegram': False, 'youtube': False, 'custom': [
            {'id': 'chatgpt_services', 'url': 'https://chat.example.invalid'}]}}}))
    assert worker.run_failover_candidate_worker(source, result) == 2
    report = json.loads(result.read_text())
    assert report['confirmation_verdict'] is False
    assert report['confirmation_service'] == 'chatgpt_services'


def run_sequence(sequence, *, identities=None, valid=True):
    state = {}; applied = []
    for i, evidence in enumerate(sequence):
        policy.required_route_recovery(state, (identities or ['old']*len(sequence))[i],
            now=100+i*60, check_active=lambda: evidence, select_candidate=lambda: 'new',
            still_valid=lambda c: valid, apply_candidate=applied.append)
    return state, applied


@pytest.mark.parametrize('interrupt', [True, None, {'verdict': False, 'service': 'discord'}])
def test_unrelated_failure_success_and_unknown_interrupt_confirmation(interrupt):
    failed = {'verdict': False, 'service': 'chatgpt_services'}
    _, applied = run_sequence([failed, failed, interrupt, failed, failed])
    assert applied == []
    _, applied = run_sequence([failed, failed, interrupt, failed, failed, failed])
    assert applied == ['new']


def test_key_change_does_not_erase_cooldown_and_stale_results_never_apply():
    failed = {'verdict': False, 'service': 'chatgpt_services'}
    state, applied = run_sequence([failed]*6, identities=['old']*3+['new']*3)
    assert applied == ['new'] and state['retry_at'] == 520
    assert run_sequence([failed]*3, valid=False)[1] == []


@pytest.mark.parametrize('proto', PROTOCOLS)
def test_reservation_is_atomic_and_commit_extends_shared_hold(proto):
    gate = policy.RouteRecoveryGate()
    barrier = threading.Barrier(3); results=[]
    def reserve():
        barrier.wait(); results.append(gate.deferred(proto, 100, reserve=True))
    threads=[threading.Thread(target=reserve) for _ in range(2)]
    for t in threads:t.start()
    barrier.wait()
    for t in threads:t.join()
    assert sorted(results) == [False, True]
    gate.committed(proto, 145)
    assert gate.deferred(proto, 444) and not gate.deferred(proto, 445)
    other=next(p for p in PROTOCOLS if p != proto)
    assert not gate.deferred(other, 150)
    gate.reject(proto, 'old', 100)
    assert not gate.eligible(proto, 'old', 699)
    assert gate.eligible(proto, 'old', 700)
    assert gate.eligible(proto, 'different', 150)


@pytest.mark.parametrize('name,args', [
    ('_attempt_auto_failover', ()),
    ('_attempt_chatgpt_route_failover', ()),
    ('_switch_youtube_to_verified_candidate', ('vless', 'old', {}, {})),
])
def test_all_production_automations_obey_same_route_hold(name, args):
    gate=policy.RouteRecoveryGate(); gate.committed('vless', 100)
    env={'time':SimpleNamespace(time=lambda:150), '_route_recovery_gate':gate,
        '_key_apply_maintenance_active':lambda:False, '_telegram_route_protocol':lambda:'vless',
        '_app_mode_pool_enabled':lambda:True, '_update_maintenance_active':lambda:False,
        '_post_apply_ready':lambda:True, 'pool_apply_lock':threading.RLock(),
        '_current_failover_service_contracts':lambda:{'vless':{'custom':[{'id':'chatgpt_services'}]}},
        '_load_current_keys':lambda:{'vless':'old'}, '_chatgpt_failover_cursor':0,
        '_chatgpt_failover_states':{}, 'proxy_settings':{'vless':'fixture'}}
    call=bot_function(name, env)
    kwargs={'trigger':'failed','reason':'fixture'} if args else {}
    assert call(*args, **kwargs) is False


def test_five_commits_and_hundreds_of_checks_keep_exactly_five_history_rows(tmp_path):
    path=str(tmp_path/'history')
    for index in range(5):
        event_history.record_event(action='key_switch_auto', key_hash=str(index), event_path=path)
        for _ in range(150):
            event_history.record_event(action='failover_service_check', event_path=path)
    rows=event_history.load_events(120,event_path=path)
    assert len(rows)==5 and {e['key_hash'] for e in rows}==set(map(str,range(5)))
    assert len(Path(path).read_text().splitlines())==5


def test_legacy_noise_is_filtered_before_limit_and_other_actions_survive(tmp_path):
    path=tmp_path/'history'
    rows=[{'ts':i,'action':'key_switch_auto','key_hash':str(i)} for i in range(5)]
    rows += [{'action':'web_command_finish'}, {'action':'key_switch'}, {'action':'scheduler_error','level':'error'}]
    rows += [{'action':'failover_service_check'}]*200
    path.write_text('\n'.join(json.dumps(e) for e in rows)+'\n')
    visible=event_history.load_events(120,event_path=str(path))
    assert len(visible)==8 and sum(e['action']=='key_switch_auto' for e in visible)==5
    event_history._trim_history(str(path),120,force=True)
    assert len(path.read_text().splitlines())==8


def test_diagnostic_log_is_deduplicated_bounded_and_never_writes_history():
    logs=[]
    env={'_failover_log_times':{},'time':SimpleNamespace(time=lambda:1000),
         '_write_runtime_log':logs.append, '_record_event':lambda *a,**kw:pytest.fail('history')}
    log=bot_function('_failover_service_log',env)
    for _ in range(100):log('same','route','vless')
    assert len(logs)==1
    for i in range(200):log(str(i),'route','vless')
    assert len(env['_failover_log_times'])<=128


def test_production_hot_filter_excludes_recently_rejected_key_and_then_rechecks():
    gate=policy.RouteRecoveryGate(); gate.reject('vmess','old',100)
    clock=[150]
    env={'_route_recovery_gate':gate,'time':SimpleNamespace(time=lambda:clock[0]),
         '_hash_key':str,'_logical_proxy_config':lambda *a:{},
         'proxy_live_backend':SimpleNamespace(apply_requirement=lambda *a,**kw:object())}
    select=bot_function('_automatic_hot_candidates',env)
    assert select([('vmess','old'),('vmess','new')])==[('vmess','new')]
    clock[0]=701
    assert select([('vmess','old')])==[('vmess','old')]


def test_manual_choice_discards_old_series_and_holds_automatic_recovery():
    gate=policy.RouteRecoveryGate()
    env={'_chatgpt_failover_states':{'vmess':{'failures':2}},'_route_recovery_gate':gate,
         'time':SimpleNamespace(time=lambda:100),'_hash_key':str,
         '_telegram_route_protocol':lambda:'vless','_youtube_route_protocol':lambda:'vless2'}
    reset=bot_function('_reset_failover_state_after_manual_apply',env)
    reset('vmess','manual')
    assert env['_chatgpt_failover_states']=={}
    assert gate.deferred('vmess',399) and not gate.deferred('vmess',400)
