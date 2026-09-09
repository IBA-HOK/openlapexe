# -*- coding: utf-8 -*-
"""tests/test_photo_opacity_alpha.py - RED only for true alpha transparency (S-photo-lock core).

Требования: opacity uses RGBA alpha (map shows through) - не белый бленд.

Tests:
- headless source check asserts 'putalpha'/'RGBA' in osm_canvas.py (PIL path must use RGBA alpha, keep white-blend only in tk fallback)
- functional: load RGBA PNG via _load_photo_image opacity 0.5 -> image mode RGBA + alpha <255

Headless tries Tk, but still asserts API via source inspection (no skip that hides RED).
Do NOT fix src/ - this file must stay RED until implementation uses putalpha RGBA.
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


def _tmp_rgba_png() -> pathlib.Path:
    # Create a small RGBA PNG via PIL if available, else fallback to 1x1 b64
    try:
        from PIL import Image  # type: ignore

        tmp = pathlib.Path(tempfile.mkdtemp())
        p = tmp / "photo_alpha.png"
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
        img.save(str(p), "PNG")
        return p
    except Exception:
        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
        tmp = pathlib.Path(tempfile.mkdtemp())
        p = tmp / "photo_alpha.png"
        p.write_bytes(base64.b64decode(png_b64))
        return p


def test_photo_opacity_uses_rgba_alpha():
    from openlapexe.gui import osm_canvas as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")

    # Headless source checks: PIL path must use RGBA putalpha, not white-blend
    # Should contain putalpha and RGBA, and should NOT have white-blend in PIL branch (only tk fallback may keep _white_blend_tk)
    has_putalpha = "putalpha" in src
    has_rgba = "RGBA" in src
    # Check that _load_photo_image PIL branch uses putalpha/RGBA, not Image.blend with white
    # Isolate _load_photo_image source
    if "def _load_photo_image" in src:
        load_src = src.split("def _load_photo_image")[1].split("\ndef ")[0]
    else:
        load_src = ""
    # PIL branch should have putalpha, tk fallback keeps _white_blend_tk
    # Allow white blend only in fallback (outside PIL try)
    # So we assert putalpha present; if missing -> RED
    if not (has_putalpha and has_rgba):
        pytest.fail("RED: osm_canvas.py PIL path must use RGBA putalpha(int(255*a)) for true alpha (map shows through), not white-blend — missing 'putalpha'/'RGBA'")

    # Ensure PIL branch does not use white blend (Image.blend or white Image.new RGB) for opacity — only tk fallback may use _white_blend_tk
    # If still has "Image.blend" or 'Image.new("RGB"' with white in load_src's PIL try, it's white-blend -> RED
    # We allow _white_blend_tk definition elsewhere, but PIL branch must not blend with white
    if "Image.blend" in load_src and "putalpha" not in load_src:
        pytest.fail("RED: _load_photo_image PIL path still uses Image.blend white-blend instead of RGBA putalpha")
    # Also check _get_cached_photo_image uses putalpha if it handles opacity
    if "def _get_cached_photo_image" in src:
        cache_src = src.split("def _get_cached_photo_image")[1].split("\ndef ")[0]
        if "opacity" in cache_src.lower() and "Image.blend" in cache_src and "putalpha" not in cache_src:
            pytest.fail("RED: _get_cached_photo_image opacity still uses white-blend instead of RGBA putalpha")
    # Additional check: _white_blend_tk should still exist for tk fallback (keep white-blend only there)
    assert "_white_blend_tk" in src, "tk fallback _white_blend_tk should remain for non-PIL path"

    root = _try_root()
    if root is None:
        return
    try:
        # Functional: load RGBA PNG via _load_photo_image opacity 0.5 -> image mode RGBA + alpha <255
        try:
            import PIL.Image as PILImage  # type: ignore
            import PIL.ImageTk as PILImageTk  # type: ignore
        except Exception as e:
            pytest.skip(f"PIL not available: {e}")

        tmp_path = _tmp_rgba_png()
        captured: dict = {}

        orig_PhotoImage = PILImageTk.PhotoImage

        def _capture(img, *args, **kwargs):
            try:
                captured["img"] = img
                captured["mode"] = getattr(img, "mode", None)
                if getattr(img, "mode", None) == "RGBA":
                    try:
                        alpha = img.getchannel("A")
                        captured["alpha_extrema"] = alpha.getextrema()
                        captured["pixel"] = img.getpixel((0, 0))
                    except Exception:
                        pass
            except Exception:
                pass
            return orig_PhotoImage(img, *args, **kwargs)

        import unittest.mock as mock

        with mock.patch.object(PILImageTk, "PhotoImage", side_effect=_capture):
            try:
                from openlapexe.gui.osm_canvas import _load_photo_image

                img_tk, w, h = _load_photo_image(str(tmp_path), opacity=0.5, max_side=1024)
            except Exception as e:
                pytest.fail(f"_load_photo_image failed: {e}")
            assert "mode" in captured, "PIL Image not captured - _load_photo_image may have taken tk fallback (PIL not used)"
            mode = captured.get("mode")
            assert mode == "RGBA", f"RED: PIL path image mode should be RGBA for true alpha, got {mode} (still RGB white-blend)"
            if "alpha_extrema" in captured:
                lo, hi = captured["alpha_extrema"]
                assert hi < 255, f"RED: alpha max should be <255 for opacity 0.5, got extrema {captured['alpha_extrema']}"
                assert hi == int(255 * 0.5) or 120 <= hi <= 135, f"RED: alpha should be int(255*0.5)=127, got {hi}"
            if "pixel" in captured:
                px = captured["pixel"]
                if isinstance(px, (tuple, list)) and len(px) == 4:
                    a = px[3]
                    assert a < 255, f"RED: pixel alpha <255 expected for opacity 0.5, got {px}"
                    assert 120 <= a <= 135, f"RED: pixel alpha should be ~127 for opacity 0.5, got {a} pixel {px}"
    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass
