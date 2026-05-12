import os
import subprocess
import threading
import time


def read_proc_text(path, max_bytes=16384):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as file:
            return file.read(max_bytes)
    except Exception:
        return ''


def read_proc_meminfo(meminfo_path='/proc/meminfo'):
    values = {}
    for line in read_proc_text(meminfo_path).splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        parts = value.strip().split()
        if not parts:
            continue
        try:
            values[key] = int(parts[0])
        except Exception:
            pass
    return values


def read_ndmc_system_snapshot():
    try:
        result = subprocess.run(
            ['ndmc', '-c', 'show system'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return {}
    values = {}
    for line in (result.stdout or '').splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        key = key.strip().lower()
        value = value.strip()
        if not key or not value:
            continue
        if key == 'memory' and '/' in value:
            used_text, total_text = value.split('/', 1)
            try:
                values['memory_used'] = int(used_text.strip())
                values['memory_total'] = int(total_text.strip())
            except Exception:
                pass
            continue
        try:
            values[key] = int(value.split()[0])
        except Exception:
            values[key] = value
    return values


def process_rss_kb(pid='self', read_text=read_proc_text):
    for line in read_text(f'/proc/{pid}/status').splitlines():
        if line.startswith('VmRSS:'):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1])
                except Exception:
                    return None
    return None


def count_proc_cmdline(marker, proc_root='/proc', read_text=read_proc_text):
    count = 0
    try:
        names = os.listdir(proc_root)
    except Exception:
        return 0
    for name in names:
        if not name.isdigit():
            continue
        text = read_text(os.path.join(proc_root, name, 'cmdline'), max_bytes=2048)
        if marker in text.replace('\x00', ' '):
            count += 1
    return count


def build_router_health_payload(
    *,
    meminfo,
    ndmc_system,
    load_text,
    bot_rss_kb,
    probe_progress,
    temp_xray_count,
):
    meminfo = meminfo or {}
    ndmc_system = ndmc_system or {}
    total_kb = int(meminfo.get('MemTotal') or 0)
    free_kb = int(meminfo.get('MemFree') or 0)
    buffers_kb = int(meminfo.get('Buffers') or 0)
    cached_kb = int(meminfo.get('Cached') or 0)
    reclaimable_kb = int(meminfo.get('SReclaimable') or 0)
    linux_cache_kb = max(0, buffers_kb + cached_kb + reclaimable_kb)
    available_kb = int(meminfo.get('MemAvailable') or (free_kb + linux_cache_kb) or free_kb or 0)
    swap_total_kb = int(meminfo.get('SwapTotal') or 0)
    swap_free_kb = int(meminfo.get('SwapFree') or 0)
    display_total_kb = int(ndmc_system.get('memory_total') or ndmc_system.get('memtotal') or total_kb or 0)
    ndmc_free_kb = int(ndmc_system.get('memfree') or 0)
    ndmc_buffers_kb = int(ndmc_system.get('membuffers') or 0)
    ndmc_cache_kb = int(ndmc_system.get('memcache') or 0)
    ndmc_cache_total_kb = max(0, ndmc_buffers_kb + ndmc_cache_kb)
    if display_total_kb and int(ndmc_system.get('memory_used') or 0):
        used_kb = int(ndmc_system.get('memory_used') or 0)
        display_cache_kb = ndmc_cache_total_kb
        display_free_kb = ndmc_free_kb
        memory_source = 'keenetic'
    elif display_total_kb and ndmc_free_kb:
        used_kb = max(0, display_total_kb - ndmc_free_kb - ndmc_cache_total_kb)
        display_cache_kb = ndmc_cache_total_kb
        display_free_kb = ndmc_free_kb
        memory_source = 'keenetic'
    else:
        display_total_kb = total_kb
        used_kb = max(0, total_kb - free_kb - buffers_kb - cached_kb) if total_kb else 0
        display_cache_kb = max(0, buffers_kb + cached_kb)
        display_free_kb = free_kb
        memory_source = 'proc'
    used_mb = int(round(used_kb / 1024.0)) if used_kb else 0
    total_mb = int(round(display_total_kb / 1024.0)) if display_total_kb else 0
    available_mb = int(round(available_kb / 1024.0)) if available_kb else 0
    free_mb = int(round(display_free_kb / 1024.0)) if display_free_kb else 0
    cache_mb = int(round(display_cache_kb / 1024.0)) if display_cache_kb else 0
    used_percent = int(round((used_kb / float(display_total_kb)) * 100)) if display_total_kb else 0
    available_percent = int(round((available_kb / float(display_total_kb)) * 100)) if display_total_kb else 0
    bot_rss_mb = int(round(bot_rss_kb / 1024.0)) if bot_rss_kb else 0
    probe_progress = probe_progress or {}
    probe_running = bool(probe_progress.get('running')) and int(probe_progress.get('total') or 0) > 0
    probe_checked = int(probe_progress.get('checked') or 0)
    probe_total = int(probe_progress.get('total') or 0)
    probe_note = str(probe_progress.get('note') or '').strip()
    swap_used_mb = int(round(max(0, swap_total_kb - swap_free_kb) / 1024.0)) if swap_total_kb else 0
    memory_text = f'Память: занято {used_mb} из {total_mb} MB' if total_mb else 'Память: данные недоступны'
    details = []
    if used_mb:
        details.append(f'Занято по данным роутера: {used_mb} MB ({used_percent}%).')
    if free_mb:
        details.append(f'Свободно: {free_mb} MB.')
    if available_mb:
        details.append(f'Доступно для приложений: {available_mb} MB ({available_percent}%).')
    if cache_mb:
        details.append(f'Кэш и буферы: {cache_mb} MB.')
    if load_text:
        details.append(f'Нагрузка CPU за 1/5/15 мин: {load_text}.')
    if bot_rss_mb:
        details.append(f'Бот использует {bot_rss_mb} MB RAM.')
    if swap_total_kb:
        swap_total_mb = int(round(swap_total_kb / 1024.0))
        details.append(f'Swap: занято {swap_used_mb} из {swap_total_mb} MB.')
    if probe_running:
        details.append(f'Проверка пула: выполняется, проверено {probe_checked} из {probe_total} ключей.')
    else:
        details.append('Проверка пула: сейчас не запущена.')
    if temp_xray_count:
        details.append(f'Временный xray-процессов: {temp_xray_count}.')
    if probe_note:
        details.append(probe_note if probe_note.endswith(('.', '!', '?')) else f'{probe_note}.')
    return {
        'memory_text': memory_text,
        'note': ' '.join(details),
        'available_kb': available_kb,
        'used_kb': used_kb,
        'total_kb': display_total_kb,
        'proc_total_kb': total_kb,
        'used_percent': used_percent,
        'linux_cache_kb': display_cache_kb,
        'memory_source': memory_source,
        'load_text': load_text,
        'bot_rss_kb': bot_rss_kb or 0,
        'pool_probe_running': probe_running,
        'pool_probe_text': (
            f'Проверяется {probe_checked}/{probe_total}'
            if probe_running else 'Не запущена'
        ),
        'temporary_xray_count': temp_xray_count,
    }


class RouterHealthRuntime:
    def __init__(self, cache_ttl=5.0, time_provider=time.time):
        self.cache_ttl = float(cache_ttl or 0)
        self.time_provider = time_provider
        self._lock = threading.Lock()
        self._cache = {'timestamp': 0, 'payload': None}

    def snapshot(self, pool_probe_progress_getter):
        now = self.time_provider()
        with self._lock:
            payload = self._cache.get('payload')
            if payload is not None and now - float(self._cache.get('timestamp') or 0) < self.cache_ttl:
                return dict(payload)

        probe_progress = pool_probe_progress_getter() if pool_probe_progress_getter else {}
        probe_running = bool((probe_progress or {}).get('running')) and int((probe_progress or {}).get('total') or 0) > 0
        payload = build_router_health_payload(
            meminfo=read_proc_meminfo(),
            ndmc_system=read_ndmc_system_snapshot(),
            load_text=' / '.join((read_proc_text('/proc/loadavg').split()[:3] or [])),
            bot_rss_kb=process_rss_kb('self'),
            probe_progress=probe_progress,
            temp_xray_count=count_proc_cmdline('/tmp/bypass_pool_probe_') if probe_running else 0,
        )
        with self._lock:
            self._cache['timestamp'] = now
            self._cache['payload'] = payload
        return dict(payload)

    def invalidate(self):
        with self._lock:
            self._cache = {'timestamp': 0, 'payload': None}
