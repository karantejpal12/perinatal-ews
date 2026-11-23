"""latest.json against its JSON Schema (docs/latest.schema.json): the published file and the file the code writes."""
import copy
import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "docs" / "latest.schema.json").read_text())
PUBLISHED = ROOT / "results" / "latest" / "latest.json"


def _errors(doc):
    v = jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())
    return sorted(f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in v.iter_errors(doc))


@pytest.fixture(scope="module")
def published():
    return json.loads(PUBLISHED.read_text())


def test_schema_is_valid():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_published_latest_matches_schema(published):
    assert _errors(published) == []


def test_published_headline_counts_match_the_state_results(published):
    s = published["states_data"]
    assert published["states"] == len(s)
    levels = [e["level"] for v in s.values() for e in v["ind"].values()]
    assert published["counts"] == {"alerts": levels.count("alert"), "watch": levels.count("watch")}
    # the outlook is published for every state and indicator, with the projection inside its interval
    for v in s.values():
        for e in v["ind"].values():
            o = e["outlook"]
            assert o["lo"] <= o["proj"] <= o["hi"] and o["p_alert"] <= o["p_flag"]


@pytest.mark.parametrize("break_it, where", [
    (lambda d: d.pop("ytd_label"), "ytd_label"),
    (lambda d: d["counts"].update(alerts="6"), "counts/alerts"),
    (lambda d: d["states_data"]["GA"]["ind"]["preterm_birth"].update(level="high"), "level"),
    (lambda d: d["states_data"]["GA"]["ind"]["preterm_birth"].update(rate=10.5), "rate"),
    (lambda d: d["states_data"]["GA"]["ind"].update(preterm=d["states_data"]["GA"]["ind"]["preterm_birth"]), "ind"),
    (lambda d: d["states_data"]["GA"]["race"]["preterm_birth"][0].update(status="ok"), "status"),
    (lambda d: d["states_data"].update(Georgia=d["states_data"]["GA"]), "states_data"),
    (lambda d: d.update(ytd_through_month=13), "ytd_through_month"),
])
def test_schema_rejects_broken_files(published, break_it, where):
    d = copy.deepcopy(published)
    break_it(d)
    errs = _errors(d)
    assert errs and any(where in e for e in errs), errs


def test_file_written_by_the_monthly_update_matches_schema(tmp_path):
    """The payload update_latest.py writes, built from synthetic data, with and without the outlook."""
    from perinatal_ews.config import load_config
    from perinatal_ews.latest import explorer_payload, run_latest
    from test_pipeline import _synthetic_state_feed

    prov, base = _synthetic_state_feed()
    meta = {"ytd_year": 2026, "ytd_through_month": 8, "latest_month_available": "2026-08",
            "latest_month_completeness": 0.99, "provisional_years": [2025, 2026], "fetched_at": "2026-10-14",
            "sources": {"provisional": "synthetic", "final": "synthetic"}}
    p = explorer_payload(run_latest(prov, base, meta, load_config(), tmp_path))
    p = json.loads(json.dumps(p, default=str))           # as written to disk
    assert _errors(p) == []
    e = next(iter(next(iter(p["states_data"].values()))["ind"].values()))
    e["outlook"] = {"proj": 0.1, "lo": 0.09, "hi": 0.11, "p_flag": 0.2, "p_alert": 0.05}
    p["outlook_backtest"] = {"years": [2024, 2025], "state_indicators": 204, "full_year_flags": 10,
                             "interval80_coverage": 0.8, "months_known": 8, "outlook": {"auroc": 0.9}}
    assert _errors(p) == []


def _teen_feed(prov, base, seed=5):
    """Add a count indicator (teen births per female aged 15-19) to the synthetic state feed: the same
    states, years and race groups, with Poisson counts over a population rather than births. As in a real
    download, the population is annual in every file, whatever the months covered; events accrue with
    the months."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    pop = {f: float(rng.integers(40_000, 300_000)) for f in prov["state_fips"].unique()}
    rate = 0.015
    b = base[base["indicator"] == "preterm_birth"].copy()
    b["indicator"] = "teen_birth_rate"
    b["denominator"] = b["state_fips"].map(pop)
    b["numerator"] = rng.poisson(rate * b["denominator"] * b["through_month"] / 12).astype(float)
    p = prov[prov["indicator"] == "preterm_birth"].copy()
    p["indicator"] = "teen_birth_rate"
    share = {"All": 1.0, "White": 0.6, "Filipino": 0.004, "Hawaiian": 0.003}
    p["denominator"] = p["state_fips"].map(pop) * p["subgroup"].map(share)
    p["numerator"] = rng.poisson(rate * p["denominator"] * np.where(p["series"] == "prov_ytd", 8 / 12, 1.0)).astype(float)
    return pd.concat([prov, p], ignore_index=True), pd.concat([base, b], ignore_index=True)


def test_count_indicator_in_latest_is_marked_and_uses_poisson_intervals(tmp_path):
    """An indicator with `model: count` is listed in count_indicators (so the explorer shows it per 1,000
    population), its race rows have exact Poisson intervals and a Poisson rate-ratio interval, and the
    results for the four indicators are unchanged."""
    import numpy as np
    from perinatal_ews.config import load_config
    from perinatal_ews.indicators import poisson_rate_interval
    from perinatal_ews.latest import explorer_payload, run_latest
    from test_pipeline import _synthetic_state_feed

    meta = {"ytd_year": 2026, "ytd_through_month": 8, "latest_month_available": "2026-08",
            "latest_month_completeness": 0.99, "provisional_years": [2025, 2026], "fetched_at": "2026-10-14",
            "sources": {"provisional": "synthetic", "final": "synthetic"}}
    prov, base = _synthetic_state_feed()
    plain = explorer_payload(run_latest(prov, base, meta, load_config(), tmp_path / "plain"))
    assert "count_indicators" not in plain

    cfg = load_config()
    cfg["indicators"]["teen_birth_rate"] = {"label": "Teen birth rate", "direction": "higher_is_worse",
                                            "model": "count", "set": "more"}
    tprov, tbase = _teen_feed(prov, base)
    res = run_latest(tprov, tbase, meta, cfg, tmp_path / "teen")
    p = json.loads(json.dumps(explorer_payload(res), default=str))
    assert p["count_indicators"] == ["teen_birth_rate"]
    assert json.loads((tmp_path / "teen" / "latest_meta.json").read_text())["count_indicators"] == ["teen_birth_rate"]
    schema = copy.deepcopy(SCHEMA)
    schema["$defs"]["indicator"]["enum"].append("teen_birth_rate")
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    assert [e.message for e in v.iter_errors(p)] == []

    # The four indicators' results are the same with or without the count indicator.
    for st, s in plain["states_data"].items():
        t = p["states_data"][st]
        assert {k: t["ind"][k] for k in s["ind"]} == s["ind"]
        assert {k: t["race"][k] for k in s["race"]} == s["race"]
    assert p["counts"]["alerts"] >= plain["counts"]["alerts"]

    # Race rows: exact Poisson intervals and log rate-ratio variance 1/k + 1/k_ref.
    race = res["race"][(res["race"]["indicator"] == "teen_birth_rate") & (res["race"]["status"] == "reliable")]
    assert len(race)
    lo, hi = poisson_rate_interval(race["numerator"], race["denominator"])
    assert np.allclose(race["ci_low"], lo) and np.allclose(race["ci_high"], hi)
    se = np.sqrt(1 / race["numerator"] + 1 / race["ref_num"])
    assert np.allclose(race["rr_low"], race["rate_ratio"] * np.exp(-1.96 * se))
    assert ((race["ci_low"] < race["rate"]) & (race["rate"] < race["ci_high"])).all()
    # About 1.5% of the population a year (January-August scaled to person-time), with the population
    # (not births) behind each state's rate: eight months of an annual population.
    assert 0.013 < race["rate"].median() < 0.017
    for st, s in p["states_data"].items():
        e = s["ind"]["teen_birth_rate"]
        assert 0.01 < e["rate"] < 0.02 and e["births"] > 10_000
