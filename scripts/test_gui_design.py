#!/usr/bin/env python3
"""Tests for the v0.2.0 GUI helpers and the app icon assets (no window, no hardware).

Run:  .venv-win\\Scripts\\python.exe scripts\\test_gui_design.py
"""
import os
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from scripts import gui_design as gd  # noqa: E402


@dataclass
class FakeReading:
    key: str
    value: object


class MetricText(unittest.TestCase):
    def test_missing_sensor_shows_dash(self):
        self.assertEqual(gd.metric_text({}, "cpu.temp", "{value:.0f}°C"), gd.NO_VALUE)
        self.assertEqual(gd.metric_text(None, "cpu.temp", "{value:.0f}"), gd.NO_VALUE)

    def test_reading_object_is_formatted(self):
        readings = {"cpu.load": FakeReading("cpu.load", 42.6)}
        self.assertEqual(gd.metric_text(readings, "cpu.load", "{value:.0f}%"), "43%")

    def test_plain_number_is_formatted(self):
        self.assertEqual(gd.metric_text({"mem.used": 24.66}, "mem.used", "{value:.1f} GB"), "24.7 GB")

    def test_none_and_text_values_show_dash(self):
        self.assertEqual(gd.metric_text({"x": None}, "x", "{value:.0f}"), gd.NO_VALUE)
        self.assertEqual(gd.metric_text({"x": "n/a"}, "x", "{value:.0f}"), gd.NO_VALUE)


class Sparkline(unittest.TestCase):
    def test_too_few_samples_give_no_line(self):
        self.assertEqual(gd.sparkline_points([], 100, 40), [])
        self.assertEqual(gd.sparkline_points([50], 100, 40), [])
        self.assertEqual(gd.sparkline_points([None, 50], 100, 40), [])

    def test_points_span_the_width_and_scale_the_height(self):
        pts = gd.sparkline_points([0, 100], 100, 40, pad=2)
        self.assertEqual(pts, [2.0, 38.0, 98.0, 2.0])  # 0 at the bottom, 100 at the top

    def test_values_outside_0_100_are_clamped(self):
        pts = gd.sparkline_points([-50, 300], 100, 40, pad=2)
        self.assertEqual(pts[1], 38.0)
        self.assertEqual(pts[3], 2.0)


class Layout(unittest.TestCase):
    def test_sidebar_has_nine_entries(self):
        self.assertEqual(len(gd.SIDEBAR_ITEMS), 9)
        self.assertEqual(gd.SIDEBAR_ITEMS[0], "Dashboard")

    def test_sidebar_groups_list_every_item_once_in_tab_order(self):
        grouped = [name for _group, names in gd.SIDEBAR_GROUPS for name in names]
        self.assertEqual(grouped, list(gd.SIDEBAR_ITEMS))

    def test_quick_themes_exist_in_the_themes_folder(self):
        themes = ROOT / "themes"
        for slug, _label, _colour in gd.QUICK_THEMES:
            self.assertTrue((themes / slug).is_dir(), slug)


class ColourMix(unittest.TestCase):
    def test_mix_matches_css_color_mix(self):
        # nav active tint: accent 13% over the sidebar colour; primary hover: accent 88% over white
        self.assertEqual(gd.mix("#22D3EE", "#12161F", 0.13), "#142F3A")
        self.assertEqual(gd.mix("#22D3EE", "#FFFFFF", 0.88), "#3DD8F0")

    def test_mix_ends(self):
        self.assertEqual(gd.mix("#102030", "#FFFFFF", 1), "#102030")
        self.assertEqual(gd.mix("#102030", "#FFFFFF", 0), "#FFFFFF")


class DeviceStatus(unittest.TestCase):
    def test_states(self):
        self.assertEqual(gd.device_status("COM4 ✓", False), ("Connected", "ok"))
        self.assertEqual(gd.device_status("COM4 ✓", True), ("Monitor running", "ok"))
        self.assertEqual(gd.device_status("Busy / In Use ⚠", False), ("Busy", "busy"))
        self.assertEqual(gd.device_status("Not found ✗", False), ("Disconnected", "off"))
        self.assertEqual(gd.device_status("", False), ("Disconnected", "off"))

    def test_chip_text(self):
        self.assertEqual(gd.device_chip_text("COM4 ✓", "ok"), "TURMO · COM4")
        self.assertEqual(gd.device_chip_text("Busy / In Use ⚠", "ok"), "Monitor running")
        self.assertEqual(gd.device_chip_text("Not found ✗", "ok"), "Monitor running")
        self.assertEqual(gd.device_chip_text("x", "busy"), "COM port busy")
        self.assertEqual(gd.device_chip_text("x", "off"), "No device")

    def test_the_monitor_link_state_wins_while_the_monitor_runs(self):
        self.assertEqual(gd.device_status("COM4 ✓", True, "retrying"), ("Reconnecting…", "busy"))
        self.assertEqual(gd.device_status("Not found ✗", True, "not_found"), ("Not found", "off"))
        self.assertEqual(gd.device_status("Not found ✗", True, "starting"), ("Connecting…", "busy"))
        self.assertEqual(gd.device_status("COM4 ✓", True, "connected"), ("Monitor running", "ok"))
        self.assertEqual(gd.device_status("COM4 ✓", False, "retrying"), ("Connected", "ok"))  # no Monitor: stale
        self.assertEqual(gd.device_chip_text("COM4 ✓", "busy", "retrying"), "Waiting for the display")


class ScaleHistory(unittest.TestCase):
    def test_fixed_top_and_own_maximum(self):
        self.assertEqual(gd.scale_history([0, 50], 100), [0.0, 50.0])
        self.assertEqual(gd.scale_history([1, 2, 4]), [25.0, 50.0, 100.0])

    def test_empty_and_all_zero_do_not_divide_by_zero(self):
        self.assertEqual(gd.scale_history([]), [])
        self.assertEqual(gd.scale_history([0, 0]), [0.0, 0.0])
        self.assertEqual(gd.scale_history([None, 5], 10), [50.0])


class RuntimeLog(unittest.TestCase):
    LINES = [
        "[2026-11-17T10:35:10.513019] [INFO] PID=28940 TID=30956 Thread=Thread-3 (_preview_worker) "
        "Component=PREVIEW Event=START",
        "  Frozen: True | Python: 3.14.6",
        "[2026-11-17T10:35:11.000000] [WARN] PID=1 TID=2 Thread=MainThread Component=MONITOR Event=SLOW",
        "  late by 2 s",
        "[2026-11-17T10:35:12.000000] [ERROR] PID=1 TID=2 Thread=MainThread Component=CPU_TEMP Event=FAIL boom",
        "Traceback (most recent call last):",
        "not a log line at all",
    ]

    def test_entries_have_time_level_and_a_short_message(self):
        entries = gd.parse_log(self.LINES)
        self.assertEqual(entries[0], ("10:35:10", "INFO", "PREVIEW · START"))
        self.assertEqual(len(entries), 3)  # the continuation of an INFO entry is dropped

    def test_continuations_join_warnings_and_errors(self):
        entries = gd.parse_log(self.LINES)
        self.assertIn("late by 2 s", entries[1][2])
        self.assertIn("Traceback", entries[2][2])

    def test_kind_and_recent_errors(self):
        entries = gd.parse_log(self.LINES)
        self.assertEqual([gd.log_kind(e[1]) for e in entries], ["info", "warn", "err"])
        self.assertEqual([e[0] for e in gd.recent_errors(entries)], ["10:35:12"])
        self.assertEqual(gd.recent_errors([]), [])

    def test_limit_keeps_the_newest_entries(self):
        many = [f"[2026-11-17T10:00:{i:02d}.0] [INFO] x" for i in range(10)]
        self.assertEqual([e[0] for e in gd.parse_log(many, limit=2)], ["10:00:08", "10:00:09"])


class DimImage(unittest.TestCase):
    """Brightness is applied to the pixels (the display has no known brightness command)."""

    def setUp(self):
        from PIL import Image
        self.Image = Image
        self.im = Image.new("RGB", (2, 2), (200, 100, 50))

    def test_full_brightness_returns_the_same_image(self):
        from scripts.settings import dim_image
        self.assertIs(dim_image(self.im, 100), self.im)
        self.assertIs(dim_image(self.im, 250), self.im)

    def test_half_brightness_halves_the_channels(self):
        from scripts.settings import dim_image
        self.assertEqual(dim_image(self.im, 50).getpixel((0, 0)), (100, 50, 25))

    def test_zero_and_negative_give_black_and_the_source_is_untouched(self):
        from scripts.settings import dim_image
        self.assertEqual(dim_image(self.im, 0).getpixel((0, 0)), (0, 0, 0))
        self.assertEqual(dim_image(self.im, -5).getpixel((0, 0)), (0, 0, 0))
        self.assertEqual(self.im.getpixel((0, 0)), (200, 100, 50))

    def test_works_without_pil_imageenhance(self):
        # the frozen Monitor does not bundle PIL.ImageEnhance: dimming silently did nothing on the display
        from unittest import mock
        from scripts.settings import dim_image
        with mock.patch.dict(sys.modules, {"PIL.ImageEnhance": None}):
            self.assertEqual(dim_image(self.im, 50).getpixel((0, 0)), (100, 50, 25))

    def test_bad_value_leaves_the_image_alone(self):
        from scripts.settings import dim_image
        self.assertIs(dim_image(self.im, None), self.im)
        self.assertIs(dim_image(self.im, "x"), self.im)


class PickTopmost(unittest.TestCase):
    def test_the_topmost_box_under_the_point_wins(self):
        from scripts.gui_design import pick_topmost
        boxes = [("under", (0, 0, 100, 100)), ("over", (50, 50, 150, 150))]
        self.assertEqual(pick_topmost(boxes, 75, 75), "over")
        self.assertEqual(pick_topmost(boxes, 10, 10), "under")
        self.assertIsNone(pick_topmost(boxes, 300, 300))

    def test_a_small_box_is_easy_to_hit(self):
        from scripts.gui_design import pick_topmost
        self.assertEqual(pick_topmost([("clock", (10, 10, 12, 12))], 14, 8), "clock")  # a few pixels off
        self.assertIsNone(pick_topmost([("clock", (10, 10, 12, 12))], 30, 30))
        self.assertIsNone(pick_topmost([], 1, 1))


class ThemeOrder(unittest.TestCase):
    def test_saved_order_first_then_alphabetical(self):
        from scripts.gui_design import order_themes
        self.assertEqual(order_themes(["a", "b", "c", "d"], ["c", "gone", "a", "c"]), ["c", "a", "b", "d"])
        self.assertEqual(order_themes(["b", "a"]), ["a", "b"])

    def test_filter_uses_the_order(self):
        from scripts.gui_design import filter_themes
        self.assertEqual(filter_themes(["a", "b", "c"], "All", "", ["c", "b"]), ["c", "b", "a"])

    def test_move_inside_what_is_shown(self):
        from scripts.gui_design import move_theme
        order = ["a", "x", "b", "y", "c"]
        shown = ["a", "b", "c"]  # x and y are in another category
        self.assertEqual(move_theme(order, shown, "c", "start"), ["c", "x", "a", "y", "b"])
        self.assertEqual(move_theme(order, shown, "a", "right"), ["b", "x", "a", "y", "c"])
        self.assertEqual(move_theme(order, shown, "b", "end"), ["a", "x", "c", "y", "b"])
        self.assertEqual(move_theme(order, shown, "c", "left"), ["a", "x", "c", "y", "b"])

    def test_impossible_moves_change_nothing(self):
        from scripts.gui_design import move_theme
        order = ["a", "b"]
        self.assertEqual(move_theme(order, order, "a", "left"), order)
        self.assertEqual(move_theme(order, order, "b", "right"), order)
        self.assertEqual(move_theme(order, order, "a", "start"), order)
        self.assertEqual(move_theme(order, order, "zz", "end"), order)
        self.assertEqual(move_theme(order, order, "a", "sideways"), order)


class DescriptionCollapse(unittest.TestCase):
    measure = staticmethod(len)  # one pixel per character

    def test_short_text_is_not_cut(self):
        from scripts.gui_design import collapse_description
        short, lines = collapse_description("Light theme with one accent.", self.measure, 30, "See more")
        self.assertIsNone(short)
        self.assertEqual(lines, ["Light theme with one accent."])

    def test_long_text_is_cut_to_two_lines_with_room_for_the_link(self):
        from scripts.gui_design import collapse_description
        text = "Neon magenta cyan on deep purple black. Glowing rings and a lit graph for the cyberpunk look."
        short, lines = collapse_description(text, self.measure, 30, "See more")
        self.assertEqual(len(short), 2)
        self.assertGreater(len(lines), 2)
        self.assertEqual(short[0], lines[0])
        self.assertTrue(short[1].endswith("…"))
        self.assertLessEqual(len(short[1]) + 1 + len("See more"), 30)

    def test_one_long_word_does_not_loop(self):
        from scripts.gui_design import collapse_description
        short, _ = collapse_description("ab " + "x" * 80 + " tail", self.measure, 30, "See more")
        self.assertEqual(len(short), 2)


class AppIcon(unittest.TestCase):
    def test_one_logo_png_and_no_ico(self):
        self.assertTrue((ROOT / "assets" / "turmo_icon.png").is_file())
        self.assertFalse((ROOT / "assets" / "turmo.ico").exists())
        for spec in ("turmo.spec", "turmo_monitor.spec"):
            self.assertIn("turmo_icon.png", (ROOT / spec).read_text(encoding="utf-8"))

    def test_icon_outside_is_transparent(self):
        from PIL import Image
        im = Image.open(ROOT / "assets" / "turmo_icon.png").convert("RGBA")
        self.assertEqual(im.getpixel((2, 2))[3], 0)
        self.assertGreater(im.getpixel((512, 512))[3], 0)


class SidebarGlyphs(unittest.TestCase):
    def test_every_sidebar_entry_has_a_private_use_glyph(self):
        for name in gd.SIDEBAR_ITEMS:
            glyph = gd.SIDEBAR_GLYPHS[name]
            self.assertEqual(len(glyph), 1, name)
            self.assertTrue(0xE000 <= ord(glyph) <= 0xF8FF, name)

    def test_glyphs_are_distinct(self):
        self.assertEqual(len(set(gd.SIDEBAR_GLYPHS.values())), len(gd.SIDEBAR_ITEMS))


class FontChoice(unittest.TestCase):
    def test_first_installed_preferred_family_wins(self):
        available = {"Segoe UI", "Arial"}
        self.assertEqual(gd.pick_family(available, gd.TEXT_FONTS), "Segoe UI")
        self.assertEqual(gd.pick_family({"Segoe UI Variable Text", "Segoe UI"}, gd.TEXT_FONTS),
                         "Segoe UI Variable Text")

    def test_falls_back_when_nothing_matches(self):
        self.assertEqual(gd.pick_family({"Arial"}, gd.TEXT_FONTS), "TkDefaultFont")


class GalleryFilter(unittest.TestCase):
    ALL = ["clean-white", "custom-blank-canvas", "cyberpunk-neon", "futuristic-hud",
           "hardware-dashboard", "matrix-terminal", "minimal-dark", "rgb-gaming"]

    def test_every_official_theme_has_a_category(self):
        for slug in self.ALL:
            self.assertIn(slug, gd.THEME_CATEGORIES)

    def test_category_filter(self):
        self.assertEqual(gd.filter_themes(self.ALL, "Neon"), ["cyberpunk-neon", "rgb-gaming"])
        self.assertEqual(gd.filter_themes(self.ALL, "Light"), ["clean-white"])

    def test_user_themes_are_custom_and_deletable_official_ones_are_not(self):
        slugs = self.ALL + ["cyberpunk-neon-copy"]
        self.assertEqual(gd.filter_themes(slugs, "Custom"), ["custom-blank-canvas", "cyberpunk-neon-copy"])
        self.assertTrue(gd.is_custom_theme("cyberpunk-neon-copy"))
        for slug in self.ALL:
            self.assertFalse(gd.is_custom_theme(slug), slug)  # custom-blank-canvas is the New theme template

    def test_all_and_search(self):
        self.assertEqual(gd.filter_themes(self.ALL, "All"), sorted(self.ALL))
        self.assertEqual(gd.filter_themes(self.ALL, "All", " HUD "), ["futuristic-hud"])


class SensorList(unittest.TestCase):
    def test_every_listed_sensor_has_a_format(self):
        self.assertEqual(len(gd.SENSOR_FORMATS), 8)
        self.assertEqual(gd.metric_text({"cpu.temp": 61.4}, "cpu.temp", gd.SENSOR_FORMATS["cpu.temp"]), "61\u00b0C")
        self.assertEqual(gd.metric_text({}, "net.up", gd.SENSOR_FORMATS["net.up"]), gd.NO_VALUE)

    def test_fahrenheit_converts_temperatures_only(self):
        """v0.2.6.2: Settings > Units > Fahrenheit did nothing; temperatures now show in the chosen unit."""
        fmt = gd.SENSOR_FORMATS["cpu.temp"]
        self.assertEqual(gd.metric_text({"cpu.temp": 59.0}, "cpu.temp", fmt, "fahrenheit"), "138°F")
        self.assertEqual(gd.metric_text({"gpu.temp": 0.0}, "gpu.temp", gd.SENSOR_FORMATS["gpu.temp"], "fahrenheit"), "32°F")
        self.assertEqual(gd.metric_text({"cpu.temp": 59.0}, "cpu.temp", fmt, "celsius"), "59°C")
        self.assertEqual(gd.metric_text({"cpu.temp": 59.0}, "cpu.temp", fmt), "59°C")  # the default
        self.assertEqual(gd.metric_text({"cpu.load": 59.0}, "cpu.load", "{value:.0f}%", "fahrenheit"), "59%")
        self.assertEqual(gd.metric_text({}, "cpu.temp", fmt, "fahrenheit"), gd.NO_VALUE)

    def test_the_meters_show_the_chosen_unit(self):
        from scripts import quick_panel as qp

        class Label:
            text = ""

            def config(self, text):
                self.text = text

        class Bar:
            def delete(self, *a): pass
            def winfo_width(self): return 100
            def create_rectangle(self, *a, **k): pass
        label = Label()
        qp.draw_meter(Bar(), label, 40.0, 50.0, "fahrenheit")
        self.assertEqual(label.text, "40% 122°")
        qp.draw_meter(Bar(), label, 40.0, 50.0)
        self.assertEqual(label.text, "40% 50°")

    def test_rate_unit_follows_the_size(self):
        for value, text in ((0, "0 B/s"), (999, "999 B/s"), (1023, "1023 B/s"), (1024, "1.0 KB/s"), (15793, "15.4 KB/s"),
                            (250_000, "244 KB/s"), (2_500_000, "2.4 MB/s"), (3 * 1024 ** 3, "3.0 GB/s"), (-5, "0 B/s")):
            self.assertEqual(gd.format_rate(value), text)
        self.assertEqual(gd.metric_text({"net.down": 15793}, "net.down", gd.SENSOR_FORMATS["net.down"]), "15.4 KB/s")

    def test_every_sensor_has_a_name(self):
        self.assertEqual(set(gd.SENSOR_NAMES), set(gd.SENSOR_FORMATS))


class QuickPanelPlacement(unittest.TestCase):
    def test_panel_sits_at_the_bottom_right_of_the_work_area(self):
        from scripts import quick_panel as qp
        # taskbar at the bottom: work area is shorter than the screen
        self.assertEqual(qp.panel_position(300, 345, (0, 0, 1920, 1032), (1920, 1080)), (1608, 687))
        # taskbar on the left: the work area starts at x=60
        self.assertEqual(qp.panel_position(300, 345, (60, 0, 1920, 1080), (1920, 1080)), (1608, 735))
        # no work area known: the screen is used; a tiny screen never gives a negative position
        self.assertEqual(qp.panel_position(300, 345, None, (1920, 1080)), (1608, 735))
        self.assertEqual(qp.panel_position(300, 345, (0, 0, 200, 200), (200, 200)), (0, 0))

    def test_read_meters_uses_shared_readings_and_dashes_a_missing_gpu(self):
        import threading
        from scripts import quick_panel as qp

        class Reading:
            def __init__(self, value):
                self.value = value
        app = type("A", (), {})()
        app._psutil_readings = lambda: {"cpu.load": 12.0, "mem.load": 48.0}
        app._preview_lock = threading.Lock()
        app.preview_running = True
        app._preview_readings = {"cpu.temp": Reading(55.0)}
        meters = qp.read_meters(app)
        self.assertEqual(meters, {"cpu": (12.0, 55.0), "gpu": (None, None), "ram": (48.0, None)})
        app.preview_running = False  # stopped: no stale temperatures
        self.assertEqual(qp.read_meters(app)["cpu"], (12.0, None))

    def test_meter_colour_warns_then_turns_critical(self):
        from scripts import quick_panel as qp
        self.assertEqual(qp.meter_colour(10), gd.PALETTE["cyan"])
        self.assertEqual(qp.meter_colour(80), gd.PALETTE["warn"])
        self.assertEqual(qp.meter_colour(95), gd.PALETTE["crit"])


class ExtraSensors(unittest.TestCase):
    def test_names_and_formats_fall_back_for_sensors_outside_the_page_list(self):
        self.assertEqual(gd.sensor_name("gpu.freq"), "GPU clock")
        self.assertEqual(gd.sensor_format("gpu.freq").format(value=1800.4), "1800 MHz")
        self.assertEqual(gd.sensor_name("cpu.load"), "CPU load")
        self.assertEqual(gd.sensor_name("x.y"), "x.y")  # unknown: the key itself
        self.assertEqual(gd.sensor_format("x.y").format(value=2.04), "2.0")
        self.assertEqual(gd.LOCKED_GRAPHS, ("cpu-graph", "gpu-graph", "ram-graph"))


class AppMode(unittest.TestCase):
    def test_light_and_dark_swap_the_shared_palette_and_back(self):
        dark = dict(gd.PALETTE)
        try:
            gd.set_mode("light")
            self.assertEqual(gd.PALETTE["bg0"], "#F4F6FA")
            self.assertNotEqual(gd.PALETTE["text"], dark["text"])
            self.assertEqual(set(gd.LIGHT), set(dark))  # every token has a light value
        finally:
            gd.set_mode("dark")
        self.assertEqual(gd.PALETTE, dark)


if __name__ == "__main__":
    unittest.main(verbosity=2)
