import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from route_diagnostics_service import RouteDiagnosticsService, available_wans, memory_available
from route_diagnostics_web import render_page, results_html
from route_profiles import profile_fingerprint
import web_get_actions
import web_post_actions


class Runtime:
    def __init__(self, **kwargs):
        self.callbacks = kwargs
        self.started = []
        self.cancelled = False
    def snapshot(self):
        return {'job': {'state': 'idle', 'running': False}, 'results': {}}
    def start(self, identity):
        self.started.append(identity)
    def cancel(self):
        self.cancelled = True


@pytest.fixture
def service(tmp_path):
    control = SimpleNamespace(lock=threading.RLock(), generation=lambda: 3,
                              capture=lambda: SimpleNamespace(generation=3), current=lambda ticket: True)
    return RouteDiagnosticsService(path=tmp_path/'profiles.json', control=control,
        load_keys=lambda: {'vless': 'PRIVATE-KEY', 'vless2': 'PRIVATE-KEY2'},
        coordinated=lambda name, work: (True, work()), probe_lock=threading.Lock(),
        resource_guard=lambda: True, wans=lambda: ['eth1'], runtime_factory=Runtime)


def form(**values):
    default = {'label': 'Видео на ПК', 'device': '192.168.1.50', 'url': 'https://example.com/',
               'protocols': ['vless', 'vless2'], 'wan': 'eth1', 'revision': '0'}
    default.update(values)
    return {key: value if isinstance(value, list) else [value] for key, value in default.items()}


def test_read_payload_never_starts_probes_or_exposes_key(service):
    payload = service.payload()
    assert payload['active_protocols'] == ['vless', 'vless2']
    assert 'PRIVATE' not in json.dumps(payload)
    assert not service.runtime.started
    page = service.page('safe-token')
    assert 'PRIVATE' not in page
    assert 'csrf_token' in page and 'X-CSRF-Token' in page


def test_save_run_cancel_remove_and_revision_race(service):
    assert service.action('save', form())['success']
    state = service.payload()
    profile = state['profiles'][0]
    assert profile['direct_allowed'] is False
    assert not service.action('save', form(label='Stale'))['success']
    data = {'profile_id': [profile['id']], 'revision': ['1']}
    assert service.action('run', data)['success']
    assert service.runtime.started == [profile['id']]
    assert service.action('cancel', {})['success'] and service.runtime.cancelled
    assert not service.action('remove', dict(data, revision=['0']))['success']
    assert service.action('remove', data)['success']
    assert service.payload()['profiles'] == []


@pytest.mark.parametrize('fields', [
    {'wan': 'missing'}, {'url': 'https://user:private@example.com/'},
    {'url': 'https://example.com:secret/'}, {'device': '8.8.8.8'},
    {'url': 'https://127.0.0.1/'}, {'protocols': ['vless']*4},
])
def test_rejects_invalid_target_and_never_echoes_private_input(service, fields):
    result = service.action('save', form(**fields))
    assert not result['success'] and not service.payload()['profiles']
    assert 'private' not in str(result) and 'secret' not in str(result)


def test_actual_kernel_wan_listing_does_not_accept_disabled_or_host_routes(tmp_path):
    route = tmp_path/'route'
    route.write_text('Iface Destination Gateway Flags RefCnt Use Metric Mask\n'
                     'eth1 00000000 01010101 0003 0 0 0 00000000\n'
                     'eth1 00000000 01010101 0003 0 0 5 00000000\n'
                     'eth2 00000000 01010101 0002 0 0 0 00000000\n'
                     'br0 0001A8C0 00000000 0001 0 0 0 00FFFFFF\n')
    assert available_wans(route, index=lambda name: 2) == ['eth1']
    assert available_wans(tmp_path/'missing') == []
    mem = tmp_path/'mem'
    mem.write_text('MemAvailable: 98303 kB\n')
    assert not memory_available(mem)
    mem.write_text('MemAvailable: 98304 kB\n')
    assert memory_available(mem)


def test_edited_stale_or_different_generation_result_not_recommended(service):
    service.action('save', form(label='<script>bad</script>'))
    profile = service.payload()['profiles'][0]
    result = {'generation': 3, 'checked_at': 1000, 'profile_fingerprint': profile_fingerprint(profile),
              'recommended_protocol': 'vless', 'windows': []}
    state = {'results': {profile['id']: result}}
    fresh = results_html([profile], state, generation=3, now=1010)
    assert 'Рекомендация: Vless 1' in fresh and '<script>bad' not in fresh
    assert '&lt;script&gt;' in fresh
    for generation, now in ((4, 1010), (3, 2000), (3, 999)):
        assert 'Рекомендация:' not in results_html([profile], state, generation=generation, now=now)
    assert 'Рекомендация:' not in results_html([dict(profile, wan='eth2')], state, generation=3, now=1010)


def test_web_dispatch_uses_existing_authenticated_action_contract(service):
    context = {'route_diagnostics_action': service.action,
               'route_diagnostics_payload': service.payload,
               'route_diagnostics_page': lambda: service.page('csrf')}
    assert web_get_actions.dispatch(context, '/route-diagnostics')['kind'] == 'html'
    assert web_get_actions.dispatch(context, '/api/route_diagnostics')['payload']['revision'] == 0
    assert web_post_actions.dispatch(context, '/route_diagnostics/save', form())['success']
    assert web_post_actions.dispatch(context, '/route_diagnostics/unknown', {}) is None


def test_corrupt_store_remains_untouched_and_page_explains_read_only_state(service):
    service.store.path.write_text('broken-private-content', encoding='utf-8')
    payload = service.payload()
    assert payload['read_only'] and payload['error']
    assert 'broken-private' not in service.page('csrf')
    assert not service.action('save', form())['success']
    assert service.store.path.read_text() == 'broken-private-content'
