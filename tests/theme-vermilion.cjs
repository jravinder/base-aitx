// Historical filename retained for existing commands; verifies the approved green theme.
// Run: node tests/theme-vermilion.cjs. No running server or model service needed.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
let chromium;
try { ({ chromium } = require('playwright')); }
catch { ({ chromium } = require('/Users/red/.agents/skills/gstack/node_modules/playwright')); }
const root = path.resolve(__dirname, '..');

function luminance(hex) {
  let raw = hex.replace('#', '');
  if (raw.length === 3) raw = [...raw].map(c => c + c).join('');
  const rgb = raw.match(/../g).map(c => parseInt(c, 16) / 255)
    .map(c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}
function contrast(a, b) {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

(async () => {
  const css = await fs.readFile(path.join(root, 'web/shell.css'), 'utf8');
  assert(!/overflow(?:-x)?:\s*(?:hidden|clip)/.test(css), 'Do not mask overflow');
  assert(!/letter-spacing:\s*(?!0(?:[;}\s]))[^;}]+/.test(css), 'Zero tracking');
  const browser = await chromium.launch({ headless: true });
  const artifacts = await fs.mkdtemp(path.join(os.tmpdir(), 'theme-vermilion-'));
  const errors = [], external = [];
  let cases = 0;
  try {
    const page = await browser.newPage();
    page.on('pageerror', e => errors.push(e.message));
    // Serve checked-out assets in memory; never call external sources or local models.
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== 'http://base-fleet.test') {
        external.push(url.href);
        return route.abort();
      }
      const file = path.resolve(root, '.' + decodeURIComponent(url.pathname));
      if (!file.startsWith(root + path.sep)) return route.fulfill({ status: 403 });
      const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
        '.json': 'application/json', '.svg': 'image/svg+xml' };
      try { await route.fulfill({ body: await fs.readFile(file), contentType: types[path.extname(file)] || 'text/plain' }); }
      catch { await route.fulfill({ status: 404, body: 'Not found' }); }
    });
    for (const system of ['light', 'dark']) {
      await page.emulateMedia({ colorScheme: system });
      await page.goto('http://base-fleet.test/web/onboarding.html?tour=judge#home');
      await page.waitForSelector('.sh-tour');
      for (const theme of ['auto', 'light', 'dark']) {
        await page.evaluate(theme => {
          if (theme === 'auto') document.documentElement.removeAttribute('data-theme');
          else document.documentElement.dataset.theme = theme;
        }, theme);
        const dark = theme === 'dark';
        const tokens = await page.evaluate(() => {
          const s = getComputedStyle(document.documentElement);
          return Object.fromEntries(['bg', 'surface', 'sunk', 'ink', 'muted', 'faint', 'brand',
            'brand-strong', 'brand-tint', 'on-brand', 'blue', 'blue-tint', 'amber', 'amber-tint',
            'danger', 'danger-tint', 'focus'].map(k => [k, s.getPropertyValue('--bf-' + k).trim()]));
        });
        assert.equal(tokens.brand, dark ? '#86efac' : '#1e4d2b');
        assert.notEqual(tokens.brand, tokens.danger);
        for (const bg of ['bg', 'surface', 'sunk']) {
          for (const fg of ['ink', 'muted', 'faint', 'brand', 'blue']) {
            assert(contrast(tokens[fg], tokens[bg]) >= 4.5, `${system}/${theme}: ${fg} on ${bg}`);
          }
        }
        for (const [fg, bg] of [['on-brand', 'brand'], ['on-brand', 'brand-strong'],
          ['brand', 'brand-tint'], ['blue', 'blue-tint'], ['amber', 'amber-tint'], ['danger', 'danger-tint']]) {
          assert(contrast(tokens[fg], tokens[bg]) >= 4.5, `${theme}: ${fg} on ${bg}`);
        }
        for (const width of [320, 390, 768, 1440]) {
          await page.setViewportSize({ width, height: 900 });
          if (width <= 860 && !await page.locator('.sh-nav').evaluate(n => n.classList.contains('sh-open'))) {
            await page.locator('.sh-toggle').click();
          }
          const layout = await page.evaluate(() => {
            const controls = [...document.querySelectorAll('.sh-nav a,.sh-nav button,.sh-tour-btn,.sh-beats a')]
              .filter(n => n.getClientRects().length);
            return {
              overflow: document.documentElement.scrollWidth > innerWidth,
              controls: controls.map(n => {
                const r = n.getBoundingClientRect();
                return { label: n.textContent, width: r.width, height: r.height, tracking: getComputedStyle(n).letterSpacing };
              }),
              clipped: [...document.querySelectorAll('.sh-nav,.sh-tour,.sh-beats')]
                .filter(n => n.getClientRects().length).some(n => n.scrollWidth > n.clientWidth + 1)
            };
          });
          assert(!layout.overflow, `${theme}/${width}: page overflow`);
          assert(!layout.clipped, `${theme}/${width}: shell content overflow`);
          for (const control of layout.controls) {
            assert(control.width >= 44 && control.height >= 44, `${width}: small control ${JSON.stringify(control)}`);
            assert(['0px', 'normal'].includes(control.tracking), `Nonzero tracking: ${JSON.stringify(control)}`);
          }
          if (width <= 860) await page.locator('.sh-toggle').click();
          if (system === 'light' && theme !== 'auto' && [320, 1440].includes(width)) {
            await page.screenshot({ path: path.join(artifacts, `${theme}-${width}.png`), fullPage: true });
          }
          cases++;
        }
      }
    }
    await page.evaluate(() => {
      const a = document.createElement('a');
      a.href = 'https://example.com/source'; a.id = 'source-probe'; a.textContent = 'Source';
      document.body.append(a);
    });
    assert.equal(await page.locator('#source-probe').evaluate(n => getComputedStyle(n).color), 'rgb(140, 189, 230)');
    await page.keyboard.press('Tab');
    await page.locator('.sh-theme').focus();
    assert.equal(await page.locator('.sh-theme').evaluate(n => getComputedStyle(n).outlineStyle), 'solid');
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(JSON.stringify({ passed: true, themeViewportCases: cases, contrast: '>=4.5:1', artifacts }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
