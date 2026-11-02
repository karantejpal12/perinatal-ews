"""Checks on the published results files themselves (results/latest)."""
import json
from pathlib import Path

import pandas as pd
import pytest

LATEST = Path(__file__).resolve().parents[1] / "results" / "latest"
MIN_EVENTS = 20  # NCHS: rates based on fewer than 20 events are unreliable


@pytest.fixture(scope="module")
def race():
    """Every state-by-race entry in latest.json, joined to its event counts in state_race_ytd.csv."""
    d = json.loads((LATEST / "latest.json").read_text())
    rows = [dict(e, state=st, indicator=ind)
            for st, v in d["states_data"].items() for ind, lst in v["race"].items() for e in lst]
    pub = pd.DataFrame(rows)
    counts = pd.read_csv(LATEST / "state_race_ytd.csv", dtype={"geo_id": str})
    counts = counts.drop(columns="state").rename(columns={"geo_id": "state", "subgroup": "g"})
    return pub.merge(counts[["state", "indicator", "g", "numerator", "ref_num", "status"]],
                     on=["state", "indicator", "g"], how="outer", suffixes=("", "_csv"), indicator=True)


def test_every_published_race_entry_has_its_counts(race):
    assert len(race) > 0
    assert (race["_merge"] == "both").all(), race.loc[race["_merge"] != "both", ["state", "indicator", "g"]]
    assert (race["status"] == race["status_csv"]).all()


def test_no_published_race_rate_rests_on_fewer_than_20_events(race):
    shown = race[race[["rate", "lo", "hi"]].notna().any(axis=1)]
    assert len(shown) > 0
    assert (shown["numerator"] >= MIN_EVENTS).all(), shown.loc[shown["numerator"] < MIN_EVENTS, ["state", "g"]]
    assert (shown["status"] == "reliable").all()


def test_no_published_reference_rate_or_ratio_rests_on_fewer_than_20_events(race):
    ref = race[race["ref"].notna()]
    assert len(ref) > 0 and (ref["ref_num"] >= MIN_EVENTS).all()
    rr = race[race["rr"].notna()]
    assert ((rr["numerator"] >= MIN_EVENTS) & (rr["ref_num"] >= MIN_EVENTS)).all()
    compared = race[race["change"] != "not compared"]
    assert compared["rr"].notna().all()


def test_unreliable_and_suppressed_groups_show_no_rate(race):
    hidden = race[race["status"] != "reliable"]
    assert len(hidden) > 0
    assert hidden[["rate", "lo", "hi", "ref", "rr"]].isna().all().all()
    assert (hidden["change"] == "not compared").all()
    small = race[race["numerator"] < MIN_EVENTS]
    assert (small["status"] == f"unreliable (<{MIN_EVENTS} events)").all()
