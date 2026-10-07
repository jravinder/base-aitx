const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || '/Users/red/.agents/skills/gstack/node_modules/playwright');
const root = path.resolve(__dirname, '..');
(async () => {
 const config = JSON.parse(await fs.readFile(path.join(root, 'vercel.json'), 'utf8'));
 const entry = config.redirects.find(r => r.source === '/');
 assert.equal(entry.destination, '/home');
 for(const route of ['/home','/compute']) assert.equal(config.rewrites.find(r=>r.source===route).destination,'/web/start.html');
 assert.equal(entry.permanent, false);
 assert.equal(config.redirects.find(r => r.source === '/myhome').destination, '/web/onboarding.html#home');
 const server = http.createServer(async (req,res) => {
  const u = new URL(req.url, 'http://localhost');
  if(u.pathname === '/') { res.writeHead(307,{location:entry.destination}); res.end(); return; }
  const rewrite = config.rewrites.find(r=>r.source===u.pathname);
  const file = path.resolve(root, '.' + (rewrite ? rewrite.destination : u.pathname));
  if(!file.startsWith(root + path.sep)) { res.writeHead(403); res.end(); return; }
  try {
   const body = await fs.readFile(file);
   res.writeHead(200, {'Content-Type':({'.html':'text/html','.css':'text/css','.js':'text/javascript','.json':'application/json'})[path.extname(file)] || 'application/octet-stream'});
   res.end(body);
  } catch {res.writeHead(404); res.end();}
 });
 await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
 const origin = 'http://127.0.0.1:' + server.address().port;
 let browser;
 try {
  browser = await chromium.launch({headless:true});
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror',e => errors.push(e.message));
  const shots = path.join(root,process.env.SCREENSHOT_DIR || 'docs/evidence/entry-paths');
  await fs.mkdir(shots,{recursive:true});
  const choices=[['choose-install','onboarding.html','lead','home','Get the next battery installed faster'],
   ['choose-fleet','overview.html','fleet','compute','Make the fleet more than backup power'],
   ['choose-ercot','grid.html','operations','home','Know when a battery is worth the most']];
  for(const track of ['home','compute']) for(const width of [320,390,1440]) {
   await page.setViewportSize({width,height:900});
   await page.goto(origin + (track==='home' ? '/' : '/compute'));
   assert.equal(new URL(page.url()).pathname,'/'+track);
   assert.equal(await page.locator('h1').innerText(),'What do you want to dig into?');
   assert.equal(await page.title(),'Base Power Case Study');
   // One question, exactly three choices, nothing else in main.
   assert.equal(await page.locator('main a').count(),3);
   assert.equal(await page.locator('main .choice').count(),3);
   assert.equal(await page.locator('h2,select,input,button').count(),0);
   assert.equal(await page.locator('.sh-nav,.sh-beats').count(),0);
   assert(!/sample|fictional|US-TX|Hz|24 ?kWh|islanding|terminal|secure grid/i.test(await page.locator('body').innerText()));
   assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false);
   for(const [id,destination,role,t,label] of choices) {
    const choice=page.locator('#'+id);
    assert(await choice.isVisible());
    assert.equal((await choice.locator('b').innerText()).trim(),label);
    const target = new URL(await choice.getAttribute('href'),page.url());
    assert.equal(target.pathname,'/web/'+destination);
    assert.equal(target.searchParams.get('persona'),role);
    assert.equal(target.searchParams.get('track'),t);
   }
   // All three choices sit on the first screen.
   if(width>=1000) for(const [id] of choices) { const bb=await page.locator('#'+id).boundingBox(); assert(bb.y + bb.height <= 900, id+' below the fold'); } // desktop: whole choices on the first screen; phone stacks
   const order=[];
   for(let i=0;i<4;i++){await page.keyboard.press('Tab');order.push(await page.locator(':focus').getAttribute('id'));}
   assert.deepEqual(order,['days-sq',...choices.map(c=>c[0])]); // the day grid is keyboard-readable, then the three choices
   for(const [label,dest] of [['What we built','/web/built.html'],['Repo','https://github.com/jravinder/base-aitx']]) assert.equal(await page.locator('footer a',{hasText:label}).first().getAttribute('href'),dest);
   await page.screenshot({path:path.join(shots,track+'-'+width+'.png'),fullPage:true});
  }
  for(const [id,,role,track] of choices) {
   await page.goto(origin+'/home');
   await page.locator('#'+id).click();
   await page.waitForSelector('.sh-nav');
   assert.equal(new URL(page.url()).searchParams.get('persona'),role);
   assert.equal(new URL(page.url()).searchParams.get('track'),track);
   assert.equal(await page.locator('#sh-persona,#sh-track').count(),0);
  }
  // Base admin is no longer a landing link: from the lead flow, the in-page Customer -> Base admin switch opens it.
  await page.goto(origin+'/home');
  await page.locator('#choose-install').click();
  await page.waitForSelector('.sh-role-link[data-sh-role="operations"]',{state:'attached'});
  await page.locator('.sh-role-link[data-sh-role="operations"]').click();
  await page.waitForSelector('.sh-nav');
  assert.equal(new URL(page.url()).searchParams.get('persona'),'operations');
  assert.equal(new URL(page.url()).searchParams.get('track'),'home');
  assert.deepEqual(errors,[]);
  console.log('PASS: /home and /compute; root defaults to /home; 6 viewport/track cases; one question, three choices; keyboard order; 3 choice destinations; Customer to Base admin switch; no JS errors.');
 } finally {
  if(browser) await browser.close();
  await new Promise(resolve=>server.close(resolve));
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
