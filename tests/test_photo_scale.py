# -*- coding: utf-8 -*-
"""tests/test_photo_scale.py - RED only for per-photo scale (S-photo-resize).

3 FAILing tests:
 (a) add_photo then set_photo_scale(pid,2.0) changes w/h and get_photo_specs contains scale==2.0
 (b) get_photo_specs/load_photo_specs roundtrip preserves scale
 (c) shell save/load overlays preserve scale

Current specs only path/lat/lon/opacity, no scale; _draw_photos fixed thumbnail max_side 1024 center anchor.
Success = pytest RED with AttributeError/no-scale messages.

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
    except Exception as e:
        # headless: return None so tests can still assert AttributeError/no-scale via class inspection
        return None


def _tmp_png() -> pathlib.Path:
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = tmp / "photo_scale.png"
    p.write_bytes(base64.b64decode(png_b64))
    return p


def test_a_set_photo_scale_changes_wh_and_specs_contains_scale():
    """(a) add_photo then set_photo_scale(pid,2.0) changes w/h and specs contains scale==2.0"""
    from openlapexe.gui import osm_canvas as mod
    import inspect

    # API existence - must FAIL now (RED) with AttributeError/no-scale
    assert hasattr(mod.OSMCanvas, "set_photo_scale"), "AttributeError: OSMCanvas.set_photo_scale missing (no-scale) - per-photo scale not implemented"
    # Also check signature expects scale param
    sig = inspect.signature(mod.OSMCanvas.set_photo_scale)
    assert "scale" in sig.parameters or len(sig.parameters) >= 3, "no-scale: set_photo_scale signature missing scale param"

    root = _try_root()
    # If headless, we already asserted API missing above (which would have failed);
    # if we are here, API exists (future GREEN) - still need functional check.
    # To keep RED now, also assert specs contain scale even headless via source inspection
    if root is None:
        # fallback source check - current impl has no scale key
        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        # get_photo_specs should emit scale
        assert '"scale"' in src or "'scale'" in src or "scale" in src and "get_photo_specs" in src, "no-scale: get_photo_specs does not emit scale key"
        # _load_photo_image should accept scale? or add_photo should store scale
        assert "def set_photo_scale" in src, "AttributeError: set_photo_scale not defined"
        # w/h scaling check - src should multiply by scale
        assert "scale" in src, "no-scale: scale handling missing in osm_canvas.py"
        pytest.fail("no-scale: headless but scale API not functional - expected w/h *2 and scale==2.0")
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=300, height=300, zoom=10)
        c.pack()
        root.update()
        p = _tmp_png()
        pid = c.add_photo(str(p), lat=35.68, lon=139.76, opacity=0.5)
        rec0 = c.get_photo(pid)
        assert rec0 is not None, "add_photo failed"
        w0, h0 = int(rec0["w"]), int(rec0["h"])
        # try scale 2.0
        ok = c.set_photo_scale(pid, 2.0)
        assert ok is True, "set_photo_scale should return True"
        rec1 = c.get_photo(pid)
        assert rec1 is not None
        w1, h1 = int(rec1["w"]), int(rec1["h"])
        # w/h should be ~2x (allow rounding)
        assert w1 == int(w0 * 2.0) or abs(w1 - w0 * 2.0) < 2, f"no-scale: w not scaled {w0}->{w1} expected *2.0"
        assert h1 == int(h0 * 2.0) or abs(h1 - h0 * 2.0) < 2, f"no-scale: h not scaled {h0}->{h1} expected *2.0"
        specs = c.get_photo_specs()
        assert len(specs) == 1, f"specs len {specs}"
        assert "scale" in specs[0], f"no-scale: scale key missing in get_photo_specs {specs[0]}"
        assert float(specs[0]["scale"]) == 2.0, f"scale !=2.0 got {specs[0].get('scale')}"
    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass


def test_b_photo_specs_roundtrip_preserves_scale():
    """(b) get_photo_specs/load_photo_specs roundtrip preserves scale"""
    from openlapexe.gui import osm_canvas as mod
    import inspect

    assert hasattr(mod.OSMCanvas, "set_photo_scale"), "AttributeError: set_photo_scale missing - roundtrip cannot preserve scale"
    assert hasattr(mod.OSMCanvas, "get_photo_specs"), "AttributeError: get_photo_specs missing"
    assert hasattr(mod.OSMCanvas, "load_photo_specs"), "AttributeError: load_photo_specs missing"

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    # load should handle scale key
    assert "scale" in src, "no-scale: load_photo_specs does not handle scale"

    root = _try_root()
    if root is None:
        # headless: check source contains scale preservation logic
        assert "scale" in src and "load_photo_specs" in src, "no-scale: load_photo_specs missing scale handling"
        # Force RED now by inspecting current impl: add_photo sig and get_photo_specs
        lines = src
        # current get_photo_specs only emits path/lat/lon/opacity - no scale -> fail
        if '"scale"' not in lines and "'scale'" not in lines:
            pytest.fail("AttributeError/no-scale: get_photo_specs/load_photo_specs roundtrip missing scale key - current specs only path/lat/lon/opacity")
        pytest.fail("no-scale: headless roundtrip scale not preserved")
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=300, height=300, zoom=10)
        c.pack()
        root.update()
        p = _tmp_png()
        pid = c.add_photo(str(p), lat=35.681, lon=139.767, opacity=0.6)
        c.set_photo_scale(pid, 1.5)
        specs = c.get_photo_specs()
        assert any("scale" in s for s in specs), f"no-scale: specs missing scale {specs}"
        assert any(abs(float(s.get("scale", 0)) - 1.5) < 1e-9 for s in specs), f"scale 1.5 not in specs {specs}"
        # roundtrip via new canvas
        root2 = root
        # clear and reload on fresh canvas to test load path
        c2 = OSMCanvas(root2, width=300, height=300, zoom=10)
        c2.pack()
        root.update()
        n = c2.load_photo_specs(specs)
        assert n == 1, f"load_photo_specs returned {n} expected 1"
        specs2 = c2.get_photo_specs()
        assert len(specs2) == 1
        assert "scale" in specs2[0], f"no-scale: roundtrip lost scale key {specs2[0]}"
        assert abs(float(specs2[0]["scale"]) - 1.5) < 1e-9, f"roundtrip scale mismatch {specs2[0].get('scale')} !=1.5"
        # w/h should also be preserved scaled
        rec = c2.get_photo(c2.list_photos()[0])
        assert rec is not None
        rec_orig = c.get_photo(pid)
        assert int(rec["w"]) == int(rec_orig["w"]) and int(rec["h"]) == int(rec_orig["h"]), f"no-scale: w/h not preserved roundtrip {rec} vs {rec_orig}"
    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass


def test_c_shell_save_load_overlays_preserve_scale():
    """(c) shell save/load overlays preserve scale"""
    from openlapexe.gui import osm_canvas as mod
    import pathlib as _pl

    # Check OSMCanvas API first (RED if missing)
    assert hasattr(mod.OSMCanvas, "set_photo_scale"), "AttributeError: OSMCanvas.set_photo_scale missing - shell overlays cannot preserve scale"
    src_canvas = _pl.Path(mod.__file__).read_text(encoding="utf-8")
    assert "scale" in src_canvas, "no-scale: osm_canvas missing scale - shell overlay preservation will fail"

    # Check shell.py handlers for scale preservation (RED now)
    shell_path = _pl.Path("src/openlapexe/gui/shell.py")
    if not shell_path.exists():
        shell_path = _pl.Path(mod.__file__).parent / "shell.py"
    shell_src = shell_path.read_text(encoding="utf-8") if shell_path.exists() else ""
    # shell should propagate scale via get_photo_specs -> meta.overlays -> load_photo_specs
    # Current shell does overlays = get_photo_specs() but specs lack scale, so this asserts scale handling
    assert "scale" in shell_src.lower() and "overlays" in shell_src.lower(), "no-scale: shell.py photo handlers missing scale preservation for overlays (save/load)"
    # Also check load path uses scale
    assert "load_photo_specs" in shell_src, "AttributeError: shell load_photo_specs handler missing"
    # Check that shell's _on_save_track includes scale via get_photo_specs that contains scale
    # Force failure now because shell does not explicitly handle scale yet
    if "scale" not in shell_src:
        pytest.fail("AttributeError/no-scale: shell.py overlays do not preserve scale - missing scale key in save/load")

    root = _try_root()
    if root is None:
        pytest.fail("no-scale: shell overlays scale preservation not implemented - AttributeError set_photo_scale missing, overlays lack scale")

    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        # simulate shell save/load flow without full App2 (which needs display)
        c = OSMCanvas(root, width=300, height=300, zoom=10)
        c.pack()
        root.update()
        p = _tmp_png()
        pid = c.add_photo(str(p), lat=35.68, lon=139.76, opacity=0.5)
        c.set_photo_scale(pid, 2.5)
        specs = c.get_photo_specs()
        assert "scale" in specs[0] and float(specs[0]["scale"]) == 2.5, f"no-scale: specs before shell save missing scale {specs}"

        # mimic shell _on_save_track: track.meta.overlays = specs
        # mimic shell _on_load_track: load_photo_specs(overlays)
        # Use Track if available, else direct dict roundtrip
        try:
            from openlapexe.track import Track
            import tempfile as _tf
            # create dummy track via from_candidates minimal
            meta_overlays = specs
            # Use direct canvas reload to simulate shell load
            c2 = OSMCanvas(root, width=300, height=300, zoom=10)
            c2.pack()
            root.update()
            n = c2.load_photo_specs(meta_overlays)
            assert n == 1
            specs2 = c2.get_photo_specs()
            assert "scale" in specs2[0], f"no-scale: shell load lost scale {specs2}"
            assert abs(float(specs2[0]["scale"]) - 2.5) < 1e-9, f"shell overlay scale mismatch {specs2[0].get('scale')} !=2.5"
        except Exception as e:
            # If Track fails, at least canvas roundtrip must preserve
            c2 = OSMCanvas(root, width=300, height=300, zoom=10)
            c2.pack()
            root.update()
            n = c2.load_photo_specs(specs)
            assert n == 1
            specs2 = c2.get_photo_specs()
            assert "scale" in specs2[0], f"no-scale: shell overlay roundtrip lost scale: {e} {specs2}"

        # Also verify shell.py actually writes overlays with scale (inspect _on_save_track/_on_load_track)
        assert "overlays" in shell_src and "scale" in shell_src, "no-scale: shell save/load overlays missing scale propagation"

    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass
