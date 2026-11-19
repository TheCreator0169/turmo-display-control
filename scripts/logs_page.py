"""Settings > Logs and the log sweeper (v0.3.0): methods of TurmoApp, mixed in."""

from scripts.gui_common import *  # noqa: F401,F403

SWEEP_EVERY_MS = 24 * 3600 * 1000  # the GUI sweeps at start and once a day while it runs


class LogsPage:
    """Methods of TurmoApp (mixed in)."""

    def build_logs_card(self, card, row, bg2, small):
        """The Logs section of Settings: how long and how much to keep, what is there now, Clean now, Open folder."""
        inner = card("Logs", tr("Logs"), tr("Keep the log files small: old ones are removed by themselves."))
        self.log_keep_var = tk.IntVar(value=valid_choice(self.settings.log_keep_days, KEEP_DAYS_CHOICES, 7))
        Segmented(row(inner, tr("Keep logs for"), tr("Days an old log file is kept.")),
                  [(d, str(d)) for d in KEEP_DAYS_CHOICES], self.log_keep_var.get(),
                  lambda _v: self.on_log_rule_change(), bg2, small, variable=self.log_keep_var).pack()
        self.log_cap_var = tk.IntVar(value=valid_choice(self.settings.log_max_mb, MAX_MB_CHOICES, 20))
        Segmented(row(inner, tr("Size limit"), tr("Megabytes in all; the oldest logs go first.")),
                  [(m, str(m)) for m in MAX_MB_CHOICES], self.log_cap_var.get(),
                  lambda _v: self.on_log_rule_change(), bg2, small, variable=self.log_cap_var).pack()
        self.log_now_var = tk.StringVar()
        control = row(inner, tr("Now"), "", desc_var=self.log_now_var)
        make_button(control, tr("Clean now"), self.clean_logs_now, (self.ui_font, 10), variant="primary",
                    backdrop=bg2).pack(side=tk.LEFT, padx=(0, 8))
        make_button(control, tr("Open folder"), self.open_log_folder, (self.ui_font, 10), variant="ghost",
                    backdrop=bg2).pack(side=tk.LEFT)
        self.refresh_log_stats()

    def refresh_log_stats(self):
        files, size = log_folder_stats()
        self.log_now_var.set(f"{files} {tr('files')}, {size / 1048576:.1f} MB")

    def on_log_rule_change(self):
        self.settings.log_keep_days = int(self.log_keep_var.get())
        self.settings.log_max_mb = int(self.log_cap_var.get())
        self.settings.save()

    def clean_logs_now(self):
        """Sweep in a thread (reading thousands of old logs would freeze the window), then say what went."""
        result = []
        worker = threading.Thread(target=lambda: result.append(sweep_logs(
            keep_days=self.settings.log_keep_days, max_mb=self.settings.log_max_mb)), name="log-clean", daemon=True)
        worker.start()

        def finish():
            if worker.is_alive():
                self.root.after(150, finish)
                return
            removed, size = result[0] if result else (0, 0)
            self.refresh_log_stats()
            self.show_info(tr("Logs"), f"{removed} {tr('files removed')}, {size / 1048576:.1f} MB" if removed else
                           tr("Nothing to remove: every log is within the days and the size you chose."))
        finish()

    def open_log_folder(self):
        folder = log_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))  # Windows only, like the rest of the app
        except (OSError, AttributeError) as e:
            log_swallowed("open log folder", e)

    def start_log_sweeper(self):
        """Sweep the logs in a background thread now and again in 24 hours (no extra process, no scheduled task)."""
        def work():
            try:
                sweep_logs(keep_days=self.settings.log_keep_days, max_mb=self.settings.log_max_mb)
            except Exception as e:  # sweep_logs never raises; this is only the last net for a thread
                log_swallowed("log sweep", e)
        threading.Thread(target=work, name="log-sweep", daemon=True).start()
        self.root.after(SWEEP_EVERY_MS, self.start_log_sweeper)
