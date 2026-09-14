# graph_placement.md — 原典グラフ群配置決定

- encoding: utf-8

## 概要
原典 `charts_results` / `charts_drag` / `charts_track` / `charts_vehicle` の4モジュール群を既存4タブの子Notebookへ組込む配置を記録。共通方針は **per-tab方式**（タブ1枚=グラフ1種、try/except+プレースホルダfallback）を採用。

## 方式選定: per-tab vs 分割Canvas/重ね描き
- **per-tab方式を選択**: 各グラフが独立した描画責務を持ち、タブ切替で全面表示させることでCanvas自前描画の負荷とレイアウト競合を回避。1タブ=1チャートは既存 `SimulateView2` の `chart_notebook`（速度/G-G/セクター）と `DragView` の `graph_notebook`（ドラッグ曲線/ギアマップ）の実績パターンに整合し、既存タブ順序・属性名を破壊せず拡張できる。
- **重ね描き/分割Canvasを不採用**: 単一Canvasに複数グラフを重ねると800点間引き・軸範囲・凡例が衝突し、`<Configure>`再描画で相互に干渉。分割CanvasはPaneサイズ依存でリサイズ時の再計算が複雑化する。per-tabは各チャートが `pack(fill=both, expand=True)` で独立にリサイズでき、テストでの子タブ数検証も明確になる。

## 4ビュー配置

### simulate.py — chart_notebook 3→9
- 維持: 速度 / G-G / セクター（順序固定、先頭3）
- 追加: 標高・曲率 / G合力 / TPS・BPS / ステア / GGV3D / トラックマップ（末尾6）
- 使用: `charts_results` の `ResultsElevationChart` / `ResultsAccelChart` / `ResultsInputChart` / `ResultsSteerChart` / `ResultsGGV3DChart` / `ResultsTrackMapChart`（`ResultsSpeedChart`は既存速度と重複のため不使用、既存SpeedChartを温存）
- fallback: 各 `ttk.Frame` に `ttk.Label("…(読込失敗)")` を pack、属性は None にフォールバック
- 更新: `simulate_full` 結果の `_poll` で `plot(res)` を全6チャートへ配信、 `_redraw_charts` に6名を追加

### drag_view.py — graph_notebook 2+13
- 維持: ドラッグ曲線 / ギアマップ（先頭2）
- 追加: T-X / T-V / X-V / T-A / X-A / T-RPM / X-RPM / T-GEAR / X-GEAR / T-TPS / X-TPS / T-BPS / X-BPS（13系列）
- 使用: `charts_drag` の `DragTXChart` … `DragXBPSChart`（gear系は NaN 隙間表示、X-Vは単調保証）
- fallback: 各タブ `try: Drag*Chart(tab).pack` `except: Label(読込失敗)`、既存aero/Wd Canvasは tab_curve 内で温存
- 更新: `_on_run` の simulate_drag 結果を13チャートへ `plot(result)`、 `_redraw_canvas` で `_redraw()` を13チャートへ伝播

### track_view.py — ミニマップ下に子Notebook 6タブ
- 配置: `canvas`（minimap、height 320、expand True）の直下に `graph_notebook`（expand True）を pack、末尾に既存 `sector_table` を残置（順序: 選択行 → minimap → 6タブグラフ → sectorテーブル）
- 追加: 地図 / 曲率 / 標高 / 勾配 / バンク / グリップ
- 使用: `charts_track` の `TrackMapChart` / `TrackCurvChart` / `TrackElevChart` / `TrackGradChart` / `TrackBankChart` / `TrackGripChart`（Track2の8列 s,x,y,z,curv,bank,grip,sector を利用、勾配は dz/ds finite保証、グリップ ylim 0.8..1.2 固定、地図は axis equal）
- fallback: 各タブ `try/except` + Label、track変更時 `_load_track` で `set_track(t)` を6チャートへ配信、 `_redraw` 終端で各_chart._redraw() を呼出
- 理由: minimapは既存描画（banking色分け+grip濃淡+sector境界+apex）と責務分離し、定量グラフ（曲率/標高/勾配/バンク/グリップ）は数値軸で拡大観察させたいため別Notebookで分離。ミニマップ下配置で視線が 地図俯瞰 → 数値推移 → sector表 と自然に流れる。

### vehicle_editor.py — トルク表下に子Notebook 4タブ
- 配置: `_build_torque_table` 直後に `_build_vehicle_graphs` で `graph_notebook` を pack（entries → torque Treeview(18行) → 4タブグラフ → PCHIPプレビュー → Save/Reset の順、トルク表の直下で既存PCHIPプレビューは温存）
- 追加: トルク・パワー / ギア / Fx包絡 / GGV
- 使用: `charts_vehicle` の `VehicleTorqueChart` / `VehicleGearChart` / `VehicleFxChart` / `VehicleGGVChart`（トルク点一致、Fx単調減少+段差、20×20 wireframe 5..80m/s）
- fallback: 各タブ `try/except` + Label、 `_update_vehicle_graphs` で Vehicle47 を4チャートへ配信（`__init__` / `_populate_tree` / `_on_add` / `_on_delete` / `_on_reset` / add_torque/delete_torque_at で呼出）
- 理由: VehicleEditorのPCHIPプレビューはトルク入力の編集即時反映に特化し、Gear/Fx/GGVは車両仕様全体の俯瞰（ギア比・Fx包絡・GGV 3D）に特化して関心を分離。トルク表直下に置くことで「入力表 → 4種解析 → PCHIP詳細」の編集フローが途切れない。

## 共通規約
- 全組込はタブ単位 `try/except` + プレースホルダ `ttk.Label` fallback、既存タブ順序・属性名（`chart_notebook` / `graph_notebook` / `tab_*` / `speed_chart` 等）を破壊しない
- 新規属性は追加のみ（例: `SimulateView2.elevation_chart` / `DragView.drag_tx_chart` / `TrackView2.track_map_chart` / `VehicleEditor47.vehicle_torque_chart`）
- `scipy` / `matplotlib` 不使用、`chart_base` / `chart_xy` を経由した Canvas自前描画を維持、`encoding="utf-8"` で保存
- ヘッドレス: Notebook生成は try で包み、テストは `tk.Tk` 生成可否で skip するがファイル内容自体は grep で検証可能

## 検証
- `tests/test_shell_integration.py`: 子タブ数 Sim 9・Drag 2+13・Track 6・Vehicle 4、タイトル重複なし、ヘッドレスでも pytest GREEN（Tk生成可では widget 検証、可不可ではソースgrep検証の二段構え）
