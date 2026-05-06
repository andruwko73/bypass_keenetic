import base64
import json
import re
import secrets
from http.cookies import SimpleCookie
from urllib.parse import parse_qs


class WebRequestMixin:
    csrf_cookie_name = 'bk_csrf_token'
    csrf_token_re = re.compile(r'^[A-Za-z0-9_-]{32,256}$')
    csrf_error_as_json = False
    auth_realm = 'bypass_keenetic web'
    local_client_checker = staticmethod(lambda address: False)
    web_auth_token_getter = staticmethod(lambda: '')
    web_auth_user_getter = staticmethod(lambda: 'admin')
    flash_message_setter = staticmethod(lambda message: None)

    def _request_is_allowed(self):
        client_ip = self.client_address[0] if self.client_address else ''
        return bool(self.local_client_checker(client_ip))

    def _ensure_request_allowed(self):
        if not self._request_is_allowed():
            self._send_html('<h1>403 Forbidden</h1><p>Web UI is available only from the local network.</p>', status=403)
            return False
        return self._ensure_web_auth()

    def _send_unauthorized(self):
        body = (
            'Authentication required. Use user "admin" and web_auth_token from '
            'bot_config.py, or leave web_auth_token empty to disable the password.'
        ).encode('utf-8')
        self.send_response(401)
        self.send_header('WWW-Authenticate', f'Basic realm="{self.auth_realm}"')
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _ensure_web_auth(self):
        expected_token = str(self.web_auth_token_getter() or '')
        if not expected_token:
            return True
        expected_user = str(self.web_auth_user_getter() or 'admin')
        header = self.headers.get('Authorization', '')
        if header.lower().startswith('basic '):
            try:
                decoded = base64.b64decode(header.split(' ', 1)[1].strip()).decode('utf-8')
                supplied_user, _, supplied_token = decoded.partition(':')
                if (
                    secrets.compare_digest(supplied_user, expected_user) and
                    secrets.compare_digest(supplied_token, expected_token)
                ):
                    return True
            except Exception:
                pass
        self._send_unauthorized()
        return False

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

    def _ensure_csrf_allowed(self, data=None):
        supplied = self.headers.get('X-CSRF-Token', '').strip()
        if not supplied and isinstance(data, dict):
            supplied = data.get('csrf_token', [''])[0].strip()
        cookie_token = self._csrf_token_from_cookie()
        if supplied and cookie_token and secrets.compare_digest(supplied, cookie_token):
            return True
        if self.csrf_error_as_json:
            self._send_json({'ok': False, 'error': 'CSRF token is missing or invalid.'}, status=403)
        else:
            self._send_html('<h1>403 Forbidden</h1><p>CSRF token is missing or invalid.</p>', status=403)
        return False

    def _read_post_data(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
        except Exception:
            length = 0
        body = self.rfile.read(max(0, length)).decode('utf-8', errors='replace')
        return parse_qs(body)

    def _send_html(self, html, status=200):
        body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-type', 'text/html; charset=utf-8')
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
        self.close_connection = True

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _send_redirect(self, location='/'):
        self.send_response(303)
        self.send_header('Location', location)
        self.send_header('Content-Length', '0')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True

    def _send_png(self, filepath):
        try:
            with open(filepath, 'rb') as file:
                body = file.read()
            content_type = 'image/png'
            if body.lstrip().startswith(b'<svg'):
                content_type = 'image/svg+xml'
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Content-Length', '9')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(b'Not Found')
        self.close_connection = True

    def _wants_json(self):
        accept = self.headers.get('Accept', '')
        requested_with = self.headers.get('X-Requested-With', '')
        return 'application/json' in accept or requested_with == 'fetch'

    def _send_action_result(self, result, success=True, extra=None, redirect='/'):
        if self._wants_json():
            payload = {
                'ok': bool(success),
                'result': result or '',
                'status': 'ok' if success else 'error',
            }
            if extra:
                payload.update(extra)
            self._send_json(payload, status=200 if success else 400)
            return
        self.flash_message_setter(result)
        self._send_redirect(redirect)
