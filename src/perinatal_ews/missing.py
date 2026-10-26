"""Missing-data sensitivity: do alerts depend on how unknown items are handled?

By default, births whose item is "Unknown or Not Stated" are left out of the
indicator's denominator (as in NCHS reports). The other defensible choice is
to count them as births without the outcome. `unknown_sensitivity` runs
detection both ways on the same tidy table and lists, for every area,
indicator and subgroup, the flag under each choice and whether it changed.

The input must have the `unknown` column written by `ingest.wonder_to_tidy`
with its default setting (unknowns left out). Do not pass a table ingested
with `--unknown-in-denominator`: the unknowns would be counted twice.

Under the "included" choice, an area-year whose unknown count is missing
(suppressed) becomes unusable, matching `wonder_to_tidy`, so an area can move
to "insufficient data" for that reason alone; `unknown_missing` marks it.

For an indicator with an `unknown_as_case` rule in its config (gestational
hypertension: the item is unknown but eclampsia is checked), and a tidy table
with the `unknown_as_case` column (`ingest-wonder --unknown-as-case-file`), a
third variant is added: those births are counted as cases, and the remaining
unknowns stay out of the denominator. Its columns end in `_as_case`;
`changed_as_case` compares it with the default. Other indicators get no value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .detect import LEVELS, detect

KEYS = ["indicator", "subgroup", "geo_id"]


def unknown_in_denominator(tidy: pd.DataFrame) -> pd.DataFrame:
    """Copy of `tidy` with births of unknown status added to each denominator."""
    if "unknown" not in tidy.columns:
        raise ValueError("tidy table has no 'unknown' column; ingest with ingest-wonder (default settings)")
    out = tidy.copy()
    unk = pd.to_numeric(out["unknown"], errors="coerce")
    out["denominator"] = out["denominator"] + unk
    out.loc[out["denominator"].isna(), "numerator"] = np.nan
    return out


def rule_indicators(config: dict) -> list[str]:
    """Indicators whose config has an `unknown_as_case` rule."""
    return [k for k, v in config.get("indicators", {}).items() if (v.get("wonder") or {}).get("unknown_as_case")]


def unknown_as_cases(tidy: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Copy of `tidy` with the `unknown_as_case` births counted as cases (numerator and denominator).

    Only indicators with an `unknown_as_case` rule change; for them a missing
    (suppressed or not downloaded) count makes the row unusable.
    """
    if "unknown_as_case" not in tidy.columns:
        raise ValueError("tidy table has no 'unknown_as_case' column; ingest with --unknown-as-case-file")
    out = tidy.copy()
    rows = out["indicator"].isin(rule_indicators(config))
    add = pd.to_numeric(out.loc[rows, "unknown_as_case"], errors="coerce")
    out.loc[rows, "numerator"] = out.loc[rows, "numerator"] + add
    out.loc[rows, "denominator"] = out.loc[rows, "denominator"] + add
    return out


def unknown_sensitivity(
    tidy: pd.DataFrame,
    config: dict,
    target_year: int | None = None,
    subgroups: list[str] | None = None,
) -> pd.DataFrame:
    """Compare detection with unknowns left out of the denominator and with them included.

    Returns one row per area, indicator and subgroup with the target-year
    unknown share, the rate, z and level under each choice
    (`*_excluded`, `*_included`), `changed` (the level differs) and
    `change` (e.g. "alert -> watch"). Rows that changed come first.
    """
    target_year = int(target_year or tidy["year"].max())
    base = detect(tidy, config, target_year=target_year, subgroups=subgroups)
    alt = detect(unknown_in_denominator(tidy), config, target_year=target_year, subgroups=subgroups)
    cols = ["rate", "z", "level"]
    if base.empty:
        return pd.DataFrame(columns=KEYS + ["geo_name", "state", "year", "unknown", "unknown_share",
                                            "unknown_missing"] + [f"{c}_{s}" for s in ("excluded", "included")
                                                                  for c in cols] + ["changed", "change"])
    out = base[KEYS + ["geo_name", "state", "year"] + cols].merge(
        alt[KEYS + cols], on=KEYS, how="left", suffixes=("_excluded", "_included"))

    t = tidy[tidy["year"] == target_year].set_index(KEYS)
    unk = pd.to_numeric(t["unknown"], errors="coerce")
    known = t["denominator"]
    idx = pd.MultiIndex.from_frame(out[KEYS])
    out["unknown"] = unk.reindex(idx).to_numpy()
    known = known.reindex(idx).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        out["unknown_share"] = out["unknown"] / (known + out["unknown"])
    out["unknown_missing"] = np.isnan(out["unknown"].to_numpy(float)) & ~np.isnan(known.astype(float))

    for s in ("excluded", "included"):
        out[f"level_{s}"] = pd.Categorical(out[f"level_{s}"].astype(str), LEVELS, ordered=True)
    out["changed"] = out["level_excluded"] != out["level_included"]
    out["change"] = np.where(out["changed"],
                             out["level_excluded"].astype(str) + " -> " + out["level_included"].astype(str), "")
    order = (KEYS + ["geo_name", "state", "year", "unknown", "unknown_share", "unknown_missing"]
             + [f"{c}_{s}" for s in ("excluded", "included") for c in cols] + ["changed", "change"])

    rules = rule_indicators(config)
    if "unknown_as_case" in tidy.columns and rules:
        alt2 = detect(unknown_as_cases(tidy, config), config, target_year=target_year, subgroups=subgroups)
        alt2 = alt2[alt2["indicator"].isin(rules)]
        out = out.merge(alt2[KEYS + cols].rename(columns={c: f"{c}_as_case" for c in cols}), on=KEYS, how="left")
        out["unknown_as_case"] = pd.to_numeric(t["unknown_as_case"], errors="coerce").reindex(idx).to_numpy()
        applies = out["indicator"].isin(rules).to_numpy()
        out.loc[~applies, "unknown_as_case"] = np.nan
        lvl = out["level_as_case"].astype(object)
        out["changed_as_case"] = applies & (lvl.astype(str) != out["level_excluded"].astype(str))
        out["change_as_case"] = np.where(out["changed_as_case"], out["level_excluded"].astype(str) + " -> "
                                         + lvl.astype(str), "")
        order += ["unknown_as_case"] + [f"{c}_as_case" for c in cols] + ["changed_as_case", "change_as_case"]
        out["_any"] = out["changed"] | out["changed_as_case"]
    else:
        out["_any"] = out["changed"]
    out = out.sort_values(["_any", "changed", "level_excluded", "indicator", "subgroup", "geo_id"],
                          ascending=[False, False, True, True, True, True])
    return out[order].reset_index(drop=True)
