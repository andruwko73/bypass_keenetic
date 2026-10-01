const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    for (const mode of ['advanced', 'web_only', 'simple']) {
      for (const viewport of [{width:1280,height:720}, {width:390,height:844}, {width:320,height:568}]) {
        const page = await browser.newPage({viewport});
        const failures = [];
        page.on('pageerror', error => failures.push(error.message));
        const url = new URL(process.env.BYPASS_UI_URL);
        url.searchParams.set('mode', mode);
        await page.goto(url.href, {waitUntil:'networkidle'});
        if (mode !== 'simple') {
          for (const [name,label] of Object.entries({subscriptions:'Подписки:',queue:'Следующая попытка'})) {
            const line = page.locator('#pool-automation-' + name);
            await line.scrollIntoViewIfNeeded();
            assert.ok(await line.isVisible());
            assert.ok((await line.innerText()).includes(label));
            const bounds = await line.boundingBox();
            assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= viewport.width + 1);
          }
          const last = page.locator('#pool-latest-run-summary');
          assert.match(await last.innerText(), /^Последняя проверка: завершена · 29\.09 03:30\./);
          assert.equal(await page.locator('#pool-automation-manual, #pool-automation-automatic').count(), 0);
          assert.equal((await page.locator('.key-pool-card').innerText()).split('Последняя проверка:').length - 1, 1);
          const button = page.locator('.key-pool-card [data-pool-probe-start-button]');
          await button.scrollIntoViewIfNeeded();
          assert.ok(await button.isVisible());
        } else {
          assert.equal(await page.locator('#pool-automation-queue').count(), 0);
        }
        assert.deepEqual(failures, []);
        console.log(`Scheduler UI passed: ${mode} ${viewport.width}x${viewport.height}`);
        await page.close();
      }
    }
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
