#!/usr/bin/env python3
"""
TURMO Windows Application — System tray + GUI for TURMO USB display monitor.
Features: system tray, live preview, theme selection, orientation toggle, 
Windows startup, visual theme editor, graph customization, installer-ready.
"""

import sys
import os
import json
import re
import unicodedata
import shutil
import threading
import subprocess
import time
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from copy import deepcopy
import traceback
from datetime import datetime
import sys

# Runtime logging - must be early
# Run as `python scripts\turmo_app_enhanced.py`, sys.path holds scripts\ but not the project
# root, so `scripts.runtime_logging` would not import and every runtime log line is dropped.
if not getattr(sys, "frozen", False):
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

# Loading screen (v0.2.1): shown before the heavy imports below. Only when this file is the program
# (the test suites import it and must not open a window).
SPLASH = None
STARTUP = "--startup" in sys.argv  # v0.3.7.2: started by Windows at sign-in: no splash, window hidden in the tray
if __name__ == "__main__" and not STARTUP:
    # The .NET runtime (CPU temperature) is loaded before the first Tk window exists: with the window first, the
    # frozen exe spent 5 s here (measured 2026-11-18). turmo_runtime._preinit_libre_hardware_monitor() sees it loaded.
    # clr_loader runs `dotnet --list-runtimes`; from this windowed exe that opened a terminal window (Windows
    # Terminal is the default host), so every child process of this block gets CREATE_NO_WINDOW.
    import subprocess as _subprocess
    _Popen = _subprocess.Popen

    class _QuietPopen(_Popen):
        def __init__(self, *args, **kwargs):
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | 0x08000000  # CREATE_NO_WINDOW
            super().__init__(*args, **kwargs)
    _subprocess.Popen = _QuietPopen
    try:
        import pythonnet
        pythonnet.load("coreclr")
        import clr  # noqa: F401
    except Exception:
        pass  # ok: the later call in main() logs the real reason
    finally:
        _subprocess.Popen = _Popen
    from scripts import splash as _splash_module
    SPLASH = _splash_module.start()


def _splash_step(name: str) -> None:
    """A real start-up milestone: moves the loading screen's bar (and redraws it)."""
    if SPLASH is not None:
        try:
            SPLASH.step(name)
        except Exception as e:
            log_swallowed("loading screen step", e)


from scripts.gui_common import *  # noqa: F401,F403  (the start-up environment, see gui_common.py)
_splash_step("imports")


from scripts.gallery_page import GalleryPage, _SearchQuery  # noqa: E402,F401
from scripts.diagnostics_page import DiagnosticsPage  # noqa: E402
from scripts.preview_page import PreviewPage  # noqa: E402
from scripts.graph_page import GraphPage  # noqa: E402
from scripts.about_page import AboutPage  # noqa: E402
from scripts.logs_page import LogsPage  # noqa: E402
from scripts.first_run import FirstRunPage  # noqa: E402
from scripts.theme_editor import (  # noqa: F401
    WidgetConfig, tk_colour, ThemePalette, widget_defaults, widget_from_dict, widget_to_dict, ThemeEditor, DEFAULT_THEME, WIDGET_FIELDS, SIZED_TYPES,
)


def _process_rows():
    """(pid, name, command line, parent pid) of the processes that can be a TURMO Monitor.
    The command line is read only for Python processes (cheap every 2 s)."""
    import psutil
    # psutil's per-process "ppid" takes a Windows snapshot each time: about 12 ms x 400 processes = 5 s on the first scan,
    # run on the Tk thread 0.5 s after the window opened (the app froze and "Device status" stayed empty). One snapshot
    # for all processes costs 12 ms.
    try:
        from psutil import _psutil_windows as _cext
        parent_of = _cext.ppid_map()
    except Exception as _e:
        log_swallowed("ppid snapshot", _e)
        parent_of = None
    rows = []
    for p in psutil.process_iter(["pid", "name"] if parent_of is not None else ["pid", "name", "ppid"]):
        try:
            name = p.info["name"] or ""
            low = name.lower()
            cmd = " ".join(p.cmdline() or []) if "python" in low else ""
            if "turmo-monitor" in low or ("python" in low and cmd):
                ppid = parent_of.get(p.info["pid"]) if parent_of is not None else p.info["ppid"]
                rows.append((p.info["pid"], name, cmd, ppid))
        except Exception as e:  # a process that vanished or is not ours to read
            log_swallowed("process scan", e)
            continue
    return rows


def _turmo_monitor_pids(rows):
    """PIDs of the top-level TURMO Monitor processes among (pid, name, command line, parent pid) rows.
    A one-file PyInstaller exe runs a bootloader and a child with the same name. Only the
    bootloader is listed (its PID is the one Popen returns), so one Monitor counts once."""
    monitor = set()
    for pid, name, cmd, _ppid in rows:
        low, c = (name or "").lower(), (cmd or "").lower()
        if "turmo-monitor" in low or ("python" in low and ("turmo_runtime" in c or "turmo-monitor" in c)):
            monitor.add(pid)
    return sorted(pid for pid, _name, _cmd, ppid in rows if pid in monitor and ppid not in monitor)


class TurmoApp(AboutPage, GraphPage, PreviewPage, DiagnosticsPage, GalleryPage, LogsPage, FirstRunPage):
    def __init__(self, root: tk.Tk):
        # Initialize startup logging
        self._startup_log = init_startup_log()
        log_startup(self._startup_log, "INIT", "TurmoApp.__init__ started")

        # Initialize runtime logging
        if RUNTIME_LOGGING_AVAILABLE:
            init_runtime_log()
            install_thread_excepthook()
            log_runtime("APP", "INIT", "Runtime logging initialized")

        self.root = root
        # v0.3.5: an error inside a button or timer is logged and shown in plain words, not lost on a hidden stderr
        from scripts.errors import CallbackErrors
        self.root.report_callback_exception = CallbackErrors(
            lambda e: log_exception("APP", "CALLBACK_ERROR", e),
            lambda text: self.toast(tr(text), kind="error"))
        self.root.title("TURMO Display Control")
        self.root.geometry("%dx%d" % self._window_sizes()[0])
        self._apply_window_icon()
        self._set_resize_mode(False)
        log_startup(self._startup_log, "TK_ROOT", "Tk root created and configured")

        # Single-instance mutex (create after Tk init for PyInstaller --windowed)
        self._mutex = None
        if sys.platform == "win32" and win32event:
            try:
                log_startup(self._startup_log, "MUTEX", "Creating mutex Global\\TURMO-Display-Control-GUI")
                self._mutex = win32event.CreateMutex(None, False, "Global\\TURMO-Display-Control-GUI")
                last_error = win32api.GetLastError()
                log_startup(self._startup_log, "MUTEX", f"CreateMutex result: last_error={last_error} (ERROR_ALREADY_EXISTS={winerror.ERROR_ALREADY_EXISTS})")
                if last_error == winerror.ERROR_ALREADY_EXISTS or last_error == 5:  # 5 = ERROR_ACCESS_DENIED
                    # Another instance is running, or access denied (mutex exists with different perms)
                    # Try to handle both cases by opening existing mutex
                    try:
                        if self._mutex:
                            win32api.CloseHandle(self._mutex)
                    except Exception as e:
                        log_startup(self._startup_log, "MUTEX", f"CloseHandle error: {e}", e)
                    # Try opening existing mutex and check if we can acquire (stale)
                    try:
                        MUTEX_ALL_ACCESS = 0x1F0001
                        existing = win32event.OpenMutex(MUTEX_ALL_ACCESS, False, "Global\\TURMO-Display-Control-GUI")
                        acquired = win32event.WaitForSingleObject(existing, 0) == win32event.WAIT_OBJECT_0
                        log_startup(self._startup_log, "MUTEX", f"OpenMutex acquired={acquired}")
                        if acquired:
                            # Stale mutex - we got it, close and create our own
                            win32event.ReleaseMutex(existing)
                            win32api.CloseHandle(existing)
                            self._mutex = win32event.CreateMutex(None, True, "Global\\TURMO-Display-Control-GUI")
                            log_startup(self._startup_log, "MUTEX", "Stale mutex detected - created new mutex")
                        else:
                            # Another instance is genuinely running
                            win32api.CloseHandle(existing)
                            log_startup(self._startup_log, "MUTEX", "Another instance genuinely running - exiting")
                            print("TURMO Display Control is already running.", file=sys.stderr)
                            self.root.after(0, self.root.destroy)
                            return
                    except Exception as e:
                        # If we can't determine, assume another instance
                        log_startup(self._startup_log, "MUTEX", f"Mutex check error: {e}", e)
                        print("TURMO Display Control is already running.", file=sys.stderr)
                        self.root.after(0, self.root.destroy)
                        return
            except Exception as e:
                log_startup(self._startup_log, "MUTEX", f"Mutex creation failed: {e}", e)
                pass

        log_startup(self._startup_log, "SETTINGS", "Loading settings")
        self._first_run = not Settings.path().exists()  # v0.3.0: a fresh install shows the first-run dialog once
        if Settings.quarantine_damaged():
            log_runtime("APP", "SETTINGS_DAMAGED", "settings.json was not valid and was moved to settings.json.bad")
        self.settings = Settings.load()
        set_logging_enabled(self.settings.logging_enabled)
        i18n.set_missing_logger(_log_missing_text)
        i18n.set_language(self.settings.language)  # before any widget is built: they draw through tr()
        _splash_step("settings")
        self.monitor_process: Optional[subprocess.Popen] = None
        self._ignored_pids: set = set()  # Monitor PIDs this window just stopped; forgotten once gone
        self.preview_thread: Optional[threading.Thread] = None
        self.preview_running = False
        self._pynvml_init = False
        self.tray_icon: Optional[pystray.Icon] = None
        self.quick_panel = QuickPanel(self)
        self.tray_thread: Optional[threading.Thread] = None
        self.theme_editor: Optional[ThemeEditor] = None
        # Live readings for the dashboard, created here so it works before Live Preview starts
        self._preview_lock = threading.Lock()
        self._preview_readings = {}
        self._preview_worker_thread: Optional[threading.Thread] = None  # read by the Diagnostics refresh

        # Clean up stale workers and COM4 locks from previous runs
        self._cleanup_stale_workers()
        _splash_step("cleanup")

        log_startup(self._startup_log, "BUILD_UI", "Building UI")
        set_mode(self.settings.app_mode)
        self.build_ui()
        log_startup(self._startup_log, "REFRESH_PORT", "Initial port detection")
        self.refresh_port()
        _splash_step("port")
        log_startup(self._startup_log, "START_TRAY", "Starting system tray")
        self.start_tray()
        _splash_step("tray")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.auto_detect_gpu()
        self.apply_app_theme(self.settings.app_theme, initial=True)
        _splash_step("theme")
        _log_event("GUI_START", "startup")
        self.root.after(500, self._refresh_monitor_state)
        self.root.after(1000, self._refresh_dashboard)
        self.root.bind("<Map>", self._on_window_shown, add="+")  # restored from the taskbar or the tray

        # Style for danger button
        style = ttk.Style()
        style.configure("Danger.TButton", foreground="red")
        log_startup(self._startup_log, "INIT", "TurmoApp.__init__ completed successfully")

    def _apply_dark_style(self):
        """v0.2.0 look for every ttk widget: dark surfaces, light text, cyan accent (design tokens)."""
        import tkinter.font as tkfont
        families = set(tkfont.families(self.root))
        self.ui_font = pick_family(families, TEXT_FONTS)
        self.ui_semibold = pick_family(families, SEMIBOLD_FONTS)
        st = ttk.Style(self.root)
        st.theme_use("clam")
        bg0, bg1, bg2, bg3 = PALETTE["bg0"], PALETTE["bg1"], PALETTE["bg2"], PALETTE["bg3"]
        line, text, muted, dim = PALETTE["line"], PALETTE["text"], PALETTE["muted"], PALETTE["dim"]
        cyan = PALETTE["cyan"]
        self.root.configure(bg=bg0)
        st.configure(".", background=bg0, foreground=text, fieldbackground=bg2, bordercolor=line,
                     lightcolor=bg2, darkcolor=bg2, troughcolor=bg2, selectbackground=cyan,
                     selectforeground=bg0, insertcolor=text, font=(self.ui_font, 10))
        st.configure("TFrame", background=bg0)
        st.configure("TLabel", background=bg0, foreground=text)
        st.configure("TLabelframe", background=bg0, bordercolor=line)
        st.configure("TLabelframe.Label", background=bg0, foreground=muted)
        st.configure("TButton", background=bg2, foreground=text, bordercolor=line, padding=(12, 6))
        st.map("TButton", background=[("active", bg3), ("disabled", bg1)],
               foreground=[("disabled", dim)])
        st.configure("Danger.TButton", background=bg2, foreground=PALETTE["crit"])
        st.map("Danger.TButton", background=[("active", bg3), ("disabled", bg1)],
               foreground=[("disabled", dim)])
        st.configure("TEntry", fieldbackground=bg2, foreground=text)
        st.configure("TSpinbox", fieldbackground=bg2, foreground=text, arrowcolor=muted)
        st.configure("TCombobox", fieldbackground=bg2, background=bg2, foreground=text, arrowcolor=muted)
        st.map("TCombobox", fieldbackground=[("readonly", bg2)], foreground=[("readonly", text)],
               selectbackground=[("readonly", bg3)])
        st.configure("TNotebook", background=bg0, bordercolor=line)
        st.configure("TNotebook.Tab", background=bg2, foreground=muted, padding=(12, 6))
        st.map("TNotebook.Tab", background=[("selected", bg3)], foreground=[("selected", text)])
        st.configure("TCheckbutton", background=bg0, foreground=text, indicatorbackground=bg2)
        st.map("TCheckbutton", background=[("active", bg0)])
        st.configure("TRadiobutton", background=bg0, foreground=text, indicatorbackground=bg2,
                     indicatorforeground=cyan)
        st.map("TRadiobutton", indicatorbackground=[("selected", bg2), ("!selected", bg2)],
               indicatorforeground=[("selected", cyan), ("!selected", bg0)])
        st.configure("TScale", background=bg0, troughcolor=bg2)
        st.configure("TProgressbar", background=cyan, troughcolor=bg2)
        st.configure("Treeview", background=bg2, fieldbackground=bg2, foreground=text, bordercolor=line)
        st.configure("Treeview.Heading", background=bg1, foreground=muted)
        st.map("Treeview", background=[("selected", bg3)], foreground=[("selected", text)])
        for orient in ("Vertical", "Horizontal"):  # a slim bar with no arrow buttons: a track and a rounded-looking thumb
            fill = "ns" if orient == "Vertical" else "ew"
            st.layout(f"{orient}.TScrollbar", [(f"{orient}.Scrollbar.trough", {"sticky": fill, "children": [
                (f"{orient}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
            st.configure(f"{orient}.TScrollbar", background=PALETTE["line2"], troughcolor=bg0, bordercolor=bg0,
                         lightcolor=PALETTE["line2"], darkcolor=PALETTE["line2"], relief="flat", gripcount=0,
                         arrowsize=10, width=10)
            st.map(f"{orient}.TScrollbar", background=[("active", cyan), ("pressed", cyan)],
                   lightcolor=[("active", cyan), ("pressed", cyan)], darkcolor=[("active", cyan), ("pressed", cyan)])
        st.configure("TStatusbar", background=bg1)
        # Dropdown lists and menus (not ttk, so set through the option database)
        self.root.option_add("*TCombobox*Listbox.background", bg2)
        self.root.option_add("*TCombobox*Listbox.foreground", text)
        self.root.option_add("*TCombobox*Listbox.selectBackground", bg3)
        self.root.option_add("*Menu.background", bg1)
        self.root.option_add("*Menu.foreground", text)
        self.root.option_add("*Menu.activeBackground", bg3)

    def build_ui(self):
        self._apply_dark_style()
        # No menu bar (design): Export and Import settings are on the Settings page, Graph Config is the
        # Sensors & Graphs page, About is in the sidebar, Exit is the window's close button.
        # Main notebook
        # Sidebar (v0.2.0 design): drives the notebook; the notebook's own tab bar is hidden
        self.sidebar = tk.Frame(self.root, bg=PALETTE["bg1"], width=SIDEBAR_W)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        style = ttk.Style()
        style.layout("Hidden.TNotebook.Tab", [])
        style.configure("Hidden.TNotebook", background=PALETTE["bg0"], borderwidth=0)
        self.nb = ttk.Notebook(self.root, style="Hidden.TNotebook", takefocus=0)  # its tabs are hidden: a Tab stop with no sign
        self.nb.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Dashboard Tab (first, opened by the sidebar) ---
        self.build_dashboard_tab(self.nb)
        _splash_step("dashboard")

        # --- Monitor Tab ---
        self.build_monitor_tab(self.nb)
        _splash_step("monitor")

        # --- Live Preview Tab ---
        self.build_preview_tab(self.nb)
        _splash_step("preview")

        self._lazy_gen = getattr(self, "_lazy_gen", 0) + 1
        self._lazy_pages, self._lazy_attrs = {}, set()
        self._lazy_page("Gallery", self.build_gallery_tab, "Gallery")
        _splash_step("gallery")

        # --- Theme Editor Tab ---
        self.build_theme_editor_tab(self.nb)
        _splash_step("editor")

        # --- Sensors & Graphs Tab (before Settings: the order of SIDEBAR_ITEMS) ---
        self._lazy_page("Sensors & Graphs", self.build_graph_config_tab, "Graph Config")
        _splash_step("graphs")

        # --- Settings Tab ---
        self.build_settings_tab(self.nb)
        _splash_step("settings_tab")

        # --- Diagnostics Tab ---
        self._lazy_page("Diagnostics", self.build_diagnostics_tab, "Diagnostics")
        _splash_step("diagnostics")

        self._lazy_page("About", self.build_about_tab, "About")
        _splash_step("about")

        self.build_sidebar()
        _splash_step("sidebar")

        # No status bar (design): the sidebar's device chip shows the state. The messages stay in status_var.
        self.status_var = tk.StringVar(value="Ready")
        self._dark_title_bar()
        fit_cards(self.nb)  # v0.3.6.1: the cards of every page have their size before the page is first shown

    # ─── v0.2.4: pages built on first visit ───
    # Gallery, Sensors & Graphs, Diagnostics and About are an empty frame until they are opened (or, 1 s after the
    # window is up, one at a time while it is idle): building all nine pages made a theme switch take 2 s. The pages that
    # other code reads variables from (Dashboard, Monitor, Live Preview, Settings) are built at once.

    def _lazy_page(self, name, builder, text):
        placeholder = tk.Frame(self.nb, bg=PALETTE["bg0"])
        self.nb.add(placeholder, text=text)
        self._lazy_pages[name] = (placeholder, builder)
        if len(self._lazy_pages) == 1:
            self.root.after(1000, self._prebuild_next, self._lazy_gen)

    def _ensure_page(self, name):
        """Build the page `name` now if it is still an empty frame; it keeps its place in the notebook."""
        entry = getattr(self, "_lazy_pages", {}).pop(name, None)
        if entry is None:
            return
        placeholder, builder = entry
        before = set(vars(self))
        selected = self.nb.select() == str(placeholder)
        position = self.nb.index(placeholder)
        tabs_before = set(self.nb.tabs())
        try:
            builder(self.nb)
        except Exception:
            for tab in set(self.nb.tabs()) - tabs_before:  # a half-built page is not left behind
                self.nb.forget(tab)
            self._lazy_pages[name] = entry  # and it is tried again at the next visit
            raise
        self._lazy_attrs |= set(vars(self)) - before
        built = self.nb.tabs()[-1]
        self.nb.insert(position, built)  # moves the new page from the end to where the empty frame is
        self.nb.forget(placeholder)
        placeholder.destroy()
        fit_cards(self.nb.nametowidget(built))
        if selected:
            self.nb.select(built)

    def _prebuild_next(self, gen):
        """While idle, build the pages nobody opened yet, one at a time."""
        if gen != self._lazy_gen:
            return
        if not self._lazy_pages:  # every page was opened by hand already
            self.root.after(800, self._prebuild_editor, gen)
            return
        try:
            if not self._window_hidden():
                self._ensure_page(next(iter(self._lazy_pages)))
        except Exception as e:
            log_swallowed("prebuild page", e)
        if self._lazy_pages:
            self.root.after(800, self._prebuild_next, gen)
        else:
            self.root.after(800, self._prebuild_editor, gen)

    def _prebuild_editor(self, gen):
        """v0.3.6.1: the Theme Editor is built while idle, not when it is first opened (building it on screen showed the
        page filling up piece by piece for over a second)."""
        if gen != self._lazy_gen or self.editor_initialized:
            return
        try:
            if self._window_hidden():
                self.root.after(800, self._prebuild_editor, gen)  # nothing to see: wait until the window is back
                return
            self.theme_editor = ThemeEditor(self, self.editor_frame)
            self.editor_initialized = True
        except Exception as e:
            log_swallowed("prebuild theme editor", e)

    # ─── v0.2.0 design: window icon, sidebar, dashboard ───

    def _dark_title_bar(self):
        """Colour the Windows title bar like the design's (dark, hairline border) with DWM; it keeps its native
        buttons, resize and snap. Windows 11 only: on older builds nothing changes."""
        try:
            import ctypes
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())

            def colorref(hex_colour):  # "#RRGGBB" -> 0x00BBGGRR
                r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
                return b << 16 | g << 8 | r
            for attr, value in ((20, 0 if self.settings.app_mode == "light" else 1), (34, colorref(PALETTE["line"])), (35, colorref(PALETTE["bg1"])),
                                (36, colorref(PALETTE["text"]))):  # dark mode, border, caption, caption text
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ctypes.c_int(value)), 4)
        except Exception as e:
            log_startup(self._startup_log, "TITLEBAR", f"dark title bar not applied: {e}")

    def _apply_window_icon(self):
        """Window and taskbar icon from assets/turmo_icon.png, shrunk (LANCZOS) to the sizes Windows asks for
        (no .ico: that one is only the exe icon); the default icon stays if it fails."""
        try:
            import ctypes
            from ctypes import wintypes
            user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
            user32.CreateIconIndirect.restype = ctypes.c_void_p
            user32.SetClassLongPtrW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
            user32.SendMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)
            src = Image.open(asset_path("turmo_icon.png")).convert("RGBA")

            def hicon(size):
                bgra = src.resize((size, size), Image.LANCZOS).tobytes("raw", "BGRA")
                colour = gdi32.CreateBitmap(size, size, 1, 32, bgra)
                mask = gdi32.CreateBitmap(size, size, 1, 1, None)
                class ICONINFO(ctypes.Structure):
                    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                                ("hbmMask", ctypes.c_void_p), ("hbmColor", ctypes.c_void_p)]
                return user32.CreateIconIndirect(ctypes.byref(ICONINFO(True, 0, 0, mask, colour)))
            big, small = (user32.GetSystemMetrics(11), user32.GetSystemMetrics(49))  # SM_CXICON, SM_CXSMICON
            self._icons = (hicon(big), hicon(small))  # kept alive for the window's lifetime
            # Hide the window BEFORE anything can map it (even update_idletasks maps a Tk root, and the window then
            # flashed over the loading screen): "-alpha 0" first. It stays hidden until show_window().
            # Then update_idletasks(): it makes Tk's wrapper window (the one the title bar and the taskbar button belong
            # to) and maps it, invisible. The icons go to that wrapper at once, on the class too: the taskbar button
            # takes its icon when the window first appears, and a wrapper asked for before this does not exist (GetParent
            # gives 0 on a fresh root, which is the real start: the loading screen runs first). From v0.2.1 (the flash
            # fix removed the early update_idletasks) to v0.2.3 the icons went nowhere: Tk's feather in both places.
            self.root.attributes("-alpha", 0.0)
            self.root.update_idletasks()
            hwnd = user32.GetParent(self.root.winfo_id())
            self._set_window_icons(user32, hwnd)
            self.root.update()
            self._set_window_icons(user32, user32.GetParent(self.root.winfo_id()))  # the same wrapper, unless Tk replaced it
        except Exception as e:
            log_startup(self._startup_log, "ICON", f"window icon not set: {e}")

    def _set_window_icons(self, user32, hwnd):
        """Window icon, and the same on the window class: under load the taskbar asks while the window is busy
        starting, gets no answer and falls back to the class icon (Tk's feather)."""
        for slot, (index, handle) in enumerate(((-14, self._icons[0]), (-34, self._icons[1]))):
            user32.SetClassLongPtrW(hwnd, index, handle)
            user32.SendMessageW(hwnd, 0x80, slot ^ 1, handle)  # WM_SETICON: ICON_BIG=1, ICON_SMALL=0

    def show_window(self):
        """Make the window visible once it is fully drawn (it was mapped invisible by _apply_window_icon)."""
        self.root.update_idletasks()
        self.root.update()
        self.root.attributes("-alpha", 1.0)

    def build_dashboard_tab(self, nb):
        bg0 = PALETTE["bg0"]
        frame = tk.Frame(nb, bg=bg0)
        nb.add(frame, text="Dashboard")
        page = ScrollFrame(frame, bg0, stretch=True)
        page.pack(fill=tk.BOTH, expand=True)
        body = tk.Frame(page.body, bg=bg0)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)
        body.columnconfigure(0, minsize=self.px(280))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)  # both columns fill the page, so it fits the window without scrolling
        left = tk.Frame(body, bg=bg0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        right = tk.Frame(body, bg=bg0)
        right.grid(row=0, column=1, sticky="nsew")
        self._build_dash_left(left)
        self._dash_hist = {m[5]: deque(maxlen=60) for m in DASHBOARD_METRICS + DASHBOARD_METRICS_2}
        self.dash_metrics = {}
        self._metric_row(right, DASHBOARD_METRICS).pack(fill=tk.X)
        self._build_dash_preview(right)
        self._metric_row(right, DASHBOARD_METRICS_2).pack(fill=tk.X, pady=(16, 0))

    def _build_dash_left(self, parent):
        bg0, bg2 = PALETTE["bg0"], PALETTE["bg2"]
        status_card = RoundedCard(parent, bg2, PALETTE["line"], bg0)
        status_card.pack(fill=tk.X)
        status = status_card.inner
        head = tk.Frame(status, bg=bg2)
        head.pack(fill=tk.X, padx=16, pady=(16, 0))
        tk.Label(head, text=tr("Device status"), bg=bg2, fg=PALETTE["text"],
                 font=(self.ui_semibold, 11)).pack(side=tk.LEFT)
        self.dash_state = Badge(head, bg2, (self.ui_font, 9, "bold"))
        self.dash_state.set(NO_VALUE, PALETTE["muted"])
        self.dash_state.pack(side=tk.RIGHT)
        self.dash_values = {}  # refresh rate and brightness live in Settings, not here
        for label in ("TURMO port", "Resolution", "Active theme"):
            row = tk.Frame(status, bg=bg2)
            row.pack(fill=tk.X, padx=16, pady=(10 if label == "TURMO port" else 3, 3))
            tk.Label(row, text=tr(label), bg=bg2, fg=PALETTE["muted"], font=(self.ui_font, 10)).pack(side=tk.LEFT)
            value = tk.Label(row, text=NO_VALUE, bg=bg2, fg=PALETTE["text"], font=("Cascadia Code", 10))
            value.pack(side=tk.RIGHT)
            self.dash_values[label] = value
        tk.Frame(status, bg=PALETTE["line"], height=1).pack(fill=tk.X, padx=16, pady=(12, 12))

        # Start / Stop / Restart / Test image: the same methods as the Monitor tab
        grid = tk.Frame(status, bg=bg2)
        grid.pack(fill=tk.X, padx=16, pady=(0, 16))
        grid.columnconfigure(0, weight=1, uniform="dash")
        grid.columnconfigure(1, weight=1, uniform="dash")
        icon = (ICON_FONT, 14)
        self.dash_start = self._dash_button(grid, "", tr("Start"), tr("Worker"), self.start_monitor, PALETTE["green"], 0, 0, icon)
        self.dash_stop = self._dash_button(grid, "", tr("Stop"), tr("Free the port"), self.stop_monitor, PALETTE["crit"], 0, 1, icon)
        self.dash_restart = self._dash_button(grid, "", tr("Restart"), tr("Reset USB link"), self.restart_monitor, None, 1, 0, icon)
        self.dash_test = self._dash_button(grid, "", tr("Test image"), tr("RGB pattern"), self.send_test_image, None, 1, 1, icon)

        # Quick theme chips: 2 columns
        theme_card = RoundedCard(parent, bg2, PALETTE["line"], bg0)
        theme_card.pack(fill=tk.BOTH, expand=True, pady=(16, 0))  # stretches so both columns end on one line
        inner = theme_card.inner
        head = tk.Frame(inner, bg=bg2)
        head.pack(fill=tk.X, padx=16, pady=(16, 0))
        tk.Label(head, text=tr("Quick theme"), bg=bg2, fg=PALETTE["text"], font=(self.ui_semibold, 11)).pack(side=tk.LEFT)
        make_button(head, tr("See all →"), lambda: self.select_tab(3), (self.ui_font, 9), variant="ghost",
                    backdrop=bg2, small=True).pack(side=tk.RIGHT)
        chips = tk.Frame(inner, bg=bg2)
        chips.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 16))
        chips.columnconfigure(0, weight=1, uniform="chip")
        chips.columnconfigure(1, weight=1, uniform="chip")
        for r in range((len(QUICK_THEMES) + 1) // 2):  # the free height is shared by the rows
            chips.rowconfigure(r, weight=1, uniform="chiprow")
        self.dash_chips = {}
        for i, (slug, label, dot) in enumerate(QUICK_THEMES):
            chip = ThemeChip(chips, label, dot, lambda s=slug: self.apply_quick_theme(s), bg2, bg2, (self.ui_font, 9))
            chip.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, 4) if i % 2 == 0 else (4, 0),
                      pady=(0, 8) if i < len(QUICK_THEMES) - 2 else 0)
            self.dash_chips[slug] = chip

    def _dash_button(self, parent, glyph, title, sub, command, tint, row, col, icon_font):
        btn = ControlButton(parent, glyph, title, sub, command, PALETTE["bg2"], tint, icon_font,
                            (self.ui_semibold, 11), (self.ui_font, 9))
        btn.grid(row=row, column=col, sticky="nsew", padx=(0, 6) if col == 0 else (6, 0),
                 pady=(0, 12) if row == 0 else 0)
        return btn

    def _metric_row(self, parent, metrics):
        bg0, bg2 = PALETTE["bg0"], PALETTE["bg2"]
        row = tk.Frame(parent, bg=bg0)
        for c in range(len(metrics)):
            row.columnconfigure(c, weight=1, uniform="metric")
        for i, (value_key, title, fmt, colour, glyph, hist_key, top) in enumerate(metrics):
            outer = RoundedCard(row, bg2, PALETTE["line"], bg0)
            outer.grid(row=0, column=i, sticky="nsew", padx=(0, 12) if i < len(metrics) - 1 else 0)
            card = outer.inner
            head = tk.Frame(card, bg=bg2)
            head.pack(fill=tk.X, padx=10, pady=(10, 0))
            tk.Label(head, text=glyph, bg=bg2, fg=colour, font=(ICON_FONT, 11)).pack(side=tk.LEFT)
            title_label = tk.Label(head, text=tr(title), bg=bg2, fg=PALETTE["muted"], font=(self.ui_font, 8, "bold"))
            title_label.pack(side=tk.LEFT, padx=(6, 0))
            value = tk.Label(card, text=NO_VALUE, bg=bg2, fg=PALETTE["text"], font=("Cascadia Code", 12, "bold"))
            value._title = (title_label, self.ui_font)
            value.pack(in_=head, side=tk.RIGHT)  # the card is its parent so it can move out of the head row
            Tip(value, lambda v=value, k=value_key: self._missing_reason(v, k))
            canvas = tk.Canvas(card, width=1, height=28, bg=bg2, highlightthickness=0)
            canvas.pack(fill=tk.X, padx=10, pady=(6, 10))
            outer.bind("<Configure>", lambda e, v=value, h=head, c=canvas: self._place_metric_value(e.width, v, h, c), add="+")
            self.dash_metrics[value_key] = (value, canvas, colour, fmt, hist_key, top)
        return row

    @staticmethod
    def _place_metric_value(width, value, head, canvas):
        """The value sits beside the title when the card is wide enough, else on its own line under it."""
        wide = width >= 210
        if wide == getattr(value, "_beside", True):
            return
        value._beside = wide
        title, font = value._title
        title.config(font=(font, 8 if wide else 7, "bold"))  # a narrow card (the value under the title) gets a smaller title
        value.pack_forget()
        if wide:
            value.pack(in_=head, side=tk.RIGHT)
        else:
            value.pack(in_=head.master, before=canvas, anchor="w", padx=10, pady=(6, 0))

    def _build_dash_preview(self, parent):
        bg0 = PALETTE["bg0"]
        card = RoundedCard(parent, bg0, PALETTE["line"], bg0)
        card.pack(fill=tk.BOTH, expand=True, pady=(16, 0))
        inner = card.inner
        head = tk.Frame(inner, bg=bg0)
        head.pack(fill=tk.X, padx=16, pady=12)
        self.dash_pv_dot = tk.Label(head, text="●", bg=bg0, fg=PALETTE["dim"], font=(self.ui_font, 9))
        self.dash_pv_dot.pack(side=tk.LEFT)
        tk.Label(head, text=tr("Live view of the physical display"), bg=bg0, fg=PALETTE["text"],
                 font=(self.ui_semibold, 10)).pack(side=tk.LEFT, padx=(8, 0))
        make_button(head, tr("Open Live Preview →"), lambda: self.select_tab(2), (self.ui_font, 9),
                    variant="ghost", backdrop=bg0, small=True).pack(side=tk.RIGHT)
        self.dash_orient = make_button(head, tr("Landscape"), self._toggle_dash_orientation,
                                       (self.ui_font, 9), variant="ghost", backdrop=bg0, small=True)
        self.dash_orient.pack(side=tk.RIGHT, padx=(0, 8))
        tk.Frame(inner, bg=PALETTE["line"], height=1).pack(fill=tk.X)
        self.dash_stage = tk.Canvas(inner, width=1, height=120, bg="#05070B", highlightthickness=0)
        self.dash_stage.pack(fill=tk.BOTH, expand=True)  # takes the height the window leaves; the screen is scaled to it
        self._dash_stage_key = None
        self.dash_stage.bind("<Configure>", lambda e: (setattr(self, "_dash_stage_key", None),
                                                       self._refresh_dashboard_preview()))
        tk.Frame(inner, bg=PALETTE["line"], height=1).pack(fill=tk.X)
        meta = tk.Frame(inner, bg=bg0)
        meta.pack(fill=tk.X, padx=16, pady=10)
        self.dash_pv_meta = {}
        for label in ("Status", "Resolution", "Port"):
            cell = tk.Frame(meta, bg=bg0)
            cell.pack(side=tk.LEFT, padx=(0, 20))
            tk.Label(cell, text=f"{tr(label)}: ", bg=bg0, fg=PALETTE["muted"], font=(self.ui_font, 9)).pack(side=tk.LEFT)
            value = tk.Label(cell, text=NO_VALUE, bg=bg0, fg=PALETTE["text"], font=(self.ui_semibold, 9))
            value.pack(side=tk.LEFT)
            self.dash_pv_meta[label] = value

    def _toggle_dash_orientation(self):
        self.landscape_var.set(self.settings.orientation != "landscape")
        self.on_orientation_change()
        self._refresh_dashboard_status()

    def _refresh_dashboard_preview(self):
        """Draw the display frame the Live Preview worker produced, or say that the preview is off."""
        landscape = self.settings.orientation == "landscape"
        with self._preview_lock:
            frame = self._preview_frame if self.preview_running else None
        stage = self.dash_stage
        w, h = max(stage.winfo_width(), 10), max(stage.winfo_height(), 10)
        key = (id(frame), landscape, w, h)
        if key == self._dash_stage_key:
            return
        self._dash_stage_key = key
        base = (360, 240) if landscape else (200, 300)
        fit = min(1.5, (w - 40) / base[0], (h - 40) / base[1])  # 20 px bezel + 10 px margin each side
        box = (max(int(base[0] * fit), 60), max(int(base[1] * fit), 40))
        stage.delete("all")
        cx, cy = w // 2, h // 2
        round_rect(stage, cx - box[0] / 2 - 10, cy - box[1] / 2 - 10, cx + box[0] / 2 + 10, cy + box[1] / 2 + 10,
                   18, fill="#0B0E14", outline=PALETTE["line2"])
        if frame is not None:
            self._dash_photo = ImageTk.PhotoImage(frame.resize(box, Image.LANCZOS))
            stage.create_image(cx, cy, image=self._dash_photo)
        else:
            stage.create_rectangle(cx - box[0] / 2, cy - box[1] / 2, cx + box[0] / 2, cy + box[1] / 2,
                                   fill="#05070B", outline="")
            stage.create_text(cx, cy - 8, text=tr("Live Preview is off"), fill=PALETTE["muted"],
                              font=(self.ui_semibold, 10))
            stage.create_text(cx, cy + 12, text=tr("Start it on the Live Preview tab"), fill=PALETTE["dim"],
                              font=(self.ui_font, 9))

    def build_sidebar(self):
        bar = self.sidebar
        bg1 = PALETTE["bg1"]
        from scripts.app_version import TURMO_VERSION
        tk.Label(bar, text=f"{TURMO_VERSION} · {tr('Desktop GUI')}", bg=bg1, fg=PALETTE["muted"],
                 font=(self.ui_font, 9), anchor="w").pack(fill=tk.X, padx=24, pady=(20, 6))
        # the footer is packed first so it keeps the bottom edge
        footer = tk.Frame(bar, bg=bg1)
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Frame(footer, bg=PALETTE["line"], height=1).pack(fill=tk.X)
        self._device_chip = DeviceChip(footer, bg1, (self.ui_font, 8, "bold"), ("Cascadia Code", 9),
                                       logo=self._chip_logo())
        self._device_chip.pack(fill=tk.X, padx=12, pady=(14, 8))
        mode = tk.Frame(footer, bg=bg1)
        mode.pack(fill=tk.X, padx=12, pady=(0, 14))  # same edges as the device card above
        tk.Label(mode, text=tr("Theme"), bg=bg1, fg=PALETTE["muted"], font=(self.ui_font, 10), padx=0).pack(side=tk.LEFT)
        self.light_var = tk.BooleanVar(value=self.settings.app_mode == "light")
        Switch(mode, self.light_var.get(), lambda _on: self.on_mode_change(), bg1, variable=self.light_var,
               shrink=0.88).pack(side=tk.RIGHT)
        self._sidebar_items = []
        for group, names in SIDEBAR_GROUPS:  # the groups, in order, are SIDEBAR_ITEMS: index = tab index
            tk.Label(bar, text=tr(group), bg=bg1, fg=PALETTE["dim"], font=(self.ui_font, 8, "bold"),
                     anchor="w").pack(fill=tk.X, padx=24, pady=(14, 4))
            for name in names:
                item = NavItem(bar, SIDEBAR_GLYPHS[name], tr(name),
                               lambda idx=len(self._sidebar_items): self.select_tab(idx),
                               bg1, (ICON_FONT, 13), (self.ui_font, 10))
                item.pack(fill=tk.X, padx=12, pady=2)
                self._sidebar_items.append(item)
        footer.lift()  # built first to keep the bottom edge; last in the Tab order
        self._fit_sidebar()
        self.nb.bind("<<NotebookTabChanged>>", self._sync_sidebar, add="+")
        self.select_tab(0)

    def _fit_sidebar(self):
        """A short window (a laptop screen at 125 % or more) cannot hold the nine entries at their usual spacing and
        Tk squeezes the last one: tighten the vertical margins (half, then none) until the list fits (v0.2.8)."""
        self.sidebar.update_idletasks()  # the requested heights are only known after a layout pass
        tops = [k for k in self.sidebar.winfo_children() if k.pack_info()["side"] == "top"]
        pads = {k: k.pack_info()["pady"] for k in tops}
        pair = lambda p: (p, p) if isinstance(p, int) else tuple(p)
        total = lambda: sum(k.winfo_reqheight() for k in self.sidebar.winfo_children()) + sum(sum(pair(k.pack_info()["pady"])) for k in tops)
        limit = self._window_sizes()[0][1]
        for share in (0.5, 0):
            if total() <= limit:
                return
            for k in tops:
                k.pack_configure(pady=tuple(round(v * share) for v in pair(pads[k])))

    def _chip_logo(self, height=34):
        """The T logo for the device card: as is on the dark look, inverted (black T) on the light one."""
        from PIL import ImageOps
        src = Image.open(asset_path("turmo_icon.png")).convert("RGBA")
        src = src.crop(src.getchannel("A").getbbox())
        w = round(src.width * height / src.height)
        src = src.resize((w, height), Image.LANCZOS)
        if self.settings.app_mode == "light":
            r, g, b, a = src.split()
            r, g, b = (ImageOps.invert(c) for c in (r, g, b))
            src = Image.merge("RGBA", (r, g, b, a))
        self._chip_photo = ImageTk.PhotoImage(src)  # kept: Tk drops an image nobody references
        return self._chip_photo

    def on_mode_change(self):
        """The Theme switch: dark or light window. The colours are read when widgets are built, so the window
        is built again; settings, the Monitor and the Live Preview worker are not touched."""
        self.settings.app_mode = "light" if self.light_var.get() else "dark"
        self.settings.save()
        set_mode(self.settings.app_mode)
        self.root.after_idle(self.rebuild_ui)

    def _curtain(self):
        """v0.3.5: a picture of the window, shown in a borderless window on top of it while the pages are built again, so
        the window stays on screen (it used to vanish for 2 to 3 seconds). None when the window cannot be photographed
        (minimised, in the tray): the caller hides it as before."""
        try:
            if self._window_hidden() or not self.root.winfo_viewable():
                return None
            from PIL import ImageGrab, ImageTk
            self.root.update_idletasks()
            x, y, w, h = self.root.winfo_rootx(), self.root.winfo_rooty(), self.root.winfo_width(), self.root.winfo_height()
            picture = ImageTk.PhotoImage(ImageGrab.grab((x, y, x + w, y + h)))
            cover = tk.Toplevel(self.root)
            cover.overrideredirect(True)
            cover.geometry(f"{w}x{h}+{x}+{y}")
            label = tk.Label(cover, image=picture, bd=0)
            label.image = picture  # kept: Tk drops a picture nobody holds
            label.pack()
            cover.attributes("-topmost", True)
            cover.update()
            return cover
        except Exception as e:  # ok: no curtain, the window is hidden while it is built, as before
            log_swallowed("rebuild_ui curtain", e)
            return None

    def rebuild_ui(self):
        tab = self.nb.index(self.nb.select())
        self._rebuilding = True
        cover = self._curtain()
        try:
            if cover is None:
                self.root.attributes("-alpha", 0.0)  # nothing of the half-built window is drawn
        except tk.TclError as e:
            log_swallowed("rebuild_ui hide window", e)
        try:
            for w in (self.sidebar, self.nb, getattr(self, "minimal_view", None)):
                if w is not None:
                    # v0.3.6.1: Tk drops the whole subtree at once (3x faster than tkinter walking about 1000 widgets)
                    self.root.tk.call("destroy", w._w)
                    self.root.children.pop(w._name, None)
            self.minimal_view, self._minimal_on = None, False
            self.theme_editor, self.editor_initialized = None, False
            for attr in getattr(self, "_lazy_attrs", ()):  # their widgets are gone: the pages are built again on demand
                self.__dict__.pop(attr, None)
            self.build_ui()
            self.refresh_port()  # build_ui made a new "Detecting..." label: it stayed that way for good
            self.apply_app_theme(self.settings.app_theme, initial=True)
            if self.settings.app_theme != "minimalist":
                self.select_tab(tab)
            self.root.update_idletasks()
            self.root.update()  # every widget is drawn in its final colours before the window shows again
        finally:
            try:
                self._rebuilding = False
                self.root.attributes("-alpha", 1.0)
                if cover is not None:
                    old = getattr(self, "_cover", None)
                    if old is not None and old is not cover:
                        self._drop_cover(old)
                    self._cover = cover
                    self._fade_cover(cover)  # v0.3.6.2: the old window fades into the new one instead of jumping
            except tk.TclError as e:
                log_swallowed("rebuild_ui show window", e)

    def select_tab(self, index):
        if getattr(self, "_covering", False):
            self._pending_tab = index  # a click that came while the picture was made: it wins
            return
        cover = self._page_cover(index)
        index = self.__dict__.pop("_pending_tab", index)
        try:
            self.nb.select(index)
            self._sync_sidebar()
            if cover is not None:
                self.root.update_idletasks()
                self.root.update()  # the new page is drawn completely behind the picture of the old one
        finally:
            if cover is not None:
                self._fade_cover(cover)  # also when a page builder raised: the picture never stays on screen

    def _page_cover(self, index):
        """v0.3.6.2: the picture of the page being left, shown over the pages while the new one is drawn (its cards used to
        appear one after the other). None when the setting is off, in the middle of a rebuild, or nothing can be photographed."""
        old = getattr(self, "_cover", None)
        if old is not None:
            self._drop_cover(old)
        if not self.settings.smooth_pages or getattr(self, "_rebuilding", False):
            return None
        try:
            if self._window_hidden() or not self.root.winfo_viewable() or not self.nb.winfo_ismapped():
                return None
            if self.nb.index("current") == index:
                return None
            from PIL import ImageGrab, ImageTk
            self.root.update_idletasks()
            x, y, w, h = self.nb.winfo_rootx(), self.nb.winfo_rooty(), self.nb.winfo_width(), self.nb.winfo_height()
            picture = ImageTk.PhotoImage(ImageGrab.grab((x, y, x + w, y + h)))
            cover = tk.Toplevel(self.root)
            self._cover = cover  # known before anything else can fail or run
            cover.overrideredirect(True)
            cover.geometry(f"{w}x{h}+{x}+{y}")
            label = tk.Label(cover, image=picture, bd=0)
            label.image = picture
            label.pack()
            cover.attributes("-topmost", True)
            self._covering = True
            try:
                cover.update()  # the picture must be on screen before the page changes
            finally:
                self._covering = False
            return cover
        except Exception as e:  # ok: the pages change without the fade
            log_swallowed("page cover", e)
            if getattr(self, "_cover", None) is not None:
                self._drop_cover(self._cover)
            return None

    def _drop_cover(self, cover):
        try:
            cover.destroy()
        except tk.TclError:  # ok: the picture is already gone (window closed)
            pass
        if getattr(self, "_cover", None) is cover:
            self._cover = None

    def _fade_cover(self, cover, step=0):
        """The picture fades out in 6 steps of 20 ms (about 120 ms), showing the finished page."""
        if getattr(self, "_cover", None) is not cover:
            return  # another page change took over
        try:
            if step >= 6:
                self._drop_cover(cover)
                return
            cover.attributes("-alpha", 1.0 - (step + 1) / 6)
            self.root.after(20, self._fade_cover, cover, step + 1)
        except tk.TclError:
            self._drop_cover(cover)

    def _sync_sidebar(self, event=None):
        if not hasattr(self, "_sidebar_items"):
            return
        current = self.nb.index("current")
        if SIDEBAR_ITEMS[current] in getattr(self, "_lazy_pages", ()):
            self._ensure_page(SIDEBAR_ITEMS[current])  # the page being opened is built now
            current = self.nb.index("current")
        for i, item in enumerate(self._sidebar_items):
            item.set_active(i == current)
        if current == SIDEBAR_ITEMS.index("Diagnostics") and hasattr(self, "diag_tiles"):
            self._refresh_diagnostics()  # it is not refreshed while another page is shown

    def _watch_port(self):
        """Plugging the display in (or out) after the app started must show on the Dashboard without pressing Refresh.
        A thread asks for the port once a second (about 8 ms); the answer is applied on the next tick. "Busy" is left
        alone: only Not found becomes Connected, and Connected becomes Not found."""
        probe = getattr(self, "_port_probe", None)
        if probe is None:
            probe = self._port_probe = {"busy": False, "port": False}  # False: no answer yet
        answer, probe["port"] = probe["port"], False
        if answer is not False:
            shown = self.port_var.get()
            if answer and "✓" not in shown:
                self.port_var.set(f"{answer} ✓")
            elif not answer and "✓" in shown:
                self.port_var.set("Not found ✗")
        if probe["busy"]:
            return

        def ask():
            try:
                probe["port"] = find_turmo_port()
            except Exception as e:
                log_swallowed("port watch", e)
            probe["busy"] = False
        probe["busy"] = True
        threading.Thread(target=ask, name="port-watch", daemon=True).start()

    def _link_state(self):
        """The Monitor's USB link state ("connected", "retrying", "busy", "not_found") or None when it is not running.
        Read once a second at most; a change tells the user (toast) and the tray."""
        now = time.monotonic()
        if now - getattr(self, "_link_read_at", -9.0) >= 0.9:
            self._link_read_at = now
            link = read_link_status()
            state = link["state"] if link else None
            if state == "connected" and link.get("port") and "✓" not in self.port_var.get():
                self.port_var.set(f"{link['port']} ✓")  # the Monitor found the display after the last port scan
            before = getattr(self, "_link_seen", None)
            if state != before:
                self._link_seen = state
                self._announce_link(before, state)
        seen = getattr(self, "_link_seen", None)
        if seen is None and self.monitor_status_var.get().startswith("Running"):
            return "starting"  # the Monitor is up but has not told its USB state yet: not "running" until it has
        return seen

    def _announce_link(self, before, state):
        """A toast when the display link is lost, and when it is back; the tray tooltip follows the state."""
        lost = state in ("retrying", "busy", "not_found")
        try:
            if lost and before in (None, "connected"):
                if before == "connected":  # a link that never was up at start is not a "lost" event
                    self.toast(tr("Display link lost, reconnecting…"), "error")
            elif state == "connected" and before in ("retrying", "busy", "not_found"):
                self.toast(tr("Display connected again"))
            if self.tray_icon:
                self.tray_icon.title = "TURMO Display" + {"retrying": " - " + tr("Reconnecting…"),
                                                          "busy": " - " + tr("Busy"),
                                                          "not_found": " - " + tr("Not found")}.get(state, "")
        except Exception as e:
            log_swallowed("link announce", e)

    def _refresh_device_chip(self):
        port = self.port_var.get()
        link = self._link_state()
        _label, level = device_status(port, self.monitor_status_var.get().startswith("Running"), link)
        text = device_chip_text(port, level, link)
        self._device_chip.set_status(text if text.startswith("TURMO \u00b7") else tr(text), level)

    def apply_quick_theme(self, slug):
        self.theme_var.set(slug)
        self.on_theme_change()
        self._refresh_dashboard_status()  # not _refresh_dashboard: that starts one more 1 s loop per click
        # v0.2.4.1: a running Monitor sees the new theme in settings.json and draws it by itself, no restart

    def _refresh_dashboard(self):
        """Every second: device status and live metrics. Never stops the loop, even on error.
        v0.2.4: nothing is redrawn while the window is minimised or in the tray, and the Diagnostics page (a full
        process scan) is refreshed only while it is the page on screen."""
        try:
            if self._window_hidden():
                self._poll_on = False  # the sensor poller thread ends after its current read
                self.root.after(1000, self._refresh_dashboard)
                return
            self._update_poll_on()
            self._watch_port()
            if hasattr(self, "_device_chip"):
                self._refresh_device_chip()
            self._refresh_preview_info()
            if hasattr(self, "dash_values"):
                self._refresh_dashboard_status()
                self._refresh_dashboard_metrics()
                self._refresh_dashboard_preview()
            if hasattr(self, "_sensor_rows"):
                self._refresh_sensor_panel()
            if hasattr(self, "diag_tiles") and self._diagnostics_shown():
                self._refresh_diagnostics()
        except Exception as e:
            log_startup(self._startup_log, "DASHBOARD", f"refresh failed: {e}")
        self.root.after(1000, self._refresh_dashboard)

    def _window_hidden(self):
        """True while the window is minimised or hidden in the tray: nothing on it can be seen."""
        try:
            return self.root.state() in ("iconic", "withdrawn")
        except tk.TclError:
            return False  # ok: the window is being rebuilt or closed; keep refreshing as before

    def _diagnostics_shown(self):
        try:
            return self.nb.index("current") == SIDEBAR_ITEMS.index("Diagnostics")
        except tk.TclError:
            return False  # ok: no page selected yet

    def _sensor_poller(self):
        """v0.2.6: the sensor poller (None when it cannot be made, said once in the start-up log)."""
        if hasattr(self, "_poller"):
            return self._poller
        self._poller = None
        try:
            from scripts.sensor_poll import SensorPoller, make_reader
            try:
                from turmo_runtime import read_cpu_temperature
            except ImportError:  # ok: the other import path (source run vs frozen) is tried next
                from scripts.turmo_runtime import read_cpu_temperature
            self._poller = SensorPoller(make_reader(self.settings, read_cpu_temperature), lambda: self._poll_on)
        except Exception as e:
            log_startup(self._startup_log, "SENSORS", f"sensor poller unavailable, only CPU load and RAM show: {e}")
        return self._poller

    def _update_poll_on(self):
        """The poller thread runs while the window is visible and Live Preview is off (the preview reads the sensors
        itself). Called every Dashboard tick, so it also stops a second after the preview starts."""
        shown = not self._window_hidden() or time.time() < getattr(self, "_meters_wanted_until", 0)
        self._poll_on = not self.preview_running and shown

    def temp_unit(self):
        """"celsius" or "fahrenheit": the Units choice as it is on screen (the page's variable, before it is saved),
        else the saved setting. v0.2.6.2: the Dashboard, Sensors page, panels and Live Preview follow it; the LCD
        themes do not yet."""
        var = getattr(self, "temp_unit_var", None)
        unit = var.get() if var is not None else self.settings.units.get("temp", "celsius")
        self._temp_unit_seen = unit  # for the Live Preview thread, which must not touch a Tk variable
        return unit

    def temp_unit_for_thread(self):
        """The unit for a worker thread: the last one `temp_unit()` saw on the Tk thread (every Dashboard tick)."""
        return getattr(self, "_temp_unit_seen", None) or self.settings.units.get("temp", "celsius")

    def sensor_reasons(self):
        """Why a sensor has no value while Live Preview is off ({} when the poller is not running)."""
        poller = getattr(self, "_poller", None)
        return poller.reasons() if poller is not None else {}

    def _missing_reason(self, label, key):
        """The tooltip of a Dashboard value: why it shows a dash. "" when it has a value or while Live Preview runs
        (the preview worker reads the sensors itself and gives no reason)."""
        if label.cget("text") != NO_VALUE or self.preview_running:
            return ""
        from scripts.sensor_poll import reason_for
        return reason_for(self.sensor_reasons(), key)

    def _psutil_readings(self):
        """What the Dashboard, the Sensors page and the panels show while Live Preview is off. v0.2.6: all the
        sensors, read once a second on a thread (`SensorPoller`); only CPU load and RAM when it cannot be made.
        While it runs nobody else calls cpu_percent (a second call a few ms later would measure nothing)."""
        self._update_poll_on()
        poller = self._sensor_poller()
        if poller is not None:
            poller.ensure_running()
            if poller.running():
                return poller.latest()  # {} for the first second: dashes, then the values
        now = time.time()
        cached = getattr(self, "_psutil_cache", None)
        if cached and now - cached[0] < 0.5:
            return dict(cached[1])
        values = {}
        try:
            import psutil
            vm = psutil.virtual_memory()
            values = {"cpu.load": psutil.cpu_percent(interval=None), "mem.load": vm.percent,
                      "mem.used": vm.used / 1024 ** 3}
        except Exception as e:
            if not getattr(self, "_psutil_warned", False):
                self._psutil_warned = True
                log_startup(self._startup_log, "PSUTIL", f"psutil readings unavailable: {e}")
        self._psutil_cache = (now, values)
        return dict(values)

    def _add_sensor_row(self, key):
        row = StatRow(self._sensor_inner, tr(sensor_name(key)), PALETTE["bg2"], (self.ui_semibold, 10),
                      ("Cascadia Code", 10))
        row.pack(fill=tk.X, padx=16, pady=(0, 8), before=self._sensor_tail)
        row._fit()
        self._sensor_rows[key] = (row._dot, row._value)
        self._sensor_widgets[key] = row
        self._sensor_hist.setdefault(key, deque(maxlen=60))

    def _sync_sensor_rows(self):
        """Active sensors lists the sensors the theme's graphs read: a graph on one that is not there adds its row,
        and a row added that way goes when no graph uses it any more."""
        if not hasattr(self, "_sensor_inner"):
            return
        used = {g["sensor"] for g in self.graph_configs}
        for key in sorted(used - set(self._sensor_rows)):
            self._add_sensor_row(key)
        for key in [k for k in self._sensor_rows if k not in SENSOR_FORMATS and k not in used]:
            self._sensor_widgets.pop(key).destroy()
            del self._sensor_rows[key]

    def _refresh_sensor_panel(self):
        with self._preview_lock:
            readings = dict(self._preview_readings) if self.preview_running else {}  # stopped: no stale values
        if "cpu.load" not in readings:  # Live Preview not running: psutil gives the loads, as on the Dashboard
            readings.update(self._psutil_readings())
        for key, (dot, value) in self._sensor_rows.items():
            text = metric_text(readings, key, sensor_format(key), self.temp_unit())
            value.config(text=text)
            dot.config(fg=PALETTE["green"] if text != NO_VALUE else PALETTE["dim"])
            raw = readings.get(key)
            number = getattr(raw, "value", raw)
            if isinstance(number, (int, float)):
                self._sensor_hist.setdefault(key, deque(maxlen=60)).append(float(number))
        chosen = next((k for k, n in SENSOR_NAMES.items() if tr(n) == self._chart_name.get()), "cpu.load")
        self._chart_value.config(text=self._sensor_rows[chosen][1].cget("text"))
        top = 100 if SENSOR_FORMATS[chosen].endswith(("%", "\u00b0C")) else None
        draw_spark(self._chart, sparkline_points(scale_history(self._sensor_hist[chosen], top),
                                                 max(self._chart.winfo_width(), 10),
                                                 max(self._chart.winfo_height(), 10)), PALETTE["cyan"], PALETTE["bg2"])

    def _refresh_dashboard_status(self):
        port = self.port_var.get()
        state, level = device_status(port, self.monitor_status_var.get().startswith("Running"), self._link_state())
        self.dash_state.set(tr(state), PALETTE[{"ok": "green", "busy": "warn", "off": "crit"}[level]])
        s = self.settings
        resolution = "480 \u00d7 320" if s.orientation == "landscape" else "320 \u00d7 480"
        self.dash_values["TURMO port"].config(text=port.replace(" \u2713", ""))
        self.dash_values["Resolution"].config(text=resolution)
        self.dash_values["Active theme"].config(text=s.theme)
        self.dash_start.config(state=self.start_btn.cget("state"))
        self.dash_stop.config(state=self.stop_btn.cget("state"))
        for slug, chip in self.dash_chips.items():
            chip.set_active(slug == s.theme)
        if hasattr(self, "dash_pv_meta"):
            self.dash_pv_meta["Status"].config(text=tr("Active") if self.preview_running else tr("Stopped"),
                                               fg=PALETTE["green"] if self.preview_running else PALETTE["muted"])
            self.dash_pv_meta["Resolution"].config(text=resolution)
            self.dash_pv_meta["Port"].config(text=port.replace(" \u2713", ""))
            self.dash_pv_dot.config(fg=PALETTE["green"] if self.preview_running else PALETTE["dim"])
            self.dash_orient.config(text=tr("Landscape") if s.orientation == "landscape" else tr("Portrait"))

    def _refresh_dashboard_metrics(self):
        with self._preview_lock:
            readings = dict(self._preview_readings) if self.preview_running else {}  # stopped: no stale values
        if "cpu.load" not in readings:  # Live Preview not running: psutil gives the loads
            for key, value in self._psutil_readings().items():
                readings.setdefault(key, value)
        down = getattr(readings.get("net.down"), "value", readings.get("net.down"))
        if isinstance(down, (int, float)):
            readings["net.mbs"] = down  # bytes per second, written by format_rate
        for hist_key, hist in self._dash_hist.items():
            raw = readings.get(hist_key)
            val = getattr(raw, "value", raw)
            if isinstance(val, (int, float)):
                hist.append(float(val))
        for value_key, (label, canvas, colour, fmt, hist_key, top) in self.dash_metrics.items():
            label.config(text=metric_text(readings, value_key, fmt, self.temp_unit()))
            history = scale_history(self._dash_hist[hist_key], top)
            draw_spark(canvas, sparkline_points(history, max(canvas.winfo_width(), 10),
                                                max(canvas.winfo_height(), 10)), colour, PALETTE["bg2"])

    def build_monitor_tab(self, nb):
        """Monitor: two columns that fit the window without scrolling. Left: the USB port and the quick
        settings. Right: the worker controls and its log, which takes the height that is left."""
        bg0, bg2 = PALETTE["bg0"], PALETTE["bg2"]
        frame = tk.Frame(nb, bg=bg0)
        nb.add(frame, text="Monitor")
        page = ScrollFrame(frame, bg0, stretch=True)
        page.pack(fill=tk.BOTH, expand=True)
        body = tk.Frame(page.body, bg=bg0)
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)
        page_header(body, tr("Monitor"), tr("The background worker that drives the display."), bg0,
                    (self.ui_semibold, 16), (self.ui_font, 10)).pack(fill=tk.X, pady=(0, 14))
        font, semi = (self.ui_font, 10), (self.ui_semibold, 11)
        cols = tk.Frame(body, bg=bg0)
        cols.pack(fill=tk.BOTH, expand=True)
        cols.rowconfigure(0, weight=1)
        cols.columnconfigure(0, weight=1, uniform="mon")
        cols.columnconfigure(1, weight=1, uniform="mon")
        left = tk.Frame(cols, bg=bg0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        right = tk.Frame(cols, bg=bg0)
        right.grid(row=0, column=1, sticky="nsew")
        fits = []  # cards made after the first layout need an explicit fit

        def card(parent, title, top=16, grow=False):
            outer = RoundedCard(parent, bg2, PALETTE["line"], bg0)
            outer.pack(fill=tk.BOTH if grow else tk.X, expand=grow, pady=(top, 0))
            tk.Label(outer.inner, text=title, bg=bg2, fg=PALETTE["text"], font=semi, anchor="w").pack(
                fill=tk.X, padx=16, pady=(14, 6))
            fits.append(outer)
            return outer.inner

        def line(inner, label):
            """A row: the label on the left, the returned frame for the control on the right."""
            row = tk.Frame(inner, bg=bg2)
            row.pack(fill=tk.X, padx=16, pady=5)
            tk.Label(row, text=label, bg=bg2, fg=PALETTE["muted"], font=font).pack(side=tk.LEFT)
            holder = tk.Frame(row, bg=bg2)
            holder.pack(side=tk.RIGHT)
            return holder

        # Hardware
        inner = card(left, tr("Hardware"), top=0)
        holder = line(inner, tr("TURMO port"))
        self.port_var = tk.StringVar(value="Detecting...")
        tk.Label(holder, textvariable=self.port_var, bg=bg2, fg=PALETTE["text"],
                 font=("Cascadia Code", 10, "bold")).pack(side=tk.LEFT, padx=(0, 12))
        make_button(holder, tr("Refresh"), self.refresh_port, font, variant="ghost", backdrop=bg2, small=True).pack(
            side=tk.LEFT, padx=(0, 8))
        make_button(holder, tr("Scan all ports"), self.show_all_ports, font, variant="ghost", backdrop=bg2,
                    small=True).pack(side=tk.LEFT)
        tk.Frame(inner, bg=bg2, height=10).pack()

        # Quick settings: the same variables as Settings and Live Preview
        inner = card(left, tr("Quick settings"), grow=True)  # stretches so both columns end on one line
        self.theme_var = tk.StringVar(value=self.settings.theme)
        self.theme_combo = Select(line(inner, tr("Theme")), self.get_available_themes, self.theme_var.get(),  # the list is read when it opens
                                  lambda _v: self.on_theme_change(), bg2, font, variable=self.theme_var, width=200, align="center")
        self.theme_combo.pack()
        self.landscape_var = tk.BooleanVar(value=self.settings.orientation == "landscape")
        orientation = Segmented(line(inner, tr("Orientation")), [(True, tr("Landscape")), (False, tr("Portrait"))],
                                self.landscape_var.get(), lambda _v: self.on_orientation_change(), bg2, font,
                                variable=self.landscape_var)
        orientation.pack()
        self.refresh_var = tk.IntVar(value=self.settings.refresh_ms)
        rates = [(250, "250 ms"), (500, "500 ms"), (1000, "1 s"), (2000, "2 s")]
        if self.refresh_var.get() not in [v for v, _l in rates]:  # a saved rate outside the list stays visible
            rates.append((self.refresh_var.get(), f"{self.refresh_var.get()} ms"))
        refresh = Segmented(line(inner, tr("Refresh")), rates, self.refresh_var.get(), lambda _v: self.on_refresh_change(),
                            bg2, font, variable=self.refresh_var)
        refresh.pack()
        self.gpu_index_var = tk.IntVar(value=self.settings.gpu_index)
        gpu = Segmented(line(inner, tr("GPU index")), [(i, str(i)) for i in range(8)], self.gpu_index_var.get(),
                        lambda _v: self.on_gpu_index_change(), bg2, font, variable=self.gpu_index_var)
        gpu.pack()
        # every control starts and ends where the GPU index boxes do (right edge unchanged)
        box = int(gpu.cget("width"))
        self.theme_combo.configure(width=box)
        orientation.fit_width(box)
        refresh.fit_width(box)
        if not hasattr(self, "brightness_var"):  # the same variable as Live Preview and Settings
            self.brightness_var = tk.IntVar(value=self.settings.brightness)
        holder = line(inner, tr("Brightness"))
        shown = tk.Label(holder, text=f"{int(self.brightness_var.get())}%", bg=bg2, fg=PALETTE["text"],
                         font=("Cascadia Code", 10), width=5, anchor="e")
        shown.pack(side=tk.RIGHT)
        self.brightness_var.trace_add("write", lambda *a: shown.config(text=f"{int(self.brightness_var.get())}%"))
        # the track starts at the left edge of the GPU boxes and the value ends at their right edge
        Slider(holder, 10, 100, self.brightness_var.get(), self.on_brightness_change, bg2,
               variable=self.brightness_var, step=1,
               width=box - shown.winfo_reqwidth() + Slider.PAD).pack(side=tk.RIGHT)
        # The applied theme's picture fills the space the window leaves in the card
        slot = tk.Frame(inner, bg=bg2, width=1, height=1)
        slot.pack(fill=tk.BOTH, expand=True, padx=16, pady=(8, 16))
        slot.pack_propagate(False)
        thumb = tk.Label(slot, bg=bg2, fg=PALETTE["muted"], font=font)

        def show_thumb(*_):
            room = (slot.winfo_width() - 4, slot.winfo_height() - 4)
            slug = {"minimal": "minimal-dark"}.get(self.theme_var.get(), self.theme_var.get())
            photo = self._gallery_thumb(slug, size=room, keep=False) if min(room) >= 60 else None
            self._monitor_thumb = photo  # Tk drops a picture nobody references
            thumb.config(image=photo or "", text="" if photo or min(room) < 60 else "No preview")
            thumb.place(relx=0.5, rely=0.5, anchor="center")
        self.theme_var.trace_add("write", show_thumb)
        slot.bind("<Configure>", show_thumb)

        # Monitor control
        inner = card(right, tr("Monitor control"), top=0)
        self.monitor_status_var = tk.StringVar(value="Stopped")
        holder = line(inner, tr("Status"))
        state_badge = Badge(holder, bg2, (self.ui_font, 9, "bold"))
        state_badge.pack()

        def show_state(*_):
            running = self.monitor_status_var.get().startswith("Running")
            text = self.monitor_status_var.get()  # "Running (started outside this window, PID n)" has a changing tail: only its first word is translated
            shown = tr("Running") + text[len("Running"):] if text.startswith("Running") else tr(text)
            state_badge.set(shown, PALETTE["green"] if running else PALETTE["muted"])
        self.monitor_status_var.trace_add("write", show_state)
        show_state()
        buttons = tk.Frame(inner, bg=bg2)
        buttons.pack(fill=tk.X, padx=16, pady=(8, 16))
        buttons.columnconfigure(0, weight=1, uniform="mb")
        buttons.columnconfigure(1, weight=1, uniform="mb")
        self.start_btn = make_button(buttons, tr("Start monitor"), self.start_monitor, font, variant="primary",
                                     backdrop=bg2)
        self.stop_btn = make_button(buttons, tr("Stop monitor"), self.stop_monitor, font, variant="danger",
                                    backdrop=bg2)
        self.stop_btn.config(state=tk.DISABLED)
        test_btn = make_button(buttons, tr("Send test image"), self.send_test_image, font, variant="ghost",
                               backdrop=bg2)
        restart_btn = make_button(buttons, tr("Restart monitor"), self.restart_monitor, font, variant="ghost",
                                  backdrop=bg2)
        for i, widget in enumerate((self.start_btn, self.stop_btn, test_btn, restart_btn)):
            widget.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 4) if i % 2 == 0 else (4, 0),
                        pady=(0, 8) if i < 2 else 0)

        # Log output: fills the rest of the column and scrolls inside
        inner = card(right, tr("Monitor log"), grow=True)
        logbox = tk.Frame(inner, bg=bg0, highlightbackground=PALETTE["line"], highlightthickness=1)
        logbox.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))
        self.log_text = tk.Text(logbox, height=4, width=1, bg=bg0, fg=PALETTE["muted"],
                                font=("Cascadia Code", 9), relief=tk.FLAT, highlightthickness=0, padx=10, pady=8,
                                wrap=tk.NONE)
        log_scroll = ttk.Scrollbar(logbox, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        for outer in fits:
            outer._fit()

    # ─── v0.2.0 design: theme gallery and diagnostics ───

    def build_theme_editor_tab(self, nb):
        """Build the theme editor tab."""
        editor_frame = tk.Frame(nb, bg=PALETTE["bg0"])
        nb.add(editor_frame, text="Theme Editor")

        # The ThemeEditor will be initialized when tab is shown
        self.editor_frame = editor_frame
        self.editor_initialized = False

        # Bind tab change event
        nb.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def _settings_show(self, name):
        """Show only the section `name` (each section is a page) and tint its nav item."""
        for key, item in self._settings_nav.items():
            on = key == name
            item.config(bg=mix(PALETTE["cyan"], PALETTE["bg0"], 0.13) if on else PALETTE["bg0"],
                        fg=PALETTE["cyan"] if on else PALETTE["muted"],
                        active_bg=mix(PALETTE["cyan"], PALETTE["bg0"], 0.13) if on else PALETTE["bg3"])
        for key, card in self._settings_sections.items():
            card.pack_forget()
        self._settings_sections[name].pack(fill=tk.X)
        self._settings_page._canvas.yview_moveto(0)

    def build_settings_tab(self, nb):
        """Settings (v0.2.0 design): a section nav on the left, one card per section with rows (label and
        description on the left, the control on the right). Same variables and handlers as before."""
        bg0, bg2 = PALETTE["bg0"], PALETTE["bg2"]
        small, label_font = (self.ui_font, 9), (self.ui_semibold, 10)
        frame = tk.Frame(nb, bg=bg0)
        nb.add(frame, text="Settings")
        page = ScrollFrame(frame, bg0)
        page.pack(fill=tk.BOTH, expand=True)
        body = tk.Frame(page.body, bg=bg0)
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=24)
        page_header(body, tr("Settings"), tr("Global configuration, the USB display and system preferences."), bg0,
                    (self.ui_semibold, 16), (self.ui_font, 10)).pack(fill=tk.X, pady=(0, 16))
        layout = tk.Frame(body, bg=bg0)
        layout.pack(fill=tk.BOTH, expand=True)
        layout.columnconfigure(0, minsize=self.px(200))
        layout.columnconfigure(1, weight=1)
        nav = tk.Frame(layout, bg=bg0)
        nav.grid(row=0, column=0, sticky="new", padx=(0, 16))
        stack = tk.Frame(layout, bg=bg0)
        stack.grid(row=0, column=1, sticky="new")
        self._settings_nav, sections = {}, {}
        self._settings_sections, self._settings_page = sections, page

        def card(name, title, subtitle):
            outer = RoundedCard(stack, bg2, PALETTE["line"], bg0)  # shown by _settings_show, one at a time
            tk.Label(outer.inner, text=title, bg=bg2, fg=PALETTE["text"], font=(self.ui_semibold, 11),
                     anchor="w").pack(fill=tk.X, padx=16, pady=(14, 0))
            tk.Label(outer.inner, text=subtitle, bg=bg2, fg=PALETTE["muted"], font=small, anchor="w").pack(
                fill=tk.X, padx=16, pady=(2, 6))
            sections[name] = outer
            btn = RoundedButton(nav, tr(name), lambda n=name: self._settings_show(n), bg0,
                                bg0, PALETTE["muted"], PALETTE["bg3"], (self.ui_font, 10), radius=10, padx=12,
                                pady=8, anchor="w")
            btn.pack(fill=tk.X, pady=(0, 2))
            self._settings_nav[name] = btn
            return outer.inner

        def row(inner, title, desc, desc_var=None):
            """A setting row: text on the left, and the frame for the control on the right."""
            tk.Frame(inner, bg=PALETTE["line"], height=1).pack(fill=tk.X, padx=16)
            line = tk.Frame(inner, bg=bg2)
            line.pack(fill=tk.X, padx=16, pady=10)
            left = tk.Frame(line, bg=bg2)
            left.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(left, text=title, bg=bg2, fg=PALETTE["text"], font=label_font, anchor="w").pack(fill=tk.X)
            kw = {"textvariable": desc_var} if desc_var is not None else {"text": desc}
            tk.Label(left, bg=bg2, fg=PALETTE["muted"], font=small, anchor="w", justify=tk.LEFT,
                     wraplength=380, **kw).pack(fill=tk.X)
            control = tk.Frame(line, bg=bg2)
            control.pack(side=tk.RIGHT, padx=(16, 0))
            return control

        # Windows startup
        inner = card("Windows startup", tr("Windows startup"), tr("Start with your Windows session."))
        self.startup_var = tk.BooleanVar(value=self.is_startup_enabled())
        Switch(row(inner, tr("Start TURMO monitor on Windows login"), tr("Runs the monitor automatically when you log in.")),
               self.startup_var.get(), lambda _v: self.toggle_startup(), bg2, variable=self.startup_var).pack()

        self.quick_panel_var = tk.BooleanVar(value=self.settings.quick_panel)
        Switch(row(inner, tr("Quick panel on tray click"),
                   tr("A click on the tray icon opens a small panel above the taskbar; a double click opens this window.")), self.quick_panel_var.get(),
               lambda _v: self.on_quick_panel_change(), bg2, variable=self.quick_panel_var).pack()

        # App theme: the choice is saved; only Default is drawn today
        tk.Frame(inner, bg=PALETTE["line"], height=1).pack(fill=tk.X, padx=16)
        tk.Label(inner, text=tr("App theme"), bg=bg2, fg=PALETTE["text"], font=label_font, anchor="w").pack(
            fill=tk.X, padx=16, pady=(10, 0))
        tk.Label(inner, text=tr("Look of this window. Only Default is drawn for now; the others are coming."), bg=bg2,
                 fg=PALETTE["muted"], font=small, anchor="w").pack(fill=tk.X, padx=16)
        choices = tk.Frame(inner, bg=bg2)
        choices.pack(fill=tk.X, padx=16, pady=(10, 16))
        self.app_theme_tiles = {}
        chosen = self.settings.app_theme if self.settings.app_theme in ("default", "minimalist") else "default"
        for i, (key, name) in enumerate((("default", tr("Default")), ("minimalist", tr("Minimalist")))):
            choices.columnconfigure(i, weight=1, uniform="looks")
            tile = ChoiceTile(choices, name, key == chosen, lambda k=key: self.on_app_theme_change(k), bg2,
                              (self.ui_semibold, 10))
            tile.grid(row=0, column=i, sticky="ew", padx=(0, 10) if i < 1 else 0)
            self.app_theme_tiles[key] = tile

        # CPU temperature helper
        inner = card("CPU temperature", tr("CPU temperature"), tr("Helper that reads the CPU sensor (one UAC prompt at install)."))
        self.helper_status = tk.StringVar(value=tr("Helper: not installed"))
        control = row(inner, tr("Temperature helper"), "", desc_var=self.helper_status)
        self.helper_btn = make_button(control, tr("Enable CPU temperature (one-time UAC)"), self.toggle_cpu_temp_helper,
                                      (self.ui_font, 10), variant="primary", backdrop=bg2)
        self.helper_btn.pack()
        self._refresh_helper_status()

        # Display
        inner = card("Display", tr("Display"), tr("Brightness and orientation of the 3.5\u2033 screen."))
        if not hasattr(self, "brightness_var"):
            self.brightness_var = tk.IntVar(value=self.settings.brightness)
        control = row(inner, tr("Brightness"), tr("Dims the pixels sent to the display and the preview."))
        value = tk.Label(control, text=f"{int(self.brightness_var.get())}%", bg=bg2, fg=PALETTE["text"],
                         font=("Cascadia Code", 10), width=5, anchor="e")
        value.pack(side=tk.RIGHT)
        self.brightness_var.trace_add("write", lambda *a: value.config(text=f"{int(self.brightness_var.get())}%"))
        Slider(control, 10, 100, self.brightness_var.get(), self.on_brightness_change, bg2,
               variable=self.brightness_var, step=1, width=200).pack(side=tk.RIGHT)
        Segmented(row(inner, tr("Orientation"), tr("Landscape (480 \u00d7 320) or portrait (320 \u00d7 480).")),
                  [(True, tr("Landscape")), (False, tr("Portrait"))], self.landscape_var.get(),
                  lambda _v: self.on_orientation_change(), bg2, small, variable=self.landscape_var).pack()

        # Screen colour (v0.2.9.1): the LCD's colour correction and a white balance the user sets by eye
        inner = card("Screen colour", tr("Screen colour"),
                     tr("Match the 3.5″ screen's colours to the previews. Changes reach the running display at once."))
        self.color_correction_var = tk.BooleanVar(value=bool(self.settings.color_correction))
        Switch(row(inner, tr("Colour correction"),
                   tr("Evens out the screen's blue-heavy greys. Off sends the picture unchanged.")),
               self.color_correction_var.get(), lambda _v: self.on_color_correction_change(), bg2,
               variable=self.color_correction_var).pack()
        self.color_gain_vars = {}
        shown = dict(zip("rgb", gain_values(self.settings.color_gain)))
        for key, title, desc in (("r", "Red", "Less red makes whites bluer."), ("g", "Green", "Less green makes whites pinker."),
                                 ("b", "Blue", "Less blue makes whites warmer.")):
            var = self.color_gain_vars[key] = tk.IntVar(value=shown[key])
            control = row(inner, tr(title), tr(desc))
            label = tk.Label(control, text=f"{var.get()}%", bg=bg2, fg=PALETTE["text"], font=("Cascadia Code", 10),
                             width=5, anchor="e")
            label.pack(side=tk.RIGHT)
            var.trace_add("write", lambda *a, v=var, l=label: l.config(text=f"{int(v.get())}%"))
            Slider(control, GAIN_RANGE[0], GAIN_RANGE[1], var.get(), lambda val, k=key: self.on_color_gain_change(k, val),
                   bg2, variable=var, step=1, width=200).pack(side=tk.RIGHT)
        make_button(row(inner, tr("Reset colours"), tr("Back to 100% for red, green and blue.")), tr("Reset"),
                    self.on_color_gain_reset, (self.ui_font, 10), variant="ghost", backdrop=bg2).pack()

        # Logs (v0.3.0): how long and how much to keep
        self.build_logs_card(card, row, bg2, small)

        # Language: the choice is saved and the window is drawn again in it (i18n.py)
        inner = card("Language", tr("Language"), tr("Language of this window."))
        tk.Frame(inner, bg=PALETTE["line"], height=1).pack(fill=tk.X, padx=16)
        choices = tk.Frame(inner, bg=bg2)
        choices.pack(fill=tk.X, padx=16, pady=(10, 16))
        self.language_tiles = {}
        chosen = self.settings.language if self.settings.language in ("en", "fr", "pt") else "en"
        for i, (key, name) in enumerate((("en", "English"), ("fr", "Fran\u00e7ais"), ("pt", "Portugu\u00eas"))):
            choices.columnconfigure(i, weight=1, uniform="langs")
            tile = ChoiceTile(choices, name, key == chosen, lambda k=key: self.on_language_change(k), bg2,
                              (self.ui_semibold, 10))
            tile.grid(row=0, column=i, sticky="ew", padx=(0, 10) if i < 2 else 0)
            self.language_tiles[key] = tile

        # Units
        inner = card("Units", tr("Units"), tr("How values are written on the display."))
        if not hasattr(self, "temp_unit_var"):  # the Sensors & Graphs page owns it when it is built first
            self.temp_unit_var = tk.StringVar(value=self.settings.units.get("temp", "celsius"))
        self.clock_unit_var = tk.StringVar(value=self.settings.units.get("clock", "24h"))
        self.data_unit_var = tk.StringVar(value=self.settings.units.get("data", "auto"))
        for title, desc, var, values in (
                ("Temperature", "Celsius or Fahrenheit.", self.temp_unit_var, ["celsius", "fahrenheit"]),
                ("Clock", "12 or 24 hour clock.", self.clock_unit_var, ["12h", "24h"]),
                ("Data", "Automatic or manual data units.", self.data_unit_var, ["auto", "manual"])):
            Select(row(inner, tr(title), tr(desc)), values, var.get(), None, bg2, (self.ui_font, 10), variable=var,
                   width=150).pack()
            var.trace_add("write", lambda *_: self.on_unit_change())

        # Visible widgets
        inner = card("Visible widgets", tr("Visible widgets"), tr("Which blocks the themes draw."))
        tk.Frame(inner, bg=PALETTE["line"], height=1).pack(fill=tk.X, padx=16)
        grid = tk.Frame(inner, bg=bg2)
        grid.pack(fill=tk.X, padx=16, pady=(10, 8))
        self.widget_vars = {}
        for i, w in enumerate(["clock", "cpu", "gpu", "ram", "net", "disk", "graph"]):
            var = tk.BooleanVar(value=self.settings.widgets.get(w, True))
            self.widget_vars[w] = var
            grid.columnconfigure(i % 4, weight=1, uniform="widgets")
            cell = tk.Frame(grid, bg=bg2)
            cell.grid(row=i // 4, column=i % 4, sticky="w", pady=4)
            Switch(cell, var.get(), lambda _v, w=w: self.on_widget_change(w), bg2, variable=var).pack(side=tk.LEFT)
            tk.Label(cell, text=tr({"cpu": "CPU", "gpu": "GPU", "ram": "RAM", "net": "Network"}.get(w, w.capitalize())), bg=bg2, fg=PALETTE["text"], font=(self.ui_font, 10)).pack(
                side=tk.LEFT, padx=(8, 0))

        # Appearance
        inner = card("Appearance", tr("Appearance"), tr("Text size and spacing of this window."))
        self.font_scale_var = tk.DoubleVar(value=round(self.settings.font_scale, 2))
        control = row(inner, tr("UI font scale"), tr("Applies after a restart."))
        scale_label = tk.Label(control, text=f"{self.font_scale_var.get():.2f}", bg=bg2, fg=PALETTE["text"],
                               font=("Cascadia Code", 10), width=5, anchor="e")
        scale_label.pack(side=tk.RIGHT)
        self.font_scale_var.trace_add("write", lambda *a: scale_label.config(text=f"{self.font_scale_var.get():.2f}"))
        Slider(control, 0.7, 1.5, self.font_scale_var.get(), self.on_font_scale_change, bg2,
               variable=self.font_scale_var, step=0.05, width=200).pack(side=tk.RIGHT)
        self.compact_var = tk.BooleanVar(value=self.settings.compact)
        Switch(row(inner, tr("Compact layout"), tr("Smaller margins.")), self.compact_var.get(),
               lambda _v: self.on_compact_change(), bg2, variable=self.compact_var).pack()
        self.smooth_var = tk.BooleanVar(value=self.settings.smooth_pages)
        Switch(row(inner, tr("Smooth page changes"), tr("Fades to the new page once it is drawn. Off: pages change at once.")),
               self.smooth_var.get(), lambda _v: self.on_smooth_change(), bg2, variable=self.smooth_var).pack()

        # Port override
        inner = card("Port", tr("Port"), tr("Fix the COM port of the display."))
        self.port_override_var = tk.StringVar(value=self.settings.port)
        field = RoundedCard(row(inner, tr("COM port override"), tr("Empty means automatic detection.")), bg0,
                            PALETTE["line2"], bg2, radius=10, width=150)
        field.pack()
        tk.Entry(field.inner, textvariable=self.port_override_var, bg=bg0, fg=PALETTE["text"],
                 insertbackground=PALETTE["text"], relief=tk.FLAT, highlightthickness=0,
                 font=("Cascadia Code", 10), width=1).pack(fill=tk.X, padx=10, ipady=5)
        self.port_override_var.trace_add("write", lambda *_: self.on_port_override_change())

        # Backup and restore
        inner = card("Backup & restore", tr("Backup & restore"), tr("Export or import all settings."))
        tk.Frame(inner, bg=PALETTE["line"], height=1).pack(fill=tk.X, padx=16)
        buttons = tk.Frame(inner, bg=bg2)
        buttons.pack(fill=tk.X, padx=16, pady=(12, 16))
        make_button(buttons, tr("Export settings"), self.export_settings, (self.ui_font, 10), variant="primary",
                    backdrop=bg2).pack(side=tk.LEFT, padx=(0, 8))
        make_button(buttons, tr("Import settings"), self.import_settings, (self.ui_font, 10), variant="ghost",
                    backdrop=bg2).pack(side=tk.LEFT)
        self._settings_show("Windows startup")

    # ─── Tab Events ───

    def on_tab_changed(self, event):
        """Handle tab change - initialize editor when shown."""
        nb = event.widget
        # Compare the widget, not the index: the Dashboard tab moved the Theme Editor to index 3
        if nb.nametowidget(nb.select()) is self.editor_frame:
            if not self.editor_initialized:
                self.theme_editor = ThemeEditor(self, self.editor_frame)
                self.editor_initialized = True

    # ─── Hardware & Port ───

    def get_available_themes(self):
        themes = theme_paths.names(DATA_ROOT / "themes")  # official and custom, no orientation variants
        # Add alias for "minimal" -> "minimal-dark"
        if "minimal-dark" in themes and "minimal" not in themes:
            themes.append("minimal")
        return sorted(themes) or ["cyberpunk-neon"]

    def refresh_port(self):
        """Refresh the port detection with detailed status."""
        self.status_var.set(tr("Scanning ports..."))
        self.root.update_idletasks()

        port = find_turmo_port()
        all_ports = scan_all_ports()

        # Check if TURMO device is present in PnP but busy
        turmo_in_pnp = any(
            p["vid"] == "0x1a86" and p["pid"] == "0x5722" 
            for p in all_ports
        )

        if port:
            self.port_var.set(f"{port} ✓")
            self.status_var.set(tr("TURMO connected on {port}").format(port=port))
        elif turmo_in_pnp:
            self.port_var.set("Busy / In Use ⚠")
            self.status_var.set(tr("TURMO detected but COM port busy (another app?)"))
        else:
            self.port_var.set("Not found ✗")
            self.status_var.set(tr("No TURMO device (VID 1A86:5722) detected"))

        # Update Start button state
        if hasattr(self, 'start_btn'):
            self.start_btn.config(state=tk.NORMAL)  # v0.3.0: the Monitor waits for a display that is not there yet

    def show_all_ports(self):
        modal = Modal(self, tr("All serial ports"), width=700)
        bg2 = PALETTE["bg2"]
        columns = (("Device", 90), ("Description", 280), ("VID:PID", 120), ("Serial", 150))
        tree = ttk.Treeview(modal.body, columns=[c for c, _w in columns], show="headings", height=8)
        for col, width in columns:
            tree.heading(col, text=col)
            tree.column(col, width=width)
        for p in scan_all_ports():
            marker = " <- TURMO" if p["vid"] == "0x1a86" and p["pid"] == "0x5722" else ""
            tree.insert("", tk.END, values=(p["device"], p["description"], f"{p['vid']}:{p['pid']}", p["serial"] + marker))
        tree.pack(fill=tk.BOTH, expand=True)
        make_button(modal.body, tr("Close"), modal.close, (self.ui_font, 10), variant="ghost", backdrop=bg2).pack(
            anchor="e", pady=(14, 0))
        modal.show()

    def auto_detect_gpu(self):
        """At startup: initialise NVML once and pick a valid GPU index, no dialog."""
        try:
            import pynvml
            pynvml.nvmlInit()
            self._pynvml_init = True
            count = pynvml.nvmlDeviceGetCount()
            idx = self.settings.gpu_index if self.settings.gpu_index < count else 0
            name = pynvml.nvmlDeviceGetName(pynvml.nvmlDeviceGetHandleByIndex(idx))
            if isinstance(name, bytes):
                name = name.decode()
            if idx != self.settings.gpu_index:
                self.settings.gpu_index = idx
                self.settings.save()
            self.gpu_index_var.set(idx)
            self.log_text.insert(tk.END, f"  GPU {idx}: {name} (auto-detected)\n")
        except Exception as e:
            self.log_text.insert(tk.END, f"  GPU auto-detect failed: {e}\n")

    # ─── Settings Handlers ───

    def on_theme_change(self, event=None):
        theme = self.theme_var.get()
        # Resolve "minimal" alias to "minimal-dark"
        if theme == "minimal":
            theme = "minimal-dark"
        self.settings.theme = theme
        self.settings.save()
        self.status_var.set(tr("Theme: {theme}").format(theme=theme))
        # Reload theme editor if open
        if self.editor_initialized and self.theme_editor:
            self.theme_editor.follow(theme)
        # Update preview
        if self.preview_running:
            self.restart_preview()

    def on_orientation_change(self):
        self.settings.orientation = "landscape" if self.landscape_var.get() else "portrait"
        if hasattr(self, "_gallery_grid"):  # the gallery shows the pictures of this orientation
            self._gallery_render()
        if self.editor_initialized and self.theme_editor and \
                self.theme_editor.editor_orientation.get() != self.settings.orientation:
            self.theme_editor.editor_orientation.set(self.settings.orientation)
            self.theme_editor.on_orientation_change()
        self.settings.save()
        self.status_var.set(tr("Orientation: {orientation}").format(orientation=tr(self.settings.orientation.capitalize())))
        self._refresh_preview_caption()
        if self.preview_running:
            self.restart_preview()
        # a running Monitor sees the new orientation in settings.json and switches the panel by itself, no restart

    def on_refresh_change(self):
        self.settings.refresh_ms = self.refresh_var.get()
        self.settings.save()

    def on_gpu_index_change(self):
        self.settings.gpu_index = self.gpu_index_var.get()
        self.settings.save()

    def on_brightness_change(self, val):
        self.settings.brightness = int(float(val))
        self.settings.save()

    def on_color_correction_change(self):
        self.settings.color_correction = bool(self.color_correction_var.get())
        self.settings.save()

    def on_color_gain_change(self, key, val):
        self.settings.color_gain = dict(zip("rgb", gain_values(self.settings.color_gain)))  # a saved odd value is cleaned
        self.settings.color_gain[key] = int(float(val))
        self.settings.save()

    def on_color_gain_reset(self):
        self.settings.color_gain = {"r": 100, "g": 100, "b": 100}
        for var in self.color_gain_vars.values():
            var.set(100)
        self.settings.save()

    def on_unit_change(self):
        self.settings.units["temp"] = self.temp_unit_var.get()
        self.settings.units["clock"] = self.clock_unit_var.get()
        self.settings.units["data"] = self.data_unit_var.get()
        self.settings.save()

    def on_widget_change(self, widget):
        self.settings.widgets[widget] = self.widget_vars[widget].get()
        self.settings.save()

    def on_font_scale_change(self, val):
        self.settings.font_scale = round(float(val), 2)  # not 1.0139784946236559
        self.settings.save()

    def on_quick_panel_change(self):
        self.settings.quick_panel = self.quick_panel_var.get()
        self.settings.save()

    def theme_swatches(self, slug):
        """The three colours of a theme's gallery tile (accent, background, text), or none when it has no palette."""
        try:
            pal = json.loads((theme_paths.folder(DATA_ROOT / "themes", slug) / "theme.json").read_text(encoding="utf-8")).get("palette")
        except Exception as _e:
            log_swallowed("tray icon colours", _e)
            return ()
        if not pal:
            return ()
        return (tk_colour(pal.get("accent", PALETTE["cyan"])), tk_colour(pal.get("bg", PALETTE["bg0"])),
                mix(PALETTE["text"], PALETTE["bg3"], 0.3))

    def on_language_change(self, key):
        """A tile was chosen: ask first (in the language offered), change only on Yes, put the tiles back on No."""
        if key == i18n.language():
            self._show_language_tiles(key)
            return
        title, question, yes, no = i18n.LANGUAGE_PROMPT[key]
        self.confirm(title, question, yes, lambda: self._apply_language(key),
                     no_label=no, on_no=lambda: self._show_language_tiles(i18n.language()))

    def _show_language_tiles(self, key):
        groups = [self.language_tiles]
        if getattr(self, "minimal_view", None) is not None:
            groups.append(self.minimal_view.language_tiles)
        for group in groups:
            for k, tile in group.items():
                tile.set_selected(k == key)

    def _apply_language(self, key):
        self._show_language_tiles(key)
        self.settings.language = key
        self.settings.save()
        i18n.set_language(key)
        self.root.after_idle(self.rebuild_ui)  # after this click is handled: the tile that was pressed is destroyed with the window

    def on_app_theme_change(self, key):
        tiles = [self.app_theme_tiles]
        if getattr(self, "minimal_view", None) is not None:
            tiles.append(self.minimal_view.look_tiles)
        for group in tiles:
            for k, tile in group.items():
                tile.set_selected(k == key)
        self.settings.app_theme = key
        self.settings.save()
        self.apply_app_theme(key)

    def px(self, n):
        """A pixel width designed at 96 dpi, grown with the screen scaling (fonts grow, fixed widths must too)."""
        return round(n * max(1.0, self.root.winfo_fpixels("1i") / 96))

    def _window_sizes(self):
        """(full size, minimal size) in pixels for this screen's scaling and work area (v0.2.8)."""
        wa = work_area()
        area = (wa[2] - wa[0], wa[3] - wa[1]) if wa else None
        dpi = self.root.winfo_fpixels("1i")
        return window_size(FULL_SIZE, dpi, area), window_size(MINIMAL_MIN, dpi, area)

    def _set_resize_mode(self, minimal):
        """How the window may change size (v0.2.3). Minimal look: not at all (no grip, no maximise button, only
        minimise and close). Full look: floating, it keeps its size (the thick frame is taken off, so no edge can be
        dragged), but the maximise button stays and gives a full-screen window; the pages follow its size."""
        if minimal:
            self.root.minsize(*self._window_sizes()[1])  # the full look's minimum would keep the window from getting small
            self.root.resizable(False, False)
            return
        self.root.resizable(True, True)  # brings the maximise button back
        self.root.minsize(*self._window_sizes()[0])
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.GetParent.restype, user32.GetParent.argtypes = ctypes.c_void_p, (ctypes.c_void_p,)
            user32.GetWindowLongW.restype, user32.GetWindowLongW.argtypes = ctypes.c_long, (ctypes.c_void_p, ctypes.c_int)
            user32.SetWindowLongW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_long)
            user32.SetWindowPos.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_uint)
            self.root.update_idletasks()
            hwnd = user32.GetParent(self.root.winfo_id())
            style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
            user32.SetWindowLongW(hwnd, -16, style & ~0x00040000)  # WS_THICKFRAME off
            # SWP_NOSIZE | NOMOVE | NOZORDER | NOACTIVATE | FRAMECHANGED
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
            self.root.update_idletasks()
            if not self.root.state() == "zoomed":
                self.root.geometry("%dx%d" % self._window_sizes()[0])  # the frame change moved the client size by a few pixels
        except Exception as e:
            log_swallowed("resize frame", e)

    def apply_app_theme(self, key, initial=False):
        """Show the look chosen in Settings: "minimalist" is the small window, anything else the full one.
        Nothing is rebuilt but the visible frame, so every setting and running worker stays as it is."""
        minimal = key == "minimalist"
        if minimal == (getattr(self, "_minimal_on", False)) and (not minimal or not initial):
            self._minimal_on = minimal  # already showing this look
            return
        self.root.update_idletasks()
        if minimal:
            if not getattr(self, "_minimal_on", False):
                self._full_geometry = self.root.geometry() if self.root.state() == "normal" else "%dx%d" % self._window_sizes()[0]
            self.sidebar.pack_forget()
            self.nb.pack_forget()
            if getattr(self, "minimal_view", None) is None:
                self.minimal_view = MinimalView(self, self.root)
            self.minimal_view.pack(fill=tk.BOTH, expand=True)
            self._set_resize_mode(True)
            where = "+" + self.root.geometry().split("+", 1)[1] if "+" in self.root.geometry() else ""
            self.root.geometry("%dx%d" % self._window_sizes()[1] + where)
            self.minimal_view.refresh()
        else:
            if getattr(self, "minimal_view", None) is not None:
                self.minimal_view.pack_forget()
            self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
            self.nb.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
            self._set_resize_mode(False)
            self.root.geometry(getattr(self, "_full_geometry", None) or "%dx%d" % self._window_sizes()[0])
        self._minimal_on = minimal

    def on_compact_change(self):
        self.settings.compact = self.compact_var.get()
        self.settings.save()

    def on_smooth_change(self):
        self.settings.smooth_pages = self.smooth_var.get()
        self.settings.save()

    def on_port_override_change(self):
        self.settings.port = self.port_override_var.get()
        self.settings.save()

    def is_startup_enabled(self):
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            value = winreg.QueryValueEx(key, "TURMO")[0]
            winreg.CloseKey(key)
            hidden = startup_entry.upgraded(value, GUI_EXE)
            if hidden:  # v0.3.7.2: an entry written by an older version ran the console Monitor (a black window at sign-in)
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                    winreg.SetValueEx(key, "TURMO", 0, winreg.REG_SZ, hidden)
                    winreg.CloseKey(key)
                except OSError as _e:  # the entry exists: the switch stays on, the rewrite is tried again next time
                    log_swallowed("startup entry rewrite", _e)
            return True
        except FileNotFoundError:
            return False  # ok: no file: not found
        except Exception as _e:
            log_swallowed("startup entry check", _e)
            return False

    def toggle_startup(self):
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
            if self.startup_var.get():
                cmd = startup_entry.command(GUI_EXE)  # the GUI, hidden in the tray; it starts the Monitor
                winreg.SetValueEx(key, "TURMO", 0, winreg.REG_SZ, cmd)
                self.status_var.set(tr("Startup enabled"))
            else:
                winreg.DeleteValue(key, "TURMO")
                self.status_var.set(tr("Startup disabled"))
            winreg.CloseKey(key)
        except Exception as e:
            self.show_error(tr("Startup Error"), f"Failed to update startup: {e}")
            self.startup_var.set(not self.startup_var.get())

    # ─── CPU Temp Helper ───

    def _refresh_helper_status(self):
        """Check if the helper is running and update the status label."""
        import socket
        try:
            s = socket.create_connection(("127.0.0.1", 18234), timeout=0.5)
            s.sendall(b"GET\n")
            data = b""
            while b"\n" not in data:
                c = s.recv(4096)
                if not c:
                    break
                data += c
            s.close()
            import json as _json
            info = _json.loads(data.decode().strip())
            self.helper_status.set(f"{tr('Helper: running')}  ({info.get('cpu_name', 'CPU')}, "
                                  f"{tr('elevated')}={info.get('elevated', '?')})")
            self.helper_btn.config(text=tr("Disable CPU temperature"))
        except Exception:
            self.helper_status.set(tr("Helper: not running"))
            self.helper_btn.config(text=tr("Enable CPU temperature (one-time UAC)"))

    @staticmethod
    def _helper_admin_script(action, src, user):
        """PowerShell run elevated (one UAC prompt): install or remove the CPU temp
        helper under %ProgramFiles%\\TURMO. Passed via -EncodedCommand, so no
        user-writable script file is ever executed as admin."""
        def q(s):
            return s.replace("'", "''")
        return (
            "$ErrorActionPreference = 'Stop'\n"
            f"$action = '{q(action)}'; $src = '{q(src)}'; $user = '{q(user)}'\n"
            "$task = 'TURMO CpuTemp Helper'\n"
            "$dst = Join-Path $env:ProgramFiles 'TURMO\\CpuTempHelper'\n"
            "try {\n"
            "  if ($action -eq 'install') {\n"
            "    New-Item -ItemType Directory -Force -Path $dst | Out-Null\n"
            "    robocopy $src $dst /MIR /NJH /NJS /NFL /NDL | Out-Null\n"
            "    if ($LASTEXITCODE -ge 8) { throw \"robocopy failed: $LASTEXITCODE\" }\n"
            "    $exe = Join-Path $dst 'TURMO-CpuTempHelper.exe'\n"
            "    $xml = @\"\n"
            "<?xml version=\"1.0\" encoding=\"UTF-16\"?>\n"
            "<Task version=\"1.2\" xmlns=\"http://schemas.microsoft.com/windows/2004/02/mit/task\">\n"
            "  <RegistrationInfo><Description>TURMO CPU temperature helper (elevated, localhost read-only)</Description></RegistrationInfo>\n"
            "  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>$user</UserId></LogonTrigger></Triggers>\n"
            "  <Principals><Principal id=\"Author\"><UserId>$user</UserId><LogonType>InteractiveToken</LogonType><RunLevel>HighestAvailable</RunLevel></Principal></Principals>\n"
            "  <Settings>\n"
            "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
            "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
            "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
            "    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>\n"
            "    <RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure>\n"
            "    <StartWhenAvailable>true</StartWhenAvailable>\n"
            "    <Enabled>true</Enabled>\n"
            "    <Hidden>true</Hidden>\n"
            "  </Settings>\n"
            "  <Actions Context=\"Author\"><Exec><Command>$exe</Command><WorkingDirectory>$dst</WorkingDirectory></Exec></Actions>\n"
            "</Task>\n"
            "\"@\n"
            "    Register-ScheduledTask -TaskName $task -Xml $xml -Force | Out-Null\n"
            "    Start-ScheduledTask -TaskName $task\n"
            "  } else {\n"
            "    Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue\n"
            "    Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue\n"
            "    Get-Process -Name 'TURMO-CpuTempHelper' -ErrorAction SilentlyContinue | Stop-Process -Force\n"
            "    Remove-Item -Recurse -Force $dst -ErrorAction SilentlyContinue\n"
            "  }\n"
            "} catch {\n"
            "  $_ | Out-File (Join-Path $env:TEMP 'turmo_cpu_temp_admin.log')\n"
            "}\n"
        )

    def toggle_cpu_temp_helper(self):
        """Install or remove the elevated CPU temp helper. One UAC prompt per action;
        the helper itself then runs at logon without prompts."""
        import os
        import sys

        running = self.helper_status.get().startswith(tr("Helper: running"))
        if running:
            self.confirm(tr("CPU temperature"), tr("Remove the CPU temperature helper?\nWindows will ask for admin approval once."),
                         tr("Remove"),
                         lambda: self._helper_run("uninstall", ""))
            return
        app_dir = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                   else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        src = next((d for d in (os.path.join(app_dir, "TURMO-CpuTempHelper"),
                                os.path.join(app_dir, "dist", "TURMO-CpuTempHelper"))
                    if os.path.isfile(os.path.join(d, "TURMO-CpuTempHelper.exe"))), None)
        if src is None:
            self.show_error(tr("Helper not found"), tr("TURMO-CpuTempHelper folder not found next to the app."))
            return
        self._helper_run("install", src)

    def _helper_run(self, action, src):
        """Start the elevated install / uninstall of the CPU temperature helper (one UAC prompt)."""
        import base64
        import ctypes
        import os
        user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}"
        script = self._helper_admin_script(action, src, user)
        enc = base64.b64encode(script.encode("utf-16-le")).decode()
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe",
            f"-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -EncodedCommand {enc}",
            None, 0)
        if ret > 32:
            self.helper_status.set(tr("Helper: waiting for Windows approval..."))
            self.log_text.insert(tk.END, f"  CPU temp helper: {action} (elevated launch started; Windows asks for consent)\n")
            self.root.after(5000, self._refresh_helper_status)
        else:
            self.show_warning(tr("Helper not changed"),
                f"Admin approval was not given (code {ret}).")

    # ─── Monitor Control ───

    def start_monitor(self, reason="button"):
        if self.monitor_process and self.monitor_process.poll() is None:
            return
        try:
            live = self._other_monitor_pids()
        except Exception as e:
            self.show_error(tr("Start Error"), f"Could not check for a running Monitor: {e}")
            return
        if live:
            self.show_warning(tr("Monitor running"), f"A TURMO Monitor is still running (PID {live[0]}), not started by this window. Stop it first.")
            return

        port = self.port_override_var.get().strip() or find_turmo_port()  # no port: the Monitor waits for the display

        # Verify COM4 is free before starting
        import serial
        for attempt in range(5 if port else 0):
            try:
                test_ser = serial.Serial(port, 115200, timeout=0.5, write_timeout=1, rtscts=False)
                test_ser.close()
                self.log_text.insert(tk.END, f"  COM4 free for monitor (attempt {attempt+1})\n")
                break
            except serial.SerialException as e:
                if attempt < 4:
                    self.root.update()
                    time.sleep(0.3)
                else:
                    self.log_text.insert(tk.END, f"  WARNING: COM4 not free after 5 attempts: {e}\n")

        # Use bundled TURMO-Monitor.exe (headless worker) instead of external Python
        cmd = [str(TURMO_MONITOR_EXE), "--monitor"] + (["--port", port] if port else [])

        # Pass theme, orientation, gpu-index from current settings (resolve minimal alias)
        theme = self.theme_var.get()
        if theme == "minimal":
            theme = "minimal-dark"
        cmd.extend(["--theme", theme])
        if self.landscape_var.get():
            cmd.append("--landscape")
        else:
            cmd.append("--portrait")
        cmd.extend(["--gpu-index", str(self.gpu_index_var.get())])

        # ponytail: brief settle delay — USB COM port can still be closing on first
        # launch even after the free-check above. Restart path has an implicit 1s gap.
        time.sleep(0.5)

        try:
            # CREATE_NO_WINDOW prevents CMD/console window from appearing
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            # the worker's error messages go to a file, so the log can say why it stopped on its own
            self._monitor_err_path = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "TURMO" / "monitor_stderr.txt"
            self._monitor_err_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._monitor_err_path, "w", encoding="utf-8") as err_file:
                self.monitor_process = subprocess.Popen(
                    cmd,
                    creationflags=creation_flags,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,  # a GUI has no console: an unset std handle is invalid in the worker (OSError 22)
                    stderr=err_file,
                )
            self.monitor_status_var.set("Running")
            _log_event("MONITOR_START", reason)
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.status_var.set(tr("Monitor started"))
            self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Monitor started on {port}\n")
            self.log_text.see(tk.END)
            self.start_preview()
        except Exception as e:
            self.show_error(tr("Start Error"), tr("Failed to start the Monitor: {reason}").format(reason=tr(friendly_error(e))))

    def stop_monitor(self, reason="button"):
        """Stop the monitor worker and verify COM4 is released.

        Safe process management:
        1. Graceful: write stop_monitor.request — worker checks each tick,
           closes the serial handle itself, exits; bootloader follows.
        2. Fallback: taskkill /F /T on the EXACT Popen PID only (never /IM).
        """
        own_left = None
        if self.monitor_process:
            proc = self.monitor_process  # a refresh run by root.update() below may clear self.monitor_process
            pid = proc.pid
            self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Stopping monitor (PID={pid})...\n")
            self.log_text.see(tk.END)

            # Step 1: graceful shutdown via stop-request file
            try:
                import os
                stop_req = Path(os.environ.get("APPDATA", "")) / "TURMO" / "stop_monitor.request"
                stop_req.parent.mkdir(parents=True, exist_ok=True)
                stop_req.write_text(str(time.time()))
                self.log_text.insert(tk.END, f"  Graceful stop requested\n")
            except Exception as e:
                self.log_text.insert(tk.END, f"  stop-request write failed: {e}\n")

            # Step 2: poll for exit, pumping the Tk event loop so the UI stays responsive
            for _ in range(24):
                if proc.poll() is not None:
                    break
                self.root.update_idletasks()
                self.root.update()
                time.sleep(0.5)
            if proc.poll() is not None:
                self.log_text.insert(tk.END, f"  Worker exited gracefully\n")
            else:
                # Step 3: targeted forced termination — exact PID tree only
                self.log_text.insert(tk.END, f"  Graceful stop timed out; forcing PID={pid} tree\n")
                self._force_kill_pid(pid)
            try:
                proc.wait(timeout=5)
            except Exception as e:  # it did not exit in time: the check below decides what to report
                log_swallowed("wait for the monitor to exit", e)
            if proc.poll() is not None:  # hide the PID only once it has really exited
                self._ignored_pids.add(pid)
            else:
                own_left = pid  # still alive: the outside branch below tries again, and says whose it is
            self.monitor_process = None

        # A Monitor this window did not start: stop it only for the Stop button or a restart,
        # never on quit, so closing the GUI does not stop a Monitor the user started by hand.
        outside = self._outside_monitor_pids() if reason in ("button", "restart") else []
        if outside:
            import psutil
            mine = [p for p in outside if p == own_left]
            others = [p for p in outside if p != own_left]
            if mine:
                self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Monitor started by this window is still running (PID {mine[0]}): trying again...\n")
            if others:
                self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Stopping Monitor started outside this window (PID {', '.join(str(p) for p in others)})...\n")
            self.log_text.see(tk.END)
            self._ignored_pids.update(outside)
            try:
                self._write_stop_request()
                for _ in range(24):
                    if not any(psutil.pid_exists(p) for p in outside):
                        break
                    self.root.update_idletasks()
                    self.root.update()
                    time.sleep(0.5)
                for p in outside:
                    if psutil.pid_exists(p):
                        self.log_text.insert(tk.END, f"  Graceful stop timed out; forcing PID={p} tree\n")
                        self._force_kill_pid(p)
            finally:
                # Hidden during the wait so the refresh does not report it. An error above must not leave a live
                # Monitor hidden: only a PID confirmed gone stays ignored.
                gone = set()
                for p in outside:
                    try:
                        if not psutil.pid_exists(p):
                            gone.add(p)
                    except Exception as e:
                        log_swallowed("pid_exists after stopping a monitor", e)
                self._ignored_pids.difference_update(set(outside) - gone)

        # Verify COM4 is released by attempting to open it
        port = self.port_override_var.get().strip() or find_turmo_port()
        if port:
            import serial
            try:
                test_ser = serial.Serial(port, 115200, timeout=0.5, write_timeout=1, rtscts=False)
                test_ser.close()
                self.log_text.insert(tk.END, f"  COM4 verified released\n")
            except serial.SerialException as e:
                self.log_text.insert(tk.END, f"  WARNING: COM4 still busy: {e}\n")

        # Stop-request file: always removed (the Monitor has seen it, or was just force-stopped).
        # Lock file: kept while any Monitor is alive, because it is what keeps a second Monitor off COM4.
        try:
            import os
            turmo_dir = Path(os.environ.get("APPDATA", "")) / "TURMO"
            stop_req = turmo_dir / "stop_monitor.request"
            if stop_req.exists():
                stop_req.unlink()
                self.log_text.insert(tk.END, f"  {stop_req.name} removed\n")
            lock_path = turmo_dir / "monitor.lock"
            if self._other_monitor_pids():
                self.log_text.insert(tk.END, "  Monitor still running: lock kept\n")
            elif lock_path.exists():
                lock_path.unlink()
                self.log_text.insert(tk.END, f"  {lock_path.name} removed\n")
        except Exception as e:
            self.log_text.insert(tk.END, f"  lock cleanup skipped: {e}\n")

        self.monitor_status_var.set("Stopped")
        _log_event("MONITOR_STOP", reason)
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.stop_preview()
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Monitor stopped\n")
        self.log_text.see(tk.END)
        self.status_var.set(tr("Monitor stopped"))

    def _force_kill_pid(self, pid):
        """taskkill /F /T on one exact PID. A failure is written to the log and the runtime log, never raised."""
        try:
            res = subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], capture_output=True, timeout=10)
            if res.returncode == 0:
                return
            import psutil
            if res.returncode == 128 and not psutil.pid_exists(pid):  # "process not found": it exited on its own
                self.log_text.insert(tk.END, f"  PID {pid} had already exited\n")
                return
            detail =f"rc={res.returncode} {(res.stderr or b'').decode(errors='replace').strip()[:200]}"
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"
        self.log_text.insert(tk.END, f"  taskkill /PID {pid} failed: {detail}\n")
        self.log_text.see(tk.END)
        _log_event("MONITOR_KILL_FAILED", f"pid={pid} {detail}")

    def _write_stop_request(self):
        """Ask the running Monitor to stop: it reads %APPDATA%\\TURMO\\stop_monitor.request each tick."""
        try:
            import os
            stop_req = Path(os.environ.get("APPDATA", "")) / "TURMO" / "stop_monitor.request"
            stop_req.parent.mkdir(parents=True, exist_ok=True)
            stop_req.write_text(str(time.time()))
            self.log_text.insert(tk.END, "  Graceful stop requested\n")
        except Exception as e:
            self.log_text.insert(tk.END, f"  stop-request write failed: {e}\n")

    def _other_monitor_pids(self):
        """Every live TURMO Monitor PID except this window's own process. Unlike
        _outside_monitor_pids, a PID we just asked to stop still counts while it is alive:
        it still holds COM4. Raises if the process list cannot be read (callers fail closed)."""
        own = self.monitor_process.pid if self.monitor_process is not None else None
        return [p for p in _turmo_monitor_pids(_process_rows()) if p != own]

    def _outside_monitor_pids(self, pids=None):
        """TURMO Monitor PIDs this window did not start and has not just stopped."""
        if pids is None:
            try:
                pids = _turmo_monitor_pids(_process_rows())
            except Exception as _e:
                log_swallowed("outside monitor scan", _e)
                return []
        own = self.monitor_process.pid if self.monitor_process is not None else None
        return [p for p in pids if p != own and p not in self._ignored_pids]

    def _refresh_monitor_state(self):
        """The loop: scan, then again in 2 s (5 s while the window is hidden and the tray panel is closed)."""
        self._scan_monitor_state()
        quick = getattr(self, "quick_panel", None)
        slow = self._window_hidden() and not (quick is not None and quick.visible)
        self.root.after(5000 if slow else 2000, self._refresh_monitor_state)

    def _on_window_shown(self, event=None):
        """The window came back from the tray or the taskbar: bring the Start / Stop state up to date at once."""
        if event is None or event.widget is self.root:
            self.root.after_idle(self._scan_monitor_state)

    def _scan_monitor_state(self):
        """Show a Monitor started outside this window, or by hand, so the status
        and the Start / Stop buttons never say 'Stopped' while one is running."""
        try:
            pids = _turmo_monitor_pids(_process_rows())
        except Exception as _e:
            log_swallowed("monitor state process list", _e)
            pids = []
        self._ignored_pids &= set(pids)  # a PID we stopped is forgotten once it has really exited
        if self.monitor_process is not None and self.monitor_process.poll() is not None:
            self._report_monitor_exit()
        own = self.monitor_process is not None and self.monitor_process.poll() is None
        outside = self._outside_monitor_pids(pids)
        running = own or bool(outside)
        shown = self.monitor_status_var.get()
        if running and not shown.startswith("Running"):
            label = "Running" if own else f"Running (started outside this window, PID {outside[0]})"
            self.monitor_status_var.set(label)
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
        elif not running and shown.startswith("Running"):
            self.monitor_status_var.set("Stopped")
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)


    def _report_monitor_exit(self):
        """The worker ended without the Stop button: write that, with its exit code and its last error lines, in
        the Monitor log (it used to go from Running to Stopped with nothing said)."""
        code = self.monitor_process.returncode
        self._ignored_pids.add(self.monitor_process.pid)
        self.monitor_process = None
        try:
            lines = [l.strip() for l in self._monitor_err_path.read_text(encoding="utf-8", errors="replace").splitlines()
                     if l.strip()][-4:]
        except OSError:
            lines = []  # ok: no log file yet
        stamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{stamp}] Monitor stopped by itself (exit code {code})\n")
        for line in lines or ["No error message from the worker."]:
            self.log_text.insert(tk.END, f"  {line}\n")
        self.log_text.see(tk.END)
        self.status_var.set(tr("Monitor stopped by itself, see the Monitor log"))
        self.toast(tr("The Monitor stopped by itself. The Monitor log says why."), "error")
        _log_event("MONITOR_EXIT", f"code={code} {' | '.join(lines)}")

    def _cleanup_stale_workers(self):
        """On startup, never stop a Monitor. A Monitor still running, even one left by an
        earlier GUI, keeps running and shows as started outside this window. Only a lock whose
        PID is gone is cleared, and the stop-request file is always removed."""
        try:
            import os
            import psutil
            turmo_dir = Path(os.environ.get("APPDATA", "")) / "TURMO"
            lock_path = turmo_dir / "monitor.lock"
            stop_req = turmo_dir / "stop_monitor.request"
            if stop_req.exists():
                stop_req.unlink()
                log_startup(self._startup_log, "CLEANUP", "Removed stale stop_monitor.request")
            if lock_path.exists():
                try:
                    pid = int(lock_path.read_text().strip() or "0")
                except ValueError:
                    pid = 0  # ok: not a number: treated as no pid
                if pid and psutil.pid_exists(pid):
                    log_startup(self._startup_log, "CLEANUP", f"Monitor PID={pid} still running: lock kept, not stopped")
                else:
                    lock_path.unlink()
                    log_startup(self._startup_log, "CLEANUP", "Removed monitor.lock of a Monitor that is gone")
        except Exception as e:
            log_startup(self._startup_log, "CLEANUP", f"Startup cleanup error: {e}", e)

    def restart_monitor(self):
        """Restart monitor: stop gracefully, verify COM4 released, then start."""
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Restarting monitor...\n")
        self.log_text.see(tk.END)
        self.stop_monitor(reason="restart")
        # Wait for COM4 to be fully released
        self.root.after(1000, self._restart_monitor_start)

    def _restart_monitor_start(self):
        """Continue restart: verify COM4 is free, then start monitor."""
        # Verify COM4 is free before starting
        port = self.port_override_var.get().strip() or find_turmo_port()
        if port:
            import serial
            for attempt in range(5):
                try:
                    test_ser = serial.Serial(port, 115200, timeout=0.5, write_timeout=1, rtscts=False)
                    test_ser.close()
                    self.log_text.insert(tk.END, f"  COM4 free after {attempt+1} attempt(s)\n")
                    break
                except serial.SerialException:
                    if attempt < 4:
                        self.root.update()
                        time.sleep(0.5)
                    else:
                        self.log_text.insert(tk.END, f"  WARNING: COM4 not free after 5 attempts\n")
        self.start_monitor(reason="restart")

    def send_test_image(self):
        port = find_turmo_port()
        if not port:
            self.show_error(tr("No Port"), tr("TURMO device not found"))
            return

        # Stop monitor first to release COM4 lock for test image
        was_running = False
        if self.monitor_process and self.monitor_process.poll() is None:
            was_running = True
            self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Stopping monitor for test image...\n")
            self.log_text.see(tk.END)
            self.stop_monitor(reason="test image")

        try:
            live = self._other_monitor_pids()
        except Exception as e:
            self.show_error(tr("Test Image"), f"Could not check for a running Monitor: {e}")
            return
        if live:
            self.show_warning(tr("Monitor running"), tr("A TURMO Monitor is still running (PID {pid}) and holds COM4. Stop it first.").format(pid=live[0]))
            return

        # Verify COM4 is free before sending test image
        import serial
        for attempt in range(10):
            try:
                test_ser = serial.Serial(port, 115200, timeout=0.5, write_timeout=1, rtscts=False)
                test_ser.close()
                self.log_text.insert(tk.END, f"  COM4 free for test image (attempt {attempt+1})\n")
                break
            except serial.SerialException as e:
                if attempt < 9:
                    self.root.update()
                    time.sleep(0.3)
                else:
                    self.log_text.insert(tk.END, f"  WARNING: COM4 not free after 10 attempts: {e}\n")

        # Use bundled TURMO-Monitor.exe for test image
        cmd = [str(TURMO_MONITOR_EXE), "--test-image", "--port", port]
        if self.landscape_var.get():
            cmd.append("--landscape")

        try:
            # CREATE_NO_WINDOW prevents CMD/console window from appearing
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20, creationflags=creation_flags)
            if result.returncode == 0:
                self.status_var.set(tr("Test image sent"))
                self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Test image sent\n")
            else:
                errmsg = result.stderr.strip() if result.stderr else ""
                if "already running" in errmsg.lower():
                    self.show_warning(tr("Monitor Active"), 
                        "Another TURMO monitor is active. Cannot send test image while monitor is running.")
                elif "could not open" in errmsg.lower() or "permission" in errmsg.lower():
                    self.show_error(tr("COM Port Error"), 
                        f"Could not open {port}: {errmsg} -- Make sure no other app is using COM4.")
                else:
                    self.show_error(tr("Test Failed"), f"{result.returncode}: {errmsg or result.stdout}")
                    self.log_text.insert(tk.END, f"  Test image failed: {errmsg or result.stdout}\n")
        except subprocess.TimeoutExpired:
            self.show_error(tr("Test Timeout"), tr("Test image command timed out"))
            self.log_text.insert(tk.END, f"  Test image timeout\n")
        except Exception as e:
            self.show_error(tr("Test Error"), f"Failed to send test image: {e}")
            self.log_text.insert(tk.END, f"  Test image error: {e}\n")
        finally:
            # Restart monitor if it was running
            if was_running:
                self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Restarting monitor after test image...\n")
                self.root.after(500, self.start_monitor)
        self.log_text.see(tk.END)

    # ─── Live Preview ───

    # ─── Graph Configuration ───

    # ─── System Tray ───

    def start_tray(self):
        def create_image():
            try:
                return Image.open(asset_path("turmo_icon.png")).convert("RGBA").resize((32, 32), Image.LANCZOS)
            except Exception as e:  # the drawn icon below is the fallback
                log_swallowed("tray icon file", e)
            img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([8, 8, 56, 56], fill=(255, 43, 214))
            draw.rectangle([20, 28, 44, 36], fill=(255, 255, 255))
            return img

        def on_quit(icon, item):
            self.root.after(0, lambda: self._quit_from_tray(icon))

        def on_show(icon, item):
            self.root.after(0, self.show_main_window)

        def on_click(icon, item):  # the tray icon's left click (a double click arrives as two)
            self.root.after(0, self._tray_click)

        def on_start(icon, item):
            self.root.after(0, self.start_monitor)

        def on_stop(icon, item):
            self.root.after(0, self.stop_monitor)

        menu = pystray.Menu(
            pystray.MenuItem("Show", on_click, default=True, visible=False),  # the click, not a menu line
            pystray.MenuItem("Open TURMO", on_show),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start Monitor", on_start),
            pystray.MenuItem("Stop Monitor", on_stop),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit)
        )

        self.tray_icon = pystray.Icon("TURMO", create_image(), "TURMO Display", menu)
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()

    def show_main_window(self):
        """The full window (Default or Minimalist look), in front."""
        self.quick_panel.close()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _tray_click(self):
        """One click: the quick panel (or the full window when the panel is off). Two clicks within 350 ms:
        the full window. The panel waits those 350 ms so a double click never flashes it."""
        pending = getattr(self, "_tray_pending", None)
        if pending is not None:
            self.root.after_cancel(pending)
            self._tray_pending = None
            self.show_main_window()
            return
        if not self.settings.quick_panel:
            self.show_main_window()
            return

        def single():
            self._tray_pending = None
            self.quick_panel.toggle()
        self._tray_pending = self.root.after(350, single)

    def log_panel_error(self, error):
        log_startup(self._startup_log, "QUICKPANEL", f"refresh failed: {error}")

    def on_close(self):
        """Hide to tray instead of closing."""
        _log_event("GUI_HIDE", "close button")
        self.root.withdraw()

    def _quit_from_tray(self, icon):
        """Tray Quit: log it, stop only this window's own Monitor (never one started outside), then leave."""
        _log_event("GUI_QUIT", "tray quit")
        self.stop_monitor(reason="tray quit")
        icon.stop()
        self.root.after(0, self.root.quit)

    def quit_app(self):
        """Actually quit the application."""
        _log_event("GUI_QUIT", "quit")
        self.stop_monitor(reason="quit")
        if self.tray_icon:
            self.tray_icon.stop()
        # Release mutex
        if self._mutex:
            try:
                win32api.CloseHandle(self._mutex)
            except Exception as e:
                log_swallowed("close the single-instance mutex", e)
        self.root.quit()
        self.root.destroy()

    def export_settings(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="turmo_settings.json"
        )
        if filepath:
            import shutil
            try:
                shutil.copy2(self.settings.path(), filepath)
            except OSError as e:
                log_exception("APP", "EXPORT_SETTINGS", e)
                self.show_error(tr("Could not export the settings"), tr(friendly_error(e)))
                return
            self.show_info(tr("Exported"), f"Settings exported to {filepath}")

    def import_settings(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filepath:
            import shutil
            try:
                Settings.check_file(filepath)
                keep = self.settings.path().with_name("settings.json.bak")
                if self.settings.path().exists():
                    shutil.copy2(self.settings.path(), keep)
                swap = self.settings.path().with_name("settings.json.new")
                shutil.copy2(filepath, swap)
                os.replace(swap, self.settings.path())  # whole file or nothing
            except (OSError, ValueError) as e:
                log_exception("APP", "IMPORT_SETTINGS", e)
                self.show_error(tr("Could not import the settings"), tr(friendly_error(e)))
                return
            self.settings = Settings.load()
            set_logging_enabled(self.settings.logging_enabled)
            # Reload UI
            self.theme_var.set(self.settings.theme)
            self.landscape_var.set(self.settings.orientation == "landscape")
            self.refresh_var.set(self.settings.refresh_ms)
            self.gpu_index_var.set(self.settings.gpu_index)
            self.brightness_var.set(self.settings.brightness)
            self.color_correction_var.set(bool(self.settings.color_correction))
            for key, value in zip("rgb", gain_values(self.settings.color_gain)):
                self.color_gain_vars[key].set(value)
            self.temp_unit_var.set(self.settings.units.get("temp", "celsius"))
            self.clock_unit_var.set(self.settings.units.get("clock", "24h"))
            self.data_unit_var.set(self.settings.units.get("data", "auto"))
            for w, var in self.widget_vars.items():
                var.set(self.settings.widgets.get(w, True))
            self.font_scale_var.set(self.settings.font_scale)
            self.compact_var.set(self.settings.compact)
            self.port_override_var.set(self.settings.port)
            self.startup_var.set(self.is_startup_enabled())
            self.show_info(tr("Imported"), f"Settings imported from {filepath}\nRestart app to apply fully.")


def main():
    # Initialize startup logging
    startup_log = init_startup_log()
    log_startup(startup_log, "MAIN_ENTRY", "main() called")
    if RUNTIME_LOGGING_ERROR:
        log_startup(startup_log, "RUNTIME_LOGGING", f"runtime logging unavailable: {RUNTIME_LOGGING_ERROR}")

    # Initialize runtime logging
    if RUNTIME_LOGGING_AVAILABLE:
        init_runtime_log()
        install_thread_excepthook()
        log_runtime("APP", "MAIN_ENTRY", "Runtime logging initialized in main()")

    try:  # v0.2.3: user themes moved from the %LOCALAPPDATA% mirror to %APPDATA%\TURMO\themes\custom
        theme_paths.migrate_old_mirror(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "TURMO" / "themes")
    except OSError as e:
        log_swallowed("theme folder migration", e)
    log_startup(startup_log, "DATA_DIRS", theme_paths.user_data_report(DATA_ROOT / "themes"))

    # ponytail: pre-initialize CLR for pythonnet on main thread before any threads spawn
    # Required: pythonnet.load("netfx") has thread-affinity requirements for LibreHardwareMonitor
    _preinit_libre_hardware_monitor()

    # Windows DPI awareness (before Tk init for best results); with the loading screen, splash.start() did it
    # before its own Tk window (it is per process).
    from ctypes import windll
    if SPLASH is None:
        try:
            windll.shcore.SetProcessDpiAwareness(1)
            log_startup(startup_log, "DPI", "SetProcessDpiAwareness(1) succeeded")
        except Exception as e:
            log_startup(startup_log, "DPI", f"SetProcessDpiAwareness failed: {e}", e)
            pass

    try:  # without its own id the taskbar shows Tk's feather instead of the window icon
        windll.shell32.SetCurrentProcessExplicitAppUserModelID("TURMO.DisplayControl")
    except Exception as e:
        log_startup(startup_log, "AUMID", f"AppUserModelID not set: {e}", e)

    root = tk.Tk()
    log_startup(startup_log, "TK_ROOT", "tk.Tk() created")
    if SPLASH is not None:
        import psutil
        since = lambda t: int((t - psutil.Process().create_time()) * 1000)
        log_startup(startup_log, "SPLASH", f"loading screen shown {since(SPLASH.shown_wall)} ms after process start")

    log_startup(startup_log, "APP_CREATE", "Creating TurmoApp instance")
    app = TurmoApp(root)
    root.update()  # every widget is drawn while the window is still hidden
    if SPLASH is not None:
        SPLASH.finish()  # the bar fills, the splash thread removes its window
        log_startup(startup_log, "SPLASH", f"UI ready {since(time.time())} ms after process start")
        n, span, fps, gap = SPLASH.stats()
        log_startup(startup_log, "SPLASH", f"loading screen redrew {n} times in {span:.2f} s: {fps:.0f} per second, longest gap {gap:.0f} ms")
        stalls = SPLASH.stalls()
        if stalls:
            log_startup(startup_log, "SPLASH", "gaps over 50 ms (seconds after the first redraw, ms): " + ", ".join(f"{t} s {g} ms" for t, g in stalls))
    if STARTUP:
        root.withdraw()  # in the tray, no window; alpha back to 1 so "Open TURMO" shows it normally
        root.attributes("-alpha", 1.0)
        root.after(1500, lambda: app.start_monitor(reason="startup"))
    else:
        app.show_window()  # after the loading screen is gone
    log_startup(startup_log, "MAINLOOP", "Entering root.mainloop()")
    app.start_log_sweeper()
    if not STARTUP:
        root.after(800, app.start_first_run)
    root.mainloop()
    log_startup(startup_log, "MAINLOOP_EXIT", "root.mainloop() exited")


if __name__ == "__main__":
    main()