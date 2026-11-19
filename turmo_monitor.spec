# PyInstaller spec file for TURMO Monitor Worker
# Build: pyinstaller --clean turmo_monitor.spec
# This creates a standalone headless executable for the monitoring service

import sys
import os
from pathlib import Path

# SPEC is provided by PyInstaller's spec exec context (path to this .spec file)
PROJECT_ROOT = Path(SPEC).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.exe_version import write_version_file

# Add vendor directory to path so collect_all finds libre_panel locally
VENDOR_DIR = PROJECT_ROOT / "scripts" / "vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))
    print(f"[SPEC DEBUG] Added vendor dir: {VENDOR_DIR}", file=sys.stderr)
else:
    print(f"[SPEC DEBUG] Vendor dir NOT found: {VENDOR_DIR}", file=sys.stderr)

from PyInstaller.utils.hooks import collect_all

SCRIPTS_DIR = PROJECT_ROOT / "scripts"
THEMES_DIR = PROJECT_ROOT / "themes"
DOCS_DIR = PROJECT_ROOT / "docs"
PREVIEWS_DIR = PROJECT_ROOT / "previews"

# libre_panel is now vendored in scripts/vendor/libre_panel
# collect_all pulls every submodule, data file, and binary.
lp_datas, lp_binaries, lp_hiddenimports = collect_all('libre_panel')
# Filter out .py files from datas - they should be handled as hiddenimports (Python modules)
# not as data files extracted to _MEIPASS
lp_datas = [(src, dest) for src, dest in lp_datas if not src.endswith('.py')]
# Filter hiddenimports: remove problematic sensor modules that PyInstaller can't analyze
# from the foreign venv. Keep only what we actually need.
lp_hiddenimports = [h for h in lp_hiddenimports if not h.startswith('libre_panel.sensors.') and not h.startswith('libre_panel.sensorservice')]
print(f"[SPEC DEBUG] collect_all: {len(lp_datas)} datas (filtered), {len(lp_binaries)} binaries, {len(lp_hiddenimports)} hiddenimports (filtered)", file=sys.stderr)
datas = list(lp_datas)
binaries = list(lp_binaries)
hiddenimports = list(lp_hiddenimports)
print(f"[SPEC DEBUG] initial hiddenimports: {len(hiddenimports)}", file=sys.stderr)

# Include all themes
for theme_dir in THEMES_DIR.iterdir():
    if theme_dir.is_dir():
        theme_json = theme_dir / "theme.json"
        if theme_json.exists():
            datas.append((str(theme_json), f"themes/{theme_dir.name}"))
        for extra in theme_dir.glob("*"):
            if extra.suffix in (".ttf", ".otf", ".png", ".jpg", ".jpeg"):
                datas.append((str(extra), f"themes/{theme_dir.name}"))

# Include docs
if DOCS_DIR.exists():
    for doc in DOCS_DIR.rglob("*"):
        if doc.is_file():
            datas.append((str(doc), str(doc.parent.relative_to(PROJECT_ROOT))))

# Include previews
if PREVIEWS_DIR.exists():
    for preview in PREVIEWS_DIR.rglob("*"):
        if preview.is_file() and "old" not in preview.relative_to(PREVIEWS_DIR).parts:  # previews\old keeps the old pictures, not shipped
            datas.append((str(preview), str(preview.parent.relative_to(PROJECT_ROOT))))

# Include START-TURMO.bat and check_pawnio.py
for fname in ["START-TURMO.bat", "check_pawnio.py"]:
    f = PROJECT_ROOT / fname
    if f.exists():
        datas.append((str(f), "."))

# Include vendored libre_panel directory
VENDOR_LIBRE_PANEL = PROJECT_ROOT / "scripts" / "vendor" / "libre_panel"
if VENDOR_LIBRE_PANEL.exists():
    datas.append((str(VENDOR_LIBRE_PANEL), "scripts/vendor/libre_panel"))
    print(f"[SPEC DEBUG] Added vendored libre_panel: {VENDOR_LIBRE_PANEL}", file=sys.stderr)
else:
    print(f"[SPEC DEBUG] Vendored libre_panel NOT found: {VENDOR_LIBRE_PANEL}", file=sys.stderr)

# Include scripts that are needed at runtime (turmo_runtime.py is entry point, compiled automatically)
scripts_to_include = [
    "settings.py",
    "runtime_logging.py",
]
for script in scripts_to_include:
    script_path = SCRIPTS_DIR / script
    if script_path.exists():
        datas.append((str(script_path), "scripts"))

# Bundle LibreHardwareMonitor DLLs for CPU/GPU sensors
LHM_DIR = PROJECT_ROOT / "scripts" / "vendor" / "lhm"
if LHM_DIR.exists():
    for dll in LHM_DIR.glob("*.dll"):
        datas.append((str(dll), "lhm"))
    print(f"[SPEC] Bundled {sum(1 for _ in LHM_DIR.glob('*.dll'))} LHM DLLs → lhm/", file=sys.stderr)

# Hidden imports for monitor worker (headless - no GUI dependencies)
hiddenimports += [
    "psutil",
    "pynvml",
    "numpy",
    "serial",
    "serial.tools.list_ports",
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
    "argparse",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageChops",
    # libre_panel modules needed by monitor
    "libre_panel",
    "libre_panel.sensors",
    "libre_panel.sensors.base",
    "libre_panel.sensors.psutil_provider",
    "libre_panel.render",
    "libre_panel.theme",
    "libre_panel.theme.model",
    # pythonnet for LHM GPU sensors
    "pythonnet",
    "clr",
    # stdlib modules needed by libre_panel
    "tomllib",
    # runtime logging
    "runtime_logging",
]
print(f"[SPEC DEBUG] final hiddenimports: {len(hiddenimports)}", file=sys.stderr)

# Excludes - keep it lean for headless worker
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
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.colorchooser",
    "pystray",
]

a = Analysis(
    ["scripts/turmo_runtime.py"],
    pathex=[str(PROJECT_ROOT), str(SCRIPTS_DIR), str(PROJECT_ROOT / ".venv-win" / "Lib" / "site-packages")],  # scripts/ holds settings and runtime_logging (the only copies)
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="TURMO-Monitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console for logging output
    onefile=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "assets" / "turmo_icon.png"),
    version=write_version_file(PROJECT_ROOT / "build" / "version_TURMO-Monitor.txt", "TURMO Monitor", "TURMO-Monitor"),
)