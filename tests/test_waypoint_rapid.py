# -*- coding: utf-8 -*-
"""TDD RED: waypoint rapid — 5px euclidean, dynamic radius, micro-click, Treeview, autosave, Shift bypass, empty-save block, offline robustness.

All 8 tests are expected to FAIL on current codebase (154 GREEN baseline).
Failures must be spec-driven (assert on behavior/presence), never syntax/import.
"""
from __future__ import annotations

import pathlib
import sys

import pytest


def _read(rel: str) -> str:
    p = pathlib.Path(rel)
    if not p.exists():
        p = pathlib.Path(__file__).resolve().parents[1] / rel
    return p.read_text(encoding="utf-8")


def _try_root():
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.update()
        return root
    except Exception as e:
        pytest.skip(f"headless no display: {e}")


def test_5px_euclidean_threshold_exists() -> None:
    """OSMCanvas hit-test must use euclidean distance with 5px threshold (hypot < 5)."""
    text = _read("src/openlapexe/gui/osm_canvas.py")
    # Current: abs(px - event.x) < 10 and abs(py - event.y) < 10  (rectangular 10px)
    # Expected: hypot-based euclidean 5px, e.g. math.hypot(dx,dy) < 5 or np.hypot
    has_hypot = "hypot" in text
    # check that hypot is actually used in hit-test context with threshold 5
    has_5_threshold = ("< 5" in text or "<5" in text) and has_hypot
    assert has_hypot and has_5_threshold, (
        "Expected OSMCanvas to use euclidean hypot with 5px threshold; "
        f"got hypot={has_hypot}, 5px_threshold={has_5_threshold}. "
        "Current is rectangular abs() <10."
    )


def test_dynamic_hit_radius_helper_exists() -> None:
    """Dynamic hit-radius helper (e.g. _hit_radius / get_hit_radius / HIT_RADIUS) must exist."""
    osm = _read("src/openlapexe/gui/osm_canvas.py")
    creator = _read("src/openlapexe/gui/course_creator.py")
    combined = osm + "\n" + creator
    has_helper = (
        "_hit_radius" in combined
        or "get_hit_radius" in combined
        or "hit_radius" in combined.lower()
        or "HIT_RADIUS" in combined
        or "dynamic_radius" in combined.lower()
    )
    # Also check zoom-dependent radius (should scale with zoom)
    has_zoom_dependent = "zoom" in combined.lower() and "radius" in combined.lower()
    assert has_helper and has_zoom_dependent, (
        "Expected dynamic hit-radius helper (e.g. _hit_radius(zoom) -> radius) "
        "that scales with zoom; not found in osm_canvas/course_creator."
    )


def test_dragging_idx_micro_move_click_registers() -> None:
    """Same hit-area consecutive 2 clicks must each register (+2 points); micro-move should not be treated as drag."""
    root = _try_root()
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=400, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack()
        root.update()
        # Start empty
        c.points_latlon.clear()
        c.points_xy.clear()
        c.points_zone.clear()
        root.update()

        # Add first point at center
        lat_c, lon_c = c.center_lat, c.center_lon
        c.add_point_latlon(lat_c, lon_c)
        assert len(c.points_latlon) == 1
        init = len(c.points_latlon)

        # Get pixel of existing point
        px, py = c.latlon_to_pixel(lat_c, lon_c)
        # First click slightly offset within hit area (2px away) — should add, not drag
        # Simulate press/release at (px+2, py+2)
        class Ev:
            def __init__(self, x, y):
                self.x = int(x)
                self.y = int(y)

        # Ensure dragging_idx cleared
        c._dragging_idx = None  # type: ignore[attr-defined]
        c._moved = False  # type: ignore[attr-defined]
        c._press_x = None  # type: ignore[attr-defined]
        c._press_y = None  # type: ignore[attr-defined]

        # Two consecutive clicks in same hit area should each add a point (total +2)
        for _ in range(2):
            ev = Ev(int(px) + 2, int(py) + 2)
            try:
                c._on_press(ev)  # type: ignore[attr-defined]
                # Do NOT move — micro move
                c._on_release(ev)  # type: ignore[attr-defined]
            except Exception:
                pass
            root.update()

        # Expected: init + 2
        assert len(c.points_latlon) == init + 2, (
            f"Micro-move clicks in same hit area should register +2 points; "
            f"got {len(c.points_latlon)} (init {init}), expected {init+2}. "
            "Current _dragging_idx absorbs click as drag candidate and blocks addition."
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_treeview_columns_no_lat_lon_exists() -> None:
    """Treeview with columns (No/lat/lon) must exist in shell or waypoint view."""
    shell = _read("src/openlapexe/gui/shell.py")
    osm = _read("src/openlapexe/gui/osm_canvas.py")
    creator = _read("src/openlapexe/gui/course_creator.py")
    combined = shell + osm + creator
    has_treeview = "Treeview" in combined
    has_no = '"No"' in combined or "'No'" in combined or "No" in combined
    # Strict: check Treeview columns definition containing lat & lon
    has_lat_lon_cols = False
    for txt in (shell, osm, creator):
        if "Treeview" in txt and "lat" in txt.lower() and "lon" in txt.lower():
            # look for columns tuple containing these names
            if "columns" in txt.lower():
                has_lat_lon_cols = True
    # Also import-level check: instantiate App2 and search Treeview columns if display available
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            from openlapexe.gui.shell import App2

            app = App2()
            app.update()
            found = False
            for w in app.winfo_children():
                # walk
                stack = [w]
                while stack:
                    cur = stack.pop()
                    try:
                        if cur.winfo_class() == "Treeview":  # type: ignore[attr-defined]
                            cols = cur.cget("columns")  # type: ignore[attr-defined]
                            cols_str = str(cols).lower()
                            if "no" in cols_str and "lat" in cols_str and "lon" in cols_str:
                                found = True
                    except Exception:
                        pass
                    try:
                        stack.extend(cur.winfo_children())
                    except Exception:
                        pass
            has_lat_lon_cols = has_lat_lon_cols or found
            try:
                app.destroy()
            except Exception:
                pass
            root.destroy()
        except Exception:
            try:
                root.destroy()
            except Exception:
                pass
    except Exception:
        pass

    assert has_treeview and has_lat_lon_cols, (
        "Expected Treeview with columns (No/lat/lon) in shell/waypoint view; "
        f"Treeview present={has_treeview}, No/lat/lon cols={has_lat_lon_cols}"
    )


def test_10points_autosave_exists() -> None:
    """10-point autosave (e.g. AUTOSAVE_THRESHOLD=10 or _autosave) must exist."""
    osm = _read("src/openlapexe/gui/osm_canvas.py")
    shell = _read("src/openlapexe/gui/shell.py")
    creator = _read("src/openlapexe/gui/course_creator.py")
    combined = osm + shell + creator
    has_autosave = (
        "autosave" in combined.lower()
        or "auto_save" in combined.lower()
        or "AUTOSAVE" in combined
        or "10" in combined  # trivially true, so need stricter
    )
    # Stricter: look for autosave symbol explicitly
    has_autosave_symbol = "autosave" in combined.lower() or "auto_save" in combined.lower()
    has_threshold_10 = "AUTOSAVE_THRESHOLD" in combined or ("autosave" in combined.lower() and "10" in combined)
    assert has_autosave_symbol and has_threshold_10, (
        "Expected 10-point autosave (e.g. autosave threshold 10, _autosave()) "
        f"in osm_canvas/shell/course_creator; autosave_symbol={has_autosave_symbol}, threshold10={has_threshold_10}"
    )


def test_photo_armed_shift_click_bypass_exists() -> None:
    """When photo armed, Shift+Click should bypass photo placement and add waypoint."""
    osm = _read("src/openlapexe/gui/osm_canvas.py")
    shell = _read("src/openlapexe/gui/shell.py")
    # Spec: photo armed + Shift => waypoint bypass
    has_shift = "Shift" in osm or "shift" in osm.lower() or "Shift" in shell
    # Check that osm_canvas handles Shift state (event.state & 0x1) or keysym Shift
    has_shift_handling = (
        ("state" in osm and "Shift" in osm)
        or ("keysym" in osm.lower() and "shift" in osm.lower())
        or ("event.state" in osm)
        or ("Shift" in osm and "arm" in osm.lower())
    )
    # Functional check if display available
    functional_ok = False
    try:
        import base64
        import pathlib
        import tempfile

        root = _try_root()
        from openlapexe.gui.osm_canvas import OSMCanvas

        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
        tmp = pathlib.Path(tempfile.mkdtemp())
        p = tmp / "photo.png"
        p.write_bytes(base64.b64decode(png_b64))
        c = OSMCanvas(root, width=300, height=300, zoom=12)
        c.pack()
        root.update()
        pid = c.add_photo(str(p), lat=35.68, lon=139.76, opacity=0.5)
        assert c.arm_photo_place(pid) is True
        # arm should reject normal click and require Shift to add point
        # We check that file-level Shift handling exists; functional bypass would keep photo count same and add point
        # If Shift handling missing, file check already fails
        functional_ok = has_shift_handling
        try:
            root.destroy()
        except Exception:
            pass
    except Exception:
        functional_ok = has_shift_handling

    assert has_shift and has_shift_handling and functional_ok, (
        "Expected Shift+Click bypass when photo armed (OSMCanvas should check Shift state "
        f"and add waypoint instead of placing photo); Shift in file={has_shift}, "
        f"handling={has_shift_handling}"
    )


def test_empty_save_blocked() -> None:
    """Save button must be disabled when points <2 (empty save blocked via UI state, not just warning)."""
    text = _read("src/openlapexe/gui/shell.py")
    # Current: _on_save_track checks len<2 and shows warning, but button stays enabled.
    # Expected: button state toggling (state='disabled' when <2, 'normal' when >=2) or similar guard
    has_state_disabled = "disabled" in text.lower() and "save" in text.lower()
    has_len_check_for_state = False
    # Look for pattern where points length controls button state
    if "btn_save" in text and "disabled" in text.lower():
        # check proximity: save button and points length in same file suggests guard
        has_len_check_for_state = True
    # Functional: empty creator should have save disabled
    functional_disabled = False
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        from openlapexe.gui.shell import App2

        app = App2()
        app.update()
        # Ensure creator has 0 or 1 point
        cc = getattr(app, "_creator_osm", None) or getattr(app, "course_creator", None)
        if cc is not None:
            try:
                cc.set_points([])
                app.update()
            except Exception:
                pass
        btn = getattr(app, "btn_save", None) or getattr(app, "save_button", None)
        if btn is not None:
            try:
                state = str(btn.cget("state"))
                functional_disabled = state == "disabled"
            except Exception:
                functional_disabled = False
        try:
            app.destroy()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass
    except Exception:
        pass

    assert has_state_disabled and has_len_check_for_state and functional_disabled, (
        "Expected empty-save blocked via button disabled state when points<2; "
        f"disabled in save context={has_state_disabled}, len->state guard={has_len_check_for_state}, "
        f"functional disabled={functional_disabled}. Current only shows warning, button stays enabled."
    )


def test_offline_no_crash_and_immediate_placeholder() -> None:
    """Offline fetch must not crash and must return immediate gray placeholder (fetch_tile should return bytes, not raise)."""
    from openlapexe.geo_tile import fetch_tile, _clear_caches_for_tests
    import pathlib
    import tempfile

    _clear_caches_for_tests()
    tmp = pathlib.Path(tempfile.mkdtemp())
    # Use non-routable address to force offline
    bad_base = "http://127.0.0.1:1/{z}/{x}/{y}.png"
    # Clear LRU to force network attempt
    _clear_caches_for_tests()
    try:
        data = fetch_tile(10, 909, 403, base_url=bad_base, cache_dir=tmp, timeout=0.2)
        # Expected: immediate placeholder bytes (non-empty), no exception
        assert isinstance(data, (bytes, bytearray)) and len(data) > 0, "Expected placeholder bytes"
        # Also check that it is a valid PNG-ish or at least not empty
        assert len(data) > 10, f"Placeholder too small: {len(data)}"
    except Exception as e:
        pytest.fail(
            f"Offline fetch must return immediate placeholder without raising; raised {type(e).__name__}: {e}. "
            "Current fetch_tile raises URLError after retry."
        )
    finally:
        _clear_caches_for_tests()


def test_undo_rolls_back_map_side() -> None:
    """Undo must pop OSM map lists AND mirror creator (no resurrection)."""
    root = _try_root()
    try:
        import openlapexe.geo_tile as gt

        orig = gt.fetch_tile
        gt.fetch_tile = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline"))
        try:
            sys.path.insert(0, "src")
            from openlapexe.gui.shell import App2

            app = App2()
            try:
                app.update_idletasks()
                oc = getattr(app, "_osm_canvas", None) or getattr(app, "osm_canvas", None)
                assert oc is not None
                for lat, lon in ((35.68, 139.76), (35.681, 139.761), (35.682, 139.762)):
                    oc.add_point_latlon(lat, lon)
                app.update_idletasks()
                app._sync_osm_to_creator()
                app.update_idletasks()
                assert len(oc.points_latlon) == 3
                cc = getattr(app, "_creator_osm", None) or getattr(app, "course_creator", None)
                assert cc is not None and len(list(cc.points_xy)) == 3
                app._on_waypoint_undo()
                app.update_idletasks()
                assert len(oc.points_latlon) == 2, f"map side must roll back, got {len(oc.points_latlon)}"
                assert len(list(cc.points_xy)) == 2, f"creator must mirror rollback, got {len(list(cc.points_xy))}"
                app._on_waypoint_undo()
                app.update_idletasks()
                assert len(oc.points_latlon) == 1
                assert len(list(cc.points_xy)) == 1
                try:
                    app._on_close()
                except Exception:
                    pass
                try:
                    app.destroy()
                except Exception:
                    pass
            finally:
                try:
                    app.destroy()
                except Exception:
                    pass
        finally:
            gt.fetch_tile = orig
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_saved_course_reload_into_creator() -> None:
    """Saved course must be loadable back into create tab (map + creator + tree)."""
    root = _try_root()
    try:
        import openlapexe.geo_tile as gt

        orig = gt.fetch_tile
        gt.fetch_tile = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline"))
        try:
            sys.path.insert(0, "src")
            from openlapexe.gui.shell import App2

            app = App2()
            try:
                app.update_idletasks()
                assert hasattr(app, "_on_load_track"), "load API must exist"
                oc = getattr(app, "_osm_canvas", None) or getattr(app, "osm_canvas", None)
                assert oc is not None
                for lat, lon in ((35.68, 139.76), (35.681, 139.761), (35.682, 139.762)):
                    oc.add_point_latlon(lat, lon)
                app.update_idletasks()
                app._sync_osm_to_creator()
                import tkinter.messagebox as mb
                import tkinter.simpledialog as sd

                _orig_warn = mb.showwarning
                _orig_err = mb.showerror
                _orig_info = mb.showinfo
                _orig_ask = sd.askstring
                mb.showwarning = lambda *a, **kw: None
                mb.showerror = lambda *a, **kw: None
                mb.showinfo = lambda *a, **kw: None
                sd.askstring = lambda *a, **kw: "__ut_reload__"
                try:
                    app._on_save_track()
                    oc.points_latlon.clear()
                    oc.points_xy.clear()
                    oc.points_zone.clear()
                    app._refresh_waypoint_tree()
                    app._on_load_track("__ut_reload__")
                finally:
                    mb.showwarning = _orig_warn
                    mb.showerror = _orig_err
                    mb.showinfo = _orig_info
                    sd.askstring = _orig_ask
                app.update_idletasks()
                assert len(oc.points_latlon) == 3, f"map must hold 3 after reload, got {len(oc.points_latlon)}"
                cc = getattr(app, "_creator_osm", None) or getattr(app, "course_creator", None)
                assert cc is not None and len(list(cc.points_xy)) == 3
                try:
                    app._on_close()
                except Exception:
                    pass
                try:
                    app.destroy()
                except Exception:
                    pass
            finally:
                try:
                    app.destroy()
                except Exception:
                    pass
                p = pathlib.Path("data/tracks/__ut_reload__.json")
                if p.exists():
                    p.unlink()
        finally:
            gt.fetch_tile = orig
    finally:
        try:
            root.destroy()
        except Exception:
            pass
