"""Plain-words errors for the user (v0.3.5).

`friendly_error(e)` turns an exception into one short English sentence a person can act on ("No internet connection",
"The disk is full"). The text is a key of the language table: show it through `tr()`. The raw error stays in the log.
`CallbackErrors` is the root handler for an error inside a button or timer callback: log it, tell the user once.
"""
import errno
import json
import socket
import time
import urllib.error

NO_INTERNET = "No internet connection."
TIMED_OUT = "The connection timed out."
BUSY = "The server is busy. Try again in a few minutes."
NOT_FOUND_ONLINE = "The server did not find what was asked for."
ACCESS = "Windows refused access: the file is in use or protected."
MISSING = "The file or folder was not found."
DISK_FULL = "The disk is full."
BAD_FILE = "The file is not valid."
OTHER = "An unexpected error happened."
ALL = (NO_INTERNET, TIMED_OUT, BUSY, NOT_FOUND_ONLINE, ACCESS, MISSING, DISK_FULL, BAD_FILE, OTHER)


def friendly_error(e):
    """One English sentence for `e` (one of `ALL`). Never raises."""
    reason = getattr(e, "reason", None)
    if isinstance(e, urllib.error.HTTPError):
        return BUSY if e.code in (403, 429, 500, 502, 503, 504) else NOT_FOUND_ONLINE
    if isinstance(e, (socket.timeout, TimeoutError)) or isinstance(reason, (socket.timeout, TimeoutError)):
        return TIMED_OUT
    if isinstance(e, (urllib.error.URLError, socket.gaierror, ConnectionError)) or isinstance(reason, OSError):
        return NO_INTERNET
    if isinstance(e, (json.JSONDecodeError, UnicodeDecodeError)):
        return BAD_FILE
    if isinstance(e, FileNotFoundError):
        return MISSING
    if isinstance(e, PermissionError) or getattr(e, "winerror", None) in (5, 32, 33):
        return ACCESS
    if isinstance(e, OSError) and getattr(e, "errno", None) == errno.ENOSPC:
        return DISK_FULL
    if isinstance(e, ValueError):
        return BAD_FILE
    return OTHER


class CallbackErrors:
    """`root.report_callback_exception`: Tk calls it when a callback raises. Without it the error went to a hidden
    stderr and the button just seemed dead. `log(e)` writes the log line, `show(text)` tells the user; the same kind of
    error is shown at most once every `quiet` seconds (a timer that fails every second must not flood the screen)."""

    def __init__(self, log, show, quiet=10.0, clock=time.monotonic):
        self._log, self._show, self._quiet, self._clock = log, show, quiet, clock
        self._last = {}

    def __call__(self, exc_type, exc, tb):
        try:
            self._log(exc)
        except Exception:
            pass  # ok: a failing log must not hide the message below
        now = self._clock()
        key = (exc_type, str(exc)[:80])
        if now - self._last.get(key, -1e9) < self._quiet:
            return
        self._last[key] = now
        try:
            self._show(friendly_error(exc))
        except Exception:
            pass  # ok: the window may be closing; the error is in the log
