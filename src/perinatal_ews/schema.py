"""The tidy input schema every data source is converted into.

One row = one indicator, for one geography, one year and one subgroup.

    geo_id       county FIPS code as a 5-character string (e.g. "25017")
    geo_name     human-readable name
    state        2-letter state abbreviation or state name
    year         integer
    indicator    key from the config `indicators` block
    subgroup     "All" for the total population, otherwise a subgroup label
    numerator    births with the outcome
    denominator  births with a known value for the outcome
"""
from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = [
    "geo_id", "geo_name", "state", "year", "indicator", "subgroup", "numerator", "denominator",
]
TOTAL_SUBGROUP = "All"


class SchemaError(ValueError):
    pass


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """Check and normalise a tidy table. Returns a cleaned copy."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaError(f"missing required columns: {missing}")

    out = df[REQUIRED_COLUMNS + [c for c in df.columns if c not in REQUIRED_COLUMNS]].copy()
    out["geo_id"] = out["geo_id"].astype(str).str.strip().str.zfill(5)
    out["year"] = pd.to_numeric(out["year"], errors="raise").astype(int)
    for col in ("numerator", "denominator"):
        out[col] = pd.to_numeric(out[col], errors="coerce")

    bad = out["numerator"] > out["denominator"]
    if bad.any():
        raise SchemaError(f"{int(bad.sum())} rows have numerator > denominator")
    if (out["denominator"] < 0).any() or (out["numerator"] < 0).any():
        raise SchemaError("negative counts found")

    key = ["geo_id", "year", "indicator", "subgroup"]
    dupes = out.duplicated(key)
    if dupes.any():
        raise SchemaError(f"{int(dupes.sum())} duplicate rows for key {key}")
    return out.reset_index(drop=True)
