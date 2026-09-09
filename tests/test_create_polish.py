# -*- coding: utf-8 -*-
"""TDD RED: create-tab polish — label dedup, closed loop, spline interp, L/R sides.

All tests are expected to FAIL on current codebase.
Failures must be spec-driven (assert on behavior/presence), never syntax/import.
"""
from __future__ import annotations

import pathlib
import sys

import pytest


def _try_root():
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.update()
        return root
    except Exception as e:
        pytest.skip(f"headless no display: {e}")


def _create_app_offline():
    sys.path.insert(0, "src")
    import openlapexe.geo_tile as gt

    orig = gt.fetch_tile
    gt.fetch_tile = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline"))
    from openlapexe.gui.shell import App2

    app = App2()
    return app, orig


def test_mode_radio_labels_appear_once() -> None:
    """Create tab must show 走行ライン直接 exactly once (no duplicate pairs)."""
    root = _try_root()
    try:
        app, orig = _create_app_offline()
        try:
            app.update_idletasks()
            texts: list[str] = []

            def walk(w):
                try:
                    kids = w.winfo_children()
                except Exception:
                    return
                for k in kids:
                    try:
                        t = str(k.cget("text"))
                        if t:
                            texts.append(t)
                    except Exception:
                        pass
                    walk(k)

            walk(app.tab_create)
            n = sum(1 for t in texts if t == "走行ライン直接")
            assert n == 1, f"expected exactly 1 走行ライン直接 label, got {n}: {texts}"
            try:
                app._on_close()
            except Exception:
                pass
            try:
                app.destroy()
            except Exception:
                pass
        finally:
            try:
                app.destroy()
            except Exception:
                pass
            import openlapexe.geo_tile as gt

            gt.fetch_tile = orig
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_closed_loop_toggle_and_save() -> None:
    """Loop toggle must exist and saved JSON must carry closed_loop=true."""
    root = _try_root()
    try:
        app, orig = _create_app_offline()
        try:
            app.update_idletasks()
            assert hasattr(app, "_loop_var") or hasattr(app, "loop_var"), "loop toggle var must exist"
            import tkinter.messagebox as mb

            _w, _e = mb.showwarning, mb.showerror
            mb.showwarning = lambda *a, **kw: None
            mb.showerror = lambda *a, **kw: None
            try:
                oc = app._osm_canvas
                for lat, lon in ((35.68, 139.76), (35.681, 139.761), (35.682, 139.762), (35.681, 139.763)):
                    oc.add_point_latlon(lat, lon)
                app._sync_osm_to_creator()
                try:
                    app._loop_var.set(True)
                except Exception:
                    app.loop_var.set(True)
                from openlapexe.track import Track

                cand = {"points_xy": list(oc.points_xy), "name": "__ut_loop__"}
                track = Track.from_candidates([cand], closed_loop=True)
                track.name = "__ut_loop__"
                path = track.save_json("__ut_loop__")
                import json

                data = json.loads(path.read_text(encoding="utf-8"))
                assert data.get("closed_loop") is True, f"JSON must be closed_loop, got {data.get('closed_loop')}"
            finally:
                mb.showwarning, mb.showerror = _w, _e
                p = pathlib.Path("data/tracks/__ut_loop__.json")
                if p.exists():
                    p.unlink()
            try:
                app._on_close()
            except Exception:
                pass
            try:
                app.destroy()
            except Exception:
                pass
        finally:
            try:
                app.destroy()
            except Exception:
                pass
            import openlapexe.geo_tile as gt

            gt.fetch_tile = orig
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_spline_waypoints_through_points_and_denser() -> None:
    """spline_waypoints must pass through originals and densify."""
    sys.path.insert(0, "src")
    import numpy as np

    import openlapexe.curvature_opt as co

    assert hasattr(co, "spline_waypoints"), "spline_waypoints must exist in curvature_opt"
    pts = [(0.0, 0.0), (10.0, 3.0), (20.0, 0.0), (30.0, 5.0)]
    dense = co.spline_waypoints(pts, closed=False, step_m=2.0)
    dense = np.asarray(dense, dtype=float)
    assert dense.shape[0] > len(pts), "spline must densify"
    for x, y in pts:
        d = np.hypot(dense[:, 0] - x, dense[:, 1] - y)
        assert float(np.min(d)) < 1e-9, f"spline must pass through {(x, y)}"
    loop = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    cd = np.asarray(co.spline_waypoints(loop, closed=True, step_m=2.0), dtype=float)
    gap = float(np.hypot(cd[0, 0] - cd[-1, 0], cd[0, 1] - cd[-1, 1]))
    assert gap < 1e-6, f"closed spline must wrap, gap={gap}"


def test_edge_side_selector_routes_clicks() -> None:
    """Edge mode must allow designating left/right side for clicks."""
    root = _try_root()
    try:
        sys.path.insert(0, "src")
        from openlapexe.gui.course_creator import CourseCreator
        import tkinter as tk

        cc = CourseCreator(root)
        cc.pack()
        root.update()
        assert hasattr(cc, "set_edge_side"), "set_edge_side API must exist"
        cc.set_mode("edge")
        cc.set_edge_side("right")
        assert cc.edge_side == "right"
        cc._on_left_click_at(100.0, 100.0) if hasattr(cc, "_on_left_click_at") else cc.add_point_at(100.0, 100.0)
        root.update()
        assert len(list(cc.right_xy)) == 1 and len(list(cc.left_xy)) == 0, "click must go to right side"
        cc.set_edge_side("left")
        cc._on_left_click_at(200.0, 200.0) if hasattr(cc, "_on_left_click_at") else cc.add_point_at(200.0, 200.0)
        root.update()
        assert len(list(cc.left_xy)) == 1, "click must go to left side"
        try:
            cc.destroy()
        except Exception:
            pass
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_side_buttons_hidden_in_direct_mode() -> None:
    """L/R side buttons must be hidden in direct mode, shown in edge mode."""
    root = _try_root()
    try:
        sys.path.insert(0, "src")
        from openlapexe.gui.course_creator import CourseCreator

        cc = CourseCreator(root)
        cc.pack()
        root.update()
        cc.set_mode("direct")
        root.update()
        assert str(cc.radio_left.winfo_manager()) == "", "left button must be hidden in direct"
        assert str(cc.radio_right.winfo_manager()) == "", "right button must be hidden in direct"
        cc.set_mode("edge")
        root.update()
        assert str(cc.radio_left.winfo_manager()) == "pack", "left button must show in edge"
        assert str(cc.radio_right.winfo_manager()) == "pack", "right button must show in edge"
        try:
            cc.destroy()
        except Exception:
            pass
    finally:
        try:
            root.destroy()
        except Exception:
            pass
