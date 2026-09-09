# -*- coding: utf-8 -*-
"""tests/test_photo_rotate.py - RED only for photo rotation (S-photo-drag core).

Tests:
 (a) set_photo_rotation(pid,30) -> specs angle_deg==30 and get_photo shows 30
 (b) specs roundtrip preserves angle_deg (+ scale/ref_zoom/width_m)
 (c) no-PIL headless still asserts API (set_photo_rotation exists, PIL optional try-import, tk fallback)

Headless checks fallback to source inspection + pytest.fail to stay RED until impl.
"""
from __future__ import annotations

import base64
import pathlib
import tempfile

import pytest


def _try_root():
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
    p = tmp / "photo_rotate.png"
    p.write_bytes(base64.b64decode(png_b64))
    return p


class _Evt:
    def __init__(self, x, y, state=0, num=1):
        self.x = int(x)
        self.y = int(y)
        self.state = int(state)
        self.num = int(num)


def test_a_set_photo_rotation_specs_angle_30():
    """(a) set_photo_rotation(pid,30) -> specs angle_deg ==30"""
    from openlapexe.gui import osm_canvas as mod

    assert hasattr(mod.OSMCanvas, "set_photo_rotation"), "AttributeError: OSMCanvas.set_photo_rotation missing - rotation not implemented"
    assert hasattr(mod.OSMCanvas, "get_photo_rotation") or hasattr(mod.OSMCanvas, "set_photo_rotation"), "AttributeError: rotation API missing"
    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert "angle_deg" in src, "AttributeError: angle_deg missing in osm_canvas.py"
    assert "set_photo_rotation" in src, "AttributeError: set_photo_rotation not in src"
    assert "get_photo_specs" in src, "AttributeError: get_photo_specs missing"
    # check specs emits angle_deg
    if "def get_photo_specs" in src:
        specs_src = src.split("def get_photo_specs")[1].split("def ")[0]
        assert "angle_deg" in specs_src, "AttributeError: get_photo_specs does not emit angle_deg"
    # check _draw_photos handles angle / PIL rotate
    if "def _draw_photos" in src:
        draw_src = src.split("def _draw_photos")[1].split("def ")[0]
        assert "angle" in draw_src.lower() and ("rotate" in draw_src.lower() or "angle_deg" in draw_src.lower()), "AttributeError: _draw_photos missing rotation handling"
    # PIL optional try-import + tk fallback for handle hidden
    assert "PIL" in src or "Image" in src, "AttributeError: PIL handling missing for smooth resize/rotate"
    assert "subsample" in src or "zoom" in src, "AttributeError: tk fallback subsample/zoom missing"

    root = _try_root()
    if root is None:
        pytest.fail("no-rotation: headless but rotation API not functional - expected set_photo_rotation->specs angle==30")

    try:
        from openlapexe.gui.osm_canvas import OSMCanvas
        c = OSMCanvas(root, width=300, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack(); root.update()
        p = _tmp_png()
        pid = c.add_photo(str(p), lat=35.68, lon=139.76, opacity=0.5, scale=1.0)
        root.update()
        ok = c.set_photo_rotation(pid, 30)
        assert ok is True, "set_photo_rotation should return True"
        rec = c.get_photo(pid)
        assert rec is not None
        assert "angle_deg" in rec, f"rec missing angle_deg {rec.keys()}"
        assert abs(float(rec["angle_deg"]) - 30.0) < 1e-9, f"angle_deg !=30 got {rec['angle_deg']}"
        # also get_photo_rotation if exists
        if hasattr(c, "get_photo_rotation"):
            assert abs(float(c.get_photo_rotation(pid)) - 30.0) < 1e-9
        specs = c.get_photo_specs()
        assert len(specs) == 1
        assert "angle_deg" in specs[0], f"specs missing angle_deg {specs[0]}"
        assert abs(float(specs[0]["angle_deg"]) - 30.0) < 1e-9, f"specs angle !=30 {specs[0]}"
        # check rotation handle would be hidden if no PIL: we verify tk fallback exists but not crash
        # drawn bbox should still be valid
        if hasattr(c, "get_photo_bbox"):
            bbox = c.get_photo_bbox(pid)
            assert isinstance(bbox, (list, tuple)) and len(bbox) == 4, f"bbox {bbox}"
            x0, y0, x1, y1 = bbox
            assert x1 > x0 and y1 > y0, f"bbox invalid {bbox}"
    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass


def test_b_specs_roundtrip_preserves_angle():
    """(b) specs roundtrip preserves angle_deg"""
    from openlapexe.gui import osm_canvas as mod

    assert hasattr(mod.OSMCanvas, "set_photo_rotation"), "AttributeError: set_photo_rotation missing"
    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert "angle_deg" in src, "AttributeError: angle_deg missing"
    assert "load_photo_specs" in src, "AttributeError: load_photo_specs missing"
    if "def load_photo_specs" in src:
        load_src = src.split("def load_photo_specs")[1].split("def ")[0]
        assert "angle_deg" in load_src, "AttributeError: load_photo_specs does not handle angle_deg"

    root = _try_root()
    if root is None:
        pytest.fail("no-roundtrip: headless but specs roundtrip missing angle_deg")

    try:
        from openlapexe.gui.osm_canvas import OSMCanvas
        c = OSMCanvas(root, width=300, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack(); root.update()
        p = _tmp_png()
        pid = c.add_photo(str(p), lat=35.68, lon=139.76, opacity=0.5, scale=1.0)
        c.set_photo_rotation(pid, 45)
        c.set_photo_scale(pid, 1.5)
        specs = c.get_photo_specs()
        assert any("angle_deg" in s for s in specs), f"specs missing angle {specs}"
        assert any(abs(float(s.get("angle_deg",0)) - 45) < 1e-9 for s in specs), f"angle 45 not in {specs}"
        # also must preserve ref_zoom/scale/width_m
        assert "ref_zoom" in specs[0] and "scale" in specs[0], f"specs missing ref_zoom/scale {specs[0]}"
        c2 = OSMCanvas(root, width=300, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c2.pack(); root.update()
        n = c2.load_photo_specs(specs)
        assert n == 1, f"load returned {n}"
        specs2 = c2.get_photo_specs()
        assert len(specs2) == 1
        assert "angle_deg" in specs2[0], f"roundtrip lost angle {specs2[0]}"
        assert abs(float(specs2[0]["angle_deg"]) - 45) < 1e-9, f"roundtrip angle mismatch {specs2[0]['angle_deg']} !=45"
        # scale+ref_zoom also preserved
        assert abs(float(specs2[0]["scale"]) - float(specs[0]["scale"])) < 1e-9
        assert int(specs2[0]["ref_zoom"]) == int(specs[0]["ref_zoom"])
        rec2 = c2.get_photo(c2.list_photos()[0])
        assert rec2 is not None and abs(float(rec2["angle_deg"])-45) < 1e-9
    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass


def test_c_no_pil_headless_still_asserts_api():
    """(c) no-PIL headless still asserts API (PIL optional try-import, tk fallback, handle hidden if no PIL)"""
    from openlapexe.gui import osm_canvas as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    # PIL optional try-import
    assert "try" in src and "PIL" in src, "AttributeError: PIL optional try-import missing"
    # fallback hiding handle if no PIL -> _draw_photos should check PIL availability before drawing handles
    # we look for import error handling or has_pil flag
    lower = src.lower()
    has_fallback = ("subsample" in lower or "zoom" in lower) and ("pillow" in lower or "pil" in lower or "imagetk" in lower)
    assert has_fallback, "AttributeError: tk fallback (subsample/zoom) missing for PIL-less case"
    # API must exist even without PIL
    assert hasattr(mod.OSMCanvas, "set_photo_rotation") and hasattr(mod.OSMCanvas, "get_photo_rotation"), "AttributeError: rotation API must exist even without PIL"
    # check angle_deg defaults to 0
    assert "angle_deg" in src, "AttributeError: angle_deg handling missing"
    # verify that load ignores unknown keys (should not crash)
    if "def load_photo_specs" in src:
        # should gracefully ignore unknown keys - at least not raise
        pass

    root = _try_root()
    if root is None:
        # headless still must have API - if src passes above, this is now considered RED until impl sets angle default
        # Force headless functional check via class without Tk: simulate specs ignore unknown
        try:
            from openlapexe.gui.osm_canvas import OSMCanvas as C2
            # Check that load_photo_specs signature exists and would ignore unknown keys (src inspection)
            assert "unknown" in src.lower() or "get" in src.lower(), "AttributeError: load_photo_specs should ignore unknown keys"
        except Exception:
            pass
        pytest.fail("no-PIL headless: API should still work without PIL - rotation handle hidden, but set_photo_rotation must exist")

    try:
        from openlapexe.gui.osm_canvas import OSMCanvas
        c = OSMCanvas(root, width=300, height=300, zoom=10)
        c.pack(); root.update()
        p = _tmp_png()
        # load with unknown key should not crash and default angle 0
        specs_unknown = [{"path": str(p), "lat": 35.68, "lon": 139.76, "opacity": 0.5, "scale": 1.0, "ref_zoom": 10, "angle_deg": 10, "unknown_key": 123, "extra": "x"}]
        n = c.load_photo_specs(specs_unknown)
        assert n == 1, f"load with unknown keys failed {n}"
        pid = c.list_photos()[0]
        rec = c.get_photo(pid)
        assert rec is not None
        assert abs(float(rec.get("angle_deg", 0)) - 10) < 1e-9
        # default angle when not supplied should be 0
        c2 = OSMCanvas(root, width=300, height=300, zoom=10)
        c2.pack(); root.update()
        specs_no_angle = [{"path": str(p), "lat": 35.68, "lon": 139.76, "opacity": 0.5, "scale": 1.2}]
        n2 = c2.load_photo_specs(specs_no_angle)
        assert n2 == 1
        rec2 = c2.get_photo(c2.list_photos()[0])
        assert abs(float(rec2.get("angle_deg", -1)) - 0.0) < 1e-9, f"default angle not 0 {rec2}"
        # also add_photo default angle 0, ref_zoom current
        pid3 = c2.add_photo(str(p), lat=35.68, lon=139.76)
        rec3 = c2.get_photo(pid3)
        assert abs(float(rec3.get("angle_deg", -1)) - 0.0) < 1e-9
        assert "ref_zoom" in rec3 and int(rec3["ref_zoom"]) == int(c2.get_zoom()) if hasattr(c2,"get_zoom") else "ref_zoom" in rec3
    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass
