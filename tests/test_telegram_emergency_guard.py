"""Run the real Telegram cycle and resource guard together, without a router."""
import ast
from pathlib import Path
import time

import pytest

SOURCE = ast.parse((Path(__file__).resolve().parents[1] / 'app/bot.py').read_text(encoding='utf-8'))


def compile_functions(names, env):
    for node in SOURCE.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<bot functions>', 'exec'), env)


@pytest.mark.parametrize('reason', ['pending failure', 'hard failure', 'Telegram polling stopped'])
def test_telegram_emergency_runs_above_normal_program_rss(reason):
    calls = []
    env = {'time': time, 'BACKGROUND_TASK_MAX_BOT_RSS_KB': 65*1024,
           'BACKGROUND_TASK_CRITICAL_MAX_BOT_RSS_KB': 70*1024,
           'BACKGROUND_TASK_MAX_PROGRAM_RSS_KB': 100*1024,
           'BACKGROUND_TASK_CRITICAL_MAX_PROGRAM_RSS_KB': 100*1024,
           'BACKGROUND_TASK_MAX_CPU_PERCENT': 80,
           'BACKGROUND_TASK_BUSY_BACKOFF_SECONDS': 180,
           'BACKGROUND_TASK_SKIP_LOG_INTERVAL_SECONDS': 900,
           'background_task_skip_until': {'Telegram auto-failover': time.time()+180},
           'background_task_skip_reason': {'Telegram auto-failover': 'program_rss'},
           'background_task_skip_log_at': {},
           '_update_maintenance_active': lambda: False,
           '_memory_sensitive_operation_running': lambda **kw: False,
           '_process_rss_kb': lambda: 78*1024,
           '_program_rss_kb': lambda: 120*1024,
           '_mem_available_kb_light': lambda: 170*1024,
           '_background_cpu_busy_percent': lambda: 5,
           '_write_runtime_log': lambda *a: None,
           '_memory_cleanup': lambda *a, **k: {'rss_after_kb': 78*1024},
           '_auto_failover_should_run': lambda: (True, reason),
           '_auto_failover_idle_log': lambda *a: None,
           '_attempt_auto_failover': lambda: calls.append('attempt') or True,
           '_run_coordinated_background_task': lambda name, fn: (True, fn())}
    compile_functions({'_background_task_rss_limit', '_background_task_program_rss_limit',
                       '_background_task_allowed', '_run_auto_failover_cycle'}, env)
    assert env['_run_auto_failover_cycle']()
    assert calls == ['attempt']
    assert not env['_background_task_allowed']('ordinary task')
    env['_mem_available_kb_light'] = lambda: 32*1024
    assert not env['_run_auto_failover_cycle']()
    assert calls == ['attempt']
    env['_mem_available_kb_light'] = lambda: 170*1024
    env['_update_maintenance_active'] = lambda: True
    assert not env['_run_auto_failover_cycle']()
    assert calls == ['attempt']


def test_healthy_polling_does_not_start_emergency():
    env = {'_auto_failover_should_run': lambda: (False, 'Telegram polling is healthy'),
           '_auto_failover_idle_log': lambda *a: None,
           '_background_task_allowed': lambda *a, **k: pytest.fail('healthy idle must not probe'),
           '_write_runtime_log': lambda *a: pytest.fail('unexpected failure')}
    compile_functions({'_run_auto_failover_cycle'}, env)
    assert not env['_run_auto_failover_cycle']()
