# Indicator definitions

The four early-warning indicators, and the maternal and child health measures added in November 2026, come from the US standard certificate of live birth (2003 revision), as published by NCHS through CDC WONDER. Since 2016 every state uses the 2003 revision, so the items are defined the same way in every state across 2016–2024; how completely they are recorded still differs by state, hospital and year. The CDC WONDER variables and categories used are in [`default_config.yaml`](../src/perinatal_ews/default_config.yaml).

## The four indicators

| Indicator | Definition | CDC WONDER variable | Counted as the outcome | Left out of the denominator |
|---|---|---|---|---|
| Late or no prenatal care | Prenatal care began in the third trimester (7th month or later) or there was no prenatal care | Month Prenatal Care Began | 7th, 8th, 9th or 10th month; No prenatal care | Unknown or not stated |
| Preterm birth | Born before 37 completed weeks of gestation, obstetric estimate | OE Gestational Age Recode 10 | Under 20 weeks to 34–36 weeks | Unknown or not stated |
| Low birth weight | Birth weight under 2,500 grams | Infant Birth Weight 12 | 499 grams or less to 2,000–2,499 grams | Unknown or not stated |
| Gestational hypertension | Hypertension diagnosed in this pregnancy (the checkbox covers pregnancy-induced hypertension and preeclampsia) | Gestational Hypertension | Yes | Unknown or not stated; not reported |

Rates are counts of the outcome divided by births with the item known, for births to residents of the county or state (the mother's place of residence, not the place of birth).

## Added maternal and child health measures

Added in November 2026 at the suggestion of a state maternal and child health epidemiologist. They come from the same birth certificates and are defined in [`default_config.yaml`](../src/perinatal_ews/default_config.yaml) with `set: more`; [`scripts/fetch_wonder_more.js`](../scripts/fetch_wonder_more.js) downloads them from CDC WONDER. Each is framed so that a higher rate is worse, so an alert or watch flag always means "worse than expected", as for the four indicators.

| Measure | Definition | CDC WONDER variable | Counted as the outcome | Left out of the denominator |
|---|---|---|---|---|
| No first-trimester prenatal care | Prenatal care did not begin in months 1–3. The first-trimester rate that state reports use is 100% minus this rate | Month Prenatal Care Began | 4th to 10th month; No prenatal care | Unknown or not stated |
| Obesity before pregnancy | Pre-pregnancy body mass index 30 or more | Mother's Pre-pregnancy BMI | Obesity I, Obesity II, Extreme Obesity III | Unknown or not stated |
| Overweight or obesity before pregnancy | Pre-pregnancy body mass index 25 or more | Mother's Pre-pregnancy BMI | Overweight and the three obesity categories | Unknown or not stated |
| Gestational diabetes | Diabetes diagnosed in this pregnancy | Gestational Diabetes | Yes | Unknown or not stated; not reported |
| Smoking during pregnancy | Cigarettes smoked at any time during pregnancy | Tobacco Use | Yes | Unknown or not stated; not reported |
| Low-risk (NTSV) cesarean | Cesarean deliveries among first births at 37 weeks or more, single and head-first: the NCHS low-risk cesarean rate | Delivery Method, from an export limited to Live Birth Order 1, Plurality Single, Fetal Presentation Cephalic and OE gestational age 37 weeks or more | Cesarean | Unknown or not stated delivery method; births outside the limits |

**What these measures get, and what they do not.** Each gets the same change detection (alert and watch), the persistent-burden ranking, the similar-county comparison and, at state level, results by mother's race, Hispanic origin and payer pooled over three years. The next-year forecast, county types, the unusual-data check and the need-and-access review were built and tested on the four indicators above, so they still use only those four (`config.core_indicators`); a test checks that adding the measures leaves every result for the four unchanged. Totals in the explorer and the AI assistant are reported separately for the four indicators and the added measures. The monthly state results (provisional data) cover the four indicators only.

**Low-risk (NTSV) cesarean.** NCHS defines the rate as singleton, term (37 or more completed weeks, obstetric estimate), cephalic cesarean deliveries to women having a first birth, per 100 women delivering singleton, term, cephalic first births (NCHS natality user guide, "Low-risk cesarean rate"). NCHS counts first births by live-birth order, which excludes fetal deaths, so the tool uses Live Birth Order 1. Hospital quality measures of NTSV cesarean are built from hospital records with their own exclusions, so their rates are not directly comparable. Because the CDC WONDER export has to be limited to these births before it is downloaded, the indicator's config records the limits (`wonder.filters`), and `ingest-wonder` stops if an export's query criteria do not show exactly those limits; the download script checks the same before saving. Restricting to first, term, single, head-first births makes the counts small, so many county-years will need pooled years.

**Pre-pregnancy body mass index.** NCHS computes it from the mother's height and pre-pregnancy weight as entered on the birth certificate, which are usually self-reported. Self-reported weight tends to be lower than measured weight, so these rates are more likely to be too low than too high.

**Smoking.** The birth certificate asks about cigarettes smoked before and in each trimester of pregnancy; "Tobacco Use" is yes when any cigarettes were smoked during pregnancy. Comparisons with the PRAMS survey found that birth certificates miss some mothers who report smoking in the survey (Allen et al., 2008; Tong et al., 2013).

**Gestational diabetes.** A checkbox in "Risk factors in this pregnancy". Nationally it rose from 6.0% of mothers in 2016 to 8.3% in 2021, and NCHS notes it may be under-reported (MMWR QuickStats, 2023). Detection compares each county with the change across all counties, so a national rise alone does not flag a county.

**Not yet added.** Teen birth rates use the number of females aged 15–19 as the denominator rather than births; CDC WONDER provides it as a fertility rate by county, year and mother's age, and it will be added once its detection has been checked on synthetic data (see the [roadmap](ROADMAP.md)).

## How each item is recorded

**Month prenatal care began.** NCHS derives it from the date of the first prenatal care visit, the date of birth and the obstetric estimate of gestational age. When the month of the first visit is valid but the day is missing, NCHS imputes the day from a previous record with the same month (3.1% of 2016 records); 2.9% of 2016 records had the month prenatal care began missing altogether (Osterman and Martin, 2018). A late first visit can therefore reflect the visit date recorded on the hospital worksheet as well as when care actually began.

**Gestational age.** Since 2014, NCHS uses the obstetric estimate (the clinician's best estimate of gestation at delivery) rather than the date of the last menstrual period. Preterm birth is under 37 completed weeks on this estimate.

**Birth weight.** Recorded in grams at delivery; births with weight not stated are left out. CDC WONDER's documentation labels this category "Not stated" while the tool removes the label "Unknown or Not Stated"; whether the two match in the export is being checked (see the [roadmap](ROADMAP.md)). Such births are rare, so the effect on rates is at most very small.

**Gestational hypertension.** A checkbox in "Risk factors in this pregnancy": "Diagnosis in this pregnancy (pregnancy-induced hypertension or preeclampsia)"; the NCHS worksheet guide lists PIH, preeclampsia, eclampsia, transient hypertension and HELLP syndrome as terms to look for. Chronic (prepregnancy) hypertension is a separate checkbox, and only one of the two should be checked; eclampsia is a further checkbox. The hospital fills it in from the prenatal record, the labour and delivery triage form, the admission history and physical, and the delivery record. In NCHS validation studies against hospital records, the checkbox identified 20–50% of cases in two states and 23% in New York City (see [Limitations](methodology.md#limitations)), so this indicator is shown with a reporting-quality caveat.

## Missing values

Births with an item unknown or not stated are left out of that indicator's denominator, as NCHS does in its own percentages. If the share of unknowns changes, a rate can move without any change in health. The tool can rerun detection with unknown births counted in the denominator instead, and for gestational hypertension with unknown births counted as cases when eclampsia is checked; see [Missing data](methodology.md#limitations). These sensitivity results have not yet been run on the published county data, because the published download does not include unknown counts (see the [roadmap](ROADMAP.md)).

## Comparability

- **Across states.** Definitions are the same since 2016, but completeness and coding practice differ, especially for checkbox items such as gestational hypertension. A state-wide jump is often a recording change; see [Interpreting a flag](interpreting_flags.md).
- **Over time.** A hospital's move to a new electronic health record, a new worksheet or training can change how an item is recorded from one year to the next.
- **Final and provisional data.** County results use final data (2016–2024). The monthly state results use provisional data for the current year, whose most recent months are incomplete and are revised.
- **Small areas.** CDC WONDER shows counties with 100,000 or more residents and suppresses counts of 1 to 9; rates on fewer than 20 events are marked unstable (NCHS standard).

## Sources

- CDC WONDER. Natality, 2016–2024 expanded: documentation. <https://wonder.cdc.gov/wonder/help/natality.html>
- NCHS. Guide to completing the facility worksheets for the certificate of live birth and report of fetal death: risk factors in this pregnancy. <https://www.cdc.gov/nchs/nvss/facility-worksheets-guide/14.htm>
- NCHS. User guide to the 2024 natality public use file. <https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Dataset_Documentation/DVS/natality/UserGuide2024.pdf>
- Osterman MJK, Martin JA. Timing and adequacy of prenatal care in the United States, 2016. *National Vital Statistics Reports*. 2018;67(3). <https://www.cdc.gov/nchs/data/nvsr/nvsr67/nvsr67_03.pdf>
- Allen AM, Dietz PM, Tong VT, England L, Prince CB. Prenatal smoking prevalence ascertained from two population-based data sources: birth certificates and PRAMS questionnaires, 2004. *Public Health Reports*. 2008;123(5):586–592. <https://doi.org/10.1177/003335490812300508>
- Tong VT, Dietz PM, Farr SL, D'Angelo DV, England LJ. Estimates of smoking before and during pregnancy, and smoking cessation during pregnancy: comparing two population-based data sources. *Public Health Reports*. 2013;128(3):179–188. <https://doi.org/10.1177/003335491312800308>
- Martin JA, Gregory ECW. QuickStats: Percentage of mothers with gestational diabetes, by maternal age — National Vital Statistics System, United States, 2016 and 2021. *MMWR*. 2023;72(1):16. <https://doi.org/10.15585/mmwr.mm7201a4>
