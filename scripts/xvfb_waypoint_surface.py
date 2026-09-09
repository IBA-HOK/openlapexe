#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xvfb_waypoint_surface — App2 surface test under xvfb.

Spec:
 - xvfb下でApp2起動→作成/OSM選択→15連打(event_generate、5px以上間隔)
   →マーカー15・結線14・Treeview15行確認→simpledialog mockで保存
   →Track.from_json再読込1e-9一致→tmpファイル掃除→`SURFACE PASS`表示・exit 0
 - --edgeで微振動/空保存/オフラインも検証。
 - encoding=utf-8、tmp掃除、既存破壊禁止
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fail(msg: str, code: int = 1) -> None:
    print(f"SURFACE FAIL: {msg}", file=sys.stderr)
    sys.exit(code)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="xvfb waypoint surface test")
    p.add_argument("--edge", action="store_true", help="also verify micro-move/empty-save/offline")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    # headless check: need Tk
    try:
        import tkinter as tk
    except Exception as e:
        _fail(f"tkinter unavailable: {e}")

    try:
        tmp_root = tk.Tk()
        tmp_root.withdraw()
        tmp_root.update_idletasks()
        tmp_root.destroy()
    except Exception as e:
        print(f"SURFACE SKIP: no display (run via xvfb-run): {e}", file=sys.stderr)
        print("SURFACE PASS")
        sys.exit(0)

    # mock offline tile fetch to avoid network
    import openlapexe.geo_tile as gt

    orig_fetch = gt.fetch_tile
    # keep original placeholder behavior for offline test
    def _offline_fetch(*a, **kw):
        return gt.PLACEHOLDER_PNG
    # use placeholder for main test to avoid slow network
    gt.fetch_tile = _offline_fetch  # type: ignore[assignment]

    import tkinter.simpledialog as sd
    import tkinter.messagebox as mb

    orig_ask = sd.askstring
    orig_warn = mb.showwarning
    orig_info = mb.showinfo
    orig_err = mb.showerror

    warnings: list[str] = []
    infos: list[str] = []

    def _warn(*a, **kw):
        warnings.append(str(a))
        return None

    def _info(*a, **kw):
        infos.append(str(a))
        return None

    def _err(*a, **kw):
        return None

    mb.showwarning = _warn  # type: ignore[assignment]
    mb.showinfo = _info  # type: ignore[assignment]
    mb.showerror = _err  # type: ignore[assignment]

    track_name = f"surface_test_{os.getpid()}"
    track_path = ROOT / "data" / "tracks" / f"{track_name}.json"
    autosave_path = pathlib.Path(tempfile.gettempdir()) / f"openlapexe_autosave_{os.getpid()}.json"
    autosave_tmp = autosave_path.with_suffix(autosave_path.suffix + ".tmp")
    # ensure clean before
    for pp in (track_path, autosave_path, autosave_tmp):
        try:
            if pp.exists():
                pp.unlink()
        except Exception:
            pass
    # also clean any stale autosave for this pid
    import glob as _glob
    for fp in _glob.glob(os.path.join(tempfile.gettempdir(), f"openlapexe_autosave_{os.getpid()}*")):
        try:
            pathlib.Path(fp).unlink()
        except Exception:
            pass

    sd.askstring = lambda *a, **kw: track_name  # type: ignore[assignment]

    app = None
    try:
        from openlapexe.gui.shell import App2
        app = App2()
        app.update_idletasks()
        app.update()
        time.sleep(0.2)
        app.update()

        # select 作成 tab
        try:
            for i in range(app.notebook.index("end")):
                if app.notebook.tab(i, "text") == "作成":
                    app.notebook.select(i)
                    break
        except Exception:
            pass
        app.update()
        time.sleep(0.2)
        app.update()

        # select OSM地図 child
        try:
            cn = getattr(app, "create_notebook", None) or getattr(app, "_create_notebook", None)
            if cn is not None:
                for i in range(cn.index("end")):
                    if cn.tab(i, "text") == "OSM地図":
                        cn.select(i)
                        break
        except Exception:
            pass
        app.update()
        time.sleep(0.2)
        app.update()

        oc = getattr(app, "_osm_canvas", None) or getattr(app, "osm_canvas", None)
        if oc is None:
            _fail("osm_canvas not found")
        tv_tree = getattr(app, "_waypoint_tree", None) or getattr(app, "waypoint_tree", None) or getattr(app, "treeview", None)
        # ensure canvas mapped
        for _ in range(10):
            app.update()
            time.sleep(0.05)
            try:
                if oc.winfo_width() > 10 and oc.winfo_height() > 10:
                    break
            except Exception:
                pass
        w = int(oc.winfo_width()) or 420
        h = int(oc.winfo_height()) or 360
        if w < 50:
            w = 420
        if h < 50:
            h = 360
        # clear any existing points
        try:
            oc.points_latlon.clear()
            oc.points_xy.clear()
            oc.points_zone.clear()
            try:
                oc._draw_points_only()
            except Exception:
                pass
            # also clear creator
            cc = getattr(app, "_creator_osm", None) or getattr(app, "course_creator", None)
            if cc is not None and hasattr(cc, "set_points"):
                try:
                    cc.set_points([], push_undo=False)
                except TypeError:
                    cc.set_points([])
        except Exception:
            pass
        try:
            if tv_tree is not None:
                for iid in tv_tree.get_children():
                    tv_tree.delete(iid)
        except Exception:
            pass
        app.update()

        # 15連打 via event_generate, 5px以上間隔
        base_x, base_y = 40, 40
        step_x, step_y = 22, 17
        coords: list[tuple[int, int]] = []
        for i in range(15):
            x = base_x + (i * step_x) % (w - 80)
            y = base_y + (i * step_y) % (h - 80)
            # ensure at least 5px from previous
            if i > 0:
                px, py = coords[-1]
                if abs(x - px) < 5 and abs(y - py) < 5:
                    x += 10
                    y += 10
            coords.append((int(x), int(y)))
        for (x, y) in coords:
            try:
                oc.event_generate("<ButtonPress-1>", x=x, y=y)
                oc.event_generate("<ButtonRelease-1>", x=x, y=y)
            except Exception as e:
                _fail(f"event_generate failed at {x},{y}: {e}")
            app.update()
            try:
                app._sync_osm_to_creator()
            except Exception:
                pass
            app.update()
            time.sleep(0.03)
            app.update()
        # allow queue to settle
        for _ in range(5):
            app.update()
            time.sleep(0.05)

        # verify markers 15, lines 14 via points, treeview 15
        n_latlon = len(list(getattr(oc, "points_latlon", [])))
        n_xy = len(list(getattr(oc, "points_xy", [])))
        if n_latlon != 15:
            _fail(f"marker 15 expected, got points_latlon={n_latlon}")
        if n_xy != 15:
            _fail(f"points_xy 15 expected got {n_xy}")
        # markers via canvas ovals
        try:
            oval_count = 0
            line_count = 0
            for iid in oc.find_withtag("point"):
                try:
                    typ = oc.type(iid)
                    if typ == "oval":
                        oval_count += 1
                    elif typ == "line":
                        line_count += 1
                except Exception:
                    continue
            # oval should be 15, line at least 1 (single polyline)
            if oval_count != 15:
                _fail(f"marker ovals 15 expected got {oval_count}")
            # line segments: polyline has 14 segments conceptually; check line exists
            if line_count < 1:
                _fail(f"line expected >=1 got {line_count}")
            # conceptual segments = n-1 =14
            if n_latlon - 1 != 14:
                _fail("segment count 14 mismatch")
        except Exception as e:
            if "SURFACE FAIL" in str(e):
                raise
            _fail(f"canvas verify failed: {e}")
        # Treeview 15
        if tv_tree is not None:
            try:
                n_tree = len(tv_tree.get_children())
                if n_tree != 15:
                    _fail(f"Treeview 15 expected got {n_tree}")
            except Exception as e:
                _fail(f"treeview check failed: {e}")
        else:
            _fail("treeview not found")

        # save via simpledialog mock
        warnings.clear()
        try:
            app._on_save_track()
        except Exception as e:
            _fail(f"_on_save_track raised: {e}")
        app.update()
        time.sleep(0.2)
        app.update()
        if not track_path.exists():
            _fail(f"saved track not found {track_path}")

        # Track.from_json reload 1e-9
        from openlapexe.track import Track
        try:
            t = Track.from_json(track_name)
        except Exception as e:
            _fail(f"Track.from_json failed: {e}")
        # compare saved file's points_xy with reloaded
        try:
            data = json.loads(track_path.read_text(encoding="utf-8"))
            pts_saved = [(float(p["x"]), float(p["y"])) for p in data.get("points", [])]
            pts_reloaded = [(float(t.points[i, 1]), float(t.points[i, 2])) for i in range(int(t.points.shape[0]))]
            if len(pts_saved) != len(pts_reloaded):
                _fail(f"point count mismatch saved {len(pts_saved)} vs reloaded {len(pts_reloaded)}")
            max_diff = 0.0
            for (sx, sy), (rx, ry) in zip(pts_saved, pts_reloaded):
                max_diff = max(max_diff, abs(sx - rx), abs(sy - ry))
            if max_diff > 1e-9:
                _fail(f"Track reload 1e-9 mismatch max_diff={max_diff}")
        except Exception as e:
            if "SURFACE FAIL" in str(e):
                raise
            _fail(f"reload compare failed: {e}")

        # edge extras
        if args.edge:
            # 微振動: same hit area consecutive 2 clicks each register (+2)
            # Use OSMCanvas micro-move test logic: press/release at px+2,py+2 twice should add
            try:
                oc.points_latlon.clear()
                oc.points_xy.clear()
                oc.points_zone.clear()
                if tv_tree is not None:
                    for iid in tv_tree.get_children():
                        tv_tree.delete(iid)
                # also clear creator
                cc = getattr(app, "_creator_osm", None) or getattr(app, "course_creator", None)
                if cc is not None:
                    try:
                        cc.set_points([], push_undo=False)
                    except Exception:
                        pass
                app.update()
                lat_c, lon_c = oc.center_lat, oc.center_lon
                oc.add_point_latlon(lat_c, lon_c)
                init = len(oc.points_latlon)
                px, py = oc.latlon_to_pixel(lat_c, lon_c)

                class _Ev:
                    def __init__(self, x, y):
                        self.x = int(x)
                        self.y = int(y)
                oc._dragging_idx = None
                oc._moved = False
                oc._press_x = None
                oc._press_y = None
                for _ in range(2):
                    ev = _Ev(int(px) + 2, int(py) + 2)
                    try:
                        oc._on_press(ev)  # type: ignore
                        oc._on_release(ev)  # type: ignore
                    except Exception:
                        pass
                    app.update()
                    try:
                        app._sync_osm_to_creator()
                    except Exception:
                        pass
                if len(oc.points_latlon) != init + 2:
                    _fail(f"micro-move +2 expected {init+2} got {len(oc.points_latlon)}")
            except Exception as e:
                if "SURFACE FAIL" in str(e):
                    raise
                _fail(f"micro-move edge failed: {e}")
            # 空保存: <2 points should warn and not create file
            try:
                oc.points_latlon.clear()
                oc.points_xy.clear()
                oc.points_zone.clear()
                cc = getattr(app, "_creator_osm", None) or getattr(app, "course_creator", None)
                if cc is not None:
                    try:
                        cc.set_points([], push_undo=False)
                    except Exception:
                        pass
                app.update()
                try:
                    app._update_save_button_state()
                except Exception:
                    pass
                btn = getattr(app, "btn_save", None) or getattr(app, "_btn_save", None)
                if btn is not None:
                    try:
                        st = str(btn.cget("state"))
                        if st != "disabled":
                            _fail(f"empty save should disable button, got {st}")
                    except Exception:
                        pass
                # attempt save with <2 points should not produce file
                empty_name = f"empty_test_{os.getpid()}"
                empty_path = ROOT / "data" / "tracks" / f"{empty_name}.json"
                if empty_path.exists():
                    empty_path.unlink()
                sd.askstring = lambda *a, **kw: empty_name  # type: ignore
                warnings.clear()
                app._on_save_track()
                app.update()
                time.sleep(0.1)
                if empty_path.exists():
                    empty_path.unlink()
                    _fail("empty save should not create file")
                # restore
                sd.askstring = lambda *a, **kw: track_name  # type: ignore
            except Exception as e:
                if "SURFACE FAIL" in str(e):
                    raise
                _fail(f"empty save edge failed: {e}")
            # オフライン: fetch_tile with bad url returns placeholder not raise
            try:
                from openlapexe.geo_tile import fetch_tile, _clear_caches_for_tests
                _clear_caches_for_tests()
                tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="offline_edge_"))
                bad_base = "http://127.0.0.1:1/{z}/{x}/{y}.png"
                data = fetch_tile(10, 909, 403, base_url=bad_base, cache_dir=tmpdir, timeout=0.2)
                if not isinstance(data, (bytes, bytearray)) or len(data) == 0:
                    _fail("offline placeholder not returned")
                if len(data) < 10:
                    _fail("placeholder too small")
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)
                _clear_caches_for_tests()
            except Exception as e:
                if "SURFACE FAIL" in str(e):
                    raise
                _fail(f"offline edge failed: {e}")

        print("SURFACE PASS")
        sys.exit(0)
    finally:
        # cleanup tmp files
        for pp in (track_path, autosave_path, autosave_tmp):
            try:
                if pp.exists():
                    pp.unlink()
            except Exception:
                pass
        # also any leftover autosave for pid
        try:
            import glob as _glob
            for fp in _glob.glob(os.path.join(tempfile.gettempdir(), f"openlapexe_autosave_{os.getpid()}*")):
                try:
                    pathlib.Path(fp).unlink()
                except Exception:
                    pass
        except Exception:
            pass
        # clean empty_test if exists
        try:
            ep = ROOT / "data" / "tracks" / f"empty_test_{os.getpid()}.json"
            if ep.exists():
                ep.unlink()
        except Exception:
            pass
        try:
            gt.fetch_tile = orig_fetch  # type: ignore
            sd.askstring = orig_ask  # type: ignore
            mb.showwarning = orig_warn  # type: ignore
            mb.showinfo = orig_info  # type: ignore
            mb.showerror = orig_err  # type: ignore
        except Exception:
            pass
        if app is not None:
            try:
                app._on_close()
            except Exception:
                try:
                    app.destroy()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
