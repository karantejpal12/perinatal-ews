"""Pooled small-numbers estimates for indicators that are counts per population (``model: count``).

Synthetic data only. Shares of births keep their Wilson intervals and binomial rate-ratio variance.
"""
import numpy as np
import pandas as pd
import pytest
import yaml

from perinatal_ews.indicators import poisson_rate_interval, wilson_interval
from perinatal_ews.pooling import (
    compare_windows,
    pooled_estimates,
    small_numbers_analysis,
)


def test_poisson_interval_matches_exact_gamma_limits():
    lo, hi = poisson_rate_interval([0, 10, 100], [1, 1, 1000])
    assert lo[0] == 0 and hi[0] == pytest.approx(3.689, abs=1e-3)       # Garwood limits for 0 events
    assert (lo[1], hi[1]) == pytest.approx((4.795, 18.390), abs=1e-3)     # and for 10 events
    assert (lo[2], hi[2]) == pytest.approx((0.08136, 0.12163), abs=1e-4)  # 100 events per 1,000
    lo, hi = poisson_rate_interval([5, np.nan], [0, 10])
    assert np.isnan(lo).all() and np.isnan(hi).all()


def test_poisson_interval_covers_at_least_nominal():
    rng = np.random.default_rng(3)
    for mu in (3, 25, 200):
        k = rng.poisson(mu, 20_000)
        lo, hi = poisson_rate_interval(k, np.ones_like(k, dtype=float))
        assert ((lo <= mu) & (mu <= hi)).mean() >= 0.95                   # exact intervals are conservative


def _teen_tidy():
    """Teen-birth-like counts per population for two counties, plus a share-of-births indicator."""
    rows = []
    for y in range(2016, 2025):
        for geo, pop, rate in (("00001", 4_000, 0.020), ("00002", 200, 0.030)):
            rows.append(dict(geo_id=geo, geo_name=f"County {geo}", state="ZZ", year=y, indicator="teen_birth_rate",
                             subgroup="All", numerator=float(round(pop * rate * (1.3 if y >= 2022 else 1))),
                             denominator=float(pop)))
            rows.append(dict(geo_id=geo, geo_name=f"County {geo}", state="ZZ", year=y, indicator="preterm_birth",
                             subgroup="All", numerator=float(round(pop * 0.1)), denominator=float(pop)))
    return pd.DataFrame(rows)


def test_pooled_count_indicator_gets_poisson_intervals_and_shares_are_unchanged():
    t = _teen_tidy()
    plain = pooled_estimates(t, window=3)
    p = pooled_estimates(t, window=3, count_indicators=["teen_birth_rate"])
    share = p.indicator == "preterm_birth"
    pd.testing.assert_frame_equal(p[share], plain[share])                 # binomial results unchanged
    teen = p[~share]
    lo, hi = poisson_rate_interval(teen["numerator"], teen["denominator"])
    assert np.allclose(teen["ci_low"], lo) and np.allclose(teen["ci_high"], hi)
    wlo, whi = wilson_interval(teen["numerator"], teen["denominator"])
    assert (teen["ci_high"].to_numpy() - teen["ci_low"].to_numpy() > whi - wlo).all()  # no (1-p) shrinkage
    assert (teen["status"] == plain.loc[~share, "status"]).all()          # reliability still by event count


def test_count_rates_above_one_get_a_sensible_interval():
    # Events can outnumber the population (for example visits per person); Wilson would cap at 1.
    t = pd.DataFrame([dict(geo_id="X", geo_name="X", state="ZZ", year=y, indicator="visits", subgroup="All",
                           numerator=150.0, denominator=100.0) for y in (2022, 2023, 2024)])
    r = pooled_estimates(t, window=3, count_indicators=["visits"]).iloc[0]
    assert r["rate"] == 1.5 and r["ci_low"] < 1.5 < r["ci_high"] and r["ci_low"] > 1.3


def test_compare_windows_uses_poisson_variance_for_counts():
    t = _teen_tidy()
    p, c = small_numbers_analysis(t, window=3, combine={}, count_indicators=["teen_birth_rate"])
    c = c.set_index(["geo_id", "indicator"])
    big = c.loc[("00001", "teen_birth_rate")]
    a = p[(p.geo_id == "00001") & (p.indicator == "teen_birth_rate") & (p.window == "2022-2024")].iloc[0]
    b = p[(p.geo_id == "00001") & (p.indicator == "teen_birth_rate") & (p.window == "2019-2021")].iloc[0]
    se = np.sqrt(1 / a["numerator"] + 1 / b["numerator"])
    assert big["ci_low"] == pytest.approx(big["rate_ratio"] * np.exp(-1.96 * se))
    assert big["change"] == "higher"
    plain = compare_windows(pooled_estimates(t, window=3), window=3).set_index(["geo_id", "indicator"])
    assert c.loc[("00001", "preterm_birth"), "ci_low"] == plain.loc[("00001", "preterm_birth"), "ci_low"]
    assert c.loc[("00002", "teen_birth_rate"), "change"].startswith("not compared")   # 6 a year, 18 in 2019-2021


def test_pooled_command_reads_count_indicators_from_config(tmp_path):
    from perinatal_ews.cli import main

    _teen_tidy().to_csv(tmp_path / "tidy.csv", index=False)
    (tmp_path / "cfg.yaml").write_text(yaml.safe_dump({"indicators": {"teen_birth_rate": {
        "label": "Teen birth rate", "direction": "higher_is_worse", "model": "count"}}}))
    main(["pooled", "--input", str(tmp_path / "tidy.csv"), "--out", str(tmp_path / "a")])
    main(["pooled", "--input", str(tmp_path / "tidy.csv"), "--out", str(tmp_path / "b"),
          "--config", str(tmp_path / "cfg.yaml")])
    a = pd.read_csv(tmp_path / "a" / "pooled_estimates.csv")
    b = pd.read_csv(tmp_path / "b" / "pooled_estimates.csv")
    teen = b.indicator == "teen_birth_rate"
    lo, _ = poisson_rate_interval(b.loc[teen, "numerator"], b.loc[teen, "denominator"])
    assert np.allclose(b.loc[teen, "ci_low"], lo, equal_nan=True)
    assert not np.allclose(a.loc[teen, "ci_low"], lo, equal_nan=True)     # without the config: Wilson
    pd.testing.assert_frame_equal(a[~teen].reset_index(drop=True), b[~teen].reset_index(drop=True))
