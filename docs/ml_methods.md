# Machine learning and AI in perinatal-ews

A summary of every learned or AI component, what it is for, how it was validated, and its results on the 2016–2024 US county data (578 counties with 100,000+ residents). Detection itself is statistical modelling (empirical-Bayes shrinkage, overdispersion, false-discovery control), described in [methodology.md](methodology.md).

| Component | Method | Purpose | Validation | Result on US data |
|---|---|---|---|---|
| Next-year forecast | Gradient-boosted trees (supervised classification) | Probability each county is flagged next year | Rolling-origin, forward in time, against logistic regression and persistence; bootstrap CI; calibration; accuracy by county size | AUROC 0.790, AUPRC 0.354, Brier 0.061 ([model card](model_card.md)) |
| Forecast explanations | Occlusion attribution | Main factors behind each county's risk | Shown as approximate | — |
| Similar-county comparison | Gradient-boosted trees (supervised regression), 5-fold cross-validation | Expected rate for a county given its health, social and access context | Cross-validated R² against a state-average baseline | R² 0.61 vs 0.23 (low birth weight), 0.55 vs 0.34 (preterm) |
| Prediction ranges | Cross-conformal prediction, normalised residuals | 90% range for "counties like this one"; outside = higher or lower than similar | Empirical coverage on held-out folds | 90.1–90.5% (target 90%) |
| County types | k-means clustering (unsupervised) | Peer groups of counties | Silhouette for k = 4–8; 50 bootstrap resamples, adjusted Rand index | 4 types; ARI 0.78; silhouette 0.15 |
| Data-quality check | Isolation Forest (unsupervised anomaly detection) | Unusual county-year records that may be data errors | Injected errors in synthetic data, against the births-change rule | Found 65–67% of single-indicator errors the rule misses; 0.5% false flags |
| Full-year outlook (states) | Empirical-Bayes seasonal model, simulation through detection | Chance the current year will be flagged, and projected full-year rate | Backtest 2021–2025 with only January–August known; each monthly outlook saved and scored when the year ends | AUROC 0.97, Brier 0.029 (0.040 for "flagged so far"); 80% ranges covered 85% |
| AI assistant | Large language model agent with tool use | Plain-language answers to questions about the results | Grounding in tool results; automatic figure check; JavaScript tests | See [ai_assistant.md](ai_assistant.md) |

## County types (clustering)

`typology.py`. Each county is described by its recent (2022–2024) level of the four indicators (log-odds), its size (log births), adult high blood pressure, obesity, diabetes and smoking, uninsured adults, poverty, no high-school diploma, single-parent households, no broadband, the 2024 overdose death rate (log) and MOUD access for pregnant patients per 1,000 births (log). Features are standardised and clipped at ±4 standard deviations. k-means is fitted for k = 4 to 8 and the k with the best mean silhouette is kept. Each type is described by the features on which its average differs most from all counties.

| Type | Counties | What sets it apart |
|---|---|---|
| 1 | 228 | Close to average on most measures |
| 2 | 171 | Larger; lower adult smoking and obesity |
| 3 | 117 | Higher adult high blood pressure, low birth weight and adult diabetes |
| 4 | 62 | Higher share of uninsured adults and adults without a high-school diploma, higher adult diabetes; lower gestational hypertension and lower MOUD access for pregnant patients |

Stability: re-clustering 50 bootstrap resamples agrees with the full-data clustering with a median adjusted Rand index of 0.78 (10th percentile 0.58). Including 2016–2024 trends made the groups less stable (0.70), so trends are left to detection. The silhouette of 0.15 shows that counties lie on a continuum: the types are a useful summary, not natural categories.

## Data-quality check (anomaly detection)

`anomaly.py`. Every county-year record is described by log births, the change in births, and for each indicator the rate, its change from the year before and its distance from the county's own median, with changes divided by their sampling standard error. An Isolation Forest (400 trees) flags the 2% least typical records and lists the features that make each one unusual.

Validation on synthetic data, averaged over five datasets with 15 injected errors of each kind:

| Injected error | Found by model | Found by births-change rule |
|---|---|---|
| Half the births missing (rates unchanged) | 3% | 100% |
| One category collapsed (rate × 0.15) | 65% | 0% |
| One indicator spiking (rate × 2.5) | 67% | 4% |
| False flags on clean records | 0.5% | 0.1% |

The two checks are complementary and both run on every analysis. On the US data, 20 records in 2024 were flagged. Most are large counties with a sharp rise in late or no prenatal care, which also appear as alerts. The check cannot tell a data error from a real change; it marks records to verify with the data provider, which is particularly useful where a state-wide recording change is possible (Georgia, for example).

## Prediction ranges (conformal prediction)

In `context.benchmark`, residuals of the cross-validated model are normalised by each county's expected spread (sampling variance of its rate plus the variation the model does not explain). For each fold, the 90% quantile of the normalised residuals from the *other* folds sets the width of the range, so a county's range never uses its own residual. A county is "higher than similar counties" if its rate is above the range. Empirical coverage on the US data was 90.1% to 90.5% across the four indicators; 120 county-indicators are above their range and 104 below.

## What is not claimed

- No component makes causal claims; county context and types describe places, not people.
- County context did not improve the next-year forecast and is not used in it (see the model card).
- The data-quality check and the forecast are aids for prioritising review, not decisions.
