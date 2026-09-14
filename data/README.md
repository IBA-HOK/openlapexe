# data, 出典と生成メモ

## Origin

- Upstream: [mc12027/OpenLAP-Lap-Time-Simulator](https://github.com/mc12027/OpenLAP-Lap-Time-Simulator)
- Commit SHA: `882116a47b5c3c57d5806924b600cb7ffbb264e1` (abbr `882116a`), `Update OpenVEHICLE.m` (Apr 2020)
- 取得方法: `/tmp` に `git clone --depth 1` で取得、`openpyxl`/`pandas` で読込
- License: GPLv3（本リポジトリは派生物として GPLv3 を継承）

## Vehicles (`data/vehicles/`)

- 元ファイル: `Formula 1.xlsx`（`Info` シート 47項目 + `Torque Curve` 18点 1000 to 18000 rpm）
- 圧縮: MVP 10項目に集約 + トルク表 8 to 12点

| MVP key | 由来 |
|---|---|
| `mass_kg` | Info `Total Mass` 650 kg |
| `weight_dist_front` | `Front Mass Distribution` 45% → 0.45 |
| `wheelbase_m` | `Wheelbase` 3000 mm → 3.0 m |
| `cog_height_m` | 元表に無し。F1推定 0.30 m（点質量モデルで使用しないが将来拡張用）/ GT 0.42 m |
| `cda` | `abs(CD)*Frontal Area` = 1.2*1 = 1.2 (GT は 0.68) |
| `cl` | `Lift Coefficient CL` = -4.8 (GT -1.85) |
| `tire_mu_x` | `Longitudinal Friction Coefficient` = 2.0 (GT 1.65) |
| `tire_mu_y` | `Lateral Friction Coefficient` = 2.0 (GT 1.70) |
| `engine_power_factor` | `Power Factor Multiplier` = 1.0 (GT 0.92) |
| `final_drive` | `Final Gear Reduction` = 7.0 (GT 3.85) |

- `f1.json` torque_curve: 元18点から曲線形状を保ち 10点に間引き (indices 0,2,4,6,8,10,12,14,16,17)
- `gt.json` torque_curve: 同一元データを GT3 クラスへスケール（1245 kg, 低空力、低μ）し 10点で再構成（2000 to 7000 rpm, peak 550 Nm）
- encoding: `utf-8`, `ensure_ascii=False`, indent 2

## Tracks (`data/tracks/`)

- 元ファイル: `Spa-Francorchamps.xlsx` / `Autodromo Nazionale Monza.xlsx` / `Donington Park.xlsx`
- 各 `Info` (Closed/Forward) + `Shape` (Type/Section Length/Corner Radius) + `Elevation`/`Banking`/`Grip Factors`/`Sectors`
- 変換: OpenTRACK.m / OpenTRACK.py の shape-data 経路を再実装
  - `mesh_size` 1 to 5 m（spa 2.0 m, monza 3.0 m, donington 2.5 m）
  - Pchip で `curv`=type/R を 1 m刻みに補間、Elevation/Banking は線形補間
  - Heading = cumsum(dx*curv), 閉ループは `dh` 接線補正 + `DX/DY/DZ` 閉合補正
  - 生成 `points:[{s,x,y,z,curv}]` 閉ループ centerline、s は 0→L 単調、`closed_loop:true`
- 代表長: `spa.json` `length_m=6953.611`（元 Shape 合計 6953.611 m。公式 7004 m に対し 0.73% 差で ±1% 以内）
- `monza.json` 5755.122 m, `donington.json` 3942.045 m

注: 上記 3 コースの数値は centerline 由来。2026-09 の racing 変換後、デフォルト `X.json` は racing ラインとなり、centerline は `X_centerline.json` に退避。長さは下表が最新。

## Suzuka 2026-09, All Tracks Racing vs Centerline (2026-09 racing-line conversion)

`882116a` の Origin 節は不変、以下は 2026-09 追記を全コースに拡張。2026-09-12 の変換で、全 8 コースについて `X.json` が racing ライン (out-in-out, `optimize_centerline` による最小曲率) に置換され、元 centerline は `X_centerline.json` (` (コース中心線)` 付) に退避した。命名: plain = racing default, ` (コース中心線)` = original annotated.

長さは実行時に各 JSON の `length_m` を読むこと。決してハードコードしない。下表の丸めは可読用、括弧内がファイル内の正確値。

検証は `python -c "import json,pathlib; print(json.loads(pathlib.Path('data/tracks/spa.json').read_text(encoding='utf-8'))['length_m'])"` のように行う。

## Shape Verification 2026-09-13

This section records full shape verification performed on 2026-09-13. All lengths were read at runtime from `data/tracks/*.json:length_m`, never hard coded. Verification code is:

```bash
python3 - << 'PY'
import json, pathlib
for p in sorted(pathlib.Path("data/tracks").glob("*.json")):
    d=json.loads(p.read_text(encoding="utf-8"))
    print(p.name, d["length_m"], d.get("meta",{}).get("fia_status","-"))
PY
```

### Method

1. Load `length_m` and `meta` at runtime from each JSON.
2. Compare `length_m` against FIA or official nominal `L_FIA`: `delta_pct = (length_m - L_FIA) / L_FIA * 100%`.
3. Apply tolerance `+-1%`. If `abs(delta_pct) <= 1%` then `fia_status` is `VERIFIED`, otherwise `FAIL`. The `fia_status` string is stored in `meta.fia_status` for annotated tracks and shown in the table column `fia_status`.
4. Check `zone` persistence, `closed_loop true`, monotonic `s`, and `source` provenance.
5. Diagnose curvature: `Rmin = 1 / max(|curv|)`, report `Rmin` for south.

FIA nominals used: Spa 7004 m, Monza 5793 m, Suzuka 5807 m, Donington GP 4020 m, National 3149 m (alt 3186 m quoted for reference). Other local tracks (sugo_west, suzuka_south, test, asete) have no FIA nominal, shown as `-`, and `fia_status` is `N/A`.

### Donington Park note

`donington.json` 3941.689 m and `donington_centerline.json` 3942.045 m are both `FAIL` against GP 4020 m. Delta is `-1.95%` (racing `-78.31 m`) and `-1.94%` (centerline `-77.96 m`). Layout is National derived from `Donington Park.xlsx` shape data, not GP. The annotation was added as `meta.fia_status = "FAIL -1.95% (National 3942m, not GP4020)"`, with `meta.fia_reference_m = 4020`, `meta.layout = "National"`, and `meta.recommended_action` pointing to `AgentDoc/docs/donington_decision.md` Option B. The files are frozen, no geometry was mutated, see `AgentDoc/docs/donington_retrace_followup.md` for the deferred GP retrace. Inside tolerance check `fia_status` is `FAIL`, honest gap, not a silent fix.

### Suzuka South note

`suzuka_south_centerline.json` 1264.00 m and `suzuka_south.json` 1263.89 m are synthetic approximations, not survey grade. Source is manual PDF trace of official `map02.gif` 481x221 via 11 point control plus west hairpin and S curves. Redigitized with 11 corner breakdown, georef 34.8395,136.5395, zone 6, scaled to 1264 m. Pre fix curvature spike was `5.14` (R0.19 kink joint), capped to `0.3` with xy 3 point average smoothing, DATA SIDE only. Post fix `Rmin_center_m` is `8.4` m and `Rmin_racing_m` is `25.3` m (hairpin expands from 8.3 to about 12.9 via racing optimization, see `meta.south_phase`). S curves have three apexes, the tightest radius is 8.39 m at 656.3 m (0.519 L). Peaks counted at threshold 0.02 are 4 at 12.3, 596.7, 621.9, 656.3 m. Record honestly as synthetic approximation, do not treat as official. `fia_status` is `N/A` (no FIA yardstick), `synthetic_approximation_honesty` block in meta documents this.

### Donington & FIA Scaling Decisions (DEFAULT done)

Two decisions were resolved and are now marked DEFAULT done, both keep originals frozen.

**Donington:** annotated as `FAIL` and frozen, follow up scaffold is `AgentDoc/docs/donington_retrace_followup.md`. No track was rewritten, only `meta.fia_status` annotation plus `recommended_action`. The retrace task is scaffold only, deferred, with Overpass 68 way precedent and estimate 1 to 2 days. See `AgentDoc/docs/donington_decision.md` Option C DEFAULT and `AgentDoc/docs/donington_retrace_followup.md`.

**FIA scaling:** scaling was approved as YES to opt in variants. Originals remain frozen, no original `data/tracks/*.json` was overwritten. Instead `scripts/fia_scale.py` produced `*_scaled.json` opt in siblings:

- `spa_scaled.json` 7003.6375 m and `spa_centerline_scaled.json` 7004.0038 m (factor 1.007247, FIA 7004 m)
- `monza_scaled.json` 5792.0751 m and `monza_centerline_scaled.json` 5793.0137 m (factor 1.006584, FIA 5793 m)
- `suzuka_scaled.json` 5800.9050 m and `suzuka_centerline_scaled.json` 5806.9983 m (factor 1.000275, FIA 5807 m)

Method is deterministic numpy only, `x,y,s *= f`, `curv /= f`, `length_m *= f`, with `meta.scaled_from` and `meta.fia_scaling_factor` recorded. Centerline scaled hits 7004.00, 5793.01, 5807.00 within rounding, racing scaled preserves the racing delta (for example spa racing 7003.64 vs 7004.00 is -0.36 m). See `AgentDoc/docs/fia_scaling_decision.md` Appendix A. `fia_status` for all six scaled files is `VERIFIED` within +-1%.

### Track table (22 files: 16 core + 6 scaled opt-in)

Lengths are read at runtime, never hard coded. The 16 core covers spa, monza, donington, suzuka, sugo_west, suzuka_south, test, asete each with centerline, plus 6 scaled opt in variants listed above. Rounding is for reading, exact values are authoritative via `length_m`.

| name | length_m | FIA nominal | delta% | fia_status | source | zone |
|---|---|---|---|---|---|---|
| `spa.json` | 6953.2473 m (6953.2473096721205 in file) | 7004 m | -0.725% | VERIFIED | `Spa-Francorchamps.xlsx` shape-data via OpenTRACK reimpl, then `optimize_centerline` from `spa_centerline.json` | - |
| `spa_centerline.json` | 6953.6110 m (6953.611 in file) | 7004 m | -0.719% | VERIFIED | `Spa-Francorchamps.xlsx` shape-data, Pchip curv, mesh 2.0 m, closed_loop true | - |
| `spa_scaled.json` | 7003.6375 m (7003.637492925314 in file) | 7004 m | -0.005% | VERIFIED | `spa.json` scaled by 1.007247 via `scripts/fia_scale.py`, `meta.scaled_from spa.json`, `meta.fia_scaling_factor 1.007247` | - |
| `spa_centerline_scaled.json` | 7004.0038 m (7004.003818917 in file) | 7004 m | +0.000% | VERIFIED | `spa_centerline.json` scaled by 1.007247, `meta.scaled_from spa_centerline.json` | - |
| `monza.json` | 5754.1895 m (5754.189477637658 in file) | 5793 m | -0.670% | VERIFIED | `Autodromo Nazionale Monza.xlsx` shape-data, then `optimize_centerline` from `monza_centerline.json` | - |
| `monza_centerline.json` | 5755.1220 m (5755.122 in file) | 5793 m | -0.654% | VERIFIED | `Autodromo Nazionale Monza.xlsx` shape-data, mesh 3.0 m | - |
| `monza_scaled.json` | 5792.0751 m (5792.0750611584235 in file) | 5793 m | -0.016% | VERIFIED | `monza.json` scaled by 1.006584, `meta.scaled_from monza.json` | - |
| `monza_centerline_scaled.json` | 5793.0137 m (5793.013723248 in file) | 5793 m | +0.000% | VERIFIED | `monza_centerline.json` scaled by 1.006584 | - |
| `suzuka.json` | 5799.3102 m (5799.310206257777 in file) | 5807 m | -0.132% | VERIFIED | Overpass 68-way stitch, then `optimize_centerline` from `suzuka_centerline.json` (half_width 6.0, iters 200, margin 0.5) | 6 |
| `suzuka_centerline.json` | 5805.4018 m (5805.401834506836 in file) | 5807 m | -0.028% | VERIFIED | Overpass API 0.7.62.11, 68 `<way>` elements fetched 2026-09-12T13:09:52Z | 6 |
| `suzuka_scaled.json` | 5800.9050 m (5800.9050165644985 in file) | 5807 m | -0.105% | VERIFIED | `suzuka.json` scaled by 1.000275 | 6 |
| `suzuka_centerline_scaled.json` | 5806.9983 m (5806.998320011326 in file) | 5807 m | -0.000% | VERIFIED | `suzuka_centerline.json` scaled by 1.000275 | 6 |
| `donington.json` | 3941.6890 m (3941.6889565405927 in file) | 4020 m | -1.948% | FAIL | `Donington Park.xlsx` shape-data, then `optimize_centerline` from `donington_centerline.json`, `meta.fia_status FAIL -1.95% (National 3942m, not GP4020)` | - |
| `donington_centerline.json` | 3942.0450 m (3942.045 in file) | 4020 m | -1.939% | FAIL | `Donington Park.xlsx` shape-data, mesh 2.5 m, `meta.fia_status FAIL -1.95%` | - |
| `sugo_west.json` | 980.0141 m (980.014127010978 in file) | - | - | N/A | OSM way/573824373, then `optimize_centerline` from `sugo_west_centerline.json`, zone 10 | 10 |
| `sugo_west_centerline.json` | 982.1725 m (982.1724813542529 in file) | - | - | N/A | OSM way/573824373 single way, raw 950.9 m scaled by 1.03479 to 982.17 m, zone 10 | 10 |
| `suzuka_south.json` | 1263.8948 m (1263.8947731937433 in file) | - | - | N/A | stadium-synthetic trace, then `optimize_centerline` from `suzuka_south_centerline.json`, zone 6, 11-corner synthetic `Rmin_center 8.4` `Rmin_racing 25.3` | 6 |
| `suzuka_south_centerline.json` | 1264.0001 m (1264.0001224736939 in file) | - | - | N/A | stadium area synthetic trace, manual PDF trace 11-corner, capped max_curv 0.3 + xy 3pt avg for R0.19 kink, `Rmin 8.4` | 6 |
| `test.json` | 643.8715 m (643.8714810957653 in file) | - | - | N/A | local test loop, `optimize_centerline` from `test_centerline.json`, half_width 4.0, margin 0.5 | 7 |
| `test_centerline.json` | 643.9270 m (643.9269503454034 in file) | - | - | N/A | local test loop, creator_mode dxf | 7 |
| `asete.json` | 2058.9629 m (2058.962930076211 in file) | - | - | N/A | local asete, `optimize_centerline` from `asete_centerline.json`, half_width 5.0, margin 0.5 | - |
| `asete_centerline.json` | 2063.2221 m (2063.222092305863 in file) | - | - | N/A | local asete, creator_mode dxf | - |

Values were verified at runtime via `python -c "import json,pathlib; print(json.loads(pathlib.Path('data/tracks/spa_scaled.json').read_text(encoding='utf-8'))['length_m'])"` etc. For core 16, scaling deltas are small (F1 shape-data gains under 1 m). For opt-in scaled, `fia_status` is `VERIFIED` and `meta.fia_scaling_factor` documents the factor.

Legacy alias: `suzuka_racing.json` (5799.3102 m) was byte-identical to `suzuka.json` and is now superseded by plain `suzuka.json`, not a separate course.

Optim params (from `src/openlapexe/curvature_opt.py::optimize_centerline`, objective sum kappa squared times ds, projection `|c-mid| <= half_width - 0.5`): F1 spa/monza half_width 6.0, donington 5.5, suzuka 6.0, sugo_west 4.5, suzuka_south 5.0, test 4.0, asete 5.0, width_margin 0.5 everywhere, iters 60 to 200 (suzuka 200, monza 100, others 60). See `AgentDoc/docs/racing_lines_all.md` for the full method and per-track table.

Notes, honest provenance:

- suzuka: Overpass API 0.7.62.11, 68 `<way>` elements fetched 2026-09-12T13:09:52Z, bounds Suzuka Circuit surroundings, `data/tracks/suzuka.json` built with zone 6, `overpass_raw.xml` kept as raw source. Stitched centerline, racing via min-curvature, delta -6.09 m honest.
- sugo_west: OSM way/573824373 single way, raw length 950.9 m, scaled by 1.03479 to 982.17 m to match known west course, then racing 980.01 m. Record honestly as scaled estimate, not measured. Zone 10.
- suzuka_south: stadium area synthetic trace, not survey grade, 1263.99 m centerline, 1259.30 m racing, zone 6. Record honestly as synthetic approximation, do not treat as official. Pre-fix R0.19 kink (curv 5.14) capped to 0.3 plus xy 3-pt avg, DATA-SIDE only. `Rmin` center 8.4 m versus racing 25.3 m documents hairpin expansion.
- F1 spa/monza/donington: gains are small because shape-data centerlines already follow radius-based type/R. Expect deltas under 1 m, which is correct, not a failure.

Additional vehicles added 2026-09 (not tracks, kept for completeness):

| name | spec | provenance link |
|---|---|---|
| `gt500_suzuka.json` | M 1100 kg fallback (1245 + 0 + 0 = 1245 -> fallback 1100) | `AgentDoc/reference/gt500_suzuka_bop_calc.md` + `data/vehicles/gt500_suzuka.json` provenance, Q2 2024 1'43.143 / 2025 1'45.377 |
| `rental_gx270.json` | 185 kg total incl driver, Honda GX270 8.5PS rental kart | `data/vehicles/rental_gx270.json` provenance |
| `fs125_x30.json` | 150 kg total incl driver, IAME X30 125cc 28PS racing kart | `data/vehicles/fs125_x30.json` provenance |

Laptimes: do not copy numbers here. See `data/reference/verification_report_2026-09.json` and `AgentDoc/docs/accuracy_suzuka_2026-09.md` (and its new appendix). The parallel test agent refreshes those.

Validation:

```bash
pytest tests/test_suzuka_tracks.py tests/test_gt500_suzuka.py tests/test_kart_vehicles.py tests/test_data_schema.py -q
git diff -- data/vehicles/f1.json data/tracks/spa.json  # empty for frozen, but spa.json is now racing, check centerline instead: git diff -- data/tracks/spa_centerline.json
python3 - << 'PY'
import json, pathlib, glob
for p in sorted(glob.glob("data/tracks/*.json")):
    d=json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    print(p, d["length_m"], d["name"])
PY
# shape verification check
python3 - << 'PY'
import json, pathlib
pairs=[("data/tracks/spa.json",7004),("data/tracks/spa_centerline_scaled.json",7004),("data/tracks/donington.json",4020)]
for p,fia in pairs:
    cur=json.loads(pathlib.Path(p).read_text())["length_m"]
    print(p, cur, f"{(cur-fia)/fia*100:+.3f}%", "fia_status", json.loads(pathlib.Path(p).read_text()).get("meta",{}).get("fia_status","-"))
PY
```

