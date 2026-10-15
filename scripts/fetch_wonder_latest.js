// Monthly update for perinatal-ews: fetch CDC provisional natality data by state.
//
// When: after CDC's monthly update (near the end of each month).
// 1. Open https://wonder.cdc.gov/natality-expanded-provisional.html, read the data use restrictions and
//    click "I Agree" (never publish counts of 9 or fewer).
// 2. On the request form, paste this file into the browser console. It runs about 35 queries
//    (about 3 minutes, with pauses so CDC WONDER does not block the address) and downloads two files:
//      wonder_provisional_state_<YYYY-MM>.csv   counts by state, year, indicator and mother's race
//      wonder_provisional_months_<YYYY-MM>.json monthly national births (used to check completeness)
// 3. Put them in data/latest/ and run:
//      python scripts/update_latest.py --provisional data/latest/<csv> --months data/latest/<json>
//
// The latest month is used only if its births are at least 97% of what earlier months suggest
// (same rule as perinatal_ews.latest.choose_months); otherwise the window ends a month earlier.
(async function () {
  const f = [...document.forms].find(x => x.elements['B_1'] && /D192/.test(x.action));
  if (!f) throw new Error('Open the CDC WONDER provisional natality request form (D192) first.');
  const P = 'D192';
  async function q(groups, filters, radios) {
    const fd = new FormData(f);
    for (const k of [...fd.keys()]) if (/^(action-|tab-|finder-action-)/.test(k)) fd.delete(k);
    for (let i = 0; i < 5; i++) fd.set('B_' + (i + 1), groups[i] || '*None*');
    for (const [k, v] of Object.entries(radios || {})) fd.set(k, v);
    for (const [k, vals] of Object.entries(filters || {})) { fd.delete(k); for (const v of vals) fd.append(k, v); }
    fd.set('O_change_action-Send-Export Results', 'Export Results'); fd.set('O_export-format', 'tsv');
    fd.delete('O_show_totals'); fd.set('O_show_suppressed', 'true'); fd.set('O_show_zeros', 'true'); fd.set('action-Send', 'Send');
    await new Promise(r => setTimeout(r, 2500));  // CDC WONDER blocks addresses that send requests too quickly
    const t = await (await fetch(f.action, { method: 'POST', body: new URLSearchParams(fd), credentials: 'include' })).text();
    if (/Too many requests/i.test(t)) throw new Error('CDC WONDER has temporarily blocked requests from this address (too many requests). Wait 30 minutes and run the script again.');
    if (!t.startsWith('"Notes"')) throw new Error('Unexpected response from WONDER: ' + t.slice(0, 200));
    return t.split('\n').filter(l => l.startsWith('\t')).map(l => l.split('\t').map(s => s.replace(/^"|"$/g, '')));
  }
  // Which years are provisional, and how complete is the latest month?
  const yearOpts = [...f.elements['V_' + P + '.V20'].options].filter(o => /^\d{4}$/.test(o.value));
  const provisionalYears = yearOpts.filter(o => /Provisional/i.test(o.text)).map(o => +o.value);
  const cur = Math.max(...yearOpts.map(o => +o.value));
  const mrows = await q([P + '.V20', P + '.V25'], { ['V_' + P + '.V20']: [String(cur - 1), String(cur)] });
  const monthly = mrows.map(r => ({ year: +r[2], month: +r[4], births: /^\d+$/.test(r[5]) ? +r[5] : 0 }));
  const b = (y, m) => (monthly.find(x => x.year === y && x.month === m) || {}).births || 0;
  const months = monthly.filter(x => x.year === cur && x.births > 0).map(x => x.month);
  const latest = Math.max(...months);
  const ratios = months.filter(m => m !== latest && b(cur - 1, m) > 0).map(m => b(cur, m) / b(cur - 1, m)).sort((a, c) => a - c);
  const typical = ratios.length ? ratios[Math.floor((ratios.length - 1) / 2)] * 0.5 + ratios[Math.ceil((ratios.length - 1) / 2)] * 0.5 : 1;
  const completeness = b(cur - 1, latest) ? (b(cur, latest) / b(cur - 1, latest)) / typical : 0;
  const M = completeness >= 0.97 ? latest : latest - 1;
  console.log(`perinatal-ews: latest month ${cur}-${latest}, completeness ${completeness.toFixed(3)}, using January-${M}`);

  const IND = {
    preterm_birth: { radio: { O_oe_gestation: P + '.V32' }, v: 'V_' + P + '.V32', num: ['01', '02', '03', '04', '05'], den: ['01', '02', '03', '04', '05', '06', '07', '08', '09'] },
    low_birth_weight: { radio: { O_weight: P + '.V9' }, v: 'V_' + P + '.V9', num: ['01', '02', '03', '04', '05'], den: ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11'] },
    late_no_prenatal_care: { radio: { O_prenatal: P + '.V8' }, v: 'V_' + P + '.V8', num: ['00', '07', '08', '09', '10'], den: ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10'] },
    gestational_hypertension: { radio: {}, v: 'V_' + P + '.V17', num: ['1'], den: ['1', '2'] },
  };
  const num = s => (/^\d+$/.test(s || '') ? s : '');
  const out = ['series,state_fips,geo_name,year,indicator,subgroup,numerator,denominator'];
  const ytdMonths = Array.from({ length: M }, (_, i) => String(i + 1));
  for (const [series, mf, byRace] of [['prov_ytd', ytdMonths, false], ['prov_ytd', ytdMonths, true], ['prov_full', ['*All*'], false]]) {
    for (const [ind, s] of Object.entries(IND)) {
      console.log('perinatal-ews:', series, ind, byRace ? 'by race' : 'total');
      const groups = [P + '.V21', P + '.V20'].concat(byRace ? [P + '.V49'] : []);
      const filt = { ['V_' + P + '.V20']: ['*All*'], ['V_' + P + '.V25']: mf };
      const rad = byRace ? { ...s.radio, O_race: P + '.V49' } : s.radio;
      const N = await q(groups, { ...filt, [s.v]: s.num }, rad), D = await q(groups, { ...filt, [s.v]: s.den }, rad);
      const key = r => r[2] + '|' + r[4] + '|' + (byRace ? r[6] : '');
      const nm = new Map(N.map(r => [key(r), byRace ? r[7] : r[5]]));
      for (const r of D) {
        const sub = byRace ? r[5] : 'All';
        if (/Unknown|Not Reported/.test(sub)) continue;
        out.push([series, r[2], '"' + r[1] + '"', r[4], ind, '"' + sub + '"', num(nm.get(key(r))), num(byRace ? r[7] : r[5])].join(','));
      }
    }
  }
  const stamp = `${cur}-${String(latest).padStart(2, '0')}`;
  const save = (name, text, type) => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; document.body.appendChild(a); a.click(); };
  save(`wonder_provisional_state_${stamp}.csv`, out.join('\n'), 'text/csv');
  save(`wonder_provisional_months_${stamp}.json`, JSON.stringify({ fetched_at: new Date().toISOString().slice(0, 10),
    provisional_years: provisionalYears, ytd_through_month_fetched: M, monthly_births: monthly }, null, 1), 'application/json');
  console.log('perinatal-ews: done,', out.length - 1, 'rows');
})();
