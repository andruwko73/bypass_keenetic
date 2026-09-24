"""Apply decisions must never infer runtime state from a saved key or a port."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from proxy_apply_plan import (
    ChangeKind, PlanAction, RuntimeEvidence, classify_config_change,
    config_fingerprint, plan_proxy_apply,
)


@pytest.fixture
def config():
    return {
        'log': {'loglevel': 'warning'},
        'dns': {'servers': ['localhost']},
        'inbounds': [{'tag': 'in-vless', 'protocol': 'socks', 'port': 10811}],
        'outbounds': [
            {'tag': 'proxy-vless', 'protocol': 'vless', 'settings': {'test_key': 'synthetic-A'}},
            {'tag': 'proxy-vless2', 'protocol': 'vless', 'settings': {'test_key': 'synthetic-B'}},
            {'tag': 'direct', 'protocol': 'freedom'},
        ],
        'routing': {'domainStrategy': 'IPIfNonMatch', 'rules': [
            {'inboundTag': ['in-vless'], 'outboundTag': 'proxy-vless'},
            {'domain': ['full:example.invalid'], 'outboundTag': 'proxy-vless2'},
        ]},
    }


def evidence_for(config):
    digest = config_fingerprint(config)
    return RuntimeEvidence(digest, digest, 'boot:pid:start', 7, 100.0, True)


def plan(current, desired=None, **overrides):
    args = dict(evidence=evidence_for(current), process_identity='boot:pid:start',
                generation=7, process_running=True, now=110.0, max_health_age=30.0)
    args.update(overrides)
    return plan_proxy_apply(current, current if desired is None else desired, **args)


def test_healthy_unchanged_snapshot_is_noop_without_mutation(config):
    before = deepcopy(config)
    reordered_fields = dict(reversed(list(config.items())))
    result = plan(config, reordered_fields)
    assert result.change is ChangeKind.UNCHANGED
    assert result.action is PlanAction.NOOP
    assert config == before
    assert config_fingerprint(config) == config_fingerprint(reordered_fields)


@pytest.mark.parametrize('edit,kind,action', [
    (lambda c: c['outbounds'][0]['settings'].update(test_key='synthetic-new'),
     ChangeKind.OUTBOUND, PlanAction.PREPARE_OUTBOUND),
    (lambda c: c['routing']['rules'].reverse(), ChangeKind.ROUTING, PlanAction.PREPARE_ROUTING),
    (lambda c: c['routing'].update(balancers=[{'tag': 'choice', 'selector': ['proxy-']}]),
     ChangeKind.ROUTING, PlanAction.PREPARE_ROUTING),
    (lambda c: c['outbounds'].reverse(), ChangeKind.CORE, PlanAction.RESTART_REQUIRED),
    (lambda c: c['outbounds'].append({'tag': 'added', 'protocol': 'freedom'}),
     ChangeKind.CORE, PlanAction.RESTART_REQUIRED),
    (lambda c: c['inbounds'][0].update(port=10899), ChangeKind.CORE, PlanAction.RESTART_REQUIRED),
    (lambda c: c['dns'].update(servers=['192.0.2.1']), ChangeKind.CORE, PlanAction.RESTART_REQUIRED),
    (lambda c: c.update(api={'services': ['HandlerService']}), ChangeKind.CORE, PlanAction.RESTART_REQUIRED),
    (lambda c: c['routing'].update(domainStrategy='AsIs'), ChangeKind.CORE, PlanAction.RESTART_REQUIRED),
    (lambda c: c['routing'].update(futureOption=True), ChangeKind.CORE, PlanAction.RESTART_REQUIRED),
    (lambda c: c.update(futureOption=True), ChangeKind.CORE, PlanAction.RESTART_REQUIRED),
])
def test_changes_are_classified_conservatively(config, edit, kind, action):
    desired = deepcopy(config)
    edit(desired)
    before = deepcopy(desired)
    result = plan(config, desired)
    assert (result.change, result.action) == (kind, action)
    assert desired == before


def test_outbound_and_route_change_is_one_transaction(config):
    desired = deepcopy(config)
    desired['outbounds'][1]['settings']['test_key'] = 'synthetic-C'
    desired['routing']['rules'][0]['outboundTag'] = 'proxy-vless2'
    assert plan(config, desired).action is PlanAction.PREPARE_TRANSACTION


@pytest.mark.parametrize('overrides', [
    {'evidence': None}, {'process_running': None}, {'process_running': 1},
    {'process_identity': 'boot:pid:new-start'}, {'process_identity': ''},
    {'generation': 8}, {'generation': True}, {'generation': -1},
])
def test_same_saved_config_with_missing_or_changed_runtime_is_not_noop(config, overrides):
    assert plan(config, **overrides).action is PlanAction.VERIFY_RUNTIME


@pytest.mark.parametrize('changes', [
    {'applied_fingerprint': 'other'}, {'verified_fingerprint': 'other'},
    {'generation': 6}, {'generation': True}, {'healthy': None}, {'healthy': 1},
    {'checked_at': 79.99}, {'checked_at': 110.01},
    {'checked_at': float('nan')}, {'checked_at': float('inf')},
    {'checked_at': '100'},
])
def test_untrusted_stale_or_unknown_health_cannot_skip_application(config, changes):
    e = replace(evidence_for(config), **changes)
    assert plan(config, evidence=e).action is PlanAction.VERIFY_RUNTIME


def test_failed_current_health_requests_recovery_not_noop_or_automatic_restart(config):
    assert plan(config, process_running=False).action is PlanAction.RECOVER_RUNTIME
    failed = replace(evidence_for(config), healthy=False)
    assert plan(config, evidence=failed).action is PlanAction.RECOVER_RUNTIME
    # Failure from a superseded intent does not authorize recovery of a new one.
    assert plan(config, evidence=failed, generation=8).action is PlanAction.VERIFY_RUNTIME


def test_health_age_boundary_and_a_b_a_generation(config):
    assert plan(config, now=130).action is PlanAction.NOOP
    assert plan(config, now=130.001).action is PlanAction.VERIFY_RUNTIME
    assert plan(config, generation=9).action is PlanAction.VERIFY_RUNTIME


@pytest.mark.parametrize('field,value', [('now', float('nan')), ('now', True),
                                      ('max_health_age', -1), ('max_health_age', float('inf'))])
def test_invalid_freshness_policy_is_rejected(config, field, value):
    with pytest.raises(ValueError, match='freshness'):
        plan(config, **{field: value})


@pytest.mark.parametrize('edit', [
    lambda c: c.update(outbounds=[]),
    lambda c: c['outbounds'][1].update(tag='proxy-vless'),
    lambda c: c['outbounds'][0].pop('tag'),
    lambda c: c['inbounds'][0].update(protocol=''),
    lambda c: c['routing'].update(rules=None),
    lambda c: c.update(routing=[]),
    lambda c: c.update(secret=float('nan')),
    lambda c: c.update(secret=float('inf')),
    lambda c: c.update(secret=object()),
    lambda c: c.update({9: 'synthetic-private'}),
])
def test_malformed_configuration_is_rejected_without_echoing_values(config, edit):
    edit(config)
    with pytest.raises(ValueError) as error:
        plan(config)
    assert 'synthetic' not in str(error.value)


def test_json_types_are_not_confused(config):
    desired = deepcopy(config)
    config['futureFlag'] = 1
    desired['futureFlag'] = True
    assert classify_config_change(config, desired) is ChangeKind.CORE


def test_plan_and_evidence_repr_do_not_expose_config_fingerprints_or_keys(config):
    e = evidence_for(config)
    result = plan(config)
    output = repr(result) + repr(e)
    assert 'synthetic-A' not in output
    assert e.applied_fingerprint not in output
    assert e.process_identity not in output
