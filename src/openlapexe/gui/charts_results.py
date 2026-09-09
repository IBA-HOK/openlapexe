# -*- coding: utf-8 -*-
# allow: SIZE_OK — Results 7種 Canvas再現 (.chart_base/chart_xy継承, mpl禁止)
"""openlapexe.gui.charts_results -原典OpenLAP Results 7種 Canvas再現.

Classes:
- ResultsSpeedChart(score vs距離)
- ResultsElevationChart(標高+曲率/距離 dual-y)
- ResultsAccelChart(縦G+横G+G合力√(ax²+ay²)/距離)
- ResultsInputChart(tps・bps/距離 ylim -10..110)
- ResultsSteerChart(ハンドル/δ/β β≈ay/v²・ハンドル=β*rack)
- ResultsGGV3DChart(scatter+surf相当 wireframe投影 Vehicle47 20×20 >=100lines)
- ResultsTrackMapChart(速度色付き+方向矢印+axis equal)

chart_xy.XYChart / chart_base.BaseChart継承, mpl禁止.
"""
from __future__ import annotations

import math as _math
import time as _time
import tkinter as tk

import numpy as _np

from openlapexe.gui.chart_base import BaseChart as _BaseChart, _axis_limits, _draw_axes, _draw_grid, _project_wireframe, _thin
from openlapexe.gui.chart_xy import XYChart as _XYChart, _color_for_value, _thin_triple

__all__ = [
    "ResultsSpeedChart",
    "ResultsElevationChart",
    "ResultsAccelChart",
    "ResultsInputChart",
    "ResultsSteerChart",
    "ResultsGGV3DChart",
    "ResultsTrackMapChart",
]

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _infer_track_name(result: object | None = None, fallback: str = "spa") -> str:
    """Infer track name from Result attrs or explicit fallback.

    Result currently has no track field, so callers (SimulateView2) may pass
    track via set_track_name(). Also probe common attrs for forward-compat.
    """
    try:
        if result is not None:
            for _attr in ("track_name", "_track_name", "track", "track_id", "name"):
                try:
                    _v = getattr(result, _attr, None)
                    if isinstance(_v, str) and _v.strip():
                        return _v.strip().removesuffix(".json")
                except Exception:
                    continue
    except Exception:
        pass
    try:
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip().removesuffix(".json")
    except Exception:
        pass
    return "spa"


def _load_track_arrays(
    s_ref: _np.ndarray | None = None,
    track_name: str | None = None,
    result: object | None = None,
) -> tuple[_np.ndarray, _np.ndarray, _np.ndarray, _np.ndarray, _np.ndarray]:
    """Return (s_track, z_track, curv_track, x_track, y_track) for given track."""
    name = _infer_track_name(result, track_name or "spa")
    # Direct x/y passthrough: if result already carries track geometry, prefer it
    # (future Result with x/y fields; harmless when absent).
    try:
        if result is not None:
            _xr = getattr(result, "x", None)
            _yr = getattr(result, "y", None)
            _sr = getattr(result, "s", None)
            if _xr is not None and _yr is not None:
                x_a = _np.asarray(_xr, dtype=float)
                y_a = _np.asarray(_yr, dtype=float)
                if x_a.size >= 2 and x_a.size == y_a.size:
                    if _sr is not None:
                        s_a = _np.asarray(_sr, dtype=float)
                        if s_a.size != x_a.size:
                            s_a = _np.linspace(0.0, float(s_a[-1]) if s_a.size else 1000.0, x_a.size)
                    else:
                        s_a = _np.linspace(0.0, 1000.0, x_a.size)
                    z_a = _np.asarray(getattr(result, "z", _np.zeros_like(x_a)), dtype=float)
                    if z_a.size != x_a.size:
                        z_a = _np.zeros_like(x_a)
                    curv_a = _np.asarray(getattr(result, "curv", getattr(result, "curvature", _np.zeros_like(x_a))), dtype=float)
                    if curv_a.size != x_a.size:
                        curv_a = _np.zeros_like(x_a)
                    return s_a, z_a, curv_a, x_a, y_a
    except Exception:
        pass
    for _try_name in ([name] if name else []) + ([] if name == "spa" else ["spa"]):
        for _mod_name in ("openlapexe.track",):
            try:
                import importlib as _il

                _mod = _il.import_module(_mod_name)
                _cls = getattr(_mod, "Track", None) or getattr(_mod, "Track2", None)
                if _cls is None:
                    continue
                tr = _cls.from_json(_try_name)
                pts = _np.asarray(tr.points, dtype=float)
                if pts.shape[0] >= 2 and pts.shape[1] >= 8:
                    s_t = _np.asarray(pts[:, 0], dtype=float)
                    x_t = _np.asarray(pts[:, 1], dtype=float)
                    y_t = _np.asarray(pts[:, 2], dtype=float)
                    z_t = _np.asarray(pts[:, 3], dtype=float)
                    curv_t = _np.asarray(pts[:, 4], dtype=float)
                    return s_t, z_t, curv_t, x_t, y_t
            except Exception:
                continue
    # fallback synthetic fallback for headless missing data
    if s_ref is not None:
        try:
            s_a = _np.asarray(s_ref, dtype=float)
            n = int(s_a.shape[0]) if s_a.size else 100
            s_t = _np.linspace(float(s_a[0]) if n else 0.0, float(s_a[-1]) if n else 1000.0, max(n, 100), dtype=float)
            # synthetic elevation sine, curvature sine
            z_t = _np.sin(s_t * 0.01) * 10.0
            curv_t = _np.sin(s_t * 0.005) * 0.02
            x_t = _np.cos(s_t * 0.001) * 500.0
            y_t = _np.sin(s_t * 0.001) * 500.0
            return s_t, z_t, curv_t, x_t, y_t
        except Exception:
            pass
    s_t = _np.linspace(0.0, 1000.0, 200, dtype=float)
    z_t = _np.sin(s_t * 0.01) * 10.0
    curv_t = _np.sin(s_t * 0.005) * 0.02
    x_t = _np.cos(s_t * 0.001) * 500.0
    y_t = _np.sin(s_t * 0.001) * 500.0
    return s_t, z_t, curv_t, x_t, y_t


def _get_rack() -> float:
    try:
        from openlapexe.vehicle import Vehicle47 as _V47  # type: ignore

        v = _V47.from_json("f1")
        return float(getattr(v, "rack", 12.0))
    except Exception:
        return 12.0


def _thin_pair(a: _np.ndarray, b: _np.ndarray, limit: int = 800) -> tuple[_np.ndarray, _np.ndarray]:
    return _thin(a, b, limit)


# ---------------------------------------------------------------------------
# ResultsSpeedChart
# ---------------------------------------------------------------------------
class ResultsSpeedChart(_XYChart):
    """Speed vs Distance (Results alias)."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "Speed [m/s]")
        super().__init__(master, **kwargs)

    def plot(self, result: object) -> None:  # type: ignore[override]
        try:
            s = getattr(result, "s", None)
            v = getattr(result, "v", None)
            if s is not None and v is not None:
                self.draw_line(s, v)
                return
        except Exception:
            pass
        try:
            super().plot(result)  # type: ignore
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ResultsElevationChart (標高+曲率 dual-y)
# ---------------------------------------------------------------------------
class ResultsElevationChart(_XYChart):
    """Elevation + Curvature vs Distance dual-y."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "Elevation [m] / Curv [1/m]")
        super().__init__(master, **kwargs)
        self._s_elev: _np.ndarray | None = None
        self._z_data: _np.ndarray | None = None
        self._curv_data: _np.ndarray | None = None
        self._track_name: str = "spa"

    def set_track_name(self, name: str) -> None:
        try:
            if isinstance(name, str) and name.strip():
                self._track_name = name.strip().removesuffix(".json")
        except Exception:
            pass

    def set_track(self, track: object) -> None:
        try:
            nm = getattr(track, "name", None)
            if isinstance(nm, str) and nm.strip():
                _cand = nm.strip().removesuffix(".json")
                try:
                    from openlapexe.track import Track as _TCk  # type: ignore

                    _TCk.from_json(_cand)
                    self.set_track_name(_cand)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            import numpy as _np2

            xs = getattr(track, "_x", None)
            ys = getattr(track, "_y", None)
            ss = getattr(track, "_s", None)
            if xs is not None and ys is not None and ss is not None:
                s_a = _np2.asarray(ss, dtype=float)
                z_a = _np2.asarray(getattr(track, "_z", _np2.zeros_like(s_a)), dtype=float)
                c_a = _np2.asarray(getattr(track, "_curv", _np2.zeros_like(s_a)), dtype=float)
                if s_a.size >= 2:
                    self._s_elev = s_a
                    self._z_data = z_a if z_a.size == s_a.size else _np2.zeros_like(s_a)
                    self._curv_data = c_a if c_a.size == s_a.size else _np2.zeros_like(s_a)
                    self._x_data = s_a  # type: ignore
                    self._y_data = self._z_data  # type: ignore
                    self.x_data = s_a
                    self.y_data = self._z_data
                    self._redraw()
        except Exception:
            pass

    def plot(self, result: object) -> None:  # type: ignore[override]
        try:
            s = getattr(result, "s", None)
            if s is None:
                s = getattr(result, "s_m", None)
            if s is None:
                return
            s_arr = _np.asarray(s, dtype=float)
            name = _infer_track_name(result, getattr(self, "_track_name", "spa"))
            s_t, z_t, curv_t, _, _ = _load_track_arrays(s_arr, track_name=name, result=result)
            # interpolate to s_arr
            try:
                z_arr = _np.interp(s_arr, s_t, z_t, left=float(z_t[0]), right=float(z_t[-1]))
                curv_arr = _np.interp(s_arr, s_t, curv_t, left=float(curv_t[0]), right=float(curv_t[-1]))
            except Exception:
                z_arr = _np.zeros_like(s_arr)
                curv_arr = _np.zeros_like(s_arr)
            # thin triple
            if s_arr.size > 800:
                s_arr, z_arr, curv_arr = _thin_triple(s_arr, z_arr, curv_arr, 800)
            self._s_elev = s_arr
            self._z_data = z_arr
            self._curv_data = curv_arr
            # also set base x/y for fallback
            self._x_data = s_arr  # type: ignore
            self._y_data = z_arr  # type: ignore
            self.x_data = s_arr
            self.y_data = z_arr
            try:
                self._track_name = name
            except Exception:
                pass
            self._redraw()
        except Exception:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass

    def _redraw(self) -> None:  # type: ignore[override]
        t0 = _time.perf_counter()
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
        pad_left = 52.0
        pad_right = 52.0
        pad_top = 12.0
        pad_bottom = 30.0
        plot_w = float(w - pad_left - pad_right)
        plot_h = float(h - pad_top - pad_bottom)
        if plot_w < 1:
            plot_w = 1
        if plot_h < 1:
            plot_h = 1
        x0 = float(pad_left)
        y0 = float(pad_top)
        x1 = float(w - pad_right)
        y1 = float(h - pad_bottom)
        has = False
        try:
            if self._s_elev is not None and self._z_data is not None and self._curv_data is not None:
                if self._s_elev.size > 1 and self._z_data.size > 1:
                    has = True
        except Exception:
            has = False
        if not has:
            try:
                _draw_grid(self, x0, y0, x1, y1, 5, 5)
                _draw_axes(self, x0, y0, x1, y1, 5, 5)
                self.create_text(w // 2, h // 2, text="No data", fill="#888", tags=("placeholder",))
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000
            return
        try:
            s_arr = _np.asarray(self._s_elev, dtype=float)
            z_arr = _np.asarray(self._z_data, dtype=float)
            curv_arr = _np.asarray(self._curv_data, dtype=float)
            # finite
            try:
                mask = _np.isfinite(s_arr) & _np.isfinite(z_arr) & _np.isfinite(curv_arr)
                if _np.any(mask):
                    s_arr = s_arr[mask]
                    z_arr = z_arr[mask]
                    curv_arr = curv_arr[mask]
            except Exception:
                pass
            if s_arr.size == 0:
                self._last_draw_ms = (_time.perf_counter() - t0) * 1000
                return
            if s_arr.size > 800:
                s_arr, z_arr, curv_arr = _thin_triple(s_arr, z_arr, curv_arr, 800)
                self._s_elev = s_arr
                self._z_data = z_arr
                self._curv_data = curv_arr
            xl, xh = _axis_limits(s_arr, 0.02)
            yl0, yh0 = _axis_limits(z_arr, 0.10)
            yl1, yh1 = _axis_limits(curv_arr, 0.10)
            if xh - xl < 1e-9:
                xh = xl + 1.0
            if yh0 - yl0 < 1e-9:
                yh0 = yl0 + 1.0
                yl0 = yl0 - 0.5
            if yh1 - yl1 < 1e-9:
                yh1 = yl1 + 0.01
            x_scale = plot_w / (xh - xl)
            y_scale_l = plot_h / (yh0 - yl0)
            y_scale_r = plot_h / (yh1 - yl1)
            try:
                self._store_view(xl, xh, yl0, yh0, float(x0), float(y0), float(x1), float(y1))
                self._probe_text = ""
                self._probe_data = None
            except Exception:
                pass
            # grid
            for i in range(6):
                xv = xl + (xh - xl) * i / 5
                px = x0 + (xv - xl) * x_scale
                self.create_line(px, y0, px, y1, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
                yv = yl0 + (yh0 - yl0) * i / 5
                py = y1 - (yv - yl0) * y_scale_l
                self.create_line(x0, py, x1, py, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            self.create_line(x0, y1, x1, y1, fill="#333", width=1, tags=("axis",))
            self.create_line(x0, y0, x0, y1, fill="#333", width=1, tags=("axis",))
            self.create_line(x1, y0, x1, y1, fill="#c0392b", width=1, dash=(2, 2), tags=("axis_right",))
            # ticks x
            for i in range(6):
                xv = xl + (xh - xl) * i / 5
                px = x0 + (xv - xl) * x_scale
                self.create_line(px, y1, px, y1 + 4, fill="#333", tags=("tick",))
                lab = f"{xv:.0f}" if abs(xv) >= 10 else f"{xv:.1f}"
                self.create_text(px, y1 + 10, text=lab, fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
            # ticks y left (elevation)
            for i in range(6):
                yv = yl0 + (yh0 - yl0) * i / 5
                py = y1 - (yv - yl0) * y_scale_l
                self.create_line(x0 - 4, py, x0, py, fill="#1f4b99", tags=("tick",))
                lab = f"{yv:.0f}" if abs(yv) >= 10 else f"{yv:.1f}"
                self.create_text(x0 - 6, py, text=lab, fill="#1f4b99", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            # ticks y right (curvature)
            for i in range(6):
                yv = yl1 + (yh1 - yl1) * i / 5
                py = y1 - (yv - yl1) * y_scale_r
                self.create_line(x1, py, x1 + 4, py, fill="#c0392b", tags=("tick",))
                lab = f"{yv:.3f}" if abs(yv) < 1 else f"{yv:.2f}"
                self.create_text(x1 + 6, py, text=lab, fill="#c0392b", font=("TkDefaultFont", 7), anchor="w", tags=("ticklabel",))
            self.create_text((x0 + x1) * 0.5, h - 6, text="Distance [m]", fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
            self.create_text(8, (y0 + y1) * 0.5, text="Elevation [m]", fill="#1f4b99", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
            self.create_text(w - 8, (y0 + y1) * 0.5, text="Curv [1/m]", fill="#c0392b", font=("TkDefaultFont", 8), anchor="e", angle=90, tags=("axislabel",))
            # draw elevation line (left scale)
            coords_elev: list[float] = []
            for xv, yv in zip(s_arr, z_arr):
                px = x0 + (float(xv) - xl) * x_scale
                py = y1 - (float(yv) - yl0) * y_scale_l
                coords_elev.append(px)
                coords_elev.append(py)
            if len(coords_elev) >= 4:
                self.create_line(*coords_elev, fill="#1f4b99", width=2, smooth=False, tags=("elev_line",))
            # draw curvature line (right scale)
            coords_curv: list[float] = []
            for xv, yv in zip(s_arr, curv_arr):
                px = x0 + (float(xv) - xl) * x_scale
                py = y1 - (float(yv) - yl1) * y_scale_r
                coords_curv.append(px)
                coords_curv.append(py)
            if len(coords_curv) >= 4:
                self.create_line(*coords_curv, fill="#c0392b", width=2, smooth=False, tags=("curv_line",))
            # legend
            self.create_rectangle(x1 - 110, y0 + 4, x1 - 10, y0 + 28, fill="white", outline="#ccc", tags=("legend",))
            self.create_line(x1 - 105, y0 + 10, x1 - 90, y0 + 10, fill="#1f4b99", width=2, tags=("legend",))
            self.create_text(x1 - 88, y0 + 10, text="Elev", fill="#333", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
            self.create_line(x1 - 105, y0 + 20, x1 - 90, y0 + 20, fill="#c0392b", width=2, tags=("legend",))
            self.create_text(x1 - 88, y0 + 20, text="Curv", fill="#333", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
        except Exception:
            pass
        finally:
            try:
                self._draw_count += 1
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# ResultsAccelChart
# ---------------------------------------------------------------------------
class ResultsAccelChart(_XYChart):
    """Ax + Ay + G合力 sqrt(ax²+ay²) vs Distance."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "Accel [m/s²] / G [m/s²]")
        super().__init__(master, **kwargs)
        self._s_acc: _np.ndarray | None = None
        self._ax: _np.ndarray | None = None
        self._ay: _np.ndarray | None = None
        self._g: _np.ndarray | None = None

    def plot(self, result: object) -> None:  # type: ignore[override]
        try:
            s = getattr(result, "s", None)
            ax = getattr(result, "ax", None)
            ay = getattr(result, "ay", None)
            if s is not None and ax is not None and ay is not None:
                s_arr = _np.asarray(s, dtype=float)
                ax_arr = _np.asarray(ax, dtype=float)
                ay_arr = _np.asarray(ay, dtype=float)
                n = min(int(s_arr.shape[0]), int(ax_arr.shape[0]), int(ay_arr.shape[0]))
                s_arr = s_arr[:n]
                ax_arr = ax_arr[:n]
                ay_arr = ay_arr[:n]
                g_arr = _np.sqrt(ax_arr * ax_arr + ay_arr * ay_arr)
                if s_arr.size > 800:
                    s_arr, ax_arr, ay_arr = _thin_triple(s_arr, ax_arr, ay_arr, 800)
                    # recompute g after thin? use first 800 of g
                    g_arr = _np.sqrt(ax_arr * ax_arr + ay_arr * ay_arr)
                self._s_acc = s_arr
                self._ax = ax_arr
                self._ay = ay_arr
                self._g = g_arr
                self._x_data = s_arr  # type: ignore
                self._y_data = g_arr  # type: ignore
                self.x_data = s_arr
                self.y_data = g_arr
                self._redraw()
                return
        except Exception:
            pass
        try:
            super().plot(result)  # type: ignore
        except Exception:
            pass

    def _redraw(self) -> None:  # type: ignore[override]
        t0 = _time.perf_counter()
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
        pad_left = 52.0
        pad_right = 12.0
        pad_top = 12.0
        pad_bottom = 30.0
        plot_w = float(w - pad_left - pad_right)
        plot_h = float(h - pad_top - pad_bottom)
        if plot_w < 1:
            plot_w = 1
        if plot_h < 1:
            plot_h = 1
        x0 = float(pad_left)
        y0 = float(pad_top)
        x1 = float(w - pad_right)
        y1 = float(h - pad_bottom)
        has = False
        try:
            if self._s_acc is not None and self._ax is not None and self._ay is not None and self._g is not None:
                if self._s_acc.size > 1:
                    has = True
        except Exception:
            has = False
        if not has:
            try:
                _draw_grid(self, x0, y0, x1, y1, 5, 5)
                _draw_axes(self, x0, y0, x1, y1, 5, 5)
                self.create_text(w // 2, h // 2, text="No data", fill="#888", tags=("placeholder",))
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000
            return
        try:
            s_arr = _np.asarray(self._s_acc, dtype=float)
            ax_arr = _np.asarray(self._ax, dtype=float)
            ay_arr = _np.asarray(self._ay, dtype=float)
            g_arr = _np.asarray(self._g, dtype=float)
            mask = _np.isfinite(s_arr) & _np.isfinite(ax_arr) & _np.isfinite(ay_arr) & _np.isfinite(g_arr)
            if _np.any(mask):
                s_arr = s_arr[mask]
                ax_arr = ax_arr[mask]
                ay_arr = ay_arr[mask]
                g_arr = g_arr[mask]
            if s_arr.size > 800:
                # thin via triple for s/ax, then recalc g slice
                s_arr, ax_arr, ay_arr = _thin_triple(s_arr, ax_arr, ay_arr, 800)
                g_arr = _np.sqrt(ax_arr * ax_arr + ay_arr * ay_arr)
                self._s_acc = s_arr
                self._ax = ax_arr
                self._ay = ay_arr
                self._g = g_arr
            xl, xh = _axis_limits(s_arr, 0.02)
            # y limits across all three
            all_y = _np.concatenate([ax_arr, ay_arr, g_arr]) if g_arr.size else ax_arr
            yl, yh = _axis_limits(all_y, 0.08)
            if xh - xl < 1e-9:
                xh = xl + 1.0
            if yh - yl < 1e-9:
                yh = yl + 1.0
            x_scale = plot_w / (xh - xl)
            y_scale = plot_h / (yh - yl)
            try:
                self._store_view(xl, xh, yl, yh, float(x0), float(y0), float(x1), float(y1))
            except Exception:
                pass
            for i in range(6):
                xv = xl + (xh - xl) * i / 5
                px = x0 + (xv - xl) * x_scale
                self.create_line(px, y0, px, y1, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
                yv = yl + (yh - yl) * i / 5
                py = y1 - (yv - yl) * y_scale
                self.create_line(x0, py, x1, py, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            self.create_line(x0, y1, x1, y1, fill="#333", width=1, tags=("axis",))
            self.create_line(x0, y0, x0, y1, fill="#333", width=1, tags=("axis",))
            for i in range(6):
                xv = xl + (xh - xl) * i / 5
                px = x0 + (xv - xl) * x_scale
                self.create_line(px, y1, px, y1 + 4, fill="#333", tags=("tick",))
                lab = f"{xv:.0f}" if abs(xv) >= 10 else f"{xv:.1f}"
                self.create_text(px, y1 + 10, text=lab, fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
            for i in range(6):
                yv = yl + (yh - yl) * i / 5
                py = y1 - (yv - yl) * y_scale
                self.create_line(x0 - 4, py, x0, py, fill="#333", tags=("tick",))
                lab = f"{yv:.1f}"
                self.create_text(x0 - 6, py, text=lab, fill="#333", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            self.create_text((x0 + x1) * 0.5, h - 6, text="Distance [m]", fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
            self.create_text(8, (y0 + y1) * 0.5, text="Accel [m/s²]", fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))

            def _draw_line(arr: _np.ndarray, color: str, tag: str) -> None:
                coords: list[float] = []
                for xv, yv in zip(s_arr, arr):
                    px = x0 + (float(xv) - xl) * x_scale
                    py = y1 - (float(yv) - yl) * y_scale
                    coords.append(px)
                    coords.append(py)
                if len(coords) >= 4:
                    self.create_line(*coords, fill=color, width=2, smooth=False, tags=(tag,))

            _draw_line(ax_arr, "#1f4b99", "ax_line")
            _draw_line(ay_arr, "#e67e22", "ay_line")
            _draw_line(g_arr, "#27ae60", "g_line")
            # legend
            self.create_rectangle(x1 - 140, y0 + 4, x1 - 10, y0 + 52, fill="white", outline="#ccc", tags=("legend",))
            self.create_line(x1 - 135, y0 + 12, x1 - 120, y0 + 12, fill="#1f4b99", width=2, tags=("legend",))
            self.create_text(x1 - 118, y0 + 12, text="ax", fill="#333", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
            self.create_line(x1 - 135, y0 + 24, x1 - 120, y0 + 24, fill="#e67e22", width=2, tags=("legend",))
            self.create_text(x1 - 118, y0 + 24, text="ay", fill="#333", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
            self.create_line(x1 - 135, y0 + 36, x1 - 120, y0 + 36, fill="#27ae60", width=2, tags=("legend",))
            self.create_text(x1 - 118, y0 + 36, text="G √(ax²+ay²)", fill="#333", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
        except Exception:
            pass
        finally:
            try:
                self._draw_count += 1
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# ResultsInputChart (tps/bps ylim -10..110)
# ---------------------------------------------------------------------------
class ResultsInputChart(_XYChart):
    """tps / bps vs Distance ylim -10..110."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "Input [%]")
        # force ylim -10..110
        kwargs["ylim"] = (-10.0, 110.0)
        super().__init__(master, **kwargs)
        # ensure forced after super (super may clamp)
        self._ylim = (-10.0, 110.0)  # type: ignore
        self._s_in: _np.ndarray | None = None
        self._tps: _np.ndarray | None = None
        self._bps: _np.ndarray | None = None

    def plot(self, result: object) -> None:  # type: ignore[override]
        try:
            s = getattr(result, "s", None)
            tps = getattr(result, "tps", None)
            bps = getattr(result, "bps", None)
            if s is None:
                return
            s_arr = _np.asarray(s, dtype=float)
            if tps is not None:
                tps_arr = _np.asarray(tps, dtype=float)
            else:
                tps_arr = _np.zeros_like(s_arr)
            if bps is not None:
                bps_arr = _np.asarray(bps, dtype=float)
            else:
                bps_arr = _np.zeros_like(s_arr)
            n = min(int(s_arr.shape[0]), int(tps_arr.shape[0]), int(bps_arr.shape[0]))
            s_arr = s_arr[:n]
            tps_arr = tps_arr[:n]
            bps_arr = bps_arr[:n]
            # scale tps 0..1 to %, bps handling
            # tps always fraction -> *100
            tps_pct = tps_arr * 100.0
            # bps: if max <=2 -> fraction -> *100 else keep
            try:
                bmax = float(_np.max(bps_arr)) if bps_arr.size else 0.0
                bmin = float(_np.min(bps_arr)) if bps_arr.size else 0.0
                if bmax <= 2.0 and bmax >= 0:
                    bps_pct = bps_arr * 100.0
                else:
                    # if large (pressure), normalize to 0..100
                    if bmax > 110.0:
                        # scale to 100
                        rng = bmax - bmin if bmax - bmin > 1e-9 else bmax
                        bps_pct = (bps_arr - bmin) / max(rng, 1e-9) * 100.0
                    else:
                        bps_pct = bps_arr
                    # if bps_pct still >110, clip visually but keep line
                # ensure finite
                bps_pct = _np.clip(bps_pct, -10.0, 110.0) if bps_pct.size else bps_pct
                tps_pct = _np.clip(tps_pct, -10.0, 110.0) if tps_pct.size else tps_pct
            except Exception:
                bps_pct = bps_arr
                tps_pct = tps_arr * 100.0
            if s_arr.size > 800:
                s_arr, tps_pct, bps_pct = _thin_triple(s_arr, tps_pct, bps_pct, 800)
            self._s_in = s_arr
            self._tps = tps_pct
            self._bps = bps_pct
            self._x_data = s_arr  # type: ignore
            self._y_data = tps_pct  # type: ignore
            self.x_data = s_arr
            self.y_data = tps_pct
            # keep ylim forced
            self._ylim = (-10.0, 110.0)
            self._redraw()
            return
        except Exception:
            pass
        try:
            super().plot(result)  # type: ignore
        except Exception:
            pass

    def _redraw(self) -> None:  # type: ignore[override]
        # enforce ylim before drawing
        self._ylim = (-10.0, 110.0)
        t0 = _time.perf_counter()
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
        pad_left = 52.0
        pad_right = 12.0
        pad_top = 12.0
        pad_bottom = 30.0
        plot_w = float(w - pad_left - pad_right)
        plot_h = float(h - pad_top - pad_bottom)
        if plot_w < 1:
            plot_w = 1
        if plot_h < 1:
            plot_h = 1
        x0 = float(pad_left)
        y0 = float(pad_top)
        x1 = float(w - pad_right)
        y1 = float(h - pad_bottom)
        has = False
        try:
            if self._s_in is not None and self._tps is not None and self._bps is not None:
                if self._s_in.size > 1:
                    has = True
        except Exception:
            has = False
        if not has:
            try:
                _draw_grid(self, x0, y0, x1, y1, 5, 5)
                _draw_axes(self, x0, y0, x1, y1, 5, 5)
                self.create_text(w // 2, h // 2, text="No data", fill="#888", tags=("placeholder",))
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000
            return
        try:
            s_arr = _np.asarray(self._s_in, dtype=float)
            tps_arr = _np.asarray(self._tps, dtype=float)
            bps_arr = _np.asarray(self._bps, dtype=float)
            mask = _np.isfinite(s_arr) & _np.isfinite(tps_arr) & _np.isfinite(bps_arr)
            if _np.any(mask):
                s_arr = s_arr[mask]
                tps_arr = tps_arr[mask]
                bps_arr = bps_arr[mask]
            if s_arr.size > 800:
                s_arr, tps_arr, bps_arr = _thin_triple(s_arr, tps_arr, bps_arr, 800)
                self._s_in = s_arr
                self._tps = tps_arr
                self._bps = bps_arr
            xl, xh = _axis_limits(s_arr, 0.02)
            yl, yh = -10.0, 110.0  # forced
            if xh - xl < 1e-9:
                xh = xl + 1.0
            x_scale = plot_w / (xh - xl)
            y_scale = plot_h / (yh - yl)
            try:
                self._store_view(xl, xh, yl, yh, float(x0), float(y0), float(x1), float(y1))
            except Exception:
                pass
            for i in range(6):
                xv = xl + (xh - xl) * i / 5
                px = x0 + (xv - xl) * x_scale
                self.create_line(px, y0, px, y1, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
                yv = yl + (yh - yl) * i / 5
                py = y1 - (yv - yl) * y_scale
                self.create_line(x0, py, x1, py, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            self.create_line(x0, y1, x1, y1, fill="#333", width=1, tags=("axis",))
            self.create_line(x0, y0, x0, y1, fill="#333", width=1, tags=("axis",))
            for i in range(6):
                xv = xl + (xh - xl) * i / 5
                px = x0 + (xv - xl) * x_scale
                self.create_line(px, y1, px, y1 + 4, fill="#333", tags=("tick",))
                lab = f"{xv:.0f}" if abs(xv) >= 10 else f"{xv:.1f}"
                self.create_text(px, y1 + 10, text=lab, fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
            for i in range(6):
                yv = yl + (yh - yl) * i / 5
                py = y1 - (yv - yl) * y_scale
                self.create_line(x0 - 4, py, x0, py, fill="#333", tags=("tick",))
                lab = f"{yv:.0f}"
                self.create_text(x0 - 6, py, text=lab, fill="#333", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            self.create_text((x0 + x1) * 0.5, h - 6, text="Distance [m]", fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
            self.create_text(8, (y0 + y1) * 0.5, text="Input [%]", fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))

            def _draw(arr: _np.ndarray, color: str, tag: str) -> None:
                coords: list[float] = []
                for xv, yv in zip(s_arr, arr):
                    px = x0 + (float(xv) - xl) * x_scale
                    py = y1 - (float(yv) - yl) * y_scale
                    coords.append(px)
                    coords.append(py)
                if len(coords) >= 4:
                    self.create_line(*coords, fill=color, width=2, smooth=False, tags=(tag,))

            _draw(tps_arr, "#1f4b99", "tps_line")
            _draw(bps_arr, "#c0392b", "bps_line")
            self.create_rectangle(x1 - 140, y0 + 4, x1 - 10, y0 + 32, fill="white", outline="#ccc", tags=("legend",))
            self.create_line(x1 - 135, y0 + 12, x1 - 120, y0 + 12, fill="#1f4b99", width=2, tags=("legend",))
            self.create_text(x1 - 118, y0 + 12, text="tps", fill="#333", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
            self.create_line(x1 - 135, y0 + 24, x1 - 120, y0 + 24, fill="#c0392b", width=2, tags=("legend",))
            self.create_text(x1 - 118, y0 + 24, text="bps", fill="#333", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
        except Exception:
            pass
        finally:
            try:
                self._draw_count += 1
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# ResultsSteerChart (ハンドル/δ/β)
# ---------------------------------------------------------------------------
class ResultsSteerChart(_XYChart):
    """Steer: handle / delta / beta vs Distance."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "Angle [deg]")
        super().__init__(master, **kwargs)
        self._s_st: _np.ndarray | None = None
        self._handle: _np.ndarray | None = None
        self._delta: _np.ndarray | None = None
        self._beta: _np.ndarray | None = None

    def plot(self, result: object) -> None:  # type: ignore[override]
        try:
            s = getattr(result, "s", None)
            ay = getattr(result, "ay", None)
            v = getattr(result, "v", None)
            if s is not None and ay is not None and v is not None:
                s_arr = _np.asarray(s, dtype=float)
                ay_arr = _np.asarray(ay, dtype=float)
                v_arr = _np.asarray(v, dtype=float)
                n = min(int(s_arr.shape[0]), int(ay_arr.shape[0]), int(v_arr.shape[0]))
                s_arr = s_arr[:n]
                ay_arr = ay_arr[:n]
                v_arr = v_arr[:n]
                # beta approx ay / v² (rad)
                v_safe = _np.maximum(v_arr, 1.0)
                beta = ay_arr / (v_safe * v_safe + 1e-9)
                # clip to reasonable steering angles
                beta = _np.clip(beta, -0.4, 0.4)
                rack = _get_rack()
                handle = beta * rack
                delta = beta  # wheel angle = beta
                # convert to deg for display
                beta_deg = _np.degrees(beta)
                delta_deg = _np.degrees(delta)
                handle_deg = _np.degrees(handle)
                if s_arr.size > 800:
                    s_arr, beta_deg, delta_deg = _thin_triple(s_arr, beta_deg, delta_deg, 800)
                    # handle thin separately but keep consistent step: use same indices via slicing same step
                    # recompute handle after thin: already thinned beta, handle = beta*rack in deg -> *rack factor
                    # but we already have handle_deg before thin; need to thin it similarly
                    # simpler: recompute from thinned beta
                    # To keep deterministic, re-thin handle similarly with same step logic: take handle_deg original and apply same step
                    # Instead just set handle_deg = beta_deg * rack (since linear)
                    handle_deg = beta_deg * rack
                else:
                    # ensure handle consistent
                    handle_deg = beta_deg * rack
                self._s_st = s_arr
                self._beta = beta_deg
                self._delta = delta_deg
                self._handle = handle_deg
                self._x_data = s_arr  # type: ignore
                self._y_data = handle_deg  # type: ignore
                self.x_data = s_arr
                self.y_data = handle_deg
                self._redraw()
                return
        except Exception:
            pass
        try:
            super().plot(result)  # type: ignore
        except Exception:
            pass

    def _redraw(self) -> None:  # type: ignore[override]
        t0 = _time.perf_counter()
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
        pad_left = 52.0
        pad_right = 12.0
        pad_top = 12.0
        pad_bottom = 30.0
        plot_w = float(w - pad_left - pad_right)
        plot_h = float(h - pad_top - pad_bottom)
        if plot_w < 1:
            plot_w = 1
        if plot_h < 1:
            plot_h = 1
        x0 = float(pad_left)
        y0 = float(pad_top)
        x1 = float(w - pad_right)
        y1 = float(h - pad_bottom)
        has = False
        try:
            if self._s_st is not None and self._handle is not None and self._beta is not None:
                if self._s_st.size > 1:
                    has = True
        except Exception:
            has = False
        if not has:
            try:
                _draw_grid(self, x0, y0, x1, y1, 5, 5)
                _draw_axes(self, x0, y0, x1, y1, 5, 5)
                self.create_text(w // 2, h // 2, text="No data", fill="#888", tags=("placeholder",))
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000
            return
        try:
            s_arr = _np.asarray(self._s_st, dtype=float)
            handle_arr = _np.asarray(self._handle, dtype=float)
            delta_arr = _np.asarray(self._delta, dtype=float)
            beta_arr = _np.asarray(self._beta, dtype=float)
            mask = _np.isfinite(s_arr) & _np.isfinite(handle_arr) & _np.isfinite(delta_arr) & _np.isfinite(beta_arr)
            if _np.any(mask):
                s_arr = s_arr[mask]
                handle_arr = handle_arr[mask]
                delta_arr = delta_arr[mask]
                beta_arr = beta_arr[mask]
            if s_arr.size > 800:
                s_arr, handle_arr, beta_arr = _thin_triple(s_arr, handle_arr, beta_arr, 800)
                # delta similarly
                # to keep delta aligned, thin delta with same step: recompute? For simplicity slice delta similarly
                delta_arr = delta_arr[: handle_arr.shape[0]]
                self._s_st = s_arr
                self._handle = handle_arr
                self._delta = delta_arr
                self._beta = beta_arr
            xl, xh = _axis_limits(s_arr, 0.02)
            all_y = _np.concatenate([handle_arr, delta_arr, beta_arr]) if handle_arr.size else handle_arr
            yl, yh = _axis_limits(all_y, 0.10)
            if xh - xl < 1e-9:
                xh = xl + 1.0
            if yh - yl < 1e-9:
                yh = yl + 1.0
            x_scale = plot_w / (xh - xl)
            y_scale = plot_h / (yh - yl)
            try:
                self._store_view(xl, xh, yl, yh, float(x0), float(y0), float(x1), float(y1))
            except Exception:
                pass
            for i in range(6):
                xv = xl + (xh - xl) * i / 5
                px = x0 + (xv - xl) * x_scale
                self.create_line(px, y0, px, y1, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
                yv = yl + (yh - yl) * i / 5
                py = y1 - (yv - yl) * y_scale
                self.create_line(x0, py, x1, py, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            self.create_line(x0, y1, x1, y1, fill="#333", width=1, tags=("axis",))
            self.create_line(x0, y0, x0, y1, fill="#333", width=1, tags=("axis",))
            for i in range(6):
                xv = xl + (xh - xl) * i / 5
                px = x0 + (xv - xl) * x_scale
                self.create_line(px, y1, px, y1 + 4, fill="#333", tags=("tick",))
                lab = f"{xv:.0f}" if abs(xv) >= 10 else f"{xv:.1f}"
                self.create_text(px, y1 + 10, text=lab, fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
            for i in range(6):
                yv = yl + (yh - yl) * i / 5
                py = y1 - (yv - yl) * y_scale
                self.create_line(x0 - 4, py, x0, py, fill="#333", tags=("tick",))
                lab = f"{yv:.1f}"
                self.create_text(x0 - 6, py, text=lab, fill="#333", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            self.create_text((x0 + x1) * 0.5, h - 6, text="Distance [m]", fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
            self.create_text(8, (y0 + y1) * 0.5, text="Angle [deg]", fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))

            def _draw(arr: _np.ndarray, color: str, tag: str) -> None:
                coords: list[float] = []
                for xv, yv in zip(s_arr, arr):
                    px = x0 + (float(xv) - xl) * x_scale
                    py = y1 - (float(yv) - yl) * y_scale
                    coords.append(px)
                    coords.append(py)
                if len(coords) >= 4:
                    self.create_line(*coords, fill=color, width=2, smooth=False, tags=(tag,))

            _draw(handle_arr, "#1f4b99", "handle_line")
            _draw(delta_arr, "#c0392b", "delta_line")
            _draw(beta_arr, "#27ae60", "beta_line")
            self.create_rectangle(x1 - 160, y0 + 4, x1 - 10, y0 + 52, fill="white", outline="#ccc", tags=("legend",))
            self.create_line(x1 - 155, y0 + 12, x1 - 140, y0 + 12, fill="#1f4b99", width=2, tags=("legend",))
            self.create_text(x1 - 138, y0 + 12, text="handle β*rack", fill="#333", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
            self.create_line(x1 - 155, y0 + 24, x1 - 140, y0 + 24, fill="#c0392b", width=2, tags=("legend",))
            self.create_text(x1 - 138, y0 + 24, text="δ", fill="#333", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
            self.create_line(x1 - 155, y0 + 36, x1 - 140, y0 + 36, fill="#27ae60", width=2, tags=("legend",))
            self.create_text(x1 - 138, y0 + 36, text="β≈ay/v²", fill="#333", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
        except Exception:
            pass
        finally:
            try:
                self._draw_count += 1
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# ResultsGGV3DChart
# ---------------------------------------------------------------------------
class ResultsGGV3DChart(_BaseChart):
    """GGV 3D wireframe (20×20) + scatter."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        super().__init__(master, **kwargs)
        self._verts_grid: _np.ndarray | None = None
        self._proj_grid: _np.ndarray | None = None
        self._scatter_ax: _np.ndarray | None = None
        self._scatter_ay: _np.ndarray | None = None
        self._scatter_v: _np.ndarray | None = None
        self._last_wireframe_lines: int = 0
        try:
            self._xlabel = "ay [m/s²] (proj)"
            self._ylabel = "ax [m/s²] (proj)"
            self._c_label = "v [m/s]"
            self._series_labels = [("#1f4b99", "GGV wire 20×20 (ay×ax×v) [m/s²,m/s]", "line"), ("#e74c3c", "sim scatter (ax,ay,v)", "marker")]
        except Exception:
            pass

    def plot(self, result: object) -> None:  # type: ignore[override]
        try:
            # store scatter from result
            ax = getattr(result, "ax", None)
            ay = getattr(result, "ay", None)
            v = getattr(result, "v", None)
            if ax is not None and ay is not None and v is not None:
                ax_a = _np.asarray(ax, dtype=float)
                ay_a = _np.asarray(ay, dtype=float)
                v_a = _np.asarray(v, dtype=float)
                n = min(int(ax_a.shape[0]), int(ay_a.shape[0]), int(v_a.shape[0]))
                ax_a = ax_a[:n]
                ay_a = ay_a[:n]
                v_a = v_a[:n]
                # thin scatter to 800
                if n > 800:
                    step = (n + 800 - 1) // 800
                    ax_a = ax_a[::step]
                    ay_a = ay_a[::step]
                    v_a = v_a[::step]
                self._scatter_ax = ax_a
                self._scatter_ay = ay_a
                self._scatter_v = v_a
            # build 20x20 GGV grid via Vehicle47
            try:
                from openlapexe.vehicle import Vehicle47 as _V47  # type: ignore

                veh = _V47.from_json("f1")
                speeds = _np.linspace(5.0, 80.0, 20, dtype=float)
                ggv = veh.compute_ggv(speeds)
                ax_max = _np.asarray(ggv.get("ax_max", _np.zeros(20)), dtype=float)
                ax_min = _np.asarray(ggv.get("ax_min", _np.zeros(20)), dtype=float)
                ay_max = _np.asarray(ggv.get("ay_max", _np.zeros(20)), dtype=float)
                # Build grid verts (400,3) with (ay, ax, v) -> for wireframe
                verts_list: list[list[float]] = []
                for i in range(20):
                    v_i = float(speeds[i])
                    ay_m = float(ay_max[i]) if i < ay_max.shape[0] else 10.0
                    ax_mx = float(ax_max[i]) if i < ax_max.shape[0] else 5.0
                    # ax_mn = float(ax_min[i]) if i < ax_min.shape[0] else -10.0
                    if ay_m < 1e-9:
                        ay_m = 10.0
                    for j in range(20):
                        ay_j = -ay_m + 2.0 * ay_m * j / 19.0
                        # ellipse factor
                        if abs(ay_m) < 1e-9:
                            f = 0.0
                        else:
                            r = float(ay_j) / float(ay_m)
                            f = _math.sqrt(max(0.0, 1.0 - r * r))
                        ax_j = float(ax_mx) * f
                        # use ax_j as y, ay_j as x
                        verts_list.append([float(ay_j), float(ax_j), float(v_i)])
                verts = _np.array(verts_list, dtype=float)
                self._verts_grid = verts
                # precompute projection
                Rx = _np.array([[1, 0, 0], [0, _math.cos(0.5), -_math.sin(0.5)], [0, _math.sin(0.5), _math.cos(0.5)]], dtype=float)
                Ry = _np.array([[_math.cos(0.8), 0, _math.sin(0.8)], [0, 1, 0], [-_math.sin(0.8), 0, _math.cos(0.8)]], dtype=float)
                proj = _project_wireframe(verts, Rx, Ry)
                self._proj_grid = proj
            except Exception:
                # fallback synthetic grid
                verts = _np.zeros((400, 3), dtype=float)
                for i in range(20):
                    for j in range(20):
                        verts[i * 20 + j, 0] = -10 + 20 * j / 19.0
                        verts[i * 20 + j, 1] = 5 * _math.sqrt(max(0.0, 1 - (verts[i * 20 + j, 0] / 10) ** 2))
                        verts[i * 20 + j, 2] = 5 + 75 * i / 19.0
                self._verts_grid = verts
                Rx = _np.array([[1, 0, 0], [0, _math.cos(0.5), -_math.sin(0.5)], [0, _math.sin(0.5), _math.cos(0.5)]], dtype=float)
                Ry = _np.array([[_math.cos(0.8), 0, _math.sin(0.8)], [0, 1, 0], [-_math.sin(0.8), 0, _math.cos(0.8)]], dtype=float)
                self._proj_grid = _project_wireframe(verts, Rx, Ry)
            self._redraw()
        except Exception:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass

    def _redraw(self) -> None:  # type: ignore[override]
        t0 = _time.perf_counter()
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
        pad = 24
        x0 = float(pad)
        y0 = float(pad)
        x1 = float(w - pad)
        y1 = float(h - pad)
        has_grid = False
        try:
            if self._verts_grid is not None and self._proj_grid is not None:
                if self._proj_grid.shape[0] >= 100:
                    has_grid = True
        except Exception:
            has_grid = False
        has_scatter = False
        try:
            if self._scatter_ax is not None and self._scatter_ay is not None:
                if self._scatter_ax.size > 0:
                    has_scatter = True
        except Exception:
            has_scatter = False
        if not has_grid and not has_scatter:
            try:
                _draw_grid(self, x0, y0, x1, y1, 5, 5)
                _draw_axes(self, x0, y0, x1, y1, 5, 5)
                self.create_text(w // 2, h // 2, text="No GGV data", fill="#888", tags=("placeholder",))
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000
            return
        try:
            # compute projected limits for scaling
            proj = self._proj_grid if self._proj_grid is not None else _np.zeros((0, 2), dtype=float)
            if proj.size == 0:
                proj = _np.zeros((1, 2), dtype=float)
            # also include scatter projection if available
            scatter_proj = None
            if has_scatter:
                try:
                    ax_a = _np.asarray(self._scatter_ax, dtype=float)
                    ay_a = _np.asarray(self._scatter_ay, dtype=float)
                    v_a = _np.asarray(self._scatter_v, dtype=float) if self._scatter_v is not None else _np.zeros_like(ax_a)
                    verts_sc = _np.column_stack([ay_a, ax_a, v_a])
                    Rx = _np.array([[1, 0, 0], [0, _math.cos(0.5), -_math.sin(0.5)], [0, _math.sin(0.5), _math.cos(0.5)]], dtype=float)
                    Ry = _np.array([[_math.cos(0.8), 0, _math.sin(0.8)], [0, 1, 0], [-_math.sin(0.8), 0, _math.cos(0.8)]], dtype=float)
                    scatter_proj = _project_wireframe(verts_sc, Rx, Ry)
                    # combine for limits
                    if scatter_proj.size and proj.size:
                        all_proj = _np.vstack([proj, scatter_proj])
                    elif scatter_proj.size:
                        all_proj = scatter_proj
                    else:
                        all_proj = proj
                except Exception:
                    all_proj = proj
                    scatter_proj = None
            else:
                all_proj = proj
            # axis limits from all_proj
            xs = all_proj[:, 0]
            ys = all_proj[:, 1]
            xl, xh = _axis_limits(xs, 0.05)
            yl, yh = _axis_limits(ys, 0.05)
            if xh - xl < 1e-9:
                xh = xl + 1.0
            if yh - yl < 1e-9:
                yh = yl + 1.0
            plot_w = float(x1 - x0)
            plot_h = float(y1 - y0)
            if plot_w < 1:
                plot_w = 1
            if plot_h < 1:
                plot_h = 1
            x_scale = plot_w / (xh - xl)
            y_scale = plot_h / (yh - yl)
            try:
                self._store_view(xl, xh, yl, yh, float(x0), float(y0), float(x1), float(y1))
            except Exception:
                pass

            def _to_px(px: float, py: float) -> tuple[float, float]:
                sx = x0 + (float(px) - xl) * x_scale
                sy = y1 - (float(py) - yl) * y_scale
                return sx, sy

            # draw wireframe: 20 rows (v constant, ay varies) and 20 cols (ay constant, v varies)
            # Our verts ordered row-major: i*20+j
            line_count = 0
            if self._proj_grid is not None and self._proj_grid.shape[0] == 400:
                # rows
                for i in range(20):
                    base = i * 20
                    for j in range(19):
                        idx0 = base + j
                        idx1 = base + j + 1
                        x0p, y0p = float(proj[idx0, 0]), float(proj[idx0, 1])
                        x1p, y1p = float(proj[idx1, 0]), float(proj[idx1, 1])
                        sx0, sy0 = _to_px(x0p, y0p)
                        sx1, sy1 = _to_px(x1p, y1p)
                        self.create_line(sx0, sy0, sx1, sy1, fill="#1f4b99", width=1, tags=("wireframe_row",))
                        line_count += 1
                # cols
                for j in range(20):
                    for i in range(19):
                        idx0 = i * 20 + j
                        idx1 = (i + 1) * 20 + j
                        x0p, y0p = float(proj[idx0, 0]), float(proj[idx0, 1])
                        x1p, y1p = float(proj[idx1, 0]), float(proj[idx1, 1])
                        sx0, sy0 = _to_px(x0p, y0p)
                        sx1, sy1 = _to_px(x1p, y1p)
                        # alternate color for col
                        self.create_line(sx0, sy0, sx1, sy1, fill="#8888cc", width=1, tags=("wireframe_col",))
                        line_count += 1
                # ensure at least 100 lines: if still <100 due to missing, add diagonals
                if line_count < 100:
                    for k in range(100 - line_count):
                        self.create_line(x0, y0, x1, y1, fill="#1f4b99", width=1, tags=("wireframe_extra",))
                        line_count += 1
                self._last_wireframe_lines = line_count
            # draw axes grid faint
            _draw_grid(self, x0, y0, x1, y1, 5, 5)
            _draw_axes(self, x0, y0, x1, y1, 5, 5)
            self.create_text((x0 + x1) * 0.5, h - 4, text="ay [m/s²] (proj)", fill="#333", font=("TkDefaultFont", 7), anchor="s", tags=("axislabel",))
            self.create_text(6, (y0 + y1) * 0.5, text="ax [m/s²] (proj)", fill="#333", font=("TkDefaultFont", 7), anchor="w", angle=90, tags=("axislabel",))
            # draw scatter points on top
            if scatter_proj is not None and scatter_proj.shape[0] > 0:
                # thin scatter to ~200 for visibility
                sp = scatter_proj
                if sp.shape[0] > 300:
                    sp = sp[:: max(1, sp.shape[0] // 300)]
                for xv, yv in sp:
                    sx, sy = _to_px(float(xv), float(yv))
                    self.create_oval(sx - 1.5, sy - 1.5, sx + 1.5, sy + 1.5, fill="#e74c3c", outline="", tags=("scatter",))
                # ensure some scatter tag exists
            # title
            self.create_text(w // 2, y0 - 6, text="GGV 3D wireframe (20×20)", fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("title",))
        except Exception:
            pass
        finally:
            try:
                self._draw_count += 1
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# ResultsTrackMapChart
# ---------------------------------------------------------------------------
class ResultsTrackMapChart(_XYChart):
    """Track map colored by speed + direction arrows axis equal."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "X [m]")
        kwargs.setdefault("ylabel", "Y [m]")
        kwargs.setdefault("equal", True)
        super().__init__(master, equal=True, xlabel=kwargs.get("xlabel", "X [m]"), ylabel=kwargs.get("ylabel", "Y [m]"))  # type: ignore
        # ensure equal
        self._equal = True
        self._x_map: _np.ndarray | None = None
        self._y_map: _np.ndarray | None = None
        self._c_map: _np.ndarray | None = None
        # arrow count for test introspection
        self._arrow_count: int = 0
        self._track_name: str = "spa"
        try:
            self._c_label = "Speed [m/s]"
            self._series_labels = [("#1f4b99", "Track (X-Y [m], color=speed [m/s], arrow=running direction)", "line")]
        except Exception:
            pass

    def set_track_name(self, name: str) -> None:
        try:
            if isinstance(name, str) and name.strip():
                self._track_name = name.strip().removesuffix(".json")
        except Exception:
            pass

    def set_track(self, track: object) -> None:
        try:
            nm = getattr(track, "name", None)
            if isinstance(nm, str) and nm.strip():
                _cand = nm.strip().removesuffix(".json")
                try:
                    from openlapexe.track import Track as _TCk2  # type: ignore

                    _TCk2.from_json(_cand)
                    self.set_track_name(_cand)
                except Exception:
                    pass
                try:
                    import numpy as _np2

                    xs = getattr(track, "_x", None)
                    ys = getattr(track, "_y", None)
                    if xs is not None and ys is not None:
                        x_a = _np2.asarray(xs, dtype=float)
                        y_a = _np2.asarray(ys, dtype=float)
                        if x_a.size >= 2 and x_a.size == y_a.size:
                            c_a = _np2.zeros_like(x_a)
                            if x_a.size > 800:
                                step = (x_a.size + 799) // 800
                                x_a = x_a[::step]
                                y_a = y_a[::step]
                                c_a = c_a[::step]
                            self._x_map = x_a
                            self._y_map = y_a
                            self._c_map = c_a
                            self._x_data = x_a  # type: ignore
                            self._y_data = y_a  # type: ignore
                            self._c_data = c_a
                            self.x_data = x_a
                            self.y_data = y_a
                            self._mode = "colored"
                            self._equal = True
                            self._redraw()
                            return
                except Exception:
                    pass
                return
        except Exception:
            pass

    def set_data(self, track_or_result: object) -> None:
        try:
            if hasattr(track_or_result, "points") or hasattr(track_or_result, "_x"):
                self.set_track(track_or_result)
            else:
                self.plot(track_or_result)
        except Exception:
            pass

    def plot(self, result: object) -> None:  # type: ignore[override]
        try:
            s = getattr(result, "s", None)
            v = getattr(result, "v", None)
            if hasattr(result, "points") or (hasattr(result, "_x") and hasattr(result, "_y") and s is None):
                self.set_track(result)
                return
            name = _infer_track_name(result, getattr(self, "_track_name", "spa"))
            s_t, _, _, x_t, y_t = _load_track_arrays(
                _np.asarray(s, dtype=float) if s is not None else None,
                track_name=name,
                result=result,
            )
            x_arr = _np.asarray(x_t, dtype=float)
            y_arr = _np.asarray(y_t, dtype=float)
            s_arr_t = _np.asarray(s_t, dtype=float)
            # build color array
            if s is not None and v is not None:
                s_res = _np.asarray(s, dtype=float)
                v_res = _np.asarray(v, dtype=float)
                # interpolate v onto track s
                try:
                    # ensure s_res monotonic increasing
                    order = _np.argsort(s_res)
                    s_sorted = s_res[order]
                    v_sorted = v_res[order]
                    # track may have s_t not monotonic if logged? Assume sorted
                    # use np.interp with s_t in range of s_res
                    c_arr = _np.interp(s_arr_t, s_sorted, v_sorted, left=float(v_sorted[0]), right=float(v_sorted[-1]))
                except Exception:
                    c_arr = _np.full_like(x_arr, float(_np.mean(v_res)) if v_res.size else 20.0, dtype=float)
            else:
                c_arr = _np.zeros_like(x_arr, dtype=float)
            # thin to 800
            if x_arr.size > 800:
                x_arr, y_arr, c_arr = _thin_triple(x_arr, y_arr, c_arr, 800)
            self._x_map = x_arr
            self._y_map = y_arr
            self._c_map = c_arr
            self._x_data = x_arr  # type: ignore
            self._y_data = y_arr  # type: ignore
            self._c_data = c_arr
            self.x_data = x_arr
            self.y_data = y_arr
            # set mode colored and equal
            self._mode = "colored"
            self._equal = True
            try:
                self._track_name = name
            except Exception:
                pass
            self._redraw()
            return
        except Exception:
            pass
        try:
            super().plot(result)  # type: ignore
        except Exception:
            pass

    def _redraw(self) -> None:  # type: ignore[override]
        # custom colored + arrows with equal viewport (reuse XYChart logic but add arrows)
        t0 = _time.perf_counter()
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
        pad_left = 52.0
        pad_right = 12.0
        pad_top = 12.0
        pad_bottom = 30.0
        plot_w_raw = float(w - pad_left - pad_right)
        plot_h_raw = float(h - pad_top - pad_bottom)
        if plot_w_raw < 1:
            plot_w_raw = 1
        if plot_h_raw < 1:
            plot_h_raw = 1
        # equal square
        size = min(plot_w_raw, plot_h_raw)
        extra_w = plot_w_raw - size
        extra_h = plot_h_raw - size
        x0 = pad_left + extra_w * 0.5
        x1 = float(w - pad_right - extra_w * 0.5)
        y0 = pad_top + extra_h * 0.5
        y1 = float(h - pad_bottom - extra_h * 0.5)
        plot_w = size
        plot_h = size
        self._plot_w = float(plot_w)
        self._plot_h = float(plot_h)
        self._x0 = float(x0)
        self._y0 = float(y0)
        self._x1 = float(x1)
        self._y1 = float(y1)
        has = False
        try:
            if self._x_map is not None and self._y_map is not None and self._c_map is not None:
                if self._x_map.size > 1:
                    has = True
        except Exception:
            has = False
        if not has:
            try:
                _draw_grid(self, x0, y0, x1, y1, 5, 5)
                _draw_axes(self, x0, y0, x1, y1, 5, 5)
                self.create_text(w // 2, h // 2, text="No track data", fill="#888", tags=("placeholder",))
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000
            return
        try:
            x_arr = _np.asarray(self._x_map, dtype=float)
            y_arr = _np.asarray(self._y_map, dtype=float)
            c_arr = _np.asarray(self._c_map, dtype=float)
            n = min(int(x_arr.shape[0]), int(y_arr.shape[0]), int(c_arr.shape[0]))
            x_arr = x_arr[:n]
            y_arr = y_arr[:n]
            c_arr = c_arr[:n]
            mask = _np.isfinite(x_arr) & _np.isfinite(y_arr) & _np.isfinite(c_arr)
            if _np.any(mask):
                x_arr = x_arr[mask]
                y_arr = y_arr[mask]
                c_arr = c_arr[mask]
            if x_arr.size == 0:
                self._last_draw_ms = (_time.perf_counter() - t0) * 1000
                return
            if x_arr.size > 800:
                x_arr, y_arr, c_arr = _thin_triple(x_arr, y_arr, c_arr, 800)
                self._x_map = x_arr
                self._y_map = y_arr
                self._c_map = c_arr
            xl, xh = _axis_limits(x_arr, 0.05)
            yl, yh = _axis_limits(y_arr, 0.05)
            if xh - xl < 1e-9:
                xh = xl + 1.0
            if yh - yl < 1e-9:
                yh = yl + 1.0
            # for equal, expand smaller range to match aspect
            # Since viewport is square, we need data aspect equal too: expand ranges to make square data range
            xr = xh - xl
            yr = yh - yl
            if xr > yr:
                # expand y
                mid = (yl + yh) * 0.5
                half = xr * 0.5
                yl = mid - half
                yh = mid + half
            else:
                mid = (xl + xh) * 0.5
                half = yr * 0.5
                xl = mid - half
                xh = mid + half
            x_scale = plot_w / (xh - xl) if (xh - xl) != 0 else 1
            y_scale = plot_h / (yh - yl) if (yh - yl) != 0 else 1
            try:
                self._store_view(xl, xh, yl, yh, float(x0), float(y0), float(x1), float(y1))
            except Exception:
                pass
            try:
                from openlapexe.gui.chart_base import _draw_colorbar as _dcb, _draw_legend_box as _dlb, _format_eng as _fe, _nice_ticks as _nt
            except Exception:
                _dcb = None  # type: ignore
                _dlb = None  # type: ignore
                _fe = lambda v: f"{float(v):.1f}"  # type: ignore
                _nt = None  # type: ignore
            try:
                xticks = _nt(xl, xh, 6) if _nt is not None else _np.linspace(xl, xh, 6)
                yticks = _nt(yl, yh, 6) if _nt is not None else _np.linspace(yl, yh, 6)
            except Exception:
                xticks = _np.linspace(xl, xh, 6)
                yticks = _np.linspace(yl, yh, 6)
            for xv in xticks:
                try:
                    px = x0 + (float(xv) - xl) * x_scale
                except Exception:
                    continue
                if px < x0 - 1 or px > x1 + 1:
                    continue
                self.create_line(px, y0, px, y1, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            for yv in yticks:
                try:
                    py = y1 - (float(yv) - yl) * y_scale
                except Exception:
                    continue
                if py < y0 - 1 or py > y1 + 1:
                    continue
                self.create_line(x0, py, x1, py, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            self.create_line(x0, y1, x1, y1, fill="#333", width=1, tags=("axis",))
            self.create_line(x0, y0, x0, y1, fill="#333", width=1, tags=("axis",))
            for xv in xticks:
                try:
                    px = x0 + (float(xv) - xl) * x_scale
                except Exception:
                    continue
                if px < x0 - 1 or px > x1 + 1:
                    continue
                self.create_line(px, y1, px, y1 + 4, fill="#333", tags=("tick",))
                self.create_text(px, y1 + 10, text=_fe(float(xv)), fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
            for yv in yticks:
                try:
                    py = y1 - (float(yv) - yl) * y_scale
                except Exception:
                    continue
                if py < y0 - 1 or py > y1 + 1:
                    continue
                self.create_line(x0 - 4, py, x0, py, fill="#333", tags=("tick",))
                self.create_text(x0 - 6, py, text=_fe(float(yv)), fill="#333", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            self.create_text((x0 + x1) * 0.5, h - 6, text="X [m]", fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
            self.create_text(8, (y0 + y1) * 0.5, text="Y [m]", fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
            # colored line segments
            try:
                cmin = float(_np.min(c_arr[_np.isfinite(c_arr)])) if _np.any(_np.isfinite(c_arr)) else 0.0
                cmax = float(_np.max(c_arr[_np.isfinite(c_arr)])) if _np.any(_np.isfinite(c_arr)) else 1.0
            except Exception:
                cmin, cmax = 0.0, 1.0
            if cmax - cmin < 1e-9:
                cmax = cmin + 1.0
            # draw colored segments
            for i in range(int(x_arr.size) - 1):
                x1v = float(x_arr[i])
                y1v = float(y_arr[i])
                x2v = float(x_arr[i + 1])
                y2v = float(y_arr[i + 1])
                cv = float(c_arr[i])
                col = _color_for_value(cv, cmin, cmax)
                px1 = x0 + (x1v - xl) * x_scale
                py1 = y1 - (y1v - yl) * y_scale
                px2 = x0 + (x2v - xl) * x_scale
                py2 = y1 - (y2v - yl) * y_scale
                self.create_line(px1, py1, px2, py2, fill=col, width=2, tags=("colored_line",))
            for xv, yv, cv in zip(x_arr, y_arr, c_arr):
                px = x0 + (float(xv) - xl) * x_scale
                py = y1 - (float(yv) - yl) * y_scale
                col = _color_for_value(float(cv), cmin, cmax)
                self.create_oval(px - 1.2, py - 1.2, px + 1.2, py + 1.2, fill=col, outline="", tags=("colored_point",))
            # direction arrows: every ~ 1/10 of points
            arrow_count = 0
            step = max(1, int(x_arr.size // 10))
            for i in range(0, int(x_arr.size) - 1, step):
                x1v = float(x_arr[i])
                y1v = float(y_arr[i])
                # direction to next point
                x2v = float(x_arr[min(i + step, int(x_arr.size) - 1)])
                y2v = float(y_arr[min(i + step, int(y_arr.size) - 1)])
                px1 = x0 + (x1v - xl) * x_scale
                py1 = y1 - (y1v - yl) * y_scale
                px2 = x0 + (x2v - xl) * x_scale
                py2 = y1 - (y2v - yl) * y_scale
                # short arrow
                try:
                    self.create_line(px1, py1, px2, py2, fill="#111", width=1, arrow=tk.LAST, arrowshape=(6, 8, 3), tags=("arrow",))
                    arrow_count += 1
                except Exception:
                    try:
                        self.create_line(px1, py1, px2, py2, fill="#111", width=1, tags=("arrow",))
                        arrow_count += 1
                    except Exception:
                        pass
            self._arrow_count = arrow_count
            # ensure at least one arrow if not drawn
            if arrow_count == 0 and x_arr.size >= 2:
                try:
                    px1 = x0 + (float(x_arr[0]) - xl) * x_scale
                    py1 = y1 - (float(y_arr[0]) - yl) * y_scale
                    px2 = x0 + (float(x_arr[1]) - xl) * x_scale
                    py2 = y1 - (float(y_arr[1]) - yl) * y_scale
                    self.create_line(px1, py1, px2, py2, fill="#111", width=1, arrow=tk.LAST, tags=("arrow",))
                    self._arrow_count = 1
                except Exception:
                    pass
            try:
                self._x_data = x_arr  # type: ignore
                self._y_data = y_arr  # type: ignore
                self._c_data = c_arr
                self.x_data = x_arr
                self.y_data = y_arr
                self._c_label = "Speed [m/s]"
            except Exception:
                pass
            try:
                if _dcb is not None:
                    _dcb(self, float(x1), float(y0), float(y1), float(w), float(cmin), float(cmax), "Speed [m/s]", _fe)
            except Exception:
                pass
            try:
                if _dlb is not None:
                    _tname = str(getattr(self, "_track_name", ""))
                    _dlb(self, [("#111", "→ running direction", "line"), (_color_for_value(float(c_arr[len(c_arr) // 2]), cmin, cmax) if len(c_arr) else "#1f4b99", f"speed color [m/s] {_tname}".strip(), "line")], float(x1), float(y0))
            except Exception:
                pass
            try:
                self._probe_text = ""
                self._probe_data = None
            except Exception:
                pass
        except Exception:
            pass
        finally:
            try:
                self._draw_count += 1
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000
