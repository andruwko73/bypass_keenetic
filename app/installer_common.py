import html
import base64
import hmac
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import time
from urllib.parse import parse_qs

SETUP_STATE_DIR = '/opt/var/lib/bypass-setup'


def self_service_setup_active(state_dir=None):
    return os.path.lexists(state_dir or SETUP_STATE_DIR)


def installer_pairing_authorized(authorization, state_dir=None):
    """Pair only with the code obtained through the native admin interface."""
    state_dir = state_dir or SETUP_STATE_DIR
    if not self_service_setup_active(state_dir):
        return True
    code_path = os.path.join(state_dir, 'pairing.code')
    try:
        if os.path.islink(state_dir) or os.path.islink(code_path):
            return False
        with open(code_path, encoding='ascii') as stream:
            code = stream.read(128).strip()
        if not re.fullmatch(r'[a-f0-9]{32}', code):
            return False
        scheme, data = authorization.split(' ', 1)
        if scheme.lower() != 'basic' or len(data) > 512:
            return False
        supplied = base64.b64decode(data, validate=True).decode('ascii')
        return hmac.compare_digest(supplied, 'setup:' + code)
    except (OSError, ValueError, UnicodeError):
        return False


def installer_setup_status(state_dir=None):
    state_dir = state_dir or SETUP_STATE_DIR
    try:
        path = os.path.join(state_dir, 'state.tsv')
        if os.path.islink(state_dir) or os.path.islink(path):
            return {}
        with open(path, encoding='ascii') as stream:
            rows = dict(line.split('\t', 1) for line in stream.read(4096).strip().splitlines())
        phase = rows.get('phase')
        if phase not in ('preflight', 'download', 'verify', 'entware', 'dependencies', 'application', 'configure', 'ready', 'failed'):
            return {}
        return {'phase': phase, 'commit': rows.get('commit', '') if re.fullmatch(r'[a-f0-9]{40}', rows.get('commit', '')) else ''}
    except (OSError, ValueError, UnicodeError):
        return {}


def set_initial_entware_password(password, state_dir=None):
    state_dir = state_dir or SETUP_STATE_DIR
    if not os.path.isfile(os.path.join(state_dir, 'entware.secured')):
        return
    if len(password) < 12 or '\n' in password or '\r' in password or '\x00' in password:
        raise ValueError('Задайте пароль Entware длиной от 12 символов.')
    # Password goes to stdin, never argv, logs, URLs or a persistent form file.
    result = subprocess.run(['/opt/bin/passwd', 'root'], input=password + '\n' + password + '\n',
                            text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    if result.returncode:
        raise ValueError('Не удалось задать пароль Entware. Повторите сохранение.')


def cleanup_self_service_setup(state_dir=SETUP_STATE_DIR, work_dir='/tmp/bypass-self-service',
                               starter_dir='/opt/share/bypass-setup', init_dir='/opt/etc/init.d',
                               pairing_export='/opt/bypass-setup-code.txt'):
    """Remove only a receipt-matched installer's files, after verified handover."""
    def regular(path):
        return os.path.isfile(path) and not os.path.islink(path)

    def read(path):
        with open(path, 'rb') as stream:
            return stream.read()

    try:
        for directory in (state_dir, work_dir, starter_dir, init_dir):
            if os.path.realpath(directory) != os.path.abspath(directory):
                return False
        receipt_path = os.path.join(state_dir, 'receipt.sha256')
        if not regular(receipt_path):
            return False
        receipt = read(receipt_path).strip()
        if not re.fullmatch(b'[a-f0-9]{64}', receipt):
            return False
        snapshot = installer_setup_status(state_dir)
        if snapshot.get('phase') not in ('configure', 'ready') or not snapshot.get('commit'):
            return False
        temporary = os.path.join(state_dir, 'state.new')
        if os.path.lexists(temporary):
            return False
        if os.path.isdir(work_dir) and (not regular(os.path.join(work_dir, 'owner')) or read(os.path.join(work_dir, 'owner')).strip() != receipt):
            return False
        if os.path.isdir(starter_dir):
            manifest = os.path.join(starter_dir, 'manifest.tsv')
            if not regular(manifest) or hashlib.sha256(read(manifest)).hexdigest().encode() != receipt:
                return False
            for name in ('S01bypass_setup',):
                installed, original = os.path.join(init_dir, name), os.path.join(starter_dir, 'wizard')
                if os.path.lexists(installed) and (not regular(installed) or not regular(original) or read(installed) != read(original)):
                    return False
        code_path = os.path.join(state_dir, 'pairing.code')
        if os.path.lexists(pairing_export):
            if not regular(pairing_export) or not regular(code_path) or read(pairing_export) != read(code_path):
                return False
        # Finish all ownership checks before the first deletion. Keep a ready
        # state checkpoint so a partially interrupted cleanup is retryable.
        for name in ('pairing.code', 'entware.started', 'entware.secured', 'dependencies.started', 'dependencies.done', 'application.started', 'error.tsv'):
            path = os.path.join(state_dir, name)
            if os.path.lexists(path) and not regular(path):
                return False
        with open(temporary, 'x', encoding='ascii') as stream:
            stream.write(f"phase\tready\ncommit\t{snapshot['commit']}\nupdated\t{int(time.time())}\n")
        os.replace(temporary, os.path.join(state_dir, 'state.tsv'))
        if os.path.lexists(pairing_export):
            os.remove(pairing_export)
        if os.path.isdir(starter_dir):
            for name in ('S01bypass_setup',):
                installed = os.path.join(init_dir, name)
                if regular(installed):
                    os.remove(installed)
            shutil.rmtree(starter_dir)
        if os.path.isdir(work_dir):
            shutil.rmtree(work_dir)
        for name in ('pairing.code', 'entware.started', 'entware.secured', 'dependencies.started', 'dependencies.done', 'application.started', 'error.tsv'):
            path = os.path.join(state_dir, name)
            if regular(path):
                os.remove(path)
        return True
    except (OSError, ValueError):
        return False


def finalize_self_service_setup(config_path='/opt/etc/bot/bot_config.py', attempts=30):
    """One bounded handover check, not a permanent monitoring process."""
    import ast
    import http.client
    try:
        with open(config_path, encoding='utf-8') as stream:
            tree = ast.parse(stream.read())
        settings = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id in ('routerip', 'browser_port', 'web_auth_user', 'web_auth_token', 'app_runtime_mode'):
                    settings[node.targets[0].id] = ast.literal_eval(node.value)
        host = settings.get('routerip') or detect_router_ip()
        if not ipaddress.ip_address(host).is_private:
            return False
        port = int(settings.get('browser_port', 8080))
        credentials = str(settings.get('web_auth_user') or 'admin') + ':' + str(settings.get('web_auth_token') or '')
        headers = {'Authorization': 'Basic ' + base64.b64encode(credentials.encode()).decode()}
        with open(os.path.join(os.path.dirname(config_path), 'static', 'app.js'), 'rb') as stream:
            expected_asset = hashlib.sha256(stream.read()).digest()
        for attempt in range(attempts):
            try:
                result = subprocess.run(['/opt/etc/init.d/S99telegram_bot', 'status'], timeout=5,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                connection = http.client.HTTPConnection(host, port, timeout=2)
                try:
                    connection.request('GET', '/static/app.js', headers=headers)
                    response = connection.getresponse()
                    asset = response.read(2 * 1024 * 1024)
                    if result.returncode == 0 and response.status == 200 and hashlib.sha256(asset).digest() == expected_asset:
                        connection.close()
                        connection = http.client.HTTPConnection(host, port, timeout=2)
                        connection.request('GET', '/api/status?lite=1', headers=headers)
                        response = connection.getresponse()
                        payload = json.loads(response.read(256 * 1024)) if response.status == 200 else {}
                        if isinstance(payload, dict) and 'pool_probe_running' in payload and (
                            (payload.get('bot_ready') is True and payload.get('bot_polling') is True)
                            or settings.get('app_runtime_mode') == 'web_only'
                        ):
                            return cleanup_self_service_setup()
                finally:
                    connection.close()
            except (OSError, ValueError, subprocess.SubprocessError, http.client.HTTPException):
                pass
            time.sleep(2)
    except (OSError, ValueError, SyntaxError):
        pass
    return False

def detect_router_ip():
    try:
        output = subprocess.check_output(
            ['sh', '-c', "ip -4 addr show br0 | grep -Eo '([0-9]{1,3}\\.){3}[0-9]{1,3}' | head -n1"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if output:
            return output
    except Exception:
        pass
    return '192.168.1.1'


def resolve_bind_host():
    candidate = detect_router_ip().strip()
    if not candidate:
        return ''
    try:
        ip_obj = ipaddress.ip_address(candidate)
    except ValueError:
        return ''
    if ip_obj.is_unspecified:
        return ''
    return candidate


def ensure_legacy_path(source_path, legacy_path):
    try:
        if os.path.islink(legacy_path) or os.path.exists(legacy_path):
            os.remove(legacy_path)
    except Exception:
        pass

    try:
        os.symlink(source_path, legacy_path)
        return
    except Exception:
        pass

    shutil.copyfile(source_path, legacy_path)


def escape_python(value):
    return (value or '').replace('\\', '\\\\').replace("'", "\\'").replace('\r', '\\r').replace('\n', '\\n')


def browser_port_is_valid(value):
    port = (value or '').strip()
    if not port:
        return True
    if not re.fullmatch(r'\d{1,5}', port):
        return False
    try:
        port_number = int(port)
    except ValueError:
        return False
    return 1 <= port_number <= 65535


def form_value(form, key, default=''):
    return (form.get(key, default) or '').strip()


def normalize_web_auth_form(form, default_user='admin'):
    form['web_auth_user'] = form_value(form, 'web_auth_user', default_user) or default_user
    form['web_auth_token'] = form_value(form, 'web_auth_token')
    return form


def web_auth_summary(form, default_user='admin'):
    web_auth_user = form_value(form, 'web_auth_user', default_user) or default_user
    web_auth_token = form_value(form, 'web_auth_token')
    note = (
        ' Пароль веб-интерфейса задан.'
        if web_auth_token else
        ' Пароль веб-интерфейса не задан; без пароля доступен только локальный адрес.'
    )
    return web_auth_user, note


def validate_installer_form(form, required_fields):
    missing = [key for key in required_fields if not form_value(form, key)]
    if missing:
        return False, 'Не заполнены обязательные поля: ' + ', '.join(missing)

    if not browser_port_is_valid(form_value(form, 'browser_port')):
        return False, 'Поле browser_port должно содержать номер порта 1-65535.'

    return True, ''


def parse_urlencoded_request(handler, max_bytes=1024 * 1024):
    try:
        content_length = int(handler.headers.get('Content-Length', '0') or '0')
    except (TypeError, ValueError):
        content_length = 0
    if content_length < 0:
        content_length = 0
    if content_length > max_bytes:
        raise ValueError('POST body is too large.')
    raw_body = handler.rfile.read(content_length).decode('utf-8', errors='ignore')
    return {key: values[0] for key, values in parse_qs(raw_body, keep_blank_values=True).items()}


def write_installer_config(bot_dir, config_path, config_text, legacy_config_path, bot_main_path=None, legacy_main_path=None):
    import ast
    import tempfile
    ast.parse(config_text)
    os.makedirs(bot_dir, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.installer-config-', dir=bot_dir)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
            file.write(config_text)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, config_path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    ensure_legacy_path(config_path, legacy_config_path)
    if bot_main_path and legacy_main_path and os.path.exists(bot_main_path):
        ensure_legacy_path(bot_main_path, legacy_main_path)


def start_detached_shell(command):
    subprocess.Popen(
        ['sh', '-c', command],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def installer_target_url(form, default_browser_port):
    router_ip = form_value(form, 'routerip', detect_router_ip()) or detect_router_ip()
    browser_port = form_value(form, 'browser_port', str(default_browser_port)) or str(default_browser_port)
    return f'http://{router_ip}:{browser_port}/'


def installer_page_parts(message='', redirect_url=None, redirect_delay_seconds=3):
    notice = ''
    redirect_head = ''
    redirect_script = ''
    if message:
        notice = f'<div class="notice">{html.escape(message)}</div>'
    if redirect_url:
        escaped_redirect_url = html.escape(redirect_url, quote=True)
        redirect_head = f'<meta http-equiv="refresh" content="{redirect_delay_seconds};url={escaped_redirect_url}">'
        redirect_script = f"""
    <script>
        setTimeout(function () {{
            window.location.replace({redirect_url!r});
        }}, {redirect_delay_seconds * 1000});
    </script>"""
    return notice, redirect_head, redirect_script


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['--finalize-self-service']:
        import fcntl
        descriptor = os.open('/tmp/bypass-self-service-finalize.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'w') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit(0)
            raise SystemExit(0 if finalize_self_service_setup() else 1)
