"""Validate a swapped-in dataset before spending a Brightway run on it.

    python src/data_check.py

Exits non-zero with a readable list of problems, so a bad swap fails with
"column `truck_km` is missing from scenarios" instead of a NaN score ten minutes
later. Run it in CI, run it after every edit to your own data.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from config import AGGREGATED_BACKGROUND_FLOWS, BIOSPHERE_FLOWS, TECHNOSPHERE_MAP
from datasets import (
    NON_NEGATIVE,
    REQUIRED_COLUMNS,
    model_tables,
    read_table,
    source_description,
    table_path,
)
from methods import CF_ALIASES


def check() -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors make a run meaningless; warnings do not."""
    errors: list[str] = []
    warnings: list[str] = []
    tables: dict[str, pd.DataFrame] = {}

    for name in model_tables():
        try:
            tables[name] = read_table(name)
        except Exception as exc:  # noqa: BLE001 - report, do not raise
            errors.append(f"{name}: cannot be read ({exc})")
            continue

    for name, df in tables.items():
        if df.empty:
            errors.append(f"{name}: table is empty ({table_path(name)})")
        missing = [c for c in REQUIRED_COLUMNS.get(name, []) if c not in df.columns]
        if missing:
            errors.append(f"{name}: missing required column(s) {', '.join(missing)}")
        for col in NON_NEGATIVE.get(name, []):
            if col in df.columns:
                numeric = pd.to_numeric(df[col], errors="coerce")
                if numeric.isna().any():
                    errors.append(f"{name}.{col}: contains non-numeric or empty values")
                elif (numeric < 0).any():
                    errors.append(f"{name}.{col}: contains negative values")

    # --- scenarios ---------------------------------------------------------- #
    sc = tables.get("scenarios")
    if sc is not None and "scenario" in sc.columns:
        if sc["scenario"].duplicated().any():
            errors.append("scenarios: duplicate scenario names")
        if "baseline_0pct" not in set(sc["scenario"]):
            warnings.append(
                "scenarios: no row named 'baseline_0pct'; the comparison "
                "P(better than baseline) needs a baseline scenario"
            )
        if "cofiring_pct_energy" in sc.columns and (sc["cofiring_pct_energy"] > 100).any():
            errors.append("scenarios.cofiring_pct_energy: value above 100 %")
        if "net_efficiency_pct" in sc.columns:
            eff = pd.to_numeric(sc["net_efficiency_pct"], errors="coerce")
            if ((eff <= 0) | (eff > 60)).any():
                errors.append("scenarios.net_efficiency_pct: outside the plausible 0-60 % range")

    # --- background: every mapped activity must exist ----------------------- #
    bg = tables.get("background")
    if bg is not None and "background_key" in bg.columns:
        keys = set(bg["background_key"])
        for flow, key in TECHNOSPHERE_MAP.items():
            if key not in keys:
                errors.append(
                    f"background: no row with background_key '{key}' for the "
                    f"foreground exchange '{flow}' (see config.TECHNOSPHERE_MAP)"
                )
        if bg["background_key"].duplicated().any():
            errors.append("background: duplicate background_key rows")

    # --- characterisation factors ------------------------------------------ #
    cfs = tables.get("characterization")
    if cfs is not None and {"flow_name", "impact_category", "cf_midpoint"} <= set(cfs.columns):
        aliased = {CF_ALIASES.get(n, n) for n in cfs["flow_name"]}
        for flow in BIOSPHERE_FLOWS:
            if flow not in aliased:
                warnings.append(f"characterization: no CF for elementary flow '{flow}' (it will score 0)")
        cats = set(cfs["impact_category"])
        for _, (_flow, category, _unit) in AGGREGATED_BACKGROUND_FLOWS.items():
            if category not in cats:
                warnings.append(
                    f"characterization: impact category '{category}' has no foreground CFs; "
                    "only the aggregated background will contribute"
                )
        if not np.isfinite(pd.to_numeric(cfs["cf_midpoint"], errors="coerce")).all():
            errors.append("characterization.cf_midpoint: non-numeric or infinite values")

    # --- inventory pedigree scores ----------------------------------------- #
    inv = tables.get("inventory")
    if inv is not None:
        for col in [c for c in inv.columns if c.startswith("ped_")]:
            s = pd.to_numeric(inv[col], errors="coerce")
            if s.isna().any() or ((s < 1) | (s > 5)).any():
                errors.append(f"inventory.{col}: pedigree scores must be integers 1-5")

    # --- fuel quality ------------------------------------------------------ #
    fq = tables.get("fuel_quality")
    if fq is not None and {"fuel_type", "LHV_MJ_per_kg"} <= set(fq.columns):
        types = {str(t).strip().upper() for t in fq["fuel_type"]}
        # "Batubara" is the Indonesian label used by the plant's own lab sheet
        for expected in (("PKS",), ("COAL", "BATUBARA")):
            if not any(alias in t for t in types for alias in expected):
                warnings.append(
                    f"fuel_quality: no sample with fuel_type containing {' or '.join(expected)}"
                )
        lhv = pd.to_numeric(fq["LHV_MJ_per_kg"], errors="coerce")
        if ((lhv < 5) | (lhv > 40)).any():
            warnings.append("fuel_quality.LHV_MJ_per_kg: values outside 5-40 MJ/kg — check the units")

    return errors, warnings


def main() -> int:
    print(f"Validating dataset — source: {source_description()}\n")
    errors, warnings = check()
    for w in warnings:
        print(f"  WARNING  {w}")
    for e in errors:
        print(f"  ERROR    {e}")
    if not errors and not warnings:
        print("  all tables present, all required columns found, all values in range.")
    print(
        f"\n{len(errors)} error(s), {len(warnings)} warning(s). "
        + ("Dataset is NOT usable as-is." if errors else "Dataset is usable.")
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
