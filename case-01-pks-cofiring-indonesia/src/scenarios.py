"""Parametric foreground inventory for any PKS co-firing share.

The inventory is *computed*, not typed in: given a co-firing energy share, a net
plant efficiency and the transport distances, the module returns the full set of
technosphere and elementary exchanges per functional unit. This is what makes the
model usable ex-ante — every scenario is a function call, not a copied file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from config import PARAMS, PKS_SCALING, p
from datasets import read_table

MJ_PER_MWH = 3600.0


@dataclass
class Scenario:
    name: str
    cofiring_pct_energy: float
    truck_km: float
    barge_km: float
    net_efficiency_pct: float
    stage: dict = field(default_factory=dict)


def load_scenarios(path=None) -> list[Scenario]:
    df = read_table("scenarios", path)
    return [
        Scenario(
            name=r.scenario,
            cofiring_pct_energy=float(r.cofiring_pct_energy),
            truck_km=float(r.truck_km),
            barge_km=float(r.barge_km),
            net_efficiency_pct=float(r.net_efficiency_pct),
        )
        for r in df.itertuples()
    ]


def build_inventory(sc: Scenario, overrides: dict[str, float] | None = None) -> pd.DataFrame:
    """Return the per-functional-unit inventory of one scenario.

    Columns: stage, process, flow, kind ('technosphere'|'elementary'),
    direction, amount, unit.
    """
    o = overrides or {}

    def par(name: str) -> float:
        return float(o.get(name, p(name)))

    # ---- energy and fuel masses ------------------------------------------
    fuel_energy_MJ = MJ_PER_MWH / (sc.net_efficiency_pct / 100.0)
    x = sc.cofiring_pct_energy / 100.0
    e_pks_MJ = x * fuel_energy_MJ
    e_coal_MJ = (1.0 - x) * fuel_energy_MJ
    kg_pks = e_pks_MJ / par("lhv_pks_MJ_per_kg")
    kg_coal = e_coal_MJ / par("lhv_coal_MJ_per_kg")
    kg_fuel = kg_pks + kg_coal

    # ---- combustion emissions --------------------------------------------
    co2_fossil = e_coal_MJ / 1000.0 * par("co2_coal_kg_per_GJ")
    co2_biogenic = e_pks_MJ / 1000.0 * par("co2_pks_kg_per_GJ")
    ch4_fossil = e_coal_MJ / 1000.0 * par("ch4_kg_per_GJ")
    ch4_biogenic_comb = e_pks_MJ / 1000.0 * par("ch4_kg_per_GJ")
    n2o = fuel_energy_MJ / 1000.0 * par("n2o_kg_per_GJ")
    nox = (e_coal_MJ + e_pks_MJ * PKS_SCALING["nox"]) / 1000.0 * par("nox_coal_kg_per_GJ")
    so2 = (e_coal_MJ + e_pks_MJ * PKS_SCALING["so2"]) / 1000.0 * par("so2_coal_kg_per_GJ")
    pm25 = (e_coal_MJ + e_pks_MJ * PKS_SCALING["pm25"]) / 1000.0 * par("pm25_coal_kg_per_GJ")

    # ---- ancillary flows tied to fuel composition ------------------------
    s_in = kg_coal * par("s_coal_frac") + kg_pks * par("s_pks_frac")
    ash_in = kg_coal * par("ash_coal_frac") + kg_pks * par("ash_pks_frac")
    limestone = s_in * par("limestone_kg_per_kg_S")
    faba = ash_in * par("ash_capture_frac")
    aux_kWh = kg_fuel * par("aux_kWh_per_kg_fuel")
    water_m3 = fuel_energy_MJ * par("water_m3_per_MJ_fuel")

    rows: list[tuple] = []

    def add(stage, process, flow, kind, direction, amount, unit):
        rows.append((stage, process, flow, kind, direction, float(amount), unit))

    # P1 — PKS upstream (allocated plantation and mill burden)
    add("upstream", "P1_PKM", "PKS upstream, economically allocated", "technosphere", "input",
        kg_pks * par("pks_upstream_kg_per_kg"), "kg")
    add("upstream", "P1_PKM", "Okupasi lahan kebun sawit teralokasi", "elementary", "input",
        kg_pks * par("land_m2a_per_kg"), "m2a")

    # P2 — drying and size reduction
    add("upstream", "P2_Drying", "Drying heat from biomass residue", "technosphere", "input",
        kg_pks * par("drying_heat_MJ_per_kg"), "MJ")
    add("upstream", "P2_Drying", "Crusher electricity", "technosphere", "input",
        kg_pks * par("crusher_kWh_per_kg"), "kWh")
    add("upstream", "P2_Drying", "CH4 biogenik", "elementary", "output",
        kg_pks * par("stockpile_ch4_kg_per_kg"), "kg")

    # P3 — transport to the plant
    add("transport", "P3_Transport", "Truck transport, diesel 24 t", "technosphere", "input",
        kg_pks / 1000.0 * sc.truck_km, "t.km")
    add("transport", "P3_Transport", "Barge transport, 3000 DWT", "technosphere", "input",
        kg_pks / 1000.0 * sc.barge_km, "t.km")

    # P4 — on-site handling
    add("core", "P4_Handling", "Conveyor and coal mill electricity", "technosphere", "input",
        aux_kWh, "kWh")

    # P5 — combustion and power generation
    add("core", "P5_Generation", "Sub-bituminous coal, 4200 kcal GAR", "technosphere", "input", kg_coal, "kg")
    add("core", "P5_Generation", "FGD limestone", "technosphere", "input", limestone, "kg")
    add("core", "P5_Generation", "Process and make-up water", "technosphere", "input", water_m3, "m3")
    add("core", "P5_Generation", "Air proses & make-up", "elementary", "input", water_m3, "m3")
    add("core", "P5_Generation", "CO2 fosil", "elementary", "output", co2_fossil, "kg")
    add("core", "P5_Generation", "CO2 biogenik", "elementary", "output", co2_biogenic, "kg")
    add("core", "P5_Generation", "CH4 fosil", "elementary", "output", ch4_fossil, "kg")
    add("core", "P5_Generation", "CH4 biogenik", "elementary", "output", ch4_biogenic_comb, "kg")
    add("core", "P5_Generation", "N2O", "elementary", "output", n2o, "kg")
    add("core", "P5_Generation", "NOx", "elementary", "output", nox, "kg")
    add("core", "P5_Generation", "SO2", "elementary", "output", so2, "kg")
    add("core", "P5_Generation", "PM2.5", "elementary", "output", pm25, "kg")

    # P6 — ash management
    add("downstream", "P6_Ash", "Controlled FABA landfilling", "technosphere", "input", faba, "kg")

    inv = pd.DataFrame(rows, columns=["stage", "process", "flow", "kind", "direction", "amount", "unit"])
    inv["scenario"] = sc.name
    return inv


def fuel_summary(sc: Scenario) -> dict[str, float]:
    fuel_energy_MJ = MJ_PER_MWH / (sc.net_efficiency_pct / 100.0)
    x = sc.cofiring_pct_energy / 100.0
    return {
        "fuel_energy_MJ_per_MWh": fuel_energy_MJ,
        "kg_coal_per_MWh": (1 - x) * fuel_energy_MJ / p("lhv_coal_MJ_per_kg"),
        "kg_pks_per_MWh": x * fuel_energy_MJ / p("lhv_pks_MJ_per_kg"),
    }


PARAMETER_TABLE = pd.DataFrame(
    [{"parameter": k, "value": v["value"], "source": v["source"]} for k, v in PARAMS.items()]
)
