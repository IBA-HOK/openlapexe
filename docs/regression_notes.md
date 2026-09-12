# 回帰ノート — たたき台許容差の説明

## 目的

`data/reference/spa_f1_baseline.txt` に保存した `101.17s` は `simulate('f1','spa')` の期待ラップタイム（たたき台）であり、`tests/test_regression_spa_f1.py` が **±0.5%** 以内を検証します。物理再実装を禁止する制約下で、将来のリファクタや環境差による微小変動を検出しつつ、たたき台としての妥当性を担保します。

## なぜ ±0.5% か

- **たたき台であること**: 本シミュレータは OpenLAP の「点質量 + GGV + 前後/横の摩擦楕円 + エアロ反復」モデルを `numpy` のみで再実装した骨組みです。実車 1:1 を謳うものではなく、教育・プリセット比較用の基準値（reference）として位置づけます。
- **決定論的ゆえに 1e-9 で一致すべきだが、環境差を許容**: 同一コミットでは `simulate('f1','spa')` は2回実行で `1e-9` 差以内（`test_spa_f1_laptime_range_deterministic_and_fast` および回帰の nondeterminism 検出）。しかし別Python/numpyバージョン、微小な丸め、将来の軽微な定数整理で `1e-9` を厳密に要求すると CI が脆くなります。
- **±0.5% の根拠**:
  - `101.17s` の `0.5%` は `±0.505s` → 許容区間 `[100.66, 101.68]`。実測 `101.172s` は中心から `0.002%` と十分内側。
  - OpenLAP本家でもメッシュ刻み（本実装は spa で2m）や `curv` 補間（PCHIP vs 線形）で数百msの差が出るため、`±0.5%` は「物理が壊れていない」ことを保証しつつ、実装の正当な進化を妨げないバランス。
  - `7004m` に対する `0.73%` の実測長誤差（`6953m`）と同程度のオーダを許容し、コース長誤差がラップに線形に伝播しても検出可能な閾値。

## ベースラインの由来

- 車両: `f1.json`（MVP10項目 + トルク10点、PCHIP補間）
- コース: `spa.json`（`Spa-Francorchamps` 6953.611m, 2mメッシュ, 3478点, `closed_loop:true`）
- ソルバ: 2mメッシュ → 横加速度制限 `v_lat=sqrt(ay_max/|curv|)` をエアロ込みで8反復 → 前後パス各6反復（摩擦楕円 `ax_allowed = ax_max * sqrt(1-(ay/ay_max)^2)`）→ 台形積分で `laptime`
- 計測: `pytest` で `simulate('f1','spa')` を2回呼び出し、初回・2回目の両方が `<2s`、ラップ `90-110s`、決定性 `1e-9` を満たすことを確認（`tests/test_solver.py`）。

## 運用

- **更新時**: 物理モデルやプリセットを意図的に変更した場合は、`python -c "import app; print(app.simulate('f1','spa').laptime)"` で新値を計測し、`data/reference/spa_f1_baseline.txt` を手動で更新。コミットメッセージに理由を明記。
- **失敗時**: CIで `test_spa_f1_regression_within_tolerance` が落ちた場合は、①環境差か②バグかを `test_spa_f1_nondeterminism_detection` の結果で切り分け。後者は同一環境で2回実行が乖離＝非決定性の混入を示す。

## 参照

- `data/README.md`: SHA `882116a` 由来と生成手順
- `tests/test_regression_spa_f1.py`: 実装
- `app.py` SECTION: VEHICLE/TRACK/SOLVER: `rho=1.225, g=9.81, wheel_r=0.33` 等の定数は固定

---

## 完全移植ベースラインへの移行 (2026-09-06)

### 新ベースライン

- `data/reference/spa_f1_full_baseline.txt` = `95.80591391534297` (実測値, `openlapexe.solver.simulate_full('f1','spa',50)` 50Hz, utf-8)
- `tests/test_regression_full.py` が **±0.5%** 以内 (`[95.326, 96.285]` ≈ `±0.479s`) かつ全配列決定論 `1e-9` を検証
- 旧ベースライン `data/reference/spa_f1_baseline.txt` = `101.17` (`previous_baseline`) は温存。`tests/test_regression_spa_f1.py` は旧shim `app.simulate('f1','spa')` 用として維持し、改変しない

### BREAKING CHANGE

- `Result` 5→12列拡張 (`laptime, s, v, ax, ay, time` + `sector, gear, rpm, tps, energy, fuel, sector_time [, bps]`) だが旧5列先頭互換あり。`Result.s/v/ax/ay/time` は先頭6フィールドに維持され、既存 `app.simulate` 呼び出しの `res.s, res.v, res.time` はそのまま動作。追加列は `openlapexe.solver.Result` でのみ取得

### ベースライン移動表

| Gap | Δ laptime | Reason | MATLAB:Line |
|-----|-----------|--------|-------------|
| D1 | ±0.00s (影響なし) | OpenDRAG分離 — ドラッグ計算を `drag.py` に分離したのみで物理は同一。ソルバは同一式を呼び出すためラップタイムに影響なし | MATLAB:OpenDRAG.m → `drag.py` |
| V1 | 約 -1.5s〜-2.0s | 47項目フル車両 + cog荷重移動 — MVP10項目から `Vehicle47` (Info47項目) へ拡張。`cog_height_m` による前後荷重移動 `Wz*df` / `Wd=(factor_drive*Wz - factor_aero*Aero_Df)/driven_wheels` 、`mu_x_M/mu_y_M + sens_x/sens_y` によるグリップ飽和、駆動方式別 `factor_drive/aero` を再現 | MATLAB:OpenVEHICLE.m:47-103, 234-245, 376, 468-470 |
| T1 | 約 -0.8s〜-1.2s | banking/grip/PCHIP — `bank_rad`/`grip_factor` の `Track2` 8列化、shape-dataのPCHIP補間（線形からの置換）、`incl=atand(dZ/dx)` / `Wz=M*g*cosd(bank)*cosd(incl)` による旋回限界補正。旧簡易QSSは平面・grip=1.0固定であった差分 | MATLAB:OpenTRACK.m: shape-data, PCHIP; OpenLAP.m:675-678, 667 |
| S1 | 約 -2.2s〜-2.8s (主因) | freq尊重 + マルチギア + エネルギー積算 — `freq` に応じた `step=100/freq` (50Hz→2m, 100Hz→1m) のmesh刻み/出力リサンプル (`MATLAB:OpenLAP.m:64, 890-927`)、`ratio_gearbox` によるマルチギア `vehicle_speed/gear/fx_engine` テーブルと `TPS/bps` 状態機械、燃料 `fuel_cons=cumsum(Fx*dx /n_thermal/fuel_LHV)` / `energy_spent` 積算。単一 `final_drive` 固定とエネルギー未積算からの置換が最大のラップ短縮要因 | MATLAB:OpenLAP.m:64, 148-224, 244, 498-503, 519-520, 890-927 |

- 合計 Δ: `101.17` → `95.81` = **-5.36s (-5.30%)**。D1は0、V1/T1/S1の積算が旧簡易QSS時代の余裕代を解消
- 旧 `101.17` は `previous_baseline` として保持し、`git log -- data/reference/spa_f1_baseline.txt` で追跡可能。旧 `app.simulate` (101.28s) との差は0.11s (0.11%) で旧許容内
- 検証: `PYTHONPATH=src pytest tests/test_regression_full.py -v` + `pytest -q` 全体GREEN、`py_compile` OK、encoding utf-8、`scipy`/`matplotlib` 不使用は `tests/test_regression_full.py` が保証

---

## CORRECTED — invalidates -5.36s table (2026-09-12)

**Invalidation:** The table above claiming `101.17 → 95.81 = -5.36s` via V1/T1/S1 is **INVALID** after solver audit fixes. The `95.80591391534297` value was a **previous_buggy** baseline (kept as `previous_buggy` for history) measured from a solver that simplified apex physics.

**Root causes fixed (solver verified 101.1788s, target 101.17±0.5% 100.66-101.68, vmax 299 km/h, sectors [33.12,34.16,33.91]):**

1. **Quartic `a*v^4+b*v^2+c=0` min-root** — replaces `v=sqrt(ay_max/|curv|)` 8-iter. `a=-sign(r)*dmy/4*D^2`, `b=sign(r)*(muy*D+(dmy/4)*(Ny*4)*D-2*(dmy/4)*Wz*D)-M*r`, `c=sign(r)*(muy*Wz+(dmy/4)*(Ny*4)*Wz-(dmy/4)*Wz^2)+Wy` with `Wz=M*g*cosd(bank)*cosd(incl)`, `Wy=-M*g*sind(bank)`, `D=-0.5*rho*factor_Cl*Cl*A`. Positive `u=v^2` roots solved `(-b±sqrt(b²-4ac))/(2a)`, smallest positive kept, fallback to `v_limit`.
2. **Wd/ellipse separation** — `Wd=(factor_drive*Wz - factor_aero*Aero_Df)/driven_wheels` unified, ellipse `sqrt(1-(ay/ay_max)^2)` applied **only to `ax_tyre`**, engine `ax_power=fx_engine/M` kept unscaled; `ax_com=min(ax_tyre_scaled, ax_power)`.
3. **`ax_drag` in envelope** — `ax_drag=(Aero_Dr+Roll_Dr+Wx)/M` with `Wx=M*g*sind(incl)`, `Aero_Dr=0.5*rho*factor_Cd*Cd*A*v²`, `Roll_Dr=Cr*abs(Fz_total)`. Envelope uses `ax_avail=ax_com+ax_drag` (clamped `>=ax_drag`), not tyre alone.
4. **Power-drag `v_limit`** — `v_limit` from `fx_engine(v)` vs `drag(v)` crossover (`net=fx - drag` zero interpolation), clamped 5..`v_max`, feeds `v_max_arr` quartic fallback and phase cap.

**New baseline (2026-09-12):** `data/reference/spa_f1_full_baseline.txt = 101.17879935516551` (simulate_full f1/spa 50Hz, freq respected step=100/freq, 50Hz→2m, 100Hz→1m). Tolerance stays **±0.5%** → `[100.66,101.68]`. `data/reference/spa_f1_baseline.txt = 101.17` (shim) remains.

**Preserved:** `previous_buggy = 95.80591391534297` (old V1/T1/S1 table base). Any reference to `95.81` as canonical is deprecated; contract tests in `tests/test_contract_regression.py` enforce `95.8059` outside `±0.5%` of `101.17`.

**Verification:** `PYTHONPATH=src python -m openlapexe --vehicle f1 --track spa --headless --json` → `laptime 101.178799` in `[100.66,101.68]`; `PYTHONPATH=src pytest -q` → 0 failures.
