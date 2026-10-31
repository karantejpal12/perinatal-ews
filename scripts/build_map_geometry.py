"""Build compact map outlines for the explorer.

    python scripts/build_map_geometry.py --tidy data/raw/cdc_wonder_natality_county_2016_2024_tidy.csv \
        --geojson data/context/us_counties.geojson --out results/map

Writes counties.json (only the scored counties), states.json (state outlines,
dissolved from all counties) and, with --context, counties_other.json (every other
county, with its name and 2024 drug overdose death rate, used only by the explorer's
overdose map), simplified and with coordinates rounded to keep the files small. Needs shapely. County outlines: US Census cartographic boundary
counties via https://github.com/plotly/datasets (geojson-counties-fips.json).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.polygon import orient
from shapely.ops import unary_union


def _round(geom, nd=3):
    def r(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], nd), round(c[1], nd)]
        return [r(x) for x in c]
    g = mapping(geom)
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def _clockwise(geom):
    """Exterior rings clockwise, as d3-geo expects; a ring wound the other way draws as the whole globe."""
    if isinstance(geom, Polygon):
        return orient(geom, sign=-1.0)
    if isinstance(geom, MultiPolygon):
        return MultiPolygon([orient(g, sign=-1.0) for g in geom.geoms if not g.is_empty])
    return geom


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tidy", required=True)
    ap.add_argument("--geojson", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--context", default=None, help="data/context/county_context.csv: adds counties_other.json")
    a = ap.parse_args()
    ctx = (pd.read_csv(a.context, dtype={"geo_id": str}).set_index("geo_id") if a.context else None)
    ids = set(pd.read_csv(a.tidy, dtype={"geo_id": str}, usecols=["geo_id"])["geo_id"])
    gj = json.loads(Path(a.geojson).read_text(encoding="latin-1"))
    counties, others, by_state = [], [], {}
    for f in gj["features"]:
        g = shape(f["geometry"]).buffer(0)
        by_state.setdefault(f["id"][:2], []).append(g)
        if f["id"] in ids:
            counties.append({"type": "Feature", "id": f["id"], "properties": {},
                             "geometry": _round(g.simplify(0.01, preserve_topology=True))})
        elif ctx is not None and f["id"][:2] != "72":
            row = ctx.loc[f["id"]] if f["id"] in ctx.index else None
            od = row["overdose_rate_2024"] if row is not None else None
            props = {"n": f"{row['name']}, {row['state']}" if row is not None else f["id"],
                     "od": round(float(od), 1) if od is not None and pd.notna(od) else None}
            others.append({"type": "Feature", "id": f["id"], "properties": props,
                           "geometry": _round(_clockwise(g.simplify(0.02, preserve_topology=True)), 3)})
    states = [{"type": "Feature", "id": st, "properties": {},
               "geometry": _round(unary_union(gs).simplify(0.03, preserve_topology=True), 2)}
              for st, gs in sorted(by_state.items()) if st != "72"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "counties.json").write_text(json.dumps({"type": "FeatureCollection", "features": counties}, separators=(",", ":")))
    (out / "states.json").write_text(json.dumps({"type": "FeatureCollection", "features": states}, separators=(",", ":")))
    if ctx is not None:
        (out / "counties_other.json").write_text(json.dumps({"type": "FeatureCollection", "features": others},
                                                            separators=(",", ":")))
        print(f"other counties: {len(others)} ({(out / 'counties_other.json').stat().st_size / 1024:.0f} KB)")
    missing = sorted(ids - {c["id"] for c in counties})
    print(f"counties: {len(counties)} ({(out / 'counties.json').stat().st_size / 1024:.0f} KB); "
          f"states: {len(states)} ({(out / 'states.json').stat().st_size / 1024:.0f} KB); missing: {missing}")


if __name__ == "__main__":
    main()
