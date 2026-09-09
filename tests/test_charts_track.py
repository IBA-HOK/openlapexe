# -*- coding: utf-8 -*-
"""tests/test_charts_track - RED→GREEN for charts_track 6種."""
from __future__ import annotations

import pathlib

import pytest
import numpy as np


def _has_display() -> bool:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.update_idletasks()
        root.destroy()
        return True
    except Exception:
        return False


HAS_DISPLAY = _has_display()

pytestmark = pytest.mark.skipif(not HAS_DISPLAY, reason="no display for Tk") if not HAS_DISPLAY else pytest.mark.usefixtures()


def test_import_no_mpl_and_classes_exist() -> None:
    path = pathlib.Path("src/openlapexe/gui/charts_track.py")
    if not path.exists():
        path = pathlib.Path(__file__).resolve().parents[1] / "src" / "openlapexe" / "gui" / "charts_track.py"
    txt = path.read_text(encoding="utf-8")
    assert "matplotlib" not in txt.lower(), "mpl禁止"
    assert "scipy" not in txt.lower(), "sci-py禁止"
    assert "chart_xy" in txt or "chart_base" in txt, "chart_xy/chart_base利用必須"
    import openlapexe.gui.charts_track as mod

    expected = ["TrackMapChart", "TrackCurvChart", "TrackElevChart", "TrackGradChart", "TrackBankChart", "TrackGripChart"]
    for name in expected:
        assert hasattr(mod, name), f"missing {name}"
    # existing name not reused
    for bad in ["SpeedChart", "GGChart", "SectorChart", "VehicleTorqueChart", "ResultsSpeedChart"]:
        assert not hasattr(mod, bad), f"{bad}名再利用禁止"
    from openlapexe.gui.chart_xy import XYChart
    from openlapexe.gui.chart_base import BaseChart

    for name in expected:
        cls = getattr(mod, name)
        assert issubclass(cls, (XYChart, BaseChart)), f"{name} must inherit XYChart/BaseChart"


def test_spa_all_charts_draw() -> None:
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.track import Track2
    import openlapexe.gui.charts_track as mod

    tr = Track2.from_json("spa")
    assert tr.points.shape[1] == 8
    assert tr.points.shape[0] > 1000
    classes = [mod.TrackMapChart, mod.TrackCurvChart, mod.TrackElevChart, mod.TrackGradChart, mod.TrackBankChart, mod.TrackGripChart]
    root = tk.Tk()
    root.withdraw()
    try:
        for cls in classes:
            c = cls(root, width=600, height=400)
            c.pack()
            root.update_idletasks()
            c.plot(tr)
            root.update_idletasks()
            items = c.find_all()
            assert len(items) > 0, f"{cls.__name__} has no canvas items"
            assert hasattr(c, "_last_draw_ms")
            if hasattr(c, "_draw_count"):
                assert c._draw_count >= 1
            c.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_grad_finite() -> None:
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.track import Track2
    import openlapexe.gui.charts_track as mod

    tr = Track2.from_json("spa")
    root = tk.Tk()
    root.withdraw()
    try:
        c = mod.TrackGradChart(root, width=600, height=400)
        c.pack()
        root.update_idletasks()
        c.plot(tr)
        root.update_idletasks()
        grad = getattr(c, "_grad", None)
        assert grad is not None, "grad missing"
        arr = np.asarray(grad, dtype=float)
        assert np.all(np.isfinite(arr)), "勾配finiteでない"
        # also check via getter
        g2 = c.get_gradient()
        assert g2 is not None
        assert np.all(np.isfinite(g2[1]))
        c.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_grip_range() -> None:
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.track import Track2
    import openlapexe.gui.charts_track as mod

    tr = Track2.from_json("spa")
    root = tk.Tk()
    root.withdraw()
    try:
        c = mod.TrackGripChart(root, width=600, height=400)
        c.pack()
        root.update_idletasks()
        c.plot(tr)
        root.update_idletasks()
        ylim = getattr(c, "_ylim", None)
        if ylim is None:
            ylim = getattr(c, "ylim", None)
        assert ylim is not None
        lo, hi = float(ylim[0]), float(ylim[1])
        assert lo == 0.8 and hi == 1.2, f"grip ylim expected (0.8,1.2) got {ylim}"
        grip = getattr(c, "_grip", None)
        if grip is not None:
            arr = np.asarray(grip, dtype=float)
            # grip values may be 1.0 constant, but should be within plausible 0.5..1.5 and finite
            assert np.all(np.isfinite(arr))
        # also check with synthetic varying grip
        pts = tr.points.copy()
        # modify grip column to vary 0.85..1.15 to ensure chart handles range
        n = pts.shape[0]
        pts[:, 6] = np.linspace(0.85, 1.15, n)
        c2 = mod.TrackGripChart(root, width=600, height=400)
        c2.pack()
        root.update_idletasks()
        c2.plot(pts)
        root.update_idletasks()
        ylim2 = getattr(c2, "_ylim", getattr(c2, "ylim", None))
        assert ylim2 == (0.8, 1.2) or (float(ylim2[0]) == 0.8 and float(ylim2[1]) == 1.2)
        c2.destroy()
        c.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_map_axis_equal() -> None:
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.track import Track2
    import openlapexe.gui.charts_track as mod

    tr = Track2.from_json("spa")
    root = tk.Tk()
    root.withdraw()
    try:
        c = mod.TrackMapChart(root, width=600, height=400)
        c.pack()
        root.update_idletasks()
        c.plot(tr)
        root.update_idletasks()
        eq = getattr(c, "equal", None)
        if eq is None:
            eq = getattr(c, "axis_equal", None)
        if eq is None:
            eq = getattr(c, "_equal", None)
        assert eq is True or eq == 1, f"axis equal expected True got {eq}"
        pw = getattr(c, "_plot_w", None)
        ph = getattr(c, "_plot_h", None)
        if pw is not None and ph is not None:
            assert abs(float(pw) - float(ph)) < 1e-6, f"equal viewport not square {pw} vs {ph}"
        c.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass
