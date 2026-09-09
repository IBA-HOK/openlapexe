# -*- coding: utf-8 -*-
"""tests/test_course_creator - CourseCreator RED→GREEN."""
from __future__ import annotations

import pathlib

import numpy as np
import pytest


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


def test_import_and_file_constraints() -> None:
    path = pathlib.Path("src/openlapexe/gui/course_creator.py")
    if not path.exists():
        path = pathlib.Path(__file__).resolve().parents[1] / "src" / "openlapexe" / "gui" / "course_creator.py"
    assert path.exists(), "course_creator.py missing"
    txt = path.read_text(encoding="utf-8")
    assert "import scipy" not in txt.lower(), "scipy禁止"
    assert "from scipy" not in txt.lower(), "scipy禁止"
    assert "import matplotlib" not in txt.lower(), "matplotlib禁止"
    assert "from matplotlib" not in txt.lower(), "matplotlib禁止"
    assert "ttk" in txt, "ttk必須"
    assert "Canvas" in txt, "Canvas自前必須"
    assert "Radiobutton" in txt, "Radiobutton必須"
    # check mode strings: mode pair lives once in shell top bar (dedup),
    # creator owns L/R side labels
    shell_path = pathlib.Path(__file__).resolve().parents[1] / "src" / "openlapexe" / "gui" / "shell.py"
    shell_txt = shell_path.read_text(encoding="utf-8")
    assert shell_txt.count("走行ライン直接") == 1, "走行ライン直接はshellに1箇所のみ"
    assert "コース両端" in shell_txt, "コース両端 文字必須(shell)"
    assert "左側を描く" in txt and "右側を描く" in txt, "左右指定 文字必須(creator)"
    assert "optimize_centerline" in txt, "optimize_centerline連携必須"
    assert "chart_xy" in txt, "chart_xy利用必須"
    assert "messagebox" in txt, "messagebox必須"
    assert "parent=self" in txt, "parent=self必須"
    # Undo depth 50 and Ctrl+Z
    assert "50" in txt, "Undo深さ50 記述必須"
    assert "Ctrl+Z" in txt or "Control-z" in txt or "<Control" in txt, "Ctrl+Z必須"
    # check B1-Motion
    assert "B1-Motion" in txt or "B1_Motion" in txt, "<B1-Motion>必須"

    from openlapexe.gui.course_creator import CourseCreator

    assert CourseCreator is not None
    # API check via inspection without display
    import inspect

    src = inspect.getsource(CourseCreator)
    assert "points_xy" in src
    assert "set_points" in src
    assert "get_centerline" in src


def test_empty_no_crash() -> None:
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.gui.course_creator import CourseCreator

    root = tk.Tk()
    root.withdraw()
    try:
        cc = CourseCreator(root, width=600, height=400)
        cc.pack()
        root.update_idletasks()
        # empty should not crash
        try:
            cl = cc.get_centerline()
            assert isinstance(cl, np.ndarray)
            assert cl.shape[0] == 0 or cl.size == 0 or cl.shape[1] == 2
        except Exception as e:
            pytest.fail(f"empty get_centerline crash: {e}")
        # set empty
        cc.set_points([])
        root.update_idletasks()
        # mode switch
        cc.set_mode("edge")
        root.update_idletasks()
        cl2 = cc.get_centerline()
        assert isinstance(cl2, np.ndarray)
        cc.set_mode("direct")
        root.update_idletasks()
        # chart should exist
        assert hasattr(cc, "chart") or hasattr(cc, "curvature_preview") or hasattr(cc, "_chart")
        cc.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_add_delete_drag_undo() -> None:
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.gui.course_creator import CourseCreator

    root = tk.Tk()
    root.withdraw()
    try:
        cc = CourseCreator(root, width=600, height=400)
        cc.pack()
        root.update_idletasks()

        # initial 3 points forming L shape
        pts = [(0, 0), (10, 0), (10, 10)]
        cc.set_points(pts)
        root.update_idletasks()
        assert len(cc.points_xy) == 3

        # add: click near segment 0-1 (midpoint 5,0) should insert
        before = len(cc.points_xy)
        cc.add_point(5, 0)
        root.update_idletasks()
        assert len(cc.points_xy) == before + 1, f"add failed {cc.points_xy}"
        # nearest segment insertion check: new point should be near (5,0)
        # ensure undo restores
        cc.undo()
        root.update_idletasks()
        assert len(cc.points_xy) == before, "undo after add failed"

        # add again then delete
        cc.add_point(5, 0)
        root.update_idletasks()
        assert len(cc.points_xy) == before + 1
        # delete nearest to (5,0)
        cc.delete_at(5, 0)
        root.update_idletasks()
        assert len(cc.points_xy) == before, "delete_at failed"

        # drag: move first point
        orig = cc.points_xy[0]
        cc.move_point(0, 1, 1)
        root.update_idletasks()
        assert cc.points_xy[0] == (1, 1) or cc.points_xy[0] == (1.0, 1.0)
        cc.undo()
        root.update_idletasks()
        assert cc.points_xy[0] == orig, f"undo drag failed {cc.points_xy[0]} vs {orig}"

        # alias methods check
        assert hasattr(cc, "undo")
        assert hasattr(cc, "set_points")
        assert hasattr(cc, "get_centerline")

        # test drag alias
        cc.drag_point(1, 9, 1)
        root.update_idletasks()
        assert cc.points_xy[1][0] == 9 or cc.points_xy[1][0] == 9.0
        cc.undo()
        root.update_idletasks()

        cc.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_mode2_kmax_lt_mode1() -> None:
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.gui.course_creator import CourseCreator
    from openlapexe.curvature_opt import compute_curvature_profile

    root = tk.Tk()
    root.withdraw()
    try:
        cc = CourseCreator(root, width=600, height=400)
        cc.pack()
        root.update_idletasks()

        # sharp 90deg corner polyline for mode1
        # Build L shape 0,0 ->10,0 ->10,10 with 3 points (sharp)
        sharp = [(0, 0), (10, 0), (10, 10), (20, 10)]
        # also test with more points for curvature calc
        # For mode1, direct line = same as sharp
        cc.set_mode("direct")
        cc.set_points(sharp)
        root.update_idletasks()
        c1 = cc.get_centerline()
        k1 = float(np.max(np.abs(compute_curvature_profile(c1, closed=False)))) if c1.shape[0] >= 3 else 0.0

        # mode2: left/right offset of same L shape
        # generate left/right via offset 2m
        # Use helper to build parallel offsets
        mid = np.array(sharp, dtype=float)
        n = mid.shape[0]
        left = []
        right = []
        width = 4.0
        for i in range(n):
            if i == 0:
                tx, ty = mid[1] - mid[0]
            elif i == n - 1:
                tx, ty = mid[-1] - mid[-2]
            else:
                tx, ty = mid[i + 1] - mid[i - 1]
            tn = float(np.hypot(tx, ty))
            if tn < 1e-12:
                nx, ny = 0.0, 1.0
            else:
                tx /= tn
                ty /= tn
                nx, ny = -ty, tx
            half = width * 0.5
            left.append((float(mid[i, 0] - nx * half), float(mid[i, 1] - ny * half)))
            right.append((float(mid[i, 0] + nx * half), float(mid[i, 1] + ny * half)))

        cc.set_mode("edge")
        cc.set_left_right(left, right)
        root.update_idletasks()
        c2 = cc.get_centerline()
        k2 = float(np.max(np.abs(compute_curvature_profile(c2, closed=False)))) if c2.shape[0] >= 3 else 0.0

        assert k2 < k1, f"mode2 kmax {k2} should be < mode1 {k1}"

        cc.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_undo_stack_depth() -> None:
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.gui.course_creator import CourseCreator

    root = tk.Tk()
    root.withdraw()
    try:
        cc = CourseCreator(root)
        cc.pack()
        root.update_idletasks()
        # push 60 adds, stack should cap at 50 but not crash
        for i in range(60):
            cc.add_point(float(i), float(i))
        root.update_idletasks()
        # undo 50 times should not crash
        for _ in range(55):
            cc.undo()
            root.update_idletasks()
        # after many undos, should still be valid
        cl = cc.get_centerline()
        assert isinstance(cl, np.ndarray)
        cc.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_api_osm_import_linkage() -> None:
    """points_xy, set_points, get_centerline で OSMCanvas/import_view と連携できるか."""
    if not HAS_DISPLAY:
        pytest.skip("no display")
    import tkinter as tk
    from openlapexe.gui.course_creator import CourseCreator

    root = tk.Tk()
    root.withdraw()
    try:
        cc = CourseCreator(root)
        cc.pack()
        root.update_idletasks()
        # points_xy attribute mutable list
        assert hasattr(cc, "points_xy")
        assert isinstance(cc.points_xy, list)
        # set_points with ndarray
        pts = np.array([[0, 0], [5, 0], [10, 5]], dtype=float)
        cc.set_points(pts)
        assert len(cc.points_xy) == 3
        # get_centerline returns ndarray (N,2)
        cl = cc.get_centerline()
        assert isinstance(cl, np.ndarray)
        assert cl.ndim == 2 and cl.shape[1] == 2
        # OSMCanvas連携: set_from_osm-like
        # Create a dummy osm object with points_xy
        class DummyOSM:
            points_xy = [(1, 2), (3, 4)]

        if hasattr(cc, "set_from_osm"):
            cc.set_from_osm(DummyOSM())
            assert len(cc.points_xy) == 2
        # left/right existence for edge mode
        assert hasattr(cc, "left_xy") or hasattr(cc, "left_points") or hasattr(cc, "left")
        assert hasattr(cc, "right_xy") or hasattr(cc, "right_points") or hasattr(cc, "right")
        cc.destroy()
    finally:
        try:
            root.destroy()
        except Exception:
            pass
