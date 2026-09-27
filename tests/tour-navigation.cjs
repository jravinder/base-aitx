// Tour routing contract on actual pages. Page interactions are covered by focused suites.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('/Users/red/.agents/skills/gstack/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const origin = 'https://tour.test';
const mime = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.jpg':'image/jpeg','.png':'image/png','.ttf':'font/ttf'};
(async () => {
  const {tours} = JSON.parse(await fs.readFile(path.join(root,'web/data/tours.json')));
  const browser = await chromium.launch({headless:true});
  let checks = 0;
  try {
    const page = await browser.newPage();
    page.setDefaultTimeout(10000);
    await page.route('**/*', async route => {
      const u = new URL(route.request().url());
      if (u.origin !== origin || route.request().method() !== 'GET') return route.abort();
      const file = path.resolve(root,'.'+u.pathname);
      if (!file.startsWith(root+path.sep)) return route.abort();
      try { await route.fulfill({body:await fs.readFile(file),contentType:mime[path.extname(file)]||'text/plain'}); }
      catch { await route.fulfill({status:404,body:''}); }
    });
    for (const tour of tours) {
      const start = new URL('/web/'+tour.stops[0].page,origin);
      start.searchParams.set('tour',tour.id);
      await page.goto(start.href);
      for (let i=0;i<tour.stops.length;i++) {
        await page.locator('.sh-tour-head').waitFor();
        const actual = new URL(page.url()), expected = new URL('/web/'+tour.stops[i].page,origin);
        assert.equal(actual.pathname,expected.pathname);
        assert.equal(actual.hash,expected.hash);
        assert.equal(actual.searchParams.get('track'),tour.track);
        assert.equal(actual.searchParams.get('persona'),tour.persona);
        assert.equal(await page.locator('.sh-tour-head').innerText(),tour.stops[i].headline);
        if (i<tour.stops.length-1) {
          const target = new URL(await page.locator('.sh-next').getAttribute('href'));
          assert.equal(target.origin,origin);
          assert.equal(target.searchParams.get('tour'),tour.id);
          await page.locator('.sh-next').click();
        } else {
          assert.equal(await page.locator('.sh-tour-go').getAttribute('aria-disabled'),'true');
          await page.locator('.sh-tour-exit').click();
          assert.equal(await page.locator('.sh-tour').count(),0);
          assert.equal(new URL(page.url()).searchParams.has('tour'),false);
        }
        checks++;
      }
    }
    console.log(`PASS: ${tours.length} tours, ${checks} stops; role, product, hash, same-origin transitions and exit.`);
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
