import numpy as np
import pandas as pd
import pytest

from perinatal_ews import config as cfgmod
from perinatal_ews import synthetic
from perinatal_ews.detect import detect
from perinatal_ews.missing import unknown_in_denominator, unknown_sensitivity
from perinatal_ews.schema import TOTAL_SUBGROUP


@pytest.fixture(scope="module")
def cfg():
    return cfgmod.load_config()


@pytest.fixture(scope="module")
def tidy():
    t, _ = synthetic.generate(seed=7)
    t = t[t["subgroup"] == TOTAL_SUBGROUP].copy()
    t["unknown"] = (t["denominator"] * 0.01).round()  # 1% unknown everywhere
    return t.reset_index(drop=True)


def test_adds_unknowns_and_suppressed_unknown_makes_row_unusable():
    t = pd.DataFrame({"numerator": [10.0, 10.0], "denominator": [100.0, 100.0], "unknown": [5.0, np.nan]})
    alt = unknown_in_denominator(t)
    assert alt["denominator"].tolist()[0] == 105
    assert np.isnan(alt.at[1, "numerator"]) and np.isnan(alt.at[1, "denominator"])
    assert t.at[0, "denominator"] == 100  # input untouched


def test_requires_unknown_column(cfg, tidy):
    with pytest.raises(ValueError, match="unknown"):
        unknown_sensitivity(tidy.drop(columns="unknown"), cfg)


def test_excluded_side_matches_default_detection(cfg, tidy):
    sens = unknown_sensitivity(tidy, cfg)
    base = detect(tidy, cfg)
    m = sens.merge(base[["indicator", "subgroup", "geo_id", "level"]], on=["indicator", "subgroup", "geo_id"])
    assert len(m) == len(base)
    assert (m["level_excluded"].astype(str) == m["level"].astype(str)).all()
    assert np.allclose(sens["unknown_share"].dropna(), 0.01, atol=0.002)


def test_alert_that_rests_on_unknown_handling_is_reported(cfg, tidy):
    year = int(tidy["year"].max())
    base = detect(tidy, cfg)
    alert = base[base["level"] == "alert"].iloc[0]
    t = tidy.copy()
    row = (t["geo_id"] == alert["geo_id"]) & (t["indicator"] == alert["indicator"]) & (t["year"] == year)
    # Many births with the item unknown in the target year only: counting them as non-cases
    # pulls the rate far below the county's history, so the alert disappears.
    t.loc[row, "unknown"] = t.loc[row, "denominator"] * 2
    sens = unknown_sensitivity(t, cfg).set_index(["indicator", "geo_id"])
    r = sens.loc[(alert["indicator"], alert["geo_id"])]
    assert r["level_excluded"] == "alert" and r["level_included"] != "alert"
    assert r["changed"] and r["change"].startswith("alert -> ")
    assert sens["changed"].iloc[0]  # changed rows are listed first


def test_suppressed_unknown_is_marked(cfg, tidy):
    year = int(tidy["year"].max())
    t = tidy.copy()
    gid = t["geo_id"].iloc[0]
    t.loc[(t["geo_id"] == gid) & (t["year"] == year), "unknown"] = np.nan
    sens = unknown_sensitivity(t, cfg)
    r = sens[sens["geo_id"] == gid]
    assert r["unknown_missing"].all()
    assert (r["level_included"] == "insufficient data").all()
    assert not sens.loc[sens["geo_id"] != gid, "unknown_missing"].any()


def test_run_writes_sensitivity_file_only_with_unknown_column(tmp_path, tidy):
    from perinatal_ews.cli import main
    f = tmp_path / "t.csv"
    tidy.to_csv(f, index=False)
    main(["run", "--input", str(f), "--out", str(tmp_path / "a")])
    out = pd.read_csv(tmp_path / "a" / "unknown_sensitivity.csv")
    assert {"level_excluded", "level_included", "changed"} <= set(out.columns)
    tidy.drop(columns="unknown").to_csv(f, index=False)
    main(["run", "--input", str(f), "--out", str(tmp_path / "b")])
    assert not (tmp_path / "b" / "unknown_sensitivity.csv").exists()


def test_to_state_sums_unknown_and_keeps_missing_missing(tidy):
    from perinatal_ews.pooling import to_state
    st = to_state(tidy)
    assert "unknown" in st.columns
    key = ["state", "year", "indicator", "subgroup"]
    expect = tidy.groupby(key)["unknown"].sum().rename("expect").reset_index()
    m = st.merge(expect, on=key)
    assert (m["unknown"] == m["expect"]).all()
    t2 = tidy.copy()
    k = t2.index[0]
    t2.loc[k, "unknown"] = np.nan
    s2 = to_state(t2)
    row = (s2.state == t2.at[k, "state"]) & (s2.year == t2.at[k, "year"]) & (s2.indicator == t2.at[k, "indicator"])
    assert s2.loc[row, "unknown"].isna().all()
    assert s2.loc[row, "numerator"].notna().all()       # numerator unaffected
    assert s2.loc[~row, "unknown"].notna().all()
    plain = to_state(tidy.drop(columns="unknown"))     # tables without the column are unchanged
    assert "unknown" not in plain.columns
    assert plain[["numerator", "denominator"]].equals(st[["numerator", "denominator"]])


def test_state_level_run_writes_sensitivity_file(tmp_path, tidy):
    from perinatal_ews.cli import main
    f = tmp_path / "t.csv"
    tidy.to_csv(f, index=False)
    main(["run", "--input", str(f), "--out", str(tmp_path / "s"), "--level", "state"])
    out = pd.read_csv(tmp_path / "s" / "unknown_sensitivity.csv", dtype={"geo_id": str, "state": str})
    assert len(out) and (out["geo_id"] == out["state"]).all()       # one row per state, not per county
    assert out["geo_id"].nunique() == tidy["state"].nunique()
    assert out["unknown"].notna().all()
