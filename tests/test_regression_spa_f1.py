# -*- coding: utf-8 -*-
"""S3 regression: spa_f1 baseline 100.617s ±0.5% and nondeterminism detection."""
from __future__ import annotations

import pathlib

import numpy as np
import pytest


BASELINE_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "reference" / "spa_f1_baseline.txt"
EXPECTED_BASELINE = 100.61726451283548
TOLERANCE = 0.005  # ±0.5%


def _read_baseline() -> float:
    txt = BASELINE_PATH.read_text(encoding="utf-8").strip()
    return float(txt.split()[0])


def test_baseline_file_exists_and_value() -> None:
    assert BASELINE_PATH.exists(), f"baseline file missing: {BASELINE_PATH}"
    val = _read_baseline()
    assert abs(val - EXPECTED_BASELINE) < 1e-9, f"baseline {val} != {EXPECTED_BASELINE}"
    # also ensure raw text matches re-baselined value (first line; old 101.17 in git history)
    raw = BASELINE_PATH.read_text(encoding="utf-8").strip()
    assert raw.startswith("100.617"), f"raw baseline should start with 100.617, got {raw!r}"


def test_spa_f1_regression_within_tolerance() -> None:
    import app

    baseline = _read_baseline()
    res = app.simulate("f1", "spa")
    assert 90.0 <= res.laptime <= 110.0
    # ±0.5% check
    lo = baseline * (1 - TOLERANCE)
    hi = baseline * (1 + TOLERANCE)
    assert lo <= res.laptime <= hi, f"laptime {res.laptime} not in [{lo},{hi}] baseline {baseline} ±0.5%"
    # also check against hard-coded canonical within same tolerance (double-check file vs constant)
    lo2 = EXPECTED_BASELINE * (1 - TOLERANCE)
    hi2 = EXPECTED_BASELINE * (1 + TOLERANCE)
    assert lo2 <= res.laptime <= hi2


def test_spa_f1_nondeterminism_detection() -> None:
    import app

    r1 = app.simulate("f1", "spa")
    r2 = app.simulate("f1", "spa")
    assert abs(r1.laptime - r2.laptime) < 1e-9, f"nondeterministic laptime {r1.laptime} vs {r2.laptime}"
    np.testing.assert_allclose(np.asarray(r1.v), np.asarray(r2.v), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.s), np.asarray(r2.s), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.ax), np.asarray(r2.ax), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.ay), np.asarray(r2.ay), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.time), np.asarray(r2.time), atol=1e-9, rtol=0)
