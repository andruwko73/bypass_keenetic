"""Bound runtime logs without changing open file descriptors or adding a daemon."""
import contextlib
import os
import stat
import threading
import time

try:
    import fcntl
except ImportError:  # Local Windows tests; the router uses flock as well.
    fcntl = None

_LOCK = threading.RLock()
RUNTIME_LOG_LIMITS = {
    '/opt/etc/bot/error.log': 256 * 1024,
    '/opt/etc/error.log': 256 * 1024,
    '/opt/etc/xray/error.log': 512 * 1024,
    '/opt/etc/xray/access.log': 256 * 1024,
    '/opt/etc/v2ray/error.log': 512 * 1024,
    '/opt/etc/v2ray/access.log': 256 * 1024,
    '/opt/var/log/bypass-unblock-scheduler.log': 256 * 1024,
    '/opt/var/log/bypass-youtube-edge-prefetch.log': 256 * 1024,
}


@contextlib.contextmanager
def _open_locked(path, *, create=False):
    with _LOCK:
        flags = os.O_RDWR | (os.O_CREAT if create else 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
        fd = os.open(path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('log must be a regular file')
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            yield fd
        finally:
            os.close(fd)


def _trim_fd(fd, limit, *, extra=0):
    size = os.fstat(fd).st_size
    if size + extra <= limit:
        return False
    keep = max(0, limit // 2 - extra)
    os.lseek(fd, max(0, size - keep), os.SEEK_SET)
    tail = os.read(fd, keep) if keep else b''
    # Discard an incomplete UTF-8 line; retain the most recent complete lines.
    if size > keep and b'\n' in tail:
        tail = tail.split(b'\n', 1)[1]
    os.lseek(fd, 0, os.SEEK_SET)
    if tail:
        os.write(fd, tail)
    os.ftruncate(fd, len(tail))
    return True


def append_log(path, message, *, limit=256 * 1024, mode='a'):
    limit = max(1024, int(limit))
    text = str(message or '').rstrip('\n')
    if not text:
        return
    stamp = time.strftime('%Y-%m-%d %H:%M:%S %z')
    data = (stamp + ' ' + text[:8192] + '\n').encode('utf-8', errors='replace')
    data = data[:min(8192, limit // 2)].decode('utf-8', errors='ignore').encode('utf-8').rstrip(b'\n') + b'\n'
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with _open_locked(path, create=True) as fd:
        if mode == 'w':
            os.ftruncate(fd, 0)
        _trim_fd(fd, limit, extra=len(data))
        os.lseek(fd, 0, os.SEEK_END)
        os.write(fd, data)


def trim_logs(limits=None):
    """Periodic retention for stdout and external appenders; no archive copies.

    Cooperative writers use flock. External processes keep their append fd;
    copy/truncate retention is best effort for their concurrent diagnostic lines.
    """
    trimmed = 0
    for path, limit in (RUNTIME_LOG_LIMITS if limits is None else limits).items():
        try:
            if os.lstat(path).st_size <= limit:
                continue
            with _open_locked(path) as fd:
                trimmed += int(_trim_fd(fd, max(1024, int(limit))))
        except (OSError, ValueError):
            continue
    return trimmed
