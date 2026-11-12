"""Internal reference group: each county compared with its own lowest-risk mothers.

Detection compares a county with its own past, and persistent burden ranks it
against other counties. Perinatal Periods of Risk (PPOR) asks a third
question: how much higher is the county's rate than the rate among its own
mothers who are least at risk? Following Gilbert CS, Xaverius PK, Tibbits MK
et al., *Matern Child Health J* 2022;26:2396-2406, the reference group is
non-Hispanic White mothers aged 20 or older with at least some college, and
it is taken from the same county (within-county rates, not national
2014-2016 rates).

Input is the usual tidy table with two subgroups per county, year and
indicator: the total (`All`) and the reference group (`REFERENCE_SUBGROUP`,
for example from a CDC WONDER export filtered on race, Hispanic origin,
mother's age and education). The reference group is part of the total.

Rules:
- For each county, indicator and target year, years are pooled backwards from
  the target year, up to `max_span` years, until the reference group's
  outcome count (for example, preterm births among reference mothers) reaches
  the PPOR minimum of 60. The total is pooled over the same years.
- A year is used only when both the total and the reference group have a
  known count and births; missing or suppressed years are skipped and listed,
  never treated as zero.
- If the reference group's outcome count is still under 60 after `max_span`
  years, the result is "insufficient data" and no rate or comparison is given.
- The excess rate is the county rate minus the reference rate (PPOR "excess").
  Because the reference group is part of the total, the total and reference
  rates are not independent; the excess equals the share of births outside
  the reference group times the difference between the other births' rate
  and the reference rate, and its 95% interval is that share times the
  Newcombe (Wilson score) interval for the difference of those two
  independent rates.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import wilson_interval
from .schema import TOTAL_SUBGROUP

REFERENCE_SUBGROUP = "PPOR reference"
PPOR_MIN_EVENTS = 60
STATUSES = ["compared", "insufficient data"]


def newcombe_difference(k1, n1, k2, n2, level: float = 0.95):
    """Newcombe hybrid score interval for p1 - p2 (independent binomial proportions)."""
    k1, n1, k2, n2 = (np.asarray(x, dtype=float) for x in (k1, n1, k2, n2))
    with np.errstate(invalid="ignore", divide="ignore"):
        p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson_interval(k1, n1, level)
    l2, u2 = wilson_interval(k2, n2, level)
    d = p1 - p2
    low = d - np.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    high = d + np.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return d, low, high


def _check_nested(total: pd.DataFrame, ref: pd.DataFrame) -> None:
    both = total.join(ref, rsuffix="_ref", how="inner")
    bad = (both["numerator_ref"] > both["numerator"]) | (both["denominator_ref"] > both["denominator"])
    if bad.any():
        ex = both[bad].index[0]
        raise ValueError(f"reference group larger than the total for {int(bad.sum())} rows (first: {ex}); "
                         "the reference group must be part of the county total")


def reference_comparison(
    tidy: pd.DataFrame,
    reference_subgroup: str = REFERENCE_SUBGROUP,
    min_events: int = PPOR_MIN_EVENTS,
    max_span: int = 5,
    target_years: list[int] | None = None,
    level: float = 0.95,
) -> pd.DataFrame:
    """Compare every county's rate with its own reference group's rate, pooling years to reach `min_events`.

    Returns one row per county, indicator and target year with the years pooled
    and skipped, the county's and the reference group's counts and rates, the
    rate ratio, the excess rate with its interval, the excess share (excess as
    a share of the county rate) and `status` (compared / insufficient data).
    """
    if min_events < 1 or max_span < 1:
        raise ValueError("need min_events >= 1 and max_span >= 1")
    if reference_subgroup not in set(tidy["subgroup"]):
        raise ValueError(f"no rows for the reference subgroup {reference_subgroup!r}")
    key = ["geo_id", "indicator", "year"]
    total = tidy[tidy["subgroup"] == TOTAL_SUBGROUP].set_index(key)[["numerator", "denominator"]]
    ref = tidy[tidy["subgroup"] == reference_subgroup].set_index(key)[["numerator", "denominator"]]
    _check_nested(total, ref)

    years_all = sorted(int(y) for y in tidy["year"].unique())
    targets = sorted(int(y) for y in (target_years or years_all))
    names = tidy.drop_duplicates("geo_id").set_index("geo_id")[["geo_name", "state"]]
    usable = total.join(ref, rsuffix="_ref", how="inner").dropna()
    usable = usable[(usable["denominator"] > 0) & (usable["denominator_ref"] > 0)]
    by_pair = {k: g.droplevel(["geo_id", "indicator"]) for k, g in usable.groupby(level=["geo_id", "indicator"])}

    rows = []
    pairs = tidy[tidy["subgroup"].isin([TOTAL_SUBGROUP, reference_subgroup])][["geo_id", "indicator"]]
    for geo, ind in pairs.drop_duplicates().itertuples(index=False):
        have = by_pair.get((geo, ind), usable.iloc[0:0].droplevel(["geo_id", "indicator"]))
        for target in targets:
            used, skipped, ref_events = [], [], 0.0
            for y in range(target, target - max_span, -1):
                if y not in have.index:
                    skipped.append(y)
                    continue
                used.append(y)
                ref_events += have.at[y, "numerator_ref"]
                if ref_events >= min_events:
                    break
            used.sort()
            start = used[0] if used and ref_events >= min_events else target - max_span + 1
            skipped = sorted(y for y in skipped if y >= start)
            u = have.loc[used] if used else have.iloc[0:0]
            rows.append({
                "geo_id": geo, "geo_name": names.at[geo, "geo_name"], "state": names.at[geo, "state"],
                "indicator": ind, "target_year": target, "window": f"{start}-{target}",
                "years_used": ",".join(map(str, used)), "years_missing_or_suppressed": ",".join(map(str, skipped)),
                "n_years": len(used),
                "numerator": float(u["numerator"].sum()), "denominator": float(u["denominator"].sum()),
                "ref_numerator": float(u["numerator_ref"].sum()), "ref_denominator": float(u["denominator_ref"].sum()),
            })

    cols = ["geo_id", "geo_name", "state", "indicator", "target_year", "window", "years_used",
            "years_missing_or_suppressed", "n_years", "numerator", "denominator", "rate", "ref_numerator",
            "ref_denominator", "ref_rate", "rate_ratio", "excess_rate", "excess_ci_low", "excess_ci_high",
            "excess_share", "status"]
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=cols)
    ok = out["ref_numerator"] >= min_events
    with np.errstate(invalid="ignore", divide="ignore"):
        out["rate"] = np.where(ok, out["numerator"] / out["denominator"], np.nan)
        out["ref_rate"] = np.where(ok, out["ref_numerator"] / out["ref_denominator"], np.nan)
        out["rate_ratio"] = out["rate"] / out["ref_rate"]
        other_k = out["numerator"] - out["ref_numerator"]
        other_n = out["denominator"] - out["ref_denominator"]
        share_other = other_n / out["denominator"]
        _, lo, hi = newcombe_difference(other_k, other_n, out["ref_numerator"], out["ref_denominator"], level)
        out["excess_rate"] = out["rate"] - out["ref_rate"]
        # Every birth in the reference group: no other births, so the excess is exactly zero.
        lo = np.where(other_n > 0, lo, 0.0)
        hi = np.where(other_n > 0, hi, 0.0)
        out["excess_ci_low"] = np.where(ok, share_other * lo, np.nan)
        out["excess_ci_high"] = np.where(ok, share_other * hi, np.nan)
        out["excess_share"] = out["excess_rate"] / out["rate"]
    out["status"] = pd.Categorical(np.where(ok, "compared", "insufficient data"), STATUSES)
    return out[cols].sort_values(["indicator", "target_year", "geo_id"]).reset_index(drop=True)
