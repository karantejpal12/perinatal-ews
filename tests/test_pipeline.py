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
