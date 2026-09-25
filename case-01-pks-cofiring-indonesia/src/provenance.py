"""Provenance record: what data, what parameters, what mapping, what code.

An LCA result without provenance is an opinion. Every run writes a JSON (and a
flat CSV) that pins down the exact inputs: SHA-256 of every dataset file, the
frozen parameter set with its source notes, the Brightway mapping, package
versions, the electricity-background model, the RNG seed and iteration count, and
the git commit with a dirty flag. Re-running after any data edit changes the
hash, so two results can never be silently confused.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pandas as pd

from config import (
    AGGREGATED_BACKGROUND_FLOWS,
    BACKGROUND_DB,
    BIOSPHERE_DB,
    BIOSPHERE_FLOWS,
    FOREGROUND_DB,
    FUNCTIONAL_UNIT,
    METHOD_FAMILY,
    PARAMS,
    PKS_SCALING,
    PROJECT_NAME,
    REPO_DIR,
    SYSTEM_BOUNDARY,
    TECHNOSPHERE_MAP,
    electricity_mode_spec,
)
from datasets import TABLES, model_tables, source_description, table_path

TRACKED_PACKAGES = [
    "bw2data",
    "bw2calc",
    "bw2io",
    "stats_arrays",
    "numpy",
    "pandas",
    "matplotlib",
    "SALib",
    "plotly",
]

# Code files whose content changes the numbers.
TRACKED_SOURCES = [
    "src/config.py",
    "src/scenarios.py",
    "src/build_project.py",
    "src/methods.py",
    "src/pedigree.py",
    "src/analysis.py",
    "src/datasets.py",
]


def file_fingerprint(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {"path": str(path), "exists": False}
    raw = path.read_bytes()
    return {
        "path": str(path),
        "exists": True,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "modified_utc": _dt.datetime.fromtimestamp(
            path.stat().st_mtime, _dt.timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S"),
    }


def dataset_fingerprints() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for table in model_tables():
        path = table_path(table)
        fp = file_fingerprint(path)
        fp["default_file"] = TABLES[table]
        try:
            from datasets import read_table

            df = read_table(table)
            fp["rows"] = int(len(df))
            fp["columns"] = list(map(str, df.columns))
        except Exception as exc:  # noqa: BLE001 - provenance must never break a run
            fp["read_error"] = str(exc)
        out[table] = fp
    return out


def dataset_digest(fingerprints: dict[str, dict] | None = None) -> str:
    """One short hash standing for the whole input dataset."""
    fps = fingerprints or dataset_fingerprints()
    joined = "|".join(f"{k}:{v.get('sha256', 'missing')}" for k, v in sorted(fps.items()))
    return hashlib.sha256(joined.encode()).hexdigest()[:12]


def git_state() -> dict:
    def run(*args: str) -> str | None:
        try:
            return subprocess.run(
                args, cwd=REPO_DIR, capture_output=True, text=True, timeout=10, check=True
            ).stdout.strip()
        except Exception:  # noqa: BLE001 - a tarball download has no git
            return None

    commit = run("git", "rev-parse", "HEAD")
    status = run("git", "status", "--porcelain")
    return {
        "commit": commit,
        "short_commit": commit[:8] if commit else None,
        "branch": run("git", "rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status) if status is not None else None,
    }


def package_versions() -> dict[str, str]:
    out = {}
    for name in TRACKED_PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "not installed"
    return out


def record(
    mode: str,
    iterations: int,
    seed: int = 42,
    sobol_n: int | None = None,
    extra: dict | None = None,
) -> dict:
    fps = dataset_fingerprints()
    rec = {
        "run": {
            "timestamp_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "functional_unit": FUNCTIONAL_UNIT,
            "system_boundary": SYSTEM_BOUNDARY,
            "monte_carlo_iterations": iterations,
            "monte_carlo_seed": seed,
            "sobol_base_samples": sobol_n,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "code": {
            "git": git_state(),
            "packages": package_versions(),
            "sources": {f: file_fingerprint(REPO_DIR / f) for f in TRACKED_SOURCES},
        },
        "data": {
            "source": source_description(),
            "digest": dataset_digest(fps),
            "tables": fps,
        },
        "electricity_model": {"mode": mode, **electricity_mode_spec(mode)},
        "parameters": {k: {"value": v["value"], "source": v["source"]} for k, v in PARAMS.items()},
        "derived_pks_scaling": dict(PKS_SCALING),
        "brightway_mapping": {
            "project": PROJECT_NAME,
            "databases": {
                "biosphere": BIOSPHERE_DB,
                "background": BACKGROUND_DB,
                "foreground": FOREGROUND_DB,
            },
            "method_family": list(METHOD_FAMILY),
            "technosphere_map": dict(TECHNOSPHERE_MAP),
            "aggregated_background_flows": {
                col: {"flow": flow, "impact_category": cat, "unit": unit}
                for col, (flow, cat, unit) in AGGREGATED_BACKGROUND_FLOWS.items()
            },
            "biosphere_flows": {
                name: {"compartment": comp, "unit": unit}
                for name, (comp, unit) in BIOSPHERE_FLOWS.items()
            },
        },
    }
    if extra:
        rec["extra"] = extra
    return rec


def flatten(rec: dict) -> pd.DataFrame:
    """Long-format view of the record: one row per (section, key, value)."""
    rows: list[dict] = []

    def walk(prefix: str, obj) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(f"{prefix}.{k}" if prefix else str(k), v)
        elif isinstance(obj, (list, tuple)):
            rows.append({"key": prefix, "value": ", ".join(map(str, obj))})
        else:
            rows.append({"key": prefix, "value": obj})

    walk("", rec)
    return pd.DataFrame(rows)


def write(rec: dict, output_dir) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "provenance.json"
    json_path.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
    flatten(rec).to_csv(out / "provenance.csv", index=False)
    return json_path


def summary_table(rec: dict) -> pd.DataFrame:
    """Compact reviewer-facing table for the report."""
    git = rec["code"]["git"]
    return pd.DataFrame(
        [
            ("Run timestamp (UTC)", rec["run"]["timestamp_utc"]),
            ("Dataset source", rec["data"]["source"]),
            ("Dataset digest", rec["data"]["digest"]),
            ("Electricity mode", rec["electricity_model"]["mode"]),
            ("Monte Carlo iterations", rec["run"]["monte_carlo_iterations"]),
            ("Monte Carlo seed", rec["run"]["monte_carlo_seed"]),
            ("Sobol base samples", rec["run"]["sobol_base_samples"]),
            ("Git commit", f"{git.get('short_commit')} ({'dirty' if git.get('dirty') else 'clean'})"),
            ("Python", rec["run"]["python"]),
            ("brightway (bw2data / bw2calc)", f"{rec['code']['packages']['bw2data']} / {rec['code']['packages']['bw2calc']}"),
        ],
        columns=["item", "value"],
    ).set_index("item")


def dataset_table(rec: dict) -> pd.DataFrame:
    rows = []
    for table, fp in rec["data"]["tables"].items():
        rows.append(
            {
                "table": table,
                "file": Path(fp["path"]).name,
                "rows": fp.get("rows"),
                "bytes": fp.get("bytes"),
                "modified (UTC)": fp.get("modified_utc"),
                "sha256 (first 16)": str(fp.get("sha256", ""))[:16],
            }
        )
    return pd.DataFrame(rows)


def mapping_table(rec: dict) -> pd.DataFrame:
    m = rec["brightway_mapping"]["technosphere_map"]
    return pd.DataFrame({"foreground exchange": list(m), "background activity key": list(m.values())})
