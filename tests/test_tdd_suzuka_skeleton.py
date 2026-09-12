# -*- coding: utf-8 -*-
"""TDD skeleton for Suzuka track (RED phase - skipped placeholders).

Placeholders for:
- suzuka length / closed / determinism
- future: gen_tracks_helper determinism, geo_proj sanity, fixture validation
"""
from __future__ import annotations

import pytest


@pytest.mark.skip(reason="TDD placeholder: suzuka length check not yet implemented (RED)")
def test_suzuka_length():
    """Verify Suzuka total length ~5807m within tolerance."""
    # TODO: load data/tracks/suzuka.json and assert 5700 < length_m < 5900
    assert False, "not implemented"


@pytest.mark.skip(reason="TDD placeholder: suzuka closed-loop check not yet implemented (RED)")
def test_suzuka_closed():
    """Verify Suzuka is closed loop and start/end points coincide."""
    # TODO: load track, check closed_loop True and distance between first/last point < threshold
    assert False, "not implemented"


@pytest.mark.skip(reason="TDD placeholder: suzuka determinism check not yet implemented (RED)")
def test_suzuka_determinism():
    """Verify Suzuka generation is deterministic (two builds produce identical points)."""
    # TODO: use gen_tracks_helper.kml_to_track twice and compare points with assert_deterministic
    assert False, "not implemented"


@pytest.mark.skip(reason="TDD placeholder: suzuka geo_proj sanity not yet implemented (RED)")
def test_suzuka_geo_proj():
    """Verify Suzuka lat/lon -> plane projection sanity."""
    assert False, "not implemented"


@pytest.mark.skip(reason="TDD placeholder: suzuka fixture existence not yet implemented (RED)")
def test_suzuka_fixtures():
    """Verify fastf1/supergt fixtures exist and contain expected keys."""
    assert False, "not implemented"
