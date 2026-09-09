# -*- coding: utf-8 -*-
"""TDD RED: empty torque_curve fail-fast + freq validation."""
import pytest


def test_empty_torque_curve_raises_valueerror():
    from openlapexe.solver import _build_driveline_cache

    class DummyVehicle:
        torque_curve = []
        ratio_primary = 1.0
        ratio_final = 3.0
        ratio_gearbox = (1.0,)
        tyre_radius = 0.33
        n_primary = 1.0
        n_gearbox = 0.98
        n_final = 0.92

    with pytest.raises(ValueError, match="torque_curve empty"):
        _build_driveline_cache(DummyVehicle())


def test_freq_non_numeric_raises_typeerror():
    from openlapexe.solver import simulate_full

    with pytest.raises(TypeError):
        simulate_full("f1", "spa", freq="abc")  # type: ignore[arg-type]


def test_freq_zero_raises_valueerror():
    from openlapexe.solver import simulate_full

    with pytest.raises(ValueError):
        simulate_full("f1", "spa", freq=0)


def test_freq_over_200_raises_valueerror():
    from openlapexe.solver import simulate_full

    with pytest.raises(ValueError):
        simulate_full("f1", "spa", freq=201)


def test_freq_negative_raises_valueerror():
    from openlapexe.solver import simulate_full

    with pytest.raises(ValueError):
        simulate_full("f1", "spa", freq=-5)
