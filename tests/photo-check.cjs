/* Photo upload flow in onboarding step 3: in-browser quality check, hosted reading panel, Confirm awards the photo.
 * Run: node tests/photo-check.cjs   (no server or model needed; every request outside the test origin is blocked) */
const fs = require('node:fs/promises');
const path = require('node:path');
let chromium;
try { ({ chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')); }
catch { ({ chromium } = require('/Users/red/.agents/skills/gstack/node_modules/playwright')); }
const root = path.resolve(__dirname, '..');
const origin = 'http://pk.test';
const types = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.ttf': 'font/ttf', '.woff2': 'font/woff2' };
let checks = 0;
function check(ok, msg) { if (!ok) throw new Error('FAIL: ' + msg); checks++; }

// Synthetic photos drawn in the page: a dark flat image and a sharp, well-lit label in the centre.
async function synth(page, kind) {
  const b64 = await page.evaluate(kind => {
    const c = document.createElement('canvas'); c.width = 1200; c.height = 900;
    const x = c.getContext('2d');
    if (kind === 'dark') { x.fillStyle = '#141414'; x.fillRect(0, 0, 1200, 900); x.fillStyle = '#1c1c1c'; x.fillRect(500, 350, 200, 200); }
    else {
      x.fillStyle = '#b8bcc0'; x.fillRect(0, 0, 1200, 900);
      x.fillStyle = '#fff'; x.fillRect(400, 300, 400, 300);
      x.fillStyle = '#111'; x.font = 'bold 44px sans-serif';
      for (let i = 0; i < 5; i++) x.fillText('MAIN 200A  240V', 420, 360 + i * 56);
    }
    return c.toDataURL('image/jpeg', 0.92).split(',')[1];
  }, kind);
  return { name: kind + '.jpg', mimeType: 'image/jpeg', buffer: Buffer.from(b64, 'base64') };
}

(async () => {
  const watchdog = setTimeout(() => { console.error('photo-check suite exceeded 90 s'); process.exit(2); }, 90000);
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [390, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 900 } });
      const page = await context.newPage();
      const denied = [], errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await context.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.origin !== origin) { denied.push(url.href); return route.abort('blockedbyclient'); }
        const file = path.resolve(root, decodeURIComponent(url.pathname).replace(/^\/+/, ''));
        try { return await route.fulfill({ body: await fs.readFile(file), contentType: types[path.extname(file)] || 'application/octet-stream' }); }
        catch { return route.fulfill({ status: 404, body: '' }); }
      });
      await page.goto(origin + '/web/onboarding.html?track=home&persona=lead', { waitUntil: 'load' });
      await page.waitForFunction(() => !document.getElementById('pk-file').disabled);
      check(await page.locator('#pk-file').getAttribute('capture') === 'environment', 'camera capture on the input');

      await page.setInputFiles('#pk-file', await synth(page, 'dark'));
      await page.waitForSelector('.pk-chip[data-check="light"]');
      check(await page.locator('.pk-chip[data-check="light"]').getAttribute('data-pass') === 'false', 'dark photo fails light');
      check(/of 255/.test(await page.locator('.pk-chip[data-check="light"]').innerText()), 'light chip shows measured value');
      check(/Too dark: turn on a light or open the door/.test(await page.locator('.pk-tips').innerText()), 'dark retake tip');
      check(await page.locator('#pk-confirm').isDisabled(), 'Confirm waits for a clear photo');
      const firstSrc = await page.locator('.pk-preview img').getAttribute('src');

      await page.setInputFiles('#pk-file', await synth(page, 'sharp'));
      await page.waitForFunction(() => document.querySelector('.pk-chip[data-check="light"]')?.dataset.pass === 'true');
      for (const id of ['resolution', 'light', 'sharpness', 'framing'])
        check(await page.locator(`.pk-chip[data-check="${id}"]`).getAttribute('data-pass') === 'true', `sharp photo passes ${id}`);
      check(await page.locator('.pk-tip').count() === 0, 'no retake tips for a clear photo');
      check(await page.locator('.pk-preview img').getAttribute('src') !== firstSrc, 'retake replaces the preview');
      check(/^blob:/.test(await page.locator('.pk-preview img').getAttribute('src')), 'photo stays on the device as an object URL');
      check(/Reading runs on the PC beside your battery/.test(await page.locator('#pk-read').innerText()), 'hosted reading panel');

      await page.locator('#pk-sample').click();
      check(await page.locator('#sample-reading').evaluate(d => d.open), 'sample reading opens');

      const key = await page.evaluate(() => Object.keys(localStorage).find(k => k.startsWith('base-fleet:journey:v1:')) || null);
      const before = key ? await page.evaluate(k => JSON.parse(localStorage.getItem(k) || 'null'), key) : null;
      check(!(before && before.photo), 'no photo milestone before Confirm');
      await page.locator('#pk-correct').click();
      await page.locator('#pk-amps').fill('150');
      await page.locator('#pk-confirm').click();
      const after = await page.evaluate(() => {
        const k = Object.keys(localStorage).find(k => k.startsWith('base-fleet:journey:v1:'));
        return k && JSON.parse(localStorage.getItem(k));
      });
      check(after && after.photo === true, 'Confirm marks the photo milestone');
      check(/Main breaker 150 A saved/.test(await page.locator('.pk-msg').innerText()), 'corrected amps confirmed');
      check(await page.locator('#pk-confirm').isDisabled(), 'Confirm is done once');
      check(await page.evaluate(() => window.BasePhotoCheck.safeRetake('Open the panel cover and show the bus bars')) !== 'Open the panel cover and show the bus bars', 'unsafe retake advice replaced');
      await page.locator('#photos').screenshot({ path: path.join(root, `docs/evidence/photo-check-${width}.png`) });
      check(denied.length === 0, 'no request leaves the page origin: ' + denied.join(','));
      check(errors.length === 0, 'no page errors: ' + errors.join(','));
      await context.close();
    }
    console.log(`PASS ${checks} photo upload checks`);
  } catch (e) { console.error(e.message); process.exitCode = 1; }
  finally { clearTimeout(watchdog); await browser.close(); }
})();
