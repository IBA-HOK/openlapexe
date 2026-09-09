# -*- coding: utf-8 -*-
"""bench_cold_tiles — ローカルHTTPスタブ + tmp cache でコールド6タイル vs ウォーム計測.

Spec: cold 6 tiles via local HTTP stub + tmp cache dir, warm = cached, display `cold X.XXs` (~2.5s current).
Uses MIN_INTERVAL throttle (0.5s) sequentially so cold ~2.5s (5 gaps *0.5).
Warm should be near-instant (cached, no network).
"""
from __future__ import annotations

import base64
import http.server
import pathlib
import tempfile
import threading
import time

# 1x1 PNG stub (valid image)
PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
PNG_BYTES = base64.b64decode(PNG_B64)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # small artificial serve delay to mimic network (10ms)
        time.sleep(0.01)
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(PNG_BYTES)))
        self.end_headers()
        self.wfile.write(PNG_BYTES)

    def log_message(self, *a, **kw):
        pass


def bench() -> None:
    import sys

    # Ensure src on path
    root = pathlib.Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from openlapexe.geo_tile import fetch_tile, _clear_caches_for_tests, MIN_INTERVAL

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.05)

    base = f"http://127.0.0.1:{port}/{{z}}/{{x}}/{{y}}.png"
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="bench_tiles_"))
    _clear_caches_for_tests()

    # 6 distinct tiles at zoom 12 around Tokyo (avoid overlap)
    tiles = [(12, 909, 403), (12, 910, 403), (12, 909, 404), (12, 910, 404), (12, 911, 403), (12, 911, 404)]

    # Cold: no cache, sequential fetches (throttle applies)
    t0 = time.monotonic()
    for z, x, y in tiles:
        try:
            fetch_tile(z, x, y, base_url=base, cache_dir=tmp)
        except Exception as e:
            print(f"cold fetch failed {z}/{x}/{y}: {e}")
    cold_dt = time.monotonic() - t0

    # Warm: same 6 should be cached (LRU + file cache)
    t1 = time.monotonic()
    for z, x, y in tiles:
        try:
            fetch_tile(z, x, y, base_url=base, cache_dir=tmp)
        except Exception as e:
            print(f"warm fetch failed {z}/{x}/{y}: {e}")
    warm_dt = time.monotonic() - t1

    server.shutdown()
    _clear_caches_for_tests()

    # Clean tmp (best effort)
    try:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        pass

    # Expected: cold ~2.5s with MIN_INTERVAL=0.5 (5 intervals) + serve delay.
    # With MIN_INTERVAL=0.1, cold would be ~0.5s.
    print(f"cold {cold_dt:.2f}s")
    print(f"warm {warm_dt:.2f}s")
    print(f"MIN_INTERVAL={MIN_INTERVAL} (cold expected ~{(len(tiles)-1)*MIN_INTERVAL:.2f}s + overhead)")
    # Also indicate whether cold matches ~2.5s regime
    if 2.0 <= cold_dt <= 3.5:
        print("cold range: ~2.5s (current 0.5s throttle) — OK")
    elif 0.3 <= cold_dt <= 1.0:
        print("cold range: ~0.5s (0.1s throttle after fix) — OK")
    else:
        print(f"cold range: unexpected {cold_dt:.2f}s")


if __name__ == "__main__":
    bench()
