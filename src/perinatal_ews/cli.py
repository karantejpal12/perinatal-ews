"""Command-line interface.

    perinatal-ews demo --out out/
    perinatal-ews ingest-wonder --file preterm.txt --indicator preterm_birth --out data/preterm.csv
    perinatal-ews run --input data/tidy.csv --out out/ [--year 2024] [--config my.yaml]
                      [--forecast] [--context data/context/county_context.csv] [--level state]
    perinatal-ews pooled --input data/tidy.csv --out out/ [--level state] [--window 3]
                         [--unavailable-years 2017,2018] [--fill-window] [--combine groups.yaml]
    perinatal-ews mcp [--results path-or-url]
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
         title: str = "Perinatal Early Warning", source_note: str | None = None, with_forecast: bool = False,
         context_path: str | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    subgroups = sorted(set(tidy["subgroup"]) - {TOTAL_SUBGROUP})
    res = detect(tidy, cfg, target_year=year, subgroups=[TOTAL_SUBGROUP] + subgroups)
    res.to_csv(out / "detections.csv", index=False)
    state_clusters(res, tidy, cfg).to_csv(out / "state_patterns.csv", index=False)
    from .persistent import persistent_burden
    persistent_burden(tidy, cfg, end_year=year).to_csv(out / "persistent_burden.csv", index=False)
    if subgroups:
        subgroup_gaps(tidy, cfg, year).to_csv(out / "subgroup_gaps.csv", index=False)
    data_quality(tidy, year).to_csv(out / "data_quality.csv", index=False)
    from .anomaly import record_anomalies
    anomalies = record_anomalies(tidy)
    anomalies.to_csv(out / "data_anomalies.csv", index=False)
    distribution_drift(tidy, cfg, year).to_csv(out / "distribution_drift.csv", index=False)
    backtest(tidy, cfg).to_csv(out / "backtest.csv", index=False)
    if truth is not None:
        ev = evaluate_against_truth(tidy, cfg, truth, year)
        ev["summary"].to_csv(out / "evaluation_summary.csv", index=False)
        ev["by_size"].to_csv(out / "evaluation_by_size.csv", index=False)
        ev["cases"].to_csv(out / "evaluation_cases.csv", index=False)
    ctx = None
    if context_path:
        from .context import load_context
        ctx = load_context(context_path)
    fc = None
    if with_forecast:
        from .forecast import run_forecast
        fc = run_forecast(tidy, cfg, context=ctx)
        fc.scores.to_csv(out / "forecast_scores.csv", index=False)
        for name in ("metrics", "folds", "by_size", "by_indicator", "calibration", "importance", "feature_drift"):
            getattr(fc, name).to_csv(out / f"forecast_{name}.csv", index=False)
    na = bench = typ = None
    if ctx is not None:
        from .context import benchmark, need_access
        na = need_access(res, ctx, fc.scores if fc is not None else None,
                         labels={k: v["label"] for k, v in cfg["indicators"].items()})
        na.to_csv(out / "need_access.csv", index=False)
        bench = benchmark(tidy, ctx, cfg, year)
        bench[0].to_csv(out / "context_benchmark.csv", index=False)
        bench[1].to_csv(out / "context_benchmark_quality.csv", index=False)
        from .typology import county_typology
        typ = county_typology(tidy, ctx)
        typ[0].to_csv(out / "county_typology.csv", index=False)
        typ[1].to_csv(out / "typology_summary.csv", index=False)
        typ[2].to_csv(out / "typology_profiles.csv", index=False)
        import json
        (out / "typology_quality.json").write_text(json.dumps(typ[3], indent=2))
        if fc is not None:
            fc.metrics.to_csv(out / "forecast_metrics.csv", index=False)
    (out / "report.html").write_text(build_report(tidy, cfg, truth=truth, target_year=year, title=title,
                                                  source_note=source_note, forecast=fc, need_access=na,
                                                  benchmark=bench, typology=typ,
                                                  anomalies=anomalies))
    total = res[res["subgroup"] == TOTAL_SUBGROUP]
    print(f"Scored {total['geo_id'].nunique()} areas: "
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
    w.add_argument("--unknown-in-denominator", action="store_true",
                   help="count births with the item unknown or not stated as births without the outcome "
                        "(default: leave them out of the denominator; their count is kept in the 'unknown' column)")

    r = sub.add_parser("run", help="run detection on a tidy CSV")
    r.add_argument("--input", required=True, nargs="+", help="one or more tidy CSV files")
    r.add_argument("--out", default="out")
    r.add_argument("--year", type=int, default=None)
    r.add_argument("--config", default=None)
    r.add_argument("--title", default="Perinatal Early Warning")
    r.add_argument("--forecast", action="store_true", help="also train and evaluate the next-year ML forecast")
    r.add_argument("--source-note", default=None, help="one line on the data source, shown under the report title")
    r.add_argument("--context", default=None,
                   help="county context CSV (scripts/build_county_context.py): adds context to the forecast "
                        "and writes the need-versus-access review list")

    r.add_argument("--level", choices=["county", "state"], default="county",
                   help="state: sum county rows to states first (or use state-level input as is)")

    pl = sub.add_parser("pooled", help="multi-year pooled estimates, combining small groups (small-numbers analysis)")
    pl.add_argument("--input", required=True, nargs="+")
    pl.add_argument("--out", default="out")
    pl.add_argument("--level", choices=["county", "state", "as-is"], default="as-is",
                    help="state: sum county rows to states; as-is: use the input geography")
    pl.add_argument("--window", type=int, default=3, help="years per pooled window (default 3)")
    pl.add_argument("--unavailable-years", default="", help="comma-separated years with no data, e.g. 2017,2018")
    pl.add_argument("--fill-window", action="store_true",
                    help="reach further back to collect --window available years when some are missing")
    pl.add_argument("--min-events", type=int, default=20, help="events needed for a reliable estimate (NCHS: 20)")
    pl.add_argument("--combine", default=None,
                    help="YAML file mapping combined-group labels to lists of subgroups (default: federal-style combinations)")

    mc = sub.add_parser("mcp", help="serve the published results to AI assistants over MCP (read-only)")
    mc.add_argument("--results", default=None,
                    help="latest.json path or URL (default: this repository's copy, else the published file)")

    args = p.parse_args(argv)
    if args.cmd == "demo":
        cfg = load_config()
        tidy, truth = synthetic.generate(seed=args.seed)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        tidy.to_csv(out / "synthetic_tidy.csv", index=False)
        truth.to_csv(out / "synthetic_truth.csv", index=False)
        _run(tidy, cfg, out, None, truth, with_forecast=True)
    elif args.cmd == "ingest-wonder":
        cfg = load_config(args.config)
        tidy = wonder_to_tidy(args.file, args.indicator, cfg, subgroup_column=args.subgroup_column,
                             unknown_in_denominator=args.unknown_in_denominator)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        tidy.to_csv(args.out, index=False)
        others = tidy.attrs.get("non_case_categories", [])
        print(f"Wrote {len(tidy)} rows to {args.out}. Categories counted as non-cases: {others}")
    elif args.cmd == "pooled":
        _pooled(args)
    elif args.cmd == "mcp":
        from .mcp_server import main as mcp_main
        mcp_main(args.results)
    elif args.cmd == "run":
        cfg = load_config(args.config)
        tidy = pd.concat([load_tidy_csv(f) for f in args.input], ignore_index=True)
        if args.level == "state" and tidy["geo_id"].astype(str).str.len().eq(5).any():
            from .pooling import to_state
            tidy = to_state(tidy)
        _run(tidy, cfg, Path(args.out), args.year, None, args.title, args.source_note, args.forecast, args.context)


def _pooled(args) -> None:
    import yaml

    from .pooling import to_state

    tidy = pd.concat([load_tidy_csv(f) for f in args.input], ignore_index=True)
    if args.level == "state":
        tidy = to_state(tidy)
    unavailable = [int(y) for y in args.unavailable_years.split(",") if y.strip()]
    combine = yaml.safe_load(Path(args.combine).read_text()) if args.combine else None
    from .pooling import small_numbers_analysis
    p, c = small_numbers_analysis(tidy, window=args.window, unavailable_years=unavailable,
                                  fill_window=args.fill_window, combine=combine, min_events=args.min_events)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    p.to_csv(out / "pooled_estimates.csv", index=False)
    c.to_csv(out / "pooled_comparison.csv", index=False)
    latest = p[p["window_end"] == p["window_end"].max()]
    print(f"Pooled {args.window}-year windows: {len(p)} estimates; latest window "
          f"{latest['window'].iloc[0] if len(latest) else '-'}: {int((latest['status'] == 'reliable').sum())} reliable, "
          f"{int((latest['report_as'] == 'insufficient data').sum())} insufficient. Outputs in {out}/")


if __name__ == "__main__":
    main()
