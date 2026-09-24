import os
import re
import subprocess
import stat
import tempfile

from protocol_catalog import PROTOCOL_DISPLAY_ORDER, PROTOCOL_LABELS, PROTOCOL_ROUTE_NAMES


UNBLOCK_DIR = '/opt/etc/unblock'
UNBLOCK_UPDATE_SCRIPT = '/opt/bin/unblock_update.sh'

BASE_LABELS = {
    PROTOCOL_ROUTE_NAMES[proto]: PROTOCOL_LABELS[proto]
    for proto in PROTOCOL_DISPLAY_ORDER
}

DEFAULT_ORDER = [f'{PROTOCOL_ROUTE_NAMES[proto]}.txt' for proto in PROTOCOL_DISPLAY_ORDER]
VISIBLE_UNBLOCK_LISTS = set(DEFAULT_ORDER)


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


def _replace_list(path, content, metadata):
    """Replace on the same filesystem, preserving the existing file permissions."""
    fd, staged = tempfile.mkstemp(prefix='.route-move-', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        if hasattr(os, 'chown'):
            os.chown(staged, metadata.st_uid, metadata.st_gid)
        os.chmod(staged, stat.S_IMODE(metadata.st_mode))
        os.replace(staged, path)
    finally:
        if os.path.exists(staged):
            os.unlink(staged)


def move_unblock_list(source_list, target_list, *, unblock_dir=UNBLOCK_DIR, apply_changes=None):
    """Move saved entries only. Caller serializes this with other route writers."""
    if source_list not in VISIBLE_UNBLOCK_LISTS or target_list not in VISIBLE_UNBLOCK_LISTS:
        raise ValueError('Выберите список из доступных протоколов')
    if source_list == target_list:
        raise ValueError('Выберите другой список для переноса')
    snapshots = {}
    for name in (source_list, target_list):
        path = os.path.join(unblock_dir, name)
        metadata = os.lstat(path)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError('Список должен быть обычным файлом')
        with open(path, 'rb') as file:
            content = file.read()
        snapshots[name] = (path, content, metadata)
    source = snapshots[source_list][1].decode('utf-8')
    target = snapshots[target_list][1].decode('utf-8')
    merged = normalize_unblock_list(target + '\n' + source)
    changed = bool(source.strip())
    if changed:
        written = []
        apply_started = False
        try:
            # Destination first: interruption cannot remove the only copy of an address.
            for name, content in ((target_list, (merged + '\n').encode('utf-8')), (source_list, b'')):
                path, _, metadata = snapshots[name]
                _replace_list(path, content, metadata)
                written.append(name)
            if callable(apply_changes):
                apply_started = True
                apply_changes()
        except Exception as exc:
            try:
                # Restore the source before removing its copy from the destination.
                for name in (source_list, target_list):
                    if name in written:
                        path, content, metadata = snapshots[name]
                        _replace_list(path, content, metadata)
            except Exception as restore_exc:
                raise RuntimeError('Ошибка восстановления списков; проверьте оба списка перед повтором') from restore_exc
            if apply_started:
                try:
                    apply_changes()
                except Exception as restore_exc:
                    raise RuntimeError('Списки восстановлены, но прежние маршруты применить не удалось') from restore_exc
            raise RuntimeError('Изменения отменены, исходные списки сохранены') from exc
    return {
        'changed': changed,
        'source_label': list_label(source_list),
        'target_label': list_label(target_list),
        'entries': len(entries_from_service_text(normalize_unblock_list(source))),
        'list_contents': {source_list: '' if changed else source.strip(),
                          target_list: merged if changed else target.strip()},
    }


def _run_unblock_update(async_update=False):
    if async_update:
        popen_kwargs = {
            'stdout': subprocess.DEVNULL,
            'stderr': subprocess.DEVNULL,
            'close_fds': True,
        }
        try:
            subprocess.Popen([UNBLOCK_UPDATE_SCRIPT], start_new_session=True, **popen_kwargs)
        except TypeError:
            subprocess.Popen([UNBLOCK_UPDATE_SCRIPT], **popen_kwargs)
        return
    subprocess.run([UNBLOCK_UPDATE_SCRIPT], check=False)


def save_unblock_list_file(list_name, text, before_update=None, async_update=False):
    safe_name = validate_visible_unblock_list_name(list_name)
    target_path = os.path.join(UNBLOCK_DIR, safe_name)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    normalized = normalize_unblock_list(text)
    with open(target_path, 'w', encoding='utf-8') as file:
        if normalized:
            file.write(normalized + '\n')
    if callable(before_update):
        before_update()
    _run_unblock_update(async_update=async_update)
    return safe_name


def unblock_list_path(list_name, unblock_dir=UNBLOCK_DIR):
    return os.path.join(unblock_dir, f'{list_name}.txt')


def read_unblock_list_entries(list_name, unblock_dir=UNBLOCK_DIR):
    list_path = unblock_list_path(list_name, unblock_dir=unblock_dir)
    if not os.path.exists(list_path):
        raise FileNotFoundError(list_path)
    with open(list_path, encoding='utf-8') as file:
        return [line.strip() for line in file if line.strip()]


def write_unblock_list_entries(list_name, entries, unblock_dir=UNBLOCK_DIR):
    list_path = unblock_list_path(list_name, unblock_dir=unblock_dir)
    with open(list_path, 'w', encoding='utf-8') as file:
        for line in sorted(set(entries)):
            if line:
                file.write(line + '\n')


def normalize_unblock_route_name(list_name):
    safe_name = os.path.basename((list_name or '').strip())
    if safe_name.endswith('.txt'):
        safe_name = safe_name[:-4]
    if not safe_name or not re.match(r'^[A-Za-z0-9_-]+$', safe_name):
        raise ValueError('Некорректное имя списка')
    return safe_name


def validate_visible_unblock_list_name(list_name):
    safe_name = f'{normalize_unblock_route_name(list_name)}.txt'
    if safe_name not in VISIBLE_UNBLOCK_LISTS:
        raise ValueError('List is not editable from the web interface')
    return safe_name


def entries_from_service_text(text, excluded_entries=None):
    entries = []
    seen = set()
    excluded_entries = set(excluded_entries or [])
    for raw_line in (text or '').replace('\r', '\n').split('\n'):
        line = raw_line.split('#', 1)[0].strip()
        if not line or line.lower() in excluded_entries or line in seen:
            continue
        seen.add(line)
        entries.append(line)
    return entries


def list_label(file_name, include_vpn=False):
    base = file_name[:-4] if file_name.endswith('.txt') else file_name
    return BASE_LABELS.get(base, base)


def load_unblock_lists(with_content=True, read_text_file=None, include_vpn=False):
    try:
        file_names = sorted(name for name in os.listdir(UNBLOCK_DIR) if name.endswith('.txt'))
    except Exception:
        file_names = []
    file_names = [name for name in file_names if name in VISIBLE_UNBLOCK_LISTS]
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
