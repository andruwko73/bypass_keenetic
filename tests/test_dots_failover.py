"""Offline regional admission and independent per-route recovery for Pro."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import custom_check_policy as region
import failover_services as policy
import failover_candidate_runner as worker
import pool_probe_curl as curl
import proxy_status
from protocol_catalog import PROTOCOL_DISPLAY_ORDER
from test_failover_services import bot_function
import threading
import re


@pytest.mark.parametrize('country', sorted(region.DOTS_PRO_EXCLUDED_REGIONS | {'RU', 'CN', 'BY', 'IR'}))
def test_pro_excludes_eea_uk_switzerland_and_unsupported_chatgpt_regions(country):
    assert region.dots_pro_region_verdict(f'h=chatgpt.com\nloc={country}\n'.encode())[0] is False


@pytest.mark.parametrize('country', ['US', 'CA', 'JP', 'AU', 'RS', 'AL', 'ME', 'TR', 'BR'])
def test_supported_pro_countries_including_non_eea_europe(country):
    assert region.dots_pro_region_verdict(f'h=chatgpt.com\nloc={country}\n'.encode())[0] is True


@pytest.mark.parametrize('body', [b'', b'<html>challenge</html>', b'loc=USA', b'loc=', b'loc=US\n' * 0])
def test_unknown_country_is_not_a_failed_key(body):
    assert region.dots_pro_region_verdict(body)[0] is None


@pytest.mark.parametrize('proto', PROTOCOL_DISPLAY_ORDER)
def test_gpt_does_not_require_unassigned_telegram(proto):
    check = {'id': 'chatgpt_services', 'url': 'https://chatgpt.com'}
    contracts = policy.build_contracts([check], {proto: ['chatgpt.com']})
    assert contracts[proto]['telegram'] is False
    assert contracts[proto]['custom']
    for other in PROTOCOL_DISPLAY_ORDER:
        if other != proto:
            assert not contracts[other]['custom'] and not contracts[other]['telegram']
    assert all(not c['custom'] for c in policy.build_contracts([], {proto: ['chatgpt.com']}).values())


@pytest.mark.parametrize('transport', ['curl', 'requests'])
@pytest.mark.parametrize('country,expected', [('US', True), ('DE', False), ('GB', False), ('CH', False), ('', None)])
def test_every_probe_transport_checks_country_before_accepting_api_401(monkeypatch, transport, country, expected):
    calls = []
    trace = f'h=chatgpt.com\nloc={country}\nip=192.0.2.1\n'.encode()
    def respond(url):
        calls.append(url)
        return (200, trace) if url == region.DOTS_TRACE_URL else (401, b'authentication required')
    if transport == 'curl':
        def run(proxy, url, *a, **kw):
            code, body = respond(url)
            return code, url, body, ''
        monkeypatch.setattr(curl, '_run_curl', run)
        checker = curl.check_custom_target_through_proxy
    else:
        class Response:
            def __init__(self, code, body): self.status_code, self.body = code, body
            def iter_content(self, **kw): return iter([self.body])
            def close(self): pass
        class Session:
            def get(self, url, **kw):
                assert self.trust_env is False
                assert kw['proxies']['https'] == 'socks5h://127.0.0.1:1'
                return Response(*respond(url))
            def close(self): pass
        monkeypatch.setattr(proxy_status, '_requests_module', lambda: SimpleNamespace(Session=Session))
        checker = proxy_status.check_custom_target_through_proxy
    verdict, message = checker(lambda u: u, 'socks5h://127.0.0.1:1', 'https://api.openai.com/v1/models')
    assert verdict is expected
    assert calls[0] == region.DOTS_TRACE_URL
    assert len(calls) == (2 if expected is True else 1)
    assert '192.0.2.1' not in message


@pytest.mark.parametrize('verdict', [True, None, False])
def test_recovery_needs_three_failures_and_preserves_unknown(verdict):
    state = {}; applied = []
    def cycle(t):
        return policy.required_route_recovery(state, ('key', 'route'), now=t,
            check_active=lambda: verdict, select_candidate=lambda: 'candidate',
            still_valid=lambda c: True, apply_candidate=applied.append)
    assert not cycle(100)
    assert not cycle(110)
    assert not cycle(160)
    assert cycle(220) is (verdict is False)
    assert applied == (['candidate'] if verdict is False else [])
    assert not cycle(230)


def test_changed_key_or_route_resets_failures_and_stale_candidate_never_applies():
    state = {}; applied = []
    def cycle(t, identity, valid):
        return policy.required_route_recovery(state, identity, now=t, check_active=lambda: False,
            select_candidate=lambda: 'candidate', still_valid=lambda c: valid, apply_candidate=applied.append)
    assert not cycle(100, ('old', 'route'), True)
    assert not cycle(160, ('new', 'route'), True)
    assert not cycle(220, ('new', 'route'), False)
    assert not applied


def test_unknown_active_worker_result_survives_serialization_without_starting_xray(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, 'find_pool_failover_candidate', lambda *a, **kw: pytest.fail('temporary Xray'))
    monkeypatch.setattr(worker, 'record_key_probe', lambda *a, **kw: pytest.fail('cache write before commit'))
    monkeypatch.setattr(worker, '_telegram_check', lambda *a: lambda *a, **kw: (True, ''))
    monkeypatch.setattr(worker, '_check_custom', lambda *a, **kw: (None, 'country unknown'))
    payload = {'service': 'telegram', 'candidates': [['vless2', 'fixture']],
        'confirmation_proxy': 'socks5h://127.0.0.1:1', 'confirmation_verdict': True, 'record_confirmation': False,
        'service_contracts': {'vless2': {'telegram': True, 'custom': [
            {'id': 'chatgpt_services', 'url': 'https://chatgpt.com'}]}}}
    source, result = tmp_path / 'input.json', tmp_path / 'result.json'
    source.write_text(json.dumps(payload), encoding='utf-8')
    assert worker.run_failover_candidate_worker(source, result) == 2
    assert json.loads(result.read_text(encoding='utf-8'))['confirmation_verdict'] is None


@pytest.mark.parametrize('proto', PROTOCOL_DISPLAY_ORDER)
@pytest.mark.parametrize('media_active', [False, True])
@pytest.mark.parametrize('bookkeeping_error', [False, True])
def test_independent_bot_recovers_gpt_route_with_telegram_still_working(proto, media_active, bookkeeping_error):
    contract = policy.build_contracts([{'id': 'chatgpt_services', 'url': 'https://chatgpt.com'}],
                                      {proto: ['chatgpt.com']})[proto]
    applied = []; clock = [100]; current = {proto: 'old'}
    env = {'_chatgpt_failover_cursor': 0, '_chatgpt_failover_states': {},
        '_chatgpt_failover_guard': threading.local(), 'time': SimpleNamespace(time=lambda: clock[0]),
        '_app_mode_pool_enabled': lambda: True, '_update_maintenance_active': lambda: False,
        '_key_apply_maintenance_active': lambda: False, '_post_apply_ready': lambda: True,
        'pool_apply_lock': threading.RLock(), '_current_failover_service_contracts': lambda: {proto: contract},
        '_load_current_keys': lambda: current, '_hash_key': lambda k: k,
        'proxy_settings': {proto: 'proxy'}, '_check_required_route': lambda *a, **kw: {'verdict': False, 'service': 'chatgpt_services'},
        '_post_apply_current_matches': lambda p, k: current[p] == k,
        '_failover_candidate_still_valid': lambda *a: True,
        '_key_pool_store': lambda: SimpleNamespace(failover_candidates=lambda *a, **kw: [(proto, 'new')]),
        '_load_key_pools': lambda: {proto: ['old', 'new']}, '_load_key_probe_cache': lambda: {},
        '_automatic_hot_candidates': lambda c: c,
        '_find_pool_failover_candidate': lambda c, **kw: (proto, 'new', True, None),
        'YOUTUBE_STREAM_GUARD_PROTOCOLS': (proto,), 'YOUTUBE_STREAM_GUARD_FAILOVER_HOLD_SECONDS':60,
        '_vless_traffic_guard_active':lambda *a,**kw:pytest.fail('unrelated traffic must not block recovery'),
        '_audit_key_switch': lambda *a, **kw: None,
        '_invalidate_web_status_cache': lambda: None, '_invalidate_key_status_cache': lambda: None,
        '_write_runtime_log': lambda *a: None}
    if bookkeeping_error:
        env['_invalidate_web_status_cache'] = lambda: (_ for _ in ()).throw(OSError('fixture'))
    def install(p, key, **kw):
        assert kw == {'automatic': True, 'require_health': True}
        assert env['_chatgpt_failover_guard'].expected == (proto, key, contract['revision'])
        applied.append((p, key))
        current[p] = key
    env['_install_key_for_protocol'] = install
    def media_guard(p, **kw):
        assert p == proto and kw['require_downlink'] is True and kw['log'] is True
        return media_active
    env['_youtube_stream_guard_active'] = media_guard
    attempt = bot_function('_attempt_chatgpt_route_failover', env)
    assert attempt() is False
    clock[0] = 160
    assert attempt() is False
    clock[0] = 220
    assert attempt() is (not media_active)
    assert applied == ([] if media_active else [(proto, 'new')])
    assert getattr(env['_chatgpt_failover_guard'],'expected',None) is None
    clock[0] = 280
    assert attempt() is False
    assert applied == ([] if media_active else [(proto, 'new')])


@pytest.mark.parametrize('mode', ['unknown', 'route_deleted', 'route_changed', 'key_deleted'])
def test_permanent_probe_rejects_unknown_and_concurrent_route_changes(mode):
    contract = policy.build_contracts([{'id': 'chatgpt_services', 'url': 'https://chatgpt.com'}],
                                     {'vless': ['chatgpt.com']})['vless']
    guard = threading.local(); guard.expected = ('vless', 'candidate', contract['revision'])
    contracts = {'vless': contract}
    def check(*a, **kw):
        assert kw == {'record': False}
        if mode == 'route_deleted': contracts.clear()
        if mode == 'route_changed': contracts['vless'] = dict(contract, revision='changed')
        return None if mode == 'unknown' else True
    env = {'_chatgpt_failover_guard': guard, '_current_failover_service_contracts': lambda: contracts,
        '_load_key_pools': lambda: {'vless': [] if mode == 'key_deleted' else ['candidate']},
        '_check_required_route': check}
    verify = bot_function('_live_key_data_check', env)
    assert verify('vless', 'candidate') is False


def test_chatgpt_recovery_is_audited_as_automatic_with_its_own_service(tmp_path):
    import os, time
    events=[]
    env={'_hash_key': lambda key:'synthetic-id', '_pool_key_display_name':lambda key:'Synthetic',
        '_redact_sensitive_text':str, 're':re, 'os':os, 'time':time,
        'KEY_SWITCH_AUDIT_LOG':str(tmp_path/'audit.log'),
        '_record_event':lambda **kw:events.append(kw)}
    audit=bot_function('_audit_key_switch',env)
    audit('chatgpt_auto_failover','vless','fixture','qualified Pro region')
    assert events[0]['action']=='key_switch_auto'
    assert events[0]['service']=='chatgpt_services'
    assert events[0]['details']['mode']=='automatic'
