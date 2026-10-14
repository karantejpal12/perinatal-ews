# perinatal-ews

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23378773.svg)](https://doi.org/10.5281/zenodo.23378773)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/karantejpal12/perinatal-ews/blob/main/notebooks/perinatal_ews_colab.ipynb)

**Try it:** [county explorer and in-browser tool](https://karantejpal12.github.io/perinatal-ews/app.html) · [project site](https://karantejpal12.github.io/perinatal-ews/) · [2024 bulletin](https://karantejpal12.github.io/perinatal-ews/results/2024/report.html)

**Open-source early-warning analytics for county maternal and newborn health.**

`perinatal-ews` scans public natality data every year and flags counties where outcomes such as preterm birth, low birth weight, late or no prenatal care and gestational hypertension are getting worse than their own recent history predicts, after allowing for the trend seen across all counties. It is built for state and local health department epidemiologists, maternal and child health programmes, perinatal quality collaboratives and researchers who need to know *where to look first*.

It produces:

- a ranked list of **alerts** and **watch** flags, with rate, expected rate, excess cases and trend
- the same test run **within subgroups** (for example by payer or race and ethnicity), because a change confined to one group can be invisible in the county total
- **within-county equity gaps** between subgroups
- a **next-year machine-learning forecast**: the probability that each county will be flagged for each indicator next year, including counties that look stable today, with forward-in-time validation against simpler baselines (see the [model card](docs/model_card.md))
- **county context** (v0.3): drug overdose deaths, opioid treatment capacity for pregnant and postpartum patients, hospitals with labour and delivery care, adult health and social conditions, from public CDC, SAMHSA and CMS data; a **cross-validated machine-learning comparison with similar counties**; and a **need-versus-access review list** (see [county context](docs/county_context.md))
- a **system health** check on every run: data completeness, distribution shift, a backtest of alert rates, and (on synthetic data) detection sensitivity by county size
- a self-contained HTML bulletin and CSV outputs

This is population surveillance to prompt a closer look by local teams. It is not a clinical tool and makes no statement about individual patients.

## Quick start

No install needed: open the [Colab notebook](https://colab.research.google.com/github/karantejpal12/perinatal-ews/blob/main/notebooks/perinatal_ews_colab.ipynb) to view the 2024 results, run the demo, or upload your own data.

On your own machine:

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
perinatal-ews run --input data/*.csv --out out/ --forecast --context data/context/county_context.csv
```

`ingest-wonder` prints the categories it counted as non-cases. **Check them**: WONDER category labels differ between databases and years. Edit the `wonder` block in a copy of `src/perinatal_ews/default_config.yaml` and pass it with `--config` if anything is misassigned.

Things to know about WONDER county data:

- Counties with fewer than 100,000 residents are not shown individually; they are combined per state as "Unidentified Counties".
- Counts from 0 to 9 are suppressed. A suppressed cell makes that county-year unusable for that indicator rather than silently low.
- Follow the WONDER data use restrictions in anything you publish.

Any other source works too: convert it to the tidy schema in `src/perinatal_ews/schema.py` (one row per county, year, indicator and subgroup, with numerator and denominator) and use `run`.

## First results on real data: US counties, 2024

Run on CDC WONDER natality data for the 578 US counties with 100,000+ residents (2016–2024, about 80% of US births). Full outputs are in [`results/2024/`](results/2024/), including the bulletin `report.html`.

| Indicator | Alerts | Watch | Counties scored |
|---|---|---|---|
| Gestational hypertension | 65 | 30 | 578 |
| Late or no prenatal care | 23 | 22 | 578 |
| Preterm birth | 9 | 28 | 578 |
| Low birth weight | 0 | 21 | 578 |

Findings the tool surfaced:

- **State-wide patterns.** Flags cluster by state: gestational hypertension in Pennsylvania (15 of 31 counties flagged), South Carolina and Hawaii, and late or no prenatal care in Georgia (11 of 24), where the state rate rose from about 9% to 12.5% in 2024. Clusters like these can be real state-wide changes or changes in how a state records a birth-certificate item; the bulletin lists them separately so they can be checked with the state vital records office before being read as local problems.
- **Subgroups add signal.** Running the test within Medicaid and privately insured births produced 144 subgroup alerts, including changes that were too diluted to show in the county total.
- **Self-monitoring.** Gestational hypertension shows a major distribution shift (stability index 0.33) because it has risen nationally from 5.8% to 10.2% since 2016; detection adjusts for this national trend. The backtest gives alert rates of 2.7–4.2% per year for 2021–2024, and 71–83% of alerts stay elevated the next year.

These are statistical flags for follow-up, not confirmed problems. Each needs local review.

To reproduce, run [`scripts/fetch_wonder_counties.js`](scripts/fetch_wonder_counties.js) in your browser on the CDC WONDER request form (instructions in the file), then `perinatal-ews run`.

## Next-year forecast (machine learning)

`perinatal-ews run --forecast` trains a gradient-boosted tree model that predicts which counties will be flagged next year. It uses each county's recent rates and trend, detection scores, size, Medicaid share, Medicaid-to-private gap and state-wide trends. It is validated forward in time (trained only on earlier years for each held-out year) against a logistic regression on z-scores and a persistence baseline, and each run uses whichever trainable method has the better held-out average precision.

On the US county data (held-out outcome years 2023 and 2024; next-year flag rate 7–9%):

| Method | AUROC | AUPRC | Brier |
|---|---|---|---|
| Gradient-boosted trees (selected) | 0.790 | 0.354 | 0.061 |
| Logistic regression on z-scores | 0.795 | 0.349 | 0.061 |
| Persistence (current z only) | 0.777 | 0.335 | 0.082 |

The model's ranking is close to the logistic baseline (the bootstrap interval for the AUPRC gain includes zero), and it is better calibrated than persistence. Most of the predictable signal for next year is already in this year's detection result; the forecast adds calibrated probabilities and surfaces counties that are **stable today but high-risk for 2025**, such as gestational hypertension in Columbia County, GA (64%). Accuracy is highest for large counties (AUROC 0.84) and lowest for small ones (0.68). Details, limitations and monitoring are in the [model card](docs/model_card.md).

## County context: substance use, maternity care access and social conditions (v0.3)

`perinatal-ews run --context data/context/county_context.csv` joins public county data to the results. Every measure describes a place, not a person.

- **Compared with similar counties.** A gradient-boosted model predicts each county's 2022–2024 rate from its context alone, with 5-fold cross-validation so no county is judged by a model that saw it. Context explains far more of the variation than the state average for low birth weight (cross-validated R² 0.61 vs 0.23) and preterm birth (0.55 vs 0.34), but not for gestational hypertension (0.22 vs 0.22), where differences between states, including how the item is recorded, dominate. 106 county-indicators are higher than counties with similar conditions.
- **Need and access review list.** 122 counties have a perinatal warning sign together with a high drug overdose burden, thin treatment access for pregnant and postpartum patients, or thin delivery capacity. Six have both a top-quarter overdose rate and thin treatment access: King County WA, Madison County IN, Monroe County NY, Ascension Parish LA, Monroe County IN and Comanche County OK. 89 of the 578 counties have no listed facility that offers buprenorphine or methadone, accepts Medicaid and runs a programme for pregnant or postpartum patients.
- **Context in the forecast.** Tested as extra forecast inputs, county context did not clearly improve next-year prediction (AUPRC −0.006, 95% CI −0.033 to +0.024), so the forecast keeps the base model. County conditions explain where rates are high; recent changes in a county's own data explain which counties change next. Each forecast now lists its main factors.

Sources: CDC PLACES (BRFSS 2023) and ACS 2017–2021 measures, CDC VSRR provisional county overdose deaths 2020–2024, SAMHSA FindTreatment.gov listings, CMS Maternal Health – Hospital. To rebuild: run [`scripts/fetch_county_context.js`](scripts/fetch_county_context.js) in a browser on each site, then `python scripts/build_county_context.py` (needs `pip install shapely`). Methods and limitations: [docs/county_context.md](docs/county_context.md).

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
  monitor.py       data quality, distribution drift, state patterns, backtest, evaluation
  forecast.py      next-year ML forecast, validation, explanations and monitoring
  context.py       county context, need-versus-access list, similar-county benchmark
  synthetic.py     fictional data with known injected changes
  report.py        HTML bulletin
  cli.py           command line
scripts/           CDC WONDER and county context fetch and build scripts
data/context/      county_context.csv (public county context table)
results/2024/      outputs on real 2016–2024 US county data
tests/             pytest suite
docs/              methodology, model card and county context
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Licence

MIT. See [LICENSE](LICENSE).

## Citation

If you use this software, please cite it:

> Tejpal, K. (2026). *perinatal-ews: open-source early-warning analytics for county maternal and newborn health* (Version 0.3.0) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.23378773

GitHub's "Cite this repository" button gives this in other formats. The software is archived on Zenodo: [v0.3.0](https://doi.org/10.5281/zenodo.23378773) · [v0.2.0](https://doi.org/10.5281/zenodo.23374647) · [v0.1.0](https://doi.org/10.5281/zenodo.23374047). To cite all versions, use the concept DOI [10.5281/zenodo.23374046](https://doi.org/10.5281/zenodo.23374046), which always resolves to the latest release.

## Author

Karan Tejpal · [ORCID 0009-0004-8609-2854](https://orcid.org/0009-0004-8609-2854)
