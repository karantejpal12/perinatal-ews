"""County context: health, social, substance-use and maternity-care conditions.

Detection says *where* outcomes are getting worse. Context helps say *why it
might matter there* and *what local capacity exists to respond*. It is used in
three ways:

1. As extra features in the next-year forecast (forecast.py), evaluated
   forward in time against the model without them.
2. In a "need versus access" review list: counties with a perinatal flag, a
   high drug overdose burden and little treatment capacity suitable for
   pregnant and postpartum patients, or few hospitals offering labour and
   delivery care.
3. In plain-language explanations of each county's forecast.

The context table is built by scripts/build_county_context.py from public
CDC PLACES, ACS (via CDC), CDC VSRR overdose, SAMHSA FindTreatment.gov and CMS
Maternal Health data. All measures are county-level and describe places, not
people: they must not be read as statements about any individual parent.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .schema import TOTAL_SUBGROUP

# feature name -> (source column, plain-language label)
STATIC_FEATURES = {
    "ctx_high_blood_pressure": ("bphigh", "adult high blood pressure"),
    "ctx_obesity": ("obesity", "adult obesity"),
    "ctx_diabetes": ("diabetes", "adult diabetes"),
    "ctx_smoking": ("csmoking", "adult smoking"),
    "ctx_depression": ("depression", "adult depression"),
    "ctx_uninsured": ("access2", "uninsured adults aged 18-64"),
    "ctx_poverty": ("acs_pov150", "residents below 150% of poverty"),
    "ctx_unemployment": ("acs_unemp", "unemployment"),
    "ctx_no_high_school": ("acs_nohsdp", "adults without a high-school diploma"),
    "ctx_single_parent": ("acs_sngpnt", "single-parent households"),
    "ctx_no_broadband": ("acs_broad", "households without broadband"),
}
DYNAMIC_LABELS = {
    "ctx_overdose_rate": "drug overdose death rate",
    "ctx_overdose_change": "change in overdose death rate",
    "ctx_moud_per_1k_births": "opioid treatment (MOUD) facilities per 1,000 births",
    "ctx_preg_moud_per_1k_births": "MOUD facilities for pregnant/postpartum patients taking Medicaid, per 1,000 births",
    "ctx_births_per_ld_hospital": "births per labour-and-delivery hospital",
}
CONTEXT_FEATURES = list(STATIC_FEATURES) + list(DYNAMIC_LABELS)
LABELS = {**{k: v[1] for k, v in STATIC_FEATURES.items()}, **DYNAMIC_LABELS}

OVERDOSE_YEARS = range(2020, 2025)


def load_context(path: str | Path) -> pd.DataFrame:
    ctx = pd.read_csv(path, dtype={"geo_id": str})
    ctx["geo_id"] = ctx["geo_id"].str.zfill(5)
    return ctx.set_index("geo_id")


def _overdose(ctx: pd.DataFrame, geo_id: str, year: int) -> float:
    """Overdose rate for the year, or the nearest earlier year with data (never a later one)."""
    for y in range(min(year, max(OVERDOSE_YEARS)), min(OVERDOSE_YEARS) - 1, -1):
        v = ctx.at[geo_id, f"overdose_rate_{y}"] if f"overdose_rate_{y}" in ctx.columns else np.nan
        if pd.notna(v):
            return float(v)
    return np.nan


def add_context_features(feats: pd.DataFrame, ctx: pd.DataFrame) -> pd.DataFrame:
    """Join context onto forecast feature rows (one row per indicator, county, year).

    Overdose rates are matched to the feature year so a model trained on year t
    never sees later information. Facility and hospital counts are a current
    snapshot (2026), applied to all years; this is noted in the model card.
    """
    out = feats.copy()
    have = out["geo_id"].isin(ctx.index)
    for f, (col, _) in STATIC_FEATURES.items():
        out[f] = out["geo_id"].map(ctx[col]) if col in ctx.columns else np.nan
    od, od_prev = [], []
    for gid, y, ok in zip(out["geo_id"], out["year"], have):
        od.append(_overdose(ctx, gid, int(y)) if ok and y >= min(OVERDOSE_YEARS) else np.nan)
        od_prev.append(_overdose(ctx, gid, int(y) - 1) if ok and y - 1 >= min(OVERDOSE_YEARS) else np.nan)
    out["ctx_overdose_rate"] = od
    out["ctx_overdose_change"] = np.asarray(od) - np.asarray(od_prev)
    def col(name):
        return ctx[name] if name in ctx.columns else pd.Series(np.nan, index=ctx.index)

    births = out.groupby(["geo_id", "year"])["births"].transform("max")
    k = births / 1000.0
    out["ctx_moud_per_1k_births"] = out["geo_id"].map(col("moud_facilities")) / k
    out["ctx_preg_moud_per_1k_births"] = out["geo_id"].map(col("preg_moud_medicaid_facilities")) / k
    ld = out["geo_id"].map(col("ld_hospitals"))
    out["ctx_births_per_ld_hospital"] = np.where(ld > 0, births / ld.where(ld > 0), np.nan)
    return out


def need_access(detections: pd.DataFrame, ctx: pd.DataFrame, forecast_scores: pd.DataFrame | None = None,
                risk_threshold: float = 0.30, labels: dict | None = None) -> pd.DataFrame:
    """Counties where perinatal warning signs coincide with high substance-use burden or thin access.

    A county is listed when it has a perinatal signal (an alert or watch flag in
    the total or a payer subgroup, or forecast risk >= `risk_threshold`) AND at
    least one of:

    - overdose death rate in the top quarter of scored counties ("high overdose burden");
    - no facility that offers buprenorphine or methadone, accepts Medicaid and runs a
      programme for pregnant or postpartum patients, or a rate of such facilities per
      1,000 births in the bottom quarter ("thin perinatal SUD treatment access");
    - no hospital reporting labour and delivery care, or births per such hospital in
      the top tenth ("thin delivery capacity").

    Counties with all three of signal, high burden and thin treatment access are
    marked priority "high". The output is a review list for programme planning,
    not a ranking of need.
    """
    labels = labels or {}
    lab = lambda k: labels.get(k, k.replace("_", " ")).lower()  # noqa: E731
    det = detections.copy()
    det["flag"] = det["level"].isin(["alert", "watch"])
    sig = det[det["flag"]].groupby("geo_id").apply(
        lambda g: "; ".join(sorted({f"{lab(r.indicator)} ({r.level}"
                                    + (")" if r.subgroup == TOTAL_SUBGROUP else f", {r.subgroup})")
                                    for r in g.itertuples()})), include_groups=False)
    signals = sig.rename("perinatal_signals")
    if forecast_scores is not None and len(forecast_scores):
        hi = forecast_scores[forecast_scores["risk"] >= risk_threshold]
        fr = hi.groupby("geo_id").apply(
            lambda g: "; ".join(f"{lab(r.indicator)} next-year risk {r.risk:.0%}" for r in g.itertuples()),
            include_groups=False).rename("forecast_signals")
    else:
        fr = pd.Series(dtype=str, name="forecast_signals")

    tot = detections[detections["subgroup"] == TOTAL_SUBGROUP]
    counties = tot.groupby("geo_id").agg(geo_name=("geo_name", "first"), state=("state", "first"),
                                         births=("births", "max"))
    c = counties.join(ctx, how="left", rsuffix="_ctx")
    od_col = max((f"overdose_rate_{y}" for y in OVERDOSE_YEARS if f"overdose_rate_{y}" in c.columns), default=None)
    c["overdose_rate"] = c[od_col] if od_col else np.nan
    c["preg_moud_per_1k_births"] = c.get("preg_moud_medicaid_facilities", np.nan) / (c["births"] / 1000)
    c["births_per_ld_hospital"] = np.where(c.get("ld_hospitals", 0) > 0,
                                           c["births"] / c.get("ld_hospitals", np.nan).where(c.get("ld_hospitals", 0) > 0),
                                           np.nan)
    od_q = c["overdose_rate"].quantile(0.75)
    acc_q = c["preg_moud_per_1k_births"].quantile(0.25)
    ld_q = c["births_per_ld_hospital"].quantile(0.90)
    c["high_overdose_burden"] = c["overdose_rate"] >= od_q
    c["thin_treatment_access"] = (c.get("preg_moud_medicaid_facilities", np.nan) == 0) | (c["preg_moud_per_1k_births"] <= acc_q)
    no_ld = (c.get("ld_hospitals", np.nan) == 0) & (c.get("hospitals_ld_status_unknown", 0) == 0)
    c["thin_delivery_capacity"] = no_ld | (c["births_per_ld_hospital"] >= ld_q)
    c = c.join(signals, how="left").join(fr, how="left")
    c["has_signal"] = c["perinatal_signals"].notna() | c["forecast_signals"].notna()
    keep = c["has_signal"] & (c["high_overdose_burden"] | c["thin_treatment_access"] | c["thin_delivery_capacity"])
    out = c[keep].copy()
    out["priority"] = np.where(out["high_overdose_burden"] & out["thin_treatment_access"], "high", "review")

    def why(r):
        parts = []
        if r.high_overdose_burden:
            parts.append(f"overdose deaths {r.overdose_rate:.0f} per 100k (top quarter)")
        if r.thin_treatment_access:
            n = r.get("preg_moud_medicaid_facilities", np.nan)
            parts.append("no MOUD facility listed for pregnant/postpartum patients that accepts Medicaid"
                         if n == 0 else f"{int(n)} MOUD {'facility' if n == 1 else 'facilities'} for pregnant/postpartum patients taking Medicaid "
                                        f"({r.preg_moud_per_1k_births:.2f} per 1,000 births, bottom quarter)")
        if r.thin_delivery_capacity:
            parts.append("no hospital in the county reports labour and delivery care to CMS "
                         "(residents may deliver in neighbouring counties)" if r.get("ld_hospitals", 0) == 0
                         else f"{r.births_per_ld_hospital:,.0f} births per labour-and-delivery hospital (top tenth)")
        return "; ".join(parts)

    out["context_reasons"] = out.apply(why, axis=1)
    out["thresholds"] = (f"overdose >= {od_q:.1f}/100k; MOUD-for-pregnancy facilities <= {acc_q:.2f}/1k births; "
                         f"births per L&D hospital >= {ld_q:,.0f}")
    cols = ["geo_name", "state", "births", "priority", "perinatal_signals", "forecast_signals", "context_reasons",
            "overdose_rate", "preg_moud_medicaid_facilities", "preg_moud_per_1k_births", "ld_hospitals",
            "births_per_ld_hospital", "high_overdose_burden", "thin_treatment_access", "thin_delivery_capacity",
            "thresholds"]
    out = out[[k for k in cols if k in out.columns]].reset_index()
    out["_p"] = (out["priority"] == "high").astype(int)
    return out.sort_values(["_p", "overdose_rate"], ascending=[False, False]).drop(columns="_p").reset_index(drop=True)


def explain(model, X: pd.DataFrame, features: list[str], reference: pd.Series, top: int = 3,
            labels: dict | None = None) -> list[str]:
    """Approximate per-row explanation for a fitted classifier.

    For each feature, the row's value is replaced by the reference value (the
    training median) and the change in predicted risk is recorded. The largest
    risk-raising factors are returned in plain language. This is a simple
    occlusion method, not SHAP; it is described as "approximate" in outputs.
    """
    labels = labels or {}
    base = model.predict_proba(X)[:, 1]
    contrib = np.zeros((len(X), len(features)))
    for j, f in enumerate(features):
        Xr = X.copy()
        Xr[f] = reference.get(f, np.nan)
        contrib[:, j] = base - model.predict_proba(Xr)[:, 1]
    out = []
    for i in range(len(X)):
        order = np.argsort(-contrib[i])
        parts = [f"{labels.get(features[j], features[j])} (+{contrib[i, j] * 100:.0f} pts)"
                 for j in order[:top] if contrib[i, j] >= 0.01]
        out.append("; ".join(parts))
    return out


BENCHMARK_COLUMNS = {
    "bphigh": "adult high blood pressure", "obesity": "adult obesity", "diabetes": "adult diabetes",
    "csmoking": "adult smoking", "depression": "adult depression", "access2": "uninsured adults",
    "checkup": "routine check-ups", "binge": "binge drinking", "acs_pov150": "poverty",
    "acs_unemp": "unemployment", "acs_nohsdp": "no high-school diploma", "acs_sngpnt": "single-parent households",
    "acs_broad": "no broadband", "acs_hcost": "housing cost burden", "acs_crowd": "crowded housing",
    "overdose_rate_2023": "overdose death rate", "moud_facilities_per100k": "MOUD facilities per capita",
    "pregnant_programs_per100k": "SUD programmes for pregnant/postpartum patients per capita",
}


def benchmark(tidy: pd.DataFrame, ctx: pd.DataFrame, config: dict, year: int | None = None,
              pool_years: int = 3, n_splits: int = 5, seed: int = 0, coverage: float = 0.90):
    """Context-adjusted benchmark: is a county's rate higher than counties with similar conditions?

    For each indicator, a gradient-boosted regression model predicts each county's
    pooled rate over the last `pool_years` years (log-odds, weighted by births)
    from its health, social, substance-use and access context only. Predictions
    are out-of-fold (K-fold cross-validation), so a county is never compared with
    a model that saw it. The ratio observed / predicted then says whether the
    county does worse or better than places like it, which a raw ranking cannot.

    Each county also gets a 90% prediction range for "counties like this one"
    (cross-conformal prediction on normalised residuals): the range a county's
    rate would fall in 90% of the time if it behaved like similar counties. A
    county is "higher/lower than similar counties" when its rate is outside the
    range. Empirical coverage of the ranges is reported.

    Returns (scores, quality): scores per county-indicator, and cross-validated
    R-squared for the context model against a state-average baseline.
    """
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.model_selection import KFold

    year = int(year or tidy["year"].max())
    yrs = list(range(year - pool_years + 1, year + 1))
    d = tidy[(tidy["subgroup"] == TOTAL_SUBGROUP) & tidy["year"].isin(yrs)].dropna(subset=["numerator", "denominator"])
    g = d.groupby(["indicator", "geo_id"]).agg(geo_name=("geo_name", "first"), state=("state", "first"),
                                               numerator=("numerator", "sum"), denominator=("denominator", "sum"),
                                               n_years=("year", "nunique")).reset_index()
    g = g[(g["n_years"] == pool_years) & (g["denominator"] > 0) & (g["numerator"] >= 20)]
    cols = [c for c in BENCHMARK_COLUMNS if c in ctx.columns]
    rows, quality = [], []
    for ind, gi in g.groupby("indicator"):
        gi = gi[gi["geo_id"].isin(ctx.index)].reset_index(drop=True)
        if len(gi) < 50:
            continue
        X = ctx.loc[gi["geo_id"], cols].astype(float).to_numpy()
        p = gi["numerator"] / gi["denominator"]
        y = np.log(p / (1 - p)).to_numpy()
        w = gi["denominator"].to_numpy(dtype=float)
        pred = np.full(len(gi), np.nan)
        pred_state = np.full(len(gi), np.nan)
        kf = KFold(n_splits=n_splits, shuffle=True, random_state=seed)
        fold = np.zeros(len(gi), dtype=int)
        for f_i, (tr, te) in enumerate(kf.split(X)):
            fold[te] = f_i
            m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                              min_samples_leaf=20, l2_regularization=1.0, random_state=seed)
            m.fit(X[tr], y[tr], sample_weight=w[tr])
            pred[te] = m.predict(X[te])
            # Baseline: births-weighted mean of the same state's other counties in the training fold.
            st_tr = gi.loc[tr].assign(y=y[tr], w=w[tr])
            st_mean = st_tr.groupby("state").apply(lambda s: np.average(s["y"], weights=s["w"]), include_groups=False)
            overall = np.average(y[tr], weights=w[tr])
            pred_state[te] = gi.loc[te, "state"].map(st_mean).fillna(overall).to_numpy()

        def r2(pr):
            yb = np.average(y, weights=w)
            return 1 - np.sum(w * (y - pr) ** 2) / np.sum(w * (y - yb) ** 2)

        exp = 1 / (1 + np.exp(-pred))
        e_cases = exp * w
        se = np.sqrt(e_cases * (1 - exp))
        # Residual spread the model does not explain, so the z-score is not over-confident.
        resid_sd = np.sqrt(np.average((p - exp) ** 2, weights=w))
        z = (gi["numerator"] - e_cases) / np.sqrt(se ** 2 + (resid_sd * w) ** 2)

        # Cross-conformal prediction interval (normalised residuals, log-odds scale). Each county's
        # interval width uses the residuals of the *other* folds only, so coverage is honest.
        v = 1 / gi["numerator"].to_numpy(float) + 1 / (w - gi["numerator"].to_numpy(float))
        s2 = max(np.average((y - pred) ** 2, weights=w) - np.average(v, weights=w), 1e-4)
        sigma = np.sqrt(v + s2)
        score = np.abs(y - pred) / sigma
        alpha = 1 - coverage
        q = np.empty(len(gi))
        for f_i in np.unique(fold):
            other = score[fold != f_i]
            lvl = min(1.0, np.ceil((len(other) + 1) * (1 - alpha)) / len(other))
            q[fold == f_i] = np.quantile(other, lvl, method="higher")
        lo = 1 / (1 + np.exp(-(pred - q * sigma)))
        hi = 1 / (1 + np.exp(-(pred + q * sigma)))
        inside = (p >= lo) & (p <= hi)
        quality.append({"indicator": ind, "counties": len(gi), "years_pooled": f"{yrs[0]}-{yrs[-1]}",
                        "r2_context_model": r2(pred), "r2_state_average": r2(pred_state),
                        "interval_target_coverage": coverage, "interval_empirical_coverage": float(inside.mean())})
        rows.append(gi.assign(observed_rate=p, context_expected_rate=exp, similar_range_low=lo, similar_range_high=hi,
                              ratio_to_similar=p / exp, z_vs_similar=z,
                              compared_with_similar=np.where(p > hi, "higher than similar counties",
                                                             np.where(p < lo, "lower than similar counties",
                                                                      "in line with similar counties"))))
    scores = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return scores, pd.DataFrame(quality)
