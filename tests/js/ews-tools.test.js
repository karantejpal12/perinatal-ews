// Run: node --test tests/js/ews-tools.test.js
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

test('gestational hypertension results carry the reporting-quality caveat, other indicators do not', () => {
  const gh = D.indicators.gestational_hypertension, cav = EWS.CAVEATS.gestational_hypertension;
  assert.match(cav, /20–50%/);
  const r = tool('get_county').run(D, { fips: '25013' });
  assert.equal(r.indicators[gh].reporting_caveat, cav);
  for (const [lab, e] of Object.entries(r.indicators)) if (lab !== gh) assert.equal(e.reporting_caveat, undefined, lab);
  const s = tool('state_summary').run(D, { state: 'GA' });
  assert.deepEqual(s.reporting_caveats, { [gh]: cav });
  assert.deepEqual(tool('national_summary').run(D, {}).reporting_caveats, { [gh]: cav });
  const withGh = tool('list_counties').run(D, { filter: 'flagged', indicator: 'gestational_hypertension', limit: 100 });
  assert.ok(withGh.total_matching > 0);
  assert.deepEqual(withGh.reporting_caveats, { [gh]: cav });
  const noGh = tool('list_counties').run(D, { filter: 'flagged', indicator: 'preterm_birth', limit: 100 });
  assert.equal(noGh.reporting_caveats, undefined);
  // The caveat's figures are in the tool result, so quoting it is not reported as an unsupported number.
  assert.deepEqual(EWS.checkNumbers(`Gestational hypertension: ${cav}`, [r]), []);
});

test('persistent-burden filter lists exactly the persistent county results, most years first', () => {
  for (const k of Object.keys(D.indicators)) {
    const r = tool('list_counties').run(D, { filter: 'persistent_burden', indicator: k, limit: 100 });
    assert.equal(r.total_matching, D.persistent.persistent_counties[k], k);
    assert.ok(r.rows.every(x => x.years_in_highest_fifth >= D.persistent.min_years), k);
    for (let i = 1; i < r.rows.length; i++) assert.ok(r.rows[i - 1].years_in_highest_fifth >= r.rows[i].years_in_highest_fifth, k);
  }
});

test('county record reports persistent burden as a level over 2020-2024, separate from status', () => {
  const r = tool('get_county').run(D, { fips: '01097' });
  for (const e of Object.values(r.indicators)) {
    const p = e.persistent_burden; assert.ok(p);
    assert.equal(p.which_years.length, p.years_in_highest_fifth);
    assert.equal(p.status === 'persistent', p.years_in_highest_fifth >= D.persistent.min_years);
    assert.ok(p.which_years.every(y => y >= D.persistent.window_start && y <= D.persistent.window_end));
  }
  const n = tool('national_summary').run(D, {});
  assert.deepEqual(Object.values(n.persistently_among_highest.counties_by_indicator), Object.values(D.persistent.persistent_counties));
});

test('each list_counties filter returns exactly the county results that meet its rule', () => {
  const lc = tool('list_counties');
  const flg = e => e.level === 'alert' || e.level === 'watch';
  const sub = e => Object.values(e.subgroups || {}).some(s => s.level === 'alert' || s.level === 'watch');
  const rules = {
    flagged: (c, e) => flg(e),
    alert: (c, e) => e.level === 'alert',
    subgroup_flag: (c, e) => sub(e),
    high_next_year_risk: (c, e) => (e.risk || 0) >= 0.3,
    stable_but_high_risk: (c, e) => e.level === 'stable' && (e.risk || 0) >= 0.25,
    need_and_access: (c, e) => !!c.need && (flg(e) || sub(e) || (e.risk || 0) >= 0.3),
    higher_than_similar: (c, e) => !!(e.similar && /higher/.test(e.similar.verdict)),
    unusual_data: c => !!c.unusual,
    persistent_burden: (c, e) => !!(e.persistent && e.persistent.status === 'persistent'),
  };
  assert.deepEqual(Object.keys(rules).sort(), [...lc.input_schema.properties.filter.enum].sort());
  for (const [f, rule] of Object.entries(rules)) {
    const want = new Set();
    for (const c of D.counties) for (const [k, e] of Object.entries(c.ind)) if (rule(c, e)) want.add(`${c.id}|${D.indicators[k]}`);
    const r = lc.run(D, { filter: f, limit: 100 });
    assert.equal(r.total_matching, want.size, f);
    assert.equal(r.showing, Math.min(want.size, 100), f);
    assert.ok(r.rows.every(x => want.has(`${x.fips}|${x.indicator}`)), f);
    for (const k of Object.keys(D.indicators)) {
      const n = [...want].filter(w => w.endsWith(`|${D.indicators[k]}`)).length;
      assert.equal(lc.run(D, { filter: f, indicator: k }).total_matching, n, `${f} ${k}`);
    }
    const ga = lc.run(D, { filter: f, state: 'ga', limit: 100 });
    assert.ok(ga.rows.every(x => x.state === 'GA'), f);
    assert.equal(ga.total_matching, [...want].filter(w => D.counties.find(c => c.id === w.split('|')[0]).state === 'GA').length, f);
  }
  assert.deepEqual(lc.run(D, {}).total_matching, lc.run(D, { filter: 'flagged' }).total_matching);
  const risk = lc.run(D, { filter: 'high_next_year_risk', limit: 100 }).rows;
  for (let i = 1; i < risk.length; i++) assert.ok(risk[i - 1].next_year_risk >= risk[i].next_year_risk);
  const fl = lc.run(D, { filter: 'flagged', limit: 100 }).rows, order = { alert: 0, watch: 1 };
  for (let i = 1; i < fl.length; i++) assert.ok(order[fl[i - 1].status] <= order[fl[i].status]);
});

test('list_counties: combinations that match nothing return no rows, and unknown values are errors', () => {
  const lc = tool('list_counties');
  // Wyoming has no county of 100,000+ residents, so nothing is scored there.
  const wy = lc.run(D, { filter: 'flagged', state: 'WY' });
  assert.equal(wy.total_matching, 0); assert.deepEqual(wy.rows, []); assert.match(wy.note, /Wyoming/);
  // A real state and indicator with no match: no rows, no note, no caveat.
  const none = Object.keys(D.indicators).flatMap(k => Object.keys(EWS.STATE_NAMES).filter(s => D.counties.some(c => c.state === s))
    .map(s => ({ filter: 'alert', state: s, indicator: k }))).find(a => lc.run(D, a).total_matching === 0);
  assert.ok(none);
  const r = lc.run(D, none);
  assert.deepEqual(r, { total_matching: 0, showing: 0, rows: [] });
  for (const a of [{ filter: 'worst' }, { filter: 'alert', indicator: 'stillbirth' }, { filter: 'alert', state: 'XX' }]) {
    const e = lc.run(D, a);
    assert.ok(e.error, JSON.stringify(a)); assert.equal(e.rows, undefined);
  }
  assert.match(lc.run(D, { filter: 'worst' }).error, /persistent_burden/);
  assert.equal(lc.run(D, { filter: 'flagged', limit: 1000 }).showing, 100);
});
