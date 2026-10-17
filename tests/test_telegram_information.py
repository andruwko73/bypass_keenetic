"""The information button must work offline and preserve both useful links."""
import ast
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import app_runtime_mode
import telegram_info_runtime as info


class MessageHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.links = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        assert tag in ('b', 'a')
        self.stack.append(tag)
        if tag == 'a':
            self.links.append(dict(attrs)['href'])

    def handle_endtag(self, tag):
        assert self.stack.pop() == tag

    def handle_data(self, data):
        self.text.append(data)


@pytest.mark.parametrize('pool_enabled', [True, False])
@pytest.mark.parametrize('version', ['1.1087', '<b>&"😀' * 1000, ''])
def test_short_valid_message_always_has_both_links(pool_enabled, version):
    text = info.telegram_information_html(version, '192.168.50.1', '8099', pool_enabled=pool_enabled)
    parsed = MessageHTML()
    parsed.feed(text)
    parsed.close()
    assert not parsed.stack
    assert parsed.links == ['https://github.com/andruwko73/bypass_keenetic', 'http://192.168.50.1:8099/']
    assert len(''.join(parsed.text).encode('utf-16-le')) // 2 < 1000
    assert len(text.encode('utf-16-le')) // 2 < 1500
    assert ('Пулы ключей' in text) == pool_enabled


@pytest.mark.parametrize('host,port,expected,default', [
    ('10.4.1.1', 80, 'http://10.4.1.1:80/', False),
    ('172.20.0.1', 8081, 'http://172.20.0.1:8081/', False),
    ('fd00::1', 8080, 'http://[fd00::1]:8080/', False),
    ('0.0.0.0', 8080, 'http://192.168.1.1:8080/', True),
    ('127.0.0.1', 8080, 'http://192.168.1.1:8080/', True),
    ('8.8.8.8', 8080, 'http://192.168.1.1:8080/', True),
    ('198.51.100.1', 8080, 'http://192.168.1.1:8080/', True),
    ('user:secret@host', 8080, 'http://192.168.1.1:8080/', True),
    (None, 'bad', 'http://192.168.1.1:8080/', True),
    ('::', 8080, 'http://192.168.1.1:8080/', True),
    ('fe80::1%eth0', 8080, 'http://192.168.1.1:8080/', True),
    ('192.168.2.1', 65536, 'http://192.168.2.1:8080/', True),
    ('192.168.2.1', True, 'http://192.168.2.1:8080/', True),
])
def test_panel_url_is_local_and_uses_configured_port(host, port, expected, default):
    assert info.local_panel_url(host, port) == (expected, default)


@pytest.mark.parametrize('owner,name', [
    ('x?token=secret', '../private'), ('admin:secret@host', '<a>'),
    ('a' * 1000, 'b' * 1000),
])
def test_invalid_repo_values_do_not_become_credential_links(owner, name):
    text = info.telegram_information_html(repo_owner=owner, repo_name=name)
    parsed = MessageHTML(); parsed.feed(text)
    assert parsed.links[0] == 'https://github.com/andruwko73/bypass_keenetic'
    assert 'secret' not in text


def test_configured_fork_link():
    parsed = MessageHTML()
    parsed.feed(info.telegram_information_html(repo_owner='example-owner', repo_name='router-fork'))
    assert parsed.links[0] == 'https://github.com/example-owner/router-fork'


@pytest.mark.parametrize('mode', ['simple', 'advanced', 'web_only'])
def test_button_sends_one_complete_offline_message_with_keyboard(mode):
    # Execute only the real two functions: importing bot would start runtime setup.
    tree = ast.parse((ROOT / 'app/bot.py').read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in
             ('_telegram_information_text', '_send_telegram_information')]
    assert len(nodes) == 2
    calls = []
    def forbidden(*args, **kwargs):
        raise AssertionError('Information must not fetch GitHub or read README')
    namespace = {
        '_telegram_info_runtime': lambda: info, 'APP_VERSION_LABEL': '1.1087',
        'routerip': '10.2.1.1', 'browser_port': '8090', 'fork_repo_owner': 'example',
        'fork_repo_name': 'router', 'app_runtime_mode': app_runtime_mode,
        '_load_app_runtime_mode': lambda: mode,
        '_fetch_remote_text': forbidden, '_read_text_file': forbidden,
        'bot': SimpleNamespace(send_message=lambda *args, **kwargs: calls.append((args, kwargs))),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'information-functions', 'exec'), namespace)
    keyboard = object()
    namespace['_send_telegram_information'](SimpleNamespace(chat=SimpleNamespace(id=123)), keyboard)
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == 123 and 'http://10.2.1.1:8090/' in args[1]
    assert kwargs == {'parse_mode': 'HTML', 'disable_web_page_preview': True, 'reply_markup': keyboard}
    assert ('Пулы ключей' in args[1]) == (mode != 'simple')
