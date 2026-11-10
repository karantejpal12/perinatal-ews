"""Map outlines against their JSON Schema (docs/map.schema.json): the published files and the files the build writes."""
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from perinatal_ews.latest import FIPS_TO_ABBR

jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "docs" / "map.schema.json").read_text())
MAP = ROOT / "results" / "map"
EXPLORER = ROOT / "results" / "2024" / "explorer.json"
FILES = ("states", "counties", "counties_other")


def _errors(doc, which):
    schema = {k: v for k, v in SCHEMA.items() if k != "anyOf"} | {"$ref": f"#/$defs/{which}"}
    v = jsonschema.Draft202012Validator(schema)
    return sorted(f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in v.iter_errors(doc))


def _signed_area(ring):
    """Shoelace area in degrees: negative for a clockwise ring (longitude east, latitude north)."""
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:])) / 2


def _polygons(geom):
    return [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]


def _consistency(maps, scored):
    """Rules the schema cannot express: what d3-geo and the explorer's map assume."""
    ids = {}
    for which, fc in maps.items():
        ids[which] = [f["id"] for f in fc["features"]]
        assert len(ids[which]) == len(set(ids[which])), f"{which}: an area appears twice"
        for f in fc["features"]:
            for poly in _polygons(f["geometry"]):
                for i, ring in enumerate(poly):
                    assert ring[0] == ring[-1], f"{which} {f['id']}: ring not closed"
                    a = _signed_area(ring)
                    # d3-geo reads an anticlockwise exterior as everything outside it, which fills the whole map;
                    # a few slivers collapse to zero area when coordinates are rounded and draw nothing
                    assert (a <= 0) if i == 0 else (a >= 0), f"{which} {f['id']}: ring {i} wound the wrong way"
    states = set(ids["states"])
    assert states <= set(FIPS_TO_ABBR), "a state outline that is not a US state or DC"
    assert set(ids["counties"]) == set(scored), (
        f"scored counties without a shape: {sorted(set(scored) - set(ids['counties']))}; "
        f"shapes for unscored counties: {sorted(set(ids['counties']) - set(scored))}")
    if "counties_other" in maps:
        assert not set(ids["counties_other"]) & set(ids["counties"]), "a scored county is also drawn as an other county"
    for which in ("counties", "counties_other"):
        assert all(i[:2] in states for i in ids.get(which, [])), f"{which}: a county outside every state outline"


def _bad_names(fc):
    """Other-county names that are not "Name, ST" with the state matching the FIPS code (or the bare code)."""
    bad = []
    for f in fc["features"]:
        n = f["properties"]["n"]
        m = re.fullmatch(r"(.+), ([A-Z]{2})", n)
        if n != f["id"] and not (m and m.group(1) != "nan" and m.group(2) == FIPS_TO_ABBR.get(f["id"][:2])):
            bad.append((f["id"], n))
    return bad


@pytest.fixture(scope="module")
def published():
    if not all((MAP / f"{w}.json").exists() for w in FILES) or not EXPLORER.exists():
        pytest.skip("map files not built")
    maps = {w: json.loads((MAP / f"{w}.json").read_text()) for w in FILES}
    return maps, [c["id"] for c in json.loads(EXPLORER.read_text())["counties"]]


def test_schema_is_valid():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("which", FILES)
def test_published_map_file_matches_schema(published, which):
    assert _errors(published[0][which], which) == []


def test_published_map_files_are_consistent(published):
    """Every scored county has exactly one shape, and every ring is closed and wound as d3-geo expects."""
    _consistency(*published)


@pytest.mark.xfail(strict=True, reason="counties_other.json was built before the name fix in build_map_geometry.py; "
                                       "about 150 counties (mostly Kentucky and Pennsylvania) read 'nan, nan' until "
                                       "it is rebuilt (see the roadmap). Remove this mark after the rebuild.")
def test_published_other_county_names(published):
    assert _bad_names(published[0]["counties_other"]) == []


@pytest.mark.parametrize("which, break_it, where", [
    ("states", lambda d: d["features"][0].update(id="1"), "features/0/id"),
    ("counties", lambda d: d["features"][0]["properties"].update(name="x"), "features/0/properties"),
    ("counties", lambda d: d["features"][0]["geometry"].update(type="Point"), "features/0/geometry"),
    ("counties_other", lambda d: d["features"][0]["properties"].update(od=-1.0), "features/0/properties/od"),
    ("counties_other", lambda d: d["features"][0]["properties"].pop("n"), "features/0/properties"),
])
def test_schema_rejects_broken_files(published, which, break_it, where):
    d = copy.deepcopy(published[0][which])
    break_it(d)
    assert any(e.startswith(where) for e in _errors(d, which)), _errors(d, which)


def _first_ring(d, which):
    return _polygons(d[which]["features"][0]["geometry"])[0][0]


@pytest.mark.parametrize("break_it", [
    lambda d, s: _first_ring(d, "counties").pop(),                       # ring not closed
    lambda d, s: _first_ring(d, "counties").reverse(),                   # exterior anticlockwise
    lambda d, s: d["counties"]["features"].pop(),                        # a scored county loses its shape
    lambda d, s: d["counties_other"]["features"].append(copy.deepcopy(d["counties"]["features"][0])),
    lambda d, s: d["states"]["features"].pop(0),                         # counties outside every state
])
def test_consistency_check_catches_broken_files(published, break_it):
    maps, scored = copy.deepcopy(published[0]), published[1]
    break_it(maps, scored)
    with pytest.raises(AssertionError):
        _consistency(maps, scored)


def _square(x, y, clockwise):
    ring = [[x, y], [x, y + 1], [x + 1, y + 1], [x + 1, y], [x, y]]   # clockwise
    return {"type": "Polygon", "coordinates": [ring if clockwise else ring[::-1]]}


def test_files_written_by_the_build_match_schema(tmp_path):
    """scripts/build_map_geometry.py on a synthetic outline file: names, Puerto Rico, winding and suppressed rates."""
    pytest.importorskip("shapely")
    feats = [  # (id, NAME, x, y, clockwise)
        ("01001", "Alpha", -87, 32, False), ("01003", "Beta", -88, 31, False), ("01005", "Gamma", -86, 31, True),
        ("02013", "Delta", -160, 55, False), ("02016", None, -170, 52, True), ("72001", "Adjuntas", -66.8, 18.1, True),
    ]
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": i, "properties": ({"NAME": n} if n else {}), "geometry": _square(x, y, cw)}
        for i, n, x, y, cw in feats]}
    (tmp_path / "us.geojson").write_text(json.dumps(gj))
    (tmp_path / "tidy.csv").write_text("geo_id,year\n01001,2024\n")
    # 01003 has a context row with no name (as some Kentucky and Pennsylvania counties do); 02013 has none at all
    (tmp_path / "context.csv").write_text("geo_id,state,name,overdose_rate_2024\n"
                                          "01003,,,\n01005,AL,Gamma,41.26\n02016,AK,Epsilon,\n")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_map_geometry.py"), "--tidy", str(tmp_path / "tidy.csv"),
                    "--geojson", str(tmp_path / "us.geojson"), "--context", str(tmp_path / "context.csv"),
                    "--out", str(tmp_path / "map")], check=True, capture_output=True)
    maps = {w: json.loads((tmp_path / "map" / f"{w}.json").read_text()) for w in FILES}
    for w in FILES:
        assert _errors(maps[w], w) == []
    _consistency(maps, ["01001"])
    assert [f["id"] for f in maps["states"]["features"]] == ["01", "02"]   # no Puerto Rico
    other = {f["id"]: f["properties"] for f in maps["counties_other"]["features"]}
    assert other == {"01003": {"n": "Beta, AL", "od": None}, "01005": {"n": "Gamma, AL", "od": 41.3},
                     "02013": {"n": "Delta, AK", "od": None}, "02016": {"n": "Epsilon, AK", "od": None}}
    assert _bad_names(maps["counties_other"]) == []
