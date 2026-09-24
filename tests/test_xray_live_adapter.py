from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from xray_live_apply import (
    LiveApplyError, XrayApi, balancer_tag, managed_config, switch_prepared_outbound,
)


@pytest.fixture
def config():
    return {'inbounds': [{'tag': 'in-vless', 'protocol': 'socks', 'port': 10811}],
            'outbounds': [{'tag': 'proxy-vless', 'protocol': 'vless'},
                          {'tag': 'proxy-vless2', 'protocol': 'vless'},
                          {'tag': 'direct', 'protocol': 'freedom'}],
            'routing': {'domainStrategy': 'AsIs', 'rules': [
                {'type': 'field', 'inboundTag': ['in-vless'], 'outboundTag': 'proxy-vless'},
                {'type': 'field', 'domain': ['full:example.invalid'], 'outboundTag': 'proxy-vless2'},
            ]}}


def test_fixed_selectors_do_not_select_vless2_or_unverified_generation(config):
    original = deepcopy(config)
    value = managed_config(config, api_port=10899)
    assert config == original
    assert value['inbounds'][-1]['listen'] == '127.0.0.1'
    assert value['outbounds'][0]['protocol'] == 'blackhole'
    first, second = value['routing']['balancers']
    assert not second['selector'][0].startswith(first['selector'][0])
    assert not 'proxy-vless@g1.'.startswith(first['selector'][0])
    assert value['routing']['rules'][-1]['balancerTag'] == balancer_tag('proxy-vless')
    assert value['routing']['domainStrategy'] == 'AsIs'


@pytest.mark.parametrize('mutate', [
    lambda c: c.update(api={}),
    lambda c: c['routing'].update(balancers=[{'tag': 'foreign'}]),
    lambda c: c['outbounds'][0].update(proxySettings={'tag': 'proxy-vless2'}),
    lambda c: c['inbounds'][0].update(port='10899'),
    lambda c: c['outbounds'][0].update(tag='bypass-foreign'),
])
def test_config_migration_refuses_unsupported_topology(config, mutate):
    mutate(config)
    with pytest.raises(ValueError):
        managed_config(config, api_port=10899)


class FakeApi:
    def __init__(self, fault=None):
        self.handlers = {'proxy-vless@initial.': {}, 'independent': {}}
        self.selected = ''
        self.fault = fault
        self.calls = []

    def outbounds(self):
        return dict(self.handlers)

    def target(self, _):
        return self.selected

    def add(self, candidate):
        self.handlers[candidate['tag']] = candidate
        self.calls.append('add')
        if self.fault == 'add_response_lost':
            raise LiveApplyError('synthetic')

    def select(self, _, target):
        self.selected = target
        self.calls.append('select')
        if self.fault == 'select_response_lost':
            self.fault = None
            raise LiveApplyError('synthetic')

    def remove(self, tag):
        self.calls.append('remove')
        self.handlers.pop(tag, None)


def execute(api, *, verify=lambda: True, persist=lambda _: None, check=lambda: None,
            identity=lambda: 'boot:pid:start', checkpoint=lambda *_: None):
    return switch_prepared_outbound(
        api, logical_tag='proxy-vless', old_target='proxy-vless@initial.',
        candidate={'protocol': 'vless'}, generation=1, checkpoint=checkpoint,
        require_current=check, verify=verify, persist=persist,
        current_identity=identity, expected_identity='boot:pid:start',
    )


def test_success_keeps_old_handler_for_drain():
    api, checkpoints, saved = FakeApi(), [], []
    assert execute(api, checkpoint=lambda *v: checkpoints.append(v[0]), persist=saved.append) == 'proxy-vless@g1.'
    assert saved == ['proxy-vless@g1.']
    assert api.selected == 'proxy-vless@g1.'
    assert 'proxy-vless@initial.' in api.handlers
    assert 'independent' in api.handlers
    assert checkpoints == ['prepared', 'added', 'selected', 'verified']


@pytest.mark.parametrize('fault', ['add_response_lost', 'select_response_lost', 'health', 'disk'])
def test_failure_recovers_actual_state_without_restart(fault):
    api = FakeApi(fault)
    def persist(_):
        if fault == 'disk':
            raise OSError('synthetic')
    with pytest.raises(LiveApplyError, match='previous route restored'):
        execute(api, verify=lambda: fault != 'health', persist=persist)
    assert api.selected == ''
    assert set(api.handlers) == {'proxy-vless@initial.', 'independent'}
    assert 'restart' not in api.calls


def test_new_manual_intent_after_selection_rolls_back_before_persist():
    api, saved = FakeApi(), []
    def check():
        if api.selected:
            raise RuntimeError('superseded')
    with pytest.raises(LiveApplyError, match='previous route restored'):
        execute(api, check=check, persist=saved.append)
    assert saved == []
    assert api.selected == ''


def test_changed_process_during_verification_requires_recovery():
    api, identity, phases = FakeApi(), ['boot:pid:start'], []
    def verify():
        identity[0] = 'boot:pid:newstart'
        return True
    with pytest.raises(LiveApplyError, match='explicit recovery'):
        execute(api, identity=lambda: identity[0], verify=verify,
                checkpoint=lambda *v: phases.append(v[0]))
    assert phases[-1] == 'recovery_required'
    assert 'remove' not in api.calls


def test_api_failure_never_exposes_config_or_output(tmp_path):
    secret = 'synthetic-private-value'
    def fail(argv, **kwargs):
        assert all(secret not in value for value in argv)
        return subprocess.CompletedProcess(argv, 1, stdout=secret.encode(), stderr=secret.encode())
    api = XrayApi('xray', port=10899, directory=tmp_path, run=fail)
    with pytest.raises(LiveApplyError) as error:
        api.add({'protocol': 'vless', 'settings': {'secret': secret}})
    assert secret not in str(error.value)
    assert not list(tmp_path.iterdir())


def test_api_timeout_cleans_private_file(tmp_path):
    def fail(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 2)
    api = XrayApi('xray', port=10899, directory=tmp_path, run=fail)
    with pytest.raises(LiveApplyError):
        api.validate({'outbounds': []})
    assert not list(tmp_path.iterdir())
