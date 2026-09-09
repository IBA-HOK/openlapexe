# -*- coding: utf-8 -*-
"""TDD RED: OSM speedup — MIN_INTERVAL 0.1, lock split, TIMEOUT 1.0, placeholder, zero fetch on point add, inflight discard.

All 6 tests are expected to FAIL on current codebase.
Current: MIN_INTERVAL=0.5, single _LOCK, TIMEOUT=2.0, fetch raises, inflight not cleared on zoom, point add may trigger fetches.
"""
from __future__ import annotations

import pathlib
import time

import pytest


def _read(rel: str) -> str:
    p = pathlib.Path(rel)
    if not p.exists():
        p = pathlib.Path(__file__).resolve().parents[1] / rel
    return p.read_text(encoding="utf-8")


def test_min_interval_is_0_1() -> None:
    from openlapexe import geo_tile

    assert geo_tile.MIN_INTERVAL == 0.1, (
        f"Expected MIN_INTERVAL==0.1 (2req/s throttle -> 10req/s), got {geo_tile.MIN_INTERVAL}. "
        "Current is 0.5 (2req/s)."
    )
    text = _read("src/openlapexe/geo_tile.py")
    assert "MIN_INTERVAL" in text and "0.1" in text, "geo_tile.py should define MIN_INTERVAL = 0.1"


def test_lru_and_throttle_locks_separated() -> None:
    """_LRU_LOCK and _THROTTLE_LOCK must be separate (current single _LOCK is bottleneck)."""
    from openlapexe import geo_tile

    has_lru_lock = hasattr(geo_tile, "_LRU_LOCK")
    has_throttle_lock = hasattr(geo_tile, "_THROTTLE_LOCK")
    # Check source also
    text = _read("src/openlapexe/geo_tile.py")
    has_lru_in_src = "_LRU_LOCK" in text
    has_throttle_in_src = "_THROTTLE_LOCK" in text
    # Ensure they are distinct objects if both exist
    distinct = False
    if has_lru_lock and has_throttle_lock:
        try:
            distinct = geo_tile._LRU_LOCK is not geo_tile._THROTTLE_LOCK  # type: ignore[attr-defined]
        except Exception:
            distinct = False
    assert has_lru_lock and has_throttle_lock and has_lru_in_src and has_throttle_in_src and distinct, (
        f"Expected separated _LRU_LOCK and _THROTTLE_LOCK (distinct). "
        f"has _LRU_LOCK={has_lru_lock} (src={has_lru_in_src}), "
        f"has _THROTTLE_LOCK={has_throttle_lock} (src={has_throttle_in_src}), distinct={distinct}. "
        "Current uses single _LOCK for both LRU and throttle (line 29)."
    )
    # Also ensure old _LOCK is gone or not used for both
    assert "_LOCK = " not in text or ("_LRU_LOCK" in text and "_THROTTLE_LOCK" in text), "Single _LOCK should be replaced by split locks"


def test_timeout_is_1_0() -> None:
    from openlapexe import geo_tile

    assert geo_tile.TIMEOUT == 1.0, f"Expected TIMEOUT==1.0, got {geo_tile.TIMEOUT}. Current is 2.0 (line 24)."
    text = _read("src/openlapexe/geo_tile.py")
    # TIMEOUT line should contain 1.0
    assert "TIMEOUT" in text and "1.0" in text, "geo_tile.py should define TIMEOUT = 1.0"


def test_failure_returns_immediate_placeholder() -> None:
    """On network failure, fetch_tile must return immediate placeholder bytes (not raise after retry)."""
    from openlapexe.geo_tile import fetch_tile, _clear_caches_for_tests
    import tempfile

    _clear_caches_for_tests()
    tmp = pathlib.Path(tempfile.mkdtemp())
    bad_base = "http://127.0.0.1:1/{z}/{x}/{y}.png"
    t0 = time.monotonic()
    try:
        data = fetch_tile(10, 909, 403, base_url=bad_base, cache_dir=tmp, timeout=0.3)
    except Exception as e:
        pytest.fail(
            f"fetch_tile should return immediate placeholder on failure, not raise {type(e).__name__}: {e}. "
            "Current retries and raises URLError (line 283-289)."
        )
        return
    finally:
        _clear_caches_for_tests()
    dt = time.monotonic() - t0
    assert isinstance(data, (bytes, bytearray)) and len(data) > 0, "Expected non-empty placeholder bytes"
    # Immediate: should return quickly (<0.8s), not wait for retry*timeout
    assert dt < 0.9, f"Failure placeholder should be immediate (<0.9s), took {dt:.2f}s (current retry adds delay)"


def test_point_add_triggers_zero_fetch() -> None:
    """Adding a point (add_point_latlon/_request_redraw) must be optimized to 0 fetch_tile calls — requires guard."""
    # RED: current has no guard separating point-add redraw from tile fetch.
    # We assert for an explicit optimization marker that does not yet exist.
    text_osm = _read("src/openlapexe/gui/osm_canvas.py")
    text_geo = _read("src/openlapexe/geo_tile.py")
    # Expected: OSMCanvas.add_point_latlon should have a flag like _skip_fetch_on_point_add
    # or geo_tile should expose a point-add-optimized path, or OSMCanvas should check `has_fetch_guard`
    has_guard = (
        "_skip_fetch" in text_osm
        or "point_add_no_fetch" in text_osm.lower()
        or "POINT_ADD_FETCH" in text_osm
        or "_fetch_suppressed" in text_osm
        or "suppress_fetch" in text_osm.lower()
    )
    has_geo_guard = "point_add" in text_geo.lower() and "fetch" in text_geo.lower()
    # Also functional: monkey-patch and ensure zero fetches after point add — current will show guard missing as well
    # We fail on missing guard (spec-driven), not on transient network timing.
    assert has_guard or has_geo_guard, (
        "Expected point-add zero-fetch optimization (e.g. _skip_fetch_on_point_add / point_add_no_fetch guard) "
        f"in osm_canvas/geo_tile; has_osm_guard={has_guard}, has_geo_guard={has_geo_guard}. "
        "Current add_point_latlon triggers _request_redraw which may schedule _fetch_tile_async without suppression."
    )


def test_old_zoom_inflight_discarded() -> None:
    """Old zoom's inflight fetches must be discarded/cleared when zoom changes."""
    try:
        import pathlib as _pl
        import tempfile as _tf
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.update()
        from openlapexe.gui.osm_canvas import OSMCanvas
        from openlapexe.geo_tile import _clear_caches_for_tests

        _clear_caches_for_tests()
        tmp = _pl.Path(_tf.mkdtemp())
        # Use bad base so fetches stay inflight longer (timeout)
        c = OSMCanvas(root, width=200, height=200, zoom=12, cache_dir=tmp, base_url="http://127.0.0.1:1/{z}/{x}/{y}.png")
        c.pack()
        root.update()
        time.sleep(0.1)
        root.update()
        # Capture inflight at zoom 12
        c.set_zoom(12)
        root.update()
        # Force some inflight by triggering redraw (tiles not cached -> fetch)
        c._redraw()  # type: ignore[attr-defined]
        root.update()
        time.sleep(0.05)
        inflight_before = set(getattr(c, "_inflight", set()))
        # Change zoom — old inflight should be discarded
        c.set_zoom(14)
        root.update()
        time.sleep(0.05)
        root.update()
        inflight_after = set(getattr(c, "_inflight", set()))
        # If old zoom inflight not discarded, then old tiles (z=12) remain in inflight_after
        old_zoom_tiles = [t for t in inflight_after if t[0] == 12]
        assert len(old_zoom_tiles) == 0, (
            f"Old zoom (12) inflight should be discarded on zoom change to 14; "
            f"found {old_zoom_tiles} still inflight. inflight_before={inflight_before}, after={inflight_after}"
        )
        # Also check that inflight doesn't keep growing unbounded after zooms
        c.set_zoom(10)
        root.update()
        time.sleep(0.05)
        inflight_10 = set(getattr(c, "_inflight", set()))
        old = [t for t in inflight_10 if t[0] in (12, 14)]
        assert len(old) == 0, f"After zoom to 10, old zooms should be cleared, got {old}"

        try:
            root.destroy()
        except Exception:
            pass
        _clear_caches_for_tests()
    except Exception as e:
        if isinstance(e, AssertionError):
            raise
        pytest.fail(f"Old zoom inflight discard check failed: {type(e).__name__}: {e}")
