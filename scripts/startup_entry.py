"""The "Start with Windows" entry (HKCU Run, value TURMO): TURMO Display Control itself, started with --startup (v0.3.7.2).
The window stays hidden in the tray and the GUI starts the Monitor with no console window. Versions 0.3.7 and older
ran TURMO-Monitor.exe directly, a console program: it opened a black window at sign-in."""

MARK = "--startup"


def command(gui_exe):
    return f'"{gui_exe}" {MARK}'


def upgraded(value, gui_exe):
    """The new form of an entry written by an older version (it ran the Monitor), or None when it is not ours or is
    already the new form."""
    if not isinstance(value, str) or MARK in value or "TURMO-Monitor.exe" not in value:
        return None
    return command(gui_exe)
