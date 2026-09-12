# Data Validation Report — FIA Yardstick vs Current Data

Date: 2026-09-12
Scope: `data/vehicles/f1.json`, `data/tracks/spa.json` against FIA and real world yardsticks
Upstream: [mc12027/OpenLAP-Lap-Time-Simulator](https://github.com/mc12027/OpenLAP-Lap-Time-Simulator) SHA `882116a` (`882116a47b5c3c57d5806924b600cb7ffbb264e1`)
Policy: `data/*.json` is frozen, `git diff -- data/` must stay empty

## Summary

Current data reproduce the upstream OpenLAP snapshot faithfully. Track geometry is within 1 percent of the official length and within 1 percent of official elevation change. Vehicle mass and tyre grip are intentionally offset from the 2023 to 2025 regulations because they mirror the upstream `Formula 1.xlsx` point mass model, not a current homologated car. Lap time deltas against the real 2025 Spa pole therefore reflect solver physics and model scope, not data errors that should be patched by editing the frozen JSON.

Conclusion: solver is the root cause for lap time realism gaps, data remain frozen.

## Sources

* Vehicles: `data/vehicles/f1.json` derived from upstream `Formula 1.xlsx` (47 items on Info sheet, 18 point torque curve 1000 to 18000 rpm), compressed to MVP 10 keys plus torque table. See `data/README.md`.
* Tracks: `data/tracks/spa.json` derived from upstream `Spa-Francorchamps.xlsx` (Info, Shape, Elevation, Banking, Grip, Sectors) via a reimplementation of `OpenTRACK.m` / `OpenTRACK.py`.
* Yardsticks: FIA Circuit Licence length 7004 m, FIA Technical Regulations mass 798 kg (2023 to 2024) and 800 kg (2025), modern PU about 630 kW ICE plus 120 kW MGU-K, dry tyre mu about 1.4 to 1.6, Spa elevation change about 102.2 m, maximum grade about 17 percent, 19 official corners, 2025 Belgian GP dry pole 1:40.562 by L. Norris.

## Track — Spa-Francorchamps

File: `data/tracks/spa.json`
Metadata: `length_m 6953.611`, `num_points 3478`, `mesh_size_m 2.0`, `closed_loop true`, source `mc12027/OpenLAP-Lap-Time-Simulator SHA 882116a Spa-Francorchamps.xlsx`

Measured from file: min `z 366.09` m, max `z 467.59` m, delta 101.50 m. Maximum grade `dz/ds` about 14.4 percent. Average point spacing `6953.61 / 3478 = 2.00` m.

| Item | Yardstick | Current (`spa.json`) | Delta | Verdict |
|---|---|---|---|---|
| Course length | 7004 m (FIA official) | 6953.611 m | -50.39 m, -0.72 percent | Pass, within ±1 percent. Matches the upstream Shape sum exactly, documented in `data/README.md`. |
| Point count / mesh | — | 3478 points, 2.0 m mesh, avg spacing 2.00 m | — | Pass. Consistent with 1 to 5 m spec, closed loop polyline is monotonic `s 0 -> L`. |
| Elevation change | 102.2 m (official) | 101.50 m (min to max `z`) | -0.70 m, -0.68 percent | Pass. Within measurement and datum differences. |
| Maximum grade | 17 percent (Eau Rouge / Raidillon) | 14.37 percent (`max abs(dz/ds)`) | -2.63 pp | Accept. Grade depends on sampling and smoothing, Pchip versus linear and 2 m mesh lower the instantaneous peak. Functionally similar. |
| Corners | 19 official | 21 segments where `abs(curv) > 0.002` | +2 at this threshold | Accept. Count depends on curvature threshold and splitting of compound bends (for example La Source, Pouhon, Stavelot). Raw `curv` series contains 19 major peaks, extra segments are sub segments of long compound corners, not a data error. |
| Banking / grip / sectors | Banking and grip vary through lap | `banking_rad` and `grip_factor` present per point, 3 sectors via `sector_id` | — | Pass. `Track2` 8 column model is present, `grip_factor 1.0` default matches upstream. |

Notes:

* Length delta is intentional, the file reproduces the upstream sheet sum `6953.611 m` rather than forcing 7004 m. Forcing the official length would break the Shape geometry and the closure correction (`DH` tangent plus `DX/DY/DZ` closure) described in `data/README.md`.
* Elevation and grade are close enough that lap time sensitivity is small. A 0.7 m elevation shortfall and 2.6 pp grade shortfall do not explain multi second lap gaps alone.

## Vehicle — Formula 1

File: `data/vehicles/f1.json`
Keys: MVP 10 plus full 18 point `torque_curve` (also carries legacy OpenLAP keys for compatibility)

| Item | Yardstick (2023 to 2025 F1) | Current (`f1.json`) | Delta | Verdict |
|---|---|---|---|---|
| Mass | 798 kg (2023 to 2024) / 800 kg (2025) minimum with driver, no fuel | 650 kg (`M` and `mass_kg`) | -148 kg (-18.5 percent) vs 798 kg, -150 kg (-18.8 percent) vs 800 kg | Frozen, by design. Mirrors upstream `Total Mass 650 kg`. Not a bug to patch. |
| Weight distribution | About 45 to 46 percent front | `weight_dist_front 0.45`, `df 0.45` | — | Pass. Matches upstream. |
| Wheelbase | About 3.6 m current regs | 3.0 m (`L` and `wheelbase_m`) | -0.6 m | Frozen. Mirrors upstream. |
| Aero CdA | Varies by team, on order 1.0 to 1.3 | `Cd -1.2`, `A 1.0`, `cda 1.2` | — | Pass. Upstream value, used as `abs(CD)*A`. |
| Aero Cl | Varies, on order -3.5 to -5.0 at high downforce | `Cl -4.8`, `cl -4.8` | — | Pass. Upstream value. |
| Power unit | About 630 kW ICE plus 120 kW MGU-K, about 750 kW combined, plus ERS deploy strategy | Peak about 559 kW at 18000 rpm from torque curve alone (see table below), `factor_power 1.0` | About -190 kW vs combined PU if ERS is counted, closer to ICE only | Frozen. Upstream curve predates current PU, no ERS model. The file has no MGU-K, no battery, no deploy logic. This is a model scope choice, not a typo. |
| Tyre mu | Dry slick peak about 1.4 to 1.6 (load and temp sensitive) | `mu_x 2.0`, `mu_y 2.0`, `tire_mu_x 2.0`, `tire_mu_y 2.0` | +0.4 to +0.6 (+25 to +43 percent) | Frozen. Mirrors upstream `Longitudinal/Lateral Friction Coefficient 2.0`. Intentionally high, compensated by `sens_x/sens_y` load sensitivity and `mu_x_M/mu_y_M`. |
| Load sensitivity | Mu falls with load | `sens_x 0.0001`, `sens_y 0.0001`, `mu_x_M 250`, `mu_y_M 250` | — | Pass. Upstream values present. |
| CoG height | About 0.30 to 0.35 m | `cog_height_m 0.30` | — | Pass. Estimate documented in `data/README.md`, reserved for future load transfer. |
| Gearbox | 8 speed, final drive varies | `n_gearbox 0.98`, 7 ratios plus `ratio_final 7`, `shift_time 0.01 s` | — | Pass. Upstream values. Note `simulate_full` uses `ratio_gearbox` multi gear table, `app.simulate` uses simplified `final_drive` only, both are correct per their fidelity level. |

Torque derived power (ICE only, `P = T * omega / 1000`):

| rpm | torque Nm | power kW |
|---|---|---|
| 1000 | 125.0 | 13.1 |
| 7000 | 150.0 | 110.0 |
| 8000 | 200.0 | 167.6 |
| 11000 | 300.0 | 345.6 |
| 13000 | 350.0 | 476.5 |
| 15000 | 330.0 | 518.4 |
| 18000 | 296.75 | 559.4 |

No ERS term is added in the JSON. If you compare 559 kW to a modern combined 750 kW you will see a gap, but that gap belongs to the physics model, not to the data file. Adding 120 kW in JSON without a deploy and harvesting model would make the car wrong in a different way.

## Lap Time Yardstick

Real 2025 Spa dry pole: 1:40.562 (100.562 s) by L. Norris.

Current simulator baselines on the same `f1 + spa` pair:

* `app.simulate('f1','spa')` simplified point mass QSS, single `final_drive`, plane track, `freq` independent: 101.17 s (`data/reference/spa_f1_baseline.txt`), allowed ±0.5 percent [100.66, 101.68].
* `openlapexe.solver.simulate_full('f1','spa', 50)` full 47 item vehicle, banking and grip, Pchip curvature, multi gear, energy integration, `freq` respected `step = 100/freq`: 95.81 s (`data/reference/spa_f1_full_baseline.txt`), allowed ±0.5 percent [95.33, 96.29].

So the simplified baseline sits +0.61 s (+0.6 percent) above the real pole, the full baseline sits -4.75 s (-4.7 percent) below it. The two baselines differ by -5.36 s, which `docs/regression_notes.md` breaks down as `D1 0 s` (OpenDRAG split, no physics change) plus `V1 -1.5 to -2.0 s` (47 item vehicle and CoG load transfer) plus `T1 -0.8 to -1.2 s` (banking, grip, Pchip) plus `S1 -2.2 to -2.8 s` (freq respected mesh, multi gear, energy).

That tells you where to look. The data themselves are stable and reproduce the upstream sheets, the lap time moves when the solver fidelity moves.

## Delta Summary Table

| Domain | Yardstick | Current | Delta | Impact on lap |
|---|---|---|---|---|
| Track length | 7004 m | 6953.61 m | -0.72 percent | About -0.7 s if linear, small. |
| Elevation delta | 102.2 m | 101.50 m | -0.68 percent | Negligible. |
| Max grade | 17 percent | 14.37 percent | -2.63 pp | Small, slightly lower climb resistance on Kemmel and Eau Rouge. |
| Corners | 19 | 19 peaks, 21 segments at `curv > 0.002` | Definition dependent | None if thresholds align. |
| Mass | 798 / 800 kg | 650 kg | -18.5 / -18.8 percent | Large if you think in real car terms, but solver is tuned to this mass and its aero and mu. Changing mass without retuning the whole GGV would break lap time more than it helps. |
| Tyre mu | 1.4 to 1.6 | 2.0 | +25 to +43 percent | Large on paper, offset by load sensitivity and by the GGV loop that caps `ay_max` and `ax_max`. Again, retuning is a solver task. |
| PU peak | About 750 kW combined | About 559 kW ICE only | About -25 percent vs combined | Mid. The full solver adds gear dependent `fx_engine` and TPS logic, so raw peak alone does not map one to one to lap. |

## Why Solver Is Root Cause and Data Stay Frozen

1. **Data reproduce the stated source.** Every frozen value in `f1.json` and `spa.json` can be traced to `mc12027/OpenLAP-Lap-Time-Simulator` at `882116a`, as documented in `data/README.md`. `mass_kg 650`, `mu 2.0`, `cda 1.2`, `cl -4.8` and the 18 point torque curve are literal transcriptions. `spa.json` length `6953.611 m` is the exact Shape sum from `Spa-Francorchamps.xlsx`, with the same `mesh_size_m 2.0` and `closed_loop true` closure logic. `git diff -- data/` is empty today and must remain so, otherwise the repo would stop being a faithful derivation of its GPLv3 upstream and would lose reproducibility.

2. **Gaps to modern F1 are model scope, not data typos.** Mass, PU with ERS, DRS, tyre thermal and wear, ground effect aero maps, and brake blending are not in the upstream sheets at all. Fixing them by editing the JSON would be a thin patch. For example raising mass to 798 kg while keeping the point mass plus GGV coefficients tuned for 650 kg would slow the car for the wrong reason, and adding 120 kW without an energy and deploy model would make it too fast in the wrong places (long Kemmel straight versus traction limited La Source).

3. **Track deltas are within tolerance and solver sensitive.** Length within 1 percent and elevation within 1 percent are already inside the validation guard `6933 to 7075 m` in `tests/test_data_schema.py`. Grade and corner count differences come from interpolation choices (Pchip versus linear, 2 m mesh, `banking_rad` smoothing). Those choices live in `src/openlapexe/solver.py` and `src/openlapexe/track.py`, not in the JSON points.

4. **Lap time moves with solver, not with data edits.** The -5.36 s shift from 101.17 s to 95.81 s came from solver changes alone (V1, T1, S1) while the data files did not change. That is direct evidence that the solver dominates realism. Further realism work belongs in the solver: load dependent mu, CoG transfer already added in V1, full ERS and DRS models, aero maps that vary with ride height and yaw, and proper combined slip handling, with updated `data/reference/*baseline.txt` values and notes in `docs/regression_notes.md`.

## Recommendations (Do Not Edit `data/*.json`)

* Keep `data/vehicles/f1.json` and `data/tracks/spa.json` frozen. If modern spec alignment is needed, create new presets such as `data/vehicles/f1_2025.json` or `data/tracks/spa_2025.json` and leave the baseline pair intact for regression.
* Put physics corrections in code: ERS energy and deploy, DRS, tyre temp and load sensitivity refinement, aero varying with speed and banking, and brake system capacity. Update `data/reference/spa_f1_full_baseline.txt` and `docs/regression_notes.md` alongside each solver change.
* Keep validation strict: `pytest tests/test_data_schema.py -q` and the regression suite `tests/test_regression_spa_f1.py` plus `tests/test_regression_full.py` must pass before any conclusion about realism is drawn.

## Verification

```bash
pytest tests/test_data_schema.py -q
git diff -- data/
```

Expected: `pytest` passes (6 tests, vehicle MVP, torque 8 to 18 points, track length ±1 percent, mesh 1 to 5 m, points contain `s,x,y,z,curv`), and `git diff -- data/` prints nothing. Do not edit `data/*.json` to make tests pass, fix the solver or the tests instead.

## Provenance

* This report compared `data/vehicles/f1.json` and `data/tracks/spa.json` as found on disk to the yardsticks listed in the task: course 7004 m, mass 798 kg (23 to 24) and 800 kg (25) vs json 650 kg frozen, PU 630 plus 120 kW, mu 1.4 to 1.6 vs json 2.0, elevation 102.2 m, grade 17 percent, 19 corners, real dry pole 2025 1:40.562 Norris.
* Generation method matches `data/README.md`: clone upstream at `882116a`, read sheets with `openpyxl`/`pandas` in `/tmp`, generate via the `gen_vehicles.py` / `gen_tracks2.py` path, no `scipy`/`matplotlib` in `requirements.txt`.
