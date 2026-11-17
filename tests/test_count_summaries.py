"""Persistent burden, state sums and state patterns for indicators per population (``model: count``).

Synthetic data only. A count per population (for example teen births per female
aged 15-19, or visits per person) can exceed 1; nothing in input validation,
the persistent-burden ranking, `to_state` or the state patterns may cap it or
treat it as a share of births.
"""
import copy

import numpy as np
import pandas as pd
import pytest

from perinatal_ews import cli
from perinatal_ews import config as cfgmod
from perinatal_ews.detect import detect
from perinatal_ews.monitor import state_clusters
from perinatal_ews.persistent import persistent_burden
from perinatal_ews.pooling import to_state
from perinatal_ews.schema import SchemaError, validate

YEARS = list(range(2016, 2025))
IND = "visits_per_person"


@pytest.fixture(scope="module")
def cfg():
    c = copy.deepcopy(cfgmod.load_config())
    c["indicators"][IND] = {"label": "Visits per person", "direction": "higher_is_worse", "model": "count",
                            "set": "more"}
    return c


def _counts(seed=5, n=60, base_rate=1.4, states=3, shock=None, factor=1.5):
    """Counts per population with rates around `base_rate`; counties in `shock` rise by `factor` in 2024."""
    rng = np.random.default_rng(seed)
    pop = np.exp(rng.uniform(np.log(3_000), np.log(40_000), n)).round()
    effect = rng.gamma(30, 1 / 30, n)
    rows = []
    for i in range(n):
        for j, year in enumerate(YEARS):
            mu = base_rate * effect[i] * 0.99 ** j
            if shock is not None and i in shock and year == YEARS[-1]:
                mu *= factor
            rows.append(dict(indicator=IND, subgroup="All", geo_id=f"9{i:04d}", geo_name=f"County {i} (synthetic)",
                             state=f"S{i % states}", year=year, numerator=float(rng.poisson(mu * pop[i])),
                             denominator=float(pop[i])))
    return pd.DataFrame(rows)


def test_validate_allows_rates_above_one_only_for_count_indicators():
    t = _counts(n=6)
    assert (t["numerator"] > t["denominator"]).any()
    with pytest.raises(SchemaError, match=IND):
        validate(t)
    out = validate(t, count_indicators=[IND])
    assert len(out) == len(t)
    # Shares of births are still checked when a count indicator is in the same table.
    share = t.head(1).assign(indicator="low_birth_weight")
    with pytest.raises(SchemaError, match="low_birth_weight"):
        validate(pd.concat([t, share]), count_indicators=[IND])


def test_persistent_burden_ranks_rates_above_one(cfg):
    years = YEARS[-5:]
    rows = []
    for i in range(10):
        for k, y in enumerate(years):
            rate = 1.2 + 0.01 * i
            if i == 0 and k < 3:
                rate = 2.5          # worst in 3 of 5 years -> persistent
            if i == 1 and k < 2:
                rate = 2.5          # worst in 2 of 5 -> not persistent
            rows.append(dict(indicator=IND, subgroup="All", geo_id=f"9{i:04d}", geo_name=f"Area {i}", state="S0",
                             year=y, numerator=round(rate * 10_000), denominator=10_000.0))
    res = persistent_burden(pd.DataFrame(rows), cfg).set_index("geo_id")
    assert res.loc["90000", "status"] == "persistent"
    assert res.loc["90000", "worst_quintile_years"] == "2020,2021,2022"
    assert res.loc["90001", "status"] == "not persistent"
    assert res.loc["90001", "years_in_worst_quintile"] == 2
    # Areas 8 and 9 have the highest rates in the other years: three of five each.
    assert res.loc["90009", "years_in_worst_quintile"] == 3
    assert res["reliable"].all()


def test_persistent_burden_is_unchanged_by_rescaling_a_count_rate(cfg):
    """Rates per person and per 1,000 people rank the same; only the order of areas matters."""
    t = _counts()
    per_person = persistent_burden(t, cfg)
    per_1000 = persistent_burden(t.assign(denominator=t["denominator"] / 1000), cfg)
    cols = ["geo_id", "years_in_worst_quintile", "worst_quintile_years", "status"]
    pd.testing.assert_frame_equal(per_person[cols].sort_values("geo_id").reset_index(drop=True),
                                  per_1000[cols].sort_values("geo_id").reset_index(drop=True))


def test_to_state_sums_events_and_population():
    t = _counts()
    s = to_state(t)
    one = t[(t["state"] == "S1") & (t["year"] == 2024)]
    row = s[(s["state"] == "S1") & (s["year"] == 2024)].iloc[0]
    assert row["numerator"] == one["numerator"].sum()
    assert row["denominator"] == one["denominator"].sum()
    assert row["numerator"] / row["denominator"] > 1
    # A missing county makes the state-year missing, not a lower rate.
    t.loc[(t["state"] == "S1") & (t["year"] == 2024), "numerator"] = [np.nan] + [1.0] * (len(one) - 1)
    s2 = to_state(t)
    assert s2[(s2["state"] == "S1") & (s2["year"] == 2024)]["numerator"].isna().all()


def test_state_patterns_use_pooled_rates_per_population(cfg):
    rng = np.random.default_rng(0)
    shock = set(int(i) for i in rng.choice(np.arange(0, 60, 3), 18, replace=False))  # 18 of 20 counties in S0
    t = _counts(shock=shock)
    res = detect(t, cfg)
    sp = state_clusters(res, t, cfg)
    assert list(sp["state"]) == ["S0"]
    row = sp.iloc[0]
    det = cfg["detection"]
    last = 2024 - det.get("guard_years", 1)
    base = t[t["year"].between(last - det["baseline_years"], last - 1) & (t["state"] == "S0")]
    cur = t[(t["year"] == 2024) & (t["state"] == "S0")]
    assert row["state_rate_baseline"] == pytest.approx(base["numerator"].sum() / base["denominator"].sum())
    assert row["state_rate_current"] == pytest.approx(cur["numerator"].sum() / cur["denominator"].sum())
    assert row["state_rate_current"] > 1.5
    assert row["state_change_vs_national"] > 1.2


@pytest.mark.parametrize("level", ["county", "state"])
def test_run_command_with_a_count_indicator(tmp_path, level):
    """`perinatal-ews run --config` reads rates above 1 for a count indicator and scores it at both levels."""
    t = _counts()
    path = tmp_path / "tidy.csv"
    t.to_csv(path, index=False)
    conf = tmp_path / "config.yaml"
    conf.write_text(f"indicators:\n  {IND}:\n    label: Visits per person\n    direction: higher_is_worse\n"
                    f"    model: count\n    set: more\n")
    out = tmp_path / "out"
    cli.main(["run", "--input", str(path), "--config", str(conf), "--out", str(out), "--level", level])
    det = pd.read_csv(out / "detections.csv")
    assert set(det["indicator"]) == {IND}
    assert det["geo_id"].nunique() == (60 if level == "county" else 3)
    assert (det["expected_rate"] > 1).mean() > 0.8  # not capped below 1 as a share of births would be
    pb = pd.read_csv(out / "persistent_burden.csv")
    assert len(pb) == det["geo_id"].nunique()
    # The bulletin covers only the original four indicators, so none is written for this input.
    assert not (out / "report.html").exists()
    # Without the config, the same file is rejected as shares of births above 100%.
    with pytest.raises(SchemaError):
        cli.main(["run", "--input", str(path), "--out", str(tmp_path / "out2"), "--level", level])
