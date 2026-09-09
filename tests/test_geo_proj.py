# -*- coding: utf-8 -*-
import time

import numpy as np
import pytest


def test_import():
    from openlapexe.geo_proj import auto_zone, plane_to_wgs84, wgs84_to_plane

    assert callable(wgs84_to_plane)
    assert callable(plane_to_wgs84)
    assert callable(auto_zone)


def test_tokyo_zone9_roundtrip():
    from openlapexe.geo_proj import plane_to_wgs84, wgs84_to_plane

    lat, lon = 35.68, 139.76
    x, y, zone = wgs84_to_plane(lat, lon)
    assert zone == 9
    lat2, lon2 = plane_to_wgs84(x, y, zone)
    assert abs(lat2 - lat) < 1e-3
    assert abs(lon2 - lon) < 1e-3


def test_tokyo_vectorized_roundtrip():
    from openlapexe.geo_proj import plane_to_wgs84, wgs84_to_plane

    lats = np.array([35.68, 35.68])
    lons = np.array([139.76, 139.76])
    x, y, zone = wgs84_to_plane(lats, lons)
    assert x.shape == (2,)
    assert zone[0] == 9
    lat2, lon2 = plane_to_wgs84(x, y, zone)
    assert np.all(np.abs(lat2 - lats) < 1e-3)
    assert np.all(np.abs(lon2 - lons) < 1e-3)


def test_auto_zone_122_154_single():
    from openlapexe.geo_proj import auto_zone

    for lon in range(122, 155):
        z = auto_zone(float(lon))
        assert 1 <= z <= 19, f"lon {lon} zone {z} not in 1-19"
    # ベクトル入力
    lons = np.arange(122, 155, dtype=float)
    zones = auto_zone(lons)
    assert zones.shape == (33,)
    assert np.all((zones >= 1) & (zones <= 19))


def test_auto_zone_utm_fallback():
    from openlapexe.geo_proj import auto_zone

    assert auto_zone(0.0) == 31  # int((0+180)/6)+1
    assert auto_zone(10.0) == 32
    assert auto_zone(-120.0) == 11
    # 配列 fallback
    lons = np.array([-120.0, 0.0, 10.0])
    zs = auto_zone(lons)
    assert list(zs) == [11, 31, 32]


def test_10000_points_under_50ms():
    from openlapexe.geo_proj import wgs84_to_plane

    n = 10000
    rng = np.random.default_rng(0)
    lats = rng.uniform(30.0, 45.0, size=n)
    lons = rng.uniform(129.0, 145.0, size=n)
    t0 = time.perf_counter()
    x, y, zone = wgs84_to_plane(lats, lons)
    dt = (time.perf_counter() - t0) * 1000.0
    assert dt < 50.0, f"10k forward {dt:.1f}ms exceeds 50ms"
    assert x.shape == (n,)
    assert y.shape == (n,)
    assert zone.shape == (n,)


def test_deterministic():
    from openlapexe.geo_proj import wgs84_to_plane

    x1, y1, z1 = wgs84_to_plane(35.68, 139.76)
    x2, y2, z2 = wgs84_to_plane(35.68, 139.76)
    assert x1 == x2
    assert y1 == y2
    assert z1 == z2


def test_inverse_vectorized():
    from openlapexe.geo_proj import plane_to_wgs84, wgs84_to_plane

    lats = np.array([34.0, 35.0, 36.0])
    lons = np.array([135.0, 139.0, 141.0])
    x, y, zone = wgs84_to_plane(lats, lons)
    lat2, lon2 = plane_to_wgs84(x, y, zone)
    assert np.allclose(lat2, lats, atol=1e-3)
    assert np.allclose(lon2, lons, atol=1e-3)
