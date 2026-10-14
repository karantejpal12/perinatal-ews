"""Small numbers: state-level analysis, multi-year pooling and combining small groups.

Many state maternal and child health teams work at state level and, when a
group is too small for a reliable estimate, pool several years or combine
related racial and ethnic groups. This module does the same, transparently:

- `to_state` aggregates county rows to state totals (or use state-level input
  directly, for example a CDC WONDER export grouped by state).
- `pooled_estimates` pools a window of years for every place, group and
  indicator. Years that are missing from the data, suppressed, or listed as
  unavailable (for example Hawaii PRAMS 2017-2018) are skipped and reported,
  never treated as zero. With `fill_window=True` the window reaches further
  back to collect the requested number of available years.
- `add_combined_groups` adds configured combined groups year by year, before
  pooling (or keeps combined groups requested directly from the source).
- `choose_reported` reports each estimate itself if reliable, otherwise the
  first reliable combined group it belongs to, labelled as combined, otherwise
  "insufficient data" rather than an unreliable number.
- `small_numbers_analysis` runs all of the above.
- `compare_windows` compares the latest pooled window with the one before it
  (rate ratio with a 95% confidence interval), only where both are reliable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import wilson_interval
from .schema import TOTAL_SUBGROUP

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

# Default combinations, in the order they are tried. They follow common federal reporting practice and
# work with CDC WONDER "Single Race 15" or "Single Race 6" groups; pass your own to follow local practice.
NHOPI_15 = ["Hawaiian", "Guamanian or Chamorro", "Samoan", "Other Pacific Islander"]
ASIAN_15 = ["Asian Indian", "Chinese", "Filipino", "Japanese", "Korean", "Vietnamese", "Other Asian"]
DEFAULT_COMBINE = {
    "Native Hawaiian or Other Pacific Islander (combined)": NHOPI_15,
    "Asian (combined)": ASIAN_15,
    "Asian or Pacific Islander (combined)": ASIAN_15 + NHOPI_15 + ["Asian", "Native Hawaiian or Other Pacific Islander"],
}


def to_state(tidy: pd.DataFrame) -> pd.DataFrame:
    """Sum county rows to states. A state-year is missing if any of its county rows is missing."""
    g = tidy.groupby(["state", "year", "indicator", "subgroup"])
    out = g[["numerator", "denominator"]].sum(min_count=1).reset_index()
    incomplete = g["numerator"].apply(lambda s: s.isna().any()).reset_index(drop=True)
    out.loc[incomplete.to_numpy(), "numerator"] = np.nan
    out["geo_id"] = out["state"]
    out["geo_name"] = out["state"].map(STATE_NAMES).fillna(out["state"])
    return out[["geo_id", "geo_name", "state", "year", "indicator", "subgroup", "numerator", "denominator"]]


def _windows(years: list[int], end_years: list[int], window: int, unavailable: set, fill_window: bool, max_span: int):
    for end in end_years:
        if fill_window:
            used, y = [], end
            while len(used) < window and end - y < max_span:
                if y in years and y not in unavailable:
                    used.append(y)
                y -= 1
            used = sorted(used)
            start = used[0] if used else end
        else:
            start = end - window + 1
            used = [y for y in range(start, end + 1) if y in years and y not in unavailable]
        missing = [y for y in range(start, end + 1) if y not in used]
        yield end, start, used, missing


def pooled_estimates(tidy: pd.DataFrame, window: int = 3, unavailable_years: list[int] | None = None,
                     fill_window: bool = False, max_span: int = 6, min_years: int | None = None,
                     min_events: int = 20) -> pd.DataFrame:
    """Pooled rate per place, group, indicator and window. Suppressed or missing years are skipped and listed."""
    unavailable = set(int(y) for y in (unavailable_years or []))
    min_years = min_years or max(1, window - 1)
    years = sorted(int(y) for y in tidy["year"].unique())
    ends = [y for y in years if y - window + 1 >= years[0]] if not fill_window else years[window - 1:]
    rows = []
    for (geo, name, st, ind, sub), g in tidy.groupby(["geo_id", "geo_name", "state", "indicator", "subgroup"]):
        g = g.set_index("year")
        have = [y for y in g.index if pd.notna(g.at[y, "numerator"]) and pd.notna(g.at[y, "denominator"])]
        for end, start, used, missing in _windows(have, ends, window, unavailable, fill_window, max_span):
            listed = [y for y in missing if y in unavailable]
            absent = [y for y in missing if y not in unavailable]
            n_used = len(used)
            num = float(g.loc[used, "numerator"].sum()) if used else np.nan
            den = float(g.loc[used, "denominator"].sum()) if used else np.nan
            rows.append({"geo_id": geo, "geo_name": name, "state": st, "indicator": ind, "subgroup": sub,
                         "window": f"{start}-{end}", "window_end": end, "years_used": ",".join(map(str, used)),
                         "years_unavailable": ",".join(map(str, listed)),
                         "years_missing_or_suppressed": ",".join(map(str, absent)),
                         "n_years": n_used, "numerator": num, "denominator": den})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    ok = out["n_years"] >= min_years
    out.loc[~ok, ["numerator", "denominator"]] = np.nan
    out["rate"] = out["numerator"] / out["denominator"]
    out["ci_low"], out["ci_high"] = wilson_interval(out["numerator"], out["denominator"])
    out["status"] = np.select(
        [~ok, out["numerator"] < 10, out["numerator"] < min_events],
        [f"too few years with data (<{min_years})", "suppressed (<10 events)", f"unreliable (<{min_events} events)"],
        default="reliable")
    return out


def add_combined_groups(tidy: pd.DataFrame, combine: dict | None = None) -> pd.DataFrame:
    """Add combined-group rows, year by year, before pooling.

    For each year, a combined group's count is the sum of its members' counts.
    If any member's count is suppressed or missing that year, the combined count
    is missing too (a suppressed cell hides a value from 1 to 9, so the sum is
    unknown). Combined groups already present in the data, for example requested
    directly from CDC WONDER, are kept as they are and not recomputed.
    """
    combine = combine if combine is not None else DEFAULT_COMBINE
    present = set(tidy["subgroup"].unique())
    keys = ["geo_id", "geo_name", "state", "year", "indicator"]
    new = []
    for label, members in combine.items():
        mem = [m for m in members if m in present]
        if label in present or len(mem) < 2:
            continue
        m = tidy[tidy["subgroup"].isin(mem)]
        g = m.groupby(keys)
        agg = g.agg(numerator=("numerator", "sum"), denominator=("denominator", "sum"),
                    n=("subgroup", "nunique"), num_missing=("numerator", lambda x: x.isna().any()),
                    den_missing=("denominator", lambda x: x.isna().any())).reset_index()
        agg.loc[agg["num_missing"] | (agg["n"] < len(mem)), "numerator"] = np.nan
        agg.loc[agg["den_missing"] | (agg["n"] < len(mem)), "denominator"] = np.nan
        agg["subgroup"] = label
        new.append(agg[keys + ["subgroup", "numerator", "denominator"]])
    return pd.concat([tidy] + new, ignore_index=True) if new else tidy.copy()


def choose_reported(pooled: pd.DataFrame, combine: dict | None = None) -> pd.DataFrame:
    """For each estimate, say what to report: itself if reliable, otherwise the first reliable
    combined group it belongs to (in the order given), otherwise "insufficient data"."""
    combine = combine if combine is not None else DEFAULT_COMBINE
    p = pooled.copy()
    p["combined_from"] = p["subgroup"].map({k: " + ".join(v) for k, v in combine.items()}).fillna("")
    member_of: dict[str, list[str]] = {}
    for label, members in combine.items():
        for m in members:
            member_of.setdefault(m, []).append(label)
    keys = ["geo_id", "indicator", "window"]
    status = p.set_index(keys + ["subgroup"])["status"].to_dict()

    def report_as(r):
        if r["status"] == "reliable":
            return r["subgroup"]
        for lab in member_of.get(r["subgroup"], []):
            if status.get((r["geo_id"], r["indicator"], r["window"], lab)) == "reliable":
                return lab
        return "insufficient data"

    p["report_as"] = p.apply(report_as, axis=1)
    return p


def combine_small_groups(pooled: pd.DataFrame, combine: dict | None = None, min_events: int = 20) -> pd.DataFrame:
    """Backward-compatible wrapper: decide what to report for already pooled estimates."""
    return choose_reported(pooled, combine)


def small_numbers_analysis(tidy: pd.DataFrame, window: int = 3, unavailable_years: list[int] | None = None,
                           fill_window: bool = False, combine: dict | None = None, min_events: int = 20):
    """Combine groups year by year, pool years, choose what to report and compare windows."""
    t = add_combined_groups(tidy, combine)
    p = pooled_estimates(t, window=window, unavailable_years=unavailable_years, fill_window=fill_window,
                         min_events=min_events)
    p = choose_reported(p, combine)
    return p, compare_windows(p, window=window)


def compare_windows(pooled: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """Latest pooled window vs the previous, non-overlapping window (rate ratio, 95% CI)."""
    rows = []
    for key, g in pooled.groupby(["geo_id", "geo_name", "state", "indicator", "subgroup"]):
        g = g.set_index("window_end")
        last = g.index.max()
        prev = last - window
        if prev not in g.index:
            continue
        a, b = g.loc[last], g.loc[prev]
        ok = a["status"] == "reliable" and b["status"] == "reliable"
        rr = lo = hi = np.nan
        verdict = "not compared (an estimate is not reliable)"
        if ok:
            rr = a["rate"] / b["rate"]
            se = np.sqrt(1 / a["numerator"] - 1 / a["denominator"] + 1 / b["numerator"] - 1 / b["denominator"])
            lo, hi = rr * np.exp(-1.96 * se), rr * np.exp(1.96 * se)
            verdict = "higher" if lo > 1 else "lower" if hi < 1 else "no clear change"
        rows.append(dict(zip(["geo_id", "geo_name", "state", "indicator", "subgroup"], key),
                         latest_window=a["window"], latest_rate=a["rate"], previous_window=b["window"],
                         previous_rate=b["rate"], rate_ratio=rr, ci_low=lo, ci_high=hi, change=verdict,
                         latest_years_missing=",".join(x for x in [a["years_unavailable"], a["years_missing_or_suppressed"]] if x)))
    return pd.DataFrame(rows)
