"""The Windows 'Details' properties of the exes (file description, version, product, copyright).

`write_version_file` writes the text file PyInstaller's `version=` option reads. The version comes from
`app_version.TURMO_VERSION`, so it changes with the release number and nowhere else.
"""
from pathlib import Path

from scripts.app_version import TURMO_VERSION

PRODUCT = "TURMO Display Control"
COPYRIGHT = "Copyright \u00a9 TheCreator0169 (github.com/TheCreator0169)"


def version_tuple(version=TURMO_VERSION):
    """'v0.2.0' -> (0, 2, 0, 0): Windows wants four numbers."""
    nums = [int(p) for p in version.lstrip("vV").split(".")]
    return tuple((nums + [0, 0, 0, 0])[:4])


def version_text(description, exe_name, version=TURMO_VERSION):
    nums = version_tuple(version)
    dotted = version.lstrip("vV")  # shown as typed (0.2.0); only the binary field needs four numbers
    strings = [("CompanyName", ""), ("FileDescription", description), ("FileVersion", dotted),
               ("InternalName", exe_name), ("LegalCopyright", COPYRIGHT), ("OriginalFilename", exe_name + ".exe"),
               ("ProductName", PRODUCT), ("ProductVersion", dotted)]
    body = ", ".join(f"StringStruct({k!a}, {v!a})" for k, v in strings)
    return (f"VSVersionInfo(ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004, "
            f"fileType=0x1, subtype=0x0, date=(0, 0)), kids=[StringFileInfo([StringTable('040904B0', [{body}])]), "
            "VarFileInfo([VarStruct('Translation', [1033, 1200])])])\n")


def write_version_file(path, description, exe_name):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(version_text(description, exe_name), encoding="ascii")  # !a escapes the (c) sign
    return str(path)
