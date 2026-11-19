"""Loading screen (v0.2.1): the TURMO logo is the progress bar.

No window background and no bar: a transparent window (per-pixel alpha, UpdateLayeredWindow) shows only the logo.
It starts as a faint grey ghost of the T; the T slides out into TURMO (time-based) and a white-and-black copy of
the logo is wiped over the ghost from left to right as the start-up reaches its real milestones (weights below),
never a guessed percentage and never a number.

Imported first by turmo_app_enhanced.py, before the heavy imports. Frames are the transparent PNGs written by
scripts/make_loading_frames.py (assets/loading_<nn>.png, loading_ghost_<nn>.png, loading_meta.json).

The main thread is busy for seconds (imports, building the window), so the splash runs in its own thread with its
own Tk interpreter and a 60 Hz timer: the animation does not wait for the app. The main thread only hands over
progress: `step(name)` marks a milestone.
"""
import ctypes
import gc
import json
import sys
import threading
import time
import tkinter
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

SIZE = (400, 240)                 # make_loading_frames.SIZE
FRAMES = 49                       # make_loading_frames.FRAMES: 1.2 s of reveal = 40 distinct frames per second
LEAD_IN = 0.45                    # seconds of T alone
REVEAL = 1.2                      # seconds for URMO to slide out; the last frame is then held
MAX_STEP = 0.04                   # most animation time one redraw may add, seconds
TICK_MS = 8                       # timer period; Windows rounds it to about 15.6 ms (64 redraws per second)
FILL_SPEED = 1.5                  # the loaded part moves at most this much of the logo's width per second
FILL_SOFT = 28                    # width in pixels of the soft edge between loaded and not loaded

# Start-up milestones in order, with the weight of the work that ends at each (about the share of the
# measured start-up time). Unknown names are ignored.
STEPS = (
    ("imports", 31), ("settings", 14), ("cleanup", 1),
    ("dashboard", 2), ("monitor", 13), ("preview", 1), ("gallery", 8), ("editor", 1), ("graphs", 5),
    ("settings_tab", 2), ("diagnostics", 3), ("about", 11), ("sidebar", 1),
    ("port", 3), ("tray", 1), ("theme", 4),
)  # seconds measured from source, 2 runs (2.6 and 2.7 s in total), times 100 / 2.7


def frame_index(elapsed):
    """Which frame to show `elapsed` seconds after the splash appeared (0 = T alone, FRAMES-1 = wordmark)."""
    if elapsed <= LEAD_IN:
        return 0
    x = min(1.0, (elapsed - LEAD_IN) / REVEAL)
    return min(FRAMES - 1, round(x * (FRAMES - 1)))


def step_target(done_names):
    """Loaded share (0..1) once the milestones in `done_names` are reached: weight of the last reached milestone
    and everything before it, over the total."""
    total = sum(w for _, w in STEPS)
    reached = 0
    for i, (name, _) in enumerate(STEPS):
        if name in done_names:
            reached = i + 1
    return sum(w for _, w in STEPS[:reached]) / total


def mask_offset(value, ink_x, width=SIZE[0], soft=FILL_SOFT):
    """Crop offset into the wide ramp mask for a loaded share `value`: the loaded part (full logo) ends at
    ink_x[0] - soft when value is 0 (nothing loaded) and at ink_x[1] when it is 1 (all of the ink loaded)."""
    x0, x1 = ink_x
    edge = x0 - soft + value * (x1 - x0 + soft)
    return int(round(width - edge))


def asset_dir():
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
        return (base / "_internal" if (base / "_internal").is_dir() else base) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


class _Layered:
    """A Win32 per-pixel-alpha window: premultiplied BGRA bytes go through a DIB section to UpdateLayeredWindow."""

    class _Header(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    class _Blend(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                    ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

    def __init__(self, hwnd, x, y, w, h):
        self.hwnd, self.w, self.h = hwnd, w, h
        self.u, self.g = ctypes.windll.user32, ctypes.windll.gdi32
        u, g = self.u, self.g
        vp = ctypes.c_void_p
        u.GetDC.restype, u.GetDC.argtypes = vp, [vp]
        u.ReleaseDC.argtypes = [vp, vp]
        g.CreateCompatibleDC.restype, g.CreateCompatibleDC.argtypes = vp, [vp]
        g.CreateDIBSection.restype = vp
        g.CreateDIBSection.argtypes = [vp, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(vp), vp, wintypes.DWORD]
        g.SelectObject.restype, g.SelectObject.argtypes = vp, [vp, vp]
        g.DeleteObject.argtypes = [vp]
        g.DeleteDC.argtypes = [vp]
        u.UpdateLayeredWindow.argtypes = [vp, vp, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE), vp,
                                          ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
                                          ctypes.POINTER(self._Blend), wintypes.DWORD]
        ex = u.GetWindowLongW(hwnd, -20)    # GWL_EXSTYLE: layered, tool window (no taskbar button), never activated
        u.SetWindowLongW(hwnd, -20, ex | 0x00080000 | 0x00000080 | 0x08000000)
        self.screen_dc = u.GetDC(None)
        self.mem_dc = g.CreateCompatibleDC(self.screen_dc)
        header = self._Header(40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)    # top-down 32 bit BGRA
        bits = vp()
        self.dib = g.CreateDIBSection(self.screen_dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        if not self.dib or not bits.value:
            raise OSError("CreateDIBSection failed")
        self.bits = bits.value
        self.old = g.SelectObject(self.mem_dc, self.dib)
        self.dst, self.src, self.size = wintypes.POINT(x, y), wintypes.POINT(0, 0), wintypes.SIZE(w, h)
        self.blend = self._Blend(0, 0, 255, 1)     # AC_SRC_OVER, AC_SRC_ALPHA

    def push(self, bgra):
        ctypes.memmove(self.bits, bgra, self.w * self.h * 4)
        ok = self.u.UpdateLayeredWindow(self.hwnd, self.screen_dc, ctypes.byref(self.dst), ctypes.byref(self.size),
                                        self.mem_dc, ctypes.byref(self.src), 0, ctypes.byref(self.blend), 2)
        if not ok:
            raise OSError("UpdateLayeredWindow failed")

    def close(self):
        try:
            self.g.SelectObject(self.mem_dc, self.old)
            self.g.DeleteObject(self.dib)
            self.g.DeleteDC(self.mem_dc)
            self.u.ReleaseDC(None, self.screen_dc)
        except Exception:
            pass


class Splash:
    """Owns a thread with its own Tk root. Nothing outside that thread touches a widget."""

    def __init__(self):
        self.target = 0.0             # written by the main thread, read by the splash thread (a float: atomic)
        self._done = set()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self.shown_wall = None        # time.time() when the first frame was on screen
        self.ticks = []               # time.perf_counter() of every redraw, for the start-up log
        self.thread = threading.Thread(target=self._run, name="turmo-splash", daemon=True)

    # ---- main thread ----
    def start(self, timeout=3.0):
        self.thread.start()
        return self._ready.wait(timeout)

    def step(self, name):
        if name in dict(STEPS):
            self._done.add(name)
            self.target = max(self.target, step_target(self._done))

    def finish(self):
        """Fill the logo and remove the splash; returns once its window is gone."""
        self.target = 1.0
        self._stop.set()
        self.thread.join(3.0)

    def stats(self):
        """(redraws, seconds shown, average redraws per second, longest gap in ms) for the start-up log."""
        t = self.ticks
        if len(t) < 2:
            return len(t), 0.0, 0.0, 0.0
        span = t[-1] - t[0]
        return len(t), span, (len(t) - 1) / span if span else 0.0, max(b - a for a, b in zip(t, t[1:])) * 1000

    def stalls(self, over_ms=50):
        """[(seconds after the first redraw, gap in ms)] for every gap between redraws longer than `over_ms`."""
        t = self.ticks
        return [(round(b - t[0], 2), round((b - a) * 1000)) for a, b in zip(t, t[1:]) if (b - a) * 1000 > over_ms]

    # ---- splash thread ----
    def _run(self):
        try:
            self._play()
        except Exception:
            pass
        finally:
            self._ready.set()           # never leave the main thread waiting
            gc.collect()                # the Tk objects form cycles: free them here, or the main thread would delete
                                        # the interpreter later ("Tcl_AsyncDelete: async handler deleted by the wrong thread")

    def _play(self):
        from PIL import Image           # here, not at import: the main thread should reach its own work first
        folder = asset_dir()
        ink_x = json.loads((folder / "loading_meta.json").read_text(encoding="utf-8"))["ink_x"]
        w, h = SIZE
        # wide mask: 255 for the first w columns, a soft edge, then 0; a crop of it is the "loaded" part
        row = bytes([255] * w + [round(255 * (1 - k / FILL_SOFT)) for k in range(FILL_SOFT)] + [0] * w)
        ramp = Image.frombytes("L", (len(row), 1), row).resize((len(row), h), Image.NEAREST)

        root = tk.Tk()
        if tkinter._default_root is root:
            tkinter._default_root = None   # the app's own root, created later in the main thread, must be the default
        layered = None
        try:
            root.withdraw()
            root.overrideredirect(True)
            x, y = (root.winfo_screenwidth() - w) // 2, (root.winfo_screenheight() - h) // 2
            root.geometry(f"{w}x{h}+{x}+{y}")
            root.attributes("-topmost", True)
            root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
            layered = _Layered(hwnd, x, y, w, h)
            state = {"frame": -1, "key": None, "value": 0.0, "last": time.perf_counter(), "anim": 0.0,
                     "full": None, "ghost": None}

            def load(i):
                state["full"] = Image.open(folder / f"loading_{i:02d}.png").convert("RGBA")
                state["ghost"] = Image.open(folder / f"loading_ghost_{i:02d}.png").convert("RGBA")

            def draw(final=False):
                now = time.perf_counter()
                dt, state["last"] = now - state["last"], now
                state["anim"] += min(dt, MAX_STEP)   # the main thread can hold the GIL for ~200 ms (it creates its own
                i = frame_index(state["anim"])       # Tk root): the animation pauses there instead of skipping frames
                state["value"] = 1.0 if final else min(self.target, state["value"] + FILL_SPEED * dt)
                off = mask_offset(state["value"], ink_x, w)
                if i != state["frame"]:
                    load(i)
                if (i, off) != state["key"]:
                    mask = ramp.crop((off, 0, off + w, h))
                    out = Image.composite(state["full"], state["ghost"], mask).convert("RGBa")
                    r, g, b, a = out.split()
                    layered.push(Image.merge("RGBA", (b, g, r, a)).tobytes())   # premultiplied BGRA
                    state["frame"], state["key"] = i, (i, off)
                self.ticks.append(now)

            def tick():
                if self._stop.is_set():
                    draw(final=True)
                    root.destroy()      # ends mainloop
                    return
                draw()
                root.after(TICK_MS, tick)

            draw()
            root.deiconify()            # first frame is already in the layered window: no grey Tk window flashes
            root.update()
            draw()                      # Tk may have moved or resized the window while mapping it
            self.shown_wall = time.time()
            self._ready.set()
            root.after(TICK_MS, tick)
            root.mainloop()
        finally:
            if layered is not None:
                layered.close()
            try:
                root.destroy()
            except tk.TclError:
                pass


def start():
    """Show the splash first thing in the app's __main__. Returns the Splash, or None if it cannot be shown."""
    try:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)    # before the first Tk window, or the splash is blurry
        except Exception:
            pass
        splash = Splash()
        if splash.start() and splash.shown_wall is not None:
            return splash
        return None
    except Exception:
        return None
