import html
import ipaddress
import os
import re
import shutil
import subprocess
from urllib.parse import parse_qs


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


def is_local_web_client(address):
    try:
        ip_obj = ipaddress.ip_address((address or '').strip())
    except ValueError:
        return False
    return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local


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
    return (value or '').replace('\\', '\\\\').replace("'", "\\'")


def browser_port_is_valid(value):
    port = (value or '').strip()
    return not port or bool(re.fullmatch(r'\d{2,5}', port))


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
        ' Пароль веб-интерфейса не задан; вход будет без пароля.'
    )
    return web_auth_user, note


def validate_installer_form(form, required_fields):
    missing = [key for key in required_fields if not form_value(form, key)]
    if missing:
        return False, 'Не заполнены обязательные поля: ' + ', '.join(missing)

    if not browser_port_is_valid(form_value(form, 'browser_port')):
        return False, 'Поле browser_port должно содержать номер порта.'

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
    os.makedirs(bot_dir, exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as file:
        file.write(config_text)
    os.chmod(config_path, 0o600)
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
