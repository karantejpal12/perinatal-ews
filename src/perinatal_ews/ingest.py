"""Convert raw exports into the tidy schema.

CDC WONDER natality exports are tab-delimited text with a "Notes" column,
subtotal rows marked "Total" in Notes, and a footer that starts with a
line of dashes. Small counts appear as "Suppressed". This module reads
one export per indicator, grouped by County, Year and the indicator's
category column (and optionally a subgroup column).
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pandas as pd

from .schema import TOTAL_SUBGROUP, validate

NON_NUMERIC = {"Suppressed", "Not Available", "Not Applicable", "Missing", "Unreliable", ""}


def read_wonder_text(path: str | Path) -> pd.DataFrame:
    """Read a CDC WONDER export, dropping the footer and subtotal rows."""
    lines = []
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            if line.startswith('"---"') or line.startswith("---"):
                break
            lines.append(line)
    df = pd.read_csv(io.StringIO("".join(lines)), sep="\t", dtype=str, quoting=csv.QUOTE_MINIMAL)
    df.columns = [c.strip() for c in df.columns]
    if "Notes" in df.columns:
        df = df[df["Notes"].fillna("").str.strip() == ""].drop(columns="Notes")
    return df.reset_index(drop=True)


def _parse_count(value: str) -> float:
    v = (value or "").strip().replace(",", "")
    if v in NON_NUMERIC:
        return float("nan")
    return float(v)


def _split_county(label: str) -> tuple[str, str]:
    """'Middlesex County, MA' -> ('Middlesex County', 'MA')."""
    if "," in label:
        name, state = label.rsplit(",", 1)
        return name.strip(), state.strip()
    return label.strip(), ""


def wonder_to_tidy(
    path: str | Path,
    indicator: str,
    config: dict,
    subgroup_column: str | None = None,
    count_column: str = "Births",
) -> pd.DataFrame:
    """Turn one WONDER export into tidy rows for one indicator.

    The export must be grouped by County and Year plus the indicator's
    `group_column` from the config (and `subgroup_column`, if given).
    """
    spec = config["indicators"][indicator]["wonder"]
    raw = read_wonder_text(path)

    group_col = spec["group_column"]
    for col in ("County", "County Code", "Year", group_col, count_column):
        if col not in raw.columns:
            raise ValueError(f"{path}: expected column '{col}', found {list(raw.columns)}")
    if subgroup_column and subgroup_column not in raw.columns:
        raise ValueError(f"{path}: subgroup column '{subgroup_column}' not found")

    raw = raw[~raw[group_col].isin(spec.get("exclude_values", []))].copy()
    raw["count"] = raw[count_column].map(_parse_count)
    raw["is_case"] = raw[group_col].isin(spec["numerator_values"])
    raw["subgroup"] = raw[subgroup_column] if subgroup_column else TOTAL_SUBGROUP

    unknown = set(raw[group_col]) - set(spec["numerator_values"])
    # Everything not excluded and not a case is treated as a non-case; surface it so labels can be checked.
    raw.attrs["non_case_categories"] = sorted(unknown)

    keys = ["County Code", "County", "Year", "subgroup"]
    # A suppressed cell makes the whole county-year unusable rather than silently low.
    agg = raw.groupby(keys, dropna=False).agg(
        numerator=("count", lambda s: s[raw.loc[s.index, "is_case"]].sum(min_count=0)),
        denominator=("count", "sum"),
        any_suppressed=("count", lambda s: s.isna().any()),
    ).reset_index()
    agg.loc[agg["any_suppressed"], ["numerator", "denominator"]] = float("nan")

    names = agg["County"].map(_split_county)
    tidy = pd.DataFrame({
        "geo_id": agg["County Code"],
        "geo_name": [n for n, _ in names],
        "state": [s for _, s in names],
        "year": agg["Year"],
        "indicator": indicator,
        "subgroup": agg["subgroup"],
        "numerator": agg["numerator"],
        "denominator": agg["denominator"],
    })
    if subgroup_column:
        totals = tidy.groupby(["geo_id", "geo_name", "state", "year", "indicator"], as_index=False)[
            ["numerator", "denominator"]].agg(lambda s: s.sum(skipna=False))
        totals["subgroup"] = TOTAL_SUBGROUP
        tidy = pd.concat([tidy, totals], ignore_index=True)
    out = validate(tidy)
    out.attrs["non_case_categories"] = raw.attrs["non_case_categories"]
    return out


def load_tidy_csv(path: str | Path) -> pd.DataFrame:
    return validate(pd.read_csv(path, dtype={"geo_id": str}))
