const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/Users/red/.agents/skills/gstack/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const shots = fs.mkdtempSync(path.join(os.tmpdir(), 'member-stitch-'));
let checks = 0;
const check = (ok, message) => { assert.ok(ok, message); checks++; };
(async () => {
  const browser = await chromium.launch();
  try {
    for (const width of [320, 390, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 900 } });
      const page = await context.newPage();
      const errors = [], localRequests = [];
      page.on('pageerror', error => errors.push(error.message));
      await context.route('**/*', route => {
        const url = new URL(route.request().url());
        if (/localhost|127\.0\.0\.1/.test(url.hostname)) localRequests.push(url.href);
        if (url.origin !== 'http://member.test') return route.abort();
        const file = path.resolve(root, '.' + url.pathname);
        if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return route.fulfill({ status: 404, body: '' });
        const contentType = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.ttf': 'font/ttf' }[path.extname(file)] || 'text/plain';
        return route.fulfill({ contentType, body: fs.readFileSync(file) });
      });
      await page.goto('http://member.test/web/member.html?track=home&persona=lead');
      await page.waitForSelector('#ans .big');
      await page.evaluate(() => document.fonts.ready);
      const raw = JSON.parse(fs.readFileSync(path.join(root, 'data/members.json')));
      const members = Array.isArray(raw) ? raw : raw.members;
      const member = members.find(m => m.member_id === 'm001');
      check((await page.locator('#ans .big').innerText()).startsWith('$' + member.totals.battery_usd.toFixed(2)), 'Battery total retained');
      check(/not an issued payment/.test(await page.locator('#ans').innerText()), 'Payment boundary retained');
      check(!/confirm|Base can plan/.test(await page.locator('#ans').innerText()), 'No prospect prompt');
      check(await page.locator('.days').isHidden(), 'Daily activity initially collapsed');
      check(await page.locator('#local-questions').isHidden(), 'Hosted local form absent');
      check(await page.locator('.help-links a').count() === 2, 'Search and support available');
      check(await page.locator('.help-links a').last().getAttribute('href') === 'brain.html?track=home&persona=lead&q=how%20do%20I%20talk%20to%20Base', 'Support uses existing search');
      check(await page.locator('#setup-banner h1').evaluate(el => el.getBoundingClientRect().top < innerHeight), 'Setup status in first viewport');
      check(await page.locator('[data-milestones]:visible').count() === 1, 'One shared tracker');
      check(await page.locator('#setup-banner a[href="status.html"]').count() === 1, 'Banner links to application status');
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'No initial overflow');
      await page.screenshot({ path: path.join(shots, `member-${width}.png`), fullPage: true });
      await page.locator('.daily-detail summary').click();
      check(await page.locator('.day').count() === member.week.length, 'All daily data retained');
      check(await page.locator('.days').isVisible(), 'Daily disclosure works');
      await page.locator('#chips button').first().click();
      await page.waitForSelector('#answers .answer');
      check(/stored answer/.test(await page.locator('#answers').innerText()), 'Recorded answer works');
      await page.locator('#detail > summary').click();
      const second = members.find(m => m.member_id !== 'm001');
      await page.locator('#member').selectOption(second.member_id);
      check((await page.locator('#ans .big').innerText()).startsWith('$' + second.totals.battery_usd.toFixed(2)), 'Member change updates totals');
      check(await page.locator('#answers .answer').count() === 0, 'Member change clears answers');
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Expanded source record fits');
      check(localRequests.length === 0, 'No hosted local-model requests');
      check(errors.length === 0, 'No runtime errors: ' + errors.join('; '));
      await context.close();
    }
    console.log(`PASS ${checks} member checks. Screenshots: ${shots}`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
