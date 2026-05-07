import html


PROXY_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')
PROTOCOL_SECTIONS = [
    ('vless', 'Vless 1', 6, 'vless://...'),
    ('vless2', 'Vless 2', 6, 'vless://...'),
    ('vmess', 'Vmess', 6, 'vmess://...'),
    ('trojan', 'Trojan', 5, 'trojan://...'),
    ('shadowsocks', 'Shadowsocks', 5, 'shadowsocks://...'),
]


def js_bool(value):
    return 'true' if value else 'false'


def status_refresh_pending(status, protocol_statuses, pool_probe_pending=False):
    return (
        'Фоновая проверка связи выполняется' in (status or {}).get('api_status', '') or
        any(item.get('label') == 'Проверяется' for item in (protocol_statuses or {}).values()) or
        bool(pool_probe_pending)
    )


def proxy_mode_label(proxy_mode, none_label='Без прокси'):
    return {
        'none': none_label,
        'shadowsocks': 'Shadowsocks',
        'vmess': 'Vmess',
        'vless': 'Vless 1',
        'vless2': 'Vless 2',
        'trojan': 'Trojan',
    }.get(proxy_mode, proxy_mode)


def render_message_block(message, *, live=False):
    if message:
        safe_message = html.escape(message)
        block_id = ' id="web-action-message"' if live else ''
        return f'''<div{block_id} class="notice notice-result">
  <strong>Результат</strong>
  <pre class="log-output">{safe_message}</pre>
</div>'''
    if live:
        return '''<div id="web-action-message" class="notice notice-result hidden">
  <strong>Результат</strong>
  <pre class="log-output"></pre>
</div>'''
    return ''


def render_command_block(command_state, *, live=False):
    command_state = command_state or {}
    if command_state.get('label'):
        command_title = 'Команда выполняется' if command_state.get('running') else 'Последняя команда'
        suffix = 'Статус обновится без перезагрузки страницы.' if live else 'Обновление страницы происходит автоматически.'
        command_text = command_state.get('result') or f'⏳ {command_state["label"]} ещё выполняется. {suffix}'
        block_id = ' id="web-command-status"' if live else ''
        return f'''<div{block_id} class="notice notice-status">
  <strong>{html.escape(command_title)}: {html.escape(command_state['label'])}</strong>
  <pre class="log-output">{html.escape(command_text)}</pre>
</div>'''
    if live:
        return '''<div id="web-command-status" class="notice notice-status hidden">
  <strong></strong>
  <pre class="log-output"></pre>
</div>'''
    return ''


def render_socks_block(status, *, live=False):
    details = (status or {}).get('socks_details', '')
    if live:
        hidden = '' if details else ' hidden'
        return f'<p id="web-socks-details" class="status-note"{hidden}>{html.escape(details)}</p>'
    if details:
        return f'<p class="status-note">{html.escape(details)}</p>'
    return ''


def render_fallback_block(status, *, live=False):
    status = status or {}
    reason = status.get('fallback_reason')
    if reason and status.get('proxy_mode') == 'none':
        block_id = ' id="web-fallback-reason"' if live else ''
        return f'<p{block_id} class="status-note">Последняя неудачная попытка прокси: {html.escape(reason)}</p>'
    if live:
        return '<p id="web-fallback-reason" class="status-note hidden"></p>'
    return ''


def render_select_mode_picker(active_mode, csrf_input_html, *, none_label='Без VPN (по умолчанию)'):
    options = [
        ('none', none_label),
        ('shadowsocks', 'Shadowsocks'),
        ('vmess', 'Vmess'),
        ('vless', 'Vless 1'),
        ('vless2', 'Vless 2'),
        ('trojan', 'Trojan'),
    ]
    option_html = '\n'.join(
        f'            <option value="{value}"{" selected" if active_mode == value else ""}>{html.escape(label)}</option>'
        for value, label in options
    )
    return f'''<div id="mode-picker" class="hero-popover mode-picker hidden">
    <form method="post" action="/set_proxy" class="mode-picker-form">
        {csrf_input_html}
        <label class="mode-picker-label" for="hero-proxy-type">Активный протокол</label>
        <select id="hero-proxy-type" name="proxy_type">
{option_html}
        </select>
        <button type="submit">Применить режим</button>
    </form>
</div>'''


def render_button_mode_picker(active_mode, *, none_label='Без прокси', csrf_input_html=''):
    options = [
        ('none', none_label),
        ('shadowsocks', 'Shadowsocks'),
        ('vmess', 'Vmess'),
        ('vless', 'Vless 1'),
        ('vless2', 'Vless 2'),
        ('trojan', 'Trojan'),
    ]
    mode_buttons_html = ''.join(
        f'''<form method="post" action="/set_proxy" data-async-action="set-proxy">
        {csrf_input_html}
        <input type="hidden" name="proxy_type" value="{value}">
        <button type="submit" class="mode-choice{' active' if active_mode == value else ''}" data-mode-value="{value}">
            <span>{html.escape(label)}</span>
        </button>
    </form>'''
        for value, label in options
    )
    return f'''<div id="mode-picker" class="hero-popover mode-picker hidden">
    <div class="mode-picker-form">
        <span class="mode-picker-label">Активный протокол</span>
        <div class="mode-choice-grid">{mode_buttons_html}</div>
    </div>
</div>'''
