# Methodology

## Purpose

Public health teams usually learn about a worsening maternal or newborn indicator in a county long after it started, from annual reports that rank counties by level rather than by change. `perinatal-ews` asks a narrower, more actionable question: **is this county doing worse this year than its own recent history and the national trend predict, by more than chance allows?**

## Data model

Every source is converted to a tidy table: one row per county (`geo_id`), year, indicator and subgroup, with a numerator (births with the outcome) and denominator (births with a known value). Subgroup `All` is the county total.

## Indicators

| Key | Definition | Direction |
|---|---|---|
| `late_no_prenatal_care` | Prenatal care began in the 3rd trimester or not at all | higher is worse |
| `preterm_birth` | Under 37 completed weeks, obstetric estimate | higher is worse |
| `low_birth_weight` | Under 2,500 g | higher is worse |
| `gestational_hypertension` | Hypertension first diagnosed in pregnancy | higher is worse |

Indicators are defined in configuration, so new ones (for example, a severe maternal morbidity measure from hospital discharge data) can be added without code changes.

## Detection, for target year T

**Baseline.** For county *c*, pool numerator and denominator over years T−1−B … T−2 (default B = 3), skipping the guard year T−1. Without the guard year, a deterioration that began in T−1 is partly absorbed into the baseline and the alert in T is muted. Counties need at least B−1 baseline years.

**Shrinkage.** Let *m* be the pooled all-county baseline rate. Between-county variance of baseline rates is estimated by method of moments (observed weighted variance minus expected sampling variance). Treating county rates as Beta(*km*, *k*(1−*m*)), the prior strength is *k* = *m*(1−*m*)/σ²<sub>between</sub> − 1. The shrunk baseline is

  p̂<sub>c</sub> = (x<sub>c</sub> + *km*) / (n<sub>c</sub> + *k*)

so a county with few births is pulled toward the peer rate and a large county keeps its own.

**Peer trend.** Expected rate in T is p̂<sub>c</sub> × d, where d = (all-county rate in T) / (all-county baseline rate). This removes shifts that affect every county (secular trends, national coding changes) so the system highlights counties that diverge from peers. It can be disabled with `adjust_for_reference_trend: false`.

**Variance.** County-years scatter more than binomial noise allows, and the excess grows with county size. We model

  Var(O − E) = E(1−p) + τ²E² + (n d)² p̂(1−p̂)/(n<sub>c</sub>+*k*) + τ²E²/y<sub>c</sub>

covering binomial noise in T, extra year-to-year variation, sampling error in the baseline and year-to-year error in the baseline (y<sub>c</sub> = baseline years). τ² is estimated by method of moments from the baseline years' residuals, with a correction because each residual is measured against a baseline that includes it.

**Flags.** z = (O − E)/√Var, one-sided in the direction of harm. Benjamini–Hochberg q-values are computed across counties within each indicator and subgroup.

- **Alert:** q ≤ 0.05, O/E ≥ 1.10 and O ≥ 20.
- **Watch:** z ≥ 2, O/E ≥ 1.05 and O ≥ 10.
- **Sustained:** z ≥ 2 in both T and T−1.

The relative-risk floors stop very large counties from alerting on changes that are statistically clear but too small to act on.

**Trend.** Annual percent change in odds from a weighted least-squares fit of logit(rate) on year, reported for context.

## Persistent burden

Change alerts never flag a county whose rate is high but stable. A separate persistent-burden flag (`perinatal_ews.persistent`, written to `persistent_burden.csv` by `perinatal-ews run`) covers that case, following the persistence criterion of Brown et al. (2020):

- Each year, counties with a known rate are ranked (one county, one rank); the worst quintile is the fifth with the highest rates (lowest for `lower_is_worse` indicators), with ties at the boundary included. Years with fewer than five ranked counties are skipped.
- For each county and indicator, the years among the last five in which the county was in the worst quintile are counted. Three or more makes the county **persistent**; fewer than three ranked years is **insufficient data**. Missing or suppressed years are skipped, never counted as "not worst".
- A persistent county is marked not `reliable` when any of its worst-quintile years rests on fewer than 20 events.

The flag is reported beside change alerts, not merged into them: a county can be persistent and stable, newly alerting without being persistent, or both. Brown et al. also required neighbouring counties to be high; that condition is dropped because public county data identify only counties of 100,000 residents or more.

## Subgroups and equity

Detection is repeated within each subgroup present in the data. Separately, for each county and indicator, the highest and lowest reliable subgroup rates are compared (ratio and difference) and shown beside the same gap for all counties combined.

## Monitoring the system

- **Data quality:** counties missing compared with last year, suppressed counts, and denominator changes over 30%.
- **Distribution drift:** population stability index (PSI) of county rates in T against the baseline years. PSI < 0.10 stable, 0.10–0.25 moderate, > 0.25 major. A shift can be a real national trend, which detection adjusts for, or a coding change, which it may not.
- **State-wide patterns:** states where at least 40% of scored counties (minimum 3) are flagged for the same indicator. Detection compares counties with all counties nationally, so a state-wide shift (policy, coverage, or a change in how the state codes a birth-certificate item) can appear as many county flags; these are reported separately for review with the state vital records office.
- **Backtest:** each past year scored as if current. On stable data, alert rates should stay low and steady; a jump with no known cause suggests a data problem.
- **Ground-truth evaluation (synthetic data):** sensitivity overall and by county size, and false-alert rate on unchanged series.

Reporting performance by county size matters because detectors that work well for large urban counties can quietly miss small and rural ones.

## County context

Version 0.3 adds county context (substance use, maternity care access, adult health and social conditions), a cross-validated comparison with similar counties and a need-versus-access review list. See [county_context.md](county_context.md).

## Limitations

- Annual county data detect changes a year or more after they begin. Monthly or provisional data would shorten the lag.
- CDC WONDER hides counties under 100,000 residents, which excludes most rural counties from county-level analysis. State vital records offices hold complete data and are the natural partners for deployment.
- Birth certificate items vary in completeness and coding quality between states and over time.
- Flags identify where to look, not why. Interpreting them needs local knowledge (a hospital closure, a reporting change, a real clinical shift).
- Effects confined to small rural counties cannot be detected. For example, the fall in adequate prenatal care after rural labor and delivery units close (Radke et al., 2023) affects few births: it is lost within state totals, and the public data have no measure of obstetric services in the mother's county of residence.
- Detection measures change against each county's own history, so a county whose rates are persistently high but stable is not flagged as a change. The separate [persistent-burden flag](#persistent-burden) covers that case; it has not yet been run on the published county data (see the [roadmap](ROADMAP.md)).
- Births with an item unknown or not stated are left out of that indicator's denominator. How much this matters has not yet been measured; a sensitivity analysis is planned.

## References

- Brown CC et al. Geographic hotspots for low birthweight: an analysis of counties with persistently high rates. *Inquiry*. 2020;57.
- Benjamini Y, Hochberg Y. Controlling the false discovery rate. *J R Stat Soc B*. 1995.
- Spiegelhalter DJ. Funnel plots for comparing institutional performance. *Stat Med*. 2005.
- Farrington CP et al. A statistical algorithm for the early detection of outbreaks of infectious disease. *J R Stat Soc A*. 1996.
- National Center for Health Statistics. Data presentation standards for proportions (reliability of rates based on fewer than 20 events).
- Radke SM, Smiens L, Ryckman KK, Gruca TS. Closure of labor and delivery units in rural counties is associated with reduced adequacy of prenatal care. *J Rural Health*. 2023;39(4):746–755.
