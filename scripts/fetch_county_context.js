/*
 * Fetch the public county context files used by perinatal-ews v0.3.
 *
 * These sites block scripted downloads from some networks, so the files are
 * fetched from your own browser: open each site below, paste the matching block
 * into the browser console (Developer tools > Console), and save the CSV it
 * downloads into data/context/. Then run:
 *
 *     python scripts/build_county_context.py
 *
 * and download the county outlines (used to place treatment facilities in counties):
 *     https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json
 *     -> data/context/us_counties.geojson
 */

function save(name, text) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' }));
  a.download = name; a.click();
}

/* ---- 1. Open https://data.cdc.gov and run: CDC PLACES + VSRR overdose -> cdc_places_overdose_county.csv,
 *         PLACES 2024 fill + ACS factors -> places2024_fill_and_acs_factors_long.csv ---- */
async function cdc() {
  const M = ['OBESITY', 'BPHIGH', 'DIABETES', 'CSMOKING', 'DEPRESSION', 'MHLTH', 'ACCESS2', 'LACKTRPT', 'FOODINSECU',
    'HOUSINSECU', 'BINGE', 'CHECKUP'];
  const inM = M.map(m => `'${m}'`).join(',');
  // PLACES county data, 2025 release (BRFSS 2023), age-adjusted prevalence
  const rows = await fetch(`/resource/swc5-untb.json?$select=locationid,stateabbr,locationname,measureid,data_value,totalpopulation&$where=year='2023' AND datavaluetypeid='AgeAdjPrv' AND measureid in(${inM})&$limit=100000`).then(r => r.json());
  const P = {};
  for (const r of rows) { const k = r.locationid; P[k] = P[k] || { state: r.stateabbr, name: r.locationname, pop: r.totalpopulation }; P[k][r.measureid] = r.data_value; }
  // VSRR provisional county drug overdose deaths: 12-month count ending each December (1-9 suppressed)
  const od = await fetch(`/resource/gb4e-yj24.json?$select=fips,year,provisional_drug_overdose&$where=month='12' AND year>='2020' AND year<='2024'&$limit=100000`).then(r => r.json());
  const O = {};
  for (const r of od) { const f = r.fips.padStart(5, '0'); O[f] = O[f] || {}; O[f][r.year] = r.provisional_drug_overdose ?? ''; }
  const yrs = ['2020', '2021', '2022', '2023', '2024'];
  const L = [['fips', 'state', 'name', 'pop2023', ...M.map(m => m.toLowerCase()), ...yrs.map(y => 'od_' + y)].join(',')];
  for (const k of [...new Set([...Object.keys(P), ...Object.keys(O)])].sort()) {
    const p = P[k] || {}, o = O[k] || {};
    L.push([k, p.state || '', `"${(p.name || '').replace(/"/g, '')}"`, p.pop || '', ...M.map(m => p[m] ?? ''), ...yrs.map(y => o[y] ?? '')].join(','));
  }
  save('cdc_places_overdose_county.csv', L.join('\n'));
  // PLACES 2024 release for states missing from 2025, and ACS 2017-2021 non-medical factor measures
  const fill = await fetch(`/resource/fu4u-a9bh.json?$select=locationid,measureid,data_value,totalpopulation&$where=stateabbr in('PA','KY','CT') AND datavaluetypeid='AgeAdjPrv' AND measureid in(${inM})&$limit=50000`).then(r => r.json());
  const nm = await fetch(`/resource/i6u4-y3g4.json?$select=locationid,measureid,data_value&$where=measureid in('POV150','UNEMP','NOHSDP','SNGPNT','BROAD','HCOST','CROWD')&$limit=100000`).then(r => r.json());
  const F = ['source,fips,measure,value,pop'];
  for (const r of fill) F.push(['places2024', r.locationid, r.measureid, r.data_value ?? '', r.totalpopulation ?? ''].join(','));
  for (const r of nm) F.push(['acs2017_2021', r.locationid, r.measureid, r.data_value ?? '', ''].join(','));
  save('places2024_fill_and_acs_factors_long.csv', F.join('\n'));
}

/* ---- 2. Open https://findtreatment.gov and run: substance use facilities -> samhsa_findtreatment_su_facilities.csv ---- */
async function samhsa() {
  // All substance use facilities within 9,000 km of the geographic centre of the US (covers AK, HI, PR).
  const base = '/locator/exportsAsJson/v2?sAddr=%2239.8283,-98.5795%22&limitType=2&limitValue=9000000&sType=sa&pageSize=2000';
  const first = await fetch(base + '&page=1').then(r => r.json());
  const all = [...first.rows];
  for (let p = 2; p <= first.totalPages; p++) all.push(...(await fetch(base + '&page=' + p).then(r => r.json())).rows);
  const L = ['state,zip,lat,lon,moud,bup_or_methadone,otp,pregnant_postpartum,medicaid'];
  for (const r of all) {
    const g = k => ((r.services || []).find(s => s.f2 === k) || { f3: '' }).f3;
    const om = g('OM'), ot = g('OT'), sg = g('SG'), pay = g('PAY');
    L.push([r.state, (r.zip || '').slice(0, 5), r.latitude, r.longitude, om ? 1 : 0,
      /Buprenorphine|Methadone/.test(om) ? 1 : 0, /Federally-certified Opioid Treatment Program/.test(ot) ? 1 : 0,
      /Pregnant\/postpartum women/.test(sg) ? 1 : 0, /(^|; )Medicaid/.test(pay) ? 1 : 0].join(','));
  }
  save('samhsa_findtreatment_su_facilities.csv', L.join('\n'));
}

/* ---- 3. Open https://data.cms.gov/provider-data and run: hospitals -> cms_maternal_structural_measure_hospitals.csv ---- */
async function cms() {
  const rows = [];
  for (let off = 0; ; off += 500) {
    const r = await fetch(`/provider-data/api/1/datastore/query/nrdb-3fcy/0?limit=500&offset=${off}&results=true&count=false&schema=false`).then(r => r.json());
    rows.push(...r.results); if (r.results.length < 500) break;
  }
  const L = ['facility_id,state,county,zip,sm7'];
  // SM_7 = Maternal Morbidity Structural Measure: Yes/No = hospital has labour and delivery care.
  for (const r of rows.filter(r => r.measure_id === 'SM_7')) {
    const s = r.score.startsWith('Not Applicable') ? 'NA_no_LD' : r.score === 'Not Available' ? 'not_available' : r.score;
    L.push([r.facility_id, r.state, `"${r.countyparish}"`, r.zip_code, s].join(','));
  }
  save('cms_maternal_structural_measure_hospitals.csv', L.join('\n'));
}

// Run the one that matches the site you are on:
// await cdc();  await samhsa();  await cms();
