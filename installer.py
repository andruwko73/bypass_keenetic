#!/usr/bin/python3
import html
import os
import re
import secrets
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app_version import APP_VERSION_COUNTER
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
YOUTUBE_EDGE_PREFETCH_RUNNER = '/opt/etc/bot/youtube_edge_prefetch_runner.py'
YOUTUBE_EDGE_PREFETCH_LOG = '/opt/var/log/bypass-youtube-edge-prefetch.log'
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

    return f"""# ВЕРСИЯ СКРИПТА v{APP_VERSION_COUNTER}

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
pool_probe_min_available_kb = 190000
pool_probe_pause_available_kb = 125000
pool_probe_slow_available_kb = 190000
pool_probe_slow_memory_delay_seconds = 3.0
pool_probe_delay_seconds = 3.0
pool_probe_cpu_guard_enabled = True
pool_probe_max_cpu_percent = 45.0
pool_probe_cpu_sample_seconds = 0.35
pool_probe_high_cpu_delay_seconds = 8.0
pool_probe_high_cpu_max_wait_seconds = 120.0
pool_probe_max_load1 = 2.0
pool_probe_high_load_delay_seconds = 10.0
pool_probe_high_load_max_wait_seconds = 120.0
pool_probe_max_process_rss_kb = 66560
pool_probe_process_worker_enabled = True
pool_probe_process_worker_poll_seconds = 0.75
pool_probe_youtube_profile = 'quick'
pool_probe_quality_enabled = True
pool_probe_quality_download_url = 'https://speed.cloudflare.com/__down?bytes={{bytes}}'
pool_probe_quality_download_bytes = 524288
pool_probe_quality_min_available_kb = 170000
pool_probe_quality_max_samples_per_run = 6
pool_probe_quality_download_connect_timeout = 6.0
pool_probe_quality_download_read_timeout = 10.0
pool_probe_quality_stable_latency_ms = 2500
pool_probe_quality_fast_latency_ms = 1500
pool_probe_quality_1600p_min_mbps = 25.0
pool_probe_quality_4k_min_mbps = 45.0
memory_watchdog_enabled = True
memory_watchdog_rss_soft_kb = 87040
memory_watchdog_rss_limit_kb = 112640
memory_watchdog_idle_restart_rss_kb = 71680
memory_watchdog_idle_restart_hold_seconds = 120.0
memory_watchdog_check_interval = 60.0
memory_watchdog_min_uptime_seconds = 300.0
memory_watchdog_restart_cooldown_seconds = 1800.0
status_refresh_min_interval_seconds = 180.0
web_status_api_cache_ttl = 30.0
router_metrics_history_limit = 120
router_metrics_warn_bot_rss_kb = 66560
router_metrics_critical_bot_rss_kb = 87040
router_metrics_warn_load1 = 3.0
web_pools_api_cache_ttl = 45.0
service_route_intersections_cache_ttl = 60.0
web_response_cleanup_rss_kb = 61440
web_response_cleanup_min_interval_seconds = 60.0
memory_post_pool_restart_enabled = True
memory_post_pool_restart_rss_kb = 71680
memory_post_pool_cleanup_target_rss_kb = 63488
memory_post_pool_restart_delay_seconds = 20.0
memory_post_pool_restart_retry_seconds = 30.0
memory_post_pool_restart_max_wait_seconds = 300.0
memory_timeline_enabled = False
memory_timeline_path = '/opt/tmp/bypass_memory_timeline.jsonl'
memory_timeline_interval_seconds = 60.0
memory_timeline_max_events = 720
background_task_max_bot_rss_kb = 66560
udp_quic_block_shadowsocks_enabled = True
udp_quic_block_vmess_enabled = True
udp_quic_block_vless_enabled = True
udp_quic_block_vless2_enabled = True
udp_quic_block_trojan_enabled = True
youtube_quic_policy = 'auto'
telegram_udp_policy = 'auto'
youtube_edge_prefetch_enabled = True
youtube_edge_prefetch_mode = 'external'
youtube_edge_prefetch_start_delay_seconds = 120
youtube_edge_prefetch_interval_seconds = 1800
youtube_edge_prefetch_cache_path = '/opt/etc/bot/youtube_edge_cache.json'
youtube_edge_prefetch_status_path = '/opt/etc/bot/youtube_edge_prefetch_status.json'
youtube_edge_prefetch_lock_dir = '/tmp/bypass-youtube-edge-prefetch.lock'
youtube_edge_prefetch_cache_ttl_seconds = 259200
youtube_edge_prefetch_max_cache_entries = 128
youtube_edge_prefetch_max_hosts_per_run = 6
youtube_edge_prefetch_max_resolved_addresses = 16
youtube_edge_prefetch_max_candidates = 32
youtube_edge_prefetch_max_addresses_per_run = 8
youtube_edge_prefetch_min_available_kb = 125000
youtube_edge_prefetch_max_rss_kb = 66560
youtube_edge_prefetch_exclusive_ipsets = True
youtube_edge_prefetch_protect_shared_google = True
youtube_edge_prefetch_cache_restore_enabled = True
youtube_edge_prefetch_cache_restore_max_addresses = 16
youtube_edge_prefetch_cache_restore_require_quality_ok = True
youtube_edge_prefetch_fast_warm_enabled = True
youtube_edge_prefetch_fast_hosts = (
    'www.youtube.com',
    'youtube.com',
    'youtubei.googleapis.com',
    'manifest.googlevideo.com',
    'redirector.googlevideo.com',
    'i.ytimg.com',
    's.ytimg.com',
    'yt3.ggpht.com',
)
youtube_edge_prefetch_fast_max_hosts_per_run = 4
youtube_edge_prefetch_fast_max_candidates = 16
youtube_edge_prefetch_quality_probe_enabled = True
youtube_edge_prefetch_quality_target_ms = 1000
youtube_edge_prefetch_quality_timeout_seconds = 5
youtube_edge_prefetch_quality_bad_cooldown_seconds = 3600
youtube_edge_prefetch_quality_max_candidates = 12
youtube_edge_prefetch_scheduler_max_cpu_percent = 45
youtube_edge_prefetch_scheduler_max_load1 = 2.0
youtube_edge_prefetch_cpu_sample_ms = 250
youtube_edge_watch_warm_enabled = True
youtube_edge_watch_warm_urls = (
    'https://www.youtube.com/watch?v=aqz-KE-bpKQ',
    'https://www.youtube.com/watch?v=jfKfPfyJRdk',
)
youtube_edge_watch_warm_max_pages = 1
youtube_edge_watch_warm_max_hosts = 4
youtube_edge_watch_warm_max_bytes = 900000
youtube_edge_watch_warm_connect_timeout = 4
youtube_edge_watch_warm_max_time = 10
youtube_edge_prefetch_dns_servers = ('local', '1.1.1.1', '8.8.8.8')
youtube_edge_prefetch_hosts = (
    'www.youtube.com',
    'youtube.com',
    'm.youtube.com',
    'youtubei.googleapis.com',
    'youtubei-att.googleapis.com',
    'jnn-pa.googleapis.com',
    'play-fe.googleapis.com',
    'i.ytimg.com',
    's.ytimg.com',
    'yt3.ggpht.com',
    'www.gstatic.com',
    'manifest.googlevideo.com',
    'redirector.googlevideo.com',
)
telegram_call_learning_enabled = True
telegram_call_learning_state_path = '/tmp/bypass_telegram_call_learning.json'
telegram_call_learning_default_duration_seconds = 90
telegram_call_learning_max_duration_seconds = 180
telegram_call_learning_poll_interval_seconds = 1.0
telegram_call_learning_auto_enabled = True
telegram_call_learning_scan_interval_seconds = 5.0
telegram_call_learning_min_score = 5
telegram_call_learning_min_packets = 2
telegram_call_learning_min_bytes = 240
telegram_call_learning_max_candidates = 20
telegram_call_learning_max_seen_addresses = 512
telegram_call_learning_apply_by_default = True
telegram_call_learning_client_timeout_seconds = 900
telegram_call_learning_address_timeout_seconds = 14400
telegram_call_tproxy_enabled = True
ipset_refresh_command_timeout_seconds = 420
ipv6_bypass_fallback_enabled = True
reality_endpoint_overrides = {{}}
reality_endpoint_repair_enabled = True
reality_endpoint_repair_max_candidates = 6
reality_endpoint_repair_dns_servers = ('1.1.1.1', '8.8.8.8', '9.9.9.9')
auto_failover_startup_hold_seconds = 180
auto_failover_consecutive_failures = 3
auto_failover_traffic_guard_bypass_failures = 3
youtube_vless2_failover_enabled = True
youtube_vless2_failover_grace_seconds = 180
youtube_vless2_failover_poll_seconds = 120
youtube_vless2_failover_switch_cooldown_seconds = 300
youtube_vless2_failover_check_connect_timeout = 6
youtube_vless2_failover_check_read_timeout = 10
youtube_vless2_failover_confirm_retries = 3
youtube_vless2_failover_confirm_delay_seconds = 8.0
active_status_recent_success_ttl = 900
youtube_vless2_failover_recent_success_ttl = 900
youtube_vless2_restart_recheck_enabled = True
youtube_vless2_restart_recheck_cooldown_seconds = 300
youtube_vless2_failover_consecutive_failures = 3
youtube_vless2_hard_failure_recovery_cooldown_seconds = 90

localportsh = '1082'
localportvmess = '10810'
localportvless = '10811'
localporttrojan = '10829'
localportsh_tproxy = '11802'
localportvmess_tproxy = '11815'
localportvless_tproxy = '11812'
localportvless2_tproxy = '11814'
localporttrojan_tproxy = '11829'
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


def youtube_edge_prefetch_shell(trigger):
    safe_trigger = ''.join(ch for ch in trigger if ch.isalnum() or ch in '-_') or 'first-run'
    return (
        f'if [ -f {YOUTUBE_EDGE_PREFETCH_RUNNER} ]; then '
        'python_bin="$(command -v python3 2>/dev/null || echo /opt/bin/python3)"; '
        f'mkdir -p "$(dirname {YOUTUBE_EDGE_PREFETCH_LOG})" >/dev/null 2>&1 || true; '
        f'PYTHONPATH=/opt/etc/bot "$python_bin" {YOUTUBE_EDGE_PREFETCH_RUNNER} --trigger "{safe_trigger}" >> {YOUTUBE_EDGE_PREFETCH_LOG} 2>&1 || true; '
        'fi'
    )


def switch_to_main_bot(run_youtube_prefetch=False):
    command = (
        f'sleep 2; {INSTALLER_SERVICE_PATH} stop >/dev/null 2>&1 || true; '
        'sleep 1; '
        f'if [ -x {BOT_SERVICE_PATH} ]; then {BOT_SERVICE_PATH} restart >/dev/null 2>&1 || {BOT_SERVICE_PATH} start >/dev/null 2>&1 || true; fi'
    )
    if run_youtube_prefetch:
        command = f'{command}; sleep 8; {youtube_edge_prefetch_shell("first-run")}'
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


def page_html(message='', redirect_url=None, redirect_delay_seconds=3, csrf_token=''):
    router_ip = detect_router_ip()
    notice, redirect_head, redirect_script = installer_page_parts(message, redirect_url, redirect_delay_seconds)
    csrf_input_html = (
        f'<input type="hidden" name="csrf_token" value="{html.escape(csrf_token, quote=True)}">'
        if csrf_token else
        ''
    )
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
                {csrf_input_html}
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
                        <input id="web_auth_token" name="web_auth_token" placeholder="Обычно пароль основного интерфейса роутера">
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
                {csrf_input_html}
                <button class="secondary-button" type="submit">Запустить режим Web only</button>
            </form>
            <div class="hint">После сохранения эта страница будет заменена основным интерфейсом бота на том же адресе.</div>
        </div>
    </div>
</body>
</html>
"""


class InstallerHandler(BaseHTTPRequestHandler):
    csrf_cookie_name = 'bk_installer_csrf'
    csrf_token_re = re.compile(r'^[A-Za-z0-9_-]{32,256}$')
    max_post_bytes = 256 * 1024

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
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        csrf_cookie = getattr(self, '_csrf_cookie_token', '')
        if csrf_cookie:
            self.send_header(
                'Set-Cookie',
                f'{self.csrf_cookie_name}={csrf_cookie}; Path=/; HttpOnly; SameSite=Strict',
            )
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)

    def _csrf_token_from_cookie(self):
        cookie_header = self.headers.get('Cookie', '')
        if not cookie_header:
            return ''
        try:
            cookie = SimpleCookie()
            cookie.load(cookie_header)
            token_value = cookie.get(self.csrf_cookie_name)
            if token_value is None:
                return ''
            value = token_value.value.strip()
            return value if self.csrf_token_re.fullmatch(value) else ''
        except Exception:
            return ''

    def _get_or_create_csrf_token(self):
        token_value = self._csrf_token_from_cookie()
        if not token_value:
            token_value = secrets.token_urlsafe(32)
        self._csrf_cookie_token = token_value
        return token_value

    def _ensure_csrf_allowed(self, data):
        supplied = (data.get('csrf_token') or '').strip()
        cookie_token = self._csrf_token_from_cookie()
        if supplied and cookie_token and secrets.compare_digest(supplied, cookie_token):
            return True
        self._send_html('<h1>403 Forbidden</h1><p>CSRF token is missing or invalid.</p>', status=403)
        return False

    def do_GET(self):
        if not self._ensure_request_allowed():
            return
        if self.path.startswith('/static/telegram.png'):
            self._send_file(os.path.join(os.path.dirname(__file__), 'static', 'telegram.png'))
            return
        if self.path.startswith('/static/youtube.png'):
            self._send_file(os.path.join(os.path.dirname(__file__), 'static', 'youtube.png'))
            return
        self._send_html(page_html(csrf_token=self._get_or_create_csrf_token()))

    def do_POST(self):
        if not self._ensure_request_allowed():
            return
        try:
            parsed = parse_urlencoded_request(self, max_bytes=self.max_post_bytes)
        except ValueError as exc:
            self._send_html(page_html(str(exc), csrf_token=self._get_or_create_csrf_token()), status=413)
            return
        if not self._ensure_csrf_allowed(parsed):
            return
        if self.path == '/install-web-only':
            install_web_only()
            target_url = installer_target_url({}, DEFAULT_BROWSER_PORT)
            self._send_html(
                page_html(
                    f'Включен режим Web only в единой версии. Через несколько секунд откроется основной web-интерфейс: {target_url}',
                    redirect_url=target_url,
                    redirect_delay_seconds=8,
                    csrf_token=self._get_or_create_csrf_token(),
                )
            )
            return
        if self.path != '/save':
            self._send_html(page_html('Неизвестное действие.', csrf_token=self._get_or_create_csrf_token()), status=404)
            return

        ok, message = validate_form(parsed)
        if not ok:
            self._send_html(page_html(message, csrf_token=self._get_or_create_csrf_token()), status=400)
            return

        normalize_web_auth_form(parsed)

        try:
            write_config(parsed)
            switch_to_main_bot(run_youtube_prefetch=True)
        except Exception as exc:
            self._send_html(page_html(f'Не удалось сохранить конфиг: {exc}', csrf_token=self._get_or_create_csrf_token()), status=500)
            return

        target_url = installer_target_url(parsed, DEFAULT_BROWSER_PORT)
        web_auth_user, web_auth_note = web_auth_summary(parsed)
        self._send_html(
            page_html(
                f'Конфиг сохранён. Основной бот запускается. Основная страница: {target_url}. Логин веб-интерфейса: {web_auth_user}.{web_auth_note}',
                redirect_url=target_url,
                redirect_delay_seconds=12,
                csrf_token=self._get_or_create_csrf_token(),
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
