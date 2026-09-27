/* Standalone browser regression. No server or model required.
 * Run: node tests/photo-checklist.cjs
 * Optional WIDTHS=320,390,1440 OUTPUT_DIR=docs/evidence/photo-checklist
 */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
let chromium;
try { ({ chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')); }
catch { ({ chromium } = require('/Users/red/.agents/skills/gstack/node_modules/playwright')); }
const root = path.resolve(__dirname, '..');
const origin = 'https://photos.test';
const output = path.resolve(root, process.env.OUTPUT_DIR || 'docs/evidence/photo-checklist');
const widths = (process.env.WIDTHS || '320,390,1440').split(',').map(Number);
assert(widths.every(w => [320, 390, 1440].includes(w)), 'WIDTHS must select 320,390,1440');
const types = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.ttf': 'font/ttf', '.woff2': 'font/woff2' };
const fixture = `<!doctype html><html lang="en" data-theme="light"><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/web/shell.css"><link rel="stylesheet" href="/web/photo-checklist.css">
<script defer src="/web/photo-checklist.js"></script></head><body>
<main><section id="photo-checklist"></section></main></body></html>`;

async function setup(browser, width, isolated) {
  const context = await browser.newContext({ viewport: { width, height: 1000 }, serviceWorkers: 'block' });
  const page = await context.newPage();
  page.setDefaultTimeout(4000);
  const requests = [], denied = [], errors = [], missing = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.addInitScript(() => {
    window.photoTestUrls = { created: [], revoked: [] };
    const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
    URL.createObjectURL = value => { const url = create(value); window.photoTestUrls.created.push(url); return url; };
    URL.revokeObjectURL = url => { window.photoTestUrls.revoked.push(url); return revoke(url); };
  });
  await context.route('**/*', async route => {
    const req = route.request(), url = new URL(req.url());
    requests.push({ url: req.url(), method: req.method() });
    if (req.method() !== 'GET' || url.origin !== origin) {
      denied.push(requests.at(-1)); return route.abort('blockedbyclient');
    }
    if (url.pathname === '/fixture.html') return route.fulfill({ contentType: 'text/html', body: fixture });
    const relative = decodeURIComponent(url.pathname).replace(/^\/+/, '');
    const file = path.resolve(root, relative);
    if (!/^(web|house)\/|^data\/ptc_tdu\.json$/.test(relative) || !types[path.extname(file)] || !file.startsWith(root + path.sep)) {
      denied.push(requests.at(-1)); return route.abort('blockedbyclient');
    }
    try {
      assert((await fs.realpath(file)).startsWith(root + path.sep));
      return await route.fulfill({ body: await fs.readFile(file), contentType: types[path.extname(file)] });
    } catch { missing.push(url.pathname); return route.fulfill({ status: 404, body: 'Not found' }); }
  });
  if (context.routeWebSocket) await context.routeWebSocket('**/*', socket => { denied.push({ url: socket.url(), method: 'WEBSOCKET' }); socket.close(); });
  await page.goto(origin + (isolated ? '/fixture.html' : '/web/onboarding.html?track=home&persona=lead'),
    { waitUntil: 'load', timeout: 15000 });
  await page.waitForSelector('#photo-checklist input[type=file]', { state: 'attached' });
  await page.evaluate(() => document.fonts.ready);
  return { context, page, requests, denied, errors, missing };
}

async function imageFile(page, mimeType, name, color) {
  const encoded = await page.evaluate(({ mimeType, color }) => {
    const canvas = document.createElement('canvas'); canvas.width = 40; canvas.height = 30;
    const ctx = canvas.getContext('2d'); ctx.fillStyle = color; ctx.fillRect(0, 0, 40, 30);
    return canvas.toDataURL(mimeType).split(',')[1];
  }, { mimeType, color });
  return { name, mimeType, buffer: Buffer.from(encoded, 'base64') };
}

async function dispatch(page, event, address) {
  await page.evaluate(({ event, address }) => {
    document.dispatchEvent(new CustomEvent(event, { detail: { address } }));
  }, { event, address });
}

async function noOverflow(page) {
  const layout = await page.evaluate(() => ({ width: innerWidth, document: document.documentElement.scrollWidth,
    overflowing: [...document.querySelectorAll('#photo-checklist *')].filter(el => {
      if (!el.getClientRects().length || getComputedStyle(el).position === 'absolute') return false;
      const r = el.getBoundingClientRect(); return r.right > innerWidth + 2 || r.left < -2;
    }).map(el => el.id || el.className || el.tagName) }));
  assert(layout.document <= layout.width + 2, JSON.stringify(layout));
  assert.deepEqual(layout.overflowing, [], JSON.stringify(layout));
}

async function storage(page) {
  return page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }));
}

const groups = { Outside: ['meter', 'surroundings', 'left', 'right', 'wall', 'fence'],
  Electrical: ['breaker', 'disconnect', 'panel-area'] };
const results = [];
let checks = 0;
function check(value, message) { assert(value, message); checks++; }
async function choose(page, group, id) {
  await page.locator('.pc-groups').getByRole('button', { name: group, exact: true }).click();
  await page.locator('#pc-item').selectOption(id);
}
async function settlePhoto(page) {
  await page.waitForFunction(() => document.querySelector('.pc-controls').getAttribute('aria-busy') === 'false');
}
async function previewURL(page) { return page.locator('.pc-preview img').getAttribute('src'); }
async function put(page, file) {
  await page.locator('#pc-file').setInputFiles(file);
  await settlePhoto(page);
  check(await page.locator('.pc-preview').isVisible(), 'Selected image preview visible');
  check(await page.locator('.pc-preview img').evaluate(img => img.complete && img.naturalWidth > 0), 'Preview decodes');
  check((await previewURL(page)).startsWith('blob:'), 'Preview uses an in-memory blob URL');
  check(await page.locator('#pc-review').inputValue() === 'Captured', 'New photo starts Captured');
}
async function revoked(page, url) {
  check(await page.evaluate(url => window.photoTestUrls.revoked.includes(url), url), 'Old preview URL revoked');
}
async function screenshot(page, name) {
  await noOverflow(page);
  await page.screenshot({ path: path.join(output, name), fullPage: true, animations: 'disabled', timeout: 8000 });
}

async function componentCase(browser, width) {
  const h = await setup(browser, width, true);
  const { page } = h;
  try {
    const summary = page.locator('.pc-summary');
    await summary.focus(); await page.keyboard.press('Enter');
    check(await page.locator('.pc-details').evaluate(el => el.open), 'Keyboard opens checklist');
    check(await page.locator('#pc-file').isDisabled(), 'Capture disabled before a home is supplied');
    check(await page.locator('#pc-item').isDisabled(), 'Item selector initially disabled');
    await screenshot(page, `disabled-${width}.png`);
    await dispatch(page, 'home-context-changed', '706 HUNTINGDON PL');
    check(await page.locator('#pc-file').isEnabled(), 'Capture enabled by home context');
    check(/706 HUNTINGDON PL/.test(await page.locator('.pc-context').innerText()), 'Active address displayed');
    check(await page.locator('.pc-groups button').count() === 2, 'Exactly two groups');
    for (const [group, ids] of Object.entries(groups)) {
      await page.locator('.pc-groups').getByRole('button', { name: group, exact: true }).click();
      assert.deepEqual(await page.locator('#pc-item option').evaluateAll(nodes => nodes.map(n => n.value)), ids);
      checks++;
    }
    check(Object.values(groups).flat().length === 9, 'Nine photo items');
    const png = await imageFile(page, 'image/png', 'meter.png', '#15803d');
    const jpeg = await imageFile(page, 'image/jpeg', 'replacement-' + 'long-name-'.repeat(12) + '.jpg', '#2563eb');
    const initialStorage = await storage(page);
    await choose(page, 'Outside', 'meter');
    check(await page.locator('.pc-na').isHidden(), 'Not applicable hidden for required items');
    const baseline = h.requests.length;
    await put(page, png);
    check(h.requests.length === baseline, 'PNG preview triggers no network request');
    check(/\b1 photo\b/.test(await page.locator('.pc-count').innerText()), 'Photo count updates');
    check(/nothing has been submitted/i.test(await page.locator('.pc-message').innerText()), 'Honest local-only status');
    const first = await previewURL(page);
    await page.locator('#pc-review').selectOption('Needs another photo');
    check((await page.locator('#pc-item option:checked').textContent()).includes('Needs another photo'), 'Item status reflects user selection');
    check(/set by you.*No review has been requested/.test(await page.locator('.pc-message').innerText()), 'Status does not imply human review');

    // Native file chooser activation must work from the keyboard, not only setInputFiles.
    await page.locator('#pc-file').focus();
    const chooser = page.waitForEvent('filechooser');
    await page.keyboard.press('Enter');
    await (await chooser).setFiles(jpeg);
    await settlePhoto(page);
    check(await page.locator('.pc-preview figcaption').innerText() === jpeg.name, 'JPEG replaces PNG');
    check(await previewURL(page) !== first, 'Replacement uses a new blob');
    await revoked(page, first);
    check(await page.locator('#pc-review').inputValue() === 'Captured', 'Replacement resets self-review status');
    await screenshot(page, `jpeg-preview-${width}.png`);
    const second = await previewURL(page);
    await page.locator('#pc-file').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('not an image') });
    await settlePhoto(page);
    check(/Choose an image/.test(await page.locator('.pc-message').innerText()), 'Invalid MIME reports an error');
    check(await previewURL(page) === second, 'Invalid MIME preserves existing photo');
    await page.locator('#pc-file').setInputFiles({ name: 'broken.png', mimeType: 'image/png', buffer: Buffer.from('not a PNG') });
    await settlePhoto(page);
    check(/could not be opened/.test(await page.locator('.pc-message').innerText()), 'Corrupt image reports decode error');
    check(await previewURL(page) === second, 'Corrupt image preserves existing photo');
    await screenshot(page, `invalid-file-${width}.png`);
    const remove = page.getByRole('button', { name: 'Remove photo', exact: true });
    await remove.focus(); await page.keyboard.press('Enter');
    check(await page.locator('.pc-preview').isHidden(), 'Keyboard remove hides preview');
    check(/0 photos/.test(await page.locator('.pc-count').innerText()), 'Remove updates count');
    await revoked(page, second);

    await choose(page, 'Outside', 'fence');
    check(/optional/i.test(await page.locator('#pc-item option:checked').innerText()), 'Fence explicitly optional');
    const na = page.locator('.pc-na input');
    await na.focus(); await page.keyboard.press('Space');
    check(await na.isChecked(), 'Keyboard toggles Not applicable');
    check(await page.locator('#pc-file').isDisabled(), 'Fence capture disabled while not applicable');
    check(/fence not applicable/.test(await page.locator('.pc-count').innerText()), 'Optional state appears in count');
    await screenshot(page, `optional-fence-${width}.png`);
    await na.uncheck(); await put(page, png);
    const fence = await previewURL(page);
    await na.check();
    check(await page.locator('.pc-preview').isHidden(), 'Not applicable removes existing fence photo');
    await revoked(page, fence);
    await na.uncheck();

    for (const [group, ids] of Object.entries(groups)) {
      for (const id of ids) { await choose(page, group, id); await put(page, png); }
    }
    check(/9 photos/.test(await page.locator('.pc-count').innerText()), 'All nine captures counted independently');
    await screenshot(page, `nine-photos-${width}.png`);
    assert.deepEqual(await storage(page), initialStorage); checks++;
    await dispatch(page, 'home-context-changed', 'DIFFERENT SAMPLE HOME');
    check(/0 photos/.test(await page.locator('.pc-count').innerText()), 'Address switch clears all photos');
    check(await page.locator('.pc-preview').isHidden(), 'Address switch clears preview');
    check(await page.locator('#pc-item').inputValue() === 'meter', 'Address switch resets active item');
    check(await page.evaluate(() => window.photoTestUrls.created.every(u => window.photoTestUrls.revoked.includes(u))), 'Address switch revokes all blobs');
    await put(page, jpeg);
    await dispatch(page, 'home-photos-reset');
    check(/0 photos/.test(await page.locator('.pc-count').innerText()), 'Reset clears photos');
    check(await page.locator('.pc-preview').isHidden(), 'Reset clears preview');
    check(await page.locator('#pc-file').isEnabled(), 'Reset retains active home');
    check(await page.evaluate(() => window.photoTestUrls.created.every(u => window.photoTestUrls.revoked.includes(u))), 'Reset revokes all blobs');
    await screenshot(page, `reset-${width}.png`);
    assert.deepEqual(await storage(page), initialStorage); checks++;
    assert.deepEqual(h.denied, []); assert.deepEqual(h.errors, []); assert.deepEqual(h.missing, []); checks += 3;
    return { requests: h.requests, checks };
  } finally { await h.context.close(); }
}

async function integrationCase(browser, width) {
  const h = await setup(browser, width, false);
  const { page } = h;
  try {
    await page.waitForFunction(() => !document.getElementById('address-select').disabled);
    await page.locator('.pc-summary').click();
    check(await page.locator('#pc-file').isEnabled(), 'Journey initial home activates capture');
    const png = await imageFile(page, 'image/png', 'journey.png', '#15803d');
    await put(page, png);
    const original = await page.locator('#address-select').inputValue();
    const other = await page.locator('#address-select option').evaluateAll((nodes, original) => nodes.find(n => n.value !== original)?.value, original);
    assert(other, 'Need a second actual cohort address');
    await page.locator('#address-change').click();
    await page.locator('#address-input').fill(other);
    await page.locator('#address-list li').first().waitFor();
    await page.locator('#address-input').press('Enter');
    check((await page.locator('.pc-context').innerText()).includes(other), 'Actual home selector updates component');
    check(/0 photos/.test(await page.locator('.pc-count').innerText()), 'Actual home switch clears captures');
    check(await page.locator('.pc-preview').isHidden(), 'No previous-home preview remains');
    await put(page, png);
    await page.locator('#reset-progress').click();
    check(/0 photos/.test(await page.locator('.pc-count').innerText()), 'Actual Start over clears captures');
    check(await page.locator('.pc-preview').isHidden(), 'Actual Start over removes preview');
    await page.locator('.pc-summary').click();
    await page.evaluate(() => document.dispatchEvent(new CustomEvent('home-photos-open', { detail: { group: 'electrical' } })));
    check(await page.locator('.pc-details').evaluate(el => el.open), 'Electrical helper event opens checklist');
    check(await page.locator('.pc-groups').getByRole('button', { name: 'Electrical', exact: true }).getAttribute('aria-pressed') === 'true', 'Electrical helper selects Electrical');
    await screenshot(page, `journey-electrical-${width}.png`);
    assert.deepEqual(h.denied, []); assert.deepEqual(h.errors, []); assert.deepEqual(h.missing, []); checks += 3;
    return { requests: h.requests, checks };
  } finally { await h.context.close(); }
}

(async () => {
  for (const file of ['web/photo-checklist.js', 'web/photo-checklist.css']) await fs.access(path.join(root, file));
  await fs.mkdir(output, { recursive: true });
  const watchdog = setTimeout(() => { console.error('Photo checklist suite exceeded 120 seconds'); process.exit(2); }, 120000);
  let browser;
  try {
    browser = await chromium.launch({ headless: true, timeout: 15000 });
    for (const width of widths) {
      for (const [name, run] of [['component', componentCase], ['journey', integrationCase]]) {
        const row = { name, width };
        try { Object.assign(row, await run(browser, width), { passed: true }); }
        catch (error) { row.passed = false; row.error = error.stack; process.exitCode = 1; }
        results.push(row);
        console.log(JSON.stringify({ name, width, passed: row.passed, error: row.error, checks }));
        await fs.writeFile(path.join(output, 'report.json'), JSON.stringify({ checks, results }, null, 2));
      }
    }
    console.log(`${checks} assertions; ${results.filter(r => r.passed).length}/${results.length} cases passed. Evidence: ${output}`);
  } finally {
    try { if (browser) await browser.close(); } finally { clearTimeout(watchdog); }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
