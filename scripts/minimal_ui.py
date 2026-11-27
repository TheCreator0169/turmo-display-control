"""Minimalist look: a small window (about 520 x 440) with four pages in tabs on top: Home, Themes, Settings,
More. It shows and controls the same things as the default window (same Tk variables and handlers); only
the layout is smaller. Settings has the App theme choice, where Default brings back the full window."""

import tkinter as tk

from scripts.i18n import port_text, tr
from scripts.gui_design import LINK_LABELS, ICON_FONT, NO_VALUE, SIDEBAR_ITEMS, mix, PALETTE, is_custom_theme, SENSOR_NAMES, metric_text, sensor_format
from scripts.gui_widgets import (Badge, ChoiceTile, RoundedCard, ScrollFrame, Segmented, Select, Slider, Switch,
                                 make_button)
from scripts.quick_panel import draw_meter, read_meters

SIZE = "540x560"
MIN_SIZE = (540, 560)  # the same as SIZE: no resize and no maximise button in the minimal look
LOG_LINES = 10  # the box shows only the newest lines: the text is replaced at each refresh, so nothing piles up
PAGES = (("home", "Home"), ("themes", "Themes"), ("settings", "Settings"), ("more", "More"))


class MinimalView(tk.Frame):
    def __init__(self, app, parent):
        bg0 = PALETTE["bg0"]
        super().__init__(parent, bg=bg0)
        self.app = app
        self.font, self.small = (app.ui_font, 10), (app.ui_font, 9)
        self.page = tk.StringVar(value="home")
        self.theme_tiles = {}
        self.look_tiles = {}
        self.language_tiles = {}
        self.pages = {}

        head = tk.Frame(self, bg=bg0)
        head.pack(fill=tk.X, padx=16, pady=(14, 0))
        tk.Label(head, text="TURMO", bg=bg0, fg=PALETTE["text"], font=(app.ui_semibold, 14)).pack(side=tk.LEFT)
        self._state = Badge(head, bg0, (app.ui_font, 9, "bold"))
        self._state.pack(side=tk.LEFT, padx=(10, 0), pady=(2, 0))  # 1 px down: its centre was 1.5 px above the title text
        # the same button as a selected tab (size and radius are set below, from the tab bar); 4 px in from the
        # box's edge, where the last tab's segment ends
        self._toggle = make_button(head, "Start", self._start_stop, (app.ui_semibold, 11), variant="primary", backdrop=bg0,
                                   small=True, radius=7, icon=("", (ICON_FONT, 12)), icon_dy=1)  # power glyph, left of the text
        self._toggle.pack(side=tk.RIGHT, padx=(0, 4))
        tk.Label(head, text="·", bg=bg0, fg=PALETTE["text"], font=(app.ui_semibold, 10)).pack(side=tk.RIGHT, padx=(8, 8))
        self._port = tk.Label(head, text="", bg=bg0, fg=PALETTE["muted"], font=self.small)
        self._port.pack(side=tk.RIGHT)

        tabs = tk.Frame(self, bg=bg0)
        tabs.pack(fill=tk.X, padx=16, pady=(12, 8))
        tab_bar = Segmented(tabs, list(PAGES), "home", self.show, bg0, self.font, variable=self.page)
        tab_bar.stretch()
        tab_bar.pack(fill=tk.X)
        # a tab's segment: a quarter of the bar inside its 1 px border and 3 px tray, as tall as the bar inside them
        # exactly a segment's size; only the bold, larger text and the power glyph tell it apart
        self._toggle.configure(height=tab_bar.winfo_reqheight() - 8)
        tabs.bind("<Configure>", lambda e: self._toggle.winfo_exists() and self._toggle.configure(
            width=round((e.width - 8) / len(PAGES))))  # the window may already be rebuilt

        self.stage = tk.Frame(self, bg=bg0)
        self.stage.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 14))
        for key, builder in (("home", self._home), ("themes", self._themes), ("settings", self._settings),
                             ("more", self._more)):
            frame = tk.Frame(self.stage, bg=bg0)
            self.pages[key] = frame
            builder(frame)
        self.show("home")
        app.theme_var.trace_add("write", lambda *_: self._sync_themes())
        self.after(1000, self._tick)

    # --- helpers ---------------------------------------------------------
    def show(self, key):
        for name, frame in self.pages.items():
            frame.pack_forget()
        self.pages[key].pack(fill=tk.BOTH, expand=True)
        self.page.set(key)

    def _card(self, parent, grow=False, top=0):
        card = RoundedCard(parent, PALETTE["bg2"], PALETTE["line"], PALETTE["bg0"], radius=14)
        card.pack(fill=tk.BOTH if grow else tk.X, expand=grow, pady=(top, 0))
        return card

    def _row(self, inner, title, last=False, half=None):
        """A line: the title on the left, the returned frame for its control on the right. half=n: the frame
        runs from the middle of the box (n px further left, for a control that draws n px inside its edge) to
        the right edge, so a control that fills it starts at the middle."""
        bg2 = PALETTE["bg2"]
        line = tk.Frame(inner, bg=bg2, height=36)
        line.pack(fill=tk.X, padx=14, pady=(8, 8))
        if half is not None:
            tk.Label(line, text=title, bg=bg2, fg=PALETTE["text"], font=self.font).place(x=0, rely=0.5, anchor="w")
            holder = tk.Frame(line, bg=bg2)
            holder.place(relx=0.5, x=-half, rely=0.5, anchor="w", relwidth=0.5, width=half)
        else:
            tk.Label(line, text=title, bg=bg2, fg=PALETTE["text"], font=self.font).pack(side=tk.LEFT)
            holder = tk.Frame(line, bg=bg2)
            holder.pack(side=tk.RIGHT)
        if not last:
            tk.Frame(inner, bg=PALETTE["line"], height=1).pack(fill=tk.X, padx=14)
        return holder

    # --- pages -----------------------------------------------------------
    def _home(self, frame):
        app, bg2 = self.app, PALETTE["bg2"]
        card = self._card(frame, grow=True)  # takes the height the controls below leave
        grid = tk.Frame(card.inner, bg=bg2)
        grid.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)
        grid.columnconfigure(1, weight=1)
        self.meters = {}
        for i, (key, name) in enumerate((("cpu", "CPU"), ("gpu", "GPU"), ("ram", "RAM"))):
            grid.rowconfigure(i, weight=1)  # the three bars share the free height
            tk.Label(grid, text=name, bg=bg2, fg=PALETTE["muted"], font=self.small, width=4, anchor="w").grid(
                row=i, column=0, pady=6)
            bar = tk.Canvas(grid, height=6, bg=bg2, highlightthickness=0, bd=0, width=1)
            bar.grid(row=i, column=1, sticky="ew", padx=10)
            value = tk.Label(grid, text="—", bg=bg2, fg=PALETTE["text"], font=("Cascadia Code", 9), width=10,
                             anchor="center")
            value.grid(row=i, column=2)
            self.meters[key] = (bar, value)
        # the other sensors: a name over its value, one row across the box
        tk.Frame(card.inner, bg=PALETTE["line"], height=1).pack(fill=tk.X, padx=14)
        extra = tk.Frame(card.inner, bg=bg2)
        extra.pack(fill=tk.X, padx=14, pady=(8, 10))
        self.extra = {}
        for c, key in enumerate(("cpu.temp", "gpu.temp", "mem.used", "net.down", "net.up")):
            extra.columnconfigure(c, weight=1, uniform="extra")
            tk.Label(extra, text=tr(SENSOR_NAMES[key]), bg=bg2, fg=PALETTE["muted"], font=self.small).grid(row=0, column=c)
            value = tk.Label(extra, text=NO_VALUE, bg=bg2, fg=PALETTE["text"], font=("Cascadia Code", 9))
            value.grid(row=1, column=c)
            self.extra[key] = value
        card._fit()
        card = self._card(frame, top=10)
        orient = Segmented(self._row(card.inner, tr("Orientation"), half=0), [(True, tr("Landscape")), (False, tr("Portrait"))],
                           app.landscape_var.get(), lambda _v: app.on_orientation_change(), bg2, self.small,
                           variable=app.landscape_var)
        orient.stretch()
        orient.pack(fill=tk.X)
        orient.master.master.configure(height=orient.winfo_reqheight())  # the row is as tall as the control: no clipped border
        holder = self._row(card.inner, "Brightness", last=True, half=Slider.PAD)
        label = tk.Label(holder, text=f"{int(app.brightness_var.get())}%", bg=bg2, fg=PALETTE["text"],
                         font=("Cascadia Code", 9), width=5, anchor="e")
        label.pack(side=tk.RIGHT)
        app.brightness_var.trace_add("write", lambda *_: label.config(text=f"{int(app.brightness_var.get())}%"))
        Slider(holder, 10, 100, app.brightness_var.get(), app.on_brightness_change, bg2,
               variable=app.brightness_var, step=1, width=1).pack(side=tk.LEFT, fill=tk.X, expand=True)
        card._fit()

    def _themes(self, frame):
        bg0 = PALETTE["bg0"]
        actions = tk.Frame(frame, bg=bg0)
        actions.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        make_button(actions, tr("New theme"), self._new_theme, self.font, variant="primary", backdrop=bg0,
                    small=True).pack(side=tk.LEFT)
        make_button(actions, tr("Edit in full window"), self._full_editor, self.font, variant="ghost", backdrop=bg0,
                    small=True).pack(side=tk.LEFT, padx=(8, 0))
        scroll = ScrollFrame(frame, bg0, bar_gap=14)  # the tiles are a little narrower: more room for the bar
        scroll.pack(fill=tk.BOTH, expand=True)
        self._theme_host = scroll.body
        self._build_theme_tiles()

    def _build_theme_tiles(self):
        for child in self._theme_host.winfo_children():
            child.destroy()
        self.theme_tiles = {}
        current = self.app.theme_var.get()
        names = [s for s in self.app.get_available_themes() if s != "minimal"]  # "minimal" is only an alias
        for slug in sorted(names, key=is_custom_theme):  # official themes first, the user's last (stable sort)
            tile = ChoiceTile(self._theme_host, slug, slug == current, lambda s=slug: self._pick_theme(s),
                              PALETTE["bg0"], (self.app.ui_semibold, 10), swatches=self.app.theme_swatches(slug))
            tile.pack(fill=tk.X, pady=(0, 6))
            self.theme_tiles[slug] = tile

    def _pick_theme(self, slug):
        self.app.theme_var.set(slug)
        self.app.on_theme_change()

    def _sync_themes(self):
        current = self.app.theme_var.get()
        for slug, tile in self.theme_tiles.items():
            tile.set_selected(slug == current)

    def _new_theme(self):
        self.app.gallery_new()  # opens the editor, which lives in the full window
        self.app.on_app_theme_change("default")
        self.app.select_tab(self.app.nb.index(self.app.editor_frame))

    def _full_editor(self):
        self.app.on_app_theme_change("default")
        self.app.select_tab(self.app.nb.index(self.app.editor_frame))

    def _settings(self, frame):
        app, bg2 = self.app, PALETTE["bg2"]
        card = self._card(frame)
        tk.Label(card.inner, text=tr("App theme"), bg=bg2, fg=PALETTE["text"], font=(app.ui_semibold, 10),
                 anchor="w").pack(fill=tk.X, padx=14, pady=(12, 0))
        tk.Label(card.inner, text=tr("Default brings back the full window."), bg=bg2, fg=PALETTE["muted"],
                 font=self.small, anchor="w").pack(fill=tk.X, padx=14)
        row = tk.Frame(card.inner, bg=bg2)
        row.pack(fill=tk.X, padx=14, pady=(8, 12))
        current = app.settings.app_theme if app.settings.app_theme in ("default", "minimalist") else "default"
        for i, (key, name) in enumerate((("default", tr("Default")), ("minimalist", tr("Minimalist")))):
            row.columnconfigure(i, weight=1, uniform="looks")
            tile = ChoiceTile(row, name, key == current, lambda k=key: app.on_app_theme_change(k), bg2,
                              (app.ui_semibold, 10))
            tile.grid(row=0, column=i, sticky="ew", padx=(0, 8) if i == 0 else 0)
            self.look_tiles[key] = tile
        tk.Frame(card.inner, bg=PALETTE["line"], height=1).pack(fill=tk.X, padx=14)
        tk.Label(card.inner, text=tr("Language"), bg=bg2, fg=PALETTE["text"], font=(app.ui_semibold, 10),
                 anchor="w").pack(fill=tk.X, padx=14, pady=(10, 0))
        row = tk.Frame(card.inner, bg=bg2)
        row.pack(fill=tk.X, padx=14, pady=(8, 12))
        chosen = app.settings.language if app.settings.language in ("en", "fr", "pt") else "en"
        for i, (key, name) in enumerate((("en", "English"), ("fr", "Fran\u00e7ais"), ("pt", "Portugu\u00eas"))):
            row.columnconfigure(i, weight=1, uniform="langs")
            tile = ChoiceTile(row, name, key == chosen, lambda k=key: app.on_language_change(k), bg2,
                              (app.ui_semibold, 10))
            tile.grid(row=0, column=i, sticky="ew", padx=(0, 8) if i < 2 else 0)
            self.language_tiles[key] = tile
        card._fit()
        card = self._card(frame, top=10)
        Switch(self._row(card.inner, tr("Start with Windows")), app.startup_var.get(), lambda _v: app.toggle_startup(),
               bg2, variable=app.startup_var).pack()
        Switch(self._row(card.inner, tr("Quick panel on tray click")), app.quick_panel_var.get(),
               lambda _v: app.on_quick_panel_change(), bg2, variable=app.quick_panel_var).pack()
        Select(self._row(card.inner, "Temperature"), ["celsius", "fahrenheit"], app.temp_unit_var.get(), None, bg2,
               self.small, variable=app.temp_unit_var, width=120).pack()
        Select(self._row(card.inner, tr("Clock"), last=True), ["12h", "24h"], app.clock_unit_var.get(), None, bg2,
               self.small, variable=app.clock_unit_var, width=120).pack()
        card._fit()

    def _more(self, frame):
        app, bg0, bg2 = self.app, PALETTE["bg0"], PALETTE["bg2"]
        from scripts.app_version import TURMO_VERSION
        card = self._card(frame)
        for title, value in (("Version", TURMO_VERSION), ("Port", None), ("Settings file", str(app.settings.path()))):
            holder = self._row(card.inner, tr(title), last=title == "Settings file")
            label = tk.Label(holder, text=value or "", bg=bg2, fg=PALETTE["muted"], font=("Cascadia Code", 9),
                             wraplength=300, justify=tk.RIGHT)
            label.pack()
            if value is None:
                self._port_info = label
        card._fit()
        card = self._card(frame, grow=True, top=10)
        tk.Label(card.inner, text=tr("Monitor log"), bg=bg2, fg=PALETTE["text"], font=(app.ui_semibold, 10),
                 anchor="w").pack(fill=tk.X, padx=14, pady=(10, 4))
        self._log = tk.Text(card.inner, height=1, bg=PALETTE["bg1"], fg=PALETTE["muted"], relief=tk.FLAT,
                            borderwidth=0, highlightthickness=0, font=("Cascadia Code", 8), wrap="none",
                            state=tk.DISABLED, cursor="arrow", padx=8, pady=6)
        make_button(card.inner, tr("Open full diagnostics"), self._full_diagnostics, self.font, variant="ghost",
                    backdrop=bg2, small=True).pack(side=tk.BOTTOM, anchor="w", padx=(3, 14), pady=(4, 10))  # text under the title
        self._log.pack(fill=tk.BOTH, expand=True, padx=14)
        self._log.tag_config("err", foreground=PALETTE["crit"])
        self._log.tag_config("warn", foreground=PALETTE["warn"])
        card._fit()

    def _full_diagnostics(self):
        self.app.on_app_theme_change("default")
        self.app.select_tab(SIDEBAR_ITEMS.index("Diagnostics"))  # opening the page builds it if it is still empty

    # --- live -------------------------------------------------------------
    def _start_stop(self):
        if self.app.monitor_status_var.get().startswith("Running"):
            self.app.stop_monitor()
        else:
            self.app.start_monitor()

    def _tick(self):
        try:
            if self.winfo_ismapped():
                self.refresh()
        except Exception as e:  # never let a bad reading stop the loop
            self.app.log_panel_error(e)
        self.after(1000, self._tick)

    def refresh(self):
        app = self.app
        running = app.monitor_status_var.get().startswith("Running")
        link = app._link_state() if running else None  # v0.3.0: the Monitor's USB link while it is down
        if link in LINK_LABELS:
            label, level = LINK_LABELS[link]
            self._state.set(tr(label), PALETTE["warn" if level == "busy" else "crit"])
        else:
            self._state.set(tr("Running") if running else tr("Stopped"), PALETTE["green"] if running else PALETTE["muted"])
        accent = PALETTE["crit"] if running else PALETTE["cyan"]  # Stop is red, Start is the accent colour
        self._toggle.config(text=tr("Stop") if running else tr("Start"), bg=accent, fg=PALETTE["on_accent"],
                            active_bg=mix(accent, "#FFFFFF", 0.88))
        port = port_text(app.port_var.get()).replace(" ✓", "")
        self._port.config(text=port)
        self._port_info.config(text=port)
        for key, (percent, temp) in read_meters(app).items():
            draw_meter(*self.meters[key], percent, temp, app.temp_unit())
        readings = self._readings()
        for key, label in self.extra.items():
            label.config(text=metric_text(readings, key, sensor_format(key), app.temp_unit()))
        if self.pages["more"].winfo_ismapped():
            self._refresh_log()

    def _readings(self):
        """What the Live Preview reads while it runs, otherwise the loads psutil gives (as the Dashboard does)."""
        app = self.app
        with app._preview_lock:
            readings = dict(app._preview_readings) if app.preview_running else {}
        if "cpu.load" not in readings:
            readings.update(app._psutil_readings())
        return readings

    def _refresh_log(self):
        lines = self.app.recent_log_entries(LOG_LINES)
        self._log.config(state=tk.NORMAL)
        self._log.delete("1.0", tk.END)
        for when, kind, message in lines:
            self._log.insert(tk.END, f"{when} {message}\n", kind if kind != "info" else "")
        self._log.config(state=tk.DISABLED)
