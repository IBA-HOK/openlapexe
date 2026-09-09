# FINDINGS_verified.md — 引用行番号の実測監査

> 監査日: 2026-09-09 / 監査者: Sisyphus-Junior
> 対象: `src/openlapexe/gui/osm_canvas.py`, `src/openlapexe/gui/course_creator.py`, `src/openlapexe/geo_tile.py`, `src/openlapexe/gui/shell.py`
> 手法: `grep -n` + `sed -n` + `pytest -q` + `python -c` import 検証。各行番号は `wc -l` + 実ファイル先頭からのカウントで `1-indexed`。

---

## 1. osm_canvas.py — 1px / 10px / _dragging_idx

| 主張 | 実測 | 行番号 | 引用 | 判定 |
|------|------|--------|------|------|
| 1px閾値が存在する | **無し** | — | ファイル内 `1px` 該当なし。最小は ` < 10` の矩形判定のみ | drift: 1px なる記述は誤り、実体は10px矩形 |
| 10px矩形 hit-test | **有り** | `328` | `if abs(px - event.x) < 10 and abs(py - event.y) < 10:` | ✅ 実在 — 但し euclidean ではなく `abs` 二軸独立判定 (矩形) |
| `_dragging_idx` | **有り** | `178`, `322`, `329`, `337`, `368` | `self._dragging_idx: int \| None = None` / `_on_press`で `self._dragging_idx = idx` / `_on_drag`で `if self._dragging_idx is not None:` / `_on_release`でクリア | ✅ 実在 — しかし閾値5px euclidean ではなく10px矩形、かつ微移動でもドラッグ扱いになりクリック登録を奪う問題あり |
| euclidean hypot 5px | **無し** | — | `hypot` 文字列は `osm_canvas.py` 内に0件 (`grep -c hypot` == 0) | 🔴 drift: 仕様は5px euclideanを要求するが現状は矩形10pxで未実装 |

詳細抜粋 (osm_canvas.py:324-332):
```
        # hit test existing points
        try:
            for idx, (lat, lon) in enumerate(self.points_latlon):
                px, py = self._latlon_to_pixel(lat, lon)
                if abs(px - event.x) < 10 and abs(py - event.y) < 10:
                    self._dragging_idx = idx
                    return
```

---

## 2. course_creator.py — 2px / 12px

| 主張 | 実測 | 行番号 | 引用 | 判定 |
|------|------|--------|------|------|
| 2px閾値 | **無し** | — | `course_creator.py` 内で `< 2` は存在するが hit-test とは無関係 (`_on_drag` の `dx>2` はドラッグ移動判定) | drift: 2px hit-test は存在しない |
| 12px euclidean hit-test | **有り** | `594`, `613` | `if best_d < 12: return best_idx` ( `_find_nearest_vertex` ) / `if best_d < 12 and best_idx is not None: return` ( `_find_nearest_edge_vertex` ) | ✅ 実在 — `np.hypot` による euclidean 距離で閾値12px |
| _drag_start / _drag_idx | **有り** | `114`, `813`, `820` | `self._drag_idx: int \| None = None` / `_on_press` で `self._drag_idx = idx` | ✅ 実在 |

抜粋 (course_creator.py:588-594):
```
            for i, (x, y) in enumerate(lst):
                    d = float(np.hypot(float(x) - float(px), float(y) - float(py)))
                    ...
            if best_d < 12:
                return best_idx
```

---

## 3. geo_tile.py — MIN_INTERVAL / _LOCK / TIMEOUT

| 主張 | 実測 | 行番号 | 引用 | 判定 |
|------|------|--------|------|------|
| `MIN_INTERVAL=0.5` | **有り** | `26` | `MIN_INTERVAL: float = 0.5` | ✅ 実在 — 但し仕様期待は `0.1` なので要変更 |
| 単一 `_LOCK` | **有り** | `29` | `_LOCK = threading.Lock()` — 単一ロックで LRU と throttle を共用 | ✅ 実在 — 仕様は `_LRU_LOCK` / `_THROTTLE_LOCK` 分離を要求 |
| `_LRU_LOCK` / `_THROTTLE_LOCK` 分離 | **無し** | — | ファイル内に `_LRU_LOCK` 0件, `_THROTTLE_LOCK` 0件 | 🔴 drift: 分離未実装 (単一 `_LOCK` がボトルネック) |
| `TIMEOUT=2.0` | **有り** | `24` | `TIMEOUT: float = 2.0` | ✅ 実在 — 但し仕様期待は `1.0` |
| throttle 実装 | **有り** | `114-121` | `def _throttle() -> None:` 内 `with _LOCK: ... time.sleep(MIN_INTERVAL - elapsed)` | ✅ 実在 |

抜粋 (geo_tile.py:24-30):
```
MAX_CACHE_ENTRIES: int = 500
TIMEOUT: float = 2.0
RETRY_COUNT: int = 1
MIN_INTERVAL: float = 0.5

_LRU: collections.OrderedDict[Tuple[str, int, int, int], bytes] = collections.OrderedDict()
_LOCK = threading.Lock()
_LAST_REQUEST_TS: float = 0.0
```

---

## 4. shell.py — sync bind

| 主張 | 実測 | 行番号 | 引用 | 判定 |
|------|------|--------|------|------|
| `sync bind` (OSM → Creator 同期) | **有り** | `560`, `564`, `810` | `oc.bind("<ButtonRelease-1>", lambda _e: self._sync_osm_to_creator(), add="+")` / `oc.bind("<B1-Motion>", ...)` / `def _sync_osm_to_creator(self) -> None:` | ✅ 実在 |
| `after(50)` / `queue` / `threading` scaffold | **有り** | `142`, `217`, `253`, `82`, `271` | `self.after(50, self._poll_queue)` / `queue.Queue` / `threading.Thread` | ✅ 実在 |
| 現状の問題 | — | — | `ButtonRelease-1` と `B1-Motion` の両方で `_sync_osm_to_creator` を呼ぶため、ドラッグ中も毎回同期が走り冗長。点追加時の `fetch_tile` 呼び出しゼロ化が未対応 | 要改善: 点追加はコールバック同期のみでタイル再取得不要 |

抜粋 (shell.py:560-564):
```
            try:
                oc.bind("<ButtonRelease-1>", lambda _e: self._sync_osm_to_creator(), add="+")
            except Exception:
                pass
            try:
                oc.bind("<B1-Motion>", lambda _e: self._sync_osm_to_creator(), add="+")
```

---

## 5. Drift サマリ

| 項目 | 期待 | 現状 | drift |
|------|------|------|-------|
| osm_canvas hit 半径 | 5px euclidean hypot | 10px 矩形 `abs<10` | 🔴 未実装。動的半径ヘルパも無し (`_hit_radius` 等0件) |
| course_creator hit 半径 | 5px or 動的 | 12px euclidean `hypot<12` | 🔴 12px は 5px 要求と不一致。動的半径無し |
| _dragging_idx 微移動 | 同一ヒット域の連続2クリックで+2点 | 現状は2回目クリックが既存点ヒットで `_dragging_idx` に吸収され追加されない | 🔴 要修正 |
| Treeview No/lat/lon | 列 (No/lat/lon) | 現状 Treeview 列は (name/kind/verts/length), (rpm,Nm), (sector) 等で (No/lat/lon) は無し | 🔴 未実装 |
| 10点 autosave | 10点で自動保存 | `autosave` / `auto_save` 文字列は0件 | 🔴 未実装 |
| 写真 armed Shift bypass | Shift+Click で写真配置 bypass | `Shift` 文字列は osm_canvas.py に0件 (shell の `shift_time` のみ) | 🔴 未実装 |
| 空保存ブロック | 保存ボタン disabled (<2点) | 現状は `len<2` で warning のみ、ボタンは常に enabled | 🔴 UI state 未連動 |
| オフライン非crash | 失敗時即placeholder bytes | 現状は `raise` (retry後例外) で placeholder 返却無し | 🔴 未実装 (OSMCanvas側は gray rect で耐えるが geo_tile は例外) |
| geo_tile throttle | MIN_INTERVAL=0.1 | MIN_INTERVAL=0.5 | 🔴 要変更 |
| geo_tile lock | _LRU_LOCK / _THROTTLE_LOCK 分離 | 単一 _LOCK | 🔴 未分離 |
| geo_tile timeout | TIMEOUT=1.0 | TIMEOUT=2.0 | 🔴 要変更 |
| geo_tile 失敗時 | 即placeholder | retry1 + raise | 🔴 要変更 |
| OSM点追加 fetch | 0回 | _redraw経由で潜在的に fetch 発生 | 🔴 要ゼロ化 |
| zoom inflight破棄 | old zoom inflight 破棄 | 破棄無し (_inflight は zoom 変更でクリアされない) | 🔴 未実装 |
| bench cold | 6タイル cold ~2.5s, warm instant, `cold X.XXs` 表示 | 未計測 (bench スクリプト無し → 今回追加) | 🟡 今回 `scripts/bench_cold_tiles.py` で提供 |

---

## 6. 検証コマンド (再現)

```bash
grep -n "_dragging_idx\|MIN_INTERVAL\|TIMEOUT\|_LOCK" src/openlapexe/geo_tile.py
grep -n "abs.*< 10\|hypot" src/openlapexe/gui/osm_canvas.py src/openlapexe/gui/course_creator.py
grep -n "_drag_idx\|_find_nearest" src/openlapexe/gui/course_creator.py
grep -n "Treeview" src/openlapexe/gui/shell.py src/openlapexe/gui/*.py
grep -n "autosave\|auto_save" src/openlapexe/gui/*.py src/openlapexe/*.py
grep -n "Shift" src/openlapexe/gui/osm_canvas.py
grep -n "_sync_osm_to_creator\|bind.*ButtonRelease" src/openlapexe/gui/shell.py
pytest -q  # 154 passed baseline (before RED tests), RED tests are expected FAIL
python scripts/bench_cold_tiles.py  # -> cold X.XXs (現状 ~2.5s with 0.5 throttle)
```

---

## 7. 結論

- 引用行番号の実ファイル照合は **全て一致** (上記行番号は `1-indexed` で実測)。
- drift は **14項目** で仕様未達 (上表 🔴)。本ファイルと同時に投入した RED テスト (`tests/test_waypoint_rapid.py` 8件 + `tests/test_osm_speedup.py` 6件) はこれら drift を仕様由来で FAIL させることを目的とし、構文/import エラーではない。
- `src/` は本監査時点では **無改変** を維持 (TDD Red フェーズ)。
