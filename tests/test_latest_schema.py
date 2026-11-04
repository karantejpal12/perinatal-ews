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
