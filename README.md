# LCA & EIA work with Python and Brightway

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Brightway](https://img.shields.io/badge/Brightway-2.5-green)

A working collection of **life cycle assessment (LCA)** and **environmental
impact assessment (EIA)** case studies built as code — Python, Brightway,
pandas, SALib — rather than as saved files in a graphical LCA application.

The purpose is methodological. In a GUI tool a scenario is a copy of a product
system and the technosphere matrix is hidden behind the solver. Here the
inventory is a *function* of physical parameters, uncertainty comes from
documented data quality rather than a default, and every result can be
regenerated from a clean clone with one command. That is the working mode that
ex-ante and prospective LCA require.

## Case studies

| # | Case | Method stack | Status |
|---|---|---|---|
| 01 | **Palm kernel shell (PKS) co-firing in a 300 MW Indonesian sub-critical coal unit** — 0–30 % co-firing on an energy basis, cradle-to-grave fuel chain, ISO 14067 fossil/biogenic split, plus a linked techno-economic assessment | Brightway 2.5, ReCiPe 2016 (H) midpoint, pedigree-based Monte Carlo, OAT + Sobol GSA, switchable marginal-electricity background, LCA/TEA workbook | complete |
| 02 | *(planned)* EIA screening with input–output / EEIO hybridisation | MARIO, Exiobase | planned |

## How to read this repository in five minutes

1. Open the case folder [`case-01-pks-cofiring-indonesia/`](case-01-pks-cofiring-indonesia/)
   and read its `README.md` — goal, scope, functional unit, headline results.
2. Look at `docs/` for the rendered **LCA / carbon footprint / TEA reports** and the
   `output/pks_cofiring_report.pdf` generated directly by the code.
3. Open `output/dashboard.html` for the interactive scenario, Monte Carlo and
   Sobol comparison.
4. If you want the method rather than the numbers, read
   `src/scenarios.py` (the inventory is computed, not typed in),
   `src/pedigree.py` (data quality → lognormal uncertainty) and the
   cross-validation in `src/analysis.py`, which reproduces every Brightway result
   with an independent pandas implementation of `g = C·B·A⁻¹f`.
5. `COMPARISON.md` explains where GUI LCA software still wins and where a
   framework is the only option.

## Shared toolchain

`bw2data` / `bw2calc` / `bw2io` (Brightway 2.5) · `stats_arrays` for uncertainty ·
`pandas` / `numpy` · `SALib` for Sobol · `matplotlib` and `plotly` for figures ·
`pytest` for the model tests · GitHub Actions for continuous reproduction ·
`nbclient` to execute the notebooks in CI.

## Reproducing a case

```bash
git clone https://github.com/robbyfajrino/LCA-EIA-work-with-Python-and-Brightway2.git
cd LCA-EIA-work-with-Python-and-Brightway2/case-01-pks-cofiring-indonesia
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python src/data_check.py        # validate the input tables first
python src/analysis.py         # LCIA, contribution, Monte Carlo, OAT, Sobol, validation
python src/report.py all-modes  # HTML + PDF report
pytest                          # model tests incl. Brightway vs pandas cross-validation
```

Google Colab: open `notebooks/PKS_Cofiring_Brightway.ipynb` and run the first
cell, which installs the pinned requirements.

## Data statement

Input tables in these case studies are **dummy values that reproduce the
structure of real plant records** (coal flow meter, CEMS, fuel laboratory
results, delivery notes) from a 2025 field campaign. They are realistic in
magnitude and internally consistent, but they must not be used for external
reporting or comparative assertions. Every table is swappable — see the
"Bring your own data" section in the case README.

## Standards followed

ISO 14040 / ISO 14044 (LCA framework and requirements), ISO 14067 (product
carbon footprint, with biogenic CO₂ characterised separately from fossil CO₂),
ILCD/Weidema pedigree matrix for data-quality uncertainty.

## Author

**Robby Fajrino Nugraha** — MSc Environmental Technology and Engineering
(Erasmus Mundus: IHE Delft · Ghent University · UCT Prague),
BSc Chemistry (Universitas Indonesia). Sustainability data analyst working on GHG inventories,
product carbon footprints and LCA in Indonesia.

- Portfolio: https://robby-fajrino.lovable.app
- LinkedIn: https://www.linkedin.com/in/robbyfnugraha
- Contact: see the portfolio site

> [Computer software]. GitHub.
> https://github.com/robbyfajrino/LCA-EIA-work-with-Python-and-Brightway2
