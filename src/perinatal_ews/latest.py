"""Monthly state-level updates from CDC provisional birth data.

Final natality data arrive about nine months after a year ends (2024 final data
were added to CDC WONDER in September 2025). CDC also publishes provisional
natality data (CDC WONDER database D192), updated near the end of each month
with births through the previous month. Provisional data are available by
state, not by county. This module turns a monthly download into "this year so
far" results for every state and records exactly how current the data are.

Method
- Year-to-date detection compares January to month *m* of the current year
  with January to *m* of the baseline years, so seasonal patterns cancel out
  and the standard detection method is used unchanged.
- Earlier years come from final data (a fixed file of final state counts for
  each January-to-*m* window, 2016-2022); 2023 onwards come from the
  provisional database, which marks 2023-2024 as final and later years as
  provisional.
- The latest month is used only if it looks complete: its births, relative to
  the same month a year earlier, must be at least 97% of the typical ratio for
  earlier months of the year. Otherwise it is left out and the window ends a
  month earlier. CDC notes that the most recent months are the least complete.
- The latest full year that only has provisional data (for example 2025) is
  also scored as a whole year.
- By mother's race, the current year so far is compared with the same months
  of the three previous years combined (rate ratio, 95% CI), reporting small
  groups through combined groups as in pooling.py.
"""
from __future__ import annotations

import calendar
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .detect import detect
from .pooling import STATE_NAMES, add_combined_groups, choose_reported
from .schema import TOTAL_SUBGROUP, validate

FIPS_TO_ABBR = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC",
    "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT",
    "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY",
}


def month_name(m: int) -> str:
    return calendar.month_name[int(m)]


def choose_months(monthly_births: pd.DataFrame, threshold: float = 0.97) -> dict:
    """Decide how many months of the current year to use.

    `monthly_births`: columns year, month, births (national), for the current and previous year.
    The latest month is kept only if its births, relative to the same month last year, are at least
    `threshold` of the typical ratio for earlier months; if last year's month is missing it is dropped.
    Raises ValueError if a month before the chosen one has no births, or if no complete month remains.
    """
    mb = monthly_births[monthly_births["births"] > 0]
    year = int(mb["year"].max())
    cur = mb[mb["year"] == year].set_index("month")["births"]
    prev = mb[mb["year"] == year - 1].set_index("month")["births"]
    latest = int(cur.index.max())
    ratios = (cur / prev).dropna()
    typical = float(ratios.drop(latest, errors="ignore").median()) if len(ratios) > 1 else 1.0
    completeness = float(ratios.get(latest, np.nan) / typical) if typical else np.nan
    use_latest = bool(np.isfinite(completeness) and completeness >= threshold)
    m = latest if use_latest else latest - 1
    if m < 1:
        raise ValueError(f"Only {year}-{latest:02d} is available and it looks incomplete "
                         f"(completeness {completeness:.2f}); there is no complete month of {year} to compare yet.")
    gaps = [k for k in range(1, m + 1) if k not in cur.index]
    if gaps:
        raise ValueError(f"National births for {year} are missing month(s) {', '.join(map(str, gaps))} within "
                         f"January-{m}; the year-to-date totals would be incomplete. Re-download the monthly births.")
    return {"ytd_year": year, "latest_month_available": f"{year}-{latest:02d}", "latest_month": latest,
            "latest_month_completeness": round(completeness, 4) if np.isfinite(completeness) else None,
            "excluded_latest_month": not use_latest, "ytd_through_month": m}


def _states(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["state_fips"] = d["state_fips"].astype(str).str.zfill(2)
    d = d[d["state_fips"].isin(FIPS_TO_ABBR)]
    d["state"] = d["state_fips"].map(FIPS_TO_ABBR)
    d["geo_id"] = d["state"]
    d["geo_name"] = d["state"].map(STATE_NAMES)
    return d


def build_tidy(provisional: pd.DataFrame, baseline: pd.DataFrame, m: int, kind: str = "ytd",
               subgroup: str = TOTAL_SUBGROUP) -> tuple[pd.DataFrame, list[int]]:
    """State tidy table for January-m (kind='ytd') or full years (kind='full')."""
    p = _states(provisional)
    p = p[(p["series"] == f"prov_{kind}") & (p["subgroup"] == subgroup)]
    b = _states(baseline)
    b = b[(b["through_month"] == (m if kind == "ytd" else 12)) & (b["subgroup"] == subgroup)]
    b = b[~b["year"].isin(p["year"].unique())]
    cols = ["geo_id", "geo_name", "state", "year", "indicator", "subgroup", "numerator", "denominator"]
    t = pd.concat([b[cols], p[cols]], ignore_index=True)
    return validate(t), sorted(int(y) for y in b["year"].unique())


def compare_to_recent(provisional: pd.DataFrame, year: int, reference_years: list[int], min_events: int = 20,
                      combine: dict | None = None) -> pd.DataFrame:
    """Current year so far vs the same months of reference years combined, by state, group and indicator."""
    from .indicators import wilson_interval

    p = _states(provisional)
    p = p[p["series"] == "prov_ytd"]
    cols = ["geo_id", "geo_name", "state", "year", "indicator", "subgroup", "numerator", "denominator"]
    t = add_combined_groups(p[cols], combine)
    cur = t[t["year"] == year]
    ref = t[t["year"].isin(reference_years)]
    rg = ref.groupby(["geo_id", "geo_name", "state", "indicator", "subgroup"]).agg(
        ref_num=("numerator", lambda s: s.sum() if s.notna().all() else np.nan),
        ref_den=("denominator", lambda s: s.sum() if s.notna().all() else np.nan),
        ref_years=("year", "nunique")).reset_index()
    rg.loc[rg["ref_years"] < len(reference_years), ["ref_num", "ref_den"]] = np.nan
    c = cur.merge(rg, on=["geo_id", "geo_name", "state", "indicator", "subgroup"], how="left")
    c["rate"] = c["numerator"] / c["denominator"]
    c["ci_low"], c["ci_high"] = wilson_interval(c["numerator"], c["denominator"])
    c["ref_rate"] = c["ref_num"] / c["ref_den"]
    c["status"] = np.where(c["numerator"].isna(), "suppressed or missing",
                           np.where(c["numerator"] < min_events, f"unreliable (<{min_events} events)", "reliable"))
    ok = (c["status"] == "reliable") & (c["ref_num"] >= min_events)
    c["rate_ratio"] = np.where(ok, c["rate"] / c["ref_rate"], np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        se = np.sqrt(1 / c["numerator"] - 1 / c["denominator"] + 1 / c["ref_num"] - 1 / c["ref_den"])
    c["rr_low"] = np.where(ok, c["rate_ratio"] * np.exp(-1.96 * se), np.nan)
    c["rr_high"] = np.where(ok, c["rate_ratio"] * np.exp(1.96 * se), np.nan)
    c["change"] = np.where(~ok, "not compared", np.where(c["rr_low"] > 1, "higher",
                                                          np.where(c["rr_high"] < 1, "lower", "no clear change")))
    c["window"] = str(year)
    c = choose_reported(c.rename(columns={}), combine)
    return c


def run_latest(provisional: pd.DataFrame, baseline: pd.DataFrame, meta: dict, config: dict,
               out: str | Path) -> dict:
    """Year-to-date and full-year provisional detection for states, race comparison and metadata."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    m, year = int(meta["ytd_through_month"]), int(meta["ytd_year"])

    ytd, final_years = build_tidy(provisional, baseline, m, "ytd")
    prov_years = [int(y) for y in meta.get("provisional_years", [])]
    det_ytd = detect(ytd, config, target_year=year)
    det_ytd.to_csv(out / "state_detections_ytd.csv", index=False)
    result = {"ytd": det_ytd, "ytd_tidy": ytd}

    full_years = [y for y in prov_years if y < year]
    if full_years:
        fy = max(full_years)
        full, _ = build_tidy(provisional, baseline, m, "full")
        full = full[full["year"] <= fy]
        det_full = detect(full, config, target_year=fy)
        det_full.to_csv(out / f"state_detections_{fy}_provisional.csv", index=False)
        result["full"], result["full_year"] = det_full, fy

    race = compare_to_recent(provisional, year, [year - 3, year - 2, year - 1])
    race = race[race["subgroup"] != TOTAL_SUBGROUP]
    race.to_csv(out / "state_race_ytd.csv", index=False)
    result["race"] = race

    tot = det_ytd[det_ytd["subgroup"] == TOTAL_SUBGROUP]
    latest = {
        "updated": meta.get("fetched_at", date.today().isoformat()),
        "latest_month_available": meta["latest_month_available"],
        "latest_month_completeness": meta.get("latest_month_completeness"),
        "excluded_latest_month": bool(meta.get("excluded_latest_month", False)),
        "ytd_year": year, "ytd_through_month": m,
        "ytd_label": f"January–{month_name(m)} {year}" if m > 1 else f"January {year}",
        "final_years": (lambda ys: f"{min(ys)}–{max(ys)}" if ys else "")(
            sorted(int(y) for y in ytd["year"].unique() if int(y) not in set(prov_years))),
        "provisional_years": prov_years,
        "full_year_provisional": result.get("full_year"),
        "geography": "state",
        "states": int(tot["geo_id"].nunique()),
        "counts": {"alerts": int((tot["level"] == "alert").sum()), "watch": int((tot["level"] == "watch").sum())},
        "sources": meta.get("sources", {}),
    }
    (out / "latest_meta.json").write_text(json.dumps(latest, indent=2, default=str))
    result["meta"] = latest
    return result


def explorer_payload(result: dict) -> dict:
    """Compact per-state results for the web explorer (rates only where 10 or more events)."""
    def r(x, nd=4):
        return None if x is None or pd.isna(x) else round(float(x), nd)

    meta = dict(result["meta"])
    states: dict = {}
    det = result["ytd"]
    for row in det[det["subgroup"] == TOTAL_SUBGROUP].itertuples():
        shown = row.observed >= 10
        states.setdefault(row.geo_id, {"ind": {}, "race": {}})["ind"][row.indicator] = {
            "level": row.level, "rate": r(row.rate) if shown else None, "expected": r(row.expected_rate),
            "rr": r(row.relative_risk, 3) if shown else None, "births": None if pd.isna(row.births) else int(row.births)}
    full = result.get("full")
    if full is not None:
        for row in full[full["subgroup"] == TOTAL_SUBGROUP].itertuples():
            e = states.setdefault(row.geo_id, {"ind": {}, "race": {}})["ind"].setdefault(row.indicator, {})
            e["full_year_level"] = row.level
            e["full_year_rate"] = r(row.rate) if row.observed >= 10 else None
    for row in result["race"].itertuples():
        ok = row.status == "reliable"
        states.setdefault(row.geo_id, {"ind": {}, "race": {}})["race"].setdefault(row.indicator, []).append({
            "g": row.subgroup, "rate": r(row.rate) if ok else None, "lo": r(row.ci_low) if ok else None,
            "hi": r(row.ci_high) if ok else None, "ref": r(row.ref_rate) if ok and row.ref_num >= 20 else None,
            "rr": r(row.rate_ratio, 3), "change": row.change, "status": row.status, "report": row.report_as})
    meta["states_data"] = states
    return meta
