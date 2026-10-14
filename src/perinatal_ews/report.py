"""Self-contained HTML bulletin for one run of the early-warning system."""
from __future__ import annotations

from html import escape

import numpy as np
import pandas as pd

from . import __version__
from .detect import detect
from .equity import subgroup_gaps
from .monitor import backtest, data_quality, distribution_drift, evaluate_against_truth
from .schema import TOTAL_SUBGROUP

CSS = """
/* Layout: a single reading column of bulletin sections, summary first, system health last */
:root {
  --bg: #f6f7f9; --surface: #ffffff; --ink: #14181f; --ink-2: #4a5160; --ink-3: #6b7280;
  --rule: #dfe3ea; --accent: #2a78d6; --expected: #8a919e; --band: #eef1f5;
  --alert: #d03b3b; --alert-bg: #fbeaea; --watch: #9a6a00; --watch-bg: #fdf3dc;
  --stable: #2f7d32; --stable-bg: #e7f3e8; --synthetic-bg: #e9f0fb; --synthetic-ink: #1c4f95;
  --font-body: "Public Sans", "Segoe UI", system-ui, sans-serif;
  --font-data: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #121418; --surface: #1a1d22; --ink: #eceef2; --ink-2: #b9bfca; --ink-3: #9198a4;
  --rule: #2c313a; --accent: #3987e5; --expected: #8a919e; --band: #22262d;
  --alert: #e66767; --alert-bg: #3a2222; --watch: #e0a83a; --watch-bg: #352c18;
  --stable: #5cbf60; --stable-bg: #1d2e1e; --synthetic-bg: #1b2a40; --synthetic-ink: #9ec5f4;
  color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #121418; --surface: #1a1d22; --ink: #eceef2; --ink-2: #b9bfca; --ink-3: #9198a4;
  --rule: #2c313a; --accent: #3987e5; --expected: #8a919e; --band: #22262d;
  --alert: #e66767; --alert-bg: #3a2222; --watch: #e0a83a; --watch-bg: #352c18;
  --stable: #5cbf60; --stable-bg: #1d2e1e; --synthetic-bg: #1b2a40; --synthetic-ink: #9ec5f4;
  color-scheme: dark; }
body { background: var(--bg); color: var(--ink); font-family: var(--font-body); font-size: 15px; line-height: 1.55; }
.page { max-width: 1080px; margin: 0 auto; padding-block: 32px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: flex; flex-direction: column; gap: 40px; }
header { display: flex; flex-direction: column; gap: 10px; }
.eyebrow { font-family: var(--font-data); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--ink-3); }
h1 { font-size: clamp(26px, 4vw, 36px); line-height: 1.15; margin: 0; font-weight: 700; text-wrap: balance; }
h2 { font-size: 20px; margin: 0; font-weight: 650; text-wrap: balance; }
p { margin: 0; max-width: 68ch; color: var(--ink-2); }
.synthetic { background: var(--synthetic-bg); color: var(--synthetic-ink); padding: 10px 14px; border-radius: 6px; font-size: 14px; max-width: 72ch; }
section { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1px; background: var(--rule); border: 1px solid var(--rule); border-radius: 8px; overflow: hidden; }
.kpi { background: var(--surface); padding: 14px 16px; display: flex; flex-direction: column; gap: 2px; }
.kpi b { font-family: var(--font-data); font-size: 26px; font-weight: 500; font-variant-numeric: tabular-nums; }
.kpi span { font-size: 13px; color: var(--ink-3); }
.table-wrap { overflow-x: auto; border: 1px solid var(--rule); border-radius: 8px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th { text-align: left; font-weight: 600; font-size: 12px; letter-spacing: .04em; text-transform: uppercase; color: var(--ink-3); padding: 10px 12px; border-bottom: 1px solid var(--rule); white-space: nowrap; }
td { padding: 10px 12px; border-bottom: 1px solid var(--rule); vertical-align: middle; }
tr:last-child td { border-bottom: 0; }
td.num, th.num { text-align: right; font-family: var(--font-data); font-variant-numeric: tabular-nums; white-space: nowrap; }
.place { font-weight: 600; }
.place small { display: block; font-weight: 400; color: var(--ink-3); font-size: 12px; }
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 2px 9px 2px 7px; border-radius: 999px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.pill svg { width: 12px; height: 12px; }
.pill.alert { background: var(--alert-bg); color: var(--alert); }
.pill.watch { background: var(--watch-bg); color: var(--watch); }
.pill.stable { background: var(--stable-bg); color: var(--stable); }
.spark { display: block; }
.spark .obs { stroke: var(--accent); }
.spark .dot { fill: var(--accent); stroke: var(--surface); stroke-width: 2; }
.spark .exp { fill: var(--surface); stroke: var(--expected); stroke-width: 2; }
.legend { display: flex; gap: 18px; flex-wrap: wrap; font-size: 13px; color: var(--ink-3); align-items: center; }
.legend i { display: inline-block; width: 16px; height: 2px; background: var(--accent); vertical-align: middle; margin-right: 6px; }
.legend i.ring { width: 9px; height: 9px; border-radius: 50%; background: transparent; border: 2px solid var(--expected); }
.two { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }
.two > * { min-width: 0; }
.chart { background: var(--surface); border: 1px solid var(--rule); border-radius: 8px; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
.chart h3 { margin: 0; font-size: 15px; font-weight: 600; }
.chart svg text { fill: var(--ink-3); font-family: var(--font-data); font-size: 11px; }
.chart .bar { fill: var(--accent); }
.chart .bar:hover { opacity: .8; }
.chart .grid { stroke: var(--rule); }
.note { font-size: 13px; color: var(--ink-3); }
ul.methods { margin: 0; padding-left: 20px; color: var(--ink-2); max-width: 72ch; display: flex; flex-direction: column; gap: 6px; }
footer { font-size: 13px; color: var(--ink-3); border-top: 1px solid var(--rule); padding-top: 16px; }
"""

ICONS = {
    "alert": '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 1 11.5 11h-11z" fill="currentColor"/></svg>',
    "watch": '<svg viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
    "stable": '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 6.5 5 9l5-6" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
}


def _pill(level: str) -> str:
    key = level if level in ICONS else "stable"
    return f'<span class="pill {key}">{ICONS[key]}{escape(level.capitalize())}</span>'


def _pct(x, digits=1) -> str:
    return "–" if x is None or not np.isfinite(x) else f"{100 * x:.{digits}f}%"


def _num(x, fmt="{:,.0f}") -> str:
    return "–" if x is None or not np.isfinite(x) else fmt.format(x)


def _sparkline(history: pd.DataFrame, expected_rate: float, w: int = 132, h: int = 38) -> str:
    """Observed rate by year (line) with the target year's expected rate (ring)."""
    history = history.dropna(subset=["rate"]).sort_values("year")
    if len(history) < 2:
        return ""
    years = history["year"].to_numpy()
    rates = history["rate"].to_numpy()
    lo = min(rates.min(), expected_rate) * 0.95
    hi = max(rates.max(), expected_rate) * 1.05
    pad = 6
    sx = lambda y: pad + (y - years[0]) / max(years[-1] - years[0], 1) * (w - 2 * pad)
    sy = lambda r: h - pad - (r - lo) / max(hi - lo, 1e-9) * (h - 2 * pad)
    pts = " ".join(f"{sx(y):.1f},{sy(r):.1f}" for y, r in zip(years, rates))
    hits = "".join(
        f'<circle cx="{sx(y):.1f}" cy="{sy(r):.1f}" r="7" fill="transparent"><title>{y}: {_pct(r)}</title></circle>'
        for y, r in zip(years, rates))
    ex, ey = sx(years[-1]), sy(expected_rate)
    lx, ly = sx(years[-1]), sy(rates[-1])
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="Rate {years[0]} to {years[-1]}, latest {_pct(rates[-1])} vs expected {_pct(expected_rate)}">'
            f'<polyline class="obs" points="{pts}" fill="none" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle class="exp" cx="{ex:.1f}" cy="{ey:.1f}" r="4"><title>Expected {years[-1]}: {_pct(expected_rate)}</title></circle>'
            f'<circle class="dot" cx="{lx:.1f}" cy="{ly:.1f}" r="4"/>{hits}</svg>')


def _bar_chart(labels: list[str], values: list[float], fmt, title: str, y_label: str,
               w: int = 460, h: int = 200, y_max: float | None = None) -> str:
    """Single-series vertical bar chart with rounded data ends and hover titles."""
    left, right, top, bottom = 44, 8, 10, 30
    vmax = y_max or (max([v for v in values if np.isfinite(v)] + [0]) * 1.15 or 1)
    plot_w, plot_h = w - left - right, h - top - bottom
    step = plot_w / max(len(values), 1)
    bw = min(48, step * 0.55)
    ticks = np.linspace(0, vmax, 5)
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{escape(title)}">']
    for t in ticks:
        y = top + plot_h - t / vmax * plot_h
        parts.append(f'<line class="grid" x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke-width="1"/>')
        parts.append(f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{escape(fmt(t))}</text>')
    for i, (lab, v) in enumerate(zip(labels, values)):
        cx = left + step * (i + 0.5)
        v = v if np.isfinite(v) else 0
        bh = max(v / vmax * plot_h, 0)
        x0, y0, base = cx - bw / 2, top + plot_h - bh, top + plot_h
        r = min(4, bh, bw / 2)
        path = (f"M{x0:.1f},{base:.1f} V{y0 + r:.1f} Q{x0:.1f},{y0:.1f} {x0 + r:.1f},{y0:.1f} "
                f"H{x0 + bw - r:.1f} Q{x0 + bw:.1f},{y0:.1f} {x0 + bw:.1f},{y0 + r:.1f} V{base:.1f} Z")
        parts.append(f'<path class="bar" d="{path}"><title>{escape(lab)}: {escape(fmt(v))}</title></path>')
        parts.append(f'<text x="{cx:.1f}" y="{h - 10}" text-anchor="middle">{escape(lab)}</text>')
    parts.append("</svg>")
    return (f'<div class="chart"><h3>{escape(title)}</h3><div class="note">{escape(y_label)}</div>'
            + "".join(parts) + "</div>")


def _flag_table(res: pd.DataFrame, tidy: pd.DataFrame, labels: dict, subgroup_col: bool) -> str:
    if res.empty:
        return '<p class="note">No counties flagged.</p>'
    hist = tidy.copy()
    hist["rate"] = hist["numerator"] / hist["denominator"]
    rows = []
    for r in res.itertuples():
        h = hist[(hist["geo_id"] == r.geo_id) & (hist["indicator"] == r.indicator) & (hist["subgroup"] == r.subgroup)]
        sub = f"<td>{escape(r.subgroup)}</td>" if subgroup_col else ""
        rows.append(
            f"<tr><td>{_pill(str(r.level))}</td>"
            f'<td class="place">{escape(r.geo_name)}<small>{escape(r.state)} · {escape(r.geo_id)}</small></td>'
            f"<td>{escape(labels.get(r.indicator, r.indicator))}</td>{sub}"
            f'<td class="num">{_pct(r.rate)}</td><td class="num">{_pct(r.expected_rate)}</td>'
            f'<td class="num">{_num(r.relative_risk, "{:.2f}")}</td>'
            f'<td class="num">{_num(r.excess_cases, "{:+,.0f}")}</td>'
            f'<td class="num">{_num(r.births)}</td>'
            f'<td>{"Yes" if r.sustained else "No"}</td>'
            f"<td>{_sparkline(h, r.expected_rate)}</td></tr>")
    sub_h = "<th>Subgroup</th>" if subgroup_col else ""
    return ('<div class="table-wrap"><table><thead><tr><th>Level</th><th>County</th><th>Indicator</th>'
            f'{sub_h}<th class="num">Rate</th><th class="num">Expected</th><th class="num">Ratio</th>'
            '<th class="num">Excess cases</th><th class="num">Births</th><th>2nd year</th><th>Trend</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def build_report(tidy: pd.DataFrame, config: dict, truth: pd.DataFrame | None = None,
                 target_year: int | None = None, title: str = "Perinatal Early Warning") -> str:
    year = int(target_year or tidy["year"].max())
    labels = {k: v["label"] for k, v in config["indicators"].items()}
    subgroups = sorted(s for s in tidy["subgroup"].unique() if s != TOTAL_SUBGROUP)

    res_all = detect(tidy, config, target_year=year)
    flagged = res_all[res_all["level"].isin(["alert", "watch"])]
    res_sub = detect(tidy, config, target_year=year, subgroups=subgroups) if subgroups else pd.DataFrame()
    sub_flagged = res_sub[res_sub["level"] == "alert"] if len(res_sub) else res_sub
    gaps = subgroup_gaps(tidy, config, year) if subgroups else pd.DataFrame()
    dq = data_quality(tidy, year)
    drift = distribution_drift(tidy, config, year)
    bt = backtest(tidy, config)

    scored = res_all[res_all["level"] != "insufficient data"]
    n_alert = int((scored["level"] == "alert").sum())
    n_watch = int((scored["level"] == "watch").sum())
    excess = flagged.loc[flagged["level"] == "alert", "excess_cases"].sum()

    synthetic_note = ""
    if truth is not None:
        synthetic_note = ('<div class="synthetic"><b>Demonstration data.</b> Every county and number on this page is '
                          'synthetic, generated with known changes injected so the system can be tested. '
                          'No real places or people are shown.</div>')

    out = [f'<title>{escape(title)}</title>',
           '<meta name="claude:viewport-fit-sides" content="cover">',
           '<link rel="preconnect" href="https://fonts.googleapis.com">',
           '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Public+Sans:wght@400;600;650;700&display=swap">',
           f"<style>{CSS}</style>", '<div class="page">']

    out.append(f'''<header><div class="eyebrow">County bulletin · birth year {year}</div>
<h1>{escape(title)}</h1>
<p>Counties where maternal and newborn indicators in {year} are worse than their own recent history predicts,
after allowing for the change seen across all counties.</p>{synthetic_note}</header>''')

    out.append(f'''<section><div class="kpis">
<div class="kpi"><b>{n_alert}</b><span>Alerts</span></div>
<div class="kpi"><b>{n_watch}</b><span>Watch list</span></div>
<div class="kpi"><b>{_num(excess, "{:+,.0f}")}</b><span>Excess cases in alerted series</span></div>
<div class="kpi"><b>{scored["geo_id"].nunique()}</b><span>Counties scored</span></div>
<div class="kpi"><b>{len(labels)}</b><span>Indicators</span></div>
</div></section>''')

    out.append(f'''<section><h2>Flagged counties</h2>
<p>An <b>alert</b> means the rise is statistically clear after correcting for testing every county at once,
and at least 10% above expected. <b>Watch</b> means a likely rise that needs another year of data to confirm.
"2nd year" shows whether the county was also elevated the year before.</p>
<div class="legend"><span><i></i>Observed rate by year</span><span><i class="ring"></i>Expected rate, {year}</span></div>
{_flag_table(flagged, tidy, labels, subgroup_col=False)}</section>''')

    if len(res_sub):
        out.append(f'''<section><h2>Subgroup alerts</h2>
<p>The same test run separately within each subgroup ({escape(", ".join(subgroups))}). A change confined to one group
can be too diluted to show in the county total.</p>
{_flag_table(sub_flagged, tidy, labels, subgroup_col=True)}</section>''')

    if len(gaps):
        top = gaps.sort_values("rate_ratio", ascending=False).groupby("indicator").head(3)
        rows = "".join(
            f'<tr><td class="place">{escape(r.geo_name)}<small>{escape(r.state)}</small></td>'
            f"<td>{escape(labels.get(r.indicator, r.indicator))}</td>"
            f"<td>{escape(r.highest_subgroup)}</td><td class=\"num\">{_pct(r.highest_rate)}</td>"
            f"<td>{escape(r.lowest_subgroup)}</td><td class=\"num\">{_pct(r.lowest_rate)}</td>"
            f'<td class="num">{r.rate_ratio:.2f}×</td><td class="num">{r.peer_rate_ratio:.2f}×</td></tr>'
            for r in top.itertuples())
        out.append(f'''<section><h2>Largest gaps between subgroups</h2>
<p>Within-county ratio of the highest to the lowest subgroup rate, for the three widest gaps per indicator.
The last column is the same gap across all counties combined, for context.</p>
<div class="table-wrap"><table><thead><tr><th>County</th><th>Indicator</th><th>Highest</th><th class="num">Rate</th>
<th>Lowest</th><th class="num">Rate</th><th class="num">Gap</th><th class="num">All counties</th></tr></thead>
<tbody>{rows}</tbody></table></div></section>''')

    # System health
    health = [f'<section><h2>System health</h2><p>Checks on the input data and on the detector itself, run every time.</p>']
    dq_text = ("No data issues found: every county reported, no suppressed counts, no implausible jumps in births."
               if dq.empty else f"{len(dq)} data issues found. Review before acting on alerts in affected counties.")
    health.append(f"<p>{escape(dq_text)}</p>")
    if not dq.empty:
        rows = "".join(f"<tr><td>{escape(labels.get(r.indicator, r.indicator))}</td><td>{escape(r.geo_name)}</td>"
                       f"<td>{escape(r.issue)}</td><td>{escape(r.detail)}</td></tr>" for r in dq.head(25).itertuples())
        health.append('<div class="table-wrap"><table><thead><tr><th>Indicator</th><th>County</th><th>Issue</th>'
                      f"<th>Detail</th></tr></thead><tbody>{rows}</tbody></table></div>")

    rows = "".join(
        f"<tr><td>{escape(labels.get(r.indicator, r.indicator))}</td><td class=\"num\">{_pct(r.median_rate_baseline)}</td>"
        f'<td class="num">{_pct(r.median_rate_current)}</td><td class="num">{r.psi:.3f}</td><td>{escape(r.status)}</td></tr>'
        for r in drift.itertuples())
    health.append('<div class="table-wrap"><table><thead><tr><th>Indicator</th><th class="num">Median county rate, baseline</th>'
                  f'<th class="num">Median, {year}</th><th class="num">Stability index</th><th>Distribution</th></tr></thead>'
                  f"<tbody>{rows}</tbody></table></div>"
                  '<p class="note">The stability index compares this year\'s spread of county rates with the baseline years. '
                  "A shift can be a real national trend (which the detector already adjusts for) or a change in how data were coded.</p>")

    charts = [_bar_chart([str(y) for y in bt["year"]], list(bt["alert_rate_pct"]),
                         lambda v: f"{v:.1f}%", "Alert rate by year (backtest)",
                         "Share of county-indicator pairs alerted when each past year is scored as if it were current")]
    if truth is not None:
        ev = evaluate_against_truth(tidy, config, truth, year)
        bs = ev["by_size"].set_index("size_class").reindex(
            ["small (<1k births)", "medium (1k-5k)", "large (5k+)"]).dropna(how="all")
        charts.append(_bar_chart(["Small", "Medium", "Large"][:len(bs)], list(bs["found_as_alert_or_watch_pct"]),
                                 lambda v: f"{v:.0f}%", "Injected changes found, by county size",
                                 "Share flagged as alert or watch (synthetic test only)", y_max=100))
        s = ev["summary"].iloc[0]
        health.append(f'<div class="two">{"".join(charts)}</div>')
        health.append(f'<p>On this synthetic test, {s["found_as_alert_or_watch_pct"]:.0f}% of {int(s["injected_changes"])} injected '
                      f'changes were flagged ({s["found_as_alert_pct"]:.0f}% as alerts), with a false-alert rate of '
                      f'{s["false_alert_rate_pct"]:.2f}% across {int(s["clean_county_indicators"])} unchanged county-indicator pairs. '
                      "Small counties are harder: one year of a few hundred births rarely carries enough signal, "
                      "so their flags should be read alongside multi-year trends.</p>")
    else:
        health.append(f'<div class="two">{"".join(charts)}</div>')
    health.append("</section>")
    out.extend(health)

    out.append(f'''<section><h2>How this works</h2><ul class="methods">
<li>Each county's expected {year} rate comes from its own births in the {config["detection"]["baseline_years"]} baseline years,
skipping the year just before {year} so a change that started then is not counted as normal.</li>
<li>Baselines for small counties are pulled toward the all-county rate (empirical Bayes), so a single noisy year does not set the bar.</li>
<li>Expected rates are scaled by the change seen across all counties, so a nationwide rise does not flag everyone at once.</li>
<li>Uncertainty includes ordinary binomial noise, uncertainty in the baseline, and the extra year-to-year variation measured in the data.</li>
<li>Alerts require a Benjamini–Hochberg q-value of {config["detection"]["alert_q"]} or less and a ratio of at least
{config["detection"]["min_relative_risk_alert"]:.2f}, and at least {config["detection"]["min_numerator_reliable"]} events, the NCHS reliability threshold.</li>
<li>This is population surveillance to prompt a closer look by local teams. It is not a clinical tool and says nothing about individual patients.</li>
</ul></section>''')

    out.append(f'<footer>Generated by perinatal-ews {escape(__version__)} · open source, MIT licence · '
               f'{len(tidy):,} input rows, {tidy["year"].min()}–{tidy["year"].max()}</footer></div>')
    return "\n".join(out)
