"""Year-so-far denominators of counts per population (``model: count``), on synthetic state counts.

Downloads give a count indicator an annual population in both the year-so-far and full-year files.
`build_tidy` scales it to person-time for January to m (population x m / 12), so that year-so-far
rates are per year and the full-year outlook has a population for the remaining months. Before this,
the remaining months had no population and the indicator silently dropped out of the outlook.
"""
import numpy as np
import pandas as pd
import pytest

from perinatal_ews.config import load_config
from perinatal_ews.latest import build_tidy, person_time
from perinatal_ews.outlook import outlook, remaining_table
from test_latest_schema import _teen_feed
from test_pipeline import _synthetic_state_feed

IND = "teen_birth_rate"
M = 8


@pytest.fixture(scope="module")
def cfg():
    c = load_config()
    c["indicators"][IND] = {"label": "Teen birth rate", "direction": "higher_is_worse", "model": "count",
                            "set": "more"}
    return c


@pytest.fixture(scope="module")
def feed():
    return _teen_feed(*_synthetic_state_feed())


def test_person_time_scales_only_counts_per_population():
    t = pd.DataFrame({"indicator": [IND, "preterm_birth"], "numerator": [30.0, 900], "denominator": [12_000, 9_000]})
    out = person_time(t, M, [IND])
    assert out["denominator"].tolist() == [8_000, 9_000]
    assert t["denominator"].tolist() == [12_000, 9_000]                 # the input is left alone
    assert person_time(t, 12, [IND])["denominator"].tolist() == [12_000, 9_000]
    assert person_time(t, M) is t                                     # no count indicator: unchanged
    with pytest.raises(ValueError, match="1-12"):
        person_time(t, 0, [IND])


def test_build_tidy_gives_count_indicators_person_time_for_the_months_covered(feed):
    prov, base = feed
    ytd, _ = build_tidy(prov, base, M, "ytd", count_indicators=[IND])
    full, _ = build_tidy(prov, base, M, "full", count_indicators=[IND])
    key = ["geo_id", "year"]
    y = ytd[ytd["indicator"] == IND].set_index(key)["denominator"]
    f = full[full["indicator"] == IND].set_index(key)["denominator"]
    both = y.index.intersection(f.index)
    assert len(both) > 100
    assert np.allclose(y[both], f[both] * M / 12)                     # full years keep the annual population
    # year-so-far rates are per year, like full-year rates (about 1.5% in the synthetic feed)
    r = ytd[ytd["indicator"] == IND]
    assert 0.014 < (r["numerator"] / r["denominator"]).median() < 0.016
    # shares of births are exactly as before
    plain, _ = build_tidy(*_synthetic_state_feed(), M, "ytd")
    shares = ytd[ytd["indicator"] != IND].reset_index(drop=True)
    pd.testing.assert_frame_equal(shares, plain.reset_index(drop=True), check_dtype=False)


def test_count_indicator_reaches_the_full_year_outlook(cfg, feed):
    prov, base = feed
    counts = [IND]
    ytd, _ = build_tidy(prov, base, M, "ytd", count_indicators=counts)
    full, _ = build_tidy(prov, base, M, "full", count_indicators=counts)
    full = full[full["year"] < 2026]
    rem = remaining_table(ytd, full, counts)
    teen = rem[rem["indicator"] == IND]
    assert len(teen) and np.allclose(teen["births_ratio"], (12 - M) / M)   # four months of population remain
    ol = outlook(ytd, full, cfg, 2026, [2023, 2024, 2025], n_draws=40)
    t = ol[ol["indicator"] == IND]
    assert t["geo_id"].nunique() == ytd["geo_id"].nunique()           # every state, none dropped
    assert 0.014 < t["projected_rate"].median() < 0.016
    assert (t["projected_low80"] <= t["projected_rate"]).all() and (t["projected_rate"] <= t["projected_high80"]).all()


def test_without_scaling_the_count_indicator_would_drop_out(feed):
    """The gap this fixes: with the annual population in both files nothing remains for the outlook."""
    prov, base = feed
    ytd, _ = build_tidy(prov, base, M, "ytd", count_indicators=[IND])
    full, _ = build_tidy(prov, base, M, "full", count_indicators=[IND])
    unscaled = ytd.copy()
    hit = unscaled["indicator"] == IND
    unscaled.loc[hit, "denominator"] = unscaled.loc[hit, "denominator"] * 12 / M
    rem = remaining_table(unscaled, full[full["year"] < 2026], [IND])
    assert (rem["indicator"] == IND).sum() == 0
