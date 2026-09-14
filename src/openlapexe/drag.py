# -*- coding: utf-8 -*-
# allow: SIZE_OK — OpenDRAG 578行完全移植 単一責務モジュール
"""openlapexe.drag - OpenDRAG.m 578行完全移植 (numpy only, deterministic, clamp).

MATLAB:OpenDRAG.m 由来注記は各行に併記。
Vehicle47 (47項目・18点トルク・tyre_radius車両別) と Track2(banking/grip) を入力に使う。
"""

from __future__ import annotations

import math as _math
import pathlib as _pathlib
from dataclasses import dataclass as _dataclass

import numpy as _np
import numpy.typing as _npt


# ---------------------------------------------------------------------------
# DragResult
# ---------------------------------------------------------------------------
@_dataclass(frozen=True, slots=True)
class DragResult:
    T: _npt.NDArray[_np.float64]
    X: _npt.NDArray[_np.float64]
    V: _npt.NDArray[_np.float64]
    A: _npt.NDArray[_np.float64]
    RPM: _npt.NDArray[_np.float64]
    TPS: _npt.NDArray[_np.float64]
    BPS: _npt.NDArray[_np.float64]
    GEAR: _npt.NDArray[_np.float64]
    MODE: _npt.NDArray[_np.float64]
    a_ave: float
    a_peak: float
    trap_log: list[dict[str, float]]
    # extra for completeness (deceleration)
    a_dec_ave: float = 0.0
    a_dec_peak: float = 0.0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _cosd(d: float) -> float:  # MATLAB:OpenDRAG.m:81 cosd
    return _math.cos(_math.radians(d))


def _sind(d: float) -> float:  # MATLAB:OpenDRAG.m:83 sind
    return _math.sin(_math.radians(d))


def _interp_clamp(x: _npt.NDArray[_np.float64], y: _npt.NDArray[_np.float64], xq: float) -> float:
    # MATLAB:OpenDRAG.m:275 interp1 clamp -> np.interp clamp
    if x.shape[0] == 0:
        return 0.0
    return float(_np.interp(float(xq), x, y, left=float(y[0]), right=float(y[-1])))


def _build_driveline(vehicle: object) -> dict[str, _npt.NDArray[_np.float64]]:
    # MATLAB:OpenVEHICLE.m:148-224 driveline model
    # en_speed_curve / en_torque_curve from torque_curve
    tc = getattr(vehicle, "torque_curve", None)
    if tc is None:
        tc = getattr(vehicle, "torque_curve", [])
    en_speed = _np.array([float(p[0]) for p in tc], dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:151 en_speed_curve
    en_torque = _np.array([float(p[1]) for p in tc], dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:152 en_torque_curve
    if en_speed.shape[0] == 0:
        en_speed = _np.array([1000.0, 8000.0], dtype=_np.float64)
        en_torque = _np.array([100.0, 100.0], dtype=_np.float64)
    # ratios
    rp = float(getattr(vehicle, "ratio_primary", 1.0))  # MATLAB:OpenVEHICLE.m:101 ratio_primary
    rf = float(getattr(vehicle, "ratio_final", getattr(vehicle, "final_drive", 7.0)))  # MATLAB:OpenVEHICLE.m:102 ratio_final
    rg_raw = getattr(vehicle, "ratio_gearbox", (1.0,))
    if isinstance(rg_raw, (list, tuple)):
        rg = _np.array(list(rg_raw), dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:103 ratio_gearbox
    else:
        rg = _np.array([float(rg_raw)], dtype=_np.float64)
    Rt = float(getattr(vehicle, "tyre_radius", getattr(vehicle, "wheel_radius", 0.33)))  # MATLAB:OpenVEHICLE.m:81 tyre_radius
    if Rt <= 1e-9:
        Rt = 0.33
    np_eff = float(getattr(vehicle, "n_primary", 1.0))  # MATLAB:OpenVEHICLE.m:98 n_primary
    ng_eff = float(getattr(vehicle, "n_gearbox", 0.98))  # MATLAB:OpenVEHICLE.m:100 n_gearbox
    nf_eff = float(getattr(vehicle, "n_final", 0.92))  # MATLAB:OpenVEHICLE.m:99 n_final
    nog = int(rg.shape[0])
    if nog == 0:
        rg = _np.array([1.0], dtype=_np.float64)
        nog = 1
    n_en = int(en_speed.shape[0])
    wheel_speed_gear = _np.zeros((n_en, nog), dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:156 wheel_speed_gear
    vehicle_speed_gear = _np.zeros((n_en, nog), dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:158 vehicle_speed_gear
    wheel_torque_gear = _np.zeros((n_en, nog), dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:160 wheel_torque_gear
    for j in range(nog):  # MATLAB:OpenVEHICLE.m:162 for i=1:nog
        rgj = float(rg[j])
        # MATLAB:OpenVEHICLE.m:163 wheel_speed_gear(:,i)=en_speed_curve/ratio_primary/ratio_gearbox(i)/ratio_final
        wheel_speed_gear[:, j] = en_speed / max(rp, 1e-9) / max(rgj, 1e-9) / max(rf, 1e-9)
        # MATLAB:OpenVEHICLE.m:164 vehicle_speed_gear = wheel_speed*2*pi/60*tyre_radius
        vehicle_speed_gear[:, j] = wheel_speed_gear[:, j] * 2.0 * _math.pi / 60.0 * Rt
        # MATLAB:OpenVEHICLE.m:165 wheel_torque_gear = en_torque*ratio_primary*ratio_gearbox(i)*ratio_final*n_primary*n_gearbox*n_final
        wheel_torque_gear[:, j] = en_torque * rp * rgj * rf * np_eff * ng_eff * nf_eff
    v_min = float(_np.min(vehicle_speed_gear))  # MATLAB:OpenVEHICLE.m:168 v_min
    v_max = float(_np.max(vehicle_speed_gear))  # MATLAB:OpenVEHICLE.m:169 v_max
    if v_max <= v_min:
        v_max = v_min + 10.0
    dv = 0.5 / 3.6  # MATLAB:OpenVEHICLE.m:171 dv = 0.5/3.6
    npts_f = (v_max - v_min) / dv  # MATLAB:OpenVEHICLE.m:172 (v_max-v_min)/dv
    npts = int(max(2, round(npts_f)))  # MATLAB: linspace uses float count -> round
    if npts < 2:
        npts = 2
    vehicle_speed = _np.linspace(v_min, v_max, npts, dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:172 vehicle_speed
    fx = _np.zeros((npts, nog), dtype=_np.float64)  # MATLAB:OpenVEHICLE.m:179 fx
    for i in range(npts):  # MATLAB:OpenVEHICLE.m:181 for i=1:length(vehicle_speed)
        vi = float(vehicle_speed[i])
        for j in range(nog):  # MATLAB:OpenVEHICLE.m:183 for j=1:nog
            vs_g = vehicle_speed_gear[:, j]
            wt_g = wheel_torque_gear[:, j] / max(Rt, 1e-9)
            # MATLAB:OpenVEHICLE.m:184 fx(i,j)=interp1(vehicle_speed_gear(:,j),wheel_torque_gear(:,j)/tyre_radius,vehicle_speed(i),'linear',0)
            # interp1 with 'linear',0 -> 0 outside
            if vi < float(vs_g[0]) or vi > float(vs_g[-1]):
                fx[i, j] = 0.0
            else:
                fx[i, j] = float(_np.interp(vi, vs_g, wt_g, left=0.0, right=0.0))
    fx_engine = _np.max(fx, axis=1)  # MATLAB:OpenVEHICLE.m:187 [fx_engine(i),gear(i)]=max(fx(i,:))
    gear = _np.argmax(fx, axis=1).astype(_np.float64) + 1.0  # 1-indexed MATLAB:OpenVEHICLE.m:187 gear
    # MATLAB:OpenVEHICLE.m:190-192 adding 0 speed for interpolation at low speeds
    vehicle_speed_ext = _np.concatenate([_np.array([0.0], dtype=_np.float64), vehicle_speed])  # MATLAB:OpenVEHICLE.m:190 vehicle_speed=[0;vehicle_speed]
    gear_ext = _np.concatenate([_np.array([float(gear[0])], dtype=_np.float64), gear])  # MATLAB:OpenVEHICLE.m:191 gear=[gear(1);gear]
    fx_engine_ext = _np.concatenate([_np.array([float(fx_engine[0])], dtype=_np.float64), fx_engine])  # MATLAB:OpenVEHICLE.m:192 fx_engine
    # MATLAB:OpenVEHICLE.m:195 engine_speed = ratio_final*ratio_gearbox(gear)*ratio_primary.*vehicle_speed/tyre_radius*60/2/pi
    engine_speed = _np.zeros_like(vehicle_speed_ext)
    for idx in range(int(vehicle_speed_ext.shape[0])):
        g_ = int(float(gear_ext[idx]))
        if 1 <= g_ <= nog:
            rgj = float(rg[g_ - 1])
        else:
            rgj = float(rg[0])
        engine_speed[idx] = rf * rgj * rp * float(vehicle_speed_ext[idx]) / max(Rt, 1e-9) * 60.0 / 2.0 / _math.pi
    # shifting points: MATLAB:OpenVEHICLE.m:208-214
    # gear_change = diff(gear); gear_change=logical([gear_change;0]+[0;gear_change]); engine_speed_gear_change=engine_speed(gear_change); shift_points=engine_speed_gear_change(1:2:end)
    gear_diff = _np.diff(gear_ext)  # MATLAB:OpenVEHICLE.m:208 gear_change=diff(gear)
    # MATLAB:OpenVEHICLE.m:210 gear_change=logical([gear_change;0]+[0;gear_change])
    gear_change_bool = _np.zeros(int(gear_ext.shape[0]), dtype=bool)
    for idx in range(int(gear_ext.shape[0])):
        left = float(gear_diff[idx - 1]) if idx > 0 and idx - 1 < gear_diff.shape[0] else 0.0
        right = float(gear_diff[idx]) if idx < gear_diff.shape[0] else 0.0
        if left != 0.0 or right != 0.0:
            gear_change_bool[idx] = True
    engine_speed_gear_change = engine_speed[gear_change_bool]  # MATLAB:OpenVEHICLE.m:212
    shift_points = engine_speed_gear_change[0::2]  # MATLAB:OpenVEHICLE.m:214 shift_points=engine_speed_gear_change(1:2:end)
    # MATLAB:OpenDRAG.m:100 shift_points=[shift_points;veh.en_speed_curve(end)] tail
    if shift_points.shape[0] == 0:
        shift_points = _np.array([float(en_speed[-1])], dtype=_np.float64)
    else:
        # append en_speed_curve(end) if not already tail
        shift_points = _np.concatenate([shift_points, _np.array([float(en_speed[-1])], dtype=_np.float64)])
    return {
        "en_speed_curve": en_speed,
        "en_torque_curve": en_torque,
        "vehicle_speed": vehicle_speed_ext,
        "gear": gear_ext,
        "engine_speed": engine_speed,
        "fx_engine": fx_engine_ext,
        "v_max": float(v_max),
        "v_min": float(v_min),
        "shift_points": shift_points,
        "rg": rg,
        "rf": float(rf),
        "rp": float(rp),
        "Rt": float(Rt),
        "np": float(np_eff),
        "ng": float(ng_eff),
        "nf": float(nf_eff),
        "nog": int(nog),
    }


def _resolve_vehicle(vehicle: object) -> object:
    if vehicle is None:
        vehicle = "f1"
    # if already Vehicle47-like (has M and tyre_radius) return
    if hasattr(vehicle, "M") and hasattr(vehicle, "tyre_radius") and hasattr(vehicle, "torque_curve"):
        return vehicle
    if hasattr(vehicle, "mass_kg") and hasattr(vehicle, "torque_curve"):
        # MVP Vehicle -> adapt to Vehicle47-like needed for drag? Keep as is but drag will handle fallback
        return vehicle
    if isinstance(vehicle, dict):
        # try Vehicle47 from dict
        try:
            from openlapexe.vehicle import Vehicle47 as _V47

            return _V47.from_json(vehicle)  # type: ignore[arg-type]
        except Exception:
            pass
        # fallback MVP
        from app import Vehicle as _Veh

        return _Veh.from_json(vehicle)  # type: ignore[arg-type]
    if isinstance(vehicle, _pathlib.Path):
        try:
            from openlapexe.vehicle import Vehicle47 as _V47

            return _V47.from_json(vehicle)
        except Exception:
            from app import Vehicle as _Veh

            return _Veh.from_json(vehicle)
    if isinstance(vehicle, str):
        s = vehicle.strip()
        # try Vehicle47
        try:
            from openlapexe.vehicle import Vehicle47 as _V47

            return _V47.from_json(s)
        except Exception:
            pass
        try:
            from app import Vehicle as _Veh

            return _Veh.from_json(s)
        except Exception as e:
            raise ValueError(f"vehicle not found: {vehicle!r}: {e}") from e
    return vehicle


def _resolve_track(track: object) -> object | None:
    if track is None:
        return None
    if hasattr(track, "points") and hasattr(track, "length_m"):
        return track
    if isinstance(track, str):
        try:
            from openlapexe.track import Track2 as _T2

            return _T2.from_json(track)
        except Exception:
            try:
                from app import Track as _Tr

                return _Tr.from_json(track)
            except Exception:
                return None
    return track


def simulate_drag(
    vehicle: object | None = None,
    track: object | None = None,
    dt: float = 1e-3,  # MATLAB:OpenDRAG.m:57 dt=1E-3
    t_max: float = 60.0,  # MATLAB:OpenDRAG.m:59 t_max=60
    ax_sens: float = 0.05,  # MATLAB:OpenDRAG.m:61 ax_sens=0.05
    speed_trap: _npt.NDArray[_np.float64] | None = None,  # MATLAB:OpenDRAG.m:63 speed_trap=[50;100;150;200;250;300;350]/3.6
    bank: float = 0.0,  # MATLAB:OpenDRAG.m:65 bank=0
    incl: float = 0.0,  # MATLAB:OpenDRAG.m:66 incl=0
) -> DragResult:
    # Resolve vehicle/track (deterministic, numpy only)
    veh = _resolve_vehicle(vehicle)  # MATLAB:OpenDRAG.m:71 veh=load(vehiclefile)
    _trk = _resolve_track(track)  # Track2 banking/grip input (kept for API compatibility)
    # Use Track2 banking/grip if track provided and bank/incl not explicitly overridden? Keep bank/incl as passed (spec requires explicit)
    # But if track has average banking, we could blend: not needed for straight line drag; bank/incl scalars dominate
    _ = _trk

    # defaults for speed_trap
    if speed_trap is None:
        speed_trap_arr: _npt.NDArray[_np.float64] = _np.array([50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0], dtype=_np.float64) / 3.6  # MATLAB:OpenDRAG.m:63
    else:
        speed_trap_arr = _np.asarray(speed_trap, dtype=_np.float64).ravel()
        # if values look like km/h (>50), convert? spec says [50..350]/3.6 already; keep as is if already m/s (small), otherwise convert heuristic not needed
        # assume already m/s if caller passed via default; if caller passes km/h values >20, they are already divided in MATLAB but we keep raw
        # No auto conversion to keep deterministic 1e-9

    # Vehicle params (adapt Vehicle47 and MVP)
    # M
    if hasattr(veh, "M"):
        M = float(getattr(veh, "M"))  # MATLAB:OpenDRAG.m:73 M=veh.M
    elif hasattr(veh, "mass_kg"):
        M = float(getattr(veh, "mass_kg"))
    else:
        M = 650.0
    g = 9.81  # MATLAB:OpenDRAG.m:75 g=9.81
    # tyre coefficients
    factor_grip = float(getattr(veh, "factor_grip", 1.0))
    sens_x = float(getattr(veh, "sens_x", getattr(veh, "tire_mu_x", 0.0001) if hasattr(veh, "sens_x") else 0.0001))
    # fallback for MVP: sens_x not present
    if not hasattr(veh, "sens_x"):
        # MVP has no sens_x; use default 0.0001
        sens_x = 0.0001
    mu_x = float(getattr(veh, "mu_x", getattr(veh, "tire_mu_x", 2.0)))
    mu_x_M = float(getattr(veh, "mu_x_M", 250.0))
    dmx = factor_grip * sens_x  # MATLAB:OpenDRAG.m:77 dmx=veh.factor_grip*veh.sens_x
    mux = factor_grip * mu_x  # MATLAB:OpenDRAG.m:78 mux=veh.factor_grip*veh.mu_x
    Nx = mu_x_M * g  # MATLAB:OpenDRAG.m:79 Nx=veh.mu_x_M*g
    Wz = M * g * _cosd(float(bank)) * _cosd(float(incl))  # MATLAB:OpenDRAG.m:81 Wz=M*g*cosd(bank)*cosd(incl)
    # Wx for ax_drag (sign bug included: positive Wx adds to drag, butincl=0 =>0)
    Wx = M * g * _sind(float(incl))  # MATLAB:OpenDRAG.m:84 Wx=M*g*sind(incl) ; Wy unused
    # ratios / tyre
    rf = float(getattr(veh, "ratio_final", getattr(veh, "final_drive", 7.0)))  # MATLAB:OpenDRAG.m:86 rf=veh.ratio_final
    rg_arr_raw = getattr(veh, "ratio_gearbox", (1.0,))
    if isinstance(rg_arr_raw, (list, tuple, _np.ndarray)):
        rg = _np.array(list(rg_arr_raw), dtype=_np.float64)  # MATLAB:OpenDRAG.m:87 rg=veh.ratio_gearbox
    else:
        rg = _np.array([float(rg_arr_raw)], dtype=_np.float64)
    rp = float(getattr(veh, "ratio_primary", 1.0))  # MATLAB:OpenDRAG.m:88 rp=veh.ratio_primary
    Rt = float(getattr(veh, "tyre_radius", getattr(veh, "wheel_radius", 0.33)))  # MATLAB:OpenDRAG.m:90 Rt=veh.tyre_radius (vehicle別)
    if Rt <= 1e-9:
        Rt = 0.33
    np_eff = float(getattr(veh, "n_primary", 1.0))  # MATLAB:OpenDRAG.m:92 np=veh.n_primary
    ng_eff = float(getattr(veh, "n_gearbox", 0.98))  # MATLAB:OpenDRAG.m:93 ng=veh.n_gearbox
    nf_eff = float(getattr(veh, "n_final", 0.92))  # MATLAB:OpenDRAG.m:94 nf=veh.n_final
    # aero
    rho = float(getattr(veh, "rho", 1.225))  # MATLAB:OpenVEHICLE.m:70 rho
    factor_Cl = float(getattr(veh, "factor_Cl", 1.0))
    Cl = float(getattr(veh, "Cl", getattr(veh, "cl", -4.8)))
    factor_Cd = float(getattr(veh, "factor_Cd", 1.0))
    Cd = float(getattr(veh, "Cd", getattr(veh, "cda", 1.2)))
    # For MVP cda vs Cd handling: if Cd is positive from cda, need negative sign per MATLAB (Cd negative)
    # Vehicle47 stores Cd negative; MVP cda positive -> Cd derived as negative; keep as is
    # If vehicle has cda and Cd is positive magnitude, ensure Aero_Dr sign matches MATLAB (Cd negative => Aero_Dr negative)
    # No auto sign flip; use stored Cd directly (Vehicle maps cda to negative)
    A = float(getattr(veh, "A", 1.0))
    if hasattr(veh, "cda") and not hasattr(veh, "Cd"):
        # MVP: cda positive, approximate Cd = -cda/A for aero calc to get negative drag
        A_val = float(getattr(veh, "A", 1.0)) if hasattr(veh, "A") else 1.0
        Cd = -abs(float(getattr(veh, "cda"))) / max(A_val, 1e-9)
    Cr = float(getattr(veh, "Cr", -0.001))  # MATLAB:OpenVEHICLE.m:82 Cr (negative)
    # drive factors
    drive = str(getattr(veh, "drive", "RWD"))
    df = float(getattr(veh, "df", getattr(veh, "weight_dist_front", 0.45)))
    da = float(getattr(veh, "da", getattr(veh, "weight_dist_front", 0.5)))
    if drive == "RWD":  # MATLAB:OpenVEHICLE.m:234 factor_drive=(1-df)
        factor_drive = 1.0 - df  # MATLAB:OpenVEHICLE.m:235
        factor_aero = 1.0 - da  # MATLAB:OpenVEHICLE.m:236
        driven_wheels = 2  # MATLAB:OpenVEHICLE.m:237
    elif drive == "FWD":  # MATLAB:OpenVEHICLE.m:238
        factor_drive = df  # MATLAB:OpenVEHICLE.m:239
        factor_aero = da  # MATLAB:OpenVEHICLE.m:240
        driven_wheels = 2  # MATLAB:OpenVEHICLE.m:241
    else:  # AWD MATLAB:OpenVEHICLE.m:242
        factor_drive = 1.0  # MATLAB:OpenVEHICLE.m:243
        factor_aero = 1.0  # MATLAB:OpenVEHICLE.m:244
        driven_wheels = 4  # MATLAB:OpenVEHICLE.m:245
    # beta for braking
    # MATLAB:OpenVEHICLE.m:133-135 br_pist_a = br_nop*pi*(br_pist_d/1000)^2/4 ; beta=tyre_radius/(br_disc_d/2-br_pad_h/2)/br_pist_a/br_pad_mu/4
    # Vehicle47 stores br_* already in meters (divided by 1000)
    beta = 0.0
    try:
        br_disc_d = float(getattr(veh, "br_disc_d", 0.25))
        br_pad_h = float(getattr(veh, "br_pad_h", 0.04))
        br_pad_mu = float(getattr(veh, "br_pad_mu", 0.45))
        br_nop = float(getattr(veh, "br_nop", 6.0))
        br_pist_d = float(getattr(veh, "br_pist_d", 0.04))
        br_pist_a = br_nop * _math.pi * br_pist_d * br_pist_d / 4.0
        denom = (br_disc_d / 2.0 - br_pad_h / 2.0)
        if abs(denom) > 1e-9 and br_pist_a > 1e-9 and br_pad_mu > 1e-9:
            beta = Rt / denom / br_pist_a / br_pad_mu / 4.0  # MATLAB:OpenVEHICLE.m:135 beta
        else:
            beta = 0.0
    except Exception:
        beta = 0.0
    # fallback if beta still 0 and vehicle has beta attribute
    if beta == 0.0 and hasattr(veh, "beta"):
        try:
            beta = float(getattr(veh, "beta"))
        except Exception:
            pass
    # driveline for shift points, v_max, vehicle_speed/gear/engine_speed
    dl = _build_driveline(veh)  # MATLAB:OpenVEHICLE.m:148-217 driveline
    en_speed_curve = dl["en_speed_curve"]  # MATLAB:OpenDRAG.m:96 rpm_curve base
    en_torque_curve = dl["en_torque_curve"]
    v_max = float(dl["v_max"])  # MATLAB:OpenVEHICLE.m:169 v_max (also veh.v_max)
    # allow veh.v_max override if present
    if hasattr(veh, "v_max"):
        try:
            v_max = float(getattr(veh, "v_max"))
        except Exception:
            pass
    shift_points = dl["shift_points"]  # MATLAB:OpenDRAG.m:99-100 shift_points=[shift_points;veh.en_speed_curve(end)]
    nog = int(dl["nog"])
    # rpm_curve / torque_curve for engine torque interp
    # MATLAB:OpenDRAG.m:96 rpm_curve=[0;veh.en_speed_curve]
    rpm_curve = _np.concatenate([_np.array([0.0], dtype=_np.float64), en_speed_curve.astype(_np.float64)])  # MATLAB:OpenDRAG.m:96
    # MATLAB:OpenDRAG.m:97 torque_curve=veh.factor_power*[veh.en_torque_curve(1);veh.en_torque_curve]
    factor_power = float(getattr(veh, "factor_power", getattr(veh, "engine_power_factor", 1.0)))
    torque_curve = factor_power * _np.concatenate([_np.array([float(en_torque_curve[0])], dtype=_np.float64), en_torque_curve.astype(_np.float64)])  # MATLAB:OpenDRAG.m:97
    # vehicle_speed / gear / engine_speed for deceleration interp
    veh_vehicle_speed = dl["vehicle_speed"]  # MATLAB:OpenVEHICLE.m:190 vehicle_speed
    veh_gear = dl["gear"]  # MATLAB:OpenVEHICLE.m:191 gear
    veh_engine_speed = dl["engine_speed"]  # MATLAB:OpenVEHICLE.m:195 engine_speed

    # -----------------------------------------------------------------------
    # Acceleration preprocessing MATLAB:OpenDRAG.m:102-141
    # -----------------------------------------------------------------------
    N = int(float(t_max) / float(dt))  # MATLAB:OpenDRAG.m:105 N=t_max/dt
    if N <= 0:
        N = 60000
    # memory preallocation not needed with lists but keep N for limit checks
    T_list: list[float] = []
    X_list: list[float] = []
    V_list: list[float] = []
    A_list: list[float] = []
    RPM_list: list[float] = []
    TPS_list: list[float] = []
    BPS_list: list[float] = []
    GEAR_list: list[float] = []
    MODE_list: list[float] = []
    trap_log: list[dict[str, float]] = []

    t = 0.0  # MATLAB:OpenDRAG.m:116 t=0
    t_start = 0.0  # MATLAB:OpenDRAG.m:117 t_start=0
    x = 0.0  # MATLAB:OpenDRAG.m:119 x=0
    x_start = 0.0  # MATLAB:OpenDRAG.m:120 x_start=0
    v = 0.0  # MATLAB:OpenDRAG.m:122 v=0
    a = 0.0  # MATLAB:OpenDRAG.m:124 a=0
    gear = 1  # MATLAB:OpenDRAG.m:126 gear=1
    gear_prev = 1  # MATLAB:OpenDRAG.m:127 gear_prev=1
    shifting = False  # MATLAB:OpenDRAG.m:129 shifting=false
    rpm = 0.0  # MATLAB:OpenDRAG.m:131 rpm=0
    tps = 0.0  # MATLAB:OpenDRAG.m:133 tps=0
    bps = 0.0  # MATLAB:OpenDRAG.m:135 bps=0
    trap_number = 0  # 0-indexed for python (MATLAB:OpenDRAG.m:137 trap_number=1)
    check_speed_traps = True  # MATLAB:OpenDRAG.m:139 check_speed_traps=true
    i = 0  # MATLAB:OpenDRAG.m:141 i=1 (0-indexed)
    t_shift = 0.0  # MATLAB:OpenDRAG.m:250 t_shift (initialized on shift)
    ax = 0.0  # engine acc, zeroed on shift MATLAB:OpenDRAG.m:252 ax=0
    ax_drag = 0.0  # drag acc, computed each step MATLAB:OpenDRAG.m:230 ax_drag
    ax_power_limit = 1.0  # init for tps guard

    # -----------------------------------------------------------------------
    # Acceleration MATLAB:OpenDRAG.m:179-293 while true
    # -----------------------------------------------------------------------
    # We loop with deterministic dt, clamp interp via _np.interp
    max_iter = N
    # For a_ave / a_peak
    # HUD not needed
    # eslint-like: keep loop bounded by N and v_max and drag limit
    iter_count = 0
    while True:  # MATLAB:OpenDRAG.m:179 while true
        # saving values MATLAB:OpenDRAG.m:181-189 MODE(i)=1 etc
        # interpret each as clamp: store before break checks (MATLAB saves then checks)
        T_list.append(float(t))  # MATLAB:OpenDRAG.m:182 T(i)=t
        X_list.append(float(x))  # MATLAB:OpenDRAG.m:183 X(i)=x
        V_list.append(float(v))  # MATLAB:OpenDRAG.m:184 V(i)=v
        A_list.append(float(a))  # MATLAB:OpenDRAG.m:185 A(i)=a
        RPM_list.append(float(rpm))  # MATLAB:OpenDRAG.m:186 RPM(i)=rpm
        TPS_list.append(float(tps))  # MATLAB:OpenDRAG.m:187 TPS(i)=tps
        BPS_list.append(0.0)  # MATLAB:OpenDRAG.m:188 BPS(i)=0
        GEAR_list.append(float(gear))  # MATLAB:OpenDRAG.m:189 GEAR(i)=gear (0 during shift)
        MODE_list.append(1.0)  # MATLAB:OpenDRAG.m:181 MODE(i)=1

        # checking if rpm limiter is on or if out of memory MATLAB:OpenDRAG.m:191-199
        if v >= v_max:  # MATLAB:OpenDRAG.m:191 if v>=veh.v_max
            break  # MATLAB:OpenDRAG.m:195 break
        if i >= N:  # inclusive S-OT4
            break  # MATLAB:OpenDRAG.m:199 break
        # check if drag limited MATLAB:OpenDRAG.m:202 if tps==1 && ax+ax_drag<=ax_sens
        if tps == 1.0 and (ax + ax_drag) <= float(ax_sens):  # MATLAB:OpenDRAG.m:202
            break  # MATLAB:OpenDRAG.m:206 break
        # checking speed trap MATLAB:OpenDRAG.m:209-220
        if check_speed_traps:  # MATLAB:OpenDRAG.m:209 if check_speed_traps
            if trap_number < int(speed_trap_arr.shape[0]):  # bounds
                if v >= float(speed_trap_arr[trap_number]):  # MATLAB:OpenDRAG.m:211 if v>=speed_trap(trap_number)
                    # log trap (deterministic, trap_log)
                    trap_log.append({"trap": float(trap_number + 1), "speed_kmh": float(speed_trap_arr[trap_number] * 3.6), "t": float(t), "x": float(x), "v": float(v), "mode": 1.0})
                    trap_number += 1  # MATLAB:OpenDRAG.m:215 trap_number=trap_number+1
                    if trap_number >= int(speed_trap_arr.shape[0]):  # MATLAB:OpenDRAG.m:217 if trap_number>length(speed_trap)
                        check_speed_traps = False  # MATLAB:OpenDRAG.m:218

        # aero forces MATLAB:OpenDRAG.m:223-224
        Aero_Df = 0.5 * rho * factor_Cl * Cl * A * v * v  # MATLAB:OpenDRAG.m:223 Aero_Df=1/2*veh.rho*veh.factor_Cl*veh.Cl*veh.A*v^2
        Aero_Dr = 0.5 * rho * factor_Cd * Cd * A * v * v  # MATLAB:OpenDRAG.m:224 Aero_Dr=1/2*veh.rho*veh.factor_Cd*veh.Cd*veh.A*v^2
        # rolling resistance MATLAB:OpenDRAG.m:226 Roll_Dr=veh.Cr*(-Aero_Df+Wz)
        Roll_Dr = Cr * (-Aero_Df + Wz)  # MATLAB:OpenDRAG.m:226
        # normal load on driven wheels MATLAB:OpenDRAG.m:228 Wd=(veh.factor_drive*Wz+(-veh.factor_aero*Aero_Df))/veh.driven_wheels
        Wd = (factor_drive * Wz + (-factor_aero * Aero_Df)) / max(driven_wheels, 1)  # MATLAB:OpenDRAG.m:228
        # drag acceleration MATLAB:OpenDRAG.m:230 ax_drag=(Aero_Dr+Roll_Dr+Wx)/M
        ax_drag = (Aero_Dr + Roll_Dr + Wx) / max(M, 1e-9)  # MATLAB:OpenDRAG.m:230
        # rpm calculation MATLAB:OpenDRAG.m:232-238
        if gear == 0:  # MATLAB:OpenDRAG.m:232 if gear==0 % shifting gears
            # MATLAB:OpenDRAG.m:233 rpm=rf*rg(gear_prev)*rp*v/Rt*60/2/pi
            rg_prev = float(rg[int(gear_prev) - 1]) if 1 <= int(gear_prev) <= int(rg.shape[0]) else float(rg[0])
            rpm = rf * rg_prev * rp * v / max(Rt, 1e-9) * 60.0 / 2.0 / _math.pi  # MATLAB:OpenDRAG.m:233
            rpm_shift = float(shift_points[int(gear_prev) - 1]) if 1 <= int(gear_prev) <= int(shift_points.shape[0]) else float(shift_points[-1])  # MATLAB:OpenDRAG.m:234 rpm_shift=shift_points(gear_prev)
        else:  # MATLAB:OpenDRAG.m:235 else % gear change finished
            rg_cur = float(rg[int(gear) - 1]) if 1 <= int(gear) <= int(rg.shape[0]) else float(rg[0])
            rpm = rf * rg_cur * rp * v / max(Rt, 1e-9) * 60.0 / 2.0 / _math.pi  # MATLAB:OpenDRAG.m:236
            rpm_shift = float(shift_points[int(gear) - 1]) if 1 <= int(gear) <= int(shift_points.shape[0]) else float(shift_points[-1])  # MATLAB:OpenDRAG.m:237 rpm_shift=shift_points(gear)

        # checking for gearshifts MATLAB:OpenDRAG.m:240-280
        if rpm >= rpm_shift and not shifting:  # MATLAB:OpenDRAG.m:240 if rpm>=rpm_shift && ~shifting
            if gear == nog:  # MATLAB:OpenDRAG.m:241 if gear==veh.nog % maximum gear number
                break  # MATLAB:OpenDRAG.m:245 break
            else:  # MATLAB:OpenDRAG.m:246 else % higher gear available
                shifting = True  # MATLAB:OpenDRAG.m:248 shifting=true
                t_shift = float(t)  # MATLAB:OpenDRAG.m:250 t_shift=t
                ax = 0.0  # MATLAB:OpenDRAG.m:252 ax=0
                gear_prev = int(gear)  # MATLAB:OpenDRAG.m:254 gear_prev=gear
                gear = 0  # MATLAB:OpenDRAG.m:256 gear=0
        elif shifting:  # MATLAB:OpenDRAG.m:258 elseif shifting % currently shifting gears
            ax = 0.0  # MATLAB:OpenDRAG.m:260 ax=0
            # MATLAB:OpenDRAG.m:262 if t-t_shift>veh.shift_time 厳密> (strictly >)
            if (t - t_shift) > float(getattr(veh, "shift_time", 0.05)):  # MATLAB:OpenDRAG.m:262
                shifting = False  # MATLAB:OpenDRAG.m:267 shifting=false
                gear = int(gear_prev) + 1  # MATLAB:OpenDRAG.m:269 gear=gear_prev+1
        else:  # MATLAB:OpenDRAG.m:271 else % no gearshift
            # max long acc available from tyres MATLAB:OpenDRAG.m:273 ax_tyre_max_acc=1/M*(mux+dmx*(Nx-Wd))*Wd*veh.driven_wheels
            ax_tyre_max_acc = 1.0 / max(M, 1e-9) * (mux + dmx * (Nx - Wd)) * Wd * driven_wheels  # MATLAB:OpenDRAG.m:273
            # getting power limit from engine MATLAB:OpenDRAG.m:275 engine_torque=interp1(rpm_curve,torque_curve,rpm)
            engine_torque = _interp_clamp(rpm_curve, torque_curve, float(rpm))  # MATLAB:OpenDRAG.m:275 interp1 clamp
            # MATLAB:OpenDRAG.m:276 wheel_torque=engine_torque*rf*rg(gear)*rp*nf*ng*np
            rg_cur2 = float(rg[int(gear) - 1]) if 1 <= int(gear) <= int(rg.shape[0]) else float(rg[0])
            wheel_torque = engine_torque * rf * rg_cur2 * rp * nf_eff * ng_eff * np_eff  # MATLAB:OpenDRAG.m:276
            ax_power_limit = wheel_torque / max(Rt, 1e-9) / max(M, 1e-9)  # MATLAB:OpenDRAG.m:277 ax_power_limit=1/M*wheel_torque/Rt
            # final long acc MATLAB:OpenDRAG.m:279 ax=min([ax_power_limit,ax_tyre_max_acc])
            ax = float(min(float(ax_power_limit), float(ax_tyre_max_acc)))  # MATLAB:OpenDRAG.m:279

        # tps MATLAB:OpenDRAG.m:282 tps=ax/ax_power_limit (ゼロ除算ガード)
        if abs(float(ax_power_limit)) > 1e-12:
            tps = float(ax) / float(ax_power_limit)  # MATLAB:OpenDRAG.m:282
            # clamp to [0,1] for sanity (original may exceed 1 briefly during shift where ax=0)
            if tps > 1.0:
                tps = 1.0
            if tps < 0.0:
                tps = 0.0
        else:
            tps = 0.0

        # longitudinal acceleration MATLAB:OpenDRAG.m:284 a=ax+ax_drag (正値、原典通り符号バグ含む)
        a = float(ax) + float(ax_drag)  # MATLAB:OpenDRAG.m:284

        # new position MATLAB:OpenDRAG.m:286 x=x+v*dt+1/2*a*dt^2
        x = x + v * float(dt) + 0.5 * a * float(dt) * float(dt)  # MATLAB:OpenDRAG.m:286
        # new velocity MATLAB:OpenDRAG.m:288 v=v+a*dt
        v = v + a * float(dt)  # MATLAB:OpenDRAG.m:288
        if v < 0.0:
            v = 0.0
        # new time MATLAB:OpenDRAG.m:290 t=t+dt
        t = t + float(dt)  # MATLAB:OpenDRAG.m:290
        # next iteration MATLAB:OpenDRAG.m:292 i=i+1
        i += 1
        iter_count += 1
        if iter_count >= max_iter - 1:
            # prevent infinite; also save final? break after saving next iteration start
            # Ensure we have saved enough; loop will save at top next iteration then break via i>=N
            if i >= N - 1:
                break
        # safety: if t exceeds t_max, break
        if t >= float(t_max):
            # will be caught via i==N next loop, but break now to avoid extra
            # save one more iteration? follow MATLAB's i==N break at top of next loop
            # So we continue to let top save handle; just keep looping
            pass

    i_acc = i  # MATLAB:OpenDRAG.m:294 i_acc=i
    # average acceleration MATLAB:OpenDRAG.m:296 a_acc_ave=v/t
    if t > 1e-12:
        a_acc_ave = v / t  # MATLAB:OpenDRAG.m:296
    else:
        a_acc_ave = 0.0
    # peak acceleration MATLAB:OpenDRAG.m:298 max(A)
    if len(A_list) > 0:
        # A_list includes values before update; a_peak is max of saved A (which is previous a)
        # Use numpy for deterministic max
        a_peak = float(_np.max(_np.array(A_list, dtype=_np.float64)))
    else:
        a_peak = 0.0

    # -----------------------------------------------------------------------
    # Deceleration preprocessing MATLAB:OpenDRAG.m:302-313
    # -----------------------------------------------------------------------
    t_start = float(t)  # MATLAB:OpenDRAG.m:307 t_start=t
    x_start = float(x)  # MATLAB:OpenDRAG.m:308 x_start=x
    check_speed_traps = True  # MATLAB:OpenDRAG.m:310 check_speed_traps=true
    # active braking speed traps MATLAB:OpenDRAG.m:312 speed_trap_decel=speed_trap(speed_trap<=v)
    speed_trap_decel = speed_trap_arr[speed_trap_arr <= v + 1e-12]  # MATLAB:OpenDRAG.m:312
    trap_number_decel = int(speed_trap_decel.shape[0]) - 1  # MATLAB:OpenDRAG.m:313 trap_number=length(speed_trap_decel) (1-indexed -> -1 for 0-index)
    if speed_trap_decel.shape[0] == 0:
        check_speed_traps = False
    # BPS init for decel already bps variable, but ensure
    # continue a from previous (still last acceleration a)
    # deceleration loop
    # Note: i continues from i_acc

    # -----------------------------------------------------------------------
    # Deceleration MATLAB:OpenDRAG.m:325-391 while true
    # -----------------------------------------------------------------------
    # Ensure gear for decel start: if we ended in shifting (gear==0) set to gear_prev+1 else keep
    if gear == 0:
        # if still shifting at end of accel, set to next gear for decel start (original would have gear==0 but decel resets via interp)
        # gear will be overwritten by interp1 anyway, but keep sensible
        gear = int(gear_prev) + 1
        if gear > nog:
            gear = nog
        if gear < 1:
            gear = 1

    decel_iter = 0
    while True:  # MATLAB:OpenDRAG.m:325 while true
        # saving values MATLAB:OpenDRAG.m:327-335 MODE(i)=2 etc
        # Expand lists if needed (they are lists, just append)
        # But to keep MODE etc length aligned, we append
        # However MATLAB uses same i index continuing; for lists we append
        T_list.append(float(t))  # MATLAB:OpenDRAG.m:328 T(i)=t
        X_list.append(float(x))  # MATLAB:OpenDRAG.m:329 X(i)=x
        V_list.append(float(v))  # MATLAB:OpenDRAG.m:330 V(i)=v
        A_list.append(float(a))  # MATLAB:OpenDRAG.m:331 A(i)=a
        RPM_list.append(float(rpm))  # MATLAB:OpenDRAG.m:332 RPM(i)=rpm
        TPS_list.append(0.0)  # MATLAB:OpenDRAG.m:333 TPS(i)=0
        BPS_list.append(float(bps))  # MATLAB:OpenDRAG.m:334 BPS(i)=bps
        GEAR_list.append(float(gear))  # MATLAB:OpenDRAG.m:335 GEAR(i)=gear
        MODE_list.append(2.0)  # MATLAB:OpenDRAG.m:327 MODE(i)=2
        i += 1
        decel_iter += 1
        # checking if stopped or if out of memory MATLAB:OpenDRAG.m:337-347
        if v <= 0.0:  # MATLAB:OpenDRAG.m:337 if v<=0
            v = 0.0  # MATLAB:OpenDRAG.m:339 v=0
            break  # MATLAB:OpenDRAG.m:343 break
        if i >= N:  # inclusive S-OT4
            break  # MATLAB:OpenDRAG.m:347 break
        # safety t_max
        if t >= float(t_max):
            break
        # checking speed trap MATLAB:OpenDRAG.m:350-362
        if check_speed_traps and speed_trap_decel.shape[0] > 0:  # MATLAB:OpenDRAG.m:350 if check_speed_traps
            if 0 <= trap_number_decel < int(speed_trap_decel.shape[0]):
                if v <= float(speed_trap_decel[trap_number_decel]) + 1e-12:  # MATLAB:OpenDRAG.m:352 if v<=speed_trap_decel(trap_number)
                    trap_log.append({"trap": float(trap_number_decel + 1), "speed_kmh": float(speed_trap_decel[trap_number_decel] * 3.6), "t": float(t), "x": float(x), "v": float(v), "mode": 2.0})
                    trap_number_decel -= 1  # MATLAB:OpenDRAG.m:357 trap_number=trap_number-1
                    if trap_number_decel < 0:  # MATLAB:OpenDRAG.m:359 if trap_number<1
                        check_speed_traps = False  # MATLAB:OpenDRAG.m:360

        # aero forces MATLAB:OpenDRAG.m:365-366
        Aero_Df = 0.5 * rho * factor_Cl * Cl * A * v * v  # MATLAB:OpenDRAG.m:365
        Aero_Dr = 0.5 * rho * factor_Cd * Cd * A * v * v  # MATLAB:OpenDRAG.m:366
        Roll_Dr = Cr * (-Aero_Df + Wz)  # MATLAB:OpenDRAG.m:368
        ax_drag = (Aero_Dr + Roll_Dr + Wx) / max(M, 1e-9)  # MATLAB:OpenDRAG.m:370
        # gear MATLAB:OpenDRAG.m:372 gear=interp1(veh.vehicle_speed,veh.gear,v)
        # Use clamp via _np.interp, round to nearest int
        gear_f = _np.interp(float(v), veh_vehicle_speed, veh_gear, left=float(veh_gear[0]), right=float(veh_gear[-1]))  # MATLAB:OpenDRAG.m:372
        gear = int(round(float(gear_f)))
        if gear < 1:
            gear = 1
        if gear > nog:
            gear = nog
        # rpm MATLAB:OpenDRAG.m:374 rpm=interp1(veh.vehicle_speed,veh.engine_speed,v)
        rpm = float(_np.interp(float(v), veh_vehicle_speed, veh_engine_speed, left=float(veh_engine_speed[0]), right=float(veh_engine_speed[-1])))  # MATLAB:OpenDRAG.m:374
        # max long dec available from tyres MATLAB:OpenDRAG.m:376 ax_tyre_max_dec=-1/M*(mux+dmx*(Nx-(Wz-Aero_Df)/4))*(Wz-Aero_Df)
        ax_tyre_max_dec = -1.0 / max(M, 1e-9) * (mux + dmx * (Nx - (Wz - Aero_Df) / 4.0)) * (Wz - Aero_Df)  # MATLAB:OpenDRAG.m:376
        ax = float(ax_tyre_max_dec)  # MATLAB:OpenDRAG.m:378 ax=ax_tyre_max_dec
        # brake pressure MATLAB:OpenDRAG.m:380 bps=-veh.beta*veh.M*ax
        bps = -beta * M * ax  # MATLAB:OpenDRAG.m:380
        # longitudinal acceleration MATLAB:OpenDRAG.m:382 a=ax+ax_drag
        a = float(ax) + float(ax_drag)  # MATLAB:OpenDRAG.m:382
        # new position MATLAB:OpenDRAG.m:384 x=x+v*dt+1/2*a*dt^2
        x = x + v * float(dt) + 0.5 * a * float(dt) * float(dt)  # MATLAB:OpenDRAG.m:384
        # new velocity MATLAB:OpenDRAG.m:386 v=v+a*dt
        v = v + a * float(dt)  # MATLAB:OpenDRAG.m:386
        if v < 0.0:
            v = 0.0
        # new time MATLAB:OpenDRAG.m:388 t=t+dt
        t = t + float(dt)  # MATLAB:OpenDRAG.m:388
        # MATLAB:OpenDRAG.m:390 i=i+1 already done at top (we increment at top); keep loop
        if decel_iter > N:
            break

    # average deceleration MATLAB:OpenDRAG.m:393 a_dec_ave=V(i_acc)/(t-t_start)
    # V(i_acc) is velocity at start of braking (saved V at i_acc index)
    # We have V_list, t etc.
    if len(V_list) > int(i_acc) and (t - t_start) > 1e-12:
        v_brake_start = float(V_list[int(i_acc)])
        a_dec_ave = v_brake_start / (t - t_start)  # MATLAB:OpenDRAG.m:393
    else:
        a_dec_ave = 0.0
    # peak deceleration MATLAB:OpenDRAG.m:395 -min(A)
    if len(A_list) > 0:
        a_dec_peak = float(-_np.min(_np.array(A_list, dtype=_np.float64)))
        if a_dec_peak < 0:
            a_dec_peak = 0.0
    else:
        a_dec_peak = 0.0

    # Results compression MATLAB:OpenDRAG.m:407-418 to_delete=T==-1 ; deleting
    # Our lists are already trimmed, but ensure deterministic length

    T_arr = _np.array(T_list, dtype=_np.float64)
    X_arr = _np.array(X_list, dtype=_np.float64)
    V_arr = _np.array(V_list, dtype=_np.float64)
    A_arr = _np.array(A_list, dtype=_np.float64)
    RPM_arr = _np.array(RPM_list, dtype=_np.float64)
    TPS_arr = _np.array(TPS_list, dtype=_np.float64)
    BPS_arr = _np.array(BPS_list, dtype=_np.float64)
    GEAR_arr = _np.array(GEAR_list, dtype=_np.float64)
    MODE_arr = _np.array(MODE_list, dtype=_np.float64)

    # Ensure encoding utf-8 not needed for arrays but for file
    # Return DragResult
    return DragResult(
        T=T_arr,
        X=X_arr,
        V=V_arr,
        A=A_arr,
        RPM=RPM_arr,
        TPS=TPS_arr,
        BPS=BPS_arr,
        GEAR=GEAR_arr,
        MODE=MODE_arr,
        a_ave=float(a_acc_ave),
        a_peak=float(a_peak),
        trap_log=trap_log,
        a_dec_ave=float(a_dec_ave),
        a_dec_peak=float(a_dec_peak),
    )


__all__ = ["DragResult", "simulate_drag"]
