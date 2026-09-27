const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/Users/red/.agents/skills/gstack/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const replay = JSON.parse(fs.readFileSync(path.join(root, 'web/data/tower_replay.json')));
let checks = 0;
const check = (ok, message) => { assert.ok(ok, message); checks++; };
(async () => {
  const browser = await chromium.launch();
  try {
    for (const width of [1440, 390]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      const page = await context.newPage();
      page.setDefaultTimeout(5000);
      const errors = [], posts = [], mutations = [], externalRequests = [];
      let live = false, rejectJob = false, replayFailure = null;
      page.on('pageerror', error => errors.push(error.message));
      await context.route('**/*', async route => {
        const req = route.request(), url = new URL(req.url());
        if (!['GET', 'HEAD'].includes(req.method())) mutations.push(url.pathname);
        if (url.origin !== 'http://compute.test') { externalRequests.push(req.url()); return route.abort(); }
        if (url.pathname.endsWith('/tower_replay.json') && replayFailure) {
          return route.fulfill({ status: replayFailure === 'missing' ? 404 : 200,
            contentType: 'application/json', body: replayFailure === 'malformed' ? '{' : '{"frames":[]}' });
        }
        if (url.pathname === '/state') return route.fulfill({ json: replay.frames[0] });
        if (url.pathname.startsWith('/node/')) return route.fulfill({ json: { jobs: [] } });
        if (url.pathname === '/jobs') {
          posts.push(req.postDataJSON());
          return route.fulfill({ status: rejectJob ? 503 : 200, json: rejectJob ? { error: 'unavailable' } : { id: 42, rate: 1.2 } });
        }
        const file = path.resolve(root, '.' + url.pathname);
        if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return route.fulfill({ status: 404, body: '' });
        const type = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png' }[path.extname(file)] || 'text/plain';
        return route.fulfill({ contentType: type, headers: live ? { 'x-content-type-options': 'nosniff' } : {}, body: req.method() === 'HEAD' ? '' : fs.readFileSync(file) });
      });
      const open = async file => { await page.goto('http://compute.test/web/' + file); await page.waitForTimeout(350); };
      const layout = async name => {
        check(await page.locator('.sh-nav').count() === 1, name + ' shell');
        check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), name + ' overflow');
        if (process.env.SCREENSHOT_DIR) {
          fs.mkdirSync(process.env.SCREENSHOT_DIR, { recursive: true });
          await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, `${name}-${width}.png`), fullPage: true });
        }
      };
      await open('tower.html?node=3&track=compute&persona=gpu');
      await page.waitForFunction(() => document.querySelector('#banner')?.textContent === 'Recorded data');
      check(await page.locator('h1').innerText() === 'Your compute', 'Customer heading');
      check(!/sample|simulation|demo/i.test(await page.locator('.sh-foot').innerText()), 'No repeated sidebar disclaimer');
      check(await page.locator('#m-run').innerText() === 'Run job', 'Product action label');
      check(await page.locator('#ops').isHidden(), 'Fleet controls hidden from node view');
      check(await page.locator('#m-run').isDisabled(), 'Recorded job action disabled');
      check(/grid page shows public ERCOT data, and this simulator runs on its own/.test(await page.locator('.support').first().textContent()), 'Grid and simulator boundary explicit');
      check(await page.locator('#member h2').first().innerText() === 'Node availability', 'Compute first, not battery');
      check(await page.locator('#m-neighbors a').count() > 0, 'Keyboard-accessible neighbors');
      await page.locator('#replay-toggle').click();
      const pausedClock = await page.locator('#clock').innerText();
      await page.waitForTimeout(900);
      check(await page.locator('#clock').innerText() === pausedClock, 'Recorded frame stays paused for inspection');
      await page.locator('#m-next-workload').click();
      check(/Recorded workload/.test(await page.locator('#m-jobs-title').innerText()), 'Recorded work is not claimed as customer job history');
      check(/job/.test(await page.locator('#m-jobs').innerText()), 'Next workload displays actual recorded job evidence');
      check(await page.locator('#m-run').isDisabled(), 'Inspecting recorded work never enables submission');
      const at = await page.evaluate(() => lastState.t);
      const recordedJob = replay.frames.find(f => f.t === at).nodes.find(n => n.id === 3).job;
      check((await page.locator('#m-jobs').innerText()).includes(recordedJob.id), 'Displayed job ID comes from selected frame');
      check(new URL(await page.locator('#m-neighbors a').first().getAttribute('href'), page.url()).searchParams.get('hour') === String(at), 'Neighbor inspection preserves recorded hour');
      check(await page.locator('#replay-evidence').getAttribute('href') === 'data/tower_replay.json', 'Recorded evidence accessible');
      await layout('tower-customer');
      await open('tower.html?node=4&track=compute&persona=gpu&hour=0');
      check(/No job on this node at recorded hour 0/.test(await page.locator('#m-jobs').innerText()), 'Empty recorded workload is explicit');
      await page.locator('#m-next-workload').click();
      check(await page.evaluate(() => !!lastState.nodes.find(n => n.id === 4).job), 'Empty-state action finds actual recorded work');
      await open('tower.html?track=compute&persona=fleet');
      check(await page.locator('h1').innerText() === 'Break it and watch it recover.', 'Admin heading');
      check(await page.locator('#member').isHidden(), 'Node view hidden from admin');
      await page.locator('[data-kind=node]').click();
      const kill = replay.kills.find(k => k.kind === 'node');
      check(await page.evaluate(() => lastState.t) === kill.t, 'Recorded failure jumps to exact event');
      await page.waitForTimeout(900);
      check(await page.evaluate(() => lastState.t) === kill.t, 'Failure evidence remains paused');
      check(await page.locator('#region').isDisabled(), 'Recorded region selector cannot imply a new chosen failure');
      check((await page.locator('#recovery-note').innerText()).includes(String(kill.target)), 'Failure target is explicit');
      const inspect = page.locator(`#feeders a[aria-label="Inspect node ${kill.target}"]`);
      await inspect.click();
      await page.waitForFunction(() => document.querySelector('#banner')?.textContent === 'Recorded data');
      check(await page.evaluate(() => lastState.t) === kill.t, 'Fleet-to-node navigation preserves failure evidence');
      check(await page.locator('#m-gpu').innerText() === 'Offline', 'Interrupted node displays recorded offline state');
      await page.locator('#nav-ops').click();
      await page.waitForFunction(() => document.querySelector('#banner')?.textContent === 'Recorded data');
      check(await page.evaluate(() => lastState.t) === kill.t, 'Return to fleet preserves frame');
      await page.locator('[data-kind=node]').click();
      await page.locator('#replay-next').click();
      check(await page.evaluate(() => lastState.t) === kill.t + 1, 'Step advances one recorded hour');
      await page.locator('#replay-next').click();
      await page.locator('#replay-next').click();
      check(await page.evaluate(id => lastState.nodes.find(n => n.id === id).alive, kill.target), 'Recorded node recovery visible three hours later');
      check((await page.locator('#recovery-note').innerText()).includes(`Viewing hour ${kill.t + 3}`), 'Selected-event note follows current viewed hour');
      check(mutations.length === 0, 'Recorded inspection never submits mutations');
      for (const file of ['placement.html', 'index.html', 'grid.html']) {
        const href = await page.locator(`#ops a[href^="${file}"]`).getAttribute('href');
        check(new URL(href, page.url()).searchParams.get('persona') === 'fleet', 'Supporting action retains fleet role: ' + file);
      }
      await layout('tower-admin');
      live = true;
      await open('tower.html?node=3&track=compute&persona=gpu');
      await page.waitForFunction(() => !document.querySelector('#m-run').disabled);
      await page.locator('#m-run').click();
      await page.waitForFunction(() => document.querySelector('#m-out').textContent.includes('42'));
      check(posts.at(-1).origin === 3 && posts.at(-1).tier === 'member', 'Existing member API contract');
      rejectJob = true;
      await page.locator('#m-run').click();
      await page.waitForFunction(() => document.querySelector('#m-out').textContent.includes('not confirmed'));
      check(await page.locator('#m-run').isEnabled(), 'Failed submission can retry');
      live = false;
      await open('tower.html?node=9999&track=compute&persona=gpu');
      check(await page.locator('#m-run').isDisabled(), 'Unknown node cannot submit');
      check(/not found/i.test(await page.locator('#m-gpu').innerText()), 'Unknown node clear state');
      check(await page.locator('#m-fleet-link').isVisible(), 'Unknown node has fleet return link');
      check(await page.locator('#m-next-workload').isDisabled(), 'Unknown node cannot inspect invented workloads');
      for (const failure of ['missing', 'malformed', 'empty']) {
        replayFailure = failure;
        await open('tower.html?track=compute&persona=fleet');
        await page.waitForFunction(() => document.querySelector('#banner').textContent.includes('Data could not load'));
        check(await page.locator('#j-go').isDisabled(), failure + ' recording cannot enable submission');
        check(await page.locator('[data-kind=node]').isDisabled(), failure + ' recording cannot enable failure replay');
        check(await page.locator('#replay-controls').isHidden(), failure + ' recording hides unusable playback');
      }
      replayFailure = null;
      await open('member.html');
      await page.waitForFunction(() => document.querySelector('#ans .big'));
      const data = JSON.parse(fs.readFileSync(path.join(root, 'data/members.json')));
      const member = (Array.isArray(data) ? data : data.members).find(m => m.member_id === 'm001');
      check((await page.locator('#ans .big').innerText()).startsWith('$' + member.totals.battery_usd.toFixed(2)), 'Home summary is battery only');
      check(!/GPU|PC beside/i.test(await page.locator('#ans').innerText()), 'Compute not mixed into home headline');
      await page.locator('#chips button').first().click();
      await page.waitForSelector('#answers .answer');
      check(await page.locator('.ask').isHidden(), 'Hosted live form is hidden');
      await page.evaluate(() => ask('A new battery question'));
      check(/only when this page runs locally/.test(await page.locator('#answers .answer').first().innerText()), 'Hosted local-model boundary');
      check(!externalRequests.some(url => /localhost|127\.0\.0\.1|11434/.test(url)), 'Hosted member makes no localhost request');
      await layout('member');
      await open('index.html');
      await page.waitForSelector('#chips button');
      check(/public ERCOT prices/.test(await page.locator('#lede').innerText()), 'Economics identifies public price inputs');
      await page.locator('#chips button').nth(1).click();
      await page.locator('#play').click();
      check(await page.locator('#money').isHidden(), 'Economics supporting detail collapsed');
      await layout('fleet');
      await open('grid.html');
      await page.waitForFunction(() => !document.querySelector('#a-now').textContent.includes('loading'));
      check(/At snapshot time/.test(await page.locator('#a-now').innerText()), 'Grid observation is timestamped snapshot, not live now');
      check(/tower fleet runs on its own simulator/.test(await page.locator('#lede').innerText()), 'Grid does not claim tower control');
      check(await page.locator('#detail').evaluate(d => !d.open), 'ERCOT grid detail collapsed');
      check(/2025/.test(await page.locator('#a-earn').innerText()), 'Stitch answer cards show modeled 2025 earnings');
      await layout('grid');
      await open('placement.html');
      await page.locator('#btn-homes').click();
      check(await page.locator('#btn-homes').getAttribute('aria-pressed') === 'true', 'Placement policy control');
      check(await page.locator('#c').evaluate(c => { const p = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; return p.some((v, i) => i % 4 !== 3 && v !== p[i % 4]); }), 'Placement nonblank');
      await layout('placement');
      check(errors.length === 0, 'Runtime errors: ' + errors.join('; '));
      await context.close();
    }
    console.log(`PASS: ${checks} focused compute checks (live API responses mocked)`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
