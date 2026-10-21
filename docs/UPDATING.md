# Keeping perinatal-ews up to date

perinatal-ews has two update cycles.

| Results | Data | How often | Geography |
|---|---|---|---|
| "This year so far" state results | CDC WONDER provisional natality (database D192) | Monthly, after CDC's end-of-month release | States and DC, totals and by mother's race |
| County results, forecast, context | CDC WONDER final natality (database D149) | Yearly, when CDC adds a new final year (2024 final data were added in September 2025) | 578 counties with 100,000+ residents |

The site always shows how current the data are: the banner at the top of the explorer and the state view say which months are included, when the data were retrieved and that they are provisional.

## Monthly update (about 10 minutes)

1. Open <https://wonder.cdc.gov/natality-expanded-provisional.html>, read the data use restrictions and click **I Agree**.
2. On the request form, open the browser console and paste [`scripts/fetch_wonder_latest.js`](../scripts/fetch_wonder_latest.js). It checks which months are complete, runs about 35 queries and downloads two files.
3. Move both files to `data/latest/` and run:

   ```bash
   python scripts/update_latest.py \
       --provisional data/latest/wonder_provisional_state_YYYY-MM.csv \
       --months data/latest/wonder_provisional_months_YYYY-MM.json
   ```

4. Check the printed summary, then commit and push. The site updates within a few minutes:

   ```bash
   git add data/latest results/latest results/history
   git commit -m "Monthly update: provisional data through <Month YYYY>"
   git push
   ```

Each update also saves a dated copy in `results/history/<YYYY-MM>/`, so every monthly result stays on record. That copy includes the full-year outlook (`outlook.csv`) and its backtest (`outlook_backtest.json`); with data through December the outlook is the actual year, so there is no backtest and that file is not written. Once a year is complete in the provisional data, the update scores every outlook saved for that year and publishes the results (`results/latest/outlook_track_record.json`). The update takes about eight minutes, mostly for the outlook simulations.

### How the months are chosen

CDC's latest month is the least complete. The fetch script compares births in the latest month with the same month a year earlier; if that ratio is below 97% of the typical ratio for earlier months, the month is left out and the window ends a month earlier. The site says whether the latest month was included.

## Yearly update (when CDC adds a new final year)

1. Run [`scripts/fetch_wonder_counties.js`](../scripts/fetch_wonder_counties.js) on the final natality request form, then `perinatal-ews run --forecast --context data/context/county_context.csv` as in the README.
2. Rebuild the explorer data with `scripts/build_explorer_data.py`.
3. Score the previous year's archived forecast against the new final year (`perinatal_ews.latest.score_forecast`), and publish a new release so Zenodo archives it.
4. When the provisional database marks a year as final, nothing else changes: the monthly update uses it automatically.

## One-time setup (already done)

`data/baseline/final_state_ytd_2016_2022.csv` holds final state counts for every January-to-month window from 2016 to 2022. It was made with [`scripts/fetch_wonder_state_baseline.js`](../scripts/fetch_wonder_state_baseline.js) and does not change.

## Why the data are fetched in a browser

CDC WONDER requires agreeing to its data use restrictions in a browser session, and, as far as we know, its automated interface (API) does not provide state- or county-level birth data. The fetch scripts therefore run in the browser of the person doing the update.
