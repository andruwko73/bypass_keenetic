import html
import json
from web_template_styles import render_web_styles
from web_template_scripts import render_web_scripts


ASSET_CACHE_REVISION = 'pool-service-columns-1768-1'


def render_web_style_asset(TELEGRAM_SVG_B64=''):
    return render_web_styles(TELEGRAM_SVG_B64=TELEGRAM_SVG_B64)


def render_web_script_asset(**kwargs):
    return render_web_scripts(**kwargs)


def _script_json(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')


def _script_bool(value):
    return str(value).strip().lower() == 'true'


def _safe_percent(value):
    try:
        return max(0, min(100, int(round(float(value)))))
    except Exception:
        return 0


def _attention_text_html(text):
    safe_text = html.escape(text)
    if str(text or '').startswith('Telegram API'):
        return f'<span class="attention-telegram-icon" aria-hidden="true"></span>{safe_text}'
    return safe_text


def _display_note_text(text):
    return str(text or '').strip().rstrip('.')


def _api_status_requires_attention(api_status):
    text = str(api_status or '').strip()
    if not text:
        return False
    lowered = text.casefold()
    failure_markers = (
        '❌',
        'не проходит',
        'не отвечает',
        'ошибка',
        'failed',
        'error',
        'timeout',
        'таймаут',
    )
    if any(marker in lowered for marker in failure_markers):
        return True
    ok_markers = ('подтверж', 'работает', 'ok', 'доступ')
    return not any(marker in lowered for marker in ok_markers)


def _attention_items(status, router_health, pool_summary_note, enable_key_pool, enable_telegram=True):
    items = []
    status = status or {}
    router_health = router_health or {}
    used_percent = _safe_percent(router_health.get('used_percent'))
    if used_percent >= 85:
        items.append(('danger', 'Память роутера почти заполнена', f'Сейчас занято {used_percent}%; лучше остановить проверку пула или перезапустить сервис'))
    elif used_percent >= 70:
        items.append(('warn', 'Память роутера под нагрузкой', f'Сейчас занято {used_percent}%; проверку большого пула стоит запускать осторожно'))

    api_status = str(status.get('api_status') or '').strip()
    if enable_telegram and _api_status_requires_attention(api_status):
        items.append(('warn', 'Telegram API требует внимания', api_status))

    pool_note_lower = str(pool_summary_note or '').lower()
    if enable_key_pool and 'не работает' in pool_note_lower:
        items.append(('warn', 'В пуле есть ключи с ошибками', 'Откройте вкладку "Ключи" и отфильтруйте строки с проблемами'))

    if not items:
        if enable_telegram:
            text = 'Telegram API отвечает, память роутера в норме'
        elif enable_key_pool:
            text = 'Память роутера в норме'
        else:
            text = 'Память роутера в норме, веб-интерфейс готов к работе'
        items.append(('ok', 'Проблем не найдено', text))
    return items


def _topbar_status_item(status, router_health, pool_summary_note, enable_key_pool, enable_telegram=True, bot_ready=False, topbar_status_text=''):
    status = status or {}
    override_text = str(topbar_status_text or '').strip()
    api_status = str(status.get('api_status') or '').strip()
    if override_text and override_text != api_status:
        tone = 'warn' if any(marker in override_text.casefold() for marker in ('ошибка', 'не работает', 'failed', 'error')) else 'info'
        return tone, 'Статус обновляется', override_text

    tone, title, text = _attention_items(status, router_health, pool_summary_note, enable_key_pool, enable_telegram)[0]
    if tone == 'ok' and enable_telegram:
        title = 'Telegram-бот работает' if bot_ready else 'Telegram API отвечает'
        text = 'API отвечает, память роутера в норме'
    return tone, title, text


def _topbar_status_html(status_item, *, enable_telegram=True, bot_ready=False):
    tone, title, text = status_item
    safe_tone = html.escape(tone or 'info', quote=True)
    icon_html = (
        '<span class="topbar-status-icon topbar-status-icon-telegram" aria-hidden="true"></span>'
        if enable_telegram and bot_ready else
        ''
    )
    return f'''<span class="api-pill topbar-status topbar-status-{safe_tone}" id="web-api-pill" data-bot-ready="{str(bool(bot_ready)).lower()}">
                    {icon_html}
                    <span class="topbar-status-copy">
                        <strong id="topbar-status-title">{html.escape(title)}</strong>
                        <span id="topbar-status-text">{html.escape(text)}</span>
                    </span>
                </span>'''


def render_web_form(
    APP_BRANCH_DESCRIPTION,
    APP_BRANCH_LABEL,
    APP_VERSION_LABEL,
    POOL_PROBE_UI_POLL_EXTENSION_MS,
    TELEGRAM_SVG_B64,
    YOUTUBE_SVG_B64,
    _telegram_icon_html,
    csrf_token,
    command_block,
    command_buttons_html,
    app_runtime_mode_description,
    app_runtime_mode_label,
    app_runtime_mode_picker_block,
    current_mode_label,
    custom_checks_json,
    fallback_block,
    initial_command_running,
    initial_status_pending,
    list_route_label,
    message_block,
    mode_picker_block,
    mode_toggle_label,
    pool_summary,
    pool_summary_note,
    protocol_panels_html,
    protocol_tabs_html,
    quick_key_label,
    quick_key_proto,
    quick_key_value,
    quick_start_note,
    router_health,
    socks_block,
    start_button_label,
    status,
    topbar_status_text,
    unblock_panels_html,
    unblock_tabs_html,
    event_history_html='',
    enable_async_forms=True,
    enable_custom_checks=True,
    enable_key_pool=True,
    enable_live_status=True,
    enable_telegram=True,
    bot_ready=False,
):
    start_form_async_attr = ' data-async-action="start"' if enable_async_forms else ''
    quick_install_async_attr = ' data-async-action="install"' if enable_async_forms else ''
    pool_probe_async_attr = ' data-async-action="pool-probe"' if enable_async_forms else ''
    pool_probe_cancel_async_attr = ' data-async-action="pool-probe-cancel"' if enable_async_forms else ''
    csrf_input_html = f'<input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}">'
    quick_start_forms = []
    if start_button_label:
        quick_start_forms.append(f'''<form method="post" action="/start"{start_form_async_attr}>
                                    {csrf_input_html}
                                    <button type="submit">{html.escape(start_button_label)}</button>
                                </form>''')
    quick_start_block = f'''
                            <div class="status-card-actions quick-start-actions">
                                {''.join(quick_start_forms)}
                            </div>''' if quick_start_forms else ''
    quick_key_note = (
        'Быстрое редактирование активного ключа, полное управление пулом находится во вкладке "Ключи"'
        if enable_key_pool else
        'Быстрое редактирование активного ключа, остальные ключи находятся во вкладке "Ключи"'
    )
    quick_key_secondary_label = 'Открыть пул ключей' if enable_key_pool else 'Открыть все ключи'
    router_health = router_health or {}
    router_memory_text = html.escape(str(router_health.get('memory_text') or 'недоступно'))
    router_health_note = html.escape(_display_note_text(router_health.get('note') or 'данные обновляются из /proc с коротким кэшем'))
    router_dns_note = html.escape(_display_note_text(router_health.get('dns_note') or ''))
    router_core_proxy_note = html.escape(_display_note_text(router_health.get('core_proxy_note') or ''))
    router_telegram_call_note = html.escape(_display_note_text(router_health.get('telegram_call_note') or ''))
    router_memory_percent = _safe_percent(router_health.get('used_percent'))
    router_memory_tone = ' danger' if router_memory_percent >= 85 else ' warn' if router_memory_percent >= 70 else ''
    keys_view_subtitle = (
        'Выберите протокол, сохраните активный ключ или управляйте его пулом'
        if enable_key_pool else
        'Выберите протокол и сохраните активный ключ'
    )
    key_pool_status_card = ''
    dashboard_classes = ['status-dashboard']
    if enable_key_pool:
        dashboard_classes.append('status-dashboard-with-pool')
    if not enable_telegram:
        dashboard_classes.append('status-dashboard-no-bot')
    dashboard_class = ' '.join(dashboard_classes)
    pool_probe_running = enable_key_pool and bool(router_health.get('pool_probe_running'))
    pool_probe_start_disabled = ' disabled aria-disabled="true"' if pool_probe_running else ' aria-disabled="false"'
    pool_probe_cancel_disabled = ' aria-disabled="false"' if pool_probe_running else ' disabled aria-disabled="true"'
    status_overview_subtitle = (
        'Связь, активный режим и сервисные действия собраны в одном месте'
        if enable_telegram else
        'Веб-интерфейс, состояние роутера и сервисные действия собраны в одном месте'
    )
    if enable_key_pool:
        key_pool_status_card = f'''
                        <div class="status-card key-pool-card">
                            <div class="status-card-top">
                                    <span class="card-icon">⚿</span>
                                    <div class="status-copy">
                                        <span class="status-label">Ключи и пул</span>
                                    <span class="status-value" id="pool-active-summary">{html.escape(pool_summary['active_text'])}</span>
                                    <p class="status-note" id="pool-summary-note">{html.escape(pool_summary_note)}</p>
                                    </div>
                                </div>
                            <div class="status-card-actions key-pool-actions">
                                <form method="post" action="/pool_probe"{pool_probe_async_attr}>
                                    {csrf_input_html}
                                    <button type="submit" class="outline-button" data-pool-probe-start-button{pool_probe_start_disabled}>Проверить все ключи</button>
                                </form>
                                <form method="post" action="/pool_probe_cancel"{pool_probe_cancel_async_attr}>
                                    {csrf_input_html}
                                    <button type="submit" class="outline-button" data-pool-probe-cancel-button{pool_probe_cancel_disabled}>Остановить проверку</button>
                                </form>
                            </div>
                        </div>'''
    active_mode_card = ''
    if enable_telegram:
        active_mode_card = f'''
                            <div class="status-card active-mode-card">
                                <div class="status-card-top">
                                    <span class="card-icon">◇</span>
                                    <div class="status-copy">
                                        <span class="status-label">Активный режим Telegram-бота</span>
                                        <span class="status-value" id="current-mode-label">{html.escape(current_mode_label)}</span>
                                        <p class="status-note">Списки обхода: <span id="list-route-label">{html.escape(list_route_label)}</span></p>
                                        <p class="status-note" id="active-mode-dns-note">{router_dns_note}</p>
                                    </div>
                                </div>
                                <div class="status-card-actions active-mode-actions">
                                    <div class="mode-control active-mode-control">
                                        <button type="button" id="mode-toggle-button" class="mode-toggle" onclick="toggleModePicker()">
                                            <span>{html.escape(mode_toggle_label)}</span>
                                            <span>{html.escape(current_mode_label)}</span>
                                        </button>
                                        {mode_picker_block}
                                    </div>
                                </div>
                            </div>'''
    secondary_status_column = ''
    if active_mode_card or key_pool_status_card:
        secondary_status_column = f'''
                        <div class="status-dashboard-column status-dashboard-column-secondary">
                            {active_mode_card}
                            {key_pool_status_card}
                        </div>'''
    topbar_status_item = _topbar_status_item(
        status,
        router_health,
        pool_summary_note,
        enable_key_pool,
        enable_telegram,
        bot_ready=bot_ready,
        topbar_status_text=topbar_status_text,
    )
    telegram_topbar_block = (
        _topbar_status_html(topbar_status_item, enable_telegram=enable_telegram, bot_ready=bot_ready)
        if enable_telegram else
        ''
    )
    bot_mode_control_block = ''
    asset_version = html.escape(f'{APP_VERSION_LABEL or "1"}-{ASSET_CACHE_REVISION}')
    try:
        custom_checks = json.loads(custom_checks_json or '[]') if enable_custom_checks else []
        if not isinstance(custom_checks, list):
            custom_checks = []
    except Exception:
        custom_checks = []
    event_history_content_html = event_history_html or '<div data-event-history-list></div>'
    event_history_drawer_html = f'''
        <div id="event-history-modal" class="event-history-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="event-history-title">
            <aside class="event-history-drawer">
                <div class="event-history-drawer-head">
                    <h2 id="event-history-title">История событий</h2>
                    <button type="button" class="secondary-button event-history-close" data-event-history-close aria-label="Закрыть историю событий">Закрыть</button>
                </div>
                <section class="event-history-content" data-event-history-pane="events">
                    <div class="router-metrics-compact" aria-live="polite">
                        <div class="router-metrics-compact-head">
                            <small id="router-metrics-status">Метрики загрузятся при открытии истории</small>
                            <button type="button" class="outline-button compact-button" data-router-metrics-refresh>Обновить</button>
                        </div>
                        <div class="router-metrics-compact-row">
                            <span><em>Load</em><strong id="router-metrics-load">-</strong></span>
                            <span><em>Bot RSS</em><strong id="router-metrics-bot-rss">-</strong></span>
                            <span><em>Bot CPU</em><strong id="router-metrics-bot-cpu">-</strong></span>
                            <span><em>Xray RSS</em><strong id="router-metrics-xray-rss">-</strong></span>
                            <span><em>Xray CPU</em><strong id="router-metrics-xray-cpu">-</strong></span>
                        </div>
                    </div>
                    {event_history_content_html}
                </section>
            </aside>
        </div>'''
    app_config_json = _script_json({
        'csrfToken': csrf_token,
        'customChecks': custom_checks,
        'initialCommandRunning': _script_bool(initial_command_running),
        'initialStatusPending': _script_bool(initial_status_pending),
        'enableAsyncForms': bool(enable_async_forms),
        'enableCustomChecks': bool(enable_custom_checks),
        'enableKeyPool': bool(enable_key_pool),
        'enableLiveStatus': bool(enable_live_status),
        'enableTelegram': bool(enable_telegram),
        'botReady': bool(bot_ready),
        'poolProbePollExtensionMs': int(POOL_PROBE_UI_POLL_EXTENSION_MS),
    })
    topbar_actions_class = 'topbar-actions' + ('' if enable_telegram else ' topbar-actions-web-only')
    page_class = ' class="command-running"' if _script_bool(initial_command_running) else ''
    return f'''<!DOCTYPE html>
<html lang="ru"{page_class}>
<head>
  <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <link rel="icon" href="data:,">
  <title>Установка ключей прокси</title>
    <link rel="stylesheet" href="/static/app.css?v={asset_version}">
    <script>window.BK_APP_CONFIG={app_config_json};</script>
    <script src="/static/app.js?v={asset_version}" defer></script>
</head>
<body{page_class}>
    <div class="app-shell">
        <header class="topbar">
            <div class="{topbar_actions_class}">
                <div class="app-caption">
                    <strong>Локальная панель управления обходом на роутере</strong>
                    <span class="app-branch">Режим работы: {html.escape(app_runtime_mode_description)}</span>
                </div>
                {telegram_topbar_block}
                {bot_mode_control_block}
                <div class="theme-control">
                    <button type="button" id="theme-toggle-button" class="theme-toggle" onclick="toggleThemePicker()" title="Выбрать тему интерфейса">
                        <span>Тема:</span>
                        <span id="theme-toggle-label">Темная</span>
                    </button>
                    <div id="theme-picker" class="hero-popover mode-picker theme-picker hidden">
                        <div class="mode-picker-form">
                            <span class="mode-picker-label">Оформление интерфейса</span>
                            <div class="mode-choice-grid">
                                <button type="button" class="mode-choice" data-theme-choice="dark" onclick="setTheme('dark')"><span>Темная</span></button>
                                <button type="button" class="mode-choice" data-theme-choice="light" onclick="setTheme('light')"><span>Светлая</span></button>
                                <button type="button" class="mode-choice" data-theme-choice="glass" onclick="setTheme('glass')"><span>Liquid Glass</span></button>
                            </div>
                        </div>
                    </div>
                </div>
                <span class="version-badge" title="Номер версии по количеству коммитов в ветке">{html.escape(APP_VERSION_LABEL)}</span>
            </div>
        </header>
        {message_block}
        {command_block}
        <div class="workspace-layout">
            <nav class="side-nav" aria-label="Разделы">
                <button type="button" class="nav-item active" data-view-target="status">
                    <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11.5 12 5l8 6.5"></path><path d="M6.5 10.5V20h11V10.5"></path></svg>
                    <span>Статус</span>
                </button>
                <button type="button" class="nav-item" data-view-target="keys">
                    <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="8" cy="15" r="4"></circle><path d="M11 12 21 2"></path><path d="m16 7 2 2"></path><path d="m14 9 2 2"></path></svg>
                    <span>Ключи</span>
                </button>
                <button type="button" class="nav-item" data-view-target="lists">
                    <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6h13"></path><path d="M8 12h13"></path><path d="M8 18h13"></path><path d="M3 6h.01"></path><path d="M3 12h.01"></path><path d="M3 18h.01"></path></svg>
                    <span>Списки</span>
                </button>
            </nav>
            <main class="app-main">
                <section class="app-view active" data-view="status">
                    <div class="view-head status-overview-head">
                        <div class="status-overview-copy">
                            <h2>Статус и сервис</h2>
                            <p class="section-subtitle">{html.escape(status_overview_subtitle)}</p>
                        </div>
                    </div>
                    <div class="{dashboard_class}">
                        <div class="status-dashboard-column status-dashboard-column-primary">
                            <div class="status-card quick-start-card">
                                <div class="status-card-top">
                                    <span class="card-icon">↗</span>
                                    <div class="status-copy">
                                        <span class="status-label">Быстрый старт</span>
                                        <p class="status-note">{html.escape(quick_start_note)}</p>
                                    </div>
                                </div>
                                {quick_start_block}
                            </div>
                            <div class="status-card router-health-card">
                                <div class="status-card-top">
                                    <span class="card-icon">CPU</span>
                                    <div class="status-copy">
                                        <span class="status-label">Роутер</span>
                                        <span class="status-value" id="router-memory-text">{router_memory_text}</span>
                                        <div class="health-meter{router_memory_tone}" id="router-memory-meter" title="Занято памяти: {router_memory_percent}%">
                                            <span style="width:{router_memory_percent}%"></span>
                                        </div>
                                        <p class="status-note" id="router-health-note">{router_health_note}</p>
                                        <p class="status-note" id="router-core-proxy-note">{router_core_proxy_note}</p>
                                        <p class="status-note" id="router-telegram-call-note">{router_telegram_call_note}</p>
                                    </div>
                                </div>
                                <div class="status-card-actions router-health-actions">
                                    <button type="button" class="outline-button" data-event-history-open>История событий</button>
                                </div>
                            </div>
                        </div>
                        {secondary_status_column}
                    </div>
                    <div class="overview-service-grid">
                        <section class="panel service-panel service-panel-wide">
                            <h3>Сервисные команды</h3>
                            <div class="command-grid service-command-grid">
                                <div class="app-mode-control">
                                    <button type="button" id="app-mode-toggle-button" class="mode-toggle app-mode-command" onclick="toggleAppModePicker()">
                                        <span>Режим работы программы:</span>
                                        <span id="app-mode-label">{html.escape(app_runtime_mode_label)}</span>
                                    </button>
                                    {app_runtime_mode_picker_block}
                                </div>
                                {command_buttons_html}
                            </div>
                        </section>
                    </div>
                    <section class="panel overview-key-panel">
                        <div class="workspace-head">
                            <div>
                                <h2 class="inline-page-title"><span class="title-kicker">Ключ текущего режима</span><span>{html.escape(quick_key_label)}</span></h2>
                                <p class="section-subtitle">{quick_key_note}</p>
                            </div>
                        </div>
                        <form method="post" action="/install"{quick_install_async_attr} class="key-editor-form">
                            {csrf_input_html}
                            <input type="hidden" name="type" value="{quick_key_proto}">
                            <label class="field-label">Ключ {html.escape(quick_key_label)}</label>
                            <textarea name="key" rows="4" placeholder="Вставьте ключ {html.escape(quick_key_label)}">{quick_key_value}</textarea>
                            <div class="form-actions">
                                <button type="submit">Сохранить ключ</button>
                                <button type="button" class="outline-button" data-view-target="keys">{quick_key_secondary_label}</button>
                            </div>
                        </form>
                    </section>
                </section>

                <section class="app-view" data-view="keys">
                    <div class="view-head">
                        <h2 class="inline-page-title"><span class="title-kicker">Ключи</span><span>Подключения по протоколам</span></h2>
                        <p class="section-subtitle">{keys_view_subtitle}</p>
                    </div>
                    <div class="segmented protocol-tabs">{protocol_tabs_html}</div>
                    <div class="protocol-panels">{protocol_panels_html}</div>
                </section>

                <section class="app-view" data-view="lists">
                    <div class="view-head">
                        <h2 class="inline-page-title"><span class="title-kicker">Маршрутизация</span><span>Списки обхода</span></h2>
                        <p class="section-subtitle">Домены из выбранного списка будут отправляться через соответствующий протокол</p>
                    </div>
                    <div class="segmented list-tabs">{unblock_tabs_html}</div>
                    <div class="list-panels">{unblock_panels_html}</div>
                </section>
            </main>
        </div>
        <nav class="mobile-nav" aria-label="Разделы">
            <button type="button" class="nav-item active" data-view-target="status">
                <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11.5 12 5l8 6.5"></path><path d="M6.5 10.5V20h11V10.5"></path></svg>
                <span>Статус</span>
            </button>
            <button type="button" class="nav-item" data-view-target="keys">
                <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="8" cy="15" r="4"></circle><path d="M11 12 21 2"></path><path d="m16 7 2 2"></path><path d="m14 9 2 2"></path></svg>
                <span>Ключи</span>
            </button>
            <button type="button" class="nav-item" data-view-target="lists">
                <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6h13"></path><path d="M8 12h13"></path><path d="M8 18h13"></path><path d="M3 6h.01"></path><path d="M3 12h.01"></path><path d="M3 18h.01"></path></svg>
                <span>Списки</span>
            </button>
        </nav>
        <div id="confirm-modal" class="confirm-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
            <div class="confirm-card">
                <h2 id="confirm-title">Подтверждение</h2>
                <p id="confirm-message">Подтвердите действие</p>
                <div class="confirm-actions">
                    <button type="button" id="confirm-cancel" class="secondary-button">Отмена</button>
                    <button type="button" id="confirm-accept" class="danger">Подтвердить</button>
                </div>
            </div>
        </div>
        {event_history_drawer_html}
    </div>
</body>
</html>'''
