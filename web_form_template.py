import html
from web_template_styles import render_web_styles
from web_template_scripts import render_web_scripts


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
    socks_block,
    start_button_label,
    status,
    topbar_status_text,
    unblock_panels_html,
    unblock_tabs_html,
    enable_async_forms=True,
    enable_custom_checks=True,
    enable_key_pool=True,
    enable_live_status=True,
):
    start_form_async_attr = ' data-async-action="start"' if enable_async_forms else ''
    quick_install_async_attr = ' data-async-action="install"' if enable_async_forms else ''
    pool_probe_async_attr = ' data-async-action="pool-probe"' if enable_async_forms else ''
    csrf_input_html = f'<input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}">'
    quick_key_note = (
        'Быстрое редактирование активного ключа. Полное управление пулом находится во вкладке "Ключи".'
        if enable_key_pool else
        'Быстрое редактирование активного ключа. Остальные ключи находятся во вкладке "Ключи".'
    )
    quick_key_secondary_label = 'Открыть пул ключей' if enable_key_pool else 'Открыть все ключи'
    keys_view_subtitle = (
        'Выберите протокол, сохраните активный ключ или управляйте его пулом.'
        if enable_key_pool else
        'Выберите протокол и сохраните активный ключ.'
    )
    key_pool_status_card = ''
    if enable_key_pool:
        key_pool_status_card = f'''
                        <div class="status-card">
                            <div class="status-card-top">
                                    <span class="card-icon">⚿</span>
                                    <div class="status-copy">
                                        <span class="status-label">Ключи и пул</span>
                                    <span class="status-value" id="pool-active-summary">{html.escape(pool_summary['active_text'])}</span>
                                    <p class="status-note" id="pool-summary-note">{html.escape(pool_summary_note)}</p>
                                    </div>
                                </div>
                            <div class="status-card-actions">
                                <button type="button" class="outline-button" data-view-target="keys">Открыть ключи</button>
                                <form method="post" action="/pool_probe"{pool_probe_async_attr}>
                                    {csrf_input_html}
                                    <button type="submit" class="outline-button">Проверить все ключи</button>
                                </form>
                            </div>
                        </div>'''
    web_styles = render_web_styles(TELEGRAM_SVG_B64=TELEGRAM_SVG_B64)
    web_scripts = render_web_scripts(
        POOL_PROBE_UI_POLL_EXTENSION_MS=POOL_PROBE_UI_POLL_EXTENSION_MS,
        TELEGRAM_SVG_B64=TELEGRAM_SVG_B64,
        YOUTUBE_SVG_B64=YOUTUBE_SVG_B64,
        csrf_token=csrf_token,
        custom_checks_json=custom_checks_json,
        initial_command_running=initial_command_running,
        initial_status_pending=initial_status_pending,
        enable_async_forms=enable_async_forms,
        enable_custom_checks=enable_custom_checks,
        enable_key_pool=enable_key_pool,
        enable_live_status=enable_live_status,
    )
    return f'''<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <link rel="icon" href="data:,">
  <title>Установка ключей прокси</title>
    <style>
{web_styles}    </style>
    <script>
{web_scripts}    </script>
</head>
<body>
    <div class="app-shell">
        <header class="topbar">
            <div class="topbar-actions">
                <div class="app-caption">
                    <strong>Локальная панель управления обходом на роутере</strong>
                    <span class="app-branch">Ветка: {html.escape(APP_BRANCH_LABEL)} · {html.escape(APP_BRANCH_DESCRIPTION)}</span>
                </div>
                <span class="api-pill" id="web-api-pill">{html.escape(topbar_status_text)}</span>
                <button type="button" id="mode-toggle-button" class="mode-toggle" onclick="toggleModePicker()">
                    <span>{html.escape(mode_toggle_label)}</span>
                    <span>{html.escape(current_mode_label)}</span>
                </button>
                <button type="button" class="theme-toggle" onclick="toggleTheme()" title="Переключить тему">
                    <span id="theme-toggle-label">Темная тема</span>
                </button>
                <span class="version-badge" title="Номер версии по количеству коммитов в ветке">{html.escape(APP_VERSION_LABEL)}</span>
                {mode_picker_block}
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
                    <div class="view-head">
                        <span class="eyebrow">Обзор</span>
                        <h2>Статус и сервис</h2>
                        <p class="section-subtitle">Связь, активный режим и сервисные действия собраны в одном месте.</p>
                    </div>
                    <div class="status-dashboard">
                        <div class="status-card status-card-wide">
                            <div class="status-card-top">
                                <span class="card-icon">{_telegram_icon_html(opacity=1.0)}</span>
                                <div class="status-copy">
                                    <span class="status-label">Telegram API</span>
                                    <span class="status-value" id="web-api-status">{html.escape(status['api_status'])}</span>
                                    {socks_block}
                                    {fallback_block}
                                </div>
                                <span class="status-dot"></span>
                            </div>
                        </div>
                        <div class="status-card">
                            <div class="status-card-top">
                                <span class="card-icon">◇</span>
                                <div class="status-copy">
                                    <span class="status-label">Активный режим</span>
                                    <span class="status-value" id="current-mode-label">{html.escape(current_mode_label)}</span>
                                    <p class="status-note">Списки обхода: <span id="list-route-label">{html.escape(list_route_label)}</span></p>
                                </div>
                            </div>
                        </div>
                        {key_pool_status_card}
                        <div class="status-card">
                            <div class="status-card-top">
                                <span class="card-icon">↗</span>
                                <div class="status-copy">
                                    <span class="status-label">Быстрый старт</span>
                                    <p class="status-note">{html.escape(quick_start_note)}</p>
                                </div>
                            </div>
                            <form method="post" action="/start"{start_form_async_attr}>
                                {csrf_input_html}
                                <button type="submit">{start_button_label}</button>
                            </form>
                        </div>
                    </div>
                    <div class="overview-service-grid">
                        <section class="panel service-panel service-panel-wide">
                            <h3>Сервисные команды</h3>
                            <div class="app-mode-control">
                                <button type="button" id="app-mode-toggle-button" class="mode-toggle app-mode-command" onclick="toggleAppModePicker()">
                                    <span>Режим работы программы:</span>
                                    <span id="app-mode-label">{html.escape(app_runtime_mode_label)}</span>
                                </button>
                                {app_runtime_mode_picker_block}
                            </div>
                            <div class="command-grid">{command_buttons_html}</div>
                        </section>
                    </div>
                    <section class="panel overview-key-panel">
                        <div class="workspace-head">
                            <div>
                                <span class="eyebrow">Ключ текущего режима</span>
                                <h2>{html.escape(quick_key_label)}</h2>
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
                        <span class="eyebrow">Ключи</span>
                        <h2>Подключения по протоколам</h2>
                        <p class="section-subtitle">{keys_view_subtitle}</p>
                    </div>
                    <div class="segmented protocol-tabs">{protocol_tabs_html}</div>
                    <div class="protocol-panels">{protocol_panels_html}</div>
                </section>

                <section class="app-view" data-view="lists">
                    <div class="view-head">
                        <span class="eyebrow">Маршрутизация</span>
                        <h2>Списки обхода</h2>
                        <p class="section-subtitle">Домены из выбранного списка будут отправляться через соответствующий протокол.</p>
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
                <p id="confirm-message">Подтвердите действие.</p>
                <div class="confirm-actions">
                    <button type="button" id="confirm-cancel" class="secondary-button">Отмена</button>
                    <button type="button" id="confirm-accept" class="danger">Подтвердить</button>
                </div>
            </div>
        </div>
    </div>
</body>
</html>'''
