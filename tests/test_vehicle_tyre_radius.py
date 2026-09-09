# -*- coding: utf-8 -*-
"""TDD RED: tyre_radius fallback must not use cog_height_m."""
import json
import pathlib


def _base_data():
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "vehicles" / "f1.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_tyre_radius_missing_uses_default_033_not_cog():
    from openlapexe.vehicle import Vehicle47

    data = _base_data()
    data.pop("tyre_radius", None)
    data.pop("wheel_radius", None)
    # cog_height_m set to 0.5 to expose bug
    data["cog_height_m"] = 0.5
    data["cog"] = 0.5
    v = Vehicle47.from_json(data)
    assert abs(v.tyre_radius - 0.33) < 1e-9, f"tyre_radius {v.tyre_radius} should be 0.33 not cog_height {data['cog_height_m']}"
    # cog untouched
    assert abs(v.cog_height_m - 0.5) < 1e-9


def test_tyre_radius_missing_with_wheel_radius_fallback():
    from openlapexe.vehicle import Vehicle47

    data = _base_data()
    data.pop("tyre_radius", None)
    data["wheel_radius"] = 0.31
    data["cog_height_m"] = 0.5
    v = Vehicle47.from_json(data)
    assert abs(v.tyre_radius - 0.31) < 1e-9


def test_tyre_radius_none_falls_back_to_default():
    from openlapexe.vehicle import Vehicle47

    data = _base_data()
    data["tyre_radius"] = None
    data["cog_height_m"] = 0.5
    v = Vehicle47.from_json(data)
    assert abs(v.tyre_radius - 0.33) < 1e-9


def test_tyre_radius_explicit_wins_over_cog():
    from openlapexe.vehicle import Vehicle47

    data = _base_data()
    data["tyre_radius"] = 0.28
    data["cog_height_m"] = 0.5
    v = Vehicle47.from_json(data)
    assert abs(v.tyre_radius - 0.28) < 1e-9


def test_tyre_radius_missing_both_defaults_to_033():
    from openlapexe.vehicle import Vehicle47

    data = _base_data()
    data.pop("tyre_radius", None)
    data.pop("wheel_radius", None)
    data["cog_height_m"] = 0.6
    data.pop("cog", None)
    v = Vehicle47.from_json(data)
    assert abs(v.tyre_radius - 0.33) < 1e-9
