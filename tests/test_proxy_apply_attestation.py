from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from proxy_apply_attestation import AttestationStore
from proxy_apply_plan import PlanAction, plan_proxy_apply


@pytest.fixture
def config():
    return {'inbounds': [{'tag': 'in', 'protocol': 'socks'}],
            'outbounds': [{'tag': 'proxy', 'protocol': 'vless'}], 'routing': {'rules': []}}


def loaded(store, config, generation=1, identity='boot:42:100'):
    store.record_loaded(config, process_identity=identity, generation=generation,
                        observed_fingerprint='observed-runtime')


def healthy(store, config, generation=1, identity='boot:42:100', protocol='vless'):
    return store.record_health(protocol, config=config, process_identity=identity,
                               generation=generation, observed_fingerprint='observed-runtime',
                               checked_at=100.0, healthy=True)


def decision(store, config, protocol='vless', generation=1, identity='boot:42:100'):
    return plan_proxy_apply(config, config, evidence=store.evidence(protocol, observed_fingerprint='observed-runtime'),
                            process_identity=identity, generation=generation, process_running=True, now=101).action


def test_file_or_loaded_receipt_alone_does_not_attest_health(tmp_path, config):
    store = AttestationStore(tmp_path / 'applied.json')
    assert not healthy(store, config)
    assert decision(store, config) == PlanAction.VERIFY_RUNTIME
    loaded(store, config)
    assert decision(store, config) == PlanAction.VERIFY_RUNTIME
    assert healthy(store, config)
    assert decision(store, config) == PlanAction.NOOP


def test_health_is_specific_to_route_and_current_process(tmp_path, config):
    store = AttestationStore(tmp_path / 'applied.json')
    loaded(store, config)
    healthy(store, config)
    assert decision(store, config, protocol='vless2') == PlanAction.VERIFY_RUNTIME
    assert decision(store, config, identity='boot:42:101') == PlanAction.VERIFY_RUNTIME
    assert store.evidence('vless', observed_fingerprint='external-api-change') is None


def test_old_background_result_cannot_attest_new_generation_a_b_a(tmp_path, config):
    store = AttestationStore(tmp_path / 'applied.json')
    loaded(store, config)
    healthy(store, config)
    loaded(store, config, generation=3)
    assert not healthy(store, config, generation=1)
    assert decision(store, config, generation=3) == PlanAction.VERIFY_RUNTIME
    assert healthy(store, config, generation=3)
    assert decision(store, config, generation=3) == PlanAction.NOOP


@pytest.mark.parametrize('raw', ['{', '{}', '[]', '{"schema":1,"health":[]}'])
def test_corrupted_marker_is_unknown(tmp_path, config, raw):
    path = tmp_path / 'applied.json'
    path.write_text(raw)
    assert decision(AttestationStore(path), config) == PlanAction.VERIFY_RUNTIME


def test_probe_failure_is_preserved(tmp_path, config):
    store = AttestationStore(tmp_path / 'applied.json')
    loaded(store, config)
    assert store.record_health('vless', config=config, process_identity='boot:42:100',
                               generation=1, observed_fingerprint='observed-runtime',
                               checked_at=100, healthy=False)
    assert decision(store, config) == PlanAction.RECOVER_RUNTIME
