// Run: node tests/extraction-gallery.cjs. Serves local files in memory; no backend.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/Users/red/.agents/skills/gstack/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const origin = 'https://gallery.test';
const output = path.join(root, 'docs/evidence/extraction-gallery');
const mime = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
  '.svg': 'image/svg+xml', '.ttf': 'font/ttf', '.woff2': 'font/woff2' };
let checks = 0;
const check = (value, message) => { assert(value, message); checks++; };

async function setup(browser, width) {
  const context = await browser.newContext({ viewport: { width, height: 1000 }, serviceWorkers: 'block' });
  const page = await context.newPage();
  page.setDefaultTimeout(4000);
  const denied = [], missing = [], errors = [], requests = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.route('**/*', async route => {
    const req = route.request(), url = new URL(req.url());
    requests.push({ url: req.url(), method: req.method() });
    const relative = decodeURIComponent(url.pathname).replace(/^\/+/, '');
    const file = path.resolve(root, relative);
    if (url.origin !== origin || req.method() !== 'GET' || !/^(web|house)\/|^data\/ptc_tdu\.json$/.test(relative)
      || !mime[path.extname(file)] || !file.startsWith(root + path.sep)) {
      denied.push(req.url()); return route.abort('blockedbyclient');
    }
    try {
      assert((await fs.realpath(file)).startsWith(root + path.sep));
      return await route.fulfill({ body: await fs.readFile(file), contentType: mime[path.extname(file)] });
    } catch { missing.push(req.url()); return route.fulfill({ status: 404, body: 'Not found' }); }
  });
  if (context.routeWebSocket) await context.routeWebSocket('**/*', socket => { denied.push(socket.url()); socket.close(); });
  return { context, page, denied, missing, errors, requests };
}

async function stored(page) {
  return page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }));
}
async function shot(page, name) {
  const paired = await page.locator('.eg-body').evaluate(el => {
    const image = el.querySelector('.eg-visual').getBoundingClientRect();
    const text = el.querySelector('.eg-panel').getBoundingClientRect();
    return image.right <= text.left && image.width > 0 && text.width > 0;
  });
  check(paired, 'Image stays beside extracted text at every viewport');
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), 'No horizontal overflow');
  await page.locator('#extraction-gallery').screenshot({ path: path.join(output, name), animations: 'disabled',
    style: '.sh-nav { visibility: hidden !important; }', timeout: 8000 });
}

(async () => {
  const { examples } = JSON.parse(await fs.readFile(path.join(root, 'web/data/photo-examples.json'), 'utf8'));
  assert.equal(examples.length, 5);
  assert.equal(examples[0].id, 'panel-rating');
  assert.equal(examples[0].fields.find(f => f.key === 'main_breaker_amps').value, '200 A');
  await fs.mkdir(output, { recursive: true });
  const rows = [];
  const timer = setTimeout(() => { console.error('Gallery suite exceeded 90 seconds'); process.exit(2); }, 90000);
  let browser;
  try {
    browser = await chromium.launch({ headless: true, timeout: 15000 });
    for (const width of [320, 390, 1440]) {
      const h = await setup(browser, width), { page } = h;
      const row = { width };
      try {
        await page.goto(origin + '/web/onboarding.html?track=home&persona=lead', { waitUntil: 'load', timeout: 15000 });
        // The gallery sits behind the step 3 "See a sample photo reading" disclosure.
        await page.locator('#sample-reading > summary').click();
        await page.waitForSelector('.eg-thumbnail');
        await page.waitForFunction(() => !document.getElementById('address-select').disabled);
        await page.evaluate(() => document.fonts.ready);
        const gallery = page.locator('#extraction-gallery');
        const thumbs = gallery.locator('.eg-thumbnail');
        const count = page.locator('#photo-checklist .pc-count');
        const photoCount = await count.innerText();
        const initialStorage = await stored(page);
        const confirm = gallery.getByRole('button', { name: 'Confirm', exact: true });
        const correct = gallery.getByRole('button', { name: 'Correct', exact: true });
        const reset = gallery.getByRole('button', { name: 'Reset sample', exact: true });
        const status = gallery.locator('.eg-status');
        check(await thumbs.count() === examples.length, 'Every example has a real thumbnail');
        check(/Sample extraction.*Unverified sample/.test(await gallery.locator('.eg-context').innerText()), 'Saved, unverified result disclosure');
        check(/not in your home record/.test(await gallery.locator('.eg-context').innerText()), 'Sample/home privacy boundary');
        for (let i = 0; i < examples.length; i++) {
          const sample = examples[i];
          await thumbs.nth(i).click();
          await gallery.locator('.eg-image').evaluate(img => img.decode());
          const thumb = thumbs.nth(i).locator('img');
          await thumb.evaluate(img => img.decode());
          check(await thumb.evaluate(img => img.complete && img.naturalWidth > 0), 'Thumbnail asset renders: ' + sample.id);
          check(await gallery.locator('.eg-image').getAttribute('src') === new URL(sample.image, origin + '/web/').href, 'Correct full image: ' + sample.id);
          check(await thumbs.nth(i).getAttribute('aria-pressed') === 'true', 'Selection state exposed');
          for (let f = 0; f < sample.fields.length; f++) {
            const input = gallery.locator('#eg-field-' + f), field = sample.fields[f];
            check(await input.inputValue() === (field.value == null ? '' : String(field.value)), 'Saved field matches data: ' + field.key);
            if (field.value == null) check(await input.getAttribute('placeholder') === 'Not read', 'Null remains Not read');
          }
          check(await count.innerText() === photoCount, 'Selecting sample does not capture a real photo');
          await shot(page, `${sample.id}-${width}.png`);
        }
        await gallery.getByRole('button', { name: 'Use my photo', exact: true }).click();
        check(await page.evaluate(() => document.activeElement?.id === 'pk-file'), 'Use my photo moves to the photo upload');
        check(await page.locator('#photo-check').isVisible(), 'Photo upload is visible');
        check(await count.innerText() === photoCount, 'Use my photo does not apply or capture the sample');
        await thumbs.nth(0).click();
        await confirm.focus(); await page.keyboard.press('Enter');
        check(await status.innerText() === 'Confirmed by you', 'Keyboard Confirm updates sample status');
        await thumbs.nth(1).click();
        check(await status.innerText() === 'To review', 'Other example review remains independent');
        const edited = gallery.locator('#eg-field-1');
        await edited.fill('TEST CORRECTION');
        check(await confirm.isDisabled(), 'Dirty values cannot be confirmed without correction');
        check(await correct.isEnabled(), 'Correction action enabled for edits');
        await correct.click();
        check(await status.innerText() === 'Corrected by you', 'Correct commits local sample edits');
        await thumbs.nth(0).click();
        check(await status.innerText() === 'Confirmed by you', 'First example keeps independent confirmation');
        await thumbs.nth(1).click();
        check(await edited.inputValue() === 'TEST CORRECTION', 'Correction survives sample switches');
        check(await status.innerText() === 'Corrected by you', 'Review status survives sample switches');
        await shot(page, `corrected-${width}.png`);
        await reset.click();
        check(await edited.inputValue() === '', 'Reset sample restores original null');
        check(await status.innerText() === 'To review', 'Reset sample clears its review');
        await thumbs.nth(0).click();
        check(await status.innerText() === 'Confirmed by you', 'Reset sample leaves other review unchanged');
        check(await count.innerText() === photoCount, 'Confirm/correct/reset never increment real photo count');
        assert.deepEqual(await stored(page), initialStorage); checks++;

        // The real journey controls must clear every sample, not just the selected one.
        await thumbs.nth(1).click(); await confirm.click();
        const selected = await page.locator('#address-select').inputValue();
        const other = await page.locator('#address-select option').evaluateAll((options, selected) => options.find(o => o.value !== selected)?.value, selected);
        assert(other, 'Second cohort home required');
        await page.locator('#address-change').click();
        await page.locator('#address-input').fill(other);
        await page.locator('#address-list li').first().waitFor();
        await page.locator('#address-input').press('Enter');
        for (let i = 0; i < examples.length; i++) {
          await thumbs.nth(i).click();
          check(await status.innerText() === 'To review', 'Home switch clears review for sample ' + i);
        }
        await thumbs.nth(0).click(); await confirm.click();
        await thumbs.nth(1).click(); await edited.fill('RESET ME'); await correct.click();
        await page.locator('#reset-progress').click();
        for (let i = 0; i < examples.length; i++) {
          await thumbs.nth(i).click();
          check(await status.innerText() === 'To review', 'Home reset clears review for sample ' + i);
          check(await gallery.locator('#eg-field-1').inputValue() === '', 'Home reset restores original fields');
        }
        await thumbs.nth(0).click(); await confirm.click();
        const beforeReload = await stored(page);
        await page.reload({ waitUntil: 'load', timeout: 15000 });
        // The gallery sits behind the step 3 "See a sample photo reading" disclosure.
        await page.locator('#sample-reading > summary').click();
        await page.waitForSelector('.eg-thumbnail');
        check(await status.innerText() === 'To review', 'Review is memory-only and clears on reload');
        assert.deepEqual(await stored(page), beforeReload); checks++;
        check(await count.innerText() === photoCount, 'Sample activity leaves real checklist empty');
        assert.deepEqual(h.denied, []); assert.deepEqual(h.missing, []); assert.deepEqual(h.errors, []); checks += 3;
        row.passed = true;
      } catch (error) { row.passed = false; row.error = error.stack; process.exitCode = 1; }
      finally { await h.context.close(); }
      Object.assign(row, { requests: h.requests, denied: h.denied, missing: h.missing, errors: h.errors });
      rows.push(row);
      await fs.writeFile(path.join(output, 'report.json'), JSON.stringify({ checks, rows }, null, 2));
      console.log(JSON.stringify({ width, passed: row.passed, error: row.error, checks }));
    }
    console.log(`${rows.filter(r => r.passed).length}/3 cases passed; ${checks} assertions. Evidence: ${output}`);
  } finally { try { if (browser) await browser.close(); } finally { clearTimeout(timer); } }
})().catch(error => { console.error(error); process.exitCode = 1; });
