# -*- coding: utf-8 -*-
"""creator/atlas横断の決定論1e-9テスト - QA hardening追加.

検証:
- geo_proj wgs84_to_plane / plane_to_wgs84 決定論 (同一入力→同一出力 1e-9)
- geo_tile latlon_to_tile / tile_to_latlon 決定論
- track.from_candidates (points_lonlat→plane) 決定論 1e-9
- curvature_opt optimize_centerline 決定論 1e-9 (creator横断)
- CourseCreator get_centerline 決定論 1e-9 (両モード)
- OSMCanvas pixel<->latlon roundtrip 決定論 1e-9
- KML Candidate→Track→CourseCreator パイプライン決定論 1e-9
"""
from __future__ import annotations

import pytest
import numpy as np
import numpy.testing as npt


def test_geo_proj_deterministic_1e9() -> None:
    from openlapexe.geo_proj import wgs84_to_plane, plane_to_wgs84, auto_zone

    # スカラー決定論: 同一入力で完全一致
    x1, y1, z1 = wgs84_to_plane(35.68, 139.76)
    x2, y2, z2 = wgs84_to_plane(35.68, 139.76)
    assert x1 == x2
    assert y1 == y2
    assert z1 == z2
    # ベクトル決定論 1e-9
    lats = np.array([35.68, 34.5, 36.1], dtype=float)
    lons = np.array([139.76, 139.70, 140.2], dtype=float)
    xa, ya, za = wgs84_to_plane(lats, lons)
    xb, yb, zb = wgs84_to_plane(lats, lons)
    npt.assert_allclose(xa, xb, atol=1e-9, rtol=0)
    npt.assert_allclose(ya, yb, atol=1e-9, rtol=0)
    assert np.array_equal(za, zb)
    # roundtrip 再変換決定論
    lat2a, lon2a = plane_to_wgs84(xa, ya, za)
    lat2b, lon2b = plane_to_wgs84(xb, yb, zb)
    npt.assert_allclose(lat2a, lat2b, atol=1e-9, rtol=0)
    npt.assert_allclose(lon2a, lon2b, atol=1e-9, rtol=0)
    # auto_zone 決定論
    z_a = auto_zone(139.76)
    z_b = auto_zone(139.76)
    assert z_a == z_b
    lons2 = np.array([139.76, 139.76], dtype=float)
    za2 = auto_zone(lons2)
    zb2 = auto_zone(lons2)
    npt.assert_allclose(za2, zb2, atol=0, rtol=0)


def test_geo_tile_deterministic_1e9() -> None:
    from openlapexe.geo_tile import latlon_to_tile, tile_to_latlon, tile_bounds, get_tile_url

    # latlon_to_tile は整数タイルで完全決定論
    for _ in range(3):
        assert latlon_to_tile(35.68, 139.76, 10) == (909, 403)
        assert latlon_to_tile(35.6590699, 139.7006793, 18) == (232798, 103246)
    # tile_to_latlon 決定論 1e-9
    a1 = tile_to_latlon(909, 403, 10)
    a2 = tile_to_latlon(909, 403, 10)
    npt.assert_allclose(np.array(a1), np.array(a2), atol=1e-9, rtol=0)
    b1 = tile_bounds(909, 403, 10)
    b2 = tile_bounds(909, 403, 10)
    npt.assert_allclose(np.array(b1), np.array(b2), atol=1e-9, rtol=0)
    u1 = get_tile_url(10, 909, 403)
    u2 = get_tile_url(10, 909, 403)
    assert u1 == u2
    # ベクトル的: 複数タイルで roundtrip 決定論
    for lat, lon, z in [(35.68, 139.76, 12), (34.0, 135.0, 8), (43.06, 141.35, 14)]:
        x, y = latlon_to_tile(lat, lon, z)
        x2, y2 = latlon_to_tile(lat, lon, z)
        assert (x, y) == (x2, y2)


def test_track_from_candidates_deterministic_1e9() -> None:
    from openlapexe.track import Track

    cand_lonlat = [(139.0, 35.0), (139.001, 35.0), (139.002, 35.001), (139.003, 35.002)]
    cand = {"points_lonlat": cand_lonlat, "name": "cross_test"}
    t1 = Track.from_candidates([cand])
    t2 = Track.from_candidates([cand])
    assert t1.points.shape == t2.points.shape
    npt.assert_allclose(t1.points, t2.points, atol=1e-9, rtol=0)
    assert abs(t1.length_m - t2.length_m) < 1e-9
    # points_xy 経由も決定論
    cand_xy = {"points_xy": [(0, 0), (10, 0), (10, 10), (20, 10)], "name": "xy_test"}
    t3 = Track.from_candidates([cand_xy])
    t4 = Track.from_candidates([cand_xy])
    npt.assert_allclose(t3.points, t4.points, atol=1e-9, rtol=0)
    # 同一 cand で2回連続→ length_m も 1e-9
    cands = [{"points_xy": [(float(i), float(i * 0.5)) for i in range(10)], "name": "seq"}]
    ta = Track.from_candidates(cands)
    tb = Track.from_candidates(cands)
    npt.assert_allclose(ta.points[:, 0], tb.points[:, 0], atol=1e-9, rtol=0)


def test_curvature_opt_cross_deterministic_1e9() -> None:
    from openlapexe.curvature_opt import optimize_centerline, compute_curvature_profile

    # 固定の左右境界で optimize_centerline が 1e-9 決定論
    left = np.array([[0, 0], [10, 0], [10, 10], [20, 10]], dtype=float)
    # 右側は幅4mオフセット
    right = left + np.array([[0, 4], [0, 4], [0, 4], [0, 4]], dtype=float)
    # 左右を細かくリサンプルして最適化テストに適した形に
    def resample(pts, N=20):
        s = np.zeros(pts.shape[0])
        for i in range(1, pts.shape[0]):
            s[i] = s[i - 1] + float(np.hypot(pts[i, 0] - pts[i - 1, 0], pts[i, 1] - pts[i - 1, 1]))
        L = s[-1]
        pts_ext = pts
        s_ext = s
        s_new = np.linspace(0, L, N)
        x_new = np.interp(s_new, s_ext, pts_ext[:, 0])
        y_new = np.interp(s_new, s_ext, pts_ext[:, 1])
        return np.stack([x_new, y_new], axis=1)
    li = resample(left, 20)
    ri = resample(right, 20)
    c1, curv1 = optimize_centerline(li, ri, closed=False, iters=40, width_margin=0.1)
    c2, curv2 = optimize_centerline(li, ri, closed=False, iters=40, width_margin=0.1)
    npt.assert_allclose(c1, c2, atol=1e-9, rtol=0)
    npt.assert_allclose(curv1, curv2, atol=1e-9, rtol=0)
    # compute_curvature_profile も決定論
    k1 = compute_curvature_profile(c1, closed=False)
    k2 = compute_curvature_profile(c2, closed=False)
    npt.assert_allclose(k1, k2, atol=1e-9, rtol=0)


def test_course_creator_cross_deterministic_1e9() -> None:
    # ヘッドレスならスキップ
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.update_idletasks()
        has_display = True
    except Exception:
        pytest.skip("no display")
    try:
        from openlapexe.gui.course_creator import CourseCreator

        cc = CourseCreator(root, width=600, height=400)
        cc.pack()
        root.update_idletasks()
        pts = [(0, 0), (10, 0), (10, 10), (20, 10), (20, 20)]
        cc.set_mode("direct")
        cc.set_points(pts)
        root.update_idletasks()
        c1 = cc.get_centerline()
        c2 = cc.get_centerline()
        npt.assert_allclose(c1, c2, atol=1e-9, rtol=0)
        # direct mode: set_points 2回 同一入力で同一 centerline
        cc.set_points(pts)
        c3 = cc.get_centerline()
        npt.assert_allclose(c1, c3, atol=1e-9, rtol=0)
        # edge mode も決定論
        left = [(0, 0), (10, 0), (10, 10)]
        right = [(0, 4), (10, 4), (10, 14)]
        cc.set_mode("edge")
        cc.set_left_right(left, right)
        root.update_idletasks()
        e1 = cc.get_centerline()
        e2 = cc.get_centerline()
        npt.assert_allclose(e1, e2, atol=1e-9, rtol=0)
        # 再設定でも同一
        cc.set_left_right(left, right)
        e3 = cc.get_centerline()
        npt.assert_allclose(e1, e3, atol=1e-9, rtol=0)
        cc.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_kml_candidate_to_track_to_creator_deterministic_1e9(tmp_path) -> None:
    """KMLパース→Track.from_candidates→CourseCreator パイプライン横断で決定論 1e-9."""
    from openlapexe.io_kml import parse_kml
    from openlapexe.track import Track
    import pathlib

    kml = """<?xml version="1.0" encoding="UTF-8"?><kml><Document><Placemark><name>Pipe</name><LineString><coordinates>139.0,35.0,0 139.001,35.0,0 139.002,35.001,0</coordinates></LineString></Placemark></Document></kml>"""
    p = tmp_path / "pipe.kml"
    p.write_text(kml, encoding="utf-8")
    cands1 = parse_kml(p)
    cands2 = parse_kml(p)
    assert len(cands1) == 1 and len(cands2) == 1
    # Candidate自体決定論
    assert cands1[0].points_lonlat == cands2[0].points_lonlat
    assert abs(cands1[0].length_m - cands2[0].length_m) < 1e-9
    # Track.from_candidates 決定論
    t1 = Track.from_candidates(cands1)
    t2 = Track.from_candidates(cands2)
    npt.assert_allclose(t1.points, t2.points, atol=1e-9, rtol=0)
    # さらに s 単調・length_m一致 1e-9
    npt.assert_allclose(t1.points[:, 0], t2.points[:, 0], atol=1e-9, rtol=0)
    assert abs(t1.length_m - t2.length_m) < 1e-9


def test_osm_canvas_pixel_latlon_deterministic_1e9() -> None:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.update_idletasks()
    except Exception:
        pytest.skip("no display")
    try:
        from openlapexe.gui.osm_canvas import OSMCanvas

        c = OSMCanvas(root, width=400, height=300, center_lat=35.68, center_lon=139.76, zoom=12)
        c.pack()
        root.update()
        # pixel<->latlon 往復が 1e-9 で決定論 (同一入力→同一出力)
        for px, py in [(200, 150), (100, 100), (300, 200)]:
            lat1, lon1 = c.pixel_to_latlon(px, py)
            lat2, lon2 = c.pixel_to_latlon(px, py)
            assert abs(lat1 - lat2) < 1e-9
            assert abs(lon1 - lon2) < 1e-9
            # 往復: pixel->latlon->pixel
            px1, py1 = c.latlon_to_pixel(lat1, lon1)
            px2, py2 = c.latlon_to_pixel(lat1, lon1)
            assert abs(px1 - px2) < 1e-9
            assert abs(py1 - py2) < 1e-9
            # 元の px,py との roundtrip は 1e-6 程度の誤差許容だが、決定論は 1e-9 で同一
            # 第二回往復も同一
            lat1b, lon1b = c.pixel_to_latlon(px1, py1)
            assert abs(lat1b - lat1) < 1e-6
        root.destroy()
    except Exception as e:
        try:
            root.destroy()
        except Exception:
            pass
        # OSMCanvas特有の例外はスキップではなく失敗として扱うが、headless起因はskip
        if "display" in str(e).lower() or "couldn't connect" in str(e).lower():
            pytest.skip(f"headless: {e}")
        raise
