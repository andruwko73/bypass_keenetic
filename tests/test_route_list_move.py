"""Whole-list moves preserve custom entries without expanding the service catalog."""
import ast
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import unblock_lists as lists
import web_post_actions


@pytest.mark.parametrize('source,target', [(a, b) for a in lists.DEFAULT_ORDER for b in lists.DEFAULT_ORDER if a != b])
def test_move_all_addresses_without_touching_other_lists(tmp_path, source, target):
    originals = {name: ('# ' + name + '\ncustom-' + name + '.example\n') for name in lists.DEFAULT_ORDER}
    originals[source] += 'youtube.com\n192.0.2.3\n198.51.100.0/24\n2001:db8::/32\nshared.example\nshared.example\n'
    originals[target] += 'shared.example\n'
    for name, content in originals.items():
        (tmp_path / name).write_text(content, encoding='utf-8')
    updates = []
    def apply():
        assert (tmp_path / source).read_text() == ''
        assert '192.0.2.3' in (tmp_path / target).read_text()
        updates.append(True)
    result = lists.move_unblock_list(source, target, unblock_dir=str(tmp_path), apply_changes=apply)
    assert result['changed'] and result['entries'] == 6 and updates == [True]
    expected = lists.normalize_unblock_list(originals[source] + originals[target])
    assert result['list_contents'] == {source: '', target: expected}
    assert (tmp_path / target).read_text() == expected + '\n'
    for name in set(originals) - {source, target}:
        assert (tmp_path / name).read_text() == originals[name]
    assert len(list(tmp_path.iterdir())) == 6
    again = lists.move_unblock_list(source, target, unblock_dir=str(tmp_path), apply_changes=apply)
    assert not again['changed'] and updates == [True]


@pytest.mark.parametrize('source,target', [('vless.txt', 'vless.txt'), ('../vless.txt', 'hysteria2.txt'),
    ('vless.txt', r'..\hysteria2.txt'), ('vpn.txt', 'hysteria2.txt'), ('vless', 'hysteria2.txt')])
def test_invalid_move_leaves_files_untouched(tmp_path, source, target):
    (tmp_path / 'vless.txt').write_bytes(b'custom.example\n')
    with pytest.raises(ValueError):
        lists.move_unblock_list(source, target, unblock_dir=str(tmp_path))
    assert (tmp_path / 'vless.txt').read_bytes() == b'custom.example\n'
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize('failure', ['target_write', 'source_write', 'apply', 'apply_and_restore'])
def test_failure_restores_exact_bytes_and_cleans_staged_files(tmp_path, monkeypatch, failure):
    originals = {'vless.txt': b'# custom\r\nz.example\r\na.example\r\n', 'hysteria2.txt': b'existing.example\n'}
    for name, content in originals.items():
        (tmp_path / name).write_bytes(content)
    replace = lists.os.replace
    calls = []
    def failed_replace(staged, target):
        name = Path(target).name
        if (failure == 'target_write' and name == 'hysteria2.txt') or (failure == 'source_write' and name == 'vless.txt'):
            raise OSError('fixture disk full')
        return replace(staged, target)
    monkeypatch.setattr(lists.os, 'replace', failed_replace)
    def apply():
        calls.append(True)
        if failure == 'apply_and_restore' or (failure == 'apply' and len(calls) == 1):
            raise RuntimeError('fixture apply error')
    with pytest.raises(RuntimeError, match='прежние маршруты' if failure == 'apply_and_restore' else 'Изменения отменены'):
        lists.move_unblock_list('vless.txt', 'hysteria2.txt', unblock_dir=str(tmp_path), apply_changes=apply)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == originals
    assert len(calls) == (2 if failure.startswith('apply') else 0)


def test_missing_target_does_not_clear_source(tmp_path):
    (tmp_path / 'vless.txt').write_bytes(b'custom.example\n')
    with pytest.raises(FileNotFoundError):
        lists.move_unblock_list('vless.txt', 'hysteria2.txt', unblock_dir=str(tmp_path))
    assert (tmp_path / 'vless.txt').read_bytes() == b'custom.example\n'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX ownership/symlink checks')
def test_permissions_and_symlink_rejection(tmp_path):
    source, target = tmp_path / 'vless.txt', tmp_path / 'hysteria2.txt'
    source.write_text('custom.example\n')
    target.write_text('existing.example\n')
    source.chmod(0o600)
    target.chmod(0o640)
    metadata = {p.name: (p.stat().st_mode, p.stat().st_uid, p.stat().st_gid) for p in (source, target)}
    lists.move_unblock_list(source.name, target.name, unblock_dir=str(tmp_path))
    assert {p.name: (p.stat().st_mode, p.stat().st_uid, p.stat().st_gid) for p in (source, target)} == metadata
    source.unlink()
    source.symlink_to(target)
    with pytest.raises(ValueError, match='обычным файлом'):
        lists.move_unblock_list(source.name, target.name, unblock_dir=str(tmp_path))


@pytest.mark.parametrize('enabled', [False, True])
def test_endpoint_all_modes_returns_only_affected_lists(tmp_path, enabled):
    for name in ('vless.txt', 'hysteria2.txt'):
        (tmp_path / name).write_text(name + '.example\n')
    result = web_post_actions.dispatch({'custom_checks_enabled': enabled,
        'service_routes_payload': lambda: {'route_tools_html': '<div>updated routes</div>'},
        'move_route_list': lambda a, b: lists.move_unblock_list(a, b, unblock_dir=str(tmp_path))},
        '/route_list_move', {'source_list': ['vless.txt'], 'target_list': ['hysteria2.txt']})
    assert result['success'] and 'Vless 1' in result['result'] and 'Hysteria2' in result['result']
    assert set(result['extra']['list_contents']) == {'vless.txt', 'hysteria2.txt'}
    assert ('route_tools_html' in result['extra']) == enabled


def test_route_card_refresh_failure_does_not_report_move_failure(tmp_path):
    for name in ('vless.txt', 'hysteria2.txt'):
        (tmp_path / name).write_text(name + '.example\n')
    def fail():
        raise RuntimeError('fixture render error')
    result = web_post_actions.dispatch({'custom_checks_enabled': True, 'service_routes_payload': fail,
        'move_route_list': lambda a, b: lists.move_unblock_list(a, b, unblock_dir=str(tmp_path))},
        '/route_list_move', {'source_list': ['vless.txt'], 'target_list': ['hysteria2.txt']})
    assert result['success'] and 'Обновите страницу' in result['result']
    assert result['extra']['list_contents']['vless.txt'] == ''


def test_failed_endpoint_does_not_return_empty_snapshots():
    def fail(*args):
        raise ValueError('fixture failure')
    result = web_post_actions.dispatch({'move_route_list': fail}, '/route_list_move', {})
    assert not result['success'] and 'list_contents' not in result['extra']


def bot_functions(*names, **context):
    tree = ast.parse((ROOT / 'app/bot.py').read_text(encoding='utf-8-sig'))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(selected) == len(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), 'bot-functions', 'exec'), context)
    return context


def test_bot_move_uses_strict_apply_under_mutation_lock(monkeypatch):
    import route_move_runtime
    calls, lock = [], threading.Lock()
    def move(a, b, **kwargs):
        assert lock.locked() and (a, b) == ('vless.txt', 'hysteria2.txt')
        kwargs['apply_changes']()
        return {'changed': True}
    monkeypatch.setattr(lists, 'move_unblock_list', move)
    monkeypatch.setattr(route_move_runtime, 'run_update', lambda affected: calls.append(affected))
    ctx = bot_functions('_move_route_list', service_route_mutation_lock=lock,
        os=os, time=time, _write_runtime_log=lambda text: None,
        _sync_proxy_route_policy_config=lambda **kw: calls.append(kw),
        subprocess=SimpleNamespace(DEVNULL=-3, run=lambda *args, **kw: calls.append(kw)),
        _web_route_tools_runtime=None, _invalidate_web_status_cache=lambda: None)
    assert ctx['_move_route_list']('vless.txt', 'hysteria2.txt') == {'changed': True}
    assert calls[0] == {'strict': True} and set(calls[1].split()) == {'unblockvless', 'unblockhy2'}


@pytest.mark.parametrize('raises', [False, True])
def test_strict_policy_sync_propagates_core_failure(raises):
    def restart():
        if raises:
            raise OSError('fixture')
        return False, 'fixture'
    ctx = bot_functions('_sync_proxy_route_policy_config', _sync_udp_policy_config=lambda **kw: None,
        XRAY_STRICT_TRANSPARENT_PROTOCOLS=('vless',), _write_all_proxy_core_config=lambda: None,
        _restart_core_proxy_after_validation=restart, _write_runtime_log=lambda msg: None,
        _invalidate_web_status_cache=lambda: None, _invalidate_key_status_cache=lambda: None)
    ctx['_sync_proxy_route_policy_config']()
    with pytest.raises(RuntimeError, match='Xray'):
        ctx['_sync_proxy_route_policy_config'](strict=True)


def test_progress_get_is_read_only_and_duplicate_move_is_rejected():
    import route_move_runtime
    import web_get_actions
    assert route_move_runtime.begin()
    try:
        route_move_runtime.phase('Обновление DNS и адресов')
        result = web_get_actions.dispatch({}, '/api/route_move_status')
        assert result['payload']['running'] and result['payload']['stage'] == 'Обновление DNS и адресов'
        response = web_post_actions.dispatch({'move_route_list': lambda *a: pytest.fail('duplicate ran')},
            '/route_list_move', {'source_list': ['vless.txt'], 'target_list': ['vmess.txt']})
        assert not response['success'] and 'уже выполняется' in response['result']
    finally:
        route_move_runtime.finish()
    assert not route_move_runtime.snapshot()['running']


def test_unchanged_attested_route_config_does_not_restart():
    ctx = bot_functions('_sync_proxy_route_policy_config', _sync_udp_policy_config=lambda **kw: None,
        XRAY_STRICT_TRANSPARENT_PROTOCOLS=('vless',),
        proxy_live_backend=SimpleNamespace(confirms_config=lambda config: config == {'same': True}),
        _logical_proxy_config=lambda: {'same': True}, _write_runtime_log=lambda text: None,
        _write_all_proxy_core_config=lambda: pytest.fail('unchanged config rewritten'),
        _restart_core_proxy_after_validation=lambda: pytest.fail('unchanged core restarted'))
    ctx['_sync_proxy_route_policy_config'](strict=True)
