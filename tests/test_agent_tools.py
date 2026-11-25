"""Tests for the read-only assistant tools and the MCP server, on the published results."""
import asyncio
import copy
import json
from pathlib import Path

import pytest

from perinatal_ews import agent_tools as T

LATEST = Path(__file__).resolve().parents[1] / "results" / "latest" / "latest.json"


@pytest.fixture(scope="module")
def res():
    return T.load_results(LATEST)


def test_flag_list_matches_published_counts(res):
    out = T.list_state_flags(res)
    assert out["count"] == res["counts"]["alerts"] + res["counts"]["watch"]
    assert [r["level"] for r in out["flags"]] == sorted((r["level"] for r in out["flags"]), key=lambda l: l != "alert")
    assert out["period"] == res["ytd_label"] and out["data_retrieved"] == res["updated"]
    late = T.list_state_flags(res, "Late or no prenatal care", "alert")
    assert late["count"] > 0 and all(r["indicator"] == "Late or no prenatal care" and r["level"] == "alert"
                                     for r in late["flags"])


def test_state_lookup_by_code_or_name_and_values_are_published(res):
    a, b = T.get_state(res, "wi"), T.get_state(res, "Wisconsin")
    assert a == b and a["state"] == "WI"
    e = res["states_data"]["WI"]["ind"]["preterm_birth"]
    got = a["indicators"]["Preterm birth"]
    assert got["rate_pct"] == round(100 * e["rate"], 2) and got["births"] == e["births"]
    assert got["outlook_full_year"]["chance_flagged"] == e["outlook"]["p_flag"]


def test_explanation_only_uses_reliable_race_results_and_adds_follow_up(res):
    flag = T.list_state_flags(res)["flags"][0]
    ex = T.explain_state_flag(res, flag["state"], flag["indicator"])
    assert ex["level"] in ("alert", "watch") and ex["level_means"]
    ind = T._indicator(flag["indicator"])
    reliable = {r["report"] for r in res["states_data"][flag["state"]]["race"].get(ind, [])
                if r["status"] == "reliable" and r["change"] != "not compared"}
    assert {r["group"] for r in ex["by_mothers_race"]} == reliable
    assert len(ex["suggested_follow_up"]) >= 4 and ex["does_not_mean"]
    assert "AUROC" in ex["outlook_full_year"]["track_record"]
    cov = res["outlook_backtest"]["interval80_coverage"]
    assert f"{int(100 * cov + 0.5)}% of the time" in ex["outlook_full_year"]["track_record"]   # same as the explorer


def test_unknown_state_or_indicator_is_an_error_not_a_guess(res):
    with pytest.raises(T.ToolError):
        T.get_state(res, "Atlantis")
    with pytest.raises(T.ToolError):
        T.list_state_flags(res, "infant mortality")
    with pytest.raises(T.ToolError):
        T.list_state_flags(res, level="everything")


def test_status_reports_period_and_sources(res):
    s = T.data_status(res)
    assert s["latest_month_available"] == res["latest_month_available"] and s["sources"] == res["sources"]
    assert len(s["indicators"]) == 4


def test_mcp_server_lists_and_runs_tools():
    pytest.importorskip("mcp")
    from perinatal_ews.mcp_server import build_server

    server = build_server(str(LATEST))
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"data_status", "list_state_flags", "get_state", "explain_state_flag", "outlook_track_record"}
    out = asyncio.run(server.call_tool("get_state", {"state": "Atlantis"}))
    assert "error" in json.dumps(out, default=str)


def test_gestational_hypertension_carries_reporting_caveat(res):
    caveat = T._caveats()["gestational_hypertension"]
    assert "20–50%" in caveat
    # Same text as the explorer and its assistant (js/ews-tools.js).
    js = (Path(__file__).resolve().parents[1] / "js" / "ews-tools.js").read_text()
    assert f"gestational_hypertension: '{caveat}'" in js
    st = next(iter(res["states_data"]))
    out = T.get_state(res, st)["indicators"]
    assert out["Gestational hypertension"]["reporting_caveat"] == caveat
    assert all("reporting_caveat" not in v for k, v in out.items() if k != "Gestational hypertension")
    assert T.explain_state_flag(res, st, "gestational_hypertension")["reporting_caveat"] == caveat
    assert T.explain_state_flag(res, st, "preterm_birth")["reporting_caveat"] is None
    gh = T.list_state_flags(res, "gestational_hypertension")
    if gh["count"]:
        assert gh["reporting_caveats"] == {"Gestational hypertension": caveat}
    pre = T.list_state_flags(res, "preterm_birth")
    assert "reporting_caveats" not in pre


def _with_count_indicator(res):
    """The published results plus a synthetic count indicator (teen births per population) in one state."""
    r = copy.deepcopy(res)
    st = next(iter(r["states_data"]))
    r["count_indicators"] = ["teen_birth_rate"]
    r["states_data"][st]["ind"]["teen_birth_rate"] = {
        "level": "alert", "rate": 0.01523, "expected": 0.0121, "rr": 1.259, "births": 412000,
        "full_year_level": "stable", "full_year_rate": 0.0118,
        "outlook": {"proj": 0.0149, "lo": 0.0141, "hi": 0.0157, "p_flag": 0.81, "p_alert": 0.55}}
    r["states_data"][st]["race"]["teen_birth_rate"] = [
        {"g": "Black", "rate": 0.0241, "lo": 0.0222, "hi": 0.0261, "ref": 0.0188, "rr": 1.282, "change": "higher",
         "status": "reliable", "report": "Black"}]
    return r, st


def test_count_indicators_per_1000_population(res):
    r, st = _with_count_indicator(res)
    unit = T.COUNT_RATE_UNIT
    # Listed with the four, found by key or label.
    assert T.data_status(r)["indicators"]["teen_birth_rate"] == "Teen birth rate"
    flags = T.list_state_flags(r, "Teen birth rate")
    assert flags["count"] == 1
    row = flags["flags"][0]
    assert row["rate_per_1000"] == 15.23 and row["expected_per_1000"] == 12.1 and row["population"] == 412000
    assert row["rate_unit"] == unit and not {"rate_pct", "expected_pct", "births"} & row.keys()
    got = T.get_state(r, st)["indicators"]
    tb = got["Teen birth rate"]
    assert tb["rate_per_1000"] == 15.23 and tb["population"] == 412000 and tb["rate_unit"] == unit
    assert tb[f"full_year_{r['full_year_provisional']}"]["rate_per_1000"] == 11.8
    assert tb["outlook_full_year"]["projected_rate_per_1000"] == 14.9
    assert tb["outlook_full_year"]["range80_per_1000"] == [14.1, 15.7]
    assert "rate_pct" not in tb["outlook_full_year"] and "projected_rate_pct" not in tb["outlook_full_year"]
    ex = T.explain_state_flag(r, st, "teen_birth_rate")
    assert ex["rate_per_1000"] == 15.23 and ex["population"] == 412000 and ex["rate_unit"] == unit
    assert ex["by_mothers_race"] == [{"group": "Black", "rate_per_1000": 24.1, "earlier_years_per_1000": 18.8,
                                      "ratio": 1.282, "change": "higher"}]
    # Shares of births in the same file are unchanged.
    assert got["Preterm birth"] == T.get_state(res, st)["indicators"]["Preterm birth"]
    assert T.explain_state_flag(r, st, "preterm_birth") == T.explain_state_flag(res, st, "preterm_birth")
    assert "rate_unit" not in got["Preterm birth"]
