# Model card: perinatal-ews next-year forecast

## Purpose

Predict, for each US county and indicator, the probability that next year's perinatal-ews detection will flag the county as worse than expected (z ≥ 2 in the harmful direction). The forecast helps health departments decide where to look early. It is population surveillance, not a clinical tool, and says nothing about individual patients.

## Model

- Gradient-boosted decision trees (scikit-learn `HistGradientBoostingClassifier`): 250 iterations, learning rate 0.05, at most 15 leaves per tree, at least 40 samples per leaf, L2 regularisation 1.0. Indicator is a categorical feature.
- One model covers all four indicators.
- Trained on county-years where the following year's outcome is known; refitted on all of them to score the latest year.
- **Validated fallback.** Each run compares the gradient-boosted model with a logistic regression on z-scores on held-out years and uses whichever has the higher average precision. On small or low-signal datasets (for example the bundled synthetic demo) the simpler model wins and is used; on the 2016–2024 US county data the gradient-boosted model is selected.

## Features (known at the end of year t)

| Feature | Meaning |
|---|---|
| `z`, `z_prev` | Detection z-score in year t and t−1 |
| `relative_risk` | Observed ÷ expected cases in year t |
| `logit_rate`, `logit_change_1y`, `logit_change_2y` | Rate on the logit scale and its change over 1 and 2 years |
| `apc` | Annual percent change in odds over all years to t |
| `logit_rate_vs_peer` | County rate relative to the all-county rate |
| `log_births` | County size |
| `medicaid_share` | Share of births paid by Medicaid |
| `medicaid_private_ratio` | Indicator rate for Medicaid births ÷ privately insured births |
| `state_change_vs_national` | State's change in rate since t−1 relative to the national change |
| `state_share_flagged` | Share of the state's counties flagged in year t |
| `peer_drift` | National change in the indicator relative to baseline |

## Evaluation

Rolling-origin, forward in time: to predict outcomes in year *y*, the model is trained only on outcome years before *y*. This matches how the system would have been used in practice and avoids leakage from the future.

It is compared with two baselines: logistic regression on `z` and `z_prev`, and persistence (risk is a logistic function of the current z only). Metrics: AUROC, average precision (AUPRC), Brier score, and precision and recall among the 10% highest-risk county-indicators. A 500-sample bootstrap gives a 95% interval for the AUPRC gain over the better baseline.

### Results on US county data (CDC WONDER, 578 counties, outcome years 2023 and 2024)

| Model | AUROC | AUPRC | Brier | Precision, top 10% | Recall, top 10% |
|---|---|---|---|---|---|
| Gradient-boosted trees | 0.790 | 0.354 | 0.061 | 0.346 | 0.443 |
| Logistic regression on z-scores | 0.795 | 0.349 | 0.061 | 0.316 | 0.403 |
| Persistence (current z) | 0.777 | 0.335 | 0.082 | 0.307 | 0.389 |

The base rate of next-year flags is 7–9%. The model's ranking is close to the logistic baseline: the bootstrap interval for the AUPRC gain includes zero in both years (−0.035 to +0.056 for 2023; −0.042 to +0.032 for 2024). It improves on persistence in calibration (Brier 0.061 vs 0.082) and finds somewhat more of next year's flags in its top 10%. The most important features are the current z-score, the one-year change and the relative risk; the Medicaid-to-private gap and the state trend add smaller amounts.

**Interpretation.** Most of the predictable signal for next year is already in this year's detection result. The machine-learning layer adds calibrated probabilities and modest gains in the highest-risk group, not a step change. This is reported as found.

### Performance by county size (pooled over both test years)

| County size | AUROC | AUPRC | Next-year flag rate |
|---|---|---|---|
| Large (5,000+ births) | 0.838 | 0.424 | 7.3% |
| Medium (1,000–5,000) | 0.775 | 0.339 | 8.2% |
| Small (<1,000) | 0.684 | 0.105 | 3.8% |

The model is least reliable for small counties, which also have the fewest examples (131 county-indicator-years). Small-county forecasts should be read with caution.

## Monitoring

Each run reports:

- **Calibration** by risk quintile (predicted vs observed rate).
- **Performance by county size and by indicator.**
- **Feature drift**: population stability index between the training years and the year being scored. Features with fewer than 20 distinct values are excluded.
- **Permutation importance** on held-out years.

When a new year of data arrives, the previous forecast can be scored against what happened and added to the evaluation, so performance is tracked over time.

## Limitations

- Only two held-out outcome years are available from 2016–2024 data; estimates will firm up as years are added.
- The outcome is defined by perinatal-ews detection, so forecast quality is bounded by detection quality, including any state reporting changes.
- County data cover only counties with 100,000+ residents (CDC WONDER restriction), which excludes most rural counties.
- 2020–2021 include pandemic effects on care and reporting.
- Features describe counties, not people. The model must not be used for individual decisions.

## Data use

CDC WONDER natality data, used under the NCHS data use restrictions. Counts under 10 are suppressed and excluded; no published output shows them.
