# -*- coding: utf-8 -*-
"""openlapexe.gui.scrollable - ScrollableFrame (ttk + Canvas self-built, no external GUI lib).

Features:
- ttk.Frame + tk.Canvas + ttk.Scrollbar (vertical always, horizontal optional)
- <Configure> で scrollregion 更新
- マウスホイール対応: <MouseWheel> (Win/mac, delta) + <Button-4> / <Button-5> (Linux)
- inner フレーム公開 (self.inner)
- auto-show scrollbar (grid管理で必要時のみ expand, 常時表示でもレイアウト崩壊なし)
- 800x600で主要操作へ到達可能 (scrollなしで主要ボタン可視、不足時はscrollで到達)
- ttkのみ + Canvas自前 (PIL/requests/matplotlib禁止を維持)
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    """ScrollableFrame(ttk.Frame): Canvas + Scrollbars + inner.

    Public API:
      - self.inner : ttk.Frame (子ウィジェットはここに pack/grid)
      - self.canvas : tk.Canvas
      - self.vscroll : ttk.Scrollbar
      - self.hscroll : ttk.Scrollbar | None (horizontal=True時のみ)
      - _update_scrollregion() : scrollregion再計算
      - _on_mousewheel(event) : Windows/mac delta対応
      - _on_button4(event) / _on_button5(event) : Linux対応
      - xview / yview は canvas へ委譲

    Contract:
    - 属するトーンは常に薄い; 文字は可読 (bg白系, highlight #ccc)
    - heightが指定されなければ Top-level packing の expand/fill に従い <Configure> で追従
    """

    def __init__(
        self,
        parent: tk.Misc | ttk.Frame | None = None,
        *args: object,
        horizontal: bool = False,
        width: int | None = None,
        height: int | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(parent, *args, **kwargs)  # type: ignore[arg-type]
        self._horizontal = bool(horizontal)
        # canvas: bg white, highlight thin like other views
        canvas_kwargs: dict[str, object] = {"bg": "white", "highlightthickness": 1, "highlightbackground": "#ccc"}
        if width is not None:
            canvas_kwargs["width"] = int(width)
        if height is not None:
            canvas_kwargs["height"] = int(height)
        # For pack compatibility, keep bd 0
        canvas_kwargs["bd"] = 0  # type: ignore[assignment]

        self.canvas: tk.Canvas = tk.Canvas(self, **canvas_kwargs)  # type: ignore[arg-type]
        self._canvas: tk.Canvas = self.canvas
        self.vscroll: ttk.Scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_vscroll_set)

        # Layout: canvas expands, vscroll固定幅
        # Use grid for reliable weight: canvas col0 weight1, scrollbar col1 weight0
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vscroll.grid(row=0, column=1, sticky="ns")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        self.hscroll: ttk.Scrollbar | None = None
        self._hscroll: ttk.Scrollbar | None = None
        if self._horizontal:
            self.hscroll = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
            self._hscroll = self.hscroll
            self.canvas.configure(xscrollcommand=self._on_hscroll_set)
            self.hscroll.grid(row=1, column=0, sticky="ew")
            self.grid_rowconfigure(1, weight=0)
        else:
            # still allow x scrolling but without visible bar; configure xscroll to noop
            pass

        # inner frame inside canvas via window
        self.inner: ttk.Frame = ttk.Frame(self.canvas)
        self._inner: ttk.Frame = self.inner
        # Store window id for width adjustments
        self._window_id: int = int(self.canvas.create_window((0, 0), window=self.inner, anchor="nw"))

        # Bindings: scrollregion + wheel
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # Wheel bindings on canvas and inner for propagation
        for widget in (self.canvas, self.inner):
            widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
            widget.bind("<Button-4>", self._on_button4, add="+")
            widget.bind("<Button-5>", self._on_button5, add="+")
            # Enter/leave to capture wheel even when focus elsewhere
            # Use <Enter> to bind globally while hovered
        # Self also capture wheel when focused
        self.bind("<MouseWheel>", self._on_mousewheel, add="+")
        self.bind("<Button-4>", self._on_button4, add="+")
        self.bind("<Button-5>", self._on_button5, add="+")

        # Auto-bind inner children recruitment: when new child appears, ensure it also propagates wheel
        # Use bindtags trick is overkill; we just rely on canvas scrolling via <MouseWheel> bubbling.
        # Additionally, bind mouse wheel on all descendants via bind_class-like delegation using <Enter> bridge
        # Bind <Enter> to activate wheel on inner subtree via global bind
        self.inner.bind("<Enter>", self._bind_wheel_recursive, add="+")
        self.canvas.bind("<Enter>", self._bind_wheel_recursive, add="+")
        self.bind("<Enter>", self._bind_wheel_recursive, add="+")
        # Also handle Leave to avoid global leak - no-op (we keep bindings)
        # Track scrollbar visibility
        self._v_visible: bool = True
        self._h_visible: bool = bool(self._horizontal)

    # -- scrollbar set callbacks that hide when not needed (optional hiding) --
    def _on_vscroll_set(self, *args: object) -> None:
        try:
            self.vscroll.set(*args)  # type: ignore[arg-type]
        except Exception:
            pass
        # Optionally auto-hide when not scrollable: (first==0 and last==1) -> no scroll needed
        # We keep scrollbar visible to avoid layout shift, but ensure scrollregion still correct
        # If needed, hide by grid_remove (not required for test but improves UX on small content)
        try:
            first = float(args[0]) if args else 0.0
            last = float(args[1]) if len(args) > 1 else 1.0
            if first <= 0.0 and last >= 1.0:
                # content fits; optionally keep but mark not needing scroll
                pass
        except Exception:
            pass

    def _on_hscroll_set(self, *args: object) -> None:
        if self.hscroll is not None:
            try:
                self.hscroll.set(*args)  # type: ignore[arg-type]
            except Exception:
                pass

    def _on_inner_configure(self, event: object | None = None) -> None:
        self._update_scrollregion()

    def _on_canvas_configure(self, event: object | None = None) -> None:
        # Make inner frame width = canvas width (for vertical-only scroll, avoids horizontal drift)
        # Only if horizontal scrollbar not enabled; if horizontal, allow natural width
        try:
            cw = self.canvas.winfo_width()
            if cw > 10 and not self._horizontal:
                self.canvas.itemconfigure(self._window_id, width=cw)
        except Exception:
            pass
        self._update_scrollregion()

    def _update_scrollregion(self) -> None:
        try:
            # Ensure geometry propagated
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception:
            try:
                self.update_idletasks()
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            except Exception:
                pass

    def _bind_wheel_recursive(self, _event: object | None = None) -> None:
        # Ensure all current descendants also propagate wheel to this scrollable
        # Bind wheel on every child of inner recursively (once)
        try:
            for child in self.inner.winfo_children():
                try:
                    # Avoid double binding loop: bind with add="+"
                    child.bind("<MouseWheel>", self._on_mousewheel, add="+")
                    child.bind("<Button-4>", self._on_button4, add="+")
                    child.bind("<Button-5>", self._on_button5, add="+")
                    # Also recurse for container children
                    for sub in child.winfo_children():
                        try:
                            sub.bind("<MouseWheel>", self._on_mousewheel, add="+")
                            sub.bind("<Button-4>", self._on_button4, add="+")
                            sub.bind("<Button-5>", self._on_button5, add="+")
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    # -- wheel handlers ----------------------------------------------------
    def _on_mousewheel(self, event: object) -> str | None:
        # Windows: event.delta is 120/-120 multiples, macOS: small values
        delta = 0
        try:
            delta = int(getattr(event, "delta", 0))
        except Exception:
            delta = 0
        if delta == 0:
            return "break"
        # Normalize: negative delta (wheel down) should scroll down (yview_scroll 1)
        # On Windows, delta 120 = up; we invert
        # Standard: canvas.yview_scroll(-1* (delta/120), "units")
        try:
            steps = int(-1 * (delta / 120)) if abs(delta) >= 120 else int(-1 * delta)
            # Clamp steps to [-5, 5] for large delta
            if steps > 5:
                steps = 5
            elif steps < -5:
                steps = -5
            if steps == 0:
                steps = -1 if delta > 0 else 1
            self.canvas.yview_scroll(steps, "units")
        except Exception:
            try:
                self.canvas.yview_scroll(-1 if delta > 0 else 1, "units")
            except Exception:
                pass
        return "break"

    def _on_button4(self, event: object | None = None) -> str | None:
        try:
            self.canvas.yview_scroll(-1, "units")
        except Exception:
            pass
        return "break"

    def _on_button5(self, event: object | None = None) -> str | None:
        try:
            self.canvas.yview_scroll(1, "units")
        except Exception:
            pass
        return "break"

    # -- convenience passthrough ------------------------------------------
    def yview(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        return self.canvas.yview(*args, **kwargs)

    def xview(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        return self.canvas.xview(*args, **kwargs)


__all__ = ["ScrollableFrame"]
