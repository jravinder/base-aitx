const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || '/Users/red/.agents/skills/gstack/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const origin = 'https://home-admin.test';

(async () => {
  const browser = await chromium.launch({headless:true});
  let checks = 0;
  try {
    for (const width of [320,390,1440]) {
      const page = await browser.newPage({viewport:{width,height:1000},colorScheme:'light'});
      page.setDefaultTimeout(15000);
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.route('**/*', async route => {
        const u = new URL(route.request().url());
        if (['cdnjs.cloudflare.com','cdn.tailwindcss.com','fonts.googleapis.com','fonts.gstatic.com'].includes(u.hostname)) return route.continue();
        // Map geometry and controls use real Leaflet; remote basemap tiles are not under test.
        if (u.origin !== origin) return route.abort();
        const file = path.resolve(root, '.' + decodeURIComponent(u.pathname));
        if (!file.startsWith(root + path.sep)) return route.fulfill({status:403,body:''});
        try {
          await route.fulfill({body:await fs.readFile(file),contentType:({'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.geojson':'application/json'})[path.extname(file)] || 'application/octet-stream'});
        } catch { await route.fulfill({status:404,body:''}); }
      });
      for (const name of (process.env.ADMIN_ONLY ? ['admin'] : ['judgments','market','explorer','house','admin'])) {
        // judgments, house and market are Base admin story steps; explorer and admin left the nav and open by direct URL.
        const story = ['judgments','market','house'].includes(name);
        await page.goto(`${origin}/web/${name}.html` + (story ? '?track=home&persona=operations' : ''));
        await page.waitForSelector('.sh-nav',{state:'attached'});
        assert.equal(new URL(page.url()).pathname,`/web/${name}.html`,`${name}: no redirect`);
        if (story) {
          assert.equal(await page.locator('.admin-path').count(),0,`${name}: old workflow tabs removed`);
          assert.equal(await page.locator('.sh-link[aria-current="page"]').getAttribute('data-sh-id'),name);
        } else {
          await page.waitForSelector('.admin-path');
          assert.equal(await page.locator('.admin-path [aria-current="page"]').count(),1);
        }
        if (name === 'admin') {
          await page.waitForSelector('#rules .card');
          assert.equal(await page.locator('#rules details[open]').count(),0);
          assert.equal(await page.locator('#rules .review-next').count(),5);
          for (const link of await page.locator('#rules .review-next').all()) {
            const url = new URL(await link.getAttribute('href'),origin);
            assert.equal(url.searchParams.get('track'),'home');
            assert.equal(url.searchParams.get('persona'),'operations');
          }
          await page.locator('#rules details summary').first().click();
          assert.match(await page.locator('#rules details').first().innerText(),/Source:.*permits/s);
          await page.locator('#rules .review-next').first().click();
          await page.waitForURL(u=>u.pathname==='/web/market.html' && u.searchParams.get('persona')==='operations');
          // Operations is a Base Ready admin page; the compute admin menu no longer lists it.
          assert.equal(await page.locator('#lrnprops button:not(:disabled)').count(),0);
        } else if (name === 'judgments') {
          // Story step 1: the run screen is the first screen, the notebook figures sit under it, one H1.
          const labels = await page.locator('.sh-link .sh-short').allTextContents();
          assert.deepEqual(labels.map(t => t.trim()),['Permits','The lead','Will it fit','Ready to install','Where next','Energy']);
          assert.equal(await page.locator('h1').count(),1);
          assert.match(await page.locator('h1').innerText(),/34,334 Austin permits/);
          await page.waitForSelector('#sq i.p');
          const top = await page.evaluate(() => [document.querySelector('.run').getBoundingClientRect().top, document.querySelector('.pj').getBoundingClientRect().top]);
          assert(top[0] < top[1],'run screen above the notebook');
          await page.waitForSelector('#pj-f1 svg');
          assert.equal(new URL(await page.locator('#story-next').getAttribute('href'),page.url()).pathname,'/web/house.html');
        } else if (name === 'market') {
          await page.waitForSelector('#cards .card');
          // Stitch layout: permit chart open as the hero, four answer cards, closed details.
          assert.equal(await page.locator('#cards .card').count(),4);
          assert.match(await page.locator('#cards').innerText(),/still open/);
          assert.match(await page.locator('#cards').innerText(),/open permit shows the work is still on file/);
          assert.doesNotMatch(await page.locator('#cards').innerText(),/passed inspection/);
          assert(await page.locator('#bars > div').count() >= 12);
          await page.locator('#range').click();
          assert.equal(await page.locator('#range').getAttribute('aria-pressed'),'true');
          assert.equal(await page.locator('#market-trends').evaluate(e => e.open),false);
          await page.locator('#market-trends > summary').click();
          await page.waitForFunction(() => document.querySelector('#annual').width > 0);
          assert(await page.locator('#zips tr').count() > 1);
        } else if (name === 'explorer') {
          await page.waitForSelector('#chips button');
          assert.equal(await page.locator('#chips button').first().innerText(),'Base permits');
          for (const button of await page.locator('#chips button').all()) {
            await button.click();
            assert.equal(await button.getAttribute('aria-pressed'),'true');
            assert((await page.locator('#card').innerText()).length > 30);
          }
          await page.locator('#chips button').first().click();
          await page.locator('#play').click();
          assert.match(await page.locator('#play').innerText(),/Pause/);
          await page.locator('#play').click();
          await page.locator('#slider').focus();
          await page.keyboard.press('Home');
          assert(await page.locator('#map canvas').count() > 0);
          await page.locator('#details > summary').click();
          await page.waitForFunction(() => {
            const canvas = document.querySelector('#chart');
            if (!document.querySelector('#details').open || canvas.height < 180) return false;
            const pixels = canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
            let colored = 0;
            for (let i = 0; i < pixels.length; i += 4) {
              if (pixels[i+3] > 100 && Math.max(pixels[i],pixels[i+1],pixels[i+2]) - Math.min(pixels[i],pixels[i+1],pixels[i+2]) > 25) colored++;
            }
            return colored > 100;
          });
          assert(await page.locator('#chart').evaluate(c => Math.abs(c.width - c.clientWidth * devicePixelRatio) <= 1),'Expanded history chart matches its layout width');
        } else {
          await page.waitForSelector('#panel .gn');
          assert.equal(await page.locator('[data-k="easy"]').getAttribute('aria-pressed'),'true');
          const second = page.locator('#panel .gn').nth(1);
          const address = await second.getAttribute('aria-label');
          await second.click();
          assert.equal(await page.locator('#card h2').innerText(),address);
          await page.locator('[data-k="file"]').click();
          assert(await page.locator('#panel .gn').count() > 1);
          await page.locator('[data-k="teach"]').click();
          // The initial highest-reach home remains available without an invented confirmation.
          await page.reload();
          await page.locator('[data-k="teach"]').click();
          assert.equal(await page.locator('#ask').isChecked(),false);
          await page.locator('#ask').check();
          assert.equal(await page.locator('#ask').isChecked(),true);
          await page.locator('#details > summary').click();
          assert(await page.locator('#guesses tr').count() > 1);
        }
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),`${name}: ${width}px overflow`);
        assert.deepEqual(errors,[],`${name}: runtime errors`);
        if (process.env.SCREENSHOT_DIR) {
          await fs.mkdir(process.env.SCREENSHOT_DIR,{recursive:true});
          await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`${name}-${width}.png`),fullPage:true});
        }
        checks++;
      }
      await page.close();
    }
    console.log(`PASS: ${checks} Home admin page/viewport scenarios. CDN libraries required; basemap tiles excluded.`);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
