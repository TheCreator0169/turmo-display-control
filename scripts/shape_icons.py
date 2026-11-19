"""Simple shapes next to the display's icons (CPU, GPU, RAM...): circle, square, triangle and a few more, so an Icon
widget can be a plain shape. They are drawn with the same pen as the icons, so they take the widget's colour, size
and stroke. `register()` adds them to the icon list of the renderer; the GUI and the Monitor both call it, so a
theme that uses one looks the same in the editor and on the display."""
import math

SHAPES = ("circle", "dot", "square", "block", "triangle", "wedge", "diamond", "hexagon", "star", "plus", "check")


def _filled(pen, points):
    pen.draw.polygon([pen.p(*pt) for pt in points], fill=pen.color)


def _circle(pen):
    pen.circle(12, 12, 9)


def _dot(pen):
    pen.circle(12, 12, 9, fill=True)


def _square(pen):
    pen.rect(4, 4, 20, 20, 2)


def _block(pen):
    pen.draw.rounded_rectangle([*pen.p(3, 3), *pen.p(21, 21)], radius=2 * pen.s, fill=pen.color)


def _triangle(pen):
    pen.polygon([(12, 3.5), (21, 19.5), (3, 19.5)])


def _wedge(pen):
    _filled(pen, [(12, 3), (21.5, 20), (2.5, 20)])


def _diamond(pen):
    pen.polygon([(12, 2.5), (21.5, 12), (12, 21.5), (2.5, 12)])


def _hexagon(pen):
    pen.polygon([(12 + 9.5 * math.cos(math.radians(a)), 12 + 9.5 * math.sin(math.radians(a)))
                 for a in range(0, 360, 60)])


def _star(pen):
    pts = [(12 + (10 if i % 2 == 0 else 4.2) * math.cos(math.radians(-90 + i * 36)),
            12 + (10 if i % 2 == 0 else 4.2) * math.sin(math.radians(-90 + i * 36))) for i in range(10)]
    pen.polygon(pts)


def _plus(pen):
    pen.line((12, 4), (12, 20))
    pen.line((4, 12), (20, 12))


def _check(pen):
    pen.line((4, 13), (9.5, 18.5), (20, 6))


_DRAW = {"circle": _circle, "dot": _dot, "square": _square, "block": _block, "triangle": _triangle,
         "wedge": _wedge, "diamond": _diamond, "hexagon": _hexagon, "star": _star, "plus": _plus, "check": _check}


def register():
    """Add the shapes to the renderer's icons and to the names a theme may use; safe to call twice."""
    from libre_panel import icons
    from libre_panel.theme import model
    icons._ICONS.update(_DRAW)
    names = tuple(icons.ICON_NAMES) + tuple(n for n in SHAPES if n not in icons.ICON_NAMES)
    icons.ICON_NAMES = names
    model.ICON_NAMES = names
