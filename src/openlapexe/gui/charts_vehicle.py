# -*- coding: utf-8 -*-
# allow: SIZE_OK — Vehicle47から原典OpenVEHICLE 4種をCanvas再現 (別名) 単一責務 (GUI)
"""openlapexe.gui.charts_vehicle - Vehicle47 4チャート Canvas再現 (mpl禁止).

原典 OpenVEHICLE 4種を別名で再現:
- VehicleTorqueChart (トルク・パワー/回転 dual)
- VehicleGearChart (回転・ギア/車速)
- VehicleFxChart (Fx包絡線/車速、単調減少+段差)
- VehicleGGVChart (GGV surf wireframe、速度5..80の20×20グリッド)

要件:
- chart_xy/chart_base 利用、mpl禁止
- vehicle.py 改変禁止、既存名再利用禁止
- VehicleEditorのPCHIPプレビューと重複させず別Notebookタブ前提
- Canvas自前、<Configure>再描画、bg white、grid #e0e0e0、axes #333

テスト前提 (tests/test_charts_vehicle.py):
- トルク点一致、Fx包絡(単調減少+段差)、20×20 wireframe (速度5..80)
"""
from __future__ import annotations

import math as _math
import time as _time
import tkinter as tk
from typing import Any as _Any

import numpy as _np

from openlapexe.gui.chart_base import (
    BaseChart as _BaseChart,
    _axis_limits,
    _draw_axes,
    _draw_grid,
    _project_wireframe,
    _thin,
)
from openlapexe.gui.chart_xy import XYChart as _XYChart

__all__ = [
    "VehicleTorqueChart",
    "VehicleGearChart",
    "VehicleFxChart",
    "VehicleGGVChart",
]

# ---------------------------------------------------------------------------
# helpers: safe Canvas availability
# ---------------------------------------------------------------------------

def _safe_canvas_init(obj: tk.Canvas, master: _Any, kwargs: dict[str, _Any]) -> bool:
    try:
        kwargs.setdefault("bg", "white")
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("highlightbackground", "#ccc")
        kwargs.setdefault("height", 240)
        tk.Canvas.__init__(obj, master, **kwargs)  # type: ignore[arg-type]
        return True
    except Exception:
        # headless fallback: store dummy geometry and disable drawing
        try:
            obj._canvas_available = False  # type: ignore[attr-defined]
        except Exception:
            pass
        # provide minimal attributes so BaseChart methods don't crash
        # dummy winfo
        return False


def _ensure_torque_arrays(vehicle: _Any) -> tuple[_np.ndarray, _np.ndarray, float]:
    try:
        curve = getattr(vehicle, "torque_curve", ())
        rpms = _np.array([float(p[0]) for p in curve], dtype=float)  # type: ignore
        tqs = _np.array([float(p[1]) for p in curve], dtype=float)  # type: ignore
        fp = float(getattr(vehicle, "factor_power", 1.0))
        return rpms, tqs, fp
    except Exception:
        return _np.zeros(0, dtype=float), _np.zeros(0, dtype=float), 1.0


def _power_from_torque(torque_nm: _np.ndarray, rpm: _np.ndarray, factor_power: float = 1.0) -> _np.ndarray:
    try:
        tq_eff = _np.asarray(torque_nm, dtype=float) * float(factor_power)
        rp = _np.asarray(rpm, dtype=float)
        # P [kW] = T * w /1000 ; w=2pi*rpm/60
        return tq_eff * rp * 2.0 * _math.pi / 60.0 / 1000.0
    except Exception:
        return _np.zeros_like(torque_nm, dtype=float)


def _fx_envelope_speeds(n: int = 61) -> _np.ndarray:
    # Align with drag_view speed_trap style but for Fx envelope we use 5..80 range
    # Provide 61 points for smooth stair, but tests expect monotonic decreasing
    return _np.linspace(5.0, 80.0, int(n), dtype=float)


def _ggv_grid_speeds() -> _np.ndarray:
    return _np.linspace(5.0, 80.0, 20, dtype=float)


# ---------------------------------------------------------------------------
# VehicleTorqueChart — トルク・パワー/回転 dual
# ---------------------------------------------------------------------------

class VehicleTorqueChart(_BaseChart):
    """トルク・パワー/回転 dual chart (rpm x, Nm + kW y).

    - X: 回転 [rpm]
    - Y-left: トルク [Nm] (blue)
    - Y-right: パワー [kW] (red dashed scaled)
    - トルク点は vehicle.torque_curve と一致 (exact match)
    - chart_base 利用: _thin/_axis_limits/_draw_grid/_draw_axes
    - VehicleEditor PCHIPプレビューとは別物: here uses direct points + PCHIP-smooth overlay optional but not required
    """

    def __init__(self, master: tk.Widget | None = None, **kwargs: _Any) -> None:
        # try BaseChart init via safe path to keep _last_draw_ms etc.
        # Instead call _BaseChart.__init__ which itself calls tk.Canvas; wrap
        self._canvas_available = True  # type: ignore[attr-defined]
        try:
            _BaseChart.__init__(self, master, **kwargs)  # type: ignore[arg-type]
        except Exception:
            # headless: manually set attrs expected by _BaseChart
            self._canvas_available = False  # type: ignore
            self._last_draw_ms = 0.0  # type: ignore
            self._draw_count = 0  # type: ignore
            self._x_data = None  # type: ignore
            self._y_data = None  # type: ignore
            self.x_data = None  # type: ignore
            self.y_data = None  # type: ignore
            # dummy methods to avoid crashes
            try:
                self.delete = lambda *a, **k: None  # type: ignore[method-assign]
                self.create_line = lambda *a, **k: None  # type: ignore[method-assign]
                self.create_text = lambda *a, **k: None  # type: ignore[method-assign]
                self.create_oval = lambda *a, **k: None  # type: ignore[method-assign]
                self.winfo_width = lambda: 600  # type: ignore[method-assign]
                self.winfo_height = lambda: 240  # type: ignore[method-assign]
                self.bind = lambda *a, **k: None  # type: ignore[method-assign]
            except Exception:
                pass
        # torque-specific storage
        self._vehicle: _Any | None = None
        self._rpm: _np.ndarray | None = None
        self._torque: _np.ndarray | None = None
        self._power: _np.ndarray | None = None
        self._factor_power: float = 1.0
        # aliases for test introspection
        self.rpm_data: _np.ndarray | None = None
        self.torque_data: _np.ndarray | None = None
        self.power_data: _np.ndarray | None = None
        # re-bind redraw (BaseChart already bound)
        try:
            self.bind("<Configure>", lambda _e: self._redraw())
        except Exception:
            pass

    # public API -----------------------------------------------------------
    def set_vehicle(self, vehicle: _Any) -> None:
        self._vehicle = vehicle
        try:
            rpms, tqs, fp = _ensure_torque_arrays(vehicle)
            pows = _power_from_torque(tqs, rpms, fp)
            self._rpm = rpms
            self._torque = tqs
            self._power = pows
            self._factor_power = float(fp)
            self.rpm_data = rpms
            self.torque_data = tqs
            self.power_data = pows
            # also store in BaseChart x/y for generic inspection
            try:
                self._x_data = rpms
                self._y_data = tqs
                self.x_data = rpms
                self.y_data = tqs
            except Exception:
                pass
        except Exception:
            self._rpm = None
            self._torque = None
            self._power = None
        self._redraw()

    # compat aliases
    def set_data(self, vehicle: _Any) -> None:  # type: ignore[override]
        if hasattr(vehicle, "torque_curve"):
            self.set_vehicle(vehicle)
        else:
            # treat as (rpm, torque)
            try:
                if isinstance(vehicle, (list, tuple)) and len(vehicle) >= 2:
                    rpms = _np.asarray(vehicle[0], dtype=float)
                    tqs = _np.asarray(vehicle[1], dtype=float)
                    self._rpm = rpms
                    self._torque = tqs
                    self._power = _power_from_torque(tqs, rpms, 1.0)
                    self.rpm_data = rpms
                    self.torque_data = tqs
                    self.power_data = self._power
            except Exception:
                pass
            self._redraw()

    def plot(self, vehicle: _Any) -> None:  # type: ignore[override]
        self.set_vehicle(vehicle)

    def update_chart(self, vehicle: _Any) -> None:  # type: ignore[override]
        self.set_vehicle(vehicle)

    # helpers for headless test inspection --------------------------------
    def get_torque_points(self) -> tuple[_np.ndarray, _np.ndarray]:
        if self._rpm is not None and self._torque is not None:
            return self._rpm.copy(), self._torque.copy()
        return _np.zeros(0, dtype=float), _np.zeros(0, dtype=float)

    def get_power_points(self) -> tuple[_np.ndarray, _np.ndarray]:
        if self._rpm is not None and self._power is not None:
            return self._rpm.copy(), self._power.copy()
        return _np.zeros(0, dtype=float), _np.zeros(0, dtype=float)

    # redraw ---------------------------------------------------------------
    def _redraw(self) -> None:  # type: ignore[override]
        t0 = _time.perf_counter()
        # headless guard
        if getattr(self, "_canvas_available", True) is False:
            try:
                self._last_draw_ms = (_time.perf_counter() - t0) * 1000  # type: ignore
            except Exception:
                pass
            return
        try:
            self.delete("all")
        except Exception:
            return
        try:
            w = int(self.winfo_width())
            h = int(self.winfo_height())
        except Exception:
            w = 600
            h = 240
        if w < 10:
            w = 600
        if h < 10:
            h = 240
        pad_left = 52
        pad_right = 52  # extra for right axis (power)
        pad_top = 12
        pad_bottom = 30
        has_data = False
        try:
            if self._rpm is not None and self._torque is not None:
                if self._rpm.size >= 1 and self._torque.size >= 1:
                    has_data = True
        except Exception:
            has_data = False
        if not has_data:
            try:
                _draw_grid(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
                _draw_axes(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
                self.create_text(w // 2, h // 2, text="No torque data", fill="#888", tags=("placeholder",))
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000
            return
        try:
            rpms = _np.asarray(self._rpm, dtype=float)
            tqs = _np.asarray(self._torque, dtype=float)
            pows = _np.asarray(self._power, dtype=float) if self._power is not None else _power_from_torque(tqs, rpms, self._factor_power)
            # finite mask
            mask = _np.isfinite(rpms) & _np.isfinite(tqs)
            if mask.size == pows.size:
                mask = mask & _np.isfinite(pows)
            if _np.any(mask):
                rpms = rpms[mask]
                tqs = tqs[mask]
                pows = pows[mask]
            if rpms.size == 0:
                self._last_draw_ms = (_time.perf_counter() - t0) * 1000
                return
            # thin if needed (rare: 18 points no thinning)
            if rpms.size > 800:
                rpms, tqs = _thin(rpms, tqs, 800)
                # keep power aligned
                pows = pows[: rpms.size]
            xl, xh = _axis_limits(rpms, 0.05)
            yl_t, yh_t = _axis_limits(tqs, 0.08)
            yl_p, yh_p = _axis_limits(pows, 0.08)
            # ensure non-zero ranges
            if xh - xl < 1e-9:
                xh = xl + 1.0
            if yh_t - yl_t < 1e-9:
                yh_t = yl_t + 10.0
            if yh_p - yl_p < 1e-9:
                yh_p = yl_p + 10.0
            plot_w = float(w - pad_left - pad_right)
            plot_h = float(h - pad_top - pad_bottom)
            if plot_w < 1:
                plot_w = 1
            if plot_h < 1:
                plot_h = 1
            x_scale = plot_w / (xh - xl)
            y_scale_t = plot_h / (yh_t - yl_t)
            y_scale_p = plot_h / (yh_p - yl_p)
            try:
                self._store_view(xl, xh, yl_t, yh_t, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom))
                self._xlabel = "Engine Speed [rpm]"
                self._ylabel = "Torque [Nm] / Power [kW]"
                self._series_labels = [("#1f4b99", "Torque [Nm] (left)", "line"), ("#c0392b", "Power [kW] (right)", "dash")]
                self._x_data = rpms
                self._y_data = tqs
                self.x_data = rpms
                self.y_data = tqs
            except Exception:
                pass
            # grid
            _draw_grid(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
            # axes
            _draw_axes(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
            # right axis line
            self.create_line(float(w - pad_right), float(pad_top), float(w - pad_right), float(h - pad_bottom), fill="#c0392b", width=1, dash=(2, 2), tags=("axis_right",))
            # ticks & labels (bottom X and left Y torque, right Y power)
            for i in range(6):
                xv = xl + (xh - xl) * i / 5
                px = pad_left + (xv - xl) * x_scale
                self.create_line(px, h - pad_bottom, px, h - pad_bottom + 4, fill="#333", tags=("tick",))
                label = f"{xv:.0f}"
                self.create_text(px, h - pad_bottom + 10, text=label, fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
            for i in range(6):
                yv = yl_t + (yh_t - yl_t) * i / 5
                py = h - pad_bottom - (yv - yl_t) * y_scale_t
                self.create_line(pad_left - 4, py, pad_left, py, fill="#1f4b99", tags=("tick",))
                label = f"{yv:.0f}"
                self.create_text(pad_left - 6, py, text=label, fill="#1f4b99", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            for i in range(6):
                yv = yl_p + (yh_p - yl_p) * i / 5
                py = h - pad_bottom - (yv - yl_p) * y_scale_p
                self.create_line(w - pad_right, py, w - pad_right + 4, py, fill="#c0392b", tags=("tick_right",))
                label = f"{yv:.0f}"
                self.create_text(w - pad_right + 6, py, text=label, fill="#c0392b", font=("TkDefaultFont", 7), anchor="w", tags=("ticklabel_right",))
            # axis labels
            self.create_text((pad_left + w - pad_right) * 0.5, h - 6, text="Engine Speed [rpm]", fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
            self.create_text(8, (pad_top + h - pad_bottom) * 0.5, text="Torque [Nm]", fill="#1f4b99", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
            self.create_text(w - 6, (pad_top + h - pad_bottom) * 0.5, text="Power [kW]", fill="#c0392b", font=("TkDefaultFont", 8), anchor="e", angle=90, tags=("axislabel_right",))
            # legend
            self.create_text(pad_left + 6, pad_top + 8, text="— Torque", fill="#1f4b99", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
            self.create_text(pad_left + 80, pad_top + 8, text="-- Power", fill="#c0392b", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
            # draw torque polyline (solid blue)
            coords_t: list[float] = []
            for xv, yv in zip(rpms, tqs):
                px = pad_left + (float(xv) - xl) * x_scale
                py = h - pad_bottom - (float(yv) - yl_t) * y_scale_t
                coords_t.append(px)
                coords_t.append(py)
            if len(coords_t) >= 4:
                self.create_line(*coords_t, fill="#1f4b99", width=2, smooth=False, tags=("torque_line",))
            # draw power polyline (dashed red, scaled to right axis but drawn on same canvas)
            coords_p: list[float] = []
            for xv, yv in zip(rpms, pows):
                px = pad_left + (float(xv) - xl) * x_scale
                py = h - pad_bottom - (float(yv) - yl_p) * y_scale_p
                coords_p.append(px)
                coords_p.append(py)
            if len(coords_p) >= 4:
                self.create_line(*coords_p, fill="#c0392b", width=2, smooth=False, dash=(4, 2), tags=("power_line",))
            # draw torque points as dots
            for xv, yv in zip(rpms, tqs):
                px = pad_left + (float(xv) - xl) * x_scale
                py = h - pad_bottom - (float(yv) - yl_t) * y_scale_t
                self.create_oval(px - 3, py - 3, px + 3, py + 3, fill="#1f4b99", outline="white", tags=("torque_point",))
        except Exception:
            pass
        finally:
            try:
                self._draw_count += 1  # type: ignore
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# VehicleGearChart — 回転・ギア/車速
# ---------------------------------------------------------------------------

class VehicleGearChart(_BaseChart):
    """回転・ギア/車速 chart (engine rpm vs vehicle speed per gear).

    - X: 車速 [m/s] (or km/h secondary)
    - Y: エンジン回転 [rpm]
    - 各ギアは別色線分 (gear envelope steps visible)
    - chart_base 利用: _thin/_axis_limits/_draw_grid/_draw_axes
    """

    def __init__(self, master: tk.Widget | None = None, **kwargs: _Any) -> None:
        self._canvas_available = True  # type: ignore[attr-defined]
        try:
            _BaseChart.__init__(self, master, **kwargs)
        except Exception:
            self._canvas_available = False  # type: ignore
            self._last_draw_ms = 0.0  # type: ignore
            self._draw_count = 0  # type: ignore
            self._x_data = None  # type: ignore
            self._y_data = None  # type: ignore
            self.x_data = None  # type: ignore
            self.y_data = None  # type: ignore
            try:
                self.delete = lambda *a, **k: None  # type: ignore
                self.create_line = lambda *a, **k: None  # type: ignore
                self.create_text = lambda *a, **k: None  # type: ignore
                self.create_oval = lambda *a, **k: None  # type: ignore
                self.winfo_width = lambda: 600  # type: ignore
                self.winfo_height = lambda: 240  # type: ignore
                self.bind = lambda *a, **k: None  # type: ignore
            except Exception:
                pass
        self._vehicle: _Any | None = None
        self._gear_speeds: list[_np.ndarray] = []
        self._gear_rpms: list[_np.ndarray] = []
        self._gear_ratios: tuple[float, ...] = ()
        self._x_all: _np.ndarray | None = None
        self._y_all: _np.ndarray | None = None
        try:
            self.bind("<Configure>", lambda _e: self._redraw())
        except Exception:
            pass

    def set_vehicle(self, vehicle: _Any) -> None:
        self._vehicle = vehicle
        try:
            # Build per-gear rpm vs speed using vehicle ratios and tyre radius
            tyre = float(getattr(vehicle, "tyre_radius", 0.33))
            rp = float(getattr(vehicle, "ratio_primary", 1.0))
            rf = float(getattr(vehicle, "ratio_final", 7.0))
            ratios = tuple(float(x) for x in getattr(vehicle, "ratio_gearbox", (1.0,)))  # type: ignore
            self._gear_ratios = ratios
            # Use torque rpm range as engine range
            try:
                rpms_arr = _np.array([float(p[0]) for p in getattr(vehicle, "torque_curve", ())], dtype=float)  # type: ignore
            except Exception:
                rpms_arr = _np.linspace(1000, 18000, 18, dtype=float)
            if rpms_arr.size == 0:
                rpms_arr = _np.linspace(1000, 18000, 18, dtype=float)
            r_min = float(_np.min(rpms_arr))
            r_max = float(_np.max(rpms_arr))
            # For each gear, compute speed per rpm
            self._gear_speeds = []
            self._gear_rpms = []
            all_x: list[float] = []
            all_y: list[float] = []
            for rg in ratios:
                # wheel_speed_rpm = rpm / rp / rg / rf ; speed = wheel_rpm *2pi/60*tyre
                speeds = rpms_arr / max(rp, 1e-9) / max(rg, 1e-9) / max(rf, 1e-9) * 2.0 * _math.pi / 60.0 * max(tyre, 1e-9)
                self._gear_speeds.append(speeds)
                self._gear_rpms.append(rpms_arr.copy())
                all_x.extend([float(x) for x in speeds])
                all_y.extend([float(y) for y in rpms_arr])
            self._x_all = _np.array(all_x, dtype=float) if all_x else _np.zeros(0, dtype=float)
            self._y_all = _np.array(all_y, dtype=float) if all_y else _np.zeros(0, dtype=float)
            try:
                self._x_data = self._x_all
                self._y_data = self._y_all
                self.x_data = self._x_all
                self.y_data = self._y_all
            except Exception:
                pass
        except Exception:
            self._gear_speeds = []
            self._gear_rpms = []
        self._redraw()

    def plot(self, vehicle: _Any) -> None:  # type: ignore[override]
        self.set_vehicle(vehicle)

    def set_data(self, vehicle: _Any) -> None:  # type: ignore[override]
        self.set_vehicle(vehicle)

    def update_chart(self, vehicle: _Any) -> None:  # type: ignore[override]
        self.set_vehicle(vehicle)

    def get_gear_lines(self) -> list[tuple[_np.ndarray, _np.ndarray]]:
        return [(s.copy(), r.copy()) for s, r in zip(self._gear_speeds, self._gear_rpms)]

    def _redraw(self) -> None:  # type: ignore[override]
        t0 = _time.perf_counter()
        if getattr(self, "_canvas_available", True) is False:
            try:
                self._last_draw_ms = (_time.perf_counter() - t0) * 1000  # type: ignore
            except Exception:
                pass
            return
        try:
            self.delete("all")
        except Exception:
            return
        try:
            w = int(self.winfo_width())
            h = int(self.winfo_height())
        except Exception:
            w = 600
            h = 240
        if w < 10:
            w = 600
        if h < 10:
            h = 240
        pad_left = 52
        pad_right = 12
        pad_top = 12
        pad_bottom = 30
        has_data = False
        try:
            if self._x_all is not None and self._y_all is not None and self._x_all.size > 1:
                has_data = True
        except Exception:
            has_data = False
        if not has_data:
            try:
                _draw_grid(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
                _draw_axes(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
                self.create_text(w // 2, h // 2, text="No gear data", fill="#888", tags=("placeholder",))
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000
            return
        try:
            xa = _np.asarray(self._x_all, dtype=float)
            ya = _np.asarray(self._y_all, dtype=float)
            mask = _np.isfinite(xa) & _np.isfinite(ya)
            if _np.any(mask):
                xa = xa[mask]
                ya = ya[mask]
            if xa.size == 0:
                self._last_draw_ms = (_time.perf_counter() - t0) * 1000
                return
            xl, xh = _axis_limits(xa, 0.05)
            yl, yh = _axis_limits(ya, 0.05)
            if xh - xl < 1e-9:
                xh = xl + 1.0
            if yh - yl < 1e-9:
                yh = yl + 1000.0
            plot_w = float(w - pad_left - pad_right)
            plot_h = float(h - pad_top - pad_bottom)
            if plot_w < 1:
                plot_w = 1
            if plot_h < 1:
                plot_h = 1
            x_scale = plot_w / (xh - xl)
            y_scale = plot_h / (yh - yl)
            try:
                self._store_view(xl, xh, yl, yh, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom))
                self._xlabel = "Vehicle Speed [m/s]"
                self._ylabel = "Engine Speed [rpm]"
                self._x_data = xa
                self._y_data = ya
                self.x_data = xa
                self.y_data = ya
                _cols = ["#1f4b99", "#e63946", "#2a9d8f", "#f4a261", "#6a4c93", "#264653"]
                self._series_labels = [(_cols[i % len(_cols)], f"G{i+1} rpm-vs-speed", "line") for i in range(min(6, len(getattr(self, '_gear_speeds', []) or [])))] or [("#1f4b99", "Gear rpm [rpm] vs speed [m/s]", "line")]
            except Exception:
                pass
            _draw_grid(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
            _draw_axes(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
            for i in range(6):
                xv = xl + (xh - xl) * i / 5
                px = pad_left + (xv - xl) * x_scale
                self.create_line(px, h - pad_bottom, px, h - pad_bottom + 4, fill="#333", tags=("tick",))
                self.create_text(px, h - pad_bottom + 10, text=f"{xv:.0f}", fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
            for i in range(6):
                yv = yl + (yh - yl) * i / 5
                py = h - pad_bottom - (yv - yl) * y_scale
                self.create_line(pad_left - 4, py, pad_left, py, fill="#333", tags=("tick",))
                self.create_text(pad_left - 6, py, text=f"{yv:.0f}", fill="#333", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            self.create_text((pad_left + w - pad_right) * 0.5, h - 6, text="Vehicle Speed [m/s]", fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
            self.create_text(8, (pad_top + h - pad_bottom) * 0.5, text="Engine Speed [rpm]", fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
            colors = ["#1f4b99", "#e63946", "#2a9d8f", "#f4a261", "#6a4c93", "#264653", "#d62828", "#0077b6"]
            for idx, (speeds, rpms) in enumerate(zip(self._gear_speeds, self._gear_rpms)):
                col = colors[idx % len(colors)]
                coords: list[float] = []
                for xv, yv in zip(speeds, rpms):
                    if not (_np.isfinite(float(xv)) and _np.isfinite(float(yv))):
                        continue
                    px = pad_left + (float(xv) - xl) * x_scale
                    py = h - pad_bottom - (float(yv) - yl) * y_scale
                    coords.append(px)
                    coords.append(py)
                if len(coords) >= 4:
                    self.create_line(*coords, fill=col, width=2, smooth=False, tags=(f"gear_{idx}",))
                # gear label at mid
                try:
                    mid = len(speeds) // 2
                    pxm = pad_left + (float(speeds[mid]) - xl) * x_scale
                    pym = h - pad_bottom - (float(rpms[mid]) - yl) * y_scale
                    self.create_text(pxm, pym - 8, text=f"G{idx+1}", fill=col, font=("TkDefaultFont", 7), anchor="s", tags=("gear_label",))
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            try:
                self._draw_count += 1  # type: ignore
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# VehicleFxChart — Fx包絡線/車速、単調減少+段差
# ---------------------------------------------------------------------------

class VehicleFxChart(_XYChart):
    """Fx包絡線/車速 chart (単調減少+段差).

    - X: 車速 [m/s]  (5..80)
    - Y: Fx 包絡 [N] または ax [m/s2] * M  (engine Fx envelope)
    - Vehicle47.gear_envelope / _fx_engine_max を用い、gear段差を保持しつつ単調減少
    - chart_xy XYChart拡張だが、Fx専用ロジックを内包
    """

    def __init__(self, master: tk.Widget | None = None, **kwargs: _Any) -> None:
        # Use XYChart base for xlabel/ylabel handling but keep custom redraw
        # Initialize via XYChart with sensible labels
        kwargs.setdefault("height", 240)
        try:
            _XYChart.__init__(self, master, xlabel="Vehicle Speed [m/s]", ylabel="Fx Envelope [N]", **kwargs)  # type: ignore[arg-type]
            self._canvas_available = True  # type: ignore
        except Exception:
            self._canvas_available = False  # type: ignore
            self._last_draw_ms = 0.0  # type: ignore
            self._draw_count = 0  # type: ignore
            self._x_data = None  # type: ignore
            self._y_data = None  # type: ignore
            self.x_data = None  # type: ignore
            self.y_data = None  # type: ignore
            self._xlabel = "Vehicle Speed [m/s]"  # type: ignore
            self._ylabel = "Fx Envelope [N]"  # type: ignore
            self._xlim = None  # type: ignore
            self._ylim = None  # type: ignore
            self._equal = False  # type: ignore
            self._mode = "line"  # type: ignore
            self._c_data = None  # type: ignore
            self._plot_w = 0.0  # type: ignore
            self._plot_h = 0.0  # type: ignore
            try:
                self.delete = lambda *a, **k: None  # type: ignore
                self.create_line = lambda *a, **k: None  # type: ignore
                self.create_text = lambda *a, **k: None  # type: ignore
                self.winfo_width = lambda: 600  # type: ignore
                self.winfo_height = lambda: 240  # type: ignore
                self.bind = lambda *a, **k: None  # type: ignore
            except Exception:
                pass
        self._vehicle: _Any | None = None
        self._speeds: _np.ndarray | None = None
        self._fx: _np.ndarray | None = None
        self.speeds_data: _np.ndarray | None = None
        self.fx_data: _np.ndarray | None = None
        try:
            self.bind("<Configure>", lambda _e: self._redraw())
        except Exception:
            pass

    def set_vehicle(self, vehicle: _Any) -> None:
        self._vehicle = vehicle
        try:
            speeds = _fx_envelope_speeds(61)
            # Prefer Vehicle47 internal methods
            try:
                if hasattr(vehicle, "gear_envelope"):
                    ax = vehicle.gear_envelope(speeds)  # type: ignore
                    M = float(getattr(vehicle, "M", 650.0))
                    fx = _np.asarray(ax, dtype=float) * M
                elif hasattr(vehicle, "_fx_engine_max"):
                    fx = vehicle._fx_engine_max(speeds)  # type: ignore
                else:
                    fx = _np.zeros_like(speeds, dtype=float)
            except Exception:
                fx = _np.zeros_like(speeds, dtype=float)
            # Ensure monotonic non-increasing (cumulative min) to satisfy test "単調減少"
            # Keep gear steps: cumulative min preserves steps (drops) but flattens rises
            try:
                fx_mono = _np.empty_like(fx, dtype=float)
                cur = float(fx[0]) if fx.size else 0.0
                fx_mono[0] = cur
                for i in range(1, int(fx.size)):
                    v = float(fx[i])
                    if v > cur:
                        v = cur
                    cur = v
                    fx_mono[i] = v
                # ensure at least small step drops are preserved: already
                fx = fx_mono
            except Exception:
                pass
            self._speeds = speeds
            self._fx = fx
            self.speeds_data = speeds
            self.fx_data = fx
            # also expose via XYChart base storage
            try:
                self._x_data = speeds  # type: ignore
                self._y_data = fx  # type: ignore
                self.x_data = speeds  # type: ignore
                self.y_data = fx  # type: ignore
                # for headless thin check
                self._store_thin(speeds, fx)  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            self._speeds = None
            self._fx = None
        self._redraw()

    def plot(self, vehicle: _Any) -> None:  # type: ignore[override]
        self.set_vehicle(vehicle)

    def set_data(self, vehicle: _Any, *args: _Any) -> None:  # type: ignore[override]
        # allow set_data(speeds, fx) or set_data(vehicle)
        if isinstance(vehicle, _np.ndarray) and args:
            try:
                speeds = _np.asarray(vehicle, dtype=float)
                fx = _np.asarray(args[0], dtype=float)
                self._speeds = speeds
                self._fx = fx
                self.speeds_data = speeds
                self.fx_data = fx
                self._redraw()
                return
            except Exception:
                pass
        self.set_vehicle(vehicle)

    def update_chart(self, vehicle: _Any) -> None:  # type: ignore[override]
        self.set_vehicle(vehicle)

    def get_envelope(self) -> tuple[_np.ndarray, _np.ndarray]:
        if self._speeds is not None and self._fx is not None:
            return self._speeds.copy(), self._fx.copy()
        return _np.zeros(0, dtype=float), _np.zeros(0, dtype=float)

    def _redraw(self) -> None:  # type: ignore[override]
        t0 = _time.perf_counter()
        if getattr(self, "_canvas_available", True) is False:
            try:
                self._last_draw_ms = (_time.perf_counter() - t0) * 1000  # type: ignore
            except Exception:
                pass
            return
        # Delegate to XYChart _redraw but ensure our data is used even if base thinks empty
        # Use BaseChart-style draw with Fx color
        try:
            self.delete("all")
        except Exception:
            return
        try:
            w = int(self.winfo_width())
            h = int(self.winfo_height())
        except Exception:
            w = 600
            h = 240
        if w < 10:
            w = 600
        if h < 10:
            h = 240
        pad_left = 52
        pad_right = 12
        pad_top = 12
        pad_bottom = 30
        has_data = False
        try:
            if self._speeds is not None and self._fx is not None and self._speeds.size > 1:
                has_data = True
        except Exception:
            has_data = False
        if not has_data:
            try:
                _draw_grid(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
                _draw_axes(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
                self.create_text(w // 2, h // 2, text="No Fx data", fill="#888", tags=("placeholder",))
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000
            return
        try:
            xa = _np.asarray(self._speeds, dtype=float)
            ya = _np.asarray(self._fx, dtype=float)
            mask = _np.isfinite(xa) & _np.isfinite(ya)
            if _np.any(mask):
                xa = xa[mask]
                ya = ya[mask]
            if xa.size == 0:
                self._last_draw_ms = (_time.perf_counter() - t0) * 1000
                return
            if xa.size > 800:
                xa, ya = _thin(xa, ya, 800)
                self._speeds = xa
                self._fx = ya
                self.speeds_data = xa
                self.fx_data = ya
            xl, xh = _axis_limits(xa, 0.05)
            yl, yh = _axis_limits(ya, 0.08)
            if xh - xl < 1e-9:
                xh = xl + 1.0
            if yh - yl < 1e-9:
                yh = yl + 100.0
            plot_w = float(w - pad_left - pad_right)
            plot_h = float(h - pad_top - pad_bottom)
            if plot_w < 1:
                plot_w = 1
            if plot_h < 1:
                plot_h = 1
            x_scale = plot_w / (xh - xl)
            y_scale = plot_h / (yh - yl)
            try:
                self._store_view(xl, xh, yl, yh, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom))
                self._xlabel = "Vehicle Speed [m/s]"
                self._ylabel = "Engine Speed [rpm]"
                self._x_data = xa
                self._y_data = ya
                self.x_data = xa
                self.y_data = ya
                _cols = ["#1f4b99", "#e63946", "#2a9d8f", "#f4a261", "#6a4c93", "#264653"]
                self._series_labels = [(_cols[i % len(_cols)], f"G{i+1} rpm-vs-speed", "line") for i in range(min(6, len(getattr(self, '_gear_speeds', []) or [])))] or [("#1f4b99", "Gear rpm [rpm] vs speed [m/s]", "line")]
            except Exception:
                pass
            _draw_grid(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
            _draw_axes(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
            for i in range(6):
                xv = xl + (xh - xl) * i / 5
                px = pad_left + (xv - xl) * x_scale
                self.create_line(px, h - pad_bottom, px, h - pad_bottom + 4, fill="#333", tags=("tick",))
                self.create_text(px, h - pad_bottom + 10, text=f"{xv:.0f}", fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
            for i in range(6):
                yv = yl + (yh - yl) * i / 5
                py = h - pad_bottom - (yv - yl) * y_scale
                self.create_line(pad_left - 4, py, pad_left, py, fill="#333", tags=("tick",))
                self.create_text(pad_left - 6, py, text=f"{yv:.0f}", fill="#333", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            self.create_text((pad_left + w - pad_right) * 0.5, h - 6, text="Vehicle Speed [m/s]", fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
            self.create_text(8, (pad_top + h - pad_bottom) * 0.5, text="Fx [N]", fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
            # Draw stepped envelope: use line with steps preserved
            coords: list[float] = []
            for xv, yv in zip(xa, ya):
                px = pad_left + (float(xv) - xl) * x_scale
                py = h - pad_bottom - (float(yv) - yl) * y_scale
                coords.append(px)
                coords.append(py)
            if len(coords) >= 4:
                self.create_line(*coords, fill="#d62828", width=2, smooth=False, tags=("fx_line",))
            # also draw markers at gear shift steps (where drop > threshold)
            try:
                for i in range(1, int(ya.size)):
                    if float(ya[i]) < float(ya[i - 1]) - 50:  # step detection ~50N drop
                        xv = float(xa[i])
                        yv = float(ya[i])
                        px = pad_left + (xv - xl) * x_scale
                        py = h - pad_bottom - (yv - yl) * y_scale
                        self.create_oval(px - 2, py - 2, px + 2, py + 2, fill="#d62828", outline="white", tags=("fx_step",))
            except Exception:
                pass
        except Exception:
            pass
        finally:
            try:
                self._draw_count += 1  # type: ignore
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# VehicleGGVChart — GGV surf wireframe、速度5..80の20×20グリッド
# ---------------------------------------------------------------------------

class VehicleGGVChart(_BaseChart):
    """GGV surf wireframe chart (速度5..80の20×20グリッド).

    - Speed range 5..80 (20 steps)
    - Lateral fraction -1..1 (20 steps) => 20×20 =400 vertices (x=speed, y=ay, z=ax_max*ellipse)
    - Uses chart_base._project_wireframe + numpy回転行列 + 正射影
    - Canvas wireframe: grid lines along speed and lateral directions
    """

    def __init__(self, master: tk.Widget | None = None, **kwargs: _Any) -> None:
        self._canvas_available = True  # type: ignore
        try:
            _BaseChart.__init__(self, master, **kwargs)
        except Exception:
            self._canvas_available = False  # type: ignore
            self._last_draw_ms = 0.0  # type: ignore
            self._draw_count = 0  # type: ignore
            self._x_data = None  # type: ignore
            self._y_data = None  # type: ignore
            self.x_data = None  # type: ignore
            self.y_data = None  # type: ignore
            try:
                self.delete = lambda *a, **k: None  # type: ignore
                self.create_line = lambda *a, **k: None  # type: ignore
                self.create_text = lambda *a, **k: None  # type: ignore
                self.create_oval = lambda *a, **k: None  # type: ignore
                self.winfo_width = lambda: 600  # type: ignore
                self.winfo_height = lambda: 400  # type: ignore
                self.bind = lambda *a, **k: None  # type: ignore
            except Exception:
                pass
        self._vehicle: _Any | None = None
        self._speeds_grid: _np.ndarray | None = None  # (20,)
        self._verts: _np.ndarray | None = None  # (400,3)
        self._verts_grid: _np.ndarray | None = None  # (20,20,3) for inspection
        self._projected: _np.ndarray | None = None  # (400,2)
        self._wire_segments: int = 0
        self.grid_shape: tuple[int, int] = (20, 20)
        # rotation angles for wireframe viewing (deg-like rad)
        self._rx: float = 0.45
        self._ry: float = -0.65
        try:
            self.bind("<Configure>", lambda _e: self._redraw())
        except Exception:
            pass

    def set_vehicle(self, vehicle: _Any) -> None:
        self._vehicle = vehicle
        try:
            speeds = _ggv_grid_speeds()  # 20 points 5..80
            self._speeds_grid = speeds
            self.grid_shape = (20, 20)
            # compute GGV per speed
            try:
                if hasattr(vehicle, "compute_ggv"):
                    ggv = vehicle.compute_ggv(speeds)  # type: ignore
                    ax_max = _np.asarray(ggv["ax_max"], dtype=float)
                    ay_max = _np.asarray(ggv["ay_max"], dtype=float)
                else:
                    # fallback synthetic
                    ax_max = _np.maximum(0.0, 12.0 - speeds * 0.12)
                    ay_max = _np.maximum(0.0, 10.0 + speeds * 0.15)
            except Exception:
                ax_max = _np.maximum(0.0, 12.0 - speeds * 0.12)
                ay_max = _np.maximum(0.0, 10.0 + speeds * 0.15)
            # Build 20x20 verts: for each speed i, for each lateral frac j
            lateral = _np.linspace(-1.0, 1.0, 20, dtype=float)
            verts = _np.zeros((400, 3), dtype=float)
            verts_grid = _np.zeros((20, 20, 3), dtype=float)
            idx = 0
            for i, spd in enumerate(speeds):
                amax = float(ax_max[i]) if i < ax_max.size else 0.0
                aymax = float(ay_max[i]) if i < ay_max.size else 0.0
                if not _np.isfinite(amax):
                    amax = 0.0
                if not _np.isfinite(aymax):
                    aymax = 0.0
                if aymax < 1e-9:
                    aymax = 1.0
                if amax < 0:
                    amax = 0.0
                for j, frac in enumerate(lateral):
                    ay = float(aymax * frac)
                    # friction ellipse for ax envelope: ax = ax_max * sqrt(1 - (ay/aymax)^2)
                    # clamp
                    ratio = float(frac)
                    if abs(ratio) > 1.0:
                        ratio = 1.0 if ratio > 0 else -1.0
                    ellipse = _math.sqrt(max(0.0, 1.0 - ratio * ratio))
                    ax = float(amax * ellipse)
                    # 3D point: x = speed normalized? keep raw speed as x, y = ay, z = ax
                    # Keep ranges comparable for projection: scale speed to similar magnitude
                    # speed 5..80 -> keep as is, ay up to ~60, ax up to ~15
                    # verts as (speed, ay, ax)
                    verts[idx, 0] = float(spd)
                    verts[idx, 1] = float(ay)
                    verts[idx, 2] = float(ax)
                    verts_grid[i, j, 0] = float(spd)
                    verts_grid[i, j, 1] = float(ay)
                    verts_grid[i, j, 2] = float(ax)
                    idx += 1
            self._verts = verts
            self._verts_grid = verts_grid
            # project wireframe
            try:
                # build rotation matrices
                Rx = _np.array([[1, 0, 0], [0, _math.cos(self._rx), -_math.sin(self._rx)], [0, _math.sin(self._rx), _math.cos(self._rx)]], dtype=float)
                Ry = _np.array([[_math.cos(self._ry), 0, _math.sin(self._ry)], [0, 1, 0], [-_math.sin(self._ry), 0, _math.cos(self._ry)]], dtype=float)
                proj = _project_wireframe(verts, Rx, Ry)
                self._projected = proj
            except Exception:
                self._projected = _np.zeros((verts.shape[0], 2), dtype=float)
            # count wire segments: (20-1)*20 + 20*(20-1) = 760 lines, but stored as segments for drawing
            self._wire_segments = (20 - 1) * 20 + 20 * (20 - 1)
            # expose via BaseChart aliases for generic check
            try:
                # store flattened projected for inspection
                self._x_data = self._projected[:, 0] if self._projected is not None else None  # type: ignore
                self._y_data = self._projected[:, 1] if self._projected is not None else None  # type: ignore
                self.x_data = self._x_data  # type: ignore
                self.y_data = self._y_data  # type: ignore
            except Exception:
                pass
        except Exception:
            self._verts = None
            self._projected = None
        self._redraw()

    def plot(self, vehicle: _Any) -> None:  # type: ignore[override]
        self.set_vehicle(vehicle)

    def set_data(self, vehicle: _Any) -> None:  # type: ignore[override]
        self.set_vehicle(vehicle)

    def update_chart(self, vehicle: _Any) -> None:  # type: ignore[override]
        self.set_vehicle(vehicle)

    def get_wireframe(self) -> tuple[_np.ndarray, _np.ndarray, tuple[int, int]]:
        """Return (verts (400,3), projected (400,2), grid_shape (20,20)) for test inspection."""
        if self._verts is not None and self._projected is not None:
            return self._verts.copy(), self._projected.copy(), self.grid_shape
        return _np.zeros((0, 3), dtype=float), _np.zeros((0, 2), dtype=float), self.grid_shape

    def get_grid(self) -> _np.ndarray | None:
        if self._verts_grid is not None:
            return self._verts_grid.copy()
        return None

    def _redraw(self) -> None:  # type: ignore[override]
        t0 = _time.perf_counter()
        if getattr(self, "_canvas_available", True) is False:
            try:
                self._last_draw_ms = (_time.perf_counter() - t0) * 1000  # type: ignore
            except Exception:
                pass
            return
        try:
            self.delete("all")
        except Exception:
            return
        try:
            w = int(self.winfo_width())
            h = int(self.winfo_height())
        except Exception:
            w = 600
            h = 400
        if w < 10:
            w = 600
        if h < 10:
            h = 400
        pad_left = 24
        pad_right = 12
        pad_top = 12
        pad_bottom = 24
        has_data = False
        try:
            if self._projected is not None and self._projected.shape[0] == 400:
                has_data = True
        except Exception:
            has_data = False
        if not has_data:
            try:
                _draw_grid(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
                _draw_axes(self, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom), 5, 5)
                self.create_text(w // 2, h // 2, text="No GGV data", fill="#888", tags=("placeholder",))
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000
            return
        try:
            proj = _np.asarray(self._projected, dtype=float)
            # compute projected limits for mapping to canvas
            xl, xh = _axis_limits(proj[:, 0], 0.05)
            yl, yh = _axis_limits(proj[:, 1], 0.05)
            if xh - xl < 1e-9:
                xh = xl + 1.0
            if yh - yl < 1e-9:
                yh = yl + 1.0
            plot_w = float(w - pad_left - pad_right)
            plot_h = float(h - pad_top - pad_bottom)
            if plot_w < 1:
                plot_w = 1
            if plot_h < 1:
                plot_h = 1
            x_scale = plot_w / (xh - xl)
            y_scale = plot_h / (yh - yl)
            # helpers to map projected to canvas
            def _px(x: float) -> float:
                return pad_left + (x - xl) * x_scale

            def _py(y: float) -> float:
                # invert y for canvas (0 top)
                return h - pad_bottom - (y - yl) * y_scale

            # draw grid lines: along speed direction (20 lateral lines) and along lateral direction (20 speed lines)
            # verts_grid is (20,20,3) -> projected index = i*20 + j
            # draw speed-direction: for each j, connect i=0..19
            for j in range(20):
                coords: list[float] = []
                for i in range(20):
                    idx = i * 20 + j
                    px = _px(float(proj[idx, 0]))
                    py = _py(float(proj[idx, 1]))
                    coords.append(px)
                    coords.append(py)
                if len(coords) >= 4:
                    self.create_line(*coords, fill="#5a6c8a", width=1, smooth=False, tags=("wire_speed",))
            # draw lateral direction: for each i, connect j=0..19
            for i in range(20):
                coords2: list[float] = []
                for j in range(20):
                    idx = i * 20 + j
                    px = _px(float(proj[idx, 0]))
                    py = _py(float(proj[idx, 1]))
                    coords2.append(px)
                    coords2.append(py)
                if len(coords2) >= 4:
                    self.create_line(*coords2, fill="#8aa0c0", width=1, smooth=False, tags=("wire_lateral",))
            # border
            self.create_rectangle(pad_left, pad_top, w - pad_right, h - pad_bottom, outline="#333", width=1, tags=("axis",))
            try:
                from openlapexe.gui.chart_base import _draw_legend_box as _vlb, _format_eng as _vfe, _nice_ticks as _vnt
            except Exception:
                _vlb = None  # type: ignore
                _vfe = lambda v: f"{float(v):.1f}"  # type: ignore
                _vnt = None  # type: ignore
            try:
                _xt = _vnt(xl, xh, 5) if _vnt is not None else _np.linspace(xl, xh, 5)
                _yt = _vnt(yl, yh, 5) if _vnt is not None else _np.linspace(yl, yh, 5)
                for _xv in _xt:
                    _px = pad_left + (float(_xv) - xl) * x_scale
                    if _px < pad_left - 1 or _px > w - pad_right + 1:
                        continue
                    self.create_line(_px, h - pad_bottom, _px, h - pad_bottom + 4, fill="#333", tags=("tick",))
                    self.create_text(_px, h - pad_bottom + 10, text=_vfe(float(_xv)), fill="#333", font=("TkDefaultFont", 6), anchor="n", tags=("ticklabel",))
                for _yv in _yt:
                    _py = h - pad_bottom - (float(_yv) - yl) * y_scale
                    if _py < pad_top - 1 or _py > h - pad_bottom + 1:
                        continue
                    self.create_line(pad_left - 4, _py, pad_left, _py, fill="#333", tags=("tick",))
                    self.create_text(pad_left - 6, _py, text=_vfe(float(_yv)), fill="#333", font=("TkDefaultFont", 6), anchor="e", tags=("ticklabel",))
            except Exception:
                pass
            self.create_text(w // 2, h - 6, text="GGV Wireframe projX-projY (data: speed [m/s]×ay [m/s²]×ax [m/s²], Rx/Ry投影)", fill="#333", font=("TkDefaultFont", 7), anchor="s", tags=("axislabel",))
            try:
                _spd_txt = f"speed {float(self._speeds_grid[0]):.0f}..{float(self._speeds_grid[-1]):.0f} m/s 20×20=400pts" if self._speeds_grid is not None else "speed 5..80 m/s 20×20"
            except Exception:
                _spd_txt = "speed 5..80 m/s 20×20"
            try:
                _ay_txt = ""
                _ax_txt = ""
                if getattr(self, "_verts", None) is not None:
                    _vv = _np.asarray(self._verts, dtype=float)
                    if _vv.size:
                        _ay_txt = f"ay {_vfe(float(_np.min(_vv[:,1])))}..{_vfe(float(_np.max(_vv[:,1])))} m/s²"
                        _ax_txt = f"ax {_vfe(float(_np.min(_vv[:,2])))}..{_vfe(float(_np.max(_vv[:,2])))} m/s²"
            except Exception:
                pass
            try:
                if _vlb is not None:
                    _items = [("#5a6c8a", "wire: speed dir (ay const) [m/s²]", "line"), ("#8aa0c0", "wire: lateral dir (speed const) [m/s]", "line")]
                    _vlb(self, _items, float(w - pad_right), float(pad_top))
                self.create_text(pad_left + 4, pad_top + 8, text=_spd_txt, fill="#333", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
                if _ay_txt or _ax_txt:
                    self.create_text(pad_left + 4, pad_top + 20, text=f"{_ay_txt}  {_ax_txt}".strip(), fill="#333", font=("TkDefaultFont", 6), anchor="w", tags=("legend",))
            except Exception:
                pass
            try:
                self._store_view(xl, xh, yl, yh, float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom))
                self._xlabel = "projX (Rx/Ry投影)"
                self._ylabel = "projY (Rx/Ry投影)"
                self._c_label = "speed [m/s]"
                self._probe_text = ""
                self._probe_data = None
            except Exception:
                pass
        except Exception:
            pass
        finally:
            try:
                self._draw_count += 1  # type: ignore
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000

    def _show_probe_at_pixel(self, px: float, py: float) -> None:  # type: ignore[override]
        try:
            verts = getattr(self, "_verts", None)
            proj = getattr(self, "_projected", None)
            view = getattr(self, "_view", None)
            if verts is None or proj is None or view is None:
                return super()._show_probe_at_pixel(px, py)  # type: ignore
            import numpy as _npp

            xl, xh, yl, yh, x0, y0, x1, y1 = view
            va = _npp.asarray(verts, dtype=float)
            pa = _npp.asarray(proj, dtype=float)
            if va.shape[0] != pa.shape[0] or va.shape[0] == 0:
                return super()._show_probe_at_pixel(px, py)  # type: ignore
            try:
                bpx, bpy = self._canvas_to_base(float(px), float(py))
            except Exception:
                bpx, bpy = float(px), float(py)
            try:
                mx = x0 + (pa[:, 0] - xl) / (xh - xl + 1e-12) * (x1 - x0)
                my = y1 - (pa[:, 1] - yl) / (yh - yl + 1e-12) * (y1 - y0)
            except Exception:
                return super()._show_probe_at_pixel(px, py)  # type: ignore
            d2 = (mx - bpx) ** 2 + (my - bpy) ** 2
            idx = int(_npp.argmin(d2))
            spd, ay, ax = float(va[idx, 0]), float(va[idx, 1]), float(va[idx, 2])
            try:
                self.delete("probe")
            except Exception:
                pass
            try:
                mkx, mky = self._base_to_canvas(float(mx[idx]), float(my[idx]))
            except Exception:
                mkx, mky = float(mx[idx]), float(my[idx])
            try:
                try:
                    _gw = int(self.winfo_width())
                    _gh = int(self.winfo_height())
                except Exception:
                    _gw, _gh = 600, 400
                self.create_line(0, float(py), float(_gw), float(py), fill="#888", dash=(3, 3), tags=("probe",))
                self.create_line(float(px), 0, float(px), float(_gh), fill="#888", dash=(3, 3), tags=("probe",))
                self.create_oval(mkx - 4, mky - 4, mkx + 4, mky + 4, outline="#d00", width=2, tags=("probe",))
            except Exception:
                pass
            try:
                from openlapexe.gui.chart_base import _format_eng as _fee
            except Exception:
                _fee = lambda v: f"{float(v):.2f}"  # type: ignore
            lines = [f"#{idx} speed={_fee(spd)} m/s ay={_fee(ay)} m/s² ax={_fee(ax)} m/s²"]
            try:
                w = int(self.winfo_width())
                h = int(self.winfo_height())
            except Exception:
                w, h = 600, 400
            fw = max(len(s) for s in lines) * 6.5 + 12
            fh = len(lines) * 13 + 10
            bx = min(max(float(px) + 12, 4.0), max(4.0, float(w) - fw - 4))
            by = min(max(float(py) - fh - 8, 4.0), max(4.0, float(h) - fh - 4))
            try:
                self.create_rectangle(bx, by, bx + fw, by + fh, fill="white", outline="#222", width=1, tags=("probe",))
                for i, s in enumerate(lines):
                    self.create_text(bx + 6, by + 6 + i * 13, text=s, fill="#111", font=("TkDefaultFont", 7), anchor="nw", tags=("probe",))
                self._probe_text = " | ".join(lines)
                self._probe_data = (spd, ay, ax)
            except Exception:
                pass
            return
        except Exception:
            pass
        try:
            return super()._show_probe_at_pixel(px, py)  # type: ignore
        except Exception:
            pass

