# -*- coding: utf-8 -*-
"""openlapexe.gui.track_view - Track2ビュー (Canvas自前, matplotlib禁止).

Track2 (banking_rad/grip_factor/sector_id/logged) を表示:
- tk.Canvas 中心線 + banking色分け + grip濃淡 + sector区間線 + apex赤点
- 自動スケール (bounds→scale→center+ Y flip)
- 800点間引き <100ms (スライス薄化)
- <Configure> 再描画
- sectorテーブル読取表示
- resource_path 利用 (data/tracks 発見)
- app.py TrackFrame 温存 (本モジュールは独立)

Public: TrackView2 (alias TrackView)
"""
from __future__ import annotations

import logging
import pathlib
import time
import tkinter as tk
from tkinter import ttk, messagebox
import math

try:
    from openlapexe.gui.combobox_fix import fix_combobox as _fix_combo, fix_treeview_horizontal as _fix_tree_h  # type: ignore
except Exception:
    _fix_combo = None  # type: ignore
    _fix_tree_h = None  # type: ignore

try:
    from openlapexe.io import resource_path as _resource_path  # type: ignore
except Exception:  # fallback
    import sys

    def _resource_path(relative: str) -> pathlib.Path:  # type: ignore[no-redef]
        if hasattr(sys, "_MEIPASS"):
            base = pathlib.Path(str(sys._MEIPASS))  # type: ignore[attr-defined]
        else:
            base = pathlib.Path(__file__).resolve().parents[3]
            if not (base / "app.py").exists() and not (base / "data").exists():
                base = pathlib.Path(__file__).resolve().parents[2]
        return base / relative

try:
    from openlapexe.track import Track, Track2  # type: ignore
except Exception:
    Track = None  # type: ignore
    Track2 = None  # type: ignore

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# helpers: color mapping
# ---------------------------------------------------------------------------

def _banking_to_color(b: float) -> str:
    """Map banking_rad to hex color. Negative->blue, zero->#1f4b99, positive->red."""
    # clamp to +/- 0.12 rad (~6.9 deg) typical banking max; beyond -> clamp
    lo = -0.12
    hi = 0.12
    if b < lo:
        b = lo
    if b > hi:
        b = hi
    # normalize 0..1
    t = (b - lo) / (hi - lo) if hi != lo else 0.5
    # Interpolate: 0 => steel blue #2a5fb0, 0.5 => #1f4b99 (mid), 1 => #c0392b (red)
    # Piecewise linear
    if t < 0.5:
        # 0..0.5: #2a5fb0 -> #1f4b99
        f = t / 0.5
        r1, g1, b1 = 0x2A, 0x5F, 0xB0
        r2, g2, b2 = 0x1F, 0x4B, 0x99
        r = int(r1 + (r2 - r1) * f)
        g = int(g1 + (g2 - g1) * f)
        bl = int(b1 + (b2 - b1) * f)
    else:
        f = (t - 0.5) / 0.5
        r1, g1, b1 = 0x1F, 0x4B, 0x99
        r2, g2, b2 = 0xC0, 0x39, 0x2B
        r = int(r1 + (r2 - r1) * f)
        g = int(g1 + (g2 - g1) * f)
        bl = int(b1 + (b2 - b1) * f)
    return f"#{r:02x}{g:02x}{bl:02x}"


def _grip_to_width(g: float) -> int:
    """Map grip_factor to line width (濃淡代用: 太さ)."""
    # grip typically 0.85..1.15, nominal 1.0 -> width 2
    try:
        gv = float(g)
    except Exception:
        gv = 1.0
    # clamp 0.7..1.3
    if gv < 0.7:
        gv = 0.7
    if gv > 1.3:
        gv = 1.3
    # width 1..4
    w = 1.2 + (gv - 0.7) * (2.8 / 0.6)
    # round to at least 1
    wi = int(round(w))
    if wi < 1:
        wi = 1
    if wi > 5:
        wi = 5
    return wi


def _grip_to_alpha_color(base_hex: str, g: float) -> str:
    """Blend base color with white/black based on grip for 濃淡 visual."""
    # low grip -> lighten, high grip -> darken slightly
    # simple: grip 1.0 keep base, <1 lighten towards white, >1 darken 10%
    try:
        gv = float(g)
    except Exception:
        return base_hex
    if abs(gv - 1.0) < 1e-9:
        return base_hex
    # parse
    try:
        r = int(base_hex[1:3], 16)
        gg = int(base_hex[3:5], 16)
        bl = int(base_hex[5:7], 16)
    except Exception:
        return base_hex
    if gv < 1.0:
        # lighten: mix with white proportion (1-gv)*0.6
        p = (1.0 - gv) * 0.6
        if p > 0.55:
            p = 0.55
        r = int(r + (255 - r) * p)
        gg = int(gg + (255 - gg) * p)
        bl = int(bl + (255 - bl) * p)
    else:
        # darken: mix with black proportion (gv-1)*0.4
        p = (gv - 1.0) * 0.4
        if p > 0.3:
            p = 0.3
        r = int(r * (1 - p))
        gg = int(gg * (1 - p))
        bl = int(bl * (1 - p))
    return f"#{r:02x}{gg:02x}{bl:02x}"


# ---------------------------------------------------------------------------
# TrackView2
# ---------------------------------------------------------------------------
class TrackView2(ttk.Frame):
    """Track2ビュー: Track2 の可視化 Canvas + sectorテーブル.

    要件:
    - tk.Canvas 中心線 + banking色分け + grip濃淡 + sector区間線 + apex赤点
    - 自動スケール (boundsからscale算出, center+ Y反転)
    - 800点間引き <100ms
    - <Configure> 再描画
    - sectorテーブル読取表示
    - resource_path で data/tracks 発見
    """

    def __init__(self, parent: tk.Widget | ttk.Frame, *args: object, **kwargs: object) -> None:
        super().__init__(parent, *args, **kwargs)  # type: ignore[arg-type]
        self._track: object | None = None
        self._track_files: list[pathlib.Path] = []
        self._track_stems: list[str] = []
        self._last_draw_ms: float = 0.0
        self._discover_tracks()

        # -- top row: combobox + labels ---------------------------------
        self._ctrl = ttk.Frame(self)
        self._ctrl.pack(side="top", fill="x", padx=6, pady=(6, 4))

        ttk.Label(self._ctrl, text="コース選択").pack(side="left", padx=(0, 6))

        self.combo = ttk.Combobox(self._ctrl, state="readonly", width=22, values=self._track_stems)
        self.combobox = self.combo  # alias
        self.track_combo = self.combo
        self.selector = self.combo
        self.combo.pack(side="left", padx=4)
        self.combo.bind("<<ComboboxSelected>>", self._on_track_selected)
        try:
            self.combo.bind("<FocusIn>", lambda _e: self.refresh_tracks())
            self.combo.bind("<Button-1>", lambda _e: self.refresh_tracks())
        except Exception:
            pass
        try:
            if _fix_combo is not None:
                _fix_combo(self.combo, self._track_stems, max_chars=40)
        except Exception:
            pass

        self._length_var = tk.StringVar(value="全長: -- m")
        self._points_var = tk.StringVar(value="ポイント数: --")
        self._closed_var = tk.StringVar(value="閉ループ: --")
        self._logged_var = tk.StringVar(value="Logged: --")

        self.length_label = ttk.Label(self._ctrl, textvariable=self._length_var)
        self.length_label.pack(side="left", padx=8)
        self.label_length = self.length_label

        self.points_label = ttk.Label(self._ctrl, textvariable=self._points_var)
        self.points_label.pack(side="left", padx=8)
        self.label_points = self.points_label

        self.closed_label = ttk.Label(self._ctrl, textvariable=self._closed_var)
        self.closed_label.pack(side="left", padx=8)
        self.label_closed = self.closed_label

        self.logged_label = ttk.Label(self._ctrl, textvariable=self._logged_var)
        self.logged_label.pack(side="left", padx=8)

        self.preview_label = self.length_label

        # -- resizable split: minimap (top) + graphs (bottom) share the window --
        self._scroll = None  # type: ignore
        self.scrollable = None  # type: ignore
        scroll_parent = self  # type: ignore
        self._split = ttk.PanedWindow(self, orient="vertical")
        self._split.pack(side="top", fill="both", expand=True, padx=2, pady=2)
        self._map_frame = ttk.Frame(self._split)
        self._graph_frame = ttk.Frame(self._split)
        try:
            self._split.add(self._map_frame, weight=3)
            self._split.add(self._graph_frame, weight=2)
        except Exception:
            pass
        scroll_parent = self._map_frame  # type: ignore

        # -- middle: canvas minimap ---------------------------------------
        self.canvas = tk.Canvas(scroll_parent, bg="white", highlightthickness=1, highlightbackground="#ccc", height=320)
        self.canvas.pack(side="top", fill="both", expand=True, padx=6, pady=6)
        self.minimap = self.canvas
        self._canvas = self.canvas
        # also expose under alternate names
        self._track_canvas = self.canvas

        # <Configure> redraw
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._probe_press: tuple[int, int] | None = None
        self._probe_arrays: tuple | None = None
        try:
            self.canvas.bind("<ButtonPress-1>", self._on_probe_press, add="+")
            self.canvas.bind("<ButtonRelease-1>", self._on_probe_release, add="+")
            self.canvas.bind("<Escape>", lambda _e: self._clear_probe(), add="+")
        except Exception:
            pass

        # -- graphs: 6タブ子Notebook (下ペイン, Track* 6) per-tab fallback ---
        self.graph_notebook = ttk.Notebook(self._graph_frame)
        self.graph_notebook.pack(side="top", fill="both", expand=True, padx=6, pady=6)
        self._graph_notebook = self.graph_notebook
        self.chart_notebook = self.graph_notebook
        self.tab_map = ttk.Frame(self.graph_notebook)
        self.tab_curv = ttk.Frame(self.graph_notebook)
        self.tab_elev = ttk.Frame(self.graph_notebook)
        self.tab_grad = ttk.Frame(self.graph_notebook)
        self.tab_bank = ttk.Frame(self.graph_notebook)
        self.tab_grip = ttk.Frame(self.graph_notebook)
        try:
            self.graph_notebook.add(self.tab_map, text="地図")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_curv, text="曲率")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_elev, text="標高")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_grad, text="勾配")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_bank, text="バンク")
        except Exception:
            pass
        try:
            self.graph_notebook.add(self.tab_grip, text="グリップ")
        except Exception:
            pass
        try:
            from openlapexe.gui.charts_track import TrackMapChart as _TMap  # type: ignore
            self.track_map_chart = _TMap(self.tab_map)
            self.track_map_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_map, text="地図 (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.track_map_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_track import TrackCurvChart as _TCurv  # type: ignore
            self.track_curv_chart = _TCurv(self.tab_curv)
            self.track_curv_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_curv, text="曲率 (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.track_curv_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_track import TrackElevChart as _TElev  # type: ignore
            self.track_elev_chart = _TElev(self.tab_elev)
            self.track_elev_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_elev, text="標高 (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.track_elev_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_track import TrackGradChart as _TGrad  # type: ignore
            self.track_grad_chart = _TGrad(self.tab_grad)
            self.track_grad_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_grad, text="勾配 (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.track_grad_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_track import TrackBankChart as _TBank  # type: ignore
            self.track_bank_chart = _TBank(self.tab_bank)
            self.track_bank_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_bank, text="バンク (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.track_bank_chart = None  # type: ignore
        try:
            from openlapexe.gui.charts_track import TrackGripChart as _TGrip  # type: ignore
            self.track_grip_chart = _TGrip(self.tab_grip)
            self.track_grip_chart.pack(fill="both", expand=True, padx=2, pady=2)
        except Exception:
            try:
                ttk.Label(self.tab_grip, text="グリップ (読込失敗)", foreground="#888").pack(expand=True)
            except Exception:
                pass
            self.track_grip_chart = None  # type: ignore
        try:
            self.graph_notebook.bind("<<NotebookTabChanged>>", lambda _e: self._redraw())
        except Exception:
            pass

        # -- bottom: sectorテーブル (compact, always visible) ---------------
        self._sector_frame = ttk.Frame(self)
        self._sector_frame.pack(side="bottom", fill="x", padx=6, pady=(0, 6))

        header = ttk.Frame(self._sector_frame)
        header.pack(side="top", fill="x")
        ttk.Label(header, text="Sectorテーブル", font=("TkDefaultFont", 9, "bold")).pack(side="left")
        self._sector_info_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=self._sector_info_var).pack(side="left", padx=8)
        # also logged inline
        ttk.Label(header, textvariable=self._logged_var).pack(side="right")

        # Treeview for sectors
        columns = ("sector", "start", "end", "length", "count")
        self.sector_table = ttk.Treeview(self._sector_frame, columns=columns, show="headings", height=5)
        self.sector_tree = self.sector_table
        self.tree = self.sector_table
        # alias
        self._sector_tree = self.sector_table
        for col, w, txt in [
            ("sector", 70, "Sector"),
            ("start", 90, "Start m"),
            ("end", 90, "End m"),
            ("length", 90, "Length m"),
            ("count", 70, "Points"),
        ]:
            self.sector_table.heading(col, text=txt)
            self.sector_table.column(col, width=w, anchor="center")
        # scrollbar
        vsb = ttk.Scrollbar(self._sector_frame, orient="vertical", command=self.sector_table.yview)
        hsb = ttk.Scrollbar(self._sector_frame, orient="horizontal", command=self.sector_table.xview)
        self.sector_table.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.sector_table.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        try:
            hsb.pack(side="bottom", fill="x")
        except Exception:
            pass
        try:
            if _fix_tree_h is not None:
                _fix_tree_h(self.sector_table, self._sector_frame)
        except Exception:
            pass

        # also keep fallback labels for tests that search text
        self._sector_text_var = tk.StringVar(value="")
        self.sector_label = ttk.Label(self._sector_frame, textvariable=self._sector_text_var)
        # not packed by default; but exists for introspection
        self._sector_label = self.sector_label

        # default selection Spa
        default_idx = 0
        lower = [s.lower() for s in self._track_stems]
        if "spa" in lower:
            default_idx = lower.index("spa")
        else:
            for i, s in enumerate(lower):
                if "spa" in s:
                    default_idx = i
                    break
        if self._track_stems:
            self.combo.current(default_idx)
            try:
                self._load_track(self._track_stems[default_idx])
            except Exception:
                pass
        self.bind("<Map>", lambda _e: self._redraw())
        try:
            if getattr(self, "_scroll", None) is not None:
                self.after(100, lambda: self._scroll._update_scrollregion())  # type: ignore
        except Exception:
            pass

    # -- discovery -------------------------------------------------------
    def _discover_tracks(self) -> None:
        base: pathlib.Path | None = None
        try:
            rp = _resource_path("data/tracks")
            if rp.exists():
                base = rp
        except Exception:
            pass
        if base is None or not base.exists():
            # fallback
            base = pathlib.Path(__file__).resolve().parents[2] / "data" / "tracks"
            if not base.exists():
                base = pathlib.Path(__file__).resolve().parents[3] / "data" / "tracks"
        self._tracks_dir = base
        files: list[pathlib.Path] = []
        try:
            if base is not None and base.exists():
                files = sorted(base.glob("*.json"))
        except Exception:
            files = []
        valid: list[pathlib.Path] = []
        for p in files:
            try:
                p.read_text(encoding="utf-8")
                valid.append(p)
            except Exception:
                valid.append(p)
        self._track_files = valid
        self._track_stems = [p.stem for p in valid]

    def refresh_tracks(self, select: str | None = None) -> None:
        try:
            base: pathlib.Path | None = None
            try:
                rp = _resource_path("data/tracks")
                if rp.exists():
                    base = rp
            except Exception:
                pass
            if base is None or not base.exists():
                base = pathlib.Path(__file__).resolve().parents[2] / "data" / "tracks"
                if not base.exists():
                    base = pathlib.Path(__file__).resolve().parents[3] / "data" / "tracks"
            self._tracks_dir = base
            files: list[pathlib.Path] = []
            try:
                if base is not None and base.exists():
                    files = sorted(base.glob("*.json"))
            except Exception:
                files = []
            valid: list[pathlib.Path] = []
            for p in files:
                try:
                    p.read_text(encoding="utf-8")
                    valid.append(p)
                except Exception:
                    valid.append(p)
            cur = ""
            try:
                cur = self.combo.get().strip() if hasattr(self, "combo") else ""
            except Exception:
                cur = ""
            if select is not None:
                cur = str(select).strip()
            self._track_files = valid
            self._track_stems = sorted([p.stem for p in valid])
            vals = list(self._track_stems)
            try:
                self.combo.configure(values=vals)
            except Exception:
                try:
                    self.combo["values"] = vals  # type: ignore
                except Exception:
                    pass
            try:
                if cur and cur in vals:
                    self.combo.set(cur)
                    try:
                        self.combo.current(vals.index(cur))
                    except Exception:
                        pass
                elif select is not None and str(select).strip() in vals:
                    s2 = str(select).strip()
                    self.combo.set(s2)
                    try:
                        self.combo.current(vals.index(s2))
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if _fix_combo is not None and hasattr(self, "combo"):
                    _fix_combo(self.combo, vals, max_chars=40)
            except Exception:
                pass
        except Exception:
            pass

    def _list_track_names(self) -> list[str]:
        try:
            self.refresh_tracks()
        except Exception:
            pass
        return list(self._track_stems)

    # -- selection -------------------------------------------------------
    def _on_track_selected(self, event: object | None = None) -> None:
        try:
            self.refresh_tracks()
        except Exception:
            pass
        name = self.combo.get().strip()
        if not name:
            return
        try:
            self._load_track(name)
        except Exception as e:
            log.warning("TrackView2 load failed %r: %s", name, e)
            try:
                messagebox.showwarning("警告", f"コースデータが破損しているため読み込めません: {name}\n{e}", parent=self)
            except Exception:
                try:
                    messagebox.showwarning("警告", f"コースデータが破損しているため読み込めません: {name}\n{e}")
                except Exception:
                    pass
            try:
                self._length_var.set("全長: -- m (破損)")
                self._points_var.set("ポイント数: --")
                self._closed_var.set("閉ループ: --")
                self._logged_var.set("Logged: --")
            except Exception:
                pass

    def _load_track(self, name: str) -> None:
        stem = name.strip().removesuffix(".json")
        if Track is None:
            raise RuntimeError("Track not available")
        try:
            t = Track.from_json(stem)  # type: ignore
        except Exception as e:
            log.warning("track json broken for %r: %s", stem, e)
            try:
                messagebox.showwarning("警告", f"コースデータが破損しているため既定値を使用できません: {stem}\n{e}", parent=self)
            except Exception:
                try:
                    messagebox.showwarning("警告", f"コースデータが破損しているため既定値を使用できません: {stem}\n{e}")
                except Exception:
                    pass
            raise
        self._track = t
        self._update_labels(t)
        self._refresh_sector_table(t)
        self._redraw()
        for _nm in (
            "track_map_chart",
            "track_curv_chart",
            "track_elev_chart",
            "track_grad_chart",
            "track_bank_chart",
            "track_grip_chart",
        ):
            try:
                _ch = getattr(self, _nm, None)
                if _ch is not None:
                    try:
                        _ch.set_track(t)  # type: ignore
                    except Exception:
                        try:
                            _ch.plot(t)  # type: ignore
                        except Exception:
                            pass
            except Exception:
                pass

    def _update_labels(self, t: object) -> None:
        try:
            length = float(getattr(t, "length_m", 0.0))  # type: ignore
        except Exception:
            length = 0.0
        try:
            npts = int(len(t))  # type: ignore
        except Exception:
            try:
                npts = int(getattr(t, "points").shape[0])  # type: ignore
            except Exception:
                npts = 0
        try:
            closed = bool(getattr(t, "closed_loop", False))
        except Exception:
            closed = False
        try:
            logged = bool(getattr(t, "logged", False))
        except Exception:
            logged = False
        self._length_var.set(f"全長: {length:.1f} m")
        self._points_var.set(f"ポイント数: {npts}")
        self._closed_var.set(f"閉ループ: {'Yes' if closed else 'No'}")
        self._logged_var.set(f"Logged: {'Yes' if logged else 'No'}")
        try:
            top = self.winfo_toplevel()
            if hasattr(top, "set_status"):
                top.set_status(f"コース: {getattr(t, 'name', stem)} ({length:.0f}m)")  # type: ignore
        except Exception:
            pass

    # -- sector table -----------------------------------------------------
    def _refresh_sector_table(self, t: object) -> None:
        # clear
        try:
            for iid in self.sector_table.get_children():
                self.sector_table.delete(iid)
        except Exception:
            pass
        sectors: list[dict[str, object]] = []
        try:
            import numpy as np  # type: ignore

            pts = getattr(t, "points", None)
            if pts is not None:
                arr = np.asarray(pts, dtype=float)
                if arr.ndim == 2 and arr.shape[0] > 0 and arr.shape[1] >= 8:
                    s_col = arr[:, 0]
                    sector_col = arr[:, 7]
                    # group by sector change
                    n = int(arr.shape[0])
                    start_idx = 0
                    cur_sec = float(sector_col[0])
                    for i in range(1, n):
                        sec = float(sector_col[i])
                        if sec != cur_sec:
                            # close previous
                            start_s = float(s_col[start_idx])
                            end_s = float(s_col[i - 1])
                            length = end_s - start_s
                            # handle last diff more accurately: include interval to next
                            # but for table use s range
                            sectors.append({
                                "sector": int(cur_sec) if cur_sec == int(cur_sec) else cur_sec,
                                "start": start_s,
                                "end": end_s,
                                "length": abs(length),
                                "count": i - start_idx,
                            })
                            start_idx = i
                            cur_sec = sec
                    # last
                    start_s = float(s_col[start_idx])
                    end_s = float(s_col[n - 1])
                    length = end_s - start_s
                    sectors.append({
                        "sector": int(cur_sec) if cur_sec == int(cur_sec) else cur_sec,
                        "start": start_s,
                        "end": end_s,
                        "length": abs(length),
                        "count": n - start_idx,
                    })
                elif arr.ndim == 2 and arr.shape[1] >= 5:
                    # fallback: try _sector or sector_id property
                    sec_arr = None
                    for attr in ("sector_id", "_sector", "sector"):
                        try:
                            v = getattr(t, attr, None)
                            if v is not None:
                                sec_arr = np.asarray(v, dtype=float)
                                if sec_arr.size == arr.shape[0]:
                                    break
                                sec_arr = None
                        except Exception:
                            continue
                    if sec_arr is not None and sec_arr.size > 0:
                        s_col = np.asarray(getattr(t, "_s", arr[:, 0]), dtype=float)
                        n = int(sec_arr.shape[0])
                        start_idx = 0
                        cur_sec = float(sec_arr[0])
                        for i in range(1, n):
                            sec = float(sec_arr[i])
                            if sec != cur_sec:
                                sectors.append({
                                    "sector": int(cur_sec) if cur_sec == int(cur_sec) else cur_sec,
                                    "start": float(s_col[start_idx]),
                                    "end": float(s_col[i - 1]),
                                    "length": abs(float(s_col[i - 1]) - float(s_col[start_idx])),
                                    "count": i - start_idx,
                                })
                                start_idx = i
                                cur_sec = sec
                        sectors.append({
                            "sector": int(cur_sec) if cur_sec == int(cur_sec) else cur_sec,
                            "start": float(s_col[start_idx]),
                            "end": float(s_col[n - 1]),
                            "length": abs(float(s_col[n - 1]) - float(s_col[start_idx])),
                            "count": n - start_idx,
                        })
        except Exception as e:
            log.debug("sector table build failed: %s", e)
            sectors = []
        # if still empty, create single entry from length
        if not sectors:
            try:
                length = float(getattr(t, "length_m", 0.0))
                npts = int(len(t))  # type: ignore
                sectors = [{"sector": 1, "start": 0.0, "end": length, "length": length, "count": npts}]
            except Exception:
                pass
        # populate tree
        for sec in sectors:
            try:
                self.sector_table.insert("", "end", values=(
                    sec["sector"],
                    f"{float(sec['start']):.1f}",
                    f"{float(sec['end']):.1f}",
                    f"{float(sec['length']):.1f}",
                    sec["count"],
                ))
            except Exception:
                pass
        # update info var and text var for tests that grep text
        try:
            total = len(sectors)
            self._sector_info_var.set(f"{total} sectors")
            # build readable string
            parts = []
            for sec in sectors:
                parts.append(f"{sec['sector']}:{float(sec['start']):.0f}-{float(sec['end']):.0f}")
            self._sector_text_var.set(" ".join(parts))
        except Exception:
            pass

    # -- drawing ---------------------------------------------------------
    def _on_canvas_configure(self, event: object | None = None) -> None:
        self._redraw()

    def _redraw(self) -> None:
        start_t = time.perf_counter()
        c = self.canvas
        try:
            c.delete("all")
        except Exception:
            return
        t = self._track
        if t is None:
            try:
                c.create_text(10, 10, anchor="nw", text="コース未選択", fill="#666", tags=("placeholder",))
            except Exception:
                pass
            return
        # canvas size
        try:
            w = int(c.winfo_width())
            h = int(c.winfo_height())
        except Exception:
            w = 400
            h = 320
        if w < 10:
            w = 400
        if h < 10:
            h = 320
        pad = 12

        try:
            import numpy as np  # type: ignore

            # Extract arrays: prefer _x/_y/_bank/_grip/_sector
            # Fallback to points
            xs_arr = None
            ys_arr = None
            bank_arr = None
            grip_arr = None
            sector_arr = None
            s_arr = None
            # try direct attrs
            try:
                if hasattr(t, "_x") and hasattr(t, "_y"):
                    xv = getattr(t, "_x", None)
                    yv = getattr(t, "_y", None)
                    if xv is not None and yv is not None:
                        xs_arr = np.asarray(xv, dtype=float)
                        ys_arr = np.asarray(yv, dtype=float)
                        # banking/grip/sector
                        for attr, target in [
                            ("_bank", "bank_arr"),
                            ("banking_rad", "bank_arr"),
                            ("_grip", "grip_arr"),
                            ("grip_factor", "grip_arr"),
                            ("_sector", "sector_arr"),
                            ("sector_id", "sector_arr"),
                            ("_s", "s_arr"),
                        ]:
                            try:
                                val = getattr(t, attr, None)
                                if val is not None:
                                    arr = np.asarray(val, dtype=float)
                                    if arr.size == xs_arr.size:
                                        if target == "bank_arr":
                                            bank_arr = arr
                                        elif target == "grip_arr":
                                            grip_arr = arr
                                        elif target == "sector_arr":
                                            sector_arr = arr
                                        elif target == "s_arr":
                                            s_arr = arr
                            except Exception:
                                pass
                        # also try _curv via points?
                        if xs_arr is None or xs_arr.size == 0:
                            xs_arr = None
            except Exception:
                xs_arr = None

            if xs_arr is None or xs_arr.size == 0:
                pts = getattr(t, "points", None)
                if pts is None:
                    return
                arr = np.asarray(pts, dtype=float)
                if arr.ndim != 2 or arr.shape[1] < 2:
                    return
                if arr.shape[1] >= 3:
                    xs_arr = arr[:, 1]
                    ys_arr = arr[:, 2]
                    if arr.shape[1] >= 6:
                        bank_arr = arr[:, 5]
                    if arr.shape[1] >= 7:
                        grip_arr = arr[:, 6]
                    if arr.shape[1] >= 8:
                        sector_arr = arr[:, 7]
                    if arr.shape[1] >= 1:
                        s_arr = arr[:, 0]
                else:
                    xs_arr = arr[:, 0]
                    ys_arr = arr[:, 1]

            if xs_arr is None or ys_arr is None or xs_arr.size == 0:
                return
            n0 = int(xs_arr.shape[0])
            # thinning to <=800
            if n0 > 800:
                step = (n0 + 799) // 800
                # need synchronized slicing
                xs_arr = xs_arr[::step]
                ys_arr = ys_arr[::step]
                if bank_arr is not None and bank_arr.size == n0:
                    bank_arr = bank_arr[::step]
                if grip_arr is not None and grip_arr.size == n0:
                    grip_arr = grip_arr[::step]
                if sector_arr is not None and sector_arr.size == n0:
                    sector_arr = sector_arr[::step]
                if s_arr is not None and s_arr.size == n0:
                    s_arr = s_arr[::step]
                # for closed loop ensure last point kept for closure
                try:
                    if bool(getattr(t, "closed_loop", False)):
                        # if we sliced away last, append original last
                        # check original last not already present
                        orig_x = float(np.asarray(getattr(t, "_x", getattr(t, "points")[:, 1]))[-1]) if hasattr(t, "_x") else float(xs_arr[-1])
                        orig_y = float(np.asarray(getattr(t, "_y", getattr(t, "points")[:, 2]))[-1]) if hasattr(t, "_y") else float(ys_arr[-1])
                        if abs(float(xs_arr[-1]) - orig_x) > 1e-9 or abs(float(ys_arr[-1]) - orig_y) > 1e-9:
                            # need to append
                            xs_arr = np.append(xs_arr, orig_x)
                            ys_arr = np.append(ys_arr, orig_y)
                            if bank_arr is not None:
                                # append last bank value
                                try:
                                    last_bank = float(np.asarray(getattr(t, "_bank", bank_arr))[-1])
                                    bank_arr = np.append(bank_arr, last_bank)
                                except Exception:
                                    bank_arr = np.append(bank_arr, bank_arr[-1])
                            if grip_arr is not None:
                                try:
                                    last_grip = float(np.asarray(getattr(t, "_grip", grip_arr))[-1])
                                    grip_arr = np.append(grip_arr, last_grip)
                                except Exception:
                                    grip_arr = np.append(grip_arr, grip_arr[-1])
                            if sector_arr is not None:
                                try:
                                    last_sec = float(np.asarray(getattr(t, "_sector", sector_arr))[-1])
                                    sector_arr = np.append(sector_arr, last_sec)
                                except Exception:
                                    sector_arr = np.append(sector_arr, sector_arr[-1])
                except Exception:
                    pass
                n0 = int(xs_arr.shape[0])

            # ensure defaults for bank/grip/sector
            if bank_arr is None or bank_arr.size != n0:
                bank_arr = np.zeros(n0, dtype=float)
            if grip_arr is None or grip_arr.size != n0:
                grip_arr = np.ones(n0, dtype=float)
            if sector_arr is None or sector_arr.size != n0:
                sector_arr = np.zeros(n0, dtype=float)
            if s_arr is None or s_arr.size != n0:
                s_arr = np.linspace(0, float(getattr(t, "length_m", n0)), n0)

            # compute bounds
            min_x = float(np.min(xs_arr))
            max_x = float(np.max(xs_arr))
            min_y = float(np.min(ys_arr))
            max_y = float(np.max(ys_arr))
            range_x = max_x - min_x
            range_y = max_y - min_y
            if range_x < 1e-9:
                range_x = 1.0
            if range_y < 1e-9:
                range_y = 1.0
            avail_w = float(w - 2 * pad)
            avail_h = float(h - 2 * pad)
            scale = min(avail_w / range_x, avail_h / range_y)
            extra_w = avail_w - range_x * scale
            extra_h = avail_h - range_y * scale
            off_x = pad + extra_w * 0.5 - min_x * scale
            off_y = pad + extra_h * 0.5 - min_y * scale

            def _px(x: float) -> float:
                return x * scale + off_x

            def _py(y: float) -> float:
                return h - (y * scale + off_y)

            try:
                self._probe_arrays = (
                    xs_arr.copy(),
                    ys_arr.copy(),
                    s_arr.copy(),
                    float(min_x),
                    float(max_x),
                    float(min_y),
                    float(max_y),
                    float(pad),
                )
            except Exception:
                pass

            # draw centerline with banking色分け+grip濃淡
            # Merge consecutive segments with same banking bucket to reduce canvas items (<100ms)
            # Bucketize banking into 8 levels to keep color variation but limit draw calls
            def _bank_bucket(b: float) -> int:
                lo_b = -0.08
                hi_b = 0.08
                if b < lo_b:
                    b = lo_b
                if b > hi_b:
                    b = hi_b
                # 0..7
                t = (b - lo_b) / (hi_b - lo_b) if hi_b != lo_b else 0.5
                bv = int(t * 7 + 0.5)
                if bv < 0:
                    bv = 0
                if bv > 7:
                    bv = 7
                return bv

            # Build polyline runs
            runs: list[list[float]] = []
            run_colors: list[str] = []
            run_widths: list[int] = []
            run_buckets: list[int] = []
            if n0 >= 2:
                # start first run
                cur_bucket = _bank_bucket(float((bank_arr[0] + bank_arr[1]) * 0.5))
                cur_grip = float((grip_arr[0] + grip_arr[1]) * 0.5)
                cur_col = _grip_to_alpha_color(_banking_to_color(float((bank_arr[0] + bank_arr[1]) * 0.5)), cur_grip)
                cur_width = _grip_to_width(cur_grip)
                cur_coords: list[float] = [_px(float(xs_arr[0])), _py(float(ys_arr[0])), _px(float(xs_arr[1])), _py(float(ys_arr[1]))]
                # for smoothing grip/bucket transitions, track average within run
                run_grip_vals: list[float] = [cur_grip]
                run_bank_vals: list[float] = [float((bank_arr[0] + bank_arr[1]) * 0.5)]
                for i in range(1, n0 - 1):
                    b = float((bank_arr[i] + bank_arr[i + 1]) * 0.5)
                    g = float((grip_arr[i] + grip_arr[i + 1]) * 0.5)
                    bv = _bank_bucket(b)
                    # if bucket same and grip width same (bucketed), extend run
                    gw = _grip_to_width(g)
                    if bv == cur_bucket and gw == cur_width and len(cur_coords) < 5000:
                        cur_coords.append(_px(float(xs_arr[i + 1])))
                        cur_coords.append(_py(float(ys_arr[i + 1])))
                        run_grip_vals.append(g)
                        run_bank_vals.append(b)
                    else:
                        # flush previous run
                        runs.append(cur_coords)
                        run_colors.append(cur_col)
                        run_widths.append(cur_width)
                        run_buckets.append(cur_bucket)
                        # start new run
                        cur_bucket = bv
                        cur_col = _grip_to_alpha_color(_banking_to_color(b), g)
                        cur_width = gw
                        cur_coords = [_px(float(xs_arr[i])), _py(float(ys_arr[i])), _px(float(xs_arr[i + 1])), _py(float(ys_arr[i + 1]))]
                        run_grip_vals = [g]
                        run_bank_vals = [b]
                # flush last
                if cur_coords:
                    runs.append(cur_coords)
                    run_colors.append(cur_col)
                    run_widths.append(cur_width)
                    run_buckets.append(cur_bucket)

                for coords, col, wd in zip(runs, run_colors, run_widths):
                    if len(coords) >= 4:
                        c.create_line(*coords, fill=col, width=wd, smooth=False, tags=("centerline", "banking", "grip"))
            else:
                # single point edge
                pass

            # closed loop closing segment if needed (rare: thinned slice dropped closure)
            try:
                if bool(getattr(t, "closed_loop", False)) and n0 >= 2:
                    x_first = _px(float(xs_arr[0]))
                    y_first = _py(float(ys_arr[0]))
                    x_last = _px(float(xs_arr[-1]))
                    y_last = _py(float(ys_arr[-1]))
                    if math.hypot(x_first - x_last, y_first - y_last) > 2.0:
                        b = float((bank_arr[-1] + bank_arr[0]) * 0.5)
                        g = float((grip_arr[-1] + grip_arr[0]) * 0.5)
                        base_col = _banking_to_color(b)
                        col = _grip_to_alpha_color(base_col, g)
                        width = _grip_to_width(g)
                        c.create_line(x_last, y_last, x_first, y_first, fill=col, width=width, tags=("centerline", "banking", "grip", "closed"))
            except Exception:
                pass

            # sector区間線: at points where sector changes, draw small tick + tag sector
            try:
                for i in range(1, n0):
                    if float(sector_arr[i]) != float(sector_arr[i - 1]):
                        cx = _px(float(xs_arr[i]))
                        cy = _py(float(ys_arr[i]))
                        # draw sector boundary: vertical short line and dot
                        c.create_line(cx - 6, cy, cx + 6, cy, fill="#2c3e50", width=2, tags=("sector", "sector_line"))
                        c.create_line(cx, cy - 6, cx, cy + 6, fill="#2c3e50", width=2, tags=("sector", "sector_line"))
                        c.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#f1c40f", outline="#2c3e50", width=1, tags=("sector",))
                        # label sector id
                        sec_id = int(sector_arr[i]) if float(sector_arr[i]) == int(sector_arr[i]) else float(sector_arr[i])
                        c.create_text(cx + 5, cy - 8, text=str(sec_id), fill="#2c3e50", font=("TkDefaultFont", 7), anchor="sw", tags=("sector", "sector_label"))
            except Exception:
                pass

            apex_s: list[float] = []
            # Prefer fast path: only call apex_candidates if stored curvature significant
            has_curv = False
            try:
                import numpy as _np_apex  # type: ignore

                curv_check = getattr(t, "_curv", None)
                if curv_check is not None:
                    curv_arr_chk = _np_apex.asarray(curv_check, dtype=float)
                    if curv_arr_chk.size > 0 and _np_apex.any(_np_apex.abs(curv_arr_chk) > 1e-6):
                        has_curv = True
                else:
                    has_curv = True
            except Exception:
                has_curv = True
            if has_curv:
                try:
                    if hasattr(t, "apex_candidates"):
                        apex_s = list(t.apex_candidates())  # type: ignore
                    elif hasattr(t, "find_apex_candidates"):
                        apex_s = list(t.find_apex_candidates())  # type: ignore
                except Exception:
                    apex_s = []
                if len(apex_s) > 60:
                    apex_s = apex_s[:60]
            else:
                apex_s = []
            if not apex_s:
                try:
                    # fallback using _curv peak detection
                    curv_arr = None
                    try:
                        curv_arr = np.asarray(getattr(t, "_curv"), dtype=float)  # type: ignore
                    except Exception:
                        try:
                            pts = getattr(t, "points", None)
                            if pts is not None:
                                curv_arr = np.asarray(np.asarray(pts)[:, 4], dtype=float)
                        except Exception:
                            curv_arr = None
                    if curv_arr is not None and curv_arr.size > 2:
                        idxs: list[int] = []
                        for idx in range(1, int(curv_arr.shape[0]) - 1):
                            av = abs(float(curv_arr[idx]))
                            if av > abs(float(curv_arr[idx - 1])) and av > abs(float(curv_arr[idx + 1])) and av > 1e-6:
                                idxs.append(idx)
                        if len(idxs) > 60:
                            idxs = idxs[:60]
                        for ii in idxs:
                            try:
                                sx = float(np.asarray(getattr(t, "_s"))[ii])  # type: ignore
                                apex_s.append(sx)
                            except Exception:
                                pass
                except Exception:
                    pass
            # draw apex dots
            try:
                # need full track s/x/y for apex positions (not thinned)
                # use original track arrays if available
                full_s = None
                full_x = None
                full_y = None
                try:
                    full_s = np.asarray(getattr(t, "_s"), dtype=float)
                    full_x = np.asarray(getattr(t, "_x"), dtype=float)
                    full_y = np.asarray(getattr(t, "_y"), dtype=float)
                except Exception:
                    try:
                        pts = np.asarray(getattr(t, "points"), dtype=float)
                        full_s = pts[:, 0]
                        full_x = pts[:, 1]
                        full_y = pts[:, 2]
                    except Exception:
                        full_s = s_arr
                        full_x = xs_arr
                        full_y = ys_arr
                for s_val in apex_s:
                    idx = 0
                    if full_s is not None and full_s.size > 0:
                        try:
                            idx = int(np.searchsorted(full_s, float(s_val)))
                            if idx >= int(full_s.size):
                                idx = int(full_s.size) - 1
                            if idx < 0:
                                idx = 0
                        except Exception:
                            idx = 0
                    try:
                        ax = float(full_x[idx]) if full_x is not None and full_x.size > idx else float(xs_arr[0])
                        ay = float(full_y[idx]) if full_y is not None and full_y.size > idx else float(ys_arr[0])
                    except Exception:
                        continue
                    cx = _px(ax)
                    cy = _py(ay)
                    r = 4
                    c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="red", outline="white", width=1, tags=("apex",))
            except Exception:
                pass

        except Exception as e:
            log.debug("TrackView2 redraw failed: %s", e)
            return
        finally:
            try:
                self._last_draw_ms = (time.perf_counter() - start_t) * 1000.0
            except Exception:
                self._last_draw_ms = 0.0
            for _nm in (
                "track_map_chart",
                "track_curv_chart",
                "track_elev_chart",
                "track_grad_chart",
                "track_bank_chart",
                "track_grip_chart",
            ):
                try:
                    _ch = getattr(self, _nm, None)
                    if _ch is not None:
                        _rd = getattr(_ch, "_redraw", None)
                        if callable(_rd):
                            _rd()
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
            info = getattr(self, "_probe_arrays", None)
            if not info:
                return
            xs, ys, ss, min_x, max_x, min_y, max_y, pad = info
            import numpy as _npp

            xa = _npp.asarray(xs, dtype=float)
            ya = _npp.asarray(ys, dtype=float)
            sa = _npp.asarray(ss, dtype=float) if ss is not None else _npp.arange(xa.size, dtype=float)
            if xa.size == 0:
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
                w, h = 400, 320
            if w < 10:
                w = 400
            if h < 10:
                h = 320
            rx = float(max_x) - float(min_x)
            ry = float(max_y) - float(min_y)
            if rx < 1e-9:
                rx = 1.0
            if ry < 1e-9:
                ry = 1.0
            scale = min(float(w - 2 * pad) / rx, float(h - 2 * pad) / ry)
            extra_w = float(w - 2 * pad) - rx * scale
            extra_h = float(h - 2 * pad) - ry * scale
            off_x = float(pad) + extra_w * 0.5 - float(min_x) * scale
            off_y = float(pad) + extra_h * 0.5 - float(min_y) * scale
            try:
                mpx = xa * scale + off_x
                mpy = float(h) - (ya * scale + off_y)
                idx = int(_npp.argmin((mpx - cx) ** 2 + (mpy - cy) ** 2))
            except Exception:
                idx = 0
            nx, ny = float(xa[idx]), float(ya[idx])
            ns = float(sa[idx]) if sa.size > idx else 0.0
            try:
                vx0 = float(self.canvas.canvasx(0))
                vy0 = float(self.canvas.canvasy(0))
            except Exception:
                vx0, vy0 = 0.0, 0.0
            try:
                self.canvas.create_oval(mpx[idx] - 4, mpy[idx] - 4, mpx[idx] + 4, mpy[idx] + 4, outline="#d00", width=2, tags=("probe",))
                self.canvas.create_line(vx0, cy, vx0 + float(w), cy, fill="#888", dash=(3, 3), tags=("probe",))
                self.canvas.create_line(cx, vy0, cx, vy0 + float(h), fill="#888", dash=(3, 3), tags=("probe",))
            except Exception:
                pass
            lines = [f"#{idx} s={ns:.1f} m X={nx:.1f} m Y={ny:.1f} m"]
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

    # public helpers for tests
    def get_current_track(self) -> object | None:
        return self._track

    def get_track_names(self) -> list[str]:
        return list(self._track_stems)

    def select_track(self, name: str) -> None:
        found = False
        for i, s in enumerate(self._track_stems):
            if s.lower() == name.lower().removesuffix(".json") or s.lower() == name.lower():
                try:
                    self.combo.current(i)
                except Exception:
                    pass
                found = True
                break
        if not found:
            try:
                self.combo.set(name)
            except Exception:
                pass
        self._load_track(name)

    def get_sector_table_data(self) -> list[dict[str, object]]:
        """Return current sector table rows for testing."""
        rows: list[dict[str, object]] = []
        try:
            for iid in self.sector_table.get_children():
                vals = self.sector_table.item(iid, "values")
                if vals:
                    rows.append({
                        "sector": vals[0],
                        "start": vals[1],
                        "end": vals[2],
                        "length": vals[3],
                        "count": vals[4],
                    })
        except Exception:
            pass
        return rows


# alias for compatibility
TrackView = TrackView2

__all__ = ["TrackView2", "TrackView", "_banking_to_color", "_grip_to_width"]
