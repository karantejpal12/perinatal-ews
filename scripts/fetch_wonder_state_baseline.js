// One-time: fixed file of FINAL state counts for every January-to-month window, 2016-2022.
//
// The monthly update compares this year so far with the same months of earlier years. Years from 2023
// onwards come from the provisional database (which also holds final 2023-2024 data); earlier years
// come from this file. Final data do not change, so this only needs to be run once.
//
// 1. Open https://wonder.cdc.gov/natality-expanded-current.html and click "I Agree".
// 2. Paste this file into the browser console on the request form. It runs 96 queries (5-10 minutes)
//    and downloads final_state_ytd_2016_2022.csv. Save it to data/baseline/.
(async function () {
  const f = [...document.forms].find(x => x.elements['B_1'] && /D149/.test(x.action));
  if (!f) throw new Error('Open the CDC WONDER natality 2016-2024 expanded request form (D149) first.');
  const P = 'D149';
  async function q(groups, filters, radios) {
    const fd = new FormData(f);
    for (const k of [...fd.keys()]) if (/^(action-|tab-|finder-action-)/.test(k)) fd.delete(k);
    for (let i = 0; i < 5; i++) fd.set('B_' + (i + 1), groups[i] || '*None*');
    for (const [k, v] of Object.entries(radios || {})) fd.set(k, v);
    for (const [k, vals] of Object.entries(filters || {})) { fd.delete(k); for (const v of vals) fd.append(k, v); }
    fd.set('O_change_action-Send-Export Results', 'Export Results'); fd.set('O_export-format', 'tsv');
    fd.delete('O_show_totals'); fd.set('O_show_suppressed', 'true'); fd.set('O_show_zeros', 'true'); fd.set('action-Send', 'Send');
    const t = await (await fetch(f.action, { method: 'POST', body: new URLSearchParams(fd), credentials: 'include' })).text();
    if (!t.startsWith('"Notes"')) throw new Error('Unexpected response from WONDER: ' + t.slice(0, 200));
    return t.split('\n').filter(l => l.startsWith('\t')).map(l => l.split('\t').map(s => s.replace(/^"|"$/g, '')));
  }
  const IND = {
    preterm_birth: { radio: { O_oe_gestation: P + '.V32' }, v: 'V_' + P + '.V32', num: ['01', '02', '03', '04', '05'], den: ['01', '02', '03', '04', '05', '06', '07', '08', '09'] },
    low_birth_weight: { radio: { O_weight: P + '.V9' }, v: 'V_' + P + '.V9', num: ['01', '02', '03', '04', '05'], den: ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11'] },
    late_no_prenatal_care: { radio: { O_prenatal: P + '.V8' }, v: 'V_' + P + '.V8', num: ['00', '07', '08', '09', '10'], den: ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10'] },
    gestational_hypertension: { radio: {}, v: 'V_' + P + '.V17', num: ['1'], den: ['1', '2'] },
  };
  const years = ['2016', '2017', '2018', '2019', '2020', '2021', '2022'];
  const num = s => (/^\d+$/.test(s || '') ? s : '');
  const out = ['state_fips,geo_name,year,indicator,subgroup,through_month,numerator,denominator'];
  for (let m = 1; m <= 12; m++) {
    const months = Array.from({ length: m }, (_, i) => String(i + 1));
    for (const [ind, s] of Object.entries(IND)) {
      console.log('perinatal-ews: January-' + m, ind);
      const filt = { ['V_' + P + '.V20']: years, ['V_' + P + '.V25']: months };
      const N = await q([P + '.V21-level1', P + '.V20'], { ...filt, [s.v]: s.num }, s.radio);
      const D = await q([P + '.V21-level1', P + '.V20'], { ...filt, [s.v]: s.den }, s.radio);
      const nm = new Map(N.map(r => [r[2] + '|' + r[4], r[5]]));
      for (const r of D) out.push([r[2], '"' + r[1] + '"', r[4], ind, 'All', m, num(nm.get(r[2] + '|' + r[4])), num(r[5])].join(','));
    }
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([out.join('\n')], { type: 'text/csv' }));
  a.download = 'final_state_ytd_2016_2022.csv'; document.body.appendChild(a); a.click();
  console.log('perinatal-ews: done,', out.length - 1, 'rows');
})();
