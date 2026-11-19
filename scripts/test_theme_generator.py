#!/usr/bin/env python3
"""Regression checks for the dashboard themes (no hardware, no libre_panel).

Run:  python scripts/test_theme_generator.py

Checks, for the 8 portrait (320x480) and 8 landscape (480x320) themes:
  * each theme.json declares the right display size;
  * every widget with a box (x, y, w, h) stays inside the display;
  * no two widgets share an id;
  * the shipped theme.json widgets equal the generator output (no drift);
  * the RAM value cannot run into its GB unit (max_width + fixed GB position).
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
THEMES = os.path.join(ROOT, "themes")
sys.path.insert(0, HERE)

import generate_themes as g  # noqa: E402

THEME_NAMES = [
    "clean-white", "custom-blank-canvas", "cyberpunk-neon", "futuristic-hud",
    "hardware-dashboard", "matrix-terminal", "minimal-dark", "rgb-gaming",
]


def load_widgets(folder):
    with open(os.path.join(THEMES, folder, "theme.json"), encoding="utf-8") as f:
        return json.load(f)


def outside(widgets, width, height):
    bad = []
    for w in widgets:
        if "x" in w and "w" in w and "h" in w:
            if (w["x"] < 0 or w["y"] < 0 or w["x"] + w["w"] > width or w["y"] + w["h"] > height):
                bad.append(w.get("id"))
    return bad


class PortraitThemes(unittest.TestCase):
    def test_display_size_is_320x480(self):
        for name in THEME_NAMES:
            d = load_widgets(name + "-320x480")["display"]
            self.assertEqual((d["width"], d["height"]), (320, 480), name)

    def test_widgets_inside_320x480(self):
        for name in THEME_NAMES:
            self.assertEqual(outside(load_widgets(name + "-320x480")["widgets"], 320, 480), [], name)

    def test_no_duplicate_ids(self):
        for name in THEME_NAMES:
            ids = [w.get("id") for w in load_widgets(name + "-320x480")["widgets"]]
            self.assertEqual(len(ids), len(set(ids)), name)

    def test_matches_generator(self):
        expected = g.portrait_dashboard()
        for name in THEME_NAMES:
            layout = g.layout_for(name)
            want = layout() if layout else expected
            if name == "custom-blank-canvas":  # a real blank canvas, not the dashboard
                want = g.blank_canvas_theme(320, 480)["widgets"]
            if name == "hardware-dashboard":  # its own grid of modules
                want = g.hardware_dashboard_theme(True)["widgets"]
            self.assertEqual(load_widgets(name + "-320x480")["widgets"], want, name)

    def test_clean_white_shows_the_release_version(self):
        from app_version import TURMO_VERSION
        version = next(w for w in g.portrait_mockup() if w.get("id") == "version")
        self.assertEqual(version["text"], TURMO_VERSION)

    def test_ram_value_cannot_reach_gb(self):
        value = next(w for w in g.portrait_dashboard() if w.get("id") == "ram-value")
        unit = next(w for w in g.portrait_dashboard() if w.get("id") == "ram-unit")
        self.assertIn("max_width", value)
        self.assertLessEqual(value["x"] + value["max_width"], unit["x"])


class LandscapeThemes(unittest.TestCase):
    def test_display_size_is_480x320(self):
        for name in THEME_NAMES:
            d = load_widgets(name)["display"]
            self.assertEqual((d["width"], d["height"]), (480, 320), name)

    def test_widgets_inside_480x320(self):
        for name in THEME_NAMES:
            self.assertEqual(outside(load_widgets(name)["widgets"], 480, 320), [], name)

    def test_no_duplicate_ids(self):
        for name in THEME_NAMES:
            ids = [w.get("id") for w in load_widgets(name)["widgets"]]
            self.assertEqual(len(ids), len(set(ids)), name)

    def test_matches_generator(self):
        expected = g.landscape_dashboard()
        for name in THEME_NAMES:
            own = {"custom-blank-canvas": g.blank_canvas_theme, "hardware-dashboard": g.hardware_dashboard_theme}
            want = own[name]()["widgets"] if name in own else expected
            self.assertEqual(load_widgets(name)["widgets"], want, name)


class GeneratorShape(unittest.TestCase):
    def test_removed_helpers_are_gone(self):
        self.assertFalse(hasattr(g, "portrait"))
        self.assertFalse(hasattr(g, "fix_portrait_layout"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
