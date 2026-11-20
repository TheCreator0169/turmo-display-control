"""First-run screen (v0.3.0): shown once after a fresh install (no settings file at launch). Four checks in one
dialog: the display, the CPU temperature helper, the language and the look (Default or Minimalist). Methods of TurmoApp, mixed in."""

from scripts.gui_common import *  # noqa: F401,F403

POLL_MS = 1000


def cpu_helper_running() -> bool:
    """True when the elevated CPU temperature helper answers on localhost (same check as the Settings page)."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 18234), timeout=0.5) as s:
            s.sendall(b"GET\n")
            return bool(s.recv(4096))
    except OSError:
        return False


class FirstRunPage:
    """Methods of TurmoApp (mixed in)."""

    def start_first_run(self):
        """Show the first-run dialog when this launch found no settings file; writes the file at once so it comes once."""
        if not getattr(self, "_first_run", False):
            return
        self._first_run = False
        try:
            self.settings.save()
        except Exception as e:  # a read-only profile: the dialog still shows, it just comes back next launch
            log_swallowed("first run save", e)
        self._first_run_done = False
        try:
            self.show_first_run()
        except Exception as e:
            log_swallowed("first run", e)
        self.root.after(500, self._first_run_guard)

    def _first_run_guard(self):
        """The dialog must be answered with Done: when an alert (a cancelled admin prompt, say) took its place and was
        closed, show it again."""
        if self._first_run_done:
            return
        try:
            if getattr(self, "_modal", None) is None:
                self.show_first_run()
        except Exception as e:
            log_swallowed("first run guard", e)
        self.root.after(500, self._first_run_guard)

    def show_first_run(self):
        bg2, muted, small = PALETTE["bg2"], PALETTE["muted"], (self.ui_font, 9)
        modal = Modal(self, tr("Welcome to TURMO"), width=460, dismissable=False)  # Done is the only way out
        tk.Label(modal.body, text=tr("Four quick checks. You can change all of this later in Settings."), bg=bg2, fg=muted,
                 font=(self.ui_font, 10), justify=tk.LEFT, anchor="w", wraplength=410).pack(fill=tk.X, pady=(0, 10))

        def line(name, hint=""):
            tk.Frame(modal.body, bg=PALETTE["line"], height=1).pack(fill=tk.X)
            row = tk.Frame(modal.body, bg=bg2)
            row.pack(fill=tk.X, pady=8)
            tk.Label(row, text=tr(name), bg=bg2, fg=PALETTE["text"], font=(self.ui_semibold, 10), anchor="w").pack(side=tk.LEFT)
            hint_label = None
            if hint is not None:
                hint_label = tk.Label(modal.body, text="", bg=bg2, fg=muted, font=small, justify=tk.LEFT, anchor="w",
                                      wraplength=410)
            return row, hint_label

        # 1. the display
        row, note = line("Display")
        display_row = row
        display = Badge(row, bg2, (self.ui_font, 9, "bold"))
        display.pack(side=tk.RIGHT)
        # 2. the CPU temperature helper
        row, _ = line("CPU temperature", None)
        cpu = Badge(row, bg2, (self.ui_font, 9, "bold"))
        asked = [0.0]

        def ask_helper():
            if time.monotonic() - asked[0] < 15:  # the admin prompt is still open: a second click would start a second one
                return
            asked[0] = time.monotonic()
            self.toggle_cpu_temp_helper()
        enable = make_button(row, tr("Enable (one-time admin prompt)"), ask_helper, (self.ui_font, 10),
                             variant="primary", backdrop=bg2, small=True)
        # 3. the language: chosen at once (no question, this is the first choice); the window is drawn again in it and
        #    the guard below shows this dialog again, in the new language
        row, _ = line("Language", None)
        langs = tk.Frame(modal.body, bg=bg2)
        langs.pack(fill=tk.X, pady=(0, 8))
        lang_now = self.settings.language if self.settings.language in ("en", "fr", "pt") else "en"
        lang_tiles = {}

        def pick_language(key):
            if key == lang_now:
                return
            for k, tile in lang_tiles.items():
                tile.set_selected(k == key)
            modal.close()  # also applies a Look already picked
            self.settings.language = key
            self.settings.save()
            i18n.set_language(key)
            self.root.after_idle(self.rebuild_ui)
        for i, (key, name) in enumerate((("en", "English"), ("fr", "Français"), ("pt", "Português"))):
            langs.columnconfigure(i, weight=1, uniform="firstlang")
            tile = ChoiceTile(langs, name, key == lang_now, lambda k=key: pick_language(k), bg2, (self.ui_semibold, 10))
            tile.grid(row=0, column=i, sticky="ew", padx=(0, 8) if i < 2 else 0)
            lang_tiles[key] = tile
        # 4. the look
        row, _ = line("Look", None)
        tiles = tk.Frame(modal.body, bg=bg2)
        tiles.pack(fill=tk.X, pady=(0, 8))
        chosen = {}
        current = self.settings.app_theme if self.settings.app_theme in ("default", "minimalist") else "default"

        choice = [current]

        def pick(key):  # applied when the dialog closes: the Minimalist window is small and would cover this card
            choice[0] = key
            for k, tile in chosen.items():
                tile.set_selected(k == key)
        for i, (key, name) in enumerate((("default", tr("Default")), ("minimalist", tr("Minimalist")))):
            tiles.columnconfigure(i, weight=1, uniform="firstlook")
            tile = ChoiceTile(tiles, name, key == current, lambda k=key: pick(k), bg2, (self.ui_semibold, 10))
            tile.grid(row=0, column=i, sticky="ew", padx=(0, 8) if i == 0 else 0)
            chosen[key] = tile
        actions = tk.Frame(modal.body, bg=bg2)
        actions.pack(fill=tk.X, pady=(8, 0))
        close = modal.close

        def close_and_apply():
            close()
            if choice[0] != current:
                self.on_app_theme_change(choice[0])
        modal.close = close_and_apply

        def finish():
            self._first_run_done = True
            close_and_apply()
        make_button(actions, tr("Done"), finish, (self.ui_font, 10), variant="primary", backdrop=bg2).pack(side=tk.RIGHT)

        seen = {"port": None, "helper": None}  # filled by a thread: a closed loopback port can take 0.5 s to answer

        def probe():
            try:
                seen["port"], seen["helper"] = find_turmo_port(), cpu_helper_running()
            except Exception as e:  # never let a probe end the loop
                log_swallowed("first run probe", e)
            seen["busy"] = False

        def refresh():
            if not modal.scrim.winfo_exists():
                return  # closed: the loop ends
            try:
                if not seen.get("busy"):
                    seen["busy"] = True
                    threading.Thread(target=probe, name="first-run-probe", daemon=True).start()
                if seen["helper"] is not None:  # the first answer comes within a second
                    port = seen["port"]
                    if port:
                        display.set(f"{tr('Connected')} {port}", PALETTE["green"])
                        note.pack_forget()  # no hint line, no empty gap
                    else:
                        display.set(tr("Not found"), PALETTE["warn"])
                        note.config(text=tr("Plug it in and switch it on, the app will find it."))
                        note.pack(fill=tk.X, after=display_row)
                    if seen["helper"]:
                        enable.pack_forget()
                        cpu.set(tr("Enabled"), PALETTE["green"])
                        cpu.pack(side=tk.RIGHT)
                    else:
                        cpu.pack_forget()
                        enable.pack(side=tk.RIGHT)
                    modal.card._fit()
            except Exception as e:
                log_swallowed("first run refresh", e)
            self.root.after(POLL_MS, refresh)
        refresh()
        modal.show()
