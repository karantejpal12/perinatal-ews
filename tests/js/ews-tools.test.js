// Run: node --test tests/js/
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const EWS = require('../../js/ews-tools.js');
const D = JSON.parse(fs.readFileSync(path.join(__dirname, '../../results/2024/explorer.json'), 'utf8'));
const tool = n => EWS.TOOLS.find(t => t.name === n);

test('every tool runs and returns JSON-serialisable output', () => {
  const args = { search_counties: { query: 'Hampden, MA' }, get_county: { fips: '25013' }, list_counties: { filter: 'alert', state: 'GA' },
    state_summary: { state: 'ga' }, national_summary: {}, method_info: { topic: 'forecast' } };
  for (const t of EWS.TOOLS) assert.doesNotThrow(() => JSON.stringify(t.run(D, args[t.name])), t.name);
});

test('county lookup and brief use the published numbers', () => {
  const r = tool('get_county').run(D, { fips: '25013' });
  assert.equal(r.county, 'Hampden County');
  assert.match(r.plain_language_brief, /statistical flags for local follow-up/);
  assert.deepEqual(EWS.checkNumbers(r.plain_language_brief, [r]), []);
});

test('state summary counts match list_counties', () => {
  const s = tool('state_summary').run(D, { state: 'PA' });
  const alerts = Object.values(s.by_indicator).reduce((a, b) => a + b.alerts, 0);
  assert.equal(alerts, tool('list_counties').run(D, { filter: 'alert', state: 'PA', limit: 100 }).total_matching);
  assert.deepEqual(EWS.checkNumbers(s.plain_language_brief, [s]), []);
});

test('number checker flags invented figures but accepts real ones', () => {
  const r = tool('get_county').run(D, { fips: '13121' });
  const e = Object.values(r.indicators)[0];
  const ok = `The rate was ${(100 * e.rate).toFixed(1)}% in 2024.`;
  assert.deepEqual(EWS.checkNumbers(ok, [r]), []);
  assert.deepEqual(EWS.checkNumbers('The rate was 87.3% and 4,321 extra births.', [r]), ['87.3%', '4,321']);
});

test('unknown county returns an error, not a guess', () => {
  assert.ok(tool('get_county').run(D, { fips: '99999' }).error);
});

test('county names resolve with or without "County"', () => {
  assert.equal(EWS.findCounty(D, 'Fulton, GA').id, '13121');
  assert.equal(EWS.findCounty(D, 'fulton county, ga').id, '13121');
});

test('a figure close to a real value but not equal after rounding is flagged', () => {
  assert.deepEqual(EWS.checkNumbers('ratio 87.3%', [{ v: 0.871 }]), ['87.3%']);
  assert.deepEqual(EWS.checkNumbers('ratio 87.1%', [{ v: 0.871 }]), []);
});

test('every county and state brief contains only figures found in the data', () => {
  const get = EWS.TOOLS.find(t => t.name === 'get_county'), st = EWS.TOOLS.find(t => t.name === 'state_summary');
  for (const c of D.counties) {
    const r = get.run(D, { fips: c.id });
    assert.deepEqual(EWS.checkNumbers(r.plain_language_brief, [r]), [], c.id);
  }
  for (const s of new Set(D.counties.map(c => c.state))) {
    const r = st.run(D, { state: s });
    assert.deepEqual(EWS.checkNumbers(r.plain_language_brief, [r]), [], s);
  }
});

test('rate intervals match the Python Wilson interval and mark fewer than 20 events unstable', () => {
  const a = EWS.rateInterval(0.0587, 3391);  // 199 events; Python wilson_interval(199, 3391) = 0.051262, 0.067106
  assert.equal(a.events, 199);
  assert.ok(Math.abs(a.lo - 0.051262) < 1e-5 && Math.abs(a.hi - 0.067106) < 1e-5);
  assert.equal(a.unstable, false);
  const b = EWS.rateInterval(0.012, 1000);
  assert.equal(b.events, 12);
  assert.equal(b.unstable, true);
  assert.ok(Math.abs(b.lo - 0.0068777) < 1e-5 && Math.abs(b.hi - 0.0208573) < 1e-5);
  assert.equal(EWS.rateInterval(null, 1000), null);
  assert.equal(EWS.rateInterval(0.05, 0), null);
});

test('every county rate gets an interval that contains it', () => {
  for (const c of D.counties) for (const e of Object.values(c.ind)) {
    if (e.rate == null) continue;
    const ci = EWS.rateInterval(e.rate, e.births);
    assert.ok(ci.lo <= e.rate + 1e-4 && e.rate - 1e-4 <= ci.hi, c.id);
    assert.ok(ci.events >= 10, c.id);  // rates on fewer than 10 events are not published
  }
});

test('state summary reports counties not covered, and a state with no flags says no flag is not no concern', () => {
  const s = tool('state_summary').run(D, { state: 'NH' });
  assert.equal(s.counties_in_state, 10);
  assert.equal(s.counties_not_scored, 10 - s.counties);
  assert.match(s.plain_language_brief, /not reported separately by CDC WONDER/);
  assert.match(s.plain_language_brief, /does not mean there is no concern/);
  for (const st of new Set(D.counties.map(c => c.state))) {
    assert.ok(EWS.COUNTIES_IN_STATE[st] >= D.counties.filter(c => c.state === st).length, st);
  }
  assert.equal(Object.values(EWS.COUNTIES_IN_STATE).reduce((a, b) => a + b, 0), 3143);
});
