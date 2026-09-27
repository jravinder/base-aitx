const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/Users/red/.agents/skills/gstack/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const shots = fs.mkdtempSync(path.join(os.tmpdir(), 'voice-clarity-'));
let checks = 0;
const check = (ok, message) => { assert.ok(ok, message); checks++; };
(async () => {
  const browser = await chromium.launch();
  try {
    for (const width of [320, 390, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      const page = await context.newPage();
      const errors = [], localRequests = [];
      page.on('pageerror', e => errors.push(e.message));
      await context.route('**/*', route => {
        const url = new URL(route.request().url());
        if (/localhost|127\.0\.0\.1/.test(url.hostname)) localRequests.push(url.href);
        if (url.origin !== 'http://voice.test') return route.abort();
        const file = path.resolve(root, '.' + url.pathname);
        if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return route.fulfill({ status: 404, body: '' });
        const contentType = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.ttf': 'font/ttf' }[path.extname(file)] || 'text/plain';
        return route.fulfill({ contentType, body: fs.readFileSync(file) });
      });
      await page.goto('http://voice.test/web/voice.html?track=home&persona=lead');
      await page.waitForSelector('#vg-guided .vg-big');
      await page.evaluate(() => document.fonts.ready);
      const layout = async state => {
        check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), state + ' fits');
        check(await page.locator('main button:visible, main select:visible, main summary:visible, main .vg-big:visible').evaluateAll(els => els.every(el => el.getBoundingClientRect().height >= 44)), state + ' touch targets');
        check(await page.locator('.vg-help:visible, .vg-note:visible, .vg-cg p:visible, .vg-steps:visible').evaluateAll(els => els.every(el => parseFloat(getComputedStyle(el).fontSize) >= 18)), state + ' readable text');
        await page.screenshot({ path: path.join(shots, `${state}-${width}.png`), fullPage: true });
      };
      check(await page.locator('#vg-caption').isHidden(), 'Duplicate transcript collapsed');
      await layout('intro');
      await page.locator('.vg-caption summary').click();
      check(await page.locator('#vg-caption').isVisible(), 'Transcript accessible');
      await page.locator('#vg-guided .vg-big').first().click();
      check(await page.locator('#vg-guided .vg-answers button').count() === 3, 'Question choices retained');
      await layout('question');
      await page.locator('.vg-options summary').click();
      await page.locator('#vg-caregiver').click();
      check(await page.locator('#vg-caregiver-view').isVisible(), 'Caregiver view retained');
      check(/Keep all doors and covers closed/.test(await page.locator('#vg-caregiver-view').innerText()), 'Photo safety retained');
      await layout('caregiver');
      await page.locator('#vg-caregiver').click();
      check(await page.locator('#vg-guided').isVisible(), 'Return to guide');
      check(/No application, human review, or callback/.test(await page.locator('.vg-foot').textContent()), 'Privacy boundary retained');
      check(localRequests.length === 0, 'No local backend requests');
      check(errors.length === 0, 'No runtime errors');
      await context.close();
    }
    console.log(`PASS ${checks} checks. Screenshots: ${shots}`);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
