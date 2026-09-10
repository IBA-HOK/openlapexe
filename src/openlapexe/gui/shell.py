# -*- coding: utf-8 -*-
"""openlapexe.gui.shell - App2 Tk shell (V2 scaffold).

App (app.py) is canonical and untouched. App2 is the src-side Tk root
extracted for V2 migration. Requirements:
- tk.Tk, 800x600, Notebook 4 tabs=車両/コース/OpenDRAG/シミュレーション
- Statusbar (ttk), menu File/Help, geometry persistence, thread+queue+after(50)
- messagebox parent=self, stdout None guard, ttk only, Font self retention
- encoding utf-8 for config I/O
"""
from __future__ import annotations

import io
import json
import logging
import pathlib
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont

log = logging.getLogger(__name__)

# helpers: try openlapexe.io, fallback to local
try:
    from openlapexe.io import (  # type: ignore[import-not-found]
        _atomic_write_text as _atomic_write_text,
        get_config_path as get_config_path,
        resource_path as resource_path,
    )
except ImportError:

    def resource_path(relative: str) -> pathlib.Path:
        if hasattr(sys, "_MEIPASS"):
            base = pathlib.Path(str(sys._MEIPASS))  # type: ignore[attr-defined]
        else:
            base = pathlib.Path(__file__).resolve().parents[3]
            if not (base / "app.py").exists() and not (base / "data").exists():
                base = pathlib.Path(__file__).resolve().parents[2]
        return base / relative

    def get_config_path() -> pathlib.Path:
        if sys.platform == "win32":
            base = pathlib.Path.home() / "AppData" / "Roaming" / "OpenLAPexe"
        elif sys.platform == "darwin":
            base = pathlib.Path.home() / "Library" / "Application Support" / "OpenLAPexe"
        else:
            import os

            xdg = pathlib.Path.home() / ".config" / "openlapexe"
            env = os.environ.get("XDG_CONFIG_HOME")
            if env:
                base = pathlib.Path(env) / "openlapexe"
            else:
                base = xdg
        return base / "config.json"

    def _atomic_write_text(path: pathlib.Path, text: str, encoding: str = "utf-8") -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(text, encoding=encoding)
        tmp.replace(path)


class App2(tk.Tk):
    """Src-side App shell. Mirrors app.App but with 4 tabs + thread/queue scaffold."""

    def __init__(self) -> None:
        super().__init__()
        self.title("OpenLAPexe")
        # Font retention (Tk quirk: keep reference to avoid GC)
        self._font_default = tkfont.nametofont("TkDefaultFont")
        self._font_text = tkfont.nametofont("TkTextFont")
        # stdout None guard (when --windowed / no console)
        if sys.stdout is None:
            sys.stdout = io.StringIO()  # type: ignore[assignment]
        if sys.stderr is None:
            sys.stderr = sys.stdout  # type: ignore[assignment]
        # thread+queue+after polling scaffold
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._poll_job: str | None = None
        self._result: object | None = None
        # geometry persistence via get_config_path
        try:
            self._config_path = get_config_path()
        except Exception:
            self._config_path = pathlib.Path.home() / ".config" / "openlapexe" / "config.json"
        geom = self._load_geometry()
        if geom:
            try:
                self.geometry(geom)
            except Exception:
                self.geometry("800x600")
        else:
            self.geometry("800x600")
        # resource_path integration (icon)
        self._setup_icon()
        # menu bar
        self._setup_menu()
        # Notebook 6 tabs (車両/コース/OpenDRAG/シミュレーション/作成/データ)
        self.notebook = ttk.Notebook(self)
        self.tab_vehicle = ttk.Frame(self.notebook)
        self.tab_track = ttk.Frame(self.notebook)
        self.tab_opendrag = ttk.Frame(self.notebook)
        # aliases for discovery
        self.tab_drag = self.tab_opendrag
        self.tab_open_drag = self.tab_opendrag
        self.tab_simulate = ttk.Frame(self.notebook)
        self.tab_sim = self.tab_simulate
        self.tab_create = ttk.Frame(self.notebook)
        # aliases for creator tab discovery
        self.tab_creator = self.tab_create
        self.tab_creation = self.tab_create
        self.tab_data = ttk.Frame(self.notebook)
        # aliases for data tab discovery
        self.tab_datum = self.tab_data
        self.tab_dataset = self.tab_data
        self.notebook.add(self.tab_vehicle, text="車両")
        self.notebook.add(self.tab_track, text="コース")
        self.notebook.add(self.tab_opendrag, text="OpenDRAG")
        self.notebook.add(self.tab_simulate, text="シミュレーション")
        self.notebook.add(self.tab_create, text="作成")
        self.notebook.add(self.tab_data, text="データ")
        self.notebook.pack(fill="both", expand=True)
        # tab contents (ttk only, no Entry)
        self._setup_tab_contents()
        # ttk Statusbar
        self._status_var = tk.StringVar(value="Ready")
        self.statusbar = ttk.Frame(self, relief="sunken")
        self.statusbar.pack(side="bottom", fill="x")
        self._status_label = ttk.Label(self.statusbar, textvariable=self._status_var, anchor="w", padding=(6, 2))
        self._status_label.pack(side="left", fill="x", expand=True)
        # aliases for test compatibility
        self._statusbar = self.statusbar
        self.status_bar = self.statusbar
        self.status_frame = self.statusbar
        # persist geometry on close
        try:
            self.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass
        # start polling scaffold (after 50ms)
        try:
            self._poll_job = self.after(50, self._poll_queue)
        except Exception:
            pass
        log.info("App2 initialized")

    # -- geometry persistence -------------------------------------------------
    def _load_geometry(self) -> str | None:
        try:
            p = getattr(self, "_config_path", get_config_path())
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except Exception as e:
                    log.warning("config json broken, using default geometry: %s", e)
                    try:
                        messagebox.showwarning("警告", f"設定ファイルが破損しているため既定値を使用します:\n{e}", parent=self)
                    except Exception:
                        try:
                            messagebox.showwarning("警告", f"設定ファイルが破損しているため既定値を使用します:\n{e}", parent=self)
                        except Exception:
                            pass
                    try:
                        self._status_var.set("設定ファイル破損→既定値を使用")
                    except Exception:
                        pass
                    return None
                g = data.get("geometry") if isinstance(data, dict) else None
                if isinstance(g, str) and g:
                    return g
        except Exception as e:
            log.debug("load geometry failed: %s", e)
        return None

    def _save_geometry(self) -> None:
        try:
            p = getattr(self, "_config_path", get_config_path())
            p.parent.mkdir(parents=True, exist_ok=True)
            data: dict[str, object] = {}
            if p.exists():
                try:
                    loaded = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        data = loaded
                except Exception:
                    data = {}
            try:
                geom = self.geometry()
            except Exception:
                geom = "800x600"
            data["geometry"] = geom
            _atomic_write_text(p, json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log.debug("save geometry failed: %s", e)

    def _on_close(self) -> None:
        try:
            # cancel polling
            if self._poll_job is not None:
                try:
                    self.after_cancel(self._poll_job)
                except Exception:
                    pass
                self._poll_job = None
        except Exception:
            pass
        try:
            self._save_geometry()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    # -- thread+queue+after polling scaffold ---------------------------------
    def _poll_queue(self) -> None:
        """Poll background queue; re-schedule via after(50). Scaffold for simulate."""
        try:
            while True:
                try:
                    kind, payload = self._queue.get_nowait()
                except queue.Empty:
                    break
                except Exception as e:
                    log.debug("queue poll error: %s", e)
                    break
                # handle scaffold messages (no-op, just log)
                if kind == "ok":
                    self._result = payload
                    try:
                        self._status_var.set("完了")
                    except Exception:
                        pass
                elif kind == "error":
                    try:
                        messagebox.showerror("Error", str(payload), parent=self)
                    except Exception:
                        try:
                            messagebox.showerror("Error", str(payload), parent=self)
                        except Exception:
                            pass
                elif kind == "status":
                    try:
                        self._status_var.set(str(payload))
                    except Exception:
                        pass
                else:
                    log.debug("unknown queue kind=%s payload=%s", kind, payload)
        finally:
            # re-schedule polling every 50ms
            try:
                self._poll_job = self.after(50, self._poll_queue)
            except Exception:
                self._poll_job = None

    def _start_background_task(self, target, *args, **kwargs) -> None:
        """Helper to run target in background thread and feed queue."""

        def _worker() -> None:
            try:
                result = target(*args, **kwargs)
                self._queue.put(("ok", result))
            except Exception as e:
                try:
                    self._queue.put(("error", e))
                except Exception:
                    self._queue.put(("error", str(e)))

        try:
            self._thread = threading.Thread(target=_worker, daemon=True)
            self._thread.start()
        except Exception as e:
            try:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                pass

    # -- resource_path integration -------------------------------------------
    def _setup_icon(self) -> None:
        try:
            for rel in ("assets/icon.png", "assets/icon.ico", "data/icon.png", "icon.png"):
                try:
                    pp = resource_path(rel)
                    if pp.exists():
                        if pp.suffix.lower() == ".png":
                            img = tk.PhotoImage(file=str(pp))
                            self._icon_img = img  # type: ignore[attr-defined]
                            self.iconphoto(True, img)
                        elif pp.suffix.lower() == ".ico":
                            self.iconbitmap(str(pp))
                        break
                except Exception:
                    continue
        except Exception as e:
            log.debug("icon setup skipped: %s", e)

    # -- menu ----------------------------------------------------------------
    def _setup_menu(self) -> None:
        try:
            menubar = tk.Menu(self)
            file_menu = tk.Menu(menubar, tearoff=0)
            file_menu.add_command(label="設定フォルダを開く", command=self._open_config_folder)
            file_menu.add_separator()
            file_menu.add_command(label="終了", command=self._on_close)
            menubar.add_cascade(label="File", menu=file_menu)
            help_menu = tk.Menu(menubar, tearoff=0)
            help_menu.add_command(label="このソフトについて", command=self._show_about)
            menubar.add_cascade(label="Help", menu=help_menu)
            self.config(menu=menubar)
            self._menubar = menubar  # type: ignore[attr-defined]
            self._file_menu = file_menu  # type: ignore[attr-defined]
            self._help_menu = help_menu  # type: ignore[attr-defined]
        except Exception as e:
            log.debug("menu setup failed: %s", e)

    def _open_config_folder(self) -> None:
        try:
            p = getattr(self, "_config_path", get_config_path())
            folder = p.parent
            folder.mkdir(parents=True, exist_ok=True)
            self._status_var.set(str(folder))
            import subprocess

            if sys.platform == "win32":
                import os as _os

                _os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as e:
            log.debug("open config folder failed: %s", e)
            try:
                messagebox.showinfo("設定フォルダ", str(getattr(self, "_config_path", get_config_path()).parent), parent=self)
            except Exception:
                pass

    def _show_about(self) -> None:
        try:
            messagebox.showinfo(
                "このソフトについて",
                "OpenLAPexe\n"
                "OpenLAP Lap Time Simulator GUI (Tk)\n"
                "License: GPLv3\n"
                "Origin: mc12027/OpenLAP-Lap-Time-Simulator SHA 882116a\n"
                "© Michael Halkiopoulos / Cranfield University",
                parent=self,
            )
        except Exception as e:
            log.debug("about dialog failed: %s", e)

    def _setup_tab_contents(self) -> None:
        integrated = 0
        try:
            from openlapexe.gui.vehicle_editor import VehicleEditor47 as _VE47  # type: ignore

            ve = _VE47(self.tab_vehicle)
            ve.pack(fill="both", expand=True, padx=4, pady=4)
            self.vehicle_editor = ve  # type: ignore[attr-defined]
            self._vehicle_editor = ve
            try:
                ve.on_vehicle_saved = lambda name="": self._on_vehicle_saved(str(name) if name else None)  # type: ignore[attr-defined]
            except Exception:
                pass
            integrated += 1
        except Exception as e:
            log.debug("VehicleEditor47 embed failed: %s", e)
            try:
                ttk.Label(self.tab_vehicle, text="車両", font=self._font_default).pack(anchor="w", padx=12, pady=(12, 4))
                vehicle_info = self._collect_data_preview("vehicles")
                ttk.Label(self.tab_vehicle, text=vehicle_info, wraplength=760, justify="left").pack(anchor="w", padx=12, pady=4)
                ttk.Separator(self.tab_vehicle, orient="horizontal").pack(fill="x", padx=12, pady=8)
                ttk.Label(self.tab_vehicle, text="※ 編集は別タスクで対応", foreground="#666").pack(anchor="w", padx=12)
            except Exception:
                pass
        try:
            from openlapexe.gui.track_view import TrackView2 as _TV2  # type: ignore

            tv = _TV2(self.tab_track)
            tv.pack(fill="both", expand=True, padx=4, pady=4)
            self.track_view = tv  # type: ignore[attr-defined]
            self._track_view = tv
            integrated += 1
        except Exception as e:
            log.debug("TrackView2 embed failed: %s", e)
            try:
                ttk.Label(self.tab_track, text="コース", font=self._font_default).pack(anchor="w", padx=12, pady=(12, 4))
                track_info = self._collect_data_preview("tracks")
                ttk.Label(self.tab_track, text=track_info, wraplength=760, justify="left").pack(anchor="w", padx=12, pady=4)
                ttk.Separator(self.tab_track, orient="horizontal").pack(fill="x", padx=12, pady=8)
                ttk.Label(self.tab_track, text="※ 編集は別タスクで対応", foreground="#666").pack(anchor="w", padx=12)
            except Exception:
                pass
        try:
            from openlapexe.gui.drag_view import DragView as _DV  # type: ignore

            dv = _DV(self.tab_opendrag)
            dv.pack(fill="both", expand=True, padx=4, pady=4)
            self.drag_view = dv  # type: ignore[attr-defined]
            self._drag_view = dv
            integrated += 1
        except Exception as e:
            log.debug("DragView embed failed: %s", e)
            try:
                ttk.Label(self.tab_opendrag, text="OpenDRAG", font=self._font_default).pack(anchor="w", padx=12, pady=(12, 4))
                ttk.Label(self.tab_opendrag, text="OpenDRAG 空力モジュール 準備中。", wraplength=760, justify="left").pack(anchor="w", padx=12, pady=4)
                ttk.Separator(self.tab_opendrag, orient="horizontal").pack(fill="x", padx=12, pady=8)
                ttk.Label(self.tab_opendrag, text="※ 空力編集は別タスクで対応", foreground="#666").pack(anchor="w", padx=12)
            except Exception:
                pass
        try:
            from openlapexe.gui.simulate import SimulateView2 as _SV2  # type: ignore

            sv = _SV2(self.tab_simulate)
            sv.pack(fill="both", expand=True, padx=4, pady=4)
            self.simulate_view = sv  # type: ignore[attr-defined]
            self._simulate_view = sv
            integrated += 1
        except Exception as e:
            log.debug("SimulateView2 embed failed: %s", e)
            try:
                ttk.Label(self.tab_simulate, text="シミュレーション", font=self._font_default).pack(anchor="w", padx=12, pady=(12, 4))
                ttk.Label(self.tab_simulate, text="準備完了。車両とコースを選択して実行します。", wraplength=760, justify="left").pack(anchor="w", padx=12, pady=4)
                ttk.Separator(self.tab_simulate, orient="horizontal").pack(fill="x", padx=12, pady=8)
                ttk.Label(self.tab_simulate, text="※ 計算ロジックはソルバーで提供", foreground="#666").pack(anchor="w", padx=12)
            except Exception:
                pass
        log.info("App2 tab integration: %d/4 views embedded", integrated)
        try:
            self._setup_create_tab()
        except Exception as e:
            log.debug("create tab setup failed: %s", e)
            try:
                ttk.Label(self.tab_create, text="作成", font=self._font_default).pack(anchor="w", padx=12, pady=(12, 4))
                ttk.Label(self.tab_create, text="作成タブ準備中", wraplength=760, justify="left").pack(anchor="w", padx=12, pady=4)
            except Exception:
                pass
        try:
            self._setup_data_tab()
        except Exception as e:
            log.debug("data tab setup failed: %s", e)
            try:
                ttk.Label(self.tab_data, text="データ", font=self._font_default).pack(anchor="w", padx=12, pady=(12, 4))
                ttk.Label(self.tab_data, text="データタブ準備中", wraplength=760, justify="left").pack(anchor="w", padx=12, pady=4)
            except Exception:
                pass

    def _on_vehicle_saved(self, name: str | None = None) -> None:
        try:
            self._refresh_vehicle_combos_all(name)
        except Exception:
            pass
        try:
            self._refresh_data_tab(select_vehicle=name)
        except Exception:
            pass

    def _on_data_changed(self, kind: str = "", name: str | None = None) -> None:
        k = str(kind or "").lower()
        try:
            if k in ("vehicle", "vehicles", "車両"):
                self._refresh_vehicle_combos_all(name)
            elif k in ("track", "tracks", "コース"):
                self._refresh_track_combos_all(name)
                self._refresh_load_combo()
            else:
                self._refresh_vehicle_combos_all(name)
                self._refresh_track_combos_all(name)
                self._refresh_load_combo()
        except Exception:
            pass

    def _refresh_data_tab(self, select_vehicle: str | None = None, select_track: str | None = None) -> None:
        for attr in ("data_view", "_data_view"):
            try:
                dv = getattr(self, attr, None)
                if dv is None:
                    continue
                if select_vehicle is not None and hasattr(dv, "refresh_vehicles"):
                    try:
                        dv.refresh_vehicles(select=select_vehicle)  # type: ignore[attr-defined]
                    except TypeError:
                        dv.refresh_vehicles()  # type: ignore[attr-defined]
                if select_track is not None and hasattr(dv, "refresh_tracks"):
                    try:
                        dv.refresh_tracks(select=select_track)  # type: ignore[attr-defined]
                    except TypeError:
                        dv.refresh_tracks()  # type: ignore[attr-defined]
                if select_vehicle is None and select_track is None and hasattr(dv, "refresh_all"):
                    try:
                        dv.refresh_all()  # type: ignore[attr-defined]
                    except Exception:
                        pass
            except Exception:
                continue

    def _setup_data_tab(self) -> None:
        tab = getattr(self, "tab_data", None)
        if tab is None:
            return
        try:
            from openlapexe.gui.data_view import DataView as _DataView  # type: ignore
        except Exception as e:
            log.debug("DataView import failed: %s", e)
            raise
        dv = _DataView(tab)
        try:
            dv.pack(fill="both", expand=True, padx=4, pady=4)
        except Exception:
            pass
        self.data_view = dv  # type: ignore[attr-defined]
        self._data_view = dv
        self.create_data_view = dv  # type: ignore[attr-defined]
        try:
            dv.on_data_changed = lambda kind="", name=None: self._on_data_changed(str(kind), name)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            self.bind("<<NotebookTabChanged>>", lambda _e: self._refresh_data_tab(), add="+")
        except Exception:
            pass

    def _setup_create_tab(self) -> None:
        tab = getattr(self, "tab_create", None)
        if tab is None:
            return
        self._create_mode_var = tk.StringVar(value="direct")
        self._creator_mode_var = self._create_mode_var
        self.create_mode_var = self._create_mode_var
        self.mode_var = self._create_mode_var
        try:
            top = ttk.Frame(tab)
            top.pack(side="top", fill="x", padx=6, pady=(6, 4))
            self._create_mode_frame = top
            self.create_mode_frame = top
            self.mode_frame = top
            self._rb_direct = ttk.Radiobutton(top, text="走行ライン直接", variable=self._create_mode_var, value="direct", command=self._on_create_mode_changed)
            self._rb_edge = ttk.Radiobutton(top, text="コース両端→最適化", variable=self._create_mode_var, value="edge", command=self._on_create_mode_changed)
            self.rb_direct = self._rb_direct
            self.rb_edge = self._rb_edge
            self.radio_direct = self._rb_direct
            self.radio_edge = self._rb_edge
            self._rb_direct.pack(side="left", padx=4)
            self._rb_edge.pack(side="left", padx=4)
            self._loop_var = tk.BooleanVar(value=True)
            self.loop_var = self._loop_var
            self.closed_loop_var = self._loop_var
            self._chk_loop = ttk.Checkbutton(top, text="周回コース", variable=self._loop_var, command=self._on_loop_changed)
            self._chk_loop.pack(side="left", padx=8)
            self.loop_checkbutton = self._chk_loop
            self._btn_spline = ttk.Button(top, text="スプライン補間", command=self._on_spline_interpolate)
            self._btn_spline.pack(side="left", padx=4)
            self.spline_button = self._btn_spline
        except Exception:
            pass
        try:
            bot = ttk.Frame(tab)
            bot.pack(side="bottom", fill="x", padx=6, pady=(4, 6))
            self._create_bottom = bot
            self.create_bottom = bot
            self.btn_save = ttk.Button(bot, text="保存", command=self._on_save_track)
            self.save_button = self.btn_save
            self.button_save = self.btn_save
            self.btn_save_track = self.btn_save
            self._btn_save = self.btn_save
            self.btn_save.pack(side="right", padx=4)
            self._save_status_var = tk.StringVar(value="")
            self._save_label = ttk.Label(bot, textvariable=self._save_status_var)
            self._save_label.pack(side="left", padx=6)
            try:
                ttk.Label(bot, text="読込").pack(side="left", padx=(12, 2))
                self._load_combo = ttk.Combobox(bot, width=24, state="readonly")
                self._load_combo.pack(side="left", padx=2)
                self.load_combo = self._load_combo
                self.btn_load = ttk.Button(bot, text="読込", command=lambda: self._on_load_track())
                self.btn_load.pack(side="left", padx=2)
                self.load_button = self.btn_load
                self._refresh_load_combo()
            except Exception:
                pass
        except Exception:
            pass
        self.create_notebook = ttk.Notebook(tab)
        self._create_notebook = self.create_notebook
        self.creator_notebook = self.create_notebook
        self.child_notebook = self.create_notebook
        try:
            self.create_notebook.pack(fill="both", expand=True, padx=4, pady=4)
        except Exception:
            pass
        self.tab_osm = ttk.Frame(self.create_notebook)
        self.tab_import = ttk.Frame(self.create_notebook)
        self.tab_osm_map = self.tab_osm
        self.tab_osmmap = self.tab_osm
        self.create_tab_osm = self.tab_osm
        self.create_tab_import = self.tab_import
        try:
            self.create_notebook.add(self.tab_osm, text="OSM地図")
        except Exception:
            pass
        try:
            self.create_notebook.add(self.tab_import, text="取込")
        except Exception:
            pass
        self._setup_create_osm_tab()
        self._setup_create_import_tab()

    def _setup_create_osm_tab(self) -> None:
        tab = getattr(self, "tab_osm", None)
        if tab is None:
            return
        try:
            pan = ttk.Frame(tab)
            pan.pack(fill="both", expand=True, padx=4, pady=4)
            self._osm_pane = pan
            pw = ttk.PanedWindow(pan, orient="horizontal")
            pw.pack(fill="both", expand=True)
            self._osm_paned = pw
            self._osm_map_frame = ttk.Frame(pw)
            self._osm_edit_frame = ttk.Frame(pw)
            pw.add(self._osm_map_frame, weight=1)
            pw.add(self._osm_edit_frame, weight=1)
        except Exception:
            pan = tab
        self._creator_osm: object | None = None
        self._osm_canvas: object | None = None
        try:
            from openlapexe.gui.course_creator import CourseCreator as _CC  # type: ignore

            cc = _CC(pan)
            try:
                cc.pack(in_=getattr(self, "_osm_edit_frame", pan), side="right", fill="both", expand=True, padx=4, pady=4)
            except Exception:
                try:
                    cc.pack(fill="both", expand=True)
                except Exception:
                    pass
            self._creator_osm = cc
            self.course_creator_osm = cc  # type: ignore[attr-defined]
            self.creator_osm = cc  # type: ignore[attr-defined]
            self.course_creator = cc  # type: ignore[attr-defined]
            self._course_creator = cc
            self.creator = cc  # type: ignore[attr-defined]
            self.create_creator = cc  # type: ignore[attr-defined]
        except Exception as e:
            log.debug("CourseCreator osm embed failed: %s", e)
            try:
                ttk.Label(pan, text="CourseCreator 読み込み失敗", foreground="#888").pack(fill="x", padx=6, pady=4)
            except Exception:
                pass
        try:
            from openlapexe.gui.osm_canvas import OSMCanvas as _OC  # type: ignore

            oc = _OC(pan, width=420, height=360)
            try:
                oc.pack(in_=getattr(self, "_osm_map_frame", pan), side="left", fill="both", expand=True, padx=4, pady=4)
            except Exception:
                try:
                    oc.pack(fill="both", expand=True)
                except Exception:
                    pass
            self._osm_canvas = oc
            self.osm_canvas = oc  # type: ignore[attr-defined]
            self.create_osm_canvas = oc  # type: ignore[attr-defined]
            try:
                oc.closed_loop = self._loop_closed()
            except Exception:
                pass
            try:
                oc.bind("<ButtonRelease-1>", lambda e: self._sync_osm_to_creator(e), add="+")
            except Exception:
                pass
            try:
                oc.bind("<ButtonRelease-2>", lambda e: self._sync_osm_to_creator(e), add="+")
                oc.bind("<ButtonRelease-3>", lambda e: self._sync_osm_to_creator(e), add="+")
            except Exception:
                pass
            try:
                # Ctrl/Shift+ホイールで選択写真をリサイズ（修飾なしは通常ズームのまま）
                oc.bind("<MouseWheel>", lambda e: self._on_photo_wheel(e), add="+")
                oc.bind("<Button-4>", lambda e: self._on_photo_wheel(e, 1), add="+")
                oc.bind("<Button-5>", lambda e: self._on_photo_wheel(e, -1), add="+")
            except Exception:
                pass
        except Exception as e:
            log.debug("OSMCanvas embed failed: %s", e)
            try:
                ttk.Label(pan, text="OSM地図 読み込み失敗", foreground="#888").pack(fill="x", padx=6, pady=4)
            except Exception:
                pass
        if self._creator_osm is None and self._osm_canvas is None:
            try:
                ttk.Label(tab, text="OSM地図 準備中", foreground="#888").pack(expand=True)
            except Exception:
                pass
        try:
            bar = ttk.Frame(tab)
            bar.pack(side="bottom", fill="x", padx=4, pady=4)
            self._photo_bar = bar
            self.photo_bar = bar
            self._photo_add_btn = ttk.Button(bar, text="写真追加", command=self._on_photo_add)
            self._photo_add_btn.pack(side="left", padx=2)
            self.photo_add_button = self._photo_add_btn
            self._photo_place_btn = ttk.Button(bar, text="配置", command=self._on_photo_place)
            self._photo_place_btn.pack(side="left", padx=2)
            self.photo_place_button = self._photo_place_btn
            self._photo_del_btn = ttk.Button(bar, text="削除", command=self._on_photo_delete)
            self._photo_del_btn.pack(side="left", padx=2)
            self.photo_delete_button = self._photo_del_btn
            try:
                self._photo_locked_var = tk.BooleanVar(value=False)
                self._photo_lock_btn = ttk.Checkbutton(bar, text="🔒 ロック", variable=self._photo_locked_var, command=self._on_photo_lock)
                self._photo_lock_btn.pack(side="left", padx=2)
                self.photo_lock_button = self._photo_lock_btn
                self._photo_lock_button = self._photo_lock_btn
                self.photo_lock_var = self._photo_locked_var
                self._photo_locked_button = self._photo_lock_btn
            except Exception:
                try:
                    self._photo_locked_var = tk.BooleanVar(value=False)
                    self._photo_lock_btn = ttk.Button(bar, text="🔒 ロック", command=self._on_photo_lock)
                    self._photo_lock_btn.pack(side="left", padx=2)
                    self.photo_lock_button = self._photo_lock_btn
                except Exception:
                    pass
            try:
                self.interact_mode_var = tk.StringVar(value="trace")
                self._interact_mode_var = self.interact_mode_var
                self._interact_mode = "trace"
                self.interact_mode = "trace"
                self.photo_interact_mode_var = self.interact_mode_var
                self._photo_interact_mode_var = self.interact_mode_var
            except Exception:
                try:
                    self.interact_mode_var = tk.StringVar(value="trace")
                    self._interact_mode_var = self.interact_mode_var
                except Exception:
                    self.interact_mode_var = None  # type: ignore
                    self._interact_mode_var = None  # type: ignore
            try:
                self._rb_trace = ttk.Radiobutton(bar, text="trace", variable=self.interact_mode_var, value="trace", command=self._on_interact_mode_changed)
                self._rb_place = ttk.Radiobutton(bar, text="place", variable=self.interact_mode_var, value="place", command=self._on_interact_mode_changed)
                self._rb_edit = ttk.Radiobutton(bar, text="edit", variable=self.interact_mode_var, value="edit", command=self._on_interact_mode_changed)
                self._rb_trace.pack(side="left", padx=2)
                self._rb_place.pack(side="left", padx=2)
                self._rb_edit.pack(side="left", padx=2)
                self.rb_trace = self._rb_trace
                self.rb_place = self._rb_place
                self.rb_edit = self._rb_edit
                self.radio_trace = self._rb_trace
                self.radio_place = self._rb_place
                self.radio_edit = self._rb_edit
                self.interact_radio_trace = self._rb_trace
                self.interact_radio_place = self._rb_place
                self.interact_radio_edit = self._rb_edit
            except Exception:
                pass
            try:
                oc0 = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
                if oc0 is not None and hasattr(oc0, "set_interact_mode"):
                    try:
                        oc0.set_interact_mode("trace")
                    except Exception:
                        pass
                var0 = getattr(self, "interact_mode_var", None)
                if var0 is not None and hasattr(var0, "set"):
                    try:
                        var0.set("trace")
                    except Exception:
                        pass
                self._interact_mode = "trace"
                self.interact_mode = "trace"
            except Exception:
                pass
            ttk.Label(bar, text="不透明度").pack(side="left", padx=(8, 2))
            self._photo_opacity = tk.IntVar(value=50)
            self._photo_scale = ttk.Scale(bar, from_=0, to=100, variable=self._photo_opacity, command=lambda _v: self._on_photo_opacity())
            self._photo_scale.pack(side="left", padx=2, fill="x", expand=True)
            self.photo_opacity_scale = self._photo_scale
            ttk.Label(bar, text="大きさ").pack(side="left", padx=(8, 2))
            self._photo_size = tk.IntVar(value=100)
            self._photo_size_scale = ttk.Scale(bar, from_=1, to=400, variable=self._photo_size, command=lambda _v: self._on_photo_size())
            self._photo_size_scale.pack(side="left", padx=2, fill="x", expand=True)
            self.photo_size_scale = self._photo_size_scale
            self._photo_size_label = ttk.Label(bar, text="100%", width=5, anchor="e")
            self._photo_size_label.pack(side="left", padx=(0, 2))
            self.photo_size_label = self._photo_size_label
            self._photo_syncing = False
            self._photo_listbox = tk.Listbox(bar, height=2, exportselection=False)
            self._photo_listbox.pack(side="left", padx=4, fill="x", expand=True)
            self.photo_listbox = self._photo_listbox
            try:
                self._photo_listbox.bind("<<ListboxSelect>>", lambda _e: self._on_photo_select())
            except Exception:
                pass
            try:
                self._photo_listbox.bind("<Delete>", lambda e: self._on_photo_delete_key(e), add="+")
                self._photo_listbox.bind("<BackSpace>", lambda e: self._on_photo_delete_key(e), add="+")
                self._photo_listbox.bind("<Escape>", lambda e: self._on_photo_escape(e), add="+")
                self._photo_listbox.bind("<KeyPress-Delete>", lambda e: self._on_photo_delete_key(e), add="+")
            except Exception:
                pass
            try:
                oc0 = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
                if oc0 is not None:
                    oc0.bind("<Delete>", lambda e: self._on_photo_delete_key(e), add="+")
                    oc0.bind("<BackSpace>", lambda e: self._on_photo_delete_key(e), add="+")
                    oc0.bind("<Escape>", lambda e: self._on_photo_escape(e), add="+")
                    oc0.bind("<KeyPress-Delete>", lambda e: self._on_photo_delete_key(e), add="+")
                    try:
                        oc0.focus_set()
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                self.set_status("photo: drag/handles to move/resize, Delete to remove, Esc to disarm")
            except Exception:
                pass
        except Exception:
            pass
        try:
            self._setup_waypoint_ui()
        except Exception as e:
            log.debug("waypoint ui setup failed: %s", e)

    def _setup_waypoint_ui(self) -> None:
        tab = getattr(self, "tab_osm", None)
        if tab is None:
            return
        try:
            wp_outer = ttk.Frame(tab, width=280)
            wp_outer.pack(side="right", fill="y", padx=4, pady=4)
            try:
                wp_outer.pack_propagate(False)
            except Exception:
                pass
            self._waypoint_frame = wp_outer  # type: ignore[attr-defined]
            self.waypoint_frame = wp_outer  # type: ignore[attr-defined]
        except Exception:
            wp_outer = tab
            self._waypoint_frame = wp_outer  # type: ignore[attr-defined]
        try:
            ctrl = ttk.Frame(wp_outer)
            ctrl.pack(side="top", fill="x", padx=2, pady=2)
            self._waypoint_ctrl = ctrl  # type: ignore[attr-defined]
            self._btn_undo = ttk.Button(ctrl, text="Undo", command=self._on_waypoint_undo)
            self._btn_undo.pack(side="left", padx=2)
            self.btn_undo = self._btn_undo  # type: ignore[attr-defined]
            self.undo_button = self._btn_undo  # type: ignore[attr-defined]
            self._btn_clear = ttk.Button(ctrl, text="Clear All", command=self._on_waypoint_clear)
            self._btn_clear.pack(side="left", padx=2)
            self.btn_clear = self._btn_clear  # type: ignore[attr-defined]
            self.clear_button = self._btn_clear  # type: ignore[attr-defined]
            self.btn_clear_all = self._btn_clear  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            tv_frame = ttk.Frame(wp_outer)
            tv_frame.pack(side="top", fill="both", expand=True, padx=2, pady=2)
            self._waypoint_tree_frame = tv_frame  # type: ignore[attr-defined]
            vsb = ttk.Scrollbar(tv_frame, orient="vertical")
            self._waypoint_vsb = vsb  # type: ignore[attr-defined]
            tree = ttk.Treeview(tv_frame, columns=("no", "lat", "lon"), show="headings", height=8, yscrollcommand=vsb.set)
            tree.heading("no", text="No")
            tree.heading("lat", text="lat")
            tree.heading("lon", text="lon")
            tree.column("no", width=40, anchor="center", stretch=False)
            tree.column("lat", width=110, anchor="center")
            tree.column("lon", width=110, anchor="center")
            vsb.config(command=tree.yview)
            tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            self._waypoint_tree = tree  # type: ignore[attr-defined]
            self.waypoint_tree = tree  # type: ignore[attr-defined]
            self.treeview = tree  # type: ignore[attr-defined]
            self.waypoint_view = tree  # type: ignore[attr-defined]
            self.waypoint_list = tree  # type: ignore[attr-defined]
        except Exception as e:
            log.debug("waypoint tree setup failed: %s", e)
            return
        try:
            self.bind("<Control-z>", lambda e: self._on_waypoint_undo(), add="+")
            self.bind("<Control-Z>", lambda e: self._on_waypoint_undo(), add="+")
        except Exception:
            pass
        try:
            self._refresh_waypoint_tree()
        except Exception:
            pass
        try:
            self._wrap_creator_save_hook()
            self._update_save_button_state()
        except Exception:
            pass

    def _refresh_waypoint_tree(self) -> None:
        try:
            tree = getattr(self, "_waypoint_tree", None)
            if tree is None:
                return
            try:
                for iid in tree.get_children():
                    tree.delete(iid)
            except Exception:
                pass
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            if oc is None or not hasattr(oc, "points_latlon"):
                return
            for idx, (lat, lon) in enumerate(list(oc.points_latlon)):  # type: ignore[arg-type]
                try:
                    tree.insert("", "end", values=(str(idx + 1), f"{float(lat):.7f}", f"{float(lon):.7f}"))
                except Exception:
                    continue
        except Exception:
            pass

    def _append_waypoint_row(self, lat: float, lon: float) -> None:
        try:
            tree = getattr(self, "_waypoint_tree", None)
            if tree is None:
                return
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            try:
                n = len(list(oc.points_latlon)) if oc is not None and hasattr(oc, "points_latlon") else len(tree.get_children()) + 1
            except Exception:
                n = len(tree.get_children()) + 1
            tree.insert("", "end", values=(str(n), f"{float(lat):.7f}", f"{float(lon):.7f}"))
        except Exception:
            pass

    def _pop_waypoint_row(self) -> None:
        try:
            tree = getattr(self, "_waypoint_tree", None)
            if tree is None:
                return
            children = tree.get_children()
            if children:
                tree.delete(children[-1])
        except Exception:
            pass

    def _clear_waypoint_tree(self) -> None:
        try:
            tree = getattr(self, "_waypoint_tree", None)
            if tree is None:
                return
            for iid in tree.get_children():
                tree.delete(iid)
        except Exception:
            pass

    def _on_waypoint_undo(self, event: object | None = None) -> None:
        undone = False
        try:
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            cc = getattr(self, "_creator_osm", None) or getattr(self, "course_creator", None) or getattr(self, "creator", None)
            oc_points = list(getattr(oc, "points_latlon", []) or []) if oc is not None else []
            if oc is not None and oc_points:
                try:
                    oc.points_latlon.pop()
                    if hasattr(oc, "points_xy") and oc.points_xy:
                        oc.points_xy.pop()
                    if hasattr(oc, "points_zone") and oc.points_zone:
                        oc.points_zone.pop()
                    try:
                        if hasattr(oc, "_draw_points_only"):
                            oc._draw_points_only()  # type: ignore[attr-defined]
                        elif hasattr(oc, "_draw_points"):
                            oc._draw_points()  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    undone = True
                except Exception:
                    pass
                if undone and cc is not None:
                    try:
                        lst = list(getattr(oc, "points_xy", []) or [])
                        if hasattr(cc, "set_points"):
                            try:
                                import inspect as _ins
                                sig = _ins.signature(getattr(cc, "set_points"))
                                if "push_undo" in sig.parameters:
                                    cc.set_points(lst, push_undo=False)  # type: ignore[attr-defined]
                                else:
                                    cc.set_points(lst)  # type: ignore[attr-defined]
                            except Exception:
                                try:
                                    cc.set_points(lst, push_undo=False)  # type: ignore[attr-defined]
                                except Exception:
                                    cc.points_xy = lst  # type: ignore[attr-defined]
                        else:
                            try:
                                cc.points_xy = lst  # type: ignore[attr-defined]
                            except Exception:
                                pass
                    except Exception:
                        pass
            elif cc is not None and hasattr(cc, "undo"):
                try:
                    if cc.undo():
                        undone = True
                except Exception:
                    pass
        except Exception:
            pass
        if undone:
            try:
                self._pop_waypoint_row()
            except Exception:
                pass
        try:
            self._update_save_button_state()
        except Exception:
            pass
        try:
            return None  # type: ignore[return-value]
        except Exception:
            pass

    def _on_waypoint_clear(self) -> None:
        try:
            if not messagebox.askyesno("確認", "全てのウェイポイントを削除しますか？", parent=self):
                return
        except TypeError:
            try:
                if not messagebox.askyesno("確認", "全てのウェイポイントを削除しますか？"):
                    return
            except Exception:
                return
        except Exception:
            try:
                if not messagebox.askyesno("確認", "全てのウェイポイントを削除しますか？", parent=self):
                    return
            except Exception:
                return
        try:
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            if oc is not None:
                try:
                    if hasattr(oc, "points_latlon"):
                        oc.points_latlon.clear()  # type: ignore[attr-defined]
                    if hasattr(oc, "points_xy"):
                        oc.points_xy.clear()  # type: ignore[attr-defined]
                    if hasattr(oc, "points_zone"):
                        oc.points_zone.clear()  # type: ignore[attr-defined]
                    try:
                        if hasattr(oc, "_draw_points_only"):
                            oc._draw_points_only()  # type: ignore[attr-defined]
                        elif hasattr(oc, "_draw_points"):
                            oc._draw_points()  # type: ignore[attr-defined]
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass
        try:
            for attr in ("_creator_osm", "_creator_import", "course_creator", "creator", "_course_creator"):
                obj = getattr(self, attr, None)
                if obj is not None:
                    try:
                        if hasattr(obj, "set_points"):
                            try:
                                import inspect as _ins2
                                sig2 = _ins2.signature(getattr(obj, "set_points"))
                                if "push_undo" in sig2.parameters:
                                    obj.set_points([], push_undo=False)  # type: ignore[attr-defined]
                                else:
                                    obj.set_points([])  # type: ignore[attr-defined]
                            except Exception:
                                try:
                                    obj.set_points([])  # type: ignore[attr-defined]
                                except Exception:
                                    pass
                        elif hasattr(obj, "points_xy"):
                            obj.points_xy.clear()  # type: ignore[attr-defined]
                    except Exception:
                        continue
        except Exception:
            pass
        try:
            self._clear_waypoint_tree()
        except Exception:
            pass
        try:
            self._update_save_button_state()
        except Exception:
            pass

    def _update_save_button_state(self) -> None:
        try:
            btn = getattr(self, "btn_save", None) or getattr(self, "_btn_save", None) or getattr(self, "save_button", None)
            if btn is None:
                return
            n = 0
            try:
                cc = getattr(self, "_creator_osm", None) or getattr(self, "course_creator", None) or getattr(self, "creator", None)
                if cc is not None and hasattr(cc, "points_xy"):
                    n = len(list(getattr(cc, "points_xy") or []))
                if n < 2:
                    oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
                    if oc is not None and hasattr(oc, "points_latlon"):
                        n2 = len(list(getattr(oc, "points_latlon") or []))
                        if n2 > n:
                            n = n2
            except Exception:
                pass
            try:
                if n < 2:
                    btn.configure(state="disabled")
                else:
                    btn.configure(state="normal")
            except Exception:
                try:
                    btn["state"] = "disabled" if n < 2 else "normal"  # type: ignore
                except Exception:
                    pass
        except Exception:
            pass

    def _wrap_creator_save_hook(self) -> None:
        for attr in ("_creator_osm", "_creator_import"):
            try:
                obj = getattr(self, attr, None)
                if obj is None or getattr(obj, "_waypoint_wrapped", False):
                    continue
                orig = getattr(obj, "set_points", None)
                if orig is None:
                    continue
                self_ref = self

                def _make_wrapper(orig_fn, _obj):  # type: ignore
                    def _wrapped(pts, push_undo=True):  # type: ignore
                        try:
                            try:
                                import inspect as _ins3
                                sig3 = _ins3.signature(orig_fn)
                                if "push_undo" in sig3.parameters:
                                    res = orig_fn(pts, push_undo=push_undo)
                                else:
                                    res = orig_fn(pts)
                            except Exception:
                                try:
                                    res = orig_fn(pts, push_undo=push_undo)  # type: ignore
                                except TypeError:
                                    res = orig_fn(pts)  # type: ignore
                            try:
                                if _obj is getattr(self_ref, "_creator_osm", None):
                                    if pts is None or (hasattr(pts, "__len__") and len(list(pts)) == 0):  # type: ignore
                                        self_ref._clear_waypoint_tree()
                                    else:
                                        oc2 = getattr(self_ref, "_osm_canvas", None) or getattr(self_ref, "osm_canvas", None)
                                        if oc2 is not None and hasattr(oc2, "points_latlon") and len(list(oc2.points_latlon)) > 0:
                                            self_ref._refresh_waypoint_tree()
                                        else:
                                            pass
                            except Exception:
                                pass
                            try:
                                self_ref._update_save_button_state()
                            except Exception:
                                pass
                            return res
                        except Exception as e:
                            raise e

                    return _wrapped

                obj.set_points = _make_wrapper(orig, obj)  # type: ignore[assignment]
                obj._waypoint_wrapped = True  # type: ignore[attr-defined]
            except Exception:
                continue

    def _photo_selection(self) -> int | None:
        try:
            lb = getattr(self, "_photo_listbox", None)
            sel = lb.curselection() if lb is not None else ()
            if not sel:
                return None
            txt = lb.get(int(sel[0]))
            return int(str(txt).split(":")[0])
        except Exception:
            return None

    def _refresh_photo_list(self) -> None:
        try:
            lb = getattr(self, "_photo_listbox", None)
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            if lb is None or oc is None or not hasattr(oc, "list_photos"):
                return
            keep: int | None = None
            try:
                sel = lb.curselection()
                if sel:
                    keep = int(sel[0])
            except Exception:
                keep = None
            lb.delete(0, "end")
            count = 0
            for pid in oc.list_photos():
                rec = oc.get_photo(pid) if hasattr(oc, "get_photo") else None
                if rec is None:
                    lb.insert("end", f"{pid}")
                else:
                    try:
                        pct = float(rec.get("scale", 1.0)) * 100.0
                    except Exception:
                        pct = 100.0
                    line = f"{pid}: {pathlib.Path(str(rec.get('path', ''))).name} @{float(rec.get('opacity', 0.5)):.2f} x{pct:.0f}%"
                    try:
                        if rec.get("locked"):
                            line += " 🔒"
                    except Exception:
                        pass
                    lb.insert("end", line)
                count += 1
            if keep is not None and 0 <= keep < count:
                try:
                    lb.selection_set(keep)
                    lb.activate(keep)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_photo_add(self) -> None:
        try:
            from tkinter import filedialog
        except Exception:
            return
        oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
        if oc is None or not hasattr(oc, "add_photo"):
            return
        try:
            path = filedialog.askopenfilename(parent=self, title="写真を選択", filetypes=[("画像", "*.png *.gif *.jpg *.jpeg *.ppm *.pgm"), ("すべて", "*.*")])
        except TypeError:
            try:
                path = filedialog.askopenfilename(title="写真を選択")
            except Exception:
                return
        except Exception:
            return
        if not path:
            return
        try:
            op = float(getattr(self, "_photo_opacity", None).get()) / 100.0 if getattr(self, "_photo_opacity", None) is not None else 0.5
        except Exception:
            op = 0.5
        pid = None
        try:
            pid = oc.add_photo(str(path), opacity=op)
        except Exception as e:
            try:
                messagebox.showerror("写真", f"読込失敗: {e}", parent=self)
            except Exception:
                pass
            return
        try:
            sz = float(getattr(self, "_photo_size", None).get()) if getattr(self, "_photo_size", None) is not None else 100.0
        except Exception:
            sz = 100.0
        if pid is not None and abs(sz - 100.0) > 0.01 and hasattr(oc, "set_photo_scale"):
            try:
                oc.set_photo_scale(int(pid), min(8.0, max(0.01, sz / 100.0)))
            except Exception:
                pass
        self._refresh_photo_list()

    def _on_interact_mode_changed(self) -> None:
        try:
            var = getattr(self, "interact_mode_var", None) or getattr(self, "_interact_mode_var", None)
            mode = str(var.get()).strip().lower() if var is not None and hasattr(var, "get") else "trace"
            if mode not in ("trace", "place", "edit"):
                mode = "trace"
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            if oc is not None and hasattr(oc, "set_interact_mode"):
                try:
                    oc.set_interact_mode(mode)
                except Exception:
                    try:
                        oc._interact_mode = mode  # type: ignore
                        oc.interact_mode = mode  # type: ignore
                        if hasattr(oc, "interact_mode_var") and hasattr(oc.interact_mode_var, "set"):
                            oc.interact_mode_var.set(mode)
                    except Exception:
                        pass
            else:
                try:
                    if oc is not None:
                        oc._interact_mode = mode  # type: ignore
                        oc.interact_mode = mode  # type: ignore
                except Exception:
                    pass
            try:
                self._interact_mode = mode
                self.interact_mode = mode
            except Exception:
                pass
            if mode == "trace":
                try:
                    if oc is not None and hasattr(oc, "disarm_photo_place"):
                        oc.disarm_photo_place()
                    elif oc is not None and hasattr(oc, "_placing_photo_id"):
                        oc._placing_photo_id = None  # type: ignore
                except Exception:
                    pass
                try:
                    for r in getattr(oc, "_photos", []) if oc is not None else []:
                        r["selected"] = False
                    if oc is not None:
                        oc._selected_photo_id = None
                except Exception:
                    pass
                try:
                    lb = getattr(self, "_photo_listbox", None)
                    if lb is not None:
                        lb.selection_clear(0, "end")
                        lb.selection_clear(0, tk.END)
                except Exception:
                    pass
            elif mode == "edit":
                try:
                    if oc is not None and hasattr(oc, "disarm_photo_place"):
                        oc.disarm_photo_place()
                    elif oc is not None and hasattr(oc, "_placing_photo_id"):
                        oc._placing_photo_id = None  # type: ignore
                except Exception:
                    pass
            elif mode == "place":
                try:
                    if oc is not None and getattr(oc, "_placing_photo_id", None) is None:
                        sel = self._photo_selection()
                        if sel is None and hasattr(oc, "_selected_photo_id"):
                            sel = getattr(oc, "_selected_photo_id")
                        if sel is not None and hasattr(oc, "arm_photo_place"):
                            oc.arm_photo_place(int(sel))
                except Exception:
                    pass
            try:
                self._refresh_mode_ui()
            except Exception:
                pass
        except Exception:
            pass

    def set_interact_mode(self, mode: str) -> bool:
        try:
            m = str(mode).strip().lower()
            if m not in ("trace", "place", "edit"):
                return False
            var = getattr(self, "interact_mode_var", None) or getattr(self, "_interact_mode_var", None)
            if var is not None and hasattr(var, "set"):
                try:
                    var.set(m)
                except Exception:
                    pass
            try:
                self._interact_mode = m
                self.interact_mode = m
            except Exception:
                pass
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            if oc is not None and hasattr(oc, "set_interact_mode"):
                try:
                    oc.set_interact_mode(m)
                except Exception:
                    pass
            else:
                try:
                    if oc is not None:
                        oc._interact_mode = m  # type: ignore
                        oc.interact_mode = m  # type: ignore
                except Exception:
                    pass
            self._on_interact_mode_changed()
            return True
        except Exception:
            return False

    def get_interact_mode(self) -> str:
        try:
            var = getattr(self, "interact_mode_var", None) or getattr(self, "_interact_mode_var", None)
            if var is not None and hasattr(var, "get"):
                gv = var.get()
                if isinstance(gv, str) and gv in ("trace", "place", "edit"):
                    return gv
        except Exception:
            pass
        try:
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            if oc is not None and hasattr(oc, "get_interact_mode"):
                gm = oc.get_interact_mode()
                if isinstance(gm, str) and gm in ("trace", "place", "edit"):
                    return gm
        except Exception:
            pass
        try:
            v = getattr(self, "_interact_mode", None)
            if isinstance(v, str) and v in ("trace", "place", "edit"):
                return v
        except Exception:
            pass
        return "trace"

    def set_photo_interact_mode(self, mode: str) -> bool:
        return self.set_interact_mode(mode)

    def get_photo_interact_mode(self) -> str:
        return self.get_interact_mode()

    def set_mode(self, mode: str) -> bool:
        if str(mode).lower() in ("trace", "place", "edit"):
            return self.set_interact_mode(mode)
        return False

    def _on_photo_place(self) -> None:
        oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
        pid = self._photo_selection()
        if oc is None or pid is None or not hasattr(oc, "arm_photo_place"):
            return
        try:
            self.set_interact_mode("place")
        except Exception:
            pass
        try:
            if oc.arm_photo_place(pid):
                self.set_status("写真配置: 地図上をクリック (drag/handlesで調整)")
        except Exception:
            pass
        try:
            self._refresh_mode_ui()
        except Exception:
            pass

    def _on_photo_delete(self) -> None:
        oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
        pid = self._photo_selection()
        if oc is None or pid is None or not hasattr(oc, "remove_photo"):
            return
        try:
            locked = False
            try:
                if hasattr(oc, "is_photo_locked"):
                    locked = bool(oc.is_photo_locked(pid))  # type: ignore[attr-defined]
                elif hasattr(oc, "get_photo_locked"):
                    locked = bool(oc.get_photo_locked(pid))  # type: ignore[attr-defined]
                else:
                    rec0 = oc.get_photo(pid) if hasattr(oc, "get_photo") else None
                    locked = bool(rec0.get("locked")) if rec0 else False
            except Exception:
                locked = False
            if locked:
                try:
                    self.set_status("photo locked — delete ignored (unlock first)")
                except Exception:
                    pass
                return
        except Exception:
            pass
        try:
            oc.remove_photo(pid)
        except Exception as e:
            try:
                messagebox.showerror("写真", f"削除失敗: {e}", parent=self)
            except TypeError:
                try:
                    messagebox.showerror("写真", f"削除失敗: {e}")
                except Exception:
                    pass
            except Exception:
                try:
                    messagebox.showerror("写真", f"削除失敗: {e}", parent=self)
                except Exception:
                    pass
        self._refresh_photo_list()
        try:
            self.set_status("photo: drag/handles to move/resize, Delete to remove, Esc to disarm")
        except Exception:
            pass
        try:
            self._refresh_mode_ui()
        except Exception:
            pass

    def _on_photo_delete_key(self, event: object | None = None) -> str | None:
        try:
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            pid = self._photo_selection()
            if oc is None or pid is None or not hasattr(oc, "remove_photo"):
                return None
            try:
                locked = False
                try:
                    if hasattr(oc, "is_photo_locked"):
                        locked = bool(oc.is_photo_locked(pid))  # type: ignore[attr-defined]
                    elif hasattr(oc, "get_photo_locked"):
                        locked = bool(oc.get_photo_locked(pid))  # type: ignore[attr-defined]
                    else:
                        rec0 = oc.get_photo(pid) if hasattr(oc, "get_photo") else None
                        locked = bool(rec0.get("locked")) if rec0 else False
                except Exception:
                    locked = False
                if locked:
                    try:
                        self.set_status("photo locked — delete ignored (unlock first)")
                    except Exception:
                        pass
                    return None
            except Exception:
                pass
            try:
                oc.remove_photo(pid)
            except Exception as e:
                try:
                    messagebox.showerror("写真", f"削除失敗: {e}", parent=self)
                except TypeError:
                    try:
                        messagebox.showerror("写真", f"削除失敗: {e}")
                    except Exception:
                        pass
                except Exception:
                    try:
                        messagebox.showerror("写真", f"削除失敗: {e}", parent=self)
                    except Exception:
                        pass
            try:
                self._refresh_photo_list()
            except Exception:
                pass
            try:
                self.set_status("photo removed (Delete); drag/handles to adjust")
            except Exception:
                pass
            try:
                self._refresh_mode_ui()
            except Exception:
                pass
        except Exception:
            pass
        return None

    def _on_photo_escape(self, event: object | None = None) -> str | None:
        try:
            try:
                lb = getattr(self, "_photo_listbox", None)
                if lb is not None:
                    try:
                        lb.selection_clear(0, "end")
                    except Exception:
                        pass
                    try:
                        lb.selection_clear(0, tk.END)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
                if oc is not None:
                    disarmed = False
                    if hasattr(oc, "disarm_photo_place"):
                        try:
                            oc.disarm_photo_place()
                            disarmed = True
                        except Exception as e:
                            try:
                                messagebox.showerror("写真", f"解除失敗: {e}", parent=self)
                            except Exception:
                                pass
                    elif hasattr(oc, "cancel_photo_place"):
                        try:
                            oc.cancel_photo_place()
                            disarmed = True
                        except Exception as e:
                            try:
                                messagebox.showerror("写真", f"解除失敗: {e}", parent=self)
                            except Exception:
                                pass
                    elif hasattr(oc, "arm_photo_place"):
                        try:
                            if hasattr(oc, "_placing_photo_id"):
                                oc._placing_photo_id = None  # type: ignore[attr-defined]
                                disarmed = True
                            if hasattr(oc, "_armed_photo_id"):
                                oc._armed_photo_id = None  # type: ignore[attr-defined]
                                disarmed = True
                        except Exception:
                            pass
                    else:
                        try:
                            if hasattr(oc, "_placing_photo_id"):
                                oc._placing_photo_id = None  # type: ignore[attr-defined]
                            if hasattr(oc, "_armed_photo_id"):
                                oc._armed_photo_id = None  # type: ignore[attr-defined]
                        except Exception:
                            pass
                    _ = disarmed
                    try:
                        for r in getattr(oc, "_photos", []):
                            r["selected"] = False
                        oc._selected_photo_id = None
                        oc._dragging_photo_id = None
                        oc._dragging_photo = None
                        oc._dragging_handle = None
                    except Exception:
                        pass
                    try:
                        if hasattr(oc, "set_interact_mode"):
                            oc.set_interact_mode("trace")
                        else:
                            oc._interact_mode = "trace"  # type: ignore
                            oc.interact_mode = "trace"  # type: ignore
                            if hasattr(oc, "interact_mode_var") and hasattr(oc.interact_mode_var, "set"):
                                oc.interact_mode_var.set("trace")
                    except Exception:
                        pass
                    try:
                        self._request_redraw() if hasattr(oc, "_request_redraw") else None
                    except Exception:
                        pass
            except Exception as e:
                try:
                    messagebox.showerror("写真", f"解除失敗: {e}", parent=self)
                except Exception:
                    pass
            try:
                var = getattr(self, "interact_mode_var", None) or getattr(self, "_interact_mode_var", None)
                if var is not None and hasattr(var, "set"):
                    var.set("trace")
                self._interact_mode = "trace"
                self.interact_mode = "trace"
            except Exception:
                pass
            try:
                self.set_status("photo: drag/handles to move/resize, Esc disarms placement")
            except Exception:
                pass
            try:
                self._refresh_mode_ui()
            except Exception:
                pass
        except Exception:
            pass
        return None

    def _on_photo_opacity(self) -> None:
        oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
        pid = self._photo_selection()
        if oc is None or pid is None or not hasattr(oc, "set_photo_opacity"):
            return
        try:
            op = float(getattr(self, "_photo_opacity", None).get()) / 100.0
        except Exception:
            return
        try:
            oc.set_photo_opacity(pid, op)
        except Exception:
            pass
        self._refresh_photo_list()

    def _on_photo_size(self) -> None:
        if getattr(self, "_photo_syncing", False):
            return
        oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
        pid = self._photo_selection()
        if oc is None or pid is None or not hasattr(oc, "set_photo_scale"):
            return
        try:
            locked = False
            try:
                if hasattr(oc, "is_photo_locked"):
                    locked = bool(oc.is_photo_locked(pid))  # type: ignore[attr-defined]
                elif hasattr(oc, "get_photo_locked"):
                    locked = bool(oc.get_photo_locked(pid))  # type: ignore[attr-defined]
                else:
                    rec0 = oc.get_photo(pid) if hasattr(oc, "get_photo") else None
                    locked = bool(rec0.get("locked")) if rec0 else False
            except Exception:
                locked = False
            if locked:
                try:
                    self.set_status("photo locked — size change ignored")
                except Exception:
                    pass
                return
        except Exception:
            pass
        try:
            pct = float(getattr(self, "_photo_size", None).get())
        except Exception:
            return
        pct = min(400.0, max(1.0, float(pct)))
        self._sync_photo_size_label(pct)
        try:
            oc.set_photo_scale(pid, min(8.0, max(0.01, pct / 100.0)))
        except Exception:
            pass
        self._refresh_photo_list()
        try:
            self._refresh_mode_ui()
        except Exception:
            pass

    def _on_photo_select(self) -> None:
        oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
        pid = self._photo_selection()
        if oc is None or pid is None:
            return
        rec = oc.get_photo(pid) if hasattr(oc, "get_photo") else None
        if not rec:
            return
        try:
            pct = int(round(float(rec.get("scale", 1.0)) * 100.0))
        except Exception:
            pct = 100
        pct = min(400, max(1, pct))
        self._photo_syncing = True
        try:
            sv = getattr(self, "_photo_size", None)
            if sv is not None:
                sv.set(pct)
            self._sync_photo_size_label(pct)
        finally:
            self._photo_syncing = False
        try:
            locked = False
            try:
                if hasattr(oc, "is_photo_locked"):
                    locked = bool(oc.is_photo_locked(pid))  # type: ignore[attr-defined]
                elif hasattr(oc, "get_photo_locked"):
                    locked = bool(oc.get_photo_locked(pid))  # type: ignore[attr-defined]
                else:
                    locked = bool(rec.get("locked")) if rec else False
            except Exception:
                locked = False
            var = getattr(self, "_photo_locked_var", None)
            if var is not None:
                try:
                    var.set(bool(locked))
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._refresh_mode_ui()
        except Exception:
            pass

    def _on_photo_lock(self) -> None:
        try:
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            pid = self._photo_selection()
            if oc is None or pid is None:
                try:
                    self.set_status("photo locked — no selection")
                except Exception:
                    pass
                return
            if not hasattr(oc, "set_photo_locked"):
                try:
                    self.set_status("photo locked — not supported")
                except Exception:
                    pass
                return
            locked = False
            try:
                if hasattr(oc, "is_photo_locked"):
                    locked = bool(oc.is_photo_locked(pid))  # type: ignore[attr-defined]
                elif hasattr(oc, "get_photo_locked"):
                    locked = bool(oc.get_photo_locked(pid))  # type: ignore[attr-defined]
                else:
                    rec0 = oc.get_photo(pid) if hasattr(oc, "get_photo") else None
                    locked = bool(rec0.get("locked")) if rec0 else False
            except Exception:
                locked = False
            try:
                oc.set_photo_locked(pid, not locked)  # type: ignore[attr-defined]
            except Exception as e:
                try:
                    messagebox.showerror("写真", f"ロック切替失敗: {e}", parent=self)
                except TypeError:
                    try:
                        messagebox.showerror("写真", f"ロック切替失敗: {e}")
                    except Exception:
                        pass
                except Exception:
                    try:
                        messagebox.showerror("写真", f"ロック切替失敗: {e}", parent=self)
                    except Exception:
                        pass
                return
            try:
                var = getattr(self, "_photo_locked_var", None)
                if var is not None:
                    var.set(not locked)
            except Exception:
                pass
            try:
                self._refresh_photo_list()
            except Exception:
                pass
            try:
                self.set_status(f"photo {'locked' if not locked else 'unlocked'}: {pid}")
            except Exception:
                pass
            try:
                self._refresh_mode_ui()
            except Exception:
                pass
        except Exception:
            pass

    def _on_photo_wheel(self, event: object, direction: int = 0) -> None:
        try:
            st = int(getattr(event, "state", 0) or 0)
        except Exception:
            st = 0
        if not (st & 0x0004 or st & 0x0001):
            return
        oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
        pid = self._photo_selection()
        if oc is None or pid is None or not hasattr(oc, "set_photo_scale"):
            return
        try:
            locked = False
            try:
                if hasattr(oc, "is_photo_locked"):
                    locked = bool(oc.is_photo_locked(pid))  # type: ignore[attr-defined]
                elif hasattr(oc, "get_photo_locked"):
                    locked = bool(oc.get_photo_locked(pid))  # type: ignore[attr-defined]
                else:
                    rec0 = oc.get_photo(pid) if hasattr(oc, "get_photo") else None
                    locked = bool(rec0.get("locked")) if rec0 else False
            except Exception:
                locked = False
            if locked:
                try:
                    self.set_status("photo locked — wheel ignored")
                except Exception:
                    pass
                return
        except Exception:
            pass
        d = int(direction)
        if d == 0:
            try:
                d = 1 if int(getattr(event, "delta", 0) or 0) > 0 else -1
            except Exception:
                d = 0
        if d == 0:
            return
        cur = 100.0
        try:
            rec = oc.get_photo(pid) if hasattr(oc, "get_photo") else None
            if rec:
                cur = float(rec.get("scale", 1.0)) * 100.0
        except Exception:
            cur = 100.0
        pct = min(400.0, max(1.0, cur + 10.0 * d))
        try:
            oc.set_photo_scale(pid, min(8.0, max(0.01, pct / 100.0)))
        except Exception:
            return
        self._photo_syncing = True
        try:
            sv = getattr(self, "_photo_size", None)
            if sv is not None:
                sv.set(int(round(pct)))
            self._sync_photo_size_label(pct)
        finally:
            self._photo_syncing = False
        self._refresh_photo_list()

    def _sync_photo_size_label(self, pct: float) -> None:
        try:
            lbl = getattr(self, "_photo_size_label", None)
            if lbl is not None:
                lbl.configure(text=f"{int(round(float(pct)))}%")
        except Exception:
            pass

    def _setup_create_import_tab(self) -> None:
        tab = getattr(self, "tab_import", None)
        if tab is None:
            return
        try:
            pan = ttk.Frame(tab)
            pan.pack(fill="both", expand=True, padx=4, pady=4)
            self._import_pane = pan
            pw2 = ttk.PanedWindow(pan, orient="horizontal")
            pw2.pack(fill="both", expand=True)
            self._import_paned = pw2
            self._import_left_frame = ttk.Frame(pw2)
            self._import_right_frame = ttk.Frame(pw2)
            pw2.add(self._import_left_frame, weight=1)
            pw2.add(self._import_right_frame, weight=1)
        except Exception:
            pan = tab
        self._creator_import: object | None = None
        self._import_view: object | None = None
        try:
            from openlapexe.gui.course_creator import CourseCreator as _CC2  # type: ignore

            cc2 = _CC2(pan)
            try:
                cc2.pack(in_=getattr(self, "_import_right_frame", pan), side="right", fill="both", expand=True, padx=4, pady=4)
            except Exception:
                try:
                    cc2.pack(fill="both", expand=True)
                except Exception:
                    pass
            self._creator_import = cc2
            self.course_creator_import = cc2  # type: ignore[attr-defined]
            self.creator_import = cc2  # type: ignore[attr-defined]
            if getattr(self, "_creator_osm", None) is None:
                self._creator_osm = cc2
                self.course_creator = cc2  # type: ignore[attr-defined]
                self.creator = cc2  # type: ignore[attr-defined]
        except Exception as e:
            log.debug("CourseCreator import embed failed: %s", e)
            try:
                ttk.Label(pan, text="CourseCreator 読み込み失敗", foreground="#888").pack(fill="x", padx=6, pady=4)
            except Exception:
                pass
        try:
            from openlapexe.gui.import_view import ImportView as _IV  # type: ignore

            iv = _IV(pan)
            try:
                iv.pack(in_=getattr(self, "_import_left_frame", pan), side="left", fill="both", expand=True, padx=4, pady=4)
            except Exception:
                try:
                    iv.pack(fill="both", expand=True)
                except Exception:
                    pass
            self._import_view = iv
            self.import_view = iv  # type: ignore[attr-defined]
            self.create_import_view = iv  # type: ignore[attr-defined]
        except Exception as e:
            log.debug("ImportView embed failed: %s", e)
            try:
                ttk.Label(pan, text="取込 読み込み失敗", foreground="#888").pack(fill="x", padx=6, pady=4)
            except Exception:
                pass
        try:
            ctrl = ttk.Frame(pan if hasattr(self, "_import_view") else tab)
            ctrl.pack(side="bottom", fill="x", padx=4, pady=(4, 0))
            self._import_ctrl = ctrl
            self.btn_apply_import = ttk.Button(ctrl, text="確定", command=self._apply_import_to_creator)
            self.apply_button = self.btn_apply_import
            self.button_apply = self.btn_apply_import
            self.btn_confirm = self.btn_apply_import
            self._btn_apply = self.btn_apply_import
            self.btn_apply_import.pack(side="left", padx=4)
            self.btn_preview_import = ttk.Button(ctrl, text="プレビュー", command=self._preview_import)
            try:
                self.btn_preview_import.pack(side="left", padx=4)
            except Exception:
                pass
        except Exception:
            pass
        if self._creator_import is None and self._import_view is None:
            try:
                ttk.Label(tab, text="取込 準備中", foreground="#888").pack(expand=True)
            except Exception:
                pass

    def _loop_closed(self) -> bool:
        try:
            v = getattr(self, "_loop_var", None)
            if v is None:
                return False
            return bool(v.get())
        except Exception:
            return False

    def _on_loop_changed(self) -> None:
        try:
            closed = self._loop_closed()
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            if oc is not None:
                try:
                    oc.closed_loop = bool(closed)
                except Exception:
                    pass
                try:
                    if hasattr(oc, "_draw_points_only"):
                        oc._draw_points_only()
                except Exception:
                    pass
            for attr in ("_creator_osm", "_creator_import", "course_creator", "creator"):
                try:
                    obj = getattr(self, attr, None)
                    if obj is not None:
                        obj.closed_loop = bool(closed)
                except Exception:
                    continue
            try:
                self.set_status(f"周回: {'閉じる' if closed else '開く'}")
            except Exception:
                pass
        except Exception:
            pass

    def _on_spline_interpolate(self) -> None:
        try:
            from openlapexe.curvature_opt import spline_waypoints
        except Exception as e:
            try:
                messagebox.showerror("スプライン", f"読込失敗: {e}", parent=self)
            except Exception:
                pass
            return
        try:
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            if oc is None:
                return
            pts = list(getattr(oc, "points_xy", []) or [])
            if len(pts) < 3:
                try:
                    messagebox.showwarning("スプライン", "3点以上必要です", parent=self)
                except Exception:
                    pass
                return
            closed = self._loop_closed()
            try:
                dense = spline_waypoints(pts, closed=closed, step_m=2.0)
                import numpy as _np
                arr = _np.asarray(dense, dtype=float)
            except Exception as e:
                try:
                    messagebox.showerror("スプライン", f"補間失敗: {e}", parent=self)
                except Exception:
                    pass
                return
            if arr.ndim != 2 or arr.shape[0] < 2:
                return
            xs = [float(v) for v in arr[:, 0]]
            ys = [float(v) for v in arr[:, 1]]
            try:
                zones = list(getattr(oc, "points_zone", []) or [])
                zone = int(zones[0]) if zones else None
            except Exception:
                zone = None
            if zone is None:
                try:
                    messagebox.showwarning("スプライン", "zone情報がありません", parent=self)
                except Exception:
                    pass
                return
            try:
                from openlapexe.geo_proj import plane_to_wgs84
                ll = plane_to_wgs84(xs, ys, int(zone))
                latlon = [(float(a), float(b)) for a, b in zip(list(ll[0]), list(ll[1]))]
            except Exception as e:
                try:
                    messagebox.showerror("スプライン", f"座標変換失敗: {e}", parent=self)
                except Exception:
                    pass
                return
            try:
                oc.points_xy = list(zip(xs, ys))
                oc.points_latlon = latlon
                oc.points_zone = [int(zone)] * len(latlon)
            except Exception:
                return
            try:
                self._sync_osm_to_creator()
            except Exception:
                pass
            try:
                self._refresh_waypoint_tree()
            except Exception:
                pass
            try:
                self._update_save_button_state()
            except Exception:
                pass
            try:
                self.set_status(f"スプライン補間: {len(pts)}→{len(latlon)}点")
            except Exception:
                pass
        except Exception:
            pass

    def _on_create_mode_changed(self) -> None:
        try:
            mode = self._create_mode_var.get() if hasattr(self, "_create_mode_var") else "direct"
            if mode not in ("direct", "edge"):
                mode = "direct"
            for attr in ("_creator_osm", "_creator_import", "_course_creator", "course_creator", "creator"):
                try:
                    obj = getattr(self, attr, None)
                    if obj is not None and hasattr(obj, "set_mode"):
                        obj.set_mode(mode)  # type: ignore[attr-defined]
                    elif obj is not None and hasattr(obj, "mode_var"):
                        try:
                            obj.mode_var.set(mode)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                except Exception:
                    continue
            try:
                self.set_status(f"作画モード: {mode}")
            except Exception:
                pass
        except Exception:
            pass

    def _refresh_mode_ui(self) -> None:
        try:
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            imode = None
            try:
                if oc is not None and hasattr(oc, "get_interact_mode"):
                    im = oc.get_interact_mode()  # type: ignore[attr-defined]
                    if isinstance(im, str) and im in ("trace", "place", "edit"):
                        imode = im
                if imode is None:
                    var = getattr(self, "interact_mode_var", None) or getattr(self, "_interact_mode_var", None)
                    if var is not None and hasattr(var, "get"):
                        gv = var.get()
                        if isinstance(gv, str) and gv in ("trace", "place", "edit"):
                            imode = gv
                if imode is None:
                    v = getattr(self, "_interact_mode", None)
                    if isinstance(v, str) and v in ("trace", "place", "edit"):
                        imode = v
            except Exception:
                imode = None
            if imode is None:
                imode = "trace"
            try:
                var2 = getattr(self, "interact_mode_var", None) or getattr(self, "_interact_mode_var", None)
                if var2 is not None and hasattr(var2, "get") and var2.get() != imode:
                    try:
                        var2.set(imode)
                    except Exception:
                        pass
            except Exception:
                pass
            mode = "normal"
            try:
                if oc is not None and hasattr(oc, "get_mode"):
                    m = oc.get_mode()  # type: ignore[attr-defined]
                    if isinstance(m, str) and m:
                        mode = str(m)
            except Exception:
                mode = "normal"
            try:
                if mode == "normal" and oc is not None and getattr(oc, "_placing_photo_id", None) is not None:
                    mode = "place"
            except Exception:
                pass
            try:
                if mode == "normal":
                    sel = self._photo_selection()
                    if sel is not None:
                        mode = "select"
            except Exception:
                pass
            display = imode if imode in ("trace", "place", "edit") else mode
            try:
                if display == "trace":
                    self.set_status("trace: click adds waypoint (photos ignored)")
                elif display == "edit":
                    self.set_status("edit: click selects photo, drag/handles to adjust")
                elif display == "place":
                    self.set_status("配置モード…")
                elif mode == "select":
                    self.set_status("写真選択中…")
                else:
                    self.set_status("通常…")
            except Exception:
                pass
            try:
                btn = getattr(self, "_photo_place_btn", None) or getattr(self, "photo_place_button", None)
                if btn is not None:
                    armed = (imode == "place" or mode == "place")
                    if armed:
                        try:
                            btn.configure(text="配置中…")
                        except Exception:
                            pass
                        try:
                            btn.state(["pressed"])  # type: ignore[attr-defined]
                        except Exception:
                            try:
                                btn.configure(state="pressed")
                            except Exception:
                                pass
                    else:
                        try:
                            btn.configure(text="配置")
                        except Exception:
                            pass
                        try:
                            btn.state(["!pressed"])  # type: ignore[attr-defined]
                        except Exception:
                            try:
                                btn.configure(state="normal")
                            except Exception:
                                pass
            except Exception:
                pass
        except Exception:
            pass

    def _sync_osm_to_creator(self, event: object | None = None) -> None:
        try:
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            cc = getattr(self, "_creator_osm", None) or getattr(self, "course_creator", None) or getattr(self, "creator", None)
            if oc is None or cc is None:
                return
            pts = getattr(oc, "points_xy", None)
            if pts is None:
                return
            lst = list(pts)  # type: ignore[arg-type]
            if not lst:
                return
            try:
                placing = getattr(oc, "_placing_photo_id", None)
                if placing is not None and event is not None:
                    is_bypass = False
                    try:
                        st = int(getattr(event, "state", 0))
                        if st & 0x0001:
                            is_bypass = True
                        num = getattr(event, "num", None)
                        if num in (2, 3):
                            is_bypass = True
                        ks = getattr(event, "keysym", "")
                        if isinstance(ks, str) and ks.lower() == "shift_l":
                            is_bypass = True
                    except Exception:
                        pass
                    try:
                        ev_type = str(getattr(event, "type", ""))
                        if "ButtonPress-2" in ev_type or "ButtonPress-3" in ev_type:
                            is_bypass = True
                    except Exception:
                        pass
                    _ = "Shift Button-2 Button-3"
                    is_on_photo = False
                    try:
                        if hasattr(oc, "_last_click_on_photo") and bool(getattr(oc, "_last_click_on_photo")):
                            is_on_photo = True
                    except Exception:
                        pass
                    try:
                        if hasattr(oc, "hit_test_photo"):
                            try:
                                ht = oc.hit_test_photo(int(getattr(event, "x", -9999)), int(getattr(event, "y", -9999)))
                                if ht is not None:
                                    is_on_photo = True
                            except Exception:
                                pass
                    except Exception:
                        pass
                    if not (is_bypass or is_on_photo):
                        try:
                            self._refresh_mode_ui()
                        except Exception:
                            pass
                        return
            except Exception:
                pass
            try:
                cur = list(getattr(cc, "points_xy", []) or [])
            except Exception:
                cur = []
            if lst == cur:
                try:
                    self._refresh_mode_ui()
                except Exception:
                    pass
                return
            try:
                if len(lst) > len(cur) and lst[: len(cur)] == cur:
                    try:
                        if hasattr(cc, "_push_undo"):
                            cc._push_undo()  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    new_pts = lst[len(cur) :]
                    try:
                        cc.points_xy.extend([(float(x), float(y)) for x, y in new_pts])  # type: ignore[attr-defined]
                        try:
                            cc.points = cc.points_xy  # type: ignore[attr-defined]
                            cc.buffer = cc.points_xy  # type: ignore[attr-defined]
                        except Exception:
                            pass
                        try:
                            if hasattr(cc, "_redraw"):
                                cc._redraw()  # type: ignore[attr-defined]
                            if hasattr(cc, "_update_preview"):
                                cc._update_preview()  # type: ignore[attr-defined]
                        except Exception:
                            pass
                    except Exception:
                        try:
                            cc.set_points(lst, push_undo=False)  # type: ignore[attr-defined]
                        except TypeError:
                            cc.points_xy.clear()  # type: ignore[attr-defined]
                            cc.points_xy.extend(lst)  # type: ignore[attr-defined]
                        except Exception:
                            cc.points_xy = lst  # type: ignore[attr-defined]
                    try:
                        oc_ll = list(getattr(oc, "points_latlon", []) or [])
                        for lat, lon in oc_ll[len(cur):]:
                            try:
                                self._append_waypoint_row(float(lat), float(lon))
                            except Exception:
                                pass
                    except Exception:
                        pass
                    try:
                        self._update_save_button_state()
                    except Exception:
                        pass
                    try:
                        self.set_status(f"OSM {len(lst)}点 → 作成へ反映")
                    except Exception:
                        pass
                    try:
                        self._refresh_mode_ui()
                    except Exception:
                        pass
                    return
            except Exception:
                pass
            try:
                has_push_flag = False
                try:
                    import inspect as _ins

                    sig = _ins.signature(getattr(cc, "set_points", lambda: None))  # type: ignore
                    has_push_flag = "push_undo" in sig.parameters
                except Exception:
                    has_push_flag = False
                if has_push_flag:
                    try:
                        if hasattr(cc, "_push_undo"):
                            cc._push_undo()  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    try:
                        cc.set_points(lst, push_undo=False)  # type: ignore[attr-defined]
                    except Exception:
                        try:
                            cc.points_xy = lst  # type: ignore[attr-defined]
                        except Exception:
                            pass
                else:
                    try:
                        cc.set_points(lst)  # type: ignore[attr-defined]
                    except Exception:
                        try:
                            cc.points_xy = lst  # type: ignore[attr-defined]
                        except Exception:
                            pass
            except Exception:
                try:
                    cc.set_points(lst)  # type: ignore[attr-defined]
                except Exception:
                    try:
                        cc.points_xy = lst  # type: ignore[attr-defined]
                    except Exception:
                        pass
            try:
                self.set_status(f"OSM {len(lst)}点 → 作成へ反映")
            except Exception:
                pass
            try:
                self._refresh_waypoint_tree()
            except Exception:
                pass
            try:
                self._update_save_button_state()
            except Exception:
                pass
            try:
                self._refresh_mode_ui()
            except Exception:
                pass
        except Exception as e:
            log.debug("sync osm to creator failed: %s", e)

    def _apply_import_to_creator(self) -> None:
        try:
            iv = getattr(self, "_import_view", None) or getattr(self, "import_view", None)
            cc = getattr(self, "_creator_import", None) or getattr(self, "_creator_osm", None) or getattr(self, "course_creator", None)
            if iv is None or cc is None:
                try:
                    messagebox.showwarning("警告", "取込または作成ビューが未初期化です", parent=self)
                except Exception:
                    try:
                        messagebox.showwarning("警告", "取込または作成ビューが未初期化です", parent=self)
                    except Exception:
                        pass
                return
            staging = getattr(iv, "points", None)
            if staging is None:
                staging = getattr(iv, "staging", None)
            if staging is None:
                staging = getattr(iv, "_staging", None)
            if staging is None:
                staging = []
            lst = list(staging) if staging is not None else []  # type: ignore[arg-type]
            if not lst:
                try:
                    sel = iv.get_selected_candidates() if hasattr(iv, "get_selected_candidates") else []  # type: ignore[attr-defined]
                    if sel:
                        lst = list(sel)
                except Exception:
                    pass
            if not lst:
                try:
                    messagebox.showwarning("警告", "候補を選択してください", parent=self)
                except Exception:
                    try:
                        messagebox.showwarning("警告", "候補を選択してください", parent=self)
                    except Exception:
                        pass
                return
            pts: list[tuple[float, float]] = []
            try:
                import numpy as np  # type: ignore

                for cand in lst:
                    arr = getattr(cand, "points_xy", None)
                    if arr is None and isinstance(cand, dict):
                        arr = cand.get("points_xy")  # type: ignore[attr-defined]
                    if arr is None and isinstance(cand, (list, tuple)) and len(cand) == 2:
                        try:
                            pts.append((float(cand[0]), float(cand[1])))  # type: ignore
                            continue
                        except Exception:
                            pass
                    if arr is not None:
                        try:
                            a = np.asarray(arr, dtype=float)
                            if a.ndim == 1 and a.size % 2 == 0 and a.size >= 2:
                                a = a.reshape(-1, 2)
                            if a.ndim == 2 and a.shape[1] >= 2:
                                for i in range(int(a.shape[0])):
                                    pts.append((float(a[i, 0]), float(a[i, 1])))
                                continue
                        except Exception:
                            pass
                    ll = getattr(cand, "points_lonlat", None)
                    if ll is not None:
                        try:
                            from openlapexe.geo_proj import wgs84_to_plane as _w2p  # type: ignore

                            seq = list(ll)  # type: ignore[arg-type]
                            lons = [float(p[0]) for p in seq]  # type: ignore
                            lats = [float(p[1]) for p in seq]  # type: ignore
                            x_arr, y_arr, _ = _w2p(lats, lons)  # type: ignore[arg-type]
                            for xv, yv in zip(np.asarray(x_arr, dtype=float), np.asarray(y_arr, dtype=float)):
                                pts.append((float(xv), float(yv)))
                        except Exception:
                            try:
                                a2 = np.asarray(ll, dtype=float)
                                if a2.ndim == 2 and a2.shape[1] >= 2:
                                    for i in range(int(a2.shape[0])):
                                        pts.append((float(a2[i, 0]), float(a2[i, 1])))
                            except Exception:
                                pass
            except Exception:
                try:
                    for cand in lst:
                        if isinstance(cand, (list, tuple)) and len(cand) == 2:
                            pts.append((float(cand[0]), float(cand[1])))  # type: ignore
                except Exception:
                    pts = []
            if not pts:
                try:
                    messagebox.showwarning("警告", "変換後の点が空です", parent=self)
                except Exception:
                    try:
                        messagebox.showwarning("警告", "変換後の点が空です", parent=self)
                    except Exception:
                        pass
                return
            try:
                cc.set_points(pts)  # type: ignore[attr-defined]
            except Exception:
                try:
                    cc.points_xy = pts  # type: ignore[attr-defined]
                except Exception:
                    pass
            try:
                cc2 = getattr(self, "_creator_osm", None)
                if cc2 is not None and cc2 is not cc:
                    try:
                        cc2.set_points(pts)  # type: ignore[attr-defined]
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                self.set_status(f"取込 {len(pts)}点 → 作成へ反映")
            except Exception:
                pass
        except Exception as e:
            log.debug("apply import to creator failed: %s", e)
            try:
                messagebox.showerror("エラー", str(e), parent=self)
            except Exception:
                try:
                    messagebox.showerror("エラー", str(e), parent=self)
                except Exception:
                    pass

    def _preview_import(self) -> None:
        try:
            iv = getattr(self, "_import_view", None) or getattr(self, "import_view", None)
            if iv is not None and hasattr(iv, "preview_selected"):
                iv.preview_selected()  # type: ignore[attr-defined]
            elif iv is not None and hasattr(iv, "_on_preview"):
                iv._on_preview()  # type: ignore[attr-defined]
        except Exception:
            pass

    def _on_save_track(self) -> None:
        try:
            from tkinter import simpledialog  # type: ignore
        except Exception:
            simpledialog = None  # type: ignore
        name: str | None = None
        try:
            if simpledialog is not None:
                try:
                    name = simpledialog.askstring("保存", "トラック名を入力してください", parent=self)
                except TypeError:
                    name = simpledialog.askstring("保存", "トラック名を入力してください")
                except Exception:
                    name = None
            else:
                try:
                    name = tk.simpledialog.askstring("保存", "トラック名を入力してください", parent=self)  # type: ignore[attr-defined]
                except Exception:
                    name = None
        except Exception:
            name = None
        if name is None:
            return
        raw = str(name).strip()
        if not raw:
            try:
                messagebox.showwarning("警告", "名前を入力してください", parent=self)
            except Exception:
                try:
                    messagebox.showwarning("警告", "名前を入力してください", parent=self)
                except Exception:
                    pass
            return
        try:
            cc = getattr(self, "_creator_osm", None) or getattr(self, "_creator_import", None) or getattr(self, "course_creator", None) or getattr(self, "creator", None)
            if cc is None:
                raise RuntimeError("CourseCreatorが未初期化です")
            center = None
            pts_xy: list[tuple[float, float]] | None = None
            try:
                if hasattr(cc, "get_centerline"):
                    center = cc.get_centerline()  # type: ignore[attr-defined]
                elif hasattr(cc, "get_centreline"):
                    center = cc.get_centreline()  # type: ignore[attr-defined]
            except Exception:
                center = None
            try:
                import numpy as np  # type: ignore

                if center is not None:
                    a = np.asarray(center, dtype=float)
                    if a.size > 0:
                        if a.ndim == 1 and a.size % 2 == 0 and a.size >= 2:
                            a = a.reshape(-1, 2)
                        if a.ndim == 2 and a.shape[1] >= 2:
                            pts_xy = [(float(a[i, 0]), float(a[i, 1])) for i in range(int(a.shape[0]))]
                if pts_xy is None:
                    raw_pts = getattr(cc, "points_xy", None) or getattr(cc, "points", None) or getattr(cc, "buffer", None)
                    if raw_pts is not None:
                        a2 = np.asarray(raw_pts, dtype=float)
                        if a2.size > 0:
                            if a2.ndim == 1 and a2.size % 2 == 0 and a2.size >= 2:
                                a2 = a2.reshape(-1, 2)
                            if a2.ndim == 2 and a2.shape[1] >= 2:
                                pts_xy = [(float(a2[i, 0]), float(a2[i, 1])) for i in range(int(a2.shape[0]))]
                            else:
                                pts_xy = list(raw_pts)  # type: ignore[arg-type]
            except Exception:
                try:
                    pts_xy = list(getattr(cc, "points_xy", []) or [])  # type: ignore[arg-type]
                except Exception:
                    pts_xy = None
            if not pts_xy or len(pts_xy) < 2:
                try:
                    messagebox.showwarning("警告", "点が不足しています（2点以上必要）", parent=self)
                except Exception:
                    try:
                        messagebox.showwarning("警告", "点が不足しています（2点以上必要）", parent=self)
                    except Exception:
                        pass
                return
            try:
                from openlapexe.track import Track as _Track  # type: ignore
            except Exception as e:
                raise RuntimeError(f"Track import失敗: {e}") from e
            cand = {"points_xy": pts_xy, "name": raw}
            try:
                loop_closed = self._loop_closed()
            except Exception:
                loop_closed = False
            track = _Track.from_candidates([cand], closed_loop=bool(loop_closed))  # type: ignore[attr-defined]
            try:
                meta = getattr(track, "meta", None)
                if isinstance(meta, dict) and meta.get("zone") is None:
                    oc0 = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
                    zones = list(getattr(oc0, "points_zone", []) or []) if oc0 is not None else []
                    if zones:
                        import collections as _collections
                        zone = _collections.Counter(int(z) for z in zones).most_common(1)[0][0]
                        meta["zone"] = int(zone)
            except Exception:
                pass
            try:
                oc2 = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
                specs = oc2.get_photo_specs() if oc2 is not None and hasattr(oc2, "get_photo_specs") else []
                if specs:
                    try:
                        track.meta.update({"overlays": specs})
                    except Exception:
                        try:
                            track.meta = {"overlays": specs}  # type: ignore[attr-defined]
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                track.name = raw
            except Exception:
                pass
            path = track.save_json(raw)  # type: ignore[attr-defined]
            try:
                from openlapexe.track import Track as _T2  # type: ignore

                _reloaded = _T2.from_json(raw)  # type: ignore[attr-defined]
                if _reloaded.points.shape[0] < 2:
                    raise ValueError("保存後に再読込したトラックが空です")
            except Exception as e:
                log.debug("reload verify failed: %s", e)
            self._refresh_track_combos_all(raw)
            self._refresh_load_combo()
            self._refresh_data_tab(select_track=raw)
            try:
                self.set_status(f"保存: {path}")
            except Exception:
                pass
            try:
                if hasattr(self, "_save_status_var"):
                    self._save_status_var.set(f"保存: {path.name}")
            except Exception:
                pass
            try:
                messagebox.showinfo("保存", f"{path} に保存しました", parent=self)
            except Exception:
                try:
                    messagebox.showinfo("保存", f"{path} に保存しました", parent=self)
                except Exception:
                    pass
        except Exception as e:
            log.debug("save track failed: %s", e)
            try:
                messagebox.showerror("エラー", f"{type(e).__name__}: {e}", parent=self)
            except Exception:
                try:
                    messagebox.showerror("エラー", f"{type(e).__name__}: {e}", parent=self)
                except Exception:
                    pass

    def _refresh_track_combos_all(self, select: str | None = None) -> None:
        sel = str(select).removesuffix(".json") if select is not None else None
        for attr in ("track_view", "_track_view"):
            try:
                tv = getattr(self, attr, None)
                if tv is not None:
                    if hasattr(tv, "refresh_tracks"):
                        try:
                            tv.refresh_tracks(select=sel)  # type: ignore[attr-defined]
                        except TypeError:
                            tv.refresh_tracks()  # type: ignore[attr-defined]
                    elif hasattr(tv, "_discover_tracks"):
                        try:
                            tv._discover_tracks()  # type: ignore[attr-defined]
                        except Exception:
                            pass
                        if sel is not None and hasattr(tv, "_track_stems"):
                            try:
                                stems = list(getattr(tv, "_track_stems", []) or [])
                                if sel not in stems:
                                    stems.append(sel)
                                    stems = sorted(stems)
                                    tv._track_stems = stems  # type: ignore[attr-defined]
                                    if hasattr(tv, "combo"):
                                        try:
                                            tv.combo["values"] = stems  # type: ignore[attr-defined]
                                        except Exception:
                                            pass
                            except Exception:
                                pass
                    if sel is not None and hasattr(tv, "combo"):
                        try:
                            vals = []
                            if hasattr(tv, "get_track_names"):
                                try:
                                    vals = list(tv.get_track_names())  # type: ignore[attr-defined]
                                except Exception:
                                    vals = []
                            if not vals and hasattr(tv, "_track_stems"):
                                vals = list(getattr(tv, "_track_stems", []))
                            if vals and sel in vals:
                                try:
                                    tv.combo.set(sel)  # type: ignore[attr-defined]
                                    tv.combo.current(vals.index(sel))  # type: ignore[attr-defined]
                                except Exception:
                                    pass
                                try:
                                    if hasattr(tv, "_load_track"):
                                        tv._load_track(sel)  # type: ignore[attr-defined]
                                    elif hasattr(tv, "select_track"):
                                        tv.select_track(sel)  # type: ignore[attr-defined]
                                except Exception:
                                    pass
                        except Exception:
                            pass
            except Exception:
                continue
        for attr in ("simulate_view", "_simulate_view", "simulateFrame", "sim_view"):
            try:
                sv = getattr(self, attr, None)
                if sv is not None and hasattr(sv, "refresh_tracks"):
                    try:
                        sv.refresh_tracks(select=sel)  # type: ignore[attr-defined]
                    except TypeError:
                        sv.refresh_tracks()  # type: ignore[attr-defined]
            except Exception:
                continue

    def _refresh_vehicle_combos_all(self, select: str | None = None) -> None:
        sel = str(select).removesuffix(".json") if select is not None else None
        for attr in ("drag_view", "_drag_view"):
            try:
                dv = getattr(self, attr, None)
                if dv is not None and hasattr(dv, "refresh_vehicles"):
                    try:
                        dv.refresh_vehicles(select=sel)  # type: ignore[attr-defined]
                    except TypeError:
                        dv.refresh_vehicles()  # type: ignore[attr-defined]
            except Exception:
                continue
        for attr in ("simulate_view", "_simulate_view"):
            try:
                sv = getattr(self, attr, None)
                if sv is not None and hasattr(sv, "refresh_vehicles"):
                    try:
                        sv.refresh_vehicles(select=sel)  # type: ignore[attr-defined]
                    except TypeError:
                        sv.refresh_vehicles()  # type: ignore[attr-defined]
            except Exception:
                continue

    def _refresh_track_combo(self, name: str) -> None:
        try:
            self._refresh_track_combos_all(name)
        except Exception as e:
            log.debug("refresh track combo outer failed: %s", e)

    def _discover_saved_tracks(self) -> list[str]:
        try:
            from openlapexe.io import resource_path
            base = resource_path("data/tracks")
            if not base.exists():
                base = pathlib.Path(__file__).resolve().parents[3] / "data" / "tracks"
            if not base.exists():
                return []
            return sorted(p.stem for p in base.glob("*.json") if p.is_file())
        except Exception:
            return []

    def _refresh_load_combo(self) -> None:
        try:
            combo = getattr(self, "_load_combo", None)
            if combo is None:
                return
            stems = self._discover_saved_tracks()
            try:
                cur = combo.get()
            except Exception:
                cur = ""
            try:
                combo["values"] = stems
            except Exception:
                return
            try:
                if cur in stems:
                    combo.set(cur)
                elif stems:
                    combo.set(stems[0])
            except Exception:
                pass
        except Exception:
            pass

    def _on_load_track(self, name: str | None = None) -> None:
        try:
            if name is None:
                combo = getattr(self, "_load_combo", None)
                try:
                    name = combo.get().strip() if combo is not None else ""
                except Exception:
                    name = ""
            stem = str(name or "").strip().removesuffix(".json")
            if not stem:
                try:
                    messagebox.showwarning("読込", "コースを選択してください", parent=self)
                except Exception:
                    pass
                return
            try:
                from openlapexe.track import Track as _Track
            except Exception as e:
                raise RuntimeError(f"Track import失敗: {e}") from e
            try:
                track = _Track.from_json(stem)
            except Exception as e:
                try:
                    messagebox.showerror("読込", f"読込失敗: {e}", parent=self)
                except Exception:
                    pass
                return
            try:
                import numpy as _np
                pts = _np.asarray(track.points, dtype=float)
            except Exception as e:
                try:
                    messagebox.showerror("読込", f"点列取得失敗: {e}", parent=self)
                except Exception:
                    pass
                return
            if pts.ndim != 2 or pts.shape[1] < 3 or pts.shape[0] < 1:
                try:
                    messagebox.showerror("読込", "点列が空です", parent=self)
                except Exception:
                    pass
                return
            xs = [float(v) for v in pts[:, 1]]
            ys = [float(v) for v in pts[:, 2]]
            zone = None
            try:
                meta = getattr(track, "meta", None) or {}
                zone = meta.get("zone")
            except Exception:
                zone = None
            if zone is None:
                try:
                    messagebox.showwarning("読込", "緯度経度情報がありません(zoneなし)のため地図に配置できません", parent=self)
                except Exception:
                    pass
                return
            try:
                from openlapexe.geo_proj import plane_to_wgs84
                ll = plane_to_wgs84(xs, ys, int(zone))
                latlon = [(float(a), float(b)) for a, b in zip(list(ll[0]), list(ll[1]))]
            except Exception:
                try:
                    latlon = []
                    for x, y in zip(xs, ys):
                        la, lo = plane_to_wgs84(float(x), float(y), int(zone))
                        latlon.append((float(la), float(lo)))
                except Exception as e:
                    try:
                        messagebox.showerror("読込", f"座標変換失敗: {e}", parent=self)
                    except Exception:
                        pass
                    return
            oc = getattr(self, "_osm_canvas", None) or getattr(self, "osm_canvas", None)
            cc = getattr(self, "_creator_osm", None) or getattr(self, "course_creator", None) or getattr(self, "creator", None)
            if oc is None:
                try:
                    messagebox.showerror("読込", "地図が未初期化です", parent=self)
                except Exception:
                    pass
                return
            try:
                oc.points_latlon = list(latlon)
                oc.points_xy = list(zip(xs, ys))
                oc.points_zone = [int(zone)] * len(latlon)
            except Exception as e:
                try:
                    messagebox.showerror("読込", f"反映失敗: {e}", parent=self)
                except Exception:
                    pass
                return
            if cc is not None:
                try:
                    if hasattr(cc, "set_points"):
                        try:
                            import inspect as _ins2
                            if "push_undo" in _ins2.signature(getattr(cc, "set_points")).parameters:
                                cc.set_points(list(zip(xs, ys)), push_undo=False)
                            else:
                                cc.set_points(list(zip(xs, ys)))
                        except Exception:
                            cc.points_xy = list(zip(xs, ys))
                    else:
                        cc.points_xy = list(zip(xs, ys))
                except Exception:
                    pass
                try:
                    st = getattr(cc, "_undo_stack", None)
                    if isinstance(st, list):
                        st.clear()
                except Exception:
                    pass
            try:
                if hasattr(oc, "_draw_points_only"):
                    oc._draw_points_only()
                elif hasattr(oc, "_request_redraw"):
                    oc._request_redraw()
            except Exception:
                pass
            try:
                self._refresh_waypoint_tree()
            except Exception:
                pass
            restored = 0
            try:
                meta = getattr(track, "meta", None) or {}
                specs = meta.get("overlays") or []
                if specs and hasattr(oc, "load_photo_specs"):
                    restored = int(oc.load_photo_specs(specs) or 0)
            except Exception:
                restored = 0
            try:
                self._update_save_button_state()
            except Exception:
                pass
            try:
                self.set_status(f"読込: {stem} ({len(latlon)}点, 写真{restored}件)")
            except Exception:
                pass
        except Exception:
            pass

    def _collect_data_preview(self, kind: str) -> str:
        try:
            base = resource_path(f"data/{kind}")
            if not base.exists():
                base = pathlib.Path(__file__).resolve().parents[3] / "data" / kind
            if not base.exists():
                return f"data/{kind} フォルダが見つかりません"
            files: list[str] = []
            try:
                for pp in sorted(base.glob("*.json")):
                    # encoding check
                    try:
                        pp.read_text(encoding="utf-8")
                    except Exception:
                        pass
                    files.append(pp.name)
            except Exception:
                pass
            if not files:
                return f"data/{kind} にJSONがありません"
            preview = ", ".join(files[:5])
            if len(files) > 5:
                preview += f" ほか{len(files)-5}件"
            return f"{len(files)}件: {preview}"
        except Exception as e:
            log.debug("collect preview failed: %s", e)
            return f"{kind} データ読み込みスキップ"

    def set_status(self, text: str) -> None:
        try:
            self._status_var.set(text)
        except Exception:
            pass


__all__ = ["App2"]
