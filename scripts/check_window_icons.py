"""Frozen smoke check of the GUI's icons (v0.2.3): start the exe, wait for its window, ask Windows for the window's
small and big icons (WM_GETICON) and for the taskbar strip, then stop exactly the processes it started (by PID).
Zero from WM_GETICON means Tk's feather in the title bar and the taskbar.

    .venv-win\\Scripts\\python.exe scripts\\check_window_icons.py dist\\TURMO-Display-Control.exe [taskbar.png]

Exit 0 when both icons are set. The taskbar picture is for a human to look at (the T logo, not a feather)."""
import ctypes
import subprocess
import sys
import time

import psutil
from PIL import ImageGrab

TITLE = "TURMO Display Control"


def window_icons(user32, title=TITLE, wait=60.0):
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.SendMessageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)
    user32.IsWindowVisible.argtypes = (ctypes.c_void_p,)
    deadline = time.time() + wait
    while time.time() < deadline:
        hwnd = user32.FindWindowW(None, title)
        if hwnd and user32.IsWindowVisible(hwnd):
            time.sleep(3)  # the window is shown only after the loading screen is gone
            # the first window can be replaced (the app rebuilds itself while starting): ask the current one, a few times
            for _ in range(10):
                hwnd = user32.FindWindowW(None, title) or hwnd
                small, big = user32.SendMessageW(hwnd, 0x7F, 0, 0), user32.SendMessageW(hwnd, 0x7F, 1, 0)
                if small and big:
                    break
                time.sleep(1)
            return hwnd, small, big
        time.sleep(0.5)
    return None, None, None


def main(argv):
    exe = argv[1]
    picture = argv[2] if len(argv) > 2 else None
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    proc = subprocess.Popen([exe])
    try:
        hwnd, small, big = window_icons(ctypes.windll.user32)
        print(f"window={hwnd} small icon={small} big icon={big}")
        if picture:
            shot = ImageGrab.grab()
            w, h = shot.size
            shot.crop((int(w * 0.30), h - 56, int(w * 0.72), h)).resize((int(w * 0.84), 112)).save(picture)
            print(f"taskbar picture: {picture}")
        return 0 if (small and big) else 1
    finally:
        try:  # the one-file exe is a bootloader plus a child: stop both, by PID
            parent = psutil.Process(proc.pid)
            victims = parent.children(recursive=True) + [parent]
        except psutil.Error:
            victims = []
        for p in victims:
            try:
                p.terminate()
            except psutil.Error:
                pass  # ok: already gone


if __name__ == "__main__":
    sys.exit(main(sys.argv))
