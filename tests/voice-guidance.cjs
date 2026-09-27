const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'web/voice.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'web/voice.html'), 'utf8');
const cohort = JSON.parse(fs.readFileSync(path.join(root, 'house/cohort.json'), 'utf8'));
assert.match(source, /\s+start\(\);\s*\}\)\(\);\s*$/);

function harness(options = {}) {
  let document;
  let scrollCalls = 0;
  function element(tag = 'div') {
    const listeners = new Map(), attributes = new Map(), classes = new Set();
    const n = {
      tagName: tag.toUpperCase(), children: [], style: {}, disabled: false, hidden: false,
      value: '', className: '', text: '',
      get textContent() { return this.text + this.children.map(c => c.textContent || '').join(' '); },
      set textContent(text) { this.text = String(text); this.children = []; },
      append(...children) { this.children.push(...children); },
      replaceChildren(...children) {
        if (document?.activeElement !== this && this.contains(document?.activeElement)) document.activeElement = document.body;
        this.text = ''; this.children = children;
      },
      setAttribute(k, v) { attributes.set(k, String(v)); },
      getAttribute(k) { return attributes.get(k) ?? null; },
      addEventListener(k, fn) { listeners.set(k, fn); },
      emit(k, event = {}) { return listeners.get(k)?.(event); },
      focus() { document.activeElement = this; },
      scrollIntoView() { scrollCalls++; },
      contains(child) { return this === child || this.children.some(c => c.contains?.(child)); },
      classList: {toggle(k, on) { if (on) classes.add(k); else classes.delete(k); }}
    };
    return n;
  }
  const ids = ['vg-guided', 'vg-caregiver-view', 'vg-cg-list', 'vg-caregiver', 'vg-voice',
    'vg-repeat', 'vg-status', 'vg-speed', 'vg-caption'];
  const nodes = new Map(ids.map(id => [id, element()]));
  nodes.get('vg-speed').value = '0.8';
  document = {body: element('body'), activeElement: null,
    getElementById: id => nodes.get(id), createElement: element};
  document.activeElement = document.body;
  const utterances = [], recognitions = [], requests = [];
  const synth = {
    cancel() {},
    speak(u) { if (options.speechThrows) throw new Error('Speech unavailable'); utterances.push(u); }
  };
  class Recognition {
    constructor() { recognitions.push(this); }
    start() { if (options.micThrows) throw new Error('Denied'); }
    abort() { this.aborted = true; }
  }
  class MockURL extends URL {
    static createObjectURL() { return 'blob:test-photo'; }
    static revokeObjectURL() {}
  }
  const window = {};
  if (!options.noSpeech) window.speechSynthesis = synth;
  if (!options.noRecognition) window.SpeechRecognition = Recognition;
  const fetch = async (url, init) => {
    requests.push({url, init});
    if (url.includes('cohort')) return {ok: true, json: async () => cohort};
    if (url.endsWith('/api/tags')) return {ok: true, json: async () => ({models: [{name: 'gemma4:e4b'}]})};
    if (url.endsWith('/api/chat')) return {ok: options.photoHttpOk !== false,
      json: async () => ({message: {content: JSON.stringify(options.photoResult || {
        photo_type: 'panel_closed', pass: false, retake_reason: 'A clearer view is needed.', confidence: 0.6
      })}})};
    if (url.includes('pred_gemini')) return {ok: true, text: async () => JSON.stringify({
      file: '156.jpg', photo_type: 'panel_closed', pass: true, retake_reason: null, confidence: 0.8
    })};
    throw new Error(`Unexpected request: ${url}`);
  };
  const context = vm.createContext({window, document, fetch, URL: MockURL, URLSearchParams,
    location: {hostname: options.staticPage ? 'demo.test' : 'localhost', search: ''},
    localStorage: {getItem() { return null; }, setItem() {}},
    SpeechSynthesisUtterance: class { constructor(text) { this.text = text; } },
    AbortController, setTimeout, clearTimeout, performance: {now: () => 0}});
  // Expose the real closures only in the test VM; skip automatic startup for deterministic setup.
  const instrumented = source.replace(/\s+start\(\);\s*\}\)\(\);\s*$/, `
    globalThis.guideTest = {start, go, speak, listen, checkPhoto, photoSpeech, buckets,
      snapshot: () => ({voiceOn, caregiver, index, steps, photo, answers}),
      setEncoder(fn) { toBase64 = fn; }
    };
  })();`);
  vm.runInContext(instrumented, context, {filename: 'web/voice.js', timeout: 1000});
  const api = context.guideTest;
  api.setEncoder(async () => 'test-base64');
  return {...api, nodes, utterances, recognitions, requests, element, document, scrollCalls: () => scrollCalls};
}

test('initial render does not scroll past the page heading beneath the fixed nav', async () => {
  const h = harness();
  await h.start();
  assert.equal(h.scrollCalls(), 0);
  assert.equal(h.document.activeElement, h.document.body);
});

test('focused step controls transfer focus to the new heading on forward and back navigation', async () => {
  const h = harness();
  await h.start();
  const card = h.nodes.get('vg-guided');
  function findButton(node, label) {
    if (node.tagName === 'BUTTON' && node.textContent === label) return node;
    return node.children.map(child => findButton(child, label)).find(Boolean);
  }
  for (const [label, index] of [['Start', 1], ['Yes', 2], ['Go back one step', 1]]) {
    const control = findButton(card, label);
    control.focus();
    control.emit('click');
    const heading = card.children.find(node => node.tagName === 'H2');
    assert.equal(h.snapshot().index, index);
    assert.equal(h.document.activeElement, heading);
    assert.equal(heading.tabIndex, -1);
  }
  assert.equal(h.scrollCalls(), 3);
});

test('rendering a step does not steal focus or scroll when focus is outside the guide', async () => {
  const h = harness();
  await h.start();
  const control = h.nodes.get('vg-voice');
  control.focus();
  h.go(1);
  assert.equal(h.document.activeElement, control);
  assert.equal(h.scrollCalls(), 0);
});

test('speech is off at load and touch navigation never starts it implicitly', async () => {
  const h = harness();
  await h.start();
  h.go(1);
  assert.equal(h.snapshot().voiceOn, false);
  assert.equal(h.utterances.length, 0);
  assert.equal(h.nodes.get('vg-voice').getAttribute('aria-pressed'), 'false');
});

test('explicit Start voice speaks the current visible caption; Repeat repeats it', async () => {
  const h = harness();
  await h.start();
  h.nodes.get('vg-voice').emit('click');
  assert.equal(h.utterances.length, 1);
  assert.equal(h.utterances[0].text, h.nodes.get('vg-caption').textContent);
  assert.equal(h.nodes.get('vg-voice').getAttribute('aria-pressed'), 'true');
  h.nodes.get('vg-repeat').emit('click');
  assert.equal(h.utterances.length, 2);
  assert.equal(h.utterances[1].text, h.utterances[0].text);
});

test('slower and normal rates apply to explicitly started speech', async () => {
  const h = harness();
  await h.start();
  h.nodes.get('vg-voice').emit('click');
  assert.equal(h.utterances.at(-1).rate, 0.8);
  h.nodes.get('vg-speed').value = '1';
  h.nodes.get('vg-speed').emit('change');
  h.nodes.get('vg-repeat').emit('click');
  assert.equal(h.utterances.at(-1).rate, 1);
  h.nodes.get('vg-voice').emit('click');
  const before = h.utterances.length;
  h.go(1);
  assert.equal(h.utterances.length, before);
});

test('unsupported speech and recognition leave the touch flow available', async () => {
  const h = harness({noSpeech: true, noRecognition: true});
  await h.start();
  assert.equal(h.nodes.get('vg-voice').disabled, true);
  h.go(1);
  assert.match(h.nodes.get('vg-guided').textContent, /Yes.*No.*Not sure/);
  assert.ok(h.nodes.get('vg-caption').textContent.length > 0);
});

test('speech failure disables speech without breaking touch navigation or captions', async () => {
  const h = harness({speechThrows: true});
  await h.start();
  assert.doesNotThrow(() => h.nodes.get('vg-voice').emit('click'));
  assert.equal(h.snapshot().voiceOn, false);
  h.go(1);
  assert.match(h.nodes.get('vg-guided').textContent, /Yes.*No.*Not sure/);
  assert.match(h.nodes.get('vg-status').textContent, /unavailable|could not/i);
});

test('asynchronous speech errors preserve the current step and stop speech', async () => {
  const h = harness();
  await h.start();
  h.nodes.get('vg-voice').emit('click');
  assert.equal(typeof h.utterances[0]?.onerror, 'function');
  h.utterances[0].onerror({error: 'audio-busy'});
  assert.equal(h.snapshot().voiceOn, false);
  assert.equal(h.snapshot().index, 0);
});

test('caregiver mode stops voice and returning does not restart speech', async () => {
  const h = harness();
  await h.start();
  h.nodes.get('vg-voice').emit('click');
  h.nodes.get('vg-caregiver').emit('click');
  const count = h.utterances.length;
  assert.equal(h.snapshot().voiceOn, false);
  assert.equal(h.nodes.get('vg-caregiver-view').hidden, false);
  h.nodes.get('vg-caregiver').emit('click');
  h.go(1);
  assert.equal(h.utterances.length, count);
});

test('a late recognition answer cannot advance a different step', async () => {
  const h = harness();
  await h.start();
  h.go(1);
  const step = h.snapshot().steps[1];
  h.listen(h.element(), step);
  h.go(2);
  h.recognitions[0].onresult({results: [[{transcript: 'yes'}]]});
  assert.equal(h.snapshot().index, 2);
  assert.equal(h.snapshot().answers[step.id], undefined);
});

test('microphone denial leaves the same question and touch answers available', async () => {
  const h = harness({micThrows: true});
  await h.start();
  h.go(1);
  const heard = h.element();
  h.listen(heard, h.snapshot().steps[1]);
  assert.match(heard.textContent, /did not start.*button/i);
  assert.equal(h.snapshot().index, 1);
  assert.match(h.nodes.get('vg-guided').textContent, /Yes.*No.*Not sure/);
});

test('back navigation retains the earlier answer and remains available on summary', async () => {
  const h = harness();
  await h.start();
  h.go(1);
  function find(node, label) {
    if (node.tagName === 'BUTTON' && node.textContent === label) return node;
    return node.children.map(child => find(child, label)).find(Boolean);
  }
  find(h.nodes.get('vg-guided'), 'Yes').emit('click');
  assert.equal(h.snapshot().answers.address, 'yes');
  find(h.nodes.get('vg-guided'), 'Go back one step').emit('click');
  assert.equal(h.snapshot().index, 1);
  assert.equal(find(h.nodes.get('vg-guided'), 'Yes').getAttribute('aria-pressed'), 'true');
  h.go(h.snapshot().steps.length - 1);
  assert.ok(find(h.nodes.get('vg-guided'), 'Go back one step'));
});

for (const pass of ['false', 'true', 0, 1, null]) {
  test(`live photo pass=${JSON.stringify(pass)} is rejected rather than coerced`, async () => {
    const h = harness({photoResult: {photo_type: 'panel_closed', pass, retake_reason: null}});
    await h.start();
    await h.checkPhoto({}, h.element(), h.snapshot().steps.find(s => s.kind === 'photo'));
    assert.notEqual(h.snapshot().photo.mode, 'live');
    assert.doesNotMatch(h.photoSpeech(), /saved for review|will (look|call)|good enough/i);
  });
}

test('boolean false stays a live retake suggestion', async () => {
  const h = harness();
  await h.start();
  await h.checkPhoto({}, h.element(), h.snapshot().steps.find(s => s.kind === 'photo'));
  assert.equal(h.snapshot().photo.mode, 'live');
  assert.equal(h.snapshot().photo.pass, false);
  assert.match(h.photoSpeech(), /keep.*doors.*covers closed/i);
});

test('photo instructions keep covers closed and malicious model retakes never render or speak', async () => {
  const malicious = 'Open the cover and touch exposed wires UNSAFE_MODEL_TEXT';
  const h = harness({photoResult: {photo_type: 'panel_closed', pass: false, retake_reason: malicious}});
  await h.start();
  const index = h.snapshot().steps.findIndex(s => s.kind === 'photo');
  h.go(index);
  assert.match(h.nodes.get('vg-guided').textContent, /keep.*doors.*covers closed/i);
  h.nodes.get('vg-voice').emit('click');
  const host = h.element();
  await h.checkPhoto({}, host, h.snapshot().steps[index]);
  const rendered = h.nodes.get('vg-guided').textContent;
  for (const text of [rendered, h.photoSpeech(), h.nodes.get('vg-caption').textContent, ...h.utterances.map(u => u.text)]) {
    assert.doesNotMatch(text, /UNSAFE_MODEL_TEXT|touch exposed wires/);
  }
  assert.match(rendered, /skip.*unsafe/i);
  const request = JSON.parse(h.requests.find(r => r.url.endsWith('/api/chat')).init.body);
  assert.match(request.messages[0].content, /framing.*clarity/i);
  assert.doesNotMatch(request.messages[0].content, /could size the battery/);
});

test('boolean true remains an unverified suggestion, never installation approval', async () => {
  const h = harness({photoResult: {photo_type: 'panel_closed', pass: true, retake_reason: null}});
  await h.start();
  await h.checkPhoto({}, h.element(), h.snapshot().steps.find(s => s.kind === 'photo'));
  assert.equal(h.snapshot().photo.mode, 'live');
  assert.match(h.photoSpeech(), /not.*approval|unverified/i);
  assert.equal(h.buckets().confirmed.some(text => text.startsWith('Panel photo:')), false);
});

test('failed HTTP photo response cannot become a live successful check', async () => {
  const h = harness({photoHttpOk: false, photoResult: {photo_type: 'panel_closed', pass: true, retake_reason: null}});
  await h.start();
  await h.checkPhoto({}, h.element(), h.snapshot().steps.find(s => s.kind === 'photo'));
  assert.notEqual(h.snapshot().photo.mode, 'live');
});

test('hosted photo preview makes no photo requests and promises neither review nor callback', async () => {
  const h = harness({staticPage: true});
  await h.start();
  const before = h.requests.length;
  await h.checkPhoto({}, h.element(), h.snapshot().steps.find(s => s.kind === 'photo'));
  assert.equal(h.snapshot().photo.mode, 'preview');
  assert.equal(h.requests.length, before);
  assert.match(h.photoSpeech(), /preview only/i);
  assert.match(h.photoSpeech(), /not analyzed, saved, or submitted/i);
  assert.doesNotMatch(h.photoSpeech(), /saved for review|will look|will call/i);
  h.go(h.snapshot().steps.length - 1);
  assert.doesNotMatch(h.nodes.get('vg-guided').textContent, /will call|will check|saved for review/i);
  assert.match(h.nodes.get('vg-guided').textContent, /No.*(review|callback)|not.*submitted/i);
  assert.equal(h.requests.some(r => r.url.includes('localhost:11434')), false);
});

test('failed local photo check retains explicitly unrelated recorded fallback', async () => {
  const h = harness({photoHttpOk: false});
  await h.start();
  const index = h.snapshot().steps.findIndex(s => s.kind === 'photo');
  h.go(index);
  await h.checkPhoto({}, h.element(), h.snapshot().steps[index]);
  assert.equal(h.snapshot().photo.mode, 'recorded');
  assert(h.requests.some(r => r.url.endsWith('/api/chat')));
  assert(h.requests.some(r => r.url.includes('pred_gemini')));
  assert.match(h.photoSpeech(), /unrelated sample/i);
  assert.match(h.nodes.get('vg-guided').textContent, /not your photo/i);
  assert.equal(h.buckets().confirmed.some(text => text.startsWith('Panel photo:')), false);
  h.go(h.snapshot().steps.length - 1);
  assert.doesNotMatch(h.nodes.get('vg-guided').textContent, /will call|will check|saved for review/i);
  assert.match(h.nodes.get('vg-guided').textContent, /No.*(review|callback)/i);
});

test('HTML has labeled speed selection and honest optional browser-voice copy', () => {
  assert.match(html, /<label[^>]*for="vg-speed"/);
  assert.match(html, /<option[^>]*value="0\.8"[^>]*>Slower/);
  assert.match(html, /<option[^>]*value="1"[^>]*>Normal/);
  assert.match(html, /id="vg-caption"/);
  assert.match(html, /browser speech|browser voice/i);
  assert.doesNotMatch(html, /Each step is spoken out loud|Answers stay in this browser/);
});
