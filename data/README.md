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
