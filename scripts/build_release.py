#!/usr/bin/env python3
"""Release build for TURMO (Windows; run with the project venv).

Refuses to build when the git tree is not clean, runs PyInstaller --clean for
turmo.spec (GUI) and turmo_monitor.spec (Monitor), and writes the SHA256
manifest to archives\\<version>-release\\SHA256SUMS-<version>.txt.

Usage (from the project root):
    .venv-win\\Scripts\\python.exe scripts\\build_release.py v0.1.6

The CPU temperature helper (turmo_cpumonitor_helper.spec) is not rebuilt here:
rebuild it only with a verified defect.
"""
import datetime
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = ROOT / ".venv-win" / "Scripts" / "python.exe"
if not PY.exists():  # CI: no project venv, use the running interpreter
    PY = pathlib.Path(sys.executable)
SPECS = ["turmo.spec", "turmo_monitor.spec"]
OUTPUTS = ["TURMO-Display-Control.exe", "TURMO-Monitor.exe"]


def git(*args):
    """Output of a git command. Stops the build when git itself fails, so a broken git
    can never look like a clean tree."""
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_previous(version):
    """Copy the current dist pair to archives/pre-<version>-build-<date>/ before it is replaced.
    If that folder already exists (an earlier build of the same version), the time is added to
    the name, so nothing is overwritten. Returns the backup folder, or None when there is nothing
    to back up."""
    existing = [ROOT / "dist" / name for name in OUTPUTS if (ROOT / "dist" / name).exists()]
    if not existing:
        return None
    now = datetime.datetime.now()
    dest = ROOT / "archives" / f"pre-{version}-build-{now:%Y%m%d}"
    if dest.exists():
        dest = ROOT / "archives" / f"pre-{version}-build-{now:%Y%m%d-%H%M%S}"
    if dest.exists():
        raise FileExistsError(f"backup folder already exists, not overwriting: {dest}")
    dest.mkdir(parents=True)
    lines = []
    for src in existing:
        shutil.copy2(src, dest / src.name)
        lines.append(f"{sha256(src)}  {src.name}")
    (dest / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def in_use(path):
    """True when Windows holds the file open (a running program keeps its exe locked)."""
    try:
        with open(path, "r+b"):
            return False
    except PermissionError:
        return True
    except FileNotFoundError:
        return False


def build_installer(version):
    """v0.3.0: compile installer/turmo.iss into dist/TURMO-Setup-<version>.exe. Returns its path, or None when Inno Setup
    or the helper folder is missing (the two exes are still a complete build; a missing installer is printed, not silent)."""
    iscc = next((p for p in (pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
                             pathlib.Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")) if p.is_file()), None)
    if iscc is None or not (ROOT / "dist" / "TURMO-CpuTempHelper" / "TURMO-CpuTempHelper.exe").is_file():
        print("installer not built: Inno Setup 6 or dist/TURMO-CpuTempHelper is missing")
        return None
    print("== Inno Setup installer/turmo.iss")
    for attempt in range(3):  # a scanner can hold the fresh exes for a few seconds ("file in use", exit 2): wait and retry
        rc = subprocess.run([str(iscc), "/Q", f"/DAppVersion={version}", str(ROOT / "installer" / "turmo.iss")], cwd=ROOT).returncode
        if rc == 0:
            break
        time.sleep(15)
    setup = ROOT / "dist" / f"TURMO-Setup-{version}.exe"
    if rc != 0 or not setup.is_file():
        print(f"installer build failed (exit {rc})")
        return None
    return setup


def main(argv):
    if len(argv) != 2 or not argv[1].startswith("v"):
        print("usage: build_release.py vX.Y.Z")
        return 2
    version = argv[1]
    # Tracked changes only: an untracked file (a note, a local folder) does not change the build.
    dirty = git("status", "--porcelain", "--untracked-files=no")
    if dirty:
        print("refusing to build: the git tree is not clean:\n" + dirty)
        return 1
    busy = [name for name in OUTPUTS if in_use(ROOT / "dist" / name)]
    if busy:
        print("refusing to build: these dist files are in use (stop the program first): " + ", ".join(busy))
        return 1
    try:
        backup = backup_previous(version)
    except FileExistsError as e:
        print(e)
        return 1
    print(f"previous build kept in: {backup}" if backup else "no previous dist pair to back up")
    commit = git("rev-parse", "--short", "HEAD")
    for spec in SPECS:
        print(f"== PyInstaller --clean {spec}")
        rc = subprocess.run([str(PY), "-m", "PyInstaller", "--clean", "--noconfirm", spec], cwd=ROOT).returncode
        if rc != 0:
            print(f"build failed for {spec} (exit {rc})")
            return rc
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    out_dir = ROOT / "archives" / f"{version}-release"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for name in OUTPUTS:
        exe = ROOT / "dist" / name
        lines.append(f"{sha256(exe)}  {name}")
    setup = build_installer(version)
    if setup:
        lines.append(f"{sha256(setup)}  {setup.name}")
    lines.append(f"# {version} built {stamp} with --clean from commit {commit} (clean tree)")
    manifest = out_dir / f"SHA256SUMS-{version}.txt"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"manifest: {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
