/* Photo upload flow in onboarding step 3: in-browser quality check, hosted reading panel, Confirm awards the photo.
 * Reading paths use a mocked /api/read-photo: progress bar, low confidence, failure, timeout, Not right -> Base reviewer.
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
      if (kind === 'blurry') { const c2 = document.createElement('canvas'); c2.width = 1200; c2.height = 900;
        const y = c2.getContext('2d'); y.filter = 'blur(8px)'; y.drawImage(c, 0, 0); return c2.toDataURL('image/jpeg', 0.92).split(',')[1]; }
    }
    return c.toDataURL('image/jpeg', 0.92).split(',')[1];
  }, kind);
  return { name: kind + '.jpg', mimeType: 'image/jpeg', buffer: Buffer.from(b64, 'base64') };
}

(async () => {
  const watchdog = setTimeout(() => { console.error('photo-check suite exceeded 150 s'); process.exit(2); }, 150000);
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
      // Mocked reading server: {delay, status, body}; records the request bodies.
      let mock = null; const sent = [];
      await page.route('**/api/read-photo', async route => {
        sent.push(JSON.parse(route.request().postData() || '{}'));
        const m = mock;
        await new Promise(r => setTimeout(r, m.delay || 0));
        try { await route.fulfill({ status: m.status || 200, contentType: 'application/json', body: JSON.stringify(m.body || {}) }); } catch { /* aborted by the page */ }
      });
      const good = { photo_type: 'meter_exterior', manufacturer: null, main_breaker_amps: null, usable: true, retake_reason: null, confidence: 0.95, model: 'gemini-3.8-flash', seconds: 2.1 };
      await page.goto(origin + '/web/onboarding.html?track=home&persona=lead&static', { waitUntil: 'load' });
      await page.waitForFunction(() => !document.getElementById('pk-file').disabled);
      check(await page.locator('#pk-file').getAttribute('capture') === 'environment', 'camera capture on the input');

      await page.setInputFiles('#pk-file', await synth(page, 'dark'));
      await page.waitForSelector('.pk-chip[data-check="light"]');
      check(await page.locator('.pk-chip[data-check="light"]').getAttribute('data-pass') === 'false', 'dark photo fails light');
      check(/of 255/.test(await page.locator('.pk-chip[data-check="light"]').innerText()), 'light chip shows measured value');
      check(/Too dark: turn on a light or use the flash/.test(await page.locator('.pk-tips').innerText()), 'dark retake tip');
      check(await page.locator('#pk-confirm').isDisabled(), 'Confirm waits for a clear photo');
      const firstSrc = await page.locator('.pk-preview img').getAttribute('src');

      await page.setInputFiles('#pk-file', await synth(page, 'sharp'));
      await page.waitForFunction(() => document.querySelector('.pk-chip[data-check="light"]')?.dataset.pass === 'true');
      for (const id of ['resolution', 'light', 'sharpness', 'framing'])
        check(await page.locator(`.pk-chip[data-check="${id}"]`).getAttribute('data-pass') === 'true', `sharp photo passes ${id}`);
      check(await page.locator('.pk-tip').count() === 0, 'no retake tips for a clear photo');
      check(await page.locator('.pk-preview img').getAttribute('src') !== firstSrc, 'retake replaces the preview');
      check(/^blob:/.test(await page.locator('.pk-preview img').getAttribute('src')), 'photo stays on the device as an object URL');
      check(/Reading sends this one photo to Google Gemini/.test(await page.locator('#pk-read').innerText()), 'hosted reading panel');

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
      // Reading: progress stages, elapsed timer and expected time while the mocked server answers.
      await page.setInputFiles('#pk-file', await synth(page, 'sharp'));
      await page.waitForSelector('#pk-read-pc');
      await page.locator('#pk-shot').selectOption('closed_breaker_box');
      await page.waitForSelector('#pk-read-pc');
      mock = { delay: 1500, body: good };
      await page.locator('#pk-read-pc').click();
      const bar = page.locator('#pk-progress[role="progressbar"]');
      await bar.waitFor();
      check(/Checking quality[\s\S]*Sending[\s\S]*Reading[\s\S]*Done/.test(await page.locator('.pk-steps').innerText()), 'four progress stages');
      check(/Usually 3 to 6 seconds/.test(await page.locator('.pk-progress').innerText()), 'expected time for the hosted reading');
      check(/^\d+ s$/.test(await page.locator('.pk-elapsed').innerText()), 'elapsed timer');
      check(await bar.getAttribute('aria-valuemin') === '0' && await bar.getAttribute('aria-valuemax') === '100', 'progressbar range');
      check(await page.locator('#pk-live').getAttribute('aria-live') === 'polite', 'stage changes announced politely');
      await page.waitForFunction(() => document.querySelector('.pk-step[data-state="now"]')?.textContent === 'Reading');
      await page.locator('#photos').screenshot({ path: path.join(root, `docs/evidence/photo-check-progress-${width}.png`) });
      await page.waitForSelector('.pk-usable.is-ok');
      check(sent.at(-1).shot === 'closed_breaker_box' && sent.at(-1).mime === 'image/jpeg' && sent.at(-1).image.length > 100, 'page sends image, mime and shot');
      check(/Read by Gemini in/.test(await page.locator('#pk-read').innerText()), 'reading time shown');

      // Not right -> ask a Base reviewer.
      await page.locator('#pk-not-right').click();
      await page.locator('#pk-ask-review').click();
      const reviewKey = 'base-fleet:review:v1:' + await page.evaluate(() => Object.keys(localStorage).find(k => k.startsWith('base-fleet:journey:v1:')).slice('base-fleet:journey:v1:'.length));
      const rev = await page.evaluate(k => JSON.parse(localStorage.getItem(k)), reviewKey);
      check(rev && rev.shot === 'closed_breaker_box' && rev.reason === 'not_right' && !Number.isNaN(Date.parse(rev.time)), 'review saved with shot, time and reason');
      check(/A Base reviewer will check this photo during the engineering review\. You can keep going\./.test(await page.locator('.pk-msg').innerText()), 'review note shown');
      check(/^Submit for review/.test(await page.locator('#pk-confirm').innerText()) && !(await page.locator('#pk-confirm').isDisabled()), 'flow continues with Submit for review');

      // Low confidence offers the reviewer without a click on Not right.
      await page.locator('#pk-shot').selectOption('meter_closeup');
      mock = { delay: 50, body: { ...good, usable: false, retake_reason: 'Open the panel door and photograph the breakers inside.', confidence: 0.4 } };
      await page.locator('#pk-read-pc').click();
      await page.waitForSelector('#pk-ask-review');
      check(/unsure about this photo/.test(await page.locator('#pk-review-box').innerText()), 'low confidence offers a reviewer');
      check(!/open|inside/i.test(await page.locator('.pk-usable').innerText()), 'retake advice keeps doors closed: ' + await page.locator('.pk-usable').innerText());

      // Server failure offers the reviewer and a second try.
      await page.locator('#pk-shot').selectOption('meter_surroundings');
      mock = { status: 502, body: { error: 'reading failed' } };
      await page.locator('#pk-read-pc').click();
      await page.waitForSelector('#pk-ask-review');
      check(await page.locator('#pk-read-pc').innerText() === 'Read again', 'failed reading can run again');

      // Timeout: the deadline (30 s in the page, shortened here) offers the reviewer.
      await page.evaluate(() => { window.BasePhotoCheck.LIMITS.deadline = 800; });
      mock = { delay: 3000, body: good };
      await page.locator('#pk-read-pc').click();
      await page.waitForSelector('#pk-ask-review');
      check(/taking longer than usual/.test(await page.locator('#pk-review-box').innerText()), 'timeout offers a reviewer');
      await page.evaluate(() => { window.BasePhotoCheck.LIMITS.deadline = 30000; });
      await page.locator('#pk-ask-review').click();
      check((await page.evaluate(k => JSON.parse(localStorage.getItem(k)), reviewKey)).reason === 'timeout', 'timeout reason saved');
      await page.locator('#pk-confirm').click();
      check(/for Base review/.test(await page.locator('.pk-msg').innerText()), 'submitted for review');
      check(await page.evaluate(() => { const k = Object.keys(localStorage).find(k => k.startsWith('base-fleet:journey:v1:')); return JSON.parse(localStorage.getItem(k)).photo === true; }), 'photo points kept on submit for review');
      await page.locator('#photos').screenshot({ path: path.join(root, `docs/evidence/photo-check-review-${width}.png`) });

      // Status page shows the photo under step 4.
      await page.goto(origin + '/web/status.html?address=' + encodeURIComponent(reviewKey.slice('base-fleet:review:v1:'.length)), { waitUntil: 'load' });
      await page.waitForFunction(() => document.getElementById('action-title')?.textContent !== 'Loading');
      check(await page.locator('#photo-review').isVisible(), 'status shows the photo waiting for Base review');
      await page.locator('#photo-review').screenshot({ path: path.join(root, `docs/evidence/status-photo-review-${width}.png`) });
      check(/Photo waiting for Base review/.test(await page.locator('#photo-review').innerText()), 'status review copy');

      check(denied.length === 0, 'no request leaves the page origin: ' + denied.join(','));
      check(errors.length === 0, 'no page errors: ' + errors.join(','));
      await context.close();
    }
    // Blurry photo on the PC's own page (auto-read) with a mocked Gemini "usable": Confirm stays blocked.
    {
      const local = 'http://localhost:8799';
      const context = await browser.newContext({ viewport: { width: 390, height: 900 } });
      const page = await context.newPage();
      const denied = [], errors = [], sent = [];
      page.on('pageerror', e => errors.push(e.message));
      await context.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.href.startsWith('http://localhost:8742/photo/read')) {
          sent.push(url.href);
          return route.fulfill({ status: 200, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': local },
            body: JSON.stringify({ photo_type: 'meter_exterior', manufacturer: null, main_breaker_amps: 200, usable: true, retake_reason: null, confidence: 0.95, model: 'gemini-3.8-flash', seconds: 2 }) });
        }
        if (url.origin !== local) { denied.push(url.href); return route.abort('blockedbyclient'); }
        const file = path.resolve(root, decodeURIComponent(url.pathname).replace(/^\/+/, ''));
        try { return await route.fulfill({ body: await fs.readFile(file), contentType: types[path.extname(file)] || 'application/octet-stream' }); }
        catch { return route.fulfill({ status: 404, body: '' }); }
      });
      await page.goto(local + '/web/onboarding.html?track=home&persona=lead', { waitUntil: 'load' });
      await page.waitForFunction(() => !document.getElementById('pk-file').disabled);
      await page.setInputFiles('#pk-file', await synth(page, 'blurry'));
      await page.waitForSelector('.pk-chip[data-check="sharpness"]');
      check(await page.locator('.pk-chip[data-check="sharpness"]').getAttribute('data-pass') === 'false', 'blurry photo fails sharpness');
      check(/Blurry: hold still and tap to focus/.test(await page.locator('.pk-tips').innerText()), 'blurry tip shown');
      await page.waitForTimeout(1500);
      check(await page.locator('#pk-confirm').isDisabled() && !(await page.locator('#pk-confirm').isVisible()), 'Confirm blocked for a blurry photo even when the reading says usable');
      check(!(await page.locator('#pk-correct').isVisible()) && await page.locator('#pk-retake').isVisible(), 'only Retake is offered with the reviewer');
      check(await page.locator('#pk-ask-review').isVisible() && await page.locator('#pk-read-pc').count() === 0, 'reviewer offered, no read button');
      check(sent.length === 1, 'mocked Gemini was asked');
      await page.locator('#photos').screenshot({ path: path.join(root, 'docs/evidence/photo-check-blurry-390.png') });
      await page.locator('#pk-ask-review').click();
      check(/^Submit for review/.test(await page.locator('#pk-confirm').innerText()) && !(await page.locator('#pk-confirm').isDisabled()), 'reviewer path keeps the flow moving');
      check(denied.length === 0, 'blurry case: no other requests: ' + denied.join(','));
      check(errors.length === 0, 'blurry case: no page errors: ' + errors.join(','));
      await context.close();
    }
    console.log(`PASS ${checks} photo upload checks`);
  } catch (e) { console.error(e.message); process.exitCode = 1; }
  finally { clearTimeout(watchdog); await browser.close(); }
})();
