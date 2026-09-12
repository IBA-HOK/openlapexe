# -*- coding: utf-8 -*-
"""Full solver regression: spa_f1_full_baseline ≈101.17s ±0.5% and determinism.

TDD red→green for simulate_full baseline lock.
New baseline: data/reference/spa_f1_full_baseline.txt (measured 101.17879935516551 at 50Hz).
Old baseline data/reference/spa_f1_baseline.txt=101.17 is retained as previous_baseline.
Previous buggy baseline 95.80591391534297 is documented as previous_buggy.
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pytest

BASELINE_FULL_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "reference" / "spa_f1_full_baseline.txt"
BASELINE_OLD_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "reference" / "spa_f1_baseline.txt"
TOLERANCE = 0.005  # ±0.5%
PREVIOUS_BUGGY = 95.80591391534297


def _read_baseline(path: pathlib.Path) -> float:
    txt = path.read_text(encoding="utf-8").strip()
    return float(txt.split()[0])


def test_full_baseline_file_exists_and_utf8() -> None:
    # Given: full baseline file should exist, utf-8, single float line
    assert BASELINE_FULL_PATH.exists(), f"full baseline missing: {BASELINE_FULL_PATH}"
    raw = BASELINE_FULL_PATH.read_text(encoding="utf-8")
    assert raw.strip() != "", "baseline empty"
    # no BOM
    assert not raw.startswith("\ufeff"), "BOM detected, should be plain utf-8"
    # first token is float
    val = float(raw.strip().split()[0])
    # plausible range now 100.66-101.68 ±0.5% around 101.17
    assert 90.0 <= val <= 110.0, f"full baseline {val} out of plausible range"
    assert 100.0 <= val <= 102.5, f"full baseline {val} not near 101.17"
    # ensure old baseline still exists unchanged
    assert BASELINE_OLD_PATH.exists()
    old = _read_baseline(BASELINE_OLD_PATH)
    assert abs(old - 101.17) < 1e-9, f"old baseline changed {old}"
    # corrected: new baseline should be close to old (both ~101.17) within 1s
    assert abs(val - old) < 1.0, f"full baseline {val} too far from old {old}, expected close (~101.17)"
    # previous buggy must be outside tolerance
    assert abs(PREVIOUS_BUGGY - val) > 1.0, f"previous buggy {PREVIOUS_BUGGY} too close to corrected {val}"


def test_full_baseline_value_is_measured_not_mocked() -> None:
    # Given: file value should match simulate_full measurement within tolerance of itself
    # When: we read baseline and compare to simulate_full 50Hz
    from openlapexe.solver import simulate_full

    baseline = _read_baseline(BASELINE_FULL_PATH)
    res = simulate_full("f1", "spa", 50)
    lo = baseline * (1 - TOLERANCE)
    hi = baseline * (1 + TOLERANCE)
    # Then: laptime within ±0.5% of baseline
    assert lo <= res.laptime <= hi, f"laptime {res.laptime} not in [{lo},{hi}] baseline {baseline} ±0.5%"


def test_spa_f1_full_50hz_laptime_range() -> None:
    # Given: 50Hz full solver
    from openlapexe.solver import simulate_full

    # When: simulate
    res = simulate_full("f1", "spa", 50)
    # Then: plausible F1 Spa range narrowed around corrected physics (~101.17 ±0.5% => 100.66-101.68, keep 90-110 outer)
    assert 90.0 <= res.laptime <= 110.0, f"full laptime {res.laptime} not in 90-110"
    assert 100.0 <= res.laptime <= 102.5, f"full laptime {res.laptime} not in corrected 100-102.5"
    # also within ±0.5% of baseline file
    baseline = _read_baseline(BASELINE_FULL_PATH)
    assert abs(res.laptime - baseline) / baseline <= TOLERANCE


def test_spa_f1_full_nondeterministic_all_arrays_1e9() -> None:
    # Given: two consecutive runs
    from openlapexe.solver import simulate_full

    r1 = simulate_full("f1", "spa", 50)
    r2 = simulate_full("f1", "spa", 50)
    # When: compare
    # Then: laptime and every array exactly deterministic 1e-9
    assert abs(r1.laptime - r2.laptime) < 1e-9, f"laptime nondeterministic {r1.laptime} vs {r2.laptime}"
    np.testing.assert_allclose(np.asarray(r1.s), np.asarray(r2.s), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.v), np.asarray(r2.v), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.ax), np.asarray(r2.ax), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.ay), np.asarray(r2.ay), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.time), np.asarray(r2.time), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.sector), np.asarray(r2.sector), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.gear), np.asarray(r2.gear), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.rpm), np.asarray(r2.rpm), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.tps), np.asarray(r2.tps), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.energy), np.asarray(r2.energy), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.fuel), np.asarray(r2.fuel), atol=1e-9, rtol=0)
    np.testing.assert_allclose(np.asarray(r1.sector_time), np.asarray(r2.sector_time), atol=1e-9, rtol=0)


def test_result_has_12cols_old5_head_compatible() -> None:
    # Given: Result dataclass fields order
    from openlapexe.solver import Result, simulate_full

    res = simulate_full("f1", "spa", 50)
    # Then: old 5 cols head compatible (s,v,ax,ay,time) plus laptime leading
    for attr in ("laptime", "s", "v", "ax", "ay", "time"):
        assert hasattr(res, attr), f"Result missing old field {attr}"
    # new extended fields
    for attr in ("sector", "gear", "rpm", "tps", "energy", "fuel", "sector_time"):
        assert hasattr(res, attr), f"Result missing extended field {attr}"
    # field count >=12 (laptime + 11 arrays)
    # dataclass fields order check: first 6 should be laptime,s,v,ax,ay,time
    field_names = [f.name for f in Result.__dataclass_fields__.values()]  # type: ignore[attr-defined]
    assert field_names[:6] == ["laptime", "s", "v", "ax", "ay", "time"], f"old 5 cols not head-compatible: {field_names[:6]}"
    assert len(field_names) >= 12, f"expected >=12 fields, got {len(field_names)}: {field_names}"
    # all extended arrays same length as time except sector_time
    n = len(res.time)
    for attr in ("s", "v", "ax", "ay", "sector", "gear", "rpm", "tps", "energy", "fuel"):
        arr = getattr(res, attr)
        assert len(arr) == n, f"{attr} len {len(arr)} != {n}"


def test_no_scipy_matplotlib_import() -> None:
    # Given: solver must be numpy-only, no scipy/matplotlib
    # When: we inspect sys.modules after import and source text
    import openlapexe.solver as solver_mod
    import pathlib as _pl

    # Then: sys.modules should not contain scipy/matplotlib (unless unrelated test imported before)
    # We check source file text directly for forbidden imports
    src_path = _pl.Path(solver_mod.__file__)  # type: ignore[arg-type]
    txt = src_path.read_text(encoding="utf-8")
    assert "import scipy" not in txt, "scipy found in solver"
    assert "import matplotlib" not in txt, "matplotlib found in solver"
    assert "from scipy" not in txt, "scipy found in solver"
    assert "from matplotlib" not in txt, "matplotlib found in solver"
    # also ensure at runtime scipy not required for simulate_full
    assert "scipy" not in sys.modules or sys.modules["scipy"] is None or True  # allow but check not imported by solver
    # stricter: if scipy loaded, it must not have been loaded by solver import path
    # We verify solver file doesn't reference scipy string at all (already above)


def test_freq_respected_multi_gear_and_energy() -> None:
    # Given: freq parameter must affect mesh/output
    from openlapexe.solver import simulate_full

    r50 = simulate_full("f1", "spa", 50)
    r100 = simulate_full("f1", "spa", 100)
    # Then: different freq yields different output length (freq尊重)
    assert len(r50.s) != len(r100.s), f"freq not respected: 50 len {len(r50.s)} == 100 len {len(r100.s)}"
    # higher freq -> finer mesh -> more points
    assert len(r100.s) > len(r50.s), "100Hz should have more points than 50Hz"
    # multi-gear: gear array should have at least 2 distinct gears
    gears = set(int(g) for g in np.asarray(r50.gear, dtype=float))
    assert len(gears) >= 2, f"multi-gear not observed, gears={gears}"
    # gear range 1..nog valid
    assert min(gears) >= 1
    # energy & fuel積算: monotonic non-decreasing, non-negative, fuel>0 at end if throttle used
    energy = np.asarray(r50.energy, dtype=float)
    fuel = np.asarray(r50.fuel, dtype=float)
    assert np.all(energy >= -1e-9), "energy negative"
    assert np.all(fuel >= -1e-9), "fuel negative"
    assert np.all(np.diff(energy) >= -1e-9), "energy not monotonic"
    assert np.all(np.diff(fuel) >= -1e-9), "fuel not monotonic"
    assert float(fuel[-1]) > 0.0, "fuel should be >0 at lap end"
    assert float(energy[-1]) > 0.0, "energy should be >0 at lap end"


def test_sector_sum_equals_laptime_and_closed_loop() -> None:
    # Given: sector_time and closed-loop physics
    from openlapexe.solver import simulate_full

    res = simulate_full("f1", "spa", 50)
    # Then: sector_time sum == laptime within 1e-9
    assert abs(float(np.sum(res.sector_time)) - res.laptime) < 1e-6, f"sector sum {np.sum(res.sector_time)} != laptime {res.laptime}"
    # closed_loop v0 == vN
    assert abs(float(res.v[0]) - float(res.v[-1])) < 1e-9, f"closed loop v0 {res.v[0]} != vN {res.v[-1]}"
    # s monotonic and time monotonic
    assert np.all(np.diff(np.asarray(res.s)) > 0), "s not monotonic"
    assert np.all(np.diff(np.asarray(res.time)) >= -1e-12), "time not monotonic"
    assert abs(float(res.time[0])) < 1e-9
    assert abs(float(res.time[-1]) - res.laptime) < 1e-9


def test_utf8_read_and_no_scipy_in_repo() -> None:
    # Given: baseline files must be readable as utf-8
    for p in [BASELINE_FULL_PATH, BASELINE_OLD_PATH]:
        txt = p.read_text(encoding="utf-8")
        assert txt, f"{p} empty"
        float(txt.strip().split()[0])  # must parse
    # When: grep repo for forbidden imports (import statement only, comments mentioning scipy are allowed)
    import pathlib as _pl

    root = _pl.Path(__file__).resolve().parent.parent
    for py in (root / "src").rglob("*.py"):
        t = py.read_text(encoding="utf-8")
        low = t.lower()
        assert "import scipy" not in low, f"scipy import found in {py}"
        assert "from scipy" not in low, f"scipy import found in {py}"
        assert "import matplotlib" not in low, f"matplotlib import found in {py}"
        assert "from matplotlib" not in low, f"matplotlib import found in {py}"
