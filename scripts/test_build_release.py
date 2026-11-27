#!/usr/bin/env python3
"""Release build script tests (no PyInstaller run, no git changes).

Run:  .venv-win\\Scripts\\python.exe scripts\\test_build_release.py

Checks that a broken git can never look like a clean tree.
"""
import importlib.util
import os
import pathlib
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("build_release", HERE / "build_release.py")
br = importlib.util.module_from_spec(spec)
spec.loader.exec_module(br)


def completed(returncode, stdout="", stderr=""):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)


class GitGuard(unittest.TestCase):
    def test_git_failure_stops_the_build(self):
        # git prints to stderr and exits non-zero, e.g. not a repo or a stuck index.lock
        with mock.patch.object(br.subprocess, "run",
                               return_value=completed(128, "", "fatal: not a git repository")):
            with self.assertRaises(SystemExit) as cm:
                br.git("status", "--porcelain")
        self.assertIn("not a git repository", str(cm.exception))

    def test_failing_git_never_passes_as_clean(self):
        # Before the fix, an empty stdout here passed as "clean" and the build ran.
        # backup and in-use checks are stubbed so a failing test cannot touch dist/ or archives/
        with mock.patch.object(br.subprocess, "run", return_value=completed(128, "", "fatal: boom")), \
                mock.patch.object(br, "backup_previous") as backup, \
                mock.patch.object(br, "in_use", return_value=False), \
                mock.patch.object(br.subprocess, "Popen") as popen:
            with self.assertRaises(SystemExit):
                br.main(["build_release.py", "v0.1.6"])
        backup.assert_not_called()
        popen.assert_not_called()

    def test_dirty_tree_is_refused(self):
        with mock.patch.object(br.subprocess, "run", return_value=completed(0, " M scripts/x.py\n")), \
                mock.patch.object(br, "backup_previous") as backup:
            self.assertEqual(br.main(["build_release.py", "v0.1.6"]), 1)
        backup.assert_not_called()


class UntrackedFiles(unittest.TestCase):
    def test_main_checks_tracked_files_only(self):
        # Untracked files (local notes and folders) must not block a release build.
        with mock.patch.object(br, "git", side_effect=SystemExit("stop after the status check")) as git:
            with self.assertRaises(SystemExit):
                br.main(["build_release.py", "v0.1.7"])
        git.assert_called_with("status", "--porcelain", "--untracked-files=no")


class BackupNaming(unittest.TestCase):
    def test_second_backup_of_the_same_version_gets_a_new_folder(self):
        import tempfile
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "dist").mkdir()
        (root / "archives").mkdir()
        (root / "dist" / "TURMO-Monitor").mkdir()
        exe = root / "dist" / "TURMO-Monitor" / "TURMO-Monitor.exe"
        exe.write_bytes(b"new")
        with mock.patch.object(br, "ROOT", root):
            first = br.backup_previous("v0.1.8")
            exe.write_bytes(b"newer")
            second = br.backup_previous("v0.1.8")
        self.assertNotEqual(first, second)
        self.assertEqual((first / "TURMO-Monitor" / "TURMO-Monitor.exe").read_bytes(), b"new")
        self.assertEqual((second / "TURMO-Monitor" / "TURMO-Monitor.exe").read_bytes(), b"newer")


class OnedirLayout(unittest.TestCase):
    """v0.3.8.5: the GUI and the Monitor are onedir builds: no unpacking at start (a one-file exe once failed with
    "Failed to load Python DLL" when its temp folder was gone), the installer ships the folders."""
    ROOT = pathlib.Path(__file__).resolve().parents[1]

    def test_both_specs_build_a_folder_without_upx(self):
        for spec in ("turmo.spec", "turmo_monitor.spec"):
            text = (self.ROOT / spec).read_text(encoding="utf-8")
            self.assertIn("COLLECT(", text, spec)
            self.assertIn("exclude_binaries=True", text, spec)
            self.assertNotIn("onefile=True", text, spec)
            self.assertNotIn("upx=True", text, spec)

    def test_the_build_script_and_the_installer_use_the_folders(self):
        self.assertEqual(br.OUTPUTS, ["TURMO-Display-Control/TURMO-Display-Control.exe", "TURMO-Monitor/TURMO-Monitor.exe"])
        iss = (self.ROOT / "installer" / "turmo.iss").read_text(encoding="utf-8")
        self.assertIn('Source: "..\dist\TURMO-Display-Control\*"; DestDir: "{app}"', iss)
        self.assertIn('Source: "..\dist\TURMO-Monitor\*"; DestDir: "{app}\TURMO-Monitor"', iss)
        self.assertIn('Name: "{app}\TURMO-Monitor.exe"', iss)  # the old one-file Monitor is removed on upgrade

    def test_the_app_finds_the_monitor_in_its_folder(self):
        text = (self.ROOT / "scripts" / "gui_common.py").read_text(encoding="utf-8")
        self.assertIn('EXE_DIR / "TURMO-Monitor" / "TURMO-Monitor.exe"', text)
        self.assertIn('GUI_EXE = Path(sys.executable)', text)


class ExeVersion(unittest.TestCase):
    def test_version_follows_the_release_number(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
        from scripts import exe_version
        self.assertEqual(exe_version.version_tuple("v0.2.0"), (0, 2, 0, 0))
        text = exe_version.version_text("TURMO GUI", "TURMO-Display-Control", "v1.3.4")
        for want in ("filevers=(1, 3, 4, 0)", "'FileVersion', '1.3.4'", "'ProductName', 'TURMO Display Control'",
                     "'FileDescription', 'TURMO GUI'", "github.com/TheCreator0169", "'OriginalFilename', 'TURMO-Display-Control.exe'"):
            self.assertIn(want, text)
        self.assertTrue(text.isascii())


class SingleSourceModules(unittest.TestCase):
    """v0.2.2: the root had older copies of settings.py and runtime_logging.py, and the Monitor spec put the root first,
    so the frozen Monitor bundled the stale ones (no dim_image) in its PYZ."""

    def test_the_root_has_no_copy_of_scripts_modules(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        for name in ("settings.py", "runtime_logging.py"):
            self.assertTrue((root / "scripts" / name).is_file(), name)
            self.assertFalse((root / name).exists(), f"{name} is duplicated in the project root")

    def test_monitor_spec_analyses_scripts_for_those_modules(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        spec = (root / "turmo_monitor.spec").read_text(encoding="utf-8")
        pathex = next(l for l in spec.splitlines() if l.strip().startswith("pathex="))
        self.assertIn("SCRIPTS_DIR", pathex)


class AppIconStaysInTheBuild(unittest.TestCase):
    """v0.2.3: the title bar and the taskbar showed Tk's feather (the window icon went to a window Tk replaced when it
    mapped). The runtime half is tested in test_gui_logic; this half keeps the icon in every build."""

    ROOT = pathlib.Path(__file__).resolve().parents[1]

    def test_both_specs_use_the_app_icon_and_the_gui_bundles_it(self):
        for name in ("turmo.spec", "turmo_monitor.spec"):
            self.assertIn('"assets" / "turmo_icon.png"', (self.ROOT / name).read_text(encoding="utf-8"), name)
        self.assertIn('(PROJECT_ROOT / "assets").glob', (self.ROOT / "turmo.spec").read_text(encoding="utf-8"))

    def test_the_icon_file_is_a_real_picture_large_enough(self):
        from PIL import Image
        with Image.open(self.ROOT / "assets" / "turmo_icon.png") as im:
            self.assertGreaterEqual(min(im.size), 128)
            self.assertIn("A", im.convert("RGBA").getbands())

    def test_the_built_exes_carry_an_icon(self):
        import ctypes
        for exe in ("TURMO-Display-Control.exe", "TURMO-Monitor.exe"):
            path = self.ROOT / "dist" / exe[:-4] / exe
            if not path.is_file():
                self.skipTest(f"{exe} is not built")
            count = ctypes.windll.shell32.ExtractIconExW(str(path), -1, None, None, 0)
            self.assertGreaterEqual(count, 1, f"{exe} has no icon resource")


if __name__ == "__main__":
    unittest.main(verbosity=2)
