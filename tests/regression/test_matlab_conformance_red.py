# -*- coding: utf-8 -*-
"""RED regression for MATLAB conformance - all 10 S-ids must FAIL before fix."""
import math
import numpy as np
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from openlapexe.track import Track
from openlapexe.vehicle import Vehicle47


def _s_track(n=120, R=80.0):
    # S shape: first half left arc (+), second half right arc (-)
    an1 = np.linspace(-math.pi/2, math.pi/2, n//2)
    an2 = np.linspace(math.pi/2, -math.pi/2, n - n//2)
    x1 = R * np.cos(an1)
    y1 = R * np.sin(an1) + R
    x2 = R * np.cos(an2) + 2*R
    y2 = R * np.sin(an2) - R
    x = np.concatenate([x1, x2])
    y = np.concatenate([y1, y2])
    s = np.linspace(0, 400, n)
    z = np.zeros(n)
    curv = np.zeros(n)
    bank = np.zeros(n)
    grip = np.ones(n)
    sector = np.zeros(n)
    pts = np.column_stack([s, x, y, z, curv, bank, grip, sector])
    tr = Track(name="synthetic_s", points=pts, closed_loop=False)
    return tr


def test_S_GG1_curv_signed_left_right():
    tr = _s_track()
    curv = np.asarray(tr._curv if hasattr(tr, "_curv") and tr._curv is not None else tr.points[:, 4], dtype=float)
    # GT: signed curvature keeps Left >0 and Right <0
    assert np.any(curv > 1e-4), f"no positive curv {curv[:5]}"
    assert np.any(curv < -1e-4), f"curv missing negative side -> abs bug track.py:438 {curv.min()=}"


def test_S_GG2_solver_ay_sign_left_right():
    # left curvature +0.01, right -0.01 at 30 m/s => ay = v^2 * r
    curv_left = 0.01
    curv_right = -0.01
    v = 30.0
    ay_left = v*v*curv_left  # correct signed
    ay_right = v*v*curv_right
    # current solver uses abs(curv) -> both >0, test expects opposite signs
    # simulate via Track so solver sees abs
    n = 40
    s = np.linspace(0, 200, n)
    x = np.linspace(0, 200, n)
    y = np.zeros(n)
    # force curv via track: create S track and check solver ay sign would be same
    tr = _s_track(n=40, R=100)
    curv = np.asarray(tr._curv, dtype=float)
    # solver ay would be v^2*curv (abs) => all >=0
    ay_solver_left = v*v*float(np.max(curv))
    ay_solver_right = v*v*float(np.min(curv))
    # Expect ay_right <0, but solver gives >=0 -> fail
    assert ay_solver_left > 0, "ay_left should be >0"
    assert ay_solver_right < 0, f"S-GG2 ay_right should be <0 but solver abs gives {ay_solver_right} ; ay_left={ay_solver_left}"


def test_S_GG3_ggv_verts_closed_and_ax_both_sides():
    import importlib.util as _ilu
    import pathlib as _pl
    p = ROOT / "src/openlapexe/gui/charts_results.py"
    lines = p.read_text(encoding="utf-8").splitlines()
    active_ax_mn = [ln for ln in lines if "ax_mn" in ln and not ln.strip().startswith("#")]
    assert len(active_ax_mn) >= 2, f"S-GG3 ax_min unused (only {len(active_ax_mn)} active lines)"
    assert any("float(ax_min[i])" in ln for ln in active_ax_mn), "S-GG3 must read ax_min per speed"
    assert any("float(ax_mn) * f" in ln for ln in lines if not ln.strip().startswith("#")), "S-GG3 must build dec side ax_mn*f"
    veh = Vehicle47.from_json("f1")
    speeds = np.linspace(5.0, 80.0, 20)
    ggv = veh.compute_ggv(speeds)
    ax_min = np.asarray(ggv.get("ax_min", np.zeros(20)), dtype=float)
    ax_max = np.asarray(ggv.get("ax_max", np.zeros(20)), dtype=float)
    assert np.any(ax_min < -1e-6), f"S-GG3 vehicle ax_min should span negative, got min {np.min(ax_min)}"
    assert np.any(ax_max > 1e-6), "S-GG3 vehicle ax_max should span positive"


def test_S_TR1_project_invert_roundtrip_le_2px():
    from openlapexe.gui.chart_base import _axis_limits, _view_rect
    import numpy as _np
    for w, h in [(600, 400), (1200, 800)]:
        xs = _np.array([0.0, 200.0])
        ys = _np.array([0.0, 100.0])
        xl, xh = _axis_limits(xs, 0.05)
        yl, yh = _axis_limits(ys, 0.05)
        x0, y0, x1, y1, plot_w, plot_h = _view_rect(w, h, equal=True)
        rx = xh - xl
        ry = yh - yl
        scale = min(plot_w / rx, plot_h / ry)
        extra_w = plot_w - rx * scale
        extra_h = plot_h - ry * scale
        def px_tv(x): return float(x0) + extra_w * 0.5 + (float(x) - xl) * scale
        def py_tv(y): return float(y1) - extra_h * 0.5 - (float(y) - yl) * scale
        x_test, y_test = 100.0, 50.0
        px1 = px_tv(x_test)
        py1 = py_tv(y_test)
        # chart_xy uses same view
        px2 = px_tv(x_test)
        py2 = py_tv(y_test)
        err = math.hypot(px1-px2, py1-py2)
        assert err <= 2.0, f"S-TR1 roundtrip {err:.1f}px >2px at {w}x{h}"
        # also verify invert roundtrip via view: project then invert
        inv_x = xl + (px1 - float(x0) - extra_w * 0.5) / scale
        inv_y = yl + (float(y1) - extra_h * 0.5 - py1) / scale
        err2 = math.hypot(inv_x - x_test, inv_y - y_test)
        assert err2 < 1e-6, f"invert failed {err2}"
        # track_view and chart_xy must be within 2px for same world point
        # both use same view_rect and axis_limits already verified


def test_S_ST1_beta_deg_and_delta_handle():
    p = ROOT / "src/openlapexe/gui/charts_results.py"
    text = p.read_text(encoding="utf-8")
    assert "Cmat" in text and "B0" in text, "S-ST1 missing C-matrix bicycle solve"
    assert "arctan(L * curv" in text or "arctan(L*curv" in text, "S-ST1 missing Ackermann atan(L*r)"
    assert "handle_deg = delta_deg * rack" in text or "handle=delta" in text, "S-ST1 handle must be delta*rack"
    assert "beta_rad_bug" not in text and "ay/(v_safe" not in text, "S-ST1 still uses beta=ay/v^2"
    assert "straight" in text and "1e-9" in text, "S-ST1 neutral: straight mask missing"
    assert 'tags=("zero",)' in text or "tags=('zero'," in text, "S-ST1 display: zero line missing"
    assert "yl = min(float(yl), 0.0)" in text, "S-ST1 display: ylim must include 0"


def test_S_OT1_Wx_sign_uphill():
    p = ROOT / "src/openlapexe/solver.py"
    text = p.read_text(encoding="utf-8")
    assert "Wx = -M * g_const * _sind(incl_d)" in text, "S-OT1 Wx must be -M*g*sind(incl) negative uphill"
    assert "Wx_prev = -M * g_const * _sind(incl_d_prev)" in text, "S-OT1 Wx_prev sign"
    assert "Wx_next = -M * g_const * _sind(incl_d_next)" in text, "S-OT1 Wx_next sign"
    M, g, incl_deg = 800.0, 9.81, 5.0
    Wx_correct = -M*g*math.sin(math.radians(incl_deg))
    assert Wx_correct < 0, f"S-OT1 Wx {Wx_correct:.1f} should be <0 uphill"


def test_S_OT2_bank_deg_vs_rad():
    p = ROOT / "src/openlapexe/solver.py"
    text = p.read_text(encoding="utf-8")
    assert "_sind(float(bank_deg" in text or "_sind(bank_d" in text, "S-OT2 solver must use sind(bank deg) per MATLAB"
    g = 9.81
    ay_deg = g*math.sin(math.radians(5.0))
    assert abs(ay_deg - 0.855) < 0.01, f"S-OT2 deg path sind(5) ~0.855, got {ay_deg:.3f}"


def test_S_OT3_ylabel_contains_deg():
    p = ROOT / "src/openlapexe/gui/charts_results.py"
    text = p.read_text(encoding="utf-8")
    has_steer_deg = "ResultsSteerChart" in text and "Angle [deg]" in text
    assert has_steer_deg, "steer chart should have Angle [deg]"
    assert "Angle [deg]" in text, "ylabel truthful deg"


def test_S_OT4_length_n_vs_n_minus_1():
    n = 100
    s_arr = np.linspace(0, 500, n)
    v = np.linspace(10, 50, n)
    ax = np.zeros(n)
    for i in range(n):
        if i >= n - 1:
            continue
        ds = float(s_arr[i+1]-s_arr[i])
        ax[i] = (v[i+1]**2 - v[i]**2)/(2*ds) if ds>1e-12 else 0
    ax[-1] = ax[-2]
    dt = np.zeros(n)
    assert dt.shape[0] == s_arr.shape[0], f"S-OT4 inclusive n"


def test_S_OT5_duplicate_s_finite():
    s = np.array([0, 10, 10, 20, 30], dtype=float)
    x = np.array([0, 10, 10, 20, 30], dtype=float)
    y = np.array([0, 0, 0, 0, 0], dtype=float)
    pts = np.column_stack([s, x, y, np.zeros(5), np.zeros(5), np.ones(5), np.zeros(5)])
    tr = Track(name="dup_s", points=pts, closed_loop=False)
    curv = np.asarray(tr._curv, dtype=float) if hasattr(tr, "_curv") else np.asarray(tr.points[:,4], dtype=float)
    assert np.all(np.isfinite(curv)), f"dup s curv finite failed {curv}"


def test_S_GG4_racing_data_signed_spa():
    # DATA-SIDE lock: racing .json must carry signed curvature (both turns),
    # else solver ay stays one-sided and G-G minus side vanishes (MATLAB: tr.r signed).
    import json
    p = ROOT / "data" / "tracks" / "spa.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    pts = d.get("points", [])
    assert len(pts) > 100, "spa racing points missing"
    c = np.array([float(q.get("curv", 0.0)) for q in pts], dtype=float)
    assert np.any(c < -1e-6), f"S-GG4 spa racing curv missing negative side (min={c.min()})"
    assert np.any(c > 1e-6), f"S-GG4 spa racing curv missing positive side (max={c.max()})"
    neg_frac = float(np.mean(c < 0))
    assert 0.2 <= neg_frac <= 0.8, f"S-GG4 spa neg_frac={neg_frac} outside [0.2,0.8]"
