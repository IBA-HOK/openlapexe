# -*- coding: utf-8 -*-
"""tests/test_photo_drag_zoom.py - RED only for map-linked photo guide (S-photo-drag).

3 FAILing tests for map-linked photo guide:
 (a) body-drag moves photo lat/lon: add_photo at center, press-drag-release inside photo bbox away from waypoints changes rec lat/lon toward drop point
 (b) zoom keeps ground footprint: drawn pixel width doubles on zoom+1 (tolerance +-25%) while width_m/ref_zoom unchanged
 (c) specs roundtrip preserves scale+ref_zoom

Current: photos fixed-pixel center-anchor, no bbox hit-test, drag only handles waypoints/pan; goal map-linked guide (position+ground size survive zoom, directly draggable).
Success = pytest RED proving no drag support and fixed-pixel draw.

Headless: tries Tk, if no display still asserts API missing (no pytest.skip that hides RED) via assert hasattr + source inspection + pytest.fail.

Do NOT fix src/ - this file must stay RED until implementation lands.
"""
from __future__ import annotations

import base64
import math
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
        # headless: return None so tests can still assert AttributeError/no-drag via class inspection
        return None


def _tmp_png() -> pathlib.Path:
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = tmp / "photo_drag.png"
    p.write_bytes(base64.b64decode(png_b64))
    return p


class _Evt:
    def __init__(self, x, y, state=0, num=1):
        self.x = int(x)
        self.y = int(y)
        self.state = int(state)
        self.num = int(num)


def test_a_body_drag_moves_photo_latlon():
    """(a) body-drag moves photo lat/lon: add_photo at center, press-drag-release inside photo bbox away from waypoints changes rec lat/lon toward drop point"""
    from openlapexe.gui import osm_canvas as mod

    # --- HEADLESS API CHECKS (must FAIL now, not skip-green) ---
    # Expect photo bbox hit-test and drag support; current only handles waypoints/pan.
    # Check for photo drag state/method that will exist after S-photo-drag.
    assert hasattr(mod.OSMCanvas, "get_photo_bbox") or hasattr(mod.OSMCanvas, "hit_test_photo") or hasattr(mod.OSMCanvas, "_dragging_photo_id") or hasattr(mod.OSMCanvas, "_dragging_photo"), \
        "AttributeError: OSMCanvas photo bbox hit-test/drag missing (no drag support) - expected get_photo_bbox or _dragging_photo_id"
    # Source inspection: _on_press must handle photo bbox before waypoint/pan
    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    # isolate _on_press source chunk
    if "def _on_press" in src and "def _on_drag" in src:
        on_press_src = src.split("def _on_press")[1].split("def _on_drag")[0]
    else:
        on_press_src = ""
    assert "photo" in on_press_src.lower() and ("bbox" in on_press_src.lower() or "dragging_photo" in on_press_src.lower() or "hit_test" in on_press_src.lower()), \
        "AttributeError: _on_press has no photo bbox hit-test (fixed-pixel center-anchor, no bbox)"
    # also _on_drag must handle photo
    if "def _on_drag" in src and "def _on_release" in src:
        on_drag_src = src.split("def _on_drag")[1].split("def _on_release")[0]
    else:
        on_drag_src = ""
    assert "photo" in on_drag_src.lower() and ("dragging_photo" in on_drag_src.lower() or "bbox" in on_drag_src.lower()), \
        "AttributeError: _on_drag has no photo drag handling (only waypoints/pan)"
    # Also check that photo rec will have ground footprint fields (for completeness)
    assert "width_m" in src or "ref_zoom" in src, "AttributeError: photo ground footprint fields width_m/ref_zoom missing"

    root = _try_root()
    if root is None:
        pytest.fail("no-drag: headless but photo body-drag API not implemented - AttributeError bbox/drag missing, expected lat/lon change on body drag")

    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=400, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack()
        root.update()

        # Ensure no waypoints interfere - clear any existing
        c.points_latlon = []
        c.points_xy = []
        c.points_zone = []

        p = _tmp_png()
        pid = c.add_photo(str(p), lat=35.68, lon=139.76, opacity=0.5, scale=1.0)
        root.update()
        rec0 = c.get_photo(pid)
        assert rec0 is not None, "add_photo failed"
        lat0, lon0 = float(rec0["lat"]), float(rec0["lon"])
        w0, h0 = int(rec0["w"]), int(rec0["h"])
        assert w0 > 0 and h0 > 0, f"photo w/h invalid {w0},{h0}"

        # Photo center in pixel
        px_c, py_c = c.latlon_to_pixel(lat0, lon0)
        # Choose press inside bbox but away from waypoint (no waypoint at center, so offset is safe)
        # Current fixed-pixel bbox: center +/- w/2, h/2
        # Use 0.3 * w inside bbox to guarantee inside, but not center
        px_press = int(px_c + w0 * 0.30)
        py_press = int(py_c + h0 * 0.25)
        # Verify press is inside bbox (sanity for test)
        assert abs(px_press - px_c) < w0 * 0.49 and abs(py_press - py_c) < h0 * 0.49, "press not inside bbox"

        # Drop point offset +40px away (still within canvas)
        px_drop = int(px_press + 40)
        py_drop = int(py_press + 30)
        drop_lat, drop_lon = c.pixel_to_latlon(px_drop, py_drop)

        # Simulate press-drag-release (distance >5 to be drag, not click)
        c._on_press(_Evt(px_press, py_press))
        # Ensure dragging photo is recognized (future should set _dragging_photo_id)
        # Current will treat as pan or waypoint miss -> no photo drag
        c._on_drag(_Evt(px_drop, py_drop))
        c._on_release(_Evt(px_drop, py_drop))
        root.update()

        rec1 = c.get_photo(pid)
        assert rec1 is not None
        lat1, lon1 = float(rec1["lat"]), float(rec1["lon"])

        # Photo should have moved toward drop point (distance reduced)
        # Compute haversine-ish simple Euclidean in lat/lon degrees for test
        dist0 = math.hypot(lat0 - drop_lat, lon0 - drop_lon)
        dist1 = math.hypot(lat1 - drop_lat, lon1 - drop_lon)
        # Also check absolute move
        moved = math.hypot(lat1 - lat0, lon1 - lon0)
        assert moved > 1e-6, f"no-drag: body-drag did not move photo lat/lon {lat0,lon0}->{lat1,lon1} (fixed-pixel, no bbox hit-test)"
        assert dist1 < dist0 * 0.95, f"no-drag: photo not moved toward drop point {dist0:.6f}->{dist1:.6f} drop={drop_lat,drop_lon} current={lat1,lon1} (drag only handles waypoints/pan)"
        # Also ensure not just pan: center should not have shifted dramatically if photo drag works
        # For this test, center move is not asserted; main is photo lat/lon change.
    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass


def test_b_zoom_keeps_ground_footprint():
    """(b) zoom keeps ground footprint: drawn pixel width doubles on zoom+1 (tolerance +-25%) while width_m/ref_zoom unchanged"""
    from openlapexe.gui import osm_canvas as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    # Headless API checks - must FAIL now because fixed-pixel draw has no ground footprint
    assert "width_m" in src and "ref_zoom" in src, "AttributeError: OSMCanvas photo ground footprint missing - expected width_m and ref_zoom fields for map-linked guide"
    # _draw_photos must scale with zoom (2**(zoom - ref_zoom) or tile logic)
    if "def _draw_photos" in src:
        draw_src = src.split("def _draw_photos")[1].split("def ")[0]
    else:
        draw_src = ""
    assert "zoom" in draw_src.lower() and ("width_m" in draw_src.lower() or "ref_zoom" in draw_src.lower() or "scale" in draw_src.lower() and "zoom" in draw_src.lower()), \
        "AttributeError: _draw_photos fixed-pixel center-anchor, no zoom ground footprint scaling (no width_m/ref_zoom handling)"
    # Also expect add_photo stores width_m/ref_zoom
    if "def add_photo" in src:
        add_src = src.split("def add_photo")[1].split("def ")[0]
    else:
        add_src = ""
    assert "width_m" in add_src or "ref_zoom" in add_src, "AttributeError: add_photo does not store width_m/ref_zoom (fixed-pixel)"

    root = _try_root()
    if root is None:
        pytest.fail("no-ground-footprint: headless but zoom ground footprint not implemented - drawn pixel width should double on zoom+1 while width_m/ref_zoom unchanged")

    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=400, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack()
        root.update()

        p = _tmp_png()
        pid = c.add_photo(str(p), lat=35.68, lon=139.76, opacity=0.5, scale=1.0)
        root.update()
        rec0 = c.get_photo(pid)
        assert rec0 is not None
        w0 = int(rec0.get("w", 0))
        h0 = int(rec0.get("h", 0))
        # Future fields: width_m and ref_zoom should exist and be preserved
        assert "width_m" in rec0 or "width_m" in str(rec0), f"no-ground-footprint: photo rec missing width_m {rec0.keys()}"
        assert "ref_zoom" in rec0, f"no-ground-footprint: photo rec missing ref_zoom {rec0.keys()}"
        width_m0 = float(rec0.get("width_m", rec0.get("width", 0)) if isinstance(rec0.get("width_m", None), (int, float)) else rec0.get("width_m", 0))
        ref_zoom0 = int(rec0.get("ref_zoom", rec0.get("refZoom", -1)) if rec0.get("ref_zoom") is not None else -1)
        # Also check via specs
        specs0 = c.get_photo_specs()
        assert len(specs0) == 1
        assert "width_m" in specs0[0] or "width" in specs0[0], f"no-ground-footprint: specs missing width_m {specs0[0]}"
        assert "ref_zoom" in specs0[0], f"no-ground-footprint: specs missing ref_zoom {specs0[0]}"

        # Measure drawn pixel width at zoom 12
        # Try to get bbox via canvas or via helper method if exists
        def _drawn_width(canvas, pid_):
            # Prefer new API if exists
            if hasattr(canvas, "get_photo_drawn_width"):
                try:
                    return float(canvas.get_photo_drawn_width(pid_))
                except Exception:
                    pass
            if hasattr(canvas, "get_photo_bbox"):
                try:
                    bbox = canvas.get_photo_bbox(pid_)
                    # bbox as (x0,y0,x1,y1) or (lat,lon,width_m)
                    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                        return abs(float(bbox[2]) - float(bbox[0]))
                except Exception:
                    pass
            # Fallback: use rec w/h or canvas item bbox
            try:
                rec = canvas.get_photo(pid_)
                if rec is not None and "w" in rec:
                    return float(rec["w"])
            except Exception:
                pass
            # Try canvas bbox of photo tag
            try:
                ids = canvas.find_withtag(f"photo_{pid_}")
                if ids:
                    # image has no bbox, try to estimate via image size
                    # Use stored w
                    rec2 = canvas.get_photo(pid_)
                    return float(rec2.get("w", 0)) if rec2 else 0.0
            except Exception:
                pass
            return 0.0

        drawn_w0 = _drawn_width(c, pid)
        assert drawn_w0 > 0, f"drawn width 0 at zoom 12 w0={w0} rec={rec0}"

        # Zoom +1: ground footprint kept, drawn pixel should double (~2x, tolerance +-25% => 1.5..2.5)
        c.set_zoom(13)
        root.update()
        # allow after_idle redraw
        for _ in range(5):
            root.update()

        rec1 = c.get_photo(pid)
        drawn_w1 = _drawn_width(c, pid)
        # width_m and ref_zoom must be unchanged
        assert "width_m" in rec1, f"no-ground-footprint: width_m lost after zoom {rec1}"
        assert "ref_zoom" in rec1, f"no-ground-footprint: ref_zoom lost after zoom {rec1}"
        width_m1 = float(rec1.get("width_m", 0))
        ref_zoom1 = int(rec1.get("ref_zoom", -1))
        assert width_m1 == width_m0 or abs(width_m1 - width_m0) < 1e-9, f"no-ground-footprint: width_m changed on zoom {width_m0}->{width_m1} (must stay ground footprint)"
        assert ref_zoom1 == ref_zoom0, f"no-ground-footprint: ref_zoom changed on zoom {ref_zoom0}->{ref_zoom1} (must stay)"

        # Drawn width should double
        ratio = drawn_w1 / drawn_w0 if drawn_w0 else 0
        assert 1.5 <= ratio <= 2.5, f"no-ground-footprint: drawn pixel width should double on zoom+1 (1.5..2.5) got {drawn_w0}->{drawn_w1} ratio {ratio:.2f} (fixed-pixel draw)"

        # Also check specs preserve width_m/ref_zoom across zoom
        specs1 = c.get_photo_specs()
        assert "width_m" in specs1[0] and "ref_zoom" in specs1[0], f"specs lost width_m/ref_zoom after zoom {specs1[0]}"
        assert float(specs1[0].get("width_m", 0)) == width_m0 or abs(float(specs1[0].get("width_m", 0)) - width_m0) < 1e-6, "specs width_m changed on zoom"

    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass


def test_c_specs_roundtrip_preserves_scale_and_ref_zoom():
    """(c) specs roundtrip preserves scale+ref_zoom"""
    from openlapexe.gui import osm_canvas as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    # Headless checks: specs must contain scale+ref_zoom, load must handle them
    assert hasattr(mod.OSMCanvas, "get_photo_specs") and hasattr(mod.OSMCanvas, "load_photo_specs"), \
        "AttributeError: get_photo_specs/load_photo_specs missing"
    # Current get_photo_specs only emits path/lat/lon/opacity/scale, no ref_zoom/width_m -> should FAIL
    # Check source contains ref_zoom handling in get_photo_specs/load_photo_specs
    assert "ref_zoom" in src, "AttributeError: get_photo_specs/load_photo_specs missing ref_zoom handling (no scale+ref_zoom roundtrip)"
    assert "width_m" in src, "AttributeError: get_photo_specs/load_photo_specs missing width_m handling"
    if "def get_photo_specs" in src:
        specs_src = src.split("def get_photo_specs")[1].split("def ")[0]
    else:
        specs_src = ""
    assert "scale" in specs_src and "ref_zoom" in specs_src, "AttributeError: get_photo_specs does not emit scale+ref_zoom"
    if "def load_photo_specs" in src:
        load_src = src.split("def load_photo_specs")[1].split("def ")[0]
    else:
        load_src = ""
    assert "scale" in load_src and "ref_zoom" in load_src, "AttributeError: load_photo_specs does not handle scale+ref_zoom"
    # Also add_photo should accept scale+ref_zoom/width_m
    if "def add_photo" in src:
        add_src = src.split("def add_photo")[1].split("def ")[0]
    else:
        add_src = ""
    assert "scale" in add_src, "AttributeError: add_photo missing scale param"

    root = _try_root()
    if root is None:
        pytest.fail("no-roundtrip: headless but specs roundtrip missing scale+ref_zoom - AttributeError get_photo_specs/load_photo_specs incomplete")

    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=300, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack()
        root.update()
        p = _tmp_png()
        pid = c.add_photo(str(p), lat=35.681, lon=139.767, opacity=0.6, scale=1.5)
        root.update()
        # If API supports setting ground footprint, try to set/get it; else this will fail to show missing field
        rec = c.get_photo(pid)
        assert rec is not None
        # Expect rec to have scale and ref_zoom (and maybe width_m)
        assert "scale" in rec or "scale" in str(rec), f"no-roundtrip: rec missing scale {rec}"
        assert "ref_zoom" in rec, f"no-roundtrip: rec missing ref_zoom {rec} (specs should preserve scale+ref_zoom)"
        # Set scale via set_photo_scale if exists (already in current, but ref_zoom not)
        if hasattr(c, "set_photo_scale"):
            c.set_photo_scale(pid, 1.8)
            root.update()
            rec2 = c.get_photo(pid)
            assert abs(float(rec2.get("scale", 0)) - 1.8) < 1e-9, f"scale not updated {rec2}"

        specs = c.get_photo_specs()
        assert len(specs) == 1, f"specs len {specs}"
        assert "scale" in specs[0], f"no-roundtrip: specs missing scale {specs[0]}"
        assert "ref_zoom" in specs[0], f"no-roundtrip: specs missing ref_zoom {specs[0]} (current only path/lat/lon/opacity/scale)"
        scale0 = float(specs[0].get("scale", 0))
        ref0 = int(specs[0].get("ref_zoom", -1))
        # width_m may also be required, but at least ref_zoom
        assert abs(scale0 - 1.8) < 1e-9 or abs(scale0 - 1.5) < 1e-9, f"scale mismatch {scale0}"

        # Roundtrip via new canvas / load_photo_specs
        c2 = OSMCanvas(root, width=300, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c2.pack()
        root.update()
        n = c2.load_photo_specs(specs)
        assert n == 1, f"load_photo_specs returned {n} expected 1"
        specs2 = c2.get_photo_specs()
        assert len(specs2) == 1
        assert "scale" in specs2[0], f"no-roundtrip: roundtrip lost scale {specs2[0]}"
        assert "ref_zoom" in specs2[0], f"no-roundtrip: roundtrip lost ref_zoom {specs2[0]}"
        assert abs(float(specs2[0].get("scale", 0)) - scale0) < 1e-9, f"roundtrip scale mismatch {specs2[0].get('scale')} != {scale0}"
        assert int(specs2[0].get("ref_zoom", -1)) == ref0, f"roundtrip ref_zoom mismatch {specs2[0].get('ref_zoom')} != {ref0}"

        # Also w/h should be preserved at same scale/ref_zoom
        rec_orig = c.get_photo(pid)
        rec_new = c2.get_photo(c2.list_photos()[0])
        assert rec_new is not None
        assert int(rec_new.get("w", 0)) == int(rec_orig.get("w", 0)) or abs(int(rec_new.get("w",0)) - int(rec_orig.get("w",0))) < 2, f"w not preserved {rec_orig} vs {rec_new}"
        # width_m preserved if exists
        if "width_m" in rec_orig:
            assert "width_m" in rec_new and abs(float(rec_new["width_m"]) - float(rec_orig["width_m"])) < 1e-6, f"width_m not preserved roundtrip {rec_orig.get('width_m')} vs {rec_new.get('width_m')}"

    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass
