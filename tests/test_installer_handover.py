"""Owner pairing and cleanup exercise real filesystem boundaries in a fixture."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('handover_common', Path(__file__).resolve().parents[1] / 'app/installer_common.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)


def test_pairing_legacy_and_incomplete_setup(tmp_path):
    state = tmp_path / 'state'
    assert common.installer_pairing_authorized('', str(state))
    state.mkdir()
    assert not common.installer_pairing_authorized('', str(state))
    code = 'a' * 32
    (state / 'pairing.code').write_text(code + '\n')
    header = 'Basic ' + base64.b64encode(('setup:' + code).encode()).decode()
    assert common.installer_pairing_authorized(header, str(state))
    assert not common.installer_pairing_authorized(header[:-2], str(state))
    assert not common.installer_pairing_authorized('Basic !!', str(state))


def cleanup_fixture(tmp_path):
    locations = {name: tmp_path / name for name in ('state_dir', 'work_dir', 'starter_dir', 'init_dir')}
    for path in locations.values():
        path.mkdir()
    state, work, starter, init = locations.values()
    manifest = b'commit\t' + b'a' * 40 + b'\n'
    receipt = hashlib.sha256(manifest).hexdigest().encode()
    (starter / 'manifest.tsv').write_bytes(manifest)
    (state / 'receipt.sha256').write_bytes(receipt)
    (work / 'owner').write_bytes(receipt)
    (state / 'state.tsv').write_bytes(b'phase\tconfigure\n' + manifest)
    (init / 'S01bypass_setup').write_text('owned wizard binary')
    (starter / 'wizard').write_text('owned wizard binary')
    (init / 'doinstall').write_text('unrelated installer')
    (init / 'S99telegram_bot').write_text('working service')
    (state / 'pairing.code').write_text('a' * 32)
    (state / 'error.tsv').write_text('code\tinterrupted\n')
    export = tmp_path / 'code.txt'
    export.write_bytes((state / 'pairing.code').read_bytes())
    locations['pairing_export'] = export
    return locations


def test_cleanup_preserves_service_receipt_and_is_repeatable(tmp_path):
    paths = cleanup_fixture(tmp_path)
    assert common.cleanup_self_service_setup(**paths)
    assert not paths['work_dir'].exists()
    assert not paths['starter_dir'].exists()
    assert not paths['pairing_export'].exists()
    assert not (paths['state_dir'] / 'error.tsv').exists()
    assert (paths['init_dir'] / 'S99telegram_bot').read_text() == 'working service'
    assert (paths['init_dir'] / 'doinstall').read_text() == 'unrelated installer'
    assert common.installer_setup_status(paths['state_dir'])['phase'] == 'ready'
    assert common.cleanup_self_service_setup(**paths)


@pytest.mark.parametrize('area,name', [('work_dir', 'owner'), ('starter_dir', 'manifest.tsv'),
                                     ('init_dir', 'S01bypass_setup'), ('state_dir', 'state.new')])
def test_cleanup_foreign_or_interrupted_state_deletes_nothing(tmp_path, area, name):
    paths = cleanup_fixture(tmp_path)
    (paths[area] / name).write_text('foreign')
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert not common.cleanup_self_service_setup(**paths)
    after = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert after == before


def test_first_password_goes_only_to_stdin(tmp_path, monkeypatch):
    (tmp_path / 'entware.secured').touch()
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return type('Result', (), {'returncode': 0})()
    monkeypatch.setattr(common.subprocess, 'run', run)
    common.set_initial_entware_password('fixture-password', str(tmp_path))
    assert calls[0][0] == ['/opt/bin/passwd', 'root']
    assert calls[0][1]['input'] == 'fixture-password\nfixture-password\n'
    with pytest.raises(ValueError):
        common.set_initial_entware_password('bad\npassword long', str(tmp_path))
    assert len(calls) == 1


@pytest.mark.parametrize('reply,bot_ready,polling,mode,expected', [
    (401, True, True, 'advanced', False), (200, False, False, 'advanced', False),
    (200, True, True, 'advanced', True), (200, False, False, 'web_only', True),
    (404, True, True, 'advanced', False), (200, True, False, 'advanced', False),
])
def test_handover_requires_own_authenticated_web_and_mode_readiness(tmp_path, monkeypatch, reply, bot_ready, polling, mode, expected):
    import http.client
    (tmp_path / 'static').mkdir()
    (tmp_path / 'static/app.js').write_bytes(b'our asset')
    config = tmp_path / 'config.py'
    config.write_text(f"routerip='192.168.1.1'\nbrowser_port=8080\nweb_auth_token='test-password'\napp_runtime_mode={mode!r}\n")
    requests, cleanup = [], []
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, method, path, headers):
            requests.append(path)
            assert headers['Authorization'].startswith('Basic ')
            self.path = path
        def getresponse(self): return self
        @property
        def status(self): return reply
        def read(self, limit):
            return b'our asset' if self.path.startswith('/static/') else json.dumps({'pool_probe_running': False, 'bot_ready': bot_ready, 'bot_polling': polling}).encode()
        def close(self): pass
    monkeypatch.setattr(http.client, 'HTTPConnection', Connection)
    monkeypatch.setattr(common.subprocess, 'run', lambda *a, **kw: type('Result', (), {'returncode': 0})())
    monkeypatch.setattr(common.time, 'sleep', lambda _: None)
    monkeypatch.setattr(common, 'cleanup_self_service_setup', lambda: cleanup.append(True) or True)
    assert common.finalize_self_service_setup(str(config), attempts=1) is expected
    assert bool(cleanup) is expected


def test_config_failed_atomic_replace_preserves_old_bytes(tmp_path, monkeypatch):
    config = tmp_path / 'config.py'
    config.write_bytes(b'old=1\n')
    def fail(*args): raise OSError('write failed')
    monkeypatch.setattr(common.os, 'replace', fail)
    with pytest.raises(OSError):
        common.write_installer_config(str(tmp_path), str(config), 'new=2\n', str(tmp_path / 'legacy.py'))
    assert config.read_bytes() == b'old=1\n'
    assert list(tmp_path.iterdir()) == [config]
