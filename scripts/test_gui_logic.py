#!/usr/bin/env python3
"""GUI logic regression tests (Tk is stubbed: no window, no hardware, no runtime log writes).

Run:  .venv-win\\Scripts\\python.exe scripts\\test_gui_logic.py

Checks:
  * finding TURMO Monitor processes from process rows (frozen exe, source worker,
    unrelated processes ignored);
  * Live Preview generations: a restart leaves no active older worker or UI tick;
  * the Monitor status shows a Monitor started outside the window, and the Stop button
    stops it only when the user asks (button or restart), never on quit;
  * a PID this window just stopped is not reported as "outside" while it exits;
  * Start refuses while a Monitor started outside holds COM4.

This is logic coverage with Tk stubbed. The real window is checked by hand (see the
v0.1.6 verification notes).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import turmo_app_enhanced as app  # noqa: E402


def patch_everywhere(name, value):
    """mock.patch for a name the app's code and the page modules (theme_editor, gallery_page, gui_common, ...) each bound when they
    star-imported gui_common (v0.2.3): patching only `app` would leave the moved code on the real value (a test once
    wrote into the real themes folder that way). Every module that still holds the original object is patched."""
    import contextlib
    orig = getattr(app, name)
    stack = contextlib.ExitStack()
    for mod in list(sys.modules.values()):
        modname = getattr(mod, "__name__", "") or ""
        if (modname.startswith("scripts.") or modname == "turmo_app_enhanced") and getattr(mod, name, None) is orig:
            stack.enter_context(mock.patch.object(mod, name, value))
    return stack

def custom(root):
    """The custom themes folder when %APPDATA% is root/appdata (see patch_roots)."""
    return root / "appdata" / "TURMO" / "themes" / "custom"


def patch_roots(root):
    """DATA_ROOT is `root` (the official themes are root/themes) and %APPDATA% is root/appdata, so the themes the user
    makes land in custom(root): a test never touches the real settings or custom themes."""
    import contextlib
    stack = contextlib.ExitStack()
    stack.enter_context(patch_everywhere("DATA_ROOT", root))
    stack.enter_context(mock.patch.dict(os.environ, {"APPDATA": str(root / "appdata")}))
    return stack


_patches = []
_tmp_appdata = None


class _EverywhereStack:
    """start()/stop() wrapper so setUpModule can treat patch_everywhere like any other patcher."""

    def __init__(self, name):
        self.name, self.stack = name, None

    def start(self):
        self.stack = patch_everywhere(self.name, mock.Mock())
        self.stack.__enter__()

    def stop(self):
        self.stack.__exit__(None, None, None)


def setUpModule():
    """Keep the tests away from the real runtime log, real APPDATA and real COM ports."""
    global _tmp_appdata
    _tmp_appdata = tempfile.mkdtemp(prefix="turmo-test-appdata-")
    for target, kwargs in (
        (_EverywhereStack("_log_event"), {}),  # the page modules hold their own copy
        (mock.patch.object(app, "find_turmo_port", return_value=None), {}),
        # LOCALAPPDATA too: a save now writes the theme mirror from source as well (v0.2.3), the real one feeds the exe
        (mock.patch.dict(os.environ, {"APPDATA": _tmp_appdata, "LOCALAPPDATA": _tmp_appdata}), {}),
        (mock.patch.object(app.time, "sleep"), {}),
    ):
        _patches.append(target)
        target.start()


def tearDownModule():
    for p in reversed(_patches):
        p.stop()
    shutil.rmtree(_tmp_appdata, ignore_errors=True)


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Widget:
    def __init__(self):
        self.state = None

    def config(self, state=None, **_):
        if state is not None:
            self.state = state


class TextStub:
    def __init__(self):
        self.text = []

    def insert(self, _index, s):
        self.text.append(s)

    def see(self, _index):
        pass


class FakeRoot:
    def __init__(self):
        self.calls = []
        self.window_state = "normal"

    def state(self):
        return self.window_state

    def after(self, ms, callback=None):
        self.calls.append((ms, callback))

    def update(self):
        pass

    def update_idletasks(self):
        pass

    def quit(self):
        pass


class FakeThread:
    def __init__(self, *args, **kwargs):
        self.started = False

    def start(self):
        self.started = True

    def is_alive(self):
        return False


def make_app():
    """A TurmoApp without Tk: only the attributes the logic under test uses."""
    obj = app.TurmoApp.__new__(app.TurmoApp)
    obj.root = FakeRoot()
    obj.toast = mock.Mock()  # the in-app notice replaces message boxes
    obj.status_var = Var()
    obj.port_var = Var("")
    obj.monitor_status_var = Var("Stopped")
    obj.start_btn = Widget()
    obj.start_btn.state = "normal"  # the GUI starts with Start enabled, Stop disabled
    obj.stop_btn = Widget()
    obj.stop_btn.state = "disabled"
    obj.log_text = TextStub()
    obj.port_override_var = Var("")
    obj.monitor_process = None
    obj._ignored_pids = set()
    obj.preview_running = False
    obj._preview_ready = False
    obj._preview_worker_thread = None
    obj._write_stop_request = mock.Mock(name="_write_stop_request")
    return obj


class FakeProcess:
    """Stands in for the Popen of a Monitor this window started."""

    def __init__(self, pid):
        self.pid = pid

    def poll(self):
        return 0  # already exited: stop_monitor needs no waiting

    def wait(self, timeout=None):
        return 0


class EditorColour(unittest.TestCase):
    def test_alpha_hex_is_shown_without_alpha(self):
        self.assertEqual(app.tk_colour("#ff2bd644"), "#ff2bd6")
        self.assertEqual(app.tk_colour("#ff2bd6"), "#ff2bd6")
        self.assertEqual(app.tk_colour("red"), "red")


class EditorOrientationFolder(unittest.TestCase):
    def test_portrait_saves_into_the_320x480_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("demo", "demo-320x480"):
                (Path(tmp) / "themes" / name).mkdir(parents=True)
            editor = app.ThemeEditor.__new__(app.ThemeEditor)
            editor.theme_name, editor._shown = "demo", "landscape"
            with patch_everywhere("DATA_ROOT", Path(tmp)):
                self.assertEqual(editor.theme_dir().name, "demo")
                self.assertEqual(editor.theme_dir("portrait").name, "demo-320x480")
                (Path(tmp) / "themes" / "demo-320x480").rmdir()  # no portrait version: falls back
                self.assertEqual(editor.theme_dir("portrait").name, "demo")


class EditorThemeName(unittest.TestCase):
    def test_name_box_becomes_a_folder_name(self):
        editor = app.ThemeEditor.__new__(app.ThemeEditor)
        for typed, slug in (("My Théme!", "my-theme"), ("", "custom-theme"), ("  ", "custom-theme"),
                            ("neon-320x480", "neon")):
            editor.name_var = mock.Mock(get=lambda t=typed: t)
            self.assertEqual(editor.name_slug(), slug)


class NewThemeAndImport(unittest.TestCase):
    """New theme is an unsaved draft; saving never overwrites another theme or a built-in; import loads a file."""

    def _editor(self, root, loaded="custom-blank-canvas", typed="custom-2026-11-17"):
        for name in ("custom-blank-canvas", "custom-blank-canvas-320x480", "mine", "mine-320x480", "cyberpunk-neon"):
            d = (custom(root) if name.startswith("mine") else root / "themes") / name  # "mine" is the user's theme
            d.mkdir(parents=True)
            (d / "theme.json").write_text('{"name": "x", "palette": {"accent": "#111111"}, "widgets": ['
                                          '{"type": "rect", "id": "backdrop", "locked": true},'
                                          '{"type": "clock", "id": "clock", "x": 1}]}', encoding="utf-8")
        ed = app.ThemeEditor.__new__(app.ThemeEditor)
        ed.app = mock.Mock()
        ed.theme_name, ed._named, ed._shown, ed._stash = loaded, loaded, "landscape", {}
        ed._pending_palette = None
        ed.name_var = Var(typed)
        ed.widgets = [app.WidgetConfig(id="clock", type="clock", x=0, y=0)]
        ed.current_orientation = lambda: "landscape"
        return ed

    def _root(self):
        root = Path(tempfile.mkdtemp(prefix="turmo-test-new-"))
        self.addCleanup(shutil.rmtree, root, True)
        return root

    def test_unique_name_adds_a_number(self):
        from scripts.gui_design import unique_theme_name
        taken = {"a", "a-2"}
        self.assertEqual(unique_theme_name(taken.__contains__, "a"), "a-3")
        self.assertEqual(unique_theme_name(taken.__contains__, "b"), "b")

    def test_draft_writes_nothing_and_suggests_a_free_date_name(self):
        root = self._root()
        ed = self._editor(root)
        ed.load_current_theme = mock.Mock()
        (custom(root) / "custom-2026-11-17").mkdir(parents=True)  # an existing theme of the user (a folder with its theme.json)
        (custom(root) / "custom-2026-11-17" / "theme.json").write_text("{}")
        before = sorted(str(p) for p in root.rglob("*"))
        with patch_roots(root),                 patch_everywhere("datetime", mock.Mock(now=lambda: __import__("datetime").datetime(2026, 11, 17))):
            ed.start_draft()
        self.assertEqual(sorted(str(p) for p in root.rglob("*")), before)
        self.assertEqual(ed.name_var.get(), "custom-2026-11-17-2")

    def test_saving_a_draft_creates_both_orientations(self):
        root = self._root()
        ed = self._editor(root, typed="My New One")
        with patch_roots(root):
            ed.save_theme()
        self.assertTrue((custom(root) / "my-new-one" / "theme.json").is_file())
        self.assertTrue((custom(root) / "my-new-one-320x480" / "theme.json").is_file())
        self.assertFalse((root / "themes" / "my-new-one").exists(), "a user theme never goes into the official folder")

    def test_the_gallery_title_follows_the_name_box_in_both_orientations(self):
        """Saved from the portrait view, the landscape file (the one a Gallery card reads) must get the title too."""
        import json
        root = self._root()
        ed = self._editor(root, typed="My New One")
        ed.current_orientation = lambda: "portrait"
        with patch_roots(root):
            ed.save_theme()
        for folder in ("my-new-one", "my-new-one-320x480"):
            data = json.loads((custom(root) / folder / "theme.json").read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "my-new-one", folder)

    def test_a_name_already_used_is_refused(self):
        root = self._root()
        ed = self._editor(root, typed="mine")  # another theme, not the one loaded
        with patch_roots(root):
            ed.save_theme()
        self.assertIn("already exists", ed.app.toast.call_args.args[0])
        self.assertEqual(ed.theme_name, "custom-blank-canvas")

    def test_a_new_theme_draft_cannot_take_the_name_of_the_theme_it_started_from(self):
        root = self._root()
        ed = self._editor(root, loaded="mine", typed="x")
        ed.load_current_theme = mock.Mock()
        ed.current_orientation = lambda: "portrait"
        with patch_roots(root):
            ed.start_draft()
            for typed in ("Custom Blank Canvas", "custom-blank-canvas-320x480", "mine"):
                ed.name_var.set(typed)
                ed.save_theme()
                self.assertIn("already exists", ed.app.toast.call_args.args[0], typed)
            self.assertFalse(list(root.rglob("theme.json.bak")), "nothing was overwritten")
            ed.name_var.set("brand new")
            ed.save_theme()
            self.assertTrue((custom(root) / "brand-new" / "theme.json").is_file())
            ed.name_var.set("brand new")  # saved once: it is a real theme now and can be saved again under its name
            ed.save_theme()
            self.assertIn("Theme saved", ed.app.toast.call_args.args[0])

    def test_a_built_in_theme_cannot_be_saved_over(self):
        root = self._root()
        ed = self._editor(root, loaded="cyberpunk-neon", typed="cyberpunk-neon")
        with patch_roots(root):
            ed.save_theme()
        self.assertIn("Built-in", ed.app.toast.call_args.args[0])
        self.assertFalse((root / "themes" / "cyberpunk-neon" / "theme.json.bak").exists())

    def test_the_custom_blank_canvas_can_be_edited_and_the_edit_goes_to_the_custom_folder(self):
        root = self._root()
        ed = self._editor(root, loaded="custom-blank-canvas", typed="custom-blank-canvas")
        with patch_roots(root):
            ed.save_theme()
        self.assertTrue((custom(root) / "custom-blank-canvas" / "theme.json.bak").exists())
        self.assertFalse((root / "themes" / "custom-blank-canvas" / "theme.json.bak").exists(), "the official copy stays")
        from scripts.gui_design import is_custom_theme, is_editable_theme
        self.assertFalse(is_custom_theme("custom-blank-canvas"))  # so it still cannot be deleted
        self.assertTrue(is_editable_theme("custom-blank-canvas"))

    def test_own_theme_can_be_saved_again_under_its_name(self):
        root = self._root()
        ed = self._editor(root, loaded="mine", typed="mine")
        with patch_roots(root):
            ed.save_theme()
        self.assertTrue((custom(root) / "mine" / "theme.json.bak").exists())

    def test_import_loads_widgets_and_palette_under_a_free_name(self):
        root = self._root()
        ed = self._editor(root)
        ed.redraw_canvas = mock.Mock()
        f = root / "mine.json"
        f.write_text('﻿{"name": "Mine", "palette": {"accent": "#abcdef"}, "widgets": ['
                     '{"type": "text", "id": "t1", "text": "héllo"}]}', encoding="utf-8")
        with patch_roots(root),                 mock.patch.object(app.filedialog, "askopenfilename", return_value=str(f)):
            ed.import_json()
        self.assertEqual([w.id for w in ed.widgets], ["t1"])
        self.assertEqual(ed._pending_palette, {"accent": "#abcdef"})
        self.assertEqual(ed.name_var.get(), "mine-2")  # "mine" is taken
        self.assertIn("Imported", ed.app.toast.call_args.args[0])

    def test_import_of_a_bad_file_keeps_the_layout_and_says_why(self):
        root = self._root()
        ed = self._editor(root)
        keep = list(ed.widgets)
        f = root / "bad.json"
        f.write_text("not json", encoding="utf-8")
        with mock.patch.object(app.filedialog, "askopenfilename", return_value=str(f)):
            ed.import_json()
        self.assertEqual(ed.widgets, keep)
        self.assertEqual(ed.app.toast.call_args.args[1], "error")


class PsutilReadings(unittest.TestCase):
    def test_one_cpu_read_per_tick_is_shared(self):
        import types
        obj = types.SimpleNamespace(_startup_log=None, preview_running=False, _window_hidden=lambda: False,
                                    _update_poll_on=lambda: None, _sensor_poller=lambda: None)  # no poller: CPU load and RAM only
        fake = mock.MagicMock()
        fake.cpu_percent.return_value = 12.0
        fake.virtual_memory.return_value = mock.Mock(percent=40.0, used=2 * 1024 ** 3)
        with mock.patch.dict(sys.modules, {"psutil": fake}):
            first = app.TurmoApp._psutil_readings(obj)
            second = app.TurmoApp._psutil_readings(obj)
        self.assertEqual(fake.cpu_percent.call_count, 1)
        self.assertEqual(first, second)
        self.assertEqual(first["mem.used"], 2.0)


class MonitorProcessRows(unittest.TestCase):
    def test_finds_frozen_and_source_monitors_only(self):
        rows = [
            (100, "TURMO-Monitor.exe", "", 1),
            (101, "python.exe", "python.exe scripts\\turmo_runtime.py --monitor", 1),
            (102, "python.exe", "python.exe other_tool.py", 1),
            (103, "TURMO-Display-Control.exe", "", 1),
            (104, "chrome.exe", "", 1),
        ]
        self.assertEqual(app._turmo_monitor_pids(rows), [100, 101])

    def test_bootloader_child_pair_counts_once(self):
        # one-file exe: bootloader 300 (parent 1) runs worker 301 with the same name
        rows = [(300, "TURMO-Monitor.exe", "", 1), (301, "TURMO-Monitor.exe", "", 300)]
        self.assertEqual(app._turmo_monitor_pids(rows), [300])

    def test_no_monitor_gives_empty_list(self):
        self.assertEqual(app._turmo_monitor_pids([(1, "explorer.exe", "", 1)]), [])


class PreviewGenerations(unittest.TestCase):
    def test_restart_makes_the_old_generation_stale(self):
        obj = make_app()
        with mock.patch.object(app.threading, "Thread", FakeThread):
            obj.start_preview()
            first = obj._preview_gen
            obj.stop_preview()
            obj.start_preview()
            second = obj._preview_gen
        self.assertEqual((first, second), (1, 2))
        self.assertTrue(obj.preview_running)

        # A UI tick from the first start must stop without rescheduling itself.
        calls_before = len(obj.root.calls)
        obj._preview_ui_tick(first)
        self.assertEqual(len(obj.root.calls), calls_before)

        # A UI tick from the current start keeps going.
        obj._preview_ui_tick(second)
        self.assertGreater(len(obj.root.calls), calls_before)

    def test_stop_clears_the_running_flag(self):
        obj = make_app()
        with mock.patch.object(app.threading, "Thread", FakeThread):
            obj.start_preview()
            obj.stop_preview()
        self.assertFalse(obj.preview_running)


class ProcessScan(unittest.TestCase):
    def test_scan_reads_parents_in_one_snapshot_not_per_process(self):
        import psutil
        seen = {}
        real = psutil.process_iter

        def spy(attrs=None, *a, **k):
            seen["attrs"] = list(attrs or [])
            return real(attrs, *a, **k)
        with mock.patch.object(psutil, "process_iter", spy):
            rows = app._process_rows()
        self.assertNotIn("ppid", seen["attrs"])  # per-process ppid cost 5 s on the first scan
        self.assertTrue(all(isinstance(r[3], int) for r in rows))

    def test_rows_find_this_python_with_its_real_parent(self):
        import os
        mine = [r for r in app._process_rows() if r[0] == os.getpid()]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0][3], os.getppid())


class LinkAnnouncements(unittest.TestCase):
    def run_states(self, states):
        obj = make_app()
        obj.toasts, obj.tray_icon = [], None
        obj.toast = lambda text, kind="info": obj.toasts.append((text, kind))
        for state in states:
            obj._link_read_at = -9.0
            link = {"state": state, "port": "COM4", "attempt": 0, "since": 0.0} if state else None
            with mock.patch.object(app, "read_link_status", return_value=link):
                obj._link_state()
        return obj.toasts

    def test_a_lost_link_and_its_return_each_toast_once(self):
        got = self.run_states(["connected", "retrying", "retrying", "not_found", "connected", "connected"])
        self.assertEqual([k for _t, k in got], ["error", "info"])

    def test_a_display_powered_on_late_says_so_but_a_stopped_monitor_stays_silent(self):
        self.assertEqual(self.run_states(["not_found", "connected"]), [("Display connected again", "info")])
        self.assertEqual(self.run_states(["not_found"]), [])  # never up: nothing was lost
        self.assertEqual(self.run_states(["connected", None, "connected"]), [])


class LinkPortRow(unittest.TestCase):
    def test_a_display_found_by_the_monitor_replaces_a_stale_not_found(self):
        obj = make_app()
        obj.port_var.set("Not found ✗")
        link = {"state": "connected", "port": "COM4", "attempt": 0, "since": 0.0}
        with mock.patch.object(app, "read_link_status", return_value=link):
            obj._link_state()
        self.assertEqual(obj.port_var.get(), "COM4 ✓")


class PortWatch(unittest.TestCase):
    def tick(self, obj, found):
        with mock.patch.object(app, "find_turmo_port", return_value=found):
            obj._watch_port()  # starts the thread
            while obj._port_probe["busy"]:
                time.sleep(0.01)
            obj._watch_port()  # applies its answer

    def test_a_display_plugged_in_after_start_turns_not_found_into_connected(self):
        obj = make_app()
        obj.port_var.set("Not found ✗")
        self.tick(obj, "COM4")
        self.assertEqual(obj.port_var.get(), "COM4 ✓")

    def test_a_display_unplugged_turns_connected_into_not_found(self):
        obj = make_app()
        obj.port_var.set("COM4 ✓")
        self.tick(obj, None)
        self.assertEqual(obj.port_var.get(), "Not found ✗")

    def test_busy_is_left_alone_and_a_failing_scan_changes_nothing(self):
        obj = make_app()
        obj.port_var.set("Busy / In Use ⚠")
        self.tick(obj, None)
        self.assertEqual(obj.port_var.get(), "Busy / In Use ⚠")
        with mock.patch.object(app, "find_turmo_port", side_effect=OSError("scan failed")):
            obj._watch_port()
            while obj._port_probe["busy"]:
                time.sleep(0.01)
            obj._watch_port()
        self.assertEqual(obj.port_var.get(), "Busy / In Use ⚠")


class FirstRun(unittest.TestCase):
    def test_a_fresh_install_shows_it_once_and_writes_the_settings_file(self):
        obj = make_app()
        obj._first_run = True
        obj.settings = mock.Mock()
        obj.show_first_run = mock.Mock()
        obj.start_first_run()
        obj.settings.save.assert_called_once()
        obj.show_first_run.assert_called_once()
        obj.start_first_run()  # a second call does nothing
        obj.show_first_run.assert_called_once()

    def test_the_guard_shows_it_again_until_done_and_not_while_another_dialog_is_open(self):
        obj = make_app()
        obj._first_run_done = False
        obj.show_first_run = mock.Mock()
        obj._modal = object()  # an alert is open
        obj._first_run_guard()
        obj.show_first_run.assert_not_called()
        obj._modal = None  # the alert was closed
        obj._first_run_guard()
        obj.show_first_run.assert_called_once()
        obj._first_run_done = True
        obj._first_run_guard()
        obj.show_first_run.assert_called_once()  # Done was pressed: it stays closed

    def test_the_dialog_has_no_way_out_but_done(self):
        text = (Path(app.__file__).parent / "first_run.py").read_text(encoding="utf-8")
        self.assertIn("dismissable=False", text)
        modal = (Path(app.__file__).parent / "modal.py").read_text(encoding="utf-8")
        self.assertIn("if dismissable:", modal)

    def test_an_existing_install_never_shows_it(self):
        obj = make_app()
        obj._first_run = False
        obj.show_first_run = mock.Mock()
        obj.start_first_run()
        obj.show_first_run.assert_not_called()

    def test_a_failure_in_the_dialog_is_swallowed_and_logged(self):
        obj = make_app()
        obj._first_run = True
        obj.settings = mock.Mock()
        obj.show_first_run = mock.Mock(side_effect=RuntimeError("boom"))
        obj.start_first_run()  # must not raise

    def test_the_helper_check_is_false_when_nothing_listens(self):
        import scripts.first_run as fr
        with mock.patch("socket.create_connection", side_effect=OSError("refused")):
            self.assertFalse(fr.cpu_helper_running())

    def test_the_launch_decides_from_the_settings_file(self):
        text = (Path(app.__file__)).read_text(encoding="utf-8")
        self.assertIn("self._first_run = not Settings.path().exists()", text)


class MonitorStatus(unittest.TestCase):
    def test_monitor_started_outside_is_shown_and_stop_is_enabled(self):
        obj = make_app()
        rows = [(4242, "TURMO-Monitor.exe", "", 1)]
        with mock.patch.object(app, "_process_rows", return_value=rows):
            obj._refresh_monitor_state()
        self.assertTrue(obj.monitor_status_var.get().startswith("Running"))
        self.assertIn("4242", obj.monitor_status_var.get())
        self.assertEqual(obj.start_btn.state, "disabled")
        self.assertEqual(obj.stop_btn.state, "normal")

    def test_status_returns_to_stopped_when_no_monitor(self):
        obj = make_app()
        obj.monitor_status_var.set("Running (started outside this window, PID 4242)")
        with mock.patch.object(app, "_process_rows", return_value=[]):
            obj._refresh_monitor_state()
        self.assertEqual(obj.monitor_status_var.get(), "Stopped")
        self.assertEqual(obj.start_btn.state, "normal")
        self.assertEqual(obj.stop_btn.state, "disabled")

    def test_refresh_reschedules_itself(self):
        obj = make_app()
        with mock.patch.object(app, "_process_rows", return_value=[]):
            obj._refresh_monitor_state()
        self.assertEqual(obj.root.calls[-1][0], 2000)

    def test_pid_this_window_just_stopped_is_not_reported_as_outside(self):
        obj = make_app()
        obj._ignored_pids = {4242}
        with mock.patch.object(app, "_process_rows", return_value=[(4242, "TURMO-Monitor.exe", "", 1)]):
            obj._refresh_monitor_state()
        self.assertEqual(obj.monitor_status_var.get(), "Stopped")
        self.assertEqual(obj.start_btn.state, "normal")
        self.assertEqual(obj._ignored_pids, {4242})  # still exiting: kept

    def test_ignored_pid_is_forgotten_once_gone(self):
        obj = make_app()
        obj._ignored_pids = {4242}
        with mock.patch.object(app, "_process_rows", return_value=[]):
            obj._refresh_monitor_state()
        self.assertEqual(obj._ignored_pids, set())


class StopOutsideMonitor(unittest.TestCase):
    def _stop(self, obj, reason, pid_alive):
        rows = [(4242, "TURMO-Monitor.exe", "", 1)]
        with mock.patch.object(app, "_process_rows", return_value=rows), \
                mock.patch("psutil.pid_exists", return_value=pid_alive), \
                mock.patch.object(app.subprocess, "run") as run:
            obj.stop_monitor(reason=reason)
        return run

    def test_stop_button_asks_the_outside_monitor_to_stop(self):
        obj = make_app()
        run = self._stop(obj, "button", pid_alive=False)
        obj._write_stop_request.assert_called_once()
        run.assert_not_called()
        self.assertIn(4242, obj._ignored_pids)
        self.assertEqual(obj.monitor_status_var.get(), "Stopped")

    def test_restart_also_stops_the_outside_monitor(self):
        obj = make_app()
        self._stop(obj, "restart", pid_alive=False)
        obj._write_stop_request.assert_called_once()

    def test_quit_does_not_stop_a_monitor_started_by_hand(self):
        obj = make_app()
        self._stop(obj, "quit", pid_alive=False)
        obj._write_stop_request.assert_not_called()

    def test_outside_monitor_that_ignores_the_request_is_forced(self):
        obj = make_app()
        run = self._stop(obj, "button", pid_alive=True)
        obj._write_stop_request.assert_called_once()
        run.assert_called_once()
        self.assertEqual(run.call_args[0][0], ["taskkill", "/F", "/T", "/PID", "4242"])

    def test_own_monitor_stop_ignores_its_pid_while_exiting(self):
        obj = make_app()
        obj.monitor_process = FakeProcess(5150)
        with mock.patch.object(app, "_process_rows", return_value=[(5150, "TURMO-Monitor.exe", "", 1)]):
            obj.stop_monitor(reason="button")
            obj._refresh_monitor_state()
        self.assertIn(5150, obj._ignored_pids)
        self.assertEqual(obj.monitor_status_var.get(), "Stopped")


class SensorsWithoutPreview(unittest.TestCase):
    """v0.2.6: with Live Preview off only CPU load and RAM had values; the rest showed a dash."""

    def setUp(self):
        from scripts import sensor_poll
        self.sp = sensor_poll

    # No real threads here: a thread alive during the suite let Python's garbage collector free a Tk object of another
    # test on the wrong thread (Tcl_AsyncDelete crash). The loop runs in the test's own thread instead.
    @staticmethod
    def turns(n):
        """A `wanted` that is True for n-1 checks, then False: `_loop` then ends by itself."""
        left = [n]

        def wanted():
            left[0] -= 1
            return left[0] > 0
        return wanted

    def test_the_tooltip_gives_the_reason_only_for_a_dash(self):
        """v0.2.6.1: hovering a dash on the Dashboard says why; a real value gets no tooltip."""
        class Label:
            def __init__(self, text):
                self.text = text

            def cget(self, _name):
                return self.text
        owner = mock.Mock(preview_running=False)
        owner.sensor_reasons.return_value = {"gpu.": "No NVIDIA GPU", "cpu.temp": "Helper is not answering"}
        miss = lambda text, key: app.TurmoApp._missing_reason(owner, Label(text), key)  # noqa: E731
        self.assertEqual(miss(app.NO_VALUE, "gpu.temp"), "No NVIDIA GPU")  # the group entry
        self.assertEqual(miss(app.NO_VALUE, "cpu.temp"), "Helper is not answering")  # the exact entry
        self.assertEqual(miss(app.NO_VALUE, "net.mbs"), "")  # no reason known: no tooltip
        self.assertEqual(miss("42%", "gpu.load"), "")  # has a value
        owner.preview_running = True  # the preview worker gives no reason: a kept one would be stale
        self.assertEqual(miss(app.NO_VALUE, "gpu.temp"), "")

    def test_the_thread_starts_only_when_it_is_wanted(self):
        wanted = [False]
        poller = self.sp.SensorPoller(lambda: ({}, {}), lambda: wanted[0])
        with mock.patch.object(self.sp.threading, "Thread") as thread:
            poller.ensure_running()
            thread.assert_not_called()
            wanted[0] = True
            poller.ensure_running()
            thread.assert_called_once()
            thread.return_value.start.assert_called_once()

    def test_the_loop_reads_while_wanted_and_ends_when_it_is_not(self):
        calls = []
        poller = self.sp.SensorPoller(lambda: (calls.append(1) or {"a": 1}, {"gpu.": "no GPU"}), self.turns(3),
                                      interval=1.0)
        with mock.patch.object(self.sp.time, "sleep"):
            poller._loop()
        self.assertEqual(len(calls), 2)  # the third check said no
        self.assertEqual(poller.latest(), {"a": 1})
        self.assertEqual(poller.reasons(), {"gpu.": "no GPU"})

    def test_old_readings_are_not_shown(self):
        poller = self.sp.SensorPoller(lambda: ({"a": 1}, {}), lambda: True)
        poller._readings, poller._stamp = {"a": 1}, 0.0  # read long ago
        self.assertEqual(poller.latest(), {})

    def test_a_failing_read_keeps_polling_and_says_why(self):
        calls = []

        def read():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return {"a": 2}, {}
        poller = self.sp.SensorPoller(read, self.turns(3), interval=1.0)
        with mock.patch.object(self.sp.time, "sleep"):
            poller._loop()
        self.assertEqual(len(calls), 2)
        self.assertEqual(poller.latest(), {"a": 2})  # the second read worked

    def test_reason_for_a_key_falls_back_to_its_group_then_the_generic_one(self):
        reasons = {"cpu.temp": "no helper", "gpu.": "no GPU", "": "failed"}
        self.assertEqual(self.sp.reason_for(reasons, "cpu.temp"), "no helper")
        self.assertEqual(self.sp.reason_for(reasons, "gpu.vram_used"), "no GPU")
        self.assertEqual(self.sp.reason_for(reasons, "disk.load"), "failed")
        self.assertEqual(self.sp.reason_for({}, "disk.load"), "")

    def test_a_machine_without_nvml_gives_no_gpu_readings_and_a_reason(self):
        with mock.patch.dict("sys.modules", {"pynvml": None}):  # import raises ImportError
            readings, reasons = self.sp.read_nvml(0, {})
        self.assertEqual(readings, {})
        self.assertIn("NVIDIA", reasons["gpu."])

    def test_the_reader_merges_psutil_gpu_and_cpu_temperature_and_names_a_missing_helper(self):
        from libre_panel.sensors.base import Reading
        provider = mock.Mock()
        provider.read.return_value = {"cpu.load": Reading("cpu.load", 5.0, "%", "CPU load"),
                                      "net.down": Reading("net.down", 100.0, "B/s", "down")}
        gpu = {"gpu.temp": Reading("gpu.temp", 60.0, "C", "GPU")}
        settings = mock.Mock(gpu_index=0)
        with mock.patch("libre_panel.sensors.psutil_provider.PsutilProvider", return_value=provider), \
                mock.patch.object(self.sp, "read_nvml", return_value=(gpu, {})):
            readings, reasons = self.sp.make_reader(settings, lambda: {})()
        self.assertEqual(sorted(readings), ["cpu.load", "gpu.temp", "net.down"])
        self.assertIn("helper", reasons["cpu.temp"])
        with mock.patch("libre_panel.sensors.psutil_provider.PsutilProvider", return_value=provider), \
                mock.patch.object(self.sp, "read_nvml", return_value=(gpu, {})):
            temp = {"cpu.temp": Reading("cpu.temp", 50.0, "C", "t")}
            readings, reasons = self.sp.make_reader(settings, lambda: temp)()
        self.assertIn("cpu.temp", readings)
        self.assertNotIn("cpu.temp", reasons)

    def test_the_dashboard_takes_the_polled_values_and_leaves_cpu_percent_alone(self):
        obj = make_app()
        obj.preview_running = False
        obj._window_hidden = lambda: False
        poller = mock.Mock()
        poller.running.return_value = True
        poller.latest.return_value = {"gpu.temp": 61.0, "cpu.load": 7.0}
        obj._poller = poller
        with mock.patch("psutil.cpu_percent") as cpu:
            self.assertEqual(obj._psutil_readings(), {"gpu.temp": 61.0, "cpu.load": 7.0})
            cpu.assert_not_called()  # a second cpu_percent reader would spoil the poller's figure
        poller.ensure_running.assert_called_once()
        self.assertTrue(obj._poll_on)
        obj.preview_running = True  # the preview reads the sensors itself
        obj._psutil_readings()
        self.assertFalse(obj._poll_on)

    def test_the_polled_values_are_plain_numbers_the_quick_panel_can_compare(self):
        """Review finding: Reading objects reached read_meters, and draw_meter raised on min(Reading, 100)."""
        from libre_panel.sensors.base import Reading
        from scripts import quick_panel
        poller = self.sp.SensorPoller(lambda: ({"cpu.load": Reading("cpu.load", 7.0, "%", "x"), "mem.load": 40.0}, {}),
                                      SensorsWithoutPreview.turns(2), interval=1.0)
        with mock.patch.object(self.sp.time, "sleep"):
            poller._loop()
        values = poller.latest()
        self.assertEqual(values, {"cpu.load": 7.0, "mem.load": 40.0})
        obj = make_app()
        obj.preview_running = False
        obj._poller = mock.Mock(running=mock.Mock(return_value=True), latest=mock.Mock(return_value=values))
        obj._window_hidden = lambda: False
        obj._preview_lock = mock.MagicMock()
        obj._preview_readings = {}
        meters = quick_panel.read_meters(obj)
        self.assertEqual(meters["cpu"][0], 7.0)
        self.assertEqual(meters["ram"][0], 40.0)

    def test_the_poller_stops_when_the_preview_starts_even_if_nothing_asks_for_readings(self):
        obj = make_app()
        obj._window_hidden = lambda: False
        obj.preview_running = False
        obj._update_poll_on()
        self.assertTrue(obj._poll_on)
        obj.preview_running = True  # the dashboard tick calls this before anything else
        obj._update_poll_on()
        self.assertFalse(obj._poll_on)
        obj.preview_running, obj._window_hidden = False, lambda: True
        obj._update_poll_on()
        self.assertFalse(obj._poll_on)

    def test_the_quick_panel_shows_gpu_and_cpu_temperature_from_the_poller_when_the_preview_is_off(self):
        # v0.3.4: GPU showed a dash in the tray panel and the Minimalist window (only the Live Preview was read)
        from scripts import quick_panel
        obj = make_app()
        obj.preview_running, obj._window_hidden = False, (lambda: False)
        values = {"cpu.load": 7.0, "mem.load": 40.0, "gpu.load": 12.0, "gpu.temp": 55.0, "cpu.temp": 61.0}
        obj._poller = mock.Mock(running=mock.Mock(return_value=True), latest=mock.Mock(return_value=values))
        obj._preview_lock, obj._preview_readings = mock.MagicMock(), {}
        meters = quick_panel.read_meters(obj)
        self.assertEqual(meters["gpu"], (12.0, 55.0))
        self.assertEqual(meters["cpu"], (7.0, 61.0))

    def test_the_poller_runs_for_the_tray_panel_while_the_window_is_hidden(self):
        # v0.3.4: the tray panel showed no GPU: with the window in the tray nothing asked the poller to run
        obj = make_app()
        obj._window_hidden, obj.preview_running = (lambda: True), False
        obj._update_poll_on()
        self.assertFalse(obj._poll_on)
        obj._meters_wanted_until = time.time() + 3  # set by quick_panel.read_meters
        obj._update_poll_on()
        self.assertTrue(obj._poll_on)
        obj._meters_wanted_until = time.time() - 1  # the panel closed: the poller stops again
        obj._update_poll_on()
        self.assertFalse(obj._poll_on)

    def test_without_a_poller_cpu_load_and_ram_still_show(self):
        obj = make_app()
        obj.preview_running = False
        obj._window_hidden = lambda: False
        obj._poller = None
        with mock.patch("psutil.cpu_percent", return_value=12.0):
            values = obj._psutil_readings()
        self.assertEqual(values["cpu.load"], 12.0)
        self.assertIn("mem.load", values)


class AppCpuTile(unittest.TestCase):
    """The Diagnostics "App CPU" tile read 0.0 % for good: it made a new psutil.Process on every refresh."""

    def test_one_process_object_is_kept_between_readings(self):
        obj = make_app()
        import psutil
        with mock.patch.object(psutil, "Process") as proc:
            proc.return_value.cpu_percent.side_effect = [0.0, 7.5]
            first, second = obj._app_cpu(), obj._app_cpu()
        self.assertEqual(proc.call_count, 1)
        self.assertEqual((first, second), (0.0, 7.5))


class PanelColourCorrection(unittest.TestCase):
    """The LCD's blue is too bright in the shadows and mid-tones; the three channels get one grey curve (v0.2.9)."""

    def setUp(self):
        import settings
        self.settings = settings

    def test_tables_keep_black_and_white_and_never_fall(self):
        for table in self.settings.panel_luts():
            self.assertEqual((len(table), table[0], table[255]), (256, 0, 255))
            self.assertTrue(all(b >= a for a, b in zip(table, table[1:])))

    def test_blue_is_pulled_down_and_red_pushed_up_in_the_mid_tones(self):
        r, g, b = self.settings.panel_luts()
        self.assertGreater(r[109], g[109])
        self.assertGreater(g[109], b[109])

    def test_grey_in_stays_grey_in_the_ends_and_off_returns_the_same_picture(self):
        from PIL import Image
        img = Image.new("RGB", (2, 1), (255, 255, 255))
        img.putpixel((1, 0), (0, 0, 0))
        out = self.settings.correct_panel(img)
        self.assertEqual((out.getpixel((0, 0)), out.getpixel((1, 0))), ((255, 255, 255), (0, 0, 0)))
        self.assertIs(self.settings.correct_panel(img, False), img)

    def test_a_violet_gets_less_blue_and_more_red(self):
        from PIL import Image
        out = self.settings.correct_panel(Image.new("RGB", (1, 1), (75, 12, 74))).getpixel((0, 0))
        self.assertGreater(out[0], 75)
        self.assertLess(out[2], 74)

    def test_mid_grey_comes_out_with_the_same_share_in_each_channel(self):
        shares = [t[128] / 255 for t in self.settings.panel_luts()]
        self.assertLess(max(shares) - min(shares), 0.25)  # the raw panel's spread there is about 0.3 of white

    def test_a_hand_edited_false_text_turns_it_off(self):
        from PIL import Image
        img = Image.new("RGB", (1, 1), (75, 12, 74))
        for off in ("false", "0", None, False):
            self.assertIs(self.settings.correct_panel(img, off), img)

    def test_the_monitor_calls_it_live_and_with_once(self):
        text = (Path(__file__).parent / "turmo_runtime.py").read_text(encoding="utf-8")
        self.assertIn("correct_panel(frame, live.color_correction, live.color_gain)", text)
        self.assertIn("correct_panel(img, settings.color_correction, settings.color_gain)", text)

    def test_gain_values_clip_and_ignore_odd_input(self):
        gv = self.settings.gain_values
        self.assertEqual(gv({}), (100, 100, 100))
        self.assertEqual(gv({"r": 150, "g": 10, "b": "90"}), (130, 70, 90))
        self.assertEqual(gv({"r": "x", "g": None, "b": 95.4}), (100, 100, 95))
        self.assertEqual(gv("not a dict"), (100, 100, 100))
        # json.loads('{"r": 1e400}') is inf: that once crashed the window at start-up
        self.assertEqual(gv({"r": float("inf"), "g": "inf", "b": float("nan")}), (100, 100, 100))
        self.assertEqual(gv({"r": True, "g": [1], "b": "1e400"}), (100, 100, 100))
        self.assertEqual(self.settings.Settings().color_gain, {"r": 100, "g": 100, "b": 100})

    def test_white_balance_scales_each_colour_and_off_ignores_it(self):
        from PIL import Image
        white = Image.new("RGB", (1, 1), (255, 255, 255))
        out = self.settings.correct_panel(white, True, {"r": 100, "g": 100, "b": 80}).getpixel((0, 0))
        self.assertEqual(out, (255, 255, 204))
        same = self.settings.correct_panel(white, True, {"r": 100, "g": 100, "b": 100}).getpixel((0, 0))
        self.assertEqual(same, self.settings.correct_panel(white).getpixel((0, 0)))
        self.assertIs(self.settings.correct_panel(white, False, {"b": 70}), white)

    def test_the_settings_handlers_save_a_clean_gain_and_reset_it(self):
        import types
        saved = []
        stub = types.SimpleNamespace(settings=self.settings.Settings(), color_gain_vars={k: Var(80) for k in "rgb"})
        stub.settings.color_gain = {"r": "bad"}
        stub.settings.save = lambda: saved.append(dict(stub.settings.color_gain))
        app.TurmoApp.on_color_gain_change(stub, "b", 85.0)
        self.assertEqual(saved[-1], {"r": 100, "g": 100, "b": 85})
        app.TurmoApp.on_color_gain_reset(stub)
        self.assertEqual(saved[-1], {"r": 100, "g": 100, "b": 100})
        self.assertEqual([v.get() for v in stub.color_gain_vars.values()], [100, 100, 100])

    def test_setting_defaults_on_and_survives_a_saved_file(self):
        self.assertTrue(self.settings.Settings().color_correction)
        self.assertFalse(self.settings.Settings(**{"color_correction": False}).color_correction)


class IdleWork(unittest.TestCase):
    """v0.2.4: idle CPU was 3.5 % of a core with the window open and 4.9 % minimised, mostly a scan of every process
    twice a second (the Monitor state every 2 s, the Diagnostics page every second even when it was not shown)."""

    def make(self, state="normal", page="Dashboard"):
        obj = make_app()
        obj.root.window_state = state
        obj.nb = mock.Mock()
        obj.nb.index.return_value = app.SIDEBAR_ITEMS.index(page)
        obj.diag_tiles = {}
        obj._device_chip = object()
        obj._startup_log = None
        for name in ("_refresh_device_chip", "_refresh_preview_info", "_refresh_diagnostics"):
            setattr(obj, name, mock.Mock(name=name))
        return obj

    def test_monitor_state_scan_is_slower_while_the_window_is_hidden(self):
        for state, wait in (("normal", 2000), ("zoomed", 2000), ("iconic", 5000), ("withdrawn", 5000)):
            obj = make_app()
            obj.root.window_state = state
            with mock.patch.object(app, "_process_rows", return_value=[]):
                obj._refresh_monitor_state()
            self.assertEqual(obj.root.calls[-1][0], wait, state)

    def test_scan_stays_at_2_s_while_the_tray_panel_is_open(self):
        obj = make_app()
        obj.root.window_state = "withdrawn"
        obj.quick_panel = mock.Mock(visible=True)
        with mock.patch.object(app, "_process_rows", return_value=[]):
            obj._refresh_monitor_state()
        self.assertEqual(obj.root.calls[-1][0], 2000)

    def test_monitor_state_is_scanned_at_once_when_the_window_comes_back(self):
        obj = make_app()
        obj._scan_monitor_state = mock.Mock()
        obj.root.after_idle = lambda cb: cb()
        obj._on_window_shown(mock.Mock(widget=obj.root))
        obj._scan_monitor_state.assert_called_once()
        obj._scan_monitor_state.reset_mock()
        obj._on_window_shown(mock.Mock(widget=object()))  # a child widget being mapped is not the window
        obj._scan_monitor_state.assert_not_called()

    def test_quick_theme_sets_the_theme_and_leaves_the_running_monitor_alone(self):
        for status, restarts in (("Running", 0), ("Stopped", 0)):
            obj = make_app()
            obj.monitor_status_var.set(status)
            obj.theme_var = Var()
            obj.on_theme_change = mock.Mock()
            obj._refresh_dashboard_status = mock.Mock()
            obj.restart_monitor = mock.Mock()
            obj.apply_quick_theme("matrix-terminal")
            self.assertEqual(obj.theme_var.get(), "matrix-terminal")
            self.assertEqual(obj.restart_monitor.call_count, restarts, status)

    def test_stop_monitor_survives_a_refresh_that_clears_the_process_while_it_waits(self):
        """root.update() inside stop_monitor can run the Monitor-state refresh, which sets monitor_process to None:
        stop_monitor then crashed on `None.poll` (seen once in test_gui_callbacks, v0.2.4)."""
        obj = make_app()

        class Slow(FakeProcess):
            calls = 0

            def poll(self):
                Slow.calls += 1
                if Slow.calls == 1:
                    return None  # still running at the first look
                obj.monitor_process = None  # the refresh that ran during root.update()
                return 0

        obj.monitor_process = Slow(7001)
        with mock.patch.object(app.time, "sleep"):
            obj.stop_monitor(reason="button")
        self.assertIsNone(obj.monitor_process)

    def test_nothing_is_refreshed_while_the_window_is_minimised_or_in_the_tray(self):
        for state in ("iconic", "withdrawn"):
            obj = self.make(state)
            obj._refresh_dashboard()
            obj._refresh_device_chip.assert_not_called()
            obj._refresh_preview_info.assert_not_called()
            obj._refresh_diagnostics.assert_not_called()
            self.assertEqual(obj.root.calls[-1][0], 1000)  # the loop keeps going

    def test_diagnostics_is_refreshed_only_on_its_own_page(self):
        obj = self.make(page="Dashboard")
        obj._refresh_dashboard()
        obj._refresh_diagnostics.assert_not_called()
        obj._refresh_device_chip.assert_called_once()  # the rest of the loop still runs
        obj = self.make(page="Diagnostics")
        obj._refresh_dashboard()
        obj._refresh_diagnostics.assert_called_once()

    def test_diagnostics_is_filled_in_when_its_page_is_opened(self):
        obj = self.make(page="Diagnostics")
        obj._sidebar_items = []
        obj.nb.index.return_value = app.SIDEBAR_ITEMS.index("Diagnostics")
        obj._sync_sidebar()
        obj._refresh_diagnostics.assert_called_once()

    def test_sidebar_entry_does_not_redraw_when_nothing_changed(self):
        import tkinter as tk
        root = tk.Tk()
        self.addCleanup(root.destroy)
        item = app.NavItem(root, "x", "Name", lambda: None, "#000000", ("Segoe UI", 12), ("Segoe UI", 10))
        item.set_active(True)
        with mock.patch.object(item, "_redraw") as redraw:
            item.set_active(True)
            redraw.assert_not_called()
            item.set_active(False)
            redraw.assert_called_once()


class StartRefusesOnOutsideMonitor(unittest.TestCase):
    def test_start_is_refused_and_no_process_is_launched(self):
        obj = make_app()
        with mock.patch.object(app, "_process_rows", return_value=[(4242, "TURMO-Monitor.exe", "", 1)]), \
                mock.patch.object(app.subprocess, "Popen") as popen:
            obj.show_warning = box = mock.Mock()
            obj.start_monitor(reason="button")
        box.assert_called_once()
        popen.assert_not_called()
        self.assertIsNone(obj.monitor_process)


class LiveMonitorGuards(unittest.TestCase):
    """A Monitor whose stop timed out is still alive and still holds COM4: Start must refuse,
    and the lock file that keeps a second Monitor out must stay."""

    def _app_stub(self):
        obj = make_app()
        obj.theme_var = Var("clean-white")
        obj.landscape_var = Var(False)
        obj.gpu_index_var = Var(0)
        obj.port_override_var = Var("COM4")
        return obj

    def test_start_refused_while_an_ignored_monitor_is_still_alive(self):
        obj = self._app_stub()
        obj._ignored_pids = {4242}  # we asked it to stop; it has not exited yet
        rows = [(4242, "TURMO-Monitor.exe", "", 1)]
        with mock.patch.object(app, "_process_rows", return_value=rows), \
                mock.patch.object(app.subprocess, "Popen") as popen, \
                mock.patch("serial.Serial"):
            obj.show_warning = box = mock.Mock()
            obj.start_monitor(reason="button")
        popen.assert_not_called()
        box.assert_called_once()

    def test_stop_keeps_the_lock_while_a_monitor_is_still_alive(self):
        obj = make_app()
        lock = Path(os.environ["APPDATA"]) / "TURMO" / "monitor.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("4242")
        rows = [(4242, "TURMO-Monitor.exe", "", 1)]  # still alive after the forced kill
        with mock.patch.object(app, "_process_rows", return_value=rows), \
                mock.patch("psutil.pid_exists", return_value=True), \
                mock.patch.object(app.subprocess, "run"):
            obj.stop_monitor(reason="button")
        self.assertTrue(lock.exists(), "lock was deleted while a Monitor still runs")
        lock.unlink()

    def test_stop_removes_the_lock_once_no_monitor_is_left(self):
        obj = make_app()
        lock = Path(os.environ["APPDATA"]) / "TURMO" / "monitor.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("4242")
        with mock.patch.object(app, "_process_rows", return_value=[]):
            obj.stop_monitor(reason="button")
        self.assertFalse(lock.exists())


class StartupCleanup(unittest.TestCase):
    """Opening the GUI must never stop a Monitor. It may only clear a lock whose PID is gone."""

    def _lock(self, pid):
        lock = Path(os.environ["APPDATA"]) / "TURMO" / "monitor.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(str(pid))
        return lock

    def test_live_monitor_is_not_killed_at_startup(self):
        obj = make_app()
        obj._startup_log = None
        lock = self._lock(4242)
        with mock.patch("psutil.pid_exists", return_value=True),                 mock.patch.object(app.subprocess, "run") as run,                 mock.patch.object(app, "log_startup"):
            app.TurmoApp._cleanup_stale_workers(obj)
        run.assert_not_called()
        self.assertTrue(lock.exists(), "lock removed while its Monitor still runs")
        lock.unlink()

    def test_dead_lock_is_removed_at_startup(self):
        obj = make_app()
        obj._startup_log = None
        lock = self._lock(4242)
        with mock.patch("psutil.pid_exists", return_value=False),                 mock.patch.object(app.subprocess, "run") as run,                 mock.patch.object(app, "log_startup"):
            app.TurmoApp._cleanup_stale_workers(obj)
        run.assert_not_called()
        self.assertFalse(lock.exists())


class TrayQuit(unittest.TestCase):
    def test_tray_quit_logs_gui_quit_and_stops_only_its_own_monitor(self):
        obj = make_app()
        obj.stop_monitor = mock.Mock()
        icon = mock.Mock()
        app._log_event.reset_mock()
        app.TurmoApp._quit_from_tray(obj, icon)
        app._log_event.assert_called_with("GUI_QUIT", "tray quit")
        obj.stop_monitor.assert_called_with(reason="tray quit")
        icon.stop.assert_called_once()


class NeverExitingProcess:
    """A Monitor Popen whose exit never comes: poll() is None, wait() times out."""

    def __init__(self, pid):
        self.pid = pid

    def poll(self):
        return None

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired("monitor", timeout)


class ProcessKilledByTaskkill:
    """Alive until a taskkill call succeeds (run_state["killed"] is set by the mocked run)."""

    def __init__(self, pid, run_state):
        self.pid = pid
        self.run_state = run_state

    def poll(self):
        return 0 if self.run_state["killed"] else None

    def wait(self, timeout=None):
        if self.run_state["killed"]:
            return 0
        raise subprocess.TimeoutExpired("monitor", timeout)


def _log_lines(obj):
    return "".join(obj.log_text.text).splitlines()


def _has_taskkill_failure(lines):
    return any("taskkill" in line and "failed" in line for line in lines)


class OwnMonitorStopFailure(unittest.TestCase):
    def test_failed_taskkill_is_logged_and_pid_stays_visible(self):
        obj = make_app()
        obj.monitor_process = NeverExitingProcess(5150)
        failed = subprocess.CompletedProcess(["taskkill"], 1, b"", b"Access is denied")
        with mock.patch.object(app, "_process_rows", return_value=[]), \
                mock.patch.object(app.subprocess, "run", return_value=failed):
            obj.stop_monitor(reason="button")
        with self.subTest("failure is logged"):
            self.assertTrue(_has_taskkill_failure(_log_lines(obj)),
                            f"no 'taskkill ... failed' log line: {_log_lines(obj)}")
        with self.subTest("live pid is not ignored"):
            self.assertNotIn(5150, obj._ignored_pids,
                             "a Monitor that is still alive was hidden from the status")

    def test_pid_is_ignored_once_taskkill_succeeded_and_it_exited(self):
        obj = make_app()
        run_state = {"killed": False}
        obj.monitor_process = ProcessKilledByTaskkill(5150, run_state)
        ok = subprocess.CompletedProcess(["taskkill"], 0, b"", b"")

        def fake_run(cmd, **_kwargs):
            run_state["killed"] = True
            return ok

        with mock.patch.object(app, "_process_rows", return_value=[]), \
                mock.patch.object(app.subprocess, "run", side_effect=fake_run):
            obj.stop_monitor(reason="button")
        self.assertIn(5150, obj._ignored_pids)


class OutsideMonitorStopFailure(unittest.TestCase):
    def _check_stop(self, run_kwargs):
        obj = make_app()
        obj.monitor_status_var.set("Running")
        request = Path(os.environ["APPDATA"]) / "TURMO" / "stop_monitor.request"
        request.parent.mkdir(parents=True, exist_ok=True)
        request.write_text("0")
        self.addCleanup(lambda: request.unlink(missing_ok=True))
        try:
            with mock.patch.object(app, "_process_rows", return_value=[]), \
                    mock.patch.object(obj, "_outside_monitor_pids", return_value=[4242]), \
                    mock.patch("psutil.pid_exists", return_value=True), \
                    mock.patch.object(app.subprocess, "run", **run_kwargs):
                obj.stop_monitor(reason="button")
        except Exception as e:
            self.fail(f"stop_monitor raised {e!r} for a failed taskkill")
        lines = _log_lines(obj)
        with self.subTest("failure is logged"):
            self.assertTrue(_has_taskkill_failure(lines), f"no 'taskkill ... failed' log line: {lines}")
        with self.subTest("log still ends with Monitor stopped"):
            self.assertTrue(lines and lines[-1].endswith("Monitor stopped"), f"last line: {lines[-1:]}")
        with self.subTest("status is Stopped"):
            self.assertEqual(obj.monitor_status_var.get(), "Stopped")
        with self.subTest("stop request file removed"):
            self.assertFalse(request.exists())

    def test_taskkill_timeout_does_not_raise_and_is_logged(self):
        self._check_stop({"side_effect": subprocess.TimeoutExpired("taskkill", 10)})

    def test_taskkill_nonzero_return_is_logged(self):
        self._check_stop({"return_value": subprocess.CompletedProcess(
            ["taskkill"], 1, b"", b"Access is denied")})


class StopMonitorReviewFindings(unittest.TestCase):
    """v0.2.3: the three findings left open by the 2026-11-17 review of stop_monitor."""

    def test_an_error_while_waiting_does_not_leave_a_live_monitor_hidden(self):
        obj = make_app()
        with mock.patch.object(app, "_process_rows", return_value=[]),                 mock.patch.object(obj, "_outside_monitor_pids", return_value=[4242]),                 mock.patch("psutil.pid_exists", side_effect=RuntimeError("process table unreadable")):
            with self.assertRaises(RuntimeError):
                obj.stop_monitor(reason="button")
        self.assertNotIn(4242, obj._ignored_pids, "a Monitor that may still be alive stayed hidden from the status")

    def test_own_monitor_that_survives_taskkill_is_not_called_outside(self):
        obj = make_app()
        obj.monitor_process = NeverExitingProcess(5150)
        failed = subprocess.CompletedProcess(["taskkill"], 1, b"", b"Access is denied")
        rows = [(5150, "TURMO-Monitor.exe", "", 1)]
        with mock.patch.object(app, "_process_rows", return_value=rows),                 mock.patch("psutil.pid_exists", return_value=True),                 mock.patch.object(app.subprocess, "run", return_value=failed):
            obj.stop_monitor(reason="button")
        lines = _log_lines(obj)
        self.assertFalse(any("started outside this window" in l and "5150" in l for l in lines), lines)
        self.assertTrue(any("started by this window" in l and "5150" in l for l in lines), lines)

    def test_taskkill_on_a_process_that_just_exited_is_not_a_failure(self):
        obj = make_app()
        gone = subprocess.CompletedProcess(["taskkill"], 128, b"", b"ERROR: The process not found.")
        with mock.patch("psutil.pid_exists", return_value=False),                 mock.patch.object(app, "_log_event") as log_event,                 mock.patch.object(app.subprocess, "run", return_value=gone):
            obj._force_kill_pid(4242)
        self.assertFalse(_has_taskkill_failure(_log_lines(obj)), _log_lines(obj))
        self.assertNotIn("MONITOR_KILL_FAILED", [c.args[0] for c in log_event.call_args_list])


class TrayQuitDeferred(unittest.TestCase):
    def test_quit_menu_item_hands_off_to_the_tk_thread(self):
        obj = make_app()
        obj._quit_from_tray = mock.Mock(name="_quit_from_tray")
        obj.root.after = mock.Mock(name="after")
        actions = {}
        fake_pystray = mock.Mock(name="pystray")

        def menu_item(label, action=None, **_kwargs):
            actions[label] = action
            return mock.Mock(name=f"MenuItem({label})")

        fake_pystray.MenuItem.side_effect = menu_item
        with mock.patch.object(app, "pystray", fake_pystray), \
                mock.patch.object(app, "Image"), \
                mock.patch.object(app, "ImageDraw"), \
                mock.patch.object(app.threading, "Thread", FakeThread):
            obj.start_tray()
        icon = obj.tray_icon
        actions["Quit"](icon, None)  # what pystray calls on its own thread
        obj._quit_from_tray.assert_not_called()  # must not run on the pystray thread
        obj.root.after.assert_called_once()
        ms, callback, *extra = obj.root.after.call_args[0]
        self.assertEqual(ms, 0)
        callback(*extra)
        obj._quit_from_tray.assert_called_once_with(icon)


class GalleryRender(unittest.TestCase):
    def test_each_render_keeps_only_the_images_of_its_cards(self):
        obj = make_app()
        old = [object() for _ in range(5)]
        obj._gallery_images = list(old)
        obj._gallery_grid = mock.Mock(name="grid")
        obj._gallery_grid.winfo_children.return_value = []
        obj._gallery_canvas = mock.Mock(name="canvas")
        obj._gallery_canvas.yview.return_value = (0.4, 0.9)
        obj._gallery_category = "All"
        obj._gallery_query = Var("")
        obj.get_available_themes = lambda: ["a", "b"]
        obj.settings = mock.Mock(theme_order=["b"])
        made = []

        def card(_parent, _slug):
            sentinel = object()
            obj._gallery_images.append(sentinel)
            made.append(sentinel)
            return mock.Mock(name="card")

        order_seen = []

        def card(_parent, slug, _inner=card):
            order_seen.append(slug)
            return _inner(_parent, slug)

        obj._gallery_card = card
        obj._gallery_render()
        self.assertEqual(order_seen, ["b", "a"], "the saved order is used")
        self.assertEqual(len(obj._gallery_images), 2, "images from earlier renders are kept")
        self.assertEqual(obj._gallery_images, made)

        made.clear()
        obj._gallery_render()
        self.assertEqual(len(obj._gallery_images), 2)
        self.assertEqual(obj._gallery_images, made)
        obj._gallery_canvas.yview_moveto.assert_called_with(0.4)  # the scroll position survives a re-render


class GalleryApplyRestart(unittest.TestCase):
    def _app(self, status):
        obj = make_app()
        obj.theme_var, obj.monitor_status_var = Var(""), Var(status)
        obj.on_theme_change = lambda: None
        obj._refresh_dashboard_status = lambda: None
        obj._gallery_render = lambda: None
        obj.restart_monitor = mock.Mock()
        return obj

    def test_apply_does_not_restart_a_running_monitor(self):
        """v0.2.4.1: the running Monitor sees the new theme in settings.json and draws it without a restart."""
        for status in ("Running", "Stopped"):
            obj = self._app(status)
            obj.gallery_apply("neon")
            obj.restart_monitor.assert_not_called()
            self.assertEqual(obj.theme_var.get(), "neon")


class MonitorThemeHotReload(unittest.TestCase):
    """v0.2.4.1: the live loop of the Monitor draws a new theme without a restart (the restart took 5 to 10 s: the
    one-file exe needs about 7 s to start)."""

    def setUp(self):
        import turmo_runtime as rt
        self.rt = rt
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        patcher = mock.patch.object(rt, "_theme_folder", lambda name: self.tmp / name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def theme(self, name, text="{}"):
        (self.tmp / name).mkdir(exist_ok=True)
        (self.tmp / name / "theme.json").write_text(text)

    def decide(self, **kw):
        args = dict(target_theme="a", seen_setting="a", setting_theme="a", landscape=True, current=("a", None), bad=None)
        args.update(kw)
        return self.rt._theme_to_draw(**args)

    def test_nothing_changes_while_the_name_and_the_file_stay(self):
        self.theme("a")
        current = ("a", self.rt._theme_stamp("a"))
        *_, load = self.decide(current=current)
        self.assertFalse(load)

    def test_a_new_theme_name_in_settings_is_drawn(self):
        self.theme("a"); self.theme("b")
        target, seen, want, load = self.decide(setting_theme="b", current=("a", self.rt._theme_stamp("a")))
        self.assertEqual((target, seen, want[0], load), ("b", "b", "b", True))

    def test_a_theme_setting_that_is_not_a_name_changes_nothing(self):
        self.theme("a")
        current = ("a", self.rt._theme_stamp("a"))
        for bad in (None, 5, ["x"], ""):
            *_, load = self.decide(setting_theme=bad, current=current)
            self.assertFalse(load, bad)

    def test_an_unreadable_settings_file_gives_no_theme(self):
        import settings as st
        path = self.tmp / "settings.json"
        with mock.patch.object(st.Settings, "path", classmethod(lambda cls: path)):
            self.assertIsNone(self.rt._setting_theme())  # missing
            path.write_text('{"theme": "ne')  # half written
            self.assertIsNone(self.rt._setting_theme())
            path.write_text('{"theme": 5}')
            self.assertIsNone(self.rt._setting_theme())
            path.write_text('{"theme": "neon"}')
            self.assertEqual(self.rt._setting_theme(), "neon")

    def test_a_cli_theme_survives_when_settings_hold_the_minimal_alias(self):
        self.theme("cli")
        # the loop starts with seen_setting already mapped, as turmo_runtime does
        *_, load = self.decide(target_theme="cli", seen_setting="minimal-dark", setting_theme="minimal",
                               current=("cli", self.rt._theme_stamp("cli")))
        self.assertFalse(load)

    def test_the_minimal_alias_means_minimal_dark(self):
        self.theme("minimal-dark")
        target, _s, want, load = self.decide(setting_theme="minimal", current=("a", None))
        self.assertEqual((target, want[0], load), ("minimal-dark", "minimal-dark", True))

    def test_a_custom_theme_saved_again_is_drawn_again(self):
        self.theme("mine", '{"v": 1}')
        current = ("mine", self.rt._theme_stamp("mine"))
        (self.tmp / "mine" / "theme.json").write_text('{"v": 22}')
        os.utime(self.tmp / "mine" / "theme.json", ns=(current[1] + 5_000_000_000, current[1] + 5_000_000_000))
        *_, load = self.decide(target_theme="mine", seen_setting="mine", setting_theme="mine", current=current)
        self.assertTrue(load)

    def test_portrait_draws_the_portrait_folder(self):
        self.theme("a"); self.theme("a-320x480")
        _t, _s, want, load = self.decide(landscape=False, current=("a", self.rt._theme_stamp("a")))
        self.assertEqual((want[0], load), ("a-320x480", True))

    def test_a_theme_that_failed_is_not_tried_every_frame_until_its_file_changes(self):
        self.theme("b", "broken")
        bad = ("b", self.rt._theme_stamp("b"))
        *_, load = self.decide(setting_theme="b", current=("a", None), bad=bad)
        self.assertFalse(load)
        (self.tmp / "b" / "theme.json").write_text("fixed")
        os.utime(self.tmp / "b" / "theme.json", ns=(bad[1] + 5_000_000_000, bad[1] + 5_000_000_000))
        *_, load = self.decide(setting_theme="b", current=("a", None), bad=bad)
        self.assertTrue(load)

    def test_a_theme_given_on_the_command_line_is_kept_until_settings_change(self):
        self.theme("cli"); self.theme("saved")
        current = ("cli", self.rt._theme_stamp("cli"))
        target, seen, want, load = self.decide(target_theme="cli", seen_setting="saved", setting_theme="saved", current=current)
        self.assertEqual((target, want[0], load), ("cli", "cli", False))  # the setting did not change: no switch

    def test_a_missing_theme_folder_is_a_failed_candidate_not_a_crash(self):
        _t, _s, want, load = self.decide(setting_theme="gone", current=("a", None))
        self.assertEqual((want, load), (("gone", None), True))  # the loop then fails to load it and keeps the old one


class FontScaleSetting(unittest.TestCase):
    def test_saved_scale_is_rounded_to_two_decimals(self):
        obj = make_app()
        obj.settings = mock.Mock(font_scale=1.0)
        obj.on_font_scale_change(1.0139784946236559)
        self.assertEqual(obj.settings.font_scale, 1.01)
        obj.settings.save.assert_called_once()


class GalleryDelete(unittest.TestCase):
    def _setup(self, applied="a"):
        root = Path(tempfile.mkdtemp(prefix="turmo-test-del-"))
        self.addCleanup(shutil.rmtree, root, True)
        for name in ("mine", "mine-320x480"):
            (custom(root) / name).mkdir(parents=True)  # the user's theme
        (root / "themes" / "cyberpunk-neon").mkdir(parents=True)  # an official one
        obj = make_app()
        obj.settings = mock.Mock(theme=applied)
        obj._gallery_render = lambda: None
        obj._refresh_dashboard_status = mock.Mock()
        return root, obj

    def _delete(self, root, obj, slug, answer):
        ask = mock.Mock(side_effect=lambda title, text, label, on_yes, **kw: on_yes() if answer else None)
        obj.confirm = ask  # the in-app dialog; the test answers it at once
        with patch_roots(root):
            obj.gallery_delete(slug)
        return ask, obj.toast

    def _left(self, root):
        return sorted(p.name for d in (root / "themes", custom(root)) if d.is_dir() for p in d.iterdir())

    def test_confirmed_delete_removes_the_theme_and_its_portrait_variant(self):
        root, obj = self._setup()
        ask, _ = self._delete(root, obj, "mine", True)
        ask.assert_called_once()
        self.assertEqual(self._left(root), ["cyberpunk-neon"])

    def test_declined_delete_keeps_everything(self):
        root, obj = self._setup()
        self._delete(root, obj, "mine", False)
        self.assertEqual(self._left(root), ["cyberpunk-neon", "mine", "mine-320x480"])

    def test_official_theme_is_refused_without_asking(self):
        root, obj = self._setup()
        ask, info = self._delete(root, obj, "cyberpunk-neon", True)
        ask.assert_not_called()
        info.assert_called_once()
        self.assertEqual(self._left(root), ["cyberpunk-neon", "mine", "mine-320x480"])

    def test_the_applied_custom_theme_can_be_deleted_and_the_default_is_applied(self):
        root, obj = self._setup(applied="mine")
        obj.theme_var, obj.on_theme_change = Var("mine"), mock.Mock()
        obj._refresh_dashboard_status = mock.Mock()
        ask, _ = self._delete(root, obj, "mine", True)
        self.assertIn("will be applied instead", ask.call_args.args[1])
        self.assertEqual(obj.theme_var.get(), app.DEFAULT_THEME)
        obj.on_theme_change.assert_called_once()
        self.assertEqual(self._left(root), ["cyberpunk-neon"])

    def test_declining_for_the_applied_theme_changes_nothing(self):
        root, obj = self._setup(applied="mine")
        obj.theme_var, obj.on_theme_change = Var("mine"), mock.Mock()
        self._delete(root, obj, "mine", False)
        self.assertEqual(obj.theme_var.get(), "mine")
        obj.on_theme_change.assert_not_called()
        self.assertEqual(self._left(root), ["cyberpunk-neon", "mine", "mine-320x480"])


class GalleryDuplicate(unittest.TestCase):
    def _themes(self):
        root = Path(tempfile.mkdtemp(prefix="turmo-test-gal-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "themes" / "a").mkdir(parents=True)
        (root / "themes" / "a" / "theme.json").write_text('{"name": "A"}', encoding="utf-8")
        return root

    def test_copy_gets_a_free_name_and_is_returned(self):
        root = self._themes()
        (root / "themes" / "a-copy-320x480").mkdir()  # a leftover variant also blocks the name
        obj = make_app()
        obj._gallery_render = lambda: None
        with patch_roots(root):
            self.assertEqual(obj.gallery_duplicate("a"), "a-copy2")
        self.assertTrue((custom(root) / "a-copy2" / "theme.json").is_file())
        self.assertFalse((root / "themes" / "a-copy2").exists(), "the copy is a user theme: it goes to the custom folder")

    def test_failed_copy_leaves_no_half_made_folder(self):
        root = self._themes()
        (root / "themes" / "a-320x480").mkdir()  # a portrait variant without theme.json
        obj = make_app()
        obj._gallery_render = lambda: None
        with patch_roots(root):
            self.assertIsNone(obj.gallery_duplicate("a"))
        obj.toast.assert_called_once()
        self.assertEqual(sorted(p.name for p in (root / "themes").iterdir()), ["a", "a-320x480"])
        self.assertEqual(list(custom(root).iterdir()) if custom(root).is_dir() else [], [])


RUNTIME_PROBE = (
    "import sys\n"
    "{blocker}"
    "sys.path[:0] = [sys.argv[1], sys.argv[2]]\n"
    "import turmo_app_enhanced as a\n"
    "print(a.RUNTIME_LOGGING_AVAILABLE)\n"
    "print(repr(getattr(a, 'RUNTIME_LOGGING_ERROR', '<missing>')))\n"
)

BLOCKER = (
    "import importlib.abc\n"
    "class _Block(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name.endswith('runtime_logging'):\n"
    "            raise ImportError('blocked by test')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Block())\n"
)


class RuntimeLoggingFallback(unittest.TestCase):
    def _probe(self, blocker):
        tmp = tempfile.mkdtemp(prefix="turmo-test-rl-")
        self.addCleanup(shutil.rmtree, tmp, True)
        env = dict(os.environ, LOCALAPPDATA=tmp, APPDATA=tmp, PYTHONDONTWRITEBYTECODE="1")
        script = RUNTIME_PROBE.format(blocker=blocker)
        proc = subprocess.run([sys.executable, "-c", script, HERE, ROOT], capture_output=True,
                              text=True, env=env, cwd=tmp, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.splitlines()

    def test_failed_runtime_logging_import_sets_the_error_text(self):
        out = self._probe(BLOCKER)
        self.assertEqual(out[0], "False", "the blocker did not disable runtime logging")
        self.assertNotIn(out[1], ("'<missing>'", "''"),
                         "RUNTIME_LOGGING_ERROR is missing or empty after a failed import")

    def test_normal_import_leaves_the_error_text_empty(self):
        out = self._probe("")
        self.assertEqual(out[0], "True")
        self.assertEqual(out[1], "''")


class Languages(unittest.TestCase):
    """v0.2.7: English is the source and the fallback; French and Portuguese come from i18n.TABLE."""

    def setUp(self):
        from scripts import i18n
        self.i18n = i18n
        i18n._reported.clear()

    def tearDown(self):
        self.i18n.set_language("en")
        self.i18n.set_missing_logger(None)

    def test_each_language_gives_its_own_text_and_english_is_the_source(self):
        for code, text in (("en", "Settings"), ("fr", "Réglages"), ("pt", "Configurações")):
            self.i18n.set_language(code)
            self.assertEqual(self.i18n.tr("Settings"), text)

    def test_an_unknown_language_shows_english(self):
        self.i18n.set_language("de")
        self.assertEqual(self.i18n.language(), "en")
        self.assertEqual(self.i18n.tr("Settings"), "Settings")

    def test_a_missing_text_falls_back_to_english_and_is_logged_once(self):
        seen = []
        self.i18n.set_missing_logger(lambda language, text: seen.append((language, text)))
        self.i18n.set_language("fr")
        self.assertEqual(self.i18n.tr("A text nobody translated"), "A text nobody translated")
        self.i18n.tr("A text nobody translated")
        self.assertEqual(seen, [("fr", "A text nobody translated")])
        self.i18n.set_language("pt")
        self.i18n.tr("A text nobody translated")
        self.assertEqual(len(seen), 2)  # once per language
        self.i18n.set_language("en")
        self.i18n.tr("Another untranslated text")
        self.assertEqual(len(seen), 2)  # English is the source: nothing is missing

    def test_choosing_a_language_saves_it_and_rebuilds_the_window(self):
        obj = make_app()
        obj.language_tiles = {k: mock.Mock() for k in ("en", "fr", "pt")}
        obj.settings = mock.Mock(language="en")
        obj.rebuild_ui = mock.Mock()
        obj.root = mock.Mock()  # after_idle: the rebuild waits until the click that chose the language is handled
        obj.confirm = mock.Mock()
        obj._show_language_tiles = lambda k: app.TurmoApp._show_language_tiles(obj, k)
        obj._apply_language = lambda k: app.TurmoApp._apply_language(obj, k)
        app.TurmoApp.on_language_change(obj, "fr")
        # a question first, written in French, and nothing changed yet
        args, kw = obj.confirm.call_args
        self.assertEqual(args[:3], ("Langue", "Passer la langue en français ?", "Oui"))
        self.assertEqual(kw["no_label"], "Non")
        obj.settings.save.assert_not_called()
        self.assertEqual(self.i18n.language(), "en")
        kw["on_no"]()  # No: the tiles go back to the current language
        obj.language_tiles["en"].set_selected.assert_called_with(True)
        self.assertEqual(self.i18n.language(), "en")
        args[3]()  # Yes: saved, switched, and the rebuild waits until the click is handled
        self.assertEqual(obj.settings.language, "fr")
        obj.settings.save.assert_called_once()
        obj.rebuild_ui.assert_not_called()
        obj.root.after_idle.assert_called_once_with(obj.rebuild_ui)
        obj.rebuild_ui()
        self.assertEqual(self.i18n.language(), "fr")
        obj.language_tiles["fr"].set_selected.assert_called_with(True)
        obj.confirm.reset_mock()
        app.TurmoApp.on_language_change(obj, "fr")  # the same language again: no question
        obj.confirm.assert_not_called()

    def test_every_language_has_a_question_in_its_own_language(self):
        for code in self.i18n.LANGUAGES:
            self.assertEqual(len(self.i18n.LANGUAGE_PROMPT[code]), 4)
            self.assertTrue(all(self.i18n.LANGUAGE_PROMPT[code]))

    def test_the_sidebar_is_drawn_in_the_chosen_language(self):
        """The routing names stay English inside the code; only the label is translated."""
        from scripts import gui_design as gd
        self.i18n.set_language("fr")
        self.assertEqual([self.i18n.tr(n) for n in gd.SIDEBAR_ITEMS][:3], ["Tableau de bord", "Moniteur", "Aperçu en direct"])
        self.assertEqual(gd.SIDEBAR_ITEMS[0], "Dashboard")


class LcdTemperatureUnit(unittest.TestCase):
    """v0.2.6.3: Settings > Units > Fahrenheit also applies to the LCD (the Monitor and the Live Preview)."""

    def setUp(self):
        from libre_panel.sensors.base import Reading
        import settings
        self.R, self.s = Reading, settings
        self.readings = {"cpu.temp": Reading(key="cpu.temp", value=60.0, unit="°C", label="CPU"),
                         "cpu.load": Reading(key="cpu.load", value=60.0, unit="%", label="load")}
        self.history = {"cpu.temp": [50.0, 60.0], "cpu.load": [50.0, 60.0]}

    def test_fahrenheit_converts_temperatures_and_their_history_only(self):
        out, hist = self.s.temps_in_unit(self.readings, self.history, "fahrenheit")
        self.assertEqual((out["cpu.temp"].value, out["cpu.temp"].unit), (140.0, "°F"))
        self.assertEqual(hist["cpu.temp"], [122.0, 140.0])
        self.assertEqual(out["cpu.load"].value, 60.0)  # a load is not a temperature
        self.assertEqual(hist["cpu.load"], [50.0, 60.0])
        self.assertEqual(self.readings["cpu.temp"].value, 60.0)  # the caller's Celsius data is not edited
        self.assertEqual(self.history["cpu.temp"], [50.0, 60.0])

    def test_celsius_or_a_bad_unit_changes_nothing(self):
        for unit in ("celsius", None, "kelvin"):
            out, hist = self.s.temps_in_unit(self.readings, self.history, unit)
            self.assertIs(out, self.readings)
            self.assertIs(hist, self.history)

    def test_a_text_reading_is_left_alone(self):
        readings = {"gpu.temp": self.R(key="gpu.temp", value="n/a", unit="°C")}
        out, _ = self.s.temps_in_unit(readings, {}, "fahrenheit")
        self.assertEqual(out["gpu.temp"].value, "n/a")

    def test_a_theme_with_a_celsius_only_module_keeps_celsius(self):
        """The hardware-dashboard "temps" module has a fixed "°C" format, a 20..100 range and heat rules at 75 and 88:
        Fahrenheit would read 140°C on a full red bar."""
        themes = Path(__file__).resolve().parent.parent / "themes"
        self.assertTrue(self.s.keeps_celsius(themes / "hardware-dashboard"))
        self.assertFalse(self.s.keeps_celsius(themes / "cyberpunk-neon"))
        self.assertFalse(self.s.keeps_celsius(themes / "no-such-theme"))

    def test_the_portrait_themes_write_the_unit_not_a_fixed_c(self):
        """A fixed "°C" in the format would read 140°C after the conversion."""
        import json
        from libre_panel.render.formatting import safe_format
        for name in ("cyberpunk-neon-320x480", "minimal-dark-320x480"):
            theme = json.loads((Path(__file__).resolve().parent.parent / "themes" / name / "theme.json").read_text(encoding="utf-8"))
            formats = [w["format"] for w in theme["widgets"] if w.get("sensor") in ("cpu.temp", "gpu.temp")]
            self.assertTrue(formats, name)
            for fmt in formats:
                self.assertEqual(safe_format(fmt, 140.0, "°F", ""), "140°F")
                self.assertEqual(safe_format(fmt, 60.0, "°C", ""), "60°C")


class ThemePaths(unittest.TestCase):
    """v0.2.3: official themes in the app's themes folder, the user's in %APPDATA%\\TURMO\\themes\\custom, read by the GUI and
    the Monitor alike. (Before, a source GUI saved to the project and the frozen Monitor read an older mirror: the LCD
    showed an older layout than Live Preview.)"""

    def _env(self):
        tmp = Path(tempfile.mkdtemp(prefix="turmo-test-paths-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        patcher = mock.patch.dict(os.environ, {"APPDATA": str(tmp / "appdata"), "LOCALAPPDATA": str(tmp / "local")})
        patcher.start()
        self.addCleanup(patcher.stop)
        (tmp / "builtin").mkdir()
        return tmp

    def test_set_title_renames_a_theme_file_and_leaves_a_missing_one_alone(self):
        """v0.2.5 bug: the editor saved the name into one orientation only, so the Gallery card (landscape file)
        kept "Custom Blank Canvas" for every theme made from the blank canvas."""
        import json
        from scripts import theme_paths
        tmp = self._env()
        self._theme(tmp / "mine", '{"name": "Custom Blank Canvas", "x": 1}')
        theme_paths.set_title(tmp / "mine", "custom-2026-11-18-3")
        data = json.loads((tmp / "mine" / "theme.json").read_text())
        self.assertEqual((data["name"], data["x"]), ("custom-2026-11-18-3", 1))
        theme_paths.set_title(tmp / "absent", "x")  # no file: nothing happens, no error

    def test_user_data_report_says_where_the_data_is_and_flags_a_bundle_path(self):
        """v0.2.5: a frozen exe unpacks its themes into a temp folder; settings and custom themes must be outside it."""
        from scripts import theme_paths
        tmp = self._env()
        text = theme_paths.user_data_report(tmp / "builtin")
        self.assertIn(str(theme_paths.custom_dir()), text)
        self.assertIn("user data outside the bundle", text)
        # the bundle sitting around the user's data is what v0.2.5 guards against
        self.assertIn("USER DATA INSIDE THE BUNDLE", theme_paths.user_data_report(tmp / "appdata"))

    @staticmethod
    def _theme(folder, text="{}"):
        folder.mkdir(parents=True)
        (folder / "theme.json").write_text(text)

    def test_the_custom_folder_is_next_to_settings_json(self):
        from scripts import theme_paths
        from scripts.settings import _config_dir
        self._env()
        self.assertEqual(theme_paths.custom_dir(), _config_dir() / "themes" / "custom")

    def test_a_custom_folder_wins_and_the_official_one_is_the_fallback(self):
        from scripts import theme_paths
        tmp = self._env()
        self._theme(tmp / "builtin" / "both", "official")
        self._theme(theme_paths.custom_dir() / "both", "mine")
        self._theme(tmp / "builtin" / "only-official")
        self.assertEqual((theme_paths.folder(tmp / "builtin", "both") / "theme.json").read_text(), "mine")
        self.assertEqual(theme_paths.folder(tmp / "builtin", "only-official"), tmp / "builtin" / "only-official")
        self.assertEqual(theme_paths.folder(tmp / "builtin", "nowhere"), tmp / "builtin" / "nowhere")
        self.assertTrue(theme_paths.is_custom("both"))
        self.assertFalse(theme_paths.is_custom("only-official"))

    def test_every_folder_with_a_theme_json_is_a_theme_in_either_place(self):
        from scripts import theme_paths
        tmp = self._env()
        self._theme(tmp / "builtin" / "neon")
        self._theme(tmp / "builtin" / "neon-320x480")  # an orientation variant is not a theme of its own
        self._theme(theme_paths.custom_dir() / "mine")
        self._theme(theme_paths.custom_dir() / "mine-480x320")
        (theme_paths.custom_dir() / "no-json").mkdir()
        self.assertEqual(theme_paths.names(tmp / "builtin"), ["mine", "neon"])

    def test_the_old_local_mirror_moves_into_the_custom_folder_without_overwriting_a_newer_copy(self):
        from scripts import theme_paths
        tmp = self._env()
        old = tmp / "local" / "TURMO" / "themes"
        self._theme(old / "stuck-in-mirror", "old")
        self._theme(old / "both", "stale")
        self._theme(theme_paths.custom_dir() / "both", "newer")
        theme_paths.migrate_old_mirror(old)
        self.assertEqual((theme_paths.custom_dir() / "stuck-in-mirror" / "theme.json").read_text(), "old")
        self.assertEqual((theme_paths.custom_dir() / "both" / "theme.json").read_text(), "newer")
        self.assertFalse((old / "stuck-in-mirror").exists())
        theme_paths.migrate_old_mirror(tmp / "no-such-folder")  # nothing to migrate: no error

    def test_the_monitor_finds_a_custom_theme_in_the_custom_folder(self):
        """The LCD bug: the Monitor must read the same folder the editor saves to."""
        from scripts import theme_paths, turmo_runtime as rt
        tmp = self._env()
        self._theme(theme_paths.custom_dir() / "mine-320x480", "saved layout")
        self.assertEqual((rt._theme_folder("mine-320x480") / "theme.json").read_text(), "saved layout")
        self.assertEqual(rt._theme_folder("cyberpunk-neon"), rt.THEMES_DIR / "cyberpunk-neon")  # official: the bundle

    def test_a_half_copied_custom_folder_does_not_hide_the_official_theme(self):
        from scripts import theme_paths
        tmp = self._env()
        self._theme(tmp / "builtin" / "custom-blank-canvas", "official")
        (theme_paths.custom_dir() / "custom-blank-canvas").mkdir(parents=True)  # a copy that failed midway: no theme.json
        self.assertEqual((theme_paths.folder(tmp / "builtin", "custom-blank-canvas") / "theme.json").read_text(), "official")
        self.assertFalse(theme_paths.is_custom("custom-blank-canvas"))

    def test_own_copy_copies_an_official_theme_once_and_keeps_later_edits(self):
        """Graphs and the editor save an edited Custom Blank Canvas into the custom folder, never into the official one."""
        from scripts import theme_paths
        tmp = self._env()
        self._theme(tmp / "builtin" / "blank", "official")
        mine = theme_paths.own_copy(tmp / "builtin", "blank")
        self.assertEqual(mine, theme_paths.custom_dir() / "blank")
        (mine / "theme.json").write_text("edited")
        self.assertEqual(theme_paths.own_copy(tmp / "builtin", "blank"), mine)  # second time: no new copy over the edit
        self.assertEqual((mine / "theme.json").read_text(), "edited")
        self.assertEqual((tmp / "builtin" / "blank" / "theme.json").read_text(), "official")

    def test_a_theme_of_the_user_gets_its_gallery_picture_once_it_has_run(self):
        """The gallery shows "No preview" for a new custom theme; after it ran, its own picture is kept in its folder."""
        import time
        from PIL import Image
        from scripts import theme_paths
        tmp = self._env()
        self._theme(theme_paths.custom_dir() / "mine", "{}")
        self._theme(tmp / "builtin" / "neon")
        frame, obj = Image.new("RGB", (8, 8), "red"), mock.Mock(spec=[])
        save = app.TurmoApp._save_theme_picture
        picture = theme_paths.custom_dir() / "mine" / "preview.png"
        save(obj, "neon", frame)  # official: ships its own picture
        self.assertFalse(hasattr(obj, "_picture_new"))
        save(obj, "mine", frame)
        self.assertTrue(picture.is_file())
        self.assertTrue(obj._picture_new)
        obj._picture_new = False
        stamp = picture.stat().st_mtime_ns
        save(obj, "mine", Image.new("RGB", (8, 8), "blue"))  # same theme.json: not written again
        self.assertEqual(picture.stat().st_mtime_ns, stamp)
        time.sleep(0.05)
        (theme_paths.custom_dir() / "mine" / "theme.json").write_text('{"edited": 1}')  # the theme changed
        save(obj, "mine", Image.new("RGB", (8, 8), "blue"))
        self.assertTrue(obj._picture_new)
        self.assertEqual(Image.open(picture).getpixel((0, 0)), (0, 0, 255))

    def test_a_custom_theme_may_name_its_gallery_category(self):
        from scripts.gui_design import filter_themes, theme_category
        self.assertEqual(theme_category("cyberpunk-neon", "HUD"), "Neon")  # official ones keep their own
        self.assertEqual(theme_category("mine", "hud"), "HUD")
        self.assertEqual(theme_category("mine", "nonsense"), "Custom")
        self.assertEqual(theme_category("mine"), "Custom")
        self.assertEqual(filter_themes(["mine", "other"], "HUD", declared={"mine": "HUD"}), ["mine"])
        self.assertEqual(filter_themes(["mine", "other"], "Custom", declared={"mine": "HUD"}), ["other"])


class EditorFollowsOnlyEditableThemes(unittest.TestCase):
    def test_a_built_in_theme_is_never_loaded_into_the_editor(self):
        ed = mock.Mock(theme_name="mine")
        app.ThemeEditor.follow(ed, "cyberpunk-neon")
        self.assertEqual(ed.theme_name, "mine")
        ed.load_current_theme.assert_not_called()
        app.ThemeEditor.follow(ed, "other-custom")
        self.assertEqual(ed.theme_name, "other-custom")
        ed.load_current_theme.assert_called_once()
        app.ThemeEditor.follow(ed, "custom-blank-canvas")
        self.assertEqual(ed.theme_name, "custom-blank-canvas")


class MonitorExitReport(unittest.TestCase):
    def test_a_worker_that_stops_by_itself_is_explained_in_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            err = Path(tmp) / "err.txt"
            err.write_text("ERROR: No preview found for theme 'x'\n\n", encoding="utf-8")
            log = mock.Mock()
            obj = mock.Mock(_monitor_err_path=err, monitor_process=mock.Mock(returncode=1, pid=7), log_text=log,
                            _ignored_pids=set())
            app.TurmoApp._report_monitor_exit(obj)
            written = "".join(c.args[1] for c in log.insert.call_args_list)
            self.assertIn("exit code 1", written)
            self.assertIn("No preview found for theme 'x'", written)
            self.assertIsNone(obj.monitor_process)
            self.assertIn(7, obj._ignored_pids)


class EditorWidgetsKeepTheirFile(unittest.TestCase):
    def test_every_widget_of_every_theme_survives_a_round_trip(self):
        import json
        checked = 0
        for path in sorted((app.PROJECT_ROOT / "themes").glob("*/theme.json")):
            for w in json.loads(path.read_text(encoding="utf-8")).get("widgets", []):
                back = app.widget_to_dict(app.widget_from_dict(w))
                want = {k: v for k, v in w.items() if not (k == "color_rules" and not v)}
                self.assertEqual(back, want, f"{path.parent.name}/{w.get('id')}")
                checked += 1
        self.assertGreater(checked, 100)

    def test_a_new_icon_gets_an_icon_a_size_and_no_text_keys(self):
        ed = app.ThemeEditor.__new__(app.ThemeEditor)
        ed.widgets, ed.get_canvas_size = [], lambda: (320, 480)
        ed.select_widget = lambda w: None
        ed.add_widget("icon")
        ed.add_widget("icon")
        first, second = ed.widgets
        self.assertNotEqual(first.id, second.id)
        out = app.widget_to_dict(first)
        self.assertEqual((out["icon"], out["size"]), ("cpu", 48))
        self.assertNotIn("text", out)
        self.assertNotIn("font_size", out)


class ShapesAndRealPicture(unittest.TestCase):
    def test_shapes_are_icons_the_renderer_accepts_and_draw_something(self):
        from libre_panel import icons
        from libre_panel.theme import model
        from scripts import shape_icons
        shape_icons.register()
        shape_icons.register()  # twice is safe
        for name in shape_icons.SHAPES:
            self.assertEqual(icons.ICON_NAMES.count(name), 1, name)
            self.assertIn(name, model.ICON_NAMES)
            self.assertIsNotNone(icons.draw_icon(name, 32, (255, 255, 255, 255)).getbbox(), name)

    def test_the_editor_picture_and_the_box_of_a_text_follow_the_real_renderer(self):
        import json
        from scripts import shape_icons
        from scripts.editor_render import Shot
        shape_icons.register()
        root = app.PROJECT_ROOT / "themes" / "custom-blank-canvas-320x480"
        doc = json.loads((root / "theme.json").read_text(encoding="utf-8"))
        doc.pop("widgets")
        clock = {"type": "clock", "id": "c", "x": 100, "y": 200, "format": "%H:%M", "font_size": 30,
                 "color": "#ffffff"}
        shot = Shot(doc, root, [clock], {})
        self.assertEqual(shot.image().size, (320, 480))
        x1, y1, x2, y2 = shot.extent(clock)
        self.assertTrue(100 <= x1 < x2 and 200 <= y1 < y2 and x2 - x1 > 40, (x1, y1, x2, y2))
        moved = dict(clock, x=130, y=210)
        self.assertEqual(shot.extent(moved), (x1 + 30, y1 + 10, x2 + 30, y2 + 10))
        icon = {"type": "icon", "id": "i", "x": 20, "y": 20, "icon": "triangle", "size": 40, "color": "#ff0000"}
        self.assertEqual(Shot(doc, root, [icon], {}).extent(icon)[2] - 20 <= 41, True)


class WidgetStaysOnTheScreen(unittest.TestCase):
    def test_everything_a_widget_paints_is_kept_inside_the_screen(self):
        ed = app.ThemeEditor.__new__(app.ThemeEditor)
        ed.get_canvas_size = lambda: (320, 480)
        ed._shot = lambda: None
        ed.widget_box = lambda w, shot: (w.x + 2, w.y, w.x + 160, w.y + 14)  # a 14 px tall text, 158 wide
        text = app.WidgetConfig(id="d", type="clock", x=400, y=470)
        app.ThemeEditor.keep_inside(ed, text)
        self.assertEqual((text.x, text.y), (320 - 160, 480 - 14))
        text.x, text.y = -30, -5
        app.ThemeEditor.keep_inside(ed, text)
        self.assertEqual((text.x, text.y), (0, 0))


class SettingsFile(unittest.TestCase):
    def test_font_scale_is_saved_with_two_decimals(self):
        import json
        from scripts.settings import Settings
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(Settings, "path", classmethod(lambda cls: Path(tmp) / "s.json")):
            Settings(font_scale=1.0139784946236559).save()
            self.assertEqual(json.loads((Path(tmp) / "s.json").read_text())["font_scale"], 1.01)


class MainWindowStaysHidden(unittest.TestCase):
    """v0.2.1: the main window flashed over the loading screen (recording, 3 frames) because update_idletasks
    mapped it before it was made transparent."""

    def test_alpha_zero_is_set_before_anything_maps_the_window(self):
        import re
        src = (Path(__file__).resolve().parent / "turmo_app_enhanced.py").read_text(encoding="utf-8")
        body = src[src.index("def _apply_window_icon"):src.index("def _set_window_icons")]
        body = "\n".join(l.split("#")[0] for l in body.splitlines())  # code only, not the comments
        first_map = min(m.start() for m in re.finditer(r"update(_idletasks)?\(\)", body))
        self.assertLess(body.index('attributes("-alpha", 0.0)'), first_map)

    def test_the_icons_are_set_before_the_window_first_shows(self):
        """The taskbar button takes its icon when the window first appears (v0.2.3: it kept Tk's feather while the
        title bar was right, because the icons came after update())."""
        src = (Path(__file__).resolve().parent / "turmo_app_enhanced.py").read_text(encoding="utf-8")
        body = src[src.index("def _apply_window_icon"):src.index("def _set_window_icons")]
        code = [l.split("#")[0] for l in body.splitlines()]
        steps = [next(i for i, l in enumerate(code) if needle in l) for needle in
                 ('attributes("-alpha", 0.0)', "update_idletasks()", "self._set_window_icons(user32, hwnd)", "self.root.update()")]
        self.assertEqual(steps, sorted(steps), "order must be: hide, make the wrapper, set the icons, then update()")

    def test_a_fresh_root_gets_the_app_icon_not_the_tk_feather(self):
        """The wrapper window only exists once Tk made it: the icons must reach it on a root nothing has updated yet
        (the real start: the loading screen runs, then tk.Tk() and TurmoApp straight away)."""
        import ctypes
        import tkinter as tk
        user32 = ctypes.windll.user32
        user32.GetParent.restype, user32.GetParent.argtypes = ctypes.c_void_p, (ctypes.c_void_p,)
        user32.SendMessageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)
        root = tk.Tk()
        self.addCleanup(root.destroy)
        fake = mock.Mock(root=root, _startup_log=None)
        fake._set_window_icons = lambda *a: app.TurmoApp._set_window_icons(fake, *a)
        with mock.patch.object(app, "log_startup"):
            app.TurmoApp._apply_window_icon(fake)
        wrapper = user32.GetParent(root.winfo_id())
        for size in (0, 1):  # WM_GETICON: ICON_SMALL, ICON_BIG
            self.assertTrue(user32.SendMessageW(wrapper, 0x7F, size, 0), f"icon {size} missing on the window")
        self.assertEqual(root.attributes("-alpha"), 0.0)  # still hidden until show_window()

    def test_window_is_shown_after_the_loading_screen_is_gone(self):
        src = (Path(__file__).resolve().parent / "turmo_app_enhanced.py").read_text(encoding="utf-8")
        main = src[src.index("def main()"):]
        self.assertLess(main.index("SPLASH.finish()"), main.index("app.show_window()"))
        self.assertLess(main.index("app.show_window()"), main.index("root.mainloop()"))


class NoConsoleAtStartup(unittest.TestCase):
    """v0.2.1: `dotnet --list-runtimes` (run by pythonnet at start-up) opened a terminal window from the exe."""

    def test_pythonnet_load_runs_with_create_no_window_and_is_restored(self):
        src = (Path(__file__).resolve().parent / "turmo_app_enhanced.py").read_text(encoding="utf-8")
        top = src[:src.index("def _splash_step")]
        self.assertLess(top.index("0x08000000"), top.index('pythonnet.load("coreclr")'))
        self.assertLess(top.index('pythonnet.load("coreclr")'), top.index("_subprocess.Popen = _Popen"))

    def test_no_console_flag_reaches_a_real_child_process(self):
        import subprocess
        seen = []
        real = subprocess.Popen

        class Spy(real):
            def __init__(self, *a, **k):
                seen.append(k.get("creationflags"))
                super().__init__(*a, **k)
        ns = {}
        src = (Path(__file__).resolve().parent / "turmo_app_enhanced.py").read_text(encoding="utf-8")
        block = src[src.index("    import subprocess as _subprocess"):src.index("    _subprocess.Popen = _QuietPopen") + len("    _subprocess.Popen = _QuietPopen")]
        import textwrap
        with mock.patch.object(subprocess, "Popen", Spy):
            exec(textwrap.dedent(block), ns)
            try:
                subprocess.run([sys.executable, "-c", "pass"], check=True)
            finally:
                subprocess.Popen = Spy
        self.assertEqual(seen, [0x08000000])


class SerialLatencyTile(unittest.TestCase):
    """Diagnostics > Serial latency (v0.2.9.2): the Monitor times each frame it sends and writes it, the GUI reads it."""

    def setUp(self):
        import settings
        self.settings = settings
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "serial_stats.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_average_of_the_last_ten_frames_and_the_count(self):
        timer = self.settings.SerialTimer(self.path)
        for _ in range(5):
            timer.record(0.100)  # falls out of the window
        for _ in range(10):
            timer.record(0.020)
        ms, frames = self.settings.read_serial_stats(self.path)
        self.assertAlmostEqual(ms, 20.0, places=3)
        self.assertEqual(frames, 15)

    def test_no_file_a_broken_file_and_an_old_file_read_as_not_measured(self):
        read = self.settings.read_serial_stats
        self.assertIsNone(read(self.path))  # no file
        self.path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(read(self.path))
        self.settings.SerialTimer(self.path).record(0.03)
        self.assertIsNotNone(read(self.path))
        self.assertIsNone(read(self.path, now=time.time() + self.settings.SERIAL_STATS_MAX_AGE + 5))  # Monitor stopped

    def test_odd_values_are_ignored_not_shown(self):
        import json
        read = self.settings.read_serial_stats
        now = time.time()
        for bad in ({"ms": float("nan"), "frames": 1, "time": now}, {"ms": -1, "frames": 1, "time": now},
                    {"ms": 1e9, "frames": 1, "time": now}, {"ms": "x", "frames": 1, "time": now},
                    {"ms": 5, "frames": float("inf"), "time": now},  # int(inf) raises OverflowError
                    {"ms": 5, "frames": 1, "time": now + 3600}, {"ms": 5, "frames": 1}, [1, 2], None):
            self.path.write_text(json.dumps(bad), encoding="utf-8")
            self.assertIsNone(read(self.path, now=now), bad)

    def test_a_write_that_fails_costs_nothing(self):
        blocked = Path(self.tmp.name) / "file"
        blocked.write_text("x", encoding="utf-8")  # a file where the folder should be
        timer = self.settings.SerialTimer(blocked / "serial_stats.json")
        timer.record(0.01)  # must not raise
        self.assertEqual(timer.frames, 1)

    def test_monitor_times_the_send_and_the_tile_reads_it(self):
        runtime = (Path(__file__).resolve().parent / "turmo_runtime.py").read_text(encoding="utf-8")
        self.assertIn("serial_timer.record(time.perf_counter() - sent_at)", runtime)
        self.assertIn("SerialTimer, Settings, correct_panel", runtime)
        page = (Path(__file__).resolve().parent / "diagnostics_page.py").read_text(encoding="utf-8")
        self.assertIn("read_serial_stats()", page)
        self.assertNotIn("not measured: the GUI sends no probe", page)


class AboutConfigurationCard(unittest.TestCase):
    """About > Configuration (v0.2.9.4): both folders first, each wrapped and written with %USERPROFILE%."""

    def test_settings_file_then_custom_themes_then_the_facts(self):
        src = (Path(__file__).resolve().parent / "about_page.py").read_text(encoding="utf-8")
        order = [src.index(t) for t in ('path_row(tr("Settings file")', 'path_row(tr("Custom themes")', 'fact(inner, tr("Version")')]
        self.assertEqual(order, sorted(order))
        self.assertIn('return "%USERPROFILE%" + folder[len(home):]', src)
        self.assertIn("wraplength=330", src)


class LogRegulator(unittest.TestCase):
    """v0.3.0 log regulator: old logs go, the newest of each kind and the last error stay, nothing else is touched."""

    DAY = 86400

    def setUp(self):
        import runtime_logging
        self.rl = runtime_logging
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.now = 2_000_000_000.0

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, name, age_days, size=100, text="x"):
        path = self.dir / name
        path.write_text(text * size, encoding="utf-8")
        stamp = self.now - age_days * self.DAY
        os.utime(path, (stamp, stamp))
        return path

    def names(self):
        return sorted(p.name for p in self.dir.iterdir())

    def test_old_logs_go_young_and_foreign_files_stay(self):
        self.make("runtime_20260101_000000.log", 1)
        self.make("runtime_20260102_000000.log", 30)
        self.make("runtime_20260103_000000.log", 40)
        self.make("settings.json", 90)
        self.make("tkinter_minimal_startup.log", 90)
        self.make("notes_runtime_20260101_000000.log", 90)
        (self.dir / "runtime_20260104_000000.log.d").mkdir()
        removed, size = self.rl.sweep_logs(self.dir, keep_days=7, max_mb=20, now=self.now)
        self.assertEqual((removed, size), (2, 200))
        self.assertEqual(self.names(), ["notes_runtime_20260101_000000.log", "runtime_20260101_000000.log",
                                        "runtime_20260104_000000.log.d", "settings.json", "tkinter_minimal_startup.log"])

    def test_the_newest_log_of_each_kind_stays_however_old(self):
        for kind in ("runtime", "startup", "lifecycle"):
            self.make(f"{kind}_20260101_000000.log", 100)
            self.make(f"{kind}_20260102_000000.log", 99)
        self.rl.sweep_logs(self.dir, keep_days=7, max_mb=20, now=self.now)
        self.assertEqual(self.names(), ["lifecycle_20260102_000000.log", "runtime_20260102_000000.log",
                                        "startup_20260102_000000.log"])

    def test_the_last_log_with_an_error_stays_older_ones_go(self):
        self.make("runtime_20260101_000000.log", 50, text="[ERROR] old\n")       # older error: goes
        self.make("runtime_20260102_000000.log", 40, text="[CRITICAL] crash\n")  # newest error: stays
        self.make("runtime_20260103_000000.log", 30, text="fine\n")              # old, no error: goes
        self.make("runtime_20260104_000000.log", 0, text="fine\n")               # newest: stays
        self.rl.sweep_logs(self.dir, keep_days=7, max_mb=20, now=self.now)
        self.assertEqual(self.names(), ["runtime_20260102_000000.log", "runtime_20260104_000000.log"])

    def test_over_the_cap_the_oldest_go_first(self):
        mb = 1024 * 1024
        for i in range(5):  # ages 4, 3, 2, 1, 0 days, 3 MB each: 15 MB against a 10 MB cap
            self.make(f"runtime_2026010{i + 1}_000000.log", 4 - i, size=3 * mb)
        removed, _size = self.rl.sweep_logs(self.dir, keep_days=30, max_mb=10, now=self.now)
        self.assertEqual(removed, 2)
        self.assertEqual(self.names(), ["runtime_20260103_000000.log", "runtime_20260104_000000.log",
                                        "runtime_20260105_000000.log"])

    def test_odd_arguments_never_raise(self):
        self.make("runtime_20260101_000000.log", 100)
        self.make("runtime_20260102_000000.log", 100)
        for keep, cap in ((None, None), ("x", 5), (float("inf"), 20), (-5, -5), (0, 0), (1e400, 1e400)):
            self.rl.sweep_logs(self.dir, keep, cap, self.now)
        self.assertEqual(len(self.names()), 1)  # the newest of its kind always stays
        self.assertEqual(self.rl.sweep_logs(self.dir / "missing", 7, 20, self.now), (0, 0))

    def test_an_error_log_is_spared_before_the_cap_is_counted(self):
        mb = 1024 * 1024
        self.make("runtime_20260101_000000.log", 3, size=6 * mb, text="[ERROR]".ljust(1))  # oldest, holds an error
        self.make("runtime_20260102_000000.log", 2, size=6 * mb)
        self.make("runtime_20260103_000000.log", 0, size=1 * mb)
        removed, _size = self.rl.sweep_logs(self.dir, keep_days=30, max_mb=10, now=self.now)
        self.assertEqual(removed, 1)  # the middle file goes, not nothing
        self.assertEqual(self.names(), ["runtime_20260101_000000.log", "runtime_20260103_000000.log"])

    def test_odd_settings_values_mean_the_defaults_not_one_day_and_one_megabyte(self):
        for name in ("runtime_20260101_000000.log", "runtime_20260102_000000.log", "runtime_20260103_000000.log"):
            self.make(name, 3, size=2 * 1024 * 1024)  # 6 MB, three days old
        for keep, cap in ((True, False), (0, 0), (1.5, 1.5), ("7", "20"), (-1, -1)):
            self.assertEqual(self.rl.sweep_logs(self.dir, keep, cap, self.now), (0, 0), (keep, cap))
        self.assertEqual(len(self.names()), 3)

    def test_only_names_this_app_writes_are_logs(self):
        match = self.rl._OWN_LOG.match
        for ok in ("runtime_20261119_153921.log", "runtime_20261119_153921_2.log", "lifecycle_20261114_144544.log",
                   "startup.log", "startup.1.log", "startup.2.log", "startup_20261119_152347.log"):
            self.assertTrue(match(ok), ok)
        for bad in ("runtime.log", "lifecycle.log", "runtime_20261119.log", "startup.3x.log", "my_runtime_20261119_153921.log",
                    "tkinter_minimal_startup.log", "runtime_20261119_153921.log.bak", "settings.json"):
            self.assertFalse(match(bad), bad)

    def test_a_link_is_not_followed_or_removed(self):
        target = self.make("outside.txt", 100)
        link = self.dir / "runtime_20260101_000000.log"
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError):
            self.skipTest("no permission to create a symbolic link")
        self.make("runtime_20260102_000000.log", 100)
        self.rl.sweep_logs(self.dir, keep_days=7, max_mb=20, now=self.now)
        self.assertTrue(target.exists())
        self.assertTrue(link.is_symlink())

    def test_folder_stats_count_only_own_logs(self):
        self.make("runtime_20260101_000000.log", 1, size=10)
        self.make("startup.log", 1, size=20)
        self.make("startup.1.log", 1, size=30)
        self.make("settings.json", 1, size=999)
        self.assertEqual(self.rl.log_folder_stats(self.dir), (3, 60))

    def test_startup_log_rotates_to_three_files(self):
        path = self.make("startup.log", 0, size=50)
        self.rl.rotate_startup_log(path, max_bytes=100)  # small: nothing happens
        self.assertEqual(self.names(), ["startup.log"])
        for generation in ("a", "b", "c"):
            path.write_text(generation * 200, encoding="utf-8")
            self.rl.rotate_startup_log(path, max_bytes=100)
        self.assertEqual(self.names(), ["startup.1.log", "startup.2.log"])
        self.assertEqual((self.dir / "startup.1.log").read_text(encoding="utf-8")[0], "c")
        self.assertEqual((self.dir / "startup.2.log").read_text(encoding="utf-8")[0], "b")  # "a" was dropped

    def test_a_full_runtime_log_continues_in_a_new_file(self):
        first = self.dir / "runtime_20260101_000000.log"
        old = self.rl._RUNTIME_LOG_FILE
        self.rl._RUNTIME_LOG_FILE = first
        try:
            with mock.patch.object(self.rl, "RUNTIME_LOG_MAX_BYTES", 300):
                for i in range(12):
                    self.rl.log_runtime("TEST", "FILL", "y" * 100)
            second = self.rl._RUNTIME_LOG_FILE
        finally:
            self.rl._RUNTIME_LOG_FILE = old
        self.assertNotEqual(second, first)
        self.assertTrue(first.exists() and second.exists())
        self.assertTrue(all(self.rl._OWN_LOG.match(p.name) for p in self.dir.iterdir()))  # the sweep still knows them


class LogsSettingsAndWiring(unittest.TestCase):
    """Settings > Logs and where the sweep is called (v0.3.0)."""

    def test_defaults_and_a_hand_edited_value_falls_back(self):
        import settings
        from runtime_logging import valid_choice
        s = settings.Settings()
        self.assertEqual((s.log_keep_days, s.log_max_mb), (7, 20))
        choices = (1, 3, 7, 14, 30)
        self.assertEqual([valid_choice(v, choices, 7) for v in (14, 8, True, "x", None, 1e400)], [14, 7, 7, 7, 7, 7])

    def test_the_handler_saves_whole_numbers(self):
        import types
        import settings
        saved = []
        stub = types.SimpleNamespace(settings=settings.Settings(), log_keep_var=Var(30), log_cap_var=Var(50))
        stub.settings.save = lambda: saved.append((stub.settings.log_keep_days, stub.settings.log_max_mb))
        app.TurmoApp.on_log_rule_change(stub)
        self.assertEqual(saved, [(30, 50)])

    def test_clean_now_runs_off_the_window_thread_and_reports(self):
        import types
        import settings
        from scripts import logs_page
        shown, stats = [], []
        st = settings.Settings()
        stub = types.SimpleNamespace(settings=st, root=types.SimpleNamespace(after=lambda ms, fn: fn()),
                                     refresh_log_stats=lambda: stats.append(1),
                                     show_info=lambda title, text, modal=False: shown.append(text))
        with mock.patch.object(logs_page, "sweep_logs", lambda **kw: (3, 2097152)):
            app.TurmoApp.clean_logs_now(stub)
        self.assertEqual(stats, [1])
        self.assertEqual(shown, ["3 files removed, 2.0 MB"])
        shown.clear()
        with mock.patch.object(logs_page, "sweep_logs", lambda **kw: (0, 0)):
            app.TurmoApp.clean_logs_now(stub)
        self.assertEqual(shown, ["Nothing to remove: every log is within the days and the size you chose."])

    def test_the_sweeper_runs_in_a_thread_and_comes_back_in_a_day(self):
        import threading
        import types
        from scripts import logs_page
        import settings
        calls, timers, done = [], [], threading.Event()

        def fake_sweep(**kw):
            calls.append(kw)
            done.set()
        st = settings.Settings()
        st.log_keep_days, st.log_max_mb = 14, 10
        stub = types.SimpleNamespace(settings=st, start_log_sweeper=None,
                                    root=types.SimpleNamespace(after=lambda ms, fn: timers.append(ms)))
        with mock.patch.object(logs_page, "sweep_logs", fake_sweep):
            app.TurmoApp.start_log_sweeper(stub)
            self.assertTrue(done.wait(5))
        self.assertEqual(calls, [{"keep_days": 14, "max_mb": 10}])
        self.assertEqual(timers, [logs_page.SWEEP_EVERY_MS])

    def test_the_gui_the_monitor_and_the_startup_log_are_wired(self):
        here = Path(__file__).resolve().parent
        self.assertIn("LogsPage", (here / "turmo_app_enhanced.py").read_text(encoding="utf-8").split("class TurmoApp(")[1].split(":")[0])
        self.assertIn("app.start_log_sweeper()", (here / "turmo_app_enhanced.py").read_text(encoding="utf-8"))
        self.assertIn("self.build_logs_card(card, row, bg2, small)", (here / "turmo_app_enhanced.py").read_text(encoding="utf-8"))
        self.assertIn("target=sweep_logs", (here / "turmo_runtime.py").read_text(encoding="utf-8"))
        self.assertIn('log_dir / "startup.log"', (here / "gui_common.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
