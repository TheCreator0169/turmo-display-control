# PyInstaller spec file for TURMO Display Control
# Build: pyinstaller --clean turmo.spec

import sys
import os
from pathlib import Path

# SPEC is provided by PyInstaller's spec exec context (path to this .spec file)
PROJECT_ROOT = Path(SPEC).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.exe_version import write_version_file
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
THEMES_DIR = PROJECT_ROOT / "themes"
DOCS_DIR = PROJECT_ROOT / "docs"

from PyInstaller.utils.hooks import collect_all

# libre_panel is pip-installed in the build venv, not a source dir.
# collect_all pulls every submodule, data file, and binary.
lp_datas, lp_binaries, lp_hiddenimports = collect_all('libre_panel')
datas = list(lp_datas)
binaries = list(lp_binaries)
hiddenimports = list(lp_hiddenimports)

# Include all themes
for theme_dir in THEMES_DIR.iterdir():
    if theme_dir.is_dir():
        theme_json = theme_dir / "theme.json"
        if theme_json.exists():
            datas.append((str(theme_json), f"themes/{theme_dir.name}"))
        # Include any fonts or images in theme
        for extra in theme_dir.glob("*"):
            if extra.suffix in (".ttf", ".otf", ".png", ".jpg", ".jpeg"):
                datas.append((str(extra), f"themes/{theme_dir.name}"))

# App icon files (window, tray and tray image); the exe icon is the same PNG below (PyInstaller converts it)
for asset in (PROJECT_ROOT / "assets").glob("*"):
    if asset.is_file():
        datas.append((str(asset), "assets"))

# Include docs
if DOCS_DIR.exists():
    for doc in DOCS_DIR.rglob("*"):
        if doc.is_file():
            datas.append((str(doc), str(doc.parent.relative_to(PROJECT_ROOT))))

# Include scripts that are needed at runtime
scripts_to_include = [
    "turmo_runtime.py",
    "settings.py",
]
for script in scripts_to_include:
    script_path = SCRIPTS_DIR / script
    if script_path.exists():
        datas.append((str(script_path), "scripts"))

# Include the entire scripts package for imports
# Add scripts directory to pathex so PyInstaller analyzes it as a package
pathex = [str(PROJECT_ROOT), str(PROJECT_ROOT / ".venv-win" / "Lib" / "site-packages"), str(SCRIPTS_DIR)]
PREVIEWS_DIR = PROJECT_ROOT / "previews"
if PREVIEWS_DIR.exists():
    for preview in PREVIEWS_DIR.rglob("*"):
        if preview.is_file() and "old" not in preview.relative_to(PREVIEWS_DIR).parts:  # previews\old keeps the old pictures, not shipped
            datas.append((str(preview), str(preview.parent.relative_to(PROJECT_ROOT))))

# Bundle LibreHardwareMonitor DLLs for CPU/GPU sensors in scripts/vendor/lhm/
LHM_DIR = PROJECT_ROOT / "scripts" / "vendor" / "lhm"
if LHM_DIR.exists():
    for dll in LHM_DIR.glob("*.dll"):
        datas.append((str(dll), "lhm"))
    print(f"[SPEC] Bundled {sum(1 for _ in LHM_DIR.glob('*.dll'))} LHM DLLs → lhm/", file=sys.stderr)

# Include START-TURMO.bat
bat_file = PROJECT_ROOT / "START-TURMO.bat"
if bat_file.exists():
    datas.append((str(bat_file), "."))

# Include check_pawnio.py
check_file = PROJECT_ROOT / "check_pawnio.py"
if check_file.exists():
    datas.append((str(check_file), "."))

# Hidden imports
hiddenimports += [
    "pystray",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageTk",
    "PIL.ImageFont",
    "psutil",
    "pynvml",
    "numpy",
    "serial",
    "serial.tools.list_ports",
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.colorchooser",
    "json",
    "pathlib",
    "threading",
    "subprocess",
    "time",
    "dataclasses",
    "typing",
    "collections",
    "copy",
    "winreg",
    "ctypes",
    # pythonnet for LHM GPU sensors
    "pythonnet",
    "clr",
]

# Excludes
excludes = [
    "matplotlib",
    
    "scipy",
    "pandas",
    "pytest",
    "sphinx",
    "IPython",
    "jupyter",
    "notebook",
    "test",
    "tests",
]

a = Analysis(
    ["scripts/turmo_app_enhanced.py"],
    pathex=pathex,
    binaries=lp_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Onedir (v0.3.8.5): nothing is unpacked at start, so no temp folder can vanish ("Failed to load Python DLL").
# No UPX: a packed python DLL is slower to load and flagged more often by scanners.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TURMO-Display-Control",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "assets" / "turmo_icon.png"),
    version=write_version_file(PROJECT_ROOT / "build" / "version_TURMO-Display-Control.txt", "TURMO GUI", "TURMO-Display-Control"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TURMO-Display-Control",
)
