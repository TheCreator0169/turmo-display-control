#!/usr/bin/env python3
"""v0.3.5: what the user is told when something fails (errors.py, the Update button, settings files, exports), no window.

Run:  .venv-win/Scripts/python.exe scripts/test_error_handling.py
"""
import errno
import json
import os
import socket
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from scripts import errors  # noqa: E402


class FriendlyErrors(unittest.TestCase):
    def test_no_internet_in_all_its_forms(self):
        for e in (urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed")), socket.gaierror(11001, "x"),
                  ConnectionResetError(), urllib.error.URLError(ConnectionRefusedError())):
            self.assertEqual(errors.friendly_error(e), errors.NO_INTERNET, repr(e))

    def test_a_timeout_is_not_called_no_internet(self):
        self.assertEqual(errors.friendly_error(socket.timeout()), errors.TIMED_OUT)
        self.assertEqual(errors.friendly_error(urllib.error.URLError(socket.timeout())), errors.TIMED_OUT)

    def test_github_busy_and_not_found(self):
        for code in (403, 429, 503):
            self.assertEqual(errors.friendly_error(urllib.error.HTTPError("u", code, "m", {}, None)), errors.BUSY)
        self.assertEqual(errors.friendly_error(urllib.error.HTTPError("u", 404, "m", {}, None)), errors.NOT_FOUND_ONLINE)

    def test_file_problems(self):
        self.assertEqual(errors.friendly_error(PermissionError(13, "denied")), errors.ACCESS)
        self.assertEqual(errors.friendly_error(FileNotFoundError(2, "no")), errors.MISSING)
        self.assertEqual(errors.friendly_error(OSError(errno.ENOSPC, "full")), errors.DISK_FULL)
        self.assertEqual(errors.friendly_error(json.JSONDecodeError("x", "y", 0)), errors.BAD_FILE)
        sharing = OSError(); sharing.winerror = 32
        self.assertEqual(errors.friendly_error(sharing), errors.ACCESS)

    def test_anything_else_gets_a_neutral_sentence_and_never_raises(self):
        self.assertEqual(errors.friendly_error(RuntimeError("boom")), errors.OTHER)
        self.assertEqual(errors.friendly_error(None), errors.OTHER)


class CallbackErrors(unittest.TestCase):
    def make(self, quiet=10.0):
        self.log, self.shown, self.now = mock.Mock(), [], [0.0]
        return errors.CallbackErrors(self.log, self.shown.append, quiet=quiet, clock=lambda: self.now[0])

    def test_an_error_is_logged_and_shown_in_plain_words(self):
        handler = self.make()
        handler(PermissionError, PermissionError(13, "denied"), None)
        self.log.assert_called_once()
        self.assertEqual(self.shown, [errors.ACCESS])

    def test_the_same_error_is_shown_once_per_quiet_period_but_always_logged(self):
        handler = self.make()
        err = RuntimeError("a timer failing every second")
        for _ in range(5):
            handler(RuntimeError, err, None)
            self.now[0] += 1
        self.assertEqual(len(self.shown), 1)
        self.assertEqual(self.log.call_count, 5)
        self.now[0] += 20
        handler(RuntimeError, err, None)
        self.assertEqual(len(self.shown), 2)

    def test_a_failing_log_or_a_failing_toast_never_raises(self):
        handler = errors.CallbackErrors(mock.Mock(side_effect=OSError("log")), mock.Mock(side_effect=RuntimeError("ui")))
        handler(ValueError, ValueError("x"), None)  # must not raise: it runs inside Tk's own error path


class Translations(unittest.TestCase):
    def test_every_user_sentence_has_french_and_portuguese(self):
        from scripts import i18n, update_check
        for text in errors.ALL + update_check.MESSAGES:
            self.assertIn(text, i18n.TABLE, text)


class SettingsFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"APPDATA": self.tmp.name, "TURMO_PORTABLE": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        from scripts.settings import Settings
        self.S = Settings

    def test_save_leaves_no_temporary_file_and_reloads(self):
        s = self.S(theme="x-theme")
        s.save()
        self.assertEqual(self.S.load().theme, "x-theme")
        self.assertEqual([p.name for p in self.S.path().parent.iterdir()], ["settings.json"])

    def test_an_import_is_checked_before_it_replaces_anything(self):
        bad = Path(self.tmp.name) / "bad.json"
        for content in ("not json", "[1, 2]", '{"colour": 1}'):
            bad.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                self.S.check_file(bad)
        good = Path(self.tmp.name) / "good.json"
        good.write_text('{"theme": "a"}', encoding="utf-8")
        self.S.check_file(good)  # no error

    def test_a_damaged_settings_file_is_kept_aside_not_overwritten(self):
        self.S().save()
        self.S.path().write_text("{broken", encoding="utf-8")
        self.assertTrue(self.S.quarantine_damaged())
        self.assertEqual((self.S.path().parent / "settings.json.bad").read_text(encoding="utf-8"), "{broken")
        self.assertFalse(self.S.path().exists())
        self.assertFalse(self.S.quarantine_damaged())  # nothing left to move

    def test_a_strange_settings_file_never_crashes_the_loader(self):
        path = self.S.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        for raw in (b"[]", b"42", b"\xff\xfe{}", b"not json"):
            path.write_bytes(raw)
            self.assertEqual(self.S.load().theme, self.S().theme, raw)
        path.write_bytes(b"\xef\xbb\xbf" + b'{"theme": "from-bom"}')
        self.assertEqual(self.S.load().theme, "from-bom")
        path.write_text('{"logging_enabled": "false"}', encoding="utf-8")
        self.assertTrue(self.S.load().logging_enabled)  # a string is not a switch position

    def test_an_import_with_a_wrong_value_is_refused(self):
        bad = Path(self.tmp.name) / "v.json"
        for content in ('{"font_scale": "abc"}', '{"font_scale": 1e400}', '{"quick_panel": 1}', '{"theme": 5}'):
            bad.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError, msg=content):
                self.S.check_file(bad)

    def test_a_bad_reply_from_github_is_not_called_a_bad_file(self):
        import io
        from scripts import update_check
        fake = mock.MagicMock()
        fake.__enter__.return_value = io.BytesIO(b"<html>login</html>")
        with self.assertRaises(update_check.UpdateError) as caught:
            update_check.fetch_latest(urlopen=lambda *a, **k: fake)
        self.assertEqual(str(caught.exception), update_check.NO_VERSION)

    def test_log_runtime_writes_nothing_when_off(self):
        from scripts import runtime_logging as rl
        target = Path(self.tmp.name) / "r.log"
        with mock.patch.object(rl, "_RUNTIME_LOG_FILE", target):
            self.addCleanup(rl.set_enabled, True)
            rl.set_enabled(False)
            rl.log_runtime("T", "OFF", "must not be written")
            self.assertFalse(target.exists())
            rl.set_enabled(True)
            rl.log_runtime("T", "ON", "written")
            self.assertTrue(target.exists())

    def test_logging_is_on_by_default(self):
        self.assertTrue(self.S().logging_enabled)


if __name__ == "__main__":
    unittest.main()
