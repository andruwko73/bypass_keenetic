import base64
from collections import deque
import os
import queue
import signal
import stat
import subprocess
import tarfile
import threading
import time
from urllib.parse import quote

import requests


SCRIPT_PATH = '/opt/root/script.sh'
SCRIPT_MODE = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
PROGRESS_INTERVAL_SECONDS = 0.5
PROGRESS_TAIL_BYTES = 16 * 1024
INACTIVITY_TIMEOUT_SECONDS = 10 * 60
HARD_TIMEOUT_SECONDS = 45 * 60
TERMINATE_GRACE_SECONDS = 60
FORCE_KILL_WAIT_SECONDS = 5
OUTPUT_QUEUE_SIZE = 256
OUTPUT_POLL_SECONDS = 0.2
ACTIVITY_PROBE_INTERVAL_SECONDS = 1.0
TIMEOUT_RETURN_CODE = 124


class _LiveLogTail:
    def __init__(self, max_bytes):
        self.max_bytes = max(1, int(max_bytes))
        self._items = deque()
        self._size = 0

    @staticmethod
    def _encoded_size(value):
        return len(value.encode('utf-8', errors='replace'))

    def append(self, value):
        value = str(value)
        separator_size = 1 if self._items else 0
        self._items.append(value)
        self._size += separator_size + self._encoded_size(value)

        while len(self._items) > 1 and self._size > self.max_bytes:
            removed = self._items.popleft()
            self._size -= self._encoded_size(removed) + 1

        if self._size > self.max_bytes and self._items:
            encoded = self._items.pop().encode('utf-8', errors='replace')
            value = encoded[-self.max_bytes:].decode('utf-8', errors='ignore')
            self._items.append(value)
            self._size = self._encoded_size(value)

    def text(self):
        return '\n'.join(self._items)


def _put_output_event(output_queue, stop_event, event):
    while not stop_event.is_set():
        try:
            output_queue.put(event, timeout=OUTPUT_POLL_SECONDS)
            return True
        except queue.Full:
            continue
    return False


def _read_process_output(stdout, output_queue, stop_event):
    try:
        if stdout is not None:
            for line in stdout:
                if stop_event.is_set() or not _put_output_event(output_queue, stop_event, ('line', line)):
                    break
    except Exception as exc:
        _put_output_event(output_queue, stop_event, ('error', type(exc).__name__))
    finally:
        _put_output_event(output_queue, stop_event, ('eof', None))


def _signal_process_group(process, signal_value):
    pid = int(getattr(process, 'pid', 0) or 0)
    if os.name == 'posix' and pid > 0:
        try:
            os.killpg(pid, signal_value)
            return
        except ProcessLookupError:
            return
        except Exception:
            pass
    try:
        if signal_value == signal.SIGTERM:
            process.terminate()
        else:
            process.kill()
    except Exception:
        pass


def _terminate_process_group(process, grace_seconds, force_wait_seconds=FORCE_KILL_WAIT_SECONDS):
    _signal_process_group(process, signal.SIGTERM)
    try:
        return process.wait(timeout=max(0.0, float(grace_seconds))), False
    except subprocess.TimeoutExpired:
        pass

    _signal_process_group(process, getattr(signal, 'SIGKILL', 9))
    try:
        return process.wait(timeout=max(0.0, float(force_wait_seconds))), True
    except subprocess.TimeoutExpired:
        return getattr(process, 'returncode', None), True


def _timeout_message(reason, seconds):
    if reason == 'inactivity':
        return f'Обновление остановлено: нет активности {int(seconds)} секунд.'
    return f'Обновление остановлено: превышен общий лимит {int(seconds)} секунд.'


def fetch_remote_text(url, timeout=20):
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def _archive_ref_candidates(repo_ref):
    yield repo_ref
    if not repo_ref.startswith('refs/'):
        yield f'refs/heads/{repo_ref}'
        yield f'refs/tags/{repo_ref}'


def download_repo_file_from_archive(session, repo_owner, repo_name, repo_ref, path):
    suffix = '/' + path.strip('/')
    last_error = None
    for archive_ref in _archive_ref_candidates(repo_ref):
        archive_url = f'https://codeload.github.com/{repo_owner}/{repo_name}/tar.gz/{archive_ref}'
        try:
            with session.get(archive_url, stream=True, timeout=(10, 90)) as response:
                response.raise_for_status()
                response.raw.decode_content = True
                with tarfile.open(fileobj=response.raw, mode='r|gz') as archive:
                    for member in archive:
                        if member.isfile() and member.name.endswith(suffix):
                            extracted = archive.extractfile(member)
                            if extracted is not None:
                                return archive_url, extracted.read().decode('utf-8')
        except Exception as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    raise ValueError(f'Архив GitHub не содержит {path}')


def download_repo_file_text(session, repo_owner, repo_name, repo_ref, path):
    headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
    raw_url = f'https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{repo_ref}/{path}'
    try:
        response = session.get(raw_url, headers=headers, timeout=(5, 8))
        response.raise_for_status()
        return raw_url, response.text
    except requests.RequestException:
        pass

    try:
        return download_repo_file_from_archive(session, repo_owner, repo_name, repo_ref, path)
    except Exception:
        pass

    api_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{quote(path, safe="/")}'
    response = session.get(
        api_url,
        params={'ref': repo_ref},
        headers={'Accept': 'application/vnd.github+json', **headers},
        timeout=(10, 30),
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get('encoding') != 'base64' or 'content' not in payload:
        raise ValueError('GitHub Contents API вернул неожиданный формат файла')
    content = ''.join(str(payload.get('content', '')).split())
    return response.url, base64.b64decode(content).decode('utf-8')


def resolve_repo_ref(session, repo_owner, repo_name, repo_ref):
    headers = {'Accept': 'application/vnd.github+json', 'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
    api_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/commits/{quote(repo_ref, safe="")}'
    try:
        response = session.get(api_url, headers=headers, timeout=(5, 12))
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return repo_ref
    sha = str(payload.get('sha') or '').strip()
    return sha or repo_ref


def download_repo_script(repo_owner, repo_name, branch='main'):
    session = requests.Session()
    session.trust_env = False
    repo_ref = resolve_repo_ref(session, repo_owner, repo_name, branch)
    url, script_text = download_repo_file_text(session, repo_owner, repo_name, repo_ref, 'script.sh')
    if '#!/bin/sh' not in script_text:
        raise ValueError('GitHub вернул некорректный script.sh')
    return url, script_text, repo_ref


def write_script(script_text, script_path=SCRIPT_PATH, mode=SCRIPT_MODE):
    with open(script_path, 'w', encoding='utf-8') as file:
        file.write(script_text)
    os.chmod(script_path, mode)


def direct_fetch_env(env_keys, environ=None):
    env = dict(os.environ if environ is None else environ)
    for key in env_keys:
        env.pop(key, None)
    return env


def run_script_and_collect(
    action,
    env,
    logs,
    progress_callback=None,
    script_path=SCRIPT_PATH,
    *,
    progress_interval_seconds=PROGRESS_INTERVAL_SECONDS,
    progress_tail_bytes=PROGRESS_TAIL_BYTES,
    inactivity_timeout_seconds=INACTIVITY_TIMEOUT_SECONDS,
    hard_timeout_seconds=HARD_TIMEOUT_SECONDS,
    terminate_grace_seconds=TERMINATE_GRACE_SECONDS,
    activity_probe=None,
    monotonic=time.monotonic,
):
    process = subprocess.Popen(
        ['/bin/sh', script_path, action],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        start_new_session=True,
    )

    live_tail = _LiveLogTail(progress_tail_bytes)
    for line in logs:
        live_tail.append(line)

    output_queue = queue.Queue(maxsize=OUTPUT_QUEUE_SIZE)
    reader_stop = threading.Event()
    reader = threading.Thread(
        target=_read_process_output,
        args=(process.stdout, output_queue, reader_stop),
        name='repo-update-output',
        daemon=True,
    )
    reader.start()

    progress_interval_seconds = max(0.0, float(progress_interval_seconds))
    inactivity_timeout_seconds = max(0.0, float(inactivity_timeout_seconds or 0))
    hard_timeout_seconds = max(0.0, float(hard_timeout_seconds or 0))
    started_at = monotonic()
    last_activity_at = started_at
    last_progress_at = None
    last_probe_at = started_at
    probe_value = None
    probe_initialized = False
    callback_enabled = progress_callback is not None
    callback_error_recorded = False
    eof_received = False
    timeout_reason = ''
    return_code = None

    if activity_probe is not None:
        try:
            probe_value = activity_probe()
            probe_initialized = True
        except Exception:
            pass

    def publish_progress(force=False):
        nonlocal callback_enabled, callback_error_recorded, last_progress_at
        if not callback_enabled:
            return
        now = monotonic()
        if (not force and last_progress_at is not None and
                now - last_progress_at < progress_interval_seconds):
            return
        try:
            progress_callback(live_tail.text())
            last_progress_at = now
        except Exception:
            callback_enabled = False
            if not callback_error_recorded:
                callback_error_recorded = True
                warning = 'Не удалось обновить промежуточный статус; выполнение продолжается.'
                logs.append(warning)
                live_tail.append(warning)

    try:
        while True:
            now = monotonic()

            if activity_probe is not None and now - last_probe_at >= ACTIVITY_PROBE_INTERVAL_SECONDS:
                last_probe_at = now
                try:
                    current_probe_value = activity_probe()
                except Exception:
                    current_probe_value = probe_value
                if probe_initialized and current_probe_value != probe_value:
                    last_activity_at = now
                probe_value = current_probe_value
                probe_initialized = True

            if hard_timeout_seconds and now - started_at >= hard_timeout_seconds:
                timeout_reason = 'hard'
                break
            if inactivity_timeout_seconds and now - last_activity_at >= inactivity_timeout_seconds:
                timeout_reason = 'inactivity'
                break

            wait_seconds = OUTPUT_POLL_SECONDS
            if hard_timeout_seconds:
                wait_seconds = min(wait_seconds, max(0.01, hard_timeout_seconds - (now - started_at)))
            if inactivity_timeout_seconds:
                wait_seconds = min(wait_seconds, max(0.01, inactivity_timeout_seconds - (now - last_activity_at)))

            try:
                event, payload = output_queue.get(timeout=wait_seconds)
            except queue.Empty:
                event = ''
                payload = None

            if event == 'line':
                clean_line = payload.strip()
                if clean_line:
                    logs.append(clean_line)
                    live_tail.append(clean_line)
                    last_activity_at = monotonic()
                    publish_progress()
            elif event == 'error':
                warning = f'Ошибка чтения вывода процесса ({payload}).'
                logs.append(warning)
                live_tail.append(warning)
            elif event == 'eof':
                eof_received = True

            if eof_received:
                return_code = process.poll()
                if return_code is not None:
                    break

        if timeout_reason:
            timeout_seconds = inactivity_timeout_seconds if timeout_reason == 'inactivity' else hard_timeout_seconds
            timeout_line = _timeout_message(timeout_reason, timeout_seconds)
            logs.append(timeout_line)
            live_tail.append(timeout_line)
            publish_progress(force=True)
            _terminated_code, forced = _terminate_process_group(process, terminate_grace_seconds)
            if forced:
                forced_line = 'Зависшая группа процессов завершена принудительно.'
                logs.append(forced_line)
                live_tail.append(forced_line)
            return_code = TIMEOUT_RETURN_CODE
        elif return_code is None:
            return_code = process.wait()
    finally:
        reader_stop.set()
        try:
            if process.stdout is not None:
                process.stdout.close()
        except Exception:
            pass
        reader.join(timeout=1.0)

    if return_code != 0:
        logs.append(f'Команда завершилась с кодом {return_code}.')
        live_tail.append(logs[-1])
    publish_progress(force=True)
    return return_code, '\n'.join(logs)
