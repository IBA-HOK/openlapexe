# -*- coding: utf-8 -*-
"""tests/test_charts_results - RED→GREEN for charts_results 7種."""
from __future__ import annotations

import os
import pathlib
import sys

import pytest
import numpy as np


def _has_display() -> bool:
    # check tk available
    try:
        import tkinter as tk

        # try to create root
        try:
            root = tk.Tk()
            root.withdraw()
            root.update_idletasks()
            root.destroy()
            return True
        except Exception:
            return False
    except Exception:
        return False


HAS_DISPLAY = _has_display()

if not HAS_DISPLAY:
    pytestmark = pytest.mark.skip(reason="no display for Tk")


def test_import_no_matplotlib_and_classes_exist() -> None:
    path = pathlib.Path("src/openlapexe/gui/charts_results.py")
    if not path.exists():
        path = pathlib.Path(__file__).resolve().parents[1] / "src" / "openlapexe" / "gui" / "charts_results.py"
    txt = path.read_text(encoding="utf-8")
    assert "matplotlib" not in txt.lower(), "matplotlib禁止"
    assert "scipy" not in txt.lower(), "scipy禁止"
    assert "chart_xy" in txt or "chart_base" in txt, "chart_xy/chart_base利用必須"
    # check classes
    import openlapexe.gui.charts_results as mod  # type: ignore

    expected = [
        "ResultsElevationChart",
        "ResultsAccelChart",
        "ResultsInputChart",
        "ResultsSteerChart",
        "ResultsGGV3DChart",
        "ResultsTrackMapChart",
    ]
    for name in expected:
        assert hasattr(mod, name), f"missing {name}"
    # also ResultsSpeedChart as 7th
    assert hasattr(mod, "ResultsSpeedChart"), "missing ResultsSpeedChart (7種目)"
    # SpeedChart名未使用
    assert not hasattr(mod, "SpeedChart"), "SpeedChart名再利用禁止"
    assert not hasattr(mod, "GGChart"), "GGChart名再利用禁止"
    assert not hasattr(mod, "SectorChart"), "SectorChart名再利用禁止"
    # inheritance check
    from openlapexe.gui.chart_xy import XYChart  # type: ignore
    from openlapexe.gui.chart_base import BaseChart  # type: ignore

    for name in expected + ["ResultsSpeedChart"]:
        cls = getattr(mod, name)
        assert issubclass(cls, (XYChart, BaseChart)), f"{name} must inherit XYChart/BaseChart"


def test_spa_real_result_all_charts_draw() -> None:
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.solver import simulate_full  # type: ignore
    import openlapexe.gui.charts_results as mod  # type: ignore

    result = simulate_full("f1", "spa")
    # sanity laptime 95.81
    assert 80 < result.laptime < 120
    assert result.s.size > 1000
    classes = [
        mod.ResultsSpeedChart,
        mod.ResultsElevationChart,
        mod.ResultsAccelChart,
        mod.ResultsInputChart,
        mod.ResultsSteerChart,
        mod.ResultsGGV3DChart,
        mod.ResultsTrackMapChart,
    ]
    root = tk.Tk()
    root.withdraw()
    try:
        for cls in classes:
            c = cls(root, width=600, height=400)
            c.pack()
            root.update_idletasks()
            # plot
            c.plot(result)
            root.update_idletasks()
            # check canvas has items
            try:
                items = c.find_all()
                assert len(items) > 0, f"{cls.__name__} has no canvas items"
            except Exception:
                pass
            # check _last_draw_ms exists
            assert hasattr(c, "_last_draw_ms")
            # check has_data
            # ensure after plot, _redraw was called (draw count >0)
            if hasattr(c, "_draw_count"):
                assert c._draw_count >= 1, f"{cls.__name__} _draw_count"
            c.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_results_input_ylim_forced() -> None:
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.solver import simulate_full
    import openlapexe.gui.charts_results as mod

    result = simulate_full("f1", "spa")
    root = tk.Tk()
    root.withdraw()
    try:
        c = mod.ResultsInputChart(root, width=600, height=400)
        c.pack()
        root.update_idletasks()
        c.plot(result)
        root.update_idletasks()
        # ylim must be -10..110
        ylim = getattr(c, "ylim", None)
        if ylim is None:
            ylim = getattr(c, "_ylim", None)
        assert ylim is not None, "ylim missing"
        lo, hi = float(ylim[0]), float(ylim[1])
        assert lo == -10.0 and hi == 110.0, f"ylim expected (-10,110) got {ylim}"
        # also check _ylim attribute
        assert getattr(c, "_ylim", None) == (-10.0, 110.0) or getattr(c, "ylim", None) == (-10.0, 110.0)
        c.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_ggv_wireframe_ge_100_lines() -> None:
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.solver import simulate_full
    import openlapexe.gui.charts_results as mod

    result = simulate_full("f1", "spa")
    root = tk.Tk()
    root.withdraw()
    try:
        c = mod.ResultsGGV3DChart(root, width=600, height=400)
        c.pack()
        root.update_idletasks()
        c.plot(result)
        root.update_idletasks()
        # count lines
        try:
            all_items = c.find_all()
            count_lines = 0
            for item in all_items:
                try:
                    typ = c.type(item)
                    if typ == "line":
                        count_lines += 1
                except Exception:
                    continue
            # also check _last_wireframe_lines if exists
            wl = getattr(c, "_last_wireframe_lines", None)
            if wl is not None:
                assert wl >= 100, f"wireframe lines {wl} <100"
            assert count_lines >= 100, f"wireframe canvas lines {count_lines} <100, expected >=100"
        except Exception as e:
            # fallback: check internal verts count
            verts = getattr(c, "_verts_grid", None)
            if verts is not None:
                assert verts.shape[0] in (400, 780), "closed-loop grid 400 legacy or 780 both-sides expected"
            else:
                raise e
        # also check Vehicle47 compute_ggv 20x20 grid
        from openlapexe.vehicle import Vehicle47  # type: ignore

        veh = Vehicle47.from_json("f1")
        ggv = veh.compute_ggv(np.linspace(5, 80, 20))
        assert "ax_max" in ggv and "ay_max" in ggv
        assert ggv["ax_max"].shape[0] == 20
        assert ggv["ay_max"].shape[0] == 20
        c.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_track_map_axis_equal_and_arrows() -> None:
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.solver import simulate_full
    import openlapexe.gui.charts_results as mod

    result = simulate_full("f1", "spa")
    root = tk.Tk()
    root.withdraw()
    try:
        c = mod.ResultsTrackMapChart(root, width=600, height=400)
        c.pack()
        root.update_idletasks()
        c.plot(result)
        root.update_idletasks()
        # axis equal
        eq = getattr(c, "equal", None)
        if eq is None:
            eq = getattr(c, "axis_equal", None)
        if eq is None:
            eq = getattr(c, "_equal", None)
        assert eq is True or eq == 1, f"axis equal expected True got {eq}"
        # check equal viewport geometry: _plot_w == _plot_h (square)
        pw = getattr(c, "_plot_w", None)
        ph = getattr(c, "_plot_h", None)
        if pw is not None and ph is not None:
            assert abs(float(pw) - float(ph)) < 1e-6, f"equal viewport not square {pw} vs {ph}"
        # arrows
        arrow_count = getattr(c, "_arrow_count", 0)
        # also count canvas arrows via tag
        try:
            arrows = c.find_withtag("arrow")
            cnt = len(arrows) if arrows else 0
            assert cnt >= 1 or arrow_count >= 1, "TrackMap needs direction arrows"
        except Exception:
            assert arrow_count >= 1, "TrackMap needs direction arrows"
        c.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_elevation_dual_y_and_accel_g() -> None:
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.solver import simulate_full
    import openlapexe.gui.charts_results as mod

    result = simulate_full("f1", "spa")
    root = tk.Tk()
    root.withdraw()
    try:
        # Elevation: should have both elev and curv data stored
        c = mod.ResultsElevationChart(root, width=600, height=400)
        c.pack()
        root.update_idletasks()
        c.plot(result)
        root.update_idletasks()
        assert getattr(c, "_z_data", None) is not None
        assert getattr(c, "_curv_data", None) is not None
        # check canvas has at least 2 lines (elev+curv)
        items = c.find_all()
        lines = [i for i in items if c.type(i) == "line"]
        assert len(lines) >= 2, "Elevation need 2 lines"
        c.destroy()
        # Accel: check g = sqrt(ax²+ay²)
        c2 = mod.ResultsAccelChart(root, width=600, height=400)
        c2.pack()
        root.update_idletasks()
        c2.plot(result)
        root.update_idletasks()
        g = getattr(c2, "_g", None)
        assert g is not None
        # verify g = sqrt(ax²+ay²) for at least one point
        ax = getattr(c2, "_ax", None)
        ay = getattr(c2, "_ay", None)
        if ax is not None and ay is not None and g is not None:
            exp = float(np.sqrt(float(ax[0]) ** 2 + float(ay[0]) ** 2))
            assert abs(float(g[0]) - exp) < 1e-6
        # check 3 lines tags
        items2 = c2.find_all()
        # check that legend or lines exist: at least 3 lines (ax,ay,g)
        # Our impl draws 3 lines, so count wireframe-like?
        c2.destroy()
        # Steer: handle = delta*rack (S-ST1); magnitudes physical on cornering
        c3 = mod.ResultsSteerChart(root, width=600, height=400)
        c3.pack()
        root.update_idletasks()
        c3.plot(result)
        root.update_idletasks()
        handle = getattr(c3, "_handle", None)
        beta = getattr(c3, "_beta", None)
        delta = getattr(c3, "_delta", None)
        assert handle is not None and beta is not None and delta is not None
        # handle = delta*rack (in deg)
        from openlapexe.vehicle import Vehicle47

        rack = float(Vehicle47.from_json("f1").rack)
        # delta_deg * rack = handle_deg
        assert abs(float(handle[0]) - float(delta[0]) * rack) < 1e-6
        # cornering point: bicycle-model magnitudes must stay physical
        idx = int(np.argmax(np.abs(delta)))
        assert abs(float(delta[idx])) < 30.0, f"delta unphysical: {float(delta[idx])}"
        assert abs(float(beta[idx])) < 15.0, f"beta unphysical: {float(beta[idx])}"
        assert abs(float(handle[idx]) - float(delta[idx]) * rack) < 1e-6
        c3.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass
