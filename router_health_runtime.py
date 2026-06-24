import json
import os
import subprocess
import threading
import time

try:
    import xray_compat_runtime
except Exception:
    xray_compat_runtime = None

IPSET_STATUS_FILE = '/opt/tmp/bypass_ipset_status.json'
UDP_POLICY_CONFIG_FILE = '/opt/etc/bot/udp_policy.conf'
IPSET_SET_NAMES = (
    'unblocksh',
    'unblockshudp',
    'unblockvmess',
    'unblockvmessudp',
    'unblockvless',
    'unblockvlessudp',
    'unblockvless2',
    'unblockvless2udp',
    'unblocktroj',
    'unblocktrojudp',
)
IPSET_DISPLAY_ORDER = (
    ('unblockvless', 'VLESS'),
    ('unblockvlessudp', 'VLESSUDP'),
    ('unblockvless2', 'VLESS2'),
    ('unblockvless2udp', 'VLESS2UDP'),
    ('unblockvmess', 'VMESS'),
    ('unblockvmessudp', 'VMESSUDP'),
    ('unblocktroj', 'Trojan'),
    ('unblocktrojudp', 'TrojanUDP'),
    ('unblocksh', 'ShadowSocks'),
    ('unblockshudp', 'ShadowSocksUDP'),
)
DNSMASQ_STATE_LABELS = {
    'running': 'запущен',
    'dead': 'не запущен',
    'unavailable': 'недоступен',
    'unknown': 'неизвестно',
}
IPSET_REFRESH_STATUS_LABELS = {
    'success': 'успешно',
    'failure': 'ошибка',
    'partial': 'частично',
    'unknown': 'неизвестно',
}
IPSET_REFRESH_MESSAGE_LABELS = {
    'ipset refresh completed.': 'ipset обновлён.',
    'ipset refresh completed with preserved/fallback sets.': 'ipset обновлён частично: часть наборов сохранена.',
}
TELEGRAM_CALL_TPROXY_DEFAULT_PORTS = {
    'shadowsocks': 11802,
    'vmess': 11815,
    'vless': 11812,
    'vless2': 11814,
    'trojan': 11829,
}
TELEGRAM_CALL_TPROXY_PORT_KEYS = {
    'shadowsocks': 'TELEGRAM_CALL_TPROXY_PORT_SHADOWSOCKS',
    'vmess': 'TELEGRAM_CALL_TPROXY_PORT_VMESS',
    'vless': 'TELEGRAM_CALL_TPROXY_PORT_VLESS',
    'vless2': 'TELEGRAM_CALL_TPROXY_PORT_VLESS2',
    'trojan': 'TELEGRAM_CALL_TPROXY_PORT_TROJAN',
}
TELEGRAM_CALL_ROUTE_KEYS = {
    'shadowsocks': 'BYPASS_TELEGRAM_CALL_ROUTE_SHADOWSOCKS',
    'vmess': 'BYPASS_TELEGRAM_CALL_ROUTE_VMESS',
    'vless': 'BYPASS_TELEGRAM_CALL_ROUTE_VLESS',
    'vless2': 'BYPASS_TELEGRAM_CALL_ROUTE_VLESS2',
    'trojan': 'BYPASS_TELEGRAM_CALL_ROUTE_TROJAN',
}
TELEGRAM_CALL_PROTOCOL_LABELS = {
    'shadowsocks': 'Shadowsocks',
    'vmess': 'Vmess',
    'vless': 'Vless',
    'vless2': 'Vless 2',
    'trojan': 'Trojan',
}
REALTIME_CALL_SERVICE_LABELS = ('Telegram', 'WhatsApp', 'Discord')


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


def run_command_text(command, timeout=2):
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return ''
    return result.stdout or ''


def parse_key_value_text(text):
    values = {}
    for raw_line in (text or '').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def read_key_value_file(path):
    return parse_key_value_text(read_proc_text(path, max_bytes=32768))


def _config_bool(values, key, default=False):
    if key not in values:
        return bool(default)
    return str(values.get(key) or '').strip().lower() not in ('0', 'false', 'no', 'off', '')


def _config_int(values, key, default):
    try:
        return int(str(values.get(key, default)).strip())
    except Exception:
        return int(default)


def parse_listening_ports(netstat_text, ports):
    result = {}
    for port in ports:
        try:
            port_int = int(port)
        except Exception:
            continue
        pattern = f':{port_int} '
        result[port_int] = any(pattern in line or f'.{port_int} ' in line for line in (netstat_text or '').splitlines())
    return result


def telegram_call_proxy_health(
    policy_path=UDP_POLICY_CONFIG_FILE,
    run_text=run_command_text,
    read_values=read_key_value_file,
):
    values = read_values(policy_path)
    enabled = _config_bool(values, 'BYPASS_TELEGRAM_CALL_LEARNING_ENABLED', True)
    tproxy_enabled = _config_bool(values, 'BYPASS_TELEGRAM_CALL_TPROXY_ENABLED', True)
    protocols = [
        proto for proto in TELEGRAM_CALL_TPROXY_DEFAULT_PORTS
        if _config_bool(values, TELEGRAM_CALL_ROUTE_KEYS[proto], False)
    ]
    ports_by_protocol = {
        proto: _config_int(values, TELEGRAM_CALL_TPROXY_PORT_KEYS[proto], default_port)
        for proto, default_port in TELEGRAM_CALL_TPROXY_DEFAULT_PORTS.items()
    }
    active_ports = [ports_by_protocol[proto] for proto in protocols]
    netstat_text = run_text(['netstat', '-lnp'], timeout=2) if active_ports else ''
    port_states = parse_listening_ports(netstat_text, active_ports)
    chain_text = run_text(['iptables', '-t', 'mangle', '-nL', 'BYPASS_TG_CALL_TPROXY'], timeout=2) if protocols else ''
    chain_ok = bool((chain_text or '').strip())
    ports_ok = all(port_states.get(port, False) for port in active_ports) if active_ports else False
    ok = bool(enabled and tproxy_enabled and protocols and chain_ok and ports_ok)
    return {
        'ok': ok,
        'enabled': enabled,
        'tproxy_enabled': tproxy_enabled,
        'chain_ok': chain_ok,
        'services': list(REALTIME_CALL_SERVICE_LABELS),
        'protocols': protocols,
        'ports': {proto: ports_by_protocol[proto] for proto in protocols},
        'port_states': {str(port): bool(port_states.get(port, False)) for port in active_ports},
    }


def telegram_call_proxy_note(health):
    health = health or {}
    if not health.get('enabled'):
        return 'Звонки через TPROXY отключены'
    if not health.get('tproxy_enabled'):
        return 'Звонки через TPROXY отключены'
    protocols = list(health.get('protocols') or [])
    ports = health.get('ports') or {}
    port_states = health.get('port_states') or {}
    if not protocols:
        return 'Звонки через TPROXY ожидают активный Telegram-маршрут'
    working_ports = []
    failed_ports = []
    for proto in protocols:
        port = ports.get(proto)
        label = f'{TELEGRAM_CALL_PROTOCOL_LABELS.get(proto, proto)} {port}'
        if port_states.get(str(port)):
            working_ports.append(label)
        else:
            failed_ports.append(label)
    services = '/'.join(str(item) for item in (health.get('services') or []) if str(item or '').strip())
    service_text = f' для {services}' if services else ''
    if working_ports:
        port_word = 'порте' if len(working_ports) == 1 else 'портах'
        note = f'Звонки через TPROXY работают{service_text} на {port_word}: {", ".join(working_ports)}'
    else:
        note = f'Звонки через TPROXY не работают{service_text}'
    if not health.get('chain_ok'):
        note += '. Цепочка TPROXY не активна'
    if failed_ports:
        port_word = 'порт' if len(failed_ports) == 1 else 'порты'
        note += f'. Не работает {port_word}: {", ".join(failed_ports)}'
    return note


def _compact_multiline_text(text, max_chars=360):
    text = str(text or '').strip()
    if not text:
        return ''
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    compact = '\n'.join(lines[-3:]) if lines else text
    if len(compact) > max_chars:
        return compact[-max_chars:]
    return compact


def compact_core_proxy_health(health):
    health = health or {}
    if not isinstance(health, dict):
        return {}
    compact = {
        'ok': bool(health.get('ok')),
        'xray_state': health.get('xray_state') or '',
        'v2ray_state': health.get('v2ray_state') or '',
        'xray_config_ok': bool(health.get('xray_config_ok')),
        'ports': dict(health.get('ports') or {}),
    }
    if not compact['ok']:
        xray_status = _compact_multiline_text(health.get('xray_status'), max_chars=240)
        xray_config_message = _compact_multiline_text(health.get('xray_config_message'), max_chars=360)
        if xray_status:
            compact['xray_status'] = xray_status
        if xray_config_message:
            compact['xray_config_message'] = xray_config_message
    return compact


def parse_dns_backend(netstat_text):
    lines = [
        line for line in (netstat_text or '').splitlines()
        if ':53' in line or '.53' in line
    ]
    if any('dnsmasq' in line for line in lines):
        return 'dnsmasq'
    if any('ndnproxy' in line for line in lines):
        return 'ndnproxy'
    if lines:
        return 'unknown'
    return 'none'


def read_dnsmasq_state(run_text=run_command_text):
    text = run_text(['/opt/etc/init.d/S56dnsmasq', 'status'], timeout=2)
    lowered = (text or '').lower()
    if 'running' in lowered:
        return 'running'
    if 'dead' in lowered or 'not running' in lowered or 'stopped' in lowered:
        return 'dead'
    if lowered.strip():
        return 'unknown'
    return 'unavailable'


def parse_ipset_member_count(ipset_text):
    count = None
    in_members = False
    for raw_line in (ipset_text or '').splitlines():
        line = raw_line.strip()
        if line.startswith('Number of entries:'):
            try:
                return int(line.split(':', 1)[1].strip().split()[0])
            except Exception:
                return 0
        if in_members:
            if line:
                count = (count or 0) + 1
            continue
        if line == 'Members:':
            in_members = True
            count = 0
    return int(count or 0)


def ipset_member_count(set_name, run_text=run_command_text):
    return parse_ipset_member_count(run_text(['ipset', 'list', set_name], timeout=2))


def load_ipset_refresh_status(status_path=IPSET_STATUS_FILE, read_text=read_proc_text):
    try:
        data = json.loads(read_text(status_path, max_bytes=8192) or '{}')
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def ipset_counts_from_status(status):
    raw_counts = (status or {}).get('counts')
    if not isinstance(raw_counts, dict):
        return {}
    counts = {}
    for set_name in IPSET_SET_NAMES:
        try:
            counts[set_name] = int(raw_counts.get(set_name) or 0)
        except Exception:
            counts[set_name] = 0
    return counts


def read_dns_health(
    *,
    run_text=run_command_text,
    read_text=read_proc_text,
    time_provider=time.time,
    status_path=IPSET_STATUS_FILE,
):
    netstat_text = run_text(['netstat', '-lnptu'], timeout=2)
    backend = parse_dns_backend(netstat_text)
    status = load_ipset_refresh_status(status_path, read_text=read_text)
    counts = ipset_counts_from_status(status)
    if not counts:
        counts = {}
        for set_name in IPSET_SET_NAMES:
            counts[set_name] = ipset_member_count(set_name, run_text=run_text)
    updated_at = int(status.get('updated_at') or 0)
    age_seconds = None
    if updated_at:
        try:
            age_seconds = max(0, int(time_provider()) - updated_at)
        except Exception:
            age_seconds = None
    effective_backend = backend if backend not in ('none', 'unknown') else (status.get('dns_backend') or backend)
    return {
        'backend': effective_backend,
        'listener_backend': backend,
        'dnsmasq_state': read_dnsmasq_state(run_text=run_text),
        'ipset_counts': counts,
        'ipset_updated_at': updated_at,
        'ipset_refresh_age_seconds': age_seconds,
        'ipset_refresh_status': status.get('status') or '',
        'ipset_refresh_message': status.get('message') or '',
    }


def _format_age(seconds):
    if seconds is None:
        return 'возраст неизвестен'
    try:
        seconds = int(seconds)
    except Exception:
        return 'возраст неизвестен'
    if seconds < 60:
        return f'{seconds} сек назад'
    minutes = seconds // 60
    if minutes < 60:
        return f'{minutes} мин назад'
    hours = minutes // 60
    if hours < 48:
        return f'{hours} ч назад'
    return f'{hours // 24} дн назад'


def _dns_backend_detail(backend, dnsmasq_state):
    backend = backend or 'unknown'
    dnsmasq_state = dnsmasq_state or 'unknown'
    dnsmasq_label = DNSMASQ_STATE_LABELS.get(dnsmasq_state, dnsmasq_state)
    if backend == 'ndnproxy' and dnsmasq_state in ('dead', 'unavailable', 'unknown'):
        return 'DNS: ndnproxy (S56dnsmasq не используется)'
    if backend == 'dnsmasq':
        if dnsmasq_state in ('running', 'dead'):
            return f'DNS: dnsmasq (S56dnsmasq {dnsmasq_label})'
        return 'DNS: dnsmasq'
    return f'DNS: {backend}; S56dnsmasq: {dnsmasq_label}'


def dns_health_note(dns_health):
    if not dns_health:
        return ''
    dns_health = dns_health or {}
    backend = dns_health.get('backend') or 'unknown'
    dnsmasq_state = dns_health.get('dnsmasq_state') or 'unknown'
    details = [_dns_backend_detail(backend, dnsmasq_state)]
    refresh_status = dns_health.get('ipset_refresh_status') or 'unknown'
    refresh_status_label = IPSET_REFRESH_STATUS_LABELS.get(refresh_status, refresh_status)
    updated_at = int(dns_health.get('ipset_updated_at') or 0)
    if updated_at:
        age_text = _format_age(dns_health.get("ipset_refresh_age_seconds"))
        if refresh_status and refresh_status != 'success':
            details.append(f'ipset обновлён: {age_text} ({refresh_status_label})')
        else:
            details.append(f'ipset обновлён: {age_text}')
    else:
        details.append('ipset: нет файла состояния')
    counts = dns_health.get('ipset_counts') or {}
    if counts:
        ordered = [
            f'{label}={int(counts.get(name) or 0)}'
            for name, label in IPSET_DISPLAY_ORDER
            if name in counts
        ]
        details.append('записи ipset: ' + ', '.join(ordered))
    raw_message = str(dns_health.get('ipset_refresh_message') or '').strip()
    message = IPSET_REFRESH_MESSAGE_LABELS.get(raw_message, raw_message)
    already_shown = refresh_status == 'success' and raw_message == 'ipset refresh completed.'
    detail_texts = {part.rstrip('.') for part in details}
    if message and not already_shown and message.rstrip('.') not in detail_texts:
        details.append(message.rstrip('.'))
    return '; '.join(part.rstrip('.') for part in details if part)


def _current_load_text(load_text):
    value = str(load_text or '').strip()
    if not value:
        return ''
    return value.split('/', 1)[0].strip()


def build_router_health_payload(
    *,
    meminfo,
    ndmc_system,
    load_text,
    bot_rss_kb,
    probe_progress,
    temp_xray_count,
    dns_health=None,
    core_proxy_health=None,
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
    if total_mb:
        memory_text = f'Память: доступно {available_mb} MB, занято {used_mb} из {total_mb} MB'
    else:
        memory_text = 'Память: данные недоступны'
    details = []
    if used_mb:
        details.append(f'Занято по данным роутера: {used_mb} MB ({used_percent}%)')
    if free_mb:
        details.append(f'Свободно: {free_mb} MB')
    if available_mb:
        details.append(f'Доступно для приложений: {available_mb} MB ({available_percent}%)')
    if cache_mb:
        details.append(f'Кэш и буферы: {cache_mb} MB')
    if load_text:
        details.append(f'Нагрузка CPU: {_current_load_text(load_text)}')
    if bot_rss_mb:
        details.append(f'Бот использует {bot_rss_mb} MB RAM')
    if swap_total_kb:
        swap_total_mb = int(round(swap_total_kb / 1024.0))
        details.append(f'Swap: занято {swap_used_mb} из {swap_total_mb} MB')
    dns_note = dns_health_note(dns_health)
    core_proxy_health = core_proxy_health or {}
    if xray_compat_runtime is not None and core_proxy_health:
        core_proxy_note = xray_compat_runtime.core_proxy_note(core_proxy_health)
    elif core_proxy_health:
        core_proxy_note = 'Xray: health module unavailable.'
    else:
        core_proxy_note = ''
    telegram_call_health = dict(core_proxy_health.get('telegram_call') or {})
    telegram_call_note = telegram_call_proxy_note(telegram_call_health) if telegram_call_health else ''
    compact_core_health = compact_core_proxy_health(core_proxy_health)
    return {
        'memory_text': memory_text,
        'note': '; '.join(details),
        'dns_note': dns_note,
        'core_proxy_note': core_proxy_note,
        'core_proxy_health': compact_core_health,
        'telegram_call_note': telegram_call_note,
        'telegram_call_health': telegram_call_health,
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
        'dns_backend': (dns_health or {}).get('backend') or '',
        'dns_listener_backend': (dns_health or {}).get('listener_backend') or '',
        'dnsmasq_state': (dns_health or {}).get('dnsmasq_state') or '',
        'ipset_counts': dict((dns_health or {}).get('ipset_counts') or {}),
        'ipset_updated_at': int((dns_health or {}).get('ipset_updated_at') or 0),
        'ipset_refresh_age_seconds': (dns_health or {}).get('ipset_refresh_age_seconds'),
        'ipset_refresh_status': (dns_health or {}).get('ipset_refresh_status') or '',
        'ipset_refresh_message': (dns_health or {}).get('ipset_refresh_message') or '',
    }


class RouterHealthRuntime:
    def __init__(
        self,
        cache_ttl=5.0,
        time_provider=time.time,
        core_proxy_cache_ttl=60.0,
        dns_cache_ttl=45.0,
        ndmc_cache_ttl=30.0,
    ):
        self.cache_ttl = float(cache_ttl or 0)
        self.core_proxy_cache_ttl = float(core_proxy_cache_ttl or 0)
        self.dns_cache_ttl = float(dns_cache_ttl or 0)
        self.ndmc_cache_ttl = float(ndmc_cache_ttl or 0)
        self.time_provider = time_provider
        self._lock = threading.Lock()
        self._cache = {'timestamp': 0, 'payload': None}
        self._core_proxy_cache = {'timestamp': 0, 'payload': None}
        self._dns_cache = {'timestamp': 0, 'payload': None}
        self._ndmc_cache = {'timestamp': 0, 'payload': None}

    def _cached_payload(self, cache_name, ttl, now, loader):
        cache = getattr(self, cache_name)
        cached = cache.get('payload')
        if cached is not None and now - float(cache.get('timestamp') or 0) < float(ttl or 0):
            return dict(cached) if isinstance(cached, dict) else cached
        payload = loader()
        setattr(self, cache_name, {'timestamp': now, 'payload': dict(payload) if isinstance(payload, dict) else payload})
        return dict(payload) if isinstance(payload, dict) else payload

    def _core_proxy_snapshot(self, now):
        def load_core_proxy():
            try:
                if xray_compat_runtime is None:
                    payload = {
                        'ok': False,
                        'xray_state': 'unknown',
                        'xray_config_ok': False,
                        'xray_config_message': 'xray health module unavailable',
                        'ports': {},
                    }
                else:
                    payload = xray_compat_runtime.core_proxy_health()
                payload['telegram_call'] = telegram_call_proxy_health()
                return payload
            except Exception as exc:
                return {
                    'ok': False,
                    'xray_state': 'error',
                    'xray_config_ok': False,
                    'xray_config_message': str(exc),
                    'ports': {},
                    'telegram_call': {'ok': False, 'error': str(exc)},
                }

        return self._cached_payload('_core_proxy_cache', self.core_proxy_cache_ttl, now, load_core_proxy)

    def _dns_snapshot(self, now):
        return self._cached_payload(
            '_dns_cache',
            self.dns_cache_ttl,
            now,
            lambda: read_dns_health(time_provider=self.time_provider),
        )

    def _ndmc_snapshot(self, now):
        return self._cached_payload(
            '_ndmc_cache',
            self.ndmc_cache_ttl,
            now,
            read_ndmc_system_snapshot,
        )

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
            ndmc_system=self._ndmc_snapshot(now),
            load_text=' / '.join((read_proc_text('/proc/loadavg').split()[:3] or [])),
            bot_rss_kb=process_rss_kb('self'),
            probe_progress=probe_progress,
            temp_xray_count=count_proc_cmdline('/tmp/bypass_pool_probe_') if probe_running else 0,
            dns_health=self._dns_snapshot(now),
            core_proxy_health=self._core_proxy_snapshot(now),
        )
        with self._lock:
            self._cache['timestamp'] = now
            self._cache['payload'] = payload
        return dict(payload)

    def invalidate(self):
        with self._lock:
            self._cache = {'timestamp': 0, 'payload': None}
            self._core_proxy_cache = {'timestamp': 0, 'payload': None}
            self._dns_cache = {'timestamp': 0, 'payload': None}
            self._ndmc_cache = {'timestamp': 0, 'payload': None}
