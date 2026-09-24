import ast
import io
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest

APP = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(APP))
from youtube_stream_evidence import reply_counters, incoming_progress, defer_control_failure
from youtube_failover_runtime import attempt_youtube_failover


def flow(out_packets=20, out_bytes=20000, in_packets=10, in_bytes=600, state='ESTABLISHED'):
    return (f'ipv4 2 tcp 6 120 {state} src=192.168.1.50 dst=203.0.113.1 sport=50000 dport=443 '
            f'packets={out_packets} bytes={out_bytes} src=203.0.113.1 dst=192.168.1.50 '
            f'sport=10813 dport=50000 packets={in_packets} bytes={in_bytes} [ASSURED]')


def test_outgoing_retry_or_upload_and_ack_only_is_not_incoming_media():
    before = reply_counters(flow())
    after = reply_counters(flow(1000, 2000000, 990, 59400))
    assert not incoming_progress(after, before, minimum_bytes=8192)
    assert not incoming_progress(reply_counters(flow(1000, 2000000)), before, minimum_bytes=8192)


def test_old_cumulative_download_needs_a_new_receive_delta():
    before = reply_counters(flow(in_packets=1000, in_bytes=1000000))
    assert not incoming_progress(before, None, minimum_bytes=8192)
    assert not incoming_progress(before, before, minimum_bytes=8192)
    after = reply_counters(flow(in_packets=1020, in_bytes=1020000))
    assert incoming_progress(after, before, minimum_bytes=8192)
    assert not incoming_progress(before, after, minimum_bytes=8192)


@pytest.mark.parametrize('line', [flow(state='SYN_SENT'), flow(state='CLOSE_WAIT'), 'udp packets=3 bytes=1000', 'bad'])
def test_missing_direction_or_unestablished_tcp_does_not_guard(line):
    assert reply_counters(line) is None


def test_repeated_transient_error_cannot_skip_confirmation_forever():
    state = {}
    assert defer_control_failure(state, now=100)
    assert defer_control_failure(state, now=115)
    assert not defer_control_failure(state, now=130)
    assert not defer_control_failure(state, now=145)
    state = {}
    assert defer_control_failure(state, now=100)
    assert not defer_control_failure(state, now=146)


def test_bot_scan_separates_receive_evidence_from_general_traffic_guard():
    tree = ast.parse((APP/'bot.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_youtube_active_connection_count')
    state = {};now = [100];line = [flow()]
    env = {'YOUTUBE_STREAM_GUARD_ENABLED': True, 'YOUTUBE_STREAM_GUARD_SCAN_CACHE_SECONDS': 3,
        'YOUTUBE_STREAM_GUARD_MIN_PACKETS': 8, 'YOUTUBE_STREAM_GUARD_MIN_BYTES': 8192,
        '_youtube_protocol_conntrack_ports': lambda proto: {'10813'},
        '_youtube_stream_guard_state': lambda proto: state, 'time': SimpleNamespace(time=lambda: now[0]),
        'open': lambda *args, **kwargs: io.StringIO(line[0]),
        '_conntrack_packets_bytes': lambda text: (sum(map(int,re.findall(r'packets=(\d+)',text))),sum(map(int,re.findall(r'bytes=(\d+)',text)))),
        '_conntrack_identity': lambda text: 'one-connection', '_conntrack_tuple_summary': lambda text: {}}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'bot-scan', 'exec'), env)
    scan = env['_youtube_active_connection_count']
    assert scan('vless2') == 1  # Existing upload/general guard stays compatible.
    assert scan('vless2', require_downlink=True) == 0
    now[0] += 4;line[0] = flow(200, 200000, 100, 6000)
    assert scan('vless2', require_downlink=True) == 0
    now[0] += 4;line[0] = flow(200, 200000, 130, 40000)
    assert scan('vless2', require_downlink=True) == 1


def context(*, incoming=True, message='request timed out'):
    state = {'in_progress': False, 'last_fail': 0, 'consecutive_failures': 0}
    now = [100.0];events = [];locked = [False]
    names = re.findall(r'context\["(_[^\"]+)"\]', (APP/'youtube_failover_runtime.py').read_text())
    result = {name: (lambda *args, **kwargs: None) for name in names}
    def guard(*args, **kwargs):
        assert kwargs.get('require_downlink') is True
        return incoming() if callable(incoming) else incoming
    def reset(target, *, health_state='healthy', reason='', **kwargs):
        target.update(last_health_state=health_state, last_health_reason=reason)
        if health_state != 'failed':
            target.update(failure_deadline=0, hard_failure_confirmed_at=0)
    def confirm(*args, **kwargs):
        events.append('confirm');return False, message, 3, {}
    def pause(*args, **kwargs):
        events.append('pause');locked[0] = False;return 1, ''
    result.update({
        'YOUTUBE_ROUTE_EMERGENCY_CONNECT_TIMEOUT': 2, 'YOUTUBE_ROUTE_EMERGENCY_READ_TIMEOUT': 3,
        'YOUTUBE_ROUTE_EMERGENCY_DEADLINE_SECONDS': 120, 'YOUTUBE_ROUTE_HARD_FAILURE_CONFIRM_TTL_SECONDS': 30,
        'YOUTUBE_ROUTE_PROTOCOLS': ('vless2',), 'YOUTUBE_ROUTE_QUALITY_CONSECUTIVE_CHECKS': 3,
        'YOUTUBE_ROUTE_QUALITY_FAILOVER_ENABLED': False, 'YOUTUBE_ROUTE_QUALITY_MIN_DURATION_SECONDS': 60,
        'YOUTUBE_ROUTE_QUALITY_SCORE_THRESHOLD': 50, 'YOUTUBE_STREAM_GUARD_FAILOVER_HOLD_SECONDS': 45,
        'YOUTUBE_VLESS2_FAILOVER_ENABLED': True,
        '_youtube_route_protocol': lambda: 'vless2', '_youtube_failover_state': lambda proto: state,
        '_load_current_keys': lambda: {'vless2': 'fixture-current'}, '_hash_key': lambda key: key,
        '_check_youtube_protocol_once': lambda *args, **kwargs: (False, message),
        '_youtube_health_state': lambda *args: ('failed', message, {}),
        '_youtube_failure_is_hard_proxy_failure': lambda text: 'refused' in text,
        '_youtube_stream_guard_active': guard, '_reset_youtube_quality_state': reset,
        '_youtube_failover_policy': lambda: SimpleNamespace(remaining_seconds=lambda deadline, **kwargs: 0),
        '_confirm_youtube_key_emergency': confirm,
        '_handle_confirmed_youtube_hard_failure': lambda *args, **kwargs: events.append('recover') or True,
        '_pause_pool_probe_operation': pause,
        '_resume_cancelled_pool_probe': lambda *args, **kwargs: events.append('resume') or (True, 0),
        '_has_pool_probe_resume_payload': lambda: False,
        'pool_probe_lock': SimpleNamespace(locked=lambda: locked[0]),
        'shutdown_requested': SimpleNamespace(is_set=lambda: False),
        'time': SimpleNamespace(time=lambda: now[0]),
    })
    return result, state, now, events, locked


def test_single_control_timeout_preserves_incoming_video():
    ctx, state, now, events, locked = context(incoming=True)
    assert not attempt_youtube_failover(ctx)
    assert not events and state['transient_control_failures'] == 1


def test_repeated_errors_confirm_and_recover_when_incoming_progress_stops():
    incoming = [True]
    ctx, state, now, events, locked = context(incoming=lambda: incoming[0])
    for _ in range(2):
        assert not attempt_youtube_failover(ctx)
        now[0] += 15
    def confirm(*args, **kwargs):
        events.append('confirm');incoming[0] = False
        return False, 'request timed out', 3, {}
    ctx['_confirm_youtube_key_emergency'] = confirm
    assert attempt_youtube_failover(ctx)
    assert events == ['confirm', 'recover']


def test_other_incoming_route_traffic_cannot_hide_failed_youtube_confirmation():
    ctx, state, now, events, locked = context(incoming=True)
    for _ in range(2):
        assert not attempt_youtube_failover(ctx)
        now[0] += 15
    assert attempt_youtube_failover(ctx)
    assert events == ['confirm', 'recover'] and state['transient_control_failures'] == 0


def test_a_single_failed_endpoint_does_not_switch_when_group_confirms_health():
    ctx, state, now, events, locked = context(incoming=True)
    for _ in range(2):
        assert not attempt_youtube_failover(ctx)
        now[0] += 15
    ctx['_confirm_youtube_key_emergency'] = lambda *args, **kwargs: (True, 'ok', 2, {})
    ctx['_youtube_health_state'] = lambda ok, metrics: ('healthy' if ok else 'failed', '', {})
    assert not attempt_youtube_failover(ctx)
    assert events == [] and state['transient_control_failures'] == 0


def test_failed_route_pauses_pool_then_recovers_without_stream_false_positive():
    ctx, state, now, events, locked = context(incoming=False)
    locked[0] = True
    assert attempt_youtube_failover(ctx)
    assert events == ['pause', 'confirm', 'recover', 'resume']


def test_hard_proxy_failure_bypasses_stream_hold():
    ctx, state, now, events, locked = context(incoming=True, message='connection refused')
    assert attempt_youtube_failover(ctx)
    assert events == ['confirm', 'recover']
