"""Paper analysis: recalibrate detection's variance from held-out years (not published to the site).

Learns a variance inflation factor per indicator from 2020-2023 held-out z-scores (robust SD squared),
checks 2024 held-out coverage before and after, and rescores the published 2024 county results
(All births) with z / sqrt(factor), using the same alert and watch rules as perinatal_ews.detect.
"""
import json
import numpy as np
import pandas as pd
from scipy import stats
from perinatal_ews.detect import benjamini_hochberg
from perinatal_ews.config import load_config, core_indicators

cfg = load_config(); det_cfg = cfg["detection"]
core = core_indicators(cfg)
p = pd.read_csv("out/paper/heldout_predictions.csv", dtype={"geo_id": str})
p = p[p["indicator"].isin(core)]

def rsd(z):
    z = z.dropna(); return 1.4826 * np.median(np.abs(z - np.median(z)))

train = p[p["target_year"].between(2020, 2023)] if "target_year" in p else p[p["year"].between(2020, 2023)]
ycol = "target_year" if "target_year" in p else "year"
fac = {k: rsd(g["z"]) ** 2 for k, g in train.groupby("indicator")}
out = {"inflation": fac, "robust_sd_all_years": {k: rsd(g["z"]) for k, g in p.groupby("indicator")},
       "robust_sd_overall": rsd(p["z"])}

test = p[p[ycol] == 2024].copy()
def cov(z, level):
    c = stats.norm.ppf(0.5 + level / 2); return float((z.abs() <= c).mean())
test["z_recal"] = test["z"] / np.sqrt(test["indicator"].map(fac))
out["coverage_2024"] = {
    "before": {str(l): cov(test["z"].dropna(), l) for l in (0.8, 0.9, 0.95)},
    "after": {str(l): cov(test["z_recal"].dropna(), l) for l in (0.8, 0.9, 0.95)},
    "by_indicator_after_90": {k: cov(g["z_recal"].dropna(), 0.9) for k, g in test.groupby("indicator")},
    "by_indicator_before_90": {k: cov(g["z"].dropna(), 0.9) for k, g in test.groupby("indicator")},
}

d = pd.read_csv("results/2024/detections.csv", dtype={"geo_id": str})
d = d[d["indicator"].isin(core)]
rows = []
for (ind, sub), g in d.groupby(["indicator", "subgroup"]):
    g = g.copy()
    zc = g["z"] / np.sqrt(fac[ind])
    pv = stats.norm.sf(zc); q = benjamini_hochberg(pv)
    rel = g["observed"] >= det_cfg["min_numerator_reliable"]; shown = g["observed"] >= det_cfg["min_numerator_shown"]
    lvl = np.full(len(g), "stable", dtype=object)
    watch = (zc >= det_cfg["watch_z"]) & (g["relative_risk"] >= det_cfg["min_relative_risk_watch"]) & shown
    alert = (q <= det_cfg["alert_q"]) & (g["relative_risk"] >= det_cfg["min_relative_risk_alert"]) & rel
    lvl[watch.to_numpy()] = "watch"; lvl[alert.to_numpy()] = "alert"; lvl[g["z"].isna().to_numpy()] = "insufficient data"
    g["level_recal"] = lvl; rows.append(g)
r = pd.concat(rows)
tab = (r.groupby(["subgroup", "indicator"]).apply(lambda g: pd.Series({
    "scored": int(g["z"].notna().sum()),
    "alert_published": int((g["level"] == "alert").sum()), "watch_published": int((g["level"] == "watch").sum()),
    "alert_recal": int((g["level_recal"] == "alert").sum()), "watch_recal": int((g["level_recal"] == "watch").sum())}), include_groups=False)
    .reset_index())
tab.to_csv("out/paper/recalibrated_2024.csv", index=False)
allb = tab[tab["subgroup"] == "All"]
out["counts_2024_all_births"] = allb.drop(columns="subgroup").set_index("indicator").to_dict("index")
out["totals_2024_all_births"] = allb[["scored", "alert_published", "watch_published", "alert_recal", "watch_recal"]].sum().astype(int).to_dict()
# Of recalibrated alerts, how many were published alerts
a = r[r["subgroup"] == "All"]
out["recal_alerts_that_were_published_alerts"] = int(((a["level_recal"] == "alert") & (a["level"] == "alert")).sum())
json.dump(out, open("out/paper/recalibration.json", "w"), indent=1, default=float)
print(json.dumps(out, indent=1, default=float))
