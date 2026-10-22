"""Persistent burden: areas whose rate stays among the worst year after year.

Detection (`detect`) asks whether an area is doing worse than its own recent
history, so an area whose rate is high but stable is never flagged. This
module answers the other question, separately from change alerts: for each
area and indicator, in how many of the last `window` years (default five) was
the area's rate in the worst national quintile of areas? Three or more such
years (default) makes the area "persistent".

This follows the persistence part of Brown CC et al., "Geographic Hotspots
for Low Birthweight: An Analysis of Counties With Persistently High Rates",
*Inquiry* 2020;57. Their condition that neighbouring counties are also high
is dropped, because public county data identify only large counties.

Rules:
- Each year, areas with a known numerator and a denominator above zero are
  ranked among themselves (unweighted: one area, one rank). The worst quintile
  is the fifth of areas with the highest rates (lowest for indicators marked
  `lower_is_worse`); areas tied at the boundary are all included.
- Years with fewer than five ranked areas are skipped: a quintile needs five.
- Missing or suppressed years are skipped, never counted as "not worst".
  An area with fewer ranked years than `min_years` is "insufficient data".
- `reliable` is False when any of the area's worst-quintile years rests on
  fewer than `min_numerator_reliable` events (NCHS: 20), so a high rate from
  a handful of births can be told apart from a well-measured one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import TOTAL_SUBGROUP

STATUSES = ["persistent", "not persistent", "insufficient data"]
MIN_AREAS_PER_YEAR = 5


def worst_quintile(rates: pd.Series, higher_is_worse: bool = True) -> pd.Series:
    """True for rates in the worst fifth of `rates` (ties at the boundary included)."""
    rank = rates.rank(ascending=not higher_is_worse, method="min")
    return rank <= np.ceil(len(rates) / 5)


def persistent_burden(
    tidy: pd.DataFrame,
    config: dict,
    end_year: int | None = None,
    window: int = 5,
    min_years: int = 3,
    subgroups: list[str] | None = None,
) -> pd.DataFrame:
    """Count, for every area, indicator and subgroup, the years in the worst national quintile.

    Returns one row per area, indicator and subgroup with the window, the number
    of ranked years, the number and list of worst-quintile years, `status`
    (persistent / not persistent / insufficient data) and `reliable`.
    """
    if window < 1 or not 1 <= min_years <= window:
        raise ValueError("need window >= 1 and 1 <= min_years <= window")
    end_year = int(end_year or tidy["year"].max())
    start_year = end_year - window + 1
    subgroups = subgroups or [TOTAL_SUBGROUP]
    min_events = config["detection"]["min_numerator_reliable"]

    d = tidy[tidy["year"].between(start_year, end_year) & tidy["subgroup"].isin(subgroups)]
    areas = tidy[tidy["subgroup"].isin(subgroups)].drop_duplicates(
        ["indicator", "subgroup", "geo_id"])[["indicator", "subgroup", "geo_id", "geo_name", "state"]]
    d = d.dropna(subset=["numerator", "denominator"])
    d = d[d["denominator"] > 0].copy()
    d["rate"] = d["numerator"] / d["denominator"]

    ranked = []
    for (indicator, _, _), g in d.groupby(["indicator", "subgroup", "year"]):
        if len(g) < MIN_AREAS_PER_YEAR:
            continue
        spec = config["indicators"].get(indicator, {})
        g = g.copy()
        g["worst"] = worst_quintile(g["rate"], spec.get("direction") != "lower_is_worse")
        ranked.append(g)
    cols = ["indicator", "subgroup", "geo_id"]
    if ranked:
        r = pd.concat(ranked, ignore_index=True)
        r["small_worst"] = r["worst"] & (r["numerator"] < min_events)
        summary = r.groupby(cols).agg(
            years_ranked=("year", "nunique"),
            years_in_worst_quintile=("worst", "sum"),
            small_worst=("small_worst", "any"),
        ).reset_index()
        years = (r[r["worst"]].sort_values("year").groupby(cols)["year"]
                 .agg(lambda s: ",".join(str(y) for y in s)).rename("worst_quintile_years").reset_index())
        summary = summary.merge(years, on=cols, how="left")
    else:
        summary = pd.DataFrame(columns=cols + ["years_ranked", "years_in_worst_quintile", "small_worst",
                                               "worst_quintile_years"])

    out = areas.merge(summary, on=cols, how="left")
    out["years_ranked"] = out["years_ranked"].fillna(0).astype(int)
    out["years_in_worst_quintile"] = out["years_in_worst_quintile"].fillna(0).astype(int)
    out["worst_quintile_years"] = out["worst_quintile_years"].fillna("")
    out["reliable"] = ~out["small_worst"].fillna(False).astype(bool)
    out = out.drop(columns="small_worst")
    out.insert(5, "window_start", start_year)
    out.insert(6, "window_end", end_year)

    status = np.where(out["years_in_worst_quintile"] >= min_years, "persistent",
                      np.where(out["years_ranked"] >= min_years, "not persistent", "insufficient data"))
    out["status"] = pd.Categorical(status, STATUSES, ordered=True)
    return out.sort_values(["indicator", "subgroup", "status", "years_in_worst_quintile", "geo_id"],
                           ascending=[True, True, True, False, True]).reset_index(drop=True)
