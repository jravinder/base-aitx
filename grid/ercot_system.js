// grid/ercot_system.js
//
// Load https://www.ercot.com/gridmktinfo/dashboards in headless Chromium, record every
// JSON feed the page requests under /api/1/services/read/dashboards/, and save each one
// to data/ercot/<feed>-<date>.json (date = today in Central time). No login.
// curl hits a bot wall; a browser session does not.
//
// Run:
//   node grid/ercot_system.js

const path = require('path');
const fs = require('fs');
const { chromium } = require('/Users/red/Documents/github/leaseflow/node_modules/playwright');

const PAGE = 'https://www.ercot.com/gridmktinfo/dashboards';
const PREFIX = '/api/1/services/read/dashboards/';
const OUT_DIR = path.join(__dirname, '..', 'data', 'ercot');

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const date = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const feeds = new Map();

  page.on('response', async (res) => {
    const u = res.url();
    const i = u.indexOf(PREFIX);
    if (i < 0 || !res.ok()) return;
    const feed = u.slice(i + PREFIX.length).split('?')[0].replace(/\.json$/, '');
    try { feeds.set(feed, await res.json()); } catch (e) { /* not JSON */ }
  });

  await page.goto(PAGE, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForTimeout(5000);
  await browser.close();

  for (const [feed, json] of [...feeds].sort()) {
    const out = path.join(OUT_DIR, `${feed.replace(/[^\w.-]/g, '_')}-${date}.json`);
    fs.writeFileSync(out, JSON.stringify(json));
    const keys = Object.keys(json).slice(0, 6).join(', ');
    console.log(`saved ${path.relative(process.cwd(), out)}  keys: ${keys}`);
  }
  console.log(`${feeds.size} feeds`);
}

main().catch((err) => { console.error('ercot_system.js failed:', err); process.exit(1); });
