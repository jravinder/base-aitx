/* Read-only browser audit. ROUTES=onboarding.html,onboarding.html#network WIDTHS=1440,390
 * PAGE_TIMEOUT_MS=25000 SETTLE_MS=1200 STRICT=1 node tests/all-pages-visual.cjs
 * Public HTTPS assets are allowed; APIs, mutations and private-network traffic are blocked.
 */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/Users/red/.agents/skills/gstack/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const out = path.join(root, process.env.EVIDENCE_DIR || 'docs/evidence/coherent');
const files = fs.readdirSync(path.join(root, 'web')).filter(f => f.endsWith('.html')).sort();
const routes = process.env.ROUTES ? process.env.ROUTES.split(',') : [...files, 'onboarding.html#network'];
for (const route of routes) if (!files.includes(route.split(/[?#]/)[0])) throw Error('Unknown route: ' + route);
const widths = (process.env.WIDTHS || '1440,390').split(',').map(Number);
if (widths.some(w => !Number.isInteger(w) || w < 280 || w > 2560)) throw Error('Invalid WIDTHS');
const timeout = Math.min(60000, Math.max(5000, Number(process.env.PAGE_TIMEOUT_MS) || 25000));
const settle = Math.min(5000, Math.max(100, Number(process.env.SETTLE_MS) || 1200));
const mime = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json', '.jsonl': 'text/plain', '.geojson': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.woff2': 'font/woff2', '.ico': 'image/x-icon' };
const stamp = () => new Date().toISOString();
mime['.ttf'] = 'font/ttf';
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const sourceHashes = () => Object.fromEntries([...files.map(f => 'web/' + f), 'web/shell.css', 'web/shell.js', 'web/onboarding.js', 'web/onboarding.css'].map(f => [f, hash(path.join(root, f))]));
const escape = text => String(text).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const privateHost = hostname => /^(localhost|.*\.localhost|.*\.local|127\..*|10\..*|192\.168\..*|169\.254\..*|172\.(1[6-9]|2\d|3[01])\..*|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\..*|\[.*\])$/i.test(hostname);
const apiPath = pathname => /^\/(api(?:\/|$)|state$|node\/|jobs(?:\/|$)|kill$|health$|ask$)/.test(pathname);
const server = http.createServer((req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://local').pathname);
    const file = path.resolve(root, '.' + pathname);
    const relative = path.relative(root, file);
    const allowed = /^(web|house|panel|brain|data)\//.test(relative) || relative.startsWith('docs/evidence/') || relative.startsWith('docs/shots/');
    if (!['GET', 'HEAD'].includes(req.method) || !allowed || relative.split(path.sep).some(p => p.startsWith('.')) || !mime[path.extname(file)] || !fs.existsSync(file) || !fs.statSync(file).isFile() || !fs.realpathSync(file).startsWith(root + path.sep)) {
      res.writeHead(404); res.end(); return;
    }
    res.writeHead(200, { 'Content-Type': mime[path.extname(file)], 'Cache-Control': 'no-store' });
    if (req.method === 'HEAD') res.end(); else fs.createReadStream(file).pipe(res);
  } catch { res.writeHead(400); res.end(); }
});

async function inspect(page) {
  return page.evaluate(() => {
    const visible = el => { if (el.checkVisibility && !el.checkVisibility()) return false; const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
    const label = el => el.id ? '#' + el.id : el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.') : '');
    const text = el => (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 140);
    const nodes = [...document.querySelectorAll('body *')].filter(visible);
    const overflow = nodes.filter(el => { const r = el.getBoundingClientRect(); return r.right > innerWidth + 2 || r.left < -2; }).map(el => ({ selector: label(el), text: text(el), left: Math.round(el.getBoundingClientRect().left), right: Math.round(el.getBoundingClientRect().right) })).slice(0, 35);
    const clipped = nodes.filter(el => !el.children.length && text(el) && ['hidden', 'clip'].includes(getComputedStyle(el).overflowX) && el.scrollWidth > el.clientWidth + 3).map(el => ({ selector: label(el), text: text(el) })).slice(0, 25);
    const controls = nodes.filter(el => el.matches('button,input:not([type=hidden]),select,textarea,[role=button]'));
    const unnamedControls = controls.filter(el => !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby') && !el.getAttribute('title') && !(el.labels && el.labels.length) && !text(el) && !el.value).map(label);
    const tinyControls = controls.filter(el => { const r = el.getBoundingClientRect(); return r.width < 24 || r.height < 24; }).map(el => ({ selector: label(el), text: text(el) })).slice(0, 20);
    const brokenImages = [...document.images].filter(el => visible(el) && (!el.complete || !el.naturalWidth)).map(el => el.src);
    const canvases = [...document.querySelectorAll('canvas')].filter(visible).map(el => {
      let result = 'unreadable';
      try {
        const probe = document.createElement('canvas'); probe.width = 32; probe.height = 32;
        const ctx = probe.getContext('2d'); ctx.drawImage(el, 0, 0, 32, 32);
        const pixels = ctx.getImageData(0, 0, 32, 32).data;
        const colors = new Set(); for (let i = 0; i < pixels.length; i += 4) colors.add(Array.from(pixels.slice(i, i + 4)).join(','));
        result = colors.size <= 1 ? 'uniform-or-blank' : 'nonblank';
      } catch { /* Cross-origin/WebGL buffers may not be readable. */ }
      return { selector: label(el), width: el.width, height: el.height, pixels: result };
    });
    const notices = nodes.filter(el => el.matches('.notice,[role=alert],.error') && text(el)).map(el => ({ selector: label(el), text: text(el) }));
    const links = [...document.querySelectorAll('a[href]')].map(el => ({ href: el.href, text: text(el) }));
    const shells = [...document.querySelectorAll('.sh-nav')];
    const shell = { count: shells.length, visible: shells.length === 1 && visible(shells[0]), navigation: shells[0]?.getAttribute('role') === 'navigation', links: shells[0]?.querySelectorAll('a.sh-link[href]').length || 0, rootClass: document.documentElement.classList.contains('sh') };
    return { shell, title: document.title, heading: [...document.querySelectorAll('h1')].filter(visible).map(text), bodyTextLength: document.body.innerText.length, theme: document.documentElement.dataset.theme || null, background: getComputedStyle(document.body).backgroundColor, foreground: getComputedStyle(document.body).color, width: innerWidth, documentWidth: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight, overflow, clipped, unnamedControls, tinyControls, brokenImages, canvases, notices, links };
  });
}

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const started = stamp(), before = sourceHashes();
  const palette = files.map(file => {
    const source = fs.readFileSync(path.join(root, 'web', file), 'utf8');
    const colors = [];
    for (const block of source.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/gi)) {
      const offset = source.slice(0, block.index).split('\n').length;
      for (const match of block[1].matchAll(/#[\da-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)/gi)) colors.push({ color: match[0], line: offset + block[1].slice(0, match.index).split('\n').length - 1 });
    }
    return { file, hardcodedCount: colors.length, colors };
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  let browser;
  const previous = process.env.UPDATE_MATRIX === '1' && fs.existsSync(path.join(out, 'matrix.json'))
    ? JSON.parse(fs.readFileSync(path.join(out, 'matrix.json'), 'utf8')).rows : [];
  const rows = previous.filter(row => !routes.includes(row.route) || !widths.includes(row.width));
  const watchdog = setTimeout(() => { console.error('Global audit timeout'); server.closeAllConnections(); process.exit(2); }, (routes.length * widths.length + 3) * (timeout + 5000));
  try {
    browser = await chromium.launch({ headless: true });
    for (const route of routes) for (const width of widths) {
      const name = route.replace(/[^a-z0-9-]/gi, '_') + '-' + width;
      const row = { route, width, started: stamp(), runtimeErrors: [], consoleErrors: [], blocked: [], externalFailures: [], localFailures: [], httpErrors: [] };
      const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: 'light', serviceWorkers: 'block' });
      const page = await context.newPage();
      page.setDefaultTimeout(4000);
      const blocked = new Set();
      await context.route('**/*', async requestRoute => {
        const req = requestRoute.request(), url = new URL(req.url());
        if (!['http:', 'https:'].includes(url.protocol)) return requestRoute.continue();
        const deny = !['GET', 'HEAD'].includes(req.method()) || (url.origin === origin ? apiPath(url.pathname) : privateHost(url.hostname) || url.protocol !== 'https:' || ['fetch', 'xhr', 'eventsource', 'websocket'].includes(req.resourceType()));
        if (deny) { blocked.add(req.url()); row.blocked.push({ url: req.url(), method: req.method() }); return requestRoute.abort('blockedbyclient'); }
        return requestRoute.continue();
      });
      if (context.routeWebSocket) await context.routeWebSocket('**/*', socket => socket.close());
      page.on('pageerror', error => row.runtimeErrors.push(error.message));
      page.on('console', message => { if (message.type() === 'error') row.consoleErrors.push(message.text()); });
      page.on('requestfailed', req => {
        if (blocked.has(req.url())) return;
        const list = req.url().startsWith(origin) ? row.localFailures : row.externalFailures;
        list.push({ url: req.url(), error: req.failure()?.errorText });
      });
      page.on('response', response => { if (response.status() >= 400) row.httpErrors.push({ url: response.url(), status: response.status() }); });
      let timer;
      try {
        await Promise.race([(async () => {
          await page.goto(origin + '/web/' + route, { waitUntil: 'domcontentloaded', timeout: 14000 });
          await page.waitForTimeout(settle);
          await page.evaluate(async () => {
            const images = [...document.images];
            images.forEach(img => { img.loading = 'eager'; });
            await Promise.race([Promise.all(images.map(img => img.decode().catch(() => {}))), new Promise(resolve => setTimeout(resolve, 2000))]);
          });
          // Visit the bottom once so lazy images participate without waiting on live polling.
          await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
          await page.waitForTimeout(250);
          await page.evaluate(() => window.scrollTo(0, 0));
          row.dom = await inspect(page);
          const shell = row.dom.shell;
          row.shellPresent = shell.count === 1 && shell.visible && shell.navigation && shell.links > 0 && shell.rootClass;
          row.missingLinks = row.dom.links.filter(link => {
            const url = new URL(link.href);
            if (url.origin !== origin || !url.pathname.endsWith('.html')) return false;
            return !fs.existsSync(path.resolve(root, '.' + decodeURIComponent(url.pathname)));
          });
          delete row.dom.links;
          row.viewportShot = name + '.png';
          await page.screenshot({ path: path.join(out, row.viewportShot), animations: 'disabled', timeout: 6000 });
          row.fullShot = name + '-full.png';
          await page.screenshot({ path: path.join(out, row.fullShot), fullPage: true, animations: 'disabled', clip: { x: 0, y: 0, width, height: Math.min(row.dom.height, 16000) }, timeout: 6000 });
          row.captureTruncated = row.dom.height > 16000;
          row.continuationShots = [];
          for (let y = 16000; y < row.dom.height; y += 16000) {
            const shot = name + '-part-' + (Math.floor(y / 16000) + 1) + '.png';
            await page.screenshot({ path: path.join(out, shot), fullPage: true, animations: 'disabled', clip: { x: 0, y, width, height: Math.min(16000, row.dom.height - y) }, timeout: 6000 });
            row.continuationShots.push(shot);
          }
          row.captureTruncated = false;
          row.entryPage = route.split(/[?#]/)[0] === 'start.html';
          assert.ok(row.shellPresent || (row.entryPage && shell.count === 0), `Shared shell missing or incomplete on ${route} at ${width}px: ${JSON.stringify(shell)}`);
          // Native disclosures can be checked without submitting forms or starting backends.
          row.disclosures = [];
          for (const text of (await page.locator('details:visible > summary').allTextContents()).slice(0, 5)) {
            const summary = page.locator('details:visible > summary').filter({hasText:text}).first();
            const initial = await summary.evaluate(el => el.parentElement.open);
            await summary.focus(); await page.keyboard.press('Enter');
            row.disclosures.push({ text, toggled: await summary.evaluate(el => el.parentElement.open) !== initial });
            await page.keyboard.press('Enter');
          }
        })(), new Promise((_, reject) => { timer = setTimeout(() => reject(Error('Page matrix timeout')), timeout); })]);
      } catch (error) { row.error = error.message; }
      finally { clearTimeout(timer); await context.close(); }
      row.finished = stamp(); rows.push(row);
      fs.writeFileSync(path.join(out, 'matrix.json'), JSON.stringify({ started, finished: stamp(), origin, routes, widths, before, after: sourceHashes(), palette, rows }, null, 2));
      const d = row.dom;
      console.log(JSON.stringify({ route, width, shellPresent: row.shellPresent, error: row.error, overflow: d ? d.documentWidth - width : null, brokenImages: d?.brokenImages.length, runtime: row.runtimeErrors, externalFailures: row.externalFailures.length, localHTTP: row.httpErrors.filter(x => x.url.startsWith(origin)).length, blocked: row.blocked.length }));
    }
    const cells = rows.map(row => `<article><h2>${escape(row.route)} · ${row.width}px</h2>${row.viewportShot ? `<a href="${escape(row.fullShot)}"><img src="${escape(row.viewportShot)}" loading="eager" alt="${escape(row.route)} at ${row.width}px"></a>${(row.continuationShots || []).map((shot, i) => `<a href="${escape(shot)}">Continuation ${i + 2}</a>`).join('')}` : `<p>${escape(row.error)}</p>`}</article>`).join('');
    const gallery = `<!doctype html><html lang="en"><meta charset="utf-8"><title>Coherent all-pages audit</title><style>body{font:14px system-ui;margin:24px;background:#eee;color:#111}main{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}article{min-width:0}h2{font-size:13px}img{width:100%;height:200px;object-fit:contain;object-position:top;background:white}a{display:block}p{overflow-wrap:anywhere}</style><h1>All pages: desktop and mobile</h1><p>Fresh light-mode contexts. Click a thumbnail for its full-page capture. Backend requests blocked; public CDN assets allowed. See matrix.json for errors and palette candidates.</p><main>${cells}</main></html>`;
    fs.writeFileSync(path.join(out, 'index.html'), gallery);
    const sheet = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await sheet.goto(origin + '/' + path.relative(root, out) + '/index.html', { waitUntil: 'load', timeout: 10000 });
    await sheet.screenshot({ path: path.join(out, 'contact-sheet.png'), fullPage: true, timeout: 10000 });
    await sheet.close();
    const failing = rows.filter(r => r.error || r.runtimeErrors.length || r.dom?.documentWidth > r.width + 2 || r.dom?.brokenImages.length || r.missingLinks?.length);
    console.log(`Completed ${routes.length * widths.length} selected entries; ${rows.length} total matrix entries; ${failing.length} require review. Evidence: ${out}`);
    if (rows.some(row => row.shellPresent === false && !row.entryPage) || (process.env.STRICT === '1' && failing.length)) process.exitCode = 1;
  } finally {
    clearTimeout(watchdog);
    if (browser) await browser.close();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 2; server.closeAllConnections(); server.close(); });
