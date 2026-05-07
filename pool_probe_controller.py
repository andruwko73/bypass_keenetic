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


def failed_custom_probe_results(custom_checks):
    return {check.get('id'): False for check in (custom_checks or []) if check.get('id')}


def available_memory_kb(meminfo_path='/proc/meminfo'):
    try:
        with open(meminfo_path, 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                if line.startswith('MemAvailable:'):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
    except Exception:
        pass
    return None


def pool_probe_timeout_budget(custom_checks, task_count, workers, timeouts):
    tg_connect, tg_read, http_connect, http_read, custom_connect, custom_read, single_timeout, batch_timeout = timeouts
    custom_target_count = 0
    for check in custom_checks or []:
        targets = check.get('urls') if isinstance(check.get('urls'), list) else [check.get('url', '')]
        custom_target_count += len([target for target in targets[:2] if target])
    base_per_key = tg_connect + tg_read + http_connect + http_read + custom_target_count * (custom_connect + custom_read)
    retry_per_key = tg_connect + tg_read
    per_key = max(single_timeout, base_per_key + retry_per_key + 5.0)
    workers = max(1, int(workers or 1))
    task_count = max(1, int(task_count or 1))
    waves = (task_count + workers - 1) // workers
    return max(batch_timeout, per_key * waves + 5.0)


def select_pool_probe_tasks(tasks, *, protocol_order, custom_checks, cache, hash_key, is_fresh, max_keys=None, stale_only=False, now=None):
    now = time.time() if now is None else now
    selected = []
    seen = set()
    for proto, key_value in tasks:
        key_value = (key_value or '').strip()
        if proto not in protocol_order or not key_value:
            continue
        task_id = (proto, hash_key(key_value))
        if task_id in seen:
            continue
        seen.add(task_id)
        if stale_only and is_fresh(cache.get(hash_key(key_value)), now=now, custom_checks=custom_checks):
            continue
        selected.append((proto, key_value))
        if max_keys is not None and len(selected) >= max_keys:
            break
    return selected, custom_checks


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
