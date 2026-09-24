from pathlib import Path
import os
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from proxy_apply_state import ApplyFileBundle, ApplyStateError


@pytest.fixture
def bundle(tmp_path):
    directory = tmp_path / 'private'
    directory.mkdir(mode=0o700)
    paths = [tmp_path / name for name in ('config.json', 'key', 'new-state')]
    paths[0].write_bytes(b'old config')
    paths[1].write_bytes(b'old key')
    changes = dict(zip(paths, (b'new config', b'new key', b'new marker')))
    return ApplyFileBundle(directory, paths), paths, changes


def test_bundle_commit_keeps_only_current_files(bundle):
    store, paths, changes = bundle
    store.prepare(changes)
    assert store.pending()
    assert paths[0].read_bytes() == b'old config'
    store.commit()
    assert not store.pending()
    assert all(path.read_bytes() == data for path, data in changes.items())
    assert not list(store.directory.iterdir())


@pytest.mark.parametrize('accepted', [False, True])
def test_service_acceptance_is_inside_recoverable_commit(bundle, accepted):
    store, paths, changes = bundle
    store.prepare(changes)
    def acknowledge():
        assert all(path.read_bytes() == data for path, data in changes.items())
        assert store._load()['phase'] == 'prepared'
        return accepted
    if accepted:
        store.commit(after_write=acknowledge)
        assert not store.pending()
    else:
        with pytest.raises(ApplyStateError):
            store.commit(after_write=acknowledge)
        assert store.recover() == 'rolled_back'
        assert paths[0].read_bytes() == b'old config'
        assert paths[1].read_bytes() == b'old key'
        assert not paths[2].exists()


@pytest.mark.parametrize('after', [0, 1, 2, 3])
def test_crash_after_each_file_can_restore_original_bundle(bundle, monkeypatch, after):
    store, paths, changes = bundle
    store.prepare(changes)
    write = store._write
    count = [0]
    def crash(item, value):
        if count[0] == after:
            raise OSError('injected power loss boundary')
        write(item, value)
        count[0] += 1
        if count[0] == after:
            raise OSError('injected power loss boundary')
    monkeypatch.setattr(store, '_write', crash)
    with pytest.raises(ApplyStateError):
        store.commit()
    restarted = ApplyFileBundle(store.directory, paths)
    assert restarted.recover() == 'rolled_back'
    assert paths[0].read_bytes() == b'old config'
    assert paths[1].read_bytes() == b'old key'
    assert not paths[2].exists()
    assert restarted.recover() == 'none'


def test_crash_after_durable_commit_keeps_new_files(bundle, monkeypatch):
    store, paths, changes = bundle
    store.prepare(changes)
    def crash():
        raise OSError('injected before journal cleanup')
    monkeypatch.setattr(store, '_clear', crash)
    with pytest.raises(OSError):
        store.commit()
    restarted = ApplyFileBundle(store.directory, paths)
    assert restarted.recover() == 'committed'
    assert all(path.read_bytes() == data for path, data in changes.items())


def test_external_change_is_not_overwritten_during_recovery(bundle):
    store, paths, changes = bundle
    store.prepare(changes)
    paths[1].write_bytes(b'new independent manual edit')
    with pytest.raises(ApplyStateError, match='outside the transaction'):
        store.recover()
    assert paths[1].read_bytes() == b'new independent manual edit'
    assert store.pending()


def test_second_apply_cannot_replace_pending_journal(bundle):
    store, _, changes = bundle
    store.prepare(changes)
    original = store.path.read_bytes()
    with pytest.raises(ApplyStateError, match='Previous apply'):
        store.prepare(changes)
    assert store.path.read_bytes() == original


def test_prepare_rejects_outside_target_without_touching_files(bundle, tmp_path):
    store, _, _ = bundle
    outside = tmp_path / 'unrelated'
    outside.write_bytes(b'keep')
    with pytest.raises(ApplyStateError, match='not permitted'):
        store.prepare({outside: b'overwrite'})
    assert outside.read_bytes() == b'keep'
    assert not store.pending()


def test_oversized_bundle_is_refused(bundle):
    store, paths, _ = bundle
    store.limit = 5
    with pytest.raises(ApplyStateError, match='size limit'):
        store.prepare({paths[0]: b'too much data'})
    assert not store.pending()


@pytest.mark.skipif(os.name == 'nt', reason='Requires POSIX permissions and symlinks')
def test_permissions_and_symlink_refusal(bundle, tmp_path):
    store, paths, changes = bundle
    paths[0].chmod(0o640)
    store.prepare(changes)
    assert store.path.stat().st_mode & 0o777 == 0o600
    store.commit()
    assert paths[0].stat().st_mode & 0o777 == 0o640
    assert paths[2].stat().st_mode & 0o777 == 0o600
    paths[1].unlink()
    paths[1].symlink_to(paths[0])
    with pytest.raises(ApplyStateError, match='regular file'):
        store.prepare(changes)
