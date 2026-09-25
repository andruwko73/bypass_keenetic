"""Batch DNS route generation. No network lookup is needed to render rules.

Keep legacy normalization and policy matching order. The cache contains hashes
only and lives in RAM; output and input hashes are checked on every invocation.
"""
import argparse
import contextlib
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import tempfile
import time

from youtube_route_owner import ROUTE_FILES, youtube_route_owner

PRIORITY = ('youtube.com www.youtube.com m.youtube.com youtu.be youtube-nocookie.com '
            'youtube.googleapis.com youtubei.googleapis.com youtubei-att.googleapis.com '
            'youtube-ui.l.google.com wide-youtube.l.google.com googlevideo.com '
            'manifest.googlevideo.com redirector.googlevideo.com c.youtube.com '
            'ytimg.com i.ytimg.com s.ytimg.com ggpht.com yt3.ggpht.com gvt1.com')
SETS = ('unblocksh', 'unblockvmess', 'unblockvless', 'unblockvless2', 'unblocktroj', 'unblockhy2')
CALLS = ('sh', 'vmess', 'vless', 'vless2', 'troj', 'hy2')
CONNECTIVITY = frozenset(('connectivitycheck.gstatic.com', 'connectivitycheck.android.com',
                         'clients3.google.com', 'clients4.google.com', 'www.google.com', 'www.gstatic.com'))
IPV4 = re.compile(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}')


def normalize_domain(value):
    value = value.replace('\r', '')
    for prefix in ('DOMAIN-SUFFIX,', 'DOMAIN,', 'HOST-SUFFIX,', '+.', '*.'):
        if value.startswith(prefix):
            value = value[len(prefix):]
    value = re.split(r'\s|,', value, maxsplit=1)[0]
    if value.startswith('/'):
        value = value[1:]
    if value.endswith('/'):
        value = value[:-1]
    return value.lower().strip()


def policy_matcher(text):
    """Preserve the legacy AWK ERE suffix rule, including unescaped dots."""
    entries = set()
    for line in text.splitlines():
        entry = line.lower().replace('\r', '', 1).split('#', 1)[0].strip()
        for prefix in ('domain-suffix,', 'domain,', 'host-suffix,', '+.', '*.'):
            if entry.startswith(prefix):
                entry = entry[len(prefix):]
        entry = entry.removesuffix('/')
        if entry and not re.search(r'[:/]', entry) and not re.fullmatch(r'[0-9.]+', entry):
            entries.add(entry)
    patterns = [re.compile(r'\.' + entry + '$') for entry in sorted(entries)]
    return lambda domain: domain in entries or any(p.search(domain) for p in patterns)


def domain_in_set(domain, entries):
    while domain:
        if domain in entries:
            return True
        domain = domain.partition('.')[2]
    return False


def render(routes, *, owner, priority=PRIORITY, udp_policy='', call_policy=''):
    udp = policy_matcher(udp_policy)
    calls = policy_matcher(call_policy)
    priority_domains = [normalize_domain(d) for d in priority.split()]
    priority_set = set(priority_domains)
    result = {}

    def append(domain, index):
        if not domain:
            return
        targets = [SETS[index]]
        if udp(domain):
            targets.append(SETS[index] + 'udp')
        if calls(domain):
            targets.append('bypass_call_signal_' + CALLS[index])
        result['ipset=/' + domain + '/' + ','.join(targets)] = None

    for index, (protocol, filename) in enumerate(ROUTE_FILES):
        for raw in routes[filename].splitlines():
            line = raw.replace('\r', '').strip()
            if not line or line.startswith('#') or IPV4.search(line):
                continue
            # IP literals/CIDRs belong to unblock_ipset.sh, never DNS names.
            if ':' in line:
                ipaddress.ip_network(line.split()[0].split(',')[0], strict=False)
                continue
            if '\x00' in line:
                raise ValueError('Invalid route entry')
            domain = normalize_domain(line)
            if domain in CONNECTIVITY:
                continue
            if domain_in_set(domain, priority_set) and protocol != owner:
                continue
            if protocol == 'shadowsocks' and '*' in line:
                host = re.sub(r'^.*\.(.*\.\w{2,6})$', r'\1', line, flags=re.ASCII).replace('*', '', 1)
                append(normalize_domain('*.' + host), index)
                append(normalize_domain(host), index)
            else:
                append(domain, index)
    for index, (protocol, _filename) in enumerate(ROUTE_FILES):
        if protocol == owner:
            for domain in priority_domains:
                append(domain, index)
    return ''.join(line + '\n' for line in result).encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_optional(path):
    try:
        return Path(path).read_bytes()
    except FileNotFoundError:
        return b''


def atomic_write(path, raw, mode=0o600):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Unexpected DNS output symlink')
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = path.stat() if path.exists() else None
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.tmp.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            if previous and hasattr(os, 'fchown'):
                os.fchown(stream.fileno(), previous.st_uid, previous.st_gid)
            os.chmod(temporary, stat.S_IMODE(previous.st_mode) if previous else mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextlib.contextmanager
def generation_lock(path, timeout=30):
    import errno
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Unexpected DNS lock symlink')
    with path.open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            if not path.stat().st_size:
                stream.write(b'0'); stream.flush()
            def lock():
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            def unlock():
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def lock():
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def unlock():
                fcntl.flock(stream, fcntl.LOCK_UN)
        deadline = time.monotonic() + timeout
        while True:
            try:
                lock(); break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError('DNS generation lock timeout') from None
                time.sleep(0.05)
        try:
            yield
        finally:
            unlock()


def snapshot(env):
    root = Path(env.get('UNBLOCK_DIR', '/opt/etc/unblock'))
    bot = Path(env.get('BOT_DIR', '/opt/etc/bot'))
    # Missing/unreadable route files abort before replacing any working rules.
    raw_routes = {filename: (root / filename).read_bytes() for _, filename in ROUTE_FILES}
    policies = []
    for variable, filename, constant in (
        ('UDP_QUIC_POLICY_FILE', 'udp_quic_routes.txt', 'UDP_QUIC_ROUTE_ENTRIES'),
        ('CALL_SIGNAL_POLICY_FILE', 'call_signal_routes.txt', 'REALTIME_CALL_SIGNAL_ROUTE_ENTRIES'),
    ):
        raw = read_optional(env.get(variable, str(bot / filename)))
        if not raw:
            import service_catalog
            raw = ('\n'.join(getattr(service_catalog, constant)) + '\n').encode()
        policies.append(raw.decode('utf-8'))
    owner = youtube_route_owner(unblock_dir=str(root), state_path=env.get(
        'YOUTUBE_ROUTE_OWNER_STATE_FILE', '/opt/tmp/bypass-youtube-route-owner.json'))
    priority = env.get('YOUTUBE_ROUTE_PRIORITY_DOMAINS') or PRIORITY
    payload = {'routes': {name: digest(raw) for name, raw in raw_routes.items()},
               'policies': policies, 'owner': owner, 'priority': priority,
               'generator': digest(Path(__file__).read_bytes()),
               'dependencies': [digest(read_optional(Path(__file__).parent / name))
                                for name in ('service_catalog.py', 'youtube_route_owner.py')]}
    return digest(json.dumps(payload, sort_keys=True).encode()), {
        'routes': {name: raw.decode('utf-8') for name, raw in raw_routes.items()},
        'owner': owner, 'priority': priority, 'udp_policy': policies[0], 'call_policy': policies[1]}


def daemon_identity():
    identities = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if (entry / 'comm').read_text().strip() == 'dnsmasq':
                identities.append((int(entry.name), (entry / 'stat').read_text().rsplit(')', 1)[1].split()[19]))
        except (OSError, IndexError):
            pass
    return sorted(identities)


def dns_healthy():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1)
            ident = os.urandom(2)
            sock.connect(('127.0.0.1', 53))
            sock.send(ident + b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x09localhost\x00\x00\x01\x00\x01')
            data = sock.recv(4096)
            return len(data) >= 12 and data[:2] == ident and bool(data[2] & 128) and data[3] & 15 in (0, 3)
    except OSError:
        return False


def apply_identity(output_hash):
    return {'output': output_hash, 'config': digest(read_optional('/opt/etc/dnsmasq.conf')),
            'boot': read_optional('/proc/sys/kernel/random/boot_id').decode().strip(),
            'daemon': daemon_identity()}


def validate(path):
    subprocess.run(['/opt/sbin/dnsmasq', '--test', '--conf-file=' + str(path)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)


def restart():
    subprocess.run(['/opt/etc/init.d/S56dnsmasq', 'restart'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    for _ in range(10):
        if daemon_identity() and dns_healthy():
            return
        time.sleep(0.2)
    raise RuntimeError('DNS service did not recover')


def generate(env=None, *, refresh=False):
    env = os.environ if env is None else env
    output = Path(env.get('DNSMASQ_OUTPUT_FILE', '/opt/etc/unblock.dnsmasq'))
    cache = Path(env.get('DNSMASQ_CACHE_FILE', '/tmp/bypass-dns-routes/' + digest(str(output).encode())[:16] + '.json'))
    started = time.monotonic()
    with generation_lock(cache.with_suffix('.lock')):
        if output.is_symlink() or cache.is_symlink():
            raise ValueError('Unexpected DNS path symlink')
        signature, inputs = snapshot(env)
        try:
            state = json.loads(cache.read_text())
        except (OSError, ValueError):
            state = {}
        if not isinstance(state, dict):
            state = {}
        old = output.read_bytes() if output.exists() else None
        cached = state.get('input') == signature and old is not None and state.get('output') == digest(old)
        rendered = old if cached else render(**inputs)
        if not cached and snapshot(env)[0] != signature:
            raise RuntimeError('Route inputs changed during generation')
        changed = old != rendered
        output_hash = digest(rendered)
        # Verify syntax before publication, including standalone installation calls.
        validator = Path('/opt/sbin/dnsmasq')
        if changed and (refresh or validator.is_file()):
            output.parent.mkdir(parents=True, exist_ok=True)
            fd, check_path = tempfile.mkstemp(prefix=output.name + '.check.', dir=output.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(rendered)
                validate(check_path)
            finally:
                os.unlink(check_path)
        restart_needed = refresh and (changed or state.get('applied') != json.loads(json.dumps(apply_identity(output_hash))) or not dns_healthy())
        if changed and snapshot(env)[0] != signature:
            raise RuntimeError('Route inputs changed before DNS publication')
        published = False
        try:
            if changed:
                atomic_write(output, rendered, 0o644)
                published = True
            if restart_needed:
                restart()
            applied = apply_identity(output_hash) if refresh else (state.get('applied') if not changed else None)
            atomic_write(cache, json.dumps({'input': signature, 'output': output_hash, 'applied': applied}).encode())
        except BaseException:
            if published:
                if old is None:
                    output.unlink(missing_ok=True)
                else:
                    atomic_write(output, old, 0o644)
                if refresh:
                    restart()
            raise
        result = {'changed': changed, 'cached': cached, 'restarted': bool(restart_needed),
                  'seconds': round(time.monotonic() - started, 3)}
        log = Path(env.get('DNSMASQ_LOG_FILE', '/opt/var/log/bypass-dnsmasq-route.log'))
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open('a') as stream:
                stream.write(time.strftime('%Y-%m-%dT%H:%M:%S%z') + ' youtube_route=' + inputs['owner'] + ' ' + json.dumps(result) + '\n')
        except OSError:
            pass
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        result = generate(refresh=args.refresh)
        print(json.dumps(result) if args.json else ('DNS-правила обновлены.' if result['changed'] else 'DNS-правила проверены; изменений нет.'))
    except (Exception, KeyboardInterrupt) as error:
        # Input domains and subprocess diagnostics may contain private data.
        print('Не удалось применить DNS-правила: ' + type(error).__name__, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
