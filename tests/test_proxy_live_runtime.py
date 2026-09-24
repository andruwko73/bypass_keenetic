from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from proxy_apply_coordinator import ApplyCoordinator
from proxy_live_runtime import ProxyLiveRuntime
from xray_live_apply import LiveApplyError


class Api:
    def __init__(self):
        self.handlers, self.overrides, self.calls = {}, {}, []

    def load(self, config):
        self.handlers = {item['tag']: item for item in config['outbounds']}
        self.overrides = {item['tag']: '' for item in config['routing']['balancers']}

    def outbounds(self):
        return self.handlers

    def observation(self, _):
        return self.fingerprint(self.snapshot(_))

    def snapshot(self, _):
        return deepcopy({'outbounds': self.handlers, 'targets': self.overrides})

    @staticmethod
    def fingerprint(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    def validate(self, config):
        self.calls.append('validate')

    def target(self, tag):
        return self.overrides[tag]

    def add(self, value):
        self.calls.append('add')
        assert value['tag'] not in self.handlers
        self.handlers[value['tag']] = value

    def select(self, balancer, tag):
        self.calls.append('select')
        self.overrides[balancer] = tag

    def remove(self, tag):
        self.calls.append('remove')
        self.handlers.pop(tag)


@pytest.fixture
def setup(tmp_path):
    private, ram = tmp_path / 'private', tmp_path / 'ram'
    private.mkdir()
    ram.mkdir()
    path, key = tmp_path / 'config.json', tmp_path / 'key'
    key.write_text('old-key\n')
    coordinator = ApplyCoordinator(ram)
    api, identity = Api(), ['boot:42:100']
    runtime = ProxyLiveRuntime(
        coordinator=coordinator, directory=private, ram_directory=ram, config_path=path,
        key_paths={'vless': key}, binary='unused', identity=lambda: identity[0],
        allowed_protocols=('vless',), api=api, clock=lambda: 100.0,
    )
    config = {'inbounds': [{'protocol': 'socks', 'tag': 'in', 'port': 10811}],
              'outbounds': [{'protocol': 'vless', 'tag': 'proxy-vless', 'settings': {'synthetic': 'old-key'}}],
              'routing': {'rules': [{'type': 'field', 'inboundTag': ['in'], 'outboundTag': 'proxy-vless'}]}}
    cold = runtime.config_for_load(config)
    path.write_text(json.dumps(cold))
    api.load(cold)
    with coordinator.lock:
        runtime.register_controlled_load(config, previous_identity=None, generation=0)
    return runtime, config, identity


def apply(runtime, current, key='new-key', *, verify=lambda: True, precheck=lambda: True):
    desired = deepcopy(current)
    desired['outbounds'][0]['settings']['synthetic'] = key
    ticket = runtime.coordinator.request_manual()
    with runtime.coordinator.transaction(ticket, manual=True) as accepted:
        result = runtime.try_apply('vless', key, current=current, desired=desired,
                                   ticket=accepted, verify=verify, precheck=precheck)
    return result, desired


def test_confirmed_hot_apply_persists_consistent_files_and_evidence(setup):
    runtime, config, _ = setup
    result, desired = apply(runtime, config)
    assert result == 'hot'
    receipt = runtime._receipt()
    assert receipt['logical'] == desired
    assert receipt['targets']['proxy-vless'] == 'proxy-vless@g1.'
    assert runtime.key_paths['vless'].read_text() == 'new-key\n'
    assert json.loads(runtime.config_path.read_text()) == runtime.config_for_load(desired)
    assert not runtime.bundle.pending()
    assert not runtime.pending_path.exists()
    assert runtime.attestation.evidence('vless', observed_fingerprint=receipt['observed']).healthy is True
    assert 'proxy-vless@initial.' in runtime.api.handlers


def test_unchanged_key_requires_data_check_then_reuses_fresh_evidence(setup):
    runtime, config, _ = setup
    before = runtime.receipt_path.read_bytes()
    calls = []
    def verify():
        calls.append('data')
        return True
    assert apply(runtime, config, 'old-key', verify=verify)[0] == 'noop'
    assert apply(runtime, config, 'old-key', verify=verify)[0] == 'noop'
    assert calls == ['data']
    assert runtime.receipt_path.read_bytes() == before
    assert runtime.api.calls == []


def test_unhealthy_unchanged_key_never_causes_automatic_restart(setup):
    runtime, config, _ = setup
    assert apply(runtime, config, 'old-key', verify=lambda: False)[0] == 'unhealthy'
    assert runtime.api.calls == []
    assert runtime.key_paths['vless'].read_text() == 'old-key\n'


@pytest.mark.parametrize('failure', ['precheck', 'health', 'write'])
def test_failed_candidate_preserves_key_config_and_receipt(setup, monkeypatch, failure):
    runtime, config, _ = setup
    originals = {p: p.read_bytes() for p in (runtime.config_path, runtime.receipt_path, runtime.key_paths['vless'])}
    if failure == 'write':
        def fail():
            raise OSError('injected before file commit')
        monkeypatch.setattr(runtime.bundle, 'commit', fail)
    with pytest.raises(LiveApplyError):
        apply(runtime, config, verify=lambda: failure != 'health', precheck=lambda: failure != 'precheck')
    assert all(p.read_bytes() == data for p, data in originals.items())
    assert 'proxy-vless@g1.' not in runtime.api.handlers
    assert not runtime.pending_path.exists()
    assert runtime._observe(runtime._receipt()['targets']) == runtime._receipt()['observed']
    if failure != 'write':
        assert apply(runtime, config)[0] == 'hot'


def test_external_api_change_blocks_apply_without_cold_fallback(setup):
    runtime, config, _ = setup
    runtime.api.handlers['external'] = {'protocol': 'freedom'}
    with pytest.raises(LiveApplyError, match='outside the coordinator'):
        apply(runtime, config)
    assert runtime.api.calls == []


def test_stale_process_blocks_apply_without_cold_fallback(setup):
    runtime, config, identity = setup
    identity[0] = 'boot:42:101'
    with pytest.raises(LiveApplyError, match='not attested'):
        apply(runtime, config)
    assert runtime.api.calls == []


def test_generation_limit_defers_without_removing_live_handlers(setup):
    runtime, config, _ = setup
    runtime.max_retained = 1
    _, current = apply(runtime, config)
    calls = list(runtime.api.calls)
    with pytest.raises(LiveApplyError, match='budget reached'):
        apply(runtime, current, key='third-key')
    assert runtime.api.calls == calls
    assert len(runtime.api.handlers) == 3  # guard, original, current


def test_planned_reload_recovers_generation_floor_and_invalidates_health(setup):
    runtime, config, identity = setup
    _, desired = apply(runtime, config)
    previous = identity[0]
    identity[0] = 'boot:42:200'
    runtime.api.load(runtime.config_for_load(desired))
    with runtime.coordinator.lock:
        runtime.recover_files_before_startup()
        floor = runtime.coordinator.capture().generation
        runtime.register_controlled_load(desired, previous_identity=previous, generation=floor)
    assert floor > 1
    assert runtime._receipt()['retained'] == []
    assert runtime.attestation.evidence('vless', observed_fingerprint=runtime._receipt()['observed']).healthy is None
    result, _ = apply(runtime, desired, key='third-key')
    assert result == 'hot'


def test_pending_file_recovery_precedes_receipt_replacement(setup):
    runtime, config, identity = setup
    before = runtime.receipt_path.read_bytes()
    runtime.bundle.prepare({runtime.key_paths['vless']: b'pending'})
    identity[0] = 'boot:42:200'
    with runtime.coordinator.lock, pytest.raises(LiveApplyError, match='recovery must precede'):
        runtime.register_controlled_load(config, previous_identity='boot:42:100', generation=1)
    assert runtime.receipt_path.read_bytes() == before


def test_new_manual_intent_during_probe_cancels_candidate_before_add(setup):
    runtime, config, _ = setup
    def precheck():
        runtime.coordinator.request_manual()
        return True
    from proxy_apply_coordinator import StaleApply
    with pytest.raises(StaleApply):
        apply(runtime, config, precheck=precheck)
    assert runtime.api.calls == ['validate']
    assert not runtime.pending_path.exists()


def test_qualified_detach_bounds_manager_handlers_over_repeated_applies(setup):
    runtime, config, _ = setup
    runtime.detach_qualified = True
    for index in range(12):
        result, config = apply(runtime, config, key='synthetic-key-' + str(index))
        assert result == 'hot'
        assert len(runtime.api.handlers) == 2  # permanent guard + selected
        assert runtime._receipt()['retained'] == []
        assert not runtime.pending_path.exists()


@pytest.mark.parametrize('failure', ['lost_reply', 'failed_remove', 'external_change', 'receipt_write'])
def test_detach_failure_never_rolls_back_committed_key(setup, monkeypatch, failure):
    runtime, config, _ = setup
    runtime.detach_qualified = True
    original = runtime.api.remove
    def remove(tag):
        if failure == 'failed_remove':
            raise LiveApplyError('synthetic removal failure')
        original(tag)
        if failure == 'external_change':
            runtime.api.handlers['foreign'] = {'protocol': 'freedom'}
        if failure == 'lost_reply':
            raise LiveApplyError('synthetic lost reply')
        if failure == 'receipt_write':
            import proxy_live_runtime
            atomic = proxy_live_runtime._atomic_json
            def fail(path, value):
                if path == runtime.receipt_path:
                    raise OSError('synthetic write failure')
                return atomic(path, value)
            monkeypatch.setattr(proxy_live_runtime, '_atomic_json', fail)
    monkeypatch.setattr(runtime.api, 'remove', remove)
    result, desired = apply(runtime, config)
    assert result == ('hot' if failure == 'lost_reply' else 'hot_cleanup_pending')
    assert runtime.key_paths['vless'].read_text() == 'new-key\n'
    assert runtime.api.target('bypass-choice-proxy-vless') == 'proxy-vless@g1.'
    assert runtime.pending_path.exists() == (failure != 'lost_reply')
    if failure != 'lost_reply':
        with pytest.raises(LiveApplyError, match='earlier transaction'):
            apply(runtime, desired, key='another-key')


@pytest.mark.parametrize('failed_commit', [False, True])
def test_pool_metadata_uses_latest_snapshot_and_commits_with_key(setup, monkeypatch, failed_commit):
    import threading
    runtime, config, _ = setup
    pool = runtime.directory / 'pool.json'
    pool.write_text(json.dumps(['existing']))
    runtime.bundle.allowed.add(str(pool.absolute()))
    runtime.metadata_lock = threading.RLock()
    def metadata(proto, key):
        values = json.loads(pool.read_text())
        return {pool: json.dumps([*values, key]).encode()}
    runtime.metadata_updates = metadata
    def precheck():
        # Subscription/manual import completed during the network check. Its
        # unrelated addition must survive both success and commit rollback.
        pool.write_text(json.dumps(['existing', 'independent-import']))
        return True
    if failed_commit:
        original = runtime.bundle._write
        def write(item, value):
            if item['path'] == str(pool.absolute()) and b'new-key' in (value or b''):
                raise OSError('synthetic full disk at metadata write')
            return original(item, value)
        monkeypatch.setattr(runtime.bundle, '_write', write)
        with pytest.raises(LiveApplyError):
            apply(runtime, config, precheck=precheck)
    else:
        assert apply(runtime, config, precheck=precheck)[0] == 'hot'
    assert json.loads(pool.read_text()) == ['existing', 'independent-import'] + ([] if failed_commit else ['new-key'])
    assert runtime.key_paths['vless'].read_text() == ('old-key\n' if failed_commit else 'new-key\n')


def test_resource_and_rate_budgets_do_not_mutate_runtime(setup):
    runtime, config, _ = setup
    runtime.resource_guard = lambda: False
    with pytest.raises(LiveApplyError, match='resource budget'):
        apply(runtime, config)
    assert runtime.api.calls == []
    runtime.resource_guard = lambda: True
    runtime.max_attempts_per_minute = 1
    _, current = apply(runtime, config)
    calls = list(runtime.api.calls)
    with pytest.raises(LiveApplyError, match='rate budget'):
        apply(runtime, current, key='third-key')
    assert runtime.api.calls == calls
    # A confirmed no-op does not spend the candidate budget.
    assert apply(runtime, current)[0] == 'noop'
    runtime.clock = lambda: 161.0
    assert apply(runtime, current, key='third-key')[0] == 'hot'
