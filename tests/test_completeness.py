"""How drops in item completeness affect alerts, on synthetic data with injected drops.

A drop in completeness (more births with the item unknown or not stated) removes
births from the indicator's denominator. These tests pin down what that does to
detection: missing at random it costs a little power and creates no alerts;
when births without the outcome go missing it creates false alerts, which the
missing-data sensitivity analysis reveals; when cases go missing it can hide a
real change and, through the reference-trend adjustment, create false alerts in
other counties, which that analysis does not reveal. See docs/validation.md.
"""
import numpy as np
import pandas as pd
import pytest

from perinatal_ews import config as cfgmod
from perinatal_ews import synthetic
from perinatal_ews.detect import detect
from perinatal_ews.missing import unknown_sensitivity
from perinatal_ews.schema import TOTAL_SUBGROUP

YEAR = 2024


@pytest.fixture(scope="module")
def cfg():
    return cfgmod.load_config()


@pytest.fixture(scope="module")
def demo():
    return synthetic.generate(seed=7)


@pytest.fixture(scope="module")
def base(cfg, demo):
    return _levels(detect(demo[0], cfg))


@pytest.fixture(scope="module")
def unchanged_by_size(demo):
    """Counties with no injected change, largest first."""
    tidy, truth = demo
    births = tidy[(tidy["subgroup"] == TOTAL_SUBGROUP) & (tidy["year"] == YEAR)].groupby("geo_id")["denominator"].sum()
    return [g for g in births.sort_values(ascending=False).index if g not in set(truth["geo_id"])]


def _levels(det):
    return det[det["subgroup"] == TOTAL_SUBGROUP].set_index(["geo_id", "indicator"])["level"].astype(str)


def _alerts(levels, keys):
    return {k for k in keys if levels[k] == "alert"}


def _injected(demo):
    return set(zip(demo[1]["geo_id"], demo[1]["indicator"]))


def test_drop_bookkeeping(demo):
    tidy = demo[0]
    geo = tidy["geo_id"].iloc[0]
    out = synthetic.drop_completeness(tidy, [geo], [YEAR], 0.3, seed=1)
    hit = (out["geo_id"] == geo) & (out["year"] == YEAR)
    # Births made unknown leave the denominator (and, if cases, the numerator) and are counted as unknown.
    assert np.allclose(out.loc[hit, "denominator"] + out.loc[hit, "unknown"], tidy.loc[hit, "denominator"])
    assert (out.loc[hit, "numerator"] <= tidy.loc[hit, "numerator"]).all()
    share = out.loc[hit, "unknown"].sum() / tidy.loc[hit, "denominator"].sum()
    assert 0.27 < share < 0.33
    # Other rows are untouched and have no unknowns; the input is not modified.
    pd.testing.assert_frame_equal(out.loc[~hit, tidy.columns], tidy.loc[~hit])
    assert (out.loc[~hit, "unknown"] == 0).all()
    assert "unknown" not in tidy.columns
    # The total is rebuilt as the sum of the subgroups.
    parts = out[hit & (out["subgroup"] != TOTAL_SUBGROUP)].groupby("indicator")[["numerator", "denominator", "unknown"]].sum()
    total = out[hit & (out["subgroup"] == TOTAL_SUBGROUP)].set_index("indicator")[["numerator", "denominator", "unknown"]]
    pd.testing.assert_frame_equal(parts.sort_index(), total.sort_index(), check_names=False)


def test_drop_of_cases_only_or_none(demo):
    tidy = demo[0]
    t = tidy[tidy["subgroup"] == TOTAL_SUBGROUP]
    geo = t["geo_id"].iloc[0]
    hit = (t["geo_id"] == geo) & (t["year"] == YEAR)
    spared = synthetic.drop_completeness(t, [geo], [YEAR], 0.5, case_relative_chance=0)
    assert (spared.loc[hit, "numerator"] == t.loc[hit, "numerator"]).all()  # cases always recorded
    assert (spared.loc[hit, "unknown"] > 0).all()
    none = synthetic.drop_completeness(t, [geo], [YEAR], 0.0)
    pd.testing.assert_frame_equal(none[t.columns], t)
    only_prenatal = synthetic.drop_completeness(t, [geo], [YEAR], 0.5, indicators=["preterm_birth"])
    assert set(only_prenatal.loc[only_prenatal["unknown"] > 0, "indicator"]) == {"preterm_birth"}
    with pytest.raises(ValueError):
        synthetic.drop_completeness(t, [geo], [YEAR], 1.5)
    with pytest.raises(ValueError):
        synthetic.drop_completeness(t, [geo], [YEAR], 0.2, case_relative_chance=-1)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_drop_at_random_creates_no_alerts(cfg, demo, base, unchanged_by_size, seed):
    """30% of births unknown at random in the 30 largest unchanged counties (half of all births)."""
    thinned = unchanged_by_size[:30]
    t = synthetic.drop_completeness(demo[0], thinned, [YEAR], 0.3, seed=seed)
    lv = _levels(detect(t, cfg))
    assert _alerts(lv, lv.index) == _alerts(base, base.index)
    injected = _injected(demo)
    found = lambda levels: sum(levels[k] in ("alert", "watch") for k in injected)
    assert found(lv) >= found(base) - 1  # power is barely affected


@pytest.mark.parametrize("seed", [0, 1])
def test_drop_sparing_cases_creates_alerts_that_the_sensitivity_analysis_reveals(cfg, demo, base, unchanged_by_size, seed):
    """Cases always recorded, 20% of other births unknown, in the 5 largest unchanged counties."""
    thinned = unchanged_by_size[:5]
    t = synthetic.drop_completeness(demo[0], thinned, [YEAR], 0.2, case_relative_chance=0, seed=seed)
    lv = _levels(detect(t, cfg))
    in_thinned = [k for k in lv.index if k[0] in thinned]
    false_alerts = _alerts(lv, in_thinned)
    assert not _alerts(base, in_thinned)
    assert len(false_alerts) >= 5  # the rate rises by about a fifth: many of the 20 county-indicators alert
    sens = unknown_sensitivity(t, cfg)
    sens = sens[sens["subgroup"] == TOTAL_SUBGROUP].set_index(["geo_id", "indicator"])
    for k in false_alerts:  # counting the unknowns as births without the outcome removes every one
        assert sens.at[k, "changed"] and sens.at[k, "level_included"] != "alert"
        assert sens.at[k, "unknown_share"] > 0.15
    others = [k for k in lv.index if k[0] not in thinned]
    assert _alerts(lv, others) <= _alerts(base, others)


def test_drop_of_cases_hides_a_real_change(cfg, demo, base):
    """In the largest county with an injected change, 75% of cases and 25% of other births go unknown."""
    tidy, truth = demo
    big = truth.sort_values("baseline_births").iloc[-1]
    key = (big["geo_id"], big["indicator"])
    assert base[key] == "alert"
    t = synthetic.drop_completeness(tidy, [key[0]], [YEAR], 0.25, case_relative_chance=3, indicators=[key[1]])
    assert _levels(detect(t, cfg))[key] != "alert"
    # The sensitivity analysis counts unknowns as births without the outcome, which lowers the rate
    # further, so it does not reveal a change hidden this way.
    sens = unknown_sensitivity(t, cfg)
    sens = sens[sens["subgroup"] == TOTAL_SUBGROUP].set_index(["geo_id", "indicator"])
    assert sens.at[key, "level_included"] != "alert"


def test_drop_of_cases_in_large_counties_creates_alerts_elsewhere(cfg, demo, base, unchanged_by_size):
    """Cases 2.5 times as likely to be unknown (50% vs 20%) in the 10 largest unchanged counties.

    Their rates fall, which lowers the rate of all counties and so, through the
    reference-trend adjustment, the expected rate of every other county.
    """
    thinned = unchanged_by_size[:10]
    t = synthetic.drop_completeness(demo[0], thinned, [YEAR], 0.2, case_relative_chance=2.5)
    det = detect(t, cfg)
    lv = _levels(det)
    others = [k for k in lv.index if k[0] not in thinned and k not in _injected(demo)]
    new = _alerts(lv, others) - _alerts(base, others)
    assert len(new) >= 5
    drift = det.groupby("indicator")["peer_drift"].first()
    base_drift = detect(demo[0], cfg).groupby("indicator")["peer_drift"].first()
    assert (drift < base_drift).all()
    sens = unknown_sensitivity(t, cfg)
    sens = sens[sens["subgroup"] == TOTAL_SUBGROUP].set_index(["geo_id", "indicator"])
    assert all(sens.at[k, "level_included"] == "alert" for k in new)  # not revealed: their own data are complete
