# -*- coding: utf-8 -*-
"""Edge contracts: synthetic high-curv, bank edge, freq 1/200 clamp 90-120s."""
from __future__ import annotations

import json
import pathlib
import tempfile

import numpy as np
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
        res = simulate_full("f1", tmp, 50)
        assert 5.0 < res.laptime < 120.0, f"high-curv laptime {res.laptime} not in 5-120"
        assert np.all(np.asarray(res.v) > 0)
        assert np.all(np.diff(np.asarray(res.s)) > 0)
    finally:
        pathlib.Path(tmp).unlink(missing_ok=True)


def test_edge_bank_edge() -> None:
    from openlapexe.solver import simulate_full

    bank = float(np.radians(15.0))
    tmp = _make_synthetic_track(n=100, length=600.0, curv=0.015, bank_rad=bank, closed=False)
    try:
        res = simulate_full("f1", tmp, 50)
        assert 5.0 < res.laptime < 120.0, f"bank edge laptime {res.laptime} not in 5-120"
        assert np.all(np.isfinite(np.asarray(res.v)))
    finally:
        pathlib.Path(tmp).unlink(missing_ok=True)


def test_edge_freq_clamp_1_and_200() -> None:
    from openlapexe.solver import simulate_full

    r1 = simulate_full("f1", "spa", 1)
    r200 = simulate_full("f1", "spa", 200)
    assert 90.0 <= r1.laptime <= 120.0, f"freq 1 laptime {r1.laptime} not in 90-120"
    assert 90.0 <= r200.laptime <= 120.0, f"freq 200 laptime {r200.laptime} not in 90-120"
    assert len(r200.s) > len(r1.s)
    assert r1.laptime != pytest.approx(r200.laptime, rel=1e-9) or len(r1.s) != len(r200.s)
    r0 = simulate_full("f1", "spa", 50)
    assert 90.0 <= r0.laptime <= 120.0
