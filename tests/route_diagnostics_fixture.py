"""Loopback-only UI fixture using the production profile and web adapters."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

APP = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(APP))
from route_diagnostics_service import RouteDiagnosticsService
from route_profiles import profile_fingerprint


class FixtureRuntime:
    def __init__(self, **callbacks):
        self.store = callbacks['store']
        self.started = 0
        self.profile_id = ''
        self.state = 'idle'
        self.results = {}

    def start(self, profile_id):
        self.started, self.profile_id, self.state = time.time(), profile_id, 'running'

    def cancel(self):
        self.state = 'cancelled'

    def snapshot(self):
        if self.state == 'running' and time.time() - self.started >= .3:
            self.state = 'completed'
            profile = next(p for p in self.store.snapshot()['profiles'] if p['id'] == self.profile_id)
            self.results[self.profile_id] = {
                'generation': 3, 'checked_at': time.time(), 'recommended_protocol': 'vless2',
                'profile_fingerprint': profile_fingerprint(profile),
                'windows': [
                    {'identity': {'protocol': proto}, 'metrics': {'reason': '', 'median_ms': latency,
                        'p95_ms': latency+25, 'sent': 20, 'received_on_time': 20}}
                    for proto, latency in (('vless', 240), ('vless2', 110))
                ],
            }
        return {'job': {'state': self.state, 'running': self.state == 'running'}, 'results': self.results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='bypass-route-ui-') as directory:
        control = SimpleNamespace(lock=threading.RLock(), generation=lambda: 3,
            capture=lambda: SimpleNamespace(generation=3), current=lambda ticket: True)
        service = RouteDiagnosticsService(path=Path(directory)/'profiles.json', control=control,
            load_keys=lambda: {'vless': 'fixture-private', 'vless2': 'fixture-private-2'},
            coordinated=lambda name, work: (True, work()), probe_lock=threading.Lock(),
            resource_guard=lambda: True, wans=lambda: ['eth1'], runtime_factory=FixtureRuntime)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, content, kind, status=200):
                raw = content.encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', kind+'; charset=utf-8')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                path = urlsplit(self.path).path
                if path in ('/static/app.css', '/static/app.js'):
                    return self.send((APP/path.lstrip('/')).read_text(encoding='utf-8'),
                                     'text/css' if path.endswith('.css') else 'text/javascript')
                if path == '/api/ui_background':
                    return self.send(json.dumps({'available': True, 'enabled': True,
                        'shade': 55, 'panel_transparency': 20, 'url': '/fixture/background.svg'}), 'application/json')
                if path == '/fixture/background.svg':
                    return self.send('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><path fill="#143436" d="M0 0h40v40H0z"/></svg>', 'image/svg+xml')
                if self.path == '/api/route_diagnostics':
                    return self.send(json.dumps(service.payload()), 'application/json')
                if self.path == '/fixture/stop':
                    self.send('stopping', 'text/plain')
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                return self.send(service.page('fixture-csrf'), 'text/html')

            def do_POST(self):
                size = int(self.headers.get('Content-Length', 0))
                if size > 16384:
                    return self.send('{}', 'application/json', 413)
                data = parse_qs(self.rfile.read(size).decode('utf-8'))
                if data.get('csrf_token') != ['fixture-csrf'] or self.headers.get('X-CSRF-Token') != 'fixture-csrf':
                    return self.send('{}', 'application/json', 403)
                result = service.action(self.path.rsplit('/', 1)[-1], data)
                return self.send(json.dumps(dict(result or {}, ok=bool(result and result['success']))), 'application/json')

        with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
            server.serve_forever(poll_interval=.05)


if __name__ == '__main__':
    main()
