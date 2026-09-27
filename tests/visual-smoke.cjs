const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
let chromium;
try { ({chromium} = require('playwright')); }
catch { ({chromium} = require('/Users/red/.agents/skills/gstack/node_modules/playwright')); }
const base = process.env.BASE_URL || 'http://127.0.0.1:8773';
const output = process.env.SCREENSHOT_DIR || '/private/tmp/base-fleet-vermilion-shots';
(async () => {
  fs.mkdirSync(output, {recursive:true});
  const browser = await chromium.launch({headless:true});
  const results = [];
  try {
    for (const width of [1440, 390]) {
      const page = await browser.newPage({viewport:{width,height:1000}, colorScheme:'light'});
      for (const route of ['onboarding.html','voice.html','member.html?m=m001','story.html','data-qa.html']) {
        const errors = [];
        const onError = error => errors.push(error.message);
        page.on('pageerror', onError);
        await page.goto(base + '/web/' + route);
        await page.waitForLoadState('networkidle');
        assert.deepEqual(errors, [], route + ' runtime errors');
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), route + ' overflow at ' + width);
        if (width < 860) {
          const clear = await page.evaluate(() => {
            const title = document.querySelector('h1');
            const nav = document.querySelector('.sh-nav');
            return !title || !nav || title.getBoundingClientRect().top >= nav.getBoundingClientRect().bottom;
          });
          assert(clear, route + ' heading overlaps mobile navigation');
        }
        const name = route.split('.')[0] + '-' + width + '.png';
        await page.screenshot({path:path.join(output,name),fullPage:true});
        results.push(name);
        page.off('pageerror',onError);
      }
      await page.close();
    }
    console.log(JSON.stringify({passed:true,screenshots:results,output}));
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
