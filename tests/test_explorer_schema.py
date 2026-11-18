"""explorer.json against its JSON Schema (docs/explorer.schema.json): the published file and the file the build writes."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "docs" / "explorer.schema.json").read_text())
PUBLISHED = ROOT / "results" / "2024" / "explorer.json"


def _errors(doc, schema=SCHEMA):
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    return sorted(f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in v.iter_errors(doc))


def _consistency(d):
    """Rules the schema cannot express: what the explorer assumes when it draws a county."""
    ids = [c["id"] for c in d["counties"]]
    assert len(ids) == len(set(ids)), "a county appears twice"
    ids = set(ids)
    for c in d["counties"]:
        assert set(c.get("ctx", {})) <= set(d["context_fields"])
        assert all(p in ids and p != c["id"] for p in c.get("peers", []))
        if "type" in c:
            assert str(c["type"]) in d.get("types", {})
        for k, e in c["ind"].items():
            assert k in d["indicators"]
            assert len(e["trend"]) == len(e["trend_n"]) == len(d["years"])
            for r, n in zip(e["trend"], e["trend_n"]):
                assert (r is None) == (n is None)
                # no trend point rests on fewer than 10 events (rates are rounded to 4 decimals)
                assert r is None or r * n + n * 5e-5 >= 10
            if "persistent" in e and "persistent" in d:
                p = e["persistent"]
                assert len(p["worst_years"]) == p["years_worst"] <= p["years_ranked"]
                assert all(d["persistent"]["window_start"] <= y <= d["persistent"]["window_end"] for y in p["worst_years"])
            if "similar" in e and None not in (e["similar"]["low"], e["similar"]["high"]):
                assert e["similar"]["low"] <= e["similar"]["high"]
    assert set(d.get("count_indicators", [])) <= set(d["indicators"])
    if "indicator_sets" in d:
        assert d["indicator_sets"]["core"] + d["indicator_sets"]["more"] == list(d["indicators"])
        assert set(d.get("indicator_descriptions", d["indicators"])) == set(d["indicators"])
        more = set(d["indicator_sets"]["more"])
        # The forecast was validated only on the core indicators, so no added measure carries a risk.
        assert not any("risk" in e for c in d["counties"] for k, e in c["ind"].items() if k in more)
    for s in d["state_patterns"]:
        assert s["flagged"] <= s["counties"]
    if "types" in d:
        assert sum(t["counties"] for t in d["types"].values()) == sum("type" in c for c in d["counties"])
    if "forecast_metrics" in d:
        assert sum(m["selected"] for m in d["forecast_metrics"]) == 1


@pytest.fixture(scope="module")
def published():
    return json.loads(PUBLISHED.read_text())


def test_schema_is_valid():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_published_explorer_matches_schema(published):
    assert _errors(published) == []
    _consistency(published)


@pytest.mark.parametrize("break_it, where", [
    (lambda d: d.pop("counties"), "counties"),
    (lambda d: d["counties"][0].update(id="2020"), "counties/0/id"),
    (lambda d: d["counties"][0]["ind"]["preterm_birth"].update(level="high"), "level"),
    (lambda d: d["counties"][0]["ind"]["preterm_birth"].update(rate=10.5), "rate"),
    (lambda d: d["counties"][0]["ind"]["preterm_birth"]["trend"].__setitem__(0, "0.1"), "trend/0"),
    (lambda d: d["counties"][0]["ind"].update(preterm=d["counties"][0]["ind"]["preterm_birth"]), "ind"),
    (lambda d: d["counties"][0]["ind"]["preterm_birth"]["subgroups"].update(Uninsured={}), "subgroups"),
    (lambda d: d["counties"][0]["ind"]["preterm_birth"]["similar"].update(verdict="higher"), "verdict"),
    (lambda d: d["counties"][0]["ind"]["preterm_birth"].pop("trend_n"), "preterm_birth"),
    (lambda d: d["counties"][0].update(county_name="x"), "counties/0"),
])
def test_schema_rejects_broken_files(published, break_it, where):
    d = copy.deepcopy(published)
    break_it(d)
    errs = _errors(d)
    assert errs and any(where in e for e in errs), errs


@pytest.mark.parametrize("break_it", [
    lambda d: d["counties"][0]["ind"]["preterm_birth"]["trend"].pop(),
    lambda d: d["counties"][0].update(peers=["99999"]),
    lambda d: d["counties"][0]["ind"]["preterm_birth"].update(trend=[0.0001] * len(d["years"])),
])
def test_consistency_check_catches_broken_files(published, break_it):
    d = copy.deepcopy(published)
    break_it(d)
    with pytest.raises(AssertionError):
        _consistency(d)


def test_file_written_by_the_build_matches_schema(tmp_path):
    """scripts/build_explorer_data.py on a pipeline run over synthetic counties, with and without county context."""
    from perinatal_ews import synthetic
    from perinatal_ews.cli import main
    from test_pipeline import _synthetic_context

    tidy, _ = synthetic.generate(seed=7)
    tidy = tidy[tidy["geo_id"].isin(tidy["geo_id"].drop_duplicates().head(60))].copy()
    # the explorer keys states by two-letter code; give the fictional states codes no real state uses
    names = sorted(tidy["state"].unique())
    tidy["state"] = tidy["state"].map({s: "Z" + chr(65 + i) for i, s in enumerate(names)})
    tidy.to_csv(tmp_path / "tidy.csv", index=False)
    _synthetic_context(tidy).to_csv(tmp_path / "context.csv")
    main(["run", "--input", str(tmp_path / "tidy.csv"), "--out", str(tmp_path / "res"),
          "--context", str(tmp_path / "context.csv")])
    build = [sys.executable, str(ROOT / "scripts" / "build_explorer_data.py"),
             "--tidy", str(tmp_path / "tidy.csv"), "--results", str(tmp_path / "res")]
    subprocess.run(build + ["--out", str(tmp_path / "with.json"), "--context", str(tmp_path / "context.csv")],
                   check=True, capture_output=True)
    subprocess.run(build + ["--out", str(tmp_path / "without.json")], check=True, capture_output=True)
    for name in ("with.json", "without.json"):
        d = json.loads((tmp_path / name).read_text())
        assert len(d["counties"]) == 60
        assert _errors(d) == []
        _consistency(d)
    d = json.loads((tmp_path / "with.json").read_text())
    assert all("ctx" in c and "peers" in c for c in d["counties"])


def test_count_indicator_is_marked_for_display_per_population(tmp_path):
    """An indicator with `model: count` (teen births per female aged 15-19) is listed in count_indicators,
    so the explorer shows it per 1,000 population; county births leave its population out."""
    import numpy as np
    import pandas as pd
    import yaml
    from perinatal_ews import config as cfgmod
    from perinatal_ews import synthetic
    from perinatal_ews.cli import main

    tidy, _ = synthetic.generate(seed=7)
    tidy = tidy[tidy["geo_id"].isin(tidy["geo_id"].drop_duplicates().head(60))].copy()
    names = sorted(tidy["state"].unique())
    tidy["state"] = tidy["state"].map({s: "Z" + chr(65 + i) for i, s in enumerate(names)})
    rng = np.random.default_rng(3)
    counties = tidy.drop_duplicates("geo_id")[["geo_id", "geo_name", "state"]]
    pop = {g: float(rng.integers(3_000, 40_000)) for g in counties["geo_id"]}
    teen = pd.DataFrame([dict(indicator="teen_birth_rate", subgroup="All", geo_id=c.geo_id, geo_name=c.geo_name,
                              state=c.state, year=y, numerator=float(rng.poisson(0.015 * pop[c.geo_id])),
                              denominator=pop[c.geo_id])
                         for c in counties.itertuples() for y in sorted(tidy["year"].unique())])
    pd.concat([tidy, teen], ignore_index=True).to_csv(tmp_path / "tidy.csv", index=False)
    cfg = cfgmod.load_config()
    cfg["indicators"]["teen_birth_rate"] = {"label": "Teen birth rate", "direction": "higher_is_worse",
                                            "model": "count", "set": "more",
                                            "description": "Births to mothers aged 15-19 per female aged 15-19"}
    (tmp_path / "cfg.yaml").write_text(yaml.safe_dump(cfg))
    main(["run", "--input", str(tmp_path / "tidy.csv"), "--out", str(tmp_path / "res"),
          "--config", str(tmp_path / "cfg.yaml")])
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_explorer_data.py"), "--tidy", str(tmp_path / "tidy.csv"),
                    "--results", str(tmp_path / "res"), "--config", str(tmp_path / "cfg.yaml"),
                    "--out", str(tmp_path / "e.json")], check=True, capture_output=True)
    d = json.loads((tmp_path / "e.json").read_text())
    assert d["count_indicators"] == ["teen_birth_rate"]
    # The schema lists the published indicators; allow the synthetic one, and nothing else changes.
    schema = copy.deepcopy(SCHEMA)
    schema["$defs"]["indicator"]["enum"].append("teen_birth_rate")
    assert _errors(d, schema) == []
    _consistency(d)
    scored = [c for c in d["counties"] if "teen_birth_rate" in c["ind"]]
    assert scored
    for c in scored:
        e = c["ind"]["teen_birth_rate"]
        assert e["births"] == pop[c["id"]]
        assert e["rate"] is None or 0.005 < e["rate"] < 0.05


def test_published_explorer_has_no_count_indicators(published):
    """Every published indicator is a share of births, so the explorer keeps showing percentages."""
    assert "count_indicators" not in published
