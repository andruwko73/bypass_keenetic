"""Bounded DNS queue for one transactional ipset refresh; cache lives in RAM."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import time

SETS = ('unblocksh', 'unblockvmess', 'unblockvless', 'unblockvless2', 'unblocktroj', 'unblockhy2')
V6 = ('unblocksh6', 'unblockvmess6', 'unblockvless6', 'unblockvless2v6', 'unblocktroj6', 'unblockhy26')
YOUTUBE = ('youtube.com', 'youtube-nocookie.com', 'youtu.be', 'googlevideo.com', 'ytimg.com', 'ggpht.com')
YOUTUBE_EXACT = ('youtube.googleapis.com', 'youtubei.googleapis.com', 'youtube-ui.l.google.com', 'wide-youtube.l.google.com')
MAX_CACHE_BYTES, MAX_QUERIES = 2_000_000, 32768


def youtube_domain(domain, family='A'):
    return (domain in YOUTUBE_EXACT or any(domain == suffix or domain.endswith('.' + suffix) for suffix in YOUTUBE)
            or family == 'AAAA' and domain in ('yt3.googleusercontent.com', 'yt4.googleusercontent.com'))


def address(value, family):
    try:
        ip = ipaddress.ip_address(value)
    except (ValueError, TypeError):
        return None
    if ip.version != (4 if family == 'A' else 6):
        return None
    # Match the established shell filter, including its 172.16-only exclusion.
    if re.search(r'localhost|^0\.|^127\.|^10\.|^172\.16\.|^192\.168\.|^::|^fc..:|^fd..:|^fe..:', str(ip)):
        return None
    return str(ip)


def query_dns_dig(query, *, run=subprocess.run):
    domain, family, host, port = query
    if not re.fullmatch(r'[a-z0-9_.-]{1,253}', domain) or domain.startswith('-'):
        return [], 0, False
    try:
        response = run(['dig', '+time=2', '+tries=1', '+noall', '+answer', '+comments',
                        family, domain, '@' + host, '-p', str(port)], capture_output=True,
                       timeout=3.5, check=False, text=True)
    except (OSError, subprocess.SubprocessError):
        return [], 0, False
    if response.returncode or not re.search(r'status: (NOERROR|NXDOMAIN),', response.stdout):
        return [], 0, False
    values, ttls = [], []
    for line in response.stdout.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[2] != 'IN':
            continue
        try:
            ttl = max(0, int(fields[1]))
        except ValueError:
            continue
        if fields[3] == 'CNAME':
            ttls.append(ttl)
        elif fields[3] == family:
            ip = address(fields[4], family)
            if ip:
                values.append(ip); ttls.append(ttl)
    # Empty/negative answers are not cached. Timeouts cannot become NXDOMAIN.
    return sorted(set(values)), min([300, *ttls]) if values else 0, True


def read_name(packet, offset):
    labels, end, seen = [], None, set()
    for _ in range(128):
        if offset in seen or offset >= len(packet):
            raise ValueError('Invalid DNS name')
        seen.add(offset)
        size = packet[offset]; offset += 1
        if size == 0:
            return '.'.join(labels).lower(), end or offset
        if size & 0xc0 == 0xc0:
            if offset >= len(packet):
                raise ValueError('Truncated DNS pointer')
            end = end or offset + 1
            offset = ((size & 0x3f) << 8) | packet[offset]
            continue
        if size > 63 or offset + size > len(packet):
            raise ValueError('Invalid DNS label')
        labels.append(packet[offset:offset + size].decode('ascii'))
        offset += size
    raise ValueError('DNS name limit')


def parse_response(packet, transaction, domain, family):
    if len(packet) < 12:
        raise ValueError('Truncated DNS header')
    ident, flags, qd, an, ns, ar = struct.unpack('!6H', packet[:12])
    if ident != transaction or flags & 0x8000 == 0 or flags & 0x7800 or qd != 1:
        raise ValueError('Mismatched DNS response')
    name, offset = read_name(packet, 12)
    qtype = 1 if family == 'A' else 28
    if name != domain.rstrip('.').lower() or packet[offset:offset + 4] != struct.pack('!HH', qtype, 1):
        raise ValueError('Mismatched DNS question')
    if flags & 0x0200:
        return None  # validated truncated response: retry TCP
    if flags & 15 not in (0, 3):
        return [], 0, False
    offset += 4
    records, negative_ttl = [], 0
    for number in range(an + ns + ar):
        owner, offset = read_name(packet, offset)
        if offset + 10 > len(packet):
            raise ValueError('Truncated DNS record')
        kind, record_class, ttl, size = struct.unpack('!HHIH', packet[offset:offset + 10])
        offset += 10; end = offset + size
        if end > len(packet):
            raise ValueError('Truncated DNS data')
        if record_class == 1 and number < an:
            if kind == 5:
                target, name_end = read_name(packet, offset)
                if name_end != end:
                    raise ValueError('Invalid DNS CNAME data length')
                records.append((owner, kind, target, ttl))
            elif kind == qtype and size == (4 if family == 'A' else 16):
                value = address(str(ipaddress.ip_address(packet[offset:end])), family)
                if value:
                    records.append((owner, kind, value, ttl))
        if record_class == 1 and kind == 6 and an <= number < an + ns:
            _, soa_at = read_name(packet, offset)
            _, soa_at = read_name(packet, soa_at)
            if soa_at + 20 == end:
                minimum = struct.unpack('!5I', packet[soa_at:end])[-1]
                negative_ttl = min(30, ttl, minimum)
        offset = end
    accepted, ttls = {name}, []
    for _ in range(16):
        more = {value for owner, kind, value, ttl in records if kind == 5 and owner in accepted}
        if more.issubset(accepted):
            break
        accepted.update(more)
    values = []
    for owner, kind, value, ttl in records:
        if owner in accepted:
            ttls.append(ttl)
            if kind == qtype:
                values.append(value)
    if flags & 15 == 3:
        values = []
    return sorted(set(values)), min([300, *ttls]) if values else negative_ttl, True


def query_dns(query):
    domain, family, host, port = query
    if not re.fullmatch(r'[a-z0-9_.-]{1,253}', domain) or domain.startswith('-'):
        return [], 0, False
    try:
        labels = domain.rstrip('.').split('.')
        if any(not label or len(label) > 63 for label in labels):
            return [], 0, False
        question = b''.join(bytes([len(label)]) + label.encode('ascii') for label in labels) + b'\0'
        question += struct.pack('!HH', 1 if family == 'A' else 28, 1)
        transaction = int.from_bytes(os.urandom(2), 'big')
        request = struct.pack('!6H', transaction, 0x0100, 1, 0, 0, 0) + question
        af = socket.AF_INET6 if ipaddress.ip_address(host).version == 6 else socket.AF_INET
        deadline = time.monotonic() + 2.5
        with socket.socket(af, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2)
            sock.connect((host, int(port)))
            sock.send(request)
            reply = sock.recv(65535)
        result = parse_response(reply, transaction, domain, family)
        if result is not None:
            return result
        with socket.socket(af, socket.SOCK_STREAM) as sock:
            sock.settimeout(max(.05, deadline - time.monotonic()))
            sock.connect((host, int(port)))
            sock.sendall(struct.pack('!H', len(request)) + request)
            def read_exact(length):
                data = bytearray()
                while len(data) < length:
                    sock.settimeout(max(.05, deadline - time.monotonic()))
                    chunk = sock.recv(length - len(data))
                    if not chunk or time.monotonic() > deadline:
                        raise ValueError('Incomplete DNS TCP reply')
                    data.extend(chunk)
                return bytes(data)
            length = struct.unpack('!H', read_exact(2))[0]
            result = parse_response(read_exact(length), transaction, domain, family)
            return result or ([], 0, False)
    except (OSError, ValueError, UnicodeError, struct.error):
        return [], 0, False


def load_cache(path, now):
    try:
        if path.is_symlink() or path.stat().st_size > MAX_CACHE_BYTES:
            return {}
        raw = json.loads(path.read_text())
        if raw.get('version') != 1:
            return {}
        entries = raw['entries']
        if not isinstance(entries, dict) or len(entries) > 8192:
            return {}
        return {k: v for k, v in entries.items() if isinstance(v, dict)
                and isinstance(v.get('saved'), (int, float)) and 0 <= now - v['saved'] <= 600
                and isinstance(v.get('until'), (int, float)) and v['until'] <= v['saved'] + 300
                and isinstance(v.get('values'), list) and len(v['values']) <= 256}
    except (OSError, ValueError, TypeError, KeyError):
        return {}


def resolve_queue(queries, cache_path, *, workers=6, now=None, query=query_dns):
    now = time.time() if now is None else now
    queries = sorted(set(queries))
    if len(queries) > MAX_QUERIES:
        raise ValueError('DNS queue limit exceeded')
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if cache_path.parent.is_symlink() or cache_path.is_symlink():
        raise ValueError('Unsafe DNS cache path')
    cache, results, pending = load_cache(cache_path, now), {}, []
    stats = dict(queries=len(queries), cached=0, requested=0, failed=0, stale=0)
    for item in queries:
        cache_key = json.dumps(item, separators=(',', ':'))
        entry = cache.get(cache_key)
        if entry and entry['until'] > now:
            results[item] = [ip for value in entry['values'] if (ip := address(value, item[1]))]
            stats['cached'] += 1
        else:
            pending.append(item)
    def completed(executor, count):
        remaining = iter(pending)
        active = {}
        def refill():
            while len(active) < count * 2:
                item = next(remaining, None)
                if item is None:
                    break
                active[executor.submit(query, item)] = item
        refill()
        while active:
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                item = active.pop(future)
                yield item, future.result()
            refill()
    workers = max(1, min(8, int(workers)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for item, (values, ttl, succeeded) in completed(executor, workers):
            stats['requested'] += 1
            cache_key = json.dumps(item, separators=(',', ':'))
            results[item] = values
            if succeeded and ttl > 0:
                cache[cache_key] = dict(values=values, saved=now, until=now + min(300, ttl))
            elif not succeeded:
                stats['failed'] += 1
                previous = cache.get(cache_key)
                if previous:
                    results[item] = [ip for value in previous['values'] if (ip := address(value, item[1]))]
                    stats['stale'] += 1
            else:
                cache.pop(cache_key, None)
    # Keep only this bounded working set, never persist credentials or URI keys.
    allowed = {json.dumps(item, separators=(',', ':')) for item in queries}
    entries = {k: v for k, v in cache.items() if k in allowed}
    entries = dict(sorted(entries.items(), key=lambda pair: pair[1]['saved'], reverse=True)[:8192])
    payload = json.dumps(dict(version=1, entries=entries), separators=(',', ':')).encode()
    if len(payload) > MAX_CACHE_BYTES:
        payload = b'{"version":1,"entries":{}}'
    temp = cache_path.with_name(cache_path.name + '.' + str(os.getpid()))
    try:
        with open(temp, 'xb') as output:
            output.write(payload)
        os.replace(temp, cache_path)
    finally:
        temp.unlink(missing_ok=True)
    return results, stats


def lines(path):
    try:
        if path.stat().st_size > MAX_CACHE_BYTES:
            raise ValueError('Route input too large')
        return set(path.read_text().splitlines())
    except FileNotFoundError:
        return set()


def batch(directory, suffix, env):
    directory = Path(directory)
    local = (env.get('DNS_HOST', '127.0.0.1'), int(env.get('DNS_PORT', '53')))
    external = [(host, 53) for host in env.get('YOUTUBE_DNS_SAMPLE_SERVERS', '').split()]
    ipv6_all = env.get('BATCH_IPV6_ALL') == '1'
    domains = {name: lines(directory / (name + '.domains')) for name in SETS}
    mirrors = {name: lines(directory / (name + 'udp.domains')) for name in SETS}
    priority = set(env.get('VLESS_PRIORITY_DOMAINS', '').split())
    queries = set()
    def sources(domain, family):
        return [local, *(external if youtube_domain(domain, family) else [])]
    for values in domains.values():
        for domain in values:
            for family in ('A', 'AAAA'):
                if family == 'AAAA' and not (ipv6_all or youtube_domain(domain, family)):
                    continue
                queries.update((domain, family, *server) for server in sources(domain, family))
    queries.update((domain, family, *local) for domain in priority for family in ('A', 'AAAA'))
    results, stats = resolve_queue(queries, env.get('ROUTE_DNS_CACHE', '/tmp/bypass-route-dns/cache.json'),
                                   workers=int(env.get('PARALLEL_JOBS', '6')))
    exclude = lines(Path(env.get('UDP_QUIC_EXCLUDE_SOURCE') or directory / 'no-excludes'))
    commands = set()
    for name, name6 in zip(SETS, V6):
        for domain in domains[name]:
            for family in ('A', 'AAAA'):
                values = {ip for server in sources(domain, family) for ip in results.get((domain, family, *server), ())}
                for ip in values:
                    target = name if family == 'A' else name6
                    commands.add('add tmp_' + target + '_' + suffix + ' ' + ip)
                    if family == 'A' and domain in mirrors[name] and ip not in exclude:
                        commands.add('add tmp_' + name + 'udp_' + suffix + ' ' + ip)
                    if family == 'AAAA' and youtube_domain(domain, family):
                        # Match legacy behavior: /64 only when first four groups
                        # are explicit in the canonical IPv6 representation.
                        if all(ip.split(':')[:4]):
                            network = str(ipaddress.ip_network(ip + '/64', strict=False))
                            commands.add('add tmp_' + name6 + '_' + suffix + ' ' + network)
    (directory / 'dns.restore').write_text('\n'.join(sorted(commands)) + '\n')
    priority_rows = [domain + ' ' + family + ' ' + ip for domain in sorted(priority)
                     for family in ('A', 'AAAA') for ip in results.get((domain, family, *local), ())]
    (directory / 'priority.answers').write_text('\n'.join(priority_rows) + '\n')
    (directory / 'dns.stats.json').write_text(json.dumps(stats))
    return stats


if __name__ == '__main__':
    try:
        started = time.monotonic()
        stats = batch(sys.argv[1], sys.argv[2], os.environ)
        print('DNS batch: ' + json.dumps(dict(stats, seconds=round(time.monotonic() - started, 3))))
    except Exception as exc:
        print('DNS batch failed: ' + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
