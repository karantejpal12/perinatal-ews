# Changelog

All notable changes to perinatal-ews. Each release is archived on Zenodo (concept DOI [10.5281/zenodo.23374046](https://doi.org/10.5281/zenodo.23374046)). Feedback from users and reviewers is tracked as [GitHub issues](https://github.com/karantejpal12/perinatal-ews/issues) and linked here.

## Unreleased

Changes in response to feedback from a state maternal and child health epidemiologist ([#1](https://github.com/karantejpal12/perinatal-ews/issues/1)):

- State-level analysis: `perinatal-ews run --level state` sums county rows to states; state-level input can be used directly.
- `perinatal-ews pooled`: multi-year pooled estimates. Unavailable, missing or suppressed years are skipped and reported, never treated as zero (`--unavailable-years 2017,2018`); `--fill-window` reaches further back to collect enough years.
- Small racial and ethnic groups are combined when they have too few events, using configurable combinations, and labelled as combined; results that are still too small are reported as "insufficient data".
- Comparison of the latest pooled window with the previous one, only when both estimates are reliable.
- Tests for state aggregation, pooling with a 2017–2018 gap, combining small groups and window comparison.

## 0.5.0 – 2026-10-14

- Interactive county map in the explorer.
- County types from unsupervised k-means clustering (silhouette-based k, bootstrap stability).
- Machine-learning data-quality check (Isolation Forest), validated on injected errors.
- Cross-conformal 90% prediction ranges for the similar-county comparison.
- `docs/ml_methods.md`.

## 0.4.0 – 2026-10-14

- "Ask perinatal-ews" AI assistant (LLM agent with six data tools and an automatic figure check).
- Rule-based plain-language county and state summaries.
- State view with every scored county side by side.

## 0.3.0 – 2026-10-14 · [10.5281/zenodo.23378773](https://doi.org/10.5281/zenodo.23378773)

- County context: CDC PLACES and ACS measures, CDC VSRR overdose deaths, SAMHSA treatment capacity, CMS labour-and-delivery hospitals.
- Cross-validated comparison with similar counties; need-versus-access review list.
- Context-aware forecast evaluation and per-county forecast explanations.

## 0.2.0 – 2026-10-14 · [10.5281/zenodo.23374647](https://doi.org/10.5281/zenodo.23374647)

- Results on real CDC WONDER county data (578 counties, 2016–2024) and state-wide pattern check.
- Next-year machine-learning forecast with forward-in-time validation and model card.
- Project site, Colab notebook, interactive explorer and in-browser analysis.

## 0.1.0 – 2026-10-14 · [10.5281/zenodo.23374047](https://doi.org/10.5281/zenodo.23374047)

- First release: county perinatal early-warning pipeline (empirical-Bayes detection, subgroup analysis, equity gaps, monitoring, synthetic validation, HTML bulletin).
