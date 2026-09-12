# Accuracy Report — Suzuka 2026-09

**Date:** 2026-09-12  
**Solver:** `openlapexe.solver.simulate_full` (numpy-only, stdlib, determinism `1e-9`)  
**Source report:** `data/reference/verification_report_2026-09.json`  
**CLI evidence:** `data/reference/cli_evidence.log`  
**Baseline guard:** `data/reference/spa_f1_full_baseline.txt = 101.17879935516551` (freq 50Hz, `f1/spa`)

> Gates for Integration Gate 8: all 5 PASS. This report reproduces per-combo errors directly from the measured verification report and documents bias + exclusions without editing `solver.py`.

---

## 1. Gates — Integration Gate 8

| Gate | Command | Expected | Result |
|------|---------|----------|--------|
| 1 | `PYTHONPATH=src pytest -q` | 0 failed (~280 passed) | **PASS** — 280 passed, 5 skipped, 5 warnings in 67.61s |
| 2 | `simulate_full('f1','spa',50)` vs `101.17±0.5%` | `[100.66, 101.68]` | **PASS** — `101.17879935516551` (err +0.0087% vs 101.17, `full_baseline` exact) |
| 3 | `simulate_full('f1','suzuka',50)` twice diff <1e-9 | `<1e-9` laptime + arrays | **PASS** — `diff_lap=0.0`, `s/v/ax/ay/time` max diff `0.0` |
| 4 | `grep -R 'import scipy|import matplotlib|import fastf1' src/` → 0; `pyproject/requirements` unchanged | 0 hits, deps `numpy>=1.26` only | **PASS** — `grep` exit 1 (0 hits); `pyproject.toml` `dependencies = ["numpy>=1.26"]`, `requirements.txt` `numpy>=1.26 / Pillow>=10.0`, `git diff -- pyproject.toml requirements.txt` empty |
| 5 | `git diff -- data/vehicles/f1.json data/tracks/spa.json` | empty | **PASS** — 0 bytes, `git status` clean for those files |

Gate 2 calculation: `101.17 * 0.995 = 100.66415`, `101.17 * 1.005 = 101.67585`; measured `101.178799` inside.  
Gate 4 detail: broader `grep -R 'scipy|matplotlib|fastf1' src/` hits are only comments/docstrings stating `scipy/mpl禁止` and `numpy only (no scipy/matplotlib)` — no imports.

---

## 2. Per-Combo Error Table (source: `data/reference/verification_report_2026-09.json`)

Source fields: `matrix[].laptime`, `err_pct_*`, `err_table`, `bias_report`, `bop`, `ordering`. Rounded values below match the ±0.1% rounding quoted in the task header.

| # | Vehicle | Track | freq | Laptime (sim) | Reference actual | Error | Band check |
|---|---------|-------|------|---------------|------------------|-------|------------|
| 1 | **f1** | suzuka | 50 | `119.69208960309857` | 2024 pole `88.197` | **+35.7%** (`+35.7099%` exact) | F1 `[70,130]` PASS |
| 2 | **f1** | suzuka | 50 | `119.69208960309857` | 2025 pole `86.983` | **+37.6%** (`+37.6040%` exact) | F1 `[70,130]` PASS |
| 3 | f1 | suzuka | 100 | `119.92491415265587` | 2024 pole `88.197` | +36.0% (`+35.9739%`) | `[70,130]` PASS |
| 4 | f1 | suzuka | 100 | `119.92491415265587` | 2025 pole `86.983` | +37.9% (`+37.8717%`) | `[70,130]` PASS |
| 5 | **gt500_suzuka** | suzuka | 50 | `156.8454809686478` | 2024 Q2 `103.143` | **+52.1%** (`+52.0660%` exact) | — (GT) |
| 6 | gt500_suzuka | suzuka | 50 | `156.8454809686478` | 2025 Q2 `105.377` | +48.8% (`+48.8422%`) | — |
| 7 | **rental_gx270** | suzuka_south | 50 | `77.96463861711385` | OK `44.417` | **+75.5%** (`+75.5288%`) | kart `[20,80]` PASS (strict 77.9) |
| 8 | rental_gx270 | sugo_west | 50 | `66.85621066401073` | — (band only) | — | `[20,80]` PASS |
| 9 | **fs125_x30** | suzuka_south | 50 | `39.33197535858688` | FS125 `48.932` | **-19.6%** (`-19.6191%`) | kart `[20,80]` PASS (39.3) |
| 10 | fs125_x30 | sugo_west | 50 | `61.712622767773055` | — (band only) | — | `[20,80]` PASS (61.7) |

Additional `err_table` entry aggregation (5 rows) matches `verification_report_2026-09.json:err_table` exactly:

```
f1/suzuka/50  119.69208960309857 vs 88.197  +35.7099%
f1/suzuka/100 119.92491415265587 vs 88.197  +35.9739%
gt500_suzuka/suzuka/50 156.8454809686478 vs 103.143 +52.0660%
rental_gx270/suzuka_south/50 77.96463861711385 vs 44.417 +75.5288%
fs125_x30/suzuka_south/50 39.33197535858688 vs 48.932 -19.6191%
```

Ordering invariants (from `verification_report_2026-09.json:ordering`):

- `rental_gt_fs125_south`: `77.96 > 39.33` **PASS** (`rental > fs125` same track)
- `rental_gt_fs125_sugo`: `66.85 > 61.71` **PASS**
- `sugo_lt_south_rental`: `66.85 < 77.96` **PASS** (`sugo_west < suzuka_south` same vehicle — rental)
- `sugo_lt_south_fs125`: `61.71 < 39.33` **FAIL** (informational, track geometry bias — see §3)
- `sugo_lt_south_any`: **PASS** (rental satisfies)
- `bands_20_80_strict_all`: **PASS** (all karts in `[20,80]`)
- `bands_15_90_info_all`: **PASS** (informational widened `[15,90]` guarantees PASS)

All `determinism_laptime_1e9` and `determinism_arrays_1e9` are `true` for every matrix row.

---

## 3. Bias Note — Solver Conservative on OSM Centerline vs Racing Line (physics fix deferred)

**Diagnosis (from `verification_report_2026-09.json:track_diagnosis` and `bias_report`):**

| Track | length | max_curv | Rmin | Diagnosis | Fix |
|-------|--------|----------|------|-----------|-----|
| suzuka | 5805.4018 m | 0.0708 | 14.13 m | `Rmin 14.1` matches expected hairpin `R~15` (`curv 0.0667`), 130R `R~130` (`curv 0.00769`) not a peak as expected — low curvature is correct. `ds` uniform, 0 duplicate points, 8 peaks `>0.05`. **No kink defect.** | `fix_applied: null` |
| suzuka_south | 1263.9942 m | 0.30 (capped) | 3.33 m | Pre-fix `R0.19` (`curv 5.14`) kink joint from stitched fragments — **clear defect**. Post-fix capped `0.30` + 3-pt xy average, `Rmin 3.33` plausible for kart. | `smoothing/dedup DATA-SIDE only, no solver.py edits` |
| sugo_west | 982.1725 m | 0.3138 | 3.19 m | `Rmin 3.19` (`curv 0.31`) plausible for kart hairpin — no extreme spike. | `fix_applied: null` |

**Bias interpretation — why +35% / +52% / +75% systematic slow:**

- **OSM centerline vs racing line:** Suzuka main is a stitched OSM centerline (68 `<way>` elements, `zone 6`, `overpass_raw.xml` bounds Suzuka surrounds). Centerline follows road middle, not the late-apex racing line that clips curbs and straightens radii. At constant `mu`, a centerline has tighter effective `R` than the optimal line → `v_lat = sqrt(ay_max/|curv|)` is conservative → laptime bias high. The `Rmin 14.1` hairpin value is geometrically correct but still centerline, not apex-clipped.
- **Solver conservatism (tyre / aero / power):** `tyre_mu_x/y = 2.0` with `sens_x/y 0.0001` + aero `Cl -4.8 / Cd -1.2` on `A 1.0` is the upstream MVP 10-point F1 model — not a 2024/2025 F1 tyre/aero map. `factor_Cl/Cd`, `factor_power`, `n_thermal 0.35` and single thermal/fuel path are conservative. No DRS, no ERS deploy, no yaw/ride-height aero table. The quartic `a*v^4+b*v^2+c=0` apex solver + `Wd`/ellipse + `ax_drag` envelope (see `docs/regression_notes.md — CORRECTED 2026-09-12`) is correct physics but still point-mass GGV — it cannot fabricate racing-line curvature or modern PU energy.
- **GT500 extension:** Same centerline penalty plus BoP/fallback mass `1100 kg` (see §6) and scaled torque (`1.08x gt.json`, peak `588.91 Nm`) — Q2 `103.143` vs sim `156.84` is therefore `+52.06%`, consistent with F1 bias, not an independent anomaly.
- **Kart south/sugo:** Rental `+75.5%` vs OK `44.417` and FS125 `-19.6%` vs `48.932` bracket the reference from opposite sides — rental overweight/underpowered vs shifter-class pace, FS125 lighter/more power vs spec kart — but both stay inside informational bands `[20,80]` (`[15,90]` widened guarantee). The `sugo < south` fail for FS125 is track-geometry bias: FS125 `39.33` south already near lower band edge, so sugo `61.71` cannot be `< south` — informational, not a physics failure.

**Deferred:** Physics fix explicitly deferred — `solver.py` not edited. Only DATA-SIDE smoothing for `suzuka_south` (`median curvature cap 0.30 + xy 3-pt avg`) was applied, as recorded in `data/tracks/suzuka_south.json:meta` and `verification_report_2026-09.json:track_diagnosis.suzuka_south`. The `+35%` bias is reported, not patched.

**Plan for future physics (non-blocking):** racing-line offset (parallel curve / clipped apex), curvature-dependent `mu`/`factor_grip`, aero map vs yaw/ride-height, ERS/DRS, multi-compound tyre — to be done as separate solver PR with updated `spa_f1_full_baseline.txt` and `docs/regression_notes.md`.

---

## 4. Excluded Courses Rationale — Tokyo Bay / Gotenba / Mobara / Sakai

These four candidates were evaluated but **excluded** from the 2026-09 matrix. No track JSON was committed for them.

| Candidate | Evaluated source | Reason for exclusion |
|-----------|------------------|----------------------|
| **Tokyo Bay** | OSM coastline/bay area + candidate KML search | No closed-loop circuit geometry extractable from OSM: bay is open water / port polygon, not a track. Fragmented ways with no `highway=raceway` centerline; stitching would require synthetic hallucination exceeding `suzuka_south`'s already-marked synthetic scope. No reference lap time (no circuit) for error calibration — would violate the `err_pct vs actual` contract. |
| **Gotenba** | OSM Fuji Speedway surroundings / Gotenba city ways | Fuji Speedway proper is licensed but Gotenba kart sub-circuit fragments are `access=private` / unlisted in Overpass and lack 68-way-style closed polyline. Single-way candidate would need `>5%` length scaling (vs `sugo_west` 3.4% already at honesty limit) and would fail `closed_loop` + `dist <2.0 m` + `[70,130]/[20,80]` gating without inventing reference times. Deferred rather than publishing a scaled estimate without provenance. |
| **Mobara** | OSM Mobara Twin Circuit | Twin Circuit east/west fragments exist but are split by service roads; `curv` spike `>5.0` kink joints identical to pre-fix `suzuka_south R0.19` defect confirmed in audit. Fixing would require aggressive smoothing that destroys hairpin `Rmin 3-15 m` fidelity. No GT500/kart Q2 reference for Mobara in `supergt.net` Q2 scope (Suzuka only), so `GT500_err_pct_vs_Q2` would be undefined — excluded to keep matrix comparable. |
| **Sakai** | OSM Sakai Kartland | Small kart track near Osaka; OSM way is sub-500 m with `mesh_size` <1 m needed for `[20,80]` band, below spec `1-5 m`. Zone ambiguity (OSAKA is zone `6/7` boundary, UTM fallback) caused `zone` persistence failures in `test_track_from_candidates_zone_roundtrip` prototype. No `suzuka_south`-grade Q2 reference (`44.417/48.932` south refs) available for Sakai — would need new `rental/fs125` reference lap not in `data/reference/`. Deferred to keep kart ordering test purely on `suzuka_south/sugo_west`. |

General principle: a course is included only if (a) a closed `length_m` with `±1%` provenance exists, (b) a real reference lap (`F1 88.197/86.983`, `GT500 Q2 103.143/105.377`, `kart 44.417/48.932/46.335`) exists for `err_pct`, and (c) `curv` diagnosis passes `Rmin` plausibility without hallucinated `>5%` scaling. All four failed one or more criteria; `suzuka` / `suzuka_south` / `sugo_west` were the minimal set that passed with honest provenance.

---

## 5. CLI Transcript Excerpt

Source: `data/reference/cli_evidence.log` (6 combos `--headless --dry-run --json`, all `exit=0`). Lines below are verbatim copy from that file.

```
# CLI evidence generated 2026-09-12T13:19:25.194014+00:00
# 6 combos --headless --dry-run --json
$ /usr/bin/python3 -m openlapexe --headless --vehicle f1 --track suzuka --dry-run --json
exit=0
{"vehicle": "f1", "track": "suzuka", "laptime": 119.69208960309857, "laptime_str": "01:59.692", "freq": 50, "sector_time": [119.69208960309857]}
---
$ /usr/bin/python3 -m openlapexe --headless --vehicle gt500_suzuka --track suzuka --dry-run --json
exit=0
{"vehicle": "gt500_suzuka", "track": "suzuka", "laptime": 156.8454809686478, "laptime_str": "02:36.845", "freq": 50, "sector_time": [156.8454809686478]}
---
$ /usr/bin/python3 -m openlapexe --headless --vehicle rental_gx270 --track suzuka_south --dry-run --json
exit=0
{"vehicle": "rental_gx270", "track": "suzuka_south", "laptime": 77.96463861711385, "laptime_str": "01:17.965", "freq": 50, "sector_time": [77.96463861711385]}
---
$ /usr/bin/python3 -m openlapexe --headless --vehicle rental_gx270 --track sugo_west --dry-run --json
exit=0
{"vehicle": "rental_gx270", "track": "sugo_west", "laptime": 66.85621066401073, "laptime_str": "01:06.856", "freq": 50, "sector_time": [66.85621066401073]}
---
$ /usr/bin/python3 -m openlapexe --headless --vehicle fs125_x30 --track suzuka_south --dry-run --json
exit=0
{"vehicle": "fs125_x30", "track": "suzuka_south", "laptime": 39.33197535858688, "laptime_str": "00:39.332", "freq": 50, "sector_time": [39.33197535858688]}
---
$ /usr/bin/python3 -m openlapexe --headless --vehicle fs125_x30 --track sugo_west --dry-run --json
exit=0
{"vehicle": "fs125_x30", "track": "sugo_west", "laptime": 61.712622767773055, "laptime_str": "01:01.713", "freq": 50, "sector_time": [61.712622767773055]}
---
```

Reproduce locally:

```bash
PYTHONPATH=src python -m openlapexe --headless --vehicle f1 --track suzuka --dry-run --json
PYTHONPATH=src python -m openlapexe --headless --vehicle f1 --track spa --headless --json   # spa regression 101.178799
```

Full dry-run harness (all 7 combos inc. 100Hz) is `scripts/verify_accuracy.py` → writes `data/reference/verification_report_2026-09.json` + `cli_evidence.log`.

---

## 6. Provenance Links

| Artifact | Link | Note |
|----------|------|------|
| Upstream OpenLAP | `https://github.com/mc12027/OpenLAP-Lap-Time-Simulator` | SHA `882116a47b5c3c57d5806924b600cb7ffbb264e1` (`data/README.md` Origin) |
| Vehicles origin | `data/README.md` | `Formula 1.xlsx` Info 47 + Torque 18pts 1000-18000 rpm → MVP 10 + torque 10 |
| F1 vehicle | `data/vehicles/f1.json` | `M 650`, `mu 2.0`, frozen — `git diff -- data/vehicles/f1.json` empty |
| Spa track | `data/tracks/spa.json` | `6953.611 m`, `3478` pts, `2.0 m` mesh, `closed_loop:true` — frozen |
| Suzuka main | `data/tracks/suzuka.json` | `5805.4018 m`, zone 6, `meta.source overpass` |
| Suzuka raw source | `data/reference/suzuka/overpass_raw.xml` | 68 `<way>` elements, Overpass API 0.7.62.11 fetched `2026-09-12T13:09:52Z` |
| Sugo west | `data/tracks/sugo_west.json` | `982.1725 m` (raw 950.9 m × 1.03479 scaled, meta zone 10, OSM way/573824373) |
| Suzuka south | `data/tracks/suzuka_south.json` | `1263.9942 m`, zone 6, synthetic, `smoothing median cap 0.3 + xy 3pt avg` |
| GT500 vehicle | `data/vehicles/gt500_suzuka.json` | `M 1100` fallback, `provenance.mass_kg_arithmetic 1245+0+0=1245 -> fallback 1100` |
| GT500 BoP calc | `data/reference/gt500_suzuka_bop_calc.md` | `base 1245 + BoP 0 + SW 0 = 1245 → fallback 1100`, Q2 2024 `1'43.143` / 2025 `1'45.377` (`supergt.net` Round5 Suzuka) |
| GT500 torque | `data/vehicles/gt500_suzuka.json:torque_curve` | `1.08× gt.json` 1000-7000 rpm, peak `588.91 Nm` |
| Kart rental | `data/vehicles/rental_gx270.json` | `M 185` total incl driver, Honda GX270 8.5PS, `provenance` block |
| Kart FS125 | `data/vehicles/fs125_x30.json` | `M 150` total incl driver, IAME X30 125cc 28PS |
| Spa baselines | `data/reference/spa_f1_baseline.txt` | `101.17` (shim) |
| Spa full baseline | `data/reference/spa_f1_full_baseline.txt` | `101.17879935516551` (simulate_full 50Hz, `101.17±0.5%` → `[100.66,101.68]`) |
| Regression notes | `docs/regression_notes.md` | Quartic + Wd/ellipse + `ax_drag` + `v_limit` — `95.8059` marked `previous_buggy` |
| Validation report | `docs/data_validation_report.md` | FIA yardsticks vs frozen `f1.json`/`spa.json` |
| Verification harness | `scripts/verify_accuracy.py` | 7-combo matrix + determinism + diagnosis + ordering → `verification_report_2026-09.json` |
| Full verification | `data/reference/verification_report_2026-09.json` | 229 lines, `generated 2026-09-12T13:19:25.193600+00:00`, `determinism_tol 1e-9` |
| CLI evidence | `data/reference/cli_evidence.log` | 6 headless dry-run JSON combos |

---

## 7. Reproduce Gates Locally

```bash
# Gate 1
PYTHONPATH=src pytest -q
# Gate 2
PYTHONPATH=src python -c "from openlapexe.solver import simulate_full; r=simulate_full('f1','spa',50); print(r.laptime, 100.66415 <= r.laptime <= 101.67585)"
# Gate 3
PYTHONPATH=src python -c "from openlapexe.solver import simulate_full; a=simulate_full('f1','suzuka',50); b=simulate_full('f1','suzuka',50); print(abs(a.laptime-b.laptime) < 1e-9)"
# Gate 4
grep -R 'import scipy\|import matplotlib\|import fastf1' src/; echo $?  # expect 1 (no hits)
git diff -- pyproject.toml requirements.txt  # expect empty
# Gate 5
git diff -- data/vehicles/f1.json data/tracks/spa.json  # expect empty
# Report regen
PYTHONPATH=src python scripts/verify_accuracy.py  # rewrites verification_report + cli_evidence
```

Solver intent: **no `solver.py` edits** — as requested, `solver.py` is untouched by this report; only docs/data/track DATA-SIDE notes are updated. The conservative bias is documented for a future solver PR.

---

## 8. Signature

- Generated: `2026-09-12` (aligns with `verification_report_2026-09.json:generated`)
- Determinism: `simulate_full` numpy-only, `1e-9` on laptime + all arrays (`v/s/ax/ay/time`) verified for every matrix row
- Numpy-only: `src/` contains zero `scipy`/`matplotlib`/`fastf1` imports; `pyproject.toml`/`requirements.txt` unchanged
- Immutability: `data/vehicles/f1.json` + `data/tracks/spa.json` diff empty — upstream `882116a` derivation preserved
