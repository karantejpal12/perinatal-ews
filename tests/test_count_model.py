"""Count (Poisson) model in detection, for indicators per population such as teen births.

Synthetic data only: county populations, a common national trend, county effects
and extra year-to-year variation, with known increases injected in some counties.
"""
import copy

import numpy as np
import pandas as pd
import pytest

from perinatal_ews import config as cfgmod
from perinatal_ews import detect, synthetic

YEARS = list(range(2016, 2025))


def _count_data(seed=11, n=400, base_rate=0.015, inject=None, factor=1.6):
    """Teen-birth-like counts: births to females 15-19 over the female population 15-19."""
    rng = np.random.default_rng(seed)
    pop = np.exp(rng.uniform(np.log(1_500), np.log(60_000), n)).round()
    county = rng.gamma(20, 1 / 20, n)  # county effect, mean 1
    rows = []
    for i in range(n):
        for j, year in enumerate(YEARS):
            mu = base_rate * county[i] * 0.97 ** j * rng.gamma(200, 1 / 200)  # national decline, small extra variation
            if inject is not None and i in inject and year == YEARS[-1]:
                mu *= factor
            rows.append({"indicator": "teen_birth_rate", "subgroup": "All", "geo_id": f"{i:05d}",
                         "geo_name": f"County {i}", "state": "ZZ", "year": year,
                         "numerator": float(rng.poisson(mu * pop[i])), "denominator": float(pop[i])})
    return pd.DataFrame(rows), pop


@pytest.fixture(scope="module")
def cfg():
    c = copy.deepcopy(cfgmod.load_config())
    c["indicators"]["teen_birth_rate"] = {"label": "Teen birth rate", "direction": "higher_is_worse",
                                          "model": "count"}
    return c


def test_count_model_is_calibrated_without_changes(cfg):
    tidy, _ = _count_data()
    res = detect.detect(tidy, cfg)
    z = res["z"].dropna()
    assert len(z) == 400
    assert abs(z.mean()) < 0.2
    assert 0.8 < z.std() < 1.25
    assert (res["level"] == "alert").mean() < 0.02
    assert (res["expected_rate"] > 0).all()


def test_count_model_finds_injected_increases_in_large_counties(cfg):
    _, pop = _count_data()
    large = set(np.argsort(pop)[-15:])
    tidy, _ = _count_data(inject=large)
    res = detect.detect(tidy, cfg).set_index("geo_id")
    hit = res.loc[[f"{i:05d}" for i in large], "level"]
    assert (hit == "alert").all()
    others = res.drop(index=[f"{i:05d}" for i in large])
    assert (others["level"] == "alert").mean() < 0.02


def test_count_model_trend_is_percent_change_in_rate(cfg):
    tidy, _ = _count_data()
    res = detect.detect(tidy, cfg)
    big = res.nlargest(50, "births")["apc"]
    # simulated national decline of 3% a year
    assert -5 < big.median() < -1


def test_count_model_allows_rates_above_one(cfg):
    """A count per population can exceed 1 (for example visits per person); binomial clipping must not apply."""
    tidy, _ = _count_data(base_rate=1.5)
    res = detect.detect(tidy, cfg)
    assert res["expected_rate"].max() > 1.5  # would be capped just below 1 under the binomial model
    assert (res["expected_rate"] > 1).mean() > 0.5
    assert abs(res["z"].mean()) < 0.25


def test_count_and_binomial_agree_for_rare_outcomes(cfg):
    tidy, _ = _count_data(base_rate=0.005)
    c = detect.detect(tidy, cfg).set_index("geo_id")
    b_cfg = copy.deepcopy(cfg)
    b_cfg["indicators"]["teen_birth_rate"]["model"] = "binomial"
    b = detect.detect(tidy, b_cfg).set_index("geo_id").loc[c.index]
    assert np.allclose(c["expected"], b["expected"], rtol=0.01)
    assert np.allclose(c["z"], b["z"], atol=0.05)


def test_binomial_is_the_default_and_unchanged():
    base = cfgmod.load_config()
    tidy, _ = synthetic.generate(seed=7)
    explicit = copy.deepcopy(base)
    for spec in explicit["indicators"].values():
        spec["model"] = "binomial"
    a = detect.detect(tidy, base)
    b = detect.detect(tidy, explicit)
    pd.testing.assert_frame_equal(a, b)


def test_unknown_model_is_rejected(cfg):
    tidy, _ = _count_data(n=20)
    bad = copy.deepcopy(cfg)
    bad["indicators"]["teen_birth_rate"]["model"] = "poisson"
    with pytest.raises(ValueError, match="unknown model 'poisson'"):
        detect.detect(tidy, bad)
