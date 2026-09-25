"""DNS policy parity, cache invalidation and failure-safe publication."""
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
dns = importlib.import_module('dns_route_generator')
LEGACY = ROOT / 'tests/fixtures/unblock_dnsmasq_1_1067.sh'
POLICY = 'DOMAIN-SUFFIX,media.example # comment\nexample.com\n'
MIXED = ''' # comment
DOMAIN-SUFFIX,Example.COM
DOMAIN,DOMAIN,Prefix.Example
HOST-SUFFIX,+.Mixed.Example
*.EXAMPLE.COM
 /slash.example/
a.media.example
a.mediaXexample
plain.example # comment
trailing.example,
youtube.com
sub.googlevideo.com
clients3.google.com
WWW.GSTATIC.COM
203.0.113.8
198.51.100.0/24
duplicate.example
duplicate.example
last.example'''


def routes(text=''):
    return {name: text for _, name in dns.ROUTE_FILES}


def legacy(folder, inputs, owner):
    shell = r'C:\Program Files\Git\bin\bash.exe' if os.name == 'nt' else shutil.which('bash')
    if not shell or not Path(shell).is_file():
        pytest.skip('Legacy differential oracle requires Bash')
    folder.mkdir()
    for filename, value in inputs.items():
        (folder / filename).write_text(value, encoding='utf-8', newline='')
    for filename in ('udp', 'calls'):
        (folder / filename).write_text(POLICY, encoding='utf-8')
    source = LEGACY.read_text(encoding='utf-8')
    source = source.replace('YOUTUBE_ROUTE_PROTOCOL="$(youtube_route_protocol)"', 'YOUTUBE_ROUTE_PROTOCOL="' + owner + '"')
    source = source.replace('UDP_QUIC_POLICY_SOURCE="$(udp_quic_policy_source || true)"', 'UDP_QUIC_POLICY_SOURCE=./udp')
    source = source.replace('CALL_SIGNAL_POLICY_SOURCE="$(call_signal_policy_source || true)"', 'CALL_SIGNAL_POLICY_SOURCE=./calls')
    (folder / 'legacy.sh').write_text(source, encoding='utf-8', newline='\n')
    p = subprocess.run([shell, 'legacy.sh'], cwd=folder, capture_output=True, timeout=180,
                       env={**os.environ, 'UNBLOCK_DIR': '.', 'DNSMASQ_OUTPUT_FILE': './out',
                            'DNSMASQ_LOG_FILE': './log', 'LC_ALL': 'C'})
    assert p.returncode == 0, p.stderr.decode(errors='replace')
    return (folder / 'out').read_bytes()


@pytest.mark.parametrize('owner', [p for p, _ in dns.ROUTE_FILES] + [''])
@pytest.mark.skipif(os.name == 'nt', reason='Legacy fork-heavy matrix runs on Linux CI and Entware')
def test_immutable_legacy_parity(tmp_path, owner):
    inputs = routes('simple.example\n')
    inputs[dict(dns.ROUTE_FILES).get(owner, 'vless.txt')] = MIXED.replace('\n', '\r\n')
    assert dns.render(inputs, owner=owner, udp_policy=POLICY, call_policy=POLICY) == legacy(tmp_path / 'old', inputs, owner)


def test_ipv6_is_never_emitted_as_a_dns_name():
    result = dns.render(routes('2001:db8::1\n2001:db8::/64\nexample.org'), owner='')
    assert b'2001:db8' not in result
    assert b'example.org' in result


@pytest.fixture
def environment(tmp_path):
    for name, text in routes('example.org\n').items():
        (tmp_path / name).write_text(text)
    (tmp_path / 'udp').write_text(POLICY)
    (tmp_path / 'calls').write_text(POLICY)
    return {'UNBLOCK_DIR': str(tmp_path), 'BOT_DIR': str(ROOT / 'app'),
            'DNSMASQ_OUTPUT_FILE': str(tmp_path / 'out'), 'DNSMASQ_CACHE_FILE': str(tmp_path / 'cache.json'),
            'DNSMASQ_LOG_FILE': str(tmp_path / 'log'), 'YOUTUBE_ROUTE_OWNER_STATE_FILE': str(tmp_path / 'owner.json'),
            'UDP_QUIC_POLICY_FILE': str(tmp_path / 'udp'), 'CALL_SIGNAL_POLICY_FILE': str(tmp_path / 'calls')}


def test_cache_no_write_and_invalidation_by_content(environment, monkeypatch):
    assert dns.generate(environment)['changed']
    output = Path(environment['DNSMASQ_OUTPUT_FILE'])
    stamp = output.stat().st_mtime_ns
    real_render = dns.render
    monkeypatch.setattr(dns, 'render', lambda **_: pytest.fail('render on cache hit'))
    assert dns.generate(environment)['cached']
    assert output.stat().st_mtime_ns == stamp
    monkeypatch.setattr(dns, 'render', real_render)
    source = Path(environment['UNBLOCK_DIR']) / 'vless.txt'
    original = source.stat()
    source.write_text('another.org\n')
    os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))
    assert dns.generate(environment)['changed']
    output.write_text('stale')
    assert dns.generate(environment)['changed']


@pytest.mark.parametrize('changed', ['udp', 'calls', 'priority', 'owner', 'module'])
def test_policy_owner_and_generator_invalidate_cache(environment, monkeypatch, changed):
    dns.generate(environment)
    root = Path(environment['UNBLOCK_DIR'])
    if changed in ('udp', 'calls'):
        (root / changed).write_text('example.org\n')
    elif changed == 'priority':
        environment['YOUTUBE_ROUTE_PRIORITY_DOMAINS'] = 'example.org'
    elif changed == 'owner':
        (root / 'owner.json').write_text('{"protocol":"hysteria2"}')
    else:
        replacement = root / 'changed.py'; replacement.write_text('# version changed')
        monkeypatch.setattr(dns, '__file__', str(replacement))
    assert not dns.generate(environment)['cached']


def test_comment_only_change_does_not_replace_output(environment):
    dns.generate(environment)
    root = Path(environment['UNBLOCK_DIR'])
    stamp = (root / 'out').stat().st_mtime_ns
    with (root / 'vless.txt').open('a') as f:
        f.write('# no rule change\n')
    result = dns.generate(environment)
    assert not result['changed'] and not result['cached']
    assert (root / 'out').stat().st_mtime_ns == stamp


def fake_runtime(monkeypatch):
    restarts = []
    monkeypatch.setattr(dns, 'validate', lambda path: None)
    monkeypatch.setattr(dns, 'apply_identity', lambda h: {'output': h, 'daemon': ['one']})
    monkeypatch.setattr(dns, 'dns_healthy', lambda: True)
    monkeypatch.setattr(dns, 'restart', lambda: restarts.append(True))
    return restarts


def test_reload_only_when_needed_and_recover_stopped_daemon(environment, monkeypatch):
    restarts = fake_runtime(monkeypatch)
    assert dns.generate(environment, refresh=True)['restarted']
    assert not dns.generate(environment, refresh=True)['restarted']
    monkeypatch.setattr(dns, 'apply_identity', lambda h: {'output': h, 'daemon': ['new']})
    assert dns.generate(environment, refresh=True)['restarted']
    monkeypatch.setattr(dns, 'dns_healthy', lambda: False)
    assert dns.generate(environment, refresh=True)['restarted']
    assert len(restarts) == 3


@pytest.mark.parametrize('failure', ['validation', 'replace', 'restart', 'interrupt', 'missing', 'changed_inputs'])
def test_failure_retains_previous_rules(environment, monkeypatch, failure):
    fake_runtime(monkeypatch)
    dns.generate(environment, refresh=True)
    root = Path(environment['UNBLOCK_DIR'])
    old = (root / 'out').read_bytes()
    (root / 'vless.txt').write_text('new.example\n')
    def fail(*args):
        raise RuntimeError('injected failure')
    if failure == 'validation':
        monkeypatch.setattr(dns, 'validate', fail)
    elif failure == 'replace':
        monkeypatch.setattr(dns.os, 'replace', fail)
    elif failure in ('restart', 'interrupt'):
        count = []
        def once():
            if not count:
                count.append(1)
                if failure == 'interrupt':
                    raise KeyboardInterrupt
                fail()
        monkeypatch.setattr(dns, 'restart', once)
    elif failure == 'missing':
        (root / 'vmess.txt').unlink()
    else:
        real_render = dns.render
        def race(**kwargs):
            (root / 'vless.txt').write_text('raced.example\n')
            return real_render(**kwargs)
        monkeypatch.setattr(dns, 'render', race)
    with pytest.raises((RuntimeError, FileNotFoundError, KeyboardInterrupt)):
        dns.generate(environment, refresh=True)
    assert (root / 'out').read_bytes() == old
    assert not list(root.glob('out.tmp.*')) and not list(root.glob('out.check.*'))


def test_a_b_a_and_cache_loss_reapply(environment, monkeypatch):
    fake_runtime(monkeypatch)
    dns.generate(environment, refresh=True)
    root = Path(environment['UNBLOCK_DIR']); a = (root / 'out').read_bytes()
    (root / 'vless.txt').write_text('b.example\n')
    assert dns.generate(environment, refresh=True)['restarted']
    (root / 'vless.txt').write_text('example.org\n')
    assert dns.generate(environment, refresh=True)['restarted']
    assert (root / 'out').read_bytes() == a
    (root / 'cache.json').unlink()
    assert dns.generate(environment, refresh=True)['restarted']


def test_concurrent_processes_share_generation_lock(environment):
    command = [sys.executable, '-B', str(ROOT / 'app/dns_route_generator.py'), '--json']
    children = [subprocess.Popen(command, env={**os.environ, **environment}, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(4)]
    results = []
    try:
        for child in children:
            out, err = child.communicate(timeout=30)
            assert child.returncode == 0, err
            results.append(json.loads(out))
    finally:
        for child in children:
            if child.poll() is None:
                child.kill(); child.wait()
    assert sum(r['changed'] for r in results) == 1
    assert sum(r['cached'] for r in results) == 3


def test_large_input_and_safe_literal_handling():
    value = ''.join(f'host{i}.example\n' for i in range(10000))
    inputs = routes(); inputs['vless.txt'] = value
    result = dns.render(inputs, owner='')
    assert len(result.splitlines()) == 10000
    assert b'ipset=/host9999.example/unblockvless\n' in result


def test_corrupt_cache_and_output_metadata(environment):
    root = Path(environment['UNBLOCK_DIR'])
    (root / 'out').write_text('old')
    (root / 'out').chmod(0o640)
    mode = (root / 'out').stat().st_mode
    (root / 'cache.json').write_text('[]')
    assert dns.generate(environment)['changed']
    assert (root / 'out').stat().st_mode == mode


@pytest.mark.skipif(os.name == 'nt', reason='POSIX symlink creation')
def test_output_symlink_is_not_followed(environment):
    root = Path(environment['UNBLOCK_DIR'])
    (root / 'protected').write_text('keep')
    (root / 'out').symlink_to(root / 'protected')
    with pytest.raises(ValueError):
        dns.generate(environment)
    assert (root / 'protected').read_text() == 'keep'


def test_invalid_route_does_not_replace_output(environment):
    dns.generate(environment)
    root = Path(environment['UNBLOCK_DIR']); old = (root / 'out').read_bytes()
    (root / 'vless.txt').write_bytes(b'bad\x00domain.example\n')
    with pytest.raises(ValueError):
        dns.generate(environment)
    assert (root / 'out').read_bytes() == old
