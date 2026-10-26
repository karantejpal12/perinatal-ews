/*
 * perinatal-ews data tools, plain-language briefs and a number checker.
 *
 * Used by the explorer (app.html) and by the AI assistant (assistant.js):
 *  - TOOLS: functions the assistant can call. They read only the published
 *    results (results/<year>/explorer.json), so every answer is grounded in the
 *    same numbers as the bulletin.
 *  - countyBrief / stateBrief: deterministic plain-language summaries (no AI
 *    model needed); also given to the assistant as a starting point.
 *  - checkNumbers: lists numbers in an answer that do not appear in any tool
 *    result, so unsupported figures are visible to the reader.
 *
 * Works in the browser (window.EWS) and in Node (module.exports) for tests.
 */
(function (root) {
  'use strict';
  const pct = (x, d = 1) => (x == null ? 'not available' : (100 * x).toFixed(d) + '%');
  const LEVEL_WORD = { alert: 'an alert', watch: 'a watch flag', stable: 'no flag', 'insufficient data': 'not enough data' };

  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const STATE_NAMES = { AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California', CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', DC: 'District of Columbia', FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont', VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming', PR: 'Puerto Rico' };
  function indLabel(D, k) { return (D.indicators && D.indicators[k]) || k; }
  function findCounty(D, q) {
    if (!q) return null;
    const s = String(q).trim().toLowerCase();
    if (/^\d{5}$/.test(s)) return D.counties.find(c => c.id === s) || null;
    const exact = D.counties.filter(c => `${c.name}, ${c.state}`.toLowerCase() === s);
    if (exact.length) return exact[0];
    const norm = t => t.toLowerCase().replace(/\b(county|parish|borough|city and borough|census area)\b/g, '').replace(/\s+/g, ' ').replace(/ ,/g, ',').trim();
    const qn = norm(s);
    const hits = D.counties.filter(c => norm(`${c.name}, ${c.state}`) === qn);
    if (hits.length === 1) return hits[0];
    const part = D.counties.filter(c => norm(`${c.name}, ${c.state}`).includes(qn));
    return part.length === 1 ? part[0] : null;
  }
  const flagged = e => e && (e.level === 'alert' || e.level === 'watch');
  const subFlagged = e => Object.values((e && e.subgroups) || {}).some(sd => sd.level === 'alert' || sd.level === 'watch');

  function countyRecord(D, c) {
    const ind = {};
    for (const [k, e] of Object.entries(c.ind)) {
      ind[indLabel(D, k)] = {
        status_2024: e.level, rate: e.rate, expected_rate: e.expected, observed_vs_expected: e.rr,
        births: e.births, excess_cases: e.excess, elevated_previous_year: e.sustained,
        subgroups: e.subgroups, next_year_risk_of_flag: e.risk ?? null, forecast_main_factors: e.factors || null,
        compared_with_similar_counties: e.similar || null,
        statewide_pattern: (D.state_patterns || []).some(p => p.state === c.state && p.indicator === k),
        rates_by_year: Object.fromEntries(D.years.map((y, i) => [y, e.trend[i]])),
      };
    }
    return { fips: c.id, county: c.name, state: c.state, data_year: D.year, forecast_year: D.forecast_year,
      indicators: ind, county_context: c.ctx || null, context_median_of_scored_counties: D.context_median || null,
      need_and_access: c.need || null,
      county_type: c.type ? { type: c.type, description: (D.types || {})[c.type] ? D.types[c.type].description : null } : null,
      unusual_data_this_year: c.unusual || null };
  }

  function countyBrief(D, c) {
    const parts = [];
    const flags = Object.entries(c.ind).filter(([, e]) => flagged(e));
    if (flags.length) {
      parts.push(`In ${D.year}, ${c.name}, ${c.state} was flagged for ` + flags.map(([k, e]) =>
        `${indLabel(D, k).toLowerCase()} (${e.level}: ${pct(e.rate)} against ${pct(e.expected)} expected)`).join('; ') + '.');
    } else {
      parts.push(`In ${D.year}, ${c.name}, ${c.state} had no county-wide flags on the four indicators.`);
    }
    const subs = [];
    for (const [k, e] of Object.entries(c.ind)) for (const [s, sd] of Object.entries(e.subgroups || {}))
      if (sd.level === 'alert' || sd.level === 'watch') subs.push(`${indLabel(D, k).toLowerCase()} among ${s.toLowerCase()} births (${sd.level}, ${pct(sd.rate)})`);
    if (subs.length) parts.push(`Within payer groups: ${subs.join('; ')}.`);
    const sw = Object.keys(c.ind).filter(k => (D.state_patterns || []).some(p => p.state === c.state && p.indicator === k));
    if (sw.length) parts.push(`Many ${c.state} counties were flagged for ${sw.map(k => indLabel(D, k).toLowerCase()).join(' and ')}, so the change may be state-wide or reflect how the state records it.`);
    const risky = Object.entries(c.ind).filter(([, e]) => (e.risk || 0) >= 0.3).sort((a, b) => b[1].risk - a[1].risk);
    if (risky.length) parts.push(`The forecast gives a ${pct(risky[0][1].risk, 0)} chance of a ${D.forecast_year} flag for ${indLabel(D, risky[0][0]).toLowerCase()}.`);
    const hi = Object.entries(c.ind).filter(([, e]) => e.similar && /higher/.test(e.similar.verdict));
    if (hi.length) parts.push(`Compared with counties in similar conditions, ${hi.map(([k, e]) => `${indLabel(D, k).toLowerCase()} is higher (${pct(e.similar.rate)} vs ${pct(e.similar.expected)})`).join('; ')}.`);
    if (c.need) parts.push(`Need and access (${c.need.priority === 'high' ? 'high priority' : 'for review'}): ${c.need.reasons}.`);
    if (c.unusual) parts.push(`The machine-learning data check found this county's ${D.year} record unusual (${c.unusual}); confirm the data before acting on its flags.`);
    parts.push('These are statistical flags for local follow-up, not confirmed problems.');
    return parts.join(' ');
  }

  // Counties (and county equivalents) per state in the 2016-2024 natality data: Connecticut's eight
  // historical counties, Alaska after the 2019 Chugach / Copper River split. CDC WONDER shows only
  // counties with 100,000+ residents; the rest are combined per state as "Unidentified Counties".
  const COUNTIES_IN_STATE = { AL: 67, AK: 30, AZ: 15, AR: 75, CA: 58, CO: 64, CT: 8, DE: 3, DC: 1, FL: 67, GA: 159, HI: 5, ID: 44, IL: 102, IN: 92, IA: 99, KS: 105, KY: 120, LA: 64, ME: 16, MD: 24, MA: 14, MI: 83, MN: 87, MS: 82, MO: 115, MT: 56, NE: 93, NV: 17, NH: 10, NJ: 21, NM: 33, NY: 62, NC: 100, ND: 53, OH: 88, OK: 77, OR: 36, PA: 67, RI: 5, SC: 46, SD: 66, TN: 95, TX: 254, UT: 29, VT: 14, VA: 133, WA: 39, WV: 55, WI: 72, WY: 23 };

  /* 95% Wilson interval for a published rate and its births. Events are recovered from the rate
     (published to 4 decimals), so they can be off by a fraction of an event in very large counties.
     Rates on fewer than 20 events are marked unstable (NCHS standard). */
  function rateInterval(rate, births, z = 1.959964) {
    if (rate == null || !births) return null;
    const n = births, k = Math.round(rate * n), p = k / n;
    const den = 1 + z * z / n, centre = (p + z * z / (2 * n)) / den;
    const half = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den;
    return { events: k, lo: Math.max(0, centre - half), hi: Math.min(1, centre + half), unstable: k < 20 };
  }

  function stateSummary(D, st) {
    const cs = D.counties.filter(c => c.state === st);
    if (!cs.length) return null;
    const by = {};
    for (const k of Object.keys(D.indicators)) {
      const es = cs.map(c => c.ind[k]).filter(Boolean);
      by[indLabel(D, k)] = { counties_scored: es.length, alerts: es.filter(e => e.level === 'alert').length,
        watch: es.filter(e => e.level === 'watch').length,
        high_next_year_risk: es.filter(e => (e.risk || 0) >= 0.3).length };
    }
    return {
      state: st, data_year: D.year, counties: cs.length, counties_in_state: COUNTIES_IN_STATE[st] ?? null,
      counties_not_scored: COUNTIES_IN_STATE[st] != null ? Math.max(0, COUNTIES_IN_STATE[st] - cs.length) : null, by_indicator: by,
      statewide_patterns: (D.state_patterns || []).filter(p => p.state === st).map(p => ({ indicator: indLabel(D, p.indicator),
        counties_flagged: p.flagged, counties: p.counties, state_rate_baseline: p.rate_before, state_rate_now: p.rate_now })),
      need_and_access: cs.filter(c => c.need).map(c => ({ county: c.name, fips: c.id, priority: c.need.priority, reasons: c.need.reasons })),
      year_to_date_provisional: D.latest && D.latest.states_data[st] ? { period: D.latest.ytd_label, latest_month_available: D.latest.latest_month_available,
        retrieved: D.latest.updated, indicators: Object.fromEntries(Object.entries(D.latest.states_data[st].ind).map(([k, e]) => [indLabel(D, k), e])) } : null,
      flagged_counties: cs.filter(c => Object.values(c.ind).some(flagged)).map(c => ({ county: c.name, fips: c.id,
        flags: Object.entries(c.ind).filter(([, e]) => flagged(e)).map(([k, e]) => `${indLabel(D, k)} (${e.level})`) })),
    };
  }

  function stateBrief(D, st) {
    const s = stateSummary(D, st); if (!s) return '';
    const tot = Object.values(s.by_indicator).reduce((a, b) => a + b.alerts, 0);
    const tw = Object.values(s.by_indicator).reduce((a, b) => a + b.watch, 0);
    const parts = [`${STATE_NAMES[st] || st}: ${plural(s.counties, 'county', 'counties')} with 100,000+ residents ${s.counties === 1 ? 'was' : 'were'} scored for ${D.year}, with ${plural(tot, 'alert', 'alerts')} and ${plural(tw, 'watch flag', 'watch flags')} across the four indicators.`];
    const top = Object.entries(s.by_indicator).filter(([, v]) => v.alerts + v.watch > 0).sort((a, b) => (b[1].alerts + b[1].watch) - (a[1].alerts + a[1].watch));
    if (s.counties_not_scored) parts.push(`The other ${plural(s.counties_not_scored, 'county', 'counties')} of ${s.counties_in_state} ${s.counties_not_scored === 1 ? 'has' : 'have'} fewer than 100,000 residents and ${s.counties_not_scored === 1 ? 'is' : 'are'} not reported separately by CDC WONDER, so ${s.counties_not_scored === 1 ? 'it is' : 'they are'} not covered by the county results.`);
    if (tot + tw === 0) parts.push('No flag means no change from each county\'s own recent history was detected; it does not mean there is no concern, and a rate can stay high without being flagged.');
    if (top.length) parts.push('Most flags: ' + top.map(([k, v]) => `${k.toLowerCase()} (${plural(v.alerts, 'alert', 'alerts')}, ${v.watch} watch)`).join('; ') + '.');
    for (const p of s.statewide_patterns) parts.push(`State-wide pattern in ${p.indicator.toLowerCase()}: ${p.counties_flagged} of ${p.counties} counties flagged; state rate ${pct(p.state_rate_baseline)} at baseline, ${pct(p.state_rate_now)} now. Check with the state vital records office whether recording changed.`);
    if (s.year_to_date_provisional) {
      const y = s.year_to_date_provisional, fl = Object.entries(y.indicators).filter(([, e]) => e.level === 'alert' || e.level === 'watch');
      parts.push(fl.length ? `Provisional data for ${y.period}: ${fl.map(([k, e]) => `${k.toLowerCase()} ${e.level} (${pct(e.rate)} vs ${pct(e.expected)} expected)`).join('; ')}.`
        : `Provisional data for ${y.period} show no state-wide flags.`);
    }
    if (s.need_and_access.length) parts.push(`${s.need_and_access.length} ${s.need_and_access.length === 1 ? 'county is' : 'counties are'} on the need-and-access review list${s.need_and_access.some(n => n.priority === 'high') ? ', including high-priority ' + s.need_and_access.filter(n => n.priority === 'high').map(n => n.county).join(', ') : ''}.`);
    return parts.join(' ');
  }

  function listCounties(D, a = {}) {
    const lim = Math.min(Number(a.limit) || 25, 100);
    const rows = [];
    for (const c of D.counties) {
      if (a.state && c.state !== String(a.state).toUpperCase()) continue;
      for (const [k, e] of Object.entries(c.ind)) {
        if (a.indicator && k !== a.indicator) continue;
        const f = a.filter || 'flagged';
        const ok = f === 'alert' ? e.level === 'alert' : f === 'flagged' ? flagged(e)
          : f === 'subgroup_flag' ? subFlagged(e) : f === 'high_next_year_risk' ? (e.risk || 0) >= 0.3
          : f === 'stable_but_high_risk' ? e.level === 'stable' && (e.risk || 0) >= 0.25
          : f === 'need_and_access' ? !!c.need && (flagged(e) || subFlagged(e) || (e.risk || 0) >= 0.3)
          : f === 'higher_than_similar' ? !!(e.similar && /higher/.test(e.similar.verdict))
          : f === 'unusual_data' ? !!c.unusual : false;
        if (ok) rows.push({ county: c.name, state: c.state, fips: c.id, indicator: indLabel(D, k), status: e.level,
          rate: e.rate, expected_rate: e.expected, observed_vs_expected: e.rr, next_year_risk: e.risk ?? null,
          similar_counties_rate: e.similar ? e.similar.expected : null, need_priority: c.need ? c.need.priority : null });
      }
    }
    const key = { alert: 0, watch: 1, stable: 2 };
    rows.sort((x, y) => (a.filter || '').includes('risk') ? (y.next_year_risk || 0) - (x.next_year_risk || 0)
      : (key[x.status] - key[y.status]) || ((y.observed_vs_expected || 0) - (x.observed_vs_expected || 0)));
    return { total_matching: rows.length, showing: Math.min(lim, rows.length), rows: rows.slice(0, lim) };
  }

  function nationalSummary(D) {
    const by = {};
    for (const k of Object.keys(D.indicators)) {
      const es = D.counties.map(c => c.ind[k]).filter(Boolean);
      by[indLabel(D, k)] = { alerts: es.filter(e => e.level === 'alert').length, watch: es.filter(e => e.level === 'watch').length };
    }
    return { data_year: D.year, forecast_year: D.forecast_year, counties: D.counties.length, years: D.years,
      by_indicator: by, statewide_patterns: (D.state_patterns || []).map(p => ({ state: p.state, indicator: indLabel(D, p.indicator), flagged: p.flagged, counties: p.counties })),
      need_and_access_counties: D.counties.filter(c => c.need).length,
      need_and_access_high_priority: D.counties.filter(c => c.need && c.need.priority === 'high').map(c => `${c.name}, ${c.state}`),
      forecast_validation: D.forecast_metrics || null, similar_county_model_fit: D.benchmark_quality || null,
      county_types: D.types || null, county_types_quality: D.types_quality || null,
      sources: [D.source, D.context_source].filter(Boolean) };
  }

  const METHOD = {
    detection: 'Each county is compared with its own pooled rate over three baseline years (skipping the year just before), shrunk toward the all-county rate for small counties (empirical Bayes) and scaled by the national trend. Alerts need a Benjamini-Hochberg q <= 0.05, observed/expected >= 1.10 and at least 20 events; watch flags need z >= 2 and a ratio >= 1.05. Payer subgroups (Medicaid, private insurance) are tested the same way.',
    forecast: 'A gradient-boosted tree model predicts whether each county will be flagged next year from recent rates, trends, detection scores, size, payer mix and state-wide changes. It is validated forward in time (trained only on earlier years) against logistic regression and persistence baselines. County context did not clearly improve it, so it is not used in the forecast.',
    similar_counties: 'A gradient-boosted regression model predicts each county\'s 2022-2024 rate from its health, social, overdose and access context alone, using 5-fold cross-validation so no county is judged by a model that saw it. Rates well above the prediction are "higher than similar counties".',
    need_and_access: 'Counties with a perinatal flag (or next-year risk >= 30%) plus a top-quarter overdose death rate, thin treatment access for pregnant/postpartum patients (no or bottom-quarter facilities offering buprenorphine or methadone, accepting Medicaid, with a pregnancy programme), or thin delivery capacity. High priority = high overdose burden and thin treatment access.',
    county_types: 'Unsupervised k-means clustering groups the 578 counties into peer types by recent indicator levels, county size, adult health, social conditions, overdose burden and treatment access. The number of types was chosen by silhouette score and checked for stability on 50 bootstrap resamples (adjusted Rand index). Types are a summary of a continuum, not sharp categories.',
    data_anomalies: 'An Isolation Forest (unsupervised anomaly detection) scores every county-year record; the 2% least typical are flagged, with the features that make them unusual. It complements the rule that flags births changing by more than 30%: on synthetic data with injected errors it found about two-thirds of single-indicator errors the rule misses, with 0.5% false flags.',
    prediction_ranges: 'For the similar-county comparison, each county gets a 90% range for counties like it, from cross-conformal prediction on normalised residuals. Counties outside the range are higher or lower than similar counties. On the real data the ranges contained 90-91% of counties.',
    limitations: 'County data come from CDC WONDER natality for counties with 100,000+ residents; counts of 9 or fewer are suppressed. Flags are statistical leads, not confirmed problems. Context measures describe places, not people, and are associations, not causes. The tool is not for clinical or individual decisions.',
  };

  const TOOLS = [
    { name: 'search_counties', description: 'Find counties by name and/or state. Returns FIPS codes. Use before get_county when you only have a name.',
      input_schema: { type: 'object', properties: { query: { type: 'string', description: 'County name, optionally with state, e.g. "Hampden" or "Fulton, GA"' } }, required: ['query'] },
      run: (D, a) => { const s = String(a.query || '').toLowerCase().replace(/ county| parish/g, '').trim();
        const [n, st] = s.split(',').map(x => x && x.trim());
        return D.counties.filter(c => c.name.toLowerCase().includes(n || '') && (!st || c.state.toLowerCase() === st)).slice(0, 15).map(c => ({ fips: c.id, county: c.name, state: c.state })); } },
    { name: 'get_county', description: 'All results for one county: 2024 status, rates, expected rates, payer subgroups, year-by-year rates, next-year risk and its main factors, comparison with similar counties, county context (overdose, treatment, hospitals, adult health, poverty) and need-and-access status. Also returns a plain-language brief.',
      input_schema: { type: 'object', properties: { fips: { type: 'string', description: '5-digit county FIPS code' } }, required: ['fips'] },
      run: (D, a) => { const c = findCounty(D, a.fips); return c ? { ...countyRecord(D, c), plain_language_brief: countyBrief(D, c) } : { error: 'County not found. Use search_counties. Only counties with 100,000+ residents are included.' }; } },
    { name: 'list_counties', description: 'List county-indicator results matching a filter, optionally within one state and/or indicator.',
      input_schema: { type: 'object', properties: {
        filter: { type: 'string', enum: ['flagged', 'alert', 'subgroup_flag', 'high_next_year_risk', 'stable_but_high_risk', 'need_and_access', 'higher_than_similar', 'unusual_data'] },
        state: { type: 'string', description: 'Two-letter state code' },
        indicator: { type: 'string', enum: ['late_no_prenatal_care', 'preterm_birth', 'low_birth_weight', 'gestational_hypertension'] },
        limit: { type: 'integer', description: 'Max rows (default 25, max 100)' } }, required: ['filter'] },
      run: (D, a) => listCounties(D, a) },
    { name: 'state_summary', description: 'Summary for one state: flags by indicator, state-wide patterns, need-and-access counties and flagged counties, plus a plain-language brief.',
      input_schema: { type: 'object', properties: { state: { type: 'string', description: 'Two-letter state code' } }, required: ['state'] },
      run: (D, a) => { const st = String(a.state || '').toUpperCase(); const s = stateSummary(D, st); return s ? { ...s, plain_language_brief: stateBrief(D, st) } : { error: 'No scored counties in that state.' }; } },
    { name: 'national_summary', description: 'National overview: flags by indicator, state-wide patterns, need-and-access counts, forecast validation metrics, model fit of the similar-county comparison and data sources.',
      input_schema: { type: 'object', properties: {} }, run: D => nationalSummary(D) },
    { name: 'method_info', description: 'How a part of perinatal-ews works, and its limitations.',
      input_schema: { type: 'object', properties: { topic: { type: 'string', enum: Object.keys(METHOD) } }, required: ['topic'] },
      run: (D, a) => ({ topic: a.topic, text: METHOD[a.topic] || 'Unknown topic.' }) },
  ];

  /* Numbers in an answer that do not appear in any tool result (after rounding). Years and small integers are ignored. */
  function checkNumbers(answer, toolResults) {
    const known = new Set();
    const add = v => {
      if (typeof v !== 'number' || !isFinite(v)) return;
      [v, v * 100].forEach(x => { for (const d of [0, 1, 2, 3]) known.add(Number(x.toFixed(d))); known.add(Math.round(x)); });
    };
    const walk = o => { if (o == null) return; if (typeof o === 'number') add(o); else if (typeof o === 'string') (o.match(/-?\d[\d,]*\.?\d*/g) || []).forEach(t => add(Number(t.replace(/,/g, '')))); else if (typeof o === 'object') Object.values(o).forEach(walk); };
    toolResults.forEach(walk);
    const out = [];
    const re = /(-?\d[\d,]*\.?\d*)\s*(%|×|x\b)?/g; let m;
    while ((m = re.exec(answer))) {
      const raw = m[1].replace(/,$/, ''); const n = Number(raw.replace(/,/g, ''));
      if (!isFinite(n)) continue;
      if (!m[2] && Number.isInteger(n) && (n <= 12 || (n >= 1990 && n <= 2035))) continue;
      const ok = known.has(n);  // known holds every value rounded to 0-3 decimals, as a percentage and as-is
      if (!ok) out.push(m[0].trim());
    }
    return [...new Set(out)];
  }

  const api = { STATE_NAMES, COUNTIES_IN_STATE, rateInterval, TOOLS, countyBrief, stateBrief, stateSummary, listCounties, nationalSummary, checkNumbers, findCounty, METHOD };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.EWS = api;
})(typeof window !== 'undefined' ? window : globalThis);
