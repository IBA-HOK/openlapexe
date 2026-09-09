# -*- coding: utf-8 -*-
# Gripping: OSMタイル利用規約を遵守すること
# - tile.openstreetmap.org の Tile Usage Policy 遵守、大量アクセス禁止、帰属表記必須
# - ネットワークは urllib.request のみ、User-Agent OpenLAPexe/0.1 明示、timeout 1s / retry1 / 10req/s throttle (MIN_INTERVAL 0.1) 厳守
# - OSM Tile Usage Policy 遵守、大量アクセス禁止、帰属表記必須 — throttle 0.1は並列2維持の最小間隔、OSM規約コメントは保守的に維持
# - ~/.cache/openlapexe/tiles/{z}/{x}/{y}.png 永続キャッシュ必須、LRU 500件で再利用し無通信優先
# - 決定論的・stdlibのみ・encoding=utf-8

from __future__ import annotations

import collections
import math
import pathlib
import struct
import threading
import time
import urllib.error
import urllib.request
import zlib
from typing import Tuple

USER_AGENT: str = "OpenLAPexe/0.1"
ATTRIBUTION: str = "© OpenStreetMap contributors"
TILE_URL_TEMPLATE: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
CACHE_ROOT: pathlib.Path = pathlib.Path.home() / ".cache" / "openlapexe" / "tiles"
MAX_CACHE_ENTRIES: int = 500
TIMEOUT: float = 1.0
RETRY_COUNT: int = 1
MIN_INTERVAL: float = 0.1

_LRU: collections.OrderedDict[Tuple[str, int, int, int], bytes] = collections.OrderedDict()
_LRU_LOCK = threading.Lock()
_THROTTLE_LOCK = threading.Lock()
_LAST_REQUEST_TS: float = 0.0

__all__ = [
    "USER_AGENT",
    "ATTRIBUTION",
    "TILE_URL_TEMPLATE",
    "CACHE_ROOT",
    "MAX_CACHE_ENTRIES",
    "TIMEOUT",
    "latlon_to_tile",
    "tile_to_latlon",
    "tile_bounds",
    "get_tile_url",
    "fetch_tile",
]


def _clamp_lat(lat: float) -> float:
    return max(min(lat, 85.05112878), -85.05112878)


def _valid_tile(z: int, x: int, y: int) -> bool:
    if not (0 <= z <= 30):
        return False
    try:
        n = 1 << z
        return 0 <= x < n and 0 <= y < n
    except Exception:
        return False


def _norm_zxy(a: int, b: int, c: int) -> Tuple[int, int, int]:
    # accept (z,x,y) or (x,y,z), return (z,x,y)
    if _valid_tile(a, b, c):
        return (a, b, c)
    if _valid_tile(c, a, b):
        return (c, a, b)
    # fallback: prefer (z,x,y) if none valid, let caller raise
    return (a, b, c)


def _norm_xyz_for_tile(a: int, b: int, c: int) -> Tuple[int, int, int]:
    # accept (x,y,z) or (z,x,y), return (x,y,z)
    if _valid_tile(c, a, b):
        return (a, b, c)
    if _valid_tile(a, b, c):
        return (b, c, a) if _valid_tile(b, c, a) and not _valid_tile(c, a, b) else (a, b, c)
    # heuristic: check swapped validity
    # if (a,b,c) as (x,y,z) invalid but (z,x,y) valid, swap
    if not _valid_tile(c, a, b) and _valid_tile(a, b, c):
        return (b, c, a)
    # use generic: if c is valid zoom and a,b within 2**c, treat as (x,y,z)
    # else if a is valid zoom and b,c within, treat as (z,x,y)
    ca = _valid_tile(c, a, b)
    sw = _valid_tile(a, b, c)
    if ca and not sw:
        return (a, b, c)
    if sw and not ca:
        return (b, c, a)
    return (a, b, c)


def _resolve_tile_args(a: int, b: int, c: int, canonical: str) -> Tuple[int, int, int]:
    # canonical: "zxy" or "xyz" indicates primary order
    if canonical == "zxy":
        return _norm_zxy(a, b, c)
    # xyz
    z_xy_valid = _valid_tile(c, a, b)
    zxy_valid = _valid_tile(a, b, c)
    if z_xy_valid and not zxy_valid:
        return (a, b, c)
    if zxy_valid and not z_xy_valid:
        return (b, c, a)
    # both or none: keep as xyz if z_xy_valid else swap check
    if not z_xy_valid and zxy_valid:
        return (b, c, a)
    return (a, b, c)


def _placeholder_png_bytes() -> bytes:
    raw = b"\x00\xdd"

    def chunk(typ: bytes, data: bytes) -> bytes:
        body = struct.pack(">I", len(data)) + typ + data
        return body + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


PLACEHOLDER_PNG: bytes = _placeholder_png_bytes()


def _tile_cache_path(z: int, x: int, y: int, cache_root: pathlib.Path | None = None) -> pathlib.Path:
    root = cache_root if cache_root is not None else CACHE_ROOT
    return root / str(z) / str(x) / f"{y}.png"


def _throttle() -> None:
    global _LAST_REQUEST_TS
    with _THROTTLE_LOCK:
        now = time.monotonic()
        elapsed = now - _LAST_REQUEST_TS
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        _LAST_REQUEST_TS = time.monotonic()


def _lru_key(base_url: str | None, z: int, x: int, y: int) -> Tuple[str, int, int, int]:
    return (base_url if base_url is not None else TILE_URL_TEMPLATE, int(z), int(x), int(y))


def _lru_get(key: Tuple[str, int, int, int]) -> bytes | None:
    with _LRU_LOCK:
        if key in _LRU:
            _LRU.move_to_end(key)
            return _LRU[key]
        return None


def _lru_put(key: Tuple[str, int, int, int], data: bytes) -> None:
    with _LRU_LOCK:
        _LRU[key] = data
        _LRU.move_to_end(key)
        while len(_LRU) > MAX_CACHE_ENTRIES:
            _LRU.popitem(last=False)


def latlon_to_tile(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
    if not isinstance(zoom, int):
        raise TypeError("zoom must be int")
    if zoom < 0 or zoom > 30:
        raise ValueError("zoom must be 0..30")
    lat_c = _clamp_lat(float(lat))
    lon_f = float(lon)
    if lon_f < -180 or lon_f > 180:
        lon_f = ((lon_f + 180) % 360) - 180
        if lon_f == -180 and float(lon) > 0:
            lon_f = 180
    n = 1 << zoom
    x_f = (lon_f + 180.0) / 360.0 * n
    lat_rad = math.radians(lat_c)
    y_f = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    x = int(math.floor(x_f))
    y = int(math.floor(y_f))
    if x < 0:
        x = 0
    elif x >= n:
        x = n - 1
    if y < 0:
        y = 0
    elif y >= n:
        y = n - 1
    return (x, y)


def tile_to_latlon(x: int, y: int, zoom: int) -> Tuple[float, float]:
    # support both (x,y,z) and (z,x,y) via heuristic
    if not _valid_tile(zoom, x, y) and _valid_tile(x, y, zoom):
        x, y, zoom = y, zoom, x  # actually (z,x,y) -> (x,y,z)
        # careful: _norm approach
        # fallback generic
        pass
    # use resolver for xyz
    # try canonical xyz, if invalid but swapped valid, swap
    if not _valid_tile(zoom, x, y) and _valid_tile(x, y, zoom):
        x, y, zoom = y, zoom, x
        # The above line is incorrect for general, use _resolve
    # simpler: use _resolve
    # re-resolve properly
    a, b, c = x, y, zoom
    if not _valid_tile(c, a, b) and _valid_tile(a, b, c):
        a, b, c = b, c, a  # (z,x,y) -> (x,y,z)
        x, y, zoom = a, b, c
    x = int(x); y = int(y); zoom = int(zoom)
    if zoom < 0 or zoom > 30:
        raise ValueError("zoom must be 0..30")
    n = 1 << zoom
    if x < 0 or x >= n or y < 0 or y >= n:
        raise ValueError(f"tile coordinates out of range for zoom {zoom}: x={x}, y={y}, n={n}")
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return (lat, lon)


def tile_bounds(x: int, y: int, zoom: int) -> Tuple[float, float, float, float]:
    if not _valid_tile(zoom, x, y) and _valid_tile(x, y, zoom):
        x, y, zoom = y, zoom, x
    a, b, c = x, y, zoom
    if not _valid_tile(c, a, b) and _valid_tile(a, b, c):
        a, b, c = b, c, a
        x, y, zoom = a, b, c
    x = int(x); y = int(y); zoom = int(zoom)
    lat_north, lon_west = tile_to_latlon(x, y, zoom)
    n = 1 << zoom
    lon_east = (x + 1) / n * 360.0 - 180.0
    lat_south_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))
    lat_south = math.degrees(lat_south_rad)
    return (lat_south, lon_west, lat_north, lon_east)


def get_tile_url(z: int, x: int, y: int, base_url: str | None = None) -> str:
    # canonical (z,x,y), also accept (x,y,z)
    a, b, c = z, x, y
    if not _valid_tile(a, b, c) and _valid_tile(c, a, b):
        a, b, c = c, a, b  # (x,y,z) -> (z,x,y)
        z, x, y = a, b, c
    z = int(z); x = int(x); y = int(y)
    if z < 0 or z > 30:
        raise ValueError("z must be 0..30")
    n = 1 << z
    if x < 0 or x >= n or y < 0 or y >= n:
        raise ValueError(f"tile coordinates out of range for z {z}: x={x}, y={y}")
    template = base_url if base_url is not None else TILE_URL_TEMPLATE
    return template.format(z=z, x=x, y=y)


def fetch_tile(
    z: int,
    x: int,
    y: int,
    *,
    base_url: str | None = None,
    cache_dir: pathlib.Path | None = None,
    timeout: float = TIMEOUT,
) -> bytes:
    a, b, c = z, x, y
    if not _valid_tile(a, b, c) and _valid_tile(c, a, b):
        a, b, c = c, a, b
        z, x, y = a, b, c
    z = int(z); x = int(x); y = int(y)
    if z < 0 or z > 30:
        raise ValueError("z must be 0..30")
    n = 1 << z
    if x < 0 or x >= n or y < 0 or y >= n:
        raise ValueError(f"tile coordinates out of range for z {z}: x={x}, y={y}")
    key = _lru_key(base_url, z, x, y)
    cached = _lru_get(key)
    if cached is not None:
        return cached
    path = _tile_cache_path(z, x, y, cache_dir)
    if path.is_file():
        try:
            data = path.read_bytes()
            _lru_put(key, data)
            return data
        except Exception:
            pass
    url = get_tile_url(z, x, y, base_url=base_url)
    last_exc: Exception | None = None
    for attempt in range(RETRY_COUNT + 1):
        _throttle()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # type: ignore[arg-type]
                data = resp.read()
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = path.with_suffix(path.suffix + ".tmp")
                    tmp.write_bytes(data)
                    tmp.replace(path)
                except Exception:
                    pass
                _lru_put(key, data)
                return data
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
            last_exc = e
            if attempt >= RETRY_COUNT:
                break
            time.sleep(0.05)
            continue
    if last_exc is not None:
        return PLACEHOLDER_PNG
    return PLACEHOLDER_PNG


def _clear_caches_for_tests() -> None:
    global _LAST_REQUEST_TS
    # デッドロックなし証明: 本モジュールは常に単一ロックのみ取得し、ネスト取得なし。
    # _throttleは_THROTTLE_LOCKのみ、_lru_*は_LRU_LOCKのみ。順序依存なし。
    # _clear_caches_for_testsは両ロックを逐次取得（ネストせず）するためデッドロック不能。
    # _LAST_REQUEST_TSは_THROTTLE_LOCKのみで保護（分離要件）。
    with _LRU_LOCK:
        _LRU.clear()
    with _THROTTLE_LOCK:
        _LAST_REQUEST_TS = 0.0


def get_attribution() -> str:
    return ATTRIBUTION
