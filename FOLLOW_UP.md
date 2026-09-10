# FOLLOW_UP.md — V2改良候補（実装なし、列挙のみ）

> 本ファイルは今後の改良アイデアを列挙するのみで、実装は含まない。優先度は参考であり、着手前に再評価すること。

## 1. GUI/UX

- [ ] `App2` メニュー拡張: `File > Export`（CSV 11列の他に JSON/Parquet 選択）、`View > Theme`（light/dark 切替）、`Help > Docs`（`docs/regression_notes.md` を別ウィンドウで表示）
- [ ] キーボードショートカット: `Ctrl+R` Run、`Ctrl+S` Save、`Ctrl+E` Export、`Esc` 進捗キャンセル
- [ ] 4タブ間の選択同期: `TrackView2` でコースを切替えたら `SimulateView2` の `track_combo` も追従（逆も）、`VehicleEditor47` 保存後に `SimulateView2`/`DragView` の車両リストを自動リロード
- [ ] HiDPI / スケーリング検証: `tk.call('tk', 'scaling', ...)` の明示設定と `Canvas` 再描画の解像度テスト（4K/スケール125%）
- [ ] アクセシビリティ: `ttk` のコントラスト比検証、フォーカス順序の明示、`Tab` 移動の論理順序整理

## 2. Vehicle（47項目）

- [ ] `VehicleEditor47` の入力支援: 単位表示（kg/%/m/deg/N/deg）、ツールチップで行のMATLAB由来注記（`OpenVEHICLE.m:57` 等）をホバー表示
- [ ] バリデーション強化: `sens_x/sens_y` の符号チェック、`mu_x_M/mu_y_M` の `Ny/Nx` 換算表示、`tyre_radius` と `ratio_*` の整合性警告（`v_max` が極端に小さい場合）
- [ ] プリセット管理: `f1`/`gt` 以外の `custom` 複数保存、プリセット差分ビュー（`diff` 表示）、インポート/エクスポート（`data/vehicles/*.json` のドラッグ&ドロップ）
- [ ] ギア比ビジュアライザ: `ratio_gearbox` 別の `vehicle_speed vs wheel_torque` を `Canvas` で重ね描き、`shift_points` のドラッグ編集

## 3. Track（Track2）

- [ ] `Track2` エディタ: `bank_rad` / `grip_factor` / `sector_id` の直接編集テーブル（`TrackView2` に編集モード追加）、変更時の `PCHIP` 再補間プレビュー
- [ ] Logged data import: 実走行 `CSV`（`s,x,y,z,curv`）からの `Track2` 生成ウィザード、閉ループ自動判定と `logged` フラグ付与
- [ ] コース差分ビュー: 2コースの `elevation` / `curvature` / `bank` を重ねプロット、`length_m` 差のハイライト
- [ ] メッシュ検証ツール: `mesh(1.0)`〜`mesh(5.0)` の `length_m` 誤差と `curvature` ピーク数のテーブル表示

## 4. Solver / OpenDRAG

- [ ] `solver` の高速化: `numpy` ベクトル化の进一步、前後パスの `numba` 任意有効化（`numpy` フォールバック維持）、プロファイル用 `bench` スクリプト
- [ ] `OpenDRAG` の拡張: `incl`/`bank` を考慮したドラッグ走行（現在は平坦0deg固定）、`t - t_shift > shift_time` の可視化ログを `DragView` にタイムライン表示
- [ ] `freq` の連続スライダ: `25`/`50`/`100` 固定から `10..200 Hz` スライダへ、`step=100/freq` のリアルタイム長さプレビュー
- [ ] エネルギー/燃料の可視化: `SimulateView2` で `energy` / `fuel` の積算グラフ（距離ベース）を追加、`n_thermal` / `fuel_LHV` 変更時の即時再計算

## 5. チャート/可視化

- [ ] `Chart` のインタラクション: マウスホバーで `s/v/ax/ay/gear/rpm` のツールチップ、ドラッグでズーム、ダブルクリックでリセット
- [ ] GGダイアグラムの摩擦楕円オーバレイ: `ay_max(v)` / `ax_max(v)` の楕円を速度別に重ね描き、現在点の正規化位置表示
- [ ] Sector棒グラフの色分け: `sector` 別の平均速度/時間で色相変化、クリックで該当区間を `TrackView2` でハイライト
- [ ] エクスポート連携: チャートの `PNG` 保存（`Canvas.postscript` → `Pillow` 変換、依存は任意）

## 6. ビルド/配布

- [ ] `app.spec` のプラットフォーム別最適化: Windows `icon`/`version` リソース、macOS `bundle` 識別子、`--add-data` のパス区切り（`;` vs `:`）自動切替
- [ ] CIでの `pyinstaller` 成果物検証: `pytest -q` 後に `pyinstaller app.spec` を実行し `dist/OpenLAPexe --help` 相当のスモークテスト（ヘッドレスでは `xvfb-run`）
- [ ] 署名/公証: Windows `signtool`、macOS `codesign`/`notarytool` の手順書を `docs/build.md` に分離
- [ ] `requirements.txt` / `pyproject.toml` の同期チェック: `pip-compile` 的な依存ロックファイル生成（`numpy` のみだが再現性確保）

## 7. テスト/品質

- [ ] ヘッドレスGUIテストの拡充: `xvfb` での `App2` 4タブ統合のスクリーンショット比較（`Pillow` 差分、許容誤差付き）
- [ ] プロパティテスト: `rapid`/`hypothesis` での `Vehicle47` ランダム生成と `compute_ggv` の単調性・非負・決定論検証
- [ ] パフォーマンス回帰: `simulate_full('f1','spa',50)` の実行時間閾値（例: `<1.5s`）をCIで監視、`mesh` 刻み別のベンチマーク表
- [ ] エンコーディング/改行の厳密テスト: `data/*.json` の `utf-8` / `CRLF` 混入検出、`CSV` の `lineterminator="\n"` 固定検証

## 8. ドキュメント/運用

- [ ] `docs/architecture.md`: `src/openlapexe` の依存グラフ（`vehicle` → `drag` → `solver` → `gui`）と `app.py` shim の位置づけ
- [ ] `docs/build.md`: `pyinstaller` のトラブル（`hiddenimports` 追加基準、`datas` の相対パス解決、`--windowed` での `stdout None` ガード）
- [ ] `CONTRIBUTING.md`: コミット規約（`conventional commits`）、`pytest -q` 必須、`scipy`/`matplotlib` 追加禁止の明記
- [ ] 多言語化の下地: `gettext` 的な文字列外部化（現状は日本語ハードコード、`_()` ラップのみ準備）

---

---

## 9. QA hardening 2026-09-07 追記 — 残課題（優先度付き）

> 本節は TASK「コースクリエイター+原典グラフ全量の最終QA hardening」完了時点（143 passed）での残課題を追記。136テスト維持が最低線、新規7追加で143へ上積み、禁止importゼロ・py_compile全GREEN・文書完備を達成。commit禁止のため残課題のみ列挙。

- [ ] **P1 — OSMタイルのレート制限可視化**: 現在は 2req/s throttle で黙って `time.sleep` するのみ。残課題: ステータスバーへ `throttle: 0.5s wait` 表示と、`fetch_tile` の `URLError` 時のリトライ回数をUIへ通知（offline時の灰色プレースホルダは動作するが、ログに `User-Agent: OpenLAPexe/0.1` の成功/失敗を区別して残す）。`geo_tile.py` の `_throttle` と `OSMCanvas` の `queue` 連携をテストで検証済みだが、ユーザー向け可視化が未実装。
- [ ] **P1 — CourseCreator のキーボード Undo 伝播**: `CourseCreator` 単体では `<Control-z>` が `self.bind` / `canvas.bind` / `bind_all` の三重で動作するが、`App2` の5タブ同時存在時に `bind_all` が他タブの `Entry` の `Ctrl+Z` と競合する可能性を手動確認のみ。残課題: `App2` レベルで `notebook.select()` が作成タブの時にのみ `CourseCreator.undo` を発火させるフォーカスガードを導入し、`test_course_creator.py::test_undo_stack_depth` のヘッドレス版にフォーカス条件を追加。
- [ ] **P2 — Track.from_candidates の zone 永続化**: `from_candidates` で `points_lonlat` → `wgs84_to_plane` 変換時に `zone` を `meta.zone` に保存するが、`save_json`→`from_json` 往復後に `zone` が `meta` に残るだけで `points` の再投影には未使用。残課題: 保存トラックを再読込→再度 `from_candidates` した際の `zone` 一貫性を 1e-9 で保証する `test_track_from_candidates_zone_roundtrip` を追加し、`geo_proj.lon0_for_zone` のキャッシュを検討。
- [ ] **P2 — 原典グラフの凡例重なり**: `charts_track.py` / `charts_results.py` / `charts_drag.py` の凡例は固定矩形（`x1 - 110` 等）で描画。残課題: Canvas幅が極小（<300px）時に凡例がプロットと重なる。`_redraw` 内で `w < 400` の分岐を入れ、`font size 6` への縮小または凡例非表示の閾値を `test_charts_*` の `<Configure>` リサイズテストで検証。
- [ ] **P2 — DXF取込のブロック/INSERT対応**: `io_dxf.py` は `LINE/LWPOLYLINE/POLYLINE` のみ対応。原典 `ezdxf` が扱う `INSERT`（ブロック参照）や `ARC`/`CIRCLE` は未対応でスキップされる。残課題: `test_io_dxf.py` に `INSERT+block` のサンプルを追加し、未対応 entity を警告リストとして `ImportView` ステージングへ表示（現在は無視で `length_m` が短くなる）。
- [ ] **P3 — `geo_proj` の極域・日付変更線テスト**: 日本19系 (122..154°E) とUTM fallback (その他) はカバー済みだが、緯度85°超の clamping と経度±180°の wrap-around のエッジケースは `test_geo_proj.py::test_auto_zone_utm_fallback` で最小限のみ。残課題: 極域 `lat=89` / `lon=-179` / `lon=179` の roundtrip を 1e-3 内で検証するテーブル駆動テストを追加し、`_clamp_lat` の閾値 85.05112878 の根拠を `geo_tile` と共通化。
- [ ] **P3 — パフォーマンス回帰のCI閾値**: `simulate_full('f1','spa',50)` は現在 0.4〜0.6s だが CI 閾値なし。残課題: `pytest -q --durations=10` で `test_regression_full` / `test_integration_fidelity` の各 1s 未満を `pytest.ini` の `addopts` で強制し、`curvature_opt` の 200iter がヘッドレスで 1.5s を超えないことを `test_deterministic_cross.py::test_curvature_opt_cross_deterministic_1e9` のタイムアサートで担保（現在は時間計測なし）。

### QA hardening 検証サマリ（2026-09-07）

- `pytest -q`: **143 passed**（136維持 + deterministic_cross 7追加）、5 warnings（`Image.__del__` headlessのみ）
- `grep -R "import scipy\|from scipy\|import matplotlib\|from matplotlib\|import requests\|from PIL\|import ezdxf\|import pyproj" src/ --include="*.py"`: **EXIT 1**（ゼロ件、禁止importなし）
- `python -m py_compile main.py app.py app.spec && python -m py_compile src/openlapexe/*.py src/openlapexe/gui/*.py`: 全GREEN
- `tests/test_geo_proj.py` 存在: 8 tests、1e-9決定論・10000点<50ms・vectorized roundtrip検証
- `tests/test_deterministic_cross.py` 新規7 tests: creator/atlas横断 1e-9（geo_proj/geo_tile/track/curvature_opt/CourseCreator/KML→Track→Creator/OSM pixel）
- README: 5タブ化、作成タブ使い方、原典グラフ23種一覧、OSM規約クレジット、143テスト表を更新
- encoding=utf-8: 全 `read_text/write_text` で明示、atomic `tmp.write_text(..., encoding="utf-8"); tmp.replace(path)` 維持

---

## 10. T8 統合仕上げ 2026-09-09 追記 — 残課題（優先度付き）

> 本節は TASK「T8 統合仕上げ」完了時点（168 passed, SURFACE PASS, cold 0.5s<1.6s）での残課題を追記。Waypoint 8種（5px euclidean/dynamic radius/micro-move/Treeview/autosave 10点/Shift bypass/空保存/offline）の残1 REDをGREEN化、xvfb surface 15連打→保存→再読込1e-9、bench再測、README追記を達成。commit禁止のため残課題のみ列挙。

- [ ] **P1 — Autosave のクラッシュリカバリUI**: 現状は 10点ごとに `tempfile.gettempdir()/openlapexe_autosave_<pid>.json` へ atomic 保存し `autosave: N` を表示するのみ。残課題: 起動時に同ファイルが存在すれば `復元しますか？` ダイアログ（`messagebox.askyesno(parent=self)`）を提示し、`points_latlon/points_xy` を `OSMCanvas` へ再投入する `restore_autosave` フローを `App2.__init__` に追加。`tempfile` は pid 毎のため multi-instance の衝突は無いが、異常終了時の leftover を次回起動で検出するテスト `test_autosave_restore_on_restart` を追加。
- [ ] **P1 — Autosave の明示的クリア**: 保存成功後（`_on_save_track`）に autosave ファイルを削除すべきだが現状は残置。残課題: `track.save_json` 成功後に `autosave_path.unlink(missing_ok=True)` を `shell.py:_on_save_track` の `messagebox.showinfo` 直前に追加し、`tmp` 掃除（leftover禁止）の延長として `xvfb_waypoint_surface.py` の最終クリーンアップでも二重削除を保証。`test_autosave_cleared_after_save` で 10点作成→保存→ファイル無を確認。
- [ ] **P2 — xvfb surface のCI常時実行**: `scripts/xvfb_waypoint_surface.py` は手動 `xvfb-run -a python ...` では `SURFACE PASS` だが、CI の `pytest -q` には未統合。残課題: `pyproject.toml` の `addopts` へ `xvfb` スキップ条件を追加し、GitHub Actions では `apt-get install xvfb` + `xvfb-run -a pytest -q`（または `pytest --run-surface` カスタムフラグ）を導入。`--edge` の微振動/空保存/offline も CI で常時実行し、ヘッドレス時の `find_all` headless warning を許容。
- [ ] **P2 — Bench閾値の厳格化と warm 検証**: `bench_cold_tiles.py` は cold `0.51s (<1.6s)` で PASS だが、warm `0.00s` の閾値未定義。残課題: `warm <0.05s` を CI アサートに追加し、`MIN_INTERVAL=0.1` の根拠（OSM Tile Usage Policy 10req/s）を `geo_tile.py` 先頭コメントと `README` のPolicy注記で二重記載を追加。`test_geo_tile.py::test_bench_threshold` を新設し、cold/warm を `time.monotonic` で計測。
- [ ] **P3 — Waypoint数の上限ガード**: 現状は Treeview と Canvas が 15点程度では軽量だが、数百点で `create_oval`/`create_text` が線形増加。残課題: `CourseCreator` の `points_xy` が 500点超で `status_var` に `警告: 点が多すぎます` を表示し、`_autosave_points` の頻度を 10→50 に段階切替するガードを `shell.py:_sync_osm_to_creator` に追加。`test_waypoint_many_points_performance` で 1000点の `_draw_points_only` が `<100ms` であることを検証。
- [ ] **P3 — Policy注記の多言語化**: README のPolicy注記は日本語のみ。残課題: 英訳セクション `## OSM Tile Policy (English)` を併記し、`geo_tile.USER_AGENT` / `ATTRIBUTION` の定数参照を `README` と `geo_tile.py` で同期する `test_policy_doc_sync` を追加（`ATTRIBUTION` 文字列が両ファイルに含まれることを検証）。

### T8 検証サマリ（2026-09-09）

- `pytest -q`: **168 passed**（旧143 + waypoint_rapid 8の残1をGREEN化）、5 warnings（`Image.__del__` headlessのみ）
- `xvfb-run -a python scripts/xvfb_waypoint_surface.py` → **SURFACE PASS**（15連打マーカー15・結線14・Treeview15→保存→再読込1e-9→tmp掃除→exit 0）
- `xvfb-run -a python scripts/xvfb_waypoint_surface.py --edge` → **SURFACE PASS**（微振動+2・空保存disabled・offline placeholder）
- `python scripts/bench_cold_tiles.py` → **cold 0.51s (<1.6s), warm 0.00s**
- `python -m py_compile main.py app.py app.spec && python -m py_compile src/openlapexe/*.py src/openlapexe/gui/*.py scripts/*.py` → 全GREEN
- `grep -R "import scipy\|from scipy\|import matplotlib\|from matplotlib\|import requests\|from PIL\|import ezdxf\|import pyproj" src/ --include="*.py"` → **EXIT 1**（ゼロ件）
- `tests/test_waypoint_rapid.py::test_10points_autosave_exists` → **PASSED**（9無・10有・20有、atomic utf-8、`autosave: N`）
- README: Waypoint操作・autosave・policy注記・surface/bench手順・168テスト表を追記
- encoding=utf-8: 全 `read_text/write_text` で明示、atomic `tmp.write_text(..., encoding="utf-8"); tmp.replace(path)` 維持、leftover `.tmp` 無し

*運用メモ*: 本リストは実装を伴わないため、着手時は各候補を Issue 化し、受け入れ条件（Given/When/Then）とテストを先に定義してから `TDD` で進めること。`scipy`/`matplotlib` 追加は原則禁止（`numpy` + `tk.Canvas` 自前を維持）。
