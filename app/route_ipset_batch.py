"""Batch legacy hash:net overlap removal without one process per member.

Kernel hash_net*_test treats a host as a longest-prefix lookup, but an
explicit network as an exact prefix lookup. Preserve that distinction.
"""
import ipaddress
from pathlib import Path
import re
import subprocess
import sys


class NetIndex:
    def __init__(self, entries):
        self.exact = {ipaddress.ip_network(value, strict=False) for value in entries}
        self.prefixes = {}
        for net in self.exact:
            self.prefixes.setdefault((net.version, net.prefixlen), set()).add(int(net.network_address))

    def contains(self, value):
        net = ipaddress.ip_network(value, strict=False)
        if net.prefixlen != net.max_prefixlen:
            return net in self.exact
        integer = int(net.network_address)
        for (version, prefix), addresses in self.prefixes.items():
            if version == net.version:
                shift = net.max_prefixlen - prefix
                if (integer >> shift) << shift in addresses:
                    return True
        return False


def members(dump, name):
    values = []
    for line in dump.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == 'create':
            if fields[1:3] != [name, 'hash:net'] or 'timeout' in fields:
                raise ValueError('Unsupported set type')
        elif fields[0] == 'add':
            if len(fields) != 3 or fields[1] != name:
                raise ValueError('Extended entries require kernel fallback')
            ipaddress.ip_network(fields[2], strict=False)
            values.append(fields[2])
    return values


def remove_overlaps(pairs, *, run=subprocess.run):
    names = sorted({name for pair in pairs for name in pair})
    if len(names) > 32 or not all(re.fullmatch(r'[a-zA-Z0-9_]{1,31}', name) for name in names):
        raise ValueError('Invalid set name')
    snapshots = {}
    for name in names:
        result = run(['ipset', 'save', name], capture_output=True, text=True, timeout=5, check=False)
        snapshots[name] = members(result.stdout, name) if result.returncode == 0 else None
    commands = []
    for loser, winner in pairs:
        if snapshots[loser] is None or snapshots[winner] is None:
            continue
        index = NetIndex(snapshots[winner])
        kept = []
        for value in snapshots[loser]:
            if index.contains(value):
                commands.append('del ' + loser + ' ' + value)
            else:
                kept.append(value)
        snapshots[loser] = kept
    if commands:
        run(['ipset', 'restore', '-exist'], input='\n'.join(commands) + '\n',
            capture_output=True, text=True, timeout=15, check=True)
    return len(commands)


if __name__ == '__main__':
    try:
        pairs = [tuple(line.split()) for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
        if any(len(pair) != 2 for pair in pairs):
            raise ValueError('Invalid pair')
        remove_overlaps(pairs)
    except Exception:
        # Caller retains the old kernel-based loop for unsupported set options.
        sys.exit(1)
