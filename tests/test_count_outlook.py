"""Full-year outlook for counts per population (``model: count``), on synthetic state counts.

The year-so-far denominator is person-time (population times the share of the year covered), so the
remaining months have a denominator of their own. Rates above 1 are used on purpose: the binomial
simulation cannot produce them.
"""
import copy

import numpy as np
import pandas as pd
import pytest

from perinatal_ews import config as cfgmod
from perinatal_ews.outlook import backtest, outlook, remaining_table

IND = "visits_per_person"
STATES = [f"S{i:02d}" for i in range(30)]
M = 8                       # months known
EARLY, LATE = 0.95, 1.10    # seasonal factors for January-August and September-December


def _feed(rate=2.0, bump_state=None, bump=1.35, seed=5):
    rng = np.random.default_rng(seed)
    pop = np.exp(rng.uniform(np.log(50_000), np.log(2_000_000), len(STATES))).round()
    effect = rng.gamma(50, 1 / 50, len(STATES))
    ytd, full = [], []
    for s, st in enumerate(STATES):
        for year in range(2016, 2027):
            r = rate * effect[s] * 0.99 ** (year - 2016) * rng.gamma(400, 1 / 400)
            if st == bump_state and year == 2026:
                r *= bump
            d_ytd, d_rem = pop[s] * M / 12, pop[s] * (12 - M) / 12
            n_ytd = rng.poisson(r * EARLY * d_ytd)
            n_rem = rng.poisson(r * LATE * d_rem)
            key = {"geo_id": st, "geo_name": f"State {st}", "state": st, "indicator": IND, "subgroup": "All",
                   "year": year}
            ytd.append({**key, "numerator": float(n_ytd), "denominator": d_ytd})
            if year < 2026:
                full.append({**key, "numerator": float(n_ytd + n_rem), "denominator": d_ytd + d_rem})
    return pd.DataFrame(ytd), pd.DataFrame(full)


@pytest.fixture(scope="module")
def cfg():
    c = copy.deepcopy(cfgmod.load_config())
    c["indicators"][IND] = {"label": "Visits per person", "direction": "higher_is_worse", "model": "count"}
    return c


def test_seasonal_step_is_on_the_log_rate_scale():
    ytd, full = _feed()
    rem = remaining_table(ytd, full, {IND})
    # remaining-months rate / January-August rate is LATE / EARLY, whatever the level of the rate
    assert abs(rem["d"].mean() - np.log(LATE / EARLY)) < 0.01
    assert (rem["var_d"] > 0).all()


def test_outlook_projects_rates_above_one_with_poisson_noise(cfg):
    ytd, full = _feed(bump_state="S03")
    ol = outlook(ytd, full, cfg, 2026, [2023, 2024, 2025], n_draws=60)
    assert len(ol) == len(STATES)
    assert (ol["projected_rate"] > 1).all() and (ol["rate_ytd"] > 1).all()
    assert (ol["projected_low80"] <= ol["projected_rate"]).all()
    assert (ol["projected_rate"] <= ol["projected_high80"]).all()
    # the full year sits above the year so far, because September-December run higher
    assert (ol["projected_rate"] > ol["rate_ytd"]).mean() > 0.9
    assert ol["p_flag"].between(0, 1).all() and (ol["p_alert"] <= ol["p_flag"] + 1e-9).all()
    o = ol.set_index("geo_id")
    assert o.loc["S03", "p_flag"] > 0.9                       # the injected rise carries into the full year
    assert o.drop(index="S03")["p_flag"].mean() < 0.15


def test_backtest_intervals_cover_the_actual_full_year(cfg):
    ytd, full = _feed()
    bt, summary = backtest(ytd, full, cfg, [2023, 2024, 2025], n_draws=40)
    assert summary["state_indicators"] == 3 * len(STATES)
    assert 0.6 <= summary["interval80_coverage"] <= 1.0
    # projection error is small relative to the rate: within 5% for nearly every state-year
    rel = (bt["projected_rate"] - bt["actual_rate"]).abs() / bt["actual_rate"]
    assert (rel < 0.05).mean() > 0.95
