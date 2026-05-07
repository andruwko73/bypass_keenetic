from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import key_pool_web
import key_pool_store
import web_get_actions
import web_form_blocks
import web_pool_form_blocks
import web_post_actions
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


def test_web_post_actions_helpers():
    data = {'target_list_name': ['custom'], 'list_name': ['fallback']}
    assert web_post_actions.form_value(data, 'missing', 'none') == 'none'
    assert web_post_actions.first_form_value(data, ('target_list_name', 'list_name')) == 'custom'
    assert web_post_actions.dispatch({}, '/pool_add', {}) is None


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
    assert 'notice-result' in web_form_blocks.render_message_block('ok')
    assert web_form_blocks.render_message_block('', live=False) == ''
    assert 'hidden' in web_form_blocks.render_message_block('', live=True)
    button_picker = web_form_blocks.render_button_mode_picker('vless', csrf_input_html='<input name="csrf_token">')
    assert 'mode-choice-grid' in button_picker
    assert 'csrf_token' in button_picker
    assert '<select' in web_form_blocks.render_select_mode_picker('none', '<input>')


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


def main():
    test_proxy_config_builder()
    test_key_pool_web()
    test_key_pool_subscription_helpers()
    test_web_get_actions_helpers()
    test_web_form_blocks_helpers()
    test_web_pool_form_blocks_helpers()
    test_web_post_actions_helpers()
    print('smoke_modules: ok')


if __name__ == '__main__':
    main()
