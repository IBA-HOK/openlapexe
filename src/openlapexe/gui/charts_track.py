# allow: SIZE_OK — Track2 8列から原典OpenTRACK 6種Canvas再現 単一責務 (GUI, TrackViewミニマップと重複せず)
# -*- coding: utf-8 -*-
"""openlapexe.gui.charts_track - Track2 8列から原典OpenTRACK 6種 Canvas再現 (mpl/sci-py禁止).

原典 OpenTRACK 6種をCanvas再現 (別名, TrackViewミニマップと重複させず):
- TrackMapChart(axis equal地図+曲率overlay)
- TrackCurvChart(曲率/距離)
- TrackElevChart(標高/距離)
- TrackGradChart(勾配dz/ds/距離)
- TrackBankChart(バンク/距離)
- TrackGripChart(グリップ/距離 0.8..1.2想定)

要件:
- chart_xy/chart_base利用, mpl禁止
- track.py改変禁止, 既存名再利用禁止 (SpeedChart/GGChart/SectorChart/Vehicle*/Results* 不使用)
- Track2の8列配列 s,x,y,z,curv,bank_rad,grip_factor,sector_id から描画
- chart_xy.XYChart / chart_base.BaseChart 継承, <Configure>再描画, bg white, grid #e0e0e0, axes #333
- 800点間引き (決定論的 slice), _last_draw_ms計測
"""

from __future__ import annotations

import math as _math
import time as _time
import tkinter as tk

import numpy as _np

from openlapexe.gui.chart_base import BaseChart as _BaseChart, _axis_limits, _draw_axes, _draw_grid, _thin
from openlapexe.gui.chart_xy import XYChart as _XYChart, _color_for_value, _thin_triple

__all__ = [
    "TrackMapChart",
    "TrackCurvChart",
    "TrackElevChart",
    "TrackGradChart",
    "TrackBankChart",
    "TrackGripChart",
]


# ---------------------------------------------------------------------------
# helpers: Track2 -> arrays
# ---------------------------------------------------------------------------

def _get_points(obj: object) -> _np.ndarray | None:
    if obj is None:
        return None
    # ndarray directly
    try:
        if isinstance(obj, _np.ndarray):
            arr = _np.asarray(obj, dtype=float)
            if arr.ndim == 2 and arr.shape[1] >= 2:
                return arr
            return None
    except Exception:
        pass
    # Track-like with .points
    try:
        pts = getattr(obj, "points", None)
        if pts is not None:
            arr = _np.asarray(pts, dtype=float)
            if arr.ndim == 2 and arr.shape[0] >= 1:
                return arr
            if arr.ndim == 1 and arr.size == 0:
                return arr.reshape(0, 8)
    except Exception:
        pass
    # fallback: object itself may be array-like list of dicts? ignore
    try:
        arr = _np.asarray(obj, dtype=float)  # type: ignore
        if arr.ndim == 2 and arr.shape[1] >= 5:
            return arr
    except Exception:
        pass
    return None


def _extract_track_columns(obj: object) -> dict[str, _np.ndarray] | None:
    pts = _get_points(obj)
    if pts is None:
        # maybe obj has s/x/y/z etc directly? try s attribute
        try:
            s = getattr(obj, "s", None)
            x = getattr(obj, "x", None)
            y = getattr(obj, "y", None)
            if s is not None and x is not None and y is not None:
                s_a = _np.asarray(s, dtype=float).ravel()
                x_a = _np.asarray(x, dtype=float).ravel()
                y_a = _np.asarray(y, dtype=float).ravel()
                n = min(int(s_a.shape[0]), int(x_a.shape[0]), int(y_a.shape[0]))
                s_a = s_a[:n]; x_a = x_a[:n]; y_a = y_a[:n]
                z_a = _np.zeros(n, dtype=float)
                curv_a = _np.zeros(n, dtype=float)
                bank_a = _np.zeros(n, dtype=float)
                grip_a = _np.ones(n, dtype=float)
                sector_a = _np.zeros(n, dtype=float)
                try:
                    zv = getattr(obj, "z", None)
                    if zv is not None:
                        z_a = _np.asarray(zv, dtype=float).ravel()[:n]
                except Exception:
                    pass
                try:
                    cv = getattr(obj, "curv", None)
                    if cv is None:
                        cv = getattr(obj, "curvature", None)
                    if cv is not None:
                        curv_a = _np.asarray(cv, dtype=float).ravel()[:n]
                except Exception:
                    pass
                return {"s": s_a, "x": x_a, "y": y_a, "z": z_a, "curv": curv_a, "bank": bank_a, "grip": grip_a, "sector": sector_a}
        except Exception:
            pass
        return None
    try:
        arr = _np.asarray(pts, dtype=float)
        if arr.size == 0:
            return None
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        n = int(arr.shape[0])
        m = int(arr.shape[1])
        # columns: s,x,y,z,curv,bank,grip,sector
        def _col(i: int, default: float) -> _np.ndarray:
            if m > i:
                return _np.asarray(arr[:, i], dtype=float)
            return _np.full(n, float(default), dtype=float)
        s = _col(0, 0.0)
        x = _col(1, 0.0)
        y = _col(2, 0.0)
        z = _col(3, 0.0)
        curv = _col(4, 0.0)
        bank = _col(5, 0.0)
        grip = _col(6, 1.0)
        sector = _col(7, 0.0)
        # if s is all zero but n>1, synthesize s as cumulative
        try:
            if _np.all(s == 0) and n > 1:
                # try to use _s attribute if available
                if hasattr(obj, "_s"):
                    try:
                        s2 = _np.asarray(getattr(obj, "_s"), dtype=float).ravel()
                        if s2.size == n:
                            s = s2
                    except Exception:
                        pass
        except Exception:
            pass
        return {"s": s, "x": x, "y": y, "z": z, "curv": curv, "bank": bank, "grip": grip, "sector": sector}
    except Exception:
        return None


def _compute_gradient(s: _np.ndarray, z: _np.ndarray) -> _np.ndarray:
    try:
        sa = _np.asarray(s, dtype=float).ravel()
        za = _np.asarray(z, dtype=float).ravel()
        n = min(int(sa.shape[0]), int(za.shape[0]))
        sa = sa[:n]
        za = za[:n]
        if n < 2:
            return _np.zeros(n, dtype=float)
        # ensure s monotonic increasing; if not, sort
        try:
            if _np.any(_np.diff(sa) <= 0):
                order = _np.argsort(sa)
                sa = sa[order]
                za = za[order]
        except Exception:
            pass
        # use np.gradient with edge handling; replace non-finite s diff
        try:
            grad = _np.gradient(za, sa, edge_order=1)  # type: ignore
        except Exception:
            # fallback diff
            ds = _np.diff(sa)
            dz = _np.diff(za)
            # avoid zero ds
            ds = _np.where(_np.abs(ds) < 1e-9, 1e-9, ds)
            g = dz / ds
            grad = _np.zeros(n, dtype=float)
            grad[1:-1] = (g[:-1] + g[1:]) * 0.5
            grad[0] = g[0]
            grad[-1] = g[-1]
        # sanitize: replace non-finite with 0 or nearest finite
        grad = _np.asarray(grad, dtype=float)
        mask = ~_np.isfinite(grad)
        if _np.any(mask):
            grad[mask] = 0.0
        # clip extreme to avoid spikes from duplicate s
        # keep within reasonable road grade +-0.5 (50%)
        grad = _np.clip(grad, -1.0, 1.0)
        return grad
    except Exception:
        try:
            n = int(_np.asarray(s).size)
            return _np.zeros(n, dtype=float)
        except Exception:
            return _np.zeros(0, dtype=float)


# ---------------------------------------------------------------------------
# TrackMapChart — axis equal地図 + 曲率overlay
# ---------------------------------------------------------------------------

class TrackMapChart(_XYChart):
    """Track map (axis equal) + 曲率overlay (color_by curvature)."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "X [m]")
        kwargs.setdefault("ylabel", "Y [m]")
        kwargs.setdefault("equal", True)
        super().__init__(master, **kwargs)  # type: ignore[arg-type]
        # ensure equal
        try:
            self._equal = True
        except Exception:
            pass
        self._track_obj: object | None = None
        self._s_map: _np.ndarray | None = None
        try:
            self._c_label = "Curvature [1/m]"
            self._series_labels = [("#1f4b99", "Track (X-Y [m], color=curvature [1/m])", "line")]
        except Exception:
            pass

    def set_track(self, track: object) -> None:
        self._track_obj = track
        cols = _extract_track_columns(track)
        if cols is None:
            # try ndarray directly
            pts = _get_points(track)
            if pts is None:
                self._s_map = None
                self._redraw()
                return
            cols = _extract_track_columns(pts)
            if cols is None:
                self._redraw()
                return
        try:
            x = _np.asarray(cols["x"], dtype=float)
            y = _np.asarray(cols["y"], dtype=float)
            curv = _np.asarray(cols["curv"], dtype=float)
            self._s_map = _np.asarray(cols["s"], dtype=float)
            # use colored draw for curvature overlay
            # ensure finite
            mask = _np.isfinite(x) & _np.isfinite(y) & _np.isfinite(curv)
            if _np.any(mask):
                x = x[mask]; y = y[mask]; curv = curv[mask]
                self._s_map = self._s_map[mask]
            self.draw_colored(x, y, curv)
        except Exception:
            try:
                self._redraw()
            except Exception:
                pass

    # aliases
    def set_data(self, track: object, *args: object) -> None:  # type: ignore[override]
        if args:
            # treat as (x,y) direct
            try:
                x = _np.asarray(track, dtype=float)
                y = _np.asarray(args[0], dtype=float)
                c = args[1] if len(args) > 1 else None
                if c is not None:
                    self.draw_colored(x, y, c)
                else:
                    self.draw_line(x, y)
                return
            except Exception:
                pass
        self.set_track(track)

    def plot(self, track: object) -> None:  # type: ignore[override]
        self.set_track(track)

    def update_chart(self, track: object) -> None:  # type: ignore[override]
        self.set_track(track)

    # ensure _redraw keeps equal true (in case user toggled)
    def _redraw(self) -> None:  # type: ignore[override]
        try:
            self._equal = True
        except Exception:
            pass
        super()._redraw()


# ---------------------------------------------------------------------------
# TrackCurvChart — 曲率/距離
# ---------------------------------------------------------------------------

class TrackCurvChart(_XYChart):
    """Curvature vs Distance."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "Curvature [1/m]")
        super().__init__(master, **kwargs)  # type: ignore[arg-type]
        self._s_curv: _np.ndarray | None = None
        self._curv: _np.ndarray | None = None

    def set_track(self, track: object) -> None:
        cols = _extract_track_columns(track)
        if cols is None:
            pts = _get_points(track)
            if pts is not None:
                cols = _extract_track_columns(pts)
        if cols is None:
            self._redraw()
            return
        try:
            s = _np.asarray(cols["s"], dtype=float)
            curv = _np.asarray(cols["curv"], dtype=float)
            mask = _np.isfinite(s) & _np.isfinite(curv)
            if _np.any(mask):
                s = s[mask]; curv = curv[mask]
            self._s_curv = s
            self._curv = curv
            self.draw_line(s, curv)
        except Exception:
            self._redraw()

    def set_data(self, track: object, *args: object) -> None:  # type: ignore[override]
        if args:
            try:
                x = _np.asarray(track, dtype=float)
                y = _np.asarray(args[0], dtype=float)
                self.draw_line(x, y)
                self._s_curv = x
                self._curv = y
                return
            except Exception:
                pass
        self.set_track(track)

    def plot(self, track: object) -> None:  # type: ignore[override]
        self.set_track(track)

    def update_chart(self, track: object) -> None:  # type: ignore[override]
        self.set_track(track)

    def get_curvature(self) -> tuple[_np.ndarray, _np.ndarray] | None:
        if self._s_curv is not None and self._curv is not None:
            return self._s_curv.copy(), self._curv.copy()
        return None


# ---------------------------------------------------------------------------
# TrackElevChart — 標高/距離
# ---------------------------------------------------------------------------

class TrackElevChart(_XYChart):
    """Elevation vs Distance."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "Elevation [m]")
        super().__init__(master, **kwargs)  # type: ignore[arg-type]
        self._s_elev: _np.ndarray | None = None
        self._elev: _np.ndarray | None = None

    def set_track(self, track: object) -> None:
        cols = _extract_track_columns(track)
        if cols is None:
            pts = _get_points(track)
            if pts is not None:
                cols = _extract_track_columns(pts)
        if cols is None:
            self._redraw()
            return
        try:
            s = _np.asarray(cols["s"], dtype=float)
            z = _np.asarray(cols["z"], dtype=float)
            mask = _np.isfinite(s) & _np.isfinite(z)
            if _np.any(mask):
                s = s[mask]; z = z[mask]
            self._s_elev = s
            self._elev = z
            self.draw_line(s, z)
        except Exception:
            self._redraw()

    def set_data(self, track: object, *args: object) -> None:  # type: ignore[override]
        if args:
            try:
                x = _np.asarray(track, dtype=float)
                y = _np.asarray(args[0], dtype=float)
                self.draw_line(x, y)
                self._s_elev = x
                self._elev = y
                return
            except Exception:
                pass
        self.set_track(track)

    def plot(self, track: object) -> None:  # type: ignore[override]
        self.set_track(track)

    def update_chart(self, track: object) -> None:  # type: ignore[override]
        self.set_track(track)


# ---------------------------------------------------------------------------
# TrackGradChart — 勾配 dz/ds / 距離 (finite保証)
# ---------------------------------------------------------------------------

class TrackGradChart(_XYChart):
    """Gradient dz/ds vs Distance (finite保証)."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "Gradient dz/ds [-]")
        super().__init__(master, **kwargs)  # type: ignore[arg-type]
        self._s_grad: _np.ndarray | None = None
        self._grad: _np.ndarray | None = None

    def set_track(self, track: object) -> None:
        cols = _extract_track_columns(track)
        if cols is None:
            pts = _get_points(track)
            if pts is not None:
                cols = _extract_track_columns(pts)
        if cols is None:
            self._redraw()
            return
        try:
            s = _np.asarray(cols["s"], dtype=float)
            z = _np.asarray(cols["z"], dtype=float)
            mask = _np.isfinite(s) & _np.isfinite(z)
            if _np.any(mask):
                s = s[mask]; z = z[mask]
            grad = _compute_gradient(s, z)
            # ensure finite
            grad = _np.where(_np.isfinite(grad), grad, 0.0)
            self._s_grad = s
            self._grad = grad
            self.draw_line(s, grad)
        except Exception:
            self._redraw()

    def set_data(self, track: object, *args: object) -> None:  # type: ignore[override]
        if args:
            try:
                x = _np.asarray(track, dtype=float)
                y = _np.asarray(args[0], dtype=float)
                y = _np.where(_np.isfinite(y), y, 0.0)
                self.draw_line(x, y)
                self._s_grad = x
                self._grad = y
                return
            except Exception:
                pass
        self.set_track(track)

    def plot(self, track: object) -> None:  # type: ignore[override]
        self.set_track(track)

    def update_chart(self, track: object) -> None:  # type: ignore[override]
        self.set_track(track)

    def get_gradient(self) -> tuple[_np.ndarray, _np.ndarray] | None:
        if self._s_grad is not None and self._grad is not None:
            return self._s_grad.copy(), self._grad.copy()
        return None


# ---------------------------------------------------------------------------
# TrackBankChart — バンク/距離
# ---------------------------------------------------------------------------

class TrackBankChart(_XYChart):
    """Bank (rad) vs Distance."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "Bank [rad]")
        super().__init__(master, **kwargs)  # type: ignore[arg-type]
        self._s_bank: _np.ndarray | None = None
        self._bank: _np.ndarray | None = None

    def set_track(self, track: object) -> None:
        cols = _extract_track_columns(track)
        if cols is None:
            pts = _get_points(track)
            if pts is not None:
                cols = _extract_track_columns(pts)
        if cols is None:
            self._redraw()
            return
        try:
            s = _np.asarray(cols["s"], dtype=float)
            bank = _np.asarray(cols["bank"], dtype=float)
            mask = _np.isfinite(s) & _np.isfinite(bank)
            if _np.any(mask):
                s = s[mask]; bank = bank[mask]
            self._s_bank = s
            self._bank = bank
            self.draw_line(s, bank)
        except Exception:
            self._redraw()

    def set_data(self, track: object, *args: object) -> None:  # type: ignore[override]
        if args:
            try:
                x = _np.asarray(track, dtype=float)
                y = _np.asarray(args[0], dtype=float)
                self.draw_line(x, y)
                self._s_bank = x
                self._bank = y
                return
            except Exception:
                pass
        self.set_track(track)

    def plot(self, track: object) -> None:  # type: ignore[override]
        self.set_track(track)

    def update_chart(self, track: object) -> None:  # type: ignore[override]
        self.set_track(track)


# ---------------------------------------------------------------------------
# TrackGripChart — グリップ/距離 0.8..1.2想定 (ylim強制)
# ---------------------------------------------------------------------------

class TrackGripChart(_XYChart):
    """Grip factor vs Distance (ylim 0.8..1.2想定)."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "Grip [-]")
        kwargs["ylim"] = (0.8, 1.2)
        super().__init__(master, **kwargs)  # type: ignore[arg-type]
        # enforce
        try:
            self._ylim = (0.8, 1.2)  # type: ignore
        except Exception:
            pass
        self._s_grip: _np.ndarray | None = None
        self._grip: _np.ndarray | None = None

    def set_track(self, track: object) -> None:
        cols = _extract_track_columns(track)
        if cols is None:
            pts = _get_points(track)
            if pts is not None:
                cols = _extract_track_columns(pts)
        if cols is None:
            self._redraw()
            return
        try:
            s = _np.asarray(cols["s"], dtype=float)
            grip = _np.asarray(cols["grip"], dtype=float)
            mask = _np.isfinite(s) & _np.isfinite(grip)
            if _np.any(mask):
                s = s[mask]; grip = grip[mask]
            # clip grip to 0.8..1.2 range visually? keep data as-is but ensure ylim
            # ensure grip finite and within plausible 0.5..1.5
            grip = _np.where(_np.isfinite(grip), grip, 1.0)
            self._s_grip = s
            self._grip = grip
            # enforce ylim before draw
            self._ylim = (0.8, 1.2)  # type: ignore
            self.draw_line(s, grip)
            # re-enforce after
            self._ylim = (0.8, 1.2)  # type: ignore
        except Exception:
            self._redraw()

    def set_data(self, track: object, *args: object) -> None:  # type: ignore[override]
        if args:
            try:
                x = _np.asarray(track, dtype=float)
                y = _np.asarray(args[0], dtype=float)
                y = _np.where(_np.isfinite(y), y, 1.0)
                self._ylim = (0.8, 1.2)  # type: ignore
                self.draw_line(x, y)
                self._s_grip = x
                self._grip = y
                self._ylim = (0.8, 1.2)  # type: ignore
                return
            except Exception:
                pass
        self.set_track(track)

    def plot(self, track: object) -> None:  # type: ignore[override]
        self.set_track(track)

    def update_chart(self, track: object) -> None:  # type: ignore[override]
        self.set_track(track)

    def _redraw(self) -> None:  # type: ignore[override]
        # enforce ylim every redraw
        try:
            self._ylim = (0.8, 1.2)  # type: ignore
        except Exception:
            pass
        super()._redraw()
        try:
            self._ylim = (0.8, 1.2)  # type: ignore
        except Exception:
            pass
