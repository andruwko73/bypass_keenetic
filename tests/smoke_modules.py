from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from proxy_config_builder import build_proxy_core_config, build_shadowsocks_config, build_trojan_config
import web_get_actions
import web_form_blocks
import web_pool_form_blocks
import web_post_actions


SS_KEY = 'ss://YWVzLTEyOC1nY206cGFzc3dvcmQ@example.com:8388#sample'
TROJAN_KEY = 'trojan://secret@example.com:443?sni=example.com#sample'
PORTS = {
    'vmess': 10810,
    'vless': 10811,
    'vless_transparent': 10812,
    'vless2': 10813,
    'vless2_transparent': 10814,
    'shadowsocks_bot': 10815,
    'trojan_bot': 10816,
}


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
    )
    outbound_tags = {outbound.get('tag') for outbound in core_config['outbounds']}
    assert {'proxy-shadowsocks', 'proxy-trojan', 'direct'} <= outbound_tags
    assert core_config['routing']['rules'][0]['outboundTag'] == 'direct'


def test_web_post_actions_helpers():
    data = {'target_list_name': ['custom'], 'list_name': ['fallback']}
    assert web_post_actions.form_value(data, 'missing', 'none') == 'none'
    assert web_post_actions.first_form_value(data, ('target_list_name', 'list_name')) == 'custom'
    assert web_post_actions.dispatch({}, '/pool_add', {}) is None


def test_web_get_actions_helpers():
    refreshed = []
    current_keys = {'vmess': 'key'}
    ctx = {
        'build_form': lambda message: 'form:' + message,
        'consume_flash_message': lambda: 'saved',
        'load_current_keys': lambda: current_keys,
        'cached_status_snapshot': lambda keys: None,
        'placeholder_web_status_snapshot': lambda: {'state': 'pending'},
        'placeholder_protocol_statuses': lambda keys: {'vmess': {'label': 'pending'}},
        'refresh_status_caches_async': lambda keys: refreshed.append(keys),
        'refresh_status_on_api': True,
        'get_web_command_state': lambda: {'running': False},
    }
    page = web_get_actions.dispatch(ctx, '/')
    assert page == {'kind': 'html', 'html': 'form:saved'}
    status = web_get_actions.dispatch(ctx, '/api/status')
    assert status['payload']['web'] == {'state': 'pending'}
    assert status['payload']['pool_probe_running'] is False
    assert refreshed == [current_keys]
    command = web_get_actions.dispatch(ctx, '/api/command_state')
    assert command['payload'] == {'running': False}


def test_web_form_blocks_helpers():
    assert web_form_blocks.proxy_mode_label('none', none_label='Без VPN') == 'Без VPN'
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
    tab = web_pool_form_blocks.render_protocol_tab('vless', 'Vless 1', 1, active=True)
    assert 'protocol-tab active' in tab
    panel = web_pool_form_blocks.render_protocol_panel(
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
        active=True,
        csrf_input_html='<input name="csrf_token" value="token">',
        enable_key_pool=False,
        enable_custom_checks=False,
    )
    assert 'protocol-workspace active' in panel
    assert 'csrf_token' in panel
    assert 'Пул ключей' not in panel
    assert 'custom-check-form' not in panel


def main():
    test_proxy_config_builder()
    test_web_get_actions_helpers()
    test_web_form_blocks_helpers()
    test_web_pool_form_blocks_helpers()
    test_web_post_actions_helpers()
    print('smoke_modules: ok')


if __name__ == '__main__':
    main()
