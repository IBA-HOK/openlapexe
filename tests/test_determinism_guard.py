# -*- coding: utf-8 -*-
"""Determinism guard: 1e-9, numpy-only, solver invariant, Track.mesh roundtrip."""
from __future__ import annotations

import pathlib
import subprocess
import sys

import numpy as np
import numpy.testing as npt
import pytest


def test_determinism_1e9_spa_suzuka_variants() -> None:
    """simulate_full twice for spa/suzuka/suzuka_south/sugo_west x freq 50 + spa 100Hz only."""
    from openlapexe.solver import simulate_full

    tracks_50 = ["spa", "suzuka", "suzuka_south", "sugo_west"]
    for name in tracks_50:
        r1 = simulate_full(track_name=name, freq=50)
        r2 = simulate_full(track_name=name, freq=50)
        assert abs(float(r1.laptime) - float(r2.laptime)) < 1e-9, f"{name} laptime not deterministic 1e-9: {r1.laptime} vs {r2.laptime}"
        npt.assert_allclose(np.asarray(r1.v, dtype=float), np.asarray(r2.v, dtype=float), atol=1e-9, rtol=0, err_msg=f"{name} v not deterministic")
        npt.assert_allclose(np.asarray(r1.ax, dtype=float), np.asarray(r2.ax, dtype=float), atol=1e-9, rtol=0, err_msg=f"{name} ax not deterministic")
        npt.assert_allclose(np.asarray(r1.ay, dtype=float), np.asarray(r2.ay, dtype=float), atol=1e-9, rtol=0, err_msg=f"{name} ay not deterministic")
        npt.assert_allclose(np.asarray(r1.time, dtype=float), np.asarray(r2.time, dtype=float), atol=1e-9, rtol=0, err_msg=f"{name} time not deterministic")
        # also s deterministic
        npt.assert_allclose(np.asarray(r1.s, dtype=float), np.asarray(r2.s, dtype=float), atol=1e-9, rtol=0)

    # 100Hz only for spa to save time
    r1 = simulate_full(track_name="spa", freq=100)
    r2 = simulate_full(track_name="spa", freq=100)
    assert abs(float(r1.laptime) - float(r2.laptime)) < 1e-9
    npt.assert_allclose(np.asarray(r1.v, dtype=float), np.asarray(r2.v, dtype=float), atol=1e-9, rtol=0)
    npt.assert_allclose(np.asarray(r1.ax, dtype=float), np.asarray(r2.ax, dtype=float), atol=1e-9, rtol=0)
    npt.assert_allclose(np.asarray(r1.ay, dtype=float), np.asarray(r2.ay, dtype=float), atol=1e-9, rtol=0)
    npt.assert_allclose(np.asarray(r1.time, dtype=float), np.asarray(r2.time, dtype=float), atol=1e-9, rtol=0)


def test_numpy_only_no_scipy_matplotlib() -> None:
    """src/ must not import scipy/matplotlib; pyproject dependencies == ['numpy>=1.26']."""
    # grep check via subprocess
    # use grep -r -E pattern src ; returns 1 when no match (empty)
    result = subprocess.run(
        ["grep", "-R", "-E", r"import scipy|from scipy|import matplotlib", "src"],
        capture_output=True,
        text=True,
        cwd=str(pathlib.Path(__file__).resolve().parent.parent),
    )
    # grep exit 0 = found, 1 = no match, 2 = error; stdout should be empty for pass
    stdout = (result.stdout or "").strip()
    assert stdout == "", f"numpy-only violation: found scipy/matplotlib imports in src/: {stdout!r}"
    # ensure we didn't get grep error unrelated to missing pattern
    # exit 1 is expected when nothing found
    assert result.returncode in (0, 1), f"grep failed: {result.stderr!r}"

    # pyproject dependencies check
    pyproject = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    assert pyproject.exists(), "pyproject.toml missing"
    # parse dependencies without external toml lib via simple check + tomllib when available
    deps: list[str] | None = None
    try:
        import tomllib  # py3.11+

        data = tomllib.loads(pyproject.read_bytes().decode("utf-8"))
        deps = list(data.get("project", {}).get("dependencies", []))
    except Exception:
        # fallback: crude parse
        txt = pyproject.read_text(encoding="utf-8")
        # find dependencies = [...]
        import re

        m = re.search(r"dependencies\s*=\s*\[(.*?)\]", txt, re.S)
        if m is not None:
            inner = m.group(1)
            # extract quoted strings
            deps = re.findall(r'"([^"]+)"|\'([^\']+)\'', inner)
            deps = [a or b for a, b in deps]
        else:
            deps = None
    assert deps == ["numpy>=1.26"], f"dependencies must be ['numpy>=1.26'], got {deps!r}"


def test_solver_invariant_git_diff() -> None:
    """git diff -- src/openlapexe/solver.py is empty; check ONLY that path."""
    root = pathlib.Path(__file__).resolve().parent.parent
    result = subprocess.run(
        ["git", "diff", "--", "src/openlapexe/solver.py"],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if result.returncode != 0 and "not a git repository" in (result.stderr or "").lower():
        pytest.skip(f"not a git repo: {result.stderr!r}")
    # empty diff = invariant holds
    out = (result.stdout or "").strip()
    assert out == "", f"solver.py has uncommitted changes (invariant violated):\n{out[:2000]}"


def test_track_mesh_roundtrip_1e9_suzuka() -> None:
    """Track.mesh roundtrip 1e-9 for suzuka (deterministic mesh)."""
    from openlapexe.track import Track

    tr = Track.from_json("suzuka")
    # deterministic: same step twice yields 1e-9 identical points
    for step in (1.0, 2.0):
        m1 = tr.mesh(step)
        m2 = tr.mesh(step)
        assert m1.length_m == pytest.approx(m2.length_m, abs=1e-9)
        assert m1.points.shape == m2.points.shape
        npt.assert_allclose(m1.points, m2.points, atol=1e-9, rtol=0, err_msg=f"suzuka mesh step={step} not deterministic 1e-9")
        # s monotonic and 0..L
        s = m1.points[:, 0]
        assert abs(float(s[0])) < 1e-9
        assert abs(float(s[-1]) - float(m1.length_m)) < 1e-9
        assert np.all(np.diff(s) > 0)

    # roundtrip: mesh -> reconstruct -> mesh again should stay within 1e-9 for same step
    m = tr.mesh(2.0)
    tr2 = Track(name=m.name, length_m=m.length_m, closed_loop=m.closed_loop, points=m.points, logged=m.logged, meta=dict(m.meta) if isinstance(m.meta, dict) else {})
    m3 = tr2.mesh(2.0)
    npt.assert_allclose(m.points, m3.points, atol=1e-9, rtol=0)
