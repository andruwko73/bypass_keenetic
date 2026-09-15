"""Repeated reads must not retain every historical payload in the bot."""
import gc
import sys
import weakref
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import router_health_runtime as health
import router_metrics as metrics


def test_metrics_history_and_pid_state_stay_bounded(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(metrics, 'read_loadavg', lambda: (0.1, 0.2, 0.3))
    monkeypatch.setattr(metrics, 'read_system_ticks', lambda: int(clock[0] * 100))
    monkeypatch.setattr(metrics, 'find_pid_by_cmdline', lambda _m: 42)
    monkeypatch.setattr(metrics, 'pid_matches_cmdline', lambda *_a: True)
    monkeypatch.setattr(metrics, 'process_ticks', lambda _p: int(clock[0]))
    monkeypatch.setattr(metrics, 'process_rss_kb', lambda _p: 30000)
    runtime = metrics.RouterMetricsRuntime(time_provider=lambda: clock[0])
    for _ in range(10000):
        clock[0] += 1
        runtime.snapshot()
        runtime.snapshot(include_history=False)
    assert len(runtime._history) == 120
    assert len(runtime._previous) == 2
    assert len(runtime._pid_cache) == 1
    assert runtime._history[-1]['timestamp'] == clock[0]
    assert runtime._history[0]['timestamp'] == clock[0] - 119


def test_heavy_cache_releases_replaced_payloads():
    class Marker:
        pass

    runtime = health.RouterHealthRuntime()
    references = []
    for i in range(500):
        marker = Marker()
        references.append(weakref.ref(marker))
        runtime._cached_payload('_dns_cache', 0, i, lambda: {'marker': marker})
    del marker
    gc.collect()
    assert sum(ref() is not None for ref in references) == 1
    runtime.invalidate()
    gc.collect()
    assert all(ref() is None for ref in references)
