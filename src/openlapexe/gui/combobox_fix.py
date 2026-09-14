# -*- coding: utf-8 -*-
"""openlapexe.gui.combobox_fix - CJK-aware width fixes."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
import unicodedata
import re
def _is_wide(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ("W", "F")
def display_width(text: str) -> int:
    return sum(2 if _is_wide(c) else 1 for c in str(text))
def cjk_safe_truncate(text: str, max_cells: int, ellipsis: str = "…") -> str:
    if max_cells <= 0:
        return ""
    ell_w = display_width(ellipsis)
    s = str(text)
    if display_width(s) <= max_cells:
        return s
    target = max_cells - ell_w
    if target <= 0:
        return ellipsis[:max_cells]
    cur = 0
    out = []
    for ch in s:
        w = 2 if _is_wide(ch) else 1
        if cur + w > target:
            break
        out.append(ch)
        cur += w
    return "".join(out) + ellipsis
def _measure_px(widget: tk.Widget, text: str, font: tkfont.Font | None = None) -> int:
    try:
        if font is None:
            try:
                fname = widget.cget("font")  # type: ignore
                if fname:
                    try:
                        font = tkfont.nametofont(fname)
                    except Exception:
                        font = tkfont.Font(font=fname)
                else:
                    font = tkfont.nametofont("TkDefaultFont")
            except Exception:
                font = tkfont.nametofont("TkDefaultFont")
        return int(font.measure(str(text)))
    except Exception:
        w = 0
        for c in str(text):
            w += 13 if _is_wide(c) else 7
        return w + 4
def fix_combobox(cb: ttk.Combobox, values: list[str] | None = None, max_chars: int = 40, min_chars: int = 12, max_px: int = 520) -> None:
    try:
        vals = list(values) if values is not None else list(cb.cget("values") or [])
        if not vals:
            return
        needed_cells = max(display_width(str(v)) for v in vals) + 2
        need_px = 0
        for v in vals:
            px = _measure_px(cb, v)
            if px > need_px:
                need_px = px
        need_px += 28
        target_cells = needed_cells
        if target_cells > max_chars:
            target_cells = max_chars
        if target_cells < min_chars:
            target_cells = min_chars
        if need_px > max_px:
            need_px = max_px
        try:
            cb.configure(width=target_cells)
        except Exception:
            cb["width"] = target_cells  # type: ignore
        def _post():
            try:
                cur_vals = list(cb.cget("values") or [])
                if cur_vals:
                    np = max(_measure_px(cb, v) for v in cur_vals) + 28
                    if np > max_px:
                        np = max_px
                    cb.after(8, lambda: _apply_popdown_width(cb, np))
                else:
                    cb.after(8, lambda: _apply_popdown_width(cb, need_px))
            except Exception:
                pass
        try:
            cb.configure(postcommand=_post)
        except Exception:
            cb.bind("<Button-1>", lambda _e: _post(), add="+")
        try:
            tip = _get_tooltip(cb)
            def _on_enter(_e=None):
                try:
                    cur = cb.get().strip()
                    if cur and display_width(cur) > int(cb.cget("width") or 12):
                        tip.show(cur)
                except Exception:
                    pass
            def _on_leave(_e=None):
                tip.hide()
            cb.bind("<Enter>", _on_enter, add="+")
            cb.bind("<Leave>", _on_leave, add="+")
            cb.bind("<FocusOut>", _on_leave, add="+")
            cb.bind("<<ComboboxSelected>>", _on_leave, add="+")
        except Exception:
            pass
        try:
            cb._cjk_fixed = True  # type: ignore
        except Exception:
            pass
    except Exception:
        pass
def _apply_popdown_width(cb: ttk.Combobox, need_px: int) -> None:
    try:
        popdown = cb.tk.call("ttk::combobox::PopdownWindow", str(cb))
        if not popdown:
            return
        p = str(popdown)
        try:
            cur = cb.tk.call("wm", "geometry", p)
            m = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", str(cur))
            if m:
                h = m.group(2); x = m.group(3); y = m.group(4)
                cb.tk.call("wm", "geometry", p, f"{int(need_px)}x{h}+{x}+{y}")
                try:
                    chars = max(12, int(need_px / 7))
                    cb.tk.call(p + ".f.l", "configure", "-width", str(chars))
                except Exception:
                    pass
                return
        except Exception:
            pass
        chars = max(12, int(need_px / 7))
        cb.tk.call(p + ".f.l", "configure", "-width", str(chars))
    except Exception:
        pass
class _SimpleTooltip:
    def __init__(self, widget: tk.Widget): self.widget=widget; self.tip=None
    def show(self, text, x=None, y=None):
        self.hide()
        try:
            tw=tk.Toplevel(self.widget); tw.wm_overrideredirect(True); tw.configure(bg="#ffffe0")
            try: tw.attributes("-topmost", True)
            except: pass
            tk.Label(tw, text=str(text), bg="#ffffe0", fg="#222", relief="solid", borderwidth=1, font=("TkDefaultFont",8), padx=4, pady=2).pack()
            if x is None or y is None:
                try: bx=self.widget.winfo_rootx()+12; by=self.widget.winfo_rooty()+self.widget.winfo_height()+4
                except: bx,by=100,100
            else: bx,by=x,y
            tw.wm_geometry(f"+{int(bx)}+{int(by)}"); self.tip=tw
        except: self.tip=None
    def hide(self):
        try:
            if self.tip: self.tip.destroy()
        except: pass
        self.tip=None
def _get_tooltip(w):
    if not hasattr(_get_tooltip,"cache"): _get_tooltip.cache={}  # type: ignore
    c=_get_tooltip.cache  # type: ignore
    if id(w) not in c: c[id(w)]=_SimpleTooltip(w)
    return c[id(w)]
def fix_treeview_horizontal(tree: ttk.Treeview, container=None) -> None:
    try:
        parent = container if container is not None else tree.master
        has_hsb=False
        for ch in parent.winfo_children():
            try:
                if ch.winfo_class()=="TScrollbar" and str(ch.cget("orient"))=="horizontal" and str(tree) in str(ch.cget("command")):
                    has_hsb=True; break
            except: continue
        if not has_hsb:
            hsb=ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
            tree.configure(xscrollcommand=hsb.set)
            hsb.pack(side="bottom", fill="x")
            tree._hsb=hsb  # type: ignore
    except: pass
    try:
        tip=_get_tooltip(tree)
        def _on_motion(e):
            try:
                row=tree.identify_row(e.y); col=tree.identify_column(e.x)
                if not row or col=="#0": tip.hide(); return
                col_idx=int(col[1:])-1; cols=list(tree["columns"])
                if 0 <= col_idx < len(cols):
                    cname=str(cols[col_idx]); val=str(tree.set(row,cname))
                    if not val: tip.hide(); return
                    col_w=int(tree.column(cname,"width") or 100)
                    need_px=_measure_px(tree,val)
                    if need_px+12>col_w: tip.show(val, x=e.x_root+8, y=e.y_root+12)
                    else: tip.hide()
            except: tip.hide()
        def _on_leave(_e=None): tip.hide()
        tree.bind("<Motion>", _on_motion, add="+")
        tree.bind("<Leave>", _on_leave, add="+")
    except: pass
    try:
        for c in list(tree["columns"] or []):
            if str(c).lower() in ("name","file","track","vehicle","course"):
                vals=[]
                for iid in tree.get_children():
                    try: vals.append(str(tree.set(iid,c)))
                    except: pass
                if vals:
                    max_cells=max(display_width(v) for v in vals)
                    try: hdr=str(tree.heading(c,"text") or c); max_cells=max(max_cells, display_width(hdr)+2)
                    except: pass
                    px=max_cells*8+16
                    if px<80: px=80
                    if px>320: px=320
                    try: tree.column(c, width=px, minwidth=60, stretch=False)
                    except: tree.column(c, width=px)
    except: pass
def fix_listbox_horizontal(lb: tk.Listbox, parent=None) -> None:
    try:
        par=parent if parent is not None else lb.master
        has_hsb=False
        for ch in par.winfo_children():
            try:
                if ch.winfo_class()=="Scrollbar" and str(ch.cget("orient"))=="horizontal": has_hsb=True; break
            except: continue
        if not has_hsb:
            hsb=tk.Scrollbar(par, orient="horizontal", command=lb.xview)
            lb.configure(xscrollcommand=hsb.set)
            hsb.pack(side="bottom", fill="x")
            lb._hsb=hsb  # type: ignore
        try: lb.configure(wrap="none")
        except: pass
        tip=_get_tooltip(lb)
        def _on_motion(e):
            try:
                idx=lb.nearest(e.y); val=str(lb.get(idx))
                need_px=_measure_px(lb,val)
                lb_w=int(lb.winfo_width() or 200)
                if need_px+12>lb_w: tip.show(val, x=e.x_root+8, y=e.y_root+12)
                else: tip.hide()
            except: tip.hide()
        def _on_leave(_e=None): tip.hide()
        lb.bind("<Motion>", _on_motion, add="+")
        lb.bind("<Leave>", _on_leave, add="+")
    except: pass
__all__=["display_width","cjk_safe_truncate","fix_combobox","fix_treeview_horizontal","fix_listbox_horizontal"]
