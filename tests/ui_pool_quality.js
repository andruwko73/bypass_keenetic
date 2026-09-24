const assert = require('node:assert/strict');
const {chromium} = require('playwright');

async function checkQuality(browser, mode, viewport, label) {
  const context = await browser.newContext({viewport, isMobile:label === 'mobile'});
  try {
    const page = await context.newPage();
    const errors=[];
    page.on('pageerror', error => errors.push(String(error)));
    await page.addInitScript(() => {
      localStorage.setItem('router-active-protocol','vless');
      localStorage.setItem('router-theme','glass');
    });
    const rows = [
      {key_id:'fixture-france', display_name:'Франция', tg:'fail', yt:'fail', yt_score:99, checked_ts:999},
      {key_id:'fixture-partial', display_name:'Без замера скорости', tg:'ok', yt:'ok', yt_score:75, checked_ts:100},
      {key_id:'fixture-best', display_name:'С замером скорости', tg:'ok', yt:'ok', yt_score:95, checked_ts:90,
       yt_quality:'fast', yt_quality_label:'Быстро'},
      {key_id:'fixture-warn', display_name:'Нестабильный', tg:'ok', yt:'warn', yt_score:99, checked_ts:99},
      {key_id:'fixture-unknown', display_name:'Не проверен', tg:'unknown', yt:'unknown', yt_score:100, checked_ts:999},
      {key_id:'fixture-slow', display_name:'Медленный рабочий', tg:'ok', yt:'ok', yt_score:30, checked_ts:99},
      {key_id:'fixture-active', display_name:'Активный', active:true, tg:'fail', yt:'fail', yt_score:0, checked_ts:99},
    ].map((row,index) => ({...row, index:index+1, checked_at:'01.01 12:00', custom:{},
      quality_summary: row.key_id === 'fixture-partial'
        ? 'Оценка YouTube: 75/100 — выше лучше; это баллы, не проценты\nПредварительная оценка: скорость скачивания не измерена'
        : 'Результат тестовой проверки'}));
    await page.route('**/api/pools*', route => route.fulfill({json:{pools:{vless:{label:'Vless 1', count:rows.length,
      core_services:['telegram','youtube'], custom_checks:[], rows}}, timestamp:Date.now()/1000}}));
    await page.goto(process.env.BYPASS_UI_URL + '?mode=' + mode);
    await page.locator('.nav-item[data-view-target="keys"]:visible').click();
    await page.locator('[data-protocol-panel="vless"] [data-subview-target="pool"]').click();
    const body=page.locator('[data-pool-body="vless"]');
    await page.waitForFunction(() => document.querySelector('[data-key-id="fixture-partial"]'));
    const sort=async value => {
      await page.locator('[data-pool-sort-button="vless"]').click();
      await page.locator(`[data-pool-sort-menu="vless"] [data-pool-sort-value="${value}"]`).click();
    };
    const order=() => body.locator('[data-pool-row]').evaluateAll(nodes => nodes.map(n => n.dataset.keyId));
    const expected=['fixture-active','fixture-best','fixture-partial','fixture-slow','fixture-warn','fixture-unknown','fixture-france'];
    await sort('quality');
    assert.deepEqual(await order(), expected);
    assert.equal(await page.locator('[data-pool-sort-button="vless"]').innerText(),'Качество YouTube');
    const partial=body.locator('[data-key-id="fixture-partial"]');
    assert.equal(await partial.locator('.pool-quality-badge').count(),0);
    assert.match(await partial.locator('.pool-apply-btn').getAttribute('title'), /75\/100[\s\S]*скорость скачивания не измерена/);
    await sort('youtube');
    assert.deepEqual(await order(), expected);
    await sort('original');
    assert.deepEqual(await order(), ['fixture-active', ...rows.filter(row => !row.active).map(row => row.key_id)]);
    await sort('quality');
    // Keep IDs/count unchanged: exercise in-place API refresh and re-sorting.
    rows[0].yt='ok'; rows[0].tg='ok'; rows[0].yt_score=88;
    rows[2].yt='fail'; rows[2].tg='fail'; rows[2].yt_score=0;
    rows[2].yt_quality=''; rows[2].yt_quality_label='';
    rows[2].quality_summary='YouTube: не работает по последней проверке\nОценка YouTube: 0/100';
    await page.evaluate(() => window.__bypassTestHooks.refreshPoolData(0,['vless']));
    await page.waitForFunction(() => document.querySelector('[data-key-id="fixture-best"]').dataset.ytState === 'fail');
    assert.deepEqual(await order(), ['fixture-active','fixture-france','fixture-partial','fixture-slow','fixture-warn','fixture-unknown','fixture-best']);
    assert.equal(await body.locator('[data-key-id="fixture-best"] .pool-quality-badge').count(),0);
    assert.match(await body.locator('[data-key-id="fixture-best"] .pool-apply-btn').getAttribute('title'), /0\/100/);
    const overflow=await page.locator('[data-pool-sort-button="vless"]').evaluate(n => n.scrollWidth > n.clientWidth+2);
    assert.equal(overflow,false,'Quality button text clipped');
    assert.equal(await body.locator('input[name="key"], [data-key]').count(),0);
    assert.deepEqual(errors,[]);
    console.log(`Pool quality UI passed: ${mode}/${label}`);
  } finally { await context.close(); }
}

(async () => {
  const url=new URL(process.env.BYPASS_UI_URL);
  assert(['127.0.0.1','localhost','[::1]'].includes(url.hostname),'Use a local fixture');
  const browser=await chromium.launch({headless:true, executablePath:process.env.CHROME_EXECUTABLE || undefined});
  try {
    for (const mode of ['advanced','web_only']) {
      for (const [label,width,height] of [['desktop',1365,768],['compact desktop',915,640],['mobile',393,851]]) {
        await checkQuality(browser,mode,{width,height},label);
      }
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode=1; });
