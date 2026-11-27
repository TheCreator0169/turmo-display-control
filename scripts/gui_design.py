"""Design tokens and pure helpers for the v0.2.0 GUI (dark sidebar, dashboard, sparklines).

Kept free of Tk so the logic can be tested without opening a window. The palette comes
from design/v0.2.0/tokens.css; the widgets that use it live in turmo_app_enhanced.py.
"""

import re

PALETTE = {
    "bg0": "#0B0E14",   # app background
    "bg1": "#12161F",   # sidebar, title and panels
    "bg2": "#1A2029",   # cards
    "bg3": "#232B36",   # hover / active surface
    "line": "#2C3540",  # hairline borders
    "line2": "#38414E", # stronger dividers, button and input borders
    "text": "#E9EDF3",
    "muted": "#8A93A0",
    "dim": "#5A6370",
    "cyan": "#22D3EE",  # accent
    "blue": "#3B82F6",
    "violet": "#8B5CF6",
    "green": "#22C55E",
    "warn": "#F59E0B",
    "crit": "#EF4444",
    "on_accent": "#04121A",  # text on a cyan fill
}

DARK = dict(PALETTE)
# The light look (DESIGN.md: #F4F6FA background, #FFFFFF cards, #DDE3EC hairlines). Text and the text on
# accent fills are the inverse of the dark look; the accents are a step darker so they read on white.
LIGHT = {
    "bg0": "#F4F6FA", "bg1": "#FFFFFF", "bg2": "#FFFFFF", "bg3": "#E8EDF4",
    "line": "#DDE3EC", "line2": "#C9D2DE",
    "text": "#0F172A", "muted": "#5B6675", "dim": "#8A94A3",
    "cyan": "#0891B2", "blue": "#2563EB", "violet": "#7C3AED",
    "green": "#16A34A", "warn": "#D97706", "crit": "#DC2626",
    "on_accent": "#FFFFFF",
}


def set_mode(mode):
    """Switch the shared PALETTE (every module holds this same dict) to "light" or "dark"; widgets read it
    when they are built, so the window has to be built again afterwards."""
    PALETTE.update(LIGHT if mode == "light" else DARK)


def mix(top, base, share):
    """The colour `share` (0..1) of `top` over `base`, both "#RRGGBB": CSS color-mix(top share%, base)."""
    t = [int(top[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(base[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * share + y * (1 - share)):02X}" for x, y in zip(t, b))


SIDEBAR_W = 252  # --sidebar-w at the 1440 px reference

# Size of the floating window (v0.2.3): it cannot be dragged to another size, only maximised (full look) or not at all
# (minimal look, minimal_ui.SIZE). Every page fits it, and the maximised window, without a scroll bar, except Gallery
# and Diagnostics, whose lists are long.
FULL_SIZE = (1200, 760)


def window_size(base, dpi, area=None):
    """Pixels for a window designed at `base` px at 96 dpi: grown with the scaling (the fonts grow, so the pages
    need the room), but never beyond the work area `area` = (width, height) minus room for the title bar and the
    edges, so a small laptop screen still shows the whole window. Pure, for tests."""
    f = max(1.0, dpi / 96)
    w, h = round(base[0] * f), round(base[1] * f)
    if area:
        w, h = min(w, area[0] - 16), min(h, area[1] - 48)
    return w, h

# Sidebar entries, in the order of the notebook tabs they open.
SIDEBAR_ITEMS = ("Dashboard", "Monitor", "Live Preview", "Gallery", "Theme Editor",
                 "Sensors & Graphs", "Settings", "Diagnostics", "About")

# Section labels of the design's sidebar; the entries of all groups, in order, are SIDEBAR_ITEMS.
SIDEBAR_GROUPS = (
    ("MONITORING", ("Dashboard", "Monitor", "Live Preview")),
    ("DESIGN", ("Gallery", "Theme Editor", "Sensors & Graphs")),
    ("SYSTEM", ("Settings", "Diagnostics", "About")),
)


LINK_LABELS = {"starting": ("Connecting…", "busy"), "retrying": ("Reconnecting…", "busy"), "busy": ("Busy", "busy"), "not_found": ("Not found", "off")}


def device_status(port_text, monitor_running, link_state=None):
    """(label, level) for the device chip and the dashboard state from the port text and Monitor state.

    level is "ok", "busy" or "off". The port text is the Monitor tab's: "COM4 ✓", "Busy / In Use ⚠", ..."""
    if monitor_running:
        # the Monitor's own view of the USB link wins while it is down (v0.3.0): it keeps retrying by itself
        return LINK_LABELS.get(link_state, ("Monitor running", "ok"))
    if "✓" in port_text:
        return "Connected", "ok"
    if "Busy" in port_text:
        return "Busy", "busy"
    return "Disconnected", "off"


def device_chip_text(port_text, level, link_state=None):
    """Second line of the sidebar device chip: the device and its port, or why there is none."""
    if link_state in LINK_LABELS:
        return "Waiting for the display"
    if level == "ok":
        if "✓" not in port_text:  # Monitor running while the port text says Busy / Not found
            return "Monitor running"
        return "TURMO · " + port_text.split()[0]
    return "COM port busy" if level == "busy" else "No device"

# Quick theme chips on the dashboard: (theme folder name, label, dot colour).
QUICK_THEMES = (
    ("cyberpunk-neon", "Cyberpunk", "#ff2bd6"),
    ("futuristic-hud", "Futuristic", "#00e5ff"),
    ("matrix-terminal", "Matrix", "#00ff41"),
    ("hardware-dashboard", "Hardware", "#4da3ff"),
    ("minimal-dark", "Minimal", "#e8e8ec"),
    ("rgb-gaming", "RGB", "#8b5cf6"),
)

NO_VALUE = "—"  # em dash, shown while a sensor has no reading yet


RATE = "rate"  # a format name, not a format string: a data rate written with the unit that fits it


def format_rate(value):
    """Bytes per second as B/s, KB/s, MB/s or GB/s (steps of 1024, like the LCD's {value:bytes}/s):
    the unit grows with the number, so 15793 B/s reads 15.4 KB/s."""
    value = max(float(value), 0.0)
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if value < 1024 or unit == "GB/s":
            return f"{value:.0f} {unit}" if unit == "B/s" or value >= 100 else f"{value:.1f} {unit}"
        value /= 1024


def temp_in(value, unit):
    """A temperature read in Celsius, in the unit of Settings > Units ("celsius" or "fahrenheit")."""
    return value * 9 / 5 + 32 if unit == "fahrenheit" else value


def metric_text(readings, key, fmt, temp_unit="celsius"):
    """Text for one metric from a readings dict (values are Reading objects or plain numbers).
    A temperature sensor (key ending ".temp") is shown in `temp_unit`; the readings stay in Celsius.

    Returns NO_VALUE when the sensor is missing, empty, or not a number."""
    if not readings or key not in readings:
        return NO_VALUE
    value = getattr(readings[key], "value", readings[key])
    if value is None or isinstance(value, str):
        return NO_VALUE
    if key.endswith(".temp") and temp_unit == "fahrenheit" and isinstance(value, (int, float)):
        value, fmt = temp_in(value, temp_unit), fmt.replace("°C", "°F")
    try:
        return format_rate(value) if fmt == RATE else fmt.format(value=float(value))
    except (TypeError, ValueError):
        return NO_VALUE


def sparkline_points(values, width, height, pad=2):
    """Canvas coordinates (x0, y0, x1, y1, ...) of a 0..100 history, scaled into width x height.

    Fewer than two numeric samples give no line (an empty list)."""
    samples = [v for v in values if v is not None]
    if len(samples) < 2:
        return []
    step = (width - 2 * pad) / (len(samples) - 1)
    points = []
    for i, v in enumerate(samples):
        clamped = max(0.0, min(100.0, float(v)))
        x = pad + i * step
        y = pad + (height - 2 * pad) * (1.0 - clamped / 100.0)
        points.extend((round(x, 1), round(y, 1)))
    return points

def scale_history(values, top=None):
    """History scaled to 0..100 for sparkline_points: by `top` when given, else by its own maximum."""
    samples = [float(v) for v in values if v is not None]
    peak = top if top else max(samples + [1e-9])
    return [v / peak * 100.0 for v in samples]


# Segoe MDL2 Assets glyph for each sidebar entry (checked against the font).
SIDEBAR_GLYPHS = {
    "Dashboard": "",      # home
    "Monitor": "",        # monitor screen
    "Live Preview": "",   # eye
    "Theme Editor": "",   # pencil
    "Settings": "",       # gear
    "Gallery": "\uE790",        # palette
    "Sensors & Graphs": "\uE9D2",  # area chart
    "Diagnostics": "\uE9F9",    # document with chart
    "About": "",          # info
}

ICON_FONT = "Segoe MDL2 Assets"
TEXT_FONTS = ("Segoe UI Variable Text", "Segoe UI")
SEMIBOLD_FONTS = ("Segoe UI Semibold", "Segoe UI Variable Display", "Segoe UI")


def pick_family(available, preferred, fallback="TkDefaultFont"):
    """First preferred family that is installed; the Tk default otherwise."""
    for name in preferred:
        if name in available:
            return name
    return fallback


# Gallery categories: folder name -> category (the eight official themes).
THEME_CATEGORIES = {
    "cyberpunk-neon": "Neon",
    "rgb-gaming": "Neon",
    "minimal-dark": "Clean",
    "futuristic-hud": "HUD",
    "hardware-dashboard": "HUD",
    "matrix-terminal": "Terminal",
    "clean-white": "Light",
    "custom-blank-canvas": "Custom",
}
GALLERY_CATEGORIES = ("All", "Neon", "Clean", "HUD", "Terminal", "Light", "Custom")


def is_custom_theme(slug):
    """True for a theme the user made (a copy or a new theme); the official ones are in THEME_CATEGORIES."""
    return slug not in THEME_CATEGORIES


EDITABLE_BUILTIN = ("custom-blank-canvas",)  # official, but named Custom: it is meant to be edited


def is_editable_theme(slug):
    """True for the user's themes and for the Custom Blank Canvas; every other official theme is copy-only."""
    return is_custom_theme(slug) or slug in EDITABLE_BUILTIN


def wrap_words(text, measure, width):
    """Greedy word wrap; `measure(str)` gives the width in pixels."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}" if cur else word
        if cur and measure(trial) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def collapse_description(text, measure, width, link, max_lines=2):
    """(short_lines, all_lines). short_lines is None when the text fits in max_lines; otherwise it is the
    first max_lines lines, the last one cut so that '...' and the `link` word still fit on it."""
    lines = wrap_words(text, measure, width)
    if len(lines) <= max_lines:
        return None, lines
    last = lines[max_lines - 1].split()
    while last and measure(" ".join(last) + "… " + link) > width:
        last.pop()
    return lines[:max_lines - 1] + [" ".join(last) + "…"], lines


def unique_theme_name(taken, base):
    """`base`, or base-2, base-3... the first name for which taken(name) is False."""
    name, n = base, 2
    while taken(name):
        name, n = f"{base}-{n}", n + 1
    return name


def pick_topmost(boxes, x, y, pad=3):
    """The key of the last (topmost) box that holds the point (x, y), grown by `pad` pixels so that small things
    are easy to hit; None if there is none. `boxes` is a list of (key, (x1, y1, x2, y2)) in drawing order."""
    for key, (x1, y1, x2, y2) in reversed(boxes):
        if x1 - pad <= x <= x2 + pad and y1 - pad <= y <= y2 + pad:
            return key
    return None


def order_themes(slugs, saved=None):
    """The gallery order: the names in `saved` first, in that order, then the others alphabetically."""
    have = set(slugs)
    first = []
    for slug in saved or []:
        if slug in have and slug not in first:
            first.append(slug)
    return first + sorted(have.difference(first))


def theme_category(slug, declared=None):
    """The gallery category of a theme: the official ones are listed in THEME_CATEGORIES; a theme the user made may
    declare one in its theme.json ("category"), Custom otherwise (or when the declared name is not a category)."""
    if slug in THEME_CATEGORIES:
        return THEME_CATEGORIES[slug]
    match = next((c for c in GALLERY_CATEGORIES[1:] if c.lower() == str(declared or "").strip().lower()), None)
    return match or "Custom"


def filter_themes(slugs, category="All", query="", order=None, declared=None):
    """Theme names in a category whose name contains the search text (case-insensitive), in the user's order
    (`order`, see order_themes) or alphabetically. `declared` maps a custom theme to the category in its theme.json."""
    needle = query.strip().lower()
    shown = []
    for slug in order_themes(slugs, order):
        if category != "All" and theme_category(slug, (declared or {}).get(slug)) != category:
            continue
        if needle and needle not in slug.lower():
            continue
        shown.append(slug)
    return shown


MOVE_ACTIONS = ("start", "left", "right", "end")


def move_theme(order, shown, slug, action):
    """`order` (every theme) with `slug` moved inside the cards on screen (`shown`, a subset of `order` in
    order): to the start, one step left or right, or to the end of what is shown. The cards that are not
    shown keep their places. An impossible move returns `order` unchanged."""
    if slug not in shown or action not in MOVE_ACTIONS:
        return list(order)
    i = shown.index(slug)
    j = {"start": 0, "left": i - 1, "right": i + 1, "end": len(shown) - 1}[action]
    if j == i or not 0 <= j < len(shown):
        return list(order)
    moved = list(shown)
    moved.insert(j, moved.pop(i))
    slots = sorted(order.index(s) for s in shown)
    result = list(order)
    for slot, name in zip(slots, moved):
        result[slot] = name
    return result


# Sensors listed on the Sensors & Graphs tab, with how each value is shown.
SENSOR_FORMATS = {
    "cpu.load": "{value:.0f}%",
    "cpu.temp": "{value:.0f}\u00b0C",
    "gpu.load": "{value:.0f}%",
    "gpu.temp": "{value:.0f}\u00b0C",
    "mem.load": "{value:.0f}%",
    "mem.used": "{value:.1f} GB",
    "net.down": RATE,
    "net.up": RATE,
}


# Names shown for the sensors on the Sensors & Graphs page.
SENSOR_NAMES = {
    "cpu.load": "CPU load", "cpu.temp": "CPU temp", "gpu.load": "GPU load", "gpu.temp": "GPU temp",
    "mem.load": "RAM %", "mem.used": "RAM used", "net.down": "Network \u2193", "net.up": "Network \u2191",
}


# Sensors a graph can use that the page does not list at first: they get a row in Active sensors once a graph uses them.
EXTRA_SENSORS = {"gpu.freq": ("GPU clock", "{value:.0f} MHz")}
LOCKED_GRAPHS = ("cpu-graph", "gpu-graph", "ram-graph")  # the graphs every theme starts with: they cannot be removed


def sensor_name(key):
    return SENSOR_NAMES.get(key) or EXTRA_SENSORS.get(key, (key,))[0]


def sensor_format(key):
    return SENSOR_FORMATS.get(key) or EXTRA_SENSORS.get(key, (None, "{value:.1f}"))[1]


# --- Diagnostics: the runtime log as entries -------------------------------------------------------
LOG_HEAD = re.compile(r"^\[\d{4}-\d{2}-\d{2}T(\d{2}:\d{2}:\d{2})[^\]]*\]\s+\[(\w+)\]\s+(.*)$")
LOG_NOISE = re.compile(r"PID=\d+ TID=\d+ Thread=.*?(?=Component=)")
LOG_BAD = ("ERROR", "CRITICAL")
LOG_WARN = ("WARN", "WARNING")


def parse_log(lines, limit=200):
    """Runtime log lines as (time, level, message) entries, oldest first. Continuation lines (a traceback)
    are joined to a WARN or ERROR entry and dropped from the others. Lines that start no entry are skipped."""
    entries = []
    for line in lines:
        m = LOG_HEAD.match(line)
        if m:
            text = LOG_NOISE.sub("", m.group(3)).strip()
            c = re.match(r"Component=(\S+) Event=(\S+)\s*(.*)", text)
            if c:
                text = f"{c.group(1)} \u00b7 {c.group(2)} {c.group(3)}".strip()
            entries.append([m.group(1), m.group(2).upper(), text])
        elif entries and line.strip() and entries[-1][1] in LOG_BAD + LOG_WARN:
            entries[-1][2] += " | " + line.strip()
    return [(t, lvl, msg[:200]) for t, lvl, msg in entries][-limit:]


def log_kind(level):
    """"err", "warn" or "info": how an entry is coloured."""
    return "err" if level in LOG_BAD else "warn" if level in LOG_WARN else "info"


def recent_errors(entries, count=3):
    """The last `count` error entries, newest last."""
    return [e for e in entries if log_kind(e[1]) == "err"][-count:]


PAWNIO_URL = "https://pawnio.eu"
_PAWNIO_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO"


def pawnio_version():
    """Installed PawnIO driver version ("" if it does not say), None when it is not installed."""
    try:
        import winreg
    except ImportError:
        return None
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _PAWNIO_KEY, 0, winreg.KEY_READ | view) as key:
                try:
                    return str(winreg.QueryValueEx(key, "DisplayVersion")[0])
                except OSError:
                    return ""
        except OSError:
            continue
    return None


def pawnio_state(version):
    """'missing', 'old' (major below 2: the CPU temperature needs 2 or newer) or 'ok'."""
    if version is None:
        return "missing"
    m = re.match(r"\d+", version)
    return "old" if m and int(m.group()) < 2 else "ok"
