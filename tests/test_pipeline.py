import numpy as np
import pandas as pd
import pytest

from perinatal_ews import config as cfgmod
from perinatal_ews import detect, equity, indicators, ingest, monitor, schema, synthetic


@pytest.fixture(scope="module")
def cfg():
    return cfgmod.load_config()


@pytest.fixture(scope="module")
def data():
    return synthetic.generate(seed=7)


def test_synthetic_is_valid_and_fictional(data):
    tidy, truth = data
    schema.validate(tidy)
    assert tidy["geo_id"].str.startswith("9").all()
    assert tidy["geo_name"].str.contains("synthetic").all()
    allrows = tidy[tidy["subgroup"] == "All"].set_index(["geo_id", "year", "indicator"])["denominator"]
    parts = tidy[tidy["subgroup"] != "All"].groupby(["geo_id", "year", "indicator"])["denominator"].sum()
    assert np.allclose(allrows.sort_index(), parts.sort_index())
    assert len(truth) == 14


def test_schema_rejects_bad_rows():
    bad = pd.DataFrame([["1", "x", "S", 2020, "a", "All", 5, 3]], columns=schema.REQUIRED_COLUMNS)
    with pytest.raises(schema.SchemaError):
        schema.validate(bad)


def test_wilson_interval_bounds():
    lo, hi = indicators.wilson_interval([0, 50, 100], [100, 100, 100])
    assert lo[0] == pytest.approx(0, abs=1e-12) and hi[2] == pytest.approx(1, abs=1e-12)
    assert lo[1] < 0.5 < hi[1]


def test_benjamini_hochberg_monotone():
    q = detect.benjamini_hochberg(np.array([0.01, 0.04, 0.03, 0.5, np.nan]))
    assert np.isnan(q[-1])
    assert (q[:4] >= np.array([0.01, 0.04, 0.03, 0.5])).all()


def test_detector_is_calibrated_and_finds_large_changes(cfg, data):
    tidy, truth = data
    ev = monitor.evaluate_against_truth(tidy, cfg, truth)
    s = ev["summary"].iloc[0]
    assert s["false_alert_rate_pct"] < 1.5
    assert s["found_as_alert_or_watch_pct"] >= 50
    large = ev["by_size"].set_index("size_class").loc["large (5k+)"]
    assert large["found_as_alert_or_watch_pct"] == 100


def test_no_alerts_without_injected_change(cfg):
    tidy, truth = synthetic.generate(seed=3, n_injected=1)
    # score a year before any injected onset: alerts should be rare
    res = detect.detect(tidy, cfg, target_year=2022)
    assert (res["level"] == "alert").mean() < 0.02


def test_peer_trend_adjustment_prevents_mass_flagging(cfg):
    tidy, _ = synthetic.generate(seed=5, n_injected=1)
    res = detect.detect(tidy, cfg)
    gh = res[res["indicator"] == "gestational_hypertension"]
    assert (gh["level"] == "alert").mean() < 0.05  # indicator rises nationally every year


def test_equity_gaps(cfg, data):
    tidy, _ = data
    gaps = equity.subgroup_gaps(tidy, cfg)
    assert not gaps.empty
    assert (gaps["rate_ratio"] >= 1).all()
    assert set(gaps["highest_subgroup"]) <= {"Medicaid", "Private insurance", "Other payer"}


def test_data_quality_flags_missing_and_jumps(data):
    tidy, _ = data
    t = tidy.copy()
    drop = (t["geo_id"] == "91001") & (t["year"] == 2024)
    t = t[~drop]
    jump = (t["geo_id"] == "91002") & (t["year"] == 2024)
    t.loc[jump, ["numerator", "denominator"]] *= 2
    dq = monitor.data_quality(t)
    assert "missing this year" in set(dq["issue"])
    assert "denominator jump" in set(dq["issue"])


def test_psi():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 1, 2000)
    assert monitor.population_stability_index(a, rng.normal(0, 1, 2000)) < 0.1
    assert monitor.population_stability_index(a, rng.normal(1, 1, 2000)) > 0.25


WONDER_SAMPLE = '''"Notes"\t"County"\t"County Code"\t"Year"\t"Year Code"\t"OE Gestational Age Recode 10"\t"OE Gestational Age Recode 10 Code"\t"Births"
\t"Middlesex County, MA"\t"25017"\t"2023"\t"2023"\t"34 - 36 weeks"\t"5"\t"1200"
\t"Middlesex County, MA"\t"25017"\t"2023"\t"2023"\t"37 - 38 weeks"\t"6"\t"5000"
\t"Middlesex County, MA"\t"25017"\t"2023"\t"2023"\t"39 weeks"\t"7"\t"8000"
\t"Middlesex County, MA"\t"25017"\t"2023"\t"2023"\t"Unknown or Not Stated"\t"99"\t"12"
"Total"\t"Middlesex County, MA"\t"25017"\t"2023"\t"2023"\t\t\t"14212"
\t"Tiny County, MA"\t"25999"\t"2023"\t"2023"\t"34 - 36 weeks"\t"5"\t"Suppressed"
\t"Tiny County, MA"\t"25999"\t"2023"\t"2023"\t"39 weeks"\t"7"\t"150"
"---"
"Dataset: Natality, 2016-2023 expanded"
'''


def test_wonder_parser(tmp_path, cfg):
    f = tmp_path / "preterm.txt"
    f.write_text(WONDER_SAMPLE)
    tidy = ingest.wonder_to_tidy(f, "preterm_birth", cfg)
    mid = tidy[tidy["geo_id"] == "25017"].iloc[0]
    assert mid["numerator"] == 1200 and mid["denominator"] == 14200
    assert mid["state"] == "MA" and mid["geo_name"] == "Middlesex County"
    tiny = tidy[tidy["geo_id"] == "25999"].iloc[0]
    assert np.isnan(tiny["numerator"])  # suppressed cell invalidates the county-year


def test_state_clusters_flags_statewide_shift(cfg):
    tidy, _ = synthetic.generate(seed=9, n_injected=0)
    t = tidy.copy()
    state = t["state"].iloc[0]
    hit = (t["state"] == state) & (t["indicator"] == "preterm_birth") & (t["year"] == t["year"].max())
    t.loc[hit, "numerator"] = (t.loc[hit, "numerator"] * 1.6).clip(upper=t.loc[hit, "denominator"]).round()
    res = detect.detect(t, cfg)
    cl = monitor.state_clusters(res, t, cfg)
    assert ((cl["state"] == state) & (cl["indicator"] == "preterm_birth")).any()
    assert not ((cl["indicator"] != "preterm_birth")).any()


def test_forecast_runs_forward_in_time_and_beats_chance(cfg):
    from perinatal_ews import forecast
    # Shocks that start in 2022 persist, so next-year flags are partly predictable.
    tidy, _ = synthetic.generate(seed=7, onset_years=3, n_injected=30)
    tidy = tidy[tidy["subgroup"] == "All"]
    r = forecast.run_forecast(tidy, cfg)
    assert r.forecast_year == 2025
    assert r.outcome_years == [2023, 2024]
    assert set(forecast.FEATURES) <= set(r.scores.columns)
    assert r.scores["risk"].between(0, 1).all()
    chosen = r.metrics[r.metrics["selected"]].iloc[0]
    assert chosen["model"] == r.selected_model
    assert chosen["auroc"] > 0.6
    assert chosen["auprc"] == r.metrics["auprc"].iloc[:2].max()
    assert len(r.scores) == tidy[tidy["year"] == 2024].groupby(["indicator", "geo_id"]).ngroups


def _synthetic_context(tidy, seed=0):
    """Fictional county context for the fictional counties; preterm risk is tied to blood pressure."""
    from perinatal_ews.context import BENCHMARK_COLUMNS

    rng = np.random.default_rng(seed)
    ids = sorted(tidy["geo_id"].unique())
    pre = (tidy[(tidy.indicator == "preterm_birth") & (tidy.subgroup == "All")]
           .groupby("geo_id")[["numerator", "denominator"]].sum())
    rate = (pre["numerator"] / pre["denominator"]).reindex(ids)
    ctx = pd.DataFrame(index=pd.Index(ids, name="geo_id"))
    for c in BENCHMARK_COLUMNS:
        ctx[c] = rng.normal(20, 5, len(ids))
    ctx["bphigh"] = 30 + 200 * (rate - rate.mean()) + rng.normal(0, 0.5, len(ids))
    for y in range(2020, 2025):
        ctx[f"overdose_rate_{y}"] = rng.gamma(4, 8, len(ids))
    ctx["moud_facilities"] = rng.poisson(5, len(ids))
    ctx["preg_moud_medicaid_facilities"] = rng.poisson(1, len(ids))
    ctx["ld_hospitals"] = rng.integers(0, 4, len(ids))
    ctx["hospitals_ld_status_unknown"] = 0
    return ctx


def test_context_need_access_and_benchmark(cfg, data):
    from perinatal_ews.context import benchmark, need_access

    tidy, _ = data
    ctx = _synthetic_context(tidy)
    det = detect.detect(tidy, cfg)
    na = need_access(det, ctx)
    assert {"priority", "context_reasons", "perinatal_signals"} <= set(na.columns)
    flagged = set(det.loc[det["level"].isin(["alert", "watch"]), "geo_id"])
    assert set(na["geo_id"]) <= flagged               # every listed county has a perinatal signal
    hi = na[na["priority"] == "high"]
    assert (hi["high_overdose_burden"] & hi["thin_treatment_access"]).all()

    scores, quality = benchmark(tidy, ctx, cfg)
    q = quality.set_index("indicator")
    # Context built from preterm rates must explain preterm much better than chance.
    assert q.loc["preterm_birth", "r2_context_model"] > 0.5
    assert set(scores["compared_with_similar"]) <= {"higher than similar counties", "lower than similar counties",
                                                    "in line with similar counties"}


def test_context_features_never_use_future_overdose_data():
    from perinatal_ews.context import add_context_features

    ctx = pd.DataFrame({f"overdose_rate_{y}": [float(y - 2000)] for y in range(2020, 2025)}, index=["90001"])
    f = pd.DataFrame({"geo_id": ["90001"] * 3, "year": [2019, 2021, 2030], "births": [1000.0] * 3})
    out = add_context_features(f, ctx)
    assert np.isnan(out.loc[0, "ctx_overdose_rate"])       # before any data: missing, not a later year
    assert out.loc[1, "ctx_overdose_rate"] == 21.0
    assert out.loc[2, "ctx_overdose_rate"] == 24.0         # latest available, never beyond


def test_benchmark_conformal_ranges_have_honest_coverage(cfg, data):
    from perinatal_ews.context import benchmark

    tidy, _ = data
    scores, quality = benchmark(tidy, _synthetic_context(tidy), cfg)
    assert (quality["interval_empirical_coverage"] > 0.80).all()
    assert (scores["similar_range_low"] <= scores["context_expected_rate"]).all()
    assert (scores["context_expected_rate"] <= scores["similar_range_high"]).all()
    outside = scores["compared_with_similar"] != "in line with similar counties"
    assert ((scores["observed_rate"] > scores["similar_range_high"]) | (scores["observed_rate"] < scores["similar_range_low"]))[outside].all()


def test_typology_groups_are_stable_and_described(data):
    from perinatal_ews.typology import county_typology

    tidy, _ = data
    assign, summary, profiles, quality = county_typology(tidy, _synthetic_context(tidy))
    assert 4 <= quality["k"] <= 8
    assert set(assign["geo_id"]) == set(tidy["geo_id"])
    assert summary["counties"].sum() == tidy["geo_id"].nunique()
    assert summary["description"].str.len().gt(0).all()


def test_anomaly_model_finds_injected_errors_the_rule_misses():
    from perinatal_ews.anomaly import validate_on_synthetic

    v = validate_on_synthetic(seed=7).set_index("error_type")
    assert v.loc["category_collapse", "found_by_model_pct"] >= 50
    assert v.loc["one_rate_spike", "found_by_model_pct"] >= 50
    assert v.loc["births_drop", "found_by_either_pct"] == 100
    assert v.loc["false flags on clean records (%)", "found_by_model_pct"] <= 2


def _race_tidy():
    """Small fictional state-level table with race groups and a 2017-2018 gap."""
    rows = []
    groups = {"White": (20000, 0.10), "Asian": (3000, 0.10), "Native Hawaiian or Other Pacific Islander": (40, 0.12),
              "Black": (2500, 0.13)}
    for y in range(2016, 2025):
        for g, (n, p) in groups.items():
            num = round(n * p) if not (g == "Native Hawaiian or Other Pacific Islander" and y in (2017, 2018)) else np.nan
            rows.append(dict(geo_id="HI", geo_name="Hawaii", state="HI", year=y, indicator="preterm_birth",
                             subgroup=g, numerator=num, denominator=float(n)))
    return pd.DataFrame(rows)


def test_to_state_sums_counties_and_keeps_missing_missing(data):
    from perinatal_ews.pooling import to_state

    tidy, _ = data
    st = to_state(tidy)
    one = tidy[(tidy.year == 2024) & (tidy.indicator == "preterm_birth") & (tidy.subgroup == "All")]
    s = st[(st.year == 2024) & (st.indicator == "preterm_birth") & (st.subgroup == "All")]
    assert s["denominator"].sum() == one["denominator"].sum()
    t2 = tidy.copy()
    k = t2.index[(t2.year == 2024) & (t2.indicator == "preterm_birth") & (t2.subgroup == "All")][0]
    t2.loc[k, "numerator"] = np.nan
    s2 = to_state(t2)
    st_k = t2.loc[k, "state"]
    assert s2[(s2.state == st_k) & (s2.year == 2024) & (s2.indicator == "preterm_birth") & (s2.subgroup == "All")]["numerator"].isna().all()


def test_pooling_skips_and_reports_unavailable_years():
    from perinatal_ews.pooling import pooled_estimates

    p = pooled_estimates(_race_tidy(), window=3, unavailable_years=[2017, 2018])
    r = p[(p.subgroup == "White") & (p.window == "2016-2018")].iloc[0]
    assert r["years_used"] == "2016" and r["years_unavailable"] == "2017,2018"
    assert r["status"].startswith("too few years") and np.isnan(r["rate"])   # never treated as zero
    full = p[(p.subgroup == "White") & (p.window == "2022-2024")].iloc[0]
    assert full["n_years"] == 3 and full["denominator"] == 60000
    filled = pooled_estimates(_race_tidy(), window=3, unavailable_years=[2017, 2018], fill_window=True)
    f = filled[(filled.subgroup == "White") & (filled.window_end == 2019)].iloc[0]
    assert f["years_used"] == "2016,2019" and f["years_unavailable"] == "2017,2018"
    g = filled[(filled.subgroup == "White") & (filled.window_end == 2021)].iloc[0]
    assert g["years_used"] == "2019,2020,2021"


def test_small_groups_are_combined_and_labelled():
    from perinatal_ews.pooling import small_numbers_analysis

    combine = {"Asian or Pacific Islander (combined)": ["Asian", "Native Hawaiian or Other Pacific Islander"]}
    p, _ = small_numbers_analysis(_race_tidy(), window=3, combine=combine)
    w = p[p.window == "2022-2024"].set_index("subgroup")
    nhpi = "Native Hawaiian or Other Pacific Islander"
    combo = "Asian or Pacific Islander (combined)"
    assert w.loc[nhpi, "status"] != "reliable"                     # about 15 events over 3 years
    assert w.loc[combo, "combined_from"] == "Asian + " + nhpi
    assert w.loc[combo, "denominator"] == w.loc["Asian", "denominator"] + w.loc[nhpi, "denominator"]
    assert w.loc[combo, "status"] == "reliable"
    assert w.loc[nhpi, "report_as"] == combo
    assert w.loc["White", "report_as"] == "White"
    # A year where a member is suppressed makes the combined year missing, never a partial sum.
    early = p[(p.subgroup == combo) & (p.window == "2016-2018")].iloc[0]
    assert "2017" in early["years_missing_or_suppressed"] and "2018" in early["years_missing_or_suppressed"]


def test_combined_group_from_source_is_not_recomputed():
    from perinatal_ews.pooling import add_combined_groups

    t = _race_tidy()
    combo = "Asian or Pacific Islander (combined)"
    src = t[t.subgroup == "Asian"].assign(subgroup=combo, numerator=1.0)
    out = add_combined_groups(pd.concat([t, src]), {combo: ["Asian", "Native Hawaiian or Other Pacific Islander"]})
    assert (out[out.subgroup == combo]["numerator"] == 1.0).all()


def test_compare_windows_only_when_reliable():
    from perinatal_ews.pooling import compare_windows, pooled_estimates

    c = compare_windows(pooled_estimates(_race_tidy(), window=3)).set_index("subgroup")
    assert c.loc["White", "change"] == "no clear change"
    assert c.loc["Native Hawaiian or Other Pacific Islander", "change"].startswith("not compared")


def test_published_state_race_results_never_show_small_counts():
    import json
    from pathlib import Path

    f = Path(__file__).resolve().parents[1] / "results" / "2024" / "state_race.json"
    if not f.exists():
        pytest.skip("state_race.json not built")
    d = json.loads(f.read_text())
    shown = [r for st in d["states"].values() for rows in st.values() for r in rows if r["rate"] is not None]
    assert shown and all(r["n"] >= 20 and r["status"] == "reliable" for r in shown)
    hidden = [r for st in d["states"].values() for rows in st.values() for r in rows if r["rate"] is None]
    assert all(r["n"] is None for r in hidden)


def _synthetic_state_feed(seed=0, bump_state="13", bump=1.35):
    """Fictional monthly state counts shaped like the CDC final (baseline) and provisional files."""
    from perinatal_ews.latest import FIPS_TO_ABBR

    rng = np.random.default_rng(seed)
    fips = list(FIPS_TO_ABBR)[:30]
    inds = {"preterm_birth": 0.10, "low_birth_weight": 0.08, "late_no_prenatal_care": 0.07,
            "gestational_hypertension": 0.08}
    base, prov = [], []
    for f in fips:
        births_m = rng.integers(1500, 9000)
        for y in range(2016, 2027):
            for ind, p0 in inds.items():
                p = p0 * (bump if (f == bump_state and y == 2026 and ind == "late_no_prenatal_care") else 1.0)
                monthly = [(births_m, rng.binomial(births_m, p)) for _ in range(12)]
                for m in range(1, 13):
                    den = sum(b for b, _ in monthly[:m]); num = sum(k for _, k in monthly[:m])
                    if y <= 2022:
                        base.append(dict(state_fips=f, geo_name="x", year=y, indicator=ind, subgroup="All",
                                         through_month=m, numerator=num, denominator=den))
                if y >= 2023:
                    m_ytd = 8
                    den = sum(b for b, _ in monthly[:m_ytd]); num = sum(k for _, k in monthly[:m_ytd])
                    prov.append(dict(series="prov_ytd", state_fips=f, geo_name="x", year=y, indicator=ind,
                                     subgroup="All", numerator=num, denominator=den))
                    for g, share in (("White", 0.6), ("Filipino", 0.004), ("Hawaiian", 0.003)):
                        prov.append(dict(series="prov_ytd", state_fips=f, geo_name="x", year=y, indicator=ind,
                                         subgroup=g, numerator=round(num * share), denominator=round(den * share)))
                    full_m = 8 if y == 2026 else 12
                    prov.append(dict(series="prov_full", state_fips=f, geo_name="x", year=y, indicator=ind,
                                     subgroup="All", numerator=sum(k for _, k in monthly[:full_m]),
                                     denominator=sum(b for b, _ in monthly[:full_m])))
    return pd.DataFrame(prov), pd.DataFrame(base)


def test_choose_months_drops_an_incomplete_latest_month():
    from perinatal_ews.latest import choose_months

    rows = [dict(year=2025, month=m, births=300000) for m in range(1, 13)]
    rows += [dict(year=2026, month=m, births=294000) for m in range(1, 8)] + [dict(year=2026, month=8, births=240000)]
    rows += [dict(year=2026, month=m, births=0) for m in range(9, 13)]
    c = choose_months(pd.DataFrame(rows))
    assert c["latest_month_available"] == "2026-08" and c["excluded_latest_month"] and c["ytd_through_month"] == 7
    rows[-5] = dict(year=2026, month=8, births=292000)
    c2 = choose_months(pd.DataFrame(rows))
    assert not c2["excluded_latest_month"] and c2["ytd_through_month"] == 8


def test_monthly_update_flags_year_to_date_change_and_records_dates(cfg, tmp_path):
    from perinatal_ews.latest import explorer_payload, run_latest

    prov, base = _synthetic_state_feed()
    meta = {"ytd_year": 2026, "ytd_through_month": 8, "latest_month_available": "2026-08",
            "provisional_years": [2025, 2026], "fetched_at": "2026-10-14"}
    res = run_latest(prov, base, meta, cfg, tmp_path)
    d = res["ytd"].set_index(["geo_id", "indicator"])
    assert d.loc[("GA", "late_no_prenatal_care"), "level"] == "alert"          # the injected 35% rise
    others = res["ytd"][(res["ytd"].geo_id != "GA")]
    assert (others["level"] == "alert").mean() < 0.05
    assert res["meta"]["ytd_label"] == "January–August 2026"
    assert res["meta"]["final_years"] == "2016–2024" and res["full_year"] == 2025
    assert (tmp_path / "latest_meta.json").exists()
    race = res["race"].set_index(["geo_id", "indicator", "subgroup"])
    assert race.loc[("GA", "preterm_birth", "Hawaiian"), "report_as"] != "Hawaiian"   # too small alone
    p = explorer_payload(res)
    assert p["states_data"]["GA"]["ind"]["late_no_prenatal_care"]["level"] == "alert"
    assert all(e["rate"] is None or e["rate"] >= 0 for s in p["states_data"].values() for e in s["ind"].values())


def test_full_year_outlook_and_backtest(cfg):
    from perinatal_ews.latest import build_tidy
    from perinatal_ews.outlook import backtest, outlook, score_archived

    prov, base = _synthetic_state_feed(bump=1.35)
    ytd, _ = build_tidy(prov, base, 8, "ytd")
    full, _ = build_tidy(prov, base, 8, "full")
    full = full[full["year"] < 2026]
    ol = outlook(ytd, full, cfg, 2026, [2023, 2024, 2025], n_draws=40)
    assert ol["p_flag"].between(0, 1).all() and (ol["p_alert"] <= ol["p_flag"] + 1e-9).all()
    assert (ol["projected_low80"] <= ol["projected_rate"]).all() and (ol["projected_rate"] <= ol["projected_high80"]).all()
    ga = ol.set_index(["geo_id", "indicator"]).loc[("GA", "late_no_prenatal_care")]
    assert ga["p_flag"] > 0.9                                    # the injected rise carries into the full year
    assert ol[ol["geo_id"] != "GA"]["p_flag"].mean() < 0.1
    bt, summary = backtest(ytd, full, cfg, [2024, 2025], n_draws=30)
    assert 0.5 <= summary["interval80_coverage"] <= 1.0 and summary["state_indicators"] == len(bt)
    from perinatal_ews.detect import detect
    s = score_archived(ol.assign(year=2025), detect(full, cfg, target_year=2025))
    assert s["state_indicators"] > 0
