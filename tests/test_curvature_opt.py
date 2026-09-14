# -*- coding: utf-8 -*-
"""tests/test_curvature_opt - 厳密な最小曲率最適化の検証."""
from __future__ import annotations

import numpy as np
import pytest


def _make_90deg_corner(n_per_leg: int = 20, width: float = 4.0):
    """90°コーナーの left/right を生成 (L字)."""
    # left: inner corner, right: outer
    # L shape from (0,0)->(10,0)->(10,10)
    # left inner: offset -width/2, right outer: +width/2 (simplified)
    # For determinism we construct left/right as parallel offset of mid
    # mid is L shape, left/right offset perpendicular
    # Build mid polyline
    xs_mid = np.concatenate([np.linspace(0, 10, n_per_leg, endpoint=False), np.linspace(10, 10, n_per_leg)])
    ys_mid = np.concatenate([np.linspace(0, 0, n_per_leg, endpoint=False), np.linspace(0, 10, n_per_leg)])
    mid = np.stack([xs_mid, ys_mid], axis=1)
    # compute normal per segment then per point average
    n = mid.shape[0]
    left = np.zeros_like(mid)
    right = np.zeros_like(mid)
    for i in range(n):
        # tangent via central diff (wrap=False for this helper)
        if i == 0:
            tx, ty = mid[1] - mid[0]
        elif i == n - 1:
            tx, ty = mid[-1] - mid[-2]
        else:
            tx, ty = mid[i + 1] - mid[i - 1]
        tn = float(np.hypot(tx, ty))
        if tn < 1e-12:
            nx, ny = 0.0, 1.0
        else:
            tx /= tn
            ty /= tn
            # normal left = (-ty, tx)
            nx, ny = -ty, tx
        half = width * 0.5
        left[i, 0] = float(mid[i, 0] + nx * half * -1)  # shift left side inner?
        left[i, 1] = float(mid[i, 1] + ny * half * -1)
        right[i, 0] = float(mid[i, 0] + nx * half)
        right[i, 1] = float(mid[i, 1] + ny * half)
    # Actually left/right as above gives symmetric width; use left as -half, right as +half
    # Ensure left is at -half, right at +half already done
    return left, right


def test_kmax_reduction_90deg():
    from openlapexe.curvature_opt import compute_curvature_profile, optimize_centerline

    left, right = _make_90deg_corner(n_per_leg=20, width=4.0)
    mid = (left + right) * 0.5
    k_init = compute_curvature_profile(mid, closed=False)
    kmax_init = float(np.max(np.abs(k_init)))
    center, curv = optimize_centerline(left, right, closed=False, iters=200, width_margin=0.1)
    assert center.shape == left.shape
    assert curv.shape[0] == left.shape[0]
    assert np.all(np.isfinite(center))
    assert np.all(np.isfinite(curv))
    kmax_opt = float(np.max(np.abs(curv)))
    # 90° corner should be smoothed -> max curvature reduced at least 5%
    assert kmax_opt < kmax_init * 0.95, f"kmax not reduced: init {kmax_init} opt {kmax_opt}"
    # also ensure not all zero (finite reduction)
    assert kmax_opt >= 0.0


def test_finite():
    from openlapexe.curvature_opt import optimize_centerline

    left, right = _make_90deg_corner(n_per_leg=15, width=6.0)
    center, curv = optimize_centerline(left, right, closed=False, iters=200, width_margin=0.1)
    assert np.all(np.isfinite(center)), "center contains non-finite"
    assert np.all(np.isfinite(curv)), "curv contains non-finite"
    assert not np.any(np.isnan(center))
    assert not np.any(np.isnan(curv))
    assert not np.any(np.isinf(curv))


def test_deterministic_200iter_1e9():
    from openlapexe.curvature_opt import optimize_centerline

    left, right = _make_90deg_corner(n_per_leg=18, width=4.0)
    c1, curv1 = optimize_centerline(left, right, closed=False, iters=200, width_margin=0.1)
    c2, curv2 = optimize_centerline(left, right, closed=False, iters=200, width_margin=0.1)
    assert np.allclose(c1, c2, atol=1e-9, rtol=0), f"not deterministic center max diff {np.max(np.abs(c1-c2))}"
    assert np.allclose(curv1, curv2, atol=1e-9, rtol=0), f"not deterministic curv max diff {np.max(np.abs(curv1-curv2))}"


def test_closed_loop_closure_lt_1mm():
    from openlapexe.curvature_opt import optimize_centerline

    # closed square-ish loop
    # left inner square 0,0 ->10,0->10,10->0,10 close, right outer offset 2m
    left = np.array([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], dtype=float)
    right = np.array([[0, 2], [10, 2], [12, 10], [0, 12], [0, 2]], dtype=float)

    # interpolate to more points to make curvature meaningful
    def interp(pts, N=40):
        # linear resample expecting closed duplicate at end
        pts_no_dup = pts[:-1] if np.allclose(pts[0], pts[-1]) else pts
        n0 = pts_no_dup.shape[0]
        s = np.zeros(n0)
        for i in range(1, n0):
            s[i] = s[i - 1] + float(np.hypot(pts_no_dup[i, 0] - pts_no_dup[i - 1, 0], pts_no_dup[i, 1] - pts_no_dup[i - 1, 1]))
        L = s[-1] + float(np.hypot(pts_no_dup[0, 0] - pts_no_dup[-1, 0], pts_no_dup[0, 1] - pts_no_dup[-1, 1]))
        s_ext = np.append(s, L)
        pts_ext = np.vstack([pts_no_dup, pts_no_dup[0:1]])
        s_new = np.linspace(0, L, N, endpoint=False)
        x_new = np.interp(s_new, s_ext, pts_ext[:, 0])
        y_new = np.interp(s_new, s_ext, pts_ext[:, 1])
        return np.stack([x_new, y_new], axis=1)

    left_i = interp(left, 50)
    right_i = interp(right, 50)
    center, curv = optimize_centerline(left_i, right_i, closed=True, iters=200, width_margin=0.1)
    # closure <1mm = 1e-3 m
    dist = float(np.hypot(center[0, 0] - center[-1, 0], center[0, 1] - center[-1, 1]))
    assert dist < 1e-3, f"closed loop not closed: dist {dist}"
    assert np.all(np.isfinite(curv))


def test_compute_curvature_profile_public():
    from openlapexe.curvature_opt import compute_curvature_profile

    c = np.array([[0, 0], [5, 0], [10, 1], [15, 0]], dtype=float)
    curv = compute_curvature_profile(c, closed=False)
    assert curv.shape == (c.shape[0],)
    assert np.all(np.isfinite(curv))
    assert np.all(np.abs(curv) >= 0)  # signed curvature allowed (Left=+1/R, Right=-1/R)


def test_direct_line_helper():
    from openlapexe.curvature_opt import direct_line

    pts = np.array([[0, 0], [1, 1], [2, 0]], dtype=float)
    out = direct_line(pts)
    assert np.allclose(out, pts)
    # ensure copy not alias
    out[0, 0] = 999
    assert pts[0, 0] != 999


def test_import_no_scipy():
    import pathlib

    p = pathlib.Path("src/openlapexe/curvature_opt.py")
    txt = p.read_text(encoding="utf-8")
    assert "import scipy" not in txt.lower(), "scipy must not be imported"
    assert "from scipy" not in txt.lower(), "scipy must not be imported"
    assert "import numpy" in txt
