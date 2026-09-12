# -*- coding: utf-8 -*-
"""GT500 Suzuka vehicle regression."""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
VEH = ROOT / "data" / "vehicles" / "gt500_suzuka.json"
BOP_MD = ROOT / "data" / "reference" / "gt500_suzuka_bop_calc.md"
GT = ROOT / "data" / "vehicles" / "gt.json"


def _load(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def test_file_exists():
    assert VEH.exists(), "gt500_suzuka.json missing"
    assert BOP_MD.exists(), "gt500_suzuka_bop_calc.md missing"
    assert GT.exists()


def test_mass_fallback_1100():
    d = _load(VEH)
    assert d["M"] == 1100
    assert d["mass_kg"] == 1100
    prov = d["provenance"]
    assert prov["M_final_kg"] == 1100
    assert prov["base_mass_kg"] == 1245
    assert prov["BoP_kg"] == 0
    assert prov["SW_kg"] == 0
    assert prov["mass_kg_arithmetic"] == "1245+0+0=1245 -> fallback 1100"
    assert "1245" in prov["M_calculation"]
    assert prov["provenance_type"] == "fallback estimate"


def test_bop_md_contains_arithmetic():
    txt = BOP_MD.read_text(encoding="utf-8")
    assert "1245 + 0 + 0 = 1245" in txt or "1245+0+0" in txt
    assert "1100" in txt
    assert "fallback" in txt.lower()


def test_q2_times_recorded():
    d = _load(VEH)
    prov = d["provenance"]
    assert "1'43.143" in prov["Q2_2024_best"] or "1'43.143" in str(prov)
    assert "1'45.377" in prov["Q2_2025_best"] or "1'45.377" in str(prov)
    assert prov["Q2_2024_best"]
    assert prov["Q2_2025_best"]


def test_torque_scale_preserved():
    gt = _load(GT)
    d = _load(VEH)
    # rpm unchanged, torque scaled about 1.08
    gt_tc = gt["torque_curve"]
    tc = d["torque_curve"]
    assert len(tc) == len(gt_tc)
    for a, b in zip(gt_tc, tc):
        assert a["rpm"] == b["rpm"]
    # check peak scale
    gt_peak = max(p["torque_nm"] for p in gt_tc)
    peak = max(p["torque_nm"] for p in tc)
    assert abs(peak - gt_peak * 1.08) < 0.5, f"peak {peak} not 1.08* {gt_peak}"
    assert peak == 588.91


def test_provenance_urls_and_dates():
    d = _load(VEH)
    prov = d["provenance"]
    assert "source_urls" in prov and len(prov["source_urls"]) >= 2
    assert "supergt.net" in prov["source_urls"][0]
    assert prov.get("date_fetched") == "2026-09-12"
    assert prov.get("torque_source") == "data/vehicles/gt.json 18 points 1000-7000rpm"


def test_mvp_keys_present():
    d = _load(VEH)
    for k in ["mass_kg", "weight_dist_front", "wheelbase_m", "cog_height_m", "cda", "cl", "tire_mu_x", "tire_mu_y", "engine_power_factor", "final_drive"]:
        assert k in d, f"missing {k}"


def test_f1_spa_unchanged_guard():
    spa = json.loads((ROOT / "data" / "tracks" / "spa.json").read_text(encoding="utf-8"))
    assert spa["length_m"] == 6953.611
    f1 = json.loads((ROOT / "data" / "vehicles" / "f1.json").read_text(encoding="utf-8"))
    assert f1["mass_kg"] == 650
