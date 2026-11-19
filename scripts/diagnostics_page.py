"""Diagnostics page (v0.2.3): methods of TurmoApp, mixed in."""

from scripts.gui_common import *  # noqa: F401,F403


class DiagnosticsPage:
    """Methods of TurmoApp (mixed in), moved out of turmo_app_enhanced.py in v0.2.3."""

    def build_diagnostics_tab(self, nb):
        """Diagnostics (v0.2.0 design): four status tiles, then workers and the live log on the left,
        recent errors and recovery actions on the right."""
        bg0, bg1, bg2 = PALETTE["bg0"], PALETTE["bg1"], PALETTE["bg2"]
        small, semi, mono = (self.ui_font, 9), (self.ui_semibold, 11), ("Cascadia Code", 9)
        frame = tk.Frame(nb, bg=bg0)
        nb.add(frame, text="Diagnostics")
        self.diag_frame = frame
        page = ScrollFrame(frame, bg0)
        page.pack(fill=tk.BOTH, expand=True)
        body = tk.Frame(page.body, bg=bg0)
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=24)
        page_header(body, tr("Diagnostics & Log"), tr("USB link health, background workers and the live log."), bg0,
                    (self.ui_semibold, 16), (self.ui_font, 10)).pack(fill=tk.X, pady=(0, 16))

        # Status tiles: label and icon tile, value, subtitle
        tiles = tk.Frame(body, bg=bg0)
        tiles.pack(fill=tk.X)
        self.diag_tiles, self.diag_subs = {}, {}
        specs = (("Connection", "\uE73E", PALETTE["green"]), ("Frames", "\uE7F4", PALETTE["cyan"]),
                 ("Serial latency", "\uE9D2", PALETTE["blue"]), ("App CPU", "\uE950", PALETTE["violet"]))
        for i, (title, glyph, colour) in enumerate(specs):
            outer = RoundedCard(tiles, bg2, PALETTE["line"], bg0)
            outer.grid(row=0, column=i, sticky="nsew", padx=(0, 16) if i < 3 else 0)
            tiles.columnconfigure(i, weight=1, uniform="tile")
            tile = outer.inner
            head = tk.Frame(tile, bg=bg2)
            head.pack(fill=tk.X, padx=16, pady=(14, 0))
            tk.Label(head, text=tr(title).upper(), bg=bg2, fg=PALETTE["muted"],
                     font=(self.ui_font, 8, "bold")).pack(side=tk.LEFT)
            ico = tk.Canvas(head, width=30, height=30, bg=bg2, highlightthickness=0)
            ico.pack(side=tk.RIGHT)
            round_rect(ico, 1, 1, 29, 29, 10, fill=mix(colour, bg2, 0.15), outline="")
            ico.create_text(15, 15, text=glyph, font=(ICON_FONT, 11), fill=colour)
            value = tk.Label(tile, text=NO_VALUE, bg=bg2, fg=PALETTE["text"], font=("Cascadia Code", 18, "bold"))
            value.pack(anchor=tk.W, padx=16, pady=(6, 0))
            sub = tk.Label(tile, text="", bg=bg2, fg=PALETTE["muted"], font=(self.ui_font, 9), anchor="w")
            sub.pack(fill=tk.X, padx=16, pady=(0, 14))
            self.diag_tiles[title], self.diag_subs[title] = value, sub

        cols = tk.Frame(body, bg=bg0)
        cols.pack(fill=tk.BOTH, expand=True, pady=(16, 0))
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, minsize=self.px(340))
        left = tk.Frame(cols, bg=bg0)
        left.grid(row=0, column=0, sticky="new", padx=(0, 16))
        right = tk.Frame(cols, bg=bg0)
        right.grid(row=0, column=1, sticky="new")

        def card(parent, title, subtitle, top=0):
            outer = RoundedCard(parent, bg2, PALETTE["line"], bg0)
            outer.pack(fill=tk.X, pady=(top, 0))
            head = tk.Frame(outer.inner, bg=bg2)
            head.pack(fill=tk.X, padx=16, pady=(14, 0))
            tk.Label(head, text=title, bg=bg2, fg=PALETTE["text"], font=semi).pack(side=tk.LEFT)
            if subtitle:
                tk.Label(outer.inner, text=subtitle, bg=bg2, fg=PALETTE["muted"], font=small,
                         anchor="w").pack(fill=tk.X, padx=16, pady=(2, 10))
            return outer.inner, head

        # Workers: one row each; the Monitor worker and the Live Preview can be restarted from here
        workers, _h = card(left, tr("Background workers"), tr("Threads and processes that monitor and render."))
        self.diag_workers = {}
        rows = (("GUI", "\uE7F4", None), ("Monitor worker", "\uE9D2", self.restart_monitor),
                ("Live Preview", "\uE7B3", self.restart_preview), ("Tray", "\uE8A7", None))
        for name, glyph, restart in rows:
            row_outer = RoundedCard(workers, bg1, PALETTE["line"], bg2, radius=10)
            row_outer.pack(fill=tk.X, padx=16, pady=(0, 8))
            row = row_outer.inner
            tk.Label(row, text=glyph, bg=bg1, fg=PALETTE["muted"], font=(ICON_FONT, 11)).pack(
                side=tk.LEFT, padx=(12, 8), pady=10)
            tk.Label(row, text=tr(name), bg=bg1, fg=PALETTE["text"], font=(self.ui_semibold, 10)).pack(side=tk.LEFT)
            if restart:
                make_button(row, tr("Restart"), restart, small, variant="ghost", backdrop=bg1, small=True).pack(
                    side=tk.RIGHT, padx=(8, 8))
            state = tk.Label(row, text=NO_VALUE, bg=bg1, fg=PALETTE["dim"], font=mono)
            # no button: end where the Restart text ends (the button's 8 px margin plus its 11 px padding)
            state.pack(side=tk.RIGHT, padx=(8, 0) if restart else (8, 19))
            self.diag_workers[name] = state
        tk.Frame(workers, bg=bg2, height=6).pack()

        # Live log: time coloured by level, message in the text colour
        logbox, head = card(left, tr("Live log"), "", top=16)
        make_button(head, tr("Clear"), self._clear_diag_log, small, variant="ghost", backdrop=bg2,
                    small=True).pack(side=tk.RIGHT)
        view = RoundedCard(logbox, bg0, PALETTE["line"], bg2, radius=10)
        view.pack(fill=tk.X, padx=16, pady=(8, 16))
        self.diag_log = tk.Text(view.inner, bg=bg0, fg=PALETTE["text"], relief=tk.FLAT, borderwidth=0,
                                highlightthickness=0, font=("Cascadia Code", 9), wrap=tk.NONE, height=14, width=1,
                                padx=12, pady=10)
        self.diag_log.pack(fill=tk.X, padx=2, pady=2)
        for kind, colour in (("info", PALETTE["cyan"]), ("warn", PALETTE["warn"]), ("err", PALETTE["crit"])):
            self.diag_log.tag_config("t_" + kind, foreground=colour)
        self.diag_log.tag_config("m_err", foreground=PALETTE["crit"])
        self.diag_log.tag_config("m_warn", foreground=PALETTE["warn"])
        self.diag_log.config(state=tk.DISABLED)
        self._diag_ticks, self._diag_clear_pos, self._diag_err_key = 0, 0, None

        # Recent errors
        errs, _h = card(right, tr("Recent errors"), tr("Alerts from the runtime log."))
        self.diag_errors = tk.Frame(errs, bg=bg2)
        self.diag_errors.pack(fill=tk.X, padx=16, pady=(0, 16))

        # Recovery actions: what exists works, the rest is shown disabled
        rec, _h = card(right, tr("Recovery actions"), tr("Tools for when the USB display freezes."), top=16)
        grid = tk.Frame(rec, bg=bg2)
        grid.pack(fill=tk.X, padx=16, pady=(0, 8))
        grid.columnconfigure(0, weight=1, uniform="rec")
        grid.columnconfigure(1, weight=1, uniform="rec")
        buttons = (("Restart Monitor", self.restart_monitor, "primary", True),
                   ("Export logs", self.export_runtime_log, "ghost", True),
                   ("Flush buffer", None, "ghost", False), ("Hardware reset", None, "ghost", False))
        for i, (text, command, variant, enabled) in enumerate(buttons):
            btn = make_button(grid, tr(text), command, (self.ui_font, 10), variant=variant, backdrop=bg2)
            btn.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 5) if i % 2 == 0 else (5, 0), pady=(0, 10))
            if not enabled:
                btn.config(state="disabled")
        tk.Label(rec, text=tr("Flush and reset: no documented device command yet."), bg=bg2, fg=PALETTE["dim"],
                 font=(self.ui_font, 8), anchor="w").pack(fill=tk.X, padx=16, pady=(0, 14))

    def _app_cpu(self):
        """This app's CPU percent since the last call. One Process object is kept: a new one reports 0 on its first
        reading, so a fresh object every second made the tile read 0.0 % for good."""
        import psutil
        if getattr(self, "_app_proc", None) is None:
            self._app_proc = psutil.Process(os.getpid())
        return self._app_proc.cpu_percent(interval=None)

    def _refresh_diagnostics(self):
        import os
        import psutil
        port = self.port_var.get()
        link = self._link_state()
        if link in LINK_LABELS and self.monitor_status_var.get().startswith("Running"):
            state, level = LINK_LABELS[link]
            colour = PALETTE["warn" if level == "busy" else "crit"]
            sub = tr("The Monitor keeps trying by itself")
        elif link == "connected" and self.monitor_status_var.get().startswith("Running"):
            state, colour, sub = "Connected", PALETTE["green"], "1A86:5722"
        elif "\u2713" in port:
            state, colour, sub = "Connected", PALETTE["green"], f"{port.split()[0]} (1A86:5722)"
        elif "Busy" in port:
            state, colour, sub = "Busy", PALETTE["warn"], tr("Port in use by another program")
        else:
            state, colour, sub = "Disconnected", PALETTE["crit"], tr("No TURMO display found")
        shown = tr(state)
        self.diag_tiles["Connection"].config(text=shown, fg=colour,
                                             font=("Cascadia Code", 18 if len(shown) < 10 else 14, "bold"))
        self.diag_subs["Connection"].config(text=sub)
        self.diag_tiles["Frames"].config(text=f"#{getattr(self, '_frame_count', 0)}")
        self.diag_subs["Frames"].config(text=tr("Live Preview frames"))
        stats = read_serial_stats()  # written by the Monitor, which owns the port; None while it is not running
        self.diag_tiles["Serial latency"].config(text=f"{stats[0]:.0f} ms" if stats else NO_VALUE)
        self.diag_subs["Serial latency"].config(text=tr("Per frame") if stats else tr("Not measured"))
        try:
            self.diag_tiles["App CPU"].config(text=f"{self._app_cpu():.1f}%")
            self.diag_subs["App CPU"].config(text=tr("This app only"))
        except Exception as e:
            log_swallowed("App CPU tile", e)
        self.diag_workers["GUI"].config(text=f"PID {os.getpid()}")
        mon = self.monitor_process
        if mon is not None and mon.poll() is None:
            monitor_text = f"PID {mon.pid}"
        else:
            outside = self._other_monitor_pids() if hasattr(self, "_other_monitor_pids") else []
            monitor_text = f"PID {outside[0]} (outside)" if outside else tr("stopped")
        self.diag_workers["Monitor worker"].config(text=monitor_text)
        live = self._preview_worker_thread is not None and self._preview_worker_thread.is_alive()
        self.diag_workers["Live Preview"].config(text=tr("running") if live else tr("stopped"))
        tray = self.tray_thread is not None and self.tray_thread.is_alive()
        self.diag_workers["Tray"].config(text=tr("running") if tray else tr("stopped"))
        self._diag_ticks += 1
        if self._diag_ticks % 3 == 1:  # the log every 3 seconds
            self._refresh_diag_log()

    def _clear_diag_log(self):
        """Clear empties the view only: the log file stays, and later lines still appear."""
        path = get_runtime_log_path() if RUNTIME_LOGGING_AVAILABLE else None
        try:
            self._diag_clear_pos = os.path.getsize(path) if path else 0
        except OSError:
            self._diag_clear_pos = 0  # ok: log file not readable yet
        self._refresh_diag_log()

    def recent_log_entries(self, limit=6, tail=16384):
        """The newest runtime-log entries as (time, kind, message); only the file's tail is read."""
        if not RUNTIME_LOGGING_AVAILABLE:
            return []
        path = get_runtime_log_path()
        if path is None:
            return []
        try:
            with open(path, "rb") as f:
                f.seek(0, 2)
                f.seek(max(self._diag_clear_pos, f.tell() - tail))
                text = f.read().decode("utf-8", errors="replace")
        except Exception as _e:
            log_swallowed("recent log entries", _e)
            return []
        return [(when, log_kind(level), message[:70]) for when, level, message in parse_log(text.splitlines(), limit)]

    def _refresh_diag_log(self):
        if not RUNTIME_LOGGING_AVAILABLE:
            return
        path = get_runtime_log_path()
        if path is None:
            return
        try:
            with open(path, "rb") as f:
                f.seek(0, 2)
                f.seek(max(self._diag_clear_pos, f.tell() - 65536))
                text = f.read().decode("utf-8", errors="replace")
        except Exception as _e:
            log_swallowed("diagnostics refresh", _e)
            return
        entries = parse_log(text.splitlines())
        at_end = self.diag_log.yview()[1] >= 0.99  # a reader who scrolled up keeps their place
        self.diag_log.config(state=tk.NORMAL)
        self.diag_log.delete("1.0", tk.END)
        for when, level, message in entries:
            kind = log_kind(level)
            self.diag_log.insert(tk.END, f"[{when}] ", "t_" + kind)
            self.diag_log.insert(tk.END, message + "\n", "m_" + kind if kind != "info" else "")
        if at_end:
            self.diag_log.see(tk.END)
        self.diag_log.config(state=tk.DISABLED)
        self._refresh_diag_errors(recent_errors(entries))

    def _refresh_diag_errors(self, errors):
        """The Recent errors card: the last errors of the log, or a calm message when there are none."""
        if errors == self._diag_err_key:
            return
        self._diag_err_key = errors
        bg2 = PALETTE["bg2"]
        for child in self.diag_errors.winfo_children():
            child.destroy()
        items = [(f"[{t}]", msg, PALETTE["crit"]) for t, _lvl, msg in errors] or [
            (tr("No active errors"), tr("No error in the recent part of the runtime log."), PALETTE["green"])]
        for title, text, colour in items:
            outer = RoundedCard(self.diag_errors, mix(colour, bg2, 0.06), PALETTE["line"], bg2, radius=10)
            outer.pack(fill=tk.X, pady=(0, 8))
            tk.Label(outer.inner, text=title, bg=mix(colour, bg2, 0.06), fg=colour,
                     font=(self.ui_semibold, 10), anchor="w").pack(fill=tk.X, padx=12, pady=(10, 0))
            tk.Label(outer.inner, text=text, bg=mix(colour, bg2, 0.06), fg=PALETTE["muted"],
                     font=(self.ui_font, 9), anchor="w", justify=tk.LEFT, wraplength=270).pack(
                fill=tk.X, padx=12, pady=(2, 10))
            outer._fit()  # cards added after the first layout get no event: size them now
        self.diag_errors.master.master._fit()  # and the Recent errors card around them

    def export_runtime_log(self):
        import shutil
        path = get_runtime_log_path() if RUNTIME_LOGGING_AVAILABLE else None
        if path is None:
            self.show_info(tr("Export logs"), tr("No runtime log yet."))
            return
        dest = filedialog.asksaveasfilename(defaultextension=".log", initialfile="turmo_runtime.log",
                                            filetypes=[("Log file", "*.log"), ("All files", "*.*")])
        if dest:
            shutil.copyfile(path, dest)
            self.status_var.set(f"Logs exported to {dest}")
