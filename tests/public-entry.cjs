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
  for(const track of ['home','compute']) for(const width of [320,390,1440]) {
   await page.setViewportSize({width,height:900});
   await page.goto(origin + (track==='home' ? '/' : '/compute'));
   assert.equal(new URL(page.url()).pathname,'/'+track);
   assert.equal(await page.locator('h1').innerText(),'Pick your track.');
   assert.equal(await page.title(),track==='home'?'Base Home | Base Fleet':'Base Compute | Base Fleet');
   assert.equal(await page.locator('#'+track+'-card.is-route').count(),1);
   assert.equal(await page.locator('main a').count(),7);
   assert.equal(await page.locator('select,input,button').count(),0);
   assert.deepEqual((await page.locator('h2').allTextContents()).map(t=>t.trim()),['Base Home','Base Compute']);
   assert.equal(await page.locator('.sh-nav,.sh-beats').count(),0);
   assert(!/sample|fictional|US-TX|Hz|24 ?kWh|islanding|terminal|secure grid/i.test(await page.locator('body').innerText()));
   assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false);
   for(const [id,destination,role,t] of [['home-customer','onboarding.html','lead','home'],['home-admin','market.html','operations','home'],['compute-customer','compute-home.html','gpu','compute'],['compute-admin','overview.html','fleet','compute']]) {
    const target = new URL(await page.locator('#'+id).getAttribute('href'),page.url());
    assert.equal(target.pathname,'/web/'+destination);
    assert.equal(target.searchParams.get('persona'),role);
    assert.equal(target.searchParams.get('track'),t);
   }
   const order=[];
   for(let i=0;i<5;i++){await page.keyboard.press('Tab');order.push(await page.locator(':focus').getAttribute('id'));}
   assert.deepEqual(order,['home-customer','home-member','home-admin','compute-customer','compute-admin']);
   await page.screenshot({path:path.join(shots,track+'-'+width+'.png'),fullPage:true});
  }
  for(const [track,id,role] of [['home','home-customer','lead'],['home','home-admin','operations'],['compute','compute-customer','gpu'],['compute','compute-admin','fleet']]) {
   await page.goto(origin+'/'+track);
   await page.locator('#'+id).click();
   await page.waitForSelector('.sh-nav');
   assert.equal(new URL(page.url()).searchParams.get('persona'),role);
   assert.equal(new URL(page.url()).searchParams.get('track'),track);
   assert.equal(await page.locator('#sh-persona,#sh-track').count(),0);
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: /home and /compute; root defaults to /home; 6 viewport/track cases; two track cards; keyboard order; all 4 role destinations; no JS errors.');
 } finally {
  if(browser) await browser.close();
  await new Promise(resolve=>server.close(resolve));
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
