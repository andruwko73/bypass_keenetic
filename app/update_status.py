import json
import os
import re
import time


UPDATE_STATUS_PATH = '/opt/etc/bot/update_status.json'
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


def write_update_status(
    *,
    command,
    running=True,
    progress=0,
    progress_label='',
    message='',
    target_version=None,
    path=UPDATE_STATUS_PATH,
    time_provider=time.time,
):
    now = float(time_provider())
    current = read_update_status(path)
    started_at = current.get('started_at') if current.get('running') and current.get('command') == command else now
    if target_version is None and current.get('running') and current.get('command') == command:
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
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as file:
            json.dump(status, file, ensure_ascii=False, separators=(',', ':'))
        os.replace(tmp_path, path)
    except Exception:
        pass
    return status


def finish_update_status(command, message='', *, progress=100, path=UPDATE_STATUS_PATH):
    return write_update_status(
        command=command,
        running=False,
        progress=progress,
        progress_label='Завершено',
        message=message,
        path=path,
    )
