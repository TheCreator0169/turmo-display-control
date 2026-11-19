"""Quick panel: the small window that rises above the taskbar when the tray icon is clicked (like the
Synology Drive one). Status, three live meters, Start/Stop, brightness and a link to the full window.
Built from the app's own widgets; it reads what the Dashboard already reads (no extra sensor polling)."""

import ctypes
import tkinter as tk
from ctypes import wintypes

from scripts.gui_design import PALETTE, temp_in
from scripts.i18n import tr
from scripts.gui_widgets import Badge, RoundedCard, Slider, make_button

def transparent_key():
    """The window colour made transparent, so the rounded card shows through. It is the card's border colour
    with one blue step added: the anti-aliased corner pixels blend border and key, so they stay the border's
    colour instead of a dark fringe."""
    r, g, b = (int(PALETTE["line2"][i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (r, g, min(b + 1, 255) if b < 255 else b - 1)

WIDTH = 300
MARGIN = 12


def work_area():
    """(left, top, right, bottom) of the screen without the taskbar, wherever the taskbar is."""
    rect = wintypes.RECT()
    try:
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return None


def panel_position(width, height, area, screen):
    """Top-left of the panel: bottom right of the work area, MARGIN from the right edge and flat on the bottom
    one (the taskbar). Pure, for tests."""
    left, top, right, bottom = area or (0, 0, screen[0], screen[1])
    return max(left, right - width - MARGIN), max(top, bottom - height)


def meter_colour(percent):
    return PALETTE["crit"] if percent >= 90 else PALETTE["warn"] if percent >= 75 else PALETTE["cyan"]


def read_meters(app):
    """{cpu, gpu, ram: (percent or None, temperature or None)} from what the Dashboard already reads."""
    values = app._psutil_readings()
    with app._preview_lock:
        readings = dict(app._preview_readings) if app.preview_running else {}

    def read(key):
        return getattr(readings.get(key), "value", None)
    return {"cpu": (values.get("cpu.load"), read("cpu.temp")), "gpu": (read("gpu.load"), read("gpu.temp")),
            "ram": (values.get("mem.load"), None)}


def draw_meter(bar, label, percent, temp, unit="celsius"):
    """A thin bar and its text; no value shows a dash. `temp` is in Celsius, shown in `unit`."""
    bar.delete("all")
    width = max(bar.winfo_width(), 1)
    bar.create_rectangle(0, 0, width, 6, fill=PALETTE["bg3"], outline="")
    if percent is None:
        label.config(text="—")
        return
    bar.create_rectangle(0, 0, width * min(percent, 100) / 100, 6, fill=meter_colour(percent), outline="")
    label.config(text=f"{percent:.0f}%" + (f" {temp_in(temp, unit):.0f}°" if temp is not None else ""))


class QuickPanel:
    def __init__(self, app):
        self.app = app
        self.win = None

    @property
    def visible(self):
        return self.win is not None and self.win.winfo_exists()

    def toggle(self):
        self.close() if self.visible else self.open()

    def close(self):
        if self.visible:
            self.win.destroy()
        self.win = None

    def open(self):
        if self.visible:
            return
        app, root = self.app, self.app.root
        bg1, bg2 = PALETTE["bg1"], PALETTE["bg2"]
        win = self.win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        key = transparent_key()
        win.configure(bg=key)
        try:
            win.attributes("-transparentcolor", key)
        except tk.TclError:
            pass
        card = RoundedCard(win, bg1, PALETTE["line2"], key, radius=16, hard=True)
        # 20 px taller than the window: its bottom corners fall outside it, so the panel sits flat on the taskbar
        card.place(x=0, y=0, relwidth=1, relheight=1, height=20)
        body = card.inner
        font, semi, small = (app.ui_font, 10), (app.ui_semibold, 11), (app.ui_font, 9)

        head = tk.Frame(body, bg=bg1)
        head.pack(fill=tk.X, padx=16, pady=(14, 4))
        tk.Label(head, text="TURMO", bg=bg1, fg=PALETTE["text"], font=(app.ui_semibold, 12)).pack(side=tk.LEFT)
        self._state = Badge(head, bg1, (app.ui_font, 9, "bold"))
        self._state.pack(side=tk.RIGHT)
        self._port = tk.Label(body, text="", bg=bg1, fg=PALETTE["muted"], font=small, anchor="w")
        self._port.pack(fill=tk.X, padx=16)

        self._meters = {}
        grid = tk.Frame(body, bg=bg1)
        grid.pack(fill=tk.X, padx=16, pady=(12, 4))
        grid.columnconfigure(1, weight=1)
        for i, (key, name) in enumerate((("cpu", "CPU"), ("gpu", "GPU"), ("ram", "RAM"))):
            tk.Label(grid, text=name, bg=bg1, fg=PALETTE["muted"], font=small, width=4, anchor="w").grid(
                row=i, column=0, pady=5)
            bar = tk.Canvas(grid, height=6, bg=bg1, highlightthickness=0, bd=0, width=1)
            bar.grid(row=i, column=1, sticky="ew", padx=8)
            value = tk.Label(grid, text="—", bg=bg1, fg=PALETTE["text"], font=("Cascadia Code", 9), width=9,
                             anchor="e")
            value.grid(row=i, column=2)
            self._meters[key] = (bar, value)

        buttons = tk.Frame(body, bg=bg1)
        buttons.pack(fill=tk.X, padx=16, pady=(10, 0))
        self._toggle_btn = make_button(buttons, "Start monitor", self._start_stop, font, variant="primary",
                                       backdrop=bg1)
        self._toggle_btn.pack(fill=tk.X)

        if not hasattr(app, "brightness_var"):
            app.brightness_var = tk.IntVar(value=app.settings.brightness)
        row = tk.Frame(body, bg=bg1)
        row.pack(fill=tk.X, padx=16, pady=(12, 0))
        tk.Label(row, text=tr("Brightness"), bg=bg1, fg=PALETTE["muted"], font=small).pack(side=tk.LEFT)
        self._bright = tk.Label(row, text=f"{int(app.brightness_var.get())}%", bg=bg1, fg=PALETTE["text"],
                                font=("Cascadia Code", 9), width=5, anchor="e")
        self._bright.pack(side=tk.RIGHT)
        Slider(body, 10, 100, app.brightness_var.get(), self._brightness, bg1, variable=app.brightness_var,
               step=1, width=260).pack(padx=16, pady=(4, 0))

        link = tk.Label(body, text=tr("Open TURMO"), bg=bg1, fg=PALETTE["cyan"], font=(app.ui_semibold, 10),
                        cursor="hand2", takefocus=1, highlightthickness=2, highlightbackground=bg1,
                        highlightcolor=PALETTE["cyan"])  # Tk's own ring, same width focused or not; it adds 2 px a side
        link.pack(pady=(10, 12))
        link.bind("<Button-1>", lambda _e: self._open_main())
        for key in ("<space>", "<Return>"):
            link.bind(key, lambda _e: self._open_main())

        win.bind("<Escape>", lambda _e: self.close())
        self._refresh()
        card._fit()
        win.update_idletasks()
        height = body.winfo_reqheight() + 2 * card._inset
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x, y = panel_position(WIDTH, height, work_area(), (sw, sh))
        win.geometry(f"{WIDTH}x{height}+{x}+{y + 24}")
        win.focus_force()
        self._rise(x, y, height, 0)
        win.after(500, self._watch_focus)
        self._tick()

    # --- behaviour --------------------------------------------------------
    def _rise(self, x, y, height, step):  # slides up 24 px in 10 frames
        if not self.visible:
            return
        t = step / 10
        self.win.geometry(f"{WIDTH}x{height}+{x}+{y + round(24 * (1 - t) ** 2)}")
        if step < 10:
            self.win.after(15, self._rise, x, y, height, step + 1)

    def _watch_focus(self):  # closes when the user clicks anywhere else
        if not self.visible:
            return
        if self.win.focus_displayof() is None:
            self.close()
        else:
            self.win.after(200, self._watch_focus)

    def _tick(self):
        if not self.visible:
            return
        try:
            self._refresh()
        except Exception as e:  # never let a bad reading kill the panel
            self.app.log_panel_error(e)
        self.win.after(1000, self._tick)

    def _refresh(self):
        app = self.app
        running = app.monitor_status_var.get().startswith("Running")
        self._state.set("Running" if running else "Stopped", PALETTE["green"] if running else PALETTE["muted"])
        self._toggle_btn.config(text=tr("Stop monitor") if running else tr("Start monitor"))
        port = getattr(app, "port_var", None)
        self._port.config(text=(port.get() if port is not None else "").replace(" ✓", ""))
        for key, (percent, temp) in read_meters(app).items():
            draw_meter(*self._meters[key], percent, temp, app.temp_unit())

    def _start_stop(self):
        if self.app.monitor_status_var.get().startswith("Running"):
            self.app.stop_monitor()
        else:
            self.app.start_monitor()

    def _brightness(self, value):
        self._bright.config(text=f"{int(float(value))}%")
        self.app.on_brightness_change(value)

    def _open_main(self):
        self.close()
        self.app.show_main_window()
