// Fetch the added maternal and child health indicators, and state results by Hispanic origin and
// by payer, from CDC WONDER (Natality, 2016-2024 expanded).
//
// How to use:
// 1. Open https://wonder.cdc.gov/natality-expanded-current.html, read the data use restrictions
//    and click "I Agree". You must follow those terms, including never publishing counts of 9 or fewer.
// 2. On the request form, open the browser's developer console and paste this whole file.
//    It first finds every variable it needs on the form by its name and stops, listing what is
//    missing, if any is not found. Set `window.PEWS_DRYRUN = true` before pasting to see the
//    variables and categories it would use without running any query.
// 3. It then runs about 125 queries, pausing between them (20-30 minutes in all), and downloads two CSV
//    files in the tidy schema. Keep the tab open; `window.PEWS_STATUS` shows progress:
//    - cdc_wonder_natality_county_more_2016_2024_tidy.csv: the six added indicators by county and
//      year, for all births and for Medicaid and private-insurance births;
//    - cdc_wonder_natality_state_groups_2016_2024.csv: every indicator by state and year, by mother's
//      race (added indicators; the original four are in fetch_wonder_states_race.js), by Hispanic
//      origin and by source of payment.
// 4. Then:
//    perinatal-ews run --input cdc_wonder_natality_county_2016_2024_tidy.csv \
//        cdc_wonder_natality_county_more_2016_2024_tidy.csv --forecast --context data/context/county_context.csv --out results/2024
//    perinatal-ews pooled --input cdc_wonder_natality_state_groups_2016_2024.csv --window 3 --out results/2024/state_groups
//
// Indicator definitions are in src/perinatal_ews/default_config.yaml and docs/indicators.md. Each
// rate is built from two filtered queries (outcome and all births with the item known), so a
// suppressed category never invalidates a whole county-year. NTSV cesarean queries are limited to
// first births, single, head-first, 37 weeks or more; the script checks each export's query
// criteria and stops if a limit is missing.

const UNKNOWN = /unknown|not stated|not reported|^all\b|^\*all\*$/i;
// Pause before each query, as in fetch_wonder_latest.js: CDC WONDER blocks an address for about
// 30 minutes after too many quick requests.
const PAUSE_MS = 2500;

// Variables already used by the other fetch scripts are taken by code; the others are found on the
// form by their title in the "Group Results By" list, so no code is guessed.
const VARS = {
  county: { code: 'D149.V21-level2' },
  state: { code: 'D149.V21-level1' },
  year: { code: 'D149.V20' },
  prenatal: { code: 'D149.V8' },
  weight: { code: 'D149.V9' },
  oe10: { code: 'D149.V32' },
  ghyp: { code: 'D149.V17' },
  race: { code: 'D149.V49' },
  payer: { code: 'D149.V110' },
  bmi: { title: /^Mother's Pre-?pregnancy BMI$/i },
  gdiab: { title: /^Gestational Diabetes$/i },
  tobacco: { title: /^Tobacco Use$/i },
  delivery: { title: /^Delivery Method$/i },
  lbo: { title: /^Live Birth Order$/i },
  plurality: { title: /^Plurality$/i },
  presentation: { title: /^Fetal Presentation$/i },
  hispanic: { title: /^Mother's Hispanic Origin$/i },
};

// The first number in a category label: "4th month" -> 4, "2000 - 2499 grams" -> 2000, "39 weeks" -> 39.
const first = t => parseInt(t, 10);

// Indicator -> variable, categories counted as the outcome, and (NTSV) categories the births must be in.
const IND = {
  no_first_trimester_care: { v: 'prenatal', num: t => /^No prenatal care$/i.test(t) || first(t) >= 4, more: true },
  prepregnancy_obesity: { v: 'bmi', num: /^(Obesity|Extreme Obesity)/i, more: true },
  prepregnancy_overweight_obesity: { v: 'bmi', num: /^(Overweight|Obesity|Extreme Obesity)/i, more: true },
  gestational_diabetes: { v: 'gdiab', num: /^Yes$/i, more: true },
  smoking_during_pregnancy: { v: 'tobacco', num: /^Yes$/i, more: true },
  ntsv_cesarean: { v: 'delivery', num: /^Cesarean$/i, more: true,
    limit: { lbo: t => first(t) === 1 || /^One\b/i.test(t), plurality: /^Single/i, presentation: /^Cephalic$/i,
             oe10: t => first(t) >= 37 } },
  // The original four, for the state results by Hispanic origin and by payer.
  late_no_prenatal_care: { v: 'prenatal', num: t => /^No prenatal care$/i.test(t) || first(t) >= 7 },
  preterm_birth: { v: 'oe10', num: t => /^Under/i.test(t) || first(t) < 37 },
  low_birth_weight: { v: 'weight', num: t => first(t) < 2500 },
  gestational_hypertension: { v: 'ghyp', num: /^Yes$/i },
};

const RACE_COMBOS = {
  'Native Hawaiian or Other Pacific Islander (combined)': /^(Hawaiian|Guamanian|Samoan|Other Pacific Islander)/i,
  'Asian (combined)': /^(Asian Indian|Chinese|Filipino|Japanese|Korean|Vietnamese|Other Asian)$/i,
  'Asian or Pacific Islander (combined)': /^(Asian Indian|Chinese|Filipino|Japanese|Korean|Vietnamese|Other Asian|Hawaiian|Guamanian|Samoan|Other Pacific Islander)/i,
};
const PAYER_LABEL = { 'Medicaid': 'Medicaid', 'Private Insurance': 'Private insurance', 'Self Pay': 'Self-pay', 'Self-Pay': 'Self-pay', 'Other': 'Other payer' };
const ABBR = { Alabama: 'AL', Alaska: 'AK', Arizona: 'AZ', Arkansas: 'AR', California: 'CA', Colorado: 'CO', Connecticut: 'CT', Delaware: 'DE', 'District of Columbia': 'DC', Florida: 'FL', Georgia: 'GA', Hawaii: 'HI', Idaho: 'ID', Illinois: 'IL', Indiana: 'IN', Iowa: 'IA', Kansas: 'KS', Kentucky: 'KY', Louisiana: 'LA', Maine: 'ME', Maryland: 'MD', Massachusetts: 'MA', Michigan: 'MI', Minnesota: 'MN', Mississippi: 'MS', Missouri: 'MO', Montana: 'MT', Nebraska: 'NE', Nevada: 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', Ohio: 'OH', Oklahoma: 'OK', Oregon: 'OR', Pennsylvania: 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD', Tennessee: 'TN', Texas: 'TX', Utah: 'UT', Vermont: 'VT', Virginia: 'VA', Washington: 'WA', 'West Virginia': 'WV', Wisconsin: 'WI', Wyoming: 'WY' };

// Find each variable on the form: its code, its title (as WONDER writes it in exports), its filter
// list and, for variables offered in several versions, the radio button that selects this version.
function resolve(form) {
  const by = [...form.elements['B_1'].options].map(o => ({ code: o.value, title: o.text.trim() }));
  const found = {}, missing = [];
  for (const [key, spec] of Object.entries(VARS)) {
    // A known code that the "Group Results By" list does not show is still used as is.
    const hit = spec.code ? (by.find(o => o.code === spec.code) || { code: spec.code, title: spec.code })
      : by.find(o => spec.title.test(o.title));
    if (!hit) { missing.push(key + ' (' + spec.title + ')'); continue; }
    const base = hit.code.replace(/-level\d$/, '');
    const sel = form.elements['V_' + base];
    const radio = [...form.querySelectorAll('input[type=radio]')].find(r => r.value === base);
    found[key] = { code: hit.code, base, title: hit.title, radio: radio ? radio.name : null,
      options: sel && sel.options ? [...sel.options].map(o => ({ value: o.value, text: o.text.trim() })) : [] };
  }
  return { vars: found, missing };
}

const test = (m, t) => (typeof m === 'function' ? m(t) : m.test(t));
function codes(v, m) { return v.options.filter(o => !UNKNOWN.test(o.text) && o.value !== '*All*' && test(m, o.text)).map(o => o.value); }
function known(v) { return v.options.filter(o => !UNKNOWN.test(o.text) && o.value !== '*All*').map(o => o.value); }

// The categories each indicator uses, as codes, with their labels for checking.
function plan(R) {
  const out = {}, problems = [];
  for (const [ind, s] of Object.entries(IND)) {
    const v = R.vars[s.v];
    if (!v) { problems.push(`${ind}: variable ${s.v} not found`); continue; }
    const num = codes(v, s.num), den = known(v);
    if (!num.length || num.length >= den.length) problems.push(`${ind}: outcome categories look wrong (${num.length} of ${den.length})`);
    const limits = {};
    for (const [lk, re] of Object.entries(s.limit || {})) {
      const lv = R.vars[lk];
      const c = lv ? codes(lv, re) : [];
      if (!c.length) problems.push(`${ind}: no ${lk} category matches`);
      limits[lk] = { v: lv, codes: c, labels: lv ? lv.options.filter(o => c.includes(o.value)).map(o => o.text) : [] };
    }
    out[ind] = { v, num, den, limits, numLabels: v.options.filter(o => num.includes(o.value)).map(o => o.text),
      denLabels: v.options.filter(o => den.includes(o.value)).map(o => o.text) };
  }
  return { plan: out, problems };
}

// Parse a WONDER tab-separated export: header names, data rows (no Notes), and footer lines.
function parseExport(t) {
  if (!t.startsWith('"Notes"')) throw new Error('Unexpected response from WONDER: ' + t.slice(0, 200));
  const lines = t.split('\n');
  const head = lines[0].split('\t').map(s => s.replace(/^"|"$/g, '').trim());
  const rows = [], footer = [];
  let inFooter = false;
  for (const l of lines.slice(1)) {
    if (/^"?---/.test(l)) { inFooter = true; continue; }
    if (inFooter) { footer.push(l.replace(/^"|"$/g, '').trim()); continue; }
    if (!l.startsWith('\t')) continue;  // Total rows carry a note in the first column
    const c = l.split('\t').map(s => s.replace(/^"|"$/g, ''));
    rows.push(Object.fromEntries(head.map((h, i) => [h, c[i]])));
  }
  return { head, rows, footer };
}

// Stop unless every limit appears in the export's query criteria.
function checkLimits(footer, limits) {
  for (const l of Object.values(limits)) {
    const line = footer.find(f => f.toLowerCase().startsWith(l.v.title.toLowerCase() + ':'));
    if (!line) throw new Error(`The export is not limited by ${l.v.title}; stopping so no unlimited counts are saved.`);
  }
}

function count(x) { return /^\d+$/.test(x || '') ? +x : null; }

async function query(form, opts) {
  // opts: { geo: 'county'|'state', R, v, codes, by: varKey|null, byCodes: [..]|null, limits: {...} }
  const { R } = opts;
  const fd = new FormData(form);
  for (const k of [...fd.keys()]) if (/^(action-|tab-|finder-action-)/.test(k)) fd.delete(k);
  fd.set('B_1', opts.geo === 'county' ? R.vars.county.code : R.vars.state.code);
  fd.set('B_2', R.vars.year.code);
  fd.set('B_3', opts.by ? R.vars[opts.by].code : '*None*'); fd.set('B_4', '*None*'); fd.set('B_5', '*None*');
  fd.delete('V_' + R.vars.year.base); fd.append('V_' + R.vars.year.base, '*All*');
  const setVar = (v, cs) => { if (v.radio) fd.set(v.radio, v.base); fd.delete('V_' + v.base); for (const c of cs) fd.append('V_' + v.base, c); };
  setVar(opts.v, opts.codes);
  for (const l of Object.values(opts.limits || {})) setVar(l.v, l.codes);
  if (opts.by && opts.byCodes) setVar(R.vars[opts.by], opts.byCodes);
  else if (opts.by && R.vars[opts.by].radio) fd.set(R.vars[opts.by].radio, R.vars[opts.by].base);
  fd.set('O_change_action-Send-Export Results', 'Export Results'); fd.set('O_export-format', 'tsv');
  fd.delete('O_show_totals'); fd.set('O_show_suppressed', 'true'); fd.set('O_show_zeros', 'true');
  fd.set('action-Send', 'Send');
  await new Promise(r => setTimeout(r, PAUSE_MS));  // CDC WONDER blocks addresses that send requests too quickly
  const t = await (await fetch(form.action, { method: 'POST', body: new URLSearchParams(fd), credentials: 'include' })).text();
  if (/too many requests|temporarily blocked|access denied/i.test(t.slice(0, 2000)))
    throw new Error('CDC WONDER is limiting requests from this address. Stop, wait 30 minutes, then run the script again.');
  const e = parseExport(t);
  if (opts.limits && Object.keys(opts.limits).length) checkLimits(e.footer, opts.limits);
  return e;
}

// Key each export row by place, year and group. Columns are, in order: Notes, place, place code,
// year, year code, then the group and its code when grouped by a third variable, then Births.
function keyed(e, by) {
  const [, name, code, year, , group] = e.head;
  const m = new Map();
  for (const r of e.rows) m.set([r[code], r[year], by ? r[group] : ''].join('|'), { name: r[name], n: count(r['Births']) });
  return m;
}

function tidyRows(N, D, ind, geo, label) {
  const out = [];
  for (const [k, d] of D) {
    const [id, yr, g] = k.split('|');
    if (geo === 'county' && /999$/.test(id)) continue;  // "Unidentified Counties"
    if (UNKNOWN.test(g || '')) continue;
    let gid = id, name = d.name, st;
    if (geo === 'county') { const cut = name.lastIndexOf(','); st = name.slice(cut + 1).trim(); name = name.slice(0, cut).trim(); }
    else { st = ABBR[name]; if (!st) continue; gid = st; }
    const sub = label ? label(g) : (g || 'All');
    if (!sub) continue;
    const n = N.get(k);
    out.push([gid, '"' + name + '"', st, yr, ind, '"' + sub + '"', n && n.n != null ? n.n : '', d.n != null ? d.n : ''].join(','));
  }
  return out;
}

async function main() {
  const form = [...document.forms].find(x => x.elements['B_1']);
  if (!form) throw new Error('Open the CDC WONDER natality request form first.');
  const R = resolve(form);
  const P = plan(R);
  const summary = Object.fromEntries(Object.entries(P.plan).map(([k, p]) => [k, { variable: p.v.title, outcome: p.numLabels,
    births: p.denLabels, limits: Object.fromEntries(Object.entries(p.limits).map(([lk, l]) => [l.v ? l.v.title : lk, l.labels])) }]));
  console.log('perinatal-ews: variables and categories', JSON.stringify(summary, null, 1));
  if (R.missing.length || P.problems.length) throw new Error('perinatal-ews: stopping. Missing: ' + R.missing.join(', ') + ' ' + P.problems.join('; '));
  window.PEWS_PLAN = summary;
  if (window.PEWS_DRYRUN) return summary;

  const header = 'geo_id,geo_name,state,year,indicator,subgroup,numerator,denominator';
  const county = [header], state = [header];
  const status = (s) => { window.PEWS_STATUS = s; console.log('perinatal-ews:', s); };
  const pair = async (p, o) => [await query(form, { ...o, R, v: p.v, codes: p.num, limits: p.limits }),
                                await query(form, { ...o, R, v: p.v, codes: p.den, limits: p.limits })];
  const payerCodes = R.vars.payer.options.filter(o => /^(Medicaid|Private Insurance)$/i.test(o.text)).map(o => o.value);
  for (const [ind, p] of Object.entries(P.plan)) {
    if (IND[ind].more) {
      status(`${ind}: counties`);
      let [N, D] = await pair(p, { geo: 'county' });
      county.push(...tidyRows(keyed(N), keyed(D), ind, 'county'));
      status(`${ind}: counties by payer`);
      [N, D] = await pair(p, { geo: 'county', by: 'payer', byCodes: payerCodes });
      county.push(...tidyRows(keyed(N, 1), keyed(D, 1), ind, 'county', g => PAYER_LABEL[g]));
      status(`${ind}: states`);
      [N, D] = await pair(p, { geo: 'state' });
      state.push(...tidyRows(keyed(N), keyed(D), ind, 'state'));
      status(`${ind}: states by race`);
      [N, D] = await pair(p, { geo: 'state', by: 'race' });
      state.push(...tidyRows(keyed(N, 1), keyed(D, 1), ind, 'state'));
      for (const [label, re] of Object.entries(RACE_COMBOS)) {
        status(`${ind}: states, ${label}`);
        const rc = codes(R.vars.race, re);
        if (!rc.length) throw new Error('perinatal-ews: no race categories for ' + label);
        const o = { geo: 'state', limits: { ...p.limits, race: { v: R.vars.race, codes: rc } } };
        const n2 = await query(form, { ...o, R, v: p.v, codes: p.num }), d2 = await query(form, { ...o, R, v: p.v, codes: p.den });
        state.push(...tidyRows(keyed(n2), keyed(d2), ind, 'state', () => label));
      }
    }
    status(`${ind}: states by Hispanic origin`);
    let [N, D] = await pair(p, { geo: 'state', by: 'hispanic' });
    state.push(...tidyRows(keyed(N, 1), keyed(D, 1), ind, 'state', g => 'Hispanic origin: ' + g));
    status(`${ind}: states by payer`);
    [N, D] = await pair(p, { geo: 'state', by: 'payer' });
    state.push(...tidyRows(keyed(N, 1), keyed(D, 1), ind, 'state', g => PAYER_LABEL[g] ? 'Payer: ' + PAYER_LABEL[g] : null));
  }
  const save = (rows, name) => { const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([rows.join('\n')], { type: 'text/csv' })); a.download = name; document.body.appendChild(a); a.click(); };
  save(county, 'cdc_wonder_natality_county_more_2016_2024_tidy.csv');
  save(state, 'cdc_wonder_natality_state_groups_2016_2024.csv');
  status(`done: ${county.length - 1} county rows, ${state.length - 1} state rows`);
  window.PEWS_DONE = { county: county.length - 1, state: state.length - 1 };
  return window.PEWS_DONE;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { VARS, IND, RACE_COMBOS, resolve, plan, parseExport, checkLimits, keyed, tidyRows, codes, known, UNKNOWN, query };
} else {
  main().catch(e => { window.PEWS_STATUS = 'error: ' + e.message; console.error(e); });
}
