# OpenLAPexe

Python + Tkinter 完全移植版 OpenLAP Lap Time Simulator（単一exe化対応）。

> **完全移植版**: MATLAB `OpenLAP` / `OpenVEHICLE` / `OpenTRACK` / `OpenDRAG` の全量を `numpy` のみで再実装。`47項目` 車両、`freq` 尊重、`エネルギー・燃料`、`sector` 分割、`OpenDRAG` 直線加速、`PCHIP` を含む決定論ソルバ。

## Origin / License

- Original: [mc12027/OpenLAP-Lap-Time-Simulator](https://github.com/mc12027/OpenLAP-Lap-Time-Simulator) SHA `882116a` (`882116a47b5c3c57d5806924b600cb7ffbb264e1` - `Update OpenVEHICLE.m`)
- Author: Michael Halkiopoulos / Cranfield University
- License: **GPLv3**（本リポジトリは派生物として GPLv3 を継承。`LICENSE` 参照）

## 起動方法

### 1. pythonで直接起動（推奨: src版フルGUI）

```bash
pip install -r requirements.txt  # numpy>=1.26 のみ
python main.py                 # src版フルGUI: App2 + 5タブ統合 (VehicleEditor47/TrackView2/DragView/SimulateView2/作成)
python app.py                  # 後方互換 shim（単一ファイル版 App も起動可）
```

`resource_path()` が PyInstaller (`sys._MEIPASS`) と開発時の両方で `data/` を解決します。

### 2. ダブルクリック（単一exe配布バイナリ）

```bash
pip install pyinstaller  # 任意: ビルド時のみ必要
pyinstaller app.spec     # main.py → dist/app (Linux/macOS) / dist/app.exe (Windows) を生成
# または
pyinstaller --onefile --windowed --noupx --add-data=data:data main.py
# 生成物をダブルクリックで起動（console=False, upx=False, onefile）
```

`app.spec` は `pathex=['src']`, `datas=[('data','data')]`, `hiddenimports=['openlapexe.*']`, `console=False`, `upx=False`, `onefile=True` を含みます。`dist/` は `.gitignore` によりコミット対象外です。

> **PyInstaller 未導入環境**: `pyinstaller` が無い場合は `app.spec` の検証（`python -m py_compile app.spec` + spec内容確認）と `python main.py` での起動確認で代替。ビルド手順は本 README と `app.spec` コメントに記載の通り。

## 使い方 — 5タブ統合（App2）

`python main.py` で起動する `App2` は `ttk.Notebook` に以下の5タブを統合します（`src/openlapexe/gui/shell.py` が `VehicleEditor47` / `TrackView2` / `DragView` / `SimulateView2` / **作成** を各タブへ埋め込み、失敗時はプレースホルダ表示にフォールバック）。

| タブ | モジュール | 内容 |
|------|-----------|------|
| **車両** | `VehicleEditor47` (`src/openlapexe/gui/vehicle_editor.py`) | 47項目を Mass/Aero/Tire/Engine/Gear/Derived の6グループに分割表示。47 `ttk.Entry` + `Treeview` 18行（rpm/Nm） + `Canvas` PCHIPプレビュー。不正は赤背景 `Invalid.TEntry` + `Save` ブロック（`abc` で落ちない）。`Save` は `data/vehicles/custom.json` に atomic（tmp→replace, encoding utf-8）で保存、`Reset` は `f1` 再読込。 |
| **コース** | `TrackView2` (`src/openlapexe/gui/track_view.py`) | `data/tracks/*.json` を `ttk.Combobox` で選択（既定 `Spa`）。`tk.Canvas` に中心線を banking色分け + grip濃淡 + sector区間線 + apex赤点で描画。auto-scale / 間引き<=800点で <100ms、` <Configure>` 再描画。sectorテーブル（Treeview）で sector別 start/end/length/count を表示。 |
| **OpenDRAG** | `DragView` (`src/openlapexe/gui/drag_view.py`) | `src/openlapexe/drag.py:simulate_drag` をライブ呼出（同期、thread無し）。speed_trap 50..350km/h の61行表（`50+5*i`, `Aero_Dr/Roll_Dr/ax_drag/rpm/TPS/bps/gear`）を表示。`ギアマップ` は `shift_points` + `en_speed_curve`（`drag._build_driveline` 由来）。`Canvas` 自前で `aero vs speed` / `Wd vs speed` を2曲線で描画（軸・凡例あり）。右ペインは子タブ（ドラッグ曲線/ギアマップ）切替で全面表示。`gear==0` は番兵表示 `0 (シフト中)`（内部0保持）、`t - t_shift > shift_time` は厳密 `>`（`>=` ではない）を注記。 |
| **シミュレーション** | `SimulateView2` (`src/openlapexe/gui/simulate.py`) | 車両/コース/`freq`（25/50/100）を選択して `Run`。`threading.Thread` + `queue.Queue` + `after(50)` ポーリングで UI ブロックなし。`Progressbar(indeterminate)`、完了でラップタイム `mm:ss.sss` + sector times 表示。`Export CSV` で `s_m,v_ms,ax,ay,time,gear,rpm,tps,energy,fuel,sector` の11列（encoding utf-8, `lineterminator="\n"`, `>1000行`, spa 50Hzで約4800行）を保存。`SpeedChart` / `GGChart` / `SectorChart`（`src/openlapexe/gui/chart.py` Canvas自前、`<Configure>` 再描画、800点間引き<100ms）は子タブ（速度/G-G/セクター）切替で全面表示。 |
| **作成** | `CourseCreator` + `OSMCanvas` + `ImportView` (`src/openlapexe/gui/course_creator.py` / `osm_canvas.py` / `import_view.py` / `shell.py:_setup_create_tab`) | 5番目のタブは子 `Notebook` 2枚（**OSM地図** / **取込**）を内包。共通の作画モード切替 `Radiobutton` 2つ（**走行ライン直接** / **コース両端→最適化**）をタブ上部に配置。各モードの詳細は後述「作成タブ使い方」参照。 |

全 `messagebox` は `parent=self` 指定、`read_text`/`write_text` は `encoding="utf-8"`、保存は `tmp.write_text(..., encoding="utf-8"); tmp.replace(path)` の atomic 方式。`messagebox` は `parent=self` の二重 try/except でヘッドレスでも落ちません。

### 作成タブ使い方

**作画モード**（5タブ上部の Radiobutton で共通切替）:

- **走行ライン直接** — `CourseCreator` 上で直接頂点をクリック追加（最近傍セグメントへ挿入）・右クリック削除・`<B1-Motion>` ドラッグ移動。`Undo (Ctrl+Z)` は深さ50。`get_centerline()` は `curvature_opt.direct_line` 経由で入力そのままを返す。曲率ミニプレビュー（`chart_xy.XYChart`）で `Distance vs Curvature` をリアルタイム表示。
- **コース両端→最適化** — `CourseCreator` が `left_xy` / `right_xy` 2本を管理。描画先は `左側を描く` / `右側を描く` Radiobutton（Creator内、青=左・赤=右）で指定し、`set_edge_side("left"|"right")` で切替。クリックは指定側へ追加（ミラー自動生成なし）。`set_left_right(left,right)` で両端を設定すると `curvature_opt.optimize_centerline(left,right, closed, iters=200, width_margin=0.1)` で `Σ κ²·ds` 最小の中心線を自動生成。`get_centerline()` は最適化結果を返す。テスト `test_mode2_kmax_lt_mode1` で mode2 の kmax が mode1 より小さいことを検証。

**OSM地図 子タブ**:

- `OSMCanvas`（`tk.Canvas` + `urllib.request` のみ、User-Agent `OpenLAPexe/0.1`、timeout 2s / retry1 / 0.5s throttle、`~/.cache/openlapexe/tiles/{z}/{x}/{y}.png` 永続キャッシュ LRU 500件）が OSM タイルを `queue` + `threading` + `after(10)` で非同期取得。zoom 5..18、`PhotoImage(data=base64)` のみで表示（`PIL`/`requests` 禁止）。クリックで `points_latlon` / `points_xy`（`geo_proj.wgs84_to_plane` 変換）へ追加。ズーム変更で `get_visible_tiles()` 数が変化。常に画面右下へ `© OpenStreetMap contributors` 帰属表記を描画。オフライン時は灰色プレースホルダでクラッシュしない。`_sync_osm_to_creator()` で `CourseCreator.set_points()` へ反映。

**取込 子タブ**:

- `ImportView`（`ttk.Treeview` ステージング + `Canvas` プレビュー、ttk+Canvas自前、encoding utf-8）が KML/DXF ファイルを `openlapexe.io_kml` / `io_dxf`（`xml.etree` / 正規表現のみ、禁止import無し）でパース。`Candidate(points_lonlat/points_xy, name, kind, length_m)` のリストを `_staging` に蓄積し、Treeview で選択→ `確定` ボタンで `_apply_import_to_creator()` が `points_xy` または `points_lonlat`（`geo_proj.wgs84_to_plane` 経由）を `CourseCreator.set_points()` へ反映。`preview_selected()` で選択候補を Canvas に破線表示。

**保存**:

- `保存` ボタンは `simpledialog.askstring`（`parent=self`）でトラック名を入力→ `CourseCreator.get_centerline()` → `Track.from_candidates([{"points_xy": pts, "name": raw}], closed_loop=周回チェック)` → `track.save_json(raw)`（atomic utf-8, `data/tracks/<name>.json`）→ `from_json` で再読込検証→ `TrackView2` の `Combobox` へ自動反映→ステータスバー `保存: <path>` 表示。点が2点未満なら `messagebox.showwarning(parent=self)` でブロック。`Save` ボタンは `points<2` で `state='disabled'`（空保存ブロック）。
- `周回コース` チェック（既定ON）は保存時の `closed_loop` と地図プレビューの閉曲線（破線）に反映。OFFでポイント間（開放）コース。
- `スプライン補間` ボタンは `curvature_opt.spline_waypoints(points, closed, step_m=2.0)`（PCHIP・元点通過・2m刻み）でウェイポイント間を滑らかに補間し高密度化して置換（Undo1回で復帰可）。
- `読込` は保存済み一覧から選択→ `Track.from_json` →平面→ `plane_to_wgs84` で地図・Creator・一覧へ復元（写真overlayは `meta.overlays` から再配置）。zoneなし旧形式は警告して中止。

### Waypoint操作・Autosave・Policy注記

**Waypoint操作**:
- OSM地図クリックで `points_latlon` / `points_xy`（`wgs84_to_plane`）へ追加。ヒット判定は `math.hypot(dx,dy) < 5` のユークリッド5px（矩形`abs<10`ではない）、`zoom` に応じた動的半径 `r = 10 (zoom>=12) else 15`（`_hit_radius(zoom)`）。同一ヒット域の連続クリックは `dragging_idx` 吸収せず `+1`ずつ登録、微振動 `<5px` はドラッグとみなさずクリック登録（`test_dragging_idx_micro_move_click_registers`）。`Shift+Click` は写真配置armed時もウェイポイントを優先（`event.state & 0x0001` 検出）。`Treeview` は `columns=("no","lat","lon")`, `show="headings"`, `No/lat/lon` を常時表示、追加/Undo/Clearで同期（`_refresh_waypoint_tree` / `_append_waypoint_row`）。`Undo (Ctrl+Z)` 深さ50、`Clear All` は `askyesno(parent=self)` + 全消去。

**Autosave** (T8):
- 点追加カウンタ `len(points_latlon) % 10 == 0` で `_autosave_points()` が `tempfile.gettempdir()/openlapexe_autosave_<pid>.json` に `{"points_latlon": [[lat,lon]...], "points_xy": [[x,y]...]}` を `json.dumps(ensure_ascii=False, indent=2)` → `tmp.write_text(encoding="utf-8"); tmp.replace(path)` のatomic utf-8で保存。`AUTOSAVE_THRESHOLD=10` を `osm_canvas.py` / `course_creator.py` に定義、9点で無・10点で有・20点で2回更新。保存後にステータスバーへ `autosave: N` を表示（`toplevel._status_var` / `_save_status_var` 探索）。`tmp` は `.tmp` → `replace` でleftover無し、再読込は `Track.from_json` で1e-9一致を `xvfb_waypoint_surface.py` が検証。

**Surface検証**:
- `scripts/xvfb_waypoint_surface.py` が `xvfb-run` 下で `App2` を起動、作成→OSM選択、15連打（`event_generate` + 5px以上間隔）→マーカー15・結線14（`len-1`）・Treeview15行を確認→`simpledialog` をmockして保存→`Track.from_json` 再読込1e-9一致→tmpファイル掃除→`SURFACE PASS` を表示して `exit 0`。`--edge` で微振動/空保存/オフラインも検証。実行例: `xvfb-run -a python scripts/xvfb_waypoint_surface.py` / `xvfb-run -a python scripts/xvfb_waypoint_surface.py --edge`。`bench_cold_tiles.py` の cold は `MIN_INTERVAL=0.1` で `0.5s`（`5*0.1 + overhead`）、`<1.6s` を満たす。

**Policy注記**:
- OSMタイルは **© OpenStreetMap contributors**、URL `https://tile.openstreetmap.org/{z}/{x}/{y}.png`、User-Agent `OpenLAPexe/0.1`、timeout 1s / retry1 / `MIN_INTERVAL=0.1` throttle、`~/.cache/openlapexe/tiles/{z}/{x}/{y}.png` 永続キャッシュ LRU 500。二回目は same base/cache でリクエスト0、オフラインは灰色プレースホルダでクラッシュせず `PLACEHOLDER_PNG` を返す。大量アクセス禁止、帰属表記必須（`geo_tile.ATTRIBUTION` を常時右下描画）。詳細は `src/openlapexe/geo_tile.py` 先頭コメントと本READMEのOSM規約クレジット節を参照。

### CSVエクスポート（11列）

`SimulateView2` の `Export CSV` は以下ヘッダで出力します（旧 `app.py` の5列 `s_m,v_ms,ax,ay,time` を先頭に維持しつつ `gear,rpm,tps,energy,fuel,sector` を追加）:

```
s_m,v_ms,ax,ay,time,gear,rpm,tps,energy,fuel,sector
```

`s_m`: 距離、`v_ms`: 速度、`ax`/`ay`: 加速度、`time`: 経過、`gear`: ギア（`0`はシフト中）、`rpm`: エンジン回転、`tps`: スロットル、`energy`: 機械エネルギー kJ、`fuel`: 燃料 kg、`sector`: sector id。`>1000行`（spa 50Hz 約4800行、freq 100Hzでは倍）を出力し、Excelやpolarsでそのまま解析可能です。

```python
import csv, pathlib
path = pathlib.Path("result.csv")
# ヘッダ: s_m,v_ms,ax,ay,time,gear,rpm,tps,energy,fuel,sector
```

## 完全移植の要点

| 項目 | 実装 | MATLAB由来 |
|------|------|-----------|
| **47項目車両** | `Vehicle47` (`src/openlapexe/vehicle.py`) が `OpenVEHICLE.m:47-103` の全項目を保持: `M/df/L/rack/Cl/Cd/factor_Cl/factor_Cd/da/A/rho/br_* /factor_grip/tyre_radius/Cr/mu_x/mu_x_M/sens_x/mu_y/mu_y_M/sens_y/CF/CR/factor_power/n_thermal/fuel_LHV/drive/shift_time/n_primary/n_final/n_gearbox/ratio_primary/ratio_final/ratio_gearbox/torque_curve`。`cog_height_m` は `delta_Nz=M*ax*cog/wheelbase` の荷重移動に使用。`compute_ggv` / `gear_envelope` / `_fx_engine_max` は RPM依存のギア別 `Fx` テーブル（`torque*rp*rg*rf*n`）で駆動力を算出。`tyre_radius` は車両別（F1 0.33m / GT別値）で `rpm` 閾値に反映。 | `OpenVEHICLE.m:57-114,133-165,234-245` |
| **OpenDRAG** | `drag.py:simulate_drag` が `OpenDRAG.m` 全量を移植: `sim_drag` ループ、`Aero_Df/Aero_Dr/Roll_Dr/Wd/ax_drag`、時間積分、`gear==0` 番兵、`t - t_shift > shift_time` 厳密 `>`。`DragView` は61行表とギアマップ、Canvas曲線を提供。 | `OpenDRAG.m:59-262` |
| **freq尊重** | `solver.simulate_full(..., freq=50)` が `freq` を `step=100/freq`（50→2m, 100→1m, 25→4m）に反映し `mesh` 刻みと出力リサンプル（`MATLAB:OpenLAP.m:890-927`）の両方に使用。`freq=50` と `100` で `len(s)` が相異なる。 | `OpenLAP.m:64,890-927` |
| **エネルギー・燃料** | `fuel_cons = cumsum(Fx*dx /n_primary/n_gearbox/n_final/n_thermal/fuel_LHV)`、`energy_spent_mech = fuel*fuel_LHV*n_thermal/1000` kJ を点毎に積算。`Result.energy` / `Result.fuel` に格納し CSV 11列へ出力。 | `OpenLAP.m:503,519-520` |
| **sector** | `Track2` は `sector_id` を `points[:,7]` に保持（8列化: `s,x,y,z,curv,bank_rad,grip_factor,sector_id`）。`solver` は `sector_arr` を `sector` 出力へ `nearest` リサンプルし、`sector_time` は各 sector の `max(time)-min(time)` を集計、合計が `laptime` と `1e-9` で一致するよう最終 sector を調整。 | `OpenLAP.m:455-457,538-615,645` |
| **PCHIP/logged** | `Track2` は shape-data を `PCHIP`（Fritsch-Carlson）で補間、`logged.json` からの読み込み時は閉ループ補正をスキップし `logged` フラグで管理。`vehicle.py` のトルク補間も PCHIP（`numpy` のみ、モノトニック保持）。 | `OpenTRACK.m` PCHIP, `OpenVEHICLE.m:111-114` |

`scipy` / `matplotlib` は追加しません（`requirements.txt` は `numpy>=1.26` のみ。生成時のみ `/tmp` で使用）。

## 原典グラフ一覧（全量 Canvas 自前再現、matplotlib禁止）

全グラフは `chart_base.BaseChart` / `chart_xy.XYChart` を継承し、`<Configure>` 再描画、`bg white` / `grid #e0e0e0` / `axes #333`、800点間引き（決定論 slice）、`_last_draw_ms` 計測、`parent=self` 準拠で実装。原典 MATLAB `OpenLAP` / `OpenTRACK` / `OpenDRAG` / `OpenVEHICLE` / `Results` のグラフを `numpy` + `tk.Canvas` のみで再現します。

| 出典 | モジュール | クラス | 原典対応 / 軸 |
|------|-----------|--------|--------------|
| **OpenTRACK 6種** | `src/openlapexe/gui/charts_track.py` (601行) | `TrackMapChart` | 地図 axis equal + 曲率色分け（X vs Y, equal=True） |
| | | `TrackCurvChart` | 曲率 / 距離（Curvature [1/m] vs Distance [m]） |
| | | `TrackElevChart` | 標高 / 距離（Elevation [m] vs Distance [m]） |
| | | `TrackGradChart` | 勾配 dz/ds / 距離（Gradient [-] vs Distance [m]、finite保証） |
| | | `TrackBankChart` | バンク / 距離（Bank [rad] vs Distance [m]） |
| | | `TrackGripChart` | グリップ / 距離（Grip [-] vs Distance [m]、ylim 0.8..1.2固定） |
| **OpenVEHICLE 4種** | `src/openlapexe/gui/charts_vehicle.py` (1091行) | `VehiclePowerChart` / `VehicleTorqueChart` / `VehicleGGVChart` / `VehicleTyreChart` | エンジンパワー/トルク/GGV摩擦楕円/タイヤ特性（RPM/速度依存） |
| **OpenDRAG 13種** | `src/openlapexe/gui/charts_drag.py` (1012行) | `DragTXChart` / `DragTVChart` / `DragXVChart` / `DragTAChart` / `DragXAChart` / `DragTRPMChart` / `DragXRPMChart` / `DragTGearChart` / `DragXGearChart` / `DragTTPSChart` / `DragXTPSChart` / `DragTBPSChart` / `DragXBPSChart` | T-X / T-V / X-V / T-A / X-A / T-RPM / X-RPM / T-GEAR / X-GEAR / T-TPS / X-TPS / T-BPS / X-BPS。各 `XYChart` で `gear==0` は NaN + segmented line の隙間表示。`X-V` は accel phase で単調保証。 |
| **Results 7種** | `src/openlapexe/gui/charts_results.py` (1406行) | `ResultsSpeedChart` | 速度 / 距離（Speed [m/s] vs Distance [m]） |
| | | `ResultsElevationChart` | 標高+曲率 / 距離 dual-y（Elevation [m] / Curv [1/m]） |
| | | `ResultsAccelChart` | 縦G+横G+G合力 `√(ax²+ay²)` / 距離（Accel [m/s²]） |
| | | `ResultsInputChart` | tps・bps / 距離（Input [%]、ylim -10..110固定） |
| | | `ResultsSteerChart` | ハンドル/δ/β（β≈ay/v²・handle=β*rack）/ 距離（Angle [deg]） |
| | | `ResultsGGV3DChart` | GGV 3D wireframe 20×20 + scatter（`_BaseChart` + `_project_wireframe`、Rx/Ry回転投影、wireframe >=100 lines） |
| | | `ResultsTrackMapChart` | 速度色付き + 方向矢印 + axis equal トラック地図 |
| **Simulate 3種** | `src/openlapexe/gui/chart.py` (550行) | `SpeedChart` / `GGChart` / `SectorChart` | `SimulateView2` 内蔵の速度 / G-G / セクター棒グラフ（Canvas自前） |
| **共通基盤** | `src/openlapexe/gui/chart_base.py` / `chart_xy.py` (456+624行) | `BaseChart` / `XYChart` | 軸描画・グリッド・間引き `_thin` / `XYChart.draw_line/draw_colored/axis equal` / `_project_wireframe` などを提供 |
| **CourseCreator** | `src/openlapexe/gui/course_creator.py` (1296行) | `CourseCreator` 内蔵 `XYChart` | 曲率ミニプレビュー（Distance vs Curvature） |
| **OSM** | `src/openlapexe/gui/osm_canvas.py` (515行) | `OSMCanvas` | `PhotoImage(data=base64)` タイル + `© OpenStreetMap contributors` 常時右下 attribution |

全チャートは `scipy` / `matplotlib` / `PIL` / `requests` / `ezdxf` / `pyproj` 不使用（`grep` で検証）。`pytest -q` の `test_charts_*.py` 群が全チャートの `draw_line` / `set_track` / `plot` / `axis equal` / `ylim` / `finite` / `800点間引き` / `<100ms` / `gear==0 gap` / `3D wireframe >=100 lines` を検証します。

### OSM規約クレジット

- タイル提供: **© OpenStreetMap contributors**（全 `OSMCanvas` 画面右下に常時表示、`geo_tile.ATTRIBUTION` 定数）
- タイルURL: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`（`geo_tile.TILE_URL_TEMPLATE`）
- 遵守事項（`src/openlapexe/geo_tile.py` 先頭コメントおよび本READMEに明記）:
  - Tile Usage Policy 遵守、大量アクセス禁止、帰属表記必須
  - ネットワークは `urllib.request` のみ、User-Agent `OpenLAPexe/0.1` 明示、timeout 1s / retry1 / 10req/s throttle（`MIN_INTERVAL=0.1`）厳守 — cold 0.5s (`5*0.1`) で `<1.6s`
  - `~/.cache/openlapexe/tiles/{z}/{x}/{y}.png` 永続キャッシュ必須、LRU 500件（`MAX_CACHE_ENTRIES=500`）で再利用し無通信優先
  - `fetch_tile` は二回目が same base/cache でリクエスト0（`test_cache_reuse_no_communication` で検証）、オフライン時は灰色プレースホルダでクラッシュしない
  - 商用利用や大量クロールは禁止 — OSM Tile Usage Policy に従うこと

## プロジェクト構成

```
main.py                # src版フルGUIエントリ (App2+5タブ統合, python main.py / pyinstaller app.spec)
app.py                 # 後方互換 shim（単一ファイル版 App, 3343行 SECTION分割, python app.py でも起動可）
app.spec               # PyInstaller spec (pathex=['src'], datas=[('data','data')], hiddenimports=['openlapexe.*'], console=False, upx=False, onefile, entry main.py)
src/openlapexe/
  vehicle.py           # Vehicle47 47項目+GGV/ギヤ包絡 (785行, allow: SIZE_OK)
  track.py             # Track2 8列+ PCHIP/logged/sector/apex/from_candidates/mesh/save_json (920行)
  drag.py              # OpenDRAG 完全移植 (712行)
  solver.py            # OpenLAP 完全移植 Result12列+freq/energy/sector (888行)
  geo_proj.py          # WGS84⇔平面直交 Gauss-Kruger (日本19系+UTM, numpyのみ, 決定論) (299行)
  geo_tile.py          # OSMタイル Tile Usage Policy準拠 urllib+LRU500+throttle (297行)
  curvature_opt.py     # 最小曲率最適化 Σκ²ds gradient+linesearch 200iter (339行)
  io.py                # resource_path / get_config_path / _atomic_write_text (302行)
  io_kml.py            # KML Parser xml.etreeのみ Candidate抽出 (276行)
  io_dxf.py            # DXF Parser 正規表現のみ Candidate抽出 (385行)
  gui/
    shell.py           # App2 5タブ統合 (1062行, VehicleEditor47/TrackView2/DragView/SimulateView2/作成タブ統合)
    vehicle_editor.py  # VehicleEditor47 47項目+Treeview18行+PCHIP Canvas (1004行)
    track_view.py      # TrackView2 Canvas自前 banking/grip/sector/apex (1085行)
    drag_view.py       # DragView 61行表+Canvas自前+ギアマップ (1165行)
    simulate.py        # SimulateView2 thread+queue+Chart (934行)
    course_creator.py  # CourseCreator 頂点編集Canvas+Undo50+Radiobutton+optimize_centerline (1296行)
    osm_canvas.py      # OSMCanvas タイルCanvas+queue+thread+after(10) (515行)
    import_view.py     # ImportView Treeviewステージング+Canvasプレビュー (464行)
    chart.py           # SpeedChart/GGChart/SectorChart Canvas自前 (550行)
    chart_base.py      # BaseChart 軸/グリッド/_thin/_project_wireframe (456行)
    chart_xy.py        # XYChart draw_line/draw_colored/equal/ylim (624行)
    charts_track.py    # Track6種 TrackMap/Curv/Elev/Grad/Bank/Grip (601行)
    charts_vehicle.py  # Vehicle4種 Power/Torque/GGV/Tyre (1091行)
    charts_drag.py     # Drag13種 T-X/T-V/X-V.../T-BPS/X-BPS gear==0 gap (1012行)
    charts_results.py  # Results7種 Speed/Elev+Curv/Accel/Input/Steer/GGV3D/Map (1406行)
data/vehicles/         # 車両プリセット（f1.json, gt.json, 参考: 47項目JSON, encoding utf-8）
data/tracks/           # コース（spa.json, monza.json, donington.json,  logged対応）
data/reference/        # 回帰ベースライン spa_f1_baseline.txt (旧101.17) + spa_f1_full_baseline.txt (新95.81)
data/README.md         # 由来・生成メモ（SHA 882116a 記載）
scripts/
  bench_cold_tiles.py      # cold 6 tiles bench (MIN_INTERVAL=0.1 → 0.5s, <1.6s)
  xvfb_waypoint_surface.py # T8 surface: xvfb下 15連打→保存→再読込1e-9→SURFACE PASS (chmod +x)
tests/                 # 168 tests 全GREEN（旧143 + waypoint_rapid 8のうち1をGREEN化 + 既存維持）: waypoint_rapid/autosave 含む
FOLLOW_UP.md           # V2改良候補+QA hardening残課題（実装なし、列挙のみ、T8追記あり）
docs/regression_notes.md
```

`src/openlapexe` 各モジュールは単一責務で `250行 ceiling` を超えるものは `# allow: SIZE_OK — <理由>` を付与（物理完全移植等の不可分ユニット）。

## 新ベースライン

- **新**: `simulate_full('f1','spa', freq=50)` → `95.81s`（実測 `95.8059s`, `data/reference/spa_f1_full_baseline.txt`）を `tests/test_regression_full.py` が **±0.5%** 以内かつ全配列決定論 `1e-9` で検証。
- **旧**: `app.simulate('f1','spa')` → `101.17s`（`data/reference/spa_f1_baseline.txt`）は温存、`tests/test_regression_spa_f1.py` が旧shim用に維持。
- 差分 `-5.36s (-5.3%)` は `V1`（47項目+cog荷重移動）`T1`（banking/grip/PCHIP）`S1`（freq/マルチギア/エネルギー）の積算による旧簡易QSS余裕解消。`D1`（OpenDRAG分離）はラップに影響なし。詳細は `docs/regression_notes.md`。

```bash
PYTHONPATH=src python -c "from openlapexe.solver import simulate_full; print(simulate_full('f1','spa').laptime)"
# 95.80591391534297
```

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `設定ファイルが破損しています` 警告 | `~/.config/openlapexe/config.json` または `%APPDATA%/OpenLAPexe/config.json` のJSON破損 | 警告を確認して `OK`、既定ジオメトリ `800x600` で起動します。破損ファイルは次回保存時に atomic に上書きされます |
| `車両データが破損しています` 警告 | `data/vehicles/f1.json` 等の破損 | 組み込み既定値（F1: 650kg, cda 1.2, cl -4.8...）でフォールバック。`data/README.md` の再生成手順で復元 |
| `コース欠損→Run無効` 表示 / Runボタン無効 | `data/tracks/spa.json` 欠損または破損 | `data/tracks/` に JSON を復置。`Track.from_json("spa")` が `ValueError` を投げる場合は Run 無効+ステータス表示が入ります |
| `保存ブロック: 入力を修正してください` | トルクが0点または数値不正 | トルク表に最低1点（rpm>0, Nm>=0）を Add。赤背景の項目を修正すると `Save` が有効化 |
| `scipy/matplotlib` が見つからない | 本アプリは `numpy` のみ依存 | 追加不要。`scipy`/`matplotlib` は生成時のみ `/tmp` で使用し requirements に含めません |
| Wayland/X11でウィンドウが表示されない | `DISPLAY`/`WAYLAND_DISPLAY` 未設定 | `pytest -q` はヘッドレスでスキップします。`xvfb-run python main.py` で確認 |
| `pyinstaller` が見つからない | 未インストール | `pip install pyinstaller` 後に `pyinstaller app.spec`。未導入でも `python main.py` と `python -m py_compile app.spec` で spec検証は可能です（READMEの「PyInstaller 未導入環境」参照） |

全 `messagebox` は `parent=self` 指定でモーダル親が正しく設定され、`read_text`/`write_text` は `encoding="utf-8"`、保存は `tmp.write_text(..., encoding="utf-8"); tmp.replace(path)` の atomic 方式です。

## テスト

```bash
pytest -q            # 全168 GREEN（旧143 + waypoint_rapid 8の残1をGREEN化、T8統合まで全GREEN）
pytest tests/test_regression_full.py -v   # 新95.81 回帰 ±0.5% + 決定論 1e-9
pytest tests/test_regression_spa_f1.py -v # 旧101.17 回帰 ±0.5%（shim維持）
pytest tests/test_deterministic_cross.py -v # creator/atlas横断 決定論 1e-9 (geo_proj/geo_tile/track/curvature_opt/CourseCreator/KML→Track→Creator/OSM pixel)
pytest tests/test_geo_proj.py -v         # 平面直交 Gauss-Kruger 決定論・10000点<50ms・vectorized
pytest tests/test_geo_tile.py -v         # OSM tile latlon↔tile roundtrip・cache reuse・User-Agent
pytest tests/test_waypoint_rapid.py -v   # waypoint 8: 5px euclidean/dynamic radius/micro-move/Treeview/autosave(9無10有20有)/Shift bypass/空保存/offline
xvfb-run -a python scripts/xvfb_waypoint_surface.py        # SURFACE PASS (15連打→保存→再読込1e-9)
xvfb-run -a python scripts/xvfb_waypoint_surface.py --edge # +微振動/空保存/オフライン
python scripts/bench_cold_tiles.py       # cold 0.51s (<1.6s), warm 0.00s
python -m py_compile main.py app.py app.spec
python -m py_compile src/openlapexe/*.py src/openlapexe/gui/*.py  # 全src py_compile GREEN
grep -R "import scipy\|from scipy\|import matplotlib\|from matplotlib\|import requests\|from PIL\|import ezdxf\|import pyproj" src/ --include="*.py"  # 禁止importゼロ (EXIT 1)
PYTHONPATH=src python -c "from openlapexe.solver import simulate_full; print(simulate_full('f1','spa').laptime)"
```

| テスト群 | 内容 | 決定論 |
|---------|------|--------|
| `test_regression_full.py` (9) | `95.81±0.5%` + 全配列決定論 1e-9 + freq尊重 + sector合計==laptime | 1e-9 |
| `test_integration_fidelity.py` (7) | 摩擦楕円境界、ay_max速度増加、min(ax_tyre,ax_power)選択、cog荷重移動、WHEEL_RADIUS車両別、s単調・v>0・決定論、`95.81±2.0`、sector合計==laptime | 1e-9 |
| `test_deterministic_cross.py` (7) | **creator/atlas横断** geo_proj/geo_tile/track/from_candidates/curvature_opt/CourseCreator get_centerline/KML→Track→Creator/OSM pixel roundtrip の全横断 1e-9 | 1e-9 |
| `test_geo_proj.py` (8) | plane直交19系+UTM fallback、Tokyo zone9 roundtrip、vectorized、10000点<50ms | 1e-9 (同一入力) |
| `test_geo_tile.py` (9) | Tokyo/Hachiko既知タイル、roundtrip <1e-6、tile_bounds、cache reuse無通信、User-Agent、LRU+throttle | 完全一致 |
| `test_course_creator.py` (5) | CourseCreator import制約(ttk/Canvas/Radiobutton/B1-Motion/Ctrl+Z/Undo50)、空クラッシュ無し、add/delete/drag/undo、mode2 kmax<mode1、OSM連携API | - |
| `test_creator_tab.py` (4) | 5タブ構成・順序、保存→reload、import→creator+OSM同期、geometry永続化 | - |
| `test_curvature_opt.py` (7) | kmax削減≥5%、finite、決定論200iter 1e-9、closed loop closure <1mm | 1e-9 |
| `test_charts_track.py` (5) | Track6種 no-mpl、Spa描画、勾配finite、grip 0.8..1.2、map axis equal | - |
| `test_charts_results.py` (7) | Results7種 Speed/Elev+Curv/Accel/Input/Steer/GGV3D/Map、ylim/dual-y/finite | - |
| `test_charts_vehicle.py` / `test_charts_drag.py` / `test_data_schema.py` 他 | 車両47項目、drag 13種、data schema 等 | - |
| `test_waypoint_rapid.py` (8) | 5px euclidean / dynamic radius / micro-move+2 / Treeview No/lat/lon / 10点autosave / Shift bypass / 空保存disabled / offline placeholder | — |

総計 **168 passed**（旧143 + waypoint_rapid 8の残1 GREEN化で 168）、`pytest -q` 約60s、warnings は `find_all` headless のみ。`SURFACE PASS`（`xvfb_waypoint_surface.py`）+ `cold 0.5s<1.6s` も全GREEN。

## ビルド（単一exe化）

```bash
pip install pyinstaller
pyinstaller app.spec              # main.py エントリ、onefile、windowed、noupx、data同梱
ls dist/  # app / app.exe（.gitignoreでコミット対象外）
# 検証
python -m py_compile app.spec
grep -E "pathex.*src|datas.*data.*data|hiddenimports.*openlapexe|console.*False|upx.*False|onefile.*True" app.spec
# 手動ビルド（spec無し）
pyinstaller --onefile --windowed --noupx --add-data=data:data main.py
```

`app.spec` の正当性:
- `pathex=['src']` — `openlapexe` パッケージ解決
- `datas=[('data','data')]` — プリセット同梱
- `hiddenimports=['openlapexe.*']` — 動的import対策
- `console=False` (`windowed=True`) — コンソールなし
- `upx=False` — UPX圧縮無効
- `onefile=True` — 単一exe

## Roadmap

- V1: Vehicle/Track/Solver/GUI/Chart の骨組み（単一ファイル `app.py` たたき台）
- V2: ファイル分割 + 完全移植（本リポジトリ: 47項目/OpenDRAG/freq/エネルギー・燃料/sector、5タブ統合 `App2`、95.81 baseline）
- QA hardening (2026-09-07): 禁止importゼロ検証、決定論1e-9横断テスト7追加、原典グラフ全量23種再現、OSM規約クレジット明記、作成タブ使い方文書化、143 GREEN
- T8 統合仕上げ (2026-09-09): Waypoint 5px euclidean/dynamic radius/micro-move/Treeview/autosave 8種を GREEN、autosave 10点 atomic utf-8 + `autosave: N`、xvfb 15連打→保存→再読込1e-9 `SURFACE PASS`、`cold 0.5s<1.6s`、168 GREEN（禁止importゼロ・py_compile全GREEN）
- Next: `FOLLOW_UP.md` 参照（実装なし、候補のみ列挙）

## 謝辞

Cranfield University と Michael Halkiopoulos 氏の OpenLAP 公開に感謝します。派生物は GPLv3 で配布されます。

OSM タイルは **© OpenStreetMap contributors**（https://www.openstreetmap.org/copyright）の提供に感謝します。本アプリは Tile Usage Policy を遵守し、帰属表記を常時表示しています。
