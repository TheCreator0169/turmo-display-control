"""About page (v0.2.3): methods of TurmoApp, mixed in."""

from scripts.gui_common import *  # noqa: F401,F403


class AboutPage:
    """Methods of TurmoApp (mixed in), moved out of turmo_app_enhanced.py in v0.2.3."""

    def build_about_tab(self, nb):
        """About: the app name and version, the device, the config path and the features, as cards."""
        from scripts.app_version import TURMO_VERSION
        bg0, bg2 = PALETTE["bg0"], PALETTE["bg2"]
        frame = tk.Frame(nb, bg=bg0)
        nb.add(frame, text="About")
        page = ScrollFrame(frame, bg0, stretch=True)
        page.pack(fill=tk.BOTH, expand=True)
        body = tk.Frame(page.body, bg=bg0)
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)
        head = page_header(body, "TURMO Display Control",
                           f"{TURMO_VERSION} \u00b7 {tr('USB display monitor for the TURMO 3.5\u2033 panel')}",
                           bg0, (self.ui_semibold, 16), (self.ui_font, 10))
        head.pack(fill=tk.X, pady=(0, 14))
        head.actions.pack_configure(anchor="center")
        # visual only for now: a press does nothing and nothing leaves the machine
        make_button(head.actions, tr("Update"), lambda: None, (self.ui_font, 10), variant="default", backdrop=bg0,
                    icon=("\uE895", (ICON_FONT, 11))).pack()
        semi, font, mono = (self.ui_semibold, 11), (self.ui_font, 10), ("Cascadia Code", 10)
        cols = tk.Frame(body, bg=bg0)
        cols.pack(fill=tk.BOTH, expand=True)
        cols.rowconfigure(0, weight=1)
        cols.columnconfigure(0, weight=1, uniform="about")
        cols.columnconfigure(1, weight=1, uniform="about")
        left = tk.Frame(cols, bg=bg0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        right = tk.Frame(cols, bg=bg0)
        right.grid(row=0, column=1, sticky="nsew")
        fits = []

        def card(parent, title, top=16, grow=False):
            outer = RoundedCard(parent, bg2, PALETTE["line"], bg0)
            outer.pack(fill=tk.BOTH if grow else tk.X, expand=grow, pady=(top, 0))
            tk.Label(outer.inner, text=title, bg=bg2, fg=PALETTE["text"], font=semi, anchor="w").pack(
                fill=tk.X, padx=16, pady=(14, 6))
            fits.append(outer)
            return outer.inner

        def fact(inner, label, value):
            row = tk.Frame(inner, bg=bg2)
            row.pack(fill=tk.X, padx=16, pady=3)
            tk.Label(row, text=label, bg=bg2, fg=PALETTE["muted"], font=font).pack(side=tk.LEFT)
            tk.Label(row, text=value, bg=bg2, fg=PALETTE["text"], font=mono).pack(side=tk.RIGHT)

        inner = card(left, tr("Device"), top=0)
        fact(inner, tr("USB ID"), "1A86:5722")
        fact(inner, tr("Serial chip"), "CH340")
        tk.Frame(inner, bg=bg2, height=10).pack()
        inner = card(left, tr("Configuration"), grow=True)
        from pathlib import Path
        home = str(Path.home())

        def shown(folder):
            """The path with the user's folder written as %USERPROFILE% (shorter, no user name on a screenshot);
            whole folder names only, so C:/Users/me-old is left alone."""
            folder = str(folder)
            if (folder.lower() + os.sep).startswith(home.lower() + os.sep):
                return "%USERPROFILE%" + folder[len(home):]
            return folder

        def path_row(label, value, last=False):
            tk.Label(inner, text=label, bg=bg2, fg=PALETTE["muted"], font=font, anchor="w").pack(fill=tk.X, padx=16)
            tk.Label(inner, text=shown(value), bg=bg2, fg=PALETTE["text"], font=mono, anchor="nw",
                     justify=tk.LEFT, wraplength=330).pack(fill=tk.X, padx=16, pady=(4, 0 if last else 10))

        path_row(tr("Settings file"), self.settings.path())
        path_row(tr("Custom themes"), theme_paths.custom_dir())
        fact(inner, tr("Version"), TURMO_VERSION)
        fact(inner, tr("License"), "GPL-3.0-or-later")
        fact(inner, tr("Display"), "480 \u00d7 320 / 320 \u00d7 480")
        fact(inner, tr("Port"), "COM4 \u00b7 115200 baud")
        fact(inner, tr("Monitor log"), "%LOCALAPPDATA%\\TURMO\\logs")
        tk.Frame(inner, bg=bg2, height=10).pack()
        inner = card(right, tr("Features"), top=0, grow=True)
        features = [
            "Real-time CPU/GPU/RAM/Network/Disk monitoring",
            "CPU temperature via LibreHardwareMonitor + PawnIO",
            "NVIDIA GPU monitoring via NVML",
            "Multiple themes with visual editor",
            "Portrait & Landscape orientation support",
            "System tray integration with Windows startup",
            "Automatic USB detection & reconnection",
            "Live preview with configurable FPS",
            "Drag-and-drop editor using the LCD renderer",
            "Icon picker, shapes, rounded rectangles and bars",
            "Your own themes are saved safely and run on the LCD",
            "Built-in themes are protected; duplicate one to edit it",
            "The Monitor log says why it stopped",
            "Graph sensor customization",
            "No cloud dependency - fully local"
        ]
        for f in features:
            row = tk.Frame(inner, bg=bg2)
            row.pack(fill=tk.X, padx=16, pady=2)
            tk.Label(row, text="\u25cf", bg=bg2, fg=PALETTE["cyan"], font=(self.ui_font, 6)).pack(side=tk.LEFT)
            tk.Label(row, text=tr(f), bg=bg2, fg=PALETTE["text"], font=font, anchor="w").pack(
                side=tk.LEFT, padx=(10, 0))
        tk.Frame(inner, bg=bg2, height=10).pack()
        for outer in fits:
            outer._fit()

    def show_about(self):
        self.show_info(tr("About TURMO"), modal=True, text=
            "TURMO Display Control\n\n"
            "USB display monitor for TURMO 3.5\" panel\n"
            "VID:PID 1A86:5722 | CH340 serial\n\n"
            "Features:\n"
            "• Real-time CPU/GPU/RAM/Network/Disk monitoring\n"
            "• CPU temperature via LibreHardwareMonitor + PawnIO\n"
            "• NVIDIA GPU monitoring via NVML\n"
            "• Multiple themes with visual editor\n"
            "• Portrait & Landscape orientation support\n"
            "• System tray integration with Windows startup\n"
            "• Automatic USB detection & reconnection\n"
            "• Live preview with configurable FPS\n"
            "• Drag-and-drop theme editor\n"
            "• Graph sensor customization\n"
            "• No cloud dependency - fully local")
