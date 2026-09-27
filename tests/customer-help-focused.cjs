const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
let chromium;
try { ({chromium} = require('playwright')); }
catch { ({chromium} = require('/Users/red/.agents/skills/gstack/node_modules/playwright')); }
const root = path.resolve(__dirname, '..');
(async () => {
 const browser = await chromium.launch({headless:true});
 const artifacts = process.env.SCREENSHOT_DIR || await fs.mkdtemp(path.join(os.tmpdir(),'customer-help-focused-'));
 await fs.mkdir(artifacts,{recursive:true});
 const errors=[], localRequests=[], optionalRequests=[];
 let checks=0;
 let failFaq=false;
 let allowLocalTest=false;
 try {
  const page=await browser.newPage({ignoreHTTPSErrors:true});
  await page.addInitScript(() => {
   window.spoken = [];
   Object.defineProperty(window, 'speechSynthesis', {value:{cancel(){},speak(u){window.spoken.push({text:u.text,rate:u.rate});}}});
   window.SpeechSynthesisUtterance = class {constructor(text){this.text=text;}};
  });
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const u=new URL(route.request().url());
   if (u.href==='https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js') return route.continue();
   if(allowLocalTest && u.href==='http://localhost:8744/tts') return route.fulfill({status:503,body:'Unavailable'});
   if(allowLocalTest && u.href==='http://localhost:8742/ask') {optionalRequests.push(u.href);return route.fulfill({status:503,body:'Unavailable'});}
   if (u.origin!=='https://fleet.test' && !(allowLocalTest && u.origin==='http://localhost:8741')) {localRequests.push(u.href);return route.abort();}
   if (failFaq && u.pathname==='/web/data/faq.json') return route.fulfill({status:503,body:'Unavailable'});
   const file=path.resolve(root,'.'+u.pathname);
   if(!file.startsWith(root+path.sep)) return route.fulfill({status:403});
   try {await route.fulfill({body:await fs.readFile(file),contentType:({'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png'})[path.extname(file)]||'application/octet-stream'});}
   catch {await route.fulfill({status:404,body:''});}
  });
  const pages=process.env.HELP_PAGES ? process.env.HELP_PAGES.split(',') : ['brain','data-qa','knowledge','voice'];
  for(const width of [320,390,1440]) for(const file of pages) {
   await page.setViewportSize({width,height:1000});
   await page.goto(`https://fleet.test/web/${file}.html?track=home&persona=${file==="data-qa" ? "operations" : "lead"}`);
   if(file==='brain') {
    await page.waitForFunction(()=>document.querySelectorAll('#chips button').length===3 && !/Loading/.test(document.querySelector('#ans-q').textContent));
    assert(await page.locator('#local-ask').isVisible());
    assert(await page.locator('.tabs').isHidden());
    assert.equal(await page.locator('[data-milestones]').count(),0);
    for(const id of ['list','zip-answers','support-card','installation-guide','return-flow']) assert.equal(await page.locator('#'+id).count(),0,id+' removed');
    if(width===320) { await page.waitForFunction(()=>document.querySelectorAll('#askout .msg-brain .speak').length===1); assert.equal(await page.locator('#askout .msg-you').textContent(),'Why is my battery not full?'); assert(await page.locator('#askout .msg-brain .srch').count()===1); }
    const chips=page.locator('#chips button');
    assert.equal(await chips.first().getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('#ans-q').textContent(),await chips.first().textContent());
    await chips.nth(1).click();
    assert.equal(await page.locator('#ans-q').textContent(),await chips.nth(1).textContent());
    assert.equal(await chips.nth(1).getAttribute('aria-pressed'),'true');
    assert(await page.locator('#ans-stats .stat').count()>=1);
    await page.locator('#q').fill('power goes out');
    await page.waitForFunction(()=>/power goes out/i.test(document.querySelector('#ans-q').textContent));
    assert.match(await page.locator('#ans-src').textContent(),/Source:/);
    const kbLink=new URL(await page.locator('#ans-src a.kb').first().getAttribute('href'));
    assert(kbLink.pathname.endsWith('/knowledge.html') && kbLink.searchParams.get('kb') && kbLink.hash==='#knowledge');
    assert.equal(kbLink.searchParams.get('track'),'home');
    await page.locator('#q').fill('stay in their homes');
    await page.waitForTimeout(3000);
    console.log('DBG2', JSON.stringify(await page.evaluate(()=>({cat:document.querySelector('#ans-cat').textContent, q:document.querySelector('#ans-q').textContent, val:document.querySelector('#q').value}))));
    await page.waitForFunction(()=>document.querySelector('#ans-cat').textContent==='Your zip');
    assert.match(await page.locator('#ans-where').textContent(),/Zip 78745/);
    await page.locator('#q').fill('zzzznomatch');
    await page.waitForFunction(()=>/Ask Base Brain/.test(document.querySelector('#ans-q').textContent));
    assert(await page.locator('#ans-foot').isHidden());
    assert(!/\bno\b|not|unavailable|unknown/i.test(await page.locator('#answer').innerText()));
    await page.locator('#q').fill('');
    await chips.first().click();
    const before=await page.evaluate(()=>window.spoken.length);
    await page.locator('#listen').click();
    await page.waitForFunction(n=>window.spoken.length>n,before);
    assert.match(await page.evaluate(()=>window.spoken.at(-1).text),/Source:/);
    assert.equal(await page.locator('#listen').getAttribute('aria-pressed'),'true');
    await page.locator('#listen').click();
    assert.equal(await page.locator('#listen').getAttribute('aria-pressed'),'false');
    assert(await page.locator('#home-body').isVisible());
    assert.match(await page.locator('#home-meta').textContent(),/Zip \d{5}/);
    assert.equal(await page.locator('#help-center').getAttribute('href'),'https://help.basepowercompany.com/');
   } else if(file==='data-qa') {
    await page.waitForSelector('#card .q');
    for(const id of ['prev','next','flip','nail']) assert(await page.locator('#'+id).isHidden());
    assert(await page.locator('#card .ans').isVisible());
    const selectedQuestion=await page.locator('#question-select option').nth(1).textContent();
    await page.locator('#question-select').selectOption('1');
    assert.equal(await page.locator('#card .q').textContent(),selectedQuestion);
    await page.locator('#card .q').click();
    assert(await page.locator('#card .ans').isVisible());
    const beforeQuestion=await page.locator('#card .q').textContent();
    await page.locator('#card').focus();await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('#card .q').textContent(),beforeQuestion);
    await page.locator('#search').fill('permit');
    assert.match(await page.locator('#card').textContent(),/permit/i);
    assert(await page.locator('#card .from').isVisible());
    await page.locator('#card .how summary').click();
    assert(await page.locator('#card .ans').isVisible());
    assert(await page.locator('#card .how code').isVisible());
    await page.locator('#search').fill('zzzznomatch');
    assert(await page.locator('#next').isDisabled());
    assert(await page.locator('#question-select').isDisabled());
    await page.locator('#search').fill('permit');
    const z=await page.locator('#zip option').nth(1).getAttribute('value');
    await page.locator('#zip').selectOption(z);
    assert.equal(await page.locator('#zip').inputValue(),z);
   } else if(file==='knowledge') {
    await page.waitForSelector('#how-src button');
    assert(await page.locator('#groups .grp').count()>=5,'sources grouped by kind');
    await page.locator('#map-toggle').click();
    await page.waitForSelector('.node');
    await page.locator('#q').fill('permit');
    await page.locator('#matches button').first().click();
    assert(await page.locator('#panel h2').isVisible());
    assert.equal(await page.locator('a[href^="../"]').count(),0,'member view has no raw doc or data links');
    assert(!/\b(?:web\/)?data\/[\w.]+\.json|docs\/[\w.]+\.md|GAPS\b/.test(await page.locator('#knowledge').innerText()),'member view shows plain names');
    const bounds=await page.locator('.node circle').first().boundingBox();
    assert(bounds && bounds.width>0);
    await page.locator('#q').fill('zzzznomatch');
    assert.match(await page.locator('#matches').textContent(),/No matching sources/);
    await page.locator('#q').fill('permit');
   } else {
    await page.waitForSelector('#vg-guided h2');
    assert.equal(await page.locator('#vg-voice').getAttribute('aria-pressed'),'false');
    await page.locator('.vg-options summary').click();
    await page.locator('#vg-caregiver').click();
    assert(await page.locator('#vg-caregiver-view').isVisible());
    assert.match(await page.locator('#vg-caregiver-view').textContent(),/closed/i);
    const example=page.locator('.vg-example img').last();
    await example.waitFor();
    assert(await example.evaluate(n=>n.complete&&n.naturalWidth>0));
    await page.locator('#vg-file-cg').setInputFiles({name:'panel.png',mimeType:'image/png',buffer:await fs.readFile(path.join(root,'web/assets/guide-panel.png'))});
    await page.waitForFunction(()=>document.querySelector('#vg-cg-list').textContent.includes('preview only'));
    assert(!/Recorded example/.test(await page.locator('#vg-cg-list').textContent()));
    await page.locator('#vg-caregiver').click();
    assert(await page.locator('#vg-guided').isVisible());
   }
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${file}/${width}: overflow`);
   await page.screenshot({path:path.join(artifacts,`${file}-${width}.png`),fullPage:false});
   checks++;
  }
  if(pages.includes('brain')) {
   const address='706 HUNTINGDON PL';
   for(const [track,persona,query] of [['home','lead','Can someone read the steps to me'],['home','operations','permit'],['compute','gpu','Why is my battery not full'],['compute','fleet','What did one battery earn for the grid last year']]) {
    const params=new URLSearchParams({track,persona,address,node:'7',q:query});
    await page.goto('https://fleet.test/web/brain.html?'+params);
    await page.waitForFunction(q=>document.querySelectorAll('#chips button').length>0 && document.querySelector('#ans-q').textContent.toLowerCase().includes(q.split(' ')[0].toLowerCase()),query);
    const team=['operations','fleet'].includes(persona);
    assert.equal(await page.locator('.tabs').isVisible(),team);
    await page.locator('#home-card').waitFor();
    const ctxLink=persona==='gpu' ? '#home-link' : '#ans-src a.kb';
    await page.waitForSelector(ctxLink+'[href*="track="]',{state:'attached'});
    const kbLink=new URL(await page.locator(ctxLink).first().getAttribute('href'));
    assert.equal(kbLink.searchParams.get('track'),track);
    assert.equal(kbLink.searchParams.get('persona'),persona);
    assert.equal(kbLink.searchParams.get('address'),track==='home' ? address : null);
    assert.equal(kbLink.searchParams.get('node'),track==='compute' ? '7' : null);
    if(persona==='gpu') {
     assert.equal(await page.locator('#home-addr').textContent(),'Node 7');
     assert.equal(new URL(await page.locator('#home-link').getAttribute('href')).searchParams.get('node'),'7');
     assert.match(await page.locator('#chips').textContent(),/battery/i);
    }
    if(team) {
     assert(await page.locator('#home-body').isHidden());
     await page.getByRole('tab',{name:'Members'}).click();
     assert.equal(await page.getByRole('tab',{name:'Members'}).getAttribute('aria-selected'),'true');
     assert(await page.locator('#chips button').count()>0);
    }
    checks++;
   }
   await page.goto('https://fleet.test/web/brain.html?track=home&persona=lead&q=How%20and%20when%20do%20I%20pay');
   await page.waitForFunction(()=>/pay/i.test(document.querySelector('#ans-q').textContent));
   assert.equal(await page.locator('#ans-cat').textContent(),'Base team answers');
   assert.equal(await page.locator('#ans-src a',{hasText:'Open Base Help Center'}).getAttribute('href'),'https://help.basepowercompany.com/');
   checks++;
   failFaq=true;
   await page.goto('https://fleet.test/web/brain.html?track=compute&persona=gpu&node=7&address='+encodeURIComponent(address));
   await page.waitForFunction(()=>document.querySelector('#ans-q').textContent==='Ask Base Brain');
   assert(await page.locator('#local-ask').isVisible());
   failFaq=false;
   checks++;
   allowLocalTest=true;
   await page.goto('http://localhost:8741/web/brain.html?track=home&persona=lead&address='+encodeURIComponent(address));
   await page.waitForSelector('#chips button');
   assert.deepEqual(optionalRequests,[]);
   await page.waitForFunction(()=>document.querySelectorAll('#askout .msg-brain .speak').length===1);
   assert.equal(await page.locator('#askout > *').count(),2);
   await page.locator('#askq').fill('zzzznomatch');
   await page.locator('#askf button').click();
   await page.waitForFunction(()=>document.querySelectorAll('#askout .msg-brain .speak').length===2);
   assert.equal(optionalRequests.length,1);
   assert.equal(await page.locator('#askout .msg-brain a',{hasText:'Open Base Help Center'}).count(),1);
   assert(!/unavailable|not|unknown/i.test(await page.locator('#askout .msg-brain').last().innerText()));
   await page.locator('#askq').fill('What happens in an outage');
   await page.locator('#askf button').click();
   await page.waitForFunction(()=>document.querySelectorAll('#askout .msg-brain .speak').length===3);
   const reply=page.locator('#askout .msg-brain').last();
   assert.match(await reply.textContent(),/power goes out/i);
   assert(new URL(await reply.locator('a.kb').first().getAttribute('href')).searchParams.get('kb'));
   const n=await page.evaluate(()=>window.spoken.length);
   await reply.locator('.speak').click();
   await page.waitForFunction(k=>window.spoken.length>k,n);
   assert.match(await page.evaluate(()=>window.spoken.at(-1).text),/battery/i);
   await page.reload();
   await page.waitForSelector('#chips button');
   assert.equal(await page.locator('#askout .msg-you').count(),2);
   checks++;
  }
  assert.deepEqual(errors,[]);
  assert.deepEqual(localRequests,[],JSON.stringify(localRequests));
  console.log(JSON.stringify({passed:true,checks,artifacts}));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
