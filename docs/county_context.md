# County context (v0.3)

Detection shows where maternal and newborn outcomes are getting worse. County context helps answer the next two questions a health department asks: *is this county doing worse than places like it?* and *what local capacity is there to respond?* It adds substance use, maternity-care access and social conditions to perinatal-ews, using only free public data.

Every measure describes a county, not a person. Nothing here says anything about individual parents, and results should not be presented in a way that blames families who use drugs.

## Data

| Source | Measures | Year | Level |
|---|---|---|---|
| CDC PLACES, county data (2025 release; 2024 release for states missing from 2025) | Adult high blood pressure, obesity, diabetes, smoking, depression, frequent mental distress, binge drinking, routine check-ups, uninsured adults 18–64, lack of transport, food and housing insecurity (model-based, age-adjusted) | BRFSS 2023 (2022 for fill) | County |
| CDC PLACES non-medical factor measures | Below 150% of poverty, unemployment, no high-school diploma, single-parent households, no broadband, housing cost burden, crowding | ACS 2017–2021 | County |
| CDC VSRR provisional county drug overdose deaths | 12-month count ending each December, converted to a rate per 100,000 residents; counts 1–9 suppressed by NCHS stay missing | 2020–2024 | County |
| SAMHSA FindTreatment.gov | Substance use treatment facilities; those offering medications for opioid use disorder (MOUD); federally certified opioid treatment programmes; those with a programme for pregnant or postpartum patients; Medicaid accepted | Listings as of October 2026 | Facility, placed in counties by coordinates (ZIP where coordinates are missing) |
| CMS Maternal Health – Hospital (Maternal Morbidity Structural Measure) | Hospitals with inpatient labour and delivery care; "Birthing-Friendly" designation | 2024 reporting | Hospital, matched to county by name |

`scripts/fetch_county_context.js` downloads the files in a browser and `scripts/build_county_context.py` builds `data/context/county_context.csv`, one row per county. For the 578 study counties, 570 have PLACES health measures (Connecticut now reports planning regions instead of counties), all have ACS measures, and 562–570 have an overdose rate depending on the year. 97% of facility listings were placed in a county and 99.5% of hospitals were matched.

## 1. Compared with similar counties (machine learning)

For each indicator, a gradient-boosted regression model predicts a county's pooled 2022–2024 rate (log-odds, weighted by births) from its context alone. Predictions are out-of-fold from 5-fold cross-validation, so no county is judged by a model that saw it. The ratio of the observed rate to the predicted rate says whether the county does better or worse than counties with similar health, social and access conditions. A county is "higher than similar counties" when z ≥ 1.96, where the variance includes binomial noise and the spread the model does not explain.

How much of the between-county variation the context explains (cross-validated R², births-weighted), compared with using the state average:

| Indicator | R², context model | R², state average |
|---|---|---|
| Low birth weight | 0.61 | 0.23 |
| Preterm birth | 0.55 | 0.34 |
| Late or no prenatal care | 0.47 | 0.45 |
| Gestational hypertension | 0.22 | 0.22 |

Context explains low birth weight and preterm birth far better than geography alone. For gestational hypertension it does no better than the state average, which is consistent with differences between states, including how this birth-certificate item is recorded, mattering more than local conditions; comparisons for that indicator should be read with care.

Results for 2024: 106 county-indicators are higher than similar counties, 51 lower, and 2,154 in line.

## 2. Need and access review list

A county is listed when it has a perinatal signal (an alert or watch flag in the total or a payer subgroup, or forecast risk of 30% or more) and at least one of:

- **High overdose burden:** overdose death rate in the top quarter of scored counties (2024: 29.4 per 100,000 or more).
- **Thin treatment access:** no facility that offers buprenorphine or methadone, accepts Medicaid and runs a programme for pregnant or postpartum patients, or a rate of such facilities per 1,000 births in the bottom quarter.
- **Thin delivery capacity:** no hospital in the county reports labour and delivery care to CMS (residents may deliver in a neighbouring county), or births per such hospital in the top tenth.

Counties with a signal, a high overdose burden and thin treatment access are marked **high**. In 2024, 122 counties are listed and 6 are high: King County WA, Madison County IN, Monroe County NY, Ascension Parish LA, Monroe County IN and Comanche County OK. 89 of the 578 counties have no listed MOUD facility for pregnant or postpartum patients that accepts Medicaid.

The cut-offs are relative to the counties scored and are printed with the results. This is a list for programme planning and for checking with local partners, not a ranking of need.

## 3. Context in the forecast

The context features were added to the next-year forecast and tested the same way as the base model (trained on earlier years only, scored on 2023 and 2024). They did not clearly improve it: held-out AUPRC changed by −0.006 (95% bootstrap CI −0.033 to +0.024), so the forecast keeps the base model. This is a finding, not a failure: county conditions explain where rates are high, but they say little about which counties will change next year, which is driven mostly by recent changes in the county's own data.

Each forecast now comes with its main factors: for every input, the change in predicted risk when that input is set to the training median. This is a simple occlusion method, labelled "approximate" in the outputs.

## Limitations

- Context measures are cross-sectional or a recent snapshot; facility and hospital data are 2026 and 2024 and are applied to all years. They are suitable for describing places, not for causal claims.
- PLACES estimates are model-based small-area estimates from BRFSS, not direct counts.
- FindTreatment.gov is voluntary; some facilities are missing or out of date. Facilities just across a county line serve residents too.
- Births are counted by the mother's county of residence; many suburban residents deliver in a neighbouring county, so "no labour and delivery hospital" is not by itself a gap.
- County-level associations do not apply to individuals (ecological fallacy).
