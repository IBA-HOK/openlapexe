# -*- coding: utf-8 -*-
"""Schema validation for vehicle/track presets (TDD RED)."""
from __future__ import annotations

import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
VEHICLES = ROOT / "data" / "vehicles"
TRACKS = ROOT / "data" / "tracks"

MVP_KEYS = [
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
]


def _load_json(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def test_vehicles_exist():
    assert (VEHICLES / "f1.json").exists(), "data/vehicles/f1.json missing"
    assert (VEHICLES / "gt.json").exists(), "data/vehicles/gt.json missing"


def test_vehicle_f1_mvp_and_torque():
    data = _load_json(VEHICLES / "f1.json")
    for k in MVP_KEYS:
        assert k in data, f"f1.json missing MVP key: {k}"
        assert isinstance(data[k], (int, float)), f"{k} must be number"
    # plausible ranges
    assert 500 <= data["mass_kg"] <= 800
    assert 0.3 <= data["weight_dist_front"] <= 0.6
    assert 1.5 <= data["wheelbase_m"] <= 4.0
    assert 0.15 <= data["cog_height_m"] <= 0.6
    assert 0.3 <= data["cda"] <= 2.5
    assert -6.0 <= data["cl"] <= 0.0
    assert 1.0 <= data["tire_mu_x"] <= 2.5
    assert 1.0 <= data["tire_mu_y"] <= 2.5
    assert 0.5 <= data["engine_power_factor"] <= 2.0
    assert 1 <= data["final_drive"] <= 12
    # torque curve 8-18 points (MVP 8-12, full 18)
    tc = data.get("torque_curve") or data.get("torque") or data.get("torque_nm")
    assert tc is not None, "torque_curve missing"
    assert isinstance(tc, list) and 8 <= len(tc) <= 18, f"torque points {len(tc)} not in 8-18"
    for pt in tc:
        # allow [rpm, nm] or {rpm, torque_nm}
        if isinstance(pt, dict):
            rpm = pt.get("rpm", pt.get("x"))
            tq = pt.get("torque_nm", pt.get("torque", pt.get("y")))
        else:
            rpm, tq = pt
        assert 500 <= rpm <= 20000
        assert 50 <= tq <= 600


def test_vehicle_gt_mvp_and_torque():
    data = _load_json(VEHICLES / "gt.json")
    for k in MVP_KEYS:
        assert k in data, f"gt.json missing MVP key: {k}"
    tc = data.get("torque_curve") or data.get("torque") or data.get("torque_nm")
    assert isinstance(tc, list) and 8 <= len(tc) <= 18
    # GT must differ from F1 (not identical mass)
    f1 = _load_json(VEHICLES / "f1.json")
    assert data["mass_kg"] != f1["mass_kg"]
    assert data["cda"] != f1["cda"]


def test_tracks_exist():
    # spa.json required +2 more
    assert (TRACKS / "spa.json").exists(), "data/tracks/spa.json missing"
    files = list(TRACKS.glob("*.json"))
    assert len(files) >= 3, f"expected >=3 track json, got {len(files)}: {files}"


def test_spa_length_and_closed_loop():
    data = _load_json(TRACKS / "spa.json")
    assert data.get("closed_loop") is True
    length = data.get("length_m") or data.get("length") or data.get("L")
    assert length is not None, "spa length_m missing"
    # 7004m ±1% => 6933.96 .. 7074.04
    assert 6933 <= length <= 7075, f"spa length {length} not in 7004±1%"
    # also check points
    pts = data.get("points")
    assert isinstance(pts, list) and len(pts) > 100
    # mesh 1-5m: spacing approx length/len
    avg_spacing = length / len(pts)
    assert 0.9 <= avg_spacing <= 5.5, f"avg mesh {avg_spacing:.2f} not 1-5m"
    # each point has s,x,y,z,curv
    for p in pts[:: max(1, len(pts)//10)]:
        for k in ("s", "x", "y", "z", "curv"):
            assert k in p, f"point missing {k}: {p}"
    # s monotonic
    s_vals = [p["s"] for p in pts]
    assert s_vals[0] == 0 or abs(s_vals[0]) < 1e-6
    for a, b in zip(s_vals, s_vals[1:]):
        assert b > a
    assert abs(s_vals[-1] - length) < 5.0 or abs(s_vals[-1] - length) < length*0.01
    # closed loop: first and last xy close (within ~5m after correction)
    dx = pts[0]["x"] - pts[-1]["x"]
    dy = pts[0]["y"] - pts[-1]["y"]
    dist = math.hypot(dx, dy)
    assert dist < 2.0, f"closed_loop not closed: dist {dist:.3f}m"


def test_all_tracks_schema():
    for p in TRACKS.glob("*.json"):
        data = _load_json(p)
        assert "points" in data
        assert "closed_loop" in data
        pts = data["points"]
        assert len(pts) >= 200, f"{p.name} too few points"
        # no NaN / inf
        for pt in pts[:: max(1, len(pts)//20)]:
            for k in ("x", "y", "z", "curv", "s"):
                v = pt[k]
                assert isinstance(v, (int, float))
                assert math.isfinite(v), f"{p.name} point has non-finite {k}={v}"


def test_data_readme_has_sha():
    readme = ROOT / "data" / "README.md"
    assert readme.exists(), "data/README.md missing"
    txt = readme.read_text(encoding="utf-8")
    assert "882116a" in txt, "SHA 882116a not in data/README.md"
    assert "OpenLAP" in txt

def test_encoding_and_json_valid():
    for p in list(VEHICLES.glob("*.json")) + list(TRACKS.glob("*.json")):
        txt = p.read_text(encoding="utf-8")
        # ensure ensure_ascii=False was used if non-ascii present? just check valid json
        data = json.loads(txt)
        assert data is not None
