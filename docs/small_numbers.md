# Small numbers: state level, pooled years and combined groups (v0.6)

Added in response to feedback from a state maternal and child health epidemiologist ([issue #1](https://github.com/karantejpal12/perinatal-ews/issues/1)): county-level subgroup analysis by race often runs out of power, especially when broad groups are disaggregated (Native Hawaiian, Other Pacific Islander, Filipino, Japanese); state teams usually work at state level, combine racial and ethnic groups when counts are too small, and pool years, taking care with years when data are unavailable (for example Hawaii PRAMS 2017–2018).

## What the tool now does

1. **State level.** `perinatal-ews run --level state` sums county rows to states. State-level input, such as a CDC WONDER export grouped by state, is used as is.
2. **Pooled years.** `perinatal-ews pooled` pools a window of years (default 3) for every place, group and indicator. A year that is missing, suppressed (fewer than 10 events) or listed with `--unavailable-years` is skipped and reported in the output, never counted as zero. An estimate needs at least two years with data. With `--fill-window` the window reaches further back to collect enough available years (for example 2016 and 2019 when 2017–2018 are unavailable).
3. **Combined groups.** Groups are combined year by year, before pooling. If any member's count is suppressed in a year, the combined count for that year is treated as missing (a suppressed cell hides a value from 1 to 9, so the sum is unknown). Combined groups requested directly from the data source are used as they are. Each estimate is reported as itself if reliable (20 or more events, the NCHS threshold); otherwise as the first reliable combined group it belongs to, clearly labelled; otherwise as "insufficient data". Default combinations follow federal practice: Native Hawaiian or Other Pacific Islander; Asian; Asian or Pacific Islander. Pass a YAML file with `--combine` to use local practice.
4. **Change over time.** The latest pooled window is compared with the previous, non-overlapping window (rate ratio and 95% confidence interval), only when both estimates are reliable.

## Real-data example: all states by mother's race, 2016–2024

Data: CDC WONDER Natality, 2016–2024 expanded, grouped by state, year and mother's single race (15 groups), for the four indicators; combined groups were requested directly from WONDER so suppression in a member group does not affect them. The explorer's state view shows the 2022–2024 pooled results for every state, with the comparison against 2019–2021.

Across all states and indicators in 2022–2024: 2,409 pooled estimates are reliable, 209 groups are shown as insufficient data, and the rest are reported through a combined group.

Hawaii, preterm birth, pooled 2022–2024: all births 10.0%; Filipino 12.6%; Hawaiian 13.6%; Samoan 10.8%; Other Pacific Islander 12.2%; Japanese 9.4%; Chinese 7.4%; White 7.5%. Asian Indian, Vietnamese and Guamanian or Chamorro mothers had too few events in most years and are reported through the Asian and Native Hawaiian or Other Pacific Islander combined groups; American Indian or Alaska Native mothers have insufficient data.

## Limitations

- Race is the mother's self-reported single race on the birth certificate. Mothers who report more than one race are counted in "More than one race", not in each group. In Hawaii this group is large (about 38% of births in 2024), so single-race counts understate Native Hawaiian mothers. State analysts with access to multiple-race or "any mention" coding should use it.
- Race groups include all Hispanic origins.
- Changes between pooled windows are not adjusted for national trends. Gestational hypertension, for example, rose in almost every group nationally.
- Public data suppress counts of 1 to 9, which limits what can be combined after the fact; state teams with unsuppressed data will get more groups reported directly.
- The tool currently uses birth certificate data, which are available every year. The handling of unavailable years is built for sources with gaps, such as PRAMS.
