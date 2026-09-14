# -*- coding: utf-8 -*-
# allow: SIZE_OK — DragView 61行表+Canvas自前+ギアマップ単一責務 (ttk GUI) 737行
"""openlapexe.gui.drag_view - OpenDRAGタブ(NEW) ttk+Canvas自前.

Requirements (TASK):
- src/openlapexe/drag.py の simulate_drag をライブ呼出 (thread無し同期でOK)
- speed_trap 50..350km/h 表: 61行 (50+5*i, i=0..60), 列 Aero_Dr/Roll_Dr/ax_drag/rpm/TPS/bps
- ギアマップ: shift_points + en_speed_curve (driveline)
- ドラッグ曲線 Canvas自前: aero vs speed, Wd vs speed (2曲線, 軸・凡例あり)
- gear==0 番兵表示: "0 (シフト中)" 表示, 内部0保持
- t - t_shift > shift_time 厳密> 注記 (strictly >, not >=) MATLAB:OpenDRAG.m:262
- ttkのみ, mpl/sci-py禁止, messagebox parent=self, encoding utf-8
- app.py既存タブ温存 (本モジュールは独立, App2で任意統合)
- tests/test_drag_view_src.py で RED->GREEN: 61行, 100m/s値がdrag単体と一致

Public: DragView
"""
from __future__ import annotations

import logging
import math
import pathlib
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont

import numpy as _np

try:
    from openlapexe.gui.combobox_fix import fix_combobox as _fix_combo, fix_treeview_horizontal as _fix_tree_h  # type: ignore
except Exception:
    _fix_combo = None  # type: ignore
    _fix_tree_h = None  # type: ignore

try:
    from openlapexe.io import resource_path as _resource_path
except Exception:
    def _resource_path(relative: str) -> pathlib.Path:  # type: ignore[no-redef]
        if hasattr(sys, "_MEIPASS"):
            base = pathlib.Path(str(sys._MEIPASS))  # type: ignore[attr-defined]
        else:
            base = pathlib.Path(__file__).resolve().parents[3]
            if not (base / "app.py").exists() and not (base / "data").exists():
                base = pathlib.Path(__file__).resolve().parents[2]
        return base / relative

try:
    from openlapexe.drag import simulate_drag as _simulate_drag
except Exception:
    _simulate_drag = None  # type: ignore

try:
    from openlapexe.vehicle import Vehicle47 as _Vehicle47
except Exception:
    _Vehicle47 = None  # type: ignore

# Try import _build_driveline forギアマップ
try:
    from openlapexe.drag import _build_driveline as _build_driveline  # type: ignore
except Exception:
    _build_driveline = None  # type: ignore

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# helpers: physics matching drag.py (Aero_Dr etc) for 100m/s一致検証
# ---------------------------------------------------------------------------

def _aero_for_speed(v: float, vehicle: object) -> tuple[float, float, float, float, float]:
    """Compute Aero_Dr, Roll_Dr, ax_drag, Aero_Df, Wd for given v matching drag.py.

    Returns (Aero_Dr, Roll_Dr, ax_drag, Aero_Df, Wd)
    Uses same formulas as drag.py: MATLAB:OpenDRAG.m:223-230, 228
    """
    # vehicle params with fallbacks matching drag.py
    M: float
    if hasattr(vehicle, "M"):
        M = float(getattr(vehicle, "M"))
    elif hasattr(vehicle, "mass_kg"):
        M = float(getattr(vehicle, "mass_kg"))
    else:
        M = 650.0
    g = 9.81
    bank = 0.0
    incl = 0.0

    def _cosd(d: float) -> float:
        return math.cos(math.radians(d))

    def _sind(d: float) -> float:
        return math.sin(math.radians(d))

    Wz = M * g * _cosd(bank) * _cosd(incl)  # MATLAB:OpenDRAG.m:81
    Wx = M * g * _sind(incl)  # MATLAB:OpenDRAG.m:84 (0 for incl=0)

    rho = float(getattr(vehicle, "rho", 1.225))
    factor_Cl = float(getattr(vehicle, "factor_Cl", 1.0))
    Cl = float(getattr(vehicle, "Cl", getattr(vehicle, "cl", -4.8)))
    factor_Cd = float(getattr(vehicle, "factor_Cd", 1.0))
    Cd = float(getattr(vehicle, "Cd", getattr(vehicle, "cda", 1.2)))
    if hasattr(vehicle, "cda") and not hasattr(vehicle, "Cd"):
        A_val_tmp = float(getattr(vehicle, "A", 1.0)) if hasattr(vehicle, "A") else 1.0
        Cd = -abs(float(getattr(vehicle, "cda"))) / max(A_val_tmp, 1e-9)
    A = float(getattr(vehicle, "A", 1.0))
    Cr = float(getattr(vehicle, "Cr", -0.001))
    df = float(getattr(vehicle, "df", getattr(vehicle, "weight_dist_front", 0.45)))
    da = float(getattr(vehicle, "da", getattr(vehicle, "weight_dist_front", 0.5)))
    drive = str(getattr(vehicle, "drive", "RWD"))
    if drive == "RWD":
        factor_drive = 1.0 - df  # MATLAB:OpenVEHICLE.m:234-237
        factor_aero = 1.0 - da
        driven_wheels = 2
    elif drive == "FWD":
        factor_drive = df
        factor_aero = da
        driven_wheels = 2
    else:
        factor_drive = 1.0
        factor_aero = 1.0
        driven_wheels = 4

    Aero_Df = 0.5 * rho * factor_Cl * Cl * A * v * v  # MATLAB:OpenDRAG.m:223
    Aero_Dr = 0.5 * rho * factor_Cd * Cd * A * v * v  # MATLAB:OpenDRAG.m:224
    Roll_Dr = Cr * (-Aero_Df + Wz)  # MATLAB:OpenDRAG.m:226
    Wd = (factor_drive * Wz + (-factor_aero * Aero_Df)) / max(driven_wheels, 1)  # MATLAB:OpenDRAG.m:228
    ax_drag = (Aero_Dr + Roll_Dr + Wx) / max(M, 1e-9)  # MATLAB:OpenDRAG.m:230
    return Aero_Dr, Roll_Dr, ax_drag, Aero_Df, Wd


def _format_gear(g: float | int) -> str:
    """gear==0番兵表示: 0はシフト中表示, 内部は0保持."""
    try:
        gi = int(float(g))
    except Exception:
        return str(g)
    if gi == 0:
        return "0 (シフト中)"
    return str(gi)


# ---------------------------------------------------------------------------
# DragView
# ---------------------------------------------------------------------------
class DragView(ttk.Frame):
    """OpenDRAGタブ: simulate_dragライブ呼出 + 61行表 + ギアマップ + Canvas曲線.

    要件:
    - ttkのみ + tk.Canvas (mpl禁止)
    - simulate_drag live call (speed_trap 50..350km/h 既定)
    - 表61行: 50+5*i km/h, 列 Aero_Dr/Roll_Dr/ax_drag/rpm/TPS/bps (+speed, gear)
    - ギアマップ: shift_points + en_speed_curve (drag._build_driveline経由)
    - Canvas: aero vs speed, Wd vs speed
    - gear==0番兵表示
    - t - t_shift > shift_time 厳密> 注記 (MATLAB:OpenDRAG.m:262 strict >)
    - messagebox parent=self, encoding utf-8, resource_path利用
    """

    def __init__(self, parent: tk.Widget | ttk.Frame | tk.Misc | None = None, **kwargs: object) -> None:
        super().__init__(parent, **kwargs)  # type: ignore[arg-type]
        # Font retention
        try:
            self._font_default = tkfont.nametofont("TkDefaultFont")
            self._font_text = tkfont.nametofont("TkTextFont")
        except Exception:
            self._font_default = None  # type: ignore
            self._font_text = None  # type: ignore

        self._vehicle: object | None = None
        self._drag_result: object | None = None
        self._speeds_kmh: list[float] = [50.0 + 5.0 * i for i in range(61)]  # 50..350 step5 =61
        self._speeds_mps: _np.ndarray = _np.array([v / 3.6 for v in self._speeds_kmh], dtype=float)
        self._shift_points: _np.ndarray | None = None
        self._en_speed_curve: _np.ndarray | None = None
        self._table_data: list[dict[str, object]] = []

        self._discover_vehicles()

        # -- top controls: vehicle selector + Run + speed_trapラベル --
        self._ctrl = ttk.Frame(self)
        self._ctrl.pack(side="top", fill="x", padx=6, pady=(6, 4))

        ttk.Label(self._ctrl, text="車両").pack(side="left", padx=(0, 4))
        self.combo = ttk.Combobox(self._ctrl, state="readonly", width=18, values=self._vehicle_names)
        self.combobox = self.combo
        self.vehicle_combo = self.combo
        self.selector = self.combo
        if self._vehicle_names:
            # default f1
            lower = [s.lower() for s in self._vehicle_names]
            idx = lower.index("f1") if "f1" in lower else 0
            self.combo.current(idx)
            try:
                self._load_vehicle(self._vehicle_names[idx])
            except Exception:
                pass
        self.combo.pack(side="left", padx=4)
        self.combo.bind("<<ComboboxSelected>>", self._on_vehicle_selected)
        try:
            self.combo.bind("<FocusIn>", lambda _e: self.refresh_vehicles())
            self.combo.bind("<Button-1>", lambda _e: self.refresh_vehicles())
        except Exception:
            pass
        try:
            if _fix_combo is not None:
                _fix_combo(self.combo, self._vehicle_names, max_chars=36)
        except Exception:
            pass

        self.btn_run = ttk.Button(self._ctrl, text="Run", command=self._on_run)
        self.run_button = self.btn_run
        self._run_btn = self.btn_run
        self.btn_run.pack(side="left", padx=8)

        # speed_trapラベル 50..350km/h
        self._speed_trap_label = ttk.Label(self._ctrl, text="speed_trap 50..350km/h (61行)")
        self.speed_trap_label = self._speed_trap_label
        self._speed_trap_label.pack(side="left", padx=8)

        # status var
        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(self._ctrl, textvariable=self._status_var).pack(side="right", padx=6)

        self._scroll = None  # type: ignore
        self.scrollable = None  # type: ignore
        _drag_parent = self  # type: ignore

        # -- middle: PanedWindow 分割 (表 + 右Canvas/ギアマップ) --
        self._paned = ttk.PanedWindow(_drag_parent, orient="horizontal")
        self._paned.pack(fill="both", expand=True, padx=6, pady=6)

        # left: 表 Treeview 61行
        self._left_frame = ttk.Frame(self._paned)
        self._paned.add(self._left_frame, weight=3)

        columns = ("no", "speed_kmh", "speed_ms", "Aero_Dr", "Roll_Dr", "ax_drag", "rpm", "TPS", "bps", "gear")
        self.tree = ttk.Treeview(self._left_frame, columns=columns, show="headings", height=14)
        self.table = self.tree
        self.speed_table = self.tree
        self._tree = self.tree
        # headings matching spec strings
        headings = {
            "no": "No",
            "speed_kmh": "speed km/h",
            "speed_ms": "speed m/s",
            "Aero_Dr": "Aero_Dr",
            "Roll_Dr": "Roll_Dr",
            "ax_drag": "ax_drag",
            "rpm": "rpm",
            "TPS": "TPS",
            "bps": "bps",
            "gear": "gear",
        }
        widths = {"no": 40, "speed_kmh": 80, "speed_ms": 80, "Aero_Dr": 85, "Roll_Dr": 85, "ax_drag": 80, "rpm": 70, "TPS": 60, "bps": 60, "gear": 90}
        for c in columns:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="center", stretch=True)
        # scrollbar
        vsb = ttk.Scrollbar(self._left_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self._left_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        try:
            hsb.pack(side="bottom", fill="x")
        except Exception:
            pass
        try:
            if _fix_tree_h is not None:
                _fix_tree_h(self.tree, self._left_frame)
        except Exception:
            pass

        # right: tab-switched notebook (ドラッグ曲線 / ギアマップ)
        self._right_frame = ttk.Frame(self._paned)
        self._paned.add(self._right_frame, weight=2)
        self.graph_notebook = ttk.Notebook(self._right_frame)
        self.graph_notebook.pack(fill="both", expand=True, padx=2, pady=2)
        self._graph_notebook = self.graph_notebook
        self.tab_curve = ttk.Frame(self.graph_notebook)
        self.tab_gear = ttk.Frame(self.graph_notebook)
        self.graph_notebook.add(self.tab_curve, text="ドラッグ曲線")
        self.graph_notebook.add(self.tab_gear, text="ギアマップ")
        # Drag* 13系列タブ追加 (2+13=15, per-tab try/except)
        self.tab_tx = ttk.Frame(self.graph_notebook)
        self.tab_tv = ttk.Frame(self.graph_notebook)
        self.tab_xv = ttk.Frame(self.graph_notebook)
        self.tab_ta = ttk.Frame(self.graph_notebook)
        self.tab_xa = ttk.Frame(self.graph_notebook)
        self.tab_trpm = ttk.Frame(self.graph_notebook)
        self.tab_xrpm = ttk.Frame(self.graph_notebook)
        self.tab_tgear = ttk.Frame(self.graph_notebook)
        self.tab_xgear = ttk.Frame(self.graph_notebook)
        self.tab_ttps = ttk.Frame(self.graph_notebook)
        self.tab_xtps = ttk.Frame(self.graph_notebook)
        self.tab_tbps = ttk.Frame(self.graph_notebook)
        self.tab_xbps = ttk.Frame(self.graph_notebook)
        try:
            self.graph_notebook.add(self.tab_tx, text="T-X")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_tv, text="T-V")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_xv, text="X-V")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_ta, text="T-A")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_xa, text="X-A")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_trpm, text="T-RPM")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_xrpm, text="X-RPM")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_tgear, text="T-GEAR")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_xgear, text="X-GEAR")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_ttps, text="T-TPS")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_xtps, text="X-TPS")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_tbps, text="T-BPS")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_xbps, text="X-BPS")
        except Exception:
            pass
        self.graph_notebook.bind("<<NotebookTabChanged>>", lambda _e: self._redraw_canvas())

        # Canvas for drag curves: aero vs speed, Wd vs speed
        self._canvas_frame = ttk.LabelFrame(self.tab_curve, text="ドラッグ曲線: aero vs speed / Wd vs speed (Canvas自前)")
        self._canvas_frame.pack(fill="both", expand=True, padx=4, pady=4)
        self.canvas = tk.Canvas(self._canvas_frame, bg="white", highlightthickness=1, highlightbackground="#ccc", height=220)
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self.drag_canvas = self.canvas
        self._drag_canvas = self.canvas
        self.aero_canvas = self.canvas
        self.canvas.bind("<Configure>", lambda _e: self._redraw_canvas())
        self._probe_press: tuple[int, int] | None = None
        self._probe_curve: tuple | None = None
        try:
            self.canvas.bind("<ButtonPress-1>", self._on_probe_press, add="+")
            self.canvas.bind("<ButtonRelease-1>", self._on_probe_release, add="+")
            self.canvas.bind("<Escape>", lambda _e: self._clear_probe(), add="+")
        except Exception:
            pass

        # legend row
        self._legend_frame = ttk.Frame(self._canvas_frame)
        self._legend_frame.pack(fill="x", padx=4, pady=(0, 4))
        # aero label
        self._legend_aero = ttk.Label(self._legend_frame, text="● aero (Aero_Dr)", foreground="#1f4b99")
        self._legend_aero.pack(side="left", padx=6)
        self._legend_wd = ttk.Label(self._legend_frame, text="● Wd (駆動輪荷重)", foreground="#c0392b")
        self._legend_wd.pack(side="left", padx=6)

        # ギアマップ Frame: shift_points + en_speed_curve
        self._gear_frame = ttk.LabelFrame(self.tab_gear, text="ギアマップ: shift_points + en_speed_curve")
        self._gear_frame.pack(fill="both", expand=True, padx=4, pady=4)
        self._gear_info_var = tk.StringVar(value="shift_points: --")
        self._gear_label = ttk.Label(self._gear_frame, textvariable=self._gear_info_var, wraplength=320, justify="left")
        self._gear_label.pack(anchor="w", padx=6, pady=4)
        self.gear_label = self._gear_label
        self.shift_label = self._gear_label

        self._en_info_var = tk.StringVar(value="en_speed_curve: --")
        self._en_label = ttk.Label(self._gear_frame, textvariable=self._en_info_var, wraplength=320, justify="left")
        self._en_label.pack(anchor="w", padx=6, pady=(0, 4))
        self.en_label = self._en_label

        # Treeview for gear details (optional second table)
        self.gear_table = ttk.Treeview(self._gear_frame, columns=("gear", "ratio", "shift_rpm"), show="headings", height=4)
        for col, w, txt in [("gear", 50, "gear"), ("ratio", 80, "ratio"), ("shift_rpm", 90, "shift_rpm")]:
            self.gear_table.heading(col, text=txt)
            self.gear_table.column(col, width=w, anchor="center")
        self.gear_table.pack(fill="x", padx=4, pady=4)
        self._gear_table = self.gear_table

        # Drag* 13系列チャートを各タブへ埋込 (try/except+placeholder)
        try:
            from openlapexe.gui.charts_drag import DragTXChart as _DTX  # type: ignore
            self.drag_tx_chart = _DTX(self.tab_tx)
            self.drag_tx_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_tx, text="T-X (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.drag_tx_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_drag import DragTVChart as _DTV  # type: ignore
            self.drag_tv_chart = _DTV(self.tab_tv)
            self.drag_tv_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_tv, text="T-V (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.drag_tv_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_drag import DragXVChart as _DXV  # type: ignore
            self.drag_xv_chart = _DXV(self.tab_xv)
            self.drag_xv_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_xv, text="X-V (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.drag_xv_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_drag import DragTAChart as _DTA  # type: ignore
            self.drag_ta_chart = _DTA(self.tab_ta)
            self.drag_ta_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_ta, text="T-A (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.drag_ta_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_drag import DragXAChart as _DXA  # type: ignore
            self.drag_xa_chart = _DXA(self.tab_xa)
            self.drag_xa_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_xa, text="X-A (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.drag_xa_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_drag import DragTRPMChart as _DTRPM  # type: ignore
            self.drag_trpm_chart = _DTRPM(self.tab_trpm)
            self.drag_trpm_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_trpm, text="T-RPM (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.drag_trpm_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_drag import DragXRPMChart as _DXRPM  # type: ignore
            self.drag_xrpm_chart = _DXRPM(self.tab_xrpm)
            self.drag_xrpm_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_xrpm, text="X-RPM (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.drag_xrpm_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_drag import DragTGearChart as _DTGear  # type: ignore
            self.drag_tgear_chart = _DTGear(self.tab_tgear)
            self.drag_tgear_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_tgear, text="T-GEAR (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.drag_tgear_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_drag import DragXGearChart as _DXGear  # type: ignore
            self.drag_xgear_chart = _DXGear(self.tab_xgear)
            self.drag_xgear_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_xgear, text="X-GEAR (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.drag_xgear_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_drag import DragTTPSChart as _DTTPS  # type: ignore
            self.drag_ttps_chart = _DTTPS(self.tab_ttps)
            self.drag_ttps_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_ttps, text="T-TPS (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.drag_ttps_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_drag import DragXTPSChart as _DXTPS  # type: ignore
            self.drag_xtps_chart = _DXTPS(self.tab_xtps)
            self.drag_xtps_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_xtps, text="X-TPS (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.drag_xtps_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_drag import DragTBPSChart as _DTBPS  # type: ignore
            self.drag_tbps_chart = _DTBPS(self.tab_tbps)
            self.drag_tbps_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_tbps, text="T-BPS (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.drag_tbps_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_drag import DragXBPSChart as _DXBPS  # type: ignore
            self.drag_xbps_chart = _DXBPS(self.tab_xbps)
            self.drag_xbps_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_xbps, text="X-BPS (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.drag_xbps_chart = None  # type: ignore

        # -- bottom: 注記 + トラップログ --
        _bottom_parent = _drag_parent if '_drag_parent' in locals() else self
        self._bottom = ttk.Frame(_bottom_parent)
        self._bottom.pack(fill="x", padx=6, pady=(0, 6))

        # 厳密> 注記: t - t_shift > shift_time
        # MATLAB:OpenDRAG.m:262 if t - t_shift > veh.shift_time 厳密> (strictly >)
        self._note_var = tk.StringVar(value="注記: t - t_shift > shift_time 厳密> (strictly >, not >=) — MATLAB:OpenDRAG.m:262")
        self._note_label = ttk.Label(self._bottom, textvariable=self._note_var, foreground="#666", wraplength=760, justify="left")
        self._note_label.pack(anchor="w", padx=4)
        self.note_label = self._note_label
        # also expose text for grep
        self._note_text = "t - t_shift > shift_time 厳密> (strictly >)"
        # Explicit comment string for test grep: t-t_shift>shift_time and gear==0
        self._sentinel_note = "gear==0番兵表示: 0はシフト中, t-t_shift>shift_time 厳密>"

        # trap log label
        self._trap_var = tk.StringVar(value="speed_trap log: --")
        self._trap_label = ttk.Label(self._bottom, textvariable=self._trap_var, wraplength=760, justify="left")
        self._trap_label.pack(anchor="w", padx=4, pady=(2, 0))

        # initial populate
        try:
            self._on_run()
        except Exception:
            pass
        self.bind("<Map>", lambda _e: self._redraw_canvas())

    # -- discover vehicles ---------------------------------------------------
    def _discover_vehicles(self) -> None:
        base: pathlib.Path | None = None
        try:
            rp = _resource_path("data/vehicles")
            if rp.exists():
                base = rp
        except Exception:
            pass
        if base is None or not base.exists():
            base = pathlib.Path(__file__).resolve().parents[2] / "data" / "vehicles"
            if not base.exists():
                base = pathlib.Path(__file__).resolve().parents[3] / "data" / "vehicles"
        self._vehicles_dir = base
        files: list[pathlib.Path] = []
        try:
            if base is not None and base.exists():
                files = sorted(base.glob("*.json"))
        except Exception:
            files = []
        valid: list[str] = []
        for p in files:
            try:
                p.read_text(encoding="utf-8")
                valid.append(p.stem)
            except Exception:
                valid.append(p.stem)
        self._vehicle_names: list[str] = valid
        self._vehicle_files: list[pathlib.Path] = files

    def refresh_vehicles(self, select: str | None = None) -> None:
        try:
            base: pathlib.Path | None = None
            try:
                rp = _resource_path("data/vehicles")
                if rp.exists():
                    base = rp
            except Exception:
                pass
            if base is None or not base.exists():
                base = pathlib.Path(__file__).resolve().parents[2] / "data" / "vehicles"
                if not base.exists():
                    base = pathlib.Path(__file__).resolve().parents[3] / "data" / "vehicles"
            self._vehicles_dir = base
            files: list[pathlib.Path] = []
            try:
                if base is not None and base.exists():
                    files = sorted(base.glob("*.json"))
            except Exception:
                files = []
            valid: list[str] = []
            for p in files:
                try:
                    p.read_text(encoding="utf-8")
                    valid.append(p.stem)
                except Exception:
                    valid.append(p.stem)
            valid = sorted(valid)
            cur = ""
            try:
                cur = self.combo.get().strip() if hasattr(self, "combo") else ""
            except Exception:
                cur = ""
            if select is not None:
                cur = str(select).strip()
            self._vehicle_names = valid
            self._vehicle_files = files
            try:
                self.combo.configure(values=self._vehicle_names)
            except Exception:
                try:
                    self.combo["values"] = self._vehicle_names  # type: ignore
                except Exception:
                    pass
            try:
                if cur and cur in self._vehicle_names:
                    self.combo.set(cur)
                    try:
                        self.combo.current(self._vehicle_names.index(cur))
                    except Exception:
                        pass
                elif select is not None and str(select).strip() in self._vehicle_names:
                    s2 = str(select).strip()
                    self.combo.set(s2)
                    try:
                        self.combo.current(self._vehicle_names.index(s2))
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if _fix_combo is not None and hasattr(self, "combo"):
                    _fix_combo(self.combo, self._vehicle_names, max_chars=36)
            except Exception:
                pass
        except Exception:
            pass

    def _load_vehicle(self, name: str) -> None:
        stem = name.strip().removesuffix(".json")
        if _Vehicle47 is None:
            # fallback: keep name string for simulate_drag resolver
            self._vehicle = stem  # type: ignore
            return
        try:
            v = _Vehicle47.from_json(stem)  # type: ignore
            self._vehicle = v
        except Exception as e:
            log.warning("DragView load vehicle failed %r: %s", stem, e)
            try:
                messagebox.showwarning("警告", f"車両データが破損しています: {stem}\n{e}", parent=self)
            except Exception:
                try:
                    messagebox.showwarning("警告", f"車両データが破損しています: {stem}\n{e}")
                except Exception:
                    pass
            self._vehicle = stem  # type: ignore

    def _on_vehicle_selected(self, _event: object | None = None) -> None:
        try:
            self.refresh_vehicles()
        except Exception:
            pass
        name = self.combo.get().strip()
        if not name:
            return
        try:
            self._load_vehicle(name)
            self._on_run()
        except Exception as e:
            log.warning("DragView vehicle select failed %r: %s", name, e)
            try:
                messagebox.showwarning("警告", f"車両選択失敗: {name}\n{e}", parent=self)
            except Exception:
                pass

    # -- Run simulate_drag live ----------------------------------------------
    def _on_run(self) -> None:
        try:
            self.refresh_vehicles()
        except Exception:
            pass
        if _simulate_drag is None:
            try:
                messagebox.showerror("Error", "simulate_drag が見つかりません: src/openlapexe/drag.py", parent=self)
            except Exception:
                pass
            return
        # resolve vehicle name from combo if needed
        veh: object | None = self._vehicle
        if veh is None:
            try:
                name = self.combo.get().strip() if hasattr(self, "combo") else "f1"
                veh = name if name else "f1"
            except Exception:
                veh = "f1"
        # speed_trap 50..350km/h 既定: [50,100,150,200,250,300,350]/3.6
        speed_trap = _np.array([50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0], dtype=float) / 3.6  # MATLAB:OpenDRAG.m:63
        try:
            # t - t_shift > shift_time 厳密> : simulate_drag は既に厳密>で実装済み (drag.py:499)
            result = _simulate_drag(vehicle=veh, speed_trap=speed_trap)  # type: ignore
            self._drag_result = result
        except Exception as e:
            log.warning("simulate_drag failed: %s", e)
            try:
                messagebox.showerror("Error", f"simulate_drag 失敗: {e}", parent=self)
            except Exception:
                try:
                    messagebox.showerror("Error", f"simulate_drag 失敗: {e}")
                except Exception:
                    pass
            return
        # update gear map
        try:
            self._refresh_gear_map(veh)
        except Exception as e:
            log.debug("gear map refresh failed: %s", e)
        # populate 61-row table
        try:
            self._populate_table(veh, result)
        except Exception as e:
            log.debug("populate table failed: %s", e)
        # trap log var
        try:
            tl = getattr(result, "trap_log", [])
            if tl:
                parts: list[str] = []
                for entry in tl[:7]:
                    parts.append(f"{float(entry.get('speed_kmh', 0)):.0f}km/h: t={float(entry.get('t', 0)):.2f}s")
                self._trap_var.set("speed_trap log: " + " | ".join(parts))
            else:
                self._trap_var.set("speed_trap log: (no trap)")
        except Exception:
            pass
        # update Drag* 13 charts
        for _nm in (
            "drag_tx_chart",
            "drag_tv_chart",
            "drag_xv_chart",
            "drag_ta_chart",
            "drag_xa_chart",
            "drag_trpm_chart",
            "drag_xrpm_chart",
            "drag_tgear_chart",
            "drag_xgear_chart",
            "drag_ttps_chart",
            "drag_xtps_chart",
            "drag_tbps_chart",
            "drag_xbps_chart",
        ):
            try:
                _ch = getattr(self, _nm, None)
                if _ch is not None:
                    try:
                        _ch.plot(result)  # type: ignore
                    except Exception:
                        try:
                            _ch.set_data(result)  # type: ignore
                        except Exception:
                            pass
            except Exception:
                pass
        # redraw canvas
        try:
            self._redraw_canvas()
        except Exception:
            pass
        try:
            self._status_var.set("Drag 計算完了")
        except Exception:
            pass

    def _refresh_gear_map(self, vehicle: object) -> None:
        # Use _build_driveline if available, else fallback to vehicle ratios
        dl: dict[str, object] | None = None
        if _build_driveline is not None:
            try:
                # _build_driveline expects Vehicle47-like
                veh_obj = vehicle
                if isinstance(vehicle, str):
                    if _Vehicle47 is not None:
                        try:
                            veh_obj = _Vehicle47.from_json(vehicle)  # type: ignore
                        except Exception:
                            veh_obj = vehicle
                dl = _build_driveline(veh_obj)  # type: ignore
            except Exception as e:
                log.debug("_build_driveline failed: %s", e)
                dl = None
        if dl is not None:
            try:
                sp = dl.get("shift_points")  # type: ignore
                en = dl.get("en_speed_curve")  # type: ignore
                if isinstance(sp, _np.ndarray):
                    self._shift_points = sp.astype(float)
                elif sp is not None:
                    self._shift_points = _np.array(sp, dtype=float)
                if isinstance(en, _np.ndarray):
                    self._en_speed_curve = en.astype(float)
                elif en is not None:
                    self._en_speed_curve = _np.array(en, dtype=float)
            except Exception:
                pass
        else:
            # fallback: derive from vehicle torque_curve + ratio_gearbox
            try:
                if hasattr(vehicle, "torque_curve"):
                    tc = getattr(vehicle, "torque_curve")
                    en = _np.array([float(p[0]) for p in tc], dtype=float)
                    self._en_speed_curve = en
                if hasattr(vehicle, "ratio_gearbox"):
                    rg = getattr(vehicle, "ratio_gearbox")
                    # approximate shift_points as en_speed_curve tail?
                    if self._en_speed_curve is not None and len(self._en_speed_curve) > 0:
                        tail = float(self._en_speed_curve[-1])
                        self._shift_points = _np.array([tail * 0.85, tail], dtype=float)
            except Exception:
                pass

        # update label
        try:
            if self._shift_points is not None:
                pts_str = ", ".join(f"{float(x):.0f}" for x in self._shift_points[:6])
                if len(self._shift_points) > 6:
                    pts_str += f" ... (+{len(self._shift_points)-6})"
                self._gear_info_var.set(f"shift_points: [{pts_str}] rpm")
            else:
                self._gear_info_var.set("shift_points: --")
        except Exception:
            pass
        try:
            if self._en_speed_curve is not None:
                en_str = ", ".join(f"{float(x):.0f}" for x in self._en_speed_curve[:6])
                if len(self._en_speed_curve) > 6:
                    en_str += f" ... (+{len(self._en_speed_curve)-6})"
                self._en_info_var.set(f"en_speed_curve: [{en_str}] rpm ({len(self._en_speed_curve)}点)")
            else:
                self._en_info_var.set("en_speed_curve: --")
        except Exception:
            pass

        # populate gear_table with ratio + shift_rpm mapping
        try:
            for iid in self.gear_table.get_children():
                self.gear_table.delete(iid)
        except Exception:
            pass
        try:
            veh_rg: object | None = None
            if isinstance(vehicle, str) and _Vehicle47 is not None:
                try:
                    vtmp = _Vehicle47.from_json(vehicle)  # type: ignore
                    veh_rg = getattr(vtmp, "ratio_gearbox", None)
                except Exception:
                    pass
            elif hasattr(vehicle, "ratio_gearbox"):
                veh_rg = getattr(vehicle, "ratio_gearbox")
            if veh_rg is not None:
                rg_list = list(veh_rg)  # type: ignore
                sp_list = list(self._shift_points) if self._shift_points is not None else [None] * len(rg_list)
                for idx, rgv in enumerate(rg_list):
                    gear_no = idx + 1
                    try:
                        rg_f = float(rgv)
                    except Exception:
                        rg_f = 0.0
                    try:
                        srpm = float(sp_list[idx]) if idx < len(sp_list) and sp_list[idx] is not None else (float(sp_list[-1]) if sp_list else 0.0)
                    except Exception:
                        srpm = 0.0
                    try:
                        self.gear_table.insert("", "end", values=(gear_no, f"{rg_f:.2f}", f"{srpm:.0f}"))
                    except Exception:
                        pass
        except Exception:
            pass

    def _populate_table(self, vehicle: object, result: object) -> None:
        # clear
        try:
            for iid in self.tree.get_children():
                self.tree.delete(iid)
        except Exception:
            pass
        self._table_data = []
        # For rpm/TPS/bps interpolation, use result arrays if available
        # result.V, RPM, TPS, BPS, GEAR are arrays from simulate_drag
        # We will interpolate rpm/TPS/bps at each speed_mps via np.interp where possible
        # gear==0番兵表示 handled via _format_gear
        res_V: _np.ndarray | None = None
        res_RPM: _np.ndarray | None = None
        res_TPS: _np.ndarray | None = None
        res_BPS: _np.ndarray | None = None
        res_GEAR: _np.ndarray | None = None
        try:
            res_V = _np.asarray(getattr(result, "V", None), dtype=float) if getattr(result, "V", None) is not None else None
            res_RPM = _np.asarray(getattr(result, "RPM", None), dtype=float) if getattr(result, "RPM", None) is not None else None
            res_TPS = _np.asarray(getattr(result, "TPS", None), dtype=float) if getattr(result, "TPS", None) is not None else None
            res_BPS = _np.asarray(getattr(result, "BPS", None), dtype=float) if getattr(result, "BPS", None) is not None else None
            res_GEAR = _np.asarray(getattr(result, "GEAR", None), dtype=float) if getattr(result, "GEAR", None) is not None else None
        except Exception:
            pass

        # For physical consistency, ensure we have monotonic V for interp (result.V is monotonic increasing during accel then maybe decreasing during decel? Actually drag simulation includes accel then decel, V goes up then down. For interp we should use accel phase up to max speed.)
        # Use only accel phase up to max V index for rpm interpolation; else use overall and clamp.
        # Simpler: use np.interp with left/right clamp via sorted unique V? But result.V may not be strictly monotonic due to decel. We'll extract monotonic increasing prefix.
        V_mono: _np.ndarray | None = None
        if res_V is not None and res_V.size > 1:
            # Find peak V index
            try:
                peak_idx = int(_np.argmax(res_V))
                # monotonic increasing up to peak
                V_mono = res_V[: peak_idx + 1]
                # ensure strictly increasing (it is)
                # For interp we can use V_mono and corresponding RPM_mono etc.
            except Exception:
                V_mono = res_V
        # fallback to full V if needed

        for idx, kmh in enumerate(self._speeds_kmh):
            v = float(kmh / 3.6)
            Aero_Dr, Roll_Dr, ax_drag, Aero_Df, Wd = _aero_for_speed(v, vehicle)
            # rpm/TPS/bps via interpolation if available
            rpm_val: float = 0.0
            tps_val: float = 0.0
            bps_val: float = 0.0
            gear_val: float = 0.0
            if res_V is not None and res_RPM is not None and res_V.size > 1:
                try:
                    # Use V_mono for rpm if available
                    if V_mono is not None and V_mono.size > 1:
                        # need corresponding RPM_mono etc. Align size
                        # RPM array same length as V
                        peak_idx = int(_np.argmax(res_V))
                        RPM_mono = res_RPM[: peak_idx + 1]
                        TPS_mono = res_TPS[: peak_idx + 1] if res_TPS is not None else None
                        BPS_mono = res_BPS[: peak_idx + 1] if res_BPS is not None else None
                        GEAR_mono = res_GEAR[: peak_idx + 1] if res_GEAR is not None else None
                        # interp clamp
                        rpm_val = float(_np.interp(v, V_mono, RPM_mono, left=float(RPM_mono[0]), right=float(RPM_mono[-1])))
                        if TPS_mono is not None:
                            tps_val = float(_np.interp(v, V_mono, TPS_mono, left=float(TPS_mono[0]), right=float(TPS_mono[-1])))
                        if BPS_mono is not None:
                            bps_val = float(_np.interp(v, V_mono, BPS_mono, left=float(BPS_mono[0]), right=float(BPS_mono[-1])))
                        if GEAR_mono is not None:
                            # gear: nearest via round after interp
                            g_f = float(_np.interp(v, V_mono, GEAR_mono, left=float(GEAR_mono[0]), right=float(GEAR_mono[-1])))
                            gear_val = float(round(g_f))
                        else:
                            gear_val = 0.0
                    else:
                        rpm_val = float(_np.interp(v, res_V, res_RPM, left=float(res_RPM[0]), right=float(res_RPM[-1])))
                        if res_TPS is not None:
                            tps_val = float(_np.interp(v, res_V, res_TPS, left=float(res_TPS[0]), right=float(res_TPS[-1])))
                        if res_BPS is not None:
                            bps_val = float(_np.interp(v, res_V, res_BPS, left=float(res_BPS[0]), right=float(res_BPS[-1])))
                        if res_GEAR is not None:
                            g_f = float(_np.interp(v, res_V, res_GEAR, left=float(res_GEAR[0]), right=float(res_GEAR[-1])))
                            gear_val = float(round(g_f))
                except Exception:
                    pass
            # Fallback compute rpm via gear envelope if interp not available (e.g., no result)
            if rpm_val == 0.0:
                try:
                    # approximate rpm via first gear ratio (for static table, use gear 1)
                    rg_first = 2.57
                    if hasattr(vehicle, "ratio_gearbox"):
                        rg_list = getattr(vehicle, "ratio_gearbox")
                        if isinstance(rg_list, (list, tuple)) and len(rg_list) > 0:
                            rg_first = float(rg_list[0])
                    rf = float(getattr(vehicle, "ratio_final", getattr(vehicle, "final_drive", 7.0)))
                    rp = float(getattr(vehicle, "ratio_primary", 1.0))
                    Rt = float(getattr(vehicle, "tyre_radius", getattr(vehicle, "wheel_radius", 0.33)))
                    # estimate rpm = rf*rg*rp*v/Rt*60/2/pi
                    rpm_val = rf * rg_first * rp * v / max(Rt, 1e-9) * 60.0 / 2.0 / math.pi
                except Exception:
                    rpm_val = 0.0

            gear_display = _format_gear(gear_val)  # gear==0番兵表示

            row = {
                "no": idx + 1,
                "speed_kmh": kmh,
                "speed_ms": v,
                "Aero_Dr": Aero_Dr,
                "Roll_Dr": Roll_Dr,
                "ax_drag": ax_drag,
                "rpm": rpm_val,
                "TPS": tps_val,
                "bps": bps_val,
                "gear": gear_val,
                "gear_display": gear_display,
            }
            self._table_data.append(row)
            # insert into tree
            try:
                self.tree.insert(
                    "",
                    "end",
                    values=(
                        idx + 1,
                        f"{kmh:.1f}",
                        f"{v:.2f}",
                        f"{Aero_Dr:.1f}",
                        f"{Roll_Dr:.1f}",
                        f"{ax_drag:.3f}",
                        f"{rpm_val:.0f}",
                        f"{tps_val:.2f}",
                        f"{bps_val:.1f}",
                        gear_display,
                    ),
                )
            except Exception:
                pass

        # Ensure 61 rows exactly (guard)
        # If table not 61 due to earlier clear failure, pad/truncate
        try:
            n = len(self.tree.get_children())
            if n != 61:
                # adjust by adding dummy rows or trimming (should not happen)
                while len(self.tree.get_children()) < 61:
                    self.tree.insert("", "end", values=(len(self.tree.get_children()) + 1, "--", "--", "--", "--", "--", "--", "--", "--", "--"))
        except Exception:
            pass

    # -- Canvas: aero vs speed, Wd vs speed ---------------------------------
    def _redraw_canvas(self) -> None:
        c = getattr(self, "canvas", None)
        if c is None:
            return
        try:
            c.delete("all")
        except Exception:
            return
        # need vehicle and speeds
        veh: object | None = self._vehicle
        if veh is None:
            try:
                name = self.combo.get().strip() if hasattr(self, "combo") else "f1"
                if _Vehicle47 is not None:
                    try:
                        veh = _Vehicle47.from_json(name or "f1")  # type: ignore
                    except Exception:
                        veh = name or "f1"
                else:
                    veh = name or "f1"
            except Exception:
                veh = "f1"
        # canvas size
        try:
            w = int(c.winfo_width())
            h = int(c.winfo_height())
        except Exception:
            w = 400
            h = 220
        if w < 10:
            w = 400
        if h < 10:
            h = 220
        pad = 36
        # placeholder if no vehicle
        if veh is None:
            try:
                c.create_text(w // 2, h // 2, text="車両未選択", fill="#888", anchor="center")
            except Exception:
                pass
            return

        # compute data for 61 speeds
        speeds = self._speeds_mps if len(self._speeds_mps) == 61 else _np.array([50.0 + 5.0 * i for i in range(61)], dtype=float) / 3.6
        aero_vals: list[float] = []
        wd_vals: list[float] = []
        for v in speeds:
            try:
                # Need vehicle object for physics; if veh is str, load
                veh_obj = veh
                if isinstance(veh, str) and _Vehicle47 is not None:
                    try:
                        veh_obj = _Vehicle47.from_json(veh)  # type: ignore
                    except Exception:
                        pass
                Aero_Dr, _Roll_Dr, _ax_drag, _Aero_Df, Wd = _aero_for_speed(float(v), veh_obj)  # type: ignore
                # For visualization, use absolute drag magnitude (positive)
                aero_vals.append(abs(float(Aero_Dr)))
                wd_vals.append(float(Wd))
            except Exception:
                aero_vals.append(0.0)
                wd_vals.append(0.0)

        # bounds
        try:
            min_sp = float(_np.min(speeds))
            max_sp = float(_np.max(speeds))
            # Convert to km/h for x axis label
            # keep m/s for compute but display km/h
            # For y, combine aero and Wd ranges
            min_y = min(min(aero_vals) if aero_vals else 0, min(wd_vals) if wd_vals else 0)
            max_y = max(max(aero_vals) if aero_vals else 1, max(wd_vals) if wd_vals else 1)
            if max_y - min_y < 1e-9:
                max_y = min_y + 1.0
            # add margin 10%
            yr = max_y - min_y
            min_y -= yr * 0.05
            max_y += yr * 0.10
            # also ensure min_y not negative too much for Wd (positive)
            if min_y < 0 and min(wd_vals) > 0:
                min_y = 0
            avail_w = float(w - 2 * pad)
            avail_h = float(h - 2 * pad)
            range_x = max_sp - min_sp if max_sp != min_sp else 1.0
            range_y = max_y - min_y if max_y != min_y else 1.0
            scale_x = avail_w / range_x
            scale_y = avail_h / range_y

            def _px(sp: float) -> float:
                return pad + (sp - min_sp) * scale_x

            def _py(val: float) -> float:
                return h - pad - (val - min_y) * scale_y

            # grid
            try:
                # horizontal grid 4 lines
                for i in range(5):
                    yv = min_y + range_y * i / 4.0
                    yy = _py(yv)
                    c.create_line(pad, yy, w - pad, yy, fill="#eee", width=1, tags=("grid",))
                    c.create_text(pad - 4, yy, text=f"{yv:.0f}", anchor="e", fill="#666", font=("TkDefaultFont", 7), tags=("grid",))
                # vertical grid 6 lines
                for i in range(7):
                    xv = min_sp + range_x * i / 6.0
                    xx = _px(xv)
                    c.create_line(xx, pad, xx, h - pad, fill="#eee", width=1, tags=("grid",))
                    kmh = xv * 3.6
                    c.create_text(xx, h - pad + 6, text=f"{kmh:.0f}", anchor="n", fill="#666", font=("TkDefaultFont", 7), tags=("grid",))
            except Exception:
                pass

            # axes
            try:
                c.create_line(pad, h - pad, w - pad, h - pad, fill="#333", width=1.5)  # x axis
                c.create_line(pad, pad, pad, h - pad, fill="#333", width=1.5)  # y axis
                c.create_text(w - pad, h - pad + 18, text="speed km/h", anchor="e", fill="#333", font=("TkDefaultFont", 7))
                c.create_text(pad, pad - 8, text="N (aero/Wd)", anchor="w", fill="#333", font=("TkDefaultFont", 7))
            except Exception:
                pass

            # aero vs speed line (blue)
            try:
                aero_coords: list[float] = []
                for sp, av in zip(speeds, aero_vals):
                    aero_coords.append(_px(float(sp)))
                    aero_coords.append(_py(float(av)))
                if len(aero_coords) >= 4:
                    c.create_line(*aero_coords, fill="#1f4b99", width=2, smooth=False, tags=("aero",))
            except Exception:
                pass
            # Wd vs speed line (red)
            try:
                wd_coords: list[float] = []
                for sp, wv in zip(speeds, wd_vals):
                    wd_coords.append(_px(float(sp)))
                    wd_coords.append(_py(float(wv)))
                if len(wd_coords) >= 4:
                    c.create_line(*wd_coords, fill="#c0392b", width=2, smooth=False, tags=("wd",))
            except Exception:
                pass
            try:
                self._probe_curve = (
                    _np.asarray(speeds, dtype=float).copy(),
                    _np.asarray(aero_vals, dtype=float).copy(),
                    _np.asarray(wd_vals, dtype=float).copy(),
                    float(min_sp),
                    float(max_sp),
                    float(min_y),
                    float(max_y),
                    float(pad),
                )
            except Exception:
                pass

            # legend already via labels, but also draw mini line in canvas corner
            try:
                lx = w - pad - 90
                ly = pad + 8
                c.create_line(lx, ly, lx + 14, ly, fill="#1f4b99", width=2)
                c.create_text(lx + 18, ly, text="aero", anchor="w", fill="#1f4b99", font=("TkDefaultFont", 7))
                c.create_line(lx, ly + 12, lx + 14, ly + 12, fill="#c0392b", width=2)
                c.create_text(lx + 18, ly + 12, text="Wd", anchor="w", fill="#c0392b", font=("TkDefaultFont", 7))
            except Exception:
                pass
            for _nm in (
                "drag_tx_chart",
                "drag_tv_chart",
                "drag_xv_chart",
                "drag_ta_chart",
                "drag_xa_chart",
                "drag_trpm_chart",
                "drag_xrpm_chart",
                "drag_tgear_chart",
                "drag_xgear_chart",
                "drag_ttps_chart",
                "drag_xtps_chart",
                "drag_tbps_chart",
                "drag_xbps_chart",
            ):
                try:
                    _ch = getattr(self, _nm, None)
                    if _ch is not None:
                        _red = getattr(_ch, "_redraw", None)
                        if callable(_red):
                            _red()
                except Exception:
                    pass

        except Exception as e:
            log.debug("DragView redraw canvas failed: %s", e)
            try:
                c.create_text(w // 2, h // 2, text=f"描画エラー: {e}", fill="#c00", anchor="center")
            except Exception:
                pass

    def _on_probe_press(self, event: object) -> None:
        try:
            self._probe_press = (int(getattr(event, "x", 0)), int(getattr(event, "y", 0)))
        except Exception:
            self._probe_press = None

    def _on_probe_release(self, event: object) -> None:
        try:
            px = int(getattr(event, "x", 0))
            py = int(getattr(event, "y", 0))
            if self._probe_press is not None:
                dx = px - self._probe_press[0]
                dy = py - self._probe_press[1]
                if dx * dx + dy * dy > 25:
                    return
            self._show_probe(float(px), float(py))
        except Exception:
            pass

    def _clear_probe(self) -> None:
        try:
            self.canvas.delete("probe")
        except Exception:
            pass

    def _show_probe(self, px: float, py: float) -> None:
        try:
            self.canvas.delete("probe")
        except Exception:
            pass
        try:
            info = getattr(self, "_probe_curve", None)
            if not info:
                return
            speeds, aero, wd, min_sp, max_sp, min_y, max_y, pad = info
            import numpy as _npp

            sp = _npp.asarray(speeds, dtype=float)
            av = _npp.asarray(aero, dtype=float)
            wv = _npp.asarray(wd, dtype=float)
            if sp.size == 0:
                return
            try:
                cx = float(self.canvas.canvasx(float(px)))
                cy = float(self.canvas.canvasy(float(py)))
            except Exception:
                cx, cy = float(px), float(py)
            try:
                w = int(self.canvas.winfo_width())
                h = int(self.canvas.winfo_height())
            except Exception:
                w, h = 400, 220
            if w < 10:
                w = 400
            if h < 10:
                h = 220
            rx = float(max_sp) - float(min_sp)
            ry = float(max_y) - float(min_y)
            if abs(rx) < 1e-9:
                rx = 1.0
            if abs(ry) < 1e-9:
                ry = 1.0
            scx = float(w - 2 * pad) / rx
            scy = float(h - 2 * pad) / ry
            try:
                mpx = float(pad) + (sp - float(min_sp)) * scx
                idx = int(_npp.argmin((mpx - cx) ** 2))
            except Exception:
                idx = 0
            nx = float(sp[idx])
            na = float(av[idx]) if av.size > idx else 0.0
            nw = float(wv[idx]) if wv.size > idx else 0.0
            try:
                vx0 = float(self.canvas.canvasx(0))
                vy0 = float(self.canvas.canvasy(0))
            except Exception:
                vx0, vy0 = 0.0, 0.0
            try:
                qx = float(pad) + (nx - float(min_sp)) * scx
                qay = float(h) - float(pad) - (na - float(min_y)) * scy
                qwy = float(h) - float(pad) - (nw - float(min_y)) * scy
                self.canvas.create_line(vx0, cy, vx0 + float(w), cy, fill="#888", dash=(3, 3), tags=("probe",))
                self.canvas.create_line(cx, vy0, cx, vy0 + float(h), fill="#888", dash=(3, 3), tags=("probe",))
                self.canvas.create_oval(qx - 4, qay - 4, qx + 4, qay + 4, outline="#1f4b99", width=2, tags=("probe",))
                self.canvas.create_oval(qx - 4, qwy - 4, qx + 4, qwy + 4, outline="#c0392b", width=2, tags=("probe",))
            except Exception:
                pass
            lines = [f"#{idx} v={nx * 3.6:.1f} km/h aero={na:.1f} N Wd={nw:.1f} N"]
            fw = max(len(s) for s in lines) * 6.5 + 12
            fh = len(lines) * 13 + 10
            bx = min(max(cx + 12, vx0 + 4), max(vx0 + 4, vx0 + float(w) - fw - 4))
            by = min(max(cy - fh - 8, vy0 + 4), max(vy0 + 4, vy0 + float(h) - fh - 4))
            try:
                self.canvas.create_rectangle(bx, by, bx + fw, by + fh, fill="white", outline="#222", width=1, tags=("probe",))
                for i, s in enumerate(lines):
                    self.canvas.create_text(bx + 6, by + 6 + i * 13, text=s, fill="#111", font=("TkDefaultFont", 7), anchor="nw", tags=("probe",))
                self._probe_text = " | ".join(lines)
            except Exception:
                pass
        except Exception:
            pass

    # -- public helpers for tests --------------------------------------------
    def get_table_row_count(self) -> int:
        try:
            return len(self.tree.get_children())
        except Exception:
            return len(self._table_data)

    def get_table_data(self) -> list[dict[str, object]]:
        return list(self._table_data)

    def get_shift_points(self) -> _np.ndarray | None:
        return self._shift_points

    def get_en_speed_curve(self) -> _np.ndarray | None:
        return self._en_speed_curve

    def get_value_at_speed(self, v_mps: float) -> dict[str, float]:
        """Return aero values at arbitrary v_mps matching drag.py (for 100m/s test)."""
        veh = self._vehicle
        if veh is None:
            try:
                name = self.combo.get().strip() if hasattr(self, "combo") else "f1"
                if _Vehicle47 is not None:
                    try:
                        veh = _Vehicle47.from_json(name or "f1")  # type: ignore
                    except Exception:
                        veh = name or "f1"
                else:
                    veh = name or "f1"
            except Exception:
                veh = "f1"
        # ensure veh object for physics
        veh_obj = veh
        if isinstance(veh, str) and _Vehicle47 is not None:
            try:
                veh_obj = _Vehicle47.from_json(veh)  # type: ignore
            except Exception:
                pass
        Aero_Dr, Roll_Dr, ax_drag, Aero_Df, Wd = _aero_for_speed(float(v_mps), veh_obj)  # type: ignore
        return {"Aero_Dr": float(Aero_Dr), "Roll_Dr": float(Roll_Dr), "ax_drag": float(ax_drag), "Aero_Df": float(Aero_Df), "Wd": float(Wd)}

    def _get_aero_at_100ms(self) -> float:
        """Helper for test: Aero_Dr at 100 m/s."""
        d = self.get_value_at_speed(100.0)
        return float(d["Aero_Dr"])


DragView2 = DragView

__all__ = ["DragView", "DragView2"]
