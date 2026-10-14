// Fetch state-level natality data by mother's race (15 groups) for perinatal-ews from CDC WONDER.
//
// 1. Open https://wonder.cdc.gov/natality-expanded-current.html, read the data use restrictions and
//    click "I Agree" (never publish counts of 9 or fewer).
// 2. Paste this file into the browser console on the request form. It runs 40 queries (about 3-4 minutes)
//    and downloads cdc_wonder_natality_state_race_2016_2024.csv: state totals, each race group, and
//    three combined groups requested directly from WONDER (so suppression in a member group does not
//    affect them).
// 3. Then: perinatal-ews pooled --input <file> --window 3 --out results/state_race
(async function () {
  const f = [...document.forms].find(x => x.elements['B_1']);
  if (!f) throw new Error('Open the CDC WONDER natality request form first.');
  const IND = {
    preterm_birth: { radio: { O_oe_gestation: 'D149.V32' }, v: 'V_D149.V32', num: ['01', '02', '03', '04', '05'], den: ['01', '02', '03', '04', '05', '06', '07', '08', '09'] },
    low_birth_weight: { radio: { O_weight: 'D149.V9' }, v: 'V_D149.V9', num: ['01', '02', '03', '04', '05'], den: ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11'] },
    late_no_prenatal_care: { radio: { O_prenatal: 'D149.V8' }, v: 'V_D149.V8', num: ['00', '07', '08', '09', '10'], den: ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10'] },
    gestational_hypertension: { radio: {}, v: 'V_D149.V17', num: ['1'], den: ['1', '2'] },
  };
  const COMBOS = { 'Native Hawaiian or Other Pacific Islander (combined)': ['11', '12', '13', '14'],
    'Asian (combined)': ['4', '5', '6', '7', '8', '9', '10'],
    'Asian or Pacific Islander (combined)': ['4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14'] };
  const ABBR = { Alabama: 'AL', Alaska: 'AK', Arizona: 'AZ', Arkansas: 'AR', California: 'CA', Colorado: 'CO', Connecticut: 'CT', Delaware: 'DE', 'District of Columbia': 'DC', Florida: 'FL', Georgia: 'GA', Hawaii: 'HI', Idaho: 'ID', Illinois: 'IL', Indiana: 'IN', Iowa: 'IA', Kansas: 'KS', Kentucky: 'KY', Louisiana: 'LA', Maine: 'ME', Maryland: 'MD', Massachusetts: 'MA', Michigan: 'MI', Minnesota: 'MN', Mississippi: 'MS', Missouri: 'MO', Montana: 'MT', Nebraska: 'NE', Nevada: 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', Ohio: 'OH', Oklahoma: 'OK', Oregon: 'OR', Pennsylvania: 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD', Tennessee: 'TN', Texas: 'TX', Utah: 'UT', Vermont: 'VT', Virginia: 'VA', Washington: 'WA', 'West Virginia': 'WV', Wisconsin: 'WI', Wyoming: 'WY' };
  async function q(spec, codes, byRace, race) {
    const fd = new FormData(f);
    for (const k of [...fd.keys()]) if (/^(action-|tab-|finder-action-)/.test(k)) fd.delete(k);
    fd.set('B_1', 'D149.V21-level1'); fd.set('B_2', 'D149.V20'); fd.set('B_3', byRace ? 'D149.V49' : '*None*');
    fd.set('B_4', '*None*'); fd.set('B_5', '*None*'); fd.set('O_race', 'D149.V49');
    if (race) { fd.delete('V_D149.V49'); for (const r of race) fd.append('V_D149.V49', r); }
    for (const [k, v] of Object.entries(spec.radio)) fd.set(k, v);
    fd.delete('V_D149.V20'); fd.append('V_D149.V20', '*All*'); fd.delete(spec.v); for (const c of codes) fd.append(spec.v, c);
    fd.set('O_change_action-Send-Export Results', 'Export Results'); fd.set('O_export-format', 'tsv');
    fd.delete('O_show_totals'); fd.set('O_show_suppressed', 'true'); fd.set('O_show_zeros', 'true'); fd.set('action-Send', 'Send');
    const t = await (await fetch(f.action, { method: 'POST', body: new URLSearchParams(fd), credentials: 'include' })).text();
    if (!t.startsWith('"Notes"')) throw new Error('Unexpected response from WONDER: ' + t.slice(0, 200));
    const m = new Map();
    for (const l of t.split('\n')) {
      if (!l.startsWith('\t')) continue;
      const c = l.split('\t').map(s => s.replace(/^"|"$/g, ''));
      const v = byRace ? c[7] : c[5];
      m.set(c[1] + '|' + c[3] + '|' + (byRace ? c[5] : ''), /^\d+$/.test(v) ? +v : null);
    }
    return m;
  }
  const rows = ['geo_id,geo_name,state,year,indicator,subgroup,numerator,denominator'];
  const add = (N, D, ind, label) => {
    for (const [k, d] of D) {
      const [st, yr, race] = k.split('|'); const sub = label || race || 'All';
      if (!ABBR[st] || /Unknown|Not Reported/.test(sub)) continue;
      const n = N.get(k);
      rows.push([ABBR[st], '"' + st + '"', ABBR[st], yr, ind, '"' + sub + '"', n ?? '', d ?? ''].join(','));
    }
  };
  for (const [ind, spec] of Object.entries(IND)) {
    for (const byRace of [false, true]) { console.log('perinatal-ews:', ind, byRace ? 'by race' : 'total'); add(await q(spec, spec.num, byRace), await q(spec, spec.den, byRace), ind, null); }
    for (const [label, codes] of Object.entries(COMBOS)) { console.log('perinatal-ews:', ind, label); add(await q(spec, spec.num, false, codes), await q(spec, spec.den, false, codes), ind, label); }
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([rows.join('\n')], { type: 'text/csv' }));
  a.download = 'cdc_wonder_natality_state_race_2016_2024.csv'; document.body.appendChild(a); a.click();
  console.log('perinatal-ews: done,', rows.length - 1, 'rows');
})();
