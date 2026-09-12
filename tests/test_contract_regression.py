# -*- coding: utf-8 -*-
"""Regression guard: old 95.8059 outside ±0.5% of 101.17, baseline differs >1s."""
from __future__ import annotations

import pathlib

import pytest

CANONICAL = 101.17
TOL = 0.005
LO = CANONICAL * (1 - TOL)
HI = CANONICAL * (1 + TOL)
PREVIOUS_BUGGY = 95.80591391534297
FULL_BASELINE_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "reference" / "spa_f1_full_baseline.txt"
OLD_BASELINE_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "reference" / "spa_f1_baseline.txt"


def test_old_95_outside_canonical_band() -> None:
    assert not (LO <= PREVIOUS_BUGGY <= HI), f"previous buggy {PREVIOUS_BUGGY} unexpectedly inside [{LO},{HI}]"
    diff = abs(PREVIOUS_BUGGY - CANONICAL)
    assert diff > 1.0, f"buggy diff {diff} not >1s"
    assert diff / CANONICAL > TOL, "buggy outside tolerance"


def test_full_baseline_differs_gt_1s_from_buggy() -> None:
    txt = FULL_BASELINE_PATH.read_text(encoding="utf-8").strip()
    val = float(txt.split()[0])
    assert abs(val - PREVIOUS_BUGGY) > 1.0, f"full baseline {val} not >1s from buggy {PREVIOUS_BUGGY}"
    assert LO <= val <= HI, f"full baseline {val} not in canonical band"


def test_old_shim_baseline_still_101() -> None:
    txt = OLD_BASELINE_PATH.read_text(encoding="utf-8").strip()
    old = float(txt.split()[0])
    assert abs(old - 101.17) < 1e-9, f"old shim baseline {old} != 101.17"
    assert LO <= old <= HI
