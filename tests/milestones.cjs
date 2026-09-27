// One milestone tracker and one rewards model on every customer page (web/milestones.js, ADR 0015).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/Users/red/.agents/skills/gstack/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const LABELS = ['Public records', 'Your details', 'Photo', 'Engineering review', 'Installation'];
const ADDRESS = '4601 CLAWSON RD';
// Seed: one field confirmed (10), one left open, photo taken (20), all tasks done (30) = 60 kWh.
const SEED = { version: 2, saved: { ac_age_years: 10, has_generator: null }, open: 2, photo: true };
const EXPECTED = 60;
const q = 'track=home&persona=lead&address=' + encodeURIComponent(ADDRESS);
const PAGES = ['onboarding.html?' + q + '#home', 'voice.html?' + q, 'member.html?' + q, 'data-qa.html?' + q];
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.ttf': 'font/ttf', '.woff2': 'font/woff2', '.jsonl': 'text/plain' };
let checks = 0;
const check = (ok, msg) => { assert.ok(ok, msg); checks++; };
(async () => {
  const browser = await chromium.launch();
  try {
    for (const width of [390, 1440]) {
      for (const route of PAGES) {
        const context = await browser.newContext({ viewport: { width, height: 900 } });
        await context.addInitScript(([addr, seed]) => {
          if (sessionStorage.getItem('seeded')) return;
          localStorage.setItem('base-fleet:journey:v1:' + addr, JSON.stringify(seed));
          localStorage.setItem('base-fleet:home:v1', JSON.stringify({ address: addr }));
          sessionStorage.setItem('seeded', '1');
        }, [ADDRESS, SEED]);
        await context.route('**/*', r => {
          const url = new URL(r.request().url());
          if (url.origin !== 'http://ms.test') return r.abort();
          const file = path.resolve(root, '.' + decodeURIComponent(url.pathname));
          if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return r.fulfill({ status: 404, body: '' });
          return r.fulfill({ contentType: TYPES[path.extname(file)] || 'text/plain', body: fs.readFileSync(file) });
        });
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', e => errors.push(e.message));
        await page.goto('http://ms.test/web/' + route);
        await page.waitForSelector('[data-milestones] .bf-ms-steps li');
        const trackers = page.locator('[data-milestones]:visible');
        check(await trackers.count() === 1, `${route} @${width}: one visible tracker`);
        const labels = await trackers.first().locator('.bf-ms-label').allInnerTexts();
        check(JSON.stringify(labels) === JSON.stringify(LABELS), `${route}: five labels in order, got ${labels}`);
        const credit = Number(await trackers.first().locator('.bf-ms-credit').getAttribute('data-credit'));
        check(credit === EXPECTED, `${route}: credit ${credit} kWh, expected ${EXPECTED}`);
        check(/Base Ready points \(proposal\)/i.test(await trackers.first().innerText()), `${route}: points labelled as a proposal`);
        check(/^Next: /.test(await trackers.first().locator('.bf-ms-next').innerText()), `${route}: next reward line`);
        check(!(await page.locator('#bf-ms-toast.bf-ms-toast-on').count()), `${route}: no toast on page load`);
        const text = await page.locator('body').innerText();
        check(!/\b(badges?|streaks?|leaderboard)\b/i.test(text), `${route}: no badges or streaks`);
        check(!/\+\d+ kWh\b/.test(text), `${route}: rewards in points, not kWh`);
        const other = (text.match(/\b\d+ ?(kWh credit|pts earned)\b/gi) || []).length;
        check(other === 0, `${route}: no second points total on load`);
        const chip = page.locator('.sh-points');
        check(await chip.count() === 1 && /^60 pts$/.test((await chip.innerText()).trim()), `${route}: nav points chip`);
        check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${route} @${width}: no overflow`);
        check(errors.length === 0, `${route}: no runtime errors ${errors.join('; ')}`);
        await context.close();
      }
    }
    // Earn moment: answering the open question raises points, so a toast appears and the total pulses.
    {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      await context.addInitScript(([addr, seed]) => {
        if (sessionStorage.getItem('seeded')) return;
        localStorage.setItem('base-fleet:journey:v1:' + addr, JSON.stringify(seed));
        localStorage.setItem('base-fleet:home:v1', JSON.stringify({ address: addr }));
        sessionStorage.setItem('seeded', '1');
      }, [ADDRESS, { version: 2, saved: { ac_age_years: 10 }, open: 2, photo: true }]);
      await context.route('**/*', r => {
        const url = new URL(r.request().url());
        if (url.origin !== 'http://ms.test') return r.abort();
        const file = path.resolve(root, '.' + decodeURIComponent(url.pathname));
        if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return r.fulfill({ status: 404, body: '' });
        return r.fulfill({ contentType: TYPES[path.extname(file)] || 'text/plain', body: fs.readFileSync(file) });
      });
      const page = await context.newPage();
      await page.goto('http://ms.test/web/' + PAGES[0]);
      await page.waitForSelector('#questions .q-btn');
      check(!(await page.locator('#bf-ms-toast.bf-ms-toast-on').count()), 'no toast before an answer');
      check(/^Next: answer 1 more question/.test(await page.locator('[data-milestones] .bf-ms-next').innerText()), 'next line names the open question');
      await page.locator('#questions .q-btn').first().click();
      await page.locator('#continue-question').click();
      const toast = page.locator('#bf-ms-toast.bf-ms-toast-on');
      await toast.waitFor({ timeout: 2000 });
      const t = await toast.innerText();
      check(/^\+\d+ pts · \d+ pts earned$/.test(t.trim()), `toast text, got ${t}`);
      check(await page.locator('#bf-ms-toast[aria-live="polite"]').count() === 1, 'toast is polite live region');
      check(await page.locator('.bf-ms-credit.bf-ms-pulse').count() >= 1, 'credit number pulses');
      await page.waitForTimeout(300);
      if (process.env.SHOT) await page.screenshot({ path: process.env.SHOT, clip: { x: 0, y: 0, width: 1440, height: 900 } });
      await toast.waitFor({ state: 'detached', timeout: 10 }).catch(() => {});
      await page.waitForFunction(() => !document.querySelector('#bf-ms-toast.bf-ms-toast-on'), null, { timeout: 4000 });
      check(true, 'toast hides after 3 s');
      await context.close();
    }
    console.log(`PASS ${checks} milestone checks on ${PAGES.length} customer pages`);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
