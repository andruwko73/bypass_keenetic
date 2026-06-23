import json
import os
import subprocess
import sys
import time

import youtube_edge_prefetch

for config_dir in ('/opt/etc/bot', '/opt/etc'):
    if os.path.isdir(config_dir) and config_dir not in sys.path:
        sys.path.insert(0, config_dir)

try:
    import bot_config as config
except Exception:
    config = None


STATUS_PATH = '/opt/etc/bot/youtube_edge_prefetch_status.json'
CACHE_PATH = '/opt/etc/bot/youtube_edge_cache.json'
LOCK_DIR = '/tmp/bypass-youtube-edge-prefetch.lock'
UNBLOCK_DIR = '/opt/etc/unblock'
MIN_AVAILABLE_KB = 160000
LOCK_STALE_SECONDS = 300
STATUS_MAX_BYTES = 65536

PROTOCOL_ROUTE_FILES = (
    ('shadowsocks', 'shadowsocks.txt'),
    ('vmess', 'vmess.txt'),
    ('vless', 'vless.txt'),
    ('vless2', 'vless-2.txt'),
    ('trojan', 'trojan.txt'),
)

YOUTUBE_ROUTE_MARKERS = (
    'youtube.com',
    'youtube-nocookie.com',
    'youtubeeducation.com',
    'youtubei.googleapis.com',
    'youtube.googleapis.com',
    'youtubeembeddedplayer.googleapis.com',
    'googlevideo.com',
    'ytimg.com',
    'yt3.ggpht.com',
    'ggpht.com',
    'youtu.be',
)


def _config_value(name, default):
    if config is None:
        return default
    return getattr(config, name, default)


def _config_bool(name, default):
    return bool(_config_value(name, default))


def _config_int(name, default, minimum=0):
    try:
        value = int(_config_value(name, default))
    except Exception:
        value = default
    return max(minimum, int(value))


def _config_str(name, default):
    return str(_config_value(name, default) or default).strip()


def _read_json_file(path, default=None):
    try:
        if os.path.getsize(path) > STATUS_MAX_BYTES:
            return default
        with open(path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def _write_json_file(path, payload):
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as file:
            json.dump(payload, file, ensure_ascii=False, separators=(',', ':'))
        os.replace(tmp_path, path)
        return True
    except Exception:
        return False


def _entry_matches_youtube(entry):
    value = str(entry or '').split('#', 1)[0].strip().lower()
    if not value:
        return False
    for prefix in ('full:', 'domain:', '+.', '*.'):
        if value.startswith(prefix):
            value = value[len(prefix):]
    value = value.strip('.')
    return any(value == marker or value.endswith('.' + marker) for marker in YOUTUBE_ROUTE_MARKERS)


def detect_youtube_route_protocol(unblock_dir=UNBLOCK_DIR, default='vless2'):
    best_protocol = ''
    best_count = 0
    for protocol, file_name in PROTOCOL_ROUTE_FILES:
        path = os.path.join(unblock_dir, file_name)
        count = 0
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as file:
                for line in file:
                    if _entry_matches_youtube(line):
                        count += 1
        except Exception:
            count = 0
        if count > best_count:
            best_count = count
            best_protocol = protocol
    return best_protocol or str(default or 'vless2').strip().lower() or 'vless2'


def read_available_memory_kb(meminfo_path='/proc/meminfo'):
    values = {}
    try:
        with open(meminfo_path, 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                if ':' not in line:
                    continue
                key, value = line.split(':', 1)
                parts = value.strip().split()
                if parts and parts[0].isdigit():
                    values[key] = int(parts[0])
    except Exception:
        return 0
    available = values.get('MemAvailable')
    if available:
        return int(available)
    return int(values.get('MemFree', 0) + values.get('Cached', 0) + values.get('Buffers', 0))


def _pid_is_active(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def _lock_age_seconds(lock_dir):
    try:
        return max(0, int(time.time() - os.stat(lock_dir).st_mtime))
    except Exception:
        return 0


def acquire_lock(lock_dir=LOCK_DIR, stale_seconds=LOCK_STALE_SECONDS):
    try:
        os.mkdir(lock_dir)
    except FileExistsError:
        pid = ''
        try:
            with open(os.path.join(lock_dir, 'pid'), 'r', encoding='utf-8') as file:
                pid = ''.join(ch for ch in file.read(32) if ch.isdigit())
        except Exception:
            pid = ''
        if _lock_age_seconds(lock_dir) >= int(stale_seconds or LOCK_STALE_SECONDS) and not _pid_is_active(pid or 0):
            release_lock(lock_dir)
            os.mkdir(lock_dir)
        else:
            return False
    except Exception:
        return False
    try:
        with open(os.path.join(lock_dir, 'pid'), 'w', encoding='utf-8') as file:
            file.write(str(os.getpid()))
    except Exception:
        pass
    return True


def release_lock(lock_dir=LOCK_DIR):
    try:
        os.remove(os.path.join(lock_dir, 'pid'))
    except Exception:
        pass
    try:
        os.rmdir(lock_dir)
    except Exception:
        pass


def _run_command(args, timeout=3):
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=timeout,
        check=False,
    )


def ipset_contains(set_name, address):
    try:
        result = _run_command(['ipset', 'test', str(set_name), str(address)], timeout=2)
        return result.returncode == 0
    except Exception:
        return False


def ipset_add(set_name, address):
    try:
        result = _run_command(['ipset', 'add', str(set_name), str(address), '-exist'], timeout=2)
        return result.returncode == 0, (result.stdout or '').strip()
    except Exception as exc:
        return False, str(exc)


def ipset_delete(set_name, address):
    try:
        result = _run_command(['ipset', 'del', str(set_name), str(address)], timeout=2)
        return result.returncode == 0
    except Exception:
        return False


def delete_conntrack_for_address(address):
    deleted = 0
    for proto in ('tcp', 'udp'):
        for direction in ('--orig-dst', '--reply-src'):
            try:
                result = subprocess.run(
                    ['conntrack', '-D', '-p', proto, direction, str(address)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
                if result.returncode == 0:
                    deleted += 1
            except Exception:
                continue
    return deleted


def _status_message(status):
    skipped = str((status or {}).get('skipped_reason') or '').strip()
    if skipped:
        return f'skipped: {skipped}'
    protocol = str((status or {}).get('route_protocol') or '').strip() or 'unknown'
    return (
        f'{protocol}: added {int((status or {}).get("added_addresses") or 0)} addresses, '
        f'candidates {int((status or {}).get("candidates") or 0)}, '
        f'cache {int((status or {}).get("cache_entries") or 0)}'
    )


def _normalize_status(status, *, trigger, started_at, next_host_index=0):
    now = time.time()
    status = dict(status or {})
    status['external'] = True
    status['trigger'] = str(trigger or 'manual')[:40]
    status['last_run_at'] = float(status.get('last_run_at') or now)
    status['finished_at'] = now
    status['duration_ms'] = int(max(0.0, now - float(started_at or now)) * 1000)
    status['pid'] = os.getpid()
    status['running'] = False
    status['next_host_index'] = int(next_host_index or 0)
    status['last_message'] = _status_message(status)
    return status


def _selected_hosts(hosts, max_hosts, status):
    hosts = tuple(youtube_edge_prefetch.normalize_hosts(hosts))
    if not hosts:
        return (), 0
    max_hosts = min(len(hosts), max(1, int(max_hosts or youtube_edge_prefetch.DEFAULT_MAX_HOSTS_PER_RUN)))
    try:
        start_index = int((status or {}).get('next_host_index') or 0) % len(hosts)
    except Exception:
        start_index = 0
    selected = tuple(hosts[(start_index + offset) % len(hosts)] for offset in range(max_hosts))
    return selected, (start_index + max_hosts) % len(hosts)


def run_prefetch(trigger='manual', *, status_path=None, cache_path=None, unblock_dir=None):
    started_at = time.time()
    status_path = status_path or _config_str('youtube_edge_prefetch_status_path', STATUS_PATH)
    cache_path = cache_path or _config_str('youtube_edge_prefetch_cache_path', CACHE_PATH)
    lock_dir = _config_str('youtube_edge_prefetch_lock_dir', LOCK_DIR)
    previous_status = _read_json_file(status_path, {})
    try:
        next_host_index = int((previous_status or {}).get('next_host_index') or 0)
    except Exception:
        next_host_index = 0

    if not _config_bool('youtube_edge_prefetch_enabled', True):
        status = {'ok': False, 'skipped_reason': 'disabled'}
        status = _normalize_status(status, trigger=trigger, started_at=started_at, next_host_index=next_host_index)
        _write_json_file(status_path, status)
        return status

    if not acquire_lock(lock_dir):
        status = {'ok': False, 'skipped_reason': 'already_running'}
        status = _normalize_status(status, trigger=trigger, started_at=started_at, next_host_index=next_host_index)
        _write_json_file(status_path, status)
        return status

    try:
        min_available_kb = _config_int('youtube_edge_prefetch_min_available_kb', MIN_AVAILABLE_KB, minimum=0)
        available_kb = read_available_memory_kb()
        route_protocol = detect_youtube_route_protocol(
            unblock_dir=unblock_dir or UNBLOCK_DIR,
            default=_config_str('youtube_edge_prefetch_default_route_protocol', 'vless2'),
        )
        if min_available_kb > 0 and available_kb > 0 and available_kb < min_available_kb:
            status = {
                'ok': False,
                'route_protocol': route_protocol,
                'skipped_reason': 'low_available_memory',
                'available_memory_kb': available_kb,
            }
            status = _normalize_status(status, trigger=trigger, started_at=started_at, next_host_index=next_host_index)
            _write_json_file(status_path, status)
            return status

        hosts, next_host_index = _selected_hosts(
            _config_value('youtube_edge_prefetch_hosts', youtube_edge_prefetch.DEFAULT_PREFETCH_HOSTS),
            _config_int(
                'youtube_edge_prefetch_max_hosts_per_run',
                youtube_edge_prefetch.DEFAULT_MAX_HOSTS_PER_RUN,
                minimum=1,
            ),
            previous_status,
        )
        status = youtube_edge_prefetch.prefetch_once(
            route_protocol=route_protocol,
            cache_path=cache_path,
            hosts=hosts,
            dns_servers=_config_value('youtube_edge_prefetch_dns_servers', youtube_edge_prefetch.DEFAULT_DNS_SERVERS),
            ipset_contains=ipset_contains,
            ipset_add=ipset_add,
            ipset_delete=ipset_delete,
            delete_conntrack=delete_conntrack_for_address,
            cache_ttl_seconds=_config_int(
                'youtube_edge_prefetch_cache_ttl_seconds',
                youtube_edge_prefetch.DEFAULT_CACHE_TTL_SECONDS,
                minimum=3600,
            ),
            max_cache_entries=_config_int(
                'youtube_edge_prefetch_max_cache_entries',
                youtube_edge_prefetch.DEFAULT_MAX_CACHE_ENTRIES,
                minimum=16,
            ),
            max_hosts_per_run=len(hosts) or 1,
            max_resolved_addresses=_config_int(
                'youtube_edge_prefetch_max_resolved_addresses',
                youtube_edge_prefetch.DEFAULT_MAX_RESOLVED_ADDRESSES,
                minimum=1,
            ),
            max_candidates=_config_int(
                'youtube_edge_prefetch_max_candidates',
                youtube_edge_prefetch.DEFAULT_MAX_CANDIDATES,
                minimum=1,
            ),
            max_addresses_per_run=_config_int(
                'youtube_edge_prefetch_max_addresses_per_run',
                youtube_edge_prefetch.DEFAULT_MAX_ADDRESSES_PER_RUN,
                minimum=1,
            ),
            remove_from_other_sets=_config_bool('youtube_edge_prefetch_exclusive_ipsets', True),
        )
        status['available_memory_kb'] = available_kb
        status = _normalize_status(status, trigger=trigger, started_at=started_at, next_host_index=next_host_index)
        _write_json_file(status_path, status)
        return status
    except Exception as exc:
        status = {
            'ok': False,
            'skipped_reason': 'error',
            'error': str(exc)[:160],
        }
        status = _normalize_status(status, trigger=trigger, started_at=started_at, next_host_index=next_host_index)
        _write_json_file(status_path, status)
        return status
    finally:
        release_lock(lock_dir)


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    trigger = 'manual'
    if argv:
        if argv[0] == '--trigger' and len(argv) > 1:
            trigger = argv[1]
        elif argv[0].startswith('--trigger='):
            trigger = argv[0].split('=', 1)[1]
        else:
            trigger = argv[0]
    status = run_prefetch(trigger=trigger)
    print(status.get('last_message') or _status_message(status))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
