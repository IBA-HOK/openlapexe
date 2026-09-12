# data — 出典と生成メモ

## Origin

- Upstream: [mc12027/OpenLAP-Lap-Time-Simulator](https://github.com/mc12027/OpenLAP-Lap-Time-Simulator)
- Commit SHA: `882116a47b5c3c57d5806924b600cb7ffbb264e1` (abbr `882116a`) — `Update OpenVEHICLE.m` (Apr 2020)
- 取得方法: `/tmp` に `git clone --depth 1` で取得、`openpyxl`/`pandas` で読込
- License: GPLv3（本リポジトリは派生物として GPLv3 を継承）

## Vehicles (`data/vehicles/`)

- 元ファイル: `Formula 1.xlsx`（`Info` シート 47項目 + `Torque Curve` 18点 1000–18000 rpm）
- 圧縮: MVP 10項目に集約 + トルク表 8–12点

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
- `gt.json` torque_curve: 同一元データを GT3 クラスへスケール（1245 kg, 低空力、低μ）し 10点で再構成（2000–7000 rpm, peak 550 Nm）
- encoding: `utf-8`, `ensure_ascii=False`, indent 2

## Tracks (`data/tracks/`)

- 元ファイル: `Spa-Francorchamps.xlsx` / `Autodromo Nazionale Monza.xlsx` / `Donington Park.xlsx`
- 各 `Info` (Closed/Forward) + `Shape` (Type/Section Length/Corner Radius) + `Elevation`/`Banking`/`Grip Factors`/`Sectors`
- 変換: OpenTRACK.m / OpenTRACK.py の shape-data 経路を再実装
  - `mesh_size` 1–5 m（spa 2.0 m, monza 3.0 m, donington 2.5 m）
  - Pchip で `curv`=type/R を 1 m刻みに補間、Elevation/Banking は線形補間
  - Heading = cumsum(dx*curv), 閉ループは `dh` 接線補正 + `DX/DY/DZ` 閉合補正
  - 生成 `points:[{s,x,y,z,curv}]` 閉ループ centerline、s は 0→L 単調、`closed_loop:true`
- 代表長: `spa.json` `length_m=6953.611`（元 Shape 合計 6953.611 m。公式 7004 m に対し 0.73% 差で ±1% 以内）
- `monza.json` 5755.122 m, `donington.json` 3942.045 m

## Validation

```bash
pytest tests/test_data_schema.py -q
python -c "import json,pathlib; print(json.loads(pathlib.Path('data/vehicles/f1.json').read_text(encoding='utf-8'))['mass_kg'])"
```

- `scipy`/`matplotlib` は生成時のみ `/tmp` で利用し、`requirements.txt` には追加しない（`numpy` のみ維持）。
- `app.py` の SECTION マーカーは未改変（`data/` + `tests/` のみ追加）。

## Repro

```bash
git clone --depth 1 https://github.com/mc12027/OpenLAP-Lap-Time-Simulator /tmp/OpenLAP
git -C /tmp/OpenLAP rev-parse HEAD  # 882116a47b5c3c57d5806924b600cb7ffbb264e1 を確認
python /tmp/gen_vehicles.py
python /tmp/gen_tracks2.py
```

## Suzuka 2026-09

追加データ。`882116a` の Origin 節は不変、以下は 2026-09 追記。

| name | length | source | zone | provenance link |
|---|---|---|---|---|
| suzuka | 5805.40 m (5805.4018 m in file) | Overpass 68 ways stitched | 6 | `data/reference/suzuka/overpass_raw.xml` |
| sugo_west | 982 m (982.17 m in file, 950.9 m x 1.03479 scaled) | OSM way/573824373 scaled 1.03479 from 950.9 m | 10 | `data/tracks/sugo_west.json` meta, OSM way/573824373 |
| suzuka_south | 1264 m (1263.99 m in file) | stadium-synthetic trace, synthetic approximation | 6 | `data/tracks/suzuka_south.json` meta, record honestly as synthetic |
| gt500_suzuka | M 1100 kg fallback (1245 + 0 + 0 = 1245 -> fallback 1100) | 2024 Suzuka Q2 1'43.143 / 2025 1'45.377 | - | `data/reference/gt500_suzuka_bop_calc.md` + `data/vehicles/gt500_suzuka.json` provenance |
| rental_gx270 | 185 kg total incl driver | Honda GX270 8.5PS rental kart | - | `data/vehicles/rental_gx270.json` provenance |
| fs125_x30 | 150 kg total incl driver | IAME X30 125cc 28PS racing kart | - | `data/vehicles/fs125_x30.json` provenance |

Notes:

- suzuka: Overpass API 0.7.62.11, 68 `<way>` elements fetched 2026-09-12T13:09:52Z, bounds Suzuka Circuit surroundings, `data/tracks/suzuka.json` built with zone 6, `overpass_raw.xml` kept as raw source. Stitched centerline, length 5805.40 m.
- sugo_west: OSM way/573824373 single way, raw length 950.9 m, scaled by 1.03479 to 982.17 m to match known west course. Record honestly as scaled estimate, not measured. Zone 10.
- suzuka_south: stadium area synthetic trace, not survey grade, 1263.99 m, zone 6. Record honestly as synthetic approximation, do not treat as official.
- gt500_suzuka: base 1245 kg (GT3 Generic), BoP 0 kg, SW 0 kg, arithmetic 1245, fallback 1100 kg applied per `provenance_type fallback estimate`. Q2 best times 2024 1'43.143 (Car 14) and 2025 1'45.377 (Car 16) from supergt.net Round5 Suzuka. Detail in `data/reference/gt500_suzuka_bop_calc.md`.
- rental_gx270 / fs125_x30: masses 185 kg and 150 kg total incl driver, single ratio direct drive, created 2026-09-12, provenance in JSON.

Validation:

```bash
pytest tests/test_suzuka_tracks.py tests/test_gt500_suzuka.py tests/test_kart_vehicles.py tests/test_data_schema.py -q
git diff -- data/vehicles/f1.json data/tracks/spa.json  # empty
```
