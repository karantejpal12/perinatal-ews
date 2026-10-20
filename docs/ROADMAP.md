# Roadmap

Planned improvements to perinatal-ews, in rough order. Items are small enough to finish, test and document one at a time. Each finished item is ticked with its date and noted in the [changelog](../CHANGELOG.md) under "Unreleased"; the data updates themselves follow [UPDATING.md](UPDATING.md). Suggestions are welcome as [GitHub issues](https://github.com/karantejpal12/perinatal-ews/issues).

## Reliability and testing

- [x] Run the Python and JavaScript tests automatically on every change (GitHub Actions) and show the status in the README. (2026-10-19)
- [x] Test the full-year outlook when only one month remains and when the year is already complete. (2026-10-20)
- [ ] Monthly update script: when the data reach December, skip the outlook backtest (nothing remains to project) instead of failing.
- [ ] Test the completeness check (`choose_months`) when the latest month is far below normal and when a month is missing.
- [ ] Test pooled estimates when every year in the window is suppressed or unavailable.
- [ ] Test that input validation keeps two-letter state codes and pads numeric county codes.
- [ ] Test the data-quality check (Isolation Forest) on very small inputs: it should skip with a message, not fail.
- [ ] JavaScript tests for each `list_counties` filter, including combinations that match nothing.
- [ ] Test that no published state-by-race result in `latest.json` shows a rate based on fewer than 20 events.
- [ ] Check that every relative link in the README and `docs/` points to a file that exists.
- [ ] JSON Schema for `results/latest/latest.json`, with a test that the published file matches it.

## Documentation

- [ ] Data dictionary for every published results file: columns, units and meaning.
- [ ] Indicator definitions: the birth-certificate items and NCHS definitions behind each of the four indicators, and known comparability issues.
- [ ] "Interpreting a flag" guide for health department staff: what an alert does and does not mean, and suggested follow-up checks.
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
