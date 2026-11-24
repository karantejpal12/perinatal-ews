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
  // A state with no flag on any indicator says that no flag is not the same as no concern.
  const flagged = new Set(D.counties.filter(c => Object.values(c.ind).some(e => e.level === 'alert' || e.level === 'watch')).map(c => c.state));
  const quiet = [...new Set(D.counties.map(c => c.state))].find(st => !flagged.has(st));
  if (quiet) assert.match(tool('state_summary').run(D, { state: quiet }).plain_language_brief, /does not mean there is no concern/);
  else {
    const t = { ...D, counties: D.counties.filter(c => c.state === 'NH').map(c => ({ ...c, ind: Object.fromEntries(Object.entries(c.ind).map(([k, e]) => [k, { ...e, level: 'stable' }])) })) };
    assert.match(tool('state_summary').run(t, { state: 'NH' }).plain_language_brief, /does not mean there is no concern/);
  }
  for (const st of new Set(D.counties.map(c => c.state))) {
    assert.ok(EWS.COUNTIES_IN_STATE[st] >= D.counties.filter(c => c.state === st).length, st);
  }
  assert.equal(Object.values(EWS.COUNTIES_IN_STATE).reduce((a, b) => a + b, 0), 3143);
});

test('each indicator carries its own reporting caveat, and the four without one carry none', () => {
  const gh = D.indicators.gestational_hypertension, cav = EWS.CAVEATS.gestational_hypertension;
  assert.match(cav, /20–50%/);
  const r = tool('get_county').run(D, { fips: '25013' });
  assert.equal(r.indicators[gh].reporting_caveat, cav);
  const keyOf = Object.fromEntries(Object.entries(D.indicators).map(([k, l]) => [l, k]));
  for (const [lab, e] of Object.entries(r.indicators)) assert.equal(e.reporting_caveat, EWS.CAVEATS[keyOf[lab]], lab);
  const all = Object.fromEntries(Object.keys(D.indicators).filter(k => EWS.CAVEATS[k]).map(k => [D.indicators[k], EWS.CAVEATS[k]]));
  const s = tool('state_summary').run(D, { state: 'GA' });
  assert.deepEqual(s.reporting_caveats, all);
  assert.deepEqual(tool('national_summary').run(D, {}).reporting_caveats, all);
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

test('count indicators (per population) use exact Poisson intervals and are shown per 1,000', () => {
  // scipy: gamma.ppf(0.025, 100) / 1000, gamma.ppf(0.975, 101) / 1000 (as tests/test_count_pooling.py)
  const a = EWS.poissonInterval(0.1, 1000);
  assert.equal(a.events, 100);
  assert.ok(Math.abs(a.lo - 0.081364) < 1e-6 && Math.abs(a.hi - 0.121627) < 1e-6);
  const b = EWS.poissonInterval(0.012, 1000);  // gamma.ppf(0.025, 12), gamma.ppf(0.975, 13)
  assert.equal(b.unstable, true);
  assert.ok(Math.abs(b.lo - 0.0062006) < 1e-6 && Math.abs(b.hi - 0.0209616) < 1e-6);
  const c = EWS.poissonInterval(1.4, 30000);  // rates above 1 are not capped
  assert.ok(c.lo > 1 && c.hi > c.lo && Math.abs(c.hi - 1.4134541) < 1e-6);
  const z = EWS.poissonInterval(0, 500);
  assert.equal(z.lo, 0);
  assert.ok(Math.abs(z.hi - 0.0073778) < 1e-6);
  assert.equal(EWS.poissonInterval(null, 1000), null);
  assert.equal(EWS.poissonInterval(0.01, 0), null);

  const T = { ...D, count_indicators: ['teen_birth_rate'] };
  assert.equal(EWS.isCountIndicator(T, 'teen_birth_rate'), true);
  assert.equal(EWS.isCountIndicator(T, 'preterm_birth'), false);
  assert.equal(EWS.formatRate(T, 'teen_birth_rate', 0.0135), '13.5 per 1,000');
  assert.equal(EWS.formatRate(T, 'preterm_birth', 0.105), '10.5%');
  assert.equal(EWS.denominatorWord(T, 'teen_birth_rate'), 'population');
  assert.deepEqual(EWS.indicatorInterval(T, 'teen_birth_rate', 0.1, 1000), a);
  assert.deepEqual(EWS.indicatorInterval(T, 'preterm_birth', 0.0587, 3391), EWS.rateInterval(0.0587, 3391));
  // The published file has no count indicators: every rate stays a percentage of births.
  for (const k of Object.keys(D.indicators)) assert.equal(EWS.isCountIndicator(D, k), false, k);
});

test('intervals are written once with their unit', () => {
  const T = { ...D, count_indicators: ['teen_birth_rate'] };
  assert.equal(EWS.formatRange(T, 'teen_birth_rate', 0.0895, 0.1078), '89.5–107.8 per 1,000');
  assert.equal(EWS.formatRange(T, 'preterm_birth', 0.09, 0.107), '9.0%–10.7%');
});

test('alert list, map tooltips and state-wide patterns keep percentages for the published file', () => {
  // The explorer formats these with formatRate (missing values are written '–' in app.html before it is called);
  // with no count indicators every value must match the old percentages.
  const pct = x => (100 * x).toFixed(1) + '%';
  for (const c of D.counties) for (const [k, e] of Object.entries(c.ind)) {
    if (e.rate != null) assert.equal(EWS.formatRate(D, k, e.rate), pct(e.rate), `${c.id} ${k}`);
    if (e.similar && e.similar.expected != null) assert.equal(EWS.formatRate(D, k, e.similar.expected), pct(e.similar.expected));
  }
  for (const p of D.state_patterns || []) assert.equal(EWS.formatRate(D, p.indicator, p.rate_now), pct(p.rate_now));
  // A state-wide pattern whose indicator is not found falls back to a percentage rather than failing.
  const T = { ...D, count_indicators: ['teen_birth_rate'] };
  assert.equal(EWS.formatRate(T, undefined, 0.3467), '34.7%');
  assert.equal(EWS.formatRate(T, 'teen_birth_rate', 0.0219), '21.9 per 1,000');
});

test('assistant tools and briefs give count indicators per 1,000 population and keep shares of births unchanged', () => {
  // Synthetic: a copy of the published file with a teen birth rate (per female aged 15-19) added to two GA counties.
  const T = JSON.parse(JSON.stringify(D));
  T.count_indicators = ['teen_birth_rate'];
  T.indicators.teen_birth_rate = 'Teen birth rate';
  const ga = T.counties.filter(c => c.state === 'GA').slice(0, 2);
  ga[0].ind.teen_birth_rate = { trend: T.years.map(() => 0.0152), level: 'alert', rate: 0.0219, expected: 0.0161, rr: 1.36, births: 41250,
    excess: 239, sustained: false, subgroups: {}, similar: { rate: 0.0201, expected: 0.0148, low: 0.009, high: 0.0189, verdict: 'higher than similar counties' } };
  ga[1].ind.teen_birth_rate = { trend: T.years.map(() => 0.0105), level: 'stable', rate: 0.0108, expected: 0.0111, rr: 0.97, births: 28800, excess: -9, sustained: false };
  T.state_patterns = [...(T.state_patterns || []), { indicator: 'teen_birth_rate', state: 'GA', flagged: 2, counties: 2, rate_before: 0.0154, rate_now: 0.0187 }];
  T.latest = { ytd_label: 'January–June 2026', latest_month_available: '2026-06', updated: '2026-11-01', count_indicators: ['teen_birth_rate'],
    states_data: { GA: { ind: { preterm_birth: { level: 'watch', rate: 0.1162, expected: 0.1101, rr: 1.055, births: 61000 },
      teen_birth_rate: { level: 'alert', rate: 0.0193, expected: 0.0164, rr: 1.18, births: 165000, full_year_rate: 0.0171,
        outlook: { proj: 0.0189, lo: 0.0181, hi: 0.0197, p_flag: 0.9, p_alert: 0.7 } } } } } };

  const r = tool('get_county').run(T, { fips: ga[0].id });
  const e = r.indicators['Teen birth rate'];
  assert.equal(e.rate, 21.9); assert.equal(e.expected_rate, 16.1);
  assert.equal(e.population, 41250); assert.equal(e.births, undefined);
  assert.match(e.rate_unit, /per 1,000 population/);
  assert.equal(e.compared_with_similar_counties.expected, 14.8);
  assert.equal(e.rates_by_year[T.years[0]], 15.2);
  assert.match(r.plain_language_brief, /teen birth rate \(alert: 21\.9 per 1,000 against 16\.1 per 1,000 expected\)/);
  assert.match(r.plain_language_brief, /is higher \(20\.1 per 1,000 vs 14\.8 per 1,000\)/);
  assert.deepEqual(EWS.checkNumbers(r.plain_language_brief, [r]), []);
  // Shares of births in the same county are unchanged: proportions, with births as the denominator.
  const pb = r.indicators[T.indicators.preterm_birth], orig = ga[0].ind.preterm_birth;
  assert.equal(pb.rate, orig.rate); assert.equal(pb.births, orig.births); assert.equal(pb.rate_unit, undefined);

  const lc = tool('list_counties').run(T, { filter: 'alert', indicator: 'teen_birth_rate' });
  assert.equal(lc.rows[0].rate, 21.9); assert.equal(lc.rows[0].expected_rate, 16.1); assert.match(lc.rows[0].rate_unit, /population/);
  assert.equal(lc.rows[0].key, undefined);

  const s = tool('state_summary').run(T, { state: 'GA' });
  const p = s.statewide_patterns.find(q => q.indicator === 'Teen birth rate');
  assert.equal(p.state_rate_now, 18.7); assert.match(p.rate_unit, /per 1,000/);
  const y = s.year_to_date_provisional.indicators;
  assert.equal(y['Teen birth rate'].rate, 19.3); assert.equal(y['Teen birth rate'].population, 165000);
  assert.equal(y['Teen birth rate'].outlook.hi, 19.7); assert.equal(y['Teen birth rate'].outlook.p_flag, 0.9);
  assert.equal(y[T.indicators.preterm_birth].rate, 0.1162);
  assert.match(s.plain_language_brief, /state rate 15\.4 per 1,000 at baseline, 18\.7 per 1,000 now/);
  assert.match(s.plain_language_brief, /teen birth rate alert \(19\.3 per 1,000 vs 16\.4 per 1,000 expected\)/);
  assert.match(s.plain_language_brief, /preterm birth watch \(11\.6% vs 11\.0% expected\)/);
  assert.deepEqual(EWS.checkNumbers(s.plain_language_brief, [s]), []);

  // The figure check accepts rates per 1,000 that are in the results, and still catches invented ones.
  assert.deepEqual(EWS.checkNumbers(`The teen birth rate was 21.9 per 1,000 against 16.1 per 1,000 expected.`, [r]), []);
  assert.deepEqual(EWS.checkNumbers(`The teen birth rate was 24.6 per 1,000.`, [r]), ['24.6']);
});

test('assistant tool results for the published file have no count-indicator fields', () => {
  for (const c of D.counties.slice(0, 50)) for (const e of Object.values(tool('get_county').run(D, { fips: c.id }).indicators)) {
    assert.equal(e.rate_unit, undefined); assert.equal(e.population, undefined);
  }
  for (const row of tool('list_counties').run(D, { filter: 'flagged', limit: 100 }).rows) assert.equal(row.key, undefined);
});
