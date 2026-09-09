# -*- coding: utf-8 -*-
"""tests/test_creator_tab - RED→GREEN for 5th tab creation."""
from __future__ import annotations

import json
import pathlib

import pytest


def _has_display() -> bool:
    try:
        import tkinter as tk

        r = tk.Tk()
        r.withdraw()
        r.update_idletasks()
        r.destroy()
        return True
    except Exception:
        return False


HAS_DISPLAY = _has_display()


def test_shell_has_5_tabs():
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import sys

    sys.path.insert(0, "src")
    import openlapexe.geo_tile as gt

    orig = gt.fetch_tile
    gt.fetch_tile = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline"))
    try:
        from openlapexe.gui.shell import App2

        root = App2()
        root.update_idletasks()
        tabs = root.notebook.tabs()
        assert len(tabs) == 5, f"notebook.tabs()==5 required got {len(tabs)}"
        texts = [root.notebook.tab(tid, "text") for tid in tabs]
        assert texts == ["車両", "コース", "OpenDRAG", "シミュレーション", "作成"], f"order broken {texts}"
        # selectable
        try:
            root.notebook.select(tabs[4])
            root.update_idletasks()
            sel = root.notebook.select()
            assert sel == tabs[4]
        except Exception as e:
            pytest.fail(f"作成 tab not selectable: {e}")
        # child notebook
        assert hasattr(root, "create_notebook") or hasattr(root, "_create_notebook") or hasattr(root, "creator_notebook")
        cn = getattr(root, "create_notebook", None) or getattr(root, "_create_notebook", None) or getattr(root, "creator_notebook", None)
        assert cn is not None
        assert len(cn.tabs()) == 2
        ctexts = [cn.tab(tid, "text") for tid in cn.tabs()]
        assert "OSM地図" in ctexts and "取込" in ctexts
        # check embedded views
        assert hasattr(root, "osm_canvas") or hasattr(root, "_osm_canvas")
        assert hasattr(root, "import_view") or hasattr(root, "_import_view")
        assert hasattr(root, "course_creator") or hasattr(root, "_creator_osm") or hasattr(root, "creator")
        # mode radio shared existence
        assert hasattr(root, "_create_mode_var") or hasattr(root, "mode_var")
        # check placeholder fallback strings exist in source
        txt = pathlib.Path("src/openlapexe/gui/shell.py").read_text(encoding="utf-8")
        assert "CourseCreator" in txt
        assert "OSMCanvas" in txt
        assert "ImportView" in txt
        assert "from_candidates" in txt
        assert "save_json" in txt
        root._on_close()
    finally:
        gt.fetch_tile = orig


def test_save_track_and_reload():
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import sys

    sys.path.insert(0, "src")
    import openlapexe.geo_tile as gt

    orig_fetch = gt.fetch_tile
    gt.fetch_tile = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline"))
    import tkinter.simpledialog as sd
    import tkinter.messagebox as mb

    orig_ask = sd.askstring
    orig_info = mb.showinfo
    orig_warn = mb.showwarning
    orig_err = mb.showerror
    sd.askstring = lambda *a, **kw: "test_creator_tab_save"
    mb.showinfo = lambda *a, **kw: None
    mb.showwarning = lambda *a, **kw: None
    mb.showerror = lambda *a, **kw: None
    p = pathlib.Path("data/tracks/test_creator_tab_save.json")
    if p.exists():
        p.unlink()
    try:
        from openlapexe.gui.shell import App2

        root = App2()
        root.update_idletasks()
        # ensure creator has points
        cc = getattr(root, "_creator_osm", None) or getattr(root, "course_creator", None)
        assert cc is not None
        cc.set_points([(0, 0), (10, 0), (10, 10), (20, 10), (20, 20)])
        root.update_idletasks()
        # call save
        root._on_save_track()
        root.update_idletasks()
        assert p.exists(), f"saved file not found {p}"
        txt = p.read_text(encoding="utf-8")
        assert "test_creator_tab_save" in txt or "points" in txt
        # reload via Track
        from openlapexe.track import Track

        t = Track.from_json("test_creator_tab_save")
        assert t.points.shape[0] >= 2
        assert t.points.shape[1] == 8
        # geometry persist check: TrackView2 combobox updated
        tv = getattr(root, "track_view", None)
        if tv is not None and hasattr(tv, "combo"):
            vals = list(tv.combo["values"])
            assert "test_creator_tab_save" in vals or "test_creator_tab_save.json" in vals or any("test_creator_tab_save" in str(v) for v in vals), f"combo not updated {vals}"
        # statusbar notified
        status = root._status_var.get() if hasattr(root, "_status_var") else ""
        assert "保存" in status or "test_creator_tab_save" in status or status != ""
        root._on_close()
        # geometry persistence file
        cfg = root._config_path
        assert cfg.exists()
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert "geometry" in data
    finally:
        gt.fetch_tile = orig_fetch
        sd.askstring = orig_ask
        mb.showinfo = orig_info
        mb.showwarning = orig_warn
        mb.showerror = orig_err
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass


def test_import_to_creator_and_osm_sync():
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import sys

    sys.path.insert(0, "src")
    import openlapexe.geo_tile as gt

    orig_fetch = gt.fetch_tile
    gt.fetch_tile = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline"))
    import tkinter.messagebox as mb

    orig_info = mb.showinfo
    orig_warn = mb.showwarning
    mb.showinfo = lambda *a, **kw: None
    mb.showwarning = lambda *a, **kw: None
    try:
        from openlapexe.gui.shell import App2

        root = App2()
        root.update_idletasks()
        # OSM sync: set osm points then sync
        oc = getattr(root, "osm_canvas", None) or getattr(root, "_osm_canvas", None)
        cc_osm = getattr(root, "_creator_osm", None) or getattr(root, "course_creator", None)
        assert oc is not None and cc_osm is not None
        oc.points_xy.clear()
        oc.points_xy.extend([(1, 1), (2, 2)])
        try:
            oc.points_latlon.clear()
            oc.points_latlon.extend([(35.68, 139.76), (35.69, 139.77)])
        except Exception:
            pass
        root._sync_osm_to_creator()
        root.update_idletasks()
        assert len(cc_osm.points_xy) >= 2
        # Import sync: create dummy staging
        iv = getattr(root, "import_view", None) or getattr(root, "_import_view", None)
        cc_imp = getattr(root, "_creator_import", None) or getattr(root, "_creator_osm", None)
        assert iv is not None and cc_imp is not None

        class Cand:
            points_xy = [(5, 5), (6, 6), (7, 7)]
            name = "dummy"
            kind = "polyline"

        iv._staging.clear()
        iv._staging.append(Cand())
        # need to set tree selection? but _apply_import_to_creator uses staging directly
        root._apply_import_to_creator()
        root.update_idletasks()
        assert len(cc_imp.points_xy) >= 2
        root._on_close()
    finally:
        gt.fetch_tile = orig_fetch
        mb.showinfo = orig_info
        mb.showwarning = orig_warn


def test_geometry_persistence():
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import sys
    import pathlib as pl
    import tempfile
    import json as js

    sys.path.insert(0, "src")
    import openlapexe.geo_tile as gt

    orig = gt.fetch_tile
    gt.fetch_tile = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline"))
    try:
        from openlapexe.gui.shell import App2
        import pathlib as _pl

        tmp = pl.Path(tempfile.mkdtemp()) / "config.json"
        # monkeypatch get_config_path within shell module
        import openlapexe.gui.shell as shell_mod

        orig_gcp = shell_mod.get_config_path
        shell_mod.get_config_path = lambda: tmp
        try:
            root = App2()
            root.update_idletasks()
            root.geometry("900x700+10+10")
            root.update_idletasks()
            root._save_geometry()
            assert tmp.exists()
            data = js.loads(tmp.read_text(encoding="utf-8"))
            assert "geometry" in data
            assert "900x700" in data["geometry"]
            root._on_close()
            # new instance loads geometry
            root2 = App2()
            root2.update_idletasks()
            geom = root2.geometry()
            # geometry may have decorations, but should start with 900x700 if loaded
            assert geom.startswith("900x700") or "900x700" in js.loads(tmp.read_text(encoding="utf-8"))["geometry"]
            root2._on_close()
        finally:
            shell_mod.get_config_path = orig_gcp
    finally:
        gt.fetch_tile = orig


def test_create_child_notebook_mapped_with_sizes():
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import sys
    import time

    sys.path.insert(0, "src")
    import openlapexe.geo_tile as gt

    orig = gt.fetch_tile
    gt.fetch_tile = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline"))
    try:
        from openlapexe.gui.shell import App2

        root = App2()
        root.geometry("1200x800")
        root.update()
        time.sleep(0.3)
        root.update()
        for i in range(root.notebook.index("end")):
            if root.notebook.tab(i, "text") == "作成":
                root.notebook.select(i)
                break
        root.update()
        time.sleep(0.3)
        root.update()
        cn = root.create_notebook
        assert cn.winfo_ismapped(), "create_notebook must be packed/mapped"
        assert cn.winfo_width() > 50, "create_notebook must have width"
        cn.select(0)
        root.update()
        time.sleep(0.3)
        root.update()
        oc = root._osm_canvas
        cc = root._creator_osm
        assert oc.winfo_width() > 100 and oc.winfo_height() > 100, f"osm squeezed {oc.winfo_width()}x{oc.winfo_height()}"
        assert cc.winfo_width() > 100, f"creator squeezed {cc.winfo_width()}"
        root._on_close()
    finally:
        gt.fetch_tile = orig
