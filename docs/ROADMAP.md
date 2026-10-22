# Roadmap

Planned improvements to perinatal-ews, in rough order. Items are small enough to finish, test and document one at a time. Each finished item is ticked with its date and noted in the [changelog](../CHANGELOG.md) under "Unreleased"; the data updates themselves follow [UPDATING.md](UPDATING.md). Suggestions are welcome as [GitHub issues](https://github.com/karantejpal12/perinatal-ews/issues).

## Methods priorities

Work first on these. Items marked "needs data" require a fresh CDC WONDER download, which needs a person to accept CDC's data use terms; build and test the code on synthetic data first.

- [x] Persistent-burden flag (code): for each county and indicator, count the years among the last five in which the county's rate was in the worst national quintile; flag three or more as "persistent", reported separately from change alerts. Tests on synthetic data; methods note citing Brown CC et al., "Geographic Hotspots for Low Birthweight: An Analysis of Counties With Persistently High Rates", *Inquiry* 2020;57 (the neighbouring-county condition is dropped because only large counties are identifiable). (2026-10-22)
- [ ] Persistent-burden flag (needs data): run on 2016–2024 county data and show it in the explorer beside change alerts.
- [ ] Missing-data sensitivity (code): an option to count births with the item "Unknown or Not Stated" in the denominator, and a report of alerts that change between the two choices. For gestational hypertension, a variant that counts an unknown gestational item as yes when eclampsia is checked; chronic hypertension stays a separate composite, since it is not gestational by definition.
- [ ] Missing-data sensitivity (needs data): download unknown counts by county and year for each indicator, report the unknown share, and run the sensitivity analysis.
- [ ] Held-out validation of detection: leave out each county-year (recent years first), predict it from the rest, and report interval coverage against the predictive distribution of held-out counts (so binomial noise is included) and prediction error.
- [ ] Space-time comparison: fit a space-time smoothing model (R package SUMMER) on the same held-out county-years and compare coverage and error with the current pooled empirical-Bayes approach; write up in the validation page.
- [ ] Internal reference group (code): compare each county with a reference group defined by Perinatal Periods of Risk criteria (non-Hispanic White mothers, aged 20 or older, with at least some college; Gilbert CS, Xaverius PK, Tibbits MK et al., *Matern Child Health J* 2022;26:2396–2406), querying CDC WONDER with filters. Each county is compared with its own reference group (within-county rates, not the national 2014–2016 rates), and only where every cell meets the PPOR minimum of 60, pooling adjacent years to reach it; counties that still fall short are reported as insufficient data. To confirm: whether the minimum applies to events or to births for these indicators.

## Reliability and testing

- [x] Run the Python and JavaScript tests automatically on every change (GitHub Actions) and show the status in the README. (2026-10-19)
- [x] Test the full-year outlook when only one month remains and when the year is already complete. (2026-10-20)
- [x] Monthly update script: when the data reach December, skip the outlook backtest (nothing remains to project) instead of failing. (2026-10-21)
- [ ] Test the completeness check (`choose_months`) when the latest month is far below normal and when a month is missing.
- [ ] Test pooled estimates when every year in the window is suppressed or unavailable.
- [ ] Test that input validation keeps two-letter state codes and pads numeric county codes.
- [ ] Test the data-quality check (Isolation Forest) on very small inputs: it should skip with a message, not fail.
- [ ] JavaScript tests for each `list_counties` filter, including combinations that match nothing.
- [ ] Test that no published state-by-race result in `latest.json` shows a rate based on fewer than 20 events.
- [ ] Check that every relative link in the README and `docs/` points to a file that exists.
- [ ] JSON Schema for `results/latest/latest.json`, with a test that the published file matches it.

## Uncertainty, validation and interpretation

- [ ] County view: show a 95% confidence interval with every rate, and mark rates based on 10–19 events as unstable (NCHS: fewer than 20 events).
- [ ] "How this was calculated" panel beside each county and state result: how the expected rate is set, the alert and watch thresholds, and what the forecast probability means and how well calibrated it was in testing.
- [ ] Reporting-completeness signal: the share of births with each item unknown or not stated, by area and year, shown beside every flag, with a note when completeness changed.
- [ ] Label every explorer table and chart as final or provisional data, with the data year and retrieval date.
- [ ] Validation page (`docs/validation.md`) bringing together every evaluation: alert rates on historical data, sensitivity and false-alert rate on synthetic data, forward-in-time forecast accuracy and calibration, and the outlook backtest.
- [ ] Compare county and state estimates with published state vital-records reports for a sample of states, and document any differences.
- [ ] Forecast and alert performance by county size and by county characteristics (rurality, births by payer, race and ethnicity mix), in the model card.
- [ ] Test how changes in item completeness affect alerts, using synthetic data with injected drops in completeness.

## Documentation

- [ ] Data dictionary for every published results file: columns, units and meaning.
- [ ] Indicator definitions: the birth-certificate items and NCHS definitions behind each of the four indicators, how missing values are handled (for example, how the month prenatal care began is set when dates are missing), and known comparability issues across states and years.
- [ ] "Interpreting a flag" guide for health department staff: what an alert does and does not mean, and suggested follow-up checks (local data quality, several years of trend, access to care and social factors).
- [ ] Full references in the methodology (empirical Bayes, false discovery rate, conformal prediction, Isolation Forest, k-means).
- [ ] Frequently asked questions.
- [ ] Docstrings for every public function, one module at a time (`detect`, `pooling`, `latest`, `outlook`, `context`).
- [ ] `CONTRIBUTING.md`: running the tests, reporting a data issue, proposing an indicator.
- [ ] Issue templates for bug reports, data questions and indicator requests.

## Explorer

- [ ] Download the current state view and the county table as CSV.
- [ ] Keyboard access to the map (move between areas, open one with Enter).
- [ ] Check the map colours for colour-blind readability; add text labels where colour alone carries meaning.
- [ ] Shareable links: the address keeps the selected state, indicator and map option.
- [ ] Print-friendly state summary.
- [ ] Show how the outlook performed in its backtest next to each outlook value.

## AI assistant for health departments

Goal: let health department staff go from a flag to a documented follow-up plan in minutes, using the assistant they already have, with every figure traceable to the published results.

- [x] MCP server (`perinatal-ews mcp`): read-only tools over this year's state results and the full-year outlook, for Claude Desktop, Claude Code and other MCP clients. (2026-10-20)
- [ ] MCP tools for the 2024 county results (the same six tools as the explorer's Ask AI tab), so one server covers states and counties.
- [ ] Figure check for MCP answers: a tool that checks every figure in a draft answer against the results looked up, as the explorer does.
- [ ] Flag investigation memo: for one flagged state and indicator, run the follow-up checks (neighbouring states, last full year, groups by mother's race, data-quality signals, outlook) and write a one-page memo with what the flag means, what it does not mean and suggested next steps.
- [ ] Monthly state briefing: after each update, a plain-language one-page summary per state, written by fixed rules from the data, for programme staff and leadership.
- [ ] Short guide and demo questions for health department epidemiologists trying the assistant, with a feedback issue template.

## Package and command line

- [ ] `perinatal-ews --version`.
- [ ] Clearer error when an input file lacks required columns, naming the missing columns.
- [ ] `perinatal-ews validate`: check an input file without running the analysis.
- [ ] Type hints on public functions, checked automatically.
