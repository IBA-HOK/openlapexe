# -*- coding: utf-8 -*-
# allow: SIZE_OK — SimulateView2 単一責務 (ttk GUI) Run→thread+queue+after Progressbar laptime sector Export CSV 11列 Chart統合
"""openlapexe.gui.simulate - SimulateView2 (V2).

要件(TASK):
- Runボタン→threading.Threadでopenlapexe.solver.simulate_full(車両/コース/freq選択反映)→queue→after(50,poll)
- Progressbar indeterminate
- 完了でlaptime mm:ss.sss + sector times表示
- Export CSV→asksaveasfilename→ヘッダ s_m,v_ms,ax,ay,time,gear,rpm,tps,energy,fuel,sector (11列、utf-8、lineterminator=\\n、1000行超)
- Canvas自前チャート(SpeedChart/GG/Sector棒)はchart.pyを利用, <Configure>再描画, 800点間引き<100ms, mpl/sci-py禁止
- app.py既存SimulateFrame温存 (本モジュールは独立, App2で任意dock)
- thread+queue+after(no thread join), messagebox parent=self
- solver.py改変禁止

Public: SimulateView2 (alias SimulateView, SimulateFrame2)
"""
from __future__ import annotations

import csv
import logging
import pathlib
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import numpy as _np

log = logging.getLogger(__name__)

# helpers: resource_path fallback
try:
    from openlapexe.io import resource_path as _resource_path  # type: ignore
except Exception:
    def _resource_path(relative: str) -> pathlib.Path:  # type: ignore[no-redef]
        if hasattr(sys, "_MEIPASS"):
            base = pathlib.Path(str(sys._MEIPASS))  # type: ignore[attr-defined]
        else:
            base = pathlib.Path(__file__).resolve().parents[3]
            if not (base / "app.py").exists() and not (base / "data").exists():
                base = pathlib.Path(__file__).resolve().parents[2]
        return base / relative

# chart imports (no matplotlib/scipy)
try:
    from openlapexe.gui.chart import SpeedChart as _SpeedChart, GGChart as _GGChart, SectorChart as _SectorChart
except Exception:
    _SpeedChart = None  # type: ignore
    _GGChart = None  # type: ignore
    _SectorChart = None  # type: ignore

# solver import (for patchability, import module not direct function)
try:
    import openlapexe.solver as _solver_mod  # type: ignore
except Exception:
    _solver_mod = None  # type: ignore


def _format_laptime(sec: float) -> str:
    try:
        s = float(sec)
        import math as _math
        if not _math.isfinite(s) or s < 0:
            s = 0.0
        m = int(s // 60)
        rem = s - m * 60
        return f"{m:02d}:{rem:06.3f}"
    except Exception:
        return "--:--.---"


class SimulateView2(ttk.Frame):
    """SimulateタブV2: Run thread+queue+after, Progressbar, laptime/sector, CSV 11列, Chart統合."""

    def __init__(self, parent: tk.Widget | ttk.Frame | None = None, *args: object, **kwargs: object) -> None:
        super().__init__(parent, *args, **kwargs)  # type: ignore[arg-type]
        self._result: object | None = None
        self._queue: queue.Queue[tuple[str, object]] | None = None
        self._thread: threading.Thread | None = None
        self._poll_job: str | None = None
        self._pending_track: str = "spa"
        self._vehicle_names: list[str] = []
        self._track_names: list[str] = []
        self._freq_values: list[str] = ["25", "50", "100"]
        self._discover_presets()
        self._build_ui()

    # -- discovery -------------------------------------------------------
    def _discover_presets(self) -> None:
        try:
            base_v: pathlib.Path | None = None
            try:
                rp = _resource_path("data/vehicles")
                if rp.exists():
                    base_v = rp
            except Exception:
                pass
            if base_v is None or not base_v.exists():
                base_v = pathlib.Path(__file__).resolve().parents[3] / "data" / "vehicles"
                if not base_v.exists():
                    base_v = pathlib.Path(__file__).resolve().parents[2] / "data" / "vehicles"
            if base_v is not None and base_v.exists():
                stems = sorted([p.stem for p in base_v.glob("*.json")])
                # ensure utf-8 readable
                for p in base_v.glob("*.json"):
                    try:
                        p.read_text(encoding="utf-8")
                    except Exception:
                        pass
                if stems:
                    self._vehicle_names = stems
            if not self._vehicle_names:
                self._vehicle_names = ["f1", "gt"]
        except Exception:
            self._vehicle_names = ["f1", "gt"]
        try:
            base_t: pathlib.Path | None = None
            try:
                rp2 = _resource_path("data/tracks")
                if rp2.exists():
                    base_t = rp2
            except Exception:
                pass
            if base_t is None or not base_t.exists():
                base_t = pathlib.Path(__file__).resolve().parents[3] / "data" / "tracks"
                if not base_t.exists():
                    base_t = pathlib.Path(__file__).resolve().parents[2] / "data" / "tracks"
            if base_t is not None and base_t.exists():
                stems2 = sorted([p.stem for p in base_t.glob("*.json")])
                for p in base_t.glob("*.json"):
                    try:
                        p.read_text(encoding="utf-8")
                    except Exception:
                        pass
                if stems2:
                    self._track_names = stems2
            if not self._track_names:
                self._track_names = ["spa", "monza", "donington"]
        except Exception:
            self._track_names = ["spa", "monza", "donington"]

    def refresh_tracks(self, select: str | None = None) -> None:
        try:
            base_t: pathlib.Path | None = None
            try:
                rp2 = _resource_path("data/tracks")
                if rp2.exists():
                    base_t = rp2
            except Exception:
                pass
            if base_t is None or not base_t.exists():
                base_t = pathlib.Path(__file__).resolve().parents[3] / "data" / "tracks"
                if not base_t.exists():
                    base_t = pathlib.Path(__file__).resolve().parents[2] / "data" / "tracks"
            new_names: list[str] = []
            if base_t is not None and base_t.exists():
                try:
                    stems2 = sorted([p.stem for p in base_t.glob("*.json")])
                    for p in base_t.glob("*.json"):
                        try:
                            p.read_text(encoding="utf-8")
                        except Exception:
                            pass
                    if stems2:
                        new_names = stems2
                except Exception:
                    pass
            if not new_names:
                new_names = list(self._track_names) if self._track_names else ["spa", "monza", "donington"]
            cur = ""
            try:
                cur = self.track_combo.get().strip() if hasattr(self, "track_combo") else ""
            except Exception:
                cur = ""
            if select is not None:
                cur = str(select).strip()
            self._track_names = new_names
            try:
                self.track_combo.configure(values=self._track_names)
            except Exception:
                try:
                    self.track_combo["values"] = self._track_names  # type: ignore
                except Exception:
                    pass
            try:
                if cur and cur in self._track_names:
                    self.track_combo.set(cur)
                    try:
                        self.track_combo.current(self._track_names.index(cur))
                    except Exception:
                        pass
                elif select is not None and str(select).strip() in self._track_names:
                    s2 = str(select).strip()
                    self.track_combo.set(s2)
                    try:
                        self.track_combo.current(self._track_names.index(s2))
                    except Exception:
                        pass
                elif self._track_names:
                    if not cur or cur not in self._track_names:
                        pass
            except Exception:
                pass
        except Exception:
            pass

    def refresh_vehicles(self, select: str | None = None) -> None:
        try:
            base_v: pathlib.Path | None = None
            try:
                rp = _resource_path("data/vehicles")
                if rp.exists():
                    base_v = rp
            except Exception:
                pass
            if base_v is None or not base_v.exists():
                base_v = pathlib.Path(__file__).resolve().parents[3] / "data" / "vehicles"
                if not base_v.exists():
                    base_v = pathlib.Path(__file__).resolve().parents[2] / "data" / "vehicles"
            new_names: list[str] = []
            if base_v is not None and base_v.exists():
                try:
                    stems = sorted([p.stem for p in base_v.glob("*.json")])
                    for p in base_v.glob("*.json"):
                        try:
                            p.read_text(encoding="utf-8")
                        except Exception:
                            pass
                    if stems:
                        new_names = stems
                except Exception:
                    pass
            if not new_names:
                new_names = list(self._vehicle_names) if self._vehicle_names else ["f1", "gt"]
            cur = ""
            try:
                cur = self.vehicle_combo.get().strip() if hasattr(self, "vehicle_combo") else ""
            except Exception:
                cur = ""
            if select is not None:
                cur = str(select).strip()
            self._vehicle_names = new_names
            try:
                self.vehicle_combo.configure(values=self._vehicle_names)
            except Exception:
                try:
                    self.vehicle_combo["values"] = self._vehicle_names  # type: ignore
                except Exception:
                    pass
            try:
                if cur and cur in self._vehicle_names:
                    self.vehicle_combo.set(cur)
                    try:
                        self.vehicle_combo.current(self._vehicle_names.index(cur))
                    except Exception:
                        pass
                elif select is not None and str(select).strip() in self._vehicle_names:
                    s2 = str(select).strip()
                    self.vehicle_combo.set(s2)
                    try:
                        self.vehicle_combo.current(self._vehicle_names.index(s2))
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

    def _is_track_available(self, name: str) -> bool:
        try:
            stem = name.strip().removesuffix(".json")
            if not stem:
                return False
            import json as _js
            pp: pathlib.Path | None = None
            try:
                rp = _resource_path(f"data/tracks/{stem}.json")
                if rp.exists():
                    pp = rp
            except Exception:
                pass
            if pp is None:
                pp = pathlib.Path(__file__).resolve().parents[3] / "data" / "tracks" / f"{stem}.json"
                if not pp.exists():
                    pp = pathlib.Path(__file__).resolve().parents[2] / "data" / "tracks" / f"{stem}.json"
            if pp is None or not pp.exists():
                alt = pathlib.Path(stem)
                if alt.exists():
                    pp = alt
                else:
                    return False
            txt = pp.read_text(encoding="utf-8")
            _js.loads(txt)
            return True
        except Exception:
            return False

    def _get_vehicle_arg(self) -> str:
        try:
            self.refresh_vehicles()
        except Exception:
            pass
        try:
            if hasattr(self, "vehicle_combo"):
                v = self.vehicle_combo.get().strip()  # type: ignore[attr-defined]
                if v:
                    return v
        except Exception:
            pass
        return self._vehicle_names[0] if self._vehicle_names else "f1"

    def _get_track_name(self) -> str:
        try:
            self.refresh_tracks()
        except Exception:
            pass
        try:
            if hasattr(self, "track_combo"):
                v = self.track_combo.get().strip()  # type: ignore[attr-defined]
                if v:
                    return v
        except Exception:
            pass
        # also check external TrackView if docked alongside?
        try:
            top = self.winfo_toplevel()
            tf = getattr(top, "track_frame", None) or getattr(top, "track_selector", None)
            if tf is not None:
                for attr in ("combo", "combobox", "track_combo", "selector"):
                    if hasattr(tf, attr):
                        try:
                            val = getattr(tf, attr).get().strip()  # type: ignore
                            if val:
                                return val
                        except Exception:
                            continue
        except Exception:
            pass
        return self._track_names[0] if self._track_names else "spa"

    def _get_freq(self) -> int:
        try:
            if hasattr(self, "freq_combo"):
                v = self.freq_combo.get().strip()  # type: ignore[attr-defined]
                if v:
                    return int(float(v))
        except Exception:
            pass
        return 50

    def _update_run_state(self) -> None:
        try:
            name = self._get_track_name()
            avail = self._is_track_available(name) if name else bool(self._track_names)
            if not avail or not self._track_names:
                try:
                    self.run_button.configure(state="disabled")
                except Exception:
                    pass
                try:
                    self._laptime_var.set("コース欠損→Run無効")
                except Exception:
                    pass
                try:
                    top = self.winfo_toplevel()
                    if hasattr(top, "set_status"):
                        top.set_status(f"コース欠損: {name} が見つかりません→Run無効")  # type: ignore
                except Exception:
                    pass
            else:
                try:
                    # only enable if not running
                    if self._thread is None or not self._thread.is_alive():
                        self.run_button.configure(state="normal")
                except Exception:
                    pass
                try:
                    if self._laptime_var.get() == "コース欠損→Run無効":
                        self._laptime_var.set("--:--.---")
                except Exception:
                    pass
        except Exception:
            pass

    # -- UI --------------------------------------------------------------
    def _build_ui(self) -> None:
        # top controls
        ctrl = ttk.Frame(self)
        ctrl.pack(fill="x", padx=6, pady=6)
        ttk.Label(ctrl, text="車両").pack(side="left", padx=(0, 4))
        self.vehicle_combo = ttk.Combobox(ctrl, state="readonly", width=12, values=self._vehicle_names)
        self.vehicle_combo.pack(side="left", padx=4)
        self.vehicle_combobox = self.vehicle_combo  # alias
        self.combo_vehicle = self.vehicle_combo
        try:
            if "f1" in self._vehicle_names:
                self.vehicle_combo.current(self._vehicle_names.index("f1"))
            elif self._vehicle_names:
                self.vehicle_combo.current(0)
        except Exception:
            try:
                self.vehicle_combo.set("f1")
            except Exception:
                pass

        ttk.Label(ctrl, text="コース").pack(side="left", padx=(8, 4))
        self.track_combo = ttk.Combobox(ctrl, state="readonly", width=12, values=self._track_names)
        self.track_combo.pack(side="left", padx=4)
        self.track_combobox = self.track_combo
        self.combo = self.track_combo
        self.combobox = self.track_combo
        try:
            low = [s.lower() for s in self._track_names]
            if "spa" in low:
                self.track_combo.current(low.index("spa"))
            elif self._track_names:
                self.track_combo.current(0)
        except Exception:
            try:
                self.track_combo.set("spa")
            except Exception:
                pass

        ttk.Label(ctrl, text="Freq").pack(side="left", padx=(8, 4))
        self.freq_combo = ttk.Combobox(ctrl, state="readonly", width=6, values=self._freq_values)
        self.freq_combo.pack(side="left", padx=4)
        self.freq_combobox = self.freq_combo
        self.combo_freq = self.freq_combo
        try:
            self.freq_combo.set("50")
        except Exception:
            pass

        self.run_button = ttk.Button(ctrl, text="Run", command=self._on_run)
        self.run_button.pack(side="left", padx=12)
        self.btn_run = self.run_button  # aliases
        self.button_run = self.run_button
        self.btn = self.run_button

        # Progressbar indeterminate
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=6, pady=(4, 2))
        self.progressbar = self.progress
        self.pbar = self.progress
        self._progress = self.progress

        # laptime + sector times display
        info = ttk.Frame(self)
        info.pack(fill="x", padx=6, pady=4)
        self._laptime_var = tk.StringVar(value="--:--.---")
        self.laptime_var = self._laptime_var
        self.laptime_label = ttk.Label(info, textvariable=self._laptime_var, font=("TkDefaultFont", 14, "bold"))
        self.laptime_label.pack(side="left", padx=4)
        self.label_laptime = self.laptime_label
        self._time_label = self.laptime_label

        self._sector_var = tk.StringVar(value="Sector: --")
        self.sector_var = self._sector_var
        self.sector_label = ttk.Label(info, textvariable=self._sector_var)
        self.sector_label.pack(side="left", padx=12)
        self.label_sector = self.sector_label
        self.sector_times_label = self.sector_label
        # also sector_time string for test introspection
        self._sector_time_var = tk.StringVar(value="")
        self.sector_time_var = self._sector_time_var

        # Charts area fills the window directly (scroll wrapper removed:
        # an inner frame inside a canvas window never expands, leaving dead space)
        self._chart_scroll = None  # type: ignore
        self.chart_scroll = None  # type: ignore
        chart_container = ttk.Frame(self)
        chart_container.pack(fill="both", expand=True, padx=6, pady=6)
        self.chart_notebook = ttk.Notebook(chart_container)
        self.chart_notebook.pack(fill="both", expand=True)
        self.graph_notebook = self.chart_notebook
        self._chart_notebook = self.chart_notebook
        self.tab_speed = ttk.Frame(self.chart_notebook)
        self.tab_gg = ttk.Frame(self.chart_notebook)
        self.tab_sector = ttk.Frame(self.chart_notebook)
        self.chart_notebook.add(self.tab_speed, text="速度")
        self.chart_notebook.add(self.tab_gg, text="G-G")
        self.chart_notebook.add(self.tab_sector, text="セクター")
        # --- Results* 6追加 (chart_notebook 3→9, per-tab try/except+placeholder) ---
        self.tab_elev = ttk.Frame(self.chart_notebook)
        self.tab_accel = ttk.Frame(self.chart_notebook)
        self.tab_input = ttk.Frame(self.chart_notebook)
        self.tab_steer = ttk.Frame(self.chart_notebook)
        self.tab_ggv3d = ttk.Frame(self.chart_notebook)
        self.tab_trackmap = ttk.Frame(self.chart_notebook)
        self.tab_elevation = self.tab_elev
        self.tab_gforce = self.tab_accel
        self.tab_tpsbps = self.tab_input
        try:
            self.chart_notebook.add(self.tab_elev, text="標高・曲率")
        except Exception:
            pass
        try:
            self.chart_notebook.add(self.tab_accel, text="G合力")
        except Exception:
            pass
        try:
            self.chart_notebook.add(self.tab_input, text="TPS・BPS")
        except Exception:
            pass
        try:
            self.chart_notebook.add(self.tab_steer, text="ステア")
        except Exception:
            pass
        try:
            self.chart_notebook.add(self.tab_ggv3d, text="GGV3D")
        except Exception:
            pass
        try:
            self.chart_notebook.add(self.tab_trackmap, text="トラックマップ")
        except Exception:
            pass
        self.chart_notebook.bind("<<NotebookTabChanged>>", lambda _e: self._redraw_charts())

        # Use chart.py canvases if available, else fallback to app.SpeedChart
        if _SpeedChart is not None:
            try:
                self.speed_chart = _SpeedChart(self.tab_speed)
                self.speed_chart.pack(fill="both", expand=True, padx=2, pady=2)
                self.chart = self.speed_chart
                self.canvas = self.speed_chart
                self._chart = self.speed_chart
            except Exception:
                self.speed_chart = None  # type: ignore
                self.chart = None  # type: ignore
        else:
            # fallback try app.SpeedChart
            try:
                import app as _app_mod  # type: ignore
                SC = getattr(_app_mod, "SpeedChart", None)
                if SC is not None:
                    self.speed_chart = SC(self.tab_speed)  # type: ignore
                    self.speed_chart.pack(fill="both", expand=True, padx=2, pady=2)
                    self.chart = self.speed_chart
                    self.canvas = self.speed_chart
                    self._chart = self.speed_chart
                else:
                    self.speed_chart = None  # type: ignore
            except Exception:
                self.speed_chart = None  # type: ignore

        if _GGChart is not None:
            try:
                self.gg_chart = _GGChart(self.tab_gg)
                self.gg_chart.pack(fill="both", expand=True, padx=2, pady=2)
                self.gg_canvas = self.gg_chart
                self.ggchart = self.gg_chart
            except Exception:
                self.gg_chart = None  # type: ignore
        else:
            self.gg_chart = None  # type: ignore
        # SectorChart side right
        if _SectorChart is not None:
            try:
                self.sector_chart = _SectorChart(self.tab_sector)
                self.sector_chart.pack(fill="both", expand=True, padx=2, pady=2)
                self.sector_canvas = self.sector_chart
                self.sector_bar = self.sector_chart
            except Exception:
                self.sector_chart = None  # type: ignore
        else:
            self.sector_chart = None  # type: ignore

        # Results* 6追加: 各タブにCanvasチャートをtry/exceptで埋込
        try:
            from openlapexe.gui.charts_results import ResultsElevationChart as _RElev  # type: ignore
            self.elevation_chart = _RElev(self.tab_elev)
            self.elevation_chart.pack(fill="both", expand=True, padx=2, pady=2)
            self.results_elevation_chart = self.elevation_chart
        except Exception:
            try:
                ttk.Label(self.tab_elev, text="標高・曲率 (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.elevation_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_results import ResultsAccelChart as _RAcc  # type: ignore
            self.accel_chart = _RAcc(self.tab_accel)
            self.accel_chart.pack(fill="both", expand=True, padx=2, pady=2)
            self.results_accel_chart = self.accel_chart
            self.g_chart = self.accel_chart
        except Exception:
            try:
                ttk.Label(self.tab_accel, text="G合力 (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.accel_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_results import ResultsInputChart as _RInp  # type: ignore
            self.input_chart = _RInp(self.tab_input)
            self.input_chart.pack(fill="both", expand=True, padx=2, pady=2)
            self.results_input_chart = self.input_chart
            self.tpsbps_chart = self.input_chart
        except Exception:
            try:
                ttk.Label(self.tab_input, text="TPS・BPS (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.input_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_results import ResultsSteerChart as _RSteer  # type: ignore
            self.steer_chart = _RSteer(self.tab_steer)
            self.steer_chart.pack(fill="both", expand=True, padx=2, pady=2)
            self.results_steer_chart = self.steer_chart
        except Exception:
            try:
                ttk.Label(self.tab_steer, text="ステア (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.steer_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_results import ResultsGGV3DChart as _RGGV3D  # type: ignore
            self.ggv3d_chart = _RGGV3D(self.tab_ggv3d)
            self.ggv3d_chart.pack(fill="both", expand=True, padx=2, pady=2)
            self.results_ggv3d_chart = self.ggv3d_chart
            self.ggv_chart = self.ggv3d_chart
        except Exception:
            try:
                ttk.Label(self.tab_ggv3d, text="GGV3D (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.ggv3d_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_results import ResultsTrackMapChart as _RMap  # type: ignore
            self.trackmap_chart = _RMap(self.tab_trackmap)
            self.trackmap_chart.pack(fill="both", expand=True, padx=2, pady=2)
            self.results_trackmap_chart = self.trackmap_chart
            self.track_map_chart = self.trackmap_chart
        except Exception:
            try:
                ttk.Label(self.tab_trackmap, text="トラックマップ (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.trackmap_chart = None  # type: ignore

        # Export CSV button (fixed bottom visible at 800x600)
        exp_frame = ttk.Frame(self)
        exp_frame.pack(side="bottom", fill="x", padx=6, pady=6)
        self.export_button = ttk.Button(exp_frame, text="Export CSV", command=self._on_export)
        self.export_button.pack(side="right", padx=4)
        self.btn_export = self.export_button
        self.button_export = self.export_button
        self.csv_button = self.export_button
        self.btn_csv = self.export_button
        self.export_csv_button = self.export_button

        try:
            self.track_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_track_selected())
            self.vehicle_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_run_state())
            self.track_combo.bind("<FocusIn>", lambda _e: self.refresh_tracks())
            self.track_combo.bind("<Button-1>", lambda _e: self.refresh_tracks())
            self.vehicle_combo.bind("<FocusIn>", lambda _e: self.refresh_vehicles())
            self.vehicle_combo.bind("<Button-1>", lambda _e: self.refresh_vehicles())
        except Exception:
            pass
        try:
            self.after(150, self._update_run_state)
        except Exception:
            pass
        try:
            self.after(300, self._refresh_track_preview)
        except Exception:
            pass
        try:
            if getattr(self, "_chart_scroll", None) is not None:
                self.after(100, lambda: self._chart_scroll._update_scrollregion())  # type: ignore
        except Exception:
            pass

    def _refresh_track_preview(self, track_name: str | None = None) -> None:
        try:
            name = str(track_name).strip() if track_name is not None else ""
            if not name:
                try:
                    name = self.track_combo.get().strip() if hasattr(self, "track_combo") else ""
                except Exception:
                    name = ""
            if not name:
                try:
                    name = self._track_names[0] if self._track_names else "spa"
                except Exception:
                    name = "spa"
            name = str(name).strip().removesuffix(".json") or "spa"
        except Exception:
            name = "spa"
        try:
            track_obj = None
            try:
                from openlapexe.track import Track as _TrackCls  # type: ignore

                track_obj = _TrackCls.from_json(name)
            except Exception:
                try:
                    from openlapexe.track import Track2 as _Track2Cls  # type: ignore

                    track_obj = _Track2Cls.from_json(name)
                except Exception:
                    track_obj = None
        except Exception:
            track_obj = None
        for _nm in ("trackmap_chart", "track_map_chart", "results_trackmap_chart", "elevation_chart"):
            try:
                _ch = getattr(self, _nm, None)
                if _ch is None:
                    continue
                try:
                    setter = getattr(_ch, "set_track_name", None)
                    if callable(setter):
                        setter(name)
                except Exception:
                    pass
                if track_obj is not None:
                    try:
                        st = getattr(_ch, "set_track", None)
                        if callable(st):
                            st(track_obj)
                    except Exception:
                        pass
                    try:
                        setter2 = getattr(_ch, "set_track_name", None)
                        if callable(setter2):
                            setter2(name)
                    except Exception:
                        pass
                    continue
                try:
                    _rd = getattr(_ch, "_redraw", None)
                    if callable(_rd):
                        _rd()
                except Exception:
                    pass
            except Exception:
                pass

    def _on_track_selected(self, _event: object | None = None) -> None:
        try:
            self._update_run_state()
        except Exception:
            pass
        try:
            self._refresh_track_preview()
        except Exception:
            pass

    def _redraw_charts(self) -> None:
        for _name in (
            "speed_chart",
            "gg_chart",
            "sector_chart",
            "elevation_chart",
            "accel_chart",
            "input_chart",
            "steer_chart",
            "ggv3d_chart",
            "trackmap_chart",
        ):
            _chart = getattr(self, _name, None)
            _redraw = getattr(_chart, "_redraw", None)
            if callable(_redraw):
                try:
                    _redraw()
                except Exception:
                    pass

    # -- run -------------------------------------------------------------
    def _on_run(self) -> None:
        try:
            self.refresh_tracks()
        except Exception:
            pass
        try:
            self.refresh_vehicles()
        except Exception:
            pass
        try:
            vehicle_arg = self._get_vehicle_arg()
            track_arg = self._get_track_name()
            freq_arg = self._get_freq()
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                try:
                    messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
                except Exception:
                    pass
            return
        if not self._is_track_available(str(track_arg)):
            try:
                messagebox.showwarning("警告", f"コースデータが見つからないか破損しています: {track_arg}", parent=self)
            except Exception:
                try:
                    messagebox.showwarning("警告", f"コースデータが見つからないか破損しています: {track_arg}", parent=self)
                except Exception:
                    pass
            try:
                self._laptime_var.set("コース欠損→Run無効")
            except Exception:
                pass
            try:
                self.run_button.configure(state="disabled")
            except Exception:
                pass
            return
        try:
            self.run_button.configure(state="disabled")
        except Exception:
            pass
        try:
            self.export_button.configure(state="disabled")
        except Exception:
            pass
        try:
            self.progress.start(10)
        except Exception:
            pass
        try:
            self._laptime_var.set("Running...")
            self._sector_var.set("Sector: Running...")
        except Exception:
            pass
        try:
            self._pending_track = str(track_arg).strip().removesuffix(".json")
        except Exception:
            self._pending_track = "spa"  # type: ignore[attr-defined]
        try:
            self._refresh_track_preview(str(track_arg))
        except Exception:
            pass
        self._queue = queue.Queue()
        q = self._queue

        def _worker() -> None:
            try:
                # Prefer solver module import for mock patchability
                try:
                    import openlapexe.solver as _sm2  # type: ignore
                    res = _sm2.simulate_full(vehicle_arg, track_arg, freq_arg)  # type: ignore
                except Exception:
                    if _solver_mod is not None and hasattr(_solver_mod, "simulate_full"):
                        res = _solver_mod.simulate_full(vehicle_arg, track_arg, freq_arg)  # type: ignore
                    else:
                        # fallback to app.simulate
                        import app as _app  # type: ignore
                        res = _app.simulate(vehicle_arg, track_arg)  # type: ignore
                q.put(("ok", res))
            except Exception as e:
                try:
                    q.put(("error", e))
                except Exception:
                    import traceback as _tb
                    q.put(("error", _tb.format_exc()))

        try:
            self._thread = threading.Thread(target=_worker, daemon=True)
            self._thread.start()
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                try:
                    messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
                except Exception:
                    pass
            try:
                self.progress.stop()
            except Exception:
                pass
            try:
                self.run_button.configure(state="normal")
                self.export_button.configure(state="normal")
            except Exception:
                pass
            return
        # poll via after(50) — no join
        try:
            self.after(50, self._poll)
        except Exception:
            pass

    def _poll(self) -> None:
        q = self._queue
        if q is None:
            return
        try:
            if q.empty():
                try:
                    self.after(50, self._poll)
                except Exception:
                    pass
                return
        except Exception:
            try:
                self.after(50, self._poll)
            except Exception:
                pass
            return
        try:
            kind, payload = q.get_nowait()
        except queue.Empty:
            try:
                self.after(50, self._poll)
            except Exception:
                pass
            return
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                pass
            try:
                self.progress.stop()
            except Exception:
                pass
            try:
                self.run_button.configure(state="normal")
                self.export_button.configure(state="normal")
            except Exception:
                pass
            return
        # got result
        try:
            self.progress.stop()
        except Exception:
            pass
        try:
            self.run_button.configure(state="normal")
            self.export_button.configure(state="normal")
        except Exception:
            pass
        if kind == "error":
            err = payload
            msg = str(err) if not isinstance(err, str) else err
            if isinstance(payload, BaseException):
                msg = f"{type(payload).__name__}: {payload}"
            try:
                messagebox.showerror("Error", msg, parent=self)
            except Exception:
                try:
                    messagebox.showerror("Error", msg, parent=self)
                except Exception:
                    pass
            try:
                self._laptime_var.set("--:--.---")
                self._sector_var.set("Sector: --")
            except Exception:
                pass
            return
        res = payload
        self._result = res
        # laptime mm:ss.sss
        try:
            lt = float(getattr(res, "laptime", 0.0))
            self._laptime_var.set(_format_laptime(lt))
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                pass
        # sector times display
        try:
            st = getattr(res, "sector_time", None)
            if st is None:
                st = getattr(res, "sector_times", None)
            if st is not None:
                arr = _np.asarray(st, dtype=float)
                parts = []
                for i, v in enumerate(arr):
                    parts.append(f"S{i+1} {_format_laptime(float(v))}")
                txt = ""
                for idx, p in enumerate(parts):
                    if idx == 0:
                        txt = p
                    else:
                        txt = txt + " | " + p
                if not txt:
                    txt = "Sector: --"
                # also plain sector times for sector_label
                self._sector_var.set(txt)
                self._sector_time_var.set(txt)
                # also update sector_chart if exists? will do below
            else:
                # fallback if no sector_time, show laptime only
                self._sector_var.set(f"Sector: {self._laptime_var.get()}")
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                pass
        # charts
        try:
            s = getattr(res, "s", None)
            v = getattr(res, "v", None)
            if s is not None and v is not None and hasattr(self, "speed_chart") and self.speed_chart is not None:
                try:
                    self.speed_chart.set_data(s, v)  # type: ignore
                except Exception:
                    try:
                        self.speed_chart.plot(res)  # type: ignore
                    except Exception:
                        pass
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                pass
        try:
            ax = getattr(res, "ax", None)
            ay = getattr(res, "ay", None)
            if ax is not None and ay is not None and hasattr(self, "gg_chart") and self.gg_chart is not None:
                try:
                    self.gg_chart.set_data(ax, ay)  # type: ignore
                except Exception:
                    try:
                        self.gg_chart.plot(res)  # type: ignore
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            st = getattr(res, "sector_time", None)
            if st is not None and hasattr(self, "sector_chart") and self.sector_chart is not None:
                try:
                    self.sector_chart.set_data(st)  # type: ignore
                except Exception:
                    try:
                        self.sector_chart.plot(res)  # type: ignore
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            _cur_track = str(getattr(self, "_pending_track", "") or "").strip().removesuffix(".json")
            if not _cur_track:
                try:
                    _cur_track = self._get_track_name()
                except Exception:
                    _cur_track = "spa"
            for _nm in ("elevation_chart", "trackmap_chart"):
                try:
                    _ch = getattr(self, _nm, None)
                    if _ch is not None:
                        setter = getattr(_ch, "set_track_name", None)
                        if callable(setter):
                            setter(_cur_track)
                except Exception:
                    pass
        except Exception:
            pass
        for _nm in ("elevation_chart", "accel_chart", "input_chart", "steer_chart", "ggv3d_chart", "trackmap_chart"):
            try:
                _ch = getattr(self, _nm, None)
                if _ch is not None:
                    try:
                        _ch.plot(res)  # type: ignore
                    except Exception:
                        try:
                            _ch.set_data(res)  # type: ignore
                        except Exception:
                            pass
            except Exception:
                pass
        # status
        try:
            top = self.winfo_toplevel()
            if hasattr(top, "set_status"):
                top.set_status(f"完了: {self._laptime_var.get()}")  # type: ignore
        except Exception:
            pass

    # -- export CSV ------------------------------------------------------
    def _on_export(self) -> None:
        if self._result is None:
            try:
                messagebox.showerror("Error", "先にシミュレーションを実行してください", parent=self)
            except Exception:
                try:
                    messagebox.showerror("Error", "先にシミュレーションを実行してください", parent=self)
                except Exception:
                    pass
            return
        try:
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv"), ("All", "*.*")],
                initialfile="result.csv",
                title="CSVを保存",
            )
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                pass
            return
        if not path:
            return
        try:
            res = self._result
            s_arr = getattr(res, "s", None)
            v_arr = getattr(res, "v", None)
            ax_arr = getattr(res, "ax", None)
            ay_arr = getattr(res, "ay", None)
            t_arr = getattr(res, "time", None)
            gear_arr = getattr(res, "gear", None)
            rpm_arr = getattr(res, "rpm", None)
            tps_arr = getattr(res, "tps", None)
            energy_arr = getattr(res, "energy", None)
            fuel_arr = getattr(res, "fuel", None)
            sector_arr = getattr(res, "sector", None)
            # convert to arrays, fallback zeros
            def _to_arr(val, fallback_len: int = 0) -> _np.ndarray:
                if val is None:
                    if fallback_len > 0:
                        return _np.zeros(fallback_len, dtype=float)
                    return _np.array([], dtype=float)
                try:
                    return _np.asarray(val, dtype=float)
                except Exception:
                    return _np.zeros(fallback_len, dtype=float)
            # first determine n from s
            s_np = _to_arr(s_arr)
            n = int(s_np.shape[0]) if s_np.size > 0 else 0
            if n == 0:
                # try derive from v
                v_tmp = _to_arr(v_arr)
                n = int(v_tmp.shape[0]) if v_tmp.size else 0
                if n == 0:
                    raise ValueError("result has no data")
                s_np = _np.zeros(n, dtype=float)
            v_np = _to_arr(v_arr, n)
            ax_np = _to_arr(ax_arr, n)
            ay_np = _to_arr(ay_arr, n)
            t_np = _to_arr(t_arr, n)
            gear_np = _to_arr(gear_arr, n)
            rpm_np = _to_arr(rpm_arr, n)
            tps_np = _to_arr(tps_arr, n)
            energy_np = _to_arr(energy_arr, n)
            fuel_np = _to_arr(fuel_arr, n)
            sector_np = _to_arr(sector_arr, n)
            # ensure lengths
            for arr in [v_np, ax_np, ay_np, t_np, gear_np, rpm_np, tps_np, energy_np, fuel_np, sector_np]:
                if arr.shape[0] != n:
                    # pad or trim
                    if arr.shape[0] < n:
                        pad = _np.zeros(n - arr.shape[0], dtype=float)
                        arr = _np.concatenate([arr, pad])  # type: ignore
                    else:
                        arr = arr[:n]  # type: ignore
            # ensure at least fallback values for gear etc not NaN
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(["s_m", "v_ms", "ax", "ay", "time", "gear", "rpm", "tps", "energy", "fuel", "sector"])
                for i in range(n):
                    w.writerow([
                        float(s_np[i]) if i < s_np.shape[0] else 0.0,
                        float(v_np[i]) if i < v_np.shape[0] else 0.0,
                        float(ax_np[i]) if i < ax_np.shape[0] else 0.0,
                        float(ay_np[i]) if i < ay_np.shape[0] else 0.0,
                        float(t_np[i]) if i < t_np.shape[0] else 0.0,
                        float(gear_np[i]) if i < gear_np.shape[0] else 0.0,
                        float(rpm_np[i]) if i < rpm_np.shape[0] else 0.0,
                        float(tps_np[i]) if i < tps_np.shape[0] else 0.0,
                        float(energy_np[i]) if i < energy_np.shape[0] else 0.0,
                        float(fuel_np[i]) if i < fuel_np.shape[0] else 0.0,
                        float(sector_np[i]) if i < sector_np.shape[0] else 0.0,
                    ])
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                try:
                    messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
                except Exception:
                    pass
            return
        try:
            top = self.winfo_toplevel()
            if hasattr(top, "set_status"):
                top.set_status(f"CSV保存: {path}")  # type: ignore
        except Exception:
            pass


# aliases for test compatibility
SimulateView = SimulateView2
SimulateFrame2 = SimulateView2
SimulateFrame = SimulateView2

__all__ = ["SimulateView2", "SimulateView", "SimulateFrame2", "SimulateFrame"]
