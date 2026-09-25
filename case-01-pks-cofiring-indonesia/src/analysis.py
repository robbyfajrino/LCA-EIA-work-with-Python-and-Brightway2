"""LCIA, contribution analysis, Monte Carlo, and sensitivity on top of Brightway."""

from __future__ import annotations

import numpy as np
import pandas as pd

import bw2data as bd
from bw2calc import LCA

from build_project import build_all, foreground_key
from config import BACKGROUND_DB, FOREGROUND_DB, OUTPUT_DIR
from methods import impact_categories, method_key
from scenarios import Scenario, build_inventory, load_scenarios

GWP = "GWP100 (climate change)"
MC_SEED = 42


# --------------------------------------------------------------------------- #
# Static LCIA
# --------------------------------------------------------------------------- #
def score(scenario: str, category: str = GWP) -> float:
    act = bd.get_activity(foreground_key("P5_Generation", scenario))
    lca = LCA({act: 1.0}, method=method_key(category))
    lca.lci()
    lca.lcia()
    return float(lca.score)


def score_table(scenarios: list[str], categories: list[str] | None = None) -> pd.DataFrame:
    categories = categories or impact_categories()
    rows = []
    for sc in scenarios:
        row = {"scenario": sc}
        for cat in categories:
            row[cat] = score(sc, cat)
        rows.append(row)
    return pd.DataFrame(rows).set_index("scenario")


def contribution_by_stage(scenario: str, category: str = GWP) -> pd.DataFrame:
    """Score of each life-cycle stage, isolated by cutting the stage links."""
    stages = ["P1_PKM", "P2_Drying", "P3_Transport", "P4_Handling", "P6_Ash"]
    rows = []
    for stage in stages:
        act = bd.get_activity(foreground_key(stage, scenario))
        lca = LCA({act: 1.0}, method=method_key(category))
        lca.lci()
        lca.lcia()
        rows.append({"stage": stage, "score": float(lca.score)})
    # P5 minus the stage services it consumes = direct generation burden
    total = score(scenario, category)
    rows.append({"stage": "P5_Generation (direct)", "score": total - sum(r["score"] for r in rows)})
    df = pd.DataFrame(rows)
    df["share_pct"] = df["score"] / total * 100.0
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def biosphere_contributions(scenario: str, category: str = GWP, top: int = 10) -> pd.DataFrame:
    act = bd.get_activity(foreground_key("P5_Generation", scenario))
    lca = LCA({act: 1.0}, method=method_key(category))
    lca.lci()
    lca.lcia()
    matrix = lca.characterized_inventory.tocoo()
    rows: dict[str, float] = {}
    rev_bio = {v: k for k, v in lca.dicts.biosphere.items()}
    for i, v in zip(matrix.row, matrix.data):
        flow = bd.get_activity(rev_bio[i])
        rows[flow["name"]] = rows.get(flow["name"], 0.0) + float(v)
    df = pd.DataFrame({"flow": list(rows), "score": list(rows.values())})
    df["share_pct"] = df["score"] / df["score"].sum() * 100
    return df.sort_values("score", ascending=False).head(top).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Monte Carlo (pedigree-derived lognormal uncertainty)
# --------------------------------------------------------------------------- #
def monte_carlo(scenario: str, iterations: int = 500, category: str = GWP, seed: int = MC_SEED) -> np.ndarray:
    act = bd.get_activity(foreground_key("P5_Generation", scenario))
    lca = LCA({act: 1.0}, method=method_key(category), use_distributions=True, seed_override=seed)
    lca.lci()
    lca.lcia()
    out = np.empty(iterations)
    for i, _ in zip(range(iterations), lca):
        out[i] = lca.score
    return out


def mc_summary(samples: dict[str, np.ndarray]) -> pd.DataFrame:
    rows = []
    for name, s in samples.items():
        rows.append(
            {
                "scenario": name,
                "mean": s.mean(),
                "median": np.median(s),
                "p5": np.percentile(s, 5),
                "p95": np.percentile(s, 95),
                "cv_pct": s.std(ddof=1) / s.mean() * 100,
            }
        )
    return pd.DataFrame(rows).set_index("scenario")


def probability_of_improvement(baseline: np.ndarray, alternative: np.ndarray) -> float:
    """P(alternative < baseline) on paired Monte Carlo samples."""
    n = min(len(baseline), len(alternative))
    return float(np.mean(alternative[:n] < baseline[:n]))


# --------------------------------------------------------------------------- #
# Sensitivity
# --------------------------------------------------------------------------- #
def oat_sensitivity(sc: Scenario, parameters: list[str], delta: float = 0.10, category: str = GWP) -> pd.DataFrame:
    """One-at-a-time elasticity, rebuilding the foreground for each perturbation.

    Only the foreground is rewritten; biosphere, background and the registered
    methods stay untouched so their processed matrices remain valid.
    """
    from config import p

    base = _rebuild_and_score(sc, {}, category)
    rows = []
    for name in parameters:
        hi = _rebuild_and_score(sc, {name: p(name) * (1 + delta)}, category)
        lo = _rebuild_and_score(sc, {name: p(name) * (1 - delta)}, category)
        rows.append(
            {
                "parameter": name,
                "score_low": lo,
                "score_high": hi,
                "elasticity": ((hi - lo) / (2 * delta)) / base,
            }
        )
    df = pd.DataFrame(rows)
    df["abs_elasticity"] = df["elasticity"].abs()
    return df.sort_values("abs_elasticity", ascending=False).reset_index(drop=True)


def _rebuild_and_score(sc: Scenario, overrides: dict[str, float], category: str) -> float:
    from build_project import write_foreground

    write_foreground([sc], overrides)
    return score(sc.name, category)


def sobol_indices(
    sc: Scenario,
    parameters: list[str],
    ranges: dict[str, tuple[float, float]],
    n: int = 32,
    category: str = GWP,
) -> pd.DataFrame:
    """Variance-based global sensitivity (Sobol) on the parametric model.

    Runs on a fast surrogate: the parametric inventory combined with the proxy
    background factors, which reproduces the Brightway score exactly (see the
    cross-validation cell), so thousands of samples stay cheap.
    """
    from SALib.analyze import sobol as sobol_analyze
    from SALib.sample import sobol as sobol_sample

    problem = {
        "num_vars": len(parameters),
        "names": parameters,
        "bounds": [list(ranges[p_]) for p_ in parameters],
    }
    X = sobol_sample.sample(problem, n, calc_second_order=False)
    Y = np.array([surrogate_score(sc, dict(zip(parameters, row)), category) for row in X])
    Si = sobol_analyze.analyze(problem, Y, calc_second_order=False, print_to_console=False)
    return (
        pd.DataFrame({"parameter": parameters, "S1": Si["S1"], "ST": Si["ST"]})
        .sort_values("ST", ascending=False)
        .reset_index(drop=True)
    )


# --------------------------------------------------------------------------- #
# Independent pandas surrogate, used for cross-validation and for Sobol
# --------------------------------------------------------------------------- #
def surrogate_score(sc: Scenario, overrides: dict[str, float] | None = None, category: str = GWP) -> float:
    """Score the same inventory without Brightway, as g = CF . (B s).

    Two independent implementations of one model is the cheapest available guard
    against silent modelling errors.
    """
    from build_project import load_background_table
    from methods import CF_ALIASES, load_cfs
    from config import AGGREGATED_BACKGROUND_FLOWS, TECHNOSPHERE_MAP

    inv = build_inventory(sc, overrides)
    bg = load_background_table().set_index("background_key")
    cfs = load_cfs()
    cfs = cfs[cfs["impact_category"] == category]
    cf_map: dict[str, float] = {}
    for r in cfs.itertuples():
        cf_map[CF_ALIASES.get(r.flow_name, r.flow_name)] = float(r.cf_midpoint)

    bg_column = None
    for column, (_flow, cat, _unit) in AGGREGATED_BACKGROUND_FLOWS.items():
        if cat == category:
            bg_column = column
    total = 0.0
    for r in inv.itertuples():
        if r.kind == "technosphere":
            if bg_column is None:
                continue
            total += r.amount * float(bg.loc[TECHNOSPHERE_MAP[r.flow], bg_column])
        else:
            total += r.amount * cf_map.get(r.flow, 0.0)
    return total


# Brightway stores matrix data in float32, so agreement is checked at 1e-5
# relative tolerance rather than machine epsilon.
def cross_validate(scenarios: list[Scenario], categories: list[str] | None = None, rtol: float = 1e-5) -> pd.DataFrame:
    from build_project import write_foreground

    # make sure the unperturbed foreground for every scenario is in the database
    write_foreground(scenarios)
    categories = categories or impact_categories()
    rows = []
    for sc in scenarios:
        for cat in categories:
            bw = score(sc.name, cat)
            ref = surrogate_score(sc, None, cat)
            rows.append(
                {
                    "scenario": sc.name,
                    "category": cat,
                    "brightway": bw,
                    "pandas_matrix": ref,
                    "rel_diff": 0.0 if ref == 0 else abs(bw - ref) / abs(ref),
                }
            )
    df = pd.DataFrame(rows)
    assert df["rel_diff"].max() < rtol, f"cross-validation failed: {df['rel_diff'].max():.2e}"
    return df


# --------------------------------------------------------------------------- #
# Entry point: full run, results written to output/
# --------------------------------------------------------------------------- #
def run_all(
    iterations: int = 400,
    electricity_mode: str | None = None,
    output_dir=None,
    sensitivity: bool = True,
    sobol_n: int = 32,
) -> dict[str, pd.DataFrame]:
    """Full LCA run for one electricity-background model.

    `electricity_mode` selects a key of config.ELECTRICITY_MODES, e.g.
    'marginal_time_of_use' vs 'marginal_time_of_construction'. Results are
    written as CSV to `output_dir` (default: output/, or output/modes/<mode> for
    a non-default mode).
    """
    from config import (
        DEFAULT_ELECTRICITY_MODE,
        SENSITIVITY_PARAMETERS,
        electricity_mode_spec,
        p,
        set_electricity_mode,
    )

    mode = set_electricity_mode(electricity_mode or DEFAULT_ELECTRICITY_MODE)
    out = output_dir or (OUTPUT_DIR if mode == DEFAULT_ELECTRICITY_MODE else OUTPUT_DIR / "modes" / mode)
    out.mkdir(parents=True, exist_ok=True)

    scs = load_scenarios()
    build_all(scs)
    from methods import write_methods

    write_methods()

    results = {}
    results["scores"] = score_table([s.name for s in scs])
    results["validation"] = cross_validate(scs)
    results["contribution_baseline"] = contribution_by_stage("baseline_0pct")
    results["contribution_30pct"] = contribution_by_stage("cofire_30pct_barge")

    samples = {s.name: monte_carlo(s.name, iterations) for s in scs}
    results["monte_carlo"] = mc_summary(samples)
    results["monte_carlo"]["p_better_than_baseline"] = [
        probability_of_improvement(samples["baseline_0pct"], samples[s.name]) for s in scs
    ]

    if sensitivity:
        pars = SENSITIVITY_PARAMETERS
        results["oat_sensitivity"] = oat_sensitivity(scs[-1], pars, delta=0.10)
        ranges = {name: (p(name) * 0.8, p(name) * 1.2) for name in pars}
        results["sobol_indices"] = sobol_indices(scs[-1], pars, ranges, n=sobol_n)
        # the OAT loop rewrote the foreground with perturbed parameters
        from build_project import write_foreground

        write_foreground(scs)

    spec = electricity_mode_spec(mode)
    results["electricity_model"] = pd.DataFrame(
        [{"mode": mode, **{k: v for k, v in spec.items()}}]
    ).set_index("mode")

    for name, df in results.items():
        index = name in ("scores", "monte_carlo", "electricity_model")
        df.to_csv(out / f"{name}.csv", index=index)

    # --- provenance: pin the inputs this result came from -------------------
    import provenance as prov

    record = prov.record(mode=mode, iterations=iterations, seed=MC_SEED, sobol_n=sobol_n if sensitivity else None)
    prov.write(record, out)
    results["provenance_summary"] = prov.summary_table(record)
    results["provenance_datasets"] = prov.dataset_table(record)
    results["provenance_mapping"] = prov.mapping_table(record)

    results["_meta"] = {"mode": mode, "output_dir": out, "samples": samples, "provenance": record}
    return results


def run_electricity_modes(
    modes: list[str] | None = None, iterations: int = 300, sobol_n: int = 32
) -> dict[str, dict]:
    """Re-run every scenario under each electricity model and tabulate the swing."""
    from config import ELECTRICITY_MODES

    modes = modes or list(ELECTRICITY_MODES)
    runs = {m: run_all(iterations=iterations, electricity_mode=m, sobol_n=sobol_n) for m in modes}

    gwp = pd.DataFrame({m: runs[m]["scores"][GWP] for m in modes})
    gwp.index.name = "scenario"
    gwp.to_csv(OUTPUT_DIR / "electricity_mode_comparison.csv")

    prob = pd.DataFrame({m: runs[m]["monte_carlo"]["p_better_than_baseline"] for m in modes})
    prob.index.name = "scenario"
    prob.to_csv(OUTPUT_DIR / "electricity_mode_probability.csv")
    return {"runs": runs, "gwp": gwp, "probability": prob}


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else None
    if mode == "all-modes":
        comparison = run_electricity_modes()
        print("\n=== GWP100 per MWh by electricity model ===")
        print(comparison["gwp"].round(1).to_string())
        print("\n=== P(better than baseline) by electricity model ===")
        print(comparison["probability"].round(3).to_string())
    else:
        for name, df in run_all(electricity_mode=mode).items():
            if name.startswith("_"):
                continue
            print(f"\n=== {name} ===")
            print(df.to_string())

