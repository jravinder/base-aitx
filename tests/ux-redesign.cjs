const { chromium } = require('/Users/red/.agents/skills/gstack/node_modules/playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const root = path.resolve(__dirname, '..');
(async () => {
 const browser = await chromium.launch({headless:true});
 const page = await browser.newPage({viewport:{width:1440,height:1080}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const url='http://127.0.0.1:8769/web/onboarding.html';
 try {
  await page.goto(url);await page.waitForSelector('.fact-row');
  await page.locator('#reset-progress').click();
  await page.locator('#contribution-main_breaker_amps').fill('200');
  await page.getByRole('button',{name:'Save contribution: Main breaker amperage',exact:true}).click();
  const credit=await page.locator('#reward-value').textContent();
  assert.match(credit,/10/);
  await page.getByRole('button',{name:'Save contribution: Main breaker amperage',exact:true}).click();
  assert.equal(await page.locator('#reward-value').textContent(),credit);
  await page.reload();await page.waitForSelector('.fact-row');
  assert.equal(await page.locator('#contribution-main_breaker_amps').inputValue(),'200');
  assert.equal(await page.locator('#reward-value').textContent(),credit);
  await page.locator('#review-submit').click();
  assert.equal(await page.locator('#review-summary').getAttribute('data-state'),'needs-review');
  await page.locator('#photo-check').click();
  await page.waitForFunction(()=>document.querySelector('#photo-result').textContent.toLowerCase().includes('retake'));
  assert(await page.locator('#home-view').isVisible());
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:path.join(root,'docs/shots/redesign-home.png'),fullPage:true});
  await page.screenshot({path:path.join(root,'docs/shots/redesign-home-viewport.png')});
  await page.locator('.sidebar a[data-view="network"]').click();
  await page.locator('#submit-job').click();
  await page.waitForFunction(()=>document.querySelector('#job-status').dataset.state==='running');
  await page.locator('#fail-node').click();
  assert.equal(await page.locator('#job-status').getAttribute('data-state'),'queued');
  await page.waitForFunction(()=>document.querySelector('#job-status').dataset.state==='running');
  assert.match(await page.locator('#job-status').textContent(),/Node 2/);
  await page.screenshot({path:path.join(root,'docs/shots/redesign-network.png'),fullPage:true});
  await page.waitForFunction(()=>document.querySelector('#job-status').dataset.state==='completed');
  await page.locator('#reset-network').click();
  assert.equal(await page.locator('#job-status').getAttribute('data-state'),'idle');
  const sizes=[];
  for(const width of [1920,1440,768,390,320]){
   await page.setViewportSize({width,height:width<500?844:1080});
   for(const hash of ['home','network']){
    await page.goto(url+'#'+hash);await page.waitForSelector('.fact-row',{state:'attached'});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),width+' '+hash+' overflow');
    assert(await page.locator('img').evaluateAll(imgs=>imgs.every(i=>i.complete&&i.naturalWidth)));
    if(width===390) await page.screenshot({path:path.join(root,'docs/shots/redesign-'+hash+'-mobile.png'),fullPage:true});
   }
   sizes.push(width);
  }
  assert.deepEqual(errors,[]);
  const result={sizes,creditDeduplication:true,persistence:true,retake:true,recovery:true,consoleErrors:errors};
  fs.writeFileSync(path.join(root,'docs/shots/redesign-checks.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
