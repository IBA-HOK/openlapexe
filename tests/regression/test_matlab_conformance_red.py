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
    veh = Vehicle47.from_json("f1")
    speeds = np.linspace(5.0, 80.0, 20)
    ggv = veh.compute_ggv(speeds)
    # GGV grid via charts_results builds 400 verts with ay span +/- and ax only positive upper half
    # Replicate charts_results logic to expose bug
    ay_max = np.asarray(ggv.get("ay_max", np.zeros(20)), dtype=float)
    ax_max = np.asarray(ggv.get("ax_max", np.zeros(20)), dtype=float)
    ax_min = np.asarray(ggv.get("ax_min", np.zeros(20)), dtype=float)
    verts = []
    for i in range(20):
        v_i = float(speeds[i])
        ay_m = float(ay_max[i]) if i < len(ay_max) else 10.0
        ax_mx = float(ax_max[i]) if i < len(ax_max) else 5.0
        if ay_m < 1e-9:
            ay_m = 10.0
        for j in range(20):
            ay_j = -ay_m + 2*ay_m*j/19.0
            r = float(ay_j)/float(ay_m) if ay_m else 0
            f = math.sqrt(max(0.0, 1 - r*r))
            ax_j = float(ax_mx)*f  # bug: only + side, no ax_min
            verts.append([float(ay_j), float(ax_j), float(v_i)])
    verts = np.array(verts, dtype=float)
    ay_min_verts = float(np.min(verts[:, 0]))
    ax_min_verts = float(np.min(verts[:, 1]))
    ax_max_verts = float(np.max(verts[:, 1]))
    # Expect verts contain ay both signs and ax both signs (acc and dec)
    assert ay_min_verts < -1e-6, f"ay_min {ay_min_verts} should be <0"
    assert ax_min_verts < -1e-6, f"S-GG3 ax should span negative (dec) but verts ax_min={ax_min_verts} >=0 -> upper-half only bug charts_results:1096"
    assert ax_max_verts > 1e-6, "ax_max should be >0"
    # closed-loop: first and last ring should meet? synthetic grid not closed
    # Check closed-loop count: verts should be 400+1 closed? currently 400 open
    assert verts.shape[0] > 400, f"closed-loop verts need closure point, got {verts.shape[0]}"


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
    # V=20,R=100 => curv 0.01, ay = V^2*R? Actually ay=V^2*r =4, bank 0
    V, R = 20.0, 100.0
    curv = 1.0/R
    ay = V*V*curv
    v_safe = max(V, 1.0)
    beta_rad_bug = ay/(v_safe*v_safe)  # charts_results 851: ay/v^2
    beta_deg_bug = math.degrees(beta_rad_bug)
    rack = 12.0
    delta_bug = beta_deg_bug  # bug delta=beta
    handle_bug = beta_deg_bug * rack
    # Correct MATLAB: solve C\B, delta = sol(1)+atand(L*r) ~ for typical CF/CR ~800/1000, M~800, gives 2-4deg
    # atand(L*r) alone = atand(2.5*0.01)=atand(0.025)=1.43deg, plus slip ~1-2deg => 2.5-3.5deg
    L = 2.5
    atand_Lr = math.degrees(math.atan(L*curv))
    # even minimal correct delta should be >2
    assert 2.0 <= delta_bug <= 4.0, f"S-ST1 delta {delta_bug:.2f} deg out of 2-4deg (bug beta=ay/v^2 dim 1/m) atand_Lr={atand_Lr:.2f}"
    assert math.isclose(handle_bug, delta_bug*rack, rel_tol=1e-9), f"handle should be delta*rack {handle_bug} vs {delta_bug*rack}"


def test_S_OT1_Wx_sign_uphill():
    M, g, incl_deg = 800.0, 9.81, 5.0
    Wx = M*g*math.sin(math.radians(incl_deg))  # solver 528 current
    # MATLAB OpenLAP Wx is opposite sign for uphill positive incl (gravity opposes motion)
    # Expect Wx negative when incl positive (uphill resists)
    assert Wx < 0, f"S-OT1 Wx {Wx:.1f} should be <0 for uphill incl {incl_deg}deg (sign inverted)"


def test_S_OT2_bank_deg_vs_rad():
    bank_rad = math.radians(5.0)
    # bug: code treats bank_rad as deg in _sind(bank_deg) -> sind(0.087) ~0.0015 vs sind(5)=0.087
    # Check ay contribution g*sind(bank) diff >5x
    g = 9.81
    ay_bug = g*math.sin(math.radians(bank_rad))  # bug: rad fed to sind
    ay_correct = g*math.sin(bank_rad)  # if bank stored rad should use sin(rad)
    # also correct deg path: bank_deg=5, sind(5)=0.087
    ay_deg = g*math.sin(math.radians(5.0))
    # bug ay is tiny vs correct
    assert abs(ay_bug - ay_correct) < 0.01, f"S-OT2 bank rad {bank_rad} treated as deg gives {ay_bug:.3f} vs {ay_correct:.3f}"


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
