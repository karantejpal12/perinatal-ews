# perinatal-ews

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23383550.svg)](https://doi.org/10.5281/zenodo.23383550)
[![tests](https://github.com/karantejpal12/perinatal-ews/actions/workflows/tests.yml/badge.svg)](https://github.com/karantejpal12/perinatal-ews/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/karantejpal12/perinatal-ews/blob/main/notebooks/perinatal_ews_colab.ipynb)

**Try it:** [county map and explorer](https://karantejpal12.github.io/perinatal-ews/app.html) · [AI assistant](https://karantejpal12.github.io/perinatal-ews/app.html#ask) · [state view](https://karantejpal12.github.io/perinatal-ews/app.html#state-GA) · [project site](https://karantejpal12.github.io/perinatal-ews/) · [2024 bulletin](https://karantejpal12.github.io/perinatal-ews/results/2024/report.html)

**Open-source early-warning analytics for county maternal and newborn health.**

`perinatal-ews` scans public natality data every year and flags counties where outcomes such as preterm birth, low birth weight, late or no prenatal care and gestational hypertension are getting worse than their own recent history predicts, after allowing for the trend seen across all counties. It is built for state and local health department epidemiologists, maternal and child health programmes, perinatal quality collaboratives and researchers who need to know *where to look first*.

It produces:

- a ranked list of **alerts** and **watch** flags, with rate, expected rate, excess cases and trend
- the same test run **within subgroups** (for example by payer or race and ethnicity), because a change confined to one group can be invisible in the county total
- **within-county equity gaps** between subgroups
- a **next-year machine-learning forecast**: the probability that each county will be flagged for each indicator next year, including counties that look stable today, with forward-in-time validation against simpler baselines (see the [model card](docs/model_card.md))
- **county context** (v0.3): drug overdose deaths, opioid treatment capacity for pregnant and postpartum patients, hospitals with labour and delivery care, adult health and social conditions, from public CDC, SAMHSA and CMS data; a **cross-validated machine-learning comparison with similar counties**; and a **need-versus-access review list** (see [county context](docs/county_context.md))
- an **AI assistant** (v0.4) that answers questions about the results in plain language by calling the tool's own data functions, shows each lookup, and checks every figure in its answer against the data (see [AI assistant](docs/ai_assistant.md)); plus plain-language county and state summaries that need no AI model
- an **interactive county map** (v0.5) of 2024 status, forecast risk, similar-county comparison, county type, overdose deaths, need and access, and unusual data
- **more machine learning** (v0.5): county types from unsupervised clustering, an Isolation Forest data-quality check, and 90% conformal prediction ranges for the similar-county comparison; every learned component and its validation is listed in [ML and AI methods](docs/ml_methods.md)
- **monthly "this year so far" results for every state** (v0.7) from CDC provisional data, with the data date shown on the site
- **small-numbers analysis** (v0.6): state-level mode, multi-year pooling that skips and reports unavailable years, and combining of small racial and ethnic groups, labelled as combined; state results by mother's race for every state (see [small numbers](docs/small_numbers.md))
- a **state view** with every scored county side by side, state-wide patterns and the need-and-access list
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

Births with the item "Unknown or Not Stated" are left out of the denominator, and their number is kept in an `unknown` column of the tidy file. To count them as births without the outcome instead (for a sensitivity check), add `--unknown-in-denominator`.

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

- **Compared with similar counties.** A gradient-boosted model predicts each county's 2022–2024 rate from its context alone, with 5-fold cross-validation so no county is judged by a model that saw it. Context explains far more of the variation than the state average for low birth weight (cross-validated R² 0.61 vs 0.23) and preterm birth (0.55 vs 0.34), but not for gestational hypertension (0.22 vs 0.22), where differences between states, including how the item is recorded, dominate. 120 county-indicators are above the 90% prediction range for counties with similar conditions.
- **Need and access review list.** 122 counties have a perinatal warning sign together with a high drug overdose burden, thin treatment access for pregnant and postpartum patients, or thin delivery capacity. Six have both a top-quarter overdose rate and thin treatment access: King County WA, Madison County IN, Monroe County NY, Ascension Parish LA, Monroe County IN and Comanche County OK. 89 of the 578 counties have no listed facility that offers buprenorphine or methadone, accepts Medicaid and runs a programme for pregnant or postpartum patients.
- **Context in the forecast.** Tested as extra forecast inputs, county context did not clearly improve next-year prediction (AUPRC −0.006, 95% CI −0.033 to +0.024), so the forecast keeps the base model. County conditions explain where rates are high; recent changes in a county's own data explain which counties change next. Each forecast now lists its main factors.

Sources: CDC PLACES (BRFSS 2023) and ACS 2017–2021 measures, CDC VSRR provisional county overdose deaths 2020–2024, SAMHSA FindTreatment.gov listings, CMS Maternal Health – Hospital. To rebuild: run [`scripts/fetch_county_context.js`](scripts/fetch_county_context.js) in a browser on each site, then `python scripts/build_county_context.py` (needs `pip install shapely`). Methods and limitations: [docs/county_context.md](docs/county_context.md).

## Machine learning and AI at a glance

| Component | Method | Validated result on US data |
|---|---|---|
| Next-year forecast | Gradient-boosted trees | AUROC 0.790, AUPRC 0.354, forward in time |
| Similar-county comparison | Gradient-boosted regression, 5-fold CV | R² 0.61 vs 0.23 (low birth weight), 0.55 vs 0.34 (preterm) |
| Prediction ranges | Cross-conformal prediction | 90.1–90.5% coverage (target 90%) |
| County types | k-means clustering | 4 types, bootstrap ARI 0.78 |
| Data-quality check | Isolation Forest | 65–67% of injected single-indicator errors found (synthetic), 0.5% false flags |
| AI assistant | LLM agent with tool use | Every figure checked against the data |

Details: [docs/ml_methods.md](docs/ml_methods.md).

## Monthly updates: this year so far (v0.7)

County results use CDC's final data, which arrive about nine months after a year ends. To give earlier warning, perinatal-ews also uses CDC's provisional birth data, updated monthly with births through the previous month. Provisional data are available by state, so every month the tool compares each state's births from January to the latest complete month with the same months of earlier years, overall and by mother's race. The site shows exactly how current the data are; the first update covers **January–August 2026**.

Each update also gives a **full-year outlook** for every state: the projected rate for the whole year and the chance the full year will be flagged. Tested on 2021–2025 using only January–August of each year, it ranked the states whose full year was flagged with an AUROC of 0.97, and its 80% ranges contained the actual rate 85% of the time. Every month's outlook is saved and scored once the year is complete, so its track record is public.

How to run the monthly update: [docs/UPDATING.md](docs/UPDATING.md). Each month's results are kept in `results/history/`.

## Small numbers: state level, pooled years and combined groups (v0.6)

Built in response to feedback from a state maternal and child health epidemiologist ([#1](https://github.com/karantejpal12/perinatal-ews/issues/1)).

```bash
perinatal-ews run --input county_tidy.csv --level state --out out/            # state-level detection
perinatal-ews pooled --input state_race_tidy.csv --window 3 \
    --unavailable-years 2017,2018 --fill-window --out out/pooled/               # pooled, combined estimates
```

Pooled estimates skip and list unavailable or suppressed years (never counted as zero); small groups are reported through labelled combined groups or as "insufficient data". The explorer's state view shows pooled 2022–2024 results by mother's race for every state. Details and limitations: [docs/small_numbers.md](docs/small_numbers.md).

## AI assistant (v0.4)

The explorer's **Ask AI** tab is an AI agent built on Anthropic Claude with tool use. It answers questions such as "Which counties are high priority on the need-and-access list, and why?" by calling six data tools (`search_counties`, `get_county`, `list_counties`, `state_summary`, `national_summary`, `method_info`) that read the published results, so it works from the same numbers as the bulletin. Every lookup is shown, and after each answer every figure is checked against the data the assistant looked up; any figure that cannot be matched is listed for the reader to verify. The site has no server: the reader's own API key goes only from their browser to Anthropic. Without a key, each county and state page opens with a plain-language summary written by fixed rules from the data.

Design, guardrails and tests: [docs/ai_assistant.md](docs/ai_assistant.md). `node --test tests/js/ews-tools.test.js` runs the tool and figure-check tests.

**In your own AI assistant.** `perinatal-ews mcp` serves this year's state results and the full-year outlook to Claude Desktop, Claude Code or any other MCP client, read-only and on your own computer: ask "Which states are flagged for late prenatal care, and what should we check first?". Setup and guardrails: [docs/mcp_server.md](docs/mcp_server.md).

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
  context.py       county context, need-versus-access list, similar-county benchmark, conformal ranges
  typology.py      county types (clustering)
  anomaly.py       machine-learning data-quality check (Isolation Forest)
  pooling.py       state level, pooled years, combined groups (small numbers)
  latest.py        monthly state updates from CDC provisional data
  outlook.py       full-year outlook, backtest and scoring of saved outlooks
  synthetic.py     fictional data with known injected changes
  report.py        HTML bulletin
  cli.py           command line
js/                AI assistant (assistant.js) and its data tools, briefs and figure check (ews-tools.js)
scripts/           CDC WONDER and county context fetch and build scripts
data/context/      county_context.csv (public county context table)
results/2024/      outputs on real 2016–2024 US county data
tests/             pytest suite
docs/              methodology, model card, ML and AI methods, county context, AI assistant
results/map/       simplified county and state outlines for the map
```

## Development

```bash
pip install -e ".[dev]"
pytest
node --test tests/js/ews-tools.test.js
```

Both test suites run automatically on every change ([GitHub Actions](https://github.com/karantejpal12/perinatal-ews/actions/workflows/tests.yml)). Planned work is listed in the [roadmap](docs/ROADMAP.md).

## Licence

MIT. See [LICENSE](LICENSE).

## Citation

If you use this software, please cite it:

> Tejpal, K. (2026). *perinatal-ews: open-source early-warning analytics for county maternal and newborn health* (Version 0.8.0) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.23383550

GitHub's "Cite this repository" button gives this in other formats. The software is archived on Zenodo: [v0.8.0](https://doi.org/10.5281/zenodo.23383550) · [v0.7.0](https://doi.org/10.5281/zenodo.23383246) · [v0.6.0](https://doi.org/10.5281/zenodo.23381196) · [v0.5.0](https://doi.org/10.5281/zenodo.23380220) · [v0.3.0](https://doi.org/10.5281/zenodo.23378773) · [v0.2.0](https://doi.org/10.5281/zenodo.23374647) · [v0.1.0](https://doi.org/10.5281/zenodo.23374047). To cite all versions, use the concept DOI [10.5281/zenodo.23374046](https://doi.org/10.5281/zenodo.23374046), which always resolves to the latest release.

## Author

Karan Tejpal · [ORCID 0009-0004-8609-2854](https://orcid.org/0009-0004-8609-2854)
