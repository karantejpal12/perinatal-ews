import numpy as np
import pandas as pd
import pytest

from perinatal_ews import config as cfgmod
from perinatal_ews import synthetic
from perinatal_ews.holdout import heldout_predictions, heldout_summary


@pytest.fixture(scope="module")
def cfg():
    return cfgmod.load_config()


@pytest.fixture(scope="module")
def clean(cfg):
    tidy, _ = synthetic.generate(seed=11, n_injected=0)
    return tidy, heldout_predictions(tidy, cfg)


def test_coverage_near_nominal_when_the_model_holds(clean):
    """With no injected changes, predictive intervals cover held-out county-years at about their nominal rate."""
    _, p = clean
    s = heldout_summary(p).query("group == 'all'").iloc[0]
    assert 0.85 <= s["coverage_90"] <= 0.95
    assert 0.90 <= s["coverage_95"] <= 0.98
    # Binomial noise alone understates the spread: the extra-variance terms matter.
    assert s["coverage_95_binomial_only"] < s["coverage_95"]


def test_target_year_count_is_never_used(cfg, clean):
    """Changing a county's own target-year count must not change its held-out prediction."""
    tidy, p = clean
    row = p.iloc[0]
    t2 = tidy.copy()
    m = ((t2["geo_id"] == row["geo_id"]) & (t2["indicator"] == row["indicator"])
         & (t2["year"] == row["year"]) & (t2["subgroup"] == "All"))
    t2.loc[m, "numerator"] = t2.loc[m, "numerator"] * 3
    p2 = heldout_predictions(t2, cfg, years=[int(row["year"])])
    r2 = p2[(p2["geo_id"] == row["geo_id"]) & (p2["indicator"] == row["indicator"])].iloc[0]
    assert r2["expected_rate"] == pytest.approx(row["expected_rate"], rel=1e-12)
    assert r2["observed"] == pytest.approx(3 * row["observed"])


def test_years_need_a_full_baseline(clean):
    """Target years start once three baseline years and the skipped year exist (2016 + 3 + 1 = 2020)."""
    _, p = clean
    assert int(p["year"].min()) == 2020 and int(p["year"].max()) == 2024
    assert set(p["size_group"].astype(str)) == {"smallest third", "middle third", "largest third"}
    assert np.isfinite(p[["z", "expected_rate", "var"]].to_numpy()).all()
