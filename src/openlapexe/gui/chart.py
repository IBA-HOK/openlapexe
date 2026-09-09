# -*- coding: utf-8 -*-
# allow: SIZE_OK — Chart Canvas自前3種 単一責務 (ttk GUI) SpeedChart/GG/Sector棒 軸・目盛・グリッド 800点間引き<100ms <Configure>再描画 mpl/sci-py禁止
"""openlapexe.gui.chart - Canvas自前チャート群 (mpl/sci-py禁止).

要件:
- SpeedChart: Speed vs Distance (s_m, v_ms) 軸・目盛・グリッド, 800点間引き, <Configure>再描画
- GGChart: GG diagram (ax vs ay) 軸・目盛・グリッド
- SectorChart: Sector bar chart (sector times) 軸・目盛・グリッド
- 全Canvas: bg white, 薄灰grid(dash), 黒軸, tick labels, axis labels
- <Configure>で再描画, thinning sliceで<=800点, <100ms
- mpl/sci-py import禁止
- encode utf-8想定, messagebox parentは呼び出し側で担保
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

import numpy as _np

try:
    from openlapexe.gui.chart_base import _draw_legend_box as _legend_box, _format_eng as _fEng, _nice_ticks as _nTicks
except Exception:
    _legend_box = None  # type: ignore
    _fEng = lambda v: f"{float(v):.1f}"  # type: ignore
    _nTicks = None  # type: ignore

__all__ = ["SpeedChart", "GGChart", "SectorChart", "GGDiagram", "SectorBar", "SectorBarChart"]


def _probe_bind(canvas: tk.Canvas, store: dict) -> None:
    try:
        store["_press"] = None

        def _on_press(ev: object) -> None:
            try:
                store["_press"] = (int(getattr(ev, "x", 0)), int(getattr(ev, "y", 0)))
            except Exception:
                store["_press"] = None

        def _on_release(ev: object) -> None:
            try:
                px = int(getattr(ev, "x", 0))
                py = int(getattr(ev, "y", 0))
                pr = store.get("_press")
                if pr is not None and (px - pr[0]) ** 2 + (py - pr[1]) ** 2 > 25:
                    return
                _probe_show(canvas, store, float(px), float(py))
            except Exception:
                pass

        canvas.bind("<ButtonPress-1>", _on_press, add="+")
        canvas.bind("<ButtonRelease-1>", _on_release, add="+")
        canvas.bind("<Escape>", lambda _e: _probe_clear(canvas, store), add="+")
    except Exception:
        pass


def _probe_clear(canvas: tk.Canvas, store: dict) -> None:
    try:
        canvas.delete("probe")
    except Exception:
        pass
    try:
        store["_text"] = ""
    except Exception:
        pass


def _probe_show(canvas: tk.Canvas, store: dict, px: float, py: float) -> None:
    try:
        canvas.delete("probe")
    except Exception:
        pass
    try:
        view = store.get("_view")
        xa = store.get("_x")
        ya = store.get("_y")
        xl_lab = str(store.get("xlabel", "x"))
        yl_lab = str(store.get("ylabel", "y"))
        extra = store.get("extra")
        if view is None or xa is None or ya is None:
            return
        xl, xh, yl, yh, x0, y0, x1, y1 = view
        import numpy as _npp

        fx = (float(px) - x0) / (x1 - x0 + 1e-12)
        fy = (float(y1) - float(py)) / (y1 - y0 + 1e-12)
        dx = xl + fx * (xh - xl)
        dy = yl + fy * (yh - yl)
        xs = _npp.asarray(xa, dtype=float)
        ys = _npp.asarray(ya, dtype=float)
        n = min(int(xs.size), int(ys.size))
        if n == 0:
            return
        xs = xs[:n]
        ys = ys[:n]
        try:
            mx = x0 + (xs - xl) / (xh - xl + 1e-12) * (x1 - x0)
            my = y1 - (ys - yl) / (yh - yl + 1e-12) * (y1 - y0)
            cx = x0 + (dx - xl) / (xh - xl + 1e-12) * (x1 - x0)
            cy = y1 - (dy - yl) / (yh - yl + 1e-12) * (y1 - y0)
            idx = int(_npp.argmin((mx - cx) ** 2 + (my - cy) ** 2))
        except Exception:
            idx = 0
        lines = [f"#{idx} {xl_lab}={_fEng(float(xs[idx]))} {yl_lab}={_fEng(float(ys[idx]))}"]
        if callable(extra):
            try:
                ex = extra(idx)
                if ex:
                    lines.append(str(ex))
            except Exception:
                pass
        try:
            w = int(canvas.winfo_width())
            h = int(canvas.winfo_height())
        except Exception:
            w, h = 600, 400
        canvas.create_line(x0, float(py), x1, float(py), fill="#888", dash=(3, 3), tags=("probe",))
        canvas.create_line(float(px), y0, float(px), y1, fill="#888", dash=(3, 3), tags=("probe",))
        try:
            canvas.create_oval(mx[idx] - 4, my[idx] - 4, mx[idx] + 4, my[idx] + 4, outline="#d00", width=2, tags=("probe",))
        except Exception:
            pass
        fw = max(len(s) for s in lines) * 6.5 + 12
        fh = len(lines) * 13 + 10
        bx = min(max(float(px) + 12, 4.0), max(4.0, float(w) - fw - 4))
        by = min(max(float(py) - fh - 8, 4.0), max(4.0, float(h) - fh - 4))
        canvas.create_rectangle(bx, by, bx + fw, by + fh, fill="white", outline="#222", width=1, tags=("probe",))
        for i, s in enumerate(lines):
            canvas.create_text(bx + 6, by + 6 + i * 13, text=s, fill="#111", font=("TkDefaultFont", 7), anchor="nw", tags=("probe",))
        store["_text"] = " | ".join(lines)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _thin_arrays(a: _np.ndarray, b: _np.ndarray, limit: int = 800) -> tuple[_np.ndarray, _np.ndarray]:
    n = int(a.shape[0])
    if n <= limit:
        return a, b
    step = (n + limit - 1) // limit
    return a[::step], b[::step]

def _thin_triple(a: _np.ndarray, b: _np.ndarray, c: _np.ndarray, limit: int = 800) -> tuple[_np.ndarray, _np.ndarray, _np.ndarray]:
    n = int(a.shape[0])
    if n <= limit:
        return a, b, c
    step = (n + limit - 1) // limit
    return a[::step], b[::step], c[::step]


# ---------------------------------------------------------------------------
# SpeedChart
# ---------------------------------------------------------------------------
class SpeedChart(tk.Canvas):
    """速度vs距離チャート (axis + grid + ticks, autoscale, <Configure> redraw)."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("bg", "white")
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("highlightbackground", "#ccc")
        kwargs.setdefault("height", 240)
        super().__init__(master, **kwargs)  # type: ignore[arg-type]
        self._s_data: _np.ndarray | None = None
        self._v_data: _np.ndarray | None = None
        self._result: object | None = None
        self.s_data: _np.ndarray | None = None  # alias for test introspection
        self.v_data: _np.ndarray | None = None
        self._last_draw_ms: float = 0.0
        self._draw_count: int = 0
        self._probe: dict = {"xlabel": "Distance [m]", "ylabel": "Speed [m/s]"}
        self._probe_text: str = ""
        try:
            _probe_bind(self, self._probe)
        except Exception:
            pass
        self.bind("<Configure>", lambda _e: self._redraw())

    def set_data(self, s, v) -> None:  # type: ignore[no-untyped-def]
        try:
            self._s_data = _np.asarray(s, dtype=float)
            self._v_data = _np.asarray(v, dtype=float)
            self.s_data = self._s_data
            self.v_data = self._v_data
        except Exception:
            self._s_data = s  # type: ignore
            self._v_data = v  # type: ignore
        self._redraw()

    def plot(self, result) -> None:  # type: ignore[no-untyped-def]
        try:
            s = getattr(result, "s", None)
            v = getattr(result, "v", None)
            if s is not None and v is not None:
                self.set_data(s, v)
                self._result = result
                return
        except Exception:
            pass
        try:
            if isinstance(result, (list, tuple)) and len(result) >= 2:  # type: ignore
                self.set_data(result[0], result[1])  # type: ignore
        except Exception:
            pass

    def update_chart(self, s, v) -> None:  # type: ignore[no-untyped-def]
        self.set_data(s, v)

    def set_result(self, result) -> None:  # alias
        self.plot(result)

    def _redraw(self) -> None:
        t0 = time.perf_counter()
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
            if self._s_data is not None and self._v_data is not None:
                s_arr0 = _np.asarray(self._s_data, dtype=float)
                v_arr0 = _np.asarray(self._v_data, dtype=float)
                if s_arr0.size > 1 and v_arr0.size > 1:
                    has_data = True
        except Exception:
            has_data = False
        if not has_data:
            try:
                self.create_line(pad_left, h - pad_bottom, w - pad_right, h - pad_bottom, fill="#333", width=1, tags=("axis",))
                self.create_line(pad_left, pad_top, pad_left, h - pad_bottom, fill="#333", width=1, tags=("axis",))
                self.create_text(w // 2, h // 2, text="No data - Run simulation", fill="#888", tags=("placeholder",))
                for i in range(5):
                    x = pad_left + (w - pad_left - pad_right) * i / 4
                    self.create_line(x, h - pad_bottom, x, h - pad_bottom + 3, fill="#333", tags=("tick",))
                    y = h - pad_bottom - (h - pad_top - pad_bottom) * i / 4
                    self.create_line(pad_left - 3, y, pad_left, y, fill="#333", tags=("tick",))
                # grid faint
                for i in range(6):
                    x = pad_left + (w - pad_left - pad_right) * i / 5
                    self.create_line(x, pad_top, x, h - pad_bottom, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
                    y = pad_top + (h - pad_top - pad_bottom) * i / 5
                    self.create_line(pad_left, y, w - pad_right, y, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            except Exception:
                pass
            self._last_draw_ms = (time.perf_counter() - t0) * 1000
            return
        try:
            s_arr = _np.asarray(self._s_data, dtype=float)
            v_arr = _np.asarray(self._v_data, dtype=float)
            mask = _np.isfinite(s_arr) & _np.isfinite(v_arr)
            if _np.any(mask):
                s_arr = s_arr[mask]
                v_arr = v_arr[mask]
            if s_arr.size == 0:
                return
            # thin to <=800
            if s_arr.size > 800:
                s_arr, v_arr = _thin_arrays(s_arr, v_arr, 800)
            s_min = float(_np.min(s_arr))
            s_max = float(_np.max(s_arr))
            v_min = float(_np.min(v_arr))
            v_max = float(_np.max(v_arr))
            if s_max - s_min < 1e-9:
                s_max = s_min + 1.0
            if v_max - v_min < 1e-9:
                v_max = v_min + 10.0
            v_range = v_max - v_min
            v_max = v_max + v_range * 0.05
            if v_min > 0:
                v_min = max(0.0, v_min - v_range * 0.05)
            else:
                v_min = v_min - v_range * 0.05
            plot_w = float(w - pad_left - pad_right)
            plot_h = float(h - pad_top - pad_bottom)
            if plot_w < 1:
                plot_w = 1
            if plot_h < 1:
                plot_h = 1
            x_scale = plot_w / (s_max - s_min)
            y_scale = plot_h / (v_max - v_min)
            try:
                self._probe["_view"] = (float(s_min), float(s_max), float(v_min), float(v_max), float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom))
                self._probe["_x"] = s_arr
                self._probe["_y"] = v_arr
            except Exception:
                pass
            try:
                _xt = _nTicks(float(s_min), float(s_max), 6) if _nTicks is not None else _np.linspace(s_min, s_max, 6)
                _yt = _nTicks(float(v_min), float(v_max), 6) if _nTicks is not None else _np.linspace(v_min, v_max, 6)
            except Exception:
                _xt = _np.linspace(s_min, s_max, 6)
                _yt = _np.linspace(v_min, v_max, 6)
            for xv in _xt:
                try:
                    px = pad_left + (float(xv) - s_min) * x_scale
                except Exception:
                    continue
                if px < pad_left - 1 or px > w - pad_right + 1:
                    continue
                self.create_line(px, pad_top, px, h - pad_bottom, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            for yv in _yt:
                try:
                    py = h - pad_bottom - (float(yv) - v_min) * y_scale
                except Exception:
                    continue
                if py < pad_top - 1 or py > h - pad_bottom + 1:
                    continue
                self.create_line(pad_left, py, w - pad_right, py, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            self.create_line(pad_left, h - pad_bottom, w - pad_right, h - pad_bottom, fill="#333", width=1, tags=("axis",))
            self.create_line(pad_left, pad_top, pad_left, h - pad_bottom, fill="#333", width=1, tags=("axis",))
            for xv in _xt:
                try:
                    px = pad_left + (float(xv) - s_min) * x_scale
                except Exception:
                    continue
                if px < pad_left - 1 or px > w - pad_right + 1:
                    continue
                self.create_line(px, h - pad_bottom, px, h - pad_bottom + 4, fill="#333", tags=("tick",))
                self.create_text(px, h - pad_bottom + 10, text=_fEng(float(xv)), fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
            for yv in _yt:
                try:
                    py = h - pad_bottom - (float(yv) - v_min) * y_scale
                except Exception:
                    continue
                if py < pad_top - 1 or py > h - pad_bottom + 1:
                    continue
                self.create_line(pad_left - 4, py, pad_left, py, fill="#333", tags=("tick",))
                self.create_text(pad_left - 6, py, text=_fEng(float(yv)), fill="#333", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            # axis titles
            self.create_text(w // 2, h - 6, text="Distance [m]", fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
            self.create_text(8, h // 2, text="Speed [m/s]", fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
            coords: list[float] = []
            for sx, vy in zip(s_arr, v_arr):
                px = pad_left + (float(sx) - s_min) * x_scale
                py = h - pad_bottom - (float(vy) - v_min) * y_scale
                coords.append(px)
                coords.append(py)
            if len(coords) >= 4:
                self.create_line(*coords, fill="#1f4b99", width=2, smooth=False, tags=("speedline",))
            try:
                if _legend_box is not None:
                    _legend_box(self, [("#1f4b99", f"v [m/s] n={int(s_arr.size)} max={_fEng(float(_np.max(v_arr)))}", "line")], float(w - pad_right), float(pad_top))
            except Exception:
                pass
            try:
                self._probe_text = str(self._probe.get("_text", ""))
            except Exception:
                pass
        except Exception:
            pass
        finally:
            self._draw_count += 1
            self._last_draw_ms = (time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# GGChart (GG diagram ax vs ay)
# ---------------------------------------------------------------------------
class GGChart(tk.Canvas):
    """GG diagram (ax横, ay縦) 軸・目盛・グリッド, 800点間引き, <Configure>再描画."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("bg", "white")
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("highlightbackground", "#ccc")
        kwargs.setdefault("height", 240)
        kwargs.setdefault("width", 240)
        super().__init__(master, **kwargs)  # type: ignore[arg-type]
        self._ax_data: _np.ndarray | None = None
        self._ay_data: _np.ndarray | None = None
        self._last_draw_ms: float = 0.0
        self.ax_data: _np.ndarray | None = None
        self.ay_data: _np.ndarray | None = None
        self._probe: dict = {"xlabel": "ax [m/s²]", "ylabel": "ay [m/s²]"}
        self._probe_text: str = ""
        try:
            _probe_bind(self, self._probe)
        except Exception:
            pass
        self.bind("<Configure>", lambda _e: self._redraw())

    def set_data(self, ax, ay) -> None:  # type: ignore[no-untyped-def]
        try:
            self._ax_data = _np.asarray(ax, dtype=float)
            self._ay_data = _np.asarray(ay, dtype=float)
            self.ax_data = self._ax_data
            self.ay_data = self._ay_data
        except Exception:
            self._ax_data = ax  # type: ignore
            self._ay_data = ay  # type: ignore
        self._redraw()

    def plot(self, result) -> None:  # type: ignore[no-untyped-def]
        try:
            ax = getattr(result, "ax", None)
            ay = getattr(result, "ay", None)
            if ax is not None and ay is not None:
                self.set_data(ax, ay)
                return
        except Exception:
            pass
        try:
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                self.set_data(result[0], result[1])  # type: ignore
        except Exception:
            pass

    def update_chart(self, ax, ay) -> None:  # type: ignore[no-untyped-def]
        self.set_data(ax, ay)

    def _redraw(self) -> None:
        t0 = time.perf_counter()
        try:
            self.delete("all")
        except Exception:
            return
        try:
            w = int(self.winfo_width())
            h = int(self.winfo_height())
        except Exception:
            w = 240
            h = 240
        if w < 10:
            w = 240
        if h < 10:
            h = 240
        pad = 36
        # inner plot area
        plot_w = float(w - 2 * pad)
        plot_h = float(h - 2 * pad)
        if plot_w < 10:
            plot_w = 10
        if plot_h < 10:
            plot_h = 10
        # no data -> placeholder axes + grid
        has_data = False
        try:
            if self._ax_data is not None and self._ay_data is not None:
                ax0 = _np.asarray(self._ax_data, dtype=float)
                ay0 = _np.asarray(self._ay_data, dtype=float)
                if ax0.size > 1 and ay0.size > 1:
                    has_data = True
        except Exception:
            has_data = False
        if not has_data:
            try:
                # border
                self.create_rectangle(pad, pad, w - pad, h - pad, outline="#333", width=1, tags=("axis",))
                # grid
                for i in range(1, 5):
                    x = pad + plot_w * i / 5
                    self.create_line(x, pad, x, h - pad, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
                    y = pad + plot_h * i / 5
                    self.create_line(pad, y, w - pad, y, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
                # center cross
                cx = pad + plot_w * 0.5
                cy = pad + plot_h * 0.5
                self.create_line(cx, pad, cx, h - pad, fill="#999", dash=(2, 2), tags=("axis",))
                self.create_line(pad, cy, w - pad, cy, fill="#999", dash=(2, 2), tags=("axis",))
                self.create_text(w // 2, h // 2, text="No GG data", fill="#888", tags=("placeholder",))
                # ticks
                for i in range(5):
                    x = pad + plot_w * i / 4
                    self.create_line(x, h - pad, x, h - pad + 4, fill="#333", tags=("tick",))
                    y = pad + plot_h * i / 4
                    self.create_line(pad - 4, y, pad, y, fill="#333", tags=("tick",))
                self.create_text(w // 2, h - 4, text="ax [m/s²]", fill="#333", font=("TkDefaultFont", 7), anchor="s", tags=("axislabel",))
                self.create_text(6, h // 2, text="ay [m/s²]", fill="#333", font=("TkDefaultFont", 7), anchor="w", angle=90, tags=("axislabel",))
            except Exception:
                pass
            self._last_draw_ms = (time.perf_counter() - t0) * 1000
            return
        try:
            ax_arr = _np.asarray(self._ax_data, dtype=float)
            ay_arr = _np.asarray(self._ay_data, dtype=float)
            mask = _np.isfinite(ax_arr) & _np.isfinite(ay_arr)
            if _np.any(mask):
                ax_arr = ax_arr[mask]
                ay_arr = ay_arr[mask]
            if ax_arr.size == 0:
                return
            if ax_arr.size > 800:
                ax_arr, ay_arr = _thin_arrays(ax_arr, ay_arr, 800)
            # symmetric range around 0 for GG: use max absolute
            max_ax = float(_np.max(_np.abs(ax_arr))) if ax_arr.size else 5.0
            max_ay = float(_np.max(_np.abs(ay_arr))) if ay_arr.size else 5.0
            max_abs = max(max_ax, max_ay, 5.0)
            # add 10% margin
            ax_min, ax_max = -max_abs * 1.1, max_abs * 1.1
            ay_min, ay_max = -max_abs * 1.1, max_abs * 1.1
            # scales
            x_scale = plot_w / (ax_max - ax_min) if ax_max != ax_min else 1
            y_scale = plot_h / (ay_max - ay_min) if ay_max != ay_min else 1
            try:
                self._probe["_view"] = (float(ax_min), float(ax_max), float(ay_min), float(ay_max), float(pad), float(pad), float(w - pad), float(h - pad))
                self._probe["_x"] = ax_arr
                self._probe["_y"] = ay_arr
            except Exception:
                pass
            # grid lines (5x5)
            for i in range(6):
                xv = ax_min + (ax_max - ax_min) * i / 5
                px = pad + (xv - ax_min) * x_scale
                self.create_line(px, pad, px, h - pad, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
                yv = ay_min + (ay_max - ay_min) * i / 5
                py = h - pad - (yv - ay_min) * y_scale
                self.create_line(pad, py, w - pad, py, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            # axes border
            self.create_rectangle(pad, pad, w - pad, h - pad, outline="#333", width=1, tags=("axis",))
            # center cross (0,0)
            cx = pad + (0 - ax_min) * x_scale
            cy = h - pad - (0 - ay_min) * y_scale
            self.create_line(cx, pad, cx, h - pad, fill="#999", dash=(2, 2), tags=("axis",))
            self.create_line(pad, cy, w - pad, cy, fill="#999", dash=(2, 2), tags=("axis",))
            # ticks & labels
            for i in range(6):
                xv = ax_min + (ax_max - ax_min) * i / 5
                px = pad + (xv - ax_min) * x_scale
                self.create_line(px, h - pad, px, h - pad + 4, fill="#333", tags=("tick",))
                self.create_text(px, h - pad + 10, text=f"{xv:.0f}", fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
                yv = ay_min + (ay_max - ay_min) * i / 5
                py = h - pad - (yv - ay_min) * y_scale
                self.create_line(pad - 4, py, pad, py, fill="#333", tags=("tick",))
                self.create_text(pad - 6, py, text=f"{yv:.0f}", fill="#333", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            self.create_text(w // 2, h - 4, text="ax [m/s²]", fill="#333", font=("TkDefaultFont", 7), anchor="s", tags=("axislabel",))
            self.create_text(6, h // 2, text="ay [m/s²]", fill="#333", font=("TkDefaultFont", 7), anchor="w", angle=90, tags=("axislabel",))
            try:
                import numpy as _npg
                _mx = float(_npg.max(_npg.abs(ax_arr))) if ax_arr.size else 0.0
                _my = float(_npg.max(_npg.abs(ay_arr))) if ay_arr.size else 0.0
                if _legend_box is not None:
                    _legend_box(self, [("#1f4b99", f"GG n={int(ax_arr.size)} max|a|={_fEng(max(_mx,_my))} m/s²", "marker")], float(w - pad), float(pad))
            except Exception:
                pass
            # draw points as small dots (thin even further for dots? keep <=800 already)
            for xv, yv in zip(ax_arr, ay_arr):
                px = pad + (float(xv) - ax_min) * x_scale
                py = h - pad - (float(yv) - ay_min) * y_scale
                self.create_oval(px - 1.2, py - 1.2, px + 1.2, py + 1.2, fill="#1f4b99", outline="", tags=("ggpoint",))
        except Exception:
            pass
        finally:
            self._last_draw_ms = (time.perf_counter() - t0) * 1000


GGDiagram = GGChart

# ---------------------------------------------------------------------------
# SectorChart (bar chart)
# ---------------------------------------------------------------------------
class SectorChart(tk.Canvas):
    """Sector棒グラフ (sector times) 軸・目盛・グリッド, <Configure>再描画."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("bg", "white")
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("highlightbackground", "#ccc")
        kwargs.setdefault("height", 180)
        super().__init__(master, **kwargs)  # type: ignore[arg-type]
        self._sector_times: _np.ndarray | None = None
        self._sector_labels: list[str] | None = None
        self._last_draw_ms: float = 0.0
        self._probe: dict = {"xlabel": "Sector", "ylabel": "Time [s]"}
        self._probe_text: str = ""
        try:
            _probe_bind(self, self._probe)
        except Exception:
            pass
        self.bind("<Configure>", lambda _e: self._redraw())

    def set_data(self, sector_times, labels: list[str] | None = None) -> None:  # type: ignore[no-untyped-def]
        try:
            if sector_times is None:
                self._sector_times = None
            else:
                self._sector_times = _np.asarray(sector_times, dtype=float)
            self._sector_labels = labels
        except Exception:
            self._sector_times = None
        self._redraw()

    def plot(self, result) -> None:  # type: ignore[no-untyped-def]
        try:
            st = getattr(result, "sector_time", None)
            if st is None:
                st = getattr(result, "sector_times", None)
            if st is not None:
                self.set_data(st)
                return
            # fallback: if result is array
            if isinstance(result, (list, _np.ndarray)):
                self.set_data(result)
                return
        except Exception:
            pass

    def update_chart(self, sector_times, labels: list[str] | None = None) -> None:  # type: ignore[no-untyped-def]
        self.set_data(sector_times, labels)

    def _redraw(self) -> None:
        t0 = time.perf_counter()
        try:
            self.delete("all")
        except Exception:
            return
        try:
            w = int(self.winfo_width())
            h = int(self.winfo_height())
        except Exception:
            w = 400
            h = 180
        if w < 10:
            w = 400
        if h < 10:
            h = 180
        pad_left = 52
        pad_right = 12
        pad_top = 12
        pad_bottom = 36
        has_data = False
        try:
            if self._sector_times is not None:
                arr = _np.asarray(self._sector_times, dtype=float)
                if arr.size > 0 and _np.any(_np.isfinite(arr)):
                    has_data = True
        except Exception:
            has_data = False
        if not has_data:
            try:
                self.create_line(pad_left, h - pad_bottom, w - pad_right, h - pad_bottom, fill="#333", width=1, tags=("axis",))
                self.create_line(pad_left, pad_top, pad_left, h - pad_bottom, fill="#333", width=1, tags=("axis",))
                for i in range(6):
                    x = pad_left + (w - pad_left - pad_right) * i / 5
                    self.create_line(x, pad_top, x, h - pad_bottom, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
                    y = pad_top + (h - pad_top - pad_bottom) * i / 5
                    self.create_line(pad_left, y, w - pad_right, y, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
                self.create_text(w // 2, h // 2, text="No sector data", fill="#888", tags=("placeholder",))
                self.create_text(w // 2, h - 6, text="Sector", fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
                self.create_text(8, h // 2, text="Time [s]", fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
            except Exception:
                pass
            self._last_draw_ms = (time.perf_counter() - t0) * 1000
            return
        try:
            arr = _np.asarray(self._sector_times, dtype=float)
            # filter finite
            arr = arr[_np.isfinite(arr)]
            n = int(arr.size)
            if n == 0:
                return
            # labels
            if self._sector_labels is not None and len(self._sector_labels) == n:
                labels = list(self._sector_labels)
            else:
                labels = [f"S{i+1}" for i in range(n)]
            max_v = float(_np.max(arr)) if n else 1.0
            if max_v < 1e-9:
                max_v = 1.0
            max_v = max_v * 1.15
            min_v = 0.0
            plot_w = float(w - pad_left - pad_right)
            plot_h = float(h - pad_top - pad_bottom)
            y_scale = plot_h / (max_v - min_v) if max_v != min_v else 1
            # grid horizontal
            for i in range(6):
                yv = min_v + (max_v - min_v) * i / 5
                py = h - pad_bottom - (yv - min_v) * y_scale
                self.create_line(pad_left, py, w - pad_right, py, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            # axes
            self.create_line(pad_left, h - pad_bottom, w - pad_right, h - pad_bottom, fill="#333", width=1, tags=("axis",))
            self.create_line(pad_left, pad_top, pad_left, h - pad_bottom, fill="#333", width=1, tags=("axis",))
            # ticks y
            try:
                _sy = _nTicks(float(min_v), float(max_v), 6) if _nTicks is not None else _np.linspace(min_v, max_v, 6)
            except Exception:
                _sy = _np.linspace(min_v, max_v, 6)
            for yv in _sy:
                try:
                    py = h - pad_bottom - (float(yv) - min_v) * y_scale
                except Exception:
                    continue
                if py < pad_top - 1 or py > h - pad_bottom + 1:
                    continue
                self.create_line(pad_left - 4, py, pad_left, py, fill="#333", tags=("tick",))
                self.create_text(pad_left - 6, py, text=_fEng(float(yv)), fill="#333", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            try:
                import numpy as _nps

                self._probe["_view"] = (0.0, float(n), float(min_v), float(max_v), float(pad_left), float(pad_top), float(w - pad_right), float(h - pad_bottom))
                self._probe["_x"] = _nps.arange(1, n + 1, dtype=float)
                self._probe["_y"] = _nps.asarray(arr, dtype=float)
                self._probe["xlabel"] = "Sector No"
                self._probe["ylabel"] = "Time [s]"
            except Exception:
                pass
            # bars
            gap = plot_w * 0.08
            bar_area = plot_w - gap * 2
            if n > 0:
                bar_w = bar_area / n * 0.72
                step = bar_area / n
                colors = ["#1f4b99", "#2e7bb8", "#3aa0d0", "#5ab8e0", "#7acfe8"]
                for idx, val in enumerate(arr):
                    x_center = pad_left + gap + step * idx + step * 0.5
                    x0 = x_center - bar_w * 0.5
                    x1 = x_center + bar_w * 0.5
                    y0 = h - pad_bottom - (float(val) - min_v) * y_scale
                    y1 = h - pad_bottom
                    col = colors[idx % len(colors)]
                    self.create_rectangle(x0, y0, x1, y1, fill=col, outline="#1a3a6b", width=1, tags=("bar",))
                    # tick x label
                    self.create_text(x_center, h - pad_bottom + 8, text=labels[idx], fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
                    # value on top
                    self.create_text(x_center, y0 - 4, text=f"{float(val):.2f}s", fill="#333", font=("TkDefaultFont", 7), anchor="s", tags=("valuelabel",))
                # vertical grid per sector
                for idx in range(n + 1):
                    x = pad_left + gap + step * idx
                    self.create_line(x, pad_top, x, h - pad_bottom, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            self.create_text(w // 2, h - 6, text="Sector", fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
            self.create_text(8, h // 2, text="Time [s]", fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
        except Exception:
            pass
        finally:
            self._last_draw_ms = (time.perf_counter() - t0) * 1000


SectorBar = SectorChart
SectorBarChart = SectorChart
