# -*- coding: utf-8 -*-
# allow: SIZE_OK — VehicleEditor47 47項目+Treeview18行+PCHIP Canvas単一責務 (ttk GUI)
"""openlapexe.gui.vehicle_editor - 47項目 Vehicle47 エディタ.

Requirements:
- ttkのみ (CanvasはPCHIPプレビュー用で許可), Font self保持, messagebox parent=self
- グループ別 Mass/Aero/Tire/Engine/Gear/Derived で47 Entry + Treeview 18行 + PCHIP Canvas
- 不正は赤背景(Invalid.TEntry) + Saveブロック, abcで落ちない
- Save→data/vehicles/custom.json atomic utf-8, Reset→f1再読込
- app.py VehicleFrameは温存し両立, scipy/matplotlib禁止
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont

try:
    from openlapexe.io import _atomic_write_text as _atomic_write_text
    from openlapexe.io import resource_path as _resource_path
except ImportError:  # fallback

    def _resource_path(relative: str) -> pathlib.Path:  # type: ignore[no-redef]
        if hasattr(sys, "_MEIPASS"):
            base = pathlib.Path(str(sys._MEIPASS))  # type: ignore[attr-defined]
        else:
            base = pathlib.Path(__file__).resolve().parents[3]
            if not (base / "app.py").exists():
                base = pathlib.Path(__file__).resolve().parents[2]
        return base / relative

    def _atomic_write_text(path: pathlib.Path, text: str, encoding: str = "utf-8") -> None:  # type: ignore[no-redef]
        _ = encoding
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)

try:
    from openlapexe.vehicle import Vehicle47 as _Vehicle47
    from openlapexe.vehicle import _pchip_interp as _pchip_interp  # type: ignore
except Exception:
    _Vehicle47 = None  # type: ignore
    _pchip_interp = None  # type: ignore

import numpy as _np

# ---------------------------------------------------------------------------
# Group definitions (47 fields grouped into 6 LabelFrames)
# ---------------------------------------------------------------------------
GROUPS: dict[str, tuple[str, ...]] = {
    "Mass": ("Name", "Type", "M", "df", "L", "rack", "cog_height_m", "mass_kg", "wheelbase_m"),
    "Aero": ("Cl", "Cd", "factor_Cl", "factor_Cd", "da", "A", "rho"),
    "Tire": (
        "br_disc_d",
        "br_pad_h",
        "br_pad_mu",
        "br_nop",
        "br_pist_d",
        "br_mast_d",
        "br_ped_r",
        "factor_grip",
        "tyre_radius",
        "Cr",
        "mu_x",
        "mu_x_M",
        "sens_x",
        "mu_y",
        "mu_y_M",
        "sens_y",
        "CF",
        "CR",
    ),
    "Engine": ("factor_power", "n_thermal", "fuel_LHV", "drive", "shift_time"),
    "Gear": ("n_primary", "n_final", "n_gearbox", "ratio_primary", "ratio_final", "ratio_gearbox", "torque_curve"),
    "Derived": ("cda",),
}
# Derived group includes cda only (others overlap but keep Mass/Aero etc); to reach 47 we put cda duplicated?
# Actually all 47 must appear exactly once. Let's verify counts:
# Mass 9 + Aero 7 + Tire 18 + Engine 5 + Gear 7 + Derived 1 = 47 correct (9+7=16, +18=34, +5=39, +7=46, +1=47)
# Note: cog_height_m/mass_kg/wheelbase_m already in Mass, cda in Derived, so total 47 unique.
ALL_FIELDS: tuple[str, ...] = tuple(k for grp in GROUPS.values() for k in grp)
# Ensure order matches Vehicle47 field order for round-trip determinism but group order is kept for UI.
# Validate count
assert len(ALL_FIELDS) == 47, f"groups must cover 47 fields, got {len(ALL_FIELDS)}"
assert len(set(ALL_FIELDS)) == 47

STRING_FIELDS: frozenset[str] = frozenset({"Name", "Type", "drive"})


class VehicleEditor47(ttk.Frame):
    """47項目エディタ. ttk.Frame継承, 47 Entry + Treeview(18行) + Canvas(PCHIPプレビュー)."""

    GROUPS = GROUPS
    FIELDS: tuple[str, ...] = ALL_FIELDS

    def __init__(self, master: tk.Misc | None = None, **kwargs: object) -> None:
        super().__init__(master, **kwargs)  # type: ignore[arg-type]
        # Font retention (Tk quirk)
        try:
            self._font_default = tkfont.nametofont("TkDefaultFont")
            self._font_text = tkfont.nametofont("TkTextFont")
        except Exception:
            self._font_default = None  # type: ignore
            self._font_text = None  # type: ignore
        # ttk style for invalid
        try:
            self._style = ttk.Style(self)
            self._style.configure("Invalid.TEntry", fieldbackground="#ffcccc")
        except Exception:
            self._style = None  # type: ignore

        self.entries: dict[str, ttk.Entry] = {}
        self.vars: dict[str, tk.StringVar] = {}
        # keep per-field LabelFrame refs for test introspection
        self._group_frames: dict[str, ttk.LabelFrame] = {}
        self._save_btn: ttk.Button | None = None
        self._reset_btn: ttk.Button | None = None
        self.tree: ttk.Treeview  # assigned in _build_torque_table
        self.canvas: tk.Canvas  # assigned in _build_preview
        self._preview_canvas: tk.Canvas | None = None
        self._scroll: object | None = None
        self.scrollable: object | None = None
        self.on_vehicle_saved: object | None = None

        # load vehicle f1
        self._vehicle: object | None = None
        try:
            if _Vehicle47 is not None:
                self._vehicle = _Vehicle47.from_json("f1")  # type: ignore
            else:
                raise RuntimeError("Vehicle47 not available")
        except Exception as e:
            try:
                messagebox.showwarning("警告", f"車両データが破損しているため既定値を使用します:\n{e}", parent=self)
            except Exception:
                try:
                    messagebox.showwarning("警告", f"車両データが破損しているため既定値を使用します:\n{e}", parent=self)
                except Exception:
                    pass
            self._vehicle = None

        try:
            from openlapexe.gui.scrollable import ScrollableFrame as _ScrollableFrame  # type: ignore

            self._main_paned = ttk.PanedWindow(self, orient="vertical")
            self._main_paned.pack(fill="both", expand=True, padx=4, pady=4)
            self._form_frame = ttk.Frame(self._main_paned)
            self._main_paned.add(self._form_frame, weight=3)
            sf = _ScrollableFrame(self._form_frame)
            sf.pack(fill="both", expand=True)
            self._scroll = sf
            self.scrollable = sf
            self._scroll_frame = sf  # alias
            self.scroll_frame = sf
            self._chart_host = self._main_paned
        except Exception:
            sf = None  # type: ignore
            self._scroll = None
            self._chart_host = None  # type: ignore
        self._build_entries()
        self._build_torque_table()
        self._build_vehicle_graphs()
        self._build_preview()
        self._build_actions()
        try:
            if sf is not None:
                sf._update_scrollregion()  # type: ignore
        except Exception:
            pass
        # populate
        if self._vehicle is not None:
            try:
                self._populate_from_vehicle(self._vehicle)  # type: ignore[arg-type]
            except Exception:
                pass
            try:
                tc = getattr(self._vehicle, "torque_curve", ())
                self._populate_tree(tc)  # type: ignore[arg-type]
            except Exception:
                pass
        self._validate_all()
        # initial preview
        try:
            self._redraw_preview()
        except Exception:
            pass
        try:
            self._update_vehicle_graphs()
        except Exception:
            pass

    # -- entries -----------------------------------------------------------
    def _build_entries(self) -> None:
        parent = getattr(self, "_scroll", None)
        try:
            if parent is not None and hasattr(parent, "inner"):
                container = ttk.Frame(parent.inner)  # type: ignore
            else:
                container = ttk.Frame(self)
        except Exception:
            container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=4, pady=4)
        self._entries_container = container  # type: ignore
        # create 3 columns for groups: left Mass/Aero/Derived, middle Tire, right Engine/Gear
        # but pack vertically for simplicity with grouping label
        for gname, fields in GROUPS.items():
            lf = ttk.LabelFrame(container, text=f"{gname} ({len(fields)}項目)")
            lf.pack(fill="x", padx=4, pady=3)
            self._group_frames[gname] = lf
            for idx, key in enumerate(fields):
                # For torque_curve, we create an Entry that mirrors Treeview count but also keep Treeview canonical
                # ratio_gearbox is comma-separated
                r = idx // 2
                c = (idx % 2) * 2
                ttk.Label(lf, text=key).grid(row=r, column=c, sticky="e", padx=4, pady=2)
                var = tk.StringVar(self, value="")
                ent = ttk.Entry(lf, textvariable=var, width=20)
                ent.grid(row=r, column=c + 1, sticky="w", padx=4, pady=2)
                ent.bind("<KeyRelease>", lambda _e, k=key: self._on_entry_change(k))
                ent.bind("<FocusOut>", lambda _e, k=key: self._on_entry_change(k))
                try:
                    var.trace_add("write", lambda *_a, k=key: self._on_entry_change(k))
                except Exception:
                    try:
                        var.trace("w", lambda *_a, k=key: self._on_entry_change(k))  # type: ignore
                    except Exception:
                        pass
                self.vars[key] = var
                self.entries[key] = ent
            for i in range(4):
                try:
                    lf.grid_columnconfigure(i, weight=1 if i % 2 == 1 else 0)
                except Exception:
                    pass

    def _populate_from_vehicle(self, v: object) -> None:
        for key in ALL_FIELDS:
            try:
                val = getattr(v, key)  # type: ignore
                if key == "ratio_gearbox":
                    # tuple -> comma
                    if isinstance(val, (list, tuple)):
                        txt = ",".join(str(float(x)) for x in val)  # type: ignore
                    else:
                        txt = str(val)
                    self.vars[key].set(txt)
                elif key == "torque_curve":
                    # torque_curve entry shows count
                    if isinstance(val, (list, tuple)):
                        txt = f"{len(val)} points"
                    else:
                        txt = str(val)
                    self.vars[key].set(txt)
                else:
                    # numeric or string
                    if isinstance(val, float) and (math.isinf(val) or math.isnan(val)):
                        self.vars[key].set(str(val))
                    else:
                        self.vars[key].set(str(val))
            except Exception:
                self.vars[key].set("")

    # -- validation --------------------------------------------------------
    def _is_field_valid(self, key: str, text: str) -> bool:
        s = text.strip()
        if key == "torque_curve":
            # valid if Treeview has >=1 row and <=? 18 expected but allow >=1
            try:
                n = len(self.tree.get_children()) if hasattr(self, "tree") else 0
                return n >= 1
            except Exception:
                return False
        if key in STRING_FIELDS:
            return len(s) > 0
        if key == "ratio_gearbox":
            if s == "":
                return False
            parts = [p.strip() for p in s.split(",")]
            if not parts:
                return False
            for p in parts:
                try:
                    v = float(p)
                except Exception:
                    return False
                if not math.isfinite(v) or v <= 0:
                    return False
            return True
        # numeric fields
        if s == "":
            return False
        try:
            val = float(s)
        except Exception:
            return False
        if not math.isfinite(val):
            return False
        # per-key ranges
        if key in ("M", "mass_kg"):
            return 0 < val < 1e6
        if key in ("df", "da"):
            return 0.0 < val < 1.0
        if key in ("L", "wheelbase_m"):
            return 0.0 < val < 10.0
        if key == "rack":
            return 0 < val < 100
        if key == "cog_height_m":
            return 0.0 < val < 5.0
        if key == "Cl":
            return -20 < val < 20
        if key == "Cd":
            return -10 < val < 10
        if key in ("factor_Cl", "factor_Cd", "factor_grip", "factor_power"):
            return 0 < val < 10
        if key == "A":
            return 0 < val < 10
        if key == "rho":
            return 0 < val < 10
        if key in ("br_disc_d", "br_pad_h", "br_pist_d", "br_mast_d", "tyre_radius"):
            return 0 < val < 5
        if key == "br_pad_mu":
            return 0 < val < 5
        if key == "br_nop":
            return 0 < val < 32
        if key == "br_ped_r":
            return 0 < val < 20
        if key == "Cr":
            return -1 < val < 1
        if key in ("mu_x", "mu_y"):
            return 0 < val < 10
        if key in ("mu_x_M", "mu_y_M"):
            return 0 < val < 1e4
        if key in ("sens_x", "sens_y"):
            return -1 < val < 1
        if key in ("CF", "CR"):
            return 0 < val < 1e6
        if key == "n_thermal":
            return 0 < val < 1
        if key == "fuel_LHV":
            return 0 < val < 1e9
        if key == "shift_time":
            return 0 <= val < 10
        if key in ("n_primary", "n_final", "n_gearbox"):
            return 0 < val <= 1.5
        if key in ("ratio_primary", "ratio_final"):
            return 0 < val < 50
        if key == "cda":
            return 0 <= val < 10
        return True

    def _on_entry_change(self, key: str) -> None:
        try:
            ent = self.entries.get(key)
            if ent is None:
                return
            txt = self.vars[key].get()
            ok = self._is_field_valid(key, txt)
            try:
                if ok:
                    ent.configure(style="TEntry")
                else:
                    ent.configure(style="Invalid.TEntry")
            except Exception:
                pass
            self._update_save_state()
        except Exception:
            pass

    def _validate_all(self) -> bool:
        ok_all = True
        for key in ALL_FIELDS:
            try:
                txt = self.vars[key].get() if key in self.vars else ""
                # skip torque_curve Entry styling? still validate but not style torque_curve entry maybe
                ok = self._is_field_valid(key, txt)
                ent = self.entries.get(key)
                if ent is not None:
                    try:
                        ent.configure(style="TEntry" if ok else "Invalid.TEntry")
                    except Exception:
                        pass
                if not ok:
                    ok_all = False
            except Exception:
                ok_all = False
        # also check torque tree has rows (already covered via torque_curve but ensure)
        try:
            if hasattr(self, "tree") and len(self.tree.get_children()) == 0:
                ok_all = False
        except Exception:
            pass
        self._update_save_state(ok_all)
        return ok_all

    def _update_save_state(self, ok: bool | None = None) -> None:
        if ok is None:
            ok = True
            for k in ALL_FIELDS:
                if k not in self.vars:
                    continue
                if not self._is_field_valid(k, self.vars[k].get()):
                    ok = False
                    break
            if ok:
                try:
                    if hasattr(self, "tree") and len(self.tree.get_children()) == 0:
                        ok = False
                except Exception:
                    pass
        if self._save_btn is not None:
            try:
                self._save_btn.configure(state="normal" if ok else "disabled")
            except Exception:
                pass

    # -- torque table ------------------------------------------------------
    def _build_torque_table(self) -> None:
        parent = getattr(self, "_scroll", None)
        try:
            base = parent.inner if parent is not None and hasattr(parent, "inner") else self  # type: ignore
        except Exception:
            base = self
        frm = ttk.LabelFrame(base, text="トルクカーブ (rpm, Nm) 18点")
        frm.pack(fill="both", expand=True, padx=8, pady=6)
        self.tree = ttk.Treeview(frm, columns=("rpm", "Nm"), show="headings", height=8, selectmode="extended")
        self.tree.heading("rpm", text="rpm")
        self.tree.heading("Nm", text="Nm")
        self.tree.column("rpm", width=120, anchor="e")
        self.tree.column("Nm", width=120, anchor="e")
        self.tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        try:
            sb = ttk.Scrollbar(frm, orient="vertical", command=self.tree.yview)
            self.tree.configure(yscrollcommand=sb.set)
            sb.pack(side="left", fill="y", pady=4)
        except Exception:
            pass
        ctrl = ttk.Frame(frm)
        ctrl.pack(side="right", fill="y", padx=6, pady=4)
        ttk.Label(ctrl, text="rpm").pack(anchor="w")
        self._rpm_var = tk.StringVar(self, value="")
        self._rpm_entry = ttk.Entry(ctrl, textvariable=self._rpm_var, width=10)
        self._rpm_entry.pack(anchor="w", pady=(0, 6))
        ttk.Label(ctrl, text="Nm").pack(anchor="w")
        self._nm_var = tk.StringVar(self, value="")
        self._nm_entry = ttk.Entry(ctrl, textvariable=self._nm_var, width=10)
        self._nm_entry.pack(anchor="w", pady=(0, 8))
        self._add_btn = ttk.Button(ctrl, text="Add", command=self._on_add)
        self._add_btn.pack(fill="x", pady=2)
        self._del_btn = ttk.Button(ctrl, text="Delete", command=self._on_delete)
        self._del_btn.pack(fill="x", pady=2)
        self.btn_add = self._add_btn
        self.btn_delete = self._del_btn
        self.entry_rpm = self._rpm_entry
        self.entry_nm = self._nm_entry
        # bind tree selection to update preview
        try:
            self.tree.bind("<<TreeviewSelect>>", lambda _e: self._redraw_preview())
        except Exception:
            pass
        # --- inline cell editor (Excel-like) state ---
        self._cell_editor: tk.Entry | ttk.Entry | None = None  # type: ignore
        self._cell_editor_item: str | None = None
        self._cell_editor_column: str | None = None
        self._cell_editor_old_value: str = ""
        # bindings for direct editing
        try:
            self.tree.bind("<Double-Button-1>", self._on_tree_double_click)
        except Exception:
            pass
        try:
            self.tree.bind("<Return>", self._on_tree_return)
            self.tree.bind("<KP_Enter>", self._on_tree_return)
        except Exception:
            pass
        try:
            self.tree.bind("<F2>", self._on_tree_f2)
        except Exception:
            pass
        try:
            self.tree.bind("<Tab>", self._on_tree_tab)
            self.tree.bind("<ISO_Left_Tab>", self._on_tree_tab)
            self.tree.bind("<Shift-Tab>", self._on_tree_tab)
        except Exception:
            pass
        # Up/Down navigation when not editing is default; still bind to handle editing state cleanly
        try:
            self.tree.bind("<Up>", self._on_tree_arrow)
            self.tree.bind("<Down>", self._on_tree_arrow)
        except Exception:
            pass
        # commit/cancel if focus leaves tree while editing (safety)
        try:
            self.tree.bind("<Button-1>", self._on_tree_button1, add="+")
        except Exception:
            pass
        try:
            self.tree.bind("<Control-a>", self._on_tree_select_all)
            self.tree.bind("<Control-A>", self._on_tree_select_all)
            self.tree.bind("<Command-a>", self._on_tree_select_all)
            self.tree.bind("<Command-A>", self._on_tree_select_all)
        except Exception:
            pass

    def _build_vehicle_graphs(self) -> None:
        try:
            host = getattr(self, "_chart_host", None)
            if host is not None:
                base = ttk.Frame(host)
                try:
                    host.add(base, weight=2)
                except Exception:
                    base.pack(fill="both", expand=True, padx=8, pady=6)
            else:
                parent = getattr(self, "_scroll", None)
                try:
                    base = parent.inner if parent is not None and hasattr(parent, "inner") else self  # type: ignore
                except Exception:
                    base = self
            self.graph_notebook = ttk.Notebook(base)
            self.graph_notebook.pack(fill="both", expand=True, padx=8, pady=6)
            self._graph_notebook = self.graph_notebook
            self.chart_notebook = self.graph_notebook
            self.tab_torque = ttk.Frame(self.graph_notebook)
            self.tab_gear = ttk.Frame(self.graph_notebook)
            self.tab_fx = ttk.Frame(self.graph_notebook)
            self.tab_ggv = ttk.Frame(self.graph_notebook)
            try:
                self.graph_notebook.add(self.tab_torque, text="トルク・パワー")
            except Exception:
                pass
            try:
                self.graph_notebook.add(self.tab_gear, text="ギア")
            except Exception:
                pass
            try:
                self.graph_notebook.add(self.tab_fx, text="Fx包絡")
            except Exception:
                pass
            try:
                self.graph_notebook.add(self.tab_ggv, text="GGV")
            except Exception:
                pass
            try:
                from openlapexe.gui.charts_vehicle import VehicleTorqueChart as _VTorque  # type: ignore
                self.vehicle_torque_chart = _VTorque(self.tab_torque)
                self.vehicle_torque_chart.pack(fill="both", expand=True, padx=2, pady=2)
            except Exception:
                try:
                    ttk.Label(self.tab_torque, text="トルク・パワー (読込失敗)", foreground="#888").pack(expand=True)
                except Exception:
                    pass
                self.vehicle_torque_chart = None  # type: ignore
            try:
                from openlapexe.gui.charts_vehicle import VehicleGearChart as _VGear  # type: ignore
                self.vehicle_gear_chart = _VGear(self.tab_gear)
                self.vehicle_gear_chart.pack(fill="both", expand=True, padx=2, pady=2)
            except Exception:
                try:
                    ttk.Label(self.tab_gear, text="ギア (読込失敗)", foreground="#888").pack(expand=True)
                except Exception:
                    pass
                self.vehicle_gear_chart = None  # type: ignore
            try:
                from openlapexe.gui.charts_vehicle import VehicleFxChart as _VFx  # type: ignore
                self.vehicle_fx_chart = _VFx(self.tab_fx)
                self.vehicle_fx_chart.pack(fill="both", expand=True, padx=2, pady=2)
            except Exception:
                try:
                    ttk.Label(self.tab_fx, text="Fx包絡 (読込失敗)", foreground="#888").pack(expand=True)
                except Exception:
                    pass
                self.vehicle_fx_chart = None  # type: ignore
            try:
                from openlapexe.gui.charts_vehicle import VehicleGGVChart as _VGGV  # type: ignore
                self.vehicle_ggv_chart = _VGGV(self.tab_ggv)
                self.vehicle_ggv_chart.pack(fill="both", expand=True, padx=2, pady=2)
            except Exception:
                try:
                    ttk.Label(self.tab_ggv, text="GGV (読込失敗)", foreground="#888").pack(expand=True)
                except Exception:
                    pass
                self.vehicle_ggv_chart = None  # type: ignore
            try:
                self.graph_notebook.bind("<<NotebookTabChanged>>", lambda _e: self._redraw_vehicle_graphs())
            except Exception:
                pass
        except Exception:
            try:
                self.graph_notebook = None  # type: ignore
            except Exception:
                pass

    def _redraw_vehicle_graphs(self) -> None:
        for _nm in ("vehicle_torque_chart", "vehicle_gear_chart", "vehicle_fx_chart", "vehicle_ggv_chart"):
            try:
                _ch = getattr(self, _nm, None)
                if _ch is not None:
                    _rd = getattr(_ch, "_redraw", None)
                    if callable(_rd):
                        _rd()
            except Exception:
                pass

    def _update_vehicle_graphs(self, vehicle: object | None = None) -> None:
        v = vehicle if vehicle is not None else self._vehicle
        if v is None:
            try:
                if _Vehicle47 is not None:
                    v = _Vehicle47.from_json("f1")  # type: ignore
            except Exception:
                v = None
        if v is None:
            return
        for _nm in ("vehicle_torque_chart", "vehicle_gear_chart", "vehicle_fx_chart", "vehicle_ggv_chart"):
            try:
                _ch = getattr(self, _nm, None)
                if _ch is not None:
                    try:
                        _ch.set_vehicle(v)  # type: ignore
                    except Exception:
                        try:
                            _ch.plot(v)  # type: ignore
                        except Exception:
                            pass
            except Exception:
                pass

    def _populate_tree(self, curve: tuple[tuple[float, float], ...] | list[tuple[float, float]] | list[dict[str, float]]) -> None:
        try:
            for iid in list(self.tree.get_children()):
                self.tree.delete(iid)
        except Exception:
            pass
        for pt in curve:  # type: ignore
            try:
                if isinstance(pt, dict):
                    rpm_v = float(pt.get("rpm", pt.get("x", 0)))  # type: ignore
                    nm_v = float(pt.get("torque_nm", pt.get("torque", pt.get("y", 0))))  # type: ignore
                elif isinstance(pt, (list, tuple)):
                    rpm_v = float(pt[0])  # type: ignore
                    nm_v = float(pt[1])  # type: ignore
                else:
                    continue
                self.tree.insert("", "end", values=(str(float(rpm_v)), str(float(nm_v))))
            except Exception:
                pass
        # update torque_curve entry text
        try:
            n = len(self.tree.get_children())
            self.vars["torque_curve"].set(f"{n} points")
        except Exception:
            pass
        try:
            self._redraw_preview()
        except Exception:
            pass
        try:
            self._update_vehicle_graphs()
        except Exception:
            pass

    def _on_add(self) -> None:
        try:
            if getattr(self, "_cell_editor", None) is not None:
                try:
                    self._commit_cell_edit(move_next=None)
                    if getattr(self, "_cell_editor", None) is not None:
                        return
                except Exception:
                    pass
            rpm_s = self._rpm_var.get().strip()
            nm_s = self._nm_var.get().strip()
            try:
                rpm_v = float(rpm_s)
                nm_v = float(nm_s)
            except Exception as e:
                try:
                    messagebox.showerror("Error", f"数値を入力してください: {e}", parent=self)
                except Exception:
                    pass
                return
            if not (math.isfinite(rpm_v) and math.isfinite(nm_v)):
                try:
                    messagebox.showerror("Error", "有限値を入力してください", parent=self)
                except Exception:
                    pass
                return
            if rpm_v <= 0 or nm_v < 0:
                try:
                    messagebox.showerror("Error", "rpm>0, Nm>=0 で入力", parent=self)
                except Exception:
                    pass
                return
            self.tree.insert("", "end", values=(str(rpm_v), str(nm_v)))
            self._rpm_var.set("")
            self._nm_var.set("")
            self._validate_all()
            self._redraw_preview()
            try:
                self._update_vehicle_graphs()
            except Exception:
                pass
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                pass

    def _on_delete(self) -> None:
        try:
            if getattr(self, "_cell_editor", None) is not None:
                try:
                    self._cancel_cell_edit()
                except Exception:
                    pass
            sel = list(self.tree.selection())
            if not sel:
                children = list(self.tree.get_children())
                if children:
                    sel = [children[-1]]
                else:
                    try:
                        messagebox.showerror("Error", "削除する行を選択してください", parent=self)
                    except Exception:
                        pass
                    return
            for iid in sel:
                try:
                    self.tree.delete(iid)
                except Exception:
                    pass
            self._validate_all()
            self._redraw_preview()
            try:
                self._update_vehicle_graphs()
            except Exception:
                pass
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                pass

    def _on_tree_double_click(self, event: tk.Event) -> str | None:  # type: ignore
        try:
            if self._cell_editor is not None:
                try:
                    self._commit_cell_edit(move_next=None)
                except Exception:
                    pass
                if self._cell_editor is not None:
                    return "break"
            row = self.tree.identify_row(event.y)  # type: ignore
            col = self.tree.identify_column(event.x)  # type: ignore
            if not row:
                return None
            if col == "#0":
                col = "#1"
            try:
                col_idx = int(col[1:]) - 1
                cols = list(self.tree["columns"])  # type: ignore
                if 0 <= col_idx < len(cols):
                    column = str(cols[col_idx])
                else:
                    return None
            except Exception:
                return None
            self._start_cell_edit(row, column)
            return "break"
        except Exception:
            return None

    def _on_tree_return(self, event: tk.Event) -> str | None:  # type: ignore
        try:
            if self._cell_editor is not None:
                is_shift = bool(event.state & 0x0001)  # Shift mask
                move = "shift_enter" if is_shift else "enter"
                self._commit_cell_edit(move_next=move)
                return "break"
            sel = list(self.tree.selection())
            if not sel:
                children = list(self.tree.get_children())
                if not children:
                    return None
                sel = [children[0]]
            item = sel[0]
            foc = self.tree.focus()
            col = "rpm"
            if foc and foc in sel:
                item = foc
            # try to detect focused column via selection? default to rpm
            try:
                # if a cell was previously edited, reuse its column
                if self._cell_editor_column in ("rpm", "Nm"):
                    col = str(self._cell_editor_column)
            except Exception:
                pass
            self._start_cell_edit(item, col)
            return "break"
        except Exception:
            return None

    def _on_tree_f2(self, event: tk.Event) -> str | None:  # type: ignore
        try:
            if self._cell_editor is not None:
                return "break"
            sel = list(self.tree.selection())
            if not sel:
                children = list(self.tree.get_children())
                if not children:
                    return None
                sel = [children[0]]
            item = sel[0]
            try:
                foc = self.tree.focus()
                if foc and foc in self.tree.get_children():
                    item = foc
            except Exception:
                pass
            col = "rpm"
            try:
                if self._cell_editor_column in ("rpm", "Nm"):
                    col = str(self._cell_editor_column)
            except Exception:
                pass
            self._start_cell_edit(item, col)
            return "break"
        except Exception:
            return None

    def _on_tree_tab(self, event: tk.Event) -> str | None:  # type: ignore
        try:
            if self._cell_editor is not None:
                is_shift = bool(event.state & 0x0001)
                move = "shift_tab" if is_shift else "tab"
                # editor handles Tab; tree Tab should also commit if editor present
                self._commit_cell_edit(move_next=move)
                return "break"
            # when not editing, prevent focus traversal? allow default but break to keep focus on tree
            return None
        except Exception:
            return None

    def _on_tree_arrow(self, event: tk.Event) -> str | None:  # type: ignore
        try:
            if self._cell_editor is not None:
                # let editor handle commit + navigation
                is_up = event.keysym == "Up"
                move = "shift_enter" if is_up else "enter"
                self._commit_cell_edit(move_next=move)
                return "break"
            return None
        except Exception:
            return None

    def _on_tree_button1(self, event: tk.Event) -> None:  # type: ignore
        try:
            if self._cell_editor is None:
                return
            # if click is inside editor, ignore
            # editor is child of tree; check if click target is editor
            row = self.tree.identify_row(event.y)  # type: ignore
            col = self.tree.identify_column(event.x)  # type: ignore
            cur_item = self._cell_editor_item
            cur_col = self._cell_editor_column
            if row == cur_item:
                try:
                    cols = list(self.tree["columns"])  # type: ignore
                    col_idx = int(col[1:]) - 1
                    if 0 <= col_idx < len(cols) and str(cols[col_idx]) == str(cur_col):
                        return
                except Exception:
                    pass
            # click elsewhere -> commit current
            self._commit_cell_edit(move_next=None)
        except Exception:
            pass

    def _on_tree_select_all(self, event: tk.Event) -> str | None:  # type: ignore
        try:
            if self._cell_editor is not None:
                return None
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

    def _start_cell_edit(self, item: str, column: str) -> None:
        try:
            if column not in ("rpm", "Nm"):
                return
            if item not in self.tree.get_children():
                return
            # cancel existing
            if self._cell_editor is not None:
                try:
                    self._cancel_cell_edit()
                except Exception:
                    pass
            self.tree.selection_set(item)
            self.tree.focus(item)
            try:
                self.tree.see(item)
                self.update_idletasks()
            except Exception:
                pass
            bbox = self.tree.bbox(item, column)  # type: ignore
            if not bbox:
                try:
                    self.tree.see(item)
                    self.update_idletasks()
                    bbox = self.tree.bbox(item, column)  # type: ignore
                except Exception:
                    bbox = ""
            if not bbox:
                return
            try:
                x, y, w, h = bbox  # type: ignore
            except Exception:
                return
            if w < 10:
                w = 80
            if h < 10:
                h = 20
            old_val = ""
            try:
                old_val = str(self.tree.set(item, column))  # type: ignore
            except Exception:
                old_val = ""
            self._cell_editor_item = item
            self._cell_editor_column = column
            self._cell_editor_old_value = old_val
            # use tk.Entry for reliable bg handling; parent is tree
            ed = tk.Entry(self.tree, width=10, justify="right")  # type: ignore
            self._cell_editor = ed  # type: ignore
            ed.insert(0, old_val)
            ed.selection_range(0, tk.END)
            ed.icursor(tk.END)
            try:
                ed.place(x=x, y=y, width=w, height=h)
            except Exception:
                try:
                    ed.place(x=x, y=y, width=w, height=h)
                except Exception:
                    return
            try:
                ed.focus_set()
            except Exception:
                pass
            # bind editor keys
            try:
                ed.bind("<Return>", lambda e: (self._commit_cell_edit(move_next="enter"), "break")[1])
                ed.bind("<KP_Enter>", lambda e: (self._commit_cell_edit(move_next="enter"), "break")[1])
                ed.bind("<Shift-Return>", lambda e: (self._commit_cell_edit(move_next="shift_enter"), "break")[1])
                ed.bind("<Shift-KP_Enter>", lambda e: (self._commit_cell_edit(move_next="shift_enter"), "break")[1])
                ed.bind("<Tab>", lambda e: (self._commit_cell_edit(move_next="tab"), "break")[1])
                ed.bind("<ISO_Left_Tab>", lambda e: (self._commit_cell_edit(move_next="shift_tab"), "break")[1])
                ed.bind("<Shift-Tab>", lambda e: (self._commit_cell_edit(move_next="shift_tab"), "break")[1])
                ed.bind("<Escape>", lambda e: (self._cancel_cell_edit(), "break")[1])
                ed.bind("<FocusOut>", self._on_editor_focus_out)
                # arrow keys inside editor commit + move
                ed.bind("<Up>", lambda e: (self._commit_cell_edit(move_next="shift_enter"), "break")[1])
                ed.bind("<Down>", lambda e: (self._commit_cell_edit(move_next="enter"), "break")[1])
            except Exception:
                pass
        except Exception:
            try:
                if self._cell_editor is not None:
                    self._cancel_cell_edit()
            except Exception:
                pass

    def _on_editor_focus_out(self, event: tk.Event) -> str | None:  # type: ignore
        try:
            if self._cell_editor is None:
                return None
            # delay check to avoid fighting with Tab/Return handlers
            try:
                w = event.widget  # type: ignore
                if w is not self._cell_editor:
                    return None
            except Exception:
                pass
            # if editor still exists (not already destroyed by commit), commit
            if self._cell_editor is not None:
                self._commit_cell_edit(move_next=None)
            return None
        except Exception:
            return None

    def _flash_editor_error(self) -> None:
        try:
            ed = self._cell_editor
            if ed is None:
                return
            try:
                ed.configure(bg="#ffcccc")  # type: ignore
            except Exception:
                try:
                    ed.configure(background="#ffcccc")  # type: ignore
                except Exception:
                    pass
            try:
                self.after(180, lambda: ed.configure(bg="white") if ed.winfo_exists() else None)  # type: ignore
            except Exception:
                pass
        except Exception:
            pass

    def _commit_cell_edit(self, move_next: str | None = None) -> str | None:  # type: ignore
        try:
            ed = self._cell_editor
            item = self._cell_editor_item
            column = self._cell_editor_column
            if ed is None or item is None or column is None:
                return None
            try:
                txt = str(ed.get()).strip()  # type: ignore
            except Exception:
                txt = ""
            # validation - Excel風: モーダルを出さず赤フラッシュ + エラーラベルで通知
            try:
                val = float(txt)
            except Exception:
                try:
                    if hasattr(self, "_error_var"):
                        self._error_var.set("数値を入力してください")
                except Exception:
                    pass
                self._flash_editor_error()
                try:
                    ed.focus_set()  # type: ignore
                    ed.selection_range(0, tk.END)  # type: ignore
                except Exception:
                    pass
                return "break"
            if not math.isfinite(val):
                try:
                    if hasattr(self, "_error_var"):
                        self._error_var.set("有限値を入力してください")
                except Exception:
                    pass
                self._flash_editor_error()
                try:
                    ed.focus_set()  # type: ignore
                    ed.selection_range(0, tk.END)  # type: ignore
                except Exception:
                    pass
                return "break"
            if column == "rpm":
                if val <= 0:
                    try:
                        if hasattr(self, "_error_var"):
                            self._error_var.set("rpm>0 で入力")
                    except Exception:
                        pass
                    self._flash_editor_error()
                    try:
                        ed.focus_set()  # type: ignore
                        ed.selection_range(0, tk.END)  # type: ignore
                    except Exception:
                        pass
                    return "break"
            else:
                if val < 0:
                    try:
                        if hasattr(self, "_error_var"):
                            self._error_var.set("Nm>=0 で入力")
                    except Exception:
                        pass
                    self._flash_editor_error()
                    try:
                        ed.focus_set()  # type: ignore
                        ed.selection_range(0, tk.END)  # type: ignore
                    except Exception:
                        pass
                    return "break"
            # success: update tree
            new_txt = str(float(val))
            # try to preserve integer-like display? keep as str(float)
            try:
                self.tree.set(item, column, new_txt)  # type: ignore
            except Exception:
                return "break"
            # destroy editor first
            try:
                ed.destroy()  # type: ignore
            except Exception:
                pass
            self._cell_editor = None
            self._cell_editor_item = None
            self._cell_editor_column = None
            self._cell_editor_old_value = ""
            try:
                self._validate_all()
            except Exception:
                pass
            try:
                self._redraw_preview()
            except Exception:
                pass
            try:
                self._update_vehicle_graphs()
            except Exception:
                pass
            try:
                if "torque_curve" in self.vars:
                    n = len(self.tree.get_children())
                    self.vars["torque_curve"].set(f"{n} points")
            except Exception:
                pass
            try:
                if hasattr(self, "_error_var"):
                    self._error_var.set("")
            except Exception:
                pass
            # navigation
            if move_next is not None:
                try:
                    children = list(self.tree.get_children())
                    if item not in children:
                        return "break"
                    idx = children.index(item)
                    next_item: str | None = None
                    next_col: str | None = None
                    if move_next == "tab":
                        if column == "rpm":
                            next_item = item
                            next_col = "Nm"
                        else:
                            if idx + 1 < len(children):
                                next_item = children[idx + 1]
                                next_col = "rpm"
                    elif move_next == "shift_tab":
                        if column == "Nm":
                            next_item = item
                            next_col = "rpm"
                        else:
                            if idx - 1 >= 0:
                                next_item = children[idx - 1]
                                next_col = "Nm"
                    elif move_next == "enter":
                        if idx + 1 < len(children):
                            next_item = children[idx + 1]
                            next_col = column
                    elif move_next == "shift_enter":
                        if idx - 1 >= 0:
                            next_item = children[idx - 1]
                            next_col = column
                    if next_item is not None and next_col is not None:
                        # schedule to avoid FocusOut double-commit
                        try:
                            self.after(10, lambda i=next_item, c=next_col: self._start_cell_edit(i, c))  # type: ignore
                        except Exception:
                            self._start_cell_edit(next_item, next_col)
                    else:
                        # no next: keep selection
                        try:
                            self.tree.selection_set(item)
                            self.tree.focus(item)
                        except Exception:
                            pass
                except Exception:
                    pass
            return "break"
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                pass
            return "break"

    def _cancel_cell_edit(self) -> str | None:  # type: ignore
        try:
            ed = self._cell_editor
            if ed is not None:
                try:
                    ed.destroy()  # type: ignore
                except Exception:
                    pass
            self._cell_editor = None
            self._cell_editor_item = None
            self._cell_editor_column = None
            self._cell_editor_old_value = ""
            try:
                self.tree.focus_set()
            except Exception:
                pass
            return "break"
        except Exception:
            self._cell_editor = None
            self._cell_editor_item = None
            self._cell_editor_column = None
            return "break"

    def add_torque(self, rpm: float | str, nm: float | str) -> bool:
        try:
            rv = float(rpm)  # type: ignore
            nv = float(nm)  # type: ignore
        except Exception:
            return False
        if not (math.isfinite(rv) and math.isfinite(nv)):
            return False
        if rv <= 0 or nv < 0:
            return False
        try:
            self.tree.insert("", "end", values=(str(rv), str(nv)))
            self._validate_all()
            self._redraw_preview()
            try:
                self._update_vehicle_graphs()
            except Exception:
                pass
            return True
        except Exception:
            return False

    def delete_selected(self) -> None:
        self._on_delete()

    def delete_torque_at(self, index: int = 0) -> bool:
        try:
            children = list(self.tree.get_children())
            if 0 <= index < len(children):
                self.tree.delete(children[index])
                self._validate_all()
                self._redraw_preview()
                try:
                    self._update_vehicle_graphs()
                except Exception:
                    pass
                return True
            return False
        except Exception:
            return False

    # -- PCHIP preview Canvas ----------------------------------------------
    def _build_preview(self) -> None:
        host = getattr(self, "_chart_host", None)
        if host is not None:
            frm = ttk.LabelFrame(host, text="PCHIPプレビュー")
            try:
                host.add(frm, weight=1)
            except Exception:
                frm.pack(fill="both", expand=True, padx=8, pady=6)
        else:
            parent = getattr(self, "_scroll", None)
            try:
                base = parent.inner if parent is not None and hasattr(parent, "inner") else self  # type: ignore
            except Exception:
                base = self
            frm = ttk.LabelFrame(base, text="PCHIPプレビュー")
            frm.pack(fill="both", expand=True, padx=8, pady=6)
        self.canvas = tk.Canvas(frm, bg="white", highlightthickness=1, highlightbackground="#ccc", height=160)
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self._preview_canvas = self.canvas
        # aliases for test discovery
        self.preview_canvas = self.canvas  # type: ignore
        self.pchip_canvas = self.canvas  # type: ignore
        self.canvas.bind("<Configure>", lambda _e: self._redraw_preview())

    def _get_torque_points(self) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        try:
            for iid in self.tree.get_children():
                vals = self.tree.item(iid, "values")
                if len(vals) >= 2:
                    try:
                        rpm_v = float(str(vals[0]).strip())
                        nm_v = float(str(vals[1]).strip())
                        if math.isfinite(rpm_v) and math.isfinite(nm_v):
                            pts.append((rpm_v, nm_v))
                    except Exception:
                        continue
        except Exception:
            pass
        pts.sort(key=lambda x: x[0])
        return pts

    def _redraw_preview(self) -> None:
        c = getattr(self, "canvas", None)
        if c is None:
            return
        try:
            c.delete("all")
        except Exception:
            return
        pts = self._get_torque_points()
        # canvas size
        try:
            w = int(c.winfo_width())
            h = int(c.winfo_height())
        except Exception:
            w = 400
            h = 160
        if w < 10:
            w = 400
        if h < 10:
            h = 160
        pad = 12
        if len(pts) < 2:
            try:
                c.create_text(w // 2, h // 2, text="トルク点 >=2 でプレビュー", fill="#888", anchor="center")
            except Exception:
                pass
            # still draw points if 1
            if len(pts) == 1:
                try:
                    c.create_oval(w // 2 - 3, h // 2 - 3, w // 2 + 3, h // 2 + 3, fill="#e63946", outline="")
                except Exception:
                    pass
            return
        # compute bounds
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        min_x = min(xs)
        max_x = max(xs)
        min_y = min(ys)
        max_y = max(ys)
        if max_x - min_x < 1e-9:
            max_x = min_x + 1.0
        if max_y - min_y < 1e-9:
            max_y = min_y + 1.0
            min_y = min_y - 1.0
        # add margin 5%
        rx = (max_x - min_x) * 0.05
        ry = (max_y - min_y) * 0.05
        min_x -= rx
        max_x += rx
        min_y -= ry
        max_y += ry
        avail_w = float(w - 2 * pad)
        avail_h = float(h - 2 * pad)
        scale_x = avail_w / (max_x - min_x) if (max_x - min_x) != 0 else 1.0
        scale_y = avail_h / (max_y - min_y) if (max_y - min_y) != 0 else 1.0

        def _px(x: float) -> float:
            return pad + (x - min_x) * scale_x

        def _py(y: float) -> float:
            return h - pad - (y - min_y) * scale_y

        # grid
        try:
            c.create_line(pad, h - pad, w - pad, h - pad, fill="#ddd", width=1)
            c.create_line(pad, pad, pad, h - pad, fill="#ddd", width=1)
        except Exception:
            pass
        # PCHIP interpolation for smooth curve (numpy only)
        try:
            if _pchip_interp is not None and len(pts) >= 2:
                arr_x = _np.array([p[0] for p in pts], dtype=float)
                arr_y = _np.array([p[1] for p in pts], dtype=float)
                x_new = _np.linspace(min(xs), max(xs), 120, dtype=float)
                y_new = _pchip_interp(arr_x, arr_y, x_new)  # type: ignore
                coords: list[float] = []
                for xv, yv in zip(x_new, y_new):
                    coords.append(float(_px(float(xv))))
                    coords.append(float(_py(float(yv))))
                if len(coords) >= 4:
                    c.create_line(*coords, fill="#1f4b99", width=2, smooth=False)
            else:
                # fallback linear
                coords = []
                for xv, yv in pts:
                    coords.append(_px(xv))
                    coords.append(_py(yv))
                if len(coords) >= 4:
                    c.create_line(*coords, fill="#1f4b99", width=2, smooth=False)
        except Exception:
            # fallback linear
            try:
                coords = []
                for xv, yv in pts:
                    coords.append(_px(xv))
                    coords.append(_py(yv))
                if len(coords) >= 4:
                    c.create_line(*coords, fill="#1f4b99", width=2, smooth=False)
            except Exception:
                pass
        # draw points
        for xv, yv in pts:
            try:
                x = _px(xv)
                y = _py(yv)
                c.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#e63946", outline="white")
            except Exception:
                pass
        # axis labels
        try:
            c.create_text(w - pad, h - pad + 2, text="rpm", anchor="ne", fill="#666", font=("TkDefaultFont", 7))
            c.create_text(pad, pad - 2, text="Nm", anchor="sw", fill="#666", font=("TkDefaultFont", 7))
        except Exception:
            pass

    # -- actions Save/Reset ------------------------------------------------
    def _build_actions(self) -> None:
        frm = ttk.Frame(self)
        frm.pack(side="bottom", fill="x", padx=8, pady=6)
        self._save_btn = ttk.Button(frm, text="Save", command=self._on_save)
        self._save_btn.pack(side="right", padx=4)
        self._reset_btn = ttk.Button(frm, text="Reset", command=self._on_reset)
        self._reset_btn.pack(side="right", padx=4)
        self.btn_save = self._save_btn
        self.btn_reset = self._reset_btn
        self.save_button = self._save_btn  # alias
        self.reset_button = self._reset_btn
        self._error_var = tk.StringVar(self, value="")
        self._error_label = ttk.Label(frm, textvariable=self._error_var, foreground="red")
        self._error_label.pack(side="left", padx=4)
        self.error_var = self._error_var
        self.error_label = self._error_label

    def _collect_data(self) -> dict[str, object] | None:
        if not self._validate_all():
            try:
                self._error_var.set("入力エラーを修正してください")
            except Exception:
                pass
            return None
        try:
            data: dict[str, object] = {}
            for k in ALL_FIELDS:
                if k == "torque_curve":
                    continue
                if k == "ratio_gearbox":
                    txt = self.vars[k].get().strip()
                    parts = [p.strip() for p in txt.split(",") if p.strip() != ""]
                    vals = [float(p) for p in parts]
                    data[k] = vals
                    continue
                txt = self.vars[k].get().strip()
                if k in STRING_FIELDS:
                    data[k] = txt
                else:
                    data[k] = float(txt)
            # torque
            curve: list[dict[str, float]] = []
            for iid in self.tree.get_children():
                vals = self.tree.item(iid, "values")
                rpm_v = float(str(vals[0]).strip())
                nm_v = float(str(vals[1]).strip())
                curve.append({"rpm": rpm_v, "torque_nm": nm_v})
            if len(curve) == 0:
                try:
                    messagebox.showerror("Error", "トルクカーブは1点以上必要です", parent=self)
                except Exception:
                    pass
                return None
            curve.sort(key=lambda d: float(d["rpm"]))  # type: ignore
            data["torque_curve"] = curve
            # ensure derived aliases are present: mass_kg etc already in data
            # Add lower-case aliases for backward compat? keep as is
            # Name/Type keep capitalized, also add name/type lower? not needed but keep both for compat
            if "Name" in data:
                data["name"] = data["Name"]
            if "Type" in data:
                data["type"] = data["Type"]
            # ensure MVP derived consistency? keep user's values as is
            return data
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                pass
            return None

    def _get_save_paths(self) -> list[pathlib.Path]:
        paths: list[pathlib.Path] = []
        try:
            p = _resource_path("data/vehicles/custom.json")
            paths.append(p)
        except Exception:
            pass
        try:
            proj = pathlib.Path(__file__).resolve().parents[3] / "data" / "vehicles" / "custom.json"
            if proj not in paths:
                paths.append(proj)
        except Exception:
            pass
        try:
            alt = pathlib.Path(__file__).resolve().parent.parent.parent.parent / "data" / "vehicles" / "custom.json"
            if alt not in paths:
                paths.append(alt)
        except Exception:
            pass
        try:
            cfg = pathlib.Path.home() / ".config" / "openlapexe" / "vehicles" / "custom.json"
            if cfg not in paths:
                paths.append(cfg)
        except Exception:
            pass
        seen: set[str] = set()
        uniq: list[pathlib.Path] = []
        for p in paths:
            s = str(p)
            if s not in seen:
                seen.add(s)
                uniq.append(p)
        return uniq

    def _vehicle_save_path(self, name: str) -> pathlib.Path:
        stem = str(name).strip().removesuffix(".json") or "custom"
        safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in stem).strip("_") or "custom"
        try:
            p = _resource_path(f"data/vehicles/{safe}.json")
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass
        try:
            proj = pathlib.Path(__file__).resolve().parents[3] / "data" / "vehicles" / f"{safe}.json"
            proj.parent.mkdir(parents=True, exist_ok=True)
            return proj
        except Exception:
            pass
        return pathlib.Path(__file__).resolve().parents[2] / "data" / "vehicles" / f"{safe}.json"

    def _on_save(self) -> None:
        try:
            data = self._collect_data()
            if data is None:
                try:
                    messagebox.showerror("Error", "保存ブロック: 入力を修正してください", parent=self)
                except Exception:
                    pass
                return
            default_name = str(data.get("Name") or data.get("name") or "custom").strip() or "custom"
            name: str | None = None
            try:
                from tkinter import simpledialog as _sd  # type: ignore
                try:
                    name = _sd.askstring("保存", "車両名を入力してください", initialvalue=default_name, parent=self)
                except TypeError:
                    name = _sd.askstring("保存", "車両名を入力してください", initialvalue=default_name)
                except Exception:
                    name = None
            except Exception:
                name = None
            if name is None:
                return
            raw = str(name).strip()
            if not raw:
                try:
                    messagebox.showwarning("警告", "名前を入力してください", parent=self)
                except Exception:
                    try:
                        messagebox.showwarning("警告", "名前を入力してください", parent=self)
                    except Exception:
                        pass
                return
            stem = raw.removesuffix(".json")
            safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in stem).strip("_") or "custom"
            path = self._vehicle_save_path(safe)
            try:
                data["Name"] = safe
                data["name"] = safe
            except Exception:
                pass
            _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            saved = path
            try:
                self._error_var.set("")
            except Exception:
                pass
            try:
                cb = getattr(self, "on_vehicle_saved", None)
                if callable(cb):
                    try:
                        cb(safe)
                    except TypeError:
                        cb()
            except Exception:
                pass
            try:
                messagebox.showinfo("保存", f"保存しました: {saved}", parent=self)
            except Exception:
                try:
                    messagebox.showinfo("保存", f"保存しました: {saved}", parent=self)
                except Exception:
                    pass
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                try:
                    messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
                except Exception:
                    pass

    def _on_reset(self) -> None:
        try:
            if _Vehicle47 is None:
                raise RuntimeError("Vehicle47 not available")
            v = _Vehicle47.from_json("f1")  # type: ignore
            self._vehicle = v
            self._populate_from_vehicle(v)
            self._populate_tree(getattr(v, "torque_curve", ()))
            self._validate_all()
            try:
                self._update_vehicle_graphs(v)
            except Exception:
                pass
            try:
                self._error_var.set("")
            except Exception:
                pass
        except Exception as e:
            try:
                messagebox.showwarning("警告", f"車両データが破損しているため既定値を使用します:\n{e}", parent=self)
            except Exception:
                try:
                    messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
                except Exception:
                    pass


# compat alias
VehicleEditor = VehicleEditor47

__all__ = ["VehicleEditor47", "VehicleEditor", "GROUPS", "ALL_FIELDS"]
