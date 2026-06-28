import os
import threading
import time


DEFAULT_HISTORY_LIMIT = 120
DEFAULT_WARN_BOT_RSS_KB = 64 * 1024
DEFAULT_CRITICAL_BOT_RSS_KB = 85 * 1024
BOT_CMD_MARKER = 'python3 /opt/etc/bot/main.py'
XRAY_CMD_MARKER = 'xray run -c /opt/etc/xray/config.json'


def read_proc_text(path, max_bytes=16384):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as file:
            return file.read(max_bytes)
    except Exception:
        return ''


def parse_loadavg(text):
    parts = str(text or '').strip().split()
    values = []
    for index in range(3):
        try:
            values.append(float(parts[index]))
        except Exception:
            values.append(0.0)
    return tuple(values)


def read_loadavg(read_text=read_proc_text):
    return parse_loadavg(read_text('/proc/loadavg', max_bytes=256))


def parse_proc_stat_ticks(text):
    parts = str(text or '').strip().split()
    if not parts or parts[0] != 'cpu':
        return 0
    total = 0
    for value in parts[1:]:
        try:
            total += int(value)
        except Exception:
            pass
    return total


def read_system_ticks(read_text=read_proc_text):
    for line in read_text('/proc/stat', max_bytes=4096).splitlines():
        if line.startswith('cpu '):
            return parse_proc_stat_ticks(line)
    return 0


def parse_process_ticks(stat_text):
    try:
        tail = str(stat_text or '').rsplit(')', 1)[1].strip().split()
        return int(tail[11]) + int(tail[12])
    except Exception:
        return 0


def process_ticks(pid, read_text=read_proc_text):
    return parse_process_ticks(read_text(f'/proc/{pid}/stat', max_bytes=4096))


def parse_process_rss_kb(status_text):
    for line in str(status_text or '').splitlines():
        if line.startswith('VmRSS:'):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1])
                except Exception:
                    return 0
    return 0


def process_rss_kb(pid, read_text=read_proc_text):
    return parse_process_rss_kb(read_text(f'/proc/{pid}/status', max_bytes=8192))


def find_pid_by_cmdline(marker, proc_root='/proc', read_text=read_proc_text):
    marker = str(marker or '')
    if not marker:
        return None
    try:
        entries = os.listdir(proc_root)
    except Exception:
        return None
    for entry in entries:
        if not entry.isdigit():
            continue
        cmdline = read_text(os.path.join(proc_root, entry, 'cmdline'), max_bytes=4096)
        if marker in cmdline.replace('\x00', ' '):
            try:
                return int(entry)
            except Exception:
                return None
    return None


def _cpu_percent(current_ticks, previous, current_system_ticks):
    if not previous:
        return 0.0
    previous_ticks, previous_system_ticks = previous
    process_delta = max(0, int(current_ticks or 0) - int(previous_ticks or 0))
    system_delta = max(0, int(current_system_ticks or 0) - int(previous_system_ticks or 0))
    if not system_delta:
        return 0.0
    return round((process_delta / float(system_delta)) * 100.0, 2)


def _process_snapshot(name, pid, current_system_ticks, previous):
    if not pid:
        return {
            'name': name,
            'pid': None,
            'running': False,
            'rss_kb': 0,
            'cpu_percent': 0.0,
            'ticks': 0,
        }
    ticks = process_ticks(pid)
    return {
        'name': name,
        'pid': int(pid),
        'running': True,
        'rss_kb': process_rss_kb(pid),
        'cpu_percent': _cpu_percent(ticks, previous, current_system_ticks),
        'ticks': ticks,
    }


class RouterMetricsRuntime:
    def __init__(
        self,
        *,
        history_limit=DEFAULT_HISTORY_LIMIT,
        warn_bot_rss_kb=DEFAULT_WARN_BOT_RSS_KB,
        critical_bot_rss_kb=DEFAULT_CRITICAL_BOT_RSS_KB,
        warn_load1=3.0,
        time_provider=time.time,
    ):
        self.history_limit = max(10, int(history_limit or DEFAULT_HISTORY_LIMIT))
        self.warn_bot_rss_kb = int(warn_bot_rss_kb or 0)
        self.critical_bot_rss_kb = int(critical_bot_rss_kb or 0)
        self.warn_load1 = float(warn_load1 or 0.0)
        self.time_provider = time_provider
        self._lock = threading.Lock()
        self._previous = {}
        self._history = []

    def snapshot(self, *, include_history=True):
        with self._lock:
            now = float(self.time_provider())
            load1, load5, load15 = read_loadavg()
            system_ticks = read_system_ticks()
            bot_pid = os.getpid()
            xray_pid = find_pid_by_cmdline(XRAY_CMD_MARKER)
            bot = _process_snapshot('bot', bot_pid, system_ticks, self._previous.get('bot'))
            xray = _process_snapshot('xray', xray_pid, system_ticks, self._previous.get('xray'))
            self._previous['bot'] = (bot.get('ticks') or 0, system_ticks)
            if xray.get('running'):
                self._previous['xray'] = (xray.get('ticks') or 0, system_ticks)
            sample = {
                'timestamp': now,
                'load1': load1,
                'load5': load5,
                'load15': load15,
                'bot_rss_kb': bot.get('rss_kb') or 0,
                'bot_cpu_percent': bot.get('cpu_percent') or 0.0,
                'xray_rss_kb': xray.get('rss_kb') or 0,
                'xray_cpu_percent': xray.get('cpu_percent') or 0.0,
            }
            if include_history:
                self._history.append(sample)
                if len(self._history) > self.history_limit:
                    self._history = self._history[-self.history_limit:]
                history_samples = list(self._history)
            else:
                history_samples = list(self._history[-self.history_limit + 1:]) + [sample]
            bot_rss_values = [int(item.get('bot_rss_kb') or 0) for item in history_samples if item.get('bot_rss_kb')]
            xray_rss_values = [int(item.get('xray_rss_kb') or 0) for item in history_samples if item.get('xray_rss_kb')]
            load_values = [float(item.get('load1') or 0.0) for item in history_samples]
            payload = {
                'timestamp': now,
                'load': {'load1': load1, 'load5': load5, 'load15': load15},
                'processes': {'bot': bot, 'xray': xray},
                'thresholds': {
                    'warn_bot_rss_kb': self.warn_bot_rss_kb,
                    'critical_bot_rss_kb': self.critical_bot_rss_kb,
                    'warn_load1': self.warn_load1,
                },
                'summary': {
                    'samples': len(history_samples),
                    'bot_rss_min_kb': min(bot_rss_values) if bot_rss_values else 0,
                    'bot_rss_max_kb': max(bot_rss_values) if bot_rss_values else 0,
                    'xray_rss_min_kb': min(xray_rss_values) if xray_rss_values else 0,
                    'xray_rss_max_kb': max(xray_rss_values) if xray_rss_values else 0,
                    'load1_max': max(load_values) if load_values else 0.0,
                },
            }
            if include_history:
                payload['history'] = history_samples
            return payload
