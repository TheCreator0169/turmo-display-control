"""Shared start-up environment of the GUI (v0.2.3): imports, runtime logging with its fallbacks, the start-up log,
the single-instance mutex shim, source or frozen paths (DATA_ROOT, ...), the design tokens and widgets.
It used to be the top of turmo_app_enhanced.py; the app and the page modules star-import it, so every name keeps
working. Importing it has the same effects as before (sys.path, PyInstaller paths, user themes restored)."""

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

try:
    from scripts.runtime_logging import (
        init_runtime_log, log_runtime, log_exception, log_callback,
        log_worker_start, log_worker_result, log_com_error, get_runtime_log_path,
        install_thread_excepthook, safe_callback, run_worker, popen_worker, set_enabled as set_logging_enabled,
        is_enabled as logging_enabled,
        KEEP_DAYS_CHOICES, MAX_MB_CHOICES, log_dir, log_folder_stats, rotate_startup_log, sweep_logs, valid_choice
    )
    RUNTIME_LOGGING_AVAILABLE = True
    RUNTIME_LOGGING_ERROR = ""
except ImportError as e:
    RUNTIME_LOGGING_AVAILABLE = False
    RUNTIME_LOGGING_ERROR = str(e)  # written to the startup log by main()
    # Fallback stubs
    def init_runtime_log() -> Optional[Path]: return None
    def log_runtime(*args, **kwargs): pass
    def set_logging_enabled(on): pass
    def logging_enabled(): return True
    def log_exception(*args, **kwargs): pass
    def log_callback(*args, **kwargs): pass
    def log_worker_start(*args, **kwargs): pass
    def log_worker_result(*args, **kwargs): pass
    def log_com_error(*args, **kwargs): pass
    def get_runtime_log_path() -> Optional[Path]: return None
    def install_thread_excepthook(): pass
    def safe_callback(cb, *a, **k): return cb
    def run_worker(cmd, *a, **k): return subprocess.run(cmd, capture_output=True, text=True, *a, **k)
    def popen_worker(cmd, *a, **k): return subprocess.Popen(cmd, *a, **k)
    KEEP_DAYS_CHOICES, MAX_MB_CHOICES = (1, 3, 7, 14, 30), (10, 20, 50, 100)
    def log_dir() -> Path: return Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))) / "TURMO" / "logs"
    def log_folder_stats(*a, **k): return (0, 0)
    def rotate_startup_log(*a, **k): pass
    def sweep_logs(*a, **k): return (0, 0)
    def valid_choice(value, choices, default): return default

try:
    import pystray
    from PIL import Image, ImageDraw, ImageTk, ImageFont
except ImportError:
    sys.exit("pystray or Pillow not installed: pip install pystray Pillow")

# ─── Persistent Startup Diagnostics ───
def init_startup_log() -> Path:
    """Initialize persistent startup log under %LOCALAPPDATA%\\TURMO\\logs\\"""
    if sys.platform == "win32":
        localappdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    else:
        localappdata = os.path.expanduser("~/.local/share")
    log_dir = Path(localappdata) / "TURMO" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "startup.log"  # one file, renamed startup.1.log and startup.2.log when it passes 1 MB
    rotate_startup_log(log_file)
    return log_file

def log_startup(log_file: Path, stage: str, message: str, exc: Exception = None):
    """Write a startup diagnostic entry with timestamp, PID, session info."""
    if not logging_enabled():
        return
    try:
        pid = os.getpid()
        session_id = os.environ.get("SESSIONNAME", "unknown")
        username = os.environ.get("USERNAME", os.environ.get("USER", "unknown"))
        exe_path = sys.executable
        frozen = getattr(sys, 'frozen', False)
        meipass = getattr(sys, '_MEIPASS', 'N/A')

        lines = [
            f"[{datetime.now().isoformat()}] [{stage}] PID={pid} Session={session_id} User={username}",
            f"  Executable: {exe_path}",
            f"  Frozen: {frozen} | _MEIPASS: {meipass}",
            f"  Python: {sys.version.split()[0]}",
            f"  {message}",
        ]
        if exc:
            lines.append(f"  EXCEPTION: {exc}")
            lines.append(f"  TRACEBACK: {''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))}")

        with open(log_file, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
    except Exception:
        pass  # ok: never let logging failures crash the app

# Single-instance mutex for Windows (created after Tk init to work with PyInstaller --windowed)
if sys.platform == "win32":
    try:
        import win32event
        import win32api
        import winerror
    except ImportError:
        win32event = win32api = winerror = None
        # ponytail: ctypes fallback when pywin32 is unavailable
        import ctypes
        import ctypes.wintypes
        _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _kernel32 = _k32
        _kernel32.CreateMutexW.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
        _kernel32.CreateMutexW.restype = ctypes.wintypes.HANDLE
        _kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        _kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
        _kernel32.OpenMutexW.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
        _kernel32.OpenMutexW.restype = ctypes.wintypes.HANDLE
        _kernel32.WaitForSingleObject.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD]
        _kernel32.WaitForSingleObject.restype = ctypes.wintypes.DWORD
        _kernel32.ReleaseMutex.argtypes = [ctypes.wintypes.HANDLE]
        _kernel32.ReleaseMutex.restype = ctypes.wintypes.BOOL
        _kernel32.GetLastError.restype = ctypes.wintypes.DWORD
        _MUTEX_ALL_ACCESS = 0x1F0001
        _WAIT_OBJECT_0 = 0
        _ERROR_ALREADY_EXISTS = 183
        # Wrap in a simple namespace for the code below
        class _Win32Fallback:
            WAIT_OBJECT_0 = _WAIT_OBJECT_0
            ERROR_ALREADY_EXISTS = _ERROR_ALREADY_EXISTS
            @staticmethod
            def CreateMutex(_, initial, name):
                return _kernel32.CreateMutexW(None, initial, name)
            @staticmethod
            def CloseHandle(h):
                return _kernel32.CloseHandle(h)
            @staticmethod
            def OpenMutex(access, inherit, name):
                return _kernel32.OpenMutexW(access, inherit, name)
            @staticmethod
            def WaitForSingleObject(h, ms):
                return _kernel32.WaitForSingleObject(h, ms)
            @staticmethod
            def ReleaseMutex(h):
                return _kernel32.ReleaseMutex(h)
            @staticmethod
            def GetLastError():
                return ctypes.get_last_error()
        win32event = _Win32Fallback()
        win32api = _Win32Fallback()
        winerror = _Win32Fallback

# Add project root to path (source mode)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from collections import deque  # noqa: E402
from scripts.gui_design import (  # noqa: E402
    GALLERY_CATEGORIES, ICON_FONT, NO_VALUE, PALETTE, QUICK_THEMES, SEMIBOLD_FONTS, set_mode,
    LOCKED_GRAPHS, RATE, SENSOR_FORMATS, format_rate, SENSOR_NAMES, sensor_format, sensor_name, SIDEBAR_GLYPHS, SIDEBAR_GROUPS, SIDEBAR_ITEMS, FULL_SIZE, window_size,
    SIDEBAR_W, TEXT_FONTS, LINK_LABELS, device_chip_text, device_status, filter_themes, metric_text, pick_family, scale_history, sparkline_points, temp_in,
    collapse_description, is_custom_theme, pick_topmost, is_editable_theme, log_kind, move_theme, order_themes, mix, parse_log, recent_errors, unique_theme_name,
)
from scripts import i18n  # noqa: E402,F401
from scripts.i18n import tr  # noqa: E402,F401  (the texts the window draws, see i18n.py)
from scripts.modal import Modal, form_entry, form_label, form_spin  # noqa: E402
from scripts.minimal_ui import MinimalView, MIN_SIZE as MINIMAL_MIN, SIZE as MINIMAL_SIZE  # noqa: E402
from scripts.quick_panel import QuickPanel, work_area  # noqa: E402
from scripts.gui_widgets import (  # noqa: E402,F401
    Badge, ChoiceTile, ControlButton, DeviceChip, fit_cards, IconTile, LayerRow, Stepper, NavItem, RoundedButton, RoundedCard, ThemeChip, WidgetTile, draw_spark,
    ScrollFrame, Segmented, Select, Slider, StatRow, Switch, Tip, make_button, page_header, round_rect, rounded_entry,
)

# Dashboard metric cards: (value key, title, format, colour, icon glyph, history key, history top or None).
# A top of None scales the sparkline by the history's own maximum.
DASHBOARD_METRICS = (
    ("cpu.load", "CPU LOAD", "{value:.0f}%", PALETTE["cyan"], "\uE950", "cpu.load", 100),
    ("cpu.temp", "CPU TEMP", "{value:.0f}\u00b0C", PALETTE["warn"], "\uE950", "cpu.temp", 100),
    ("gpu.load", "GPU LOAD", "{value:.0f}%", PALETTE["blue"], "\uE7F4", "gpu.load", 100),
    ("mem.used", "RAM USED", "{value:.1f} GB", PALETTE["violet"], "\uE964", "mem.load", 100),
)
DASHBOARD_METRICS_2 = (
    ("gpu.vram_used", "VRAM", "{value:.1f} GB", PALETTE["cyan"], "\uE7F4", "gpu.vram_used", None),
    ("net.mbs", "NET \u2193", RATE, PALETTE["green"], "\uE774", "net.mbs", None),
    ("disk.load", "DISK", "{value:.0f}%", PALETTE["warn"], "\uEDA2", "disk.load", 100),
    ("gpu.temp", "GPU TEMP", "{value:.0f}\u00b0C", PALETTE["crit"], "\uE7F4", "gpu.temp", 100),
)


def asset_path(name: str) -> Path:
    """A file in assets/: next to the project in source runs, inside the bundle when frozen."""
    return DATA_ROOT / "assets" / name

# PyInstaller support: detect frozen exe and set correct paths
if getattr(sys, 'frozen', False):
    # Running as PyInstaller bundle
    BUNDLE_DIR = Path(sys._MEIPASS)
    EXE_DIR = Path(sys.executable).parent  # Actual EXE installation directory

    # Onedir builds have an _internal/ subdirectory with all data files
    # Onefile builds extract to a temp dir where _MEIPASS is the temp dir itself
    INTERNAL_DIR = BUNDLE_DIR / "_internal"
    if INTERNAL_DIR.is_dir():
        DATA_ROOT = INTERNAL_DIR
    else:
        DATA_ROOT = BUNDLE_DIR

    # Use bundled monitor worker executable (headless, console) - it's alongside the main exe
    # For onedir: in _internal/  For onefile: alongside main exe in installation dir
    TURMO_MONITOR_EXE = EXE_DIR / "TURMO-Monitor.exe"
    TURMO_RUNTIME_SCRIPT = DATA_ROOT / "scripts" / "turmo_runtime.py"

    # Add bundle dir to sys.path so imports like "libre_panel", "scripts" work
    sys.path.insert(0, str(DATA_ROOT))
    sys.path.insert(0, str(BUNDLE_DIR))

    try:
        from scripts.turmo_runtime import find_turmo_port, scan_all_ports, load_theme, LANDSCAPE_SIZE, TURING_SIZE, _preinit_libre_hardware_monitor
    except ImportError:
        # Fallback: define minimal port detection functions
        import serial.tools.list_ports as list_ports
        VID = 0x1A86
        PID = 0x5722
        def find_turmo_port() -> str | None:
            for info in list_ports.comports():
                if info.vid == VID and info.pid == PID:
                    return info.device
            return None
        def scan_all_ports() -> list[dict]:
            out = []
            for info in list_ports.comports():
                out.append({
                    "device": info.device,
                    "description": info.description,
                    "hwid": info.hwid,
                    "vid": f"0x{info.vid:04X}" if info.vid else None,
                    "pid": f"0x{info.pid:04X}" if info.pid else None,
                    "serial": info.serial_number,
                })
            return out
        def load_theme(name):
            return None
        LANDSCAPE_SIZE = (480, 320)
        TURING_SIZE = (320, 480)
        def _preinit_libre_hardware_monitor():
            # ponytail: onefile build, sys.platform may not be win32 in WSL build env
            # In frozen EXE on Windows, CLR init happens automatically via LHM vendor DLLs
            pass
else:
    # Running from source
    BUNDLE_DIR = PROJECT_ROOT
    DATA_ROOT = PROJECT_ROOT
    TURMO_MONITOR_EXE = PROJECT_ROOT / "dist" / "TURMO-Monitor.exe"
    TURMO_RUNTIME_SCRIPT = PROJECT_ROOT / "scripts" / "turmo_runtime.py"
    from scripts.turmo_runtime import find_turmo_port, scan_all_ports, load_theme, LANDSCAPE_SIZE, TURING_SIZE, _preinit_libre_hardware_monitor

from scripts.settings import (GAIN_RANGE, Settings, dim_image, gain_values, keeps_celsius, read_link_status, read_serial_stats,
                              temps_in_unit)
from scripts import theme_paths
from scripts.errors import friendly_error  # noqa: E402,F401
from scripts.editor_render import Shot


def _log_event(event, reason=""):
    """One line per GUI event in the runtime log, with the reason (button, restart,
    startup, tray quit...), so an unexpected start or stop can be traced later."""
    if RUNTIME_LOGGING_AVAILABLE:
        try:
            log_runtime("GUI", event, f"reason={reason} pid={os.getpid()}")
        except Exception:
            pass  # ok: the logger itself failed


_swallowed_seen = set()


def log_swallowed(where, exc):
    """A failure the code chooses to survive: one runtime-log line per place and error type, so it is never silent
    (the frozen ImageEnhance bug hid in a bare `except: pass`)."""
    key = (where, type(exc).__name__)
    if key in _swallowed_seen:
        return
    _swallowed_seen.add(key)
    if RUNTIME_LOGGING_AVAILABLE:
        try:
            log_runtime("GUI", "SWALLOWED", f"{where}: {type(exc).__name__}: {exc}")
        except Exception:
            pass  # ok: the logger itself failed


def _log_missing_text(language, text):
    """i18n calls this once for each text the language does not translate: the window shows it in English."""
    if RUNTIME_LOGGING_AVAILABLE:
        try:
            log_runtime("GUI", "I18N_MISSING", f"{language}: no translation for {text!r}, English shown")
        except Exception:
            pass  # ok: the logger itself failed


__all__ = [n for n in list(globals()) if not n.startswith("__")]
