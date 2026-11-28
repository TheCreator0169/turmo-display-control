#!/usr/bin/env python3
"""v0.3.0 M3: the Monitor's USB link (UsbLink in turmo_runtime.py) against a fake display, no hardware.

A fake display fails N times then works; a fake clock steps the backoff. Proves the states, the 0.5, 1, 2, then 5 s
backoff, one log line per change of state, the COM number changing, and the status file the GUI reads.

Run:  .venv-win/Scripts/python.exe scripts/test_usb_link.py
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "vendor"))
os.chdir(ROOT)

import serial  # noqa: E402
import settings  # noqa: E402
import turmo_runtime as rt  # noqa: E402


class Info:
    def __init__(self, device, vid=None, pid=None):
        self.device, self.vid, self.pid = device, vid, pid


class FakeDisplay:
    """open() raises while `world.open_errors` is non-empty; send_bitmap() fails while `world.send_ok` is False."""

    def __init__(self, world, port):
        self.world, self.port, self.closed = world, port, False
        world.made.append(port)

    def open(self):
        self.world.opens.append(self.port)
        if self.world.open_errors:
            raise self.world.open_errors.pop(0)

    def send_bitmap(self, image):
        if isinstance(self.world.send_ok, Exception):
            raise self.world.send_ok
        self.world.sent += 1
        return bool(self.world.send_ok)

    def close(self):
        self.closed = True

    def set_landscape(self, landscape):
        self.landscape = landscape

    def request_shutdown(self):
        self.world.shutdown = True


class World:
    def __init__(self):
        self.made, self.opens, self.sent = [], [], 0
        self.open_errors, self.send_ok, self.shutdown = [], True, False
        self.now = 100.0
        self.logs, self.published = [], []
        self.device = "COM4"  # the port the display is on; None = unplugged

    def find(self, preferred):
        return self.device

    def link(self, preferred="COM4"):
        return rt.UsbLink(lambda port: FakeDisplay(self, port), preferred,
                          publish=lambda *a: self.published.append(a), log=lambda *a: self.logs.append(a),
                          clock=lambda: self.now, find=self.find)

    def states(self):
        return [entry[0] for entry in self.logs]


class ResolvePort(unittest.TestCase):
    def test_the_old_port_while_it_exists_else_the_device_by_vid_and_pid_else_none(self):
        turmo = Info("COM5", rt.VID, rt.PID)
        other = Info("COM3", 0x0403, 0x6001)
        self.assertEqual(rt.resolve_port("COM5", [Info("COM4"), turmo, other]), "COM5")  # still the TURMO
        self.assertEqual(rt.resolve_port("COM4", [Info("COM4"), turmo, other]), "COM5")  # COM4 is now another adapter
        self.assertEqual(rt.resolve_port("COM4", [Info("COM4"), other]), "COM4")  # no TURMO listed: the saved port
        self.assertEqual(rt.resolve_port("COM4", [turmo, other]), "COM5")  # the COM number changed
        self.assertEqual(rt.resolve_port(None, [other, turmo]), "COM5")
        self.assertIsNone(rt.resolve_port("COM4", [other]))
        self.assertIsNone(rt.resolve_port(None, []))


class Link(unittest.TestCase):
    def test_connects_at_the_first_attempt_and_logs_it_once(self):
        w = World()
        link = w.link()
        self.assertFalse(link.ready())
        self.assertFalse(link.send_bitmap("frame"))  # not connected: nothing is sent, nothing raises
        link.maintain()
        self.assertTrue(link.ready())
        self.assertTrue(link.send_bitmap("frame"))
        self.assertEqual((w.states(), w.sent), (["connected"], 1))

    def test_a_failed_send_closes_the_display_and_the_backoff_is_half_one_two_then_five_seconds(self):
        w = World()
        link = w.link()
        link.maintain()
        first = link.disp
        w.send_ok = False
        self.assertFalse(link.send_bitmap("frame"))
        self.assertTrue(first.closed)
        self.assertEqual(link.state, "retrying")
        w.send_ok = True
        w.open_errors = [serial.SerialException("could not open port")] * 6
        waits = []
        for _ in range(6):
            before = len(w.opens)
            t0 = w.now
            w.now += 0.01
            link.maintain()  # not due yet: no attempt
            self.assertEqual(len(w.opens), before)
            while len(w.opens) == before:  # step the clock until the attempt happens
                w.now += 0.05
                link.maintain()
            waits.append(round(w.now - t0, 1))
        # the first wait is from the loss (0.5 s), then each failure doubles it up to 5 s, which then repeats
        self.assertEqual(waits[:2], [0.5, 1.0])
        self.assertEqual(waits[2:], [2.0, 5.0, 5.0, 5.0])
        self.assertEqual(w.states(), ["connected", "retrying"])  # six failures, one more line: none

    def test_back_after_the_failures_resets_the_backoff(self):
        w = World()
        link = w.link()
        link.maintain()
        w.send_ok = False
        link.send_bitmap("frame")
        w.send_ok = True
        w.now += 10
        link.maintain()
        self.assertTrue(link.ready())
        self.assertEqual((link.attempt, link.next_try), (0, 0.0))
        self.assertEqual(w.states(), ["connected", "retrying", "connected"])
        w.send_ok = False
        link.send_bitmap("frame")
        self.assertEqual(round(link.next_try - w.now, 1), 0.5)  # the first backoff again, not 5 s

    def test_the_display_comes_back_on_another_com_port(self):
        w = World()
        link = w.link("COM4")
        link.maintain()
        w.send_ok = False
        link.send_bitmap("frame")
        w.device = "COM5"
        w.send_ok = True
        w.now += 1
        link.maintain()
        self.assertEqual((link.state, link.port), ("connected", "COM5"))
        self.assertEqual(w.made, ["COM4", "COM5"])

    def test_not_plugged_in_waits_and_connects_when_it_appears(self):
        w = World()
        w.device = None
        link = w.link()
        for _ in range(20):  # the display is off for a long while: never an exception, never an exit
            w.now += 1
            link.maintain()
        self.assertEqual((link.state, w.opens, w.states()), ("not_found", [], ["not_found"]))
        w.device = "COM4"
        w.now += 10
        link.maintain()
        self.assertTrue(link.ready())
        self.assertEqual(w.states(), ["not_found", "connected"])

    def test_a_port_held_by_another_program_is_busy_not_lost(self):
        w = World()
        link = w.link()
        w.open_errors = [serial.SerialException("could not open port 'COM4': PermissionError(13, 'Access is denied.')")]
        link.maintain()
        self.assertEqual(link.state, "busy")
        w.now += 1
        link.maintain()
        self.assertTrue(link.ready())

    def test_odd_errors_never_escape(self):
        w = World()
        link = w.link()
        w.open_errors = [OSError("device vanished"), ValueError("odd")]
        link.maintain()
        self.assertEqual(link.state, "retrying")
        w.now += 1
        link.maintain()
        w.now += 2
        link.maintain()
        self.assertTrue(link.ready())
        w.send_ok = serial.SerialException("write failed")  # the cable pulled in the middle of a frame
        self.assertFalse(link.send_bitmap("frame"))
        self.assertEqual(link.state, "retrying")

    def test_a_stop_request_ends_the_attempts(self):
        w = World()
        link = w.link()
        link.maintain()
        link.request_shutdown()
        self.assertTrue(w.shutdown)
        self.assertFalse(link.send_bitmap("frame"))
        self.assertEqual(link.state, "connected")  # a stop is not a lost link: no retry line, no new attempt
        link.close()
        self.assertTrue(link.disp is None)


class Resilience(unittest.TestCase):
    def test_a_failing_port_scan_is_not_found_not_a_crash(self):
        w = World()
        def boom(preferred):
            raise OSError("enumeration failed")
        link = w.link()
        link.find = boom
        link.maintain()
        self.assertEqual(link.state, "not_found")

    def test_heartbeat_keeps_the_status_fresh_and_a_signal_stops_the_loop(self):
        w = World()
        link = w.link()
        link.maintain()
        before = len(w.published)
        link.heartbeat()
        self.assertEqual(len(w.published), before + 1)
        self.assertFalse(link.stopping)
        link.request_shutdown()
        self.assertTrue(link.stopping)


class HotOrientation(unittest.TestCase):
    def test_a_changed_setting_switches_and_everything_else_keeps_the_picture(self):
        f = rt._orientation_to_draw
        self.assertEqual(f("portrait", "landscape", False), ("landscape", True, True))
        self.assertEqual(f("landscape", "portrait", True), ("portrait", False, True))
        self.assertEqual(f("portrait", "portrait", False), ("portrait", False, False))  # nothing changed
        self.assertEqual(f("portrait", None, False), ("portrait", False, False))  # file unreadable
        self.assertEqual(f("portrait", "sideways", False), ("portrait", False, False))
        self.assertEqual(f("portrait", 5, False), ("portrait", False, False))
        # started by hand with --landscape while settings say portrait: stays landscape until the setting changes
        self.assertEqual(f("portrait", "portrait", True), ("portrait", True, False))
        # the setting already matches what is drawn: seen moves, nothing to do
        self.assertEqual(f("portrait", "landscape", True), ("landscape", True, False))

    def test_the_display_takes_the_new_size_and_a_link_without_a_display_is_fine(self):
        disp = rt.TurmoDisplay("COM4", landscape=False)
        self.assertEqual((disp.W, disp.H), rt.TURING_SIZE)
        disp.set_landscape(True)
        self.assertEqual((disp.W, disp.H, disp.landscape), (*rt.LANDSCAPE_SIZE, True))
        w = World()
        link = w.link()
        link.set_landscape(True)  # not connected yet: no display to tell, no error
        link.maintain()
        link.set_landscape(False)

    def test_the_loop_uses_it(self):
        text = (ROOT / "scripts" / "turmo_runtime.py").read_text(encoding="utf-8")
        self.assertIn("_orientation_to_draw(seen_orientation, live.orientation, landscape)", text)
        self.assertIn("link.set_landscape(landscape)", text)


class StatusFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "monitor_status.json"
        self.clock = [1000.0]

    def tearDown(self):
        self.tmp.cleanup()

    def writer(self):
        return settings.LinkStatus(self.path, clock=lambda: self.clock[0])

    def test_written_read_and_cleared(self):
        status = self.writer()
        status.write("retrying", "COM4", 2, 990.0)
        got = settings.read_link_status(self.path, now=1001.0)
        self.assertEqual(got, {"state": "retrying", "port": "COM4", "attempt": 2, "since": 990.0})
        status.clear()
        self.assertIsNone(settings.read_link_status(self.path, now=1001.0))
        self.assertFalse(self.path.exists())

    def test_a_heartbeat_is_throttled_but_a_change_is_written_at_once(self):
        status = self.writer()
        status.write("connected", "COM4", 0, 1000.0)
        stamp = json.loads(self.path.read_text(encoding="utf-8"))["time"]
        self.clock[0] += 0.5
        status.write("connected", "COM4", 0, 1000.0)  # same state, 0.5 s later: not rewritten
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["time"], stamp)
        self.clock[0] += 2
        status.write("connected", "COM4", 0, 1000.0)  # 2.5 s later: the heartbeat
        self.assertGreater(json.loads(self.path.read_text(encoding="utf-8"))["time"], stamp)
        status.write("retrying", "COM4", 1, 1003.0)  # a change: at once
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["state"], "retrying")

    def test_old_broken_and_odd_files_read_as_nothing(self):
        read = settings.read_link_status
        self.assertIsNone(read(self.path))  # no file
        self.path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(read(self.path))
        now = 1000.0
        for bad in ({"state": "connected", "time": now - 60}, {"state": "exploded", "time": now},
                    {"state": "connected", "time": float("nan")}, {"state": "connected", "time": now + 3600},
                    {"state": "connected", "time": now, "attempt": float("inf")}, {"state": "connected"}, [1], None, "x"):
            self.path.write_text(json.dumps(bad), encoding="utf-8")
            self.assertIsNone(read(self.path, now=now), bad)
        self.path.write_text(json.dumps({"state": "busy", "time": now, "port": 5}), encoding="utf-8")
        self.assertEqual(read(self.path, now=now)["port"], None)  # a port that is no text is dropped, the state stays

    def test_a_blocked_folder_costs_nothing(self):
        blocked = Path(self.tmp.name) / "file"
        blocked.write_text("x", encoding="utf-8")
        settings.LinkStatus(blocked / "monitor_status.json", clock=lambda: 1.0).write("connected", "COM4", 0, 1.0)  # no raise


def settings_text():
    return (ROOT / "scripts" / "settings.py").read_text(encoding="utf-8")


class Cause(unittest.TestCase):
    """v0.3.8.7: "link lost" used to say nothing about why. The first cause of a failure now goes in the log line."""

    def test_a_write_timeout_is_logged_with_its_chunk_and_time(self):
        class Port:
            writes = 0

            def write(self, data):
                Port.writes += 1
                if Port.writes == 4:  # the header and two chunks went through
                    raise serial.SerialTimeoutException("Write timeout")

        d = rt.TurmoDisplay("COM4")
        d._serial, d._orientation = Port(), "portrait"
        from PIL import Image
        self.assertFalse(d.send_bitmap(Image.new("RGB", (d.W, d.H))))
        self.assertIn("write timeout at chunk 3 of 120", d.last_error)

    def test_the_link_logs_the_cause_of_a_lost_send_and_of_a_failed_open(self):
        w = World()
        link = w.link()
        link.maintain()
        w.send_ok = serial.SerialException("device disconnected")
        link.send_bitmap("frame")
        self.assertEqual(w.logs[-1][0], "retrying")
        self.assertIn("device disconnected", w.logs[-1][3])
        w.send_ok = True
        w.open_errors = [PermissionError("Access is denied")]
        w.now += 1
        link.maintain()
        self.assertEqual(w.logs[-1][0], "busy")
        self.assertIn("Access is denied", w.logs[-1][3])

    def test_the_cause_reaches_the_runtime_log_line(self):
        from unittest import mock
        with mock.patch("runtime_logging.log_runtime") as log:
            rt._log_link("retrying", "COM4", 1, "write timeout at chunk 3 of 60")
        self.assertIn("cause: write timeout at chunk 3 of 60", log.call_args[0][2])


class Wiring(unittest.TestCase):
    def test_the_live_monitor_uses_the_link_and_a_missing_port_does_not_exit(self):
        text = (ROOT / "scripts" / "turmo_runtime.py").read_text(encoding="utf-8")
        self.assertIn("if not port and _args.once:", text)
        self.assertIn("_disp = disp = link = UsbLink(", text)
        self.assertIn("if not link.ready():", text)
        self.assertIn("link.heartbeat()", text)
        self.assertIn("if link.stopping:", text)
        self.assertEqual(settings_text().count("def read_link_status"), 1)
        self.assertIn("link_status.clear()", text)
        self.assertNotIn("giving up until next tick", text)  # the old blocking retry (5 attempts of 2 s) is gone


if __name__ == "__main__":
    unittest.main(verbosity=2)
