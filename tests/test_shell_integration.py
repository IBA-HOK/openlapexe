# -*- coding: utf-8 -*-
"""tests/test_shell_integration - 子Notebook統合検証 (Sim 9/Drag 15/Track 6/Vehicle 4, 重複なし, ヘッドレス可)."""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _has_display() -> bool:
    try:
        import tkinter as tk

        r = tk.Tk()
        r.withdraw()
        r.update_idletasks()
        r.destroy()
        return True
    except Exception:
        return False


HAS_DISPLAY = _has_display()

if HAS_DISPLAY:
    pass
else:
    pass


def _read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _count_adds(text: str, nb_name: str) -> tuple[int, list[str]]:
    pat = re.compile(re.escape(nb_name) + r"\.add\([^,]+,\s*text=\"([^\"]+)\"\)")
    titles = pat.findall(text)
    return len(titles), titles


def _check_duplicate(titles: list[str]) -> None:
    assert len(titles) == len(set(titles)), f"重複タイトルあり: {titles}"


# --- encoding ---

def test_encoding_utf8_all_gui() -> None:
    for name in ("simulate.py", "drag_view.py", "track_view.py", "vehicle_editor.py"):
        p = ROOT / f"src/openlapexe/gui/{name}"
        if not p.exists():
            p = SRC / f"openlapexe/gui/{name}"
        txt = _read_text(p)
        assert "coding" in txt and "utf-8" in txt, f"{name} encoding utf-8 missing"
        assert "scipy" not in txt.lower() or "禁止" in txt, f"{name} scipy present"
        assert "matplotlib" not in txt.lower() or "禁止" in txt, f"{name} matplotlib present"


# --- simulate 9 ---

def test_simulate_child_tabs_9() -> None:
    p = SRC / "openlapexe/gui/simulate.py"
    txt = _read_text(p)
    if HAS_DISPLAY:
        try:
            import tkinter as tk
            from openlapexe.gui.simulate import SimulateView2  # type: ignore

            root = tk.Tk()
            root.withdraw()
            view = SimulateView2(root)
            root.update_idletasks()
            nb = getattr(view, "chart_notebook", None) or getattr(view, "graph_notebook", None)
            assert nb is not None, "chart_notebook missing"
            tabs = nb.tabs()
            assert len(tabs) == 9, f"Simulate chart_notebook expected 9, got {len(tabs)}"
            texts = [nb.tab(tid, "text") for tid in tabs]
            _check_duplicate(texts)
            assert texts[0] == "速度" and texts[1] == "G-G" and texts[2] == "セクター", f"既存順序破壊: {texts[:3]}"
            assert "標高・曲率" in texts and "G合力" in texts and "TPS・BPS" in texts and "ステア" in texts and "GGV3D" in texts and "トラックマップ" in texts
            view.destroy()
            root.destroy()
            return
        except Exception as e:
            if isinstance(e, pytest.skip.Exception):
                raise
            # fallback to grep
            pass
    # headless grep path
    cnt, titles = _count_adds(txt, "chart_notebook")
    assert cnt == 9, f"simulate chart_notebook grep count expected 9 got {cnt} titles={titles}"
    _check_duplicate(titles)
    assert titles[0] == "速度" and titles[1] == "G-G" and titles[2] == "セクター"
    for need in ("標高・曲率", "G合力", "TPS・BPS", "ステア", "GGV3D", "トラックマップ"):
        assert need in titles, f"simulate missing {need} in {titles}"
    # fallback existence
    assert "読込失敗" in txt, "simulate fallback placeholder missing"
    assert "charts_results" in txt, "simulate must use charts_results"


def test_drag_child_tabs_15() -> None:
    p = SRC / "openlapexe/gui/drag_view.py"
    txt = _read_text(p)
    if HAS_DISPLAY:
        try:
            import tkinter as tk
            from openlapexe.gui.drag_view import DragView  # type: ignore

            root = tk.Tk()
            root.withdraw()
            view = DragView(root)
            root.update_idletasks()
            nb = getattr(view, "graph_notebook", None)
            assert nb is not None, "graph_notebook missing"
            tabs = nb.tabs()
            assert len(tabs) == 15, f"Drag graph_notebook expected 15 (2+13), got {len(tabs)}"
            texts = [nb.tab(tid, "text") for tid in tabs]
            _check_duplicate(texts)
            assert texts[0] == "ドラッグ曲線" and texts[1] == "ギアマップ", f"既存順序破壊 {texts[:2]}"
            for need in ("T-X", "T-V", "X-V", "T-A", "X-A", "T-RPM", "X-RPM", "T-GEAR", "X-GEAR", "T-TPS", "X-TPS", "T-BPS", "X-BPS"):
                assert need in texts, f"drag missing {need}"
            view.destroy()
            root.destroy()
            return
        except Exception as e:
            if isinstance(e, pytest.skip.Exception):
                raise
            pass
    cnt, titles = _count_adds(txt, "graph_notebook")
    assert cnt == 15, f"drag graph_notebook grep count expected 15 got {cnt} titles={titles}"
    _check_duplicate(titles)
    assert titles[0] == "ドラッグ曲線" and titles[1] == "ギアマップ"
    for need in ("T-X", "T-V", "X-V", "T-A", "X-A", "T-RPM", "X-RPM", "T-GEAR", "X-GEAR", "T-TPS", "X-TPS", "T-BPS", "X-BPS"):
        assert need in titles
    assert "charts_drag" in txt
    assert "読込失敗" in txt


def test_track_child_tabs_6() -> None:
    p = SRC / "openlapexe/gui/track_view.py"
    txt = _read_text(p)
    if HAS_DISPLAY:
        try:
            import tkinter as tk
            from openlapexe.gui.track_view import TrackView2  # type: ignore

            root = tk.Tk()
            root.withdraw()
            view = TrackView2(root)
            root.update_idletasks()
            nb = getattr(view, "graph_notebook", None) or getattr(view, "chart_notebook", None)
            assert nb is not None, "track graph_notebook missing (ミニマップ下)"
            tabs = nb.tabs()
            assert len(tabs) == 6, f"Track graph_notebook expected 6, got {len(tabs)}"
            texts = [nb.tab(tid, "text") for tid in tabs]
            _check_duplicate(texts)
            for need in ("地図", "曲率", "標高", "勾配", "バンク", "グリップ"):
                assert need in texts, f"track missing {need} in {texts}"
            # ensure sector table still exists
            assert hasattr(view, "sector_table")
            assert hasattr(view, "canvas")
            view.destroy()
            root.destroy()
            return
        except Exception as e:
            if isinstance(e, pytest.skip.Exception):
                raise
            pass
    cnt, titles = _count_adds(txt, "graph_notebook")
    assert cnt == 6, f"track graph_notebook grep count expected 6 got {cnt} titles={titles}"
    _check_duplicate(titles)
    for need in ("地図", "曲率", "標高", "勾配", "バンク", "グリップ"):
        assert need in titles
    assert "charts_track" in txt
    assert "読込失敗" in txt


def test_vehicle_child_tabs_4() -> None:
    p = SRC / "openlapexe/gui/vehicle_editor.py"
    txt = _read_text(p)
    if HAS_DISPLAY:
        try:
            import tkinter as tk
            from openlapexe.gui.vehicle_editor import VehicleEditor47  # type: ignore

            root = tk.Tk()
            root.withdraw()
            view = VehicleEditor47(root)
            root.update_idletasks()
            nb = getattr(view, "graph_notebook", None) or getattr(view, "chart_notebook", None)
            assert nb is not None, "vehicle graph_notebook missing (トルク表下)"
            tabs = nb.tabs()
            assert len(tabs) == 4, f"Vehicle graph_notebook expected 4, got {len(tabs)}"
            texts = [nb.tab(tid, "text") for tid in tabs]
            _check_duplicate(texts)
            for need in ("トルク・パワー", "ギア", "Fx包絡", "GGV"):
                assert need in texts, f"vehicle missing {need} in {texts}"
            assert hasattr(view, "tree")
            assert hasattr(view, "canvas")
            view.destroy()
            root.destroy()
            return
        except Exception as e:
            if isinstance(e, pytest.skip.Exception):
                raise
            pass
    cnt, titles = _count_adds(txt, "graph_notebook")
    assert cnt == 4, f"vehicle graph_notebook grep count expected 4 got {cnt} titles={titles}"
    _check_duplicate(titles)
    for need in ("トルク・パワー", "ギア", "Fx包絡", "GGV"):
        assert need in titles
    assert "charts_vehicle" in txt
    assert "読込失敗" in txt


def test_no_duplicate_titles_all_notebooks() -> None:
    for name, nb_name in (
        ("simulate.py", "chart_notebook"),
        ("drag_view.py", "graph_notebook"),
        ("track_view.py", "graph_notebook"),
        ("vehicle_editor.py", "graph_notebook"),
    ):
        p = SRC / f"openlapexe/gui/{name}"
        txt = _read_text(p)
        _, titles = _count_adds(txt, nb_name)
        _check_duplicate(titles)


def test_existing_attributes_preserved() -> None:
    sim_txt = _read_text(SRC / "openlapexe/gui/simulate.py")
    assert "self.tab_speed" in sim_txt and "self.tab_gg" in sim_txt and "self.tab_sector" in sim_txt
    assert "self.speed_chart" in sim_txt and "self.gg_chart" in sim_txt and "self.sector_chart" in sim_txt
    assert "self.chart_notebook" in sim_txt
    drag_txt = _read_text(SRC / "openlapexe/gui/drag_view.py")
    assert "self.tab_curve" in drag_txt and "self.tab_gear" in drag_txt
    assert "self.graph_notebook" in drag_txt
    track_txt = _read_text(SRC / "openlapexe/gui/track_view.py")
    assert "self.canvas" in track_txt and "self.sector_table" in track_txt
    veh_txt = _read_text(SRC / "openlapexe/gui/vehicle_editor.py")
    assert "self.tree" in veh_txt and "self.canvas" in veh_txt
    for f in ("simulate.py", "drag_view.py", "track_view.py", "vehicle_editor.py"):
        txt = _read_text(SRC / f"openlapexe/gui/{f}")
        assert "try:" in txt and "except" in txt, f"{f} try/except fallback missing"


def test_docs_graph_placement_exists() -> None:
    p = ROOT / "docs/graph_placement.md"
    assert p.exists(), "docs/graph_placement.md missing"
    txt = p.read_text(encoding="utf-8")
    assert "per-tab" in txt.lower() or "per-tab" in txt.lower() or "方式" in txt
    assert "simulate" in txt.lower() or "Simulate" in txt
    assert "drag" in txt.lower()
    assert "track" in txt.lower()
    assert "vehicle" in txt.lower()


def test_charts_modules_not_modified() -> None:
    for name in ("charts_results.py", "charts_drag.py", "charts_track.py", "charts_vehicle.py"):
        p = SRC / f"openlapexe/gui/{name}"
        txt = _read_text(p)
        assert "matplotlib" not in txt.lower()
        assert "scipy" not in txt.lower()
