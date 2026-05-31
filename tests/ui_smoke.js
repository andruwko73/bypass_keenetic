const { chromium, devices } = require('playwright');

const targetUrl = process.env.BYPASS_UI_URL || 'http://192.168.1.1:8080/';
const chromeExecutable = process.env.CHROME_EXECUTABLE || undefined;
const leakedFixtureKeys = [
  'vless://fixture-backup-vless',
  'vless://fixture-backup-vless2',
];

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

async function assertVisibleBox(page, selector, label) {
  const box = await page.locator(selector).boundingBox();
  if (!box || box.width < 2 || box.height < 2) {
    throw new Error(`${label}: ${selector} is not visibly sized`);
  }
  return box;
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
  const rows = await page.locator(`[data-protocol-panel="${protocol}"].active [data-pool-body="${protocol}"]`).evaluate((body) => (
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

async function runViewport(browser, name, viewport, isMobile = false) {
  const context = await browser.newContext({
    viewport,
    isMobile,
    hasTouch: isMobile,
    deviceScaleFactor: isMobile ? 2 : 1,
  });
  const page = await context.newPage();
  const failures = watchPage(page, name);
  await page.addInitScript(() => localStorage.setItem('router-theme', 'glass'));
  await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});

  await assertVisibleBox(page, '.topbar', `${name} topbar`);
  await assertVisibleBox(page, '[data-view="status"].active .view-head', `${name} overview`);
  await assertNoHorizontalOverflow(page, name);

  const titleFits = await page.locator('.app-caption strong').evaluate((node) => node.scrollWidth <= node.clientWidth + 2);
  if (!titleFits) {
    throw new Error(`${name}: header title is clipped`);
  }

  await page.locator('#theme-toggle-button').click();
  await assertVisibleBox(page, '#theme-picker:not(.hidden)', `${name} theme picker`);
  await page.locator('#theme-toggle-button').click();

  if (await page.locator('#mode-toggle-button').count()) {
    await page.locator('#mode-toggle-button').click();
    await assertVisibleBox(page, '#mode-picker:not(.hidden)', `${name} mode picker`);
    await page.locator('#mode-toggle-button').click();
  }

  await page.locator('.side-nav .nav-item[data-view-target="keys"]:visible, .mobile-nav .nav-item[data-view-target="keys"]:visible').click();
  await assertVisibleBox(page, '[data-view="keys"].active', `${name} keys view`);
  await assertPoolKeysAreMasked(page, `${name} initial keys`);
  await page.locator('[data-protocol-panel].active [data-subview-target="check"]').click();
  await assertVisibleBox(page, '[data-protocol-panel].active .service-route-tools', `${name} service route tools`);
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
  await assertNoHorizontalOverflow(page, `${name} keys`);
  assertNoPageFailures(failures);

  await context.close();
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: chromeExecutable,
  });
  try {
    await runViewport(browser, 'desktop', { width: 1365, height: 768 });
    await runViewport(browser, 'compact desktop', { width: 915, height: 640 });
    await runViewport(browser, 'mobile', devices['Pixel 5'].viewport, true);
  } finally {
    await browser.close();
  }
  console.log('UI smoke passed:', targetUrl);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
