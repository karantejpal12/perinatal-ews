"""state_race.json against its JSON Schema (docs/state_race.schema.json): the published file and the file the build writes."""
import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "docs" / "state_race.schema.json").read_text())
PUBLISHED = ROOT / "results" / "2024" / "state_race.json"


def _errors(doc):
    v = jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())
    return sorted(f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in v.iter_errors(doc))


def _consistency(d):
    """Rules the schema cannot express: what the explorer's state view assumes when it draws the race table."""
    start, end = map(int, d["window"].split("-"))
    assert start <= end
    if d["previous_window"]:
        assert int(d["previous_window"].split("-")[1]) < start
    count = set(d.get("count_indicators", []))
    assert count <= {ind for inds in d["states"].values() for ind in inds}
    for st, inds in d["states"].items():
        for ind, rows in inds.items():
            by = {r["g"]: r for r in rows}
            assert len(by) == len(rows), f"{st} {ind}: a group appears twice"
            assert "All" in by, f"{st} {ind}: no row for all mothers"
            for r in rows:
                years = [int(y) for y in r["years"].split(",")] if r["years"] else []
                assert years == sorted(set(years)) and all(start <= y <= end for y in years)
                if r["status"] == "reliable":
                    assert len(years) >= 2 and r["report"] == r["g"]
                    assert ind in count or r["n"] <= r["births"]   # counts per population may exceed it
                    assert r["lo"] <= r["rate"] <= r["hi"]
                    assert abs(r["rate"] - r["n"] / r["births"]) <= 5e-5 + 1e-9   # rates are rounded to 4 decimals
                else:
                    # a small group points to a reliable combined group it belongs to, or says insufficient data
                    rep = r["report"]
                    assert rep == "insufficient data" or (rep in by and by[rep]["combined"]
                                                          and by[rep]["status"] == "reliable"), (st, ind, r["g"], rep)
                if "rr" in r:
                    # rate ratio matches the rounded rates, within rounding (rates to 4 decimals, ratios to 3)
                    ratio = r["rate"] / r["prev"]
                    tol = 5e-4 + ratio * (5e-5 / r["rate"] + 5e-5 / r["prev"])
                    assert abs(r["rr"] - ratio) <= tol, (st, ind, r["g"], r["rr"], ratio)
                    if r["change"] == "higher":
                        assert r["rr"] > 1
                    elif r["change"] == "lower":
                        assert r["rr"] < 1


@pytest.fixture(scope="module")
def published():
    if not PUBLISHED.exists():
        pytest.skip("state_race.json not built")
    return json.loads(PUBLISHED.read_text())


def _row(d, change):
    return next(r for s in d["states"].values() for rows in s.values() for r in rows if r["change"] == change)


def test_schema_is_valid():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_published_state_race_matches_schema(published):
    assert _errors(published) == []
    _consistency(published)


@pytest.mark.parametrize("break_it, where", [
    (lambda d: d.pop("states"), "states"),
    (lambda d: d.update(window="2022–2024"), "window"),
    (lambda d: d["states"].update(Alabama=d["states"]["AL"]), "states"),
    (lambda d: d["states"]["AL"].update(preterm=d["states"]["AL"]["preterm_birth"]), "AL"),
    (lambda d: d["states"]["AL"]["preterm_birth"][0].update(rate=14.27), "rate"),
    (lambda d: d["states"]["AL"]["preterm_birth"][0].update(n=12), "n"),
    (lambda d: d["states"]["AL"]["preterm_birth"][0].update(status="ok"), "status"),
    (lambda d: d["states"]["AL"]["preterm_birth"][0].update(years="2022-2024"), "years"),
    (lambda d: d["states"]["AL"]["preterm_birth"][0].pop("combined"), "preterm_birth/0"),
    (lambda d: _row(d, "higher").pop("rr"), "states/"),
    (lambda d: _row(d, "not compared (an estimate is not reliable)").update(rr=1.2), "states/"),
    (lambda d: next(r for s in d["states"].values() for rows in s.values() for r in rows
                    if r["status"] != "reliable").update(rate=0.1), "rate"),
    (lambda d: next(r for s in d["states"].values() for rows in s.values() for r in rows
                    if r["status"] != "reliable").update(change="higher", prev=0.1, rr=1.5), "change"),
])
def test_schema_rejects_broken_files(published, break_it, where):
    d = copy.deepcopy(published)
    break_it(d)
    errs = _errors(d)
    assert errs and any(where in e for e in errs), errs


def _first_small(d):
    return next(r for s in d["states"].values() for rows in s.values() for r in rows if r["report"] != r["g"]
                and r["report"] != "insufficient data")


@pytest.mark.parametrize("break_it", [
    lambda d: d["states"]["AL"]["preterm_birth"].append(dict(d["states"]["AL"]["preterm_birth"][0])),
    lambda d: d["states"]["AL"]["preterm_birth"][0].update(rate=0.2),
    lambda d: d["states"]["AL"]["preterm_birth"][0].update(years="2019,2020,2021"),
    lambda d: _first_small(d).update(report="White"),
    lambda d: _row(d, "higher").update(rr=0.9),
])
def test_consistency_check_catches_broken_files(published, break_it):
    d = copy.deepcopy(published)
    break_it(d)
    with pytest.raises(AssertionError):
        _consistency(d)


def _synthetic_state_race(seed=3):
    """Fictional state counts by mother's race (15 groups), with small groups and missing years (counts below 3)."""
    from perinatal_ews.pooling import ASIAN_15, NHOPI_15

    rng = np.random.default_rng(seed)
    sizes = {"White": 30000, "Black": 8000, "American Indian or Alaskan Native": 600, "More than one race": 1200,
             **{g: 900 for g in ASIAN_15}, **{g: 60 for g in NHOPI_15}}
    inds = {"preterm_birth": 0.10, "low_birth_weight": 0.08, "late_no_prenatal_care": 0.06,
            "gestational_hypertension": 0.09}
    rows = []
    for st, scale in (("ZA", 1.0), ("ZB", 0.25), ("ZC", 0.04)):
        for y in range(2016, 2025):
            for ind, p in inds.items():
                tot_n = tot_d = 0
                for g, size in sizes.items():
                    den = max(int(size * scale * rng.uniform(0.9, 1.1)), 1)
                    num = int(rng.binomial(den, p * (1.3 if y >= 2022 and g == "Black" else 1.0)))
                    tot_n += num; tot_d += den
                    rows.append(dict(geo_id=st, geo_name=st, state=st, year=y, indicator=ind, subgroup=g,
                                     numerator=num if num >= 3 else np.nan, denominator=float(den)))
                rows.append(dict(geo_id=st, geo_name=st, state=st, year=y, indicator=ind, subgroup="All",
                                 numerator=tot_n, denominator=float(tot_d)))
    return pd.DataFrame(rows)


def test_file_written_by_the_build_matches_schema(tmp_path):
    """`perinatal-ews pooled` on synthetic state counts, then scripts/build_explorer_data.py's state-race step."""
    from perinatal_ews.cli import main

    _synthetic_state_race().to_csv(tmp_path / "tidy.csv", index=False)
    main(["pooled", "--input", str(tmp_path / "tidy.csv"), "--window", "3", "--out", str(tmp_path / "pooled")])
    spec = importlib.util.spec_from_file_location("build_explorer_data", ROOT / "scripts" / "build_explorer_data.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    build._state_race(tmp_path / "pooled", tmp_path / "state_race.json")
    d = json.loads((tmp_path / "state_race.json").read_text())
    assert d["window"] == "2022-2024" and d["previous_window"] == "2019-2021"
    assert sorted(d["states"]) == ["ZA", "ZB", "ZC"]
    assert _errors(d) == []
    _consistency(d)
    rows = [r for s in d["states"].values() for rs in s.values() for r in rs]
    # the synthetic data reach every case the explorer draws
    assert {r["status"].split(" ")[0] for r in rows} >= {"reliable", "too", "suppressed", "unreliable"}
    assert {r["change"] for r in rows} >= {"higher", "no clear change", "not compared (an estimate is not reliable)"}
    assert any(r["report"] not in (r["g"], "insufficient data") for r in rows)
    assert any(r["report"] == "insufficient data" for r in rows)


def test_published_state_race_has_no_count_indicators(published):
    """The published indicators are all shares of births, so the file carries no count_indicators."""
    assert "count_indicators" not in published


def test_count_indicator_is_marked_for_display_per_population(tmp_path):
    """An indicator with `model: count` (teen births per female aged 15-19) is listed in count_indicators,
    so the state table shows it per 1,000 population, with exact Poisson intervals and the population as its
    'births'; the four indicators' rows are the same as without it."""
    import yaml
    from perinatal_ews import config as cfgmod
    from perinatal_ews.cli import main
    from perinatal_ews.indicators import poisson_rate_interval

    spec = importlib.util.spec_from_file_location("build_explorer_data", ROOT / "scripts" / "build_explorer_data.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)

    tidy = _synthetic_state_race()
    tidy.to_csv(tmp_path / "plain.csv", index=False)
    main(["pooled", "--input", str(tmp_path / "plain.csv"), "--window", "3", "--out", str(tmp_path / "plain")])
    build._state_race(tmp_path / "plain", tmp_path / "plain.json", ["teen_birth_rate"])
    plain = json.loads((tmp_path / "plain.json").read_text())
    assert "count_indicators" not in plain   # listed only when the results include it

    # Teen births: about 15 per 1,000 females aged 15-19, with a population (not births) as denominator.
    rng = np.random.default_rng(11)
    teen = tidy[tidy["indicator"] == "preterm_birth"].copy()
    teen["indicator"] = "teen_birth_rate"
    teen["denominator"] = (teen["denominator"] * 1.7).round()
    teen["numerator"] = rng.poisson(0.015 * teen["denominator"]).astype(float)
    teen.loc[teen["numerator"] < 3, "numerator"] = np.nan
    all_rows = teen[teen["subgroup"] != "All"].groupby(["state", "year"])[["numerator", "denominator"]].sum(min_count=1)
    teen = teen.set_index(["state", "year"])
    is_all = teen["subgroup"] == "All"
    teen.loc[is_all, ["numerator", "denominator"]] = all_rows.reindex(teen.index[is_all]).to_numpy()
    pd.concat([tidy, teen.reset_index()], ignore_index=True).to_csv(tmp_path / "teen.csv", index=False)
    cfg = cfgmod.load_config()
    cfg["indicators"]["teen_birth_rate"] = {"label": "Teen birth rate", "direction": "higher_is_worse",
                                            "model": "count", "set": "more"}
    (tmp_path / "cfg.yaml").write_text(yaml.safe_dump(cfg))
    main(["pooled", "--input", str(tmp_path / "teen.csv"), "--window", "3", "--out", str(tmp_path / "teen"),
          "--config", str(tmp_path / "cfg.yaml")])
    build._state_race(tmp_path / "teen", tmp_path / "teen.json", ["teen_birth_rate"])
    d = json.loads((tmp_path / "teen.json").read_text())
    assert d["count_indicators"] == ["teen_birth_rate"]
    schema = copy.deepcopy(SCHEMA)
    schema["$defs"]["indicator"]["enum"].append("teen_birth_rate")
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    assert [e.message for e in v.iter_errors(d)] == []
    _consistency(d)
    for st, inds in plain["states"].items():
        assert {k: d["states"][st][k] for k in inds} == inds
    rows = [r for s in d["states"].values() for r in s["teen_birth_rate"] if r["status"] == "reliable"]
    assert rows
    for r in rows:
        assert 0.005 < r["rate"] < 0.03 and r["births"] > r["n"]
        lo, hi = poisson_rate_interval(r["n"], r["births"])
        assert abs(r["lo"] - float(lo)) <= 5e-5 + 1e-9 and abs(r["hi"] - float(hi)) <= 5e-5 + 1e-9
