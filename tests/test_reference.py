import numpy as np
import pandas as pd
import pytest

from perinatal_ews.reference import REFERENCE_SUBGROUP, newcombe_difference, reference_comparison

YEARS = list(range(2018, 2025))


def _panel(counties, indicator="preterm_birth"):
    """counties: {geo_id: {year: (total_k, total_n, ref_k, ref_n)}}; None in place of a tuple = suppressed."""
    rows = []
    for geo, by_year in counties.items():
        for y, cells in by_year.items():
            tk, tn, rk, rn = cells if cells is not None else (np.nan, np.nan, np.nan, np.nan)
            for sub, k, n in (("All", tk, tn), (REFERENCE_SUBGROUP, rk, rn)):
                rows.append(dict(geo_id=geo, geo_name=f"County {geo} (synthetic)", state="Alder", year=y,
                                 indicator=indicator, subgroup=sub, numerator=k, denominator=n))
    return pd.DataFrame(rows)


def _one(res, geo, year):
    r = res[(res["geo_id"] == geo) & (res["target_year"] == year)]
    assert len(r) == 1
    return r.iloc[0]


def test_one_year_enough_when_reference_reaches_60():
    t = _panel({"90001": {y: (1000, 10_000, 60, 1_000) for y in YEARS}})
    r = _one(reference_comparison(t), "90001", 2024)
    assert r["status"] == "compared"
    assert r["window"] == "2024-2024" and r["n_years"] == 1
    assert r["rate"] == pytest.approx(0.10)
    assert r["ref_rate"] == pytest.approx(0.06)
    assert r["rate_ratio"] == pytest.approx(0.10 / 0.06)
    assert r["excess_rate"] == pytest.approx(0.04)
    assert r["excess_share"] == pytest.approx(0.4)
    assert r["excess_ci_low"] < 0.04 < r["excess_ci_high"]


def test_pools_adjacent_years_until_60_reference_events_and_never_more():
    t = _panel({"90001": {y: (500, 5_000, 25, 600) for y in YEARS}})
    r = _one(reference_comparison(t), "90001", 2024)
    assert r["status"] == "compared"
    assert r["years_used"] == "2022,2023,2024"         # 25 + 25 + 25 = 75 >= 60; two years (50) is not enough
    assert r["ref_numerator"] == 75 and r["numerator"] == 1500
    assert r["denominator"] == 15_000 and r["ref_denominator"] == 1_800


def test_insufficient_data_after_max_span_gives_no_rate():
    t = _panel({"90001": {y: (500, 5_000, 10, 600) for y in YEARS}})
    r = _one(reference_comparison(t, max_span=5), "90001", 2024)
    assert r["status"] == "insufficient data"
    assert r["n_years"] == 5 and r["ref_numerator"] == 50
    for col in ("rate", "ref_rate", "rate_ratio", "excess_rate", "excess_ci_low", "excess_ci_high", "excess_share"):
        assert np.isnan(r[col]), col
    ok = _one(reference_comparison(t, max_span=6), "90001", 2024)
    assert ok["status"] == "compared" and ok["window"] == "2019-2024"


def test_suppressed_years_are_skipped_and_listed_not_counted_as_zero():
    cells = {y: (500, 5_000, 30, 600) for y in YEARS}
    cells[2023] = None                                  # suppressed in both
    t = _panel({"90001": cells})
    r = _one(reference_comparison(t), "90001", 2024)
    assert r["years_used"] == "2022,2024"
    assert r["years_missing_or_suppressed"] == "2023"
    assert r["window"] == "2022-2024"
    assert r["ref_numerator"] == 60 and r["numerator"] == 1000


def test_year_with_reference_suppressed_is_skipped_for_the_total_too():
    cells = {y: (500, 5_000, 30, 600) for y in YEARS}
    t = _panel({"90001": cells})
    t.loc[(t["year"] == 2024) & (t["subgroup"] == REFERENCE_SUBGROUP), "numerator"] = np.nan
    r = _one(reference_comparison(t), "90001", 2024)
    assert r["years_used"] == "2022,2023"              # same years for the county and its reference group
    assert r["numerator"] == 1000 and r["ref_numerator"] == 60


def test_missing_years_before_the_data_begin_are_insufficient():
    t = _panel({"90001": {y: (500, 5_000, 20, 600) for y in YEARS}})
    r = _one(reference_comparison(t), "90001", 2018)
    assert r["status"] == "insufficient data"
    assert r["years_missing_or_suppressed"] == "2014,2015,2016,2017"


def test_excess_interval_matches_simulation():
    """The interval accounts for the reference group being part of the total."""
    rk, rn, ok_, on = 120, 2_000, 900, 8_000            # reference and other births
    t = _panel({"90001": {2024: (rk + ok_, rn + on, rk, rn)}})
    r = _one(reference_comparison(t), "90001", 2024)
    rng = np.random.default_rng(0)
    sims = []
    for _ in range(20_000):
        a = rng.binomial(rn, rk / rn)
        b = rng.binomial(on, ok_ / on)
        sims.append((a + b) / (rn + on) - a / rn)
    lo, hi = np.quantile(sims, [0.025, 0.975])
    assert r["excess_ci_low"] == pytest.approx(lo, abs=0.002)
    assert r["excess_ci_high"] == pytest.approx(hi, abs=0.002)


def test_all_births_in_reference_group_gives_zero_excess():
    t = _panel({"90001": {2024: (80, 1_000, 80, 1_000)}})
    r = _one(reference_comparison(t), "90001", 2024)
    assert r["excess_rate"] == 0 and r["excess_ci_low"] == 0 and r["excess_ci_high"] == 0
    assert r["rate_ratio"] == 1


def test_counties_are_compared_with_their_own_reference_group():
    t = _panel({"90001": {2024: (1000, 10_000, 60, 1_000)},
                "90002": {2024: (1000, 10_000, 90, 1_000)}})
    res = reference_comparison(t)
    assert _one(res, "90001", 2024)["ref_rate"] == pytest.approx(0.06)
    assert _one(res, "90002", 2024)["ref_rate"] == pytest.approx(0.09)


def test_indicators_are_pooled_separately():
    a = _panel({"90001": {y: (500, 5_000, 60, 600) for y in YEARS}}, indicator="preterm_birth")
    b = _panel({"90001": {y: (300, 5_000, 20, 600) for y in YEARS}}, indicator="low_birth_weight")
    res = reference_comparison(pd.concat([a, b]), target_years=[2024]).set_index("indicator")
    assert res.at["preterm_birth", "n_years"] == 1
    assert res.at["low_birth_weight", "n_years"] == 3


def test_reference_larger_than_total_is_an_error():
    t = _panel({"90001": {2024: (50, 1_000, 60, 1_000)}})
    with pytest.raises(ValueError, match="part of the county total"):
        reference_comparison(t)


def test_no_reference_rows_is_an_error():
    t = _panel({"90001": {2024: (100, 1_000, 60, 500)}})
    with pytest.raises(ValueError, match="reference subgroup"):
        reference_comparison(t[t["subgroup"] == "All"])


def test_newcombe_difference_known_value():
    # Newcombe (1998), Statistics in Medicine 17:873-890, Table II example (b): 56/70 - 48/80,
    # method 10 interval 0.0524 to 0.3339.
    d, lo, hi = newcombe_difference(56, 70, 48, 80)
    assert d == pytest.approx(0.2)
    assert lo == pytest.approx(0.0524, abs=1e-4)
    assert hi == pytest.approx(0.3339, abs=1e-4)
