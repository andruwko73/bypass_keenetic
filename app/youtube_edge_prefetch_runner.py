import json
import ipaddress
import os
import signal
import subprocess
import sys
import time
from urllib.parse import urlparse

import youtube_edge_prefetch
import youtube_route_owner

for config_dir in ('/opt/etc', '/opt/etc/bot'):
    while config_dir in sys.path:
        sys.path.remove(config_dir)
    if os.path.isdir(config_dir):
        sys.path.insert(0, config_dir)

try:
    import bot_config as config
except Exception:
    config = None


STATUS_PATH = '/opt/etc/bot/youtube_edge_prefetch_status.json'
CDN_QUALITY_STATUS_PATH = '/opt/etc/bot/youtube_edge_cdn_quality_status.json'
CACHE_PATH = '/opt/etc/bot/youtube_edge_cache.json'
DNSMASQ_CONFIG_PATH = '/opt/etc/dnsmasq.conf'
DNS_QUALITY_HOSTS_PATH = '/opt/etc/bot/youtube_edge_quality.hosts'
LOCK_DIR = '/tmp/bypass-youtube-edge-prefetch.lock'
UNBLOCK_DIR = '/opt/etc/unblock'
MIN_AVAILABLE_KB = 125000
LOCK_STALE_SECONDS = 300
STATUS_MAX_BYTES = 65536
WATCH_WARM_URLS = (
    'https://www.youtube.com/watch?v=aqz-KE-bpKQ',
    'https://www.youtube.com/watch?v=jfKfPfyJRdk',
)
WATCH_WARM_MAX_PAGES = 1
WATCH_WARM_MAX_HOSTS = 6
WATCH_WARM_MAX_BYTES = 450000
WATCH_WARM_CONNECT_TIMEOUT = 4
WATCH_WARM_MAX_TIME = 10
UNBLOCK_IPSET_LOCK_DIR = '/tmp/bypass-unblock-ipset.lock'
UNBLOCK_IPSET_LOCK_STALE_SECONDS = 600
POOL_PROBE_PROCESS_MARKERS = (
    'bypass_pool_probe_worker_',
    '/tmp/bypass_pool_probe_',
)
FAST_PREFETCH_HOSTS = (
    'www.youtube.com',
    'youtube.com',
    'youtubei.googleapis.com',
    'manifest.googlevideo.com',
    'redirector.googlevideo.com',
    'i.ytimg.com',
    's.ytimg.com',
    'yt3.ggpht.com',
)
FAST_PREFETCH_TRIGGERS = (
    'post-install',
    'post-update',
    'first-run',
    'startup',
    'route-change',
    'manual-fast',
)
CACHE_FRESHNESS_TRIGGERS = (
    'post-install',
    'post-update',
    'first-run',
    'startup',
    'cdn-quality',
)
CACHE_RESTORE_TRIGGERS = FAST_PREFETCH_TRIGGERS + (
    'manual-restore',
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


def _config_float(name, default, minimum=0.0):
    try:
        value = float(_config_value(name, default))
    except Exception:
        value = default
    return max(float(minimum), float(value))


def _config_str(name, default):
    return str(_config_value(name, default) or default).strip()


def _as_tuple(value, default=()):
    if value is None:
        return tuple(default)
    if isinstance(value, str):
        return (value,)
    try:
        return tuple(value)
    except Exception:
        return tuple(default)


def _route_socks_port(protocol):
    protocol = str(protocol or '').strip().lower()
    if protocol == 'shadowsocks':
        return _config_int('localportsh_bot', 10820, minimum=1)
    if protocol == 'vmess':
        return _config_int('localportvmess', 10810, minimum=1)
    if protocol == 'vless':
        return _config_int('localportvless', 10811, minimum=1)
    if protocol == 'vless2':
        default_vless = _config_int('localportvless', 10811, minimum=1)
        return _config_int('localportvless2', default_vless + 2, minimum=1)
    if protocol == 'trojan':
        return _config_int('localporttrojan_bot', 10830, minimum=1)
    return 0


def _normalize_watch_urls(urls):
    normalized = []
    seen = set()
    for item in _as_tuple(urls, WATCH_WARM_URLS):
        url = str(item or '').strip()
        if not url:
            continue
        try:
            parsed = urlparse(url)
        except Exception:
            continue
        host = (parsed.hostname or '').lower().strip('.')
        if parsed.scheme != 'https':
            continue
        if host not in ('www.youtube.com', 'm.youtube.com', 'youtube.com', 'youtu.be'):
            continue
        if host != 'youtu.be' and not (
            parsed.path.startswith('/watch') or parsed.path.startswith('/live/')
        ):
            continue
        if url in seen:
            continue
        seen.add(url)
        normalized.append(url)
    return tuple(normalized)


def watch_urls_for_run():
    urls = list(_normalize_watch_urls(_config_value('youtube_edge_watch_warm_urls', WATCH_WARM_URLS)))
    seen = set(urls)
    for url in _normalize_watch_urls(WATCH_WARM_URLS):
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return tuple(urls)


def _fetch_watch_page(url, socks_port, *, max_bytes, connect_timeout, max_time):
    if socks_port <= 0:
        return '', 'no_socks_port'
    max_bytes = max(4096, int(max_bytes or WATCH_WARM_MAX_BYTES))
    command = [
        'curl',
        '-L',
        '-sS',
        '--compressed',
        '--max-filesize',
        str(max_bytes),
        '--socks5-hostname',
        f'127.0.0.1:{int(socks_port)}',
        '--connect-timeout',
        str(max(1, int(connect_timeout or WATCH_WARM_CONNECT_TIMEOUT))),
        '--max-time',
        str(max(2, int(max_time or WATCH_WARM_MAX_TIME))),
        '-A',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
        str(url),
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(3, int(max_time or WATCH_WARM_MAX_TIME) + 3),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return '', 'process_timeout'
    except FileNotFoundError:
        return '', 'curl_unavailable'
    except Exception:
        return '', 'launch_failed'
    if result.returncode != 0:
        error_text = bytes(result.stderr or b'').decode('utf-8', errors='ignore').lower()
        if result.returncode == 28 or 'timed out' in error_text:
            return '', 'timeout'
        if result.returncode == 63:
            return '', 'response_too_large'
        return '', f'curl_exit_{int(result.returncode)}'
    data = bytes(result.stdout or b'')[:max_bytes]
    if not data:
        return '', 'empty_response'
    return data.decode('utf-8', errors='ignore'), ''


def _quality_probe_url(host):
    host = youtube_edge_prefetch.normalize_hosts((host,))
    if not host:
        return ''
    host = host[0]
    return f'https://{host}/generate_204'


def _quality_probe_reason(returncode, stderr):
    text = str(stderr or '').strip().lower()
    if returncode == 28 or 'timeout' in text or 'timed out' in text:
        return 'timeout'
    if 'eof' in text or 'ssl' in text or 'tls' in text or 'handshake' in text:
        return 'eof'
    return 'failed'


def probe_candidate_quality(candidate, route_protocol, *, target_ms=1000, timeout_seconds=5):
    host = str((candidate or {}).get('host') or '').strip().lower().strip('.')
    address = str((candidate or {}).get('address') or '').strip()
    if not youtube_edge_prefetch.youtube_owned_host(host):
        return {'ok': False, 'reason': 'shared', 'latency_ms': 0}
    if not youtube_edge_prefetch.is_public_ipv4(address):
        return {'ok': False, 'reason': 'invalid_ip', 'latency_ms': 0}
    socks_port = _route_socks_port(route_protocol)
    if socks_port <= 0:
        return {'ok': False, 'reason': 'no_socks_port', 'latency_ms': 0}
    url = _quality_probe_url(host)
    if not url:
        return {'ok': False, 'reason': 'invalid_host', 'latency_ms': 0}

    timeout_seconds = max(2, int(timeout_seconds or 5))
    command = [
        'curl',
        '-L',
        '-sS',
        '--socks5-hostname',
        f'127.0.0.1:{int(socks_port)}',
        '--resolve',
        f'{host}:443:{address}',
        '--connect-timeout',
        str(min(3, timeout_seconds)),
        '--max-time',
        str(timeout_seconds),
        '-o',
        '/dev/null',
        '-w',
        '%{http_code} %{time_total}',
        '-A',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
        url,
    ]
    started = time.time()
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds + 2,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {'ok': False, 'reason': 'timeout', 'latency_ms': int((time.time() - started) * 1000)}
    except Exception:
        return {'ok': False, 'reason': 'failed', 'latency_ms': 0}

    latency_ms = int((time.time() - started) * 1000)
    parts = str(result.stdout or '').strip().split()
    http_code = parts[0] if parts else '000'
    if len(parts) > 1:
        try:
            latency_ms = int(float(parts[1]) * 1000)
        except Exception:
            pass
    if result.returncode != 0:
        return {
            'ok': False,
            'reason': _quality_probe_reason(result.returncode, result.stderr),
            'latency_ms': latency_ms,
        }
    if not http_code.isdigit() or http_code == '000':
        return {'ok': False, 'reason': 'failed', 'latency_ms': latency_ms}
    return {
        'ok': latency_ms <= int(target_ms or youtube_edge_prefetch.DEFAULT_QUALITY_TARGET_MS),
        'reason': 'ok' if latency_ms <= int(target_ms or youtube_edge_prefetch.DEFAULT_QUALITY_TARGET_MS) else 'slow',
        'latency_ms': latency_ms,
    }


def collect_watch_edge_hosts(route_protocol):
    if not _config_bool('youtube_edge_watch_warm_enabled', True):
        return (), {'enabled': False, 'skipped_reason': 'disabled'}
    socks_port = _route_socks_port(route_protocol)
    if socks_port <= 0:
        return (), {'enabled': True, 'skipped_reason': 'no_socks_port'}

    max_hosts = _config_int('youtube_edge_watch_warm_max_hosts', WATCH_WARM_MAX_HOSTS, minimum=0)
    if max_hosts <= 0:
        return (), {'enabled': True, 'socks_port': socks_port, 'skipped_reason': 'max_hosts_zero'}

    urls = watch_urls_for_run()
    max_pages = min(
        len(urls),
        _config_int('youtube_edge_watch_warm_max_pages', WATCH_WARM_MAX_PAGES, minimum=1),
    )
    hosts = []
    seen = set()
    fetched = 0
    fetch_attempts = 0
    fetch_errors = []
    retry_count = min(2, _config_int('youtube_edge_watch_warm_retry_count', 2, minimum=1))
    retry_delay = _config_float('youtube_edge_watch_warm_retry_delay_seconds', 2.0, minimum=0.0)
    for url in urls[:max_pages]:
        text = ''
        for attempt in range(retry_count):
            fetch_attempts += 1
            fetch_result = _fetch_watch_page(
                url,
                socks_port,
                max_bytes=_config_int('youtube_edge_watch_warm_max_bytes', WATCH_WARM_MAX_BYTES, minimum=4096),
                connect_timeout=_config_int(
                    'youtube_edge_watch_warm_connect_timeout',
                    WATCH_WARM_CONNECT_TIMEOUT,
                    minimum=1,
                ),
                max_time=_config_int('youtube_edge_watch_warm_max_time', WATCH_WARM_MAX_TIME, minimum=2),
            )
            if isinstance(fetch_result, tuple):
                text, fetch_error = fetch_result
            else:
                text, fetch_error = fetch_result, ''
            if text:
                break
            if fetch_error:
                fetch_errors.append(str(fetch_error)[:80])
            if attempt + 1 < retry_count and retry_delay:
                time.sleep(retry_delay)
        if not text:
            continue
        fetched += 1
        for host in youtube_edge_prefetch.extract_watch_edge_hosts(text, max_hosts=max_hosts - len(hosts)):
            if host in seen:
                continue
            seen.add(host)
            hosts.append(host)
            if len(hosts) >= max_hosts:
                break
        if len(hosts) >= max_hosts:
            break

    return tuple(hosts), {
        'enabled': True,
        'socks_port': socks_port,
        'fetched_pages': fetched,
        'fetch_attempts': fetch_attempts,
        'last_fetch_error': fetch_errors[-1] if fetch_errors else '',
        'hosts': len(hosts),
        'skipped_reason': '' if hosts else (fetch_errors[-1] if fetch_errors else 'no_watch_edge_hosts'),
    }


def prefetch_hosts_for_run(*, fast=False):
    quality_hosts = youtube_edge_prefetch.normalize_hosts(
        _config_value('youtube_edge_dns_quality_hosts', youtube_edge_prefetch.DEFAULT_DNS_QUALITY_HOSTS)
    )
    if fast:
        hosts = list(youtube_edge_prefetch.normalize_hosts(
            _config_value('youtube_edge_prefetch_fast_hosts', FAST_PREFETCH_HOSTS)
        ))
        hosts = list(quality_hosts) + hosts
        seen = set(hosts)
        for host in youtube_edge_prefetch.normalize_hosts(FAST_PREFETCH_HOSTS):
            if host in seen:
                continue
            seen.add(host)
            hosts.append(host)
        return tuple(hosts)
    hosts = list(youtube_edge_prefetch.normalize_hosts(
        _config_value('youtube_edge_prefetch_hosts', youtube_edge_prefetch.DEFAULT_PREFETCH_HOSTS)
    ))
    hosts = list(quality_hosts) + hosts
    seen = set(hosts)
    for host in youtube_edge_prefetch.normalize_hosts(youtube_edge_prefetch.DEFAULT_PREFETCH_HOSTS):
        if host in seen:
            continue
        seen.add(host)
        hosts.append(host)
    return tuple(hosts)


def quality_hosts_for_run():
    return youtube_edge_prefetch.normalize_hosts(
        _config_value('youtube_edge_dns_quality_hosts', youtube_edge_prefetch.DEFAULT_DNS_QUALITY_HOSTS)
    )


def _read_text_file(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as file:
            return file.read()
    except Exception:
        return ''


def _write_text_atomic(path, content):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temporary = f'{path}.tmp.{os.getpid()}'
    try:
        with open(temporary, 'w', encoding='utf-8') as file:
            file.write(content)
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o644)
        except OSError:
            pass
    finally:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _dnsmasq_addn_hosts_configured(config_path, hosts_path):
    expected = f'addn-hosts={hosts_path}'
    return any(line.strip() == expected for line in _read_text_file(config_path).splitlines())


def _reload_dnsmasq_hosts():
    try:
        result = subprocess.run(
            ['pidof', 'dnsmasq'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return False
    if result.returncode != 0:
        return False
    reloaded = False
    for token in str(result.stdout or '').split():
        try:
            os.kill(int(token), signal.SIGHUP)
            reloaded = True
        except (OSError, ValueError):
            continue
    return reloaded


def sync_quality_hosts_file(cache_path, *, now=None):
    """Apply only a fresh multi-address CDN selection through dnsmasq hosts."""
    if not _config_bool('youtube_edge_dns_quality_enabled', True):
        return {'enabled': False, 'skipped_reason': 'disabled'}
    hosts_path = _config_str('youtube_edge_dns_quality_hosts_path', DNS_QUALITY_HOSTS_PATH)
    config_path = _config_str('youtube_edge_dnsmasq_config_path', DNSMASQ_CONFIG_PATH)
    if not _dnsmasq_addn_hosts_configured(config_path, hosts_path):
        return {'enabled': True, 'skipped_reason': 'dnsmasq_hosts_not_configured'}
    now_value = time.time() if now is None else now
    cache = youtube_edge_prefetch.load_cache(
        cache_path,
        now=now_value,
        ttl_seconds=_config_int(
            'youtube_edge_prefetch_cache_ttl_seconds',
            youtube_edge_prefetch.DEFAULT_CACHE_TTL_SECONDS,
            minimum=3600,
        ),
        max_entries=_config_int(
            'youtube_edge_prefetch_max_cache_entries',
            youtube_edge_prefetch.DEFAULT_MAX_CACHE_ENTRIES,
            minimum=16,
        ),
    )
    selected = youtube_edge_prefetch.quality_host_addresses(
        cache,
        hosts=quality_hosts_for_run(),
        now=now_value,
        min_addresses=_config_int(
            'youtube_edge_dns_quality_min_addresses',
            youtube_edge_prefetch.DEFAULT_DNS_QUALITY_MIN_ADDRESSES,
            minimum=1,
        ),
        max_addresses=_config_int(
            'youtube_edge_dns_quality_max_addresses',
            youtube_edge_prefetch.DEFAULT_DNS_QUALITY_MAX_ADDRESSES,
            minimum=1,
        ),
        max_age_seconds=_config_int(
            'youtube_edge_dns_quality_max_age_seconds',
            youtube_edge_prefetch.DEFAULT_DNS_QUALITY_MAX_AGE_SECONDS,
            minimum=60,
        ),
    )
    content = youtube_edge_prefetch.render_quality_hosts_file(selected)
    changed = _read_text_file(hosts_path) != content
    result = {
        'enabled': True,
        'hosts': len(selected),
        'addresses': sum(len(addresses) for addresses in selected.values()),
        'changed': changed,
        'reloaded': False,
        'skipped_reason': '' if selected else 'not_enough_approved_addresses',
    }
    if changed:
        _write_text_atomic(hosts_path, content)
        result['reloaded'] = _reload_dnsmasq_hosts()
    return result


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


def detect_youtube_route_protocol(unblock_dir=UNBLOCK_DIR, default='', state_path=youtube_route_owner.STATE_PATH):
    owner = youtube_route_owner.youtube_route_owner(
        unblock_dir=unblock_dir,
        default=default,
        state_path=state_path,
    )
    return str(owner or default or '').strip().lower()


def _self_test_required_for_trigger(trigger):
    text = str(trigger or '').strip().lower()
    return any(text.startswith(prefix) for prefix in FAST_PREFETCH_TRIGGERS)


def _cache_freshness_required_for_trigger(trigger):
    text = str(trigger or '').strip().lower()
    return any(text.startswith(prefix) for prefix in CACHE_FRESHNESS_TRIGGERS)


def _manual_prefetch_requested(trigger):
    return str(trigger or '').strip().lower() in (
        'manual',
        'manual-prefetch',
        'manual-restore',
        'manual-refresh',
        'scheduler',
        'ipset-refresh',
    )


def youtube_route_self_test(route_protocol):
    """Check the selected route before doing an expensive edge warm-up."""
    socks_port = _route_socks_port(route_protocol)
    if socks_port <= 0:
        return {'ok': False, 'reason': 'no_socks_port', 'http_code': '000', 'duration_ms': 0}
    timeout_seconds = _config_int('youtube_route_self_test_timeout_seconds', 5, minimum=2)
    started_at = time.monotonic()
    command = [
        'curl',
        '-L',
        '-sS',
        '--socks5-hostname',
        f'127.0.0.1:{int(socks_port)}',
        '--connect-timeout',
        str(min(3, timeout_seconds)),
        '--max-time',
        str(timeout_seconds),
        '-o',
        '/dev/null',
        '-w',
        '%{http_code}',
        'https://www.youtube.com/generate_204',
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout_seconds + 2,
            check=False,
        )
        http_code = str(result.stdout or '').strip()[:3] or '000'
        ok = result.returncode == 0 and http_code.isdigit() and 200 <= int(http_code) < 500
        return {
            'ok': ok,
            'reason': 'ok' if ok else 'request_failed',
            'http_code': http_code,
            'duration_ms': int((time.monotonic() - started_at) * 1000),
        }
    except subprocess.TimeoutExpired:
        return {'ok': False, 'reason': 'timeout', 'http_code': '000', 'duration_ms': int((time.monotonic() - started_at) * 1000)}
    except Exception:
        return {'ok': False, 'reason': 'request_failed', 'http_code': '000', 'duration_ms': int((time.monotonic() - started_at) * 1000)}


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


def read_cpu_stat(stat_path='/proc/stat'):
    try:
        with open(stat_path, 'r', encoding='utf-8', errors='ignore') as file:
            parts = file.readline().split()
    except Exception:
        return None
    if not parts or parts[0] != 'cpu':
        return None
    try:
        values = tuple(int(value) for value in parts[1:])
    except Exception:
        return None
    return values if len(values) >= 4 else None


def cpu_percent_between(previous, current):
    if not previous or not current:
        return None
    previous_total = sum(previous)
    current_total = sum(current)
    previous_idle = previous[3] + (previous[4] if len(previous) > 4 else 0)
    current_idle = current[3] + (current[4] if len(current) > 4 else 0)
    total_delta = current_total - previous_total
    idle_delta = current_idle - previous_idle
    if total_delta <= 0 or idle_delta < 0:
        return None
    return max(0.0, min(100.0, (total_delta - idle_delta) * 100.0 / float(total_delta)))


def read_cpu_percent(sample_seconds=0.25):
    previous = read_cpu_stat()
    if previous is None:
        return None
    time.sleep(max(0.05, float(sample_seconds or 0.25)))
    return cpu_percent_between(previous, read_cpu_stat())


def read_load1(loadavg_path='/proc/loadavg'):
    try:
        with open(loadavg_path, 'r', encoding='utf-8', errors='ignore') as file:
            parts = file.read().split()
    except Exception:
        return None
    if not parts:
        return None
    try:
        return float(parts[0])
    except Exception:
        return None


def _lock_dir_active(lock_dir, stale_seconds=UNBLOCK_IPSET_LOCK_STALE_SECONDS):
    try:
        if not os.path.isdir(lock_dir):
            return False
        pid = ''
        try:
            with open(os.path.join(lock_dir, 'pid'), 'r', encoding='utf-8') as file:
                pid = ''.join(ch for ch in file.read(32) if ch.isdigit())
        except Exception:
            pid = ''
        if pid and _pid_is_active(pid):
            return True
        try:
            age = time.time() - os.stat(lock_dir).st_mtime
        except Exception:
            age = 0
        return age < max(1, int(stale_seconds or UNBLOCK_IPSET_LOCK_STALE_SECONDS))
    except Exception:
        return False


def _process_marker_running(markers=POOL_PROBE_PROCESS_MARKERS):
    marker_values = tuple(str(marker or '') for marker in markers or () if str(marker or ''))
    if not marker_values:
        return False
    try:
        result = subprocess.run(
            ['ps', 'w'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return False
    for line in (result.stdout or '').splitlines():
        if any(marker in line for marker in marker_values) and 'youtube_edge_prefetch_runner.py' not in line:
            return True
    return False


def _scheduler_full_run_guarded_trigger(trigger):
    text = str(trigger or '').strip().lower()
    return text in ('scheduler', 'ipset-refresh', 'manual-refresh')


def _background_busy_reason(trigger, fast_warm):
    if fast_warm:
        return ''
    if not _scheduler_full_run_guarded_trigger(trigger):
        return ''
    if _config_bool('youtube_edge_prefetch_skip_when_unblock_running', True):
        lock_dir = _config_str('youtube_edge_prefetch_unblock_lock_dir', UNBLOCK_IPSET_LOCK_DIR)
        stale_seconds = _config_int(
            'youtube_edge_prefetch_unblock_lock_stale_seconds',
            UNBLOCK_IPSET_LOCK_STALE_SECONDS,
            minimum=1,
        )
        if _lock_dir_active(lock_dir, stale_seconds=stale_seconds):
            return 'unblock_running'
    if _config_bool('youtube_edge_prefetch_skip_when_pool_probe_running', True):
        if _process_marker_running():
            return 'pool_probe_running'
    return ''


def _scheduler_full_run_cpu_busy(trigger, fast_warm):
    if fast_warm:
        return None
    if not _scheduler_full_run_guarded_trigger(trigger):
        return None
    max_cpu = _config_int('youtube_edge_prefetch_scheduler_max_cpu_percent', 45, minimum=0)
    if max_cpu <= 0:
        return None
    cpu_percent = read_cpu_percent(
        _config_int('youtube_edge_prefetch_cpu_sample_ms', 250, minimum=50) / 1000.0
    )
    if cpu_percent is None or cpu_percent <= float(max_cpu):
        return None
    return cpu_percent


def _scheduler_full_run_load_busy(trigger, fast_warm):
    if fast_warm:
        return None
    if not _scheduler_full_run_guarded_trigger(trigger):
        return None
    max_load1 = _config_float('youtube_edge_prefetch_scheduler_max_load1', 2.0, minimum=0.0)
    if max_load1 <= 0:
        return None
    load1 = read_load1()
    if load1 is None or load1 <= float(max_load1):
        return None
    return load1


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


def _ipset_member_contains_address(member, address):
    try:
        address_obj = ipaddress.ip_address(str(address or '').strip())
        network = ipaddress.ip_network(str(member or '').strip(), strict=False)
    except Exception:
        return False
    return address_obj.version == network.version and address_obj in network


def _ipset_member_overlaps_target(member, target):
    try:
        member_net = ipaddress.ip_network(str(member or '').strip(), strict=False)
        target_net = ipaddress.ip_network(str(target or '').strip(), strict=False)
    except Exception:
        return False
    return member_net.version == target_net.version and member_net.overlaps(target_net)


def ipset_delete_overlaps(set_name, address):
    try:
        target_network = ipaddress.ip_network(str(address or '').strip(), strict=False)
    except Exception:
        return 0
    if target_network.version != 4:
        return 0
    try:
        result = _run_command(['ipset', 'list', str(set_name)], timeout=3)
    except Exception:
        return 0
    if result.returncode != 0:
        return 0
    deleted = 0
    in_members = False
    for raw_line in (result.stdout or '').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == 'Members:':
            in_members = True
            continue
        if not in_members:
            continue
        member = line.split()[0]
        if member == address or _ipset_member_overlaps_target(member, address):
            if ipset_delete(set_name, member):
                deleted += 1
    return deleted


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
    edge_hosts = int((status or {}).get('watch_edge_hosts') or 0)
    edge_part = f', edge {edge_hosts}' if edge_hosts else ''
    return (
        f'{protocol}: added {int((status or {}).get("added_addresses") or 0)} addresses, '
        f'candidates {int((status or {}).get("candidates") or 0)}, '
        f'cache {int((status or {}).get("cache_entries") or 0)}'
        f'{edge_part}'
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


def _fast_warm_enabled_for_trigger(trigger):
    if not _config_bool('youtube_edge_prefetch_fast_warm_enabled', True):
        return False
    text = str(trigger or '').strip().lower()
    return any(text.startswith(prefix) for prefix in FAST_PREFETCH_TRIGGERS)


def _cache_restore_enabled_for_trigger(trigger):
    if not _config_bool('youtube_edge_prefetch_cache_restore_enabled', True):
        return False
    text = str(trigger or '').strip().lower()
    return any(text.startswith(prefix) for prefix in CACHE_RESTORE_TRIGGERS)


def _cache_restore_only_for_trigger(trigger):
    return str(trigger or '').strip().lower().startswith('manual-restore')


def _cache_restore_satisfies_prefetch(trigger, status):
    if not _fast_warm_enabled_for_trigger(trigger):
        return False
    if not bool((status or {}).get('ok')):
        return False
    if int((status or {}).get('failed_sets') or 0) > 0:
        return False
    min_candidates = _config_int(
        'youtube_edge_prefetch_cache_restore_min_candidates',
        8,
        minimum=1,
    )
    if int((status or {}).get('candidates') or 0) < min_candidates:
        return False
    max_age_seconds = _config_int(
        'youtube_edge_prefetch_cache_restore_max_age_seconds',
        6 * 3600,
        minimum=0,
    )
    if max_age_seconds > 0:
        raw_age_seconds = (status or {}).get('cache_newest_age_seconds')
        newest_age_seconds = max_age_seconds + 1 if raw_age_seconds is None else int(raw_age_seconds)
        if newest_age_seconds > max_age_seconds:
            return False
    return True


def run_prefetch(trigger='manual', *, status_path=None, cache_path=None, unblock_dir=None):
    started_at = time.time()
    cdn_quality_run = str(trigger or '').strip().lower().startswith('cdn-quality')
    if status_path is None:
        status_path = (
            CDN_QUALITY_STATUS_PATH
            if cdn_quality_run
            else _config_str('youtube_edge_prefetch_status_path', STATUS_PATH)
        )
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

    if cdn_quality_run and not _config_bool('youtube_edge_dns_quality_enabled', True):
        status = {'ok': True, 'skipped_reason': 'cdn_quality_disabled', 'warm_mode': 'not_needed'}
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
        )
        if not route_protocol:
            status = {
                'ok': False,
                'route_protocol': '',
                'skipped_reason': 'route_owner_unavailable',
                'available_memory_kb': available_kb,
            }
            status = _normalize_status(status, trigger=trigger, started_at=started_at, next_host_index=next_host_index)
            _write_json_file(status_path, status)
            return status
        fast_warm = _fast_warm_enabled_for_trigger(trigger)
        busy_reason = _background_busy_reason(trigger, fast_warm)
        if busy_reason:
            status = {
                'ok': False,
                'route_protocol': route_protocol,
                'skipped_reason': busy_reason,
                'available_memory_kb': available_kb,
                'warm_mode': 'fast' if fast_warm else 'full',
            }
            status = _normalize_status(status, trigger=trigger, started_at=started_at, next_host_index=next_host_index)
            _write_json_file(status_path, status)
            return status
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

        self_test = None
        if (
            not _self_test_required_for_trigger(trigger)
            and not _manual_prefetch_requested(trigger)
            and not cdn_quality_run
        ):
            status = {
                'ok': True,
                'route_protocol': route_protocol,
                'skipped_reason': 'not_requested',
                'available_memory_kb': available_kb,
                'warm_mode': 'not_needed',
                'candidates': 0,
                'cache_entries': 0,
                'added_addresses': 0,
                'added_sets': 0,
                'deleted_sets': 0,
                'failed_sets': 0,
            }
            status = _normalize_status(status, trigger=trigger, started_at=started_at, next_host_index=next_host_index)
            _write_json_file(status_path, status)
            return status
        if _self_test_required_for_trigger(trigger):
            self_test = youtube_route_self_test(route_protocol)
            if self_test.get('ok') and not _cache_freshness_required_for_trigger(trigger):
                status = {
                    'ok': True,
                    'route_protocol': route_protocol,
                    'skipped_reason': 'self_test_ok',
                    'available_memory_kb': available_kb,
                    'warm_mode': 'not_needed',
                    'self_test': self_test,
                    'candidates': 0,
                    'cache_entries': 0,
                    'added_addresses': 0,
                    'added_sets': 0,
                    'deleted_sets': 0,
                    'failed_sets': 0,
                }
                status = _normalize_status(status, trigger=trigger, started_at=started_at, next_host_index=next_host_index)
                _write_json_file(status_path, status)
                return status

        cache_restore_status = None
        if _cache_restore_enabled_for_trigger(trigger):
            restore_started = time.time()
            cache_restore_status = youtube_edge_prefetch.restore_cached_ipsets(
                route_protocol=route_protocol,
                cache_path=cache_path,
                ipset_contains=ipset_contains,
                ipset_add=ipset_add,
                ipset_delete=ipset_delete,
                ipset_delete_overlaps=ipset_delete_overlaps,
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
                max_addresses=_config_int(
                    'youtube_edge_prefetch_cache_restore_max_addresses',
                    youtube_edge_prefetch.DEFAULT_CACHE_RESTORE_MAX_ADDRESSES,
                    minimum=0,
                ),
                remove_from_other_sets=_config_bool('youtube_edge_prefetch_exclusive_ipsets', True),
                protect_shared_google=_config_bool('youtube_edge_prefetch_protect_shared_google', True),
                require_quality_ok=_config_bool('youtube_edge_prefetch_cache_restore_require_quality_ok', True),
                quality_bad_cooldown_seconds=_config_int(
                    'youtube_edge_prefetch_quality_bad_cooldown_seconds',
                    youtube_edge_prefetch.DEFAULT_QUALITY_BAD_COOLDOWN_SECONDS,
                    minimum=0,
                ),
            )
            cache_restore_status['duration_ms'] = int(max(0.0, time.time() - restore_started) * 1000)
            if _cache_restore_only_for_trigger(trigger) or _cache_restore_satisfies_prefetch(
                trigger,
                cache_restore_status,
            ):
                cache_restore_status['available_memory_kb'] = available_kb
                cache_restore_status['warm_mode'] = 'cache_restore'
                if not _cache_restore_only_for_trigger(trigger):
                    cache_restore_status['prefetch_skipped_reason'] = 'cache_restore_sufficient'
                    cache_restore_status['cache_restored_addresses'] = int(
                        cache_restore_status.get('added_addresses') or 0
                    )
                if self_test is not None:
                    cache_restore_status['self_test'] = self_test
                status = _normalize_status(
                    cache_restore_status,
                    trigger=trigger,
                    started_at=started_at,
                    next_host_index=next_host_index,
                )
                _write_json_file(status_path, status)
                return status

        if cdn_quality_run:
            hosts = quality_hosts_for_run()
        elif fast_warm:
            hosts = prefetch_hosts_for_run(fast=True)
            fast_max_hosts = _config_int(
                'youtube_edge_prefetch_fast_max_hosts_per_run',
                len(FAST_PREFETCH_HOSTS),
                minimum=1,
            )
            hosts = hosts[:min(len(hosts), fast_max_hosts)]
        else:
            hosts, next_host_index = _selected_hosts(
                prefetch_hosts_for_run(),
                _config_int(
                    'youtube_edge_prefetch_max_hosts_per_run',
                    youtube_edge_prefetch.DEFAULT_MAX_HOSTS_PER_RUN,
                    minimum=1,
                ),
                previous_status,
            )
        busy_cpu = _scheduler_full_run_cpu_busy(trigger, fast_warm)
        if busy_cpu is not None:
            status = {
                'ok': False,
                'route_protocol': route_protocol,
                'skipped_reason': 'high_cpu',
                'cpu_percent': round(float(busy_cpu), 2),
                'available_memory_kb': available_kb,
                'warm_mode': 'full',
            }
            status = _normalize_status(status, trigger=trigger, started_at=started_at, next_host_index=next_host_index)
            _write_json_file(status_path, status)
            return status
        busy_load1 = _scheduler_full_run_load_busy(trigger, fast_warm)
        if busy_load1 is not None:
            status = {
                'ok': False,
                'route_protocol': route_protocol,
                'skipped_reason': 'high_load',
                'load1': round(float(busy_load1), 2),
                'available_memory_kb': available_kb,
                'warm_mode': 'full',
            }
            status = _normalize_status(status, trigger=trigger, started_at=started_at, next_host_index=next_host_index)
            _write_json_file(status_path, status)
            return status
        watch_edge_hosts, watch_edge_status = (
            ((), {'enabled': False, 'skipped_reason': 'cdn_quality_only'})
            if cdn_quality_run else collect_watch_edge_hosts(route_protocol)
        )
        quality_hosts = quality_hosts_for_run()
        priority_hosts = tuple(dict.fromkeys(
            (quality_hosts if cdn_quality_run else ()) + tuple(watch_edge_hosts)
        ))
        resolved_address_limit = _config_int(
            'youtube_edge_prefetch_max_resolved_addresses',
            youtube_edge_prefetch.DEFAULT_MAX_RESOLVED_ADDRESSES,
            minimum=1,
        )
        if priority_hosts:
            resolved_address_limit = max(resolved_address_limit, len(priority_hosts) + len(hosts))
        if cdn_quality_run:
            resolved_address_limit = min(
                resolved_address_limit,
                _config_int('youtube_edge_cdn_quality_max_candidates', 6, minimum=1),
            )
        quality_enabled = _config_bool('youtube_edge_prefetch_quality_probe_enabled', True)
        quality_target_ms = _config_int(
            'youtube_edge_prefetch_quality_target_ms',
            youtube_edge_prefetch.DEFAULT_QUALITY_TARGET_MS,
            minimum=100,
        )
        quality_timeout_seconds = _config_int(
            'youtube_edge_cdn_quality_timeout_seconds' if cdn_quality_run else 'youtube_edge_prefetch_quality_timeout_seconds',
            3 if cdn_quality_run else 5,
            minimum=2,
        )
        quality_probe = None
        if quality_enabled:
            def quality_probe(candidate):
                return probe_candidate_quality(
                    candidate,
                    route_protocol,
                    target_ms=quality_target_ms,
                    timeout_seconds=quality_timeout_seconds,
                )
        status = youtube_edge_prefetch.prefetch_once(
            route_protocol=route_protocol,
            cache_path=cache_path,
            hosts=hosts,
            priority_hosts=priority_hosts,
            dns_servers=_config_value('youtube_edge_prefetch_dns_servers', youtube_edge_prefetch.DEFAULT_DNS_SERVERS),
            ipset_contains=ipset_contains,
            ipset_add=ipset_add,
            ipset_delete=ipset_delete,
            ipset_delete_overlaps=ipset_delete_overlaps,
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
            max_resolved_addresses=resolved_address_limit,
            max_candidates=(
                _config_int('youtube_edge_cdn_quality_max_candidates', 6, minimum=1)
                if cdn_quality_run else _config_int(
                    'youtube_edge_prefetch_fast_max_candidates' if fast_warm else 'youtube_edge_prefetch_max_candidates',
                    32 if fast_warm else youtube_edge_prefetch.DEFAULT_MAX_CANDIDATES,
                    minimum=1,
                )
            ),
            cache_before_dns=not fast_warm,
            max_addresses_per_run=(
                _config_int('youtube_edge_cdn_quality_max_candidates', 6, minimum=1)
                if cdn_quality_run else _config_int(
                    'youtube_edge_prefetch_max_addresses_per_run',
                    youtube_edge_prefetch.DEFAULT_MAX_ADDRESSES_PER_RUN,
                    minimum=1,
                )
            ),
            remove_from_other_sets=_config_bool('youtube_edge_prefetch_exclusive_ipsets', True),
            protect_shared_google=_config_bool('youtube_edge_prefetch_protect_shared_google', True),
            quality_probe=quality_probe,
            quality_probe_enabled=quality_enabled,
            quality_probe_existing=fast_warm or cdn_quality_run,
            quality_probe_target_ms=quality_target_ms,
            quality_probe_bad_cooldown_seconds=_config_int(
                'youtube_edge_prefetch_quality_bad_cooldown_seconds',
                youtube_edge_prefetch.DEFAULT_QUALITY_BAD_COOLDOWN_SECONDS,
                minimum=0,
            ),
            quality_probe_max_candidates=(
                _config_int('youtube_edge_cdn_quality_max_candidates', 6, minimum=1)
                if cdn_quality_run else _config_int(
                    'youtube_edge_prefetch_quality_max_candidates',
                    youtube_edge_prefetch.DEFAULT_QUALITY_MAX_CANDIDATES,
                    minimum=1,
                )
            ),
        )
        status['available_memory_kb'] = available_kb
        status['watch_edge_hosts'] = len(watch_edge_hosts)
        status['watch_edge'] = watch_edge_status
        status['cdn_quality'] = sync_quality_hosts_file(cache_path, now=time.time())
        status['warm_mode'] = 'fast' if fast_warm else 'full'
        if self_test is not None:
            status['self_test'] = self_test
        if cache_restore_status is not None:
            status['cache_restore'] = {
                'ok': bool(cache_restore_status.get('ok')),
                'skipped_reason': str(cache_restore_status.get('skipped_reason') or ''),
                'candidates': int(cache_restore_status.get('candidates') or 0),
                'cache_entries': int(cache_restore_status.get('cache_entries') or 0),
                'cache_newest_seen_at': int(cache_restore_status.get('cache_newest_seen_at') or 0),
                'cache_newest_age_seconds': int(cache_restore_status.get('cache_newest_age_seconds') or 0),
                'added_addresses': int(cache_restore_status.get('added_addresses') or 0),
                'added_sets': int(cache_restore_status.get('added_sets') or 0),
                'deleted_sets': int(cache_restore_status.get('deleted_sets') or 0),
                'duration_ms': int(cache_restore_status.get('duration_ms') or 0),
                'skipped_no_quality': int(cache_restore_status.get('cache_restore_skipped_no_quality') or 0),
                'skipped_failed_quality': int(
                    cache_restore_status.get('cache_restore_skipped_failed_quality') or 0
                ),
                'skipped_recent_bad_quality': int(
                    cache_restore_status.get('cache_restore_skipped_recent_bad_quality') or 0
                ),
            }
            status['cache_restored_addresses'] = int(cache_restore_status.get('added_addresses') or 0)
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
