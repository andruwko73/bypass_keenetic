import json
import os
import tempfile
import time

from protocol_catalog import PROTOCOL_DISPLAY_ORDER


VALID_PHASES = frozenset((
    'prepared',
    'candidate_installed',
    'candidate_verified',
    'restore_started',
    'restore_failed',
))
VALID_PROTOCOLS = frozenset(PROTOCOL_DISPLAY_ORDER)


def load_transaction(path):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            payload = json.load(file)
    except FileNotFoundError:
        return None
    except Exception:
        return None
    return normalize_transaction(payload)


def normalize_transaction(payload):
    if not isinstance(payload, dict):
        return None
    proto = str(payload.get('proto') or '').strip()
    original_id = str(payload.get('original_id') or '').strip().lower()
    candidate_id = str(payload.get('candidate_id') or '').strip().lower()
    phase = str(payload.get('phase') or '').strip().lower()
    if proto not in VALID_PROTOCOLS or len(original_id) != 40 or len(candidate_id) != 40:
        return None
    if not all(char in '0123456789abcdef' for char in original_id + candidate_id):
        return None
    if phase not in VALID_PHASES:
        return None
    try:
        started_at = float(payload.get('started_at') or 0.0)
        updated_at = float(payload.get('updated_at') or started_at)
    except (TypeError, ValueError):
        return None
    return {
        'schema': 1,
        'proto': proto,
        'original_id': original_id,
        'candidate_id': candidate_id,
        'trigger': str(payload.get('trigger') or '').strip()[:32],
        'phase': phase,
        'started_at': started_at,
        'updated_at': updated_at,
    }


def begin_transaction(path, proto, original_id, candidate_id, *, trigger='', now=None):
    now = time.time() if now is None else float(now)
    payload = normalize_transaction({
        'proto': proto,
        'original_id': original_id,
        'candidate_id': candidate_id,
        'trigger': trigger,
        'phase': 'prepared',
        'started_at': now,
        'updated_at': now,
    })
    if not payload:
        return False
    return _write_private_json(path, payload)


def update_phase(path, phase, *, now=None):
    phase = str(phase or '').strip().lower()
    if phase not in VALID_PHASES:
        return False
    payload = load_transaction(path)
    if not payload:
        return False
    payload['phase'] = phase
    payload['updated_at'] = time.time() if now is None else float(now)
    return _write_private_json(path, payload)


def clear_transaction(path):
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False


def _write_private_json(path, payload):
    directory = os.path.dirname(path)
    descriptor = None
    temporary = ''
    try:
        if directory:
            os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix='.youtube_failover_',
            suffix='.json',
            dir=directory or None,
        )
        with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
            descriptor = None
            json.dump(payload, file, ensure_ascii=False, separators=(',', ':'))
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        return True
    except Exception:
        return False
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except Exception:
                pass
        try:
            if temporary:
                os.remove(temporary)
        except FileNotFoundError:
            pass
        except Exception:
            pass
