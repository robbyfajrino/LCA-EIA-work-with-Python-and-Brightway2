# GUI LCA software vs. open-source LCA frameworks

Reference note written while building this repository. It exists because the
distinction matters for ex-ante LCA: the question is not "which tool computes
`A⁻¹f` faster", but "can the model itself be reprogrammed".

## 1. The short answer

| | OpenLCA / SimaPro / GaBi | Brightway, lcpy, PULPO, Futura, Temporalis |
|---|---|---|
| Interaction | graphical application | Python library imported into your own code |
| Unit of work | a saved project file | a script plus a database, in git |
| Matrices `A`, `B` | hidden behind the solver | first-class objects you can read and rewrite |
| LCIA methods | shipped, fixed implementations | data you register yourself (see `src/methods.py`) |
| Scenarios | manual copies of a product system | a function argument (see `src/scenarios.py`) |
| Uncertainty | built-in Monte Carlo, limited control | any distribution, any correlation, any sampler |
| Background editing | select a dataset from a list | rewrite thousands of datasets programmatically (`premise`) |
| Optimisation | not available | native (`PULPO`) |
| Time resolution | static (GWP100 fixed horizon) | dynamic, time-explicit inventories (`bw_temporalis`) |
| Reproducibility | depends on the saved file and the software version | `git clone` and re-run |
| Strength | audited compliance reporting, client deliverables, EPD workflows | research, ex-ante and prospective modelling, thousands of runs |

They are not rivals. GUI tools are still where a certified, reviewable PCF report
is produced. Frameworks are where a *method* is developed.

## 2. What actually changes in practice

**A calculation becomes an experiment.** In SimaPro a scenario is a copy of a
product system; if a reviewer asks "what if net efficiency drops 2 points and
transport doubles", you click. In Brightway that question is a loop, and the loop
can run 10,000 times overnight with results committed as a CSV.

**The background stops being fixed.** GUI tools let you pick an ecoinvent
dataset. `premise` lets you *rewrite* ecoinvent so the electricity mix, steel and
cement markets follow an IAM pathway (SSP/RCP, chosen year). For any technology
assessed before it is deployed — grid-scale storage, co-firing at national
scale — this is the difference between an answer and a guess.

**Uncertainty becomes the result, not an appendix.** Pedigree scores can be turned
into per-exchange distributions in code (`src/pedigree.py`), then propagated,
then reported as "probability that scenario A beats scenario B" instead of a
single point score.

**Decisions can be optimised, not just compared.** PULPO reformulates the LCA
system as a linear program: instead of scoring three predefined options, it
solves for the technology mix that minimises an impact subject to capacity,
demand or budget constraints.

## 3. The tools named in this note

- **Brightway** (`bw2data`, `bw2calc`, `bw2io`, Activity Browser GUI on top) —
  the framework. Databases, activities, exchanges, methods, and the sparse
  matrices are Python objects. Everything else below builds on it.
- **`premise`** — prospective background databases from IAM scenarios
  (IMAGE, REMIND). Requires a licensed ecoinvent.
- **PULPO** — LCA as optimisation (mixed-integer/linear programming) rather
  than fixed-demand calculation; methanol case study published with a Zenodo
  dataset.
- **Futura** — structured "what-if" / scenario editing of a Brightway foreground.
- **Temporalis / `bw_temporalis`** — time-explicit inventories: emissions carry
  timestamps, so dynamic characterisation replaces a fixed 100-year horizon.
  Directly relevant to biogenic carbon timing in biomass co-firing.
- **`lcpy`-type builders** — helper layers that generate Brightway foregrounds
  from tabular input, similar in spirit to `src/build_project.py` here.
- **MARIO** (Politecnico di Milano, Climate Compatible Growth course, June 2025)
  — environmentally extended input-output analysis over Exiobase/EORA. Not a
  competitor to Brightway: it is the top-down counterpart. Where no process
  dataset exists for a future sector, an IO background gives macro-consistent
  coverage, and hybrid IO-process LCA is a recognised ex-ante strategy. Having
  already used MARIO in Python is a real asset for scenario-based LCA work.

## 4. Skills roadmap before the application deadline

Ordered by return on effort for a DC14-type ex-ante LCA position.

1. **Brightway 2.5 core** — build a project from scratch, write a database, register
   a custom LCIA method, run `LCA().lci()` / `.lcia()`, read
   `characterized_inventory`. *This repository is that exercise, done.*
2. **Uncertainty and sensitivity** — pedigree to lognormal, Monte Carlo,
   probability-of-improvement reporting, OAT elasticity, Sobol indices with
   SALib. *Also in this repository.*
3. **`bw2io` importers** — bring an Excel/SimaPro/ecoSpold inventory into
   Brightway and reconcile the linking failures. Practise on the OpenLCA export
   template in `data/`.
4. **Prospective background** — read the `premise` documentation and paper
   end to end; build one scenario-coupled background if an ecoinvent licence is
   available, and be honest in interview about what was executed versus read.
5. **`bw_temporalis`** — one small dynamic-LCA example on biogenic carbon.
6. **PULPO** — reproduce the published methanol case study from its Zenodo files.
7. **Software practice** — git history that shows incremental work, a README a
   stranger can run, pinned requirements, `pytest` for the calculation core, and
   a notebook that executes top to bottom in Colab.

The honest framing for a motivation letter and interview: *retrospective,
standard-compliant LCA in industry (ISO 14067, primary data, GUI tools), now
moving upstream to scripted, uncertainty-first ex-ante modelling* — with a public
repository, dated, as the evidence.
