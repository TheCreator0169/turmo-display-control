"""Sensors & Graphs page (v0.2.3): methods of TurmoApp, mixed in."""

from scripts.gui_common import *  # noqa: F401,F403


class GraphPage:
    """Methods of TurmoApp (mixed in), moved out of turmo_app_enhanced.py in v0.2.3."""

    def build_graph_config_tab(self, nb):
        """Sensors & Graphs: the live sensor list, a live chart, the theme's graphs (editable) and units."""
        bg0, bg2 = PALETTE["bg0"], PALETTE["bg2"]
        frame = tk.Frame(nb, bg=bg0)
        nb.add(frame, text="Graph Config")
        page = ScrollFrame(frame, bg0)
        page.pack(fill=tk.BOTH, expand=True)
        body = tk.Frame(page.body, bg=bg0)
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=24)
        page_header(body, tr("Sensors & Graphs"), tr("Live sensor values, the graphs your theme draws and the units."), bg0,
                    (self.ui_semibold, 16), (self.ui_font, 10)).pack(fill=tk.X, pady=(0, 16))
        cols = tk.Frame(body, bg=bg0)
        cols.pack(fill=tk.BOTH, expand=True)
        cols.columnconfigure(0, minsize=self.px(300))
        cols.columnconfigure(1, weight=1)
        cols.rowconfigure(0, weight=1)
        left = tk.Frame(cols, bg=bg0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        right = tk.Frame(cols, bg=bg0)
        right.grid(row=0, column=1, sticky="new")
        semi = (self.ui_semibold, 11)

        fits = []  # cards made after the first layout need an explicit fit: rows first, then the card

        def card(parent, title, top=0, grow=False):
            outer = RoundedCard(parent, bg2, PALETTE["line"], bg0)
            outer.pack(fill=tk.BOTH if grow else tk.X, expand=grow, pady=(top, 0))
            tk.Label(outer.inner, text=title, bg=bg2, fg=PALETTE["text"], font=semi, anchor="w").pack(
                fill=tk.X, padx=16, pady=(14, 8))
            fits.append(outer)
            return outer.inner

        # Active sensors: one row per sensor, the value and a dot that is green while it reads
        inner = card(left, tr("Active sensors"), grow=True)
        self._sensor_rows, self._sensor_hist = {}, {key: deque(maxlen=60) for key in SENSOR_FORMATS}
        self._sensor_widgets = {}  # key -> its StatRow (for the rows a graph adds)
        self._sensor_inner = inner
        self._sensor_tail = tk.Frame(inner, bg=bg2, height=6)
        self._sensor_tail.pack()
        for key in SENSOR_FORMATS:
            self._add_sensor_row(key)

        # Main graph: a live chart of one sensor
        inner = card(right, tr("Main graph"))
        top = tk.Frame(inner, bg=bg2)
        top.pack(fill=tk.X, padx=16)
        self._chart_name = tk.StringVar(value=tr(SENSOR_NAMES["cpu.load"]))
        Select(top, [tr(n) for n in SENSOR_NAMES.values()], self._chart_name.get(), None, bg2, (self.ui_font, 10),
               variable=self._chart_name, width=170).pack(side=tk.LEFT)
        self._chart_value = tk.Label(top, text=NO_VALUE, bg=bg2, fg=PALETTE["cyan"],
                                     font=("Cascadia Code", 16, "bold"))
        self._chart_value.pack(side=tk.RIGHT)
        self._chart = tk.Canvas(inner, width=1, height=78, bg=bg2, highlightthickness=0)
        self._chart.pack(fill=tk.X, padx=16, pady=(10, 16))

        # The theme's graphs: the real, editable list
        inner = card(right, tr("Graphs in the theme"), top=16)
        columns = ("ID", "Sensor", "Min", "Max", "Color", "Fill", "History", "Smooth")
        tree_card = RoundedCard(inner, bg2, PALETTE["line"], bg2, radius=6)
        self.graph_tree = ttk.Treeview(tree_card.inner, columns=columns, show="headings", height=5)
        for col in columns:
            self.graph_tree.heading(col, text=tr(col))
            self.graph_tree.column(col, width=96 if col in ("ID", "Sensor") else 62, anchor=tk.CENTER)
        self.graph_tree.pack(fill=tk.X, padx=3, pady=3)
        tree_card.pack(fill=tk.X, padx=16)
        ctrl = tk.Frame(inner, bg=bg2)
        ctrl.pack(fill=tk.X, padx=16, pady=(12, 16))
        font = (self.ui_font, 10)
        buttons = ((tr("Add graph"), self.add_graph, "ghost"), (tr("Edit"), self.edit_graph, "ghost"),
                   (tr("Remove"), self.remove_graph, "ghost"), (tr("Load from theme"), self.load_graphs_from_theme, "ghost"),
                   (tr("Save to theme"), self.save_graphs_to_theme, "primary"))
        for i, (text, command, variant) in enumerate(buttons):
            # buttons keep their size; equal gaps (the odd columns stretch) from the table's left edge to its right
            make_button(ctrl, text, command, font, variant=variant, backdrop=bg2, small=True).grid(row=0, column=2 * i)
            if i:
                ctrl.columnconfigure(2 * i - 1, weight=1)

        # Units: the same setting as Settings > Units
        inner = card(right, tr("Units"), top=16)
        line = tk.Frame(inner, bg=bg2)
        line.pack(fill=tk.X, padx=16, pady=(0, 16))
        tk.Label(line, text=tr("Temperature"), bg=bg2, fg=PALETTE["text"], font=(self.ui_font, 10)).pack(side=tk.LEFT)
        if not hasattr(self, "temp_unit_var"):  # shared with Settings > Units, whichever page is built first
            self.temp_unit_var = tk.StringVar(value=self.settings.units.get("temp", "celsius"))
        Segmented(line, [("celsius", "\u00b0C"), ("fahrenheit", "\u00b0F")], self.temp_unit_var.get(), None, bg2,
                  (self.ui_font, 10), variable=self.temp_unit_var).pack(side=tk.RIGHT)

        for outer in fits:
            outer._fit()
        # Load existing graphs from current theme
        self.graph_configs = []
        self.load_graphs_from_theme()

    def load_graphs_from_theme(self):
        """Load graph configurations from current theme."""
        self.graph_configs = []
        theme_path = theme_paths.folder(DATA_ROOT / "themes", self.settings.theme) / "theme.json"
        if theme_path.exists():
            with open(theme_path) as f:
                data = json.load(f)
            for w in data.get("widgets", []):
                if w.get("type") == "graph":
                    self.graph_configs.append({
                        "id": w.get("id", ""),
                        "sensor": w.get("sensor", "cpu.load"),
                        "min": w.get("min", 0),
                        "max": w.get("max", 100),
                        "color": w.get("color", "@accent"),
                        "fill": w.get("fill", True),
                        "history": w.get("history", 120),
                        "smooth": w.get("smooth", True),
                    })
        self.refresh_graph_tree()

    def refresh_graph_tree(self):
        for item in self.graph_tree.get_children():
            self.graph_tree.delete(item)
        for g in self.graph_configs:
            self.graph_tree.insert("", tk.END, values=(
                g["id"], g["sensor"], g["min"], g["max"], g["color"],
                tr("Yes") if g["fill"] else tr("No"), g["history"], tr("Yes") if g["smooth"] else tr("No")
            ))
        self._sync_sensor_rows()

    def add_graph(self):
        self.edit_graph_dialog()

    def edit_graph(self):
        selection = self.graph_tree.selection()
        if selection:
            idx = self.graph_tree.index(selection[0])
            self.edit_graph_dialog(self.graph_configs[idx], idx)

    def edit_graph_dialog(self, config=None, idx=None):
        """Add or edit a graph in an in-app dialog (same controls as the rest of the app)."""
        config = config or {}
        default_id = f"graph_{len(self.graph_configs) + 1}"
        modal = Modal(self, "Edit graph" if idx is not None else "New graph", width=420)
        body, bg2 = modal.body, PALETTE["bg2"]
        font, small, mono = (self.ui_font, 10), (self.ui_font, 9), ("Cascadia Code", 10)
        sensors = ["cpu.load", "cpu.temp", "gpu.load", "gpu.temp", "mem.load", "mem.used", "net.down", "net.up",
                   "gpu.freq"]
        v = {"id": tk.StringVar(value=config.get("id", default_id)),
             "sensor": tk.StringVar(value=config.get("sensor", "cpu.load")),
             "min": tk.IntVar(value=config.get("min", 0)), "max": tk.IntVar(value=config.get("max", 100)),
             "color": tk.StringVar(value=config.get("color", "@accent")),
             "fill": tk.BooleanVar(value=config.get("fill", True)),
             "history": tk.IntVar(value=config.get("history", 120)),
             "smooth": tk.BooleanVar(value=config.get("smooth", True))}

        form_label(body, tr("Graph ID"), small, top=0)
        form_entry(body, v["id"], mono)
        form_label(body, tr("Sensor"), small)
        Select(body, sensors, v["sensor"].get(), None, bg2, font, variable=v["sensor"], width=200).pack(anchor="w")
        row = tk.Frame(body, bg=bg2)
        row.pack(fill=tk.X)
        for c, (key, text) in enumerate((("min", "Min value"), ("max", "Max value"))):
            row.columnconfigure(c, weight=1, uniform="range")
            cell = tk.Frame(row, bg=bg2)
            cell.grid(row=0, column=c, sticky="ew", padx=(0, 6) if c == 0 else (6, 0))
            form_label(cell, text, small)
            form_spin(cell, v[key], -100000, 100000, mono)
        form_label(body, tr("Color"), small)
        form_entry(body, v["color"], mono)
        form_label(body, tr("History points"), small)
        form_spin(body, v["history"], 2, 10000, mono)
        for key, text in (("fill", tr("Fill area")), ("smooth", tr("Smooth lines"))):
            line = tk.Frame(body, bg=bg2)
            line.pack(fill=tk.X, pady=(12, 0))
            tk.Label(line, text=text, bg=bg2, fg=PALETTE["text"], font=font).pack(side=tk.LEFT)
            Switch(line, v[key].get(), None, bg2, variable=v[key]).pack(side=tk.RIGHT)

        def on_save():
            try:
                new_config = {k: var.get() for k, var in v.items()}
            except tk.TclError:  # a number box holds text
                self.toast(tr("Min, Max and History points must be numbers"), "error")
                return
            if not new_config["id"].strip():
                self.toast(tr("The graph needs an ID"), "error")
                return
            if idx is not None:
                if config.get("id") in LOCKED_GRAPHS:
                    new_config["id"] = config["id"]  # a locked graph keeps its name, so it stays locked
                self.graph_configs[idx] = new_config
            else:
                self.graph_configs.append(new_config)
            self.refresh_graph_tree()
            modal.close()

        actions = tk.Frame(body, bg=bg2)
        actions.pack(fill=tk.X, pady=(20, 0))
        make_button(actions, tr("Save"), on_save, font, variant="primary", backdrop=bg2).pack(side=tk.RIGHT)
        make_button(actions, tr("Cancel"), modal.close, font, variant="ghost", backdrop=bg2).pack(side=tk.RIGHT, padx=(0, 8))
        modal.show()

    def remove_graph(self):
        selection = self.graph_tree.selection()
        if selection:
            idx = self.graph_tree.index(selection[0])
            if self.graph_configs[idx]["id"] in LOCKED_GRAPHS:
                self.toast(tr("{name} is a default graph and cannot be removed").format(name=self.graph_configs[idx]['id']), "error")
                return
            del self.graph_configs[idx]
            self.refresh_graph_tree()

    def save_graphs_to_theme(self):
        """Save graph configurations back to theme.json."""
        if not is_editable_theme(self.settings.theme):
            self.show_info(tr("Built-in theme"), tr("Built-in themes cannot be changed. Duplicate it in the Gallery first."))
            return
        try:  # saved in the custom folder, even for the official Custom Blank Canvas (copy on save)
            theme_path = theme_paths.own_copy(DATA_ROOT / "themes", self.settings.theme) / "theme.json"
        except OSError as e:
            self.show_error(tr("Error"), tr("Could not prepare the theme folder: {reason}").format(reason=tr(friendly_error(e))))
            return
        if not theme_path.exists():
            self.show_error(tr("Error"), tr("Theme file not found"))
            return

        with open(theme_path) as f:
            data = json.load(f)

        # Remove existing graph widgets
        data["widgets"] = [w for w in data.get("widgets", []) if w.get("type") != "graph"]

        # Add new graph widgets
        for i, g in enumerate(self.graph_configs):
            data["widgets"].append({
                "type": "graph",
                "id": g["id"],
                "x": 12,
                "y": 264,
                "w": 456,
                "h": 48,
                "sensor": g["sensor"],
                "history": g["history"],
                "min": g["min"],
                "max": g["max"],
                "color": g["color"],
                "fill": g["fill"],
                "fill_fade": True,
                "smooth": g["smooth"],
                "line_width": 1,
                "grid": 1,
                "grid_color": "@line",
                "glow": 0.25,
                "glow_radius": 4,
                "fill_alpha": 0.22
            })

        # Backup
        backup_path = theme_path.with_suffix(".json.bak")
        import shutil
        shutil.copy2(theme_path, backup_path)

        with open(theme_path, "w") as f:
            json.dump(data, f, indent=2)

        self.show_info(tr("Saved"), f"Graph configs saved to theme\nBackup: {backup_path}")
        if self.editor_initialized and self.theme_editor:
            self.theme_editor.follow(self.settings.theme)

    def open_graph_config(self):
        """Switch to Graph Config tab."""
        # Find the Graph Config tab index (0=Monitor, 1=Preview, 2=Theme Editor, 3=Settings, 4=Graph Config, 5=About)
        for i in range(self.nb.index('end')):
            if self.nb.tab(i, 'text') == 'Graph Config':
                self.nb.select(i)
                break
