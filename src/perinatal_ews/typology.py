"""County typology: unsupervised clustering of counties into peer groups.

Counties are grouped by what they look like (adult health, social conditions,
overdose burden, treatment and delivery access, size) and by their perinatal
outcomes (recent levels and 2016-2024 trends of the four indicators). Each type
is a peer group a health department can compare itself with.

Method
- Features: recent (3-year) level of each indicator, county size, and county
  context. Trends are left out: they are noisy at county level, already
  covered by detection, and made the groups less stable in testing
  (bootstrap ARI 0.70 with trends vs 0.79 without).
- Skewed features (overdose rate, treatment access) are log-transformed; all
  are standardised (median imputation for the few missing values).
- K-means is fitted for k = 4..8; k is chosen by the mean silhouette score.
- Stability: the clustering is repeated on 50 bootstrap resamples and compared
  with the full-data clustering by the adjusted Rand index (ARI); values above
  about 0.6 indicate reasonably stable groups.
- Each type is described by the features on which its average differs most
  from all counties (in standard deviations).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import TOTAL_SUBGROUP

CONTEXT = {
    "bphigh": "adult high blood pressure", "obesity": "adult obesity", "diabetes": "adult diabetes",
    "csmoking": "adult smoking", "access2": "uninsured adults", "acs_pov150": "poverty",
    "acs_nohsdp": "no high-school diploma", "acs_sngpnt": "single-parent households",
    "acs_broad": "no broadband", "overdose_rate_2024": "overdose deaths",
}
INDICATOR_SHORT = {"late_no_prenatal_care": "late prenatal care", "preterm_birth": "preterm birth",
                   "low_birth_weight": "low birth weight", "gestational_hypertension": "gestational hypertension"}


def _logit(p):
    if isinstance(p, pd.Series):
        q = p.clip(1e-4, 1 - 1e-4)
        return np.log(q / (1 - q))
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def build_features(tidy: pd.DataFrame, ctx: pd.DataFrame | None, recent_years: int = 3,
                   include_trends: bool = False):
    """One row per county. Returns (features, labels) where labels maps feature -> plain name."""
    t = tidy[(tidy["subgroup"] == TOTAL_SUBGROUP)].dropna(subset=["numerator", "denominator"])
    t = t[t["denominator"] > 0]
    last = int(t["year"].max())
    rec = t[t["year"] > last - recent_years].groupby(["geo_id", "indicator"])[["numerator", "denominator"]].sum()
    level = _logit(rec["numerator"] / rec["denominator"]).unstack("indicator")
    level.columns = [f"level_{c}" for c in level.columns]
    # Trend: births-weighted slope of the logit rate per year over all years.
    t = t.assign(lr=_logit(t["numerator"] / t["denominator"]))

    def slope(g):
        if g["year"].nunique() < 5:
            return np.nan
        w = g["denominator"].to_numpy(float)
        x = g["year"].to_numpy(float)
        y = g["lr"].to_numpy(float)
        xm, ym = np.average(x, weights=w), np.average(y, weights=w)
        return np.sum(w * (x - xm) * (y - ym)) / np.sum(w * (x - xm) ** 2)

    trend = t.groupby(["geo_id", "indicator"])[["year", "lr", "denominator"]].apply(slope).unstack("indicator")
    trend.columns = [f"trend_{c}" for c in trend.columns]
    births = t.groupby(["geo_id", "year"])["denominator"].max().groupby("geo_id").mean()
    X = (level.join(trend, how="outer") if include_trends else level).join(
        np.log(births).rename("log_births"), how="left")
    labels = {f"level_{k}": f"{v} level" for k, v in INDICATOR_SHORT.items()}
    labels |= {f"trend_{k}": f"{v} trend" for k, v in INDICATOR_SHORT.items()}
    labels["log_births"] = "county size (births)"
    if ctx is not None:
        cols = [c for c in CONTEXT if c in ctx.columns]
        X = X.join(ctx[cols], how="left")
        if "overdose_rate_2024" in X:
            X["overdose_rate_2024"] = np.log(X["overdose_rate_2024"])  # strongly right-skewed
        labels |= {c: CONTEXT[c] for c in cols}
        if "preg_moud_medicaid_facilities" in ctx.columns:
            X["treatment_access"] = np.log1p(ctx["preg_moud_medicaid_facilities"].reindex(X.index)
                                             / (births.reindex(X.index) / 1000))
            labels["treatment_access"] = "MOUD access for pregnant patients (per 1,000 births)"
    X = X[[c for c in X.columns if X[c].notna().mean() > 0.8]]
    return X, labels


def fit_typology(X: pd.DataFrame, labels: dict, k_range=range(4, 9), n_boot: int = 50, seed: int = 0):
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score, silhouette_score

    Z = (X - X.median()) / X.std(ddof=0).replace(0, 1)
    Z = Z.fillna(0.0).clip(-4, 4)
    A = Z.to_numpy()
    scores = []
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=20, random_state=seed).fit(A)
        scores.append({"k": k, "silhouette": silhouette_score(A, km.labels_)})
    scores = pd.DataFrame(scores)
    k = int(scores.loc[scores["silhouette"].idxmax(), "k"])
    km = KMeans(n_clusters=k, n_init=50, random_state=seed).fit(A)
    lab = km.labels_
    rng = np.random.default_rng(seed)
    aris = []
    for _ in range(n_boot):
        i = rng.integers(0, len(A), len(A))
        kb = KMeans(n_clusters=k, n_init=10, random_state=int(rng.integers(1e9))).fit(A[i])
        aris.append(adjusted_rand_score(lab, kb.predict(A)))

    # Order types by size, describe each by its most distinctive features.
    order = pd.Series(lab).value_counts().index.tolist()
    remap = {old: new + 1 for new, old in enumerate(order)}
    lab = np.array([remap[v] for v in lab])
    prof_rows, names = [], {}
    for t in sorted(set(lab)):
        m = Z[lab == t].mean()
        top_hi = m.sort_values(ascending=False).head(3)
        top_lo = m.sort_values().head(2)
        hi = [labels.get(f, f) for f, v in top_hi.items() if v >= 0.4]
        lo = [labels.get(f, f) for f, v in top_lo.items() if v <= -0.4]
        desc = ("Higher " + ", ".join(hi[:3]) if hi else "") + ("; lower " + ", ".join(lo[:2]) if lo else "")
        names[t] = desc.strip("; ") or "Close to average on most measures"
        for f, v in m.items():
            prof_rows.append({"type": t, "feature": f, "label": labels.get(f, f), "mean_z": round(float(v), 3)})
    assign = pd.DataFrame({"geo_id": X.index, "type": lab})
    assign["type_description"] = assign["type"].map(names)
    # Distance to own centre, as a "how typical" score.
    cen = np.vstack([A[lab == t].mean(axis=0) for t in sorted(set(lab))])
    d = np.linalg.norm(A - cen[lab - 1], axis=1)
    assign["typicality"] = np.round(1 - (pd.Series(d).rank(pct=True)).to_numpy(), 3)
    summary = pd.DataFrame([{"type": t, "counties": int((lab == t).sum()), "description": names[t]}
                            for t in sorted(set(lab))])
    quality = {"k": k, "silhouette": float(scores["silhouette"].max()),
               "bootstrap_ari_median": float(np.median(aris)), "bootstrap_ari_p10": float(np.percentile(aris, 10)),
               "features": list(X.columns), "k_search": scores.round(4).to_dict("records")}
    return assign, summary, pd.DataFrame(prof_rows), quality


def county_typology(tidy: pd.DataFrame, ctx: pd.DataFrame | None, seed: int = 0):
    X, labels = build_features(tidy, ctx)
    return fit_typology(X, labels, seed=seed)
