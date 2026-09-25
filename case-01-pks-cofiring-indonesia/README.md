# PKS co-firing LCA in Brightway

A scripted, uncertainty-first life cycle assessment of **palm kernel shell (PKS)
co-firing in a 300 MW sub-critical coal power unit (PLTU)**, implemented with the
open-source [Brightway](https://github.com/brightway-lca) framework instead of a
GUI LCA application.

The same inventory was previously modelled in OpenLCA and in a plain pandas
matrix notebook. This repository re-expresses it as a real Brightway project so
that scenarios, uncertainty and sensitivity become code — the working mode that
ex-ante and prospective LCA require.

> All input values are **dummy data that mimic the structure of real plant
> records** (coal flow meter, CEMS, fuel lab, delivery notes). Replace them with
> primary data before any external reporting or comparative claim.

## Goal and scope

| Item | Definition |
|---|---|
| Functional unit | 1 MWh net electricity delivered to the Java-Bali grid |
| Reference flow | `P5_Generation` producing 1 MWh |
| System boundary | allocated PKS plantation and mill burden, drying and size reduction, truck and barge transport, on-site handling, boiler combustion, FGD reagent, process water, controlled FABA landfilling |
| Excluded (cut-off) | plant construction and decommissioning |
| Standards | ISO 14040/14044, ISO 14067 (fossil and biogenic reported separately) |
| LCIA | ReCiPe 2016 v1.03 (H) midpoint, registered from `data/recipe2016_characterization_factors.csv` |
| Scenarios | 0 %, 5 %, 10 %, 20 %, 30 % co-firing on an energy basis, with scenario-specific net efficiency and transport distances |

Following ISO 14067, **biogenic CO₂ is characterised separately** (CF = 0 in
GWP100) rather than netted into the headline figure.

## Quick start

### Google Colab

```python
!git clone https://github.com/<username>/pks-cofiring-brightway.git
%cd pks-cofiring-brightway
!pip install -q -r requirements.txt
# then open notebooks/PKS_Cofiring_Brightway.ipynb
```

### Local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd src && python analysis.py          # full run, results written to output/
```

## Repository layout

```text
pks-cofiring-brightway/
├── README.md                 this file
├── COMPARISON.md             GUI LCA software vs open-source frameworks, skills roadmap
├── requirements.txt
├── data/                     field data, CFs, proxy background, scenarios (dummy)
├── src/
│   ├── config.py             every assumption and parameter, with a source note
│   ├── scenarios.py          parametric inventory: co-firing share -> exchanges
│   ├── pedigree.py           pedigree matrix -> lognormal uncertainty
│   ├── build_project.py      builds biosphere, proxy background, foreground
│   ├── methods.py            registers ReCiPe 2016 midpoint methods
│   └── analysis.py           LCIA, contribution, Monte Carlo, OAT, Sobol, validation
├── notebooks/
│   └── PKS_Cofiring_Brightway.ipynb
└── output/                   generated CSV results
```

## Model design

**Parametric, not typed in.** No inventory number is hard-coded. Given a
co-firing share, net efficiency and transport distances, `scenarios.build_inventory`
computes fuel masses, combustion emissions, FGD reagent, ash, auxiliary power and
water from fuel properties and IPCC 2006 emission factors. The 0 % case reproduces
the measured baseline inventory, which is how the parameters were calibrated.

**PKS-specific emission factors are derived, not invented.** NOx, SO₂ and PM₂.₅
factors for PKS are the calibrated coal factors scaled by the ratio of the
responsible fuel property (fuel-bound nitrogen, sulphur, ash) from the lab
results. The assumption is explicit in `config.PKS_SCALING` and testable.

**Uncertainty comes from data quality.** Pedigree scores in the field inventory are
converted to squared geometric standard deviations with the standard Weidema
factors, attached to each exchange as a lognormal distribution, and propagated by
Brightway's Monte Carlo. Results are reported as distributions and as
*probability that a co-firing scenario beats the baseline*, not as point scores.

**Two independent implementations.** `analysis.surrogate_score` computes the same
result outside Brightway as `g = CF·(B s)` in pandas, and `analysis.cross_validate`
asserts agreement across every scenario and impact category (achieved: max
relative deviation ≈ 6 × 10⁻⁸, i.e. float32 matrix precision).

## Results (dummy data)

GWP100, kg CO₂-eq per MWh net, fossil only (biogenic CO₂ characterised separately):

| Scenario | GWP100 | Land use (m²a) | Monte Carlo P(better than baseline) |
|---|---|---|---|
| baseline_0pct | 1114 | 0 | — |
| cofire_5pct | 1072 | 13.6 | 0.52 |
| cofire_10pct | 1031 | 27.5 | 0.58 |
| cofire_20pct | 942 | 56.0 | 0.67 |
| cofire_30pct_barge | 853 | 85.9 | 0.79 |

The interesting result is not the mean reduction — it is that at 5–10 % co-firing
the improvement is **not robust** under data-quality uncertainty (P ≈ 0.52–0.58,
barely better than a coin toss), while land use rises monotonically. A point
score would have hidden both.

## Limitations

1. **Background is a pre-characterised proxy.** `data/background_factors_ecoinvent_proxy.csv`
   gives aggregated impacts per unit, so each background activity emits one
   aggregated indicator flow with CF = 1. With a licensed ecoinvent, replace
   `build_project.write_background` with a `bw2io` ecoinvent import and link the
   foreground to real market activities; the aggregated flows then disappear.
2. **Proxy background carries no elementary-flow detail**, so background
   contribution analysis is limited to totals.
3. **No prospective background.** Coupling to IAM pathways via `premise` requires
   ecoinvent and is listed as future work.
4. **Static characterisation.** Biogenic carbon timing would need `bw_temporalis`.
5. **Dummy data throughout**, including the original field logs.
6. Monte Carlo scenarios share a seed, so cross-scenario comparisons are
   correlated by construction; this is intended for paired comparison, not for
   independent absolute uncertainty of each scenario.

## Provenance

Field data, characterisation factors and scenario definitions come from the
author's earlier ISO 14067 PKS co-firing study (2025 field campaign, dummy-value
version). The Brightway implementation, parametric scenario model, pedigree
uncertainty layer and cross-validation in this repository are new.

## Continuous integration

`.github/workflows/pks-lca.yml` runs on every push and pull request that touches
this folder. It installs `requirements.txt`, runs `pytest` (energy balance,
inventory logic, pedigree uncertainty and the Brightway-vs-pandas
cross-validation), re-runs the full LCA under **all four electricity background
models**, regenerates and executes the Colab notebook, builds the HTML report,
fails if any notebook cell raised, and uploads `output/` plus the executed
notebook as build artifacts. That means every commit ships an independently
reproduced result set, not just code.

## Exportable report

```bash
python src/report.py                 # active electricity mode, HTML + PDF
python src/report.py all-modes       # includes the background-model comparison
python src/report.py all-modes --no-pdf
```

The report is a single self-contained HTML file (figures embedded as base64) with
goal and scope, the electricity model in force, the scenario table, every
parameter with its source, impact results, contribution analysis, Monte Carlo
distributions with P(better than baseline), OAT elasticity, Sobol indices, the
electricity-model comparison and the verification table. The PDF is rendered from
the same HTML, so the two can never disagree.


## Bring your own data (step by step)

Every input table is resolved through `src/datasets.py`, so you can swap the dummy
tables for your own without touching the model code.

1. Copy the folder `data/` to e.g. `my-data/` and keep the same file names
   (`fuel_quality_lab_results.csv`, `scenarios.csv`,
   `background_factors_ecoinvent_proxy.csv`,
   `recipe2016_characterization_factors.csv`, `inventory_pks_cofiring.csv`).
2. Replace the rows with your own values, keeping the column headers.
3. Point the model at the new folder and validate before running:

   ```bash
   export PKS_DATA_DIR=$PWD/my-data
   python src/data_check.py            # missing columns, negatives, unmapped keys
   ```

4. Prefer one workbook? Put each table on a sheet named after the file stem
   (`scenarios`, `fuel_quality_lab_results`, ...) and use:

   ```bash
   export PKS_DATA_XLSX=$PWD/my-data/pks_inputs.xlsx
   python src/data_check.py
   ```

5. Re-run everything. Each run writes a provenance record (dataset source,
   SHA-256 digest, parameter set, Brightway mapping, git commit, seed) into
   `output/provenance/` and into the report footer:

   ```bash
   python src/analysis.py
   python src/report.py all-modes
   python src/dashboard.py            # output/dashboard.html + dashboard_data.json
   ```

If validation fails, fix the reported cell before running the LCA — the checker is
the cheapest place to catch a unit or mapping mistake.
