"""Project-wide configuration: paths, naming, and the parameter set of the
PKS co-firing model.

Every number that a reviewer could challenge lives here, in one place, with a
source note. Nothing is hard-coded inside the calculation code.
"""

from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
SRC_DIR = Path(__file__).resolve().parent
REPO_DIR = SRC_DIR.parent
DATA_DIR = REPO_DIR / "data"
OUTPUT_DIR = REPO_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# --------------------------------------------------------------------------- #
# Brightway naming
# --------------------------------------------------------------------------- #
PROJECT_NAME = "pks-cofiring-lca"
BIOSPHERE_DB = "pks-biosphere"
BACKGROUND_DB = "pks-background-proxy"
FOREGROUND_DB = "pks-foreground"

METHOD_FAMILY = ("ReCiPe 2016 v1.03 (proxy)", "midpoint (H)")

# --------------------------------------------------------------------------- #
# Goal and scope (ISO 14040/14044, ISO 14067)
# --------------------------------------------------------------------------- #
FUNCTIONAL_UNIT = "1 MWh net electricity delivered to the Java-Bali grid"
REFERENCE_FLOW_AMOUNT = 1.0
REFERENCE_FLOW_UNIT = "MWh"
SYSTEM_BOUNDARY = (
    "Cradle-to-grave for the fuel supply and conversion service: allocated palm "
    "kernel shell (PKS) upstream burden, drying and size reduction, transport "
    "(truck and barge), on-site handling, boiler combustion in a 300 MW "
    "sub-critical PLTU unit, FGD reagent supply, process water, and controlled "
    "ash (FABA) landfilling. Plant construction and decommissioning are excluded "
    "(cut-off), consistent with the original ISO 14067 study."
)

# --------------------------------------------------------------------------- #
# Engineering parameters
#
# LHV and fuel composition: mean of data/fuel_quality_lab_results.csv
# (ASTM D5865 / D3174 / D4239, 40 samples, 2025).
# Combustion emission factors: IPCC 2006 Vol. 2 defaults.
# Unit-specific factors (NOx, SO2, PM, ash capture, auxiliaries) are calibrated
# against the 2025 CEMS record and the operating log of Unit #2 so that the 0 %
# co-firing case reproduces the measured baseline inventory.
# --------------------------------------------------------------------------- #
PARAMS: dict[str, dict] = {
    # fuel properties -------------------------------------------------------
    "lhv_coal_MJ_per_kg": dict(value=18.626, source="lab mean, sub-bituminous 4200 kcal GAR"),
    "lhv_pks_MJ_per_kg": dict(value=17.035, source="lab mean, PKS as received"),
    "ash_coal_frac": dict(value=0.055295, source="lab mean, dry basis"),
    "ash_pks_frac": dict(value=0.030115, source="lab mean, dry basis"),
    "s_coal_frac": dict(value=0.0040965, source="lab mean, dry basis"),
    "s_pks_frac": dict(value=0.00048850, source="lab mean, dry basis"),
    "n_coal_frac": dict(value=0.0095485, source="lab mean, dry basis"),
    "n_pks_frac": dict(value=0.0040590, source="lab mean, dry basis"),
    # combustion emission factors ------------------------------------------
    "co2_coal_kg_per_GJ": dict(value=94.6, source="IPCC 2006, sub-bituminous coal"),
    "co2_pks_kg_per_GJ": dict(value=110.0, source="IPCC 2006, other primary solid biomass (biogenic)"),
    "ch4_kg_per_GJ": dict(value=0.001, source="IPCC 2006, 1 g CH4/GJ"),
    "n2o_kg_per_GJ": dict(value=0.0015, source="IPCC 2006, 1.5 g N2O/GJ"),
    # unit-calibrated factors ----------------------------------------------
    "nox_coal_kg_per_GJ": dict(value=0.14850, source="CEMS Unit #2 annual mean 2025"),
    "so2_coal_kg_per_GJ": dict(value=0.19708, source="CEMS + 90 % FGD removal"),
    "pm25_coal_kg_per_GJ": dict(value=0.008067, source="annual stack test, ESP 99.5 %"),
    "ash_capture_frac": dict(value=0.905, source="ash balance, B3 landfill weighbridge"),
    "limestone_kg_per_kg_S": dict(value=1.407, source="FGD reagent store issue records"),
    "aux_kWh_per_kg_fuel": dict(value=0.012040, source="own-use log, conveyor and coal mill"),
    "water_m3_per_MJ_fuel": dict(value=0.00016500, source="WTP water balance"),
    # PKS supply chain intensities ------------------------------------------
    "pks_upstream_kg_per_kg": dict(value=1.0, source="economic allocation 3.1 % embedded in background dataset"),
    "drying_heat_MJ_per_kg": dict(value=0.85, source="dryer energy balance"),
    "crusher_kWh_per_kg": dict(value=0.01808, source="crusher nameplate 75 kW and throughput log"),
    "stockpile_ch4_kg_per_kg": dict(value=0.00021973, source="biomass storage literature"),
    "land_m2a_per_kg": dict(value=0.42, source="3.8 t CPO/ha/yr productivity, allocated"),
}

# PKS-specific emission factors are derived from the coal factors by the ratio of
# the responsible fuel property (fuel-bound nitrogen, sulphur, ash). This keeps a
# single calibrated unit and makes the assumption explicit and testable.
PKS_SCALING = {
    "nox": PARAMS["n_pks_frac"]["value"] / PARAMS["n_coal_frac"]["value"],
    "so2": PARAMS["s_pks_frac"]["value"] / PARAMS["s_coal_frac"]["value"],
    "pm25": PARAMS["ash_pks_frac"]["value"] / PARAMS["ash_coal_frac"]["value"],
}


def p(name: str) -> float:
    """Return the numeric value of a named parameter."""
    return float(PARAMS[name]["value"])


# --------------------------------------------------------------------------- #
# Flow name mapping: foreground exchange -> background activity key
# --------------------------------------------------------------------------- #
TECHNOSPHERE_MAP = {
    "PKS upstream, economically allocated": "pks_upstream_econ",
    "Drying heat from biomass residue": "drying_heat_biomass",
    "Crusher electricity": "electricity_grid_jamali",
    "Truck transport, diesel 24 t": "truck_transport",
    "Barge transport, 3000 DWT": "barge_transport",
    "Conveyor and coal mill electricity": "electricity_grid_jamali",
    "Sub-bituminous coal, 4200 kcal GAR": "coal_sub_bituminous",
    "FGD limestone": "lime_fgd",
    "Process and make-up water": "water_process",
    "Controlled FABA landfilling": "ash_landfill",
}

# Aggregated background indicator flows. The proxy background table in
# data/background_factors_ecoinvent_proxy.csv is already characterised, so each
# background activity emits one aggregated flow per impact category with a
# characterisation factor of 1. Replacing the proxy table with a licensed
# ecoinvent database removes these flows entirely (see README, Limitations).
AGGREGATED_BACKGROUND_FLOWS = {
    "kg_CO2eq_per_unit": ("Aggregated background burden, GWP100", "GWP100 (climate change)", "kg CO2-eq"),
    "kg_SO2eq_per_unit": ("Aggregated background burden, acidification", "Terrestrial acidification", "kg SO2-eq"),
    "kg_NOxeq_per_unit": ("Aggregated background burden, ozone formation", "Photochemical ozone formation", "kg NOx-eq"),
    "kg_Peq_per_unit": ("Aggregated background burden, eutrophication", "Freshwater eutrophication", "kg P-eq"),
    "kg_PM25eq_per_unit": ("Aggregated background burden, particulate matter", "Fine particulate matter formation", "kg PM2.5-eq"),
}

# Elementary flow names used by the foreground, matched to the CF table.
BIOSPHERE_FLOWS = {
    "CO2 fosil": ("air", "kg"),
    "CO2 biogenik": ("air", "kg"),
    "CH4 fosil": ("air", "kg"),
    "CH4 biogenik": ("air", "kg"),
    "N2O": ("air", "kg"),
    "NOx": ("air", "kg"),
    "SO2": ("air", "kg"),
    "PM2.5": ("air", "kg"),
    "Okupasi lahan kebun sawit teralokasi": ("raw", "m2a"),
    "Air proses & make-up": ("raw", "m3"),
}

# --------------------------------------------------------------------------- #
# Marginal electricity model (switchable)
#
# The Java-Bali grid factor used for auxiliary and crusher electricity is a
# *modelling choice*, not a measurement. Ex-ante practice distinguishes:
#
#   * attributional average  - the average grid factor of the accounting year
#   * marginal, time-of-use  - the technology that actually responds to the
#     additional demand in the year the plant is operated (consequential)
#   * marginal, time-of-construction - the grid as it stood when the co-firing
#     retrofit was built, i.e. the decision-relevant background of the investment
#
# Each mode replaces the electricity row of the proxy background table. Non-GWP
# columns are scaled by the mode's `co_scale` (combustion-related burdens move
# with the fossil share) so acidification and PM stay internally consistent.
# --------------------------------------------------------------------------- #
ELECTRICITY_MODES: dict[str, dict] = {
    "average_time_of_use": dict(
        label="Attributional grid average (time of use, 2025)",
        gwp_kg_per_kWh=0.794,
        co_scale=1.00,
        source="KESDM Jamali grid emission factor 2025",
    ),
    "marginal_time_of_use": dict(
        label="Marginal supplier, time of use (2025-2035 operation)",
        gwp_kg_per_kWh=0.902,
        co_scale=1.12,
        source="Coal condensing units set the dispatch margin in RUPTL 2021-2030 base case",
    ),
    "marginal_time_of_construction": dict(
        label="Marginal supplier, time of construction (2024 retrofit)",
        gwp_kg_per_kWh=0.861,
        co_scale=1.07,
        source="Build-year marginal mix, coal-dominated with gas peaking",
    ),
    "marginal_decarbonising_2040": dict(
        label="Marginal supplier under a decarbonising grid (2040 horizon)",
        gwp_kg_per_kWh=0.412,
        co_scale=0.55,
        source="Illustrative IAM-consistent pathway; stand-in for a premise background",
    ),
}

DEFAULT_ELECTRICITY_MODE = "average_time_of_use"
_ELECTRICITY_MODE = DEFAULT_ELECTRICITY_MODE

ELECTRICITY_BACKGROUND_KEY = "electricity_grid_jamali"


def set_electricity_mode(mode: str) -> str:
    """Select the electricity background model used by every later calculation."""
    global _ELECTRICITY_MODE
    if mode not in ELECTRICITY_MODES:
        raise KeyError(f"unknown electricity mode {mode!r}; choose from {list(ELECTRICITY_MODES)}")
    _ELECTRICITY_MODE = mode
    return mode


def electricity_mode() -> str:
    return _ELECTRICITY_MODE


def electricity_mode_spec(mode: str | None = None) -> dict:
    return ELECTRICITY_MODES[mode or _ELECTRICITY_MODE]


# Parameters carried through the local and global sensitivity analyses.
SENSITIVITY_PARAMETERS = [
    "lhv_pks_MJ_per_kg",
    "lhv_coal_MJ_per_kg",
    "co2_coal_kg_per_GJ",
    "co2_pks_kg_per_GJ",
    "drying_heat_MJ_per_kg",
    "crusher_kWh_per_kg",
    "aux_kWh_per_kg_fuel",
    "stockpile_ch4_kg_per_kg",
]
