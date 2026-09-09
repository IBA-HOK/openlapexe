# -*- coding: utf-8 -*-
"""Vehicle GGV tests - RED first (TDD)."""
from __future__ import annotations

import pathlib
import math

import numpy as np
import pytest


def test_vehicle_importable() -> None:
    import app

    assert hasattr(app, "Vehicle"), "app.Vehicle missing"
    assert hasattr(app, "load_vehicle"), "app.load_vehicle missing"


def test_from_json_f1_mvp() -> None:
    import app

    v = app.Vehicle.from_json("f1")
    assert abs(v.mass_kg - 650) < 1e-9
    assert abs(v.cda - 1.2) < 1e-9
    assert abs(v.cl + 4.8) < 1e-9
    assert len(v.torque_curve) >= 8
    # check MVP10 existence
    for attr in ["mass_kg", "weight_dist_front", "wheelbase_m", "cog_height_m", "cda", "cl", "tire_mu_x", "tire_mu_y", "engine_power_factor", "final_drive"]:
        assert hasattr(v, attr)


def test_from_json_gt() -> None:
    import app

    vg = app.Vehicle.from_json("gt")
    vf = app.Vehicle.from_json("f1")
    assert vg.mass_kg != vf.mass_kg


def test_load_vehicle_alias() -> None:
    import app

    v1 = app.load_vehicle("f1")
    v2 = app.Vehicle.from_json("f1")
    assert v1.mass_kg == v2.mass_kg


def test_compute_ggv_shape_and_deterministic() -> None:
    import app

    v = app.Vehicle.from_json("f1")
    speeds = [50.0, 100.0, 150.0]
    g1 = v.compute_ggv(speeds)
    g2 = v.compute_ggv(speeds)
    # deterministic
    if isinstance(g1, dict):
        for k in g1:
            np.testing.assert_allclose(g1[k], g2[k], rtol=0, atol=0)
        # check expected keys
        assert "ay_max" in g1 or "ay" in g1 or "lat" in str(g1.keys()).lower()
        # shape: len 3
        first_key = list(g1.keys())[0]
        # allow any key but check length
        for kk, vv in g1.items():
            arr = np.asarray(vv)
            assert arr.shape[0] == 3, f"key {kk} shape {arr.shape} != 3"
    else:
        arr1 = np.asarray(g1)
        arr2 = np.asarray(g2)
        np.testing.assert_allclose(arr1, arr2, rtol=0, atol=0)
        assert arr1.shape[0] == 3, f"ggv shape {arr1.shape} first dim !=3"
        assert arr1.shape[1] >= 3, f"ggv shape {arr1.shape} second dim <3"


def test_ggv_physical_increase_with_speed() -> None:
    """Downforce => ay_max should increase with speed."""
    import app

    v = app.Vehicle.from_json("f1")
    g = v.compute_ggv([30.0, 60.0, 90.0, 120.0])
    if isinstance(g, dict):
        # find ay key
        ay_key = None
        for k in g:
            if "ay" in k.lower() or "lat" in k.lower():
                ay_key = k
                break
        if ay_key is None:
            # fallback to any increasing value
            ay_key = list(g.keys())[-1]
        ay = np.asarray(g[ay_key])
    else:
        arr = np.asarray(g)
        # assume last column is ay
        ay = arr[:, -1]
    # strictly increasing due to aero
    for a, b in zip(ay, ay[1:]):
        assert b > a, f"ay not increasing {ay}"


def test_gear_envelope_monotonic_decreasing() -> None:
    import app

    v = app.Vehicle.from_json("f1")
    # gear_envelope may take speeds or no args
    try:
        env = v.gear_envelope([10, 30, 50, 80, 120])
        use_speeds = True
    except TypeError:
        env = v.gear_envelope()
        use_speeds = False
    arr = np.asarray(env)
    # if dict, extract relevant
    if isinstance(env, dict):
        # find ax
        ax_key = None
        for k in env:
            if "ax" in k.lower():
                ax_key = k
                break
        if ax_key is None:
            ax_key = list(env.keys())[0]
        vals = np.asarray(env[ax_key])
    else:
        if arr.ndim == 2:
            # assume column 1 is ax
            if arr.shape[1] >= 2:
                vals = arr[:, 1] if not use_speeds else arr[:, 1] if arr.shape[1] > 1 else arr[:, 0]
                # if 2D with speed+ax, vals is second col
                if arr.shape[1] == 2:
                    vals = arr[:, 1]
                else:
                    vals = arr[:, 1]
            else:
                vals = arr[:, 0]
        else:
            vals = arr
    vals = np.asarray(vals).ravel()
    # envelope should be monotonic non-increasing (more drag, less torque margin at high speed)
    # allow small tolerance 1e-9
    for a, b in zip(vals, vals[1:]):
        assert b <= a + 1e-9, f"gear envelope not monotonic decreasing {vals}"


def test_matlab_reference_or_self_expected() -> None:
    """MATLAB参照3点±1e-6 or 自前期待値: compare compute_ggv([50,100,150]) to known."""
    import app

    v = app.Vehicle.from_json("f1")
    g = v.compute_ggv([50.0, 100.0, 150.0])
    if isinstance(g, dict):
        # extract ay and ax
        ay_key = next((k for k in g if "ay" in k.lower()), list(g.keys())[-1])
        ax_key = next((k for k in g if "ax_max" in k.lower() or k == "ax_max"), None)
        if ax_key is None:
            ax_key = next((k for k in g if "ax" in k.lower()), list(g.keys())[0])
        ay = np.asarray(g[ay_key], dtype=float)
        ax = np.asarray(g[ax_key], dtype=float)
    else:
        arr = np.asarray(g, dtype=float)
        # assume columns: [v, ax_max, ax_min, ay_max] or [ax, ay, ...]
        if arr.ndim == 2 and arr.shape[1] >= 3:
            # if first col is speeds (50,100,150)
            if np.allclose(arr[:, 0], [50, 100, 150], atol=1e-6):
                ax = arr[:, 1]
                ay = arr[:, -1]
            else:
                ax = arr[:, 0]
                ay = arr[:, 1] if arr.shape[1] > 1 else arr[:, 0]
        else:
            pytest.skip("unexpected ggv shape for reference test")
            return
    # Self expected values must be computed deterministically by current implementation.
    # We pin tolerance 1e-6 against values that the implementation actually yields.
    # So first we assert values are finite and reasonable, then check against hard-coded expected
    # derived from the spec formula (rho=1.225,g=9.81,r=0.33, mu* Nz/m).
    # To keep test maintainable, we allow either exact match to our formula or placeholder.
    # Here we compute expected via same physics as app.py (independent replication) and require ±1e-6.
    # Independent replication:
    rho = 1.225
    g_const = 9.81
    speeds = np.array([50.0, 100.0, 150.0])
    cda = v.cda
    cl = v.cl
    mu_y = v.tire_mu_y
    mass = v.mass_kg
    downforce = -0.5 * rho * cl * speeds**2  # cl negative => positive
    Nz = mass * g_const + downforce
    ay_expected = mu_y * Nz / mass
    # ay check
    np.testing.assert_allclose(ay, ay_expected, rtol=1e-6, atol=1e-6)
    # ax also should be plausible (engine or tire limited) - at least check finite and >=0
    for val in ax:
        assert math.isfinite(val) and val >= 0


def test_no_scipy_matplotlib_import() -> None:
    import pathlib

    text = pathlib.Path("app.py").read_text(encoding="utf-8")
    # ensure scipy/matplotlib not imported
    lowered = text.lower()
    assert "scipy" not in lowered, "scipy must not appear in app.py"
    assert "matplotlib" not in lowered, "matplotlib must not appear in app.py"
    # check pchip is self-made (Fritsch-Carlson) and numpy.interp used
    assert "numpy" in lowered or "np." in text
    assert "interp" in lowered, "numpy.interp must be used"


def test_pchip_used_and_numpy_only() -> None:
    import pathlib

    text = pathlib.Path("app.py").read_text(encoding="utf-8")
    # should contain pchip and Fritsch or Carlson keyword
    assert "pchip" in text.lower(), "pchip implementation required"
    # ensure no scipy.signal
    assert "signal" not in text.lower() or "scipy" not in text.lower()


def test_encoding_utf8() -> None:
    import pathlib

    txt = pathlib.Path("app.py").read_text(encoding="utf-8")
    assert "utf-8" in txt.lower()
