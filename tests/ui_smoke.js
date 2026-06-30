const { chromium, devices } = require('playwright');

const targetUrl = process.env.BYPASS_UI_URL || 'http://192.168.1.1:8080/';
const chromeExecutable = process.env.CHROME_EXECUTABLE || undefined;
const httpCredentials = process.env.BYPASS_UI_USERNAME && process.env.BYPASS_UI_PASSWORD
  ? { username: process.env.BYPASS_UI_USERNAME, password: process.env.BYPASS_UI_PASSWORD }
  : undefined;
const leakedFixtureKeys = [
  'vless://fixture-backup-vless',
  'vless://fixture-backup-vless2',
];
const allAppModes = [
  { mode: 'advanced', expectPool: true, expectCustomChecks: true, expectTelegram: true },
  { mode: 'simple', expectPool: false, expectCustomChecks: false, expectTelegram: true },
  { mode: 'web_only', expectPool: true, expectCustomChecks: true, expectTelegram: false },
];
const requestedModes = (process.env.BYPASS_UI_MODES || '')
  .split(',')
  .map((mode) => mode.trim())
  .filter(Boolean);
const appModes = requestedModes.length
  ? requestedModes
    .map((mode) => allAppModes.find((config) => config.mode === mode))
    .filter(Boolean)
  : allAppModes;
if (!appModes.length) {
  throw new Error(`No known UI modes selected: ${requestedModes.join(', ')}`);
}

function urlForMode(mode) {
  const url = new URL(targetUrl);
  url.searchParams.set('mode', mode);
  return url.toString();
}

function modeConfigMatches(pageConfig, modeConfig) {
  return Boolean(pageConfig.enableKeyPool) === modeConfig.expectPool
    && Boolean(pageConfig.enableCustomChecks) === modeConfig.expectCustomChecks
    && Boolean(pageConfig.enableTelegram) === modeConfig.expectTelegram;
}

async function readPageConfig(page) {
  return page.evaluate(() => window.BK_APP_CONFIG || {});
}

async function gotoModePage(page, modeConfig, label, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      await page.goto(urlForMode(modeConfig.mode), { waitUntil: 'domcontentloaded', timeout: 15000 });
      await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
      const pageConfig = await readPageConfig(page);
      if (modeConfigMatches(pageConfig, modeConfig)) {
        return pageConfig;
      }
      lastError = new Error(`${label}: mode flags do not match yet ${JSON.stringify(pageConfig)}`);
    } catch (error) {
      lastError = error;
    }
    await page.waitForTimeout(1500);
  }
  throw lastError || new Error(`${label}: timed out waiting for mode ${modeConfig.mode}`);
}

async function switchAppModeIfNeeded(page, modeConfig, label) {
  let pageConfig = await readPageConfig(page);
  if (modeConfigMatches(pageConfig, modeConfig)) {
    return pageConfig;
  }
  const toggle = page.locator('#app-mode-toggle-button');
  if (await toggle.count() !== 1) {
    throw new Error(`${label}: mode mismatch and app mode toggle is missing`);
  }
  await toggle.click();
  await assertVisibleBox(page, '#app-mode-picker:not(.hidden)', `${label} app mode picker`);
  const modeButton = page.locator(`#app-mode-picker [data-app-mode-value="${modeConfig.mode}"]`);
  if (await modeButton.count() !== 1) {
    throw new Error(`${label}: app mode button ${modeConfig.mode} is missing`);
  }
  await modeButton.click();
  const accept = page.locator('#confirm-accept');
  if (await accept.isVisible({ timeout: 3000 }).catch(() => false)) {
    await accept.click();
  }
  await page.waitForTimeout(7000);
  return gotoModePage(page, modeConfig, label, 60000);
}

function watchPage(page, label) {
  const failures = [];
  page.on('pageerror', (error) => failures.push(`${label}: page error: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') {
      failures.push(`${label}: console error: ${message.text()}`);
    }
  });
  page.on('response', (response) => {
    const url = response.url();
    const watched = url.includes('/api/') || url.includes('/static/app.');
    if (watched && !response.ok()) {
      failures.push(`${label}: ${response.status()} ${url}`);
    }
  });
  return failures;
}

function assertNoPageFailures(failures) {
  if (failures.length) {
    throw new Error(failures.join('\n'));
  }
}

function emitGitHubErrorAnnotation(error) {
  if (process.env.GITHUB_ACTIONS !== 'true') {
    return;
  }
  const text = String((error && error.stack) || error || 'Unknown UI smoke failure')
    .replace(/%/g, '%25')
    .replace(/\r/g, '%0D')
    .replace(/\n/g, '%0A');
  console.error(`::error title=UI smoke failed::${text}`);
}

function safeTargetLabel() {
  try {
    const url = new URL(targetUrl);
    url.username = '';
    url.password = '';
    return url.toString();
  } catch {
    return '[invalid target url]';
  }
}

async function assertNoHorizontalOverflow(page, label) {
  const overflow = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    viewport: document.documentElement.clientWidth,
    offenders: Array.from(document.querySelectorAll('body *'))
      .filter((node) => node.scrollWidth > node.clientWidth + 2 && getComputedStyle(node).overflowX === 'visible')
      .slice(0, 8)
      .map((node) => ({
        tag: node.tagName,
        className: node.className,
        text: (node.textContent || '').trim().slice(0, 80),
        scrollWidth: node.scrollWidth,
        clientWidth: node.clientWidth,
      })),
  }));
  if (overflow.body > overflow.viewport + 2) {
    throw new Error(`${label}: horizontal overflow ${overflow.body}/${overflow.viewport}: ${JSON.stringify(overflow.offenders)}`);
  }
}

async function assertMobileStatusGaps(page, label) {
  const expected = 8;
  const gaps = await page.evaluate(() => {
    const visibleBox = (node) => {
      if (!node) {
        return null;
      }
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      if (style.display === 'none' || style.visibility === 'hidden' || rect.width < 2 || rect.height < 2) {
        return null;
      }
      return { top: rect.top, bottom: rect.bottom };
    };
    const labelFor = (node) => (
      node.className && typeof node.className === 'string'
        ? node.className.split(/\s+/).filter(Boolean).slice(0, 3).join('.')
        : node.tagName.toLowerCase()
    );
    const result = [];
    const topbar = visibleBox(document.querySelector('.topbar'));
    const statusView = document.querySelector('[data-view="status"].active');
    const children = statusView ? Array.from(statusView.children).map((node) => ({ node, box: visibleBox(node) })).filter((item) => item.box) : [];
    if (topbar && children[0]) {
      result.push({ name: 'topbar/status', value: Math.round(children[0].box.top - topbar.bottom) });
    }
    for (let index = 1; index < children.length; index += 1) {
      result.push({
        name: `${labelFor(children[index - 1].node)}/${labelFor(children[index].node)}`,
        value: Math.round(children[index].box.top - children[index - 1].box.bottom),
      });
    }
    document.querySelectorAll('[data-view="status"].active .status-dashboard-column').forEach((column, columnIndex) => {
      const cards = Array.from(column.children).map((node) => ({ node, box: visibleBox(node) })).filter((item) => item.box);
      for (let index = 1; index < cards.length; index += 1) {
        result.push({
          name: `dashboard-${columnIndex}:${labelFor(cards[index - 1].node)}/${labelFor(cards[index].node)}`,
          value: Math.round(cards[index].box.top - cards[index - 1].box.bottom),
        });
      }
    });
    return result;
  });
  const bad = gaps.filter((gap) => Math.abs(gap.value - expected) > 2);
  if (bad.length) {
    throw new Error(`${label}: mobile status gaps should be ${expected}px: ${JSON.stringify({ gaps, bad })}`);
  }
}

async function assertVisibleBox(page, selector, label) {
  const box = await page.locator(selector).first().boundingBox();
  if (!box || box.width < 2 || box.height < 2) {
    throw new Error(`${label}: ${selector} is not visibly sized`);
  }
  return box;
}

async function assertNoVisibleMojibake(page, label) {
  const text = await page.locator('body').evaluate((node) => node.innerText || '');
  const markers = ['Рџ', 'Р ', 'Р—', 'Р', 'СЏ', 'СЋ', 'СЃ', 'С‚', 'РµР', 'РЅР'];
  const found = markers.find((marker) => text.includes(marker));
  if (found) {
    throw new Error(`${label}: visible text contains mojibake marker ${found}`);
  }
}

async function assertEventHistoryScrollLocked(page, label) {
  const list = page.locator('#event-history-modal:not(.hidden) .event-history-list').first();
  const box = await list.boundingBox();
  if (!box || box.height < 40) {
    throw new Error(`${label}: event history list is not scrollable-sized`);
  }
  const before = await page.evaluate(() => {
    const listNode = document.querySelector('#event-history-modal:not(.hidden) .event-history-list');
    return {
      windowY: window.scrollY,
      listTop: listNode ? listNode.scrollTop : -1,
      bodyPosition: getComputedStyle(document.body).position,
      bodyClass: document.body.classList.contains('event-history-open'),
      listOverflowY: listNode ? getComputedStyle(listNode).overflowY : '',
      listScrollHeight: listNode ? listNode.scrollHeight : 0,
      listClientHeight: listNode ? listNode.clientHeight : 0,
    };
  });
  if (!before.bodyClass || before.bodyPosition !== 'fixed') {
    throw new Error(`${label}: event history did not lock page scroll ${JSON.stringify(before)}`);
  }
  if (before.listOverflowY !== 'auto' || before.listScrollHeight <= before.listClientHeight + 8) {
    throw new Error(`${label}: event history list is not independently scrollable ${JSON.stringify(before)}`);
  }
  await page.mouse.move(box.x + Math.min(24, box.width / 2), box.y + Math.min(80, box.height / 2));
  await page.mouse.wheel(0, Math.max(220, Math.floor(box.height * 0.9)));
  await page.waitForTimeout(120);
  const after = await page.evaluate(() => {
    const listNode = document.querySelector('#event-history-modal:not(.hidden) .event-history-list');
    return {
      windowY: window.scrollY,
      listTop: listNode ? listNode.scrollTop : -1,
    };
  });
  if (after.windowY !== before.windowY || after.listTop <= before.listTop) {
    throw new Error(`${label}: history scroll moved page instead of list ${JSON.stringify({ before, after })}`);
  }
}

async function assertNoBrokenImages(page, label) {
  const broken = await page.evaluate(() => (
    Array.from(document.images)
      .filter((img) => !img.complete || img.naturalWidth < 1 || img.naturalHeight < 1)
      .map((img) => ({
        alt: img.alt || '',
        src: img.getAttribute('src') || '',
      }))
  ));
  if (broken.length) {
    throw new Error(`${label}: broken images ${JSON.stringify(broken)}`);
  }
}

async function assertPoolKeysAreMasked(page, label) {
  const leakage = await page.evaluate((needles) => ({
    dataKeyCount: document.querySelectorAll('[data-key]').length,
    poolLegacyKeyInputs: document.querySelectorAll('[data-pool-row] input[name="key"]').length,
    leakedNeedles: needles.filter((needle) => document.documentElement.outerHTML.includes(needle)),
  }), leakedFixtureKeys);
  if (leakage.dataKeyCount || leakage.poolLegacyKeyInputs || leakage.leakedNeedles.length) {
    throw new Error(`${label}: pool key leakage ${JSON.stringify(leakage)}`);
  }
}

async function assertActivePoolRowPinned(page, protocol, label) {
  const selector = `[data-protocol-panel="${protocol}"].active [data-pool-body="${protocol}"]`;
  await page.waitForFunction((bodySelector) => {
    const body = document.querySelector(bodySelector);
    return body && !body.hasAttribute('data-pool-deferred') && body.querySelector('[data-pool-row]');
  }, selector, { timeout: 10000 });
  const rows = await page.locator(selector).evaluate((body) => (
    Array.from(body.querySelectorAll('[data-pool-row]')).slice(0, 3).map((row) => ({
      active: row.dataset.active,
      poolIndex: Number(row.dataset.poolIndex || 0),
      text: (row.textContent || '').trim().slice(0, 80),
    }))
  ));
  if (!rows.length || rows[0].active !== '1') {
    throw new Error(`${label}: active pool row is not pinned first: ${JSON.stringify(rows)}`);
  }
  const activeIndex = rows[0].poolIndex;
  const expectedTail = Array.from({ length: rows.length + 1 }, (_, index) => index)
    .filter((index) => index !== activeIndex)
    .slice(0, Math.max(0, rows.length - 1));
  const actualTail = rows.slice(1).map((row) => row.poolIndex);
  if (actualTail.some((index, offset) => index !== expectedTail[offset])) {
    throw new Error(`${label}: original pool order after active row is wrong: ${JSON.stringify(rows)}`);
  }
}

async function assertSubscriptionImportLayout(page, label) {
  const layout = await page.evaluate(() => {
    const panel = document.querySelector('[data-protocol-panel="vless2"].active [data-subview="subscription"].active');
    const addForm = panel ? panel.querySelector('.pool-add-form') : null;
    const subscribeForm = panel ? panel.querySelector('.pool-subscribe-form') : null;
    const textarea = addForm ? addForm.querySelector('textarea[name="keys"]') : null;
    const addButton = addForm ? addForm.querySelector('button[type="submit"]') : null;
    const rect = (node) => {
      if (!node) {
        return null;
      }
      const box = node.getBoundingClientRect();
      return {
        left: Math.round(box.left),
        top: Math.round(box.top),
        right: Math.round(box.right),
        bottom: Math.round(box.bottom),
        width: Math.round(box.width),
        height: Math.round(box.height),
      };
    };
    const intersection = (a, b) => {
      if (!a || !b) {
        return 0;
      }
      const width = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
      const height = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
      return width * height;
    };
    const panelRect = rect(panel);
    const addRect = rect(addForm);
    const subscribeRect = rect(subscribeForm);
    const textareaRect = rect(textarea);
    const buttonRect = rect(addButton);
    return {
      panel: panelRect,
      addForm: addRect,
      subscribeForm: subscribeRect,
      textarea: textareaRect,
      addButton: buttonRect,
      panelOverflow: panel ? panel.scrollWidth - panel.clientWidth : null,
      formOverlap: intersection(addRect, subscribeRect),
      textareaSubscribeOverlap: intersection(textareaRect, subscribeRect),
      textareaInsideAdd: Boolean(addRect && textareaRect && textareaRect.left >= addRect.left - 1 && textareaRect.right <= addRect.right + 1),
      buttonInsideAdd: Boolean(addRect && buttonRect && buttonRect.left >= addRect.left - 1 && buttonRect.right <= addRect.right + 1),
    };
  });
  if (!layout.panel || !layout.addForm || !layout.subscribeForm || !layout.textarea || !layout.addButton) {
    throw new Error(`${label}: subscription import layout is missing nodes ${JSON.stringify(layout)}`);
  }
  if (layout.panelOverflow > 2) {
    throw new Error(`${label}: subscription import overflows horizontally ${JSON.stringify(layout)}`);
  }
  if (layout.formOverlap > 2 || layout.textareaSubscribeOverlap > 2) {
    throw new Error(`${label}: subscription import blocks overlap ${JSON.stringify(layout)}`);
  }
  if (!layout.textareaInsideAdd || !layout.buttonInsideAdd) {
    throw new Error(`${label}: add-key controls leave their card ${JSON.stringify(layout)}`);
  }
}

async function clickLazyProtocol(page, protocol, label) {
  const tab = page.locator(`.protocol-tab[data-protocol-target="${protocol}"]`);
  if (await tab.count() !== 1) {
    throw new Error(`${label}: expected one ${protocol} protocol tab`);
  }
  await tab.click();
  const panel = page.locator(`[data-protocol-panel="${protocol}"].active:not([data-protocol-panel-lazy="1"])`);
  await panel.waitFor({ state: 'visible', timeout: 10000 });
  const errorText = await page.locator(`[data-protocol-panel="${protocol}"].active [data-protocol-retry]`).count();
  if (errorText) {
    throw new Error(`${label}: lazy protocol panel failed to load`);
  }
  await assertVisibleBox(page, `[data-protocol-panel="${protocol}"].active:not([data-protocol-panel-lazy="1"])`, `${label} ${protocol} panel`);
}

async function runViewport(browser, modeConfig, viewportName, viewport, isMobile = false) {
  const name = `${modeConfig.mode} ${viewportName}`;
  const context = await browser.newContext({
    viewport,
    isMobile,
    hasTouch: isMobile,
    deviceScaleFactor: isMobile ? 2 : 1,
    httpCredentials,
  });
  const page = await context.newPage();
  const failures = watchPage(page, name);
  page.on('dialog', (dialog) => dialog.accept().catch(() => {}));
  await page.addInitScript(() => localStorage.setItem('router-theme', 'glass'));
  await page.goto(urlForMode(modeConfig.mode), { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
  await switchAppModeIfNeeded(page, modeConfig, name);
  failures.length = 0;

  const pageConfig = await readPageConfig(page);
  if (Boolean(pageConfig.enableKeyPool) !== modeConfig.expectPool) {
    throw new Error(`${name}: enableKeyPool expected ${modeConfig.expectPool}, got ${pageConfig.enableKeyPool}`);
  }
  if (Boolean(pageConfig.enableCustomChecks) !== modeConfig.expectCustomChecks) {
    throw new Error(`${name}: enableCustomChecks expected ${modeConfig.expectCustomChecks}, got ${pageConfig.enableCustomChecks}`);
  }
  if (Boolean(pageConfig.enableTelegram) !== modeConfig.expectTelegram) {
    throw new Error(`${name}: enableTelegram expected ${modeConfig.expectTelegram}, got ${pageConfig.enableTelegram}`);
  }
  const branchText = await page.locator('.app-branch').first().textContent();
  if (modeConfig.mode === 'advanced') {
    if (!/Telegram/i.test(branchText || '') || !/(бот|bot)/i.test(branchText || '')) {
      throw new Error(`${name}: advanced header mode text changed: ${branchText}`);
    }
    await assertVisibleBox(page, '#web-api-pill.topbar-status', `${name} top header status`);
  }

  await assertVisibleBox(page, '.topbar', `${name} topbar`);
  await assertVisibleBox(page, '[data-view="status"].active .view-head', `${name} overview`);
  await assertNoHorizontalOverflow(page, name);
  if (isMobile) {
    await assertMobileStatusGaps(page, name);
  }

  const titleFits = await page.locator('.app-caption strong').evaluate((node) => node.scrollWidth <= node.clientWidth + 2);
  if (!titleFits) {
    throw new Error(`${name}: header title is clipped`);
  }
  await assertNoVisibleMojibake(page, `${name} visible text`);

  await page.locator('#theme-toggle-button').click();
  await assertVisibleBox(page, '#theme-picker:not(.hidden)', `${name} theme picker`);
  await page.locator('#theme-toggle-button').click();

  const modeToggleCount = await page.locator('#mode-toggle-button').count();
  if (!modeConfig.expectTelegram && modeToggleCount) {
    throw new Error(`${name}: Telegram mode toggle is rendered in web-only mode`);
  }
  if (modeToggleCount) {
    await page.locator('#mode-toggle-button').click();
    await assertVisibleBox(page, '#mode-picker:not(.hidden)', `${name} mode picker`);
    await page.locator('#mode-toggle-button').click();
  }

  const historyButton = page.locator('[data-event-history-open]:visible').first();
  if (await historyButton.count()) {
    const initialHistoryItems = await page.locator('[data-event-history-pane="events"] .event-history-item').count();
    if (initialHistoryItems) {
      throw new Error(`${name}: event history is rendered before drawer open`);
    }
    const historyResponse = page.waitForResponse((response) => (
      response.url().includes('/api/event_history') && response.ok()
    ), { timeout: 60000 }).catch(() => null);
    await historyButton.click();
    await assertVisibleBox(page, '#event-history-modal:not(.hidden) .event-history-drawer', `${name} history drawer`);
    await assertNoVisibleMojibake(page, `${name} history loading text`);
    const historyTabs = await page.locator('[data-event-history-tab]').count();
    if (historyTabs) {
      throw new Error(`${name}: history drawer still renders separate tabs`);
    }
    await assertVisibleBox(page, '.router-metrics-compact', `${name} compact router metrics`);
    await historyResponse;
    await page.locator('[data-event-history-pane="events"]:not(.hidden) .event-history-item').first().waitFor({ state: 'visible', timeout: 60000 });
    await assertVisibleBox(page, '[data-event-history-pane="events"]:not(.hidden) .event-history-item', `${name} event history items`);
    await assertNoVisibleMojibake(page, `${name} event history loaded text`);
    if (isMobile) {
      await assertEventHistoryScrollLocked(page, `${name} event history scroll`);
    }
    await page.waitForFunction(() => {
      const value = document.getElementById('router-metrics-bot-rss');
      return value && value.textContent.includes('MB');
    }, null, { timeout: 10000 });
    const metricsText = await page.locator('#router-metrics-bot-rss').textContent();
    if (!metricsText || !metricsText.includes('MB')) {
      throw new Error(`${name}: router metrics did not load bot RSS`);
    }
    await page.locator('[data-event-history-close]').click();
    await historyButton.click();
    await page.locator('[data-event-history-pane="events"]:not(.hidden) .event-history-item').first().waitFor({ state: 'visible', timeout: 60000 });
    await assertVisibleBox(page, '[data-event-history-pane="events"]:not(.hidden) .event-history-item', `${name} event history on reopen`);
    await assertVisibleBox(page, '.router-metrics-compact', `${name} compact router metrics on reopen`);
    await page.locator('[data-event-history-close]').click();
  }

  await page.locator('.side-nav .nav-item[data-view-target="keys"]:visible, .mobile-nav .nav-item[data-view-target="keys"]:visible').click();
  await assertVisibleBox(page, '[data-view="keys"].active', `${name} keys view`);
  await assertPoolKeysAreMasked(page, `${name} initial keys`);
  await assertNoBrokenImages(page, `${name} initial keys`);
  if (modeConfig.expectPool) {
    await page.locator('[data-protocol-panel].active [data-subview-target="check"]').click();
    await assertVisibleBox(page, '[data-protocol-panel].active .service-route-tools', `${name} service route tools`);
    await assertVisibleBox(page, '[data-protocol-panel].active .service-route-telegram-icon', `${name} Telegram route icon`);
    await assertVisibleBox(page, '[data-protocol-panel].active .service-route-youtube-icon', `${name} YouTube route icon`);
    const firstRouteTrigger = page.locator('[data-protocol-panel].active .service-route-trigger').first();
    await assertVisibleBox(page, '[data-protocol-panel].active .service-route-card:first-child .service-route-trigger', `${name} service route trigger`);
    if (!isMobile) {
      await firstRouteTrigger.evaluate((node) => node.scrollIntoView({ block: 'center', inline: 'nearest' }));
    }
    await firstRouteTrigger.click();
    await assertVisibleBox(page, '[data-protocol-panel].active .service-route-menu[open] .service-route-form:first-child .service-route-menu-item', `${name} service route menu`);
    const routeMenuPosition = await page.locator('[data-protocol-panel].active .service-route-menu[open] .service-route-menu-list').first().evaluate((node) => getComputedStyle(node).position);
    if (!isMobile && routeMenuPosition !== 'absolute') {
      throw new Error(`${name}: service route menu should be a desktop popover, got ${routeMenuPosition}`);
    }
    if (isMobile && routeMenuPosition === 'absolute') {
      throw new Error(`${name}: service route menu should stay in-flow on mobile`);
    }
    const routeMenuList = page.locator('[data-protocol-panel].active .service-route-menu[open] .service-route-menu-list').first();
    let routeMenuViewport = await routeMenuList.evaluate((node) => {
      const rect = node.getBoundingClientRect();
      return { top: rect.top, bottom: rect.bottom, height: window.innerHeight };
    });
    if (!isMobile && (routeMenuViewport.top < -2 || routeMenuViewport.bottom > routeMenuViewport.height + 2)) {
      await routeMenuList.evaluate((node) => {
        const rect = node.getBoundingClientRect();
        if (rect.bottom > window.innerHeight) {
          window.scrollBy(0, rect.bottom - window.innerHeight + 16);
        } else if (rect.top < 0) {
          window.scrollBy(0, rect.top - 16);
        }
      });
      routeMenuViewport = await routeMenuList.evaluate((node) => {
        const rect = node.getBoundingClientRect();
        return { top: rect.top, bottom: rect.bottom, height: window.innerHeight };
      });
    }
    if (!isMobile && (routeMenuViewport.top < -2 || routeMenuViewport.bottom > routeMenuViewport.height + 2)) {
      throw new Error(`${name}: service route popover is clipped by viewport ${JSON.stringify(routeMenuViewport)}`);
    }
    const oldRouteChoiceCount = await page.locator('[data-protocol-panel].active .service-route-choice').count();
    if (oldRouteChoiceCount) {
      throw new Error(`${name}: old service route choice buttons are still rendered`);
    }
    const routeApi = await page.evaluate(async () => {
      const response = await fetch('/api/service_routes', { headers: { Accept: 'application/json' }, cache: 'no-store' });
      const payload = await response.json();
      return { ok: response.ok, hasHtml: String(payload.route_tools_html || '').includes('service-route-trigger') };
    });
    if (!routeApi.ok || !routeApi.hasHtml) {
      throw new Error(`${name}: service route fragment API failed`);
    }
    await assertVisibleBox(page, '[data-protocol-panel].active .route-intersection-card', `${name} route intersections`);
    await assertVisibleBox(page, '[data-protocol-panel].active .route-profile-panel', `${name} route profiles`);
    const routeTextFits = await page.locator('[data-protocol-panel].active .service-route-card').evaluateAll((nodes) => (
      nodes.every((node) => node.scrollWidth <= node.clientWidth + 2)
    ));
    if (!routeTextFits) {
      throw new Error(`${name}: service route cards overflow`);
    }
    await page.locator('[data-protocol-panel].active [data-subview-target="pool"]').click();
    if (await page.locator('[data-pool-filter]').count()) {
      await assertVisibleBox(page, '[data-pool-filter]', `${name} pool filter`);
    }
    if (await page.locator('.pool-delete-btn').count()) {
      await assertVisibleBox(page, '[data-protocol-panel].active [data-pool-body] tr:first-child .pool-delete-btn', `${name} delete button`);
    }
    await clickLazyProtocol(page, 'vless2', name);
    await page.locator('[data-protocol-panel="vless2"].active [data-subview-target="pool"]').click();
    await assertVisibleBox(page, '[data-protocol-panel="vless2"].active [data-pool-filter]', `${name} lazy pool filter`);
    await assertActivePoolRowPinned(page, 'vless2', `${name} original pool order`);
    await assertPoolKeysAreMasked(page, `${name} lazy keys`);
    await assertNoBrokenImages(page, `${name} lazy keys`);
    await page.locator('[data-protocol-panel="vless2"].active [data-subview-target="subscription"]').click();
    await assertVisibleBox(page, '[data-protocol-panel="vless2"].active [data-subview="subscription"].active', `${name} vless2 subscription tab`);
    await assertSubscriptionImportLayout(page, `${name} vless2 subscription import`);
  } else {
    const poolOnlyControls = await page.locator('[data-pool-filter], .pool-toolbar, [data-subview-target="pool"], [data-subview-target="check"], .service-route-tools').count();
    if (poolOnlyControls) {
      throw new Error(`${name}: pool-only controls are rendered in simple mode`);
    }
  }
  await assertNoHorizontalOverflow(page, `${name} keys`);

  await page.locator('.side-nav .nav-item[data-view-target="lists"]:visible, .mobile-nav .nav-item[data-view-target="lists"]:visible').click();
  await assertVisibleBox(page, '[data-view="lists"].active', `${name} lists view`);
  await assertNoBrokenImages(page, `${name} lists`);
  await assertNoHorizontalOverflow(page, `${name} lists`);
  assertNoPageFailures(failures);

  await context.close();
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: chromeExecutable,
  });
  try {
    for (const modeConfig of appModes) {
      await runViewport(browser, modeConfig, 'desktop', { width: 1365, height: 768 });
      await runViewport(browser, modeConfig, 'compact desktop', { width: 915, height: 640 });
      await runViewport(browser, modeConfig, 'mobile', devices['Pixel 5'].viewport, true);
    }
  } finally {
    await browser.close();
  }
  console.log('UI smoke passed:', safeTargetLabel(), 'modes:', appModes.map(({ mode }) => mode).join(', '));
})().catch((error) => {
  console.error(error);
  emitGitHubErrorAnnotation(error);
  process.exit(1);
});
