"""Early-warning detection.

For each indicator and county, the target-year count is compared with what
would be expected from the county's own recent history, adjusted for the
change seen across all peer counties over the same period:

1. Baseline: pool the county's numerator and denominator over
   `baseline_years` years, skipping `guard_years` immediately before the
   target so a change that started last year is not treated as normal.
2. Shrinkage: small counties have noisy baselines, so each baseline rate is
   shrunk toward the peer rate using an empirical-Bayes beta prior whose
   strength is estimated from the between-county variance.
3. Peer trend: the expected rate is scaled by the peer rate in the target
   year divided by the peer baseline rate, so a nationwide shift does not
   flag every county at once.
4. Uncertainty: the variance of (observed - expected) combines binomial
   noise in the target year, uncertainty in the baseline estimate, and
   extra year-to-year variation (Var = E(1-p) + tau2*E^2) estimated from
   scatter in the baseline years.
5. Flags: one-sided z-scores and Benjamini-Hochberg q-values across all
   counties give "watch" and "alert" levels, with minimum relative-risk
   thresholds so that statistically clear but tiny changes are not flagged.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .schema import TOTAL_SUBGROUP

LEVELS = ["alert", "watch", "stable", "insufficient data"]


def benjamini_hochberg(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    q = np.full_like(p, np.nan)
    ok = ~np.isnan(p)
    if not ok.any():
        return q
    pv = p[ok]
    order = np.argsort(pv)
    ranked = pv[order] * len(pv) / (np.arange(len(pv)) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(pv)
    out[order] = np.minimum(ranked, 1.0)
    q[ok] = out
    return q


def _beta_prior_strength(num: np.ndarray, den: np.ndarray, m: float) -> float:
    """Method-of-moments estimate of the beta prior's strength k (prior sample size)."""
    ok = den > 0
    if ok.sum() < 3 or not 0 < m < 1:
        return 1e6
    p = num[ok] / den[ok]
    w = den[ok] / den[ok].sum()
    total_var = np.sum(w * (p - m) ** 2)
    sampling_var = np.sum(w * m * (1 - m) / den[ok])
    between = total_var - sampling_var
    if between <= 0:
        return 1e6  # no detectable between-county variation: shrink fully to peers
    return float(np.clip(m * (1 - m) / between - 1, 1.0, 1e6))


def _score_year(df: pd.DataFrame, target_year: int, baseline_years: int, adjust: bool,
                guard_years: int = 1) -> pd.DataFrame:
    """Score one indicator/subgroup slice for one target year.

    `guard_years` skips the most recent year(s) before the target when building
    the baseline, so a change that began last year is not absorbed into "normal".
    """
    last = target_year - guard_years
    years = list(range(last - baseline_years, last))
    base = df[df["year"].isin(years)].dropna(subset=["numerator", "denominator"])
    tgt = df[df["year"] == target_year].set_index("geo_id")

    base_counts = base.groupby("geo_id").agg(
        num_b=("numerator", "sum"), den_b=("denominator", "sum"), n_years=("year", "nunique"))
    base_counts = base_counts[base_counts["n_years"] >= max(2, baseline_years - 1)]

    tgt_ok = tgt.dropna(subset=["numerator", "denominator"])
    ref_base = base_counts["num_b"].sum() / base_counts["den_b"].sum() if len(base_counts) else np.nan
    ref_tgt = tgt_ok["numerator"].sum() / tgt_ok["denominator"].sum() if len(tgt_ok) else np.nan
    drift = (ref_tgt / ref_base) if (adjust and ref_base > 0 and np.isfinite(ref_tgt)) else 1.0

    k = _beta_prior_strength(base_counts["num_b"].to_numpy(float), base_counts["den_b"].to_numpy(float), ref_base)

    # Extra-binomial variation: county-years scatter around their own baseline more than
    # binomial noise allows, and proportionally more in big counties. Model it as
    # Var(O) = E(1-p) + tau2 * E^2 and estimate tau2 by method of moments.
    yearly_ref = base.groupby("year").apply(
        lambda g: g["numerator"].sum() / g["denominator"].sum(), include_groups=False)
    b = base[base["geo_id"].isin(base_counts.index)].copy()
    b = b.join(base_counts[["num_b", "den_b", "n_years"]], on="geo_id")
    b["p_c"] = b["num_b"] / b["den_b"]
    b["d_y"] = b["year"].map(yearly_ref) / ref_base if adjust and ref_base > 0 else 1.0
    p_y = (b["p_c"] * b["d_y"]).clip(1e-9, 1 - 1e-9)
    e = b["denominator"] * p_y
    # (o - e) is measured against a baseline that includes o itself, which shrinks it by (1 - 1/n_years).
    shrink = (1 - 1 / b["n_years"]).clip(lower=0.5)
    excess = ((b["numerator"] - e) ** 2 / shrink - e * (1 - p_y)).sum()
    tau2 = float(max(0.0, excess / (e ** 2).sum())) if len(b) else 0.0

    rows = []
    geo_meta = df.drop_duplicates("geo_id").set_index("geo_id")[["geo_name", "state"]]
    for geo_id, meta in geo_meta.iterrows():
        row = {"geo_id": geo_id, "geo_name": meta["geo_name"], "state": meta["state"], "year": target_year}
        has_target = geo_id in tgt_ok.index
        has_base = geo_id in base_counts.index
        if has_target:
            row["observed"] = float(tgt_ok.at[geo_id, "numerator"])
            row["births"] = float(tgt_ok.at[geo_id, "denominator"])
            row["rate"] = row["observed"] / row["births"] if row["births"] else np.nan
        if has_target and has_base and row["births"] > 0:
            nb, db = base_counts.at[geo_id, "num_b"], base_counts.at[geo_id, "den_b"]
            p_hat = (nb + k * ref_base) / (db + k)
            p_exp = float(np.clip(p_hat * drift, 1e-9, 1 - 1e-9))
            n = row["births"]
            expected = n * p_exp
            n_yrs = base_counts.at[geo_id, "n_years"]
            var = (expected * (1 - p_exp)                                       # binomial noise now
                   + tau2 * expected ** 2                                      # extra year-to-year variation
                   + (n * drift) ** 2 * p_hat * (1 - p_hat) / (db + k)         # baseline sampling error
                   + tau2 * expected ** 2 / n_yrs)                             # baseline year-to-year error
            row.update(
                baseline_rate=nb / db,
                shrunk_baseline_rate=p_hat,
                expected=expected,
                expected_rate=p_exp,
                relative_risk=row["observed"] / expected if expected > 0 else np.nan,
                excess_cases=row["observed"] - expected,
                z=(row["observed"] - expected) / np.sqrt(var) if var > 0 else np.nan,
            )
        rows.append(row)

    out = pd.DataFrame(rows)
    for col in ("observed", "births", "rate", "baseline_rate", "shrunk_baseline_rate", "expected",
                "expected_rate", "relative_risk", "excess_cases", "z"):
        if col not in out:
            out[col] = np.nan
    out["peer_rate"] = ref_tgt
    out["peer_drift"] = drift
    out["prior_strength"] = k
    out["extra_variance_tau2"] = tau2
    return out


def _annual_percent_change(df: pd.DataFrame, upto_year: int) -> pd.Series:
    """Weighted least-squares slope of logit(rate) on year, as % change in odds per year."""
    d = df[(df["year"] <= upto_year)].dropna(subset=["numerator", "denominator"])
    d = d[(d["numerator"] > 0) & (d["numerator"] < d["denominator"])]

    def slope(g):
        if g["year"].nunique() < 4:
            return np.nan
        p = g["numerator"] / g["denominator"]
        y = np.log(p / (1 - p))
        w = g["denominator"] * p * (1 - p)
        x = g["year"] - g["year"].mean()
        xm = np.average(x, weights=w)
        ym = np.average(y, weights=w)
        beta = np.sum(w * (x - xm) * (y - ym)) / np.sum(w * (x - xm) ** 2)
        return (np.exp(beta) - 1) * 100

    return d.groupby("geo_id").apply(slope, include_groups=False)


def detect(
    tidy: pd.DataFrame,
    config: dict,
    target_year: int | None = None,
    subgroups: list[str] | None = None,
) -> pd.DataFrame:
    """Run early-warning detection for every indicator (and subgroup) in a tidy table."""
    det = config["detection"]
    target_year = int(target_year or tidy["year"].max())
    subgroups = subgroups or [TOTAL_SUBGROUP]
    results = []

    for (indicator, subgroup), df in tidy.groupby(["indicator", "subgroup"]):
        if subgroup not in subgroups:
            continue
        spec = config["indicators"].get(indicator, {})
        sign = -1.0 if spec.get("direction") == "lower_is_worse" else 1.0

        args = (det["baseline_years"], det["adjust_for_reference_trend"], det.get("guard_years", 1))
        cur = _score_year(df, target_year, *args)
        prev = _score_year(df, target_year - 1, *args)
        cur = cur.merge(prev[["geo_id", "z"]].rename(columns={"z": "z_prev_year"}), on="geo_id", how="left")
        cur["apc"] = cur["geo_id"].map(_annual_percent_change(df, target_year))

        z_dir = sign * cur["z"]
        cur["p_value"] = stats.norm.sf(z_dir)
        cur["q_value"] = benjamini_hochberg(cur["p_value"].to_numpy())
        rr_dir = cur["relative_risk"] if sign > 0 else 1 / cur["relative_risk"]
        reliable = cur["observed"] >= det["min_numerator_reliable"]
        shown = cur["observed"] >= det["min_numerator_shown"]

        level = np.full(len(cur), "stable", dtype=object)
        watch = (z_dir >= det["watch_z"]) & (rr_dir >= det["min_relative_risk_watch"]) & shown
        alert = (cur["q_value"] <= det["alert_q"]) & (rr_dir >= det["min_relative_risk_alert"]) & reliable
        level[watch.to_numpy()] = "watch"
        level[alert.to_numpy()] = "alert"
        level[cur["z"].isna().to_numpy()] = "insufficient data"
        cur["level"] = level
        cur["sustained"] = (z_dir >= det["watch_z"]) & ((sign * cur["z_prev_year"]) >= det["watch_z"])
        cur["reliable"] = reliable
        cur.insert(0, "subgroup", subgroup)
        cur.insert(0, "indicator", indicator)
        results.append(cur)

    if not results:
        return pd.DataFrame()
    out = pd.concat(results, ignore_index=True)
    out["level"] = pd.Categorical(out["level"], LEVELS, ordered=True)
    return out.sort_values(["level", "q_value", "z"], ascending=[True, True, False]).reset_index(drop=True)
