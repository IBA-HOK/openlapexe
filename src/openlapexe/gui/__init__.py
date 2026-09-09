# -*- coding: utf-8 -*-
"""openlapexe.gui package scaffold."""
from __future__ import annotations

try:
    from openlapexe.gui.track_view import TrackView, TrackView2  # noqa: F401
except Exception:
    TrackView = None  # type: ignore
    TrackView2 = None  # type: ignore

try:
    from openlapexe.gui.drag_view import DragView, DragView2  # noqa: F401
except Exception:
    DragView = None  # type: ignore
    DragView2 = None  # type: ignore

__all__: list[str] = ["TrackView", "TrackView2", "DragView", "DragView2"]
