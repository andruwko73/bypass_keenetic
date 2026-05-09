import html


def render_web_scripts(
    POOL_PROBE_UI_POLL_EXTENSION_MS,
    TELEGRAM_SVG_B64,
    YOUTUBE_SVG_B64,
    csrf_token,
    custom_checks_json,
    initial_command_running,
    initial_status_pending,
    enable_async_forms=True,
    enable_custom_checks=True,
    enable_key_pool=True,
    enable_live_status=True,
):
    enable_async_forms_js = 'true' if enable_async_forms else 'false'
    enable_custom_checks_js = 'true' if enable_custom_checks else 'false'
    enable_key_pool_js = 'true' if enable_key_pool else 'false'
    enable_live_status_js = 'true' if enable_live_status else 'false'
    custom_checks_json = custom_checks_json if enable_custom_checks else '[]'
    return f'''        const INITIAL_STATUS_PENDING = {initial_status_pending};
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
        let actionMessageTimer = null;
        let activeCommandName = '';

        const THEME_LABELS = {{
            dark: 'Темная',
            light: 'Светлая',
            glass: 'Liquid Glass'
        }};

        function normalizeTheme(value) {{
            return Object.prototype.hasOwnProperty.call(THEME_LABELS, value) ? value : 'dark';
        }}

        function updateThemeControls(theme) {{
            const currentTheme = normalizeTheme(theme || document.documentElement.getAttribute('data-theme'));
            const label = document.getElementById('theme-toggle-label');
            if (label) {{
                label.textContent = THEME_LABELS[currentTheme];
            }}
            document.querySelectorAll('[data-theme-choice]').forEach(function(button) {{
                button.classList.toggle('active', button.dataset.themeChoice === currentTheme);
            }});
        }}

        (function() {{
            const theme = normalizeTheme(localStorage.getItem('router-theme'));
            document.documentElement.setAttribute('data-theme', theme);
        }})();

        function setTheme(theme) {{
            const nextTheme = normalizeTheme(theme);
            document.documentElement.setAttribute('data-theme', nextTheme);
            localStorage.setItem('router-theme', nextTheme);
            updateThemeControls(nextTheme);
            const picker = document.getElementById('theme-picker');
            if (picker) {{
                picker.classList.add('hidden');
            }}
        }}

        function toggleTheme() {{
            const currentTheme = normalizeTheme(document.documentElement.getAttribute('data-theme'));
            const order = ['dark', 'light', 'glass'];
            const nextTheme = order[(order.indexOf(currentTheme) + 1) % order.length];
            setTheme(nextTheme);
        }}

        function toggleThemePicker() {{
            const picker = document.getElementById('theme-picker');
            if (!picker) {{
                return;
            }}
            const modePicker = document.getElementById('mode-picker');
            if (modePicker) {{
                modePicker.classList.add('hidden');
            }}
            const appPicker = document.getElementById('app-mode-picker');
            if (appPicker) {{
                appPicker.classList.add('hidden');
            }}
            picker.classList.toggle('hidden');
            updateThemeControls();
        }}

        function setupLiquidPointer() {{
            if (document.body.dataset.liquidPointerReady === '1') {{
                return;
            }}
            document.body.dataset.liquidPointerReady = '1';
            const selectors = [
                'button',
                '.nav-item',
                '.seg-tab',
                '.subtab',
                '.topbar-actions',
                '.api-pill',
                '.version-badge',
                '.mode-choice',
                '.theme-toggle',
                '.mode-toggle'
            ].join(',');
            const fadeTimers = new WeakMap();
            let activeElement = null;
            let lensTimer = null;
            let liquidMoveFrame = 0;
            let pendingLiquidMove = null;
            let lastLensPoint = null;
            let lensTarget = null;
            let lensCurrent = null;
            let lensRenderFrame = 0;
            const globalLens = document.createElement('div');
            globalLens.className = 'liquid-global-lens';
            globalLens.setAttribute('aria-hidden', 'true');
            document.body.appendChild(globalLens);

            function glassThemeActive() {{
                return document.documentElement.getAttribute('data-theme') === 'glass';
            }}

            function hideGlobalLens(delay) {{
                if (lensTimer) {{
                    clearTimeout(lensTimer);
                    lensTimer = null;
                }}
                lensTimer = window.setTimeout(function() {{
                    globalLens.classList.remove('liquid-global-lens-active');
                    globalLens.style.removeProperty('--lr');
                    globalLens.style.removeProperty('--lsx');
                    globalLens.style.removeProperty('--lsy');
                    lensTarget = null;
                    lensCurrent = null;
                    if (lensRenderFrame) {{
                        window.cancelAnimationFrame(lensRenderFrame);
                        lensRenderFrame = 0;
                    }}
                    lastLensPoint = null;
                }}, typeof delay === 'number' ? delay : 180);
            }}

            function renderLiquidLens() {{
                lensRenderFrame = 0;
                if (!lensTarget || !glassThemeActive() || !globalLens.classList.contains('liquid-global-lens-active')) {{
                    return;
                }}
                if (!lensCurrent) {{
                    lensCurrent = {{ x: lensTarget.x, y: lensTarget.y }};
                }}
                const dx = lensTarget.x - lensCurrent.x;
                const dy = lensTarget.y - lensCurrent.y;
                const distance = Math.sqrt(dx * dx + dy * dy);
                const follow = distance > 90 ? 0.68 : 0.52;
                if (distance < 0.45) {{
                    lensCurrent.x = lensTarget.x;
                    lensCurrent.y = lensTarget.y;
                }} else {{
                    lensCurrent.x += dx * follow;
                    lensCurrent.y += dy * follow;
                }}
                globalLens.style.setProperty('--lx', lensCurrent.x.toFixed(1) + 'px');
                globalLens.style.setProperty('--ly', lensCurrent.y.toFixed(1) + 'px');
                if (Math.abs(lensTarget.x - lensCurrent.x) > 0.45 || Math.abs(lensTarget.y - lensCurrent.y) > 0.45) {{
                    lensRenderFrame = window.requestAnimationFrame(renderLiquidLens);
                }}
            }}

            function queueLiquidLensRender() {{
                if (!lensRenderFrame) {{
                    lensRenderFrame = window.requestAnimationFrame(renderLiquidLens);
                }}
            }}

            function moveGlobalLens(clientX, clientY, holdMs) {{
                if (!glassThemeActive()) {{
                    hideGlobalLens(0);
                    return;
                }}
                if (lensTimer) {{
                    clearTimeout(lensTimer);
                    lensTimer = null;
                }}
                const now = window.performance ? window.performance.now() : Date.now();
                if (lastLensPoint) {{
                    const dx = clientX - lastLensPoint.x;
                    const dy = clientY - lastLensPoint.y;
                    const dt = Math.max(now - lastLensPoint.t, 16);
                    const distance = Math.sqrt(dx * dx + dy * dy);
                    const speed = Math.min(distance / dt, 1.8);
                    const stretch = 1 + Math.min(speed * 0.13, 0.18);
                    const squeeze = 1 - Math.min(speed * 0.045, 0.06);
                    if (distance > 0.5) {{
                        globalLens.style.setProperty('--lr', Math.atan2(dy, dx).toFixed(4) + 'rad');
                    }}
                    globalLens.style.setProperty('--lsx', stretch.toFixed(3));
                    globalLens.style.setProperty('--lsy', squeeze.toFixed(3));
                }} else {{
                    globalLens.style.setProperty('--lr', '0rad');
                    globalLens.style.setProperty('--lsx', '1');
                    globalLens.style.setProperty('--lsy', '1');
                }}
                lastLensPoint = {{ x: clientX, y: clientY, t: now }};
                lensTarget = {{ x: clientX, y: clientY }};
                if (!lensCurrent) {{
                    lensCurrent = {{ x: clientX, y: clientY }};
                    globalLens.style.setProperty('--lx', clientX.toFixed(1) + 'px');
                    globalLens.style.setProperty('--ly', clientY.toFixed(1) + 'px');
                }}
                globalLens.classList.add('liquid-global-lens-active');
                queueLiquidLensRender();
                lensTimer = window.setTimeout(function() {{
                    hideGlobalLens(160);
                }}, holdMs || 420);
            }}

            function setLiquidPosition(element, clientX, clientY) {{
                const rect = element.getBoundingClientRect();
                if (!rect.width || !rect.height) {{
                    return false;
                }}
                element.style.setProperty('--mx', (((clientX - rect.left) / rect.width) * 100).toFixed(2) + '%');
                element.style.setProperty('--my', (((clientY - rect.top) / rect.height) * 100).toFixed(2) + '%');
                return true;
            }}

            function clearLiquid(element, delay) {{
                if (!element) {{
                    return;
                }}
                const previousTimer = fadeTimers.get(element);
                if (previousTimer) {{
                    clearTimeout(previousTimer);
                }}
                if (delay === 0) {{
                    element.classList.remove('liquid-active');
                    element.style.removeProperty('--mx');
                    element.style.removeProperty('--my');
                    fadeTimers.delete(element);
                    return;
                }}
                const timer = setTimeout(function() {{
                    element.classList.remove('liquid-active');
                    element.style.removeProperty('--mx');
                    element.style.removeProperty('--my');
                    fadeTimers.delete(element);
                }}, typeof delay === 'number' ? delay : 180);
                fadeTimers.set(element, timer);
            }}

            function activateLiquid(element, clientX, clientY, holdMs) {{
                if (!element || !setLiquidPosition(element, clientX, clientY)) {{
                    return;
                }}
                if (activeElement && activeElement !== element) {{
                    clearLiquid(activeElement, 0);
                }}
                activeElement = element;
                const previousTimer = fadeTimers.get(element);
                if (previousTimer) {{
                    clearTimeout(previousTimer);
                    fadeTimers.delete(element);
                }}
                element.classList.add('liquid-active');
                const timer = setTimeout(function() {{
                    clearLiquid(element, 120);
                }}, holdMs || 360);
                fadeTimers.set(element, timer);
            }}

            function findLiquidElement(clientX, clientY) {{
                const target = document.elementFromPoint(clientX, clientY);
                if (!target) {{
                    return null;
                }}
                const popoverElement = target.closest('.hero-popover [data-liquid="true"]');
                if (popoverElement) {{
                    return popoverElement;
                }}
                return target.closest('[data-liquid-group="true"]') || target.closest('[data-liquid="true"]');
            }}

            function activateFromPoint(clientX, clientY, holdMs) {{
                const nextElement = findLiquidElement(clientX, clientY);
                if (activeElement && activeElement !== nextElement) {{
                    clearLiquid(activeElement, 0);
                }}
                if (nextElement) {{
                    activateLiquid(nextElement, clientX, clientY, holdMs);
                    moveGlobalLens(clientX, clientY, holdMs);
                }} else {{
                    activeElement = null;
                    hideGlobalLens(160);
                }}
            }}

            function queueActivateFromPoint(clientX, clientY, holdMs) {{
                pendingLiquidMove = {{
                    clientX: clientX,
                    clientY: clientY,
                    holdMs: holdMs
                }};
                if (liquidMoveFrame) {{
                    return;
                }}
                liquidMoveFrame = window.requestAnimationFrame(function() {{
                    const point = pendingLiquidMove;
                    pendingLiquidMove = null;
                    liquidMoveFrame = 0;
                    if (point) {{
                        activateFromPoint(point.clientX, point.clientY, point.holdMs);
                    }}
                }});
            }}

            function cancelQueuedLiquidMove() {{
                pendingLiquidMove = null;
                if (liquidMoveFrame) {{
                    window.cancelAnimationFrame(liquidMoveFrame);
                    liquidMoveFrame = 0;
                }}
            }}

            function attach(element) {{
                if (!element || element.dataset.liquidReady === '1') {{
                    return;
                }}
                element.dataset.liquid = 'true';
                element.dataset.liquidReady = '1';
                if (element.classList.contains('topbar-actions')) {{
                    element.dataset.liquidGroup = 'true';
                }}
                element.addEventListener('focus', function() {{
                    const rect = element.getBoundingClientRect();
                    activateLiquid(element, rect.left + rect.width / 2, rect.top + rect.height / 2, 420);
                    moveGlobalLens(rect.left + rect.width / 2, rect.top + rect.height / 2, 420);
                }});
                element.addEventListener('blur', function() {{
                    clearLiquid(element, 0);
                    hideGlobalLens(0);
                }});
            }}

            function scan(root) {{
                const scope = root && root.querySelectorAll ? root : document;
                scope.querySelectorAll(selectors).forEach(attach);
                if (root && root.matches && root.matches(selectors)) {{
                    attach(root);
                }}
            }}
            scan(document);
            if (window.MutationObserver) {{
                const observer = new MutationObserver(function(records) {{
                    records.forEach(function(record) {{
                        record.addedNodes.forEach(function(node) {{
                            if (node.nodeType === 1) {{
                                scan(node);
                            }}
                        }});
                    }});
                }});
                observer.observe(document.body, {{ childList: true, subtree: true }});
            }}
            document.addEventListener('pointermove', function(event) {{
                queueActivateFromPoint(event.clientX, event.clientY, event.pointerType === 'touch' ? 440 : 280);
            }}, {{ passive: true }});
            document.addEventListener('pointerdown', function(event) {{
                activateFromPoint(event.clientX, event.clientY, 480);
            }}, {{ passive: true }});
            document.addEventListener('pointerup', function() {{
                cancelQueuedLiquidMove();
                clearLiquid(activeElement, 260);
                hideGlobalLens(260);
                activeElement = null;
            }}, {{ passive: true }});
            document.addEventListener('pointercancel', function() {{
                cancelQueuedLiquidMove();
                clearLiquid(activeElement, 120);
                hideGlobalLens(120);
                activeElement = null;
            }}, {{ passive: true }});
            document.addEventListener('touchstart', function(event) {{
                if (event.touches && event.touches.length) {{
                    const touch = event.touches[0];
                    activateFromPoint(touch.clientX, touch.clientY, 360);
                }}
            }}, {{ passive: true }});
            document.addEventListener('touchmove', function(event) {{
                if (event.touches && event.touches.length) {{
                    const touch = event.touches[0];
                    queueActivateFromPoint(touch.clientX, touch.clientY, 260);
                }}
            }}, {{ passive: true }});
            document.addEventListener('touchend', function() {{
                cancelQueuedLiquidMove();
                clearLiquid(activeElement, 120);
                hideGlobalLens(120);
                activeElement = null;
            }}, {{ passive: true }});
            document.addEventListener('touchcancel', function() {{
                cancelQueuedLiquidMove();
                clearLiquid(activeElement, 80);
                hideGlobalLens(80);
                activeElement = null;
            }}, {{ passive: true }});
        }}

        function toggleModePicker() {{
            const picker = document.getElementById('mode-picker');
            if (!picker) {{
                return;
            }}
            const appPicker = document.getElementById('app-mode-picker');
            if (appPicker) {{
                appPicker.classList.add('hidden');
            }}
            const themePicker = document.getElementById('theme-picker');
            if (themePicker) {{
                themePicker.classList.add('hidden');
            }}
            picker.classList.toggle('hidden');
        }}

        function toggleAppModePicker() {{
            const picker = document.getElementById('app-mode-picker');
            if (!picker) {{
                return;
            }}
            const modePicker = document.getElementById('mode-picker');
            if (modePicker) {{
                modePicker.classList.add('hidden');
            }}
            const themePicker = document.getElementById('theme-picker');
            if (themePicker) {{
                themePicker.classList.add('hidden');
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

        function clearActionMessageTimer() {{
            if (actionMessageTimer) {{
                window.clearTimeout(actionMessageTimer);
                actionMessageTimer = null;
            }}
        }}

        function hideActionMessage() {{
            clearActionMessageTimer();
            const block = document.getElementById('web-action-message');
            if (!block) {{
                return;
            }}
            block.classList.add('hidden');
            const output = block.querySelector('.log-output');
            if (output) {{
                output.textContent = '';
            }}
        }}

        function scheduleActionMessageHide(delayMs) {{
            clearActionMessageTimer();
            actionMessageTimer = window.setTimeout(hideActionMessage, Number(delayMs) || 9000);
        }}

        function showActionMessage(text, ok, options) {{
            const block = document.getElementById('web-action-message');
            if (!block) {{
                return;
            }}
            clearActionMessageTimer();
            options = options || {{}};
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
            if (ok && options.autoHide) {{
                scheduleActionMessageHide(options.delayMs || 9000);
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

        function maybeReloadAfterUpdateCommand(state) {{
            const commandName = (state && state.command) || activeCommandName || '';
            if (commandName !== 'update') {{
                return;
            }}
            if (state && state.running) {{
                return;
            }}
            activeCommandName = '';
            window.setTimeout(function() {{
                window.location.reload();
            }}, 1500);
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
                    const running = showCommandState(payload);
                    if (running) {{
                        scheduleActionMessageHide(2500);
                        commandPollTimer = window.setTimeout(pollCommandState, 4000);
                    }} else {{
                        hideActionMessage();
                        maybeReloadAfterUpdateCommand(payload);
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
                        if (action === 'command' && (confirmTitle || confirmMessage)) {{
                            formData.set('confirm_switch', 'yes');
                        }}
                        if (action === 'command') {{
                            activeCommandName = String(formData.get('command') || '');
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
                            showActionMessage(payload.result || 'Готово.', ok, {{
                                autoHide: ok,
                                delayMs: action === 'command' ? 5000 : 9000
                            }});
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
                            if (action === 'set-app-mode') {{
                                const picker = document.getElementById('app-mode-picker');
                                if (picker) {{
                                    picker.classList.add('hidden');
                                }}
                                const selectedMode = String(formData.get('app_mode') || '');
                                document.querySelectorAll('[data-app-mode-value]').forEach(function(choice) {{
                                    choice.classList.toggle('active', choice.dataset.appModeValue === selectedMode);
                                }});
                                const label = document.getElementById('app-mode-label');
                                if (label && payload.app_mode_label) {{
                                    label.textContent = payload.app_mode_label;
                                }}
                                if (payload.reload_after_ms) {{
                                    window.setTimeout(function() {{
                                        window.location.reload();
                                    }}, Number(payload.reload_after_ms) || 1500);
                                }}
                            }}
                            if (action === 'command') {{
                                if (showCommandState(payload.command_state)) {{
                                    scheduleActionMessageHide(2500);
                                }} else {{
                                    maybeReloadAfterUpdateCommand(payload.command_state);
                                }}
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
            updateThemeControls(currentTheme);
            document.addEventListener('click', function(event) {{
                const picker = document.getElementById('mode-picker');
                const toggle = document.getElementById('mode-toggle-button');
                if (picker && toggle && !picker.classList.contains('hidden') && !picker.contains(event.target) && !toggle.contains(event.target)) {{
                    picker.classList.add('hidden');
                }}
                const appPicker = document.getElementById('app-mode-picker');
                const appToggle = document.getElementById('app-mode-toggle-button');
                if (appPicker && appToggle && !appPicker.classList.contains('hidden') && !appPicker.contains(event.target) && !appToggle.contains(event.target)) {{
                    appPicker.classList.add('hidden');
                }}
                const themePicker = document.getElementById('theme-picker');
                const themeToggle = document.getElementById('theme-toggle-button');
                if (themePicker && themeToggle && !themePicker.classList.contains('hidden') && !themePicker.contains(event.target) && !themeToggle.contains(event.target)) {{
                    themePicker.classList.add('hidden');
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
            setupLiquidPointer();
            setupAsyncForms();
            const actionBlock = document.getElementById('web-action-message');
            if (actionBlock && !actionBlock.classList.contains('hidden')) {{
                scheduleActionMessageHide(9000);
            }}
            if (INITIAL_STATUS_PENDING) {{
                scheduleStatusPolling(POOL_PROBE_POLL_EXTENSION_MS);
            }}
            if (INITIAL_COMMAND_RUNNING) {{
                pollCommandState();
            }}
        }});
'''
