# -*- coding: utf-8 -*-
"""openlapexe.gui.data_view - データ管理ビュー (車両/コース一覧+エクスポート/インポート).

要件:
- ttk.Frame 継承、ttk のみ + Treeview + Canvas 不使用
- 車両/コースの一覧表示 (data/vehicles, data/tracks の *.json)
- 車両/コース単位でのエクスポート (filedialog.asksaveasfilename へコピー)
- インポート (filedialog.askopenfilename → validate → data へ atomic utf-8 保存)
- messagebox parent=self, encoding=utf-8, 既存破壊禁止
"""
from __future__ import annotations

import json
import pathlib
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from openlapexe.gui.combobox_fix import fix_treeview_horizontal as _fix_tree_h  # type: ignore
except Exception:
    _fix_tree_h = None  # type: ignore

try:
    from openlapexe.io import (  # type: ignore
        _atomic_write_text as _atomic_write_text,
        resource_path as _resource_path,
        validate_track_dict as _validate_track,
        validate_vehicle_dict as _validate_vehicle,
    )
except Exception:  # fallback
    import sys as _sys

    def _resource_path(relative: str) -> pathlib.Path:  # type: ignore[no-redef]
        if hasattr(_sys, "_MEIPASS"):
            base = pathlib.Path(str(_sys._MEIPASS))  # type: ignore[attr-defined]
        else:
            base = pathlib.Path(__file__).resolve().parents[3]
            if not (base / "app.py").exists():
                base = pathlib.Path(__file__).resolve().parents[2]
        return base / relative

    def _atomic_write_text(path: pathlib.Path, text: str, encoding: str = "utf-8") -> None:  # type: ignore[no-redef]
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(text, encoding=encoding)
        tmp.replace(path)

    def _validate_vehicle(data: dict) -> dict:  # type: ignore[no-redef]
        if not isinstance(data, dict):
            raise ValueError("vehicle data must be dict")
        return data

    def _validate_track(data: dict) -> dict:  # type: ignore[no-redef]
        if not isinstance(data, dict):
            raise ValueError("track data must be dict")
        return data


def _vehicles_dir() -> pathlib.Path:
    try:
        p = _resource_path("data/vehicles")
        if p.exists() or True:
            return p
    except Exception:
        pass
    return pathlib.Path(__file__).resolve().parents[3] / "data" / "vehicles"


def _tracks_dir() -> pathlib.Path:
    try:
        p = _resource_path("data/tracks")
        if p.exists() or True:
            return p
    except Exception:
        pass
    return pathlib.Path(__file__).resolve().parents[3] / "data" / "tracks"


def _safe_json_load(path: pathlib.Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


class DataView(ttk.Frame):
    """車両/コースのデータ管理ビュー.

    - 一覧: Treeview 2基 (車両/コース)
    - 単位操作: エクスポート/インポート/削除/更新 (車両・コース別)
    - on_data_changed(kind, name): 外部連携用コールバック (shell が combo 更新に利用)
    """

    def __init__(self, master: tk.Misc | None = None, **kwargs: object) -> None:
        super().__init__(master, **kwargs)  # type: ignore[arg-type]
        self.on_data_changed = None  # type: ignore[assignment]
        self._vehicles: list[dict] = []
        self._tracks: list[dict] = []

        # -- toolbar ------------------------------------------------------
        self._toolbar = ttk.Frame(self)
        self._toolbar.pack(side="top", fill="x", padx=6, pady=(6, 2))
        self.btn_refresh = ttk.Button(self._toolbar, text="更新 (Refresh)", command=self.refresh_all)
        self.btn_refresh.pack(side="left", padx=4)
        self.refresh_button = self.btn_refresh
        self.button_refresh = self.btn_refresh
        self._status_var = tk.StringVar(value="未読込")
        self.status_label = ttk.Label(self._toolbar, textvariable=self._status_var)
        self.status_label.pack(side="left", padx=8)

        # -- vehicle section ----------------------------------------------
        self.vehicle_frame = ttk.LabelFrame(self, text="車両")
        self.vehicle_frame.pack(side="top", fill="both", expand=True, padx=6, pady=4)
        vcols = ("file", "name", "type", "mass", "drive")
        self.vehicle_tree = ttk.Treeview(self.vehicle_frame, columns=vcols, show="headings", height=6)
        self.vehicle_tree.heading("file", text="file")
        self.vehicle_tree.heading("name", text="name")
        self.vehicle_tree.heading("type", text="type")
        self.vehicle_tree.heading("mass", text="mass [kg]")
        self.vehicle_tree.heading("drive", text="drive")
        self.vehicle_tree.column("file", width=140)
        self.vehicle_tree.column("name", width=160)
        self.vehicle_tree.column("type", width=100, anchor="center")
        self.vehicle_tree.column("mass", width=80, anchor="center")
        self.vehicle_tree.column("drive", width=70, anchor="center")
        self.tree_vehicles = self.vehicle_tree
        self.tree_vehicle = self.vehicle_tree
        vsb_v = ttk.Scrollbar(self.vehicle_frame, orient="vertical", command=self.vehicle_tree.yview)
        hsb_v = ttk.Scrollbar(self.vehicle_frame, orient="horizontal", command=self.vehicle_tree.xview)
        self.vehicle_tree.configure(yscrollcommand=vsb_v.set, xscrollcommand=hsb_v.set)
        self.vehicle_tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        vsb_v.pack(side="right", fill="y", pady=4, padx=(0, 4))
        try:
            hsb_v.pack(side="bottom", fill="x", padx=4)
        except Exception:
            pass
        try:
            if _fix_tree_h is not None:
                _fix_tree_h(self.vehicle_tree, self.vehicle_frame)
        except Exception:
            pass
        vbtn = ttk.Frame(self.vehicle_frame)
        vbtn.pack(side="right", fill="y", padx=4, pady=4)
        self.btn_vehicle_export = ttk.Button(vbtn, text="エクスポート", command=self.export_vehicle_selected)
        self.btn_vehicle_export.pack(side="top", fill="x", pady=2)
        self.btn_vehicle_import = ttk.Button(vbtn, text="インポート", command=self.import_vehicle_dialog)
        self.btn_vehicle_import.pack(side="top", fill="x", pady=2)
        self.btn_vehicle_delete = ttk.Button(vbtn, text="削除", command=self.delete_vehicle_selected)
        self.btn_vehicle_delete.pack(side="top", fill="x", pady=2)
        # aliases
        self.vehicle_export_button = self.btn_vehicle_export
        self.vehicle_import_button = self.btn_vehicle_import
        self.vehicle_delete_button = self.btn_vehicle_delete

        # -- track section -------------------------------------------------
        self.track_frame = ttk.LabelFrame(self, text="コース")
        self.track_frame.pack(side="top", fill="both", expand=True, padx=6, pady=4)
        tcols = ("file", "name", "length", "points", "closed")
        self.track_tree = ttk.Treeview(self.track_frame, columns=tcols, show="headings", height=6)
        self.track_tree.heading("file", text="file")
        self.track_tree.heading("name", text="name")
        self.track_tree.heading("length", text="length [m]")
        self.track_tree.heading("points", text="points")
        self.track_tree.heading("closed", text="closed")
        self.track_tree.column("file", width=140)
        self.track_tree.column("name", width=160)
        self.track_tree.column("length", width=90, anchor="center")
        self.track_tree.column("points", width=70, anchor="center")
        self.track_tree.column("closed", width=60, anchor="center")
        self.tree_tracks = self.track_tree
        self.tree_track = self.track_tree
        vsb_t = ttk.Scrollbar(self.track_frame, orient="vertical", command=self.track_tree.yview)
        hsb_t = ttk.Scrollbar(self.track_frame, orient="horizontal", command=self.track_tree.xview)
        self.track_tree.configure(yscrollcommand=vsb_t.set, xscrollcommand=hsb_t.set)
        self.track_tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        vsb_t.pack(side="right", fill="y", pady=4, padx=(0, 4))
        try:
            hsb_t.pack(side="bottom", fill="x", padx=4)
        except Exception:
            pass
        try:
            if _fix_tree_h is not None:
                _fix_tree_h(self.track_tree, self.track_frame)
        except Exception:
            pass
        tbtn = ttk.Frame(self.track_frame)
        tbtn.pack(side="right", fill="y", padx=4, pady=4)
        self.btn_track_export = ttk.Button(tbtn, text="エクスポート", command=self.export_track_selected)
        self.btn_track_export.pack(side="top", fill="x", pady=2)
        self.btn_track_import = ttk.Button(tbtn, text="インポート", command=self.import_track_dialog)
        self.btn_track_import.pack(side="top", fill="x", pady=2)
        self.btn_track_delete = ttk.Button(tbtn, text="削除", command=self.delete_track_selected)
        self.btn_track_delete.pack(side="top", fill="x", pady=2)
        self.track_export_button = self.btn_track_export
        self.track_import_button = self.btn_track_import
        self.track_delete_button = self.btn_track_delete

        self.refresh_all()

    # -- listing -----------------------------------------------------------
    def list_vehicles(self) -> list[dict]:
        return list(self._vehicles)

    def list_tracks(self) -> list[dict]:
        return list(self._tracks)

    def get_vehicle_names(self) -> list[str]:
        return [str(d.get("stem", "")) for d in self._vehicles]

    def get_track_names(self) -> list[str]:
        return [str(d.get("stem", "")) for d in self._tracks]

    def refresh_all(self) -> None:
        self.refresh_vehicles()
        self.refresh_tracks()
        try:
            self._status_var.set(f"車両 {len(self._vehicles)}件 / コース {len(self._tracks)}件")
        except Exception:
            pass

    def refresh_vehicles(self, select: str | None = None) -> None:
        base = _vehicles_dir()
        rows: list[dict] = []
        try:
            if base.exists():
                for p in sorted(base.glob("*.json")):
                    data = _safe_json_load(p)
                    if data is None:
                        rows.append({"stem": p.stem, "path": p, "name": p.stem, "type": "?", "mass": "?", "drive": "?", "broken": True})
                        continue
                    name = str(data.get("Name", data.get("name", p.stem)))
                    typ = str(data.get("Type", data.get("type", "")))
                    mass: object = data.get("M", data.get("mass_kg", ""))
                    try:
                        mass_s = f"{float(mass):.0f}" if mass != "" else ""
                    except Exception:
                        mass_s = str(mass)
                    drive = str(data.get("drive", ""))
                    rows.append({"stem": p.stem, "path": p, "name": name, "type": typ, "mass": mass_s, "drive": drive, "broken": False})
        except Exception:
            pass
        self._vehicles = rows
        try:
            for iid in self.vehicle_tree.get_children():
                self.vehicle_tree.delete(iid)
            for r in rows:
                self.vehicle_tree.insert("", "end", values=(r["stem"], r["name"], r["type"], r["mass"], r["drive"]))
            if select is not None:
                for iid in self.vehicle_tree.get_children():
                    vals = self.vehicle_tree.item(iid, "values")
                    if vals and str(vals[0]) == str(select).removesuffix(".json"):
                        try:
                            self.vehicle_tree.selection_set(iid)
                            self.vehicle_tree.see(iid)
                        except Exception:
                            pass
                        break
        except Exception:
            pass
        try:
            if _fix_tree_h is not None:
                _fix_tree_h(self.vehicle_tree, self.vehicle_frame)
        except Exception:
            pass

    def refresh_tracks(self, select: str | None = None) -> None:
        base = _tracks_dir()
        rows: list[dict] = []
        try:
            if base.exists():
                for p in sorted(base.glob("*.json")):
                    data = _safe_json_load(p)
                    if data is None:
                        rows.append({"stem": p.stem, "path": p, "name": p.stem, "length": "?", "points": "?", "closed": "?", "broken": True})
                        continue
                    name = str(data.get("name", p.stem))
                    length: object = data.get("length_m", data.get("length", data.get("L", "")))
                    try:
                        length_s = f"{float(length):.1f}" if length != "" else ""
                    except Exception:
                        length_s = str(length)
                    pts = data.get("points", [])
                    npts = str(len(pts)) if isinstance(pts, list) else "?"
                    closed_v = data.get("closed_loop", data.get("closed", ""))
                    closed_s = "" if closed_v == "" else ("○" if bool(closed_v) else "×")
                    rows.append({"stem": p.stem, "path": p, "name": name, "length": length_s, "points": npts, "closed": closed_s, "broken": False})
        except Exception:
            pass
        self._tracks = rows
        try:
            for iid in self.track_tree.get_children():
                self.track_tree.delete(iid)
            for r in rows:
                self.track_tree.insert("", "end", values=(r["stem"], r["name"], r["length"], r["points"], r["closed"]))
            if select is not None:
                for iid in self.track_tree.get_children():
                    vals = self.track_tree.item(iid, "values")
                    if vals and str(vals[0]) == str(select).removesuffix(".json"):
                        try:
                            self.track_tree.selection_set(iid)
                            self.track_tree.see(iid)
                        except Exception:
                            pass
                        break
        except Exception:
            pass
        try:
            if _fix_tree_h is not None:
                _fix_tree_h(self.track_tree, self.track_frame)
        except Exception:
            pass

    # -- selection helpers ---------------------------------------------------
    def _selected_stem(self, tree: ttk.Treeview) -> str | None:
        try:
            sel = tree.selection()
            if not sel:
                return None
            vals = tree.item(sel[0], "values")
            if not vals:
                return None
            return str(vals[0])
        except Exception:
            return None

    def get_selected_vehicle(self) -> str | None:
        return self._selected_stem(self.vehicle_tree)

    def get_selected_track(self) -> str | None:
        return self._selected_stem(self.track_tree)

    def _notify(self, kind: str, name: str | None = None) -> None:
        try:
            cb = getattr(self, "on_data_changed", None)
            if callable(cb):
                cb(kind, name)
        except Exception:
            pass

    # -- export --------------------------------------------------------------
    def export_vehicle(self, stem: str, dest: str | pathlib.Path) -> pathlib.Path:
        src = _vehicles_dir() / f"{str(stem).removesuffix('.json')}.json"
        if not src.exists():
            raise FileNotFoundError(f"車両が見つかりません: {stem}")
        dst = pathlib.Path(str(dest))
        if dst.is_dir() or (not dst.suffix):
            dst = dst / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(src), str(dst))
        return dst

    def export_track(self, stem: str, dest: str | pathlib.Path) -> pathlib.Path:
        src = _tracks_dir() / f"{str(stem).removesuffix('.json')}.json"
        if not src.exists():
            raise FileNotFoundError(f"コースが見つかりません: {stem}")
        dst = pathlib.Path(str(dest))
        if dst.is_dir() or (not dst.suffix):
            dst = dst / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(src), str(dst))
        return dst

    def export_vehicle_selected(self) -> None:
        stem = self.get_selected_vehicle()
        if not stem:
            try:
                messagebox.showwarning("エクスポート", "車両を選択してください", parent=self)
            except Exception:
                pass
            return
        try:
            dest = filedialog.asksaveasfilename(parent=self, title="車両をエクスポート", initialfile=f"{stem}.json", filetypes=[("JSON", "*.json"), ("All files", "*.*")], defaultextension=".json")
        except TypeError:
            try:
                dest = filedialog.asksaveasfilename(title="車両をエクスポート", initialfile=f"{stem}.json")
            except Exception:
                return
        except Exception:
            return
        if not dest:
            return
        try:
            out = self.export_vehicle(stem, dest)
        except Exception as e:
            try:
                messagebox.showerror("エクスポート", f"失敗しました: {e}", parent=self)
            except Exception:
                pass
            return
        try:
            self._status_var.set(f"車両エクスポート: {out.name}")
        except Exception:
            pass

    def export_track_selected(self) -> None:
        stem = self.get_selected_track()
        if not stem:
            try:
                messagebox.showwarning("エクスポート", "コースを選択してください", parent=self)
            except Exception:
                pass
            return
        try:
            dest = filedialog.asksaveasfilename(parent=self, title="コースをエクスポート", initialfile=f"{stem}.json", filetypes=[("JSON", "*.json"), ("All files", "*.*")], defaultextension=".json")
        except TypeError:
            try:
                dest = filedialog.asksaveasfilename(title="コースをエクスポート", initialfile=f"{stem}.json")
            except Exception:
                return
        except Exception:
            return
        if not dest:
            return
        try:
            out = self.export_track(stem, dest)
        except Exception as e:
            try:
                messagebox.showerror("エクスポート", f"失敗しました: {e}", parent=self)
            except Exception:
                pass
            return
        try:
            self._status_var.set(f"コースエクスポート: {out.name}")
        except Exception:
            pass

    # -- import --------------------------------------------------------------
    def import_vehicle_file(self, src: str | pathlib.Path, overwrite: bool | None = None) -> str:
        p = pathlib.Path(str(src))
        data = json.loads(p.read_text(encoding="utf-8"))
        _validate_vehicle(data)
        stem = p.stem
        # name field があればファイル名衝突回避ではなくそのまま stem を使う
        dst = _vehicles_dir() / f"{stem}.json"
        if dst.exists() and overwrite is None:
            try:
                ok = messagebox.askyesno("インポート", f"{dst.name} は既に存在します。上書きしますか？", parent=self)
            except Exception:
                try:
                    ok = messagebox.askyesno("インポート", f"{dst.name} は既に存在します。上書きしますか？")
                except Exception:
                    ok = False
            if not ok:
                raise FileExistsError(f"中止しました: {dst.name}")
        elif dst.exists() and overwrite is False:
            raise FileExistsError(f"既に存在します: {dst.name}")
        text = json.dumps(data, ensure_ascii=False, indent=2)
        _atomic_write_text(dst, text, encoding="utf-8")
        self.refresh_vehicles(select=stem)
        try:
            self._status_var.set(f"車両インポート: {dst.name}")
        except Exception:
            pass
        self._notify("vehicles", stem)
        return stem

    def import_track_file(self, src: str | pathlib.Path, overwrite: bool | None = None) -> str:
        p = pathlib.Path(str(src))
        data = json.loads(p.read_text(encoding="utf-8"))
        _validate_track(data)
        stem = p.stem
        dst = _tracks_dir() / f"{stem}.json"
        if dst.exists() and overwrite is None:
            try:
                ok = messagebox.askyesno("インポート", f"{dst.name} は既に存在します。上書きしますか？", parent=self)
            except Exception:
                try:
                    ok = messagebox.askyesno("インポート", f"{dst.name} は既に存在します。上書きしますか？")
                except Exception:
                    ok = False
            if not ok:
                raise FileExistsError(f"中止しました: {dst.name}")
        elif dst.exists() and overwrite is False:
            raise FileExistsError(f"既に存在します: {dst.name}")
        text = json.dumps(data, ensure_ascii=False, indent=2)
        _atomic_write_text(dst, text, encoding="utf-8")
        self.refresh_tracks(select=stem)
        try:
            self._status_var.set(f"コースインポート: {dst.name}")
        except Exception:
            pass
        self._notify("tracks", stem)
        return stem

    def import_vehicle_dialog(self) -> None:
        try:
            path = filedialog.askopenfilename(parent=self, title="車両JSONを選択", filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        except TypeError:
            try:
                path = filedialog.askopenfilename(title="車両JSONを選択")
            except Exception:
                return
        except Exception:
            return
        if not path:
            return
        try:
            self.import_vehicle_file(path)
        except FileExistsError:
            return
        except Exception as e:
            try:
                messagebox.showerror("インポート", f"失敗しました: {e}", parent=self)
            except Exception:
                pass

    def import_track_dialog(self) -> None:
        try:
            path = filedialog.askopenfilename(parent=self, title="コースJSONを選択", filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        except TypeError:
            try:
                path = filedialog.askopenfilename(title="コースJSONを選択")
            except Exception:
                return
        except Exception:
            return
        if not path:
            return
        try:
            self.import_track_file(path)
        except FileExistsError:
            return
        except Exception as e:
            try:
                messagebox.showerror("インポート", f"失敗しました: {e}", parent=self)
            except Exception:
                pass

    # -- delete ---------------------------------------------------------------
    def delete_vehicle_selected(self) -> None:
        stem = self.get_selected_vehicle()
        if not stem:
            try:
                messagebox.showwarning("削除", "車両を選択してください", parent=self)
            except Exception:
                pass
            return
        try:
            ok = messagebox.askyesno("削除", f"{stem}.json を削除しますか？", parent=self)
        except Exception:
            try:
                ok = messagebox.askyesno("削除", f"{stem}.json を削除しますか？")
            except Exception:
                return
        if not ok:
            return
        try:
            target = _vehicles_dir() / f"{stem}.json"
            target.unlink()
        except Exception as e:
            try:
                messagebox.showerror("削除", f"失敗しました: {e}", parent=self)
            except Exception:
                pass
            return
        self.refresh_vehicles()
        try:
            self._status_var.set(f"車両削除: {stem}")
        except Exception:
            pass
        self._notify("vehicles", stem)

    def delete_track_selected(self) -> None:
        stem = self.get_selected_track()
        if not stem:
            try:
                messagebox.showwarning("削除", "コースを選択してください", parent=self)
            except Exception:
                pass
            return
        try:
            ok = messagebox.askyesno("削除", f"{stem}.json を削除しますか？", parent=self)
        except Exception:
            try:
                ok = messagebox.askyesno("削除", f"{stem}.json を削除しますか？")
            except Exception:
                return
        if not ok:
            return
        try:
            target = _tracks_dir() / f"{stem}.json"
            target.unlink()
        except Exception as e:
            try:
                messagebox.showerror("削除", f"失敗しました: {e}", parent=self)
            except Exception:
                pass
            return
        self.refresh_tracks()
        try:
            self._status_var.set(f"コース削除: {stem}")
        except Exception:
            pass
        self._notify("tracks", stem)


__all__ = ["DataView"]
