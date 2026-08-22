"""Register ReCiPe 2016 (H) midpoint methods in Brightway from the CF table.

This is a deliberate demonstration of what a framework buys you over a GUI: the
LCIA method is data, written by code, versioned in git, and reproducible from a
CSV a reviewer can read.
"""

from __future__ import annotations

import pandas as pd
from bw2data import Method, methods

from config import (
    AGGREGATED_BACKGROUND_FLOWS,
    BIOSPHERE_DB,
    METHOD_FAMILY,
    BIOSPHERE_FLOWS,
)
from build_project import flow_key
from datasets import read_table


def load_cfs(path=None) -> pd.DataFrame:
    return read_table("characterization", path)


def impact_categories(cfs: pd.DataFrame | None = None) -> list[str]:
    cfs = cfs if cfs is not None else load_cfs()
    cats = list(dict.fromkeys(cfs["impact_category"].tolist()))
    for _, (_, cat, _) in AGGREGATED_BACKGROUND_FLOWS.items():
        if cat not in cats:
            cats.append(cat)
    return cats


def method_key(category: str) -> tuple:
    return (*METHOD_FAMILY, category)


# Flow-name aliases: the CF table and the parametric inventory use slightly
# different labels for the same elementary flow.
CF_ALIASES = {
    "CH4 pembakaran": "CH4 fosil",
    "CH4 degradasi stockpile PKS": "CH4 biogenik",
    "N2O pembakaran": "N2O",
    "SO2 pasca-FGD": "SO2",
}


def write_methods(overwrite: bool = True) -> list[tuple]:
    cfs = load_cfs()
    written = []
    for category in impact_categories(cfs):
        key = method_key(category)
        if key in methods and not overwrite:
            written.append(key)
            continue

        data: list[tuple] = []
        sub = cfs[cfs["impact_category"] == category]
        unit = sub["cf_unit"].iloc[0].split("/")[0] if len(sub) else "unit"
        for r in sub.itertuples():
            name = CF_ALIASES.get(r.flow_name, r.flow_name)
            if name not in BIOSPHERE_FLOWS:
                continue
            data.append((flow_key(name), float(r.cf_midpoint)))

        # aggregated background indicator flow, CF = 1 by construction
        for _, (flow_name, cat, cf_unit) in AGGREGATED_BACKGROUND_FLOWS.items():
            if cat == category:
                data.append((flow_key(flow_name), 1.0))
                unit = cf_unit

        m = Method(key)
        m.register(
            unit=unit,
            description=(
                f"ReCiPe 2016 v1.03 (H) midpoint proxy for {category}, built from "
                "data/recipe2016_characterization_factors.csv. Includes an "
                "aggregated background indicator flow with CF = 1 (see README)."
            ),
            biosphere_database=BIOSPHERE_DB,
        )
        m.write(data)
        written.append(key)
    return written
