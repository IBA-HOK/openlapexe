# -*- coding: utf-8 -*-
"""GUI shell tests - headless skipable."""
from __future__ import annotations

import json
import pathlib
import sys

import pytest


def _can_create_tk() -> bool:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:
        return False


def _create_app(monkeypatch=None, tmp_config=None):
    """Create App instance; skip on headless. Optionally patch config path."""
    import tkinter as tk

    try:
        import app as app_module
    except Exception as e:
        pytest.fail(f"import app failed: {e}")

    # patch get_config_path if tmp_config provided
    if tmp_config is not None and monkeypatch is not None:
        monkeypatch.setattr(app_module, "get_config_path", lambda: pathlib.Path(tmp_config))

    try:
        inst = app_module.App()
        # ensure window is realized
        try:
            inst.update_idletasks()
        except tk.TclError:
            pass
        return inst
    except tk.TclError as e:
        pytest.skip(f"headless environment (TclError): {e}")
    except Exception as e:
        # unexpected
        raise


# ---------------------------------------------------------------------------
# encoding & module-level guards
# ---------------------------------------------------------------------------

def test_encoding_utf8_declared() -> None:
    p = pathlib.Path(__file__).resolve().parent.parent / "app.py"
    text = p.read_text(encoding="utf-8")
    assert "coding" in text and "utf-8" in text, "encoding utf-8 header missing"


def test_excepthook_maintained() -> None:
    import app as app_module

    assert hasattr(app_module, "_excepthook")
    assert sys.excepthook is app_module._excepthook


def test_resource_path_exists_and_callable() -> None:
    import app as app_module

    assert hasattr(app_module, "resource_path")
    assert callable(app_module.resource_path)
    # resource_path integration: should return Path under base
    rp = app_module.resource_path("app.py")
    assert isinstance(rp, pathlib.Path)
    assert rp.name == "app.py"


def test_get_config_path_exists() -> None:
    import app as app_module

    assert hasattr(app_module, "get_config_path")
    p = app_module.get_config_path()
    assert isinstance(p, pathlib.Path)
    assert p.name == "config.json"


# ---------------------------------------------------------------------------
# GUI shell
# ---------------------------------------------------------------------------

def test_app_is_tk_subclass() -> None:
    import tkinter as tk

    app_inst = _create_app()
    try:
        assert isinstance(app_inst, tk.Tk)
    finally:
        try:
            app_inst.destroy()
        except Exception:
            pass


def test_default_geometry_800x600(monkeypatch, tmp_path) -> None:
    app_inst = _create_app(monkeypatch=monkeypatch, tmp_config=str(tmp_path / "config.json"))
    try:
        geom = app_inst.geometry()
        # geometry format "800x600+..." or "800x600"
        assert geom.startswith("800x600"), f"geometry should start with 800x600, got {geom}"
    finally:
        try:
            app_inst.destroy()
        except Exception:
            pass


def test_notebook_exists_with_3_japanese_tabs() -> None:
    import tkinter.ttk as ttk

    app_inst = _create_app()
    try:
        assert hasattr(app_inst, "notebook")
        assert isinstance(app_inst.notebook, ttk.Notebook)
        tabs = app_inst.notebook.tabs()
        assert len(tabs) == 3, f"expected 3 tabs, got {len(tabs)}"
        texts = [app_inst.notebook.tab(tid, "text") for tid in tabs]
        assert texts == ["車両", "コース", "シミュレーション"], f"Japanese tab labels required, got {texts}"
        # also check tab frame attributes
        assert hasattr(app_inst, "tab_vehicle")
        assert hasattr(app_inst, "tab_track")
        assert hasattr(app_inst, "tab_simulate")
    finally:
        try:
            app_inst.destroy()
        except Exception:
            pass


def test_tabs_contain_simple_display_no_entry() -> None:
    """全Entryでない単純表示のみ: tabs must not contain Entry widgets."""
    import tkinter as tk

    app_inst = _create_app()
    try:
        # If VehicleFrame is implemented, tab_vehicle is expected to contain entries.
        # This legacy check should then skip tab_vehicle and only verify other tabs.
        try:
            import app as _am

            has_vf = hasattr(_am, "VehicleFrame")
        except Exception:
            has_vf = False
        tabs_to_check = ("tab_vehicle", "tab_track", "tab_simulate")
        if has_vf:
            tabs_to_check = ("tab_track", "tab_simulate")
        for attr in tabs_to_check:
            frame = getattr(app_inst, attr)
            # walk descendants
            for child in frame.winfo_children():
                # recursively check
                stack = [child]
                while stack:
                    w = stack.pop()
                    assert w.winfo_class() != "TEntry", f"{attr} must not contain Entry, found in {w}"
                    try:
                        stack.extend(w.winfo_children())
                    except Exception:
                        pass
    finally:
        try:
            app_inst.destroy()
        except Exception:
            pass


def test_statusbar_exists_ttk() -> None:
    import tkinter.ttk as ttk
    import tkinter as tk

    app_inst = _create_app()
    try:
        # statusbar may be named statusbar/_statusbar/status_bar
        bar = None
        for name in ("statusbar", "_statusbar", "status_bar", "_status_bar", "status_frame"):
            if hasattr(app_inst, name):
                bar = getattr(app_inst, name)
                break
        # fallback: search for ttk.Frame/Label at bottom with relief or status var
        if bar is None:
            # search children for ttk widgets containing status
            for child in app_inst.winfo_children():
                # ttk widgets have winfo_class like TLabel/TFrame
                if isinstance(child, (ttk.Frame, ttk.Label)):
                    # heuristic: packed at bottom? check
                    # look for textvariable or text "Ready"
                    try:
                        txt = child.cget("text") if "text" in child.keys() else ""
                    except Exception:
                        txt = ""
                    if "Ready" in str(txt) or "status" in str(type(child)).lower():
                        bar = child
                        break
            # also check for status_var
            if bar is None and hasattr(app_inst, "_status_var"):
                # consider existence of _status_var as statusbar evidence only if widget exists
                # fail to force implementation to expose bar
                pass

        assert bar is not None, "Statusbar ttk widget not found (expected self.statusbar)"
        assert isinstance(bar, (ttk.Frame, ttk.Label, ttk.Sizegrip, tk.Frame)), f"statusbar should be ttk widget, got {type(bar)}"
        # should have status var or label
        has_var = hasattr(app_inst, "_status_var") or hasattr(app_inst, "status_var")
        # also allow bar with textvariable
        if not has_var:
            # check bar has textvariable
            try:
                tv = bar.cget("textvariable")
                has_var = bool(tv)
            except Exception:
                pass
            # check children
            if not has_var:
                for child in bar.winfo_children() if hasattr(bar, "winfo_children") else []:
                    try:
                        if child.cget("textvariable"):
                            has_var = True
                            break
                    except Exception:
                        continue
        assert has_var, "statusbar should have StringVar (self._status_var or textvariable)"
    finally:
        try:
            app_inst.destroy()
        except Exception:
            pass


def test_font_retained_on_self() -> None:
    app_inst = _create_app()
    try:
        assert hasattr(app_inst, "_font_default"), "self._font_default required (GC guard)"
        assert hasattr(app_inst, "_font_text"), "self._font_text required"
    finally:
        try:
            app_inst.destroy()
        except Exception:
            pass


def test_menu_file_and_help() -> None:
    app_inst = _create_app()
    try:
        # menu bar
        menu_name = app_inst.cget("menu")
        assert menu_name, "App must have menu bar (self.config(menu=...))"
        import tkinter as tk

        # resolve menu widget
        try:
            menubar = app_inst.nametowidget(menu_name)
        except Exception:
            pytest.fail(f"menu widget not found for name {menu_name}")

        # enumerate top-level menus
        labels = []
        try:
            last = menubar.index("end")
        except Exception:
            last = None
        if last is not None:
            for i in range(last + 1):
                try:
                    t = menubar.entrycget(i, "label")
                    labels.append(t)
                except Exception:
                    pass
        assert any("File" in lb or "ファイル" in lb for lb in labels), f"File menu missing, got {labels}"
        assert any("Help" in lb or "ヘルプ" in lb for lb in labels), f"Help menu missing, got {labels}"

        # find File submenu
        file_menu = None
        help_menu = None
        if last is not None:
            for i in range(last + 1):
                try:
                    lbl = menubar.entrycget(i, "label")
                    mname = menubar.entrycget(i, "menu")
                    if "File" in lbl or "ファイル" in lbl:
                        file_menu = app_inst.nametowidget(mname)
                    if "Help" in lbl or "ヘルプ" in lbl:
                        help_menu = app_inst.nametowidget(mname)
                except Exception:
                    continue

        assert file_menu is not None, "File submenu not found"
        assert help_menu is not None, "Help submenu not found"

        # File entries: 設定フォルダを開く / 終了
        def _entries(menu):
            entries = []
            try:
                end = menu.index("end")
            except Exception:
                return entries
            if end is None:
                return entries
            for i in range(end + 1):
                try:
                    entries.append(menu.entrycget(i, "label"))
                except Exception:
                    pass
            return entries

        file_entries = _entries(file_menu)
        assert any("設定フォルダを開く" in e for e in file_entries), f"File menu must contain '設定フォルダを開く', got {file_entries}"
        assert any("終了" in e for e in file_entries), f"File menu must contain '終了', got {file_entries}"

        help_entries = _entries(help_menu)
        assert any("このソフトについて" in e for e in help_entries), f"Help menu must contain 'このソフトについて', got {help_entries}"

        # About dialog content: check method or string contains GPLv3 and SHA882116a
        # introspect source
        import pathlib as _pl

        src = _pl.Path(app_inst.__class__.__module__.replace(".", "/")).exists()  # dummy
        # actually read app.py
        apppath = pathlib.Path(__file__).resolve().parent.parent / "app.py"
        srctext = apppath.read_text(encoding="utf-8")
        assert "GPLv3" in srctext, "Help About must mention GPLv3"
        assert "882116a" in srctext, "Help About must mention SHA 882116a"
    finally:
        try:
            app_inst.destroy()
        except Exception:
            pass


def test_geometry_persistence_via_get_config_path(tmp_path, monkeypatch) -> None:
    """geometry should be persisted via get_config_path (load on init, save on close)."""
    import app as app_module

    cfg = tmp_path / "myconfig" / "config.json"
    monkeypatch.setattr(app_module, "get_config_path", lambda: cfg)

    # pre-seed config with geometry
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"geometry": "900x700+11+22"}, ensure_ascii=False), encoding="utf-8")

    app_inst = _create_app(monkeypatch=None, tmp_config=None)  # already patched via monkeypatch
    # need to recreate with patched path; _create_app uses monkeypatch internally? do manually
    # but we already patched app_module.get_config_path; next App should load it
    # The app_inst above already used patched path; check geometry
    try:
        geom = app_inst.geometry()
        # allow slight decoration: should be 900x700...
        assert geom.startswith("900x700"), f"geometry persistence load failed, expected 900x700..., got {geom}"
    finally:
        try:
            app_inst.destroy()
        except Exception:
            pass

    # test save: create new app with different geometry, trigger save, check file
    cfg.write_text(json.dumps({}, ensure_ascii=False), encoding="utf-8")
    app2 = _create_app(monkeypatch=None, tmp_config=None)
    try:
        # change geometry
        try:
            app2.geometry("820x620+5+5")
            app2.update_idletasks()
        except Exception:
            pass
        # invoke save path: _save_geometry or _on_close
        saved = False
        for meth in ("_save_geometry", "_save_config", "save_geometry", "_on_close"):
            if hasattr(app2, meth):
                try:
                    getattr(app2, meth)()
                    saved = True
                    break
                except Exception:
                    continue
        if not saved:
            # try protocol handler
            try:
                app2._on_close()
                saved = True
            except Exception:
                pass
        # check file exists and contains geometry
        assert cfg.exists(), "config file should be created on save"
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert "geometry" in data, f"saved config must contain geometry, got {data}"
        assert isinstance(data["geometry"], str) and "x" in data["geometry"]
    finally:
        try:
            app2.destroy()
        except Exception:
            # ensure file still there
            pass


def test_resource_path_integration_in_app(tmp_path) -> None:
    """App should integrate resource_path without crashing (duck typing try/except)."""
    # just verify App init doesn't crash when resource_path points to missing file
    # and that app.py source references resource_path inside GUI_SHELL
    apppath = pathlib.Path(__file__).resolve().parent.parent / "app.py"
    text = apppath.read_text(encoding="utf-8")
    # extract GUI_SHELL section
    import re

    m = re.search(r"# SECTION: GUI_SHELL(.*?)# SECTION: GUI_VEHICLE", text, re.S)
    assert m, "SECTION:GUI_SHELL not found"
    shell = m.group(1)
    assert "resource_path" in shell, "GUI_SHELL must integrate resource_path (e.g., icon loading with try/except)"
    assert "get_config_path" in shell, "GUI_SHELL must use get_config_path for geometry persistence"
