import os
import subprocess


UNBLOCK_DIR = '/opt/etc/unblock'
UNBLOCK_UPDATE_SCRIPT = '/opt/bin/unblock_update.sh'

BASE_LABELS = {
    'shadowsocks': 'Shadowsocks',
    'tor': 'Tor',
    'vmess': 'Vmess',
    'vless': 'Vless 1',
    'vless-2': 'Vless 2',
    'trojan': 'Trojan',
}

DEFAULT_ORDER = ['vless.txt', 'vless-2.txt', 'vmess.txt', 'trojan.txt', 'shadowsocks.txt']
VPN_ORDER = DEFAULT_ORDER + ['vpn.txt', 'tor.txt']


def normalize_unblock_list(text):
    items = []
    seen = set()
    for raw_line in (text or '').replace('\r', '\n').split('\n'):
        line = raw_line.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        items.append(line)
    items.sort()
    return '\n'.join(items)


def save_unblock_list_file(list_name, text):
    safe_name = os.path.basename(list_name)
    target_path = os.path.join(UNBLOCK_DIR, safe_name)
    if not target_path.endswith('.txt'):
        raise ValueError('List must be a .txt file')
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    normalized = normalize_unblock_list(text)
    with open(target_path, 'w', encoding='utf-8') as file:
        if normalized:
            file.write(normalized + '\n')
    subprocess.run([UNBLOCK_UPDATE_SCRIPT], check=False)
    return safe_name


def list_label(file_name, include_vpn=False):
    base = file_name[:-4] if file_name.endswith('.txt') else file_name
    labels = dict(BASE_LABELS)
    if include_vpn:
        labels['vpn'] = 'VPN (общий список)'
    if include_vpn and base.startswith('vpn-'):
        return f'VPN: {base[4:]}'
    return labels.get(base, base)


def load_unblock_lists(with_content=True, read_text_file=None, include_vpn=False):
    try:
        file_names = sorted(name for name in os.listdir(UNBLOCK_DIR) if name.endswith('.txt'))
    except Exception:
        file_names = []
    if include_vpn:
        file_names = [name for name in file_names if name not in ['vpn.txt', 'tor.txt']]
        preferred_order = VPN_ORDER
    else:
        file_names = [
            name for name in file_names
            if name not in ['vpn.txt', 'tor.txt'] and not name.startswith('vpn-')
        ]
        preferred_order = DEFAULT_ORDER
    ordered = []
    for item in preferred_order:
        if item in file_names:
            ordered.append(item)
    for item in file_names:
        if item not in ordered:
            ordered.append(item)
    result = []
    for file_name in ordered:
        entry = {
            'name': file_name,
            'label': list_label(file_name, include_vpn=include_vpn),
        }
        if with_content:
            reader = read_text_file or _read_text_file
            entry['content'] = reader(os.path.join(UNBLOCK_DIR, file_name)).strip()
        result.append(entry)
    return result


def _read_text_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            return file.read()
    except Exception:
        return ''
