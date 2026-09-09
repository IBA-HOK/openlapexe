# -*- coding: utf-8 -*-
"""openlapexe.io - helpers duplicated from app.py (scaffold phase).

TODO: app.py will import from here; this module is the canonical source after V2.

Provides:
- resource_path / get_config_path / _atomic_write_text (utf-8, atomic tmp->replace)
- validate_vehicle_dict / validate_track_dict (ValueError on missing key)
- assert_deterministic(fn, n=2, atol=1e-9)
- interp_clamp (np.interp wrapper with clamp)
"""
from __future__ import annotations

import math
import os
import pathlib
import sys
from typing import Any, Callable

import numpy as np

__all__ = [
    "resource_path",
    "get_config_path",
    "_atomic_write_text",
    "validate_vehicle_dict",
    "validate_track_dict",
    "assert_deterministic",
    "interp_clamp",
]


def resource_path(relative: str) -> pathlib.Path:
    """Return absolute path for bundled resource (PyInstaller + dev)."""
    if hasattr(sys, "_MEIPASS"):
        base = pathlib.Path(str(sys._MEIPASS))  # type: ignore[attr-defined]
        return base / relative
    # dev: locate project root by walking up from this file
    # src/openlapexe/io.py -> parents[2] == project root
    p = pathlib.Path(__file__).resolve()
    candidates: list[pathlib.Path] = []
    if len(p.parents) > 2:
        candidates.append(p.parents[2])
    candidates.append(p.parent.parent.parent)
    candidates.append(p.parent.parent)
    for base in candidates:
        try:
            if (base / "app.py").exists() or (base / "data").exists():
                return base / relative
        except Exception:
            continue
    # fallback: expected project root
    base = p.parent.parent.parent
    return base / relative


def get_config_path() -> pathlib.Path:
    """Return user config file path (platform aware)."""
    if sys.platform == "win32":
        base = pathlib.Path.home() / "AppData" / "Roaming" / "OpenLAPexe"
    elif sys.platform == "darwin":
        base = pathlib.Path.home() / "Library" / "Application Support" / "OpenLAPexe"
    else:
        xdg = pathlib.Path.home() / ".config" / "openlapexe"
        env = os.environ.get("XDG_CONFIG_HOME")
        if env:
            base = pathlib.Path(env) / "openlapexe"
        else:
            base = xdg
    return base / "config.json"


def _atomic_write_text(path: pathlib.Path, text: str, encoding: str = "utf-8") -> None:
    """Atomic save: tmp -> replace (encoding utf-8 fixed)."""
    # encoding fixed to utf-8 regardless of caller value (spec: encoding=utf-8固定)
    _ = encoding  # keep signature compat but enforce utf-8
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# JSON schema validators
# ---------------------------------------------------------------------------
_VEHICLE_REQUIRED_KEYS: tuple[str, ...] = (
    "mass_kg",
    "weight_dist_front",
    "wheelbase_m",
    "cog_height_m",
    "cda",
    "cl",
    "tire_mu_x",
    "tire_mu_y",
    "engine_power_factor",
    "final_drive",
)


def validate_vehicle_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Validate vehicle dict. Raises ValueError on missing required key."""
    if not isinstance(data, dict):
        raise ValueError("vehicle data must be dict")
    for k in _VEHICLE_REQUIRED_KEYS:
        if k not in data:
            raise ValueError(f"missing vehicle key: {k}")
        v = data[k]
        if not isinstance(v, (int, float)):
            raise ValueError(f"vehicle key {k} must be numeric, got {type(v).__name__}")
        # also check finite
        try:
            fv = float(v)
            if not math.isfinite(fv):
                raise ValueError(f"vehicle key {k} must be finite, got {v!r}")
        except (TypeError, ValueError):
            raise ValueError(f"vehicle key {k} must be finite numeric, got {v!r}")
    # torque_curve variants
    tc: Any = data.get("torque_curve")
    if tc is None:
        tc = data.get("torque")
    if tc is None:
        tc = data.get("torque_nm")
    if tc is None:
        raise ValueError("missing vehicle key: torque_curve")
    if not isinstance(tc, list) or len(tc) == 0:
        raise ValueError("torque_curve must be non-empty list")
    # validate each point minimally (optional, not required for missing-key test)
    for idx, pt in enumerate(tc):
        if isinstance(pt, dict):
            rpm = pt.get("rpm", pt.get("x"))
            tq = pt.get("torque_nm", pt.get("torque", pt.get("y")))
            if rpm is None or tq is None:
                raise ValueError(f"torque point {idx} missing rpm/torque")
        elif isinstance(pt, (list, tuple)):
            if len(pt) < 2:
                raise ValueError(f"torque point {idx} must have 2 values")
        else:
            raise ValueError(f"torque point {idx} invalid type {type(pt).__name__}")
    return data


def validate_track_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Validate track dict. Raises ValueError on missing required key."""
    if not isinstance(data, dict):
        raise ValueError("track data must be dict")
    if "points" not in data:
        raise ValueError("missing track key: points")
    pts = data["points"]
    if not isinstance(pts, list):
        raise ValueError("track points must be list")
    # length: allow length_m / length / L
    if not any(k in data for k in ("length_m", "length", "L")):
        raise ValueError("missing track key: length_m")
    # closed_loop: allow closed_loop / closed
    if not any(k in data for k in ("closed_loop", "closed")):
        raise ValueError("missing track key: closed_loop")
    # meta is allowed (optional); if present validate type
    if "meta" in data:
        mv = data["meta"]
        if not isinstance(mv, dict):
            raise ValueError("track meta must be dict")
        # allowed keys: source, created, creator_mode, zone (and extra tolerated)
        for mk in ("source", "created", "creator_mode", "zone"):
            if mk in mv:
                # type leniency: source/created/creator_mode should be str or int for zone
                if mk == "zone":
                    if mv[mk] is not None and not isinstance(mv[mk], (int, float)):
                        raise ValueError(f"track meta key {mk} must be numeric or null")
                else:
                    if not isinstance(mv[mk], str):
                        raise ValueError(f"track meta key {mk} must be str")
    # optional: validate points not empty for extra safety
    # but empty list is allowed as present key (not missing)
    # check finite for sampled points (defensive)
    for idx, pt in enumerate(pts[: min(5, len(pts))]):
        if not isinstance(pt, dict):
            continue
        for kk in ("s", "x", "y", "z", "curv"):
            if kk in pt:
                vv = pt[kk]
                if not isinstance(vv, (int, float)):
                    raise ValueError(f"track point {idx} key {kk} must be numeric")
                if isinstance(vv, float) and not math.isfinite(vv):
                    raise ValueError(f"track point {idx} key {kk} must be finite")
    return data


# ---------------------------------------------------------------------------
# Deterministic helper
# ---------------------------------------------------------------------------
def assert_deterministic(fn: Callable[[], Any], n: int = 2, atol: float = 1e-9) -> None:
    """Call fn n times and assert results are equal within atol. Raises AssertionError otherwise."""
    if n < 2:
        raise ValueError("n must be >=2")
    results: list[Any] = [fn() for _ in range(n)]
    first = results[0]
    for idx, other in enumerate(results[1:], start=1):
        # dict handling
        if isinstance(first, dict) and isinstance(other, dict):
            if set(first.keys()) != set(other.keys()):
                raise AssertionError(f"deterministic check failed at call {idx}: dict keys differ {set(first.keys())} vs {set(other.keys())}")
            for k in first:
                v1 = first[k]
                v2 = other[k]
                # numpy arrays or sequences
                try:
                    a1 = np.asarray(v1)
                    a2 = np.asarray(v2)
                    # if both scalar-ish and convertible, use allclose
                    if a1.shape != () or a2.shape != () or a1.dtype.kind in "fc" or a2.dtype.kind in "fc":
                        # if either is array-like with size >0 or float
                        if a1.shape == a2.shape and a1.size > 0:
                            if not np.allclose(a1, a2, atol=atol, rtol=0, equal_nan=False):
                                raise AssertionError(f"deterministic check failed at call {idx} key {k}")
                            continue
                        if a1.size == 0 and a2.size == 0:
                            continue
                except Exception:
                    pass
                # scalar float comparison
                if isinstance(v1, float) or isinstance(v2, float):
                    try:
                        if abs(float(v1) - float(v2)) > atol:
                            raise AssertionError(f"deterministic check failed at call {idx} key {k}: {v1!r} vs {v2!r} diff {abs(float(v1)-float(v2))} > atol {atol}")
                    except (TypeError, ValueError):
                        if v1 != v2:
                            raise AssertionError(f"deterministic check failed at call {idx} key {k}: {v1!r} != {v2!r}")
                else:
                    # try numpy for numeric types
                    try:
                        if isinstance(v1, (int, float, np.number)) and isinstance(v2, (int, float, np.number)):
                            if abs(float(v1) - float(v2)) > atol:
                                raise AssertionError(f"deterministic check failed at call {idx} key {k}: {v1!r} vs {v2!r}")
                        elif v1 != v2:
                            raise AssertionError(f"deterministic check failed at call {idx} key {k}: {v1!r} != {v2!r}")
                    except AssertionError:
                        raise
                    except Exception:
                        if v1 != v2:
                            raise AssertionError(f"deterministic check failed at call {idx} key {k}: {v1!r} != {v2!r}")
            continue
        # numpy arrays or array-like
        a1 = None
        a2 = None
        try:
            a1 = np.asarray(first)
            a2 = np.asarray(other)
            # if both are arrays with same shape, use allclose
            if a1.shape != () or a2.shape != () or a1.dtype.kind in "fcOU" or a2.dtype.kind in "fcOU":
                if a1.shape == a2.shape:
                    # numeric arrays: use allclose, non-numeric fallback to equal
                    if a1.dtype.kind in "iufc" and a2.dtype.kind in "iufc":
                        if not np.allclose(a1, a2, atol=atol, rtol=0, equal_nan=False):
                            raise AssertionError(f"deterministic check failed at call {idx}")
                        continue
                    else:
                        if not np.array_equal(a1, a2):
                            raise AssertionError(f"deterministic check failed at call {idx}")
                        continue
                # shape mismatch -> definitely not deterministic
                raise AssertionError(f"deterministic check failed at call {idx}: shape {a1.shape} vs {a2.shape}")
        except AssertionError:
            raise
        except Exception:
            pass
        # scalar numeric
        try:
            f1 = float(first)  # type: ignore[arg-type]
            f2 = float(other)  # type: ignore[arg-type]
            # check if both were numeric
            if isinstance(first, (int, float, np.number)) and isinstance(other, (int, float, np.number)):
                if abs(f1 - f2) > atol:
                    raise AssertionError(f"deterministic check failed at call {idx}: {first!r} vs {other!r} diff {abs(f1-f2)} > atol {atol}")
                continue
        except (TypeError, ValueError):
            pass
        # generic equality
        if first != other:
            raise AssertionError(f"deterministic check failed at call {idx}: {first!r} != {other!r}")


# ---------------------------------------------------------------------------
# np.interp wrapper with clamp
# ---------------------------------------------------------------------------
def interp_clamp(
    x: Any,
    xp: Any,
    fp: Any,
    left: Any | None = None,
    right: Any | None = None,
) -> Any:
    """np.interp wrapper that clamps out-of-bounds to edge values (left=fp[0], right=fp[-1])."""
    xp_arr = np.asarray(xp, dtype=float)
    fp_arr = np.asarray(fp, dtype=float)
    x_arr = np.asarray(x, dtype=float)
    if xp_arr.size == 0 or fp_arr.size == 0:
        raise ValueError("xp and fp must be non-empty")
    if left is None:
        left = float(fp_arr[0])
    if right is None:
        right = float(fp_arr[-1])
    return np.interp(x_arr, xp_arr, fp_arr, left=left, right=right)
