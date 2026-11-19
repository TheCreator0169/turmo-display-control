# PyInstaller onedir build spec for TURMO CPU Temperature Helper
# For onedir: EXE without PYZ + COLLECT with everything

import sys
import os
from pathlib import Path
from PyInstaller.building.build_main import EXE, COLLECT, PYZ

PROJECT_ROOT = Path(__file__).resolve().parent if "__file__" in dir() else Path(".")
S = sys.stdout.write

# LHM DLLs go to lhm/ inside the bundle
LHM_SRC = PROJECT_ROOT / "scripts" / "vendor" / "lhm"
lhm_datas = []
if LHM_SRC.exists():
    import os
    for f in os.listdir(LHM_SRC):
        if f.lower().endswith(('.dll', '.xml', '.config', '.json')):
            lhm_datas.append((str(LHM_SRC / f), "lhm"))

# Vendored libre_panel (for pythonnet)
VENDOR_LIBRE = PROJECT_ROOT / "scripts" / "vendor" / "libre_panel"
libre_datas = []
if VENDOR_LIBRE.exists():
    libre_datas.append((str(VENDOR_LIBRE), "libre_panel"))

datas = lhm_datas + libre_datas

hiddenimports = [
    "pythonnet", "clr", "ctypes", "sys", "os", "time", "json", "socket", "subprocess",
]

a = Analysis(
    ["scripts/cpu_temp_helper.py"],
    pathex=[str(PROJECT_ROOT), str(PROJECT_ROOT / ".venv-win" / "Lib" / "site-packages")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "numpy", "jinja2"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
)

# PYZ holds the compiled Python modules; without it the EXE fails at startup
pyz = PYZ(a.pure)

# For onedir mode: EXE with scripts only, binaries go to COLLECT
exe = EXE(
    pyz,
    a.scripts,
    [],
    name="TURMO-CpuTempHelper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,  # logon task: no console window
    disable_windowed_traceback=False,
    exclude_binaries=True,  # CRITICAL: binaries (including PYZ) go to COLLECT, not embedded in EXE
)

# COLLECT gathers all binaries, datas, and the EXE into a folder
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TURMO-CpuTempHelper",
)