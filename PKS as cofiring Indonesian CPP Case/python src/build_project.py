"""Build the Brightway project: biosphere, proxy background, and foreground.

Idempotent: running it twice leaves the same project state, so the notebook can
be re-executed in Colab without cleanup.
"""

from __future__ import annotations

import pandas as pd

import bw2data as bd

from config import (
    AGGREGATED_BACKGROUND_FLOWS,
    BACKGROUND_DB,
    BIOSPHERE_DB,
    BIOSPHERE_FLOWS,
    FOREGROUND_DB,
    FUNCTIONAL_UNIT,
    PROJECT_NAME,
    REFERENCE_FLOW_UNIT,
    TECHNOSPHERE_MAP,
)
from datasets import read_table
from pedigree import load_pedigree_scores, lognormal_dict, scores_for
from scenarios import Scenario, build_inventory


def slug(name: str) -> str:
    keep = [c.lower() if c.isalnum() else "_" for c in name]
    return "".join(keep).strip("_")


def flow_key(name: str) -> tuple[str, str]:
    return (BIOSPHERE_DB, slug(name))


def background_key(key: str) -> tuple[str, str]:
    return (BACKGROUND_DB, key)


def foreground_key(process: str, scenario: str) -> tuple[str, str]:
    return (FOREGROUND_DB, f"{scenario}::{process}")


def set_project(name: str = PROJECT_NAME) -> str:
    bd.projects.set_current(name)
    return name


# --------------------------------------------------------------------------- #
# Biosphere
# --------------------------------------------------------------------------- #
def write_biosphere() -> None:
    data = {}
    for name, (compartment, unit) in BIOSPHERE_FLOWS.items():
        data[flow_key(name)] = {
            "name": name,
            "categories": (compartment,),
            "unit": unit,
            "type": "emission" if compartment == "air" else "natural resource",
            "exchanges": [],
        }
    for _, (name, category, unit) in AGGREGATED_BACKGROUND_FLOWS.items():
        data[flow_key(name)] = {
            "name": name,
            "categories": ("aggregated background",),
            "unit": unit,
            "type": "emission",
            "comment": f"Pre-characterised proxy burden for {category}; CF = 1.",
            "exchanges": [],
        }
    db = bd.Database(BIOSPHERE_DB)
    db.write(data)


# --------------------------------------------------------------------------- #
# Proxy background
# --------------------------------------------------------------------------- #
def load_background_table(path=None, mode: str | None = None) -> pd.DataFrame:
    """Proxy background factors, with the electricity row set by the active
    marginal-electricity model (see config.ELECTRICITY_MODES)."""
    from config import (
        AGGREGATED_BACKGROUND_FLOWS as _AGG,
        ELECTRICITY_BACKGROUND_KEY,
        electricity_mode_spec,
    )

    bg = read_table("background", path)
    spec = electricity_mode_spec(mode)
    row = bg["background_key"] == ELECTRICITY_BACKGROUND_KEY
    if row.any():
        base_gwp = float(bg.loc[row, "kg_CO2eq_per_unit"].iloc[0])
        bg.loc[row, "kg_CO2eq_per_unit"] = spec["gwp_kg_per_kWh"]
        for column in _AGG:
            if column == "kg_CO2eq_per_unit":
                continue
            bg.loc[row, column] = bg.loc[row, column] * spec["co_scale"]
        bg.loc[row, "database_source"] = (
            f"{spec['label']} — {spec['source']} "
            f"(grid average in file: {base_gwp:g} kg CO2-eq/kWh)"
        )
    return bg



def write_background() -> None:
    bg = load_background_table()
    data = {}
    for r in bg.itertuples():
        key = background_key(r.background_key)
        exchanges = [
            {"input": key, "amount": 1.0, "type": "production", "unit": r.reference_unit}
        ]
        for column, (flow_name, _cat, _unit) in AGGREGATED_BACKGROUND_FLOWS.items():
            amount = float(getattr(r, column))
            exchanges.append(
                {
                    "input": flow_key(flow_name),
                    "amount": amount,
                    "type": "biosphere",
                    # database proxies: reliability 4, technological 3 (see README)
                    **{
                        k: v
                        for k, v in lognormal_dict(
                            amount,
                            {
                                "reliability": 4,
                                "completeness": 3,
                                "temporal": 3,
                                "geographical": 3,
                                "technological": 3,
                            },
                        ).items()
                        if k not in ("amount",)
                    },
                }
            )
        data[key] = {
            "name": r.activity_name,
            "unit": r.reference_unit,
            "location": "ID",
            "type": "process",
            "comment": r.database_source,
            "reference product": r.activity_name,
            "exchanges": exchanges,
        }
    bd.Database(BACKGROUND_DB).write(data)


# --------------------------------------------------------------------------- #
# Foreground
# --------------------------------------------------------------------------- #
STAGE_UNITS = {
    "P1_PKM": "unit",
    "P2_Drying": "unit",
    "P3_Transport": "unit",
    "P4_Handling": "unit",
    "P6_Ash": "unit",
}


def write_foreground(scenarios: list[Scenario], overrides: dict[str, float] | None = None) -> dict:
    """Write one set of foreground activities per scenario.

    P5_Generation is the reference activity producing 1 MWh net electricity; the
    other stages are modelled as unit services consumed once per functional unit.
    """
    ped = load_pedigree_scores()
    data: dict = {}
    inventories = {}

    for sc in scenarios:
        inv = build_inventory(sc, overrides)
        inventories[sc.name] = inv

        for process, grp in inv.groupby("process", sort=False):
            key = foreground_key(process, sc.name)
            is_ref = process == "P5_Generation"
            unit = REFERENCE_FLOW_UNIT if is_ref else "unit"
            exchanges = [{"input": key, "amount": 1.0, "type": "production", "unit": unit}]

            for r in grp.itertuples():
                sign = 1.0 if r.direction == "output" or r.kind == "technosphere" else 1.0
                if r.kind == "technosphere":
                    bg = TECHNOSPHERE_MAP[r.flow]
                    exch_input = background_key(bg)
                    exch_type = "technosphere"
                else:
                    exch_input = flow_key(r.flow)
                    exch_type = "biosphere"
                unc = lognormal_dict(r.amount * sign, scores_for(process, ped))
                exchanges.append(
                    {
                        "input": exch_input,
                        "amount": r.amount * sign,
                        "type": exch_type,
                        "unit": r.unit,
                        "name": r.flow,
                        **{k: v for k, v in unc.items() if k != "amount"},
                    }
                )

            if is_ref:
                for other in ("P1_PKM", "P2_Drying", "P3_Transport", "P4_Handling", "P6_Ash"):
                    if other in set(inv["process"]):
                        exchanges.append(
                            {
                                "input": foreground_key(other, sc.name),
                                "amount": 1.0,
                                "type": "technosphere",
                                "unit": "unit",
                                "name": f"life-cycle stage {other}",
                            }
                        )

            data[key] = {
                "name": f"{process} [{sc.name}]",
                "unit": unit,
                "location": "ID-JAMALI",
                "type": "process",
                "reference product": FUNCTIONAL_UNIT if is_ref else f"stage service {process}",
                "comment": (
                    f"Co-firing {sc.cofiring_pct_energy:g} % of fuel energy; net efficiency "
                    f"{sc.net_efficiency_pct:g} %; truck {sc.truck_km:g} km, barge {sc.barge_km:g} km."
                ),
                "exchanges": exchanges,
            }

    bd.Database(FOREGROUND_DB).write(data)
    return inventories


def build_all(scenarios: list[Scenario], overrides: dict[str, float] | None = None) -> dict:
    set_project()
    write_biosphere()
    write_background()
    inventories = write_foreground(scenarios, overrides)
    return inventories
