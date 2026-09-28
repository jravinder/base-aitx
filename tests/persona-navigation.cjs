const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
let chromium;
try { ({chromium} = require('playwright')); }
catch { ({chromium} = require('/Users/red/.agents/skills/gstack/node_modules/playwright')); }
const root = path.resolve(__dirname, '..');
const cases = {
  lead: ['home','onboarding.html','home'],
  operations: ['home','market.html','market'], gpu: ['compute','compute-home.html','computehome'],
  fleet: ['compute','overview.html','overview']
};
const menus = {
 lead:['home','status','rewards','brain','member','knowledge','built'],
 operations:['market','judgments','explorer','grid','ask','admin','dataflow','house','recovery','wall','knowledge','brain','built'],
 gpu:['computehome','copilot','energy','plans','models','tower','block','built'],
 fleet:['overview','tower','placement','jobs','index','plans','block','models','pitch','built']
};
(async () => {
 const browser = await chromium.launch({headless:true});
 let checks=0;
 try {
  const page = await browser.newPage({colorScheme:'dark'});
  await page.route('**/*', async route => {
   const u=new URL(route.request().url());
   if(u.origin!=='https://fleet.test') return route.abort();
   const f=path.resolve(root, '.'+u.pathname);
   if(!f.startsWith(root+path.sep)) return route.fulfill({status:403});
   try { await route.fulfill({body:await fs.readFile(f),contentType:({'.html':'text/html','.css':'text/css','.js':'text/javascript','.json':'application/json','.png':'image/png'})[path.extname(f)]||'application/octet-stream'}); }
   catch { await route.fulfill({status:404,body:''}); }
  });
  for (const width of [320,390,1440]) {
   await page.setViewportSize({width,height:1000});
   for (const [persona,[track,file,start]] of Object.entries(cases)) {
    const u=new URL('/web/'+file,'https://fleet.test');u.searchParams.set('track',track);u.searchParams.set('persona',persona);
    await page.goto(u.href); await page.waitForSelector('.sh-nav',{state:'attached'});
    if(width<860) await page.locator('.sh-toggle').click();
    assert.equal(new URL(page.url()).searchParams.get('track'),track);
    assert.equal(new URL(page.url()).searchParams.get('persona'),persona);
    assert.equal(await page.locator('.sh-perspective,#sh-track,#sh-persona').count(),0);
    assert.equal(await page.locator('.sh-beats').count(),0);
    assert.equal(await page.locator('.sh-name').textContent(),track==='compute'?'Base Super Local AI':'Base Ready');
    assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
    assert(!/signed in|authenticated|logged in|demo perspective/i.test(await page.locator('.sh-nav').textContent()));
    const links=await page.locator('.sh-link').evaluateAll(nodes=>nodes.map(n=>({id:n.dataset.shId,url:n.href})));
    assert.deepEqual(links.map(n=>n.id),menus[persona]);
    assert(links.some(n=>n.id===start));
    assert(links.every(n=>new URL(n.url).searchParams.get('persona')===persona));
    assert(links.every(n=>!n.url.includes('localhost')));
    if(persona==='gpu') assert.equal(new URL(links.find(n=>n.id==='tower').url).searchParams.get('node'),'3');
    if(persona==='lead') assert(!links.some(n=>['admin','tower','market'].includes(n.id)));
    if(persona==='gpu') assert(!links.some(n=>['admin','explorer','market','network'].includes(n.id)));
    const overflow = await page.evaluate(()=>({bad:document.documentElement.scrollWidth>innerWidth+1,items:[...document.querySelectorAll('body *')].filter(n=>n.getBoundingClientRect().right>innerWidth+1).slice(0,12).map(n=>n.tagName+'.'+n.className)}));
    assert(!overflow.bad, `${persona} ${width}px overflow ${JSON.stringify(overflow.items)}`);
    checks++;
   }
  }
  await page.goto('https://fleet.test/web/admin.html?track=home&persona=lead');
  await page.waitForURL('**/onboarding.html?*');checks++;
  await page.goto('https://fleet.test/web/story.html?tour=judge');
  await page.waitForSelector('.sh-tour');
  assert.equal(await page.locator('.sh-beats').count(),1);
  const tourUrl=page.url();await page.keyboard.press('ArrowRight');assert.equal(page.url(),tourUrl);
  await page.locator('.sh-tour-exit').click();
  assert.equal(await page.locator('.sh-beats').count(),0);checks++;
  await page.goto('https://fleet.test/web/member.html?persona=customer');
  await page.waitForSelector('.sh-nav');
  assert.equal(new URL(page.url()).searchParams.get('persona'),'lead');checks++;
  for(const saved of ['auto','light','dark']) {
   await page.evaluate(v=>localStorage.setItem('bf-theme',v),saved);
   await page.reload();await page.waitForSelector('.sh-nav');
   assert.equal(await page.locator('html').getAttribute('data-theme'),saved==='dark'?'dark':'light');checks++;
  }
  await page.locator('.sh-theme').click();
  assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
  for(const [raw,role,file] of [
   ['member.html?track=compute&persona=gpu','gpu','compute-home.html'],
   ['market.html','operations','market.html'],
   ['member.html?track=compute','gpu','compute-home.html'],
   ['onboarding.html#network','gpu','onboarding.html']
  ]) {
   await page.goto('https://fleet.test/web/onboarding.html?track=home&persona=lead');
   await page.waitForSelector('.sh-nav');
   const before=page.url();await page.keyboard.press('ArrowRight');assert.equal(page.url(),before);
   await page.evaluate(raw=>{const a=document.createElement('a');a.id='route-probe';a.href=raw;a.textContent='Open';document.body.prepend(a);},raw);
   await page.locator('#route-probe').click();
   await page.waitForURL(u=>u.pathname==='/web/'+file && u.searchParams.get('persona')===role);
   await page.waitForSelector('.sh-nav');
   assert.equal(new URL(page.url()).searchParams.get('persona'),role);checks++;
  }
  const artifacts=await fs.mkdtemp(path.join(os.tmpdir(),'workspace-navigation-'));
  for (const [track, persona, context, value, destination] of [
    ['home','lead','address','4601 CLAWSON RD','home'],
    ['compute','gpu','node','7','tower']
  ]) {
   await page.goto(`https://fleet.test/web/${track === 'home' ? 'brain' : 'copilot'}.html?track=${track}&persona=${persona}&${context}=${encodeURIComponent(value)}`);
   await page.waitForSelector('.sh-nav');
   assert.match(await page.locator('.sh-name').first().innerText(), new RegExp(track === 'home' ? 'Base Ready' : 'Base Super Local AI'));
   const link = new URL(await page.locator(`[data-sh-id="${destination}"]`).getAttribute('href'));
   assert.equal(link.searchParams.get(context), value); checks++;
  }
  await page.goto('https://fleet.test/web/onboarding.html?track=home&persona=lead');
  await page.waitForSelector('#address-select option', {state:'attached'});
  const nextAddress = await page.locator('#address-select option').nth(1).getAttribute('value');
  await page.locator('#address-change').click();
  await page.locator('#address-input').fill(nextAddress);
  await page.locator('#address-list li').first().waitFor();
  await page.locator('#address-input').press('Enter');
  assert.equal(new URL(await page.locator('[data-sh-id="brain"]').getAttribute('href')).searchParams.get('address'),nextAddress); checks++;
  await page.goto('https://fleet.test/web/demo.html?step=5');
  await page.waitForSelector('.sh-nav');
  await page.reload();
  await page.waitForSelector('.sh-nav');
  assert.equal(new URL(page.url()).pathname,'/web/demo.html');
  assert.equal(new URL(page.url()).searchParams.get('step'),'5');checks++;
  await page.goto('https://fleet.test/web/story.html?tour=judge');
  await page.waitForSelector('.sh-tour');
  await page.locator('.sh-link[data-sh-id="explorer"]').click();
  await page.waitForURL(u=>u.pathname==='/web/explorer.html');
  assert.equal(new URL(page.url()).searchParams.get('tour'),'judge');checks++;
  for(const width of [1440,390]) {
   await page.setViewportSize({width,height:1000});
   await page.goto('https://fleet.test/web/onboarding.html?track=home&persona=lead');
   await page.waitForSelector('#questions .q-btn');
   if(width<860) await page.locator('.sh-toggle').click();
   await page.screenshot({path:path.join(artifacts,`navigation-${width}.png`),fullPage:false});
  }
  console.log(`PASS: ${checks} workspace navigation scenarios; screenshots ${artifacts}`);
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
