"""Every number in the JAMA draft, computed from the published results and the CDC WONDER extract."""
import json
import numpy as np
import pandas as pd
from perinatal_ews import synthetic
from perinatal_ews.config import load_config, core_indicators
from perinatal_ews.monitor import evaluate_against_truth

cfg = load_config(); CORE = core_indicators(cfg)
S = {}
tidy = pd.read_csv("out/paper/core_tidy.csv", dtype={"geo_id": str})
S["rows"] = len(tidy); S["counties"] = int(tidy.geo_id.nunique())
allb = tidy[tidy.subgroup == "All"]
births = allb.groupby(["year", "indicator"])["denominator"].sum().groupby("year").max()
S["births_per_year_min"] = int(births.min()); S["births_per_year_max"] = int(births.max())
S["births_total"] = int(births.sum())
S["suppressed_share_rows"] = float(tidy.numerator.isna().mean())
pooled = allb.groupby(["indicator", "year"])[["numerator", "denominator"]].sum()
pooled["rate"] = pooled.numerator / pooled.denominator
S["pooled_rate"] = {k: {int(y): round(float(v), 4) for y, v in g.droplevel(0)["rate"].items()} for k, g in pooled.groupby(level=0)}
pay = tidy[tidy.subgroup.isin(["Medicaid", "Private insurance"])].groupby(["indicator", "subgroup"])[["numerator", "denominator"]].sum()
S["payer_rate_2016_2024"] = {f"{i}|{s}": round(float(r.numerator / r.denominator), 4) for (i, s), r in pay.iterrows()}

det = pd.read_csv("results/2024/detections.csv", dtype={"geo_id": str})
det = det[det.indicator.isin(CORE)]
a = det[det.subgroup == "All"]
S["scored_2024"] = int(a.z.notna().sum())
S["flags_2024"] = {k: {"alert": int((g.level == "alert").sum()), "watch": int((g.level == "watch").sum()),
                       "alerts_sustained_pct": round(float(g[g.level == "alert"].sustained.mean() * 100), 0) if (g.level == "alert").any() else None}
                   for k, g in a.groupby("indicator")}
sub = det[det.subgroup.isin(["Medicaid", "Private insurance"]) & (det.level == "alert")]
S["subgroup_alerts"] = sub.groupby("subgroup").size().to_dict()
tot_flag = set(a[a.level.isin(["alert", "watch"])][["indicator", "geo_id"]].itertuples(index=False, name=None))
S["subgroup_alerts_total_not_flagged"] = int(sum((r.indicator, r.geo_id) not in tot_flag for r in sub.itertuples()))
top = a[a.level == "alert"].sort_values("excess_cases", ascending=False).head(3)
S["largest_excess"] = top[["indicator", "geo_name", "state", "births", "rate", "expected_rate", "excess_cases"]].round(4).to_dict("records")

sp = pd.read_csv("results/2024/state_patterns.csv"); sp = sp[sp.indicator.isin(CORE)]
S["state_patterns"] = sp[["indicator", "state", "counties", "flagged", "state_rate_baseline", "state_rate_current",
                          "national_rate_baseline", "national_rate_current"]].round(4).to_dict("records")
bt = pd.read_csv("results/2024/backtest.csv"); S["backtest"] = bt.round(4).to_dict("records")
pb = pd.read_csv("results/2024/persistent_burden.csv", dtype={"geo_id": str}); pb = pb[pb.indicator.isin(CORE) & (pb.subgroup == "All")]
pers = pb[pb.status == "persistent"]
S["persistent_n"] = int(len(pers))
lv = a.set_index(["indicator", "geo_id"]).level
S["persistent_stable"] = int(sum(lv.get((r.indicator, r.geo_id)) == "stable" for r in pers.itertuples()))
S["persistent_by_indicator"] = pers.groupby("indicator").size().to_dict()

fm = pd.read_csv("results/2024/forecast_metrics.csv"); S["forecast_metrics"] = fm.round(4).to_dict("records")
for f in ("forecast_by_size", "forecast_by_indicator", "forecast_calibration"):
    S[f] = pd.read_csv(f"results/2024/{f}.csv").round(4).to_dict("records")
S["recalibration"] = json.load(open("out/paper/recalibration.json"))
hs = pd.read_csv("out/paper/heldout_summary.csv"); S["heldout_summary"] = hs.round(4).to_dict("records")

# 20 synthetic replicates
rows = []
for seed in range(1, 21):
    t, truth = synthetic.generate(seed=seed)
    ev = evaluate_against_truth(t, cfg, truth)
    tr = ev.get("cases")
    s = ev["summary"].iloc[0].to_dict(); s["seed"] = seed
    rows.append(s)
    if tr is not None:
        tr = tr.copy(); tr["seed"] = seed; rows[-1]["_truth"] = tr
summ = pd.DataFrame([{k: v for k, v in r.items() if k != "_truth"} for r in rows])
S["synthetic_summary_columns"] = list(summ.columns)
S["synthetic_totals"] = summ.drop(columns="seed").sum(numeric_only=True).to_dict()
truths = [r["_truth"] for r in rows if "_truth" in r]
if truths:
    T = pd.concat(truths)
    S["synthetic_truth_columns"] = list(T.columns)
    S["synthetic_by_size"] = T.groupby("size_class").agg(n=("detected_any", "size"), any=("detected_any", "mean"), alert=("detected_alert", "mean")).round(4).reset_index().to_dict("records")
    S["synthetic_found_any"] = float(T.detected_any.mean()); S["synthetic_found_alert"] = float(T.detected_alert.mean()); S["synthetic_injected"] = int(len(T))
json.dump(S, open("out/paper/paper_stats.json", "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
print(json.dumps({k: S[k] for k in ["births_per_year_min", "births_per_year_max", "scored_2024", "flags_2024", "subgroup_alerts",
      "subgroup_alerts_total_not_flagged", "persistent_n", "persistent_stable", "synthetic_totals"]}, indent=1, default=str))
print(S.get("synthetic_by_size"), S.get("synthetic_found_any"), S.get("synthetic_found_alert"), S.get("synthetic_truth_columns"))
