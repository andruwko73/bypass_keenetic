"""Private recoverable file bundle for an executor-owned apply transaction.

The executor must hold the common process lock from prepare through recovery.
The journal contains credentials: never log, export, or put it in project memory.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from proxy_apply_coordinator import _atomic_json


class ApplyStateError(RuntimeError):
    pass


def _regular(path, limit):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None, None
    if not stat.S_ISREG(info.st_mode):
        raise ApplyStateError('Apply target is not a regular file')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise ApplyStateError('Apply target changed while reading')
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ApplyStateError('Apply target exceeds size limit')
    return data, info


def _digest(value):
    return None if value is None else hashlib.sha256(value).hexdigest()


def _decode(value):
    return None if value is None else base64.b64decode(value, validate=True)


class ApplyFileBundle:
    """Journal only explicitly allowed paths; recover only familiar contents.

    Atomic rename is per-file. The private journal supplies rollback across the
    bundle on crash; it does not pretend the filesystem has multi-file rename.
    Startup must recover this bundle BEFORE rebuilding config or starting Xray.
    """

    def __init__(self, directory, allowed_paths, *, limit=2 * 1024 * 1024):
        self.directory = Path(directory)
        self.path = self.directory / 'transaction.json'
        self.allowed = {str(Path(path).absolute()) for path in allowed_paths}
        self.limit = limit

    def pending(self):
        return self.path.exists() or self.path.is_symlink()

    def prepare(self, updates):
        if self.pending():
            raise ApplyStateError('Previous apply requires recovery')
        entries = []
        total = 0
        for target, desired in updates.items():
            path = Path(target).absolute()
            if str(path) not in self.allowed or type(desired) is not bytes:
                raise ApplyStateError('Apply target is not permitted')
            previous, info = _regular(path, self.limit)
            total += len(desired) + len(previous or b'')
            if total > self.limit:
                raise ApplyStateError('Apply bundle exceeds size limit')
            entries.append({
                'path': str(path),
                'old': None if previous is None else base64.b64encode(previous).decode('ascii'),
                'new': base64.b64encode(desired).decode('ascii'),
                'mode': stat.S_IMODE(info.st_mode) if info else 0o600,
                'uid': info.st_uid if info else os.getuid() if hasattr(os, 'getuid') else 0,
                'gid': info.st_gid if info else os.getgid() if hasattr(os, 'getgid') else 0,
            })
        if not entries:
            raise ApplyStateError('Empty apply bundle')
        _atomic_json(self.path, {'schema': 1, 'phase': 'prepared', 'entries': entries})

    def _load(self):
        raw, _ = _regular(self.path, self.limit * 2 + 65536)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
            if (value['schema'] != 1 or value['phase'] not in ('prepared', 'committed') or
                    not isinstance(value['entries'], list) or not value['entries']):
                raise ValueError
            seen = set()
            total = 0
            for item in value['entries']:
                if item['path'] not in self.allowed or item['path'] in seen:
                    raise ValueError
                seen.add(item['path'])
                for key in ('mode', 'uid', 'gid'):
                    if type(item[key]) is not int or item[key] < 0:
                        raise ValueError
                if item['mode'] > 0o777:
                    raise ValueError
                total += len(_decode(item['old']) or b'') + len(_decode(item['new']))
                if total > self.limit:
                    raise ValueError
            return value
        except (ValueError, KeyError, TypeError):
            raise ApplyStateError('Apply journal is invalid; manual recovery required') from None

    def _check_contents(self, entries):
        # Check every target before restoring any: do not overwrite an unrelated
        # external change with an old snapshot.
        for item in entries:
            current, _ = _regular(Path(item['path']), self.limit)
            if _digest(current) not in {_digest(_decode(item['old'])), _digest(_decode(item['new']))}:
                raise ApplyStateError('Apply target changed outside the transaction')

    def _write(self, item, value):
        path = Path(item['path'])
        if value is None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        else:
            fd, name = tempfile.mkstemp(prefix='.' + path.name + '-apply-', dir=path.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(value)
                    stream.flush()
                    if hasattr(os, 'fchown'):
                        os.fchown(stream.fileno(), item['uid'], item['gid'])
                    if hasattr(os, 'fchmod'):
                        os.fchmod(stream.fileno(), item['mode'])
                    os.fsync(stream.fileno())
                os.replace(name, path)
            finally:
                try:
                    os.unlink(name)
                except FileNotFoundError:
                    pass
        self._sync_directory(path.parent)

    @staticmethod
    def _sync_directory(path):
        if os.name != 'nt':
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def _clear(self):
        self.path.unlink()
        self._sync_directory(self.directory)

    def commit(self):
        value = self._load()
        if value is None or value['phase'] != 'prepared':
            raise ApplyStateError('No prepared file transaction')
        self._check_contents(value['entries'])
        try:
            for item in value['entries']:
                self._write(item, _decode(item['new']))
            value['phase'] = 'committed'
            _atomic_json(self.path, value)
        except BaseException:
            # Recovery is explicit so API and files can be rolled back together.
            # A caller must block further applies if recovery itself fails.
            raise ApplyStateError('File commit incomplete; recovery required') from None
        self._clear()

    def recover(self):
        value = self._load()
        if value is None:
            return 'none'
        self._check_contents(value['entries'])
        if value['phase'] == 'committed':
            for item in value['entries']:
                current, _ = _regular(Path(item['path']), self.limit)
                if current != _decode(item['new']):
                    raise ApplyStateError('Committed apply contents changed')
            result = 'committed'
        else:
            for item in value['entries']:
                self._write(item, _decode(item['old']))
            result = 'rolled_back'
        self._clear()
        return result
