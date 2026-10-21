"""Monthly update: turn a CDC provisional download into the site's "latest" results.

    python scripts/update_latest.py --provisional data/latest/wonder_provisional_state_2026-08.csv \
        --months data/latest/wonder_provisional_months_2026-08.json

Inputs come from scripts/fetch_wonder_latest.js (run in a browser on the CDC WONDER
provisional natality request form). The fixed file of final state counts,
data/baseline/final_state_ytd_2016_2022.csv, comes from
scripts/fetch_wonder_state_baseline.js and only needs to be made once.

Writes results/latest/ (used by the explorer) and a dated copy in
results/history/<YYYY-MM>/ so every monthly update stays on record.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

from perinatal_ews.config import load_config
from perinatal_ews.latest import build_tidy, choose_months, explorer_payload, run_latest
from perinatal_ews.outlook import outlook_with_backtest, score_archived


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provisional", required=True, help="CSV from fetch_wonder_latest.js")
    ap.add_argument("--months", required=True, help="JSON from fetch_wonder_latest.js (monthly births, fetch date)")
    ap.add_argument("--baseline", default="data/baseline/final_state_ytd_2016_2022.csv")
    ap.add_argument("--out", default="results/latest")
    ap.add_argument("--history", default="results/history")
    ap.add_argument("--draws", type=int, default=300, help="simulations for the full-year outlook")
    ap.add_argument("--backtest-draws", type=int, default=150)
    a = ap.parse_args()

    info = json.loads(Path(a.months).read_text())
    meta = choose_months(pd.DataFrame(info["monthly_births"]))
    if int(info.get("ytd_through_month_fetched", meta["ytd_through_month"])) != meta["ytd_through_month"]:
        raise SystemExit(f"The download covers January-month {info.get('ytd_through_month_fetched')}, but the "
                         f"completeness check chose month {meta['ytd_through_month']}. Re-run the fetch script.")
    meta |= {"fetched_at": info["fetched_at"], "provisional_years": info["provisional_years"],
             "sources": {"provisional": "CDC WONDER, Natality 2023 through last month (provisional), database D192",
                         "final": "CDC WONDER, Natality 2016-2024 expanded (final), database D149"}}
    prov = pd.read_csv(a.provisional, dtype={"state_fips": str})
    base = pd.read_csv(a.baseline, dtype={"state_fips": str})
    res = run_latest(prov, base, meta, load_config(), a.out)
    cfg = load_config()
    payload = explorer_payload(res)

    # Full-year outlook for the current year, validated on the five most recent complete years.
    year, m_ = res["meta"]["ytd_year"], res["meta"]["ytd_through_month"]
    ytd = res["ytd_tidy"]
    full, _ = build_tidy(prov, base, m_, "full")
    full = full[full["year"] < year]
    bt_years = sorted(int(y) for y in full["year"].unique())[-5:]
    # With data through December nothing remains to project, so there is no backtest to run or show.
    ol, bt = outlook_with_backtest(ytd, full, cfg, year, bt_years, m_, n_draws=a.draws,
                                   backtest_draws=a.backtest_draws)
    ol.to_csv(Path(a.out, "outlook.csv"), index=False)
    bt_path = Path(a.out, "outlook_backtest.json")
    if bt is None:
        bt_path.unlink(missing_ok=True)          # never leave an earlier month's backtest beside this outlook
    else:
        bt_path.write_text(json.dumps(bt, indent=2))
        payload["outlook_backtest"] = bt
    for r in ol.itertuples():
        e = payload["states_data"].setdefault(r.geo_id, {"ind": {}, "race": {}})["ind"].setdefault(r.indicator, {})
        e["outlook"] = {"proj": round(r.projected_rate, 4), "lo": round(r.projected_low80, 4),
                        "hi": round(r.projected_high80, 4), "p_flag": round(r.p_flag, 3), "p_alert": round(r.p_alert, 3)}

    # Score outlooks saved in earlier months once their year is complete.
    scores = []
    fy = res["meta"].get("full_year_provisional")
    if fy and "full" in res:
        for f in sorted(Path(a.history).glob("*/outlook.csv")):
            arch = pd.read_csv(f)
            if len(arch) and int(arch["year"].iloc[0]) == int(fy):
                scores.append({"made_with_data_through": f.parent.name, "year": int(fy),
                               **score_archived(arch, res["full"])})
    if scores:
        Path(a.out, "outlook_track_record.json").write_text(json.dumps(scores, indent=2))
        payload["outlook_track_record"] = scores

    Path(a.out, "latest.json").write_text(json.dumps(payload, separators=(",", ":"), default=str))
    snap = Path(a.history, meta["latest_month_available"])
    snap.mkdir(parents=True, exist_ok=True)
    for f in ("latest_meta.json", "state_detections_ytd.csv", "state_race_ytd.csv", "outlook.csv",
              "outlook_backtest.json"):
        if Path(a.out, f).exists():
            shutil.copy(Path(a.out, f), snap / f)
    m = res["meta"]
    ol_note = ("year complete, outlook is the actual year (no backtest)" if bt is None else
               f"backtest AUROC {bt['outlook'].get('auroc')}, 80% interval coverage {bt['interval80_coverage']}")
    print(f"Latest data: {m['ytd_label']} (provisional; latest month available {m['latest_month_available']}, "
          f"{'left out as incomplete' if m['excluded_latest_month'] else 'included'}). "
          f"{m['states']} states: {m['counts']['alerts']} alerts, {m['counts']['watch']} watch. "
          f"Full-year provisional: {m['full_year_provisional']}. Outlook: {ol_note}. Outputs in {a.out}/ and {snap}/")


if __name__ == "__main__":
    main()
