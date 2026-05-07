from pathlib import Path
import sys
import threading


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import key_pool_web
import key_pool_store
import telegram_pool_ui
import web_get_actions
import web_command_state
import web_form_blocks
import web_form_template
import web_http_common
import web_pool_form_blocks
import web_status_builder
import web_template_styles
import web_template_scripts
import web_post_actions
import telegram_confirm
import telegram_auth_state
import telegram_jobs
import telegram_message_flow
import telegram_install_ui
import telegram_key_ui
import pool_probe_controller
import pool_probe_runner
import proxy_apply_runtime
import proxy_status
import unblock_lists
import installer_common
import repo_update
from proxy_config_builder import build_proxy_core_config, build_shadowsocks_config, build_trojan_config


SS_KEY = 'ss://YWVzLTEyOC1nY206cGFzc3dvcmQ@example.com:8388#sample'
TROJAN_KEY = 'trojan://secret@example.com:443?sni=example.com#sample'
PORTS = {
    'vmess': 10810,
    'vmess_transparent': 10817,
    'vless': 10811,
    'vless_transparent': 10812,
    'vless2': 10813,
    'vless2_transparent': 10814,
    'shadowsocks_bot': 10815,
    'trojan_bot': 10816,
}


class _FakeButton:
    def __init__(self, text):
        self.text = text


class _FakeMarkup:
    def __init__(self, resize_keyboard=False):
        self.resize_keyboard = resize_keyboard
        self.rows = []

    def row(self, *buttons):
        self.rows.append([button.text for button in buttons])


class _FakeTypes:
    KeyboardButton = _FakeButton
    ReplyKeyboardMarkup = _FakeMarkup


class _InlineThread:
    def __init__(self, target, daemon=False):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


class _FakeChat:
    def __init__(self, chat_id, chat_type='private'):
        self.id = chat_id
        self.type = chat_type


class _FakeMessage:
    def __init__(self, chat_id=1, chat_type='private'):
        self.chat = _FakeChat(chat_id, chat_type)


def _hash_key(value):
    return 'h:' + value


def test_proxy_config_builder():
    ss_config = build_shadowsocks_config(SS_KEY, 1082)
    assert ss_config['server'] == ['example.com']
    assert ss_config['server_port'] == 8388
    assert ss_config['method'] == 'aes-128-gcm'

    trojan_config = build_trojan_config(TROJAN_KEY, 1090)
    assert trojan_config['remote_addr'] == 'example.com'
    assert trojan_config['remote_port'] == 443
    assert trojan_config['password'] == ['secret']

    core_config = build_proxy_core_config(
        shadowsocks_key=SS_KEY,
        trojan_key=TROJAN_KEY,
        ports=PORTS,
        error_log_path='/tmp/xray-error.log',
        connectivity_check_domains=['api.telegram.org'],
        include_vmess_transparent=True,
    )
    outbound_tags = {outbound.get('tag') for outbound in core_config['outbounds']}
    assert {'proxy-shadowsocks', 'proxy-trojan', 'direct'} <= outbound_tags
    assert core_config['routing']['rules'][0]['outboundTag'] == 'direct'


def test_key_pool_web():
    checks = [{'id': 'custom', 'label': 'Custom'}]
    current = {'vless': 'vless-key'}
    pools = {'vless': ['vless-key', 'unused-key'], 'vmess': ['vmess-key']}
    cache = {
        _hash_key('vless-key'): {'tg_ok': True, 'yt_ok': False, 'custom': {'custom': True}, 'ts': 1},
        _hash_key('vmess-key'): {'tg_ok': True, 'yt_ok': True, 'custom': {'custom': True}, 'ts': 2},
    }

    summary = key_pool_web.pool_status_summary(current, pools, cache, checks, _hash_key)
    assert summary['active_key_count'] == 1
    assert summary['pool_total_count'] == 3
    assert summary['checked_pool_count'] == 2
    assert summary['all_services_count'] == 1
    assert summary['any_service_count'] == 2
    assert summary['services'] == [
        {'label': 'Telegram', 'count': 2},
        {'label': 'YouTube', 'count': 1},
        {'label': 'Custom', 'count': 2},
    ]

    snapshot = key_pool_web.web_pool_snapshot(
        current,
        pools,
        cache,
        checks,
        include_keys=True,
        hash_key=_hash_key,
        display_name=lambda value: value.upper(),
        probe_state=lambda probe, field: 'ok' if probe.get(field) else 'fail' if field in probe else 'unknown',
        probe_checked_at=lambda probe: str(probe.get('ts', '')),
    )
    row = snapshot['vless']['rows'][0]
    assert row['active'] is True
    assert row['display_name'] == 'VLESS-KEY'
    assert row['custom'] == {'custom': 'ok'}
    assert row['key'] == 'vless-key'
    icon_html = lambda icon, alt, opacity=1.0, size=18: f'<img data-icon="{icon}" alt="{alt}">'
    check_defs = [{'id': 'custom', 'label': 'Custom', 'url': 'https://example.com/path', 'icon': 'chat'}]
    assert key_pool_web.custom_check_url_text(check_defs[0]) == 'example.com/path'
    assert 'custom-check-item' in key_pool_web.web_custom_checks_html(check_defs, icon_html)
    assert 'service-preset-btn' in key_pool_web.web_custom_presets_html([], check_defs, icon_html)
    assert 'custom-service-ok' in key_pool_web.web_custom_check_badges({'custom': {'custom': True}}, check_defs, icon_html)
    assert key_pool_web.web_probe_state({'tg_ok': True}, 'tg_ok') == 'ok'
    assert key_pool_web.web_probe_state({'tg_ok': None}, 'tg_ok') == 'unknown'
    assert key_pool_web.web_probe_checked_at({'ts': 0}) == ''

def test_key_pool_subscription_helpers():
    raw = '\n'.join([
        SS_KEY,
        'vless://uuid@example.com:443?security=tls#sample',
        TROJAN_KEY,
    ])
    classified = key_pool_store.classify_subscription_keys(raw)
    assert classified['shadowsocks'] == [SS_KEY]
    assert classified['vless'] == ['vless://uuid@example.com:443?security=tls#sample']
    assert classified['trojan'] == [TROJAN_KEY]

    pools, added = key_pool_store.add_subscription_keys_to_pool({'vless2': []}, 'vless2', classified)
    assert added == ['vless://uuid@example.com:443?security=tls#sample']
    assert pools['vless2'] == added
    candidates = key_pool_store.failover_candidates(
        {'vless': ['active', 'next'], 'vmess': ['vmess-key']},
        'vless',
        'active',
        protocols=('vless', 'vmess'),
    )
    assert candidates == [('vless', 'next'), ('vmess', 'vmess-key')]


def test_web_post_actions_helpers():
    data = {'target_list_name': ['custom'], 'list_name': ['fallback']}
    assert web_post_actions.form_value(data, 'missing', 'none') == 'none'
    assert web_post_actions.first_form_value(data, ('target_list_name', 'list_name')) == 'custom'
    assert web_post_actions.dispatch({}, '/pool_add', {}) is None


def test_web_action_feature_gates():
    calls = []
    disabled_ctx = {
        'pool_actions_enabled': False,
        'custom_checks_enabled': False,
        'probe_all_pool_keys_async': lambda **kwargs: calls.append('pool-probe'),
        'add_custom_check': lambda **kwargs: calls.append('custom-check'),
    }
    assert web_post_actions.dispatch(disabled_ctx, '/pool_probe', {}) is None
    assert web_post_actions.dispatch(disabled_ctx, '/custom_check_add', {}) is None
    probe = web_get_actions.dispatch({'pool_enabled': True, 'get_pool_probe_progress': lambda: {'running': False, 'total': 0}}, '/api/pool_probe')
    assert probe['payload']['status'] == 'idle'
    assert calls == []


def test_telegram_confirm_state_source():
    source = (ROOT / 'bot.py').read_text(encoding='utf-8')
    install_source = (ROOT / 'telegram_install_ui.py').read_text(encoding='utf-8')
    assert 'def _handle_telegram_confirmation(' in source
    assert '_handle_telegram_confirmation(message, level, bypass, set_menu_state, service)' in source
    assert 'if level != TELEGRAM_CONFIRM_LEVEL:' in source
    assert '_telegram_is_confirm_confirmation(message.text)' in source
    assert '_telegram_is_cancel_confirmation(message.text)' in source
    assert '_execute_confirmed_telegram_action(message.chat.id, action, reply_markup)' in source
    assert 'def _handle_install_menu_message(' in source
    assert '_telegram_install_action(message.text, include_web_only=True)' in source
    assert '_request_telegram_confirmation(message, set_menu_state, action)' in source
    for action in ('restart_services', 'reboot', 'dns_on', 'dns_off'):
        assert f"'{action}'" in source
    assert "_request_telegram_confirmation(message, set_menu_state, 'update_main')" in source
    for action in ('update_main', 'update_independent', 'update_no_bot', 'remove'):
        assert f"'{action}'" in install_source


def test_telegram_confirm_helpers():
    assert telegram_confirm.TELEGRAM_CONFIRM_LEVEL == 30
    assert telegram_confirm.telegram_is_confirm('✅ Подтвердить')
    assert telegram_confirm.telegram_is_cancel('Отмена')
    assert 'Перезагрузить роутер?' in telegram_confirm.telegram_confirm_prompt('reboot')


def test_telegram_auth_state_helpers():
    assert telegram_auth_state.normalize_username('@Admin') == 'admin'
    usernames, user_ids = telegram_auth_state.build_authorized_identities(['@Admin', '123'])
    assert usernames == {'admin'}
    assert user_ids == {123}
    states = {}
    lock = threading.Lock()
    assert telegram_auth_state.get_chat_menu_state(lock, states, 1) == {'level': 0, 'bypass': None}
    telegram_auth_state.set_chat_menu_state(lock, states, 1, level=8, bypass='vless')
    assert telegram_auth_state.get_chat_menu_state(lock, states, 1) == {'level': 8, 'bypass': 'vless'}
    assert telegram_auth_state.unauthorized_message_text('missing_username').startswith('У вашего Telegram-аккаунта')


def test_telegram_message_flow_helpers():
    message = _FakeMessage(chat_id=7)
    saved = []
    session = telegram_message_flow.private_menu_session(
        message,
        lambda chat_id: {'level': 2, 'bypass': 'vless'},
        lambda chat_id, level, bypass: saved.append((chat_id, level, bypass)),
        unset_marker=telegram_auth_state.MENU_STATE_UNSET,
    )
    assert telegram_message_flow.is_private_message(message)
    assert session.level == 2 and session.bypass == 'vless'
    session.set(3)
    session.set(telegram_auth_state.MENU_STATE_UNSET, 'vmess')
    session.set(new_bypass=None)
    assert saved == [(7, 3, 'vless'), (7, 3, 'vmess'), (7, 3, None)]
    calls = []
    assert telegram_message_flow.run_handlers(lambda: False, lambda: calls.append('hit') or True)
    assert calls == ['hit']
    assert not telegram_message_flow.is_private_message(_FakeMessage(chat_type='group'))


def test_telegram_jobs_helpers():
    payload = telegram_jobs.command_result_payload('-update', '42', 'service', 0, 'ok', now=lambda: 123.0)
    assert payload['chat_id'] == 42
    assert payload['finished_at'] == 123.0
    assert telegram_jobs.final_message('-update', 0).startswith('✅ Обновление')
    assert telegram_jobs.final_message('-remove', 1).startswith('⚠️ Команда')
    code = telegram_jobs.background_command_code('/opt/etc/bot/main.py', '-update', 'owner', 'repo', 42, 'service', 'branch')
    assert 'sys.path.insert' in code
    assert 'branch=' in code

    written = []
    popen_calls = []
    started, message = telegram_jobs.start_background_command(
        job_file='job.json',
        action='-update',
        repo_owner='owner',
        repo_name='repo',
        chat_id=42,
        menu_name='service',
        bot_source_path='/opt/etc/bot/main.py',
        sys_executable='python',
        read_json_file=lambda path, default=None: {},
        write_json_file=lambda path, payload: written.append((path, payload)),
        popen=lambda *args, **kwargs: popen_calls.append((args, kwargs)),
        now=lambda: 10.0,
    )
    assert started is True and message == ''
    assert written[0][1]['started_at'] == 10.0
    assert popen_calls


def test_telegram_install_ui_helpers():
    assert telegram_install_ui.install_action_for_text('🔰 Установка и удаление', include_web_only=True) == 'menu'
    assert telegram_install_ui.install_action_for_text('♻️ Установка / переустановка (ветка main)', include_web_only=True) == 'update_main'
    assert telegram_install_ui.install_action_for_text('♻️ Переустановка (ветка independent)', include_web_only=True) == 'update_independent'
    assert telegram_install_ui.install_action_for_text('♻️ Переустановка (без Telegram бота)', include_web_only=True) == 'update_no_bot'


def test_telegram_key_ui_helpers():
    assert telegram_key_ui.key_menu_rows()[0] == ('Shadowsocks', 'Vmess')
    assert ('📦 Пул ключей' in telegram_key_ui.key_menu_rows(include_pool=True)[3])
    assert telegram_key_ui.key_input_level('Trojan', trojan_level=13) == 13
    assert telegram_key_ui.key_input_level('Vless 2', trojan_level=13) == 12
    assert telegram_key_ui.key_install_protocol(13, trojan_level=13) == 'trojan'
    assert telegram_key_ui.key_install_protocol(12, trojan_level=13) == 'vless2'
    assert 'http://192.168.1.1:8080/' in telegram_key_ui.browser_hint('192.168.1.1', 8080)


def test_proxy_apply_runtime_helpers():
    settings = proxy_apply_runtime.proxy_apply_settings('/opt/etc/init.d/S24xray', {
        'shadowsocks': 10815,
        'vmess': 10810,
        'vless': 10811,
        'vless2': 10813,
        'trojan': 10816,
    })
    commands = []
    sleeps = []
    records = []
    result = proxy_apply_runtime.apply_installed_proxy_runtime(
        'vless',
        'key',
        settings=settings,
        app_mode_noun='режим бота',
        load_proxy_mode=lambda: 'none',
        proxy_mode_label=lambda mode: 'Без прокси',
        proxy_url_getter=lambda proto: 'proxy-url',
        build_diagnostics=lambda proto, key: 'diag',
        ensure_service_port=lambda port, restart_cmd, **kwargs: True,
        check_local_endpoint=lambda proto, port: (True, 'SOCKS ok.'),
        check_telegram_api=lambda proxy, **kwargs: (True, 'tg ok'),
        check_http=lambda proxy, **kwargs: (False, 'yt fail'),
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        run_command=commands.append,
        sleep=sleeps.append,
    )
    assert result.startswith('✅ Vless 1 ключ сохранён.')
    assert commands == ['/opt/etc/init.d/S24xray restart']
    assert sleeps == [18]
    assert records == [('vless', 'key', {'tg_ok': True, 'yt_ok': False})]
    pending = proxy_apply_runtime.apply_installed_proxy_runtime(
        'trojan',
        'key',
        settings=settings,
        app_mode_noun='режим бота',
        load_proxy_mode=lambda: 'trojan',
        proxy_mode_label=lambda mode: 'Trojan',
        proxy_url_getter=lambda proto: 'unused',
        build_diagnostics=lambda proto, key: '',
        ensure_service_port=lambda port, restart_cmd, **kwargs: True,
        check_local_endpoint=lambda proto, port: (True, 'SOCKS ok.'),
        check_telegram_api=lambda proxy, **kwargs: (_ for _ in ()).throw(AssertionError('must not verify')),
        verify=False,
        run_command=lambda command: None,
        sleep=lambda seconds: None,
    )
    assert 'в фоне' in pending


def test_pool_probe_controller_helpers():
    progress = pool_probe_controller.PoolProbeProgress()
    assert progress.snapshot()['running'] is False
    progress.update(running=True, checked=2)
    assert progress.snapshot()['checked'] == 2
    assert pool_probe_controller.pool_probe_progress_label({'scope': 'protocol'}) == 'Проверка выбранного пула'
    assert pool_probe_controller.failed_custom_probe_results([{'id': 'tg'}, {'label': 'empty'}]) == {'tg': False}
    assert pool_probe_controller.pool_probe_timeout_budget(
        [{'urls': ['https://a', 'https://b', 'https://ignored']}],
        2,
        1,
        (1, 2, 3, 4, 5, 6, 10, 20),
    ) == 85.0
    meminfo_path = ROOT / 'tests' / '_meminfo.tmp'
    try:
        meminfo_path.write_text('MemAvailable:        12345 kB\n', encoding='utf-8')
        assert pool_probe_controller.available_memory_kb(meminfo_path) == 12345
    finally:
        meminfo_path.unlink(missing_ok=True)
    selected, checks = pool_probe_controller.select_pool_probe_tasks(
        [('vless', 'fresh'), ('vless', 'new'), ('bad', 'skip'), ('vless', 'new')],
        protocol_order=('vless',),
        custom_checks=[{'id': 'tg'}],
        cache={'h:fresh': {'fresh': True}},
        hash_key=lambda value: 'h:' + value,
        is_fresh=lambda probe, **kwargs: bool(probe and probe.get('fresh')),
        stale_only=True,
    )
    assert selected == [('vless', 'new')]
    assert checks == [{'id': 'tg'}]

    state = {}
    invalidated = []
    collected = []
    times = iter([10.0, 20.0])

    def set_progress(**updates):
        state.update(updates)

    def run_worker(tasks, checks, set_checked, invalidate_caches):
        assert tasks == [('vless', 'key')]
        assert checks == [{'id': 'custom'}]
        set_checked(1)
        invalidate_caches()
        return 1, len(tasks)

    started, count = pool_probe_controller.start_pool_probe_worker(
        [('vless', 'key')],
        [{'id': 'custom'}],
        scope='manual_all',
        lock=threading.Lock(),
        set_progress=set_progress,
        run_worker=run_worker,
        invalidate_caches=lambda: invalidated.append('cache'),
        time_provider=lambda: next(times),
        collect_garbage=lambda: collected.append('gc'),
        thread_factory=_InlineThread,
    )
    assert started is True
    assert count == 1
    assert state['running'] is False
    assert state['checked'] == 1
    assert state['total'] == 1
    assert state['started_at'] == 10.0
    assert state['finished_at'] == 20.0
    assert invalidated == ['cache', 'cache']
    assert collected == ['gc']

    records = []
    tg_results = iter([(False, ''), (False, '')])
    yt_results = iter([(False, ''), (False, '')])
    pool_probe_controller.check_pool_key_through_proxy(
        'vless',
        'key',
        [{'id': 'custom'}],
        'proxy',
        check_telegram_api=lambda proxy, **kwargs: next(tg_results),
        check_http=lambda proxy, **kwargs: next(yt_results),
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        probe_custom_targets=lambda proxy, custom_checks=None: {'custom': True},
        retry_delay_seconds=0,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        sleep=lambda seconds: None,
    )
    assert records == [
        ('vless', 'key', {'tg_ok': False, 'yt_ok': False}),
        ('vless', 'key', {'custom': {'custom': False}}),
    ]


def test_pool_probe_runner_failover_candidate():
    records = []
    logs = []
    stopped = []
    cleaned = []

    def validate_outbound(proto, key_value, tag, proxy_outbound_from_key):
        assert tag == 'proxy-failover-validate'
        if key_value == 'bad':
            raise ValueError('bad key')

    result = pool_probe_runner.find_pool_failover_candidate(
        [('vless', 'bad'), ('vless', 'ok')],
        service='telegram',
        batch_size=2,
        test_port='1200',
        proxy_outbound_from_key=lambda *args, **kwargs: {},
        wait_for_socks5=lambda port, timeout=6: port == '1200',
        check_telegram_api=lambda proxy, **kwargs: (True, 'ok'),
        check_http=lambda proxy, **kwargs: (False, 'yt'),
        record_key_probe=lambda proto, key, **kwargs: records.append((proto, key, kwargs)),
        proto_label=lambda proto: proto,
        log=logs.append,
        telegram_timeouts=(1, 2),
        http_timeouts=(3, 4),
        validate_outbound=validate_outbound,
        build_config_batch=lambda valid_batch, test_port, proxy_outbound_from_key: {'valid': valid_batch},
        start_xray=lambda config: ('process', 'config.json'),
        stop_xray=lambda process, config_path: stopped.append((process, config_path)),
        cleanup_runtime=lambda kill_processes=False: cleaned.append(kill_processes),
        collect_garbage=lambda: None,
    )
    assert result == ('vless', 'ok', True, False)
    assert records == [('vless', 'ok', {'tg_ok': True, 'yt_ok': False})]
    assert stopped == [('process', 'config.json')]
    assert cleaned == [True]
    assert 'не подготовлен' in logs[0]


def test_proxy_status_runtime_helpers():
    assert proxy_status.port_is_listening(
        8080,
        command_runner=lambda *args, **kwargs: 'tcp 0 0 0.0.0.0:8080 0.0.0.0:* LISTEN\n',
    )
    original_get = proxy_status.requests.get

    class _Response:
        status_code = 204

        def close(self):
            pass

    try:
        proxy_status.requests.get = lambda *args, **kwargs: _Response()
        ok, message = proxy_status.check_http_through_proxy('socks5://127.0.0.1:1080')
        assert ok is True
        assert 'HTTP 204' in message
        ok, message = proxy_status.check_custom_target_through_proxy(
            lambda value: 'https://example.com/path',
            'socks5://127.0.0.1:1080',
            'example.com',
        )
        assert ok is True
        assert 'example.com' in message
    finally:
        proxy_status.requests.get = original_get

    custom_results = proxy_status.probe_custom_targets(
        'proxy',
        [{'id': 'custom', 'urls': ['bad', 'ok']}, {'label': 'skip'}],
        lambda proxy, target, **kwargs: (target == 'ok', ''),
        connect_timeout=1,
        read_timeout=1,
    )
    assert custom_results == {'custom': True}
    tail_path = ROOT / 'tests' / '_tail.tmp'
    try:
        tail_path.write_text('one\ntwo\nthree\n', encoding='utf-8')
        assert proxy_status.read_tail(tail_path, lines=2) == 'two\nthree'
    finally:
        tail_path.unlink(missing_ok=True)


def test_unblock_list_helpers():
    assert unblock_lists.normalize_unblock_route_name('vless.txt') == 'vless'
    assert unblock_lists.entries_from_service_text('one\n#comment\ntwo # note\none', {'skip'}) == ['one', 'two']


def test_web_command_state_helpers():
    assert web_command_state.estimate_update_progress('noop', '', ('update',)) == (0, '')
    assert web_command_state.estimate_update_progress('update', 'Бэкап создан.') == (70, 'Резервная копия готова, идёт замена файлов')
    state = {}
    lock = threading.Lock()
    web_command_state.set_flash_message(lock, state, 'ok')
    assert web_command_state.consume_flash_message(lock, state) == 'ok'
    assert web_command_state.consume_flash_message(lock, state) == ''


def test_web_http_common_helpers():
    class _Config:
        web_auth_user = 'root'
        web_auth_token = ' secret '
        web_auth_disabled = False

    assert web_http_common.is_local_web_client('192.168.1.2')
    assert web_http_common.is_local_web_client('127.0.0.1')
    assert not web_http_common.is_local_web_client('8.8.8.8')
    assert web_http_common.resolve_bind_host('192.168.1.1') == '192.168.1.1'
    assert web_http_common.resolve_bind_host('0.0.0.0') == ''
    assert web_http_common.resolve_bind_host('bad') == ''
    assert web_http_common.config_web_auth_token(_Config) == 'secret'
    assert web_http_common.config_web_auth_user(_Config) == 'root'
    _Config.web_auth_disabled = True
    assert web_http_common.config_web_auth_token(_Config) == ''


def test_installer_common_helpers():
    form = {'web_auth_user': ' ', 'web_auth_token': ' secret '}
    installer_common.normalize_web_auth_form(form)
    assert form['web_auth_user'] == 'admin'
    assert form['web_auth_token'] == 'secret'
    assert installer_common.validate_installer_form(
        {'token': 'x', 'username': 'u', 'browser_port': '8080'},
        ['token', 'username'],
    ) == (True, '')
    ok, message = installer_common.validate_installer_form(
        {'token': 'x', 'username': 'u', 'appapiid': 'abc'},
        ['token', 'username', 'appapiid'],
        require_app_api=True,
    )
    assert ok is False
    assert 'appapiid' in message
    assert installer_common.installer_target_url(
        {'routerip': '192.168.1.2', 'browser_port': '9090'},
        8080,
    ) == 'http://192.168.1.2:9090/'
    notice, redirect_head, redirect_script = installer_common.installer_page_parts('<ok>', 'http://192.168.1.2/', 2)
    assert '&lt;ok&gt;' in notice
    assert '2;url=' in redirect_head
    assert 'window.location.replace' in redirect_script


def test_repo_update_helpers():
    class _Response:
        def __init__(self, url, text='', payload=None, fail=False):
            self.url = url
            self.text = text
            self._payload = payload or {}
            self._fail = fail
            self.raw = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            if self._fail:
                raise repo_update.requests.RequestException('fail')

        def json(self):
            return self._payload

    class _Session:
        def __init__(self):
            self.calls = []

        def get(self, url, **_kwargs):
            self.calls.append(url)
            if 'raw.githubusercontent.com' in url or 'codeload.github.com' in url:
                return _Response(url, fail=True)
            return _Response(url, payload={'encoding': 'base64', 'content': 'aGVsbG8='})

    session = _Session()
    url, text = repo_update.download_repo_file_text(session, 'owner', 'repo', 'branch/name', 'script.sh')
    assert text == 'hello'
    assert 'api.github.com' in url
    assert any('raw.githubusercontent.com' in call for call in session.calls)
    assert any('codeload.github.com' in call for call in session.calls)
    assert repo_update.direct_fetch_env(('HTTP_PROXY',), {'HTTP_PROXY': 'x', 'keep': 'y'}) == {'keep': 'y'}


def test_web_get_actions_helpers():
    refreshed = []
    current_keys = {'vless': 'key'}
    ctx = {
        'build_form': lambda message: 'form:' + message,
        'consume_flash_message': lambda: 'saved',
        'load_current_keys': lambda: current_keys,
        'cached_status_snapshot': lambda keys: None,
        'active_mode_status_snapshot': lambda keys: {'web': {'state': 'active'}, 'protocols': {'vless': {}}},
        'refresh_status_caches_async': lambda keys: refreshed.append(keys),
        'pool_probe_locked': lambda: False,
        'get_web_command_state': lambda: {'running': False},
        'pool_enabled': True,
        'get_pool_probe_progress': lambda: {'running': True, 'total': 2},
        'web_pool_snapshot': lambda keys: {'vless': {'rows': []}},
        'pool_status_summary': lambda keys: {'active_text': '1 / 5'},
        'web_custom_checks': lambda: [{'id': 'custom'}],
        'time_provider': lambda: 123.0,
        'static_dir': '/tmp/static',
        'service_icons_enabled': True,
    }
    assert web_get_actions.dispatch(ctx, '/') == {'kind': 'html', 'html': 'form:saved'}
    status = web_get_actions.dispatch(ctx, '/api/status')
    assert status['payload']['pool_probe_running'] is True
    assert status['payload']['timestamp'] == 123.0
    assert refreshed == [current_keys]
    probe = web_get_actions.dispatch(ctx, '/api/pool_probe')
    assert probe['payload']['status'] == 'running'
    static = web_get_actions.dispatch(ctx, '/static/service-icons/test.png')
    assert static['path'].replace('\\', '/').endswith('/service-icons/test.png')


def test_web_form_blocks_helpers():
    assert web_form_blocks.proxy_mode_label('none') == 'Без прокси'
    assert web_form_blocks.js_bool(True) == 'true'
    assert web_form_blocks.js_bool(False) == 'false'
    assert 'csrf_token' in web_form_blocks.render_csrf_input('token')
    assert 'notice-result' in web_form_blocks.render_message_block('ok')
    assert web_form_blocks.render_message_block('', live=False) == ''
    assert 'hidden' in web_form_blocks.render_message_block('', live=True)
    button_picker = web_form_blocks.render_button_mode_picker('vless', csrf_input_html='<input name="csrf_token">')
    assert 'mode-choice-grid' in button_picker
    assert 'csrf_token' in button_picker
    assert '<select' in web_form_blocks.render_select_mode_picker('none', '<input>')
    update_buttons = web_form_blocks.render_update_buttons('<input name="csrf_token">')
    assert 'update_independent' in update_buttons
    assert 'data-confirm-title=' in update_buttons
    command_buttons = web_form_blocks.render_command_button_forms(
        [('restart_services', 'Restart', '', 'Confirm?', 'Do it?')],
        '<input name="csrf_token">',
    )
    assert 'restart_services' in command_buttons
    assert 'csrf_token' in command_buttons
    router_buttons = web_form_blocks.render_router_command_buttons('<input name="csrf_token">', dns_override_active=True)
    assert 'DNS Override ВКЛ' in router_buttons and 'success-button' in router_buttons
    tabs, panels = web_form_blocks.render_unblock_lists(
        [{'name': 'custom', 'label': 'Custom', 'content': 'one\n\n two'}],
        '<input name="csrf_token">',
        ('vk',),
        'all',
        lambda key: 'All' if key == 'all' else key.upper(),
    )
    assert 'data-list-target="custom"' in tabs
    assert 'Записей: 2' in panels
    assert 'csrf_token' in panels

def test_web_pool_form_blocks_helpers():
    table_class, custom_width, mobile_width = web_pool_form_blocks.pool_table_layout([{'id': 'chat'}])
    assert table_class == 'pool-table has-custom-checks'
    assert custom_width == 32
    assert mobile_width == 28
    progress = web_pool_form_blocks.pool_probe_topbar_text(
        True,
        {'checked': 1, 'total': 2},
        lambda data: 'Проверка',
        'ok',
    )
    assert '1/2' in progress
    pool_rows = web_pool_form_blocks.render_pool_items(
        key_name='vless',
        title='Vless 1',
        pool_keys=['vless://sample'],
        current_key='vless://sample',
        key_probe_cache={'hash-vless': {'tg_ok': True}},
        custom_checks=[],
        key_display_name=lambda key: 'sample-key',
        hash_key=lambda key: 'hash-vless',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        custom_check_badges=lambda probe, checks: '',
        probe_checked_at=lambda probe: 'now',
        csrf_input_html='<input name="csrf_token" value="token">',
    )
    assert 'pool-row-active' in pool_rows
    assert 'csrf_token' in pool_rows
    panel = web_pool_form_blocks.render_protocol_panel(
        key_name='vless',
        title='Vless 1',
        rows=3,
        placeholder='vless://...',
        current_key_value='vless://sample',
        status_info={'tone': 'ok', 'label': 'OK', 'details': 'details'},
        active_status_icons='',
        pool_items_html=pool_rows,
        pool_table_class='pool-table',
        pool_custom_col_width=32,
        pool_mobile_custom_col_width=28,
        custom_header_icons='',
        custom_presets_html='',
        custom_checks_html='',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        active=True,
        csrf_input_html='<input name="csrf_token" value="token">',
    )
    assert 'protocol-workspace active' in panel
    assert 'custom-check-form' in panel
    main_panel = web_pool_form_blocks.render_protocol_panel(
        key_name='vless',
        title='Vless 1',
        rows=3,
        placeholder='vless://...',
        current_key_value='vless://sample',
        status_info={'tone': 'ok', 'label': 'OK', 'details': 'details'},
        active_status_icons='',
        pool_items_html='',
        pool_table_class='pool-table',
        pool_custom_col_width=32,
        pool_mobile_custom_col_width=28,
        custom_header_icons='',
        custom_presets_html='',
        custom_checks_html='',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        csrf_input_html='<input name="csrf_token" value="token">',
        enable_key_pool=False,
        enable_custom_checks=False,
    )
    assert 'Пул ключей' not in main_panel
    assert 'custom-check-form' not in main_panel
    tabs_html, panels_html = web_pool_form_blocks.render_protocol_tabs_and_panels(
        [('vless', 'Vless 1', 3, 'vless://...')],
        {'vless': 'vless://sample'},
        {'vless': {'tone': 'ok', 'label': 'OK', 'details': 'details'}},
        '<input name="csrf_token" value="token">',
        telegram_icon_html=lambda opacity=1.0: 'TG',
        youtube_icon_html=lambda opacity=1.0: 'YT',
        enable_key_pool=False,
        enable_custom_checks=False,
    )
    assert 'protocol-tab active' in tabs_html
    assert 'protocol-workspace active' in panels_html
    assert 'csrf_token' in panels_html


def test_web_status_builder_helpers():
    assert web_status_builder.empty_protocol_status()['tone'] == 'empty'
    active = web_status_builder.active_protocol_status(
        endpoint_ok=True,
        endpoint_message='SOCKS ok.',
        api_ok=False,
        api_message='timeout',
        api_transient=True,
        yt_ok=True,
        yt_message='ok',
        custom_states={'chat': 'ok'},
        custom_checks=[{'id': 'chat', 'label': 'Chat'}],
    )
    assert active['tone'] == 'warn'
    assert active['api_pending'] is True
    cached = web_status_builder.cached_protocol_status(
        'key',
        {'tg_ok': False, 'yt_ok': True},
        [{'id': 'chat', 'label': 'Chat'}],
        {'chat': 'fail'},
    )
    assert cached['tone'] == 'warn'
    assert 'YouTube: работает' in cached['details']


def test_web_template_styles_helpers():
    styles = web_template_styles.render_web_styles()
    assert ':root{' in styles
    assert '.app-shell' in styles
    assert '{{' not in styles


def test_web_template_scripts_helpers():
    scripts = web_template_scripts.render_web_scripts(
        POOL_PROBE_UI_POLL_EXTENSION_MS=1000,
        TELEGRAM_SVG_B64='tg',
        YOUTUBE_SVG_B64='yt',
        csrf_token='token',
        custom_checks_json='[{"id":"x"}]',
        initial_command_running='false',
        initial_status_pending='false',
        enable_key_pool=False,
        enable_custom_checks=False,
    )
    assert 'const INITIAL_STATUS_PENDING = false;' in scripts
    assert 'const ENABLE_KEY_POOL = false;' in scripts
    assert "const CSRF_TOKEN = 'token';" in scripts
    assert 'function setupAsyncForms' in scripts
    assert "formData.set('confirm_switch', 'yes');" in scripts
    assert '{{' not in scripts


def test_web_form_template_smoke():
    page = web_form_template.render_web_form(
        APP_BRANCH_DESCRIPTION='test',
        APP_BRANCH_LABEL='codex/test',
        APP_VERSION_LABEL='1',
        POOL_PROBE_UI_POLL_EXTENSION_MS=1000,
        TELEGRAM_SVG_B64='',
        YOUTUBE_SVG_B64='',
        _telegram_icon_html=lambda opacity=1.0: 'TG',
        csrf_token='token',
        command_block='',
        command_buttons_html='',
        current_mode_label='Без прокси',
        custom_checks_json='[]',
        fallback_block='',
        initial_command_running='false',
        initial_status_pending='false',
        list_route_label='list',
        message_block='',
        mode_picker_block='',
        mode_toggle_label='Режим:',
        pool_summary={'active_text': 'none'},
        pool_summary_note='',
        protocol_panels_html='',
        protocol_tabs_html='',
        quick_key_label='Vless 1',
        quick_key_proto='vless',
        quick_key_value='',
        quick_start_note='note',
        socks_block='',
        start_button_label='start',
        status={'api_status': 'ok'},
        topbar_status_text='ok',
        unblock_panels_html='',
        unblock_tabs_html='',
        update_buttons_html='',
        enable_key_pool=False,
        enable_custom_checks=False,
    )
    assert ':root{' in page
    assert '.app-shell' in page
    assert '<script>' in page


def test_telegram_pool_ui():
    markup = telegram_pool_ui.pool_protocol_markup(
        _FakeTypes,
        ['Vless 1', 'Vless 2', 'Vmess', 'Trojan', 'Shadowsocks'],
    )
    assert markup.resize_keyboard is True
    assert markup.rows[0] == ['Vless 1', 'Vless 2']
    assert markup.rows[-1][0].startswith('\U0001f519')

    label = telegram_pool_ui.pool_key_button_label(
        1,
        'key-value',
        probe={'tg_ok': True, 'yt_ok': False},
        current_key='key-value',
        proto='vless',
        display_name=lambda value: 'Example Key',
    )
    assert label.startswith('\u2705 V1 1.')
    assert 'TG\u2705 YT\u274c' in label


def main():
    test_proxy_config_builder()
    test_proxy_status_runtime_helpers()
    test_unblock_list_helpers()
    test_web_command_state_helpers()
    test_web_http_common_helpers()
    test_installer_common_helpers()
    test_repo_update_helpers()
    test_key_pool_web()
    test_key_pool_subscription_helpers()
    test_telegram_pool_ui()
    test_web_get_actions_helpers()
    test_web_form_blocks_helpers()
    test_web_pool_form_blocks_helpers()
    test_web_status_builder_helpers()
    test_web_template_styles_helpers()
    test_web_template_scripts_helpers()
    test_web_form_template_smoke()
    test_web_post_actions_helpers()
    test_web_action_feature_gates()
    test_telegram_confirm_state_source()
    test_telegram_confirm_helpers()
    test_telegram_auth_state_helpers()
    test_telegram_message_flow_helpers()
    test_telegram_jobs_helpers()
    test_telegram_install_ui_helpers()
    test_telegram_key_ui_helpers()
    test_proxy_apply_runtime_helpers()
    test_pool_probe_controller_helpers()
    test_pool_probe_runner_failover_candidate()
    print('smoke_modules: ok')


if __name__ == '__main__':
    main()
