const { chromium, devices } = require('playwright');

const targetUrl = process.env.BYPASS_UI_URL || 'http://192.168.1.1:8080/';
const chromeExecutable = process.env.CHROME_EXECUTABLE || undefined;

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

async function runViewport(browser, name, viewport, isMobile = false) {
  const context = await browser.newContext({
    viewport,
    isMobile,
    hasTouch: isMobile,
    deviceScaleFactor: isMobile ? 2 : 1,
  });
  const page = await context.newPage();
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
  await page.locator('[data-protocol-panel].active [data-subview-target="pool"]').click();
  if (await page.locator('[data-pool-filter]').count()) {
    await assertVisibleBox(page, '[data-pool-filter]', `${name} pool filter`);
  }
  if (await page.locator('.pool-delete-btn').count()) {
    await assertVisibleBox(page, '[data-protocol-panel].active [data-pool-body] tr:first-child .pool-delete-btn', `${name} delete button`);
  }
  await assertNoHorizontalOverflow(page, `${name} keys`);

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
