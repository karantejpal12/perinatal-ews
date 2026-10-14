"""Build the compact JSON used by the interactive web app (app.html).

    python scripts/build_explorer_data.py --tidy data/raw/cdc_wonder_natality_county_2016_2024_tidy.csv \
        --results results/2024 --out results/2024/explorer.json

Only rates whose numerator is 10 or more are included, so no count or rate based
on 9 or fewer events is published (NCHS data use restrictions).
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd


def _r(x, nd=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) or pd.isna(x) else round(float(x), nd)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tidy", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--context", default=None, help="data/context/county_context.csv")
    a = ap.parse_args()
    res = Path(a.results)

    tidy = pd.read_csv(a.tidy, dtype={"geo_id": str})
    det = pd.read_csv(res / "detections.csv", dtype={"geo_id": str})
    fc = pd.read_csv(res / "forecast_scores.csv", dtype={"geo_id": str}) if (res / "forecast_scores.csv").exists() else None
    states = pd.read_csv(res / "state_patterns.csv") if (res / "state_patterns.csv").exists() else pd.DataFrame()
    bench = (pd.read_csv(res / "context_benchmark.csv", dtype={"geo_id": str}).set_index(["geo_id", "indicator"])
             if (res / "context_benchmark.csv").exists() else None)
    na = (pd.read_csv(res / "need_access.csv", dtype={"geo_id": str}).set_index("geo_id")
          if (res / "need_access.csv").exists() else None)
    ctx = (pd.read_csv(a.context, dtype={"geo_id": str}).set_index("geo_id") if a.context else None)
    year = int(det["year"].max())
    years = sorted(int(y) for y in tidy["year"].unique())

    t = tidy[(tidy["subgroup"] == "All") & (tidy["numerator"] >= 10)].copy()
    t["rate"] = t["numerator"] / t["denominator"]
    rates = {(r.geo_id, r.indicator, int(r.year)): r.rate for r in t.itertuples()}

    counties = (tidy[["geo_id", "geo_name", "state"]].drop_duplicates("geo_id").sort_values(["state", "geo_name"]))
    indicators = ["late_no_prenatal_care", "preterm_birth", "low_birth_weight", "gestational_hypertension"]
    tot = det[det["subgroup"] == "All"].set_index(["geo_id", "indicator"])
    sub = det[det["subgroup"] != "All"].set_index(["geo_id", "indicator", "subgroup"])
    risk = fc.set_index(["geo_id", "indicator"])["risk"] if fc is not None else None
    factors = (fc.set_index(["geo_id", "indicator"])["top_factors"]
               if fc is not None and "top_factors" in fc.columns else None)
    CTX_FIELDS = {
        "overdose_rate_2024": "Drug overdose deaths per 100,000 (2024)",
        "preg_moud_medicaid_facilities": "Opioid treatment facilities for pregnant/postpartum patients taking Medicaid",
        "moud_facilities": "Facilities offering medications for opioid use disorder",
        "ld_hospitals": "Hospitals with labour and delivery care",
        "bphigh": "Adults with high blood pressure (%)",
        "obesity": "Adults with obesity (%)",
        "access2": "Uninsured adults 18-64 (%)",
        "acs_pov150": "Residents below 150% of poverty (%)",
    }
    ctx_ids = set(counties["geo_id"])
    ctx_median = ({k: _r(ctx.loc[ctx.index.isin(ctx_ids), k].median(), 2) for k in CTX_FIELDS if k in ctx.columns}
                  if ctx is not None else {})

    out_c = []
    for c in counties.itertuples():
        ind = {}
        for k in indicators:
            if (c.geo_id, k) not in tot.index:
                continue
            d = tot.loc[(c.geo_id, k)]
            entry = {
                "trend": [_r(rates.get((c.geo_id, k, y))) for y in years],
                "level": d["level"],
                "rate": _r(d["rate"]) if d["observed"] >= 10 else None,
                "expected": _r(d["expected_rate"]),
                "rr": _r(d["relative_risk"], 3) if d["observed"] >= 10 else None,
                "births": None if pd.isna(d["births"]) else int(d["births"]),
                "sustained": bool(d["sustained"]),
                "excess": None if pd.isna(d["excess_cases"]) or d["observed"] < 10 else int(round(d["excess_cases"])),
            }
            subs = {}
            for s in ("Medicaid", "Private insurance"):
                if (c.geo_id, k, s) in sub.index:
                    sd = sub.loc[(c.geo_id, k, s)]
                    ok = sd["observed"] >= 10
                    subs[s] = {"level": sd["level"], "rate": _r(sd["rate"]) if ok else None,
                               "expected": _r(sd["expected_rate"])}
            entry["subgroups"] = subs
            if risk is not None and (c.geo_id, k) in risk.index:
                entry["risk"] = _r(risk.loc[(c.geo_id, k)], 3)
                f = factors.loc[(c.geo_id, k)] if factors is not None else None
                if isinstance(f, str) and f:
                    entry["factors"] = f
            if bench is not None and (c.geo_id, k) in bench.index:
                b = bench.loc[(c.geo_id, k)]
                entry["similar"] = {"rate": _r(b["observed_rate"]), "expected": _r(b["context_expected_rate"]),
                                    "verdict": b["compared_with_similar"], "years": None}
            ind[k] = entry
        rec = {"id": c.geo_id, "name": c.geo_name, "state": c.state, "ind": ind}
        if ctx is not None and c.geo_id in ctx.index:
            row = ctx.loc[c.geo_id]
            rec["ctx"] = {k: (_r(row[k], 1) if pd.notna(row[k]) else None) for k in CTX_FIELDS if k in ctx.columns}
            births = max((e.get("births") or 0) for e in ind.values()) if ind else 0
            rec["births"] = births or None
        if na is not None and c.geo_id in na.index:
            n = na.loc[c.geo_id]
            rec["need"] = {"priority": n["priority"], "reasons": n["context_reasons"]}
        out_c.append(rec)

    payload = {
        "year": year,
        "forecast_year": year + 1,
        "years": years,
        "indicators": {
            "late_no_prenatal_care": "Late or no prenatal care",
            "preterm_birth": "Preterm birth",
            "low_birth_weight": "Low birth weight",
            "gestational_hypertension": "Gestational hypertension",
        },
        "source": "CDC WONDER Natality, 2016-2024 expanded (NCHS). Rates based on fewer than 10 events are not shown.",
        "state_patterns": [
            {"indicator": r.indicator, "state": r.state, "flagged": int(r.flagged), "counties": int(r.counties),
             "rate_before": _r(r.state_rate_baseline), "rate_now": _r(r.state_rate_current)}
            for r in states.itertuples()
        ],
        "counties": out_c,
        "context_fields": CTX_FIELDS if ctx is not None else {},
        "context_median": ctx_median,
        "context_source": ("County context: CDC PLACES 2025 (BRFSS 2023) and ACS 2017-2021 measures; CDC VSRR provisional "
                           "drug overdose deaths; SAMHSA FindTreatment.gov facility listings (Oct 2026); CMS Maternal "
                           "Health - Hospital (Maternal Morbidity Structural Measure)."),
    }
    if bench is not None and (res / "context_benchmark_quality.csv").exists():
        payload["benchmark_years"] = str(pd.read_csv(res / "context_benchmark_quality.csv")["years_pooled"].iloc[0])
    Path(a.out).write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {a.out}: {len(out_c)} counties, {Path(a.out).stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
