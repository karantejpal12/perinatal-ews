import numpy as np
import pandas as pd
import pytest

from perinatal_ews import config as cfgmod
from perinatal_ews import synthetic
from perinatal_ews.persistent import persistent_burden, worst_quintile


@pytest.fixture(scope="module")
def cfg():
    return cfgmod.load_config()


def _panel(rates_by_area, years, indicator="low_birth_weight", births=10_000):
    """Tidy table where area i has rate rates_by_area[i][j] in years[j]."""
    rows = []
    for i, rates in enumerate(rates_by_area):
        for y, r in zip(years, rates):
            num = np.nan if r is None else round(r * births)
            rows.append(dict(geo_id=f"9{i:04d}", geo_name=f"Area {i} (synthetic)", state="Alder", year=y,
                             indicator=indicator, subgroup="All", numerator=num, denominator=births))
    return pd.DataFrame(rows)


YEARS = list(range(2020, 2025))


def test_worst_quintile_includes_ties_and_respects_direction():
    s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 9])
    assert worst_quintile(s).tolist() == [False] * 8 + [True, True]
    assert worst_quintile(s, higher_is_worse=False).tolist() == [True, True] + [False] * 8
    ties = pd.Series([1, 2, 3, 5, 5])
    assert worst_quintile(ties).sum() == 2


def test_persistent_needs_three_of_five_worst_years(cfg):
    base = [[0.05 + 0.001 * i] * 5 for i in range(10)]
    base[0] = [0.20, 0.20, 0.20, 0.05, 0.05]   # worst in 3 of 5 years -> persistent
    base[1] = [0.20, 0.20, 0.05, 0.05, 0.05]   # worst in 2 of 5 -> not persistent
    # area 9 is the usual top rate; it is pushed out of the worst fifth in the years areas 0 and 1 lead
    res = persistent_burden(_panel(base, YEARS), cfg).set_index("geo_id")
    assert res.at["90000", "status"] == "persistent"
    assert res.at["90000", "years_in_worst_quintile"] == 3
    assert res.at["90000", "worst_quintile_years"] == "2020,2021,2022"
    assert res.at["90001", "status"] == "not persistent"
    assert res.at["90001", "years_in_worst_quintile"] == 2
    assert res.at["90009", "years_in_worst_quintile"] == 3       # worst-but-one rate in 2022-2024
    assert res.at["90005", "status"] == "not persistent"
    assert (res["window_start"] == 2020).all() and (res["window_end"] == 2024).all()


def test_stable_high_rate_is_persistent_but_not_a_change_alert(cfg):
    from perinatal_ews.detect import detect
    years = list(range(2016, 2025))
    rng = np.random.default_rng(1)
    rates = [list(0.08 + 0.002 * rng.standard_normal(len(years))) for _ in range(20)]
    rates[3] = [0.13] * len(years)                              # high every year, never changing
    tidy = _panel(rates, years)
    pb = persistent_burden(tidy, cfg).set_index("geo_id")
    assert pb.at["90003", "status"] == "persistent"
    assert pb.at["90003", "years_in_worst_quintile"] == 5
    det = detect(tidy, cfg).set_index("geo_id")
    assert det.at["90003", "level"] in ("stable", "watch")


def test_missing_years_are_skipped_not_counted(cfg):
    base = [[0.05 + 0.001 * i] * 5 for i in range(10)]
    base[0] = [0.20, None, None, None, 0.20]   # only two ranked years -> insufficient data
    base[2] = [0.20, None, 0.20, 0.20, None]   # three ranked years, all worst -> persistent
    res = persistent_burden(_panel(base, YEARS), cfg).set_index("geo_id")
    assert res.at["90000", "status"] == "insufficient data"
    assert res.at["90000", "years_ranked"] == 2
    assert res.at["90002", "status"] == "persistent"
    assert res.at["90002", "years_ranked"] == 3


def test_years_with_too_few_areas_are_not_ranked(cfg):
    res = persistent_burden(_panel([[0.1] * 5, [0.2] * 5, [0.3] * 5], YEARS), cfg)
    assert (res["years_ranked"] == 0).all()
    assert (res["status"] == "insufficient data").all()


def test_lower_is_worse_and_small_counts_are_marked_unreliable(cfg):
    cfg = {**cfg, "indicators": {**cfg["indicators"],
                                 "adequate_care": {"label": "Adequate care", "direction": "lower_is_worse"}}}
    base = [[0.80 + 0.001 * i] * 5 for i in range(10)]
    base[4] = [0.50] * 5
    res = persistent_burden(_panel(base, YEARS, indicator="adequate_care"), cfg).set_index("geo_id")
    assert res.at["90004", "status"] == "persistent"
    assert res.at["90009", "years_in_worst_quintile"] == 0
    small = _panel([[0.05 + 0.001 * i] * 5 for i in range(10)], YEARS, births=150)
    res = persistent_burden(small, cfg).set_index("geo_id")
    assert res.at["90009", "status"] == "persistent"
    assert not res.at["90009", "reliable"]                      # about 9 events a year
    assert res.at["90000", "reliable"]                          # never in the worst fifth


def test_runs_on_synthetic_data_by_subgroup_and_window(cfg):
    tidy, _ = synthetic.generate(seed=7)
    res = persistent_burden(tidy, cfg, end_year=2022, window=4, min_years=2, subgroups=["All", "Medicaid"])
    assert set(res["subgroup"]) == {"All", "Medicaid"}
    assert (res["window_start"] == 2019).all() and (res["window_end"] == 2022).all()
    n_areas = tidy["geo_id"].nunique()
    assert len(res) == n_areas * tidy["indicator"].nunique() * 2
    share = (res["years_in_worst_quintile"].sum() / res["years_ranked"].sum())
    assert share == pytest.approx(0.2, abs=0.01)
    with pytest.raises(ValueError):
        persistent_burden(tidy, cfg, window=3, min_years=4)
