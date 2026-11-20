#!/usr/bin/env python3
"""Dashboard and sidebar logic tests (Tk stubbed: no window, no hardware, no runtime log writes).

Run:  .venv-win\\Scripts\\python.exe scripts\\test_dashboard.py
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import turmo_app_enhanced as app  # noqa: E402
from scripts import gui_design as gd  # noqa: E402


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class NavStub:
    """Stands in for a sidebar NavItem."""

    active = False

    def set_active(self, active):
        self.active = active


class Label:
    """Stands in for a tk widget: remembers the last text/state it was given."""

    def __init__(self):
        self.opts = {}

    def config(self, **kw):
        self.opts.update(kw)

    def cget(self, key):
        return self.opts.get(key, "normal")


class Badge(Label):
    """Stands in for the status Badge: set(text, colour)."""

    def set(self, text, colour):
        self.opts.update(text=text, fg=colour)


class Chip:
    """Stands in for a ThemeChip."""

    active = False

    def set_active(self, active):
        self.active = active


class Canvas:
    def __init__(self):
        self.items = []

    def delete(self, _what):
        self.items = []

    def create_line(self, *pts, **kw):
        self.items.append(("line", pts, kw))

    def create_polygon(self, *pts, **kw):
        self.items.append(("fill", pts, kw))

    def winfo_width(self):
        return 200

    def winfo_height(self):
        return 56


class FakeRoot:
    def __init__(self):
        self.calls = []

    def after(self, ms, cb=None):
        self.calls.append((ms, cb))

    def state(self):
        return "normal"


def make_dash():
    obj = app.TurmoApp.__new__(app.TurmoApp)
    obj.root = FakeRoot()
    obj._startup_log = None
    obj._preview_lock = app.threading.Lock()  # set in TurmoApp.__init__
    obj._preview_readings = {}
    obj.preview_running = True
    obj.port_var = Var("COM4 ✓")
    obj.monitor_status_var = Var("Stopped")
    obj.settings = SimpleNamespace(orientation="landscape", refresh_ms=1000,
                                   brightness=100, theme="cyberpunk-neon", units={"temp": "celsius"},
                                   smooth_pages=False)  # v0.3.6.2: the page change takes no picture in these stubs
    obj.start_btn = Label()
    obj.stop_btn = Label()
    obj.dash_values = {k: Label() for k in ("TURMO port", "Resolution",
                                            "Active theme")}
    obj.dash_state = Badge()
    obj.dash_start = Label()
    obj.dash_stop = Label()
    obj.dash_chips = {slug: Chip() for slug, _l, _c in gd.QUICK_THEMES}
    obj.dash_metrics = {}
    obj._dash_hist = {k: app.deque(maxlen=60) for k in ("cpu.load", "cpu.temp", "gpu.load", "mem.load", "net.mbs")}
    return obj


class DashboardStatus(unittest.TestCase):
    def test_connected_when_the_port_is_found(self):
        obj = make_dash()
        obj._refresh_dashboard_status()
        self.assertEqual(obj.dash_state.opts["text"], "Connected")
        self.assertEqual(obj.dash_values["TURMO port"].opts["text"], "COM4")

    def test_monitor_running_overrides_the_port_state(self):
        obj = make_dash()
        obj.monitor_status_var.set("Running (started outside this window, PID 1)")
        link = {"state": "connected", "port": "COM4", "attempt": 0, "since": 0.0}
        with mock.patch.object(app, "read_link_status", return_value=link):
            obj._refresh_dashboard_status()
        self.assertEqual(obj.dash_state.opts["text"], "Monitor running")

    def test_monitor_running_but_not_yet_connected_says_connecting(self):
        obj = make_dash()
        obj.monitor_status_var.set("Running (PID 1)")
        with mock.patch.object(app, "read_link_status", return_value=None):
            obj._refresh_dashboard_status()
        self.assertEqual(obj.dash_state.opts["text"], "Connecting…")

    def test_busy_and_missing_ports(self):
        obj = make_dash()
        obj.port_var.set("Busy / In Use ⚠")
        obj._refresh_dashboard_status()
        self.assertEqual(obj.dash_state.opts["text"], "Busy")
        obj.port_var.set("Not found ✗")
        obj._refresh_dashboard_status()
        self.assertEqual(obj.dash_state.opts["text"], "Disconnected")

    def test_portrait_resolution_and_active_theme_chip(self):
        obj = make_dash()
        obj.settings.orientation = "portrait"
        obj._refresh_dashboard_status()
        self.assertEqual(obj.dash_values["Resolution"].opts["text"], "320 × 480")
        self.assertTrue(obj.dash_chips["cyberpunk-neon"].active)
        self.assertFalse(obj.dash_chips["matrix-terminal"].active)

    def test_start_and_stop_follow_the_monitor_buttons(self):
        obj = make_dash()
        obj.start_btn.config(state="disabled")
        obj.stop_btn.config(state="normal")
        obj._refresh_dashboard_status()
        self.assertEqual(obj.dash_start.opts["state"], "disabled")
        self.assertEqual(obj.dash_stop.opts["state"], "normal")


class DashboardMetrics(unittest.TestCase):
    def test_no_preview_and_no_psutil_shows_dashes(self):
        obj = make_dash()
        with mock.patch.dict("sys.modules", {"psutil": None}):
            obj._refresh_dashboard_metrics()
        # with psutil unavailable the cards stay empty; the readings path gives dashes
        obj.dash_metrics = {"cpu.temp": (Label(), Canvas(), "#fff", "{value:.0f}°C", "cpu.temp", 100),
                            "cpu.load": (Label(), Canvas(), "#fff", "{value:.0f}%", "cpu.load", 100)}
        with mock.patch.dict("sys.modules", {"psutil": None}):
            obj._refresh_dashboard_metrics()
        self.assertEqual(obj.dash_metrics["cpu.temp"][0].opts["text"], gd.NO_VALUE)
        self.assertEqual(obj.dash_metrics["cpu.load"][0].opts["text"], gd.NO_VALUE)

    def test_preview_caption_follows_orientation_and_running_state(self):
        obj = make_dash()
        obj.preview_caption = Label()
        obj._refresh_preview_caption()
        self.assertEqual(obj.preview_caption.opts["text"], "Landscape · 480 × 320 · Preview running")
        obj.settings.orientation, obj.preview_running = "portrait", False
        obj._refresh_preview_caption()
        self.assertEqual(obj.preview_caption.opts["text"], "Portrait · 320 × 480 · Preview stopped")
        del obj.preview_caption  # a tab not built yet: no error
        obj._refresh_preview_caption()

    def test_readings_of_a_stopped_preview_are_not_shown(self):
        obj = make_dash()
        obj._preview_readings = {"cpu.temp": SimpleNamespace(value=61.4)}
        obj.preview_running = False
        obj.dash_metrics = {"cpu.temp": (Label(), Canvas(), "#fff", "{value:.0f}°C", "cpu.temp", 100)}
        with mock.patch.dict("sys.modules", {"psutil": None}):
            obj._refresh_dashboard_metrics()
        self.assertEqual(obj.dash_metrics["cpu.temp"][0].opts["text"], gd.NO_VALUE)

    def test_the_dashboard_follows_the_temperature_unit(self):
        """v0.2.6.2: Fahrenheit in Settings > Units used to change nothing."""
        obj = make_dash()
        obj._preview_readings = {"cpu.load": SimpleNamespace(value=40.0), "cpu.temp": SimpleNamespace(value=61.4)}
        value_temp = Label()
        obj.dash_metrics = {"cpu.temp": (value_temp, Canvas(), "#F59E0B", "{value:.0f}°C", "cpu.temp", 100)}
        obj.settings.units["temp"] = "fahrenheit"
        obj._refresh_dashboard_metrics()
        self.assertEqual(value_temp.opts["text"], "143°F")  # 61.4 C = 142.5 F
        obj.temp_unit_var = SimpleNamespace(get=lambda: "celsius")  # the page's choice wins before it is saved
        obj._refresh_dashboard_metrics()
        self.assertEqual(value_temp.opts["text"], "61°C")

    def test_live_readings_are_formatted_and_drawn(self):
        obj = make_dash()
        obj._preview_readings = {"cpu.load": SimpleNamespace(value=40.0),
                                 "cpu.temp": SimpleNamespace(value=61.4),
                                 "net.down": SimpleNamespace(value=2_500_000)}
        value_load, canvas_load = Label(), Canvas()
        value_temp, canvas_temp = Label(), Canvas()
        value_net, canvas_net = Label(), Canvas()
        obj.dash_metrics = {
            "cpu.load": (value_load, canvas_load, "#22D3EE", "{value:.0f}%", "cpu.load", 100),
            "cpu.temp": (value_temp, canvas_temp, "#F59E0B", "{value:.0f}°C", "cpu.temp", 100),
            "net.mbs": (value_net, canvas_net, "#22C55E", "rate", "net.mbs", None),
        }
        obj._refresh_dashboard_metrics()
        self.assertEqual(value_load.opts["text"], "40%")
        self.assertEqual(value_temp.opts["text"], "61°C")
        self.assertEqual(value_net.opts["text"], "2.4 MB/s")  # bytes per second, unit chosen by size
        self.assertEqual(len(canvas_load.items), 0)  # one sample is not a line yet
        obj._refresh_dashboard_metrics()
        self.assertEqual([i[0] for i in canvas_load.items], ["fill", "line"])  # two samples: area and line
        self.assertEqual([i[0] for i in canvas_temp.items], ["fill", "line"])  # temperature has a history too

    def test_psutil_fills_the_loads_when_preview_is_off(self):
        obj = make_dash()
        obj.dash_metrics = {"cpu.load": (Label(), Canvas(), "#22D3EE", "{value:.0f}%", "cpu.load", 100)}
        fake = SimpleNamespace(cpu_percent=lambda interval=None: 17.2,
                               virtual_memory=lambda: SimpleNamespace(percent=55.0, used=8 * 1024 ** 3))
        with mock.patch.dict("sys.modules", {"psutil": fake}):
            obj._refresh_dashboard_metrics()
        self.assertEqual(obj.dash_metrics["cpu.load"][0].opts["text"], "17%")


class DashboardLoop(unittest.TestCase):
    def test_refresh_reschedules_even_when_a_step_fails(self):
        obj = make_dash()
        obj.dash_values = {}  # forces an error inside _refresh_dashboard_status
        obj._refresh_dashboard_status = mock.Mock(side_effect=RuntimeError("boom"))
        obj._refresh_dashboard_metrics = mock.Mock()
        with mock.patch.object(app, "log_startup"):
            obj._refresh_dashboard()
        self.assertEqual(obj.root.calls[-1][0], 1000)


class SidebarSelection(unittest.TestCase):
    def test_sidebar_highlights_the_current_tab(self):
        obj = make_dash()
        obj._sidebar_items = [NavStub() for _ in gd.SIDEBAR_ITEMS]
        obj.nb = mock.Mock()
        obj.nb.index.return_value = 2
        obj._sync_sidebar()
        self.assertEqual([i.active for i in obj._sidebar_items],
                         [n == 2 for n in range(len(gd.SIDEBAR_ITEMS))])

    def test_select_tab_drives_the_notebook(self):
        obj = make_dash()
        obj._sidebar_items = [NavStub() for _ in gd.SIDEBAR_ITEMS]
        obj.nb = mock.Mock()
        obj.nb.index.return_value = 1
        obj.select_tab(1)
        obj.nb.select.assert_called_with(1)

    def test_sidebar_items_match_notebook_tabs(self):
        # the sidebar index is the notebook tab index: Dashboard is built first
        self.assertEqual(gd.SIDEBAR_ITEMS[0], "Dashboard")
        self.assertEqual(gd.SIDEBAR_ITEMS[1], "Monitor")

    def test_device_chip_follows_the_port_and_the_monitor(self):
        obj = make_dash()
        obj._device_chip = SimpleNamespace(calls=[], set_status=lambda text, level: obj._device_chip.calls.append((text, level)))
        obj._refresh_device_chip()
        obj.port_var.set("Busy / In Use ⚠")
        obj._refresh_device_chip()
        obj.port_var.set("Not found ✗")
        obj._refresh_device_chip()
        self.assertEqual(obj._device_chip.calls,
                         [("TURMO · COM4", "ok"), ("COM port busy", "busy"), ("No device", "off")])


class PreviewPanel(unittest.TestCase):
    def test_orientation_button_flips_the_setting_through_the_existing_handler(self):
        obj = make_dash()
        obj.landscape_var = Var(True)
        obj.on_orientation_change = mock.Mock()
        obj._refresh_dashboard_status = mock.Mock()
        obj._toggle_dash_orientation()  # landscape now: asks for portrait
        self.assertFalse(obj.landscape_var.get())
        obj.settings.orientation = "portrait"
        obj._toggle_dash_orientation()  # portrait now: asks for landscape
        self.assertTrue(obj.landscape_var.get())
        self.assertEqual(obj.on_orientation_change.call_count, 2)


class QuickTheme(unittest.TestCase):
    def test_chip_sets_the_theme_and_saves_it(self):
        obj = make_dash()
        obj.theme_var = Var("cyberpunk-neon")
        obj.on_theme_change = mock.Mock()
        obj._refresh_dashboard_status = mock.Mock()
        obj._refresh_dashboard = mock.Mock()
        obj.apply_quick_theme("matrix-terminal")
        self.assertEqual(obj.theme_var.get(), "matrix-terminal")
        obj.on_theme_change.assert_called_once()
        obj._refresh_dashboard_status.assert_called_once()
        obj._refresh_dashboard.assert_not_called()  # it would add another 1 s loop


if __name__ == "__main__":
    unittest.main(verbosity=2)
