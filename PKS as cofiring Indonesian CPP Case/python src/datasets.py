"""Single resolver for every input table the model reads.

Why this module exists: an ex-ante LCA is only useful if the *data* can be
swapped without touching the model. Every read goes through `read_table()`, so a
different plant, a different lab batch or a different background table is a
matter of pointing an environment variable at another folder or workbook.

Resolution order (first hit wins):

1. `PKS_DATA_XLSX=/path/book.xlsx`  - one Excel workbook, one sheet per table
2. `PKS_DATA_DIR=/path/mydata`      - a folder of CSV files
3. the repository's own `data/` folder (the shipped dummy dataset)

Sheet names in the Excel path use the short aliases in `SHEETS` because Excel
caps a sheet name at 31 characters.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from config import DATA_DIR

# canonical table name -> default CSV file name (without extension)
TABLES = {
    "scenarios": "scenarios",
    "fuel_quality": "fuel_quality_lab_results",
    "background": "background_factors_ecoinvent_proxy",
    "characterization": "recipe2016_characterization_factors",
    "inventory": "inventory_pks_cofiring",
    "operation_log": "pltu_daily_operation_log_2025",
    "cems": "cems_monthly_stack_emissions_2025",
    "logistics": "pks_delivery_logistics_log",
}

# Excel sheet name per table (<= 31 chars, Excel's hard limit)
SHEETS = {name: name for name in TABLES}

# Columns each table must provide for the model to run. Extra columns are kept
# and ignored, so a richer field sheet can be dropped in unchanged.
REQUIRED_COLUMNS = {
    "scenarios": ["scenario", "cofiring_pct_energy", "truck_km", "barge_km", "net_efficiency_pct"],
    "background": [
        "background_key",
        "activity_name",
        "reference_unit",
        "kg_CO2eq_per_unit",
        "kg_SO2eq_per_unit",
        "kg_NOxeq_per_unit",
        "kg_Peq_per_unit",
        "kg_PM25eq_per_unit",
        "database_source",
    ],
    "characterization": ["flow_name", "compartment", "impact_category", "cf_midpoint", "cf_unit"],
    "inventory": [
        "process_id",
        "stage",
        "flow_name",
        "flow_type",
        "direction",
        "amount_per_MWh",
        "unit",
        "ped_reliability",
        "ped_completeness",
        "ped_temporal",
        "ped_geographical",
        "ped_technological",
    ],
    "fuel_quality": ["fuel_type", "ash_pct_db", "sulphur_pct_db", "nitrogen_pct_db", "LHV_MJ_per_kg"],
}

# Columns that must never be negative (a sign error here silently poisons a run).
NON_NEGATIVE = {
    "scenarios": ["cofiring_pct_energy", "truck_km", "barge_km", "net_efficiency_pct"],
    "background": ["kg_CO2eq_per_unit", "kg_SO2eq_per_unit", "kg_NOxeq_per_unit", "kg_Peq_per_unit", "kg_PM25eq_per_unit"],
    "fuel_quality": ["ash_pct_db", "sulphur_pct_db", "nitrogen_pct_db", "LHV_MJ_per_kg"],
}


def data_dir() -> Path:
    """The folder CSV tables are read from."""
    override = os.environ.get("PKS_DATA_DIR")
    return Path(override).expanduser().resolve() if override else DATA_DIR


def workbook_path() -> Path | None:
    """The Excel workbook tables are read from, if one is configured."""
    override = os.environ.get("PKS_DATA_XLSX")
    return Path(override).expanduser().resolve() if override else None


def table_path(table: str) -> Path:
    """Where `table` will actually be read from (the workbook, or a CSV file)."""
    wb = workbook_path()
    if wb is not None:
        return wb
    return data_dir() / f"{TABLES[table]}.csv"


def source_description() -> str:
    wb = workbook_path()
    if wb is not None:
        return f"Excel workbook {wb}"
    return f"CSV folder {data_dir()}"


def read_table(table: str, path=None) -> pd.DataFrame:
    """Read one canonical table as a DataFrame.

    `path` still wins over the environment, so callers (and tests) can pass an
    explicit file the way they always could.
    """
    if table not in TABLES:
        raise KeyError(f"unknown table {table!r}; known tables: {sorted(TABLES)}")
    if path is not None:
        path = Path(path)
        if path.suffix.lower() in (".xlsx", ".xlsm"):
            return pd.read_excel(path, sheet_name=SHEETS[table])
        return pd.read_csv(path)

    wb = workbook_path()
    if wb is not None:
        if not wb.exists():
            raise FileNotFoundError(f"PKS_DATA_XLSX points at a missing file: {wb}")
        return pd.read_excel(wb, sheet_name=SHEETS[table])

    csv = data_dir() / f"{TABLES[table]}.csv"
    if not csv.exists():
        raise FileNotFoundError(
            f"table {table!r} not found at {csv}. Either add the file or set "
            "PKS_DATA_DIR / PKS_DATA_XLSX (see README, 'Bring your own data')."
        )
    return pd.read_csv(csv)


def model_tables() -> list[str]:
    """Tables the calculation actually consumes (provenance covers these)."""
    return ["scenarios", "background", "characterization", "inventory", "fuel_quality"]


def export_workbook(target, tables: list[str] | None = None):
    """Write the currently resolved tables into one Excel workbook.

    Handy starting point for a data swap: export, edit in Excel, then point
    `PKS_DATA_XLSX` at the edited file.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    names = tables or model_tables()
    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        for name in names:
            read_table(name).to_excel(writer, sheet_name=SHEETS[name], index=False)
    return target


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "export":
        out = sys.argv[2] if len(sys.argv) > 2 else "my_dataset.xlsx"
        print(f"workbook written: {export_workbook(out)}")
    else:
        print(f"source: {source_description()}")
        for t in model_tables():
            df = read_table(t)
            print(f"  {t:<18} {len(df):>5} rows  {table_path(t)}")
