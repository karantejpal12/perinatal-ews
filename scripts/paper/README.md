# Analyses for the methods manuscript

These scripts produce every number in the manuscript draft. They read the published results in
`results/2024/` and the CDC WONDER county extract; they do not change any published result.

```
mkdir -p out/paper
cp <county tidy CSV from scripts/fetch_wonder_counties.js> out/paper/core_tidy.csv
python scripts/validate_heldout.py --tidy out/paper/core_tidy.csv --out out/paper
python scripts/paper/recalibrate.py      # held-out variance inflation (2020-2023), applied to 2024
python scripts/paper/paper_stats.py      # all other figures, including 20 synthetic replicates
```

- `recalibrate.py`: learns a variance inflation factor per indicator as the squared robust SD of held-out
  z-scores from 2020-2023, reports 2024 interval coverage before and after, and rescores the published 2024
  county results with z / sqrt(factor) under the same alert and watch rules. Writes `recalibration.json` and
  `recalibrated_2024.csv`.
- `paper_stats.py`: data description, flags by indicator, payer subgroups, state-wide patterns, persistent
  burden, backtest, forecast tables, and detection of injected changes over 20 synthetic replicates. Writes
  `paper_stats.json`.

The recalibration is an analysis for the paper; the live explorer still uses the published method.
