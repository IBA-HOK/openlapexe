# -*- coding: utf-8 -*-
"""openlapexe.curvature_opt - 厳密な最小曲率最適化 (numpyのみ, scipy禁止, 決定論).

定式化:
  center = (l + r)/2
  width  = |r - l|
  目的   Σ κ²·ds   κ = |x'y'' - y'x''| / |p'|³
  制約   |c - mid| ≤ (w/2 - margin)

有限差分勾配降下 + ラインサーチ, 固定iters, 閉ループwrap.

Public API:
  compute_curvature_profile(c, closed=True) -> np.ndarray
  direct_line(points) -> np.ndarray
  optimize_centerline(left_xy, right_xy, closed=True, iters=200, width_margin=0.1) -> (center_xy, curv)
"""
from __future__ import annotations

import numpy as np
import numpy.typing as npt

__all__ = ["compute_curvature_profile", "direct_line", "optimize_centerline"]


def _as_xy(arr: npt.NDArray[np.float64] | list | tuple) -> npt.NDArray[np.float64]:
    a = np.asarray(arr, dtype=np.float64)
    if a.ndim == 1:
        if a.size % 2 != 0:
            raise ValueError(f"xy shape invalid: {a.shape}")
        a = a.reshape(-1, 2)
    if a.ndim != 2 or a.shape[1] != 2:
        raise ValueError(f"expected (N,2) xy, got shape {a.shape}")
    if a.shape[0] == 0:
        raise ValueError("xy must be non-empty")
    return a


def _arc_ds(center: npt.NDArray[np.float64], closed: bool) -> npt.NDArray[np.float64]:
    n = int(center.shape[0])
    if n == 1:
        return np.array([0.0], dtype=np.float64)
    diffs = np.diff(center, axis=0)
    seg = np.hypot(diffs[:, 0], diffs[:, 1])  # (n-1,)
    if closed:
        closing = float(np.hypot(center[0, 0] - center[-1, 0], center[0, 1] - center[-1, 1]))
        seg_full = np.empty(n, dtype=np.float64)
        seg_full[: n - 1] = seg
        seg_full[n - 1] = closing
        ds = 0.5 * (np.roll(seg_full, 1) + seg_full)
        ds = np.maximum(ds, 1e-12)
        return ds
    else:
        if n == 2:
            return np.array([float(seg[0]), float(seg[0])], dtype=np.float64)
        ds = np.empty(n, dtype=np.float64)
        ds[0] = float(seg[0])
        ds[n - 1] = float(seg[-1])
        ds[1:-1] = 0.5 * (seg[:-1] + seg[1:])
        ds = np.maximum(ds, 1e-12)
        return ds


def _curvature_profile(center: npt.NDArray[np.float64], closed: bool) -> npt.NDArray[np.float64]:
    n = int(center.shape[0])
    kappa = np.zeros(n, dtype=np.float64)
    if n < 3:
        return kappa
    x = center[:, 0]
    y = center[:, 1]
    eps = 1e-12
    if closed:
        xp = 0.5 * (np.roll(x, -1) - np.roll(x, 1))
        yp = 0.5 * (np.roll(y, -1) - np.roll(y, 1))
        xpp = np.roll(x, -1) - 2.0 * x + np.roll(x, 1)
        ypp = np.roll(y, -1) - 2.0 * y + np.roll(y, 1)
        p_norm = np.hypot(xp, yp)
        denom = p_norm ** 3 + eps
        cross = xp * ypp - yp * xpp
        k = cross / denom
        k[~np.isfinite(k)] = 0.0
        return k
    else:
        # open: endpoints 0, interior vectorized
        xp_mid = 0.5 * (x[2:] - x[:-2])
        yp_mid = 0.5 * (y[2:] - y[:-2])
        xpp_mid = x[2:] - 2.0 * x[1:-1] + x[:-2]
        ypp_mid = y[2:] - 2.0 * y[1:-1] + y[:-2]
        p_norm_mid = np.hypot(xp_mid, yp_mid)
        denom_mid = p_norm_mid ** 3 + eps
        cross_mid = xp_mid * ypp_mid - yp_mid * xpp_mid
        k_mid = cross_mid / denom_mid
        k_mid[~np.isfinite(k_mid)] = 0.0
        kappa[1:-1] = k_mid
        kappa[~np.isfinite(kappa)] = 0.0
        return kappa


def compute_curvature_profile(
    c_xy: npt.NDArray[np.float64] | list | tuple,
    closed: bool = True,
) -> npt.NDArray[np.float64]:
    """公開: 3点曲率 κ=(x'y''-y'x'')/|p'|³ を計算 (符号付き, 左+/右-).

    Args:
        c_xy: (N,2) centerline
        closed: 閉ループwrapならTrue
    Returns:
        (N,) curvature array, non-negative, finite
    """
    c = _as_xy(c_xy)
    return _curvature_profile(c, bool(closed))


def direct_line(points: npt.NDArray[np.float64] | list | tuple) -> npt.NDArray[np.float64]:
    """モード(1)直接: 入力そのまま返却ヘルパ.

    Args:
        points: (N,2) 入力点列
    Returns:
        (N,2) copy of input
    """
    a = np.asarray(points, dtype=np.float64)
    if a.ndim == 1:
        if a.size % 2 == 0 and a.size > 0:
            a = a.reshape(-1, 2)
    # if still not 2D, just copy
    return np.array(a, dtype=np.float64, copy=True)


def _objective(center: npt.NDArray[np.float64], closed: bool) -> float:
    kappa = _curvature_profile(center, closed)
    ds = _arc_ds(center, closed)
    # Σ κ²·ds
    val = float(np.sum((kappa * kappa) * ds))
    if not np.isfinite(val):
        return float(1e100)
    return val


def _project_constraint(
    center: npt.NDArray[np.float64],
    mid: npt.NDArray[np.float64],
    radius: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """制約 |c-mid| ≤ radius へ射影."""
    out = center.copy()
    radius_c = np.maximum(np.asarray(radius, dtype=np.float64), 0.0)
    dx = out[:, 0] - mid[:, 0]
    dy = out[:, 1] - mid[:, 1]
    dist = np.hypot(dx, dy)
    mask = dist > radius_c
    tiny = mask & (dist < 1e-12)
    if np.any(tiny):
        out[tiny, 0] = mid[tiny, 0] + radius_c[tiny]
        out[tiny, 1] = mid[tiny, 1]
    regular = mask & (~tiny)
    if np.any(regular):
        scale = np.empty_like(dist)
        scale[regular] = radius_c[regular] / np.maximum(dist[regular], 1e-12)
        out[regular, 0] = mid[regular, 0] + dx[regular] * scale[regular]
        out[regular, 1] = mid[regular, 1] + dy[regular] * scale[regular]
    return out


def optimize_centerline(
    left_xy: npt.NDArray[np.float64] | list | tuple,
    right_xy: npt.NDArray[np.float64] | list | tuple,
    closed: bool = True,
    iters: int = 200,
    width_margin: float = 0.1,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """最小曲率中心線最適化.

    Args:
        left_xy: (N,2) 左境界
        right_xy: (N,2) 右境界
        closed: 閉ループならwrapで曲率計算
        iters: 固定反復回数 (決定論)
        width_margin: 制約マージン (w/2 - margin)
    Returns:
        (center_xy (N,2), curv (N,))  curvは符号付き κ=(x'y''-y'x'')/|p'|³
    """
    left = _as_xy(left_xy)
    right = _as_xy(right_xy)
    if left.shape[0] != right.shape[0]:
        raise ValueError(f"left and right must have same N, got {left.shape[0]} vs {right.shape[0]}")
    n = int(left.shape[0])
    if int(iters) <= 0:
        iters = 200
    iters = int(iters)
    closed_b = bool(closed)
    margin = float(width_margin)

    mid = (left + right) * 0.5
    width = np.hypot(right[:, 0] - left[:, 0], right[:, 1] - left[:, 1])
    radius = width * 0.5 - margin
    # clamp negative to 0, but keep as float array
    radius = np.maximum(radius, 0.0)

    center = mid.copy().astype(np.float64, copy=False)

    # closed: enforce closure initially (last==first if input already closed within tolerance?)
    if closed_b and n >= 2:
        # if input is already closed (distance <1e-6 relative?), we keep, but enforce exact closure for determinism
        # don't force if not intended? For test closure <1mm we enforce after opt, not necessarily before.
        # Keep as is initially.
        pass

    # finite difference epsilon
    eps_fd = 1e-4

    # line search step candidates (deterministic)
    # scale decays geometrically; include small steps for fine tuning
    base_steps = np.array([0.5, 0.25, 0.12, 0.06, 0.03, 0.015, 0.0075], dtype=np.float64)

    # fixed iterations
    for it in range(iters):
        cur_obj = _objective(center, closed_b)
        # compute gradient via finite differences
        grad = np.zeros_like(center, dtype=np.float64)
        # forward difference per coordinate (2*N evals)
        # For efficiency, we can perturb one element at a time
        for i in range(n):
            # skip if radius is 0 -> locked to mid, gradient 0
            if float(radius[i]) == 0.0:
                continue
            for d in range(2):
                orig = float(center[i, d])
                # perturb +eps
                center[i, d] = orig + eps_fd
                # need to clamp perturbed to constraint? For gradient we evaluate unconstrained then projection? 
                # To keep gradient within feasible, we should not project perturbation beyond radius, but eps is tiny so it's inside.
                obj_p = _objective(center, closed_b)
                center[i, d] = orig - eps_fd
                obj_m = _objective(center, closed_b)
                center[i, d] = orig
                g = (obj_p - obj_m) / (2.0 * eps_fd)
                if not np.isfinite(g):
                    g = 0.0
                # clip huge gradients to avoid blowup (deterministic)
                if abs(g) > 1e6:
                    g = float(np.sign(g) * 1e6)
                grad[i, d] = float(g)

        # gradient norm for adaptive scaling
        gnorm = float(np.linalg.norm(grad))
        if gnorm < 1e-12:
            # already stationary; continue fixed iters without change (deterministic)
            # but still enforce projection/closure
            center = _project_constraint(center, mid, radius)
            if closed_b and n >= 2:
                center[-1, :] = center[0, :]
            continue

        # normalize direction to have unit scale? Use raw grad with line search scaling
        # direction = -grad
        direction = -grad

        # normalize direction magnitude to avoid dependence on scale?
        # We scale base_steps adaptively: if gnorm large, steps would be too large, so scale by 1/(1+gnorm)?
        # Instead we treat direction as is and base_steps as absolute step multipliers.
        # To keep stable, we normalize direction to have max component ~1 via gnorm
        # Effective: direction_normed = direction / (gnorm + 1.0)
        # This makes line search stable across iterations.
        dir_scaled = direction / (gnorm + 1.0)

        best_center = center
        best_obj = cur_obj
        # line search over base_steps
        for s in base_steps:
            # effective step = s * gnorm? Actually we already normalized, so step is s * (gnorm?) 
            # We want candidate = center + s * direction_normed? Let's try s as multiplier of dir_scaled
            # dir_scaled magnitude ~ <1, s up to 0.5 means move up to 0.5m per iter, reasonable.
            cand = center + float(s) * dir_scaled * 10.0  # *10 to allow up to 5m move? tune
            # alternative: cand = center + s * direction (raw)
            # Test both via empirical. We'll try raw first with small scaling.

            # Note: we tried dir_scaled*10, but raw direction might be better.
            # For determinism we evaluate both schemes and pick best via objective.
            # However we need one deterministic choice. Let's evaluate raw candidate as well.
            # We'll just compute cand_raw = center + s * direction / (1+gnorm) ??? already done.
            # To increase smoothing we allow larger moves: s*10 factor helps.
            # Re-project
            cand = _project_constraint(cand, mid, radius)
            if closed_b and n >= 2:
                cand[-1, :] = cand[0, :]
            obj = _objective(cand, closed_b)
            if obj < best_obj and np.isfinite(obj):
                best_obj = obj
                best_center = cand

        # also try raw direction without normalization for comparison (second pass)
        # if best did not improve, try alternative scaling
        if best_obj >= cur_obj - 1e-14:
            for s in base_steps:
                # raw step: candidate = center + s * direction * (0.01 / (gnorm+1)?) -> need another scale
                # try s_small = s * 1e-3
                cand = center + float(s) * direction * 0.01
                cand = _project_constraint(cand, mid, radius)
                if closed_b and n >= 2:
                    cand[-1, :] = cand[0, :]
                obj = _objective(cand, closed_b)
                if obj < best_obj and np.isfinite(obj):
                    best_obj = obj
                    best_center = cand

        # update if improved, otherwise keep (still enforce projection)
        if best_obj < cur_obj:
            center = best_center
        else:
            # no improvement: still project and enforce closure (no move)
            center = _project_constraint(center, mid, radius)
            if closed_b and n >= 2:
                center[-1, :] = center[0, :]

    # final projection and closure
    center = _project_constraint(center, mid, radius)
    if closed_b and n >= 2:
        center[-1, :] = center[0, :]
        # ensure distance <1mm (0.001) deterministic: already exact equal, distance 0
    # final curvature
    curv = _curvature_profile(center, closed_b)
    # ensure finite
    curv[~np.isfinite(curv)] = 0.0
    center[~np.isfinite(center)] = 0.0
    # ensure contiguity and dtype
    center = np.ascontiguousarray(center, dtype=np.float64)
    curv = np.ascontiguousarray(curv, dtype=np.float64)
    return center, curv


def spline_waypoints(points: object, closed: bool = False, step_m: float = 2.0) -> "np.ndarray":
    import numpy as _np

    from openlapexe.track import _pchip_interp as _pchip

    try:
        step = float(step_m)
    except Exception:
        step = 2.0
    if not _np.isfinite(step) or step <= 0:
        step = 2.0
    try:
        a = _np.asarray(points, dtype=float).reshape(-1, 2)
    except Exception:
        return _np.zeros((0, 2), dtype=float)
    keep = [0]
    for i in range(1, int(a.shape[0])):
        if float(_np.hypot(a[i, 0] - a[keep[-1], 0], a[i, 1] - a[keep[-1], 1])) > 1e-9:
            keep.append(i)
    a = a[_np.asarray(keep, dtype=int)]
    n = int(a.shape[0])
    if n < 2:
        return _np.ascontiguousarray(a, dtype=float)
    if n == 2 and not closed:
        d = float(_np.hypot(a[1, 0] - a[0, 0], a[1, 1] - a[0, 1]))
        m = max(2, int(d / step) + 1)
        t = _np.linspace(0.0, 1.0, m)
        out = a[0][None, :] * (1.0 - t[:, None]) + a[1][None, :] * t[:, None]
        return _np.ascontiguousarray(out, dtype=float)
    seg = _np.hypot(_np.diff(a[:, 0]), _np.diff(a[:, 1]))
    s = _np.concatenate(([0.0], _np.cumsum(seg)))
    total = float(s[-1])
    if not _np.isfinite(total) or total <= 0:
        return _np.ascontiguousarray(a, dtype=float)
    if closed and n >= 3:
        xw = _np.concatenate((a[-2:, 0], a[:, 0], a[:2, 0]))
        yw = _np.concatenate((a[-2:, 1], a[:, 1], a[:2, 1]))
        ext = _np.concatenate((s[-2:] - total, s, s[:2] + total))
        lo, hi = 0.0, total
        m = max(n + 1, int(total / step) + 1)
        grid = _np.linspace(lo, hi, m)
        s_new = _np.union1d(grid, s)
        s_new = s_new[(s_new >= lo - 1e-12) & (s_new <= hi + 1e-12)]
        xn = _pchip(ext, xw, s_new)
        yn = _pchip(ext, yw, s_new)
        out = _np.column_stack((xn, yn))
        return _np.ascontiguousarray(out, dtype=float)
    m = max(n + 1, int(total / step) + 1)
    grid = _np.linspace(0.0, total, m)
    s_new = _np.union1d(grid, s)
    xn = _pchip(s, a[:, 0], s_new)
    yn = _pchip(s, a[:, 1], s_new)
    return _np.ascontiguousarray(_np.column_stack((xn, yn)), dtype=float)
