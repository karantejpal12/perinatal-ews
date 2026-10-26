import numpy as np
import pandas as pd
import pytest

from perinatal_ews import config as cfgmod
from perinatal_ews import synthetic
from perinatal_ews.detect import detect
from perinatal_ews.missing import unknown_as_cases, unknown_in_denominator, unknown_sensitivity
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


WONDER_ECLAMPSIA = '''"Notes"\t"County"\t"County Code"\t"Year"\t"Gestational Hypertension"\t"Eclampsia"\t"Births"
\t"A County, MA"\t"25001"\t"2023"\t"Yes"\t"No"\t"95"
\t"A County, MA"\t"25001"\t"2023"\t"Yes"\t"Yes"\t"Suppressed"
\t"A County, MA"\t"25001"\t"2023"\t"Unknown or Not Stated"\t"Yes"\t"12"
\t"A County, MA"\t"25001"\t"2023"\t"Unknown or Not Stated"\t"No"\t"38"
\t"B County, MA"\t"25003"\t"2023"\t"Unknown or Not Stated"\t"Yes"\t"Suppressed"
\t"C County, MA"\t"25005"\t"2023"\t"Unknown or Not Stated"\t"No"\t"20"
\t"C County, MA"\t"25005"\t"2023"\t"Not Reported"\t"Yes"\t"15"
"---"
'''


def test_wonder_unknown_as_case_counts(tmp_path, cfg):
    from perinatal_ews.ingest import wonder_unknown_as_case
    f = tmp_path / "gh_ecl.txt"
    f.write_text(WONDER_ECLAMPSIA)
    out = wonder_unknown_as_case(f, "gestational_hypertension", cfg).set_index("geo_id")["unknown_as_case"]
    assert out["25001"] == 12          # suppression in other cells does not matter
    assert np.isnan(out["25003"])      # the cell itself is suppressed
    assert out["25005"] == 0           # no such cell; "Not Reported" is not unknown
    with pytest.raises(ValueError, match="unknown_as_case"):
        wonder_unknown_as_case(f, "preterm_birth", cfg)


def test_unknown_as_cases_only_changes_rule_indicators(cfg):
    t = pd.DataFrame({"indicator": ["gestational_hypertension", "gestational_hypertension", "preterm_birth"],
                      "numerator": [10.0, 10.0, 10.0], "denominator": [100.0, 100.0, 100.0],
                      "unknown_as_case": [3.0, np.nan, 5.0]})
    alt = unknown_as_cases(t, cfg)
    assert alt.at[0, "numerator"] == 13 and alt.at[0, "denominator"] == 103
    assert np.isnan(alt.at[1, "numerator"])                         # missing count: unusable
    assert alt.at[2, "numerator"] == 10 and alt.at[2, "denominator"] == 100
    with pytest.raises(ValueError, match="unknown_as_case"):
        unknown_as_cases(t.drop(columns="unknown_as_case"), cfg)


def test_sensitivity_reports_eclampsia_variant(cfg, tidy):
    year = int(tidy["year"].max())
    base = detect(tidy, cfg)
    gh = base[(base["indicator"] == "gestational_hypertension") & (base["level"] == "stable")].iloc[0]
    t = tidy.copy()
    t["unknown_as_case"] = np.where(t["indicator"] == "gestational_hypertension", 0.0, np.nan)
    row = (t["geo_id"] == gh["geo_id"]) & (t["indicator"] == "gestational_hypertension") & (t["year"] == year)
    # Many births with the item unknown but eclampsia checked in the target year only.
    t.loc[row, "unknown_as_case"] = (t.loc[row, "denominator"] * 0.5).round()
    sens = unknown_sensitivity(t, cfg)
    assert {"unknown_as_case", "level_as_case", "changed_as_case", "change_as_case"} <= set(sens.columns)
    r = sens.set_index(["indicator", "geo_id"]).loc[("gestational_hypertension", gh["geo_id"])]
    assert r["changed_as_case"] and r["change_as_case"] == "stable -> alert"
    assert sens.iloc[0]["changed_as_case"]                          # listed first
    other = sens[sens["indicator"] != "gestational_hypertension"]
    assert other["level_as_case"].isna().all() and not other["changed_as_case"].any()
    # With no such births anywhere, the variant reproduces the default exactly.
    zero = unknown_sensitivity(t.assign(unknown_as_case=t["unknown_as_case"] * 0), cfg)
    g = zero[zero["indicator"] == "gestational_hypertension"]
    assert (g["level_as_case"].astype(str) == g["level_excluded"].astype(str)).all()
    assert not zero["changed_as_case"].any()
    # Without the column the output is as before.
    assert "level_as_case" not in unknown_sensitivity(tidy, cfg).columns


def test_ingest_cli_adds_unknown_as_case_and_state_sums_it(tmp_path):
    from perinatal_ews.cli import main
    from perinatal_ews.pooling import to_state
    main_file = tmp_path / "gh.txt"
    main_file.write_text('"Notes"\t"County"\t"County Code"\t"Year"\t"Gestational Hypertension"\t"Births"\n'
                         '\t"A County, MA"\t"25001"\t"2023"\t"Yes"\t"100"\n'
                         '\t"A County, MA"\t"25001"\t"2023"\t"No"\t"850"\n'
                         '\t"A County, MA"\t"25001"\t"2023"\t"Unknown or Not Stated"\t"50"\n'
                         '\t"C County, MA"\t"25005"\t"2023"\t"Yes"\t"30"\n'
                         '\t"C County, MA"\t"25005"\t"2023"\t"No"\t"400"\n'
                         '\t"C County, MA"\t"25005"\t"2023"\t"Unknown or Not Stated"\t"20"\n"---"\n')
    ecl = tmp_path / "gh_ecl.txt"
    ecl.write_text(WONDER_ECLAMPSIA.replace('\t"B County, MA"\t"25003"\t"2023"\t"Unknown or Not Stated"\t"Yes"\t"Suppressed"\n', ""))
    out = tmp_path / "t.csv"
    main(["ingest-wonder", "--file", str(main_file), "--indicator", "gestational_hypertension",
          "--unknown-as-case-file", str(ecl), "--out", str(out)])
    t = pd.read_csv(out, dtype={"geo_id": str}).set_index("geo_id")
    assert t.at["25001", "unknown_as_case"] == 12 and t.at["25005", "unknown_as_case"] == 0
    assert t.at["25001", "denominator"] == 950                       # default rates unchanged
    st = to_state(t.reset_index())
    assert st["unknown_as_case"].tolist() == [12] and st["unknown"].tolist() == [70]
    with pytest.raises(SystemExit):
        main(["ingest-wonder", "--file", str(main_file), "--indicator", "gestational_hypertension",
              "--unknown-as-case-file", str(ecl), "--unknown-in-denominator", "--out", str(out)])
