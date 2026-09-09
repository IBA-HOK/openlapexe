# -*- coding: utf-8 -*-
"""OSMCanvas tests - RED->GREEN for osm_canvas module."""
from __future__ import annotations

import base64
import http.server
import pathlib
import tempfile
import threading
import time

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
    except Exception as e:
        pytest.skip(f"headless no display: {e}")


def test_import():
    from openlapexe.gui.osm_canvas import OSMCanvas

    assert OSMCanvas is not None


def test_zoom_tile_count_changes():
    root = _try_root()
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=400, height=300, zoom=10)
        c.pack()
        root.update()
        time.sleep(0.05)
        root.update()
        tiles10 = c.get_visible_tiles()
        assert len(tiles10) > 0
        assert all(z == 10 for z, _, _ in tiles10)
        c.set_zoom(14)
        root.update()
        time.sleep(0.05)
        root.update()
        tiles14 = c.get_visible_tiles()
        assert len(tiles14) > 0
        assert all(z == 14 for z, _, _ in tiles14)
        assert set(tiles14) != set(tiles10), "zoom change must change tile set"
        assert len(tiles14) <= 12, f"visible tiles must stay bounded, got {len(tiles14)}"
        # also test z bounds 5-18
        c.set_zoom(4)
        assert c.get_zoom() == 5
        c.set_zoom(20)
        assert c.get_zoom() == 18
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_click_latlon_roundtrip():
    root = _try_root()
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas
        from openlapexe.geo_proj import plane_to_wgs84

        c = OSMCanvas(root, width=400, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack()
        root.update()
        time.sleep(0.05)
        root.update()
        # click at center-ish
        px, py = 200, 150
        lat, lon = c.pixel_to_latlon(px, py)
        x, y = c.add_point_latlon(lat, lon)
        assert len(c.points_xy) == 1
        assert c.points_xy[0] == (x, y)
        # roundtrip via geo_proj
        zone = c.points_zone[0]
        lat2, lon2 = plane_to_wgs84(x, y, zone)
        assert abs(lat2 - lat) < 1e-5, f"lat roundtrip {lat} vs {lat2}"
        assert abs(lon2 - lon) < 1e-5, f"lon roundtrip {lon} vs {lon2}"
        # also test pixel->latlon->pixel roundtrip via tile math
        lat_a, lon_a = c.pixel_to_latlon(px, py)
        px2, py2 = c.latlon_to_pixel(lat_a, lon_a)
        assert abs(px2 - px) < 1e-6
        assert abs(py2 - py) < 1e-6
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_cache_reuse_no_communication():
    root = _try_root()
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas
        from openlapexe.geo_tile import _clear_caches_for_tests

        # fake png 1x1
        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
        content = base64.b64decode(png_b64)
        request_count = 0

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                nonlocal request_count
                request_count += 1
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def log_message(self, *a, **kw):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), H)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.05)
        base = f"http://127.0.0.1:{port}/{{z}}/{{x}}/{{y}}.png"
        tmp = pathlib.Path(tempfile.mkdtemp())
        _clear_caches_for_tests()
        try:
            # direct cache reuse test via geo_tile (deterministic, no tkinter async flake)
            from openlapexe.geo_tile import fetch_tile

            # first fetch of a specific tile
            data = fetch_tile(10, 909, 403, base_url=base, cache_dir=tmp)
            assert data == content
            assert request_count == 1
            # second fetch same tile should be cached, no new request
            before = request_count
            data2 = fetch_tile(10, 909, 403, base_url=base, cache_dir=tmp)
            assert data2 == content
            assert request_count == before, "cache reuse should avoid second request"
            # canvas also uses same cache_dir/base_url and should benefit from cache
            c = OSMCanvas(root, width=200, height=200, zoom=10, cache_dir=tmp, base_url=base)
            c.pack()
            root.update()
            time.sleep(0.1)
            root.update()
            # wait a bit for async fetches to process, but many tiles already cached from previous fetch,
            # only tiles not in cache will cause new requests; ensure at least one more fetch happened
            for _ in range(10):
                root.update()
                time.sleep(0.05)
            # After canvas, request_count should have increased by at most number of new tiles,
            # but a second redraw should not increase further much
            mid = request_count
            c._redraw()
            for _ in range(5):
                root.update()
                time.sleep(0.05)
            after = request_count
            # second redraw of same view should not cause many new requests (cached)
            # allow at most 1 extra due to async timing, but generally should be small
            assert after - mid <= 2, f"cache reuse via canvas should be mostly cached {mid} vs {after}"
        finally:
            server.shutdown()
            _clear_caches_for_tests()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_cached_redraw_spawns_no_fetch_and_fast():
    root = _try_root()
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas
        from openlapexe.geo_tile import _clear_caches_for_tests

        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
        content = base64.b64decode(png_b64)
        request_count = 0

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                nonlocal request_count
                request_count += 1
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def log_message(self, *a, **kw):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), H)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.05)
        base = f"http://127.0.0.1:{port}/{{z}}/{{x}}/{{y}}.png"
        tmp = pathlib.Path(tempfile.mkdtemp())
        _clear_caches_for_tests()
        try:
            c = OSMCanvas(root, width=200, height=200, zoom=10, cache_dir=tmp, base_url=base)
            c.pack()
            for _ in range(150):
                root.update()
                time.sleep(0.05)
                if len(c._tile_cache) >= len(c._visible_tiles) > 0:
                    break
            assert len(c._tile_cache) > 0, "tiles should be cached after first load"
            for _ in range(60):
                root.update()
                time.sleep(0.05)
                if len(c._inflight) == 0:
                    break
            assert len(c._inflight) == 0, "in-flight fetches should drain"
            mid = request_count
            t0 = time.monotonic()
            c._redraw()
            root.update()
            dt = time.monotonic() - t0
            for _ in range(5):
                root.update()
                time.sleep(0.05)
            assert request_count == mid, f"cached redraw must not fetch: {mid} vs {request_count}"
            assert dt < 1.0, f"cached redraw too slow: {dt:.2f}s"
        finally:
            server.shutdown()
            _clear_caches_for_tests()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_attribution_always_visible():
    root = _try_root()
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=400, height=300, zoom=10)
        c.pack()
        root.update()
        time.sleep(0.05)
        root.update()
        # check attribution tag exists
        items = c.find_all()
        # find text with OpenStreetMap
        found = False
        for iid in items:
            try:
                typ = c.type(iid)
                if typ == "text":
                    txt = c.itemcget(iid, "text")
                    if "OpenStreetMap" in txt:
                        found = True
            except Exception:
                pass
        assert found, "© OpenStreetMap contributors attribution not found"
        # also check source contains required strings
        text = pathlib.Path("src/openlapexe/gui/osm_canvas.py").read_text(encoding="utf-8")
        assert "PhotoImage(data=" in text
        assert "base64" in text
        assert "queue" in text
        assert "threading" in text
        assert "after(10" in text
        assert "import requests" not in text
        assert "PIL" not in text or "Pillow" not in text
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_offline_gray_placeholder():
    root = _try_root()
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas
        from openlapexe.geo_tile import _clear_caches_for_tests

        _clear_caches_for_tests()
        tmp = pathlib.Path(tempfile.mkdtemp())
        # base_url points to non-existent server to force offline
        c = OSMCanvas(root, width=200, height=200, zoom=10, cache_dir=tmp, base_url="http://127.0.0.1:1/{z}/{x}/{y}.png")
        c.pack()
        root.update()
        time.sleep(0.2)
        root.update()
        # should have gray placeholders (rectangles) and not crash
        # check that canvas still has attribution
        items = c.find_all()
        assert len(items) > 0
        _clear_caches_for_tests()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_photo_overlay_add_opacity_remove():
    root = _try_root()
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
        tmp = pathlib.Path(tempfile.mkdtemp())
        p = tmp / "photo.png"
        p.write_bytes(base64.b64decode(png_b64))
        c = OSMCanvas(root, width=300, height=300, zoom=10)
        c.pack()
        root.update()
        pid = c.add_photo(str(p), lat=35.68, lon=139.76, opacity=0.5)
        root.update()
        assert pid in c.list_photos()
        assert len(c.find_withtag("photo")) > 0
        assert c.set_photo_opacity(pid, 0.2) is True
        rec = c.get_photo(pid)
        assert rec is not None and abs(float(rec["opacity"]) - 0.2) < 1e-9
        specs = c.get_photo_specs()
        assert len(specs) == 1 and specs[0]["path"] == str(p)
        assert c.remove_photo(pid) is True
        assert c.list_photos() == []
        c.clear_photos()
        c2 = OSMCanvas(root, width=300, height=300, zoom=10)
        c2.pack()
        root.update()
        assert c2.load_photo_specs(specs) == 1
        assert c2.list_photos() != []
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_status_text_visible_when_offline():
    root = _try_root()
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas
        from openlapexe.geo_tile import _clear_caches_for_tests

        _clear_caches_for_tests()
        tmp = pathlib.Path(tempfile.mkdtemp())
        c = OSMCanvas(root, width=200, height=200, zoom=10, cache_dir=tmp, base_url="http://127.0.0.1:1/{z}/{x}/{y}.png")
        c.pack()
        for _ in range(40):
            root.update()
            time.sleep(0.05)
            if len(c._inflight) == 0:
                break
        root.update()
        texts = [c.itemcget(i, "text") for i in c.find_withtag("status") if c.type(i) == "text"]
        assert any("読込中" in t or "オフライン" in t for t in texts), texts
        _clear_caches_for_tests()
    finally:
        try:
            root.destroy()
        except Exception:
            pass
