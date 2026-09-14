# allow: SIZE_OK — Generic Canvas base single responsibility: BaseChart + _thin/_axis_limits/_draw_grid/_draw_axes/_project_wireframe (Canvas自前)
# -*- coding: utf-8 -*-
"""openlapexe.gui.chart_base - 汎用Canvas基盤 (mpl/scipy禁止).

提供:
- _thin(a,b,limit=800) 間引き
- _axis_limits(values, pad=0.05) 軸範囲算出
- _draw_grid(canvas,x0,y0,x1,y1) 破線 #e0e0e0
- _draw_axes(canvas,x0,y0,x1,y1) #333 + 目盛
- _project_wireframe(verts,Rx,Ry) numpy回転行列 + 正射影
- BaseChart(tk.Canvas: bg white, <Configure> -> _redraw, _last_draw_ms計測)

既存 chart.py の流儀に合わせるが流用せず新規。
"""
from __future__ import annotations

import time
import tkinter as tk

import numpy as _np

__all__ = [
    "_thin",
    "_axis_limits",
    "_draw_grid",
    "_draw_axes",
    "_project_wireframe",
    "BaseChart",
    "_nice_ticks",
    "_format_eng",
    "_draw_legend_box",
    "_draw_colorbar",
    "PAD_LEFT",
    "PAD_RIGHT",
    "PAD_TOP",
    "PAD_BOTTOM",
    "_view_rect",
]

PAD_LEFT: float = 52.0  # pad_left single source
PAD_RIGHT: float = 12.0
PAD_TOP: float = 12.0
PAD_BOTTOM: float = 30.0


def _view_rect(w: int, h: int, *, equal: bool = True) -> tuple[float, float, float, float, float, float]:
    try:
        ww = int(w)
        hh = int(h)
    except Exception:
        ww, hh = 600, 400
    if ww < 10:
        ww = 600
    if hh < 10:
        hh = 400
    pl = float(PAD_LEFT)
    pr = float(PAD_RIGHT)
    pt = float(PAD_TOP)
    pb = float(PAD_BOTTOM)
    raw_w = float(ww - pl - pr)
    raw_h = float(hh - pt - pb)
    if raw_w < 1:
        raw_w = 1
    if raw_h < 1:
        raw_h = 1
    if equal:
        size = raw_w if raw_w < raw_h else raw_h
        ew = raw_w - size
        eh = raw_h - size
        x0 = pl + ew * 0.5
        x1 = float(ww - pr - ew * 0.5)
        y0 = pt + eh * 0.5
        y1 = float(hh - pb - eh * 0.5)
        return (x0, y0, x1, y1, size, size)
    return (pl, pt, float(ww - pr), float(hh - pb), raw_w, raw_h)

# ---------------------------------------------------------------------------
# _thin
# ---------------------------------------------------------------------------

def _thin(a: _np.ndarray, b: _np.ndarray, limit: int = 800) -> tuple[_np.ndarray, _np.ndarray]:
    """2配列を limit 以下へスライス間引き (決定論的)."""
    try:
        arr_a = _np.asarray(a)
        arr_b = _np.asarray(b)
        n = int(arr_a.shape[0]) if arr_a.ndim >= 1 else 0
        # b の長さが異なる場合は短い方に合わせる (通常は同長)
        try:
            nb = int(arr_b.shape[0]) if arr_b.ndim >= 1 else n
            if nb != n:
                n = min(n, nb)
                arr_a = arr_a[:n]
                arr_b = arr_b[:n]
        except Exception:
            pass
        lim = int(limit)
        if lim <= 0:
            lim = 800
        if n <= lim:
            return arr_a, arr_b
        step = (n + lim - 1) // lim
        if step < 1:
            step = 1
        return arr_a[::step], arr_b[::step]
    except Exception:
        # fallback: return as-is
        return a, b  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# _axis_limits
# ---------------------------------------------------------------------------

def _axis_limits(a: object, pad: object = 0.05, *rest: object) -> tuple[float, float]:
    """軸範囲を算出. 1配列 or 2配列 or (lo,hi) に対応する寛容実装."""
    # two-array case: _axis_limits(arr1, arr2)
    if isinstance(pad, (_np.ndarray, list, tuple)):
        # pad が配列なら 2配列を連結
        # ただし tuple/list が小さくスカラー 2要素の可能性もあるが、ここでは配列扱い
        try:
            # 判定: pad が ndarray もしくは長さ >2 の list/tuple なら配列
            is_array = isinstance(pad, _np.ndarray)
            if not is_array:
                # list/tuple length check
                if isinstance(pad, (list, tuple)) and len(pad) > 2:
                    is_array = True
                elif isinstance(pad, (list, tuple)) and len(pad) >= 2:
                    # 要素が数値かつ配列長がデータ長っぽいなら配列とみなす
                    # ここでは ndarray のみを配列連結対象に限定し、他は pad として扱わない
                    is_array = False
            if is_array:
                arr1 = _np.asarray(a, dtype=float).ravel()
                arr2 = _np.asarray(pad, dtype=float).ravel()
                if rest:
                    # 追加の配列があれば連結
                    extras = []
                    for r in rest:
                        try:
                            extras.append(_np.asarray(r, dtype=float).ravel())
                        except Exception:
                            pass
                    if extras:
                        arr = _np.concatenate([arr1, arr2] + extras)
                    else:
                        arr = _np.concatenate([arr1, arr2])
                else:
                    arr = _np.concatenate([arr1, arr2])
                pad_val = 0.05
                # 以下で arr を処理
                finite = arr[_np.isfinite(arr)] if arr.size else arr
                if finite.size == 0:
                    return (0.0, 1.0)
                lo = float(_np.min(finite))
                hi = float(_np.max(finite))
                if hi - lo < 1e-9:
                    # 退避: 点が1つまたは同値
                    if abs(lo) < 1e-9:
                        return (lo, lo + 1.0)
                    # 5%でもゼロ幅なら 1.0 拡張
                    return (lo, lo + max(1.0, abs(lo) * 0.1))
                rng = hi - lo
                return (lo - rng * pad_val, hi + rng * pad_val)
        except Exception:
            pass
        # fallback to single-array handling below if not matched
    # single array case
    try:
        # pad が数値か判定
        pad_val = 0.05
        if isinstance(pad, (int, float, _np.floating, _np.integer)):
            pad_val = float(pad)  # type: ignore
        elif isinstance(pad, str):
            try:
                pad_val = float(pad)
            except Exception:
                pad_val = 0.05
        # a を配列として解釈
        arr = _np.asarray(a, dtype=float).ravel()
        # もし rest に pad が来ている場合の対応 (呼び出しが _axis_limits(lo,hi) のような場合ではなく配列)
        # rest が1つのスカラーなら pad として扱う
        if rest and len(rest) == 1 and isinstance(rest[0], (int, float, _np.floating)):
            try:
                pad_val = float(rest[0])  # type: ignore
            except Exception:
                pass
        finite = arr[_np.isfinite(arr)] if arr.size else arr
        if finite.size == 0:
            return (0.0, 1.0)
        lo = float(_np.min(finite))
        hi = float(_np.max(finite))
        if hi - lo < 1e-9:
            if abs(lo) < 1e-9:
                return (lo, lo + 1.0)
            return (lo, lo + max(1.0, abs(lo) * 0.1))
        rng = hi - lo
        # pad_val が0-1の範囲外でもクランプせずそのまま
        return (lo - rng * pad_val, hi + rng * pad_val)
    except Exception:
        return (0.0, 1.0)


# ---------------------------------------------------------------------------
# _draw_grid / _draw_axes (module-level helpers)
# ---------------------------------------------------------------------------

def _draw_grid(canvas: tk.Canvas, x0: float, y0: float, x1: float, y1: float, nx: int = 5, ny: int = 5) -> None:
    """破線 #e0e0e0 グリッドを描画."""
    try:
        nx_i = int(nx)
        ny_i = int(ny)
        if nx_i < 1:
            nx_i = 1
        if ny_i < 1:
            ny_i = 1
        for i in range(nx_i + 1):
            x = float(x0) + (float(x1) - float(x0)) * i / nx_i
            canvas.create_line(x, float(y0), x, float(y1), fill="#e0e0e0", dash=(2, 2), tags=("grid",))
        for i in range(ny_i + 1):
            y = float(y0) + (float(y1) - float(y0)) * i / ny_i
            canvas.create_line(float(x0), y, float(x1), y, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
    except Exception:
        pass


def _draw_axes(
    canvas: tk.Canvas,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    nx: int = 5,
    ny: int = 5,
    *,
    tick_len: float = 4.0,
) -> None:
    """#333 軸 + 目盛を描画."""
    try:
        nx_i = int(nx)
        ny_i = int(ny)
        if nx_i < 1:
            nx_i = 1
        if ny_i < 1:
            ny_i = 1
        # 軸線
        canvas.create_line(float(x0), float(y1), float(x1), float(y1), fill="#333", width=1, tags=("axis",))
        canvas.create_line(float(x0), float(y0), float(x0), float(y1), fill="#333", width=1, tags=("axis",))
        # 目盛 (tick)
        for i in range(nx_i + 1):
            x = float(x0) + (float(x1) - float(x0)) * i / nx_i
            canvas.create_line(x, float(y1), x, float(y1) + float(tick_len), fill="#333", tags=("tick",))
        for i in range(ny_i + 1):
            y = float(y0) + (float(y1) - float(y0)) * i / ny_i
            canvas.create_line(float(x0) - float(tick_len), y, float(x0), y, fill="#333", tags=("tick",))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Engineering ticks / formatting / legend / colorbar (readout-ready)
# ---------------------------------------------------------------------------

def _nice_ticks(lo: float, hi: float, n: int = 6) -> "_np.ndarray":
    try:
        import math as _math

        lo_f = float(lo)
        hi_f = float(hi)
        if not (_np.isfinite(lo_f) and _np.isfinite(hi_f)):
            return _np.linspace(0.0, 1.0, int(n))
        if hi_f < lo_f:
            lo_f, hi_f = hi_f, lo_f
        if abs(hi_f - lo_f) < 1e-12:
            lo_f -= 0.5
            hi_f += 0.5
        span = hi_f - lo_f
        raw_step = span / max(1, int(n) - 1)
        mag = 10.0 ** _math.floor(_math.log10(raw_step)) if raw_step > 0 else 1.0
        norm = raw_step / mag if mag else raw_step
        if norm >= 7.5:
            step = 10.0 * mag
        elif norm >= 3.5:
            step = 5.0 * mag
        elif norm >= 1.5:
            step = 2.0 * mag
        else:
            step = 1.0 * mag
        t0 = _math.ceil(lo_f / step) * step
        ticks: list[float] = []
        v = t0
        for _ in range(int(n) + 8):
            if v > hi_f + step * 0.5:
                break
            # round to avoid 0.30000000004
            ticks.append(float(v))
            v += step
        if len(ticks) < 2:
            return _np.array([lo_f, hi_f], dtype=float)
        return _np.array(ticks, dtype=float)
    except Exception:
        try:
            return _np.linspace(float(lo), float(hi), int(n))
        except Exception:
            return _np.zeros(0, dtype=float)


def _format_eng(v: float) -> str:
    try:
        import math as _math

        f = float(v)
        if not _math.isfinite(f):
            return "--"
        if f == 0.0:
            return "0"
        a = abs(f)
        if a >= 10000.0 or (a < 0.001 and a > 0.0):
            return f"{f:.2e}"
        if a >= 100.0:
            return f"{f:.1f}"
        if a >= 10.0:
            return f"{f:.2f}"
        if a >= 1.0:
            return f"{f:.3f}"
        return f"{f:.4f}"
    except Exception:
        try:
            return str(v)
        except Exception:
            return "--"


def _draw_legend_box(canvas: tk.Canvas, items: list[tuple[str, str, str]], x1: float, y0: float) -> None:
    try:
        if not items:
            return
        n = len(items)
        box_w = 150.0
        box_h = float(10 + n * 14)
        bx0 = float(x1) - box_w - 4.0
        by0 = float(y0) + 4.0
        canvas.create_rectangle(bx0, by0, bx0 + box_w, by0 + box_h, fill="white", outline="#333", width=1, tags=("legend",))
        for i, (color, label, kind) in enumerate(items):
            cy = by0 + 12 + i * 14
            lx0 = bx0 + 6
            lx1 = bx0 + 26
            if kind == "marker":
                canvas.create_oval(lx0 + 6, cy - 3, lx0 + 12, cy + 3, fill=color, outline=color, tags=("legend",))
            elif kind == "dash":
                canvas.create_line(lx0, cy, lx1, cy, fill=color, width=2, dash=(3, 2), tags=("legend",))
            else:
                canvas.create_line(lx0, cy, lx1, cy, fill=color, width=2, tags=("legend",))
            try:
                txt = str(label)[:28]
            except Exception:
                txt = "?"
            canvas.create_text(lx1 + 4, cy, text=txt, fill="#222", font=("TkDefaultFont", 7), anchor="w", tags=("legend",))
    except Exception:
        pass


def _draw_colorbar(
    canvas: tk.Canvas,
    x1: float,
    y0: float,
    y1: float,
    canvas_w: float,
    cmin: float,
    cmax: float,
    title: str = "",
    fmt: object = None,
) -> None:
    try:
        from openlapexe.gui.chart_xy import _color_for_value as _cfv  # type: ignore
    except Exception:
        try:
            from chart_xy import _color_for_value as _cfv  # type: ignore
        except Exception:
            _cfv = None  # type: ignore
    try:
        lo = float(cmin)
        hi = float(cmax)
        if not (_np.isfinite(lo) and _np.isfinite(hi)):
            return
        if hi - lo < 1e-12:
            hi = lo + 1.0
        bar_w = 14.0
        bar_x1 = float(x1) - 4.0
        bar_x0 = bar_x1 - bar_w
        if bar_x0 < 0:
            return
        if bar_x1 + 52 > float(canvas_w):
            shift = (bar_x1 + 52) - float(canvas_w) + 2
            bar_x0 -= shift
            bar_x1 -= shift
        steps = 24
        for si in range(steps):
            t0v = lo + (hi - lo) * si / steps
            sy1 = float(y1) - (si / steps) * (float(y1) - float(y0))
            sy0 = float(y1) - ((si + 1) / steps) * (float(y1) - float(y0))
            try:
                col = _cfv(t0v, lo, hi) if _cfv is not None else "#1f4b99"  # type: ignore
            except Exception:
                col = "#1f4b99"
            canvas.create_rectangle(bar_x0, sy0, bar_x1, sy1, fill=col, outline=col, tags=("colorbar",))
        canvas.create_rectangle(bar_x0, float(y0), bar_x1, float(y1), outline="#333", width=1, tags=("colorbar",))
        _fmt = fmt if callable(fmt) else _format_eng
        try:
            mid = (lo + hi) * 0.5
            canvas.create_text(bar_x1 + 3, float(y0) + 2, text=_fmt(hi), fill="#222", font=("TkDefaultFont", 6), anchor="w", tags=("colorbar_label",))
            canvas.create_text(bar_x1 + 3, (float(y0) + float(y1)) * 0.5, text=_fmt(mid), fill="#222", font=("TkDefaultFont", 6), anchor="w", tags=("colorbar_label",))
            canvas.create_text(bar_x1 + 3, float(y1) - 2, text=_fmt(lo), fill="#222", font=("TkDefaultFont", 6), anchor="w", tags=("colorbar_label",))
        except Exception:
            pass
        if title:
            try:
                canvas.create_text((bar_x0 + bar_x1) * 0.5, float(y0) - 8, text=str(title)[:24], fill="#222", font=("TkDefaultFont", 6), anchor="s", tags=("colorbar_title",))
            except Exception:
                pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# _project_wireframe
# ---------------------------------------------------------------------------

def _project_wireframe(verts: _np.ndarray, Rx: _np.ndarray, Ry: _np.ndarray) -> _np.ndarray:
    """verts(N,3) を Rx,Ry(3,3) で回転し正射影 (x,y) を返す."""
    try:
        v = _np.asarray(verts, dtype=float)
        if v.size == 0:
            return _np.zeros((0, 2), dtype=float)
        if v.ndim == 1:
            # single vertex case
            v = v.reshape(1, -1)
        if v.shape[1] != 3:
            # try to reshape if flat
            if v.size % 3 == 0:
                v = v.reshape(-1, 3)
            else:
                return _np.zeros((v.shape[0], 2), dtype=float)
        rx = _np.asarray(Rx, dtype=float)
        ry = _np.asarray(Ry, dtype=float)
        # handle angle scalar input (deg or rad) -> build matrix
        if rx.ndim == 0 or rx.size == 1:
            try:
                ang = float(_np.asarray(rx).ravel()[0])
                # assume radian
                c = float(_np.cos(ang))
                s = float(_np.sin(ang))
                rx = _np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=float)
            except Exception:
                rx = _np.eye(3, dtype=float)
        if ry.ndim == 0 or ry.size == 1:
            try:
                ang = float(_np.asarray(ry).ravel()[0])
                c = float(_np.cos(ang))
                s = float(_np.sin(ang))
                ry = _np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=float)
            except Exception:
                ry = _np.eye(3, dtype=float)
        if rx.shape != (3, 3):
            rx = _np.eye(3, dtype=float)
        if ry.shape != (3, 3):
            ry = _np.eye(3, dtype=float)
        # 回転: Ry @ Rx を row-vector に適用 => v @ (Ry@Rx).T = v @ Rx.T @ Ry.T
        R = ry @ rx
        rotated = v @ R.T
        proj = rotated[:, :2].copy()
        # ensure finite (replace non-finite with 0)
        # keep finite if possible; tests expect finite
        # if any non-finite, clamp to 0
        mask = ~_np.isfinite(proj)
        if _np.any(mask):
            proj[mask] = 0.0
        return proj
    except Exception:
        try:
            v = _np.asarray(verts, dtype=float)
            n = int(v.shape[0]) if v.ndim >= 1 else 0
            return _np.zeros((n, 2), dtype=float)
        except Exception:
            return _np.zeros((0, 2), dtype=float)


# ---------------------------------------------------------------------------
# BaseChart
# ---------------------------------------------------------------------------

class BaseChart(tk.Canvas):
    """汎用Canvas基盤. bg white, <Configure> 再描画, _last_draw_ms計測."""

    def __init__(self, master: tk.Widget | None = None, **kwargs: object) -> None:
        kwargs.setdefault("bg", "white")
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("highlightbackground", "#ccc")
        kwargs.setdefault("height", 240)
        super().__init__(master, **kwargs)  # type: ignore[arg-type]
        self._x_data: _np.ndarray | None = None
        self._y_data: _np.ndarray | None = None
        # aliases for test introspection / compatibility
        self.x_data: _np.ndarray | None = None
        self.y_data: _np.ndarray | None = None
        self._last_draw_ms: float = 0.0
        self._draw_count: int = 0
        self.bind("<Configure>", lambda _e: self._redraw())
        self._zoom_fx: float = 1.0
        self._zoom_fy: float = 1.0
        self._pan_dx: float = 0.0
        self._pan_dy: float = 0.0
        self._zoom_data_id: int | None = None
        self._scan_x: int | None = None
        self._scan_y: int | None = None
        self._xlabel: str = ""
        self._ylabel: str = ""
        self._series_labels: list[tuple[str, str, str]] | None = None
        self._c_label: str = ""
        self._view: tuple[float, float, float, float, float, float, float, float] | None = None
        self._probe_enabled: bool = True
        self._probe_text: str = ""
        self._probe_data: tuple[float, ...] | None = None
        self._press_xy: tuple[int, int] | None = None
        _orig_redraw = self._redraw
        self._redraw_plain = _orig_redraw

        def _redraw_with_zoom() -> None:
            try:
                data_id = id(self._x_data)
            except Exception:
                data_id = None
            if data_id != self._zoom_data_id:
                self._zoom_fx = 1.0
                self._zoom_fy = 1.0
                self._pan_dx = 0.0
                self._pan_dy = 0.0
                self._zoom_data_id = data_id
            try:
                _orig_redraw()
            except Exception:
                return
            try:
                if abs(self._zoom_fx - 1.0) > 1e-9 or abs(self._zoom_fy - 1.0) > 1e-9 or abs(self._pan_dx) > 1e-9 or abs(self._pan_dy) > 1e-9:
                    w = int(self.winfo_width())
                    h = int(self.winfo_height())
                    self.scale("all", w * 0.5, h * 0.5, self._zoom_fx, self._zoom_fy)
                    self.move("all", self._pan_dx, self._pan_dy)
            except Exception:
                pass
            try:
                bb = self.bbox("all")
                if bb is not None:
                    x0, y0, x1, y1 = bb
                    w = int(self.winfo_width())
                    h = int(self.winfo_height())
                    self.configure(scrollregion=(x0 - w, y0 - h, x1 + w, y1 + h))
            except Exception:
                pass

        self._redraw = _redraw_with_zoom  # type: ignore[method-assign]
        self.bind("<MouseWheel>", self._on_zoom_wheel)
        self.bind("<Button-4>", lambda e: self._zoom_step(e, 1))
        self.bind("<Button-5>", lambda e: self._zoom_step(e, -1))
        self.bind("<ButtonPress-1>", self._on_pan_press, add="+")
        self.bind("<B1-Motion>", self._on_pan_drag, add="+")
        self.bind("<Double-Button-1>", lambda _e: self.reset_zoom())
        self.bind("<ButtonPress-1>", self._on_probe_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_probe_release, add="+")
        self.bind("<Escape>", lambda _e: self._clear_probe())

    def reset_zoom(self) -> None:
        self._zoom_fx = 1.0
        self._zoom_fy = 1.0
        self._pan_dx = 0.0
        self._pan_dy = 0.0
        try:
            self._zoom_data_id = id(self._x_data)
        except Exception:
            self._zoom_data_id = None
        try:
            self._redraw()
        except Exception:
            pass

    def _zoom_step(self, event: object, steps: int) -> str:
        try:
            px = int(getattr(event, "x", 0))
            py = int(getattr(event, "y", 0))
        except Exception:
            px, py = 0, 0
        factor = 1.25 ** int(steps)
        return self.zoom_at(px, py, factor)

    def _on_zoom_wheel(self, event: object) -> str:
        try:
            delta = int(getattr(event, "delta", 0))
        except Exception:
            delta = 0
        steps = 1 if delta > 0 else (-1 if delta < 0 else 0)
        if steps == 0:
            return "break"
        try:
            px = int(getattr(event, "x", 0))
            py = int(getattr(event, "y", 0))
        except Exception:
            px, py = 0, 0
        return self.zoom_at(px, py, 1.25 ** steps)

    def zoom_at(self, px: float, py: float, factor: float) -> str:
        try:
            self._clear_probe()
        except Exception:
            pass
        try:
            f = float(factor)
        except Exception:
            return "break"
        if f <= 0:
            return "break"
        new_f = min(25.0, max(0.2, float(self._zoom_fx) * f))
        ax = new_f / self._zoom_fx if self._zoom_fx else 1.0
        self._zoom_fx, self._zoom_fy = new_f, new_f
        try:
            self.scale("all", float(px), float(py), ax, ax)
        except Exception:
            pass
        return "break"

    def _on_pan_press(self, event: object) -> None:
        try:
            self._clear_probe()
        except Exception:
            pass
        try:
            self._scan_x = int(getattr(event, "x", 0))
            self._scan_y = int(getattr(event, "y", 0))
            self.scan_mark(self._scan_x, self._scan_y)
        except Exception:
            self._scan_x = None
            self._scan_y = None

    def _on_pan_drag(self, event: object) -> None:
        try:
            x = int(getattr(event, "x", 0))
            y = int(getattr(event, "y", 0))
        except Exception:
            return
        try:
            if self._scan_x is not None and self._scan_y is not None:
                self._pan_dx += x - self._scan_x
                self._pan_dy += y - self._scan_y
            self._scan_x, self._scan_y = x, y
            self.scan_dragto(x, y, gain=1)
        except Exception:
            pass

    def _store_view(self, xl: float, xh: float, yl: float, yh: float, x0: float, y0: float, x1: float, y1: float) -> None:
        try:
            self._view = (float(xl), float(xh), float(yl), float(yh), float(x0), float(y0), float(x1), float(y1))
        except Exception:
            pass

    def enable_probe(self, enabled: bool = True) -> None:
        try:
            self._probe_enabled = bool(enabled)
        except Exception:
            pass

    def _event_canvas_xy(self, event: object) -> tuple[float, float]:
        try:
            ex = float(getattr(event, "x", 0))
            ey = float(getattr(event, "y", 0))
        except Exception:
            ex, ey = 0.0, 0.0
        try:
            cx = float(self.canvasx(ex))  # type: ignore[attr-defined]
            cy = float(self.canvasy(ey))  # type: ignore[attr-defined]
            return (cx, cy)
        except Exception:
            return (ex, ey)

    def _canvas_to_base(self, cx: float, cy: float) -> tuple[float, float]:
        try:
            w = int(self.winfo_width())
            h = int(self.winfo_height())
        except Exception:
            w, h = 600, 400
        try:
            dx = float(getattr(self, "_pan_dx", 0.0) or 0.0)
            dy = float(getattr(self, "_pan_dy", 0.0) or 0.0)
            fx = float(getattr(self, "_zoom_fx", 1.0) or 1.0)
            fy = float(getattr(self, "_zoom_fy", 1.0) or 1.0)
            if fx == 0:
                fx = 1.0
            if fy == 0:
                fy = 1.0
            ccx = float(w) * 0.5
            ccy = float(h) * 0.5
            bx = (float(cx) - dx - ccx) / fx + ccx
            by = (float(cy) - dy - ccy) / fy + ccy
            return (bx, by)
        except Exception:
            return (float(cx), float(cy))

    def _base_to_canvas(self, bx: float, by: float) -> tuple[float, float]:
        try:
            w = int(self.winfo_width())
            h = int(self.winfo_height())
        except Exception:
            w, h = 600, 400
        try:
            dx = float(getattr(self, "_pan_dx", 0.0) or 0.0)
            dy = float(getattr(self, "_pan_dy", 0.0) or 0.0)
            fx = float(getattr(self, "_zoom_fx", 1.0) or 1.0)
            fy = float(getattr(self, "_zoom_fy", 1.0) or 1.0)
            ccx = float(w) * 0.5
            ccy = float(h) * 0.5
            cx = (float(bx) - ccx) * fx + ccx + dx
            cy = (float(by) - ccy) * fy + ccy + dy
            return (cx, cy)
        except Exception:
            return (float(bx), float(by))

    def _on_probe_press(self, event: object) -> None:
        try:
            self._press_xy = (int(getattr(event, "x", 0)), int(getattr(event, "y", 0)))
        except Exception:
            self._press_xy = None

    def _on_probe_release(self, event: object) -> None:
        try:
            if not getattr(self, "_probe_enabled", True):
                return
            px = int(getattr(event, "x", 0))
            py = int(getattr(event, "y", 0))
            if self._press_xy is not None:
                dx = px - self._press_xy[0]
                dy = py - self._press_xy[1]
                if dx * dx + dy * dy > 25:
                    return
            cx, cy = self._event_canvas_xy(event)
            self._show_probe_at_pixel(float(cx), float(cy))
        except Exception:
            pass

    def _pixel_to_data(self, px: float, py: float) -> tuple[float, float] | None:
        try:
            bx, by = self._canvas_to_base(float(px), float(py))
            v = getattr(self, "_view", None)
            if v is None:
                return None
            xl, xh, yl, yh, x0, y0, x1, y1 = v
            if x1 == x0 or y1 == y0:
                return None
            fx = (bx - x0) / (x1 - x0)
            fy = (y1 - by) / (y1 - y0)
            return (xl + fx * (xh - xl), yl + fy * (yh - yl))
        except Exception:
            return None

    def _nearest_point(self, dx: float, dy: float) -> tuple[int, float, float, float | None]:
        try:
            xa = _np.asarray(self._x_data, dtype=float) if getattr(self, "_x_data", None) is not None else None
            ya = _np.asarray(self._y_data, dtype=float) if getattr(self, "_y_data", None) is not None else None
            if xa is None or ya is None or xa.size == 0:
                return (-1, float(dx), float(dy), None)
            n = min(int(xa.size), int(ya.size))
            xa = xa[:n]
            ya = ya[:n]
            ca = None
            try:
                if getattr(self, "_c_data", None) is not None:
                    ca0 = _np.asarray(self._c_data, dtype=float)
                    if ca0.size >= n:
                        ca = ca0[:n]
            except Exception:
                ca = None
            v = getattr(self, "_view", None)
            if v is not None:
                xl, xh, yl, yh, x0, y0, x1, y1 = v
                try:
                    px = x0 + (xa - xl) / (xh - xl + 1e-12) * (x1 - x0)
                    py = y1 - (ya - yl) / (yh - yl + 1e-12) * (y1 - y0)
                    import math as _math

                    # cursor pixel from data values
                    cx = x0 + (float(dx) - xl) / (xh - xl + 1e-12) * (x1 - x0)
                    cy = y1 - (float(dy) - yl) / (yh - yl + 1e-12) * (y1 - y0)
                    d2 = (px - cx) ** 2 + (py - cy) ** 2
                    idx = int(_np.argmin(d2))
                    cv = float(ca[idx]) if ca is not None else None
                    return (idx, float(xa[idx]), float(ya[idx]), cv)
                except Exception:
                    pass
            d2 = (xa - float(dx)) ** 2 + (ya - float(dy)) ** 2
            idx = int(_np.argmin(d2))
            cv = float(ca[idx]) if ca is not None else None
            return (idx, float(xa[idx]), float(ya[idx]), cv)
        except Exception:
            return (-1, float(dx), float(dy), None)

    def _show_probe_at_pixel(self, px: float, py: float) -> None:
        try:
            self.delete("probe")
        except Exception:
            pass
        try:
            # px/py are canvas coords (scroll/zoom aware); map via base space
            bx, by = self._canvas_to_base(float(px), float(py))
            v0 = getattr(self, "_view", None)
            if v0 is None:
                return
            xl0, xh0, yl0, yh0, x00, y00, x10, y10 = v0
            if x10 == x00 or y10 == y00:
                return
            fx0 = (bx - x00) / (x10 - x00)
            fy0 = (y10 - by) / (y10 - y00)
            dx = xl0 + fx0 * (xh0 - xl0)
            dy = yl0 + fy0 * (yh0 - yl0)
            idx, nx, ny, cv = self._nearest_point(dx, dy)
            xl_lab = getattr(self, "_xlabel", "") or "x"
            yl_lab = getattr(self, "_ylabel", "") or "y"
            if idx >= 0:
                lines = [f"#{idx} {xl_lab}={_format_eng(nx)} {yl_lab}={_format_eng(ny)}"]
            else:
                lines = [f"{xl_lab}={_format_eng(dx)} {yl_lab}={_format_eng(dy)}"]
            if cv is not None:
                cl = getattr(self, "_c_label", "") or "c"
                lines.append(f"{cl}={_format_eng(cv)}")
            try:
                w = int(self.winfo_width())
                h = int(self.winfo_height())
            except Exception:
                w, h = 600, 400
            v = getattr(self, "_view", None)
            # crosshair spans full canvas so it stays correct under zoom/pan
            try:
                self.create_line(0, float(py), float(w), float(py), fill="#888", dash=(3, 3), tags=("probe",))
                self.create_line(float(px), 0, float(px), float(h), fill="#888", dash=(3, 3), tags=("probe",))
            except Exception:
                pass
            if idx >= 0 and v is not None:
                try:
                    xl, xh, yl, yh, vx0, vy0, vx1, vy1 = v
                    mpx = vx0 + (nx - xl) / (xh - xl + 1e-12) * (vx1 - vx0)
                    mpy = vy1 - (ny - yl) / (yh - yl + 1e-12) * (vy1 - vy0)
                    mpx, mpy = self._base_to_canvas(mpx, mpy)
                    self.create_oval(mpx - 4, mpy - 4, mpx + 4, mpy + 4, outline="#d00", width=2, tags=("probe",))
                except Exception:
                    pass
            # readout box
            try:
                fw = max(len(s) for s in lines) * 6.5 + 12
                fh = len(lines) * 13 + 10
                bx = min(max(float(px) + 12, 4.0), max(4.0, float(w) - fw - 4))
                by = min(max(float(py) - fh - 8, 4.0), max(4.0, float(h) - fh - 4))
                self.create_rectangle(bx, by, bx + fw, by + fh, fill="white", outline="#222", width=1, tags=("probe",))
                for i, s in enumerate(lines):
                    self.create_text(bx + 6, by + 6 + i * 13, text=s, fill="#111", font=("TkDefaultFont", 7), anchor="nw", tags=("probe",))
                self._probe_text = " | ".join(lines)
                self._probe_data = (float(nx if idx >= 0 else dx), float(ny if idx >= 0 else dy)) if idx is not None else None
            except Exception:
                pass
        except Exception:
            pass

    def _clear_probe(self) -> None:
        try:
            self.delete("probe")
        except Exception:
            pass
        try:
            self._probe_text = ""
            self._probe_data = None
        except Exception:
            pass

    def set_data(self, x, y) -> None:  # type: ignore[no-untyped-def]
        try:
            self._x_data = _np.asarray(x, dtype=float)
            self._y_data = _np.asarray(y, dtype=float)
            self.x_data = self._x_data
            self.y_data = self._y_data
        except Exception:
            self._x_data = x  # type: ignore
            self._y_data = y  # type: ignore
        self._redraw()

    def plot(self, result) -> None:  # type: ignore[no-untyped-def]
        try:
            x = getattr(result, "x", None)
            y = getattr(result, "y", None)
            if x is None:
                x = getattr(result, "s", None)
            if y is None:
                y = getattr(result, "v", None)
            if x is not None and y is not None:
                self.set_data(x, y)
                return
        except Exception:
            pass
        try:
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                self.set_data(result[0], result[1])  # type: ignore
        except Exception:
            pass

    def update_chart(self, x, y) -> None:  # type: ignore[no-untyped-def]
        self.set_data(x, y)

    # helpers exposed as methods for testability
    def _draw_grid(self, x0: float, y0: float, x1: float, y1: float, nx: int = 5, ny: int = 5) -> None:
        _draw_grid(self, x0, y0, x1, y1, nx, ny)

    def _draw_axes(self, x0: float, y0: float, x1: float, y1: float, nx: int = 5, ny: int = 5) -> None:
        _draw_axes(self, x0, y0, x1, y1, nx, ny)

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
        has_data = False
        try:
            if self._x_data is not None and self._y_data is not None:
                xa = _np.asarray(self._x_data, dtype=float)
                ya = _np.asarray(self._y_data, dtype=float)
                if xa.size > 1 and ya.size > 1:
                    has_data = True
        except Exception:
            has_data = False
        if not has_data:
            try:
                # grid
                _draw_grid(self, float(PAD_LEFT), float(PAD_TOP), float(w - PAD_RIGHT), float(h - PAD_BOTTOM), 5, 5)
                # axes + ticks
                _draw_axes(self, float(PAD_LEFT), float(PAD_TOP), float(w - PAD_RIGHT), float(h - PAD_BOTTOM), 5, 5)
                self.create_text(w // 2, h // 2, text="No data", fill="#888", tags=("placeholder",))
            except Exception:
                pass
            self._last_draw_ms = (time.perf_counter() - t0) * 1000
            return
        try:
            x_arr = _np.asarray(self._x_data, dtype=float)
            y_arr = _np.asarray(self._y_data, dtype=float)
            mask = _np.isfinite(x_arr) & _np.isfinite(y_arr)
            if _np.any(mask):
                x_arr = x_arr[mask]
                y_arr = y_arr[mask]
            if x_arr.size == 0:
                self._last_draw_ms = (time.perf_counter() - t0) * 1000
                return
            if x_arr.size > 800:
                x_arr, y_arr = _thin(x_arr, y_arr, 800)
            # axis limits with 5% padding
            xl, xh = _axis_limits(x_arr, 0.05)
            yl, yh = _axis_limits(y_arr, 0.05)
            # ensure non-zero ranges
            if xh - xl < 1e-9:
                xh = xl + 1.0
            if yh - yl < 1e-9:
                yh = yl + 10.0
            # expand y a bit similar to SpeedChart
            y_range = yh - yl
            # keep x as-is (no extra), y add 5% already done
            plot_w = float(w - PAD_LEFT - PAD_RIGHT)
            plot_h = float(h - PAD_TOP - PAD_BOTTOM)
            if plot_w < 1:
                plot_w = 1
            if plot_h < 1:
                plot_h = 1
            x_scale = plot_w / (xh - xl)
            y_scale = plot_h / (yh - yl)
            try:
                self._store_view(xl, xh, yl, yh, float(PAD_LEFT), float(PAD_TOP), float(w - PAD_RIGHT), float(h - PAD_BOTTOM))
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
                    px = PAD_LEFT + (float(xv) - xl) * x_scale
                except Exception:
                    continue
                if px < PAD_LEFT - 1 or px > w - PAD_RIGHT + 1:
                    continue
                self.create_line(px, PAD_TOP, px, h - PAD_BOTTOM, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            for yv in yticks:
                try:
                    py = h - PAD_BOTTOM - (float(yv) - yl) * y_scale
                except Exception:
                    continue
                if py < PAD_TOP - 1 or py > h - PAD_BOTTOM + 1:
                    continue
                self.create_line(PAD_LEFT, py, w - PAD_RIGHT, py, fill="#e0e0e0", dash=(2, 2), tags=("grid",))
            # axes
            self.create_line(PAD_LEFT, h - PAD_BOTTOM, w - PAD_RIGHT, h - PAD_BOTTOM, fill="#333", width=1, tags=("axis",))
            self.create_line(PAD_LEFT, PAD_TOP, PAD_LEFT, h - PAD_BOTTOM, fill="#333", width=1, tags=("axis",))
            for xv in xticks:
                try:
                    px = PAD_LEFT + (float(xv) - xl) * x_scale
                except Exception:
                    continue
                if px < PAD_LEFT - 1 or px > w - PAD_RIGHT + 1:
                    continue
                self.create_line(px, h - PAD_BOTTOM, px, h - PAD_BOTTOM + 4, fill="#333", tags=("tick",))
                self.create_text(px, h - PAD_BOTTOM + 10, text=_format_eng(float(xv)), fill="#333", font=("TkDefaultFont", 7), anchor="n", tags=("ticklabel",))
            for yv in yticks:
                try:
                    py = h - PAD_BOTTOM - (float(yv) - yl) * y_scale
                except Exception:
                    continue
                if py < PAD_TOP - 1 or py > h - PAD_BOTTOM + 1:
                    continue
                self.create_line(PAD_LEFT - 4, py, PAD_LEFT, py, fill="#333", tags=("tick",))
                self.create_text(PAD_LEFT - 6, py, text=_format_eng(float(yv)), fill="#333", font=("TkDefaultFont", 7), anchor="e", tags=("ticklabel",))
            # polyline
            coords: list[float] = []
            for xv, yv in zip(x_arr, y_arr):
                px = PAD_LEFT + (float(xv) - xl) * x_scale
                py = h - PAD_BOTTOM - (float(yv) - yl) * y_scale
                coords.append(px)
                coords.append(py)
            if len(coords) >= 4:
                self.create_line(*coords, fill="#1f4b99", width=2, smooth=False, tags=("line",))
            try:
                items = list(getattr(self, "_series_labels", None) or [])
                if not items:
                    yl_lab = str(getattr(self, "_ylabel", "") or "y")
                    items = [("#1f4b99", yl_lab if yl_lab else "data", "line")]
                _draw_legend_box(self, items, float(w - PAD_RIGHT), float(PAD_TOP))
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

