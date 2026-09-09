#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point: src版フルGUI (App2+VehicleEditor47+TrackView2+DragView+SimulateView2 4タブ統合).

起動:
  python main.py
  python -m openlapexe.gui.shell
  dist/app ダブルクリック (PyInstaller onefile, console=False, upx=False)

4タブ:
  車両        -> VehicleEditor47 (47項目+Treeview18行+PCHIP Canvas, Save/Reset, Invalid.TEntry, atomic utf-8)
  コース      -> TrackView2 (Canvas中心線+banking色分け+grip濃淡+sector区間+apex赤点, 800点間引き<100ms)
  OpenDRAG    -> DragView (simulate_dragライブ, 61行 speed_trap 50..350km/h, ギアマップ, Canvas aero/Wd)
  シミュレーション -> SimulateView2 (thread+queue+after(50), Progressbar, laptime mm:ss.sss, sector, CSV 11列, Chart)

app.pyは後方互換shimとして温存 (python app.py / python -m app でも起動可).
spec: app.spec pathex=['src'], datas=[('data','data')], hiddenimports=['openlapexe.*'], console=False, upx=False, onefile
"""
from __future__ import annotations

import pathlib
import sys

# Ensure project root and src are on sys.path for dev runs without pip install
_root = pathlib.Path(__file__).resolve().parent
_src = _root / "src"
for p in (str(_root), str(_src)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _try_import_app2():
    """Try src App2 (fully integrated). Fallback to app.App for backward compat."""
    try:
        from openlapexe.gui.shell import App2  # type: ignore

        # Verify 4 views importable (for hiddenimports check)
        try:
            from openlapexe.gui.vehicle_editor import VehicleEditor47  # noqa: F401  # type: ignore
            from openlapexe.gui.track_view import TrackView2  # noqa: F401  # type: ignore
            from openlapexe.gui.drag_view import DragView  # noqa: F401  # type: ignore
            from openlapexe.gui.simulate import SimulateView2  # noqa: F401  # type: ignore
        except Exception:
            pass
        return App2
    except Exception as e:
        # Fallback shim
        try:
            import app as _app  # type: ignore

            if hasattr(_app, "App"):
                return _app.App  # type: ignore
        except Exception:
            pass
        raise ImportError(f"App2/app.App import failed: {e}") from e


def main() -> None:
    """Launch integrated GUI (blocking mainloop)."""
    AppCls = _try_import_app2()
    # Instantiate and run
    inst = AppCls()
    try:
        inst.mainloop()
    except KeyboardInterrupt:
        try:
            inst.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    main()
