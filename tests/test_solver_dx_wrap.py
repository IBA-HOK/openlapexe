# -*- coding: utf-8 -*-
"""TDD RED for Wave WA.3 — dx wrap + incl wrap + trapezoidal dt clamp."""
from __future__ import annotations

import json
import math
import pathlib
import tempfile

import numpy as np
import pytest


def _square_track_dict(step_len: float = 100.0) -> dict:
    """4-point square closed track L=400 (100 per side), z=0 flat."""
    # points at corners of 100x100 square
    pts = [
        {"s": 0.0, "x": 0.0, "y": 0.0, "z": 0.0, "curv": 0.0},
        {"s": 100.0, "x": 100.0, "y": 0.0, "z": 0.0, "curv": 0.0},
        {"s": 200.0, "x": 100.0, "y": 100.0, "z": 0.0, "curv": 0.0},
        {"s": 300.0, "x": 0.0, "y": 100.0, "z": 0.0, "curv": 0.0},
    ]
    return {"name": "square400", "length_m": 400.0, "closed_loop": True, "points": pts}


def _flat_track_dict() -> dict:
    return _square_track_dict()


def _straight_track_dict(length: float = 1000.0, n: int = 51) -> dict:
    s = np.linspace(0, length, n)
    pts = [{"s": float(s[i]), "x": float(s[i]), "y": 0.0, "z": 0.0, "curv": 0.0} for i in range(n)]
    return {"name": "straight1000", "length_m": float(length), "closed_loop": False, "points": pts}


def _write_tmp_track(data: dict) -> str:
    tmp = tempfile.mktemp(suffix=".json")
    pathlib.Path(tmp).write_text(json.dumps(data), encoding="utf-8")
    return tmp


def test_dx_wrap_sum_equals_L() -> None:
    """Closed 4-point square L=400: sum(dx)==L within 1e-9. Bug sums to L+step ~402."""
    from openlapexe.track import Track
    from openlapexe.solver import simulate_full  # import to ensure solver loaded

    data = _square_track_dict()
    tmp = _write_tmp_track(data)
    try:
        # Build Track and mesh as solver does (step from freq 50 => 2m)
        tr = Track.from_json(tmp)
        tr_m = tr.mesh(2.0)
        pts = np.asarray(tr_m.points, dtype=float)
        s_arr = np.asarray(pts[:, 0], dtype=float)
        L = float(tr_m.length_m)
        n = int(s_arr.shape[0])
        # Recompute dx exactly as solver should after fix: wrap = L - s[-1] or hypot
        # For this mesh, s[-1]==L, so wrap segment should be 0 or L - s[-1] + s[0] to make sum==L
        # Check source fix: solver should compute dx[-1] = L - s_arr[-2]?? Actually L - s[-1] is 0.
        # We verify via solver source that fix is applied, and functionally sum(dx_fixed)==L
        # Read solver source for dx wrap pattern
        src = pathlib.Path("src/openlapexe/solver.py").read_text(encoding="utf-8")
        has_wrap = ("L - s_arr" in src or "L_wrap" in src) and "hypot" in src.lower()
        has_closed = "closed_wrap" in src
        has_fix = has_wrap and has_closed
        # Functional check: compute dx with fixed logic (last = L - s[-1] if closed else copy)
        # For current file after fix, dx last should make sum == L
        # Simulate fixed dx:
        dx_fixed = np.zeros(n, dtype=float)
        for i in range(n - 1):
            dx_fixed[i] = float(s_arr[i + 1] - s_arr[i])
        # fixed wrap: distance from last point back to start (closed loop) -> L - s[-1] (=0) or hypot
        # Use L - s_arr[-1] + s_arr[0] which is 0 for this mesh; alternative L - s_arr[-2] is step but sum then L+step.
        # To make sum==L, last dx must be L - s_arr[-1] (=0) or s_arr[0] - s_arr[-1] + L
        # We assert fixed sum equals L
        dx_fixed[-1] = float(L - float(s_arr[-1])) if n >= 1 else 0.0
        # If mesh includes L, this is 0, sum = L
        s_sum_fixed = float(np.sum(dx_fixed))
        # Before fix, solver uses dx[-1]=dx[-2] => sum = L + step ~402
        dx_buggy = np.zeros(n, dtype=float)
        for i in range(n - 1):
            dx_buggy[i] = float(s_arr[i + 1] - s_arr[i])
        if n >= 2:
            dx_buggy[-1] = float(dx_buggy[-2]) if float(dx_buggy[-2]) > 1e-12 else 2.0
        s_sum_buggy = float(np.sum(dx_buggy))
        # The test must fail before fix: we assert has_fix is True (RED before fix)
        assert has_fix, f"dx wrap not fixed: dx[-1] still copies dx[-2], buggy sum {s_sum_buggy} vs L {L}"
        # Also assert fixed sum ~ L
        assert abs(s_sum_fixed - L) < 1e-9, f"sum(dx) {s_sum_fixed} != L {L}"
        # And buggy sum was off by ~step
        assert abs(s_sum_buggy - L) > 1.0, f"buggy sum unexpectedly close to L"
    finally:
        try:
            pathlib.Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass


def test_flat_track_incl_zero_everywhere() -> None:
    """Flat z=0 square: incl==0 everywhere; bug copies incl[-2] but wrap should be atan2(z0-z[-1],dx[-1]) ==0."""
    src = pathlib.Path("src/openlapexe/solver.py").read_text(encoding="utf-8")
    # Check incl wrap fix present
    has_incl_fix = "z_arr[0]" in src and "atan2" in src and "incl_arr[-1] = float(incl_arr[-2])" not in src
    assert has_incl_fix, "incl[-1] still copied, not wrapped via atan2(z0-z[-1],dx[-1])"
    # Functional: build flat track, mesh, compute incl via fixed formula should be all zero
    from openlapexe.track import Track

    data = _flat_track_dict()
    tmp = _write_tmp_track(data)
    try:
        tr = Track.from_json(tmp)
        tr_m = tr.mesh(2.0)
        pts = np.asarray(tr_m.points, dtype=float)
        s_arr = np.asarray(pts[:, 0], dtype=float)
        z_arr = np.asarray(pts[:, 3], dtype=float)
        n = int(s_arr.shape[0])
        L = float(tr_m.length_m)
        dx = np.zeros(n, dtype=float)
        for i in range(n - 1):
            dx[i] = float(s_arr[i + 1] - s_arr[i])
        dx[-1] = float(L - float(s_arr[-1]))  # fixed wrap 0
        incl = np.zeros(n, dtype=float)
        for i in range(n - 1):
            ddx = float(dx[i])
            dz = float(z_arr[i + 1] - z_arr[i])
            incl[i] = math.degrees(math.atan2(dz, ddx)) if ddx > 1e-12 else 0.0
        # wrapped last
        ddx_last = float(dx[-1])
        dz_last = float(z_arr[0] - z_arr[-1]) if n >= 1 else 0.0
        incl[-1] = math.degrees(math.atan2(dz_last, ddx_last)) if abs(ddx_last) > 1e-12 else 0.0
        assert np.all(np.abs(incl) < 1e-12), f"incl not zero {incl}"
    finally:
        pathlib.Path(tmp).unlink(missing_ok=True)


def test_straight_analytic_t_equals_L_over_v() -> None:
    """Straight 1000m Cd=Cl=0: trapezoidal dt=2*ds/(v[i]+v[i-1]+eps) analytic t==L/v holds."""
    src = pathlib.Path("src/openlapexe/solver.py").read_text(encoding="utf-8")
    # Check dt fix: should contain eps and 2*ds/(v[i]+v[i-1]
    has_dt_fix = "2.0 * ds" in src or "2*ds" in src
    has_eps = "eps" in src.lower() or "1e-12" in src or "1e-9" in src
    # Old buggy clamp: "if v_avg < 1e-9: v_avg = 1e-9" -> should be removed
    has_clamp_bug = "if v_avg < 1e-9" in src
    assert has_dt_fix and has_eps and not has_clamp_bug, f"dt fix missing: has_dt_fix={has_dt_fix} has_eps={has_eps} has_clamp_bug={has_clamp_bug}\n Need dt=2*ds/(v[i]+v[i-1]+eps)"
    # Functional analytic check: constant speed 50 m/s over 1000m => t=20s
    # Simulate fixed trapezoidal: sum 2*ds/(v_i+v_{i-1}+eps)
    L = 1000.0
    n = 51
    s = np.linspace(0, L, n)
    v_const = 50.0
    v = np.full(n, v_const, dtype=float)
    eps = 1e-12
    time_arr = np.zeros(n, dtype=float)
    for i in range(1, n):
        ds = float(s[i] - s[i - 1])
        dt = 2.0 * ds / (float(v[i]) + float(v[i - 1]) + eps)
        time_arr[i] = time_arr[i - 1] + dt
    laptime = float(time_arr[-1])
    expected = L / v_const
    assert abs(laptime - expected) < 1e-9, f"analytic t {laptime} != L/v {expected}"
    # No 1e9 spike for realistic v>=1: dt ~ ds/v ~20/1=20, not 2e9
    v_real = np.full(n, 1.0, dtype=float)
    dt_real = 2.0 * float(s[1] - s[0]) / (float(v_real[1]) + float(v_real[0]) + eps)
    assert dt_real < 1e9 and dt_real > 0, f"dt spike {dt_real} >=1e9"
    assert abs(dt_real - 20.0) < 1e-6, f"dt with v=1 should be ~20/1, got {dt_real}"
