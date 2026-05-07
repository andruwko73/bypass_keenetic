import html
from web_template_styles import render_web_styles


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
    update_buttons_html,
    enable_async_forms=True,
    enable_custom_checks=True,
    enable_key_pool=True,
    enable_live_status=True,
):
    enable_async_forms_js = 'true' if enable_async_forms else 'false'
    enable_custom_checks_js = 'true' if enable_custom_checks else 'false'
    enable_key_pool_js = 'true' if enable_key_pool else 'false'
    enable_live_status_js = 'true' if enable_live_status else 'false'
    start_form_async_attr = ' data-async-action="start"' if enable_async_forms else ''
    quick_install_async_attr = ' data-async-action="install"' if enable_async_forms else ''
    pool_probe_async_attr = ' data-async-action="pool-probe"' if enable_async_forms else ''
    csrf_input_html = f'<input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}">'
    custom_checks_json = custom_checks_json if enable_custom_checks else '[]'
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
    web_styles = render_web_styles()
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
        const INITIAL_STATUS_PENDING = {initial_status_pending};
        const INITIAL_COMMAND_RUNNING = {initial_command_running};
        const ENABLE_ASYNC_FORMS = {enable_async_forms_js};
        const ENABLE_CUSTOM_CHECKS = {enable_custom_checks_js};
        const ENABLE_KEY_POOL = {enable_key_pool_js};
        const ENABLE_LIVE_STATUS = {enable_live_status_js};
        const POOL_PROBE_POLL_EXTENSION_MS = {POOL_PROBE_UI_POLL_EXTENSION_MS};
        const TELEGRAM_ICON_SRC = 'data:image/svg+xml;base64,{TELEGRAM_SVG_B64}';
        const YOUTUBE_ICON_SRC = 'data:image/svg+xml;base64,{YOUTUBE_SVG_B64}';
        const SERVICE_ICON_BASE = '/static/service-icons/';
        const CSRF_TOKEN = '{html.escape(csrf_token)}';
        let customChecks = ENABLE_CUSTOM_CHECKS ? {custom_checks_json} : [];
        const PROTOCOL_LABELS = {{
            none: 'Без прокси',
            shadowsocks: 'Shadowsocks',
            vmess: 'Vmess',
            vless: 'Vless 1',
            vless2: 'Vless 2',
            trojan: 'Trojan'
        }};
        let statusPollTimer = null;
        let statusPollUntil = 0;
        let commandPollTimer = null;

        (function() {{
            const savedTheme = localStorage.getItem('router-theme');
            const theme = savedTheme === 'light' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', theme);
        }})();

        function toggleTheme() {{
            const root = document.documentElement;
            const nextTheme = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
            root.setAttribute('data-theme', nextTheme);
            localStorage.setItem('router-theme', nextTheme);
            const label = document.getElementById('theme-toggle-label');
            if (label) {{
                label.textContent = nextTheme === 'light' ? 'Светлая тема' : 'Темная тема';
            }}
        }}

        function toggleModePicker() {{
            const picker = document.getElementById('mode-picker');
            if (!picker) {{
                return;
            }}
            picker.classList.toggle('hidden');
        }}

        function escapeHtml(value) {{
            return String(value || '').replace(/[&<>"']/g, function(char) {{
                return {{
                    '&': '&amp;',
                    '<': '&lt;',
                    '>': '&gt;',
                    '"': '&quot;',
                    "'": '&#39;'
                }}[char];
            }});
        }}

        function setupViewNavigation() {{
            const targets = document.querySelectorAll('[data-view-target]');
            function activate(view) {{
                let selected = view || 'status';
                if (selected === 'service' || !document.querySelector('[data-view="' + selected + '"]')) {{
                    selected = 'status';
                }}
                document.querySelectorAll('[data-view]').forEach(function(panel) {{
                    panel.classList.toggle('active', panel.dataset.view === selected);
                }});
                targets.forEach(function(button) {{
                    button.classList.toggle('active', button.dataset.viewTarget === selected);
                }});
            }}
            targets.forEach(function(button) {{
                button.addEventListener('click', function() {{
                    activate(button.dataset.viewTarget);
                }});
            }});
            localStorage.removeItem('router-active-view');
            activate('status');
        }}

        function setupSegmentedTabs(buttonSelector, panelSelector, targetAttribute, panelAttribute, storageKey) {{
            const buttons = document.querySelectorAll(buttonSelector);
            function activate(value) {{
                let selected = value || localStorage.getItem(storageKey) || (buttons[0] ? buttons[0].getAttribute(targetAttribute) : '');
                if (selected && !Array.from(buttons).some(function(button) {{ return button.getAttribute(targetAttribute) === selected; }})) {{
                    selected = buttons[0] ? buttons[0].getAttribute(targetAttribute) : '';
                }}
                buttons.forEach(function(button) {{
                    button.classList.toggle('active', button.getAttribute(targetAttribute) === selected);
                }});
                document.querySelectorAll(panelSelector).forEach(function(panel) {{
                    panel.classList.toggle('active', panel.getAttribute(panelAttribute) === selected);
                }});
                if (selected) {{
                    localStorage.setItem(storageKey, selected);
                }}
            }}
            buttons.forEach(function(button) {{
                button.addEventListener('click', function() {{
                    activate(button.getAttribute(targetAttribute));
                }});
            }});
            activate(localStorage.getItem(storageKey));
        }}

        function setupProtocolSubtabs() {{
            document.querySelectorAll('[data-protocol-panel]').forEach(function(panel) {{
                const buttons = panel.querySelectorAll('[data-subview-target]');
                function activate(value) {{
                    const selected = value || 'key';
                    buttons.forEach(function(button) {{
                        button.classList.toggle('active', button.dataset.subviewTarget === selected);
                    }});
                    panel.querySelectorAll('[data-subview]').forEach(function(subview) {{
                        subview.classList.toggle('active', subview.dataset.subview === selected);
                    }});
                }}
                buttons.forEach(function(button) {{
                    button.addEventListener('click', function() {{
                        activate(button.dataset.subviewTarget);
                    }});
                }});
                activate('key');
            }});
        }}

        function setOptionalText(id, text) {{
            const element = document.getElementById(id);
            if (!element) {{
                return;
            }}
            const value = text || '';
            element.textContent = value;
            element.classList.toggle('hidden', !value);
        }}

        function serviceIcon(src, alt) {{
            return '<img class="service-icon-img" src="' + src + '" width="16" height="16" alt="' + alt + '" style="vertical-align:middle;opacity:1">';
        }}

        function protocolIcons(status) {{
            let html = '';
            if (status && status.api_ok) {{
                html += serviceIcon(TELEGRAM_ICON_SRC, 'Telegram');
            }}
            if (status && status.yt_ok) {{
                html += serviceIcon(YOUTUBE_ICON_SRC, 'YouTube');
            }}
            if (status && status.custom) {{
                customChecks.forEach(function(check) {{
                    if (status.custom[check.id] === 'ok') {{
                        html += serviceIcon(serviceIconSrc(check.icon), check.label || 'Service');
                    }}
                }});
            }}
            return html;
        }}

        function probeBadge(state, service) {{
            if (state === 'ok') {{
                return serviceIcon(service === 'tg' ? TELEGRAM_ICON_SRC : YOUTUBE_ICON_SRC, service === 'tg' ? 'Telegram' : 'YouTube');
            }}
            if (state === 'fail') {{
                return '<span class="service-probe-mark service-probe-fail">✕</span>';
            }}
            return '<span class="service-probe-mark service-probe-unknown">?</span>';
        }}

        function customCheckById(id) {{
            for (let i = 0; i < customChecks.length; i += 1) {{
                if (customChecks[i].id === id) {{
                    return customChecks[i];
                }}
            }}
            return null;
        }}

        function customBadge(state, check) {{
            const status = state || 'unknown';
            const label = check ? check.label : 'Проверка';
            const url = check ? check.url : '';
            let content = '?';
            if (status === 'ok' && check && check.icon) {{
                content = serviceIcon(serviceIconSrc(check.icon), label);
            }} else if (status === 'fail') {{
                content = '<span class="service-probe-mark service-probe-fail">✕</span>';
            }} else {{
                content = '<span class="service-probe-mark service-probe-unknown">?</span>';
            }}
            return '<span class="custom-service-slot custom-service-' + status + '" title="' +
                escapeHtml(label + (url ? ': ' + url : '')) + '">' + content + '</span>';
        }}

        function renderCustomBadges(states) {{
            if (!customChecks.length) {{
                return '';
            }}
            return customChecks.map(function(check) {{
                const state = states && states[check.id] ? states[check.id] : 'unknown';
                return customBadge(state, check);
            }}).join('');
        }}

        function customUrlText(check) {{
            const urls = Array.isArray(check.urls) && check.urls.length ? check.urls : [check.url || ''];
            return urls.filter(Boolean).map(function(url) {{
                try {{
                    const parsed = new URL(url);
                    return (parsed.host || url) + (parsed.pathname && parsed.pathname !== '/' ? parsed.pathname : '');
                }} catch (error) {{
                    return url;
                }}
            }}).join(', ');
        }}

        function serviceIconSrc(icon) {{
            const safe = String(icon || '').replace(/[^a-z0-9_-]/gi, '').toLowerCase();
            return safe ? SERVICE_ICON_BASE + safe + '.png' : '';
        }}

        function customIconHtml(check) {{
            if (check && check.icon) {{
                return '<span class="preset-icon"><img src="' + serviceIconSrc(check.icon) + '" width="20" height="20" alt="' + escapeHtml(check.label || 'Service') + '"></span>';
            }}
            return '<span class="custom-service-badge custom-service-neutral">' + escapeHtml((check && check.badge) || 'WEB') + '</span>';
        }}

        function customHeaderIcons() {{
            if (!customChecks.length) {{
                return '';
            }}
            return customChecks.map(function(check) {{
                const label = check.label || 'Service';
                const content = check.icon
                    ? serviceIcon(serviceIconSrc(check.icon), label)
                    : '<span class="custom-service-badge custom-service-neutral">' + escapeHtml(check.badge || 'WEB') + '</span>';
                return '<span class="custom-service-slot custom-service-header" title="' + escapeHtml(label) + '">' + content + '</span>';
            }}).join('');
        }}

        function syncCustomCheckColumns() {{
            const hasChecks = customChecks.length > 0;
            const mobileWidth = Math.max(28, 28 * customChecks.length) + 'px';
            const desktopWidth = (32 * Math.max(1, customChecks.length)) + 'px';
            document.querySelectorAll('.pool-table').forEach(function(table) {{
                table.classList.toggle('has-custom-checks', hasChecks);
                table.style.setProperty('--custom-col-mobile', mobileWidth);
                const customCol = table.querySelector('.pool-col-custom');
                if (customCol) {{
                    customCol.style.width = desktopWidth;
                }}
            }});
        }}

        function renderCustomChecks(checks) {{
            if (!ENABLE_CUSTOM_CHECKS) {{
                return;
            }}
            customChecks = Array.isArray(checks) ? checks : [];
            const html = customChecks.length ? customChecks.map(function(check) {{
                return '<div class="custom-check-item">' +
                    customIconHtml(check) +
                    '<span class="custom-check-copy"><strong>' + escapeHtml(check.label || 'Проверка') + '</strong><small>' + escapeHtml(customUrlText(check)) + '</small></span>' +
                    '<form method="post" action="/custom_check_delete" data-async-action="custom-check-delete" data-confirm-title="Удалить проверку?" data-confirm-message="Удалить дополнительную проверку ' + escapeHtml(check.label || 'Проверка') + '?">' +
                        '<input type="hidden" name="id" value="' + escapeHtml(check.id || '') + '">' +
                        '<button type="submit" class="pool-delete-btn" title="Удалить проверку">Удалить</button>' +
                    '</form>' +
                '</div>';
            }}).join('') : '<div class="custom-check-empty">Дополнительные проверки пока не добавлены.</div>';
            document.querySelectorAll('[data-custom-check-list]').forEach(function(list) {{
                list.innerHTML = html;
                setupAsyncForms(list);
            }});
            const activeIds = customChecks.map(function(check) {{ return check.id; }});
            document.querySelectorAll('[data-custom-preset]').forEach(function(button) {{
                const active = activeIds.indexOf(button.dataset.customPreset) !== -1;
                button.disabled = active;
                button.title = active ? 'Уже добавлено' : 'Добавить проверку';
            }});
            document.querySelectorAll('[data-custom-check-head]').forEach(function(head) {{
                head.innerHTML = customHeaderIcons();
            }});
            syncCustomCheckColumns();
        }}

        function renderPoolBody(proto, pool) {{
            const body = document.querySelector('[data-pool-body="' + proto + '"]');
            if (!body || !pool) {{
                return;
            }}
            const rows = pool.rows || [];
            const tab = document.querySelector('[data-protocol-target="' + proto + '"] .tab-count');
            if (tab) {{
                tab.textContent = String(pool.count || rows.length);
            }}
            if (!rows.length) {{
                body.innerHTML = '<tr class="pool-row pool-empty-row"><td colspan="6">Пул пуст. Добавьте ключи или загрузите subscription.</td></tr>';
                return;
            }}
            body.innerHTML = rows.map(function(row) {{
                const activeClass = row.active ? ' pool-row-active' : '';
                const activeText = row.active ? 'активен' : '';
                const key = escapeHtml(row.key || '');
                return '<tr class="pool-row' + activeClass + '" data-pool-row data-protocol="' + proto + '" data-key-id="' + escapeHtml(row.key_id) + '" data-key="' + key + '">' +
                    '<td class="pool-key-cell">' +
                        '<form method="post" action="/pool_apply" class="pool-apply-form" data-async-action="pool-apply">' +
                            '<input type="hidden" name="type" value="' + proto + '">' +
                            '<input type="hidden" name="key" value="' + key + '">' +
                            '<button type="submit" class="pool-apply-btn" title="Применить этот ключ">' + escapeHtml(row.display_name) + '</button>' +
                        '</form>' +
                        '<span class="pool-mobile-active" data-pool-key-meta data-pool-mobile-active>' + activeText + '</span>' +
                        '<span class="pool-hash">' + escapeHtml(row.key_id) + '</span>' +
                    '</td>' +
                    '<td class="pool-service-cell" data-pool-tg>' + probeBadge(row.tg, 'tg') + '</td>' +
                    '<td class="pool-service-cell" data-pool-yt>' + probeBadge(row.yt, 'yt') + '</td>' +
                    '<td class="pool-custom-cell" data-pool-custom>' + renderCustomBadges(row.custom) + '</td>' +
                    '<td class="pool-checked-cell" data-pool-checked>' + escapeHtml(row.checked_at) + '</td>' +
                    '<td class="pool-actions-cell">' +
                        '<form method="post" action="/pool_delete" class="pool-item-form" data-async-action="pool-delete" data-confirm-title="Удалить ключ?" data-confirm-message="Удалить ключ из пула?">' +
                            '<input type="hidden" name="type" value="' + proto + '">' +
                            '<input type="hidden" name="key" value="' + key + '">' +
                            '<button type="submit" class="pool-delete-btn" title="Удалить ключ из пула">Удалить</button>' +
                        '</form>' +
                    '</td>' +
                '</tr>';
            }}).join('');
            setupAsyncForms(body);
        }}

        function updatePoolRows(proto, pool) {{
            const body = document.querySelector('[data-pool-body="' + proto + '"]');
            if (!body || !pool) {{
                return;
            }}
            const rows = pool.rows || [];
            const tab = document.querySelector('[data-protocol-target="' + proto + '"] .tab-count');
            if (tab) {{
                tab.textContent = String(pool.count || rows.length);
            }}
            body.querySelectorAll('[data-pool-row]').forEach(function(item) {{
                item.classList.remove('pool-row-active');
                const meta = item.querySelector('[data-pool-key-meta]');
                if (meta) {{
                    meta.textContent = '';
                }}
            }});
            rows.forEach(function(row) {{
                const item = body.querySelector('[data-key-id="' + row.key_id + '"]');
                if (!item) {{
                    return;
                }}
                item.classList.toggle('pool-row-active', !!row.active);
                const meta = item.querySelector('[data-pool-key-meta]');
                if (meta) {{
                    meta.textContent = row.active ? 'активен' : '';
                }}
                const tg = item.querySelector('[data-pool-tg]');
                if (tg) {{
                    tg.innerHTML = probeBadge(row.tg, 'tg');
                }}
                const yt = item.querySelector('[data-pool-yt]');
                if (yt) {{
                    yt.innerHTML = probeBadge(row.yt, 'yt');
                }}
                const custom = item.querySelector('[data-pool-custom]');
                if (custom) {{
                    custom.innerHTML = renderCustomBadges(row.custom);
                }}
                const checked = item.querySelector('[data-pool-checked]');
                if (checked) {{
                    checked.textContent = row.checked_at || '';
                }}
            }});
        }}

        function updatePoolStatus(pools) {{
            if (!ENABLE_KEY_POOL) {{
                return;
            }}
            if (!pools) {{
                return;
            }}
            Object.keys(pools).forEach(function(proto) {{
                const rows = (pools[proto] && pools[proto].rows) || [];
                const hasFullKeys = rows.some(function(row) {{ return !!row.key; }});
                if (hasFullKeys || rows.length === 0) {{
                    renderPoolBody(proto, pools[proto]);
                }} else {{
                    updatePoolRows(proto, pools[proto]);
                }}
            }});
        }}

        function updateProtocolStatus(proto, status) {{
            const card = document.querySelector('[data-protocol-card="' + proto + '"]');
            if (!card || !status) {{
                return;
            }}
            const badge = card.querySelector('[data-protocol-status-label]');
            if (badge) {{
                badge.className = 'key-status-badge key-status-' + (status.tone || 'warn');
                badge.innerHTML = status.label || 'Проверяется';
            }}
            const details = card.querySelector('[data-protocol-status-details]');
            if (details) {{
                details.textContent = status.details || '';
            }}
            const icons = card.querySelector('[data-protocol-status-icons]');
            if (icons) {{
                icons.innerHTML = protocolIcons(status);
            }}
        }}

        function poolProbeProgressLabel(scope) {{
            if (scope === 'auto_missing') {{
                return 'Автопроверка непроверенных ключей';
            }}
            if (scope === 'manual_all') {{
                return 'Полная проверка всех ключей';
            }}
            if (scope === 'protocol') {{
                return 'Проверка выбранного пула';
            }}
            return 'Фоновая проверка пула ключей';
        }}

        function updateWebStatus(snapshot) {{
            if (!snapshot || !snapshot.web) {{
                return false;
            }}
            const web = snapshot.web;
            const modeLabel = document.getElementById('current-mode-label');
            if (modeLabel) {{
                modeLabel.textContent = PROTOCOL_LABELS[web.proxy_mode] || web.proxy_mode || 'Без прокси';
            }}
            const modeToggle = document.querySelector('#mode-toggle-button span:last-child');
            if (modeToggle) {{
                modeToggle.textContent = PROTOCOL_LABELS[web.proxy_mode] || web.proxy_mode || 'Без прокси';
            }}
            const apiStatus = document.getElementById('web-api-status');
            if (apiStatus) {{
                apiStatus.textContent = web.api_status || '';
            }}
            const apiPill = document.getElementById('web-api-pill');
            if (apiPill) {{
                const progress = ENABLE_KEY_POOL ? (snapshot.pool_probe_progress || {{}}) : {{}};
                const poolProbeVisible = ENABLE_KEY_POOL && !!snapshot.pool_probe_running && Number(progress.total || 0) > 0;
                const progressLabel = poolProbeProgressLabel(progress.scope || '');
                const progressText = progress.total
                    ? '⏳ ' + progressLabel + ': ' + (progress.checked || 0) + '/' + progress.total + '. Статусы обновятся без перезагрузки страницы.'
                    : '⏳ ' + progressLabel + '. Статусы обновятся без перезагрузки страницы.';
                apiPill.textContent = poolProbeVisible ? progressText : (web.api_status || '');
            }}
            setOptionalText('web-socks-details', web.socks_details || '');
            const fallbackText = web.fallback_reason && web.proxy_mode === 'none'
                ? 'Последняя неудачная попытка прокси: ' + web.fallback_reason
                : '';
            setOptionalText('web-fallback-reason', fallbackText);

            let pending = (web.api_status || '').indexOf('Проверяется связь текущего режима') !== -1 ||
                (web.api_status || '').indexOf('Фоновая проверка') !== -1 ||
                (web.api_status || '').indexOf('перепроверяется') !== -1;
            const protocols = snapshot.protocols || {{}};
            Object.keys(protocols).forEach(function(proto) {{
                const status = protocols[proto];
                updateProtocolStatus(proto, status);
                if (status && status.label === 'Проверяется') {{
                    pending = true;
                }}
            }});
            if (ENABLE_CUSTOM_CHECKS && snapshot.custom_checks) {{
                renderCustomChecks(snapshot.custom_checks);
            }}
            const poolSummary = ENABLE_KEY_POOL ? (snapshot.pool_summary || null) : null;
            if (poolSummary) {{
                const progress = snapshot.pool_probe_progress || {{}};
                let summaryNote = poolSummary.note || '';
                if (!!snapshot.pool_probe_running && Number(progress.total || 0) > 0) {{
                    summaryNote = poolProbeProgressLabel(progress.scope || '') + ': ' + (progress.checked || 0) + '/' + progress.total + '. ' + summaryNote;
                }}
                setOptionalText('pool-active-summary', poolSummary.active_text || '');
                setOptionalText('pool-summary-note', summaryNote);
            }}
            if (ENABLE_KEY_POOL) {{
                updatePoolStatus(snapshot.pools);
            }}
            if (ENABLE_KEY_POOL && !!snapshot.pool_probe_running && Number((snapshot.pool_probe_progress || {{}}).total || 0) > 0) {{
                pending = true;
                statusPollUntil = Math.max(statusPollUntil, Date.now() + POOL_PROBE_POLL_EXTENSION_MS);
            }}
            return pending;
        }}

        function pollStatus() {{
            statusPollTimer = null;
            fetch('/api/status', {{
                headers: {{'Accept': 'application/json'}},
                cache: 'no-store'
            }})
                .then(function(response) {{ return response.json(); }})
                .then(function(payload) {{
                    const pending = updateWebStatus(payload);
                    if (pending) {{
                        statusPollUntil = Math.max(statusPollUntil, Date.now() + 30000);
                    }}
                }})
                .catch(function() {{}})
                .finally(function() {{
                    if (Date.now() < statusPollUntil && !document.hidden) {{
                        statusPollTimer = window.setTimeout(pollStatus, 4000);
                    }}
                }});
        }}

        function scheduleStatusPolling(durationMs) {{
            if (!ENABLE_LIVE_STATUS) {{
                return;
            }}
            statusPollUntil = Math.max(statusPollUntil, Date.now() + durationMs);
            if (!statusPollTimer && !document.hidden) {{
                pollStatus();
            }}
        }}

        function showActionMessage(text, ok) {{
            const block = document.getElementById('web-action-message');
            if (!block) {{
                return;
            }}
            block.classList.remove('hidden');
            block.classList.toggle('notice-status', !!ok);
            block.classList.toggle('notice-result', !ok);
            const title = block.querySelector('strong');
            if (title) {{
                title.textContent = ok ? 'Результат' : 'Ошибка';
            }}
            const output = block.querySelector('.log-output');
            if (output) {{
                output.textContent = text || '';
            }}
        }}

        function showCommandState(state) {{
            const block = document.getElementById('web-command-status');
            if (!block) {{
                return false;
            }}
            if (!state || !state.label) {{
                block.classList.add('hidden');
                return false;
            }}
            block.classList.remove('hidden');
            const title = block.querySelector('strong');
            if (title) {{
                title.textContent = (state.running ? 'Команда выполняется: ' : 'Последняя команда: ') + state.label;
            }}
            const output = block.querySelector('.log-output');
            if (output) {{
                output.textContent = state.result || ('⏳ ' + state.label + ' ещё выполняется. Статус обновится без перезагрузки страницы.');
            }}
            return !!state.running;
        }}

        function pollCommandState() {{
            if (!ENABLE_LIVE_STATUS) {{
                return;
            }}
            commandPollTimer = null;
            fetch('/api/command_state', {{
                headers: {{'Accept': 'application/json'}},
                cache: 'no-store'
            }})
                .then(function(response) {{ return response.json(); }})
                .then(function(payload) {{
                    if (showCommandState(payload)) {{
                        commandPollTimer = window.setTimeout(pollCommandState, 4000);
                    }} else {{
                        scheduleStatusPolling(30000);
                    }}
                }})
                .catch(function() {{
                    commandPollTimer = window.setTimeout(pollCommandState, 6000);
                }});
        }}

        function markProtocolPending(proto, text) {{
            const card = document.querySelector('[data-protocol-card="' + proto + '"]');
            if (!card) {{
                return;
            }}
            const badge = card.querySelector('[data-protocol-status-label]');
            if (badge) {{
                badge.className = 'key-status-badge key-status-warn';
                badge.textContent = 'Проверяется';
            }}
            const details = card.querySelector('[data-protocol-status-details]');
            if (details) {{
                details.textContent = text || 'Проверка Telegram API, YouTube и дополнительных сервисов выполняется в фоне.';
            }}
            const icons = card.querySelector('[data-protocol-status-icons]');
            if (icons) {{
                icons.innerHTML = '';
            }}
        }}

        function markPoolKeyActive(proto, key) {{
            document.querySelectorAll('[data-pool-row]').forEach(function(item) {{
                if (item.dataset.protocol !== proto) {{
                    return;
                }}
                const isActive = item.dataset.key === key;
                item.classList.toggle('pool-row-active', isActive);
                const meta = item.querySelector('[data-pool-key-meta]');
                if (meta) {{
                    meta.textContent = isActive ? 'активен' : '';
                }}
                const mobileMeta = item.querySelector('[data-pool-mobile-active]');
                if (mobileMeta) {{
                    mobileMeta.textContent = meta ? meta.textContent : '';
                }}
            }});
        }}

        function setButtonBusy(button, busy) {{
            if (!button) {{
                return;
            }}
            if (busy) {{
                button.dataset.originalText = button.textContent;
                button.disabled = true;
                button.textContent = 'Выполняется...';
            }} else {{
                button.disabled = false;
                if (button.dataset.originalText) {{
                    button.textContent = button.dataset.originalText;
                    delete button.dataset.originalText;
                }}
            }}
        }}

        function confirmAction(title, message) {{
            if (!title && !message) {{
                return Promise.resolve(true);
            }}
            const modal = document.getElementById('confirm-modal');
            const titleNode = document.getElementById('confirm-title');
            const messageNode = document.getElementById('confirm-message');
            const cancelButton = document.getElementById('confirm-cancel');
            const acceptButton = document.getElementById('confirm-accept');
            if (!modal || !cancelButton || !acceptButton) {{
                return Promise.resolve(window.confirm(message || title || 'Подтвердить действие?'));
            }}
            titleNode.textContent = title || 'Подтверждение';
            messageNode.textContent = message || 'Подтвердите действие.';
            modal.classList.remove('hidden');
            return new Promise(function(resolve) {{
                function cleanup(result) {{
                    modal.classList.add('hidden');
                    cancelButton.removeEventListener('click', onCancel);
                    acceptButton.removeEventListener('click', onAccept);
                    modal.removeEventListener('click', onBackdrop);
                    resolve(result);
                }}
                function onCancel() {{ cleanup(false); }}
                function onAccept() {{ cleanup(true); }}
                function onBackdrop(event) {{
                    if (event.target === modal) {{
                        cleanup(false);
                    }}
                }}
                cancelButton.addEventListener('click', onCancel);
                acceptButton.addEventListener('click', onAccept);
                modal.addEventListener('click', onBackdrop);
            }});
        }}

        function setupAsyncForms(root) {{
            if (!ENABLE_ASYNC_FORMS) {{
                return;
            }}
            const scope = root || document;
            scope.querySelectorAll('form[data-async-action]').forEach(function(form) {{
                let csrfInput = form.querySelector('input[name="csrf_token"]');
                if (!csrfInput) {{
                    csrfInput = document.createElement('input');
                    csrfInput.type = 'hidden';
                    csrfInput.name = 'csrf_token';
                    form.appendChild(csrfInput);
                }}
                csrfInput.value = CSRF_TOKEN;
                if (form.dataset.asyncBound === '1') {{
                    return;
                }}
                form.dataset.asyncBound = '1';
                form.addEventListener('submit', function(event) {{
                    event.preventDefault();
                    const button = event.submitter || form.querySelector('button[type="submit"]');
                    const formData = new FormData(form);
                    formData.set('csrf_token', CSRF_TOKEN);
                    if (button && button.name) {{
                        formData.append(button.name, button.value || '');
                    }}
                    const action = form.dataset.asyncAction || '';
                    const proto = formData.get('type') || '';
                    const key = formData.get('key') || '';
                    const confirmTitle = (button && button.dataset.confirmTitle) || form.dataset.confirmTitle || '';
                    const confirmMessage = (button && button.dataset.confirmMessage) || form.dataset.confirmMessage || '';
                    const actionUrl = (button && button.getAttribute('formaction')) || form.getAttribute('action');
                    confirmAction(confirmTitle, confirmMessage).then(function(confirmed) {{
                        if (!confirmed) {{
                            return;
                        }}
                        setButtonBusy(button, true);
                        if (proto && (action === 'install' || action === 'pool-apply' || action === 'pool-probe')) {{
                            markProtocolPending(proto);
                        }}
                        showActionMessage('⏳ Выполняется действие. Страница останется на месте.', true);
                        const requestBody = new URLSearchParams();
                        formData.forEach(function(value, name) {{
                            requestBody.append(name, value);
                        }});
                        fetch(actionUrl, {{
                        method: 'POST',
                        body: requestBody,
                        headers: {{
                            'Accept': 'application/json',
                            'X-Requested-With': 'fetch',
                            'X-CSRF-Token': CSRF_TOKEN,
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
                        }},
                        cache: 'no-store'
                    }})
                        .then(function(response) {{
                            return response.json().then(function(payload) {{
                                payload._responseOk = response.ok;
                                return payload;
                            }});
                        }})
                        .then(function(payload) {{
                            const ok = payload._responseOk && payload.ok !== false;
                            showActionMessage(payload.result || 'Готово.', ok);
                            if (ok && proto && action === 'install') {{
                                const card = form.closest('[data-protocol-card]');
                                const textarea = card ? card.querySelector('[data-key-textarea]') : null;
                                if (textarea) {{
                                    textarea.value = key;
                                }}
                            }}
                            if (ok && proto && action === 'pool-apply') {{
                                markPoolKeyActive(proto, key);
                                const card = form.closest('[data-protocol-card]');
                                const textarea = card ? card.querySelector('[data-key-textarea]') : null;
                                if (textarea) {{
                                    textarea.value = key;
                                }}
                            }}
                            if (payload.custom_checks) {{
                                renderCustomChecks(payload.custom_checks);
                            }}
                            if (payload.pools) {{
                                updatePoolStatus(payload.pools);
                            }}
                            if (payload.list_name && typeof payload.list_content === 'string') {{
                                const listPanel = document.querySelector('[data-list-panel="' + payload.list_name + '"]');
                                const listTextarea = listPanel ? listPanel.querySelector('textarea[name="content"]') : null;
                                if (listTextarea) {{
                                    listTextarea.value = payload.list_content;
                                }}
                            }}
                            if (action === 'set-proxy') {{
                                const picker = document.getElementById('mode-picker');
                                if (picker) {{
                                    picker.classList.add('hidden');
                                }}
                                const selectedMode = String(formData.get('proxy_type') || '');
                                const selectedLabel = payload.proxy_label || PROTOCOL_LABELS[selectedMode] || selectedMode || 'Без прокси';
                                document.querySelectorAll('.mode-choice').forEach(function(choice) {{
                                    choice.classList.toggle('active', choice.dataset.modeValue === selectedMode);
                                }});
                                const modeToggle = document.querySelector('#mode-toggle-button span:last-child');
                                if (modeToggle) {{
                                    modeToggle.textContent = selectedLabel;
                                }}
                                const currentMode = document.getElementById('current-mode-label');
                                if (currentMode) {{
                                    currentMode.textContent = selectedLabel;
                                }}
                            }}
                            if (action === 'command') {{
                                showCommandState(payload.command_state);
                                if (!commandPollTimer) {{
                                    pollCommandState();
                                }}
                                scheduleStatusPolling(120000);
                            }} else {{
                                scheduleStatusPolling(70000);
                            }}
                        }})
                        .catch(function(error) {{
                            showActionMessage('Ошибка запроса: ' + error, false);
                        }})
                        .finally(function() {{
                            setButtonBusy(button, false);
                        }});
                    }});
                }});
            }});
        }}

        document.addEventListener('DOMContentLoaded', function() {{
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
            const label = document.getElementById('theme-toggle-label');
            if (label) {{
                label.textContent = currentTheme === 'light' ? 'Светлая тема' : 'Темная тема';
            }}
            document.addEventListener('click', function(event) {{
                const picker = document.getElementById('mode-picker');
                const toggle = document.getElementById('mode-toggle-button');
                if (!picker || !toggle) {{
                    return;
                }}
                if (picker.classList.contains('hidden')) {{
                    return;
                }}
                if (!picker.contains(event.target) && !toggle.contains(event.target)) {{
                    picker.classList.add('hidden');
                }}
            }});
            document.addEventListener('visibilitychange', function() {{
                if (!document.hidden) {{
                    scheduleStatusPolling(30000);
                }}
            }});
            setupViewNavigation();
            setupSegmentedTabs('.protocol-tab', '[data-protocol-panel]', 'data-protocol-target', 'data-protocol-panel', 'router-active-protocol');
            setupSegmentedTabs('.list-tab', '[data-list-panel]', 'data-list-target', 'data-list-panel', 'router-active-list');
            setupProtocolSubtabs();
            setupAsyncForms();
            if (INITIAL_STATUS_PENDING) {{
                scheduleStatusPolling(POOL_PROBE_POLL_EXTENSION_MS);
            }}
            if (INITIAL_COMMAND_RUNNING) {{
                pollCommandState();
            }}
        }});
    </script>
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
                        <section class="panel service-panel">
                            <h3>Переустановка компонентов</h3>
                            <div class="command-grid">{update_buttons_html}</div>
                        </section>
                        <section class="panel service-panel">
                            <h3>Сервисные команды</h3>
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
                        <span class="eyebrow">Ключи и мосты</span>
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
