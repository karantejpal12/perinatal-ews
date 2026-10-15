# Changelog

All notable changes to perinatal-ews. Each release is archived on Zenodo (concept DOI [10.5281/zenodo.23374046](https://doi.org/10.5281/zenodo.23374046)). Feedback from users and reviewers is tracked as [GitHub issues](https://github.com/karantejpal12/perinatal-ews/issues) and linked here.

## 0.8.0 – 2026-10-15

- Full-year outlook (`perinatal_ews.outlook`): for every state and indicator, a projected full-year rate with an 80% range and the chance that the whole year will be flagged, from the months known so far and how each state's year usually ends (empirical-Bayes seasonal step, simulated remaining months, standard detection on each simulation).
- Backtested on 2021–2025 using only January–August of each year: AUROC 0.97, Brier score 0.029 (0.040 for "flagged so far"), 80% ranges contained the actual full-year rate 85% of the time.
- Each monthly update saves its outlook in `results/history/<YYYY-MM>/outlook.csv`; outlooks are scored automatically once their year is complete.
- Clearer explorer: every map option and section states the period and geography it covers (this year by state, 2024 by county, 2025 county forecast); map title and period label; "how to use" steps; filter reset; state view in two blocks ("Now" and "2024 in detail") with the race tables folded away.

## 0.7.0 – 2026-10-15

Monthly updates from CDC provisional data:

- `perinatal_ews.latest`: "this year so far" detection for every state, comparing January to the latest complete month with the same months of earlier years; full-year scoring of the latest provisional year (2025); comparison by mother's race with the same months of the three previous years.
- Completeness check: the latest month is used only if its births are at least 97% of what earlier months suggest.
- The explorer and home page show how current the data are (state results through August 2026, retrieved 14 October 2026; county results 2016–2024 final). The state view has a "so far" section, and the map can colour states by their status this year.
- Monthly routine: `scripts/fetch_wonder_latest.js`, `scripts/update_latest.py` and `docs/UPDATING.md`; each update is kept in `results/history/<YYYY-MM>/`.
- Final state baseline for January-to-month windows, 2016–2022 (`data/baseline/`), checked against counts requested directly for each window.
- Fetch scripts pause between queries, because CDC WONDER temporarily blocks addresses that send too many requests.

## 0.6.0 – 2026-10-14 · [10.5281/zenodo.23381196](https://doi.org/10.5281/zenodo.23381196)

Changes in response to feedback from a state maternal and child health epidemiologist ([#1](https://github.com/karantejpal12/perinatal-ews/issues/1)):

- State-level analysis: `perinatal-ews run --level state` sums county rows to states; state-level input can be used directly.
- `perinatal-ews pooled`: multi-year pooled estimates. Unavailable, missing or suppressed years are skipped and reported, never treated as zero (`--unavailable-years 2017,2018`); `--fill-window` reaches further back to collect enough years.
- Small racial and ethnic groups are combined when they have too few events, using configurable combinations, and labelled as combined; results that are still too small are reported as "insufficient data".
- Comparison of the latest pooled window with the previous one, only when both estimates are reliable.
- Groups are combined year by year before pooling; a suppressed member makes that combined year missing, never a partial sum. Combined groups requested directly from the source are used as they are.
- State-level results by mother's race (15 groups) for all states, from CDC WONDER (2016–2024), in the explorer's state view, with pooled 2022–2024 rates, combined groups and change since 2019–2021.
- `docs/small_numbers.md`.
- Tests for state aggregation, pooling with a 2017–2018 gap, combining small groups, combined groups from the source, window comparison, and a check that published race results never show a rate based on fewer than 20 events.

## 0.5.0 – 2026-10-14 · [10.5281/zenodo.23380220](https://doi.org/10.5281/zenodo.23380220)

- Interactive county map in the explorer.
- County types from unsupervised k-means clustering (silhouette-based k, bootstrap stability).
- Machine-learning data-quality check (Isolation Forest), validated on injected errors.
- Cross-conformal 90% prediction ranges for the similar-county comparison.
- `docs/ml_methods.md`.

## 0.4.0 – 2026-10-14

Not released separately; included in the 0.5.0 archive.


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
