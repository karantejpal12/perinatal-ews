"""Held-out validation of detection: predict each county-year without it, then check.

Detection (``detect``) compares a county's target-year count with an expected
count and a variance. If that model is right, a county-year that played no part
in building its own prediction should fall inside the model's predictive
interval about as often as the interval's nominal level (allowing for the real
changes that alerts exist to catch).

For every target year T, indicator and county c:

1. The prediction uses only c's baseline years (T-4 to T-2; T-1 is skipped as
   in detection), the empirical-Bayes prior and extra-variance estimated from
   all counties' baseline years, and the peer trend from all *other* counties
   in year T. Detection's peer trend includes c's own year-T count; here it is
   recomputed without it, so c's year-T data are never used.
2. The predictive distribution of c's year-T count is Normal(E, V), with V the
   variance detection uses: binomial noise in year T, extra year-to-year
   variation, and the uncertainty of the baseline. So sampling variation of
   the held-out count is included, not only the error of the expected rate.
3. Reported: coverage of 80%, 90% and 95% predictive intervals; how often the
   held-out z-score exceeds the one-sided 5% and 2.5% points; the same coverage
   with binomial noise only (to show what the extra variance adds); and
   prediction error of the rate against simpler predictors (last year's rate,
   the county's own three-year rate, and the rate of all other counties).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .detect import _score_year
from .schema import TOTAL_SUBGROUP

LEVELS = (0.80, 0.90, 0.95)


def _baseline_counts(df: pd.DataFrame, target_year: int, baseline_years: int, guard_years: int) -> pd.DataFrame:
    """Same pooled baseline as detection (``detect._score_year``)."""
    last = target_year - guard_years
    years = list(range(last - baseline_years, last))
    base = df[df["year"].isin(years)].dropna(subset=["numerator", "denominator"])
    bc = base.groupby("geo_id").agg(num_b=("numerator", "sum"), den_b=("denominator", "sum"),
                                    n_years=("year", "nunique"))
    return bc[bc["n_years"] >= max(2, baseline_years - 1)]


def heldout_predictions(tidy: pd.DataFrame, config: dict, years: list[int] | None = None,
                        subgroup: str = TOTAL_SUBGROUP) -> pd.DataFrame:
    """One row per county, indicator and target year with the held-out prediction and its checks."""
    det = config["detection"]
    nb, adjust, guard = det["baseline_years"], det["adjust_for_reference_trend"], det.get("guard_years", 1)
    first_ok = int(tidy["year"].min()) + nb + guard
    years = years or [y for y in sorted(int(y) for y in tidy["year"].unique()) if y >= first_ok]
    out = []
    for indicator, df in tidy[tidy["subgroup"] == subgroup].groupby("indicator"):
        for t in years:
            s = _score_year(df, t, nb, adjust, guard)
            s = s.dropna(subset=["expected", "observed", "births"]).set_index("geo_id")
            if s.empty:
                continue
            bc = _baseline_counts(df, t, nb, guard)
            tgt = df[df["year"] == t].dropna(subset=["numerator", "denominator"])
            num_t, den_t = tgt["numerator"].sum(), tgt["denominator"].sum()
            drift_all = float(s["peer_drift"].iloc[0])
            ref_base = float(s["peer_rate"].iloc[0]) / drift_all if adjust else np.nan
            k, tau2 = float(s["prior_strength"].iloc[0]), float(s["extra_variance_tau2"].iloc[0])
            prev = df[df["year"] == t - 1].set_index("geo_id")
            for g, r in s.iterrows():
                o, n = r["observed"], r["births"]
                # Peer trend without this county's own year-T data.
                drift = ((num_t - o) / (den_t - n)) / ref_base if adjust and den_t > n else drift_all
                p_hat = r["shrunk_baseline_rate"]
                p = float(np.clip(p_hat * drift, 1e-9, 1 - 1e-9))
                e = n * p
                db, ny = bc.at[g, "den_b"], bc.at[g, "n_years"]
                v_bin = e * (1 - p)
                v = v_bin + tau2 * e ** 2 + (n * drift) ** 2 * p_hat * (1 - p_hat) / (db + k) + tau2 * e ** 2 / ny
                pv = prev.loc[g] if g in prev.index else None
                last_rate = (pv["numerator"] / pv["denominator"]
                             if pv is not None and pd.notna(pv["numerator"]) and pv["denominator"] > 0 else np.nan)
                out.append({
                    "indicator": indicator, "geo_id": g, "state": r["state"], "year": t, "births": n,
                    "observed": o, "rate": o / n, "expected": e, "expected_rate": p,
                    "expected_rate_detection": r["expected_rate"], "var": v, "var_binomial": v_bin,
                    "z": (o - e) / np.sqrt(v), "z_binomial": (o - e) / np.sqrt(v_bin),
                    "pred_last_year": last_rate, "pred_own_baseline": r["baseline_rate"],
                    "pred_other_counties": (num_t - o) / (den_t - n) if den_t > n else np.nan,
                })
    d = pd.DataFrame(out)
    if len(d):
        d["size_group"] = pd.qcut(d["births"].rank(method="first"), 3, labels=["smallest third", "middle third", "largest third"])
    return d


def _summ(d: pd.DataFrame) -> dict:
    res = {"county_years": int(len(d))}
    for lv in LEVELS:
        zq = stats.norm.ppf(0.5 + lv / 2)
        res[f"coverage_{int(lv * 100)}"] = float((d["z"].abs() <= zq).mean())
        res[f"coverage_{int(lv * 100)}_binomial_only"] = float((d["z_binomial"].abs() <= zq).mean())
    res["above_upper_5pct"] = float((d["z"] >= stats.norm.ppf(0.95)).mean())
    res["above_upper_2_5pct"] = float((d["z"] >= stats.norm.ppf(0.975)).mean())
    err = lambda col: float((d[col] - d["rate"]).abs().mean() * 100)  # percentage points
    res["mae_pp_method"] = err("expected_rate")
    for name in ("pred_last_year", "pred_own_baseline", "pred_other_counties"):
        res[f"mae_pp_{name.removeprefix('pred_')}"] = err(name)
    res["max_diff_from_detection_pp"] = float((d["expected_rate"] - d["expected_rate_detection"]).abs().max() * 100)
    return res


def heldout_summary(d: pd.DataFrame) -> pd.DataFrame:
    """Coverage and error overall and by indicator, target year and county size."""
    rows = [{"group": "all", "value": "all", **_summ(d)}]
    for col in ("indicator", "year", "size_group"):
        for v, g in d.groupby(col, observed=True):
            rows.append({"group": col, "value": str(v), **_summ(g)})
    return pd.DataFrame(rows)
