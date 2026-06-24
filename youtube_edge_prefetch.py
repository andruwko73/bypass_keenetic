import ipaddress
import json
import os
import re
import socket
import subprocess
import time


DEFAULT_PREFETCH_HOSTS = (
    'www.youtube.com',
    'm.youtube.com',
    'youtubei.googleapis.com',
    'youtubei-att.googleapis.com',
    'jnn-pa.googleapis.com',
    'play-fe.googleapis.com',
    'i.ytimg.com',
    's.ytimg.com',
    'yt3.ggpht.com',
    'www.gstatic.com',
    'manifest.googlevideo.com',
    'redirector.googlevideo.com',
)
DEFAULT_DNS_SERVERS = ('local', '1.1.1.1', '8.8.8.8')
DEFAULT_CACHE_TTL_SECONDS = 72 * 3600
DEFAULT_MAX_CACHE_ENTRIES = 128
DEFAULT_MAX_HOSTS_PER_RUN = 12
DEFAULT_MAX_RESOLVED_ADDRESSES = 32
DEFAULT_MAX_CANDIDATES = 64
DEFAULT_MAX_ADDRESSES_PER_RUN = 16
DEFAULT_WATCH_EDGE_MAX_HOSTS = 6
DEFAULT_QUALITY_TARGET_MS = 1000
DEFAULT_QUALITY_BAD_COOLDOWN_SECONDS = 3600
DEFAULT_QUALITY_MAX_CANDIDATES = 24
QUALITY_CACHE_FIELDS = (
    'quality_last_checked',
    'quality_last_ok',
    'quality_last_fail',
    'quality_latency_ms',
    'quality_success_count',
    'quality_fail_count',
    'quality_fail_reason',
)
YOUTUBE_OWNED_HOSTS = (
    'youtubei.googleapis.com',
    'youtubei-att.googleapis.com',
    'youtube.googleapis.com',
    'youtubeembeddedplayer.googleapis.com',
    'jnn-pa.googleapis.com',
    'play-fe.googleapis.com',
)
YOUTUBE_OWNED_SUFFIXES = (
    'youtube.com',
    'youtube-nocookie.com',
    'youtubeeducation.com',
    'youtu.be',
    'googlevideo.com',
    'ytimg.com',
    'ggpht.com',
)
WATCH_EDGE_HOST_RE = re.compile(
    r'(?<![a-z0-9.-])((?:[a-z0-9-]+\.)*(?:googlevideo\.com|c\.youtube\.com))(?![a-z0-9.-])',
    re.IGNORECASE,
)

ROUTE_IPSETS = {
    'shadowsocks': ('unblocksh', 'unblockshudp'),
    'vmess': ('unblockvmess', 'unblockvmessudp'),
    'vless': ('unblockvless', 'unblockvlessudp'),
    'vless2': ('unblockvless2', 'unblockvless2udp'),
    'trojan': ('unblocktroj', 'unblocktrojudp'),
}


def _as_tuple(value, default=()):
    if value is None:
        return tuple(default)
    if isinstance(value, str):
        return (value,)
    try:
        return tuple(value)
    except Exception:
        return tuple(default)


def normalize_hosts(hosts):
    normalized = []
    seen = set()
    for item in _as_tuple(hosts, DEFAULT_PREFETCH_HOSTS):
        host = str(item or '').strip().lower().strip('.')
        if not host or '/' in host or ':' in host:
            continue
        if not re.match(r'^[a-z0-9_.-]+\.[a-z0-9_.-]+$', host):
            continue
        if host not in seen:
            seen.add(host)
            normalized.append(host)
    return tuple(normalized)


def youtube_owned_host(host):
    normalized = normalize_hosts((host,))
    if not normalized:
        return False
    host = normalized[0]
    if host in YOUTUBE_OWNED_HOSTS:
        return True
    return any(host == suffix or host.endswith('.' + suffix) for suffix in YOUTUBE_OWNED_SUFFIXES)


def extract_watch_edge_hosts(text, *, max_hosts=DEFAULT_WATCH_EDGE_MAX_HOSTS):
    max_hosts = max(0, int(max_hosts or 0))
    if max_hosts <= 0:
        return ()
    normalized = []
    seen = set()
    for match in WATCH_EDGE_HOST_RE.finditer(str(text or '')):
        host = match.group(1).strip().lower().strip('.')
        if host in ('googlevideo.com', 'c.youtube.com'):
            continue
        valid_hosts = normalize_hosts((host,))
        if not valid_hosts:
            continue
        host = valid_hosts[0]
        if host in seen:
            continue
        seen.add(host)
        normalized.append(host)
        if len(normalized) >= max_hosts:
            break
    return tuple(normalized)


def normalize_dns_servers(dns_servers):
    normalized = []
    seen = set()
    for item in _as_tuple(dns_servers, DEFAULT_DNS_SERVERS):
        value = str(item or '').strip().lower()
        if value in ('', 'local', 'system'):
            value = 'local'
        elif not _is_ipv4(value, allow_private=True):
            continue
        if value not in seen:
            seen.add(value)
            normalized.append(value)
    return tuple(normalized) or ('local',)


def _is_ipv4(value, allow_private=False, reject_addresses=None):
    try:
        ip_obj = ipaddress.ip_address(str(value or '').strip())
    except Exception:
        return False
    if ip_obj.version != 4:
        return False
    if str(ip_obj) in set(reject_addresses or ()):
        return False
    if ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_unspecified:
        return False
    if not allow_private and not ip_obj.is_global:
        return False
    return True


def is_public_ipv4(value, reject_addresses=None):
    return _is_ipv4(value, allow_private=False, reject_addresses=reject_addresses)


def parse_ipv4_tokens(text, reject_addresses=None):
    addresses = []
    seen = set()
    for token in re.findall(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', str(text or '')):
        if token not in seen and is_public_ipv4(token, reject_addresses=reject_addresses):
            seen.add(token)
            addresses.append(token)
    return addresses


def _run_command(args, timeout):
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=timeout,
        check=False,
    )


def _result_stdout(result):
    if isinstance(result, str):
        return result, 0
    return getattr(result, 'stdout', '') or '', int(getattr(result, 'returncode', 0) or 0)


def resolve_host_addresses(
    host,
    dns_servers=DEFAULT_DNS_SERVERS,
    *,
    getaddrinfo=None,
    run_command=None,
    command_timeout=3,
):
    host = normalize_hosts((host,))
    if not host:
        return []
    host = host[0]
    getaddrinfo = getaddrinfo or socket.getaddrinfo
    run_command = run_command or _run_command
    addresses = []
    seen = set()
    reject_addresses = {server for server in normalize_dns_servers(dns_servers) if server != 'local'}

    def add(address):
        if address in seen:
            return
        if is_public_ipv4(address, reject_addresses=reject_addresses):
            seen.add(address)
            addresses.append(address)

    for dns_server in normalize_dns_servers(dns_servers):
        if dns_server == 'local':
            try:
                infos = getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
            except Exception:
                infos = []
            for item in infos:
                try:
                    add(item[4][0])
                except Exception:
                    continue
            continue

        server_added = 0
        commands = (
            ['dig', '+time=2', '+tries=1', '+short', 'A', host, '@' + dns_server],
            ['nslookup', host, dns_server],
        )
        for command in commands:
            try:
                stdout, returncode = _result_stdout(run_command(command, command_timeout))
            except Exception:
                stdout, returncode = '', 1
            if returncode != 0:
                continue
            before = len(addresses)
            for address in parse_ipv4_tokens(stdout, reject_addresses=reject_addresses):
                add(address)
            server_added += len(addresses) - before
            if server_added:
                break
    return addresses


def _fresh_cache(now=None):
    return {'version': 1, 'updated_at': int(now or time.time()), 'entries': {}}


def _entry_last_seen(entry):
    try:
        return float((entry or {}).get('last_seen') or 0.0)
    except Exception:
        return 0.0


def _bounded_int(value, default=0, *, minimum=0, maximum=None):
    try:
        number = int(value)
    except Exception:
        number = int(default)
    number = max(int(minimum), number)
    if maximum is not None:
        number = min(int(maximum), number)
    return number


def _clean_cache_quality_fields(entry):
    cleaned = {}
    for field in QUALITY_CACHE_FIELDS:
        if field not in (entry or {}):
            continue
        value = entry.get(field)
        if field == 'quality_fail_reason':
            cleaned[field] = str(value or '')[:40]
        else:
            cleaned[field] = _bounded_int(value, 0, minimum=0)
    return cleaned


def prune_cache(cache, *, now=None, ttl_seconds=DEFAULT_CACHE_TTL_SECONDS, max_entries=DEFAULT_MAX_CACHE_ENTRIES):
    now = float(now or time.time())
    ttl_seconds = max(60, int(ttl_seconds or DEFAULT_CACHE_TTL_SECONDS))
    max_entries = max(1, int(max_entries or DEFAULT_MAX_CACHE_ENTRIES))
    raw_entries = cache.get('entries') if isinstance(cache, dict) else {}
    entries = {}
    cutoff = now - ttl_seconds
    for address, entry in (raw_entries or {}).items():
        if not is_public_ipv4(address):
            continue
        last_seen = _entry_last_seen(entry)
        if last_seen < cutoff:
            continue
        cleaned_entry = {
            'host': str((entry or {}).get('host') or '')[:96],
            'source': str((entry or {}).get('source') or '')[:40],
            'last_seen': int(last_seen or now),
            'hits': max(1, int((entry or {}).get('hits') or 1)),
        }
        cleaned_entry.update(_clean_cache_quality_fields(entry or {}))
        entries[str(address)] = cleaned_entry
    sorted_entries = sorted(
        entries.items(),
        key=lambda item: (int(item[1].get('last_seen') or 0), int(item[1].get('hits') or 0)),
        reverse=True,
    )[:max_entries]
    return {'version': 1, 'updated_at': int(now), 'entries': dict(sorted_entries)}


def load_cache(path, *, now=None, ttl_seconds=DEFAULT_CACHE_TTL_SECONDS, max_entries=DEFAULT_MAX_CACHE_ENTRIES):
    if not path:
        return _fresh_cache(now)
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as file:
            cache = json.load(file)
    except Exception:
        cache = _fresh_cache(now)
    if not isinstance(cache, dict):
        cache = _fresh_cache(now)
    return prune_cache(cache, now=now, ttl_seconds=ttl_seconds, max_entries=max_entries)


def save_cache(path, cache, *, now=None, ttl_seconds=DEFAULT_CACHE_TTL_SECONDS, max_entries=DEFAULT_MAX_CACHE_ENTRIES):
    if not path:
        return False
    cache = prune_cache(cache, now=now, ttl_seconds=ttl_seconds, max_entries=max_entries)
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as file:
            json.dump(cache, file, ensure_ascii=False, separators=(',', ':'))
        os.replace(tmp_path, path)
        return True
    except Exception:
        return False


def _cache_candidate(cache, address, host, source, now):
    entries = cache.setdefault('entries', {})
    entry = entries.get(address) or {}
    updated = {
        'host': str(host or entry.get('host') or '')[:96],
        'source': str(source or entry.get('source') or '')[:40],
        'last_seen': int(now),
        'hits': max(1, int(entry.get('hits') or 0) + 1),
    }
    updated.update(_clean_cache_quality_fields(entry))
    entries[address] = updated


def _add_candidate(candidates, seen, address, host, source, from_cache=False, max_candidates=DEFAULT_MAX_CANDIDATES):
    if address in seen or len(candidates) >= max_candidates:
        return
    seen.add(address)
    candidates.append({
        'address': address,
        'host': str(host or ''),
        'source': str(source or ''),
        'from_cache': bool(from_cache),
    })


def collect_prefetch_candidates(
    *,
    hosts=DEFAULT_PREFETCH_HOSTS,
    priority_hosts=(),
    dns_servers=DEFAULT_DNS_SERVERS,
    cache=None,
    now=None,
    max_hosts_per_run=DEFAULT_MAX_HOSTS_PER_RUN,
    max_resolved_addresses=DEFAULT_MAX_RESOLVED_ADDRESSES,
    max_candidates=DEFAULT_MAX_CANDIDATES,
    getaddrinfo=None,
    run_command=None,
):
    now = float(now or time.time())
    cache = prune_cache(cache or _fresh_cache(now), now=now)
    candidates = []
    seen = set()
    max_candidates = max(1, int(max_candidates or DEFAULT_MAX_CANDIDATES))
    max_hosts_per_run = max(1, int(max_hosts_per_run or DEFAULT_MAX_HOSTS_PER_RUN))
    max_resolved_addresses = max(1, int(max_resolved_addresses or DEFAULT_MAX_RESOLVED_ADDRESSES))
    resolved_count = 0

    def resolve_hosts(candidate_hosts, source, *, limit=None):
        nonlocal resolved_count
        host_list = normalize_hosts(candidate_hosts)
        if limit is not None:
            host_list = host_list[:max(0, int(limit or 0))]
        for host in host_list:
            if resolved_count >= max_resolved_addresses:
                break
            for address in resolve_host_addresses(
                host,
                dns_servers,
                getaddrinfo=getaddrinfo,
                run_command=run_command,
            ):
                _cache_candidate(cache, address, host, source, now)
                _add_candidate(candidates, seen, address, host, source, max_candidates=max_candidates)
                resolved_count += 1
                if resolved_count >= max_resolved_addresses:
                    break

    resolve_hosts(priority_hosts, 'watch')

    cached_entries = sorted(
        cache.get('entries', {}).items(),
        key=lambda item: _entry_last_seen(item[1]),
        reverse=True,
    )
    for address, entry in cached_entries:
        _add_candidate(
            candidates,
            seen,
            address,
            (entry or {}).get('host'),
            (entry or {}).get('source') or 'cache',
            from_cache=True,
            max_candidates=max_candidates,
        )

    resolve_hosts(hosts, 'dns', limit=max_hosts_per_run)

    return candidates, prune_cache(cache, now=now)


def _target_sets(route_protocol):
    return ROUTE_IPSETS.get(str(route_protocol or '').strip().lower()) or ()


def _other_sets(route_protocol):
    protocol = str(route_protocol or '').strip().lower()
    sets = []
    for proto, names in ROUTE_IPSETS.items():
        if proto == protocol:
            continue
        sets.extend(names)
    return tuple(sets)


def _recent_quality_failure(entry, now, cooldown_seconds):
    cooldown_seconds = max(0, int(cooldown_seconds or 0))
    if cooldown_seconds <= 0:
        return False
    try:
        last_fail = float((entry or {}).get('quality_last_fail') or 0.0)
        last_ok = float((entry or {}).get('quality_last_ok') or 0.0)
    except Exception:
        return False
    return last_fail > last_ok and (float(now) - last_fail) < cooldown_seconds


def _normalize_quality_result(result):
    if isinstance(result, bool):
        result = {'ok': result}
    if not isinstance(result, dict):
        result = {'ok': False, 'reason': 'failed'}
    ok = bool(result.get('ok'))
    reason = str(result.get('reason') or ('ok' if ok else 'failed')).strip().lower()[:40]
    latency_ms = _bounded_int(result.get('latency_ms'), 0, minimum=0)
    return {
        'ok': ok,
        'reason': reason or ('ok' if ok else 'failed'),
        'latency_ms': latency_ms,
    }


def _quality_reject_reason(result, target_ms):
    if not result.get('ok'):
        reason = str(result.get('reason') or 'failed').strip().lower()
        if 'slow' in reason:
            return 'slow'
        if 'timeout' in reason:
            return 'timeout'
        if 'eof' in reason or 'tls' in reason or 'ssl' in reason:
            return 'eof'
        return 'failed'
    latency_ms = int(result.get('latency_ms') or 0)
    if latency_ms > 0 and latency_ms > int(target_ms or DEFAULT_QUALITY_TARGET_MS):
        return 'slow'
    return ''


def _update_quality_cache(cache, candidate, result, now, *, accepted):
    address = str((candidate or {}).get('address') or '').strip()
    if not is_public_ipv4(address):
        return
    entries = cache.setdefault('entries', {})
    entry = dict(entries.get(address) or {})
    entry['host'] = str((candidate or {}).get('host') or entry.get('host') or '')[:96]
    entry['source'] = str((candidate or {}).get('source') or entry.get('source') or '')[:40]
    entry['last_seen'] = int(now)
    entry['hits'] = max(1, int(entry.get('hits') or 1))
    entry['quality_last_checked'] = int(now)
    latency_ms = _bounded_int((result or {}).get('latency_ms'), 0, minimum=0)
    if latency_ms:
        entry['quality_latency_ms'] = latency_ms
    if accepted:
        entry['quality_last_ok'] = int(now)
        entry['quality_success_count'] = _bounded_int(entry.get('quality_success_count'), 0) + 1
        entry['quality_fail_reason'] = ''
    else:
        entry['quality_last_fail'] = int(now)
        entry['quality_fail_count'] = _bounded_int(entry.get('quality_fail_count'), 0) + 1
        entry['quality_fail_reason'] = str((result or {}).get('reason') or 'failed')[:40]
    entries[address] = entry


def prefetch_once(
    *,
    route_protocol,
    cache_path='',
    hosts=DEFAULT_PREFETCH_HOSTS,
    priority_hosts=(),
    dns_servers=DEFAULT_DNS_SERVERS,
    ipset_contains=None,
    ipset_add=None,
    ipset_delete=None,
    delete_conntrack=None,
    now_provider=None,
    max_cache_entries=DEFAULT_MAX_CACHE_ENTRIES,
    cache_ttl_seconds=DEFAULT_CACHE_TTL_SECONDS,
    max_hosts_per_run=DEFAULT_MAX_HOSTS_PER_RUN,
    max_resolved_addresses=DEFAULT_MAX_RESOLVED_ADDRESSES,
    max_candidates=DEFAULT_MAX_CANDIDATES,
    max_addresses_per_run=DEFAULT_MAX_ADDRESSES_PER_RUN,
    remove_from_other_sets=True,
    protect_shared_google=True,
    quality_probe=None,
    quality_probe_enabled=False,
    quality_probe_target_ms=DEFAULT_QUALITY_TARGET_MS,
    quality_probe_bad_cooldown_seconds=DEFAULT_QUALITY_BAD_COOLDOWN_SECONDS,
    quality_probe_max_candidates=DEFAULT_QUALITY_MAX_CANDIDATES,
    getaddrinfo=None,
    run_command=None,
):
    now_provider = now_provider or time.time
    now = float(now_provider())
    protocol = str(route_protocol or '').strip().lower()
    target_sets = _target_sets(protocol)
    status = {
        'ok': False,
        'route_protocol': protocol,
        'last_run_at': now,
        'skipped_reason': '',
        'candidates': 0,
        'cache_entries': 0,
        'added_addresses': 0,
        'added_sets': 0,
        'deleted_sets': 0,
        'failed_sets': 0,
        'priority_hosts': len(normalize_hosts(priority_hosts)),
        'shared_candidates_skipped': 0,
    }
    quality_enabled = bool(quality_probe_enabled and quality_probe is not None)
    quality_target_ms = max(100, int(quality_probe_target_ms or DEFAULT_QUALITY_TARGET_MS))
    quality_bad_cooldown_seconds = max(0, int(
        quality_probe_bad_cooldown_seconds or DEFAULT_QUALITY_BAD_COOLDOWN_SECONDS
    ))
    quality_max_candidates = max(1, int(quality_probe_max_candidates or DEFAULT_QUALITY_MAX_CANDIDATES))
    if quality_enabled:
        status.update({
            'quality_probe_enabled': True,
            'quality_target_ms': quality_target_ms,
            'quality_tested': 0,
            'quality_accepted': 0,
            'quality_rejected_slow': 0,
            'quality_rejected_eof': 0,
            'quality_rejected_timeout': 0,
            'quality_rejected_failed': 0,
            'quality_rejected_cached': 0,
            'quality_skipped_limit': 0,
            'quality_avg_latency_ms': 0,
        })
    if not target_sets:
        status['skipped_reason'] = 'unsupported_route_protocol'
        return status
    if ipset_contains is None or ipset_add is None:
        status['skipped_reason'] = 'missing_ipset_callbacks'
        return status

    cache = load_cache(
        cache_path,
        now=now,
        ttl_seconds=cache_ttl_seconds,
        max_entries=max_cache_entries,
    )
    candidates, cache = collect_prefetch_candidates(
        hosts=hosts,
        priority_hosts=priority_hosts,
        dns_servers=dns_servers,
        cache=cache,
        now=now,
        max_hosts_per_run=max_hosts_per_run,
        max_resolved_addresses=max_resolved_addresses,
        max_candidates=max_candidates,
        getaddrinfo=getaddrinfo,
        run_command=run_command,
    )
    status['candidates'] = len(candidates)
    status['cache_entries'] = len(cache.get('entries') or {})
    max_addresses_per_run = max(1, int(max_addresses_per_run or DEFAULT_MAX_ADDRESSES_PER_RUN))
    touched_addresses = set()
    quality_latency_total = 0
    quality_latency_count = 0

    for candidate in candidates:
        if len(touched_addresses) >= max_addresses_per_run:
            break
        address = str(candidate.get('address') or '').strip()
        if not is_public_ipv4(address):
            continue
        if protect_shared_google and not youtube_owned_host(candidate.get('host')):
            status['shared_candidates_skipped'] += 1
            continue
        missing_sets = []
        for set_name in target_sets:
            try:
                present = bool(ipset_contains(set_name, address))
            except Exception:
                present = False
            if not present:
                missing_sets.append(set_name)
        if not missing_sets:
            continue

        if quality_enabled:
            entry = (cache.get('entries') or {}).get(address) or {}
            if _recent_quality_failure(entry, now, quality_bad_cooldown_seconds):
                status['quality_rejected_cached'] += 1
                continue
            if status['quality_tested'] >= quality_max_candidates:
                status['quality_skipped_limit'] += 1
                continue
            try:
                quality_result = _normalize_quality_result(quality_probe(dict(candidate)))
            except Exception as exc:
                quality_result = {'ok': False, 'reason': str(exc)[:40] or 'failed', 'latency_ms': 0}
            status['quality_tested'] += 1
            if quality_result.get('latency_ms'):
                quality_latency_total += int(quality_result.get('latency_ms') or 0)
                quality_latency_count += 1
            reject_reason = _quality_reject_reason(quality_result, quality_target_ms)
            _update_quality_cache(cache, candidate, quality_result, now, accepted=not reject_reason)
            if reject_reason:
                counter = 'quality_rejected_' + reject_reason
                status[counter] = int(status.get(counter) or 0) + 1
                continue
            status['quality_accepted'] += 1

        if remove_from_other_sets and ipset_delete is not None:
            for set_name in _other_sets(protocol):
                try:
                    if ipset_delete(set_name, address):
                        status['deleted_sets'] += 1
                except Exception:
                    continue

        added_any = False
        for set_name in missing_sets:
            try:
                result = ipset_add(set_name, address)
                ok = bool(result[0] if isinstance(result, tuple) else result)
            except Exception:
                ok = False
            if ok:
                status['added_sets'] += 1
                added_any = True
            else:
                status['failed_sets'] += 1
        if added_any:
            touched_addresses.add(address)
            if delete_conntrack is not None:
                try:
                    delete_conntrack(address)
                except Exception:
                    pass

    status['added_addresses'] = len(touched_addresses)
    if quality_enabled and quality_latency_count:
        status['quality_avg_latency_ms'] = int(quality_latency_total / quality_latency_count)
    save_cache(
        cache_path,
        cache,
        now=now,
        ttl_seconds=cache_ttl_seconds,
        max_entries=max_cache_entries,
    )
    status['ok'] = True
    return status
