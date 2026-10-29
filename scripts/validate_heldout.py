"""Held-out validation of detection on county data (see src/perinatal_ews/holdout.py).

    python scripts/validate_heldout.py --tidy data/raw/cdc_wonder_natality_county_2016_2024_tidy.csv \
        --out results/validation

Writes heldout_predictions.csv (one row per county, indicator and target year) and
heldout_summary.csv (coverage of 80/90/95% predictive intervals, upper-tail
exceedances, and prediction error against simpler predictors, overall and by
indicator, year and county size).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from perinatal_ews.config import load_config
from perinatal_ews.holdout import heldout_predictions, heldout_summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tidy", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tidy = pd.read_csv(a.tidy, dtype={"geo_id": str})
    p = heldout_predictions(tidy, load_config())
    s = heldout_summary(p)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    p.to_csv(out / "heldout_predictions.csv", index=False)
    s.to_csv(out / "heldout_summary.csv", index=False)
    r = s.query("group == 'all'").iloc[0]
    print(f"{int(r['county_years'])} held-out county-years: 90% interval coverage {r['coverage_90']:.3f}, "
          f"95% {r['coverage_95']:.3f}; outputs in {out}/")


if __name__ == "__main__":
    main()
