#!/usr/bin/python3
import html
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from installer_common import (
    detect_router_ip,
    escape_python,
    installer_page_parts,
    installer_target_url,
    is_local_web_client,
    normalize_web_auth_form,
    parse_urlencoded_request,
    resolve_bind_host,
    start_detached_shell,
    validate_installer_form,
    web_auth_summary,
    write_installer_config,
)


BOT_DIR = '/opt/etc/bot'
BOT_CONFIG_PATH = os.path.join(BOT_DIR, 'bot_config.py')
LEGACY_CONFIG_PATH = '/opt/etc/bot_config.py'
BOT_MAIN_PATH = os.path.join(BOT_DIR, 'main.py')
LEGACY_MAIN_PATH = '/opt/etc/bot.py'
BOT_SERVICE_PATH = '/opt/etc/init.d/S99telegram_bot'
INSTALLER_SERVICE_PATH = '/opt/etc/init.d/S98telegram_bot_installer'
APP_RUNTIME_MODE_FILE = '/opt/etc/bot_app_mode'
DEFAULT_BROWSER_PORT = int(os.environ.get('BYPASS_INSTALLER_PORT', '8080'))
DEFAULT_FORK_REPO_OWNER = 'andruwko73'
DEFAULT_FORK_REPO_NAME = 'bypass_keenetic'


def build_config(form):
    router_ip = form.get('routerip', detect_router_ip()).strip() or detect_router_ip()
    browser_port = form.get('browser_port', str(DEFAULT_BROWSER_PORT)).strip() or str(DEFAULT_BROWSER_PORT)
    fork_repo_owner = DEFAULT_FORK_REPO_OWNER
    fork_repo_name = DEFAULT_FORK_REPO_NAME
    fork_button_label = f'Fork by {fork_repo_owner}'
    default_proxy_mode = form.get('default_proxy_mode', 'none').strip() or 'none'
    web_auth_user = form.get('web_auth_user', 'admin').strip() or 'admin'
    web_auth_token = form.get('web_auth_token', '').strip()
    app_runtime_mode = form.get('app_runtime_mode', 'advanced').strip() or 'advanced'

    return f"""# ВЕРСИЯ СКРИПТА v1.536

token = '{escape_python(form.get('token', ''))}'
usernames = ['{escape_python(form.get('username', ''))}']

routerip = '{escape_python(router_ip)}'
browser_port = '{escape_python(browser_port)}'
web_auth_user = '{escape_python(web_auth_user)}'
web_auth_token = '{escape_python(web_auth_token)}'
web_auth_disabled = False
fork_repo_owner = '{escape_python(fork_repo_owner)}'
fork_repo_name = '{escape_python(fork_repo_name)}'
fork_button_label = '{escape_python(fork_button_label)}'
app_runtime_mode = '{escape_python(app_runtime_mode)}'

localportsh = '1082'
localportvmess = '10810'
localportvless = '10811'
localporttrojan = '10829'
default_proxy_mode = '{escape_python(default_proxy_mode)}'
dnsovertlsport = '40500'
dnsoverhttpsport = '40508'
"""


def validate_form(form):
    return validate_installer_form(form, ['token', 'username'])


def write_config(form):
    write_installer_config(
        BOT_DIR,
        BOT_CONFIG_PATH,
        build_config(form),
        LEGACY_CONFIG_PATH,
        BOT_MAIN_PATH,
        LEGACY_MAIN_PATH,
    )
    mode = form.get('app_runtime_mode', 'advanced').strip() or 'advanced'
    os.makedirs(os.path.dirname(APP_RUNTIME_MODE_FILE), exist_ok=True)
    with open(APP_RUNTIME_MODE_FILE, 'w', encoding='utf-8') as f:
        f.write(mode + '\n')


def switch_to_main_bot():
    command = (
        f'sleep 2; {INSTALLER_SERVICE_PATH} stop >/dev/null 2>&1 || true; '
        'sleep 1; '
        f'if [ -x {BOT_SERVICE_PATH} ]; then {BOT_SERVICE_PATH} restart >/dev/null 2>&1 || {BOT_SERVICE_PATH} start >/dev/null 2>&1 || true; fi'
    )
    start_detached_shell(command)


def install_web_only():
    write_config({
        'token': '',
        'username': '',
        'routerip': detect_router_ip(),
        'browser_port': str(DEFAULT_BROWSER_PORT),
        'default_proxy_mode': 'none',
        'web_auth_user': 'admin',
        'web_auth_token': '',
        'app_runtime_mode': 'web_only',
    })
    os.makedirs(os.path.dirname(APP_RUNTIME_MODE_FILE), exist_ok=True)
    with open(APP_RUNTIME_MODE_FILE, 'w', encoding='utf-8') as f:
        f.write('web_only\n')
    switch_to_main_bot()


def page_html(message='', redirect_url=None, redirect_delay_seconds=3):
    router_ip = detect_router_ip()
    notice, redirect_head, redirect_script = installer_page_parts(message, redirect_url, redirect_delay_seconds)
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
        @media (max-width: 680px) {{ .wrap {{ padding:18px 12px 36px; }} .card {{ padding:18px; border-radius:14px; }} .grid {{ grid-template-columns:1fr; }} h1 {{ font-size:24px; }} button {{ width:100%; }} }}
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
                            <option value="vless2">vless2</option>
                            <option value="trojan">trojan</option>
                        </select>
                    </div>
                </div>
                <button type="submit">Сохранить и запустить основной бот</button>
            </form>
            <form method="post" action="/install-web-only">
                <button class="secondary-button" type="submit">Запустить режим Web only</button>
            </form>
            <div class="hint">После сохранения эта страница будет заменена основным интерфейсом бота на том же адресе.</div>
        </div>
    </div>
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
        self._send_html(page_html())

    def do_POST(self):
        if not self._ensure_request_allowed():
            return
        if self.path == '/install-web-only':
            install_web_only()
            target_url = installer_target_url({}, DEFAULT_BROWSER_PORT)
            self._send_html(
                page_html(
                    f'Включен режим Web only в единой версии. Через несколько секунд откроется основной web-интерфейс: {target_url}',
                    redirect_url=target_url,
                    redirect_delay_seconds=8,
                )
            )
            return
        if self.path != '/save':
            self._send_html(page_html('Неизвестное действие.'), status=404)
            return

        parsed = parse_urlencoded_request(self)

        ok, message = validate_form(parsed)
        if not ok:
            self._send_html(page_html(message), status=400)
            return

        normalize_web_auth_form(parsed)

        try:
            write_config(parsed)
            switch_to_main_bot()
        except Exception as exc:
            self._send_html(page_html(f'Не удалось сохранить конфиг: {exc}'), status=500)
            return

        target_url = installer_target_url(parsed, DEFAULT_BROWSER_PORT)
        web_auth_user, web_auth_note = web_auth_summary(parsed)
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
