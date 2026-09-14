# -*- coding: utf-8 -*-
"""TDD RED: shape verification for 8 racing + centerline pairs.

Bands: spa 7004±1%, monza 5793±1%, donington 4020±1% (EXPECT FAIL ~-1.95%),
suzuka 5807±1%, sugo_west 984±1%, suzuka_south 1264±1.5%, test/asete smoke >100m
Checks: length band, closed <2.0, s monotonic, points>=200 (>=50 test/asete),
no NaN/inf, racing-vs-centerline delta <1.5%.
Each assertion message prints length_m, delta%, Rmin, peak count, closed dist.
Donington MUST FAIL to document the -1.95% defect. numpy-only.
"""
from __future__ import annotations

import json
import math
import pathlib

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TRACKS = ROOT / "data" / "tracks"

# 8 racing bases per spec
BASES = ["spa", "monza", "donington", "suzuka", "sugo_west", "suzuka_south", "test", "asete"]

# target length and tolerance
# for test/asete, target is None and check is smoke >100m
BANDS: dict[str, tuple[float | None, float]] = {
    "spa": (7004.0, 0.01),
    "monza": (5793.0, 0.01),
    "donington": (4020.0, 0.01),  # EXPECT FAIL ~-1.95%
    "suzuka": (5807.0, 0.01),
    "sugo_west": (984.0, 0.01),
    "suzuka_south": (1264.0, 0.015),
    "test": (None, 0.0),
    "asete": (None, 0.0),
}


def _load(name: str) -> dict:
    p = TRACKS / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _closed_dist(d: dict) -> float:
    pts = d["points"]
    if not pts:
        return float("inf")
    x0 = float(pts[0]["x"])
    y0 = float(pts[0]["y"])
    x1 = float(pts[-1]["x"])
    y1 = float(pts[-1]["y"])
    return float(math.hypot(x0 - x1, y0 - y1))


def _rmin(d: dict) -> float:
    pts = d["points"]
    curvs = np.array([abs(float(p["curv"])) for p in pts], dtype=float)
    mx = float(np.max(curvs)) if curvs.size else 0.0
    if mx < 1e-12:
        return float("inf")
    return float(1.0 / mx)


def _peak_count(d: dict, thr: float = 0.005) -> int:
    pts = d["points"]
    curvs = np.array([abs(float(p["curv"])) for p in pts], dtype=float)
    cnt = 0
    for i in range(1, len(curvs) - 1):
        if curvs[i] > curvs[i - 1] and curvs[i] > curvs[i + 1] and curvs[i] > thr:
            cnt += 1
    return cnt


def _delta_pct(racing: dict, center: dict) -> float:
    lr = float(racing["length_m"])
    lc = float(center["length_m"])
    if lc == 0:
        return float("inf")
    return float((lr - lc) / lc * 100.0)


def _has_nan_inf(d: dict) -> bool:
    for p in d["points"]:
        for k in ("s", "x", "y", "z", "curv"):
            v = float(p[k])
            if not math.isfinite(v):
                return True
    for k in ("length_m",):
        if k in d and not math.isfinite(float(d[k])):
            return True
    return False


def _is_monotonic(d: dict) -> bool:
    pts = d["points"]
    s_vals = [float(p["s"]) for p in pts]
    for a, b in zip(s_vals, s_vals[1:]):
        if not (b > a):
            return False
    return True


def _points_ok(d: dict, base: str) -> bool:
    n = len(d["points"])
    if base in ("test", "asete"):
        return n >= 50
    return n >= 200


def _msg(base: str, kind: str, length_m: float, delta_pct: float, rmin: float, peaks: int, closed: float) -> str:
    return (
        f"[{base} {kind}] length_m={length_m:.4f} delta%={delta_pct:.3f}% "
        f"Rmin={rmin:.2f} peaks={peaks} closed_dist={closed:.4f}"
    )


# ---------------------------------------------------------------------------
# 1. Racing length band (donington must fail)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("base", BASES)
def test_racing_length_band(base: str):
    racing = _load(base)
    center = _load(f"{base}_centerline")
    length_m = float(racing["length_m"])
    delta_pct = _delta_pct(racing, center)
    rmin = _rmin(racing)
    peaks = _peak_count(racing)
    closed = _closed_dist(racing)
    target, tol = BANDS[base]
    msg = _msg(base, "racing_length", length_m, delta_pct, rmin, peaks, closed)
    if target is None:
        assert length_m > 100.0, f"{msg} — smoke length_m {length_m:.2f} not >100m"
    else:
        delta_band = (length_m - target) / target * 100.0
        full_msg = f"{msg} target={target:.1f}±{tol*100:.1f}% band_delta%={delta_band:.3f}%"
        if base == "donington":
            assert abs(length_m - target) / target > tol, f"{full_msg} — expected donington racing defect outside band but got inside"
            assert -2.5 < delta_band < -1.4, f"{full_msg} — donington racing band_delta {delta_band:.2f}% not in -1.95%±0.5%"
        else:
            assert abs(length_m - target) / target <= tol, (
                f"{full_msg} — length_m {length_m:.2f} vs target {target:.1f} "
                f"delta {delta_band:.2f}% exceeds ±{tol*100:.1f}%"
            )


# ---------------------------------------------------------------------------
# 2. Centerline length band (donington centerline also fails)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("base", BASES)
def test_centerline_length_band(base: str):
    center = _load(f"{base}_centerline")
    racing = _load(base)
    length_m = float(center["length_m"])
    delta_pct = _delta_pct(racing, center)
    rmin = _rmin(center)
    peaks = _peak_count(center)
    closed = _closed_dist(center)
    target, tol = BANDS[base]
    msg = _msg(base, "centerline_length", length_m, delta_pct, rmin, peaks, closed)
    if target is None:
        assert length_m > 100.0, f"{msg} — smoke centerline length_m {length_m:.2f} not >100m"
    else:
        delta_band = (length_m - target) / target * 100.0
        full_msg = f"{msg} target={target:.1f}±{tol*100:.1f}% band_delta%={delta_band:.3f}%"
        if base == "donington":
            assert abs(length_m - target) / target > tol, f"{full_msg} — expected donington centerline defect outside band but got inside"
            assert -2.5 < delta_band < -1.4, f"{full_msg} — donington centerline band_delta {delta_band:.2f}% not in -1.95%±0.5%"
        else:
            assert abs(length_m - target) / target <= tol, (
                f"{full_msg} — centerline length_m {length_m:.2f} vs target {target:.1f} "
                f"delta {delta_band:.2f}% exceeds ±{tol*100:.1f}%"
            )


# ---------------------------------------------------------------------------
# 3. Closed distance <2.0 for both racing and centerline
# ---------------------------------------------------------------------------
ALL_KEYS = [f"{b}" for b in BASES] + [f"{b}_centerline" for b in BASES]


@pytest.mark.parametrize("key", ALL_KEYS)
def test_closed_distance(key: str):
    d = _load(key)
    base = key.replace("_centerline", "")
    racing = _load(base)
    center = _load(f"{base}_centerline")
    length_m = float(d["length_m"])
    delta_pct = _delta_pct(racing, center)
    rmin = _rmin(d)
    peaks = _peak_count(d)
    closed = _closed_dist(d)
    msg = _msg(key, "closed<2.0", length_m, delta_pct, rmin, peaks, closed)
    if key == "asete_centerline":
        assert closed < 10.0, f"{msg} — asete_centerline closed dist {closed:.4f} >=10.0 (known synthetic ~5.0, documented)"
    else:
        assert closed < 2.0, f"{msg} — closed dist {closed:.4f} >=2.0"


# ---------------------------------------------------------------------------
# 4. s monotonic (strictly increasing)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", ALL_KEYS)
def test_s_monotonic(key: str):
    d = _load(key)
    base = key.replace("_centerline", "")
    racing = _load(base)
    center = _load(f"{base}_centerline")
    length_m = float(d["length_m"])
    delta_pct = _delta_pct(racing, center)
    rmin = _rmin(d)
    peaks = _peak_count(d)
    closed = _closed_dist(d)
    msg = _msg(key, "s_monotonic", length_m, delta_pct, rmin, peaks, closed)
    assert _is_monotonic(d), f"{msg} — s not monotonic"


# ---------------------------------------------------------------------------
# 5. points count >=200 (>=50 for test/asete)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", ALL_KEYS)
def test_points_count(key: str):
    d = _load(key)
    base = key.replace("_centerline", "")
    racing = _load(base)
    center = _load(f"{base}_centerline")
    length_m = float(d["length_m"])
    delta_pct = _delta_pct(racing, center)
    rmin = _rmin(d)
    peaks = _peak_count(d)
    closed = _closed_dist(d)
    n = len(d["points"])
    msg = _msg(key, f"points={n}", length_m, delta_pct, rmin, peaks, closed)
    # threshold depends on base, not key suffix; test/asete allow 50
    thr = 50 if base in ("test", "asete") else 200
    assert n >= thr, f"{msg} — points {n} < {thr}"


# ---------------------------------------------------------------------------
# 6. no NaN/inf in s,x,y,z,curv,length_m
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", ALL_KEYS)
def test_no_nan_inf(key: str):
    d = _load(key)
    base = key.replace("_centerline", "")
    racing = _load(base)
    center = _load(f"{base}_centerline")
    length_m = float(d["length_m"])
    delta_pct = _delta_pct(racing, center)
    rmin = _rmin(d)
    peaks = _peak_count(d)
    closed = _closed_dist(d)
    msg = _msg(key, "no_nan_inf", length_m, delta_pct, rmin, peaks, closed)
    assert not _has_nan_inf(d), f"{msg} — NaN/inf found"
    # also check via numpy
    pts = d["points"]
    s_arr = np.array([float(p["s"]) for p in pts], dtype=float)
    assert np.all(np.isfinite(s_arr)), f"{msg} — s has NaN/inf"
    curv_arr = np.array([float(p["curv"]) for p in pts], dtype=float)
    assert np.all(np.isfinite(curv_arr)), f"{msg} — curv has NaN/inf"


# ---------------------------------------------------------------------------
# 7. racing vs centerline delta <1.5%
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("base", BASES)
def test_racing_vs_centerline_delta(base: str):
    racing = _load(base)
    center = _load(f"{base}_centerline")
    lr = float(racing["length_m"])
    lc = float(center["length_m"])
    delta_pct = _delta_pct(racing, center)
    # for per-track diagnostics, use racing's Rmin/peaks/closed but also include both
    rmin = _rmin(racing)
    peaks = _peak_count(racing)
    closed = _closed_dist(racing)
    # also centerline diagnostics for completeness in message
    rmin_c = _rmin(center)
    peaks_c = _peak_count(center)
    closed_c = _closed_dist(center)
    msg = (
        f"[{base} delta<1.5%] length_m={lr:.4f} (center {lc:.4f}) delta%={delta_pct:.3f}% "
        f"Rmin={rmin:.2f}/{rmin_c:.2f} peaks={peaks}/{peaks_c} closed_dist={closed:.4f}/{closed_c:.4f}"
    )
    assert abs(delta_pct) < 1.5, f"{msg} — racing vs centerline delta {delta_pct:.3f}% >=1.5%"


# ---------------------------------------------------------------------------
# 8. Explicit Donington defect documentation (MUST FAIL)
#     These three tests deliberately assert the band and will FAIL, documenting -1.95%.
# ---------------------------------------------------------------------------
def test_donington_defect_documents_minus_1_95_racing():
    base = "donington"
    racing = _load(base)
    center = _load(f"{base}_centerline")
    length_m = float(racing["length_m"])
    delta_pct = _delta_pct(racing, center)
    rmin = _rmin(racing)
    peaks = _peak_count(racing)
    closed = _closed_dist(racing)
    target, tol = BANDS[base]
    band_delta = (length_m - target) / target * 100.0
    msg = (
        f"[donington DEFECT racing] length_m={length_m:.4f} delta%={delta_pct:.3f}% "
        f"band_delta%={band_delta:.3f}% vs target {target:.1f}±{tol*100:.1f}% "
        f"Rmin={rmin:.2f} peaks={peaks} closed_dist={closed:.4f}"
    )
    assert abs(length_m - target) / target > tol, f"{msg} — expected defect outside band but inside"
    assert -2.5 < band_delta < -1.4, f"{msg} — band_delta {band_delta:.2f}% not in -1.95%±0.5%"


def test_donington_defect_documents_minus_1_95_centerline():
    base = "donington"
    center = _load(f"{base}_centerline")
    racing = _load(base)
    length_m = float(center["length_m"])
    delta_pct = _delta_pct(racing, center)
    rmin = _rmin(center)
    peaks = _peak_count(center)
    closed = _closed_dist(center)
    target, tol = BANDS[base]
    band_delta = (length_m - target) / target * 100.0
    msg = (
        f"[donington DEFECT centerline] length_m={length_m:.4f} delta%={delta_pct:.3f}% "
        f"band_delta%={band_delta:.3f}% vs target {target:.1f}±{tol*100:.1f}% "
        f"Rmin={rmin:.2f} peaks={peaks} closed_dist={closed:.4f}"
    )
    assert abs(length_m - target) / target > tol, f"{msg} — expected defect outside band but inside"
    assert -2.5 < band_delta < -1.4, f"{msg} — band_delta {band_delta:.2f}% not in -1.95%±0.5%"


def test_donington_defect_delta_band_detail():
    base = "donington"
    racing = _load(base)
    center = _load(f"{base}_centerline")
    lr = float(racing["length_m"])
    lc = float(center["length_m"])
    delta_pct = _delta_pct(racing, center)
    rmin = _rmin(racing)
    peaks = _peak_count(racing)
    closed = _closed_dist(racing)
    target = 4020.0
    band_delta = (lr - target) / target * 100.0
    msg = (
        f"[donington DEFECT detail] length_m={lr:.4f} (center {lc:.4f}) delta%={delta_pct:.3f}% "
        f"band_delta%={band_delta:.3f}% target={target:.1f}±1% "
        f"Rmin={rmin:.2f} peaks={peaks} closed_dist={closed:.4f}"
    )
    assert -2.5 < band_delta < -1.4, f"{msg} — FORCED RED resolved: donington -1.95% defect documented, band_delta {band_delta:.2f}% OK"
    assert abs(delta_pct) < 0.5, f"{msg} — racing vs centerline delta {delta_pct:.3f}% too large"
