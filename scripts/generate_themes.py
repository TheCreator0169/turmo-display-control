#!/usr/bin/env python3
"""Generate the 8 TURMO-OpenSource themes as libre-panel-theme/1 JSON for turing-3.5 (480x320).

Each theme is a dict; the same generator emits landscape (480x320) and portrait
(320x480) variants by transposing the widget grid. Run:  python scripts/generate_themes.py
Writes themes/<slug>/theme.json for every theme.
"""
import json, os, shutil, sys
from functools import partial

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
THEMES_DIR = os.path.join(ROOT, "themes")
sys.path.insert(0, HERE)
from app_version import TURMO_VERSION  # noqa: E402

W, H = 480, 320  # landscape canvas (turing-3.5 native portrait is 320x480)


def palette(**kw):
    p = dict(
        bg="#000000", bg2="#0a0a0f", card="#14141a", card2="#1d1d26",
        edge="#2a2a35", text="#f2f2f7", muted="#9a9aa6", dim="#5c5c68",
        accent="#00e5ff", accent_deep="#0091b8", violet="#7c4dff",
        violet_deep="#5e2fd0", green="#00ff9d", pink="#ff2bd6",
        warn="#ffb020", crit="#ff3b5c", line="#2a2a35", track="#1d1d26",
        text2="#dcdce4", text3="#b8b8c2",
    )
    p.update(kw)
    return p


def theme(name, author, description, pal, font, style, widgets, display=None):
    d = display or {"model": "turing-3.5", "orientation": "landscape", "width": W, "height": H}
    base = {
        "format": "libre-panel-theme/1",
        "name": name,
        "author": author,
        "license": "CC0-1.0",
        "description": description,
        "display": d,
        "palette": pal,
        "font": font,
        "background": {"color": "@bg2", "image": None},
        "refresh_ms": 1000,
        "animation": {"smoothing_ms": 450},
        "grid": {"columns": 12, "rows": 8, "gap": 8, "margin": 10},
        "style": {
            "card": style.get("card", "flat"),
            "radius": style.get("radius", 10),
            "glow": style.get("glow", 0.4),
            "backdrop": style.get("backdrop", "flat"),
            "display_font": style.get("display_font", "builtin:Barlow-Bold"),
            "text_font": style.get("text_font", "builtin:Barlow-Medium"),
        },
        "widgets": widgets,
    }
    # per-widget finish defaults to lit for glowing themes
    if style.get("card") == "flat" and style.get("glow", 0) > 0:
        for w in widgets:
            if w.get("type") in ("gauge", "graph", "bar", "metric", "clock", "text") and "finish" not in w:
                w["finish"] = "lit"
    return base


# --- widget helpers ---------------------------------------------------------

def rw(type_, id_, **kw):
    w = {"type": type_, "id": id_}
    w.update(kw)
    return w


def ring_metric(cid, sx, x, y, size, label, color, font="builtin:Barlow-Bold",
                icon=None, value_fmt="{value:.0f}%"):
    """A gauge ring + centered value + label, inside a card.

    Layout (card is (x-8, y-8, size+16, size+34)):
      - ring centered in card
      - value centered inside the ring
      - label centered below the ring (no icon overlap)
      - small icon in the card's top-right corner (fixed position, never overlaps text)
    """
    cx = x + size // 2
    ws = [
        rw("rect", f"{cid}-card", x=x - 8, y=y - 8, w=size + 16, h=size + 34,
           color="@card", radius=12, outline="@edge", locked=True),
        rw("gauge", f"{cid}-ring", x=x, y=y, w=size, h=size, sensor=sx,
           thickness=10, color=color, background="@track", ticks=0,
           glow=0.5, glow_radius=6, smooth=True,
           color_rules=[{"above": 90, "color": "@crit"}]),
        rw("metric", f"{cid}-value", x=cx - 40, y=y + size // 2 - 16, w=80, h=32,
           sensor=sx, format=value_fmt, font_size=26, color="@text",
           align="center", font=font, tabular=True, smooth=True),
        rw("text", f"{cid}-label", x=cx - 40, y=y + size + 4, w=80, h=16,
           text=label, font_size=11, color="@muted", align="center",
           letter_spacing=2.4),
    ]
    if icon:
        # icon in the card's top-right corner: fixed, no overlap with label/value
        ws.append(rw("icon", f"{cid}-icon", x=x + size - 12, y=y - 4, icon=icon,
                     size=14, color=color, stroke=2))
    return ws


def net_updown(x, y, w=140):
    """DOWN/UP rates: small label left, value left-aligned at a fixed x.

    The metric widget ignores w/h, so align=right has no box to align against
    (text renders at its natural position) — always left-align the value.
    Each row is a clean 2-column layout: label (left) + value (fixed offset).
    """
    return [
        rw("text", "net-down-label", x=x, y=y, w=44, h=18, text="DOWN",
           font_size=9, color="@muted", align="left", letter_spacing=1.6),
        rw("metric", "net-down", x=x + 46, y=y, sensor="net.down",
           format="{value:rate} {value:rate_unit}", font_size=13, color="@green",
           align="left", font="builtin:Barlow-SemiBold", tabular=True,
           smooth=True),
        rw("text", "net-up-label", x=x, y=y + 22, w=44, h=18, text="UP",
           font_size=9, color="@muted", align="left", letter_spacing=1.6),
        rw("metric", "net-up", x=x + 46, y=y + 22, sensor="net.up",
           format="{value:rate} {value:rate_unit}", font_size=13, color="@pink",
           align="left", font="builtin:Barlow-SemiBold", tabular=True,
           smooth=True),
    ]


def history_graph(y=250, h=48, x=12, w=456, sensor="cpu.load"):
    """Compact CPU history strip: thin line, subtle fill, low glow."""
    return rw("graph", "history", x=x, y=y, w=w, h=h, sensor=sensor,
              history=120, min=0, max=100, color="@accent", fill=True,
              fill_fade=True, smooth=True, line_width=1, grid=1,
              grid_color="@line", glow=0.25, glow_radius=4, fill_alpha=0.22)


def header_clock():
    return [
        rw("clock", "clock", x=14, y=2, format="%H:%M", font_size=34,
           color="@text", font="builtin:Barlow-Bold", glow=0.2),
        rw("clock", "date", x=16, y=42, format="%a %d %b", font_size=12,
           color="@muted", tabular=False),
    ]


# --- dashboard skeleton shared by several themes ----------------------------

def dashboard(pal, font, style, accent_hex, net_color="#00ff9d", mono=False,
              show_temps=True, title="TURMO"):
    """Full 480x320 hardware dashboard: header (clock+net+disk), 3 rings, temps, graph.

    Layout (landscape 480x320):
      header  y=0..76   clock (left) | title (center) | net/down/up + disk (right)
      cards   y=84..236 three 118px rings (CPU/GPU/RAM)
      temps   y=240..258 label LEFT + value at fixed offset (never overlap)
      graph   y=264..312 compact CPU history strip
    """
    mono_font = "builtin:JetBrainsMono-Bold" if mono else "builtin:Barlow-Bold"
    widgets = [
        rw("rect", "backdrop", x=0, y=0, w=W, h=H, color="@bg2", color2="@bg",
           locked=True),
        rw("clock", "clock", x=14, y=4, format="%H:%M", font_size=32,
           color="@text", font="builtin:Barlow-Bold", glow=0.2),
        rw("clock", "date", x=16, y=40, format="%a %d %b", font_size=12,
           color="@muted", tabular=False),
        rw("text", "title", x=210, y=16, w=120, h=16, text=title, font_size=11,
           color="@dim", align="left", letter_spacing=3.0),
    ]
    # right header: net down/up + disk bar
    widgets += net_updown(342, 10, w=138)
    widgets += [
        rw("text", "disk-label", x=342, y=54, w=44, h=14, text="DISK",
           font_size=9, color="@muted", align="left", letter_spacing=1.6),
        rw("bar", "disk-bar", x=388, y=56, w=80, h=6, sensor="disk.load",
           color="@green", background="@track", radius=1, segments=16,
           segment_gap=2, glow=0.4, glow_radius=5,
           color_rules=[{"above": 90, "color": "@crit"}]),
    ]
    # 3 rings across, y=84, each 118x118
    widgets += ring_metric("cpu", "cpu.load", 14, 84, 118, "CPU", "@accent",
                           icon="cpu")
    widgets += ring_metric("gpu", "gpu.load", 176, 84, 118, "GPU", net_color,
                           icon="gpu")
    widgets += ring_metric("mem", "mem.load", 338, 84, 118, "RAM", "@violet",
                           icon="ram")
    # temps row under rings: label LEFT (muted) + value at fixed offset (bold).
    # NEVER place the label and value at the same x/y — that overlaps and is
    # the exact "corrupted lower text" bug. Label at card-left, value offset right.
    if show_temps:
        widgets += [
            rw("text", "cpu-temp-label", x=14, y=244, w=44, h=16, text="CPU",
               font_size=9, color="@muted", align="left", letter_spacing=1.6),
            rw("metric", "cpu-temp", x=56, y=242, sensor="cpu.temp",
               format="{value:.0f}°", font_size=15, color="@warn",
               font=mono_font, tabular=True, smooth=True),
            rw("text", "gpu-temp-label", x=176, y=244, w=44, h=16, text="GPU",
               font_size=9, color="@muted", align="left", letter_spacing=1.6),
            rw("metric", "gpu-temp", x=218, y=242, sensor="gpu.temp",
               format="{value:.0f}°", font_size=15, color="@warn",
               font=mono_font, tabular=True, smooth=True),
            rw("text", "mem-used-label", x=338, y=244, w=44, h=16, text="USED",
               font_size=9, color="@muted", align="left", letter_spacing=1.6),
            rw("metric", "mem-used", x=380, y=242, sensor="mem.used",
               format="{value:.1f} GB", font_size=15, color="@violet",
               font=mono_font, tabular=True, smooth=True),
        ]
    # bottom graph
    widgets.append(history_graph(y=264, h=48))
    return widgets


THEMES = [
    dict(
        slug="cyberpunk-neon", name="Cyberpunk Neon", author="TURMO-OpenSource",
        desc="Neon magenta/cyan on deep purple-black. Glowing rings and a lit graph for the cyberpunk look.",
        pal=palette(bg="#0a0118", bg2="#12002e", card="#1a0b33", card2="#241244",
                    edge="#ff2bd644", text="#f5f3ff", muted="#b8a8e8",
                    accent="#ff2bd6", accent_deep="#c21ba8", violet="#7c4dff",
                    green="#00ffa3", pink="#ff2bd6", line="#3a1f66",
                    track="#241244"),
        font="builtin:Barlow-Medium",
        style=dict(card="outline", radius=14, glow=0.8, display_font="builtin:Barlow-Bold",
                   text_font="builtin:Barlow-Medium"),
        mono=False, title="TURMO // CYBER",
    ),
    dict(
        slug="minimal-dark", name="Minimal Dark", author="TURMO-OpenSource",
        desc="Near-black, quiet grays, one white accent. Thin rings, no glow — the calmest look.",
        pal=palette(bg="#0d0d0f", bg2="#111114", card="#17171b", card2="#1e1e23",
                    edge="#2a2a31", text="#ececef", muted="#9a9aa2",
                    accent="#e8e8ec", accent_deep="#b8b8c0", violet="#6e6e78",
                    green="#7ee2a8", pink="#e07a9a", line="#26262c",
                    track="#1e1e23"),
        font="builtin:Barlow-Medium",
        style=dict(card="outline", radius=10, glow=0.0, display_font="builtin:Barlow-SemiBold",
                   text_font="builtin:Barlow-Medium"),
        mono=False, title="SYSTEM",
    ),
    dict(
        slug="rgb-gaming", name="RGB Gaming", author="TURMO-OpenSource",
        desc="Dark chassis, vivid multi-colour accents (cyan/violet/green/pink) and strong glow — the RGB rig look.",
        pal=palette(bg="#050508", bg2="#0b0b12", card="#131320", card2="#1c1c2e",
                    edge="#2e2e46", text="#f4f4fa", muted="#a0a0b4",
                    accent="#00e5ff", accent_deep="#0091b8", violet="#8b5cf6",
                    green="#00ff9d", pink="#ff2bd6", line="#23233a",
                    track="#1c1c2e"),
        font="builtin:Barlow-Medium",
        style=dict(card="outline", radius=12, glow=0.7, display_font="builtin:Barlow-Bold",
                   text_font="builtin:Barlow-Medium"),
        mono=False, title="RIG",
    ),
    dict(
        slug="futuristic-hud", name="Futuristic HUD", author="TURMO-OpenSource",
        desc="Deep blue-black with cyan HUD lines and outlined cards. Instrument-panel feel.",
        pal=palette(bg="#001018", bg2="#001824", card="#00222f", card2="#00303f",
                    edge="#00e5ff33", text="#e6fbff", muted="#7fb8c8",
                    accent="#00e5ff", accent_deep="#00a8c8", violet="#5f9bff",
                    green="#00ffd0", pink="#ff5c8a", line="#00485f",
                    track="#00222f"),
        font="builtin:Barlow-Medium",
        style=dict(card="outline", radius=8, glow=0.5, display_font="builtin:BarlowCondensed-SemiBold",
                   text_font="builtin:Barlow-Medium"),
        mono=False, title="HUD",
    ),
    dict(
        slug="clean-white", name="Clean White", author="TURMO-OpenSource",
        desc="Light theme: white cards, soft gray text, one blue accent. For bright rooms.",
        pal=palette(bg="#eef0f4", bg2="#f5f6f8", card="#ffffff", card2="#f0f1f5",
                    edge="#d8dbe2", text="#1a1c22", muted="#5b6270", dim="#9aa1ad",
                    accent="#2563eb", accent_deep="#1d4ed8", violet="#6d28d9",
                    green="#047857", pink="#be185d", line="#e2e4ea",
                    track="#e6e8ee", text2="#2a2d35", text3="#4b4f59",
                    warn="#b45309", crit="#dc2626"),
        font="builtin:Barlow-Medium",
        style=dict(card="flat", radius=12, glow=0.0, display_font="builtin:Barlow-Bold",
                   text_font="builtin:Barlow-Medium"),
        mono=False, title="TURMO",
    ),
    dict(
        slug="matrix-terminal", name="Matrix Terminal", author="TURMO-OpenSource",
        desc="Black with phosphor-green mono type, no cards — a terminal window showing the machine's vitals.",
        pal=palette(bg="#000000", bg2="#020603", card="#041007", card2="#071a0c",
                    edge="#00ff4122", text="#00ff41", muted="#1f9c3a",
                    dim="#0e5c22", accent="#00ff41", accent_deep="#00b32e",
                    violet="#3aff9e", green="#00ff41", pink="#b7ff2b",
                    warn="#ffb020", crit="#ff3b5c", line="#0a3315",
                    track="#041007"),
        font="builtin:JetBrainsMono-Medium",
        style=dict(card="flat", radius=0, glow=0.3, display_font="builtin:JetBrainsMono-Bold",
                   text_font="builtin:JetBrainsMono-Medium"),
        mono=True, title="> turing-3.5",
    ),
]


def cell(col, row, cols, rows):
    return {"col": col, "row": row, "cols": cols, "rows": rows}


def hardware_dashboard_theme(portrait=False):
    """Dense multi-module dashboard: many module kinds in a grid (3 columns, or 2 in portrait)."""
    pal = palette(bg="#0b0d12", bg2="#10131a", card="#171b24", card2="#20242f",
                  edge="#2c3140", text="#eef1f6", muted="#9298a8",
                  accent="#4da3ff", violet="#a78bfa", green="#34d399",
                  pink="#f472b6")
    w, h = (320, 480) if portrait else (W, H)
    widgets = [
        rw("rect", "backdrop", x=0, y=0, w=w, h=h, color="@bg2", color2="@bg",
           locked=True),
        rw("clock", "clock", x=14, y=6, format="%H:%M", font_size=36,
           color="@text", font="builtin:Barlow-Bold"),
        rw("clock", "date", x=14, y=44, format="%a %d %b", font_size=13,
           color="@muted"),
        # Module cards sit on the theme's 12 x 8 grid (col, row, cols, rows), not at x/y
        rw("module", "temps", module="temps", card="on", source="cpu", **cell(0, 2, 4, 3)),
        rw("module", "cores", module="cores", card="on", sensor="cpu.load", **cell(4, 2, 4, 3)),
        rw("module", "system", module="system", card="on", **cell(8, 2, 4, 2)),
        rw("module", "drives", module="drives", card="on", **cell(0, 5, 4, 3)),
        rw("module", "network", module="network", card="on", **cell(4, 5, 4, 3)),
        rw("module", "battery", module="battery", card="on", **cell(8, 4, 4, 2)),
        rw("module", "power", module="power", card="on", **cell(8, 6, 4, 2)),
    ]
    if portrait:  # two columns of six grid cells; the clock keeps the first row
        spots = {"temps": (0, 1, 6, 2), "cores": (6, 1, 6, 2), "drives": (0, 3, 6, 2), "network": (6, 3, 6, 2),
                 "system": (0, 5, 6, 2), "battery": (6, 5, 6, 2), "power": (0, 7, 12, 1)}
        for wd in widgets:
            if wd["id"] in spots:
                wd.update(cell(*spots[wd["id"]]))
    return theme("Hardware Dashboard", "TURMO-OpenSource",
                 "Dense multi-module dashboard: temperatures, per-core load, drives, network, system, battery and power in one grid.",
                 pal, "builtin:Barlow-Medium",
                 dict(card="flat", radius=10, glow=0.3,
                      display_font="builtin:Barlow-SemiBold",
                      text_font="builtin:Barlow-Medium"),
                 widgets)


def blank_canvas_theme(w=W, h=H):
    """Empty canvas: a minimal clock plus a hint, ready to build on in the editor. 480x320 or 320x480."""
    pal = palette(bg="#000000", bg2="#0a0a0f", card="#14141a", edge="#2a2a35",
                  text="#f2f2f7", muted="#9a9aa6", accent="#00e5ff")
    widgets = [
        rw("rect", "backdrop", x=0, y=0, w=w, h=h, color="@bg2", color2="@bg",
           locked=True),
        rw("clock", "clock", x=16, y=10, format="%H:%M", font_size=52,
           color="@text", font="builtin:Barlow-Bold"),
        rw("clock", "date", x=18, y=70, format="%A, %d %B", font_size=16,
           color="@muted"),
        rw("text", "hint", x=16, y=h - 30, w=w - 32, h=18,
           text="EDIT ME IN THE THEME EDITOR",
           font_size=11, color="@dim", align="left", letter_spacing=1.2),
    ]
    return theme("Custom Blank Canvas", "TURMO-OpenSource",
                 "An empty canvas: just a clock and a hint. The starting point for your own layout.",
                 pal, "builtin:Barlow-Medium",
                 dict(card="flat", radius=10, glow=0.2,
                      display_font="builtin:Barlow-Bold",
                      text_font="builtin:Barlow-Medium"),
                 widgets)


def portrait_dashboard():
    """Shared 320x480 dashboard, following the reference mockup: title with side
    rules, big clock and date, three cards (CPU, GPU, RAM) with a ring, a temperature
    or memory value and a filled sparkline, and a network card with up and down rates.
    Colours are palette tokens, so each theme keeps its own look."""
    add = []
    add.append({"type": "rect", "id": "backdrop", "x": 0, "y": 0, "w": 320, "h": 480,
                "color": "@bg2", "color2": "@bg", "locked": True})
    add.append({"type": "rect", "id": "hdr-line-l", "x": 27, "y": 12, "w": 67, "h": 1,
                "color": "@violet", "locked": True})
    add.append({"type": "rect", "id": "hdr-line-r", "x": 225, "y": 12, "w": 69, "h": 1,
                "color": "@pink", "locked": True})
    add.append({"type": "text", "id": "title", "x": 160, "y": 4, "h": 18, "text": "TURMO",
                "font_size": 14, "color": "@text", "align": "center", "letter_spacing": 6.0,
                "font": "builtin:Barlow-SemiBold"})
    add.append({"type": "clock", "id": "clock", "x": 22, "y": 28, "format": "%H:%M",
                "font_size": 40, "color": "@text", "font": "builtin:Barlow-Bold"})
    add.append({"type": "rect", "id": "clock-div", "x": 148, "y": 36, "w": 1, "h": 30,
                "color": "@line", "locked": True})
    add.append({"type": "icon", "id": "date-icon", "x": 156, "y": 41, "icon": "calendar",
                "size": 20, "color": "@violet", "stroke": 2})
    add.append({"type": "clock", "id": "date", "x": 184, "y": 44, "format": "%a, %b %d, %Y",
                "font_size": 13, "color": "@text", "tabular": False})

    # key, name, subtitle, load sensor, value sensor, value label, accent, value format, card top
    cards = [
        ("cpu", "CPU", "Processor", "cpu.load", "cpu.temp", "TEMP", "@accent", "{value:.0f}{unit}", 89),
        ("gpu", "GPU", "Graphics", "gpu.load", "gpu.temp", "TEMP", "@green", "{value:.0f}{unit}", 196),
        ("ram", "RAM", "Memory", "mem.load", "mem.used", "USED", "@violet", "{value:.1f} GB", 303),
    ]
    for k, name, sub, load, value, vlabel, acc, vfmt, t in cards:
        add.append({"type": "rect", "id": f"{k}-card", "x": 8, "y": t, "w": 304, "h": 98,
                    "color": "@card", "radius": 12, "outline": "@edge", "locked": True})
        add.append({"type": "rect", "id": f"{k}-iconbox", "x": 20, "y": t + 12, "w": 42, "h": 42,
                    "color": "@card2", "radius": 8, "outline": "@edge", "locked": True})
        add.append({"type": "icon", "id": f"{k}-icon", "x": 28, "y": t + 20, "icon": k,
                    "size": 26, "color": acc, "stroke": 2})
        add.append({"type": "text", "id": f"{k}-title", "x": 70, "y": t + 14, "text": name,
                    "font_size": 17, "color": "@text", "font": "builtin:Barlow-Bold"})
        add.append({"type": "text", "id": f"{k}-sub", "x": 70, "y": t + 34, "text": sub,
                    "font_size": 11, "color": "@muted"})
        add.append({"type": "rect", "id": f"{k}-div1", "x": 127, "y": t + 14, "w": 1, "h": 40,
                    "color": "@line", "locked": True})
        add.append({"type": "gauge", "id": f"{k}-ring", "x": 144, "y": t + 5, "w": 58, "h": 58,
                    "sensor": load, "thickness": 6, "color": acc, "background": "@line",
                    "ticks": 0, "glow": 0.4, "glow_radius": 4, "smooth": True,
                    "color_rules": [{"above": 90, "color": "@crit"}]})
        add.append({"type": "metric", "id": f"{k}-val", "x": 173, "y": t + 19,
                    "sensor": load, "format": "{value:.0f}%", "font_size": 17,
                    "color": "@text", "align": "center", "font": "builtin:Barlow-Bold"})
        add.append({"type": "text", "id": f"{k}-loadlbl", "x": 173, "y": t + 40,
                    "text": "LOAD", "font_size": 9, "color": "@muted", "align": "center",
                    "letter_spacing": 1.5})
        add.append({"type": "rect", "id": f"{k}-div2", "x": 219, "y": t + 14, "w": 1, "h": 40,
                    "color": "@line", "locked": True})
        add.append({"type": "icon", "id": f"{k}-tempicon", "x": 233,
                    "y": t + 18 if k == "ram" else t + 20,
                    "icon": "temperature" if k != "ram" else "ram",
                    "size": 18 if k == "ram" else 14,
                    "color": acc, "stroke": 2})
        if k == "ram":
            # max_width: the engine shrinks the number when it would reach the GB unit,
            # so a 3-digit value (128.0, 256.0) cannot overlap "GB".
            add.append({"type": "metric", "id": f"{k}-value", "x": 254, "y": t + 17,
                        "sensor": value, "format": "{value:.1f}", "font_size": 16,
                        "max_width": 40, "color": "@text", "align": "left",
                        "font": "builtin:Barlow-Bold"})
            add.append({"type": "text", "id": f"{k}-unit", "x": 296, "y": t + 26,
                        "text": "GB", "font_size": 9, "color": "@muted", "align": "left",
                        "letter_spacing": 0.5})
        else:
            add.append({"type": "metric", "id": f"{k}-value", "x": 252, "y": t + 17,
                        "sensor": value, "format": vfmt, "font_size": 18, "color": "@text",
                        "align": "left", "font": "builtin:Barlow-Bold"})
        if k == "ram":
            add.append({"type": "metric", "id": f"{k}-vlabel", "x": 268, "y": t + 40,
                        "sensor": "mem.total", "format": "USED / {value:.0f} GB", "font_size": 9,
                        "color": "@muted", "align": "center", "font": "builtin:Barlow-Medium"})
        else:
            add.append({"type": "text", "id": f"{k}-vlabel", "x": 253, "y": t + 40,
                        "text": vlabel, "font_size": 9, "color": "@muted", "letter_spacing": 1.5})
        add.append({"type": "graph", "id": f"{k}-graph", "x": 18, "y": t + 66, "w": 286, "h": 24,
                    "sensor": load, "history": 120, "min": 0, "max": 100, "color": acc,
                    "fill": True, "fill_fade": True, "smooth": True, "line_width": 1,
                    "grid": 0, "glow": 0.2, "glow_radius": 3, "fill_alpha": 0.22})

    # network card
    add.append({"type": "rect", "id": "net-card", "x": 8, "y": 412, "w": 304, "h": 52,
                "color": "@card", "radius": 12, "outline": "@edge", "locked": True})
    add.append({"type": "icon", "id": "net-icon", "x": 20, "y": 424, "icon": "ethernet",
                "size": 24, "color": "@violet", "stroke": 2})
    add.append({"type": "text", "id": "net-title", "x": 52, "y": 423, "text": "NETWORK",
                "font_size": 12, "color": "@text", "font": "builtin:Barlow-Bold"})
    add.append({"type": "text", "id": "net-sub", "x": 52, "y": 440, "text": "Activity",
                "font_size": 9, "color": "@muted"})
    add.append({"type": "rect", "id": "net-div", "x": 113, "y": 420, "w": 1, "h": 34,
                "color": "@line", "locked": True})
    add.append({"type": "icon", "id": "net-upicon", "x": 128, "y": 423, "icon": "up",
                "size": 10, "color": "@accent", "stroke": 2})
    add.append({"type": "metric", "id": "net-up", "x": 144, "y": 421, "sensor": "net.up",
                "format": "{value:rate} {value:rate_unit}", "font_size": 11, "color": "@text",
                "align": "left", "font": "builtin:Barlow-SemiBold", "tabular": True})
    add.append({"type": "icon", "id": "net-dnicon", "x": 128, "y": 440, "icon": "down",
                "size": 10, "color": "@violet", "stroke": 2})
    add.append({"type": "metric", "id": "net-down", "x": 144, "y": 438, "sensor": "net.down",
                "format": "{value:rate} {value:rate_unit}", "font_size": 11, "color": "@text",
                "align": "left", "font": "builtin:Barlow-SemiBold", "tabular": True})
    add.append({"type": "graph", "id": "net-upgraph", "x": 210, "y": 418, "w": 90, "h": 30,
                "sensor": "net.up", "history": 120, "min": 0, "max": None, "color": "@accent", "fill": False,
                "smooth": True, "line_width": 1, "grid": 0})
    add.append({"type": "graph", "id": "net-downgraph", "x": 210, "y": 418, "w": 90, "h": 30,
                "sensor": "net.down", "history": 120, "min": 0, "max": None, "color": "@violet", "fill": False,
                "smooth": True, "line_width": 1, "grid": 0})
    # Same typeface for every text-like widget, as in the mockup: a theme's
    # default monospace font is wider and overflowed the right column.
    for w in add:
        if w.get("type") in ("text", "clock", "metric") and "font" not in w:
            w["font"] = "builtin:Barlow-Medium"
    return add


def portrait_mockup(gpu_color="#16a34a", ram_color="#7c3aed"):
    """Clean White, 320x480: the reference mockup (1024x1536) scaled by 0.3125. Header with
    side rules, the version under the title, big clock and date, three cards (CPU, GPU, RAM)
    with a ring, a big value and a filled sparkline, and a network card with two sparklines.
    Only the clean-white theme uses this layout; the other themes keep portrait_dashboard()."""
    add = []
    add.append({"type": "rect", "id": "backdrop", "x": 0, "y": 0, "w": 320, "h": 480,
                "color": "@bg2", "color2": "@bg", "locked": True})
    add.append({"type": "rect", "id": "hdr-line-l", "x": 25, "y": 14, "w": 67, "h": 1,
                "color": "@violet", "locked": True})
    add.append({"type": "rect", "id": "hdr-line-r", "x": 228, "y": 14, "w": 67, "h": 1,
                "color": "@pink", "locked": True})
    add.append({"type": "text", "id": "title", "x": 160, "y": 6, "text": "TURMO",
                "font_size": 13, "color": "@text", "align": "center", "letter_spacing": 6.0,
                "font": "builtin:Barlow-SemiBold"})
    add.append({"type": "text", "id": "version", "x": 160, "y": 20,
                "text": TURMO_VERSION, "font_size": 8, "color": "@muted", "align": "center",
                "letter_spacing": 1.0})
    add.append({"type": "clock", "id": "clock", "x": 29, "y": 28, "format": "%H:%M",
                "font_size": 38, "color": "@text", "font": "builtin:Barlow-Bold"})
    add.append({"type": "rect", "id": "clock-div", "x": 144, "y": 41, "w": 1, "h": 22,
                "color": "@line", "locked": True})
    add.append({"type": "icon", "id": "date-icon", "x": 175, "y": 44, "icon": "calendar",
                "size": 16, "color": "@violet", "stroke": 2})
    add.append({"type": "clock", "id": "date", "x": 205, "y": 45, "format": "%a, %b %d, %Y",
                "font_size": 12, "color": "@text3", "tabular": False})

    # key, load sensor, accent, card top, card height
    cards = [("cpu", "cpu.load", "@accent", 79, 105),
             ("gpu", "gpu.load", gpu_color, 190, 106),
             ("ram", "mem.load", ram_color, 302, 107)]
    for k, load, acc, t, ch in cards:
        add.append({"type": "rect", "id": f"{k}-card", "x": 5, "y": t, "w": 310, "h": ch,
                    "color": "@card", "radius": 12, "outline": "@edge", "locked": True})
        add.append({"type": "icon", "id": f"{k}-icon", "x": 16, "y": t + 5, "icon": k,
                    "size": 18, "color": acc, "stroke": 2})
        add.append({"type": "gauge", "id": f"{k}-ring", "x": 34, "y": t + 4, "w": 96, "h": 96,
                    "sensor": load, "thickness": 6, "color": acc, "background": "@track",
                    "ticks": 0, "glow": 0.0, "smooth": True,
                    "color_rules": [{"above": 90, "color": "@crit"}]})
        add.append({"type": "metric", "id": f"{k}-val", "x": 82, "y": t + 29,
                    "sensor": load, "format": "{value:.0f}%", "font_size": 32,
                    "color": "@text", "align": "center", "font": "builtin:Barlow-Bold"})
        add.append({"type": "text", "id": f"{k}-loadlbl", "x": 82, "y": t + 79,
                    "text": "LOAD", "font_size": 8, "color": "@muted", "align": "center",
                    "letter_spacing": 1.5})
        add.append({"type": "rect", "id": f"{k}-div1", "x": 144, "y": t + 9, "w": 1, "h": 86,
                    "color": "@line", "locked": True})
        if k == "ram":
            add.append({"type": "icon", "id": f"{k}-tempicon", "x": 184, "y": t + 16,
                        "icon": "ram", "size": 24, "color": acc, "stroke": 2})
            add.append({"type": "metric", "id": f"{k}-value", "x": 209, "y": t + 15,
                        "sensor": "mem.used", "format": "{value:.1f}", "font_size": 22,
                        "max_width": 46, "color": "@text", "align": "left",
                        "font": "builtin:Barlow-Bold"})
            add.append({"type": "text", "id": f"{k}-unit", "x": 258, "y": t + 21,
                        "text": "GB", "font_size": 11, "color": "@text", "align": "left",
                        "letter_spacing": 0.5})
        else:
            sensor = "cpu.temp" if k == "cpu" else "gpu.temp"
            add.append({"type": "icon", "id": f"{k}-tempicon", "x": 189, "y": t + 13,
                        "icon": "temperature", "size": 24, "color": acc, "stroke": 2})
            add.append({"type": "metric", "id": f"{k}-value", "x": 214, "y": t + 12,
                        "sensor": sensor, "format": "{value:.0f}{unit}", "font_size": 22,
                        "max_width": 90, "color": "@text", "align": "left",
                        "font": "builtin:Barlow-Bold"})
        add.append({"type": "rect", "id": f"{k}-rule", "x": 151, "y": t + 49, "w": 155, "h": 1,
                    "color": "@line", "locked": True})
        add.append({"type": "graph", "id": f"{k}-graph", "x": 151, "y": t + 58, "w": 155, "h": 37,
                    "sensor": load, "history": 120, "min": 0, "max": 100, "color": acc,
                    "fill": True, "fill_fade": True, "smooth": True, "line_width": 1,
                    "grid": 0, "glow": 0.2, "glow_radius": 3, "fill_alpha": 0.22})

    # network card
    add.append({"type": "rect", "id": "net-card", "x": 5, "y": 416, "w": 310, "h": 55,
                "color": "@card", "radius": 12, "outline": "@edge", "locked": True})
    add.append({"type": "icon", "id": "net-icon", "x": 9, "y": 417, "icon": "ethernet",
                "size": 52, "color": "@violet", "stroke": 2})
    add.append({"type": "rect", "id": "net-div", "x": 64, "y": 427, "w": 1, "h": 34,
                "color": "@line", "locked": True})
    add.append({"type": "icon", "id": "net-upicon", "x": 84, "y": 428, "icon": "up",
                "size": 10, "color": "@accent", "stroke": 2})
    add.append({"type": "metric", "id": "net-up", "x": 104, "y": 428, "sensor": "net.up",
                "format": "{value:rate} {value:rate_unit}", "font_size": 11, "color": "@text",
                "align": "left", "font": "builtin:Barlow-SemiBold", "tabular": True})
    add.append({"type": "icon", "id": "net-dnicon", "x": 84, "y": 447, "icon": "down",
                "size": 10, "color": "@violet", "stroke": 2})
    add.append({"type": "metric", "id": "net-down", "x": 104, "y": 447, "sensor": "net.down",
                "format": "{value:rate} {value:rate_unit}", "font_size": 11, "color": "@text",
                "align": "left", "font": "builtin:Barlow-SemiBold", "tabular": True})
    add.append({"type": "rect", "id": "net-div2", "x": 182, "y": 427, "w": 1, "h": 34,
                "color": "@line", "locked": True})
    add.append({"type": "graph", "id": "net-upgraph", "x": 191, "y": 428, "w": 113, "h": 34,
                "sensor": "net.up", "history": 120, "min": 0, "max": None, "color": "@accent",
                "fill": False, "smooth": True, "line_width": 1, "grid": 0})
    add.append({"type": "graph", "id": "net-downgraph", "x": 191, "y": 428, "w": 113, "h": 34,
                "sensor": "net.down", "history": 120, "min": 0, "max": None, "color": "@violet",
                "fill": False, "smooth": True, "line_width": 1, "grid": 0})
    for w in add:
        if w.get("type") in ("text", "clock", "metric") and "font" not in w:
            w["font"] = "builtin:Barlow-Medium"
    return add


def landscape_dashboard():
    """Shared 480x320 dashboard: top bar (title, clock, date, network), then
    three cards side by side (CPU, GPU, RAM) with ring, temperature or memory,
    and a sparkline. Colours are palette tokens, as in portrait_dashboard()."""
    add = []
    add.append({"type": "rect", "id": "backdrop", "x": 0, "y": 0, "w": 480, "h": 320,
                "color": "@bg2", "color2": "@bg", "locked": True})
    add.append({"type": "text", "id": "title", "x": 16, "y": 8, "text": "TURMO",
                "font_size": 12, "color": "@text", "align": "left", "letter_spacing": 4.0,
                "font": "builtin:Barlow-SemiBold"})
    add.append({"type": "clock", "id": "clock", "x": 14, "y": 22, "format": "%H:%M",
                "font_size": 30, "color": "@text", "font": "builtin:Barlow-Bold"})
    add.append({"type": "rect", "id": "clock-div", "x": 118, "y": 28, "w": 1, "h": 34,
                "color": "@line", "locked": True})
    add.append({"type": "clock", "id": "date", "x": 130, "y": 36, "format": "%a %d %b",
                "font_size": 12, "color": "@muted", "tabular": False})
    add.append({"type": "text", "id": "net-uplbl", "x": 300, "y": 12, "text": "UP",
                "font_size": 8, "color": "@muted", "letter_spacing": 1.5})
    add.append({"type": "metric", "id": "net-up", "x": 332, "y": 9, "sensor": "net.up",
                "format": "{value:rate} {value:rate_unit}", "font_size": 12, "color": "@accent",
                "align": "left", "font": "builtin:Barlow-SemiBold", "tabular": True})
    add.append({"type": "text", "id": "net-dnlbl", "x": 300, "y": 30, "text": "DOWN",
                "font_size": 8, "color": "@muted", "letter_spacing": 1.5})
    add.append({"type": "metric", "id": "net-down", "x": 332, "y": 27, "sensor": "net.down",
                "format": "{value:rate} {value:rate_unit}", "font_size": 12, "color": "@green",
                "align": "left", "font": "builtin:Barlow-SemiBold", "tabular": True})
    add.append({"type": "rect", "id": "top-line", "x": 8, "y": 56, "w": 464, "h": 1,
                "color": "@line", "locked": True})

    # key, name, subtitle, load sensor, temp sensor, temp label, accent, temp format, card x
    cards = [
        ("cpu", "CPU", "Processor", "cpu.load", "cpu.temp", "TEMP", "@accent", "{value:.0f}°", 8),
        ("gpu", "GPU", "Graphics", "gpu.load", "gpu.temp", "TEMP", "@green", "{value:.0f}°", 165),
        ("ram", "RAM", "Memory", "mem.load", "mem.used", "USED", "@violet", "{value:.1f} GB", 322),
    ]
    cy = 66
    for k, name, sub, load, temp, tlabel, acc, tfmt, cx in cards:
        add.append({"type": "rect", "id": f"{k}-card", "x": cx, "y": cy, "w": 150, "h": 240,
                    "color": "@card", "radius": 12, "outline": "@edge", "locked": True})
        add.append({"type": "icon", "id": f"{k}-icon", "x": cx + 12, "y": cy + 12, "icon": k,
                    "size": 22, "color": acc, "stroke": 2})
        add.append({"type": "text", "id": f"{k}-title", "x": cx + 42, "y": cy + 12, "text": name,
                    "font_size": 16, "color": "@text", "font": "builtin:Barlow-Bold"})
        add.append({"type": "text", "id": f"{k}-sub", "x": cx + 42, "y": cy + 34, "text": sub,
                    "font_size": 9, "color": "@muted"})
        add.append({"type": "gauge", "id": f"{k}-ring", "x": cx + 39, "y": cy + 58, "w": 72, "h": 72,
                    "sensor": load, "thickness": 7, "color": acc, "background": "@line",
                    "ticks": 0, "glow": 0.4, "glow_radius": 5, "smooth": True,
                    "color_rules": [{"above": 90, "color": "@crit"}]})
        add.append({"type": "metric", "id": f"{k}-val", "x": cx + 75, "y": cy + 80,
                    "sensor": load, "format": "{value:.0f}%", "font_size": 15,
                    "color": "@text", "align": "center", "font": "builtin:Barlow-Bold"})
        add.append({"type": "text", "id": f"{k}-loadlbl", "x": cx + 75, "y": cy + 100,
                    "text": "LOAD", "font_size": 9, "color": "@muted", "align": "center",
                    "letter_spacing": 1.5})
        add.append({"type": "rect", "id": f"{k}-div", "x": cx + 12, "y": cy + 144, "w": 126, "h": 1,
                    "color": "@line", "locked": True})
        add.append({"type": "metric", "id": f"{k}-temp", "x": cx + 12, "y": cy + 156,
                    "sensor": temp, "format": tfmt, "font_size": 22, "color": "@text",
                    "align": "left", "font": "builtin:Barlow-Bold"})
        add.append({"type": "text", "id": f"{k}-templbl", "x": cx + 12, "y": cy + 186,
                    "text": tlabel, "font_size": 9, "color": "@muted", "letter_spacing": 1.5})
        add.append({"type": "graph", "id": f"{k}-graph", "x": cx + 10, "y": cy + 204, "w": 130, "h": 28,
                    "sensor": load, "history": 120, "min": 0, "max": 100, "color": acc,
                    "fill": True, "fill_fade": True, "smooth": True, "line_width": 1,
                    "grid": 0, "glow": 0.2, "glow_radius": 3, "fill_alpha": 0.22})
    return add


MOCKUP_THEMES = {"cyberpunk-neon", "minimal-dark", "rgb-gaming", "futuristic-hud", "matrix-terminal"}


def layout_for(slug):
    """Portrait layout of a theme: the v4 mockup for the six themes of the list. Clean White keeps
    its approved greens and violets; the others use their own palette tokens. The two custom
    themes keep the default dashboard (None)."""
    if slug == "clean-white":
        return portrait_mockup
    if slug in MOCKUP_THEMES:
        return partial(portrait_mockup, gpu_color="@green", ram_color="@violet")
    return None


def emit(theme_dict, slug, portrait_variant=False, layout=None, keep=False):
    """keep=True writes the theme's own widgets (the blank canvas) instead of the standard dashboard layouts."""
    d = theme_dict["display"]
    if portrait_variant:
        d = dict(d, orientation="portrait", width=320, height=480)
        theme_dict = dict(theme_dict)
        theme_dict["display"] = d
        if not keep:
            theme_dict["widgets"] = (layout or portrait_dashboard)()
    else:
        theme_dict = dict(theme_dict)
        if not keep:
            theme_dict["widgets"] = landscape_dashboard()
    tdir = os.path.join(THEMES_DIR, slug if not portrait_variant else slug + "-320x480")
    os.makedirs(tdir, exist_ok=True)
    with open(os.path.join(tdir, "theme.json"), "w", encoding="utf-8") as f:
        json.dump(theme_dict, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return tdir


def main():
    if os.path.isdir(THEMES_DIR):
        shutil.rmtree(THEMES_DIR)
    os.makedirs(THEMES_DIR)
    made = []
    for t in THEMES:
        widgets = dashboard(t["pal"], t["font"], t["style"], t["pal"]["accent"],
                            mono=t.get("mono", False), title=t["title"])
        th = theme(t["name"], t["author"], t["desc"], t["pal"], t["font"],
                   t["style"], widgets)
        made.append(emit(th, t["slug"]))
        layout = layout_for(t["slug"])
        made.append(emit(th, t["slug"], portrait_variant=True, layout=layout))
    made.append(emit(hardware_dashboard_theme(), "hardware-dashboard", keep=True))
    made.append(emit(hardware_dashboard_theme(True), "hardware-dashboard", True, keep=True))
    made.append(emit(blank_canvas_theme(), "custom-blank-canvas", keep=True))
    made.append(emit(blank_canvas_theme(320, 480), "custom-blank-canvas", True, keep=True))
    print("wrote %d theme dirs:" % len(made))
    for d in made:
        print("  ", d)


if __name__ == "__main__":
    main()
