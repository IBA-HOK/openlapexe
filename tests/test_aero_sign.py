# -*- coding: utf-8 -*-
"""TDD RED for WA.6 — unified aero sign, high-downforce ay_max > zero-aero."""
from __future__ import annotations

import copy
import json
import pathlib
import tempfile

import numpy as np


def test_aero_sign_unified_and_dead_line_removed() -> None:
    """WA.6: unified Fz_aero negative, Fz_total, Nz=-(Fz_total), dead fx*0 removed."""
    src = pathlib.Path("src/openlapexe/solver.py").read_text(encoding="utf-8")
    # Check dead line removed
    assert "factor_grip_veh * 0" not in src, "WA.6 RED: dead fx*0 line still present"
    assert "fx * 0" not in src or "fx*0" not in src, "dead fx*0 not removed"
    # Unified aero pattern must exist
    has_fz_aero = "Fz_aero" in src and "0.5 * rho" in src and "Cl" in src
    assert has_fz_aero, "WA.6 missing Fz_aero=0.5*rho*Cl*A*v^2"
    # Check Fz_total unification
    assert "Fz_total" in src and "Fz_mass" in src, "WA.6 missing Fz_total=Fz_mass+Fz_aero"
    assert "Fz_mass + Fz_aero" in src or "Fz_mass+Fz_aero" in src, "Fz_total formula missing"
    # Check Nz = -(Fz_total)
    has_nz = "Nz = -(Fz_total)" in src or "Nz=-(Fz_total)" in src or "-(Fz_total)" in src
    assert has_nz, "WA.6 missing Nz=-(Fz_total) unified sign"
    # Ensure at least 2 places use unified (v_max and _ay_max_at or tps)
    count_nz_unified = src.count("-(Fz_total)")
    assert count_nz_unified >= 2, f"WA.6 unified Nz should appear >=2 times, got {count_nz_unified}"


def test_high_downforce_ay_greater_than_zero_aero() -> None:
    """Functional: high-downforce ay_max > zero-aero (currently decreases FAIL)."""
    from openlapexe.solver import simulate_full

    def make_track(curv: float = 0.08) -> str:
        n = 81
        L = 1000.0
        s = np.linspace(0, L, n)
        pts = [{"s": float(s[i]), "x": float(s[i]), "y": 0.0, "z": 0.0, "curv": float(curv)} for i in range(n)]
        data = {"name": "highcurve", "length_m": float(L), "closed_loop": True, "points": pts}
        p = tempfile.mktemp(suffix=".json")
        pathlib.Path(p).write_text(json.dumps(data), encoding="utf-8")
        return p

    track = make_track(curv=0.08)
    # Load base vehicle dict
    base = json.loads(pathlib.Path("data/vehicles/f1.json").read_text(encoding="utf-8"))
    d_high = copy.deepcopy(base)
    d_high["factor_Cl"] = 2.0
    # ensure Cl negative
    d_high["Cl"] = -4.8
    d_zero = copy.deepcopy(base)
    d_zero["factor_Cl"] = 0.0
    d_zero["Cl"] = 0.0
    # also zero Cd to isolate? keep same Cd factor but Cl zero enough
    p_high = tempfile.mktemp(suffix=".json")
    p_zero = tempfile.mktemp(suffix=".json")
    pathlib.Path(p_high).write_text(json.dumps(d_high), encoding="utf-8")
    pathlib.Path(p_zero).write_text(json.dumps(d_zero), encoding="utf-8")
    try:
        r_high = simulate_full(p_high, track, 50)
        r_zero = simulate_full(p_zero, track, 50)
        # High downforce should give higher ay_max => higher corner speed => lower laptime
        # Check laptime
        assert r_high.laptime < r_zero.laptime, f"WA.6 FAIL: high-downforce laptime {r_high.laptime} not < zero-aero {r_zero.laptime}"
        # Also check max v higher
        assert float(np.max(r_high.v)) > float(np.max(r_zero.v)), "high-downforce max v should be > zero-aero"
        # Direct Fz_aero sign check: Fz_aero negative, Fz_total negative, Nz positive
        # Compute with unified formula at v=50
        M = float(base["M"])
        g = 9.81
        rho = float(base["rho"])
        A = float(base["A"])
        v = 50.0
        Cl = float(d_high["Cl"])
        fCl = float(d_high["factor_Cl"])
        Fz_mass = -M * g
        Fz_aero = 0.5 * rho * fCl * Cl * A * v * v
        assert Fz_aero < 0, f"Fz_aero should be negative, got {Fz_aero}"
        Fz_total = Fz_mass + Fz_aero
        Nz = -(Fz_total)
        assert Nz > -Fz_mass, "Nz with aero should exceed mass-only"
        # Zero aero
        Fz_aero0 = 0.5 * rho * 0.0 * 0.0 * A * v * v
        assert Fz_aero0 == 0.0
    finally:
        for p in [track, p_high, p_zero]:
            try:
                pathlib.Path(p).unlink(missing_ok=True)
            except Exception:
                pass
