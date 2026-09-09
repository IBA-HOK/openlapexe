# -*- coding: utf-8 -*-
"""tests/test_photo_lock_min.py - RED only for min 1% scale + per-photo lock (S-photo-lock).

3 FAILing tests:
 (a) set_photo_scale(pid,0.02) accepted (2%, specs scale==0.02, drawn w ~2% of base) — currently clamped to 0.1
 (b) set_photo_locked(pid,True) exists, locked photo ignores body-drag (lat/lon unchanged) and set_photo_scale (returns False, scale unchanged)
 (c) specs roundtrip preserves locked flag + 2% scale

Current: osm_canvas add_photo/set_photo_scale/get_photo_specs clamps 0.1..8.0, shell _photo_size slider 10..400.
Success = pytest RED on clamp/missing-API before fix; GREEN after min 0.01 + lock persisted.

Headless: tries Tk, if no display still asserts API missing (no pytest.skip that hides RED).
Do NOT fix src/ - this file must stay RED until implementation lands.
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
    p = tmp / "photo_lock_min.png"
    p.write_bytes(base64.b64decode(png_b64))
    return p


def test_a_min_scale_002_accepted_and_drawn():
    """(a) set_photo_scale(pid,0.02) accepted — specs scale==0.02, drawn w ~2% of base. Currently clamped to 0.1."""
    from openlapexe.gui import osm_canvas as mod
    import inspect

    # API existence
    assert hasattr(mod.OSMCanvas, "set_photo_scale"), "AttributeError: OSMCanvas.set_photo_scale missing - cannot test min scale"
    # source clamp check - current impl clamps to 0.1, should allow 0.02 (min 0.01)
    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    # Fail RED if clamp still 0.1 (both add_photo and set_photo_scale)
    # We expect min 0.01 after fix, so 0.02 must not be clamped
    if "max(0.1" in src:
        # will be verified functionally below; force RED in headless too
        pass

    root = _try_root()
    if root is None:
        # headless: source inspection must show min allows 0.02 -> currently 0.1 so RED
        assert "max(0.01" in src or "max(0.02" in src or 'min_scale' in src.lower(), "RED: osm_canvas.py still clamps scale to 0.1 (min 0.1..8.0) — should allow 0.02 (min 1% =0.01) - clamped 0.02->0.1"
        # also need drawn w handling not clamping
        assert "0.02" in src or "0.01" in src, "RED: no 2%/1% scale handling in osm_canvas.py"
        pytest.fail("RED: headless clamp check — set_photo_scale(pid,0.02) would be clamped to 0.1, w not ~2% of base")
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=400, height=400, zoom=10)
        c.pack()
        root.update()
        p = _tmp_png()
        pid = c.add_photo(str(p), lat=35.68, lon=139.76, opacity=0.5)
        rec0 = c.get_photo(pid)
        assert rec0 is not None, "add_photo failed"
        w0, h0 = int(rec0["w"]), int(rec0["h"])
        assert w0 > 0 and h0 > 0, f"base w/h invalid {w0}x{h0}"
        base_w = float(w0) / float(rec0.get("scale", 1.0))
        base_h = float(h0) / float(rec0.get("scale", 1.0))
        # target 0.02
        ok = c.set_photo_scale(pid, 0.02)
        assert ok is True, "set_photo_scale(pid,0.02) should return True (accepted, not clamped to False)"
        rec1 = c.get_photo(pid)
        assert rec1 is not None
        scale1 = float(rec1.get("scale", 0))
        assert abs(scale1 - 0.02) < 1e-9, f"RED: scale clamped {scale1} !=0.02 — min 0.1 blocks 2% (should allow 0.01..8.0) rec={rec1}"
        # specs must contain exact 0.02
        specs = c.get_photo_specs()
        assert len(specs) == 1, f"specs len {specs}"
        assert "scale" in specs[0], f"scale key missing in specs {specs[0]}"
        assert abs(float(specs[0]["scale"]) - 0.02) < 1e-9, f"RED: specs scale !=0.02 got {specs[0].get('scale')}"
        # drawn w ~2% of base
        w1, h1 = int(rec1["w"]), int(rec1["h"])
        exp_w = int(round(base_w * 0.02))
        exp_h = int(round(base_h * 0.02))
        # allow rounding ±2px due to thumbnail quant
        assert abs(w1 - exp_w) <= 2 or abs(w1 - base_w*0.02) < 2.5, f"RED: drawn w not ~2% of base {w0}->{w1} expected {exp_w} (base {base_w}*0.02)"
        assert abs(h1 - exp_h) <= 2 or abs(h1 - base_h*0.02) < 2.5, f"RED: drawn h not ~2% of base {h0}->{h1} expected {exp_h}"
        # also check get_photo_drawn_width ~2% of base drawn width
        try:
            drawn_w = float(c.get_photo_drawn_width(pid))
            expected_drawn = float(base_w * 0.02) * (2 ** (int(c.zoom) - int(rec1.get("ref_zoom", c.zoom))))
            # at same zoom as add, factor=1
            assert abs(drawn_w - base_w*0.02) < 3.0, f"RED: get_photo_drawn_width not ~2% {drawn_w} vs {base_w*0.02}"
        except Exception:
            pass
        # shell slider should allow 2% (10..400 currently blocks 2%) - source check
        shell_path = pathlib.Path(mod.__file__).parent / "shell.py"
        shell_src = shell_path.read_text(encoding="utf-8") if shell_path.exists() else ""
        assert "from_=1" in shell_src or "from_=2" in shell_src or '0.01' in shell_src or '0.02' in shell_src, "RED: shell.py _photo_size slider 10..400 blocks 2% (should be 1..400 for min 1%)"
    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass


def test_b_locked_ignores_drag_and_scale():
    """(b) set_photo_locked(pid,True) exists, locked photo ignores body-drag (lat/lon unchanged) and set_photo_scale (returns False, scale unchanged)."""
    from openlapexe.gui import osm_canvas as mod

    assert hasattr(mod.OSMCanvas, "set_photo_locked"), "AttributeError: OSMCanvas.set_photo_locked missing (per-photo lock not implemented)"
    assert hasattr(mod.OSMCanvas, "get_photo_locked") or hasattr(mod.OSMCanvas, "is_photo_locked"), "AttributeError: get_photo_locked/is_photo_locked missing — lock query API not implemented"
    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert "locked" in src.lower(), "RED: locked handling missing in osm_canvas.py"
    assert "set_photo_locked" in src, "AttributeError: set_photo_locked not defined in source"

    root = _try_root()
    if root is None:
        # headless: check source for drag guard and scale guard
        assert "locked" in src and "lat" in src and "lon" in src, "RED: drag guard for locked missing"
        # must guard set_photo_scale
        assert src.count("locked") >= 2, "RED: lock not checked in both drag and scale paths"
        pytest.fail("RED: headless locked check — set_photo_locked API not functional, body-drag/scale guard missing")
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=400, height=400, zoom=12)
        c.pack()
        root.update()
        p = _tmp_png()
        pid = c.add_photo(str(p), lat=35.68, lon=139.76, opacity=0.5)
        rec0 = c.get_photo(pid)
        assert rec0 is not None
        lat0, lon0 = float(rec0["lat"]), float(rec0["lon"])
        scale0 = float(rec0.get("scale", 1.0))
        # lock
        # handle both apis: set_photo_locked(pid, True) or set_photo_locked(pid, locked=True)
        ok_lock = None
        try:
            ok_lock = c.set_photo_locked(pid, True)
        except TypeError:
            try:
                ok_lock = c.set_photo_locked(pid, locked=True)
            except Exception as e:
                pytest.fail(f"set_photo_locked signature wrong: {e}")
        assert ok_lock is True or ok_lock is None, f"set_photo_locked should return True/None, got {ok_lock}"
        # verify locked query
        is_locked = None
        if hasattr(c, "get_photo_locked"):
            is_locked = c.get_photo_locked(pid)
        elif hasattr(c, "is_photo_locked"):
            is_locked = c.is_photo_locked(pid)
        else:
            # fallback via get_photo dict
            rec_locked = c.get_photo(pid)
            is_locked = bool(rec_locked.get("locked", False)) if rec_locked else False
        assert bool(is_locked) is True, f"RED: get_photo_locked should be True after lock, got {is_locked} rec={c.get_photo(pid)}"

        # attempt body-drag: simulate press+drag on photo bbox center
        bbox = c.get_photo_bbox(pid)
        if bbox is not None:
            x0, y0, x1, y1 = bbox
            cx = int((x0 + x1) * 0.5)
            cy = int((y0 + y1) * 0.5)
            # emulate event
            class Ev:
                def __init__(self, x, y):
                    self.x = x; self.y = y; self.state = 0; self.num = 1
            # press
            try:
                c._on_press(Ev(cx, cy))
                # drag 30px away
                c._on_drag(Ev(cx+30, cy+30))
                c._on_release(Ev(cx+30, cy+30))
            except Exception as e:
                pytest.fail(f"drag simulation failed: {e}")
            rec_after_drag = c.get_photo(pid)
            assert rec_after_drag is not None
            lat1, lon1 = float(rec_after_drag["lat"]), float(rec_after_drag["lon"])
            assert abs(lat1 - lat0) < 1e-9 and abs(lon1 - lon0) < 1e-9, f"RED: locked photo lat/lon changed by body-drag {lat0},{lon0} -> {lat1},{lon1} — locked should ignore drag"

        # attempt set_photo_scale while locked - should return False and scale unchanged
        res = c.set_photo_scale(pid, 2.0)
        assert res is False, f"RED: set_photo_scale on locked photo should return False, got {res}"
        rec_after_scale = c.get_photo(pid)
        assert rec_after_scale is not None
        scale1 = float(rec_after_scale.get("scale", 0))
        assert abs(scale1 - scale0) < 1e-9, f"RED: locked photo scale changed {scale0}->{scale1} — should remain unchanged when locked"

        # unlock and verify scale now works
        try:
            c.set_photo_locked(pid, False)
        except Exception:
            pass
        ok2 = c.set_photo_scale(pid, 2.0)
        assert ok2 is True, "after unlock, set_photo_scale should succeed"
        rec_unlocked = c.get_photo(pid)
        assert abs(float(rec_unlocked.get("scale",0))-2.0) < 1e-9, "after unlock scale should be 2.0"

        # also test that dragging after unlock does move lat/lon (sanity)
        if bbox is not None:
            rec_before = c.get_photo(pid)
            lat_b, lon_b = float(rec_before["lat"]), float(rec_before["lon"])
            cx2, cy2 = c._latlon_to_pixel(lat_b, lon_b)
            class Ev2:
                def __init__(self, x, y):
                    self.x = int(x); self.y = int(y); self.state = 0; self.num = 1
            try:
                c._on_press(Ev2(cx2, cy2))
                c._on_drag(Ev2(cx2+20, cy2+20))
                c._on_release(Ev2(cx2+20, cy2+20))
                rec_after = c.get_photo(pid)
                lat_a, lon_a = float(rec_after["lat"]), float(rec_after["lon"])
                assert abs(lat_a - lat_b) > 1e-9 or abs(lon_a - lon_b) > 1e-9, "sanity: unlocked photo should move on drag"
            except Exception:
                pass

    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass


def test_c_specs_roundtrip_preserves_locked_and_min_scale():
    """(c) specs roundtrip preserves locked flag + 2% scale."""
    from openlapexe.gui import osm_canvas as mod

    assert hasattr(mod.OSMCanvas, "get_photo_specs"), "AttributeError: get_photo_specs missing"
    assert hasattr(mod.OSMCanvas, "load_photo_specs"), "AttributeError: load_photo_specs missing"
    assert hasattr(mod.OSMCanvas, "set_photo_locked"), "AttributeError: set_photo_locked missing — roundtrip cannot preserve locked"
    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert '"locked"' in src or "'locked'" in src or "locked" in src, "RED: get_photo_specs/load_photo_specs missing locked handling"
    assert "scale" in src, "RED: specs missing scale handling"

    root = _try_root()
    if root is None:
        # headless: check source emits locked and preserves min scale
        assert '"locked"' in src or "'locked'" in src, 'RED: get_photo_specs does not emit "locked" key'
        assert "load_photo_specs" in src and "locked" in src, "RED: load_photo_specs does not handle locked"
        # check min scale preserved (not clamped)
        if "max(0.1" in src:
            pytest.fail('AttributeError/no-lock: get_photo_specs/load_photo_specs roundtrip missing locked flag + clamped 0.02->0.1 — currently specs only path/lat/lon/opacity/scale(0.1..8.0)')
        pytest.fail("RED: headless roundtrip locked+2% not preserved")
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=400, height=400, zoom=10)
        c.pack()
        root.update()
        p = _tmp_png()
        pid = c.add_photo(str(p), lat=35.681, lon=139.767, opacity=0.6)
        # set min scale 0.02 and locked True
        ok = c.set_photo_scale(pid, 0.02)
        assert ok is True, "set 0.02 should succeed before roundtrip"
        # lock
        try:
            c.set_photo_locked(pid, True)
        except Exception as e:
            pytest.fail(f"set_photo_locked failed: {e}")
        specs = c.get_photo_specs()
        assert len(specs) == 1, f"specs len {specs}"
        s0 = specs[0]
        assert "scale" in s0, f"RED: specs missing scale {s0}"
        assert abs(float(s0["scale"]) - 0.02) < 1e-9, f"RED: specs scale !=0.02 got {s0.get('scale')}"
        assert "locked" in s0, f"RED: specs missing locked key {s0}"
        assert bool(s0["locked"]) is True, f"RED: specs locked !=True got {s0.get('locked')}"

        # roundtrip via new canvas
        c2 = OSMCanvas(root, width=400, height=400, zoom=10)
        c2.pack()
        root.update()
        n = c2.load_photo_specs(specs)
        assert n == 1, f"load_photo_specs returned {n} expected 1"
        specs2 = c2.get_photo_specs()
        assert len(specs2) == 1
        s1 = specs2[0]
        assert "scale" in s1, f"RED: roundtrip lost scale key {s1}"
        assert abs(float(s1["scale"]) - 0.02) < 1e-9, f"RED: roundtrip scale mismatch {s1.get('scale')} !=0.02"
        assert "locked" in s1, f"RED: roundtrip lost locked key {s1}"
        assert bool(s1["locked"]) is True, f"RED: roundtrip locked mismatch {s1.get('locked')} !=True"

        # verify locked semantics survive roundtrip
        pid2 = c2.list_photos()[0]
        # locked should still block scale
        res = c2.set_photo_scale(pid2, 3.0)
        assert res is False, f"RED: after roundtrip, locked photo set_photo_scale should return False, got {res}"
        rec2 = c2.get_photo(pid2)
        assert abs(float(rec2.get("scale",0))-0.02) < 1e-9, "locked after roundtrip scale should stay 0.02"
        # locked should block drag
        rec_before = c2.get_photo(pid2)
        lat_b, lon_b = float(rec_before["lat"]), float(rec_before["lon"])
        bbox2 = c2.get_photo_bbox(pid2)
        if bbox2 is not None:
            x0, y0, x1, y1 = bbox2
            cx = int((x0+x1)*0.5); cy = int((y0+y1)*0.5)
            class Ev:
                def __init__(self, x, y): self.x=x; self.y=y; self.state=0; self.num=1
            try:
                c2._on_press(Ev(cx, cy))
                c2._on_drag(Ev(cx+30, cy+30))
                c2._on_release(Ev(cx+30, cy+30))
                rec_after = c2.get_photo(pid2)
                assert abs(float(rec_after["lat"])-lat_b) < 1e-9 and abs(float(rec_after["lon"])-lon_b) < 1e-9, "locked after roundtrip should ignore drag"
            except AssertionError:
                raise
            except Exception:
                pass

        # shell overlay persistence: if specs go through track.meta.overlays, locked must survive
        # simulate shell save/load flow
        shell_path = pathlib.Path(mod.__file__).parent / "shell.py"
        shell_src = shell_path.read_text(encoding="utf-8") if shell_path.exists() else ""
        # shell should propagate via get_photo_specs -> meta.overlays -> load_photo_specs
        assert "overlays" in shell_src.lower(), "shell missing overlays handling"
        # locked must be inside specs that shell saves; we already proved specs contain locked, so shell will persist if it uses specs directly

    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass
