# -*- coding: utf-8 -*-
"""Kart vehicles regression: rental_gx270 and fs125_x30."""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
RENTAL = ROOT / "data" / "vehicles" / "rental_gx270.json"
FS125 = ROOT / "data" / "vehicles" / "fs125_x30.json"


def _load(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def test_files_exist():
    assert RENTAL.exists()
    assert FS125.exists()


def test_rental_mass_185():
    d = _load(RENTAL)
    assert d["M"] == 185
    assert d["mass_kg"] == 185
    assert d["provenance"]["mass_total_kg"] == 185
    assert d["Type"] == "Kart"
    assert d["Name"] == "Rental Kart GX270"


def test_fs125_mass_150():
    d = _load(FS125)
    assert d["M"] == 150
    assert d["mass_kg"] == 150
    assert d["provenance"]["mass_total_kg"] == 150
    assert d["Type"] == "Kart"
    assert d["Name"] == "FS125 IAME X30"


def test_rental_engine_provenance():
    d = _load(RENTAL)
    prov = d["provenance"]
    assert prov["engine"] == "Honda GX270"
    assert prov["power_ps"] == 8.5
    assert prov["peak_torque_nm"] == 46.0
    assert "GX270" in prov["description"]


def test_fs125_engine_provenance():
    d = _load(FS125)
    prov = d["provenance"]
    assert prov["engine"] == "IAME X30 125cc"
    assert prov["power_ps"] == 28
    assert prov["peak_torque_nm"] == 23.0
    assert prov["power_rpm"] == 8500


def test_kart_torque_curves():
    r = _load(RENTAL)
    f = _load(FS125)
    assert len(r["torque_curve"]) == 10
    assert r["torque_curve"][0]["rpm"] == 1000
    assert r["torque_curve"][-1]["rpm"] == 4000
    assert len(f["torque_curve"]) == 10
    assert f["torque_curve"][0]["rpm"] == 3000
    assert f["torque_curve"][-1]["rpm"] == 12000
    # governed / peak checks
    assert max(p["torque_nm"] for p in r["torque_curve"]) == 46.0
    assert max(p["torque_nm"] for p in f["torque_curve"]) == 23.0


def test_kart_mvp_and_single_ratio():
    for p in [RENTAL, FS125]:
        d = _load(p)
        for k in ["mass_kg", "weight_dist_front", "wheelbase_m", "cog_height_m", "cda", "cl", "tire_mu_x", "tire_mu_y", "engine_power_factor", "final_drive"]:
            assert k in d
        assert d["ratio_gearbox"] == [1.0]
        assert d["drive"] == "RWD"


def test_f1_spa_unchanged_guard():
    spa = json.loads((ROOT / "data" / "tracks" / "spa.json").read_text(encoding="utf-8"))
    assert spa["length_m"] == 6953.611
    f1 = json.loads((ROOT / "data" / "vehicles" / "f1.json").read_text(encoding="utf-8"))
    assert f1["mass_kg"] == 650
    assert f1["M"] == 650
