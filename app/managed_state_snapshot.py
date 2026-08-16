import argparse
import hashlib
import json
import os
import shutil
import stat


SNAPSHOT_FORMAT = 2
SUPPORTED_SNAPSHOT_FORMATS = frozenset((1, SNAPSHOT_FORMAT))
MANIFEST_NAME = 'manifest.json'
TREE_DIR_NAME = 'tree'
LINK_CONTENT_DIR_NAME = 'link-content'

# Persistent state owned or modified by bypass_keenetic. Transient command,
# progress, worker and log files are deliberately excluded from rollback.
MANAGED_PATHS = (
    '/etc/resolv.conf',
    '/etc/hosts',
    '/opt/etc/bot_config.py',
    '/opt/etc/bot_app_mode',
    '/opt/etc/bot_proxy_mode',
    '/opt/etc/bot_autostart',
    '/opt/etc/bot/bot_config.py',
    '/opt/etc/bot/key_pools.json',
    '/opt/etc/bot/key_pools.json.last-good',
    '/opt/etc/bot/key_probe_cache.json',
    '/opt/etc/bot/key_probe_cache.json.last-good',
    '/opt/etc/bot/pool_summary_last.json',
    '/opt/etc/bot/subscriptions.json',
    '/opt/etc/bot/subscription_nightly_pool_probe.json',
    '/opt/etc/bot/custom_checks.json',
    '/opt/etc/bot/service_route_state.json',
    '/opt/etc/bot/socialnet.txt',
    '/opt/etc/bot/call_signal_routes.txt',
    '/opt/etc/bot/udp_policy.conf',
    '/opt/etc/bot/udp_quic_exclude.txt',
    '/opt/etc/bot/udp_quic_routes.txt',
    '/opt/etc/bot/youtube_edge_cache.json',
    '/opt/etc/bot/youtube_edge_quality.hosts',
    '/opt/etc/bot/event_history.jsonl',
    '/opt/etc/bot/key_switch_audit.log',
    '/opt/etc/unblock',
    '/opt/etc/unblock.dnsmasq',
    '/opt/etc/dnsmasq.conf',
    '/opt/etc/hosts',
    '/opt/etc/xray',
    '/opt/etc/v2ray',
    '/opt/etc/shadowsocks.json',
    '/opt/etc/trojan',
    '/opt/etc/crontab',
    '/opt/var/spool/cron/crontabs/root',
    '/opt/etc/init.d/S24xray',
    '/opt/etc/init.d/S24v2ray',
    '/opt/etc/init.d/S35tor',
    '/opt/etc/tor',
    '/opt/tmp/tor',
    '/opt/etc/openvpn',
    '/opt/etc/wireguard',
    '/opt/etc/ndm/netfilter.d/100-unblock-vpn',
    '/opt/etc/ndm/netfilter.d/100-unblock-vpn.sh',
    '/opt/etc/ndm/ifstatechanged.d/100-unblock-vpn',
    '/opt/etc/ndm/ifstatechanged.d/100-unblock-vpn.sh',
)


class ManagedStateSnapshotError(RuntimeError):
    pass


def _normalized_paths(paths):
    result = []
    for value in MANAGED_PATHS if paths is None else paths:
        path = os.path.normpath(os.path.abspath(os.fspath(value)))
        if path == os.path.sep:
            raise ManagedStateSnapshotError('filesystem root cannot be managed')
        if path in result:
            raise ManagedStateSnapshotError(f'duplicate managed path: {path}')
        result.append(path)
    return tuple(result)


def _snapshot_relative_path(source_path):
    drive, tail = os.path.splitdrive(source_path)
    relative = tail.lstrip('/\\')
    if drive:
        relative = os.path.join(drive.rstrip(':').casefold(), relative)
    return relative


def _stored_path(snapshot_dir, source_path):
    return os.path.join(snapshot_dir, TREE_DIR_NAME, _snapshot_relative_path(source_path))


def _stored_link_content_path(snapshot_dir, source_path):
    return os.path.join(snapshot_dir, LINK_CONTENT_DIR_NAME, _snapshot_relative_path(source_path))


def _copy_path(source, target):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.islink(source):
        os.symlink(os.readlink(source), target)
    elif os.path.isdir(source):
        shutil.copytree(source, target, symlinks=True, copy_function=shutil.copy2)
    else:
        shutil.copy2(source, target, follow_symlinks=False)


def _path_fingerprint(path, include_modes):
    digest = hashlib.sha256()
    modes = {}

    def update(value):
        digest.update(value.encode('utf-8', errors='surrogateescape'))
        digest.update(b'\0')

    def visit(current, relative):
        metadata = os.lstat(current)
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISLNK(metadata.st_mode):
            if include_modes:
                update(f'link:{relative}:{mode:o}:{os.readlink(current)}')
            else:
                update(f'link:{relative}:{os.readlink(current)}')
            return
        if stat.S_ISDIR(metadata.st_mode):
            modes[relative] = mode
            update(f'dir:{relative}:{mode:o}' if include_modes else f'dir:{relative}')
            for name in sorted(os.listdir(current)):
                visit(os.path.join(current, name), os.path.join(relative, name))
            return
        if not stat.S_ISREG(metadata.st_mode):
            raise ManagedStateSnapshotError(f'unsupported managed file type: {relative}')
        modes[relative] = mode
        if include_modes:
            update(f'file:{relative}:{mode:o}:{metadata.st_size}')
        else:
            update(f'file:{relative}:{metadata.st_size}')
        with open(current, 'rb') as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b''):
                digest.update(chunk)

    visit(path, '.')
    return digest.hexdigest(), modes


def _path_digest(path):
    return _path_fingerprint(path, include_modes=True)[0]


def _path_content_state(path):
    return _path_fingerprint(path, include_modes=False)


def _legacy_regular_file_digest(path, mode):
    metadata = os.lstat(path)
    digest = hashlib.sha256()
    digest.update(f'file:.:{mode:o}:{metadata.st_size}'.encode('utf-8'))
    digest.update(b'\0')
    with open(path, 'rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _legacy_regular_file_mode(path, expected_digest):
    if not isinstance(expected_digest, str) or os.path.islink(path) or not os.path.isfile(path):
        return None
    actual_mode = stat.S_IMODE(os.lstat(path).st_mode)
    candidates = (
        actual_mode, 0o444, 0o600, 0o640, 0o644, 0o660, 0o664, 0o666,
        0o700, 0o750, 0o755, 0o770, 0o775,
    )
    for mode in dict.fromkeys(candidates):
        if _legacy_regular_file_digest(path, mode) == expected_digest:
            return mode
    return None


def _verified_content_state(stored, entry, format_version):
    expected_digest = entry.get('sha256')
    if format_version == 1:
        if _path_digest(stored) == expected_digest:
            return _path_content_state(stored)
        recovered_mode = _legacy_regular_file_mode(stored, expected_digest)
        if recovered_mode is None:
            raise ManagedStateSnapshotError('managed state snapshot integrity check failed')
        digest, modes = _path_content_state(stored)
        modes['.'] = recovered_mode
        return digest, modes
    digest, stored_modes = _path_content_state(stored)
    raw_modes = entry.get('modes')
    if digest != expected_digest or not isinstance(raw_modes, dict) or set(raw_modes) != set(stored_modes):
        raise ManagedStateSnapshotError('managed state snapshot integrity check failed')
    modes = {}
    for relative, mode in raw_modes.items():
        if isinstance(mode, bool) or not isinstance(mode, int) or not 0 <= mode <= 0o7777:
            raise ManagedStateSnapshotError('managed state mode metadata is invalid')
        modes[relative] = mode
    return digest, modes


def _verified_link_content_state(stored_content, link_content, format_version):
    if not os.path.isfile(stored_content) or os.path.islink(stored_content):
        raise ManagedStateSnapshotError('managed state link content integrity check failed')
    if format_version == 1:
        mode = _legacy_regular_file_mode(stored_content, link_content.get('sha256'))
        if mode is None:
            raise ManagedStateSnapshotError('managed state link content integrity check failed')
        return _path_content_state(stored_content)[0], mode
    digest, modes = _path_content_state(stored_content)
    mode = link_content.get('mode')
    if (
        digest != link_content.get('sha256')
        or set(modes) != {'.'}
        or isinstance(mode, bool)
        or not isinstance(mode, int)
        or not 0 <= mode <= 0o7777
    ):
        raise ManagedStateSnapshotError('managed state link content integrity check failed')
    return digest, mode


def _apply_modes(path, modes):
    for relative, mode in sorted(modes.items(), key=lambda item: item[0].count(os.path.sep), reverse=True):
        current = path if relative == '.' else os.path.join(path, relative)
        metadata = os.lstat(current)
        if stat.S_ISLNK(metadata.st_mode) or not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
            raise ManagedStateSnapshotError('managed state type changed before mode restore')
        os.chmod(current, mode)


def backup_managed_state(snapshot_dir, paths=None):
    snapshot_dir = os.path.abspath(os.fspath(snapshot_dir))
    if os.path.lexists(snapshot_dir):
        raise ManagedStateSnapshotError('snapshot destination already exists')
    managed_paths = _normalized_paths(paths)
    os.makedirs(os.path.join(snapshot_dir, TREE_DIR_NAME), mode=0o700)
    os.chmod(snapshot_dir, 0o700)
    entries = []
    for source_path in managed_paths:
        present = os.path.lexists(source_path)
        entry = {'path': source_path, 'present': present, 'sha256': '', 'modes': {}}
        if present:
            stored = _stored_path(snapshot_dir, source_path)
            _copy_path(source_path, stored)
            entry['sha256'], entry['modes'] = _path_content_state(stored)
            if os.path.islink(source_path) and (not os.path.exists(source_path) or os.path.isfile(source_path)):
                link_content = {'present': os.path.isfile(source_path), 'sha256': '', 'mode': 0}
                if link_content['present']:
                    stored_content = _stored_link_content_path(snapshot_dir, source_path)
                    os.makedirs(os.path.dirname(stored_content), exist_ok=True)
                    resolved_source = os.path.realpath(source_path)
                    link_content['mode'] = stat.S_IMODE(os.stat(resolved_source).st_mode)
                    shutil.copy2(resolved_source, stored_content)
                    link_content['sha256'] = _path_content_state(stored_content)[0]
                entry['link_content'] = link_content
        entries.append(entry)
    manifest = {'format': SNAPSHOT_FORMAT, 'entries': entries}
    manifest_path = os.path.join(snapshot_dir, MANIFEST_NAME)
    with open(manifest_path, 'x', encoding='utf-8') as file:
        json.dump(manifest, file, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        file.write('\n')
    os.chmod(manifest_path, 0o600)
    return {'entries': len(entries), 'present': sum(bool(item['present']) for item in entries)}


def _load_verified_manifest(snapshot_dir, paths=None):
    snapshot_dir = os.path.abspath(os.fspath(snapshot_dir))
    manifest_path = os.path.join(snapshot_dir, MANIFEST_NAME)
    try:
        with open(manifest_path, 'r', encoding='utf-8') as file:
            manifest = json.load(file)
    except Exception as exc:
        raise ManagedStateSnapshotError('managed state manifest is unreadable') from exc
    format_version = manifest.get('format')
    if (
        isinstance(format_version, bool)
        or format_version not in SUPPORTED_SNAPSHOT_FORMATS
        or not isinstance(manifest.get('entries'), list)
    ):
        raise ManagedStateSnapshotError('managed state manifest format is unsupported')
    allowed_paths = set(_normalized_paths(paths))
    entries = manifest['entries']
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get('present') not in (True, False):
            raise ManagedStateSnapshotError('managed state manifest entry is invalid')
        path = os.path.normpath(os.path.abspath(os.fspath(entry.get('path', ''))))
        if path not in allowed_paths or path in seen:
            raise ManagedStateSnapshotError('managed state manifest contains an unsafe path')
        seen.add(path)
        entry['path'] = path
        present = entry.get('present') is True
        stored = _stored_path(snapshot_dir, path)
        if present:
            if not os.path.lexists(stored):
                raise ManagedStateSnapshotError('managed state snapshot integrity check failed')
            entry['_content_sha256'], entry['_modes'] = _verified_content_state(stored, entry, format_version)
            link_content = entry.get('link_content')
            if link_content is not None:
                if (
                    not isinstance(link_content, dict)
                    or link_content.get('present') not in (True, False)
                    or not os.path.islink(stored)
                ):
                    raise ManagedStateSnapshotError('managed state link content metadata is invalid')
                stored_content = _stored_link_content_path(snapshot_dir, path)
                if link_content.get('present') is True:
                    link_content['_content_sha256'], link_content['_mode'] = _verified_link_content_state(
                        stored_content, link_content, format_version
                    )
                elif os.path.lexists(stored_content):
                    raise ManagedStateSnapshotError('absent managed link content unexpectedly has stored data')
        elif os.path.lexists(stored):
            raise ManagedStateSnapshotError('absent managed state unexpectedly has stored data')
    if seen != allowed_paths:
        raise ManagedStateSnapshotError('managed state manifest is incomplete')
    return snapshot_dir, entries


def verify_managed_state(snapshot_dir, paths=None):
    _snapshot_dir, entries = _load_verified_manifest(snapshot_dir, paths=paths)
    return {'entries': len(entries), 'present': sum(item.get('present') is True for item in entries)}


def _remove_path(path):
    if not os.path.lexists(path):
        return
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path)
    else:
        shutil.rmtree(path)


def _current_entry_matches(entry):
    path = entry['path']
    if entry.get('present') is not True:
        return not os.path.lexists(path)
    if not os.path.lexists(path) or _path_content_state(path) != (entry['_content_sha256'], entry['_modes']):
        return False
    link_content = entry.get('link_content')
    if link_content is None:
        return True
    target_exists = os.path.exists(path)
    if link_content.get('present') is not True:
        return not target_exists
    return os.path.isfile(path) and _path_content_state(os.path.realpath(path)) == (
        link_content['_content_sha256'], {'.': link_content['_mode']}
    )


def _restore_path(source, target):
    parent = os.path.dirname(target)
    os.makedirs(parent, exist_ok=True)
    temporary = os.path.join(parent, f'.{os.path.basename(target)}.rollback-{os.getpid()}')
    _remove_path(temporary)
    try:
        _copy_path(source, temporary)
        _remove_path(target)
        os.replace(temporary, target)
    finally:
        _remove_path(temporary)


def _restore_link_content(snapshot_dir, entry):
    link_content = entry.get('link_content')
    if link_content is None:
        return
    target = entry['path']
    stored = _stored_path(snapshot_dir, target)
    if not os.path.islink(target) or os.readlink(target) != os.readlink(stored):
        raise ManagedStateSnapshotError('managed state symlink changed before content restore')
    resolved_target = os.path.realpath(target)
    if link_content.get('present') is True:
        expected_state = (link_content['_content_sha256'], {'.': link_content['_mode']})
        if not os.path.isfile(resolved_target) or _path_content_state(resolved_target) != expected_state:
            _restore_path(_stored_link_content_path(snapshot_dir, target), resolved_target)
        _apply_modes(resolved_target, expected_state[1])
    else:
        if os.path.isdir(resolved_target) and not os.path.islink(resolved_target):
            raise ManagedStateSnapshotError('managed state link target unexpectedly became a directory')
        _remove_path(resolved_target)


def restore_managed_state(snapshot_dir, paths=None):
    snapshot_dir, entries = _load_verified_manifest(snapshot_dir, paths=paths)
    restored = 0
    removed = 0
    for entry in entries:
        target = entry['path']
        if _current_entry_matches(entry):
            if entry.get('present') is True:
                restored += 1
            continue
        if entry.get('present') is not True:
            if os.path.lexists(target):
                _remove_path(target)
                removed += 1
            continue
        stored = _stored_path(snapshot_dir, target)
        if not os.path.lexists(target) or _path_content_state(target)[0] != entry['_content_sha256']:
            _restore_path(stored, target)
        _apply_modes(target, entry['_modes'])
        _restore_link_content(snapshot_dir, entry)
        restored += 1
    return {'entries': len(entries), 'restored': restored, 'removed': removed}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('backup', 'verify', 'restore'))
    parser.add_argument('snapshot_dir')
    args = parser.parse_args(argv)
    if args.action == 'backup':
        result = backup_managed_state(args.snapshot_dir)
    elif args.action == 'verify':
        result = verify_managed_state(args.snapshot_dir)
    else:
        result = restore_managed_state(args.snapshot_dir)
    print(f'managed_state_{args.action}=ok entries={result["entries"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
