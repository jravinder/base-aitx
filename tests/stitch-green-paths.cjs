/* Run after the green shell is ready: node tests/stitch-green-paths.cjs
 * Optional ROUTES=onboarding.html,tower.html WIDTHS=1440,390 SYSTEMS=light,dark
 * Screenshots/report go to a temporary directory, or OUTPUT_DIR. No backend calls.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
let chromium;
try { ({ chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')); }
catch { ({ chromium } = require('/Users/red/.agents/skills/gstack/node_modules/playwright')); }
const root = path.resolve(__dirname, '..');
const origin = 'https://green-fleet.test';
const address = '706 HUNTINGDON PL';
const mime = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript',
  '.mjs': 'text/javascript', '.json': 'application/json', '.jsonl': 'text/plain',
  '.geojson': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.ico': 'image/x-icon',
  '.ttf': 'font/ttf', '.woff': 'font/woff', '.woff2': 'font/woff2' };
const tracks = { lead: 'home', operations: 'home', gpu: 'compute', fleet: 'compute' };
const tokenNames = ['bg', 'surface', 'sunk', 'ink', 'muted', 'faint', 'brand', 'brand-strong',
  'brand-tint', 'on-brand', 'blue', 'blue-tint', 'amber', 'amber-tint', 'danger', 'danger-tint', 'focus'];

function rgb(value) {
  if (/^#[a-f\d]{3}$/i.test(value)) value = '#' + [...value.slice(1)].map(c => c + c).join('');
  if (/^#[a-f\d]{6}$/i.test(value)) return value.slice(1).match(/../g).map(c => parseInt(c, 16));
  const m = value.match(/^rgb\(\s*(\d+)[, ]+\s*(\d+)[, ]+\s*(\d+)\s*\)$/);
  assert(m, `Unsupported or missing opaque color: ${value}`);
  return m.slice(1).map(Number);
}
function contrast(a, b) {
  const lum = value => rgb(value).map(v => v / 255)
    .map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
    .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
  const [high, low] = [lum(a), lum(b)].sort((a, b) => b - a);
  return (high + 0.05) / (low + 0.05);
}
function checkTokens(tokens) {
  const [r, g, b] = rgb(tokens.brand);
  assert(g > r && g > b && g - Math.min(r, b) >= 20, `Brand must be green: ${tokens.brand}`);
  assert.equal(tokens.brand, '#1e4d2b', 'Approved light brand');
  assert.equal(tokens['brand-strong'], '#023616', 'Approved light strong brand');
  assert.equal(tokens['brand-tint'], '#ecfdf5', 'Approved light brand tint');
  assert.notDeepEqual(rgb(tokens.brand), rgb(tokens.danger), 'Brand must differ from danger');
  for (const bg of ['bg', 'surface', 'sunk']) {
    for (const fg of ['ink', 'muted', 'faint', 'brand', 'blue']) {
      assert(contrast(tokens[fg], tokens[bg]) >= 4.5, `${fg}/${bg} text contrast below 4.5:1`);
    }
    assert(contrast(tokens.focus, tokens[bg]) >= 3, `focus/${bg} contrast below 3:1`);
  }
  for (const [fg, bg] of [['on-brand', 'brand'], ['on-brand', 'brand-strong'],
    ['brand', 'brand-tint'], ['blue', 'blue-tint'], ['amber', 'amber-tint'], ['danger', 'danger-tint']]) {
    assert(contrast(tokens[fg], tokens[bg]) >= 4.5, `${fg}/${bg} text contrast below 4.5:1`);
  }
}

(async () => {
  const files = (await fs.readdir(path.join(root, 'web'))).filter(f => f.endsWith('.html') && f !== 'journey.html' && f !== 'star.html').sort();
  const routes = process.env.ROUTES ? process.env.ROUTES.split(',') : [...files,
    'onboarding.html?track=home&persona=lead&address=' + encodeURIComponent(address),
    'onboarding.html?track=compute&persona=gpu#network',
    'voice.html?track=home&persona=lead&address=' + encodeURIComponent(address),
    'tower.html?track=compute&persona=gpu&node=3',
    'tower.html?track=compute&persona=fleet',
    'brain.html?track=home&persona=operations'];
  const widths = (process.env.WIDTHS || '1440,390').split(',').map(Number);
  const systems = (process.env.SYSTEMS || 'light,dark').split(',');
  assert(widths.every(w => Number.isInteger(w) && w >= 320 && w <= 2560), 'Invalid WIDTHS');
  assert(systems.every(s => ['light', 'dark'].includes(s)), 'Invalid SYSTEMS');
  assert(routes.every(r => files.includes(r.split(/[?#]/)[0])), 'Unknown ROUTES');
  const output = process.env.OUTPUT_DIR ? path.resolve(process.env.OUTPUT_DIR)
    : await fs.mkdtemp(path.join(os.tmpdir(), 'stitch-green-paths-'));
  await fs.mkdir(output, { recursive: true });
  const rows = [];
  let browser;
  const watchdog = setTimeout(() => {
    console.error(`Matrix exceeded five minutes; completed rows and screenshots: ${output}`);
    process.exit(2);
  }, 300000);
  console.log(`Green matrix: ${routes.length * widths.length * systems.length} cases; evidence ${output}`);
  try {
    browser = await chromium.launch({ headless: true, timeout: 15000 });
    for (const route of routes) for (const width of widths) for (const system of systems) {
      const row = { route, width, system, failures: [], runtimeErrors: [], missingAssets: [],
        blocked: [], externalFailures: [], externalCancellations: [] };
      const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: system, serviceWorkers: 'block' });
      const page = await context.newPage();
      page.setDefaultTimeout(2500);
      const blocked = new Set();
      page.on('pageerror', e => row.runtimeErrors.push(e.message));
      page.on('requestfailed', req => {
        if (!blocked.has(req.url()) && new URL(req.url()).origin !== origin) {
          const error = req.failure()?.errorText;
          const list = error === 'net::ERR_ABORTED' ? row.externalCancellations : row.externalFailures;
          list.push({ url: req.url(), error });
        }
      });
      page.on('response', response => {
        if (response.status() >= 400 && new URL(response.url()).origin !== origin)
          row.externalFailures.push({ url: response.url(), status: response.status() });
      });
      await context.route('**/*', async request => {
        const req = request.request(), u = new URL(req.url());
        if (req.method() === 'GET' && u.origin === 'https://cdnjs.cloudflare.com'
          && ['script', 'stylesheet', 'font'].includes(req.resourceType())) return request.continue();
        if (req.method() === 'GET' && u.protocol === 'https:' && /^(?:[abc]\.)?tile\.openstreetmap\.org$/.test(u.hostname)
          && req.resourceType() === 'image') return request.continue();
        const relative = decodeURIComponent(u.pathname).replace(/^\/+/, '');
        if (req.method() !== 'GET' || u.origin !== origin
          || !/^(web|house|panel|brain|data|docs\/(?:shots|evidence))\//.test(relative) || !mime[path.extname(relative)]) {
          blocked.add(req.url()); row.blocked.push(req.url()); return request.abort('blockedbyclient');
        }
        const file = path.resolve(root, relative);
        try {
          assert(file.startsWith(root + path.sep) && (await fs.realpath(file)).startsWith(root + path.sep));
          return await request.fulfill({ body: await fs.readFile(file), contentType: mime[path.extname(file)] });
        } catch {
          row.missingAssets.push(u.pathname);
          return request.fulfill({ status: 404, body: 'Not found' });
        }
      });
      if (context.routeWebSocket) await context.routeWebSocket('**/*', socket => socket.close());
      const check = (label, fn) => { try { fn(); } catch (e) { row.failures.push(label + ': ' + e.message); } };
      let timer;
      try {
        await Promise.race([(async () => {
          const target = new URL('/web/' + route, origin);
          await page.goto(target.href, { waitUntil: 'domcontentloaded', timeout: 10000 });
          const entry = target.pathname.endsWith('/start.html');
          if (!entry) await page.waitForSelector('.sh-nav');
          await page.waitForTimeout(350);
          await page.evaluate(async () => {
            document.querySelectorAll('img').forEach(img => { img.loading = 'eager'; });
            await Promise.race([Promise.all([document.fonts.ready,
              ...[...document.images].map(img => img.decode().catch(() => {}))]),
            new Promise(resolve => setTimeout(resolve, 1500))]);
          });
          const state = await page.evaluate(names => {
            const style = getComputedStyle(document.documentElement);
            return { theme: document.documentElement.dataset.theme,
              tokens: Object.fromEntries(names.map(k => [k, style.getPropertyValue('--bf-' + k).trim()])),
              shellCount: document.querySelectorAll('.sh-nav').length,
              selectors: document.querySelectorAll('.sh-perspective,#sh-track,#sh-persona,.sh-nav select').length,
              width: document.documentElement.scrollWidth,
              brokenImages: [...document.images].filter(img => img.getClientRects().length && !img.naturalWidth).map(img => img.src),
              links: [...document.querySelectorAll('.sh-link')].map(a => ({ id: a.dataset.shId, href: a.href })) };
          }, tokenNames);
          row.state = state; row.finalUrl = page.url();
          check('palette', () => checkTokens(state.tokens));
          check('default light', () => assert.equal(state.theme, 'light'));
          check('shell', () => assert.equal(state.shellCount, entry ? 0 : 1));
          check('no perspective selectors', () => assert.equal(state.selectors, 0));
          check('overflow', () => assert(state.width <= width + 2, `document ${state.width}px / viewport ${width}px`));
          check('images', () => assert.deepEqual(state.brokenImages, []));
          check('context', () => {
            const actual = new URL(page.url());
            assert.equal(actual.pathname, target.pathname, 'Unexpected redirect');
            if (target.hash) assert.equal(actual.hash, target.hash, 'Lost hash');
            for (const [key, value] of target.searchParams) assert.equal(actual.searchParams.get(key), value, `Lost ${key}`);
            if (entry) return;
            const persona = actual.searchParams.get('persona'), track = actual.searchParams.get('track');
            assert.equal(tracks[persona], track);
            assert(state.links.length > 0, 'Empty shell navigation');
            for (const link of state.links) {
              const url = new URL(link.href);
              assert.equal(url.origin, origin, 'Hosted route points off-origin');
              assert.equal(url.searchParams.get('persona'), persona);
              assert.equal(url.searchParams.get('track'), track);
              if (link.id === 'tower' && persona === 'gpu') assert.equal(url.searchParams.get('node'), target.searchParams.get('node') || '3');
              if (['home', 'voice'].includes(link.id) && target.searchParams.has('address'))
                assert.equal(url.searchParams.get('address'), address);
            }
          });
          if (!entry && width <= 860) {
            await page.locator('.sh-toggle').click();
            assert.equal(await page.locator('.sh-toggle').getAttribute('aria-expanded'), 'true');
            assert(await page.locator('.sh-link').first().isVisible());
            assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2));
            await page.keyboard.press('Escape');
            assert.equal(await page.locator('.sh-toggle').getAttribute('aria-expanded'), 'false');
            assert(await page.locator('.sh-toggle').evaluate(el => el === document.activeElement));
          }
          row.screenshot = `${rows.length}-${route.replace(/[^a-z0-9-]/gi, '_')}-${width}-${system}.png`;
          await page.screenshot({ path: path.join(output, row.screenshot), timeout: 4000, animations: 'disabled' });
          if (target.pathname.endsWith('/onboarding.html') && target.searchParams.has('address')) {
            const guide = page.locator('a[href*="voice.html"]:visible').first();
            await guide.click();
            await page.waitForURL(u => u.pathname.endsWith('/voice.html'));
            const next = new URL(page.url());
            assert.equal(next.searchParams.get('address'), address, 'Guide click lost home');
            assert.equal(next.searchParams.get('persona'), 'lead');
            assert.equal(next.searchParams.get('track'), 'home');
          }
        })(), new Promise((_, reject) => { timer = setTimeout(() => reject(Error('Case exceeded 18 seconds')), 18000); })]);
      } catch (e) { row.failures.push(e.message); }
      finally { clearTimeout(timer); await context.close(); }
      if (row.runtimeErrors.length) row.failures.push('Runtime errors (see runtimeErrors; CDN failures listed separately)');
      if (row.missingAssets.length) row.failures.push('Missing same-origin assets');
      if (row.externalFailures.length) row.failures.push('External asset availability: verification incomplete');
      rows.push(row);
      await fs.writeFile(path.join(output, 'report.json'), JSON.stringify({ complete: false, rows }, null, 2));
      console.log(JSON.stringify({ route, width, system, failures: row.failures, externalFailures: row.externalFailures.length }));
    }
    const failed = rows.filter(row => row.failures.length);
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify({ complete: true, passed: !failed.length, rows }, null, 2));
    console.log(`${rows.length - failed.length}/${rows.length} passed; ${failed.length} failed or incomplete. Evidence: ${output}`);
    if (failed.length) process.exitCode = 1;
  } finally {
    try { if (browser) await browser.close(); } finally { clearTimeout(watchdog); }
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
