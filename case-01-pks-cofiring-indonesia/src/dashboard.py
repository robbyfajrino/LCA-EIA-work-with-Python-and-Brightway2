"""Interactive dashboard: compare scenarios, Monte Carlo and Sobol results.

Two artefacts from one run of the model:

    python src/dashboard.py

  * `output/dashboard.html`       - a single self-contained Plotly page. No server,
                                   no assets: open it offline, e-mail it, or show
                                   it inline in Colab.
  * `output/dashboard_data.json`  - the same numbers in a compact schema, also
                                   copied to `../src/data/lca-results.json` so the
                                   portfolio website can render them with Recharts.

Filters in the HTML: electricity background mode (all four), impact category,
scenario subset (legend toggles) and a parameter selector driven by the
one-at-a-time sensitivity results.
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from analysis import GWP, run_electricity_modes
from config import (
    DEFAULT_ELECTRICITY_MODE,
    ELECTRICITY_MODES,
    FUNCTIONAL_UNIT,
    OUTPUT_DIR,
    REPO_DIR,
)
from scenarios import load_scenarios

GREEN = "#2f6b3f"
SAGE = "#7d9b76"
CLAY = "#b5793f"
INK = "#22301f"
MODE_COLORS = {
    "average_time_of_use": GREEN,
    "marginal_time_of_use": CLAY,
    "marginal_time_of_construction": "#4f7f8b",
    "marginal_decarbonising_2040": SAGE,
}

WEBSITE_JSON = REPO_DIR.parent / "src" / "data" / "lca-results.json"


# --------------------------------------------------------------------------- #
# Data extraction
# --------------------------------------------------------------------------- #
def _histogram(samples: np.ndarray, bins: int = 24) -> dict:
    counts, edges = np.histogram(samples, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    return {"centers": [round(float(c), 3) for c in centers], "counts": [int(c) for c in counts]}


def collect(iterations: int = 300, sobol_n: int = 32) -> dict:
    """Run every electricity mode and pack the results into one JSON-ready dict."""
    comparison = run_electricity_modes(iterations=iterations, sobol_n=sobol_n)
    runs = comparison["runs"]
    scenarios = load_scenarios()
    categories = list(runs[DEFAULT_ELECTRICITY_MODE]["scores"].columns)

    payload: dict = {
        "generated_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "functional_unit": FUNCTIONAL_UNIT,
        "categories": categories,
        "default_mode": DEFAULT_ELECTRICITY_MODE,
        "scenario_meta": [
            {
                "name": s.name,
                "cofiring_pct_energy": s.cofiring_pct_energy,
                "truck_km": s.truck_km,
                "barge_km": s.barge_km,
                "net_efficiency_pct": s.net_efficiency_pct,
            }
            for s in scenarios
        ],
        "modes": {},
    }

    for mode, res in runs.items():
        spec = ELECTRICITY_MODES[mode]
        samples = res["_meta"]["samples"]
        mc = res["monte_carlo"]
        payload["modes"][mode] = {
            "label": spec["label"],
            "gwp_kg_per_kWh": spec["gwp_kg_per_kWh"],
            "co_scale": spec["co_scale"],
            "source": spec["source"],
            "scores": {
                cat: {sc: float(res["scores"].loc[sc, cat]) for sc in res["scores"].index}
                for cat in categories
            },
            "monte_carlo": {
                sc: {
                    "mean": float(mc.loc[sc, "mean"]),
                    "median": float(mc.loc[sc, "median"]),
                    "p5": float(mc.loc[sc, "p5"]),
                    "p95": float(mc.loc[sc, "p95"]),
                    "cv_pct": float(mc.loc[sc, "cv_pct"]),
                    "p_better_than_baseline": float(mc.loc[sc, "p_better_than_baseline"]),
                    "histogram": _histogram(samples[sc]),
                }
                for sc in mc.index
            },
            "sobol": res["sobol_indices"].to_dict("records"),
            "oat": res["oat_sensitivity"].to_dict("records"),
            "contribution_30pct": res["contribution_30pct"].to_dict("records"),
            "contribution_baseline": res["contribution_baseline"].to_dict("records"),
            "validation_max_rel_diff": float(res["validation"]["rel_diff"].max()),
            "provenance": {
                "timestamp_utc": res["_meta"]["provenance"]["run"]["timestamp_utc"],
                "dataset_source": res["_meta"]["provenance"]["data"]["source"],
                "dataset_digest": res["_meta"]["provenance"]["data"]["digest"],
                "git_commit": res["_meta"]["provenance"]["code"]["git"].get("short_commit"),
                "git_dirty": res["_meta"]["provenance"]["code"]["git"].get("dirty"),
                "iterations": res["_meta"]["provenance"]["run"]["monte_carlo_iterations"],
                "seed": res["_meta"]["provenance"]["run"]["monte_carlo_seed"],
            },
        }
        # keep raw samples out of the JSON but available to the Plotly build
        payload["modes"][mode]["_samples"] = {k: v for k, v in samples.items()}

    return payload


def _strip_samples(payload: dict) -> dict:
    clean = json.loads(json.dumps({k: v for k, v in payload.items() if k != "modes"}, default=str))
    clean["modes"] = {}
    for mode, block in payload["modes"].items():
        clean["modes"][mode] = json.loads(
            json.dumps({k: v for k, v in block.items() if k != "_samples"}, default=str)
        )
    return clean


# --------------------------------------------------------------------------- #
# Plotly figure with mode / category / parameter filters
# --------------------------------------------------------------------------- #
def build_plotly(payload: dict) -> str:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from plotly.io import to_html

    modes = list(payload["modes"])
    categories = payload["categories"]
    scenario_names = [s["name"] for s in payload["scenario_meta"]]
    shares = [s["cofiring_pct_energy"] for s in payload["scenario_meta"]]

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Impact per functional unit vs co-firing share",
            "Monte Carlo distribution (pedigree uncertainty)",
            "Global sensitivity — total-order Sobol index",
            "Local sensitivity — elasticity (±10 %)",
        ),
        vertical_spacing=0.16,
        horizontal_spacing=0.1,
    )

    # trace bookkeeping: (mode, category) -> indices of traces to show
    visibility: list[tuple[str, str | None]] = []

    for mode in modes:
        block = payload["modes"][mode]
        color = MODE_COLORS.get(mode, GREEN)
        for cat in categories:
            values = [block["scores"][cat][sc] for sc in scenario_names]
            fig.add_trace(
                go.Scatter(
                    x=shares,
                    y=values,
                    mode="lines+markers",
                    name=block["label"],
                    line=dict(color=color, width=2.4),
                    marker=dict(size=8),
                    hovertemplate="%{x:.0f} % co-firing<br>%{y:.4g}<extra></extra>",
                    showlegend=False,
                ),
                row=1,
                col=1,
            )
            visibility.append((mode, cat))

    # Monte Carlo violins (GWP only — the uncertainty model is climate-focused)
    mc_traces: list[tuple[str, str]] = []
    for mode in modes:
        block = payload["modes"][mode]
        for sc in scenario_names:
            fig.add_trace(
                go.Violin(
                    y=np.asarray(block["_samples"][sc]),
                    name=sc.replace("_", " "),
                    box_visible=True,
                    meanline_visible=True,
                    line_color=INK,
                    fillcolor=MODE_COLORS.get(mode, GREEN),
                    opacity=0.65,
                    points=False,
                    showlegend=False,
                    hovertemplate=(
                        f"{sc}<br>P(better than baseline) = "
                        f"{block['monte_carlo'][sc]['p_better_than_baseline']:.2f}<extra></extra>"
                    ),
                ),
                row=1,
                col=2,
            )
            mc_traces.append((mode, sc))

    # Trace order matters: the visibility masks below assume all Sobol traces come
    # as one contiguous block, then all one-at-a-time traces.
    sobol_traces: list[str] = []
    for mode in modes:
        sob = pd.DataFrame(payload["modes"][mode]["sobol"]).sort_values("ST")
        fig.add_trace(
            go.Bar(
                x=sob["ST"],
                y=sob["parameter"],
                orientation="h",
                marker_color=MODE_COLORS.get(mode, GREEN),
                showlegend=False,
                hovertemplate="%{y}<br>S_T = %{x:.3f}<extra></extra>",
            ),
            row=2,
            col=1,
        )
        sobol_traces.append(mode)

    oat_traces: list[str] = []
    for mode in modes:
        oat = pd.DataFrame(payload["modes"][mode]["oat"]).sort_values("abs_elasticity")
        fig.add_trace(
            go.Bar(
                x=oat["elasticity"],
                y=oat["parameter"],
                orientation="h",
                marker_color=SAGE,
                showlegend=False,
                hovertemplate="%{y}<br>elasticity = %{x:.3f}<extra></extra>",
            ),
            row=2,
            col=2,
        )
        oat_traces.append(mode)

    def mask(active_mode: str, active_cat: str) -> list[bool]:
        vis: list[bool] = []
        for mode, cat in visibility:
            vis.append(mode == active_mode and cat == active_cat)
        for mode, _sc in mc_traces:
            vis.append(mode == active_mode)
        for mode in sobol_traces:
            vis.append(mode == active_mode)
        for mode in oat_traces:
            vis.append(mode == active_mode)
        return vis

    def all_modes_mask(active_cat: str) -> list[bool]:
        vis = [cat == active_cat for _m, cat in visibility]
        vis += [mode == DEFAULT_ELECTRICITY_MODE for mode, _sc in mc_traces]
        vis += [mode == DEFAULT_ELECTRICITY_MODE for mode in sobol_traces]
        vis += [mode == DEFAULT_ELECTRICITY_MODE for mode in oat_traces]
        return vis

    default_cat = GWP if GWP in categories else categories[0]
    for i, v in enumerate(mask(DEFAULT_ELECTRICITY_MODE, default_cat)):
        fig.data[i].visible = v
    # show the line legend for the compare-all view
    for i, (mode, cat) in enumerate(visibility):
        fig.data[i].showlegend = cat == default_cat

    mode_buttons = [
        dict(
            label=payload["modes"][m]["label"],
            method="update",
            args=[{"visible": mask(m, default_cat)}],
        )
        for m in modes
    ] + [
        dict(
            label="Compare all modes",
            method="update",
            args=[{"visible": all_modes_mask(default_cat)}],
        )
    ]

    cat_buttons = [
        dict(
            label=cat,
            method="update",
            args=[{"visible": mask(DEFAULT_ELECTRICITY_MODE, cat)}],
        )
        for cat in categories
    ]

    fig.update_layout(
        template="simple_white",
        height=880,
        font=dict(family="Fira Sans, Helvetica Neue, Arial", size=12, color=INK),
        legend=dict(orientation="h", y=-0.08, x=0),
        margin=dict(t=160, l=70, r=40, b=90),
        updatemenus=[
            dict(
                buttons=mode_buttons,
                direction="down",
                x=0.0,
                y=1.16,
                xanchor="left",
                showactive=True,
                bgcolor="#eef1ea",
            ),
            dict(
                buttons=cat_buttons,
                direction="down",
                x=0.45,
                y=1.16,
                xanchor="left",
                showactive=True,
                bgcolor="#eef1ea",
            ),
        ],
        annotations=list(fig.layout.annotations)
        + [
            dict(text="Electricity background", x=0.0, y=1.21, xref="paper", yref="paper",
                 showarrow=False, font=dict(size=11, color="#5d6b58"), xanchor="left"),
            dict(text="Impact category", x=0.45, y=1.21, xref="paper", yref="paper",
                 showarrow=False, font=dict(size=11, color="#5d6b58"), xanchor="left"),
        ],
    )
    fig.update_xaxes(title_text="co-firing share (% of fuel energy)", row=1, col=1)
    fig.update_yaxes(title_text="impact per MWh", row=1, col=1)
    fig.update_yaxes(title_text="kg CO₂-eq / MWh", row=1, col=2)
    fig.update_xaxes(title_text="S_T", row=2, col=1)
    fig.update_xaxes(title_text="elasticity", row=2, col=2)

    return to_html(fig, include_plotlyjs="inline", full_html=False, div_id="pks-dashboard")


# --------------------------------------------------------------------------- #
# HTML page
# --------------------------------------------------------------------------- #
PAGE_CSS = """
:root { --ink:#22301f; --green:#2f6b3f; --sage:#7d9b76; --paper:#fbfaf6; --line:#dfe4da; }
body { margin:0; background:var(--paper); color:var(--ink);
  font-family:"Fira Sans","Helvetica Neue",Arial,sans-serif; font-size:14px; }
main { max-width:1180px; margin:0 auto; padding:36px 26px 64px; }
h1 { font-family:"DM Serif Display",Georgia,serif; font-weight:400; color:var(--green);
  font-size:2.1rem; margin:0 0 4px; }
.sub { color:#5d6b58; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; margin:20px 0; }
.card { background:#fff; border:1px solid var(--line); border-radius:6px; padding:12px 14px; }
.card b { display:block; font-size:1.5rem; color:var(--green); font-weight:500; }
.card span { color:#5d6b58; font-size:12px; }
table { border-collapse:collapse; width:100%; font-size:12px; margin:10px 0 24px; }
th,td { border:1px solid var(--line); padding:5px 8px; text-align:right; }
th { background:#eef1ea; text-align:left; } td:first-child,th:first-child { text-align:left; }
.callout { background:#eef1ea; border-left:4px solid var(--green); padding:12px 16px; margin:18px 0; }
footer { margin-top:40px; border-top:1px solid var(--line); padding-top:10px;
  color:#5d6b58; font-size:11.5px; }
"""


def build_html(payload: dict) -> str:
    plot = build_plotly(payload)
    prov = payload["modes"][payload["default_mode"]]["provenance"]
    gwp = pd.DataFrame(
        {m: payload["modes"][m]["scores"][GWP] for m in payload["modes"]}
    )
    gwp.index.name = "scenario"
    prob = pd.DataFrame(
        {
            m: {sc: payload["modes"][m]["monte_carlo"][sc]["p_better_than_baseline"]
                for sc in payload["modes"][m]["monte_carlo"]}
            for m in payload["modes"]
        }
    )
    prob.index.name = "scenario"

    best = gwp[payload["default_mode"]]
    baseline = best.get("baseline_0pct", best.iloc[0])
    deepest = best.index[-1]

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PKS co-firing — interactive LCA dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Fira+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>{PAGE_CSS}</style></head><body><main>
<h1>PKS co-firing — interactive LCA dashboard</h1>
<p class="sub">{payload['functional_unit']} · generated {payload['generated_utc']}</p>
<div class="grid">
  <div class="card"><b>{baseline:.0f}</b><span>kg CO₂-eq / MWh, baseline (0 % co-firing)</span></div>
  <div class="card"><b>{best[deepest]:.0f}</b><span>kg CO₂-eq / MWh, {deepest.replace('_',' ')}</span></div>
  <div class="card"><b>{prob[payload['default_mode']][deepest]:.2f}</b><span>P(better than baseline), deepest scenario</span></div>
  <div class="card"><b>{len(payload['modes'])}</b><span>electricity background models compared</span></div>
</div>
<div class="callout">Use the two dropdowns above the charts to switch the
<strong>electricity background model</strong> and the <strong>impact category</strong>;
click legend entries to filter scenarios. "Compare all modes" overlays every
background assumption on the impact curve — the spread is the cost of a modelling
choice, not measurement error.</div>
{plot}
<h3>GWP100 by electricity background model (kg CO₂-eq / MWh)</h3>
{gwp.to_html(float_format=lambda v: '%.1f' % v, border=0)}
<h3>P(better than baseline) by electricity background model</h3>
{prob.to_html(float_format=lambda v: '%.3f' % v, border=0)}
<footer>Provenance — dataset: {prov['dataset_source']} · digest
<code>{prov['dataset_digest']}</code> · commit <code>{prov['git_commit']}</code>
{'(dirty working tree)' if prov['git_dirty'] else ''} · Monte Carlo
{prov['iterations']} iterations, seed {prov['seed']} · cross-validation max
relative difference {payload['modes'][payload['default_mode']]['validation_max_rel_diff']:.1e}.
Proxy background factors stand in for licensed ecoinvent datasets.</footer>
</main></body></html>"""


# --------------------------------------------------------------------------- #
def build_dashboard(iterations: int = 300, sobol_n: int = 32, copy_to_website: bool = True) -> Path:
    payload = collect(iterations=iterations, sobol_n=sobol_n)
    html_path = OUTPUT_DIR / "dashboard.html"
    html_path.write_text(build_html(payload), encoding="utf-8")

    clean = _strip_samples(payload)
    json_path = OUTPUT_DIR / "dashboard_data.json"
    json_path.write_text(json.dumps(clean, indent=1), encoding="utf-8")
    print(f"dashboard: {html_path}")
    print(f"data:      {json_path}")

    if copy_to_website and WEBSITE_JSON.parent.exists():
        shutil.copyfile(json_path, WEBSITE_JSON)
        print(f"website:   {WEBSITE_JSON}")
    return html_path


if __name__ == "__main__":
    args = sys.argv[1:]
    iters = int(args[0]) if args else 300
    build_dashboard(iterations=iters)
