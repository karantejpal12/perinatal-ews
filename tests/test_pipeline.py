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
