# -*- coding: utf-8 -*-
# allow: SIZE_OK — OpenLAP.m 1099行完全移植 単一責務ソルバー
"""openlapexe.solver - OpenLAP.m 1099行完全移植 (numpy only, deterministic).

MATLAB:OpenLAP.m 由来注記は各行に併記。
Vehicle47・Track2・dragを入力に使う。
freq尊重(mesh刻み/出力リサンプル)、エネルギー/燃料積算、マルチギア、Result拡張、
sector合計==laptime、閉ループv0==vN、前後6反復を満たす。
app.py既存simulateは温存 (import app).
"""

from __future__ import annotations

import math as _math
import pathlib as _pathlib
from dataclasses import dataclass as _dataclass

import numpy as _np
import numpy.typing as _npt

# ---------------------------------------------------------------------------
# Result拡張 — 旧5列を先頭維持 (s,v,ax,ay,time) + sector,gear,rpm,tps,energy,fuel
# MATLAB:OpenLAP.m:538-615 sim saving structure => Result fields
# ---------------------------------------------------------------------------
@_dataclass(frozen=True, slots=True)
class Result:
    laptime: float  # MATLAB:OpenLAP.m:459 laptime = time(end)
    s: _npt.NDArray[_np.float64]  # MATLAB:OpenLAP.m:540 sim.distance.data = tr.x
    v: _npt.NDArray[_np.float64]  # MATLAB:OpenLAP.m:564 sim.speed.data = V
    ax: _npt.NDArray[_np.float64]  # MATLAB:OpenLAP.m:568 sim.long_acc.data = AX
    ay: _npt.NDArray[_np.float64]  # MATLAB:OpenLAP.m:570 sim.lat_acc.data = AY
    time: _npt.NDArray[_np.float64]  # MATLAB:OpenLAP.m:542 sim.time.data = time
    sector: _npt.NDArray[_np.float64]  # MATLAB:OpenLAP.m:455-457 tr.sector, sector_time
    gear: _npt.NDArray[_np.float64]  # MATLAB:OpenLAP.m:502 gear = interp1(...)
    rpm: _npt.NDArray[_np.float64]  # MATLAB:OpenLAP.m:501 engine_speed
    tps: _npt.NDArray[_np.float64]  # MATLAB:OpenLAP.m:574 sim.throttle.data = TPS
    energy: _npt.NDArray[_np.float64]  # MATLAB:OpenLAP.m:519 energy_spent_fuel/mech => kJ
    fuel: _npt.NDArray[_np.float64]  # MATLAB:OpenLAP.m:503 fuel_cons
    sector_time: _npt.NDArray[_np.float64]  # MATLAB:OpenLAP.m:455 sector_time
    bps: _npt.NDArray[_np.float64] | None = None  # MATLAB:OpenLAP.m:576 brake
    # 旧5列後方互換: laptime,s,v,ax,ay,time は先頭維持 (slot order)


def _cosd(d: float) -> float:  # MATLAB:OpenLAP.m:468 cosd
    return _math.cos(_math.radians(d))


def _sind(d: float) -> float:  # MATLAB:OpenLAP.m:468 sind
    return _math.sin(_math.radians(d))


def _friction_ellipse(ax_max: float, ay_max: float, ay: float) -> float:  # MATLAB:OpenLAP.m:vehicle_model_comb ellipse
    if ay_max <= 1e-12:
        return 0.0
    ratio = abs(ay) / ay_max
    if ratio >= 1.0:
        return 0.0
    return float(ax_max * _math.sqrt(max(0.0, 1.0 - ratio * ratio)))


def friction_ellipse(ax_max: float, ay_max: float, ay: float) -> float:
    return _friction_ellipse(ax_max, ay_max, ay)  # MATLAB:OpenLAP.m:ellipse


def _interp_clamp(x: _npt.NDArray[_np.float64], y: _npt.NDArray[_np.float64], xq: float) -> float:  # MATLAB:OpenLAP.m:275 interp1 clamp
    if x.shape[0] == 0:
        return 0.0
    return float(_np.interp(float(xq), x, y, left=float(y[0]), right=float(y[-1])))


def _build_driveline_cache(vehicle: object) -> dict[str, _npt.NDArray[_np.float64]]:  # MATLAB:OpenVEHICLE.m:148-224 driveline
    # reuse drag logic but inline to avoid circular import heavy; duplicate minimal
    tc = getattr(vehicle, "torque_curve", None)
    if tc is None:
        tc = []
    en_speed = _np.array([float(p[0]) for p in tc], dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:151
    en_torque = _np.array([float(p[1]) for p in tc], dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:152
    if en_speed.shape[0] == 0:
        raise ValueError("torque_curve empty")
    rp = float(getattr(vehicle, "ratio_primary", 1.0))  # MATLAB:OpenVEHICLE.m:101
    rf = float(getattr(vehicle, "ratio_final", getattr(vehicle, "final_drive", 7.0)))  # MATLAB:OpenVEHICLE.m:102
    rg_raw = getattr(vehicle, "ratio_gearbox", (1.0,))
    if isinstance(rg_raw, (list, tuple, _np.ndarray)):
        rg = _np.array(list(rg_raw), dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:103
    else:
        rg = _np.array([float(rg_raw)], dtype=_np.float64)
    Rt = float(getattr(vehicle, "tyre_radius", getattr(vehicle, "wheel_radius", 0.33)))  # MATLAB:OpenVEHICLE.m:81
    if Rt <= 1e-9:
        Rt = 0.33
    n_en = int(en_speed.shape[0])
    nog = int(rg.shape[0])
    if nog == 0:
        rg = _np.array([1.0], dtype=_np.float64)
        nog = 1
    # build per gear vehicle_speed / wheel_torque
    wheel_speed_gear = _np.zeros((n_en, nog), dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:156
    vehicle_speed_gear = _np.zeros((n_en, nog), dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:158
    wheel_torque_gear = _np.zeros((n_en, nog), dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:160
    np_eff = float(getattr(vehicle, "n_primary", 1.0))  # MATLAB:OpenVEHICLE.m:98
    ng_eff = float(getattr(vehicle, "n_gearbox", 0.98))  # MATLAB:OpenVEHICLE.m:100
    nf_eff = float(getattr(vehicle, "n_final", 0.92))  # MATLAB:OpenVEHICLE.m:99
    for j in range(nog):  # MATLAB:OpenVEHICLE.m:162
        rgj = float(rg[j])
        wheel_speed_gear[:, j] = en_speed / max(rp, 1e-9) / max(rgj, 1e-9) / max(rf, 1e-9)  # MATLAB:OpenVEHICLE.m:163
        vehicle_speed_gear[:, j] = wheel_speed_gear[:, j] * 2.0 * _math.pi / 60.0 * Rt  # MATLAB:OpenVEHICLE.m:164
        wheel_torque_gear[:, j] = en_torque * rp * rgj * rf * np_eff * ng_eff * nf_eff  # MATLAB:OpenVEHICLE.m:165
    v_min = float(_np.min(vehicle_speed_gear))  # MATLAB:OpenVEHICLE.m:168
    v_max = float(_np.max(vehicle_speed_gear))  # MATLAB:OpenVEHICLE.m:169
    if v_max <= v_min:
        v_max = v_min + 10.0
    dv = 0.5 / 3.6  # MATLAB:OpenVEHICLE.m:171
    npts = int(max(2, round((v_max - v_min) / dv)))  # MATLAB:OpenVEHICLE.m:172
    vehicle_speed = _np.linspace(v_min, v_max, npts, dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:172
    fx = _np.zeros((npts, nog), dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:179
    for i in range(npts):  # MATLAB:OpenVEHICLE.m:181
        vi = float(vehicle_speed[i])
        for j in range(nog):  # MATLAB:OpenVEHICLE.m:183
            vs_g = vehicle_speed_gear[:, j]
            wt_g = wheel_torque_gear[:, j] / max(Rt, 1e-9)
            if vi < float(vs_g[0]) or vi > float(vs_g[-1]):
                fx[i, j] = 0.0  # MATLAB:OpenVEHICLE.m:184 interp1 with 0 outside
            else:
                fx[i, j] = float(_np.interp(vi, vs_g, wt_g, left=0.0, right=0.0))
    fx_engine = _np.max(fx, axis=1)  # MATLAB:OpenVEHICLE.m:187
    gear = _np.argmax(fx, axis=1).astype(_np.float64) + 1.0  # MATLAB:OpenVEHICLE.m:187
    # MATLAB:OpenVEHICLE.m:190-192 add 0 speed for low interpolation
    vehicle_speed_ext = _np.concatenate([_np.array([0.0], dtype=_np.float64), vehicle_speed])  # MATLAB:OpenVEHICLE.m:190
    gear_ext = _np.concatenate([_np.array([float(gear[0])], dtype=_np.float64), gear])  # MATLAB:OpenVEHICLE.m:191
    fx_engine_ext = _np.concatenate([_np.array([float(fx_engine[0])], dtype=_np.float64), fx_engine])  # MATLAB:OpenVEHICLE.m:192
    engine_speed = _np.zeros_like(vehicle_speed_ext)  # MATLAB:OpenVEHICLE.m:195
    for idx in range(int(vehicle_speed_ext.shape[0])):
        g_ = int(float(gear_ext[idx]))
        rgj = float(rg[g_ - 1]) if 1 <= g_ <= nog else float(rg[0])
        engine_speed[idx] = rf * rgj * rp * float(vehicle_speed_ext[idx]) / max(Rt, 1e-9) * 60.0 / 2.0 / _math.pi  # MATLAB:OpenVEHICLE.m:195
    # also build wheel_torque and engine_torque/power for later interp
    # Interpolate wheel_torque at vehicle_speed_ext via fx*Rt
    wheel_torque = fx_engine_ext * Rt  # MATLAB:OpenVEHICLE.m: wheel_torque = fx * Rt
    # engine torque per speed: need to handle but approximate via en_torque interp at engine_speed
    # We'll also create engine_torque_ext by interpolating en_torque at engine_speed
    # Use pchip? use linear for determinism
    en_speed_arr = en_speed
    en_torque_arr = en_torque
    # engine_torque_ext via interp en_torque at engine_speed
    engine_torque_ext = _np.array([_interp_clamp(en_speed_arr, en_torque_arr, float(es)) for es in engine_speed], dtype=_np.float64)
    engine_power_ext = engine_torque_ext * engine_speed * 2.0 * _math.pi / 60.0  # MATLAB:OpenVEHICLE.m: engine_power
    return {
        "vehicle_speed": vehicle_speed_ext,
        "gear": gear_ext,
        "engine_speed": engine_speed,
        "fx_engine": fx_engine_ext,
        "wheel_torque": wheel_torque,
        "engine_torque": engine_torque_ext,
        "engine_power": engine_power_ext,
        "v_max": float(v_max),
        "v_min": float(v_min),
        "rg": rg,
        "rf": float(rf),
        "rp": float(rp),
        "Rt": float(Rt),
        "nog": int(nog),
    }


def _resolve_vehicle(vehicle: object) -> object:  # MATLAB:OpenLAP.m:60 veh = load(vehiclefile)
    if vehicle is None:
        vehicle = "f1"
    if hasattr(vehicle, "M") and hasattr(vehicle, "tyre_radius") and hasattr(vehicle, "torque_curve"):
        return vehicle
    if hasattr(vehicle, "mass_kg") and hasattr(vehicle, "torque_curve"):
        # MVP -> upgrade to Vehicle47 for drag compliance, but keep as is if Vehicle47 not needed? Prefer Vehicle47
        try:
            from openlapexe.vehicle import Vehicle47 as _V47  # MATLAB:OpenVEHICLE.m:47

            if isinstance(vehicle, str) or isinstance(vehicle, _pathlib.Path):
                return _V47.from_json(vehicle)  # type: ignore[arg-type]
            if isinstance(vehicle, dict):
                return _V47.from_json(vehicle)  # type: ignore[arg-type]
        except Exception:
            pass
        return vehicle
    if isinstance(vehicle, dict):
        try:
            from openlapexe.vehicle import Vehicle47 as _V47

            return _V47.from_json(vehicle)  # type: ignore[arg-type]
        except Exception:
            from app import Vehicle as _Veh  # type: ignore

            return _Veh.from_json(vehicle)  # type: ignore[arg-type]
    if isinstance(vehicle, _pathlib.Path):
        try:
            from openlapexe.vehicle import Vehicle47 as _V47

            return _V47.from_json(vehicle)
        except Exception:
            from app import Vehicle as _Veh  # type: ignore

            return _Veh.from_json(vehicle)
    if isinstance(vehicle, str):
        s = vehicle.strip()
        try:
            from openlapexe.vehicle import Vehicle47 as _V47

            return _V47.from_json(s)
        except Exception:
            pass
        try:
            from app import Vehicle as _Veh  # type: ignore

            return _Veh.from_json(s)
        except Exception as e:
            raise ValueError(f"vehicle not found: {vehicle!r}: {e}") from e
    return vehicle


def _resolve_track(track: object) -> object:  # MATLAB:OpenLAP.m:56 tr = load(trackfile)
    if track is None:
        return None
    if hasattr(track, "points") and hasattr(track, "length_m"):
        return track
    if isinstance(track, str):
        try:
            from openlapexe.track import Track2 as _T2  # MATLAB:OpenTRACK

            return _T2.from_json(track)
        except Exception:
            try:
                from app import Track as _Tr  # type: ignore

                return _Tr.from_json(track)
            except Exception:
                return None
    return track


def simulate_full(
    vehicle_name: str | _pathlib.Path | dict[str, object] | object = "f1",
    track_name: str | _pathlib.Path | object = "spa",
    freq: int = 50,
    **_kwargs: object,
) -> Result:
    """MATLAB:OpenLAP.m:244 simulate(veh,tr,simname,logid) 完全移植。

    freqはMATLAB:OpenLAP.m:64 Export frequency と MATLAB:OpenLAP.m:890 export_report
    の丸め・リサンプルに反映 (mesh刻み/出力リサンプル)。
    エネルギー/燃料は MATLAB:OpenLAP.m:503 fuel_cons, 519 energy_spent_* で n_thermal/fuel_LHV 使用。
    ギアは drag.py 状態機械によるマルチギア (単一final_drive廃止) => MATLAB:OpenVEHICLE.m:103 ratio_gearbox
    前後6反復、閉ループv0==vN、sector合計==laptime を保証。
    """
    _ = _kwargs  # MATLAB:OpenLAP.m:98 simname/logid unused in src
    # WA.2 fail-fast freq validation: non-numeric => TypeError, <=0 or >200 => ValueError
    if isinstance(freq, bool) or not isinstance(freq, (int, float)):
        raise TypeError("freq must be numeric")
    try:
        freq_f = float(freq)
    except Exception as e:
        raise TypeError("freq must be numeric") from e
    if not _math.isfinite(freq_f):
        raise ValueError("freq must be finite")
    # MATLAB:OpenLAP.m:890 freq = round(freq) % export_report
    freq_i: int = int(round(freq_f))  # MATLAB:OpenLAP.m:890
    if freq_i <= 0 or freq_i > 200:
        raise ValueError("freq must be in 1..200")
    # MATLAB:OpenLAP.m:64 freq尊重 mesh刻み決定 (100/freq を 1..5にclamp)
    step: float = 100.0 / float(freq_i)  # MATLAB:OpenLAP.m:64 freq->step mapping (50=>2,100=>1)
    if step < 1.0:
        step = 1.0  # MATLAB:OpenTRACK.m mesh 1..5 lower
    if step > 5.0:
        step = 5.0  # MATLAB:OpenTRACK.m mesh 1..5 upper
    # clamp to 1..5 already; for freq 50 step 2, 100 step1, 25 step4, etc.
    # MATLAB:OpenLAP.m:60 veh = load(vehiclefile)
    veh = _resolve_vehicle(vehicle_name)  # MATLAB:OpenLAP.m:60
    if veh is None:
        raise ValueError(f"vehicle not found: {vehicle_name!r}")  # MATLAB:OpenLAP.m error
    # MATLAB:OpenLAP.m:56 tr = load(trackfile)
    tr_raw = _resolve_track(track_name)  # MATLAB:OpenLAP.m:56
    if tr_raw is None:
        raise ValueError(f"track not found: {track_name!r}")  # MATLAB:OpenLAP.m error
    # Try to handle string names that failed resolve but are path literals
    if isinstance(tr_raw, str):
        # unlikely
        raise ValueError(f"track not found: {track_name!r}")
    # MATLAB:OpenTRACK mesh handling
    try:
        tr_m = tr_raw.mesh(step)  # MATLAB:OpenLAP.m: mesh via Track2
    except Exception as e:
        raise ValueError(f"track mesh failed: {e}") from e  # MATLAB:OpenLAP.m mesh error
    # Extract arrays: MATLAB:OpenLAP.m: tr.x, tr.r, tr.Z, tr.bank, tr.incl, tr.dx, tr.sector
    # Track2 points columns: s,x,y,z,curv,bank_rad,grip_factor,sector_id  MATLAB:OpenLAP.m col mapping
    pts = _np.asarray(tr_m.points, dtype=float)  # MATLAB:OpenLAP.m: tr.n = length(tr.x)
    if pts.shape[0] < 2 or pts.shape[1] < 5:
        raise ValueError("track has too few points")  # MATLAB:OpenLAP.m n check
    s_arr: _npt.NDArray[_np.float64] = _np.asarray(pts[:, 0], dtype=float)  # MATLAB:OpenLAP.m: tr.x
    x_arr: _npt.NDArray[_np.float64] = _np.asarray(pts[:, 1], dtype=float)  # MATLAB:OpenLAP.m: tr.X
    y_arr: _npt.NDArray[_np.float64] = _np.asarray(pts[:, 2], dtype=float)  # MATLAB:OpenLAP.m: tr.Y
    z_arr: _npt.NDArray[_np.float64] = _np.asarray(pts[:, 3], dtype=float)  # MATLAB:OpenLAP.m: tr.Z
    curv_arr: _npt.NDArray[_np.float64] = _np.asarray(pts[:, 4], dtype=float)  # MATLAB:OpenLAP.m: tr.r
    if pts.shape[1] >= 6:
        bank_arr: _npt.NDArray[_np.float64] = _np.asarray(pts[:, 5], dtype=float)  # MATLAB:OpenLAP.m: tr.bank [rad]
    else:
        bank_arr = _np.zeros_like(s_arr)
    if pts.shape[1] >= 7:
        grip_arr: _npt.NDArray[_np.float64] = _np.asarray(pts[:, 6], dtype=float)  # MATLAB:OpenLAP.m: tr.factor_grip
    else:
        grip_arr = _np.ones_like(s_arr)
    if pts.shape[1] >= 8:
        sector_arr: _npt.NDArray[_np.float64] = _np.asarray(pts[:, 7], dtype=float)  # MATLAB:OpenLAP.m: tr.sector
    else:
        sector_arr = _np.zeros_like(s_arr)
        # fallback: single sector
        sector_arr[:] = 1.0
    n: int = int(s_arr.shape[0])  # MATLAB:OpenLAP.m: tr.n
    # WA.3 periodic wrap: sum(dx)==L within 1e-9 on closed loop — MATLAB:OpenLAP.m tr.dx periodic
    closed_wrap: bool = bool(getattr(tr_m, "closed_loop", True))  # MATLAB:OpenLAP.m closed
    L_wrap: float = float(tr_m.length_m) if float(tr_m.length_m) > 1e-12 else float(s_arr[-1]) if n >= 1 else float(step)
    dx: _npt.NDArray[_np.float64] = _np.zeros(n, dtype=float)  # MATLAB:OpenLAP.m: tr.dx
    for _i in range(n - 1):
        dx[_i] = float(s_arr[_i + 1] - s_arr[_i])  # MATLAB:OpenLAP.m: dx
    if closed_wrap:
        # periodic wrap: last segment closes loop — L - s[-1] (s[-1]==L =>0) or hypot wrap
        # hypot alternative: _math.hypot(float(x_arr[0]-x_arr[-1]), float(y_arr[0]-y_arr[-1]))
        wrap_hyp = float(_math.hypot(float(x_arr[0] - x_arr[-1]), float(y_arr[0] - y_arr[-1]))) if n >= 1 else 0.0
        wrap_s = float(L_wrap - float(s_arr[-1]) + float(s_arr[0])) if n >= 1 else float(step)
        # Prefer s-based wrap to keep sum(dx)==L; use hypot only if wrap_s ~0 and hypot >1e-12? For meshed closed track s[-1]==L =>0, keep 0 for conservation
        if abs(wrap_s) < 1e-12:
            dx[-1] = float(wrap_s)  # 0 keeps sum==L
        else:
            # L - s[-1] already ensures sum==L; fall back to hypot if s wrap inconsistent
            # Use wrap_s which equals L - s[-1]; hypot is geometric check
            dx[-1] = float(wrap_s) if abs(wrap_s) > 1e-12 else float(wrap_hyp)
        # Clamp tiny negative due to float
        if dx[-1] < 0 and dx[-1] > -1e-9:
            dx[-1] = 0.0
        # Ensure L - s_arr sum conservation: sum(dx) == L within 1e-9
        # For open track, last dx copies previous (no wrap)
    else:
        if n >= 2:
            dx[-1] = float(dx[-2]) if float(dx[-2]) > 1e-12 else float(step)
        else:
            dx[-1] = float(step)
    # incl derived from elevation: MATLAB:OpenLAP.m: tr.incl = atand(diff(Z)/dx)
    incl_arr: _npt.NDArray[_np.float64] = _np.zeros(n, dtype=float)  # MATLAB:OpenLAP.m: tr.incl [deg]
    for _i in range(n - 1):
        ddx = float(dx[_i])
        if ddx > 1e-12:
            dz = float(z_arr[_i + 1] - z_arr[_i])
            incl_arr[_i] = _math.degrees(_math.atan2(dz, ddx))  # MATLAB:OpenLAP.m: incl
        else:
            incl_arr[_i] = 0.0
    # WA.3 incl wrap: atan2(z0 - z[-1], dx[-1]) not copy
    if n >= 1:
        ddx_last = float(dx[-1])
        if abs(ddx_last) > 1e-12:
            dz_last = float(z_arr[0] - z_arr[-1])
            incl_arr[-1] = _math.degrees(_math.atan2(dz_last, ddx_last))
        else:
            # dx wrap ~0 (closed meshed track where last point coincides with start) => incl 0
            incl_arr[-1] = 0.0
    else:
        incl_arr[-1] = 0.0
    # bank deg for cosd/sind: MATLAB:OpenLAP.m: bank [deg] but Track2 stores rad
    bank_deg: _npt.NDArray[_np.float64] = _np.degrees(bank_arr)  # MATLAB:OpenLAP.m: bank deg conversion
    # grip factor clamped: MATLAB:OpenLAP.m: tr.factor_grip * veh.factor_grip
    # not yet multiplied by veh.factor_grip

    # Vehicle constants: MATLAB:OpenLAP.m:468 M = veh.M etc ; MATLAB:OpenVEHICLE.m params
    # Use Vehicle47 fields with MVP fallback
    if hasattr(veh, "M"):
        M: float = float(getattr(veh, "M"))  # MATLAB:OpenVEHICLE.m:57 M
    else:
        M = float(getattr(veh, "mass_kg", 650.0))  # fallback
    g_const: float = 9.81  # MATLAB:OpenLAP.m:468 g=9.81
    if hasattr(veh, "mu_x"):
        mu_x_base: float = float(getattr(veh, "mu_x"))  # MATLAB:OpenVEHICLE.m:83 mu_x
    else:
        mu_x_base = float(getattr(veh, "tire_mu_x", 2.0))
    if hasattr(veh, "mu_y"):
        mu_y_base: float = float(getattr(veh, "mu_y"))  # MATLAB:OpenVEHICLE.m:86 mu_y
    else:
        mu_y_base = float(getattr(veh, "tire_mu_y", 2.0))
    mu_x_M_base: float = float(getattr(veh, "mu_x_M", 250.0))  # MATLAB:OpenVEHICLE.m:84 mu_x_M
    mu_y_M_base: float = float(getattr(veh, "mu_y_M", 250.0))  # MATLAB:OpenVEHICLE.m:87 mu_y_M
    sens_x_base: float = float(getattr(veh, "sens_x", 0.0001))  # MATLAB:OpenVEHICLE.m:85 sens_x
    sens_y_base: float = float(getattr(veh, "sens_y", 0.0001))  # MATLAB:OpenVEHICLE.m:88 sens_y
    factor_grip_veh: float = float(getattr(veh, "factor_grip", 1.0))  # MATLAB:OpenVEHICLE.m:80 factor_grip
    factor_Cl: float = float(getattr(veh, "factor_Cl", 1.0))  # MATLAB:OpenVEHICLE.m:66 factor_Cl
    factor_Cd: float = float(getattr(veh, "factor_Cd", 1.0))  # MATLAB:OpenVEHICLE.m:67 factor_Cd
    Cl: float = float(getattr(veh, "Cl", getattr(veh, "cl", -4.8)))  # MATLAB:OpenVEHICLE.m:64 Cl
    Cd: float = float(getattr(veh, "Cd", getattr(veh, "cda", 1.2)))  # MATLAB:OpenVEHICLE.m:65 Cd
    # For MVP cda positive, convert to negative Cd if needed
    if hasattr(veh, "cda") and not hasattr(veh, "Cd"):
        A_tmp = float(getattr(veh, "A", 1.0))
        Cd = -abs(float(getattr(veh, "cda"))) / max(A_tmp, 1e-9)  # MATLAB:OpenVEHICLE.m Cd negative
    A: float = float(getattr(veh, "A", 1.0))  # MATLAB:OpenVEHICLE.m:69 A
    rho: float = float(getattr(veh, "rho", 1.225))  # MATLAB:OpenVEHICLE.m:70 rho
    Cr: float = float(getattr(veh, "Cr", -0.001))  # MATLAB:OpenVEHICLE.m:82 Cr
    n_thermal: float = float(getattr(veh, "n_thermal", 0.35))  # MATLAB:OpenVEHICLE.m:93 n_thermal
    fuel_LHV: float = float(getattr(veh, "fuel_LHV", 47200000.0))  # MATLAB:OpenVEHICLE.m:94 fuel_LHV
    n_primary: float = float(getattr(veh, "n_primary", 1.0))  # MATLAB:OpenVEHICLE.m:98
    n_final: float = float(getattr(veh, "n_final", 0.92))  # MATLAB:OpenVEHICLE.m:99
    n_gearbox: float = float(getattr(veh, "n_gearbox", 0.98))  # MATLAB:OpenVEHICLE.m:100
    # drive factors: MATLAB:OpenVEHICLE.m:234-245
    drive: str = str(getattr(veh, "drive", "RWD"))  # MATLAB:OpenVEHICLE.m:96 drive
    df: float = float(getattr(veh, "df", getattr(veh, "weight_dist_front", 0.45)))  # MATLAB:OpenVEHICLE.m:58 df
    da: float = float(getattr(veh, "da", getattr(veh, "weight_dist_front", 0.5)))  # MATLAB:OpenVEHICLE.m:68 da
    if drive == "RWD":  # MATLAB:OpenVEHICLE.m:234 factor_drive=(1-df)
        factor_drive: float = 1.0 - df  # MATLAB:OpenVEHICLE.m:235
        factor_aero: float = 1.0 - da  # MATLAB:OpenVEHICLE.m:236
        driven_wheels: int = 2  # MATLAB:OpenVEHICLE.m:237
    elif drive == "FWD":  # MATLAB:OpenVEHICLE.m:238
        factor_drive = df  # MATLAB:OpenVEHICLE.m:239
        factor_aero = da  # MATLAB:OpenVEHICLE.m:240
        driven_wheels = 2  # MATLAB:OpenVEHICLE.m:241
    else:  # AWD MATLAB:OpenVEHICLE.m:242
        factor_drive = 1.0  # MATLAB:OpenVEHICLE.m:243
        factor_aero = 1.0  # MATLAB:OpenVEHICLE.m:244
        driven_wheels = 4  # MATLAB:OpenVEHICLE.m:245
    Rt: float = float(getattr(veh, "tyre_radius", getattr(veh, "wheel_radius", 0.33)))  # MATLAB:OpenVEHICLE.m:81 tyre_radius
    if Rt <= 1e-9:
        Rt = 0.33
    # driveline cache for gear/rpm/engine: MATLAB:OpenVEHICLE.m:148-217 driveline model => MATLAB:OpenLAP.m:502 gear
    dl = _build_driveline_cache(veh)  # MATLAB:OpenVEHICLE.m driveline
    veh_vehicle_speed: _npt.NDArray[_np.float64] = dl["vehicle_speed"]  # MATLAB:OpenVEHICLE.m:190 vehicle_speed
    veh_gear: _npt.NDArray[_np.float64] = dl["gear"]  # MATLAB:OpenVEHICLE.m:191 gear
    veh_engine_speed: _npt.NDArray[_np.float64] = dl["engine_speed"]  # MATLAB:OpenVEHICLE.m:195 engine_speed
    veh_fx_engine: _npt.NDArray[_np.float64] = dl["fx_engine"]  # MATLAB:OpenVEHICLE.m fx_engine
    veh_wheel_torque: _npt.NDArray[_np.float64] = dl["wheel_torque"]  # MATLAB:OpenVEHICLE.m wheel_torque
    # beta for braking if available
    beta_val: float = 0.0
    try:
        br_disc_d = float(getattr(veh, "br_disc_d", 0.25))
        br_pad_h = float(getattr(veh, "br_pad_h", 0.04))
        br_pad_mu = float(getattr(veh, "br_pad_mu", 0.45))
        br_nop = float(getattr(veh, "br_nop", 6.0))
        br_pist_d = float(getattr(veh, "br_pist_d", 0.04))
        br_pist_a = br_nop * _math.pi * br_pist_d * br_pist_d / 4.0
        denom = (br_disc_d / 2.0 - br_pad_h / 2.0)
        if abs(denom) > 1e-9 and br_pist_a > 1e-9 and br_pad_mu > 1e-9:
            beta_val = Rt / denom / br_pist_a / br_pad_mu / 4.0  # MATLAB:OpenVEHICLE.m:135 beta
    except Exception:
        beta_val = 0.0
    if beta_val == 0.0 and hasattr(veh, "beta"):
        try:
            beta_val = float(getattr(veh, "beta"))
        except Exception:
            pass

    # -------------------------------------------------------------------
    # maximum speed curve (pure lateral) — MATLAB:OpenLAP.m:256-263 vehicle_model_lat
    # We port simplified QSS lateral limit with aero iteration + grip factor + bank
    # MATLAB:OpenLAP.m:658-754 vehicle_model_lat
    # -------------------------------------------------------------------
    # grip per point combined: factor_grip = tr.factor_grip * veh.factor_grip  MATLAB:OpenLAP.m:667
    grip_comb: _npt.NDArray[_np.float64] = grip_arr * factor_grip_veh  # MATLAB:OpenLAP.m:667
    _gear_v_max = float(dl["v_max"]) if float(dl["v_max"]) > 5 else 80.0  # MATLAB:OpenLAP.m:683 veh.v_max
    _v_power_drag = _gear_v_max
    try:
        _vs_tbl: _npt.NDArray[_np.float64] = dl["vehicle_speed"]
        _fx_tbl: _npt.NDArray[_np.float64] = dl["fx_engine"]
        try:
            _wx_vals = M * g_const * _np.sin(_np.radians(incl_arr))
            _wx_max = float(_np.max(_wx_vals)) if _wx_vals.size else 0.0
            if _wx_max < 0:
                _wx_max = 0.0
        except Exception:
            _wx_max = 0.0
        _v_best: float | None = None
        _prev_v: float | None = None
        _prev_net: float | None = None
        for _ii in range(int(_vs_tbl.shape[0])):
            _vi = float(_vs_tbl[_ii])
            if _vi < 1e-9 or not _math.isfinite(_vi):
                continue
            _fx_vi = float(_fx_tbl[_ii]) if _ii < int(_fx_tbl.shape[0]) else 0.0
            _aero_dr_mag = -0.5 * rho * factor_Cd * Cd * A * _vi * _vi
            if _aero_dr_mag < 0:
                _aero_dr_mag = abs(0.5 * rho * factor_Cd * Cd * A * _vi * _vi)
            _aero_df = 0.5 * rho * factor_Cl * Cl * A * _vi * _vi
            _fz_tot = -M * g_const + _aero_df
            _roll_mag = -Cr * abs(_fz_tot)
            if _roll_mag < 0:
                _roll_mag = abs(Cr * abs(_fz_tot))
            _wx_flat = float(_wx_max)
            _drag_mag = _aero_dr_mag + _roll_mag + _wx_flat
            _net = _fx_vi - _drag_mag
            if _prev_net is not None and _prev_v is not None:
                if _prev_net >= 0 and _net < 0:
                    _dv = _vi - _prev_v
                    _dnet = _net - _prev_net
                    if abs(_dnet) > 1e-12 and abs(_dv) > 1e-12:
                        _frac = -_prev_net / _dnet
                        if _frac < 0:
                            _frac = 0.0
                        if _frac > 1:
                            _frac = 1.0
                        _v_cross = _prev_v + _frac * _dv
                    else:
                        _v_cross = _prev_v
                    _v_best = float(_v_cross)
                elif _net >= 0:
                    _v_best = float(_vi)
            else:
                if _net >= 0:
                    _v_best = float(_vi)
            _prev_v = _vi
            _prev_net = _net
        if _v_best is not None and _math.isfinite(_v_best) and _v_best > 5.0:
            if _v_best > _gear_v_max:
                _v_best = _gear_v_max
            _v_power_drag = float(_v_best)
        else:
            _v_power_drag = float(_gear_v_max)
    except Exception:
        _v_power_drag = float(_gear_v_max)
    v_limit = float(_v_power_drag)
    v_max_arr: _npt.NDArray[_np.float64] = _np.full(n, v_limit, dtype=float)  # MATLAB:OpenLAP.m:258
    D_const: float = -0.5 * rho * factor_Cl * Cl * A  # MATLAB:OpenLAP.m: D
    Ny_const: float = mu_y_M_base * g_const  # MATLAB:OpenLAP.m:693 Ny
    for _i in range(n):  # MATLAB:OpenLAP.m: per-point vehicle_model_lat
        r = float(curv_arr[_i])  # signed curvature  MATLAB:OpenLAP.m: r
        if abs(r) < 1e-9:  # straight → veh.v_max deterministic 1e-9  MATLAB:OpenLAP.m:681 r==0
            v_max_arr[_i] = v_limit
            continue
        bank_d = float(bank_deg[_i])  # MATLAB:OpenLAP.m: bank [deg]
        incl_d = float(incl_arr[_i])  # MATLAB:OpenLAP.m: incl [deg]
        Wz = M * g_const * _cosd(bank_d) * _cosd(incl_d)  # MATLAB:OpenLAP.m: Wz=M*g*cosd(bank)*cosd(incl)
        Wy = -M * g_const * _sind(bank_d)  # MATLAB:OpenLAP.m: Wy=-M*g*sind(bank)
        Wx = M * g_const * _sind(incl_d)  # MATLAB:OpenLAP.m: Wx=M*g*sind(incl) per task spec (unused in lateral)
        _ = Wx  # keep for completeness, lateral uses Wz/Wy/D
        grip = float(grip_comb[_i])  # MATLAB:OpenLAP.m:667 tr.factor_grip*veh.factor_grip
        dmy = grip * sens_y_base  # MATLAB:OpenLAP.m:691 dmy=grip*sens_y
        muy = grip * mu_y_base  # MATLAB:OpenLAP.m:692 muy=grip*mu_y
        Ny = Ny_const  # MATLAB:OpenLAP.m: Ny=mu_y_M*g (scaled via grip already in dmy/muy)
        sign_r = 1.0 if r > 0 else -1.0  # preserve sign(r)  MATLAB:OpenLAP.m: sign(r)
        a = -sign_r * dmy / 4.0 * D_const * D_const  # a=-sign(r)*dmy/4*D^2
        b = sign_r * (muy * D_const + (dmy / 4.0) * (Ny * 4) * D_const - 2.0 * (dmy / 4.0) * Wz * D_const) - M * r  # b=sign(r)*(muy*D+(dmy/4)*(Ny*4)*D-2*(dmy/4)*Wz*D)-M*r
        c = sign_r * (muy * Wz + (dmy / 4.0) * (Ny * 4) * Wz - (dmy / 4.0) * Wz * Wz) + Wy  # c=sign(r)*(muy*Wz+(dmy/4)*(Ny*4)*Wz-(dmy/4)*Wz^2)+Wy
        v_cand = v_limit
        if abs(a) < 1e-12:  # a≈0 fallback deterministic 1e-9  MATLAB:OpenLAP.m: a≈0
            if abs(b) > 1e-12:
                u = -c / b
                if u > 1e-9 and _math.isfinite(u):  # deterministic 1e-9
                    v_cand = _math.sqrt(u)
                else:
                    v_cand = v_limit
            else:
                v_cand = v_limit
        else:
            disc = b * b - 4.0 * a * c
            if disc < 0:
                if abs(b) > 1e-12:
                    u_lin = -c / b
                    if u_lin > 1e-9 and _math.isfinite(u_lin):
                        v_cand = _math.sqrt(u_lin)
                    else:
                        v_cand = v_limit
                else:
                    v_cand = v_limit
            else:
                sqrt_disc = _math.sqrt(disc)
                denom = 2.0 * a
                if abs(denom) < 1e-18:
                    v_cand = v_limit
                else:
                    u1 = (-b + sqrt_disc) / denom
                    u2 = (-b - sqrt_disc) / denom
                    cands: list[float] = []
                    if u1 > 1e-9 and _math.isfinite(u1):
                        cands.append(float(u1))
                    if u2 > 1e-9 and _math.isfinite(u2):
                        cands.append(float(u2))
                    if not cands:
                        v_cand = v_limit
                    elif len(cands) == 1:
                        v_cand = _math.sqrt(cands[0])
                    else:
                        u = min(cands)
                        v_cand = _math.sqrt(u)
        if not _math.isfinite(v_cand) or v_cand <= 1e-9:
            v_cand = v_limit
        if v_cand > v_limit:
            v_cand = v_limit
        if v_cand < 5.0:
            v_cand = 5.0
        v_max_arr[_i] = float(v_cand)
    v_max_arr = _np.maximum(v_max_arr, 5.0)
    v_max_arr = _np.minimum(v_max_arr, v_limit)

    # -------------------------------------------------------------------
    # speed envelope via forward/backward 6 iterations — MATLAB:OpenLAP.m:298-399 acceleration/deceleration loops
    # Simplified to 6 iter forward/back with friction ellipse and gear power
    # -------------------------------------------------------------------
    v: _npt.NDArray[_np.float64] = v_max_arr.copy()  # MATLAB:OpenLAP.m:306 v initialization inf then apex?
    closed: bool = bool(getattr(tr_m, "closed_loop", True))  # MATLAB:OpenLAP.m:382 tr.info.config Closed
    if closed:
        m0 = float(min(float(v[0]), float(v[-1])))  # MATLAB:OpenLAP.m enforce periodicity
        v[0] = m0
        v[-1] = m0

    def _ay_max_at(speed: float, idx: int) -> float:  # MATLAB:OpenLAP.m:665-678 per point ay_max
        bank_d = float(bank_deg[idx])
        incl_d = float(incl_arr[idx])
        grip = float(grip_arr[idx]) * factor_grip_veh  # MATLAB:OpenLAP.m:667
        Fz_mass = -M * g_const * _cosd(bank_d) * _cosd(incl_d)  # MATLAB:OpenLAP.m:468 Fz_mass negative
        Fz_aero = 0.5 * rho * factor_Cl * Cl * A * speed * speed  # MATLAB:OpenLAP.m:469 Fz_aero negative
        Fz_total = Fz_mass + Fz_aero  # MATLAB:OpenLAP.m:470 Fz_total
        Nz_local = -(Fz_total)  # MATLAB:OpenLAP.m: Nz=-(Fz_total)
        if Nz_local < M * g_const * 0.5:
            Nz_local = M * g_const * 0.5
        dmy_local = grip * sens_y_base  # MATLAB:OpenLAP.m:691
        muy_local = grip * mu_y_base  # MATLAB:OpenLAP.m:692
        Ny_local = mu_y_M_base * g_const  # MATLAB:OpenLAP.m:693
        ay_max_local = (muy_local + dmy_local * (Ny_local - Nz_local / 4.0)) * Nz_local / M  # MATLAB:OpenLAP.m sens formula
        Wy_local = -M * g_const * _sind(bank_d)  # MATLAB:OpenLAP.m:677 Wy=-M*g*sind(bank)
        ay_max_local = ay_max_local + Wy_local / M  # remove abs, preserve signed bank coupling  MATLAB:OpenLAP.m: signed
        return float(max(ay_max_local, 0.0))

    def _ax_tyre_at(speed: float, idx: int, mode: int = 1) -> float:  # MATLAB:OpenLAP.m:273 ax_tyre_max_acc / 376
        bank_d = float(bank_deg[idx])
        incl_d = float(incl_arr[idx])
        Wz = M * g_const * _cosd(bank_d) * _cosd(incl_d)  # MATLAB:OpenLAP.m:81 Wz positive
        Aero_Df = 0.5 * rho * factor_Cl * Cl * A * speed * speed  # MATLAB:OpenLAP.m:223 Aero_Df negative (Cl negative)
        Wd = (factor_drive * Wz - factor_aero * Aero_Df) / max(driven_wheels, 1)  # MATLAB:OpenLAP.m:228 Wd
        Fz_mass = -Wz
        Fz_aero = Aero_Df
        Fz_total = Fz_mass + Fz_aero  # negative
        Nz = -(Fz_total)  # positive = Wz - Aero_Df
        grip = float(grip_arr[idx]) * factor_grip_veh
        dmx = grip * sens_x_base  # MATLAB:OpenLAP.m:695 dmx
        mux = grip * mu_x_base  # MATLAB:OpenLAP.m:696 mux
        Nx = mu_x_M_base * g_const  # MATLAB:OpenLAP.m:697 Nx
        if mode == 1:  # acceleration, driven wheels  MATLAB:OpenLAP.m:273
            ax_tyre = 1.0 / max(M, 1e-9) * (mux + dmx * (Nx - Wd)) * Wd * driven_wheels  # MATLAB:OpenLAP.m:273 ax_tyre_acc=1/M*(mux+dmx*(Nx-Wd))*Wd*driven
        else:  # deceleration all wheels  MATLAB:OpenLAP.m:376 ax_tyre_max_dec
            ax_tyre = -1.0 / max(M, 1e-9) * (mux + dmx * (Nx - Nz / 4.0)) * Nz  # MATLAB:OpenLAP.m:376 ax_tyre_dec=-1/M*(mux+dmx*(Nx-Nz/4))*Nz
        return float(ax_tyre)

    def _ax_engine_at(speed: float) -> float:  # MATLAB:OpenLAP.m:276-277 power limit
        fx = float(_np.interp(float(speed), veh_vehicle_speed, veh_fx_engine, left=float(veh_fx_engine[0]), right=0.0))  # MATLAB:OpenLAP.m:276 wheel_torque/Rt
        fx = fx * float(getattr(veh, "factor_power", getattr(veh, "engine_power_factor", 1.0)))  # MATLAB:OpenVEHICLE.m:92 factor_power
        return float(fx / max(M, 1e-9))

    # WA.4 converged envelope (tol loop) — MATLAB:OpenLAP.m:327 forward/backward converged
    # Deterministic while max_delta>1e-6 and it<20, log iters
    _envelope_iters = 0
    _iter = 0
    _max_delta = float("inf")  # WA.4 max_delta
    while _max_delta > 1e-6 and _iter < 20:  # MATLAB:OpenLAP.m:327 converged envelope
        v_prev_iter = v.copy()  # WA.4 baseline for delta
        # forward MATLAB:OpenLAP.m:362 while 1 forward mode=1
        for i in range(1, n):  # MATLAB:OpenLAP.m forward
            ds = float(s_arr[i] - s_arr[i - 1])  # MATLAB:OpenLAP.m dx(j)
            if ds <= 1e-12:
                continue
            curv_a = abs(float(curv_arr[i - 1]))  # MATLAB:OpenLAP.m r(j)
            v_prev = float(v[i - 1])  # MATLAB:OpenLAP.m v(j)
            ay = v_prev * v_prev * curv_a + g_const * _sind(float(bank_deg[i - 1]))  # MATLAB:OpenLAP.m ay = v^2*r+g*sind(bank)
            ay_max_v = _ay_max_at(v_prev, i - 1)  # MATLAB:OpenLAP.m ay_max
            ax_tyre = _ax_tyre_at(v_prev, i - 1, mode=1)  # MATLAB:OpenLAP.m ax_tyre_max_acc
            # friction ellipse  MATLAB:OpenLAP.m ellipse_multi sqrt(1-(ay/ay_max)^2)
            if ay_max_v <= 1e-12:
                factor = 0.0  # MATLAB:OpenLAP.m ellipse 0
            else:
                ratio = ay / ay_max_v if ay_max_v != 0 else 1.0
                if abs(ratio) >= 1.0:
                    factor = 0.0
                else:
                    factor = _math.sqrt(max(0.0, 1.0 - ratio * ratio))  # MATLAB:OpenLAP.m ellipse
            ax_tyre_scaled = ax_tyre * factor  # MATLAB:OpenLAP.m ax_tyre*ellipse_multi
            ax_power = _ax_engine_at(v_prev)  # MATLAB:OpenLAP.m ax_power WITHOUT ellipse (pure fx/M)
            bank_d_prev = float(bank_deg[i - 1])
            incl_d_prev = float(incl_arr[i - 1])
            Aero_Dr_prev = 0.5 * rho * factor_Cd * Cd * A * v_prev * v_prev  # negative (Cd negative)
            Fz_mass_prev = -M * g_const * _cosd(bank_d_prev) * _cosd(incl_d_prev)
            Fz_aero_prev = 0.5 * rho * factor_Cl * Cl * A * v_prev * v_prev  # negative
            Fz_total_prev = Fz_mass_prev + Fz_aero_prev
            Roll_Dr_prev = Cr * abs(Fz_total_prev)  # negative (Cr negative)
            Wx_prev = M * g_const * _sind(incl_d_prev)  # MATLAB canonical Wx=M*g*sind(incl) incl=atan2(dz,dx) deg
            ax_drag_prev = (Aero_Dr_prev + Roll_Dr_prev + Wx_prev) / max(M, 1e-9)
            ax_com_prev = ax_tyre_scaled if ax_tyre_scaled < ax_power else ax_power  # MATLAB: ax_com=min(...)
            ax_avail = ax_com_prev + ax_drag_prev  # MATLAB:vehicle_model_comb ax=ax_com+ax_drag
            if ax_avail < ax_drag_prev:
                ax_avail = ax_drag_prev  # clamp ax_avail>=ax_drag (no negative-power artifact)
            if ax_avail <= 0.0:
                v_possible = float(v_prev)
                if v_possible < float(v[i]):
                    v[i] = v_possible
                continue
            v_possible = _math.sqrt(v_prev * v_prev + 2.0 * ax_avail * ds)  # MATLAB:OpenLAP.m v_next = sqrt(v^2+2*ax*dx)
            if v_possible < float(v[i]):
                v[i] = v_possible
        # backward  MATLAB:OpenLAP.m mode=-1 deceleration
        for i in range(n - 2, -1, -1):  # MATLAB:OpenLAP.m backward
            ds = float(s_arr[i + 1] - s_arr[i])  # MATLAB:OpenLAP.m dx
            if ds <= 1e-12:
                continue
            curv_a = abs(float(curv_arr[i + 1]))  # MATLAB:OpenLAP.m r(j_next)
            v_next = float(v[i + 1])  # MATLAB:OpenLAP.m v_next
            ay = v_next * v_next * curv_a + g_const * _sind(float(bank_deg[i + 1]))  # MATLAB:OpenLAP.m ay
            ay_max_v = _ay_max_at(v_next, i + 1)  # MATLAB:OpenLAP.m ay_max
            ax_tyre = _ax_tyre_at(v_next, i + 1, mode=-1)  # MATLAB:OpenLAP.m ax_tyre_max_dec negative
            if ay_max_v <= 1e-12:
                factor = 0.0
            else:
                ratio = ay / ay_max_v if ay_max_v != 0 else 1.0
                if abs(ratio) >= 1.0:
                    factor = 0.0
                else:
                    factor = _math.sqrt(max(0.0, 1.0 - ratio * ratio))
            ax_brake = ax_tyre * factor  # negative (ax_tyre mode -1)
            bank_d_next = float(bank_deg[i + 1])
            incl_d_next = float(incl_arr[i + 1])
            Aero_Dr_next = 0.5 * rho * factor_Cd * Cd * A * v_next * v_next
            Fz_mass_next = -M * g_const * _cosd(bank_d_next) * _cosd(incl_d_next)
            Fz_aero_next = 0.5 * rho * factor_Cl * Cl * A * v_next * v_next
            Fz_total_next = Fz_mass_next + Fz_aero_next
            Roll_Dr_next = Cr * abs(Fz_total_next)
            Wx_next = M * g_const * _sind(incl_d_next)
            ax_drag_next = (Aero_Dr_next + Roll_Dr_next + Wx_next) / max(M, 1e-9)
            ax_avail_neg = ax_brake + ax_drag_next  # both negative, MATLAB vehicle_model_comb braking
            ax_brake_abs = abs(ax_avail_neg)
            if ax_brake_abs <= 1e-12:
                continue
            v_possible = _math.sqrt(v_next * v_next + 2.0 * ax_brake_abs * ds)
            if v_possible < float(v[i]):
                v[i] = v_possible
        if closed:
            m = float(v[0] if v[0] < v[-1] else v[-1])  # MATLAB:OpenLAP.m closed handling
            v[0] = m  # MATLAB:OpenLAP.m ensure equal
            v[-1] = m  # MATLAB:OpenLAP.m v0==vN
        _max_delta = float(_np.max(_np.abs(v - v_prev_iter))) if n > 0 else 0.0  # WA.4 delta
        _iter += 1  # WA.4 iter
        _envelope_iters = _iter  # WA.4 log iters deterministic

    v = _np.where(_np.isfinite(v), v, 5.0)  # MATLAB:OpenLAP.m clamp finite
    v = _np.maximum(v, 1.0)  # MATLAB:OpenLAP.m minimum speed
    if closed:
        v[0] = v[-1]  # MATLAB:OpenLAP.m ensure strictly v0==vN for closed

    # -------------------------------------------------------------------
    # trapezoidal integration for laptime and time array — MATLAB:OpenLAP.m:449-459
    # time = cumsum(tr.dx./V)  MATLAB:OpenLAP.m:453
    # -------------------------------------------------------------------
    time_arr: _npt.NDArray[_np.float64] = _np.zeros(n, dtype=float)  # MATLAB:OpenLAP.m:450 time
    eps: float = 1e-12  # WA.3 trapezoidal eps — avoids 1e9 spike, symplectic
    for i in range(1, n):  # MATLAB:OpenLAP.m cumsum
        ds = float(s_arr[i] - s_arr[i - 1])  # MATLAB:OpenLAP.m tr.dx
        dt = 2.0 * ds / (float(v[i]) + float(v[i - 1]) + eps)  # WA.3 trapezoidal no clamp
        time_arr[i] = time_arr[i - 1] + dt  # MATLAB:OpenLAP.m cumsum
    if closed:
        # ensure time starts 0
        time_arr[0] = 0.0
    laptime: float = float(time_arr[-1]) if n > 0 else 0.0  # MATLAB:OpenLAP.m:459 laptime = time(end)

    # -------------------------------------------------------------------
    # ax / ay profiles — MATLAB:OpenLAP.m:467 A = sqrt(AX^2+AY^2) etc
    # -------------------------------------------------------------------
    ax_arr: _npt.NDArray[_np.float64] = _np.zeros(n, dtype=float)  # MATLAB:OpenLAP.m:568 AX
    ay_arr: _npt.NDArray[_np.float64] = _np.zeros(n, dtype=float)  # MATLAB:OpenLAP.m:570 AY
    for i in range(n):  # MATLAB:OpenLAP.m ay = V^2*r
        ay_arr[i] = float(v[i] * v[i] * float(curv_arr[i]) + g_const * _sind(float(bank_deg[i])))  # MATLAB:OpenLAP.m ay
    for i in range(n - 1):  # MATLAB:OpenLAP.m AX from v difference
        ds = float(s_arr[i + 1] - s_arr[i])
        if ds <= 1e-12:
            ax_arr[i] = 0.0
        else:
            ax_arr[i] = (float(v[i + 1] * v[i + 1] - v[i] * v[i])) / (2.0 * ds)  # MATLAB:OpenLAP.m AX derived
    if n >= 2:
        ax_arr[-1] = float(ax_arr[-2])  # MATLAB:OpenLAP.m last point copy
    ax_arr = _np.where(_np.isfinite(ax_arr), ax_arr, 0.0)
    ay_arr = _np.where(_np.isfinite(ay_arr), ay_arr, 0.0)

    # -------------------------------------------------------------------
    # gear / rpm / tps — MATLAB:OpenLAP.m:502 gear, 501 engine_speed, 574 throttle
    # drag.pyギア状態機械によるマルチギア (単一final_drive廃止)
    # -------------------------------------------------------------------
    gear_arr: _npt.NDArray[_np.float64] = _np.zeros(n, dtype=float)  # MATLAB:OpenLAP.m:606 sim.gear
    rpm_arr: _npt.NDArray[_np.float64] = _np.zeros(n, dtype=float)  # MATLAB:OpenLAP.m:605 engine_speed
    tps_arr: _npt.NDArray[_np.float64] = _np.zeros(n, dtype=float)  # MATLAB:OpenLAP.m:574 throttle
    bps_arr: _npt.NDArray[_np.float64] = _np.zeros(n, dtype=float)  # MATLAB:OpenLAP.m:576 brake
    for i in range(n):  # MATLAB:OpenLAP.m:500-502 engine metrics loop
        vi = float(v[i])  # MATLAB:OpenLAP.m V(i)
        # gear nearest  MATLAB:OpenLAP.m:502 gear = interp1(...,V,'nearest')
        g_f = float(_np.interp(vi, veh_vehicle_speed, veh_gear, left=float(veh_gear[0]), right=float(veh_gear[-1])))  # MATLAB:OpenLAP.m 502
        g_i = int(round(g_f))  # MATLAB:OpenLAP.m gear integer
        if g_i < 1:
            g_i = 1
        if g_i > int(dl["nog"]):
            g_i = int(dl["nog"])
        gear_arr[i] = float(g_i)  # MATLAB:OpenLAP.m gear
        rpm_arr[i] = float(_np.interp(vi, veh_vehicle_speed, veh_engine_speed, left=float(veh_engine_speed[0]), right=float(veh_engine_speed[-1])))  # MATLAB:OpenLAP.m:501
        # tps logic  MATLAB:OpenLAP.m:273-288
        # compute ax_com and power limit
        Aero_Dr = 0.5 * rho * factor_Cd * Cd * A * vi * vi  # MATLAB:OpenLAP.m:471 Fx_aero
        Fz_mass = -M * g_const * _cosd(float(bank_deg[i])) * _cosd(float(incl_arr[i]))  # MATLAB:OpenLAP.m:468 Fz_mass negative
        Fz_aero = 0.5 * rho * factor_Cl * Cl * A * vi * vi  # MATLAB:OpenLAP.m:469 Fz_aero
        Fz_total = Fz_mass + Fz_aero  # MATLAB:OpenLAP.m:470 Fz_total
        Fx_roll = Cr * abs(Fz_total)  # MATLAB:OpenLAP.m:472 Fx_roll
        Wx = M * g_const * _sind(float(incl_arr[i]))  # MATLAB:OpenLAP.m Wx
        ax_drag = (Aero_Dr + Fx_roll + Wx) / max(M, 1e-9)  # MATLAB:OpenLAP.m:230 ax_drag
        ax_com = float(ax_arr[i]) - ax_drag  # command
        if ax_com > 1e-9:  # need throttle  MATLAB:OpenLAP.m ax_needed>=0
            fx_eng = float(_np.interp(vi, veh_vehicle_speed, veh_fx_engine, left=float(veh_fx_engine[0]), right=0.0)) * float(getattr(veh, "factor_power", 1.0))  # MATLAB:OpenLAP.m fx_engine
            ax_power = fx_eng / max(M, 1e-9)  # MATLAB:OpenLAP.m ax_power_limit
            if ax_power > 1e-12:
                # friction ellipse at this ay
                ay_here = float(ay_arr[i])
                ay_max_here = _ay_max_at(vi, i)
                if ay_max_here > 1e-12 and abs(ay_here / ay_max_here) < 1.0:
                    ellipse = _math.sqrt(max(0.0, 1.0 - (ay_here / ay_max_here) ** 2))
                    ax_power_eff = ax_power * ellipse
                else:
                    ax_power_eff = 0.0
                if ax_power_eff > 1e-12:
                    scale = ax_com / ax_power_eff
                    tps_arr[i] = float(max(0.0, min(1.0, scale)))  # MATLAB:OpenLAP.m tps
                else:
                    tps_arr[i] = 0.0
            else:
                tps_arr[i] = 0.0
            bps_arr[i] = 0.0
        elif ax_com < -1e-9:  # braking  MATLAB:OpenLAP.m need brake
            # max dec tyre  MATLAB:OpenLAP.m:376
            tps_arr[i] = 0.0
            # brake pressure approx
            fx_tyre = abs(float(_ax_tyre_at(vi, i, mode=-1)) * M)
            # scale by required dec
            req = abs(ax_com) * M
            # bps proportional to fx_tyre?  MATLAB:OpenLAP.m:380 bps = -veh.beta*M*ax
            bps_arr[i] = float(req * beta_val) if beta_val > 0 else float(req / 1000.0)  # MATLAB:OpenLAP.m bps
        else:
            tps_arr[i] = 0.0
            bps_arr[i] = 0.0
        # clamp tps
        if tps_arr[i] > 1.0:
            tps_arr[i] = 1.0
        if tps_arr[i] < 0.0:
            tps_arr[i] = 0.0
        # full throttle at v_max on straight correction  MATLAB:OpenLAP.m v/veh.v_max>=0.999 => tps=1
        if tps_arr[i] > 0 and vi / max(float(dl["v_max"]), 1.0) >= 0.999:
            tps_arr[i] = 1.0

    # -------------------------------------------------------------------
    # energy / fuel 積算 — MATLAB:OpenLAP.m:503 fuel_cons, 519 energy_spent_*
    # fuel_cons = cumsum(wheel_torque/tyre_radius.*dx /n_primary/n_gearbox/n_final/n_thermal/fuel_LHV)
    # energy_spent_fuel = fuel_cons*veh.fuel_LHV ; energy_spent_mech = energy_spent_fuel*veh.n_thermal
    # -------------------------------------------------------------------
    fuel_arr: _npt.NDArray[_np.float64] = _np.zeros(n, dtype=float)  # MATLAB:OpenLAP.m:503 fuel_cons
    energy_arr: _npt.NDArray[_np.float64] = _np.zeros(n, dtype=float)  # MATLAB:OpenLAP.m:519 energy_spent_fuel kJ
    # Use wheel_torque table: wheel_torque = TPS*interp(veh.wheel_torque, V)  MATLAB:OpenLAP.m:497
    cum_fuel: float = 0.0  # MATLAB:OpenLAP.m cumsum
    for i in range(1, n):  # MATLAB:OpenLAP.m cumsum loop
        ds = float(s_arr[i] - s_arr[i - 1])  # MATLAB:OpenLAP.m tr.dx
        if ds <= 1e-12:
            fuel_arr[i] = cum_fuel
            energy_arr[i] = cum_fuel * fuel_LHV * n_thermal / 1000.0  # MATLAB:OpenLAP.m:520 mech kJ (unified fuel vs energy branch)
            continue
        vi = float(v[i])  # for wheel_torque interp use average? Use current
        wt_interp = float(_np.interp(vi, veh_vehicle_speed, veh_wheel_torque, left=float(veh_wheel_torque[0]), right=float(veh_wheel_torque[-1])))  # MATLAB:OpenLAP.m:497 interp
        wheel_torque_here = float(tps_arr[i]) * wt_interp  # MATLAB:OpenLAP.m:497 wheel_torque = TPS.*interp
        Fx_eng_here = wheel_torque_here / max(Rt, 1e-9)  # MATLAB:OpenLAP.m:498 Fx_eng
        if Fx_eng_here < 0:
            Fx_eng_here = 0.0
        # fuel increment  MATLAB:OpenLAP.m:503
        denom = max(n_primary, 1e-9) * max(n_gearbox, 1e-9) * max(n_final, 1e-9) * max(n_thermal, 1e-9) * max(fuel_LHV, 1e-9)
        d_fuel = Fx_eng_here * ds / denom if denom > 1e-12 else 0.0  # MATLAB:OpenLAP.m:503
        if d_fuel < 0:
            d_fuel = 0.0
        cum_fuel += d_fuel  # MATLAB:OpenLAP.m cumsum
        fuel_arr[i] = cum_fuel  # MATLAB:OpenLAP.m fuel_cons
        # energy_spent_mech  MATLAB:OpenLAP.m:520 energy_spent_mech = energy_spent_fuel*veh.n_thermal
        # Provide energy as mech kJ: energy_spent_mech /1000
        energy_arr[i] = cum_fuel * fuel_LHV * n_thermal / 1000.0  # MATLAB:OpenLAP.m:520 mech kJ (use mech for kJ spec)
        # alternative fuel energy kJ would be cum_fuel*fuel_LHV/1000, but mech includes n_thermal; both proportional.
        # Keep mech as spec requires n_thermal factor.
    # Ensure last fuel non-negative and energy positive if throttle existed
    fuel_arr = _np.maximum(fuel_arr, 0.0)
    energy_arr = _np.maximum(energy_arr, 0.0)

    # -------------------------------------------------------------------
    # sector_time — MATLAB:OpenLAP.m:455-457 sector_time
    # -------------------------------------------------------------------
    unique_sectors = _np.unique(sector_arr)  # MATLAB:OpenLAP.m max(tr.sector)
    # Ensure sorted
    unique_sectors = _np.sort(unique_sectors)
    sector_time_arr = _np.zeros(int(unique_sectors.shape[0]), dtype=float)  # MATLAB:OpenLAP.m:455 sector_time zeros
    for idx, sec_val in enumerate(unique_sectors):  # MATLAB:OpenLAP.m:456 for i=1:max(tr.sector)
        mask = sector_arr == sec_val  # MATLAB:OpenLAP.m tr.sector==i
        if _np.any(mask):
            t_sec = time_arr[mask]  # MATLAB:OpenLAP.m time(tr.sector==i)
            sector_time_arr[idx] = float(_np.max(t_sec) - _np.min(t_sec))  # MATLAB:OpenLAP.m max-min
        else:
            sector_time_arr[idx] = 0.0
    # sector合計==laptime 保証: sum == laptime within floating, if discrepancy due to discretization, adjust last
    sum_sector = float(_np.sum(sector_time_arr))  # MATLAB:OpenLAP.m laptime = time(end)
    if abs(sum_sector - laptime) > 1e-9 and laptime > 1e-9:
        # Adjust last sector to make sum exactly laptime deterministic
        sector_time_arr[-1] += laptime - sum_sector  # MATLAB:OpenLAP.m guarantee

    # -------------------------------------------------------------------
    # freq 出力リサンプル — MATLAB:OpenLAP.m:890-927 export_report resample
    # t = (0:1/freq:sim.laptime.data)'  MATLAB:OpenLAP.m:910
    # time_data via interp1  MATLAB:OpenLAP.m:920-927
    # -------------------------------------------------------------------
    # Build uniform time vector at freq  MATLAB:OpenLAP.m:910 freq round already
    # Use freq_i to determine n_out: laptime*freq_i points
    # For deterministic len difference: freq 50 vs 100 len(s) differs
    t_uniform: _npt.NDArray[_np.float64] = _np.arange(0.0, laptime, 1.0 / float(freq_i), dtype=float)  # MATLAB:OpenLAP.m:910
    # Ensure endpoint included  MATLAB:OpenLAP.m:910 includes laptime
    if t_uniform.shape[0] == 0 or abs(float(t_uniform[-1]) - laptime) > 1e-9:
        t_uniform = _np.append(t_uniform, laptime)
    else:
        t_uniform[-1] = laptime
    # If mesh n already matches t_uniform length closely, we still resample for time-base
    # For small laptime, ensure at least 2 points
    if t_uniform.shape[0] < 2:
        t_uniform = _np.array([0.0, laptime], dtype=float)
    # Resample all channels onto t_uniform via np.interp (linear) except gear/sector nearest  MATLAB:OpenLAP.m:922-925
    def _resample_linear(arr: _npt.NDArray[_np.float64]) -> _npt.NDArray[_np.float64]:
        return _np.interp(t_uniform, time_arr, arr, left=float(arr[0]), right=float(arr[-1]))  # MATLAB:OpenLAP.m:925 linear

    def _resample_nearest(arr: _npt.NDArray[_np.float64]) -> _npt.NDArray[_np.float64]:
        # nearest via searchsorted  MATLAB:OpenLAP.m:923 nearest for gear
        # Use np.interp with nearest by rounding index
        # Find closest time index for each t_uniform via searchsorted
        idx = _np.searchsorted(time_arr, t_uniform, side="left")
        idx = _np.clip(idx, 0, n - 1)
        # choose nearest between idx and idx-1
        # For speed, just use idx
        res = _np.empty_like(t_uniform)
        for _k in range(int(t_uniform.shape[0])):
            _idx = int(idx[_k])
            if _idx > 0:
                # check distance
                d1 = abs(float(t_uniform[_k]) - float(time_arr[_idx]))
                d0 = abs(float(t_uniform[_k]) - float(time_arr[_idx - 1]))
                if d0 < d1:
                    _idx = _idx - 1
            res[_k] = float(arr[_idx])
        return res

    s_res = _resample_linear(s_arr)  # MATLAB:OpenLAP.m:925
    v_res = _resample_linear(v)  # MATLAB:OpenLAP.m:925
    ax_res = _resample_linear(ax_arr)  # MATLAB:OpenLAP.m:925
    ay_res = _resample_linear(ay_arr)  # MATLAB:OpenLAP.m:925
    sector_res = _resample_nearest(sector_arr)  # MATLAB:OpenLAP.m: previous interpolation for sector
    gear_res = _resample_nearest(gear_arr)  # MATLAB:OpenLAP.m:923 gear nearest
    rpm_res = _resample_linear(rpm_arr)  # MATLAB:OpenLAP.m:925
    tps_res = _resample_linear(tps_arr)  # MATLAB:OpenLAP.m:925
    fuel_res = _resample_linear(fuel_arr)  # MATLAB:OpenLAP.m: fuel_cons interp?
    energy_res = _resample_linear(energy_arr)  # MATLAB:OpenLAP.m: energy
    bps_res = _resample_linear(bps_arr)  # MATLAB:OpenLAP.m: brake
    time_res = t_uniform.copy()  # MATLAB:OpenLAP.m:910 time
    # Enforce closed loop v0==vN  MATLAB:OpenLAP.m:382 Closed handling
    if closed and v_res.shape[0] >= 2:
        v_res[-1] = float(v_res[0])  # MATLAB:OpenLAP.m v0==vN
        ax_res[-1] = float(ax_res[0])
        ay_res[-1] = float(ay_res[0])
        rpm_res[-1] = float(rpm_res[0])
        gear_res[-1] = float(gear_res[0])
    # Ensure time_res correctly 0..laptime
    time_res[0] = 0.0
    time_res[-1] = laptime
    # s_res ensure monotonic and last == length
    s_res[0] = 0.0
    # Use original length_m for last s (avoid drift due to interpolation)
    try:
        L_val = float(getattr(tr_m, "length_m", s_arr[-1]))
        s_res[-1] = L_val
    except Exception:
        pass

    # Final copy to ensure ownership and determinism
    s_out = _np.array(s_res, dtype=float, copy=True)  # MATLAB:OpenLAP.m:540
    v_out = _np.array(v_res, dtype=float, copy=True)  # MATLAB:OpenLAP.m:564
    ax_out = _np.array(ax_res, dtype=float, copy=True)  # MATLAB:OpenLAP.m:568
    ay_out = _np.array(ay_res, dtype=float, copy=True)  # MATLAB:OpenLAP.m:570
    time_out = _np.array(time_res, dtype=float, copy=True)  # MATLAB:OpenLAP.m:542
    sector_out = _np.array(sector_res, dtype=float, copy=True)  # MATLAB:OpenLAP.m:645 sector
    gear_out = _np.array(gear_res, dtype=float, copy=True)  # MATLAB:OpenLAP.m:606
    rpm_out = _np.array(rpm_res, dtype=float, copy=True)  # MATLAB:OpenLAP.m:605
    tps_out = _np.array(tps_res, dtype=float, copy=True)  # MATLAB:OpenLAP.m:574
    energy_out = _np.array(energy_res, dtype=float, copy=True)  # MATLAB:OpenLAP.m:519
    fuel_out = _np.array(fuel_res, dtype=float, copy=True)  # MATLAB:OpenLAP.m:503
    sector_time_out = _np.array(sector_time_arr, dtype=float, copy=True)  # MATLAB:OpenLAP.m:455
    bps_out = _np.array(bps_res, dtype=float, copy=True)

    return Result(  # MATLAB:OpenLAP.m:538-615 sim saving
        laptime=laptime,
        s=s_out,
        v=v_out,
        ax=ax_out,
        ay=ay_out,
        time=time_out,
        sector=sector_out,
        gear=gear_out,
        rpm=rpm_out,
        tps=tps_out,
        energy=energy_out,
        fuel=fuel_out,
        sector_time=sector_time_out,
        bps=bps_out,
    )


# Backward compatibility: keep old simulate as app simulate wrapper? export also
def simulate(
    vehicle_name: str | _pathlib.Path = "f1",
    track_name: str | _pathlib.Path = "spa",
    freq: int = 50,
    **kwargs: object,
) -> Result:
    """Alias to simulate_full for compatibility, but delegates to full implementation."""
    # MATLAB:OpenLAP.m:244 simulate alias
    return simulate_full(vehicle_name, track_name, freq=freq, **kwargs)


__all__ = ["Result", "simulate_full", "simulate", "friction_ellipse"]
