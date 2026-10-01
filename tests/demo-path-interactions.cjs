const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || '/Users/red/.agents/skills/gstack/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const base = 'https://fleet.test';
(async () => {
 const browser = await chromium.launch({headless:true});
 let checks = 0;
 try {
  const page = await browser.newPage({viewport:{width:390,height:900}});
  const requests = [], errors = [];
  page.on('request', request => requests.push(request.url()));
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => {
   const url = new URL(route.request().url());
   if (url.origin !== base) return route.abort();
   const file = path.resolve(root, '.' + url.pathname);
   if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return route.fulfill({status:404,body:''});
   return route.fulfill({body:fs.readFileSync(file),contentType:({'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png'})[path.extname(file)] || 'text/plain'});
  });
  // Search and Operations left the Base admin nav; they are still reachable by direct URL.
  await page.goto(base+'/web/ask.html');
  await page.waitForSelector('#chips button');
  assert(await page.locator('#chips button').count() <= 4); checks++;
  await page.locator('#chips button').first().click();
  await page.waitForSelector('#run .answer');
  assert(await page.locator('#run .answer').isVisible()); checks++;
  assert(!(await page.locator('#run .trace').isVisible())); checks++;
  await page.locator('#run > details > summary').click();
  assert(await page.locator('#run .trace').isVisible()); checks++;
  await page.goto(base+'/web/admin.html');
  await page.waitForSelector('#feeds table',{state:'attached'});
  assert(!(await page.locator('#pages').isVisible())); checks++;
  assert(!(await page.locator('#tracks').isVisible())); checks++;
  await page.goto(base+'/web/onboarding.html?track=home&persona=lead&address=4305%20MOUNT%20VERNON%20DR');
  await page.waitForSelector('#questions .q-btn');
  // The customer menu overflows into More; it opens from the keyboard.
  await page.locator('.sh-toggle').click();
  const summary = page.locator('.sh-more > summary');
  await summary.focus();
  await page.keyboard.press('Enter');
  assert(await page.locator('.sh-more').evaluate(el=>el.open)); checks++;
  const voice = new URL(await page.locator('.ob-voice[data-voice-step=questions]').getAttribute('href'), page.url());
  assert.equal(voice.searchParams.get('address'),'4305 MOUNT VERNON DR'); checks++;
  assert(!requests.some(url => /https?:\/\/(localhost|127\.0\.0\.1)/.test(url))); checks++;
  assert.deepEqual(errors,[]); checks++;
  console.log('PASS '+checks+' hosted support and navigation checks');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
