# -*- coding: utf-8 -*-
"""Happy-path contracts: spa f1 50Hz/100Hz + app.simulate alias in 101.17 ±0.5%."""
from __future__ import annotations

import pytest
import numpy as np

CANONICAL = 101.17
TOL = 0.005
LO = CANONICAL * (1 - TOL)  # 100.66415
HI = CANONICAL * (1 + TOL)  # 101.67585


def test_happy_spa_f1_50hz_in_band() -> None:
    from openlapexe.solver import simulate_full

    res = simulate_full("f1", "spa", 50)
    assert LO <= res.laptime <= HI, f"50Hz laptime {res.laptime} not in [{LO},{HI}]"
    assert 100.0 <= res.laptime <= 102.5


def test_happy_spa_f1_100hz_same_band_and_len() -> None:
    from openlapexe.solver import simulate_full

    r50 = simulate_full("f1", "spa", 50)
    r100 = simulate_full("f1", "spa", 100)
    assert LO <= r100.laptime <= HI, f"100Hz laptime {r100.laptime} not in [{LO},{HI}]"
    assert len(r100.s) > len(r50.s), f"100Hz len {len(r100.s)} not > 50Hz {len(r50.s)}"
    assert len(r100.s) != len(r50.s)


def test_happy_app_simulate_alias_same_band() -> None:
    import app

    res = app.simulate("f1", "spa")
    assert LO <= res.laptime <= HI, f"app.simulate laptime {res.laptime} not in [{LO},{HI}]"
    from openlapexe.solver import simulate_full

    r_full = simulate_full("f1", "spa", 50)
    assert abs(res.laptime - r_full.laptime) < 1e-9, f"alias mismatch {res.laptime} vs {r_full.laptime}"
