"""Bounded coordination for service checks after applying a proxy key."""

import threading
import time


class PostApplyCoordinator:
    """Run one post-apply check at a time and keep only the newest key per protocol."""

    def __init__(
        self,
        *,
        current_matches,
        ready,
        probe,
        prefetch=None,
        invalidate=None,
        resume_pool_probe=None,
        shutdown_event=None,
        log=None,
        wait_timeout=120.0,
        poll_seconds=0.5,
        thread_factory=threading.Thread,
        monotonic=time.monotonic,
        sleep=time.sleep,
    ):
        self._current_matches = current_matches
        self._ready = ready
        self._probe = probe
        self._prefetch = prefetch
        self._invalidate = invalidate
        self._resume_pool_probe = resume_pool_probe
        self._shutdown_event = shutdown_event
        self._log = log
        self._wait_timeout = max(0.0, float(wait_timeout or 0.0))
        self._poll_seconds = max(0.05, float(poll_seconds or 0.5))
        self._thread_factory = thread_factory
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._pending = {}
        self._worker = None
        self._resume_requested = False

    def _stopped(self):
        event = self._shutdown_event
        return bool(event is not None and event.is_set())

    def _wait(self, seconds):
        event = self._shutdown_event
        if event is not None:
            event.wait(seconds)
        else:
            self._sleep(seconds)

    def _write_log(self, message):
        if not callable(self._log):
            return
        try:
            self._log(str(message or ''))
        except Exception:
            pass

    def _wait_until_ready(self):
        deadline = self._monotonic() + self._wait_timeout if self._wait_timeout else 0.0
        while not self._stopped():
            try:
                if self._ready():
                    return True
            except Exception as exc:
                self._write_log(f'Post-apply readiness check failed: {type(exc).__name__}')
            if deadline and self._monotonic() >= deadline:
                return False
            self._wait(self._poll_seconds)
        return False

    def _new_worker_locked(self):
        worker = self._thread_factory(
            target=self._run,
            name='post-apply-key-check',
            daemon=True,
        )
        self._worker = worker
        return worker

    def schedule(self, proto, key_value, *, resume_pool_probe=False):
        proto = str(proto or '').strip()
        key_value = str(key_value or '').strip()
        if not proto or not key_value:
            return 'skipped'
        worker_to_start = None
        with self._lock:
            self._pending[proto] = key_value
            self._resume_requested = self._resume_requested or bool(resume_pool_probe)
            if self._worker is None:
                worker_to_start = self._new_worker_locked()
        if worker_to_start is not None:
            try:
                worker_to_start.start()
            except Exception:
                with self._lock:
                    if self._worker is worker_to_start:
                        self._worker = None
                        self._pending.clear()
                        self._resume_requested = False
                raise
            return 'started'
        return 'queued'

    def snapshot(self):
        with self._lock:
            return {
                'running': self._worker is not None,
                'pending_protocols': tuple(sorted(self._pending)),
                'resume_requested': bool(self._resume_requested),
            }

    def _finish_worker(self, current_worker):
        resume_requested = False
        successor = None
        with self._lock:
            if self._worker is current_worker:
                self._worker = None
                resume_requested = bool(self._resume_requested)
                self._resume_requested = False
                if self._pending and not self._stopped():
                    self._resume_requested = resume_requested
                    resume_requested = False
                    successor = self._new_worker_locked()
        if successor is not None:
            successor.start()
        if resume_requested and callable(self._resume_pool_probe):
            try:
                self._resume_pool_probe()
            except Exception as exc:
                self._write_log(f'Post-apply pool-probe resume failed: {type(exc).__name__}')

    def _run(self):
        current_worker = threading.current_thread()
        try:
            while not self._stopped():
                with self._lock:
                    if not self._pending:
                        return
                    pending = dict(self._pending)
                    self._pending.clear()
                if not self._wait_until_ready():
                    self._write_log('Post-apply service check expired while waiting for router resources.')
                    continue
                for proto, key_value in pending.items():
                    if self._stopped():
                        return
                    try:
                        if not self._current_matches(proto, key_value):
                            continue
                    except Exception as exc:
                        self._write_log(f'Post-apply active-key check failed for {proto}: {type(exc).__name__}')
                        continue
                    outcome = None
                    try:
                        outcome = self._probe(proto, key_value)
                    except Exception as exc:
                        self._write_log(f'Post-apply service check failed for {proto}: {type(exc).__name__}')
                    try:
                        still_current = self._current_matches(proto, key_value)
                    except Exception:
                        still_current = False
                    if still_current and callable(self._prefetch):
                        try:
                            self._prefetch(proto, outcome)
                        except Exception as exc:
                            self._write_log(f'Post-apply prefetch failed for {proto}: {type(exc).__name__}')
                    if callable(self._invalidate):
                        try:
                            self._invalidate()
                        except Exception as exc:
                            self._write_log(f'Post-apply cache invalidation failed: {type(exc).__name__}')
        finally:
            self._finish_worker(current_worker)
