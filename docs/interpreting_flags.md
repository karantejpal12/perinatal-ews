# Interpreting a flag

A guide for health department staff who see a perinatal-ews result for their state or county. Flags are statistical leads for follow-up, not confirmed problems. This page says what each result means, what it does not mean, and which checks to do first. The calculations are in the [methodology](methodology.md).

## What each result means

| Result | Meaning | What it does not mean |
|---|---|---|
| **Alert** | The rate is higher than the area's own recent history predicts (after allowing for the national trend), by more than chance after testing every area at once (Benjamini–Hochberg q ≤ 0.05), at least 1.10 times expected and on at least 20 events. | That something went wrong in care, or that the cause is local. A change in how the item is recorded produces the same signal. |
| **Watch** | A smaller or less certain rise: z ≥ 2, at least 1.05 times expected, at least 10 events. | That an alert will follow. |
| **Stable** | No change from the area's own history was detected. | That the rate is low or acceptable. A rate that has been high for years is stable. |
| **Persistently among the highest** | The county was in the highest fifth of the 578 scored counties in at least 3 of the last 5 years. Shown separately from alerts. | A recent change. It ranks only large counties against each other. |
| **No flag** | None of the above. | That there is no concern. Small rural counties are not scored at all, and the tool cannot see causes that the birth certificate does not record. |

Change alerts and the persistent-burden flag answer different questions. A sudden worsening matters for a policy change, a hospital closure or a disaster; a persistently high rate matters for long-term planning and resources. Read them side by side.

## Checks to do first

### 1. Is it the data?

- **Many areas in one state flagged together.** The explorer marks these as state-wide patterns. A state-wide jump is often a change in how the item is recorded (a new birth-certificate worksheet, training, or a hospital electronic health record transition) rather than a change in health. Ask the state vital records office whether anything changed in collection or coding that year.
- **Gestational hypertension.** The birth-certificate checkbox misses many cases: NCHS validation studies found it captured 20–50% of cases in two states and 23% in New York City, with quality varying by hospital (Martin et al., 2013; Gregory et al., 2019). Treat a gestational hypertension flag as reflecting reporting quality at least as much as a true change, and check which hospitals the births came from.
- **Unusual data check.** If the county's record is marked unusual by the machine-learning check, confirm the counts with the data provider before acting.
- **Missing values.** Births with the item unknown or not stated are left out of the rate. If the share of unknowns changed, the rate can move without any change in health; the [missing-data sensitivity](methodology.md) shows which flags depend on how unknowns are treated.

### 2. Is it more than one year?

- Look at the trend chart: a single high year next to a flat history is weaker evidence than a rise that continues. The county card says when the result was also elevated the year before.
- For a rate that is high but stable, see whether the county is persistently among the highest.
- Wait for the next monthly update before drawing conclusions from the most recent provisional months, which are the least complete and are revised.

### 3. Who is affected?

- Payer groups (Medicaid and private insurance) can show a change that is diluted in the county total.
- Results by mother's race are at state level with three years pooled, because county-level groups are usually too small; small groups are combined or reported as insufficient data rather than shown as unreliable rates.
- Births are counted by the mother's county of residence, but clinical items such as gestational hypertension are recorded by the hospital where she delivered. A change can come from a hospital outside the county, or from mothers starting to deliver somewhere else after a unit closes.

### 4. What else is going on?

- The comparison with similar counties and the county context (overdose deaths, treatment for pregnant and postpartum patients, hospitals with delivery care, adult health and social conditions) help judge whether the level is out of line with the county's circumstances. These describe places, not people, and are associations, not causes.
- Birth-certificate data usually arrive before survey data. PRAMS estimates for the same births generally come a year or more later, and PRAMS questions are set for multi-year phases, so PRAMS may not be able to explain a sudden change, especially one driven by a policy, a natural disaster or a new local programme.
- Local partners usually know first: the state vital records office, the perinatal quality collaborative, hospital quality teams, maternal mortality review committees and community organisations.

## What to do next

1. Confirm the data with the vital records office (recording changes, hospital transitions, completeness).
2. Look at the trend, the subgroups and the hospitals of delivery.
3. If the change looks real, share it with the programme and partners who can look at causes, and document what was checked and decided.
4. Check the next monthly or yearly update: the outlook and next-year forecast show whether the change is expected to persist.

## Limits to keep in mind

- Only the 578 counties with 100,000 or more residents are scored; CDC WONDER combines smaller counties within each state.
- The tool sees only what the birth certificate records, and some items are recorded incompletely.
- It is not designed for clinical or individual decisions.

## References

- Brown CC et al. Geographic hotspots for low birthweight: an analysis of counties with persistently high rates. *Inquiry*. 2020;57.
- Gregory ECW et al. Assessing the quality of medical and health data from the 2003 birth certificate revision: results from New York City. *National Vital Statistics Reports*. 2019.
- Martin JA et al. Assessing the quality of medical and health data from the 2003 birth certificate revision: results from two states. *National Vital Statistics Reports*. 2013.
