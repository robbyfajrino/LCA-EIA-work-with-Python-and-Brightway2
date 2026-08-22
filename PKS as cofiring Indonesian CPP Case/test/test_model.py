"""Regression tests: the guards that make continuous integration meaningful.

Run with `pytest` from the repository root; conftest.py puts src/ on sys.path.
"""

from __future__ import annotations

import numpy as np
import pytest

from analysis import GWP, cross_validate, monte_carlo, score, surrogate_score
from build_project import build_all, load_background_table
from config import (
    DEFAULT_ELECTRICITY_MODE,
    ELECTRICITY_BACKGROUND_KEY,
    ELECTRICITY_MODES,
    set_electricity_mode,
)
from methods import write_methods
from scenarios import build_inventory, load_scenarios

MJ_PER_MWH = 3600.0


@pytest.fixture(scope="module")
def project():
    set_electricity_mode(DEFAULT_ELECTRICITY_MODE)
    scenarios = load_scenarios()
    build_all(scenarios)
    write_methods()
    return scenarios


# --- inventory logic -------------------------------------------------------- #
def test_energy_balance_closes():
    sc = [s for s in load_scenarios() if s.cofiring_pct_energy == 30][0]
    inv = build_inventory(sc)
    coal = inv.loc[inv["flow"].str.startswith("Sub-bituminous"), "amount"].iloc[0]
    pks = inv.loc[inv["flow"].str.startswith("PKS upstream"), "amount"].iloc[0]
    from config import p

    energy = coal * p("lhv_coal_MJ_per_kg") + pks * p("lhv_pks_MJ_per_kg")
    assert energy == pytest.approx(MJ_PER_MWH / (sc.net_efficiency_pct / 100.0), rel=1e-9)


def test_baseline_has_no_biogenic_co2():
    sc = [s for s in load_scenarios() if s.cofiring_pct_energy == 0][0]
    inv = build_inventory(sc)
    bio = inv.loc[inv["flow"] == "CO2 biogenik", "amount"].iloc[0]
    assert bio == pytest.approx(0.0)


# --- Brightway vs independent implementation -------------------------------- #
def test_cross_validation(project):
    df = cross_validate(project)
    assert df["rel_diff"].max() < 1e-5


def test_fossil_gwp_decreases_with_cofiring(project):
    scores = [score(s.name) for s in project]
    assert all(b < a for a, b in zip(scores, scores[1:]))


# --- uncertainty ------------------------------------------------------------ #
def test_monte_carlo_is_dispersed_and_centred(project):
    samples = monte_carlo("baseline_0pct", iterations=50)
    assert len(samples) == 50
    assert np.all(samples > 0)
    assert 0.02 < samples.std(ddof=1) / samples.mean() < 1.0
    assert samples.mean() == pytest.approx(score("baseline_0pct"), rel=0.5)


# --- switchable electricity model ------------------------------------------- #
@pytest.mark.parametrize("mode", list(ELECTRICITY_MODES))
def test_electricity_mode_applied_to_background(mode):
    bg = load_background_table(mode=mode).set_index("background_key")
    assert bg.loc[ELECTRICITY_BACKGROUND_KEY, "kg_CO2eq_per_unit"] == pytest.approx(
        ELECTRICITY_MODES[mode]["gwp_kg_per_kWh"]
    )


def test_marginal_electricity_raises_score():
    sc = [s for s in load_scenarios() if s.cofiring_pct_energy == 30][0]
    set_electricity_mode("average_time_of_use")
    average = surrogate_score(sc)
    set_electricity_mode("marginal_time_of_use")
    marginal = surrogate_score(sc)
    set_electricity_mode("marginal_decarbonising_2040")
    clean = surrogate_score(sc)
    set_electricity_mode(DEFAULT_ELECTRICITY_MODE)
    assert clean < average < marginal


def test_unknown_electricity_mode_rejected():
    with pytest.raises(KeyError):
        set_electricity_mode("no_such_mode")
