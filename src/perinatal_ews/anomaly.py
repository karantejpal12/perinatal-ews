"""Machine-learning data-quality check: unusual county-year records.

Before detection, perinatal-ews checks the input for records that do not look
like the rest of the data, such as a sudden drop in births, a rate that jumps
in one indicator only, or a category that collapses to near zero. These are
often data errors (a late file, a coding change, a mis-assigned category) and
would otherwise produce false alerts.

An Isolation Forest (an unsupervised anomaly-detection model) is trained on
every county-year record. Each record is described by:

- log births and the change in births from the year before;
- for each indicator, the rate (log-odds), its change from the year before,
  and its distance from the county's own median rate, both divided by their
  sampling standard error so that ordinary noise in small counties does not
  look unusual.

Records the model finds easiest to isolate are listed, with the features that
make them unusual. The model is validated on synthetic data with known,
injected errors (see `validate_on_synthetic`), against the existing
rule-based check (births changing by more than 30%). The two are
complementary: the rule catches births that drop or jump; the model catches
problems inside one indicator (a spike, or a category that collapses), which
the rule cannot see. Averaged over five synthetic datasets (2% of records
flagged), the model found 65% of collapsed categories and 67% of
single-indicator spikes with 0.5% false flags on clean records; the rule found
all births drops and 0-4% of the others.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import TOTAL_SUBGROUP

LABELS = {"log_births": "births", "births_change": "change in births"}


def _features(tidy: pd.DataFrame) -> pd.DataFrame:
    d = tidy[tidy["subgroup"] == TOTAL_SUBGROUP].copy()
    d = d[d["denominator"] > 0]
    num = d["numerator"].clip(lower=0.5)
    non = (d["denominator"] - d["numerator"]).clip(lower=0.5)
    d["lr"] = np.log(num / non)
    d["var"] = 1 / num + 1 / non  # sampling variance of the log-odds
    lr = d.pivot_table(index=["geo_id", "year"], columns="indicator", values="lr")
    var = d.pivot_table(index=["geo_id", "year"], columns="indicator", values="var")
    births = d.groupby(["geo_id", "year"])["denominator"].max()
    X = pd.DataFrame(index=lr.index)
    X["log_births"] = np.log(births.reindex(X.index))
    lb = X["log_births"].groupby(level="geo_id")
    X["births_change"] = X["log_births"] - lb.shift(1)
    for ind in lr.columns:
        s = lr[ind]
        g = s.groupby(level="geo_id")
        v = var[ind]
        # Changes are scaled by their sampling noise, so ordinary small-county noise is not "unusual".
        X[f"rate_{ind}"] = s
        X[f"change_{ind}"] = (s - g.shift(1)) / np.sqrt(v + v.groupby(level="geo_id").shift(1))
        X[f"vs_own_median_{ind}"] = (s - g.transform("median")) / np.sqrt(v)
    return X


def _label(f: str) -> str:
    if f in LABELS:
        return LABELS[f]
    for pre, txt in (("rate_", "rate of "), ("change_", "year-on-year change in "), ("vs_own_median_", "distance from usual level of ")):
        if f.startswith(pre):
            return txt + f[len(pre):].replace("_", " ")
    return f


def record_anomalies(tidy: pd.DataFrame, contamination: float = 0.02, year: int | None = None,
                     seed: int = 0) -> pd.DataFrame:
    """Score every county-year; return the most unusual records (all years, or one year)."""
    from sklearn.ensemble import IsolationForest

    X = _features(tidy)
    # The first year has no change features; give it neutral values so it can still be scored.
    Xf = X.copy()
    for c in Xf.columns:
        Xf[c] = Xf[c].fillna(Xf[c].median())
    Z = (Xf - Xf.median()) / (Xf.quantile(0.75) - Xf.quantile(0.25)).replace(0, 1)
    model = IsolationForest(n_estimators=400, contamination=contamination, random_state=seed).fit(Z)
    score = -model.score_samples(Z)
    flag = model.predict(Z) == -1
    out = X.reset_index()[["geo_id", "year"]].assign(anomaly_score=np.round(score, 4), unusual=flag)
    # Explain: the features with the largest robust z-scores for that record.
    absz = Z.abs().to_numpy()
    cols = list(Z.columns)
    reasons = []
    for i in range(len(Z)):
        top = np.argsort(-absz[i])[:2]
        reasons.append("; ".join(f"{_label(cols[j])} ({'high' if Z.iat[i, j] > 0 else 'low'})" for j in top if absz[i, j] >= 2))
    out["why_unusual"] = reasons
    names = tidy.drop_duplicates("geo_id").set_index("geo_id")[["geo_name", "state"]]
    out = out.join(names, on="geo_id")
    if year is not None:
        out = out[out["year"] == int(year)]
    return out[out["unusual"]].sort_values("anomaly_score", ascending=False).reset_index(drop=True)


def inject_errors(tidy: pd.DataFrame, n_each: int = 15, seed: int = 0):
    """Copy of `tidy` with known data errors, and the list of affected (geo_id, year, error_type)."""
    rng = np.random.default_rng(seed)
    t = tidy.copy()
    tot = t[t["subgroup"] == TOTAL_SUBGROUP]
    keys = tot[["geo_id", "year"]].drop_duplicates()
    keys = keys[keys["year"] > keys["year"].min()].sample(frac=1, random_state=seed).reset_index(drop=True)
    inds = sorted(tot["indicator"].unique())
    truth = []
    for i, (g, y) in enumerate(keys.head(3 * n_each).itertuples(index=False)):
        m = (t["geo_id"] == g) & (t["year"] == y) & (t["subgroup"] == TOTAL_SUBGROUP)
        kind = ["births_drop", "one_rate_spike", "category_collapse"][i // n_each]
        if kind == "births_drop":          # late or partial file: about half the births missing
            t.loc[m, ["numerator", "denominator"]] = (t.loc[m, ["numerator", "denominator"]] * 0.5).round()
        else:
            ind = inds[int(rng.integers(len(inds)))]
            mi = m & (t["indicator"] == ind)
            factor = 2.5 if kind == "one_rate_spike" else 0.15  # mis-coded category
            t.loc[mi, "numerator"] = (t.loc[mi, "numerator"] * factor).round().clip(upper=t.loc[mi, "denominator"])
        truth.append({"geo_id": g, "year": int(y), "error_type": kind})
    return t, pd.DataFrame(truth)


def validate_on_synthetic(seed: int = 7, contamination: float = 0.02) -> pd.DataFrame:
    """Recall of the anomaly model vs the 30%-births-jump rule on injected errors, plus false-flag rates."""
    from . import synthetic
    from .monitor import data_quality

    tidy, _ = synthetic.generate(seed=seed)
    bad, truth = inject_errors(tidy, seed=seed)
    found = record_anomalies(bad, contamination=contamination)
    hit = set(zip(found["geo_id"], found["year"]))
    rule = set()
    for y in sorted(bad["year"].unique())[1:]:
        dq = data_quality(bad, int(y))
        rule |= {(g, int(y)) for g in dq.loc[dq["issue"] == "denominator jump", "geo_id"]}
    rows = []
    for kind, g in truth.groupby("error_type"):
        k = list(zip(g["geo_id"], g["year"]))
        rows.append({"error_type": kind, "injected": len(k),
                     "found_by_model_pct": 100 * np.mean([x in hit for x in k]),
                     "found_by_rule_pct": 100 * np.mean([x in rule for x in k]),
                     "found_by_either_pct": 100 * np.mean([x in rule or x in hit for x in k])})
    allk = set(zip(truth["geo_id"], truth["year"]))
    # Rule hits the year after a drop too (births recover); count both years as "related" for fairness.
    related = allk | {(g, y + 1) for g, y in allk}
    n_clean = bad[bad["subgroup"] == TOTAL_SUBGROUP][["geo_id", "year"]].drop_duplicates().shape[0] - len(related)
    rows.append({"error_type": "false flags on clean records (%)", "injected": n_clean,
                 "found_by_model_pct": 100 * len(hit - related) / n_clean,
                 "found_by_rule_pct": 100 * len(rule - related) / n_clean,
                 "found_by_either_pct": 100 * len((rule | hit) - related) / n_clean})
    return pd.DataFrame(rows).round(1)
