# -*- coding: utf-8 -*-
"""Happy-path contracts: spa f1 50Hz/100Hz + app.simulate alias in 101.104 ±0.5% (racing) + spa_scaled ≈101.57 proviso.

Threshold provenance (PYTHONPATH=src, simulate_full 50Hz, 2026-09-13 shape verification):
- CANONICAL 101.10435359601342 s = f1/spa racing measured via simulate_full("f1","spa",50);
  baseline txt data/reference/spa_f1_full_baseline.txt contains same value (101.10435359601342).
  data/reference/spa_f1_baseline.txt (old shim) 101.17 kept for regression history.
- Tolerance ±0.5% => LO 100.59883182803335, HI 101.60987536399348; informational band [100,102.5]
  ensures PASS with measured 101.104 and allows tiny solver drift.
- SPA_SCALED 101.57399768357575 s = f1/spa_scaled racing 50Hz measured same method;
  proviso note: spa_scaled is optimize_centerline racing from spa_centerline (delta -0.36m,
  Rmin 17.97 vs 17.84); shape-data centerlines already radius-based so scaled gain is small
  (+0.47s vs spa). Documented as ≈101.57 ±0.5% (LO 101.066, HI 102.082) and also inside
  canonical HI 101.609; both guards PASS. See data/README.md racing vs centerline section.
- Freq mapping: 50Hz step 2.0m, 100Hz step 1.0m; 100Hz laptime must stay in same canonical band
  and have longer s array (denser mesh) but deterministic.
- Determinism 1e-9: every contract runs simulate_full twice and asserts atol 1e-9 rtol 0 for
  laptime and v arrays (numpy.testing.assert_allclose). Provenance: solver numpy-only,
  deterministic mesh + trapezoidal integration, no randomness.
"""
from __future__ import annotations

import numpy as np
import numpy.testing as npt
import pytest

CANONICAL = 101.10435359601342
TOL = 0.005
LO = CANONICAL * (1 - TOL)  # 100.59883182803335
HI = CANONICAL * (1 + TOL)  # 101.60987536399348

CANONICAL_SCALED = 101.57399768357575
LO_SCALED = CANONICAL_SCALED * (1 - TOL)  # 101.06612769510788
HI_SCALED = CANONICAL_SCALED * (1 + TOL)  # 102.08186767204362


def test_happy_spa_f1_50hz_in_band() -> None:
    from openlapexe.solver import simulate_full

    r1 = simulate_full("f1", "spa", 50)
    r2 = simulate_full("f1", "spa", 50)
    npt.assert_allclose(float(r1.laptime), float(r2.laptime), atol=1e-9, rtol=0)
    npt.assert_allclose(np.asarray(r1.v), np.asarray(r2.v), atol=1e-9, rtol=0)
    assert LO <= r1.laptime <= HI, f"50Hz laptime {r1.laptime} not in [{LO},{HI}]"
    assert 100.0 <= r1.laptime <= 102.5


def test_happy_spa_f1_100hz_same_band_and_len() -> None:
    from openlapexe.solver import simulate_full

    r50_a = simulate_full("f1", "spa", 50)
    r50_b = simulate_full("f1", "spa", 50)
    npt.assert_allclose(float(r50_a.laptime), float(r50_b.laptime), atol=1e-9, rtol=0)
    r100_a = simulate_full("f1", "spa", 100)
    r100_b = simulate_full("f1", "spa", 100)
    npt.assert_allclose(float(r100_a.laptime), float(r100_b.laptime), atol=1e-9, rtol=0)
    npt.assert_allclose(np.asarray(r100_a.v), np.asarray(r100_b.v), atol=1e-9, rtol=0)
    assert LO <= r100_a.laptime <= HI, f"100Hz laptime {r100_a.laptime} not in [{LO},{HI}]"
    assert len(r100_a.s) > len(r50_a.s), f"100Hz len {len(r100_a.s)} not > 50Hz {len(r50_a.s)}"
    assert len(r100_a.s) != len(r50_a.s)


def test_happy_app_simulate_alias_same_band() -> None:
    import app

    import numpy.testing as npt2
    from openlapexe.solver import simulate_full

    res_a = app.simulate("f1", "spa")
    res_b = app.simulate("f1", "spa")
    npt2.assert_allclose(float(res_a.laptime), float(res_b.laptime), atol=1e-9, rtol=0)
    assert LO <= res_a.laptime <= HI, f"app.simulate laptime {res_a.laptime} not in [{LO},{HI}]"
    r_full_a = simulate_full("f1", "spa", 50)
    r_full_b = simulate_full("f1", "spa", 50)
    npt2.assert_allclose(float(r_full_a.laptime), float(r_full_b.laptime), atol=1e-9, rtol=0)
    assert abs(res_a.laptime - r_full_a.laptime) < 1e-9, f"alias mismatch {res_a.laptime} vs {r_full_a.laptime}"


def test_happy_spa_scaled_approx_101_57_proviso() -> None:
    """spa_scaled ≈101.57 proviso: +0.47s vs spa due to optimize_centerline; inside scaled ±0.5% and canonical HI."""
    from openlapexe.solver import simulate_full

    r1 = simulate_full("f1", "spa_scaled", 50)
    r2 = simulate_full("f1", "spa_scaled", 50)
    npt.assert_allclose(float(r1.laptime), float(r2.laptime), atol=1e-9, rtol=0)
    npt.assert_allclose(np.asarray(r1.v), np.asarray(r2.v), atol=1e-9, rtol=0)
    # proviso: spa_scaled has its own canonical 101.5739 ±0.5%
    assert LO_SCALED <= r1.laptime <= HI_SCALED, f"spa_scaled laptime {r1.laptime} not in [{LO_SCALED},{HI_SCALED}]"
    # also inside canonical HI (since +0.47s < 0.5% *101.104 ≈0.505s, borderline but PASS measured 101.573 <101.609)
    assert r1.laptime <= HI, f"spa_scaled {r1.laptime} exceeds canonical HI {HI} proviso"
    assert 100.0 <= r1.laptime <= 102.5
    # determinism vs spa: two spa runs must differ from scaled by expected ~0.47s (proviso note)
    r_spa = simulate_full("f1", "spa", 50)
    diff = float(r1.laptime) - float(r_spa.laptime)
    assert 0.3 <= diff <= 0.7, f"spa_scaled-spa diff {diff} not in proviso [0.3,0.7] (measured ~0.47)"
