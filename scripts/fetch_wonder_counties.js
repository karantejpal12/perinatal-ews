// Fetch county-level natality data for perinatal-ews from CDC WONDER.
//
// How to use:
// 1. Open https://wonder.cdc.gov/natality-expanded-current.html, read the data use
//    restrictions and click "I Agree". You must follow those terms, including never
//    publishing counts of 9 or fewer.
// 2. On the request form that opens, open the browser's developer console and paste
//    this whole file. It runs 16 queries (about 2-3 minutes) and downloads one CSV in
//    the perinatal-ews tidy schema, covering all four indicators for 2016-2024, for the
//    county total and for Medicaid and private-insurance births.
// 3. Run: perinatal-ews run --input cdc_wonder_natality_county_2016_2024_tidy.csv --out results/
//
// Each indicator is built from two filtered queries (numerator and denominator) so a
// suppressed category never invalidates the whole county-year. "Unidentified Counties"
// (codes ending 999) are dropped.
(async function () {
  const f = [...document.forms].find(x => x.elements['B_1']);
  if (!f) throw new Error('Open the CDC WONDER natality request form first.');
  const IND = {
    preterm_birth: { radio: { O_oe_gestation: 'D149.V32' }, v: 'V_D149.V32',
      num: ['01', '02', '03', '04', '05'], den: ['01', '02', '03', '04', '05', '06', '07', '08', '09'] },
    low_birth_weight: { radio: { O_weight: 'D149.V9' }, v: 'V_D149.V9',
      num: ['01', '02', '03', '04', '05'], den: ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11'] },
    late_no_prenatal_care: { radio: { O_prenatal: 'D149.V8' }, v: 'V_D149.V8',
      num: ['00', '07', '08', '09', '10'], den: ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10'] },
    gestational_hypertension: { radio: {}, v: 'V_D149.V17', num: ['1'], den: ['1', '2'] },
  };
  async function query(spec, codes, byPayer) {
    const fd = new FormData(f);
    for (const k of [...fd.keys()]) if (/^(action-|tab-|finder-action-)/.test(k)) fd.delete(k);
    fd.set('B_1', 'D149.V21-level2'); fd.set('B_2', 'D149.V20');
    fd.set('B_3', byPayer ? 'D149.V110' : '*None*'); fd.set('B_4', '*None*'); fd.set('B_5', '*None*');
    for (const [k, v] of Object.entries(spec.radio)) fd.set(k, v);
    fd.delete('V_D149.V20'); fd.append('V_D149.V20', '*All*');
    fd.delete(spec.v); for (const c of codes) fd.append(spec.v, c);
    if (byPayer) { fd.delete('V_D149.V110'); fd.append('V_D149.V110', '1'); fd.append('V_D149.V110', '2'); }
    fd.set('O_change_action-Send-Export Results', 'Export Results'); fd.set('O_export-format', 'tsv');
    fd.delete('O_show_totals'); fd.set('O_show_suppressed', 'true'); fd.set('O_show_zeros', 'true');
    fd.set('action-Send', 'Send');
    const t = await (await fetch(f.action, { method: 'POST', body: new URLSearchParams(fd), credentials: 'include' })).text();
    if (!t.startsWith('"Notes"')) throw new Error('Unexpected response from WONDER: ' + t.slice(0, 200));
    const m = new Map();
    for (const l of t.split('\n')) {
      if (!l.startsWith('\t')) continue;
      const c = l.split('\t').map(s => s.replace(/^"|"$/g, ''));
      const sub = byPayer ? ({ 'Medicaid': 'Medicaid', 'Private Insurance': 'Private insurance' })[c[5]] || c[5] : 'All';
      const births = byPayer ? c[7] : c[5];
      m.set(c[2] + '|' + c[3] + '|' + sub, { name: c[1], val: /^\d+$/.test(births) ? +births : null });
    }
    return m;
  }
  const rows = ['geo_id,geo_name,state,year,indicator,subgroup,numerator,denominator'];
  for (const [ind, spec] of Object.entries(IND)) {
    for (const byPayer of [false, true]) {
      console.log('perinatal-ews: fetching', ind, byPayer ? '(by payer)' : '(total)');
      const N = await query(spec, spec.num, byPayer), D = await query(spec, spec.den, byPayer);
      for (const [key, d] of D) {
        const [fips, yr, sub] = key.split('|');
        if (/999$/.test(fips)) continue;
        const n = N.get(key); const cut = d.name.lastIndexOf(',');
        rows.push([fips, '"' + d.name.slice(0, cut).trim() + '"', d.name.slice(cut + 1).trim(), yr, ind, sub,
          n && n.val != null ? n.val : '', d.val != null ? d.val : ''].join(','));
      }
    }
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([rows.join('\n')], { type: 'text/csv' }));
  a.download = 'cdc_wonder_natality_county_2016_2024_tidy.csv';
  document.body.appendChild(a); a.click();
  console.log('perinatal-ews: done,', rows.length - 1, 'rows');
})();
