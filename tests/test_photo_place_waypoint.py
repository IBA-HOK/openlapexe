# -*- coding: utf-8 -*-
"""tests/test_photo_place_waypoint.py - RED for armed on-photo waypoint + mode colors (S-photo-place-wp).

3 FAILing tests:
 (a) armed + click inside photo bbox adds waypoint, photo lat/lon UNCHANGED, still armed
 (b) armed + click outside any bbox places photo (existing behavior preserved)
 (c) shell _sync_osm_to_creator allows sync for armed on-photo clicks

Headless: tries Tk, asserts via source inspection (no skip-green).
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
    p = tmp / "photo_place_wp.png"
    p.write_bytes(base64.b64decode(png_b64))
    return p


class _Ev:
    def __init__(self, x, y, state=0, num=1):
        self.x = int(x)
        self.y = int(y)
        self.state = int(state)
        self.num = int(num)


def test_a_armed_inside_bbox_adds_waypoint_photo_unchanged_still_armed():
    from openlapexe.gui import osm_canvas as mod

    root = _try_root()
    if root is None:
        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        assert "hit_test_photo" in src and "get_photo_bbox" in src, "no-bbox: hit-test API missing"
        # armed block must consult bbox before moving photo
        armed = src[src.index("_placing_photo_id is not None"):]
        assert "bbox" in armed[:1500] or "hit_test" in armed[:1500], \
            "RED: armed block moves photo without bbox check - on-photo clicks cannot drop waypoints"
        return
    try:
        c = mod.OSMCanvas(root, width=300, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack()
        pid = c.add_photo(str(_tmp_png()), lat=35.68, lon=139.76, opacity=0.9)
        assert c.arm_photo_place(pid) is True
        bbox = c.get_photo_bbox(pid)
        assert bbox is not None, "RED: get_photo_bbox missing/None"
        x0, y0, x1, y1 = (float(v) for v in bbox)
        cx, cy = int((x0 + x1) / 2), int((y0 + y1) / 2)
        n0 = len(c.points_latlon)
        rec0 = c.get_photo(pid)
        lat0, lon0 = float(rec0["lat"]), float(rec0["lon"])
        c._on_press(_Ev(cx, cy))
        c._press_x, c._press_y = cx, cy
        c._moved = False
        c._on_release(_Ev(cx, cy))
        assert len(c.points_latlon) == n0 + 1, \
            f"RED: armed on-photo click added no waypoint (n0={n0} now={len(c.points_latlon)})"
        rec1 = c.get_photo(pid)
        assert abs(float(rec1["lat"]) - lat0) < 1e-9 and abs(float(rec1["lon"]) - lon0) < 1e-9, \
            "RED: armed on-photo click moved photo instead of waypoint"
        assert int(c._placing_photo_id) == int(pid), "RED: disarmed after on-photo click, tracing broken"
    finally:
        root.destroy()


def test_b_armed_outside_bbox_places_photo_preserves_existing():
    from openlapexe.gui import osm_canvas as mod

    root = _try_root()
    if root is None:
        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        assert "_placing_photo_id = None" in src, "RED: no disarm path - existing place behavior missing"
        return
    try:
        c = mod.OSMCanvas(root, width=300, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack()
        pid = c.add_photo(str(_tmp_png()), lat=35.68, lon=139.76, opacity=0.9)
        assert c.arm_photo_place(pid) is True
        n0 = len(c.points_latlon)
        # far corner, verify outside every bbox
        ox, oy = 8, 8
        try:
            assert c.hit_test_photo(ox, oy) is None, "test setup: corner unexpectedly inside photo bbox"
        except AttributeError:
            pass
        c._on_press(_Ev(ox, oy))
        c._press_x, c._press_y = ox, oy
        c._moved = False
        c._on_release(_Ev(ox, oy))
        assert len(c.points_latlon) == n0, \
            f"RED?: outside click must not add waypoint (n0={n0} now={len(c.points_latlon)})"
        assert c._placing_photo_id is None, "RED?: outside click must disarm after placing"
        rec1 = c.get_photo(pid)
        assert abs(float(rec1["lat"]) - 35.68) > 1e-7 or abs(float(rec1["lon"]) - 139.76) > 1e-7, \
            "RED?: outside click must move photo to click position"
    finally:
        root.destroy()


def test_c_sync_allowed_for_armed_on_photo_clicks():
    from openlapexe.gui import osm_canvas as mod
    from openlapexe.gui import shell as shmod
    import inspect

    src = pathlib.Path(shmod.__file__).read_text(encoding="utf-8")
    assert "_sync_osm_to_creator" in src, "RED: _sync_osm_to_creator missing"
    # sync guard must allow armed on-photo clicks (bbox exception), not blanket-suppress
    seg = src[src.index("def _sync_osm_to_creator"):]
    seg = seg[:4000]
    assert "bbox" in seg or "hit_test" in seg or "_last_click_on_photo" in seg or "on_photo" in seg, \
        "RED: sync guard suppresses armed clicks without on-photo exception - tracing never reaches creator"
