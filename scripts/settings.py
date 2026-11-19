#!/usr/bin/env python3
"""Local, persistent settings for the TURMO runtime.

A single JSON file under the user's config dir holds every preference:
themes, orientation, refresh rate, brightness, visible widgets, units,
clock format, font scale and Windows-startup.  Nothing leaves the machine.

Run: python -c "from scripts.settings import Settings; s = Settings.load(); print(s.theme)"
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path


# ponytail: one file, one dataclass, stdlib only — a config lib would add a
# dependency for what a dict and json.dumps already do.
def _config_dir() -> Path:
    """Per-user config dir: %APPDATA%/TURMO on Windows, ~/.config/turmo elsewhere.
    Portable mode: if TURMO_PORTABLE=1 or portable.flag exists next to exe, use exe dir."""
    # Check for portable mode via environment or flag file
    if os.environ.get("TURMO_PORTABLE") == "1":
        # Try to find the executable directory (when launched from .bat)
        exe_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path.cwd()
        if (exe_dir / "portable.flag").exists() or (exe_dir / "TURMO-Display-Control.exe").exists():
            return exe_dir
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "TURMO"
    return Path.home() / ".config" / "turmo"


@dataclass
class Settings:
    theme: str = "cyberpunk-neon"
    orientation: str = "landscape"          # "landscape" | "portrait"
    refresh_ms: int = 500                   # 250 | 500 | 1000 | 2000
    brightness: int = 100                   # 0..100 (hardware permitting)
    widgets: dict = field(default_factory=lambda: {
        "clock": True, "cpu": True, "gpu": True, "ram": True,
        "net": True, "disk": True, "graph": True,
    })
    units: dict = field(default_factory=lambda: {
        "temp": "celsius",                  # celsius | fahrenheit
        "clock": "24h",                     # 24h | 12h
        "data": "auto",                     # auto | manual
    })
    font_scale: float = 1.0                 # 0.8 .. 1.4
    compact: bool = False
    quick_panel: bool = True                # a click on the tray icon opens the small panel
    language: str = "en"                    # en | fr | pt (English is the source; see i18n.py)
    app_mode: str = "dark"                  # dark | light: the window's colours (not the LCD's)
    app_theme: str = "default"             # look of this window (only "default" is drawn today)
    startup_windows: bool = False
    port: str = ""                          # empty = auto-detect
    theme_order: list = field(default_factory=list)  # gallery order chosen by the user (theme names)
    gpu_index: int = 0                      # which NVIDIA GPU to monitor (0 = first)
    color_correction: bool = True           # LCD only: evens out the panel's blue-heavy grey curve (see correct_panel)
    color_gain: dict = field(default_factory=lambda: {"r": 100, "g": 100, "b": 100})  # LCD white balance, % per colour
    log_keep_days: int = 7                  # old log files are removed after this many days (see runtime_logging.sweep_logs)
    log_max_mb: int = 20                    # and the oldest go first when the logs folder is bigger than this

    # -- persistence --------------------------------------------------------
    @classmethod
    def path(cls) -> Path:
        return _config_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        p = cls.path()
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        p = self.path()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["font_scale"] = round(float(data["font_scale"]), 2)  # 1.01, not 1.0139784946236559
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(p, 0o600)  # owner read/write only
        except OSError:
            pass

    # -- helpers ------------------------------------------------------------
    def refresh_seconds(self) -> float:
        return max(0.1, self.refresh_ms / 1000.0)

    def visible(self, widget: str) -> bool:
        return bool(self.widgets.get(widget, True))


def temps_in_unit(readings, history, unit):
    """What the LCD draws (v0.2.6.3): the temperature readings (keys ending ".temp", read in Celsius) and their
    histories in the unit of Settings > Units. A reading becomes "°F"; a theme that writes {unit} follows, one that
    writes a bare "°" shows the number. Celsius (or anything else) returns both unchanged. New dicts, never edited
    in place: the caller keeps its Celsius history."""
    if unit != "fahrenheit":
        return readings, history
    from dataclasses import replace
    out, hist = dict(readings), dict(history)
    for key, reading in readings.items():
        value = getattr(reading, "value", None)
        if key.endswith(".temp") and isinstance(value, (int, float)) and reading.unit in ("°C", ""):
            out[key] = replace(reading, value=value * 9 / 5 + 32, unit="°F")
    for key, values in history.items():
        if key.endswith(".temp"):
            hist[key] = [v * 9 / 5 + 32 for v in values]
    return out, hist


CELSIUS_MODULES = ("temps", "ring", "stat")  # libre_panel modules that write "°C" with 20..100 bars and heat rules at 75 and 88


def keeps_celsius(theme_folder):
    """True when the theme at `theme_folder` uses a module whose format, range and heat rules are fixed in Celsius
    (the hardware-dashboard "temps" module): Fahrenheit would read "140°C" on a full red bar, so the LCD keeps
    Celsius for it. A theme that cannot be read returns False."""
    try:
        theme = json.loads((Path(theme_folder) / "theme.json").read_text(encoding="utf-8"))
        return any(w.get("type") == "module" and w.get("module") in CELSIUS_MODULES for w in theme.get("widgets", []))
    except (OSError, ValueError, AttributeError):  # ok: no file or a broken one: the renderer reports that itself
        return False


def dim_image(image, percent):
    """The frame at `percent` brightness (0..100). The display has no known brightness command, so the
    pixels are scaled before they are sent. 100 or more, or a bad value, returns the image unchanged."""
    try:
        percent = int(percent)
    except (TypeError, ValueError):
        return image
    if percent >= 100:
        return image
    # Image.point, not ImageEnhance: the frozen Monitor does not bundle PIL.ImageEnhance
    factor = max(percent, 0) / 100
    return image.point([int(i * factor + 0.5) for i in range(256)] * len(image.getbands()))


# Grey ramp measured on the 3.5" LCD (photos of a calibration chart, 2026-11-19): the panel's red, green and blue,
# each as a share of its own white, at input 0, 36, 73, 109, 146, 182, 219, 255. Blue is far too bright in the
# shadows and mid-tones (0.48 against 0.27 for red at 73), which turns violet themes blue. The white point is not
# touched: a phone camera sets its own, so it cannot be measured from photos.
_PANEL_LEVELS = (0, 36, 73, 109, 146, 182, 219, 255)
_PANEL_SHARE = ((0, 16, 46, 87, 114, 131, 148, 168), (0, 27, 58, 103, 124, 144, 158, 180),
                (0, 57, 94, 123, 142, 152, 170, 194))
_panel_luts = None


def _interp(x, xs, ys):
    """Linear interpolation of x over the increasing xs (a stand-in for numpy.interp; the Monitor needs no numpy)."""
    if x <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / (xs[i] - xs[i - 1])
    return ys[-1]


def panel_luts():
    """Three 256-entry tables (red, green, blue) that give the three channels the same curve (their mean)."""
    global _panel_luts
    if _panel_luts is None:
        shares = []
        for ys in _PANEL_SHARE:
            shares.append([max(ys[: i + 1]) / ys[-1] for i in range(len(ys))])
        mean = [sum(col) / 3 for col in zip(*shares)]
        tables = []
        for share in shares:
            table = [round(_interp(_interp(x, _PANEL_LEVELS, mean), share, _PANEL_LEVELS)) for x in range(256)]
            table[0], table[255] = 0, 255
            tables.append(table)
        _panel_luts = tables
    return _panel_luts


GAIN_RANGE = (70, 130)  # % of each colour the user may set (Settings > Screen colour)


def gain_values(gain):
    """(red, green, blue) in percent from the saved setting; a missing, odd or out-of-range value is 100 or clipped."""
    out = []
    for key in "rgb":
        raw = gain.get(key, 100) if hasattr(gain, "get") else 100
        try:
            number = float(raw)
            value = int(round(number)) if not isinstance(raw, bool) and number == number and abs(number) != float("inf") else 100
        except (TypeError, ValueError):  # text that is no number, a list: neutral
            value = 100
        out.append(min(max(value, GAIN_RANGE[0]), GAIN_RANGE[1]))
    return tuple(out)


def correct_panel(image, enabled=True, gain=None):
    """The frame as it should be sent so the LCD's three colours follow one grey curve, then each colour scaled by
    the user's white balance `gain` (% from `gain_values`, white stays 255 at 100). Off, or a bad image, returns
    it unchanged. Only the LCD gets this: the GUI previews show the colours the theme asks for."""
    if str(enabled).strip().lower() in ("false", "0", "no", "off", "none", ""):  # a hand-edited "false" is off too
        return image
    tables = panel_luts()
    gains = gain_values(gain or {})
    if gains != (100, 100, 100):
        tables = [[min(255, round(v * g / 100)) for v in table] for table, g in zip(tables, gains)]
    r, g, b = tables
    return image.convert("RGB").point(r + g + b)


SERIAL_STATS_MAX_AGE = 10  # seconds: an older file means the Monitor is no longer running


def serial_stats_path() -> Path:
    return _config_dir() / "serial_stats.json"


class SerialTimer:
    """Monitor side: how long each frame took to send over the serial port, averaged over the last 10 frames and
    written (average in ms, frames sent, time) for the GUI's Diagnostics tile. Never raises: a full disk or a locked
    file must not cost a frame."""

    def __init__(self, path=None):
        self.path = Path(path) if path else serial_stats_path()
        self.times = []
        self.frames = 0

    def record(self, seconds):
        self.frames += 1
        self.times = (self.times + [seconds])[-10:]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"ms": sum(self.times) / len(self.times) * 1000, "frames": self.frames,
                                       "time": time.time()}), encoding="utf-8")
            os.replace(tmp, self.path)  # the GUI never reads a half-written file
        except OSError:
            pass


def read_serial_stats(path=None, now=None):
    """GUI side: (average ms, frames sent) as the Monitor last wrote them, or None when there is no file, it is
    broken, or it is older than SERIAL_STATS_MAX_AGE seconds (the Monitor stopped)."""
    try:
        data = json.loads(Path(path or serial_stats_path()).read_text(encoding="utf-8"))
        ms, frames, stamp = float(data["ms"]), int(data["frames"]), float(data["time"])
    except (OSError, ValueError, KeyError, TypeError, OverflowError):  # OverflowError: frames written as 1e400
        return None
    now = time.time() if now is None else now
    if not (0 <= ms < 1e6) or not (-60 <= now - stamp <= SERIAL_STATS_MAX_AGE):  # also false for NaN and inf
        return None
    return ms, frames


LINK_STATES = ("connected", "retrying", "not_found", "busy")  # the Monitor's USB link (UsbLink in turmo_runtime.py)
LINK_STATUS_MAX_AGE = 10  # seconds: an older file means the Monitor is no longer running


def link_status_path() -> Path:
    return _config_dir() / "monitor_status.json"


class LinkStatus:
    """Monitor side: the state of the USB link, written for the GUI (state, port, attempt, since, time). Written when
    the state changes and at most every 2 s otherwise, so the GUI can tell a running Monitor from a stopped one.
    Never raises: a locked file must not cost a frame."""

    def __init__(self, path=None, clock=time.time):
        self.path = Path(path) if path else link_status_path()
        self.clock = clock
        self.last = None  # (state, time written)

    def write(self, state, port, attempt, since):
        now = self.clock()
        if self.last and self.last[0] == state and now - self.last[1] < 2.0:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"state": state, "port": port, "attempt": attempt, "since": since, "time": now}),
                           encoding="utf-8")
            os.replace(tmp, self.path)
            self.last = (state, now)  # only a write that happened: a reader holding the file makes the next call retry
        except OSError:
            pass

    def clear(self):
        """The Monitor is stopping: the GUI must not show the last state for another 10 s."""
        self.last = None
        try:
            self.path.unlink()
        except OSError:
            pass


def read_link_status(path=None, now=None):
    """GUI side: {"state", "port", "attempt", "since"} as the Monitor last wrote it, or None when there is no file, it
    is broken or odd, or it is older than LINK_STATUS_MAX_AGE seconds (the Monitor stopped or hangs)."""
    try:
        data = json.loads(Path(path or link_status_path()).read_text(encoding="utf-8"))
        state, stamp = data["state"], float(data["time"])
        port = data.get("port")
        attempt, since = int(data.get("attempt", 0)), float(data.get("since", stamp))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return None
    now = time.time() if now is None else now
    if state not in LINK_STATES or not (-60 <= now - stamp <= LINK_STATUS_MAX_AGE):  # also false for NaN and inf
        return None
    return {"state": state, "port": port if isinstance(port, str) else None, "attempt": attempt, "since": since}


def main() -> int:
    s = Settings.load()
    print(f"theme={s.theme} orientation={s.orientation} refresh_ms={s.refresh_ms}")
    print(f"port={s.port or '(auto)'} brightness={s.brightness} font_scale={s.font_scale}")
    print(f"widgets={s.widgets}")
    print(f"units={s.units} startup_windows={s.startup_windows}")
    print(f"config: {Settings.path()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())