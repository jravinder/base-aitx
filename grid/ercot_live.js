// grid/ercot_live.js
//
// Pull the ERCOT system-wide prices dashboard JSON through a real headless
// browser (curl hits a bot wall; a browser session does not) and save it in
// the same format as data/ercot-dam-*.json.
//
// Run:
//   node grid/ercot_live.js
//
// Uses Playwright from the leaseflow repo's node_modules.

const path = require('path');
const fs = require('fs');
const { chromium } = require('/Users/red/Documents/github/leaseflow/node_modules/playwright');

const DATA_URL = 'https://www.ercot.com/api/1/services/read/dashboards/systemWidePrices.json';
const OUT_DIR = path.join(__dirname, '..', 'data');

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const seen = new Set();
  page.on('request', (req) => {
    const u = req.url();
    if (u.includes('/api/1/services/read/dashboards/')) seen.add(u);
  });

  await page.goto('https://www.ercot.com', { waitUntil: 'networkidle', timeout: 60000 });

  const json = await page.evaluate(async (url) => {
    const res = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(`fetch failed: ${res.status}`);
    return res.json();
  }, DATA_URL);

  await browser.close();

  // Group intervals by operating day (date portion of "timestamp"), matching
  // the existing per-day file format: one file per day with lastUpdated,
  // rtSppData, damSppData (each filtered to that day), and any other top
  // level keys copied through.
  const days = {};
  const dayArraysKeys = Object.keys(json).filter((k) => Array.isArray(json[k]));

  for (const key of dayArraysKeys) {
    for (const row of json[key]) {
      const ts = row.timestamp || row.intervalEnding;
      if (!ts) continue;
      const day = String(ts).slice(0, 10);
      if (!days[day]) days[day] = {};
      if (!days[day][key]) days[day][key] = [];
      days[day][key].push(row);
    }
  }

  const savedDays = [];
  for (const day of Object.keys(days).sort()) {
    const outPath = path.join(OUT_DIR, `ercot-dam-${day}.json`);
    if (fs.existsSync(outPath)) {
      console.log(`skip ${day}: file already exists`);
      continue;
    }
    const payload = { lastUpdated: json.lastUpdated, ...days[day] };
    fs.writeFileSync(outPath, JSON.stringify(payload));
    savedDays.push(day);
    console.log(`saved ${outPath}`);
  }

  console.log('\nOther dashboard endpoints seen while loading ercot.com:');
  for (const u of seen) console.log(' -', u);

  if (savedDays.length === 0) {
    console.log('\nNo new days saved (all present or no data returned).');
  } else {
    console.log('\nDays saved:', savedDays.join(', '));
  }
}

main().catch((err) => {
  console.error('ercot_live.js failed:', err);
  process.exit(1);
});
