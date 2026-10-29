# Changelog

All notable changes to perinatal-ews. Each release is archived on Zenodo (concept DOI [10.5281/zenodo.23374046](https://doi.org/10.5281/zenodo.23374046)). Feedback from users and reviewers is tracked as [GitHub issues](https://github.com/karantejpal12/perinatal-ews/issues) and linked here.

## Unreleased

- Explorer state view: a "How this was calculated" panel for the year-so-far results (how the rate and expected rate are set, the alert and watch rules, how the full-year projection, its 80% range and the chance of a flag are simulated, and what the whole-year column is). Published numbers are unchanged.
- Persistent burden on the published data: `results/2024/persistent_burden.csv` (2020–2024) and, in the explorer, a "Persistently among the highest" map option, a note on each county card, a list filter, a sentence in county summaries, and the AI assistant's `get_county`, `list_counties` (`persistent_burden` filter), `state_summary` and `national_summary` tools. Between 102 and 110 counties are persistent per indicator, and 377 of the 423 persistent results (89%) are stable under the change alerts. Existing published numbers are unchanged; tests check the explorer data against the CSV.
- Monthly update: the completeness check (`choose_months`) now stops with a clear message if national births are missing for a month inside the year-to-date window (which would undercount every total) or if no complete month of the year is available yet, instead of continuing; new tests cover a latest month far below normal, the 97% threshold, and missing months. Published numbers are unchanged.
- Gestational hypertension's reporting-quality caveat now also appears in the state view, under the map legend when that indicator is shown, and in the AI assistants' tool results (explorer `get_county`, `state_summary`, `list_counties`, `national_summary`; MCP `get_state`, `explain_state_flag`, `list_state_flags`), whose instructions ask them to state it; one shared text (`caveat` in the indicator config, `CAVEATS` in `js/ews-tools.js`, tested to match). Published numbers are unchanged.
- Explorer: every county rate shows a 95% confidence interval (Wilson), rates on fewer than 20 events are marked unstable, and each result has a "How this was calculated" panel (expected rate, alert and watch rules, what stable means, and the forecast's forward-in-time AUROC and calibration); state summaries say how many of the state's counties are not covered and that no flag does not mean no concern; the year-so-far race table explains why most groups are insufficient data in smaller states. Published numbers are unchanged.
- Missing-data sensitivity for gestational hypertension: `ingest-wonder --unknown-as-case-file` reads a second export grouped also by Eclampsia, and `unknown_sensitivity.csv` then shows each flag when births with the item unknown but eclampsia checked are counted as cases (`*_as_case` columns, also at state level); default rates and published numbers are unchanged.
- `run --level state` now carries the `unknown` column through when summing counties to states (missing for a state-year if any county's is missing), so the missing-data sensitivity file is written for state-level runs too; published numbers are unchanged.
- `perinatal-ews run` writes `unknown_sensitivity.csv` when the tidy data have an `unknown` column: detection is run with births of unknown status left out of and counted in the denominator, and every flag that changes is listed with the county's unknown share (`perinatal_ews.missing`).
- Outlook backtest: a `forward_only` option that learns the simulated range widths only from years before each backtest year (the published method also used later years), and a simple baseline (ranking states by the year-so-far z-score); `scripts/validate_outlook.py` reruns both methods from the repository's data with results by year, indicator and calibration bin. Published figures are unchanged.
- `ingest-wonder` keeps the number of births with each item unknown or not stated in a new `unknown` column, and `--unknown-in-denominator` counts them as births without the outcome, the first step of the missing-data sensitivity analysis; default rates are unchanged.
- Explorer: every county's gestational hypertension result now carries a reporting-quality caveat; gestational hypertension stays in the alerts, to be presented separately (roadmap).
- Methodology: gestational hypertension alerts are flagged as reflecting reporting quality, citing NCHS validation studies (Martin et al., 2013; Gregory et al., 2019); roadmap adds a decision on how to show gestational hypertension, county coverage through the NCHS restricted-use natality file, the outcome-count meaning of the 60 minimum, and per-indicator display of the persistent-burden flag.
- Roadmap: the internal reference-group comparison will use each county's own Perinatal Periods of Risk reference group, only where every cell has at least 60; methodology cites evidence on excluding records with missing items (Ahrens et al., 2021).
- Persistent-burden flag (`perinatal_ews.persistent`): counts the years among the last five in which each county was in the worst national quintile and marks three or more as persistent, reported separately from change alerts in `persistent_burden.csv`; tested on synthetic data, not yet run on the published county data.
- Methodology limitations now state that effects confined to small rural counties cannot be detected, that persistently high but stable rates are not flagged, and that items with unknown values are left out of denominators; roadmap gains a methods-priorities section (persistent-burden flag, missing-data sensitivity, held-out validation, space-time comparison, internal reference group).
- MCP server (`perinatal-ews mcp`, optional `[agent]` install): AI assistants such as Claude Desktop can answer questions from this year's state results and the full-year outlook, read-only, with sources, reliable-only results by race and suggested follow-up checks ([docs/mcp_server.md](docs/mcp_server.md)).
- Monthly update no longer fails when the data reach December: it skips the outlook backtest (nothing remains to project), removes the previous month's `outlook_backtest.json` and leaves it out of `latest.json`; end-to-end test of the update script for August and December.
- Full-year outlook no longer fails once December is known: it reports the actual year (no range, flag probability 0 or 1); new tests for one month remaining and a complete year.
- Tests run automatically on every change (GitHub Actions, Python 3.10 and 3.12, and the JavaScript tests); status badge in the README.
- Public roadmap ([docs/ROADMAP.md](docs/ROADMAP.md)).

## 0.8.0 – 2026-10-15 · [10.5281/zenodo.23383550](https://doi.org/10.5281/zenodo.23383550)

- Full-year outlook (`perinatal_ews.outlook`): for every state and indicator, a projected full-year rate with an 80% range and the chance that the whole year will be flagged, from the months known so far and how each state's year usually ends (empirical-Bayes seasonal step, simulated remaining months, standard detection on each simulation).
- Backtested on 2021–2025 using only January–August of each year: AUROC 0.97, Brier score 0.029 (0.040 for "flagged so far"), 80% ranges contained the actual full-year rate 85% of the time.
- Each monthly update saves its outlook in `results/history/<YYYY-MM>/outlook.csv`; outlooks are scored automatically once their year is complete.
- Clearer explorer: every map option and section states the period and geography it covers (this year by state, 2024 by county, 2025 county forecast); map title and period label; "how to use" steps; filter reset; state view in two blocks ("Now" and "2024 in detail") with the race tables folded away.

## 0.7.0 – 2026-10-15 · [10.5281/zenodo.23383246](https://doi.org/10.5281/zenodo.23383246)

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
