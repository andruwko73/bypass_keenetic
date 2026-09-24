"""Kernel lock failure recovery and generation arbitration, without a router."""
import multiprocessing
import os
from pathlib import Path
import sys
import threading
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from proxy_apply_coordinator import (
    ApplyBusy, ApplyCoordinator, ProcessRLock, StaleApply, process_identity,
    run_service_locked,
)


def test_service_stop_holds_apply_lock_and_does_not_inherit_descriptor(tmp_path):
    from types import SimpleNamespace
    calls = []
    def run(argv, **kwargs):
        assert not ProcessRLock(tmp_path / 'apply.lock').acquire(blocking=False)
        assert kwargs['env']['BYPASS_PROXY_SERVICE_LOCKED'] == '1'
        assert kwargs['close_fds'] is True
        calls.append(argv)
        return SimpleNamespace(returncode=7)
    assert run_service_locked('/opt/etc/init.d/S99telegram_bot', 'restart', directory=tmp_path, run=run) == 7
    assert calls == [['/opt/etc/init.d/S99telegram_bot', 'restart']]
    with ProcessRLock(tmp_path / 'apply.lock'):
        pass


def test_service_wrapper_rejects_unrelated_commands(tmp_path):
    with pytest.raises(ValueError):
        run_service_locked('/opt/etc/init.d/S24xray', 'restart', directory=tmp_path)
    with pytest.raises(ValueError):
        run_service_locked('/opt/etc/init.d/S99telegram_bot', 'remove', directory=tmp_path)


def _hold(path, connection):
    with ProcessRLock(path):
        connection.send('locked')
        connection.recv()


def _try_inherited(lock, connection):
    connection.send(lock.acquire(blocking=False))
    connection.close()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX fork only')
def test_fork_does_not_inherit_reentrant_ownership(tmp_path):
    ctx = multiprocessing.get_context('fork')
    parent, child = ctx.Pipe()
    lock = ProcessRLock(tmp_path / 'apply.lock')
    with lock:
        worker = ctx.Process(target=_try_inherited, args=(lock, child))
        worker.start()
        try:
            assert parent.poll(5)
            assert parent.recv() is False
        finally:
            worker.join(5)
            if worker.is_alive():
                worker.terminate()
                worker.join(5)
            parent.close()
            child.close()
        assert lock.locked()
    assert not lock.locked()


def test_kernel_lock_survives_process_crash(tmp_path):
    ctx = multiprocessing.get_context('spawn' if os.name == 'nt' else 'fork')
    parent, child = ctx.Pipe()
    path = tmp_path / 'apply.lock'
    worker = ctx.Process(target=_hold, args=(str(path), child))
    worker.start()
    try:
        assert parent.poll(8)
        assert parent.recv() == 'locked'
        lock = ProcessRLock(path, timeout=.05)
        assert lock.locked()
        before = time.monotonic()
        assert not lock.acquire()
        assert time.monotonic() - before < .5
        worker.terminate()
        worker.join(5)
        assert not worker.is_alive()
        with lock:
            assert lock.locked()
        assert not lock.locked()
        assert path.exists(), 'lock inode must never be deleted'
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join(5)
        parent.close()
        child.close()


def test_reentrant_lock_excludes_other_threads_and_instances(tmp_path):
    lock = ProcessRLock(tmp_path / 'apply.lock')
    other = ProcessRLock(tmp_path / 'apply.lock')
    outcomes = []
    with lock:
        with lock:
            assert not other.acquire(blocking=False)
            thread = threading.Thread(target=lambda: outcomes.append(lock.acquire(blocking=False)))
            thread.start()
            thread.join(2)
            assert not thread.is_alive()
            assert outcomes == [False]
        assert lock.locked()
    with other:
        assert other.locked()


def test_lock_releases_after_exception_and_refuses_wrong_owner(tmp_path):
    lock = ProcessRLock(tmp_path / 'apply.lock')
    with pytest.raises(ValueError):
        with lock:
            raise ValueError('injected')
    assert not lock.locked()
    with pytest.raises(RuntimeError):
        lock.release()


def test_missing_directory_does_not_fall_back_to_unlocked(tmp_path):
    lock = ProcessRLock(tmp_path / 'missing' / 'apply.lock')
    for _ in range(2):
        with pytest.raises(FileNotFoundError):
            lock.acquire()


def test_manual_invalidates_running_background_and_blocks_new_probes(tmp_path):
    first, second = ApplyCoordinator(tmp_path), ApplyCoordinator(tmp_path)
    old = first.capture()
    with first.transaction(old) as running:
        assert first.current(running)
        manual = second.request_manual()
        assert not first.current(running)
        with pytest.raises(StaleApply):
            first.require_current(running)
        with pytest.raises(ApplyBusy):
            first.capture()
    with second.transaction(manual, manual=True) as accepted:
        assert second.current(accepted)
    assert first.capture() == manual


def test_a_b_a_never_revalidates_old_ticket(tmp_path):
    coordinator = ApplyCoordinator(tmp_path)
    a = coordinator.capture()
    for _ in range(2):
        ticket = coordinator.request_manual()
        with coordinator.transaction(ticket, manual=True):
            pass
    with pytest.raises(StaleApply):
        with coordinator.transaction(a):
            pytest.fail('old work entered transaction')
    assert coordinator.capture().generation == 2


def test_new_manual_wins_even_when_previous_manual_unwinds(tmp_path):
    coordinator = ApplyCoordinator(tmp_path)
    first = coordinator.request_manual()
    second = coordinator.request_manual()
    with pytest.raises(StaleApply):
        with coordinator.transaction(first, manual=True):
            pass
    with pytest.raises(ApplyBusy):
        coordinator.capture()
    with coordinator.transaction(second, manual=True):
        pass
    assert coordinator.capture() == second


def test_exception_clears_pending_manual_but_keeps_epoch(tmp_path):
    coordinator = ApplyCoordinator(tmp_path)
    before = coordinator.capture()
    ticket = coordinator.request_manual()
    with pytest.raises(ValueError):
        with coordinator.transaction(ticket, manual=True):
            raise ValueError('injected')
    assert coordinator.capture() == ticket
    assert not coordinator.current(before)
    assert not coordinator.lock.locked()


def test_startup_recovery_invalidates_abandoned_work(tmp_path):
    coordinator = ApplyCoordinator(tmp_path)
    abandoned = coordinator.request_manual()
    restarted = ApplyCoordinator(tmp_path)
    restarted.recover_abandoned_manual()
    assert not restarted.current(abandoned)
    assert restarted.capture().manual_epoch == 2


@pytest.mark.parametrize('data', ['{', '{}', '{"generation":true,"manual_epoch":0}', 'x' * 16385])
def test_corrupted_intent_state_is_not_treated_as_fresh(tmp_path, data):
    (tmp_path / 'intent.json').write_text(data, encoding='utf-8')
    coordinator = ApplyCoordinator(tmp_path)
    with pytest.raises(ValueError):
        coordinator.capture()
    assert not coordinator._state_lock.locked()


def test_failed_atomic_write_keeps_previous_intent(tmp_path, monkeypatch):
    import proxy_apply_coordinator as module
    coordinator = ApplyCoordinator(tmp_path)
    ticket = coordinator.request_manual()
    with coordinator.transaction(ticket, manual=True):
        pass
    def fail(*_):
        raise OSError('injected replace failure')
    monkeypatch.setattr(module.os, 'replace', fail)
    with pytest.raises(OSError):
        coordinator.request_manual()
    assert coordinator.capture() == ticket
    assert not list(tmp_path.glob('.intent.json-*'))


def test_process_identity_handles_parentheses_in_command_and_pid_reuse(tmp_path):
    (tmp_path / 'sys/kernel/random').mkdir(parents=True)
    (tmp_path / 'sys/kernel/random/boot_id').write_text('synthetic-boot')
    (tmp_path / '42').mkdir()
    def write(ticks):
        (tmp_path / '42/stat').write_text('42 (worker (name)) S ' + '0 ' * 18 + str(ticks) + ' 0')
    write(100)
    assert process_identity(42, proc_root=tmp_path) == 'synthetic-boot:42:100'
    write(101)
    assert process_identity(42, proc_root=tmp_path) == 'synthetic-boot:42:101'


def test_background_probe_intent_is_cancelled_before_writer_starts(tmp_path):
    background, manual = ApplyCoordinator(tmp_path), ApplyCoordinator(tmp_path)
    with background.intent():
        with manual.mutation(manual=True):
            pass
        with pytest.raises(StaleApply):
            with background.mutation():
                pytest.fail('stale background writer ran')


def test_nested_writers_share_generation_and_later_background_write_updates_ticket(tmp_path):
    coordinator = ApplyCoordinator(tmp_path)
    with coordinator.intent():
        with coordinator.mutation() as first:
            with coordinator.mutation() as nested:
                assert nested == first == coordinator.active_ticket()
        with coordinator.mutation() as second:
            assert second.generation == first.generation + 1
    with pytest.raises(RuntimeError, match='No active'):
        coordinator.active_ticket()


def test_manual_scope_cleans_pending_intent_when_handler_fails(tmp_path):
    coordinator = ApplyCoordinator(tmp_path)
    with pytest.raises(ValueError):
        with coordinator.mutation(manual=True):
            raise ValueError('injected')
    assert coordinator.capture().generation == 1
    assert not coordinator.lock.locked()


def test_absent_recovery_journal_preserves_ticket_and_present_journal_is_serialized(tmp_path):
    from proxy_apply_coordinator import install_proxy_controls
    coordinator = ApplyCoordinator(tmp_path)
    journal = tmp_path / 'recovery.json'
    calls = []
    def needed():
        assert not ProcessRLock(tmp_path / 'apply.lock').acquire(blocking=False)
        return journal.exists()
    def recovery():
        calls.append(coordinator.active_ticket())
        assert not ProcessRLock(tmp_path / 'apply.lock').acquire(blocking=False)
        journal.unlink()
        return True
    namespace = {'recover': recovery}
    install_proxy_controls(namespace, coordinator, recoveries={'recover': needed})
    ticket = coordinator.capture()
    for _ in range(5):assert namespace['recover']() is None
    assert coordinator.current(ticket) and not calls
    journal.write_text('fixture')
    assert namespace['recover']() is True
    assert not coordinator.current(ticket) and len(calls) == 1
    newer = coordinator.capture()
    assert namespace['recover']() is None and coordinator.current(newer)


def test_recovery_failure_keeps_journal_and_releases_writer_lock(tmp_path):
    from proxy_apply_coordinator import install_proxy_controls
    coordinator = ApplyCoordinator(tmp_path)
    journal = tmp_path / 'recovery.json';journal.write_text('fixture')
    def recovery():raise ValueError('fixture recovery failure')
    namespace = {'recover': recovery}
    install_proxy_controls(namespace, coordinator, recoveries={'recover': journal.exists})
    with pytest.raises(ValueError, match='fixture recovery'):
        namespace['recover']()
    assert journal.exists()
    with ProcessRLock(tmp_path / 'apply.lock'):pass
