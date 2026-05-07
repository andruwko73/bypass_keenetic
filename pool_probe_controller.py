import gc
import threading
import time


def initial_pool_probe_progress():
    return {
        'running': False,
        'checked': 0,
        'total': 0,
        'scope': '',
        'started_at': 0,
        'finished_at': 0,
    }


class PoolProbeProgress:
    def __init__(self):
        self._lock = threading.Lock()
        self._progress = initial_pool_probe_progress()

    def update(self, **updates):
        with self._lock:
            self._progress.update(updates)

    def snapshot(self):
        with self._lock:
            return dict(self._progress)


def pool_probe_progress_label(progress):
    scope = (progress or {}).get('scope')
    if scope == 'manual_all':
        return 'Полная проверка всех ключей'
    if scope == 'protocol':
        return 'Проверка выбранного пула'
    return 'Фоновая проверка пула ключей'


def start_pool_probe_worker(
    probe_tasks,
    checks,
    *,
    scope,
    lock,
    set_progress,
    run_worker,
    invalidate_caches,
    time_provider=time.time,
    collect_garbage=gc.collect,
    thread_factory=threading.Thread,
):
    probe_tasks = list(probe_tasks or [])
    if not probe_tasks:
        return False, 0
    if not lock.acquire(blocking=False):
        return False, len(probe_tasks)

    set_progress(
        running=True,
        checked=0,
        total=len(probe_tasks),
        scope=scope,
        started_at=time_provider(),
        finished_at=0,
    )

    def worker():
        checked = 0
        total = len(probe_tasks)
        try:
            checked, total = run_worker(
                probe_tasks,
                checks,
                set_checked=lambda value: set_progress(checked=value),
                invalidate_caches=invalidate_caches,
            )
        finally:
            invalidate_caches()
            set_progress(
                running=False,
                checked=checked,
                total=total,
                scope=scope,
                finished_at=time_provider(),
            )
            lock.release()
            collect_garbage()

    thread_factory(target=worker, daemon=True).start()
    return True, len(probe_tasks)
