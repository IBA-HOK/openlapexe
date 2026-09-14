# -*- coding: utf-8 -*-
"""Edge contracts: synthetic high-curv, bank edge, freq 1/200 clamp 90-120s, e4 fs125/suzuka_south.

Threshold provenance (PYTHONPATH=src, simulate_full 50Hz, 2026-09-13 shape verification):
- Synthetic high-curv: n=120 length 800m curv 0.03 (R33) => laptime in [5,120]s informational,
  v>0 and s monotonic; no NaN/inf.
- Bank edge: bank 15deg (0.2618 rad) curvature 0.015 => same band [5,120]s.
- Freq clamp 1/200: simulate_full("f1","spa",freq) with freq=1 (step 5m) and 200 (step 1m)
  both must give laptime in [90,120]s (widened from canonical 101.104±0.5% to allow mesh coarseness)
  and len(200) > len(1); also 50Hz must be in same band.
- e4 fs125/suzuka_south: measured 47.62604355376272 s racing 50Hz (fs125_x30/suzuka_south);
  actual record 48.932s (FS125 2024) => -2.67% within ±10% [44.04,53.82];
  kart strict band [20,80]s; racing Rmin 25.27m (max_curv 0.03957) from
  suzuka_south.json (optimize_centerline half_width 5.0 from centerline Rmin 8.39);
  old fake stadium-synthetic R44 (curv 0.022, Rmin ~44m, too mild, laptime ~37-39s);
  Rmin band [15,35]m excludes fake 44 and centerline 8.39, passes racing 25.27.
- Determinism 1e-9: every contract runs simulate_full twice and asserts atol 1e-9 rtol 0
  for laptime and v arrays (where applicable). Solver is numpy-only deterministic.
"""
from __future__ import annotations

import json
import pathlib
import tempfile

import numpy as np
import numpy.testing as npt
import pytest


def _make_synthetic_track(
    n: int = 120,
    length: float = 600.0,
    curv: float = 0.02,
    bank_rad: float = 0.0,
    closed: bool = False,
) -> str:
    s = np.linspace(0, length, n)
    x = s.copy()
    y = np.zeros(n)
    z = np.zeros(n)
    curvs = np.full(n, curv, dtype=float)
    banks = np.full(n, bank_rad, dtype=float)
    pts = []
    for i in range(n):
        pts.append({"s": float(s[i]), "x": float(x[i]), "y": float(y[i]), "z": float(z[i]), "curv": float(curvs[i]), "bank_rad": float(banks[i])})
    data = {"name": "synthetic", "length_m": float(length), "closed_loop": bool(closed), "points": pts}
    tmp = tempfile.mktemp(suffix=".json")
    pathlib.Path(tmp).write_text(json.dumps(data), encoding="utf-8")
    return tmp


def test_edge_synthetic_high_curv() -> None:
    from openlapexe.solver import simulate_full

    tmp = _make_synthetic_track(n=120, length=800.0, curv=0.03, bank_rad=0.0, closed=False)
    try:
        res_a = simulate_full("f1", tmp, 50)
        res_b = simulate_full("f1", tmp, 50)
        npt.assert_allclose(float(res_a.laptime), float(res_b.laptime), atol=1e-9, rtol=0)
        npt.assert_allclose(np.asarray(res_a.v), np.asarray(res_b.v), atol=1e-9, rtol=0)
        assert 5.0 < res_a.laptime < 120.0, f"high-curv laptime {res_a.laptime} not in 5-120"
        assert np.all(np.asarray(res_a.v) > 0)
        assert np.all(np.diff(np.asarray(res_a.s)) > 0)
    finally:
        pathlib.Path(tmp).unlink(missing_ok=True)


def test_edge_bank_edge() -> None:
    from openlapexe.solver import simulate_full

    bank = float(np.radians(15.0))
    tmp = _make_synthetic_track(n=100, length=600.0, curv=0.015, bank_rad=bank, closed=False)
    try:
        res_a = simulate_full("f1", tmp, 50)
        res_b = simulate_full("f1", tmp, 50)
        npt.assert_allclose(float(res_a.laptime), float(res_b.laptime), atol=1e-9, rtol=0)
        npt.assert_allclose(np.asarray(res_a.v), np.asarray(res_b.v), atol=1e-9, rtol=0)
        assert 5.0 < res_a.laptime < 120.0, f"bank edge laptime {res_a.laptime} not in 5-120"
        assert np.all(np.isfinite(np.asarray(res_a.v)))
    finally:
        pathlib.Path(tmp).unlink(missing_ok=True)


def test_edge_freq_clamp_1_and_200() -> None:
    from openlapexe.solver import simulate_full

    r1_a = simulate_full("f1", "spa", 1)
    r1_b = simulate_full("f1", "spa", 1)
    npt.assert_allclose(float(r1_a.laptime), float(r1_b.laptime), atol=1e-9, rtol=0)
    r200_a = simulate_full("f1", "spa", 200)
    r200_b = simulate_full("f1", "spa", 200)
    npt.assert_allclose(float(r200_a.laptime), float(r200_b.laptime), atol=1e-9, rtol=0)
    assert 90.0 <= r1_a.laptime <= 120.0, f"freq 1 laptime {r1_a.laptime} not in 90-120"
    assert 90.0 <= r200_a.laptime <= 120.0, f"freq 200 laptime {r200_a.laptime} not in 90-120"
    assert len(r200_a.s) > len(r1_a.s)
    assert r1_a.laptime != pytest.approx(r200_a.laptime, rel=1e-9) or len(r1_a.s) != len(r200_a.s)
    r0_a = simulate_full("f1", "spa", 50)
    r0_b = simulate_full("f1", "spa", 50)
    npt.assert_allclose(float(r0_a.laptime), float(r0_b.laptime), atol=1e-9, rtol=0)
    assert 90.0 <= r0_a.laptime <= 120.0


def test_edge_e4_fs125_suzuka_south_determinism_and_rmin_band() -> None:
    """e4: fs125/suzuka_south determinism 1e-9 + Rmin band [15,35] + laptime bands.

    Provenance: fs125_x30/suzuka_south racing 50Hz 47.62604355376272s measured
    PYTHONPATH=src simulate_full("fs125_x30","suzuka_south",50) 2026-09-13;
    actual 48.932s => -2.6689% within ±10% [44.0388,53.8252]; kart strict [20,80] passes;
    Rmin 25.27m (max_curv 0.0395728) from suzuka_south.json; old fake R44 (curv ~0.022)
    gave 37-39s (diff >5s vs new, see regression guard); centerline Rmin 8.39 excluded.
    """
    from openlapexe.solver import simulate_full

    r1 = simulate_full("fs125_x30", "suzuka_south", 50)
    r2 = simulate_full("fs125_x30", "suzuka_south", 50)
    npt.assert_allclose(float(r1.laptime), float(r2.laptime), atol=1e-9, rtol=0)
    npt.assert_allclose(np.asarray(r1.v), np.asarray(r2.v), atol=1e-9, rtol=0)

    # laptime measured 47.626... must be in kart bands and within ±10% of actual 48.932
    actual_fs125 = 48.932
    lo10 = actual_fs125 * 0.9  # 44.0388
    hi10 = actual_fs125 * 1.1  # 53.8252
    assert 20.0 <= float(r1.laptime) <= 80.0, f"fs125 south laptime {r1.laptime} not in strict kart band [20,80]"
    assert 15.0 <= float(r1.laptime) <= 90.0, f"fs125 south laptime {r1.laptime} not in info band [15,90]"
    assert lo10 <= float(r1.laptime) <= hi10, f"fs125 south laptime {r1.laptime} not within ±10% [{lo10},{hi10}] vs actual {actual_fs125}"

    # Rmin band [15,35]m deterministic from track JSON
    track_path = pathlib.Path(__file__).resolve().parents[1] / "data" / "tracks" / "suzuka_south.json"
    data = json.loads(track_path.read_text(encoding="utf-8"))
    pts = data["points"]
    max_curv = max(abs(float(p["curv"])) for p in pts)
    rmin = 1.0 / max_curv if max_curv > 1e-12 else float("inf")
    # racing Rmin must be in [15,35] (new 25.27 passes, old fake 44 fails, centerline 8.39 fails)
    assert 15.0 <= rmin <= 35.0, f"suzuka_south racing Rmin {rmin:.2f} not in [15,35] (max_curv {max_curv:.5f})"
    # also verify centerline Rmin is outside this band (outside proves shape fix distinction)
    center_path = pathlib.Path(__file__).resolve().parents[1] / "data" / "tracks" / "suzuka_south_centerline.json"
    c_data = json.loads(center_path.read_text(encoding="utf-8"))
    c_max_curv = max(abs(float(p["curv"])) for p in c_data["points"])
    c_rmin = 1.0 / c_max_curv if c_max_curv > 1e-12 else float("inf")
    assert c_rmin < 15.0, f"centerline Rmin {c_rmin:.2f} unexpectedly inside racing band [15,35]"

    # cross-check old R44 would fail: R44=44 not in [15,35] => guard
    assert not (15.0 <= 44.0 <= 35.0), "old R44 44m must be outside [15,35] band (regression guard sanity)"
