# -*- coding: utf-8 -*-
"""tests/test_photo_mode_style.py - RED for mode colors (S-photo-place-wp).

Requirements:
- get_mode() -> place|select|normal
- canvas border color per mode (place=orange #ff8c00 width 3, select=#1f4b99, normal default)
- banner text item showing mode
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
    p = tmp / "photo_mode_style.png"
    p.write_bytes(base64.b64decode(png_b64))
    return p


def test_get_mode_transitions():
    from openlapexe.gui import osm_canvas as mod

    root = _try_root()
    if root is None:
        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        assert "def get_mode" in src, "RED: get_mode missing"
        assert "def _update_mode_style" in src, "RED: _update_mode_style missing"
        assert 'place' in src and 'select' in src and 'normal' in src, "RED: mode strings missing"
        return
    try:
        c = mod.OSMCanvas(root, width=300, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack()
        # initial normal (no photos)
        assert c.get_mode() == "normal", f"RED: initial mode not normal got {c.get_mode()}"
        # add photo -> auto-select -> select mode
        pid = c.add_photo(str(_tmp_png()), lat=35.68, lon=139.76, opacity=0.9)
        # after add, should be select
        assert c.get_mode() == "select", f"RED: after add_photo expected select got {c.get_mode()}"
        # arm -> place overrides select
        assert c.arm_photo_place(pid) is True
        assert c.get_mode() == "place", f"RED: after arm expected place got {c.get_mode()}"
        # disarm -> back to select (still selected)
        c.disarm_photo_place()
        assert c.get_mode() == "select", f"RED: after disarm expected select got {c.get_mode()}"
        # clear -> normal
        c.clear_photos()
        assert c.get_mode() == "normal", f"RED: after clear expected normal got {c.get_mode()}"
    finally:
        root.destroy()


def test_highlight_color_and_banner():
    from openlapexe.gui import osm_canvas as mod

    root = _try_root()
    if root is None:
        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        assert "highlightbackground" in src, "RED: highlightbackground not configured"
        assert "highlightthickness" in src, "RED: highlightthickness not configured"
        assert "#ff8c00" in src, "RED: place orange #ff8c00 missing"
        assert "#1f4b99" in src, "RED: select #1f4b99 missing"
        assert "mode_banner" in src or "mode" in src.lower(), "RED: banner tag missing"
        return
    try:
        c = mod.OSMCanvas(root, width=300, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack()
        # helper to check highlight
        def _check(mode, exp_bg, exp_thick=None):
            c._update_mode_style()
            try:
                bg = c.cget("highlightbackground")
            except Exception:
                bg = None
            try:
                th = int(c.cget("highlightthickness"))
            except Exception:
                th = None
            assert bg == exp_bg, f"RED: mode {mode} highlightbackground {bg} != {exp_bg}"
            if exp_thick is not None:
                assert th == exp_thick, f"RED: mode {mode} thickness {th} != {exp_thick}"
            # banner
            try:
                items = c.find_withtag("mode_banner")
            except Exception:
                items = ()
            assert len(items) > 0, f"RED: mode {mode} banner missing"
            try:
                txt = c.itemcget(items[0], "text")
            except Exception:
                txt = ""
            assert txt == mode, f"RED: banner text {txt!r} != {mode!r}"

        # normal
        c._selected_photo_id = None
        c._placing_photo_id = None
        c._update_mode_style()
        assert c.get_mode() == "normal"
        _check("normal", "#ccc", 1)
        # select
        pid = c.add_photo(str(_tmp_png()), lat=35.68, lon=139.76, opacity=0.9)
        # add_photo already calls update, mode select
        assert c.get_mode() == "select"
        _check("select", "#1f4b99")
        # place
        c.arm_photo_place(pid)
        assert c.get_mode() == "place"
        _check("place", "#ff8c00", 3)
        # press/release should keep updated (headless-safe try/except)
        class _Ev:
            def __init__(self, x, y, state=0, num=1):
                self.x = int(x); self.y = int(y); self.state = int(state); self.num = int(num)
        # simulate press while armed
        c._on_press(_Ev(10, 10))
        assert c.get_mode() == "place"
        c._update_mode_style()
        assert c.cget("highlightbackground") == "#ff8c00"
        # disarm
        c.disarm_photo_place()
        c._on_release(_Ev(10, 10))
        # after release, mode should be select or normal depending on selection
        assert c.get_mode() in ("select", "normal")
    finally:
        root.destroy()
