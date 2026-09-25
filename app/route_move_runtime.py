"""Small read-only progress snapshot; reject duplicate HTTP list moves."""
import threading
import time
import os
import signal
import subprocess

_lock = threading.Lock()
_state = {'running': False, 'stage': '', 'started': 0.0}


def begin():
    with _lock:
        if _state['running']:
            return False
        _state.update(running=True, stage='Ожидание завершения текущей операции', started=time.monotonic())
        return True


def phase(label):
    with _lock:
        if _state['running']:
            _state['stage'] = label


def finish():
    with _lock:
        _state['running'] = False


def snapshot():
    with _lock:
        return {'running': _state['running'], 'stage': _state['stage'],
                'elapsed_seconds': round(time.monotonic() - _state['started'], 1) if _state['running'] else 0}


def run_update(affected):
    process = subprocess.Popen(['/opt/bin/unblock_update.sh'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=dict(os.environ, BYPASS_ROUTE_SETS=affected), start_new_session=True)
    try:
        code = process.wait(timeout=300)
        if code:
            raise RuntimeError('Не удалось обновить DNS и адреса маршрутов.')
    except subprocess.TimeoutExpired:
        # Only this invocation's process group; do not leave an old refresh
        # publishing ipsets while the caller is restoring the original lists.
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            pass
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        raise RuntimeError('Обновление маршрутов превысило время ожидания и остановлено.') from None
