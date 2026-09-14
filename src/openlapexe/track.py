# -*- coding: utf-8 -*-
# allow: SIZE_OK — OpenTRACK 820 lines full port (shape/logged, mesh, map generation)
"""openlapexe.track - OpenTRACK full port (820 lines equivalent, numpy only, deterministic).

Original: OpenTRACK.m 820 lines (shape/logged, mesh 1..5, PCHIP curvature,
linear elevation/banking, grip/sector handling, closed correction, direction).

This module ports the logic in Python with strict constraints:
- numpy only (no scipy/matplotlib)
- PCHIP self-made Fritsch-Carlson (duplicated from app.py _pchip)
- mesh(1..5): curv/elevation/banking = PCHIP, grip = np.interp clamp
- logged=True => s reversal + closed processing (deterministic)
- points columns: s, x, y, z, curv, banking_rad, grip_factor, sector_id
  (first 5 for backward compat, extended 8 columns)
- encoding utf-8 for JSON
- app.py Track preserved (separate implementation); src version coexists.

Public API: Track, Track2 (alias), _pchip_* helpers
"""
from __future__ import annotations

import datetime
import json
import math
import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

# ---------------------------------------------------------------------------
# helpers: resource path (re-use openlapexe.io if available)
# ---------------------------------------------------------------------------
try:
    from openlapexe.io import resource_path as _resource_path  # type: ignore
except Exception:
    def _resource_path(relative: str) -> pathlib.Path:  # fallback
        if hasattr(sys, "_MEIPASS"):
            base = pathlib.Path(str(sys._MEIPASS))  # type: ignore[attr-defined]
        else:
            base = pathlib.Path(__file__).resolve().parents[2]
            if not (base / "app.py").exists() and not (base / "data").exists():
                base = pathlib.Path(__file__).resolve().parent.parent.parent
        return base / relative

def _resolve_track_path(name: str) -> pathlib.Path | None:
    base = pathlib.Path(__file__).resolve().parents[2] / "data" / "tracks"
    # also try project root via _resource_path
    candidates: list[pathlib.Path] = []
    raw = name.strip()
    cand_names: list[str] = []
    cand_names.append(raw)
    if not raw.lower().endswith(".json"):
        cand_names.append(raw + ".json")
    cand_names.append(raw.lower())
    if not raw.lower().endswith(".json"):
        cand_names.append(raw.lower() + ".json")
    for variant in list(cand_names):
        cand_names.append(variant.replace(" ", "-"))
        cand_names.append(variant.replace(" ", "_"))
        cand_names.append(variant.replace("-", "_"))
    # dedup preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for c in cand_names:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    paths_to_try: list[pathlib.Path] = []
    for cn in uniq:
        paths_to_try.append(base / cn)
        try:
            rp = _resource_path(f"data/tracks/{cn}")
            if rp not in paths_to_try:
                paths_to_try.append(rp)
        except Exception:
            pass
        # also try absolute/relative as given
        pp = pathlib.Path(cn)
        if pp not in paths_to_try:
            paths_to_try.append(pp)
    for p in paths_to_try:
        try:
            if p.exists() and p.is_file():
                return p
        except Exception:
            continue
    # glob fallback
    try:
        if base.exists():
            target = raw.lower().replace(".json", "")
            for pp in base.glob("*.json"):
                stem = pp.stem.lower()
                if stem == target or stem.replace("-", "").replace("_", "") == target.replace("-", "").replace("_", ""):
                    return pp
                if len(target) >= 3 and target[:3] in stem:
                    return pp
    except Exception:
        pass
    return None

# ---------------------------------------------------------------------------
# PCHIP Fritsch-Carlson (duplicated from app.py _pchip, 60 lines, numpy only)
# ---------------------------------------------------------------------------
def _pchip_slopes(x: npt.NDArray[np.float64], y: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    n: int = int(x.shape[0])
    h: npt.NDArray[np.float64] = np.diff(x)
    delta: npt.NDArray[np.float64] = np.diff(y) / h
    m: npt.NDArray[np.float64] = np.zeros(n, dtype=np.float64)
    if n == 2:
        m[0] = delta[0]
        m[1] = delta[0]
        return m
    for i in range(1, n - 1):
        if delta[i - 1] * delta[i] <= 0.0:
            m[i] = 0.0
        else:
            w1: float = 2.0 * h[i] + h[i - 1]
            w2: float = h[i] + 2.0 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
    m[0] = ((2.0 * h[0] + h[1]) * delta[0] - h[0] * delta[1]) / (h[0] + h[1])
    if m[0] * delta[0] < 0.0:
        m[0] = 0.0
    elif delta[0] == 0.0:
        m[0] = 0.0
    else:
        if math.fabs(m[0]) > math.fabs(3.0 * delta[0]):
            m[0] = 3.0 * delta[0]
    m[n - 1] = ((2.0 * h[n - 2] + h[n - 3]) * delta[n - 2] - h[n - 2] * delta[n - 3]) / (h[n - 2] + h[n - 3])
    if m[n - 1] * delta[n - 2] < 0.0:
        m[n - 1] = 0.0
    elif delta[n - 2] == 0.0:
        m[n - 1] = 0.0
    else:
        if math.fabs(m[n - 1]) > math.fabs(3.0 * delta[n - 2]):
            m[n - 1] = 3.0 * delta[n - 2]
    for i in range(n):  # inclusive endpoint S-OT4
        if i >= n - 1:
            continue
        if delta[i] == 0.0:
            m[i] = 0.0
            m[i + 1] = 0.0
        else:
            alpha: float = float(m[i] / delta[i])
            beta: float = float(m[i + 1] / delta[i])
            tau: float = alpha * alpha + beta * beta
            if tau > 9.0:
                t: float = 3.0 / math.sqrt(tau)
                m[i] = t * alpha * delta[i]
                m[i + 1] = t * beta * delta[i]
    return m

def _pchip_eval(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    m: npt.NDArray[np.float64],
    x_new: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    n: int = int(x.shape[0])
    res: npt.NDArray[np.float64] = np.empty_like(x_new, dtype=np.float64)
    lo: float = float(x[0])
    hi: float = float(x[n - 1])
    for idx in range(int(x_new.shape[0])):
        xi: float = float(x_new[idx])
        if xi <= lo:
            res[idx] = float(y[0])
            continue
        if xi >= hi:
            res[idx] = float(y[n - 1])
            continue
        k: int = int(np.searchsorted(x, xi, side="right") - 1)
        if k < 0:
            k = 0
        if k >= n - 1:
            k = n - 2
        h: float = float(x[k + 1] - x[k])
        if h < 1e-9:  # S-OT5 PCHIP h=0 guard ensure finite
            h = 1e-9
        t: float = (xi - float(x[k])) / h
        t2: float = t * t
        t3: float = t2 * t
        h00: float = 2.0 * t3 - 3.0 * t2 + 1.0
        h10: float = t3 - 2.0 * t2 + t
        h01: float = -2.0 * t3 + 3.0 * t2
        h11: float = t3 - t2
        res[idx] = h00 * float(y[k]) + h10 * h * float(m[k]) + h01 * float(y[k + 1]) + h11 * h * float(m[k + 1])
    _ = np.interp(x_new, x, y)
    return res

def _pchip_interp(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    x_new: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    order: npt.NDArray[np.intp] = np.argsort(x)
    xs: npt.NDArray[np.float64] = x[order].astype(np.float64, copy=False)
    ys: npt.NDArray[np.float64] = y[order].astype(np.float64, copy=False)
    # handle duplicates: keep last (average)
    # deduplicate by unique with averaging
    if xs.shape[0] >= 2:
        uniq_x: list[float] = []
        uniq_y: list[float] = []
        i = 0
        while i < xs.shape[0]:
            j = i + 1
            while j < xs.shape[0] and xs[j] == xs[i]:
                j += 1
            # average y over duplicate x
            avg = float(np.mean(ys[i:j]))
            uniq_x.append(float(xs[i]))
            uniq_y.append(avg)
            i = j
        if len(uniq_x) != xs.shape[0]:
            xs = np.array(uniq_x, dtype=np.float64)
            ys = np.array(uniq_y, dtype=np.float64)
            if xs.shape[0] == 1:
                # single point -> constant
                return np.full_like(x_new, float(ys[0]), dtype=np.float64)
    slopes: npt.NDArray[np.float64] = _pchip_slopes(xs, ys)
    return _pchip_eval(xs, ys, slopes, x_new.astype(np.float64, copy=False))

# also expose under names used by tests
pchip_slopes = _pchip_slopes
pchip_eval = _pchip_eval
pchip_interp = _pchip_interp

def _triangle_curvature(x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> float:
    a = math.hypot(x1 - x2, y1 - y2)
    b = math.hypot(x2 - x3, y2 - y3)
    c = math.hypot(x1 - x3, y1 - y3)
    if a == 0 or b == 0 or c == 0:
        return 0.0
    cross = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)
    denom = a * b * c
    if denom == 0:
        return 0.0
    return 2.0 * cross / denom

def _find_peaks_indices(arr: npt.NDArray[np.float64], threshold: float = 0.0, use_abs: bool = False) -> list[int]:
    a = np.asarray(arr, dtype=float)
    if use_abs:
        a = np.abs(a)
    n = int(a.shape[0])
    if n < 3:
        return []
    peaks: list[int] = []
    for i in range(1, n - 1):
        if a[i] > a[i - 1] and a[i] > a[i + 1] and a[i] > threshold:
            peaks.append(i)
    return peaks

# ---------------------------------------------------------------------------
# Track dataclass (extended 8 columns)
# ---------------------------------------------------------------------------
@dataclass
class Track:
    name: str
    length_m: float = 0.0
    closed_loop: bool = True
    points: npt.NDArray[np.float64] = field(default_factory=lambda: np.zeros((0, 8), dtype=float))
    logged: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    # internal caches (filled in __post_init__)
    _s: npt.NDArray[np.float64] = field(init=False, repr=False, default=None)  # type: ignore
    _x: npt.NDArray[np.float64] = field(init=False, repr=False, default=None)  # type: ignore
    _y: npt.NDArray[np.float64] = field(init=False, repr=False, default=None)  # type: ignore
    _z: npt.NDArray[np.float64] = field(init=False, repr=False, default=None)  # type: ignore
    _curv: npt.NDArray[np.float64] = field(init=False, repr=False, default=None)  # type: ignore
    _bank: npt.NDArray[np.float64] = field(init=False, repr=False, default=None)  # type: ignore
    _grip: npt.NDArray[np.float64] = field(init=False, repr=False, default=None)  # type: ignore
    _sector: npt.NDArray[np.float64] = field(init=False, repr=False, default=None)  # type: ignore

    def __post_init__(self) -> None:
        if not isinstance(self.meta, dict):
            try:
                self.meta = dict(self.meta)  # type: ignore[arg-type]
            except Exception:
                self.meta = {}
        # normalize points to ndarray
        if isinstance(self.points, list):
            try:
                if len(self.points) > 0 and isinstance(self.points[0], dict):
                    n = len(self.points)
                    s = np.array([float(p.get("s", 0)) for p in self.points], dtype=float)
                    x = np.array([float(p.get("x", 0)) for p in self.points], dtype=float)
                    y = np.array([float(p.get("y", 0)) for p in self.points], dtype=float)
                    z = np.array([float(p.get("z", 0)) for p in self.points], dtype=float)
                    curv = np.array([float(p.get("curv", p.get("curvature", 0))) for p in self.points], dtype=float)
                    bank = np.array([float(p.get("banking_rad", p.get("bank_rad", p.get("bank", 0)))) for p in self.points], dtype=float)
                    # banking may be in deg in old files -> if abs > pi, treat as deg
                    # but new json stores rad; keep as is
                    grip = np.array([float(p.get("grip_factor", p.get("grip", 1.0))) for p in self.points], dtype=float)
                    sector = np.array([float(p.get("sector_id", p.get("sector", 0))) for p in self.points], dtype=float)
                    self.points = np.column_stack([s, x, y, z, curv, bank, grip, sector])
                else:
                    self.points = np.asarray(self.points, dtype=float)
            except Exception:
                self.points = np.asarray(self.points, dtype=float)
        else:
            try:
                self.points = np.asarray(self.points, dtype=float)
            except Exception:
                pass
        if isinstance(self.points, np.ndarray) and self.points.ndim == 1 and self.points.size == 0:
            self.points = np.zeros((0, 8), dtype=float)
        if isinstance(self.points, np.ndarray) and self.points.ndim == 1 and self.points.size > 0:
            self.points = self.points.reshape(1, -1)
        # ensure 2D and at least 8 columns; pad if needed
        if isinstance(self.points, np.ndarray) and self.points.ndim == 2:
            if self.points.shape[1] == 5:
                # pad banking,grip,sector
                n = self.points.shape[0]
                bank = np.zeros(n, dtype=float)
                grip = np.ones(n, dtype=float)
                sector = np.zeros(n, dtype=float)
                self.points = np.column_stack([self.points, bank, grip, sector])
            elif self.points.shape[1] == 6:
                n = self.points.shape[0]
                grip = np.ones(n, dtype=float)
                sector = np.zeros(n, dtype=float)
                self.points = np.column_stack([self.points, grip, sector])
            elif self.points.shape[1] == 7:
                n = self.points.shape[0]
                sector = np.zeros(n, dtype=float)
                self.points = np.column_stack([self.points, sector])
            elif self.points.shape[1] < 5:
                # fallback: pad to 8
                n = self.points.shape[0]
                # synthesize s as index if needed
                # but keep as is and expand
                cols = self.points.shape[1]
                extra = 8 - cols
                pad = np.zeros((n, extra), dtype=float)
                # set grip default 1 if grip column missing
                if extra >= 3:
                    pad[:, 1] = 1.0  # grip column offset
                self.points = np.hstack([self.points, pad])
        # auto-load if empty and name corresponds to json file
        if isinstance(self.points, np.ndarray) and self.points.shape[0] == 0 and self.length_m == 0.0:
            pp = _resolve_track_path(self.name)
            if pp is not None and pp.exists():
                try:
                    loaded = Track.from_json(self.name)
                    self.length_m = float(loaded.length_m)
                    self.closed_loop = bool(loaded.closed_loop)
                    self.logged = bool(loaded.logged)
                    if not self.meta and isinstance(loaded.meta, dict):
                        self.meta = dict(loaded.meta)
                    if loaded.points.shape[0] > 0:
                        avg_spacing = loaded.length_m / max(1, loaded.points.shape[0])
                        if avg_spacing > 1.5:
                            try:
                                meshed = loaded.mesh(1.0)
                                self.points = meshed.points
                                self.length_m = meshed.length_m
                                self.closed_loop = meshed.closed_loop
                                self.logged = meshed.logged
                                if not self.meta and isinstance(meshed.meta, dict) and meshed.meta:
                                    self.meta = dict(meshed.meta)
                            except Exception:
                                self.points = loaded.points
                        else:
                            self.points = loaded.points
                    else:
                        self.points = loaded.points
                except Exception:
                    pass
        self._rebuild_cache()

    def _rebuild_cache(self) -> None:
        if not isinstance(self.points, np.ndarray) or self.points.size == 0:
            self._s = np.array([], dtype=float)
            self._x = np.array([], dtype=float)
            self._y = np.array([], dtype=float)
            self._z = np.array([], dtype=float)
            self._curv = np.array([], dtype=float)
            self._bank = np.array([], dtype=float)
            self._grip = np.array([], dtype=float)
            self._sector = np.array([], dtype=float)
            return
        pts = self.points
        try:
            if pts.ndim == 2 and pts.shape[1] >= 8:
                self._s = np.asarray(pts[:, 0], dtype=float)
                self._x = np.asarray(pts[:, 1], dtype=float)
                self._y = np.asarray(pts[:, 2], dtype=float)
                self._z = np.asarray(pts[:, 3], dtype=float)
                self._curv = np.asarray(pts[:, 4], dtype=float)
                self._bank = np.asarray(pts[:, 5], dtype=float)
                self._grip = np.asarray(pts[:, 6], dtype=float)
                self._sector = np.asarray(pts[:, 7], dtype=float)
            elif pts.ndim == 2 and pts.shape[1] >= 5:
                self._s = np.asarray(pts[:, 0], dtype=float)
                self._x = np.asarray(pts[:, 1], dtype=float)
                self._y = np.asarray(pts[:, 2], dtype=float)
                self._z = np.asarray(pts[:, 3], dtype=float)
                self._curv = np.asarray(pts[:, 4], dtype=float)
                self._bank = np.zeros_like(self._s)
                self._grip = np.ones_like(self._s)
                self._sector = np.zeros_like(self._s)
                if pts.shape[1] > 5:
                    self._bank = np.asarray(pts[:, 5], dtype=float)
                if pts.shape[1] > 6:
                    self._grip = np.asarray(pts[:, 6], dtype=float)
                if pts.shape[1] > 7:
                    self._sector = np.asarray(pts[:, 7], dtype=float)
            else:
                # fallback 3 cols etc handled minimal
                flat = pts.reshape(pts.shape[0], -1)
                n = flat.shape[0]
                self._s = np.arange(float(n), dtype=float)
                self._x = flat[:, 0].astype(float) if flat.shape[1] > 0 else np.zeros(n)
                self._y = flat[:, 1].astype(float) if flat.shape[1] > 1 else np.zeros(n)
                self._z = np.zeros(n)
                self._curv = np.zeros(n)
                self._bank = np.zeros(n)
                self._grip = np.ones(n)
                self._sector = np.zeros(n)
            if self.length_m == 0.0 and self._s.size > 0:
                self.length_m = float(self._s[-1]) if self._s[-1] > 0 else float(np.max(self._s))
        except Exception:
            pass
        try:
            if isinstance(self._curv, np.ndarray) and self._curv.size >= 3 and isinstance(self._x, np.ndarray) and isinstance(self._y, np.ndarray) and self._x.size >= 3:
                _max_abs = float(np.max(np.abs(self._curv))) if self._curv.size else 0.0
                if _max_abs < 1e-9:
                    _x_range = float(np.max(self._x) - np.min(self._x)) if self._x.size else 0.0
                    _y_range = float(np.max(self._y) - np.min(self._y)) if self._y.size else 0.0
                    if max(abs(_x_range), abs(_y_range)) > 1e-9:
                        _n = int(self._curv.shape[0])
                        _xy = np.column_stack([np.asarray(self._x, dtype=float), np.asarray(self._y, dtype=float)])
                        _new_curv = None
                        try:
                            from openlapexe.curvature_opt import compute_curvature_profile as _ccp2  # type: ignore

                            _tmp = np.asarray(_ccp2(_xy, closed=bool(getattr(self, "closed_loop", True))), dtype=float).reshape(-1)
                            if _tmp.shape[0] == _n:
                                _tmp = np.where(np.isfinite(_tmp), _tmp, 0.0)
                                _new_curv = np.abs(_tmp)
                        except Exception:
                            _new_curv = None
                        if _new_curv is None:
                            _new_curv = np.zeros(_n, dtype=float)
                            try:
                                _mx = float(np.mean(self._x))
                                _my = float(np.mean(self._y))
                                _x0 = np.asarray(self._x, dtype=float) - _mx
                                _y0 = np.asarray(self._y, dtype=float) - _my
                                _eps = 1e-12
                                _closed = bool(getattr(self, "closed_loop", True))
                                for _i in range(_n):
                                    if not _closed and (_i == 0 or _i == _n - 1):
                                        _new_curv[_i] = 0.0
                                        continue
                                    _im1 = (_i - 1) % _n if _closed else _i - 1
                                    _ip1 = (_i + 1) % _n if _closed else _i + 1
                                    _xp = 0.5 * (float(_x0[_ip1]) - float(_x0[_im1]))
                                    _yp = 0.5 * (float(_y0[_ip1]) - float(_y0[_im1]))
                                    _xpp = float(_x0[_ip1]) - 2.0 * float(_x0[_i]) + float(_x0[_im1])
                                    _ypp = float(_y0[_ip1]) - 2.0 * float(_y0[_i]) + float(_y0[_im1])
                                    _pn = float(np.hypot(_xp, _yp))
                                    _den = _pn**3 + _eps
                                    _cross = abs(_xp * _ypp - _yp * _xpp)
                                    _k = _cross / _den if _den != 0 else 0.0
                                    if not np.isfinite(_k) or _k < 0:
                                        _k = 0.0
                                    _new_curv[_i] = float(_k)
                                _new_curv[~np.isfinite(_new_curv)] = 0.0
                                _new_curv = np.abs(_new_curv)
                            except Exception:
                                _new_curv = np.zeros(_n, dtype=float)
                        if _new_curv is not None and _new_curv.shape[0] == _n:
                            self._curv = np.asarray(_new_curv, dtype=float)
                            try:
                                if isinstance(self.points, np.ndarray) and self.points.ndim == 2 and self.points.shape[0] == _n and self.points.shape[1] >= 5:
                                    self.points[:, 4] = np.asarray(_new_curv, dtype=float)
                            except Exception:
                                pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # conveniences for legacy 5-col access
    # ------------------------------------------------------------------
    @property
    def banking_rad(self) -> npt.NDArray[np.float64]:
        return np.asarray(self._bank, dtype=float) if self._bank is not None else np.array([], dtype=float)

    @property
    def grip_factor(self) -> npt.NDArray[np.float64]:
        return np.asarray(self._grip, dtype=float) if self._grip is not None else np.array([], dtype=float)

    @property
    def sector_id(self) -> npt.NDArray[np.float64]:
        return np.asarray(self._sector, dtype=float) if self._sector is not None else np.array([], dtype=float)

    # ------------------------------------------------------------------
    # from_json
    # ------------------------------------------------------------------
    @classmethod
    def from_json(cls, name: str) -> "Track":
        p = _resolve_track_path(name)
        if p is None or not p.exists():
            alt = pathlib.Path(name)
            if alt.exists():
                p = alt
            else:
                raise FileNotFoundError(f"track json not found for name={name!r}")
        txt = p.read_text(encoding="utf-8")
        data = json.loads(txt)
        tname = str(data.get("name", name))
        length_m = float(data.get("length_m", data.get("length", data.get("L", 0.0))))
        closed_loop = bool(data.get("closed_loop", data.get("closed", True)))
        logged = bool(data.get("logged", data.get("is_logged", False)))
        pts_raw = data.get("points", [])
        n = len(pts_raw)
        s_arr = np.zeros(n, dtype=float)
        x_arr = np.zeros(n, dtype=float)
        y_arr = np.zeros(n, dtype=float)
        z_arr = np.zeros(n, dtype=float)
        curv_arr = np.zeros(n, dtype=float)
        bank_arr = np.zeros(n, dtype=float)
        grip_arr = np.ones(n, dtype=float)
        sector_arr = np.zeros(n, dtype=float)
        for i, pt in enumerate(pts_raw):
            s_arr[i] = float(pt.get("s", 0.0))
            x_arr[i] = float(pt.get("x", 0.0))
            y_arr[i] = float(pt.get("y", 0.0))
            z_arr[i] = float(pt.get("z", 0.0))
            curv_arr[i] = float(pt.get("curv", pt.get("curvature", 0.0)))
            # banking_rad variants
            bv = pt.get("banking_rad", pt.get("bank_rad", pt.get("bank", pt.get("banking", None))))
            if bv is not None:
                # if value looks like deg (|val|>pi), convert assuming deg; else rad
                v = float(bv)
                # Heuristic: if abs(v) > 0.5 and abs(v) < 10 and n>0: could be rad already max ~0.17 rad (10 deg)
                # But deg values would be larger: 5 deg = 0.087 rad; still small. So not distinguishable.
                # Use explicit check: if original json had bank stored as deg, it would be >1 for 5 deg? No 5 deg =5. So rad 0.087 vs deg 5 difference factor ~57.
                # We treat values > 0.5 and < 30 as deg if they appear large? Safer: if abs(v) > math.pi (3.14) treat as deg.
                if abs(v) > math.pi:
                    v = math.radians(v)
                bank_arr[i] = v
            else:
                bank_arr[i] = 0.0
            gv = pt.get("grip_factor", pt.get("grip", pt.get("gripFactor", None)))
            if gv is not None:
                grip_arr[i] = float(gv)
            else:
                grip_arr[i] = 1.0
            sv = pt.get("sector_id", pt.get("sector", pt.get("sectorId", None)))
            if sv is not None:
                sector_arr[i] = float(sv)
            else:
                sector_arr[i] = 0.0
        try:
            if n >= 3 and curv_arr.size >= 3:
                _max_abs_curv = float(np.max(np.abs(curv_arr))) if curv_arr.size else 0.0
                if _max_abs_curv < 1e-9:
                    _x_range = float(np.max(x_arr) - np.min(x_arr)) if x_arr.size else 0.0
                    _y_range = float(np.max(y_arr) - np.min(y_arr)) if y_arr.size else 0.0
                    if max(abs(_x_range), abs(_y_range)) > 1e-9:
                        _healed = None
                        try:
                            from openlapexe.curvature_opt import compute_curvature_profile as _ccp3  # type: ignore

                            _xy3 = np.column_stack([np.asarray(x_arr, dtype=float), np.asarray(y_arr, dtype=float)])
                            _tmp3 = np.asarray(_ccp3(_xy3, closed=bool(closed_loop)), dtype=float).reshape(-1)
                            if _tmp3.shape[0] == n:
                                _tmp3 = np.where(np.isfinite(_tmp3), _tmp3, 0.0)
                                _healed = np.abs(_tmp3)
                        except Exception:
                            _healed = None
                        if _healed is None:
                            _healed = np.zeros(n, dtype=float)
                            try:
                                _mx3 = float(np.mean(x_arr))
                                _my3 = float(np.mean(y_arr))
                                _x03 = np.asarray(x_arr, dtype=float) - _mx3
                                _y03 = np.asarray(y_arr, dtype=float) - _my3
                                _eps3 = 1e-12
                                _closed3 = bool(closed_loop)
                                for _i3 in range(n):
                                    if not _closed3 and (_i3 == 0 or _i3 == n - 1):
                                        _healed[_i3] = 0.0
                                        continue
                                    _im1 = (_i3 - 1) % n if _closed3 else _i3 - 1
                                    _ip1 = (_i3 + 1) % n if _closed3 else _i3 + 1
                                    _xp = 0.5 * (float(_x03[_ip1]) - float(_x03[_im1]))
                                    _yp = 0.5 * (float(_y03[_ip1]) - float(_y03[_im1]))
                                    _xpp = float(_x03[_ip1]) - 2.0 * float(_x03[_i3]) + float(_x03[_im1])
                                    _ypp = float(_y03[_ip1]) - 2.0 * float(_y03[_i3]) + float(_y03[_im1])
                                    _pn = float(np.hypot(_xp, _yp))
                                    _den = _pn**3 + _eps3
                                    _cross = abs(_xp * _ypp - _yp * _xpp)
                                    _k = _cross / _den if _den != 0 else 0.0
                                    if not np.isfinite(_k) or _k < 0:
                                        _k = 0.0
                                    _healed[_i3] = float(_k)
                                _healed[~np.isfinite(_healed)] = 0.0
                                _healed = np.abs(_healed)
                            except Exception:
                                _healed = np.zeros(n, dtype=float)
                        if _healed is not None and _healed.shape[0] == n:
                            curv_arr = np.asarray(_healed, dtype=float)
        except Exception:
            pass
        points_arr = np.column_stack([s_arr, x_arr, y_arr, z_arr, curv_arr, bank_arr, grip_arr, sector_arr])
        if length_m == 0.0 and n > 0:
            length_m = float(s_arr[-1])
        meta_raw = data.get("meta", None)
        meta_dict: dict[str, Any] = {}
        if isinstance(meta_raw, dict):
            meta_dict = dict(meta_raw)
        # also tolerate top-level source/created for backward compat
        for _k in ("source", "created", "creator_mode", "zone"):
            if _k not in meta_dict and _k in data:
                meta_dict[_k] = data[_k]
        obj = cls(name=tname, length_m=length_m, closed_loop=closed_loop, points=points_arr, logged=logged, meta=meta_dict)
        obj._rebuild_cache()
        return obj

    @classmethod
    def from_candidates(cls, cands: Any, mode: str = "dxf", closed_loop: bool = True) -> "Track":
        if isinstance(cands, (list, tuple)):
            cand_list = list(cands)
        else:
            cand_list = [cands]
        if len(cand_list) == 0:
            raise ValueError("cands must be non-empty")
        xs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        zone_val: int | None = None
        source_name: str = ""
        for cand in cand_list:
            arr_xy: np.ndarray | None = None
            pts_lonlat: Any = None
            cand_name: str = ""
            if isinstance(cand, dict):
                cand_name = str(cand.get("name", ""))
                if "points_xy" in cand and cand["points_xy"] is not None:
                    try:
                        tmp = np.asarray(cand["points_xy"], dtype=float)
                        if tmp.size > 0:
                            arr_xy = tmp
                    except Exception:
                        arr_xy = None
                if arr_xy is None and "points_lonlat" in cand and cand["points_lonlat"] is not None:
                    pts_lonlat = cand["points_lonlat"]
            else:
                try:
                    cand_name = str(getattr(cand, "name", ""))
                except Exception:
                    cand_name = ""
                if hasattr(cand, "points_xy"):
                    try:
                        v = getattr(cand, "points_xy")
                        if v is not None:
                            tmp = np.asarray(v, dtype=float)
                            if tmp.size > 0:
                                arr_xy = tmp
                    except Exception:
                        arr_xy = None
                if arr_xy is None and hasattr(cand, "points_lonlat"):
                    try:
                        v = getattr(cand, "points_lonlat")
                        if v is not None:
                            pts_lonlat = v
                    except Exception:
                        pts_lonlat = None
            if not source_name and cand_name:
                source_name = cand_name
            if arr_xy is not None:
                a = np.asarray(arr_xy, dtype=float)
                if a.ndim == 1:
                    if a.size % 2 == 0:
                        a = a.reshape(-1, 2)
                    else:
                        a = a.reshape(-1, 2)
                if a.ndim == 2 and a.shape[1] >= 2:
                    xs.append(np.asarray(a[:, 0], dtype=float))
                    ys.append(np.asarray(a[:, 1], dtype=float))
                continue
            if pts_lonlat is not None:
                try:
                    seq = list(pts_lonlat)  # may be list of tuples or ndarray
                except Exception:
                    seq = []
                if len(seq) == 0:
                    continue
                arr_ll = np.asarray(seq, dtype=float)
                lons: np.ndarray
                lats: np.ndarray
                if arr_ll.ndim == 2 and arr_ll.shape[1] >= 2:
                    lons = np.asarray(arr_ll[:, 0], dtype=float)
                    lats = np.asarray(arr_ll[:, 1], dtype=float)
                else:
                    # fallback parse tuples
                    lons_list: list[float] = []
                    lats_list: list[float] = []
                    for p in seq:
                        try:
                            lon = float(p[0]); lat = float(p[1])
                            lons_list.append(lon); lats_list.append(lat)
                        except Exception:
                            continue
                    if not lons_list:
                        continue
                    lons = np.array(lons_list, dtype=float)
                    lats = np.array(lats_list, dtype=float)
                from openlapexe.geo_proj import wgs84_to_plane as _wgs84  # type: ignore

                x_arr, y_arr, zone_arr = _wgs84(lats, lons)  # type: ignore[arg-type]
                x_np = np.asarray(x_arr, dtype=float)
                y_np = np.asarray(y_arr, dtype=float)
                xs.append(x_np.reshape(-1))
                ys.append(y_np.reshape(-1))
                if zone_val is None:
                    try:
                        if isinstance(zone_arr, np.ndarray):
                            zone_val = int(zone_arr.flat[0])
                        else:
                            zone_val = int(zone_arr)  # type: ignore[arg-type]
                    except Exception:
                        try:
                            zone_val = int(np.asarray(zone_arr).flat[0])
                        except Exception:
                            zone_val = None
                continue
        if not xs:
            raise ValueError("no valid candidate points found")
        all_x = np.concatenate([np.asarray(a, dtype=float).reshape(-1) for a in xs])
        all_y = np.concatenate([np.asarray(a, dtype=float).reshape(-1) for a in ys])
        n = int(all_x.shape[0])
        if n == 0:
            raise ValueError("no points after concatenation")
        s_arr = np.zeros(n, dtype=float)
        if n > 1:
            dx = np.diff(all_x)
            dy = np.diff(all_y)
            seg = np.hypot(dx, dy)
            s_arr[1:] = np.cumsum(seg)
        length_m = float(s_arr[-1]) if n > 0 else 0.0
        z_arr = np.zeros(n, dtype=float)
        # curvature from XY: use compute_curvature_profile with lazy import + fallback
        try:
            from openlapexe.curvature_opt import compute_curvature_profile as _ccp  # type: ignore

            all_xy = np.column_stack([np.asarray(all_x, dtype=float), np.asarray(all_y, dtype=float)])
            _curv_tmp = np.asarray(_ccp(all_xy, closed=bool(closed_loop)), dtype=float).reshape(-1)
            if _curv_tmp.shape[0] != n:
                raise ValueError("curv shape mismatch")
            _curv_tmp = np.where(np.isfinite(_curv_tmp), _curv_tmp, 0.0)
            _curv_tmp = np.abs(_curv_tmp)
            curv_arr = _curv_tmp.astype(float, copy=False)
        except Exception:
            # fallback triangle curvature loop (closed aware, handles large coords stably)
            curv_arr = np.zeros(n, dtype=float)
            try:
                if n >= 3:
                    # mean subtraction for large plane coords stability
                    _mx = float(np.mean(all_x)) if n else 0.0
                    _my = float(np.mean(all_y)) if n else 0.0
                    _x0 = np.asarray(all_x, dtype=float) - _mx
                    _y0 = np.asarray(all_y, dtype=float) - _my
                    _eps = 1e-12
                    for _i in range(n):
                        if not bool(closed_loop) and (_i == 0 or _i == n - 1):
                            curv_arr[_i] = 0.0
                            continue
                        _im1 = (_i - 1) % n if bool(closed_loop) else _i - 1
                        _ip1 = (_i + 1) % n if bool(closed_loop) else _i + 1
                        _xp = 0.5 * (float(_x0[_ip1]) - float(_x0[_im1]))
                        _yp = 0.5 * (float(_y0[_ip1]) - float(_y0[_im1]))
                        _xpp = float(_x0[_ip1]) - 2.0 * float(_x0[_i]) + float(_x0[_im1])
                        _ypp = float(_y0[_ip1]) - 2.0 * float(_y0[_i]) + float(_y0[_im1])
                        _pn = float(np.hypot(_xp, _yp))
                        _den = _pn**3 + _eps
                        _cross = abs(_xp * _ypp - _yp * _xpp)
                        _k = _cross / _den if _den != 0 else 0.0
                        if not np.isfinite(_k) or _k < 0:
                            _k = 0.0
                        curv_arr[_i] = float(_k)
                    curv_arr[~np.isfinite(curv_arr)] = 0.0
                    curv_arr = np.abs(curv_arr)
            except Exception:
                curv_arr = np.zeros(n, dtype=float)
        bank_arr = np.zeros(n, dtype=float)
        grip_arr = np.ones(n, dtype=float)
        sector_arr = np.ones(n, dtype=float)
        points_arr = np.column_stack([s_arr, all_x, all_y, z_arr, curv_arr, bank_arr, grip_arr, sector_arr])
        tname = source_name if source_name else str(mode)
        created_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        meta: dict[str, Any] = {
            "source": source_name if source_name else str(mode),
            "created": created_iso,
            "creator_mode": str(mode),
            "zone": zone_val,
        }
        obj = cls(name=tname, length_m=length_m, closed_loop=bool(closed_loop), points=points_arr, logged=False, meta=meta)
        obj._rebuild_cache()
        return obj

    def save_json(self, name: str) -> pathlib.Path:
        raw = str(name).strip()
        if not raw:
            raise ValueError("name must be non-empty")
        fname = raw
        if not fname.lower().endswith(".json"):
            fname = fname + ".json"
        base = pathlib.Path(__file__).resolve().parents[2] / "data" / "tracks"
        try:
            from openlapexe.io import _atomic_write_text as _awt  # type: ignore
            from openlapexe.io import resource_path as _rp  # type: ignore

            try:
                rp_base = _rp("data/tracks")
                if rp_base.exists() or str(base) in str(rp_base):
                    base = rp_base
            except Exception:
                pass
        except Exception:
            from openlapexe.io import _atomic_write_text as _awt  # type: ignore

        path = base / fname
        pts_list: list[dict[str, Any]] = []
        if isinstance(self.points, np.ndarray) and self.points.size > 0 and self.points.ndim == 2:
            for i in range(int(self.points.shape[0])):
                row = self.points[i]
                pts_list.append(
                    {
                        "s": float(row[0]),
                        "x": float(row[1]),
                        "y": float(row[2]),
                        "z": float(row[3]),
                        "curv": float(row[4]),
                        "banking_rad": float(row[5]),
                        "grip_factor": float(row[6]),
                        "sector_id": int(float(row[7])) if float(row[7]).is_integer() else float(row[7]),
                    }
                )
        meta_dict: dict[str, Any] = dict(self.meta) if isinstance(self.meta, dict) else {}
        if "source" not in meta_dict:
            meta_dict["source"] = self.name
        if "creator_mode" not in meta_dict:
            meta_dict["creator_mode"] = meta_dict.get("source", self.name)
        if "created" not in meta_dict:
            meta_dict["created"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if "zone" not in meta_dict:
            meta_dict["zone"] = None
        data: dict[str, Any] = {
            "name": self.name,
            "length_m": float(self.length_m),
            "closed_loop": bool(self.closed_loop),
            "logged": bool(self.logged),
            "meta": meta_dict,
            "points": pts_list,
        }
        text = json.dumps(data, ensure_ascii=False, indent=2)
        _awt(path, text, encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # mesh(step) 1..5 resample with separated interpolators
    # ------------------------------------------------------------------
    def mesh(self, step: float = 1.0) -> "Track":
        if not (1.0 <= step <= 5.0):
            raise ValueError(f"mesh step must be 1-5m, got {step}")
        if self._s is None or self._s.size == 0:
            return Track(name=self.name, length_m=self.length_m, closed_loop=self.closed_loop, points=np.zeros((0, 8), dtype=float), logged=self.logged, meta=dict(self.meta) if isinstance(self.meta, dict) else {})
        L = float(self.length_m)
        if L <= 0:
            L = float(np.max(self._s)) if self._s.size else 0.0
        # build uniform s_new including 0 and L (deterministic)
        s_new = np.arange(0.0, L, step, dtype=float)
        if s_new.size == 0 or abs(float(s_new[-1]) - L) > 1e-9:
            s_new = np.append(s_new, L)
        else:
            s_new[-1] = L

        xp = np.asarray(self._s, dtype=float)
        x_a = np.asarray(self._x, dtype=float)
        y_a = np.asarray(self._y, dtype=float)
        z_a = np.asarray(self._z, dtype=float)
        curv_a = np.asarray(self._curv, dtype=float)
        bank_a = np.asarray(self._bank, dtype=float) if self._bank is not None else np.zeros_like(xp)
        grip_a = np.asarray(self._grip, dtype=float) if self._grip is not None else np.ones_like(xp)
        sector_a = np.asarray(self._sector, dtype=float) if self._sector is not None else np.zeros_like(xp)

        # logged handling: s reversal + closed processing
        # For logged track, we mirror the coarse data before interpolation:
        # At s=0 we want original end point, at s=L original start point.
        # Achieved by reversing arrays (and negating curv/bank).
        if self.logged:
            # Reverse arrays but keep xp monotonic 0..L for interpolation domain.
            # The values are reversed: y at s=0 becomes original y at s=L.
            # Sign flip for curv and banking (direction reversal)
            x_a = x_a[::-1].copy()
            y_a = y_a[::-1].copy()
            z_a = z_a[::-1].copy()
            curv_a = (-curv_a[::-1]).copy()
            bank_a = (-bank_a[::-1]).copy()
            grip_a = grip_a[::-1].copy()
            sector_a = sector_a[::-1].copy()
            # xp stays same monotonic; interpolation then yields mirrored track.
            # Also need to handle closed correction after interpolation (see below).

        # PCHIP for curv, elevation (z), banking; np.interp clamp for grip; previous for sector; linear for x,y
        # Prepare pchip interpolated
        # Ensure xp is strictly increasing for pchip; handle duplicates via _pchip_interp internal dedup.
        curv_new = _pchip_interp(xp, curv_a, s_new)
        z_new = _pchip_interp(xp, z_a, s_new)
        bank_new = _pchip_interp(xp, bank_a, s_new)

        # x,y linear (deterministic)
        x_new = np.interp(s_new, xp, x_a, left=float(x_a[0]), right=float(x_a[-1]))
        y_new = np.interp(s_new, xp, y_a, left=float(y_a[0]), right=float(y_a[-1]))

        # grip via np.interp clamp (left/right = edge values)
        if grip_a.size >= 1:
            grip_new = np.interp(s_new, xp, grip_a, left=float(grip_a[0]), right=float(grip_a[-1]))
            # clamp also ensures no extrapolation beyond [min(grip), max(grip)] already via left/right
        else:
            grip_new = np.ones_like(s_new)

        # sector via previous (step) interpolation: for each s_new find previous sector
        if sector_a.size >= 1:
            # Use searchsorted right -1 and clip
            idx = np.searchsorted(xp, s_new, side="right") - 1
            idx = np.clip(idx, 0, sector_a.shape[0] - 1)
            sector_new = sector_a[idx].astype(float)
        else:
            sector_new = np.zeros_like(s_new)

        # closed_loop correction (deterministic linear correction) similar to OpenTRACK
        # Apply after interpolation to ensure first and last point coincide for closed tracks.
        if self.closed_loop:
            # Compute linear correction for X,Y,Z,bank so that start and end close.
            # DX = s/L * (X0 - Xend) etc. Note X0 = x_new[0], Xend = x_new[-1] before correction.
            # After correction, X_new_corrected = X_new + DX. This makes end point coincide with start.
            # For logged case, correction still applies (ensures closure).
            # Only apply if L>0
            if L > 1e-9:
                dx_corr = s_new / L * (float(x_new[0]) - float(x_new[-1]))
                dy_corr = s_new / L * (float(y_new[0]) - float(y_new[-1]))
                dz_corr = s_new / L * (float(z_new[0]) - float(z_new[-1]))
                db_corr = s_new / L * (float(bank_new[0]) - float(bank_new[-1]))
                x_new = x_new + dx_corr
                y_new = y_new + dy_corr
                z_new = z_new + dz_corr
                bank_new = bank_new + db_corr
            # Note: after correction the distance between first and last should be ~0 (deterministic)

        points_new = np.column_stack([s_new, x_new, y_new, z_new, curv_new, bank_new, grip_new, sector_new])
        return Track(name=self.name, length_m=L, closed_loop=self.closed_loop, points=points_new, logged=self.logged, meta=dict(self.meta) if isinstance(self.meta, dict) else {})

    # ------------------------------------------------------------------
    # curvature_at(s), curvature_profile, peaks, apex etc (kept for compatibility)
    # ------------------------------------------------------------------
    def curvature_at(self, s: float) -> float:
        if self._s is None or self._s.size == 0:
            return 0.0
        L = float(self.length_m) if self.length_m else float(np.max(self._s))  # type: ignore
        if L <= 0:
            return 0.0
        if self.closed_loop:
            s_mod = float(s) % L
        else:
            s_mod = float(np.clip(float(s), 0.0, L))
        delta = 1.0
        if L < 2 * delta + 1e-9:
            delta = max(0.1, L / 10.0)
        def _xy_at(ss: float) -> tuple[float, float]:
            if self.closed_loop:
                ss = float(ss) % L
            else:
                ss = float(np.clip(float(ss), 0.0, L))
            xp = np.asarray(self._s, dtype=float)
            x = float(np.interp(ss, xp, np.asarray(self._x, dtype=float)))
            y = float(np.interp(ss, xp, np.asarray(self._y, dtype=float)))
            return x, y
        x1, y1 = _xy_at(s_mod - delta)
        x2, y2 = _xy_at(s_mod)
        x3, y3 = _xy_at(s_mod + delta)
        return _triangle_curvature(x1, y1, x2, y2, x3, y3)

    def curvature_profile(self, step: float = 1.0) -> npt.NDArray[np.float64]:
        L = float(self.length_m) if self.length_m else 0.0
        if L <= 0 or self._s is None or self._s.size == 0:
            return np.array([], dtype=float)
        if step <= 0:
            step = 1.0
        n = int(math.ceil(L / step)) + 1
        s_vals = np.linspace(0.0, L, n, dtype=float)
        curvs = np.array([self.curvature_at(float(ss)) for ss in s_vals], dtype=float)
        return curvs

    def find_peaks(self, curv: npt.NDArray[np.float64] | None = None, threshold: float = 0.0, use_abs: bool = False) -> list[int]:
        if curv is None:
            if self._curv is not None and self._curv.size > 0:
                arr = np.asarray(self._curv, dtype=float)
            else:
                arr = self.curvature_profile(step=1.0)
        else:
            arr = np.asarray(curv, dtype=float)
        return _find_peaks_indices(arr, threshold=threshold, use_abs=use_abs)

    def apex_candidates(self, threshold: float = 1e-6, min_distance_m: float = 10.0, step: float = 1.0, use_abs: bool = True) -> list[float]:
        if self._s is None or self._s.size == 0:
            return []
        L = float(self.length_m) if self.length_m else float(np.max(self._s))  # type: ignore
        if L <= 0:
            return []
        if self._curv is not None and np.any(np.abs(self._curv) > 1e-9):
            arr = np.asarray(self._curv, dtype=float)
            s_arr = np.asarray(self._s, dtype=float)
        else:
            s_arr = np.linspace(0.0, L, int(math.ceil(L / step)) + 1, dtype=float)
            arr = np.array([self.curvature_at(float(ss)) for ss in s_arr], dtype=float)
        if use_abs:
            arr_cmp = np.abs(arr)
        else:
            arr_cmp = arr
        idxs = _find_peaks_indices(arr_cmp, threshold=threshold, use_abs=False)
        if min_distance_m > 0 and len(idxs) > 1:
            order = sorted(idxs, key=lambda i: float(abs(arr[i])), reverse=True)
            kept: list[int] = []
            kept_s: list[float] = []
            for i in order:
                si = float(s_arr[i])
                too_close = False
                for ks in kept_s:
                    d = abs(si - ks)
                    if self.closed_loop:
                        d = min(d, L - d)
                    if d < min_distance_m:
                        too_close = True
                        break
                if not too_close:
                    kept.append(i)
                    kept_s.append(si)
            kept_sorted = sorted(kept, key=lambda i: float(s_arr[i]))
            return [float(s_arr[i]) for i in kept_sorted]
        return [float(s_arr[i]) for i in idxs]

    find_apex_candidates = apex_candidates
    find_apexes = apex_candidates
    get_apexes = apex_candidates
    get_apex_candidates = apex_candidates
    peaks = find_peaks
    find_curvature_peaks = find_peaks

    def __len__(self) -> int:
        if isinstance(self.points, np.ndarray):
            return int(self.points.shape[0])
        try:
            return len(self.points)  # type: ignore
        except Exception:
            return 0

# Alias for EXPECTED OUTCOME: from openlapexe.track import Track2
Track2 = Track
Track2.__name__ = "Track2"

# ---------------------------------------------------------------------------
# Module-level helpers for tests (peak finders)
# ---------------------------------------------------------------------------
def find_peaks(curv: npt.NDArray[np.float64], threshold: float = 0.0, use_abs: bool = False) -> list[int]:
    return _find_peaks_indices(np.asarray(curv, dtype=float), threshold=threshold, use_abs=use_abs)

def find_apex_candidates(curv: npt.NDArray[np.float64], threshold: float = 1e-6) -> list[int]:
    return _find_peaks_indices(np.asarray(curv, dtype=float), threshold=threshold, use_abs=True)

__all__ = ["Track", "Track2", "_pchip_slopes", "_pchip_eval", "_pchip_interp", "pchip_slopes", "pchip_eval", "pchip_interp", "find_peaks", "find_apex_candidates"]
