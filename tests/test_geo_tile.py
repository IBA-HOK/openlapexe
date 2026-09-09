# -*- coding: utf-8 -*-
"""Geo tile tests - RED->GREEN for geo_tile module."""
from __future__ import annotations

import http.server
import pathlib
import tempfile
import threading
import time

import pytest


def test_latlon_to_tile_tokyo_known():
    from openlapexe.geo_tile import latlon_to_tile

    x, y = latlon_to_tile(35.68, 139.76, 10)
    assert (x, y) == (909, 403), f"expected (909,403) got {(x,y)}"


def test_latlon_to_tile_hachiko_z18_wiki():
    from openlapexe.geo_tile import latlon_to_tile

    x, y = latlon_to_tile(35.6590699, 139.7006793, 18)
    assert (x, y) == (232798, 103246), f"expected (232798,103246) got {(x,y)}"


def test_roundtrip_error_lt_1e6():
    from openlapexe.geo_tile import latlon_to_tile, tile_to_latlon

    # tile NW corner roundtrip should be <1e-6
    x, y, z = 909, 403, 10
    lat, lon = tile_to_latlon(x, y, z)
    x2, y2 = latlon_to_tile(lat, lon, z)
    assert (x, y) == (x2, y2)
    lat2, lon2 = tile_to_latlon(x2, y2, z)
    assert abs(lat - lat2) < 1e-6
    assert abs(lon - lon2) < 1e-6


def test_tile_bounds_contains():
    from openlapexe.geo_tile import latlon_to_tile, tile_bounds

    x, y = latlon_to_tile(35.68, 139.76, 10)
    lat_s, lon_w, lat_n, lon_e = tile_bounds(x, y, 10)
    # south < north, west < east
    assert lat_s < lat_n
    assert lon_w < lon_e
    # original point inside bounds
    assert lat_s <= 35.68 <= lat_n
    assert lon_w <= 139.76 <= lon_e


def test_get_tile_url_format():
    from openlapexe.geo_tile import get_tile_url

    url = get_tile_url(10, 909, 403)
    assert url == "https://tile.openstreetmap.org/10/909/403.png"
    # swapped order also works
    url2 = get_tile_url(909, 403, 10)
    assert url2 == "https://tile.openstreetmap.org/10/909/403.png"


def test_cache_reuse_no_communication_and_user_agent():
    from openlapexe.geo_tile import fetch_tile, _clear_caches_for_tests

    content = b"\x89PNG\r\n\x1a\nfake-tile"
    request_count = 0
    last_ua = None

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal request_count, last_ua
            request_count += 1
            last_ua = self.headers.get("User-Agent")
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
        data1 = fetch_tile(10, 909, 403, base_url=base, cache_dir=tmp, timeout=2)
        assert data1 == content
        assert last_ua == "OpenLAPexe/0.1"
        assert request_count == 1
        # second fetch should be cached, no network
        last_ua = None
        data2 = fetch_tile(10, 909, 403, base_url=base, cache_dir=tmp, timeout=2)
        assert data2 == content
        assert request_count == 1, "cache reuse should avoid second request"
    finally:
        server.shutdown()
        _clear_caches_for_tests()


def test_attribution_string():
    from openlapexe.geo_tile import ATTRIBUTION

    assert "OpenStreetMap" in ATTRIBUTION


def test_no_requests_import():
    import pathlib as _p

    text = _p.Path("src/openlapexe/geo_tile.py").read_text(encoding="utf-8")
    # ensure no import requests
    assert "import requests" not in text
    # ensure urllib.request is used
    assert "urllib.request" in text


def test_lru_and_throttle():
    from openlapexe.geo_tile import _clear_caches_for_tests, fetch_tile
    import http.server
    import threading
    import tempfile
    import pathlib
    import time

    content = b"png"
    request_count = 0

    class H2(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal request_count
            request_count += 1
            self.send_response(200)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *a, **kw):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), H2)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.05)
    base = f"http://127.0.0.1:{port}/{{z}}/{{x}}/{{y}}.png"
    tmp = pathlib.Path(tempfile.mkdtemp())
    _clear_caches_for_tests()
    try:
        t0 = time.monotonic()
        fetch_tile(10, 909, 403, base_url=base, cache_dir=tmp, timeout=2)
        fetch_tile(10, 910, 403, base_url=base, cache_dir=tmp, timeout=2)
        dt = time.monotonic() - t0
        # MIN_INTERVAL 0.5→0.1 に変更 (T2): OSM Tile Usage Policy 遵守は維持しつつ並列2でのスループット向上のため 0.1 に短縮。旧閾値 0.45 は 0.5 間隔前提のため現行 0.1 では dt≈0.1。閾値を 0.09 に更新して新 throttle を検証。
        assert dt >= 0.09, f"throttle 10req/s (MIN_INTERVAL=0.1) not enforced dt={dt}"
    finally:
        server.shutdown()
        _clear_caches_for_tests()
