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
from perinatal_ews.latest import choose_months, explorer_payload, run_latest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provisional", required=True, help="CSV from fetch_wonder_latest.js")
    ap.add_argument("--months", required=True, help="JSON from fetch_wonder_latest.js (monthly births, fetch date)")
    ap.add_argument("--baseline", default="data/baseline/final_state_ytd_2016_2022.csv")
    ap.add_argument("--out", default="results/latest")
    ap.add_argument("--history", default="results/history")
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
    payload = explorer_payload(res)
    Path(a.out, "latest.json").write_text(json.dumps(payload, separators=(",", ":"), default=str))
    snap = Path(a.history, meta["latest_month_available"])
    snap.mkdir(parents=True, exist_ok=True)
    for f in ("latest_meta.json", "state_detections_ytd.csv", "state_race_ytd.csv"):
        shutil.copy(Path(a.out, f), snap / f)
    m = res["meta"]
    print(f"Latest data: {m['ytd_label']} (provisional; latest month available {m['latest_month_available']}, "
          f"{'left out as incomplete' if m['excluded_latest_month'] else 'included'}). "
          f"{m['states']} states: {m['counts']['alerts']} alerts, {m['counts']['watch']} watch. "
          f"Full-year provisional: {m['full_year_provisional']}. Outputs in {a.out}/ and {snap}/")


if __name__ == "__main__":
    main()
