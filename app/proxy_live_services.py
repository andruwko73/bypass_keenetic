"""Protocol-owned transparent services participating in a hot key transaction.

Only these two fixed init scripts may run. Xray is never restarted here.
Service output can contain endpoints/credentials and is deliberately discarded.
"""
import json
from pathlib import Path
import subprocess
import time

from proxy_config_builder import build_shadowsocks_config, build_trojan_config


SERVICE_PATHS = {
    'shadowsocks': ('/opt/etc/init.d/S22shadowsocks', '/opt/etc/shadowsocks.json', 'ss-redir'),
    'trojan': ('/opt/etc/init.d/S22trojan', '/opt/etc/trojan/config.json', 'trojan'),
}


def encode_key(protocol, key, *, ports):
    if protocol == 'shadowsocks':
        config = build_shadowsocks_config(key, ports[protocol])
    elif protocol == 'trojan':
        config = build_trojan_config(key.strip(), ports[protocol])
    else:
        return (key.strip() + '\n').encode('utf-8')
    return json.dumps(config, ensure_ascii=False, indent=2).encode('utf-8')


def service_listener(protocol, port, *, proc_root='/proc'):
    """Confirm the configured service owns the TCP listener, not just any PID."""
    _, config, executable = SERVICE_PATHS[protocol]
    root, sockets = Path(proc_root), set()
    for table in ('tcp', 'tcp6'):
        try:
            rows = (root / 'net' / table).read_text().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            fields = row.split()
            if len(fields) >= 10 and fields[3] == '0A' and int(fields[1].rsplit(':', 1)[1], 16) == port:
                sockets.add('socket:[' + fields[9] + ']')
    if not sockets:
        return False
    for entry in root.iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            args = (entry / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
            if Path(args[0]).name != executable or config not in args:
                continue
            if any(fd.is_symlink() and str(fd.readlink()) in sockets for fd in (entry / 'fd').iterdir()):
                return True
        except (OSError, UnicodeError, IndexError):
            continue
    return False


def restart_service(protocol, port, *, run=subprocess.run, listening=service_listener,
                    clock=time.monotonic, sleep=time.sleep):
    script, _, _ = SERVICE_PATHS[protocol]
    try:
        result = run([script, 'restart'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, timeout=20, check=False)
        if result.returncode != 0:
            return False
        deadline = clock() + 8
        while clock() < deadline:
            if listening(protocol, port):
                return True
            sleep(.2)
    except (OSError, subprocess.SubprocessError):
        pass
    return False
