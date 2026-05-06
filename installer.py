#!/usr/bin/python3
import html
import ipaddress
import json
import os
import re
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import key_pool_store


BOT_DIR = '/opt/etc/bot'
KEY_POOLS_PATH = os.path.join(BOT_DIR, 'key_pools.json')
BOT_CONFIG_PATH = os.path.join(BOT_DIR, 'bot_config.py')
LEGACY_CONFIG_PATH = '/opt/etc/bot_config.py'
BOT_MAIN_PATH = os.path.join(BOT_DIR, 'main.py')
LEGACY_MAIN_PATH = '/opt/etc/bot.py'
BOT_SERVICE_PATH = '/opt/etc/init.d/S99telegram_bot'
INSTALLER_SERVICE_PATH = '/opt/etc/init.d/S98telegram_bot_installer'
DEFAULT_BROWSER_PORT = int(os.environ.get('BYPASS_INSTALLER_PORT', '8080'))
DEFAULT_FORK_REPO_OWNER = 'andruwko73'
DEFAULT_FORK_REPO_NAME = 'bypass_keenetic'
WEB_ONLY_BRANCH = 'codex/web-only-v1'
WEB_ONLY_SCRIPT_URL = (
    f'https://raw.githubusercontent.com/{DEFAULT_FORK_REPO_OWNER}/'
    f'{DEFAULT_FORK_REPO_NAME}/{WEB_ONLY_BRANCH}/script.sh'
)


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
    return value.replace('\\', '\\\\').replace("'", "\\'")


def get_keys_for_proto(proto):
    pools = key_pool_store.load_key_pools(KEY_POOLS_PATH)
    return pools.get(proto, [])


def add_key_to_pool(proto, key):
    pools = key_pool_store.load_key_pools(KEY_POOLS_PATH)
    pools, added = key_pool_store.add_keys_to_pool(pools, proto, key)
    key_pool_store.save_key_pools(KEY_POOLS_PATH, pools)
    return bool(added)


def remove_key_from_pool(proto, key):
    pools = key_pool_store.load_key_pools(KEY_POOLS_PATH)
    pools, removed = key_pool_store.delete_pool_key(pools, proto, key)
    key_pool_store.save_key_pools(KEY_POOLS_PATH, pools)
    return bool(removed)


def build_config(form):
    router_ip = form.get('routerip', detect_router_ip()).strip() or detect_router_ip()
    browser_port = form.get('browser_port', str(DEFAULT_BROWSER_PORT)).strip() or str(DEFAULT_BROWSER_PORT)
    fork_repo_owner = DEFAULT_FORK_REPO_OWNER
    fork_repo_name = DEFAULT_FORK_REPO_NAME
    fork_button_label = f'Fork by {fork_repo_owner}'
    default_proxy_mode = form.get('default_proxy_mode', 'none').strip() or 'none'
    web_auth_user = form.get('web_auth_user', 'admin').strip() or 'admin'
    web_auth_token = form.get('web_auth_token', '').strip()

    return f"""# ВЕРСИЯ СКРИПТА 2.2.1

token = '{escape_python(form['token'])}'
usernames = ['{escape_python(form['username'])}']

routerip = '{escape_python(router_ip)}'
browser_port = '{escape_python(browser_port)}'
web_auth_user = '{escape_python(web_auth_user)}'
web_auth_token = '{escape_python(web_auth_token)}'
web_auth_disabled = False
fork_repo_owner = '{escape_python(fork_repo_owner)}'
fork_repo_name = '{escape_python(fork_repo_name)}'
fork_button_label = '{escape_python(fork_button_label)}'

localportsh = '1082'
localportvmess = '10810'
localportvless = '10811'
localporttrojan = '10829'
default_proxy_mode = '{escape_python(default_proxy_mode)}'
dnsovertlsport = '40500'
dnsoverhttpsport = '40508'
"""


def validate_form(form):
    required = ['token', 'username']
    missing = [key for key in required if not form.get(key, '').strip()]
    if missing:
        return False, 'Не заполнены обязательные поля: ' + ', '.join(missing)

    browser_port = form.get('browser_port', '').strip()
    if browser_port and not re.fullmatch(r'\d{2,5}', browser_port):
        return False, 'Поле browser_port должно содержать номер порта.'

    return True, ''


def write_config(form):
    os.makedirs(BOT_DIR, exist_ok=True)
    config_text = build_config(form)
    with open(BOT_CONFIG_PATH, 'w', encoding='utf-8') as file:
        file.write(config_text)
    os.chmod(BOT_CONFIG_PATH, 0o600)
    ensure_legacy_path(BOT_CONFIG_PATH, LEGACY_CONFIG_PATH)
    if os.path.exists(BOT_MAIN_PATH):
        ensure_legacy_path(BOT_MAIN_PATH, LEGACY_MAIN_PATH)


def switch_to_main_bot():
    command = (
        f'sleep 2; {INSTALLER_SERVICE_PATH} stop >/dev/null 2>&1 || true; '
        'sleep 1; '
        f'if [ -x {BOT_SERVICE_PATH} ]; then {BOT_SERVICE_PATH} restart >/dev/null 2>&1 || {BOT_SERVICE_PATH} start >/dev/null 2>&1 || true; fi'
    )
    subprocess.Popen(
        ['sh', '-c', command],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def install_web_only():
    command = (
        f'sleep 2; {INSTALLER_SERVICE_PATH} stop >/dev/null 2>&1 || true; '
        f'curl -fsSL {WEB_ONLY_SCRIPT_URL!r} -o /tmp/bypass_web_only_install.sh && '
        'chmod 755 /tmp/bypass_web_only_install.sh && '
        'install_action=-install; [ -x /opt/bin/unblock_update.sh ] && install_action=-update; '
        'REPO_REF=codex/web-only-v1 /bin/sh /tmp/bypass_web_only_install.sh "$install_action"'
    )
    subprocess.Popen(
        ['sh', '-c', command],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def page_html(message='', redirect_url=None, redirect_delay_seconds=3):
    router_ip = detect_router_ip()
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
    key_pool_script = """
    <script>
        const protoSelect = document.getElementById('proto-select');
        const keyListDiv = document.getElementById('key-list');
        const newKeyInput = document.getElementById('new-key-input');

        async function fetchKeys() {
            const proto = protoSelect.value;
            keyListDiv.innerHTML = 'Загрузка...';
            try {
                const resp = await fetch('/api/keys?proto=' + encodeURIComponent(proto));
                const data = await resp.json();
                if (data.keys && Array.isArray(data.keys)) {
                    if (data.keys.length === 0) {
                        keyListDiv.innerHTML = '<em>Нет ключей для выбранного протокола.</em>';
                    } else {
                        const list = document.createElement('ul');
                        list.style.paddingLeft = '18px';
                        data.keys.forEach(function(key) {
                            const item = document.createElement('li');
                            item.style.marginBottom = '6px';
                            const text = document.createElement('span');
                            text.style.wordBreak = 'break-all';
                            text.textContent = key;
                            const button = document.createElement('button');
                            button.type = 'button';
                            button.textContent = 'Удалить';
                            button.style.marginLeft = '8px';
                            button.style.color = '#e66';
                            button.style.background = 'none';
                            button.style.border = 'none';
                            button.style.cursor = 'pointer';
                            button.onclick = function() { removeKey(proto, key); };
                            item.appendChild(text);
                            item.appendChild(button);
                            list.appendChild(item);
                        });
                        keyListDiv.replaceChildren(list);
                    }
                } else {
                    keyListDiv.innerHTML = '<span style="color:#e66">Ошибка загрузки ключей</span>';
                }
            } catch (e) {
                keyListDiv.innerHTML = '<span style="color:#e66">Ошибка запроса</span>';
            }
        }

        async function addKey() {
            const proto = protoSelect.value;
            const key = newKeyInput.value.trim();
            if (!key) return alert('Введите ключ!');
            try {
                const resp = await fetch('/api/keys/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ proto: proto, key: key })
                });
                const data = await resp.json();
                if (data.result) {
                    newKeyInput.value = '';
                    fetchKeys();
                } else {
                    alert('Ключ уже есть или ошибка добавления');
                }
            } catch (e) {
                alert('Ошибка запроса');
            }
        }

        async function removeKey(proto, key) {
            if (!confirm('Удалить этот ключ?')) return;
            try {
                const resp = await fetch('/api/keys/remove', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ proto: proto, key: key })
                });
                const data = await resp.json();
                if (data.result) {
                    fetchKeys();
                } else {
                    alert('Ошибка удаления');
                }
            } catch (e) {
                alert('Ошибка запроса');
            }
        }

        protoSelect.addEventListener('change', fetchKeys);
        window.addEventListener('DOMContentLoaded', fetchKeys);
    </script>
"""
    return f"""<!doctype html>
<html lang=\"ru\">
<head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>Первичная настройка бота</title>
        {redirect_head}
    <style>
        :root {{ color-scheme: dark; --bg:#101418; --card:#182028; --text:#f4f7fb; --muted:#9fb0c3; --accent:#63e6be; --line:#2a3846; --warn:#ffd166; }}
        * {{ box-sizing:border-box; }}
        body {{ margin:0; font-family:Segoe UI, Arial, sans-serif; background:radial-gradient(circle at top, #203040, var(--bg) 60%); color:var(--text); }}
        .wrap {{ max-width:760px; margin:0 auto; padding:32px 20px 48px; }}
        .card {{ background:rgba(24,32,40,.94); border:1px solid var(--line); border-radius:18px; padding:24px; box-shadow:0 20px 60px rgba(0,0,0,.35); }}
        h1 {{ margin:0 0 12px; font-size:32px; }}
        p {{ color:var(--muted); line-height:1.5; }}
        .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
        label {{ display:block; font-size:14px; margin:16px 0 6px; color:var(--muted); }}
        input, select {{ width:100%; padding:12px 14px; border-radius:12px; border:1px solid var(--line); background:#0d141b; color:var(--text); }}
        .full {{ grid-column:1 / -1; }}
        button {{ margin-top:20px; width:100%; padding:14px 18px; border:0; border-radius:12px; background:var(--accent); color:#06281e; font-weight:700; cursor:pointer; }}
        .secondary-button {{ background:#2f4050; color:var(--text); border:1px solid var(--line); }}
        .notice {{ margin:0 0 18px; padding:12px 14px; border-radius:12px; background:rgba(255,209,102,.12); color:var(--warn); border:1px solid rgba(255,209,102,.25); }}
        .hint {{ margin-top:18px; font-size:14px; color:var(--muted); }}
        .pool-row {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:10px; align-items:center; margin-bottom:12px; }}
        .pool-row input {{ min-width:0; }}
        .pool-row button {{ margin-top:0; width:auto; white-space:nowrap; }}
        #key-list ul {{ margin:0; padding-left:18px; }}
        #key-list li {{ margin-bottom:6px; overflow-wrap:anywhere; }}
        @media (max-width: 680px) {{ .wrap {{ padding:18px 12px 36px; }} .card {{ padding:18px; border-radius:14px; }} .grid,.pool-row {{ grid-template-columns:1fr; }} h1 {{ font-size:24px; }} button,.pool-row button {{ width:100%; }} }}
    </style>
</head>
<body>
{redirect_script}
    <div class="wrap">
        <div class="card">
            <h1>Первичная настройка бота</h1>
            <p>Эта страница запускается до основного Telegram-бота. Заполните данные доступа, после сохранения installer запишет bot_config.py и запустит основной сервис.</p>
            {notice}
            <form method="post" action="/save">
                <div class="grid">
                    <div class="full">
                        <label for="token">BotFather token</label>
                        <input id="token" name="token" placeholder="123456:AA..." required>
                    </div>
                    <div>
                        <label for="username">Telegram username</label>
                        <input id="username" name="username" placeholder="mylogin" required>
                    </div>
                    <div>
                        <label for="browser_port">Порт веб-интерфейса</label>
                        <input id="browser_port" name="browser_port" value="8080">
                    </div>
                    <div>
                        <label for="web_auth_user">Логин веб-интерфейса</label>
                        <input id="web_auth_user" name="web_auth_user" value="admin">
                    </div>
                    <div class="full">
                        <label for="web_auth_token">Пароль веб-интерфейса</label>
                        <input id="web_auth_token" name="web_auth_token" placeholder="Необязательно: пусто = вход без пароля">
                    </div>
                    <div>
                        <label for="routerip">IP роутера</label>
                        <input id="routerip" name="routerip" value="{html.escape(router_ip)}">
                    </div>
                    <div>
                        <label for="default_proxy_mode">Режим Telegram API по умолчанию</label>
                        <select id="default_proxy_mode" name="default_proxy_mode">
                            <option value="none">none</option>
                            <option value="shadowsocks">shadowsocks</option>
                            <option value="vmess">vmess</option>
                            <option value="vless">vless</option>
                            <option value="trojan">trojan</option>
                        </select>
                    </div>
                </div>
                <button type="submit">Сохранить и запустить основной бот</button>
            </form>
            <form method="post" action="/install-web-only">
                <button class="secondary-button" type="submit">Установить без бота Telegram</button>
            </form>
            <hr style="margin:32px 0 18px; border:0; border-top:1px solid var(--line);">
            <h2 style="margin:0 0 12px; font-size:22px;">Пул ключей</h2>
            <div id="key-pool-ui">
                <div style="margin-bottom:12px;">
                    <label for="proto-select">Протокол:</label>
                    <select id="proto-select">
                        <option value="shadowsocks">shadowsocks</option>
                        <option value="vmess">vmess</option>
                        <option value="vless">vless</option>
                        <option value="vless2">vless2</option>
                        <option value="trojan">trojan</option>
                    </select>
                </div>
                <div class="pool-row">
                    <input id="new-key-input" type="text" placeholder="Новый ключ...">
                    <button onclick="addKey()" type="button">Добавить</button>
                </div>
                <div id="key-list"></div>
            </div>
            <div class="hint">После сохранения эта страница будет заменена основным интерфейсом бота на том же адресе.</div>
        </div>
    </div>
{key_pool_script}
</body>
</html>
"""


class InstallerHandler(BaseHTTPRequestHandler):
    def _send_file(self, file_path, content_type='image/png'):
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)

    def _request_is_allowed(self):
        client_ip = self.client_address[0] if self.client_address else ''
        return is_local_web_client(client_ip)

    def _ensure_request_allowed(self):
        if self._request_is_allowed():
            return True
        self._send_html('<h1>403 Forbidden</h1><p>Веб-интерфейс доступен только из локальной сети.</p>', status=403)
        return False

    def _send_html(self, text, status=200):
        body = text.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._ensure_request_allowed():
            return
        if self.path.startswith('/static/telegram.png'):
            self._send_file(os.path.join(os.path.dirname(__file__), 'static', 'telegram.png'))
            return
        if self.path.startswith('/static/youtube.png'):
            self._send_file(os.path.join(os.path.dirname(__file__), 'static', 'youtube.png'))
            return
        if self.path.startswith('/api/keys'):
            query = parse_qs(urlparse(self.path).query)
            proto = query.get('proto', [''])[0]
            if not proto:
                self._send_json({'error': 'no proto'}, status=400)
                return
            self._send_json({'proto': proto, 'keys': get_keys_for_proto(proto)})
            return
        self._send_html(page_html())

    def do_POST(self):
        if not self._ensure_request_allowed():
            return
        if self.path == '/install-web-only':
            install_web_only()
            router_ip = detect_router_ip()
            target_url = f'http://{router_ip}:{DEFAULT_BROWSER_PORT}/'
            self._send_html(
                page_html(
                    f'Запущена установка web-only версии без Telegram бота. Через несколько секунд откроется основной web-интерфейс: {target_url}',
                    redirect_url=target_url,
                    redirect_delay_seconds=8,
                )
            )
            return
        if self.path.startswith('/api/keys/add') or self.path.startswith('/api/keys/remove'):
            content_length = int(self.headers.get('Content-Length', '0'))
            raw_body = self.rfile.read(content_length).decode('utf-8', errors='ignore')
            try:
                data = json.loads(raw_body)
            except Exception:
                self._send_json({'error': 'bad json'}, status=400)
                return
            proto = data.get('proto')
            key = data.get('key')
            if not proto or not key:
                self._send_json({'error': 'missing proto or key'}, status=400)
                return
            if self.path.startswith('/api/keys/add'):
                self._send_json({'result': add_key_to_pool(proto, key)})
                return
            self._send_json({'result': remove_key_from_pool(proto, key)})
            return
        if self.path != '/save':
            self._send_html(page_html('Неизвестное действие.'), status=404)
            return

        content_length = int(self.headers.get('Content-Length', '0'))
        raw_body = self.rfile.read(content_length).decode('utf-8', errors='ignore')
        parsed = {key: values[0] for key, values in parse_qs(raw_body).items()}

        ok, message = validate_form(parsed)
        if not ok:
            self._send_html(page_html(message), status=400)
            return

        parsed['web_auth_user'] = parsed.get('web_auth_user', 'admin').strip() or 'admin'
        parsed['web_auth_token'] = parsed.get('web_auth_token', '').strip()

        try:
            write_config(parsed)
            switch_to_main_bot()
        except Exception as exc:
            self._send_html(page_html(f'Не удалось сохранить конфиг: {exc}'), status=500)
            return

        router_ip = parsed.get('routerip', detect_router_ip()).strip() or detect_router_ip()
        browser_port = parsed.get('browser_port', str(DEFAULT_BROWSER_PORT)).strip() or str(DEFAULT_BROWSER_PORT)
        target_url = f'http://{router_ip}:{browser_port}/'
        web_auth_user = parsed.get('web_auth_user', 'admin')
        web_auth_token = parsed.get('web_auth_token', '')
        web_auth_note = (
            f' Пароль веб-интерфейса: {web_auth_token}.'
            if web_auth_token else
            ' Пароль веб-интерфейса не задан; вход будет без пароля.'
        )
        self._send_html(
            page_html(
                f'Конфиг сохранён. Основной бот запускается. Основная страница: {target_url}. Логин веб-интерфейса: {web_auth_user}.{web_auth_note}',
                redirect_url=target_url,
                redirect_delay_seconds=12,
            )
        )

    def log_message(self, format_text, *args):
        return


def main():
    bind_host = resolve_bind_host()
    server = ThreadingHTTPServer((bind_host, DEFAULT_BROWSER_PORT), InstallerHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
