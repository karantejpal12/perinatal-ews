"""Build the county context table used by perinatal-ews (v0.3).

All inputs are free public files, saved in data/context/ by the fetch steps in
scripts/fetch_county_context.js (run in a browser on each source site):

- CDC PLACES county data (2025 release, BRFSS 2023; 2024 release used where a
  state is missing from 2025): adult health and social-needs prevalence.
- CDC PLACES non-medical factor measures (ACS 2017-2021): poverty, unemployment,
  education, single-parent households, broadband, housing cost, crowding.
- CDC VSRR provisional county drug overdose deaths: 12-month counts ending each
  December, 2020-2024 (counts 1-9 suppressed by NCHS).
- SAMHSA FindTreatment.gov: substance use treatment facilities, with medications
  for opioid use disorder (MOUD), opioid treatment programs and programmes for
  pregnant or postpartum women.
- CMS Maternal Health - Hospital: the Maternal Morbidity Structural Measure,
  which identifies hospitals with inpatient labour and delivery care and those
  designated "Birthing-Friendly".

    python scripts/build_county_context.py --out data/context/county_context.csv

The output has one row per county (5-digit FIPS) and contains only rates,
prevalences and facility counts; no overdose count of 1-9 is reproduced.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

CTX = Path("data/context")
PLACES_MEASURES = ["obesity", "bphigh", "diabetes", "csmoking", "depression", "mhlth", "access2",
                   "lacktrpt", "foodinsecu", "housinsecu", "binge", "checkup"]
ACS_MEASURES = ["POV150", "UNEMP", "NOHSDP", "SNGPNT", "BROAD", "HCOST", "CROWD"]
OD_YEARS = [2020, 2021, 2022, 2023, 2024]


def _norm(s: str) -> str:
    s = str(s).upper().replace("SAINT", "ST").replace("&", "AND")
    s = re.sub(r"\b(COUNTY|PARISH|BOROUGH|CENSUS AREA|MUNICIPALITY|CITY AND BOROUGH)\b", "", s)
    return re.sub(r"[^A-Z]", "", s)


STATE_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC",
    "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT",
    "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY", "72": "PR",
}


def _county_shapes():
    from shapely.geometry import shape
    from shapely.strtree import STRtree

    gj = json.loads((CTX / "us_counties.geojson").read_text(encoding="latin-1"))
    geoms, fips, names = [], [], []
    for f in gj["features"]:
        geoms.append(shape(f["geometry"]))
        fips.append(f["id"])
        names.append((STATE_FIPS.get(f["id"][:2], ""), f["properties"].get("NAME", ""),
                      f["properties"].get("LSAD", "")))
    return geoms, fips, names, STRtree(geoms)


def _points_to_fips(lat, lon, shapes, states=None):
    """Point-in-polygon county lookup. The county outlines are simplified, so a
    point just outside every polygon (usually on a coastline) is assigned to the
    nearest county in the same state, if one is within about 5 km."""
    from shapely.geometry import Point

    geoms, fips, _, tree = shapes
    abbr_to_fips = {v: k for k, v in STATE_FIPS.items()}
    out = []
    states = list(states) if states is not None else [None] * len(lat)
    for la, lo, st in zip(lat, lon, states):
        try:
            p = Point(float(lo), float(la))
        except (TypeError, ValueError):
            out.append(None)
            continue
        hit = None
        for i in tree.query(p):
            if geoms[int(i)].contains(p):
                hit = fips[int(i)]
                break
        if hit is None and st in abbr_to_fips:
            pre = abbr_to_fips[st]
            cands = [(geoms[i].distance(p), fips[i]) for i in range(len(fips)) if fips[i].startswith(pre)]
            if cands:
                d, f = min(cands)
                hit = f if d < 0.05 else None
        out.append(hit)
    return out


def build() -> pd.DataFrame:
    base = pd.read_csv(CTX / "cdc_places_overdose_county.csv", dtype={"fips": str})
    base = base[base["fips"].str.len() == 5].copy()

    # PLACES 2024 release fills states absent from 2025 (for example Pennsylvania, Kentucky).
    long = pd.read_csv(CTX / "places2024_fill_and_acs_factors_long.csv", dtype={"fips": str})
    fill = long[long["source"] == "places2024"].pivot_table(index="fips", columns="measure", values="value")
    fill.columns = [c.lower() for c in fill.columns]
    fill_pop = long[long["source"] == "places2024"].groupby("fips")["pop"].max()
    base = base.set_index("fips")
    for c in PLACES_MEASURES:
        if c in fill.columns:
            base[c] = base[c].fillna(fill[c].reindex(base.index))
    base["pop2023"] = base["pop2023"].fillna(fill_pop.reindex(base.index))
    acs = long[long["source"] == "acs2017_2021"].pivot_table(index="fips", columns="measure", values="value")
    acs.columns = ["acs_" + c.lower() for c in acs.columns]
    base = base.join(acs, how="left")

    # Overdose deaths per 100,000 residents; suppressed counts stay missing.
    pop = base["pop2023"]
    for y in OD_YEARS:
        base[f"overdose_rate_{y}"] = base[f"od_{y}"] / pop * 1e5
    base = base.drop(columns=[f"od_{y}" for y in OD_YEARS])

    shapes = _county_shapes()

    # Substance use treatment capacity.
    fac = pd.read_csv(CTX / "samhsa_findtreatment_su_facilities.csv", dtype={"zip": str})
    fac["fips"] = _points_to_fips(fac["lat"], fac["lon"], shapes, fac["state"])
    # About 9% of listings have no coordinates; use the county most other facilities
    # in the same ZIP code fall in.
    zip_mode = fac.dropna(subset=["fips"]).groupby("zip")["fips"].agg(lambda s: s.mode().iloc[0])
    fac["fips"] = fac["fips"].fillna(fac["zip"].map(zip_mode))
    fac["preg_moud_medicaid"] = (fac["pregnant_postpartum"] & fac["bup_or_methadone"] & fac["medicaid"]).astype(int)
    agg = fac.dropna(subset=["fips"]).groupby("fips").agg(
        su_facilities=("state", "size"), moud_facilities=("moud", "sum"), otp_facilities=("otp", "sum"),
        pregnant_programs=("pregnant_postpartum", "sum"), preg_moud_medicaid_facilities=("preg_moud_medicaid", "sum"))
    base = base.join(agg, how="left")
    for c in agg.columns:
        base[c] = base[c].fillna(0).astype(int)
        base[c + "_per100k"] = base[c] / pop * 1e5

    # Hospitals with labour and delivery care (CMS Maternal Morbidity Structural Measure).
    hosp = pd.read_csv(CTX / "cms_maternal_structural_measure_hospitals.csv", dtype={"zip": str})
    _, fips, names, _ = shapes
    name_map = {}
    for f, (st, nm, lsad) in zip(fips, names):
        if lsad.lower() == "city":
            name_map[(st, _norm(nm) + "CITY")] = f
        name_map.setdefault((st, _norm(nm)), f)
    aliases = {("DC", "THEDISTRICT"): "11001", ("LA", "EBATONROUGE"): "22033", ("LA", "JEFFRSONDAVIS"): "22053",
               ("MN", "LAKEOFWOODS"): "27077", ("MN", "YELLOWMEDCINE"): "27173", ("MO", "STLOUISCITY"): "29510",
               ("AK", "NORTHSLOPEBOROUH"): "02185", ("AK", "NORTHWESTARTICBOROUGH"): "02188"}
    name_map.update(aliases)
    hosp["fips"] = [name_map.get((s, _norm(c))) for s, c in zip(hosp["state"], hosp["county"])]
    hosp["ld"] = hosp["sm7"].isin(["Yes", "No"]).astype(int)
    hosp["birthing_friendly"] = (hosp["sm7"] == "Yes").astype(int)
    hosp["ld_unknown"] = (hosp["sm7"] == "not_available").astype(int)
    h = hosp.dropna(subset=["fips"]).groupby("fips")[["ld", "birthing_friendly", "ld_unknown"]].sum()
    h.columns = ["ld_hospitals", "birthing_friendly_hospitals", "hospitals_ld_status_unknown"]
    base = base.join(h, how="left")
    for c in h.columns:
        base[c] = base[c].fillna(0).astype(int)

    base.index.name = "geo_id"
    keep = (["state", "name", "pop2023"] + PLACES_MEASURES + list(acs.columns)
            + [f"overdose_rate_{y}" for y in OD_YEARS]
            + [c for c in base.columns if c.endswith("_per100k") or c.endswith("_facilities") or c.endswith("_programs")]
            + list(h.columns))
    out = base[list(dict.fromkeys(keep))].round(3).reset_index()
    report = {
        "facilities_geocoded": f"{fac['fips'].notna().mean():.1%}",
        "hospitals_matched": f"{hosp['fips'].notna().mean():.1%}",
        "unmatched_hospital_examples": hosp.loc[hosp["fips"].isna(), ["state", "county"]].drop_duplicates().head(8).values.tolist(),
    }
    print(report)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(CTX / "county_context.csv"))
    a = ap.parse_args()
    out = build()
    out.to_csv(a.out, index=False)
    print(f"wrote {a.out}: {len(out)} counties, {out.shape[1]} columns")


if __name__ == "__main__":
    main()
