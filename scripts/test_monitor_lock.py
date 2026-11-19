#!/usr/bin/env python3
"""Single-instance lock tests for the Monitor (no hardware, no real lock file).

Run:  .venv-win\Scripts\python.exe scripts\test_monitor_lock.py

The lock holder of a frozen build is named TURMO-Monitor.exe, not python.exe. A live
holder must keep the lock, or a second Monitor takes it over.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import scripts.turmo_runtime as rt  # noqa: E402


class LockHolder(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.lock = self.tmp / "monitor.lock"
        self.lock.write_text("4242")
        self.patch = mock.patch.object(rt, "_lock_path", return_value=self.lock)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        for f in self.tmp.glob("*"):
            f.unlink()
        self.tmp.rmdir()

    def _holder(self, name):
        proc = mock.Mock()
        proc.name.return_value = name
        return mock.patch("psutil.pid_exists", return_value=True), \
            mock.patch("psutil.Process", return_value=proc)

    def test_frozen_monitor_holder_keeps_the_lock(self):
        p1, p2 = self._holder("TURMO-Monitor.exe")
        with p1, p2:
            self.assertFalse(rt._acquire_lock())
        self.assertEqual(self.lock.read_text(), "4242")

    def test_source_python_holder_keeps_the_lock(self):
        p1, p2 = self._holder("python.exe")
        with p1, p2:
            self.assertFalse(rt._acquire_lock())

    def test_unrelated_process_is_a_stale_lock(self):
        p1, p2 = self._holder("notepad.exe")
        with p1, p2:
            self.assertTrue(rt._acquire_lock())
        self.assertEqual(self.lock.read_text(), str(os.getpid()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
