# -*- coding: utf-8 -*-
"""TDD RED for WA.5 — energy==fuel*LHV*n_thermal/1000 within 1e-9 (mech kJ)."""
from __future__ import annotations

import pathlib

import numpy as np


def test_energy_consistent_with_fuel_mech_kJ() -> None:
    """WA.5: energy (mech kJ) must equal fuel*LHV*n_thermal/1000 within 1e-9."""
    from openlapexe.solver import simulate_full
    from openlapexe.vehicle import Vehicle47

    veh = Vehicle47.from_json("f1")
    fuel_LHV = float(getattr(veh, "fuel_LHV"))
    n_thermal = float(getattr(veh, "n_thermal"))
    res = simulate_full("f1", "spa", 50)
    fuel = np.asarray(res.fuel, dtype=float)
    energy = np.asarray(res.energy, dtype=float)
    # MATLAB:OpenLAP.m:503 fuel_cons, 519 energy_spent_fuel, 520 energy_spent_mech
    # mech kJ spec: energy_spent_mech = fuel_cons * fuel_LHV * n_thermal /1000
    expected = fuel * fuel_LHV * n_thermal / 1000.0  # MATLAB:OpenLAP.m:520
    # Check all points within 1e-9 (currently factor mismatch FAIL on some branch)
    max_err = float(np.max(np.abs(energy - expected))) if expected.size else 0.0
    assert max_err < 1e-9, f"energy != fuel*LHV*n_thermal/1000 max_err {max_err} (WA.5 factor mismatch)"
    # monotonic and non-negative
    assert np.all(energy >= -1e-12)
    assert np.all(fuel >= -1e-12)
    # Check source unification: fuel vs energy branch should both use n_thermal factor
    src = pathlib.Path("src/openlapexe/solver.py").read_text(encoding="utf-8")
    # ds <=1e-12 branch currently missing n_thermal -> should be fixed to include n_thermal
    # Count occurrences of energy_arr[i] = cum_fuel * fuel_LHV
    # After fix both lines contain * n_thermal
    assert src.count("cum_fuel * fuel_LHV * n_thermal / 1000.0") >= 2 or (
        "cum_fuel * fuel_LHV / 1000.0" not in src and "n_thermal" in src
    ), "WA.5 not unified: energy branch still uses fuel_LHV without n_thermal"
    # Ensure comment mentions MATLAB refs for mech
    assert "520" in src or "mech" in src.lower(), "WA.5 should comment MATLAB 520 mech kJ spec"


def test_energy_branch_unified_no_factor_mismatch() -> None:
    """Direct source check: no branch without n_thermal factor."""
    src = pathlib.Path("src/openlapexe/solver.py").read_text(encoding="utf-8")
    # The buggy line is exactly `energy_arr[i] = cum_fuel * fuel_LHV / 1000.0` without n_thermal
    has_bug = "cum_fuel * fuel_LHV / 1000.0" in src
    assert not has_bug, f"WA.5 RED: found fuel-energy factor mismatch branch without n_thermal: {has_bug}"
