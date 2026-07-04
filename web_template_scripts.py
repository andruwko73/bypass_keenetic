def render_web_scripts(
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
    enable_telegram=True,
):
    return f'''        const APP_CONFIG = window.BK_APP_CONFIG || {{}};
        const INITIAL_STATUS_PENDING = !!APP_CONFIG.initialStatusPending;
        const INITIAL_COMMAND_RUNNING = !!APP_CONFIG.initialCommandRunning;
        const ENABLE_ASYNC_FORMS = APP_CONFIG.enableAsyncForms !== false;
        const ENABLE_CUSTOM_CHECKS = APP_CONFIG.enableCustomChecks !== false;
        const ENABLE_KEY_POOL = APP_CONFIG.enableKeyPool !== false;
        const ENABLE_LIVE_STATUS = APP_CONFIG.enableLiveStatus !== false;
        const ENABLE_TELEGRAM = APP_CONFIG.enableTelegram !== false;
        const STATUS_ACTIVE_POLL_MS = 8000;
        const STATUS_IDLE_POLL_MS = Math.max(30000, Number(APP_CONFIG.statusIdlePollMs || 60000));
        const POOL_PROBE_STATUS_POLL_MS = Math.max(5000, Number(APP_CONFIG.poolProbeStatusPollMs || 10000));
        const POOL_PROBE_POOL_REFRESH_MS = Math.max(10000, Number(APP_CONFIG.poolProbePoolRefreshMs || 15000));
        let botReady = APP_CONFIG.botReady === true;
        const TELEGRAM_ICON_SRC = 'data:image/svg+xml;base64,{TELEGRAM_SVG_B64}';
        const YOUTUBE_ICON_SRC = 'data:image/svg+xml;base64,{YOUTUBE_SVG_B64}';
        const SERVICE_ICON_BASE = '/static/service-icons/';
        const CSRF_TOKEN = String(APP_CONFIG.csrfToken || '');
        let customChecks = ENABLE_CUSTOM_CHECKS && Array.isArray(APP_CONFIG.customChecks) ? APP_CONFIG.customChecks : [];
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
        let poolProbeWasRunning = false;
        let latestPoolProbeProgress = null;
        let poolProbePollTimer = null;
        let poolDataRefreshTimer = null;
        let poolDataRefreshDueAt = 0;
        let poolDataRefreshAll = false;
        const pendingPoolDataProtocols = new Set();
        let poolDataRetryCount = {{}};
        let poolViewTimers = {{}};
        let commandPollTimer = null;
        let commandTimer = null;
        let commandTimerState = null;
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
                'button:not(.pool-delete-btn)',
                '.nav-item',
                '.side-nav',
                '.mobile-nav',
                '.seg-tab',
                '.segmented',
                '.subtab',
                '.subtabs',
                '.mode-choice',
                '.theme-toggle',
                '.mode-toggle'
            ].join(',');
            const fadeTimers = new WeakMap();
            let activeElement = null;
            let liquidActionCooldownUntil = 0;
            let lensTimer = null;
            let liquidMoveFrame = 0;
            let pendingLiquidMove = null;
            let liquidTouchState = null;
            let liquidPointerState = null;
            let liquidSyntheticTarget = null;
            let liquidSyntheticUntil = 0;
            let suppressLiquidFocusUntil = 0;
            const globalLens = document.createElement('div');
            globalLens.className = 'liquid-global-lens';
            globalLens.setAttribute('aria-hidden', 'true');
            document.body.appendChild(globalLens);

            function glassThemeActive() {{
                return document.documentElement.getAttribute('data-theme') === 'glass';
            }}

            function touchLikeInputActive() {{
                return !!(window.matchMedia && window.matchMedia('(hover: none), (pointer: coarse)').matches);
            }}

            function suppressLiquidFocus(ms) {{
                suppressLiquidFocusUntil = Math.max(suppressLiquidFocusUntil, Date.now() + (ms || 600));
            }}

            function shouldAnimateLiquidFocus(element) {{
                if (Date.now() < suppressLiquidFocusUntil) {{
                    return false;
                }}
                if (touchLikeInputActive() && element.matches && !element.matches(':focus-visible')) {{
                    return false;
                }}
                return true;
            }}

            function isLiquidGroupElement(element) {{
                return !!(element && element.classList && (
                    element.classList.contains('mobile-nav') ||
                    element.classList.contains('side-nav') ||
                    element.classList.contains('segmented') ||
                    element.classList.contains('subtabs')
                ));
            }}

            function hideGlobalLens(delay) {{
                if (lensTimer) {{
                    clearTimeout(lensTimer);
                    lensTimer = null;
                }}
                if (typeof delay === 'number' && delay <= 0) {{
                    globalLens.classList.remove('liquid-global-lens-active');
                    return;
                }}
                lensTimer = window.setTimeout(function() {{
                    globalLens.classList.remove('liquid-global-lens-active');
                }}, typeof delay === 'number' ? delay : 180);
            }}

            function clampLiquidLensPoint(clientX, clientY) {{
                const rect = globalLens.getBoundingClientRect();
                const viewport = window.visualViewport || null;
                const viewportWidth = viewport ? viewport.width : window.innerWidth;
                const viewportHeight = viewport ? viewport.height : window.innerHeight;
                const radiusX = Math.max((rect.width || 72) / 2, 30);
                const radiusY = Math.max((rect.height || 72) / 2, 30);
                const margin = 8;
                const minX = radiusX + margin;
                const minY = radiusY + margin;
                const maxX = Math.max(minX, viewportWidth - radiusX - margin);
                const maxY = Math.max(minY, viewportHeight - radiusY - margin);
                return {{
                    x: Math.min(Math.max(clientX, minX), maxX),
                    y: Math.min(Math.max(clientY, minY), maxY)
                }};
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
                const lensPoint = clampLiquidLensPoint(clientX, clientY);
                globalLens.style.setProperty('--lx', lensPoint.x.toFixed(1) + 'px');
                globalLens.style.setProperty('--ly', lensPoint.y.toFixed(1) + 'px');
                globalLens.classList.add('liquid-global-lens-active');
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
                    element.classList.add('liquid-resetting');
                    element.classList.remove('liquid-active');
                    element.style.removeProperty('--mx');
                    element.style.removeProperty('--my');
                    fadeTimers.delete(element);
                    window.requestAnimationFrame(function() {{
                        window.requestAnimationFrame(function() {{
                            element.classList.remove('liquid-resetting');
                        }});
                    }});
                    return;
                }}
                const timer = setTimeout(function() {{
                    element.classList.add('liquid-resetting');
                    element.classList.remove('liquid-active');
                    element.style.removeProperty('--mx');
                    element.style.removeProperty('--my');
                    fadeTimers.delete(element);
                    window.requestAnimationFrame(function() {{
                        element.classList.remove('liquid-resetting');
                    }});
                }}, typeof delay === 'number' ? delay : 180);
                fadeTimers.set(element, timer);
            }}

            function resetLiquidState() {{
                cancelQueuedLiquidMove();
                document.querySelectorAll('[data-liquid].liquid-active').forEach(function(element) {{
                    clearLiquid(element, 0);
                }});
                activeElement = null;
                hideGlobalLens(0);
            }}

            function activateLiquid(element, clientX, clientY, holdMs) {{
                if (!element || !setLiquidPosition(element, clientX, clientY)) {{
                    return;
                }}
                if (activeElement === element && element.classList.contains('liquid-active')) {{
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
                element.classList.remove('liquid-resetting');
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

            function findLiquidAction(clientX, clientY) {{
                const target = document.elementFromPoint(clientX, clientY);
                if (!target) {{
                    return null;
                }}
                const action = target.closest('button[type="button"], a[href], [role="button"]');
                if (!action || action.disabled || action.getAttribute('aria-disabled') === 'true') {{
                    return null;
                }}
                if (action.classList.contains('danger') || action.closest('.danger')) {{
                    return null;
                }}
                return action;
            }}

            function applyLiquidAction(clientX, clientY) {{
                const action = findLiquidAction(clientX, clientY);
                if (!action || !glassThemeActive()) {{
                    return false;
                }}
                liquidSyntheticTarget = action;
                liquidSyntheticUntil = Date.now() + 700;
                liquidActionCooldownUntil = Date.now() + 260;
                suppressLiquidFocus(900);
                action.click();
                if (action.blur) {{
                    action.blur();
                }}
                resetLiquidState();
                return true;
            }}

            function trackLiquidMovement(state, clientX, clientY) {{
                if (!state) {{
                    return;
                }}
                const dx = clientX - state.startX;
                const dy = clientY - state.startY;
                const scrollDx = Math.abs((window.scrollX || window.pageXOffset || 0) - (state.scrollX || 0));
                const scrollDy = Math.abs((window.scrollY || window.pageYOffset || 0) - (state.scrollY || 0));
                state.lastX = clientX;
                state.lastY = clientY;
                if ((scrollDx + scrollDy) > 6) {{
                    state.scrolled = true;
                    resetLiquidState();
                    return;
                }}
                if ((dx * dx + dy * dy) > 144) {{
                    state.moved = true;
                }}
            }}

            function activateFromPoint(clientX, clientY, holdMs) {{
                if (!glassThemeActive()) {{
                    if (activeElement) {{
                        clearLiquid(activeElement, 0);
                        activeElement = null;
                    }}
                    hideGlobalLens(0);
                    return;
                }}
                if (Date.now() < liquidActionCooldownUntil) {{
                    return;
                }}
                const nextElement = findLiquidElement(clientX, clientY);
                if (activeElement && activeElement !== nextElement) {{
                    clearLiquid(activeElement, 0);
                }}
                if (nextElement) {{
                    activateLiquid(nextElement, clientX, clientY, holdMs);
                }} else {{
                    activeElement = null;
                }}
                moveGlobalLens(clientX, clientY, holdMs);
            }}

            function queueActivateFromPoint(clientX, clientY, holdMs) {{
                if (!glassThemeActive()) {{
                    cancelQueuedLiquidMove();
                    hideGlobalLens(0);
                    return;
                }}
                if (Date.now() < liquidActionCooldownUntil) {{
                    return;
                }}
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
                if (isLiquidGroupElement(element)) {{
                    element.dataset.liquidGroup = 'true';
                }}
                element.addEventListener('focus', function() {{
                    if (!shouldAnimateLiquidFocus(element)) {{
                        return;
                    }}
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
            document.addEventListener('click', function(event) {{
                if (!liquidSyntheticTarget || Date.now() > liquidSyntheticUntil || !event.isTrusted) {{
                    return;
                }}
                if (event.target === liquidSyntheticTarget || liquidSyntheticTarget.contains(event.target)) {{
                    const syntheticTarget = liquidSyntheticTarget;
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    if (syntheticTarget.blur) {{
                        syntheticTarget.blur();
                    }}
                    resetLiquidState();
                    liquidSyntheticTarget = null;
                    liquidSyntheticUntil = 0;
                }}
            }}, true);
            document.addEventListener('pointermove', function(event) {{
                if (liquidPointerState && liquidPointerState.pointerId === event.pointerId) {{
                    trackLiquidMovement(liquidPointerState, event.clientX, event.clientY);
                    if (liquidPointerState.scrolled) {{
                        return;
                    }}
                    queueActivateFromPoint(event.clientX, event.clientY, event.pointerType === 'touch' ? 440 : 280);
                    return;
                }}
                if (
                    event.pointerType === 'mouse' ||
                    event.pointerType === 'pen' ||
                    (!event.pointerType && !touchLikeInputActive())
                ) {{
                    queueActivateFromPoint(event.clientX, event.clientY, 260);
                }}
            }}, {{ passive: true }});
            document.addEventListener('pointerdown', function(event) {{
                liquidPointerState = {{
                    pointerId: event.pointerId,
                    pointerType: event.pointerType,
                    startX: event.clientX,
                    startY: event.clientY,
                    lastX: event.clientX,
                    lastY: event.clientY,
                    startTs: Date.now(),
                    scrollX: window.scrollX || window.pageXOffset || 0,
                    scrollY: window.scrollY || window.pageYOffset || 0,
                    scrolled: false,
                    moved: false
                }};
                activateFromPoint(event.clientX, event.clientY, 480);
            }}, {{ passive: true }});
            document.addEventListener('pointerup', function(event) {{
                if (liquidPointerState && liquidPointerState.pointerId === event.pointerId) {{
                    trackLiquidMovement(liquidPointerState, event.clientX, event.clientY);
                    const heldMs = Date.now() - liquidPointerState.startTs;
                    if (
                        !liquidPointerState.scrolled &&
                        ((event.pointerType !== 'touch' && (liquidPointerState.moved || heldMs >= 320)) ||
                        (event.pointerType === 'touch' && heldMs >= 320))
                    ) {{
                        if (applyLiquidAction(event.clientX, event.clientY)) {{
                            liquidPointerState = null;
                            return;
                        }}
                    }}
                }}
                if (event.pointerType === 'touch') {{
                    suppressLiquidFocus(500);
                }}
                liquidPointerState = null;
                cancelQueuedLiquidMove();
                clearLiquid(activeElement, 140);
                hideGlobalLens(140);
                activeElement = null;
            }}, {{ passive: true }});
            document.addEventListener('pointercancel', function() {{
                liquidPointerState = null;
                cancelQueuedLiquidMove();
                clearLiquid(activeElement, 90);
                hideGlobalLens(90);
                activeElement = null;
            }}, {{ passive: true }});
            document.addEventListener('touchstart', function(event) {{
                if (event.touches && event.touches.length) {{
                    const touch = event.touches[0];
                    liquidTouchState = {{
                        startX: touch.clientX,
                        startY: touch.clientY,
                        lastX: touch.clientX,
                        lastY: touch.clientY,
                        startTs: Date.now(),
                        scrollX: window.scrollX || window.pageXOffset || 0,
                        scrollY: window.scrollY || window.pageYOffset || 0,
                        scrolled: false,
                        moved: false
                    }};
                    activateFromPoint(touch.clientX, touch.clientY, 360);
                }}
            }}, {{ passive: true }});
            document.addEventListener('touchmove', function(event) {{
                if (event.touches && event.touches.length) {{
                    const touch = event.touches[0];
                    trackLiquidMovement(liquidTouchState, touch.clientX, touch.clientY);
                    if (liquidTouchState && liquidTouchState.scrolled) {{
                        return;
                    }}
                    queueActivateFromPoint(touch.clientX, touch.clientY, 260);
                }}
            }}, {{ passive: true }});
            document.addEventListener('touchend', function(event) {{
                suppressLiquidFocus(500);
                if (liquidTouchState && !liquidTouchState.scrolled && event.changedTouches && event.changedTouches.length) {{
                    const touch = event.changedTouches[0];
                    const heldMs = Date.now() - liquidTouchState.startTs;
                    if ((liquidTouchState.moved || heldMs >= 320) && applyLiquidAction(touch.clientX, touch.clientY)) {{
                        liquidTouchState = null;
                        return;
                    }}
                }}
                liquidTouchState = null;
                cancelQueuedLiquidMove();
                clearLiquid(activeElement, 90);
                hideGlobalLens(90);
                activeElement = null;
            }}, {{ passive: true }});
            document.addEventListener('touchcancel', function() {{
                liquidTouchState = null;
                cancelQueuedLiquidMove();
                clearLiquid(activeElement, 80);
                hideGlobalLens(80);
                activeElement = null;
            }}, {{ passive: true }});
            window.addEventListener('scroll', function() {{
                if (liquidTouchState) {{
                    liquidTouchState.scrolled = true;
                }}
                resetLiquidState();
            }}, {{ passive: true }});
            document.addEventListener('visibilitychange', function() {{
                if (document.hidden) {{
                    liquidTouchState = null;
                    liquidPointerState = null;
                    resetLiquidState();
                }}
            }});
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

        function setupProtocolTabs() {{
            const buttons = document.querySelectorAll('.protocol-tab');
            const storageKey = 'router-active-protocol';
            const loading = {{}};

            function findPanel(protocol) {{
                return document.querySelector('[data-protocol-panel="' + protocol + '"]');
            }}

            function showLoadError(panel, error) {{
                const target = panel ? panel.querySelector('[data-protocol-loading]') : null;
                if (!target) {{
                    return;
                }}
                const message = error && error.message ? error.message : 'Не удалось загрузить вкладку';
                target.innerHTML = '<span class="eyebrow">Ключи</span><h2>Ошибка загрузки</h2><p class="section-subtitle">' + escapeHtml(message) + '</p><button type="button" class="secondary-button" data-protocol-retry>Повторить</button>';
                const retry = target.querySelector('[data-protocol-retry]');
                if (retry) {{
                    retry.addEventListener('click', function() {{
                        const protocol = panel.getAttribute('data-protocol-panel');
                        panel.dataset.protocolLoading = '0';
                        loadPanel(protocol, panel);
                    }});
                }}
            }}

            function loadPanel(protocol, panel) {{
                if (!ENABLE_KEY_POOL || !protocol || !panel || panel.dataset.protocolLoaded === '1' || loading[protocol]) {{
                    return;
                }}
                loading[protocol] = true;
                panel.dataset.protocolLoading = '1';
                fetch('/api/protocol_panel?proto=' + encodeURIComponent(protocol), {{
                    headers: {{ 'Accept': 'application/json' }},
                    cache: 'no-store'
                }})
                    .then(function(response) {{
                        return response.json().then(function(payload) {{
                            if (!response.ok || !payload.ok) {{
                                throw new Error((payload && payload.error) || 'HTTP ' + response.status);
                            }}
                            return payload;
                        }});
                    }})
                    .then(function(payload) {{
                        const wrapper = document.createElement('div');
                        wrapper.innerHTML = String(payload.html || '').trim();
                        const loadedPanel = wrapper.firstElementChild;
                        if (!loadedPanel) {{
                            throw new Error('Пустой ответ сервера');
                        }}
                        loadedPanel.classList.add('active');
                        loadedPanel.dataset.protocolLoaded = '1';
                        panel.replaceWith(loadedPanel);
                        setupProtocolSubtabs(loadedPanel);
                        setupPoolControls(loadedPanel);
                        setupServiceRouteMenus(loadedPanel);
                        setupAsyncForms(loadedPanel);
                        refreshPoolData(0, protocol);
                    }})
                    .catch(function(error) {{
                        showLoadError(panel, error);
                    }})
                    .finally(function() {{
                        loading[protocol] = false;
                        if (panel) {{
                            panel.dataset.protocolLoading = '0';
                        }}
                    }});
            }}

            function activate(value) {{
                let selected = value || localStorage.getItem(storageKey) || (buttons[0] ? buttons[0].dataset.protocolTarget : '');
                if (selected && !Array.from(buttons).some(function(button) {{ return button.dataset.protocolTarget === selected; }})) {{
                    selected = buttons[0] ? buttons[0].dataset.protocolTarget : '';
                }}
                buttons.forEach(function(button) {{
                    button.classList.toggle('active', button.dataset.protocolTarget === selected);
                }});
                document.querySelectorAll('[data-protocol-panel]').forEach(function(panel) {{
                    panel.classList.toggle('active', panel.getAttribute('data-protocol-panel') === selected);
                }});
                if (selected) {{
                    localStorage.setItem(storageKey, selected);
                }}
                const selectedPanel = findPanel(selected);
                if (selectedPanel && selectedPanel.dataset.protocolPanelLazy === '1' && selectedPanel.dataset.protocolLoaded !== '1') {{
                    loadPanel(selected, selectedPanel);
                }}
            }}

            buttons.forEach(function(button) {{
                button.addEventListener('click', function() {{
                    activate(button.dataset.protocolTarget);
                }});
            }});
            activate(localStorage.getItem(storageKey));
        }}

        function loadProtocolCheck(panel, retryCount) {{
            if ((!ENABLE_KEY_POOL && !ENABLE_CUSTOM_CHECKS) || !panel || panel.dataset.protocolCheckLoaded === '1' || panel.dataset.protocolCheckLoading === '1') {{
                return;
            }}
            const protocol = panel.getAttribute('data-protocol-panel');
            const target = panel.querySelector('[data-protocol-check-deferred]');
            if (!protocol || !target) {{
                return;
            }}
            retryCount = Number(retryCount || 0);
            panel.dataset.protocolCheckLoading = '1';
            fetch('/api/protocol_check_panel?proto=' + encodeURIComponent(protocol), {{
                headers: {{ 'Accept': 'application/json' }},
                cache: 'no-store'
            }})
                .then(function(response) {{
                    return response.json().then(function(payload) {{
                        if (!response.ok || !payload.ok) {{
                            throw new Error((payload && payload.error) || 'HTTP ' + response.status);
                        }}
                        return payload;
                    }});
                }})
                .then(function(payload) {{
                    const subview = panel.querySelector('[data-subview="check"]');
                    if (!subview) {{
                        throw new Error('Check panel not found');
                    }}
                    subview.innerHTML = String(payload.html || '');
                    panel.dataset.protocolCheckLoaded = '1';
                    setupServiceRouteMenus(subview);
                    setupAsyncForms(subview);
                }})
                .catch(function(error) {{
                    if (retryCount < 2) {{
                        panel.dataset.protocolCheckLoading = '0';
                        window.setTimeout(function() {{
                            loadProtocolCheck(panel, retryCount + 1);
                        }}, 1200 + retryCount * 1800);
                        return;
                    }}
                    const message = error && error.message ? error.message : 'Loading failed';
                    target.innerHTML = '<span class="status-label">Checks</span><p class="status-note">' + escapeHtml(message) + '</p>';
                }})
                .finally(function() {{
                    panel.dataset.protocolCheckLoading = '0';
                }});
        }}

        function setupProtocolSubtabs(root) {{
            const panels = [];
            if (root && root.matches && root.matches('[data-protocol-panel]')) {{
                panels.push(root);
            }}
            const scope = root && root.querySelectorAll ? root : document;
            scope.querySelectorAll('[data-protocol-panel]').forEach(function(panel) {{
                if (!panels.includes(panel)) {{
                    panels.push(panel);
                }}
            }});
            panels.forEach(function(panel) {{
                if (panel.dataset.subtabsReady === '1') {{
                    return;
                }}
                panel.dataset.subtabsReady = '1';
                const buttons = panel.querySelectorAll('[data-subview-target]');
                function activate(value) {{
                    const selected = value || 'key';
                    buttons.forEach(function(button) {{
                        button.classList.toggle('active', button.dataset.subviewTarget === selected);
                    }});
                    panel.querySelectorAll('[data-subview]').forEach(function(subview) {{
                        subview.classList.toggle('active', subview.dataset.subview === selected);
                    }});
                    if (selected === 'check') {{
                        loadProtocolCheck(panel);
                    }}
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
            const value = cleanStatusText(text || '');
            element.textContent = value;
            element.classList.toggle('hidden', !value);
        }}

        function cleanStatusText(text) {{
            return String(text || '').replace(/\\s*\\.+\\s*$/u, '');
        }}

        function serviceTextBadge(label, badge) {{
            const text = String(badge || label || 'WEB').trim().slice(0, 4).toUpperCase() || 'WEB';
            return '<span class="custom-service-badge custom-service-neutral" title="' +
                escapeHtml(label || '') + '">' + escapeHtml(text) + '</span>';
        }}

        function serviceIcon(src, alt, badge) {{
            const cleanSrc = String(src || '');
            if (!cleanSrc) {{
                return serviceTextBadge(alt, badge);
            }}
            return '<img class="service-icon-img" src="' + escapeHtml(cleanSrc) + '" width="16" height="16" alt="' +
                escapeHtml(alt || 'Service') + '" style="vertical-align:middle;opacity:1">';
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
                        html += serviceIcon(serviceIconSrc(check.icon), check.label || 'Service', check.badge || '');
                    }}
                }});
            }}
            return html;
        }}

        function probeBadge(state, service) {{
            if (state === 'na') {{
                return '<span class="service-probe-mark service-probe-na">-</span>';
            }}
            if (state === 'ok') {{
                return serviceIcon(service === 'tg' ? TELEGRAM_ICON_SRC : YOUTUBE_ICON_SRC, service === 'tg' ? 'Telegram' : 'YouTube');
            }}
            if (state === 'warn') {{
                if (service === 'yt') {{
                    return '<span class="service-probe-mark service-probe-warn service-probe-icon-warn" title="YouTube works, probe is unstable">' +
                        serviceIcon(YOUTUBE_ICON_SRC, 'YouTube') + '</span>';
                }}
                return '<span class="service-probe-mark service-probe-warn">!</span>';
            }}
            if (state === 'fail') {{
                return '<span class="service-probe-mark service-probe-fail">✕</span>';
            }}
            return '<span class="service-probe-mark service-probe-unknown">?</span>';
        }}

        function poolCoreServices(pool) {{
            return ['telegram', 'youtube'];
        }}

        function poolCoreColspan(coreServices) {{
            return 4 + (Array.isArray(coreServices) ? coreServices.length : 2);
        }}

        function poolCoreServiceCells(row, coreServices) {{
            let html = '';
            (coreServices || []).forEach(function(service) {{
                if (service === 'telegram') {{
                    html += '<td class="pool-service-cell" data-pool-tg>' + probeBadge(row.tg, 'tg') + '</td>';
                }} else if (service === 'youtube') {{
                    html += '<td class="pool-service-cell" data-pool-yt>' + probeBadge(row.yt, 'yt') + '</td>';
                }}
            }});
            return html;
        }}

        function poolPanelCoreServices(proto) {{
            return ['telegram', 'youtube'];
        }}

        function updatePoolSortOptions(proto) {{
            const menu = document.querySelector('[data-pool-sort-menu="' + proto + '"]');
            const input = document.querySelector('[data-pool-sort="' + proto + '"]');
            const button = document.querySelector('[data-pool-sort-button="' + proto + '"]');
            if (!menu) {{
                return;
            }}
            menu.querySelectorAll('[data-pool-sort-value]').forEach(function(option) {{
                option.classList.remove('hidden');
            }});
            if (input) {{
                const selected = menu.querySelector('[data-pool-sort-value="' + input.value + '"]');
                if (selected && selected.classList.contains('hidden')) {{
                    input.value = 'original';
                    const fallback = menu.querySelector('[data-pool-sort-value="original"]');
                    if (button && fallback) {{
                        button.textContent = fallback.textContent || button.textContent;
                    }}
                }}
            }}
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
            if (status === 'ok' && check) {{
                content = serviceIcon(serviceIconSrc(check.icon), label, check.badge || '');
            }} else if (status === 'fail') {{
                content = '<span class="service-probe-mark service-probe-fail">✕</span>';
            }} else {{
                content = '<span class="service-probe-mark service-probe-unknown">?</span>';
            }}
            return '<span class="custom-service-slot custom-service-' + status + '" title="' +
                escapeHtml(label + (url ? ': ' + url : '')) + '">' + content + '</span>';
        }}

        function renderCustomBadges(states, checks) {{
            const activeChecks = Array.isArray(checks) ? checks : customChecks;
            if (!activeChecks.length) {{
                return '';
            }}
            const stateMap = states || {{}};
            return activeChecks.filter(function(check) {{
                return Object.prototype.hasOwnProperty.call(stateMap, check.id);
            }}).map(function(check) {{
                const state = stateMap[check.id] || 'unknown';
                return customBadge(state, check);
            }}).join('');
        }}

        function poolQualityLabel(row) {{
            const quality = String((row && row.yt_quality) || '').toLowerCase();
            if (quality === 'fast') {{
                return 'Быстро';
            }}
            if (quality === 'stable') {{
                return 'Стабильно';
            }}
            return String((row && row.yt_quality_label) || '');
        }}

        function poolQualityBadge(row) {{
            const quality = String((row && row.yt_quality) || '').toLowerCase();
            const label = poolQualityLabel(row);
            if (!label || (quality !== 'fast' && quality !== 'stable')) {{
                return '';
            }}
            return '<span class="pool-quality-badge pool-quality-' + escapeHtml(quality) + '">' + escapeHtml(label) + '</span>';
        }}

        function poolQualityTitle(row) {{
            return String((row && row.quality_summary) || 'Качество еще не измерено');
        }}

        function poolApplyButtonHtml(row, displayName) {{
            return '<span class="pool-key-name">' + displayName + '</span>' + poolQualityBadge(row);
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

        function customHeaderIcons(checks) {{
            const activeChecks = Array.isArray(checks) ? checks : customChecks;
            if (!activeChecks.length) {{
                return '';
            }}
            return activeChecks.map(function(check) {{
                const label = check.label || 'Service';
                const content = check.icon
                    ? serviceIcon(serviceIconSrc(check.icon), label, check.badge || '')
                    : '<span class="custom-service-badge custom-service-neutral">' + escapeHtml(check.badge || 'WEB') + '</span>';
                return '<span class="custom-service-slot custom-service-header" title="' + escapeHtml(label) + '">' + content + '</span>';
            }}).join('');
        }}

        function syncCustomCheckColumns(checks, root) {{
            const activeChecks = Array.isArray(checks) ? checks : customChecks;
            const hasChecks = activeChecks.length > 0;
            const mobileWidth = Math.max(28, 28 * activeChecks.length) + 'px';
            const desktopWidth = (32 * Math.max(1, activeChecks.length)) + 'px';
            const scope = root && root.querySelectorAll ? root : document;
            const tables = [];
            if (scope.matches && scope.matches('.pool-table')) {{
                tables.push(scope);
            }}
            scope.querySelectorAll('.pool-table').forEach(function(table) {{
                tables.push(table);
            }});
            tables.forEach(function(table) {{
                table.classList.toggle('has-custom-checks', hasChecks);
                table.style.setProperty('--custom-col-mobile', mobileWidth);
                const customCol = table.querySelector('.pool-col-custom');
                if (customCol) {{
                    customCol.style.width = desktopWidth;
                }}
            }});
        }}

        function poolCustomChecks(pool) {{
            if (pool && Array.isArray(pool.custom_checks)) {{
                return pool.custom_checks;
            }}
            return customChecks;
        }}

        function syncPoolCustomCheckColumns(proto, checks) {{
            const body = document.querySelector('[data-pool-body="' + proto + '"]');
            const table = body ? body.closest('.pool-table') : null;
            if (!table) {{
                return;
            }}
            syncCustomCheckColumns(checks, table);
            const head = table.querySelector('[data-custom-check-head]');
            if (head) {{
                head.innerHTML = customHeaderIcons(checks);
            }}
        }}

        function routeServiceIds() {{
            return Array.from(document.querySelectorAll('[data-service-route-id]')).map(function(item) {{
                return item.dataset.serviceRouteId || '';
            }}).filter(Boolean);
        }}

        function renderCustomChecks(checks) {{
            if (!ENABLE_CUSTOM_CHECKS) {{
                return;
            }}
            customChecks = Array.isArray(checks) ? checks : [];
            const routeIds = routeServiceIds();
            const visibleChecks = customChecks.filter(function(check) {{
                return routeIds.indexOf(check.id || '') === -1;
            }});
            const html = visibleChecks.length ? visibleChecks.map(function(check) {{
                return '<div class="custom-check-item">' +
                    customIconHtml(check) +
                    '<span class="custom-check-copy"><strong>' + escapeHtml(check.label || 'Проверка') + '</strong><small>' + escapeHtml(customUrlText(check)) + '</small></span>' +
                    '<form method="post" action="/custom_check_delete" data-async-action="custom-check-delete" data-confirm-title="Удалить проверку?" data-confirm-message="Удалить дополнительную проверку ' + escapeHtml(check.label || 'Проверка') + '?">' +
                        '<input type="hidden" name="id" value="' + escapeHtml(check.id || '') + '">' +
                        '<button type="submit" class="pool-delete-btn" title="Удалить проверку">Удалить</button>' +
                    '</form>' +
                '</div>';
            }}).join('') : '';
            document.querySelectorAll('.custom-check-card').forEach(function(card) {{
                let list = card.querySelector('[data-custom-check-list]');
                if (!html) {{
                    if (list) {{
                        list.remove();
                    }}
                    return;
                }}
                if (!list) {{
                    list = document.createElement('div');
                    list.className = 'custom-check-list';
                    list.setAttribute('data-custom-check-list', '');
                    const form = card.querySelector('.custom-check-form');
                    if (form) {{
                        card.insertBefore(list, form);
                    }} else {{
                        card.appendChild(list);
                    }}
                }}
                list.innerHTML = html;
                setupAsyncForms(list);
            }});
            const activeIds = customChecks.map(function(check) {{ return check.id; }});
            document.querySelectorAll('[data-custom-preset]').forEach(function(button) {{
                const active = activeIds.indexOf(button.dataset.customPreset) !== -1;
                button.disabled = active;
                button.title = active ? 'Уже добавлено' : 'Добавить проверку';
            }});
        }}

        function poolStateRank(value) {{
            if (value === 'ok') {{
                return 3;
            }}
            if (value === 'warn') {{
                return 2.5;
            }}
            if (value === 'unknown') {{
                return 2;
            }}
            if (value === 'fail') {{
                return 1;
            }}
            if (value === 'na') {{
                return 0;
            }}
            return 0;
        }}

        function poolStateFilterFromMode(mode) {{
            if (mode === 'working' || mode === 'problem' || mode === 'unknown') {{
                return mode;
            }}
            return 'all';
        }}

        function poolRowMatchesState(row, state) {{
            if (!state || state === 'all') {{
                return true;
            }}
            const states = [row.dataset.tgState || 'unknown', row.dataset.ytState || 'unknown'].filter(function(value) {{
                return value && value !== 'na';
            }});
            const relevantStates = states.length ? states : ['unknown'];
            if (state === 'working') {{
                return relevantStates.some(function(value) {{ return value === 'ok' || value === 'warn'; }});
            }}
            if (state === 'problem') {{
                return relevantStates.some(function(value) {{ return value === 'fail'; }});
            }}
            if (state === 'unknown') {{
                return relevantStates.every(function(value) {{ return value === 'unknown'; }});
            }}
            return true;
        }}

        function schedulePoolView(proto, delayMs) {{
            if (!proto) {{
                return;
            }}
            if (poolViewTimers[proto]) {{
                window.clearTimeout(poolViewTimers[proto]);
            }}
            poolViewTimers[proto] = window.setTimeout(function() {{
                poolViewTimers[proto] = null;
                applyPoolView(proto, false);
            }}, Math.max(0, Number(delayMs || 0)));
        }}

        function protocolList(protocols) {{
            const selected = [];
            const source = Array.isArray(protocols) ? protocols : [protocols];
            source.forEach(function(proto) {{
                proto = String(proto || '').trim();
                if (proto && selected.indexOf(proto) === -1) {{
                    selected.push(proto);
                }}
            }});
            return selected;
        }}

        function protocolQuery(protocols) {{
            const selected = protocolList(protocols);
            return selected.length ? '?protocols=' + encodeURIComponent(selected.join(',')) : '';
        }}

        function loadedPoolProtocolQuery(requestedProtocols) {{
            if (requestedProtocols) {{
                return protocolQuery(requestedProtocols);
            }}
            const protocols = [];
            document.querySelectorAll('[data-protocol-panel]').forEach(function(panel) {{
                const proto = panel.getAttribute('data-protocol-panel') || '';
                if (!proto || panel.dataset.protocolLoaded === '0') {{
                    return;
                }}
                if (!panel.querySelector('[data-pool-body="' + proto + '"]')) {{
                    return;
                }}
                if (protocols.indexOf(proto) === -1) {{
                    protocols.push(proto);
                }}
            }});
            return protocolQuery(protocols);
        }}

        function deferredPoolProtocols() {{
            const protocols = [];
            document.querySelectorAll('[data-pool-deferred="1"]').forEach(function(body) {{
                const proto = body.dataset.poolBody || '';
                if (proto && protocols.indexOf(proto) === -1) {{
                    protocols.push(proto);
                }}
            }});
            return protocols;
        }}

        function clearPoolDeferred(body) {{
            if (!body) {{
                return;
            }}
            body.removeAttribute('data-pool-deferred');
            delete body.dataset.poolDeferred;
        }}

        function poolBodyColspan(body) {{
            const table = body ? body.closest('table') : null;
            const headerCells = table ? table.querySelectorAll('thead th') : [];
            return Math.max(1, headerCells.length || 6);
        }}

        function setPoolBodyMessage(proto, message, keepDeferred) {{
            const body = document.querySelector('[data-pool-body="' + proto + '"]');
            if (!body) {{
                return;
            }}
            if (keepDeferred) {{
                body.setAttribute('data-pool-deferred', '1');
                body.dataset.poolDeferred = '1';
            }}
            body.innerHTML = '<tr class="pool-row pool-empty-row"><td colspan="' + poolBodyColspan(body) + '">' + escapeHtml(message) + '</td></tr>';
        }}

        function applyPoolView(proto, forceSort) {{
            if (!proto) {{
                return;
            }}
            const body = document.querySelector('[data-pool-body="' + proto + '"]');
            if (!body) {{
                return;
            }}
            const filterInput = document.querySelector('[data-pool-filter="' + proto + '"]');
            const sortSelect = document.querySelector('[data-pool-sort="' + proto + '"]');
            const filterText = filterInput ? filterInput.value.trim().toLowerCase() : '';
            const sortMode = sortSelect ? sortSelect.value : 'original';
            const stateFilter = poolStateFilterFromMode(sortMode);
            const rows = Array.from(body.querySelectorAll('[data-pool-row]'));
            rows.forEach(function(row) {{
                const haystack = String(row.dataset.search || row.dataset.key || '').toLowerCase();
                const matchesText = !filterText || haystack.indexOf(filterText) !== -1;
                const matchesState = poolRowMatchesState(row, stateFilter);
                row.classList.toggle('pool-row-hidden', !(matchesText && matchesState));
            }});
            if (!forceSort && body.dataset.poolAppliedSort === sortMode) {{
                return;
            }}
            rows.sort(function(left, right) {{
                const leftIndex = Number(left.dataset.poolIndex || 0);
                const rightIndex = Number(right.dataset.poolIndex || 0);
                if (sortMode === 'original' || sortMode === 'active') {{
                    const activeDelta = Number(right.dataset.active || 0) - Number(left.dataset.active || 0);
                    if (activeDelta) {{
                        return activeDelta;
                    }}
                }} else if (sortMode === 'telegram') {{
                    const tgDelta = poolStateRank(right.dataset.tgState) - poolStateRank(left.dataset.tgState);
                    if (tgDelta) {{
                        return tgDelta;
                    }}
                }} else if (sortMode === 'youtube') {{
                    const qualityDelta = Number(right.dataset.qualityScore || 0) - Number(left.dataset.qualityScore || 0);
                    if (qualityDelta) {{
                        return qualityDelta;
                    }}
                    const ytDelta = poolStateRank(right.dataset.ytState) - poolStateRank(left.dataset.ytState);
                    if (ytDelta) {{
                        return ytDelta;
                    }}
                }} else if (sortMode === 'quality') {{
                    const qualityDelta = Number(right.dataset.qualityScore || 0) - Number(left.dataset.qualityScore || 0);
                    if (qualityDelta) {{
                        return qualityDelta;
                    }}
                    const checkedDelta = Number(right.dataset.checkedTs || 0) - Number(left.dataset.checkedTs || 0);
                    if (checkedDelta) {{
                        return checkedDelta;
                    }}
                }} else if (sortMode === 'checked') {{
                    const checkedDelta = Number(right.dataset.checkedTs || 0) - Number(left.dataset.checkedTs || 0);
                    if (checkedDelta) {{
                        return checkedDelta;
                    }}
                }}
                return leftIndex - rightIndex;
            }});
            const fragment = document.createDocumentFragment();
            rows.forEach(function(row) {{
                fragment.appendChild(row);
            }});
            body.appendChild(fragment);
            body.dataset.poolAppliedSort = sortMode;
        }}

        function closePoolSortMenus(exceptProto) {{
            document.querySelectorAll('[data-pool-sort-menu]').forEach(function(menu) {{
                const proto = menu.dataset.poolSortMenu || '';
                if (exceptProto && proto === exceptProto) {{
                    return;
                }}
                menu.classList.add('hidden');
                const button = document.querySelector('[data-pool-sort-button="' + proto + '"]');
                if (button) {{
                    button.setAttribute('aria-expanded', 'false');
                }}
            }});
        }}

        function setupPoolControls(root) {{
            if (!ENABLE_KEY_POOL) {{
                return;
            }}
            const scope = root && root.querySelectorAll ? root : document;
            scope.querySelectorAll('[data-pool-filter], [data-pool-sort]').forEach(function(control) {{
                if (control.dataset.poolControlReady === '1') {{
                    return;
                }}
                control.dataset.poolControlReady = '1';
                const proto = control.dataset.poolFilter || control.dataset.poolSort || '';
                updatePoolSortOptions(proto);
                control.addEventListener(control.matches('input') ? 'input' : 'change', function() {{
                    if (control.matches('input')) {{
                        schedulePoolView(proto, 120);
                    }} else {{
                        applyPoolView(proto, true);
                    }}
                }});
            }});
            scope.querySelectorAll('[data-pool-sort-button]').forEach(function(button) {{
                if (button.dataset.poolSortReady === '1') {{
                    return;
                }}
                button.dataset.poolSortReady = '1';
                const proto = button.dataset.poolSortButton || '';
                button.addEventListener('click', function(event) {{
                    event.stopPropagation();
                    const menu = document.querySelector('[data-pool-sort-menu="' + proto + '"]');
                    if (!menu) {{
                        return;
                    }}
                    const willOpen = menu.classList.contains('hidden');
                    closePoolSortMenus(proto);
                    menu.classList.toggle('hidden', !willOpen);
                    button.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
                }});
            }});
            scope.querySelectorAll('[data-pool-sort-value]').forEach(function(option) {{
                if (option.dataset.poolSortOptionReady === '1') {{
                    return;
                }}
                option.dataset.poolSortOptionReady = '1';
                option.addEventListener('click', function(event) {{
                    event.stopPropagation();
                    const menu = option.closest('[data-pool-sort-menu]');
                    const proto = menu ? menu.dataset.poolSortMenu || '' : '';
                    const value = option.dataset.poolSortValue || 'original';
                    const input = document.querySelector('[data-pool-sort="' + proto + '"]');
                    const button = document.querySelector('[data-pool-sort-button="' + proto + '"]');
                    if (input) {{
                        input.value = value;
                    }}
                    if (button) {{
                        button.textContent = option.textContent || 'Исходный порядок';
                    }}
                    if (menu) {{
                        menu.querySelectorAll('[data-pool-sort-value]').forEach(function(item) {{
                            item.classList.toggle('active', item === option);
                        }});
                    }}
                    closePoolSortMenus();
                    applyPoolView(proto, true);
                }});
            }});
            if (document.body.dataset.poolSortDismissReady !== '1') {{
                document.body.dataset.poolSortDismissReady = '1';
                document.addEventListener('click', function() {{
                    closePoolSortMenus();
                }});
                document.addEventListener('keydown', function(event) {{
                    if (event.key === 'Escape') {{
                        closePoolSortMenus();
                    }}
                }});
            }}
            scope.querySelectorAll('[data-pool-body]').forEach(function(body) {{
                applyPoolView(body.dataset.poolBody || '', true);
            }});
        }}

        function renderPoolBody(proto, pool) {{
            const body = document.querySelector('[data-pool-body="' + proto + '"]');
            if (!body || !pool) {{
                return;
            }}
            const rows = pool.rows || [];
            const coreServices = poolCoreServices(pool);
            const checks = poolCustomChecks(pool);
            const panel = body.closest('[data-protocol-panel]');
            if (panel) {{
                panel.dataset.coreServices = coreServices.join(',');
            }}
            syncPoolCustomCheckColumns(proto, checks);
            updatePoolSortOptions(proto);
            const tab = document.querySelector('[data-protocol-target="' + proto + '"] .tab-count');
            if (tab) {{
                tab.textContent = String(pool.count || rows.length);
            }}
            clearPoolDeferred(body);
            if (!rows.length) {{
                body.innerHTML = '<tr class="pool-row pool-empty-row"><td colspan="6">Пул пуст. Добавьте ключи или загрузите subscription.</td></tr>';
                body.innerHTML = body.innerHTML.replace('colspan="6"', 'colspan="' + poolCoreColspan(coreServices) + '"');
                body.dataset.poolAppliedSort = '';
                setupPoolControls(body.closest('[data-protocol-panel]') || document);
                return;
            }}
            body.dataset.poolAppliedSort = '';
            body.innerHTML = rows.map(function(row, position) {{
                const activeClass = row.active ? ' pool-row-active' : '';
                const activeText = row.active ? 'активен' : '';
                const keyId = escapeHtml(row.key_id || '');
                const rowIndex = Number(row.index || (position + 1)) - 1;
                const displayName = escapeHtml(row.display_name || '');
                const coreCells = poolCoreServiceCells(row, coreServices);
                return '<tr class="pool-row' + activeClass + '" data-pool-row data-protocol="' + proto + '" data-key-id="' + keyId + '" data-pool-index="' + rowIndex + '" data-active="' + (row.active ? '1' : '0') + '" data-tg-state="' + escapeHtml(row.tg || 'unknown') + '" data-yt-state="' + escapeHtml(row.yt || 'unknown') + '" data-quality-score="' + Number(row.yt_score || 0) + '" data-quality-class="' + escapeHtml(row.yt_quality || '') + '" data-checked-ts="' + Number(row.checked_ts || 0) + '" data-search="' + displayName + ' ' + keyId + '">' +
                    '<td class="pool-key-cell">' +
                        '<form method="post" action="/pool_apply" class="pool-apply-form" data-async-action="pool-apply">' +
                            '<input type="hidden" name="type" value="' + proto + '">' +
                            '<input type="hidden" name="key_id" value="' + keyId + '">' +
                            '<button type="submit" class="pool-apply-btn" title="' + escapeHtml(poolQualityTitle(row)) + '">' + poolApplyButtonHtml(row, displayName) + '</button>' +
                        '</form>' +
                        '<span class="pool-mobile-active" data-pool-key-meta data-pool-mobile-active>' + activeText + '</span>' +
                        '<span class="pool-mobile-checked" data-pool-mobile-checked>' + escapeHtml(row.checked_at || '') + '</span>' +
                        '<span class="pool-hash">' + escapeHtml(row.key_id) + '</span>' +
                    '</td>' +
                    coreCells +
                    '<td class="pool-custom-cell" data-pool-custom>' + renderCustomBadges(row.custom, checks) + '</td>' +
                    '<td class="pool-checked-cell" data-pool-checked>' + escapeHtml(row.checked_at) + '</td>' +
                    '<td class="pool-actions-cell">' +
                        '<form method="post" action="/pool_delete" class="pool-item-form" data-async-action="pool-delete" data-confirm-title="Удалить ключ?" data-confirm-message="Удалить ключ из пула?">' +
                            '<input type="hidden" name="type" value="' + proto + '">' +
                            '<input type="hidden" name="key_id" value="' + keyId + '">' +
                            '<button type="submit" class="pool-delete-btn" title="Удалить ключ из пула"><span class="pool-delete-icon" aria-hidden="true">&times;</span><span class="pool-delete-label">Удалить</span></button>' +
                        '</form>' +
                    '</td>' +
                '</tr>';
            }}).join('');
            setupAsyncForms(body);
            setupPoolControls(body.closest('[data-protocol-panel]') || document);
            applyPoolView(proto, true);
        }}

        function updatePoolRows(proto, pool) {{
            const body = document.querySelector('[data-pool-body="' + proto + '"]');
            if (!body || !pool) {{
                return;
            }}
            const rows = pool.rows || [];
            const coreServices = poolCoreServices(pool);
            const checks = poolCustomChecks(pool);
            const panel = body.closest('[data-protocol-panel]');
            if (panel) {{
                panel.dataset.coreServices = coreServices.join(',');
            }}
            syncPoolCustomCheckColumns(proto, checks);
            updatePoolSortOptions(proto);
            const tab = document.querySelector('[data-protocol-target="' + proto + '"] .tab-count');
            if (tab) {{
                tab.textContent = String(pool.count || rows.length);
            }}
            clearPoolDeferred(body);
            const rowElements = Array.from(body.querySelectorAll('[data-pool-row]'));
            const rowByKeyId = new Map();
            rowElements.forEach(function(item) {{
                item.classList.remove('pool-row-active');
                const meta = item.querySelector('[data-pool-key-meta]');
                if (meta) {{
                    meta.textContent = '';
                }}
                if (item.dataset.keyId) {{
                    rowByKeyId.set(item.dataset.keyId, item);
                }}
            }});
            rows.forEach(function(row) {{
                const item = rowByKeyId.get(String(row.key_id || ''));
                if (!item) {{
                    return;
                }}
                item.classList.toggle('pool-row-active', !!row.active);
                item.dataset.active = row.active ? '1' : '0';
                item.dataset.tgState = row.tg || 'unknown';
                item.dataset.ytState = row.yt || 'unknown';
                item.dataset.qualityScore = String(row.yt_score || 0);
                item.dataset.qualityClass = String(row.yt_quality || '');
                item.dataset.checkedTs = String(row.checked_ts || 0);
                item.dataset.search = String((row.display_name || '') + ' ' + (row.key_id || ''));
                const button = item.querySelector('.pool-apply-btn');
                if (button) {{
                    const displayName = escapeHtml(row.display_name || '');
                    button.title = poolQualityTitle(row);
                    button.innerHTML = poolApplyButtonHtml(row, displayName);
                }}
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
                    custom.innerHTML = renderCustomBadges(row.custom, checks);
                }}
                const checked = item.querySelector('[data-pool-checked]');
                if (checked) {{
                    checked.textContent = row.checked_at || '';
                }}
                const mobileChecked = item.querySelector('[data-pool-mobile-checked]');
                if (mobileChecked) {{
                    mobileChecked.textContent = row.checked_at || '';
                }}
            }});
            applyPoolView(proto, true);
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
                const body = document.querySelector('[data-pool-body="' + proto + '"]');
                const currentRows = body ? Array.from(body.querySelectorAll('[data-pool-row]')) : [];
                const currentIds = new Set(currentRows.map(function(item) {{ return String(item.dataset.keyId || ''); }}));
                const needsRender = rows.length === 0 || currentRows.length !== rows.length || rows.some(function(row) {{
                    return !currentIds.has(String(row.key_id || ''));
                }});
                if (needsRender) {{
                    renderPoolBody(proto, pools[proto]);
                }} else {{
                    updatePoolRows(proto, pools[proto]);
                }}
            }});
        }}

        function freshPoolProbeProgress(progress) {{
            progress = progress || {{}};
            const total = Number(progress.total || 0);
            if (total <= 0) {{
                return progress;
            }}
            const checked = Number(progress.checked || 0);
            const startedAt = Number(progress.started_at || 0);
            if (latestPoolProbeProgress && Number(latestPoolProbeProgress.total || 0) > 0) {{
                const previousStartedAt = Number(latestPoolProbeProgress.started_at || 0);
                const previousChecked = Number(latestPoolProbeProgress.checked || 0);
                if (startedAt && previousStartedAt && startedAt < previousStartedAt) {{
                    return latestPoolProbeProgress;
                }}
                if (startedAt && previousStartedAt && startedAt === previousStartedAt && checked < previousChecked) {{
                    return latestPoolProbeProgress;
                }}
            }}
            latestPoolProbeProgress = progress;
            return progress;
        }}

        function poolProbeSummaryText(progress, fallbackNote) {{
            progress = progress || {{}};
            if (Number(progress.total || 0) <= 0) {{
                return fallbackNote || '';
            }}
            const progressNote = progress.note ? String(progress.note) : (fallbackNote || '');
            let summary = poolProbeProgressLabel(progress.scope || '') + ': ' + (progress.checked || 0) + '/' + progress.total;
            if (progressNote) {{
                summary += ' - ' + progressNote;
            }}
            return summary;
        }}

        function updatePoolSummaryBlock(poolSummary, progress, running, paused) {{
            if (!poolSummary) {{
                return;
            }}
            let summaryNote = poolSummary.note || '';
            if ((running || paused) && progress && Number(progress.total || 0) > 0) {{
                summaryNote = poolProbeSummaryText(progress, summaryNote);
            }}
            setOptionalText('pool-active-summary', poolSummary.active_text || '');
            setOptionalText('pool-summary-note', summaryNote);
        }}

        function updatePoolProbeControls(active, paused) {{
            if (!ENABLE_KEY_POOL) {{
                return;
            }}
            const running = !!active;
            const hasPausedQueue = !!paused;
            document.querySelectorAll('[data-pool-probe-start-button]').forEach(function(button) {{
                button.disabled = running;
                button.setAttribute('aria-disabled', running ? 'true' : 'false');
            }});
            document.querySelectorAll('[data-pool-probe-cancel-button]').forEach(function(button) {{
                const canCancel = running || hasPausedQueue;
                button.disabled = !canCancel;
                button.setAttribute('aria-disabled', canCancel ? 'false' : 'true');
            }});
        }}

        function applyPoolPayload(payload) {{
            if (!ENABLE_KEY_POOL || !payload) {{
                return;
            }}
            if (ENABLE_CUSTOM_CHECKS && payload.custom_checks) {{
                renderCustomChecks(payload.custom_checks);
            }}
            const progress = freshPoolProbeProgress(payload.pool_probe_progress || {{}});
            const poolProbeActive = !!payload.pool_probe_running && Number(progress.total || 0) > 0;
            const poolProbePaused = !!payload.pool_probe_paused && Number(progress.total || 0) > 0;
            updatePoolSummaryBlock(payload.pool_summary || null, progress, poolProbeActive, poolProbePaused);
            updatePoolProbeControls(poolProbeActive, poolProbePaused);
            updatePoolStatus(payload.pools);
            if ((poolProbeActive || poolProbePaused) && !document.hidden) {{
                renderStatusAttention({{
                    pool_probe_running: poolProbeActive,
                    pool_probe_paused: poolProbePaused,
                    pool_probe_progress: progress
                }});
                schedulePoolProbePolling(POOL_PROBE_STATUS_POLL_MS);
                refreshPoolData(POOL_PROBE_POOL_REFRESH_MS);
            }}
        }}

        function applyPoolProbeStatusPayload(payload) {{
            if (!ENABLE_KEY_POOL || !payload) {{
                return false;
            }}
            const progress = freshPoolProbeProgress(payload.progress || payload.pool_probe_progress || {{}});
            const poolProbeActive = !!(payload.running || payload.pool_probe_running) && Number(progress.total || 0) > 0;
            const poolProbePaused = !!(payload.paused || payload.pool_probe_paused) && Number(progress.total || 0) > 0;
            updatePoolProbeControls(poolProbeActive, poolProbePaused);
            if (poolProbeActive || poolProbePaused) {{
                const progressSummary = poolProbeSummaryText(progress, '');
                if (progressSummary) {{
                    setOptionalText('pool-summary-note', progressSummary);
                }}
                renderStatusAttention({{
                    pool_probe_running: poolProbeActive,
                    pool_probe_paused: poolProbePaused,
                    pool_probe_progress: progress
                }});
                poolProbeWasRunning = true;
                return true;
            }}
            if (poolProbeWasRunning) {{
                poolProbeWasRunning = false;
                refreshPoolData(500);
                scheduleStatusPolling(30000);
            }}
            return false;
        }}

        function schedulePoolProbePolling(delayMs) {{
            if (!ENABLE_KEY_POOL || document.hidden) {{
                return;
            }}
            if (poolProbePollTimer) {{
                window.clearTimeout(poolProbePollTimer);
            }}
            poolProbePollTimer = window.setTimeout(pollPoolProbeStatus, Math.max(0, Number(delayMs || 0)));
        }}

        function pollPoolProbeStatus() {{
            if (!ENABLE_KEY_POOL || document.hidden) {{
                poolProbePollTimer = null;
                return;
            }}
            poolProbePollTimer = null;
            fetch('/api/pool_probe', {{
                headers: {{'Accept': 'application/json'}},
                cache: 'no-store'
            }})
                .then(function(response) {{ return response.json(); }})
                .then(function(payload) {{
                    if (applyPoolProbeStatusPayload(payload)) {{
                        schedulePoolProbePolling(POOL_PROBE_STATUS_POLL_MS);
                    }}
                }})
                .catch(function() {{
                    if (!document.hidden) {{
                        schedulePoolProbePolling(Math.max(POOL_PROBE_STATUS_POLL_MS, 15000));
                    }}
                }});
        }}

        function refreshPoolData(delayMs, protocols) {{
            if (!ENABLE_KEY_POOL) {{
                return;
            }}
            const requestedNow = protocolList(protocols);
            if (requestedNow.length) {{
                requestedNow.forEach(function(proto) {{
                    pendingPoolDataProtocols.add(proto);
                }});
            }} else {{
                poolDataRefreshAll = true;
            }}
            const delay = Math.max(0, Number(delayMs || 0));
            const dueAt = Date.now() + delay;
            if (poolDataRefreshTimer && poolDataRefreshDueAt && dueAt >= poolDataRefreshDueAt) {{
                return;
            }}
            if (poolDataRefreshTimer) {{
                window.clearTimeout(poolDataRefreshTimer);
            }}
            poolDataRefreshDueAt = dueAt;
            poolDataRefreshTimer = window.setTimeout(function() {{
                poolDataRefreshTimer = null;
                poolDataRefreshDueAt = 0;
                const requestedProtocols = poolDataRefreshAll ? [] : Array.from(pendingPoolDataProtocols);
                pendingPoolDataProtocols.clear();
                poolDataRefreshAll = false;
                const loadingProtocols = requestedProtocols.length ? requestedProtocols : deferredPoolProtocols();
                loadingProtocols.forEach(function(proto) {{
                    const body = document.querySelector('[data-pool-body="' + proto + '"]');
                    if (body && body.hasAttribute('data-pool-deferred')) {{
                        setPoolBodyMessage(proto, 'Загружаю пул ключей...', true);
                    }}
                }});
                fetch('/api/pools' + loadedPoolProtocolQuery(requestedProtocols.length ? requestedProtocols : null), {{
                    headers: {{'Accept': 'application/json'}},
                    cache: 'no-store'
                }})
                    .then(function(response) {{
                        return response.json().then(function(payload) {{
                            if (!response.ok) {{
                                throw new Error((payload && payload.error) || 'HTTP ' + response.status);
                            }}
                            return payload;
                        }});
                    }})
                    .then(function(payload) {{
                        Object.keys(payload.pools || {{}}).forEach(function(proto) {{
                            poolDataRetryCount[proto] = 0;
                        }});
                        applyPoolPayload(payload);
                    }})
                    .catch(function() {{
                        const retryProtocols = loadingProtocols.length ? loadingProtocols : deferredPoolProtocols();
                        let shouldRetry = false;
                        retryProtocols.forEach(function(proto) {{
                            const count = Number(poolDataRetryCount[proto] || 0) + 1;
                            poolDataRetryCount[proto] = count;
                            if (count < 3) {{
                                shouldRetry = true;
                                setPoolBodyMessage(proto, 'Не удалось загрузить пул ключей, повторяю...', true);
                            }} else {{
                                setPoolBodyMessage(proto, 'Не удалось загрузить пул ключей. Обновите вкладку или страницу.', true);
                            }}
                        }});
                        if (shouldRetry && !document.hidden) {{
                            refreshPoolData(3000, retryProtocols);
                        }}
                    }});
            }}, Math.max(0, Number(delayMs || 0)));
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
                details.textContent = cleanStatusText(status.details || '');
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

        function apiStatusRequiresAttention(apiStatus) {{
            const text = String(apiStatus || '').trim();
            if (!text) {{
                return false;
            }}
            const lower = text.toLowerCase();
            const failed = ['❌', 'не проходит', 'не отвечает', 'ошибка', 'failed', 'error', 'timeout', 'таймаут'].some(function(marker) {{
                return lower.indexOf(marker) !== -1;
            }});
            if (failed) {{
                return true;
            }}
            return !['подтверж', 'работает', 'ok', 'доступ'].some(function(marker) {{
                return lower.indexOf(marker) !== -1;
            }});
        }}

        function webStatusIsPending(apiStatus) {{
            const text = String(apiStatus || '');
            return [
                'Проверяется связь текущего режима',
                'Фоновая проверка связи выполняется',
                'Telegram API не ответил вовремя',
                'Статус обновится без перезагрузки страницы'
            ].some(function(marker) {{
                return text.indexOf(marker) !== -1;
            }});
        }}

        function topbarStatusFromSnapshot(snapshot) {{
            snapshot = snapshot || {{}};
            const progress = ENABLE_KEY_POOL ? freshPoolProbeProgress(snapshot.pool_probe_progress || {{}}) : {{}};
            const poolProbeVisible = ENABLE_KEY_POOL && !!snapshot.pool_probe_running && Number(progress.total || 0) > 0;
            const poolProbePaused = ENABLE_KEY_POOL && !!snapshot.pool_probe_paused && Number(progress.total || 0) > 0;
            if (poolProbeVisible || poolProbePaused) {{
                const progressLabel = poolProbeProgressLabel(progress.scope || '');
                const progressNote = progress.note ? String(progress.note) : '';
                const progressText = '⏳ ' + progressLabel + ': ' + (progress.checked || 0) + '/' + (progress.total || 0);
                return ['info', 'Статус обновляется', progressNote ? progressText + '. ' + progressNote : progressText, false];
            }}

            const health = snapshot.router_health || {{}};
            const usedPercent = Math.max(0, Math.min(100, Number(health.used_percent || 0)));
            if (usedPercent >= 85) {{
                return ['danger', 'Память роутера почти заполнена', 'Сейчас занято ' + usedPercent + '%; лучше остановить проверку пула или перезапустить сервис', botReady];
            }} else if (usedPercent >= 70) {{
                return ['warn', 'Память роутера под нагрузкой', 'Сейчас занято ' + usedPercent + '%; проверку большого пула стоит запускать осторожно', botReady];
            }}
            const web = snapshot.web || {{}};
            const apiStatus = String(web.api_status || '').trim();
            if (ENABLE_TELEGRAM && apiStatusRequiresAttention(apiStatus)) {{
                return ['warn', 'Telegram API требует внимания', apiStatus, botReady];
            }}
            const poolSummary = ENABLE_KEY_POOL ? (snapshot.pool_summary || {{}}) : {{}};
            if (ENABLE_KEY_POOL && String(poolSummary.note || '').toLowerCase().indexOf('не работает') !== -1) {{
                return ['warn', 'В пуле есть ключи с ошибками', 'Откройте вкладку "Ключи" и включите быстрый фильтр "Есть проблемы"', botReady];
            }}
            if (ENABLE_TELEGRAM) {{
                return ['ok', botReady ? 'Telegram-бот работает' : 'Telegram API отвечает', 'API отвечает, память роутера в норме', botReady];
            }}
            return ['ok', 'Проблем не найдено', ENABLE_KEY_POOL ? 'Память роутера в норме' : 'Память роутера в норме, веб-интерфейс готов к работе', false];
        }}

        function renderTopbarStatus(snapshot) {{
            const pill = document.getElementById('web-api-pill');
            if (!pill) {{
                return;
            }}
            if (snapshot && Object.prototype.hasOwnProperty.call(snapshot, 'bot_ready')) {{
                botReady = !!snapshot.bot_ready;
            }}
            const item = topbarStatusFromSnapshot(snapshot || {{}});
            const tone = item[0] || 'info';
            const showTelegramIcon = ENABLE_TELEGRAM && !!item[3];
            pill.className = 'api-pill topbar-status topbar-status-' + escapeHtml(tone);
            pill.setAttribute('data-bot-ready', showTelegramIcon ? 'true' : 'false');
            pill.innerHTML = (showTelegramIcon ? '<span class="topbar-status-icon topbar-status-icon-telegram" aria-hidden="true"></span>' : '') +
                '<span class="topbar-status-copy"><strong id="topbar-status-title">' + escapeHtml(item[1] || '') +
                '</strong><span id="topbar-status-text">' + escapeHtml(item[2] || '') + '</span></span>';
        }}

        function renderStatusAttention(snapshot) {{
            renderTopbarStatus(snapshot);
        }}

        function updateRouterHealth(health) {{
            if (!health) {{
                return;
            }}
            const memory = document.getElementById('router-memory-text');
            if (memory) {{
                memory.textContent = health.memory_text || 'недоступно';
            }}
            const note = document.getElementById('router-health-note');
            if (note) {{
                note.textContent = cleanStatusText(health.note || '');
                note.classList.toggle('hidden', !note.textContent);
            }}
            const dnsNote = document.getElementById('active-mode-dns-note');
            if (dnsNote) {{
                dnsNote.textContent = cleanStatusText(health.dns_note || '');
                dnsNote.classList.toggle('hidden', !dnsNote.textContent);
            }}
            const coreProxyNote = document.getElementById('router-core-proxy-note');
            if (coreProxyNote) {{
                coreProxyNote.textContent = cleanStatusText(health.core_proxy_note || '');
                coreProxyNote.classList.toggle('hidden', !coreProxyNote.textContent);
            }}
            const telegramCallNote = document.getElementById('router-telegram-call-note');
            if (telegramCallNote) {{
                telegramCallNote.textContent = cleanStatusText(health.telegram_call_note || '');
                telegramCallNote.classList.toggle('hidden', !telegramCallNote.textContent);
            }}
            const meter = document.getElementById('router-memory-meter');
            if (meter) {{
                const percent = Math.max(0, Math.min(100, Number(health.used_percent || 0)));
                const fill = meter.querySelector('span');
                meter.classList.toggle('warn', percent >= 70 && percent < 85);
                meter.classList.toggle('danger', percent >= 85);
                meter.setAttribute('title', 'Занято памяти: ' + percent + '%');
                if (fill) {{
                    fill.style.width = percent + '%';
                }}
            }}
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
            setOptionalText('web-socks-details', web.socks_details || '');
            const fallbackText = web.fallback_reason && web.proxy_mode === 'none'
                ? 'Последняя неудачная попытка прокси: ' + web.fallback_reason
                : '';
            setOptionalText('web-fallback-reason', fallbackText);

            const progress = ENABLE_KEY_POOL ? (snapshot.pool_probe_progress || {{}}) : {{}};
            const poolProbeActive = ENABLE_KEY_POOL && !!snapshot.pool_probe_running && Number(progress.total || 0) > 0;
            const poolProbePaused = ENABLE_KEY_POOL && !!snapshot.pool_probe_paused && Number(progress.total || 0) > 0;
            updatePoolProbeControls(poolProbeActive, poolProbePaused);
            let pending = webStatusIsPending(web.api_status || '');
            const protocols = snapshot.protocols || {{}};
            Object.keys(protocols).forEach(function(proto) {{
                const status = protocols[proto];
                updateProtocolStatus(proto, status);
                if (proto === web.proxy_mode && status && (status.label === 'Проверяется' || status.api_pending)) {{
                    pending = true;
                }}
            }});
            const poolSummary = ENABLE_KEY_POOL ? (snapshot.pool_summary || null) : null;
            updatePoolSummaryBlock(poolSummary, progress, poolProbeActive, poolProbePaused);
            updateRouterHealth(snapshot.router_health);
            renderStatusAttention(snapshot);
            if (ENABLE_KEY_POOL && snapshot.pools) {{
                updatePoolStatus(snapshot.pools);
            }}
            if (ENABLE_KEY_POOL && poolProbeWasRunning && !poolProbeActive && !poolProbePaused) {{
                refreshPoolData(500);
            }}
            poolProbeWasRunning = poolProbeActive || poolProbePaused;
            if (poolProbeActive || poolProbePaused) {{
                schedulePoolProbePolling(POOL_PROBE_STATUS_POLL_MS);
            }}
            return pending;
        }}

        function pollStatus() {{
            if (!ENABLE_LIVE_STATUS || document.hidden) {{
                statusPollTimer = null;
                return;
            }}
            statusPollTimer = null;
            fetch('/api/status?compact=1&lite=1', {{
                headers: {{'Accept': 'application/json'}},
                cache: 'no-store'
            }})
                .then(function(response) {{ return response.json(); }})
                .then(function(payload) {{
                    const pending = updateWebStatus(payload);
                    if (pending) {{
                        statusPollUntil = Math.max(statusPollUntil, Date.now() + 30000);
                    }} else {{
                        statusPollUntil = 0;
                    }}
                }})
                .catch(function() {{}})
                .finally(function() {{
                    if (!document.hidden) {{
                        const delay = Date.now() < statusPollUntil ? STATUS_ACTIVE_POLL_MS : STATUS_IDLE_POLL_MS;
                        statusPollTimer = window.setTimeout(pollStatus, delay);
                    }}
                }});
        }}

        function scheduleStatusPolling(durationMs, initialDelayMs) {{
            if (!ENABLE_LIVE_STATUS) {{
                return;
            }}
            statusPollUntil = Math.max(statusPollUntil, Date.now() + durationMs);
            if (!statusPollTimer && !document.hidden) {{
                const initialDelay = Math.max(0, Number(initialDelayMs || 0));
                if (initialDelay > 0) {{
                    statusPollTimer = window.setTimeout(pollStatus, initialDelay);
                }} else {{
                    pollStatus();
                }}
            }}
        }}

        function refreshStatusSoon(delayMs, durationMs) {{
            if (!ENABLE_LIVE_STATUS) {{
                return;
            }}
            statusPollUntil = Math.max(statusPollUntil, Date.now() + (durationMs || 30000));
            window.setTimeout(function() {{
                if (statusPollTimer) {{
                    window.clearTimeout(statusPollTimer);
                    statusPollTimer = null;
                }}
                if (!document.hidden) {{
                    pollStatus();
                }}
            }}, Math.max(0, Number(delayMs || 0)));
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

        function setCommandRunningLayout(running) {{
            if (document.documentElement) {{
                document.documentElement.classList.toggle('command-running', !!running);
            }}
            if (document.body) {{
                document.body.classList.toggle('command-running', !!running);
            }}
        }}

        function formatCommandDuration(seconds) {{
            const safeSeconds = Math.max(0, Math.round(Number(seconds || 0)));
            const minutes = Math.floor(safeSeconds / 60);
            const rest = safeSeconds % 60;
            if (minutes >= 60) {{
                const hours = Math.floor(minutes / 60);
                const hourMinutes = minutes % 60;
                return hours + ':' + String(hourMinutes).padStart(2, '0') + ':' + String(rest).padStart(2, '0');
            }}
            return minutes + ':' + String(rest).padStart(2, '0');
        }}

        function commandElapsedSeconds(state) {{
            const startedAt = Number((state && state.started_at) || 0);
            if (!startedAt) {{
                return 0;
            }}
            return Math.max(0, (Date.now() / 1000) - startedAt);
        }}

        function commandTimerText(state) {{
            if (!state || state.command !== 'update' || !state.running) {{
                return '';
            }}
            const elapsed = commandElapsedSeconds(state);
            const expected = Math.max(0, Number(state.expected_seconds || 0));
            if (expected > 0) {{
                const expectedWithRestart = expected + 15;
                if (elapsed <= expectedWithRestart + 90) {{
                    return 'Прошло ' + formatCommandDuration(elapsed) + ' · в среднем ' + formatCommandDuration(expectedWithRestart);
                }}
                return 'Прошло ' + formatCommandDuration(elapsed) + ' · дольше среднего ' + formatCommandDuration(expectedWithRestart);
            }}
            return 'Прошло ' + formatCommandDuration(elapsed);
        }}

        function updateCommandProgress(state) {{
            const progressBlock = document.querySelector('#web-command-status [data-command-progress]');
            if (!progressBlock) {{
                return;
            }}
            const isUpdate = !!state && state.command === 'update' && !!state.running;
            progressBlock.classList.toggle('hidden', !isUpdate);
            if (!isUpdate) {{
                return;
            }}
            const label = progressBlock.querySelector('[data-command-progress-label]');
            if (label) {{
                label.textContent = state.progress_label || (state.running ? 'Обновление выполняется' : 'Обновление завершено');
            }}
            const timer = progressBlock.querySelector('[data-command-progress-timer]');
            if (timer) {{
                timer.textContent = state.running ? commandTimerText(state) : 'Готово';
            }}
        }}

        function stopCommandTimer() {{
            if (commandTimer) {{
                window.clearInterval(commandTimer);
                commandTimer = null;
            }}
            commandTimerState = null;
        }}

        function startCommandTimer(state) {{
            commandTimerState = Object.assign({{}}, state || {{}});
            updateCommandProgress(commandTimerState);
            if (commandTimer) {{
                return;
            }}
            commandTimer = window.setInterval(function() {{
                if (!commandTimerState || !commandTimerState.running) {{
                    stopCommandTimer();
                    return;
                }}
                updateCommandProgress(commandTimerState);
            }}, 1000);
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
                setCommandRunningLayout(false);
                stopCommandTimer();
                return false;
            }}
            if (!state || !state.label) {{
                block.classList.add('hidden');
                setCommandRunningLayout(false);
                stopCommandTimer();
                return false;
            }}
            block.classList.remove('hidden');
            setCommandRunningLayout(!!state.running);
            const title = block.querySelector('strong');
            if (title) {{
                title.textContent = (state.running ? 'Команда выполняется: ' : 'Последняя команда: ') + state.label;
            }}
            const output = block.querySelector('.log-output');
            if (output) {{
                output.textContent = state.result || ('⏳ ' + state.label + ' ещё выполняется. Статус обновится без перезагрузки страницы');
            }}
            updateCommandProgress(state);
            if (state.running && state.command === 'update') {{
                startCommandTimer(state);
            }} else {{
                stopCommandTimer();
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
                details.textContent = text || 'Проверка Telegram API, YouTube и дополнительных сервисов выполняется в фоне';
            }}
            const icons = card.querySelector('[data-protocol-status-icons]');
            if (icons) {{
                icons.innerHTML = '';
            }}
        }}

        function markPoolKeyActive(proto, keyId) {{
            document.querySelectorAll('[data-pool-row]').forEach(function(item) {{
                if (item.dataset.protocol !== proto) {{
                    return;
                }}
                const isActive = item.dataset.keyId === keyId;
                item.classList.toggle('pool-row-active', isActive);
                item.dataset.active = isActive ? '1' : '0';
                const meta = item.querySelector('[data-pool-key-meta]');
                if (meta) {{
                    meta.textContent = isActive ? 'активен' : '';
                }}
                const mobileMeta = item.querySelector('[data-pool-mobile-active]');
                if (mobileMeta) {{
                    mobileMeta.textContent = meta ? meta.textContent : '';
                }}
            }});
            applyPoolView(proto, true);
        }}

        function setButtonBusy(button, busy) {{
            if (!button) {{
                return;
            }}
            if (busy) {{
                button.dataset.originalHtml = button.innerHTML;
                button.disabled = true;
                button.textContent = 'Выполняется...';
            }} else {{
                button.disabled = false;
                if (button.dataset.originalHtml) {{
                    button.innerHTML = button.dataset.originalHtml;
                    delete button.dataset.originalHtml;
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
            messageNode.textContent = message || 'Подтвердите действие';
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

        function metricMb(kb) {{
            const value = Number(kb || 0);
            if (!value) {{
                return '-';
            }}
            return Math.round(value / 1024) + ' MB';
        }}

        function metricPercent(value) {{
            const number = Number(value || 0);
            if (!number) {{
                return '0%';
            }}
            return (Math.round(number * 100) / 100) + '%';
        }}

        function updateRouterMetricsPanel(payload) {{
            payload = payload || {{}};
            const load = payload.load || {{}};
            const processes = payload.processes || {{}};
            const bot = processes.bot || {{}};
            const xray = processes.xray || {{}};
            const status = document.getElementById('router-metrics-status');
            if (status) {{
                const date = payload.timestamp ? new Date(Number(payload.timestamp) * 1000) : null;
                status.textContent = date ? 'Обновлено ' + date.toLocaleTimeString() : 'Метрики обновлены';
            }}
            const loadText = [load.load1, load.load5, load.load15].map(function(item) {{
                return Number(item || 0).toFixed(2);
            }}).join(' / ');
            setOptionalText('router-metrics-load', loadText);
            setOptionalText('router-metrics-bot-rss', metricMb(bot.rss_kb));
            setOptionalText('router-metrics-bot-cpu', metricPercent(bot.cpu_percent));
            setOptionalText('router-metrics-xray-rss', xray.running ? metricMb(xray.rss_kb) : 'не запущен');
            setOptionalText('router-metrics-xray-cpu', xray.running ? metricPercent(xray.cpu_percent) : '-');
        }}

        function fetchRouterMetrics() {{
            const status = document.getElementById('router-metrics-status');
            if (status) {{
                status.textContent = 'Загружаю метрики...';
            }}
            return fetch('/api/router_metrics?compact=1', {{
                headers: {{'Accept': 'application/json'}},
                cache: 'no-store'
            }})
                .then(function(response) {{ return response.json(); }})
                .then(updateRouterMetricsPanel)
                .catch(function() {{
                    if (status) {{
                        status.textContent = 'Метрики временно недоступны';
                    }}
                }});
        }}

        function fetchEventHistory() {{
            const container = document.querySelector('[data-event-history-list]');
            if (container && !container.querySelector('.event-history-item')) {{
                container.innerHTML = '<section class="panel event-history-panel"><p class="section-subtitle">Загружаю историю...</p></section>';
            }}
            return fetch('/api/event_history', {{
                headers: {{'Accept': 'application/json'}},
                cache: 'no-store'
            }})
                .then(function(response) {{ return response.json(); }})
                .then(function(payload) {{
                    if (container) {{
                        container.innerHTML = payload.html || '';
                    }}
                }})
                .catch(function() {{
                    if (container) {{
                        container.innerHTML = '<section class="panel event-history-panel"><p class="section-subtitle">История временно недоступна</p></section>';
                    }}
                }});
        }}

        function setupEventHistoryPanel() {{
            const modal = document.getElementById('event-history-modal');
            const openButtons = document.querySelectorAll('[data-event-history-open]');
            if (!modal || !openButtons.length) {{
                return;
            }}
            const closeButtons = modal.querySelectorAll('[data-event-history-close]');
            const refreshButtons = modal.querySelectorAll('[data-router-metrics-refresh]');
            let metricsLoaded = false;
            let historyLoaded = false;
            let lockedScrollY = 0;
            let scrollLocked = false;
            function lockPageScroll() {{
                if (scrollLocked) {{
                    return;
                }}
                lockedScrollY = window.scrollY || document.documentElement.scrollTop || 0;
                document.body.style.position = 'fixed';
                document.body.style.top = '-' + lockedScrollY + 'px';
                document.body.style.left = '0';
                document.body.style.right = '0';
                document.body.style.width = '100%';
                scrollLocked = true;
            }}
            function unlockPageScroll() {{
                if (!scrollLocked) {{
                    return;
                }}
                document.body.style.position = '';
                document.body.style.top = '';
                document.body.style.left = '';
                document.body.style.right = '';
                document.body.style.width = '';
                window.scrollTo(0, lockedScrollY);
                scrollLocked = false;
            }}
            function openPanel() {{
                modal.classList.remove('hidden');
                document.body.classList.add('event-history-open');
                lockPageScroll();
                if (!historyLoaded) {{
                    historyLoaded = true;
                    fetchEventHistory();
                }}
                if (!metricsLoaded) {{
                    metricsLoaded = true;
                    fetchRouterMetrics();
                }}
            }}
            function closePanel() {{
                modal.classList.add('hidden');
                document.body.classList.remove('event-history-open');
                unlockPageScroll();
            }}
            openButtons.forEach(function(button) {{
                button.addEventListener('click', openPanel);
            }});
            closeButtons.forEach(function(button) {{
                button.addEventListener('click', closePanel);
            }});
            refreshButtons.forEach(function(button) {{
                button.addEventListener('click', function() {{
                    metricsLoaded = true;
                    fetchRouterMetrics();
                }});
            }});
            modal.addEventListener('click', function(event) {{
                if (event.target === modal) {{
                    closePanel();
                }}
            }});
            document.addEventListener('keydown', function(event) {{
                if (event.key === 'Escape' && !modal.classList.contains('hidden')) {{
                    closePanel();
                }}
            }});
        }}

        function closeServiceRouteMenus(exceptMenu) {{
            document.querySelectorAll('.service-route-menu[open]').forEach(function(menu) {{
                if (menu !== exceptMenu) {{
                    menu.open = false;
                    menu.classList.remove('drop-up');
                }}
            }});
        }}

        function positionServiceRouteMenu(menu) {{
            if (!menu || !menu.open) {{
                return;
            }}
            if (window.matchMedia && window.matchMedia('(max-width: 720px)').matches) {{
                menu.classList.remove('drop-up');
                return;
            }}
            const list = menu.querySelector('.service-route-menu-list');
            if (!list) {{
                return;
            }}
            menu.classList.remove('drop-up');
            list.style.maxHeight = '';
            list.style.overflowY = '';
            const rect = list.getBoundingClientRect();
            const viewportPadding = 12;
            if (rect.bottom > window.innerHeight - viewportPadding) {{
                menu.classList.add('drop-up');
            }}
            const adjustedRect = list.getBoundingClientRect();
            if (adjustedRect.top < viewportPadding || adjustedRect.bottom > window.innerHeight - viewportPadding) {{
                const available = Math.max(96, window.innerHeight - (viewportPadding * 2));
                list.style.maxHeight = available + 'px';
                list.style.overflowY = 'auto';
            }}
        }}

        function scheduleServiceRouteMenuPosition(menu) {{
            positionServiceRouteMenu(menu);
            window.requestAnimationFrame(function() {{
                positionServiceRouteMenu(menu);
            }});
            window.setTimeout(function() {{
                positionServiceRouteMenu(menu);
            }}, 80);
        }}

        function setupServiceRouteMenus(root) {{
            const scope = root || document;
            scope.querySelectorAll('.service-route-menu').forEach(function(menu) {{
                if (menu.dataset.routeMenuBound === '1') {{
                    return;
                }}
                menu.dataset.routeMenuBound = '1';
                menu.addEventListener('toggle', function() {{
                    if (menu.open) {{
                        closeServiceRouteMenus(menu);
                        scheduleServiceRouteMenuPosition(menu);
                    }} else {{
                        menu.classList.remove('drop-up');
                    }}
                }});
            }});
        }}

        function updateServiceRouteTools(html) {{
            if (typeof html !== 'string') {{
                return;
            }}
            document.querySelectorAll('[data-route-tools-root]').forEach(function(root) {{
                root.innerHTML = html;
                setupServiceRouteMenus(root);
                setupAsyncForms(root);
            }});
        }}

        function refreshDeferredServiceRouteTools() {{
            const roots = Array.from(document.querySelectorAll('[data-route-tools-root]')).filter(function(root) {{
                return root.querySelector('[data-route-tools-deferred]');
            }});
            if (!roots.length) {{
                return;
            }}
            fetch('/api/service_routes', {{
                credentials: 'same-origin',
                cache: 'no-store'
            }}).then(function(response) {{
                if (!response.ok) {{
                    throw new Error('service routes failed');
                }}
                return response.json();
            }}).then(function(payload) {{
                if (payload && payload.route_tools_html) {{
                    updateServiceRouteTools(payload.route_tools_html);
                }}
            }}).catch(function() {{}});
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
                    const keyId = formData.get('key_id') || '';
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
                        showActionMessage('⏳ Выполняется действие. Страница останется на месте', true);
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
                            showActionMessage(payload.result || 'Готово', ok, {{
                                autoHide: ok,
                                delayMs: action === 'command' ? 5000 : 9000
                            }});
                            if (ok && (action === 'service-route' || action === 'custom-check-delete' || action === 'custom-check-add')) {{
                                const routeMenu = form.closest('.service-route-menu');
                                if (routeMenu) {{
                                    routeMenu.open = false;
                                }}
                            }}
                            if (ok && proto && action === 'install') {{
                                const card = form.closest('[data-protocol-card]');
                                const textarea = card ? card.querySelector('[data-key-textarea]') : null;
                                if (textarea) {{
                                    textarea.value = key;
                                }}
                            }}
                            if (ok && proto && action === 'pool-apply') {{
                                markPoolKeyActive(proto, String(payload.key_id || keyId || ''));
                                const card = form.closest('[data-protocol-card]');
                                const textarea = card ? card.querySelector('[data-key-textarea]') : null;
                                if (textarea) {{
                                    textarea.value = '';
                                    textarea.placeholder = 'Ключ применён из пула; значение скрыто в ответе. Обновите страницу, чтобы открыть активный ключ.';
                                }}
                            }}
                            if (payload.route_tools_html) {{
                                updateServiceRouteTools(payload.route_tools_html);
                            }}
                            if (payload.custom_checks) {{
                                renderCustomChecks(payload.custom_checks);
                            }}
                            if (payload.pools || payload.pool_summary) {{
                                applyPoolPayload(payload);
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
                            if (action !== 'set-app-mode' && payload.reload_after_ms) {{
                                window.setTimeout(function() {{
                                    window.location.reload();
                                }}, Number(payload.reload_after_ms) || 900);
                            }}
                            const poolMutationAction = ['pool-add', 'pool-delete', 'pool-clear', 'pool-subscribe'].indexOf(action) !== -1;
                            if (action === 'pool-probe-cancel') {{
                                refreshPoolData(1200);
                                scheduleStatusPolling(15000);
                            }} else if (action === 'pool-probe') {{
                                refreshPoolData(1200);
                                schedulePoolProbePolling(1200);
                                scheduleStatusPolling(15000);
                            }} else if (poolMutationAction) {{
                                refreshPoolData(1200, proto ? [proto] : null);
                                if (payload.pool_probe_running || payload.pool_probe_paused) {{
                                    schedulePoolProbePolling(1200);
                                }}
                                refreshStatusSoon(600, 30000);
                            }} else if (action === 'command') {{
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
                document.querySelectorAll('.service-route-menu[open]').forEach(function(menu) {{
                    if (!menu.contains(event.target)) {{
                        menu.open = false;
                        menu.classList.remove('drop-up');
                    }}
                }});
            }});
            document.addEventListener('keydown', function(event) {{
                if (event.key === 'Escape') {{
                    closeServiceRouteMenus();
                }}
            }});
            document.addEventListener('visibilitychange', function() {{
                if (!document.hidden) {{
                    scheduleStatusPolling(30000);
                    if (poolProbeWasRunning) {{
                        schedulePoolProbePolling(0);
                    }}
                }}
            }});
            setupViewNavigation();
            setupProtocolTabs();
            setupSegmentedTabs('.list-tab', '[data-list-panel]', 'data-list-target', 'data-list-panel', 'router-active-list');
            setupProtocolSubtabs();
            setupPoolControls();
            setupServiceRouteMenus();
            setupEventHistoryPanel();
            refreshDeferredServiceRouteTools();
            setupLiquidPointer();
            setupAsyncForms();
            const actionBlock = document.getElementById('web-action-message');
            if (actionBlock && !actionBlock.classList.contains('hidden')) {{
                scheduleActionMessageHide(9000);
            }}
            if (INITIAL_STATUS_PENDING) {{
                scheduleStatusPolling(30000);
                if (ENABLE_KEY_POOL) {{
                    schedulePoolProbePolling(0);
                }}
            }} else if (ENABLE_LIVE_STATUS) {{
                scheduleStatusPolling(STATUS_IDLE_POLL_MS, STATUS_IDLE_POLL_MS);
            }}
            if (INITIAL_COMMAND_RUNNING) {{
                setCommandRunningLayout(true);
                pollCommandState();
            }}
        }});
'''
