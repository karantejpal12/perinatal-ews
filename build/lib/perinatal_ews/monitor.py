"""Monitoring the early-warning system itself.

Three questions, asked every time the system runs:

1. Is the input data healthy?  (completeness, suppression, implausible jumps)
2. Has the data distribution shifted?  (population stability index by indicator)
3. Is the detector performing evenly?  (false-alert rate over time from a backtest,
   and, where ground truth exists, sensitivity broken down by county size)

Question 3 matters because a detector that only works for large urban counties
quietly fails the small and rural counties that often need it most.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .detect import detect
from .schema import TOTAL_SUBGROUP
from .synthetic import size_class


def data_quality(tidy: pd.DataFrame, year: int | None = None, jump_threshold: float = 0.30) -> pd.DataFrame:
    """List data issues for the target year compared with the year before."""
    year = int(year or tidy["year"].max())
    d = tidy[tidy["subgroup"] == TOTAL_SUBGROUP]
    cur = d[d["year"] == year].set_index(["indicator", "geo_id"])
    prev = d[d["year"] == year - 1].set_index(["indicator", "geo_id"])
    issues = []

    for key in prev.index.difference(cur.index):
        issues.append({"indicator": key[0], "geo_id": key[1], "geo_name": prev.at[key, "geo_name"],
                       "issue": "missing this year", "detail": f"present in {year - 1}, absent in {year}"})
    for key in cur.index[cur["numerator"].isna()]:
        issues.append({"indicator": key[0], "geo_id": key[1], "geo_name": cur.at[key, "geo_name"],
                       "issue": "suppressed or missing count", "detail": "numerator not available"})
    both = cur.index.intersection(prev.index)
    change = cur.loc[both, "denominator"] / prev.loc[both, "denominator"] - 1
    for key, value in change[change.abs() > jump_threshold].items():
        issues.append({"indicator": key[0], "geo_id": key[1], "geo_name": cur.at[key, "geo_name"],
                       "issue": "denominator jump", "detail": f"{value:+.0%} births vs {year - 1}"})
    cols = ["indicator", "geo_id", "geo_name", "issue", "detail"]
    return pd.DataFrame(issues, columns=cols)


def population_stability_index(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """PSI between two samples, using reference-quantile bins. <0.1 stable, 0.1-0.25 moderate, >0.25 major."""
    reference = np.asarray(reference, dtype=float)
    current = np.asarray(current, dtype=float)
    reference, current = reference[np.isfinite(reference)], current[np.isfinite(current)]
    if len(reference) < bins or len(current) < bins:
        return float("nan")
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    ref_share = np.histogram(reference, edges)[0] / len(reference)
    cur_share = np.histogram(current, edges)[0] / len(current)
    ref_share, cur_share = np.clip(ref_share, 1e-4, None), np.clip(cur_share, 1e-4, None)
    return float(np.sum((cur_share - ref_share) * np.log(cur_share / ref_share)))


def distribution_drift(tidy: pd.DataFrame, config: dict, year: int | None = None) -> pd.DataFrame:
    """PSI of county rates (target year vs. baseline years) for each indicator."""
    year = int(year or tidy["year"].max())
    det = config["detection"]
    last = year - det.get("guard_years", 1)
    base_years = range(last - det["baseline_years"], last)
    d = tidy[(tidy["subgroup"] == TOTAL_SUBGROUP)].dropna(subset=["numerator", "denominator"])
    d = d.assign(rate=d["numerator"] / d["denominator"])
    rows = []
    for ind, g in d.groupby("indicator"):
        psi = population_stability_index(g[g["year"].isin(base_years)]["rate"], g[g["year"] == year]["rate"])
        status = "stable" if psi < 0.10 else ("moderate shift" if psi < 0.25 else "major shift")
        rows.append({"indicator": ind, "psi": psi, "status": status,
                     "median_rate_baseline": g[g["year"].isin(base_years)]["rate"].median(),
                     "median_rate_current": g[g["year"] == year]["rate"].median()})
    return pd.DataFrame(rows)


def backtest(tidy: pd.DataFrame, config: dict, years: list[int] | None = None) -> pd.DataFrame:
    """Re-run detection as if each past year were 'now'.

    Reports, per year, the share of county-indicators flagged, and how many
    alerts were still elevated (z >= 1) the following year. On data with no
    real change, a steady low flag rate means the system is well calibrated.
    """
    b = config["detection"]["baseline_years"] + config["detection"].get("guard_years", 1)
    all_years = sorted(tidy["year"].unique())
    years = years or [y for y in all_years if y - b - 1 >= all_years[0]]
    rows = []
    runs = {y: detect(tidy, config, target_year=y) for y in years}
    for y in years:
        r = runs[y]
        scored = r[r["level"] != "insufficient data"]
        alerts = scored[scored["level"] == "alert"]
        row = {"year": y, "county_indicators_scored": len(scored), "alerts": len(alerts),
               "watches": int((scored["level"] == "watch").sum()),
               "alert_rate_pct": 100 * len(alerts) / max(len(scored), 1)}
        if y + 1 in runs and len(alerts):
            nxt = runs[y + 1].set_index(["indicator", "geo_id"])["z"]
            persisted = [nxt.get((i, g), np.nan) >= 1 for i, g in zip(alerts["indicator"], alerts["geo_id"])]
            row["alerts_persisting_next_year_pct"] = 100 * float(np.mean(persisted))
        rows.append(row)
    return pd.DataFrame(rows)


def state_clusters(detections: pd.DataFrame, tidy: pd.DataFrame, config: dict,
                   min_counties: int = 3, min_share: float = 0.4) -> pd.DataFrame:
    """Flag states where many counties are flagged for the same indicator at once.

    County detection compares each county with all counties nationally. When a
    large share of one state's counties rise together, the cause is more likely
    state-wide: a real change (coverage, policy, practice) or a change in how the
    state records the birth certificate item. Either way, it should be reviewed
    with the state vital records office before reading the county flags as local.
    """
    d = detections[(detections["subgroup"] == TOTAL_SUBGROUP) & (detections["level"] != "insufficient data")]
    if d.empty:
        return pd.DataFrame()
    year = int(d["year"].iloc[0])
    det = config["detection"]
    last = year - det.get("guard_years", 1)
    base_years = list(range(last - det["baseline_years"], last))

    g = d.assign(flag=d["level"].isin(["alert", "watch"])).groupby(["indicator", "state"]).agg(
        counties=("geo_id", "size"), flagged=("flag", "sum"),
        alerts=("level", lambda s: int((s == "alert").sum()))).reset_index()
    g["share_flagged"] = g["flagged"] / g["counties"]
    g = g[(g["counties"] >= min_counties) & (g["share_flagged"] >= min_share)]
    if g.empty:
        return g.assign(state_rate_baseline=[], state_rate_current=[], national_rate_baseline=[],
                        national_rate_current=[])

    t = tidy[(tidy["subgroup"] == TOTAL_SUBGROUP)].dropna(subset=["numerator", "denominator"])

    def pooled(frame):
        return frame["numerator"].sum() / frame["denominator"].sum() if len(frame) else np.nan

    rows = []
    for r in g.itertuples():
        ti = t[t["indicator"] == r.indicator]
        ts = ti[ti["state"] == r.state]
        rows.append({
            "state_rate_baseline": pooled(ts[ts["year"].isin(base_years)]),
            "state_rate_current": pooled(ts[ts["year"] == year]),
            "national_rate_baseline": pooled(ti[ti["year"].isin(base_years)]),
            "national_rate_current": pooled(ti[ti["year"] == year]),
        })
    out = pd.concat([g.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    out["state_change_vs_national"] = (out["state_rate_current"] / out["state_rate_baseline"]) / (
        out["national_rate_current"] / out["national_rate_baseline"])
    out["year"] = year
    return out.sort_values(["share_flagged", "flagged"], ascending=False).reset_index(drop=True)


def evaluate_against_truth(tidy: pd.DataFrame, config: dict, truth: pd.DataFrame,
                           year: int | None = None) -> dict[str, pd.DataFrame]:
    """Sensitivity and false-alert rate against known injected changes (synthetic data only)."""
    year = int(year or tidy["year"].max())
    subgroups = sorted(set(truth["affected_subgroup"]) | {TOTAL_SUBGROUP})
    res = detect(tidy, config, target_year=year, subgroups=subgroups)
    res = res[res["level"] != "insufficient data"].copy()
    look = res.set_index(["indicator", "subgroup", "geo_id"])["level"]

    t = truth.copy()
    t["level_found"] = [look.get((r.indicator, r.affected_subgroup, r.geo_id), "insufficient data")
                        for r in t.itertuples()]
    t["detected_alert"] = t["level_found"] == "alert"
    t["detected_any"] = t["level_found"].isin(["alert", "watch"])

    total = res[res["subgroup"] == TOTAL_SUBGROUP].copy()
    # A Medicaid-only shock also raises the county total a little, so exclude those pairs from false positives.
    shocked_pairs = {(r.indicator, r.geo_id) for r in t.itertuples()}
    clean = total[[(i, g) not in shocked_pairs for i, g in zip(total["indicator"], total["geo_id"])]]
    summary = pd.DataFrame([{
        "injected_changes": len(t),
        "found_as_alert_pct": 100 * t["detected_alert"].mean(),
        "found_as_alert_or_watch_pct": 100 * t["detected_any"].mean(),
        "false_alerts": int((clean["level"] == "alert").sum()),
        "false_alert_rate_pct": 100 * float((clean["level"] == "alert").mean()),
        "clean_county_indicators": len(clean),
    }])
    by_size = t.groupby("size_class").agg(
        injected=("geo_id", "size"),
        found_as_alert_pct=("detected_alert", lambda s: 100 * s.mean()),
        found_as_alert_or_watch_pct=("detected_any", lambda s: 100 * s.mean()),
    ).reset_index()

    clean = clean.assign(size_class=clean["births"].map(size_class))
    fa = clean.groupby("size_class").agg(false_alert_rate_pct=("level", lambda s: 100 * (s == "alert").mean()))
    by_size = by_size.join(fa, on="size_class")
    return {"summary": summary, "by_size": by_size, "cases": t}
