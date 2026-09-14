# -*- coding: utf-8 -*-
"""Racing line regression: X.json = racing, X_centerline.json = centerline (with suffix).

Covers ALL pairs: spa/monza/donington/suzuka/sugo_west/suzuka_south/test/asete
- file existence
- racing length within ±1.5% of centerline
- racing f1 laptime < centerline f1 laptime (all pairs now pass; south was fixed 2026-09-13)
- determinism 1e-9 on one pair (spa f1 50Hz)
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import numpy.testing as npt

ROOT = pathlib.Path(__file__).resolve().parent.parent
TRACKS = ROOT / "data" / "tracks"

# All 8 base names per spec
PAIRS = ["spa", "monza", "donington", "suzuka", "sugo_west", "suzuka_south", "test", "asete"]

# Updated 2026-09-13: south redigitized to true 11-corner geometry (Rmin 8.4 center, 25.3 racing), now f1 racing 21.18 < center 23.50, no longer violates; all pairs use f1.
# Previous fake had violation (24.237 >22.938) due to synthetic R44; now corrected.
VIOLATING_PAIRS: set[str] = set()


def _load(name: str) -> dict:
    return json.loads((TRACKS / f"{name}.json").read_text(encoding="utf-8"))


def test_files_exist():
    for base in PAIRS:
        assert (TRACKS / f"{base}.json").exists(), f"racing {base}.json missing"
        assert (TRACKS / f"{base}_centerline.json").exists(), f"centerline {base}_centerline.json missing"
    # duplicate removed
    assert not (TRACKS / "suzuka_racing.json").exists(), "duplicate suzuka_racing.json should be deleted"
    # display name convention
    for base in PAIRS:
        racing = _load(base)
        center = _load(f"{base}_centerline")
        # centerline name should have suffix
        assert "コース中心線" in center.get("name", ""), f"{base}_centerline name missing suffix: {center.get('name')}"
        assert "コース中心線" not in racing.get("name", ""), f"{base} racing name should be plain without suffix: {racing.get('name')}"


def test_racing_length_within_1_5_percent_of_centerline():
    for base in PAIRS:
        racing = _load(base)
        center = _load(f"{base}_centerline")
        lr = float(racing["length_m"])
        lc = float(center["length_m"])
        rel = abs(lr - lc) / lc
        assert rel <= 0.015, f"{base} racing length {lr:.3f} vs centerline {lc:.3f} diff {rel*100:.3f}% >1.5%"
        # also sanity: points monotonic and closed
        for key in (base, f"{base}_centerline"):
            d = _load(key)
            s_vals = [p["s"] for p in d["points"]]
            assert abs(s_vals[0]) < 1e-6
            for a, b in zip(s_vals, s_vals[1:]):
                assert b > a, f"{key} s not monotonic"


def test_racing_f1_laptime_faster_than_centerline_or_rental_alternative():
    from openlapexe.solver import simulate_full

    failures = []
    for base in PAIRS:
        if base in VIOLATING_PAIRS:
            r_racing = simulate_full("rental_gx270", base, 50)
            r_center = simulate_full("rental_gx270", f"{base}_centerline", 50)
            note = f"NOTE {base}: f1 racing slower than centerline, using rental_gx270 alternative"
            assert r_racing.laptime < r_center.laptime, f"{base} rental_gx270 racing {r_racing.laptime:.5f} not < centerline {r_center.laptime:.5f} ({note})"
            f1_r = simulate_full("f1", base, 50)
            f1_c = simulate_full("f1", f"{base}_centerline", 50)
            assert f1_r.laptime > f1_c.laptime, f"expected violation not observed for {base}: f1 racing {f1_r.laptime:.5f} vs center {f1_c.laptime:.5f}"
        else:
            r_racing = simulate_full("f1", base, 50)
            r_center = simulate_full("f1", f"{base}_centerline", 50)
            assert r_racing.laptime < r_center.laptime, f"{base} f1 racing {r_racing.laptime:.5f} not < centerline {r_center.laptime:.5f}"
            # sanity bands
            assert 10.0 <= r_racing.laptime <= 200.0
            assert 10.0 <= r_center.laptime <= 200.0


def test_determinism_1e9_on_one_pair():
    from openlapexe.solver import simulate_full

    r1 = simulate_full("f1", "spa", 50)
    r2 = simulate_full("f1", "spa", 50)
    assert abs(r1.laptime - r2.laptime) < 1e-9, f"laptime nondeterministic {r1.laptime} vs {r2.laptime}"
    npt.assert_allclose(np.asarray(r1.v), np.asarray(r2.v), atol=1e-9, rtol=0)
    npt.assert_allclose(np.asarray(r1.s), np.asarray(r2.s), atol=1e-9, rtol=0)
    # also check all arrays if present
    for name in ("ax", "ay", "time"):
        npt.assert_allclose(np.asarray(getattr(r1, name)), np.asarray(getattr(r2, name)), atol=1e-9, rtol=0)
