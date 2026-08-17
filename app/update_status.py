import json
import os
import re
import time


UPDATE_STATUS_PATH = '/opt/etc/bot/update_status.json'
WEB_COMMAND_STATE_PATH = '/opt/etc/bot/web_command_state.json'
COMMAND_JOB_PATH = '/opt/etc/bot/telegram_command_job.json'
UPDATE_COMMANDS = {'update', 'update_fork', 'install', 'rollback_update'}
TARGET_VERSION_RE = re.compile(r'^v?[0-9][0-9A-Za-z._-]{0,40}$')


def _target_version(value):
    value = str(value or '').strip()
    return value if TARGET_VERSION_RE.fullmatch(value) else ''


def _default_status():
    return {
        'running': False,
        'command': '',
        'progress': 0,
        'progress_label': '',
        'message': '',
        'target_version': '',
        'started_at': 0,
        'updated_at': 0,
        'finished_at': 0,
    }


def normalize_update_status(value):
    status = _default_status()
    if isinstance(value, dict):
        status.update(value)
    try:
        status['progress'] = max(0, min(100, int(status.get('progress') or 0)))
    except Exception:
        status['progress'] = 0
    status['target_version'] = _target_version(status.get('target_version'))
    return status


def read_update_status(path=UPDATE_STATUS_PATH):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return normalize_update_status(json.load(file))
    except Exception:
        return _default_status()


def _read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            value = json.load(file)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write_json(path, value):
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as file:
            json.dump(value, file, ensure_ascii=False, separators=(',', ':'))
        os.replace(tmp_path, path)
        return True
    except Exception:
        return False


def sync_web_command_state(
    status,
    *,
    web_state_path=WEB_COMMAND_STATE_PATH,
    job_path=COMMAND_JOB_PATH,
):
    try:
        import web_command_state
    except Exception:
        return False
    state = _read_json(web_state_path)
    job = _read_json(job_path)
    matches = web_command_state.update_state_matches_command(state, status, job)
    if not matches:
        return False
    state_changed = web_command_state.reconcile_update_state(state, status, job)
    if state_changed and not _write_json(web_state_path, state):
        return False
    job_changed = bool(not status.get('running') and job.get('running'))
    if job_changed:
        job['running'] = False
        job['finished_at'] = float(status.get('finished_at') or time.time())
        _write_json(job_path, job)
    return state_changed or job_changed


def write_update_status(
    *,
    command,
    running=True,
    progress=0,
    progress_label='',
    message='',
    target_version=None,
    started_at=None,
    path=UPDATE_STATUS_PATH,
    time_provider=time.time,
    sync_web=False,
    web_state_path=WEB_COMMAND_STATE_PATH,
    job_path=COMMAND_JOB_PATH,
):
    now = float(time_provider())
    current = read_update_status(path)
    if started_at is None:
        started_at = current.get('started_at') if current.get('running') and current.get('command') == command else now
    try:
        same_run = bool(
            current.get('running')
            and current.get('command') == command
            and abs(float(current.get('started_at') or 0) - float(started_at or 0)) <= 10
        )
    except (TypeError, ValueError):
        same_run = False
    try:
        requested_progress = max(0, min(100, int(progress or 0)))
    except (TypeError, ValueError):
        requested_progress = 0
    if running and same_run and int(current.get('progress') or 0) > requested_progress:
        progress = current.get('progress') or 0
        progress_label = current.get('progress_label') or progress_label
        message = current.get('message') or message
    if target_version is None and same_run:
        target_version = current.get('target_version', '')
    status = normalize_update_status({
        'running': bool(running),
        'command': command,
        'progress': progress,
        'progress_label': progress_label,
        'message': message,
        'target_version': target_version,
        'started_at': started_at or now,
        'updated_at': now,
        'finished_at': 0 if running else now,
    })
    _write_json(path, status)
    if sync_web:
        sync_web_command_state(status, web_state_path=web_state_path, job_path=job_path)
    return status


def finish_update_status(
    command,
    message='',
    *,
    progress=100,
    path=UPDATE_STATUS_PATH,
    sync_web=False,
    web_state_path=WEB_COMMAND_STATE_PATH,
    job_path=COMMAND_JOB_PATH,
):
    return write_update_status(
        command=command,
        running=False,
        progress=progress,
        progress_label='Завершено',
        message=message,
        path=path,
        sync_web=sync_web,
        web_state_path=web_state_path,
        job_path=job_path,
    )
