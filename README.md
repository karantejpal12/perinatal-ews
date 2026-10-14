# perinatal-ews

**Open-source early-warning analytics for county maternal and newborn health.**

`perinatal-ews` scans public natality data every year and flags counties where outcomes such as preterm birth, low birth weight, late or no prenatal care and gestational hypertension are getting worse than their own recent history predicts, after allowing for the trend seen across all counties. It is built for state and local health department epidemiologists, maternal and child health programmes, perinatal quality collaboratives and researchers who need to know *where to look first*.

It produces:

- a ranked list of **alerts** and **watch** flags, with rate, expected rate, excess cases and trend
- the same test run **within subgroups** (for example by payer or race and ethnicity), because a change confined to one group can be invisible in the county total
- **within-county equity gaps** between subgroups
- a **system health** check on every run: data completeness, distribution shift, a backtest of alert rates, and (on synthetic data) detection sensitivity by county size
- a self-contained HTML bulletin and CSV outputs

This is population surveillance to prompt a closer look by local teams. It is not a clinical tool and makes no statement about individual patients.

## Quick start

```bash
pip install -e .
perinatal-ews demo --out out/
open out/report.html
```

The demo generates synthetic data for 150 fictional counties (FIPS-style codes starting with 9, which no real county uses) over 2016–2024, injects 14 known deteriorations, runs the full pipeline and writes the bulletin.

## Using real data (CDC WONDER)

CDC WONDER natality data are free and public. You export one file per indicator.

1. Go to https://wonder.cdc.gov, choose **Births**, then the expanded natality database covering 2016 onward, and agree to the data use restrictions.
2. **Group results by:** `County`, then `Year`, then the indicator's category variable:

   | Indicator | Group-by variable (third) |
   |---|---|
   | `late_no_prenatal_care` | Month Prenatal Care Began |
   | `preterm_birth` | OE Gestational Age Recode 10 |
   | `low_birth_weight` | Infant Birth Weight 12 |
   | `gestational_hypertension` | Gestational Hypertension |

   Optional fourth group-by for subgroup analysis, such as Source of Payment for Delivery.
3. Select the years (at least 6 consecutive years; 8 or more is better) and the states you want.
4. Tick **Export results** and **Show totals**, then **Send**. Save the `.txt` file.
5. Convert and run:

```bash
perinatal-ews ingest-wonder --file preterm.txt --indicator preterm_birth --out data/preterm.csv
perinatal-ews ingest-wonder --file pnc.txt --indicator late_no_prenatal_care --out data/pnc.csv \
    --subgroup-column "Source of Payment for Delivery"
perinatal-ews run --input data/*.csv --out out/
```

`ingest-wonder` prints the categories it counted as non-cases. **Check them**: WONDER category labels differ between databases and years. Edit the `wonder` block in a copy of `src/perinatal_ews/default_config.yaml` and pass it with `--config` if anything is misassigned.

Things to know about WONDER county data:

- Counties with fewer than 100,000 residents are not shown individually; they are combined per state as "Unidentified Counties".
- Counts from 0 to 9 are suppressed. A suppressed cell makes that county-year unusable for that indicator rather than silently low.
- Follow the WONDER data use restrictions in anything you publish.

Any other source works too: convert it to the tidy schema in `src/perinatal_ews/schema.py` (one row per county, year, indicator and subgroup, with numerator and denominator) and use `run`.

## How detection works

See [docs/methodology.md](docs/methodology.md) for the full method. In short:

1. Each county's baseline is its pooled rate over 3 years, skipping the year just before the target so a change that started then is not absorbed into "normal".
2. Baselines are shrunk toward the all-county rate using an empirical-Bayes beta prior, so small counties are not judged on noise.
3. Expected rates are scaled by the change across all counties, so a national rise does not flag everyone.
4. The variance combines binomial noise, baseline uncertainty and extra year-to-year variation estimated from the data.
5. Alerts need a Benjamini–Hochberg q ≤ 0.05, a ratio ≥ 1.10 and at least 20 events (the NCHS reliability threshold). Watch flags need z ≥ 2 and a ratio ≥ 1.05.

## Validation on synthetic data (default demo, seed 7)

| | |
|---|---|
| Injected changes flagged (alert or watch) | 64% (9 of 14) |
| Flagged as alerts | 43% |
| False-alert rate on unchanged county-indicators | 0.34% (2 of 586) |
| Sensitivity, counties with 5,000+ births | 100% |
| Sensitivity, counties under 1,000 births | 33% |

Backtesting earlier years, before any injected change, gives alert rates of 0–0.2%, which is what a calibrated detector should show. The weaker sensitivity in small counties is real and reported on purpose: a single year of a few hundred births rarely carries enough signal, so small-county results should be read with multi-year trends. Results vary by seed; `pytest` checks the guarantees.

## Project layout

```
src/perinatal_ews/
  schema.py        tidy input schema and validation
  ingest.py        CDC WONDER export parser
  indicators.py    rates, Wilson intervals, NCHS reliability rules
  detect.py        early-warning engine
  equity.py        within-county subgroup gaps
  monitor.py       data quality, distribution drift, backtest, evaluation
  synthetic.py     fictional data with known injected changes
  report.py        HTML bulletin
  cli.py           command line
tests/             pytest suite
docs/              methodology
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Licence

MIT. See [LICENSE](LICENSE).

## Citation

If you use this software, please cite it. A Zenodo DOI will be added with the first tagged release.
