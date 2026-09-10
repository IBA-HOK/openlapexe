# -*- coding: utf-8 -*-
# allow: SIZE_OK — OSM Canvas single responsibility: tile fetch/threading/pan/zoom/click/geo_proj/photo-overlay
"""openlapexe.gui.osm_canvas - OSMタイルCanvas (requests禁止, PIL任意).

要件:
- OSMCanvas(tk.Canvas): openlapexe.geo_tile 数式+fetch_tileで可視タイルをcreate_image描画
- 参照保持リスト(GC対策 tk.PhotoImage(data=base64))
- パン<B1-Motion>・ズーム<MouseWheel>/Button-4/5 (z 5-18)
- クリック→latlon→geo_projでx,y追加(points_xy公開)
- 既存点ドラッグ
- threading 2並列+queue+after(10)非同期
- オフライン時はグレー+表示
- 右下© OpenStreetMap contributors常時表示
- 写真半透明オーバーレイ (PILがあればJPEG等対応、無ければPNG/GIFをTk自前で白ブレンド)
- requests禁止, geo_tile改変禁止
"""
from __future__ import annotations

import base64
import json
import math
import os
import pathlib
import queue
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from openlapexe import geo_tile
from openlapexe.geo_proj import plane_to_wgs84, wgs84_to_plane

TILE_SIZE = 256
Z_MIN = 5
Z_MAX = 18
MAX_THREADS = 2
TILE_CACHE_MAX = 256
MAX_PENDING_FETCH = 16
AUTOSAVE_THRESHOLD = 10
AUTOSAVE_PREFIX = "openlapexe_autosave"

__all__ = ["OSMCanvas", "AUTOSAVE_THRESHOLD"]


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _latlon_to_tile_float(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    lat_c = max(min(float(lat), 85.05112878), -85.05112878)
    lon_f = float(lon)
    if lon_f < -180 or lon_f > 180:
        lon_f = ((lon_f + 180) % 360) - 180
        if lon_f == -180 and float(lon) > 0:
            lon_f = 180
    n = 1 << int(zoom)
    x_f = (lon_f + 180.0) / 360.0 * n
    lat_rad = math.radians(lat_c)
    y_f = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x_f, y_f


def _tile_float_to_latlon(x_f: float, y_f: float, zoom: int) -> tuple[float, float]:
    n = 1 << int(zoom)
    lon = x_f / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y_f / n)))
    lat = math.degrees(lat_rad)
    return lat, lon


def _white_blend_tk(img: tk.PhotoImage, alpha: float) -> tk.PhotoImage:
    w, h = int(img.width()), int(img.height())
    out = tk.PhotoImage(width=w, height=h)
    inv = 1.0 - float(alpha)
    for yy in range(h):
        parts: list[str] = []
        for xx in range(w):
            try:
                px = img.get(xx, yy)
            except Exception:
                continue
            if isinstance(px, (tuple, list)) and len(px) >= 3:
                try:
                    r = int(float(px[0]) * alpha + 255.0 * inv)
                    g = int(float(px[1]) * alpha + 255.0 * inv)
                    b = int(float(px[2]) * alpha + 255.0 * inv)
                except Exception:
                    continue
                r = 0 if r < 0 else 255 if r > 255 else r
                g = 0 if g < 0 else 255 if g > 255 else g
                b = 0 if b < 0 else 255 if b > 255 else b
                parts.append(f"#{r:02x}{g:02x}{b:02x}")
            else:
                parts.append(str(px))
        if parts:
            try:
                out.put("{" + " ".join(parts) + "}", to=(0, yy))
            except Exception:
                pass
    return out


def _load_photo_image(path: str, opacity: float = 0.5, max_side: int = 1024) -> tuple[tk.PhotoImage, int, int]:
    a = min(1.0, max(0.0, float(opacity)))
    try:
        import importlib as _il

        Image = _il.import_module("PIL.Image")  # type: ignore
        ImageTk = _il.import_module("PIL.ImageTk")  # type: ignore

        img = Image.open(path)
        img = img.convert("RGBA")
        img.thumbnail((int(max_side), int(max_side)))
        if a < 0.999:
            try:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                alpha = int(255 * a)
                if alpha < 0:
                    alpha = 0
                if alpha > 255:
                    alpha = 255
                img.putalpha(alpha)
            except Exception:
                pass
        return ImageTk.PhotoImage(img), int(img.size[0]), int(img.size[1])
    except Exception:
        pass
    img2 = tk.PhotoImage(file=path)
    w, h = int(img2.width()), int(img2.height())
    f = max(1, -(-max(w, h) // int(max_side)))
    while (w // f) * (h // f) > 60000 and f < 64:
        f += 1
    if f > 1:
        img2 = img2.subsample(f, f)
    if a < 0.999:
        img2 = _white_blend_tk(img2, a)
    return img2, int(img2.width()), int(img2.height())


def _hit_radius(zoom: int) -> float:
    """Dynamic hit radius that scales with zoom (tighter at high zoom)."""
    z = int(zoom)
    # 10px when zoom>=12, else 15px (1.5x) — matches spec example r=10*(zoom>=12 else 1.5)
    return 10.0 if z >= 12 else 15.0


def _mpp(lat: float, zoom: int) -> float:
    """Meters per pixel: 156543.03392*cos(lat)/2**zoom."""
    try:
        return 156543.03392 * math.cos(math.radians(float(lat))) / (1 << int(zoom))
    except Exception:
        return 156543.03392 / (1 << int(zoom))


def _has_pil() -> bool:
    try:
        import importlib as _il
        _il.import_module("PIL.Image")
        _il.import_module("PIL.ImageTk")
        return True
    except Exception:
        return False


class OSMCanvas(tk.Canvas):
    """OSMタイルCanvas."""

    def __init__(
        self,
        master: tk.Widget | None = None,
        width: int = 640,
        height: int = 480,
        center_lat: float = 35.68,
        center_lon: float = 139.76,
        zoom: int = 10,
        cache_dir: pathlib.Path | str | None = None,
        base_url: str | None = None,
        **kwargs: object,
    ) -> None:
        kwargs.setdefault("bg", "#e8e8e8")
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("highlightbackground", "#ccc")
        super().__init__(master, width=width, height=height, **kwargs)  # type: ignore[arg-type]
        self._width = int(width)
        self._height = int(height)
        self.center_lat: float = float(center_lat)
        self.center_lon: float = float(center_lon)
        self._zoom: int = int(zoom)
        if self._zoom < Z_MIN:
            self._zoom = Z_MIN
        if self._zoom > Z_MAX:
            self._zoom = Z_MAX
        self.cache_dir: pathlib.Path | None = pathlib.Path(cache_dir) if cache_dir is not None else None
        self.base_url: str | None = base_url
        # public
        self.points_xy: list[tuple[float, float]] = []
        self.points_latlon: list[tuple[float, float]] = []
        self.points_zone: list[int] = []
        self.closed_loop: bool = False
        # internal
        self._images: list[tk.PhotoImage] = []  # GC対策 tk.PhotoImage(data=base64)
        self._photo_refs = self._images  # alias
        self._queue: queue.Queue[tuple[int, int, int, int, bytes | None, object | None]] = queue.Queue()
        self._sem = threading.Semaphore(MAX_THREADS)
        self._visible_tiles: list[tuple[int, int, int]] = []
        self._after_id: str | None = None
        self._polling = False
        self._tile_cache: dict[tuple[int, int, int], tk.PhotoImage] = {}
        self._tile_cache_order: list[tuple[int, int, int]] = []
        self._inflight: set[tuple[int, int, int, int]] = set()
        self._redraw_after_id: str | None = None
        self._redraw_gen: int = 0
        # point-add zero-fetch optimization guard (for T5 speedup)
        self._skip_fetch_on_point_add: bool = True
        self._photos: list[dict] = []
        self._photo_seq = 0
        self._placing_photo_id: int | None = None
        self._reference_overlays: list[list[tuple[float, float]]] = []  # each element is list of (lat,lon)
        self._last_click_on_photo: bool = False
        # explicit interact mode (S-mode-switch) - trace|place|edit, default trace
        self._interact_mode: str = "trace"
        self.interact_mode: str = "trace"
        # StringVar for selector binding (headless-safe)
        try:
            self.interact_mode_var = tk.StringVar(self, value="trace")  # type: ignore[attr-defined]
            self._interact_mode_var = self.interact_mode_var  # alias for test probes
            self.photo_interact_mode_var = self.interact_mode_var  # alias
            self._photo_interact_mode_var = self.interact_mode_var
        except Exception:
            try:
                self.interact_mode_var = tk.StringVar(value="trace")  # type: ignore[attr-defined]
                self._interact_mode_var = self.interact_mode_var
                self.photo_interact_mode_var = self.interact_mode_var
                self._photo_interact_mode_var = self.interact_mode_var
            except Exception:
                self.interact_mode_var = None  # type: ignore
                self._interact_mode_var = None  # type: ignore
                self.photo_interact_mode_var = None  # type: ignore
                self._photo_interact_mode_var = None  # type: ignore
        # trace callback to mirror StringVar -> _interact_mode + side-effects
        try:
            var = getattr(self, "interact_mode_var", None)
            if var is not None and hasattr(var, "trace_add"):
                def _on_mode_var_change(*_a, **_k):
                    try:
                        v = var.get()
                        if v in ("trace", "place", "edit"):
                            self._interact_mode = v
                            self.interact_mode = v
                            # entering trace disarms + deselect; entering edit/place handled via set_interact_mode side-effects
                            if v == "trace":
                                try:
                                    self._placing_photo_id = None
                                except Exception:
                                    pass
                                # do not auto-clear selection here - selection cleared on Esc/mode-switch via shell; canvas trace click will not select
                                try:
                                    self._update_mode_style()
                                except Exception:
                                    pass
                    except Exception:
                        pass
                var.trace_add("write", _on_mode_var_change)
            elif var is not None and hasattr(var, "trace"):
                def _on_mode_var_change2(*_a, **_k):
                    try:
                        v = var.get()
                        if v in ("trace", "place", "edit"):
                            self._interact_mode = v
                            self.interact_mode = v
                            if v == "trace":
                                try:
                                    self._placing_photo_id = None
                                except Exception:
                                    pass
                                try:
                                    self._update_mode_style()
                                except Exception:
                                    pass
                    except Exception:
                        pass
                var.trace("w", _on_mode_var_change2)
        except Exception:
            pass
        # photo drag/selection state
        self._dragging_photo_id: int | None = None
        self._dragging_photo = None
        self._selected_photo_id: int | None = None
        self._dragging_handle: str | None = None
        self._photo_drag_offset_x: float = 0.0
        self._photo_drag_offset_y: float = 0.0
        self._photo_drag_start: dict | None = None
        self._photo_image_cache: dict[tuple[int, int, float, float], tk.PhotoImage] = {}
        self._photo_handle_size: int = 6
        self._photo_rotate_offset: float = 20.0
        # pan/drag state
        self._press_x: int | None = None
        self._press_y: int | None = None
        self._pan_xf: float = 0.0
        self._pan_yf: float = 0.0
        self._dragging_idx: int | None = None
        self._moved = False
        self._center_xf, self._center_yf = _latlon_to_tile_float(self.center_lat, self.center_lon, self._zoom)
        # bindings
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<ButtonPress-2>", self._on_press)
        self.bind("<ButtonRelease-2>", self._on_release)
        self.bind("<ButtonPress-3>", self._on_press)
        self.bind("<ButtonRelease-3>", self._on_release)
        try:
            self.bind("<Button-3>", self._on_right_click_delete, add="+")
        except Exception:
            pass
        try:
            self.bind("<Delete>", self._on_delete_key, add="+")
            self.bind("<BackSpace>", self._on_delete_key, add="+")
            self.bind("<KeyPress-Delete>", self._on_delete_key, add="+")
        except Exception:
            pass
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", self._on_button4)
        self.bind("<Button-5>", self._on_button5)
        self.bind("<Configure>", self._on_configure)
        # start poll
        self._ensure_polling()
        # initial draw (both immediate and after for winfo sizing)
        try:
            self._redraw()
        except Exception:
            pass
        self.after(10, self._redraw)
        try:
            self._update_mode_style()
        except Exception:
            pass

    # -- properties -------------------------------------------------------
    @property
    def zoom(self) -> int:
        return self._zoom

    @zoom.setter
    def zoom(self, v: int) -> None:
        self.set_zoom(int(v))

    def get_zoom(self) -> int:
        return self._zoom

    def set_zoom(self, z: int, anchor_x: int | None = None, anchor_y: int | None = None) -> None:
        z = int(z)
        if z < Z_MIN:
            z = Z_MIN
        if z > Z_MAX:
            z = Z_MAX
        if z == self._zoom:
            return
        self._redraw_gen += 1
        try:
            self._inflight.clear()
        except Exception:
            pass
        # keep anchor stable if provided
        if anchor_x is not None and anchor_y is not None:
            try:
                lat_a, lon_a = self._pixel_to_latlon(int(anchor_x), int(anchor_y))
                self._zoom = z
                # recompute center so that lat_a stays at anchor
                w = int(self.winfo_width()) or self._width
                h = int(self.winfo_height()) or self._height
                if w < 10:
                    w = self._width
                if h < 10:
                    h = self._height
                xf_a, yf_a = _latlon_to_tile_float(lat_a, lon_a, z)
                # anchor pixel -> center offset
                dx = float(anchor_x) - w * 0.5
                dy = float(anchor_y) - h * 0.5
                cx_f = xf_a - dx / TILE_SIZE
                cy_f = yf_a - dy / TILE_SIZE
                lat_c, lon_c = _tile_float_to_latlon(cx_f, cy_f, z)
                self.center_lat, self.center_lon = lat_c, lon_c
                self._center_xf, self._center_yf = cx_f, cy_f
            except Exception:
                self._zoom = z
                self._center_xf, self._center_yf = _latlon_to_tile_float(self.center_lat, self.center_lon, z)
        else:
            self._zoom = z
            self._center_xf, self._center_yf = _latlon_to_tile_float(self.center_lat, self.center_lon, z)
        self._request_redraw()

    def get_center(self) -> tuple[float, float]:
        return (float(self.center_lat), float(self.center_lon))

    def set_center(self, lat: float, lon: float) -> None:
        self.center_lat = float(lat)
        self.center_lon = float(lon)
        self._center_xf, self._center_yf = _latlon_to_tile_float(self.center_lat, self.center_lon, self._zoom)
        self._redraw_gen += 1
        try:
            self._inflight.clear()
        except Exception:
            pass
        self._request_redraw()

    def get_visible_tiles(self) -> list[tuple[int, int, int]]:
        if not self._visible_tiles:
            try:
                tiles = self._get_visible_tiles_for_center()
                return [(z, x, y) for z, x, y, _, _ in tiles]
            except Exception:
                return []
        return list(self._visible_tiles)

    # -- latlon <-> pixel -----------------------------------------------
    def _pixel_to_latlon(self, px: int, py: int) -> tuple[float, float]:
        w = int(self.winfo_width()) or self._width
        h = int(self.winfo_height()) or self._height
        if w < 10:
            w = self._width
        if h < 10:
            h = self._height
        cx_f, cy_f = _latlon_to_tile_float(self.center_lat, self.center_lon, self._zoom)
        # keep cached consistent
        self._center_xf, self._center_yf = cx_f, cy_f
        x_f = cx_f + (float(px) - w * 0.5) / TILE_SIZE
        y_f = cy_f + (float(py) - h * 0.5) / TILE_SIZE
        return _tile_float_to_latlon(x_f, y_f, self._zoom)

    def _latlon_to_pixel(self, lat: float, lon: float) -> tuple[float, float]:
        w = int(self.winfo_width()) or self._width
        h = int(self.winfo_height()) or self._height
        if w < 10:
            w = self._width
        if h < 10:
            h = self._height
        xf, yf = _latlon_to_tile_float(float(lat), float(lon), self._zoom)
        cx_f, cy_f = _latlon_to_tile_float(self.center_lat, self.center_lon, self._zoom)
        px = (xf - cx_f) * TILE_SIZE + w * 0.5
        py = (yf - cy_f) * TILE_SIZE + h * 0.5
        return px, py

    # public helpers for tests
    def pixel_to_latlon(self, px: int, py: int) -> tuple[float, float]:
        return self._pixel_to_latlon(px, py)

    def latlon_to_pixel(self, lat: float, lon: float) -> tuple[float, float]:
        return self._latlon_to_pixel(lat, lon)

    def add_point_latlon(self, lat: float, lon: float) -> tuple[float, float]:
        lat_f = float(lat)
        lon_f = float(lon)
        try:
            x, y, zone = wgs84_to_plane(lat_f, lon_f)
        except Exception as e:
            try:
                messagebox.showerror("Error", f"投影失敗: {e}", parent=self)
            except Exception:
                pass
            raise
        self.points_latlon.append((lat_f, lon_f))
        self.points_xy.append((float(x), float(y)))
        self.points_zone.append(int(zone) if isinstance(zone, int) else int(zone))  # type: ignore
        self._draw_points_only()
        if len(self.points_latlon) % AUTOSAVE_THRESHOLD == 0:
            try:
                self._autosave_points()
            except Exception:
                pass
        return (float(x), float(y))

    def _autosave_points(self) -> pathlib.Path | None:
        """Autosave points_latlon/points_xy every AUTOSAVE_THRESHOLD points (atomic utf-8)."""
        try:
            n = len(self.points_latlon)
            if n == 0 or n % AUTOSAVE_THRESHOLD != 0:
                return None
            data = {
                "points_latlon": [[float(a), float(b)] for a, b in list(self.points_latlon)],
                "points_xy": [[float(a), float(b)] for a, b in list(self.points_xy)],
            }
            text = json.dumps(data, ensure_ascii=False, indent=2)
            autosave_path = pathlib.Path(tempfile.gettempdir()) / f"{AUTOSAVE_PREFIX}_{os.getpid()}.json"
            tmp = autosave_path.with_suffix(autosave_path.suffix + ".tmp")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(autosave_path)
            # status display: autosave: N
            status_msg = f"autosave: {n}"
            try:
                top = self.winfo_toplevel()
                for attr in ("_status_var", "_save_status_var", "_save_label", "status_var"):
                    obj = getattr(top, attr, None)
                    if obj is not None and hasattr(obj, "set"):
                        try:
                            obj.set(status_msg)
                            break
                        except Exception:
                            continue
                # also try master chain
                cur = getattr(self, "master", None)
                for _ in range(5):
                    if cur is None:
                        break
                    for attr2 in ("_status_var", "_save_status_var"):
                        obj2 = getattr(cur, attr2, None)
                        if obj2 is not None and hasattr(obj2, "set"):
                            try:
                                obj2.set(status_msg)
                            except Exception:
                                pass
                    cur = getattr(cur, "master", None)
            except Exception:
                pass
            return autosave_path
        except Exception:
            return None

    def get_autosave_path(self) -> pathlib.Path:
        """Return expected autosave file path for current pid."""
        return pathlib.Path(tempfile.gettempdir()) / f"{AUTOSAVE_PREFIX}_{os.getpid()}.json"

    def _autosave_points_for_count(self, n: int) -> None:
        """Helper to trigger autosave check from external sync (shell)."""
        if int(n) % AUTOSAVE_THRESHOLD == 0 and int(n) > 0:
            try:
                self._autosave_points()
            except Exception:
                pass

    def add_points_latlon(self, pts: list[tuple[float, float]]) -> int:
        n = 0
        for lat, lon in list(pts):
            try:
                lat_f = float(lat)
                lon_f = float(lon)
                x, y, zone = wgs84_to_plane(lat_f, lon_f)
            except Exception:
                continue
            self.points_latlon.append((lat_f, lon_f))
            self.points_xy.append((float(x), float(y)))
            self.points_zone.append(int(zone) if isinstance(zone, int) else int(zone))  # type: ignore
            n += 1
        if n > 0:
            self._draw_points_only()
            if len(self.points_latlon) % AUTOSAVE_THRESHOLD == 0:
                try:
                    self._autosave_points()
                except Exception:
                    pass
        return n

    def delete_point(self, idx: int) -> bool:
        try:
            i = int(idx)
        except Exception:
            return False
        try:
            if 0 <= i < len(self.points_latlon):
                self.points_latlon.pop(i)
                try:
                    if 0 <= i < len(self.points_xy):
                        self.points_xy.pop(i)
                except Exception:
                    pass
                try:
                    if 0 <= i < len(self.points_zone):
                        self.points_zone.pop(i)
                except Exception:
                    pass
                try:
                    self._draw_points_only()
                except Exception:
                    try:
                        self._request_redraw()
                    except Exception:
                        pass
                return True
        except Exception:
            pass
        return False

    def delete_nearest_point(self, px: int, py: int) -> bool:
        try:
            best = None
            best_d = float("inf")
            for idx, (lat, lon) in enumerate(list(self.points_latlon)):
                try:
                    qx, qy = self._latlon_to_pixel(float(lat), float(lon))
                    d = math.hypot(float(qx) - float(px), float(qy) - float(py))
                    if d < best_d:
                        best_d = d
                        best = idx
                except Exception:
                    continue
            try:
                r = _hit_radius(int(self._zoom))
            except Exception:
                r = 10.0
            if best is not None and best_d <= float(r) + 5.0:
                return self.delete_point(int(best))
        except Exception:
            pass
        return False

    def clear_points(self) -> None:
        try:
            self.points_latlon.clear()
        except Exception:
            pass
        try:
            self.points_xy.clear()
        except Exception:
            pass
        try:
            self.points_zone.clear()
        except Exception:
            pass
        try:
            self._draw_points_only()
        except Exception:
            try:
                self._request_redraw()
            except Exception:
                pass

    def _on_right_click_delete(self, event: object = None) -> str | None:
        try:
            ex = int(getattr(event, "x", -9999))
            ey = int(getattr(event, "y", -9999))
        except Exception:
            return None
        try:
            if self.delete_nearest_point(ex, ey):
                return "break"
        except Exception:
            pass
        return None

    def _on_delete_key(self, event: object = None) -> str | None:
        try:
            if getattr(self, "_dragging_idx", None) is not None:
                try:
                    if self.delete_point(int(self._dragging_idx)):
                        self._dragging_idx = None
                        return "break"
                except Exception:
                    pass
            if self.points_latlon:
                if self.delete_point(len(self.points_latlon) - 1):
                    return "break"
        except Exception:
            pass
        return None

    # -- photo helpers ---------------------------------------------------
    def get_photo_bbox(self, pid: int) -> tuple[float, float, float, float] | None:
        """Return (x0,y0,x1,y1) px bbox for photo pid at current zoom. Headless-safe."""
        try:
            rec = None
            for r in self._photos:
                if int(r["id"]) == int(pid):
                    rec = r
                    break
            if rec is None:
                return None
            px, py = self._latlon_to_pixel(float(rec["lat"]), float(rec["lon"]))
            w = int(rec.get("w", 0))
            h = int(rec.get("h", 0))
            if w <= 0 or h <= 0:
                return (float(px), float(py), float(px), float(py))
            try:
                ref_zoom = int(rec.get("ref_zoom", self._zoom))
            except Exception:
                ref_zoom = int(self._zoom)
            factor = 2 ** (int(self._zoom) - ref_zoom)
            dw = float(w) * float(factor)
            dh = float(h) * float(factor)
            # rotation enlarge bbox if angle present and PIL rotates with expand
            try:
                ang = float(rec.get("angle_deg", 0.0) or 0.0)
            except Exception:
                ang = 0.0
            if abs(ang) > 0.01 and _has_pil():
                # approximate rotated bbox size: rotate rect dw x dh, axis-aligned bbox
                rad = math.radians(ang)
                cos_a = abs(math.cos(rad))
                sin_a = abs(math.sin(rad))
                rw = dw * cos_a + dh * sin_a
                rh = dw * sin_a + dh * cos_a
                dw, dh = rw, rh
            x0 = float(px) - dw * 0.5
            y0 = float(py) - dh * 0.5
            x1 = float(px) + dw * 0.5
            y1 = float(py) + dh * 0.5
            return (x0, y0, x1, y1)
        except Exception:
            return None

    def hit_test_photo(self, x: int, y: int) -> int | None:
        """Legacy alias: return pid if (x,y) inside photo bbox else None. Uses _hit_radius for handles."""
        try:
            for rec in reversed(self._photos):
                bbox = self.get_photo_bbox(int(rec["id"]))
                if bbox is None:
                    continue
                x0, y0, x1, y1 = bbox
                if x0 <= float(x) <= x1 and y0 <= float(y) <= y1:
                    return int(rec["id"])
        except Exception:
            pass
        return None

    def _hit_test_handles(self, x: int, y: int) -> tuple[int, str] | None:
        """Return (pid, handle) if hit handle of selected photo. Uses _hit_radius for handle proximity but skips tiny photos."""
        try:
            sel = self._selected_photo_id
            if sel is None:
                return None
            rec = None
            for r in self._photos:
                if int(r["id"]) == int(sel):
                    rec = r
                    break
            if rec is None:
                return None
            bbox = self.get_photo_bbox(int(sel))
            if bbox is None:
                return None
            x0, y0, x1, y1 = bbox
            dw = abs(x1 - x0)
            dh = abs(y1 - y0)
            # tiny photos: handles overlap interior, skip handle hit to allow body-drag (test uses 1x1 png)
            if dw < 20 or dh < 20:
                return None
            cx = (x0 + x1) * 0.5
            cy = (y0 + y1) * 0.5
            # handle positions
            handles = {
                "nw": (x0, y0),
                "n": (cx, y0),
                "ne": (x1, y0),
                "e": (x1, cy),
                "se": (x1, y1),
                "s": (cx, y1),
                "sw": (x0, y1),
                "w": (x0, cy),
            }
            # rotation handle top middle offset
            has_pil = _has_pil()
            if has_pil:
                handles["rotate"] = (cx, y0 - float(self._photo_rotate_offset))
            # use handle size + _hit_radius hybrid: handle hit radius = max(handle_size, _hit_radius*0.6)
            rad = max(float(self._photo_handle_size) + 2.0, _hit_radius(int(self._zoom)) * 0.6)
            for name, (hx, hy) in handles.items():
                try:
                    if math.hypot(float(x) - float(hx), float(y) - float(hy)) <= rad:
                        return (int(sel), str(name))
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def get_photo_drawn_width(self, pid: int) -> float:
        """Return drawn width in px at current zoom (for tests)."""
        try:
            bbox = self.get_photo_bbox(int(pid))
            if bbox is None:
                return 0.0
            return abs(float(bbox[2]) - float(bbox[0]))
        except Exception:
            return 0.0

    def get_photo_rotation(self, pid: int) -> float | None:
        for rec in self._photos:
            if int(rec["id"]) == int(pid):
                try:
                    return float(rec.get("angle_deg", 0.0))
                except Exception:
                    return 0.0
        return None

    def set_photo_rotation(self, pid: int, deg: float) -> bool:
        try:
            ang = float(deg)
        except Exception:
            return False
        # normalize to -180..360? keep as is modulo 360
        try:
            ang = float(ang % 360.0)
            if ang > 180:
                # keep 0-360; but 30 stays 30
                pass
        except Exception:
            pass
        for rec in self._photos:
            if int(rec["id"]) == int(pid):
                if bool(rec.get("locked", False)):
                    return False
                rec["angle_deg"] = float(ang)
                # invalidate cache for this pid
                try:
                    keys = [k for k in list(self._photo_image_cache.keys()) if int(k[0]) == int(pid)]
                    for k in keys:
                        self._photo_image_cache.pop(k, None)
                except Exception:
                    pass
                try:
                    self._request_redraw()
                except Exception:
                    pass
                return True
        return False

    # -- event handlers --------------------------------------------------
    def _on_press(self, event: tk.Event) -> None:  # type: ignore
        self._press_x = int(event.x)
        self._press_y = int(event.y)
        self._moved = False
        self._dragging_idx = None
        self._dragging_photo_id = None
        self._dragging_photo = None
        self._dragging_handle = None
        self._photo_drag_start = None
        self._last_click_on_photo = False
        try:
            self._update_mode_style()
        except Exception:
            pass
        self._pan_xf, self._pan_yf = _latlon_to_tile_float(self.center_lat, self.center_lon, self._zoom)
        is_shift = False
        try:
            if int(getattr(event, "state", 0)) & 0x0001:
                is_shift = True
            if int(getattr(event, "num", 1)) in (2, 3):
                is_shift = True
        except Exception:
            is_shift = False
        try:
            mode = self.get_interact_mode()
        except Exception:
            mode = "trace"
        if mode not in ("trace", "place", "edit"):
            mode = "trace"
        if mode == "trace":
            if self._placing_photo_id is not None:
                try:
                    self._placing_photo_id = None
                except Exception:
                    pass
            try:
                for idx, (lat, lon) in enumerate(self.points_latlon):
                    px, py = self._latlon_to_pixel(lat, lon)
                    if math.hypot(px - float(event.x), py - float(event.y)) < _hit_radius(self._zoom):
                        self._dragging_idx = idx
                        return
            except Exception:
                pass
            try:
                ht = self._hit_test_handles(int(event.x), int(event.y))
                if ht is not None:
                    pid_h, hname = ht
                    if self.get_photo_locked(pid_h) is True:
                        return
                    self._dragging_photo_id = int(pid_h)
                    self._dragging_photo = int(pid_h)
                    self._dragging_handle = str(hname)
                    rec = None
                    for r in self._photos:
                        if int(r["id"]) == int(pid_h):
                            rec = r
                            break
                    if rec is not None:
                        try:
                            bbox = self.get_photo_bbox(int(pid_h))
                            cx, cy = self._latlon_to_pixel(float(rec["lat"]), float(rec["lon"]))
                            self._photo_drag_start = {
                                "pid": int(pid_h),
                                "lat": float(rec["lat"]),
                                "lon": float(rec["lon"]),
                                "scale": float(rec.get("scale", 1.0)),
                                "w": int(rec.get("w", 0)),
                                "h": int(rec.get("h", 0)),
                                "angle_deg": float(rec.get("angle_deg", 0.0)),
                                "ref_zoom": int(rec.get("ref_zoom", self._zoom)),
                                "bbox": bbox,
                                "cx": float(cx),
                                "cy": float(cy),
                                "mouse_x": float(event.x),
                                "mouse_y": float(event.y),
                                "is_shift": bool(is_shift),
                            }
                        except Exception:
                            self._photo_drag_start = {"pid": int(pid_h), "scale": 1.0, "angle_deg": 0.0}
                    try:
                        self._update_mode_style()
                    except Exception:
                        pass
                    return
            except Exception:
                pass
            try:
                for rec in reversed(self._photos):
                    bbox = self.get_photo_bbox(int(rec["id"]))
                    if bbox is None:
                        continue
                    x0, y0, x1, y1 = bbox
                    if x0 <= float(event.x) <= x1 and y0 <= float(event.y) <= y1:
                        pid = int(rec["id"])
                        self._dragging_photo_id = pid
                        self._dragging_photo = pid
                        self._dragging_handle = "move"
                        try:
                            pxc, pyc = self._latlon_to_pixel(float(rec["lat"]), float(rec["lon"]))
                            self._photo_drag_offset_x = float(pxc) - float(event.x)
                            self._photo_drag_offset_y = float(pyc) - float(event.y)
                            self._photo_drag_start = {
                                "pid": pid,
                                "lat": float(rec["lat"]),
                                "lon": float(rec["lon"]),
                                "scale": float(rec.get("scale", 1.0)),
                                "w": int(rec.get("w", 0)),
                                "h": int(rec.get("h", 0)),
                                "angle_deg": float(rec.get("angle_deg", 0.0)),
                                "ref_zoom": int(rec.get("ref_zoom", self._zoom)),
                                "cx": float(pxc),
                                "cy": float(pyc),
                                "mouse_x": float(event.x),
                                "mouse_y": float(event.y),
                            }
                        except Exception:
                            self._photo_drag_start = {"pid": pid}
                        return
            except Exception:
                pass
            return
        if mode == "edit":
            try:
                for idx, (lat, lon) in enumerate(self.points_latlon):
                    px, py = self._latlon_to_pixel(lat, lon)
                    if math.hypot(px - float(event.x), py - float(event.y)) < _hit_radius(self._zoom):
                        self._dragging_idx = idx
                        return
            except Exception:
                pass
            try:
                ht = self._hit_test_handles(int(event.x), int(event.y))
                if ht is not None:
                    pid_h, hname = ht
                    if self.get_photo_locked(pid_h) is True:
                        return
                    self._dragging_photo_id = int(pid_h)
                    self._dragging_photo = int(pid_h)
                    self._dragging_handle = str(hname)
                    rec = None
                    for r in self._photos:
                        if int(r["id"]) == int(pid_h):
                            rec = r
                            break
                    if rec is not None:
                        try:
                            bbox = self.get_photo_bbox(int(pid_h))
                            cx, cy = self._latlon_to_pixel(float(rec["lat"]), float(rec["lon"]))
                            self._photo_drag_start = {
                                "pid": int(pid_h),
                                "lat": float(rec["lat"]),
                                "lon": float(rec["lon"]),
                                "scale": float(rec.get("scale", 1.0)),
                                "w": int(rec.get("w", 0)),
                                "h": int(rec.get("h", 0)),
                                "angle_deg": float(rec.get("angle_deg", 0.0)),
                                "ref_zoom": int(rec.get("ref_zoom", self._zoom)),
                                "bbox": bbox,
                                "cx": float(cx),
                                "cy": float(cy),
                                "mouse_x": float(event.x),
                                "mouse_y": float(event.y),
                                "is_shift": bool(is_shift),
                            }
                        except Exception:
                            self._photo_drag_start = {"pid": int(pid_h), "scale": 1.0, "angle_deg": 0.0}
                    try:
                        self._update_mode_style()
                    except Exception:
                        pass
                    return
            except Exception:
                pass
            try:
                for rec in reversed(self._photos):
                    bbox = self.get_photo_bbox(int(rec["id"]))
                    if bbox is None:
                        continue
                    x0, y0, x1, y1 = bbox
                    if x0 <= float(event.x) <= x1 and y0 <= float(event.y) <= y1:
                        pid = int(rec["id"])
                        for r in self._photos:
                            try:
                                r["selected"] = int(r["id"]) == pid
                            except Exception:
                                r["selected"] = False
                        self._selected_photo_id = pid
                        self._dragging_photo_id = pid
                        self._dragging_photo = pid
                        self._dragging_handle = "move"
                        try:
                            pxc, pyc = self._latlon_to_pixel(float(rec["lat"]), float(rec["lon"]))
                            self._photo_drag_offset_x = float(pxc) - float(event.x)
                            self._photo_drag_offset_y = float(pyc) - float(event.y)
                            self._photo_drag_start = {
                                "pid": pid,
                                "lat": float(rec["lat"]),
                                "lon": float(rec["lon"]),
                                "scale": float(rec.get("scale", 1.0)),
                                "w": int(rec.get("w", 0)),
                                "h": int(rec.get("h", 0)),
                                "angle_deg": float(rec.get("angle_deg", 0.0)),
                                "ref_zoom": int(rec.get("ref_zoom", self._zoom)),
                                "cx": float(pxc),
                                "cy": float(pyc),
                                "mouse_x": float(event.x),
                                "mouse_y": float(event.y),
                            }
                        except Exception:
                            self._photo_drag_start = {"pid": pid}
                        try:
                            self._request_redraw()
                        except Exception:
                            pass
                        try:
                            self._update_mode_style()
                        except Exception:
                            pass
                        return
            except Exception:
                pass
            return
        if self._placing_photo_id is not None and not is_shift:
            return
        try:
            for idx, (lat, lon) in enumerate(self.points_latlon):
                px, py = self._latlon_to_pixel(lat, lon)
                if math.hypot(px - float(event.x), py - float(event.y)) < _hit_radius(self._zoom):
                    self._dragging_idx = idx
                    return
        except Exception:
            pass
        try:
            ht = self._hit_test_handles(int(event.x), int(event.y))
            if ht is not None:
                pid_h, hname = ht
                self._dragging_photo_id = int(pid_h)
                self._dragging_photo = int(pid_h)
                self._dragging_handle = str(hname)
                rec = None
                for r in self._photos:
                    if int(r["id"]) == int(pid_h):
                        rec = r
                        break
                if rec is not None:
                    try:
                        bbox = self.get_photo_bbox(int(pid_h))
                        cx, cy = self._latlon_to_pixel(float(rec["lat"]), float(rec["lon"]))
                        self._photo_drag_start = {
                            "pid": int(pid_h),
                            "lat": float(rec["lat"]),
                            "lon": float(rec["lon"]),
                            "scale": float(rec.get("scale", 1.0)),
                            "w": int(rec.get("w", 0)),
                            "h": int(rec.get("h", 0)),
                            "angle_deg": float(rec.get("angle_deg", 0.0)),
                            "ref_zoom": int(rec.get("ref_zoom", self._zoom)),
                            "bbox": bbox,
                            "cx": float(cx),
                            "cy": float(cy),
                            "mouse_x": float(event.x),
                            "mouse_y": float(event.y),
                            "is_shift": bool(is_shift),
                        }
                    except Exception:
                        self._photo_drag_start = {"pid": int(pid_h), "scale": 1.0, "angle_deg": 0.0}
                try:
                    self._update_mode_style()
                except Exception:
                    pass
                return
        except Exception:
            pass
        try:
            for rec in reversed(self._photos):
                bbox = self.get_photo_bbox(int(rec["id"]))
                if bbox is None:
                    continue
                x0, y0, x1, y1 = bbox
                if x0 <= float(event.x) <= x1 and y0 <= float(event.y) <= y1:
                    pid = int(rec["id"])
                    for r in self._photos:
                        try:
                            r["selected"] = int(r["id"]) == pid
                        except Exception:
                            r["selected"] = False
                    self._selected_photo_id = pid
                    self._dragging_photo_id = pid
                    self._dragging_photo = pid
                    self._dragging_handle = "move"
                    try:
                        pxc, pyc = self._latlon_to_pixel(float(rec["lat"]), float(rec["lon"]))
                        self._photo_drag_offset_x = float(pxc) - float(event.x)
                        self._photo_drag_offset_y = float(pyc) - float(event.y)
                        self._photo_drag_start = {
                            "pid": pid,
                            "lat": float(rec["lat"]),
                            "lon": float(rec["lon"]),
                            "scale": float(rec.get("scale", 1.0)),
                            "w": int(rec.get("w", 0)),
                            "h": int(rec.get("h", 0)),
                            "angle_deg": float(rec.get("angle_deg", 0.0)),
                            "ref_zoom": int(rec.get("ref_zoom", self._zoom)),
                            "cx": float(pxc),
                            "cy": float(pyc),
                            "mouse_x": float(event.x),
                            "mouse_y": float(event.y),
                        }
                    except Exception:
                        self._photo_drag_start = {"pid": pid}
                    try:
                        self._request_redraw()
                    except Exception:
                        pass
                    try:
                        self._update_mode_style()
                    except Exception:
                        pass
                    return
        except Exception:
            pass

    def _on_drag(self, event: tk.Event) -> None:  # type: ignore
        if self._press_x is None or self._press_y is None:
            return
        if self._dragging_idx is not None:
            try:
                try:
                    dist = math.hypot(float(event.x) - float(self._press_x), float(event.y) - float(self._press_y))
                except Exception:
                    dist = 0.0
                if dist < 5:
                    return
                lat, lon = self._pixel_to_latlon(int(event.x), int(event.y))
                self.points_latlon[self._dragging_idx] = (lat, lon)
                x, y, zone = wgs84_to_plane(lat, lon)
                self.points_xy[self._dragging_idx] = (float(x), float(y))
                self.points_zone[self._dragging_idx] = int(zone) if isinstance(zone, int) else int(zone)  # type: ignore
                self._moved = True
                self._draw_points_only()
            except Exception:
                pass
            return
        # photo dragging / handle handling
        if self._dragging_photo_id is not None:
            try:
                pid = int(self._dragging_photo_id)
                rec = None
                for r in self._photos:
                    if int(r["id"]) == pid:
                        rec = r
                        break
                if rec is None:
                    return
                if bool(rec.get("locked", False)):
                    return
                handle = self._dragging_handle
                if handle == "move":
                    # body-drag moves lat/lon with grab offset
                    try:
                        dist = math.hypot(float(event.x) - float(self._press_x), float(event.y) - float(self._press_y))
                    except Exception:
                        dist = 0.0
                    if dist < 1:
                        return
                    new_px = float(event.x) + float(self._photo_drag_offset_x)
                    new_py = float(event.y) + float(self._photo_drag_offset_y)
                    lat, lon = self._pixel_to_latlon(int(new_px), int(new_py))
                    rec["lat"] = float(lat)
                    rec["lon"] = float(lon)
                    self._moved = True
                    try:
                        self._request_redraw()
                    except Exception:
                        pass
                    return
                elif handle == "rotate":
                    # rotation angle from center drag
                    try:
                        cx, cy = self._latlon_to_pixel(float(rec["lat"]), float(rec["lon"]))
                        dx = float(event.x) - float(cx)
                        dy = float(event.y) - float(cy)
                        ang = math.degrees(math.atan2(dy, dx)) + 90.0
                        # normalize 0-360
                        ang = float(ang % 360.0)
                        rec["angle_deg"] = float(ang)
                        # invalidate cache
                        try:
                            keys = [k for k in list(self._photo_image_cache.keys()) if int(k[0]) == pid]
                            for k in keys:
                                self._photo_image_cache.pop(k, None)
                        except Exception:
                            pass
                        self._moved = True
                        self._request_redraw()
                    except Exception:
                        pass
                    return
                elif handle in ("nw", "n", "ne", "e", "se", "s", "sw", "w"):
                    # resize handling
                    try:
                        is_shift = False
                        try:
                            if int(getattr(event, "state", 0)) & 0x0001:
                                is_shift = True
                        except Exception:
                            is_shift = False
                        # also consider start shift
                        try:
                            if self._photo_drag_start and bool(self._photo_drag_start.get("is_shift")):
                                is_shift = True
                        except Exception:
                            pass
                        start = self._photo_drag_start or {}
                        orig_scale = float(start.get("scale", rec.get("scale", 1.0)))
                        orig_w = int(start.get("w", rec.get("w", 0)))
                        orig_h = int(start.get("h", rec.get("h", 0)))
                        ref_zoom = int(rec.get("ref_zoom", self._zoom))
                        factor = 2 ** (int(self._zoom) - ref_zoom)
                        # base size at ref
                        base_w = float(orig_w) / float(orig_scale) if orig_scale != 0 else float(orig_w)
                        base_h = float(orig_h) / float(orig_scale) if orig_scale != 0 else float(orig_h)
                        bbox = start.get("bbox")
                        if bbox is None:
                            bbox = self.get_photo_bbox(pid)
                        if bbox is None:
                            return
                        x0, y0, x1, y1 = bbox
                        # For each handle, anchor is opposite side
                        anchor_x: float | None = None
                        anchor_y: float | None = None
                        if handle == "se":
                            anchor_x, anchor_y = x0, y0
                        elif handle == "nw":
                            anchor_x, anchor_y = x1, y1
                        elif handle == "ne":
                            anchor_x, anchor_y = x0, y1
                        elif handle == "sw":
                            anchor_x, anchor_y = x1, y0
                        elif handle == "e":
                            anchor_x, anchor_y = x0, (y0 + y1) * 0.5
                        elif handle == "w":
                            anchor_x, anchor_y = x1, (y0 + y1) * 0.5
                        elif handle == "n":
                            anchor_x, anchor_y = (x0 + x1) * 0.5, y1
                        elif handle == "s":
                            anchor_x, anchor_y = (x0 + x1) * 0.5, y0
                        mx, my = float(event.x), float(event.y)
                        # compute new drawn dimensions
                        new_dw: float | None = None
                        new_dh: float | None = None
                        if handle in ("e", "w"):
                            new_dw = abs(mx - float(anchor_x))
                            new_dh = abs(y1 - y0)
                        elif handle in ("n", "s"):
                            new_dw = abs(x1 - x0)
                            new_dh = abs(my - float(anchor_y))
                        else:
                            new_dw = abs(mx - float(anchor_x))
                            new_dh = abs(my - float(anchor_y))
                        if new_dw is None or new_dh is None:
                            return
                        # clamp minimal
                        if new_dw < 10:
                            new_dw = 10
                        if new_dh < 10:
                            new_dh = 10
                        # derive scale
                        scale_w = float(new_dw) / (float(base_w) * float(factor)) if base_w > 0 else orig_scale
                        scale_h = float(new_dh) / (float(base_h) * float(factor)) if base_h > 0 else orig_scale
                        if handle in ("e", "w"):
                            new_scale = scale_w
                        elif handle in ("n", "s"):
                            new_scale = scale_h
                        else:
                            if is_shift:
                                # aspect-lock: use max to preserve aspect, or average?
                                new_scale = max(scale_w, scale_h) if max(scale_w, scale_h) > 0 else (scale_w + scale_h) * 0.5
                            else:
                                # corner without shift: allow non-uniform but we have single scale, use average
                                new_scale = (scale_w + scale_h) * 0.5
                        new_scale = min(8.0, max(0.01, float(new_scale)))
                        # update rec
                        new_w = int(round(float(base_w) * new_scale))
                        new_h = int(round(float(base_h) * new_scale))
                        if new_w < 1:
                            new_w = 1
                        if new_h < 1:
                            new_h = 1
                        rec["scale"] = float(new_scale)
                        rec["w"] = int(new_w)
                        rec["h"] = int(new_h)
                        # width_m = w * mpp at ref_zoom
                        try:
                            rec["width_m"] = float(new_w) * _mpp(float(rec["lat"]), ref_zoom)
                        except Exception:
                            pass
                        # invalidate cache
                        try:
                            keys = [k for k in list(self._photo_image_cache.keys()) if int(k[0]) == pid]
                            for k in keys:
                                self._photo_image_cache.pop(k, None)
                        except Exception:
                            pass
                        self._moved = True
                        self._request_redraw()
                    except Exception:
                        pass
                    return
            except Exception:
                pass
            return
        # pan
        dx = int(event.x) - int(self._press_x)
        dy = int(event.y) - int(self._press_y)
        if math.hypot(float(dx), float(dy)) >= 5:
            self._moved = True
        if math.hypot(float(dx), float(dy)) < 5:
            return
        new_xf = float(self._pan_xf) - dx / TILE_SIZE
        new_yf = float(self._pan_yf) - dy / TILE_SIZE
        # clamp y to valid range
        n = 1 << self._zoom
        if new_yf < 0:
            new_yf = 0
        if new_yf > n:
            new_yf = float(n)
        lat, lon = _tile_float_to_latlon(new_xf, new_yf, self._zoom)
        self.center_lat, self.center_lon = lat, lon
        self._center_xf, self._center_yf = new_xf, new_yf
        self._request_redraw()

    def _on_release(self, event: tk.Event) -> None:  # type: ignore
        dist = 0.0
        if self._press_x is not None and self._press_y is not None:
            try:
                dist = math.hypot(float(event.x) - float(self._press_x), float(event.y) - float(self._press_y))
            except Exception:
                dist = 0.0
        try:
            mode = self.get_interact_mode()
        except Exception:
            mode = "trace"
        if mode not in ("trace", "place", "edit"):
            mode = "trace"
        if self._dragging_idx is not None:
            if mode == "edit":
                self._dragging_idx = None
                self._press_x = None
                self._press_y = None
                self._dragging_photo_id = None
                self._dragging_photo = None
                self._dragging_handle = None
                try:
                    self._update_mode_style()
                except Exception:
                    pass
                return
            if self._moved and dist >= 5:
                self._dragging_idx = None
                self._press_x = None
                self._press_y = None
                self._dragging_photo_id = None
                self._dragging_photo = None
                self._dragging_handle = None
                try:
                    self._update_mode_style()
                except Exception:
                    pass
                return
            self._dragging_idx = None
        if self._dragging_photo_id is not None:
            if mode == "trace":
                if self._moved and dist >= 2:
                    self._dragging_photo_id = None
                    self._dragging_photo = None
                    self._dragging_handle = None
                    self._photo_drag_start = None
                    self._press_x = None
                    self._press_y = None
                    try:
                        self._request_redraw()
                    except Exception:
                        pass
                    try:
                        self._update_mode_style()
                    except Exception:
                        pass
                    return
                else:
                    self._dragging_photo_id = None
                    self._dragging_photo = None
                    self._dragging_handle = None
                    self._photo_drag_start = None
            else:
                try:
                    if self._moved and dist >= 2:
                        pass
                    else:
                        pass
                except Exception:
                    pass
                self._dragging_photo_id = None
                self._dragging_photo = None
                self._dragging_handle = None
                self._photo_drag_start = None
                self._press_x = None
                self._press_y = None
                try:
                    self._request_redraw()
                except Exception:
                    pass
                try:
                    self._update_mode_style()
                except Exception:
                    pass
                if mode == "trace":
                    pass
                else:
                    return
                # for trace click, fall through to waypoint add
                if mode == "trace":
                    try:
                        if self._press_x is not None and (not self._moved or dist < 5):
                            pass
                        else:
                            return
                    except Exception:
                        pass
                else:
                    return
        if self._dragging_handle is not None:
            if mode == "trace":
                if self._moved and dist >= 2:
                    self._dragging_handle = None
                    self._dragging_photo_id = None
                    self._dragging_photo = None
                    self._photo_drag_start = None
                    self._press_x = None
                    self._press_y = None
                    try:
                        self._update_mode_style()
                    except Exception:
                        pass
                    return
                else:
                    self._dragging_handle = None
                    self._dragging_photo_id = None
                    self._dragging_photo = None
                    self._photo_drag_start = None
            else:
                self._dragging_handle = None
                self._dragging_photo_id = None
                self._dragging_photo = None
                self._photo_drag_start = None
                self._press_x = None
                self._press_y = None
                try:
                    self._update_mode_style()
                except Exception:
                    pass
                return
            self._dragging_handle = None
            self._dragging_photo_id = None
            self._dragging_photo = None
            self._photo_drag_start = None
            self._press_x = None
            self._press_y = None
            try:
                self._update_mode_style()
            except Exception:
                pass
            return
        if self._press_x is not None and (not self._moved or dist < 5):
            try:
                lat, lon = self._pixel_to_latlon(int(event.x), int(event.y))
                if mode == "trace":
                    x, y, zone = wgs84_to_plane(lat, lon)
                    self.points_latlon.append((lat, lon))
                    self.points_xy.append((float(x), float(y)))
                    self.points_zone.append(int(zone) if isinstance(zone, int) else int(zone))  # type: ignore
                    self._draw_points_only()
                    if len(self.points_latlon) % AUTOSAVE_THRESHOLD == 0:
                        try:
                            self._autosave_points()
                        except Exception:
                            pass
                    try:
                        self._last_click_on_photo = False
                        self._update_mode_style()
                    except Exception:
                        pass
                    self._press_x = None
                    self._press_y = None
                    self._dragging_photo_id = None
                    self._dragging_photo = None
                    self._dragging_handle = None
                    self._photo_drag_start = None
                    try:
                        self._update_mode_style()
                    except Exception:
                        pass
                    return
                if mode == "edit":
                    hit = None
                    try:
                        hit = self.hit_test_photo(int(event.x), int(event.y))
                    except Exception:
                        hit = None
                    if hit is not None:
                        try:
                            if bool(self.get_photo(hit).get("locked", False)) if self.get_photo(hit) else False:
                                hit = None
                            else:
                                for r in self._photos:
                                    try:
                                        r["selected"] = int(r["id"]) == int(hit)
                                    except Exception:
                                        r["selected"] = False
                                self._selected_photo_id = int(hit)
                                self._request_redraw()
                        except Exception:
                            pass
                    else:
                        try:
                            changed = False
                            for r in self._photos:
                                if bool(r.get("selected")):
                                    r["selected"] = False
                                    changed = True
                            if changed:
                                self._selected_photo_id = None
                                self._request_redraw()
                        except Exception:
                            pass
                    self._press_x = None
                    self._press_y = None
                    self._dragging_photo_id = None
                    self._dragging_photo = None
                    self._dragging_handle = None
                    self._photo_drag_start = None
                    try:
                        self._update_mode_style()
                    except Exception:
                        pass
                    return
                if self._placing_photo_id is not None:
                    _is_shift_bypass = False
                    try:
                        if int(getattr(event, "state", 0)) & 0x0001:
                            _is_shift_bypass = True
                        if int(getattr(event, "num", 1)) in (2, 3):
                            _is_shift_bypass = True
                    except Exception:
                        pass
                    _ = "Shift"
                    if not _is_shift_bypass:
                        _hit = None
                        try:
                            _hit = self.hit_test_photo(int(event.x), int(event.y))
                        except Exception:
                            _hit = None
                        if _hit is not None:
                            self._last_click_on_photo = True
                            try:
                                self._update_mode_style()
                            except Exception:
                                pass
                        else:
                            self._last_click_on_photo = False
                            pid = self._placing_photo_id
                            self._placing_photo_id = None
                            for rec in self._photos:
                                if int(rec["id"]) == int(pid):
                                    rec["lat"] = float(lat)
                                    rec["lon"] = float(lon)
                                    try:
                                        refz = int(rec.get("ref_zoom", self._zoom))
                                        rec["width_m"] = float(rec.get("w", 0)) * _mpp(float(lat), refz)
                                    except Exception:
                                        pass
                                    break
                            self._request_redraw()
                            try:
                                self._update_mode_style()
                            except Exception:
                                pass
                            self._press_x = None
                            self._press_y = None
                            return
                x, y, zone = wgs84_to_plane(lat, lon)
                self.points_latlon.append((lat, lon))
                self.points_xy.append((float(x), float(y)))
                self.points_zone.append(int(zone) if isinstance(zone, int) else int(zone))  # type: ignore
                self._draw_points_only()
                if len(self.points_latlon) % AUTOSAVE_THRESHOLD == 0:
                    try:
                        self._autosave_points()
                    except Exception:
                        pass
                try:
                    changed = False
                    for r in self._photos:
                        if bool(r.get("selected")):
                            r["selected"] = False
                            changed = True
                    if changed:
                        self._selected_photo_id = None
                        self._request_redraw()
                except Exception:
                    pass
            except Exception as e:
                try:
                    messagebox.showerror("Error", str(e), parent=self)
                except Exception:
                    pass
        self._press_x = None
        self._press_y = None
        self._dragging_photo_id = None
        self._dragging_photo = None
        self._dragging_handle = None
        self._photo_drag_start = None
        try:
            self._update_mode_style()
        except Exception:
            pass

    def _on_wheel(self, event: tk.Event) -> None:  # type: ignore
        delta = 0
        try:
            delta = int(getattr(event, "delta", 0))
        except Exception:
            delta = 0
        if delta > 0:
            self.set_zoom(self._zoom + 1, anchor_x=int(event.x), anchor_y=int(event.y))
        elif delta < 0:
            self.set_zoom(self._zoom - 1, anchor_x=int(event.x), anchor_y=int(event.y))

    def _on_button4(self, event: tk.Event) -> None:  # type: ignore
        self.set_zoom(self._zoom + 1, anchor_x=int(event.x), anchor_y=int(event.y))

    def _on_button5(self, event: tk.Event) -> None:  # type: ignore
        self.set_zoom(self._zoom - 1, anchor_x=int(event.x), anchor_y=int(event.y))

    def _on_configure(self, event: object | None = None) -> None:
        try:
            w = int(self.winfo_width())
            h = int(self.winfo_height())
            if w > 10:
                self._width = w
            if h > 10:
                self._height = h
        except Exception:
            pass
        self._request_redraw()

    # -- tile logic ------------------------------------------------------
    def _get_visible_tiles_for_center(self) -> list[tuple[int, int, int, float, float]]:
        w = int(self.winfo_width()) or self._width
        h = int(self.winfo_height()) or self._height
        if w < 10:
            w = self._width
        if h < 10:
            h = self._height
        cx_f, cy_f = _latlon_to_tile_float(self.center_lat, self.center_lon, self._zoom)
        self._center_xf, self._center_yf = cx_f, cy_f
        n = 1 << self._zoom
        x_min = math.floor(cx_f - w * 0.5 / TILE_SIZE)
        x_max = math.ceil(cx_f + w * 0.5 / TILE_SIZE)
        y_min = math.floor(cy_f - h * 0.5 / TILE_SIZE)
        y_max = math.ceil(cy_f + h * 0.5 / TILE_SIZE)
        tiles: list[tuple[int, int, int, float, float]] = []
        seen: set[tuple[int, int, int]] = set()
        for x in range(int(x_min), int(x_max) + 1):
            for y in range(int(y_min), int(y_max) + 1):
                if x < 0 or x >= n or y < 0 or y >= n:
                    continue
                px = (x - cx_f) * TILE_SIZE + w * 0.5
                py = (y - cy_f) * TILE_SIZE + h * 0.5
                tiles.append((self._zoom, x, y, float(px), float(py)))
                seen.add((self._zoom, x, y))
        return tiles

    def _request_redraw(self) -> None:
        if self._redraw_after_id is not None:
            try:
                self.after_cancel(self._redraw_after_id)
            except Exception:
                pass
            self._redraw_after_id = None
        try:
            self._redraw_after_id = self.after_idle(self._run_redraw)
        except Exception:
            try:
                self._redraw()
            except Exception:
                pass

    def _run_redraw(self) -> None:
        self._redraw_after_id = None
        try:
            self._redraw()
        except Exception:
            pass

    def _cache_store(self, key: tuple[int, int, int], img: tk.PhotoImage) -> None:
        if key in self._tile_cache:
            try:
                self._tile_cache_order.remove(key)
            except ValueError:
                pass
        self._tile_cache[key] = img
        self._tile_cache_order.append(key)
        while len(self._tile_cache_order) > TILE_CACHE_MAX:
            old = self._tile_cache_order.pop(0)
            self._tile_cache.pop(old, None)
        self._images = list(self._tile_cache.values())
        self._photo_refs = self._images

    def _redraw(self) -> None:
        try:
            self.delete("all")
        except Exception:
            return
        tiles = self._get_visible_tiles_for_center()
        self._visible_tiles = [(z, x, y) for z, x, y, _, _ in tiles]
        n_vis = len(tiles)
        n_hit = 0
        for z, x, y, px, py in tiles:
            key = (int(z), int(x), int(y))
            hit = self._tile_cache.get(key)
            if hit is not None:
                n_hit += 1
                try:
                    self.create_image(px, py, image=hit, anchor="nw", tags=("tile",))
                    continue
                except Exception:
                    pass
            try:
                self.create_rectangle(px, py, px + TILE_SIZE, py + TILE_SIZE, fill="#dddddd", outline="#cccccc", tags=("tile", "placeholder"))
                self.create_text(px + TILE_SIZE * 0.5, py + TILE_SIZE * 0.5, text=f"{z}/{x}/{y}", fill="#999", font=("TkDefaultFont", 6), tags=("tile",))
            except Exception:
                pass
            cache_key = (int(z), int(x), int(y))
            # duplicate elimination with gen-aware inflight (preserve MAX_PENDING_FETCH 16 limit)
            already = False
            try:
                gen = int(self._redraw_gen)
                for k in self._inflight:
                    if len(k) == 4 and k[0] == z and k[1] == x and k[2] == y and k[3] == gen:
                        already = True
                        break
                    if len(k) == 3 and k[0] == z and k[1] == x and k[2] == y:
                        already = True
                        break
            except Exception:
                already = cache_key in self._inflight  # type: ignore
            if not already and len(self._inflight) < MAX_PENDING_FETCH:
                self._fetch_tile_async(z, x, y)
        self._draw_photos()
        self._draw_reference_overlay()
        self._draw_points()
        self._draw_attribution()
        self._draw_status(n_hit, n_vis)

    def _get_cached_photo_image(self, rec: dict, dw: int, dh: int, angle_deg: float) -> tk.PhotoImage | None:
        """Return PhotoImage for drawn size dw x dh with angle. Per-(zoom,scale,angle) cache with PIL smooth resize/rotate, tk fallback."""
        pid = int(rec.get("id", 0))
        scale = float(rec.get("scale", 1.0))
        zoom = int(self._zoom)
        # cache key per (zoom,scale,angle) - use pid+zoom+scale+angle
        key = (pid, zoom, round(scale, 4), round(float(angle_deg), 2))
        try:
            cached = self._photo_image_cache.get(key)
            if cached is not None:
                return cached
        except Exception:
            pass
        # try PIL smooth resize/rotate
        try:
            import importlib as _il
            Image = _il.import_module("PIL.Image")  # type: ignore
            ImageTk = _il.import_module("PIL.ImageTk")  # type: ignore
            # open original
            path = str(rec.get("path", ""))
            if path and pathlib.Path(path).exists():
                pil = Image.open(path).convert("RGBA")
                # opacity alpha (true transparency, map shows through)
                try:
                    op = float(rec.get("opacity", 0.5))
                    op = min(1.0, max(0.0, op))
                    if op < 0.999:
                        try:
                            if pil.mode != "RGBA":
                                pil = pil.convert("RGBA")
                            alpha = int(255 * op)
                            if alpha < 0:
                                alpha = 0
                            if alpha > 255:
                                alpha = 255
                            pil.putalpha(alpha)
                        except Exception:
                            pass
                except Exception:
                    pass
                # smooth resize to dw,dh
                try:
                    # use LANCZOS for smooth
                    pil = pil.resize((max(1, int(dw)), max(1, int(dh))), Image.LANCZOS)  # type: ignore
                except Exception:
                    try:
                        pil = pil.resize((max(1, int(dw)), max(1, int(dh))))  # type: ignore
                    except Exception:
                        pass
                # rotate
                if abs(float(angle_deg)) > 0.01:
                    try:
                        pil = pil.rotate(-float(angle_deg), expand=True, resample=Image.BICUBIC)  # type: ignore
                    except Exception:
                        try:
                            pil = pil.rotate(-float(angle_deg), expand=True)  # type: ignore
                        except Exception:
                            pass
                img = ImageTk.PhotoImage(pil)
                try:
                    self._photo_image_cache[key] = img
                    # keep GC ref
                    self._images.append(img)
                    self._photo_refs = self._images
                except Exception:
                    pass
                return img
        except Exception:
            pass
        # tk fallback: subsample/zoom
        try:
            base_img = rec.get("img")
            if base_img is None:
                return None
            cw = int(base_img.width()) if hasattr(base_img, "width") else dw
            ch = int(base_img.height()) if hasattr(base_img, "height") else dh
            if cw <= 0 or ch <= 0:
                return base_img
            # factor from base at ref to drawn at zoom
            # base_img is w x h at ref, drawn is dw x dh
            # use zoom/subsample integer approx
            out = base_img
            # handle resize via subsample/zoom fallback
            try:
                # if drawn larger, use zoom
                if dw > cw or dh > ch:
                    fx = max(1, int(round(float(dw) / float(cw))) if cw else 1)
                    fy = max(1, int(round(float(dh) / float(ch))) if ch else 1)
                    # use min to keep aspect; try zoom
                    f = min(fx, fy)
                    if f > 1:
                        try:
                            out = out.zoom(f, f)
                        except Exception:
                            pass
                    # if still not exact, subsample alternative not needed
                elif dw < cw or dh < ch:
                    fx = max(1, int(round(float(cw) / float(dw))) if dw else 1)
                    fy = max(1, int(round(float(ch) / float(dh))) if dh else 1)
                    f = min(fx, fy)
                    if f > 1:
                        try:
                            out = out.subsample(f, f)
                        except Exception:
                            pass
            except Exception:
                pass
            # rotation not supported in tk fallback; handle hidden if no PIL (we already check PIL)
            # cache fallback similarly per key but reuse same image
            try:
                self._photo_image_cache[key] = out
            except Exception:
                pass
            return out
        except Exception:
            pass
        try:
            return rec.get("img")
        except Exception:
            return None

    def _draw_photos(self) -> None:
        for rec in self._photos:
            try:
                px, py = self._latlon_to_pixel(float(rec["lat"]), float(rec["lon"]))
                w = int(rec.get("w", 0))
                h = int(rec.get("h", 0))
                if w <= 0 or h <= 0:
                    continue
                try:
                    ref_zoom = int(rec.get("ref_zoom", self._zoom))
                except Exception:
                    ref_zoom = int(self._zoom)
                try:
                    scale = float(rec.get("scale", 1.0))
                except Exception:
                    scale = 1.0
                try:
                    angle_deg = float(rec.get("angle_deg", 0.0) or 0.0)
                except Exception:
                    angle_deg = 0.0
                factor = 2 ** (int(self._zoom) - int(ref_zoom))
                # size=base*scale*2**(zoom-ref_zoom)  -> w already base*scale, so dw = w*factor
                dw = int(round(float(w) * float(factor)))
                dh = int(round(float(h) * float(factor)))
                if dw < 1:
                    dw = 1
                if dh < 1:
                    dh = 1
                img = self._get_cached_photo_image(rec, dw, dh, angle_deg)
                if img is None:
                    img = rec.get("img")
                if img is None:
                    continue
                # keep reference
                try:
                    # ensure not GC'd; _images already holds tile cache, but also hold photo
                    if img not in self._images:
                        self._images.append(img)
                        self._photo_refs = self._images
                except Exception:
                    pass
                try:
                    self.create_image(px, py, image=img, anchor="center", tags=("photo", f"photo_{rec['id']}"))
                except Exception:
                    continue
                # selection rect + 8 handles + rotation handle
                try:
                    if bool(rec.get("selected")):
                        # bbox for selection: use dw,dh (with rotation enlarge if PIL)
                        bbox_dw, bbox_dh = float(dw), float(dh)
                        if abs(angle_deg) > 0.01 and _has_pil():
                            rad = math.radians(angle_deg)
                            cos_a = abs(math.cos(rad))
                            sin_a = abs(math.sin(rad))
                            bbox_dw = dw * cos_a + dh * sin_a
                            bbox_dh = dw * sin_a + dh * cos_a
                        x0 = float(px) - bbox_dw * 0.5
                        y0 = float(py) - bbox_dh * 0.5
                        x1 = float(px) + bbox_dw * 0.5
                        y1 = float(py) + bbox_dh * 0.5
                        cx = float(px)
                        cy = float(py)
                        # selection rect
                        try:
                            self.create_rectangle(x0, y0, x1, y1, outline="#1f4b99", width=1, dash=(3, 3), tags=("photo_select", f"photo_sel_{rec['id']}"))
                        except Exception:
                            pass
                        # 8 handles
                        hs = float(self._photo_handle_size)
                        handles = [
                            (x0, y0), (cx, y0), (x1, y0),
                            (x1, cy), (x1, y1), (cx, y1),
                            (x0, y1), (x0, cy),
                        ]
                        for hx, hy in handles:
                            try:
                                self.create_rectangle(hx - hs, hy - hs, hx + hs, hy + hs, fill="white", outline="#1f4b99", width=1, tags=("photo_handle", f"photo_handle_{rec['id']}"))
                            except Exception:
                                pass
                        # top rotation handle (angle from center drag) - hidden if no PIL (handle hidden if no PIL)
                        if _has_pil():
                            try:
                                rx = cx
                                ry = y0 - float(self._photo_rotate_offset)
                                # line from top center to handle
                                self.create_line(cx, y0, rx, ry, fill="#1f4b99", width=1, tags=("photo_rotate_line", f"photo_rot_{rec['id']}"))
                                self.create_oval(rx - hs, ry - hs, rx + hs, ry + hs, fill="#ffcc00", outline="#1f4b99", width=1, tags=("photo_rotate_handle", f"photo_rot_{rec['id']}"))
                            except Exception:
                                pass
                except Exception:
                    pass
            except Exception:
                pass

    def _plane_xy_to_latlon_offset(
        self,
        points_xy: object,
        x0: float,
        y0: float,
        mean_x: float,
        mean_y: float,
        zone: int,
    ) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        try:
            seq: object = points_xy  # type: ignore
            pts: list[object] = []
            try:
                import numpy as _np  # type: ignore

                if isinstance(seq, _np.ndarray):
                    if seq.ndim == 2 and seq.shape[1] >= 2:
                        for i in range(int(seq.shape[0])):
                            try:
                                pts.append((float(seq[i, 0]), float(seq[i, 1])))
                            except Exception:
                                continue
                    elif seq.ndim == 1 and seq.size % 2 == 0:
                        arr = seq.reshape(-1, 2)
                        for i in range(int(arr.shape[0])):
                            try:
                                pts.append((float(arr[i, 0]), float(arr[i, 1])))
                            except Exception:
                                continue
                    else:
                        pts = list(seq)
                else:
                    pts = list(seq)  # type: ignore[arg-type]
            except Exception:
                try:
                    pts = list(seq)  # type: ignore[arg-type]
                except Exception:
                    return out
            for p in pts:
                try:
                    if isinstance(p, (list, tuple)) and len(p) >= 2:
                        x = float(p[0]); y = float(p[1])
                    else:
                        x = float(p[0]); y = float(p[1])  # type: ignore
                    lat, lon = plane_to_wgs84(float(x0) + (float(x) - float(mean_x)), float(y0) + (float(y) - float(mean_y)), int(zone))
                    try:
                        import numpy as _np2  # type: ignore
                        if isinstance(lat, _np2.ndarray):
                            lat = float(lat.flat[0])
                        if isinstance(lon, _np2.ndarray):
                            lon = float(lon.flat[0])
                    except Exception:
                        pass
                    out.append((float(lat), float(lon)))
                except Exception:
                    continue
        except Exception:
            pass
        return out

    def set_reference_overlay(self, candidates: list[object] | None) -> int:
        try:
            self._reference_overlays = []
        except Exception:
            self._reference_overlays = []  # type: ignore
        if candidates is None:
            try:
                self._request_redraw()
            except Exception:
                try:
                    self._redraw()
                except Exception:
                    pass
            return 0
        try:
            cand_list = list(candidates)  # type: ignore[arg-type]
        except Exception:
            cand_list = []

        x0: float | None = None
        y0: float | None = None
        zone: int | None = None
        n_added = 0
        for cand in cand_list:
            try:
                pts_lonlat: object | None = None
                pts_xy: object | None = None
                if isinstance(cand, dict):
                    if "points_lonlat" in cand and cand["points_lonlat"] is not None:
                        pts_lonlat = cand["points_lonlat"]
                    if "points_xy" in cand and cand["points_xy"] is not None:
                        pts_xy = cand["points_xy"]
                else:
                    if hasattr(cand, "points_lonlat"):
                        try:
                            v = getattr(cand, "points_lonlat")
                            if v is not None:
                                pts_lonlat = v
                        except Exception:
                            pts_lonlat = None
                    if hasattr(cand, "points_xy"):
                        try:
                            v = getattr(cand, "points_xy")
                            if v is not None:
                                pts_xy = v
                        except Exception:
                            pts_xy = None

                poly: list[tuple[float, float]] | None = None
                if pts_lonlat is not None:
                    try:

                        out: list[tuple[float, float]] = []

                        try:
                            import numpy as _np  # type: ignore

                            if isinstance(pts_lonlat, _np.ndarray):
                                arr = _np.asarray(pts_lonlat, dtype=float)
                                if arr.ndim == 2 and arr.shape[1] >= 2:
                                    for i in range(int(arr.shape[0])):
                                        try:
                                            lon = float(arr[i, 0]); lat = float(arr[i, 1])
                                            out.append((float(lat), float(lon)))
                                        except Exception:
                                            continue
                                elif arr.ndim == 1 and arr.size % 2 == 0:
                                    arr2 = arr.reshape(-1, 2)
                                    for i in range(int(arr2.shape[0])):
                                        try:
                                            lon = float(arr2[i, 0]); lat = float(arr2[i, 1])
                                            out.append((float(lat), float(lon)))
                                        except Exception:
                                            continue
                                else:
                                    raise ValueError("fallback")
                            else:
                                raise ValueError("not ndarray")
                        except Exception:
                            seq = list(pts_lonlat)  # type: ignore[arg-type]
                            out = []
                            for p in seq:
                                try:

                                    if isinstance(p, (list, tuple)) and len(p) >= 2:
                                        lon = float(p[0]); lat = float(p[1])
                                        out.append((float(lat), float(lon)))
                                    else:
                                        continue
                                except Exception:
                                    continue
                        if len(out) >= 2:
                            poly = out
                        elif len(out) == 1:
                            poly = out
                        else:
                            poly = None
                    except Exception:
                        poly = None

                if poly is None and pts_xy is not None:
                    try:

                        if x0 is None or y0 is None or zone is None:
                            try:
                                _x0, _y0, _z = wgs84_to_plane(float(self.center_lat), float(self.center_lon))

                                try:
                                    import numpy as _np3  # type: ignore
                                    if isinstance(_x0, _np3.ndarray):
                                        _x0 = float(_x0.flat[0])
                                    if isinstance(_y0, _np3.ndarray):
                                        _y0 = float(_y0.flat[0])
                                    if isinstance(_z, _np3.ndarray):
                                        _z = int(_z.flat[0])
                                except Exception:
                                    pass
                                x0 = float(_x0); y0 = float(_y0); zone = int(_z)
                            except Exception:
                                continue

                        try:
                            import numpy as _np4  # type: ignore

                            if isinstance(pts_xy, _np4.ndarray):
                                arr = _np4.asarray(pts_xy, dtype=float)
                                if arr.ndim == 2 and arr.shape[1] >= 2:
                                    mean_x = float(_np4.mean(arr[:, 0]))
                                    mean_y = float(_np4.mean(arr[:, 1]))
                                elif arr.ndim == 1 and arr.size % 2 == 0:
                                    arr2 = arr.reshape(-1, 2)
                                    mean_x = float(_np4.mean(arr2[:, 0]))
                                    mean_y = float(_np4.mean(arr2[:, 1]))
                                else:
                                    pts_list = list(arr.flat)
                                    mean_x = 0.0; mean_y = 0.0
                            else:
                                seq_xy = list(pts_xy)  # type: ignore[arg-type]
                                xs: list[float] = []; ys: list[float] = []
                                for p in seq_xy:
                                    try:
                                        if isinstance(p, (list, tuple)) and len(p) >= 2:
                                            xs.append(float(p[0])); ys.append(float(p[1]))
                                    except Exception:
                                        continue
                                if xs and ys:
                                    mean_x = float(sum(xs) / len(xs))
                                    mean_y = float(sum(ys) / len(ys))
                                else:
                                    mean_x = 0.0; mean_y = 0.0
                        except Exception:
                            mean_x = 0.0; mean_y = 0.0

                        try:
                            poly = self._plane_xy_to_latlon_offset(pts_xy, float(x0), float(y0), float(mean_x), float(mean_y), int(zone))
                        except Exception:
                            poly = None
                        if poly is not None and len(poly) < 2:
                            pass
                        if poly is not None and len(poly) == 0:
                            poly = None
                    except Exception:
                        poly = None
                if poly is not None and len(poly) >= 1:
                    try:

                        filt: list[tuple[float, float]] = []
                        for lat, lon in poly:
                            try:
                                filt.append((float(lat), float(lon)))
                            except Exception:
                                continue
                        if len(filt) >= 1:
                            self._reference_overlays.append(filt)
                            n_added += 1
                    except Exception:
                        pass
            except Exception:
                continue
        try:
            self._request_redraw()
        except Exception:
            try:
                self._redraw()
            except Exception:
                pass
        return int(n_added)

    def clear_reference_overlay(self) -> None:
        try:
            self._reference_overlays = []
        except Exception:
            self._reference_overlays = []  # type: ignore
        try:
            self._request_redraw()
        except Exception:
            try:
                self._redraw()
            except Exception:
                pass

    def _draw_reference_overlay(self) -> None:
        try:
            overlays = getattr(self, "_reference_overlays", None)
            if not overlays:
                return
            for poly in list(overlays):
                try:
                    if poly is None or len(poly) < 2:
                        continue
                    coords: list[float] = []
                    for lat, lon in poly:
                        try:
                            px, py = self._latlon_to_pixel(float(lat), float(lon))
                            coords.extend([float(px), float(py)])
                        except Exception:
                            continue
                    if len(coords) < 4:
                        continue
                    try:
                        self.create_line(*coords, fill="#ff6b6b", width=2, dash=(4, 4), tags=("reference",))
                    except Exception:
                        try:
                            self.create_line(*coords, fill="#ff6b6b", width=2, tags=("reference",))
                        except Exception:
                            pass
                except Exception:
                    continue
        except Exception:
            pass

    def fit_reference_overlay(self) -> None:
        try:
            overlays = getattr(self, "_reference_overlays", None)
            if not overlays:
                return
            min_lat = 90.0; max_lat = -90.0
            min_lon = 180.0; max_lon = -180.0
            has = False
            for poly in list(overlays):
                try:
                    for lat, lon in poly:
                        try:
                            la = float(lat); lo = float(lon)
                            if la < min_lat: min_lat = la
                            if la > max_lat: max_lat = la
                            if lo < min_lon: min_lon = lo
                            if lo > max_lon: max_lon = lo
                            has = True
                        except Exception:
                            continue
                except Exception:
                    continue
            if not has:
                return
            try:
                center_lat = (float(min_lat) + float(max_lat)) * 0.5
                center_lon = (float(min_lon) + float(max_lon)) * 0.5
            except Exception:
                return
            lat_span = float(max_lat) - float(min_lat)
            lon_span = float(max_lon) - float(min_lon)
            span = max(float(lat_span), float(lon_span))
            try:
                if span < 0.01:
                    z = 16
                elif span < 0.03:
                    z = 15
                elif span < 0.08:
                    z = 14
                elif span < 0.15:
                    z = 13
                else:
                    z = 12
                z = max(12, min(17, int(z)))
            except Exception:
                z = 14
            try:
                self.set_center(float(center_lat), float(center_lon))
            except Exception:
                try:
                    self.center_lat = float(center_lat)
                    self.center_lon = float(center_lon)
                    self._center_xf, self._center_yf = _latlon_to_tile_float(self.center_lat, self.center_lon, self._zoom)
                except Exception:
                    pass
            try:
                self.set_zoom(int(z))
            except Exception:
                try:
                    self._zoom = int(z)
                    self._center_xf, self._center_yf = _latlon_to_tile_float(self.center_lat, self.center_lon, self._zoom)
                    self._request_redraw()
                except Exception:
                    pass
        except Exception:
            pass

    def _draw_status(self, n_hit: int, n_vis: int) -> None:
        try:
            n_fly = len(self._inflight)
            msg: str | None = None
            if n_fly > 0 or (n_vis > 0 and n_hit < n_vis):
                msg = f"読込中 {n_hit}/{n_vis}"
            elif n_vis > 0 and n_hit == 0:
                msg = "オフライン（キャッシュなし）"
            if msg is None:
                return
            self.create_rectangle(4, 4, 150, 22, fill="white", outline="#999", tags=("status",))
            self.create_text(8, 8, text=msg, fill="#333", font=("TkDefaultFont", 7), anchor="nw", tags=("status",))
            self.tag_raise("status")
        except Exception:
            pass

    def add_photo(self, path: str, lat: float | None = None, lon: float | None = None, opacity: float = 0.5, scale: float = 1.0) -> int:
        try:
            sc = float(scale)
        except Exception:
            sc = 1.0
        sc = min(8.0, max(0.01, sc))
        img, w, h = _load_photo_image(path, opacity, max_side=int(1024 * sc))
        if int(w) < 1:
            w = 1
        if int(h) < 1:
            h = 1
        self._photo_seq += 1
        # width_m derivation via mpp
        lat_f = float(self.center_lat if lat is None else lat)
        try:
            refz = int(self._zoom)
        except Exception:
            refz = 10
        try:
            width_m_val = float(w) * _mpp(lat_f, refz)
        except Exception:
            width_m_val = float(w) * 1.0
        rec = {
            "id": int(self._photo_seq),
            "path": str(path),
            "lat": float(self.center_lat if lat is None else lat),
            "lon": float(self.center_lon if lon is None else lon),
            "opacity": min(1.0, max(0.0, float(opacity))),
            "scale": float(sc),
            "img": img,
            "w": int(w),
            "h": int(h),
            "width_m": float(width_m_val),
            "ref_zoom": int(refz),
            "angle_deg": 0.0,
            "selected": False,
            "locked": False,
        }
        self._photos.append(rec)
        # auto-select new photo
        try:
            for r in self._photos:
                r["selected"] = int(r["id"]) == int(rec["id"])
            self._selected_photo_id = int(rec["id"])
        except Exception:
            pass
        try:
            self._request_redraw()
        except Exception:
            pass
        try:
            self._update_mode_style()
        except Exception:
            pass
        return int(rec["id"])

    def set_photo_opacity(self, pid: int, opacity: float) -> bool:
        for rec in self._photos:
            if int(rec["id"]) == int(pid):
                try:
                    sc = float(rec.get("scale", 1.0))
                except Exception:
                    sc = 1.0
                sc = min(8.0, max(0.01, sc))
                try:
                    img, w, h = _load_photo_image(str(rec["path"]), opacity, max_side=int(1024 * sc))
                except Exception:
                    return False
                rec["img"] = img
                rec["w"] = int(w)
                rec["h"] = int(h)
                rec["opacity"] = min(1.0, max(0.0, float(opacity)))
                # update width_m after w change
                try:
                    rec["width_m"] = float(w) * _mpp(float(rec["lat"]), int(rec.get("ref_zoom", self._zoom)))
                except Exception:
                    pass
                # invalidate cache
                try:
                    keys = [k for k in list(self._photo_image_cache.keys()) if int(k[0]) == int(pid)]
                    for k in keys:
                        self._photo_image_cache.pop(k, None)
                except Exception:
                    pass
                try:
                    self._request_redraw()
                except Exception:
                    pass
                return True
        return False

    def set_photo_scale(self, pid: int, scale: float) -> bool:
        try:
            sc = float(scale)
        except Exception:
            return False
        sc = min(8.0, max(0.01, sc))
        for rec in self._photos:
            if int(rec["id"]) == int(pid):
                if bool(rec.get("locked", False)):
                    return False
                try:
                    old_sc = float(rec.get("scale", 1.0))
                except Exception:
                    old_sc = 1.0
                old_sc = min(8.0, max(0.01, old_sc))
                old_w = int(rec.get("w", 0))
                old_h = int(rec.get("h", 0))
                try:
                    img, w, h = _load_photo_image(str(rec["path"]), rec.get("opacity", 0.5), max_side=int(1024 * sc))
                except Exception:
                    return False
                if int(w) < 1:
                    w = 1
                if int(h) < 1:
                    h = 1
                if old_w > 0 and old_h > 0 and old_sc > 0:
                    exp_w = int(round(old_w * sc / old_sc))
                    exp_h = int(round(old_h * sc / old_sc))
                    if abs(int(w) - exp_w) > 2 or abs(int(h) - exp_h) > 2:
                        w, h = exp_w, exp_h
                        if int(w) < 1:
                            w = 1
                        if int(h) < 1:
                            h = 1
                        try:
                            if abs(sc - old_sc) > 1e-9:
                                base_w = old_w / old_sc if old_sc else old_w
                                base_h = old_h / old_sc if old_sc else old_h
                                if abs(w - int(round(base_w * sc))) <= 2:
                                    pass
                        except Exception:
                            pass
                        try:
                            cur_w = int(img.width()) if hasattr(img, "width") else int(w)
                            cur_h = int(img.height()) if hasattr(img, "height") else int(h)
                            if cur_w != w or cur_h != h:
                                if sc > old_sc and cur_w > 0:
                                    factor = w / cur_w if cur_w else 1.0
                                    if factor > 1.01:
                                        try:
                                            z = int(round(factor))
                                            if z >= 2 and abs(z - factor) < 0.01:
                                                img = img.zoom(z, z)
                                            else:
                                                try:
                                                    import importlib as _il2
                                                    Image = _il2.import_module("PIL.Image")  # type: ignore
                                                    ImageTk = _il2.import_module("PIL.ImageTk")  # type: ignore
                                                    pil = Image.open(str(rec["path"])).convert("RGBA")
                                                    pil.thumbnail((int(1024 * sc), int(1024 * sc)))
                                                    nw = max(1, int(round(pil.size[0] * sc / sc)))
                                                    nh = max(1, int(round(pil.size[1] * sc / sc)))
                                                    if pil.size[0] != w or pil.size[1] != h:
                                                        pil = pil.resize((int(w), int(h)), Image.LANCZOS)  # type: ignore
                                                    img = ImageTk.PhotoImage(pil)
                                                except Exception:
                                                    pass
                                        except Exception:
                                            pass
                        except Exception:
                            pass
                if int(w) < 1:
                    w = 1
                if int(h) < 1:
                    h = 1
                rec["img"] = img
                rec["w"] = int(w)
                rec["h"] = int(h)
                rec["scale"] = float(sc)
                # update width_m to keep ground footprint consistent with new w at ref_zoom
                try:
                    rec["width_m"] = float(w) * _mpp(float(rec["lat"]), int(rec.get("ref_zoom", self._zoom)))
                except Exception:
                    pass
                # invalidate image cache
                try:
                    keys = [k for k in list(self._photo_image_cache.keys()) if int(k[0]) == int(pid)]
                    for k in keys:
                        self._photo_image_cache.pop(k, None)
                except Exception:
                    pass
                try:
                    self._request_redraw()
                except Exception:
                    pass
                return True
        return False

    def get_photo_scale(self, pid: int) -> float | None:
        for rec in self._photos:
            if int(rec["id"]) == int(pid):
                try:
                    return float(rec.get("scale", 1.0))
                except Exception:
                    return 1.0
        return None

    def set_photo_locked(self, pid: int, locked: bool) -> bool:
        for rec in self._photos:
            if int(rec["id"]) == int(pid):
                rec["locked"] = bool(locked)
                try:
                    self._request_redraw()
                except Exception:
                    pass
                return True
        return False

    def get_photo_locked(self, pid: int) -> bool | None:
        for rec in self._photos:
            if int(rec["id"]) == int(pid):
                return bool(rec.get("locked", False))
        return None

    def is_photo_locked(self, pid: int) -> bool | None:
        return self.get_photo_locked(pid)

    def remove_photo(self, pid: int) -> bool:
        for i, rec in enumerate(self._photos):
            if int(rec["id"]) == int(pid):
                del self._photos[i]
                if self._placing_photo_id == int(pid):
                    self._placing_photo_id = None
                if self._selected_photo_id == int(pid):
                    self._selected_photo_id = None
                # invalidate cache
                try:
                    keys = [k for k in list(self._photo_image_cache.keys()) if int(k[0]) == int(pid)]
                    for k in keys:
                        self._photo_image_cache.pop(k, None)
                except Exception:
                    pass
                self._request_redraw()
                try:
                    self._update_mode_style()
                except Exception:
                    pass
                return True
        return False

    def list_photos(self) -> list[int]:
        return [int(rec["id"]) for rec in self._photos]

    def get_photo(self, pid: int) -> dict | None:
        for rec in self._photos:
            if int(rec["id"]) == int(pid):
                return dict(rec)
        return None

    def clear_photos(self) -> None:
        self._photos = []
        self._placing_photo_id = None
        self._selected_photo_id = None
        self._dragging_photo_id = None
        self._dragging_photo = None
        try:
            self._photo_image_cache.clear()
        except Exception:
            pass
        self._request_redraw()
        try:
            self._update_mode_style()
        except Exception:
            pass

    def get_interact_mode(self) -> str:
        try:
            v = getattr(self, "_interact_mode", None)
            if isinstance(v, str) and v in ("trace", "place", "edit"):
                return v
        except Exception:
            pass
        try:
            var = getattr(self, "interact_mode_var", None)
            if var is not None and hasattr(var, "get"):
                gv = var.get()
                if isinstance(gv, str) and gv in ("trace", "place", "edit"):
                    return gv
        except Exception:
            pass
        try:
            v2 = getattr(self, "interact_mode", None)
            if isinstance(v2, str) and v2 in ("trace", "place", "edit"):
                return v2
        except Exception:
            pass
        return "trace"

    def set_interact_mode(self, mode: str) -> bool:
        try:
            m = str(mode).strip().lower()
            if m not in ("trace", "place", "edit"):
                return False
            self._interact_mode = m
            self.interact_mode = m
            try:
                var = getattr(self, "interact_mode_var", None)
                if var is not None and hasattr(var, "set"):
                    var.set(m)
            except Exception:
                pass
            try:
                var2 = getattr(self, "_interact_mode_var", None)
                if var2 is not None and var2 is not getattr(self, "interact_mode_var", None) and hasattr(var2, "set"):
                    var2.set(m)
            except Exception:
                pass
            if m == "trace":
                try:
                    self._placing_photo_id = None
                except Exception:
                    pass
                try:
                    self._dragging_photo_id = None
                    self._dragging_photo = None
                    self._dragging_handle = None
                except Exception:
                    pass
            elif m == "edit":
                try:
                    self._placing_photo_id = None
                except Exception:
                    pass
            elif m == "place":
                try:
                    if self._placing_photo_id is None and self._selected_photo_id is not None:
                        pid = int(self._selected_photo_id)
                        if self.get_photo(pid) is not None:
                            self._placing_photo_id = pid
                except Exception:
                    pass
            try:
                self._update_mode_style()
            except Exception:
                pass
            return True
        except Exception:
            return False

    def set_photo_interact_mode(self, mode: str) -> bool:
        return self.set_interact_mode(mode)

    def get_photo_interact_mode(self) -> str:
        return self.get_interact_mode()

    def set_mode(self, mode: str) -> bool:
        if str(mode).lower() in ("trace", "place", "edit"):
            return self.set_interact_mode(mode)
        return False

    def get_mode(self) -> str:
        try:
            if self._placing_photo_id is not None:
                return "place"
            if self._selected_photo_id is not None:
                return "select"
        except Exception:
            pass
        return "normal"

    def _update_mode_style(self) -> None:
        try:
            mode = self.get_mode()
            if mode == "place":
                bg = "#ff8c00"
                thick = 3
            elif mode == "select":
                bg = "#1f4b99"
                thick = 2
            else:
                bg = "#ccc"
                thick = 1
            try:
                self.configure(highlightbackground=bg, highlightthickness=thick)
            except Exception:
                pass
            try:
                self.delete("mode_banner")
            except Exception:
                pass
            try:
                self.create_text(6, 6, text=mode, fill=bg, font=("TkDefaultFont", 8), anchor="nw", tags=("mode_banner",))
            except Exception:
                pass
            try:
                self.tag_raise("mode_banner")
            except Exception:
                pass
        except Exception:
            pass

    def arm_photo_place(self, pid: int) -> bool:
        if self.get_photo(int(pid)) is None:
            return False
        self._placing_photo_id = int(pid)
        try:
            if self.get_interact_mode() != "place":
                self.set_interact_mode("place")
        except Exception:
            pass
        try:
            self._update_mode_style()
        except Exception:
            pass
        return True

    def disarm_photo_place(self) -> None:
        self._placing_photo_id = None
        try:
            self._update_mode_style()
        except Exception:
            pass

    def get_photo_specs(self) -> list[dict]:
        out: list[dict] = []
        for rec in self._photos:
            try:
                sc = float(rec.get("scale", 1.0))
            except Exception:
                sc = 1.0
            try:
                refz = int(rec.get("ref_zoom", self._zoom))
            except Exception:
                refz = int(self._zoom)
            try:
                ang = float(rec.get("angle_deg", 0.0) or 0.0)
            except Exception:
                ang = 0.0
            try:
                wm = float(rec.get("width_m", float(rec.get("w", 0)) * _mpp(float(rec["lat"]), refz)))
            except Exception:
                wm = float(rec.get("width_m", 0.0))
            out.append({"path": str(rec["path"]), "lat": float(rec["lat"]), "lon": float(rec["lon"]), "opacity": float(rec["opacity"]), "scale": float(sc), "ref_zoom": int(refz), "width_m": float(wm), "angle_deg": float(ang), "locked": bool(rec.get("locked", False))})
        return out

    def load_photo_specs(self, specs: object) -> int:
        n = 0
        try:
            items = list(specs)  # type: ignore[arg-type]
        except Exception:
            return 0
        for sp in items:
            try:
                if not isinstance(sp, dict):
                    continue
                p = str(sp.get("path", ""))
                if not p or not pathlib.Path(p).exists():
                    continue
                try:
                    sc = float(sp.get("scale", 1.0))
                except Exception:
                    sc = 1.0
                sc = min(8.0, max(0.01, sc))
                # ignore unknown keys: only use known ones
                try:
                    lat = sp.get("lat", None)
                except Exception:
                    lat = None
                try:
                    lon = sp.get("lon", None)
                except Exception:
                    lon = None
                try:
                    op = float(sp.get("opacity", 0.5))
                except Exception:
                    op = 0.5
                pid = self.add_photo(p, lat, lon, op, sc)
                # override ref_zoom/width_m/angle_deg if present
                try:
                    rec = None
                    for r in self._photos:
                        if int(r["id"]) == int(pid):
                            rec = r
                            break
                    if rec is not None:
                        if "ref_zoom" in sp:
                            try:
                                rec["ref_zoom"] = int(sp.get("ref_zoom", self._zoom))
                            except Exception:
                                pass
                        if "width_m" in sp:
                            try:
                                rec["width_m"] = float(sp.get("width_m", rec.get("width_m", 0.0)))
                            except Exception:
                                pass
                        else:
                            # if width_m not supplied but width present? ignore unknown keys
                            pass
                        if "angle_deg" in sp:
                            try:
                                rec["angle_deg"] = float(sp.get("angle_deg", 0.0))
                            except Exception:
                                rec["angle_deg"] = 0.0
                        if "locked" in sp:
                            try:
                                rec["locked"] = bool(sp.get("locked", False))
                            except Exception:
                                rec["locked"] = False
                        # also handle legacy width key but ignore unknown unknown_key
                        # ensure selected default False (already)
                        pass
                except Exception:
                    pass
                n += 1
            except Exception:
                pass
        return n

    def _draw_points(self) -> None:
        if len(self.points_latlon) >= 2:
            try:
                coords: list[float] = []
                for lat, lon in self.points_latlon:
                    px, py = self._latlon_to_pixel(lat, lon)
                    coords.extend([float(px), float(py)])
                if len(coords) >= 4:
                    self.create_line(*coords, fill="#1f4b99", width=2, smooth=False, tags=("point",))
                    if bool(getattr(self, "closed_loop", False)):
                        self.create_line(coords[-2], coords[-1], coords[0], coords[1], fill="#1f4b99", width=2, dash=(5, 3), smooth=False, tags=("point", "closing"))
            except Exception:
                pass
        for idx, (lat, lon) in enumerate(self.points_latlon):
            try:
                px, py = self._latlon_to_pixel(lat, lon)
                self.create_oval(px - 5, py - 5, px + 5, py + 5, fill="#ff3333", outline="white", width=2, tags=("point",))
                self.create_text(px, py - 10, text=str(idx + 1), fill="#222", font=("TkDefaultFont", 7, "bold"), tags=("point",))
            except Exception:
                pass

    def _draw_points_only(self) -> None:
        try:
            self.delete("point")
        except Exception:
            pass
        if len(self.points_latlon) >= 2:
            try:
                coords: list[float] = []
                for lat, lon in self.points_latlon:
                    px, py = self._latlon_to_pixel(lat, lon)
                    coords.extend([float(px), float(py)])
                if len(coords) >= 4:
                    self.create_line(*coords, fill="#1f4b99", width=2, smooth=False, tags=("point",))
                    if bool(getattr(self, "closed_loop", False)):
                        self.create_line(coords[-2], coords[-1], coords[0], coords[1], fill="#1f4b99", width=2, dash=(5, 3), smooth=False, tags=("point", "closing"))
            except Exception:
                pass
        for idx, (lat, lon) in enumerate(self.points_latlon):
            try:
                px, py = self._latlon_to_pixel(lat, lon)
                self.create_oval(px - 5, py - 5, px + 5, py + 5, fill="#ff3333", outline="white", width=2, tags=("point",))
                self.create_text(px, py - 10, text=str(idx + 1), fill="#222", font=("TkDefaultFont", 7, "bold"), tags=("point",))
            except Exception:
                pass

    def _draw_attribution(self) -> None:
        try:
            w = int(self.winfo_width()) or self._width
            h = int(self.winfo_height()) or self._height
            if w < 10:
                w = self._width
            if h < 10:
                h = self._height
            txt = geo_tile.ATTRIBUTION
            # background for readability
            self.create_rectangle(w - 210, h - 16, w, h, fill="white", outline="", stipple="gray50", tags=("attribution",))
            self.create_text(w - 4, h - 4, text=txt, fill="#333", font=("TkDefaultFont", 7), anchor="se", tags=("attribution",))
            self.tag_raise("attribution")
        except Exception:
            pass

    def _fetch_tile_async(self, z: int, x: int, y: int) -> None:
        cache_key = (int(z), int(x), int(y))
        if cache_key in self._tile_cache:
            return
        gen = int(self._redraw_gen)
        key = (int(z), int(x), int(y), gen)
        if key in self._inflight:
            return
        if len(self._inflight) >= MAX_PENDING_FETCH:
            return
        self._inflight.add(key)

        def worker() -> None:
            try:
                with self._sem:
                    try:
                        data = geo_tile.fetch_tile(z, x, y, base_url=self.base_url, cache_dir=self.cache_dir)  # type: ignore[arg-type]
                    except TypeError:
                        data = geo_tile.fetch_tile(z, x, y)
                    self._queue.put((z, x, y, gen, data, None))
            except Exception as e:
                try:
                    self._queue.put((z, x, y, gen, None, e))
                except Exception:
                    try:
                        self._inflight.discard(key)
                    except Exception:
                        pass

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _ensure_polling(self) -> None:
        if self._polling:
            return
        self._polling = True
        try:
            self.after(10, self._poll_queue)
        except Exception:
            pass

    def _poll_queue(self) -> None:
        redrawn = False
        try:
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                # support both old 5-tuple (z,x,y,data,err) and new 6-tuple (z,x,y,gen,data,err)
                if len(item) == 6:
                    z, x, y, gen, data, err = item  # type: ignore[misc]
                elif len(item) == 5:
                    z, x, y, data, err = item  # type: ignore[misc]
                    gen = None
                else:
                    continue
                cache_key = (int(z), int(x), int(y))
                # discard from inflight (try both 3 and 4 tuple keys)
                try:
                    if gen is not None:
                        self._inflight.discard((int(z), int(x), int(y), int(gen)))
                    self._inflight.discard(cache_key)
                except Exception:
                    pass
                # discard stale zoom/gen (T5)
                try:
                    if int(z) != int(self._zoom):
                        continue
                    if gen is not None and int(gen) != int(self._redraw_gen):
                        continue
                except Exception:
                    pass
                if err is None and data is not None and cache_key not in self._tile_cache:
                    try:
                        if data == geo_tile.PLACEHOLDER_PNG:
                            continue
                    except Exception:
                        pass
                    try:
                        b64 = base64.b64encode(data).decode("ascii")
                        img = tk.PhotoImage(data=b64)
                        self._cache_store(cache_key, img)
                        redrawn = True
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            if redrawn:
                self._request_redraw()
            try:
                if self.winfo_exists():
                    self.after(10, self._poll_queue)
            except Exception:
                pass

    def destroy(self) -> None:  # type: ignore[override]
        self._polling = False
        try:
            if self._redraw_after_id is not None:
                self.after_cancel(self._redraw_after_id)
        except Exception:
            pass
        self._redraw_after_id = None
        try:
            self._inflight.clear()
        except Exception:
            pass
        try:
            if self._after_id is not None:
                self.after_cancel(self._after_id)
        except Exception:
            pass
        try:
            self._queue = queue.Queue()
        except Exception:
            pass
        try:
            return super().destroy()
        except Exception:
            pass
