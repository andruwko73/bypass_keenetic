"""Router status must remain responsive while a diagnostic command is slow."""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import router_health_runtime as health


@pytest.fixture
def runtime(monkeypatch):
    clock = [100.0]
    calls = []
    monkeypatch.setattr(health, 'read_proc_meminfo', lambda: {'MemTotal': 500000, 'MemAvailable': 200000})
    monkeypatch.setattr(health, 'process_rss_kb', lambda _pid: 70000)
    monkeypatch.setattr(health, 'read_proc_text', lambda _path: '')
    monkeypatch.setattr(health, 'read_flash_storage', lambda: {})
    monkeypatch.setattr(health, 'related_program_process_snapshot', lambda **_kw: {})
    monkeypatch.setattr(health, 'read_dns_health', lambda **_kw: {})
    monkeypatch.setattr(health, 'read_ndmc_system_snapshot', lambda: calls.append('ndmc') or {})
    instance = health.RouterHealthRuntime(cache_ttl=30, time_provider=lambda: clock[0])
    monkeypatch.setattr(instance, '_core_proxy_snapshot', lambda _now: {})
    return instance, clock, calls


@pytest.mark.parametrize('compact', [True, False])
def test_cpu_sampling_disabled_still_caches_payload(runtime, compact):
    instance, clock, calls = runtime
    first = instance.snapshot(None, compact=compact, sample_cpu=False)
    clock[0] += 10
    assert instance.snapshot(None, compact=compact, sample_cpu=False) == first
    assert calls == ['ndmc']
    clock[0] += 21
    instance.snapshot(None, compact=compact, sample_cpu=False)
    assert calls == ['ndmc', 'ndmc']
    instance.invalidate()
    instance.snapshot(None, compact=compact, sample_cpu=False)
    assert calls == ['ndmc', 'ndmc', 'ndmc']


def capture_workers(monkeypatch):
    workers = []
    real_thread = threading.Thread

    def factory(*args, **kwargs):
        worker = real_thread(*args, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr(health.threading, 'Thread', factory)
    return workers


def finish(workers):
    for worker in workers:
        worker.join(2)
        assert not worker.is_alive()


def test_slow_command_never_blocks_page_and_only_one_refresh_runs(runtime, monkeypatch):
    instance, clock, _calls = runtime
    entered, release = threading.Event(), threading.Event()
    workers = capture_workers(monkeypatch)

    def slow_snapshot(*_args, **_kwargs):
        entered.set()
        assert release.wait(3)
        return {'note': 'measured', 'xray_rss_kb': 32000}

    monkeypatch.setattr(instance, 'snapshot', slow_snapshot)
    try:
        cold = instance.web_snapshot(None, compact=True)
        assert entered.wait(1)
        for _ in range(100):
            pending = instance.web_snapshot(None)
            assert pending['health_refreshing'] and pending['health_sampled_at'] is None
        assert len(workers) == 1
        assert cold['health_stale'] and 'обновляется' in cold['note']
    finally:
        release.set()
        finish(workers)
    fresh = instance.web_snapshot(None)
    assert fresh['health_age_seconds'] == 0 and not fresh['health_stale']
    assert fresh['xray_rss_kb'] == 32000
    clock[0] += 31
    stale = instance.web_snapshot(None)
    finish(workers)
    assert stale['health_stale'] and stale['health_age_seconds'] == 31
    assert '31 с' in stale['note']


def test_invalidation_rejects_inflight_result(runtime, monkeypatch):
    instance, _clock, _calls = runtime
    entered, release = threading.Event(), threading.Event()
    workers = capture_workers(monkeypatch)

    def slow_snapshot(*_args, **_kwargs):
        entered.set()
        assert release.wait(3)
        return {'note': 'old route'}

    monkeypatch.setattr(instance, 'snapshot', slow_snapshot)
    try:
        instance.web_snapshot(None)
        assert entered.wait(1)
        instance.invalidate()
    finally:
        release.set()
        finish(workers)
    assert instance._web_cache['payload'] is None
    assert not instance._web_refreshing
    monkeypatch.setattr(instance, 'snapshot', lambda *_a, **_k: {'note': 'new route'})
    instance.web_snapshot(None)
    finish(workers)
    assert instance.web_snapshot(None)['note'] == 'new route'


def test_refresh_failure_retains_age_and_backs_off(runtime, monkeypatch):
    instance, clock, _calls = runtime
    workers = capture_workers(monkeypatch)
    instance._web_cache = {'timestamp': 50, 'payload': {'note': 'old sample'}}

    def fail(*_args, **_kwargs):
        raise TimeoutError('private command detail')

    monkeypatch.setattr(instance, 'snapshot', fail)
    instance.web_snapshot(None)
    finish(workers)
    result = instance.web_snapshot(None)
    assert result['health_refresh_failed'] and result['health_age_seconds'] == 50
    assert 'не удалось' in result['note'] and 'private' not in result['note']
    assert len(workers) == 1
    clock[0] += 5
    instance.web_snapshot(None)
    finish(workers)
    assert len(workers) == 2


def test_invalidation_rejects_inflight_heavy_cache(runtime):
    instance, _clock, _calls = runtime

    def loader():
        instance.invalidate()
        return {'old': True}

    instance._cached_payload('_dns_cache', 30, 100, loader)
    assert instance._dns_cache['payload'] is None
