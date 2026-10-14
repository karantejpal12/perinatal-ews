"""Within-county gaps between subgroups (for example, by payer or race and ethnicity)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import compute_rates
from .schema import TOTAL_SUBGROUP


def subgroup_gaps(tidy: pd.DataFrame, config: dict, year: int | None = None) -> pd.DataFrame:
    """For each county and indicator, compare the highest- and lowest-rate reliable subgroups.

    Returns one row per county-indicator with the rate ratio and rate difference,
    plus the same gap for the peer total so county gaps can be read in context.
    """
    year = int(year or tidy["year"].max())
    d = compute_rates(tidy[(tidy["year"] == year) & (tidy["subgroup"] != TOTAL_SUBGROUP)], config)
    d = d[d["reliable"]]
    if d.empty:
        return pd.DataFrame()

    def gap(g: pd.DataFrame) -> pd.Series:
        if len(g) < 2:
            return pd.Series({"highest_subgroup": np.nan, "lowest_subgroup": np.nan,
                              "highest_rate": np.nan, "lowest_rate": np.nan})
        hi, lo = g.loc[g["rate"].idxmax()], g.loc[g["rate"].idxmin()]
        return pd.Series({"highest_subgroup": hi["subgroup"], "lowest_subgroup": lo["subgroup"],
                          "highest_rate": hi["rate"], "lowest_rate": lo["rate"]})

    out = d.groupby(["indicator", "geo_id", "geo_name", "state"]).apply(gap, include_groups=False).reset_index()
    out = out.dropna(subset=["highest_rate"])
    out["rate_ratio"] = out["highest_rate"] / out["lowest_rate"]
    out["rate_difference"] = out["highest_rate"] - out["lowest_rate"]

    peer = d.groupby(["indicator", "subgroup"])[["numerator", "denominator"]].sum()
    peer["rate"] = peer["numerator"] / peer["denominator"]
    peer_gap = peer.groupby("indicator")["rate"].agg(lambda s: s.max() / s.min()).rename("peer_rate_ratio")
    out = out.join(peer_gap, on="indicator")
    out["year"] = year
    return out.sort_values(["indicator", "rate_ratio"], ascending=[True, False]).reset_index(drop=True)
