# -*- coding: utf-8 -*-
"""Regression guard: old 95.8059 outside ±0.5% of 101.104, old R44 south diff >5s vs new 47.63.

Threshold provenance (PYTHONPATH=src, simulate_full 50Hz, 2026-09-13 shape verification):
- CANONICAL 101.10435359601342 s = f1/spa racing 50Hz measured via simulate_full("f1","spa",50);
  baseline txt data/reference/spa_f1_full_baseline.txt contains same value.
  TOL 0.5% => LO 100.59883182803335 HI 101.60987536399348.
- PREVIOUS_BUGGY 95.80591391534297 s = old buggy before shape/tyre fix (centerline kink,
  low grip, conservatism) measured pre-2026-09-13; must be OUTSIDE canonical band (LO/HI)
  and differ >1s and >TOL*CANONICAL (~0.5s) to prove regression was not noise.
- FULL_BASELINE_PATH data/reference/spa_f1_full_baseline.txt must contain 101.104...
  and be inside band, differ >1s from buggy.
- OLD_BASELINE_PATH data/reference/spa_f1_baseline.txt (old shim 101.17) must be inside band
  for history; shim differs from canonical by 0.065s but still inside ±0.5%.
- Old south R44: stadium-synthetic suzuka_south racing with Rmin ~44m (curv 0.022) gave
  fs125_x30 laptime ~37-39s (representative OLD_SOUTH_R44_FS125 38.0s, also check 37.0 and 39.0)
  vs new racing Rmin 25.27m (curv 0.03957) laptime 47.62604355376272s (measured
  fs125_x30/suzuka_south 50Hz). Diff must be >5s (actual ~9.6s) to prove shape fix;
  this guards re-introduction of fake R44 geometry.
- Determinism 1e-9: every simulation contract runs simulate_full twice and asserts
  atol 1e-9 rtol 0 for laptime and v arrays. Solver numpy-only deterministic.
- No src/data-tracks/data-vehicles/docs edits; this file is test-only.
"""
from __future__ import annotations

import pathlib

import numpy as np
import numpy.testing as npt
import pytest

CANONICAL = 101.10435359601342
TOL = 0.005
LO = CANONICAL * (1 - TOL)  # 100.59883182803335
HI = CANONICAL * (1 + TOL)  # 101.60987536399348
PREVIOUS_BUGGY = 95.80591391534297
FULL_BASELINE_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "reference" / "spa_f1_full_baseline.txt"
OLD_BASELINE_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "reference" / "spa_f1_baseline.txt"

# Old south R44 representative (midpoint of 37-39s range described in task)
OLD_SOUTH_R44_FS125 = 38.0  # s, synthetic R44
OLD_SOUTH_R44_LO = 37.0
OLD_SOUTH_R44_HI = 39.0
NEW_SOUTH_FS125 = 47.62604355376272  # measured fs125_x30/suzuka_south racing 50Hz 2026-09-13


def test_old_95_outside_canonical_band() -> None:
    # determinism for canonical (two runs) + band proof
    from openlapexe.solver import simulate_full

    r1 = simulate_full("f1", "spa", 50)
    r2 = simulate_full("f1", "spa", 50)
    npt.assert_allclose(float(r1.laptime), float(r2.laptime), atol=1e-9, rtol=0)
    npt.assert_allclose(np.asarray(r1.v), np.asarray(r2.v), atol=1e-9, rtol=0)
    assert LO <= float(r1.laptime) <= HI, f"canonical laptime {r1.laptime} not in [{LO},{HI}]"
    # old buggy must be outside
    assert not (LO <= PREVIOUS_BUGGY <= HI), f"previous buggy {PREVIOUS_BUGGY} unexpectedly inside [{LO},{HI}]"
    diff = abs(PREVIOUS_BUGGY - CANONICAL)
    assert diff > 1.0, f"buggy diff {diff} not >1s"
    assert diff / CANONICAL > TOL, "buggy outside tolerance"


def test_full_baseline_differs_gt_1s_from_buggy() -> None:
    txt = FULL_BASELINE_PATH.read_text(encoding="utf-8").strip()
    val = float(txt.split()[0])
    # determinism for baseline value vs live simulate (two runs)
    from openlapexe.solver import simulate_full

    r1 = simulate_full("f1", "spa", 50)
    r2 = simulate_full("f1", "spa", 50)
    npt.assert_allclose(float(r1.laptime), float(r2.laptime), atol=1e-9, rtol=0)
    assert abs(val - PREVIOUS_BUGGY) > 1.0, f"full baseline {val} not >1s from buggy {PREVIOUS_BUGGY}"
    assert LO <= val <= HI, f"full baseline {val} not in canonical band"
    npt.assert_allclose(float(val), float(r1.laptime), atol=1e-6, rtol=0)


def test_old_shim_baseline_still_101() -> None:
    txt = OLD_BASELINE_PATH.read_text(encoding="utf-8").strip()
    old = float(txt.split()[0])
    # shim 101.17 must still be inside canonical band (history not broken)
    assert LO <= old <= HI, f"old shim {old} not in canonical band [{LO},{HI}]"
    # allow small diff vs canonical (0.065s) but still inside band
    assert abs(old - CANONICAL) < 1.0, f"old shim {old} vs canonical {CANONICAL} diff too large"


def test_old_R44_south_diff_gt_5s_vs_new_47_63() -> None:
    """Old R44 south fs125 ~37-39s vs new 47.626s diff >5s proves shape fix; also determinism 1e-9."""
    from openlapexe.solver import simulate_full

    r1 = simulate_full("fs125_x30", "suzuka_south", 50)
    r2 = simulate_full("fs125_x30", "suzuka_south", 50)
    npt.assert_allclose(float(r1.laptime), float(r2.laptime), atol=1e-9, rtol=0)
    npt.assert_allclose(np.asarray(r1.v), np.asarray(r2.v), atol=1e-9, rtol=0)
    # new measured must be near NEW_SOUTH_FS125
    npt.assert_allclose(float(r1.laptime), float(NEW_SOUTH_FS125), atol=0.02, rtol=0)
    # old R44 representative must be outside new's ±5s band and differ >5s
    for old_val in (OLD_SOUTH_R44_FS125, OLD_SOUTH_R44_LO, OLD_SOUTH_R44_HI):
        diff = abs(float(r1.laptime) - float(old_val))
        assert diff > 5.0, f"old R44 south {old_val} diff {diff:.3f}s vs new {r1.laptime:.3f}s not >5s (shape regression not detected)"
        # also prove old was too fast (below new -5)
        assert float(old_val) < float(r1.laptime) - 5.0, f"old R44 {old_val} not < new-5s {r1.laptime - 5.0}"
    # guard: new is inside kart band [20,80] and within ±10% of actual 48.932 (same as edge)
    actual = 48.932
    assert 20.0 <= float(r1.laptime) <= 80.0
    assert actual * 0.9 <= float(r1.laptime) <= actual * 1.1


def test_old_buggy_95_outside_and_new_determinism() -> None:
    """Extra determinism guard: old 95.80 vs new 101.104 distinction must survive two runs."""
    from openlapexe.solver import simulate_full

    r1 = simulate_full("f1", "spa", 50)
    r2 = simulate_full("f1", "spa", 50)
    npt.assert_allclose(float(r1.laptime), float(r2.laptime), atol=1e-9, rtol=0)
    npt.assert_allclose(float(r1.laptime), float(CANONICAL), atol=1e-6, rtol=0)
    assert PREVIOUS_BUGGY < LO, f"buggy {PREVIOUS_BUGGY} not < LO {LO}"
    assert float(r1.laptime) > HI - (HI - LO)  # trivial but ensures HI defined
    assert abs(float(r1.laptime) - PREVIOUS_BUGGY) > 5.0, "new vs buggy diff must be >5s (actual ~5.30s)"
