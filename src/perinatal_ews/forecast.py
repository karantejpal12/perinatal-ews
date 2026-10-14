"""Machine-learning forecast: which counties are likely to deteriorate next year?

Detection (detect.py) says where an indicator is already worse than expected.
This module looks one year ahead. For every county and indicator it predicts
the probability that next year's detection will flag the county (z >= the watch
threshold, in the harmful direction), using only information available at the
end of the current year:

- the county's recent rates, trend and detection scores
- its size and payer mix (share of births paid by Medicaid)
- its Medicaid vs private-insurance gap
- what is happening across its state (state trend, share of counties flagged)
- the national trend for the indicator

The model is a gradient-boosted tree classifier, chosen because it handles
non-linear interactions on small tabular data without heavy tuning. It is
evaluated strictly forward in time (train on earlier years, test on later ones)
against two simple baselines, and its calibration and performance are reported
separately for small, medium and large counties.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from .detect import detect
from .schema import TOTAL_SUBGROUP

FEATURES = [
    "z", "z_prev", "relative_risk", "logit_rate", "logit_change_1y", "logit_change_2y", "apc",
    "logit_rate_vs_peer", "log_births", "medicaid_share", "medicaid_private_ratio",
    "state_change_vs_national", "state_share_flagged", "peer_drift", "indicator_code",
]


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def size_class(births: float) -> str:
    if not np.isfinite(births):
        return "unknown"
    if births < 1_000:
        return "small (<1k births)"
    if births < 5_000:
        return "medium (1k-5k)"
    return "large (5k+)"


def _rates(tidy: pd.DataFrame) -> pd.DataFrame:
    d = tidy.dropna(subset=["numerator", "denominator"])
    d = d[d["denominator"] > 0]
    return d.assign(rate=d["numerator"] / d["denominator"])


def build_features(tidy: pd.DataFrame, config: dict, years: list[int]) -> pd.DataFrame:
    """One row per (indicator, county, year t) with features known at the end of year t."""
    indicators = list(config["indicators"])
    codes = {k: i for i, k in enumerate(indicators)}
    r = _rates(tidy)
    tot = r[r["subgroup"] == TOTAL_SUBGROUP]
    piv = tot.pivot_table(index=["indicator", "geo_id"], columns="year", values="rate")

    # Payer mix and Medicaid/private gap, when subgroup rows exist.
    sub = r[r["subgroup"].isin(["Medicaid", "Private insurance"])]
    sub_rate = sub.pivot_table(index=["indicator", "geo_id", "year"], columns="subgroup", values="rate")
    den = tidy.pivot_table(index=["indicator", "geo_id", "year"], columns="subgroup", values="denominator")

    rows = []
    for t in years:
        cur = detect(tidy, config, target_year=t)
        cur = cur[(cur["subgroup"] == TOTAL_SUBGROUP)]
        cur = cur.assign(flag=cur["level"].isin(["alert", "watch"]))
        state_flag = cur.groupby(["indicator", "state"])["flag"].mean().rename("state_share_flagged")

        st = tot[tot["year"].isin([t - 1, t])].groupby(["indicator", "state", "year"])[
            ["numerator", "denominator"]].sum()
        st_rate = (st["numerator"] / st["denominator"]).unstack("year")
        nat = tot[tot["year"].isin([t - 1, t])].groupby(["indicator", "year"])[["numerator", "denominator"]].sum()
        nat_rate = (nat["numerator"] / nat["denominator"]).unstack("year")
        st_change = (st_rate[t] / st_rate[t - 1]).div(
            (nat_rate[t] / nat_rate[t - 1]).reindex(st_rate.index.get_level_values(0)).to_numpy())
        st_change = st_change.rename("state_change_vs_national")

        cur = cur.join(state_flag, on=["indicator", "state"]).join(st_change, on=["indicator", "state"])
        for c in cur.itertuples():
            key = (c.indicator, c.geo_id)
            hist = piv.loc[key] if key in piv.index else pd.Series(dtype=float)
            r_t, r_1, r_2 = (hist.get(t, np.nan), hist.get(t - 1, np.nan), hist.get(t - 2, np.nan))
            sk = (c.indicator, c.geo_id, t)
            med = sub_rate.at[sk, "Medicaid"] if sk in sub_rate.index and "Medicaid" in sub_rate else np.nan
            prv = (sub_rate.at[sk, "Private insurance"]
                   if sk in sub_rate.index and "Private insurance" in sub_rate else np.nan)
            d_med = den.at[sk, "Medicaid"] if sk in den.index and "Medicaid" in den else np.nan
            d_all = den.at[sk, TOTAL_SUBGROUP] if sk in den.index and TOTAL_SUBGROUP in den else np.nan
            rows.append({
                "indicator": c.indicator, "geo_id": c.geo_id, "geo_name": c.geo_name, "state": c.state, "year": t,
                "births": c.births, "level_now": c.level,
                "z": c.z, "z_prev": c.z_prev_year, "relative_risk": c.relative_risk,
                "logit_rate": _logit(r_t) if np.isfinite(r_t) else np.nan,
                "logit_change_1y": (_logit(r_t) - _logit(r_1)) if np.isfinite(r_t) and np.isfinite(r_1) else np.nan,
                "logit_change_2y": (_logit(r_t) - _logit(r_2)) if np.isfinite(r_t) and np.isfinite(r_2) else np.nan,
                "apc": c.apc,
                "logit_rate_vs_peer": (_logit(r_t) - _logit(c.peer_rate)) if np.isfinite(r_t) else np.nan,
                "log_births": np.log(c.births) if c.births and np.isfinite(c.births) and c.births > 0 else np.nan,
                "medicaid_share": d_med / d_all if np.isfinite(d_med) and d_all else np.nan,
                "medicaid_private_ratio": med / prv if np.isfinite(med) and np.isfinite(prv) and prv > 0 else np.nan,
                "state_change_vs_national": c.state_change_vs_national,
                "state_share_flagged": c.state_share_flagged,
                "peer_drift": c.peer_drift,
                "indicator_code": codes.get(c.indicator, -1),
            })
    return pd.DataFrame(rows)


def add_targets(features: pd.DataFrame, tidy: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Attach the outcome: was the county flagged (z >= watch_z, harmful direction) the following year?"""
    watch_z = config["detection"]["watch_z"]
    out = []
    for t, g in features.groupby("year"):
        if t + 1 > tidy["year"].max():
            out.append(g.assign(target=np.nan))
            continue
        nxt = detect(tidy, config, target_year=t + 1)
        nxt = nxt[nxt["subgroup"] == TOTAL_SUBGROUP].set_index(["indicator", "geo_id"])
        sign = {k: (-1.0 if v.get("direction") == "lower_is_worse" else 1.0)
                for k, v in config["indicators"].items()}
        z_next = [sign.get(i, 1.0) * nxt["z"].get((i, gid), np.nan) for i, gid in zip(g["indicator"], g["geo_id"])]
        z_next = np.asarray(z_next, dtype=float)
        target = np.where(np.isnan(z_next), np.nan, (z_next >= watch_z).astype(float))
        out.append(g.assign(target=target, z_next=z_next))
    return pd.concat(out, ignore_index=True)


def _X(df: pd.DataFrame) -> pd.DataFrame:
    """Feature matrix. A feature with no values at all (e.g. payer mix when the data have no
    subgroup rows) is set to 0 so it carries no information instead of breaking the model."""
    X = df[FEATURES].astype(float).copy()
    for c in X.columns[X.isna().all()]:
        X[c] = 0.0
    return X


def _model(seed: int = 0) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=250, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=40,
        l2_regularization=1.0, categorical_features=[FEATURES.index("indicator_code")], random_state=seed)


def _metrics(y, p) -> dict:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    ok = ~np.isnan(y) & ~np.isnan(p)
    y, p = y[ok], p[ok]
    if len(np.unique(y)) < 2:
        return {"n": len(y), "positives": int(y.sum()), "auroc": np.nan, "auprc": np.nan, "brier": np.nan}
    k = max(1, int(round(0.1 * len(p))))
    top = np.argsort(-p)[:k]
    return {"n": len(y), "positives": int(y.sum()), "prevalence": y.mean(),
            "auroc": roc_auc_score(y, p), "auprc": average_precision_score(y, p), "brier": brier_score_loss(y, p),
            "precision_top10pct": y[top].mean(), "recall_top10pct": y[top].sum() / max(y.sum(), 1)}


def _calibration(y, p, bins: int = 5) -> pd.DataFrame:
    d = pd.DataFrame({"y": y, "p": p}).dropna()
    d["bin"] = pd.qcut(d["p"], q=min(bins, d["p"].nunique()), duplicates="drop")
    c = d.groupby("bin", observed=True).agg(n=("y", "size"), mean_predicted=("p", "mean"), observed_rate=("y", "mean"))
    return c.reset_index(drop=True)


def _psi(a, b, bins: int = 10) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < bins or len(b) < bins:
        return np.nan
    edges = np.unique(np.quantile(a, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return np.nan
    edges[0], edges[-1] = -np.inf, np.inf
    pa = np.clip(np.histogram(a, edges)[0] / len(a), 1e-4, None)
    pb = np.clip(np.histogram(b, edges)[0] / len(b), 1e-4, None)
    return float(np.sum((pb - pa) * np.log(pb / pa)))


@dataclass
class ForecastResult:
    forecast_year: int
    scores: pd.DataFrame                      # risk for forecast_year, one row per county-indicator
    metrics: pd.DataFrame                     # model vs baselines, averaged over held-out years
    by_size: pd.DataFrame                     # held-out performance by county size (pooled over folds)
    by_indicator: pd.DataFrame
    calibration: pd.DataFrame
    importance: pd.DataFrame
    feature_drift: pd.DataFrame               # PSI, training years vs scoring year
    folds: pd.DataFrame = field(default_factory=pd.DataFrame)   # metrics per held-out outcome year
    outcome_years: list[int] = field(default_factory=list)
    selected_model: str = ""


def run_forecast(tidy: pd.DataFrame, config: dict, seed: int = 0, n_folds: int = 2) -> ForecastResult:
    """Train, evaluate forward in time, and score next year's risk."""
    det = config["detection"]
    first = int(tidy["year"].min()) + det["baseline_years"] + det.get("guard_years", 1)
    last = int(tidy["year"].max())
    years = list(range(first, last + 1))
    if len(years) < 3:
        raise ValueError(f"need at least {first + 2 - int(tidy['year'].min())} years of data for forecasting")

    feats = add_targets(build_features(tidy, config, years), tidy, config)
    labelled = feats.dropna(subset=["target"])
    label_years = sorted(labelled["year"].unique())
    # Rolling-origin evaluation: each of the last `n_folds` labelled years is predicted by a model
    # trained only on earlier years, exactly as the system would have been used at the time.
    test_years = label_years[-n_folds:] if len(label_years) > n_folds else label_years[1:]
    lr_cols = ["z", "z_prev"]
    preds, fold_rows, imps = [], [], []
    rng = np.random.default_rng(seed)
    for test_t in test_years:
        train = labelled[labelled["year"] < test_t]
        test = labelled[labelled["year"] == test_t]
        model = _model(seed).fit(_X(train), train["target"])
        p_model = model.predict_proba(_X(test))[:, 1]
        p_persist = 1 / (1 + np.exp(-(test["z"].fillna(0).to_numpy() - det["watch_z"])))
        lr = LogisticRegression().fit(train[lr_cols].fillna(0), train["target"])
        p_lr = lr.predict_proba(test[lr_cols].fillna(0))[:, 1]
        y = test["target"].to_numpy()
        for name, p in [("Gradient-boosted trees (perinatal-ews)", p_model),
                        ("Logistic regression on z-scores", p_lr),
                        ("Persistence (current z only)", p_persist)]:
            fold_rows.append({"outcome_year": int(test_t) + 1, "model": name, **_metrics(y, p)})
        # Bootstrap the difference in average precision against the best baseline.
        diffs = []
        for _ in range(500):
            i = rng.integers(0, len(y), len(y))
            if y[i].sum() == 0:
                continue
            diffs.append(average_precision_score(y[i], p_model[i]) -
                         max(average_precision_score(y[i], p_lr[i]), average_precision_score(y[i], p_persist[i])))
        fold_rows[-3]["auprc_gain_vs_best_baseline_ci95"] = (
            f"{np.percentile(diffs, 2.5):+.3f} to {np.percentile(diffs, 97.5):+.3f}" if diffs else "")
        preds.append(test.assign(p=p_model))
        imp = permutation_importance(model, _X(test), test["target"], scoring="average_precision",
                                     n_repeats=10, random_state=seed)
        imps.append(imp.importances_mean)

    folds = pd.DataFrame(fold_rows)
    num = ["auroc", "auprc", "brier", "precision_top10pct", "recall_top10pct"]
    metrics = folds.groupby("model", sort=False)[num + ["positives", "n"]].mean().reset_index()
    metrics["outcome_years"] = ", ".join(str(int(t) + 1) for t in test_years)

    ev = pd.concat(preds, ignore_index=True)
    ev["size_class"] = ev["births"].map(size_class)
    by_size = pd.DataFrame([{"size_class": s, **_metrics(g["target"], g["p"])}
                            for s, g in ev.groupby("size_class") if s != "unknown"])
    by_ind = pd.DataFrame([{"indicator": s, **_metrics(g["target"], g["p"])} for s, g in ev.groupby("indicator")])
    calib = _calibration(ev["target"], ev["p"])
    importance = pd.DataFrame({"feature": FEATURES, "importance": np.mean(imps, axis=0)}).sort_values(
        "importance", ascending=False)

    # Pick the trainable method with the best held-out average precision, so that on small or
    # low-signal data the system falls back to the simpler model rather than overfitting.
    gb_name, lr_name = "Gradient-boosted trees (perinatal-ews)", "Logistic regression on z-scores"
    perf = metrics.set_index("model")["auprc"]
    selected = gb_name if perf.get(gb_name, -1) >= perf.get(lr_name, -1) else lr_name
    metrics["selected"] = metrics["model"] == selected

    # Refit the selected method on every labelled year, then score the latest year.
    score_rows = feats[feats["year"] == last].copy()
    if selected == gb_name:
        final = _model(seed).fit(_X(labelled), labelled["target"])
        score_rows["risk"] = final.predict_proba(_X(score_rows))[:, 1]
    else:
        final = LogisticRegression().fit(labelled[lr_cols].fillna(0), labelled["target"])
        score_rows["risk"] = final.predict_proba(score_rows[lr_cols].fillna(0))[:, 1]
    score_rows["forecast_year"] = last + 1
    score_rows["size_class"] = score_rows["births"].map(size_class)
    base_rate = labelled["target"].mean()
    score_rows["risk_vs_average"] = score_rows["risk"] / base_rate
    scores = score_rows.sort_values("risk", ascending=False).reset_index(drop=True)

    # Features with few distinct values (indicator, national drift) are not meaningful for PSI.
    drift = pd.DataFrame([{"feature": f, "psi": _psi(labelled[f], score_rows[f])} for f in FEATURES
                          if labelled[f].nunique() >= 20])
    drift["status"] = np.where(drift["psi"] < 0.10, "stable", np.where(drift["psi"] < 0.25, "moderate shift", "major shift"))

    return ForecastResult(
        forecast_year=last + 1, scores=scores, metrics=metrics, by_size=by_size, by_indicator=by_ind,
        calibration=calib, importance=importance, feature_drift=drift.sort_values("psi", ascending=False),
        folds=folds, outcome_years=[int(t) + 1 for t in test_years], selected_model=selected)
