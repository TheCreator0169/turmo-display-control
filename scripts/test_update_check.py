#!/usr/bin/env python3
"""v0.3.4: the Update button (scripts/update_check.py and the About page's methods), no network, no window.

Run:  .venv-win/Scripts/python.exe scripts/test_update_check.py
"""
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from scripts import update_check as uc  # noqa: E402

BASE = uc.DOWNLOAD_PREFIX + "v0.9.0/"
SETUP = "TURMO-Setup-v0.9.0.exe"


class FakeResponse(io.BytesIO):
    def __init__(self, data, length=True):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))} if length else {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def latest_json(tag="v0.9.0", assets=None):
    if assets is None:
        assets = [{"name": SETUP, "browser_download_url": BASE + SETUP},
                  {"name": "SHA256SUMS.txt", "browser_download_url": BASE + "SHA256SUMS.txt"}]
    return json.dumps({"tag_name": tag, "html_url": "https://github.com/x/y/releases/tag/" + tag,
                       "assets": assets}).encode()


class Versions(unittest.TestCase):
    def test_a_newer_tag_is_newer_and_the_same_or_older_is_not(self):
        self.assertTrue(uc.is_newer("v0.3.4", "v0.3.3"))
        self.assertTrue(uc.is_newer("v0.10.0", "v0.9.9"))  # numbers, not text
        self.assertFalse(uc.is_newer("v0.3.3", "v0.3.3"))
        self.assertFalse(uc.is_newer("v0.3.2", "v0.3.3"))
        self.assertTrue(uc.is_newer("v0.3.0", "v0.2.9.22"))  # the old four-part development versions

    def test_a_tag_that_is_not_a_version_is_never_an_update(self):
        for tag in ("", "latest", "v1", "v1.2.3-beta", "1.2.3", None):
            self.assertIsNone(uc.version_tuple(tag))
            self.assertFalse(uc.is_newer(tag, "v0.3.3"))


class Fetch(unittest.TestCase):
    def test_the_latest_release_gives_its_installer_and_checksum_addresses(self):
        release = uc.fetch_latest(urlopen=lambda req, timeout: FakeResponse(latest_json()))
        self.assertEqual((release.tag, release.setup_name, release.setup_url), ("v0.9.0", SETUP, BASE + SETUP))
        self.assertEqual(release.sums_url, BASE + "SHA256SUMS.txt")
        self.assertTrue(release.has_installer())

    def test_an_installer_address_outside_this_projects_releases_is_dropped(self):
        assets = [{"name": SETUP, "browser_download_url": "https://evil.example/" + SETUP},
                  {"name": "SHA256SUMS.txt", "browser_download_url": BASE + "SHA256SUMS.txt"}]
        release = uc.fetch_latest(urlopen=lambda req, timeout: FakeResponse(latest_json(assets=assets)))
        self.assertFalse(release.has_installer())

    def test_a_file_that_is_not_the_setup_is_not_taken_for_it(self):
        assets = [{"name": "TURMO-Guide-v0.9.0.pdf", "browser_download_url": BASE + "TURMO-Guide-v0.9.0.pdf"}]
        release = uc.fetch_latest(urlopen=lambda req, timeout: FakeResponse(latest_json(assets=assets)))
        self.assertFalse(release.has_installer())

    def test_an_unreachable_github_is_a_readable_error(self):
        def boom(req, timeout):
            raise OSError("no network")
        with self.assertRaises(uc.UpdateError) as caught:
            uc.fetch_latest(urlopen=boom)
        self.assertIn("no network", str(caught.exception))

    def test_a_release_without_a_version_tag_is_refused(self):
        with self.assertRaises(uc.UpdateError):
            uc.fetch_latest(urlopen=lambda req, timeout: FakeResponse(latest_json(tag="nightly")))


class Checksum(unittest.TestCase):
    HASH = "ab" * 32

    def test_the_hash_is_read_for_the_installer_in_both_sums_styles(self):
        self.assertEqual(uc.parse_sums(f"{self.HASH} *{SETUP}\n", SETUP), self.HASH)
        self.assertEqual(uc.parse_sums(f"{'cd' * 32}  other.pdf\n{self.HASH}  {SETUP}\n", SETUP), self.HASH)

    def test_no_line_for_the_installer_or_a_short_hash_gives_none(self):
        self.assertIsNone(uc.parse_sums(f"{self.HASH} *other.exe\n", SETUP))
        self.assertIsNone(uc.parse_sums(f"abc123 *{SETUP}\n", SETUP))

    def test_a_release_without_a_checksum_for_its_installer_is_refused(self):
        release = uc.Release("v0.9.0", "", SETUP, BASE + SETUP, BASE + "SHA256SUMS.txt")
        with self.assertRaises(uc.UpdateError):
            uc.fetch_checksum(release, urlopen=lambda req, timeout: FakeResponse(b"nothing here\n"))


class Download(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.release = uc.Release("v0.9.0", "", SETUP, BASE + SETUP, BASE + "SHA256SUMS.txt")
        self.data = os.urandom(2_500_000)

    def test_a_download_that_matches_is_kept_and_reports_progress(self):
        seen = []
        path = uc.download(self.release, self.dir.name, hashlib.sha256(self.data).hexdigest(),
                           progress=lambda done, total: seen.append((done, total)),
                           urlopen=lambda req, timeout: FakeResponse(self.data))
        self.assertEqual(Path(path).read_bytes(), self.data)
        self.assertEqual(seen[-1], (len(self.data), len(self.data)))
        self.assertEqual(os.listdir(self.dir.name), [SETUP])  # no .part left

    def test_a_download_that_does_not_match_is_deleted_not_kept(self):
        with self.assertRaises(uc.UpdateError) as caught:
            uc.download(self.release, self.dir.name, "0" * 64, urlopen=lambda req, timeout: FakeResponse(self.data))
        self.assertIn("checksum", str(caught.exception))
        self.assertEqual(os.listdir(self.dir.name), [])

    def test_a_download_that_stops_halfway_leaves_nothing(self):
        class Broken(FakeResponse):
            def read(self, n=-1):
                if self.tell() > 0:
                    raise OSError("connection reset")
                return super().read(1 << 20)
        with self.assertRaises(uc.UpdateError):
            uc.download(self.release, self.dir.name, hashlib.sha256(self.data).hexdigest(),
                        urlopen=lambda req, timeout: Broken(self.data))
        self.assertEqual(os.listdir(self.dir.name), [])


class AboutButton(unittest.TestCase):
    """The About page's methods on a stand-in object: what is shown for each answer."""

    def page(self):
        from scripts import about_page
        obj = mock.Mock()
        obj._update_busy = True
        return about_page, obj

    def test_the_same_version_says_so_in_a_toast_and_offers_nothing(self):
        about_page, obj = self.page()
        from scripts.app_version import TURMO_VERSION
        release = uc.Release(TURMO_VERSION, "", SETUP, BASE + SETUP, BASE + "SHA256SUMS.txt")
        about_page.AboutPage._update_checked(obj, {"release": release})
        self.assertFalse(obj._update_busy)
        obj.toast.assert_called_once()
        self.assertIn(TURMO_VERSION, obj.toast.call_args[0][0])
        obj.confirm.assert_not_called()

    def test_a_newer_version_asks_before_downloading_anything(self):
        about_page, obj = self.page()
        release = uc.Release("v99.0.0", "", SETUP, BASE + SETUP, BASE + "SHA256SUMS.txt")
        about_page.AboutPage._update_checked(obj, {"release": release})
        obj.confirm.assert_called_once()
        self.assertIn("v99.0.0", obj.confirm.call_args[0][1])
        obj._download_update.assert_not_called()  # only the yes button starts it

    def test_a_newer_version_without_a_checkable_installer_only_warns(self):
        about_page, obj = self.page()
        release = uc.Release("v99.0.0", "https://github.com/x/y", None, None, None)
        about_page.AboutPage._update_checked(obj, {"release": release})
        obj.show_warning.assert_called_once()
        obj.confirm.assert_not_called()

    def test_an_error_is_shown_not_swallowed(self):
        about_page, obj = self.page()
        about_page.AboutPage._update_checked(obj, {"error": uc.UpdateError("GitHub did not answer (x)")})
        obj.show_error.assert_called_once()
        self.assertFalse(obj._update_busy)

    def test_pressing_twice_does_not_start_two_checks(self):
        about_page, obj = self.page()
        about_page.AboutPage.check_for_updates(obj)  # _update_busy is already True
        obj.toast.assert_not_called()
        obj._run_in_thread.assert_not_called()

    def test_every_new_text_has_a_french_and_a_portuguese_version(self):
        from scripts import about_page, i18n
        for text in (about_page.UPDATE_TEXT, about_page.NO_INSTALLER_TEXT, "Checking for updates...",
                     "You have the latest version ({version}).", "Could not check for updates", "Update available",
                     "Download and install", "Downloading...", "Could not download the update",
                     "Could not start the installer"):
            self.assertIn(text, i18n.TABLE)
            self.assertEqual(len(i18n.TABLE[text]), 2)


if __name__ == "__main__":
    unittest.main()
