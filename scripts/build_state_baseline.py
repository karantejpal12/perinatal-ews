"""Turn monthly final state counts into January-to-month windows for the monthly update.

    python scripts/build_state_baseline.py --monthly data/baseline/final_state_months_2016_2022.csv \
        --out data/baseline/final_state_ytd_2016_2022.csv

A window (January to month m) is the sum of its months; if any month in it is suppressed or
missing, the window is left missing rather than under-counted. Windows can be filled from counts
requested directly for that window (--direct), where CDC WONDER does not need to suppress them.
"""
from __future__ import annotations

import argparse

import pandas as pd


def build(monthly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, g in monthly.groupby(["state_fips", "geo_name", "year", "indicator"]):
        g = g.set_index("month").reindex(range(1, 13))
        for m in range(1, 13):
            w = g.loc[1:m]
            ok_n, ok_d = w["numerator"].notna().all(), w["denominator"].notna().all()
            rows.append(dict(zip(["state_fips", "geo_name", "year", "indicator"], key), subgroup="All", through_month=m,
                             numerator=w["numerator"].sum() if ok_n else None,
                             denominator=w["denominator"].sum() if ok_d else None))
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--monthly", default="data/baseline/final_state_months_2016_2022.csv")
    ap.add_argument("--out", default="data/baseline/final_state_ytd_2016_2022.csv")
    ap.add_argument("--direct", nargs="*", default=["data/baseline/final_state_ytd_direct_late_pnc_2016_2022.csv"],
                    help="files with state_fips, year, through_month, indicator, numerator requested directly")
    a = ap.parse_args()
    m = pd.read_csv(a.monthly, dtype={"state_fips": str})
    out = build(m)
    for f in a.direct:
        d = pd.read_csv(f, dtype={"state_fips": str}).dropna(subset=["numerator"])
        key = ["state_fips", "year", "indicator", "through_month"]
        merged = out.merge(d[key + ["numerator"]], on=key, how="left", suffixes=("", "_direct"))
        both = merged["numerator"].notna() & merged["numerator_direct"].notna()
        if both.any() and not (merged.loc[both, "numerator"] == merged.loc[both, "numerator_direct"]).all():
            raise SystemExit(f"{f}: direct counts disagree with summed monthly counts")
        out["numerator"] = merged["numerator"].fillna(merged["numerator_direct"]).to_numpy()
    out.to_csv(a.out, index=False)
    print(f"wrote {a.out}: {len(out)} rows; windows missing a month: {int(out['numerator'].isna().sum())}")


if __name__ == "__main__":
    main()
