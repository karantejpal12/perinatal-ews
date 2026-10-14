"""Build compact map outlines for the explorer.

    python scripts/build_map_geometry.py --tidy data/raw/cdc_wonder_natality_county_2016_2024_tidy.csv \
        --geojson data/context/us_counties.geojson --out results/map

Writes counties.json (only the scored counties) and states.json (state outlines,
dissolved from all counties), simplified and with coordinates rounded to keep
the files small. Needs shapely. County outlines: US Census cartographic boundary
counties via https://github.com/plotly/datasets (geojson-counties-fips.json).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from shapely.geometry import mapping, shape
from shapely.ops import unary_union


def _round(geom, nd=3):
    def r(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], nd), round(c[1], nd)]
        return [r(x) for x in c]
    g = mapping(geom)
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tidy", required=True)
    ap.add_argument("--geojson", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ids = set(pd.read_csv(a.tidy, dtype={"geo_id": str}, usecols=["geo_id"])["geo_id"])
    gj = json.loads(Path(a.geojson).read_text(encoding="latin-1"))
    counties, by_state = [], {}
    for f in gj["features"]:
        g = shape(f["geometry"]).buffer(0)
        by_state.setdefault(f["id"][:2], []).append(g)
        if f["id"] in ids:
            counties.append({"type": "Feature", "id": f["id"], "properties": {},
                             "geometry": _round(g.simplify(0.01, preserve_topology=True))})
    states = [{"type": "Feature", "id": st, "properties": {},
               "geometry": _round(unary_union(gs).simplify(0.03, preserve_topology=True), 2)}
              for st, gs in sorted(by_state.items()) if st != "72"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "counties.json").write_text(json.dumps({"type": "FeatureCollection", "features": counties}, separators=(",", ":")))
    (out / "states.json").write_text(json.dumps({"type": "FeatureCollection", "features": states}, separators=(",", ":")))
    missing = sorted(ids - {c["id"] for c in counties})
    print(f"counties: {len(counties)} ({(out / 'counties.json').stat().st_size / 1024:.0f} KB); "
          f"states: {len(states)} ({(out / 'states.json').stat().st_size / 1024:.0f} KB); missing: {missing}")


if __name__ == "__main__":
    main()
