"""Pedigree matrix -> lognormal uncertainty for Brightway exchanges.

Uses the standard ecoinvent/Weidema pedigree uncertainty factors. Each exchange
gets an uncertainty distribution derived from its own data-quality scores, so
"measured on site" and "literature guess" do not enter the Monte Carlo with the
same confidence.
"""

from __future__ import annotations

import math

import pandas as pd

from datasets import read_table

# Additional-uncertainty factors (contribution to the squared geometric SD)
PEDIGREE_FACTORS = {
    "reliability": [1.00, 1.54, 1.61, 1.69, 1.69],
    "completeness": [1.00, 1.03, 1.04, 1.08, 1.08],
    "temporal": [1.00, 1.03, 1.10, 1.19, 1.29],
    "geographical": [1.00, 1.04, 1.08, 1.11, 1.11],
    "technological": [1.00, 1.18, 1.65, 2.08, 2.80],
}
BASIC_UNCERTAINTY = 1.05


def gsd2(scores: dict[str, int], basic: float = BASIC_UNCERTAINTY) -> float:
    """Squared geometric standard deviation from pedigree scores (1..5)."""
    total = math.log(basic) ** 2
    for indicator, factors in PEDIGREE_FACTORS.items():
        s = int(scores.get(indicator, 3))
        s = min(max(s, 1), 5)
        total += math.log(factors[s - 1]) ** 2
    return math.exp(math.sqrt(total))


def lognormal_dict(amount: float, scores: dict[str, int]) -> dict:
    """Brightway/stats_arrays uncertainty dictionary for a lognormal exchange."""
    if amount == 0:
        return {"uncertainty type": 0, "amount": 0.0}
    g2 = gsd2(scores)
    return {
        "uncertainty type": 2,  # lognormal
        "amount": amount,
        "loc": math.log(abs(amount)),
        "scale": 0.5 * math.log(g2),
        "negative": amount < 0,
        "pedigree": dict(scores),
        "GSD2": g2,
    }


def load_pedigree_scores(path=None) -> dict[str, dict[str, int]]:
    """Pedigree scores per process, read from the field inventory CSV.

    The original field inventory carries pedigree scores per exchange; we keep the
    most conservative (highest) score per process and indicator, and fall back to
    a documented default of 3 for exchanges the field sheet does not cover.
    """
    df = read_table("inventory", path)
    cols = {
        "reliability": "ped_reliability",
        "completeness": "ped_completeness",
        "temporal": "ped_temporal",
        "geographical": "ped_geographical",
        "technological": "ped_technological",
    }
    out: dict[str, dict[str, int]] = {}
    for pid, grp in df.groupby("process_id"):
        out[str(pid)] = {k: int(grp[c].max()) for k, c in cols.items()}
    return out


DEFAULT_SCORES = {k: 3 for k in PEDIGREE_FACTORS}


def scores_for(process: str, table: dict[str, dict[str, int]] | None = None) -> dict[str, int]:
    table = table if table is not None else load_pedigree_scores()
    return table.get(process, DEFAULT_SCORES)
