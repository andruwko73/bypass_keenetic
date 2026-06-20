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
    proxy_mode = (status or {}).get('proxy_mode')
    active_status = (protocol_statuses or {}).get(proxy_mode, {}) if proxy_mode else {}
    return (
        'Фоновая проверка связи выполняется' in (status or {}).get('api_status', '') or
        active_status.get('label') == 'Проверяется' or
        bool(active_status.get('api_pending')) or
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


def render_csrf_input(csrf_token):
    return f'<input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}">'


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
        suffix = 'Статус обновится без перезагрузки страницы' if live else 'Обновление страницы происходит автоматически'
        command_text = command_state.get('result') or f'⏳ {command_state["label"]} ещё выполняется. {suffix}'
        block_id = ' id="web-command-status"' if live else ''
        progress = max(0, min(100, int(command_state.get('progress') or 0)))
        progress_label = html.escape(str(command_state.get('progress_label') or 'Подготовка обновления'))
        progress_hidden = '' if command_state.get('command') == 'update' and (command_state.get('running') or progress) else ' hidden'
        return f'''<div{block_id} class="notice notice-status">
  <strong>{html.escape(command_title)}: {html.escape(command_state['label'])}</strong>
  <div class="command-progress-block{progress_hidden}" data-command-progress>
    <div class="command-progress-header">
      <span data-command-progress-label>{progress_label}</span>
      <span data-command-progress-timer></span>
    </div>
    <div class="command-progress-track"><span class="command-progress-fill" data-command-progress-fill style="width:{progress}%"></span></div>
  </div>
  <pre class="log-output">{html.escape(command_text)}</pre>
</div>'''
    if live:
        return '''<div id="web-command-status" class="notice notice-status hidden">
  <strong></strong>
  <div class="command-progress-block hidden" data-command-progress>
    <div class="command-progress-header">
      <span data-command-progress-label></span>
      <span data-command-progress-timer></span>
    </div>
    <div class="command-progress-track"><span class="command-progress-fill" data-command-progress-fill style="width:0%"></span></div>
  </div>
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


def render_status_blocks(message, command_state, status, *, live=False):
    return {
        'message_block': render_message_block(message, live=live),
        'command_block': render_command_block(command_state, live=live),
        'socks_block': render_socks_block(status, live=live),
        'fallback_block': render_fallback_block(status, live=live),
    }


def quick_key_context(status, current_keys, current_mode_label, *, fallback_proto='vless', fallback_label='Vless 1', protocols=PROXY_PROTOCOLS):
    status = status or {}
    current_keys = current_keys or {}
    proxy_mode = status.get('proxy_mode')
    proto = proxy_mode if proxy_mode in protocols else fallback_proto
    label = current_mode_label if proto == proxy_mode else fallback_label
    return {
        'proto': proto,
        'label': label,
        'value': html.escape(current_keys.get(proto, '')),
    }


def render_form_basics(message, command_state, status, current_keys, current_mode_label, *, live=False):
    basics = render_status_blocks(message, command_state, status, live=live)
    basics['quick_key'] = quick_key_context(status, current_keys, current_mode_label)
    basics['initial_command_running'] = js_bool((command_state or {}).get('running'))
    return basics


def render_select_mode_picker(active_mode, csrf_input_html, *, none_label='Без прокси (по умолчанию)'):
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


def render_app_runtime_mode_picker(active_mode, modes, csrf_input_html=''):
    def render_mode_form(value, label, _description):
        confirm_attrs = _confirm_attrs(
            f'Переключить режим на {label}?',
            'Сервис может перезапуститься, страница обновится. Ключи и списки сохранятся',
        )
        active_class = ' active' if active_mode == value else ''
        return f'''<form method="post" action="/set_app_mode" data-async-action="set-app-mode"{confirm_attrs}>
        {csrf_input_html}
        <input type="hidden" name="app_mode" value="{html.escape(value)}">
        <button type="submit" class="mode-choice{active_class}" data-app-mode-value="{html.escape(value)}">
            <span>{html.escape(label)}</span>
        </button>
    </form>'''

    mode_buttons_html = ''.join(
        render_mode_form(value, label, description)
        for value, label, description in modes
    )
    return f'''<div id="app-mode-picker" class="hero-popover mode-picker app-mode-picker hidden">
    <div class="mode-picker-form">
        <span class="mode-picker-label">Режим работы программы</span>
        <div class="mode-choice-grid app-mode-choice-grid">{mode_buttons_html}</div>
    </div>
</div>'''


def _confirm_attrs(title='', message=''):
    if not title and not message:
        return ''
    return (
        f' data-confirm-title="{html.escape(title)}"'
        f' data-confirm-message="{html.escape(message)}"'
    )


def render_command_button_forms(command_buttons, csrf_input_html):
    return ''.join(
        f'''<form method="post" action="/command" data-async-action="command"{_confirm_attrs(confirm_title, confirm_message)}>
            {csrf_input_html}
            <input type="hidden" name="command" value="{html.escape(command)}">
            <button type="submit" class="{html.escape(button_class)}">{html.escape(label)}</button>
        </form>'''
        for command, label, button_class, confirm_title, confirm_message in command_buttons
    )


def render_router_command_buttons(csrf_input_html, dns_override_active=False):
    return render_command_button_forms(
        [
            ('restart_services', 'Перезапустить сервисы', '', 'Перезапустить сервисы?', 'Службы прокси и DNS будут перезапущены; соединение может кратко пропасть'),
            ('update', 'Обновить до последнего релиза', '', 'Обновить до последнего релиза?', 'Код и служебные файлы будут обновлены без сброса ключей, пулов и списков'),
            ('rollback_update', 'Откатить обновление', 'secondary-button', 'Откатить последнее обновление?', 'Будет восстановлен последний backup из /opt/root и перезапущен сервис бота'),
            ('dns_on', 'DNS Override ВКЛ', 'success-button' if dns_override_active else '', 'Включить DNS Override?', 'Роутер сохранит конфигурацию и перезагрузится'),
            ('dns_off', 'DNS Override ВЫКЛ', 'danger', 'Выключить DNS Override?', 'Роутер сохранит конфигурацию и перезагрузится'),
            ('remove', 'Удалить компоненты', 'danger', 'Удалить компоненты?', 'Будут удалены установленные компоненты программы. Настройки роутера могут измениться'),
            ('reboot', 'Перезагрузить роутер', 'danger', 'Перезагрузить роутер?', 'Связь с веб-интерфейсом временно пропадет'),
        ],
        csrf_input_html,
    )


def render_unblock_lists(
    unblock_lists,
    csrf_input_html,
    social_service_keys,
    socialnet_all_key,
    socialnet_service_label,
    *,
    async_forms=True,
    show_line_count=True,
    confirm_service_actions=True,
    textarea_rows=12,
):
    tabs = []
    panels = []
    form_async_attr = ' data-async-action="save-list"' if async_forms else ''
    social_title = 'Добавить в список' if show_line_count else 'Добавить соцсети'
    all_add_label = socialnet_service_label(socialnet_all_key) if show_line_count else 'Все соцсети'
    all_remove_label = 'Удалить сервисы' if show_line_count else 'Удалить соцсети'

    def service_button(key, action, class_name, label, confirm_title='', confirm_message=''):
        confirm_attrs = _confirm_attrs(confirm_title, confirm_message) if confirm_service_actions else ''
        return (
            f'<button type="submit" name="service_key" value="{html.escape(key)}" '
            f'formaction="{action}" class="{class_name}"{confirm_attrs}>{html.escape(label)}</button>'
        )

    for list_index, entry in enumerate(unblock_lists):
        name = entry.get('name', '')
        label = entry.get('label', '')
        content = entry.get('content', '')
        safe_name = html.escape(name)
        safe_label = html.escape(label)
        safe_content = html.escape(content)
        active_class = ' active' if list_index == 0 else ''
        social_service_buttons = ''.join(
            service_button(
                key,
                '/append_socialnet',
                'secondary-button',
                socialnet_service_label(key),
                f'Добавить {socialnet_service_label(key)}?',
                f'Добавить {socialnet_service_label(key)} в {label}?',
            )
            for key in social_service_keys
        )
        tabs.append(f'''<button type="button" class="seg-tab list-tab{active_class}" data-list-target="{safe_name}">{safe_label}</button>''')
        if show_line_count:
            line_count = len([line for line in content.splitlines() if line.strip()])
            header_html = f'''<div>
                <h2 class="inline-page-title"><span class="title-kicker">Список обхода</span><span>{safe_label}</span></h2>
                <p class="section-subtitle">Записей: {line_count}; файл: <span class="file-chip">{safe_name}</span></p>
            </div>'''
        else:
            header_html = f'''<div>
                <h2 class="inline-page-title"><span class="title-kicker">Список обхода</span><span>{safe_label}</span></h2>
            </div>
            <span class="file-chip">{safe_name}</span>'''
        panels.append(f'''<section class="list-workspace{active_class}" data-list-panel="{safe_name}">
        <div class="workspace-head">
            {header_html}
        </div>
        <form method="post" action="/save_unblock_list"{form_async_attr} class="list-editor-form">
            {csrf_input_html}
            <input type="hidden" name="list_name" value="{safe_name}">
            <textarea name="content" rows="{int(textarea_rows)}" placeholder="example.org&#10;api.telegram.org">{safe_content}</textarea>
            <div class="form-actions">
                <button type="submit">Сохранить список</button>
            </div>
            <div class="social-list-actions">
                <span class="social-list-title">{social_title}</span>
                {social_service_buttons}
                {service_button(socialnet_all_key, '/append_socialnet', 'secondary-button', all_add_label, 'Добавить все сервисы?', f'Добавить все сервисы в {label}?')}
                {service_button(socialnet_all_key, '/remove_socialnet', 'danger', all_remove_label, 'Удалить все сервисы?', f'Удалить все сервисы из {label}?')}
            </div>
        </form>
    </section>''')
    return ''.join(tabs), ''.join(panels)
