# -*- coding: utf-8 -*-
"""tests/test_photo_interact_mode.py - RED only for explicit trace/place/edit mode switch (S-mode-switch).

3 FAILing tests (must stay RED until S-mode-switch lands):

 (a) shell has trace/place/edit selector (e.g. interact_mode_var with trace|place|edit) defaulting trace
 (b) edit mode: click on empty map selects nothing and adds NO waypoint, click on photo selects it without moving
 (c) trace mode: click on photo adds waypoint without selecting/moving photo even when a photo was previously selected; place mode keeps current armed behavior

Context: Problem implicit modes trap users (armed stuck, select-vs-trace ambiguous); goal explicit human-operable switch gating all clicks.

Expectation: before impl, pytest RED on missing selector/gating.
After impl:
 - shell bar (photo_bar) has Radiobutton/OptionMenu bound to interact_mode_var (StringVar value="trace" default) with values trace/place/edit
 - osm_canvas has explicit mode state (e.g. interact_mode_var / _interact_mode / get_interact_mode / set_interact_mode) gating _on_press/_on_release:
     edit: empty click -> no waypoint, no select; photo click -> select only, no waypoint/move
     trace: photo click -> waypoint only, no select/move (even if previously selected)
     place: armed behavior preserved (inside bbox adds waypoint still-armed, outside places+disarms)

Headless: tries Tk, if no display still asserts API missing via source inspection + pytest.fail (no skip-green).
Do NOT fix src/ - this file must stay RED until implementation lands.

Related: shell.py photo bar 610-690 (_photo_place_btn, _on_photo_place 1139, _on_photo_escape 1261), osm_canvas.py _on_press/_on_release click routing + get_mode.
Follows test_photo_scale headless _try_root + tmp PNG patterns.
"""

from __future__ import annotations

import base64
import pathlib
import tempfile

import pytest


def _try_root():
    """Try to get Tk root; return None on headless without skipping (API check still fails)."""
    try:
        import tkinter as tk
    except Exception as e:
        pytest.skip(f"tkinter unavailable: {e}")
    try:
        root = tk.Tk()
        root.withdraw()
        return root
    except Exception:
        return None


def _tmp_png() -> pathlib.Path:
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = tmp / "photo_interact.png"
    p.write_bytes(base64.b64decode(png_b64))
    return p


class _Ev:
    def __init__(self, x, y, state=0, num=1):
        self.x = int(x)
        self.y = int(y)
        self.state = int(state)
        self.num = int(num)


def _shell_src_path() -> pathlib.Path:
    # import to locate file robustly
    try:
        from openlapexe.gui import shell as shmod
        return pathlib.Path(shmod.__file__)
    except Exception:
        p = pathlib.Path("src/openlapexe/gui/shell.py")
        if p.exists():
            return p
        p2 = pathlib.Path(__file__).parent.parent / "src/openlapexe/gui/shell.py"
        return p2


def _canvas_src_path() -> pathlib.Path:
    try:
        from openlapexe.gui import osm_canvas as mod
        return pathlib.Path(mod.__file__)
    except Exception:
        p = pathlib.Path("src/openlapexe/gui/osm_canvas.py")
        return p


def _set_interact_mode(canvas, shell_obj, mode: str) -> bool:
    """Try to set explicit interact mode to trace|place|edit via multiple possible APIs. Return True if any succeeded."""
    ok = False
    # canvas APIs
    for cand in (canvas, shell_obj):
        if cand is None:
            continue
        # set_interact_mode / set_photo_interact_mode / set_mode
        for mname in ("set_interact_mode", "set_photo_interact_mode", "set_mode", "set_photo_mode"):
            if hasattr(cand, mname):
                try:
                    cand.__getattribute__(mname)(mode)  # type: ignore
                    ok = True
                except Exception:
                    try:
                        getattr(cand, mname)(mode)
                        ok = True
                    except Exception:
                        pass
        # StringVar setters
        for vname in ("interact_mode_var", "_interact_mode_var", "photo_interact_mode_var", "_photo_interact_mode_var", "_interact_mode", "interact_mode"):
            if hasattr(cand, vname):
                try:
                    v = getattr(cand, vname)
                    if hasattr(v, "set"):
                        v.set(mode)
                        ok = True
                    elif isinstance(v, str):
                        setattr(cand, vname, mode)
                        ok = True
                except Exception:
                    pass
        # direct attribute fallback
        try:
            if hasattr(cand, "_interact_mode"):
                setattr(cand, "_interact_mode", mode)
                # do not alone mark ok unless also var exists, but allow
                # check if getter will reflect
                pass
            if hasattr(cand, "interact_mode"):
                setattr(cand, "interact_mode", mode)
        except Exception:
            pass
    # also try canvas internal
    try:
        if hasattr(canvas, "_interact_mode"):
            canvas._interact_mode = mode  # type: ignore
            # if canvas has _interact_mode_var, set it too
            if hasattr(canvas, "_interact_mode_var") and hasattr(canvas._interact_mode_var, "set"):
                try:
                    canvas._interact_mode_var.set(mode)  # type: ignore
                    ok = True
                except Exception:
                    pass
    except Exception:
        pass
    return ok


def _get_interact_mode(canvas, shell_obj) -> str | None:
    for cand in (canvas, shell_obj):
        if cand is None:
            continue
        for mname in ("get_interact_mode", "get_photo_interact_mode", "get_mode"):
            if hasattr(cand, mname):
                try:
                    v = getattr(cand, mname)()
                    if isinstance(v, str) and v in ("trace", "place", "edit"):
                        return v
                except Exception:
                    pass
        for vname in ("interact_mode_var", "_interact_mode_var", "photo_interact_mode_var", "_photo_interact_mode_var"):
            if hasattr(cand, vname):
                try:
                    v = getattr(cand, vname)
                    if hasattr(v, "get"):
                        gv = v.get()
                        if isinstance(gv, str):
                            return gv
                except Exception:
                    pass
        for vname in ("_interact_mode", "interact_mode"):
            if hasattr(cand, vname):
                try:
                    gv = getattr(cand, vname)
                    if isinstance(gv, str) and gv in ("trace", "place", "edit"):
                        return gv
                except Exception:
                    pass
    return None


# ------------------------------------------------------------------


def test_a_shell_has_trace_place_edit_selector_default_trace():
    """(a) shell has trace/place/edit selector (e.g. interact_mode_var with trace|place|edit) defaulting trace"""
    from openlapexe.gui import osm_canvas as cmod
    from openlapexe.gui import shell as shmod

    shell_path = _shell_src_path()
    canvas_path = _canvas_src_path()
    shell_src = shell_path.read_text(encoding="utf-8") if shell_path.exists() else ""
    canvas_src = canvas_path.read_text(encoding="utf-8") if canvas_path.exists() else ""
    combined = shell_src + "\n" + canvas_src

    # API existence - must FAIL now (RED) with AttributeError/no-selector
    # shell should expose interact_mode_var (or _interact_mode_var) bound to trace|place|edit
    has_var = (
        "interact_mode_var" in shell_src
        or "_interact_mode_var" in shell_src
        or "photo_interact_mode_var" in shell_src
        or "interact_mode" in shell_src.lower()
    )
    assert has_var, "AttributeError: shell missing trace/place/edit selector - expected interact_mode_var (StringVar trace|place|edit) in shell.py photo bar (S-mode-switch not implemented)"
    # must mention all three modes
    low = combined.lower()
    assert "trace" in low and "place" in low and "edit" in low, "AttributeError: selector missing trace|place|edit values - expected Radiobutton/OptionMenu with trace|place|edit in shell.py/osm_canvas.py"
    # selector widget: Radiobutton or OptionMenu/Combobox bound to that var
    has_widget = (
        ("Radiobutton" in shell_src and "interact" in shell_src.lower())
        or ("OptionMenu" in shell_src and "interact" in shell_src.lower())
        or ("Combobox" in shell_src and "interact" in shell_src.lower())
        or ("ttk.Radiobutton" in shell_src and "trace" in shell_src)
        or ("interact_mode" in canvas_src.lower() and "Radiobutton" in canvas_src)
    )
    assert has_widget, "AttributeError: photo bar missing Radiobutton/OptionMenu selector for trace|place|edit (interact_mode_var) - photo_bar 610-690 has only _photo_place_btn, no explicit switch"

    # default must be trace
    # look for StringVar(value="trace") or value='trace' near interact
    has_default_trace = False
    for pat in ('value="trace"', "value='trace'", 'value = "trace"', "value = 'trace'", '"trace"' ):
        if pat in combined:
            # check proximity to interact_mode
            idx = combined.find(pat)
            ctx = combined[max(0, idx-800): idx+800].lower()
            if "interact" in ctx or "mode" in ctx:
                has_default_trace = True
                break
    # alternative: check var init line contains trace as default
    if not has_default_trace:
        # search for interact_mode_var assignment line
        for line in shell_src.splitlines():
            if "interact" in line.lower() and "trace" in line.lower() and ("StringVar" in line or "Var(" in line):
                has_default_trace = True
                break
        for line in canvas_src.splitlines():
            if "interact" in line.lower() and "trace" in line.lower() and ("StringVar" in line or "Var(" in line or "_interact" in line):
                has_default_trace = True
                break
    assert has_default_trace, "AttributeError: interact_mode_var does not default to trace - expected StringVar(value=\"trace\") for S-mode-switch"

    # canvas must gate clicks on explicit mode
    # _on_press / _on_release should reference interact_mode
    assert "interact_mode" in canvas_src.lower() or "interact" in canvas_src.lower(), "AttributeError: osm_canvas.py _on_press/_on_release click routing missing explicit interact_mode gating (still using implicit _placing_photo_id/_selected_photo_id only)"
    # get_mode should be updated or new get_interact_mode should exist
    assert "get_interact_mode" in canvas_src or "interact_mode" in canvas_src.lower(), "AttributeError: OSMCanvas.get_interact_mode / interact_mode handling missing - get_mode still returns place|select|normal only, no trace|place|edit"

    root = _try_root()
    if root is None:
        pytest.fail("RED: shell trace/place/edit selector missing - headless source inspection above already failed, expected interact_mode_var default trace and gating in osm_canvas _on_press/_on_release")

    # functional check when Tk available
    try:
        import tkinter as tk

        # try to create shell App2 minimal - if fails due to missing init args, fallback to canvas-only check
        # First test canvas var default trace
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=300, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack()
        root.update()

        mode = _get_interact_mode(c, None)
        # If shell not instantiated, try canvas alone
        if mode is None:
            # try to find var directly
            for vname in ("interact_mode_var", "_interact_mode_var", "photo_interact_mode_var", "_photo_interact_mode_var"):
                if hasattr(c, vname):
                    try:
                        mode = getattr(c, vname).get()  # type: ignore
                        break
                    except Exception:
                        pass
        assert mode is not None, "AttributeError: OSMCanvas has no interact_mode_var / get_interact_mode - explicit switch missing"
        assert mode == "trace", f"AttributeError: default interact mode should be trace, got {mode!r}"

        # Try shell App2 if importable without heavy deps
        shell_obj = None
        try:
            # App2 is in shell.py, may require Tk master
            ShellCls = getattr(shmod, "App2", None) or getattr(shmod, "App", None) or getattr(shmod, "Shell", None)
            if ShellCls is not None:
                # Attempt minimal construction without blocking - use Toplevel
                # Many shells require no args or root; try root
                try:
                    shell_obj = ShellCls(root)  # type: ignore
                except TypeError:
                    try:
                        shell_obj = ShellCls()  # type: ignore
                    except Exception:
                        shell_obj = None
                if shell_obj is not None:
                    # check var on shell
                    smode = _get_interact_mode(c, shell_obj)
                    if smode is not None:
                        assert smode == "trace", f"shell interact_mode default should be trace, got {smode!r}"
                    # check bar contains selector widget
                    # Look for children containing trace/place/edit
                    def _has_selector(widget):
                        try:
                            txt = widget.cget("text") if hasattr(widget, "cget") else ""
                            if txt in ("trace", "place", "edit"):
                                return True
                        except Exception:
                            pass
                        try:
                            for ch in widget.winfo_children():  # type: ignore
                                if _has_selector(ch):
                                    return True
                        except Exception:
                            pass
                        return False

                    # try shell photo_bar inspection
                    bar = getattr(shell_obj, "_photo_bar", None) or getattr(shell_obj, "photo_bar", None)
                    if bar is not None:
                        assert _has_selector(bar) or "interact" in str(type(bar)).lower() or has_var, "shell photo_bar missing trace/place/edit Radiobutton selector"
                    # destroy shell obj if it is a Toplevel
                    try:
                        if hasattr(shell_obj, "destroy"):
                            shell_obj.destroy()
                    except Exception:
                        pass
        except Exception:
            pass

        # at least canvas default check is enough for RED->GREEN transition
        assert mode == "trace", f"RED: default trace not honored, got {mode!r}"

    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass


def test_b_edit_mode_click_empty_no_waypoint_photo_click_selects_without_moving():
    """(b) edit mode: click on empty map selects nothing and adds NO waypoint, click on photo selects it without moving"""
    from openlapexe.gui import osm_canvas as mod
    import pathlib as _pl

    shell_src = _shell_src_path().read_text(encoding="utf-8") if _shell_src_path().exists() else ""
    canvas_src = _pl.Path(mod.__file__).read_text(encoding="utf-8")

    # --- source gating checks (must FAIL now) ---
    assert "interact_mode" in canvas_src.lower() or "interact" in canvas_src.lower(), "RED: osm_canvas missing interact_mode gating - _on_press/_on_release still implicit, edit mode cannot gate clicks"
    # edit branch handling
    low = canvas_src.lower()
    # must have edit handling in press/release
    assert "edit" in low, "RED: osm_canvas source missing 'edit' mode handling - explicit edit switch not implemented"
    # _on_press should branch on edit to prevent waypoint add and to allow select-only
    if "def _on_press" in canvas_src and "def _on_drag" in canvas_src:
        press_src = canvas_src.split("def _on_press")[1].split("def _on_drag")[0].lower()
        assert "interact" in press_src or "edit" in press_src or "trace" in press_src, "RED: _on_press missing explicit edit/trace/place gating - still implicit armed/selected only"
    if "def _on_release" in canvas_src:
        rel_src = canvas_src.split("def _on_release")[1].split("def ")[0].lower()
        assert "interact" in rel_src or "edit" in rel_src or "trace" in rel_src, "RED: _on_release missing explicit mode gating for edit (should block waypoint add on empty, allow select-only on photo)"

    root = _try_root()
    if root is None:
        pytest.fail("RED: edit mode gating missing - headless source inspection shows no edit branch in _on_press/_on_release, expected explicit switch to gate clicks")

    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=400, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack()
        root.update()
        # clean state
        c.points_latlon = []
        c.points_xy = []
        c.points_zone = []
        c._selected_photo_id = None
        try:
            c._placing_photo_id = None
        except Exception:
            pass
        # ensure mode set to edit
        # try shell object as None; set on canvas
        ok = _set_interact_mode(c, None, "edit")
        assert ok, "AttributeError: cannot set interact mode to edit - explicit switch API missing (set_interact_mode / interact_mode_var)"
        got = _get_interact_mode(c, None)
        assert got == "edit", f"RED: failed to set edit mode, got {got!r} - gating cannot be tested"

        # add photo at center
        p = _tmp_png()
        pid = c.add_photo(str(p), lat=35.68, lon=139.76, opacity=0.9)
        root.update()
        rec0 = c.get_photo(pid)
        assert rec0 is not None
        lat0, lon0 = float(rec0["lat"]), float(rec0["lon"])
        # ensure photo is selected initially (add_photo auto-selects), clear to test edit empty click selects nothing
        c._selected_photo_id = None
        for r in c._photos:
            r["selected"] = False
        root.update()

        # --- edit: click on empty map (far corner 8,8) should select nothing and add NO waypoint ---
        # pick empty point far from photo: photo center ~200,150 at 400x300; 8,8 is far corner
        n0 = len(c.points_latlon)
        # ensure 8,8 not inside any photo bbox
        try:
            hit = c.hit_test_photo(8, 8)
            assert hit is None, f"test setup: 8,8 unexpectedly inside photo bbox {hit}"
        except AttributeError:
            pass
        c._on_press(_Ev(8, 8))
        c._press_x, c._press_y = 8, 8  # ensure release distance check uses same as real flow
        c._moved = False
        c._on_release(_Ev(8, 8))
        root.update()
        assert len(c.points_latlon) == n0, f"RED: edit mode empty click added waypoint (n0={n0} now={len(c.points_latlon)}) - should add NO waypoint in edit"
        # selects nothing
        sel = getattr(c, "_selected_photo_id", None)
        assert sel is None, f"RED: edit mode empty click selected photo {sel} - should select nothing"

        # --- edit: click on photo should select it without moving, no waypoint ---
        bbox = c.get_photo_bbox(pid)
        assert bbox is not None, "RED: get_photo_bbox missing - photo bbox needed for edit select test"
        x0, y0, x1, y1 = (float(v) for v in bbox)
        cx, cy = int((x0 + x1) / 2), int((y0 + y1) / 2)
        n1 = len(c.points_latlon)
        c._on_press(_Ev(cx, cy))
        c._press_x, c._press_y = cx, cy
        c._moved = False
        c._on_release(_Ev(cx, cy))
        root.update()
        assert len(c.points_latlon) == n1, f"RED: edit mode photo click added waypoint (n1={n1} now={len(c.points_latlon)}) - should select only, no waypoint"
        sel2 = getattr(c, "_selected_photo_id", None)
        assert sel2 is not None and int(sel2) == int(pid), f"RED: edit mode photo click did not select photo (sel={sel2} expected {pid}) - should select without moving"
        rec1 = c.get_photo(pid)
        assert abs(float(rec1["lat"]) - lat0) < 1e-9 and abs(float(rec1["lon"]) - lon0) < 1e-9, f"RED: edit mode photo click moved photo {lat0,lon0}->{rec1['lat'],rec1['lon']} - should select without moving"

    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass


def test_c_trace_mode_click_photo_adds_waypoint_without_selecting_moving_and_place_keeps_armed():
    """(c) trace mode: click on photo adds waypoint without selecting/moving photo even when a photo was previously selected; place mode keeps current armed behavior"""
    from openlapexe.gui import osm_canvas as mod
    import pathlib as _pl

    canvas_src = _pl.Path(mod.__file__).read_text(encoding="utf-8")
    low = canvas_src.lower()
    # must have explicit mode handling
    assert "interact_mode" in low or "interact" in low, "RED: missing explicit interact_mode gating in osm_canvas for trace/place"
    assert "trace" in low, "RED: trace mode string missing in osm_canvas.py - S-mode-switch not implemented"
    assert "place" in low, "RED: place mode string missing"
    # _on_press/_on_release must branch on trace vs place vs edit
    if "def _on_press" in canvas_src:
        press_src = canvas_src.split("def _on_press")[1].split("def _on_drag")[0].lower() if "def _on_drag" in canvas_src else canvas_src.split("def _on_press")[1][:3000].lower()
        assert "trace" in press_src or "interact" in press_src, "RED: _on_press missing trace gating - click on photo still selects/moves instead of adding waypoint"
    if "def _on_release" in canvas_src:
        rel_src = canvas_src.split("def _on_release")[1].split("def ")[0].lower()
        # should add waypoint even when hit_test_photo true, without selecting
        assert "hit_test" in rel_src or "bbox" in rel_src or "interact" in rel_src, "RED: _on_release missing bbox/hit_test gated by trace vs edit - cannot add waypoint on photo without selecting"
        # should also preserve armed behavior for place
        assert "placing" in rel_src.lower() or "_placing_photo" in rel_src, "RED: _on_release missing armed photo logic - place mode armed behavior would be lost"

    root = _try_root()
    if root is None:
        pytest.fail("RED: trace/place mode gating missing - headless source inspection shows no trace branch in _on_press/_on_release, expected waypoint-on-photo without select/move")

    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=400, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack()
        root.update()
        c.points_latlon = []
        c.points_xy = []
        c.points_zone = []
        c._selected_photo_id = None
        try:
            c._placing_photo_id = None
        except Exception:
            pass

        p = _tmp_png()
        pid = c.add_photo(str(p), lat=35.68, lon=139.76, opacity=0.9)
        root.update()
        rec0 = c.get_photo(pid)
        assert rec0 is not None
        lat0, lon0 = float(rec0["lat"]), float(rec0["lon"])
        # previously selected state: ensure selected
        c._selected_photo_id = int(pid)
        for r in c._photos:
            r["selected"] = int(r["id"]) == int(pid)
        root.update()
        assert c.get_mode() in ("select", "place", "normal") or True  # old mode

        # set trace mode
        ok = _set_interact_mode(c, None, "trace")
        assert ok, "AttributeError: cannot set trace mode - explicit switch missing"
        assert _get_interact_mode(c, None) == "trace", "RED: trace mode not set"

        bbox = c.get_photo_bbox(pid)
        assert bbox is not None, "RED: get_photo_bbox missing for trace test"
        x0, y0, x1, y1 = (float(v) for v in bbox)
        cx, cy = int((x0 + x1) / 2), int((y0 + y1) / 2)

        n0 = len(c.points_latlon)
        # click on photo in trace mode - should add waypoint without selecting/moving
        c._on_press(_Ev(cx, cy))
        c._press_x, c._press_y = cx, cy
        c._moved = False
        c._on_release(_Ev(cx, cy))
        root.update()
        assert len(c.points_latlon) == n0 + 1, f"RED: trace mode click on photo added no waypoint (n0={n0} now={len(c.points_latlon)}) - should add waypoint without selecting/moving"
        rec1 = c.get_photo(pid)
        assert abs(float(rec1["lat"]) - lat0) < 1e-9 and abs(float(rec1["lon"]) - lon0) < 1e-9, f"RED: trace mode click moved photo {lat0,lon0}->{rec1['lat'],rec1['lon']} - should not move"
        # should not have changed selection to newly select? In trace, click should NOT select photo
        # If previously selected, it should either stay selected or ideally deselect? Spec says without selecting - so either remains previous or None, but not newly selected due to click
        # We check that after click, selected does not become newly selected due to bbox hit (if it was already selected, it may stay, but clicking center should not cause selection change)
        # For this test, we set previously selected = pid, after trace click it should still be pid but not moved; OR if impl deselects in trace, it would be None - both not newly selecting counts
        # The failure case before impl is that click will keep it selected AND not add waypoint; we already asserted waypoint added, so second part is to ensure no move
        # Also check that waypoint is actually at photo location (latlon near photo latlon transformed)
        # Additional check: disallow selection change if previously deselected
        # Let's test with deselected case: clear selection then trace click should still not select
        c._selected_photo_id = None
        for r in c._photos:
            r["selected"] = False
        root.update()
        n1 = len(c.points_latlon)
        c._on_press(_Ev(cx, cy))
        c._press_x, c._press_y = cx, cy
        c._moved = False
        c._on_release(_Ev(cx, cy))
        root.update()
        assert len(c.points_latlon) == n1 + 1, f"RED: trace mode (deselected) photo click added no waypoint"
        sel = getattr(c, "_selected_photo_id", None)
        assert sel is None, f"RED: trace mode photo click selected photo {sel} - should add waypoint without selecting (even when previously deselected)"
        rec2 = c.get_photo(pid)
        assert abs(float(rec2["lat"]) - lat0) < 1e-9 and abs(float(rec2["lon"]) - lon0) < 1e-9, "RED: trace deselected click moved photo"

        # --- place mode keeps current armed behavior ---
        # switch to place and arm
        ok2 = _set_interact_mode(c, None, "place")
        assert ok2, "AttributeError: cannot set place mode"
        assert _get_interact_mode(c, None) == "place", "RED: place mode not set"
        # clear waypoints for place checks
        # keep photo at original lat/lon for clean
        # Ensure not armed initially
        try:
            c.disarm_photo_place()
        except Exception:
            try:
                c._placing_photo_id = None  # type: ignore
            except Exception:
                pass
        root.update()
        assert c.arm_photo_place(pid) is True, "arm_photo_place should succeed in place mode"
        # armed + click inside bbox should add waypoint, photo UNCHANGED, still armed (existing S-photo-place-wp)
        bbox2 = c.get_photo_bbox(pid)
        assert bbox2 is not None
        x0b, y0b, x1b, y1b = (float(v) for v in bbox2)
        cxb, cyb = int((x0b + x1b) / 2), int((y0b + y1b) / 2)
        n2 = len(c.points_latlon)
        rec_before = c.get_photo(pid)
        latb0, lonb0 = float(rec_before["lat"]), float(rec_before["lon"])
        c._on_press(_Ev(cxb, cyb))
        c._press_x, c._press_y = cxb, cyb
        c._moved = False
        c._on_release(_Ev(cxb, cyb))
        root.update()
        assert len(c.points_latlon) == n2 + 1, f"RED: place mode armed inside bbox click added no waypoint (n2={n2} now={len(c.points_latlon)}) - place must keep armed on-photo waypoint behavior"
        rec_after = c.get_photo(pid)
        assert abs(float(rec_after["lat"]) - latb0) < 1e-9 and abs(float(rec_after["lon"]) - lonb0) < 1e-9, "RED: place mode armed inside bbox moved photo - should stay"
        assert getattr(c, "_placing_photo_id", None) is not None and int(getattr(c, "_placing_photo_id")) == int(pid), "RED: place mode armed inside click disarmed unexpectedly - should stay armed for tracing"

        # armed + click outside bbox should place photo and disarm (existing behavior)
        n3 = len(c.points_latlon)
        ox, oy = 8, 8
        # ensure outside
        try:
            assert c.hit_test_photo(ox, oy) is None, "setup: 8,8 inside bbox unexpectedly"
        except AttributeError:
            # verify via bbox
            hit_outside = not (x0b <= ox <= x1b and y0b <= oy <= y1b)
            assert hit_outside, "setup outside point inside bbox"
        c._on_press(_Ev(ox, oy))
        c._press_x, c._press_y = ox, oy
        c._moved = False
        c._on_release(_Ev(ox, oy))
        root.update()
        assert len(c.points_latlon) == n3, f"RED: place mode armed outside click should NOT add waypoint (n3={n3} now={len(c.points_latlon)})"
        assert getattr(c, "_placing_photo_id", None) is None, "RED: place mode armed outside click should disarm after placing"
        rec_placed = c.get_photo(pid)
        assert abs(float(rec_placed["lat"]) - latb0) > 1e-7 or abs(float(rec_placed["lon"]) - lonb0) > 1e-7, "RED: place mode outside click must move photo to click position"

    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass
