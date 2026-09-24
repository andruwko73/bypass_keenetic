"""Bounded process/thread coordination for proxy configuration transactions.

This module has no network or service side effects. Runtime attestation must be
provided by the executor after a controlled apply and a data-plane check.
State paths belong in a private directory on RAM storage, not on flash.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
import errno
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import time


class ApplyBusy(RuntimeError):
    pass


class StaleApply(RuntimeError):
    pass


class ProcessRLock:
    """Kernel-released advisory lock, reentrant only in the owning thread.

    All instances for a path must use the same persistent lock inode. Never
    unlink a lock file: a process could still hold the old inode after unlink.
    There is deliberately no unlocked fallback on filesystem/lock errors.
    """

    def __init__(self, path, *, timeout=20.0):
        self.path = Path(path)
        self.timeout = timeout
        self._thread_lock = threading.RLock()
        self._owner = None
        self._depth = 0
        self._fd = None
        self._pid = os.getpid()

    def _after_fork(self):
        if self._pid != os.getpid():
            if self._fd is not None:
                os.close(self._fd)
            self._fd, self._owner, self._depth = None, None, 0
            self._thread_lock = threading.RLock()
            self._pid = os.getpid()

    @staticmethod
    def _try_lock(fd):
        try:
            if os.name == 'nt':
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                return False
            raise

    def acquire(self, blocking=True, timeout=-1):
        self._after_fork()
        wait = self.timeout if timeout == -1 else timeout
        if wait < 0:
            raise ValueError('Invalid lock timeout')
        deadline = time.monotonic() + (wait if blocking else 0)
        acquired = (self._thread_lock.acquire(timeout=wait) if blocking
                    else self._thread_lock.acquire(blocking=False))
        if not acquired:
            return False
        if self._owner == threading.get_ident():
            self._depth += 1
            return True
        fd = None
        try:
            # Directory ownership is established by the executor at startup.
            if self.path.is_symlink():
                raise OSError('Unsafe apply lock')
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError('Unsafe apply lock')
            while not self._try_lock(fd):
                if not blocking or time.monotonic() >= deadline:
                    os.close(fd)
                    self._thread_lock.release()
                    return False
                time.sleep(min(.02, max(0, deadline - time.monotonic())))
            self._fd, self._owner, self._depth = fd, threading.get_ident(), 1
            return True
        except BaseException:
            if fd is not None:
                os.close(fd)
            self._thread_lock.release()
            raise

    def release(self):
        self._after_fork()
        if self._owner != threading.get_ident():
            raise RuntimeError('Apply lock is not owned by this thread')
        self._depth -= 1
        try:
            if self._depth == 0:
                fd, self._fd, self._owner = self._fd, None, None
                # Closing the descriptor releases the kernel lock on both OSes.
                os.close(fd)
        finally:
            self._thread_lock.release()

    def locked(self):
        self._after_fork()
        if self._depth:
            return True
        if not self.acquire(blocking=False):
            return True
        self.release()
        return False

    def __enter__(self):
        if not self.acquire():
            raise ApplyBusy('Proxy apply is busy')
        return self

    def __exit__(self, *_):
        self.release()


def _read_json(path):
    if path.is_symlink():
        raise OSError('Unsafe apply state')
    try:
        with path.open('rb') as stream:
            data = stream.read(16385)
        if len(data) > 16384:
            raise ValueError('Apply state exceeds limit')
        return json.loads(data)
    except FileNotFoundError:
        return None


def _atomic_json(path, data):
    if path.is_symlink():
        raise OSError('Unsafe apply state')
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, separators=(',', ':'), allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        if os.name != 'nt':
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class ApplyTicket:
    generation: int
    manual_epoch: int


class ApplyCoordinator:
    """Intent arbitration separate from the long-running execution lock.

    Background work captures a ticket BEFORE probing. A manual intent can
    invalidate it even while an API call is in progress. An executor must
    recheck current() before each mutation and before committing success.
    A failed current() after a mutation requires executor rollback/recovery.
    """

    def __init__(self, directory, *, timeout=20):
        self.directory = Path(directory)
        self.lock = ProcessRLock(self.directory / 'apply.lock', timeout=timeout)
        self._state_lock = ProcessRLock(self.directory / 'intent.lock', timeout=timeout)
        self._state_path = self.directory / 'intent.json'
        self._local = threading.local()
        self._local_pid = os.getpid()

    def _context(self):
        if self._local_pid != os.getpid():
            self._local = threading.local()
            self._local_pid = os.getpid()
        return getattr(self._local, 'context', None)

    def _state(self):
        state = _read_json(self._state_path)
        if state is None:
            return {'generation': 0, 'manual_epoch': 0, 'pending_manual': None}
        if (not isinstance(state, dict) or
                any(type(state.get(k)) is not int or state[k] < 0
                    for k in ('generation', 'manual_epoch')) or
                (state.get('pending_manual') is not None and
                 (type(state['pending_manual']) is not int or state['pending_manual'] < 0))):
            raise ValueError('Invalid apply intent state')
        return state

    def capture(self):
        with self._state_lock:
            state = self._state()
            if state['pending_manual'] is not None:
                raise ApplyBusy('Manual apply is pending')
            return ApplyTicket(state['generation'], state['manual_epoch'])

    def generation(self):
        with self._state_lock:
            return self._state()['generation']

    def token(self):
        with self._state_lock:
            state = self._state()
            return ApplyTicket(state['generation'], state['manual_epoch'])

    def cancel_manual(self, ticket):
        with self._state_lock:
            state = self._state()
            if state['pending_manual'] == ticket.generation:
                state['pending_manual'] = None
                _atomic_json(self._state_path, state)

    @contextmanager
    def intent(self, *, manual=False):
        """Capture before background probes, without holding the execution lock."""
        existing = self._context()
        if existing is not None:
            if manual:
                raise RuntimeError('A manual intent cannot be nested')
            yield existing['ticket']
            return
        ticket = self.request_manual() if manual else self.capture()
        self._local.context = {'ticket': ticket, 'manual': manual, 'depth': 0}
        try:
            yield ticket
        finally:
            del self._local.context
            if manual:
                self.cancel_manual(ticket)

    @contextmanager
    def mutation(self, *, manual=False):
        """Serialize a writer; nested writers share its accepted generation.

        Reversible executors explicitly recheck the ticket before committing.
        This wrapper alone does not interrupt a partially executed cold apply.
        """
        context = self._context()
        if context is None:
            with self.intent(manual=manual):
                with self.mutation() as ticket:
                    yield ticket
            return
        if manual:
            raise RuntimeError('A manual mutation cannot be nested')
        if context['depth']:
            yield context['ticket']
            return
        try:
            with self.transaction(context['ticket'], manual=context['manual']) as accepted:
                context['ticket'] = accepted
                context['depth'] = 1
                try:
                    yield accepted
                finally:
                    context['depth'] = 0
        finally:
            context['manual'] = False

    def active_ticket(self):
        context = self._context()
        if context is None or not context['depth']:
            raise RuntimeError('No active apply transaction')
        return context['ticket']

    def request_manual(self):
        with self._state_lock:
            state = self._state()
            state['generation'] += 1
            state['manual_epoch'] += 1
            state['pending_manual'] = state['generation']
            _atomic_json(self._state_path, state)
            return ApplyTicket(state['generation'], state['manual_epoch'])

    def current(self, ticket):
        with self._state_lock:
            state = self._state()
            return ticket == ApplyTicket(state['generation'], state['manual_epoch'])

    def require_current(self, ticket):
        if not self.current(ticket):
            raise StaleApply('Apply intent was superseded')

    @contextmanager
    def commit_guard(self, ticket):
        """Serialize a short file commit against arrival of a manual intent.

        Never run probes or subprocesses inside this guard. Execution lock
        must already be held; the lock order is execution then intent.
        """
        if self.lock._owner != threading.get_ident():
            raise RuntimeError('Commit requires the apply lock')
        with self._state_lock:
            state = self._state()
            if ticket != ApplyTicket(state['generation'], state['manual_epoch']):
                raise StaleApply('Apply intent was superseded')
            yield

    @contextmanager
    def transaction(self, ticket, *, manual=False):
        try:
            with self.lock:
                with self._state_lock:
                    state = self._state()
                    if ticket != ApplyTicket(state['generation'], state['manual_epoch']):
                        raise StaleApply('Apply intent was superseded')
                    if manual:
                        if state['pending_manual'] != ticket.generation:
                            raise StaleApply('Manual intent is not pending')
                    else:
                        if state['pending_manual'] is not None:
                            raise ApplyBusy('Manual apply is pending')
                        state['generation'] += 1
                        _atomic_json(self._state_path, state)
                        ticket = ApplyTicket(state['generation'], state['manual_epoch'])
                yield ticket
        finally:
            if manual:
                self.cancel_manual(ticket)

    def recover_abandoned_manual(self, *, minimum_generation=0):
        """Startup recovery only, after taking the single application lock.

        This invalidates all old tickets. It does not recover runtime/config;
        the executor must resolve its transaction journal before accepting work.
        """
        if type(minimum_generation) is not int or minimum_generation < 0:
            raise ValueError('Invalid generation floor')
        with self.lock, self._state_lock:
            state = self._state()
            state['generation'] = max(state['generation'], minimum_generation) + 1
            state['manual_epoch'] += 1
            state['pending_manual'] = None
            _atomic_json(self._state_path, state)


def process_identity(pid, *, proc_root='/proc'):
    """Linux boot identity + PID + start ticks; PID reuse cannot attest state."""
    if type(pid) is not int or pid <= 0:
        raise ValueError('Invalid process identity')
    root = Path(proc_root)
    boot = (root / 'sys/kernel/random/boot_id').read_text(encoding='ascii').strip()
    line = (root / str(pid) / 'stat').read_text(encoding='ascii')
    tail = line.rsplit(')', 1)[1].split()
    ticks = int(tail[19])  # Field 22, with pid/comm removed.
    if not boot or ticks < 0 or int(line.split('(', 1)[0]) != pid:
        raise ValueError('Invalid process identity')
    return f'{boot}:{pid}:{ticks}'


def private_runtime_directory(path):
    path = Path(path)
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or (hasattr(os, 'geteuid') and info.st_uid != os.geteuid()):
        raise OSError('Unsafe proxy runtime directory')
    path.chmod(0o700)
    return path


def core_process_identity(binary, config_path, *, proc_root='/proc'):
    """Identify one core using this config; ignore isolated probe processes."""
    root, expected = Path(proc_root), str(Path(binary).resolve())
    config_file, config_dir = str(Path(config_path)), str(Path(config_path).parent)
    identities = []
    for child in root.iterdir():
        if not child.name.isdecimal():
            continue
        try:
            if str((child / 'exe').resolve()) != expected:
                continue
            with (child / 'cmdline').open('rb') as command_line:
                data = command_line.read(16384)
            args = data.decode('utf-8', errors='replace').split('\0')
            matches = False
            for index, arg in enumerate(args):
                flag, separator, value = arg.partition('=')
                if not separator:
                    value = args[index + 1] if index + 1 < len(args) else ''
                if (flag in ('-c', '-config', '--config') and value == config_file or
                        flag in ('-confdir', '--confdir') and value.rstrip('/') == config_dir):
                    matches = True
            if matches:
                identities.append(process_identity(int(child.name), proc_root=root))
        except (OSError, ValueError, IndexError):
            continue
    return identities[0] if len(identities) == 1 else None


def install_proxy_controls(namespace, coordinator, *, manual=(), background=(), writers=(), metadata=()):
    """Bind explicit application entry points after all functions are defined.

    Background wrappers capture an intent before probes, while writer wrappers
    acquire the execution lock. Manual wrappers do both with manual priority.
    """
    groups = {'manual': tuple(manual), 'background': tuple(background),
              'writer': tuple(writers), 'metadata': tuple(metadata)}
    names = [name for group in groups.values() for name in group]
    if len(names) != len(set(names)) or any(not callable(namespace.get(name)) for name in names):
        raise ValueError('Invalid proxy writer registry')

    def wrap(function, kind):
        @wraps(function)
        def controlled(*args, **kwargs):
            if kind == 'metadata':
                scope = coordinator.lock
            else:
                scope = coordinator.intent() if kind == 'background' else coordinator.mutation(manual=kind == 'manual')
            with scope:
                guard = namespace.get('_proxy_mutation_preflight')
                if kind != 'background' and callable(guard):
                    guard()
                return function(*args, **kwargs)
        controlled._proxy_control_kind = kind
        return controlled

    for kind, group in groups.items():
        for name in group:
            previous = getattr(namespace[name], '_proxy_control_kind', None)
            if previous is None:
                namespace[name] = wrap(namespace[name], kind)
            elif previous != kind:
                raise ValueError('Conflicting proxy writer registration')


def run_service_locked(service, action, *, directory='/tmp/bypass-proxy-apply', run=None):
    """Finish any apply before a planned service stop/update can interrupt it.

    Keep apply -> service lock ordering, including recursive restart calls.
    The child does not inherit the kernel lock descriptor. New bot startup can
    wait briefly for this wrapper while the init script confirms its process.
    """
    import subprocess
    if action not in ('stop', 'restart') or Path(service).name != 'S99telegram_bot':
        raise ValueError('Unsupported service operation')
    env = dict(os.environ, BYPASS_PROXY_SERVICE_LOCKED='1')
    control = ApplyCoordinator(private_runtime_directory(directory), timeout=180)
    with control.lock:
        return (run or subprocess.run)([service, action], env=env, close_fds=True,
                                       timeout=90, check=False).returncode


if __name__ == '__main__':
    import sys
    try:
        if len(sys.argv) != 4 or sys.argv[1] != '--service-lock':
            raise ValueError('Unsupported invocation')
        sys.exit(run_service_locked(sys.argv[2], sys.argv[3]))
    except Exception:
        print('Не удалось дождаться завершения операции с прокси; остановка отменена.', file=sys.stderr)
        sys.exit(1)
