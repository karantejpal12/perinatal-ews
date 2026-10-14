"""Command-line interface.

    perinatal-ews demo --out out/
    perinatal-ews ingest-wonder --file preterm.txt --indicator preterm_birth --out data/preterm.csv
    perinatal-ews run --input data/tidy.csv --out out/ [--year 2024] [--config my.yaml]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import synthetic
from .config import load_config
from .detect import detect
from .equity import subgroup_gaps
from .ingest import load_tidy_csv, wonder_to_tidy
from .monitor import backtest, data_quality, distribution_drift, evaluate_against_truth, state_clusters
from .report import build_report
from .schema import TOTAL_SUBGROUP


def _run(tidy: pd.DataFrame, cfg: dict, out: Path, year: int | None, truth: pd.DataFrame | None,
         title: str = "Perinatal Early Warning", source_note: str | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    subgroups = sorted(set(tidy["subgroup"]) - {TOTAL_SUBGROUP})
    res = detect(tidy, cfg, target_year=year, subgroups=[TOTAL_SUBGROUP] + subgroups)
    res.to_csv(out / "detections.csv", index=False)
    state_clusters(res, tidy, cfg).to_csv(out / "state_patterns.csv", index=False)
    if subgroups:
        subgroup_gaps(tidy, cfg, year).to_csv(out / "subgroup_gaps.csv", index=False)
    data_quality(tidy, year).to_csv(out / "data_quality.csv", index=False)
    distribution_drift(tidy, cfg, year).to_csv(out / "distribution_drift.csv", index=False)
    backtest(tidy, cfg).to_csv(out / "backtest.csv", index=False)
    if truth is not None:
        ev = evaluate_against_truth(tidy, cfg, truth, year)
        ev["summary"].to_csv(out / "evaluation_summary.csv", index=False)
        ev["by_size"].to_csv(out / "evaluation_by_size.csv", index=False)
        ev["cases"].to_csv(out / "evaluation_cases.csv", index=False)
    (out / "report.html").write_text(build_report(tidy, cfg, truth=truth, target_year=year, title=title,
                                                            source_note=source_note))
    total = res[res["subgroup"] == TOTAL_SUBGROUP]
    print(f"Scored {total['geo_id'].nunique()} counties: "
          f"{int((total['level'] == 'alert').sum())} alerts, {int((total['level'] == 'watch').sum())} watch. "
          f"Outputs in {out}/")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="perinatal-ews", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="generate synthetic data and run the full pipeline")
    d.add_argument("--out", default="out")
    d.add_argument("--seed", type=int, default=7)

    w = sub.add_parser("ingest-wonder", help="convert a CDC WONDER natality export to the tidy schema")
    w.add_argument("--file", required=True)
    w.add_argument("--indicator", required=True)
    w.add_argument("--subgroup-column", default=None)
    w.add_argument("--config", default=None)
    w.add_argument("--out", required=True)

    r = sub.add_parser("run", help="run detection on a tidy CSV")
    r.add_argument("--input", required=True, nargs="+", help="one or more tidy CSV files")
    r.add_argument("--out", default="out")
    r.add_argument("--year", type=int, default=None)
    r.add_argument("--config", default=None)
    r.add_argument("--title", default="Perinatal Early Warning")
    r.add_argument("--source-note", default=None, help="one line on the data source, shown under the report title")

    args = p.parse_args(argv)
    if args.cmd == "demo":
        cfg = load_config()
        tidy, truth = synthetic.generate(seed=args.seed)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        tidy.to_csv(out / "synthetic_tidy.csv", index=False)
        truth.to_csv(out / "synthetic_truth.csv", index=False)
        _run(tidy, cfg, out, None, truth)
    elif args.cmd == "ingest-wonder":
        cfg = load_config(args.config)
        tidy = wonder_to_tidy(args.file, args.indicator, cfg, subgroup_column=args.subgroup_column)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        tidy.to_csv(args.out, index=False)
        others = tidy.attrs.get("non_case_categories", [])
        print(f"Wrote {len(tidy)} rows to {args.out}. Categories counted as non-cases: {others}")
    elif args.cmd == "run":
        cfg = load_config(args.config)
        tidy = pd.concat([load_tidy_csv(f) for f in args.input], ignore_index=True)
        _run(tidy, cfg, Path(args.out), args.year, None, args.title, args.source_note)


if __name__ == "__main__":
    main()
