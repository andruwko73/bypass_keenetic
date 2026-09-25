#!/usr/bin/env python3
"""Linux-only whole bootstrap acceptance in a disposable chroot + namespaces.

Real bootstrap/script/modules/files/wizard. Hardware commands, package manager
and network probes are fixtures. This does NOT qualify native Keenetic/UBIFS.
Requires root, unshare, mount, a static BusyBox and installed Python test deps.
Never run the installer outside the isolated child filesystem/network/PID tree.
"""
import argparse
import base64
import hashlib
import http.cookiejar
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.parse


def run(*args, **kw):
    return subprocess.run(args, check=True, **kw)


def write(root, name, body, executable=True):
    path = root / name.lstrip('/')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8', newline='\n')
    path.chmod(0o755 if executable else 0o600)


def bind(source, target):
    target.mkdir(parents=True, exist_ok=True)
    run('mount', '--bind', str(source), str(target))
    run('mount', '-o', 'remount,bind,ro', str(target))


def child(args):
    assert os.geteuid() == 0
    assert os.readlink('/proc/self/ns/mnt') != args.parent_namespace
    run('mount', '--make-rprivate', '/')
    root = Path(tempfile.mkdtemp(prefix='bypass-install-sandbox-'))
    # tmpfs mount disappears with this private namespace and never changes /opt.
    run('mount', '-t', 'tmpfs', '-o', 'size=512m', 'tmpfs', str(root))
    for name in ('bin', 'etc', 'tmp', 'dev', 'proc', 'opt/bin', 'opt/sbin', 'opt/root',
                 'opt/etc/init.d', 'opt/etc/ndm/fs.d', 'opt/etc/ndm/netfilter.d'):
        (root / name).mkdir(parents=True, exist_ok=True)
    bind('/usr', root / 'usr')
    for name in ('lib', 'lib64', 'sbin'):
        (root / name).symlink_to('/usr/' + name)
    bind(args.dependencies, root / 'deps')
    shutil.copyfile(args.busybox, root / 'bin/busybox')
    (root / 'bin/busybox').chmod(0o755)
    for applet in subprocess.check_output([args.busybox, '--list'], text=True).splitlines():
        target = root / 'bin' / applet
        if not target.exists():
            target.symlink_to('/bin/busybox')
    if args.shell == 'bash':
        (root / 'bin/sh').unlink()
        (root / 'bin/sh').symlink_to('/usr/bin/bash')
    for name, minor in (('null', 3), ('zero', 5), ('random', 8), ('urandom', 9)):
        os.mknod(root / 'dev' / name, 0o20666, os.makedev(1, minor))
    run('mount', '-t', 'proc', 'proc', str(root / 'proc'))
    ip = shutil.which('ip')
    if ip:
        run(ip, 'link', 'set', 'lo', 'up')
        run(ip, 'link', 'add', 'br0', 'type', 'dummy')
        run(ip, 'address', 'add', '192.168.1.1/24', 'dev', 'br0')
        run(ip, 'link', 'set', 'br0', 'up')
    repo = Path(args.repo)
    inventory = Path(args.inventory).read_bytes() if args.inventory else subprocess.check_output(['git', '-C', str(repo), 'ls-files', '-z'])
    names = inventory.decode().split('\0')
    for name in names:
        if name in ('script.sh', 'version.md', 'README.md') or name == 'bootstrap/install.sh' or name.startswith('app/'):
            source, target = repo / name, root / 'kit' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            if data.startswith(b'#!/bin/sh'):
                data = data.replace(b'\r\n', b'\n')
            target.write_bytes(data)
            target.chmod(0o755 if data.startswith(b'#!') else 0o644)
    write(root, '/etc/passwd', 'root:x:0:0:root:/opt/root:/bin/sh\n', False)
    write(root, '/etc/group', 'root:x:0:\n', False)
    write(root, '/etc/hosts', '127.0.0.1 localhost\n', False)
    write(root, '/etc/resolv.conf', 'nameserver 127.0.0.1\n', False)
    (root / 'opt/bin/python3').symlink_to('/usr/bin/python3')
    write(root, '/opt/bin/curl', '''#!/bin/sh
case "$*" in
  *localhost:79*) printf '"5.1.5"'; exit 0;;
  *file://*) exec /usr/bin/curl "$@";;
  *) echo unexpected-network >> /tmp/network-attempts; exit 7;;
esac
''')
    fixtures = {
        'ip': "printf 'inet 192.168.1.1/24 scope global br0\\n'",
        'dig': "printf '192.0.2.1\\n'", 'nslookup': "printf 'Address 1: 192.0.2.1\\n'",
        'ndmc': "printf 'model: KN-1012\\nrelease: 5.1.5\\n'",
        'ipset': 'exit 0',
        'iptables': 'case " $* " in *" -C "*|*" -D "*) exit 1;; esac; exit 0',
        'ip6tables': 'case " $* " in *" -C "*|*" -D "*) exit 1;; esac; exit 0',
        'iptables-save': 'exit 0', 'ip6tables-save': 'exit 0',
        'opkg': 'exit 0', 'xray': 'exit 0', 'ss-redir': 'exit 0', 'dnsmasq': 'exit 0',
        'netstat': 'exit 0', 'logger': 'exit 0',
    }
    for name, body in fixtures.items():
        write(root, '/opt/bin/' + name, '#!/bin/sh\n' + body + '\n')
    for name in ('S10cron', 'S22shadowsocks', 'S22trojan', 'S24xray', 'S56dnsmasq'):
        write(root, '/opt/etc/init.d/' + name, '#!/bin/sh\nexit 0\n')
    write(root, '/opt/etc/crontab', '# unrelated scheduler entry\n', False)
    write(root, '/opt/etc/foreign-application', 'preserve exactly\n', False)
    if args.scenario == 'existing':
        write(root, '/opt/etc/bot/bot_config.py', "token='fixture'\nusernames=['owner']\n", False)
    if args.scenario == 'missing-asset':
        (root / 'kit/app/static/app.css').unlink()
    os.chroot(root)
    os.chdir('/')
    os.environ.update(PATH='/opt/bin:/opt/sbin:/bin:/usr/bin:/usr/sbin', PYTHONPATH='/deps',
                      BYPASS_INSTALL_REPO='/kit', BYPASS_DEPENDENCIES_READY='1',
                      BYPASS_ROUTER_IP='192.168.1.1', PYTHONDONTWRITEBYTECODE='1')
    with open('/tmp/install.log', 'w') as output:
        result = subprocess.run(['/bin/sh', '/kit/bootstrap/install.sh'], stdout=output, stderr=subprocess.STDOUT, timeout=180)
    expected = 3 if args.scenario == 'existing' else 1 if args.scenario == 'missing-asset' else 0
    if result.returncode != expected:
        print(Path('/tmp/install.log').read_text()[-6000:])
        if Path('/opt/etc/bot/installer.log').exists():
            print(Path('/opt/etc/bot/installer.log').read_text()[-2000:])
        raise AssertionError(f'bootstrap exit {result.returncode}, expected {expected}')
    assert Path('/opt/etc/foreign-application').read_text() == 'preserve exactly\n'
    assert Path('/opt/etc/crontab').read_text().startswith('# unrelated scheduler entry\n')
    assert not Path('/tmp/network-attempts').exists()
    if args.scenario == 'existing':
        assert not Path('/opt/etc/bot/main.py').exists()
    elif args.scenario == 'fresh':
        actual = Path('/opt/etc/bot/static')
        for file in Path('/kit/app/static').rglob('*'):
            if file.is_file() and file.suffix in ('.js', '.css', '.png', '.svg'):
                target = actual / file.relative_to('/kit/app/static')
                assert target.is_file(), str(target)
                assert target.read_bytes() == file.read_bytes(), str(target)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with opener.open('http://192.168.1.1:8080/', timeout=5) as response:
            html = response.read().decode()
        assert 'Сохранить и запустить' in html
        assert 'app_runtime_mode' in html and 'csrf_token' in html
        # Actual service restart is idempotent; no mock wizard process.
        run('/opt/etc/init.d/S98telegram_bot_installer', 'start', stdout=subprocess.DEVNULL)
        processes = [p for p in Path('/proc').glob('[0-9]*/cmdline')
                     if b'python3\0/opt/etc/bot/installer.py' in p.read_bytes()]
        assert len(processes) == 1
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        form = dict(csrf_token=csrf, app_runtime_mode=args.mode, token='123:' + 'A' * 35,
                    username='fixture_owner', routerip='192.168.1.1', browser_port='8080',
                    web_auth_user='fixture', web_auth_token='fixture-password', default_proxy_mode='none')
        response = opener.open('http://192.168.1.1:8080/save', urllib.parse.urlencode(form).encode(), timeout=5)
        assert response.status == 200
        response.close()
        headers = {'Authorization': 'Basic ' + base64.b64encode(b'fixture:fixture-password').decode()}
        ready = False
        for _ in range(45):
            try:
                request = urllib.request.Request('http://192.168.1.1:8080/api/status?lite=1', headers=headers)
                with opener.open(request, timeout=2) as response:
                    status = json.load(response)
                if 'pool_probe_running' in status:
                    ready = True
                    break
            except (OSError, ValueError):
                pass
            time.sleep(1)
        if not ready and Path('/opt/etc/bot/error.log').exists():
            print(Path('/opt/etc/bot/error.log').read_text()[-2000:])
        assert ready, 'main application did not take over the web port'
        assert Path('/opt/etc/bot_app_mode').read_text().strip() == args.mode
        with opener.open(urllib.request.Request('http://192.168.1.1:8080/static/app.js', headers=headers), timeout=5) as response:
            assert b'setupBackgroundControls' in response.read()
        run('/opt/etc/init.d/S99telegram_bot', 'stop', stdout=subprocess.DEVNULL)
    print(json.dumps({'scenario': args.scenario, 'shell': args.shell, 'passed': True,
                      'mode': args.mode, 'hardware': 'stubbed', 'network': 'isolated'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--busybox', required=True)
    parser.add_argument('--dependencies', required=True)
    parser.add_argument('--inventory', help='git ls-files -z from a Windows worktree when testing in WSL')
    parser.add_argument('--shell', choices=('ash', 'bash'), default='ash')
    parser.add_argument('--scenario', choices=('fresh', 'existing', 'missing-asset'), default='fresh')
    parser.add_argument('--mode', choices=('simple', 'advanced', 'web_only'), default='web_only')
    parser.add_argument('--parent-namespace')
    args = parser.parse_args()
    if args.parent_namespace:
        child(args)
    else:
        run('unshare', '--mount', '--net', '--pid', '--fork', sys.executable, __file__,
            *sys.argv[1:], '--parent-namespace', os.readlink('/proc/self/ns/mnt'))
