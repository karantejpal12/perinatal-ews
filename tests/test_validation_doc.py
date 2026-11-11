"""The tables in docs/validation.md match the published results files and the demo.

Each table on the validation page is parsed and compared, at the precision shown,
with the file it cites, so a rebuild that changes a result also has to update the page.
"""

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from perinatal_ews import config as cfgmod
from perinatal_ews import monitor, synthetic

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "docs" / "validation.md").read_text()
RESULTS = ROOT / "results"


def section(heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", PAGE, re.M | re.S)
    assert m, f"no section '{heading}' in validation.md"
    return m.group(1)


def tables(text: str) -> list[list[list[str]]]:
    """Every markdown table in text, as rows of cells, header and separator dropped."""
    out, cur = [], []
    for line in text.splitlines() + [""]:
        if line.startswith("|"):
            cur.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif cur:
            out.append([r for r in cur[2:]])
            cur = []
    return out


def num(cell: str) -> float:
    return float(re.match(r"[\d,.]+", cell).group(0).replace(",", ""))


def pct(x: float, digits: int = 0) -> str:
    return f"{x:.{digits}f}%"


def test_backtest_table_matches_published_file():
    bt = pd.read_csv(RESULTS / "2024" / "backtest.csv")
    rows = tables(section("Alert rates on historical data"))[0]
    assert [int(r[0]) for r in rows] == bt["year"].tolist()
    for r, b in zip(rows, bt.itertuples()):
        assert num(r[1]) == b.county_indicators_scored
        assert num(r[2]) == b.alerts and num(r[3]) == b.watches
        assert r[4] == pct(b.alert_rate_pct, 1)
        if pd.isna(b.alerts_persisting_next_year_pct):
            assert r[5] == "not yet known"
        else:
            assert r[5] == pct(b.alerts_persisting_next_year_pct)


def test_forecast_tables_match_published_files():
    text = section("Next-year forecast")
    metrics, calib, by_size = tables(text)
    m = pd.read_csv(RESULTS / "2024" / "forecast_metrics.csv")
    assert len(metrics) == len(m)
    for r in metrics:
        name = r[0].replace(" (selected)", "")
        row = m[m["model"].str.replace(" (perinatal-ews)", "", regex=False) == name]
        assert len(row) == 1, name
        row = row.iloc[0]
        assert ("(selected)" in r[0]) == bool(row["selected"])
        for cell, col in zip(r[1:], ["auroc", "auprc", "brier", "precision_top10pct", "recall_top10pct"]):
            assert cell == f"{row[col]:.3f}", (name, col)
    assert f"{int(m['n'].iloc[0] * 2):,} county-indicator-years" in text

    c = pd.read_csv(RESULTS / "2024" / "forecast_calibration.csv")
    assert len(calib) == len(c)
    for r, q in zip(calib, c.itertuples()):
        assert num(r[1]) == q.n
        assert r[2] == pct(100 * q.mean_predicted, 1) and r[3] == pct(100 * q.observed_rate, 1)

    s = pd.read_csv(RESULTS / "2024" / "forecast_by_size.csv")
    assert len(by_size) == len(s)
    for r, q in zip(by_size, s.itertuples()):
        assert num(r[1]) == q.n
        assert r[2] == f"{q.auroc:.3f}" and r[3] == f"{q.auprc:.3f}"
        assert r[4] == pct(100 * q.prevalence, 1)


def test_outlook_table_matches_published_backtest():
    o = json.loads((RESULTS / "latest" / "outlook_backtest.json").read_text())
    text = section("Full-year outlook")
    t = {r[0]: r[1] for r in tables(text)[0]}
    assert num(t["State-indicator-years"]) == o["state_indicators"]
    assert t["Full years flagged (alert or watch)"] == (
        f"{o['full_year_flags']} ({pct(100 * o['outlook']['prevalence'], 1)})")
    assert t["AUROC"] == f"{o['outlook']['auroc']:.3f}"
    assert t["AUPRC"] == f"{o['outlook']['auprc']:.3f}"
    assert t["Brier score"] == f"{o['outlook']['brier']:.3f}"
    assert t["Precision, top 10%"] == pct(100 * o["outlook"]["precision_top10pct"])
    assert t["Recall, top 10%"] == pct(100 * o["outlook"]["recall_top10pct"])
    assert t["Sensitivity at a 50% chance"] == pct(100 * o["outlook_at_50pct"]["sensitivity"])
    assert t["Precision at a 50% chance"] == pct(100 * o["outlook_at_50pct"]["precision"])
    assert t["80% range contained the full-year rate"] == pct(100 * o["interval80_coverage"], 1)
    ysf = o["year_so_far_flag"]
    assert (f"found {pct(100 * ysf['sensitivity'], 1)} of full-year flags with "
            f"{pct(100 * ysf['precision'], 1)} precision (Brier {o['brier_year_so_far_flag']:.3f})") in text
    assert f"{o['years'][0]}–{o['years'][-1]}" in text


@pytest.fixture(scope="module")
def demo():
    cfg = cfgmod.load_config()
    tidy, truth = synthetic.generate(seed=7)
    return cfg, tidy, monitor.evaluate_against_truth(tidy, cfg, truth)


def test_synthetic_tables_match_the_demo(demo):
    _, _, ev = demo
    text = section("Detection on synthetic data")
    summary, by_size = tables(text)
    s = ev["summary"].iloc[0]
    t = {r[0]: r[1] for r in summary}
    n = int(s["injected_changes"])
    found = round(s["found_as_alert_or_watch_pct"] * n / 100)
    alerts = round(s["found_as_alert_pct"] * n / 100)
    assert num(t["Injected changes"]) == n
    assert t["Found (alert or watch)"] == f"{pct(s['found_as_alert_or_watch_pct'])} ({found} of {n})"
    assert t["Found as alerts"] == f"{pct(s['found_as_alert_pct'])} ({alerts} of {n})"
    assert t["False alerts on unchanged county-indicators"] == (
        f"{pct(s['false_alert_rate_pct'], 2)} ({int(s['false_alerts'])} of {int(s['clean_county_indicators'])})")

    b = ev["by_size"].set_index("size_class")
    order = ["large (5k+)", "medium (1k-5k)", "small (<1k births)"]
    assert len(by_size) == len(b) == len(order)
    for r, key in zip(by_size, order):
        q = b.loc[key]
        assert num(r[1]) == q["injected"]
        assert r[2] == pct(q["found_as_alert_or_watch_pct"]) and r[3] == pct(q["found_as_alert_pct"])
        assert r[4] == pct(q["false_alert_rate_pct"], 2)


def test_synthetic_backtest_sentence_matches_the_demo(demo):
    cfg, tidy, _ = demo
    bt = monitor.backtest(tidy, cfg).set_index("year")["alert_rate_pct"]
    text = section("Detection on synthetic data")
    assert (f"alert rates of {bt[2021]:.2f}% (2021) and {bt[2022]:.0f}% (2022)") in text
