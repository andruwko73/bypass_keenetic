import html


PROXY_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')
PROTOCOL_SECTIONS = [
    ('vless', 'Vless 1', 6, 'vless://...'),
    ('vless2', 'Vless 2', 6, 'vless://...'),
    ('vmess', 'Vmess', 6, 'vmess://...'),
    ('trojan', 'Trojan', 5, 'trojan://...'),
    ('shadowsocks', 'Shadowsocks', 5, 'shadowsocks://...'),
]

STATUS_REFRESH_PENDING_MARKERS = (
    'Статус обновляется',
    'Проверяется актуальное состояние',
    'Проверяется связь текущего режима',
    'Фоновая проверка связи выполняется',
    'Telegram API не ответил вовремя',
    'Программа подбирает рабочий ключ',
    'Статус обновится без перезагрузки страницы',
)


def js_bool(value):
    return 'true' if value else 'false'


def status_refresh_pending(status, protocol_statuses, pool_probe_pending=False):
    proxy_mode = (status or {}).get('proxy_mode')
    active_status = (protocol_statuses or {}).get(proxy_mode, {}) if proxy_mode else {}
    api_status = (status or {}).get('api_status', '')
    return (
        any(marker in api_status for marker in STATUS_REFRESH_PENDING_MARKERS) or
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


def pool_probe_topbar_text(pool_probe_pending, progress, progress_label_func, fallback_text):
    if not pool_probe_pending:
        return fallback_text
    progress = progress or {}
    progress_total = int(progress.get('total') or 0)
    progress_checked = int(progress.get('checked') or 0)
    progress_label = progress_label_func(progress)
    progress_note = str(progress.get('note') or '').strip()
    progress_text = f'⏳ {progress_label}: {progress_checked}/{progress_total}'
    return f'{progress_text} - {progress_note}' if progress_note else progress_text


def pool_summary_note_with_progress(pool_summary_note, pool_probe_pending, progress, progress_label_func):
    if not pool_probe_pending:
        return pool_summary_note
    progress = progress or {}
    progress_note = str(progress.get('note') or '').strip()
    note_suffix = progress_note if progress_note else pool_summary_note
    return (
        f"{progress_label_func(progress)}: {int(progress.get('checked') or 0)}/"
        f"{int(progress.get('total') or 0)}. {note_suffix}"
    )


def _pool_loading_row_html(colspan=6):
    try:
        safe_colspan = max(1, int(colspan))
    except Exception:
        safe_colspan = 6
    return (
        f'<tr class="pool-row pool-empty-row"><td colspan="{safe_colspan}">'
        'Загружаю пул ключей...'
        '</td></tr>'
    )


def _protocol_tab_html(key_name, title, count, active=False):
    active_class = ' active' if active else ''
    return f'''<button type="button" class="seg-tab protocol-tab{active_class}" data-protocol-target="{html.escape(key_name, quote=True)}">
                    <span>{html.escape(title)}</span>
                    <span class="tab-count">{int(count)}</span>
                </button>'''


def _light_status_icons(status_info, telegram_icon_html, youtube_icon_html):
    status_info = status_info or {}
    icons = []
    if status_info.get('api_ok') or status_info.get('tg_ok'):
        icons.append(telegram_icon_html(opacity=1.0))
    if status_info.get('yt_ok'):
        icons.append(youtube_icon_html(opacity=1.0))
    return ''.join(icons)


def _light_protocol_panel_html(
    *,
    key_name,
    title,
    rows,
    placeholder,
    current_key_value,
    status_info,
    active_status_icons,
    csrf_input_html='',
    subscription_settings=None,
    telegram_icon_html=None,
    youtube_icon_html=None,
    active=False,
    enable_key_pool=True,
    enable_custom_checks=True,
    pool_probe_pending=False,
):
    active_class = ' active' if active else ''
    safe_key_name = html.escape(key_name, quote=True)
    safe_title = html.escape(title)
    safe_value = html.escape(current_key_value or '')
    safe_placeholder = html.escape(placeholder)
    status_info = status_info or {}
    safe_tone = html.escape(status_info.get('tone', 'empty'), quote=True)
    safe_label = html.escape(status_info.get('label', ''))
    safe_details = html.escape(str(status_info.get('details', '') or '').strip().rstrip('.'))
    telegram_icon_html = telegram_icon_html or (lambda opacity=1.0: '')
    youtube_icon_html = youtube_icon_html or (lambda opacity=1.0: '')
    live_status = '1' if status_info.get('endpoint_ok') is not None else '0'
    pool_probe_start_disabled = ' disabled aria-disabled="true"' if pool_probe_pending else ' aria-disabled="false"'
    pool_probe_cancel_disabled = ' aria-disabled="false"' if pool_probe_pending else ' disabled aria-disabled="true"'
    subtabs = [('key', 'Ключ и подписка')]
    if enable_key_pool:
        subtabs.append(('pool', 'Пул ключей'))
    if enable_key_pool or enable_custom_checks:
        subtabs.append(('check', 'Проверка'))
    subtabs_html = ''
    if len(subtabs) > 1:
        subtab_buttons = ''.join(
            f'<button type="button" class="subtab{" active" if index == 0 else ""}" data-subview-target="{value}">{html.escape(label)}</button>'
            for index, (value, label) in enumerate(subtabs)
        )
        subtabs_html = f'<div class="subtabs">{subtab_buttons}</div>'
    import_form_html = ''
    pool_subview_html = ''
    if enable_key_pool:
        subscription_settings = subscription_settings or {}
        hwid_checked = ' checked' if subscription_settings.get('hwid_enabled') else ''
        import_form_html = f'''
            <form method="post" action="/pool_import" class="pool-import-form" data-async-action="pool-import">
                {csrf_input_html}
                <input type="hidden" name="type" value="{safe_key_name}">
                <label class="field-label">Импорт ключей и подписки</label>
                <p class="field-hint">Вставьте один ключ, список ключей или ссылку subscription. Vless-ключи попадут в пул {safe_title}; остальные протоколы будут разложены по своим пулам.</p>
                <textarea name="import_payload" rows="5" placeholder="vless://...&#10;vmess://...&#10;trojan://...&#10;ss://...&#10;https://sub.example.com/..."></textarea>
                <label class="subscription-hwid-toggle">
                    <input type="checkbox" class="subscription-switch-input" name="send_router_hwid" value="1"{hwid_checked}>
                    <span class="subscription-switch-ui" aria-hidden="true"></span>
                    <span class="subscription-hwid-label">Передавать HWID роутера</span>
                </label>
                <button type="submit" class="secondary-button">Импортировать</button>
            </form>'''
        pool_subview_html = f'''
        <div class="protocol-subview" data-subview="pool">
            <div class="pool-toolbar">
                <form method="post" action="/pool_probe" data-async-action="pool-probe">
                    {csrf_input_html}
                    <input type="hidden" name="type" value="{safe_key_name}">
                    <button type="submit" class="secondary-button" data-pool-probe-start-button{pool_probe_start_disabled}>Проверить пул</button>
                </form>
                <form method="post" action="/pool_probe_cancel" data-async-action="pool-probe-cancel">
                    {csrf_input_html}
                    <button type="submit" class="secondary-button" data-pool-probe-cancel-button{pool_probe_cancel_disabled}>Остановить проверку</button>
                </form>
                <form method="post" action="/pool_clear" data-async-action="pool-clear" data-confirm-title="Очистить пул?" data-confirm-message="Очистить весь пул ключей для {safe_title}?">
                    {csrf_input_html}
                    <input type="hidden" name="type" value="{safe_key_name}">
                    <button type="submit" class="danger pool-clear-btn">Очистить пул</button>
                </form>
            </div>
            <div class="pool-controls" data-pool-controls="{safe_key_name}">
                <input type="search" data-pool-filter="{safe_key_name}" placeholder="Поиск по пулу">
                <div class="pool-sort-control" data-pool-sort-control="{safe_key_name}">
                    <input type="hidden" data-pool-sort="{safe_key_name}" value="original">
                    <button type="button" class="pool-sort-button" data-pool-sort-button="{safe_key_name}" aria-expanded="false">Исходный порядок</button>
                    <div class="pool-sort-menu hidden" data-pool-sort-menu="{safe_key_name}">
                        <button type="button" class="pool-sort-option active" data-pool-sort-value="original">Исходный порядок</button>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="telegram">Telegram сначала</button>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="youtube">YouTube сначала</button>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="quality">Качество сначала</button>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="checked">Свежие проверки</button>
                        <span class="pool-sort-divider">Фильтр</span>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="working">Работают</button>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="problem">Есть проблемы</button>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="unknown">Не проверены</button>
                    </div>
                </div>
            </div>
            <div class="pool-table-wrap">
                <table class="pool-table" style="--custom-col-mobile:28px">
                    <colgroup>
                        <col class="pool-col-key">
                        <col class="pool-col-icon">
                        <col class="pool-col-icon">
                        <col class="pool-col-custom" style="width:32px">
                        <col class="pool-col-checked">
                        <col class="pool-col-actions">
                    </colgroup>
                    <thead><tr><th class="pool-key-head">Ключ</th><th class="pool-icon-head" data-core-service-head="telegram">{telegram_icon_html(opacity=1.0)}</th><th class="pool-icon-head" data-core-service-head="youtube">{youtube_icon_html(opacity=1.0)}</th><th class="pool-icon-head pool-custom-head" data-custom-check-head></th><th class="pool-checked-head">Проверка</th><th class="pool-actions-head">Действия</th></tr></thead>
                    <tbody data-pool-body="{safe_key_name}" data-pool-deferred="1">{_pool_loading_row_html(6)}</tbody>
                </table>
            </div>
        </div>'''
    check_subview_html = ''
    if enable_key_pool or enable_custom_checks:
        check_subview_html = f'''
        <div class="protocol-subview protocol-subview-check" data-subview="check">
            <div class="status-card">
                <span class="status-label">Состояние ключа</span>
                <span class="status-value">{safe_label}</span>
                <p class="status-note">{safe_details}</p>
            </div>
            <div class="protocol-check-loading" data-protocol-check-deferred="{safe_key_name}">
                <span class="status-label">Checks</span>
                <p class="status-note">Loading...</p>
            </div>
        </div>'''
    return f'''<section class="protocol-workspace{active_class}" data-protocol-card="{safe_key_name}" data-protocol-panel="{safe_key_name}" data-protocol-live-status="{live_status}" data-core-services="" data-core-services-loaded="0">
        <div class="workspace-head">
            <div>
                <h2 class="inline-page-title"><span class="title-kicker">Ключи</span><span>{safe_title}</span></h2>
                <p class="key-status-note" data-protocol-status-details>{safe_details}</p>
            </div>
            <span class="key-status-wrap"><span class="key-status-icons" data-protocol-status-icons>{active_status_icons}</span><span class="key-status-badge key-status-{safe_tone}" data-protocol-status-label>{safe_label}</span></span>
        </div>
        {subtabs_html}
        <div class="protocol-subview protocol-subview-key active" data-subview="key">
            <form method="post" action="/install" data-async-action="install" class="key-editor-form">
                {csrf_input_html}
                <input type="hidden" name="type" value="{safe_key_name}">
                <label class="field-label">Активный ключ {safe_title}</label>
                <textarea name="key" rows="{int(rows)}" placeholder="{safe_placeholder}" required data-key-textarea>{safe_value}</textarea>
                <div class="form-actions">
                    <button type="submit">Сохранить {safe_title}</button>
                </div>
            </form>
            {import_form_html}
        </div>
        {pool_subview_html}
        {check_subview_html}
    </section>'''


def render_light_protocol_tabs_and_panels(
    protocol_sections,
    current_keys,
    protocol_statuses,
    csrf_input_html,
    *,
    key_pools=None,
    subscription_settings=None,
    telegram_icon_html=None,
    youtube_icon_html=None,
    active_protocol=None,
    enable_key_pool=True,
    enable_custom_checks=True,
    pool_probe_pending=False,
):
    current_keys = current_keys or {}
    protocol_statuses = protocol_statuses or {}
    key_pools = key_pools or {}
    subscription_settings = subscription_settings or {}
    telegram_icon_html = telegram_icon_html or (lambda opacity=1.0: '')
    youtube_icon_html = youtube_icon_html or (lambda opacity=1.0: '')
    protocol_keys = [section[0] for section in protocol_sections]
    if active_protocol not in protocol_keys:
        active_protocol = protocol_keys[0] if protocol_keys else None
    tabs = []
    panels = []
    for key_name, title, rows, placeholder in protocol_sections:
        status_info = protocol_statuses.get(key_name, {
            'tone': 'empty',
            'label': 'Не сохранён',
            'details': 'Ключ ещё не сохранён на роутере',
        })
        active = key_name == active_protocol
        pool_keys = key_pools.get(key_name, []) if enable_key_pool else []
        tab_count = len(pool_keys) if enable_key_pool else (1 if current_keys.get(key_name, '').strip() else 0)
        tabs.append(_protocol_tab_html(key_name, title, tab_count, active=active))
        panels.append(_light_protocol_panel_html(
            key_name=key_name,
            title=title,
            rows=rows,
            placeholder=placeholder,
            current_key_value=current_keys.get(key_name, ''),
            status_info=status_info,
            active_status_icons=_light_status_icons(status_info, telegram_icon_html, youtube_icon_html),
            csrf_input_html=csrf_input_html,
            subscription_settings=subscription_settings.get(key_name, {}),
            telegram_icon_html=telegram_icon_html,
            youtube_icon_html=youtube_icon_html,
            active=active,
            enable_key_pool=enable_key_pool,
            enable_custom_checks=enable_custom_checks,
            pool_probe_pending=pool_probe_pending,
        ))
    return ''.join(tabs), ''.join(panels)


def compact_event_value(value):
    if isinstance(value, (list, tuple, set)):
        return ', '.join(str(item) for item in value)
    if isinstance(value, dict):
        return ', '.join(f'{key}={compact_event_value(item)}' for key, item in value.items())
    return '' if value is None else str(value)


def compact_event_details(details):
    if not isinstance(details, dict) or not details:
        return ''
    parts = []
    for key, value in details.items():
        if value in (None, '', [], {}, ()):
            continue
        key_text = str(key or '').strip()
        value_text = compact_event_value(value).replace('\r', ' ').replace('\n', ' ').strip()
        if key_text and value_text:
            parts.append(f'{key_text}={value_text}')
    return ' · '.join(parts)


def render_event_history_html(events, *, time_formatter=None):
    events = events or []
    if not events:
        return '''<section class="panel event-history-panel">
            <p class="section-subtitle">Пока нет записей о переключениях, маршрутах и обновлениях</p>
        </section>'''
    if time_formatter is None:
        import time
        time_formatter = lambda ts: time.strftime('%d.%m %H:%M', time.localtime(float(ts or 0)))
    rows = []
    for event in events[:50]:
        try:
            stamp = time_formatter(event.get('ts') or 0)
        except Exception:
            stamp = ''
        level = html.escape(event.get('level') or 'info', quote=True)
        action = html.escape(event.get('action') or '')
        protocol = html.escape(event.get('protocol_label') or event.get('protocol') or '')
        service = html.escape(event.get('service') or '')
        source = html.escape(event.get('source') or '')
        key_hash = html.escape(event.get('key_hash') or '')
        message = html.escape(event.get('message') or '')
        details_text = compact_event_details(event.get('details') or {})
        details = html.escape(details_text)
        meta = ' · '.join(item for item in (protocol, service, source, key_hash) if item)
        message_line = ' · '.join(item for item in (message, details) if item)
        title = html.escape(
            ' | '.join(
                item for item in (
                    stamp,
                    event.get('action') or '',
                    meta,
                    event.get('message') or '',
                    details_text,
                )
                if item
            ),
            quote=True,
        )
        rows.append(f'''<li class="event-history-item event-{level}">
            <span class="event-time">{html.escape(stamp)}</span>
            <span class="event-main" title="{title}"><span class="event-title-row"><strong>{action}</strong><small>{html.escape(meta)}</small></span><em>{message_line}</em></span>
        </li>''')
    return f'''<section class="panel event-history-panel">
        <div class="route-section-head">
            <small>Последние переключения ключей, обновления и изменения маршрутов по всем протоколам</small>
        </div>
        <ul class="event-history-list">{"".join(rows)}</ul>
    </section>'''


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
        progress_label = html.escape(str(command_state.get('progress_label') or 'Подготовка обновления'))
        timer_hidden = '' if command_state.get('command') == 'update' and command_state.get('running') else ' hidden'
        return f'''<div{block_id} class="notice notice-status">
  <strong>{html.escape(command_title)}: {html.escape(command_state['label'])}</strong>
  <div class="command-timer-block{timer_hidden}" data-command-progress>
    <div class="command-timer-header">
      <span data-command-progress-label>{progress_label}</span>
      <span data-command-progress-timer></span>
    </div>
  </div>
  <pre class="log-output">{html.escape(command_text)}</pre>
</div>'''
    if live:
        return '''<div id="web-command-status" class="notice notice-status hidden">
  <strong></strong>
  <div class="command-timer-block hidden" data-command-progress>
    <div class="command-timer-header">
      <span data-command-progress-label></span>
      <span data-command-progress-timer></span>
    </div>
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
            ('rollback_update', 'Откатить обновление', 'secondary-button', 'Откатить последнее обновление?', 'Будет восстановлен последний backup из /opt/root вместе с ключами, списками, конфигами прокси и режимом работы'),
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
