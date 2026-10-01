const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/Users/red/.agents/skills/gstack/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const base = 'http://journey.test';
let checks = 0;
function check(value, message) { assert.ok(value, message); checks++; }
(async () => {
 const browser = await chromium.launch({headless:true});
 try {
  for (const width of [1440,390,320]) {
   const context = await browser.newContext({viewport:{width,height:1000}});
   const page = await context.newPage();
   const errors = [], writes = [];
   page.on('pageerror', e => errors.push(e.message));
   page.on('request', r => { if(r.method() !== 'GET') writes.push(r.url()); });
   await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if(url.origin !== base) return route.abort();
    const file = path.resolve(root, '.'+decodeURIComponent(url.pathname));
    if(!file.startsWith(root+path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return route.fulfill({status:404,body:''});
    const types = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png'};
    return route.fulfill({contentType:types[path.extname(file)] || 'application/octet-stream',body:fs.readFileSync(file)});
   });
   await page.goto(base+'/web/onboarding.html?track=home&persona=lead');
   await page.waitForSelector('#questions .q-btn');
   check(!/Member experience/.test(await page.locator('.topbar').innerText()),'Lead onboarding is not labeled member experience');
   check(/Onboarding/.test(await page.locator('.topbar').innerText()),'Onboarding context');
   check(await page.locator('#questions .q-card').count() === 1,'One question');
   check(await page.locator('#continue-question').isDisabled(),'Choice required');
   check(await page.locator('#credits, #tell-btn, #invite-banner').count() === 0,'No reward/referral detours');
   check(await page.locator('#home-view [data-milestones]').count() === 1,'One shared milestone tracker');
   check(/Base Ready points\b(?! \(proposal\))/i.test(await page.locator('#home-view [data-milestones]').innerText()),'Rewards labelled as Base Ready points');
   check(!/shared hub|badge|streak|leaderboard/i.test(await page.locator('#home-view').innerText()),'No badges or hub copy');
   const houses = JSON.parse(fs.readFileSync(path.join(root,'house/cohort.json')));
   const house = houses.find(h => h.confirm_with_member.includes('main_breaker_amps') && h.confirm_with_member.includes('has_solar'));
   // Find your home: search combobox over the public-record homes, then confirm on the same page.
   check(await page.locator('#address-input[role="combobox"]').count() === 1,'Address search is a combobox');
   await page.locator('#address-change').click();
   check(/Type your address/.test(await page.locator('#find-title').innerText()),'Type your address opens from Change');
   await page.locator('#address-input').fill(house.address.split(' ').slice(1,3).join(' ').toLowerCase());
   await page.waitForSelector('#address-list [role="option"]');
   const optIndex = await page.locator('#address-list [role="option"] strong').evaluateAll((els,a) => els.findIndex(e => e.textContent.toUpperCase() === a), house.address);
   check(optIndex >= 0,'Typed street suggests the home');
   for(let i=0;i<=optIndex;i++) await page.locator('#address-input').press('ArrowDown');
   check(await page.locator('#address-input').getAttribute('aria-activedescendant') === 'address-opt-'+optIndex,'Keyboard moves through suggestions');
   await page.locator('#address-input').press('Enter');
   check(await page.locator('#address-select').inputValue() === house.address,'Search keeps the address select in sync');
   check(/City of Austin permits/.test(await page.locator('#record-card').innerText()),'Record card names the permit source');
   check(await page.locator('#permit-timeline li').count() > 0,'Permit history listed');
   check(!/sample|unverified/i.test(await page.locator('#find-home').innerText()),'No sample or unverified copy');
   await page.locator('#confirm-property').click();
   check(JSON.parse(await page.evaluate(() => localStorage.getItem('base-fleet:home:v1'))).address === house.address,'Confirm saves the home');
   check(/Step 2 of 5: Your details/.test(await page.locator('#step-text').innerText()),'Step header follows the milestone tracker');
   check(new URL(page.url()).pathname === '/web/onboarding.html','Questions stay on the same page');
   await page.waitForTimeout(900);
   const vh = page.viewportSize().height;
   const trackerBox = await page.locator('#journey-milestones').boundingBox(), qBox = await page.locator('#questions').boundingBox();
   check(trackerBox && trackerBox.y < vh && trackerBox.y + trackerBox.height > 0 && qBox.y < vh,'Tracker stays on screen beside the questions');
   await page.locator('.q-skip').click();
   check(await page.locator('.q-skip').getAttribute('aria-pressed') === 'true','Unknown accepted');
   await page.locator('.q-no').click();
   const selected = await page.locator('.q-no').getAttribute('aria-label');
   await page.reload();
   await page.waitForSelector('#questions .q-btn');
   check(await page.locator('#address-select').inputValue() === house.address,'Address retained');
   await page.locator('#back-question').click();
   check(await page.locator('.q-no').getAttribute('aria-pressed') === 'true','False/correction restored');
   check(await page.locator('.q-no').getAttribute('aria-label') === selected,'Answer meaning preserved');
   await page.locator('#reset-progress').click();
   check(await page.locator('#continue-question').isDisabled(),'Reset clears selection');
   if(process.env.SCREENSHOT_DIR) {
    fs.mkdirSync(process.env.SCREENSHOT_DIR,{recursive:true});
    await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'home-question-'+width+'.png'),fullPage:true});
   }
   let photoChecked = false;
   while(await page.locator('#continue-question').isVisible()) {
    const field = await page.locator('.q-card').getAttribute('data-field');
    if(field === 'main_breaker_amps') {
     await page.locator('#panel-help summary').click();
     check(await page.locator('#panel-help').evaluate(el => el.open),'Photo help opens');
     await page.locator('#open-electrical-photos').click();
     check(await page.locator('#photo-checklist > details').evaluate(el => el.open),'Unified checklist opens from panel help');
     check(await page.locator('#photo-input').count() === 0,'No duplicate legacy photo flow');
     photoChecked = true;
    }
    await page.locator('.q-skip').click();
    await page.locator('#continue-question').click();
   }
   check(photoChecked,'Panel help exercised');
   check(await page.locator('.review-row').count() === 5,'Review all five parts');
   check((await page.locator('#home-view').innerText()).match(/saved on this device/ig).length === 1,'Saved on this device shown once');
   const ctaSizes = await page.locator('.review-actions .primary').evaluateAll(els => els.map(e => getComputedStyle(e).fontSize + ' ' + getComputedStyle(e).fontWeight + ' ' + e.getBoundingClientRect().height));
   check(ctaSizes.length === 2 && ctaSizes[0] === ctaSizes[1],'Review CTAs share one button style');
   const guide = page.getByRole('link',{name:'Review with voice guidance',exact:true});
   const guideUrl = new URL(await guide.getAttribute('href'),page.url());
   check(guideUrl.pathname === '/web/voice.html','Review opens installation guide');
   check(guideUrl.searchParams.get('address') === house.address,'Guide preserves selected home');
   check(guideUrl.searchParams.get('track') === 'home' && guideUrl.searchParams.get('persona') === 'lead','Guide preserves customer context');
   check(await page.getByRole('link',{name:'Ask a question',exact:true}).isVisible(),'Help available after review');
   check(await page.locator('.review-row').filter({hasText:'Left open by you'}).count() > 0,'Unknown provenance');
   await page.getByRole('button',{name:'Edit Electric panel',exact:true}).click();
   check(await page.locator('.q-card').getAttribute('data-field') === 'main_breaker_amps','Edit returns to question');
   await page.getByRole('button',{name:'Electric panel: 200 A',exact:true}).click();
   while(await page.locator('#continue-question').isVisible()) await page.locator('#continue-question').click();
   check(/200 A/.test(await page.locator('.home-review').innerText()),'Edited answer in review');
   check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1),'No horizontal overflow');
   // Every question, to the last one, then on to the photo step (4601 Clawson Rd and 4305 Mount Vernon Dr).
   for(const [addr,how] of [['4601 CLAWSON RD','.q-card .q-btn >> nth=0'],['4305 MOUNT VERNON DR','.q-skip']]) {
    await page.evaluate(() => localStorage.clear());
    await page.goto(base+'/web/onboarding.html?track=home&persona=lead&address='+encodeURIComponent(addr));
    await page.waitForSelector('#questions .q-btn');
    await page.locator('#confirm-property').click();
    let n = 0;
    while(await page.locator('#continue-question').isVisible() && n++ < 8) {
     check(await page.locator('#continue-question').isDisabled(),addr+': choice required on question '+n);
     await page.locator(how).click();
     check(await page.locator('#continue-question').isEnabled(),addr+': answer (including Not sure) enables question '+n);
     await page.locator('#continue-question').click();
    }
    check(await page.locator('.review-row').count() === 5,addr+': answers summary shown');
    check(await page.locator('#details').getAttribute('data-state') === 'done',addr+': step 2 done');
    check(await page.locator('#photos').getAttribute('data-state') === 'now',addr+': step 3 is current');
    check(await page.locator('#journey-milestones li[data-milestone="2"]').evaluate(el => el.classList.contains('bf-ms-done')),addr+': tracker marks details done');
    check(await page.evaluate(() => document.activeElement?.id === 'pk-file'),addr+': photo upload focused');
    const pc = await page.locator('#photo-check').boundingBox();
    check(pc && pc.y < page.viewportSize().height && pc.y + pc.height > 0,addr+': photo upload in view');
   }
   check(errors.length === 0,'No runtime errors: '+errors.join(','));
   check(writes.length === 0,'No upload/submission requests');
   if(process.env.SCREENSHOT_DIR) await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'home-review-'+width+'.png'),fullPage:true});
   await context.close();
  }
  console.log('PASS '+checks+' focused homeowner checks');
 } finally { await browser.close(); }
})().catch(e => {console.error(e);process.exitCode=1;});
