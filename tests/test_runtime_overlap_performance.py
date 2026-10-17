"""Differential correctness and bounded work, without router data or timing gates."""
import importlib.util
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import route_intersections as routes
import service_routes
from service_catalog import service_route_entries

spec = importlib.util.spec_from_file_location('overlap_legacy', Path(__file__).parent / 'fixtures/runtime_overlap_1_1087.py')
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


def test_empty_pair_never_parses(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError('empty pair must not parse')
    monkeypatch.setattr(routes, '_ip_network', unexpected)
    assert routes._network_overlap_samples([], {'192.0.2.1'}) == ([], 0)
    assert routes._network_overlap_samples({'2001:db8::1'}, []) == ([], 0)


@pytest.mark.parametrize('seed', range(40))
def test_pairs_match_immutable_legacy(seed):
    rng = random.Random(seed)
    values = ['192.0.2.0/24', '192.0.2.0/25', '192.0.2.1', '192.0.2.1/32',
              '192.0.2.128/25', '198.51.100.1', '2001:db8::/32', '2001:db8::/64',
              '2001:db8::1', '2001:db8:1::/48', 'invalid', 'example.com']
    for _ in range(15):
        left = set(rng.sample(values, rng.randrange(len(values) + 1)))
        right = set(rng.sample(values, rng.randrange(len(values) + 1)))
        kwargs = dict(left_priority_members=set(rng.sample(values, 3)),
                      right_priority_members=set(rng.sample(values, 3)), max_samples=rng.choice([0, 1, 8]))
        assert routes._network_overlap_samples(left, right, **kwargs) == legacy._network_overlap_samples(left, right, **kwargs)


@pytest.mark.parametrize('seed', range(12))
def test_six_protocol_runtime_reports_match_legacy(monkeypatch, seed):
    rng = random.Random(seed)
    names = {name for sets in routes.ROUTE_IPSET_SETS.values() for name, _ in sets}
    names.update(name for sets in routes.ROUTE_PRIORITY_IPSET_SETS.values() for name in sets.values())
    values = ['192.0.2.0/24', '192.0.2.1', '192.0.2.0/25', '198.51.100.1',
              '2001:db8::/32', '2001:db8::1', 'invalid']
    snapshot = {name: set(rng.sample(values, rng.randrange(len(values) + 1))) for name in sorted(names)}
    for module in (routes, legacy):
        monkeypatch.setattr(module, 'read_runtime_ipset_members_map', lambda *a, **k: snapshot)
    for limit in (1, 8, 120):
        assert routes._runtime_ipset_intersections(max_issues=limit) == legacy._runtime_ipset_intersections(max_issues=limit)


def test_snapshot_parsed_once_and_not_cached_across_calls(monkeypatch):
    names = [name for sets in routes.ROUTE_IPSET_SETS.values() for name, _ in sets]
    snapshot = {name: {'192.0.2.1', '2001:db8::1'} for name in names}
    calls = []
    original = routes._ip_network
    def parse(value):
        calls.append(value)
        return original(value)
    monkeypatch.setattr(routes, '_ip_network', parse)
    monkeypatch.setattr(routes, 'read_runtime_ipset_members_map', lambda *a, **k: snapshot)
    routes._runtime_ipset_intersections()
    assert len(calls) == len(names) * 2
    calls.clear()
    snapshot = {name: set() for name in names}
    assert routes._runtime_ipset_intersections() == []
    assert calls == []


def runner(snapshot, deleted):
    def run(args, **kwargs):
        if args == ['ipset', 'save']:
            text = '\n'.join('create ' + name + ' hash:net\n' + '\n'.join('add ' + name + ' ' + value for value in sorted(values)) for name, values in snapshot.items())
            return SimpleNamespace(stdout=text, returncode=0)
        if args[:2] == ['ipset', 'del']:
            deleted.append(tuple(args[2:]))
            snapshot[args[2]].discard(args[3])
            return SimpleNamespace(stdout='', returncode=0)
        return SimpleNamespace(stdout='', returncode=1)
    return run


def test_cleanup_runtime_independent_of_static_report_limit(tmp_path, monkeypatch):
    # More than 120 unrelated static conflicts must not suppress real maintenance.
    duplicates = [f'host{i}.example' for i in range(130)]
    for route in ('vless', 'vless-2'):
        entries = duplicates + (service_route_entries('youtube') if route == 'vless-2' else [])
        (tmp_path / (route + '.txt')).write_text('\n'.join(entries), encoding='utf-8')
    snapshot = {'unblockvless': {'64.233.161.97'}, 'unblockvless2': {'64.233.161.0/24'}}
    deleted = []
    run = runner(snapshot, deleted)
    full = routes.analyze_route_intersections(unblock_dir=str(tmp_path), run_command=run)
    assert full['file_count'] >= routes.MAX_ISSUES and full['runtime_count'] == 0
    result = service_routes.cleanup_runtime_service_route_intersections(unblock_dir=str(tmp_path), run_command=run)
    assert result['deleted_members'] == 1
    assert deleted == [('unblockvless', '64.233.161.97')]
    assert '64.233.161.0/24' in snapshot['unblockvless2']


def test_runtime_report_keeps_service_annotations(monkeypatch):
    snapshot = {'unblockvless': {'64.233.161.97'}, 'unblockvless2': {'64.233.161.0/24'}}
    report = routes.analyze_runtime_route_intersections(run_command=runner(snapshot, []))
    assert report['issues'][0]['service_keys'] and 'youtube' in report['issues'][0]['service_keys']


def test_cleanup_disabled_runtime_does_not_read_ipsets(tmp_path):
    def unexpected(*args, **kwargs):
        raise AssertionError('runtime disabled')
    result = service_routes.cleanup_runtime_service_route_intersections(unblock_dir=str(tmp_path), include_runtime=False, run_command=unexpected)
    assert result['deleted_members'] == 0 and result['pairs'] == 0


def test_empty_runtime_skips_service_catalog_preparation(monkeypatch):
    monkeypatch.setattr(routes, '_runtime_ipset_intersections', lambda **kwargs: [])
    monkeypatch.setattr(routes, '_service_match_index', lambda: pytest.fail('unused catalog'))
    assert routes.analyze_runtime_route_intersections() == {'issues': [], 'count': 0}


def test_partial_failed_read_cannot_delete(tmp_path):
    def failed(*args, **kwargs):
        raise TimeoutError()
    result = service_routes.cleanup_runtime_service_route_intersections(unblock_dir=str(tmp_path), run_command=failed)
    assert result['deleted_members'] == result['pairs'] == 0


@pytest.mark.parametrize('owner', ['vless', 'vless2', 'vmess', 'trojan', 'shadowsocks', 'hysteria2', ''])
def test_priority_cache_is_bounded_to_due_pass(tmp_path, owner):
    import os
    import re
    import shutil
    import subprocess
    shell = r'C:\Program Files\Git\bin\bash.exe' if os.name == 'nt' else shutil.which('bash')
    if not shell or not Path(shell).is_file():
        pytest.skip('bash unavailable')
    source = (Path(__file__).resolve().parents[1] / 'app/S99unblock').read_text()
    def function(name):
        match = re.search(r'^' + name + r'\(\) \{.*?^\}', source, re.M | re.S)
        assert match
        return match.group(0)
    (tmp_path / 'youtube_route_owner.py').touch()
    script = function('youtube_route_protocol') + '\n' + function('apply_vless_priority_domain_ips_if_due') + r"""
BOT_DIR=.
UNBLOCK_DIR=.
YOUTUBE_ROUTE_OWNER_STATE_FILE=owner.json
python3() { echo call >> count; printf '%s\n' "$OWNER"; }
priority_refresh_due() { return 0; }
apply_vless_priority_domain_ips() { test "$(youtube_route_protocol)" = "$OWNER" || exit 21; }
dedupe_vless_priority_overlaps() { test "$(youtube_route_protocol)" = "$OWNER" || exit 22; }
mark_priority_refresh_done() { :; }
apply_vless_priority_domain_ips_if_due
OWNER=trojan
apply_vless_priority_domain_ips_if_due
test "$(wc -l < count)" -eq 2
"""
    result = subprocess.run([str(shell), '-s'], input=script, text=True, cwd=tmp_path,
                            env=dict(os.environ, OWNER=owner), capture_output=True)
    assert result.returncode == 0, 'cache must resolve once per pass and invalidate next pass'


@pytest.mark.parametrize('protocol,route,set_name', [
    ('shadowsocks', 'shadowsocks', 'unblocksh'), ('vmess', 'vmess', 'unblockvmess'),
    ('vless', 'vless', 'unblockvless'), ('vless2', 'vless-2', 'unblockvless2'),
    ('trojan', 'trojan', 'unblocktroj'), ('hysteria2', 'hysteria2', 'unblockhy2'),
])
def test_runtime_cleanup_preserves_each_assigned_protocol(tmp_path, protocol, route, set_name):
    (tmp_path / (route + '.txt')).write_text('\n'.join(service_route_entries('youtube')), encoding='utf-8')
    loser = 'unblockvless' if set_name != 'unblockvless' else 'unblockvless2'
    snapshot = {set_name: {'64.233.161.0/24'}, loser: {'64.233.161.97'}}
    deleted = []
    result = service_routes.cleanup_runtime_service_route_intersections(unblock_dir=str(tmp_path), run_command=runner(snapshot, deleted))
    assert deleted == [(loser, '64.233.161.97')]
    assert snapshot[set_name] == {'64.233.161.0/24'}
    assert result['applied'][0]['target_protocol'] == protocol


def test_cleanup_rereads_members_before_each_deletion_pair(tmp_path):
    (tmp_path / 'vless-2.txt').write_text('\n'.join(service_route_entries('youtube')), encoding='utf-8')
    snapshot = {'unblockvless2': {'64.233.161.0/24'},
                'unblockvless': {'64.233.161.97'}, 'unblockvmess': {'64.233.161.98'}}
    deleted = []
    command = runner(snapshot, deleted)
    reads = []
    def changing(args, **kwargs):
        if args == ['ipset', 'save']:
            reads.append(1)
        result = command(args, **kwargs)
        if args[:2] == ['ipset', 'del']:
            # A concurrent producer removes the winner after the first pair.
            snapshot['unblockvless2'].clear()
        return result
    issues = [{'kind': 'runtime_ipset_overlap', 'service_keys': ['youtube'],
               'set_names': [loser, 'unblockvless2']} for loser in ('unblockvless', 'unblockvmess')]
    result = service_routes.cleanup_runtime_service_route_intersections(report={'issues': issues},
                    unblock_dir=str(tmp_path), run_command=changing)
    assert len(reads) == 2
    assert deleted == [('unblockvless', '64.233.161.97')]
    assert snapshot['unblockvmess'] == {'64.233.161.98'}
    assert result['deleted_members'] == 1
