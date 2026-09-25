"""Generate notebooks/PKS_Cofiring_Brightway.ipynb from a single source of truth."""

import json
from pathlib import Path

CELLS: list[tuple[str, str]] = [
    ("md", """# PKS Co-firing LCA with Brightway

**Palm kernel shell (PKS) co-firing in a 300 MW sub-critical PLTU** — 1 MWh net
electricity to the Java-Bali grid, ReCiPe 2016 (H) midpoint, ISO 14040/14044 and
ISO 14067.

This notebook runs the whole study end to end: build the Brightway project,
register the LCIA methods, score five co-firing scenarios, run contribution
analysis, propagate pedigree-based uncertainty, rank parameters with OAT and
Sobol, and cross-validate against an independent pandas matrix implementation.

*Data are dummy values that mimic real plant records. Do not use for external
claims.*"""),

    ("md", "## 1. Environment\n\nOn Colab, clone the repository first, then install the pinned requirements."),
    ("code", """# Colab only — skip when running locally
# !git clone https://github.com/<username>/pks-cofiring-brightway.git
# %cd pks-cofiring-brightway
# !pip install -q -r requirements.txt"""),

    ("code", """import os, sys
from pathlib import Path

REPO = Path.cwd() if (Path.cwd() / "src").exists() else Path.cwd().parent
sys.path.insert(0, str(REPO / "src"))

# Brightway needs a writable directory; Colab's /content is fine.
os.environ.setdefault("BRIGHTWAY2_DIR", str(REPO / ".brightway"))
Path(os.environ["BRIGHTWAY2_DIR"]).mkdir(exist_ok=True)

import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, matplotlib.pyplot as plt
import bw2data as bd

print("bw2data", bd.__version__)"""),

    ("md", """## 2. Goal and scope (ISO 14040)

Everything a reviewer could challenge lives in `src/config.py`: functional unit,
system boundary, and every engineering parameter with its source."""),
    ("code", """import config
from scenarios import PARAMETER_TABLE, load_scenarios, fuel_summary

print("Functional unit:", config.FUNCTIONAL_UNIT)
print()
print(config.SYSTEM_BOUNDARY)
PARAMETER_TABLE"""),

    ("code", """scenarios = load_scenarios()
pd.DataFrame([
    dict(scenario=s.name, cofiring_pct=s.cofiring_pct_energy, net_eff_pct=s.net_efficiency_pct,
         truck_km=s.truck_km, barge_km=s.barge_km, **fuel_summary(s))
    for s in scenarios
]).set_index("scenario").round(2)"""),

    ("md", """## 3. Parametric inventory

The inventory is computed, not typed in. A scenario is a function argument, which
is exactly what a GUI tool cannot give you."""),
    ("code", """from scenarios import build_inventory

inv_base = build_inventory(scenarios[0])
inv_30 = build_inventory(scenarios[-1])
display(inv_base.round(4))
print("30 % co-firing, PKS chain:")
inv_30[inv_30["process"].isin(["P1_PKM", "P2_Drying", "P3_Transport"])].round(4)"""),

    ("md", """## 4. Build the Brightway project

Three databases are written: a project-local biosphere, a proxy background built
from aggregated ecoinvent-like factors, and the foreground (one set of activities
per scenario). The build is idempotent — safe to re-run."""),
    ("code", """from build_project import build_all
from methods import write_methods, impact_categories

inventories = build_all(scenarios)
method_keys = write_methods()

print({db: len(bd.Database(db)) for db in (config.BIOSPHERE_DB, config.BACKGROUND_DB, config.FOREGROUND_DB)})
for k in method_keys:
    print(k)"""),

    ("code", """act = bd.get_activity((config.FOREGROUND_DB, "cofire_30pct_barge::P5_Generation"))
print(act, "|", act["unit"], "|", act["comment"])
for exc in list(act.exchanges())[:8]:
    print(f"  {exc['type']:<13} {exc.get('name', exc.input['name'])[:45]:<47} {exc['amount']:>12.4f} {exc.get('unit','')}")"""),

    ("md", "## 5. LCIA: five scenarios, seven impact categories"),
    ("code", """from analysis import GWP, score_table

scores = score_table([s.name for s in scenarios])
display(scores.round(4))

fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
x = [s.cofiring_pct_energy for s in scenarios]
ax[0].plot(x, scores[GWP], "o-", color="#2f6b3f")
ax[0].set(xlabel="co-firing share (% of fuel energy)", ylabel="kg CO2-eq / MWh",
          title="Fossil GWP100 per MWh net")
ax[1].plot(x, scores["Land use"], "s-", color="#8a6d1f")
ax[1].set(xlabel="co-firing share (% of fuel energy)", ylabel="m2a crop-eq / MWh",
          title="Land use per MWh net")
for a in ax: a.grid(alpha=.3)
plt.tight_layout(); plt.show()"""),

    ("md", """Climate impact falls and land use rises: a burden shift that a single
weighted score would hide. This is the reason aggregation stays explicit."""),

    ("md", "## 6. Contribution analysis"),
    ("code", """from analysis import contribution_by_stage, biosphere_contributions

display(contribution_by_stage("baseline_0pct").round(3))
display(contribution_by_stage("cofire_30pct_barge").round(3))
biosphere_contributions("cofire_30pct_barge", top=8).round(4)"""),

    ("md", """## 7. Uncertainty from data quality (pedigree -> Monte Carlo)

Pedigree scores from the field inventory become lognormal distributions with the
standard Weidema factors, and Brightway propagates them. The decision-relevant
output is not the mean, it is **P(scenario beats baseline)**."""),
    ("code", """from analysis import monte_carlo, mc_summary, probability_of_improvement

ITER = 500
samples = {s.name: monte_carlo(s.name, ITER) for s in scenarios}
summary = mc_summary(samples)
summary["P_better_than_baseline"] = [
    probability_of_improvement(samples["baseline_0pct"], samples[s.name]) for s in scenarios
]
summary.round(3)"""),

    ("code", """fig, ax = plt.subplots(figsize=(9, 3.8))
ax.boxplot([samples[s.name] for s in scenarios], tick_labels=[s.name for s in scenarios], showfliers=False)
ax.set(ylabel="kg CO2-eq / MWh", title=f"GWP100 distribution, {ITER} Monte Carlo iterations")
ax.grid(alpha=.3); plt.xticks(rotation=20); plt.tight_layout(); plt.show()"""),

    ("md", """**Interpretation.** At 5–10 % co-firing the improvement is not robust
(P ~ 0.5-0.6): under the plant's own data quality the credible intervals overlap
almost completely. Only from roughly 20 % upward does the conclusion survive
uncertainty. Reporting a single mean would have implied a certainty the data do
not support."""),

    ("md", "## 8. Sensitivity: local elasticity and global Sobol indices"),
    ("code", """from analysis import oat_sensitivity

pars = ["lhv_pks_MJ_per_kg", "lhv_coal_MJ_per_kg", "co2_coal_kg_per_GJ", "co2_pks_kg_per_GJ",
        "drying_heat_MJ_per_kg", "crusher_kWh_per_kg", "aux_kWh_per_kg_fuel", "stockpile_ch4_kg_per_kg"]
oat = oat_sensitivity(scenarios[-1], pars, delta=0.10)
oat.round(4)"""),

    ("code", """from analysis import sobol_indices
from config import p

ranges = {name: (p(name) * 0.8, p(name) * 1.2) for name in pars}
sob = sobol_indices(scenarios[-1], pars, ranges, n=64)
display(sob.round(4))

fig, ax = plt.subplots(figsize=(8, 3.4))
ax.barh(sob["parameter"][::-1], sob["ST"][::-1], color="#2f6b3f")
ax.set(xlabel="total-order Sobol index ST", title="Global sensitivity, GWP100 at 30 % co-firing")
ax.grid(alpha=.3, axis="x"); plt.tight_layout(); plt.show()"""),

    ("md", """OAT gives local elasticity around the base case; Sobol ranks influence
across the whole plausible parameter space. When the two rankings disagree, the
model is non-linear and only the global result should drive design decisions.

Note that the OAT loop **rebuilds the Brightway foreground for every
perturbation**, so it is the model that is perturbed, not just the result."""),

    ("md", """## 9. Cross-validation against an independent implementation

The same inventory is scored outside Brightway as `g = CF·(B s)` in pandas. Two
independent implementations agreeing to float32 precision is the cheapest
available guard against a silent modelling error — and the single most useful cell
to show a reviewer."""),
    ("code", """from analysis import cross_validate

val = cross_validate(scenarios)
print("max relative deviation:", f"{val['rel_diff'].max():.2e}")
val.round(6)"""),

    ("md", "## 10. Export results"),
    ("code", """from config import OUTPUT_DIR

scores.to_csv(OUTPUT_DIR / "scores.csv")
summary.to_csv(OUTPUT_DIR / "monte_carlo.csv")
oat.to_csv(OUTPUT_DIR / "oat_sensitivity.csv", index=False)
sob.to_csv(OUTPUT_DIR / "sobol_indices.csv", index=False)
val.to_csv(OUTPUT_DIR / "validation.csv", index=False)
sorted(pth.name for pth in OUTPUT_DIR.glob("*.csv"))"""),

    ("md", """## 11. Interpretation (ISO 14044)

1. **Fossil climate impact decreases roughly linearly** with the co-firing share,
   partially offset by the efficiency penalty and by PKS supply-chain burdens.
2. **The conclusion is not robust below ~20 % co-firing** once data quality is
   propagated. Uncertainty is the result, not an appendix.
3. **Burden shifting is real**: land use grows monotonically with the PKS share,
   and transport mode choice moves acidification and particulate formation.
4. **Biogenic CO₂ is reported separately** (ISO 14067); it is never netted into
   the headline fossil figure.
5. **Highest-value data improvements** are the ones the Sobol ranking puts on top —
   that is where primary measurement should be spent next.

### Limitations and next steps

The background is a pre-characterised proxy, so background contribution detail is
unavailable; with a licensed ecoinvent the same foreground links to real market
activities via `bw2io`. Natural extensions: a prospective background with
`premise` (grid decarbonisation makes the co-firing benefit shrink over time), a
time-explicit biogenic carbon model with `bw_temporalis`, and a PULPO
formulation that optimises the co-firing share under fuel-supply constraints
instead of comparing five fixed scenarios."""),
]


def cell(kind: str, source: str) -> dict:
    lines = source.split("\n")
    src = [ln + "\n" for ln in lines[:-1]] + [lines[-1]]
    if kind == "md":
        return {"cell_type": "markdown", "metadata": {}, "source": src}
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": src}


def main() -> Path:
    nb = {
        "cells": [cell(k, s) for k, s in CELLS],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
            "colab": {"provenance": []},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    out = Path(__file__).parent / "notebooks" / "PKS_Cofiring_Brightway.ipynb"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    print("written:", main())
