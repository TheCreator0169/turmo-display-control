"""The Theme Editor draws a theme with the same renderer as the display, so a widget sits where it will sit on the
screen (text anchored by its alignment, real fonts, real icons, rings and graphs). Sample sensor values stand in for
the live readings.

`Shot` takes the theme document (theme.json without its widgets) and the widgets as dicts; `image()` is the
picture and `extent(widget)` the pixels a widget covers, found by drawing the theme with and without it."""
import copy
import json
import math

from PIL import Image, ImageChops

DEMO = {"cpu.load": 42.0, "cpu.temp": 61.0, "gpu.load": 18.0, "gpu.temp": 47.0, "mem.load": 55.0,
        "mem.used": 17.6, "mem.total": 32.0, "net.down": 1.2, "net.up": 0.3, "disk.load": 8.0,
        "gpu.vram_used": 2.4, "gpu.vram_total": 8.0, "gpu.freq": 1800.0}
UNITS = {"cpu.load": "%", "gpu.load": "%", "mem.load": "%", "disk.load": "%", "cpu.temp": "°C", "gpu.temp": "°C",
         "mem.used": "GB", "mem.total": "GB", "gpu.vram_used": "GB", "gpu.vram_total": "GB", "net.down": "MB/s",
         "net.up": "MB/s", "gpu.freq": "MHz"}


def demo_snapshot():
    """A snapshot with plausible readings and a wavy history, so graphs and rings have something to show."""
    from libre_panel.sensors.base import Reading, Snapshot
    readings = {k: Reading(key=k, value=v, unit=UNITS.get(k, ""), label=k) for k, v in DEMO.items()}
    history = {k: [max(0.0, v + 0.35 * v * math.sin(i / 9)) for i in range(120)] for k, v in DEMO.items()}
    return Snapshot(readings=readings, history=history)


class Shot:
    def __init__(self, doc, root, widgets, cache=None):
        """`cache` (a dict the caller keeps while the theme document stays the same) lets the extents survive
        from one picture to the next, so dragging a widget does not measure the others again."""
        self.doc, self.root, self.widgets = doc, root, widgets
        self._snap = demo_snapshot()
        self._cache = {} if cache is None else cache
        self._extents = self._cache.setdefault("extents", {})

    def _render(self, widgets):
        from libre_panel.render.renderer import Renderer
        from libre_panel.theme.model import parse_theme
        data = dict(self.doc)
        data["widgets"] = widgets
        return Renderer(parse_theme(data, self.root)).render(self._snap)[0].convert("RGB")

    def image(self):
        return self._render(self.widgets)

    def extent(self, widget):
        """(x1, y1, x2, y2) of what `widget` paints, or None if it paints nothing (hidden, or off the screen).
        It is drawn in the middle of the screen, where a centred or right-aligned text is not cut, and measured
        against the empty theme; the result is kept per look of the widget, so moving it only moves the box."""
        look = {k: v for k, v in widget.items() if k not in ("x", "y")}
        key = json.dumps(look, sort_keys=True, default=str)
        if key not in self._extents:
            cx, cy = self.size()[0] // 2, self.size()[1] // 2
            probe = copy.deepcopy(widget)
            probe["x"], probe["y"] = cx, cy
            blank = self._cache.get("blank")
            if blank is None:
                blank = self._cache["blank"] = self._render([])
            box = ImageChops.difference(self._render([probe]), blank).getbbox()
            self._extents[key] = None if box is None else (box[0] - cx, box[1] - cy, box[2] - cx, box[3] - cy)
        found = self._extents[key]
        if found is None:
            return None
        x, y = widget.get("x", 0), widget.get("y", 0)
        return (x + found[0], y + found[1], x + found[2], y + found[3])

    def size(self):
        d = self.doc.get("display", {})
        return int(d.get("width", 320)), int(d.get("height", 480))
