"""Synthetic natality data with known, injected deterioration.

Used for demos, tests and the monitoring backtest: because we know which
counties were made worse, we can measure how well the detector finds them.
All geographies are fictional (FIPS-style codes starting with 9, which no
real US county uses) so synthetic output can never be mistaken for real data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import TOTAL_SUBGROUP

# baseline rate in first year, change in log-odds per year (loosely based on recent US levels)
INDICATOR_PARAMS = {
    "late_no_prenatal_care": (0.062, 0.020),
    "preterm_birth": (0.102, 0.010),
    "low_birth_weight": (0.083, 0.006),
    "gestational_hypertension": (0.075, 0.050),
}
SUBGROUP_OFFSETS = {"Medicaid": 0.25, "Private insurance": -0.15, "Other payer": 0.05}

STATE_NAMES = ["Alder", "Birch", "Cedar", "Dogwood", "Elm"]
COUNTY_WORDS = ["Ridge", "Valley", "Harbor", "Prairie", "Lake", "Summit", "River", "Forest", "Bay", "Mesa",
                "Hollow", "Grove", "Point", "Falls", "Crossing", "Bluff", "Glen", "Plains", "Shore", "Heights"]


def _logit(p):
    return np.log(p / (1 - p))


def _expit(x):
    return 1 / (1 + np.exp(-x))


def size_class(births: float) -> str:
    if births < 1_000:
        return "small (<1k births)"
    if births < 5_000:
        return "medium (1k-5k)"
    return "large (5k+)"


def generate(
    n_counties: int = 150,
    years: tuple[int, int] = (2016, 2024),
    n_injected: int = 14,
    onset_years: int = 2,
    seed: int = 7,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (tidy, truth). `truth` lists every injected county-indicator deterioration."""
    rng = np.random.default_rng(seed)
    year_list = list(range(years[0], years[1] + 1))

    counties = []
    for i in range(n_counties):
        state = STATE_NAMES[i % len(STATE_NAMES)]
        name = f"{rng.choice(COUNTY_WORDS)} {rng.choice(COUNTY_WORDS)} County"
        births = float(np.clip(np.exp(rng.normal(np.log(2600), 1.05)), 250, 90_000))
        medicaid = float(np.clip(rng.beta(8, 11), 0.15, 0.75))
        other = float(np.clip(rng.beta(2, 25), 0.02, 0.2))
        counties.append({
            "geo_id": f"9{i // 30 + 1}{i % 30 + 1:03d}",
            "geo_name": f"{name} (synthetic)",
            "state": f"{state} (synthetic)",
            "births": births,
            "mix": {"Medicaid": medicaid, "Private insurance": 1 - medicaid - other, "Other payer": other},
            "growth": rng.normal(0, 0.01),
        })

    # Choose injected deteriorations, spread across sizes and indicators.
    indicators = list(INDICATOR_PARAMS)
    order = np.argsort([c["births"] for c in counties])
    picks = order[np.linspace(5, n_counties - 1, n_injected).astype(int)]
    onset = year_list[-onset_years]
    truth = []
    for j, idx in enumerate(picks):
        c = counties[idx]
        truth.append({
            "geo_id": c["geo_id"],
            "geo_name": c["geo_name"],
            "indicator": indicators[j % len(indicators)],
            "onset_year": onset,
            "odds_multiplier": float(rng.uniform(1.25, 1.45)),
            "affected_subgroup": "Medicaid" if j % 3 == 0 else TOTAL_SUBGROUP,
            "baseline_births": round(c["births"]),
            "size_class": size_class(c["births"]),
        })
    truth_df = pd.DataFrame(truth)
    shock = {(t["geo_id"], t["indicator"]): t for t in truth}

    rows = []
    county_effect = {(c["geo_id"], ind): rng.normal(0, 0.22) for c in counties for ind in indicators}
    for c in counties:
        for y_i, year in enumerate(year_list):
            births_y = c["births"] * np.exp(c["growth"] * y_i + rng.normal(0, 0.03))
            for ind, (p0, trend) in INDICATOR_PARAMS.items():
                year_noise = rng.normal(0, 0.05)
                s = shock.get((c["geo_id"], ind))
                for sub, share in c["mix"].items():
                    n = int(rng.poisson(births_y * share))
                    lo = _logit(p0) + trend * y_i + county_effect[(c["geo_id"], ind)] + SUBGROUP_OFFSETS[sub] + year_noise
                    if s and year >= s["onset_year"] and s["affected_subgroup"] in (TOTAL_SUBGROUP, sub):
                        lo += np.log(s["odds_multiplier"])
                    k = int(rng.binomial(n, _expit(lo))) if n > 0 else 0
                    rows.append([c["geo_id"], c["geo_name"], c["state"], year, ind, sub, k, n])

    tidy = pd.DataFrame(rows, columns=["geo_id", "geo_name", "state", "year", "indicator", "subgroup",
                                       "numerator", "denominator"])
    totals = tidy.groupby(["geo_id", "geo_name", "state", "year", "indicator"], as_index=False)[
        ["numerator", "denominator"]].sum()
    totals["subgroup"] = TOTAL_SUBGROUP
    tidy = pd.concat([totals, tidy], ignore_index=True)
    tidy[["numerator", "denominator"]] = tidy[["numerator", "denominator"]].astype(float)
    return tidy[["geo_id", "geo_name", "state", "year", "indicator", "subgroup", "numerator", "denominator"]], truth_df


def drop_completeness(
    tidy: pd.DataFrame,
    geo_ids,
    years,
    share: float,
    case_relative_chance: float = 1.0,
    indicators=None,
    seed: int = 0,
) -> pd.DataFrame:
    """Copy of `tidy` in which a share of births in some areas and years have the item unknown.

    Each birth without the outcome becomes unknown with probability `share`,
    and each birth with the outcome with probability
    `share * case_relative_chance` (capped at 1): 1 is missing at random, 0
    means cases are always recorded and only births without the outcome go
    missing (the observed rate rises), above 1 that cases go missing more
    often (it falls). Births made unknown leave the numerator and denominator
    and are added to the `unknown` column (created as 0 where absent), as
    `ingest.wonder_to_tidy` does with its default setting, so the result can be
    passed to `missing.unknown_sensitivity`. When an area-year has subgroups
    besides the total, the subgroups are thinned and the total is rebuilt as
    their sum, so the two stay consistent.
    """
    if not 0 <= share <= 1:
        raise ValueError("share must be between 0 and 1")
    if case_relative_chance < 0:
        raise ValueError("case_relative_chance must be 0 or more")
    rng = np.random.default_rng(seed)
    out = tidy.copy()
    if "unknown" not in out.columns:
        out["unknown"] = 0.0
    out["unknown"] = pd.to_numeric(out["unknown"], errors="coerce").astype(float)
    hit = out["geo_id"].isin(list(geo_ids)) & out["year"].isin(list(years))
    if indicators is not None:
        hit &= out["indicator"].isin(list(indicators))
    keys = ["geo_id", "year", "indicator"]
    has_parts = out[hit & (out["subgroup"] != TOTAL_SUBGROUP)].groupby(keys).size()
    is_total = out["subgroup"] == TOTAL_SUBGROUP
    rebuilt = pd.MultiIndex.from_frame(out[keys]).isin(has_parts.index) & is_total
    thin = hit & ~rebuilt & out[["numerator", "denominator"]].notna().all(axis=1)

    num = out.loc[thin, "numerator"].to_numpy(int)
    den = out.loc[thin, "denominator"].to_numpy(int)
    lost_cases = rng.binomial(num, min(1.0, share * case_relative_chance))
    lost_other = rng.binomial(den - num, share)
    out.loc[thin, "numerator"] = (num - lost_cases).astype(float)
    out.loc[thin, "denominator"] = (den - lost_cases - lost_other).astype(float)
    out.loc[thin, "unknown"] = out.loc[thin, "unknown"] + lost_cases + lost_other

    if rebuilt.any():
        parts = out[hit & ~is_total].groupby(keys)[["numerator", "denominator", "unknown"]].sum(min_count=1)
        idx = out.index[rebuilt]
        sums = parts.reindex(pd.MultiIndex.from_frame(out.loc[idx, keys]))
        out.loc[idx, ["numerator", "denominator", "unknown"]] = sums.to_numpy()
    return out
