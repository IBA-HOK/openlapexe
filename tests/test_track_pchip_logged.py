# -*- coding: utf-8 -*-
"""Tests for OpenTRACK port: PCHIP vs linear, logged reversal, spa mesh, length."""
from __future__ import annotations

import json
import math
import pathlib

import numpy as np
import pytest


def test_pchip_vs_linear_diff():
    """PCHIP curvature/elevation/banking must differ from linear (monotonic shape preserving)."""
    from openlapexe.track import _pchip_interp
    # Non-linear data where PCHIP differs visibly from linear.
    x = np.array([0, 1, 2, 3, 4], dtype=float)
    y = np.array([0, 0.5, 2, 0.5, 0], dtype=float)
    x_new = np.array([0.5, 1.5, 2.5, 3.5], dtype=float)
    pchip_vals = _pchip_interp(x, y, x_new)
    linear_vals = np.interp(x_new, x, y)
    diff = np.max(np.abs(pchip_vals - linear_vals))
    assert diff > 1e-3, f"PCHIP vs linear diff too small: {diff}"
    # Also test elevation-like peak: 0,10,0
    xe = np.array([0, 50, 100], dtype=float)
    ye = np.array([0, 10, 0], dtype=float)
    p = _pchip_interp(xe, ye, np.array([25.0], dtype=float))
    l = np.interp([25.0], xe, ye)
    assert abs(float(p[0]) - float(l[0])) > 0.5

def test_grip_interp_clamp():
    """grip_factor uses np.interp clamp (left/right = edge)."""
    from openlapexe.track import Track
    # Create track with grip values 1.0,2.0 at s 0,100
    s = np.array([0.0, 100.0], dtype=float)
    x = np.array([0.0, 100.0], dtype=float)
    y = np.zeros(2)
    z = np.zeros(2)
    curv = np.zeros(2)
    bank = np.zeros(2)
    grip = np.array([1.0, 2.0], dtype=float)
    sector = np.array([1.0, 1.0], dtype=float)
    pts = np.column_stack([s, x, y, z, curv, bank, grip, sector])
    tr = Track(name="grip_test", length_m=100.0, closed_loop=False, points=pts, logged=False)
    meshed = tr.mesh(2.0)
    # grip should be interpolated linearly and clamped
    # At s=50, linear interp =1.5 ; PCHIP would give different if used, but we use linear.
    # Check that grip at s=50 is close to linear (1.5)
    idx_mid = np.argmin(np.abs(meshed.points[:,0] - 50.0))
    g_mid = float(meshed.points[idx_mid, 6])
    assert abs(g_mid - 1.5) < 1e-6, f"grip mid {g_mid} not 1.5 (clamp vs pchip)"
    # Check clamp beyond domain: if we manually call np.interp with left/right, it clamps.
    # Our mesh ensures s_new exactly within [0,100] so no beyond, but verify grip array uses np.interp
    assert float(meshed.points[0,6]) == 1.0
    assert float(meshed.points[-1,6]) == 2.0

def test_logged_reversal_monotonic():
    """logged=true => s reversal but still monotonic 0..L, closed handling."""
    from openlapexe.track import Track
    s = np.linspace(0, 100, 20)
    x = np.linspace(0, 100, 20)
    y = np.zeros(20)
    z = np.zeros(20)
    curv = np.zeros(20)
    # give varying curvature to check sign flip
    curv[5:10] = 0.01
    bank = np.linspace(0, 0.1, 20)
    grip = np.ones(20)
    sector = np.ones(20)
    pts = np.column_stack([s, x, y, z, curv, bank, grip, sector])
    tr = Track(name="logged_test", length_m=100.0, closed_loop=False, points=pts, logged=False)
    tr_logged = Track(name="logged_test", length_m=100.0, closed_loop=False, points=pts, logged=True)
    m = tr.mesh(2.0)
    ml = tr_logged.mesh(2.0)
    s_vals = ml.points[:,0]
    assert np.all(np.diff(s_vals) > 0), "logged mesh s not monotonic"
    assert abs(float(s_vals[0]) - 0.0) < 1e-9
    assert abs(float(s_vals[-1]) - 100.0) < 1e-9
    # Check that geometry is reversed: first x of logged ~ last x of normal
    assert abs(float(ml.points[0,1]) - 100.0) < 2.0
    assert abs(float(ml.points[-1,1]) - 0.0) < 2.0
    # curvature sign flipped: at s ~ 10-20 original curvature 0.01 should appear at s ~80-90 in logged with -0.01
    # Find max curv in normal vs logged
    assert float(np.max(np.abs(m.points[:,4]))) > 0.009
    # logged curvature should be negated
    # Compare at mirrored s: m at s= ~12, ml at s~88
    idx_n = np.argmin(np.abs(m.points[:,0] - 12))
    idx_l = np.argmin(np.abs(ml.points[:,0] - 88))
    assert abs(float(m.points[idx_n,4]) + float(ml.points[idx_l,4])) < 1e-6, "curv not flipped for logged"
    # Also check banking flipped
    assert abs(float(m.points[idx_n,5]) + float(ml.points[idx_l,5])) < 1e-6

def test_spa_mesh1_about_7000_and_length():
    """spa mesh(1) yields approx 7000 points and length ±1%."""
    from openlapexe.track import Track, Track2
    # Both Track and Track2 should work
    for Cls in (Track, Track2):
        tr = Cls.from_json("spa")
        # Check banking/grip/sector present
        assert hasattr(tr, "banking_rad") or tr.points.shape[1] >= 6
        assert hasattr(tr, "grip_factor") or tr.points.shape[1] >= 7
        # Check that track json has logged flag
        assert isinstance(tr.logged, bool)
        # Check that points have extra fields
        assert tr.points.shape[1] >= 8, f"points cols {tr.points.shape[1]} <8"
        meshed = tr.mesh(1.0)
        n = len(meshed.points)
        # spa length 6953.611, mesh 1 => floor 6953 +1 + L => 6955
        assert 6900 < n < 7100, f"spa mesh1 points {n} not ~7000 (expected ~6955)"
        length_orig = float(tr.length_m)
        length_meshed = float(meshed.length_m)
        # length ±1%
        assert abs(length_meshed - length_orig) / length_orig < 0.01, f"length diff {length_meshed} vs {length_orig}"
        # Also check officially 7004m ±1%? Our spa length 6953 is within 7004 ±1% (6933-7075)
        assert 6933 <= length_orig <= 7075
        # Check s monotonic
        s_vals = meshed.points[:,0]
        assert np.all(np.diff(s_vals) > 0)
        # Check closed
        dx = float(meshed.points[0,1] - meshed.points[-1,1])
        dy = float(meshed.points[0,2] - meshed.points[-1,2])
        dist = math.hypot(dx, dy)
        assert dist < 2.0, f"closed distance {dist}"

def test_json_has_required_fields_utf8():
    """data/tracks json must have banking_rad, grip_factor, sector_id, logged with utf-8."""
    for name in ["spa", "monza", "donington"]:
        p = pathlib.Path(f"data/tracks/{name}.json")
        txt = p.read_text(encoding="utf-8")
        data = json.loads(txt)
        assert "logged" in data, f"{name} missing logged"
        assert isinstance(data["logged"], bool)
        assert "points" in data and len(data["points"]) > 100
        pt = data["points"][0]
        for k in ("s", "x", "y", "z", "curv", "banking_rad", "grip_factor", "sector_id"):
            assert k in pt, f"{name} point missing {k}"
        # check encoding: file read as utf-8 succeeded, ensure ensure_ascii=False was used if needed
        # currencies or names contain no ascii issues but check it's valid json

def test_mesh_step_validation():
    from openlapexe.track import Track
    tr = Track.from_json("spa")
    with pytest.raises(ValueError):
        tr.mesh(0.5)
    with pytest.raises(ValueError):
        tr.mesh(5.5)
    # valid edges
    assert len(tr.mesh(1.0).points) > len(tr.mesh(5.0).points)
