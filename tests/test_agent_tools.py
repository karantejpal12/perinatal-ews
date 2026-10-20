"""Tests for the read-only assistant tools and the MCP server, on the published results."""
import asyncio
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
