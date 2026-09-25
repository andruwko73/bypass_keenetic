const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const protocols = ['vless', 'vless2', 'vmess', 'trojan', 'hysteria2', 'shadowsocks'];
const files = ['vless.txt', 'vless-2.txt', 'vmess.txt', 'trojan.txt', 'hysteria2.txt', 'shadowsocks.txt'];
const refusedPages = new WeakSet();

function isExpectedBulkError(page, message) {
  return refusedPages.has(page)
    && new URL(message.location().url || 'about:blank').pathname === '/route_list_move'
    && message.text().includes('503 (Service Unavailable)');
}

async function checkBulkRoutes(page, mode, viewport) {
  viewport = viewport.replace(mode + ' ', '');
  const menu = page.locator('[data-view="lists"] .bulk-service-route-menu');
  const trigger = menu.locator('summary');
  assert.equal(await menu.count(), 1);
  assert.equal(await page.locator('[data-view="keys"] form[action="/service_profile_apply"]').count(), 0);
  assert.equal(await menu.locator('form').count(), protocols.length);
  assert.deepEqual(await menu.locator('[name="target_list"]').evaluateAll(nodes => nodes.map(n => n.value)), files);
  await trigger.focus();
  await trigger.press('Enter');
  assert.equal(await menu.getAttribute('open'), '');
  assert.equal(await menu.locator('button:disabled').count(), 1);
  assert.equal(await menu.locator('[name="source_list"]').first().inputValue(), 'hysteria2.txt');
  const last = menu.locator('button').last();
  // Real scrolling followed by hit testing: no locator auto-scroll to the last option.
  for (let index = 0; index < 8; index++) {
    const hit = await last.evaluate(node => {
      const r = node.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
      return y > 0 && y < innerHeight && node.contains(document.elementFromPoint(x, y));
    });
    if (hit) break;
    const r = await trigger.boundingBox();
    await page.mouse.move(r.x + r.width / 2, Math.min(page.viewportSize().height - 50, r.y + r.height + 50));
    await page.mouse.wheel(0, 160);
    await page.waitForTimeout(80);
  }
  assert(await last.evaluate(node => {
    const r=node.getBoundingClientRect();
    return node.contains(document.elementFromPoint(r.left+r.width/2,r.top+r.height/2));
  }), `${mode}/${viewport}: last protocol is clipped`);
  if (process.env.BYPASS_BULK_SCREENSHOTS && mode === 'advanced' && ['desktop','compact desktop','mobile'].includes(viewport)) {
    fs.mkdirSync(process.env.BYPASS_BULK_SCREENSHOTS, {recursive:true});
    await page.screenshot({path:path.join(process.env.BYPASS_BULK_SCREENSHOTS, viewport.replaceAll(' ','-')+'.png')});
  }
  await page.keyboard.press('Escape');
  assert.equal(await menu.getAttribute('open'), null);

  // Mutation/race matrix once; the placement/scroll matrix above runs in every mode/viewport.
  if (viewport !== 'desktop') return;
  const editor = page.locator('[data-list-panel="hysteria2.txt"] textarea');
  const original = await editor.inputValue();
  let requests = [], fail = false;
  let responseDelay = 180, progressRequests = 0;
  let contents = {};
  await page.route('**/api/route_move_status', async route => {
    progressRequests++;
    await route.fulfill({json:{running:true, stage:'Обновление DNS и адресов', elapsed_seconds:2}});
  });
  await page.route('**/route_list_move', async route => {
    const params = new URLSearchParams(route.request().postData());
    requests.push([params.get('source_list'), params.get('target_list')]);
    await new Promise(resolve => setTimeout(resolve, responseDelay));
    await route.fulfill({status:fail ? 503 : 200, contentType:'application/json',
      body:JSON.stringify(fail ? {ok:false,result:'Fixture refusal'} : {ok:true,result:'Список перенесён',list_contents:contents})});
  });
  try {
    await editor.fill('unsaved.example');
    await trigger.click();
    await menu.locator('button').first().click();
    await page.waitForFunction(() => document.querySelector('#web-action-message').textContent.includes('Сначала сохраните'));
    assert.equal(requests.length, 0);
    assert.equal(await editor.inputValue(), 'unsaved.example');
    await editor.fill(original);
    fail = true;
    refusedPages.add(page);
    await menu.locator('button').first().click();
    await page.waitForFunction(() => document.querySelector('#web-action-message').textContent.includes('Fixture refusal'));
    await page.waitForFunction(() => !document.querySelector('[data-list-panel="hysteria2.txt"] textarea').disabled);
    assert.equal(await editor.inputValue(), original);
    refusedPages.delete(page);
    fail = false;
    let source = 'hysteria2.txt';
    for (const target of files) {
      const before = Object.fromEntries(await page.locator('[data-list-panel]').evaluateAll(nodes => nodes.map(n =>
        [n.dataset.listPanel, n.querySelector('textarea').value])));
      contents = {[source]: '', [target]: 'custom.example\n192.0.2.3\nexisting.example'};
      if (!(await menu.getAttribute('open') !== null)) await trigger.click();
      const form = menu.locator('form').filter({has:page.locator(`[name="target_list"][value="${target}"]`)});
      const start = requests.length;
      responseDelay = target === files[0] ? 2200 : 180;
      await form.locator('button').click();
      await page.waitForFunction(() => document.querySelector('[data-list-panel].active textarea').disabled);
      if (target === files[0]) {
        await page.waitForFunction(() => document.querySelector('#web-action-message').textContent.includes('Обновление DNS и адресов'));
        assert(progressRequests > 0, 'No actual move-stage polling');
      }
      await form.evaluate(node => node.requestSubmit(node.querySelector('button')));
      await page.waitForFunction(() => !document.querySelector('[data-list-panel].active textarea').disabled);
      assert.equal(requests.length, start+1, 'Duplicate bulk apply');
      assert.deepEqual(requests.at(-1), [source, target]);
      assert.equal(await menu.getAttribute('open'), null);
      for (const file of files) {
        const field = page.locator(`[data-list-panel="${file}"] textarea`);
        assert.equal(await field.inputValue(), contents[file] ?? before[file]);
        if (file in contents) assert.equal(await field.evaluate(node => node.defaultValue), contents[file]);
      }
      await page.locator(`[data-list-target="${target}"]`).click();
      source = target;
    }
    // A saved-list request must finish before a bulk move may begin.
    let releaseSave, saveStarted;
    const saved = new Promise(resolve => { saveStarted = resolve; });
    await page.route('**/save_unblock_list', async route => {
      saveStarted();
      await new Promise(resolve => { releaseSave = resolve; });
      const params = new URLSearchParams(route.request().postData());
      await route.fulfill({json:{ok:true, result:'Список сохранён', list_name:source, list_content:params.get('content')}});
    });
    const prior = requests.length;
    await page.locator('[data-list-panel].active [data-list-save]').click();
    await saved;
    await trigger.click();
    await menu.locator('button:enabled').first().click();
    await page.waitForFunction(() => document.querySelector('#web-action-message').textContent.includes('Дождитесь'));
    assert.equal(requests.length, prior);
    releaseSave();
    await page.waitForFunction(() => !document.querySelector('[data-list-panel].active [data-list-save]').disabled);
    await page.unroute('**/save_unblock_list');
    await page.keyboard.press('Escape');

    // An older lazy GET must not overwrite the successful transfer response.
    let releaseLoad, loadStarted;
    const loaded = new Promise(resolve => { loadStarted = resolve; });
    await page.route('**/api/unblock_list?name=vless.txt', async route => {
      loadStarted();
      await new Promise(resolve => { releaseLoad = resolve; });
      await route.fulfill({json:{ok:true, content:'stale.example', line_count:1}});
    });
    await page.locator('[data-list-panel="vless.txt"]').evaluate(panel => {
      panel.dataset.listLoaded='0';
      const field=panel.querySelector('textarea');
      field.value=''; field.defaultValue=''; field.disabled=true;
    });
    await page.locator('[data-list-target="vless.txt"]').click();
    await loaded;
    contents={'vless.txt':'', 'hysteria2.txt':'custom.example\n192.0.2.3'};
    await trigger.click();
    await menu.locator('form').filter({has:page.locator('[name="target_list"][value="hysteria2.txt"]')}).locator('button').click();
    await page.waitForFunction(() => !document.querySelector('[data-list-panel="vless.txt"] textarea').disabled);
    releaseLoad();
    await page.waitForResponse(response => response.url().includes('/api/unblock_list?name=vless.txt'));
    await page.waitForTimeout(100);
    assert.equal(await page.locator('[data-list-panel="vless.txt"] textarea').inputValue(), '');
    await page.unroute('**/api/unblock_list?name=vless.txt');
    const pollsAtEnd = progressRequests;
    await page.waitForTimeout(1700);
    assert.equal(progressRequests, pollsAtEnd, 'Move polling continued after completion');
  } finally {
    refusedPages.delete(page);
    await page.unroute('**/route_list_move');
    await page.unroute('**/api/route_move_status');
  }
}

module.exports = { checkBulkRoutes, isExpectedBulkError };

if (require.main === module) {
  (async () => {
    const {chromium} = require('playwright');
    const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_EXECUTABLE || undefined});
    try {
      for (const mode of ['advanced', 'simple', 'web_only']) {
        for (const [label, width, height] of [['desktop',1365,768], ['compact desktop',915,640], ['mobile',393,851]]) {
          const context = await browser.newContext({viewport:{width,height}, isMobile:label === 'mobile'});
          try {
            const page = await context.newPage();
            await page.goto(process.env.BYPASS_UI_URL + '?mode=' + mode);
            await page.locator('.nav-item[data-view-target="lists"]:visible').click();
            await page.locator('[data-list-target="hysteria2.txt"]').click();
            await page.waitForFunction(() => !document.querySelector('[data-list-panel].active textarea').disabled);
            await checkBulkRoutes(page, mode, label);
            console.log(`List transfer UI passed: ${mode}/${label}`);
          } finally { await context.close(); }
        }
      }
    } finally { await browser.close(); }
  })().catch(error => { console.error(error); process.exitCode=1; });
}
