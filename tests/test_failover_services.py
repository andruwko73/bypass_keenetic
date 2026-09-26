"""Automatic recovery must preserve the enabled services sharing the route."""
import ast
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import failover_services as policy
import pool_probe_runner
import probe_cache
import failover_candidate_runner
import auto_failover_runtime
from protocol_catalog import PROTOCOL_DISPLAY_ORDER as PROTOCOLS

CHECK = {'id': 'chatgpt_services', 'url': 'https://chat.example.invalid/', 'label': 'ChatGPT'}


def contract(proto):
    return policy.build_contracts([CHECK], {proto: ['chat.example.invalid']}, telegram_proto=proto)[proto]


@pytest.mark.parametrize('proto', PROTOCOLS)
def test_route_scoped_checks_and_shared_ip_do_not_add_unrelated_services(proto):
    routes = {proto: ['chat.example.invalid', '192.0.2.0/24']}
    checks = [CHECK, {'id': 'other', 'url': 'https://unrelated.example.invalid/', 'routes': ['192.0.2.0/24']}]
    contracts = policy.build_contracts(checks, routes, telegram_proto=proto)
    assert [c['id'] for c in contracts[proto]['custom']] == ['chatgpt_services']
    for other in PROTOCOLS:
        if other != proto:
            assert not contracts[other]['custom']


def test_split_exact_suffix_and_ambiguous_routes():
    checks = [{'id': 'split', 'urls': ['https://a.example.invalid/', 'https://b.example.invalid/']}]
    contracts = policy.build_contracts(checks, {'vless': ['full:a.example.invalid'], 'hysteria2': ['b.example.invalid']})
    assert contracts['vless']['custom'][0]['urls'] == ['https://a.example.invalid/']
    assert contracts['hysteria2']['custom'][0]['urls'] == ['https://b.example.invalid/']
    assert policy.target_owners('https://sub.a.example.invalid/', {'vless': {'domains': ['full:a.example.invalid'], 'ips': []}}) == set()
    assert policy.target_owners('https://a.example.invalid/', {
        p: {'domains': ['domain:example.invalid'], 'ips': []} for p in ('vless', 'vmess')}) == {'vless', 'vmess'}


def test_per_service_freshness_and_legacy_cache():
    c = contract('vless')
    cache = {}
    probe_cache.update_key_probe_cache_entry(cache, 'vless', 'synthetic', key_id='id',
        custom={'chatgpt_services': False}, custom_checks=[CHECK], now=100)
    probe_cache.update_key_probe_cache_entry(cache, 'vless', 'synthetic', key_id='id', tg_ok=True, now=200)
    assert cache['id']['custom_times']['chatgpt_services'] == 100
    assert policy.recent_failure(cache['id'], c, now=250) == 'chatgpt_services'
    assert policy.recent_failure(cache['id'], c, now=401) == ''
    legacy={'custom': {'chatgpt_services': False}, 'custom_ts':100,
            'custom_sig':probe_cache.custom_checks_signature([CHECK])}
    assert policy.recent_failure(legacy, c, now=200) == 'chatgpt_services'
    changed = policy.build_contracts([dict(CHECK, url='https://new.example.invalid')], {'vless':['new.example.invalid']})['vless']
    assert policy.recent_failure(cache['id'], changed, now=250) == ''


@pytest.mark.parametrize('value', [True, False, None])
def test_additional_service_tristate(value):
    verdict, reason, result=policy.check_required('proxy',contract('vless'),primary='telegram',
        check_telegram=lambda *a,**k:pytest.fail('primary already checked'),
        check_http=lambda *a,**k:(True,''),check_custom=lambda *a,**k:(value,'HTTP 451'))
    assert verdict is value
    assert result['custom'] == ({} if value is None else {'chatgpt_services':value})


def test_retry_budget_and_no_failure_for_interrupted_check():
    calls=[]
    def transient(*a,**k):
        calls.append(1)
        return len(calls)>1, 'request timed out'
    assert policy.check_required('proxy',contract('vless'),primary='telegram',
        check_telegram=None,check_http=None,check_custom=transient)[0] is True
    assert len(calls)==2
    assert policy.check_required('proxy',contract('vless'),primary='telegram',
        check_telegram=None,check_http=None,check_custom=transient,deadline=1,clock=lambda:2) == (None,'budget',{'custom':{}})


@pytest.mark.parametrize('proto', PROTOCOLS)
@pytest.mark.parametrize('primary', ['telegram','youtube'])
def test_candidate_with_working_primary_but_failed_chatgpt_is_never_selected(proto,primary,monkeypatch):
    import youtube_healthcheck, telegram_healthcheck
    monkeypatch.setattr(youtube_healthcheck,'check_youtube_through_proxy',lambda *a,**k:(True,''))
    monkeypatch.setattr(telegram_healthcheck,'check_telegram_service_through_proxy',lambda *a,**k:(True,''))
    records=[];stopped=[];active=[]
    def start(config):
        active[:] = [config[0][1]]
        return config, 'fixture'
    selected=pool_probe_runner.find_pool_failover_candidate(
        [(proto,'silver'),(proto,'full-service')],service=primary,batch_size=1,test_port='12000',
        proxy_outbound_from_key=lambda *a,**k:{},wait_for_socks5=lambda *a,**k:True,
        check_telegram_api=lambda *a,**k:(True,''),check_http=lambda *a,**k:(True,''),
        record_key_probe=lambda p,key,**k:records.append((key,k)),proto_label=str,log=lambda m:None,
        telegram_timeouts=(1,1),http_timeouts=(1,1),validate_outbound=lambda *a:None,
        build_config_batch=lambda batch,*a:batch,start_xray=start,
        stop_xray=lambda *a:stopped.append(True),cleanup_runtime=lambda **k:None,
        service_contracts={proto:contract(proto)},
        check_custom=lambda proxy,*a,**k:(active[0]=='full-service','HTTP 451'),
    )
    assert selected[1]=='full-service'
    assert any(key=='silver' and row.get('custom',{}).get('chatgpt_services') is False for key,row in records)
    assert stopped


def test_confirmation_worker_does_not_start_temporary_xray(tmp_path,monkeypatch):
    monkeypatch.setattr(failover_candidate_runner,'find_pool_failover_candidate',lambda *a,**k:pytest.fail('unexpected xray'))
    monkeypatch.setattr(failover_candidate_runner,'cleanup_pool_probe_runtime',lambda **k:None)
    monkeypatch.setattr(failover_candidate_runner,'record_key_probe',lambda *a,**k:None)
    monkeypatch.setattr(failover_candidate_runner,'_check_custom',lambda *a,**k:(False,'HTTP 451'))
    payload={'service':'telegram','candidates':[['vless','fixture']],
             'service_contracts':{'vless':contract('vless')},'confirmation_proxy':'socks5h://127.0.0.1:1'}
    source=tmp_path/'input';result=tmp_path/'result'
    source.write_text(json.dumps(payload))
    assert failover_candidate_runner.run_failover_candidate_worker(source,result)==2
    report=json.loads(result.read_text())
    assert report['candidate'] is None and 'ChatGPT / Codex' in report['events'][0]
    assert not source.exists()


def test_both_automations_confirm_route_services_before_commit():
    tree=ast.parse((ROOT/'app/bot.py').read_text(encoding='utf-8'))
    functions={n.name:ast.get_source_segment((ROOT/'app/bot.py').read_text(encoding='utf-8'),n)
               for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('_attempt_auto_failover','_switch_youtube_to_verified_candidate')}
    assert 'confirm_services=' in functions['_attempt_auto_failover']
    youtube=functions['_switch_youtube_to_verified_candidate']
    assert youtube.index('_confirm_failover_services(')<youtube.index("_update_youtube_failover_transaction('candidate_verified')")
    assert "_failover_candidate_still_valid(route_proto, key_value, 'youtube')" in youtube


@pytest.mark.parametrize('proto', PROTOCOLS)
@pytest.mark.parametrize('outcome', ['reject','unknown','success','stale','exception'])
def test_permanent_service_guard_restores_without_falsifying_telegram(proto,outcome):
    state={'last_ok':0,'last_fail':1,'last_attempt':0,'in_progress':False}
    installed=[];records=[];audit=[]
    value={'reject':False,'unknown':None,'success':True,'stale':True,'exception':None}[outcome]
    def confirm(*args):
        if outcome=='exception':raise RuntimeError('worker failed')
        return value,'service guard'
    result=auto_failover_runtime.attempt_auto_failover(
        state=state,pool_probe_locked=lambda:False,proxy_mode=proto,proxy_url='fixture',
        check_telegram_api=lambda *a,**k:(False,'timeout'),
        load_current_keys=lambda:{proto:'original'},load_key_pools=lambda:{proto:['original','candidate']},
        failover_candidates=lambda *a,**k:[(proto,'candidate')],
        find_pool_failover_candidate=lambda *a,**k:(proto,'candidate',True,None),
        install_key_for_protocol=lambda p,k,**kw:installed.append(k) or 'ok',
        update_proxy=lambda p:(True,''),set_active_key=lambda *a:None,
        record_key_probe=lambda *a,**k:records.append(k),log=lambda m:None,
        grace_seconds=10,switch_cooldown_seconds=30,time_provider=lambda:20,
        confirm_candidate=lambda *a:(True,'telegram works'),
        confirm_services=confirm,
        candidate_still_valid=lambda *a:outcome!='stale',
        audit_key_switch=lambda *a:audit.append(a),
    )
    assert result is (outcome=='success')
    if outcome=='stale':assert installed==[]
    elif outcome=='success':assert installed==['candidate'] and audit
    else:assert installed[0:2]==['candidate','original'] and not audit
    assert not any(row.get('tg_ok') is False for row in records)


def bot_function(name, env):
    tree=ast.parse((ROOT/'app/bot.py').read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'bot-fixture','exec'),env)
    return env[name]


def test_rotating_bounded_candidates_and_fresh_failure():
    captured=[]
    c=contract('vless')
    env={'_current_failover_service_contracts':lambda:{'vless':c},'_failover_service_contracts':{},
         '_load_key_probe_cache':lambda:{},'_hash_key':lambda k:k,'_failover_service_log':lambda *a:None,
         '_failover_candidate_cursor':{},'POOL_FAILOVER_PROCESS_WORKER_ENABLED':True,'POOL_PROBE_WORKER_MODE':False,
         '_find_pool_failover_candidate_in_process':lambda candidates,**k:captured.append(list(candidates))}
    select=bot_function('_find_pool_failover_candidate',env)
    candidates=[('vless',str(i)) for i in range(20)]
    select(candidates);select(candidates)
    assert captured==[candidates[:8],candidates[8:16]]
    assert env['_failover_service_contracts'][('telegram','vless')]==c


def test_confirmation_rejects_changed_route_and_deleted_candidate():
    c=contract('vless')
    env={'_failover_service_contracts':{('telegram','vless'):c},
         '_current_failover_service_contracts':lambda:{'vless':c},
         '_load_key_pools':lambda:{'vless':['candidate']}}
    valid=bot_function('_failover_candidate_still_valid',env)
    assert valid('vless','candidate')
    env['_load_key_pools']=lambda:{'vless':[]}
    assert not valid('vless','candidate')
    env['_load_key_pools']=lambda:{'vless':['candidate']}
    env['_current_failover_service_contracts']=lambda:{'vless':dict(c,revision='changed')}
    assert not valid('vless','candidate')


def test_recent_telegram_does_not_hide_new_custom_failure():
    cache={}
    probe_cache.update_key_probe_cache_entry(cache,'vless','fixture',key_id='id',
        custom={'chatgpt_services':True},custom_checks=[CHECK],now=100)
    probe_cache.update_key_probe_cache_entry(cache,'vless','fixture',key_id='id',tg_ok=True,now=10000)
    probe_cache.update_key_probe_cache_entry(cache,'vless','fixture',key_id='id',
        custom={'chatgpt_services':False},custom_checks=[CHECK],now=10001)
    assert cache['id']['custom']['chatgpt_services'] is False
