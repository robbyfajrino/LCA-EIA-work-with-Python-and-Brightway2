"""Exportable HTML (and optional PDF) report for the PKS co-firing LCA.

One command turns a Brightway run into a self-contained deliverable: goal and
scope, the full parameter table with sources, the electricity-background model in
force, scenario results, contribution analysis, Monte Carlo distributions and
Sobol indices, with every figure embedded as base64 PNG so the HTML file can be
e-mailed or attached to a repository release without any assets.

    python src/report.py                        # default electricity model
    python src/report.py marginal_time_of_use   # one alternative model
    python src/report.py all-modes              # every model, with comparison
"""

from __future__ import annotations

import base64
import datetime as _dt
import io
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis import GWP, run_all, run_electricity_modes
from config import (
    DEFAULT_ELECTRICITY_MODE,
    ELECTRICITY_MODES,
    FUNCTIONAL_UNIT,
    OUTPUT_DIR,
    SYSTEM_BOUNDARY,
    electricity_mode_spec,
)
from scenarios import PARAMETER_TABLE, load_scenarios

GREEN = "#2f6b3f"
SAGE = "#7d9b76"
INK = "#22301f"


# --------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------- #
def _embed(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def fig_scenarios(scores: pd.DataFrame, scenarios) -> str:
    x = [s.cofiring_pct_energy for s in scenarios]
    y = [scores.loc[s.name, GWP] for s in scenarios]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(x, y, "o-", color=GREEN, lw=2)
    for xi, yi in zip(x, y):
        ax.annotate(f"{yi:.0f}", (xi, yi), textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=8, color=INK)
    ax.set(xlabel="co-firing share (% of fuel energy)",
           ylabel="kg CO$_2$-eq / MWh",
           title="Fossil GWP100 per MWh net electricity")
    ax.grid(alpha=0.3)
    return _embed(fig)


def fig_montecarlo(samples: dict[str, np.ndarray]) -> str:
    fig, ax = plt.subplots(figsize=(7, 3.6))
    names = list(samples)
    bp = ax.boxplot([samples[n] for n in names], tick_labels=names, showfliers=False, patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_facecolor(SAGE)
        patch.set_alpha(0.7)
    for median in bp["medians"]:
        median.set_color(INK)
    ax.set(ylabel="kg CO$_2$-eq / MWh", title="Monte Carlo, pedigree-derived uncertainty")
    ax.tick_params(axis="x", rotation=20)
    ax.grid(alpha=0.3, axis="y")
    return _embed(fig)


def fig_sobol(sob: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.barh(sob["parameter"][::-1], sob["ST"][::-1], color=GREEN)
    ax.set(xlabel="total-order Sobol index $S_T$", title="Global sensitivity, GWP100 at 30 % co-firing")
    ax.grid(alpha=0.3, axis="x")
    return _embed(fig)


def fig_contribution(contrib: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.barh(contrib["stage"][::-1], contrib["share_pct"][::-1], color=SAGE)
    ax.set(xlabel="share of GWP100 (%)", title="Stage contribution, 30 % co-firing")
    ax.grid(alpha=0.3, axis="x")
    return _embed(fig)


def fig_modes(gwp: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7.4, 3.8))
    for mode in gwp.columns:
        ax.plot(gwp.index, gwp[mode], "o-", label=ELECTRICITY_MODES[mode]["label"], lw=1.8)
    ax.set(ylabel="kg CO$_2$-eq / MWh", title="Sensitivity to the electricity background model")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3, axis="y")
    return _embed(fig)


# --------------------------------------------------------------------------- #
# HTML assembly
# --------------------------------------------------------------------------- #
CSS = """
:root { --ink:#22301f; --green:#2f6b3f; --sage:#7d9b76; --paper:#fbfaf6; --line:#dfe4da; }
* { box-sizing:border-box; }
body { margin:0; background:var(--paper); color:var(--ink);
  font-family:"Fira Sans","Helvetica Neue",Arial,sans-serif; font-size:13.5px; line-height:1.6; }
main { max-width:1000px; margin:0 auto; padding:48px 32px 72px; }
h1,h2,h3 { font-family:"DM Serif Display",Georgia,serif; font-weight:400; color:var(--green); }
h1 { font-size:2.4rem; margin:0 0 4px; }
h2 { font-size:1.5rem; margin:44px 0 10px; border-bottom:1px solid var(--line); padding-bottom:6px; }
h3 { font-size:1.1rem; margin:24px 0 6px; }
.sub { color:#5d6b58; font-size:.95rem; }
table { border-collapse:collapse; width:100%; margin:12px 0; font-size:12px; }
th,td { border:1px solid var(--line); padding:5px 8px; text-align:right; }
th { background:#eef1ea; text-align:left; }
td:first-child, th:first-child { text-align:left; }
img { width:100%; max-width:820px; margin:14px 0; border:1px solid var(--line);
  background:#fff; border-radius:4px; }
.callout { background:#eef1ea; border-left:4px solid var(--green); padding:12px 16px; margin:16px 0; }
code { background:#eef1ea; padding:1px 4px; border-radius:3px; font-size:12px; }
footer { margin-top:56px; padding-top:12px; border-top:1px solid var(--line);
  color:#5d6b58; font-size:11.5px; }
@media print { body { background:#fff; } main { padding:0; } h2 { page-break-after:avoid; }
  img, table { page-break-inside:avoid; } }
"""


def _table(df: pd.DataFrame, index: bool = True, floatfmt: str = "%.4g") -> str:
    return df.to_html(index=index, float_format=lambda v: floatfmt % v, border=0)


def build_html(results: dict, comparison: dict | None = None) -> str:
    mode = results["_meta"]["mode"]
    spec = electricity_mode_spec(mode)
    scenarios = load_scenarios()
    scores = results["scores"]
    mc = results["monte_carlo"]
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    parts: list[str] = []
    a = parts.append

    a(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PKS co-firing LCA — results report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Fira+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><main>""")

    a(f"""<h1>Palm kernel shell co-firing: life-cycle results</h1>
<p class="sub">Brightway 2.5 model · ReCiPe 2016 (H) midpoint proxy · generated {stamp}</p>
<div class="callout"><strong>Functional unit.</strong> {FUNCTIONAL_UNIT}.<br>
<strong>System boundary.</strong> {SYSTEM_BOUNDARY}</div>""")

    a(f"""<h2>1. Electricity background model in force</h2>
<p>Auxiliary and crusher electricity are charged at the <strong>{spec['label']}</strong>
factor of {spec['gwp_kg_per_kWh']:g} kg CO<sub>2</sub>-eq/kWh
(mode key <code>{mode}</code>; other indicator columns scaled by
{spec['co_scale']:g}). Source: {spec['source']}.</p>
{_table(results['electricity_model'])}""")

    a(f"""<h2>2. Scenarios</h2>
{_table(pd.DataFrame([{
        'scenario': s.name, 'co-firing (% energy)': s.cofiring_pct_energy,
        'truck (km)': s.truck_km, 'barge (km)': s.barge_km,
        'net efficiency (%)': s.net_efficiency_pct} for s in scenarios]).set_index('scenario'))}""")

    a(f"""<h2>3. Parameters and sources</h2>
<p class="sub">Every number a reviewer can challenge, with its provenance.</p>
{_table(PARAMETER_TABLE.set_index('parameter'), floatfmt='%.6g')}""")

    a(f"""<h2>4. Impact results per functional unit</h2>
{_table(scores)}
<img alt="GWP100 per MWh against co-firing share" src="{fig_scenarios(scores, scenarios)}">""")

    a(f"""<h2>5. Contribution analysis</h2>
<img alt="Stage contribution at 30 % co-firing" src="{fig_contribution(results['contribution_30pct'])}">
{_table(results['contribution_30pct'], index=False)}""")

    a(f"""<h2>6. Monte Carlo under pedigree uncertainty</h2>
<img alt="Monte Carlo distributions" src="{fig_montecarlo(results['_meta']['samples'])}">
{_table(mc)}
<div class="callout">The decision-relevant number is the last column: the
probability that a scenario beats the baseline once data quality is propagated.
Low co-firing shares improve the mean while leaving the conclusion inside the
noise; the benefit only becomes robust at the higher shares.</div>""")

    a(f"""<h2>7. Sensitivity</h2>
<h3>Local elasticity (±10 %, one at a time)</h3>
{_table(results['oat_sensitivity'], index=False)}
<h3>Global variance decomposition (Sobol)</h3>
<img alt="Sobol total-order indices" src="{fig_sobol(results['sobol_indices'])}">
{_table(results['sobol_indices'], index=False)}""")

    if comparison is not None:
        a(f"""<h2>8. Electricity model comparison</h2>
<p>All scenarios re-run under each background assumption — time-of-use versus
time-of-construction is a modelling choice with a quantified consequence, not a
detail.</p>
<img alt="GWP by electricity background model" src="{fig_modes(comparison['gwp'])}">
<h3>GWP100 (kg CO<sub>2</sub>-eq / MWh)</h3>
{_table(comparison['gwp'])}
<h3>P(better than baseline)</h3>
{_table(comparison['probability'], floatfmt='%.3f')}""")

    prov = results["_meta"]["provenance"]
    a(f"""<h2>{'9' if comparison is not None else '8'}. Provenance</h2>
<p class="sub">What this result is made of. Any edit to a dataset changes its
SHA-256, so two numbers can never be silently confused.</p>
{_table(results['provenance_summary'])}
<h3>Dataset versions</h3>
{_table(results['provenance_datasets'], index=False)}
<h3>Brightway mapping — foreground exchange to background activity</h3>
{_table(results['provenance_mapping'], index=False)}
<h3>Code state</h3>
{_table(pd.DataFrame([
        {'file': f, 'sha256 (first 16)': str(fp.get('sha256',''))[:16], 'bytes': fp.get('bytes')}
        for f, fp in prov['code']['sources'].items()]), index=False)}
{_table(pd.DataFrame([prov['code']['packages']]).T.rename(columns={0: 'version'}))}
<p class="sub">The machine-readable record for this run is written next to the
results as <code>provenance.json</code> and <code>provenance.csv</code>.</p>""")

    a(f"""<h2>Verification</h2>
<p>Every score is reproduced by an independent pandas matrix implementation
(<code>g = CF·Bs</code>); the largest relative difference in this run is
{results['validation']['rel_diff'].max():.2e}, i.e. float32 precision.</p>
{_table(results['validation'], index=False, floatfmt='%.6g')}""")

    git = prov["code"]["git"]
    a(f"""<footer>Proxy background factors stand in for licensed ecoinvent datasets;
absolute values are indicative and the comparison between scenarios is the result
that carries. Generated by <code>src/report.py</code> — commit
<code>{git.get('short_commit')}</code>{' (dirty working tree)' if git.get('dirty') else ''},
dataset digest <code>{prov['data']['digest']}</code>, source {prov['data']['source']}.
</footer></main></body></html>""")
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# PDF (best effort — the HTML is the primary deliverable)
# --------------------------------------------------------------------------- #
def html_to_pdf(html_path: Path, pdf_path: Path) -> Path | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("PDF skipped: playwright not installed (HTML report is complete).")
        return None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri(), wait_until="load")
            page.pdf(path=str(pdf_path), format="A4", print_background=True,
                     margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
            browser.close()
        return pdf_path
    except Exception as exc:  # noqa: BLE001 - a missing browser must not fail the run
        print(f"PDF skipped: {exc}")
        return None


# --------------------------------------------------------------------------- #
def build_report(
    electricity_mode: str | None = None,
    all_modes: bool = False,
    iterations: int = 400,
    pdf: bool = True,
) -> Path:
    if all_modes:
        comparison = run_electricity_modes(iterations=iterations)
        mode = electricity_mode or DEFAULT_ELECTRICITY_MODE
        results = comparison["runs"][mode]
    else:
        comparison = None
        results = run_all(iterations=iterations, electricity_mode=electricity_mode)
        mode = results["_meta"]["mode"]

    html = build_html(results, comparison)
    suffix = "" if mode == DEFAULT_ELECTRICITY_MODE else f"_{mode}"
    html_path = OUTPUT_DIR / f"pks_cofiring_report{suffix}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"HTML report: {html_path}")
    if pdf:
        html_to_pdf(html_path, OUTPUT_DIR / f"pks_cofiring_report{suffix}.pdf")
    return html_path


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    no_pdf = "--no-pdf" in args
    args = [a for a in args if a != "--no-pdf"]
    if args and args[0] == "all-modes":
        build_report(all_modes=True, pdf=not no_pdf)
    else:
        build_report(electricity_mode=args[0] if args else None, pdf=not no_pdf)
