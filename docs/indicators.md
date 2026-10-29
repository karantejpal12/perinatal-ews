# Indicator definitions

The four indicators come from the US standard certificate of live birth (2003 revision), as published by NCHS through CDC WONDER. Since 2016 every state uses the 2003 revision, so the items are defined the same way in every state across 2016–2024; how completely they are recorded still differs by state, hospital and year. The CDC WONDER variables and categories used are in [`default_config.yaml`](../src/perinatal_ews/default_config.yaml).

## The four indicators

| Indicator | Definition | CDC WONDER variable | Counted as the outcome | Left out of the denominator |
|---|---|---|---|---|
| Late or no prenatal care | Prenatal care began in the third trimester (7th month or later) or there was no prenatal care | Month Prenatal Care Began | 7th, 8th, 9th or 10th month; No prenatal care | Unknown or not stated |
| Preterm birth | Born before 37 completed weeks of gestation, obstetric estimate | OE Gestational Age Recode 10 | Under 20 weeks to 34–36 weeks | Unknown or not stated |
| Low birth weight | Birth weight under 2,500 grams | Infant Birth Weight 12 | 499 grams or less to 2,000–2,499 grams | Unknown or not stated |
| Gestational hypertension | Hypertension diagnosed in this pregnancy (the checkbox covers pregnancy-induced hypertension and preeclampsia) | Gestational Hypertension | Yes | Unknown or not stated; not reported |

Rates are counts of the outcome divided by births with the item known, for births to residents of the county or state (the mother's place of residence, not the place of birth).

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
