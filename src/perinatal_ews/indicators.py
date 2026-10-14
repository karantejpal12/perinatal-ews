"""Rates, confidence intervals and NCHS-style reliability rules."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def wilson_interval(k, n, level: float = 0.95):
    """Wilson score interval for a binomial proportion. Works on arrays; NaN where n == 0."""
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)
    z = stats.norm.ppf(0.5 + level / 2)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = k / n
        denom = 1 + z**2 / n
        centre = (p + z**2 / (2 * n)) / denom
        half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    lo, hi = centre - half, centre + half
    lo = np.where(n > 0, lo, np.nan)
    hi = np.where(n > 0, hi, np.nan)
    return lo, hi


def compute_rates(tidy: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Add rate, 95% CI and reliability columns to a tidy table."""
    det = config["detection"]
    out = tidy.copy()
    with np.errstate(invalid="ignore", divide="ignore"):
        out["rate"] = out["numerator"] / out["denominator"]
    out["ci_low"], out["ci_high"] = wilson_interval(out["numerator"], out["denominator"])
    out["suppressed"] = out["numerator"].isna() | (out["numerator"] < det["min_numerator_shown"])
    out["reliable"] = ~out["suppressed"] & (out["numerator"] >= det["min_numerator_reliable"])
    return out


def reference_rates(tidy: pd.DataFrame, by: tuple[str, ...] = ("indicator", "subgroup", "year")) -> pd.DataFrame:
    """Pooled rate across all geographies with data (the peer reference)."""
    ok = tidy.dropna(subset=["numerator", "denominator"])
    ref = ok.groupby(list(by), as_index=False)[["numerator", "denominator"]].sum()
    ref["rate"] = ref["numerator"] / ref["denominator"]
    return ref
