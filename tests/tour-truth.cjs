const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const data = JSON.parse(read('web/data/tours.json'));
const docs = ['VIDEO.md'];
const roles = {
  lead: ['home', ['onboarding.html#home', 'voice.html', 'brain.html', 'member.html', 'knowledge.html']],
  operations: ['home', ['market.html', 'house.html', 'explorer.html', 'admin.html']],
  gpu: ['compute', ['block.html', 'brain.html', 'knowledge.html']],
  fleet: ['compute', ['tower.html', 'placement.html', 'index.html', 'grid.html']]
};

test('all legacy tour IDs remain unique and usable', () => {
  assert.deepEqual(data.tours.map(t => t.id).sort(),
    ['lead', 'older-house', 'member', 'small-business', 'base-ops', 'fleet', 'block-host', 'judge'].sort());
  for (const tour of data.tours) {
    assert(tour.label && tour.chip && tour.story && tour.stops.length >= 2);
    assert.equal(new Set(tour.stops.map(s => s.page)).size, tour.stops.length);
  }
});

for (const tour of data.tours) {
  test(`${tour.id}: compatible pages, declared role and existing evidence`, () => {
    const [track, pages] = roles[tour.persona];
    assert.equal(tour.track, track);
    for (const stop of tour.stops) {
      assert(pages.includes(stop.page), `${tour.id}: wrong-role stop ${stop.page}`);
      // The current shell requires a bare page/hash, not a query-bearing stop.
      assert.match(stop.page, /^[a-z-]+\.html(?:#home)?$/);
      assert(fs.statSync(path.join(root, 'web', stop.page.split('#')[0])).isFile());
      assert(stop.headline.length > 20);
      assert.match(stop.number.source, /^(?:web|data|house)\/[\w./-]+$/);
      assert(!stop.number.source.includes('..'));
      assert(fs.statSync(path.join(root, stop.number.source)).isFile());
      if (stop.number.source.endsWith('.json')) JSON.parse(read(stop.number.source));
      assert(!/\d|\$|%/.test(stop.number.value), 'Unverified numerical result in badge');
      assert.match(stop.number.value, /Public|Recorded|Guidance|Indexed|Example|Aggregate|Modeled|Simulation/);
    }
  });
}

test('metadata declares every legacy tour role explicitly without unused overrides', () => {
  const expected = {lead: 'lead', member: 'lead', 'older-house': 'operations',
    'base-ops': 'operations', judge: 'operations', 'small-business': 'gpu',
    fleet: 'fleet', 'block-host': 'fleet'};
  for (const tour of data.tours) {
    assert.equal(tour.persona, expected[tour.id]);
    for (const stop of tour.stops) {
      assert(!Object.hasOwn(stop, 'track'));
      assert(!Object.hasOwn(stop, 'persona'));
    }
  }
});

test('retired pitch overclaims cannot silently return', () => {
  const text = JSON.stringify(data) + docs.map(f => read('docs/' + f)).join('\n');
  for (const phrase of [
    /the limit is (?:the path|not demand)/i,
    /the public record agrees/i,
    /the photo only confirms/i,
    /its customer data stays in the zip/i,
    /zero jobs lost, back in one interval/i,
    /every node holds its last action and its 30 percent/i,
    /no cloud model in the path/i,
    /all pages on 8741 load from local files/i,
    /sample houses are easy fits/i
  ]) assert(!phrase.test(text), `Retired claim: ${phrase}`);
});

test('critical truth boundaries are explicit, not just implied by sources', () => {
  assert.match(read('docs/VIDEO.md'), /run in simulation; no real GPU jobs run yet/);
});

// These static checks protect the script contract, not model correctness,
// source methodology, browser navigation, or deployed-service availability.
