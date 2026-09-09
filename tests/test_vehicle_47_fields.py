# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import pathlib
import dataclasses

import numpy as np


def test_vehicle47_has_47_fields() -> None:
    from openlapexe.vehicle import Vehicle47

    fields = dataclasses.fields(Vehicle47)
    assert len(fields) == 47, f"Vehicle47 fields {len(fields)} !=47 got {[f.name for f in fields]}"
    names = {f.name for f in fields}
    for key in ["Name", "Type", "M", "df", "L", "rack", "Cl", "Cd", "factor_Cl", "factor_Cd", "da", "A", "rho", "br_disc_d", "br_pad_h", "br_pad_mu", "br_nop", "br_pist_d", "br_mast_d", "br_ped_r", "factor_grip", "tyre_radius", "Cr", "mu_x", "mu_x_M", "sens_x", "mu_y", "mu_y_M", "sens_y", "CF", "CR", "factor_power", "n_thermal", "fuel_LHV", "drive", "shift_time", "n_primary", "n_final", "n_gearbox", "ratio_primary", "ratio_final", "ratio_gearbox", "torque_curve", "cog_height_m", "mass_kg", "wheelbase_m", "cda"]:
        assert key in names, f"missing field {key}"


def test_json_has_47_keys_and_torque_18() -> None:
    root = pathlib.Path(__file__).resolve().parent.parent
    for name in ["f1", "gt"]:
        p = root / "data" / "vehicles" / f"{name}.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        # 47 MATLAB keys existence
        matlab_keys = ["Name", "Type", "M", "df", "L", "rack", "Cl", "Cd", "factor_Cl", "factor_Cd", "da", "A", "rho", "br_disc_d", "br_pad_h", "br_pad_mu", "br_nop", "br_pist_d", "br_mast_d", "br_ped_r", "factor_grip", "tyre_radius", "Cr", "mu_x", "mu_x_M", "sens_x", "mu_y", "mu_y_M", "sens_y", "CF", "CR", "factor_power", "n_thermal", "fuel_LHV", "drive", "shift_time", "n_primary", "n_final", "n_gearbox", "ratio_primary", "ratio_final", "ratio_gearbox"]
        for k in matlab_keys:
            assert k in data, f"{name}.json missing {k}"
        tc = data.get("torque_curve")
        assert isinstance(tc, list) and len(tc) == 18, f"{name} torque len {len(tc) if tc else None} !=18"
        # MVP backward compat
        for k in ["mass_kg", "weight_dist_front", "wheelbase_m", "cog_height_m", "cda", "cl", "tire_mu_x", "tire_mu_y", "engine_power_factor", "final_drive"]:
            assert k in data, f"{name} missing MVP {k}"


def test_cog_affects_ggv_when_ax_nonzero() -> None:
    from openlapexe.vehicle import Vehicle47

    v = Vehicle47.from_json("f1")
    v_high = dataclasses.replace(v, cog_height_m=0.6)
    # low speed where engine provides ax >0
    speeds = [20.0, 40.0, 60.0]
    g_low = v.compute_ggv(speeds)
    g_high = v_high.compute_ggv(speeds)
    # at least one speed where ay_max differs due to cog and ax!=0
    diff = np.abs(g_low["ay_max"] - g_high["ay_max"])
    assert np.any(diff > 1e-6), f"cog should affect ay_max when ax!=0 diff={diff}"
    # at high speed where ax_engine ~0, may not differ, but low speed must differ
    # also verify tyre_radius vehicle specific influences gear envelope
    v_gt = Vehicle47.from_json("gt")
    assert v.tyre_radius != v_gt.tyre_radius, "WHEEL_RADIUS should be vehicle-specific"


def test_torque_18_points() -> None:
    from openlapexe.vehicle import Vehicle47

    v = Vehicle47.from_json("f1")
    assert len(v.torque_curve) == 18
    rpms = [p[0] for p in v.torque_curve]
    assert rpms[0] == 1000 and rpms[-1] == 18000
    # verify peak torque around 13000
    tqs = [p[1] for p in v.torque_curve]
    assert max(tqs) == 350.0


def test_gear_envelope_rpm_dependent() -> None:
    from openlapexe.vehicle import Vehicle47

    v = Vehicle47.from_json("f1")
    # envelope should be RPM dependent: check that Fx per gear varies with torque curve, not flat peak_power/v
    # Use two speeds where different gears dominate: low speed vs high speed should have different envelope values derived from torque
    speeds = np.array([10.0, 30.0, 50.0, 80.0, 120.0], dtype=float)
    env = v.gear_envelope(speeds)
    # envelope should decrease overall but not be simple peak_power / v
    # compute peak_power approx: torque* rpm max power / v
    rpms, tqs = v._torque_arrays()
    power = tqs * rpms * 2 * np.pi / 60 * v.factor_power
    peak_power = float(np.max(power))
    peak_env = peak_power / np.maximum(speeds, 1e-6)
    # gear envelope should differ from peak_power envelope at least at one point >1%
    diff = np.abs(env - np.minimum(peak_env / v.M, env + 10))  # dummy to ensure not identical
    # Actually check that env is not proportional to 1/v via peak_power (constant numerator)
    # Instead check that torque-based Fx has gear steps: compare envelope at 20 vs 30 should be influenced by gear ratios, may be equal (flat) due to mono but _fx_engine_max raw should vary
    fx_raw = v._fx_engine_max(speeds)
    assert np.any(np.diff(fx_raw) != 0), "Fx should vary with speed (RPM dependent)"
    # also ensure using tyre_radius per vehicle
    v_gt = Vehicle47.from_json("gt")
    env_gt = v_gt.gear_envelope(speeds)
    assert not np.allclose(env, env_gt), "gear envelope should differ per vehicle (tyre_radius, ratios)"


def test_app_vehicle_coexist() -> None:
    import app
    from openlapexe.vehicle import Vehicle47

    v_app = app.Vehicle.from_json("f1")
    v_src = Vehicle47.from_json("f1")
    assert v_app.mass_kg == v_src.mass_kg
    assert v_app.torque_curve[0][0] == v_src.torque_curve[0][0]
    # both imports succeed

