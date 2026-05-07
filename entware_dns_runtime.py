import os
import re
import subprocess


ENTWARE_HOST = 'bin.entware.net'
ROUTER_DNS = '192.168.1.1'
FALLBACK_DNS = ('8.8.8.8', '1.1.1.1')
_ADDRESS_RE = re.compile(r'Address\s+\d+:\s+((?:\d{1,3}\.){3}\d{1,3})')


def _run_quiet(args):
    return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def entware_dns_is_available(run_quiet=_run_quiet):
    try:
        return run_quiet(['nslookup', ENTWARE_HOST, ROUTER_DNS]).returncode == 0
    except Exception:
        return False


def entware_ip_from_lookup(lookup_output):
    host_matches = _ADDRESS_RE.findall(lookup_output or '')
    return host_matches[-1] if host_matches else ''


def prepare_entware_dns():
    if entware_dns_is_available():
        return 'Entware DNS уже доступен.'

    notes = []
    try:
        _run_quiet(['ndmc', '-c', 'no opkg dns-override'])
        _run_quiet(['ndmc', '-c', 'system configuration save'])
        notes.append('opkg dns-override отключён')
    except Exception:
        notes.append('не удалось отключить opkg dns-override')

    try:
        resolv_conf = '/etc/resolv.conf'
        preserved = []
        if os.path.exists(resolv_conf):
            with open(resolv_conf, 'r', encoding='utf-8', errors='ignore') as file:
                preserved = [
                    line.rstrip('\n')
                    for line in file
                    if line.strip() and not line.lstrip().startswith('nameserver')
                ]
        with open(resolv_conf, 'w', encoding='utf-8') as file:
            file.write(f'nameserver {FALLBACK_DNS[0]}\n')
            file.write(f'nameserver {FALLBACK_DNS[1]}\n')
            if preserved:
                file.write('\n'.join(preserved) + '\n')
        notes.append('внешние DNS записаны первыми в /etc/resolv.conf')
    except Exception:
        notes.append('не удалось обновить /etc/resolv.conf')

    try:
        lookup_output = subprocess.check_output(
            ['nslookup', ENTWARE_HOST, FALLBACK_DNS[0]],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        entware_ip = entware_ip_from_lookup(lookup_output)
        if entware_ip:
            hosts_path = '/etc/hosts'
            preserved = []
            if os.path.exists(hosts_path):
                with open(hosts_path, 'r', encoding='utf-8', errors='ignore') as file:
                    preserved = [line.rstrip('\n') for line in file if ENTWARE_HOST not in line]
            with open(hosts_path, 'w', encoding='utf-8') as file:
                if preserved:
                    file.write('\n'.join(preserved) + '\n')
                file.write(f'{entware_ip} {ENTWARE_HOST}\n')
            notes.append(f'{ENTWARE_HOST} закреплён в /etc/hosts как {entware_ip}')
    except Exception:
        notes.append(f'не удалось закрепить {ENTWARE_HOST} в /etc/hosts')

    return 'Подготовка Entware DNS: ' + ', '.join(notes)
