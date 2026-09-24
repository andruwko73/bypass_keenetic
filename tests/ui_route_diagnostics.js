const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const http = require('node:http');
const net = require('node:net');
const path = require('node:path');
const fs = require('node:fs');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
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
    for (const [name, viewport] of Object.entries({ desktop: { width: 1366, height: 900 }, mobile: { width: 390, height: 844 } })) {
      const context = await browser.newContext({ viewport });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(url);
      await page.waitForLoadState('networkidle');
      await page.getByRole('textbox', { name: 'Название', exact: true }).fill('Видео на ПК');
      await page.getByRole('textbox', { name: 'HTTPS-адрес сервиса' }).fill('https://example.com/');
      await page.getByRole('textbox', { name: 'Устройство', exact: true }).fill('192.168.1.50');
      await page.getByRole('button', { name: 'Сохранить профиль', exact: true }).click();
      await page.locator('[data-route-run]').waitFor();
      await page.getByRole('button', { name: 'Проверить маршрут', exact: true }).click();
      await page.getByText('Рекомендация: Vless 2', { exact: true }).waitFor({ timeout: 10000 });
      assert(await page.locator('#route-cancel').isHidden(), 'Completed job still has a stop button');
      assert(await page.getByText('Игровая задержка, UDP и потери пакетов: нет данных.', { exact: true }).isVisible());
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), name+' horizontal overflow');
      await page.getByRole('button', { name: 'Сохранить профиль', exact: true }).scrollIntoViewIfNeeded();
      assert(await page.getByRole('button', { name: 'Сохранить профиль', exact: true }).isVisible());
      if (process.env.BYPASS_ROUTE_UI_ARTIFACTS) {
        fs.mkdirSync(process.env.BYPASS_ROUTE_UI_ARTIFACTS, { recursive: true });
        await page.screenshot({ path: path.join(process.env.BYPASS_ROUTE_UI_ARTIFACTS, name+'.png'), fullPage: true });
      }
      // A stale form must show the server error without losing entered text.
      await page.getByRole('textbox', { name: 'Название', exact: true }).fill('Новая проверка');
      await page.getByRole('textbox', { name: 'HTTPS-адрес сервиса' }).fill('https://127.0.0.1/');
      await page.getByRole('button', { name: 'Сохранить профиль', exact: true }).click();
      await page.locator('#route-error').filter({ hasText: 'публичный адрес' }).waitFor();
      assert.equal(await page.getByRole('textbox', { name: 'Название', exact: true }).inputValue(), 'Новая проверка');
      await page.getByRole('button', { name: 'Удалить профиль', exact: true }).click();
      await page.getByText('Добавьте профиль устройства и адрес сервиса, чтобы сравнить доступные пути.', { exact: true }).waitFor();
      assert.deepEqual(errors, []);
      await context.close();
      console.log(name+': profile save, probe, recommendation, error, delete, scrolling passed');
    }
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
