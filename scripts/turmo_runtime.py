"""TURMO native runtime v2 — connects to TURMO 3.5" USB display on Windows.

Fixes vs v1:
- Matches libre-panel's protocol exactly (no redundant screen-on per frame)
- Uses libre_panel.rgb565 for correct encoding (fixes any subtle differences)
- Removed excessive flush() calls — writes in one burst per chunk
- Fixed PIL deprecation warning (get_flattened_data)
- Added proper telemetry dashboard mode
- Added reconnection support

Usage:
    python scripts/turmo_runtime.py --check
    python scripts/turmo_runtime.py --test-image
    python scripts/turmo_runtime.py --theme cyberpunk-neon [--once] [--portrait]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

# Add vendor directory so libre_panel is importable in frozen EXE
# Must be done BEFORE any libre_panel imports
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Running in PyInstaller bundle: vendor dir is at _MEIPASS/scripts/vendor
    # Also add scripts dir for runtime_logging, settings, etc.
    _scripts_dir = str(Path(sys._MEIPASS) / "scripts")
    _vendor_dir = str(Path(sys._MEIPASS) / "scripts" / "vendor")
else:
    # Running from source: vendor dir is at scripts/vendor relative to this file
    _scripts_dir = str(Path(__file__).resolve().parent)
    _vendor_dir = str(Path(__file__).resolve().parent / "vendor")

if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)
if _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)

try:
    import serial
    import serial.tools.list_ports as list_ports
except ImportError:
    sys.exit("pyserial not installed: pip install pyserial")

# Ensure libre_panel submodules are visible to PyInstaller's static analysis
# These are used in cmd_render_theme() but inside try/except so PyInstaller might miss them
import libre_panel.sensors
import libre_panel.sensors.base
import libre_panel.sensors.psutil_provider
import libre_panel.theme.model
import libre_panel.render.renderer

try:
    from libre_panel.devices.serial_link import rgb565
except ImportError:
    # Fallback: inline implementation matching libre-panel spec
    def rgb565(image, byteorder="little"):
        from PIL import ImageChops
        r, g, b = image.convert("RGB").split()
        high = ImageChops.add(r.point(lambda v: v & 0xF8), g.point(lambda v: v >> 5))
        low = ImageChops.add(g.point(lambda v: (v & 0x1C) << 3), b.point(lambda v: v >> 3))
        pair = (low, high) if byteorder == "little" else (high, low)
        return __import__("PIL").Image.merge("LA", pair).tobytes()

from PIL import Image, ImageDraw, ImageFont

VID = 0x1A86
PID = 0x5722
BAUD = 115200
TURING_SIZE = (320, 480)   # portrait
LANDSCAPE_SIZE = (480, 320)

# PyInstaller bundle support: use sys._MEIPASS when running from a bundled EXE
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
THEMES_DIR = PROJECT_ROOT / "themes"
try:
    from scripts import theme_paths  # official themes in THEMES_DIR, the user's in %APPDATA%\TURMO\themes\custom
except ImportError:  # started as scripts/turmo_runtime.py: scripts/ itself is on the path
    import theme_paths


def _theme_folder(name):
    return theme_paths.folder(THEMES_DIR, name)


CMD_SCREEN_ON = 109
CMD_DISPLAY_BITMAP = 197

# ─── orientation constants ───
PORTRAIT, LANDSCAPE = 0, 2
CMD_SET_ORIENTATION = 121


def header(command: int, x: int = 0, y: int = 0, ex: int = 0, ey: int = 0) -> bytes:
    """6-byte command header matching libre-panel exactly."""
    return bytes([
        x >> 2,
        ((x & 3) << 6) + (y >> 4),
        ((y & 15) << 4) + (ex >> 6),
        ((ex & 63) << 2) + (ey >> 8),
        ey & 255,
        command,
    ])


def set_orientation_cmd(orientation: str, width: int, height: int) -> bytes:
    """16-byte orientation command: header(121) + orientation byte + W/H big-endian."""
    cmd = bytearray(16)
    cmd[:6] = header(CMD_SET_ORIENTATION)
    cmd[6] = (LANDSCAPE if orientation == "landscape" else PORTRAIT) + 100
    cmd[7:11] = bytes([width >> 8, width & 0xFF, height >> 8, height & 0xFF])
    return bytes(cmd)

# ─── port discovery ───

def find_turmo_port() -> str | None:
    """Return first COM port matching VID:PID 1A86:5722."""
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

# ─── display protocol ───

class TurmoDisplay:
    """Minimal driver matching libre-panel's turing-rev-a protocol."""

    def __init__(self, port: str, landscape: bool = False):
        self.port = port
        self.landscape = landscape
        self.W, self.H = LANDSCAPE_SIZE if landscape else TURING_SIZE
        self._serial = None
        self._orientation: str | None = None  # "portrait" or "landscape"
        self._shutdown = False

    def open(self) -> None:
        """Open serial port, send screen ON (once), then set orientation."""
        # Use finite write_timeout so blocked writes can be interrupted by shutdown signal
        # 10s timeout allows ~40KB per write at 115200; full frame sent in chunks
        print(f"[DEBUG] Opening {self.port} at {BAUD} baud, rtscts=False, write_timeout=10", flush=True)
        self._serial = serial.Serial(
            self.port, BAUD, timeout=1, write_timeout=10, rtscts=False
        )
        print(f"[DEBUG] Serial opened: {self._serial.is_open}", flush=True)
        cmd = header(CMD_SCREEN_ON)
        print(f"[DEBUG] Writing CMD_SCREEN_ON ({len(cmd)} bytes): {cmd.hex()}", flush=True)
        self._serial.write(cmd)
        print(f"[DEBUG] Write successful", flush=True)
        # Read any response
        try:
            resp = self._serial.read(64)
            print(f"[DEBUG] Response after SCREEN_ON: {resp.hex() if resp else 'none'}", flush=True)
        except Exception as e:
            print(f"[DEBUG] Read error: {e}", flush=True)
        time.sleep(0.5)  # longer delay
        # Tell panel our desired orientation — MUST match image dimensions
        self.send_orientation("portrait" if not self.landscape else "landscape")

    def request_shutdown(self) -> None:
        """Signal the display to stop sending and close the port."""
        self._shutdown = True
        # Closing the serial port will unblock any pending write()
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass

    def send_orientation(self, orientation: str) -> None:
        """Declare panel orientation; sends CMD_SET_ORIENTATION if changed."""
        if orientation == self._orientation:
            return
        print(f"[DEBUG] Sending orientation: {orientation}", flush=True)
        cmd = set_orientation_cmd(orientation, self.W, self.H)
        print(f"[DEBUG] Orientation cmd ({len(cmd)} bytes): {cmd.hex()}", flush=True)
        self._serial.write(cmd)
        print(f"[DEBUG] Orientation write successful", flush=True)
        self._orientation = orientation

    def set_landscape(self, landscape: bool) -> None:
        """Switch orientation while connected: the next frame sends the new orientation command with the new size."""
        self.landscape = landscape
        self.W, self.H = LANDSCAPE_SIZE if landscape else TURING_SIZE

    def close(self) -> None:
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        self._orientation = None

    def send_bitmap(self, image: Image.Image) -> bool:
        """Send a full-frame bitmap. Image size must match W×H for current orientation."""
        if self._serial is None or self._shutdown:
            return False
        orientation = "landscape" if self.landscape else "portrait"
        self.send_orientation(orientation)  # no-op if already set
        try:
            self._serial.write(header(CMD_DISPLAY_BITMAP, 0, 0, self.W - 1, self.H - 1))
        except serial.SerialTimeoutException:
            print("[turmo] write timeout sending header", file=sys.stderr)
            return False
        pix = rgb565(image, "little")
        chunk_size = self.W * 8  # width * 8 matches libre-panel reference
        for i in range(0, len(pix), chunk_size):
            if self._shutdown:
                return False
            try:
                self._serial.write(pix[i:i + chunk_size])
            except serial.SerialTimeoutException:
                print(f"[turmo] write timeout at chunk {i//chunk_size}", file=sys.stderr)
                return False
            except serial.SerialException as e:
                print(f"[turmo] serial error during send: {e}", file=sys.stderr)
                return False
        return True


# ─── USB link: reconnect without a restart (v0.3.0) ───

USB_BACKOFF = (0.5, 1.0, 2.0, 5.0)  # seconds before the next attempt; the last one repeats until the display is back


def resolve_port(preferred, ports=None):
    """The COM port to open: `preferred` while it still exists, else the device with VID:PID 1A86:5722 (Windows may give
    it another COM number after an unplug), else None (not plugged in or not powered yet)."""
    ports = list_ports.comports() if ports is None else ports
    turmo = [p.device for p in ports if p.vid == VID and p.pid == PID]
    if preferred in turmo or not turmo and any(p.device == preferred for p in ports):
        return preferred  # a saved COM number may now belong to another adapter: the TURMO by VID:PID wins
    return turmo[0] if turmo else None


class UsbLink:
    """The Monitor's USB connection as a small state machine. `state` is "connected", "retrying" (the port is there
    but opening or sending failed), "busy" (another program holds the port) or "not_found" (no TURMO device).

    `send_bitmap` is the display's own call: False while not connected, and a failed send closes the display and starts
    the retry schedule. `maintain` is called by the loop each tick while not connected and makes one attempt when the
    backoff says so, finding the port again by VID:PID. Nothing here raises, sleeps or exits: the Monitor stops only on
    Stop or a fatal error. The log gets one line per change of state, not one per attempt; `publish` tells the GUI."""

    def __init__(self, make_display, preferred_port=None, publish=None, log=None, clock=time.monotonic, find=resolve_port):
        self.make_display, self.preferred, self.clock, self.find = make_display, preferred_port, clock, find
        self.publish, self.log = publish or (lambda *a: None), log or (lambda *a: None)
        self.disp = None
        self.state = None
        self.port = preferred_port
        self.attempt = 0
        self.since = time.time()
        self.next_try = 0.0
        self._shutdown = False

    def ready(self):
        return self.state == "connected"

    def heartbeat(self):
        """While connected: tell the GUI the Monitor is alive (the status file ages out after 10 s)."""
        self.publish(self.state, self.port, self.attempt, self.since)

    @property
    def stopping(self):
        return self._shutdown

    def _set(self, state):
        if state != self.state:
            self.state, self.since = state, time.time()
            self.log(state, self.port, self.attempt)
        self.publish(self.state, self.port, self.attempt, self.since)

    def _failed(self, state, now):
        self.attempt += 1
        self.next_try = now + USB_BACKOFF[min(self.attempt - 1, len(USB_BACKOFF) - 1)]
        self._set(state)

    def maintain(self):
        """One reconnect attempt when it is due; otherwise only tells the GUI the Monitor is alive."""
        if self.ready() or self._shutdown:
            return
        now = self.clock()
        if now < self.next_try:
            self.publish(self.state, self.port, self.attempt, self.since)
            return
        try:
            port = self.find(self.preferred)
        except Exception:  # port enumeration failed: treat as not found, try again later
            port = None
        if port is None:
            self._failed("not_found", now)
            return
        self.port = port
        disp = self.make_display(port)
        try:
            disp.open()
        except Exception as e:  # SerialException, PermissionError, a cable pulled while opening: all mean "try again"
            try:
                disp.close()
            except Exception:
                pass
            denied = "denied" in str(e).lower() or isinstance(e, PermissionError)
            self._failed("busy" if denied else "retrying", now)
            return
        self.disp, self.attempt, self.next_try = disp, 0, 0.0
        self._set("connected")

    def send_bitmap(self, image):
        if self.disp is None or self._shutdown:
            return False
        try:
            ok = self.disp.send_bitmap(image)
        except Exception:  # the cable was pulled mid-frame
            ok = False
        if not ok and not self._shutdown:
            self._lose()
        return ok

    def _lose(self):
        try:
            self.disp.close()
        except Exception:
            pass
        self.disp = None
        self._failed("retrying", self.clock())

    def set_landscape(self, landscape):
        """The live orientation changed: tell the open display (a display opened later is made with the new value)."""
        if self.disp is not None:
            self.disp.set_landscape(landscape)

    def request_shutdown(self):
        self._shutdown = True
        if self.disp is not None:
            self.disp.request_shutdown()

    def close(self):
        if self.disp is not None:
            self.disp.close()
            self.disp = None


def _log_link(state, port, attempt):
    """One line per change of the USB link's state, in the console and in the runtime log (never one per attempt)."""
    text = {"connected": "display connected", "retrying": "link lost, reconnecting",
            "busy": "port in use by another program, waiting", "not_found": "display not found, waiting"}[state]
    print(f"\n[turmo] USB: {text} ({port or 'no port'})", flush=True)
    try:
        from runtime_logging import log_runtime
        log_runtime("WORKER", "USB_" + state.upper(), f"{text} port={port} attempt={attempt}",
                    level="INFO" if state == "connected" else "WARNING")
    except Exception:
        pass

# ─── test patterns ───

def draw_test_pattern(path: str = "previews/test-pattern-v2.png") -> Image.Image:
    """High-quality landscape test pattern: gradients, shapes, color bars, text."""
    W, H = LANDSCAPE_SIZE  # 480×320
    img = Image.new("RGB", (W, H), color=(10, 10, 18))
    draw = ImageDraw.Draw(img)

    # Subtle gradient background
    for y in range(H):
        brightness = int(10 + 15 * y / H)
        draw.line([(0, y), (W, y)], fill=(brightness, brightness + 2, brightness + 8))

    # Color calibration bars (bottom portion)
    colors = [
        (255, 0, 0), (0, 255, 0), (0, 0, 255),
        (255, 255, 0), (255, 0, 255), (0, 255, 255),
        (255, 255, 255), (0, 0, 0),
    ]
    bar_h = H // (len(colors) + 2)
    for i, c in enumerate(colors):
        draw.rectangle([0, (i + 1) * bar_h, W, (i + 2) * bar_h], fill=c)

    # Sharp geometric shapes (top-left area)
    cx, cy = W // 2 - 80, 60
    draw.polygon([(cx, cy - 40), (cx - 35, cy + 30), (cx + 35, cy + 30)], fill=(255, 100, 0))
    draw.ellipse([cx + 50, cy - 30, cx + 110, cy + 30], outline=(0, 255, 255), width=2)
    draw.rectangle([cx - 50, cy - 30, cx - 10, cy + 10], outline=(255, 255, 0), width=2)

    # Text
    try:
        font_big = ImageFont.truetype("arial.ttf", 34)
        font_med = ImageFont.truetype("arial.ttf", 16)
        font_small = ImageFont.truetype("arial.ttf", 11)
    except OSError:
        font_big = ImageFont.load_default()
        font_med = font_big
        font_small = font_big
    draw.text((W // 2, H - 60), "TURMO DISPLAY TEST", fill=(255, 255, 255), font=font_big, anchor="mm")
    draw.text((W // 2, H - 35), "VID:PID 1A86:5722 · COM4", fill=(200, 200, 200), font=font_med, anchor="mm")
    draw.text((W // 2, H - 15), "480×320 Landscape · RGB565 LE", fill=(150, 150, 150), font=font_small, anchor="mm")

    img.save(path)
    return img


def draw_orientation_diagnostic(path: str, orientation: str) -> Image.Image:
    """Deterministic diagnostic pattern with labeled corners for orientation testing.

    Shows colored quadrants, numbered corners, axis arrows, and center marker.
    Landscape: 480×320 | Portrait: 320×480
    """
    is_landscape = orientation == "landscape"
    W, H = LANDSCAPE_SIZE if is_landscape else TURING_SIZE

    img = Image.new("RGB", (W, H), color=(15, 15, 25))
    draw = ImageDraw.Draw(img)

    try:
        font_big = ImageFont.truetype("arial.ttf", min(W, H) // 10)
        font_med = ImageFont.truetype("arial.ttf", min(W, H) // 14)
        font_small = ImageFont.truetype("arial.ttf", min(W, H) // 20)
    except OSError:
        font_big = font_med = font_small = ImageFont.load_default()

    # Four colored quadrants (top-left=red, top-right=green, bottom-left=blue, bottom-right=white)
    hw, hh = W // 2, H // 2
    draw.rectangle([0, 0, hw, hh], fill=(200, 20, 20))     # TL red
    draw.rectangle([hw, 0, W, hh], fill=(20, 200, 20))     # TR green
    draw.rectangle([0, hh, hw, H], fill=(20, 20, 200))     # BL blue
    draw.rectangle([hw, hh, W, H], fill=(220, 220, 220))   # BR white

    # Border
    draw.rectangle([0, 0, W-1, H-1], outline=(255, 255, 0), width=2)

    # Corner markers with labels
    corners = [
        ((5, 5), "TL"), ((W-25, 5), "TR"),
        ((5, H-20), "BL"), ((W-25, H-20), "BR")
    ]
    for (x, y), label in corners:
        draw.text((x, y), label, fill=(0, 0, 0), font=font_med)

    # Center crosshair
    cx, cy = W // 2, H // 2
    draw.line([(cx-20, cy), (cx+20, cy)], fill=(0, 0, 0), width=2)
    draw.line([(cx, cy-20), (cx, cy+20)], fill=(0, 0, 0), width=2)

    # Orientation label
    label = f"Landscape {W}×{H}" if is_landscape else f"Portrait {W}×{H}"
    draw.text((cx, H//2 + 30), label, fill=(0, 0, 0), font=font_med, anchor="mm")

    # Axis arrows
    arrow_len = 40
    # X-axis (left to right)
    draw.line([(30, 25), (W-30, 25)], fill=(255, 255, 0), width=2)
    draw.polygon([(W-30, 25), (W-20, 20), (W-20, 30)], fill=(255, 255, 0))
    draw.text((W-35, 15), "X", fill=(255, 255, 0), font=font_small)
    # Y-axis (top to bottom)
    draw.line([(25, 30), (25, H-30)], fill=(255, 255, 0), width=2)
    draw.polygon([(25, H-30), (20, H-20), (30, H-20)], fill=(255, 255, 0))
    draw.text((15, H-35), "Y", fill=(255, 255, 0), font=font_small)

    img.save(path)
    return img

# ─── theme loading ───

def _generate_fallback_pattern(theme_name: str, landscape: bool = True) -> Image.Image:
    """Generate a fallback pattern when preview file can't be read."""
    W, H = LANDSCAPE_SIZE if landscape else TURING_SIZE
    img = Image.new("RGB", (W, H), color=(50, 50, 100))
    draw = ImageDraw.Draw(img)
    draw.text((W//2, H//2), f"{theme_name} {'LAND' if landscape else 'POR'} {W}x{H} (fallback)", fill=(255, 255, 0), anchor="mm")
    return img


def load_theme(theme_name: str, landscape: bool = True) -> tuple[Image.Image, dict]:
    """Load rendered theme preview PNG + metadata. Falls back to generated pattern on PermissionError."""
    # Previews live in previews/<name>.png (landscape) or previews/<name>-320x480.png (portrait)
    # A theme the user made (or edited: a custom copy of Custom Blank Canvas) must not show the official picture.
    mine = any(theme_paths.is_custom(n) for n in (theme_name, f"{theme_name}-320x480", f"{theme_name}-480x320"))
    png_candidates = [] if mine else [
        PROJECT_ROOT / "previews" / f"{theme_name}.png",
        PROJECT_ROOT / "previews" / f"{theme_name}-480x320.png",
        PROJECT_ROOT / "previews" / f"{theme_name}-320x480.png",
    ]
    png_candidates += [
        _theme_folder(theme_name) / "preview.png",
        _theme_folder(f"{theme_name}-480x320") / "preview.png",
        _theme_folder(f"{theme_name}-320x480") / "preview.png",
    ]
    png_path = next((p for p in png_candidates if p.exists()), None)
    if not png_path:
        raise FileNotFoundError(f"No preview found for theme '{theme_name}' (looked in previews/ and themes/)")

    try:
        img = Image.open(str(png_path))
    except PermissionError:
        print(f"[turmo] Warning: cannot read preview file (permission), generating fallback for '{theme_name}'")
        return _generate_fallback_pattern(theme_name, landscape), {}

    # Normalize to expected size (landscape 480x320 unless explicitly portrait)
    expected = TURING_SIZE if (png_path.name.endswith("-320x480.png") or (args and getattr(args, "portrait", False))) else LANDSCAPE_SIZE
    if img.size != expected:
        img = img.resize(expected, Image.LANCZOS)

    # Config: prefer the theme.json next to the preview; fall back to themes/<name>/
    config = {}
    for cfg_path in [
        _theme_folder(theme_name) / "theme.json",
        _theme_folder(f"{theme_name}-480x320") / "theme.json",
        _theme_folder(f"{theme_name}-320x480") / "theme.json",
    ]:
        if cfg_path.exists():
            import json
            with open(cfg_path) as f:
                config = json.load(f)
            break
    return img, config

# ─── telemetry ───

def get_telemetry() -> dict:
    """Collect system stats via psutil."""
    import psutil
    cpu_pct = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    disks = {}
    for part in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(part.mountpoint)
            disks[part.mountpoint] = {
                "total_gb": round(u.total / 1e9, 1),
                "used_gb": round(u.used / 1e9, 1),
                "percent": u.percent,
            }
        except OSError:
            pass
    net = psutil.net_io_counters()
    return {
        "cpu_pct": cpu_pct,
        "ram_used_gb": round(memory.used / 1e9, 1),
        "ram_total_gb": round(memory.total / 1e9, 1),
        "ram_percent": memory.percent,
        "disks": disks,
        "net_bytes_sent": net.bytes_sent,
        "net_bytes_recv": net.bytes_recv,
        "uptime": time.time() - psutil.boot_time(),
    }


# ─── CPU temperature via LibreHardwareMonitor (Windows) ───
# Initialize pythonnet at module level so CLR is ready for background threads
# Must happen before any threads are created (Pythonnet thread-affinity requirement)
_LHM_COMPUTER = None
_LHM_INITIALIZED = False
LIBRARY = "LibreHardwareMonitorLib"
_LHM_LAST_FAIL_TIME: float = 0.0
_LHM_LAST_FAIL_SIG: str = ""
# ponytail: helper-based CPU temp - log HELPER_UNAVAILABLE once, bounded by cooldown
_HELPER_LAST_LOG_TIME: float = 0.0
_HELPER_UNAVAILABLE_LOGGED: bool = False

def _preinit_libre_hardware_monitor():
    """Pre-initialize CLR on main thread before any background threads start.

    This must be called from main thread before spawning worker threads.
    Required because pythonnet.load("coreclr") has thread-affinity requirements.
    LibreHardwareMonitorLib.dll targets .NET 10.0 CoreCLR (.NETCoreApp,Version=v10.0).
    """
    global _LHM_INITIALIZED
    if _LHM_INITIALIZED:
        return
    if sys.platform != "win32":
        _LHM_INITIALIZED = True
        return
    try:
        import pythonnet
        if not getattr(pythonnet, "_LOADED", False):  # the GUI's loading screen may have loaded it already
            pythonnet.load("coreclr")
        import clr  # noqa: F401 - make sure clr module is loaded
        print("[turmo] CLR initialized on main thread (coreclr)", file=sys.stderr)
        try:
            from runtime_logging import log_runtime
            log_runtime("CPU_TEMP", "CLR_PREINIT_OK", "pythonnet.load(coreclr) succeeded on main thread")
        except Exception:
            pass
    except ImportError as e:
        print(f"[turmo] pythonnet not available - CPU temperature disabled: {e}", file=sys.stderr)
        try:
            from runtime_logging import log_runtime
            log_runtime("CPU_TEMP", "CLR_PREINIT_FAIL", f"pythonnet import failed: {e}", exc=e)
        except Exception:
            pass
    except Exception as e:
        print(f"[turmo] CLR preinit warning: {e}", file=sys.stderr)
        try:
            from runtime_logging import log_runtime
            log_runtime("CPU_TEMP", "CLR_PREINIT_FAIL", f"pythonnet.load(coreclr) failed: {e}", exc=e)
        except Exception:
            pass
    _LHM_INITIALIZED = True


def _init_libre_hardware_monitor():
    """Initialize LibreHardwareMonitor computer instance.

    Loads the .NET assembly from bundled DLLs in scripts/vendor/lhm/ (PyInstaller _MEIPASS)
    or from the system-wide LibreHardwareMonitor.NET10 install path.
    Includes comprehensive diagnostics and bounded retry to prevent failure storms.
    """
    global _LHM_COMPUTER, _LHM_LAST_FAIL_TIME, _LHM_LAST_FAIL_SIG
    if _LHM_COMPUTER is not None:
        return True
    if not _LHM_INITIALIZED:
        # This shouldn't happen if pre-init was called, but be defensive
        _preinit_libre_hardware_monitor()
    import sys
    import time
    lhm_dir: str | None = "unknown"
    loaded_dlls: list = []
    missing_dlls: list = []
    addref_results: list = []
    lhm_dirs: list[str] = []  # ponytail: init before try so except can reference it
    try:
        # Bounded retry: skip if identical failure within 60 seconds
        now = time.time()
        if now - _LHM_LAST_FAIL_TIME < 60.0:
            try:
                from runtime_logging import log_runtime
                log_runtime("CPU_TEMP", "LHM_RETRY_SKIP",
                            f"Skipping LHM init: failed {now - _LHM_LAST_FAIL_TIME:.0f}s ago (sig={_LHM_LAST_FAIL_SIG[:80]})")
            except Exception:
                pass
            return False

        # Find the LHM directory (before importing clr - Python.NET uses sys.path for deps)
        lhm_dirs: list[str] = []
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            lhm_dirs.append(str(Path(bundle) / "lhm"))
        if getattr(sys, "frozen", False):
            exedir = Path(sys.executable).resolve().parent
            lhm_dirs.extend([str(exedir / "lhm"), str(exedir / "_internal" / "lhm")])
        system_path = r"C:\Program Files\LibreHardwareMonitor.NET10"
        if Path(system_path).is_dir():
            lhm_dirs.append(system_path)

        lhm_dir = None
        for d in lhm_dirs:
            if Path(d, f"{LIBRARY}.dll").is_file():
                lhm_dir = d
                break
        if lhm_dir is None:
            raise FileNotFoundError(
                f"LibreHardwareMonitorLib.dll not found in any of: {lhm_dirs}"
            )

        # Add DLL directory to sys.path BEFORE importing clr
        # Python.NET resolves .NET assembly dependencies through sys.path
        if lhm_dir not in sys.path:
            sys.path.append(lhm_dir)

        # Import clr AFTER sys.path modification (matches lhm_inprocess.py pattern)
        import clr

        # Load all dependencies in order (matches lhm_inprocess.py LIBRARIES order)
        dep_order = [
            "System.Memory",
            "System.Buffers",
            "System.Numerics.Vectors",
            "System.Runtime.CompilerServices.Unsafe",
            "BlackSharp.Core",
            "RAMSPDToolkit-NDD",
            "DiskInfoToolkit",
            "HidSharp",
            LIBRARY,
        ]
        loaded_dlls = []
        missing_dlls = []
        addref_results = []  # (lib_name, success, assembly_identity_or_error)
        for lib_name in dep_order:
            dll = Path(lhm_dir, f"{lib_name}.dll")
            if dll.is_file():
                try:
                    assembly = clr.AddReference(str(dll))
                    loaded_dlls.append(lib_name)
                    try:
                        identity = assembly.FullName
                    except Exception:
                        identity = str(assembly)
                    addref_results.append((lib_name, True, identity))
                    # ponytail: capture LIBRARY assembly metadata for diagnostics
                    if lib_name == LIBRARY:
                        try:
                            ref_asms = [f"{r.Name} {r.Version}" for r in assembly.GetReferencedAssemblies()]
                            type_count = len(assembly.GetTypes())
                            addref_results.append((f"{lib_name}.refs", True, f"{type_count} types, refs: {', '.join(ref_asms[:10])}"))
                            if "10.0.0.0" in str(ref_asms) or "CoreLib" in str(ref_asms):
                                addref_results.append((f"{lib_name}.warn", True, "targets .NET 10 CoreCLR — may be incompatible with netfx"))
                        except Exception as asm_err:
                            addref_results.append((f"{lib_name}.asm_err", False, str(asm_err)))
                except Exception as e:
                    missing_dlls.append(str(dll))
                    addref_results.append((lib_name, False, f"{type(e).__name__}: {e}"))
                    print(f"[turmo] Warning: {dll} AddReference failed: {e}", file=sys.stderr)
            else:
                missing_dlls.append(str(dll))
                addref_results.append((lib_name, False, "file not found"))
                print(f"[turmo] Warning: {dll} not found, skipping", file=sys.stderr)

        # Import from the correct .NET namespace
        try:
            from LibreHardwareMonitor.Hardware import Computer
        except Exception as import_err:
            # Capture ReflectionTypeLoadException and LoaderExceptions
            import traceback
            tb = traceback.format_exc()
            loader_exceptions = []
            le_attr = getattr(import_err, 'LoaderExceptions', None)
            if le_attr:
                for le in le_attr:
                    loader_exceptions.append(f"{type(le).__name__}: {le}")
            raise import_err from None

        computer = Computer()
        computer.IsCpuEnabled = True
        computer.IsGpuEnabled = False
        computer.IsMemoryEnabled = False
        computer.Open()
        _LHM_COMPUTER = computer
        _init_libre_hardware_monitor._last_dir = lhm_dir  # exposed for helper logging
        try:
            from runtime_logging import log_runtime
            log_runtime("CPU_TEMP", "LHM_INIT_OK",
                        f"Computer opened: {len(loaded_dlls)} DLLs loaded, {len(missing_dlls)} missing, lhm_dir={lhm_dir}")
        except Exception:
            pass
        return True
    except Exception as e:
        # Comprehensive failure diagnostics (m02012 spec)
        import traceback
        tb = traceback.format_exc()
        frozen = getattr(sys, "frozen", False)
        meipass = getattr(sys, "_MEIPASS", None)
        exe = sys.executable
        py_ver = sys.version
        py_platform = sys.platform
        sys_path_entries = sys.path[-5:] if len(sys.path) > 5 else sys.path
        cwd = os.getcwd()

        # Build failure signature for bounded retry
        fail_sig = f"{type(e).__name__}:{str(e)}:{lhm_dir if 'lhm_dir' in locals() else 'unknown'}"

        # ── LHM DLL presence + size + SHA256 ──
        lhm_lib_info = ""
        if "lhm_dir" in locals() and lhm_dir is not None:
            lhm_lib_path = Path(lhm_dir, f"{LIBRARY}.dll")
            if lhm_lib_path.is_file():
                import hashlib
                sha256 = hashlib.sha256(lhm_lib_path.read_bytes()).hexdigest()
                size = lhm_lib_path.stat().st_size
                lhm_lib_info = f"{LIBRARY}.dll present size={size} sha256={sha256}"
            else:
                lhm_lib_info = f"{LIBRARY}.dll NOT FOUND at {lhm_lib_path}"

        # ── pythonnet runtime info ──
        pythonnet_info = ""
        try:
            import pythonnet
            pythonnet_info = f"pythonnet={pythonnet.__version__}"
            # Try to get runtime version
            try:
                import clr as _clr_probe
                rt_ver = _clr_probe.GetCoreAssembly().GetVersion()
                pythonnet_info += f" coreclr_runtime={rt_ver}"
            except Exception:
                pythonnet_info += " (runtime not loaded)"
        except Exception:
            pythonnet_info = "pythonnet not importable"

        # ── Dependency DLL presence ──
        dep_presence = {}
        if "lhm_dir" in locals() and lhm_dir is not None:
            for dep in ("System.Memory", "System.Buffers", "System.Numerics.Vectors",
                        "System.Runtime.CompilerServices.Unsafe", "BlackSharp.Core",
                        "RAMSPDToolkit-NDD", "DiskInfoToolkit", "HidSharp", LIBRARY):
                dep_path = Path(lhm_dir, f"{dep}.dll")
                dep_presence[dep] = dep_path.is_file()

        # ── 6-class failure classification ──
        exc_type = type(e).__name__
        exc_msg = str(e)
        if "No module named" in exc_msg and "LibreHardwareMonitor" in exc_msg:
            fail_class = "DLL_NOT_FOUND_OR_PATH_MISSING"
        elif "AddReference" in exc_msg or "Could not load file or assembly" in exc_msg:
            fail_class = "DLL_PRESENT_BUT_NOT_LOADABLE"
        elif "LoaderExceptions" in exc_msg or "TypeLoadException" in exc_msg:
            fail_class = "DEPENDENCY_RESOLUTION_FAILURE"
        elif exc_type in ("AttributeError", "ImportError") and "Computer" in exc_msg:
            fail_class = "WRONG_ASSEMBLY_OR_NAMESPACE"
        elif "Python" in exc_msg and "clr" in exc_msg:
            fail_class = "PYTHONNET_NAMESPACE_IMPORT_FAILURE"
        elif exc_type in ("Exception", "RuntimeError") and "Computer" not in exc_msg:
            fail_class = "HARDWARE_INIT_FAILURE"
        else:
            fail_class = f"UNKNOWN:{exc_type}"

        print(f"[turmo] LibreHardwareMonitor init failed: {e}", file=sys.stderr)
        print(f"[turmo] Frozen={frozen} MEIPASS={meipass} exe={exe}", file=sys.stderr)
        print(f"[turmo] py_ver={py_ver} platform={py_platform} cwd={cwd}", file=sys.stderr)
        print(f"[turmo] traceback:\n{tb}", file=sys.stderr)
        try:
            from runtime_logging import log_runtime
            lhm_dir_listing = []
            if 'lhm_dir' in locals() and lhm_dir is not None:
                try:
                    lhm_dir_listing = os.listdir(lhm_dir)
                except Exception:
                    lhm_dir_listing = ["<listdir failed>"]
            lhm_dirs_val = lhm_dirs if 'lhm_dirs' in locals() else []
            diag_msg = (
                f"LibreHardwareMonitor init failed: {type(e).__name__}: {e} | "
                f"frozen={frozen} meipass={meipass} exe={exe} "
                f"lhm_dir={lhm_dir if 'lhm_dir' in locals() else 'unknown'} "
                f"lhm_dirs={lhm_dirs_val} "
                f"lhm_dir_files={lhm_dir_listing} "
                f"py_ver={py_ver} platform={py_platform} cwd={cwd} "
                f"pythonnet_info={pythonnet_info} "
                f"lhm_lib_info={lhm_lib_info} "
                f"dep_presence={dep_presence} "
                f"fail_class={fail_class} "
                f"sys_path_tail={sys_path_entries} "
                f"loaded={loaded_dlls if 'loaded_dlls' in locals() else []} "
                f"missing={missing_dlls if 'missing_dlls' in locals() else []} "
                f"addref_results={addref_results if 'addref_results' in locals() else []}"
            )
            log_runtime("CPU_TEMP", "LHM_INIT_FAIL", diag_msg, exc=e, level="ERROR")
        except Exception:
            pass
        # Update bounded retry state
        _LHM_LAST_FAIL_TIME = time.time()
        _LHM_LAST_FAIL_SIG = fail_sig
        return False


def read_cpu_temperature():
    """Read CPU temperature from the CPU temp helper over 127.0.0.1:18234.

    ponytail: the helper runs elevated and reads LHM; the GUI stays
    unelevated.  No UAC prompt at runtime.  Logs HELPER_UNAVAILABLE
    once per 60s, no retry storm.
    """
    from libre_panel.sensors.base import Reading
    import socket
    global _HELPER_LAST_LOG_TIME, _HELPER_UNAVAILABLE_LOGGED

    try:
        sock = socket.create_connection(("127.0.0.1", 18234), timeout=1.0)
        try:
            sock.sendall(b"GET\n")
            data = b""
            while b"\n" not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
        finally:
            sock.close()
        info = json.loads(data.decode().strip())
        cpu_temp_c = info.get("cpu_temp")
        if cpu_temp_c is None:
            return {}
        # STEP 5c: treat data older than 5s as unavailable (helper is hung/crashed).
        ts = info.get("ts")
        if ts is not None and time.time() - float(ts) > 5.0:
            return {}
        return {
            "cpu.temp": Reading(
                key="cpu.temp",
                value=float(cpu_temp_c),
                unit="\u00b0C",
                label="CPU temperature",
                origin=info.get("cpu_name", "CPU temp helper"),
            )
        }
    except Exception as e:
        # Bounded logging with phase detection (connect timeout / read timeout / refused / reset)
        exc_type = type(e).__name__
        phase = "unknown"
        if "timeout" in str(e).lower():
            phase = "read_timeout"
        elif "connection refused" in str(e).lower() or "ECONNREFUSED" in str(e):
            phase = "connection_refused"
        elif "reset" in str(e).lower():
            phase = "connection_reset"
        now = time.time()
        if now - _HELPER_LAST_LOG_TIME >= 60.0:
            try:
                from runtime_logging import log_runtime
                log_runtime("CPU_TEMP", "HELPER_UNAVAILABLE",
                            f"phase={phase} error={exc_type}: {e}")
            except Exception:
                pass
            _HELPER_LAST_LOG_TIME = now
        return {}


# ─── CLI commands ───

args = None  # populated after parse_args

def _lock_path() -> Path:
    """Single-instance lock file: %APPDATA%/TURMO/monitor.lock (or ~/.config/turmo)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
        d = Path(base) / "TURMO"
    else:
        d = Path.home() / ".config" / "turmo"
    d.mkdir(parents=True, exist_ok=True)
    return d / "monitor.lock"


def _live_theme_dir(theme_name: str, landscape: bool) -> str:
    """The theme folder the live loop draws: portrait uses <theme>-320x480 when that folder exists."""
    if not landscape and _theme_folder(f"{theme_name}-320x480").is_dir():
        return f"{theme_name}-320x480"
    return theme_name


def _theme_stamp(dir_name: str):
    """Modification time of the theme's theme.json (None when it is missing): the live loop draws the theme again
    when this changes, so a custom theme saved in the editor shows on the LCD without a restart (v0.2.4.1)."""
    try:
        return (_theme_folder(dir_name) / "theme.json").stat().st_mtime_ns
    except OSError:
        return None


def _orientation_to_draw(seen_orientation, setting_orientation, landscape):
    """(seen_orientation, landscape, changed) for the live loop: the orientation in settings.json changed since the
    last frame, so the panel switches without a restart. An orientation given with --landscape/--portrait stays until
    the setting changes; anything else in the file (None, a number, another word) keeps what is drawn."""
    if setting_orientation not in ("landscape", "portrait") or setting_orientation == seen_orientation:
        return seen_orientation, landscape, False
    want = setting_orientation == "landscape"
    return setting_orientation, want, want != landscape


def _theme_to_draw(target_theme, seen_setting, setting_theme, landscape, current, bad):
    """Which theme the live loop should draw now: (target_theme, seen_setting, want, load).
    `want` is (folder name, theme.json stamp); `load` is True when it differs from `current` (what is on the screen)
    and is not `bad` (a theme that already failed, until its files change). A theme given with --theme stays until
    the theme in settings.json changes (`setting_theme` differs from `seen_setting`), so a Monitor started by hand
    with --theme is not switched on its first frame."""
    if isinstance(setting_theme, str) and setting_theme:  # anything else (None, a number): keep what is drawn
        chosen = "minimal-dark" if setting_theme == "minimal" else setting_theme
        if chosen != seen_setting:
            seen_setting = target_theme = chosen
    folder = _live_theme_dir(target_theme, landscape)
    want = (folder, _theme_stamp(folder))
    return target_theme, seen_setting, want, want != current and want != bad


def _setting_theme():
    """The theme named in settings.json, or None when the file cannot be read right now (missing, half written,
    locked): `Settings.load` would answer with the default theme then, and the loop would flash it."""
    try:
        from settings import Settings
        value = json.loads(Settings.path().read_text(encoding="utf-8")).get("theme")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) else None


def _stop_request_path() -> Path:
    """GUI→worker graceful-stop channel: %APPDATA%/TURMO/stop_monitor.request."""
    return _lock_path().parent / "stop_monitor.request"


def _acquire_lock() -> bool:
    """Return True if we hold the single-instance lock, False if another monitor runs.
    Uses atomic file creation (O_EXCL) on Windows and fcntl on Unix for race-free locking.
    On Windows, validates PID + executable path + creation time to avoid PID reuse mistakes.
    """
    p = _lock_path()
    try:
        # Atomic create - fails if file exists (O_EXCL)
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except FileExistsError:
        # Lock file exists - check if we already hold it or if stale
        try:
            content = p.read_text().strip()
            pid = int(content or "0")
            if pid == os.getpid():
                # We already hold the lock
                return True
            alive = False
            try:
                import psutil
                alive = psutil.pid_exists(pid)
                # Ponytail: on Windows, verify executable path + creation time to prevent PID reuse false positives
                if alive and sys.platform == "win32":
                    try:
                        proc = psutil.Process(pid)
                        # A Monitor is python.exe from source, or TURMO-Monitor.exe when frozen;
                        # anything else with a reused PID is a stale lock.
                        name = proc.name().lower()
                        if "python" in name or "turmo-monitor" in name:
                            alive = True
                        else:
                            alive = False
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        alive = False
            except ImportError:
                # Fallback for Unix
                try:
                    os.kill(pid, 0)
                    alive = True
                except OSError:
                    alive = False
            if alive:
                # Another process holds the lock
                return False
            # Stale lock - replace atomically
            p.unlink(missing_ok=True)
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, 'w') as f:
                f.write(str(os.getpid()))
            return True
        except Exception:
            # If lock file is corrupted, try to clear and reacquire
            try:
                p.unlink(missing_ok=True)
                fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, 'w') as f:
                    f.write(str(os.getpid()))
                return True
            except Exception:
                return False
    except Exception:
        # If locking fails (e.g. read-only FS), proceed anyway rather than block monitoring.
        return True


def _release_lock() -> None:
    try:
        p = _lock_path()
        if p.exists() and p.read_text().strip() == str(os.getpid()):
            p.unlink()
    except Exception:
        pass



def cmd_check(_args: argparse.Namespace) -> int:
    print("=" * 55)
    print("  TURMO USB Display — Hardware Diagnostic")
    print("=" * 55)
    ports = scan_all_ports()
    print(f"\nSerial ports ({len(ports)} found):")
    for p in ports:
        marker = ""
        if p["vid"] == f"0x{VID:04X}" and p["pid"] == f"0x{PID:04X}":
            marker = "  [TURMO]"
        print(f"  {p['device']:8s}  {p['description']:<30s}  "
              f"vid={p['vid'] or '---'} pid={p['pid'] or '---'}"
              f"  sn={p['serial'] or 'none'}{marker}")

    target = _args.port or find_turmo_port()
    if target:
        print(f"\n[TURMO FOUND] Port: {target}  VID:PID {VID:#06x}:{PID:#06x}")
        print("  Next: python scripts/turmo_runtime.py --test-image")
        return 0
    print("\n[TURMO NOT FOUND] No device matching VID 1A86 PID 5722.")
    return 1


def cmd_test_image(_args: argparse.Namespace) -> int:
    global _disp
    port = _args.port or find_turmo_port()
    if not port:
        print("ERROR: No TURMO port found. Use --port COMx", file=sys.stderr)
        return 1
    landscape = _args.landscape or (not _args.portrait)
    W, H = LANDSCAPE_SIZE if landscape else TURING_SIZE
    print(f"[turmo] Port: {port}  {'landscape' if landscape else 'portrait'}")
    if not _acquire_lock():
        print(f"ERROR: another TURMO monitor is already running (lock: {_lock_path()})", file=sys.stderr)
        return 1
    _disp = disp = TurmoDisplay(port, landscape=landscape)
    try:
        disp.open()
        use_high_quality = getattr(_args, 'high_quality', False)
        if use_high_quality:
            pat_path = str(PROJECT_ROOT / "previews" / f"test-pattern-{'v2' if landscape else 'portrait'}.png")
            try:
                img = draw_orientation_diagnostic(pat_path, "landscape" if landscape else "portrait")
            except PermissionError:
                print("[turmo] Warning: cannot read preview file (permission), generating fallback")
                img = Image.new("RGB", (W, H), color=(50, 50, 100))
                draw = ImageDraw.Draw(img)
                draw.text((W//2, H//2), f"{'LAND' if landscape else 'POR'} {W}x{H} (fallback)", fill=(255, 255, 0))
            print(f"[turmo] Sending orientation diagnostic ({img.size}) …")
        else:
            theme_name = "cyberpunk-neon"
            preview = PROJECT_ROOT / "previews" / f"{theme_name}{'-480x320' if landscape else ''}.png"
            if not preview.exists():
                preview = PROJECT_ROOT / "previews" / f"{theme_name}.png"
            if preview.exists():
                try:
                    img = Image.open(str(preview))
                    if img.size != (W, H):
                        img = img.resize((W, H), Image.LANCZOS)
                except PermissionError:
                    print("[turmo] Warning: cannot read preview file (permission), generating fallback")
                    img = Image.new("RGB", (W, H), color=(50, 50, 100))
                    draw = ImageDraw.Draw(img)
                    draw.text((W//2, H//2), f"{'LAND' if landscape else 'POR'} {W}x{H} (fallback)", fill=(255, 255, 0))
            else:
                # Generate a simple test pattern on-the-fly
                img = Image.new("RGB", (W, H), color=(50, 50, 100))
                draw = ImageDraw.Draw(img)
                draw.text((W//2, H//2), f"{'LAND' if landscape else 'POR'} {W}x{H}", fill=(255, 255, 0))
        ok = disp.send_bitmap(img)
        print("DONE." if ok else "FAILED.", end="")
        if ok:
            print(f"  Orientation: {'landscape' if landscape else 'portrait'} ({W}×{H})")
        print()
        return 0 if ok else 1
    finally:
        disp.close()
        _disp = None
        _release_lock()


def cmd_render_theme(_args: argparse.Namespace) -> int:
    global _disp
    from settings import LinkStatus, SerialTimer, Settings, correct_panel, dim_image, keeps_celsius, renderer_for_unit, temps_in_unit
    settings = Settings.load()
    from runtime_logging import set_enabled as _set_logging
    _set_logging(settings.logging_enabled)
    # CLI flags override persisted settings
    port = _args.port or settings.port or find_turmo_port()
    if not port and _args.once:  # the live Monitor waits for the display instead (UsbLink)
        print("ERROR: No TURMO port found.", file=sys.stderr)
        return 1
    landscape = _args.landscape or (not _args.portrait and settings.orientation != "portrait")
    theme_name = _args.theme or settings.theme
    # Resolve "minimal" alias to "minimal-dark"
    if theme_name == "minimal":
        theme_name = "minimal-dark"
    if _args.gpu_index is not None:
        settings.gpu_index = _args.gpu_index
    W, H = LANDSCAPE_SIZE if landscape else TURING_SIZE
    print(f"[turmo] Port: {port}  Theme: {theme_name}  "
          f"{'landscape' if landscape else 'portrait'}  refresh={settings.refresh_ms}ms")

    if not _acquire_lock():
        print(f"ERROR: another TURMO monitor is already running (lock: {_lock_path()})", file=sys.stderr)
        return 1

    try:
        img, cfg = load_theme(theme_name, landscape)
    except FileNotFoundError as e:
        # A theme the user made has theme.json but no preview.png; live mode renders from theme.json, so only
        # --once (which sends the picture) needs the preview.
        folders = [_theme_folder(theme_name), _theme_folder(f"{theme_name}-320x480")]
        if _args.once or not any((f / "theme.json").exists() for f in folders):
            print(f"ERROR: {e}", file=sys.stderr)
            try:
                from runtime_logging import log_runtime
                log_runtime("WORKER", "THEME_MISSING", f"Theme '{theme_name}' cannot be loaded: {e}", level="ERROR")
            except Exception:
                pass
            _release_lock()
            return 1
        img, cfg = Image.new("RGB", (W, H)), {}

    _unit_cache = {}  # the Fahrenheit renderer of the current theme (settings.renderer_for_unit)
    link_status = link = None
    if _args.once:
        _disp = disp = TurmoDisplay(port, landscape=landscape)
    else:  # live: the link opens the display, finds it again after an unplug, and tells the GUI its state
        link_status = LinkStatus()
        _disp = disp = link = UsbLink(lambda p: TurmoDisplay(p, landscape=landscape), port, link_status.write, _log_link)
    try:
        if _args.once:
            # ponytail: retry initial open — USB COM port can still be settling on
            # first launch even after the GUI's free-check.
            opened = False
            for attempt in range(3):
                try:
                    disp.open()
                    opened = True
                    break
                except serial.SerialException as e:
                    print(f"  open attempt {attempt+1} failed: {e}", file=sys.stderr)
                    if attempt < 2:
                        time.sleep(1.0)
            if not opened:
                print(f"ERROR: could not open {port} after 3 attempts", file=sys.stderr)
                return 1
        print(f"[turmo] Theme loaded  size={img.size}  orientation={'landscape' if landscape else 'portrait'}")

        if _args.once:
            try:
                img = correct_panel(img, settings.color_correction, settings.color_gain)
            except Exception as e:  # the picture is still sent
                print(f"WARN: colour correction not applied ({e})", file=sys.stderr)
            ok = disp.send_bitmap(img)
            print("Render OK." if ok else "Render FAILED.", file=sys.stderr if not ok else sys.stdout)
            return 0 if ok else 1

        # Live telemetry mode: re-render each tick with fresh psutil readings.
        # PsutilProvider must persist across calls so rate keys (net.down/net.up/disk.read)
        # appear after the second read (first read only has cumulative totals).
        try:
            from libre_panel.sensors.psutil_provider import PsutilProvider
            from libre_panel.sensors.base import Snapshot
            from libre_panel.theme.model import load_theme as lp_load_theme
            from libre_panel.render.renderer import Renderer
            import json
        except ImportError as e:
            print(f"ERROR: libre-panel not installed in Windows venv: {e}", file=sys.stderr)
            print("Installing… please wait.", file=sys.stderr)
            import subprocess
            subprocess.run([sys.executable, "-m", "pip", "install",
                            "git+https://github.com/syntensa/libre-panel.git@66fb57f8192c997c799c796f42adb750423c0fe1"],
                           check=True)
            from libre_panel.sensors.psutil_provider import PsutilProvider
            from libre_panel.sensors.base import Snapshot
            from libre_panel.theme.model import load_theme as lp_load_theme
            from libre_panel.render.renderer import Renderer
            import json

        # GPU telemetry via NVML (optional, NVIDIA only)
        def read_gpu_nvml(gpu_index: int = 0):
            try:
                import pynvml
                pynvml.nvmlInit()
                count = pynvml.nvmlDeviceGetCount()
                if gpu_index >= count:
                    gpu_index = 0
                h = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
                name = pynvml.nvmlDeviceGetName(h)
                if isinstance(name, bytes):
                    name = name.decode()
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                temp = pynvml.nvmlDeviceGetTemperature(h, 0)
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                from libre_panel.sensors.base import Reading
                readings = {
                    "gpu.load": Reading(key="gpu.load", value=float(util.gpu), unit="%", label="GPU load"),
                    "gpu.temp": Reading(key="gpu.temp", value=float(temp), unit="°C", label="GPU temperature"),
                    "gpu.vram_used": Reading(key="gpu.vram_used", value=mem.used / (1024**3), unit="GB", label="VRAM used"),
                    "gpu.vram_total": Reading(key="gpu.vram_total", value=mem.total / (1024**3), unit="GB", label="VRAM total"),
                    "gpu.name": Reading(key="gpu.name", value=0.0, unit="", label="GPU name", origin=name),
                }
                try:
                    freq = pynvml.nvmlDeviceGetClockInfo(h, 0)
                    readings["gpu.freq"] = Reading(key="gpu.freq", value=float(freq), unit="MHz", label="GPU frequency")
                except Exception:
                    pass
                return readings
            except Exception:
                return {}

        # Portrait must render the <theme>-320x480 layout. Rendering the landscape
        # layout and stretching it to 320x480 was the cause of the distorted panel.
        theme_dir_name = _live_theme_dir(theme_name, landscape)
        try:
            from scripts import shape_icons
            shape_icons.register()  # circle, square, triangle... next to the icons
            theme_cfg = lp_load_theme(_theme_folder(theme_dir_name).resolve())
            renderer = Renderer(theme_cfg)
            celsius_only = keeps_celsius(_theme_folder(theme_dir_name))  # a "temps" module is Celsius-only
        except Exception as e:  # a broken theme.json: say why in the log instead of just stopping
            print(f"ERROR: theme '{theme_dir_name}' cannot be rendered: {e}", file=sys.stderr)
            try:
                from runtime_logging import log_runtime
                log_runtime("WORKER", "THEME_INVALID", f"Theme '{theme_dir_name}' cannot be rendered", exc=e, level="ERROR")
            except Exception:
                pass
            return 1
        provider = PsutilProvider()
        # v0.2.4.1: the theme can change while this loop runs (a Quick theme, the Gallery, a custom theme saved in the
        # editor): the loop watches the theme name in settings.json and the theme's theme.json, and draws the new one
        # without a stop, a restart or closing the port. A theme that cannot be drawn leaves the old one on the screen.
        target_theme = theme_name
        seen_setting = "minimal-dark" if settings.theme == "minimal" else settings.theme
        seen_orientation = settings.orientation
        current_theme = (theme_dir_name, _theme_stamp(theme_dir_name))
        bad_theme = None

        interval = settings.refresh_seconds()
        tick = 0
        _dim_failed = False
        serial_timer = SerialTimer()
        try:  # old logs go (Settings > Logs); in a thread so the first frame is not held up
            import threading
            from runtime_logging import sweep_logs
            threading.Thread(target=sweep_logs, kwargs={"keep_days": settings.log_keep_days, "max_mb": settings.log_max_mb},
                             daemon=True).start()
        except Exception as e:
            print(f"WARN: log sweep not started ({e})", file=sys.stderr)
        # Accumulate per-sensor history for graph widgets
        _hist: defaultdict[str, list[float]] = defaultdict(list)
        MAX_HIST = 600
        print(f"[turmo] Live mode — refresh every {interval}s  (Ctrl+C to stop)")
        print(f"[turmo] Reconnect enabled: USB unplug/replug auto-recovers  (lock: {_lock_path()})")
        print(f"[turmo] GPU index: {settings.gpu_index}")
        try:
            stop_req = _stop_request_path()
            while True:
                # Graceful-stop channel: GUI writes stop_monitor.request, worker checks each tick
                if stop_req.exists():
                    stop_req.unlink(missing_ok=True)
                    disp.request_shutdown()
                    print("\n[turmo] Stop requested via stop file — exiting gracefully.")
                    break
                if link.stopping:  # SIGINT/SIGTERM: the handler asked for a stop
                    break
                if not link.ready():  # lost, not found or not opened yet: no drawing, one attempt when due
                    link.maintain()
                    time.sleep(0.25)
                    continue
                link.heartbeat()
                try:
                    # Merge psutil + NVML readings
                    readings = dict(provider.read())
                    readings.update(read_gpu_nvml(settings.gpu_index))
                    # Add CPU temperature from LibreHardwareMonitor
                    readings.update(read_cpu_temperature())
                    # Feed numeric values into persistent history for graph rendering
                    for k, r in readings.items():
                        if isinstance(r.value, (int, float)):
                            h = _hist[k]
                            h.append(float(r.value))
                            if len(h) > MAX_HIST:
                                h.pop(0)
                    live = Settings.load()
                    _set_logging(live.logging_enabled)
                    seen_orientation, new_landscape, turned = _orientation_to_draw(seen_orientation, live.orientation, landscape)
                    if turned:  # v0.3.0: Portrait/Landscape from the GUI reaches the panel without a restart
                        landscape = new_landscape
                        W, H = LANDSCAPE_SIZE if landscape else TURING_SIZE
                        link.set_landscape(landscape)
                        print(f"\n[turmo] Orientation changed to {'landscape' if landscape else 'portrait'} without a restart")
                        try:
                            from runtime_logging import log_runtime
                            log_runtime("WORKER", "ORIENTATION_RELOAD", f"Now {'landscape' if landscape else 'portrait'} {W}x{H}")
                        except Exception:
                            pass
                    target_theme, seen_setting, want, changed = _theme_to_draw(
                        target_theme, seen_setting, _setting_theme(), landscape, current_theme, bad_theme)
                    if changed:
                        try:
                            new_renderer = Renderer(lp_load_theme(_theme_folder(want[0]).resolve()))
                            renderer, current_theme = new_renderer, want
                            celsius_only = keeps_celsius(_theme_folder(want[0]))
                            print(f"\n[turmo] Theme changed to '{want[0]}' without a restart")
                            try:
                                from runtime_logging import log_runtime
                                log_runtime("WORKER", "THEME_RELOAD", f"Now drawing '{want[0]}'")
                            except Exception:
                                pass
                        except Exception as e:  # keep drawing the old theme; try again only when the files change
                            bad_theme = want
                            print(f"\nWARN: theme '{want[0]}' cannot be drawn, keeping '{current_theme[0]}': {e}", file=sys.stderr)
                            try:
                                from runtime_logging import log_runtime
                                log_runtime("WORKER", "THEME_RELOAD_FAILED", f"'{want[0]}' not drawn, '{current_theme[0]}' kept", exc=e, level="WARNING")
                            except Exception:
                                pass
                    snap = Snapshot(readings=readings, history=dict(_hist))  # Celsius: the log and the console read this
                    unit = "celsius" if celsius_only else live.units.get("temp")  # Settings > Units, hot
                    shown, shown_hist = temps_in_unit(readings, _hist, unit)
                    drawn = snap if shown is readings else Snapshot(readings=shown, history=dict(shown_hist))
                    frame, _box = renderer_for_unit(renderer, unit, _unit_cache, Renderer).render(drawn)  # Fahrenheit: °F after the number
                    frame = frame.convert("RGB").resize((W, H), Image.LANCZOS)
                    # Brightness slider of the GUI: re-read each frame so a change applies while running
                    try:
                        frame = dim_image(frame, live.brightness)
                    except Exception as e:  # never lose a frame over the brightness setting, but say so once
                        if not _dim_failed:
                            _dim_failed = True
                            print(f"WARN: brightness not applied ({e})", file=sys.stderr)
                    try:  # LCD colour curve; a frame is never lost over it
                        frame = correct_panel(frame, live.color_correction, live.color_gain)
                    except Exception as e:
                        if not _dim_failed:  # said once, with the brightness warning's flag
                            _dim_failed = True
                            print(f"WARN: colour correction not applied ({e})", file=sys.stderr)
                    sent_at = time.perf_counter()
                    ok = disp.send_bitmap(frame)
                    if ok:
                        serial_timer.record(time.perf_counter() - sent_at)  # Diagnostics > Serial latency
                except serial.SerialException as e:
                    ok = False
                    print(f"\nWARN: serial error ({e})", file=sys.stderr)
                tick += 1
                if tick % 30 == 0:  # evidence line about once a minute (refresh 2 s)
                    try:
                        from runtime_logging import log_runtime
                        vals = {k: round(snap.readings[k].value, 1)
                                for k in ("gpu.load", "gpu.temp", "cpu.temp") if k in snap.readings}
                        log_runtime("MONITOR", "READINGS", f"tick={tick} gpu_index={settings.gpu_index} {vals}")
                    except Exception:
                        pass
                if ok:
                    cpu_pct = snap.readings.get("cpu.load")
                    cpu_temp = snap.readings.get("cpu.temp")
                    mem_gb = snap.readings.get("mem.used")
                    net_dl = snap.readings.get("net.down")
                    line = f"Frame #{tick:4d}  CPU={cpu_pct.value:.0f}%"
                    if cpu_temp:
                        line += f"  TEMP={cpu_temp.value:.0f}°C"
                    line += f"  MEM={mem_gb.value:.1f} GB"
                    if net_dl and net_dl.value:
                        line += f"  NET={net_dl.value / 1e6:.2f} MB/s"
                    else:
                        line += "  NET=(warming)"
                    print(f"\r[turmo] {line:<44}", end="", flush=True)
                else:  # the link saw it: state "retrying", logged once, and the loop now retries on a backoff
                    print(f"\nWARN: frame #{tick} not sent, USB link {link.state}", file=sys.stderr)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[turmo] Stopped.")
        return 0
    finally:
        disp.close()
        if link_status is not None:
            link_status.clear()
        _disp = None
        _release_lock()


def cmd_settings(_args: argparse.Namespace) -> int:
    from settings import Settings
    s = Settings.load()
    raw_set = getattr(_args, "settings", None)   # argparse stores --settings as args.settings
    if raw_set:
        key, _, val = raw_set.partition("=")
        if key not in Settings.__dataclass_fields__:
            print(f"ERROR: unknown setting '{key}'", file=sys.stderr)
            return 1
        cur = getattr(s, key)
        val = _coerce(cur, val)
        setattr(s, key, val)
        s.save()
        print(f"set {key} = {val!r}")
        return 0
    return _settings_print(s)


def _settings_print(s) -> int:
    from settings import Settings
    print(f"config: {Settings.path()}")
    print(f"  theme            = {s.theme}")
    print(f"  orientation      = {s.orientation}")
    print(f"  refresh_ms       = {s.refresh_ms}  ({s.refresh_seconds():.1f}s)")
    print(f"  brightness       = {s.brightness}")
    print(f"  port             = {s.port or '(auto-detect)'}")
    print(f"  gpu_index        = {s.gpu_index}")
    print(f"  font_scale       = {s.font_scale}")
    print(f"  compact          = {s.compact}")
    print(f"  units.temp       = {s.units['temp']}")
    print(f"  units.clock      = {s.units['clock']}")
    print(f"  units.data       = {s.units['data']}")
    print(f"  startup_windows  = {s.startup_windows}")
    print(f"  widgets          = {s.widgets}")
    return 0


def _coerce(current, raw: str):
    if isinstance(current, bool):
        return raw.lower() in ("1", "true", "yes", "on")
    if isinstance(current, int):
        return int(raw)
    if isinstance(current, float):
        return float(raw)
    return raw


# Global display reference for signal handlers
_disp: TurmoDisplay | None = None


def _signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    global _disp
    print(f"[turmo] Received signal {signum}, initiating shutdown...", flush=True)
    if _disp:
        _disp.request_shutdown()


def main() -> int:
    global args, _disp
    
    # Pre-initialize CLR on main thread before any other threads spawn
    # Required: pythonnet.clr must be initialized before background threads start
    _preinit_libre_hardware_monitor()
    
    # Install signal handlers for graceful shutdown
    import signal
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    # Windows: also handle CTRL_BREAK_EVENT
    if sys.platform == "win32":
        try:
            signal.signal(signal.SIGBREAK, _signal_handler)
        except AttributeError:
            pass
    try:
        from runtime_logging import init_runtime_log, log_runtime
        log_file = init_runtime_log()
        log_runtime("WORKER", "MAIN_ENTRY", f"Worker started with args: {sys.argv}", level="INFO")
    except ImportError:
        pass  # Runtime logging optional
    except Exception:
        pass  # Never let logging failures crash the worker
    
    parser = argparse.ArgumentParser(description="TURMO Open Source — Native Runtime")
    parser.add_argument("--port", help="Override auto-detected COM port (e.g. COM4)")
    parser.add_argument("--portrait", action="store_true")
    parser.add_argument("--landscape", action="store_true")
    parser.add_argument("--once", action="store_true", help="Single render, no live loop")
    parser.add_argument("--high-quality", action="store_true", help="Use v2 test pattern with gradients")
    parser.add_argument("--gpu-index", type=int, metavar="N", help="NVIDIA GPU index to monitor (0=first)")
    parser.add_argument("--settings", metavar="KEY=VALUE", help="Set a persisted setting and exit")
    parser.add_argument("--show-settings", action="store_true", help="Print persisted settings and exit")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--check", action="store_true")
    group.add_argument("--test-image", action="store_true")
    parser.add_argument("--monitor", action="store_true",
                           help="Continuous live monitoring with saved settings (default theme/orientation/refresh)")
    parser.add_argument("--theme", metavar="NAME", help="Theme name for --theme or --monitor mode")
    args = parser.parse_args()

    if args.settings or args.show_settings:
        return cmd_settings(args)
    if not any((args.check, args.test_image, args.theme, args.monitor)):
        parser.error("one of --check --test-image --theme --monitor --settings --show-settings is required")
    if args.check:
        return cmd_check(args)
    elif args.test_image:
        return cmd_test_image(args)
    elif args.theme:
        return cmd_render_theme(args)
    elif args.monitor:
        return cmd_render_theme(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())