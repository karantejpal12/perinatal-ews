"""Read-only question-answering tools over the published state results, for AI assistants.

These functions read ``results/latest/latest.json`` (the file behind the explorer's state view) and
return plain dictionaries. ``perinatal_ews.mcp_server`` offers them to any assistant that speaks the
Model Context Protocol (MCP), so health department staff can ask, for example, "Which states are
flagged for late prenatal care this year, and how likely is the full year to be flagged?" from the
assistant they already use.

Every figure returned comes from the published file; nothing is recomputed or estimated here. Each
answer carries the period, retrieval date and source so the assistant can cite them.

Shares of births are given as percentages (``rate_pct``, with ``births`` as the denominator). Indicators
listed in the file's ``count_indicators`` (``model: count``, counts per population such as the teen birth
rate) are given per 1,000 population (``rate_per_1000``, with ``population`` and a ``rate_unit``), as the
explorer shows them.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from .config import core_indicators, load_config
from .pooling import STATE_NAMES

PUBLISHED_URL = "https://raw.githubusercontent.com/karantejpal12/perinatal-ews/main/results/latest/latest.json"
FLAGGED = ("alert", "watch")

LEVEL_MEANING = {
    "alert": "the rate is clearly higher than expected: a Benjamini-Hochberg q-value of 0.05 or less across all "
             "states, at least 10% above expected, and at least 20 events",
    "watch": "the rate is higher than expected but less certain: a z-score of 2 or more and at least 5% above expected",
    "stable": "the rate is in line with what the state's own recent years and the national trend suggest",
    "insufficient data": "too few births or events to judge",
}


class ToolError(ValueError):
    """A question the published results cannot answer (unknown state or indicator)."""


def load_results(source: str | Path | None = None) -> dict:
    """Load latest.json from a path or URL; by default the repository copy if present, else the published one."""
    if source is None:
        local = Path(__file__).resolve().parents[2] / "results" / "latest" / "latest.json"
        source = local if local.exists() else PUBLISHED_URL
    s = str(source)
    if s.startswith(("http://", "https://")):
        with urllib.request.urlopen(s, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    return json.loads(Path(s).read_text())


COUNT_RATE_UNIT = "per 1,000 population (the denominator is the population, not births)"


def _count_keys(results: dict | None) -> list[str]:
    """Indicators the results file lists as counts per population (absent in files without any)."""
    return list((results or {}).get("count_indicators") or [])


def _labels(results: dict | None = None) -> dict:
    """Indicators in the monthly state results: the original four (config.core_indicators), plus any
    count indicators the results file lists."""
    cfg = load_config()
    labels = {k: cfg["indicators"][k]["label"] for k in core_indicators(cfg)}
    for k in _count_keys(results):
        spec = cfg["indicators"].get(k) or {}
        labels.setdefault(k, spec.get("label") or k.replace("_", " ").capitalize())
    return labels


def _caveats() -> dict:
    """Reporting-quality caveats by indicator key (the ``caveat`` field of the indicator config)."""
    return {k: v["caveat"] for k, v in load_config()["indicators"].items() if v.get("caveat")}


def _caveats_for(keys) -> dict | None:
    """{label: caveat} for the given indicator keys that have one, or None if none do."""
    labels, cav = _labels(), _caveats()
    out = {labels.get(k, k): cav[k] for k in dict.fromkeys(keys) if k in cav}
    return out or None


def _indicator(name: str, results: dict | None = None) -> str:
    labels = _labels(results)
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    if key in labels:
        return key
    for k, lab in labels.items():
        if lab.lower() == name.strip().lower():
            return k
    raise ToolError(f"Unknown indicator '{name}'. Choose one of: " + ", ".join(f"{k} ({v})" for k, v in labels.items()))


def _state(results: dict, name: str) -> str:
    s = name.strip()
    if s.upper() in results["states_data"]:
        return s.upper()
    for abbr, full in STATE_NAMES.items():
        if full.lower() == s.lower() and abbr in results["states_data"]:
            return abbr
    raise ToolError(f"No results for state '{name}'. Use a two-letter code (e.g. GA) or a full state name.")


def _pct(x):
    return None if x is None else round(100 * x, 2)


def _per1000(x):
    return None if x is None else round(1000 * x, 3)


def _scale(results: dict, key: str):
    """(field suffix, converter, denominator name) for an indicator: 'pct' for shares of births,
    'per_1000' for counts per population."""
    if key in _count_keys(results):
        return "per_1000", _per1000, "population"
    return "pct", _pct, "births"


def _rates(results: dict, key: str, e: dict) -> dict:
    """Rate, expected rate and denominator of a year-so-far result, in the indicator's unit."""
    sfx, f, den = _scale(results, key)
    out = {f"rate_{sfx}": f(e["rate"]), f"expected_{sfx}": f(e["expected"]), "ratio_to_expected": e["rr"],
           den: e["births"]}
    if den == "population":
        out["rate_unit"] = COUNT_RATE_UNIT
    return out


def _outlook(results: dict, key: str, o: dict) -> dict:
    sfx, f, _ = _scale(results, key)
    return {f"projected_rate_{sfx}": f(o.get("proj")), f"range80_{sfx}": [f(o.get("lo")), f(o.get("hi"))],
            "chance_flagged": o.get("p_flag"), "chance_alert": o.get("p_alert")}


def _source(results: dict) -> dict:
    return {"period": results["ytd_label"], "data_retrieved": results["updated"],
            "provisional_data": True, "sources": results["sources"]}


def data_status(results: dict) -> dict:
    """How current the results are, what they cover, and how many flags there are."""
    return {**_source(results),
            "latest_month_available": results["latest_month_available"],
            "latest_month_used": results["latest_month_available"] if not results["excluded_latest_month"] else
            "excluded (births below 97% of expected, so the month is likely incomplete)",
            "states": results["states"], "flags": results["counts"],
            "full_year_compared": results["full_year_provisional"], "final_years_used_as_history": results["final_years"],
            "indicators": _labels(results)}


def list_state_flags(results: dict, indicator: str | None = None, level: str = "flagged") -> dict:
    """States flagged this year so far, optionally for one indicator; level is 'flagged', 'alert' or 'watch'."""
    if level not in ("flagged", "alert", "watch"):
        raise ToolError("level must be 'flagged', 'alert' or 'watch'")
    want = FLAGGED if level == "flagged" else (level,)
    ind = _indicator(indicator, results) if indicator else None
    labels = _labels(results)
    rows = []
    for st, v in results["states_data"].items():
        for k, e in v["ind"].items():
            if (ind is None or k == ind) and e["level"] in want:
                o = e.get("outlook") or {}
                rows.append({"state": st, "state_name": STATE_NAMES.get(st, st), "indicator": labels.get(k, k),
                             "level": e["level"], **_rates(results, k, e),
                             "chance_full_year_flagged": o.get("p_flag")})
    rows.sort(key=lambda r: (r["level"] != "alert", -(r["ratio_to_expected"] or 0)))
    out = {**_source(results), "count": len(rows), "flags": rows,
           "note": "A flag is a statistical signal for follow-up, not proof of a real change in health."}
    keys = {lab: k for k, lab in labels.items()}
    cav = _caveats_for(keys.get(r["indicator"], r["indicator"]) for r in rows)
    if cav:
        out["reporting_caveats"] = cav
    return out


def get_state(results: dict, state: str) -> dict:
    """All indicators for one state this year so far, with last full year and the full-year outlook."""
    st = _state(results, state)
    labels, caveats = _labels(results), _caveats()
    out = {}
    for k, e in results["states_data"][st]["ind"].items():
        o = e.get("outlook") or {}
        sfx, f, _ = _scale(results, k)
        out[labels.get(k, k)] = {
            "level": e["level"], **_rates(results, k, e),
            f"full_year_{results['full_year_provisional']}": {"level": e.get("full_year_level"),
                                                              f"rate_{sfx}": f(e.get("full_year_rate"))},
            "outlook_full_year": _outlook(results, k, o) if o else None}
        if k in caveats:
            out[labels.get(k, k)]["reporting_caveat"] = caveats[k]
    return {**_source(results), "state": st, "state_name": STATE_NAMES.get(st, st), "indicators": out}


def explain_state_flag(results: dict, state: str, indicator: str) -> dict:
    """What a state's result for one indicator means, how sure it is, and follow-up checks to consider."""
    st = _state(results, state)
    ind = _indicator(indicator, results)
    e = results["states_data"][st]["ind"].get(ind)
    if e is None:
        raise ToolError(f"No {ind} result for {st}.")
    o = e.get("outlook") or {}
    fy = results["full_year_provisional"]
    sfx, f, _ = _scale(results, ind)
    race = [{"group": r["report"], f"rate_{sfx}": f(r["rate"]), f"earlier_years_{sfx}": f(r["ref"]),
             "ratio": r["rr"], "change": r["change"]}
            for r in results["states_data"][st].get("race", {}).get(ind, [])
            if r["status"] == "reliable" and r["change"] != "not compared"]
    checks = [
        "Check whether the same indicator moved in neighbouring states (list_state_flags for this indicator).",
        f"Compare with the full year {fy}: a change already present then is less likely to be a data artefact.",
        "Ask vital records whether birth-certificate reporting, coding or completeness of this item changed "
        "(for example a new form, software or facility reporting practice).",
        "Provisional counts can be revised; recheck after the next monthly update before acting on a single month.",
    ]
    if race:
        checks.insert(1, "Look at which groups by mother's race moved (see by_mothers_race): a change concentrated in "
                         "one group points to different follow-up than a state-wide shift.")
    return {
        **_source(results), "state": st, "state_name": STATE_NAMES.get(st, st), "indicator": _labels(results)[ind],
        "level": e["level"], "level_means": LEVEL_MEANING.get(e["level"]),
        **_rates(results, ind, e),
        "expected_is": "the state's own rate in the same months of recent years, adjusted for the change across all states",
        f"full_year_{fy}": {"level": e.get("full_year_level"), f"rate_{sfx}": f(e.get("full_year_rate"))},
        "outlook_full_year": {**_outlook(results, ind, o),
                              "track_record": outlook_track_record(results)["summary"]} if o else None,
        "by_mothers_race": race,
        "reporting_caveat": _caveats().get(ind),
        "does_not_mean": ["It does not show a cause.", "It says nothing about any individual's risk.",
                          "It can reflect changes in how births are recorded rather than in health."],
        "suggested_follow_up": checks,
    }


def outlook_track_record(results: dict) -> dict:
    """How well the full-year outlook performed when tested on past years."""
    b = results.get("outlook_backtest") or {}
    if not b:
        return {"summary": None}
    o = b.get("outlook", {})
    summary = (f"Tested on {b['years'][0]}-{b['years'][-1]} using only the months known at this point of each year: "
               f"AUROC {o.get('auroc'):.2f}, Brier score {o.get('brier'):.3f}; 80% ranges contained the actual full-year "
               f"rate {int(100 * b['interval80_coverage'] + 0.5)}% of the time.")       # half up, as in the explorer
    return {"summary": summary, "details": b}
