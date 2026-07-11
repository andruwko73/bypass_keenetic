"""Single lightweight owner resolver for the YouTube route."""

import json
import os

from service_catalog import normalize_route_entry, service_route_entries


UNBLOCK_DIR = '/opt/etc/unblock'
STATE_PATH = '/opt/tmp/bypass-youtube-route-owner.json'
ROUTE_FILES = (
    ('shadowsocks', 'shadowsocks.txt'),
    ('vmess', 'vmess.txt'),
    ('vless', 'vless.txt'),
    ('vless2', 'vless-2.txt'),
    ('trojan', 'trojan.txt'),
)
ROUTE_PROTOCOLS = frozenset(protocol for protocol, _filename in ROUTE_FILES)


def _route_entries(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as file:
            return {
                normalized
                for line in file
                for normalized in (normalize_route_entry(line),)
                if normalized
            }
    except Exception:
        return set()


def _read_last_owner(state_path):
    try:
        with open(state_path, 'r', encoding='utf-8') as file:
            protocol = str((json.load(file) or {}).get('protocol') or '').strip().lower()
    except Exception:
        return ''
    return protocol if protocol in ROUTE_PROTOCOLS else ''


def _store_last_owner(state_path, protocol):
    if protocol not in ROUTE_PROTOCOLS or not state_path:
        return
    directory = os.path.dirname(state_path)
    temporary_path = f'{state_path}.tmp.{os.getpid()}'
    try:
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(temporary_path, 'w', encoding='utf-8') as file:
            json.dump({'protocol': protocol}, file, separators=(',', ':'))
        os.replace(temporary_path, state_path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass


def resolve_youtube_route_owner(*, unblock_dir=UNBLOCK_DIR, state_path=STATE_PATH):
    """Resolve YouTube ownership without guessing a protocol.

    A unique complete or partial owner becomes the last confirmed owner.  If a
    list rewrite is in progress, reuse only that owner.  A fresh incomplete
    configuration returns an empty protocol instead of silently forcing Vless 2.
    """
    expected = {
        normalized
        for entry in service_route_entries('youtube')
        for normalized in (normalize_route_entry(entry),)
        if normalized
    }
    if not expected:
        return {'protocol': _read_last_owner(state_path), 'source': 'last_confirmed'}

    coverage = []
    for protocol, filename in ROUTE_FILES:
        matched = len(expected & _route_entries(os.path.join(unblock_dir, filename)))
        coverage.append((matched, protocol))

    complete = [protocol for matched, protocol in coverage if matched == len(expected)]
    if len(complete) == 1:
        _store_last_owner(state_path, complete[0])
        return {'protocol': complete[0], 'source': 'complete'}
    best_count = max((matched for matched, _protocol in coverage), default=0)
    best = [protocol for matched, protocol in coverage if matched == best_count and matched > 0]
    if len(best) == 1:
        _store_last_owner(state_path, best[0])
        return {'protocol': best[0], 'source': 'partial'}
    previous = _read_last_owner(state_path)
    if previous:
        return {'protocol': previous, 'source': 'last_confirmed'}
    return {'protocol': '', 'source': 'ambiguous' if best_count else 'missing'}


def youtube_route_owner(*, unblock_dir=UNBLOCK_DIR, default='', state_path=STATE_PATH):
    """Return the confirmed owner, retaining ``default`` only for old callers."""
    owner = resolve_youtube_route_owner(
        unblock_dir=unblock_dir,
        state_path=state_path,
    ).get('protocol')
    return owner or str(default or '').strip().lower()
