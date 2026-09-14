# -*- coding: utf-8 -*-
# allow: SIZE_OK — Generic XYChart/TXChart single responsibility: BaseChart拡張 汎用XY xlabel/ylabel/xlim/ylim equal正方 color_by手動グラデーション
"""openlapexe.gui.chart_xy - 汎用XYChart/TXChart (mpl/scipy禁止).

BaseChart 拡張:
- xlabel/ylabel/xlim/ylim 指定
- axis equal フラグ (正方 viewport)
- color_by 速度カラーマップ (手動グラデーション blue->red)
- draw_line/draw_scatter/draw_colored
- ylim -10..110 対応 (tps/bps 用)
- 800点間引き (決定論的 slice)
"""
from __future__ import annotations

import time
import tkinter as tk

import numpy as _np

from openlapexe.gui.chart_base import (
    PAD_BOTTOM,
    PAD_LEFT,
    PAD_RIGHT,
    PAD_TOP,
    BaseChart,
    _axis_limits,
    _draw_axes,
    _draw_colorbar,
    _draw_grid,
    _draw_legend_box,
    _format_eng,
    _nice_ticks,
    _thin,
    _view_rect,
)

__all__ = ["XYChart", "TXChart"]


def _thin_triple(a: _np.ndarray, b: _np.ndarray, c: _np.ndarray, limit: int = 800) -> tuple[_np.ndarray, _np.ndarray, _np.ndarray]:
    try:
        arr_a = _np.asarray(a)
        arr_b = _np.asarray(b)
        arr_c = _np.asarray(c)
        n = int(arr_a.shape[0]) if arr_a.ndim >= 1 else 0
        nb = int(arr_b.shape[0]) if arr_b.ndim >= 1 else n
        nc = int(arr_c.shape[0]) if arr_c.ndim >= 1 else n
        n = min(n, nb, nc)
        arr_a = arr_a[:n]
        arr_b = arr_b[:n]
        arr_c = arr_c[:n]
        lim = int(limit)
        if lim <= 0:
            lim = 800
        if n <= lim:
            return arr_a, arr_b, arr_c
        step = (n + lim - 1) // lim
        if step < 1:
            step = 1
        return arr_a[::step], arr_b[::step], arr_c[::step]
    except Exception:
        return a, b, c  # type: ignore[return-value]


def _color_for_value(v: float, vmin: float, vmax: float) -> str:
    try:
        if not _np.isfinite(v):
            return "#888888"
        if not _np.isfinite(vmin) or not _np.isfinite(vmax):
            return "#1f4b99"
        if vmax - vmin < 1e-9:
            return "#ff0000"
        t = (float(v) - float(vmin)) / (float(vmax) - float(vmin))
        if t < 0:
            t = 0
        if t > 1:
            t = 1
        # manual gradient: blue (0,0,255) -> cyan -> green -> yellow -> red (255,0,0)
        # simplified lerp blue->red via jet-like 4 stops: blue, cyan, yellow, red
        # use piecewise: 0 blue, 0.25 cyan, 0.5 green-yellow, 0.75 orange, 1 red
        # implement smooth blue->red: r = 255*t, g = 0, b = 255*(1-t) for simple, but add green peak
        # use jet approximation: for richer gradient
        if t < 0.25:
            # blue -> cyan
            f = t / 0.25
            r = 0
            g = int(255 * f)
            b = 255
        elif t < 0.5:
            # cyan -> green
            f = (t - 0.25) / 0.25
            r = 0
            g = 255
            b = int(255 * (1 - f))
        elif t < 0.75:
            # green -> yellow
            f = (t - 0.5) / 0.25
            r = int(255 * f)
            g = 255
            b = 0
        else:
            # yellow -> red
            f = (t - 0.75) / 0.25
            r = 255
            g = int(255 * (1 - f))
            b = 0
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#1f4b99"


class XYChart(BaseChart):
    """汎用 XY チャート (BaseChart 拡張).

    - xlabel/ylabel: 軸ラベル
    - xlim/ylim: (lo,hi) 強制範囲 or None で autoscale
    - equal: True で正方 viewport (plot_w == plot_h, 中央寄せ)
    - color_by: 速度等のカラーマップ用配列 (draw_coloredで使用)
    - draw_line/draw_scatter/draw_colored
    """

    def __init__(
        self,
        master: tk.Widget | None = None,
        *,
        xlabel: str = "X",
        ylabel: str = "Y",
        xlim: tuple[float, float] | None = None,
        ylim: tuple[float, float] | None = None,
        equal: bool = False,
        color_by: _np.ndarray | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(master, **kwargs)
        self._xlabel: str = str(xlabel) if xlabel is not None else "X"
        self._ylabel: str = str(ylabel) if ylabel is not None else "Y"
        self._xlim: tuple[float, float] | None = None
        self._ylim: tuple[float, float] | None = None
        if xlim is not None:
            try:
                lo, hi = float(xlim[0]), float(xlim[1])  # type: ignore
                if hi > lo:
                    self._xlim = (lo, hi)
                else:
                    self._xlim = (lo, hi)
            except Exception:
                self._xlim = None
        if ylim is not None:
            try:
                lo, hi = float(ylim[0]), float(ylim[1])  # type: ignore
                if hi > lo:
                    self._ylim = (lo, hi)
                else:
                    self._ylim = (lo, hi)
            except Exception:
                self._ylim = None
        self._equal: bool = bool(equal)
        self._mode: str = "line"
        self._c_data: _np.ndarray | None = None
        if color_by is not None:
            try:
                self._c_data = _np.asarray(color_by, dtype=float)
            except Exception:
                self._c_data = None
        # for test introspection: last computed plot geometry
        self._plot_w: float = 0.0
        self._plot_h: float = 0.0
        self._x0: float = 0.0
        self._y0: float = 0.0
        self._x1: float = 0.0
        self._y1: float = 0.0

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------
    @property
    def xlabel(self) -> str:
        return self._xlabel

    @xlabel.setter
    def xlabel(self, v: str) -> None:
        self._xlabel = str(v)
        self._redraw()

    @property
    def ylabel(self) -> str:
        return self._ylabel

    @ylabel.setter
    def ylabel(self, v: str) -> None:
        self._ylabel = str(v)
        self._redraw()

    @property
    def xlim(self) -> tuple[float, float] | None:
        return self._xlim

    @xlim.setter
    def xlim(self, v: tuple[float, float] | None) -> None:
        if v is None:
            self._xlim = None
        else:
            try:
                self._xlim = (float(v[0]), float(v[1]))  # type: ignore
            except Exception:
                self._xlim = None
        self._redraw()

    @property
    def ylim(self) -> tuple[float, float] | None:
        return self._ylim

    @ylim.setter
    def ylim(self, v: tuple[float, float] | None) -> None:
        if v is None:
            self._ylim = None
        else:
            try:
                self._ylim = (float(v[0]), float(v[1]))  # type: ignore
            except Exception:
                self._ylim = None
        self._redraw()

    @property
    def equal(self) -> bool:
        return self._equal

    @equal.setter
    def equal(self, v: bool) -> None:
        self._equal = bool(v)
        self._redraw()

    @property
    def color_by(self) -> _np.ndarray | None:
        return self._c_data

    @color_by.setter
    def color_by(self, v: object) -> None:
        try:
            if v is None:
                self._c_data = None
            else:
                self._c_data = _np.asarray(v, dtype=float)
        except Exception:
            self._c_data = None
        self._redraw()

    # compat: axis_equal alias
    @property
    def axis_equal(self) -> bool:
        return self._equal

    @axis_equal.setter
    def axis_equal(self, v: bool) -> None:
        self._equal = bool(v)
        self._redraw()

    # ------------------------------------------------------------------
    # data helpers
    # ------------------------------------------------------------------
    def _store_thin(self, x: object, y: object, c: object | None = None) -> None:
        try:
            xa = _np.asarray(x, dtype=float)
            ya = _np.asarray(y, dtype=float)
            # handle length mismatch: trim to min
            try:
                n = int(xa.shape[0]) if xa.ndim >= 1 else 0
                ny = int(ya.shape[0]) if ya.ndim >= 1 else n
                if ny != n:
                    m = min(n, ny)
                    xa = xa[:m]
                    ya = ya[:m]
            except Exception:
                pass
            if c is not None:
                ca = _np.asarray(c, dtype=float)
                try:
                    nc = int(ca.shape[0]) if ca.ndim >= 1 else int(xa.shape[0])
                    n = int(xa.shape[0])
                    if nc != n:
                        m = min(n, nc)
                        xa = xa[:m]
                        ya = ya[:m]
                        ca = ca[:m]
                except Exception:
                    pass
                # thin triple deterministically
                if xa.size > 800:
                    xa, ya, ca = _thin_triple(xa, ya, ca, 800)
                self._x_data = xa
                self._y_data = ya
                self._c_data = ca
                self.x_data = xa
                self.y_data = ya
            else:
                if xa.size > 800:
                    xa, ya = _thin(xa, ya, 800)
                self._x_data = xa
                self._y_data = ya
                self.x_data = xa
                self.y_data = ya
        except Exception:
            # fallback store as-is
            try:
                self._x_data = _np.asarray(x, dtype=float)  # type: ignore
                self._y_data = _np.asarray(y, dtype=float)  # type: ignore
                self.x_data = self._x_data
                self.y_data = self._y_data
                if c is not None:
                    self._c_data = _np.asarray(c, dtype=float)
            except Exception:
                self._x_data = x  # type: ignore
                self._y_data = y  # type: ignore

    def set_data(self, x: object, y: object, c: object | None = None) -> None:  # type: ignore[override]
        if c is not None:
            self._mode = "colored"
        self._store_thin(x, y, c)
        self._redraw()

    def plot(self, result: object) -> None:  # type: ignore[override]
        try:
            x = getattr(result, "x", None)
            y = getattr(result, "y", None)
            if x is None:
                x = getattr(result, "s", None)
            if y is None:
                y = getattr(result, "v", None)
            c = getattr(result, "c", None)
            if c is None:
                c = getattr(result, "color_by", None)
            if x is not None and y is not None:
                self._store_thin(x, y, c)
                self._redraw()
                return
        except Exception:
            pass
        try:
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                cx = result[2] if len(result) >= 3 else None
                self._store_thin(result[0], result[1], cx)
                self._redraw()
        except Exception:
            pass

    def update_chart(self, x: object, y: object, c: object | None = None) -> None:  # type: ignore[override]
        self.set_data(x, y, c)

    # ------------------------------------------------------------------
    # public draw APIs
    # ------------------------------------------------------------------
    def draw_line(self, x: object, y: object) -> None:
        self._mode = "line"
        self._store_thin(x, y, None)
        self._redraw()

    def draw_scatter(self, x: object, y: object) -> None:
        self._mode = "scatter"
        self._store_thin(x, y, None)
        self._redraw()

    def draw_colored(self, x: object, y: object, c: object | None = None, color_by: object | None = None) -> None:
        self._mode = "colored"
        cb = c if c is not None else color_by
        if cb is None:
            cb = self._c_data
        # if still None, fallback to y as color source (speed-like)
        if cb is None:
            try:
                cb = _np.asarray(y, dtype=float)
            except Exception:
                cb = None
        self._store_thin(x, y, cb)
        self._redraw()

    # alias for tps/bps usage: draw with explicit color array
    def draw_with_color(self, x: object, y: object, color_by: object) -> None:
        self.draw_colored(x, y, color_by)

    # ------------------------------------------------------------------
    # redraw
    # ------------------------------------------------------------------
    def _redraw(self) -> None:  # type: ignore[override]
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
            h = 400
        if w < 10:
            w = 600
        if h < 10:
            h = 400
        x0, y0, x1, y1, plot_w, plot_h = _view_rect(w, h, equal=bool(self._equal))
        # store for inspection
        self._plot_w = float(plot_w)
        self._plot_h = float(plot_h)
        self._x0 = float(x0)
        self._y0 = float(y0)
        self._x1 = float(x1)
        self._y1 = float(y1)
        has_data = False
        try:
            if self._x_data is not None and self._y_data is not None:
                xa0 = _np.asarray(self._x_data, dtype=float)
                ya0 = _np.asarray(self._y_data, dtype=float)
                if xa0.size > 1 and ya0.size > 1:
                    has_data = True
        except Exception:
            has_data = False
        if not has_data:
            try:
                _draw_grid(self, x0, y0, x1, y1, 5, 5)
                _draw_axes(self, x0, y0, x1, y1, 5, 5)
                self.create_text(w // 2, h // 2, text="No data", fill="#888", tags=("placeholder",))
                self.create_text(w // 2, h - 6, text=self._xlabel, fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
                self.create_text(8, h // 2, text=self._ylabel, fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
            except Exception:
                pass
            self._last_draw_ms = (time.perf_counter() - t0) * 1000
            return
        try:
            x_arr = _np.asarray(self._x_data, dtype=float)
            y_arr = _np.asarray(self._y_data, dtype=float)
            c_arr: _np.ndarray | None = None
            if self._c_data is not None:
                try:
                    c_arr = _np.asarray(self._c_data, dtype=float)
                    # align lengths
                    n = min(int(x_arr.shape[0]), int(y_arr.shape[0]), int(c_arr.shape[0]))
                    x_arr = x_arr[:n]
                    y_arr = y_arr[:n]
                    c_arr = c_arr[:n]
                except Exception:
                    c_arr = None
            # finite mask
            try:
                mask = _np.isfinite(x_arr) & _np.isfinite(y_arr)
                if c_arr is not None:
                    mask = mask & _np.isfinite(c_arr)
                if _np.any(mask):
                    x_arr = x_arr[mask]
                    y_arr = y_arr[mask]
                    if c_arr is not None:
                        c_arr = c_arr[mask]
            except Exception:
                pass
            if x_arr.size == 0:
                self._last_draw_ms = (time.perf_counter() - t0) * 1000
                return
            # ensure thinned (in case data set without thinning)
            if x_arr.size > 800:
                if c_arr is not None:
                    x_arr, y_arr, c_arr = _thin_triple(x_arr, y_arr, c_arr, 800)
                else:
                    x_arr, y_arr = _thin(x_arr, y_arr, 800)
                # keep stored thinned for inspection
                self._x_data = x_arr
                self._y_data = y_arr
                self.x_data = x_arr
                self.y_data = y_arr
                if c_arr is not None:
                    self._c_data = c_arr
            # axis limits: forced or autoscale
            if self._xlim is not None:
                xl, xh = float(self._xlim[0]), float(self._xlim[1])
            else:
                xl, xh = _axis_limits(x_arr, 0.05)
            if self._ylim is not None:
                yl, yh = float(self._ylim[0]), float(self._ylim[1])
            else:
                yl, yh = _axis_limits(y_arr, 0.05)
            if xh - xl < 1e-9:
                xh = xl + 1.0
            if yh - yl < 1e-9:
                yh = yl + 1.0
            # scales
            x_scale = plot_w / (xh - xl) if (xh - xl) != 0 else 1
            y_scale = plot_h / (yh - yl) if (yh - yl) != 0 else 1
            try:
                self._store_view(xl, xh, yl, yh, float(x0), float(y0), float(x1), float(y1))
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
            # axes
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
            # axis titles (xlabel/ylabel)
            self.create_text((x0 + x1) * 0.5, h - 6, text=self._xlabel, fill="#333", font=("TkDefaultFont", 8), anchor="s", tags=("axislabel",))
            self.create_text(8, (y0 + y1) * 0.5, text=self._ylabel, fill="#333", font=("TkDefaultFont", 8), anchor="w", angle=90, tags=("axislabel",))
            # draw data according to mode
            if self._mode == "scatter":
                for xv, yv in zip(x_arr, y_arr):
                    px = x0 + (float(xv) - xl) * x_scale
                    py = y1 - (float(yv) - yl) * y_scale
                    self.create_oval(px - 2, py - 2, px + 2, py + 2, fill="#1f4b99", outline="", tags=("scatter",))
                try:
                    _items = list(getattr(self, "_series_labels", None) or [])
                    if not _items:
                        _yl = str(getattr(self, "_ylabel", "") or "y")
                        _items = [("#1f4b99", _yl, "marker")]
                    _draw_legend_box(self, _items, float(x1), float(y0))
                except Exception:
                    pass
            elif self._mode == "colored" and c_arr is not None and c_arr.size == x_arr.size:
                try:
                    cmin = float(_np.min(c_arr[_np.isfinite(c_arr)])) if _np.any(_np.isfinite(c_arr)) else 0.0
                    cmax = float(_np.max(c_arr[_np.isfinite(c_arr)])) if _np.any(_np.isfinite(c_arr)) else 1.0
                except Exception:
                    cmin, cmax = 0.0, 1.0
                if cmax - cmin < 1e-9:
                    cmax = cmin + 1.0
                # draw colored points + colored line segments for visibility
                # segments: each adjacent pair colored by average of its endpoints
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
                    self.create_oval(px - 2, py - 2, px + 2, py + 2, fill=col, outline="", tags=("colored_point",))
                try:
                    _ctitle = str(getattr(self, "_c_label", "") or self._ylabel or "value")
                    _draw_colorbar(self, float(x1), float(y0), float(y1), float(w), float(cmin), float(cmax), _ctitle, _format_eng)
                except Exception:
                    pass
            else:
                # default line
                coords: list[float] = []
                for xv, yv in zip(x_arr, y_arr):
                    px = x0 + (float(xv) - xl) * x_scale
                    py = y1 - (float(yv) - yl) * y_scale
                    coords.append(px)
                    coords.append(py)
                if len(coords) >= 4:
                    self.create_line(*coords, fill="#1f4b99", width=2, smooth=False, tags=("line",))
                try:
                    _items = list(getattr(self, "_series_labels", None) or [])
                    if not _items:
                        _yl = str(getattr(self, "_ylabel", "") or "y")
                        _items = [("#1f4b99", _yl, "line")]
                    _draw_legend_box(self, _items, float(x1), float(y0))
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
            self._last_draw_ms = (time.perf_counter() - t0) * 1000


class TXChart(XYChart):
    """Time-X チャート (XYChart のエイリアス, 既定 xlabel=Time [s])."""

    def __init__(
        self,
        master: tk.Widget | None = None,
        *,
        xlabel: str = "Time [s]",
        ylabel: str = "X",
        xlim: tuple[float, float] | None = None,
        ylim: tuple[float, float] | None = None,
        equal: bool = False,
        color_by: _np.ndarray | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(master, xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim, equal=equal, color_by=color_by, **kwargs)
