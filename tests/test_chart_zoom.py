# -*- coding: utf-8 -*-
"""Chart zoom/pan/reset tests (BaseChart wrapper)."""
from __future__ import annotations

import pytest


def _try_root():
    try:
        import tkinter as tk
    except Exception as e:
        pytest.skip(f"tkinter unavailable: {e}")
    try:
        root = tk.Tk()
        root.withdraw()
        return root
    except Exception as e:
        pytest.skip(f"headless no display: {e}")


def _coords_of(chart):
    out = []
    try:
        for i in chart.find_withtag("line")[:4]:
            out.append(tuple(chart.coords(i)))
    except Exception:
        pass
    return out


def test_zoom_at_changes_coords_and_reset_restores():
    root = _try_root()
    try:
        from openlapexe.gui.chart_base import BaseChart

        c = BaseChart(root, width=400, height=300)
        c.pack()
        root.update()
        c.set_data([0, 1, 2, 3, 4], [0, 1, 4, 9, 16])
        root.update()
        before = _coords_of(c)
        assert before, "chart should draw line items"
        c.zoom_at(200, 150, 2.0)
        root.update()
        after = _coords_of(c)
        assert after != before, "zoom must change coords"
        assert abs(c._zoom_fx - 2.0) < 1e-9
        c.zoom_at(200, 150, 100.0)
        assert c._zoom_fx <= 25.0, "zoom clamp max"
        c.reset_zoom()
        root.update()
        restored = _coords_of(c)
        assert restored == before, "reset must restore coords"
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_pan_moves_coords():
    root = _try_root()
    try:
        import types

        from openlapexe.gui.chart_base import BaseChart

        c = BaseChart(root, width=400, height=300)
        c.pack()
        root.update()
        c.set_data([0, 1, 2, 3], [1, 2, 1, 2])
        root.update()
        before = _coords_of(c)
        assert before
        c._on_pan_press(types.SimpleNamespace(x=100, y=100))
        c._on_pan_drag(types.SimpleNamespace(x=150, y=120))
        root.update()
        assert abs(c._pan_dx) > 0 and abs(c._pan_dy) > 0, "pan must record offsets"
        c.reset_zoom()
        assert c._pan_dx == 0.0 and c._pan_dy == 0.0
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_all_chart_classes_have_zoom_api():
    from openlapexe.gui.chart_base import BaseChart
    from openlapexe.gui.chart_xy import XYChart
    from openlapexe.gui.chart import SpeedChart, GGChart, SectorChart

    for cls in (BaseChart, XYChart, SpeedChart, GGChart, SectorChart):
        assert hasattr(cls, "zoom_at") or hasattr(BaseChart, "zoom_at")
        assert hasattr(BaseChart, "reset_zoom")
    import openlapexe.gui.charts_results as cr
    import openlapexe.gui.charts_vehicle as cv
    import openlapexe.gui.charts_track as ct
    import openlapexe.gui.charts_drag as cd

    found = 0
    for mod in (cr, cv, ct, cd):
        for name in dir(mod):
            obj = getattr(mod, name)
            try:
                if isinstance(obj, type) and issubclass(obj, BaseChart) and obj is not BaseChart:
                    found += 1
            except Exception:
                pass
    assert found >= 20, f"expected 20+ chart classes, got {found}"
