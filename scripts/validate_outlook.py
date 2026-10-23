"""Re-run the full-year outlook backtest from the files in this repository.

    python scripts/validate_outlook.py --provisional data/latest/wonder_provisional_state_2026-08.csv \
        --months data/latest/wonder_provisional_months_2026-08.json --out validation/outlook

Runs the backtest twice on the same inputs as the monthly update:

- "leave one year out" (the method behind the published results): error variances for year t
  come from the other backtest years, including years after t;
- "forward only": error variances for year t come only from years before t, so nothing from the
  future is used.

Each summary adds AUROC by year and indicator, calibration in bins of predicted probability, and a
bootstrap over states of the AUROC gain over the simple baseline. Writes
outlook_backtest_<method>.json and the per-state rows (outlook_backtest_<method>.csv) to --out.
Results do not depend on anything outside the repository's data/ folder.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from perinatal_ews.config import load_config
from perinatal_ews.latest import build_tidy, choose_months, run_latest
from perinatal_ews.outlook import backtest

CAL_BINS = [-0.01, 0.05, 0.2, 0.5, 0.8, 1.0]


def breakdown(rows: pd.DataFrame, n_boot: int = 1000, seed: int = 1) -> dict:
    """AUROC by year and indicator, calibration, and a state-clustered bootstrap of the AUROC gain over the
    simple baseline (ranking by the year-so-far z-score)."""
    d = rows.assign(y=rows["actual_level"].isin(["alert", "watch"]).astype(int),
                    z=rows["ytd_z"].fillna(rows["ytd_z"].min() - 1))

    def auc(g, col):
        return round(float(roc_auc_score(g["y"], g[col])), 3) if g["y"].nunique() == 2 else None

    by = {}
    for col in ("year", "indicator"):
        by[col] = [{col: (int(k) if col == "year" else k), "n": len(g), "flags": int(g["y"].sum()),
                    "auroc_outlook": auc(g, "p_flag"), "auroc_year_so_far_z": auc(g, "z")}
                   for k, g in d.groupby(col)]
    cal = d.assign(bin=pd.cut(d["p_flag"], CAL_BINS)).groupby("bin", observed=True).agg(
        n=("y", "size"), mean_predicted=("p_flag", "mean"), observed=("y", "mean")).reset_index()
    cal["bin"] = cal["bin"].astype(str)
    rng = np.random.default_rng(seed)
    groups = {k: g for k, g in d.groupby("geo_id")}
    states = list(groups)
    gain, base = [], []
    for _ in range(n_boot):
        b = pd.concat([groups[s] for s in rng.choice(states, len(states))])
        a, z = roc_auc_score(b["y"], b["p_flag"]), roc_auc_score(b["y"], b["z"])
        base.append(a)
        gain.append(a - z)
    return {"by_year": by["year"], "by_indicator": by["indicator"],
            "calibration": cal.round(3).to_dict("records"),
            "bootstrap": {"resamples": n_boot, "unit": "state",
                          "auroc_outlook_95ci": [round(float(x), 3) for x in np.percentile(base, [2.5, 97.5])],
                          "auroc_gain_over_year_so_far_z": round(float(np.mean(gain)), 3),
                          "auroc_gain_95ci": [round(float(x), 3) for x in np.percentile(gain, [2.5, 97.5])]}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provisional", required=True)
    ap.add_argument("--months", required=True)
    ap.add_argument("--baseline", default="data/baseline/final_state_ytd_2016_2022.csv")
    ap.add_argument("--out", default="validation/outlook")
    ap.add_argument("--draws", type=int, default=150, help="simulations per backtest year (monthly update: 150)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--method", choices=["both", "leave_one_year_out", "forward_only"], default="both")
    a = ap.parse_args()

    info = json.loads(Path(a.months).read_text())
    meta = choose_months(pd.DataFrame(info["monthly_births"]))
    meta |= {"fetched_at": info["fetched_at"], "provisional_years": info["provisional_years"]}
    prov = pd.read_csv(a.provisional, dtype={"state_fips": str})
    base = pd.read_csv(a.baseline, dtype={"state_fips": str})
    cfg = load_config()
    with tempfile.TemporaryDirectory() as tmp:          # run_latest writes files; keep them out of results/
        res = run_latest(prov, base, meta, cfg, tmp)
    year, m = res["meta"]["ytd_year"], res["meta"]["ytd_through_month"]
    full, _ = build_tidy(prov, base, m, "full")
    full = full[full["year"] < year]
    years = sorted(int(y) for y in full["year"].unique())[-5:]

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, fwd in (("leave_one_year_out", False), ("forward_only", True)):
        if a.method not in ("both", name):
            continue
        rows, summary = backtest(res["ytd_tidy"], full, cfg, years, n_draws=a.draws, seed=a.seed, forward_only=fwd)
        summary |= breakdown(rows)
        summary |= {"months_known": int(m), "draws": a.draws, "seed": a.seed,
                    "data": {"provisional": Path(a.provisional).name, "baseline": Path(a.baseline).name}}
        (out / f"outlook_backtest_{name}.json").write_text(json.dumps(summary, indent=2, default=float))
        rows.to_csv(out / f"outlook_backtest_{name}.csv", index=False)
        o = summary["outlook"]
        print(f"{name}: AUROC {o['auroc']}, AUPRC {o['auprc']}, Brier {o['brier']}, "
              f"80% coverage {summary['interval80_coverage']}; year-so-far z AUROC "
              f"{summary.get('year_so_far_z_score', {}).get('auroc')}")


if __name__ == "__main__":
    main()
