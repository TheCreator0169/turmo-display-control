"""Where themes live (v0.2.3).

Official themes ship in the app's `themes` folder, read only (inside the exe's temp bundle when frozen).
Themes the user makes live in %APPDATA%\\TURMO\\themes\\custom, next to settings.json: one folder per theme
(<name> landscape, <name>-320x480 portrait). The GUI writes there and the Monitor reads there directly, from
source or frozen, so both always see the same file. A custom folder wins over an official one of the same name
(an edited Custom Blank Canvas). Any folder that holds a theme.json is a theme.
"""
import shutil
from pathlib import Path

VARIANT_SUFFIXES = ("-320x480", "-480x320")


def custom_dir() -> Path:
    try:
        from scripts.settings import _config_dir
    except ImportError:  # the frozen Monitor imports settings as a top-level module
        from settings import _config_dir
    return _config_dir() / "themes" / "custom"


def user_data_report(builtin: Path) -> str:
    """One line for the start-up log (v0.2.5): where the user's data is, and that it is not inside the exe's temp
    bundle. A frozen exe unpacks `builtin` into a temp folder that is gone at exit; the user's data must not be there."""
    try:
        from scripts.settings import Settings
    except ImportError:  # the frozen Monitor imports settings as a top-level module
        from settings import Settings
    mine = custom_dir()
    settings = Settings.path()
    inside = [str(p) for p in (mine, settings) if Path(builtin).resolve() in Path(p).resolve().parents]
    return (f"Settings: {settings} | Custom themes: {mine} | Official themes: {builtin} | "
            + ("USER DATA INSIDE THE BUNDLE: " + ", ".join(inside) if inside else "user data outside the bundle"))


def set_title(theme_dir: Path, title: str) -> None:
    """Write `title` as the "name" of the theme.json in `theme_dir` when it differs (the Gallery card shows it).
    The editor saves one orientation at a time, so the other orientation's file kept the old title (v0.2.5: two
    saved themes both showed "Custom Blank Canvas" on their cards)."""
    import json
    path = Path(theme_dir) / "theme.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("name") != title:
        data["name"] = title
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def folder(builtin: Path, name: str) -> Path:
    """The folder of a theme or of one of its orientation variants: the custom one if there is one."""
    mine = custom_dir() / name
    return mine if (mine / "theme.json").is_file() else Path(builtin) / name  # a half-copied folder does not count


def is_custom(name: str) -> bool:
    return (custom_dir() / name / "theme.json").is_file()


def own_copy(builtin: Path, name: str) -> Path:
    """The custom folder of a theme, made first from the official one when the theme has none yet (copy on save: the
    official folder is read only, and inside the exe it is a temp folder)."""
    mine = custom_dir() / name
    if not is_custom(name):
        shutil.rmtree(mine, ignore_errors=True)  # a half-made folder from a failed copy
        shutil.copytree(Path(builtin) / name, mine)
    return mine


def names(builtin: Path) -> list:
    """Every theme name (official and custom, no orientation variants), sorted."""
    found = set()
    for root in (Path(builtin), custom_dir()):
        if root.is_dir():
            for d in root.iterdir():
                if d.is_dir() and (d / "theme.json").is_file() and not d.name.endswith(VARIANT_SUFFIXES):
                    found.add(d.name)
    return sorted(found)


def migrate_old_mirror(old_dir: Path):
    """Before v0.2.3 user themes of a frozen build were mirrored in %LOCALAPPDATA%\\TURMO\\themes. Move what is there
    into the custom folder (a name already in the custom folder keeps its newer copy), then drop the empty mirror."""
    old_dir = Path(old_dir)
    if not old_dir.is_dir():
        return
    dst = custom_dir()
    for src in list(old_dir.iterdir()):
        if src.is_dir() and not (dst / src.name).exists():
            dst.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst / src.name))
    try:
        old_dir.rmdir()  # only when nothing is left
    except OSError:
        pass  # ok: the old mirror still holds copies of themes the custom folder already has; nothing reads it any more
