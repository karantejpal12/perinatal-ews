"""The added maternal and child health indicators (`set: more` in the config).

Checks their definitions, the CDC WONDER filter check for NTSV cesarean, and that adding
them leaves every result for the original four indicators unchanged.
"""
import numpy as np
import pandas as pd
import pytest

from perinatal_ews import ingest, synthetic
from perinatal_ews.cli import _run
from perinatal_ews.config import core_indicators, load_config

CORE = ["late_no_prenatal_care", "preterm_birth", "low_birth_weight", "gestational_hypertension"]
MORE = ["no_first_trimester_care", "prepregnancy_obesity", "prepregnancy_overweight_obesity",
        "gestational_diabetes", "smoking_during_pregnancy", "ntsv_cesarean"]


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_definitions(cfg):
    assert core_indicators(cfg) == CORE
    for k in MORE:
        spec = cfg["indicators"][k]
        assert spec["set"] == "more"
        # Every indicator is framed so that higher is worse: a flag always means "worse than expected".
        assert spec["direction"] == "higher_is_worse"
        w = spec["wonder"]
        assert w["numerator_values"] and not set(w["numerator_values"]) & set(w["exclude_values"])
    labels = [v["label"] for v in cfg["indicators"].values()]
    assert len(labels) == len(set(labels))
    # Obesity is part of overweight-or-obesity.
    ob = set(cfg["indicators"]["prepregnancy_obesity"]["wonder"]["numerator_values"])
    ow = set(cfg["indicators"]["prepregnancy_overweight_obesity"]["wonder"]["numerator_values"])
    assert ob < ow
    # Late or no prenatal care is part of no first-trimester care.
    late = set(cfg["indicators"]["late_no_prenatal_care"]["wonder"]["numerator_values"])
    assert late < set(cfg["indicators"]["no_first_trimester_care"]["wonder"]["numerator_values"])


NTSV_BODY = '''"Notes"\t"County"\t"County Code"\t"Year"\t"Year Code"\t"Delivery Method"\t"Delivery Method Code"\t"Births"
\t"Middlesex County, MA"\t"25017"\t"2023"\t"2023"\t"Vaginal"\t"1"\t"3000"
\t"Middlesex County, MA"\t"25017"\t"2023"\t"2023"\t"Cesarean"\t"2"\t"1000"
\t"Middlesex County, MA"\t"25017"\t"2023"\t"2023"\t"Unknown or Not Stated"\t"9"\t"10"
"---"
"Dataset: Natality, 2016-2024 expanded"
"Query Parameters:"
'''
NTSV_FILTERS = '''"Live Birth Order: 1"
"Plurality: Single"
"Fetal Presentation: Cephalic"
"OE Gestational Age Recode 10: 37 - 39 weeks; 40 weeks; 41 weeks; 42 weeks or more"
'''
NTSV_TAIL = '''"Group By: County; Year; Delivery Method"
"Show Totals: Disabled"
"---"
"Help: See http://wonder.cdc.gov/wonder/help/Natality-expanded.html for more information."
'''


def test_ntsv_needs_a_filtered_export(tmp_path, cfg):
    ok = tmp_path / "ntsv.txt"
    ok.write_text(NTSV_BODY + NTSV_FILTERS + NTSV_TAIL)
    q = ingest.read_wonder_query(ok)
    assert q["Plurality"] == ["Single"] and q["Group By"] == ["County", "Year", "Delivery Method"]
    tidy = ingest.wonder_to_tidy(ok, "ntsv_cesarean", cfg)
    row = tidy.iloc[0]
    assert row["numerator"] == 1000 and row["denominator"] == 4000 and row["unknown"] == 10

    unfiltered = tmp_path / "all_births.txt"
    unfiltered.write_text(NTSV_BODY + NTSV_TAIL)
    with pytest.raises(ValueError, match="Live Birth Order"):
        ingest.wonder_to_tidy(unfiltered, "ntsv_cesarean", cfg)

    wrong = tmp_path / "preterm_too.txt"
    wrong.write_text(NTSV_BODY + NTSV_FILTERS.replace("37 - 39 weeks; ", "36 weeks; 37 - 39 weeks; ") + NTSV_TAIL)
    with pytest.raises(ValueError, match="OE Gestational Age Recode 10"):
        ingest.wonder_to_tidy(wrong, "ntsv_cesarean", cfg)


def test_unfiltered_indicators_ignore_the_footer(tmp_path, cfg):
    f = tmp_path / "gd.txt"
    f.write_text(NTSV_BODY.replace("Delivery Method", "Gestational Diabetes").replace('"Vaginal"', '"No"')
                 .replace('"Cesarean"', '"Yes"') + NTSV_TAIL)
    row = ingest.wonder_to_tidy(f, "gestational_diabetes", cfg).iloc[0]
    assert row["numerator"] == 1000 and row["denominator"] == 4000


def _with_more(tidy: pd.DataFrame, seed: int = 3) -> pd.DataFrame:
    """Synthetic rows for the added indicators, built from the core rows with new rates."""
    rng = np.random.default_rng(seed)
    base = tidy[tidy["indicator"] == "preterm_birth"].copy()
    extra = []
    for i, k in enumerate(MORE):
        d = base.copy()
        d["indicator"] = k
        p = np.clip(0.05 + 0.04 * i + rng.normal(0, 0.01, len(d)), 0.01, 0.6)
        d["numerator"] = rng.binomial(d["denominator"].fillna(0).astype(int), p).astype(float)
        d.loc[base["numerator"].isna().to_numpy(), "numerator"] = np.nan
        extra.append(d)
    return pd.concat([tidy, *extra], ignore_index=True)


def test_added_indicators_leave_core_results_unchanged(tmp_path, cfg):
    tidy, _ = synthetic.generate(n_counties=90, seed=5)
    a, b = tmp_path / "core", tmp_path / "all"
    _run(tidy, cfg, a, None, None, with_forecast=True)
    _run(_with_more(tidy), cfg, b, None, None, with_forecast=True)

    det_b = pd.read_csv(b / "detections.csv", dtype={"geo_id": str})
    assert set(det_b["indicator"]) == set(CORE) | set(MORE)
    det_a = pd.read_csv(a / "detections.csv", dtype={"geo_id": str})
    key = ["indicator", "subgroup", "geo_id"]
    pd.testing.assert_frame_equal(det_a.sort_values(key).reset_index(drop=True),
                                  det_b[det_b["indicator"].isin(CORE)].sort_values(key).reset_index(drop=True))
    for name in ("forecast_scores.csv", "forecast_metrics.csv", "backtest.csv", "data_anomalies.csv"):
        pd.testing.assert_frame_equal(pd.read_csv(a / name), pd.read_csv(b / name), obj=name)
    pb = pd.read_csv(b / "persistent_burden.csv")
    assert set(pb["indicator"]) == set(CORE) | set(MORE)


def test_explorer_carries_the_added_indicators(tmp_path, cfg):
    """build_explorer_data.py on synthetic results with the added indicators: schema, sets and no forecast for them."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    from test_explorer_schema import _consistency, _errors
    from test_pipeline import _synthetic_context
    from perinatal_ews.cli import main

    root = Path(__file__).resolve().parents[1]
    tidy, _ = synthetic.generate(seed=7)
    tidy = tidy[tidy["geo_id"].isin(tidy["geo_id"].drop_duplicates().head(60))].copy()
    tidy["state"] = tidy["state"].map({s: "Z" + chr(65 + i) for i, s in enumerate(sorted(tidy["state"].unique()))})
    tidy = _with_more(tidy)
    tidy.to_csv(tmp_path / "tidy.csv", index=False)
    _synthetic_context(tidy[tidy["indicator"].isin(CORE)]).to_csv(tmp_path / "context.csv")
    main(["run", "--input", str(tmp_path / "tidy.csv"), "--out", str(tmp_path / "res"), "--forecast",
          "--context", str(tmp_path / "context.csv")])
    subprocess.run([sys.executable, str(root / "scripts" / "build_explorer_data.py"), "--tidy", str(tmp_path / "tidy.csv"),
                    "--results", str(tmp_path / "res"), "--out", str(tmp_path / "e.json"),
                    "--context", str(tmp_path / "context.csv")], check=True, capture_output=True)
    d = json.loads((tmp_path / "e.json").read_text())
    assert _errors(d) == []
    _consistency(d)
    assert list(d["indicators"]) == CORE + MORE
    assert d["indicator_sets"] == {"core": CORE, "more": MORE}
    assert d["indicators"]["ntsv_cesarean"] == "Low-risk (NTSV) cesarean"
    assert set(d["persistent"]["persistent_counties"]) == set(CORE + MORE)
    c = d["counties"][0]
    assert "risk" in c["ind"]["preterm_birth"] and "risk" not in c["ind"]["gestational_diabetes"]
    assert "similar" in c["ind"]["gestational_diabetes"]


def test_caveats_match_the_explorer(cfg):
    """Every caveat in the config is shown word for word by the explorer and AI assistant (js/ews-tools.js)."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "js" / "ews-tools.js").read_text()
    for k, v in cfg["indicators"].items():
        if v.get("caveat"):
            assert f"{k}: '{v['caveat']}'" in js, k
