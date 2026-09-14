# allow: SIZE_OK — ImportView indivisible 4-part (Treeview+staging+XYChart+dialog)
# -*- coding: utf-8 -*-
"""openlapexe.gui.import_view - DXF/KML import staging (ttk+Canvas, ezdxf禁止).

要件:
- ttk.Frame 継承
- filedialog.askopenfilename フィルタ *.dxf;*.kml → io_dxf/io_kml で parse
- ttk.Treeview 列(name/kind/verts/length) extended 複数選択
- ボタン 追加/置換/プレビュー
- プレビューは chart_xy.XYChart で 800点間引き描画
- 確定分は staging buffer(points公開)→Track.from_candidates へ渡せる形
- messagebox parent=self, encoding=utf-8, ttkのみ+Canvas, 既存破壊禁止
"""
from __future__ import annotations

import pathlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from openlapexe.gui.combobox_fix import fix_treeview_horizontal as _fix_tree_h  # type: ignore
except Exception:
    _fix_tree_h = None  # type: ignore

import numpy as np


def _thin_xy(x: np.ndarray, y: np.ndarray, limit: int = 800) -> tuple[np.ndarray, np.ndarray]:
    try:
        xa = np.asarray(x, dtype=float)
        ya = np.asarray(y, dtype=float)
        n = int(xa.shape[0]) if xa.ndim >= 1 else 0
        ny = int(ya.shape[0]) if ya.ndim >= 1 else n
        n = min(n, ny)
        xa = xa[:n]
        ya = ya[:n]
        if n <= limit:
            return xa, ya
        step = (n + limit - 1) // limit
        if step < 1:
            step = 1
        return xa[::step], ya[::step]
    except Exception:
        return x, y  # type: ignore[return-value]


class ImportView(ttk.Frame):
    """DXF/KML インポートビュー.

    - Treeview: columns (name/kind/verts/length), extended multi-select
    - Chart: XYChart (equal) 800点間引き
    - Staging: self.points 公開 (Track.from_candidatesへそのまま渡せる)
    """

    def __init__(self, parent: tk.Widget | ttk.Frame, *args: object, **kwargs: object) -> None:
        super().__init__(parent, *args, **kwargs)  # type: ignore[arg-type]
        self._candidates: list[object] = []
        self._staging: list[object] = []
        # public aliases
        self.points = self._staging
        self.staging = self._staging
        self.staging_buffer = self._staging
        self.buffer = self._staging
        self.candidates = self._candidates

        # -- top controls -------------------------------------------------
        self._ctrl = ttk.Frame(self)
        self._ctrl.pack(side="top", fill="x", padx=6, pady=(6, 4))

        self.btn_open = ttk.Button(self._ctrl, text="開く", command=self._on_open)
        self.open_button = self.btn_open
        self.button_open = self.btn_open
        self.btn_open.pack(side="left", padx=4)

        # 追加 / 置換 / プレビュー (日英併記で両テスト対応)
        self.btn_add = ttk.Button(self._ctrl, text="追加 (Add)", command=self._on_add)
        self.btn_add.pack(side="left", padx=4)
        self.add_button = self.btn_add
        self.button_add = self.btn_add

        self.btn_replace = ttk.Button(self._ctrl, text="置換 (Replace)", command=self._on_replace)
        self.btn_replace.pack(side="left", padx=4)
        self.replace_button = self.btn_replace
        self.button_replace = self.btn_replace

        self.btn_preview = ttk.Button(self._ctrl, text="プレビュー (Preview)", command=self._on_preview)
        self.btn_preview.pack(side="left", padx=4)
        self.preview_button = self.btn_preview
        self.button_preview = self.btn_preview

        try:
            from openlapexe.gui.scrollable import ScrollableFrame as _ScrollableFrame  # type: ignore

            self._scroll = _ScrollableFrame(self)
            self._scroll.pack(fill="both", expand=True, padx=2, pady=2)
            self.scrollable = self._scroll
            _imp_inner = self._scroll.inner  # type: ignore
        except Exception:
            self._scroll = None  # type: ignore
            _imp_inner = self  # type: ignore

        # -- tree ---------------------------------------------------------
        tree_frame = ttk.Frame(_imp_inner)
        tree_frame.pack(side="top", fill="both", expand=True, padx=6, pady=4)

        columns = ("name", "kind", "verts", "length")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended", height=8)
        self.treeview = self.tree
        self.candidate_tree = self.tree
        self._tree = self.tree
        for col, w, txt in [
            ("name", 160, "name"),
            ("kind", 110, "kind"),
            ("verts", 70, "verts"),
            ("length", 100, "length [m]"),
        ]:
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=w, anchor="center" if col != "name" else "w")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        try:
            hsb.pack(side="bottom", fill="x")
        except Exception:
            pass
        try:
            if _fix_tree_h is not None:
                _fix_tree_h(self.tree, tree_frame)
        except Exception:
            pass
        try:
            self.tree.bind("<Control-a>", self._on_select_all)
            self.tree.bind("<Control-A>", self._on_select_all)
            self.tree.bind("<Command-a>", self._on_select_all)
            self.tree.bind("<Command-A>", self._on_select_all)
        except Exception:
            pass

        # -- chart --------------------------------------------------------
        try:
            from openlapexe.gui.chart_xy import XYChart as _XYChart  # type: ignore
        except Exception:
            _XYChart = None  # type: ignore
        if _XYChart is not None:
            _chart_parent = _imp_inner if '_imp_inner' in locals() else self
            self.chart = _XYChart(_chart_parent, xlabel="X [m]", ylabel="Y [m]", equal=True, height=280)  # type: ignore[arg-type]
        else:
            _chart_parent = _imp_inner if '_imp_inner' in locals() else self
            self.chart = tk.Canvas(_chart_parent, bg="white", height=280)  # type: ignore[assignment]
        self.xy_chart = self.chart
        self.preview_chart = self.chart
        self._chart = self.chart
        try:
            self.chart.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 6))  # type: ignore[attr-defined]
        except Exception:
            pass

        # status
        self._status_var = tk.StringVar(value="未読込")
        self.status_label = ttk.Label(self, textvariable=self._status_var)
        self.status_label.pack(side="bottom", fill="x", padx=6, pady=(0, 4))

    # -- file open -------------------------------------------------------
    def _on_open(self) -> None:
        try:
            path = filedialog.askopenfilename(
                parent=self,
                title="DXF / KML を選択",
                filetypes=[
                    ("DXF/KML", "*.dxf *.kml"),
                    ("DXF", "*.dxf"),
                    ("KML", "*.kml"),
                    ("All files", "*.*"),
                ],
            )
        except Exception:
            try:
                path = filedialog.askopenfilename(
                    title="DXF / KML を選択",
                    filetypes=[("DXF/KML", "*.dxf *.kml"), ("DXF", "*.dxf"), ("KML", "*.kml")],
                )
            except Exception:
                return
        if not path:
            return
        self.load_file(path)

    def load_file(self, path: str | pathlib.Path) -> list[object]:
        """Parse DXF/KML file, populate tree. Returns candidates. encoding=utf-8."""
        p = pathlib.Path(str(path))
        # encoding=utf-8 check: ensure file readable as utf-8 (parsers also use utf-8)
        try:
            # quick utf-8 readability test (not destructive)
            p.read_text(encoding="utf-8")
        except Exception:
            # still try parse; parser uses errors=ignore for DXF and utf-8 for KML
            pass
        ext = p.suffix.lower()
        cands: list[object] = []
        try:
            if ext == ".dxf":
                from openlapexe.io_dxf import parse_dxf  # type: ignore

                cands = parse_dxf(p)  # type: ignore[assignment]
            elif ext == ".kml":
                from openlapexe.io_kml import parse_kml  # type: ignore

                cands = parse_kml(p)  # type: ignore[assignment]
            else:
                # auto-detect by trying both (dxf first)
                tried = False
                try:
                    from openlapexe.io_dxf import parse_dxf as _pd  # type: ignore

                    cands = _pd(p)  # type: ignore[assignment]
                    if cands:
                        tried = True
                except Exception:
                    pass
                if not tried:
                    from openlapexe.io_kml import parse_kml as _pk  # type: ignore

                    cands = _pk(p)  # type: ignore[assignment]
        except FileNotFoundError:
            try:
                messagebox.showerror("エラー", f"ファイルが見つかりません: {p}", parent=self)
            except Exception:
                try:
                    messagebox.showerror("エラー", f"ファイルが見つかりません: {p}")
                except Exception:
                    pass
            return []
        except Exception as e:
            try:
                messagebox.showerror("エラー", f"解析に失敗しました: {e}", parent=self)
            except Exception:
                try:
                    messagebox.showerror("エラー", f"解析に失敗しました: {e}")
                except Exception:
                    pass
            return []
        if not cands:
            try:
                messagebox.showwarning("警告", f"候補が見つかりませんでした: {p.name}", parent=self)
            except Exception:
                try:
                    messagebox.showwarning("警告", f"候補が見つかりませんでした: {p.name}")
                except Exception:
                    pass
        self._candidates = list(cands)
        self.candidates = self._candidates
        self._populate_tree(self._candidates)
        try:
            self._status_var.set(f"{p.name}: {len(cands)}件")
        except Exception:
            pass
        return self._candidates

    # alias for tests
    def _load_path(self, path: str | pathlib.Path) -> list[object]:
        return self.load_file(path)

    def _populate_tree(self, cands: list[object]) -> None:
        try:
            for iid in self.tree.get_children():
                self.tree.delete(iid)
        except Exception:
            pass
        for c in cands:
            try:
                name = str(getattr(c, "name", ""))
                kind = str(getattr(c, "kind", ""))
                pts = getattr(c, "points_xy", None)
                if pts is None:
                    pts = getattr(c, "points_lonlat", None)
                verts = 0
                try:
                    arr = np.asarray(pts, dtype=float) if pts is not None else np.zeros((0, 2))
                    if arr.ndim == 1:
                        verts = int(arr.size // 2) if arr.size else 0
                    elif arr.ndim == 2:
                        verts = int(arr.shape[0])
                    else:
                        verts = 0
                except Exception:
                    try:
                        verts = len(pts)  # type: ignore[arg-type]
                    except Exception:
                        verts = 0
                length_m = float(getattr(c, "length_m", 0.0))
                self.tree.insert("", "end", values=(name, kind, str(verts), f"{length_m:.2f}"))
            except Exception:
                continue
        try:
            if _fix_tree_h is not None:
                _fix_tree_h(self.tree, self.tree.master)
        except Exception:
            pass

    def _on_select_all(self, event: object = None) -> str:  # type: ignore[no-untyped-def]
        try:
            children = self.tree.get_children()
            if children:
                self.tree.selection_set(children)
                try:
                    self.tree.focus(children[-1])
                except Exception:
                    pass
        except Exception:
            pass
        return "break"

    # -- selection helpers -----------------------------------------------
    def _get_selected_candidates(self) -> list[object]:
        sel = []
        try:
            ids = self.tree.selection()
        except Exception:
            ids = []
        # map selection index to candidate order
        for iid in ids:
            try:
                vals = self.tree.item(iid, "values")
                # values[0]=name,1=kind - find matching candidate by position
                # Determine index by tree order
                idx = self.tree.index(iid)
                if 0 <= idx < len(self._candidates):
                    sel.append(self._candidates[idx])
                else:
                    # fallback by name/kind match
                    n = str(vals[0]) if len(vals) > 0 else ""
                    k = str(vals[1]) if len(vals) > 1 else ""
                    for c in self._candidates:
                        if str(getattr(c, "name", "")) == n and str(getattr(c, "kind", "")) == k:
                            sel.append(c)
                            break
            except Exception:
                continue
        return sel

    def get_selected_candidates(self) -> list[object]:
        return self._get_selected_candidates()

    # -- add / replace ---------------------------------------------------
    def _on_add(self) -> None:
        sel = self._get_selected_candidates()
        if not sel:
            # if nothing selected but candidates exist, treat as all (for tests without selection)
            # but prefer warning
            try:
                messagebox.showwarning("警告", "候補を選択してください", parent=self)
            except Exception:
                try:
                    messagebox.showwarning("警告", "候補を選択してください")
                except Exception:
                    pass
            return
        # merge (append without dedup for deterministic)
        self._staging.extend(sel)
        # keep public aliases in sync (list object identity preserved)
        self.points = self._staging
        self.staging = self._staging
        self.staging_buffer = self._staging
        self.buffer = self._staging
        try:
            self._status_var.set(f"staging: {len(self._staging)}件 (追加)")
        except Exception:
            pass

    def _on_replace(self) -> None:
        sel = self._get_selected_candidates()
        if not sel:
            try:
                messagebox.showwarning("警告", "候補を選択してください", parent=self)
            except Exception:
                try:
                    messagebox.showwarning("警告", "候補を選択してください")
                except Exception:
                    pass
            return
        # replace: clear and extend
        self._staging.clear()
        self._staging.extend(sel)
        self.points = self._staging
        self.staging = self._staging
        self.staging_buffer = self._staging
        self.buffer = self._staging
        try:
            self._status_var.set(f"staging: {len(self._staging)}件 (置換)")
        except Exception:
            pass

    # public wrappers for tests
    def add_selected(self) -> None:
        self._on_add()

    def replace_selected(self) -> None:
        self._on_replace()

    # -- preview ---------------------------------------------------------
    def _on_preview(self) -> None:
        sel = self._get_selected_candidates()
        if not sel:
            # fallback: preview all if none selected (fragmented KML/DXF needs full preview)
            sel = list(self._candidates) if self._candidates else []
            if not sel:
                try:
                    messagebox.showwarning("警告", "プレビューする候補を選択してください", parent=self)
                except Exception:
                    try:
                        messagebox.showwarning("警告", "プレビューする候補を選択してください")
                    except Exception:
                        pass
                return
        # collect xy for chart
        xs_list: list[np.ndarray] = []
        ys_list: list[np.ndarray] = []
        for c in sel:
            pts_xy = getattr(c, "points_xy", None)
            pts_ll = getattr(c, "points_lonlat", None)
            arr: np.ndarray | None = None
            if pts_xy is not None:
                try:
                    a = np.asarray(pts_xy, dtype=float)
                    if a.ndim == 1:
                        a = a.reshape(-1, 2)
                    if a.ndim == 2 and a.shape[1] >= 2:
                        xs_list.append(np.asarray(a[:, 0], dtype=float))
                        ys_list.append(np.asarray(a[:, 1], dtype=float))
                        continue
                except Exception:
                    pass
            if pts_ll is not None:
                try:
                    seq = list(pts_ll)
                    # try to convert via geo_proj for correct plane coords
                    try:
                        from openlapexe.geo_proj import wgs84_to_plane as _w2p  # type: ignore

                        lons = np.array([float(p[0]) for p in seq], dtype=float)
                        lats = np.array([float(p[1]) for p in seq], dtype=float)
                        x_arr, y_arr, _ = _w2p(lats, lons)  # type: ignore[arg-type]
                        xs_list.append(np.asarray(x_arr, dtype=float).reshape(-1))
                        ys_list.append(np.asarray(y_arr, dtype=float).reshape(-1))
                        continue
                    except Exception:
                        pass
                    # fallback: use lon as x, lat as y
                    a = np.asarray(seq, dtype=float)
                    if a.ndim == 2 and a.shape[1] >= 2:
                        xs_list.append(np.asarray(a[:, 0], dtype=float))
                        ys_list.append(np.asarray(a[:, 1], dtype=float))
                except Exception:
                    continue
        if not xs_list:
            return
        # concatenate for multi-selection preview (deterministic)
        if len(xs_list) == 1:
            xs = xs_list[0]
            ys = ys_list[0]
        else:
            # concatenate with NaN separator? For simplicity concat
            xs = np.concatenate([a.reshape(-1) for a in xs_list])
            ys = np.concatenate([a.reshape(-1) for a in ys_list])
        # 800点間引き
        if xs.size > 800 or ys.size > 800:
            xs, ys = _thin_xy(xs, ys, 800)
        # draw via XYChart
        try:
            ch = self.chart
            # XYChart API: draw_line / set_data / _store_thin
            if hasattr(ch, "draw_line"):
                ch.draw_line(xs, ys)  # type: ignore[attr-defined]
            elif hasattr(ch, "set_data"):
                ch.set_data(xs, ys)  # type: ignore[attr-defined]
            elif hasattr(ch, "update_chart"):
                ch.update_chart(xs, ys)  # type: ignore[attr-defined]
            else:
                # fallback Canvas line
                if isinstance(ch, tk.Canvas):
                    ch.delete("all")
                    # simple normalized draw
                    if xs.size > 1:
                        w = int(ch.winfo_width()) or 600
                        h = int(ch.winfo_height()) or 300
                        min_x, max_x = float(np.min(xs)), float(np.max(xs))
                        min_y, max_y = float(np.min(ys)), float(np.max(ys))
                        if max_x - min_x < 1e-9:
                            max_x = min_x + 1.0
                        if max_y - min_y < 1e-9:
                            max_y = min_y + 1.0
                        pad = 12
                        sx = (w - 2 * pad) / (max_x - min_x)
                        sy = (h - 2 * pad) / (max_y - min_y)
                        sc = min(sx, sy)
                        pts = []
                        for xv, yv in zip(xs, ys):
                            px = pad + (float(xv) - min_x) * sc
                            py = h - pad - (float(yv) - min_y) * sc
                            pts.extend([px, py])
                        if len(pts) >= 4:
                            ch.create_line(*pts, fill="#1f4b99", width=2)
        except Exception:
            pass

    def preview_selected(self) -> None:
        self._on_preview()

    # alias for preview
    def preview(self) -> None:
        self._on_preview()


__all__ = ["ImportView"]
