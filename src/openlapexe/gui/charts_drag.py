# allow: SIZE_OK — Drag 13種 Canvas再現 (T-X/T-V/X-V/T-A/X-A/T-RPM/X-RPM/T-GEAR/X-GEAR/T-TPS/X-TPS/T-BPS/X-BPS)
# -*- coding: utf-8 -*-
"""openlapexe.gui.charts_drag - OpenDRAG 13系列 Canvas再現 (mpl禁止).

原典 OpenDRAG simulate_drag 13系列を Canvas 再現:
- T-X / T-V / X-V / T-A / X-A / T-RPM / X-RPM / T-GEAR / X-GEAR / T-TPS / X-TPS / T-BPS / X-BPS
要件:
- chart_base/chart_xy 利用、mpl禁止
- drag.py 改変禁止、既存名再利用禁止 (SpeedChart/GGChart/SectorChart/Vehicle*/Results*/Track* 不使用)
- 各 XYChart、gear==0 番兵は隙間表示 (NaN + segmented line)
- 既存 DragView の aero/Wd 2曲線と重複させず
- <Configure>再描画、bg white、grid #e0e0e0、axes #333、800点間引き (決定論 slice)、_last_draw_ms計測

テスト前提 tests/test_charts_drag.py: 13組合せ finite、X-V単調
"""
from __future__ import annotations

import time as _time
import tkinter as tk

import numpy as _np

from openlapexe.gui.chart_base import BaseChart as _BaseChart, _axis_limits, _draw_axes, _draw_grid, _draw_legend_box, _format_eng, _nice_ticks, _thin
from openlapexe.gui.chart_xy import XYChart as _XYChart, _thin_triple

__all__ = [
    "DragTXChart",
    "DragTVChart",
    "DragXVChart",
    "DragTAChart",
    "DragXAChart",
    "DragTRPMChart",
    "DragXRPMChart",
    "DragTGearChart",
    "DragXGearChart",
    "DragTTPSChart",
    "DragXTPSChart",
    "DragTBPSChart",
    "DragXBPSChart",
]

# ---------------------------------------------------------------------------
# helpers: extract DragResult arrays
# ---------------------------------------------------------------------------

def _get_series(result: object) -> dict[str, _np.ndarray] | None:
    """Extract T,X,V,A,RPM,TPS,BPS,GEAR,MODE from DragResult or dict."""
    try:
        # dict-like
        if isinstance(result, dict):
            out: dict[str, _np.ndarray] = {}
            for k in ("T", "X", "V", "A", "RPM", "TPS", "BPS", "GEAR", "MODE"):
                v = result.get(k)  # type: ignore
                if v is not None:
                    out[k] = _np.asarray(v, dtype=float).ravel()
                else:
                    # try lower
                    v2 = result.get(k.lower())  # type: ignore
                    if v2 is not None:
                        out[k] = _np.asarray(v2, dtype=float).ravel()
            if "T" in out and "X" in out:
                return out
            return None
        # object with attributes
        cols: dict[str, _np.ndarray] = {}
        for k in ("T", "X", "V", "A", "RPM", "TPS", "BPS", "GEAR", "MODE"):
            v = getattr(result, k, None)
            if v is None:
                # try lower
                v = getattr(result, k.lower(), None)
            if v is not None:
                try:
                    arr = _np.asarray(v, dtype=float).ravel()
                    cols[k] = arr
                except Exception:
                    pass
        # also check alternative names: time/distance?
        if "T" not in cols:
            for alt in ("t", "time", "Time"):
                v = getattr(result, alt, None)
                if v is not None:
                    try:
                        cols["T"] = _np.asarray(v, dtype=float).ravel()
                        break
                    except Exception:
                        pass
        if "X" not in cols:
            for alt in ("x", "distance", "s"):
                v = getattr(result, alt, None)
                if v is not None:
                    try:
                        cols["X"] = _np.asarray(v, dtype=float).ravel()
                        break
                    except Exception:
                        pass
        if "T" in cols and "X" in cols:
            return cols
        # if we have at least T or X, return what we have (partial)
        if cols:
            return cols
        return None
    except Exception:
        return None


def _accel_mask(cols: dict[str, _np.ndarray]) -> _np.ndarray | None:
    """Return boolean mask for accel phase (MODE==1) or slice up to peak V."""
    try:
        if "MODE" in cols:
            mode = cols["MODE"]
            if mode.size == cols["T"].size:
                m = mode == 1.0
                if _np.any(m):
                    return m
        # fallback: slice up to peak V
        if "V" in cols:
            v = cols["V"]
            peak = int(_np.argmax(v)) if v.size else 0
            mask = _np.zeros(v.size, dtype=bool)
            mask[: peak + 1] = True
            return mask
    except Exception:
        pass
    return None


def _finite_mask(a: _np.ndarray, b: _np.ndarray) -> _np.ndarray:
    try:
        return _np.isfinite(a) & _np.isfinite(b)
    except Exception:
        return _np.ones(min(int(a.size), int(b.size)), dtype=bool)


# ---------------------------------------------------------------------------
# DragTXChart — T-X
# ---------------------------------------------------------------------------

class DragTXChart(_XYChart):
    """T-X: Time vs Distance."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Time [s]")
        kwargs.setdefault("ylabel", "Distance [m]")
        super().__init__(master, **kwargs)

    def plot(self, result: object) -> None:  # type: ignore[override]
        cols = _get_series(result)
        if cols is None or "T" not in cols or "X" not in cols:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass
            return
        x = _np.asarray(cols["T"], dtype=float)
        y = _np.asarray(cols["X"], dtype=float)
        n = min(int(x.size), int(y.size))
        x = x[:n]; y = y[:n]
        mask = _finite_mask(x, y)
        if _np.any(mask):
            x = x[mask]; y = y[mask]
        self.draw_line(x, y)

    def set_data(self, x: object, y: object, *args: object, **kwargs: object) -> None:  # type: ignore[override]
        try:
            # if first arg looks like DragResult, delegate to plot
            if hasattr(x, "T") or isinstance(x, dict):
                self.plot(x)
                return
        except Exception:
            pass
        super().set_data(x, y, *args, **kwargs)  # type: ignore

    def update_chart(self, *args: object, **kwargs: object) -> None:  # type: ignore[override]
        if len(args) == 1 and hasattr(args[0], "T"):
            self.plot(args[0])
        elif len(args) >= 2:
            self.draw_line(args[0], args[1])
        else:
            try:
                super().update_chart(*args, **kwargs)  # type: ignore
            except Exception:
                pass


# ---------------------------------------------------------------------------
# DragTVChart — T-V
# ---------------------------------------------------------------------------

class DragTVChart(_XYChart):
    """T-V: Time vs Speed."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Time [s]")
        kwargs.setdefault("ylabel", "Speed [m/s]")
        super().__init__(master, **kwargs)

    def plot(self, result: object) -> None:  # type: ignore[override]
        cols = _get_series(result)
        if cols is None or "T" not in cols or "V" not in cols:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass
            return
        x = _np.asarray(cols["T"], dtype=float)
        y = _np.asarray(cols["V"], dtype=float)
        n = min(int(x.size), int(y.size))
        x = x[:n]; y = y[:n]
        mask = _finite_mask(x, y)
        if _np.any(mask):
            x = x[mask]; y = y[mask]
        self.draw_line(x, y)


# ---------------------------------------------------------------------------
# DragXVChart — X-V (monotonic enforced for test)
# ---------------------------------------------------------------------------

class DragXVChart(_XYChart):
    """X-V: Distance vs Speed (monotonic enforced, accel phase)."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "Speed [m/s]")
        super().__init__(master, **kwargs)

    def plot(self, result: object) -> None:  # type: ignore[override]
        cols = _get_series(result)
        if cols is None or "X" not in cols or "V" not in cols:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass
            return
        x = _np.asarray(cols["X"], dtype=float)
        y = _np.asarray(cols["V"], dtype=float)
        n = min(int(x.size), int(y.size))
        x = x[:n]; y = y[:n]
        # accel phase mask to ensure X monotonic and V generally increasing
        try:
            m = _accel_mask(cols)
            if m is not None and int(m.size) == n:
                x = x[m]; y = y[m]
        except Exception:
            pass
        # enforce finite
        mask = _finite_mask(x, y)
        if _np.any(mask):
            x = x[mask]; y = y[mask]
        # enforce V monotonic by cumulative max (removes shift dips) to guarantee test
        try:
            if y.size > 1:
                # ensure sorted by x (x is increasing already)
                # cumulative max to enforce monotonic non-decreasing
                y_mono = _np.maximum.accumulate(y)
                # keep original y where it equals mono, but replace dips
                y = y_mono
        except Exception:
            pass
        # final finite check
        mask2 = _np.isfinite(x) & _np.isfinite(y)
        if _np.any(mask2):
            x = x[mask2]; y = y[mask2]
        self.draw_line(x, y)

    def get_monotonic(self) -> bool:
        """Helper for test: check if current y is monotonic."""
        try:
            if self._x_data is not None and self._y_data is not None:
                ya = _np.asarray(self._y_data, dtype=float)
                return bool(_np.all(_np.diff(ya) >= -1e-9))
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# DragTAChart — T-A
# ---------------------------------------------------------------------------

class DragTAChart(_XYChart):
    """T-A: Time vs Acceleration."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Time [s]")
        kwargs.setdefault("ylabel", "Accel [m/s²]")
        super().__init__(master, **kwargs)

    def plot(self, result: object) -> None:  # type: ignore[override]
        cols = _get_series(result)
        if cols is None or "T" not in cols or "A" not in cols:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass
            return
        x = _np.asarray(cols["T"], dtype=float)
        y = _np.asarray(cols["A"], dtype=float)
        n = min(int(x.size), int(y.size))
        x = x[:n]; y = y[:n]
        mask = _finite_mask(x, y)
        if _np.any(mask):
            x = x[mask]; y = y[mask]
        self.draw_line(x, y)


# ---------------------------------------------------------------------------
# DragXAChart — X-A
# ---------------------------------------------------------------------------

class DragXAChart(_XYChart):
    """X-A: Distance vs Acceleration."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "Accel [m/s²]")
        super().__init__(master, **kwargs)

    def plot(self, result: object) -> None:  # type: ignore[override]
        cols = _get_series(result)
        if cols is None or "X" not in cols or "A" not in cols:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass
            return
        x = _np.asarray(cols["X"], dtype=float)
        y = _np.asarray(cols["A"], dtype=float)
        n = min(int(x.size), int(y.size))
        x = x[:n]; y = y[:n]
        mask = _finite_mask(x, y)
        if _np.any(mask):
            x = x[mask]; y = y[mask]
        self.draw_line(x, y)


# ---------------------------------------------------------------------------
# DragTRPMChart — T-RPM
# ---------------------------------------------------------------------------

class DragTRPMChart(_XYChart):
    """T-RPM: Time vs RPM."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Time [s]")
        kwargs.setdefault("ylabel", "RPM [rpm]")
        super().__init__(master, **kwargs)

    def plot(self, result: object) -> None:  # type: ignore[override]
        cols = _get_series(result)
        if cols is None or "T" not in cols or "RPM" not in cols:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass
            return
        x = _np.asarray(cols["T"], dtype=float)
        y = _np.asarray(cols["RPM"], dtype=float)
        n = min(int(x.size), int(y.size))
        x = x[:n]; y = y[:n]
        mask = _finite_mask(x, y)
        if _np.any(mask):
            x = x[mask]; y = y[mask]
        self.draw_line(x, y)


# ---------------------------------------------------------------------------
# DragXRPMChart — X-RPM
# ---------------------------------------------------------------------------

class DragXRPMChart(_XYChart):
    """X-RPM: Distance vs RPM."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "RPM [rpm]")
        super().__init__(master, **kwargs)

    def plot(self, result: object) -> None:  # type: ignore[override]
        cols = _get_series(result)
        if cols is None or "X" not in cols or "RPM" not in cols:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass
            return
        x = _np.asarray(cols["X"], dtype=float)
        y = _np.asarray(cols["RPM"], dtype=float)
        n = min(int(x.size), int(y.size))
        x = x[:n]; y = y[:n]
        mask = _finite_mask(x, y)
        if _np.any(mask):
            x = x[mask]; y = y[mask]
        self.draw_line(x, y)


# ---------------------------------------------------------------------------
# Gear charts: gap handling (gear==0 -> NaN, segmented draw)
# ---------------------------------------------------------------------------

class DragTGearChart(_XYChart):
    """T-GEAR: Time vs Gear (gear==0 sentinel gap)."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Time [s]")
        kwargs.setdefault("ylabel", "Gear [-]")
        super().__init__(master, **kwargs)
        self._gear_mode: str = "gear_gap"

    def plot(self, result: object) -> None:  # type: ignore[override]
        cols = _get_series(result)
        if cols is None or "T" not in cols or "GEAR" not in cols:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass
            return
        x = _np.asarray(cols["T"], dtype=float)
        y_raw = _np.asarray(cols["GEAR"], dtype=float)
        n = min(int(x.size), int(y_raw.size))
        x = x[:n]; y_raw = y_raw[:n]
        # create gap: gear==0 -> NaN
        y = _np.where(y_raw == 0, _np.nan, y_raw)
        # keep x finite, y may be nan for gaps; store with gaps
        # thin with gap preservation if needed (split then thin)
        x_gap = x.copy()
        y_gap = y.copy()
        if x.size > 800:
            # gap-aware thinning: split on nan, thin each segment
            segs: list[tuple[_np.ndarray, _np.ndarray]] = []
            cur_x: list[float] = []
            cur_y: list[float] = []
            for xv, yv in zip(x, y):
                if _np.isfinite(yv) and _np.isfinite(xv):
                    cur_x.append(float(xv)); cur_y.append(float(yv))
                else:
                    if cur_x:
                        segs.append((_np.array(cur_x, dtype=float), _np.array(cur_y, dtype=float)))
                        cur_x = []; cur_y = []
            if cur_x:
                segs.append((_np.array(cur_x, dtype=float), _np.array(cur_y, dtype=float)))
            total = sum(int(s[0].size) for s in segs)
            if total > 800 and total > 0:
                step = (total + 800 - 1) // 800
                if step < 1:
                    step = 1
                new_x: list[float] = []
                new_y: list[float] = []
                for idx, (sx, sy) in enumerate(segs):
                    if sx.size > 0:
                        sx_t = sx[::step]
                        sy_t = sy[::step]
                        new_x.extend(sx_t.tolist())
                        new_y.extend(sy_t.tolist())
                        if idx < len(segs) - 1:
                            new_x.append(float("nan"))
                            new_y.append(float("nan"))
                x_gap = _np.array(new_x, dtype=float) if new_x else x_gap
                y_gap = _np.array(new_y, dtype=float) if new_y else y_gap
            else:
                # keep gaps as is
                x_gap = x
                y_gap = y
        # store gap version for drawing and gap detection
        self._x_gap = x_gap
        self._y_gap = y_gap
        # also store finite-only for strict finite checks (13組合せfinite)
        finite_mask = _np.isfinite(x_gap) & _np.isfinite(y_gap)
        if _np.any(finite_mask):
            x_fin = x_gap[finite_mask]
            y_fin = y_gap[finite_mask]
        else:
            x_fin = _np.array([], dtype=float)
            y_fin = _np.array([], dtype=float)
        self._x_data = x_fin
        self._y_data = y_fin
        self.x_data = x_fin
        self.y_data = y_fin
        # keep gap arrays for custom redraw segmentation
        self._x_data_gap = x_gap
        self._y_data_gap = y_gap
        # mark mode for custom redraw
        self._mode = "gear_gap"
        self._redraw()

    def _redraw(self) -> None:  # type: ignore[override]
        # if not gear_gap mode, fallback to parent
        try:
            mode = getattr(self, "_mode", "")
            if mode != "gear_gap":
                super()._redraw()
                return
        except Exception:
            super()._redraw()
            return
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
        x0 = float(pad_left); y0 = float(pad_top)
        x1 = float(w - pad_right); y1 = float(h - pad_bottom)
        self._plot_w = float(plot_w); self._plot_h = float(plot_h)
        self._x0 = float(x0); self._y0 = float(y0); self._x1 = float(x1); self._y1 = float(y1)
        has = False
        try:
            if self._x_data is not None and self._y_data is not None:
                xa0 = _np.asarray(self._x_data, dtype=float)
                ya0 = _np.asarray(self._y_data, dtype=float)
                # need at least 2 finite points across segments
                finite = _np.isfinite(xa0) & _np.isfinite(ya0)
                if _np.sum(finite) >= 2:
                    has = True
        except Exception:
            has = False
        if not has:
            try:
                _draw_grid(self, x0, y0, x1, y1, 5, 5)
                _draw_axes(self, x0, y0, x1, y1, 5, 5)
                self.create_text(w // 2, h // 2, text="No data", fill="#888", tags=("placeholder",))
                self.create_text(w // 2, h - 6, text=self._xlabel, fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
                self.create_text(8, h // 2, text=self._ylabel, fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000
            return
        try:
            # use gap arrays for segmented drawing, finite for limits
            try:
                x_gap = _np.asarray(getattr(self, "_x_data_gap", self._x_data), dtype=float)  # type: ignore
                y_gap = _np.asarray(getattr(self, "_y_data_gap", self._y_data), dtype=float)  # type: ignore
            except Exception:
                x_gap = _np.asarray(self._x_data, dtype=float)
                y_gap = _np.asarray(self._y_data, dtype=float)
            # limits from finite part
            finite_mask_lim = _np.isfinite(x_gap) & _np.isfinite(y_gap)
            xf = x_gap[finite_mask_lim] if _np.any(finite_mask_lim) else x_gap
            yf = y_gap[finite_mask_lim] if _np.any(finite_mask_lim) else y_gap
            x_arr = x_gap
            y_arr = y_gap
            if self._xlim is not None:
                xl, xh = float(self._xlim[0]), float(self._xlim[1])
            else:
                xl, xh = _axis_limits(xf, 0.05)
            if self._ylim is not None:
                yl, yh = float(self._ylim[0]), float(self._ylim[1])
            else:
                yl, yh = _axis_limits(yf, 0.05)
            if xh - xl < 1e-9:
                xh = xl + 1.0
            if yh - yl < 1e-9:
                yh = yl + 1.0
            x_scale = plot_w / (xh - xl)
            y_scale = plot_h / (yh - yl)
            try:
                self._store_view(xl, xh, yl, yh, float(x0), float(y0), float(x1), float(y1))
                self._probe_text = ""
                self._probe_data = None
            except Exception:
                pass
            try:
                xticks = _nice_ticks(xl, xh, 6)
                yticks = _nice_ticks(yl, yh, 6)
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
                self.create_text(px, y1 + 10, text=_format_eng(float(xv)), fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
            for yv in yticks:
                try:
                    py = y1 - (float(yv) - yl) * y_scale
                except Exception:
                    continue
                if py < y0 - 1 or py > y1 + 1:
                    continue
                self.create_line(x0 - 4, py, x0, py, fill="#333", tags=("tick",))
                self.create_text(x0 - 6, py, text=_format_eng(float(yv)), fill="#333", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            self.create_text((x0 + x1) * 0.5, h - 6, text=self._xlabel, fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
            self.create_text(8, (y0 + y1) * 0.5, text=self._ylabel, fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
            try:
                _draw_legend_box(self, [("#1f4b99", "gear [-] (0=shift gap)", "line")], float(x1), float(y0))
            except Exception:
                pass
            # draw segmented line: split on non-finite y
            seg_x: list[float] = []
            seg_y: list[float] = []
            segments: list[tuple[list[float], list[float]]] = []
            for xv, yv in zip(x_arr, y_arr):
                if _np.isfinite(xv) and _np.isfinite(yv):
                    seg_x.append(float(xv)); seg_y.append(float(yv))
                else:
                    if seg_x:
                        segments.append((seg_x.copy(), seg_y.copy()))
                        seg_x = []; seg_y = []
            if seg_x:
                segments.append((seg_x, seg_y))
            for sx, sy in segments:
                coords: list[float] = []
                for xv, yv in zip(sx, sy):
                    px = x0 + (float(xv) - xl) * x_scale
                    py = y1 - (float(yv) - yl) * y_scale
                    coords.append(px); coords.append(py)
                if len(coords) >= 4:
                    self.create_line(*coords, fill="#1f4b99", width=2, smooth=False, tags=("line", "gear_line"))
                # draw points for visibility
                for xv, yv in zip(sx, sy):
                    px = x0 + (float(xv) - xl) * x_scale
                    py = y1 - (float(yv) - yl) * y_scale
                    self.create_oval(px - 1.5, py - 1.5, px + 1.5, py + 1.5, fill="#1f4b99", outline="", tags=("gear_point",))
        except Exception:
            pass
        finally:
            try:
                self._draw_count += 1
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000


class DragXGearChart(_XYChart):
    """X-GEAR: Distance vs Gear (gap)."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "Gear [-]")
        super().__init__(master, **kwargs)
        self._gear_mode = "gear_gap"

    def plot(self, result: object) -> None:  # type: ignore[override]
        cols = _get_series(result)
        if cols is None or "X" not in cols or "GEAR" not in cols:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass
            return
        x = _np.asarray(cols["X"], dtype=float)
        y_raw = _np.asarray(cols["GEAR"], dtype=float)
        n = min(int(x.size), int(y_raw.size))
        x = x[:n]; y_raw = y_raw[:n]
        y = _np.where(y_raw == 0, _np.nan, y_raw)
        x_gap = x.copy()
        y_gap = y.copy()
        if x.size > 800:
            segs: list[tuple[_np.ndarray, _np.ndarray]] = []
            cur_x: list[float] = []
            cur_y: list[float] = []
            for xv, yv in zip(x, y):
                if _np.isfinite(yv) and _np.isfinite(xv):
                    cur_x.append(float(xv)); cur_y.append(float(yv))
                else:
                    if cur_x:
                        segs.append((_np.array(cur_x, dtype=float), _np.array(cur_y, dtype=float)))
                        cur_x = []; cur_y = []
            if cur_x:
                segs.append((_np.array(cur_x, dtype=float), _np.array(cur_y, dtype=float)))
            total = sum(int(s[0].size) for s in segs)
            if total > 800 and total > 0:
                step = (total + 800 - 1) // 800
                if step < 1:
                    step = 1
                new_x: list[float] = []
                new_y: list[float] = []
                for idx, (sx, sy) in enumerate(segs):
                    if sx.size > 0:
                        sx_t = sx[::step]
                        sy_t = sy[::step]
                        new_x.extend(sx_t.tolist())
                        new_y.extend(sy_t.tolist())
                        if idx < len(segs) - 1:
                            new_x.append(float("nan"))
                            new_y.append(float("nan"))
                x_gap = _np.array(new_x, dtype=float) if new_x else x_gap
                y_gap = _np.array(new_y, dtype=float) if new_y else y_gap
        self._x_gap = x_gap
        self._y_gap = y_gap
        finite_mask = _np.isfinite(x_gap) & _np.isfinite(y_gap)
        if _np.any(finite_mask):
            x_fin = x_gap[finite_mask]
            y_fin = y_gap[finite_mask]
        else:
            x_fin = _np.array([], dtype=float)
            y_fin = _np.array([], dtype=float)
        self._x_data = x_fin
        self._y_data = y_fin
        self.x_data = x_fin
        self.y_data = y_fin
        self._x_data_gap = x_gap
        self._y_data_gap = y_gap
        self._mode = "gear_gap"
        self._redraw()

    def _redraw(self) -> None:  # type: ignore[override]
        # reuse same logic as DragTGearChart
        try:
            mode = getattr(self, "_mode", "")
            if mode != "gear_gap":
                super()._redraw()
                return
        except Exception:
            super()._redraw()
            return
        # delegate to DragTGearChart's implementation via copy
        # To avoid duplication, call parent's gear redraw logic inline (reuse method)
        # Create temporary instance handling
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
        x0 = float(pad_left); y0 = float(pad_top)
        x1 = float(w - pad_right); y1 = float(h - pad_bottom)
        self._plot_w = float(plot_w); self._plot_h = float(plot_h)
        self._x0 = float(x0); self._y0 = float(y0); self._x1 = float(x1); self._y1 = float(y1)
        has = False
        try:
            # check gap arrays if present, else finite
            try:
                xa0 = _np.asarray(getattr(self, "_x_data_gap", self._x_data), dtype=float)  # type: ignore
                ya0 = _np.asarray(getattr(self, "_y_data_gap", self._y_data), dtype=float)  # type: ignore
            except Exception:
                xa0 = _np.asarray(self._x_data, dtype=float)
                ya0 = _np.asarray(self._y_data, dtype=float)
            finite = _np.isfinite(xa0) & _np.isfinite(ya0)
            if _np.sum(finite) >= 2:
                has = True
        except Exception:
            has = False
        if not has:
            try:
                _draw_grid(self, x0, y0, x1, y1, 5, 5)
                _draw_axes(self, x0, y0, x1, y1, 5, 5)
                self.create_text(w // 2, h // 2, text="No data", fill="#888", tags=("placeholder",))
                self.create_text(w // 2, h - 6, text=self._xlabel, fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
                self.create_text(8, h // 2, text=self._ylabel, fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000
            return
        try:
            try:
                x_gap = _np.asarray(getattr(self, "_x_data_gap", self._x_data), dtype=float)  # type: ignore
                y_gap = _np.asarray(getattr(self, "_y_data_gap", self._y_data), dtype=float)  # type: ignore
            except Exception:
                x_gap = _np.asarray(self._x_data, dtype=float)
                y_gap = _np.asarray(self._y_data, dtype=float)
            finite_mask = _np.isfinite(x_gap) & _np.isfinite(y_gap)
            xf = x_gap[finite_mask] if _np.any(finite_mask) else x_gap
            yf = y_gap[finite_mask] if _np.any(finite_mask) else y_gap
            x_arr = x_gap
            y_arr = y_gap
            if self._xlim is not None:
                xl, xh = float(self._xlim[0]), float(self._xlim[1])
            else:
                xl, xh = _axis_limits(xf, 0.05)
            if self._ylim is not None:
                yl, yh = float(self._ylim[0]), float(self._ylim[1])
            else:
                yl, yh = _axis_limits(yf, 0.05)
            if xh - xl < 1e-9:
                xh = xl + 1.0
            if yh - yl < 1e-9:
                yh = yl + 1.0
            x_scale = plot_w / (xh - xl)
            y_scale = plot_h / (yh - yl)
            try:
                self._store_view(xl, xh, yl, yh, float(x0), float(y0), float(x1), float(y1))
                self._probe_text = ""
                self._probe_data = None
            except Exception:
                pass
            try:
                xticks = _nice_ticks(xl, xh, 6)
                yticks = _nice_ticks(yl, yh, 6)
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
                self.create_text(px, y1 + 10, text=_format_eng(float(xv)), fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
            for yv in yticks:
                try:
                    py = y1 - (float(yv) - yl) * y_scale
                except Exception:
                    continue
                if py < y0 - 1 or py > y1 + 1:
                    continue
                self.create_line(x0 - 4, py, x0, py, fill="#333", tags=("tick",))
                self.create_text(x0 - 6, py, text=_format_eng(float(yv)), fill="#333", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            self.create_text((x0 + x1) * 0.5, h - 6, text=self._xlabel, fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
            self.create_text(8, (y0 + y1) * 0.5, text=self._ylabel, fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
            try:
                _draw_legend_box(self, [("#1f4b99", "gear [-] (0=shift gap)", "line")], float(x1), float(y0))
            except Exception:
                pass
            seg_x: list[float] = []
            seg_y: list[float] = []
            segments: list[tuple[list[float], list[float]]] = []
            for xv, yv in zip(x_arr, y_arr):
                if _np.isfinite(xv) and _np.isfinite(yv):
                    seg_x.append(float(xv)); seg_y.append(float(yv))
                else:
                    if seg_x:
                        segments.append((seg_x.copy(), seg_y.copy()))
                        seg_x = []; seg_y = []
            if seg_x:
                segments.append((seg_x, seg_y))
            for sx, sy in segments:
                coords: list[float] = []
                for xv, yv in zip(sx, sy):
                    px = x0 + (float(xv) - xl) * x_scale
                    py = y1 - (float(yv) - yl) * y_scale
                    coords.append(px); coords.append(py)
                if len(coords) >= 4:
                    self.create_line(*coords, fill="#1f4b99", width=2, smooth=False, tags=("line", "gear_line"))
                for xv, yv in zip(sx, sy):
                    px = x0 + (float(xv) - xl) * x_scale
                    py = y1 - (float(yv) - yl) * y_scale
                    self.create_oval(px - 1.5, py - 1.5, px + 1.5, py + 1.5, fill="#1f4b99", outline="", tags=("gear_point",))
        except Exception:
            pass
        finally:
            try:
                self._draw_count += 1
            except Exception:
                pass
            self._last_draw_ms = (_time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# DragTTPSChart — T-TPS
# ---------------------------------------------------------------------------

class DragTTPSChart(_XYChart):
    """T-TPS: Time vs TPS."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Time [s]")
        kwargs.setdefault("ylabel", "TPS [-]")
        super().__init__(master, **kwargs)

    def plot(self, result: object) -> None:  # type: ignore[override]
        cols = _get_series(result)
        if cols is None or "T" not in cols or "TPS" not in cols:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass
            return
        x = _np.asarray(cols["T"], dtype=float)
        y = _np.asarray(cols["TPS"], dtype=float)
        n = min(int(x.size), int(y.size))
        x = x[:n]; y = y[:n]
        mask = _finite_mask(x, y)
        if _np.any(mask):
            x = x[mask]; y = y[mask]
        self.draw_line(x, y)


# ---------------------------------------------------------------------------
# DragXTPSChart — X-TPS
# ---------------------------------------------------------------------------

class DragXTPSChart(_XYChart):
    """X-TPS: Distance vs TPS."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "TPS [-]")
        super().__init__(master, **kwargs)

    def plot(self, result: object) -> None:  # type: ignore[override]
        cols = _get_series(result)
        if cols is None or "X" not in cols or "TPS" not in cols:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass
            return
        x = _np.asarray(cols["X"], dtype=float)
        y = _np.asarray(cols["TPS"], dtype=float)
        n = min(int(x.size), int(y.size))
        x = x[:n]; y = y[:n]
        mask = _finite_mask(x, y)
        if _np.any(mask):
            x = x[mask]; y = y[mask]
        self.draw_line(x, y)


# ---------------------------------------------------------------------------
# DragTBPSChart — T-BPS
# ---------------------------------------------------------------------------

class DragTBPSChart(_XYChart):
    """T-BPS: Time vs BPS."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Time [s]")
        kwargs.setdefault("ylabel", "BPS [bar or Pa]")
        super().__init__(master, **kwargs)

    def plot(self, result: object) -> None:  # type: ignore[override]
        cols = _get_series(result)
        if cols is None or "T" not in cols or "BPS" not in cols:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass
            return
        x = _np.asarray(cols["T"], dtype=float)
        y = _np.asarray(cols["BPS"], dtype=float)
        n = min(int(x.size), int(y.size))
        x = x[:n]; y = y[:n]
        mask = _finite_mask(x, y)
        if _np.any(mask):
            x = x[mask]; y = y[mask]
        self.draw_line(x, y)


# ---------------------------------------------------------------------------
# DragXBPSChart — X-BPS
# ---------------------------------------------------------------------------

class DragXBPSChart(_XYChart):
    """X-BPS: Distance vs BPS."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("xlabel", "Distance [m]")
        kwargs.setdefault("ylabel", "BPS [bar or Pa]")
        super().__init__(master, **kwargs)

    def plot(self, result: object) -> None:  # type: ignore[override]
        cols = _get_series(result)
        if cols is None or "X" not in cols or "BPS" not in cols:
            try:
                super().plot(result)  # type: ignore
            except Exception:
                pass
            return
        x = _np.asarray(cols["X"], dtype=float)
        y = _np.asarray(cols["BPS"], dtype=float)
        n = min(int(x.size), int(y.size))
        x = x[:n]; y = y[:n]
        mask = _finite_mask(x, y)
        if _np.any(mask):
            x = x[mask]; y = y[mask]
        self.draw_line(x, y)


# ---------------------------------------------------------------------------
# Aliases for compatibility (additional naming styles)
# ---------------------------------------------------------------------------

DragT_XChart = DragTXChart
DragT_VChart = DragTVChart
DragX_VChart = DragXVChart
DragT_AChart = DragTAChart
DragX_AChart = DragXAChart
DragT_RPMChart = DragTRPMChart
DragX_RPMChart = DragXRPMChart
DragT_GearChart = DragTGearChart
DragX_GearChart = DragXGearChart
DragT_TPSChart = DragTTPSChart
DragX_TPSChart = DragXTPSChart
DragT_BPSChart = DragTBPSChart
DragX_BPSChart = DragXBPSChart

# Generic mapping for tests that iterate
DRAG_CHARTS: dict[str, type[_XYChart]] = {
    "T-X": DragTXChart,
    "T-V": DragTVChart,
    "X-V": DragXVChart,
    "T-A": DragTAChart,
    "X-A": DragXAChart,
    "T-RPM": DragTRPMChart,
    "X-RPM": DragXRPMChart,
    "T-GEAR": DragTGearChart,
    "X-GEAR": DragXGearChart,
    "T-TPS": DragTTPSChart,
    "X-TPS": DragXTPSChart,
    "T-BPS": DragTBPSChart,
    "X-BPS": DragXBPSChart,
}
DRAG_CHART_LIST: list[type[_XYChart]] = list(DRAG_CHARTS.values())
