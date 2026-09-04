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

async function assertExpandedTopbarStatusIsReadable(page, label) {
  const layout = await page.evaluate(() => {
    const pill = document.getElementById('web-api-pill');
    const title = document.getElementById('topbar-status-title');
    const text = document.getElementById('topbar-status-text');
    if (!pill || !title || !text) {
      return null;
    }
    const previousClass = pill.className;
    const previousTitle = title.textContent;
    const previousText = text.textContent;
    pill.classList.add('topbar-status-expanded');
    title.textContent = 'Статус обновляется';
    text.textContent = '⏳ Проверка всех ключей: 6/109 · Экономный режим: свободно 154 МБ, порог замедления 160 МБ.';
    const textStyle = getComputedStyle(text);
    const result = {
      textClientHeight: text.clientHeight,
      textScrollHeight: text.scrollHeight,
      pillClientHeight: pill.clientHeight,
      pillScrollHeight: pill.scrollHeight,
      overflow: textStyle.overflow,
      lineClamp: textStyle.webkitLineClamp,
    };
    pill.className = previousClass;
    title.textContent = previousTitle;
    text.textContent = previousText;
    return result;
  });
  if (!layout) {
    throw new Error(`${label}: topbar status markup is missing`);
  }
  if (layout.textScrollHeight > layout.textClientHeight + 1 || layout.pillScrollHeight > layout.pillClientHeight + 1) {
    throw new Error(`${label}: expanded topbar status is clipped ${JSON.stringify(layout)}`);
  }
  if (layout.overflow === 'hidden' || layout.lineClamp === '2') {
    throw new Error(`${label}: expanded topbar status still applies clipping ${JSON.stringify(layout)}`);
  }
}

async function assertProtocolMenuGrid(page, label, isMobile) {
  const menus = [
    {
      selector: '.protocol-tabs',
      hysteriaSelector: '[data-protocol-target="hysteria2"]',
      shadowsocksSelector: '[data-protocol-target="shadowsocks"]',
    },
    {
      selector: '.list-tabs',
      hysteriaSelector: '[data-list-target="hysteria2.txt"]',
      shadowsocksSelector: '[data-list-target="shadowsocks.txt"]',
    },
  ];
  for (const menu of menus) {
    if (!(await page.locator(menu.selector).isVisible())) {
      continue;
    }
    const layout = await page.locator(menu.selector).evaluate((root, selectors) => {
      const tabs = Array.from(root.querySelectorAll('.seg-tab'));
      const hysteria = root.querySelector(selectors.hysteriaSelector);
      const shadowsocks = root.querySelector(selectors.shadowsocksSelector);
      const rect = (node) => {
        if (!node) return null;
        const box = node.getBoundingClientRect();
        return { left: box.left, top: box.top, width: box.width };
      };
      return {
        count: tabs.length,
        rowCount: new Set(tabs.map((node) => Math.round(node.getBoundingClientRect().top))).size,
        container: rect(root),
        hysteria: rect(hysteria),
        shadowsocks: rect(shadowsocks),
      };
    }, menu);
    if (layout.count !== 6 || !layout.container || !layout.hysteria || !layout.shadowsocks) {
      throw new Error(`${label} ${menu.selector}: expected all six protocol tabs, got ${JSON.stringify(layout)}`);
    }
    if (isMobile) {
      const sameRow = Math.abs(layout.hysteria.top - layout.shadowsocks.top) <= 2;
      const equalWidth = Math.abs(layout.hysteria.width - layout.shadowsocks.width) <= 2;
      const separateColumns = Math.abs(layout.hysteria.left - layout.shadowsocks.left) > 2;
      const shadowsocksIsNotFullWidth = layout.shadowsocks.width < layout.container.width * 0.75;
      if (layout.rowCount !== 3 || !sameRow || !equalWidth || !separateColumns || !shadowsocksIsNotFullWidth) {
        throw new Error(`${label} ${menu.selector}: Hysteria2 and Shadowsocks must share the third mobile row ${JSON.stringify(layout)}`);
      }
    } else if (layout.rowCount !== 1) {
      throw new Error(`${label} ${menu.selector}: desktop protocol tabs must stay on one row ${JSON.stringify(layout)}`);
    }
  }
}

async function assertPoolServiceColumns(page, label, expectHorizontalScroll) {
  const layout = await page.evaluate(() => {
    const panel = document.querySelector('[data-protocol-panel].active');
    const wrapper = panel && panel.querySelector('.pool-table-wrap');
    const table = wrapper && wrapper.querySelector('.pool-table');
    const row = table && table.querySelector('[data-pool-row]');
    if (!wrapper || !table || !row) {
      return null;
    }
    const heads = Array.from(table.querySelectorAll('[data-custom-check-head]'));
    const cells = Array.from(row.querySelectorAll('[data-pool-custom]'));
    const headIds = heads.map((node) => node.dataset.customCheckHead || '');
    const cellIds = cells.map((node) => node.dataset.poolCustom || '');
    const expectedIds = String(table.dataset.customCheckSignature || '').split('|').filter(Boolean);
    const wrapperRect = wrapper.getBoundingClientRect();
    wrapper.scrollLeft = 0;
    const firstRect = heads[0] ? heads[0].getBoundingClientRect() : null;
    const firstVisibleAtStart = Boolean(firstRect && firstRect.right > wrapperRect.left && firstRect.left < wrapperRect.right);
    wrapper.scrollLeft = wrapper.scrollWidth;
    const lastRect = heads.length ? heads[heads.length - 1].getBoundingClientRect() : null;
    const lastVisibleAtEnd = Boolean(lastRect && lastRect.right > wrapperRect.left && lastRect.left < wrapperRect.right);
    const result = {
      expectedIds,
      headIds,
      cellIds,
      iconHeads: heads.filter((node) => node.querySelector('img')).length,
      clientWidth: wrapper.clientWidth,
      scrollWidth: wrapper.scrollWidth,
      overflowX: getComputedStyle(wrapper).overflowX,
      firstVisibleAtStart,
      lastVisibleAtEnd,
    };
    wrapper.scrollLeft = 0;
    return result;
  });
  if (!layout) {
    throw new Error(`${label}: pool table is missing`);
  }
  if (layout.expectedIds.length < 10 || !layout.expectedIds.includes('tiktok')) {
    throw new Error(`${label}: all service checks, including TikTok, were not rendered ${JSON.stringify(layout)}`);
  }
  if (JSON.stringify(layout.headIds) !== JSON.stringify(layout.expectedIds) || JSON.stringify(layout.cellIds) !== JSON.stringify(layout.expectedIds)) {
    throw new Error(`${label}: pool service headers and row cells are not aligned ${JSON.stringify(layout)}`);
  }
  if (layout.iconHeads !== layout.expectedIds.length) {
    throw new Error(`${label}: one or more pool service icons are missing ${JSON.stringify(layout)}`);
  }
  if (!['auto', 'scroll'].includes(layout.overflowX)) {
    throw new Error(`${label}: pool horizontal scrolling is disabled ${JSON.stringify(layout)}`);
  }
  if (!layout.firstVisibleAtStart || !layout.lastVisibleAtEnd) {
    throw new Error(`${label}: first or last service column cannot be reached ${JSON.stringify(layout)}`);
  }
  if (expectHorizontalScroll && layout.scrollWidth <= layout.clientWidth + 2) {
    throw new Error(`${label}: all-service mobile pool should scroll horizontally ${JSON.stringify(layout)}`);
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
  await page.waitForFunction((targetSelector) => {
    const node = document.querySelector(targetSelector);
    if (!node) {
      return false;
    }
    const style = getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden') {
      return false;
    }
    const box = node.getBoundingClientRect();
    return box.width >= 2 && box.height >= 2;
  }, selector, { timeout: 30000 }).catch((error) => {
    throw new Error(`${label}: ${selector} did not become visibly sized: ${error.message}`);
  });
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
  const imagesReady = () => Array.from(document.images).every((img) => (
    img.complete && img.naturalWidth > 0 && img.naturalHeight > 0
  ));
  await page.waitForFunction(imagesReady, null, { timeout: 15000 });
  await page.waitForTimeout(300);
  await page.waitForFunction(imagesReady, null, { timeout: 15000 });
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

async function assertDesktopListEditorSizing(page, label) {
  const layout = await page.evaluate(() => {
    const textarea = document.querySelector('[data-view="lists"].active .list-workspace.active .list-editor-form textarea');
    const workspace = document.querySelector('[data-view="lists"].active .list-workspace.active');
    const actions = document.querySelector('[data-view="lists"].active .list-workspace.active .list-editor-form .form-actions');
    const shell = document.querySelector('.app-shell');
    const rect = (node) => node ? node.getBoundingClientRect() : null;
    return {
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      textarea: rect(textarea),
      workspace: rect(workspace),
      actions: rect(actions),
      shell: rect(shell),
    };
  });
  if (layout.viewportHeight < 900) return;
  if (!layout.textarea || !layout.workspace || !layout.actions || !layout.shell) {
    throw new Error(`${label}: list editor layout is missing nodes`);
  }
  if (layout.viewportWidth >= 3000) {
    if (layout.shell.width < layout.viewportWidth * 0.75 || layout.textarea.height < 516 || layout.textarea.height > 764) {
      throw new Error(`${label}: 4K layout does not use the available workspace ${JSON.stringify(layout)}`);
    }
    return;
  }
  if (layout.viewportWidth >= 1921) {
    if (layout.shell.width < layout.viewportWidth * 0.84 || layout.textarea.height < 356 || layout.textarea.height > 524) {
      throw new Error(`${label}: 2K layout does not use the available workspace ${JSON.stringify(layout)}`);
    }
    return;
  }
  if (layout.textarea.height > 324 || layout.workspace.height > 500) {
    throw new Error(`${label}: Full HD list editor is needlessly stretched ${JSON.stringify(layout)}`);
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

async function protocolHeaderIconSnapshot(page, protocol) {
  return page.evaluate((proto) => {
    const container = document.querySelector(`[data-protocol-card="${proto}"] [data-protocol-status-icons]`);
    if (!container) {
      return { count: 0, labels: [], html: '' };
    }
    const visible = Array.from(container.children).filter((node) => {
      const style = getComputedStyle(node);
      const box = node.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && box.width >= 2 && box.height >= 2;
    });
    return {
      count: visible.length,
      labels: visible.map((node) => (
        node.getAttribute('alt') || node.getAttribute('title') || (node.textContent || '').trim()
      )),
      html: container.innerHTML,
    };
  }, protocol);
}

async function assertProtocolStatusServiceMerge(page, label) {
  const result = await page.evaluate(() => {
    const hooks = window.__bypassTestHooks || {};
    const merge = hooks.mergeProtocolStatusIcons;
    const scopedStatus = hooks.protocolStatusFromActivePoolRow;
    if (typeof merge !== 'function' || typeof scopedStatus !== 'function') {
      return { error: 'protocol status test hooks are unavailable' };
    }
    const item = (service, state, text) => (
      `<span data-status-service="${service}" data-status-state="${state}">${text}</span>`
    );
    const liveOk = item('telegram', 'ok', 'live-tg');
    const pool = item('telegram', 'fail', 'pool-tg') + item('youtube', 'ok', 'pool-yt') +
      item('custom:chat', 'ok', 'pool-chat');
    const merged = merge(liveOk, pool);
    const liveFail = merge(item('telegram', 'fail', 'live-fail'), item('telegram', 'ok', 'pool-ok'));
    const fallback = merge(item('telegram', 'unknown', 'live-unknown'), item('telegram', 'ok', 'pool-ok'));
    const poolYoutube = merge(item('youtube', 'fail', 'live-yt-fail'), item('youtube', 'ok', 'pool-yt-ok'));
    const parse = (html) => {
      const template = document.createElement('template');
      template.innerHTML = html;
      return Array.from(template.content.querySelectorAll('[data-status-service]')).map((node) => ({
        service: node.dataset.statusService,
        state: node.dataset.statusState,
        text: node.textContent,
      }));
    };
    const fixture = document.createElement('div');
    fixture.innerHTML = '<article data-protocol-card="scope-test"></article>' +
      '<section data-protocol-panel="scope-test" data-core-services-loaded="1" data-core-services="youtube"></section>' +
      '<table><tr data-pool-row data-protocol="scope-test" data-active="1" data-tg-state="fail" ' +
      'data-tg-source="pool_probe" data-yt-state="ok"><td data-pool-checked>сейчас</td></tr></table>';
    document.body.appendChild(fixture);
    let poolScoped;
    let liveScoped;
    try {
      poolScoped = scopedStatus('scope-test');
      fixture.querySelector('[data-pool-row]').dataset.tgSource = 'live_polling';
      liveScoped = scopedStatus('scope-test');
    } finally {
      fixture.remove();
    }
    const compactStatus = (status) => status ? {
      tone: status.tone,
      label: status.label,
      icons: parse(status.icons),
    } : null;
    return {
      merged: parse(merged),
      liveFail: parse(liveFail),
      fallback: parse(fallback),
      poolYoutube: parse(poolYoutube),
      poolScoped: compactStatus(poolScoped),
      liveScoped: compactStatus(liveScoped),
    };
  });
  if (result.error) {
    throw new Error(`${label}: ${result.error}`);
  }
  const services = result.merged.map((item) => item.service);
  if (
    services.join('|') !== 'telegram|youtube|custom:chat' ||
    result.merged[0].state !== 'ok' || result.merged[0].text !== 'live-tg' ||
    result.liveFail[0].state !== 'fail' ||
    result.fallback[0].state !== 'ok' ||
    result.poolYoutube[0].state !== 'ok' || result.poolYoutube[0].text !== 'pool-yt-ok' ||
    !result.poolScoped || result.poolScoped.tone !== 'ok' || result.poolScoped.label !== 'Работает' ||
    result.poolScoped.icons.map((item) => item.service).join('|') !== 'youtube' ||
    !result.liveScoped || result.liveScoped.tone !== 'warn' ||
    result.liveScoped.icons.map((item) => item.service).join('|') !== 'telegram|youtube'
  ) {
    throw new Error(`${label}: service-aware status merge is wrong ${JSON.stringify(result)}`);
  }
}

async function assertPersistedCustomResultsRemainVisible(page, protocol, label) {
  const snapshot = await page.evaluate(async (proto) => {
    const row = document.querySelector(`[data-pool-row][data-protocol="${proto}"][data-active="1"]`);
    const slots = row ? Array.from(row.querySelectorAll('[data-pool-custom] [data-service-state]')) : [];
    const failedRow = document.querySelector(`[data-pool-row][data-protocol="${proto}"]:not([data-active="1"])`);
    const failedSlots = failedRow ? Array.from(failedRow.querySelectorAll('[data-pool-custom] [data-service-state]')) : [];
    const header = document.querySelector(`[data-protocol-card="${proto}"] [data-protocol-status-icons]`);
    const response = await fetch(`/api/pools?protocols=${encodeURIComponent(proto)}`, {cache: 'no-store'});
    const payload = await response.json();
    const section = payload && payload.pools ? payload.pools[proto] : null;
    const rows = Array.isArray(section) ? section : (section && Array.isArray(section.rows) ? section.rows : []);
    const active = rows.find((item) => item && item.active) || null;
    return {
      slotCount: slots.length,
      states: slots.map((node) => node.getAttribute('data-service-state') || ''),
      iconCount: slots.filter((node) => node.querySelector('img')).length,
      titles: slots.map((node) => node.getAttribute('title') || ''),
      failedStates: failedSlots.map((node) => node.getAttribute('data-service-state') || ''),
      failedIconCount: failedSlots.filter((node) => node.querySelector('img')).length,
      failedCrossCount: failedSlots.filter((node) => node.querySelector('.service-probe-fail')).length,
      failedTitles: failedSlots.map((node) => node.getAttribute('title') || ''),
      headerMarkerCount: header ? header.querySelectorAll('.service-state-marker').length : 0,
      apiStates: active && active.custom ? Object.values(active.custom) : [],
    };
  }, protocol);
  if (!snapshot.slotCount) {
    throw new Error(`${label}: selected service columns are missing`);
  }
  if (snapshot.states.some((state) => state !== 'ok')) {
    throw new Error(`${label}: saved successful results were replaced with unknown states ${JSON.stringify(snapshot)}`);
  }
  if (snapshot.iconCount !== snapshot.slotCount || snapshot.headerMarkerCount !== 0) {
    throw new Error(`${label}: successful services must use plain icons without age markers ${JSON.stringify(snapshot)}`);
  }
  if (snapshot.titles.some((title) => !title.includes('работает') || title.includes('устарел'))) {
    throw new Error(`${label}: successful result title is incorrect ${JSON.stringify(snapshot.titles)}`);
  }
  if (
    !snapshot.failedStates.length ||
    snapshot.failedStates.some((state) => state !== 'fail') ||
    snapshot.failedIconCount !== 0 ||
    snapshot.failedCrossCount !== snapshot.failedStates.length ||
    snapshot.failedTitles.some((title) => !title.includes('не работает') || title.includes('устарел'))
  ) {
    throw new Error(`${label}: saved failed results are not represented accurately ${JSON.stringify(snapshot)}`);
  }
  if (snapshot.apiStates.length !== snapshot.slotCount || snapshot.apiStates.some((state) => state !== 'ok')) {
    throw new Error(`${label}: API lost the saved custom-service result ${JSON.stringify(snapshot.apiStates)}`);
  }
}

async function assertProtocolServiceIconsStableAfterLiveStatus(page, protocol, minCount, label) {
  await page.waitForFunction(({ proto, expected }) => {
    const container = document.querySelector(`[data-protocol-card="${proto}"] [data-protocol-status-icons]`);
    if (!container) {
      return false;
    }
    return Array.from(container.children).filter((node) => {
      const style = getComputedStyle(node);
      const box = node.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && box.width >= 2 && box.height >= 2;
    }).length >= expected;
  }, { proto: protocol, expected: minCount }, { timeout: 10000 });
  const before = await protocolHeaderIconSnapshot(page, protocol);
  const applyButton = page.locator(`[data-protocol-panel="${protocol}"].active [data-pool-body="${protocol}"] .pool-apply-form button`).first();
  await assertVisibleBox(page, `[data-protocol-panel="${protocol}"].active [data-pool-body="${protocol}"] .pool-apply-form button`, `${label} apply button`);
  const liveStatusResponse = page.waitForResponse((response) => (
    response.url().includes('/api/status') && response.ok()
  ), { timeout: 15000 }).catch(() => null);
  await applyButton.click();
  const response = await liveStatusResponse;
  if (!response) {
    throw new Error(`${label}: live status poll did not run`);
  }
  await page.waitForTimeout(200);
  const after = await protocolHeaderIconSnapshot(page, protocol);
  if (after.count < minCount || after.count < before.count) {
    throw new Error(`${label}: protocol icons degraded after live status ${JSON.stringify({ before, after })}`);
  }
}

async function assertProtocolServiceIconsStableAfterIdleRefresh(page, protocol, minCount, label) {
  await page.waitForFunction(({ proto, expected }) => {
    const container = document.querySelector(`[data-protocol-card="${proto}"] [data-protocol-status-icons]`);
    if (!container) {
      return false;
    }
    return Array.from(container.children).filter((node) => {
      const style = getComputedStyle(node);
      const box = node.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && box.width >= 2 && box.height >= 2;
    }).length >= expected;
  }, { proto: protocol, expected: minCount }, { timeout: 10000 });
  const before = await protocolHeaderIconSnapshot(page, protocol);
  const liveStatusResponse = page.waitForResponse((response) => (
    response.url().includes('/api/status?compact=1&lite=1') && response.ok()
  ), { timeout: 15000 }).catch(() => null);
  await page.evaluate(() => {
    if (window.__bypassTestHooks && typeof window.__bypassTestHooks.pollStatus === 'function') {
      window.__bypassTestHooks.pollStatus();
    }
  });
  const response = await liveStatusResponse;
  if (!response) {
    throw new Error(`${label}: idle live status poll did not run`);
  }
  await page.waitForTimeout(200);
  const after = await protocolHeaderIconSnapshot(page, protocol);
    if (after.count < minCount || after.count < before.count) {
        throw new Error(`${label}: protocol icons degraded after idle live status ${JSON.stringify({ before, after })}`);
    }
}

async function assertProtocolServiceIconsStableAfterPoolRefresh(page, protocol, minCount, label) {
  await page.waitForFunction(({ proto, expected }) => {
    const container = document.querySelector(`[data-protocol-card="${proto}"] [data-protocol-status-icons]`);
    return container && Array.from(container.children).filter((node) => {
      const style = getComputedStyle(node);
      const box = node.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && box.width >= 2 && box.height >= 2;
    }).length >= expected;
  }, { proto: protocol, expected: minCount }, { timeout: 10000 });
  const before = await protocolHeaderIconSnapshot(page, protocol);
  const poolResponse = page.waitForResponse((response) => (
    response.url().includes('/api/pools') && response.ok()
  ), { timeout: 15000 }).catch(() => null);
  await page.evaluate((proto) => {
    if (window.__bypassTestHooks && typeof window.__bypassTestHooks.refreshPoolData === 'function') {
      window.__bypassTestHooks.refreshPoolData(0, [proto]);
    }
  }, protocol);
  const response = await poolResponse;
  if (!response) {
    throw new Error(`${label}: pool refresh did not run`);
  }
  await page.waitForTimeout(200);
  const after = await protocolHeaderIconSnapshot(page, protocol);
  if (after.count < minCount || after.count < before.count) {
    throw new Error(`${label}: protocol icons degraded after pool refresh ${JSON.stringify({ before, after })}`);
  }
}

async function assertActiveTelegramCardConsistent(page, protocol, label) {
  await page.waitForFunction((proto) => {
    const card = document.querySelector(`[data-protocol-card="${proto}"]`);
    const icons = card ? card.querySelector('[data-protocol-status-icons]') : null;
    return card && card.dataset.protocolLiveStatus === '1' && icons &&
      Array.from(icons.querySelectorAll('img')).some((icon) => icon.getAttribute('alt') === 'Telegram');
  }, protocol, { timeout: 10000 });
  const state = await page.locator(`[data-protocol-card="${protocol}"]`).evaluate((card) => ({
    live: card.dataset.protocolLiveStatus,
    label: (card.querySelector('[data-protocol-status-label]') || { textContent: '' }).textContent.trim(),
    telegramIcon: Array.from(card.querySelectorAll('[data-protocol-status-icons] img'))
      .some((icon) => icon.getAttribute('alt') === 'Telegram'),
  }));
  if (state.live !== '1' || !state.telegramIcon || /Частично работает|Не работает/u.test(state.label)) {
    throw new Error(`${label}: live Telegram evidence disagrees with the active card ${JSON.stringify(state)}`);
  }
}

async function assertUnifiedImportLayout(page, label) {
  const layout = await page.evaluate(() => {
    const panel = document.querySelector('[data-protocol-panel].active [data-subview="key"].active');
    const keyForm = panel ? panel.querySelector('.key-editor-form') : null;
    const importForm = panel ? panel.querySelector('.pool-import-form') : null;
    const keyTextarea = keyForm ? keyForm.querySelector('textarea[name="key"]') : null;
    const importTextarea = importForm ? importForm.querySelector('textarea[name="import_payload"]') : null;
    const importButton = importForm ? importForm.querySelector('button[type="submit"]') : null;
    const setTextareaValue = (node, value) => {
      if (!node) {
        return;
      }
      node.value = value;
      node.dispatchEvent(new Event('input', { bubbles: true }));
    };
    setTextareaValue(
      keyTextarea,
      'vless://fixture-active-' + 'a'.repeat(180) + '@example.test:443?security=reality&flow=xtls-rprx-vision#fixture-active-key'
    );
    setTextareaValue(
      importTextarea,
      [
        'vless://fixture-import-' + 'b'.repeat(180) + '@example.test:443?security=reality#fixture-import-vless',
        'vmess://fixture-import-vmess',
        'trojan://fixture-import-trojan',
        'hy2://fixture-auth@fixture.example:443#fixture-import-hysteria2',
        'ss://fixture-import-shadowsocks',
        'https://sub.example.com/fixture'
      ].join('\n')
    );
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
    const overflow = (node) => {
      if (!node) {
        return null;
      }
      return {
        x: Math.round(node.scrollWidth - node.clientWidth),
        y: Math.round(node.scrollHeight - node.clientHeight),
        overflowX: window.getComputedStyle(node).overflowX,
        overflowY: window.getComputedStyle(node).overflowY,
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
    const protocolPanel = panel ? panel.closest('[data-protocol-panel]') : null;
    const subtabWrap = protocolPanel ? protocolPanel.querySelector('.subtabs') : null;
    const checkSubtab = subtabWrap ? subtabWrap.querySelector('[data-subview-target="check"]') : null;
    const panelRect = rect(panel);
    const keyRect = rect(keyForm);
    const importRect = rect(importForm);
    const keyTextareaRect = rect(keyTextarea);
    const importTextareaRect = rect(importTextarea);
    const buttonRect = rect(importButton);
    return {
      panel: panelRect,
      keyForm: keyRect,
      importForm: importRect,
      keyTextarea: keyTextareaRect,
      importTextarea: importTextareaRect,
      importButton: buttonRect,
      keyTextareaOverflow: overflow(keyTextarea),
      importTextareaOverflow: overflow(importTextarea),
      subtabWrap: rect(subtabWrap),
      checkSubtab: rect(checkSubtab),
      panelOverflow: panel ? panel.scrollWidth - panel.clientWidth : null,
      formOverlap: intersection(keyRect, importRect),
      keyTextareaInside: Boolean(keyRect && keyTextareaRect && keyTextareaRect.left >= keyRect.left - 1 && keyTextareaRect.right <= keyRect.right + 1),
      importTextareaInside: Boolean(importRect && importTextareaRect && importTextareaRect.left >= importRect.left - 1 && importTextareaRect.right <= importRect.right + 1),
      buttonInsideImport: Boolean(importRect && buttonRect && buttonRect.left >= importRect.left - 1 && buttonRect.right <= importRect.right + 1),
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    };
  });
  if (!layout.panel || !layout.keyForm || !layout.importForm || !layout.keyTextarea || !layout.importTextarea || !layout.importButton) {
    throw new Error(`${label}: unified import layout is missing nodes ${JSON.stringify(layout)}`);
  }
  if (layout.panelOverflow > 2) {
    throw new Error(`${label}: unified import overflows horizontally ${JSON.stringify(layout)}`);
  }
  if (layout.formOverlap > 2) {
    throw new Error(`${label}: key and import blocks overlap ${JSON.stringify(layout)}`);
  }
  if (!layout.keyTextareaInside || !layout.importTextareaInside || !layout.buttonInsideImport) {
    throw new Error(`${label}: key/import controls leave their card ${JSON.stringify(layout)}`);
  }
  if (layout.keyTextareaOverflow && (layout.keyTextareaOverflow.x > 2 || layout.keyTextareaOverflow.y > 2)) {
    throw new Error(`${label}: active key textarea has internal scroll ${JSON.stringify(layout)}`);
  }
  if (layout.importTextareaOverflow && (layout.importTextareaOverflow.x > 2 || layout.importTextareaOverflow.y > 2)) {
    throw new Error(`${label}: import textarea has internal scroll ${JSON.stringify(layout)}`);
  }
  if (layout.viewportWidth < 720 && layout.subtabWrap && layout.checkSubtab && Math.abs(layout.checkSubtab.width - layout.subtabWrap.width) > 4) {
    throw new Error(`${label}: check subtab is not full-row on mobile ${JSON.stringify(layout)}`);
  }
  if (layout.viewportWidth >= 1024 && layout.importButton.bottom > layout.viewportHeight + 2) {
    throw new Error(`${label}: import button is below desktop viewport ${JSON.stringify(layout)}`);
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

async function assertCompactProtocolCheckWorkspace(page, label) {
  const layout = await page.evaluate(() => {
    const workspace = document.querySelector('[data-protocol-panel].active');
    const check = workspace ? workspace.querySelector('.protocol-subview-check.active') : null;
    if (!workspace || !check) {
      return null;
    }
    const children = Array.from(check.children).filter((node) => {
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.height > 0;
    });
    const workspaceRect = workspace.getBoundingClientRect();
    const lastBottom = children.reduce((bottom, node) => Math.max(bottom, node.getBoundingClientRect().bottom), 0);
    return {
      emptyBottom: Math.round(workspaceRect.bottom - lastBottom),
      lastBottom: Math.round(lastBottom),
      viewportHeight: window.innerHeight,
      workspaceHeight: Math.round(workspaceRect.height),
    };
  });
  if (!layout) {
    throw new Error(`${label}: active protocol check workspace is missing`);
  }
  if (layout.lastBottom <= layout.viewportHeight + 2 && layout.emptyBottom > 32) {
    throw new Error(`${label}: protocol check workspace leaves excessive empty space ${JSON.stringify(layout)}`);
  }
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
    const topbarStatus = page.locator('#web-api-pill.topbar-status');
    const topbarText = (await topbarStatus.innerText()).trim();
    if (!topbarText.includes('Telegram-бот работает') || !topbarText.includes('Память роутера в норме')) {
      throw new Error(`${name}: confirmed polling must render the normal working banner, got ${topbarText}`);
    }
    if (!(await topbarStatus.getAttribute('class') || '').includes('topbar-status-ok')) {
      throw new Error(`${name}: confirmed polling banner must use the ok state`);
    }
  }

  await assertVisibleBox(page, '.topbar', `${name} topbar`);
  await assertVisibleBox(page, '[data-view="status"].active .view-head', `${name} overview`);
  if (await page.locator('#youtube-failover-note, [data-youtube-failover-card]').count() !== 0) {
    throw new Error(`${name}: automatic failover diagnostics must not be rendered in the web interface`);
  }
  const overviewText = (await page.locator('[data-view="status"].active').innerText()).trim();
  if (overviewText.includes('Автопереключение YouTube') || overviewText.includes('Автопереключение Telegram')) {
    throw new Error(`${name}: automatic failover labels leaked into the web interface`);
  }
  await assertNoHorizontalOverflow(page, name);
  if (modeConfig.mode === 'advanced') {
    await assertExpandedTopbarStatusIsReadable(page, name);
  }
  if (modeConfig.expectPool) {
    const poolSummaryText = (await page.locator('#pool-summary-note').innerText()).trim();
    if (!poolSummaryText.includes('Instagram / Facebook:')) {
      throw new Error(`${name}: pool summary clipped the full Instagram / Facebook label: ${poolSummaryText}`);
    }
    if (poolSummaryText.includes('Facebo...')) {
      throw new Error(`${name}: pool summary still contains the legacy shortened service label: ${poolSummaryText}`);
    }
    const latestRun = page.locator('#pool-latest-run-summary');
    const latestRunText = (await latestRun.innerText()).trim();
    if (!(await latestRun.isVisible()) || !latestRunText.includes('Последняя проверка завершена')) {
      throw new Error(`${name}: latest full pool run is not shown explicitly: ${latestRunText}`);
    }
    if (latestRunText.includes('0 из')) {
      throw new Error(`${name}: current zero progress leaked into the last finished run: ${latestRunText}`);
    }
    const persistedRunState = await page.evaluate(async () => {
      const response = await fetch('/api/pools', {cache: 'no-store'});
      return (await response.json()).pool_summary;
    });
    if (
      !persistedRunState ||
      persistedRunState.current_run?.status !== 'running' ||
      persistedRunState.current_run?.checked !== 0 ||
      persistedRunState.last_finished_run?.status !== 'completed'
    ) {
      throw new Error(`${name}: current and last finished pool runs are not separated`);
    }
  }
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
  await assertVisibleBox(page, '#theme-picker:not(.hidden) #background-preview', `${name} background preview`);
  if (await page.locator('#background-file-input[accept="image/jpeg,image/png,image/webp"]').count() !== 1) {
    throw new Error(`${name}: background file input is missing or accepts unsafe formats`);
  }
  if (await page.locator('#background-save-button').isDisabled() !== true) {
    throw new Error(`${name}: background save must be disabled before a file is selected`);
  }
  if (await page.locator('#background-enabled').count() !== 0) {
    throw new Error(`${name}: background UI must not expose a separate enable checkbox`);
  }
  if (await page.locator('#background-panel-transparency[type="range"]').count() !== 1) {
    throw new Error(`${name}: background panel transparency range is missing`);
  }
  if (!isMobile && modeConfig.mode === 'advanced') {
    await page.locator('#background-file-input').evaluate(async (input) => {
      const canvas = document.createElement('canvas');
      canvas.width = 2560;
      canvas.height = 1601;
      const context = canvas.getContext('2d');
      context.fillStyle = '#198a8a';
      context.fillRect(0, 0, canvas.width, canvas.height);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
      const transfer = new DataTransfer();
      transfer.items.add(new File([blob], 'background.png', { type: 'application/octet-stream' }));
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitForFunction(() => !document.getElementById('background-save-button').disabled);
    await page.locator('#background-shade').evaluate((node) => {
      node.value = '100';
      node.dispatchEvent(new Event('input', { bubbles: true }));
    });
    if (await page.locator('#background-shade-value').textContent() !== '100%') {
      throw new Error(`${name}: background shade must support 100%`);
    }
    if (await page.locator('#background-shade').evaluate((node) => node.style.getPropertyValue('--range-progress')) !== '100%') {
      throw new Error(`${name}: background shade range must visually fill to 100%`);
    }
    await page.locator('#background-panel-transparency').evaluate((node) => {
      node.value = '64';
      node.dispatchEvent(new Event('input', { bubbles: true }));
    });
    if (await page.locator('#background-panel-transparency-value').textContent() !== '64%') {
      throw new Error(`${name}: background panel transparency must be adjustable`);
    }
    if (await page.locator('html').evaluate((node) => node.style.getPropertyValue('--user-background-panel-alpha')) !== '0.576') {
      throw new Error(`${name}: background panel transparency preview was not applied`);
    }
    if (await page.locator('html').evaluate((node) => node.style.getPropertyValue('--user-background-content-alpha')) !== '0.397') {
      throw new Error(`${name}: background content transparency preview was not applied`);
    }
    if (await page.locator('html[data-user-background="enabled"]').count() !== 1) {
      throw new Error(`${name}: pending background preview was removed by shade adjustment`);
    }
    await page.locator('#background-panel-transparency').evaluate((node) => {
      node.value = '100';
      node.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await page.waitForTimeout(500);
    if (await page.locator('html').evaluate((node) => node.style.getPropertyValue('--user-background-content-alpha')) !== '0.080') {
      throw new Error(`${name}: content surfaces must become fully translucent at 100%`);
    }
    await page.waitForFunction(() => {
      const alpha = (node) => {
        if (!node) return 1;
        const match = getComputedStyle(node).backgroundColor.match(/rgba\([^)]*,\s*(0?\.\d+)\s*\)$/);
        return match ? Number(match[1]) : 1;
      };
      const regularButtons = [
        '.protocol-tabs .seg-tab:not(.active)',
        '.protocol-workspace.active .subtab:not(.active)',
        '.protocol-workspace.active .secondary-button',
        '.list-workspace.active button',
      ].map((selector) => document.querySelector(selector));
      const regularAlphas = regularButtons.map(alpha);
      const statusAlpha = alpha(document.querySelector('[data-view="status"] .service-panel button'));
      return regularButtons.every(Boolean)
        && Math.max(...regularAlphas) - Math.min(...regularAlphas) <= 0.02
        && statusAlpha <= 0.35;
    }, null, { timeout: 3000 });
    const contentTransparency = await page.evaluate(() => {
      const surfaceSelectors = [
        '.protocol-workspace.active',
        '.list-workspace.active',
        '[data-view="status"] .status-card',
      ];
      const buttonSelectors = [
        '.protocol-tabs .seg-tab:not(.active)',
        '.protocol-workspace.active .subtab:not(.active)',
        '.protocol-workspace.active .secondary-button',
        '[data-view="status"] .service-panel button',
        '.list-workspace.active button',
      ];
      const backdrop = (node) => {
        const style = getComputedStyle(node);
        return style.backdropFilter || style.webkitBackdropFilter || 'none';
      };
      return {
        surfaceBackdrops: surfaceSelectors.map((selector) => {
          const node = document.querySelector(selector);
          return node ? backdrop(node) : 'missing';
        }),
        buttonBackgrounds: buttonSelectors.map((selector) => {
          const node = document.querySelector(selector);
          const style = node ? getComputedStyle(node) : null;
          return node ? {
            selector,
            color: style.backgroundColor,
            hovered: node.matches(':hover'),
            liquidActive: node.classList.contains('liquid-active'),
          } : null;
        }),
      };
    });
    if (contentTransparency.surfaceBackdrops.some((value) => value !== 'none')) {
      throw new Error(`${name}: content surfaces must not blur the background behind buttons`);
    }
    const regularButtonBackgrounds = contentTransparency.buttonBackgrounds
      .filter((value) => value && !value.hovered && !value.liquidActive && !value.selector.includes('.service-panel'))
      .map((value) => value.color);
    const regularButtonAlphas = regularButtonBackgrounds.map((color) => {
      const match = color.match(/rgba\([^)]*,\s*(0?\.\d+)\s*\)$/);
      return match ? Number(match[1]) : 1;
    });
    const statusButton = contentTransparency.buttonBackgrounds.find(
      (value) => value && value.selector.includes('.service-panel'),
    );
    const statusButtonAlphaMatch = statusButton
      ? statusButton.color.match(/rgba\([^)]*,\s*(0?\.\d+)\s*\)$/)
      : null;
    const statusButtonAlpha = statusButtonAlphaMatch ? Number(statusButtonAlphaMatch[1]) : 1;
    if (
      contentTransparency.buttonBackgrounds.includes(null) ||
      !regularButtonBackgrounds.length ||
      Math.max(...regularButtonAlphas) - Math.min(...regularButtonAlphas) > 0.02 ||
      statusButtonAlpha > 0.35
    ) {
      throw new Error(
        `${name}: buttons on status, keys, and lists must use one translucent background `
        + JSON.stringify(contentTransparency.buttonBackgrounds),
      );
    }
    const pickerSurface = await page.locator('#theme-picker:not(.hidden)').evaluate((node) => {
      const style = getComputedStyle(node);
      const alphaValues = Array.from(style.backgroundImage.matchAll(/rgba?\([^)]*[,/]\s*(0?\.\d+)\s*\)/g))
        .map((match) => Number(match[1]));
      const colorAlphaMatch = style.backgroundColor.match(/rgba\([^)]*,\s*(0?\.\d+)\s*\)$/);
      return {
        backgroundColor: style.backgroundColor,
        backgroundColorAlpha: colorAlphaMatch ? Number(colorAlphaMatch[1]) : 1,
        backgroundImage: style.backgroundImage,
        backdropFilter: style.backdropFilter || style.webkitBackdropFilter || '',
        hasDenseLayer: alphaValues.some((value) => value >= 0.95),
        isolation: style.isolation,
      };
    });
    if (
      pickerSurface.backgroundColorAlpha < 0.98 ||
      pickerSurface.backgroundImage === 'none' ||
      !pickerSurface.hasDenseLayer ||
      !pickerSurface.backdropFilter.includes('blur') ||
      pickerSurface.isolation !== 'isolate'
    ) {
      throw new Error(`${name}: theme picker must remain dense and blurred at 100% panel transparency`);
    }
    await page.locator('#background-panel-transparency').evaluate((node) => {
      node.value = '64';
      node.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await page.locator('#background-save-button').click();
    await page.waitForFunction(() => (document.getElementById('background-note').textContent || '').includes('сохран'));
    if (await page.locator('html[data-user-background="enabled"]').count() !== 1) {
      throw new Error(`${name}: saved background was not applied`);
    }
    page.once('dialog', (dialog) => dialog.accept().catch(() => {}));
    await page.locator('#background-delete-button').click();
    await page.waitForFunction(() => !document.documentElement.hasAttribute('data-user-background'));
  }
  await page.locator('#theme-toggle-button').click();

  const modeToggleCount = await page.locator('#mode-toggle-button').count();
  if (!modeConfig.expectTelegram && modeToggleCount) {
    throw new Error(`${name}: Telegram mode toggle is rendered in web-only mode`);
  }
  if (modeToggleCount) {
    await page.locator('#mode-toggle-button').click();
    await assertVisibleBox(page, '#mode-picker:not(.hidden)', `${name} mode picker`);
    await assertVisibleBox(page, '#mode-picker:not(.hidden) [data-mode-value="hysteria2"]', `${name} Hysteria2 mode choice`);
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
  await assertProtocolMenuGrid(page, `${name} keys protocol menu`, isMobile);
  await assertPoolKeysAreMasked(page, `${name} initial keys`);
  await assertNoBrokenImages(page, `${name} initial keys`);
  await clickLazyProtocol(page, 'hysteria2', `${name} Hysteria2 menu`);
  await assertVisibleBox(
    page,
    '[data-protocol-panel="hysteria2"].active [data-subview="key"].active',
    `${name} Hysteria2 key and subscription tab`,
  );
  const hysteria2KeyType = await page.locator(
    '[data-protocol-panel="hysteria2"].active [data-subview="key"].active .key-editor-form input[name="type"]',
  ).getAttribute('value');
  if (hysteria2KeyType !== 'hysteria2') {
    throw new Error(`${name}: Hysteria2 key form is not selected`);
  }
  if (modeConfig.expectPool) {
    await assertUnifiedImportLayout(page, `${name} Hysteria2 unified import`);
    const hysteria2ImportPlaceholder = await page.locator(
      '[data-protocol-panel="hysteria2"].active textarea[name="import_payload"]',
    ).getAttribute('placeholder');
    if (!String(hysteria2ImportPlaceholder || '').includes('hysteria2://')) {
      throw new Error(`${name}: Hysteria2 import placeholder is missing`);
    }
    await page.locator('[data-protocol-panel="hysteria2"].active [data-subview-target="pool"]').click();
    await assertVisibleBox(
      page,
      '[data-protocol-panel="hysteria2"].active [data-pool-filter]',
      `${name} Hysteria2 pool`,
    );
    await page.locator('[data-protocol-panel="hysteria2"].active [data-subview-target="check"]').click();
    await assertVisibleBox(
      page,
      '[data-protocol-panel="hysteria2"].active .service-route-tools',
      `${name} Hysteria2 checks and routes`,
    );
  }
  await clickLazyProtocol(page, 'vless', `${name} Vless return after Hysteria2 audit`);
  if (modeConfig.expectPool) {
    let injectedCheck404 = false;
    if (modeConfig.mode === 'advanced' && !isMobile) {
      injectedCheck404 = true;
      await page.route('**/api/protocol_check_panel?proto=*', async (route) => {
        await route.fulfill({
          status: 404,
          contentType: 'text/html; charset=utf-8',
          body: '<h1>404 Not Found</h1>',
        });
      }, { times: 1 });
    }
    await page.locator('[data-protocol-panel].active [data-subview-target="check"]').click();
    await assertVisibleBox(page, '[data-protocol-panel].active .service-route-tools', `${name} service route tools`);
    if (!isMobile && viewport.width >= 1024) {
      await assertCompactProtocolCheckWorkspace(page, name);
    }
    if (injectedCheck404) {
      for (let index = failures.length - 1; index >= 0; index -= 1) {
        if (
          failures[index].includes('/api/protocol_check_panel?proto=') ||
          failures[index].includes('Failed to load resource: the server responded with a status of 404')
        ) {
          failures.splice(index, 1);
        }
      }
    }
    const technicalCheckErrors = await page.getByText(/Unexpected token|not valid JSON/i).count();
    if (technicalCheckErrors) {
      throw new Error(`${name}: protocol check exposed a raw JSON parse error`);
    }
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
    if (modeConfig.mode === 'advanced' && viewportName === 'desktop') {
      let updateReadyRequests = 0;
      await page.route('**/?update_ready=*', async (route) => {
        updateReadyRequests += 1;
        if (updateReadyRequests === 1) {
          await route.fulfill({ status: 502, contentType: 'text/html', body: '<h1>502 Bad Gateway</h1>' });
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: 'text/html; charset=utf-8',
          body: '<div class="app-shell"><span class="version-badge">1.993</span></div>',
        });
      });
      await page.evaluate(() => {
        window.__updateReadyTestDone = false;
        window.__bypassTestHooks.waitForUpdatedWebServerBeforeReload('v1.993', {
          initialDelayMs: 0,
          retryDelayMs: 25,
          confirmationDelayMs: 25,
          requiredConfirmations: 2,
          onReady: () => { window.__updateReadyTestDone = true; },
        });
      });
      await page.waitForFunction(() => window.__updateReadyTestDone === true, null, { timeout: 10000 });
      if (updateReadyRequests < 3) {
        throw new Error(`${name}: update reload readiness did not retry after 502`);
      }
      await page.unroute('**/?update_ready=*');
      for (let index = failures.length - 1; index >= 0; index -= 1) {
        if (failures[index].includes('502')) {
          failures.splice(index, 1);
        }
      }

      let abortedRouteRequest = false;
      await page.route('**/service_route_apply', async (route) => {
        abortedRouteRequest = true;
        await route.abort('connectionreset');
      });
      const routeAction = page.locator('[data-protocol-panel].active .service-route-menu[open] form[action="/service_route_apply"] button').first();
      await routeAction.click();
      await page.waitForLoadState('domcontentloaded', { timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(1800);
      if (!abortedRouteRequest) {
        throw new Error(`${name}: service route recovery test did not intercept the action`);
      }
      const recoveryText = await page.locator('#web-action-message').innerText();
      if (!recoveryText.includes('Страница обновлена после применения')) {
        throw new Error(`${name}: service route fetch recovery message is missing: ${recoveryText}`);
      }
      await page.unroute('**/service_route_apply');
      failures.length = 0;
      await page.locator('.side-nav .nav-item[data-view-target="keys"]:visible, .mobile-nav .nav-item[data-view-target="keys"]:visible').click();
      await clickLazyProtocol(page, 'vless', `${name} route recovery`);
      await page.locator('[data-protocol-panel="vless"].active [data-subview-target="check"]').click();
      await assertVisibleBox(page, '[data-protocol-panel="vless"].active .service-route-trigger', `${name} recovered service routes`);
    }
    await assertVisibleBox(page, '[data-protocol-panel].active .route-intersection-card', `${name} route intersections`);
    await assertVisibleBox(page, '[data-protocol-panel].active .route-shared-card', `${name} allowed shared routes`);
    const sharedRouteCard = page.locator('[data-protocol-panel].active .route-shared-card').first();
    const sharedRouteText = await sharedRouteCard.innerText();
    for (const expected of ['accounts.google.com', 'vless.txt', 'vless-2.txt', 'ChatGPT / Codex', 'YouTube']) {
      if (!sharedRouteText.includes(expected)) {
        throw new Error(`${name}: allowed shared route details omit ${expected}`);
      }
    }
    const sharedDetailsOpen = await sharedRouteCard.locator('.route-shared-details').evaluate((node) => node.open);
    if (!sharedDetailsOpen) {
      throw new Error(`${name}: short allowed shared route list should be expanded`);
    }
    const sharedCopyControls = await sharedRouteCard.getByRole('button', { name: /Копировать/i }).count();
    if (sharedCopyControls) {
      throw new Error(`${name}: allowed shared route details unexpectedly contain a copy button`);
    }
    const sharedRouteTextFits = await sharedRouteCard.locator('.route-shared-entry').evaluateAll((nodes) => (
      nodes.every((node) => node.scrollWidth <= node.clientWidth + 2)
    ));
    if (!sharedRouteTextFits) {
      throw new Error(`${name}: allowed shared route details overflow`);
    }
    const serviceRouteText = await page.locator('[data-protocol-panel].active .service-route-tools').innerText();
    for (const expected of ['185/185', '1/185', '79/79', '1/79']) {
      if (!serviceRouteText.includes(expected)) {
        throw new Error(`${name}: service route coverage omits ${expected}`);
      }
    }
    await assertVisibleBox(page, '[data-protocol-panel].active .route-profile-panel', `${name} route profiles`);
    const routeTextFits = await page.locator('[data-protocol-panel].active .service-route-card').evaluateAll((nodes) => (
      nodes.every((node) => node.scrollWidth <= node.clientWidth + 2)
    ));
    if (!routeTextFits) {
      throw new Error(`${name}: service route cards overflow`);
    }
    await page.locator('[data-protocol-panel].active [data-subview-target="pool"]').click();
    await assertPoolServiceColumns(page, `${name} all-service pool`, isMobile);
    if (await page.locator('[data-pool-filter]').count()) {
      await assertVisibleBox(page, '[data-pool-filter]', `${name} pool filter`);
    }
    if (await page.locator('.pool-delete-btn').count()) {
      await assertVisibleBox(page, '[data-protocol-panel].active [data-pool-body] tr:first-child .pool-delete-btn', `${name} delete button`);
    }
    await assertActivePoolRowPinned(page, 'vless', `${name} vless pool order`);
    await assertPersistedCustomResultsRemainVisible(page, 'vless', `${name} saved custom results`);
    await assertProtocolStatusServiceMerge(page, `${name} protocol status merge`);
    await assertProtocolServiceIconsStableAfterIdleRefresh(page, 'vless', 5, `${name} vless status icons idle refresh`);
    await assertActiveTelegramCardConsistent(page, 'vless', `${name} vless Telegram status after idle refresh`);
    await assertProtocolServiceIconsStableAfterPoolRefresh(page, 'vless', 5, `${name} vless status icons pool refresh`);
    await assertActiveTelegramCardConsistent(page, 'vless', `${name} vless Telegram status after pool refresh`);
    await assertProtocolServiceIconsStableAfterLiveStatus(page, 'vless', 5, `${name} vless status icons apply refresh`);
    await assertActiveTelegramCardConsistent(page, 'vless', `${name} vless Telegram status after apply refresh`);
    await clickLazyProtocol(page, 'vless2', name);
    await page.locator('[data-protocol-panel="vless2"].active [data-subview-target="pool"]').click();
    await assertVisibleBox(page, '[data-protocol-panel="vless2"].active [data-pool-filter]', `${name} lazy pool filter`);
    await assertActivePoolRowPinned(page, 'vless2', `${name} original pool order`);
    await assertPoolKeysAreMasked(page, `${name} lazy keys`);
    await assertNoBrokenImages(page, `${name} lazy keys`);
    await page.locator('[data-protocol-panel="vless2"].active [data-subview-target="key"]').click();
    await assertVisibleBox(page, '[data-protocol-panel="vless2"].active [data-subview="key"].active', `${name} vless2 key and subscription tab`);
    const subtabCount = await page.locator('[data-protocol-panel="vless2"].active [data-subview-target]').count();
    if (subtabCount !== 3) {
      throw new Error(`${name}: expected 3 protocol subtabs, got ${subtabCount}`);
    }
    await assertUnifiedImportLayout(page, `${name} vless2 unified import`);
    await page.evaluate(() => localStorage.setItem('router-active-protocol', 'vless2'));
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.locator('.side-nav .nav-item[data-view-target="keys"]:visible, .mobile-nav .nav-item[data-view-target="keys"]:visible').click();
    await clickLazyProtocol(page, 'vless', `${name} vless1 return`);
    await page.locator('[data-protocol-panel="vless"].active [data-subview-target="pool"]').click();
    await assertActivePoolRowPinned(page, 'vless', `${name} vless1 return pool order`);
    await assertPoolKeysAreMasked(page, `${name} vless1 return keys`);
  } else {
    const poolOnlyControls = await page.locator('[data-pool-filter], .pool-toolbar, [data-subview-target="pool"], [data-subview-target="check"], .service-route-tools, .pool-import-form').count();
    if (poolOnlyControls) {
      throw new Error(`${name}: pool-only controls are rendered in simple mode`);
    }
  }
  await assertNoHorizontalOverflow(page, `${name} keys`);

  await page.locator('.side-nav .nav-item[data-view-target="lists"]:visible, .mobile-nav .nav-item[data-view-target="lists"]:visible').click();
  await assertVisibleBox(page, '[data-view="lists"].active', `${name} lists view`);
  await assertProtocolMenuGrid(page, `${name} lists protocol menu`, isMobile);
  const hysteria2ListTab = page.locator('.list-tab[data-list-target="hysteria2.txt"]');
  if (await hysteria2ListTab.count() !== 1 || !(await hysteria2ListTab.innerText()).includes('Hysteria2')) {
    throw new Error(`${name}: Hysteria2 list menu is missing`);
  }
  await hysteria2ListTab.click();
  await assertVisibleBox(page, '[data-list-panel="hysteria2.txt"].active', `${name} Hysteria2 list editor`);
  await assertNoBrokenImages(page, `${name} lists`);
  await assertNoHorizontalOverflow(page, `${name} lists`);
  if (!isMobile) {
    await assertDesktopListEditorSizing(page, `${name} lists`);
  }
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
      await runViewport(browser, modeConfig, 'full HD desktop', { width: 1920, height: 1080 });
      await runViewport(browser, modeConfig, 'full HD 16:10 desktop', { width: 1920, height: 1200 });
      await runViewport(browser, modeConfig, '2K 16:9 desktop', { width: 2560, height: 1440 });
      await runViewport(browser, modeConfig, '2K 16:10 desktop', { width: 2560, height: 1600 });
      await runViewport(browser, modeConfig, '4K 16:9 desktop', { width: 3840, height: 2160 });
      await runViewport(browser, modeConfig, '4K 16:10 desktop', { width: 3840, height: 2400 });
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
