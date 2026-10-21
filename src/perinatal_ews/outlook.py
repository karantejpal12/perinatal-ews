"""Full-year outlook: where each state is likely to finish the current year.

After each monthly update the tool knows January to month *m* of the current
year. This module projects the rest of the year and estimates, for every state
and indicator, the probability that the full year will be flagged.

Method
1. Seasonal step. For every state, indicator and complete past year, compare
   the rate in the remaining months (m+1 to December) with the rate in
   January to *m* (difference in log-odds, ``d``), and the remaining months'
   births with January-to-*m* births.
2. Projection. For the current year, the remaining-months rate is the
   year-to-date rate shifted by the state's typical ``d`` over the last five
   complete years, shrunk toward the all-state average with an empirical-Bayes
   weight (states with noisy histories borrow more from the average).
   Remaining births follow the state's recent births ratio.
3. Uncertainty. The spread of the projection error is learned from past years
   (a national part shared by all states in a year, and a state part), then
   the remaining months are simulated many times, each with binomial noise.
4. Flag probability. Each simulated full year is passed through the standard
   detection method, so the probability means "chance that the full year
   will be flagged by perinatal-ews", using exactly the same rules as before.

``backtest`` repeats this for past years using only what was known at month
*m* of each year, and compares the result with how the full year actually
turned out. Every monthly update stores its outlook, so the forecast can be
scored openly once the year is complete.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .detect import detect
from .forecast import _metrics
from .schema import TOTAL_SUBGROUP

KEY = ["geo_id", "geo_name", "state", "indicator", "year"]


def _logit(n, d):
    n = np.asarray(n, float)
    d = np.asarray(d, float)
    return np.log((n + 0.5) / (d - n + 0.5))


def _expit(x):
    return 1 / (1 + np.exp(-x))


def remaining_table(ytd: pd.DataFrame, full: pd.DataFrame) -> pd.DataFrame:
    """January-to-m and remaining-months counts for every state, indicator and complete year."""
    a = ytd[ytd["subgroup"] == TOTAL_SUBGROUP][KEY + ["numerator", "denominator"]]
    b = full[full["subgroup"] == TOTAL_SUBGROUP][KEY + ["numerator", "denominator"]]
    t = a.merge(b, on=KEY, suffixes=("_ytd", "_full"))
    t["num_rem"] = t["numerator_full"] - t["numerator_ytd"]
    t["den_rem"] = t["denominator_full"] - t["denominator_ytd"]
    ok = t[["numerator_ytd", "denominator_ytd", "num_rem", "den_rem"]].notna().all(axis=1) & (t["den_rem"] > 0) \
        & (t["num_rem"] >= 0)
    t = t[ok].copy()
    t["lr_ytd"] = _logit(t["numerator_ytd"], t["denominator_ytd"])
    t["lr_rem"] = _logit(t["num_rem"], t["den_rem"])
    t["d"] = t["lr_rem"] - t["lr_ytd"]
    t["births_ratio"] = t["den_rem"] / t["denominator_ytd"]
    t["var_d"] = (1 / (t["numerator_ytd"] + 0.5) + 1 / (t["denominator_ytd"] - t["numerator_ytd"] + 0.5)
                  + 1 / (t["num_rem"] + 0.5) + 1 / (t["den_rem"] - t["num_rem"] + 0.5))
    return t


def seasonal_step(rem: pd.DataFrame, year: int, history: int = 5) -> pd.DataFrame:
    """Shrunk typical seasonal step (d) and births ratio per state and indicator, from years before `year`."""
    h = rem[(rem["year"] < year) & (rem["year"] >= year - history)]
    rows = []
    for ind, g in h.groupby("indicator"):
        nat = g.groupby("year")["d"].mean()
        g = g.assign(d_dev=g["d"] - g["year"].map(nat))      # state step net of that year's national step
        st = g.groupby("geo_id").agg(dev_mean=("d_dev", "mean"), n=("d_dev", "size"), within=("d_dev", "var"),
                                     br=("births_ratio", lambda s: s.tail(3).mean()))
        within = float(st["within"].dropna().mean()) if st["within"].notna().any() else 0.0
        between_obs = float(st["dev_mean"].var()) if len(st) > 1 else 0.0
        tau2 = max(between_obs - within / max(st["n"].mean(), 1), 0.0)
        st["w"] = tau2 / (tau2 + within / st["n"]) if tau2 > 0 else 0.0
        st["d_hat"] = float(nat.mean()) + st["w"] * st["dev_mean"]
        st["indicator"] = ind
        rows.append(st.reset_index())
    return pd.concat(rows, ignore_index=True)


def _deterministic(rem_or_ytd: pd.DataFrame, step: pd.DataFrame) -> pd.DataFrame:
    """Point projection of the remaining months for each state and indicator."""
    t = rem_or_ytd.merge(step[["geo_id", "indicator", "d_hat", "br"]], on=["geo_id", "indicator"], how="inner")
    t["lr_ytd"] = _logit(t["numerator_ytd"], t["denominator_ytd"])
    t["lr_rem_hat"] = t["lr_ytd"] + t["d_hat"]
    t["den_rem_hat"] = np.round(t["denominator_ytd"] * t["br"])
    return t


def error_components(rem: pd.DataFrame, years: list[int], history: int = 5) -> pd.DataFrame:
    """Projection errors for past years: national (shared within a year) and state components, by indicator."""
    out = []
    for y in years:
        step = seasonal_step(rem, y, history)
        cur = rem[rem["year"] == y]
        p = _deterministic(cur, step)
        p["err"] = p["lr_rem"] - p["lr_rem_hat"]
        out.append(p[["geo_id", "indicator", "year", "err", "num_rem", "den_rem"]])
    e = pd.concat(out, ignore_index=True)
    e["samp_var"] = 1 / (e["num_rem"] + 0.5) + 1 / (e["den_rem"] - e["num_rem"] + 0.5)
    return e


def variance_from_errors(err: pd.DataFrame) -> dict:
    """Per-indicator variance of the national and the state part of the projection error (sampling noise removed)."""
    res = {}
    for ind, g in err.groupby("indicator"):
        nat = g.groupby("year")["err"].mean()
        state_part = g["err"] - g["year"].map(nat)
        var_state = max(float((state_part ** 2).mean() - g["samp_var"].mean()), 0.0)
        var_nat = float((nat ** 2).mean()) if len(nat) > 1 else 0.0
        res[ind] = {"var_national": var_nat, "var_state": var_state}
    return res


def simulate(ytd_now: pd.DataFrame, full_past: pd.DataFrame, step: pd.DataFrame, variances: dict, config: dict,
             year: int, n_draws: int = 300, seed: int = 0) -> pd.DataFrame:
    """Simulate the full year `year` and run detection on each draw."""
    rng = np.random.default_rng(seed)
    cur = ytd_now[(ytd_now["year"] == year) & (ytd_now["subgroup"] == TOTAL_SUBGROUP)]
    cur = cur.rename(columns={"numerator": "numerator_ytd", "denominator": "denominator_ytd"})
    p = _deterministic(cur.dropna(subset=["numerator_ytd", "denominator_ytd"]), step).reset_index(drop=True)
    past = full_past[(full_past["year"] < year) & (full_past["subgroup"] == TOTAL_SUBGROUP)]
    inds = sorted(p["indicator"].unique())
    flag = np.zeros(len(p))
    alert = np.zeros(len(p))
    rates = np.zeros((n_draws, len(p)))
    key = list(zip(p["geo_id"], p["indicator"]))
    for i in range(n_draws):
        nat = {k: rng.normal(0, np.sqrt(variances.get(k, {}).get("var_national", 0.0))) for k in inds}
        sd_state = p["indicator"].map(lambda k: np.sqrt(variances.get(k, {}).get("var_state", 0.0))).to_numpy()
        lr = p["lr_rem_hat"].to_numpy() + p["indicator"].map(nat).to_numpy() + rng.normal(0, 1, len(p)) * sd_state
        rem_num = rng.binomial(p["den_rem_hat"].astype(int).to_numpy(), _expit(lr))
        num = p["numerator_ytd"].to_numpy() + rem_num
        den = p["denominator_ytd"].to_numpy() + p["den_rem_hat"].to_numpy()
        rates[i] = num / den
        sim = p[["geo_id", "geo_name", "state", "indicator"]].assign(year=year, subgroup=TOTAL_SUBGROUP,
                                                                     numerator=num, denominator=den)
        d = detect(pd.concat([past, sim], ignore_index=True), config, target_year=year)
        lv = d.set_index(["geo_id", "indicator"])["level"]
        levels = np.array([lv.get(k, "insufficient data") for k in key])
        flag += np.isin(levels, ["alert", "watch"])
        alert += levels == "alert"
    p["rate_ytd"] = p["numerator_ytd"] / p["denominator_ytd"]
    p["projected_rate"] = np.median(rates, axis=0)
    p["projected_low80"] = np.quantile(rates, 0.10, axis=0)
    p["projected_high80"] = np.quantile(rates, 0.90, axis=0)
    p["p_flag"] = flag / n_draws
    p["p_alert"] = alert / n_draws
    p["year"] = year
    cols = ["geo_id", "geo_name", "state", "indicator", "year", "rate_ytd", "projected_rate", "projected_low80",
            "projected_high80", "p_flag", "p_alert"]
    return p[cols]


def _year_is_complete(ytd: pd.DataFrame, full: pd.DataFrame) -> bool:
    """True when the January-to-m window is the whole year (m = December): past years' counts equal their full years."""
    a = ytd[ytd["subgroup"] == TOTAL_SUBGROUP][KEY + ["denominator"]]
    b = full[full["subgroup"] == TOTAL_SUBGROUP][KEY + ["denominator"]]
    t = a.merge(b, on=KEY, suffixes=("_ytd", "_full")).dropna()
    return len(t) > 0 and bool((t["denominator_full"] == t["denominator_ytd"]).all())


def _complete_year(ytd: pd.DataFrame, full_past: pd.DataFrame, config: dict, year: int) -> pd.DataFrame:
    """Outlook for a year whose months are all known: the actual rate and detection result, with no range."""
    cur = ytd[(ytd["year"] == year) & (ytd["subgroup"] == TOTAL_SUBGROUP)].dropna(subset=["numerator", "denominator"])
    past = full_past[(full_past["year"] < year) & (full_past["subgroup"] == TOTAL_SUBGROUP)]
    d = detect(pd.concat([past, cur], ignore_index=True), config, target_year=year)
    lv = d[d["subgroup"] == TOTAL_SUBGROUP].set_index(["geo_id", "indicator"])["level"]
    levels = np.array([lv.get(k, "insufficient data") for k in zip(cur["geo_id"], cur["indicator"])])
    p = cur[["geo_id", "geo_name", "state", "indicator", "year"]].reset_index(drop=True)
    rate = (cur["numerator"] / cur["denominator"]).to_numpy()
    p["rate_ytd"] = p["projected_rate"] = p["projected_low80"] = p["projected_high80"] = rate
    p["p_flag"] = np.isin(levels, ["alert", "watch"]).astype(float)
    p["p_alert"] = (levels == "alert").astype(float)
    return p


def outlook(ytd: pd.DataFrame, full: pd.DataFrame, config: dict, year: int, backtest_years: list[int],
            history: int = 5, n_draws: int = 300, seed: int = 0) -> pd.DataFrame:
    """Full-year outlook for `year`, with error variances learned from `backtest_years`.

    If January to m already covers the whole year, nothing is simulated: the outlook is the actual year
    (projected rate and range equal to the observed rate, flag probability 0 or 1).
    """
    if _year_is_complete(ytd, full):
        return _complete_year(ytd, full, config, year)
    rem = remaining_table(ytd, full)
    variances = variance_from_errors(error_components(rem, backtest_years, history))
    step = seasonal_step(rem, year, history)
    return simulate(ytd, full, step, variances, config, year, n_draws, seed)


def backtest(ytd: pd.DataFrame, full: pd.DataFrame, config: dict, years: list[int], history: int = 5,
             n_draws: int = 200, seed: int = 0) -> tuple[pd.DataFrame, dict]:
    """Outlook for each past year using only January to m, scored against the actual full year.

    The error variances used for year t come from the other backtest years only.
    Baseline comparison: "the full year will be flagged if the year so far is flagged".
    """
    rem = remaining_table(ytd, full)
    err = error_components(rem, years, history)
    rows = []
    for t in years:
        variances = variance_from_errors(err[err["year"] != t])
        step = seasonal_step(rem, t, history)
        sim = simulate(ytd, full, step, variances, config, t, n_draws, seed + t)
        actual = detect(full[full["year"] <= t], config, target_year=t)
        actual = actual[actual["subgroup"] == TOTAL_SUBGROUP].set_index(["geo_id", "indicator"])
        so_far = detect(ytd[ytd["year"] <= t], config, target_year=t)
        so_far = so_far[so_far["subgroup"] == TOTAL_SUBGROUP].set_index(["geo_id", "indicator"])
        k = list(zip(sim["geo_id"], sim["indicator"]))
        sim["actual_level"] = [actual["level"].get(x) for x in k]
        sim["actual_rate"] = [actual["rate"].get(x) for x in k]
        sim["ytd_level"] = [so_far["level"].get(x) for x in k]
        rows.append(sim)
    bt = pd.concat(rows, ignore_index=True).dropna(subset=["actual_level"])
    y = bt["actual_level"].isin(["alert", "watch"]).astype(float)
    ytd_flag = bt["ytd_level"].isin(["alert", "watch"]).astype(float)
    inside = (bt["actual_rate"] >= bt["projected_low80"]) & (bt["actual_rate"] <= bt["projected_high80"])

    def acc(pred):
        tp = float(((pred == 1) & (y == 1)).sum())
        return {"sensitivity": tp / max(float(y.sum()), 1), "precision": tp / max(float(pred.sum()), 1)}

    summary = {
        "years": [int(x) for x in years], "state_indicators": int(len(bt)), "full_year_flags": int(y.sum()),
        "interval80_coverage": round(float(inside.mean()), 3),
        "outlook": {k: (round(float(v), 4) if isinstance(v, (float, np.floating)) and np.isfinite(v) else v)
                    for k, v in _metrics(y, bt["p_flag"]).items()},
        "outlook_at_50pct": {k: round(v, 3) for k, v in acc((bt["p_flag"] >= 0.5).astype(float)).items()},
        "year_so_far_flag": {k: round(v, 3) for k, v in acc(ytd_flag).items()},
        "brier_year_so_far_flag": round(float(((ytd_flag - y) ** 2).mean()), 4),
    }
    return bt, summary


def outlook_with_backtest(ytd: pd.DataFrame, full: pd.DataFrame, config: dict, year: int,
                          backtest_years: list[int], months_known: int, n_draws: int = 300,
                          backtest_draws: int = 150) -> tuple[pd.DataFrame, dict | None]:
    """The monthly update's outlook step: the outlook for `year` and its backtest summary.

    When January to m already covers the whole year (data through December), nothing remains to project,
    so the backtest is skipped and the summary is None.
    """
    ol = outlook(ytd, full, config, year, backtest_years, n_draws=n_draws)
    if _year_is_complete(ytd, full):
        return ol, None
    _, bt = backtest(ytd, full, config, backtest_years, n_draws=backtest_draws)
    bt["months_known"] = months_known
    return ol, bt


def score_archived(archived: pd.DataFrame, actual: pd.DataFrame) -> dict:
    """Score an outlook saved earlier against the completed year's detection results."""
    a = actual[actual["subgroup"] == TOTAL_SUBGROUP].set_index(["geo_id", "indicator"])
    k = list(zip(archived["geo_id"], archived["indicator"]))
    lv = pd.Series([a["level"].get(x) for x in k])
    rt = pd.Series([a["rate"].get(x) for x in k])
    ok = lv.notna().to_numpy()
    y = lv[ok].isin(["alert", "watch"]).astype(float).to_numpy()
    arch = archived.reset_index(drop=True)[ok]
    inside = ((rt[ok].to_numpy() >= arch["projected_low80"].to_numpy())
              & (rt[ok].to_numpy() <= arch["projected_high80"].to_numpy()))
    m = _metrics(y, arch["p_flag"].to_numpy())
    return {"state_indicators": int(ok.sum()), "full_year_flags": int(y.sum()),
            "interval80_coverage": round(float(inside.mean()), 3),
            **{k: (round(float(v), 4) if isinstance(v, (float, np.floating)) and np.isfinite(v) else v)
               for k, v in m.items()}}
