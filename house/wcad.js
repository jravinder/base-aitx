// WCAD (Williamson County Appraisal District) property lookup by address.
// Usage: node wcad.js "ADDR, CITY"
// Prints one JSON object to stdout, or {"error": "..."} on failure.
//
// Do NOT store or print owner names. Any output field derived from the
// OWNER NAME column must be stripped before this script returns.

const { chromium } = require("/Users/red/Documents/github/leaseflow/node_modules/playwright");

async function main() {
  const address = process.argv[2];
  if (!address) {
    console.log(JSON.stringify({ error: "usage: node wcad.js \"ADDR, CITY\"" }));
    process.exit(1);
  }

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 900 } });

  try {
    await page.goto("https://search.wcad.org/", { waitUntil: "networkidle" });
    const box = page.locator('input[type="text"], input[type="search"]').first();
    await box.fill(address);
    await box.press("Enter");
    await page.waitForTimeout(4000);

    // Results table row -> PROPERTY ID (R######). The grid navigates via JS
    // on row click (window.location = "/Property-Detail/PropertyQuickRefID/..."),
    // not a plain <a href>. We may also already be on the detail page if
    // there was exactly one match.
    let onDetail = /Property-Detail/.test(page.url()) && /PropertyQuickRefID/.test(page.url());
    if (!onDetail) {
      const row = page.locator(".k-master-row").first();
      if (await row.count()) {
        await row.click();
        await page.waitForLoadState("networkidle");
        await page.waitForTimeout(3000);
        onDetail = /Property-Detail/.test(page.url());
      }
    }

    if (!onDetail) {
      console.log(JSON.stringify({ error: "no match found on WCAD for address", address }));
      await browser.close();
      return;
    }

    const url = page.url();
    const idMatch = url.match(/PropertyQuickRefID[=/](R\d+)/);
    const cadId = idMatch ? idMatch[1] : null;

    // Expand improvement detail rows.
    for (const l of await page.locator("text=Expand/Collapse All Improvements").all()) {
      await l.click().catch(() => {});
    }
    await page.waitForTimeout(2000);

    const text = await page.innerText("body");
    const result = parseWcadText(text, cadId, url);
    console.log(JSON.stringify(result));
  } catch (err) {
    console.log(JSON.stringify({ error: String(err && err.message ? err.message : err) }));
  } finally {
    await browser.close();
  }
}

function parseWcadText(text, cadId, url) {
  const lines = text.split("\n").map((l) => l.trim());

  // Improvement segments: each record is a run of lines
  //   TYPE
  //   YEAR BUILT
  //   SQ. FT
  //   VALUE
  //   ADD'L INFO (optional/blank)
  // followed later (after "Collapse Details") by Class / Foundation / Heat and AC.
  const segmentTypes = [
    "Main Area",
    "Second Floor",
    "Detached Garage",
    "Open Porch",
    "Patio",
  ];

  const segments = [];
  for (let i = 0; i < lines.length; i++) {
    if (segmentTypes.includes(lines[i])) {
      const type = lines[i];
      const yearBuilt = parseInt(lines[i + 1], 10);
      const sqftStr = (lines[i + 2] || "").replace(/,/g, "");
      const sqft = parseInt(sqftStr, 10);
      if (!Number.isNaN(yearBuilt) && !Number.isNaN(sqft)) {
        segments.push({ type, year_built: yearBuilt, sqft, index: i });
      }
    }
  }

  // Class / Foundation / Heat and AC: look at the block of lines after each
  // segment header for the label followed by its value on the next line.
  function fieldAfter(startIdx, label, window = 40) {
    for (let i = startIdx; i < Math.min(lines.length, startIdx + window); i++) {
      if (lines[i] === label) {
        return lines[i + 1] || null;
      }
    }
    return null;
  }

  for (const seg of segments) {
    seg.foundation = fieldAfter(seg.index, "Foundation");
    seg.heat_ac = fieldAfter(seg.index, "Heat and AC");
    seg.class_code = fieldAfter(seg.index, "Class");
  }

  const sqftLiving = segments
    .filter((s) => s.type === "Main Area" || s.type === "Second Floor")
    .reduce((sum, s) => sum + s.sqft, 0);

  const storeys = segments.some((s) => s.type === "Second Floor") ? 2 : 1;

  const garageDetachedSqft = segments
    .filter((s) => s.type === "Detached Garage")
    .reduce((sum, s) => sum + s.sqft, 0);

  const porchPatioSqft = segments
    .filter((s) => s.type === "Open Porch" || s.type === "Patio")
    .reduce((sum, s) => sum + s.sqft, 0);

  const yearBuilt = segments.length
    ? Math.min(...segments.map((s) => s.year_built))
    : null;

  const mainSeg = segments.find((s) => s.type === "Main Area");
  const foundation = mainSeg ? mainSeg.foundation : null;
  const hvac = mainSeg ? mainSeg.heat_ac : null;

  // Land size in acres: "LAND SIZE" column value on the land segment row, or
  // the TOTALS line, e.g. "3,877 Sq. ft / 0.089000 acres".
  let lotAcres = null;
  let lotSqft = null;
  const totalsIdx = lines.indexOf("TOTALS");
  if (totalsIdx !== -1 && lines[totalsIdx + 1]) {
    const m = lines[totalsIdx + 1].match(/([\d,]+)\s*Sq\.\s*ft\s*\/\s*([\d.]+)\s*acres/i);
    if (m) {
      lotSqft = parseInt(m[1].replace(/,/g, ""), 10);
      lotAcres = parseFloat(m[2]);
    }
  }
  if (lotAcres === null) {
    for (const line of lines) {
      const m = line.match(/([\d.]+)\s*acres/i);
      if (m) {
        lotAcres = parseFloat(m[1]);
        break;
      }
    }
  }

  return {
    cad: "WCAD",
    cad_id: cadId,
    year_built: yearBuilt,
    sqft_living: sqftLiving,
    storeys: storeys,
    garage_detached_sqft: garageDetachedSqft,
    porch_patio_sqft: porchPatioSqft,
    foundation: foundation,
    hvac: hvac,
    lot_acres: lotAcres,
    lot_sqft: lotSqft,
    source_url: url,
  };
}

main();
