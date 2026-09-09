# -*- coding: utf-8 -*-
"""WGS84 -> 平面直交 Gauss-Kruger projection (numpy only, deterministic).

楕円体級数展開で Transverse Mercator を実装する。
- 楕円体: WGS84 a=6378137, f=1/298.257
- 日本平面直角19系を主とし、範囲外は UTM fallback
- k0: 日本 0.9999 / UTM 0.9996
- lat0 = 0, lon0 は zone により決定、false easting/northing なし (X=northing, Y=easting)
- ベクトル化対応、決定論的、numpyのみ
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

# --- 楕円体定数 ---
A: float = 6378137.0
F: float = 1.0 / 298.257
E2: float = 2 * F - F * F
E4: float = E2 * E2
E6: float = E4 * E2
EP2: float = E2 / (1.0 - E2)

K0_JP: float = 0.9999
K0_UTM: float = 0.9996

# 日本平面直角19系 中央子午線 (度) GSI 基準
# 1:129°00' 2:131°00' 3:132°10' 4:133°20' 5:134°20' 6:136°00'
# 7:137°10' 8:138°30' 9:139°50' 10:140°50' 11:140°15' 12:142°15'
# 13:144°15' 14:142°00' 15:144°00' 16:142°30' 17:144°30' 18:145°30' 19:146°00'
_JP_LON0: tuple[float, ...] = (
    129.0,  # 1
    131.0,  # 2
    132.0 + 10.0 / 60.0,  # 3 132°10'
    133.0 + 20.0 / 60.0,  # 4 133°20'
    134.0 + 20.0 / 60.0,  # 5 134°20'
    136.0,  # 6
    137.0 + 10.0 / 60.0,  # 7 137°10'
    138.0 + 30.0 / 60.0,  # 8 138°30'
    139.0 + 50.0 / 60.0,  # 9 139°50'
    140.0 + 50.0 / 60.0,  # 10 140°50'
    140.0 + 15.0 / 60.0,  # 11 140°15'
    142.0 + 15.0 / 60.0,  # 12 142°15'
    144.0 + 15.0 / 60.0,  # 13 144°15'
    142.0,  # 14 142°00' (北海道西部)
    144.0,  # 15 144°00'
    142.0 + 30.0 / 60.0,  # 16 142°30'
    144.0 + 30.0 / 60.0,  # 17 144°30'
    145.0 + 30.0 / 60.0,  # 18 145°30'
    146.0,  # 19 146°00'
)

_JP_LON0_ARR = np.asarray(_JP_LON0, dtype=np.float64)

# meridional arc 係数
_M_A0: float = 1.0 + 3.0 * E2 / 4.0 + 45.0 * E4 / 64.0 + 350.0 * E6 / 512.0
_M_B0: float = 3.0 * E2 / 8.0 + 15.0 * E4 / 32.0 + 525.0 * E6 / 1024.0
_M_C0: float = 15.0 * E4 / 256.0 + 105.0 * E6 / 1024.0
_M_D0: float = 35.0 * E6 / 3072.0

_M_COEF = A * (1.0 - E2)

_E1: float = (1.0 - np.sqrt(1.0 - E2)) / (1.0 + np.sqrt(1.0 - E2))
_E1_2: float = _E1 * _E1
_E1_3: float = _E1_2 * _E1
_E1_4: float = _E1_3 * _E1


def _meridional_arc(lat_rad: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """赤道から緯度 lat までの子午線弧長 M."""
    return _M_COEF * (
        _M_A0 * lat_rad
        - _M_B0 * np.sin(2.0 * lat_rad)
        + _M_C0 * np.sin(4.0 * lat_rad)
        - _M_D0 * np.sin(6.0 * lat_rad)
    )


def _lon0_for_zone(zone: int | np.ndarray) -> float | npt.NDArray[np.float64]:
    """zone -> 中央子午線 lon0 (度). 1-19は日本、20-60はUTM."""
    z = np.asarray(zone)
    scalar = z.ndim == 0
    z_arr = np.atleast_1d(z).astype(np.int64)
    out = np.empty_like(z_arr, dtype=np.float64)
    mask_jp = (z_arr >= 1) & (z_arr <= 19)
    mask_utm = ~mask_jp
    if np.any(mask_jp):
        out[mask_jp] = _JP_LON0_ARR[z_arr[mask_jp] - 1]
    if np.any(mask_utm):
        out[mask_utm] = z_arr[mask_utm].astype(np.float64) * 6.0 - 183.0
    if scalar:
        return float(out[0])
    return out


def auto_zone(lon) -> int | npt.NDArray[np.int64]:
    """経度 lon(度) -> zone.

    - 122 <= lon <= 154 は日本平面直角19系 (最も近い lon0 を選択)
    - 範囲外は UTM fallback: int((lon+180)/6)+1
    ベクトル化対応、スカラー入力はスカラー出力。
    """
    lon_arr = np.asarray(lon, dtype=np.float64)
    scalar = lon_arr.ndim == 0
    flat = np.atleast_1d(lon_arr)
    out = np.empty_like(flat, dtype=np.int64)
    # 日本範囲マスク
    mask_jp = (flat >= 122.0) & (flat <= 154.0)
    mask_utm = ~mask_jp
    if np.any(mask_jp):
        jp_lons = flat[mask_jp]
        # 各 lon と 19 個の lon0 の差の絶対値最小
        # shape (N_jp, 19)
        diff = np.abs(jp_lons[:, None] - _JP_LON0_ARR[None, :])
        out[mask_jp] = np.argmin(diff, axis=1).astype(np.int64) + 1
    if np.any(mask_utm):
        utm = np.floor((flat[mask_utm] + 180.0) / 6.0).astype(np.int64) + 1
        # 1-60 にクランプ
        utm = np.clip(utm, 1, 60)
        out[mask_utm] = utm
    if scalar:
        return int(out[0])
    # 元の shape に戻す
    return out.reshape(lon_arr.shape)


def wgs84_to_plane(lat, lon, zone=None):
    """WGS84 (lat,lon 度) -> 平面直交 (x,y,zone).

    - lat, lon はスカラーまたは配列 (ブロードキャスト可)
    - zone を省略すると auto_zone(lon) で自動決定
    - x: northing (m, 赤道基準 k0 倍), y: easting (m, 中央子午線基準)
    戻り値は x, y, zone のタプル。zone はスカラー入力なら int、配列なら ndarray。
    """
    lat_arr = np.asarray(lat, dtype=np.float64)
    lon_arr = np.asarray(lon, dtype=np.float64)
    # ブロードキャスト用の shape 決定
    bshape = np.broadcast_shapes(lat_arr.shape, lon_arr.shape)
    lat_b = np.broadcast_to(lat_arr, bshape)
    lon_b = np.broadcast_to(lon_arr, bshape)
    lat_was_scalar = np.ndim(lat) == 0 and np.ndim(lon) == 0 and zone is None or (isinstance(zone, int) and np.ndim(lat) == 0)
    # zone 解決
    if zone is None:
        zone_arr = auto_zone(lon_b)
    else:
        z = np.asarray(zone)
        if z.ndim == 0:
            zone_arr = np.full(bshape, int(z), dtype=np.int64)
        else:
            zone_arr = np.broadcast_to(z, bshape).astype(np.int64)

    # 中央子午線
    lon0_arr = np.empty(bshape, dtype=np.float64)
    # ベクトル化で zone ごとに lon0 を引く
    # 少数の異なる zone に対してマスク処理の方が速い
    uniq = np.unique(zone_arr)
    for uz in uniq:
        mask = zone_arr == uz
        if 1 <= int(uz) <= 19:
            lon0_arr[mask] = _JP_LON0_ARR[int(uz) - 1]
        else:
            lon0_arr[mask] = float(int(uz)) * 6.0 - 183.0

    # ラジアン変換
    lat_rad = np.deg2rad(lat_b.astype(np.float64))
    lon_rad = np.deg2rad(lon_b.astype(np.float64))
    lon0_rad = np.deg2rad(lon0_arr)

    dlon = lon_rad - lon0_rad
    sin_lat = np.sin(lat_rad)
    cos_lat = np.cos(lat_rad)
    tan_lat = np.tan(lat_rad)

    N = A / np.sqrt(1.0 - E2 * sin_lat * sin_lat)
    T = tan_lat * tan_lat
    C = EP2 * cos_lat * cos_lat
    A_ = dlon * cos_lat
    M = _meridional_arc(lat_rad)

    # k0 は zone ごとに選択
    k0_arr = np.where((zone_arr >= 1) & (zone_arr <= 19), K0_JP, K0_UTM)
    # スカラーで where が 0d になる場合を吸収
    if np.ndim(k0_arr) == 0:
        k0_arr = np.full(bshape, float(k0_arr), dtype=np.float64)
    else:
        k0_arr = k0_arr.astype(np.float64)
        if k0_arr.shape != bshape:
            k0_arr = np.broadcast_to(k0_arr, bshape).copy()

    A2 = A_ * A_
    A3 = A2 * A_
    A4 = A2 * A2
    A5 = A4 * A_
    A6 = A4 * A2

    x = k0_arr * (
        M
        + N * tan_lat * (A2 / 2.0 + (5.0 - T + 9.0 * C + 4.0 * C * C) * A4 / 24.0 + (61.0 - 58.0 * T + T * T + 600.0 * C - 330.0 * EP2) * A6 / 720.0)
    )
    y = k0_arr * N * (A_ + (1.0 - T + C) * A3 / 6.0 + (5.0 - 18.0 * T + T * T + 72.0 * C - 58.0 * EP2) * A5 / 120.0)

    # スカラー入力ならスカラー出力
    if bshape == ():
        return float(x), float(y), int(zone_arr)
    # zone は int 配列のまま返す
    return x, y, zone_arr


def plane_to_wgs84(x, y, zone, lon0=None):
    """平面直交 (x,y,zone) -> WGS84 (lat,lon 度).

    - x, y はスカラーまたは配列
    - zone は必須 (wgs84_to_plane が返した値を使用)
    - lon0 を明示的に渡すとその値を中央子午線として使用
    戻り値は (lat, lon) タプル。スカラー入力なら float、配列なら ndarray。
    """
    x_arr = np.asarray(x, dtype=np.float64)
    y_arr = np.asarray(y, dtype=np.float64)
    z_arr = np.asarray(zone)
    bshape = np.broadcast_shapes(x_arr.shape, y_arr.shape, z_arr.shape)
    x_b = np.broadcast_to(x_arr, bshape)
    y_b = np.broadcast_to(y_arr, bshape)
    zb = np.broadcast_to(z_arr, bshape).astype(np.int64)

    if lon0 is not None:
        lo = np.asarray(lon0, dtype=np.float64)
        lon0_arr = np.broadcast_to(lo, bshape).astype(np.float64)
    else:
        lon0_arr = np.empty(bshape, dtype=np.float64)
        uniq = np.unique(zb)
        for uz in uniq:
            mask = zb == uz
            if 1 <= int(uz) <= 19:
                lon0_arr[mask] = _JP_LON0_ARR[int(uz) - 1]
            else:
                lon0_arr[mask] = float(int(uz)) * 6.0 - 183.0

    lon0_rad = np.deg2rad(lon0_arr)

    k0_arr = np.where((zb >= 1) & (zb <= 19), K0_JP, K0_UTM)
    if np.ndim(k0_arr) == 0:
        k0_arr = np.full(bshape, float(k0_arr), dtype=np.float64)
    else:
        k0_arr = k0_arr.astype(np.float64)
        if k0_arr.shape != bshape:
            k0_arr = np.broadcast_to(k0_arr, bshape).copy()

    # 足 Washington: M' から mu を求める
    M0 = 0.0
    Mp = M0 + x_b / k0_arr
    mu = Mp / _M_COEF / _M_A0

    # phi1 (footpoint latitude)
    sin2mu = np.sin(2.0 * mu)
    sin4mu = np.sin(4.0 * mu)
    sin6mu = np.sin(6.0 * mu)
    sin8mu = np.sin(8.0 * mu)

    phi1 = (
        mu
        + (3.0 * _E1 / 2.0 - 27.0 * _E1_3 / 32.0) * sin2mu
        + (21.0 * _E1_2 / 16.0 - 55.0 * _E1_4 / 32.0) * sin4mu
        + (151.0 * _E1_3 / 96.0) * sin6mu
        + (1097.0 * _E1_4 / 512.0) * sin8mu
    )

    sin_phi1 = np.sin(phi1)
    cos_phi1 = np.cos(phi1)
    tan_phi1 = np.tan(phi1)

    N1 = A / np.sqrt(1.0 - E2 * sin_phi1 * sin_phi1)
    R1 = A * (1.0 - E2) / np.power(1.0 - E2 * sin_phi1 * sin_phi1, 1.5)
    T1 = tan_phi1 * tan_phi1
    C1 = EP2 * cos_phi1 * cos_phi1
    D = y_b / (k0_arr * N1)

    D2 = D * D
    D3 = D2 * D
    D4 = D2 * D2
    D5 = D4 * D
    D6 = D4 * D2

    lat_rad = phi1 - (N1 * tan_phi1 / R1) * (
        D2 / 2.0 - (5.0 + 3.0 * T1 + 10.0 * C1 - 4.0 * C1 * C1 - 9.0 * EP2) * D4 / 24.0 + (61.0 + 90.0 * T1 + 298.0 * C1 + 45.0 * T1 * T1 - 252.0 * EP2 - 3.0 * C1 * C1) * D6 / 720.0
    )
    lon_rad = lon0_rad + (
        D - (1.0 + 2.0 * T1 + C1) * D3 / 6.0 + (5.0 - 2.0 * C1 + 28.0 * T1 - 3.0 * C1 * C1 + 8.0 * EP2 + 24.0 * T1 * T1) * D5 / 120.0
    ) / cos_phi1

    lat = np.rad2deg(lat_rad)
    lon = np.rad2deg(lon_rad)

    if bshape == ():
        return float(lat), float(lon)
    return lat, lon


__all__ = ["wgs84_to_plane", "plane_to_wgs84", "auto_zone"]
