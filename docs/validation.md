# Validation

Every evaluation of perinatal-ews in one place: how often detection flags counties on historical data, how well it finds known changes on synthetic data, how accurate and well calibrated the next-year forecast is when tested forward in time, and how well the monthly full-year outlook predicted states' full-year results. Each section names the file its numbers come from, and `tests/test_validation_doc.py` checks the tables on this page against those files, so the page cannot drift from the published results.

| Evaluation | What it shows | Data | Source |
|---|---|---|---|
| [Alert rates on historical data](#alert-rates-on-historical-data) | Whether alert rates stay low and steady, and whether alerts last | US counties, 2021–2024 | `results/2024/backtest.csv` |
| [Detection on synthetic data](#detection-on-synthetic-data) | Sensitivity and false-alert rate against known injected changes | Synthetic demo, seed 7 | `perinatal-ews demo` |
| [Next-year forecast](#next-year-forecast) | Ranking, accuracy and calibration, forward in time | US counties, outcome years 2023 and 2024 | `results/2024/forecast_*.csv` |
| [Full-year outlook](#full-year-outlook) | Whether January–August predicts the full year for each state | US states, 2021–2025 | `results/latest/outlook_backtest.json` |
| [Held-out detection](#held-out-validation-of-detection) | Coverage of detection's predictive intervals | US counties, 2020–2024 | Under review |

## Alert rates on historical data

Each past year is scored as if it were the current year (`perinatal_ews.monitor.backtest`). On stable data, alert rates should stay low and steady; a jump with no known cause suggests a data problem. An alert "persists" if the county's z-score is still 1 or higher the next year.

| Year | County-indicators scored | Alerts | Watch | Alert rate | Alerts persisting next year |
|---|---|---|---|---|---|
| 2021 | 2,311 | 91 | 97 | 3.9% | 71% |
| 2022 | 2,311 | 78 | 105 | 3.4% | 73% |
| 2023 | 2,312 | 63 | 100 | 2.7% | 83% |
| 2024 | 2,312 | 97 | 101 | 4.2% | not yet known |

Alert rates are steady at 2.7–4.2% a year, and most alerts are still elevated the following year, so they are not mostly one-year noise. On real data some of these alerts are real changes and some are changes in recording; the backtest cannot tell the two apart (see [Interpreting a flag](interpreting_flags.md)).

## Detection on synthetic data

The demo (`perinatal-ews demo`, seed 7) generates 150 fictional counties over 2016–2024 and injects 14 known deteriorations that start in 2023, some only among Medicaid-paid births, then scores 2024. Because the truth is known, sensitivity and the false-alert rate can be measured (`perinatal_ews.monitor.evaluate_against_truth`). A false alert is an alert on a county-indicator with no injected change.

| | |
|---|---|
| Injected changes | 14 |
| Found (alert or watch) | 64% (9 of 14) |
| Found as alerts | 43% (6 of 14) |
| False alerts on unchanged county-indicators | 0.34% (2 of 586) |

By county size (births per year):

| County size | Injected changes | Found (alert or watch) | Found as alerts | False-alert rate |
|---|---|---|---|---|
| Large (5,000+ births) | 4 | 100% | 75% | 0.00% |
| Medium (1,000–5,000) | 7 | 57% | 43% | 0.31% |
| Small (under 1,000) | 3 | 33% | 0% | 0.76% |

Scored as if each earlier year were current, before any change was injected, the demo gives alert rates of 0.17% (2021) and 0% (2022), as a calibrated detector should. Weaker sensitivity in small counties is expected: one year of a few hundred births rarely carries enough signal, so small-county results should be read with several years of trend. Results vary by seed; the test suite checks the guarantees (false-alert rate under 1.5%, at least half of injected changes found, every large-county change found).

## Next-year forecast

The forecast predicts which county-indicators will be flagged (alert or watch) next year. It is tested forward in time: to predict year *y*, models are trained only on earlier outcome years. Details are in the [model card](model_card.md).

Pooled over outcome years 2023 and 2024 (4,624 county-indicator-years, 7–9% flagged):

| Model | AUROC | AUPRC | Brier | Precision, top 10% | Recall, top 10% |
|---|---|---|---|---|---|
| Gradient-boosted trees (selected) | 0.790 | 0.354 | 0.061 | 0.346 | 0.443 |
| Gradient-boosted trees + county context | 0.794 | 0.348 | 0.061 | 0.348 | 0.447 |
| Logistic regression on z-scores | 0.795 | 0.349 | 0.061 | 0.316 | 0.403 |
| Persistence (current z only) | 0.777 | 0.335 | 0.082 | 0.307 | 0.389 |

**Calibration.** County-indicators grouped into fifths by predicted risk, held-out years only (`forecast_calibration.csv`):

| Risk fifth | County-indicator-years | Mean predicted risk | Observed flag rate |
|---|---|---|---|
| 1 (lowest) | 925 | 0.4% | 1.3% |
| 2 | 925 | 1.2% | 3.1% |
| 3 | 924 | 2.4% | 4.4% |
| 4 | 925 | 5.0% | 6.6% |
| 5 (highest) | 925 | 24.8% | 23.6% |

The highest fifth, where most flags occur, is well calibrated; in the lower four fifths the model under-predicts by 1–2 percentage points, so a low forecast should not be read as "no risk".

**By county size** (`forecast_by_size.csv`):

| County size | County-indicator-years | AUROC | AUPRC | Next-year flag rate |
|---|---|---|---|---|
| Large (5,000+ births) | 1,273 | 0.838 | 0.424 | 7.3% |
| Medium (1,000–5,000) | 3,219 | 0.775 | 0.339 | 8.2% |
| Small (under 1,000) | 131 | 0.684 | 0.105 | 3.8% |

The forecast's ranking is close to the logistic baseline and better calibrated than persistence; it is least reliable for small counties, which also have the fewest examples.

## Full-year outlook

Each monthly update projects every state's full-year rate and the chance that the full year will be flagged. The backtest (`scripts/validate_outlook.py`) reruns the outlook for 2021–2025 using only January–August of each year and compares it with the full year's result.

| | |
|---|---|
| State-indicator-years | 1,020 |
| Full years flagged (alert or watch) | 73 (7.2%) |
| AUROC | 0.971 |
| AUPRC | 0.821 |
| Brier score | 0.029 |
| Precision, top 10% | 59% |
| Recall, top 10% | 82% |
| Sensitivity at a 50% chance | 75% |
| Precision at a 50% chance | 70% |
| 80% range contained the full-year rate | 84.5% |

For comparison, the year-so-far flag alone (flagged on January–August) found 68.5% of full-year flags with 73.5% precision (Brier 0.040). Every month's published outlook is saved in `results/history/` and will be scored once its year is complete.

## Held-out validation of detection

`perinatal_ews.holdout` and `scripts/validate_heldout.py` predict each county-year from 2020 on without using its own target-year count and check how often the actual count falls inside detection's 80%, 90% and 95% predictive intervals, and how the prediction error compares with simpler predictors (last year's rate, the county's own three-year rate, the rate of other counties). On synthetic data the coverage is close to nominal (`tests/test_holdout.py`). The results on the published 2016–2024 county data are being reviewed and will be added here; see the [roadmap](ROADMAP.md).

## Not yet validated

- How much missing or unknown items change the published flags: the code exists (`unknown_sensitivity.csv`), but the published data do not yet include unknown counts.
- Agreement with published state vital-records reports.
- Forecast and alert performance by rurality, payer mix and race and ethnicity mix.
- How drops in item completeness affect alerts.

These are listed in the [roadmap](ROADMAP.md).
