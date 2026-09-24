const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const http = require('node:http');
const net = require('node:net');
const path = require('node:path');
const fs = require('node:fs');
const { chromium } = require('playwright');

const root = path.resolve(process.env.BYPASS_ROUTE_UI_FIXTURE_ROOT || path.join(__dirname, '..'));

// Never use locator.click/scrollIntoView to prove reachability: both can scroll
// overflow:hidden ancestors that a real wheel/touch gesture cannot scroll.
async function reachByGesture(page, locator, touch = false) {
  const session = touch ? await page.context().newCDPSession(page) : null;
  try {
    for (let attempt = 0; attempt < 35; attempt++) {
      const target = await locator.evaluate(node => {
        const r = node.getBoundingClientRect();
        const x = r.left + r.width / 2, y = r.top + r.height / 2;
        const hit = document.elementFromPoint(x, y);
        return { x, y, reachable: r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth && (node === hit || node.contains(hit)) };
      });
      if (target.reachable) {
        // Let touch inertia settle before hit-testing and tapping a fixed point.
        await page.waitForTimeout(touch ? 250 : 40);
        const settled = await locator.boundingBox();
        if (settled && Math.abs(settled.y + settled.height / 2 - target.y) < 1) return target;
        continue;
      }
      const { width, height } = page.viewportSize();
      const down = target.y > height / 2;
      if (session) {
        const start = height * (down ? .8 : .2), end = height * (down ? .2 : .8);
        await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: width / 2, y: start }] });
        for (let step = 1; step <= 5; step++) {
          await session.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: width / 2, y: start + (end - start) * step / 5 }] });
          await page.waitForTimeout(20);
        }
        // Lift a stationary finger: a fling can consume the next tap even at
        // the scroll boundary, where bounding rectangles already look stable.
        await page.waitForTimeout(200);
        await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
      } else {
        await page.mouse.move(width / 2, height / 2);
        await page.mouse.wheel(0, (down ? 1 : -1) * height * .7);
      }
      await page.waitForTimeout(100);
    }
    throw new Error('Action is unreachable with ordinary wheel/touch scrolling');
  } finally { if (session) await session.detach(); }
}

async function userClick(page, locator, touch) {
  const { x, y } = await reachByGesture(page, locator, touch);
  if (touch) await page.touchscreen.tap(x, y);
  else await page.mouse.click(x, y);
}
function selectPort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(error => error ? reject(error) : resolve(port));
    });
  });
}
function request(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, response => {
      response.resume();
      response.once('end', () => resolve(response.statusCode));
    });
    req.once('error', reject);
    req.setTimeout(1000, () => req.destroy(new Error('timeout')));
  });
}
async function main() {
  const port = await selectPort();
  const url = `http://127.0.0.1:${port}`;
  const args = [...(process.platform === 'win32' ? ['-3.11'] : []), '-B', 'tests/route_diagnostics_fixture.py', '--port', String(port)];
  const fixture = spawn(process.platform === 'win32' ? 'py' : 'python3', args, { cwd: root, stdio: 'ignore', windowsHide: true });
  let browser;
  try {
    let ready = false;
    for (let i = 0; i < 40; i++) {
      if (await request(url).catch(() => 0) === 200) { ready = true; break; }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert(ready, 'Fixture failed to start');
    browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_EXECUTABLE || undefined });
    const cases = [
      ['compact', 1024, 600, 'dark'], ['desktop', 1366, 768, 'dark'],
      ['desktop-light', 1366, 768, 'light'], ['desktop-glass', 1366, 768, 'glass'],
      ['scaled-desktop', 780, 438, 'dark', false, 1.75],
      ['mobile', 390, 844, 'dark', true], ['mobile-light', 390, 844, 'light', true],
      ['mobile-glass', 390, 844, 'glass', true], ['narrow-mobile', 320, 568, 'dark', true],
    ];
    for (const [name, width, height, theme, touch = false, deviceScaleFactor = 1] of cases) {
      if (process.env.BYPASS_ROUTE_UI_CASE && name !== process.env.BYPASS_ROUTE_UI_CASE) continue;
      const context = await browser.newContext({ viewport: { width, height }, hasTouch: touch, isMobile: touch, deviceScaleFactor });
      await context.addInitScript(theme => localStorage.setItem('router-theme', theme), theme);
      const page = await context.newPage();
      page.fixtureCase = name;
      const errors = [];
      const apiRequests = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { const pathname = new URL(request.url()).pathname; if (pathname.startsWith('/api/')) apiRequests.push(pathname); });
      await page.goto(url);
      await page.waitForLoadState('networkidle');
      await page.evaluate(() => {
        window.fixtureClicks = [];
        document.addEventListener('click', event => window.fixtureClicks.push({tag:event.target.tagName, id:event.target.id, text:event.target.closest('button')?.textContent}), true);
      });
      const save = page.getByRole('button', { name: 'Сохранить профиль', exact: true });
      await reachByGesture(page, save, touch);
      assert.equal(await page.locator('html').getAttribute('data-theme'), theme, name+' saved theme');
      assert.equal(await page.locator('html').getAttribute('data-user-background'), 'enabled', name+' saved background');
      const styles = await page.evaluate(() => ({
        title: parseFloat(getComputedStyle(document.querySelector('h1')).fontSize),
        hint: parseFloat(getComputedStyle(document.querySelector('.field-hint')).fontSize),
        border: getComputedStyle(document.querySelector('#route-profile-form')).borderRadius,
      }));
      assert(styles.title <= 20 && styles.hint <= 13 && styles.border === '10px', name+' shared panel typography');
      await page.getByRole('textbox', { name: 'Название', exact: true }).fill('Видео на ПК');
      await page.getByRole('textbox', { name: 'HTTPS-адрес сервиса' }).fill('https://example.com/');
      await page.getByRole('textbox', { name: 'Устройство', exact: true }).fill('192.168.1.50');
      await userClick(page, save, touch);
      try { await page.locator('[data-route-run]').waitFor({ timeout: 5000 }); }
      catch (error) {
        if (process.env.BYPASS_ROUTE_UI_ARTIFACTS) await page.screenshot({path: path.join(process.env.BYPASS_ROUTE_UI_ARTIFACTS, name+'-failure.png'), fullPage: true});
        console.error(name, await page.evaluate(() => ({
          error: document.querySelector('#route-error').textContent,
          invalid: [...document.querySelectorAll('#route-profile-form :invalid')].map(node => ({name: node.name, reason: node.validationMessage})),
          viewport: {width: innerWidth, scale: visualViewport.scale, offset: visualViewport.offsetTop},
          profiles: document.querySelectorAll('[data-route-run]').length,
        })));
        throw error;
      }
      await userClick(page, page.getByRole('button', { name: 'Проверить маршрут', exact: true }), touch);
      await page.getByText('Рекомендация: Vless 2', { exact: true }).waitFor({ timeout: 10000 });
      assert(await page.locator('#route-cancel').isHidden(), 'Completed job still has a stop button');
      assert(await page.getByText('Игровая задержка, UDP и потери пакетов: нет данных.', { exact: true }).isVisible());
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), name+' horizontal overflow');
      await reachByGesture(page, save, touch);
      if (process.env.BYPASS_ROUTE_UI_ARTIFACTS) {
        fs.mkdirSync(process.env.BYPASS_ROUTE_UI_ARTIFACTS, { recursive: true });
        await page.screenshot({ path: path.join(process.env.BYPASS_ROUTE_UI_ARTIFACTS, name+'.png'), fullPage: true });
      }
      // A stale form must show the server error without losing entered text.
      await page.getByRole('textbox', { name: 'Название', exact: true }).fill('Новая проверка');
      await page.getByRole('textbox', { name: 'HTTPS-адрес сервиса' }).fill('https://127.0.0.1/');
      await userClick(page, save, touch);
      await page.locator('#route-error').filter({ hasText: 'публичный адрес' }).waitFor();
      assert.equal(await page.getByRole('textbox', { name: 'Название', exact: true }).inputValue(), 'Новая проверка');
      await userClick(page, page.getByRole('button', { name: 'Удалить профиль', exact: true }), touch);
      await page.getByText('Добавьте профиль устройства и адрес сервиса, чтобы сравнить доступные пути.', { exact: true }).waitFor();
      assert.deepEqual(errors, []);
      assert(apiRequests.every(route => ['/api/route_diagnostics', '/api/ui_background'].includes(route)), name+' unexpected main-panel polling');
      await context.close();
      console.log(name+': profile actions, wheel/touch reachability, theme, background, compact styles, no extra polling passed');
    }
  } catch (error) {
    const page = browser?.contexts().flatMap(context => context.pages()).at(-1);
    if (page && !page.isClosed()) {
      if (process.env.BYPASS_ROUTE_UI_ARTIFACTS) await page.screenshot({ path:path.join(process.env.BYPASS_ROUTE_UI_ARTIFACTS, page.fixtureCase+'-failure.png'), fullPage:true });
      console.error(await page.evaluate(() => ({error:document.querySelector('#route-error')?.textContent,
        clicks:window.fixtureClicks?.slice(-6), viewport:{width:innerWidth, height:innerHeight, scale:visualViewport.scale, offset:visualViewport.offsetTop},
        invalid:[...document.querySelectorAll(':invalid')].map(node => ({name:node.name, reason:node.validationMessage}))})));
    }
    throw error;
  } finally {
    if (browser) await browser.close();
    await request(url+'/fixture/stop').catch(() => {});
    if (fixture.exitCode === null) {
      await Promise.race([new Promise(resolve => fixture.once('exit', resolve)), new Promise(resolve => setTimeout(resolve, 2000))]);
      if (fixture.exitCode === null) fixture.kill();
    }
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
