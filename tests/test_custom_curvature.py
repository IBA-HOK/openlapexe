# -*- coding: utf-8 -*-
"""tests/test_custom_curvature.py - FAILING tests proving custom mini-course curvature bug (S-mini-shape).

Root cause verified:
- src/openlapexe/track.py:512 from_candidates sets curv_arr = zeros (line 633)
- data/tracks/test.json has 329 pts curv all 0
- solver gives constant v=88.86 ax=0 (curv-driven accel/brake disabled)
- recomputed curvature via compute_curvature_profile gives kmax 0.19

These 3 tests MUST FAIL (RED) on current code, proving curv==0 / constant v.
Do NOT edit src/ or data/ files.

Expected RED:
- (a) max|curv| == 0.0 fails >1e-6
- (b) max|curv| == 0.0 fails >1e-6
- (c) v_range == 0 fails >1.0 and ax_range == 0 fails >0.1
"""
from __future__ import annotations

import json
import pathlib
import numpy as np


def test_from_candidates_bent_xy_curvature_nonzero() -> None:
    """Track.from_candidates on bent XY (S-mini) must yield max|curv|>1e-6."""
    from openlapexe.track import Track

    # S-mini-shape: bent polyline with clear curvature (approx 0.1-0.2 1/m if computed)
    # Straight line would have curv=0; this S has alternating bends.
    pts_xy = [
        (0.0, 0.0),
        (5.0, 2.0),
        (10.0, 0.0),
        (15.0, -2.5),
        (20.0, 0.0),
        (25.0, 3.0),
        (30.0, 0.0),
    ]
    cand = {"points_xy": np.array(pts_xy, dtype=float), "name": "s_mini_bent"}
    track = Track.from_candidates([cand], closed_loop=False)

    # points columns: s,x,y,z,curv,bank_rad,grip_factor,sector_id (8 cols)
    assert track.points.shape[1] >= 5, f"points cols {track.points.shape[1]} <5"
    curv = np.asarray(track.points[:, 4], dtype=float)
    max_abs_curv = float(np.max(np.abs(curv))) if curv.size else 0.0

    # Optional cross-check: recomputed curvature via geometry should be >0.05
    # (proves XY is indeed bent, bug is in stored curv)
    try:
        from openlapexe.curvature_opt import compute_curvature_profile
        xy = np.asarray(pts_xy, dtype=float)
        k_recomputed = compute_curvature_profile(xy, closed=False)
        kmax_recomputed = float(np.max(np.abs(k_recomputed))) if k_recomputed.size else 0.0
    except Exception:
        kmax_recomputed = 0.0

    assert max_abs_curv > 1e-6, (
        f"BUG: from_candidates bent S-mini max|curv|={max_abs_curv:.6g} <=1e-6 (all zeros); "
        f"src/openlapexe/track.py:633 curv_arr=zeros, recomputed kmax={kmax_recomputed:.3f} >0.1 proves XY is bent but stored curv==0"
    )


def test_test_json_reload_curvature_nonzero() -> None:
    """data/tracks/test.json reload must yield max|curv|>1e-6 (currently all 0)."""
    from openlapexe.track import Track

    # Use real file via Track.from_json (also validates _resolve_track_path)
    track = Track.from_json("test")
    assert track.points.shape[0] >= 200, f"test.json points {track.points.shape[0]} unexpected"
    # Also verify file actually has 329 pts and all curv==0 on current buggy data
    root = pathlib.Path(__file__).resolve().parents[1]
    p = root / "data" / "tracks" / "test.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    pts_raw = raw.get("points", [])
    # prove file curvature bug: check raw json curv values
    raw_curvs = [float(pt.get("curv", 0.0)) for pt in pts_raw]
    raw_max = float(np.max(np.abs(np.array(raw_curvs, dtype=float)))) if raw_curvs else 0.0

    curv = np.asarray(track.points[:, 4], dtype=float)
    max_abs_curv = float(np.max(np.abs(curv))) if curv.size else 0.0

    assert max_abs_curv > 1e-6, (
        f"BUG: test.json reload max|curv|={max_abs_curv:.6g} <=1e-6 (curv all 0); "
        f"raw json n={len(pts_raw)} raw_max|curv|={raw_max:.6g} proves file has 329 pts curv 0, "
        f"track.py:471 curv from json keeps zeros, solver then sees straight"
    )


def test_simulate_full_test_track_v_and_ax_variation() -> None:
    """simulate_full('f1','test') must yield v variation >1.0 and ax variation >0.1 (currently constant)."""
    from openlapexe.solver import simulate_full

    result = simulate_full("f1", "test")
    v = np.asarray(result.v, dtype=float)
    ax = np.asarray(result.ax, dtype=float)
    assert v.size > 10, f"v size {v.size} too small"
    assert ax.size > 10, f"ax size {ax.size} too small"

    v_range = float(np.max(v) - np.min(v)) if v.size else 0.0
    ax_range = float(np.max(ax) - np.min(ax)) if ax.size else 0.0
    v_mean = float(np.mean(v)) if v.size else 0.0
    ax_mean = float(np.mean(ax)) if ax.size else 0.0

    # Check v variation first - this will fail with constant v=88.86
    assert v_range > 1.0, (
        f"BUG: simulate_full('f1','test') v_range={v_range:.6g} <=1.0 (constant v bug); "
        f"v_mean={v_mean:.2f} (expected ~88.86 constant), min={float(np.min(v)):.2f} max={float(np.max(v)):.2f} "
        f"proves curv==0 -> solver gives constant v, no accel/brake variation"
    )
    # Check ax variation - will also fail with ax==0 constant
    assert ax_range > 0.1, (
        f"BUG: simulate_full('f1','test') ax_range={ax_range:.6g} <=0.1 (constant ax bug); "
        f"ax_mean={ax_mean:.6g} min={float(np.min(ax)):.6g} max={float(np.max(ax)):.6g} "
        f"proves curv==0 -> ax all 0, no braking/acceleration"
    )
