"""Exercise production scheduler callers together with their real admission guard."""
import ast
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import background_policy
import subscription_runtime
import subscription_refresh_runtime

SOURCE = ast.parse((ROOT / 'app/bot.py').read_text(encoding='utf-8'))


@pytest.fixture
def scheduler(tmp_path):
    clock = [time.mktime((2026, 9, 29, 12, 0, 0, 0, 0, -1))]
    resources = {'bot': 80 * 1024, 'program': 120 * 1024, 'available': 175 * 1024,
                 'cpu': 5, 'load': .1, 'busy': False, 'maintenance': False}
    path = tmp_path / 'nightly.json'
    logs, starts = [], []

    def read_json(path, default):
        return json.loads(Path(path).read_text()) if Path(path).exists() else default

    def write_json(path, data):
        Path(path).write_text(json.dumps(data))

    env = dict(time=SimpleNamespace(time=lambda: clock[0], localtime=time.localtime, strftime=time.strftime),
               re=re, config=SimpleNamespace(), background_policy=background_policy,
               background_task_skip_until={}, background_task_skip_reason={}, background_task_skip_log_at={},
               background_task_skip_details={}, subscription_auto_refresh_skip_log_at={},
               background_task_coordinator_lock=threading.Lock(), background_task_coordinator_state={},
               pool_probe_lock=threading.Lock(), shutdown_requested=threading.Event(),
               BACKGROUND_TASK_MAX_BOT_RSS_KB=65*1024, BACKGROUND_TASK_CRITICAL_MAX_BOT_RSS_KB=70*1024,
               BACKGROUND_TASK_MAX_PROGRAM_RSS_KB=100*1024, BACKGROUND_TASK_CRITICAL_MAX_PROGRAM_RSS_KB=100*1024,
               BACKGROUND_TASK_MAX_CPU_PERCENT=45, BACKGROUND_TASK_BUSY_BACKOFF_SECONDS=180,
               BACKGROUND_TASK_SKIP_LOG_INTERVAL_SECONDS=900,
               SUBSCRIPTION_AUTO_REFRESH_ENABLED=True, SUBSCRIPTION_STATE_PATH=str(tmp_path/'sources.json'),
               SUBSCRIPTION_AUTO_REFRESH_MAX_BOT_RSS_KB=80*1024,
               SUBSCRIPTION_AUTO_REFRESH_MAX_PROGRAM_RSS_KB=110*1024,
               SUBSCRIPTION_AUTO_REFRESH_MIN_AVAILABLE_KB=90*1024,
               SUBSCRIPTION_AUTO_REFRESH_MAX_CPU_PERCENT=80, SUBSCRIPTION_AUTO_REFRESH_MAX_LOAD1=2.5,
               SUBSCRIPTION_NIGHTLY_POOL_PROBE_ENABLED=True, SUBSCRIPTION_NIGHTLY_POOL_PROBE_START_HOUR=3,
               SUBSCRIPTION_NIGHTLY_POOL_PROBE_END_HOUR=6, SUBSCRIPTION_NIGHTLY_POOL_PROBE_MAX_REFRESH_AGE_SECONDS=28800,
               SUBSCRIPTION_NIGHTLY_POOL_PROBE_STATE_PATH=str(path), _NIGHTLY_POOL_PROBE_RETRY_BACKOFF_SECONDS=300,
               _update_maintenance_active=lambda: resources['maintenance'],
               _memory_sensitive_operation_running=lambda **kw: resources['busy'],
               _process_rss_kb=lambda: resources['bot'], _program_rss_kb=lambda: resources['program'],
               _mem_available_kb_light=lambda: resources['available'],
               _background_cpu_busy_percent=lambda: resources['cpu'], _pool_probe_load_average=lambda: resources['load'],
               _memory_cleanup=lambda *a, **kw: {'rss_after_kb': resources['bot']},
               _write_runtime_log=logs.append, _app_mode_pool_enabled=lambda: True,
               _subscription_runtime=lambda: subscription_runtime,
               _has_pool_probe_resume_payload=lambda: False,
               _read_json_file=read_json, _write_json_file=write_json,
               _pool_summary_count=lambda state, key: int(state.get(key) or 0))

    def start(**kwargs):
        starts.append(kwargs)
        env['pool_probe_lock'].acquire()
        return True, 12

    env['_probe_all_pool_keys_async'] = start
    names = {'_background_task_rss_limit', '_background_task_program_rss_limit', '_background_task_allowed',
             '_subscription_auto_refresh_allowed', '_log_subscription_auto_refresh_skip',
             '_run_coordinated_background_task', '_run_subscription_auto_refresh_cycle', '_refresh_subscription_once',
             '_nightly_subscription_pool_probe_state', '_write_nightly_subscription_pool_probe_state',
             '_defer_nightly_subscription_pool_probe', '_mark_nightly_subscription_pool_probe_started',
             '_mark_nightly_subscription_pool_probe_finished', '_maybe_start_nightly_subscription_pool_probe',
             '_scheduled_checks_status'}
    for node in SOURCE.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<production bot>', 'exec'), env)
    return SimpleNamespace(env=env, clock=clock, resources=resources, path=path, starts=starts, logs=logs)


@pytest.mark.parametrize('bot,program', [(68.5,94.5), (74.16,115.12), (77.76,116.2), (90,140)])
def test_real_callers_admit_steady_rss_and_single_pool(scheduler, bot, program):
    s = scheduler
    s.resources.update(bot=int(bot*1024), program=int(program*1024))
    assert s.env['_subscription_auto_refresh_allowed']('vless')
    assert s.env['_background_task_allowed']('status refresh', task_class='normal')
    assert s.env['_maybe_start_nightly_subscription_pool_probe']({})
    assert not s.env['_maybe_start_nightly_subscription_pool_probe']({})
    assert s.starts == [dict(stale_only=False, max_keys=None, scope='nightly_subscription')]


@pytest.mark.parametrize('field,value,reason', [('available', 0, 'memory_unknown'), ('available', 32*1024, 'memory'),
                                             ('cpu', 95, 'cpu'), ('load', 5, 'load'), ('busy', True, 'busy'),
                                             ('maintenance', True, 'maintenance')])
def test_pressure_defers_then_recovers_without_consuming_attempt(scheduler, field, value, reason):
    s = scheduler
    original = s.resources[field]
    s.resources[field] = value
    assert not s.env['_subscription_auto_refresh_allowed']('vless')
    assert not s.env['_maybe_start_nightly_subscription_pool_probe']({})
    assert s.env['background_task_skip_reason']['Nightly subscription pool probe'] == reason
    assert json.loads(s.path.read_text())['attempts'] == 0
    s.resources[field] = original
    s.clock[0] += 901
    assert s.env['_subscription_auto_refresh_allowed']('vless')
    assert s.env['_maybe_start_nightly_subscription_pool_probe']({})
    assert len(s.starts) == 1


def test_task_workspace_budgets_and_custom_limits(scheduler):
    s = scheduler
    s.resources['available'] = 110*1024
    assert s.env['_background_task_allowed']('status refresh')
    assert s.env['_subscription_auto_refresh_allowed']('vless')
    assert not s.env['_maybe_start_nightly_subscription_pool_probe']({})
    s.resources['available'] = 175*1024
    s.env['SUBSCRIPTION_AUTO_REFRESH_MAX_BOT_RSS_KB'] = 79*1024
    s.clock[0] += 901
    assert not s.env['_subscription_auto_refresh_allowed']('vless')
    assert s.env['background_task_skip_reason']['Subscription auto refresh'] == 'rss'
    s.env['SUBSCRIPTION_AUTO_REFRESH_MAX_BOT_RSS_KB'] = 80*1024
    s.env['config'].scheduled_task_memory_policy = 'rss'
    s.clock[0] += 901
    assert not s.env['_subscription_auto_refresh_allowed']('vless')
    assert s.env['background_task_skip_reason']['Subscription auto refresh'] == 'program_rss'
    assert not s.env['_background_task_allowed']('ordinary', task_class='critical')


def test_days_of_pending_work_coalesce_and_completed_run_does_not_repeat(scheduler):
    s = scheduler
    s.path.write_text(json.dumps({'schema': 3, 'window_date': '2026-09-27', 'status': 'pending',
                                 'pending_since': s.clock[0]-2*86400, 'attempts': 0}))
    assert s.env['_maybe_start_nightly_subscription_pool_probe']({})
    state = json.loads(s.path.read_text())
    assert state['window_date'] == '2026-09-29'
    assert state['pending_since'] == s.clock[0]-2*86400
    s.env['pool_probe_lock'].release()
    s.env['_mark_nightly_subscription_pool_probe_finished'](
        status='completed', checked=12, total=12, started_at=s.clock[0], finished_at=s.clock[0]+30)
    s.clock[0] += 901
    assert not s.env['_maybe_start_nightly_subscription_pool_probe']({})
    # Simulate process-local state discarded after restart; durable state is enough.
    s.env['background_task_skip_until'].clear()
    assert not s.env['_maybe_start_nightly_subscription_pool_probe']({})
    assert len(s.starts) == 1


def test_auto_cycle_checks_subscriptions_before_pool_even_when_fetch_fails(scheduler):
    s = scheduler
    records = {'vless': {'url': 'https://example.invalid/sub', 'hwid_enabled': True}}
    s.env['_load_subscription_state'] = lambda: records
    s.env['_subscription_refresh_due'] = lambda *_: True
    calls = []

    def fetch(*_args, **_kwargs):
        calls.append('refresh')
        return {}, 'simulated timeout'  # Network error; saved pool must still be checked.

    s.env.update(
        subscription_operation_lock=threading.Lock(),
        _subscription_refresh_runtime=lambda: subscription_refresh_runtime,
        _subscription_record=lambda *a, **kw: records['vless'],
        _fetch_keys_from_subscription=fetch,
        _add_subscription_keys_to_pool=lambda *a, **kw: pytest.fail('failed fetch must not change pool'),
        _update_subscription_record=lambda *a, **kw: calls.append('recorded'),
    )
    s.env['_run_subscription_auto_refresh_cycle']()
    assert calls == ['refresh', 'recorded'] and len(s.starts) == 1


def test_interrupted_run_retains_progress_for_resume(scheduler):
    s = scheduler
    s.path.write_text(json.dumps({'schema': 3, 'window_date': '2026-09-27', 'status': 'running',
                                 'checked': 5, 'total': 12, 'started_at': s.clock[0]-300, 'attempts': 1}))
    s.env['_has_pool_probe_resume_payload'] = lambda: True
    assert not s.env['_maybe_start_nightly_subscription_pool_probe']({})
    assert json.loads(s.path.read_text())['status'] == 'paused'
    s.clock[0] += 301
    s.env['_resume_cancelled_pool_probe'] = lambda *_: (True, 7)
    assert s.env['_maybe_start_nightly_subscription_pool_probe']({})
    state = json.loads(s.path.read_text())
    assert state['checked'] == 5 and state['total'] == 12 and state['attempts'] == 1


def test_public_status_distinguishes_runs_and_deferral():
    lines = background_policy.status_lines(
        {'status': 'pending', 'reason': 'Недостаточно памяти.', 'next_retry_at': 300},
        {'status': 'completed', 'finished_at': 100}, {'status': 'failed', 'finished_at': 200},
        [{'last_success_at': 50, 'last_attempt_at': 60}], time_text=str, reason='memory',
        details={'available_kb': 100*1024, 'required_available_kb': 106*1024}, retry_at=300)
    assert 'Ручная проверка: завершена' in lines['manual']
    assert 'Автоматическая проверка: ошибка' in lines['automatic']
    assert 'Доступно 100 МиБ' in lines['subscriptions']
    assert '300' in lines['queue']


def test_public_running_progress_advances_without_state_file_write(scheduler, tmp_path):
    s = scheduler
    s.path.write_text(json.dumps({'schema': 3, 'status': 'running', 'window_date': '2026-09-29',
                                 'checked': 0, 'total': 139, 'started_at': s.clock[0]}))
    progress = {'running': True, 'scope': 'nightly_subscription', 'checked': 28, 'total': 139}
    reads = []
    s.env.update(os=os, _POOL_SUMMARY_LAST_PATH=str(tmp_path/'summary.json'), scheduled_checks_view_cache={},
                 _get_pool_probe_progress=lambda: dict(progress),
                 _load_subscription_state=lambda: reads.append(True) or {})
    before = s.path.read_bytes()
    lines = s.env['_scheduled_checks_status']()
    assert '28 из 139' in lines['queue']
    assert s.env['_scheduled_checks_status']() == lines and len(reads) == 1
    progress['checked'] = 29
    assert '29 из 139' in s.env['_scheduled_checks_status']()['queue']
    assert len(reads) == 2 and s.path.read_bytes() == before


@pytest.mark.parametrize('status,running,scope', [('running', True, 'protocol'),
                                               ('running', False, 'nightly_subscription'),
                                               ('paused', True, 'nightly_subscription')])
def test_public_nightly_progress_does_not_use_another_run(scheduler, tmp_path, status, running, scope):
    s = scheduler
    s.path.write_text(json.dumps({'schema': 3, 'status': status, 'window_date': '2026-09-29',
                                 'checked': 5, 'total': 12, 'started_at': s.clock[0]}))
    s.env.update(os=os, _POOL_SUMMARY_LAST_PATH=str(tmp_path/'summary.json'), scheduled_checks_view_cache={},
                 _get_pool_probe_progress=lambda: dict(running=running, scope=scope, checked=9, total=10),
                 _load_subscription_state=lambda: {})
    assert '5 из 12' in s.env['_scheduled_checks_status']()['queue']
